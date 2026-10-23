# Agent sessions

agentSessions lists resumable local AI agent sessions without editing their stores.
By default it shows the most recently active session per agent for the current
working directory,
grouped alphabetically by agent, with newest sessions first within each agent. It does not launch or resume an agent.

## Runtime

Use Python 3.10 or newer with organiseMyProjects installed in the interpreter's
environment. The repository's Conda environment is the preferred development
starting point (`conda env create -f environment.yml`); install the local
organiseMyProjects checkout editable into that environment with
`python -m pip install -e /path/to/organiseMyProjects`. Dependencies are never
installed by the command itself.

## Usage

```bash
agentSessions
agentSessions --all --full
agentSessions --history
agentSessions --id 2
agentSessions --verbose
agentSessions --quiet
agentSessions --help
agentSessions --version
```

--all includes sessions from all working directories. --history includes older
sessions within the selected directory scope. Combine --all --history to see everything. --full displays complete IDs. --verbose enables
parser diagnostics; --quiet suppresses lifecycle messages. Shared run/section
separators and the listing remain visible. This read-only utility has no
--confirm option.

## Grabbing a resume ID

Each table row has a number in the `#` column. Print that row's complete resume ID:

```bash
agentSessions --id 2
resumeId=$(agentSessions --id 2)
```

`--id` writes only the full ID to stdout, making it suitable for copying or shell
substitution. Invalid row numbers return exit status 2 with an error on stderr.
Use the same listing options: after `agentSessions --all`, use
`agentSessions --all --id 2`; include --history too when selecting from history. Row numbers refer to the current scan and can change
when sessions are added or updated; retain the extracted full ID for later use.
Use `--full` to display complete IDs directly in the table.

Current-directory matching uses the exact resolved directory, including symlink
aliases. It excludes child directories and sessions with unknown working directories.
Use --all to include those sessions and other projects.

## Discovery and output

| Agent | Local source |
| --- | --- |
| Codex | ~/.codex/sessions/**/rollout-*.jsonl session_meta records |
| Claude | ~/.claude/projects/*/UUID.jsonl working-directory metadata |
| Grok | ~/.grok/sessions/encoded-directory/UUID, excluding nested subagents |
| Copilot | $COPILOT_HOME/session-state, defaulting to ~/.copilot/session-state |

Copilot requires events.jsonl and reads the simple cwd scalar from workspace.yaml,
falling back to session.start metadata. The workspace reader supports bare and
single/double-quoted scalar paths, rather than general YAML syntax.
Activity dates use local filesystem modification times. Grok prefers summary.json,
then chat_history.jsonl, updates.jsonl and finally the session directory timestamp.
Working directories need not still exist; missing metadata is shown as `?`.
Long paths and IDs are shortened for terminal display.

Missing stores are normal. Malformed JSON lines are skipped with debug diagnostics;
I/O failures are logged with context and other agent stores are still scanned.
A successful listing may therefore be partial; inspect warnings when completeness
matters. Application logs are written under ~/.local/state/agentSessions/.

## Verification

```bash
python -m pytest tests/test_agentSessions.py --cov=agentSessions --cov-report=term-missing
python -m black --check agentSessions tests/test_agentSessions.py
```

Tests use temporary homes and synthetic session metadata with the real shared
logger. They cover all four parsers, fallback metadata, latest-session selection,
rendering, malformed input, I/O failures, source preservation and CLI execution.
The OMP linter accepts Python suffixes only: copy agentSessions unchanged to a
temporary .py file and lint that file plus tests/test_agentSessions.py.
