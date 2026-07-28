-- Round 3: Simulated multi-model research orchestration (mock adapters only)
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Orchestration run (shared state record)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research.research_runs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_code              TEXT NOT NULL UNIQUE,
  question_uuid         UUID NOT NULL REFERENCES research.research_questions(id) ON DELETE RESTRICT,
  status                TEXT NOT NULL DEFAULT 'pending',
  current_stage         TEXT,
  completed_stages      TEXT[] NOT NULL DEFAULT '{}',
  failed_stage          TEXT,
  repair_attempt_count  INTEGER NOT NULL DEFAULT 0,
  selected_provider_per_stage JSONB NOT NULL DEFAULT '{}'::jsonb,
  input_fingerprints    JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_fingerprints   JSONB NOT NULL DEFAULT '{}'::jsonb,
  final_status          TEXT,
  scenario_mode         TEXT NOT NULL DEFAULT 'success',
  budget_remaining_usd  NUMERIC(12,6) NOT NULL DEFAULT 1.000000,
  token_ceiling         INTEGER NOT NULL DEFAULT 8000,
  cost_ceiling_usd      NUMERIC(12,6) NOT NULL DEFAULT 1.000000,
  max_repair_attempts   INTEGER NOT NULL DEFAULT 2,
  cancelled             BOOLEAN NOT NULL DEFAULT FALSE,
  decision_card         JSONB,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT rr_status_check CHECK (status IN (
    'pending','running','awaiting_qa','awaiting_review','repair_required',
    'decision_ready','failed','blocked','cancelled'
  )),
  CONSTRAINT rr_final_status_check CHECK (
    final_status IS NULL OR final_status IN (
      'pending','running','awaiting_qa','awaiting_review','repair_required',
      'decision_ready','failed','blocked','cancelled'
    )
  ),
  CONSTRAINT rr_repair_nonneg CHECK (repair_attempt_count >= 0),
  CONSTRAINT rr_max_repair CHECK (max_repair_attempts = 2),
  CONSTRAINT rr_stage_check CHECK (
    current_stage IS NULL OR current_stage IN (
      'researcher','planner','implementation_proposal_writer','qa_checker',
      'independent_reviewer','debugger','finalizer'
    )
  )
);

