# Gemini Pilot Setup (Round 5A)

**Status:** waiting for Taha credential. Gemini provider and model remain **DISABLED**.
No live model requests in this round.

## Verified model

- **Model identifier:** `gemini-2.5-flash`
- **Verification date:** 2026-07-28
- **Official sources:** see `docs/ROUND_5A_REPORT.md`

## What you must do (manual)

### 1) Create a Gemini API key in Google’s official UI

1. Open [Google AI Studio API keys](https://aistudio.google.com/app/apikey) (official).
2. Sign in with the Google account you will use for this lab.
3. Create / generate an API key in a project that remains on the **Free Tier**
   (do **not** set up billing for this pilot).
4. Prefer a key restricted to the Gemini API / Generative Language API.
5. Copy the key **only** into the n8n credential form in the next step.
6. Do **not** paste the key into Cursor, chat, PowerShell, `.env`, PostgreSQL,
   Git, workflow JSON, or documentation.

Official reference: https://ai.google.dev/gemini-api/docs/api-key

### 2) Open local n8n

Open: http://127.0.0.1:5678

### 3) Create the Gemini credential in n8n only

1. In n8n, open **Credentials**.
2. Create the appropriate Google Gemini / Generative AI credential type
   available in your n8n build.
3. **Name it exactly:**
   `sentinel-research-lab-gemini-pilot`
4. Paste the API key into the credential secret field inside n8n.
5. **Save**.
6. Do not export the credential to Git or share the secret.

### 4) Reply in chat with only this line

```text
GEMINI CREDENTIAL CREATED
```

Do not include the key or any secret material.

## What happens after that (Round 5B — not started)

Only after your confirmation will a later round:

1. Record non-secret credential status `present` (label only).
2. Ask you to explicitly enable provider + model + approve the 24h pilot.
3. Run at most three successful free-tier calls for cases `R-N-01`, `R-A-01`, `R-X-01`.

## Absolute prohibitions (Round 5A)

- No live model request
- No enabling Gemini or the model yet
- No paid usage / billing setup for this pilot
- No retries / no fallback provider
- Confidentiality: public or synthetic only
