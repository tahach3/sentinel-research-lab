-- Round 2: Research question + evidence + decision lifecycle
BEGIN;

-- ---------------------------------------------------------------------------
-- Status transition map
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.question_status_transitions (
  from_status TEXT NOT NULL,
  to_status   TEXT NOT NULL,
  PRIMARY KEY (from_status, to_status),
  CONSTRAINT qst_from_check CHECK (from_status IN (
    'proposed','triage_required','approved_for_research','active','evidence_review',
    'decision_required','accepted','rejected','deferred','closed','superseded'
  )),
  CONSTRAINT qst_to_check CHECK (to_status IN (
    'proposed','triage_required','approved_for_research','active','evidence_review',
    'decision_required','accepted','rejected','deferred','closed','superseded'
  ))
);

INSERT INTO research.question_status_transitions (from_status, to_status) VALUES
  ('proposed', 'triage_required'),
  ('triage_required', 'approved_for_research'),
  ('triage_required', 'rejected'),
  ('triage_required', 'deferred'),
  ('triage_required', 'superseded'),
  ('approved_for_research', 'active'),
  ('approved_for_research', 'deferred'),
  ('active', 'evidence_review'),
  ('active', 'deferred'),
  ('evidence_review', 'decision_required'),
  ('evidence_review', 'active'),
  ('decision_required', 'accepted'),
  ('decision_required', 'rejected'),
  ('decision_required', 'deferred'),
  ('decision_required', 'active'), -- research_more returns to active via decision flow
  ('accepted', 'closed'),
  ('accepted', 'superseded'),
  ('rejected', 'closed'),
  ('deferred', 'triage_required'),
  ('deferred', 'closed'),
  ('closed', 'superseded')
  -- closed cannot return to proposed/active silently; reopen via new version path only
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Questions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.research_questions (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id             TEXT NOT NULL UNIQUE,
  title                   TEXT NOT NULL,
  precise_question        TEXT NOT NULL,
  question_class          TEXT NOT NULL,
  source_trigger          TEXT NOT NULL,
  linked_metric_or_incident TEXT,
  expected_decision       TEXT,
  priority_score          NUMERIC(8,4) NOT NULL DEFAULT 0,
  priority_rationale      TEXT,
  status                  TEXT NOT NULL DEFAULT 'proposed',
  owner                   TEXT NOT NULL DEFAULT 'Taha',
  due_or_review_at        TIMESTAMPTZ,
  duplicate_fingerprint   TEXT NOT NULL,
  current_version         INTEGER NOT NULL DEFAULT 1,
  confidentiality_class   TEXT NOT NULL DEFAULT 'public_or_synthetic',
  canonical_question_id   UUID REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  superseded_by_question_id UUID REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT rq_class_check CHECK (question_class IN (
    'constitutional','measured_gap','reliability','cost','security',
    'provider_capability','workflow_improvement','external_opportunity'
  )),
  CONSTRAINT rq_status_check CHECK (status IN (
    'proposed','triage_required','approved_for_research','active','evidence_review',
    'decision_required','accepted','rejected','deferred','closed','superseded'
  )),
  CONSTRAINT rq_conf_check CHECK (confidentiality_class IN (
    'public_or_synthetic','internal_lab','restricted'
  )),
  CONSTRAINT rq_fingerprint_sha256 CHECK (duplicate_fingerprint ~ '^[a-f0-9]{64}$'),
  CONSTRAINT rq_version_positive CHECK (current_version >= 1),
  CONSTRAINT rq_no_self_canonical CHECK (canonical_question_id IS DISTINCT FROM id),
  CONSTRAINT rq_no_self_supersede CHECK (superseded_by_question_id IS DISTINCT FROM id)
);

CREATE TABLE IF NOT EXISTS research.research_question_versions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_uuid     UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  version_number    INTEGER NOT NULL,
  title             TEXT NOT NULL,
  precise_question  TEXT NOT NULL,
  change_rationale  TEXT NOT NULL,
  created_by        TEXT NOT NULL DEFAULT 'Taha',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT rqv_unique UNIQUE (question_uuid, version_number),
  CONSTRAINT rqv_version_positive CHECK (version_number >= 1)
);

