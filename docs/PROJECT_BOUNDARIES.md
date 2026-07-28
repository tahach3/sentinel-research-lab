# Project Boundaries — SENTINEL Research Lab

## Identity

This repository (`C:\Users\Taha\sentinel-research-lab`) is the **SENTINEL Research Lab**.

It is **separate** from PROJECT SENTINEL (`C:\Users\Taha\ai-development-os`).

## Hard prohibitions

| Action | Rule |
| --- | --- |
| Write into `ai-development-os` | **Forbidden** |
| Access or modify Equitify (`C:\Users\Taha\equitify-machine`) | **Forbidden** |
| Trigger Cursor or Codex agent runs from this lab | **Forbidden** |
| Merge, deploy, or modify software project codebases | **Forbidden** |
| Create or approve SENTINEL Tasks | **Forbidden** |
| Auto-import anything into SENTINEL | **Forbidden** |

## Allowed purpose

Research Lab may:

- generate and prioritize research questions (later rounds);
- collect evidence from official and trusted sources (later rounds);
- record model-run metadata and Taha decisions (later rounds);
- produce **proposal export files** under `exports/` for later **manual** handoff.

Research Lab produces **research evidence and proposals only**.

## Import authority

**Taha approves every future SENTINEL import.** No export is authoritative until Taha reviews and imports it manually.

## Spend and APIs

- Round 0B: **no** AI API calls and **no** provider credentials.
- Paid API use in later rounds requires **separate explicit authorization**.
- Quotas and fail-closed spend gates belong in later rounds; until then, treat any paid call as unauthorized.

## Network posture

- Local loopback binding only (`127.0.0.1`).
- No public webhooks, tunnels, or reverse proxies in this foundation.
