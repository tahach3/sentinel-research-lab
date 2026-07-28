-- Round 5A final repair: immutable pilot activation + atomic capacity reservation
-- Restart-safe / idempotent via IF NOT EXISTS, CREATE OR REPLACE, ON CONFLICT DO NOTHING.
BEGIN;

-- ---------------------------------------------------------------------------
-- Dedicated reservation ledger (durable pending capacity under pilot bounds)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.pilot_capacity_reservations (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pilot_proposal_id         UUID NOT NULL REFERENCES research.provider_pilot_proposals(id) ON DELETE RESTRICT,
  authorization_id          UUID NOT NULL REFERENCES research.provider_authorization_records(id) ON DELETE RESTRICT,
  benchmark_case_id         UUID NOT NULL REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT,
  idempotency_key           TEXT NOT NULL,
  projected_input_tokens    INTEGER NOT NULL CHECK (projected_input_tokens >= 0),
  projected_output_tokens   INTEGER NOT NULL CHECK (projected_output_tokens >= 0),
  projected_cost_usd        NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (projected_cost_usd >= 0),
  envelope_id               UUID REFERENCES research.live_request_envelopes(id) ON DELETE RESTRICT,
  status                    TEXT NOT NULL DEFAULT 'reserved'
    CHECK (status IN ('reserved', 'finalized', 'released')),
  test_fixture_id           TEXT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pcr_zero_cost CHECK (projected_cost_usd = 0),
  CONSTRAINT pcr_idempotency_unique UNIQUE (pilot_proposal_id, idempotency_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pilot_capacity_one_attempt_per_case
  ON research.pilot_capacity_reservations (pilot_proposal_id, benchmark_case_id)
  WHERE status IN ('reserved', 'finalized');

CREATE INDEX IF NOT EXISTS idx_pilot_capacity_reservations_pilot
  ON research.pilot_capacity_reservations (pilot_proposal_id)
  WHERE status IN ('reserved', 'finalized');

COMMENT ON TABLE research.pilot_capacity_reservations IS
  'Atomic pending capacity for Gemini pilot envelopes; counts toward request/attempt/token bounds until released.';

-- ---------------------------------------------------------------------------
-- Immutable activation + governed-only pilot activation trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION research.trg_authorization_validity_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  -- Pilot-linked rows may enter 'active' only via governed activation GUC
  IF NEW.pilot_proposal_id IS NOT NULL
     AND NEW.status = 'active'
     AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'active') THEN
    IF current_setting('research.allow_pilot_activation', true) IS DISTINCT FROM 'on' THEN
      RAISE EXCEPTION
        'pilot-linked authorization activation requires research.activate_pilot_authorization';
    END IF;
  END IF;

  -- Once activated_at is assigned, neither timestamp may move, reset, clear, or extend
  IF TG_OP = 'UPDATE' AND OLD.activated_at IS NOT NULL THEN
    IF NEW.activated_at IS DISTINCT FROM OLD.activated_at THEN
      RAISE EXCEPTION 'activated_at is immutable after first activation';
    END IF;
    IF NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
      RAISE EXCEPTION 'expires_at is immutable after first activation';
    END IF;
  END IF;

  IF TG_OP = 'UPDATE' AND NEW.pilot_proposal_id IS NOT NULL THEN
    -- Reject active → proposed renewal path
    IF OLD.status = 'active' AND NEW.status = 'proposed' THEN
      RAISE EXCEPTION 'pilot-linked authorization cannot return to proposed after activation';
    END IF;
    -- Reject in-place renewal of terminal statuses
    IF OLD.status IN ('expired', 'exhausted', 'revoked') AND NEW.status = 'active' THEN
      RAISE EXCEPTION 'expired/exhausted/revoked pilot authorization cannot be renewed in place';
    END IF;
    -- Reject reactivation when activated_at already set (e.g. proposed with sticky stamp)
    IF NEW.status = 'active'
       AND OLD.status IS DISTINCT FROM 'active'
       AND OLD.activated_at IS NOT NULL THEN
      RAISE EXCEPTION 'pilot authorization already activated; renewal requires a new authorization record';
    END IF;
  END IF;

  IF NEW.status = 'proposed' THEN
    IF NEW.activated_at IS NOT NULL THEN
      RAISE EXCEPTION 'proposed authorization cannot retain activated_at';
    END IF;
    NEW.expires_at := TIMESTAMPTZ '-infinity';
  END IF;

  IF NEW.status = 'active' THEN
    IF TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'active' THEN
      IF TG_OP = 'UPDATE' AND OLD.activated_at IS NOT NULL THEN
        RAISE EXCEPTION 'cannot reactivate; activated_at already set';
      END IF;
      -- Assign exactly once on first governed activation
      NEW.activated_at := COALESCE(NEW.activated_at, NOW());
      NEW.expires_at := NEW.activated_at + INTERVAL '24 hours';
    END IF;

    IF NEW.activated_at IS NULL THEN
      RAISE EXCEPTION 'active authorization requires activated_at';
    END IF;

    IF NEW.expires_at IS DISTINCT FROM (NEW.activated_at + INTERVAL '24 hours') THEN
      RAISE EXCEPTION 'expires_at must equal activated_at + 24 hours';
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
  BEFORE INSERT OR UPDATE OF status, expires_at, activated_at, approving_authority, pilot_proposal_id
  ON research.provider_authorization_records
  FOR EACH ROW EXECUTE FUNCTION research.trg_authorization_validity_guard();

-- ---------------------------------------------------------------------------
-- Governed activation: approved pilot + confirmed credential; no proposal mutation
-- ---------------------------------------------------------------------------
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
  v_cred research.provider_credential_status%ROWTYPE;
  v_now TIMESTAMPTZ := NOW();
  v_pilot_status_before TEXT;
BEGIN
  SELECT * INTO v_auth FROM research.provider_authorization_records WHERE id = p_authorization_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'authorization % not found', p_authorization_id;
  END IF;
  IF v_auth.status <> 'proposed' THEN
    RAISE EXCEPTION 'only proposed authorizations can be activated (got %)', v_auth.status;
  END IF;
  IF v_auth.activated_at IS NOT NULL THEN
    RAISE EXCEPTION 'authorization already has activated_at; renewal requires a new record';
  END IF;
  IF v_auth.pilot_proposal_id IS NULL THEN
    RAISE EXCEPTION 'authorization is not linked to a pilot proposal';
  END IF;
  IF v_auth.approving_authority IS DISTINCT FROM 'Taha' THEN
    RAISE EXCEPTION 'authority must be Taha';
  END IF;

  SELECT * INTO v_pilot FROM research.provider_pilot_proposals WHERE id = v_auth.pilot_proposal_id FOR UPDATE;
  IF v_pilot.pilot_code IS DISTINCT FROM p_pilot_code THEN
    RAISE EXCEPTION 'pilot mismatch: expected %, got %', p_pilot_code, v_pilot.pilot_code;
  END IF;

  v_pilot_status_before := v_pilot.status;
  IF v_pilot.status IS DISTINCT FROM 'approved' THEN
    RAISE EXCEPTION 'pilot proposal must already be approved before activation (got %)', v_pilot.status;
  END IF;

  SELECT * INTO v_provider FROM research.providers WHERE id = v_auth.provider_id;
  SELECT * INTO v_model FROM research.provider_model_candidates WHERE id = v_auth.model_candidate_id;
  IF v_provider.code <> 'gemini' OR v_model.model_id_provisional <> 'gemini-2.5-flash' THEN
    RAISE EXCEPTION 'activation limited to gemini / gemini-2.5-flash';
  END IF;
  IF NOT (v_auth.benchmark_case_id = ANY (v_pilot.benchmark_case_ids)) THEN
    RAISE EXCEPTION 'authorization case not in pilot proposal';
  END IF;
  IF v_pilot.provider_id <> v_auth.provider_id OR v_pilot.model_candidate_id <> v_auth.model_candidate_id THEN
    RAISE EXCEPTION 'authorization provider/model must match pilot proposal';
  END IF;

  SELECT * INTO v_cred FROM research.provider_credential_status WHERE provider_id = v_auth.provider_id;
  IF NOT FOUND OR v_cred.status IS DISTINCT FROM 'present' THEN
    RAISE EXCEPTION 'expected Gemini credential-status record must confirm credential is present';
  END IF;

  -- Never mutate proposal approval state (including awaiting_taha_credential)
  PERFORM set_config('research.allow_pilot_activation', 'on', true);

  UPDATE research.provider_authorization_records
  SET status = 'active',
      activated_at = v_now,
      expires_at = v_now + INTERVAL '24 hours'
  WHERE id = p_authorization_id
  RETURNING * INTO v_auth;

  -- Clear immediately so later direct UPDATEs in the same transaction fail closed
  PERFORM set_config('research.allow_pilot_activation', 'off', true);

  IF (SELECT status FROM research.provider_pilot_proposals WHERE id = v_pilot.id) IS DISTINCT FROM v_pilot_status_before THEN
    RAISE EXCEPTION 'activation must not modify pilot proposal status';
  END IF;

  RETURN v_auth;
END;
$$;

-- ---------------------------------------------------------------------------
-- Pilot capacity counters (finalized ledger + durable reservations)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION research.pilot_capacity_snapshot(p_pilot_id UUID)
RETURNS TABLE (
  total_requests BIGINT,
  successful_calls BIGINT,
  input_tokens BIGINT,
  output_tokens BIGINT
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_req BIGINT;
  v_success BIGINT;
  v_in BIGINT;
  v_out BIGINT;
  v_r_req BIGINT;
  v_r_in BIGINT;
  v_r_out BIGINT;
BEGIN
  SELECT COALESCE(SUM(l.request_count), 0),
         COALESCE(SUM(l.request_count) FILTER (WHERE l.success), 0),
         COALESCE(SUM(l.input_tokens), 0),
         COALESCE(SUM(l.output_tokens), 0)
    INTO v_req, v_success, v_in, v_out
  FROM research.provider_usage_ledger l
  WHERE l.pilot_proposal_id = p_pilot_id;

  SELECT COUNT(*),
         COALESCE(SUM(r.projected_input_tokens), 0),
         COALESCE(SUM(r.projected_output_tokens), 0)
    INTO v_r_req, v_r_in, v_r_out
  FROM research.pilot_capacity_reservations r
  WHERE r.pilot_proposal_id = p_pilot_id
    AND r.status IN ('reserved', 'finalized');

  IF v_req IS NULL OR v_success IS NULL OR v_in IS NULL OR v_out IS NULL
     OR v_r_req IS NULL OR v_r_in IS NULL OR v_r_out IS NULL THEN
    RAISE EXCEPTION 'pilot usage counters unavailable';
  END IF;

  total_requests := v_req + v_r_req;
  successful_calls := v_success; -- finalized usage only
  input_tokens := v_in + v_r_in;
  output_tokens := v_out + v_r_out;
  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION research.pilot_case_attempt_count(
  p_pilot_id UUID,
  p_benchmark_case_id UUID
) RETURNS BIGINT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_ledger BIGINT;
  v_res BIGINT;
BEGIN
  SELECT COALESCE(SUM(l.request_count), 0) INTO v_ledger
  FROM research.provider_usage_ledger l
  WHERE l.pilot_proposal_id = p_pilot_id
    AND l.benchmark_case_id = p_benchmark_case_id;

  SELECT COUNT(*) INTO v_res
  FROM research.pilot_capacity_reservations r
  WHERE r.pilot_proposal_id = p_pilot_id
    AND r.benchmark_case_id = p_benchmark_case_id
    AND r.status IN ('reserved', 'finalized');

  IF v_ledger IS NULL OR v_res IS NULL THEN
    RAISE EXCEPTION 'pilot case attempt counters unavailable';
  END IF;
  RETURN v_ledger + v_res;
END;
$$;

-- ---------------------------------------------------------------------------
-- live_preflight: include reservations; VOLATILE (may be used under locks)
-- ---------------------------------------------------------------------------
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
VOLATILE
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
  v_cap RECORD;
  v_case_attempts BIGINT;
  v_proj_in INT;
  v_proj_out INT;
BEGIN
  BEGIN
    v_proj_in := COALESCE(p_projected_input_tokens, 0);
    v_proj_out := COALESCE(p_projected_output_tokens, 0);
  EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'malformed projected tokens', 'steps', v_steps);
  END;

  IF v_proj_in < 0 OR v_proj_out < 0 THEN
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
  IF v_auth.activated_at IS NULL
     OR v_auth.expires_at IS DISTINCT FROM (v_auth.activated_at + INTERVAL '24 hours') THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'invalid immutable validity window', 'steps', v_steps);
  END IF;

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

    SELECT * INTO v_cap FROM research.pilot_capacity_snapshot(v_pilot.id);
    IF v_cap.total_requests >= v_pilot.max_total_requests THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_total_requests reached', 'steps', v_steps);
    END IF;
    IF v_cap.successful_calls >= v_pilot.max_successful_calls THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_successful_calls reached', 'steps', v_steps);
    END IF;
    IF v_cap.input_tokens + v_proj_in > v_pilot.max_total_input_tokens THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'pilot max_total_input_tokens exceeded', 'steps', v_steps);
    END IF;
    IF v_cap.output_tokens + v_proj_out > v_pilot.max_total_output_tokens THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'pilot max_total_output_tokens exceeded', 'steps', v_steps);
    END IF;

    v_case_attempts := research.pilot_case_attempt_count(v_pilot.id, p_benchmark_case_id);
    IF v_case_attempts >= v_pilot.max_attempts_per_case THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_attempts_per_case reached', 'steps', v_steps);
    END IF;
  END IF;

  SELECT * INTO v_budget FROM research.provider_budget_policies WHERE provider_id = v_provider.id;
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 6, 'name', 'free_or_paid_policy'));
  IF v_budget.paid_fallback THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'paid_usage_blocked', 'detail', 'paid fallback forbidden', 'steps', v_steps);
  END IF;
  IF v_budget.paid_usage_authorized THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'paid_usage_blocked', 'detail', 'paid usage not authorized', 'steps', v_steps);
  END IF;
  IF NOT v_budget.free_only THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'paid_usage_blocked', 'detail', 'free_only required', 'steps', v_steps);
  END IF;
  IF v_budget.daily_cost_limit_usd <> 0 OR v_budget.monthly_cost_ceiling_usd <> 0 THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'non-zero cost ceilings forbidden', 'steps', v_steps);
  END IF;

  SELECT COALESCE(SUM(request_count), 0) INTO v_day_req
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id AND created_at >= date_trunc('day', NOW());
  IF v_day_req >= v_budget.daily_request_cap THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'daily request cap', 'steps', v_steps);
  END IF;

  SELECT COALESCE(SUM(input_tokens + output_tokens), 0) INTO v_day_tok
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id AND created_at >= date_trunc('day', NOW());
  IF v_day_tok >= v_budget.daily_token_cap THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'daily token cap', 'steps', v_steps);
  END IF;

  SELECT COALESCE(SUM(estimated_cost_usd), 0) INTO v_month_cost
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id AND created_at >= date_trunc('month', NOW());
  IF v_month_cost > 0 THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'any recorded cost blocked', 'steps', v_steps);
  END IF;

  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 7, 'name', 'authorization_spend_bounds'));
  IF v_auth.requests_spent >= v_auth.max_requests THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'authorization requests exhausted', 'steps', v_steps);
  END IF;
  IF v_auth.tokens_spent >= v_auth.max_tokens THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'authorization tokens exhausted', 'steps', v_steps);
  END IF;
  IF v_auth.cost_spent_usd > 0 OR v_auth.max_cost_usd <> 0 THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'authorization cost must remain USD 0.00', 'steps', v_steps);
  END IF;

  SELECT * INTO v_adapter FROM research.provider_adapter_versions
  WHERE provider_id = v_provider.id
  ORDER BY created_at DESC
  LIMIT 1;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'adapter missing', 'steps', v_steps);
  END IF;

  RETURN jsonb_build_object(
    'ok', true,
    'failure_class', NULL,
    'detail', NULL,
    'steps', v_steps,
    'provider_id', v_provider.id,
    'model_candidate_id', v_model.id,
    'authorization_id', v_auth.id,
    'pilot_proposal_id', v_auth.pilot_proposal_id
  );
