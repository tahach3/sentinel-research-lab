# Self-Improvement V2 — Agent Runtime Contract (Phase 1A)

Phase 1A pins the **non-secret** agent-runtime contract for the Self-Improvement Loop V2. It does **not** wire live AI Agent nodes into the design workflow (that is Phase 1B) and does **not** authorize a pilot.

Normative machine-readable sources:

| Artifact | Path |
| --- | --- |
| JSON Schema | `specs/self_improvement/v2/agent_runtime_contract.schema.json` |
| Python pins + validators | `tools/self_improvement_v2/agent_runtime_contract.py` |
| Inactive design export | `workflows/design/self_improvement_loop_v2.json` (`meta` bindings) |

## Agent identities

| Role | Agent ID | Credential reference (name only) | Provider | Model |
| --- | --- | --- | --- | --- |
| Implementer | `srl-implementer-agent` | `SRL Implementer — Google Gemini` | Google Gemini | `models/gemini-2.5-flash` |
| Independent reviewer | `srl-independent-reviewer-agent` | `SRL Independent Reviewer — Groq` | Groq | `llama3-8b-8192` |

Rules:

- Agent IDs, credential references, providers, and models must remain distinct.
- Implementer produces candidate/proposal payloads only; it must not authorize risk, mutate git, finalize, or share the reviewer credential.
- Independent reviewer produces `review_result` for `review_gate` binding; it must not authorize risk, mutate git, finalize, share the implementer credential, or self-review.

## How n8n will invoke agents (Phase 1B target)

Phase 1A records the intended invocation shape; Phase 1B performs the JSON wiring:

1. **Implementer Agent** — `@n8n/n8n-nodes-langchain.agent` with Chat Model sub-node `@n8n/n8n-nodes-langchain.lmChatGoogleGemini` (`ai_languageModel`), credential name + model pinned above.
2. **Independent Reviewer Agent** — separate `@n8n/n8n-nodes-langchain.agent` with `@n8n/n8n-nodes-langchain.lmChatGroq`, distinct credential name + model.
3. Design export remains `active: false` / `meta.srlInactiveByDesign: true`. Credential **values** never appear in repo JSON.

Until Phase 1B, proposal generation and Independent Review Bind may remain Code stubs. Meta already carries Phase 1A pins (`agentRuntimePhase=1A`, `agentRuntimeWiringStatus=CONTRACT_ONLY`).

## Worker HTTP boundary

n8n routes to the loopback worker bridge only:

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/v2/validate-proposal` | Authorize / classify (pre-mutation) |
| `POST` | `/v2/execute` | LOW-only detached worktree execution |
| `POST` | `/v2/finalize` | Bound review + candidate commit (no push/merge) |
| `GET` | `/health` | Non-secret readiness |

Bindings:

- Base URL meta key: `localWorkerBaseUrl` (default `http://127.0.0.1:8765`)
- Header Auth credential **name**: `srl-v2-worker-header-auth` (token value never in repo)

## Risk authority (sole authorizer)

Executable authorization lives only in `tools.self_improvement_v2.risk_authority` via the worker.

- n8n may route `AUTHORIZED` \| `DECISION_REQUIRED` \| `POLICY_REJECTED`.
- n8n must not compute risk, override worker decisions, manufacture `AUTO_AUTHORIZED`, or trust `proposal.risk_level`.

## Review gate separation

`tools.self_improvement_v2.review_gate` requires:

- `independent_from_implementer == true`
- `reviewer_id != implementer_id`
- Content bindings (proposal/execution/diff/tree/validation/risk) before finalization

Failure before mutation: invalid contract bindings, missing independence, or risk rejection halt before git apply/finalize.

## Secrets policy

Forbidden in repo / design export:

- API keys, worker token values, credential secret data, bearer token literals

Allowed non-secret pins:

- Credential reference names, model IDs, loopback worker base URL, Header Auth credential name

## Pilot limits (handoff caps; not a pilot authorization)

| Field | Value |
| --- | --- |
| `MAXIMUM_PILOT_COST` | 5 USD |
| `MAXIMUM_AGENT_CALLS` | 6 |
| `PILOT_TIMEOUT` | 30 minutes |

## Explicit non-goals (Phase 1A)

- Phase 1B AI/HTTP node wiring in workflow JSON
- Phase 3 preflight
- Workflow activation / Execute Workflow
- Live Gemini/Groq calls in unit tests
- Push, merge, or pilot start

## Validation (offline)

```powershell
python -m pytest tests/self_improvement_v2/test_agent_runtime_contract.py -q
```

`assert_phase_1a_contract_surface()` validates the pinned schema instance and design-workflow meta bindings without network calls.
