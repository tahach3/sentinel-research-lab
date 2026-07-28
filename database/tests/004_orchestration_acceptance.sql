-- Round 3 orchestration acceptance paths (synthetic only; no Taha decision writes)
\set ON_ERROR_STOP on

CREATE OR REPLACE FUNCTION research._r3_clone_question(p_code TEXT, p_scenario TEXT)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  src UUID;
  qid UUID;
  fp TEXT;
BEGIN
  SELECT id INTO src FROM research.research_questions WHERE question_id = 'RQ-2026-R3-001';
  fp := encode(digest(p_code || p_scenario || random()::text, 'sha256'), 'hex');
  INSERT INTO research.research_questions (
    question_id, title, precise_question, question_class, source_trigger,
    expected_decision, status, duplicate_fingerprint, confidentiality_class
  )
  SELECT
    p_code,
    title || ' [' || p_code || ']',
    precise_question,
    question_class,
    source_trigger,
    expected_decision,
    'approved_for_research',
    fp,
    confidentiality_class
  FROM research.research_questions WHERE id = src
  RETURNING id INTO qid;

  INSERT INTO research.evidence_claim_links (evidence_id, question_id, claim_text, stance)
  SELECT evidence_id, qid, claim_text, stance
  FROM research.evidence_claim_links WHERE question_id = src;

  RETURN qid;
END;
$$;

CREATE OR REPLACE FUNCTION research._r3_new_run(p_code TEXT, p_qid UUID, p_scenario TEXT, p_budget NUMERIC DEFAULT 1.0)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  rid UUID;
BEGIN
  INSERT INTO research.research_runs (run_code, question_uuid, scenario_mode, budget_remaining_usd, cost_ceiling_usd)
  VALUES (p_code, p_qid, p_scenario, p_budget, GREATEST(p_budget, 0.000001))
  RETURNING id INTO rid;
  RETURN rid;
END;
$$;

-- 1) Complete successful pipeline
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT; card JSONB;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P1', 'success');
  rid := research._r3_new_run('RUN-R3-P1', qid, 'success');
  res := research.orchestrate_research_run(rid);
  IF res <> 'decision_ready' THEN RAISE EXCEPTION 'P1 FAIL: got %', res; END IF;
  SELECT decision_card INTO card FROM research.research_runs WHERE id = rid;
  IF card IS NULL OR NOT (card ? 'decision_options') THEN
    RAISE EXCEPTION 'P1 FAIL: decision card missing';
  END IF;
  IF EXISTS (SELECT 1 FROM research.taha_decisions d
             JOIN research.improvement_proposals p ON p.id = d.proposal_id
             WHERE p.question_id = qid) THEN
    RAISE EXCEPTION 'P1 FAIL: Taha decision was recorded (forbidden in simulation)';
  END IF;
  IF research.mock_provider_for_stage('qa_checker') =
     research.mock_provider_for_stage('independent_reviewer') THEN
    RAISE EXCEPTION 'P1 FAIL: QA and reviewer providers must differ';
  END IF;
  RAISE NOTICE 'PASS P1 success pipeline';
END $$;

-- 2) Unsupported claim blocked before proposal
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P2', 'unsupported_claim');
  rid := research._r3_new_run('RUN-R3-P2', qid, 'unsupported_claim');
  res := research.orchestrate_research_run(rid);
  IF res <> 'failed' THEN RAISE EXCEPTION 'P2 FAIL: expected failed got %', res; END IF;
  IF EXISTS (SELECT 1 FROM research.improvement_proposals WHERE question_id = qid) THEN
    RAISE EXCEPTION 'P2 FAIL: proposal should not exist';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.orchestration_failures
    WHERE run_id = rid AND failure_class = 'unsupported_citation'
  ) THEN
    RAISE EXCEPTION 'P2 FAIL: unsupported_citation not recorded';
  END IF;
  RAISE NOTICE 'PASS P2 unsupported claim blocked';
END $$;

