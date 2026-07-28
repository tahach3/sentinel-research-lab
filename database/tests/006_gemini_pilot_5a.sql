-- Round 5A Gemini pilot gate tests (no live calls)
\set ON_ERROR_STOP on

-- Official policy + model verification present
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM research.provider_policy_verifications v
    JOIN research.providers p ON p.id = v.provider_id
    WHERE p.code = 'gemini'
      AND v.model_identifier = 'gemini-2.5-flash'
      AND v.free_tier_available
      AND v.billing_required_for_free_tier = FALSE
      AND v.pakistan_available
      AND v.blocked_provider_policy = FALSE
  ) THEN
    RAISE EXCEPTION 'T-policy FAIL: verification missing or blocked';
  END IF;
  RAISE NOTICE 'PASS policy verification record';
END $$;

-- Three researcher cases selected
DO $$
DECLARE codes TEXT[];
BEGIN
  SELECT benchmark_case_codes INTO codes
  FROM research.provider_pilot_proposals WHERE pilot_code = 'GEMINI-PILOT-5A';
  IF codes IS DISTINCT FROM ARRAY['R-N-01','R-A-01','R-X-01']::text[] THEN
    RAISE EXCEPTION 'T-cases FAIL: %', codes;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.benchmark_cases bc
    JOIN research.benchmark_suites bs ON bs.id = bc.suite_id
    WHERE bc.case_code = 'R-N-01' AND bc.case_kind = 'normal' AND bs.role_code = 'researcher'
  ) THEN RAISE EXCEPTION 'normal researcher case missing'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.benchmark_cases bc
    JOIN research.benchmark_suites bs ON bs.id = bc.suite_id
    WHERE bc.case_code = 'R-A-01' AND bc.case_kind = 'ambiguous' AND bs.role_code = 'researcher'
  ) THEN RAISE EXCEPTION 'ambiguous researcher case missing'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.benchmark_cases bc
    JOIN research.benchmark_suites bs ON bs.id = bc.suite_id
    WHERE bc.case_code = 'R-X-01' AND bc.case_kind = 'adversarial' AND bs.role_code = 'researcher'
  ) THEN RAISE EXCEPTION 'adversarial researcher case missing'; END IF;
  RAISE NOTICE 'PASS three-case pilot selection';
END $$;

-- Authorization binding + USD 0
DO $$
DECLARE pp research.provider_pilot_proposals%ROWTYPE; n INT;
BEGIN
  SELECT * INTO pp FROM research.provider_pilot_proposals WHERE pilot_code = 'GEMINI-PILOT-5A';
  IF pp.max_authorized_cost_usd <> 0 OR pp.retries_allowed OR pp.fallback_provider_allowed THEN
    RAISE EXCEPTION 'T-auth FAIL: cost/retry/fallback';
  END IF;
  IF pp.max_total_requests <> 3 OR pp.max_successful_calls <> 3 OR pp.max_attempts_per_case <> 1 THEN
    RAISE EXCEPTION 'T-auth FAIL: request bounds';
  END IF;
  SELECT count(*) INTO n FROM research.provider_authorization_records
  WHERE pilot_proposal_id = pp.id AND status = 'proposed' AND max_cost_usd = 0 AND max_requests = 1;
  IF n <> 3 THEN RAISE EXCEPTION 'T-auth FAIL: expected 3 proposed auths got %', n; END IF;
  RAISE NOTICE 'PASS authorization binding and USD 0';
END $$;

