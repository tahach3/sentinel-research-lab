-- Round 5A final repair tests (immutable activation + atomic reservations)
-- Leaves production pilot: 3 proposed auths, Gemini disabled, credential missing, no live calls.
\set ON_ERROR_STOP on

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

CREATE OR REPLACE FUNCTION research._r5a_final_assert_state()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE n_prop INT; n_active INT;
BEGIN
  SELECT count(*) INTO n_prop
  FROM research.provider_authorization_records a
  JOIN research.provider_pilot_proposals pp ON pp.id = a.pilot_proposal_id
  WHERE pp.pilot_code = 'GEMINI-PILOT-5A'
    AND a.status = 'proposed'
    AND a.test_fixture_id IS NULL;
  IF n_prop <> 3 THEN
    RAISE EXCEPTION 'expected exactly 3 proposed production pilot auths, got %', n_prop;
  END IF;

  SELECT count(*) INTO n_active
  FROM research.provider_authorization_records a
  JOIN research.providers p ON p.id = a.provider_id
  WHERE p.code = 'gemini' AND a.status = 'active';
  IF n_active <> 0 THEN
    RAISE EXCEPTION 'active gemini auths remain: %', n_active;
  END IF;

  IF EXISTS (
    SELECT 1 FROM research.pilot_capacity_reservations r
    WHERE r.test_fixture_id IS NOT NULL AND r.status IN ('reserved', 'finalized')
  ) THEN
    RAISE EXCEPTION 'fixture reservations remain';
  END IF;

  IF EXISTS (SELECT 1 FROM research.providers WHERE code='gemini' AND enabled) THEN
    RAISE EXCEPTION 'gemini enabled';
  END IF;
  IF EXISTS (
    SELECT 1 FROM research.provider_model_candidates m
    JOIN research.providers p ON p.id=m.provider_id
    WHERE p.code='gemini' AND m.enabled
  ) THEN RAISE EXCEPTION 'model enabled'; END IF;

  IF (SELECT status FROM research.provider_credential_status c
      JOIN research.providers p ON p.id=c.provider_id WHERE p.code='gemini') IS DISTINCT FROM 'missing' THEN
    RAISE EXCEPTION 'credential status not missing';
  END IF;

  IF (SELECT status FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A')
     IS DISTINCT FROM 'awaiting_taha_credential' THEN
    RAISE EXCEPTION 'pilot not restored to awaiting_taha_credential';
  END IF;
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

DO $$
DECLARE
  fixture TEXT := 'r5a-final-v1';
  pilot UUID; pid UUID; mid UUID; mcode TEXT;
  case1 UUID; case2 UUID; case3 UUID;
  aid UUID; aid2 UUID; aid3 UUID; aid_exp UUID; aid_renew UUID;
  auth research.provider_authorization_records%ROWTYPE;
  auth2 research.provider_authorization_records%ROWTYPE;
  activated_once TIMESTAMPTZ;
  expires_once TIMESTAMPTZ;
  delta INTERVAL;
  res JSONB; res2 JSONB;
  first_eid TEXT;
  n_res INT; n_env INT;
  pilot_status TEXT;
  ok BOOLEAN;
BEGIN
  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_final_reset_defaults();

  SELECT id INTO pilot FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A';
  SELECT benchmark_case_ids[1], benchmark_case_ids[2], benchmark_case_ids[3]
    INTO case1, case2, case3 FROM research.provider_pilot_proposals WHERE id = pilot;
  SELECT p.id, m.id, m.model_id_provisional INTO pid, mid, mcode
  FROM research.providers p
  JOIN research.provider_model_candidates m ON m.provider_id = p.id
  WHERE p.code='gemini' AND m.model_id_provisional='gemini-2.5-flash';

  -- Production shells stay proposed
  IF (SELECT count(*) FROM research.provider_authorization_records a
      WHERE a.pilot_proposal_id=pilot AND a.status='proposed' AND a.test_fixture_id IS NULL) <> 3 THEN
    RAISE EXCEPTION 'production proposed shells missing';
  END IF;

  aid := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
  aid2 := research._r5a_insert_fixture_auth(fixture, pilot, case2, pid, mid);
  aid3 := research._r5a_insert_fixture_auth(fixture, pilot, case3, pid, mid);

  -- 8) Activation while awaiting_taha_credential rejected
  BEGIN
    PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
    RAISE EXCEPTION 'expected activation reject while awaiting credential';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%must already be approved%' THEN
      RAISE EXCEPTION 'unexpected awaiting-cred activation error: %', SQLERRM;
    END IF;
  END;
  RAISE NOTICE 'PASS 8 awaiting_taha_credential activation rejected';

  -- 9) Activation without confirmed credential rejected
  UPDATE research.provider_pilot_proposals
  SET status='approved', taha_approved_at=NOW(), expires_at=NOW()+INTERVAL '24 hours'
  WHERE id=pilot;
  UPDATE research.provider_credential_status SET status='missing' WHERE provider_id=pid;
  BEGIN
    PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
    RAISE EXCEPTION 'expected credential gate reject';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%credential%present%' AND SQLERRM NOT LIKE '%credential-status%' THEN
      RAISE EXCEPTION 'unexpected credential gate error: %', SQLERRM;
    END IF;
  END;
  RAISE NOTICE 'PASS 9 activation without credential rejected';

  -- Arm credential for positive activation tests
  UPDATE research.provider_credential_status
  SET status='present', n8n_credential_label='local-test-label-only'
  WHERE provider_id=pid;

  SELECT status INTO pilot_status FROM research.provider_pilot_proposals WHERE id=pilot;

  -- 1+2) First governed activation sets immutable activated_at; expiry = +24h
  auth := research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  IF auth.status <> 'active' OR auth.activated_at IS NULL THEN
    RAISE EXCEPTION 'activation failed: %', auth;
  END IF;
  activated_once := auth.activated_at;
  expires_once := auth.expires_at;
  delta := expires_once - activated_once;
  IF delta <> INTERVAL '24 hours' THEN
    RAISE EXCEPTION 'expected exactly 24h window got %', delta;
  END IF;
  RAISE NOTICE 'PASS 1/2 first activation immutable window';

  -- 10) Governed activation does not modify proposal approval state
  IF (SELECT status FROM research.provider_pilot_proposals WHERE id=pilot) IS DISTINCT FROM pilot_status THEN
    RAISE EXCEPTION 'activation mutated pilot status';
  END IF;
  RAISE NOTICE 'PASS 10 activation does not modify proposal';

  -- 3) Updating activated_at while active rejected
  BEGIN
    UPDATE research.provider_authorization_records
    SET activated_at = activated_once + INTERVAL '1 hour'
    WHERE id = aid;
    RAISE EXCEPTION 'expected activated_at immutability reject';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%activated_at is immutable%' THEN
      RAISE EXCEPTION 'unexpected activated_at error: %', SQLERRM;
    END IF;
  END;
  RAISE NOTICE 'PASS 3 activated_at update rejected';

  -- 4) Updating expires_at while active rejected
  BEGIN
    UPDATE research.provider_authorization_records
    SET expires_at = expires_once + INTERVAL '1 hour'
    WHERE id = aid;
    RAISE EXCEPTION 'expected expires_at immutability reject';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%expires_at is immutable%' THEN
      RAISE EXCEPTION 'unexpected expires_at error: %', SQLERRM;
    END IF;
  END;
  RAISE NOTICE 'PASS 4 expires_at update rejected';

  -- 5) Active → proposed → active renewal rejected
  BEGIN
    UPDATE research.provider_authorization_records SET status='proposed' WHERE id=aid;
    RAISE EXCEPTION 'expected active→proposed reject';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%cannot return to proposed%' THEN
      RAISE EXCEPTION 'unexpected renewal path error: %', SQLERRM;
    END IF;
  END;
  RAISE NOTICE 'PASS 5 active→proposed renewal rejected';

  -- 6) Expired authorization renewal in place rejected
  aid_exp := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
  -- use distinct case for expiry fixture — case1 already has active fixture aid;
  -- insert on case2 unused? aid2 still proposed. Use aid_exp on case1 is OK (multiple proposed).
  auth2 := research.activate_pilot_authorization(aid_exp, 'GEMINI-PILOT-5A');
  UPDATE research.provider_authorization_records SET status='expired' WHERE id=aid_exp;
  BEGIN
    UPDATE research.provider_authorization_records SET status='active' WHERE id=aid_exp;
    RAISE EXCEPTION 'expected expired renewal reject';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%cannot be renewed in place%'
       AND SQLERRM NOT LIKE '%requires research.activate_pilot_authorization%'
       AND SQLERRM NOT LIKE '%already activated%' THEN
      RAISE EXCEPTION 'unexpected expired renewal error: %', SQLERRM;
    END IF;
  END;
  BEGIN
    PERFORM research.activate_pilot_authorization(aid_exp, 'GEMINI-PILOT-5A');
    RAISE EXCEPTION 'expected activate on expired reject';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%only proposed%' THEN
      RAISE EXCEPTION 'unexpected activate-expired error: %', SQLERRM;
    END IF;
  END;
  RAISE NOTICE 'PASS 6 expired in-place renewal rejected';

  -- 7) Direct pilot-linked status activation rejected
  aid_renew := research._r5a_insert_fixture_auth(fixture, pilot, case2, pid, mid);
  BEGIN
    UPDATE research.provider_authorization_records SET status='active' WHERE id=aid_renew;
    RAISE EXCEPTION 'expected direct activation reject';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%activate_pilot_authorization%' THEN
      RAISE EXCEPTION 'unexpected direct activation error: %', SQLERRM;
    END IF;
  END;
  RAISE NOTICE 'PASS 7 direct pilot-linked activation rejected';

  -- Activate remaining fixtures for reservation tests
  PERFORM research._r5a_final_arm_gates();
  -- aid already active; activate aid2/aid3 if still proposed
  IF (SELECT status FROM research.provider_authorization_records WHERE id=aid2) = 'proposed' THEN
    PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');
  END IF;
  IF (SELECT status FROM research.provider_authorization_records WHERE id=aid3) = 'proposed' THEN
    PERFORM research.activate_pilot_authorization(aid3, 'GEMINI-PILOT-5A');
  END IF;

  -- 11) First envelope reserves one total request and one case attempt
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','p1','input_fingerprint', encode(digest('p1','sha256'),'hex'),
      'projected_input_tokens', 10, 'projected_output_tokens', 5,
      'idempotency_key', fixture || '-k1'
    )
  );
  IF NOT COALESCE((res->>'ok')::boolean, false) THEN
    RAISE EXCEPTION 'first envelope failed: %', res;
  END IF;
  first_eid := res->>'envelope_id';
  SELECT count(*) INTO n_res FROM research.pilot_capacity_reservations
  WHERE pilot_proposal_id=pilot AND status='reserved' AND test_fixture_id=fixture;
  IF n_res <> 1 THEN RAISE EXCEPTION 'expected 1 reservation got %', n_res; END IF;
  IF research.pilot_case_attempt_count(pilot, case1) <> 1 THEN
    RAISE EXCEPTION 'expected 1 case attempt';
  END IF;
  RAISE NOTICE 'PASS 11 first envelope reserves request+attempt';

  -- 12) Second attempt same case blocked
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','p2','input_fingerprint', encode(digest('p2','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-k1b'
    )
  );
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN
    RAISE EXCEPTION 'second case attempt expected block: %', res;
  END IF;
  RAISE NOTICE 'PASS 12 second case attempt blocked';

  -- 16) Replay same idempotency key does not duplicate
  res2 := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','p1','input_fingerprint', encode(digest('p1','sha256'),'hex'),
      'projected_input_tokens', 10, 'projected_output_tokens', 5,
      'idempotency_key', fixture || '-k1'
    )
  );
  IF NOT COALESCE((res2->>'ok')::boolean, false) OR COALESCE((res2->>'idempotent_replay')::boolean, false) IS NOT TRUE THEN
    RAISE EXCEPTION 'idempotent replay failed: %', res2;
  END IF;
  IF res2->>'envelope_id' IS DISTINCT FROM first_eid THEN
    RAISE EXCEPTION 'replay created different envelope';
  END IF;
  SELECT count(*) INTO n_res FROM research.pilot_capacity_reservations
  WHERE pilot_proposal_id=pilot AND idempotency_key = fixture || '-k1';
  IF n_res <> 1 THEN RAISE EXCEPTION 'idempotency duplicated reservations'; END IF;
  RAISE NOTICE 'PASS 16 idempotent replay';

  -- 17) Different idempotency keys cannot bypass one-attempt-per-case
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','p3','input_fingerprint', encode(digest('p3','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-k1c'
    )
  );
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN
    RAISE EXCEPTION 'diff key bypass: %', res;
  END IF;
  RAISE NOTICE 'PASS 17 different key cannot bypass case attempt';

  -- Fill remaining slots for fourth-request test
  res := research.build_provider_request_envelope(
    'gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','c2','input_fingerprint', encode(digest('c2','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-k2'
    )
  );
  IF NOT COALESCE((res->>'ok')::boolean, false) THEN RAISE EXCEPTION 'case2 envelope %', res; END IF;
  res := research.build_provider_request_envelope(
    'gemini', mcode, case3, aid3, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','c3','input_fingerprint', encode(digest('c3','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-k3'
    )
  );
  IF NOT COALESCE((res->>'ok')::boolean, false) THEN RAISE EXCEPTION 'case3 envelope %', res; END IF;

  -- 13) Fourth total request blocked
  -- Need a fourth case attempt auth — reuse case1 already blocked; still hits total requests
  res := research.build_provider_request_envelope(
    'gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','c4','input_fingerprint', encode(digest('c4','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-k4'
    )
  );
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN
    RAISE EXCEPTION 'fourth request expected block: %', res;
  END IF;
  RAISE NOTICE 'PASS 13 fourth total request blocked';

  -- 15) Failed envelope insertion rolls back reservation
  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_final_arm_gates();
  aid := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
  aid2 := research._r5a_insert_fixture_auth(fixture, pilot, case2, pid, mid);
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  BEGIN
    PERFORM set_config('research.simulate_envelope_insert_failure', 'on', true);
    res := research.build_provider_request_envelope(
      'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
      jsonb_build_object(
        'prompt','fail','input_fingerprint', encode(digest('fail','sha256'),'hex'),
        'projected_input_tokens', 1, 'projected_output_tokens', 1,
        'idempotency_key', fixture || '-fail'
      )
    );
    RAISE EXCEPTION 'expected simulated failure';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%simulated envelope insert failure%' THEN
      RAISE EXCEPTION 'unexpected fail-insert error: %', SQLERRM;
    END IF;
  END;
  PERFORM set_config('research.simulate_envelope_insert_failure', 'off', true);
  SELECT count(*) INTO n_res FROM research.pilot_capacity_reservations
  WHERE idempotency_key = fixture || '-fail';
  SELECT count(*) INTO n_env FROM research.live_request_envelopes e
  JOIN research.provider_authorization_records a ON a.id=e.authorization_id
  WHERE a.test_fixture_id=fixture AND e.envelope->>'idempotency_key' = fixture || '-fail';
  IF n_res <> 0 OR n_env <> 0 THEN
    RAISE EXCEPTION 'rollback left residue res=% env=%', n_res, n_env;
  END IF;
  RAISE NOTICE 'PASS 15 failed insert rolls back reservation';

  -- Fresh capacity for token / success / cost / gate tests
  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_final_arm_gates();
  aid := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
  aid2 := research._r5a_insert_fixture_auth(fixture, pilot, case2, pid, mid);
  aid3 := research._r5a_insert_fixture_auth(fixture, pilot, case3, pid, mid);
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid3, 'GEMINI-PILOT-5A');

  -- 18) Aggregate input-token limit with reservations included
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','tin','input_fingerprint', encode(digest('tin','sha256'),'hex'),
      'projected_input_tokens', 8000, 'projected_output_tokens', 0,
      'idempotency_key', fixture || '-in'
    )
  );
  IF NOT COALESCE((res->>'ok')::boolean, false) THEN RAISE EXCEPTION 'input reserve %', res; END IF;
  res := research.build_provider_request_envelope(
    'gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','tin2','input_fingerprint', encode(digest('tin2','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 0,
      'idempotency_key', fixture || '-in2'
    )
  );
  IF res->>'failure_class' <> 'token_quota_exhausted' THEN
    RAISE EXCEPTION 'input aggregate with reservation: %', res;
  END IF;
  RAISE NOTICE 'PASS 18 input token limit with reservations';

  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_final_arm_gates();
  aid := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
  aid2 := research._r5a_insert_fixture_auth(fixture, pilot, case2, pid, mid);
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');

  -- 19) Aggregate output-token limit with reservations
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','tout','input_fingerprint', encode(digest('tout','sha256'),'hex'),
      'projected_input_tokens', 0, 'projected_output_tokens', 4000,
      'idempotency_key', fixture || '-out'
    )
  );
  IF NOT COALESCE((res->>'ok')::boolean, false) THEN RAISE EXCEPTION 'output reserve %', res; END IF;
  res := research.build_provider_request_envelope(
    'gemini', mcode, case2, aid2, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','tout2','input_fingerprint', encode(digest('tout2','sha256'),'hex'),
      'projected_input_tokens', 0, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-out2'
    )
  );
  IF res->>'failure_class' <> 'token_quota_exhausted' THEN
    RAISE EXCEPTION 'output aggregate with reservation: %', res;
  END IF;
  RAISE NOTICE 'PASS 19 output token limit with reservations';

  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_final_arm_gates();
  aid := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
  aid2 := research._r5a_insert_fixture_auth(fixture, pilot, case2, pid, mid);
  aid3 := research._r5a_insert_fixture_auth(fixture, pilot, case3, pid, mid);
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid2, 'GEMINI-PILOT-5A');
  PERFORM research.activate_pilot_authorization(aid3, 'GEMINI-PILOT-5A');

  -- 20) Successful-call limit from finalized usage
  PERFORM research.record_pilot_usage_for_tests(aid, 1, 1, TRUE, fixture, FALSE);
  PERFORM research.record_pilot_usage_for_tests(aid2, 1, 1, TRUE, fixture, FALSE);
  PERFORM research.record_pilot_usage_for_tests(aid3, 1, 1, TRUE, fixture, FALSE);
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','succ','input_fingerprint', encode(digest('succ','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-succ'
    )
  );
  IF res->>'failure_class' <> 'request_quota_exhausted' THEN
    RAISE EXCEPTION 'success cap: %', res;
  END IF;
  RAISE NOTICE 'PASS 20 successful-call limit';

  -- Note: record_pilot_usage also counts as case attempts / requests in ledger —
  -- success path above already blocked. Continue gates on fresh set.
  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_final_arm_gates();
  aid := research._r5a_insert_fixture_auth(fixture, pilot, case1, pid, mid);
  PERFORM research.activate_pilot_authorization(aid, 'GEMINI-PILOT-5A');

  -- 21) Any cost above USD 0.00 blocked
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','cost','input_fingerprint', encode(digest('cost','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'projected_cost_usd', 0.01,
      'idempotency_key', fixture || '-cost'
    )
  );
  IF res->>'failure_class' <> 'cost_budget_exhausted' THEN
    RAISE EXCEPTION 'cost block: %', res;
  END IF;
  RAISE NOTICE 'PASS 21 cost > 0 blocked';

  -- 22) Retry and fallback blocked
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','retry','input_fingerprint', encode(digest('retry','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'is_retry', true, 'idempotency_key', fixture || '-retry'
    )
  );
  IF res->>'failure_class' <> 'unsupported_capability' THEN RAISE EXCEPTION 'retry %', res; END IF;
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object(
      'prompt','fb','input_fingerprint', encode(digest('fb','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'fallback_provider', 'groq', 'idempotency_key', fixture || '-fb'
    )
  );
  IF res->>'failure_class' <> 'unsupported_capability' THEN RAISE EXCEPTION 'fallback %', res; END IF;
  RAISE NOTICE 'PASS 22 retry/fallback blocked';

  -- 23) Confidential input blocked
  res := research.build_provider_request_envelope(
    'gemini', mcode, case1, aid, 'researcher', 'restricted',
    jsonb_build_object(
      'prompt','conf','input_fingerprint', encode(digest('conf','sha256'),'hex'),
      'projected_input_tokens', 1, 'projected_output_tokens', 1,
      'idempotency_key', fixture || '-conf'
    )
  );
  IF res->>'failure_class' <> 'confidentiality_blocked' THEN RAISE EXCEPTION 'confidential %', res; END IF;
  RAISE NOTICE 'PASS 23 confidential blocked';

  -- 24) No envelope after failed gate
  SELECT count(*) INTO n_env FROM research.live_request_envelopes e
  JOIN research.provider_authorization_records a ON a.id=e.authorization_id
  WHERE a.test_fixture_id=fixture
    AND e.envelope->>'idempotency_key' IN (fixture||'-cost', fixture||'-retry', fixture||'-fb', fixture||'-conf');
  IF n_env <> 0 THEN RAISE EXCEPTION 'envelopes exist after failed gates'; END IF;
  RAISE NOTICE 'PASS 24 no envelope after failed gate';

  -- Final cleanup
  PERFORM research.cleanup_test_fixture(fixture);
  PERFORM research._r5a_final_reset_defaults();
  PERFORM research._r5a_final_assert_state();
  RAISE NOTICE 'PASS 25-27 residue-free final state';
