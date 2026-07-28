-- Round 4: Live provider readiness + budget gates (disabled; zero external calls)
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Registry providers (disabled by default)
-- ---------------------------------------------------------------------------
INSERT INTO research.providers (code, display_name, enabled, notes) VALUES
  ('gemini', 'Google Gemini', FALSE, 'Round 4 registry only; disabled; no live calls'),
  ('groq', 'Groq', FALSE, 'Round 4 registry only; disabled; no live calls'),
  ('openrouter', 'OpenRouter', FALSE, 'Round 4 registry only; disabled; no live calls'),
  ('ollama', 'Ollama local', FALSE, 'Round 4 registry only; disabled; not installed; no pulls')
ON CONFLICT (code) DO NOTHING;

-- Live budget gate defaults (extends Round 1 policies; no secrets)
ALTER TABLE research.provider_budget_policies
  ADD COLUMN IF NOT EXISTS paid_fallback BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS daily_cost_limit_usd NUMERIC(12,6) NOT NULL DEFAULT 0
    CHECK (daily_cost_limit_usd >= 0);

-- Allow zero daily caps for hard-closed free-only posture in Round 4
ALTER TABLE research.provider_budget_policies
  DROP CONSTRAINT IF EXISTS provider_budget_caps_positive;
ALTER TABLE research.provider_budget_policies
  ADD CONSTRAINT provider_budget_caps_nonneg CHECK (
    daily_request_cap >= 0 AND daily_token_cap >= 0 AND monthly_cost_ceiling_usd >= 0
  );

INSERT INTO research.provider_budget_policies (
  provider_id, free_only, daily_request_cap, daily_token_cap,
  monthly_cost_ceiling_usd, paid_usage_authorized, paid_fallback, daily_cost_limit_usd
)
SELECT p.id, TRUE, 0, 0, 0, FALSE, FALSE, 0
FROM research.providers p
WHERE p.code IN ('gemini','groq','openrouter','ollama')
ON CONFLICT (provider_id) DO UPDATE SET
  free_only = EXCLUDED.free_only,
  paid_usage_authorized = FALSE,
  paid_fallback = FALSE,
  daily_cost_limit_usd = 0,
  monthly_cost_ceiling_usd = 0,
  daily_request_cap = 0,
  daily_token_cap = 0,
  updated_at = NOW();

-- ---------------------------------------------------------------------------
-- Capability / model / adapter / rate-limit / credential-status / auth / usage / health
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.provider_capabilities (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  capability_code   TEXT NOT NULL,
  claim_text        TEXT NOT NULL,
  claim_source      TEXT NOT NULL,
  verification_date DATE NOT NULL,
  verified          BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pc_unique UNIQUE (provider_id, capability_code),
  CONSTRAINT pc_code_nonempty CHECK (length(trim(capability_code)) > 0)
);

CREATE TABLE IF NOT EXISTS research.provider_model_candidates (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  model_id_provisional TEXT NOT NULL,
  display_name      TEXT NOT NULL,
  enabled           BOOLEAN NOT NULL DEFAULT FALSE,
  verification_status TEXT NOT NULL DEFAULT 'unverified',
  free_tier_status  TEXT NOT NULL DEFAULT 'unverified',
  max_requests_per_day INTEGER NOT NULL DEFAULT 0 CHECK (max_requests_per_day >= 0),
  max_tokens_per_day INTEGER NOT NULL DEFAULT 0 CHECK (max_tokens_per_day >= 0),
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pmc_unique UNIQUE (provider_id, model_id_provisional),
  CONSTRAINT pmc_verify_check CHECK (verification_status IN ('unverified','verified','rejected')),
  CONSTRAINT pmc_free_check CHECK (free_tier_status IN ('unverified','free_confirmed','paid_only','unknown'))
);

