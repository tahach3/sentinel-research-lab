-- Round 5A repair: 24h approval expiry, aggregate pilot preflight, residue cleanup
BEGIN;

-- ---------------------------------------------------------------------------
-- Activation metadata
-- ---------------------------------------------------------------------------
ALTER TABLE research.provider_authorization_records
  ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS test_fixture_id TEXT;

COMMENT ON COLUMN research.provider_authorization_records.test_fixture_id IS
  'Stable test provenance marker; production rows must be NULL';

ALTER TABLE research.provider_usage_ledger
  ADD COLUMN IF NOT EXISTS pilot_proposal_id UUID REFERENCES research.provider_pilot_proposals(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS success BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS is_retry BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS test_fixture_id TEXT;

-- Migrate Round 5A proposed shells: no usable future window while proposed
UPDATE research.provider_authorization_records a
SET expires_at = TIMESTAMPTZ '-infinity',
    activated_at = NULL
FROM research.provider_pilot_proposals pp
WHERE a.pilot_proposal_id = pp.id
  AND pp.pilot_code = 'GEMINI-PILOT-5A'
  AND a.status = 'proposed';

-- Revoke ONLY proven Round 5A test residue:
-- pattern unique to database/tests/006_gemini_pilot_5a.sql (max_requests=1, max_tokens=1000,
-- max_cost=0, no pilot link, active). Round 4 fixtures used max_requests=3 and are left untouched.
UPDATE research.provider_authorization_records a
SET status = 'revoked'
FROM research.providers p
WHERE a.provider_id = p.id
  AND p.code = 'gemini'
  AND a.pilot_proposal_id IS NULL
  AND a.test_fixture_id IS NULL
  AND a.status = 'active'
  AND a.max_requests = 1
  AND a.max_tokens = 1000
  AND a.max_cost_usd = 0
  AND a.approving_authority = 'Taha';

-- ---------------------------------------------------------------------------
-- Governed activation + fail-closed validity window
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION research.trg_authorization_validity_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.status = 'proposed' THEN
    NEW.activated_at := NULL;
    -- Proposed rows must not carry a usable future validity window
    NEW.expires_at := TIMESTAMPTZ '-infinity';
  END IF;

  IF NEW.status = 'active' THEN
    IF TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'active' THEN
      NEW.activated_at := COALESCE(NEW.activated_at, NOW());
      -- Always derive expiry from approval/activation time (ignore caller-supplied long windows)
      NEW.expires_at := NEW.activated_at + INTERVAL '24 hours';
    END IF;

    IF NEW.activated_at IS NULL THEN
      RAISE EXCEPTION 'active authorization requires activated_at';
    END IF;

    IF NEW.expires_at > NEW.activated_at + INTERVAL '24 hours' THEN
      RAISE EXCEPTION 'authorization validity cannot exceed 24 hours after activation';
    END IF;

    IF NEW.expires_at <= NEW.activated_at THEN
      RAISE EXCEPTION 'active authorization expires_at must be after activated_at';
    END IF;

    IF NEW.approving_authority IS DISTINCT FROM 'Taha' THEN
      RAISE EXCEPTION 'approving_authority must be Taha';
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS provider_authorization_validity_guard ON research.provider_authorization_records;
CREATE TRIGGER provider_authorization_validity_guard
  BEFORE INSERT OR UPDATE OF status, expires_at, activated_at, approving_authority
  ON research.provider_authorization_records
  FOR EACH ROW EXECUTE FUNCTION research.trg_authorization_validity_guard();

-- Governed activation for pilot-linked authorizations
CREATE OR REPLACE FUNCTION research.activate_pilot_authorization(
  p_authorization_id UUID,
  p_pilot_code TEXT DEFAULT 'GEMINI-PILOT-5A'
) RETURNS research.provider_authorization_records
LANGUAGE plpgsql
AS $$
DECLARE
  v_auth research.provider_authorization_records%ROWTYPE;
  v_pilot research.provider_pilot_proposals%ROWTYPE;
  v_provider research.providers%ROWTYPE;
  v_model research.provider_model_candidates%ROWTYPE;
  v_now TIMESTAMPTZ := NOW();
BEGIN
  SELECT * INTO v_auth FROM research.provider_authorization_records WHERE id = p_authorization_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'authorization % not found', p_authorization_id;
  END IF;
  IF v_auth.status <> 'proposed' THEN
    RAISE EXCEPTION 'only proposed authorizations can be activated (got %)', v_auth.status;
  END IF;
  IF v_auth.pilot_proposal_id IS NULL THEN
    RAISE EXCEPTION 'authorization is not linked to a pilot proposal';
  END IF;

  SELECT * INTO v_pilot FROM research.provider_pilot_proposals WHERE id = v_auth.pilot_proposal_id FOR UPDATE;
  IF v_pilot.pilot_code IS DISTINCT FROM p_pilot_code THEN
    RAISE EXCEPTION 'pilot mismatch: expected %, got %', p_pilot_code, v_pilot.pilot_code;
  END IF;
  IF v_pilot.status NOT IN ('awaiting_taha_approval', 'approved') THEN
    -- Allow activation only after credential handoff path marks awaiting_taha_approval or approved
    -- Round 5A remains disabled; function exists for governed future use / tests
    IF v_pilot.status NOT IN ('awaiting_taha_credential', 'awaiting_taha_approval', 'approved') THEN
      RAISE EXCEPTION 'pilot status % cannot activate authorizations', v_pilot.status;
    END IF;
  END IF;

  SELECT * INTO v_provider FROM research.providers WHERE id = v_auth.provider_id;
  SELECT * INTO v_model FROM research.provider_model_candidates WHERE id = v_auth.model_candidate_id;
  IF v_provider.code <> 'gemini' OR v_model.model_id_provisional <> 'gemini-2.5-flash' THEN
    RAISE EXCEPTION 'activation limited to gemini / gemini-2.5-flash';
  END IF;
  IF NOT (v_auth.benchmark_case_id = ANY (v_pilot.benchmark_case_ids)) THEN
    RAISE EXCEPTION 'authorization case not in pilot proposal';
  END IF;
  IF v_auth.approving_authority <> 'Taha' THEN
    RAISE EXCEPTION 'authority must be Taha';
  END IF;

  UPDATE research.provider_pilot_proposals
  SET status = CASE WHEN status = 'approved' THEN status ELSE 'approved' END,
      taha_approved_at = COALESCE(taha_approved_at, v_now),
      expires_at = COALESCE(expires_at, v_now + (expiry_hours_after_approval || ' hours')::interval),
      updated_at = v_now
  WHERE id = v_pilot.id;

  UPDATE research.provider_authorization_records
  SET status = 'active',
      activated_at = v_now,
      expires_at = v_now + INTERVAL '24 hours'
  WHERE id = p_authorization_id
  RETURNING * INTO v_auth;

  RETURN v_auth;
END;
$$;

-- ---------------------------------------------------------------------------
-- Aggregate pilot enforcement inside production preflight
-- ---------------------------------------------------------------------------
-- Drop prior overloads so aggregate-aware signature is unique
DROP FUNCTION IF EXISTS research.live_preflight(TEXT, TEXT, UUID, UUID, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS research.live_preflight(TEXT, TEXT, UUID, UUID, TEXT, TEXT, TEXT, INTEGER, INTEGER, BOOLEAN, TEXT);

CREATE OR REPLACE FUNCTION research.live_preflight(
  p_provider_code TEXT,
  p_model_provisional TEXT,
  p_benchmark_case_id UUID,
  p_authorization_id UUID,
  p_role_code TEXT,
  p_confidentiality_class TEXT,
  p_claimed_credential_status TEXT DEFAULT NULL,
  p_projected_input_tokens INTEGER DEFAULT 0,
  p_projected_output_tokens INTEGER DEFAULT 0,
  p_is_retry BOOLEAN DEFAULT FALSE,
  p_fallback_provider TEXT DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_provider research.providers%ROWTYPE;
  v_model research.provider_model_candidates%ROWTYPE;
  v_cred research.provider_credential_status%ROWTYPE;
  v_auth research.provider_authorization_records%ROWTYPE;
  v_budget research.provider_budget_policies%ROWTYPE;
  v_adapter research.provider_adapter_versions%ROWTYPE;
  v_pilot research.provider_pilot_proposals%ROWTYPE;
  v_day_req BIGINT;
  v_day_tok BIGINT;
  v_month_cost NUMERIC;
  v_steps JSONB := '[]'::jsonb;
  v_pilot_req BIGINT;
  v_pilot_success BIGINT;
  v_pilot_in BIGINT;
  v_pilot_out BIGINT;
  v_case_attempts BIGINT;
BEGIN
  IF COALESCE(p_projected_input_tokens, 0) < 0 OR COALESCE(p_projected_output_tokens, 0) < 0 THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'negative projected tokens', 'steps', v_steps);
  END IF;

  SELECT * INTO v_provider FROM research.providers WHERE code = p_provider_code;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'provider_disabled', 'detail', 'unknown provider', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 1, 'name', 'provider_enabled'));
  IF NOT v_provider.enabled THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'provider_disabled', 'detail', 'provider disabled', 'steps', v_steps, 'envelope', NULL);
  END IF;

  SELECT * INTO v_model FROM research.provider_model_candidates
  WHERE provider_id = v_provider.id AND model_id_provisional = p_model_provisional;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'model_disabled', 'detail', 'model candidate missing', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 2, 'name', 'model_enabled_verified'));
  IF NOT v_model.enabled THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'model_disabled', 'detail', 'model disabled', 'steps', v_steps);
  END IF;
  IF v_model.verification_status <> 'verified' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'model_unverified', 'detail', 'model unverified', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 3, 'name', 'role_permitted'));
  IF p_role_code IS NULL OR p_role_code NOT IN (
    'researcher','planner','implementation_proposal_writer','qa_checker','independent_reviewer','debugger'
  ) THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'role not permitted', 'steps', v_steps);
  END IF;

  SELECT * INTO v_cred FROM research.provider_credential_status WHERE provider_id = v_provider.id;
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 4, 'name', 'credential_status'));
  IF p_claimed_credential_status IS NOT NULL AND p_claimed_credential_status IS DISTINCT FROM v_cred.status THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'credential_missing', 'detail', 'caller credential claim rejected; stored state wins', 'steps', v_steps);
  END IF;
  IF v_cred.status IS DISTINCT FROM 'present' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'credential_missing', 'detail', 'credential status not present', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 5, 'name', 'authorization_valid'));
  IF p_authorization_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_missing', 'detail', 'no authorization id', 'steps', v_steps);
  END IF;
  SELECT * INTO v_auth FROM research.provider_authorization_records WHERE id = p_authorization_id;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_missing', 'detail', 'authorization not found', 'steps', v_steps);
  END IF;
  IF v_auth.status <> 'active' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'authorization not active', 'steps', v_steps);
  END IF;
  IF v_auth.expires_at <= NOW() OR v_auth.status = 'expired' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_expired', 'detail', 'authorization expired', 'steps', v_steps);
  END IF;
  IF v_auth.provider_id <> v_provider.id
     OR v_auth.model_candidate_id <> v_model.id
     OR v_auth.benchmark_case_id <> p_benchmark_case_id THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'provider/model/case mismatch', 'steps', v_steps);
  END IF;
  IF v_auth.activated_at IS NOT NULL AND v_auth.expires_at > v_auth.activated_at + INTERVAL '24 hours' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'validity window exceeds 24h', 'steps', v_steps);
  END IF;

  -- Pilot proposal linkage (authoritative when present; fail closed if incomplete)
  IF v_auth.pilot_proposal_id IS NOT NULL THEN
    v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', '5b', 'name', 'pilot_proposal_bounds'));
    SELECT * INTO v_pilot FROM research.provider_pilot_proposals WHERE id = v_auth.pilot_proposal_id;
    IF NOT FOUND THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'pilot proposal missing', 'steps', v_steps);
    END IF;
    IF v_pilot.status <> 'approved' THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'pilot proposal not approved', 'steps', v_steps);
    END IF;
    IF v_pilot.expires_at IS NULL OR v_pilot.expires_at <= NOW() THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_expired', 'detail', 'pilot proposal expired', 'steps', v_steps);
    END IF;
    IF v_pilot.provider_id <> v_provider.id OR v_pilot.model_candidate_id <> v_model.id THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'pilot provider/model mismatch', 'steps', v_steps);
    END IF;
    IF NOT (p_benchmark_case_id = ANY (v_pilot.benchmark_case_ids)) THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'case not in pilot proposal', 'steps', v_steps);
    END IF;
    IF v_pilot.pilot_code = 'GEMINI-PILOT-5A' AND p_role_code <> 'researcher' THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'gemini pilot allows researcher role only', 'steps', v_steps);
    END IF;
    IF v_pilot.retries_allowed OR COALESCE(p_is_retry, FALSE) THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'retries disabled', 'steps', v_steps);
    END IF;
    IF v_pilot.fallback_provider_allowed OR (p_fallback_provider IS NOT NULL AND length(trim(p_fallback_provider)) > 0) THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'fallback provider disabled', 'steps', v_steps);
    END IF;
    IF v_pilot.max_authorized_cost_usd <> 0 OR v_auth.max_cost_usd <> 0 THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'pilot cost must be USD 0.00', 'steps', v_steps);
    END IF;
    IF p_confidentiality_class IS DISTINCT FROM 'public_or_synthetic' THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'confidentiality_blocked', 'detail', 'pilot allows public_or_synthetic only', 'steps', v_steps);
    END IF;

    SELECT COALESCE(SUM(l.request_count), 0),
           COALESCE(SUM(l.request_count) FILTER (WHERE l.success), 0),
           COALESCE(SUM(l.input_tokens), 0),
           COALESCE(SUM(l.output_tokens), 0)
      INTO v_pilot_req, v_pilot_success, v_pilot_in, v_pilot_out
    FROM research.provider_usage_ledger l
    WHERE l.pilot_proposal_id = v_pilot.id;

    IF v_pilot_req IS NULL OR v_pilot_success IS NULL OR v_pilot_in IS NULL OR v_pilot_out IS NULL THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'pilot usage counters unavailable', 'steps', v_steps);
    END IF;

    IF v_pilot_req >= v_pilot.max_total_requests THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_total_requests reached', 'steps', v_steps);
    END IF;
    IF v_pilot_success >= v_pilot.max_successful_calls THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_successful_calls reached', 'steps', v_steps);
    END IF;
    IF v_pilot_in + COALESCE(p_projected_input_tokens, 0) > v_pilot.max_total_input_tokens THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'pilot max_total_input_tokens exceeded', 'steps', v_steps);
    END IF;
    IF v_pilot_out + COALESCE(p_projected_output_tokens, 0) > v_pilot.max_total_output_tokens THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'pilot max_total_output_tokens exceeded', 'steps', v_steps);
    END IF;

    SELECT COALESCE(SUM(l.request_count), 0) INTO v_case_attempts
    FROM research.provider_usage_ledger l
    WHERE l.pilot_proposal_id = v_pilot.id
      AND l.benchmark_case_id = p_benchmark_case_id;
    IF v_case_attempts >= v_pilot.max_attempts_per_case THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_attempts_per_case reached', 'steps', v_steps);
    END IF;
  END IF;

  SELECT * INTO v_budget FROM research.provider_budget_policies WHERE provider_id = v_provider.id;
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 6, 'name', 'free_or_paid_policy'));
  IF v_budget.paid_fallback THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'paid_fallback forbidden', 'steps', v_steps);
  END IF;
  IF v_budget.free_only AND v_model.free_tier_status <> 'free_confirmed' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'free_tier_unverified', 'detail', 'free tier not confirmed', 'steps', v_steps);
  END IF;
  IF (NOT v_budget.free_only) AND NOT v_budget.paid_usage_authorized THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'paid not authorized', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 7, 'name', 'daily_request_allowance'));
  SELECT COALESCE(SUM(request_count),0) INTO v_day_req
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id AND created_at::date = CURRENT_DATE;
  IF v_day_req >= v_budget.daily_request_cap OR v_auth.requests_spent >= v_auth.max_requests THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'request quota exhausted', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 8, 'name', 'daily_token_allowance'));
  SELECT COALESCE(SUM(input_tokens + output_tokens),0) INTO v_day_tok
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id AND created_at::date = CURRENT_DATE;
  IF v_day_tok >= v_budget.daily_token_cap OR v_auth.tokens_spent >= v_auth.max_tokens THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'token quota exhausted', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 9, 'name', 'cost_allowance'));
  SELECT COALESCE(SUM(estimated_cost_usd),0) INTO v_month_cost
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id
    AND date_trunc('month', created_at) = date_trunc('month', NOW());
  IF v_month_cost > v_budget.monthly_cost_ceiling_usd
     OR (v_budget.monthly_cost_ceiling_usd = 0 AND v_month_cost > 0) THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'monthly cost ceiling exhausted', 'steps', v_steps);
  END IF;
  IF v_auth.cost_spent_usd > v_auth.max_cost_usd
     OR (v_auth.max_cost_usd = 0 AND v_auth.cost_spent_usd > 0) THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'authorization cost exhausted', 'steps', v_steps);
  END IF;
  IF v_budget.daily_cost_limit_usd = 0 AND v_auth.max_cost_usd > 0 AND NOT v_budget.paid_usage_authorized THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'paid cost not allowed under daily_cost_limit_usd=0', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 10, 'name', 'confidentiality'));
  IF p_confidentiality_class IN ('internal_lab','restricted') AND p_provider_code <> 'ollama' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'confidentiality_blocked', 'detail', 'remote providers blocked for confidential input', 'steps', v_steps);
  END IF;

  SELECT * INTO v_adapter FROM research.provider_adapter_versions
  WHERE provider_id = v_provider.id
  ORDER BY created_at DESC LIMIT 1;
  IF v_adapter.live_execution_enabled THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'live execution must remain false', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 11, 'name', 'construct_envelope_allowed'));
  RETURN jsonb_build_object(
    'ok', true,
    'failure_class', NULL,
    'detail', 'preflight passed; envelope may be constructed but not executed',
    'steps', v_steps,
    'provider_id', v_provider.id,
    'model_candidate_id', v_model.id,
    'authorization_id', v_auth.id,
    'pilot_proposal_id', v_auth.pilot_proposal_id
  );
