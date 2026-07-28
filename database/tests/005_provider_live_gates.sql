-- Round 4 provider gate tests (no live calls, no secrets)
\set ON_ERROR_STOP on

CREATE OR REPLACE FUNCTION research._r4_case_id()
RETURNS UUID LANGUAGE sql STABLE AS $$
  SELECT id FROM research.benchmark_cases ORDER BY created_at LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION research._r4_arm_provider(
  p_code TEXT,
  p_enable_provider BOOLEAN,
  p_enable_model BOOLEAN,
  p_verify_model BOOLEAN,
  p_free_confirmed BOOLEAN,
  p_cred_present BOOLEAN,
  p_daily_req INT,
  p_daily_tok INT
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  pid UUID;
  mid UUID;
BEGIN
  SELECT id INTO pid FROM research.providers WHERE code = p_code;
  UPDATE research.providers SET enabled = p_enable_provider WHERE id = pid;
  SELECT id INTO mid FROM research.provider_model_candidates WHERE provider_id = pid LIMIT 1;
  UPDATE research.provider_model_candidates
  SET enabled = p_enable_model,
      verification_status = CASE WHEN p_verify_model THEN 'verified' ELSE 'unverified' END,
      free_tier_status = CASE WHEN p_free_confirmed THEN 'free_confirmed' ELSE 'unverified' END
  WHERE id = mid;
  UPDATE research.provider_credential_status
  SET status = CASE WHEN p_cred_present THEN 'present' ELSE 'missing' END,
      n8n_credential_label = CASE WHEN p_cred_present THEN 'local-n8n-label-only' ELSE NULL END,
      last_checked_at = NOW()
  WHERE provider_id = pid;
  UPDATE research.provider_budget_policies
  SET daily_request_cap = p_daily_req,
      daily_token_cap = p_daily_tok,
      free_only = TRUE,
      paid_fallback = FALSE,
      paid_usage_authorized = FALSE,
      daily_cost_limit_usd = 0,
      monthly_cost_ceiling_usd = 0,
      updated_at = NOW()
  WHERE provider_id = pid;
  RETURN mid;
END;
$$;

CREATE OR REPLACE FUNCTION research._r4_make_auth(
  p_provider TEXT,
  p_model_id UUID,
  p_case UUID,
  p_max_req INT,
  p_max_tok INT,
  p_max_cost NUMERIC,
  p_expires TIMESTAMPTZ
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  pid UUID;
  aid UUID;
BEGIN
  SELECT id INTO pid FROM research.providers WHERE code = p_provider;
  INSERT INTO research.provider_authorization_records (
    provider_id, model_candidate_id, benchmark_case_id,
    max_requests, max_tokens, max_cost_usd, expires_at, approving_authority
  ) VALUES (
    pid, p_model_id, p_case, p_max_req, p_max_tok, p_max_cost, p_expires, 'Taha'
  ) RETURNING id INTO aid;
  RETURN aid;
END;
$$;

CREATE OR REPLACE FUNCTION research._r4_reset_defaults()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  UPDATE research.providers SET enabled = FALSE
  WHERE code IN ('gemini','groq','openrouter','ollama');
  UPDATE research.provider_model_candidates m
  SET enabled = FALSE, verification_status = 'unverified', free_tier_status = 'unverified'
  FROM research.providers p
  WHERE m.provider_id = p.id AND p.code IN ('gemini','groq','openrouter','ollama');
  UPDATE research.provider_credential_status c
  SET status = 'missing', n8n_credential_label = NULL
  FROM research.providers p
  WHERE c.provider_id = p.id AND p.code IN ('gemini','groq','openrouter','ollama');
  UPDATE research.provider_budget_policies b
  SET daily_request_cap = 0, daily_token_cap = 0, free_only = TRUE,
      paid_fallback = FALSE, paid_usage_authorized = FALSE,
      daily_cost_limit_usd = 0, monthly_cost_ceiling_usd = 0
  FROM research.providers p
  WHERE b.provider_id = p.id AND p.code IN ('gemini','groq','openrouter','ollama');
END;
$$;

-- 1) All providers disabled by default
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM research.providers
    WHERE code IN ('gemini','groq','openrouter','ollama') AND enabled
  ) THEN RAISE EXCEPTION 'T1 FAIL: provider enabled by default'; END IF;
  IF EXISTS (
    SELECT 1 FROM research.provider_model_candidates m
    JOIN research.providers p ON p.id = m.provider_id
    WHERE p.code IN ('gemini','groq','openrouter','ollama') AND m.enabled
  ) THEN RAISE EXCEPTION 'T1 FAIL: model enabled by default'; END IF;
  RAISE NOTICE 'PASS T1 defaults disabled';
END $$;

