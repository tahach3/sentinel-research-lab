-- Round 2 lifecycle constraint and transition tests
\set ON_ERROR_STOP on

-- Allowed happy-path miniature question
DO $$
DECLARE
  qid UUID;
  score NUMERIC;
BEGIN
  INSERT INTO research.research_questions (
    question_id, title, precise_question, question_class, source_trigger,
    status, duplicate_fingerprint
  ) VALUES (
    'RQ-TEST-ALLOW',
    'Allowed transition probe',
    'Does the state machine accept the documented path?',
    'workflow_improvement',
    'manual_local_form',
    'proposed',
    encode(digest('rq-test-allow', 'sha256'), 'hex')
  ) RETURNING id INTO qid;

  INSERT INTO research.research_priorities (
    question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
    urgency, evidence_availability, implementation_cost, duplication_penalty
  ) VALUES (qid, 50, 50, 50, 50, 50, 50, 50, 0)
  RETURNING calculated_score INTO score;

  IF score IS NULL OR score <= 0 THEN
    RAISE EXCEPTION 'TEST FAIL: priority calculation produced %', score;
  END IF;

  UPDATE research.research_questions SET status = 'triage_required', priority_rationale = 't' WHERE id = qid;
  UPDATE research.research_questions SET status = 'approved_for_research', priority_rationale = 't' WHERE id = qid;
  UPDATE research.research_questions SET status = 'active', priority_rationale = 't' WHERE id = qid;
  UPDATE research.research_questions SET status = 'evidence_review', priority_rationale = 't' WHERE id = qid;

  RAISE NOTICE 'PASS: allowed transitions and priority-v1';
END $$;

-- Forbidden skip proposed -> active
DO $$
DECLARE
  qid UUID;
  ok BOOLEAN := FALSE;
BEGIN
  INSERT INTO research.research_questions (
    question_id, title, precise_question, question_class, source_trigger,
    status, duplicate_fingerprint
  ) VALUES (
    'RQ-TEST-FORBID-SKIP',
    'Forbidden skip',
    'Skip?',
    'workflow_improvement',
    'manual_local_form',
    'proposed',
    encode(digest('rq-test-forbid-skip', 'sha256'), 'hex')
  ) RETURNING id INTO qid;
  BEGIN
    UPDATE research.research_questions SET status = 'active', priority_rationale = 'bad' WHERE id = qid;
  EXCEPTION WHEN OTHERS THEN
    ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'TEST FAIL: skip transition allowed'; END IF;
  RAISE NOTICE 'PASS: forbidden skip rejected';
END $$;

-- Closed cannot reopen
DO $$
DECLARE
  qid UUID;
  ok BOOLEAN := FALSE;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-2026-001';
  BEGIN
    UPDATE research.research_questions SET status = 'active', priority_rationale = 'reopen' WHERE id = qid;
  EXCEPTION WHEN OTHERS THEN
    ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'TEST FAIL: closed reopen allowed'; END IF;
  RAISE NOTICE 'PASS: closed reopen rejected';
END $$;

-- Priority override requires rationale and audits via sync
DO $$
DECLARE
  qid UUID;
  ok BOOLEAN := FALSE;
  eff NUMERIC;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-TEST-ALLOW';
  BEGIN
    UPDATE research.research_priorities
    SET override_score = 99
    WHERE question_id = qid;
  EXCEPTION WHEN OTHERS THEN
    ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'TEST FAIL: override without rationale accepted'; END IF;

  UPDATE research.research_priorities
  SET override_score = 88.5,
      override_rationale = 'Taha override for test'
  WHERE question_id = qid
  RETURNING effective_score INTO eff;

  IF eff <> 88.5 THEN RAISE EXCEPTION 'TEST FAIL: override not effective (%)', eff; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research.research_questions WHERE id = qid AND priority_score = 88.5
  ) THEN
    RAISE EXCEPTION 'TEST FAIL: question priority not synced';
  END IF;
  RAISE NOTICE 'PASS: priority override audit path';
END $$;

