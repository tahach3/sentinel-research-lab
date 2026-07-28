# Provider Credential Setup

## Absolute rules

Taha enters API keys **only** in the local n8n Credentials UI.

Never paste keys into:

- Cursor
- chat
- `.env`
- workflow JSON
- PostgreSQL
- Git
- documentation

PostgreSQL stores **credential status only** (`missing` / `present` / `unknown`)
and an optional non-secret n8n credential label.

## Future manual steps (not executed in Round 4)

1. Taha selects one provider.
2. Taha creates or obtains the API key directly from that provider.
3. Taha enters the key manually into local n8n credentials.
4. n8n encrypts the secret; it is never exported to Git.
5. A non-secret `provider_credential_status` row is set to `present`.
6. Continue with authorization + preflight (see other docs).