-- 2) Disabled provider cannot create envelope
DO $$
DECLARE
  mid UUID; aid UUID; case_id UUID; res JSONB;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', FALSE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  aid := research._r4_make_auth('gemini', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.build_provider_request_envelope(
    'gemini', (SELECT model_id_provisional FROM research.provider_model_candidates WHERE id = mid),
    case_id, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object('prompt','hi','input_fingerprint', encode(digest('t2','sha256'),'hex'))
  );
  IF res->>'failure_class' <> 'provider_disabled' OR res->'envelope' IS NOT NULL AND res->>'envelope' <> 'null' THEN
    RAISE EXCEPTION 'T2 FAIL: %', res;
  END IF;
  RAISE NOTICE 'PASS T2 disabled provider blocks envelope';
END $$;

-- 3) Missing credential blocks
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('groq', TRUE, TRUE, TRUE, TRUE, FALSE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('groq', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.live_preflight('groq', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'credential_missing' THEN RAISE EXCEPTION 'T3 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T3 missing credential';
END $$;

-- 4) Caller-supplied fake credential cannot bypass stored state
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('openrouter', TRUE, TRUE, TRUE, TRUE, FALSE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('openrouter', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.live_preflight('openrouter', mcode, case_id, aid, 'researcher', 'public_or_synthetic', 'present');
  IF res->>'failure_class' <> 'credential_missing' THEN RAISE EXCEPTION 'T4 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T4 fake credential claim rejected';
END $$;

-- 5) Missing authorization blocks
DO $$
DECLARE mid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('ollama', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  res := research.live_preflight('ollama', mcode, case_id, NULL, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_missing' THEN RAISE EXCEPTION 'T5 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T5 missing authorization';
END $$;

-- 6) Expired authorization blocks
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('gemini', mid, case_id, 3, 1000, 0, NOW() - INTERVAL '1 hour');
  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_expired' THEN RAISE EXCEPTION 'T6 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T6 expired authorization';
END $$;

-- 7) Wrong provider/model/case authorization blocks
DO $$
DECLARE mid UUID; mid2 UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  mid2 := research._r4_arm_provider('groq', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  -- auth bound to groq model but call gemini
  aid := research._r4_make_auth('groq', mid2, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_mismatch' THEN RAISE EXCEPTION 'T7 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T7 authorization mismatch';
END $$;

-- 8) Request quota exhaustion
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, TRUE, TRUE, 0, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('gemini', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN RAISE EXCEPTION 'T8 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T8 request quota';
END $$;

-- 9) Token quota exhaustion
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 0);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('gemini', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'token_quota_exhausted' THEN RAISE EXCEPTION 'T9 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T9 token quota';
END $$;

-- 10) Cost ceiling exhaustion
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('gemini', mid, case_id, 3, 1000, 1.00, NOW() + INTERVAL '1 day');
  -- max_cost > 0 without paid_usage_authorized and daily_cost_limit_usd=0
  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'cost_budget_exhausted' THEN RAISE EXCEPTION 'T10 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T10 cost ceiling';
END $$;

-- 11) Unverified free-tier blocks
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, FALSE, TRUE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('gemini', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'free_tier_unverified' THEN RAISE EXCEPTION 'T11 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T11 free-tier unverified';
END $$;

-- 12) Confidential input blocks remote providers
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('groq', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('groq', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.live_preflight('groq', mcode, case_id, aid, 'researcher', 'restricted');
  IF res->>'failure_class' <> 'confidentiality_blocked' THEN RAISE EXCEPTION 'T12 FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T12 confidentiality';
END $$;

-- 13) Valid simulated authorization creates one non-executed envelope
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB; mcode TEXT;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  SELECT model_id_provisional INTO mcode FROM research.provider_model_candidates WHERE id = mid;
  aid := research._r4_make_auth('gemini', mid, case_id, 3, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.build_provider_request_envelope(
    'gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object('prompt','fixture only','input_fingerprint', encode(digest('t13','sha256'),'hex'))
  );
  IF COALESCE((res->>'ok')::boolean,false) IS NOT TRUE THEN RAISE EXCEPTION 'T13 FAIL: %', res; END IF;
  IF (res->'envelope'->>'live_execution_allowed') <> 'false' THEN RAISE EXCEPTION 'T13 FAIL: executable'; END IF;
  IF EXISTS (SELECT 1 FROM research.live_request_envelopes WHERE executable = TRUE) THEN
    RAISE EXCEPTION 'T13 FAIL: executable envelope stored';
  END IF;
  RAISE NOTICE 'PASS T13 non-executed envelope';
END $$;

-- 14) Authorization request count cannot be overspent
DO $$
DECLARE mid UUID; aid UUID; case_id UUID; res JSONB;
BEGIN
  PERFORM research._r4_reset_defaults();
  case_id := research._r4_case_id();
  mid := research._r4_arm_provider('gemini', TRUE, TRUE, TRUE, TRUE, TRUE, 10, 1000);
  aid := research._r4_make_auth('gemini', mid, case_id, 1, 1000, 0, NOW() + INTERVAL '1 day');
  res := research.record_authorization_spend(aid, 1, 10, 0);
  IF COALESCE((res->>'ok')::boolean,false) IS NOT TRUE THEN RAISE EXCEPTION 'T14a FAIL: %', res; END IF;
  res := research.record_authorization_spend(aid, 1, 10, 0);
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN RAISE EXCEPTION 'T14b FAIL: %', res; END IF;
  RAISE NOTICE 'PASS T14 auth overspend blocked';
END $$;

-- 15) Usage ledger append-only
DO $$
DECLARE ok BOOLEAN := FALSE; lid UUID;
BEGIN
  SELECT id INTO lid FROM research.provider_usage_ledger LIMIT 1;
  BEGIN
    UPDATE research.provider_usage_ledger SET note = 'mutated' WHERE id = lid;
  EXCEPTION WHEN OTHERS THEN ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'T15 FAIL: update allowed'; END IF;
  ok := FALSE;
  BEGIN
    DELETE FROM research.provider_usage_ledger WHERE id = lid;
  EXCEPTION WHEN OTHERS THEN ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'T15 FAIL: delete allowed'; END IF;
  RAISE NOTICE 'PASS T15 usage ledger immutable';
END $$;

-- 16) Fixture responses normalize for all four providers
DO $$
DECLARE r JSONB;
BEGIN
  r := research.parse_provider_fixture_response('gemini', jsonb_build_object(
    'candidates', jsonb_build_array(jsonb_build_object('content', jsonb_build_object('parts', jsonb_build_array(jsonb_build_object('text','g'))))),
    'usageMetadata', jsonb_build_object('promptTokenCount',1,'candidatesTokenCount',2)
  ));
  IF COALESCE((r->>'ok')::boolean,false) IS NOT TRUE THEN RAISE EXCEPTION 'T16 gemini %', r; END IF;
  r := research.parse_provider_fixture_response('groq', jsonb_build_object(
    'choices', jsonb_build_array(jsonb_build_object('message', jsonb_build_object('content','x'))),
    'usage', jsonb_build_object('prompt_tokens',1,'completion_tokens',2)
  ));
  IF COALESCE((r->>'ok')::boolean,false) IS NOT TRUE THEN RAISE EXCEPTION 'T16 groq %', r; END IF;
  r := research.parse_provider_fixture_response('openrouter', jsonb_build_object(
    'choices', jsonb_build_array(jsonb_build_object('message', jsonb_build_object('content','y'))),
    'usage', jsonb_build_object('prompt_tokens',1,'completion_tokens',2)
  ));
  IF COALESCE((r->>'ok')::boolean,false) IS NOT TRUE THEN RAISE EXCEPTION 'T16 openrouter %', r; END IF;
  r := research.parse_provider_fixture_response('ollama', jsonb_build_object(
    'message', jsonb_build_object('content','z'), 'prompt_eval_count',1, 'eval_count',2
  ));
  IF COALESCE((r->>'ok')::boolean,false) IS NOT TRUE THEN RAISE EXCEPTION 'T16 ollama %', r; END IF;
  RAISE NOTICE 'PASS T16 fixture normalize';
END $$;

-- 17) Malformed fixture fails closed
DO $$
DECLARE r JSONB;
BEGIN
  r := research.parse_provider_fixture_response('gemini', jsonb_build_object('malformed', true));
  IF r->>'failure_class' <> 'malformed_provider_response' THEN RAISE EXCEPTION 'T17 FAIL: %', r; END IF;
  RAISE NOTICE 'PASS T17 malformed fixture';
END $$;

-- 18/19/20 covered partly here + external workflow scan
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM research.provider_adapter_versions WHERE live_execution_enabled
  ) THEN RAISE EXCEPTION 'T18 FAIL: live execution enabled'; END IF;
  IF EXISTS (
    SELECT 1 FROM research.provider_usage_ledger WHERE live_executed
  ) THEN RAISE EXCEPTION 'T18 FAIL: live_executed true'; END IF;
  RAISE NOTICE 'PASS T18 no live execution flags';
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='research' AND column_name ILIKE '%api_key%'
  ) THEN RAISE EXCEPTION 'T19 FAIL: api_key column exists'; END IF;
  RAISE NOTICE 'PASS T19 no secret columns';
END $$;

DO $$
BEGIN
  PERFORM research._r4_reset_defaults();
END $$;

-- View smoke
SELECT count(*) AS readiness_rows FROM research.v_enabled_provider_readiness;
SELECT count(*) AS missing_creds FROM research.v_missing_credentials;
SELECT count(*) AS awaiting FROM research.v_models_awaiting_verification;

SELECT 'ROUND4_TESTS_DONE' AS marker;
