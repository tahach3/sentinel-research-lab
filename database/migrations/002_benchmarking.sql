-- Round 1: Provider benchmarking evidence schema
-- Applied via scripts/migrate.ps1 (not docker entrypoint — volume already initialized)
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Providers / models (no credentials)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.providers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code            TEXT NOT NULL UNIQUE,
  display_name    TEXT NOT NULL,
  enabled         BOOLEAN NOT NULL DEFAULT FALSE,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT providers_code_nonempty CHECK (length(trim(code)) > 0)
);

CREATE TABLE IF NOT EXISTS research.models (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id     UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  model_code      TEXT NOT NULL,
  model_version   TEXT NOT NULL DEFAULT 'unspecified',
  display_name    TEXT NOT NULL,
  enabled         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT models_code_nonempty CHECK (length(trim(model_code)) > 0),
  CONSTRAINT models_provider_code_version_unique UNIQUE (provider_id, model_code, model_version)
);

-- ---------------------------------------------------------------------------
-- Suites / cases
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.benchmark_suites (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_code       TEXT NOT NULL,
  suite_version   TEXT NOT NULL,
  name            TEXT NOT NULL,
  description     TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT benchmark_suites_role_check CHECK (role_code IN (
    'researcher',
    'planner',
    'implementation_proposal_writer',
    'qa_checker',
    'independent_reviewer',
    'debugger'
  )),
  CONSTRAINT benchmark_suites_role_version_unique UNIQUE (role_code, suite_version)
);

CREATE TABLE IF NOT EXISTS research.benchmark_cases (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  suite_id              UUID NOT NULL REFERENCES research.benchmark_suites(id) ON DELETE RESTRICT,
  case_code             TEXT NOT NULL,
  case_kind             TEXT NOT NULL,
  title                 TEXT NOT NULL,
  input_bundle          JSONB NOT NULL,
  expected_output_schema JSONB NOT NULL,
  scoring_rubric        JSONB NOT NULL,
  max_latency_ms        INTEGER NOT NULL,
  max_token_budget      INTEGER NOT NULL,
  max_cost_usd          NUMERIC(12,6) NOT NULL,
  prompt_version        TEXT NOT NULL,
  input_fingerprint     TEXT NOT NULL,
  citation_required     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT benchmark_cases_kind_check CHECK (case_kind IN ('normal', 'ambiguous', 'adversarial')),
  CONSTRAINT benchmark_cases_latency_positive CHECK (max_latency_ms > 0),
  CONSTRAINT benchmark_cases_tokens_positive CHECK (max_token_budget > 0),
  CONSTRAINT benchmark_cases_cost_nonneg CHECK (max_cost_usd >= 0),
  CONSTRAINT benchmark_cases_fingerprint_sha256 CHECK (input_fingerprint ~ '^[a-f0-9]{64}$'),
  CONSTRAINT benchmark_cases_suite_code_unique UNIQUE (suite_id, case_code)
);

