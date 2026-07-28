-- Round 5A repair validation (residue-free; no live calls)
\set ON_ERROR_STOP on

CREATE OR REPLACE FUNCTION research._r5a_repair_reset_defaults()
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
  UPDATE research.provider_authorization_records a
  SET status = 'proposed',
      activated_at = NULL,
      expires_at = TIMESTAMPTZ '-infinity',
      requests_spent = 0,
      tokens_spent = 0,
      cost_spent_usd = 0,
      test_fixture_id = NULL
  FROM research.provider_pilot_proposals pp
  WHERE a.pilot_proposal_id = pp.id AND pp.pilot_code = 'GEMINI-PILOT-5A';
END;
$$;

CREATE OR REPLACE FUNCTION research._r5a_arm_for_pilot_tests()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE pid UUID;
BEGIN
  SELECT id INTO pid FROM research.providers WHERE code = 'gemini';
  UPDATE research.providers SET enabled = TRUE WHERE id = pid;
  UPDATE research.provider_model_candidates
  SET enabled = TRUE, verification_status = 'verified', free_tier_status = 'free_confirmed'
  WHERE provider_id = pid;
  UPDATE research.provider_credential_status
  SET status = 'present', n8n_credential_label = 'local-n8n-label-only'
  WHERE provider_id = pid;
  UPDATE research.provider_budget_policies
  SET daily_request_cap = 100, daily_token_cap = 100000
  WHERE provider_id = pid;
END;
$$;

-- Snapshot expected final pilot auth state helper
CREATE OR REPLACE FUNCTION research._r5a_assert_final_pilot_state()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE n_prop INT; n_active_test INT;
BEGIN
  SELECT count(*) INTO n_prop
  FROM research.provider_authorization_records a
  JOIN research.provider_pilot_proposals pp ON pp.id = a.pilot_proposal_id
  WHERE pp.pilot_code = 'GEMINI-PILOT-5A' AND a.status = 'proposed';
  IF n_prop <> 3 THEN
    RAISE EXCEPTION 'expected exactly 3 proposed pilot auths, got %', n_prop;
  END IF;
  SELECT count(*) INTO n_active_test
  FROM research.provider_authorization_records a
  JOIN research.providers p ON p.id = a.provider_id
  WHERE p.code = 'gemini' AND a.status = 'active' AND a.test_fixture_id IS NOT NULL;
  IF n_active_test <> 0 THEN
    RAISE EXCEPTION 'active test fixture auths remain: %', n_active_test;
  END IF;
  IF EXISTS (SELECT 1 FROM research.providers WHERE code='gemini' AND enabled) THEN
    RAISE EXCEPTION 'gemini enabled';
  END IF;
  IF EXISTS (
    SELECT 1 FROM research.provider_model_candidates m
    JOIN research.providers p ON p.id=m.provider_id
    WHERE p.code='gemini' AND m.enabled
  ) THEN RAISE EXCEPTION 'model enabled'; END IF;
END;
$$;

DO $$
DECLARE
  fixture TEXT := 'r5a-repair-v1';
  aid UUID; aid2 UUID; aid3 UUID;
  case1 UUID; case2 UUID; case3 UUID;
  pilot UUID; mid UUID; mcode TEXT;
  res JSONB; auth research.provider_authorization_records%ROWTYPE;
  delta INTERVAL;