END;
$$;

-- ---------------------------------------------------------------------------
-- Atomic envelope builder with reservation (pilot path)
-- ---------------------------------------------------------------------------
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
  v_rid UUID;
  v_in INT;
  v_out INT;
  v_cost NUMERIC;
  v_retry BOOLEAN;
  v_fallback TEXT;
  v_idem TEXT;
  v_auth research.provider_authorization_records%ROWTYPE;
  v_pilot research.provider_pilot_proposals%ROWTYPE;
  v_cap RECORD;
  v_case_attempts BIGINT;
  v_existing research.pilot_capacity_reservations%ROWTYPE;
  v_fixture TEXT;
BEGIN
  -- Fail closed on malformed projections
  BEGIN
    IF p_canonical_request ? 'projected_input_tokens'
       AND jsonb_typeof(p_canonical_request->'projected_input_tokens') NOT IN ('number', 'null') THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'malformed projected_input_tokens', 'envelope', NULL);
    END IF;
    IF p_canonical_request ? 'projected_output_tokens'
       AND jsonb_typeof(p_canonical_request->'projected_output_tokens') NOT IN ('number', 'null') THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'malformed projected_output_tokens', 'envelope', NULL);
    END IF;
    v_in := COALESCE((p_canonical_request->>'projected_input_tokens')::int, 0);
    v_out := COALESCE((p_canonical_request->>'projected_output_tokens')::int, 0);
    v_cost := COALESCE((p_canonical_request->>'projected_cost_usd')::numeric, 0);
    v_retry := COALESCE((p_canonical_request->>'is_retry')::boolean, FALSE);
    v_fallback := NULLIF(p_canonical_request->>'fallback_provider', '');
  EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'malformed canonical request projections', 'envelope', NULL);
  END;

  IF v_in < 0 OR v_out < 0 THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'negative projected tokens', 'envelope', NULL);
  END IF;
  IF v_cost IS NULL OR v_cost <> 0 THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'any cost above USD 0.00 is blocked', 'envelope', NULL);
  END IF;

  SELECT * INTO v_auth FROM research.provider_authorization_records WHERE id = p_authorization_id;
  IF FOUND AND v_auth.pilot_proposal_id IS NOT NULL THEN
    v_idem := NULLIF(trim(COALESCE(p_canonical_request->>'idempotency_key', '')), '');
    IF v_idem IS NULL THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'idempotency_key required for pilot envelopes', 'envelope', NULL);
    END IF;
  END IF;

  -- Transaction-scoped locks before mutable counter evaluation (pilot path)
  IF FOUND AND v_auth.pilot_proposal_id IS NOT NULL THEN
    SELECT * INTO v_pilot FROM research.provider_pilot_proposals
    WHERE id = v_auth.pilot_proposal_id FOR UPDATE;
    SELECT * INTO v_auth FROM research.provider_authorization_records
    WHERE id = p_authorization_id FOR UPDATE;

    SELECT * INTO v_existing
    FROM research.pilot_capacity_reservations
    WHERE pilot_proposal_id = v_pilot.id
      AND idempotency_key = v_idem
    FOR UPDATE;

    IF FOUND THEN
      IF v_existing.envelope_id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'incomplete reservation for idempotency key', 'envelope', NULL);
      END IF;
      SELECT envelope INTO v_env FROM research.live_request_envelopes WHERE id = v_existing.envelope_id;
      RETURN jsonb_build_object(
        'ok', true,
        'failure_class', NULL,
        'envelope_id', v_existing.envelope_id,
        'envelope', v_env,
        'idempotent_replay', true,
        'reservation_id', v_existing.id
      );
    END IF;
  END IF;

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
    'idempotency_key', v_idem,
    'note', 'Non-executable envelope; live_execution_allowed=false'
  );

  -- Pilot path: reserve then insert envelope atomically in this function/transaction
  IF v_auth.pilot_proposal_id IS NOT NULL THEN
    -- Re-check capacity under locks (includes reservations)
    SELECT * INTO v_cap FROM research.pilot_capacity_snapshot(v_pilot.id);
    IF v_cap.total_requests >= v_pilot.max_total_requests THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_total_requests reached', 'envelope', NULL);
    END IF;
    IF v_cap.successful_calls >= v_pilot.max_successful_calls THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_successful_calls reached', 'envelope', NULL);
    END IF;
    IF v_cap.input_tokens + v_in > v_pilot.max_total_input_tokens THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'pilot max_total_input_tokens exceeded', 'envelope', NULL);
    END IF;
    IF v_cap.output_tokens + v_out > v_pilot.max_total_output_tokens THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'pilot max_total_output_tokens exceeded', 'envelope', NULL);
    END IF;
    v_case_attempts := research.pilot_case_attempt_count(v_pilot.id, p_benchmark_case_id);
    IF v_case_attempts >= v_pilot.max_attempts_per_case THEN
      RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'pilot max_attempts_per_case reached', 'envelope', NULL);
    END IF;

    v_fixture := v_auth.test_fixture_id;

    INSERT INTO research.pilot_capacity_reservations (
      pilot_proposal_id, authorization_id, benchmark_case_id, idempotency_key,
      projected_input_tokens, projected_output_tokens, projected_cost_usd,
      status, test_fixture_id
    ) VALUES (
      v_pilot.id, p_authorization_id, p_benchmark_case_id, v_idem,
      v_in, v_out, 0,
      'reserved', v_fixture
    ) RETURNING id INTO v_rid;

    IF current_setting('research.simulate_envelope_insert_failure', true) = 'on' THEN
      RAISE EXCEPTION 'simulated envelope insert failure';
    END IF;

    INSERT INTO research.live_request_envelopes (provider_id, authorization_id, envelope, executable)
    VALUES (v_provider_id, p_authorization_id, v_env, FALSE)
    RETURNING id INTO v_eid;

    UPDATE research.pilot_capacity_reservations
    SET envelope_id = v_eid
    WHERE id = v_rid;

    RETURN jsonb_build_object(
      'ok', true,
      'failure_class', NULL,
      'envelope_id', v_eid,
      'envelope', v_env,
      'reservation_id', v_rid,
      'idempotent_replay', false
    );
  END IF;

  -- Non-pilot path (Round 4 gates): envelope only, no pilot reservation
  INSERT INTO research.live_request_envelopes (provider_id, authorization_id, envelope, executable)
  VALUES (v_provider_id, p_authorization_id, v_env, FALSE)
  RETURNING id INTO v_eid;

  RETURN jsonb_build_object('ok', true, 'failure_class', NULL, 'envelope_id', v_eid, 'envelope', v_env);
