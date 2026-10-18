<!-- deployed from Glawster/organiseMyProjects release 0.9 -- do not edit directly -->
# Agent implementation workflow

## Purpose

The organise suite may use Codex, Grok, GitHub Copilot, and other coding assistants to implement and review requirements. Requirements, ADRs, and established project conventions remain authoritative; an agent is an implementation/review tool, not an independent source of architecture or policy.

This workflow applies to organiseMediaStudio (OMS), organiseMyVideo (OMV), organiseMyPhotos (OMP), and organiseMyProjects (OMPR).

## Default workflow

```text
Requirement / ADR
      |
      v
Codex implementation
      |
      v
Grok independent review
      |
      v
Codex fixes
      |
      v
Human/integration verification
      |
      v
Merge
```

Do not normally ask multiple agents to create competing implementations of the same requirement. Independent agents are most useful when implementation and review are separated.

## Roles

### Codex - primary implementation

Codex should normally:

- work from one named requirement at a time;
- use the requirement's feature branch or an explicitly agreed implementation branch;
- implement domain/application services before UI wiring where the architecture requires that separation;
- add or update automated tests with the implementation;
- preserve non-destructive boundaries and filesystem-safety rules;
- run the project's normal verification commands;
- make small, traceable commits;
- report anything that appears to require a requirement or architecture change rather than silently changing the design.

### Grok - independent review

Grok should normally review the completed implementation against the authoritative requirement and ADRs. Review should look specifically for:

- acceptance criteria that are not satisfied;
- hard-coded assumptions that should be discovered or configured;
- domain/application logic leaking into CLI or Qt/UI layers;
- destructive behaviour crossing a scan/discovery/planning boundary;
- filesystem-safety violations;
- weak identity/duplicate assumptions;
- missing edge cases and tests;
- project-specific code that belongs in a shared OMS primitive;
- changes that have an unaddressed OMPR tooling/convention impact.

Review findings should identify evidence and proposed tests/fixes. Grok should not redesign an accepted requirement merely because another implementation would be preferable.

### GitHub Copilot - local coding assistance

Copilot is appropriate for focused local work such as repetitive tests, refactoring, type hints, Qt wiring, documentation updates, and resolving individual failures. Copilot-generated work is subject to the same requirements, tests, linting, and review as other code.

### Human/integration acceptance

Before merge, verify the implementation against the requirement and review findings. For media/filesystem features, use synthetic/temporary fixtures before exercising real libraries, and use non-destructive/dry-run modes before confirmed changes.

## Required agent report

Every substantial implementation or review run should report:

1. requirement/ADR addressed;
2. branch and commits produced or reviewed;
3. files materially changed;
4. tests added or changed;
5. verification commands and results;
6. acceptance criteria not yet satisfied;
7. unresolved risks or ambiguities;
8. proposed requirement/ADR changes, if any;
9. suite impact considered: OMS, OMV, OMP, OMPR.

Where the repository's requirement template contains agent-run traceability, record the run or review there when practical.

## Verification baseline

Use the verification commands defined by the repository and requirement. Where applicable this includes:

```text
pytest
runLinter
black --check (or the project's Black workflow)
git diff --check
```

A passing agent-generated patch is not accepted solely because one tool reports success. Requirement acceptance criteria and architectural boundaries remain the final test.

## Architecture changes

If implementation exposes a missing or incorrect architectural decision:

1. stop treating the issue as an implementation detail;
2. describe the conflict and evidence;
3. update/approve the requirement or ADR;
4. resume implementation against the revised authoritative documentation.

Agents must not silently weaken safety, discovery, policy, branding, shared-service, or UI/domain separation requirements to make implementation easier.

## Suite impact rule

Changes to organise-suite architecture, conventions, shared media primitives, UI branding, package/project layout, requirements structure, linting, or managed infrastructure must include an impact check for:

- OMS - shared media and suite architecture;
- OMV - video-domain consumer;
- OMP - photo-domain consumer;
- OMPR - project discovery, scaffolding, checking, linting, and managed conventions.

Not every change requires code in all four repositories, but the impact assessment must be explicit.
