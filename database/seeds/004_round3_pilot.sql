-- Round 3 pilot seed: vector DB vs pgvector question + synthetic evidence
BEGIN;

INSERT INTO research.research_questions (
  question_id, title, precise_question, question_class, source_trigger,
  expected_decision, status, duplicate_fingerprint, confidentiality_class
) VALUES (
  'RQ-2026-R3-001',
  'pgvector now vs dedicated vector DB later',
  'Should the Research Lab use a separate vector database now, or continue with PostgreSQL and pgvector until measured scale requires migration?',
  'workflow_improvement',
  'manual_local_form',
  'architecture_choice',
  'proposed',
  encode(digest('rq-2026-r3-001-pgvector-vs-vectordb', 'sha256'), 'hex'),
  'public_or_synthetic'
) ON CONFLICT (question_id) DO NOTHING;

INSERT INTO research.research_priorities (
  question_id, constitutional_impact, measured_performance_gap, safety_impact, expected_value,
  urgency, evidence_availability, implementation_cost, duplication_penalty
)
SELECT id, 55, 40, 35, 60, 45, 70, 65, 0
FROM research.research_questions WHERE question_id = 'RQ-2026-R3-001'
AND NOT EXISTS (
  SELECT 1 FROM research.research_priorities p
  WHERE p.question_id = (SELECT id FROM research.research_questions WHERE question_id = 'RQ-2026-R3-001')
);

INSERT INTO research.sources (source_url_or_id, publisher, source_type, publication_date, reliability_class)
VALUES
  ('https://example.com/lab/pgvector-capacity-fixture', 'Example Labs', 'lab_metric', DATE '2026-07-01', 'high'),
  ('https://example.com/lab/vector-db-ops-cost-fixture', 'Example Labs', 'synthetic_fixture', DATE '2026-07-10', 'medium'),
  ('https://example.com/lab/scale-threshold-notes', 'Example Labs', 'public_changelog', DATE '2026-07-15', 'medium')
ON CONFLICT (source_url_or_id, publisher) DO NOTHING;

WITH s AS (
  SELECT id, source_url_or_id FROM research.sources
  WHERE source_url_or_id IN (
    'https://example.com/lab/pgvector-capacity-fixture',
    'https://example.com/lab/vector-db-ops-cost-fixture',
    'https://example.com/lab/scale-threshold-notes'
  )
)
INSERT INTO research.source_snapshots (source_id, content_fingerprint, snapshot_metadata)
SELECT s.id,
       encode(digest(s.source_url_or_id || ':r3v1', 'sha256'), 'hex'),
       jsonb_build_object('fixture', true, 'round', 3)
FROM s
WHERE NOT EXISTS (SELECT 1 FROM research.source_snapshots ss WHERE ss.source_id = s.id);

INSERT INTO research.evidence_items (source_snapshot_id, quoted_excerpt, confidence_score, reliability_class, created_by_process)
SELECT ss.id, v.excerpt, v.conf, v.rel, 'round3_seed'
FROM research.source_snapshots ss
JOIN research.sources s ON s.id = ss.source_id
JOIN (VALUES
  ('https://example.com/lab/pgvector-capacity-fixture',
   'Synthetic retrieval volume remains well within PostgreSQL+pgvector capacity.', 90::numeric, 'high'),
  ('https://example.com/lab/vector-db-ops-cost-fixture',
   'A separate vector database increases operational surfaces without measured benefit at current scale.', 80::numeric, 'medium'),
  ('https://example.com/lab/scale-threshold-notes',
   'Dedicated vector DB may become preferable after sustained multi-million embedding query load.', 75::numeric, 'medium')
) AS v(url, excerpt, conf, rel) ON v.url = s.source_url_or_id
WHERE NOT EXISTS (
  SELECT 1 FROM research.evidence_items ei
  WHERE ei.source_snapshot_id = ss.id AND ei.quoted_excerpt = v.excerpt
);

DO $$
DECLARE
  qid UUID;
  e_support UUID;
  e_cost UUID;
  e_contra UUID;
BEGIN
  SELECT id INTO qid FROM research.research_questions WHERE question_id = 'RQ-2026-R3-001';

  SELECT ei.id INTO e_support
  FROM research.evidence_items ei
  JOIN research.source_snapshots ss ON ss.id = ei.source_snapshot_id
  JOIN research.sources s ON s.id = ss.source_id
  WHERE s.source_url_or_id = 'https://example.com/lab/pgvector-capacity-fixture' LIMIT 1;

  SELECT ei.id INTO e_cost
  FROM research.evidence_items ei
  JOIN research.source_snapshots ss ON ss.id = ei.source_snapshot_id
  JOIN research.sources s ON s.id = ss.source_id
  WHERE s.source_url_or_id = 'https://example.com/lab/vector-db-ops-cost-fixture' LIMIT 1;

  SELECT ei.id INTO e_contra
  FROM research.evidence_items ei
  JOIN research.source_snapshots ss ON ss.id = ei.source_snapshot_id
  JOIN research.sources s ON s.id = ss.source_id
  WHERE s.source_url_or_id = 'https://example.com/lab/scale-threshold-notes' LIMIT 1;

  INSERT INTO research.evidence_claim_links (evidence_id, question_id, claim_text, stance)
  SELECT e_support, qid, 'pgvector sufficient now', 'supports'
  WHERE NOT EXISTS (SELECT 1 FROM research.evidence_claim_links WHERE question_id = qid AND evidence_id = e_support);

  INSERT INTO research.evidence_claim_links (evidence_id, question_id, claim_text, stance)
  SELECT e_cost, qid, 'separate vector DB adds ops cost', 'supports'
  WHERE NOT EXISTS (SELECT 1 FROM research.evidence_claim_links WHERE question_id = qid AND evidence_id = e_cost);

  INSERT INTO research.evidence_claim_links (evidence_id, question_id, claim_text, stance)
  SELECT e_contra, qid, 'dedicated DB may help at large scale', 'contradicts'
  WHERE NOT EXISTS (SELECT 1 FROM research.evidence_claim_links WHERE question_id = qid AND evidence_id = e_contra);

  -- Advance to approved_for_research for orchestration entry
  UPDATE research.research_questions SET status = 'triage_required', priority_rationale = 'r3 seed'
  WHERE id = qid AND status = 'proposed';
  UPDATE research.research_questions SET status = 'approved_for_research', priority_rationale = 'r3 seed approved'
  WHERE id = qid AND status = 'triage_required';
END $$;

COMMIT;