END;
$$;

-- ---------------------------------------------------------------------------
-- Fixture cleanup: reservations + envelopes linked to fixture auths
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS live_request_envelopes_no_mutation ON research.live_request_envelopes;
DROP TRIGGER IF EXISTS live_request_envelopes_immutability ON research.live_request_envelopes;
CREATE OR REPLACE FUNCTION research.trg_envelope_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF EXISTS (
      SELECT 1 FROM research.provider_authorization_records a
      WHERE a.id = OLD.authorization_id AND a.test_fixture_id IS NOT NULL
    ) THEN
      RETURN OLD;
    END IF;
    IF EXISTS (
      SELECT 1 FROM research.pilot_capacity_reservations r
      WHERE r.envelope_id = OLD.id AND r.test_fixture_id IS NOT NULL
    ) THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'live_request_envelopes production rows cannot be deleted';
  END IF;
  RAISE EXCEPTION 'live_request_envelopes rows are immutable';
END;
$$;
CREATE TRIGGER live_request_envelopes_immutability
  BEFORE UPDATE OR DELETE ON research.live_request_envelopes
  FOR EACH ROW EXECUTE FUNCTION research.trg_envelope_immutability();

CREATE OR REPLACE FUNCTION research.cleanup_test_fixture(p_fixture_id TEXT)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_fixture_id IS NULL OR length(trim(p_fixture_id)) = 0 THEN
    RAISE EXCEPTION 'fixture id required';
  END IF;

  -- Detach envelope FKs then delete fixture reservations
  UPDATE research.pilot_capacity_reservations
  SET envelope_id = NULL, status = 'released'
  WHERE test_fixture_id = p_fixture_id;

  DELETE FROM research.live_request_envelopes e
  USING research.provider_authorization_records a
  WHERE e.authorization_id = a.id AND a.test_fixture_id = p_fixture_id;

  DELETE FROM research.pilot_capacity_reservations WHERE test_fixture_id = p_fixture_id;
  DELETE FROM research.provider_usage_ledger WHERE test_fixture_id = p_fixture_id;

  UPDATE research.provider_authorization_records
  SET status = 'revoked'
  WHERE test_fixture_id = p_fixture_id AND status IN ('active', 'proposed', 'exhausted', 'expired');
