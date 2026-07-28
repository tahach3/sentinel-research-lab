-- Round 2 synthetic lifecycle scenarios (no live SENTINEL data)
BEGIN;

-- Shared synthetic sources/evidence used across scenarios
INSERT INTO research.sources (source_url_or_id, publisher, source_type, publication_date, reliability_class)
VALUES
  ('https://example.com/docs/constitution-fixture', 'Example Labs', 'synthetic_fixture', DATE '2026-01-01', 'high'),
  ('https://example.com/metrics/reliability-gap', 'Example Labs', 'lab_metric', DATE '2026-06-01', 'medium'),
  ('https://example.com/pricing/provider-cost', 'Example Labs', 'public_changelog', DATE '2026-05-15', 'medium'),
  ('https://example.com/incidents/dns-flake', 'Example Labs', 'incident_fixture', DATE '2026-07-01', 'medium')
ON CONFLICT (source_url_or_id, publisher) DO NOTHING;

WITH s AS (
  SELECT id, source_url_or_id FROM research.sources
  WHERE source_url_or_id LIKE 'https://example.com/%'
)
INSERT INTO research.source_snapshots (source_id, content_fingerprint, snapshot_metadata)
SELECT s.id,
       encode(digest(s.source_url_or_id || ':v1', 'sha256'), 'hex'),
       jsonb_build_object('fixture', true, 'round', 2)
FROM s
WHERE NOT EXISTS (
  SELECT 1 FROM research.source_snapshots ss WHERE ss.source_id = s.id
);

-- Evidence items
INSERT INTO research.evidence_items (source_snapshot_id, quoted_excerpt, confidence_score, reliability_class, created_by_process)
SELECT ss.id, v.excerpt, v.conf, v.rel, 'round2_seed'
FROM research.source_snapshots ss
JOIN research.sources s ON s.id = ss.source_id
JOIN (VALUES
  ('https://example.com/docs/constitution-fixture', 'Lab must not write into SENTINEL without Taha approval.', 95::numeric, 'high'),
  ('https://example.com/metrics/reliability-gap', 'Restore-test failure rate fixture: 12% over 30 synthetic runs.', 80::numeric, 'medium'),
  ('https://example.com/pricing/provider-cost', 'Paid model fixture lists $0.002 per 1k tokens.', 75::numeric, 'medium'),
  ('https://example.com/incidents/dns-flake', 'Registry lookup failed intermittently with no such host.', 70::numeric, 'medium')
) AS v(url, excerpt, conf, rel)
  ON v.url = s.source_url_or_id
WHERE NOT EXISTS (
  SELECT 1 FROM research.evidence_items ei WHERE ei.source_snapshot_id = ss.id AND ei.quoted_excerpt = v.excerpt
);

-- Helper fingerprints
-- 1) Constitutional question -> accepted -> closed
INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  expected_decision, status, duplicate_fingerprint, confidentiality_class
) VALUES (
  'RQ-2026-001',
  'Require Taha approval before SENTINEL import',
  'Should every Research Lab export require explicit Taha approval before any SENTINEL import?',
  'constitutional',
  'manual_local_form',
  'policy_confirmation',
  'proposed',
  encode(digest('rq-2026-001-constitutional-approval', 'sha256'), 'hex'),
  'public_or_synthetic'
) ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_question_versions (question_uuid, version_number, title, precise_question, change_rationale)
SELECT id, 1, title, precise_question, 'initial'
FROM research.research_questions WHERE question_id = 'RQ-2026-001'
AND NOT EXISTS (
  SELECT 1 FROM research.research_question_versions v
  JOIN research.research_questions q ON q.id = v.question_uuid
  WHERE q.question_id = 'RQ-2026-001' AND v.version_number = 1
);

INSERT INTO research.research_priorities (
  question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
  urgency, evidence_availability, implementation_cost, duplication_penalty
)
SELECT id, 95, 20, 90, 70, 60, 85, 30, 0
FROM research.research_questions WHERE question_id = 'RQ-2026-001'
AND NOT EXISTS (SELECT 1 FROM research.research_priorities p WHERE p.question_id = research.research_questions.id);

