-- Round 5A: Gemini bounded pilot preparation (no live calls; provider/model remain disabled)
BEGIN;

-- Policy verification ledger (official sources only; no secrets)
CREATE TABLE IF NOT EXISTS research.provider_policy_verifications (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id         UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  verified_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model_identifier    TEXT NOT NULL,
  official_sources    JSONB NOT NULL,
  verified_facts      JSONB NOT NULL,
  unverified_or_account_dependent JSONB NOT NULL,
  model_selection_rationale TEXT NOT NULL,
  free_tier_available BOOLEAN NOT NULL,
  billing_required_for_free_tier BOOLEAN NOT NULL,
  pakistan_available  BOOLEAN,
  grounding_free_tier_notes TEXT,
  privacy_notes       TEXT NOT NULL,
  blocked_provider_policy BOOLEAN NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research.provider_pilot_proposals (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pilot_code                TEXT NOT NULL UNIQUE,
  provider_id               UUID NOT NULL REFERENCES research.providers(id) ON DELETE RESTRICT,
  model_candidate_id        UUID NOT NULL REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT,
  policy_verification_id    UUID NOT NULL REFERENCES research.provider_policy_verifications(id) ON DELETE RESTRICT,
  benchmark_case_ids        UUID[] NOT NULL,
  benchmark_case_codes      TEXT[] NOT NULL,
  max_successful_calls      INTEGER NOT NULL DEFAULT 3 CHECK (max_successful_calls = 3),
  max_attempts_per_case     INTEGER NOT NULL DEFAULT 1 CHECK (max_attempts_per_case = 1),
  max_total_requests        INTEGER NOT NULL DEFAULT 3 CHECK (max_total_requests = 3),
  max_total_input_tokens    INTEGER NOT NULL CHECK (max_total_input_tokens > 0),
  max_total_output_tokens   INTEGER NOT NULL CHECK (max_total_output_tokens > 0),
  max_authorized_cost_usd   NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (max_authorized_cost_usd = 0),
  retries_allowed           BOOLEAN NOT NULL DEFAULT FALSE CHECK (retries_allowed = FALSE),
  fallback_provider_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (fallback_provider_allowed = FALSE),
  confidentiality_class     TEXT NOT NULL DEFAULT 'public_or_synthetic'
    CHECK (confidentiality_class = 'public_or_synthetic'),
  approving_authority       TEXT NOT NULL DEFAULT 'Taha' CHECK (approving_authority = 'Taha'),
  expiry_hours_after_approval INTEGER NOT NULL DEFAULT 24,
  status                    TEXT NOT NULL DEFAULT 'proposed',
  taha_approved_at          TIMESTAMPTZ,
  expires_at                TIMESTAMPTZ,
  notes                     TEXT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ppp_status_check CHECK (status IN (
    'proposed','awaiting_taha_credential','awaiting_taha_approval','approved','rejected','expired','cancelled'
  )),
  CONSTRAINT ppp_three_cases CHECK (
    cardinality(benchmark_case_ids) = 3 AND cardinality(benchmark_case_codes) = 3
  ),
  CONSTRAINT ppp_not_live_yet CHECK (status <> 'approved' OR taha_approved_at IS NOT NULL)
);

-- Per-case proposed authorization shells (inactive until Taha approval; not executable)
ALTER TABLE research.provider_authorization_records
  DROP CONSTRAINT IF EXISTS par_status_check;
ALTER TABLE research.provider_authorization_records
  ADD CONSTRAINT par_status_check CHECK (status IN (
    'proposed','active','revoked','exhausted','expired'
  ));

ALTER TABLE research.provider_authorization_records
  ADD COLUMN IF NOT EXISTS pilot_proposal_id UUID REFERENCES research.provider_pilot_proposals(id) ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS research.gemini_pilot_request_builder_specs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pilot_code      TEXT NOT NULL UNIQUE,
  adapter_version TEXT NOT NULL DEFAULT 'r4-disabled-v1',
  model_identifier TEXT NOT NULL,
  path_template   TEXT NOT NULL,
  live_execution_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (live_execution_allowed = FALSE),
  grounding_enabled BOOLEAN NOT NULL DEFAULT FALSE CHECK (grounding_enabled = FALSE),
  request_shape   JSONB NOT NULL,
  response_parser TEXT NOT NULL DEFAULT 'research.parse_provider_fixture_response',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Seed verification + update Gemini model metadata (remain DISABLED)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  v_provider UUID;
  v_model UUID;
  v_ver UUID;
  v_pilot UUID;
  v_cases UUID[];
  v_codes TEXT[] := ARRAY['R-N-01','R-A-01','R-X-01'];
  v_case UUID;
  v_i INT;
  v_verified_at TIMESTAMPTZ := TIMESTAMPTZ '2026-07-28 10:40:00+05';
BEGIN
  SELECT id INTO v_provider FROM research.providers WHERE code = 'gemini';
  IF v_provider IS NULL THEN
    RAISE EXCEPTION 'gemini provider missing';
  END IF;

  -- Ensure provider stays disabled
  UPDATE research.providers
  SET enabled = FALSE,
      notes = 'Round 5A: Gemini pilot prepared; remains DISABLED until Taha credential + approval',
      updated_at = NOW()
  WHERE id = v_provider;

  UPDATE research.provider_model_candidates
  SET model_id_provisional = 'gemini-2.5-flash',
      display_name = 'Gemini 2.5 Flash (verified identifier; disabled)',
      enabled = FALSE,
      verification_status = 'verified',
      free_tier_status = 'free_confirmed',
      notes = 'Verified 2026-07-28 from ai.google.dev pricing/models; free-tier input/output free of charge; grounding disabled for this pilot; model remains DISABLED',
      updated_at = NOW()
  WHERE provider_id = v_provider;

  SELECT id INTO v_model FROM research.provider_model_candidates WHERE provider_id = v_provider LIMIT 1;

  INSERT INTO research.provider_capabilities (
    provider_id, capability_code, claim_text, claim_source, verification_date, verified
  ) VALUES
    (v_provider, 'chat_completions', 'Gemini API text generation via generateContent / chat-style APIs',
     'https://ai.google.dev/gemini-api/docs/models', DATE '2026-07-28', TRUE),
    (v_provider, 'free_tier_text', 'gemini-2.5-flash Standard Free Tier input/output listed Free of charge',
     'https://ai.google.dev/gemini-api/docs/pricing', DATE '2026-07-28', TRUE),
    (v_provider, 'grounding_google_search', 'Grounding with Google Search available on free tier up to shared RPD limits for 2.5 Flash; NOT enabled for Round 5A pilot',
     'https://ai.google.dev/gemini-api/docs/pricing', DATE '2026-07-28', TRUE)
  ON CONFLICT (provider_id, capability_code) DO UPDATE SET
    claim_text = EXCLUDED.claim_text,
    claim_source = EXCLUDED.claim_source,
    verification_date = EXCLUDED.verification_date,
    verified = EXCLUDED.verified;

  INSERT INTO research.provider_policy_verifications (
    provider_id, verified_at, model_identifier, official_sources, verified_facts,
    unverified_or_account_dependent, model_selection_rationale,
    free_tier_available, billing_required_for_free_tier, pakistan_available,
    grounding_free_tier_notes, privacy_notes, blocked_provider_policy
  ) VALUES (
    v_provider,
    v_verified_at,
    'gemini-2.5-flash',
    jsonb_build_array(
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/billing','retrieved_at',v_verified_at,'topic','free_tier_and_billing'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/pricing','retrieved_at',v_verified_at,'topic','model_pricing_free_tier'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/models','retrieved_at',v_verified_at,'topic','model_catalog'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/rate-limits','retrieved_at',v_verified_at,'topic','rate_limits'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/api-key','retrieved_at',v_verified_at,'topic','api_key_creation'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/terms','retrieved_at',v_verified_at,'topic','privacy_unpaid_services'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/available-regions','retrieved_at',v_verified_at,'topic','regional_availability'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/troubleshooting','retrieved_at',v_verified_at,'topic','429_behavior'),
      jsonb_build_object('url','https://ai.google.dev/gemini-api/docs/grounding','retrieved_at',v_verified_at,'topic','grounding')
    ),
    jsonb_build_object(
      'free_tier_exists', true,
      'billing_required_for_free_tier', false,
      'model_id', 'gemini-2.5-flash',
      'free_tier_input_output', 'Free of charge per pricing page for Standard Free Tier',
      'pakistan_listed_in_available_regions', true,
      'unpaid_data_use_improves_google_products', true,
      'human_reviewers_may_read_unpaid_io', true,
      'rate_limit_error', '429 RESOURCE_EXHAUSTED',
      'api_key_created_in_ai_studio', true,
      'grounding_on_2_5_flash_free', 'Free of charge up to 500 RPD shared with Flash-Lite; pilot disables grounding'
    ),
    jsonb_build_object(
      'exact_rpm_tpm_rpd_for_new_project', 'Account/tier specific; view in Google AI Studio Rate Limit page; not guaranteed capacity',
      'whether_taha_account_still_has_free_quota', 'Depends on Taha Google account/project at approval time',
      'grounding_shared_rpd_remaining', 'Account-dependent; pilot sets grounding_enabled=false'
    ),
    'Selected gemini-2.5-flash: official pricing lists Standard Free Tier input/output as Free of charge; hybrid reasoning + 1M context suitable for research synthesis; gemini-2.0-flash is deprecated/shut down; gemini-3.6-flash also free but pilot prefers 2.5-flash documented free grounding limits while keeping grounding OFF for $0 synthetic-only pilot.',
    TRUE,
    FALSE,
    TRUE,
    'Grounding with Google Search is free of charge on Free Tier for gemini-2.5-flash up to 500 RPD (shared). Round 5A pilot disables grounding to avoid search side effects and keep synthetic-only inputs.',
    'Unpaid Services (free-tier Gemini API): Google uses submitted content and generated responses to provide, improve, and develop Google products/ML; human reviewers may read/annotate after disconnecting from account identifiers. Do not submit sensitive/confidential/personal information. Pakistan is outside EEA/UK/CH unpaid exception region, so unpaid data-use terms apply.',
    FALSE
  ) RETURNING id INTO v_ver;

  SELECT array_agg(id ORDER BY array_position(v_codes, case_code))
  INTO v_cases
  FROM research.benchmark_cases
  WHERE case_code = ANY (v_codes);

  IF cardinality(v_cases) <> 3 THEN
    RAISE EXCEPTION 'expected researcher cases R-N-01, R-A-01, R-X-01';
  END IF;

  INSERT INTO research.provider_pilot_proposals (
    pilot_code, provider_id, model_candidate_id, policy_verification_id,
    benchmark_case_ids, benchmark_case_codes,
    max_successful_calls, max_attempts_per_case, max_total_requests,
    max_total_input_tokens, max_total_output_tokens, max_authorized_cost_usd,
    retries_allowed, fallback_provider_allowed, confidentiality_class,
    approving_authority, expiry_hours_after_approval, status, notes
  ) VALUES (
    'GEMINI-PILOT-5A',
    v_provider,
    v_model,
    v_ver,
    v_cases,
    v_codes,
    3, 1, 3,
    8000, 4000, 0,
    FALSE, FALSE, 'public_or_synthetic',
    'Taha', 24, 'awaiting_taha_credential',
    'Proposed bounded Gemini free-tier pilot. Not approved. Provider and model DISABLED. No live calls.'
  )
  ON CONFLICT (pilot_code) DO UPDATE SET
    model_candidate_id = EXCLUDED.model_candidate_id,
    policy_verification_id = EXCLUDED.policy_verification_id,
    benchmark_case_ids = EXCLUDED.benchmark_case_ids,
    status = 'awaiting_taha_credential',
    updated_at = NOW()
  RETURNING id INTO v_pilot;

  -- Proposed per-case authorization shells (no delete; append if missing)
  FOR v_i IN 1..3 LOOP
    v_case := v_cases[v_i];
    IF NOT EXISTS (
      SELECT 1 FROM research.provider_authorization_records a
      WHERE a.pilot_proposal_id = v_pilot
        AND a.benchmark_case_id = v_case
        AND a.status = 'proposed'
    ) THEN
      INSERT INTO research.provider_authorization_records (
        provider_id, model_candidate_id, benchmark_case_id,
        max_requests, max_tokens, max_cost_usd, expires_at,
        approving_authority, status, pilot_proposal_id
      ) VALUES (
        v_provider, v_model, v_case,
        1, 4000, 0,
        NOW() + INTERVAL '365 days',
        'Taha', 'proposed', v_pilot
      );
    END IF;
  END LOOP;

  INSERT INTO research.gemini_pilot_request_builder_specs (
    pilot_code, model_identifier, path_template, live_execution_allowed, grounding_enabled, request_shape
  ) VALUES (
    'GEMINI-PILOT-5A',
    'gemini-2.5-flash',
    '/v1beta/models/gemini-2.5-flash:generateContent',
    FALSE,
    FALSE,
    jsonb_build_object(
      'provider', 'gemini',
      'model', 'gemini-2.5-flash',
      'headers', jsonb_build_object('content-type','application/json','x-goog-api-key','{{n8n_credential_only}}'),
      'body_template', jsonb_build_object(
        'contents', jsonb_build_array(jsonb_build_object('parts', jsonb_build_array(jsonb_build_object('text','{{prompt}}'))))
      ),
      'tools', jsonb_build_array(),
      'note', 'Non-executable until all Round 4/5A gates pass; no HTTP in Round 5A'
    )
  )
  ON CONFLICT (pilot_code) DO UPDATE SET
    model_identifier = EXCLUDED.model_identifier,
    request_shape = EXCLUDED.request_shape;

  -- Credential status remains missing
  UPDATE research.provider_credential_status
  SET status = 'missing',
      n8n_credential_label = NULL,
      notes = 'Awaiting Taha to create n8n credential sentinel-research-lab-gemini-pilot (secret never stored here)',
      last_checked_at = NOW()
  WHERE provider_id = v_provider;

  -- Budget remains hard-closed at $0 / free_only
  UPDATE research.provider_budget_policies
  SET free_only = TRUE,
      paid_fallback = FALSE,
      paid_usage_authorized = FALSE,
      daily_cost_limit_usd = 0,
      monthly_cost_ceiling_usd = 0,
      daily_request_cap = 0,
      daily_token_cap = 0,
      updated_at = NOW()
  WHERE provider_id = v_provider;
