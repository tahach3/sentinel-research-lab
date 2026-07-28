-- One competing attempt for the final pilot request slot.
-- Usage: pass unique idempotency suffix via -v suffix=a|b
\set ON_ERROR_STOP on

SELECT research.build_provider_request_envelope(
  'gemini',
  (SELECT m.model_id_provisional FROM research.provider_model_candidates m
   JOIN research.providers p ON p.id=m.provider_id
   WHERE p.code='gemini' AND m.model_id_provisional='gemini-2.5-flash'),
  (SELECT benchmark_case_ids[3] FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A'),
  (SELECT a.id FROM research.provider_authorization_records a
   JOIN research.provider_pilot_proposals pp ON pp.id=a.pilot_proposal_id
   WHERE pp.pilot_code='GEMINI-PILOT-5A'
     AND a.test_fixture_id='r5a-final-concurrent'
     AND a.benchmark_case_id = (SELECT benchmark_case_ids[3] FROM research.provider_pilot_proposals WHERE pilot_code='GEMINI-PILOT-5A')
     AND a.status='active'
   ORDER BY a.created_at DESC LIMIT 1),
  'researcher',
  'public_or_synthetic',
  jsonb_build_object(
    'prompt', 'concurrent-' || :'suffix',
    'input_fingerprint', encode(digest('concurrent-' || :'suffix', 'sha256'), 'hex'),
    'projected_input_tokens', 1,
    'projected_output_tokens', 1,
    'idempotency_key', 'r5a-final-concurrent-slot-' || :'suffix'
  )
) AS result;
