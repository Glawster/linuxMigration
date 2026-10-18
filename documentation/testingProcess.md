<!-- deployed from Glawster/organiseMyProjects release 0.9 -- do not edit directly -->
# Testing Process

This is the authoritative testing process for OMP-managed projects. Tests must
show both independent component evidence and real production-path evidence.
Name Python test modules `test_camelCaseName.py`, matching the camelCase
implementation concept, and configure pytest with
`python_files = test_[a-z]*.py`.

> A test suite is not complete merely because every component is tested independently. At least one test must exercise each critical production path using the real components and representative input.

## Testing hierarchy

- **Unit tests** isolate a small function or class. They are fast and precise,
  but do not prove composition with dependencies.
- **Boundary/component tests** exercise a module through its public boundary,
  including important error and serialization behavior. Substituted external
  dependencies mean these tests do not prove those dependencies.
- **Integration tests** compose real collaborators and verify their contracts.
  Critical workflows need at least one real-dependency path where practical.
- **Golden/evidence tests** run reviewed representative input through the real
  pipeline and compare semantic output with independently reviewed truth.
- **UI tests** verify user-visible interaction, presentation, accessibility and
  wiring; they complement domain and integration tests.
- **Resolution/scale robustness tests** demonstrate stable semantics across a
  representative matrix of supported native resolutions or layouts.
- **Clean-room acceptance tests** start with only source evidence and
  configuration, rebuild derived state and verify the accepted semantic result.

## Coverage and completeness

Coverage shows that code was executed. It does not prove that real production
components were composed or that assertions establish intended behavior. A
fake or mock may prove the consumer's behaviour, but it cannot prove the
behaviour of the real dependency or the integration between them.

Prefer branch coverage over line coverage alone where practical. Treat coverage
as a diagnostic and regression indicator, not as the definition of test
completeness. During review ask:

> Which production behaviours could I break while leaving this test green?

If the answer includes the actual dependency, parser, persistence layer or real
input path that the test claims to validate, the test is probably at the wrong
level.

## Production-path testing

Production-path testing exercises the actual operational composition with
representative input and real implementations. Map each significant workflow:

```text
Input
  -> Acquisition
  -> Parsing / extraction
  -> Domain conversion
  -> Persistence
  -> Presentation / output
```

Record which stages are covered independently and which critical paths use the
real composition. Mocks and fakes remain useful for consumer behavior, faults
and rare boundaries, but must not be the only evidence for a critical workflow.

## Golden and evidence testing

Real reviewed source evidence may act as an executable specification. A golden
fixture contains independently reviewed expected truth; never create that truth
by copying current implementation output after a successful run. Pass real
input through the real production pipeline and compare expected and actual
semantic results.

Record strong identities such as role, position, reliable player or entity
identity, and semantic result. Do not rely solely on array or order position
when a stronger identity exists. Failures should report missing and unexpected
entities, expected versus actual identities and positions, and stage-specific
errors. Derived diagnostic artifacts may be created on failure but normally are
not committed as source truth.

## Evidence-processing systems

Screenshot, OCR and similar systems should separate and independently test
useful stages while also testing the real composed pipeline:

```text
Candidate detection
  -> crop/region selection
  -> OCR
  -> normalization
  -> semantic resolution
  -> geometry/position classification
  -> domain validation
  -> persistence
```

> A contradiction between independently derived facts should be reported, not silently repaired.

Missing evidence must also be reported rather than fabricated. Extraction
requirements are incomplete until the relevant real-input and clean-room
acceptance paths pass.

## Resolution and scale robustness

One golden image at one resolution is insufficient evidence of resolution
independence. Maintain a small representative matrix of real, natively captured
supported resolutions and layouts. Artificially resized images are secondary
scaling tests, not substitutes for native captures.

Semantic output must remain constant while coordinates change. Check the same
entity count, identities, positions or families, extracted instructions or
data, and no new unresolved evidence. Prefer normalized or relational geometry
assertions: correct above/below and left/right ordering, relative landmark
distance, and stable defensive/attacking row ordering.

## Clean-room acceptance

Where derived state is persisted, start from a clean state containing only
source evidence and configuration. Rebuild the model or state and verify its
semantic result. Previously generated data must not hide extraction,
transformation or migration defects.

## Requirement-level test plan

Use this table for substantial requirements so missing layers are visible:

| Production behaviour | Unit | Integration | Golden | UI | Resolution | Clean-room |
| --- | --- | --- | --- | --- | --- | --- |
| Example behaviour | ✓ | ✓ | ✓ |  | ✓ | ✓ |

## Runtime guidance

Keep fast unit and component tests suitable for frequent local execution.
Expensive golden, OCR and real-integration suites may be opt-in during routine
development. Use one project-wide pytest marker, such as `expensive`, and run it
explicitly with `pytest -m expensive`; do not invent per-feature flags. When a
requirement changes an affected production path, its relevant expensive suite
must run before acceptance and release. Expensive tests must not become
effectively optional at completion.

## Completion checklist

For requirements affecting extraction, parsing, persistence or UI, confirm:

- [ ] Relevant unit tests exist.
- [ ] Significant module boundaries are tested.
- [ ] Critical production paths use real implementations and representative input.
- [ ] Real external evidence has a golden regression where practical.
- [ ] Mocks or fakes are not the only proof of a critical workflow.
- [ ] Coverage was reviewed and did not regress unexpectedly.
- [ ] Supported resolutions and layouts are represented where relevant.
- [ ] UI behavior is tested where relevant.
- [ ] Clean-room reconstruction passes where derived persistent state exists.
- [ ] Failure diagnostics identify the failing stage and semantic differences.
- [ ] Missing or contradictory evidence is reported, not fabricated or repaired.
