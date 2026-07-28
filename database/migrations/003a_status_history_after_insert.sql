-- Hotfix for Round 2: split status validate (BEFORE) vs history (AFTER).
-- Safe to re-run. Does not change schema_version.
BEGIN;

CREATE OR REPLACE FUNCTION research.trg_question_status_validate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  allowed BOOLEAN;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
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
DROP TRIGGER IF EXISTS research_questions_status_validate ON research.research_questions;
DROP TRIGGER IF EXISTS research_questions_status_history ON research.research_questions;

CREATE TRIGGER research_questions_status_validate
  BEFORE INSERT OR UPDATE OF status ON research.research_questions
  FOR EACH ROW EXECUTE FUNCTION research.trg_question_status_validate();

CREATE TRIGGER research_questions_status_history
  AFTER INSERT OR UPDATE OF status ON research.research_questions
  FOR EACH ROW EXECUTE FUNCTION research.trg_question_status_history();

COMMIT;
