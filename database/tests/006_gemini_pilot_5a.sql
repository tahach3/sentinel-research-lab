-- Round 5A gate tests (residue-free revision)
\set ON_ERROR_STOP on

DO $$
DECLARE
  fixture TEXT := 'r5a-original-gates-v1';
  mid UUID; aid UUID; case_id UUID; case2 UUID; res JSONB; mcode TEXT; pid UUID;
BEGIN
  PERFORM research.cleanup_test_fixture(fixture);

  IF NOT EXISTS (
    SELECT 1 FROM research.provider_policy_verifications v
    JOIN research.providers p ON p.id = v.provider_id
    WHERE p.code = 'gemini' AND v.model_identifier = 'gemini-2.5-flash'
      AND v.free_tier_available AND v.pakistan_available AND NOT v.blocked_provider_policy
  ) THEN RAISE EXCEPTION 'policy verification missing'; END IF;

  IF (SELECT benchmark_case_codes FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A')
     IS DISTINCT FROM ARRAY['R-N-01','R-A-01','R-X-01']::text[] THEN
    RAISE EXCEPTION 'case selection mismatch';
  END IF;

  IF (SELECT count(*) FROM research.provider_authorization_records a
      JOIN research.provider_pilot_proposals pp ON pp.id=a.pilot_proposal_id
      WHERE pp.pilot_code='GEMINI-PILOT-5A' AND a.status='proposed' AND a.max_cost_usd=0) <> 3 THEN
    RAISE EXCEPTION 'expected 3 proposed USD0 auths';
  END IF;

  SELECT id INTO pid FROM research.providers WHERE code='gemini';
  SELECT id, model_id_provisional INTO mid, mcode FROM research.provider_model_candidates WHERE provider_id=pid;
  SELECT benchmark_case_ids[1], benchmark_case_ids[2] INTO case_id, case2
  FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A';
  SELECT id INTO aid FROM research.provider_authorization_records
  WHERE pilot_proposal_id=(SELECT id FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A')
    AND benchmark_case_id=case_id AND status='proposed' LIMIT 1;

  IF EXISTS (SELECT 1 FROM research.providers WHERE code='gemini' AND enabled) THEN RAISE EXCEPTION 'provider enabled'; END IF;
  res := research.build_provider_request_envelope(
    'gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic',
    jsonb_build_object('prompt','no','input_fingerprint', encode(digest('5a','sha256'),'hex'))
  );
  IF res->>'failure_class' <> 'provider_disabled' THEN RAISE EXCEPTION 'envelope %', res; END IF;

  -- Temporary arm for expired/wrong-case/confidential using fixture-tagged auth only
  UPDATE research.providers SET enabled=TRUE WHERE id=pid;
  UPDATE research.provider_model_candidates
  SET enabled=TRUE, verification_status='verified', free_tier_status='free_confirmed' WHERE id=mid;
  UPDATE research.provider_credential_status SET status='present', n8n_credential_label='local-n8n-label-only' WHERE provider_id=pid;
  UPDATE research.provider_budget_policies SET daily_request_cap=10, daily_token_cap=10000 WHERE provider_id=pid;

  INSERT INTO research.provider_authorization_records (
    provider_id, model_candidate_id, benchmark_case_id, max_requests, max_tokens, max_cost_usd,
    expires_at, approving_authority, status, test_fixture_id
  ) VALUES (
    pid, mid, case_id, 1, 1000, 0, TIMESTAMPTZ '-infinity', 'Taha', 'proposed', fixture
  ) RETURNING id INTO aid;

  UPDATE research.provider_authorization_records
  SET status='active'
  WHERE id=aid;
  UPDATE research.provider_authorization_records
  SET activated_at=NOW()-INTERVAL '25 hours', expires_at=NOW()-INTERVAL '1 hour'
  WHERE id=aid;

  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_expired' THEN RAISE EXCEPTION 'expired %', res; END IF;

  UPDATE research.provider_authorization_records
  SET activated_at=NOW(), expires_at=NOW()+INTERVAL '24 hours', status='active'
  WHERE id=aid;
  res := research.live_preflight('gemini', mcode, case2, aid, 'researcher', 'public_or_synthetic');
  IF res->>'failure_class' <> 'authorization_mismatch' THEN RAISE EXCEPTION 'wrong-case %', res; END IF;

  res := research.live_preflight('gemini', mcode, case_id, aid, 'researcher', 'restricted');
  IF res->>'failure_class' <> 'confidentiality_blocked' THEN RAISE EXCEPTION 'confidential %', res; END IF;

  PERFORM research.cleanup_test_fixture(fixture);
  UPDATE research.providers SET enabled=FALSE WHERE id=pid;
  UPDATE research.provider_model_candidates SET enabled=FALSE WHERE id=mid;
  UPDATE research.provider_credential_status SET status='missing', n8n_credential_label=NULL WHERE provider_id=pid;
  UPDATE research.provider_budget_policies
  SET daily_request_cap=0, daily_token_cap=0, free_only=TRUE, paid_fallback=FALSE,
      paid_usage_authorized=FALSE, daily_cost_limit_usd=0, monthly_cost_ceiling_usd=0
  WHERE provider_id=pid;

  IF EXISTS (
    SELECT 1 FROM research.provider_authorization_records WHERE test_fixture_id=fixture AND status='active'
  ) THEN RAISE EXCEPTION 'fixture auth still active'; END IF;

  RAISE NOTICE 'PASS round5a gates residue-free';
END $$;

SELECT 'ROUND5A_TESTS_DONE' AS marker;