END $$;

-- Gate helper: Gemini pilot cannot build executable envelope in 5A
CREATE OR REPLACE FUNCTION research.gemini_pilot_5a_gate_status()
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_provider research.providers%ROWTYPE;
  v_model research.provider_model_candidates%ROWTYPE;
  v_cred research.provider_credential_status%ROWTYPE;
  v_pilot research.provider_pilot_proposals%ROWTYPE;
BEGIN
  SELECT * INTO v_provider FROM research.providers WHERE code = 'gemini';
  SELECT * INTO v_model FROM research.provider_model_candidates WHERE provider_id = v_provider.id LIMIT 1;
  SELECT * INTO v_cred FROM research.provider_credential_status WHERE provider_id = v_provider.id;
  SELECT * INTO v_pilot FROM research.provider_pilot_proposals WHERE pilot_code = 'GEMINI-PILOT-5A';

  RETURN jsonb_build_object(
    'pilot_code', 'GEMINI-PILOT-5A',
    'provider_enabled', v_provider.enabled,
    'model_enabled', v_model.enabled,
    'model_id', v_model.model_id_provisional,
    'credential_status', v_cred.status,
    'pilot_status', v_pilot.status,
    'max_cost_usd', v_pilot.max_authorized_cost_usd,
    'live_execution_allowed', false,
    'executable_request_permitted', false,
    'blockers', (
      SELECT COALESCE(jsonb_agg(x), '[]'::jsonb)
      FROM (
        SELECT unnest(ARRAY[
          CASE WHEN NOT v_provider.enabled THEN 'provider_disabled' END,
          CASE WHEN NOT v_model.enabled THEN 'model_disabled' END,
          CASE WHEN v_cred.status IS DISTINCT FROM 'present' THEN 'credential_missing' END,
          CASE WHEN v_pilot.status IS DISTINCT FROM 'approved' THEN 'authorization_not_approved' END
        ]) AS x
      ) s
      WHERE x IS NOT NULL
    )
  );