CREATE TABLE IF NOT EXISTS research.provider_adapter_versions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  adapter_version   TEXT NOT NULL,
  contract_version  TEXT NOT NULL DEFAULT 'adapter-contract-v1',
  live_execution_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pav_unique UNIQUE (provider_id, adapter_version),
  CONSTRAINT pav_live_off_round4 CHECK (live_execution_enabled = FALSE)
);

CREATE TABLE IF NOT EXISTS research.provider_rate_limit_policies (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  model_candidate_id UUID REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT,
  requests_per_minute INTEGER NOT NULL DEFAULT 0 CHECK (requests_per_minute >= 0),
  tokens_per_minute INTEGER NOT NULL DEFAULT 0 CHECK (tokens_per_minute >= 0),
  notes             TEXT,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT prlp_scope UNIQUE (provider_id, model_candidate_id)
);

-- Non-secret credential presence only (never store secrets)
CREATE TABLE IF NOT EXISTS research.provider_credential_status (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL UNIQUE REFERENCES research.providers(id) ON DELETE RESTRICT,
  status            TEXT NOT NULL DEFAULT 'missing',
  n8n_credential_label TEXT,
  last_checked_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notes             TEXT,
  CONSTRAINT pcs_status_check CHECK (status IN ('missing','present','unknown')),
  CONSTRAINT pcs_no_secret_in_label CHECK (
    n8n_credential_label IS NULL
    OR (
      n8n_credential_label !~* 'sk-|api[_-]?key|bearer |password|secret'
      AND length(n8n_credential_label) < 120
    )
  )
);

CREATE TABLE IF NOT EXISTS research.provider_authorization_records (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  model_candidate_id UUID NOT NULL REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT,
  benchmark_case_id UUID NOT NULL REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT,
  max_requests      INTEGER NOT NULL CHECK (max_requests >= 0),
  max_tokens        INTEGER NOT NULL CHECK (max_tokens >= 0),
  max_cost_usd      NUMERIC(12,6) NOT NULL CHECK (max_cost_usd >= 0),
  expires_at        TIMESTAMPTZ NOT NULL,
  approving_authority TEXT NOT NULL DEFAULT 'Taha',
  requests_spent    INTEGER NOT NULL DEFAULT 0 CHECK (requests_spent >= 0),
  tokens_spent      INTEGER NOT NULL DEFAULT 0 CHECK (tokens_spent >= 0),
  cost_spent_usd    NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (cost_spent_usd >= 0),
  status            TEXT NOT NULL DEFAULT 'active',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT par_authority CHECK (approving_authority = 'Taha'),
  CONSTRAINT par_status_check CHECK (status IN ('active','revoked','exhausted','expired')),
  CONSTRAINT par_spend_bounds CHECK (
    requests_spent <= max_requests
    AND tokens_spent <= max_tokens
    AND cost_spent_usd <= max_cost_usd
  )
);

CREATE TABLE IF NOT EXISTS research.provider_usage_ledger (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  model_candidate_id UUID REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT,
  authorization_id  UUID REFERENCES research.provider_authorization_records(id) ON DELETE RESTRICT,
  benchmark_case_id UUID REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT,
  request_count     INTEGER NOT NULL DEFAULT 1 CHECK (request_count > 0),
  input_tokens      INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens     INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  estimated_cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (estimated_cost_usd >= 0),
  live_executed     BOOLEAN NOT NULL DEFAULT FALSE,
  note              TEXT NOT NULL DEFAULT 'round4_simulated',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pul_round4_no_live CHECK (live_executed = FALSE)
);

CREATE TABLE IF NOT EXISTS research.provider_health_checks (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  checked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  check_kind        TEXT NOT NULL DEFAULT 'registry_only',
  healthy           BOOLEAN NOT NULL DEFAULT FALSE,
  detail            TEXT NOT NULL,
  CONSTRAINT phc_kind_check CHECK (check_kind IN (
    'registry_only','credential_status_only','fixture_parse','live_probe_forbidden'
  ))
);