CREATE TABLE IF NOT EXISTS research.research_question_relationships (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_question_id  UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  to_question_id    UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  relationship_type TEXT NOT NULL,
  note              TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT rqr_type_check CHECK (relationship_type IN (
    'duplicate_of','supersedes','related_to','blocks','blocked_by'
  )),
  CONSTRAINT rqr_no_self CHECK (from_question_id <> to_question_id),
  CONSTRAINT rqr_unique UNIQUE (from_question_id, to_question_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS research.research_priorities (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id             UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  formula_version         TEXT NOT NULL DEFAULT 'priority-v1',
  constitutional_impact   NUMERIC(6,3) NOT NULL,
  measured_performance_gap NUMERIC(6,3) NOT NULL,
  safety_impact           NUMERIC(6,3) NOT NULL,
  expected_value          NUMERIC(6,3) NOT NULL,
  urgency                 NUMERIC(6,3) NOT NULL,
  evidence_availability   NUMERIC(6,3) NOT NULL,
  implementation_cost     NUMERIC(6,3) NOT NULL,
  duplication_penalty     NUMERIC(6,3) NOT NULL DEFAULT 0,
  calculated_score        NUMERIC(8,4) NOT NULL,
  override_score          NUMERIC(8,4),
  override_rationale      TEXT,
  effective_score         NUMERIC(8,4) NOT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT rp_components_range CHECK (
    constitutional_impact BETWEEN 0 AND 100
    AND measured_performance_gap BETWEEN 0 AND 100
    AND safety_impact BETWEEN 0 AND 100
    AND expected_value BETWEEN 0 AND 100
    AND urgency BETWEEN 0 AND 100
    AND evidence_availability BETWEEN 0 AND 100
    AND implementation_cost BETWEEN 0 AND 100
    AND duplication_penalty BETWEEN 0 AND 100
  ),
  CONSTRAINT rp_override_requires_rationale CHECK (
    (override_score IS NULL AND override_rationale IS NULL)
    OR (override_score IS NOT NULL AND override_rationale IS NOT NULL AND length(trim(override_rationale)) > 0)
  )
);

CREATE TABLE IF NOT EXISTS research.research_status_history (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id       UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  from_status       TEXT,
  to_status         TEXT NOT NULL,
  rationale         TEXT NOT NULL,
  actor             TEXT NOT NULL DEFAULT 'Taha',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research.research_closure_records (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id       UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  closure_kind      TEXT NOT NULL,
  rationale         TEXT NOT NULL,
  related_decision_id UUID,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT rcr_kind_check CHECK (closure_kind IN (
    'accepted_closed','rejected_closed','deferred_closed','superseded_closed','merged_duplicate'
  ))
);

-- Append-only history/closure
CREATE TRIGGER research_status_history_no_mutation
  BEFORE UPDATE OR DELETE ON research.research_status_history
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER research_closure_records_no_mutation
  BEFORE UPDATE OR DELETE ON research.research_closure_records
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

-- Priority calculation helper
CREATE OR REPLACE FUNCTION research.compute_priority_v1(
  constitutional_impact NUMERIC,
  measured_performance_gap NUMERIC,
  safety_impact NUMERIC,
  expected_value NUMERIC,
  urgency NUMERIC,
  evidence_availability NUMERIC,
  implementation_cost NUMERIC,
  duplication_penalty NUMERIC
) RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT ROUND((
      constitutional_impact * 0.18
    + measured_performance_gap * 0.16
    + safety_impact * 0.16
    + expected_value * 0.14
    + urgency * 0.12
    + evidence_availability * 0.10
    + (100 - implementation_cost) * 0.08
    - duplication_penalty * 0.06
  )::numeric, 4);
$$;

CREATE OR REPLACE FUNCTION research.trg_set_priority_scores()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.calculated_score := research.compute_priority_v1(
    NEW.constitutional_impact,
    NEW.measured_performance_gap,
    NEW.safety_impact,
    NEW.expected_value,
    NEW.urgency,
    NEW.evidence_availability,
    NEW.implementation_cost,
    NEW.duplication_penalty
  );
  NEW.effective_score := COALESCE(NEW.override_score, NEW.calculated_score);
  RETURN NEW;
END;
$$;

CREATE TRIGGER research_priorities_compute
  BEFORE INSERT OR UPDATE ON research.research_priorities
  FOR EACH ROW EXECUTE FUNCTION research.trg_set_priority_scores();

CREATE OR REPLACE FUNCTION research.trg_sync_question_priority()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE research.research_questions
  SET priority_score = NEW.effective_score,
      priority_rationale = COALESCE(NEW.override_rationale, 'priority-v1 calculated'),
      updated_at = NOW()
  WHERE id = NEW.question_id;
  RETURN NEW;
END;
$$;

CREATE TRIGGER research_priorities_sync_question
  AFTER INSERT OR UPDATE ON research.research_priorities
  FOR EACH ROW EXECUTE FUNCTION research.trg_sync_question_priority();

-- Status transition enforcement (BEFORE) + immutable history (AFTER).
-- History must be AFTER INSERT so question_id FK exists.
CREATE OR REPLACE FUNCTION research.trg_question_status_validate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  allowed BOOLEAN;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
    -- closed cannot silently reopen to active pipeline statuses
    IF OLD.status = 'closed' AND NEW.status IN (
      'proposed','triage_required','approved_for_research','active','evidence_review','decision_required'
    ) THEN
      RAISE EXCEPTION 'closed question % cannot reopen to %; create a new version with rationale', OLD.question_id, NEW.status;
    END IF;

    SELECT EXISTS (
      SELECT 1 FROM research.question_status_transitions t
      WHERE t.from_status = OLD.status AND t.to_status = NEW.status
    ) INTO allowed;

    IF NOT allowed THEN
      RAISE EXCEPTION 'forbidden status transition % -> % for question %', OLD.status, NEW.status, OLD.question_id;
    END IF;
  END IF;

  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION research.trg_question_status_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO research.research_status_history (question_id, from_status, to_status, rationale, actor)
    VALUES (NEW.id, NULL, NEW.status, 'initial status', COALESCE(NEW.owner, 'Taha'));
    RETURN NEW;
  END IF;

  IF NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO research.research_status_history (question_id, from_status, to_status, rationale, actor)
    VALUES (
      NEW.id,
      OLD.status,
      NEW.status,
      COALESCE(NEW.priority_rationale, 'status transition'),
      COALESCE(NEW.owner, 'Taha')
    );
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS research_questions_status_guard ON research.research_questions;
CREATE TRIGGER research_questions_status_validate
  BEFORE INSERT OR UPDATE OF status ON research.research_questions
  FOR EACH ROW EXECUTE FUNCTION research.trg_question_status_validate();

CREATE TRIGGER research_questions_status_history
  AFTER INSERT OR UPDATE OF status ON research.research_questions
  FOR EACH ROW EXECUTE FUNCTION research.trg_question_status_history();
-- ---------------------------------------------------------------------------
-- Evidence chain
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.sources (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url_or_id  TEXT NOT NULL,
  publisher         TEXT NOT NULL,
  source_type       TEXT NOT NULL,
  publication_date  DATE,
  reliability_class TEXT NOT NULL DEFAULT 'unverified',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT sources_type_check CHECK (source_type IN (
    'official_docs','public_changelog','synthetic_fixture','lab_metric','incident_fixture','other_public'
  )),
  CONSTRAINT sources_reliability_check CHECK (reliability_class IN (
    'high','medium','low','unverified'
  )),
  CONSTRAINT sources_identity_unique UNIQUE (source_url_or_id, publisher)
);

CREATE TABLE IF NOT EXISTS research.source_snapshots (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id           UUID NOT NULL REFERENCES research.sources(id) ON DELETE RESTRICT,
  retrieved_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  content_fingerprint TEXT NOT NULL,
  snapshot_metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT source_snapshots_fp_check CHECK (content_fingerprint ~ '^[a-f0-9]{64}$')
);

CREATE TRIGGER source_snapshots_no_mutation
  BEFORE UPDATE OR DELETE ON research.source_snapshots
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TABLE IF NOT EXISTS research.evidence_items (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_snapshot_id    UUID NOT NULL REFERENCES research.source_snapshots(id) ON DELETE RESTRICT,
  quoted_excerpt        TEXT NOT NULL,
  confidence_score      NUMERIC(6,3) NOT NULL,
  reliability_class     TEXT NOT NULL,
  created_by_process    TEXT NOT NULL,
  version_number        INTEGER NOT NULL DEFAULT 1,
  supersedes_evidence_id UUID REFERENCES research.evidence_items(id) ON DELETE RESTRICT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT evidence_confidence_range CHECK (confidence_score BETWEEN 0 AND 100),
  CONSTRAINT evidence_reliability_check CHECK (reliability_class IN ('high','medium','low','unverified')),
  CONSTRAINT evidence_excerpt_maxlen CHECK (char_length(quoted_excerpt) <= 1000),
  CONSTRAINT evidence_version_positive CHECK (version_number >= 1)
);

-- Evidence cannot be deleted; corrections via new version only
CREATE TRIGGER evidence_items_no_delete
  BEFORE DELETE ON research.evidence_items
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TABLE IF NOT EXISTS research.evidence_claim_links (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id       UUID NOT NULL REFERENCES research.evidence_items(id) ON DELETE RESTRICT,
  question_id       UUID REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  claim_text        TEXT NOT NULL,
  stance            TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ecl_stance_check CHECK (stance IN ('supports','contradicts','contextual'))
);

CREATE TABLE IF NOT EXISTS research.research_findings (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id       UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  summary           TEXT NOT NULL,
  confidence_score  NUMERIC(6,3) NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT findings_confidence_range CHECK (confidence_score BETWEEN 0 AND 100)
);

-- ---------------------------------------------------------------------------
-- Proposals + Taha decisions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.improvement_proposals (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_code     TEXT NOT NULL UNIQUE,
  question_id       UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  title             TEXT NOT NULL,
  one_sentence      TEXT NOT NULL,
  expected_benefit  TEXT NOT NULL,
  risk              TEXT NOT NULL,
  estimated_size    TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'draft',
  current_version   INTEGER NOT NULL DEFAULT 1,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ip_status_check CHECK (status IN (
    'draft','evidence_incomplete','ready_for_decision','decided','withdrawn'
  )),
  CONSTRAINT ip_size_check CHECK (estimated_size IN ('XS','S','M','L','XL'))
);

CREATE TABLE IF NOT EXISTS research.proposal_versions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id       UUID NOT NULL REFERENCES research.improvement_proposals(id) ON DELETE RESTRICT,
  version_number    INTEGER NOT NULL,
  body              TEXT NOT NULL,
  evidence_ids      UUID[] NOT NULL DEFAULT '{}',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pv_unique UNIQUE (proposal_id, version_number),
  CONSTRAINT pv_version_positive CHECK (version_number >= 1),
  CONSTRAINT pv_evidence_required_for_decision CHECK (
    -- enforced further by trigger when moving question/proposal to decision_required
    TRUE
  )
);

CREATE OR REPLACE FUNCTION research.proposal_has_evidence(p_evidence_ids UUID[])
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(array_length(p_evidence_ids, 1), 0) > 0
    AND NOT EXISTS (
      SELECT 1 FROM unnest(p_evidence_ids) AS e(id)
      WHERE NOT EXISTS (SELECT 1 FROM research.evidence_items ei WHERE ei.id = e.id)
    );
$$;

CREATE OR REPLACE FUNCTION research.trg_proposal_ready_requires_evidence()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  evid UUID[];
BEGIN
  IF NEW.status = 'ready_for_decision' THEN
    SELECT evidence_ids INTO evid
    FROM research.proposal_versions
    WHERE proposal_id = NEW.id AND version_number = NEW.current_version;

    IF evid IS NULL OR NOT research.proposal_has_evidence(evid) THEN
      RAISE EXCEPTION 'proposal % cannot enter ready_for_decision without valid evidence_ids on current version', NEW.proposal_code;
    END IF;
  END IF;
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER improvement_proposals_evidence_guard
  BEFORE UPDATE OF status ON research.improvement_proposals
  FOR EACH ROW EXECUTE FUNCTION research.trg_proposal_ready_requires_evidence();

CREATE OR REPLACE FUNCTION research.trg_question_decision_requires_supported_proposal()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  ok BOOLEAN;
BEGIN
  IF NEW.status = 'decision_required' AND OLD.status IS DISTINCT FROM 'decision_required' THEN
    SELECT EXISTS (
      SELECT 1
      FROM research.improvement_proposals p
      JOIN research.proposal_versions v
        ON v.proposal_id = p.id AND v.version_number = p.current_version
      WHERE p.question_id = NEW.id
        AND p.status = 'ready_for_decision'
        AND research.proposal_has_evidence(v.evidence_ids)
    ) INTO ok;
    IF NOT ok THEN
      RAISE EXCEPTION 'question % cannot enter decision_required without a ready proposal citing evidence', NEW.question_id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER research_questions_decision_gate
  BEFORE UPDATE OF status ON research.research_questions
  FOR EACH ROW EXECUTE FUNCTION research.trg_question_decision_requires_supported_proposal();

CREATE TABLE IF NOT EXISTS research.taha_decisions (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id           UUID NOT NULL REFERENCES research.improvement_proposals(id) ON DELETE RESTRICT,
  proposal_version      INTEGER NOT NULL,
  decision              TEXT NOT NULL,
  decided_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deciding_authority    TEXT NOT NULL DEFAULT 'Taha',
  evidence_considered   UUID[] NOT NULL DEFAULT '{}',
  risks_accepted        TEXT,
  conditions_text       TEXT,
  review_or_expiry_at   TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT td_decision_check CHECK (decision IN (
    'approved','rejected','deferred','research_more','superseded'
  )),
  CONSTRAINT td_authority_check CHECK (deciding_authority = 'Taha'),
  CONSTRAINT td_deferred_needs_review CHECK (
    decision <> 'deferred' OR review_or_expiry_at IS NOT NULL OR conditions_text IS NOT NULL
  )
);

CREATE TABLE IF NOT EXISTS research.decision_rationales (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_id       UUID NOT NULL REFERENCES research.taha_decisions(id) ON DELETE RESTRICT,
  concise_rationale TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT dr_rationale_nonempty CHECK (length(trim(concise_rationale)) > 0)
);

CREATE TABLE IF NOT EXISTS research.reconsideration_conditions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_id       UUID NOT NULL REFERENCES research.taha_decisions(id) ON DELETE RESTRICT,
  condition_text    TEXT NOT NULL,
  satisfied         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER taha_decisions_no_mutation
  BEFORE UPDATE OR DELETE ON research.taha_decisions
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER decision_rationales_no_mutation
  BEFORE UPDATE OR DELETE ON research.decision_rationales
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

-- Block evidence delete when linked to a decision
CREATE OR REPLACE FUNCTION research.trg_block_evidence_delete_after_decision()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM research.taha_decisions d
    WHERE OLD.id = ANY (d.evidence_considered)
  ) THEN
    RAISE EXCEPTION 'evidence % is locked by a Taha decision and cannot be deleted', OLD.id;
  END IF;
  RETURN OLD;
END;
$$;

-- replace delete trigger stack: forbid_mutation already blocks all deletes;
-- keep explicit lock message via BEFORE DELETE that runs first conceptually — forbid_mutation is enough.
-- Additional: prevent UPDATE of evidence excerpt in place; require new version
CREATE OR REPLACE FUNCTION research.trg_evidence_immutable_body()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.quoted_excerpt IS DISTINCT FROM OLD.quoted_excerpt
     OR NEW.source_snapshot_id IS DISTINCT FROM OLD.source_snapshot_id THEN
    RAISE EXCEPTION 'evidence body is immutable; insert a new version row';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER evidence_items_immutable_body
  BEFORE UPDATE ON research.evidence_items
  FOR EACH ROW EXECUTE FUNCTION research.trg_evidence_immutable_body();

-- Closure helper after decisions (application/workflow responsibility; DB supports records)
ALTER TABLE research.research_closure_records
  DROP CONSTRAINT IF EXISTS research_closure_records_related_decision_id_fkey;

ALTER TABLE research.research_closure_records
  ADD CONSTRAINT research_closure_records_related_decision_id_fkey
  FOREIGN KEY (related_decision_id) REFERENCES research.taha_decisions(id) ON DELETE RESTRICT;

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW research.v_active_research_queue AS
SELECT q.*
FROM research.research_questions q
WHERE q.status IN ('approved_for_research','active','evidence_review')
ORDER BY q.priority_score DESC, q.created_at ASC;

CREATE OR REPLACE VIEW research.v_highest_priority_unanswered AS
SELECT q.question_id, q.title, q.precise_question, q.priority_score, q.status, q.question_class
FROM research.research_questions q
WHERE q.status IN ('proposed','triage_required','approved_for_research','active','evidence_review','decision_required')
ORDER BY q.priority_score DESC, q.updated_at ASC;

CREATE OR REPLACE VIEW research.v_questions_blocked_missing_evidence AS
SELECT q.question_id, q.title, q.status, d.id AS decision_id, rc.condition_text
FROM research.research_questions q
JOIN research.improvement_proposals p ON p.question_id = q.id
JOIN research.taha_decisions d ON d.proposal_id = p.id AND d.decision = 'research_more'
JOIN research.reconsideration_conditions rc ON rc.decision_id = d.id AND rc.satisfied = FALSE;

CREATE OR REPLACE VIEW research.v_proposals_awaiting_taha AS
SELECT p.proposal_code, p.title, p.one_sentence, q.question_id, q.title AS question_title, p.estimated_size, p.status
FROM research.improvement_proposals p
JOIN research.research_questions q ON q.id = p.question_id
WHERE p.status = 'ready_for_decision'
  AND q.status = 'decision_required';

CREATE OR REPLACE VIEW research.v_rejected_eligible_reconsideration AS
SELECT p.proposal_code, q.question_id, d.id AS decision_id, d.decided_at,
       BOOL_OR(rc.satisfied) AS any_condition_satisfied,
       BOOL_AND(rc.satisfied) FILTER (WHERE rc.id IS NOT NULL) AS all_conditions_satisfied
FROM research.taha_decisions d
JOIN research.improvement_proposals p ON p.id = d.proposal_id
JOIN research.research_questions q ON q.id = p.question_id
LEFT JOIN research.reconsideration_conditions rc ON rc.decision_id = d.id
WHERE d.decision = 'rejected'
GROUP BY p.proposal_code, q.question_id, d.id, d.decided_at;

CREATE OR REPLACE VIEW research.v_settled_questions AS
SELECT q.question_id, q.title, q.status, q.priority_score, q.updated_at
FROM research.research_questions q
WHERE q.status IN ('accepted','rejected','closed','superseded');

CREATE OR REPLACE VIEW research.v_duplicate_question_warnings AS
SELECT q.question_id AS duplicate_question_id,
       q.title AS duplicate_title,
       c.question_id AS canonical_question_id,
       c.title AS canonical_title,
       q.duplicate_fingerprint
FROM research.research_questions q
JOIN research.research_questions c ON c.id = q.canonical_question_id
WHERE q.canonical_question_id IS NOT NULL;

CREATE OR REPLACE VIEW research.v_decision_history_by_topic AS
SELECT q.question_class AS topic,
       q.question_id,
       p.proposal_code,
       d.decision,
       d.decided_at,
       dr.concise_rationale
FROM research.taha_decisions d
JOIN research.improvement_proposals p ON p.id = d.proposal_id
JOIN research.research_questions q ON q.id = p.question_id
JOIN research.decision_rationales dr ON dr.decision_id = d.id
ORDER BY q.question_class, d.decided_at DESC;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA research TO research_app;
GRANT SELECT ON ALL TABLES IN SCHEMA research TO research_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA research TO research_app;

INSERT INTO research.schema_version (version, note)
VALUES (3, 'Round 2: research question and decision lifecycle')
ON CONFLICT (version) DO NOTHING;

COMMIT;
