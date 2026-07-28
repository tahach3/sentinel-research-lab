-- Concurrent final-slot contention for Round 5A final repair (run from two sessions).
-- Expect: exactly one ok=true across both sessions when competing for the last request slot.
\set ON_ERROR_STOP on

DO $$
DECLARE
  fixture TEXT := 'r5a-final-concurrent';
  pilot UUID; pid UUID; mid UUID; mcode TEXT;
  case1 UUID; case2 UUID; case3 UUID;
  aid1 UUID; aid2 UUID; aid3 UUID;
  res JSONB;
BEGIN
  -- Session A prepares shared state once (idempotent if B races — use advisory lock)
  PERFORM pg_advisory_lock(850008);
  IF NOT EXISTS (
    SELECT 1 FROM research.provider_authorization_records
    WHERE test_fixture_id = fixture AND status = 'active'
    LIMIT 1
  ) THEN
    PERFORM research.cleanup_test_fixture(fixture);
    PERFORM research._r5a_final_arm_gates();
    SELECT id INTO pilot FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A';
    SELECT benchmark_case_ids[1], benchmark_case_ids[2], benchmark_case_ids[3]
      INTO case1, case2, case3 FROM research.provider_pilot_proposals WHERE id=pilot;
    SELECT p.id, m.id, m.model_id_provisional INTO pid, mid, mcode
    FROM research.providers p
    JOIN research.provider_model_candidates m ON m.provider_id=p.id
    WHERE p.code='gemini' AND m.model_id_provisional='gemini-2.5-flash';

    aid1 := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
    aid2 := research._r5a_insert_fixture_auth(fixture, pilot, case2, pid, mid);
    aid3 := research._r5a_insert_fixture_auth(fixture, pilot, case3, pid, mid);
    PERFORM research.activate_pilot_authorization(aid1, 'GEMINI-PILOT-5A');
    PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');
    PERFORM research.activate_pilot_authorization(aid3, 'GEMINI-PILOT-5A');

    -- Consume two of three request slots
    res := research.build_provider_request_envelope(
      'gemini', mcode, case1, aid1, 'researcher', 'public_or_synthetic',
      jsonb_build_object(
        'prompt','pre1','input_fingerprint', encode(digest('pre1','sha256'),'hex'),
        'projected_input_tokens', 1, 'projected_output_tokens', 1,
        'idempotency_key', fixture || '-pre1'
      )
    );
    IF NOT COALESCE((res->>'ok')::boolean, false) THEN
      RAISE EXCEPTION 'prefill1 failed: %', res;
    END IF;
    res := research.build_provider_request_envelope(
      'gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic',
      jsonb_build_object(
        'prompt','pre2','input_fingerprint', encode(digest('pre2','sha256'),'hex'),
        'projected_input_tokens', 1, 'projected_output_tokens', 1,
        'idempotency_key', fixture || '-pre2'
      )
    );
    IF NOT COALESCE((res->>'ok')::boolean, false) THEN
      RAISE EXCEPTION 'prefill2 failed: %', res;
    END IF;
  END IF;
  PERFORM pg_advisory_unlock(850008);
END $$;