-- Advance RQ-2026-001 through lifecycle to closed/accepted path
DO $$
DECLARE
  qid UUID;
  eid UUID;
  pid UUID;
  did UUID;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-2026-001';
  SELECT ei.id INTO eid
  FROM research.evidence_items ei
  JOIN research.source_snapshots ss ON ss.id = ei.source_snapshot_id
  JOIN research.sources s ON s.id = ss.source_id
  WHERE s.source_url_or_id = 'https://example.com/docs/constitution-fixture'
  LIMIT 1;

  UPDATE research.research_questions SET status = 'triage_required', priority_rationale = 'seed triage' WHERE id = qid AND status = 'proposed';
  UPDATE research.research_questions SET status = 'approved_for_research', priority_rationale = 'seed approve' WHERE id = qid;
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'seed active' WHERE id = qid;
  UPDATE research.research_questions SET status = 'evidence_review', priority_rationale = 'seed evidence' WHERE id = qid;

  INSERT INTO research.evidence_claim_links (evidence_id, question_id, claim_text, stance)
  SELECT eid, qid, 'Exports require Taha approval', 'supports'
  WHERE NOT EXISTS (
    SELECT 1 FROM research.evidence_claim_links l WHERE l.question_id = qid AND l.evidence_id = eid
  );

  INSERT INTO research.improvement_proposals (proposal_code, question_id, title, one_sentence, expected_benefit, risk, estimated_size, status, current_version)
  SELECT 'PROP-001', qid, 'Codify approval gate', 'Require explicit Taha approval before SENTINEL import.',
         'Prevents unauthorized SENTINEL writes', 'Slightly slower handoff', 'S', 'draft', 1
  WHERE NOT EXISTS (SELECT 1 FROM research.improvement_proposals WHERE proposal_code = 'PROP-001');

  SELECT id INTO pid FROM research.improvement_proposals WHERE proposal_code = 'PROP-001';

  INSERT INTO research.proposal_versions (proposal_id, version_number, body, evidence_ids)
  SELECT pid, 1, 'Document and enforce Taha-approval gate for imports.', ARRAY[eid]
  WHERE NOT EXISTS (SELECT 1 FROM research.proposal_versions WHERE proposal_id = pid AND version_number = 1);

  UPDATE research.improvement_proposals SET status = 'ready_for_decision' WHERE id = pid;
  UPDATE research.research_questions SET status = 'decision_required', priority_rationale = 'seed decision' WHERE id = qid;

  INSERT INTO research.taha_decisions (proposal_id, proposal_version, decision, evidence_considered, risks_accepted, conditions_text)
  SELECT pid, 1, 'approved', ARRAY[eid], 'Handoff remains manual', 'Keep exports local-only'
  WHERE NOT EXISTS (SELECT 1 FROM research.taha_decisions d WHERE d.proposal_id = pid);

  SELECT id INTO did FROM research.taha_decisions WHERE proposal_id = pid ORDER BY created_at DESC LIMIT 1;

  INSERT INTO research.decision_rationales (decision_id, concise_rationale)
  SELECT did, 'Aligns with hard boundary: Taha approves every SENTINEL import.'
  WHERE NOT EXISTS (SELECT 1 FROM research.decision_rationales WHERE decision_id = did);

  UPDATE research.improvement_proposals SET status = 'decided' WHERE id = pid;
  UPDATE research.research_questions SET status = 'accepted', priority_rationale = 'seed accepted' WHERE id = qid;
  UPDATE research.research_questions SET status = 'closed', priority_rationale = 'seed closed' WHERE id = qid;

  INSERT INTO research.research_closure_records (question_id, closure_kind, rationale, related_decision_id)
  SELECT qid, 'accepted_closed', 'Approved proposal closes question', did
  WHERE NOT EXISTS (SELECT 1 FROM research.research_closure_records WHERE question_id = qid);
END $$;

-- 2) Measured reliability gap (active)
INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  linked_metric_or_incident, expected_decision, status, duplicate_fingerprint
) VALUES (
  'RQ-2026-002',
  'Reduce restore-test flakiness',
  'What local changes would reduce synthetic restore-test failure rate below 5%?',
  'measured_gap',
  'synthetic_metric_gap_fixture',
  'metric:restore_test_failure_rate',
  'mitigation_plan',
  'proposed',
  encode(digest('rq-2026-002-restore-flake', 'sha256'), 'hex')
) ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_priorities (
  question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
  urgency, evidence_availability, implementation_cost, duplication_penalty
)
SELECT id, 40, 85, 50, 65, 70, 75, 45, 0
FROM research.research_questions WHERE question_id = 'RQ-2026-002'
AND NOT EXISTS (SELECT 1 FROM research.research_priorities p WHERE p.question_id = research.research_questions.id);

DO $$
DECLARE qid UUID;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-2026-002';
  UPDATE research.research_questions SET status = 'triage_required', priority_rationale = 'seed' WHERE id = qid AND status = 'proposed';
  UPDATE research.research_questions SET status = 'approved_for_research', priority_rationale = 'seed' WHERE id = qid;
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'seed' WHERE id = qid;
END $$;