-- Provider disabled / model disabled / missing credential / no executable
DO $$
DECLARE g JSONB; mid TEXT; case_id UUID; aid UUID; res JSONB;
BEGIN
  IF EXISTS (SELECT 1 FROM research.providers WHERE code='gemini' AND enabled) THEN
    RAISE EXCEPTION 'provider enabled';
  END IF;
  IF EXISTS (
    SELECT 1 FROM research.provider_model_candidates m
    JOIN research.providers p ON p.id=m.provider_id
    WHERE p.code='gemini' AND m.enabled
  ) THEN RAISE EXCEPTION 'model enabled'; END IF;

  g := research.gemini_pilot_5a_gate_status();
  IF COALESCE((g->>'executable_request_permitted')::boolean, true) THEN
    RAISE EXCEPTION 'executable permitted';
  END IF;
  IF NOT (g->'blockers' ? 'provider_disabled') THEN RAISE EXCEPTION 'missing provider_disabled blocker'; END IF;
  IF NOT (g->'blockers' ? 'model_disabled') THEN RAISE EXCEPTION 'missing model_disabled blocker'; END IF;
  IF NOT (g->'blockers' ? 'credential_missing') THEN RAISE EXCEPTION 'missing credential_missing blocker'; END IF;

  SELECT m.model_id_provisional INTO mid
  FROM research.provider_model_candidates m
  JOIN research.providers p ON p.id=m.provider_id WHERE p.code='gemini';
  SELECT benchmark_case_ids[1] INTO case_id FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A';
  SELECT id INTO aid FROM research.provider_authorization_records
  WHERE pilot_proposal_id = (SELECT id FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A')
  LIMIT 1;

  res := research.build_provider_request_envelope(
    'gemini', mid, case_id, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object('prompt','no','input_fingerprint', encode(digest('5a','sha256'),'hex'))
  );
  IF res->>'failure_class' <> 'provider_disabled' THEN
    RAISE EXCEPTION 'envelope should fail provider_disabled got %', res;
  END IF;
  RAISE NOTICE 'PASS disabled/credential/no-envelope gates';
END $$;

-- Expired authorization blocks (using Round 4 preflight path with armed temp state then expire)
DO $$
DECLARE
  pid UUID; mid UUID; case_id UUID; aid UUID; mcode TEXT; res JSONB;
BEGIN
  SELECT id INTO pid FROM research.providers WHERE code='gemini';
  SELECT id, model_id_provisional INTO mid, mcode FROM research.provider_model_candidates WHERE provider_id=pid;
  SELECT benchmark_case_ids[1] INTO case_id FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A';

  -- temporary arm for expired-auth isolation (reset after)
  UPDATE research.providers SET enabled=TRUE WHERE id=pid;
  UPDATE research.provider_model_candidates
  SET enabled=TRUE, verification_status='verified', free_tier_status='free_confirmed' WHERE id=mid;
  UPDATE research.provider_credential_status SET status='present', n8n_credential_label='local-n8n-label-only' WHERE provider_id=pid;
  UPDATE research.provider_budget_policies
  SET daily_request_cap=10, daily_token_cap=10000 WHERE provider_id=pid;

  INSERT INTO research.provider_authorization_records (
    provider_id, model_candidate_id, benchmark_case_id, max_requests, max_tokens, max_cost_usd,
    expires_at, approving_authority, status
  ) VALUES (pid, mid, case_id, 1, 1000, 0, NOW() - INTERVAL '1 hour', 'Taha', 'active')
  RETURNING id INTO aid;

  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_expired' THEN
    RAISE EXCEPTION 'expired auth expected got %', res;
  END IF;

  -- wrong case
  UPDATE research.provider_authorization_records SET expires_at = NOW() + INTERVAL '1 day', status='active' WHERE id=aid;
  res := research.live_preflight(
    'gemini', mcode,
    (SELECT benchmark_case_ids[2] FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A'),
    aid, 'researcher', 'public_or_synthetic'
  );
  IF res->>'failure_class' <> 'authorization_mismatch' THEN
    RAISE EXCEPTION 'wrong-case expected mismatch got %', res;
  END IF;

  -- confidential block
  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'restricted');
  IF res->>'failure_class' <> 'confidentiality_blocked' THEN
    RAISE EXCEPTION 'confidential expected got %', res;
  END IF;

  -- reset Gemini to Round 5A safe defaults
  UPDATE research.providers SET enabled=FALSE WHERE id=pid;
  UPDATE research.provider_model_candidates SET enabled=FALSE WHERE id=mid;
  UPDATE research.provider_credential_status SET status='missing', n8n_credential_label=NULL WHERE provider_id=pid;
  UPDATE research.provider_budget_policies
  SET daily_request_cap=0, daily_token_cap=0, free_only=TRUE, paid_fallback=FALSE,
      paid_usage_authorized=FALSE, daily_cost_limit_usd=0, monthly_cost_ceiling_usd=0
  WHERE provider_id=pid;

  RAISE NOTICE 'PASS expired/wrong-case/confidential tests';
END $$;

-- USD 0 enforcement on pilot
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM research.provider_pilot_proposals
    WHERE pilot_code='GEMINI-PILOT-5A' AND max_authorized_cost_usd <> 0
  ) THEN RAISE EXCEPTION 'non-zero pilot cost'; END IF;
  RAISE NOTICE 'PASS USD 0 budget enforcement';
END $$;

SELECT research.gemini_pilot_5a_gate_status() AS gate;
SELECT * FROM research.v_gemini_pilot_5a;
SELECT 'ROUND5A_TESTS_DONE' AS marker;
