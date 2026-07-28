# Provider Budget Policy

## Defaults

| Rule | Value |
| --- | --- |
| Free-only by default | **Yes** (`provider_budget_policies.free_only = true`) |
| Paid fallback | **Forbidden** (`paid_fallback = false`) |
| Daily cost limit | **0.00 USD** by default (`daily_cost_limit_usd`) |
| Automatic funding | **Never** |
| Silent paid fallback | **Forbidden** |
| Silent provider switch | **Forbidden** |
| Silent paid retry | **Forbidden** |
| Paid usage | Requires explicit Taha approval (`paid_usage_authorized = true`) |

## Caps (initial placeholders for mock providers)

| Cap | Initial value |
| --- | --- |
| Per-provider daily request cap | 20 |
| Per-provider daily token cap | 50,000 |
| Monthly cost ceiling | **0.00 USD** while free-only |

## Stop behavior when quota is exhausted

1. Coordinator must **not** create a paid/live call.
2. Create or update a run as `failed` with `failure_class = quota_exhausted`.
3. Surface the failure in the Taha scoring/ops queue.
4. Do not substitute another provider.

## Taha approval for paid usage

Before any non-zero spend:

1. Set `paid_usage_authorized = true` for that provider.
2. Set a positive `monthly_cost_ceiling_usd`.
3. Record approval outside the DB if needed (chat/ops note).
4. Keep free-only models preferred when quality is comparable.

## Storage rules

- No API keys in PostgreSQL.
- No credential blobs in run/output rows.
- Cost fields are estimates only until a later metering adapter exists.