-- ---------------------------------------------------------------------------
-- Runs / outputs / scores / failures / rankings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.benchmark_runs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id               UUID NOT NULL REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT,
  model_id              UUID NOT NULL REFERENCES research.models(id) ON DELETE RESTRICT,
  execution_identity    TEXT NOT NULL,
  status                TEXT NOT NULL DEFAULT 'pending',
  prompt_version        TEXT NOT NULL,
  input_fingerprint     TEXT NOT NULL,
  started_at            TIMESTAMPTZ,
  completed_at          TIMESTAMPTZ,
  latency_ms            INTEGER,
  prompt_tokens         INTEGER,
  completion_tokens     INTEGER,
  total_tokens          INTEGER,
  cost_usd_estimate     NUMERIC(12,6),
  rate_limit_hit        BOOLEAN NOT NULL DEFAULT FALSE,
  retry_count           INTEGER NOT NULL DEFAULT 0,
  failure_code          TEXT,
  failure_detail        TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT benchmark_runs_status_check CHECK (status IN (
    'pending', 'running', 'completed', 'failed', 'cancelled'
  )),
  CONSTRAINT benchmark_runs_execution_identity_unique UNIQUE (execution_identity),
  CONSTRAINT benchmark_runs_tokens_nonneg CHECK (
    (prompt_tokens IS NULL OR prompt_tokens >= 0)
    AND (completion_tokens IS NULL OR completion_tokens >= 0)
    AND (total_tokens IS NULL OR total_tokens >= 0)
  ),
  CONSTRAINT benchmark_runs_cost_nonneg CHECK (
    cost_usd_estimate IS NULL OR cost_usd_estimate >= 0
  ),
  CONSTRAINT benchmark_runs_retry_nonneg CHECK (retry_count >= 0),
  CONSTRAINT benchmark_runs_latency_nonneg CHECK (latency_ms IS NULL OR latency_ms >= 0),
  CONSTRAINT benchmark_runs_fingerprint_sha256 CHECK (input_fingerprint ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS research.model_outputs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id                UUID NOT NULL UNIQUE REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT,
  output_json           JSONB,
  output_text           TEXT,
  output_fingerprint    TEXT NOT NULL,
  schema_valid          BOOLEAN NOT NULL DEFAULT FALSE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT model_outputs_fingerprint_sha256 CHECK (output_fingerprint ~ '^[a-f0-9]{64}$'),
  CONSTRAINT model_outputs_has_body CHECK (output_json IS NOT NULL OR output_text IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS research.automatic_scores (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id                UUID NOT NULL REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT,
  scorer_version        TEXT NOT NULL,
  dimension             TEXT NOT NULL,
  score                 NUMERIC(6,3) NOT NULL,
  details               JSONB,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT automatic_scores_range CHECK (score >= 0 AND score <= 100),
  CONSTRAINT automatic_scores_dimension_check CHECK (dimension IN (
    'factual_accuracy',
    'evidence_quality',
    'instruction_compliance',
    'reasoning_completeness',
    'output_structure',
    'citation_correctness',
    'hallucination_rate',
    'latency',
    'token_use',
    'cost',
    'retry_rate',
    'rate_limit_failures',
    'schema_valid_response_rate',
    'agreement_with_taha'
  ))
);

CREATE TABLE IF NOT EXISTS research.taha_scores (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id                UUID NOT NULL REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT,
  dimension             TEXT NOT NULL,
  score                 NUMERIC(6,3) NOT NULL,
  notes                 TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT taha_scores_range CHECK (score >= 0 AND score <= 100),
  CONSTRAINT taha_scores_dimension_check CHECK (dimension IN (
    'factual_accuracy',
    'evidence_quality',
    'instruction_compliance',
    'reasoning_completeness',
    'output_structure',
    'citation_correctness',
    'hallucination_rate',
    'latency',
    'token_use',
    'cost',
    'retry_rate',
    'rate_limit_failures',
    'schema_valid_response_rate',
    'agreement_with_taha',
    'overall_human_judgment'
  ))
);

-- Append-only: block UPDATE/DELETE on completed-run evidence tables
CREATE OR REPLACE FUNCTION research.forbid_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'Append-only table % forbids %', TG_TABLE_NAME, TG_OP;
END;
$$;

CREATE TRIGGER taha_scores_no_update
  BEFORE UPDATE OR DELETE ON research.taha_scores
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER automatic_scores_no_update
  BEFORE UPDATE OR DELETE ON research.automatic_scores
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER model_outputs_no_update
  BEFORE UPDATE OR DELETE ON research.model_outputs
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TABLE IF NOT EXISTS research.run_failures (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id                UUID NOT NULL REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT,
  failure_class         TEXT NOT NULL,
  is_critical_safety    BOOLEAN NOT NULL DEFAULT FALSE,
  detail                TEXT NOT NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT run_failures_class_check CHECK (failure_class IN (
    'schema_invalid',
    'timeout',
    'rate_limit',
    'quota_exhausted',
    'provider_error',
    'safety',
    'instruction_violation',
    'empty_output',
    'budget_exceeded',
    'cancelled',
    'other'
  ))
);

CREATE TRIGGER run_failures_no_update
  BEFORE UPDATE OR DELETE ON research.run_failures
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

-- Completed runs must have model output OR at least one failure record
CREATE OR REPLACE FUNCTION research.enforce_completed_run_evidence()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  has_output BOOLEAN;
  has_failure BOOLEAN;
BEGIN
  IF NEW.status IN ('completed', 'failed') THEN
    SELECT EXISTS(SELECT 1 FROM research.model_outputs mo WHERE mo.run_id = NEW.id) INTO has_output;
    SELECT EXISTS(SELECT 1 FROM research.run_failures rf WHERE rf.run_id = NEW.id) INTO has_failure;
    IF NEW.status = 'completed' AND NOT has_output THEN
      RAISE EXCEPTION 'completed run % requires model_outputs row', NEW.id;
    END IF;
    IF NEW.status = 'failed' AND NOT has_failure AND NEW.failure_code IS NULL THEN
      RAISE EXCEPTION 'failed run % requires run_failures row or failure_code', NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER benchmark_runs_completion_evidence
  BEFORE UPDATE OF status ON research.benchmark_runs
  FOR EACH ROW EXECUTE FUNCTION research.enforce_completed_run_evidence();

-- Block mutating terminal runs into empty evidence later
CREATE OR REPLACE FUNCTION research.forbid_terminal_run_wipe()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.status IN ('completed', 'failed') AND NEW.status IN ('pending', 'running') THEN
    RAISE EXCEPTION 'immutable completed/failed run % cannot return to %', OLD.id, NEW.status;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER benchmark_runs_no_uncomplete
  BEFORE UPDATE OF status ON research.benchmark_runs
  FOR EACH ROW EXECUTE FUNCTION research.forbid_terminal_run_wipe();

CREATE TABLE IF NOT EXISTS research.monthly_role_rankings (
  id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_code                       TEXT NOT NULL,
  year_month                      TEXT NOT NULL,
  model_id                        UUID NOT NULL REFERENCES research.models(id) ON DELETE RESTRICT,
  rank                            INTEGER NOT NULL,
  composite_score                 NUMERIC(8,4) NOT NULL,
  evidence_sufficient             BOOLEAN NOT NULL,
  case_count                      INTEGER NOT NULL,
  adversarial_count               INTEGER NOT NULL,
  technical_failure_rate          NUMERIC(6,4) NOT NULL,
  unresolved_critical_safety_count INTEGER NOT NULL DEFAULT 0,
  formula_version                 TEXT NOT NULL,
  created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT monthly_role_rankings_role_check CHECK (role_code IN (
    'researcher',
    'planner',
    'implementation_proposal_writer',
    'qa_checker',
    'independent_reviewer',
    'debugger'
  )),
  CONSTRAINT monthly_role_rankings_ym_check CHECK (year_month ~ '^[0-9]{4}-[0-9]{2}$'),
  CONSTRAINT monthly_role_rankings_rank_positive CHECK (rank >= 1),
  CONSTRAINT monthly_role_rankings_counts_nonneg CHECK (
    case_count >= 0 AND adversarial_count >= 0 AND unresolved_critical_safety_count >= 0
  ),
  CONSTRAINT monthly_role_rankings_failure_rate_range CHECK (
    technical_failure_rate >= 0 AND technical_failure_rate <= 1
  ),
  CONSTRAINT monthly_role_rankings_evidence_threshold CHECK (
    evidence_sufficient = TRUE
    AND case_count >= 10
    AND adversarial_count >= 2
    AND technical_failure_rate < 0.20
    AND unresolved_critical_safety_count = 0
  ),
  CONSTRAINT monthly_role_rankings_unique UNIQUE (role_code, year_month, model_id)
);

-- Provider budget policy ledger (limits only; no secrets)
CREATE TABLE IF NOT EXISTS research.provider_budget_policies (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id           UUID NOT NULL UNIQUE REFERENCES research.providers(id) ON DELETE RESTRICT,
  free_only             BOOLEAN NOT NULL DEFAULT TRUE,
  daily_request_cap     INTEGER NOT NULL,
  daily_token_cap       INTEGER NOT NULL,
  monthly_cost_ceiling_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  paid_usage_authorized BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT provider_budget_caps_positive CHECK (
    daily_request_cap > 0 AND daily_token_cap > 0 AND monthly_cost_ceiling_usd >= 0
  ),
  CONSTRAINT provider_budget_paid_requires_ceiling CHECK (
    paid_usage_authorized = FALSE OR monthly_cost_ceiling_usd > 0
  )
);

-- ---------------------------------------------------------------------------
-- Grants for research_app
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA research TO research_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA research TO research_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA research
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO research_app;

-- Tighten: research_app should not update append-only tables via privilege if possible.
-- Triggers already forbid UPDATE/DELETE on scores/outputs/failures.

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW research.v_provider_performance_by_role AS
SELECT
  s.role_code,
  p.code AS provider_code,
  m.model_code,
  m.model_version,
  COUNT(*) FILTER (WHERE r.status = 'completed') AS completed_runs,
  COUNT(*) FILTER (WHERE r.status = 'failed') AS failed_runs,
  AVG(a.score) FILTER (WHERE a.dimension = 'factual_accuracy') AS avg_factual_accuracy,
  AVG(a.score) FILTER (WHERE a.dimension = 'instruction_compliance') AS avg_instruction_compliance,
  AVG(a.score) FILTER (WHERE a.dimension = 'schema_valid_response_rate') AS avg_schema_valid
FROM research.benchmark_runs r
JOIN research.benchmark_cases c ON c.id = r.case_id
JOIN research.benchmark_suites s ON s.id = c.suite_id
JOIN research.models m ON m.id = r.model_id
JOIN research.providers p ON p.id = m.provider_id
LEFT JOIN research.automatic_scores a ON a.run_id = r.id
GROUP BY s.role_code, p.code, m.model_code, m.model_version;

CREATE OR REPLACE VIEW research.v_cost_per_successful_run AS
SELECT
  s.role_code,
  p.code AS provider_code,
  m.model_code,
  COUNT(*) AS successful_runs,
  AVG(r.cost_usd_estimate) AS avg_cost_usd,
  SUM(r.cost_usd_estimate) AS total_cost_usd
FROM research.benchmark_runs r
JOIN research.benchmark_cases c ON c.id = r.case_id
JOIN research.benchmark_suites s ON s.id = c.suite_id
JOIN research.models m ON m.id = r.model_id
JOIN research.providers p ON p.id = m.provider_id
WHERE r.status = 'completed'
GROUP BY s.role_code, p.code, m.model_code;

CREATE OR REPLACE VIEW research.v_failure_rate AS
SELECT
  s.role_code,
  p.code AS provider_code,
  m.model_code,
  COUNT(*) AS total_terminal_runs,
  COUNT(*) FILTER (WHERE r.status = 'failed') AS failed_runs,
  CASE WHEN COUNT(*) = 0 THEN NULL
       ELSE COUNT(*) FILTER (WHERE r.status = 'failed')::NUMERIC / COUNT(*)
  END AS failure_rate
FROM research.benchmark_runs r
JOIN research.benchmark_cases c ON c.id = r.case_id
JOIN research.benchmark_suites s ON s.id = c.suite_id
JOIN research.models m ON m.id = r.model_id
JOIN research.providers p ON p.id = m.provider_id
WHERE r.status IN ('completed', 'failed')
GROUP BY s.role_code, p.code, m.model_code;

CREATE OR REPLACE VIEW research.v_latency_percentile_summary AS
SELECT
  s.role_code,
  p.code AS provider_code,
  m.model_code,
  COUNT(r.latency_ms) AS samples,
  percentile_cont(0.50) WITHIN GROUP (ORDER BY r.latency_ms) AS p50_latency_ms,
  percentile_cont(0.90) WITHIN GROUP (ORDER BY r.latency_ms) AS p90_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY r.latency_ms) AS p95_latency_ms
FROM research.benchmark_runs r
JOIN research.benchmark_cases c ON c.id = r.case_id
JOIN research.benchmark_suites s ON s.id = c.suite_id
JOIN research.models m ON m.id = r.model_id
JOIN research.providers p ON p.id = m.provider_id
WHERE r.status = 'completed' AND r.latency_ms IS NOT NULL
GROUP BY s.role_code, p.code, m.model_code;

CREATE OR REPLACE VIEW research.v_latest_monthly_ranking AS
SELECT DISTINCT ON (role_code, year_month, rank)
  role_code,
  year_month,
  rank,
  model_id,
  composite_score,
  evidence_sufficient,
  case_count,
  adversarial_count,
  technical_failure_rate,
  formula_version,
  created_at
FROM research.monthly_role_rankings
ORDER BY role_code, year_month DESC, rank ASC, created_at DESC;

CREATE OR REPLACE VIEW research.v_insufficient_evidence_warning AS
SELECT
  s.role_code,
  p.code AS provider_code,
  m.model_code,
  m.model_version,
  COUNT(*) FILTER (WHERE r.status = 'completed') AS completed_cases,
  COUNT(*) FILTER (WHERE r.status = 'completed' AND c.case_kind = 'adversarial') AS completed_adversarial,
  CASE WHEN COUNT(*) FILTER (WHERE r.status IN ('completed','failed')) = 0 THEN NULL
       ELSE COUNT(*) FILTER (WHERE r.status = 'failed')::NUMERIC
            / COUNT(*) FILTER (WHERE r.status IN ('completed','failed'))
  END AS technical_failure_rate,
  COUNT(*) FILTER (
    WHERE rf.is_critical_safety AND r.status = 'failed'
  ) AS unresolved_critical_safety_count,
  (
    COUNT(*) FILTER (WHERE r.status = 'completed') < 10
    OR COUNT(*) FILTER (WHERE r.status = 'completed' AND c.case_kind = 'adversarial') < 2
    OR COALESCE(
         COUNT(*) FILTER (WHERE r.status = 'failed')::NUMERIC
         / NULLIF(COUNT(*) FILTER (WHERE r.status IN ('completed','failed')), 0),
         1
       ) >= 0.20
    OR COUNT(*) FILTER (WHERE rf.is_critical_safety AND r.status = 'failed') > 0
  ) AS insufficient_evidence
FROM research.models m
JOIN research.providers p ON p.id = m.provider_id
CROSS JOIN research.benchmark_suites s
LEFT JOIN research.benchmark_cases c ON c.suite_id = s.id
LEFT JOIN research.benchmark_runs r ON r.case_id = c.id AND r.model_id = m.id
LEFT JOIN research.run_failures rf ON rf.run_id = r.id
GROUP BY s.role_code, p.code, m.model_code, m.model_version;

GRANT SELECT ON ALL TABLES IN SCHEMA research TO research_app;

INSERT INTO research.schema_version (version, note)
VALUES (2, 'Round 1: provider benchmarking evidence schema')
ON CONFLICT (version) DO NOTHING;

COMMIT;
