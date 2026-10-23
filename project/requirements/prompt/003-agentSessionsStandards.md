# 003: Align agentSessions with repository standards

## Assignment

Implement and verify [requirement 003](../features/003-agentSessionsStandards.md),
acceptance criteria 1–8, following .github instructions and the shared process guides.

## Boundaries

Change agentSessions, tests/test_agentSessions.py, documentation/agentSessions.md,
README navigation and root project records. Preserve session-store formats and
read-only discovery. Do not alter managed guidance or unrelated commands.
No architecture decision is required for the existing standalone utility.

## Verification and handoff

Run pytest tests/test_agentSessions.py with coverage, Black check, targeted
runLinter and git diff --check. Run repository tests and report existing failures.
Use the real organiseMyProjects dependency. Because runLinter rejects extensionless
files, lint an identical temporary copy with a .py suffix.

Report branch/commits, changed files, acceptance evidence, remaining review,
risks and suite impact (OMS, OMV, OMP, OMPR).
