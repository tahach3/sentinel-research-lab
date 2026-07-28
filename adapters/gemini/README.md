# Gemini adapter (Round 4 — disabled)

Converts canonical adapter requests into a **non-executable** Gemini-shaped
envelope and normalizes **fixture** responses only.

- Live HTTP: **impossible** (`live_execution_allowed=false`)
- Credentials: never read; status checked in PostgreSQL only
- Entry points: `research.build_provider_request_envelope`, `research.parse_provider_fixture_response('gemini', …)`