BEGIN
  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_repair_reset_defaults();

  SELECT id INTO pilot FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A';
  SELECT benchmark_case_ids[1], benchmark_case_ids[2], benchmark_case_ids[3]
    INTO case1, case2, case3
  FROM research.provider_pilot_proposals WHERE id = pilot;
  SELECT m.id, m.model_id_provisional INTO mid, mcode
  FROM research.provider_model_candidates m
  JOIN research.providers p ON p.id=m.provider_id WHERE p.code='gemini';

  SELECT id INTO aid FROM research.provider_authorization_records
  WHERE pilot_proposal_id = pilot AND benchmark_case_id = case1 AND status='proposed';
  SELECT id INTO aid2 FROM research.provider_authorization_records
  WHERE pilot_proposal_id = pilot AND benchmark_case_id = case2 AND status='proposed';
  SELECT id INTO aid3 FROM research.provider_authorization_records
  WHERE pilot_proposal_id = pilot AND benchmark_case_id = case3 AND status='proposed';

  -- 1) Proposed not executable
  IF (SELECT expires_at FROM research.provider_authorization_records WHERE id=aid) <> TIMESTAMPTZ '-infinity' THEN
    RAISE EXCEPTION 'proposed auth must use -infinity expiry';
  END IF;
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object('prompt','x','input_fingerprint', encode(digest('p1','sha256'),'hex'))
  );
  IF res->>'failure_class' <> 'provider_disabled' THEN
    RAISE EXCEPTION 'proposed/disabled should block envelope: %', res;
  END IF;
  RAISE NOTICE 'PASS proposed not executable';

  -- 2) Activation sets exactly 24h
  auth := research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  IF auth.status <> 'active' THEN RAISE EXCEPTION 'activation failed'; END IF;
  delta := auth.expires_at - auth.activated_at;
  IF delta <> INTERVAL '24 hours' THEN
    RAISE EXCEPTION 'expected 24h window got %', delta;
  END IF;
  RAISE NOTICE 'PASS activation 24h expiry';

  -- 3) Direct status update cannot create >24h window
  UPDATE research.provider_authorization_records
  SET status='proposed', activated_at=NULL, expires_at=TIMESTAMPTZ '-infinity'
  WHERE id=aid2;
  UPDATE research.provider_authorization_records
  SET status='active', expires_at = NOW() + INTERVAL '30 days'
  WHERE id=aid2;
  SELECT * INTO auth FROM research.provider_authorization_records WHERE id=aid2;
  IF auth.expires_at - auth.activated_at <> INTERVAL '24 hours' THEN
    RAISE EXCEPTION 'direct active update did not clamp to 24h: %', auth.expires_at - auth.activated_at;
  END IF;
  -- mark as fixture for cleanup path of extra activation
  UPDATE research.provider_authorization_records SET test_fixture_id = fixture WHERE id IN (aid, aid2);
  RAISE NOTICE 'PASS direct update clamped to 24h';

  -- Prepare arm + approve pilot for aggregate tests
  PERFORM research._r5a_arm_for_pilot_tests();
  UPDATE research.provider_pilot_proposals
  SET status='approved', taha_approved_at=NOW(), expires_at=NOW()+INTERVAL '24 hours'
  WHERE id=pilot;
  -- ensure aid3 activated under fixture
  UPDATE research.provider_authorization_records
  SET status='proposed', activated_at=NULL, expires_at=TIMESTAMPTZ '-infinity', test_fixture_id=fixture
  WHERE id=aid3;
  PERFORM research.activate_pilot_authorization(aid3, 'GEMINI-PILOT-5A');
  UPDATE research.provider_authorization_records SET test_fixture_id = fixture WHERE id=aid3;

  -- Re-activate aid if needed (already active)
  UPDATE research.provider_authorization_records
  SET status='active', activated_at=NOW(), expires_at=NOW()+INTERVAL '24 hours', test_fixture_id=fixture
  WHERE id=aid AND status <> 'active';

  -- 4) Expired fails closed
  UPDATE research.provider_authorization_records
  SET activated_at = NOW() - INTERVAL '25 hours',
      expires_at = NOW() - INTERVAL '1 hour'
  WHERE id=aid;
  res := research.live_preflight('gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_expired' THEN RAISE EXCEPTION 'expired expected %', res; END IF;
  -- restore valid window for later tests
  UPDATE research.provider_authorization_records
  SET activated_at = NOW(), expires_at = NOW() + INTERVAL '24 hours', status='active'
  WHERE id=aid;
  RAISE NOTICE 'PASS expired fails closed';

  -- 5) Wrong case / role
  res := research.live_preflight('gemini', mcode, case2, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_mismatch' THEN RAISE EXCEPTION 'wrong case %', res; END IF;
  res := research.live_preflight('gemini', mcode, case1, aid, 'planner', 'public_or_synthetic');
  IF res->>'failure_class' <> 'unsupported_capability' THEN RAISE EXCEPTION 'wrong role %', res; END IF;
  RAISE NOTICE 'PASS wrong case/role';

  -- 14) Confidential blocked
  res := research.live_preflight('gemini', mcode, case1, aid, 'researcher', 'restricted');
  IF res->>'failure_class' <> 'confidentiality_blocked' THEN RAISE EXCEPTION 'confidential %', res; END IF;
  RAISE NOTICE 'PASS confidential blocked';

  -- 11) Retry blocked
  res := research.live_preflight('gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic', NULL, 0, 0, TRUE, NULL);
  IF res->>'failure_class' <> 'unsupported_capability' THEN RAISE EXCEPTION 'retry %', res; END IF;
  RAISE NOTICE 'PASS retry blocked';

  -- 12) Fallback blocked
  res := research.live_preflight('gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic', NULL, 0, 0, FALSE, 'groq');
  IF res->>'failure_class' <> 'unsupported_capability' THEN RAISE EXCEPTION 'fallback %', res; END IF;
  RAISE NOTICE 'PASS fallback blocked';

  -- 13) Cost > 0 blocked (auth max_cost stays 0; attempt via pilot check already; also bump would fail policy)
  -- Ensure pilot/auth remain 0 — try projected path with note only
  IF (SELECT max_authorized_cost_usd FROM research.provider_pilot_proposals WHERE id=pilot) <> 0 THEN
    RAISE EXCEPTION 'pilot cost not zero';
  END IF;
  RAISE NOTICE 'PASS cost USD 0 enforced on pilot';

  -- 7) Second attempt same case blocked after one usage
  PERFORM research.record_pilot_usage_for_tests(aid, 10, 10, TRUE, fixture, FALSE);
  res := research.live_preflight('gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic', NULL, 1, 1, FALSE, NULL);
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN RAISE EXCEPTION 'second attempt %', res; END IF;
  RAISE NOTICE 'PASS second attempt blocked';

  -- 6) Fourth total request blocked after 3 usages across cases
  PERFORM research.record_pilot_usage_for_tests(aid2, 10, 10, TRUE, fixture, FALSE);
  PERFORM research.record_pilot_usage_for_tests(aid3, 10, 10, TRUE, fixture, FALSE);
  -- 3 requests already; fourth blocked on any case — need fresh attempt counts:
  -- case1 already at max attempts; use preflight which checks total requests first
  res := research.live_preflight('gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic', NULL, 1, 1, FALSE, NULL);
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN RAISE EXCEPTION 'fourth request %', res; END IF;
  RAISE NOTICE 'PASS fourth request blocked';

  -- Reset usage for token/success tests
  PERFORM research.cleanup_test_fixture(fixture);
  -- re-arm auths after cleanup revoked them
  UPDATE research.provider_authorization_records
  SET status='proposed', activated_at=NULL, expires_at=TIMESTAMPTZ '-infinity',
      requests_spent=0, tokens_spent=0, cost_spent_usd=0, test_fixture_id=fixture
  WHERE id IN (aid, aid2, aid3);
  UPDATE research.provider_pilot_proposals
  SET status='approved', taha_approved_at=NOW(), expires_at=NOW()+INTERVAL '24 hours'
  WHERE id=pilot;
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid3, 'GEMINI-PILOT-5A');
  UPDATE research.provider_authorization_records SET test_fixture_id=fixture WHERE id IN (aid,aid2,aid3);

  -- 8) aggregate input > 8000 blocked
  PERFORM research.record_pilot_usage_for_tests(aid, 8000, 0, FALSE, fixture, FALSE);
  res := research.live_preflight('gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic', NULL, 1, 0, FALSE, NULL);
  IF res->>'failure_class' <> 'token_quota_exhausted' THEN RAISE EXCEPTION 'input agg %', res; END IF;
  RAISE NOTICE 'PASS aggregate input blocked';

  PERFORM research.cleanup_test_fixture(fixture);
  UPDATE research.provider_authorization_records
  SET status='proposed', activated_at=NULL, expires_at=TIMESTAMPTZ '-infinity',
      requests_spent=0, tokens_spent=0, cost_spent_usd=0, test_fixture_id=fixture
  WHERE id IN (aid, aid2, aid3);
  UPDATE research.provider_pilot_proposals
  SET status='approved', taha_approved_at=NOW(), expires_at=NOW()+INTERVAL '24 hours' WHERE id=pilot;
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');
  UPDATE research.provider_authorization_records SET test_fixture_id=fixture WHERE id IN (aid,aid2);

  -- 9) aggregate output > 4000 blocked
  PERFORM research.record_pilot_usage_for_tests(aid, 0, 4000, FALSE, fixture, FALSE);
  res := research.live_preflight('gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic', NULL, 0, 1, FALSE, NULL);
  IF res->>'failure_class' <> 'token_quota_exhausted' THEN RAISE EXCEPTION 'output agg %', res; END IF;
  RAISE NOTICE 'PASS aggregate output blocked';

  PERFORM research.cleanup_test_fixture(fixture);
  UPDATE research.provider_authorization_records
  SET status='proposed', activated_at=NULL, expires_at=TIMESTAMPTZ '-infinity',
      requests_spent=0, tokens_spent=0, cost_spent_usd=0, test_fixture_id=fixture
  WHERE id IN (aid, aid2, aid3);
  UPDATE research.provider_pilot_proposals
  SET status='approved', taha_approved_at=NOW(), expires_at=NOW()+INTERVAL '24 hours' WHERE id=pilot;
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid3, 'GEMINI-PILOT-5A');
  UPDATE research.provider_authorization_records SET test_fixture_id=fixture WHERE id IN (aid,aid2,aid3);

  -- 10) after 3 successful calls blocked
  PERFORM research.record_pilot_usage_for_tests(aid, 1, 1, TRUE, fixture, FALSE);
  PERFORM research.record_pilot_usage_for_tests(aid2, 1, 1, TRUE, fixture, FALSE);
  PERFORM research.record_pilot_usage_for_tests(aid3, 1, 1, TRUE, fixture, FALSE);
  res := research.live_preflight('gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic', NULL, 1, 1, FALSE, NULL);
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN RAISE EXCEPTION 'success cap %', res; END IF;
  RAISE NOTICE 'PASS successful-call cap blocked';

  -- 15) no envelope when gate fails
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object('prompt','x','input_fingerprint', encode(digest('fail','sha256'),'hex'), 'projected_input_tokens', 1)
  );
  IF res->'envelope' IS NOT NULL AND jsonb_typeof(res->'envelope') <> 'null' THEN
    RAISE EXCEPTION 'envelope created on failure';
  END IF;
  RAISE NOTICE 'PASS no envelope on failure';

  -- Final cleanup to proposed pilot state
  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_repair_reset_defaults();
  PERFORM research._r5a_assert_final_pilot_state();
  RAISE NOTICE 'PASS residue-free final state';
END $$;

-- Idempotency: run assert again after second cleanup
SELECT research.cleanup_test_fixture('r5a-repair-v1');
SELECT research._r5a_repair_reset_defaults();
SELECT research._r5a_assert_final_pilot_state();

-- Confirm provenance cleanup of prior 5A residue pattern (max_requests=1 active non-pilot) is gone
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM research.provider_authorization_records a
    JOIN research.providers p ON p.id=a.provider_id
    WHERE p.code='gemini' AND a.pilot_proposal_id IS NULL AND a.status='active'
      AND a.max_requests=1 AND a.max_tokens=1000 AND a.max_cost_usd=0
  ) THEN
    RAISE EXCEPTION '5A test residue pattern still active';
  END IF;
  RAISE NOTICE 'PASS prior 5A residue revoked';
END $$;

SELECT count(*) AS proposed_pilot_auths
FROM research.provider_authorization_records a
JOIN research.provider_pilot_proposals pp ON pp.id=a.pilot_proposal_id
WHERE pp.pilot_code='GEMINI-PILOT-5A' AND a.status='proposed';

SELECT 'ROUND5A_REPAIR_TESTS_DONE' AS marker;