-- 3) Provider-cost question
INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  expected_decision, status, duplicate_fingerprint
) VALUES (
  'RQ-2026-003',
  'Keep free-only default for benchmarks',
  'Should provider benchmarking remain free-only until Taha authorizes paid usage?',
  'cost',
  'manual_local_form',
  'policy_confirmation',
  'proposed',
  encode(digest('rq-2026-003-free-only', 'sha256'), 'hex')
) ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_priorities (
  question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
  urgency, evidence_availability, implementation_cost, duplication_penalty
)
SELECT id, 70, 30, 60, 55, 50, 80, 20, 0
FROM research.research_questions WHERE question_id = 'RQ-2026-003'
AND NOT EXISTS (SELECT 1 FROM research.research_priorities p WHERE p.question_id = research.research_questions.id);

-- 4) Duplicate of RQ-2026-002
INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  linked_metric_or_incident, status, duplicate_fingerprint, canonical_question_id
)
SELECT
  'RQ-2026-004',
  'Reduce restore-test flakiness',
  'How do we lower restore-test failures in the local lab?',
  'reliability',
  'synthetic_metric_gap_fixture',
  'metric:restore_test_failure_rate',
  'proposed',
  encode(digest('rq-2026-002-restore-flake', 'sha256'), 'hex'),
  q.id
FROM research.research_questions q
WHERE q.question_id = 'RQ-2026-002'
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_question_relationships (from_question_id, to_question_id, relationship_type, note)
SELECT d.id, c.id, 'duplicate_of', 'Same fingerprint and metric'
FROM research.research_questions d
JOIN research.research_questions c ON c.question_id = 'RQ-2026-002'
WHERE d.question_id = 'RQ-2026-004'
AND NOT EXISTS (
  SELECT 1 FROM research.research_question_relationships r
  WHERE r.from_question_id = d.id AND r.to_question_id = c.id AND r.relationship_type = 'duplicate_of'
);

-- 5) Previously rejected proposal
INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  status, duplicate_fingerprint
) VALUES (
  'RQ-2026-005',
  'Auto-scrape GitHub for questions',
  'Should the lab scrape GitHub issues to invent research questions?',
  'workflow_improvement',
  'manual_local_form',
  'proposed',
  encode(digest('rq-2026-005-github-scrape', 'sha256'), 'hex')
) ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_priorities (
  question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
  urgency, evidence_availability, implementation_cost, duplication_penalty
)
SELECT id, 30, 10, 40, 25, 20, 40, 70, 0
FROM research.research_questions WHERE question_id = 'RQ-2026-005'
AND NOT EXISTS (SELECT 1 FROM research.research_priorities p WHERE p.question_id = research.research_questions.id);

DO $$
DECLARE
  qid UUID; eid UUID; pid UUID; did UUID;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-2026-005';
  SELECT ei.id INTO eid FROM research.evidence_items ei LIMIT 1;

  UPDATE research.research_questions SET status = 'triage_required', priority_rationale = 'seed' WHERE id = qid AND status = 'proposed';
  UPDATE research.research_questions SET status = 'approved_for_research', priority_rationale = 'seed' WHERE id = qid;
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'seed' WHERE id = qid;
  UPDATE research.research_questions SET status = 'evidence_review', priority_rationale = 'seed' WHERE id = qid;

  INSERT INTO research.improvement_proposals (proposal_code, question_id, title, one_sentence, expected_benefit, risk, estimated_size, status)
  SELECT 'PROP-005', qid, 'Reject GitHub scrape', 'Do not scrape GitHub for question intake.',
         'Keeps intake local and authorized', 'Fewer automated inputs', 'XS', 'draft'
  WHERE NOT EXISTS (SELECT 1 FROM research.improvement_proposals WHERE proposal_code = 'PROP-005');
  SELECT id INTO pid FROM research.improvement_proposals WHERE proposal_code = 'PROP-005';
  INSERT INTO research.proposal_versions (proposal_id, version_number, body, evidence_ids)
  SELECT pid, 1, 'External scrape is out of policy for Round 2.', ARRAY[eid]
  WHERE NOT EXISTS (SELECT 1 FROM research.proposal_versions WHERE proposal_id = pid AND version_number = 1);
  UPDATE research.improvement_proposals SET status = 'ready_for_decision' WHERE id = pid;
  UPDATE research.research_questions SET status = 'decision_required', priority_rationale = 'seed' WHERE id = qid;

  INSERT INTO research.taha_decisions (proposal_id, proposal_version, decision, evidence_considered, conditions_text)
  SELECT pid, 1, 'rejected', ARRAY[eid], 'Reconsider only if policy explicitly authorizes external feeds'
  WHERE NOT EXISTS (SELECT 1 FROM research.taha_decisions WHERE proposal_id = pid);
  SELECT id INTO did FROM research.taha_decisions WHERE proposal_id = pid LIMIT 1;
  INSERT INTO research.decision_rationales (decision_id, concise_rationale)
  SELECT did, 'External GitHub scrape violates Round 2 DO NOT rules.'
  WHERE NOT EXISTS (SELECT 1 FROM research.decision_rationales WHERE decision_id = did);
  INSERT INTO research.reconsideration_conditions (decision_id, condition_text, satisfied)
  SELECT did, 'Written authorization for external feeds exists', FALSE
  WHERE NOT EXISTS (SELECT 1 FROM research.reconsideration_conditions WHERE decision_id = did);

  UPDATE research.improvement_proposals SET status = 'decided' WHERE id = pid;
  UPDATE research.research_questions SET status = 'rejected', priority_rationale = 'seed rejected' WHERE id = qid;
  UPDATE research.research_questions SET status = 'closed', priority_rationale = 'seed closed' WHERE id = qid;
  INSERT INTO research.research_closure_records (question_id, closure_kind, rationale, related_decision_id)
  SELECT qid, 'rejected_closed', 'Rejected proposal', did
  WHERE NOT EXISTS (SELECT 1 FROM research.research_closure_records WHERE question_id = qid);