CREATE TABLE IF NOT EXISTS research.live_request_envelopes (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  authorization_id  UUID NOT NULL REFERENCES research.provider_authorization_records(id) ON DELETE RESTRICT,
  envelope          JSONB NOT NULL,
  executable        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT lre_not_executable CHECK (executable = FALSE),
  CONSTRAINT lre_flag_check CHECK ((envelope->>'live_execution_allowed') = 'false')
);

-- Immutability
CREATE TRIGGER provider_usage_ledger_no_mutation
  BEFORE UPDATE OR DELETE ON research.provider_usage_ledger
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER live_request_envelopes_no_mutation
  BEFORE UPDATE OR DELETE ON research.live_request_envelopes
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER provider_authorization_no_delete
  BEFORE DELETE ON research.provider_authorization_records
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

-- ---------------------------------------------------------------------------
-- Seed capabilities / candidates / adapters / rates / credential missing / health
-- ---------------------------------------------------------------------------
INSERT INTO research.provider_capabilities (provider_id, capability_code, claim_text, claim_source, verification_date, verified)
SELECT p.id, c.code, c.claim, c.src, DATE '2026-07-28', FALSE
FROM research.providers p
JOIN (VALUES
  ('gemini', 'chat_completions', 'Chat-style generation API claimed in public docs', 'public_docs_summary_synthetic'),
  ('groq', 'chat_completions', 'OpenAI-compatible chat claimed in public docs', 'public_docs_summary_synthetic'),
  ('openrouter', 'chat_completions', 'Multi-model router chat claimed in public docs', 'public_docs_summary_synthetic'),
  ('ollama', 'local_chat', 'Local model serving claimed in public docs', 'public_docs_summary_synthetic')
) AS c(prov, code, claim, src) ON c.prov = p.code
ON CONFLICT DO NOTHING;

INSERT INTO research.provider_model_candidates (
  provider_id, model_id_provisional, display_name, enabled, verification_status, free_tier_status, notes
)
SELECT p.id, m.mid, m.dname, FALSE, 'unverified', 'unverified', 'provisional; not live-verified'
FROM research.providers p
JOIN (VALUES
  ('gemini', 'gemini-2.0-flash-provisional', 'Gemini 2.0 Flash (provisional)'),
  ('groq', 'llama-3.1-8b-instant-provisional', 'Llama 3.1 8B Instant (provisional)'),
  ('openrouter', 'openrouter-free-tier-provisional', 'OpenRouter free-tier placeholder (provisional)'),
  ('ollama', 'llama3.2-local-provisional', 'Ollama llama3.2 (provisional; not pulled)')
) AS m(prov, mid, dname) ON m.prov = p.code
ON CONFLICT DO NOTHING;

INSERT INTO research.provider_adapter_versions (provider_id, adapter_version, notes)
SELECT p.id, 'r4-disabled-v1', 'Request build + fixture parse only; live execution impossible'
FROM research.providers p
WHERE p.code IN ('gemini','groq','openrouter','ollama')
ON CONFLICT DO NOTHING;

INSERT INTO research.provider_rate_limit_policies (provider_id, model_candidate_id, requests_per_minute, tokens_per_minute, notes)
SELECT p.id, NULL, 0, 0, 'Round 4 hard-closed defaults'
FROM research.providers p
WHERE p.code IN ('gemini','groq','openrouter','ollama')
ON CONFLICT DO NOTHING;

INSERT INTO research.provider_credential_status (provider_id, status, n8n_credential_label, notes)
SELECT p.id, 'missing', NULL, 'No n8n credential object created in Round 4'
FROM research.providers p
WHERE p.code IN ('gemini','groq','openrouter','ollama')
ON CONFLICT (provider_id) DO NOTHING;

INSERT INTO research.provider_health_checks (provider_id, check_kind, healthy, detail)
SELECT p.id, 'registry_only', FALSE, 'Provider registered but disabled; no live probe'
FROM research.providers p
WHERE p.code IN ('gemini','groq','openrouter','ollama');

