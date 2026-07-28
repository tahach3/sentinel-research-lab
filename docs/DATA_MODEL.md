# Data Model — Planned Entities (not implemented in Round 0B)

Round 0B creates only:

- schemas `n8n` and `research`;
- roles `n8n_app` and `research_app`;
- extension `vector`;
- table `research.schema_version`.

The entities below are **planned for later rounds**. Do not treat this file as a live DDL.

## Planned domains

### 1. Research questions

- Question text, priority, status, tags
- Origin (manual vs generated)
- Links to related evidence and proposals

### 2. Sources

- Official / trusted source identity
- URL or citation
- Trust class and retrieval timestamp

### 3. Evidence

- Normalized excerpts or facts
- Source linkage
- Optional embedding reference (pgvector later)

### 4. Model runs

- Provider / model identity
- Prompt fingerprint (no secrets)
- Latency, token estimates, cost estimates
- Stage (research, planning, QA, review, debug)

### 5. Proposals

- Structured proposal body
- Linked questions and evidence
- Export package reference

### 6. Taha decisions

- Approve / reject / defer
- Rationale text
- Timestamp and related proposal id

### 7. Provider budgets

- Soft/hard ceilings
- Usage counters
- Authorization references (fail-closed later)

### 8. SENTINEL export packages

- Files under `exports/`
- Manifest checksum / version
- Import status: `draft` → `ready_for_taha` → `imported_manually` / `rejected`

## Separation from n8n ops data

n8n owns tables in schema `n8n` only. Research entities live in schema `research` (and later filesystem exports). Never merge research tables into n8n’s operational schema.
