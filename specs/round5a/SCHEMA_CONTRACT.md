# Round 5A Architecture Reset — Schema Contract

Architecture reset name: **Round 5A Architecture Reset**  
Specification schema version: **1.0.0**

Authoritative machine-readable schema:

```text
specs/round5a/schema/round5a_registry.schema.json
```

JSON Schema Draft: **2020-12**

This document defines authority order, artifact responsibilities, restricted predicate AST semantics, schema limitations (Phase D invariants), and versioning rules for the Round 5A Architecture Reset. It does not populate registries, fixtures, oracles, or schema-9 implementation.

---

## Authority order

1. Human-approved ND decisions  
2. Machine-readable registry contracts  
3. Literal fixture and oracle packs  
4. Generated Markdown documentation  
5. Implementation code  
6. Runtime evidence  

Clarifications:

- Runtime evidence overrides reconstructed expectations for **current-state facts**.
- Runtime evidence does **not** automatically rewrite normative ND decisions.
- When generated Markdown differs from a registry, the registry wins.

### Generated-document rule

```text
Generated Markdown is never normative when it differs from a registry.
```

---

## Artifact responsibilities

| Concern | Future normative owner | Authority class |
|---|---|---|
| Privilege expectations (table / column / function / sequence / schema) | `catalog_contract` registry | normative_source |
| Checkpoint definitions (18 structural contracts) | `checkpoint_registry` | normative_source |
| Reconciliation predicates and ordered rules (22) | `reconciliation_rule_registry` | normative_source |
| Reconciliation witnesses / boundary / mutation cases | `reconciliation_fixture_pack` | normative_source |
| Checkpoint expected digests and canonical bytes | `checkpoint_oracle_pack` | normative_source |
| Privilege expansion / exercisable path cases | `privilege_fixture_pack` | normative_source |
| Cross-artifact hashes and commit pins | `registry_manifest` | normative_source |
| Generated architecture tables / appendix matrices | `docs/generated/*` (future) | generated_document |
| Generated test documentation | `docs/generated/*` (future) | generated_document |
| Live catalog / live-preflight / runtime revalidation packs | external / pinned manifests | runtime_evidence |
| Schema-9 SQL, controller, classifier | implementation (out of scope until Phase F CLOSED) | implementation_only |

Surviving critical findings addressed structurally by these schemas:

- **#2** — column ACL semantics, privilege paths, dynamic role discovery, privilege cells with evidence class  
- **#4** — checkpoint structural completeness, typed selectors, serialization/digest contracts, bidirectional validation  
- **#5** — pure restricted predicate AST, typed actions, fallback rule 22 shape, subject domains  

Closed finding **#1** (function ACL inventory) remains closed; function ACL semantics are represented as required catalog-contract structure (`COALESCE(proacl, acldefault('f', proowner))`, PUBLIC EXECUTE, overload identity, schema-USAGE gating).

---

## Restricted AST semantics

Predicate representation: YAML/JSON abstract syntax tree validated by `$defs.predicate_node`.

### Supported nodes

```text
all
any
not
compare
is_null
is_not_null
in
not_in
set_equals
set_contains
exists
missing
```

### Supported comparison operators

```text
eq
ne
lt
lte
gt
gte
```

### Supported operands

```text
field_ref
literal
normalized_identity_ref
computed_primitive_ref
```

Literals require an explicit `data_type`.

### Null behavior

Every comparison / membership / set node that can observe null must declare exactly one of:

```text
null_is_value
null_is_unknown
null_fails_predicate
```

Implicit SQL three-valued logic is prohibited.

### Type requirements

- `field_ref` requires `scope`, `path`, `data_type`, `nullable`.
- Allowed data types: `string`, `integer`, `decimal`, `boolean`, `timestamp`, `date`, `uuid`, `bytes`, `string_set`, `identity_set`, `json_scalar`.
- Natural identities require `identity_fields`, `normalization`, `serialization_order`.
- Identity fields named or classified as `oid`, `object_oid`, `relation_oid`, `function_oid`, `row_number`, `physical_location`, or `ctid` are prohibited. Phase D also rejects case variants and nested uses.

### Prohibited arbitrary code

The following are structurally invalid in registries:

- unrestricted SQL text as a selector or predicate  
- arbitrary Python / shell / template expressions  
- `eval` or equivalent  
- prose-only actions such as “handle conflict”, “archive appropriately”, “repair if needed”  
- production digest self-oracles  

Selectors must reference versioned `PRIMITIVE-*` / `QUERY-*` identifiers with typed parameters.

---

## Schema limitations / Phase D invariants

JSON Schema alone cannot prove every registry-wide semantic rule. Mandatory Phase D offline validator checks are recorded under `x-round5a-invariants` in the schema and include:

- unique checkpoint IDs by selected field / exactly 18 unique IDs  
- contiguous rule order `1..22`  
- fallback-last behavior (order 22, sole `is_fallback: true`, `failure_state: failed_frozen`)  
- predicate reachability and no unreachable rules  
- shadowing analysis for all 231 earlier/later pairs  
- mapping totality (bounded fixture source → exactly one outcome slot)  
- cross-file reference validity  
- OID prohibition including case variants and nested uses  
- every decisive field appears in its rule predicate  
- digest input field names ⊆ selected fields with `digest_included: true`  
- no fixed role list as the sole role-discovery mechanism (`role_discovery.mode = CATALOG_DISCOVERY`)  

These checks are mandatory before any claim that findings #2/#4/#5 are CLOSED.

---

## Versioning

```text
Architecture reset name:
Round 5A Architecture Reset

Specification schema version:
1.0.0
```

- Schema changes use semantic versioning.
- Breaking schema changes require a major version increment.
- Registry content versions are tracked separately via `registry_manifest.registry_version`.
- `generated_at` on manifests is metadata only and must be excluded from normative digests.

---

## Root artifact types

The composite schema accepts exactly one of:

```text
catalog_contract
checkpoint_registry
reconciliation_rule_registry
reconciliation_fixture_pack
checkpoint_oracle_pack
privilege_fixture_pack
registry_manifest
```

Root and normative nested objects use `unevaluatedProperties: false` so unknown fields are rejected.

---

## Out of scope for Phase A

- Populating 18 checkpoints or 22 reconciliation rules  
- Fixture / oracle content  
- Offline validator implementation  
- Generated architecture or test Markdown  
- Schema-9 migration or runtime code  
- Database connections, reconstruction restarts, migrations, paid/live calls  
