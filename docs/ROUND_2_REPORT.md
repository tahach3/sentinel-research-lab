# Round 2 Report — Research Question and Decision Lifecycle

## Status

**READY_FOR_RESEARCH_LAB_ROUND_3**

Governed question lifecycle, evidence custody, and Taha decision audit are in
schema with synthetic seeds. No AI calls. No API keys. No SENTINEL/Equitify.

## Starting commit

`11470e161adda4e57eb88a421b83263fd3eb4894`

## Delivered

- Migration `003_research_lifecycle.sql` (+ `003a` status-history AFTER-insert fix)
- Seed scenarios RQ-2026-001…007
- Constraint/transition tests `database/tests/003_lifecycle_constraints.sql`
- Six inactive n8n workflow design JSON files
- Docs: lifecycle, evidence custody, decision protocol, priority policy, data model

## Explicit non-goals (confirmed as non-work)

- No API keys / AI provider calls
- No role assignment / live benchmarking
- No scraping / GitHub feeds / AI-generated questions
- No SENTINEL Tasks / Equitify / Round 3 export packages