END $$;

-- 6) Deferred with review date
INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  status, duplicate_fingerprint, due_or_review_at
) VALUES (
  'RQ-2026-006',
  'Evaluate VPS only if 24/7 needed',
  'When, if ever, should the lab move from local Docker to a VPS?',
  'external_opportunity',
  'manual_local_form',
  'proposed',
  encode(digest('rq-2026-006-vps', 'sha256'), 'hex'),
  TIMESTAMPTZ '2026-10-01 00:00:00+05'
) ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_priorities (
  question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
  urgency, evidence_availability, implementation_cost, duplication_penalty
)
SELECT id, 20, 15, 25, 40, 15, 30, 80, 0
FROM research.research_questions WHERE question_id = 'RQ-2026-006'
AND NOT EXISTS (SELECT 1 FROM research.research_priorities p WHERE p.question_id = research.research_questions.id);

DO $$
DECLARE qid UUID; eid UUID; pid UUID; did UUID;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-2026-006';
  SELECT ei.id INTO eid FROM research.evidence_items ei LIMIT 1;
  UPDATE research.research_questions SET status = 'triage_required', priority_rationale = 'seed' WHERE id = qid AND status = 'proposed';
  UPDATE research.research_questions SET status = 'approved_for_research', priority_rationale = 'seed' WHERE id = qid;
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'seed' WHERE id = qid;
  UPDATE research.research_questions SET status = 'evidence_review', priority_rationale = 'seed' WHERE id = qid;
  INSERT INTO research.improvement_proposals (proposal_code, question_id, title, one_sentence, expected_benefit, risk, estimated_size, status)
  SELECT 'PROP-006', qid, 'Defer VPS', 'Defer VPS evaluation until continuous 24/7 need is measured.',
         'Avoid premature cost', 'Delayed scaling', 'S', 'draft'
  WHERE NOT EXISTS (SELECT 1 FROM research.improvement_proposals WHERE proposal_code = 'PROP-006');
  SELECT id INTO pid FROM research.improvement_proposals WHERE proposal_code = 'PROP-006';
  INSERT INTO research.proposal_versions (proposal_id, version_number, body, evidence_ids)
  SELECT pid, 1, 'Local-first remains default.', ARRAY[eid]
  WHERE NOT EXISTS (SELECT 1 FROM research.proposal_versions WHERE proposal_id = pid AND version_number = 1);
  UPDATE research.improvement_proposals SET status = 'ready_for_decision' WHERE id = pid;
  UPDATE research.research_questions SET status = 'decision_required', priority_rationale = 'seed' WHERE id = qid;
  INSERT INTO research.taha_decisions (proposal_id, proposal_version, decision, evidence_considered, review_or_expiry_at, conditions_text)
  SELECT pid, 1, 'deferred', ARRAY[eid], TIMESTAMPTZ '2026-10-01 00:00:00+05', 'Revisit if uptime requirement proven'
  WHERE NOT EXISTS (SELECT 1 FROM research.taha_decisions WHERE proposal_id = pid);
  SELECT id INTO did FROM research.taha_decisions WHERE proposal_id = pid LIMIT 1;
  INSERT INTO research.decision_rationales (decision_id, concise_rationale)
  SELECT did, 'No measured 24/7 need yet.'
  WHERE NOT EXISTS (SELECT 1 FROM research.decision_rationales WHERE decision_id = did);
  UPDATE research.improvement_proposals SET status = 'decided' WHERE id = pid;
  UPDATE research.research_questions SET status = 'deferred', priority_rationale = 'seed deferred' WHERE id = qid;