END;
$$;

CREATE OR REPLACE FUNCTION research.build_provider_request_envelope(
  p_provider_code TEXT,
  p_model_provisional TEXT,
  p_benchmark_case_id UUID,
  p_authorization_id UUID,
  p_role_code TEXT,
  p_confidentiality_class TEXT,
  p_canonical_request JSONB,
  p_claimed_credential_status TEXT DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
  v_pf JSONB;
  v_env JSONB;
  v_provider_id UUID;
  v_eid UUID;
  v_in INT := COALESCE((p_canonical_request->>'projected_input_tokens')::int, 0);
  v_out INT := COALESCE((p_canonical_request->>'projected_output_tokens')::int, 0);
  v_retry BOOLEAN := COALESCE((p_canonical_request->>'is_retry')::boolean, FALSE);
  v_fallback TEXT := NULLIF(p_canonical_request->>'fallback_provider', '');
BEGIN
  v_pf := research.live_preflight(
    p_provider_code, p_model_provisional, p_benchmark_case_id, p_authorization_id,
    p_role_code, p_confidentiality_class, p_claimed_credential_status,
    v_in, v_out, v_retry, v_fallback
  );
  IF NOT COALESCE((v_pf->>'ok')::boolean, false) THEN
    RETURN jsonb_build_object(
      'ok', false,
      'failure_class', v_pf->>'failure_class',
      'detail', v_pf->>'detail',
      'steps', v_pf->'steps',
      'envelope', NULL
    );
  END IF;

  v_provider_id := (v_pf->>'provider_id')::uuid;

  v_env := jsonb_build_object(
    'provider', p_provider_code,
    'model', p_model_provisional,
    'adapter_version', 'r4-disabled-v1',
    'live_execution_allowed', false,
    'http_method', 'POST',
    'path', CASE p_provider_code
      WHEN 'gemini' THEN '/v1beta/models/' || p_model_provisional || ':generateContent'
      WHEN 'groq' THEN '/openai/v1/chat/completions'
      WHEN 'openrouter' THEN '/api/v1/chat/completions'
      WHEN 'ollama' THEN '/api/chat'
      ELSE '/forbidden'
    END,
    'headers', jsonb_build_object(
      'content-type', 'application/json',
      'authorization', '{{n8n_credential_injection_point_only}}'
    ),
    'body', CASE p_provider_code
      WHEN 'gemini' THEN jsonb_build_object(
        'contents', jsonb_build_array(jsonb_build_object('parts', jsonb_build_array(jsonb_build_object('text', p_canonical_request->>'prompt'))))
      )
      WHEN 'ollama' THEN jsonb_build_object(
        'model', p_model_provisional,
        'messages', jsonb_build_array(jsonb_build_object('role','user','content', p_canonical_request->>'prompt')),
        'stream', false
      )
      ELSE jsonb_build_object(
        'model', p_model_provisional,
        'messages', jsonb_build_array(jsonb_build_object('role','user','content', p_canonical_request->>'prompt'))
      )
    END,
    'canonical_input_fingerprint', p_canonical_request->>'input_fingerprint',
    'authorization_id', p_authorization_id,
    'benchmark_case_id', p_benchmark_case_id,
    'role', p_role_code,
    'pilot_proposal_id', v_pf->>'pilot_proposal_id',
    'note', 'Non-executable envelope; live_execution_allowed=false'
  );

  INSERT INTO research.live_request_envelopes (provider_id, authorization_id, envelope, executable)
  VALUES (v_provider_id, p_authorization_id, v_env, FALSE)
  RETURNING id INTO v_eid;

  RETURN jsonb_build_object('ok', true, 'failure_class', NULL, 'envelope_id', v_eid, 'envelope', v_env);
END;
$$;

-- Keep Gemini disabled after repair
UPDATE research.providers SET enabled = FALSE, updated_at = NOW() WHERE code = 'gemini';
UPDATE research.provider_model_candidates m
SET enabled = FALSE, updated_at = NOW()
FROM research.providers p
WHERE m.provider_id = p.id AND p.code = 'gemini';

-- Allow deterministic cleanup of test-fixture usage rows only
DROP TRIGGER IF EXISTS provider_usage_ledger_no_mutation ON research.provider_usage_ledger;
DROP TRIGGER IF EXISTS provider_usage_ledger_immutability ON research.provider_usage_ledger;
CREATE OR REPLACE FUNCTION research.trg_usage_ledger_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.test_fixture_id IS NULL THEN
      RAISE EXCEPTION 'provider_usage_ledger production rows cannot be deleted';
    END IF;
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'provider_usage_ledger rows are immutable';
END;
$$;
CREATE TRIGGER provider_usage_ledger_immutability
  BEFORE UPDATE OR DELETE ON research.provider_usage_ledger
  FOR EACH ROW EXECUTE FUNCTION research.trg_usage_ledger_immutability();

CREATE OR REPLACE FUNCTION research.record_authorization_spend(
  p_authorization_id UUID,
  p_requests INT,
  p_tokens INT,
  p_cost NUMERIC,
  p_note TEXT DEFAULT 'round4_simulated_spend'
) RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
  v_auth research.provider_authorization_records%ROWTYPE;
BEGIN
  SELECT * INTO v_auth FROM research.provider_authorization_records WHERE id = p_authorization_id FOR UPDATE;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_missing');
  END IF;
  IF v_auth.requests_spent + p_requests > v_auth.max_requests THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'authorization request overspend blocked');
  END IF;
  IF v_auth.tokens_spent + p_tokens > v_auth.max_tokens THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted');
  END IF;
  IF v_auth.cost_spent_usd + p_cost > v_auth.max_cost_usd THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted');
  END IF;

  UPDATE research.provider_authorization_records
  SET requests_spent = requests_spent + p_requests,
      tokens_spent = tokens_spent + p_tokens,
      cost_spent_usd = cost_spent_usd + p_cost,
      status = CASE
        WHEN requests_spent + p_requests >= max_requests THEN 'exhausted'
        ELSE status
      END
  WHERE id = p_authorization_id;

  INSERT INTO research.provider_usage_ledger (
    provider_id, model_candidate_id, authorization_id, benchmark_case_id,
    request_count, input_tokens, output_tokens, estimated_cost_usd, live_executed, note,
    pilot_proposal_id, success, is_retry
  ) VALUES (
    v_auth.provider_id, v_auth.model_candidate_id, v_auth.id, v_auth.benchmark_case_id,
    p_requests, GREATEST(p_tokens, 0), 0, p_cost, FALSE, p_note,
    v_auth.pilot_proposal_id, FALSE, FALSE
  );

  RETURN jsonb_build_object('ok', true);
