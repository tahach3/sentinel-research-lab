# Live Provider Authorization

Authorization is a fail-closed DB record that binds:

- provider
- model candidate
- benchmark case
- maximum requests
- maximum tokens
- maximum cost (USD)
- expiry
- approving authority (`Taha` audit field only)

Expired or mismatched authorization blocks envelope construction.

Completed live calls (future rounds) require both authorization and an append-only
usage ledger entry. Round 4 records **simulated** spend only (`live_executed=false`).

## Proposed Round 5 pilot (not executed)

- one provider only (not chosen permanently here)
- one verified free-tier model
- three benchmark cases
- maximum three successful calls
- maximum one retry per case
- **$0** authorized spend
- no provider fallback
- stop on first unexpected charge or privacy-policy mismatch