-- 3) QA rejection then one successful repair
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P3', 'qa_reject_then_repair');
  rid := research._r3_new_run('RUN-R3-P3', qid, 'qa_reject_then_repair');
  res := research.orchestrate_research_run(rid);
  IF res <> 'decision_ready' THEN RAISE EXCEPTION 'P3 FAIL: got %', res; END IF;
  IF (SELECT repair_attempt_count FROM research.research_runs WHERE id = rid) < 1 THEN
    RAISE EXCEPTION 'P3 FAIL: expected repair attempt';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM research.repair_attempts WHERE run_id = rid AND outcome = 'repaired') THEN
    RAISE EXCEPTION 'P3 FAIL: repaired outcome missing';
  END IF;
  RAISE NOTICE 'PASS P3 QA reject then repair';
END $$;

-- 4) Repeated same failure stops after two attempts
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P4', 'qa_reject_repeat');
  rid := research._r3_new_run('RUN-R3-P4', qid, 'qa_reject_repeat');
  res := research.orchestrate_research_run(rid);
  IF res <> 'failed' THEN RAISE EXCEPTION 'P4 FAIL: expected failed got %', res; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.repair_attempts
    WHERE run_id = rid AND outcome = 'escalated_same_failure'
  ) THEN
    RAISE EXCEPTION 'P4 FAIL: stagnation/same-failure escalation missing';
  END IF;
  RAISE NOTICE 'PASS P4 repeated failure stagnation';
END $$;

-- 5) Reviewer rejection cannot be overwritten by proposal writer
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT; vcount INT; pid UUID;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P5', 'reviewer_reject');
  rid := research._r3_new_run('RUN-R3-P5', qid, 'reviewer_reject');
  res := research.orchestrate_research_run(rid);
  IF res <> 'failed' THEN RAISE EXCEPTION 'P5 FAIL: expected failed got %', res; END IF;
  SELECT id INTO pid FROM research.improvement_proposals WHERE question_id = qid;
  SELECT count(*) INTO vcount FROM research.proposal_versions WHERE proposal_id = pid;
  IF vcount <> 1 THEN RAISE EXCEPTION 'P5 FAIL: writer overwrote/added versions (% )', vcount; END IF;
  -- Attempt illicit writer re-run should be duplicate or not change versions
  PERFORM research.run_stage(rid, 'implementation_proposal_writer', 'success');
  SELECT count(*) INTO vcount FROM research.proposal_versions WHERE proposal_id = pid;
  IF vcount <> 1 THEN RAISE EXCEPTION 'P5 FAIL: version count changed after illicit retry'; END IF;
  RAISE NOTICE 'PASS P5 reviewer rejection stands';
END $$;

-- 6) Budget exhaustion blocks before mock invocation
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P6', 'budget_exhaustion');
  rid := research._r3_new_run('RUN-R3-P6', qid, 'budget_exhaustion', 0);
  res := research.orchestrate_research_run(rid);
  IF res <> 'blocked' THEN RAISE EXCEPTION 'P6 FAIL: expected blocked got %', res; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.provider_adapter_responses
    WHERE run_id = rid AND failure_class = 'budget_blocked' AND finish_reason = 'budget_blocked'
  ) THEN
    RAISE EXCEPTION 'P6 FAIL: budget_blocked response missing';
  END IF;
  RAISE NOTICE 'PASS P6 budget block';
END $$;

-- 7) Invalid schema records exact failure
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P7', 'invalid_schema');
  rid := research._r3_new_run('RUN-R3-P7', qid, 'invalid_schema');
  res := research.orchestrate_research_run(rid);
  IF res <> 'failed' THEN RAISE EXCEPTION 'P7 FAIL: expected failed got %', res; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.provider_adapter_responses
    WHERE run_id = rid AND failure_class = 'invalid_schema'
  ) THEN
    RAISE EXCEPTION 'P7 FAIL: invalid_schema not recorded';
  END IF;
  RAISE NOTICE 'PASS P7 invalid schema';
END $$;