END;
$$;

-- Keep Gemini disabled after repair
UPDATE research.providers SET enabled = FALSE, updated_at = NOW() WHERE code = 'gemini';
UPDATE research.provider_model_candidates m
SET enabled = FALSE, updated_at = NOW()
FROM research.providers p
WHERE m.provider_id = p.id AND p.code = 'gemini';

-- Revoke leftover non-pilot Round 4/5A active test residue (idempotent)
UPDATE research.provider_authorization_records a
SET status = 'revoked'
FROM research.providers p
WHERE a.provider_id = p.id
  AND p.code = 'gemini'
  AND a.pilot_proposal_id IS NULL
  AND a.test_fixture_id IS NULL
  AND a.status = 'active'
  AND a.max_tokens = 1000
  AND a.max_requests IN (1, 3);

-- Also revoke any orphan active fixture-marked gemini auths left by interrupted tests
UPDATE research.provider_authorization_records a
SET status = 'revoked'
FROM research.providers p
WHERE a.provider_id = p.id
  AND p.code = 'gemini'
  AND a.test_fixture_id IS NOT NULL
  AND a.status IN ('active', 'proposed', 'exhausted', 'expired');

-- Test helpers used by 008 regression + concurrent slot tests (no production side effects)
CREATE OR REPLACE FUNCTION research._r5a_final_reset_defaults()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  UPDATE research.providers SET enabled = FALSE WHERE code = 'gemini';
  UPDATE research.provider_model_candidates m
  SET enabled = FALSE
  FROM research.providers p
  WHERE m.provider_id = p.id AND p.code = 'gemini';
  UPDATE research.provider_credential_status c
  SET status = 'missing', n8n_credential_label = NULL
  FROM research.providers p
  WHERE c.provider_id = p.id AND p.code = 'gemini';
  UPDATE research.provider_budget_policies b
  SET daily_request_cap = 0, daily_token_cap = 0, free_only = TRUE,
      paid_fallback = FALSE, paid_usage_authorized = FALSE,
      daily_cost_limit_usd = 0, monthly_cost_ceiling_usd = 0
  FROM research.providers p
  WHERE b.provider_id = p.id AND p.code = 'gemini';
  UPDATE research.provider_pilot_proposals
  SET status = 'awaiting_taha_credential',
      taha_approved_at = NULL,
      expires_at = NULL,
      updated_at = NOW()
  WHERE pilot_code = 'GEMINI-PILOT-5A';