END;
$$;

CREATE OR REPLACE VIEW research.v_gemini_pilot_5a AS
SELECT
  pp.pilot_code,
  pp.status AS pilot_status,
  p.enabled AS provider_enabled,
  m.model_id_provisional,
  m.enabled AS model_enabled,
  m.verification_status,
  m.free_tier_status,
  c.status AS credential_status,
  pp.benchmark_case_codes,
  pp.max_successful_calls,
  pp.max_total_requests,
  pp.max_total_input_tokens,
  pp.max_total_output_tokens,
  pp.max_authorized_cost_usd,
  pp.retries_allowed,
  pp.fallback_provider_allowed,
  pp.confidentiality_class,
  pv.model_identifier AS verified_model,
  pv.verified_at,
  pv.pakistan_available,
  pv.free_tier_available,
  pv.billing_required_for_free_tier
FROM research.provider_pilot_proposals pp
JOIN research.providers p ON p.id = pp.provider_id
JOIN research.provider_model_candidates m ON m.id = pp.model_candidate_id
JOIN research.provider_credential_status c ON c.provider_id = p.id
JOIN research.provider_policy_verifications pv ON pv.id = pp.policy_verification_id
WHERE pp.pilot_code = 'GEMINI-PILOT-5A';

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA research TO research_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA research TO research_app;
GRANT SELECT ON ALL TABLES IN SCHEMA research TO n8n_app;

INSERT INTO research.schema_version (version, note) VALUES
  (6, 'Round 5A: Gemini bounded pilot preparation (disabled; awaiting Taha credential)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
