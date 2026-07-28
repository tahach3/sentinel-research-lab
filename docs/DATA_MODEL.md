# Data Model

## Implemented

### Round 0B–3

Foundation, benchmarking, lifecycle, simulated orchestration (see prior docs).

### Round 4

- `provider_capabilities`
- `provider_model_candidates`
- `provider_adapter_versions`
- `provider_rate_limit_policies`
- `provider_credential_status` (non-secret)
- `provider_authorization_records`
- `provider_usage_ledger` (append-only; `live_executed=false`)
- `provider_health_checks`
- `live_request_envelopes` (non-executable)

Budget policy columns: `paid_fallback`, `daily_cost_limit_usd` (defaults closed).

Views: `v_enabled_provider_readiness`, `v_missing_credentials`,
`v_remaining_daily_quota`, `v_remaining_monthly_budget`,
`v_unauthorized_call_warnings`, `v_provider_health_summary`,
`v_models_awaiting_verification`.

## Explicit non-storage

No API keys, tokens, or credential secrets in PostgreSQL.
