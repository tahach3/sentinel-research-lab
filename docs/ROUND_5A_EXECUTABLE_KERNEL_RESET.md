# Round 5A Executable Kernel Reset

Reset name:
Round 5A Executable Kernel Reset

Previous registry reset:
Superseded for findings #2 and #5 only

Preserved result:
Checkpoint finding #4 remains closed

Schema-9 implementation:
Not authorized

Authority namespace:
`round5a_kernel`

Scope:

* `#2` — table, column, sequence, function, and role-path privilege semantics
* `#5` — reconciliation predicates, null semantics, mapping totality, State A, and State B

Out of scope:

* Checkpoint finding `#4` redesign
* Phase F rerun
* Patching failed `specs/round5a/**` reset artifacts
* Schema-9 implementation, SQL, Docker, migrations, live APIs

## KR-ND-001 — Executable privilege authority

Privilege semantics are normative only when represented in:

```text
specs/round5a_kernel/privilege_contract.json
```

and enforced by:

```text
tools/round5a_kernel/privilege_reference.py
```

## KR-ND-002 — Independent reconciliation authority

Reconciliation correctness requires two distinct implementations:

```text
predicate_engine.py
classification_reference.py
```

The classifier may use the predicate engine.

The independent State B recomputation must not import or invoke either one.

## KR-ND-003 — State independence

State A may consume classification outputs.

State B must recompute from raw durable facts without consuming:

* cached State A classifications;
* stored State A digests;
* stored counts;
* classifier output;
* predicate-engine results;
* checkpoint presence alone.

## KR-ND-004 — Null semantics

Every nullable predicate operation must declare one exact mode:

```text
NULL_IS_VALUE
NULL_IS_UNKNOWN
NULL_FAILS_PREDICATE
```

No implicit Python truthiness or SQL three-valued logic is permitted.

## KR-ND-005 — Proof requirement

Counts and fixture totals are not proof.

The executable kernel must enforce:

```text
For every governed source identity S,
exactly one outcome slot O exists.
```

## KR-ND-006 — Closed checkpoint boundary

The existing 18 checkpoint contracts are accepted as closed input.

This phase must not redesign or modify them.

## KR-ND-007 — Column exercisability composition

For column-supported privileges:

```text
SELECT
INSERT
UPDATE
REFERENCES
```

Define:

```text
table_contribution =
    exercisable table-level privilege for the same operation

column_contribution =
    exercisable column-specific privilege for the same operation

column_granted =
    table_contribution OR column_contribution

column_exercisable =
    schema_usage_exercisable AND column_granted
```

Requirements:

* table and column grants remain separately visible;
* table privilege composes into every governed column;
* a column grant may grant access without a table-level grant;
* null or empty `attacl` contributes no column-specific grant;
* null or empty `attacl` must not suppress a valid table-level grant;
* `acldefault('c', ...)` remains prohibited;
* `DELETE`, `TRUNCATE`, and `TRIGGER` remain table-level privileges.

## KR-ND-008 — Exact comparison null semantics

Every comparison node must use one explicit mode:

```text
NULL_IS_VALUE
NULL_IS_UNKNOWN
NULL_FAILS_PREDICATE
```

Semantics:

### Missing field

A missing operand is:

```text
INVALID
```

unless the operator is explicitly:

```text
exists
missing
```

Missing and present-null are never equivalent.

### NULL_IS_UNKNOWN

When either comparison operand is present-null:

```text
UNKNOWN
```

### NULL_FAILS_PREDICATE

When either comparison operand is present-null:

```text
FALSE
```

### NULL_IS_VALUE

For `eq`:

```text
null eq null       → TRUE
null eq non-null   → FALSE
non-null eq null   → FALSE
```

For `ne`:

```text
null ne null       → FALSE
null ne non-null   → TRUE
non-null ne null   → TRUE
```

For ordered comparisons:

```text
lt
lte
gt
gte
```

any null operand produces:

```text
INVALID
```

Incompatible non-null operand types produce:

```text
INVALID
```

### Compound-node propagation

Use exactly:

```text
not:
TRUE → FALSE
FALSE → TRUE
UNKNOWN → UNKNOWN
INVALID → INVALID
```

For `all`:

```text
any INVALID → INVALID
else any FALSE → FALSE
else any UNKNOWN → UNKNOWN
else TRUE
```

For `any`:

```text
any INVALID → INVALID
else any TRUE → TRUE
else any UNKNOWN → UNKNOWN
else FALSE
```

This intentionally prevents an invalid branch from being hidden by another branch.

## KR-ND-009 — Independent differential oracle

The bounded comparison must compare:

```text
contract AST classifier
versus
independently authored decision-table oracle
```

The oracle must not import or execute:

```text
predicate_engine
classification_reference
state_a_reference
state_b_reference
reconciliation_contract
```

The independent oracle is authored from the approved `KR-ND-*` decisions.

It must not be generated from the reconciliation contract.

## KR-ND-010 — Independent State B fixtures

State B verification must consume literal durable facts from an oracle pack.

Durable facts must not be generated from:

* classifier output;
* predicate results;
* State A output;
* expected rule identifiers;
* expected outcome slots.

The validator must compare State B’s independently derived result with a literal expected result only after State B finishes.