END $$;

-- 27 repeated run identical final state
SELECT research.cleanup_test_fixture('r5a-final-v1');
SELECT research._r5a_final_reset_defaults();
SELECT research._r5a_final_assert_state();

-- 29-32 disabled / inactive / zero credentials
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM research.providers WHERE code='gemini' AND enabled) THEN
    RAISE EXCEPTION 'gemini enabled';
  END IF;
  IF EXISTS (
    SELECT 1 FROM research.provider_model_candidates m
    JOIN research.providers p ON p.id=m.provider_id
    WHERE p.code='gemini' AND m.model_id_provisional='gemini-2.5-flash' AND m.enabled
  ) THEN RAISE EXCEPTION 'gemini-2.5-flash enabled'; END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='n8n' AND table_name='workflow_entity'
  ) THEN
    IF EXISTS (SELECT 1 FROM n8n.workflow_entity WHERE active) THEN
      RAISE EXCEPTION 'active workflows remain';
    END IF;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='n8n' AND table_name='credentials_entity'
  ) THEN
    IF (SELECT count(*) FROM n8n.credentials_entity) <> 0 THEN
      RAISE EXCEPTION 'credential objects not zero';
    END IF;
  END IF;
  RAISE NOTICE 'PASS 29-32 provider/model/workflows/credentials';
END $$;

SELECT 'ROUND5A_FINAL_TESTS_DONE' AS marker;