-- 8) Partial run cannot enter decision_required
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT; qstatus TEXT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P8', 'success');
  rid := research._r3_new_run('RUN-R3-P8', qid, 'success');
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'p8'
  WHERE id = qid AND status = 'approved_for_research';
  IF research.run_stage(rid, 'researcher') <> 'succeeded' THEN
    RAISE EXCEPTION 'P8 FAIL: researcher';
  END IF;
  res := research.try_enter_decision_from_partial(rid);
  IF res <> 'blocked_partial' THEN RAISE EXCEPTION 'P8 FAIL: expected blocked_partial got %', res; END IF;
  SELECT status INTO qstatus FROM research.research_questions WHERE id = qid;
  IF qstatus = 'decision_required' THEN
    RAISE EXCEPTION 'P8 FAIL: question entered decision_required';
  END IF;
  RAISE NOTICE 'PASS P8 partial blocked';
END $$;

-- 9) Restart resumes without duplicating completed stages
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT; c1 INT; c2 INT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P9', 'success');
  rid := research._r3_new_run('RUN-R3-P9', qid, 'success');
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'p9'
  WHERE id = qid AND status = 'approved_for_research';
  PERFORM research.run_stage(rid, 'researcher');
  PERFORM research.run_stage(rid, 'planner');
  SELECT count(*) INTO c1 FROM research.research_run_stages
  WHERE run_id = rid AND stage IN ('researcher','planner') AND status = 'succeeded';
  res := research.orchestrate_research_run(rid);
  IF res <> 'decision_ready' THEN RAISE EXCEPTION 'P9 FAIL: resume got %', res; END IF;
  SELECT count(*) INTO c2 FROM research.research_run_stages
  WHERE run_id = rid AND stage IN ('researcher','planner') AND status = 'succeeded';
  IF c2 <> c1 THEN RAISE EXCEPTION 'P9 FAIL: duplicated stages % -> %', c1, c2; END IF;
  IF research.run_stage(rid, 'researcher') <> 'duplicate_prevented' THEN
    RAISE EXCEPTION 'P9 FAIL: duplicate stage not prevented';
  END IF;
  RAISE NOTICE 'PASS P9 restart-resume + duplicate prevention';
END $$;

-- 10) Cancellation preserves evidence and stops execution
DO $$
DECLARE
  qid UUID; rid UUID; res TEXT; ecount INT;
BEGIN
  qid := research._r3_clone_question('RQ-R3-P10', 'success');
  rid := research._r3_new_run('RUN-R3-P10', qid, 'success');
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'p10'
  WHERE id = qid AND status = 'approved_for_research';
  PERFORM research.run_stage(rid, 'researcher');
  SELECT count(*) INTO ecount FROM research.evidence_claim_links WHERE question_id = qid;
  PERFORM research.cancel_research_run(rid, 'operator cancel simulation');
  res := research.orchestrate_research_run(rid);
  IF res <> 'cancelled' THEN RAISE EXCEPTION 'P10 FAIL: expected cancelled got %', res; END IF;
  IF (SELECT count(*) FROM research.evidence_claim_links WHERE question_id = qid) <> ecount THEN
    RAISE EXCEPTION 'P10 FAIL: evidence changed after cancel';
  END IF;
  IF (SELECT status FROM research.research_questions WHERE id = qid) = 'decision_required' THEN
    RAISE EXCEPTION 'P10 FAIL: cancelled run reached decision_required';
  END IF;
  RAISE NOTICE 'PASS P10 cancellation';
END $$;

-- Adapter schema smoke: request/response required fields present
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM research.provider_adapter_requests r
    JOIN research.provider_adapter_responses p ON p.request_id = r.id
    WHERE r.input_fingerprint ~ '^[a-f0-9]{64}$'
      AND p.output_fingerprint ~ '^[a-f0-9]{64}$'
      AND r.stage IS NOT NULL
      AND p.provider IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'ADAPTER SCHEMA FAIL: no valid request/response pairs';
  END IF;
  RAISE NOTICE 'PASS adapter schema validation';
END $$;

-- Seed pilot question present
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM research.research_questions WHERE question_id = 'RQ-2026-R3-001') THEN
    RAISE EXCEPTION 'seed pilot question missing';
  END IF;
  IF (SELECT count(*) FROM research.sources WHERE source_url_or_id LIKE 'https://example.com/lab/%') < 3 THEN
    RAISE EXCEPTION 'expected >=3 synthetic sources';
  END IF;
  RAISE NOTICE 'PASS seed pilot artifacts';
END $$;

SELECT 'ROUND3_ACCEPTANCE_DONE' AS marker;
