-- Round 5A repair tests — superseded for activation/aggregate paths by 008.
-- Retains residue and disabled-state checks only (no production auth activation).
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
END;
$$;

CREATE OR REPLACE FUNCTION research._r5a_assert_final_pilot_state()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE n_prop INT; n_active_test INT;
BEGIN
  SELECT count(*) INTO n_prop
  FROM research.provider_authorization_records a
  JOIN research.provider_pilot_proposals pp ON pp.id = a.pilot_proposal_id
  WHERE pp.pilot_code = 'GEMINI-PILOT-5A' AND a.status = 'proposed' AND a.test_fixture_id IS NULL;
  IF n_prop <> 3 THEN
    RAISE EXCEPTION 'expected exactly 3 proposed pilot auths, got %', n_prop;
  END IF;
  SELECT count(*) INTO n_active_test
  FROM research.provider_authorization_records a
  JOIN research.providers p ON p.id = a.provider_id
  WHERE p.code = 'gemini' AND a.status = 'active';
  IF n_active_test <> 0 THEN
    RAISE EXCEPTION 'active gemini auths remain: %', n_active_test;
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
  aid UUID;
  case1 UUID;
  mcode TEXT;
  res JSONB;
  pilot UUID;
BEGIN
  PERFORM research._r5a_repair_reset_defaults();

  SELECT id INTO pilot FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A';
  SELECT benchmark_case_ids[1] INTO case1 FROM research.provider_pilot_proposals WHERE id = pilot;
  SELECT m.model_id_provisional INTO mcode
  FROM research.provider_model_candidates m
  JOIN research.providers p ON p.id=m.provider_id WHERE p.code='gemini' AND m.model_id_provisional='gemini-2.5-flash';
  SELECT id INTO aid FROM research.provider_authorization_records
  WHERE pilot_proposal_id = pilot AND benchmark_case_id = case1 AND status='proposed' AND test_fixture_id IS NULL;

  IF (SELECT expires_at FROM research.provider_authorization_records WHERE id=aid) <> TIMESTAMPTZ '-infinity' THEN
    RAISE EXCEPTION 'proposed auth must use -infinity expiry';
  END IF;

  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','x','input_fingerprint', encode(digest('p1','sha256'),'hex'),
      'idempotency_key', 'r5a-repair-smoke-1'
    )
  );
  IF res->>'failure_class' <> 'provider_disabled' THEN
    RAISE EXCEPTION 'proposed/disabled should block envelope: %', res;
  END IF;

  -- Direct activation of production shell must fail closed
  BEGIN
    UPDATE research.provider_authorization_records SET status='active' WHERE id=aid;
    RAISE EXCEPTION 'direct activation should fail';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%activate_pilot_authorization%' THEN
      RAISE EXCEPTION 'unexpected: %', SQLERRM;
    END IF;
  END;

  PERFORM research._r5a_assert_final_pilot_state();
  RAISE NOTICE 'PASS 007 residue/disabled smoke (superseded by 008 for full suite)';
END $$;

SELECT research._r5a_repair_reset_defaults();
SELECT research._r5a_assert_final_pilot_state();

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
END $$;

SELECT 'ROUND5A_REPAIR_TESTS_DONE' AS marker;