END;
$$;

CREATE OR REPLACE FUNCTION research._r5a_final_arm_gates()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE pid UUID;
BEGIN
  SELECT id INTO pid FROM research.providers WHERE code = 'gemini';
  UPDATE research.providers SET enabled = TRUE WHERE id = pid;
  UPDATE research.provider_model_candidates
  SET enabled = TRUE, verification_status = 'verified', free_tier_status = 'free_confirmed'
  WHERE provider_id = pid AND model_id_provisional = 'gemini-2.5-flash';
  UPDATE research.provider_credential_status
  SET status = 'present', n8n_credential_label = 'local-test-label-only'
  WHERE provider_id = pid;
  UPDATE research.provider_budget_policies
  SET daily_request_cap = 100, daily_token_cap = 100000
  WHERE provider_id = pid;
  UPDATE research.provider_pilot_proposals
  SET status = 'approved',
      taha_approved_at = COALESCE(taha_approved_at, NOW()),
      expires_at = NOW() + INTERVAL '24 hours',
      updated_at = NOW()
  WHERE pilot_code = 'GEMINI-PILOT-5A';
END;
$$;

CREATE OR REPLACE FUNCTION research._r5a_insert_fixture_auth(
  p_fixture TEXT,
  p_pilot UUID,
  p_case UUID,
  p_provider UUID,
  p_model UUID
) RETURNS UUID
LANGUAGE plpgsql AS $$
DECLARE aid UUID;
BEGIN
  INSERT INTO research.provider_authorization_records (
    provider_id, model_candidate_id, benchmark_case_id,
    max_requests, max_tokens, max_cost_usd, expires_at,
    approving_authority, status, pilot_proposal_id, test_fixture_id
  ) VALUES (
    p_provider, p_model, p_case,
    1, 4000, 0, TIMESTAMPTZ '-infinity',
    'Taha', 'proposed', p_pilot, p_fixture
  ) RETURNING id INTO aid;
  RETURN aid;
END;
$$;

INSERT INTO research.schema_version (version, note) VALUES
  (8, 'Round 5A final: immutable activation + atomic pilot capacity reservations')
ON CONFLICT (version) DO NOTHING;

COMMIT;