END $$;

-- 7) research_more with missing-evidence conditions
INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  linked_metric_or_incident, status, duplicate_fingerprint
) VALUES (
  'RQ-2026-007',
  'Root-cause Docker DNS flakes',
  'What evidence is required before changing Docker DNS defaults again?',
  'reliability',
  'synthetic_incident_fixture',
  'incident:docker-dns-flake',
  'proposed',
  encode(digest('rq-2026-007-dns', 'sha256'), 'hex')
) ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_priorities (
  question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
  urgency, evidence_availability, implementation_cost, duplication_penalty
)
SELECT id, 25, 60, 35, 50, 55, 35, 40, 0
FROM research.research_questions WHERE question_id = 'RQ-2026-007'
AND NOT EXISTS (SELECT 1 FROM research.research_priorities p WHERE p.question_id = research.research_questions.id);

DO $$
DECLARE qid UUID; eid UUID; pid UUID; did UUID;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-2026-007';
  SELECT ei.id INTO eid
  FROM research.evidence_items ei
  JOIN research.source_snapshots ss ON ss.id = ei.source_snapshot_id
  JOIN research.sources s ON s.id = ss.source_id
  WHERE s.source_url_or_id = 'https://example.com/incidents/dns-flake' LIMIT 1;

  UPDATE research.research_questions SET status = 'triage_required', priority_rationale = 'seed' WHERE id = qid AND status = 'proposed';
  UPDATE research.research_questions SET status = 'approved_for_research', priority_rationale = 'seed' WHERE id = qid;
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'seed' WHERE id = qid;
  UPDATE research.research_questions SET status = 'evidence_review', priority_rationale = 'seed' WHERE id = qid;

  INSERT INTO research.improvement_proposals (proposal_code, question_id, title, one_sentence, expected_benefit, risk, estimated_size, status)
  SELECT 'PROP-007', qid, 'Need more DNS evidence', 'Collect router vs public DNS comparative logs before further changes.',
         'Avoid thrashing network config', 'Delayed mitigation', 'M', 'draft'
  WHERE NOT EXISTS (SELECT 1 FROM research.improvement_proposals WHERE proposal_code = 'PROP-007');
  SELECT id INTO pid FROM research.improvement_proposals WHERE proposal_code = 'PROP-007';
  INSERT INTO research.proposal_versions (proposal_id, version_number, body, evidence_ids)
  SELECT pid, 1, 'Current incident fixture is insufficient alone.', ARRAY[eid]
  WHERE NOT EXISTS (SELECT 1 FROM research.proposal_versions WHERE proposal_id = pid AND version_number = 1);
  UPDATE research.improvement_proposals SET status = 'ready_for_decision' WHERE id = pid;
  UPDATE research.research_questions SET status = 'decision_required', priority_rationale = 'seed' WHERE id = qid;

  INSERT INTO research.taha_decisions (proposal_id, proposal_version, decision, evidence_considered, conditions_text)
  SELECT pid, 1, 'research_more', ARRAY[eid], 'Need paired failure captures with timestamps'
  WHERE NOT EXISTS (SELECT 1 FROM research.taha_decisions WHERE proposal_id = pid);
  SELECT id INTO did FROM research.taha_decisions WHERE proposal_id = pid LIMIT 1;
  INSERT INTO research.decision_rationales (decision_id, concise_rationale)
  SELECT did, 'Insufficient comparative evidence to change DNS again.'
  WHERE NOT EXISTS (SELECT 1 FROM research.decision_rationales WHERE decision_id = did);
  INSERT INTO research.reconsideration_conditions (decision_id, condition_text, satisfied) VALUES
    (did, 'Provide 3 timestamped failure captures', FALSE),
    (did, 'Compare router DNS vs 8.8.8.8 success ratio', FALSE)
  ON CONFLICT DO NOTHING;

  UPDATE research.improvement_proposals SET status = 'decided' WHERE id = pid;
  -- research_more returns workflow to active for more research
  UPDATE research.research_questions SET status = 'active', priority_rationale = 'seed research_more -> active' WHERE id = qid;
END $$;

COMMIT;
