# Round 5A Report — Gemini Pilot Preparation

## Status

**WAITING_FOR_TAHA_GEMINI_CREDENTIAL**

Policy verified from official Google AI docs. Pilot proposal prepared.
Provider and model remain disabled. No credential. No live calls.

## Starting commit

`2825ef038bf487e47bfa440f296a3ede6a2c600b`

## Verified model identifier

`gemini-2.5-flash`

### Rationale

Official pricing lists Standard Free Tier input/output as **Free of charge**.
Hybrid reasoning + large context fits research synthesis. `gemini-2.0-flash` is
deprecated/shut down per pricing docs. Pilot keeps Google Search grounding
**off** even though free-tier grounding RPD exists for 2.5 Flash.

## Official sources (retrieved 2026-07-28)

| Topic | URL |
| --- | --- |
| Billing / free tier | https://ai.google.dev/gemini-api/docs/billing |
| Pricing | https://ai.google.dev/gemini-api/docs/pricing |
| Models | https://ai.google.dev/gemini-api/docs/models |
| Rate limits | https://ai.google.dev/gemini-api/docs/rate-limits |
| API keys | https://ai.google.dev/gemini-api/docs/api-key |
| Terms (privacy) | https://ai.google.dev/gemini-api/terms |
| Available regions | https://ai.google.dev/gemini-api/docs/available-regions |
| Troubleshooting | https://ai.google.dev/gemini-api/docs/troubleshooting |
| Grounding | https://ai.google.dev/gemini-api/docs/grounding |

## Free-tier and billing

- Free Tier exists for new/active projects (billing docs).
- Billing is **not** required for Free Tier access.
- This pilot authorizes **USD 0.00** only; do not enable billing for 5A/5B pilot.

## Privacy / data-use

Unpaid Services: Google may use prompts and responses to improve products; human
reviewers may read/annotate after disconnecting identifiers. Do not submit
sensitive/confidential/personal data. Pakistan is outside the EEA/UK/CH unpaid
exception, so unpaid terms apply.

## Pakistan availability

**Pakistan is listed** on the official Available regions page for Google AI
Studio / Gemini API.

## Account-dependent (not claimed as fixed)

Exact RPM/TPM/RPD for a new free-tier project: view in AI Studio; capacity not
guaranteed.

## Pilot cases

| Code | Kind | Role |
| --- | --- | --- |
| R-N-01 | normal | researcher |
| R-A-01 | ambiguous | researcher |
| R-X-01 | adversarial | researcher |

## Authorization limits (proposed)

- max successful calls: 3
- max attempts per case: 1
- max total requests: 3
- max total input tokens: 8000
- max total output tokens: 4000
- max cost: USD 0.00
- retries: none
- fallback: none
- expiry: 24 hours after Taha approval
- confidentiality: public_or_synthetic
- authority: Taha

## Explicit non-work

No API key created by the agent. No n8n credential. No enablement. No Round 5B.