-- Duplicate fingerprint detection (seed RQ-2026-004)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM research.v_duplicate_question_warnings
    WHERE duplicate_question_id = 'RQ-2026-004'
      AND canonical_question_id = 'RQ-2026-002'
  ) THEN
    RAISE EXCEPTION 'TEST FAIL: duplicate warning missing';
  END IF;
  RAISE NOTICE 'PASS: duplicate detection view';
END $$;

-- Proposal without evidence cannot be ready_for_decision
DO $$
DECLARE
  qid UUID;
  pid UUID;
  ok BOOLEAN := FALSE;
BEGIN
  INSERT INTO research.research_questions (
    question_id, title, precise_question, question_class, source_trigger,
    status, duplicate_fingerprint
  ) VALUES (
    'RQ-TEST-NOEV',
    'No evidence proposal',
    'Should unsupported proposals be blocked?',
    'workflow_improvement',
    'manual_local_form',
    'proposed',
    encode(digest('rq-test-noev', 'sha256'), 'hex')
  ) RETURNING id INTO qid;

  INSERT INTO research.improvement_proposals (
    proposal_code, question_id, title, one_sentence, expected_benefit, risk, estimated_size, status
  ) VALUES (
    'PROP-TEST-NOEV', qid, 'Unsupported', 'No evidence.', 'n/a', 'n/a', 'XS', 'draft'
  ) RETURNING id INTO pid;

  INSERT INTO research.proposal_versions (proposal_id, version_number, body, evidence_ids)
  VALUES (pid, 1, 'empty evidence', '{}');

  BEGIN
    UPDATE research.improvement_proposals SET status = 'ready_for_decision' WHERE id = pid;
  EXCEPTION WHEN OTHERS THEN
    ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'TEST FAIL: unsupported proposal accepted'; END IF;
  RAISE NOTICE 'PASS: proposal evidence requirement';
END $$;

-- Evidence immutability
DO $$
DECLARE
  eid UUID;
  ok BOOLEAN := FALSE;
BEGIN
  SELECT id INTO eid FROM research.evidence_items LIMIT 1;
  BEGIN
    UPDATE research.evidence_items SET quoted_excerpt = 'mutated' WHERE id = eid;
  EXCEPTION WHEN OTHERS THEN
    ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'TEST FAIL: evidence mutation allowed'; END IF;

  ok := FALSE;
  BEGIN
    DELETE FROM research.evidence_items WHERE id = eid;
  EXCEPTION WHEN OTHERS THEN
    ok := TRUE;
  END;
  IF NOT ok THEN RAISE EXCEPTION 'TEST FAIL: evidence delete allowed'; END IF;
  RAISE NOTICE 'PASS: evidence immutability';
END $$;

-- Seed scenario presence
DO $$
BEGIN
  IF (SELECT count(*) FROM research.research_questions WHERE question_id LIKE 'RQ-2026-%') < 7 THEN
    RAISE EXCEPTION 'TEST FAIL: expected >=7 seeded RQ-2026 questions';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM research.research_questions WHERE question_id = 'RQ-2026-001' AND status = 'closed') THEN
    RAISE EXCEPTION 'TEST FAIL: accepted/closed scenario missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM research.taha_decisions WHERE decision = 'rejected') THEN
    RAISE EXCEPTION 'TEST FAIL: rejected decision missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM research.taha_decisions WHERE decision = 'deferred' AND review_or_expiry_at IS NOT NULL) THEN
    RAISE EXCEPTION 'TEST FAIL: deferred review date missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM research.taha_decisions WHERE decision = 'research_more') THEN
    RAISE EXCEPTION 'TEST FAIL: research_more decision missing';
  END IF;
  RAISE NOTICE 'PASS: seed scenarios';
END $$;

-- Views readable
SELECT count(*) AS active_queue FROM research.v_active_research_queue;
SELECT count(*) AS awaiting_taha FROM research.v_proposals_awaiting_taha;
SELECT count(*) AS settled FROM research.v_settled_questions;
SELECT count(*) AS dup_warn FROM research.v_duplicate_question_warnings;
SELECT count(*) AS decision_hist FROM research.v_decision_history_by_topic;
SELECT count(*) AS blocked FROM research.v_questions_blocked_missing_evidence;

SELECT 'ROUND2_TESTS_DONE' AS marker;
