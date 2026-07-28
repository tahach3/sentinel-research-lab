-- Constraint / view verification for Round 1 (expect specific failures)
\set ON_ERROR_STOP on

-- 1) Negative tokens rejected
DO $$
DECLARE
  ok BOOLEAN := FALSE;
  pid UUID;
  mid UUID;
  cid UUID;
BEGIN
  SELECT id INTO pid FROM research.providers LIMIT 1;
  SELECT id INTO mid FROM research.models LIMIT 1;
  SELECT id INTO cid FROM research.benchmark_cases LIMIT 1;
  BEGIN
    INSERT INTO research.benchmark_runs (
      case_id, model_id, execution_identity, status, prompt_version, input_fingerprint, prompt_tokens
    ) VALUES (
      cid, mid, 'test-negative-tokens', 'pending', 'bench-prompt-v1',
      repeat('a', 64), -1
    );
  EXCEPTION WHEN check_violation THEN
    ok := TRUE;
  END;
  IF NOT ok THEN
    RAISE EXCEPTION 'TEST FAIL: negative tokens were accepted';
  END IF;
  RAISE NOTICE 'PASS: negative tokens rejected';
END $$;

-- 2) Negative cost rejected
DO $$
DECLARE
  ok BOOLEAN := FALSE;
  mid UUID;
  cid UUID;
BEGIN
  SELECT id INTO mid FROM research.models LIMIT 1;
  SELECT id INTO cid FROM research.benchmark_cases LIMIT 1;
  BEGIN
    INSERT INTO research.benchmark_runs (
      case_id, model_id, execution_identity, status, prompt_version, input_fingerprint, cost_usd_estimate
    ) VALUES (
      cid, mid, 'test-negative-cost', 'pending', 'bench-prompt-v1',
      repeat('b', 64), -0.01
    );
  EXCEPTION WHEN check_violation THEN
    ok := TRUE;
  END;
  IF NOT ok THEN
    RAISE EXCEPTION 'TEST FAIL: negative cost was accepted';
  END IF;
  RAISE NOTICE 'PASS: negative cost rejected';
END $$;

-- 3) Invalid score range rejected
DO $$
DECLARE
  ok BOOLEAN := FALSE;
  mid UUID;
  cid UUID;
  rid UUID;
BEGIN
  SELECT id INTO mid FROM research.models LIMIT 1;
  SELECT id INTO cid FROM research.benchmark_cases LIMIT 1;
  INSERT INTO research.benchmark_runs (
    case_id, model_id, execution_identity, status, prompt_version, input_fingerprint
  ) VALUES (
    cid, mid, 'test-score-range-run', 'pending', 'bench-prompt-v1', repeat('c', 64)
  ) RETURNING id INTO rid;
  BEGIN
    INSERT INTO research.automatic_scores (run_id, scorer_version, dimension, score)
    VALUES (rid, 'test', 'factual_accuracy', 101);
  EXCEPTION WHEN check_violation THEN
    ok := TRUE;
  END;
  IF NOT ok THEN
    RAISE EXCEPTION 'TEST FAIL: out-of-range score accepted';
  END IF;
  RAISE NOTICE 'PASS: invalid score range rejected';
END $$;

-- 4) Duplicate execution identity rejected
DO $$
DECLARE
  ok BOOLEAN := FALSE;
  mid UUID;
  cid UUID;
BEGIN
  SELECT id INTO mid FROM research.models LIMIT 1;
  SELECT id INTO cid FROM research.benchmark_cases LIMIT 1;
  INSERT INTO research.benchmark_runs (
    case_id, model_id, execution_identity, status, prompt_version, input_fingerprint
  ) VALUES (
    cid, mid, 'test-dup-identity', 'pending', 'bench-prompt-v1', repeat('d', 64)
  );
  BEGIN
    INSERT INTO research.benchmark_runs (
      case_id, model_id, execution_identity, status, prompt_version, input_fingerprint
    ) VALUES (
      cid, mid, 'test-dup-identity', 'pending', 'bench-prompt-v1', repeat('e', 64)
    );
  EXCEPTION WHEN unique_violation THEN
    ok := TRUE;
  END;
  IF NOT ok THEN
    RAISE EXCEPTION 'TEST FAIL: duplicate execution_identity accepted';
  END IF;
  RAISE NOTICE 'PASS: duplicate execution identity rejected';
END $$;

-- 5) Ranking without evidence threshold rejected
DO $$
DECLARE
  ok BOOLEAN := FALSE;
  mid UUID;
BEGIN
  SELECT id INTO mid FROM research.models LIMIT 1;
  BEGIN
    INSERT INTO research.monthly_role_rankings (
      role_code, year_month, model_id, rank, composite_score, evidence_sufficient,
      case_count, adversarial_count, technical_failure_rate, unresolved_critical_safety_count, formula_version
    ) VALUES (
      'researcher', '2026-07', mid, 1, 90, TRUE,
      3, 0, 0.0, 0, 'rank-v1'
    );
  EXCEPTION WHEN check_violation THEN
    ok := TRUE;
  END;
  IF NOT ok THEN
    RAISE EXCEPTION 'TEST FAIL: insufficient ranking accepted';
  END IF;
  RAISE NOTICE 'PASS: insufficient ranking rejected';
END $$;

-- 6) Completed run without output rejected
DO $$
DECLARE
  ok BOOLEAN := FALSE;
  mid UUID;
  cid UUID;
  rid UUID;
BEGIN
  SELECT id INTO mid FROM research.models LIMIT 1;
  SELECT id INTO cid FROM research.benchmark_cases LIMIT 1;
  INSERT INTO research.benchmark_runs (
    case_id, model_id, execution_identity, status, prompt_version, input_fingerprint
  ) VALUES (
    cid, mid, 'test-complete-no-output', 'pending', 'bench-prompt-v1', repeat('f', 64)
  ) RETURNING id INTO rid;
  BEGIN
    UPDATE research.benchmark_runs SET status = 'completed', completed_at = NOW() WHERE id = rid;
  EXCEPTION WHEN OTHERS THEN
    ok := TRUE;
  END;
  IF NOT ok THEN
    RAISE EXCEPTION 'TEST FAIL: completed without output accepted';
  END IF;
  RAISE NOTICE 'PASS: completed without output rejected';
END $$;

-- 7) Views selectable
SELECT COUNT(*) AS perf_rows FROM research.v_provider_performance_by_role;
SELECT COUNT(*) AS cost_rows FROM research.v_cost_per_successful_run;
SELECT COUNT(*) AS fail_rows FROM research.v_failure_rate;
SELECT COUNT(*) AS lat_rows FROM research.v_latency_percentile_summary;
SELECT COUNT(*) AS rank_rows FROM research.v_latest_monthly_ranking;
SELECT COUNT(*) AS warn_rows FROM research.v_insufficient_evidence_warning;

-- 8) Case counts per role = 3
SELECT s.role_code, COUNT(*) AS case_count
FROM research.benchmark_cases c
JOIN research.benchmark_suites s ON s.id = c.suite_id
GROUP BY s.role_code
ORDER BY s.role_code;

SELECT 'ALL_CONSTRAINT_TESTS_SECTION_DONE' AS marker;