CREATE TABLE IF NOT EXISTS research.research_run_stages (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id              UUID NOT NULL REFERENCES research.research_runs(id) ON DELETE RESTRICT,
  stage               TEXT NOT NULL,
  attempt_number      INTEGER NOT NULL DEFAULT 1,
  status              TEXT NOT NULL DEFAULT 'pending',
  provider            TEXT NOT NULL,
  model_identifier    TEXT NOT NULL,
  input_fingerprint   TEXT NOT NULL,
  output_fingerprint  TEXT,
  request_id          UUID,
  response_id         UUID,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at         TIMESTAMPTZ,
  CONSTRAINT rrs_stage_check CHECK (stage IN (
    'researcher','planner','implementation_proposal_writer','qa_checker',
    'independent_reviewer','debugger','finalizer'
  )),
  CONSTRAINT rrs_status_check CHECK (status IN (
    'pending','running','succeeded','failed','skipped','blocked'
  )),
  CONSTRAINT rrs_attempt_pos CHECK (attempt_number >= 1),
  CONSTRAINT rrs_unique_attempt UNIQUE (run_id, stage, attempt_number),
  CONSTRAINT rrs_fp_sha CHECK (input_fingerprint ~ '^[a-f0-9]{64}$'),
  CONSTRAINT rrs_out_fp_sha CHECK (output_fingerprint IS NULL OR output_fingerprint ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS research.provider_adapter_requests (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id                UUID NOT NULL REFERENCES research.research_runs(id) ON DELETE RESTRICT,
  stage_row_id          UUID REFERENCES research.research_run_stages(id) ON DELETE RESTRICT,
  question_id           TEXT NOT NULL,
  stage                 TEXT NOT NULL,
  model_identifier      TEXT NOT NULL,
  prompt_version        TEXT NOT NULL,
  normalized_evidence_bundle JSONB NOT NULL DEFAULT '[]'::jsonb,
  allowed_source_ids    UUID[] NOT NULL DEFAULT '{}',
  token_ceiling         INTEGER NOT NULL,
  cost_ceiling_usd      NUMERIC(12,6) NOT NULL,
  timeout_ms            INTEGER NOT NULL DEFAULT 5000,
  required_output_schema TEXT NOT NULL,
  confidentiality_class TEXT NOT NULL DEFAULT 'public_or_synthetic',
  input_fingerprint     TEXT NOT NULL,
  scenario_hint         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT par_stage_check CHECK (stage IN (
    'researcher','planner','implementation_proposal_writer','qa_checker',
    'independent_reviewer','debugger'
  )),
  CONSTRAINT par_fp_sha CHECK (input_fingerprint ~ '^[a-f0-9]{64}$'),
  CONSTRAINT par_conf_check CHECK (confidentiality_class IN (
    'public_or_synthetic','internal_lab','restricted'
  ))
);

CREATE TABLE IF NOT EXISTS research.provider_adapter_responses (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id            UUID NOT NULL UNIQUE REFERENCES research.provider_adapter_requests(id) ON DELETE RESTRICT,
  run_id                UUID NOT NULL REFERENCES research.research_runs(id) ON DELETE RESTRICT,
  provider              TEXT NOT NULL,
  model                 TEXT NOT NULL,
  model_version         TEXT,
  stage                 TEXT NOT NULL,
  structured_output     JSONB,
  cited_evidence_ids    UUID[] NOT NULL DEFAULT '{}',
  latency_ms            INTEGER NOT NULL DEFAULT 0,
  input_tokens          INTEGER NOT NULL DEFAULT 0,
  output_tokens         INTEGER NOT NULL DEFAULT 0,
  estimated_cost_usd    NUMERIC(12,6) NOT NULL DEFAULT 0,
  finish_reason         TEXT NOT NULL,
  retry_count           INTEGER NOT NULL DEFAULT 0,
  output_fingerprint    TEXT,
  failure_class         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pares_finish_check CHECK (finish_reason IN (
    'success','error','timeout','rate_limited','budget_blocked','cancelled'
  )),
  CONSTRAINT pares_failure_check CHECK (
    failure_class IS NULL OR failure_class IN (
      'quota_exhausted','budget_blocked','timeout','rate_limited','invalid_schema',
      'unsupported_citation','provider_unavailable','unsafe_output','mock_failure'
    )
  ),
  CONSTRAINT pares_out_fp CHECK (output_fingerprint IS NULL OR output_fingerprint ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS research.repair_attempts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id            UUID NOT NULL REFERENCES research.research_runs(id) ON DELETE RESTRICT,
  stage             TEXT NOT NULL,
  attempt_number    INTEGER NOT NULL,
  failure_class     TEXT NOT NULL,
  prior_failure_class TEXT,
  same_as_prior     BOOLEAN NOT NULL DEFAULT FALSE,
  outcome           TEXT NOT NULL,
  detail            TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ra_attempt_pos CHECK (attempt_number >= 1 AND attempt_number <= 2),
  CONSTRAINT ra_outcome_check CHECK (outcome IN (
    'repaired','escalated_same_failure','escalated_budget','blocked'
  )),
  CONSTRAINT ra_unique UNIQUE (run_id, stage, attempt_number)
);

CREATE TABLE IF NOT EXISTS research.orchestration_failures (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id        UUID NOT NULL REFERENCES research.research_runs(id) ON DELETE RESTRICT,
  stage         TEXT,
  failure_class TEXT NOT NULL,
  detail        TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT of_failure_check CHECK (failure_class IN (
    'quota_exhausted','budget_blocked','timeout','rate_limited','invalid_schema',
    'unsupported_citation','provider_unavailable','unsafe_output','mock_failure',
    'partial_blocked','stagnation','cancelled','duplicate_stage'
  ))
);

-- Immutable completed stage rows
CREATE OR REPLACE FUNCTION research.trg_run_stage_immutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'research_run_stages rows cannot be deleted';
  END IF;
  IF OLD.status IN ('succeeded','failed','blocked') THEN
    IF NEW.status IS DISTINCT FROM OLD.status
       OR NEW.output_fingerprint IS DISTINCT FROM OLD.output_fingerprint
       OR NEW.input_fingerprint IS DISTINCT FROM OLD.input_fingerprint
       OR NEW.provider IS DISTINCT FROM OLD.provider THEN
      RAISE EXCEPTION 'completed/failed stage row is immutable';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS research_run_stages_immutable ON research.research_run_stages;
CREATE TRIGGER research_run_stages_immutable
  BEFORE UPDATE OR DELETE ON research.research_run_stages
  FOR EACH ROW EXECUTE FUNCTION research.trg_run_stage_immutable();

CREATE TRIGGER provider_adapter_requests_no_mutation
  BEFORE UPDATE OR DELETE ON research.provider_adapter_requests
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER provider_adapter_responses_no_mutation
  BEFORE UPDATE OR DELETE ON research.provider_adapter_responses
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER repair_attempts_no_mutation
  BEFORE UPDATE OR DELETE ON research.repair_attempts
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

CREATE TRIGGER orchestration_failures_no_mutation
  BEFORE UPDATE OR DELETE ON research.orchestration_failures
  FOR EACH ROW EXECUTE FUNCTION research.forbid_mutation();

-- Default mock providers per stage (QA != reviewer)
CREATE OR REPLACE FUNCTION research.mock_provider_for_stage(p_stage TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE p_stage
    WHEN 'researcher' THEN 'mock-provider-researcher'
    WHEN 'planner' THEN 'mock-provider-planner'
    WHEN 'implementation_proposal_writer' THEN 'mock-provider-writer'
    WHEN 'qa_checker' THEN 'mock-provider-qa'
    WHEN 'independent_reviewer' THEN 'mock-provider-reviewer'
    WHEN 'debugger' THEN 'mock-provider-debugger'
    ELSE 'mock-provider-unknown'
  END;
$$;

CREATE OR REPLACE FUNCTION research.mock_model_for_stage(p_stage TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE p_stage
    WHEN 'researcher' THEN 'mock-researcher-v1'
    WHEN 'planner' THEN 'mock-planner-v1'
    WHEN 'implementation_proposal_writer' THEN 'mock-writer-v1'
    WHEN 'qa_checker' THEN 'mock-qa-v1'
    WHEN 'independent_reviewer' THEN 'mock-reviewer-v1'
    WHEN 'debugger' THEN 'mock-debugger-v1'
    ELSE 'mock-unknown-v1'
  END;
$$;

CREATE OR REPLACE FUNCTION research.sha256_hex(p_text TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT encode(digest(convert_to(p_text, 'UTF8'), 'sha256'), 'hex');
$$;

-- Mock adapter: deterministic scenarios, no HTTP
CREATE OR REPLACE FUNCTION research.mock_adapter_invoke(p_request_id UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  req research.provider_adapter_requests%ROWTYPE;
  run research.research_runs%ROWTYPE;
  v_provider TEXT;
  v_model TEXT;
  v_finish TEXT := 'success';
  v_failure TEXT := NULL;
  v_output JSONB;
  v_cited UUID[] := '{}';
  v_latency INT := 12;
  v_in_tok INT := 100;
  v_out_tok INT := 80;
  v_cost NUMERIC(12,6) := 0.000100;
  v_out_fp TEXT;
  v_resp_id UUID;
  v_hint TEXT;
BEGIN
  SELECT * INTO req FROM research.provider_adapter_requests WHERE id = p_request_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'adapter request % not found', p_request_id;
  END IF;
  SELECT * INTO run FROM research.research_runs WHERE id = req.run_id;

  v_provider := research.mock_provider_for_stage(req.stage);
  v_model := req.model_identifier;
  v_hint := COALESCE(req.scenario_hint, run.scenario_mode, 'success');

  -- Budget / quota gates before mock "invocation"
  IF run.budget_remaining_usd <= 0 OR run.cost_ceiling_usd <= 0 THEN
    v_finish := 'budget_blocked';
    v_failure := 'budget_blocked';
    v_output := jsonb_build_object('error', 'budget exhausted before invocation');
    v_cost := 0;
    v_out_tok := 0;
  ELSIF v_hint = 'budget_exhaustion' AND req.stage = 'researcher' THEN
    v_finish := 'budget_blocked';
    v_failure := 'budget_blocked';
    v_output := jsonb_build_object('error', 'scenario budget_exhaustion');
    v_cost := 0;
  ELSIF v_hint = 'timeout' AND req.stage = COALESCE(run.failed_stage, 'researcher') THEN
    v_finish := 'timeout';
    v_failure := 'timeout';
    v_output := jsonb_build_object('error', 'mock timeout');
    v_latency := req.timeout_ms;
  ELSIF v_hint = 'rate_limit' AND req.stage = 'researcher' THEN
    v_finish := 'rate_limited';
    v_failure := 'rate_limited';
    v_output := jsonb_build_object('error', 'mock rate limit');
  ELSIF v_hint = 'invalid_schema' AND req.stage = 'researcher' THEN
    v_finish := 'error';
    v_failure := 'invalid_schema';
    v_output := jsonb_build_object('not_the_schema', true);
  ELSIF v_hint = 'unsupported_claim' AND req.stage = 'implementation_proposal_writer' THEN
    v_finish := 'error';
    v_failure := 'unsupported_citation';
    v_output := jsonb_build_object(
      'proposal', 'Claim unsupported by allowed sources',
      'cited_evidence_ids', '["00000000-0000-0000-0000-000000000099"]'::jsonb
    );
  ELSIF v_hint IN ('qa_reject_then_repair','qa_reject_repeat') AND req.stage = 'qa_checker'
        AND NOT (run.repair_attempt_count >= 1 AND v_hint = 'qa_reject_then_repair') THEN
    v_finish := 'error';
    v_failure := 'mock_failure';
    v_output := jsonb_build_object('verdict', 'reject', 'score', 35, 'reason', 'QA rejection');
  ELSIF v_hint = 'reviewer_reject' AND req.stage = 'independent_reviewer' THEN
    v_finish := 'error';
    v_failure := 'mock_failure';
    v_output := jsonb_build_object('verdict', 'reject', 'reason', 'Independent reviewer rejection');
  ELSIF v_hint = 'contradictory_finding' AND req.stage = 'researcher' THEN
    v_finish := 'success';
    v_output := jsonb_build_object(
      'findings', jsonb_build_array(
        jsonb_build_object('claim', 'pgvector sufficient at current scale', 'stance', 'supports'),
        jsonb_build_object('claim', 'dedicated vector DB may help at large scale', 'stance', 'contradicts')
      )
    );
  ELSE
    -- success payloads by stage
    CASE req.stage
      WHEN 'researcher' THEN
        v_output := jsonb_build_object(
          'findings', jsonb_build_array(
            jsonb_build_object(
              'claim', 'PostgreSQL+pgvector meets current lab scale',
              'stance', 'supports',
              'summary', 'Synthetic scale metrics show no migration urgency'
            ),
            jsonb_build_object(
              'claim', 'Separate vector DB adds ops cost without measured need',
              'stance', 'contextual',
              'summary', 'Ops overhead is real; benefit unmeasured'
            )
          )
        );
      WHEN 'planner' THEN
        v_output := jsonb_build_object(
          'plan', 'Defer dedicated vector DB; continue pgvector; define migration triggers',
          'work_items', jsonb_build_array('document scale thresholds', 'keep pgvector', 'revisit on measured need')
        );
      WHEN 'implementation_proposal_writer' THEN
        v_cited := COALESCE(
          (SELECT array_agg(DISTINCT x) FROM unnest(req.allowed_source_ids) AS x),
          '{}'
        );
        -- Prefer evidence item IDs from bundle if present
        IF jsonb_typeof(req.normalized_evidence_bundle) = 'array'
           AND jsonb_array_length(req.normalized_evidence_bundle) > 0 THEN
          SELECT COALESCE(array_agg((e->>'evidence_id')::uuid), '{}')
            INTO v_cited
          FROM jsonb_array_elements(req.normalized_evidence_bundle) e
          WHERE e ? 'evidence_id';
        END IF;
        v_output := jsonb_build_object(
          'title', 'Continue with PostgreSQL and pgvector',
          'one_sentence', 'Keep pgvector until measured scale requires a separate vector database.',
          'expected_benefit', 'Avoid premature infrastructure cost and complexity',
          'risk', 'May need later migration if retrieval scale grows sharply',
          'estimated_size', 'S',
          'body', 'Stay on PostgreSQL+pgvector; define explicit migration thresholds.',
          'cited_evidence_ids', to_jsonb(v_cited)
        );
      WHEN 'qa_checker' THEN
        v_output := jsonb_build_object('verdict', 'pass', 'score', 88, 'notes', 'Evidence cited; schema valid');
      WHEN 'independent_reviewer' THEN
        v_output := jsonb_build_object(
          'verdict', 'approve',
          'notes', 'Proposal consistent with evidence; no silent rewrite',
          'proposal_modified', false
        );
      WHEN 'debugger' THEN
        v_output := jsonb_build_object(
          'recommendation', 'bounded_retry',
          'max_additional_attempts', 1,
          'notes', 'Repair QA issues once; do not loop forever'
        );
      ELSE
        v_output := jsonb_build_object('ok', true);
    END CASE;
  END IF;

  v_out_fp := research.sha256_hex(COALESCE(v_output::text, '') || '|' || req.input_fingerprint);

  INSERT INTO research.provider_adapter_responses (
    request_id, run_id, provider, model, model_version, stage, structured_output,
    cited_evidence_ids, latency_ms, input_tokens, output_tokens, estimated_cost_usd,
    finish_reason, retry_count, output_fingerprint, failure_class
  ) VALUES (
    p_request_id, req.run_id, v_provider, v_model, 'mock-1.0', req.stage, v_output,
    COALESCE(v_cited, '{}'), v_latency, v_in_tok, v_out_tok, v_cost,
    v_finish, 0, v_out_fp, v_failure
  ) RETURNING id INTO v_resp_id;

  IF v_finish = 'success' AND v_cost > 0 THEN
    UPDATE research.research_runs
    SET budget_remaining_usd = GREATEST(0, budget_remaining_usd - v_cost),
        updated_at = NOW()
    WHERE id = req.run_id;
  END IF;

  RETURN v_resp_id;
END;
$$;

-- Helper: append completed stage once
CREATE OR REPLACE FUNCTION research._append_completed_stage(p_run_id UUID, p_stage TEXT)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE research.research_runs
  SET completed_stages = CASE
        WHEN p_stage = ANY(completed_stages) THEN completed_stages
        ELSE completed_stages || p_stage
      END,
      updated_at = NOW()
  WHERE id = p_run_id;
END;
$$;

CREATE OR REPLACE FUNCTION research._record_failure(
  p_run_id UUID, p_stage TEXT, p_class TEXT, p_detail TEXT
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO research.orchestration_failures (run_id, stage, failure_class, detail)
  VALUES (p_run_id, p_stage, p_class, p_detail);
  UPDATE research.research_runs
  SET failed_stage = p_stage,
      status = CASE
        WHEN p_class = 'budget_blocked' THEN 'blocked'
        WHEN p_class = 'cancelled' THEN 'cancelled'
        ELSE 'failed'
      END,
      final_status = CASE
        WHEN p_class = 'budget_blocked' THEN 'blocked'
        WHEN p_class = 'cancelled' THEN 'cancelled'
        ELSE 'failed'
      END,
      updated_at = NOW()
  WHERE id = p_run_id;
END;
$$;

-- Evidence bundle for a question
CREATE OR REPLACE FUNCTION research._evidence_bundle_for_question(p_question_uuid UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'evidence_id', ei.id,
    'source_id', s.id,
    'excerpt', ei.quoted_excerpt,
    'reliability', ei.reliability_class
  ) ORDER BY ei.created_at), '[]'::jsonb)
  FROM research.evidence_claim_links l
  JOIN research.evidence_items ei ON ei.id = l.evidence_id
  JOIN research.source_snapshots ss ON ss.id = ei.source_snapshot_id
  JOIN research.sources s ON s.id = ss.source_id
  WHERE l.question_id = p_question_uuid;
$$;

CREATE OR REPLACE FUNCTION research._allowed_source_ids(p_question_uuid UUID)
RETURNS UUID[]
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(array_agg(DISTINCT s.id), '{}')
  FROM research.evidence_claim_links l
  JOIN research.evidence_items ei ON ei.id = l.evidence_id
  JOIN research.source_snapshots ss ON ss.id = ei.source_snapshot_id
  JOIN research.sources s ON s.id = ss.source_id
  WHERE l.question_id = p_question_uuid;
$$;

-- Execute one stage with quota/budget checks, fingerprinting, immutability
CREATE OR REPLACE FUNCTION research.run_stage(
  p_run_id UUID,
  p_stage TEXT,
  p_scenario_hint TEXT DEFAULT NULL
) RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  run research.research_runs%ROWTYPE;
  q research.research_questions%ROWTYPE;
  v_attempt INT;
  v_stage_id UUID;
  v_req_id UUID;
  v_resp_id UUID;
  resp research.provider_adapter_responses%ROWTYPE;
  v_in_fp TEXT;
  v_bundle JSONB;
  v_sources UUID[];
  v_provider TEXT;
  v_model TEXT;
  v_prior_fail TEXT;
BEGIN
  SELECT * INTO run FROM research.research_runs WHERE id = p_run_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run % missing', p_run_id; END IF;
  IF run.cancelled OR run.status = 'cancelled' THEN
    PERFORM research._record_failure(p_run_id, p_stage, 'cancelled', 'run cancelled');
    RETURN 'cancelled';
  END IF;
  IF p_stage = ANY(run.completed_stages) THEN
    INSERT INTO research.orchestration_failures (run_id, stage, failure_class, detail)
    VALUES (p_run_id, p_stage, 'duplicate_stage', 'refusing to re-execute completed stage');
    RETURN 'duplicate_prevented';
  END IF;
  IF run.status IN ('failed','blocked','decision_ready') THEN
    RETURN run.status;
  END IF;

  SELECT * INTO q FROM research.research_questions WHERE id = run.question_uuid;

  -- Budget gate before invocation
  IF run.budget_remaining_usd <= 0 OR COALESCE(p_scenario_hint, run.scenario_mode) = 'budget_exhaustion' THEN
    IF COALESCE(p_scenario_hint, run.scenario_mode) = 'budget_exhaustion' THEN
      UPDATE research.research_runs SET budget_remaining_usd = 0, updated_at = NOW() WHERE id = p_run_id;
    END IF;
    SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
    IF run.budget_remaining_usd <= 0 THEN
      v_attempt := 1;
      v_provider := research.mock_provider_for_stage(p_stage);
      v_model := research.mock_model_for_stage(p_stage);
      v_in_fp := research.sha256_hex(p_run_id::text || '|' || p_stage || '|budget');
      INSERT INTO research.research_run_stages (
        run_id, stage, attempt_number, status, provider, model_identifier, input_fingerprint, finished_at
      ) VALUES (
        p_run_id, p_stage, v_attempt, 'blocked', v_provider, v_model, v_in_fp, NOW()
      ) RETURNING id INTO v_stage_id;
      INSERT INTO research.provider_adapter_requests (
        run_id, stage_row_id, question_id, stage, model_identifier, prompt_version,
        normalized_evidence_bundle, allowed_source_ids, token_ceiling, cost_ceiling_usd,
        timeout_ms, required_output_schema, confidentiality_class, input_fingerprint, scenario_hint
      ) VALUES (
        p_run_id, v_stage_id, q.question_id, p_stage, v_model, 'prompt-v1',
        '[]'::jsonb, '{}', run.token_ceiling, run.cost_ceiling_usd,
        5000, p_stage || '_schema_v1', q.confidentiality_class, v_in_fp, 'budget_exhaustion'
      ) RETURNING id INTO v_req_id;
      -- Record blocked response without "success" mock work
      INSERT INTO research.provider_adapter_responses (
        request_id, run_id, provider, model, model_version, stage, structured_output,
        latency_ms, finish_reason, output_fingerprint, failure_class
      ) VALUES (
        v_req_id, p_run_id, v_provider, v_model, 'mock-1.0', p_stage,
        jsonb_build_object('error','budget blocked before invocation'),
        0, 'budget_blocked', research.sha256_hex('budget|' || v_in_fp), 'budget_blocked'
      );
      PERFORM research._record_failure(p_run_id, p_stage, 'budget_blocked', 'budget exhausted before mock invocation');
      RETURN 'blocked';
    END IF;
  END IF;

  v_attempt := COALESCE(
    (SELECT max(attempt_number) FROM research.research_run_stages WHERE run_id = p_run_id AND stage = p_stage),
    0
  ) + 1;

  v_provider := research.mock_provider_for_stage(p_stage);
  v_model := research.mock_model_for_stage(p_stage);
  v_bundle := research._evidence_bundle_for_question(q.id);
  v_sources := research._allowed_source_ids(q.id);
  v_in_fp := research.sha256_hex(
    p_run_id::text || '|' || p_stage || '|' || v_attempt::text || '|' || COALESCE(v_bundle::text, '[]')
  );

  INSERT INTO research.research_run_stages (
    run_id, stage, attempt_number, status, provider, model_identifier, input_fingerprint
  ) VALUES (
    p_run_id, p_stage, v_attempt, 'running', v_provider, v_model, v_in_fp
  ) RETURNING id INTO v_stage_id;

  UPDATE research.research_runs
  SET status = 'running',
      current_stage = p_stage,
      selected_provider_per_stage = selected_provider_per_stage || jsonb_build_object(p_stage, v_provider),
      input_fingerprints = input_fingerprints || jsonb_build_object(p_stage || ':' || v_attempt, v_in_fp),
      updated_at = NOW()
  WHERE id = p_run_id;

  INSERT INTO research.provider_adapter_requests (
    run_id, stage_row_id, question_id, stage, model_identifier, prompt_version,
    normalized_evidence_bundle, allowed_source_ids, token_ceiling, cost_ceiling_usd,
    timeout_ms, required_output_schema, confidentiality_class, input_fingerprint, scenario_hint
  ) VALUES (
    p_run_id, v_stage_id, q.question_id, p_stage, v_model, 'prompt-v1',
    v_bundle, v_sources, run.token_ceiling, run.cost_ceiling_usd,
    5000, p_stage || '_schema_v1', q.confidentiality_class, v_in_fp,
    COALESCE(p_scenario_hint, run.scenario_mode)
  ) RETURNING id INTO v_req_id;

  v_resp_id := research.mock_adapter_invoke(v_req_id);
  SELECT * INTO resp FROM research.provider_adapter_responses WHERE id = v_resp_id;

  UPDATE research.research_run_stages
  SET request_id = v_req_id,
      response_id = v_resp_id,
      output_fingerprint = resp.output_fingerprint,
      status = CASE WHEN resp.finish_reason = 'success' THEN 'succeeded' ELSE 'failed' END,
      finished_at = NOW()
  WHERE id = v_stage_id;

  IF resp.finish_reason = 'success' THEN
    UPDATE research.research_runs
    SET output_fingerprints = output_fingerprints || jsonb_build_object(p_stage || ':' || v_attempt, resp.output_fingerprint),
        updated_at = NOW()
    WHERE id = p_run_id;
    PERFORM research._append_completed_stage(p_run_id, p_stage);
    RETURN 'succeeded';
  END IF;

  -- Failure path + repair policy
  SELECT failure_class INTO v_prior_fail
  FROM research.repair_attempts
  WHERE run_id = p_run_id AND stage = p_stage
  ORDER BY attempt_number DESC
  LIMIT 1;

  IF resp.failure_class IS NOT NULL AND p_stage IN ('qa_checker','researcher','planner','implementation_proposal_writer') THEN
    -- unsupported claim / invalid schema / timeout: fail closed (unless repairable QA)
    IF resp.failure_class IN ('unsupported_citation','invalid_schema','budget_blocked','timeout','rate_limited')
       AND p_stage <> 'qa_checker' THEN
      PERFORM research._record_failure(p_run_id, p_stage, resp.failure_class, coalesce(resp.structured_output::text, resp.failure_class));
      RETURN 'failed';
    END IF;
  END IF;

  IF p_stage = 'qa_checker' AND resp.failure_class IS NOT NULL THEN
    IF run.repair_attempt_count >= run.max_repair_attempts THEN
      INSERT INTO research.repair_attempts (run_id, stage, attempt_number, failure_class, prior_failure_class, same_as_prior, outcome, detail)
      VALUES (p_run_id, p_stage, LEAST(run.repair_attempt_count + 1, 2), resp.failure_class, v_prior_fail,
              (v_prior_fail IS NOT DISTINCT FROM resp.failure_class), 'escalated_budget', 'max repair attempts reached');
      PERFORM research._record_failure(p_run_id, p_stage, 'stagnation', 'max repair attempts (2) exhausted');
      RETURN 'failed';
    END IF;

    IF v_prior_fail IS NOT DISTINCT FROM resp.failure_class AND run.repair_attempt_count >= 1 THEN
      INSERT INTO research.repair_attempts (run_id, stage, attempt_number, failure_class, prior_failure_class, same_as_prior, outcome, detail)
      VALUES (p_run_id, p_stage, run.repair_attempt_count + 1, resp.failure_class, v_prior_fail, TRUE, 'escalated_same_failure', 'same failure twice');
      PERFORM research._record_failure(p_run_id, p_stage, 'stagnation', 'same failure twice — stop and escalate');
      RETURN 'failed';
    END IF;

    INSERT INTO research.repair_attempts (run_id, stage, attempt_number, failure_class, prior_failure_class, same_as_prior, outcome, detail)
    VALUES (p_run_id, p_stage, run.repair_attempt_count + 1, resp.failure_class, v_prior_fail, FALSE, 'repaired', 'debugger recommends bounded retry');

    UPDATE research.research_runs
    SET status = 'repair_required',
        repair_attempt_count = repair_attempt_count + 1,
        failed_stage = p_stage,
        -- allow QA to be retried: remove from completed if present (should not be)
        completed_stages = array_remove(completed_stages, 'qa_checker'),
        scenario_mode = CASE
          WHEN scenario_mode = 'qa_reject_then_repair' THEN 'success'
          ELSE scenario_mode
        END,
        updated_at = NOW()
    WHERE id = p_run_id;

    -- debugger stage (recommendation only)
    PERFORM research.run_stage(p_run_id, 'debugger', 'success');
    RETURN 'repair_required';
  END IF;

  IF p_stage = 'independent_reviewer' AND resp.failure_class IS NOT NULL THEN
    PERFORM research._record_failure(p_run_id, p_stage, resp.failure_class, 'reviewer rejection stands; writer cannot overwrite');
    RETURN 'failed';
  END IF;

  PERFORM research._record_failure(p_run_id, p_stage, COALESCE(resp.failure_class, 'mock_failure'), coalesce(resp.structured_output::text, 'stage failed'));
  RETURN 'failed';
END;
$$;

-- Materialize proposal from successful writer output (only when citations valid)
CREATE OR REPLACE FUNCTION research.materialize_proposal_from_run(p_run_id UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  run research.research_runs%ROWTYPE;
  q research.research_questions%ROWTYPE;
  resp research.provider_adapter_responses%ROWTYPE;
  v_pid UUID;
  v_eids UUID[];
  v_code TEXT;
BEGIN
  SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
  IF NOT ('implementation_proposal_writer' = ANY(run.completed_stages)) THEN
    RAISE EXCEPTION 'cannot materialize proposal: writer stage incomplete';
  END IF;
  IF run.status IN ('failed','blocked','cancelled') THEN
    RAISE EXCEPTION 'cannot materialize proposal from incomplete/failed run';
  END IF;

  SELECT * INTO q FROM research.research_questions WHERE id = run.question_uuid;
  SELECT r.* INTO resp
  FROM research.provider_adapter_responses r
  JOIN research.research_run_stages s ON s.response_id = r.id
  WHERE s.run_id = p_run_id AND s.stage = 'implementation_proposal_writer' AND s.status = 'succeeded'
  ORDER BY s.attempt_number DESC
  LIMIT 1;

  IF resp.failure_class IS NOT NULL OR resp.finish_reason <> 'success' THEN
    RAISE EXCEPTION 'writer response not successful';
  END IF;

  v_eids := resp.cited_evidence_ids;
  IF v_eids IS NULL OR array_length(v_eids, 1) IS NULL THEN
    RAISE EXCEPTION 'unsupported claims: proposal lacks evidence IDs';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(v_eids) eid
    WHERE NOT EXISTS (SELECT 1 FROM research.evidence_items ei WHERE ei.id = eid)
  ) THEN
    RAISE EXCEPTION 'unsupported citation: evidence id not found';
  END IF;

  v_code := 'PROP-' || run.run_code;
  INSERT INTO research.improvement_proposals (
    proposal_code, question_id, title, one_sentence, expected_benefit, risk, estimated_size, status, current_version
  ) VALUES (
    v_code, q.id,
    COALESCE(resp.structured_output->>'title', 'Proposal'),
    COALESCE(resp.structured_output->>'one_sentence', 'Recommendation'),
    COALESCE(resp.structured_output->>'expected_benefit', 'n/a'),
    COALESCE(resp.structured_output->>'risk', 'n/a'),
    COALESCE(resp.structured_output->>'estimated_size', 'S'),
    'draft', 1
  )
  ON CONFLICT (proposal_code) DO UPDATE SET title = EXCLUDED.title
  RETURNING id INTO v_pid;

  INSERT INTO research.proposal_versions (proposal_id, version_number, body, evidence_ids)
  VALUES (
    v_pid, 1,
    COALESCE(resp.structured_output->>'body', resp.structured_output::text),
    v_eids
  )
  ON CONFLICT (proposal_id, version_number) DO NOTHING;

  RETURN v_pid;
END;
$$;

CREATE OR REPLACE FUNCTION research.build_decision_card(p_run_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
  run research.research_runs%ROWTYPE;
  q research.research_questions%ROWTYPE;
  p research.improvement_proposals%ROWTYPE;
  v_support TEXT;
  v_contra TEXT;
  v_qa NUMERIC;
  v_review TEXT;
  v_priors JSONB;
  v_card JSONB;
BEGIN
  SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
  IF run.status <> 'decision_ready' THEN
    RAISE EXCEPTION 'decision card only for decision_ready runs (got %)', run.status;
  END IF;
  SELECT * INTO q FROM research.research_questions WHERE id = run.question_uuid;
  SELECT * INTO p FROM research.improvement_proposals WHERE question_id = q.id ORDER BY created_at DESC LIMIT 1;

  SELECT ei.quoted_excerpt INTO v_support
  FROM research.evidence_claim_links l
  JOIN research.evidence_items ei ON ei.id = l.evidence_id
  WHERE l.question_id = q.id AND l.stance = 'supports'
  ORDER BY ei.confidence_score DESC NULLS LAST
  LIMIT 1;

  SELECT ei.quoted_excerpt INTO v_contra
  FROM research.evidence_claim_links l
  JOIN research.evidence_items ei ON ei.id = l.evidence_id
  WHERE l.question_id = q.id AND l.stance = 'contradicts'
  ORDER BY ei.confidence_score DESC NULLS LAST
  LIMIT 1;

  SELECT (r.structured_output->>'score')::numeric INTO v_qa
  FROM research.provider_adapter_responses r
  JOIN research.research_run_stages s ON s.response_id = r.id
  WHERE s.run_id = p_run_id AND s.stage = 'qa_checker' AND s.status = 'succeeded'
  ORDER BY s.attempt_number DESC LIMIT 1;

  SELECT r.structured_output->>'verdict' INTO v_review
  FROM research.provider_adapter_responses r
  JOIN research.research_run_stages s ON s.response_id = r.id
  WHERE s.run_id = p_run_id AND s.stage = 'independent_reviewer' AND s.status = 'succeeded'
  ORDER BY s.attempt_number DESC LIMIT 1;

  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'decision', x.decision, 'rationale', x.concise_rationale, 'at', x.created_at
  ) ORDER BY x.created_at DESC), '[]'::jsonb)
  INTO v_priors
  FROM (
    SELECT d.decision, dr.concise_rationale, d.created_at
    FROM research.taha_decisions d
    JOIN research.improvement_proposals ip ON ip.id = d.proposal_id
    LEFT JOIN research.decision_rationales dr ON dr.decision_id = d.id
    JOIN research.research_questions rq ON rq.id = ip.question_id
    WHERE rq.question_class = q.question_class
    ORDER BY d.created_at DESC
    LIMIT 5
  ) x;

  v_card := jsonb_build_object(
    'one_sentence_question', left(q.precise_question, 280),
    'recommendation', COALESCE(p.one_sentence, 'n/a'),
    'strongest_supporting_evidence', COALESCE(v_support, 'n/a'),
    'strongest_contradictory_evidence', COALESCE(v_contra, 'n/a'),
    'expected_benefit', COALESCE(p.expected_benefit, 'n/a'),
    'risk', COALESCE(p.risk, 'n/a'),
    'estimated_implementation_size', COALESCE(p.estimated_size, 'n/a'),
    'prior_related_decisions', COALESCE(v_priors, '[]'::jsonb),
    'decision_options', jsonb_build_array('approved','rejected','deferred','research_more','superseded'),
    'qa_score', v_qa,
    'independent_review_verdict', v_review,
    'note', 'Simulation only — no Taha decision recorded'
  );

  UPDATE research.research_runs SET decision_card = v_card, updated_at = NOW() WHERE id = p_run_id;
  RETURN v_card;
END;
$$;

-- Full pipeline orchestration (stops on failure; no Taha decision write)
CREATE OR REPLACE FUNCTION research.orchestrate_research_run(p_run_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  run research.research_runs%ROWTYPE;
  q research.research_questions%ROWTYPE;
  v_res TEXT;
  v_pid UUID;
  stages TEXT[] := ARRAY[
    'researcher','planner','implementation_proposal_writer','qa_checker','independent_reviewer'
  ];
  st TEXT;
BEGIN
  SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
  IF run.cancelled THEN
    PERFORM research._record_failure(p_run_id, run.current_stage, 'cancelled', 'cancelled before start');
    RETURN 'cancelled';
  END IF;

  SELECT * INTO q FROM research.research_questions WHERE id = run.question_uuid;

  -- Lifecycle: approved_for_research -> active if needed
  IF q.status = 'approved_for_research' THEN
    UPDATE research.research_questions
    SET status = 'active', priority_rationale = 'round3 orchestration start'
    WHERE id = q.id;
  ELSIF q.status NOT IN ('active','evidence_review') THEN
    -- allow resume from active/evidence_review only for orchestration
    IF q.status <> 'decision_required' THEN
      RAISE EXCEPTION 'question % must be approved_for_research or active (got %)', q.question_id, q.status;
    END IF;
  END IF;

  UPDATE research.research_runs SET status = 'running', updated_at = NOW() WHERE id = p_run_id;

  FOREACH st IN ARRAY stages LOOP
    SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
    IF run.status IN ('failed','blocked','cancelled') THEN
      RETURN run.status;
    END IF;
    IF st = ANY(run.completed_stages) THEN
      CONTINUE; -- resume without duplicating
    END IF;

    IF st = 'qa_checker' THEN
      UPDATE research.research_runs SET status = 'awaiting_qa', updated_at = NOW() WHERE id = p_run_id;
    ELSIF st = 'independent_reviewer' THEN
      UPDATE research.research_runs SET status = 'awaiting_review', updated_at = NOW() WHERE id = p_run_id;
    END IF;

    -- unsupported claim: fail before proposal materialization
    IF st = 'implementation_proposal_writer' AND run.scenario_mode = 'unsupported_claim' THEN
      v_res := research.run_stage(p_run_id, st, 'unsupported_claim');
      RETURN 'failed';
    END IF;

    v_res := research.run_stage(p_run_id, st, NULL);
    IF v_res = 'repair_required' THEN
      -- after debugger, retry QA; scenario_mode flip (if any) controls success vs repeat fail
      SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
      IF run.status = 'failed' THEN RETURN 'failed'; END IF;
      v_res := research.run_stage(p_run_id, 'qa_checker', NULL);
      IF v_res <> 'succeeded' THEN
        SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
        RETURN run.status;
      END IF;
    ELSIF v_res <> 'succeeded' AND v_res <> 'duplicate_prevented' THEN
      SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
      RETURN run.status;
    END IF;

    IF st = 'implementation_proposal_writer' THEN
      BEGIN
        v_pid := research.materialize_proposal_from_run(p_run_id);
      EXCEPTION WHEN OTHERS THEN
        PERFORM research._record_failure(p_run_id, st, 'unsupported_citation', SQLERRM);
        RETURN 'failed';
      END;
    END IF;
  END LOOP;

  SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
  IF run.status IN ('failed','blocked','cancelled') THEN
    RETURN run.status;
  END IF;

  -- Partial guard: all core stages must be completed
  IF NOT (
    'researcher' = ANY(run.completed_stages)
    AND 'planner' = ANY(run.completed_stages)
    AND 'implementation_proposal_writer' = ANY(run.completed_stages)
    AND 'qa_checker' = ANY(run.completed_stages)
    AND 'independent_reviewer' = ANY(run.completed_stages)
  ) THEN
    PERFORM research._record_failure(p_run_id, 'finalizer', 'partial_blocked', 'partial results cannot enter decision queue');
    RETURN 'failed';
  END IF;

  -- Move question: active -> evidence_review -> decision_required
  SELECT status INTO q.status FROM research.research_questions WHERE id = run.question_uuid;
  IF q.status = 'active' THEN
    UPDATE research.research_questions
    SET status = 'evidence_review', priority_rationale = 'round3 evidence review'
    WHERE id = run.question_uuid;
  END IF;

  UPDATE research.improvement_proposals
  SET status = 'ready_for_decision'
  WHERE question_id = run.question_uuid
    AND status = 'draft';

  UPDATE research.research_questions
  SET status = 'decision_required', priority_rationale = 'round3 decision card ready'
  WHERE id = run.question_uuid
    AND status = 'evidence_review';

  UPDATE research.research_runs
  SET status = 'decision_ready',
      final_status = 'decision_ready',
      current_stage = 'finalizer',
      updated_at = NOW()
  WHERE id = p_run_id;

  PERFORM research._append_completed_stage(p_run_id, 'finalizer');
  PERFORM research.build_decision_card(p_run_id);

  RETURN 'decision_ready';
END;
$$;

-- Cancel run: preserve evidence, stop execution
CREATE OR REPLACE FUNCTION research.cancel_research_run(p_run_id UUID, p_reason TEXT)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE research.research_runs
  SET cancelled = TRUE,
      status = 'cancelled',
      final_status = 'cancelled',
      updated_at = NOW()
  WHERE id = p_run_id;
  INSERT INTO research.orchestration_failures (run_id, stage, failure_class, detail)
  VALUES (p_run_id, NULL, 'cancelled', COALESCE(p_reason, 'cancelled by operator'));
END;
$$;

-- Explicit partial finalize attempt must fail
CREATE OR REPLACE FUNCTION research.try_enter_decision_from_partial(p_run_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  run research.research_runs%ROWTYPE;
BEGIN
  SELECT * INTO run FROM research.research_runs WHERE id = p_run_id;
  IF NOT (
    'researcher' = ANY(run.completed_stages)
    AND 'planner' = ANY(run.completed_stages)
    AND 'implementation_proposal_writer' = ANY(run.completed_stages)
    AND 'qa_checker' = ANY(run.completed_stages)
    AND 'independent_reviewer' = ANY(run.completed_stages)
  ) THEN
    PERFORM research._record_failure(p_run_id, 'finalizer', 'partial_blocked', 'blocked partial decision_required');
    RETURN 'blocked_partial';
  END IF;
  RETURN 'ok';
END;
$$;

-- View: decision cards awaiting Taha (simulation; no decision row)
CREATE OR REPLACE VIEW research.v_simulated_decision_cards AS
SELECT
  r.run_code,
  q.question_id,
  q.precise_question,
  r.status AS run_status,
  r.decision_card,
  r.completed_stages,
  r.repair_attempt_count,
  r.created_at
FROM research.research_runs r
JOIN research.research_questions q ON q.id = r.question_uuid
WHERE r.status = 'decision_ready';

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA research TO research_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA research TO research_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA research TO research_app;
GRANT SELECT ON ALL TABLES IN SCHEMA research TO n8n_app;

INSERT INTO research.schema_version (version, note) VALUES
  (4, 'Round 3: simulated multi-model research orchestration (mock adapters only)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