END;
$$;

CREATE OR REPLACE FUNCTION research.record_pilot_usage_for_tests(
  p_authorization_id UUID,
  p_input_tokens INT,
  p_output_tokens INT,
  p_success BOOLEAN,
  p_fixture_id TEXT,
  p_is_retry BOOLEAN DEFAULT FALSE
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_auth research.provider_authorization_records%ROWTYPE;
  v_id UUID;
BEGIN
  IF p_fixture_id IS NULL OR length(trim(p_fixture_id)) = 0 THEN
    RAISE EXCEPTION 'test fixture id required';
  END IF;
  SELECT * INTO v_auth FROM research.provider_authorization_records WHERE id = p_authorization_id;
  INSERT INTO research.provider_usage_ledger (
    provider_id, model_candidate_id, authorization_id, benchmark_case_id,
    request_count, input_tokens, output_tokens, estimated_cost_usd, live_executed, note,
    pilot_proposal_id, success, is_retry, test_fixture_id
  ) VALUES (
    v_auth.provider_id, v_auth.model_candidate_id, v_auth.id, v_auth.benchmark_case_id,
    1, p_input_tokens, p_output_tokens, 0, FALSE, 'test_fixture_usage',
    v_auth.pilot_proposal_id, p_success, p_is_retry, p_fixture_id
  ) RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION research.cleanup_test_fixture(p_fixture_id TEXT)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  DELETE FROM research.provider_usage_ledger WHERE test_fixture_id = p_fixture_id;
  UPDATE research.provider_authorization_records
  SET status = 'revoked'
  WHERE test_fixture_id = p_fixture_id AND status IN ('active','proposed','exhausted');
END;
$$;

INSERT INTO research.schema_version (version, note) VALUES
  (7, 'Round 5A repair: 24h approval expiry + aggregate pilot preflight + residue revoke')
ON CONFLICT (version) DO NOTHING;

COMMIT;
