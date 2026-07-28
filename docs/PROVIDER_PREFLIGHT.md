# Provider Preflight

Preflight order (must pass in sequence). Failure before step 11 produces **no**
request envelope.

1. provider enabled
2. model enabled and verified
3. role permitted
4. credential status confirmed **without reading the secret** (stored status only)
5. authorization record valid
6. free-only or approved paid policy valid
7. daily request allowance available
8. daily token allowance available
9. monthly/daily cost allowance available
10. confidentiality policy permits the request
11. only then construct the non-executable request envelope

Round 4: `live_execution_allowed` is always `false`. HTTP execution is impossible.

## Failure classes

`provider_disabled`, `model_disabled`, `model_unverified`, `credential_missing`,
`authorization_missing`, `authorization_expired`, `authorization_mismatch`,
`free_tier_unverified`, `request_quota_exhausted`, `token_quota_exhausted`,
`cost_budget_exhausted`, `confidentiality_blocked`, `unsupported_capability`,
`malformed_provider_response`.
