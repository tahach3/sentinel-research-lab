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