-- ---------------------------------------------------------------------------
-- Preflight + envelope builders (no HTTP)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION research.live_preflight(
  p_provider_code TEXT,
  p_model_provisional TEXT,
  p_benchmark_case_id UUID,
  p_authorization_id UUID,
  p_role_code TEXT,
  p_confidentiality_class TEXT,
  p_claimed_credential_status TEXT DEFAULT NULL
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
  v_day_req BIGINT;
  v_day_tok BIGINT;
  v_month_cost NUMERIC;
  v_steps JSONB := '[]'::jsonb;
  v_fail TEXT;
  v_detail TEXT;
BEGIN
  SELECT * INTO v_provider FROM research.providers WHERE code = p_provider_code;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'provider_disabled', 'detail', 'unknown provider', 'steps', v_steps);
  END IF;

  -- 1 provider enabled
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 1, 'name', 'provider_enabled'));
  IF NOT v_provider.enabled THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'provider_disabled', 'detail', 'provider disabled', 'steps', v_steps, 'envelope', NULL);
  END IF;

  SELECT * INTO v_model FROM research.provider_model_candidates
  WHERE provider_id = v_provider.id AND model_id_provisional = p_model_provisional;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'model_disabled', 'detail', 'model candidate missing', 'steps', v_steps);
  END IF;

  -- 2 model enabled and verified
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 2, 'name', 'model_enabled_verified'));
  IF NOT v_model.enabled THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'model_disabled', 'detail', 'model disabled', 'steps', v_steps);
  END IF;
  IF v_model.verification_status <> 'verified' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'model_unverified', 'detail', 'model unverified', 'steps', v_steps);
  END IF;

  -- 3 role permitted (no permanent assignments; only known role codes allowed for future pilots)
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 3, 'name', 'role_permitted'));
  IF p_role_code IS NULL OR p_role_code NOT IN (
    'researcher','planner','implementation_proposal_writer','qa_checker','independent_reviewer','debugger'
  ) THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'role not permitted', 'steps', v_steps);
  END IF;

  -- 4 credential status from STORE only (caller claim cannot bypass)
  SELECT * INTO v_cred FROM research.provider_credential_status WHERE provider_id = v_provider.id;
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 4, 'name', 'credential_status'));
  IF p_claimed_credential_status IS NOT NULL AND p_claimed_credential_status IS DISTINCT FROM v_cred.status THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'credential_missing', 'detail', 'caller credential claim rejected; stored state wins', 'steps', v_steps);
  END IF;
  IF v_cred.status IS DISTINCT FROM 'present' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'credential_missing', 'detail', 'credential status not present', 'steps', v_steps);
  END IF;

  -- 5 authorization valid
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 5, 'name', 'authorization_valid'));
  IF p_authorization_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_missing', 'detail', 'no authorization id', 'steps', v_steps);
  END IF;
  SELECT * INTO v_auth FROM research.provider_authorization_records WHERE id = p_authorization_id;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_missing', 'detail', 'authorization not found', 'steps', v_steps);
  END IF;
  IF v_auth.expires_at <= NOW() OR v_auth.status = 'expired' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_expired', 'detail', 'authorization expired', 'steps', v_steps);
  END IF;
  IF v_auth.provider_id <> v_provider.id
     OR v_auth.model_candidate_id <> v_model.id
     OR v_auth.benchmark_case_id <> p_benchmark_case_id THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'provider/model/case mismatch', 'steps', v_steps);
  END IF;
  IF v_auth.status <> 'active' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'authorization_mismatch', 'detail', 'authorization not active', 'steps', v_steps);
  END IF;

  -- 6 free-only / paid policy
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

  -- 7 daily request allowance
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 7, 'name', 'daily_request_allowance'));
  SELECT COALESCE(SUM(request_count),0) INTO v_day_req
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id AND created_at::date = CURRENT_DATE;
  IF v_day_req >= v_budget.daily_request_cap OR v_auth.requests_spent >= v_auth.max_requests THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'request_quota_exhausted', 'detail', 'request quota exhausted', 'steps', v_steps);
  END IF;

  -- 8 daily token allowance
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 8, 'name', 'daily_token_allowance'));
  SELECT COALESCE(SUM(input_tokens + output_tokens),0) INTO v_day_tok
  FROM research.provider_usage_ledger
  WHERE provider_id = v_provider.id AND created_at::date = CURRENT_DATE;
  IF v_day_tok >= v_budget.daily_token_cap OR v_auth.tokens_spent >= v_auth.max_tokens THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'token_quota_exhausted', 'detail', 'token quota exhausted', 'steps', v_steps);
  END IF;

  -- 9 monthly / daily cost allowance
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
  -- Round 4 default daily_cost_limit_usd=0 means only $0-authorized pilots
  IF v_budget.daily_cost_limit_usd = 0 AND v_auth.max_cost_usd > 0 AND NOT v_budget.paid_usage_authorized THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'cost_budget_exhausted', 'detail', 'paid cost not allowed under daily_cost_limit_usd=0', 'steps', v_steps);
  END IF;

  -- 10 confidentiality
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 10, 'name', 'confidentiality'));
  IF p_confidentiality_class IN ('internal_lab','restricted') AND p_provider_code <> 'ollama' THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'confidentiality_blocked', 'detail', 'remote providers blocked for confidential input', 'steps', v_steps);
  END IF;

  SELECT * INTO v_adapter FROM research.provider_adapter_versions
  WHERE provider_id = v_provider.id
  ORDER BY created_at DESC LIMIT 1;
  IF v_adapter.live_execution_enabled THEN
    RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'detail', 'live execution must remain false in Round 4', 'steps', v_steps);
  END IF;

  -- 11 ready to construct envelope (caller does next)
  v_steps := v_steps || jsonb_build_array(jsonb_build_object('step', 11, 'name', 'construct_envelope_allowed'));
  RETURN jsonb_build_object(
    'ok', true,
    'failure_class', NULL,
    'detail', 'preflight passed; envelope may be constructed but not executed',
    'steps', v_steps,
    'provider_id', v_provider.id,
    'model_candidate_id', v_model.id,
    'authorization_id', v_auth.id
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
BEGIN
  v_pf := research.live_preflight(
    p_provider_code, p_model_provisional, p_benchmark_case_id, p_authorization_id,
    p_role_code, p_confidentiality_class, p_claimed_credential_status
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
    'note', 'Round 4 non-executable envelope'
  );

  INSERT INTO research.live_request_envelopes (provider_id, authorization_id, envelope, executable)
  VALUES (v_provider_id, p_authorization_id, v_env, FALSE)
  RETURNING id INTO v_eid;

  RETURN jsonb_build_object('ok', true, 'failure_class', NULL, 'envelope_id', v_eid, 'envelope', v_env);
END;
$$;

-- Cost estimation interface (no network)
CREATE OR REPLACE FUNCTION research.estimate_provider_cost_usd(
  p_provider_code TEXT,
  p_input_tokens INT,
  p_output_tokens INT
) RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT 0::numeric; -- Round 4 free_only / $0 interface stub
$$;

-- Fixture response → canonical adapter response
CREATE OR REPLACE FUNCTION research.parse_provider_fixture_response(
  p_provider_code TEXT,
  p_fixture JSONB
) RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_text TEXT;
  v_in INT := 0;
  v_out INT := 0;
  v_finish TEXT := 'success';
  v_fail TEXT := NULL;
  v_cites JSONB := '[]'::jsonb;
BEGIN
  IF p_fixture IS NULL OR jsonb_typeof(p_fixture) <> 'object' THEN
    RETURN jsonb_build_object(
      'ok', false,
      'failure_class', 'malformed_provider_response',
      'finish_reason', 'error'
    );
  END IF;

  IF COALESCE(p_fixture->>'malformed', 'false') = 'true' THEN
    RETURN jsonb_build_object(
      'ok', false,
      'failure_class', 'malformed_provider_response',
      'finish_reason', 'error',
      'detail', 'fixture marked malformed'
    );
  END IF;

  CASE p_provider_code
    WHEN 'gemini' THEN
      v_text := p_fixture #>> '{candidates,0,content,parts,0,text}';
      v_in := COALESCE((p_fixture #>> '{usageMetadata,promptTokenCount}')::int, 0);
      v_out := COALESCE((p_fixture #>> '{usageMetadata,candidatesTokenCount}')::int, 0);
    WHEN 'groq', 'openrouter' THEN
      v_text := p_fixture #>> '{choices,0,message,content}';
      v_in := COALESCE((p_fixture #>> '{usage,prompt_tokens}')::int, 0);
      v_out := COALESCE((p_fixture #>> '{usage,completion_tokens}')::int, 0);
    WHEN 'ollama' THEN
      v_text := COALESCE(p_fixture #>> '{message,content}', p_fixture->>'response');
      v_in := COALESCE((p_fixture->>'prompt_eval_count')::int, 0);
      v_out := COALESCE((p_fixture->>'eval_count')::int, 0);
    ELSE
      RETURN jsonb_build_object('ok', false, 'failure_class', 'unsupported_capability', 'finish_reason', 'error');
  END CASE;

  IF v_text IS NULL OR length(trim(v_text)) = 0 THEN
    RETURN jsonb_build_object(
      'ok', false,
      'failure_class', 'malformed_provider_response',
      'finish_reason', 'error',
      'detail', 'missing text content'
    );
  END IF;

  IF p_fixture ? 'citations' THEN
    v_cites := p_fixture->'citations';
  END IF;

  RETURN jsonb_build_object(
    'ok', true,
    'failure_class', NULL,
    'provider', p_provider_code,
    'model', COALESCE(p_fixture->>'model', 'fixture'),
    'model_version', p_fixture->>'model_version',
    'structured_output', jsonb_build_object('text', v_text),
    'cited_evidence_ids', v_cites,
    'latency_ms', COALESCE((p_fixture->>'latency_ms')::int, 1),
    'input_tokens', v_in,
    'output_tokens', v_out,
    'estimated_cost_usd', research.estimate_provider_cost_usd(p_provider_code, v_in, v_out),
    'finish_reason', v_finish,
    'retry_count', 0,
    'output_fingerprint', encode(digest(convert_to(v_text, 'UTF8'), 'sha256'), 'hex')
  );
END;
$$;

-- Simulated authorization spend (no live call); fail closed on overspend
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
    request_count, input_tokens, output_tokens, estimated_cost_usd, live_executed, note
  ) VALUES (
    v_auth.provider_id, v_auth.model_candidate_id, v_auth.id, v_auth.benchmark_case_id,
    p_requests, GREATEST(p_tokens, 0), 0, p_cost, FALSE, p_note
  );

  RETURN jsonb_build_object('ok', true);
END;
$$;

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW research.v_enabled_provider_readiness AS
SELECT
  p.code,
  p.enabled AS provider_enabled,
  m.model_id_provisional,
  m.enabled AS model_enabled,
  m.verification_status,
  m.free_tier_status,
  c.status AS credential_status,
  b.free_only,
  b.paid_fallback,
  b.daily_request_cap,
  b.daily_token_cap,
  b.daily_cost_limit_usd,
  b.monthly_cost_ceiling_usd,
  a.live_execution_enabled,
  (p.enabled AND m.enabled AND m.verification_status = 'verified' AND c.status = 'present'
    AND a.live_execution_enabled = FALSE) AS ready_for_bounded_pilot_prep
FROM research.providers p
LEFT JOIN research.provider_model_candidates m ON m.provider_id = p.id
LEFT JOIN research.provider_credential_status c ON c.provider_id = p.id
LEFT JOIN research.provider_budget_policies b ON b.provider_id = p.id
LEFT JOIN LATERAL (
  SELECT * FROM research.provider_adapter_versions v WHERE v.provider_id = p.id ORDER BY created_at DESC LIMIT 1
) a ON TRUE
WHERE p.code IN ('gemini','groq','openrouter','ollama');

CREATE OR REPLACE VIEW research.v_missing_credentials AS
SELECT p.code, c.status, c.n8n_credential_label, c.last_checked_at
FROM research.providers p
JOIN research.provider_credential_status c ON c.provider_id = p.id
WHERE c.status <> 'present';

CREATE OR REPLACE VIEW research.v_remaining_daily_quota AS
SELECT
  p.code,
  b.daily_request_cap,
  b.daily_token_cap,
  GREATEST(b.daily_request_cap - COALESCE(u.req_used, 0), 0) AS requests_remaining,
  GREATEST(b.daily_token_cap - COALESCE(u.tok_used, 0), 0) AS tokens_remaining
FROM research.providers p
JOIN research.provider_budget_policies b ON b.provider_id = p.id
LEFT JOIN LATERAL (
  SELECT SUM(request_count) AS req_used, SUM(input_tokens + output_tokens) AS tok_used
  FROM research.provider_usage_ledger l
  WHERE l.provider_id = p.id AND l.created_at::date = CURRENT_DATE
) u ON TRUE
WHERE p.code IN ('gemini','groq','openrouter','ollama');

CREATE OR REPLACE VIEW research.v_remaining_monthly_budget AS
SELECT
  p.code,
  b.monthly_cost_ceiling_usd,
  b.daily_cost_limit_usd,
  GREATEST(b.monthly_cost_ceiling_usd - COALESCE(u.cost_used, 0), 0) AS monthly_budget_remaining_usd
FROM research.providers p
JOIN research.provider_budget_policies b ON b.provider_id = p.id
LEFT JOIN LATERAL (
  SELECT SUM(estimated_cost_usd) AS cost_used
  FROM research.provider_usage_ledger l
  WHERE l.provider_id = p.id
    AND date_trunc('month', l.created_at) = date_trunc('month', NOW())
) u ON TRUE
WHERE p.code IN ('gemini','groq','openrouter','ollama');

CREATE OR REPLACE VIEW research.v_unauthorized_call_warnings AS
SELECT
  p.code AS provider_code,
  'no_active_authorization' AS warning
FROM research.providers p
WHERE p.code IN ('gemini','groq','openrouter','ollama')
  AND NOT EXISTS (
    SELECT 1 FROM research.provider_authorization_records a
    WHERE a.provider_id = p.id AND a.status = 'active' AND a.expires_at > NOW()
  );

CREATE OR REPLACE VIEW research.v_provider_health_summary AS
SELECT
  p.code,
  h.checked_at,
  h.check_kind,
  h.healthy,
  h.detail
FROM research.providers p
JOIN LATERAL (
  SELECT * FROM research.provider_health_checks x
  WHERE x.provider_id = p.id
  ORDER BY checked_at DESC LIMIT 1
) h ON TRUE
WHERE p.code IN ('gemini','groq','openrouter','ollama');

CREATE OR REPLACE VIEW research.v_models_awaiting_verification AS
SELECT p.code AS provider_code, m.model_id_provisional, m.display_name, m.verification_status, m.free_tier_status, m.enabled
FROM research.provider_model_candidates m
JOIN research.providers p ON p.id = m.provider_id
WHERE m.verification_status = 'unverified';

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA research TO research_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA research TO research_app;
GRANT SELECT ON ALL TABLES IN SCHEMA research TO n8n_app;

INSERT INTO research.schema_version (version, note) VALUES
  (5, 'Round 4: gated live provider readiness and budget controls (disabled; no live calls)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
