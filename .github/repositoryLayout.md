<!-- synced from Glawster/organiseMyProjects -- do not edit directly -->
# Repository layout

This managed guide explains what belongs in each top-level directory and where
to put new material. It is synchronized unchanged across repositories;
repository-specific additions or exceptions belong in
`.github/additional-instructions.md`.

The central convention is to keep project-management records separate from the
durable documentation and content that a project produces.

## Choosing between `project/` and `documentation/`

Use `project/` for records about planning, governing and delivering the work.
Use `documentation/` for maintained explanations of the product, its domain
and the principles contributors need to understand it. These two directories
form the reusable core of this layout.

A useful test is:

- if the document answers **what have we decided, committed to, reviewed or
  scheduled?**, put it in `project/`;
- if it answers **what is this product, how does it work, or what does a
  contributor need to understand?**, put it in `documentation/`.

For example, a proposed outcome belongs in `project/requirements/`. A durable
explanation of the resulting behaviour belongs in `documentation/`. A choice
between competing approaches and its consequences belongs in `project/adr/`.
Do not duplicate the same explanation in both places: link to the authoritative
document instead.

## Top-level directories

| Path | Purpose | Examples |
| --- | --- | --- |
| `app/` | Optional user-facing application code and application-specific resources. | Screens, application entry points and UI orchestration. |
| `brand/` | Optional approved visual identity assets and guidance. | Logos, icons, imagery, colours and the style guide. |
| `data/` | Optional structured, non-secret data used by the project. | Schemas, safe fixtures and fictional examples. |
| `documentation/` | Living product, domain and contributor documentation. | Product vision, principles, personas, glossary, domain model, privacy model and this guide. |
| `src/` or the project package | Reusable core and domain code, independent of a particular UI. | Domain models, validation and transformations. |
| `ui/` or `qt/` | Optional user-interface code and resources. | Views, frames, widgets and UI orchestration. |
| `project/` | Planning, governance and historical delivery records. | Requirements, ADRs, roadmap and point-in-time reviews. |
| `scripts/` | Maintainer tools and repeatable development tasks. | Asset-generation and repository-maintenance scripts. |
| `tests/` | Automated tests, arranged to mirror the code they verify. | Tests for source modules and application behaviour. |

## Entry-point conventions

The required files depend on the project's role:

- a reusable library module or package is imported by other code and does not
  require `main.py` or another executable entry point;
- a packaged command-line tool declares a console-script entry point that
  normally calls a `main()` function inside its package;
- a standalone application keeps `main.py` at its project root.

Do not add a placeholder `main.py` to a library merely to match an application
layout. Add an executable entry point only when the module has an executable
workflow to expose.

## Repositories containing multiple projects

A repository may contain several independently runnable or releasable projects.
Treat the repository root and each contained project as separate ownership
boundaries. Each project should have its own applicable folders rather than
placing all project content in the repository-level folders.

```text
repository/
├── .github/                    # Shared repository and agent definitions
├── documentation/             # Cross-project documentation
├── project/                   # Repository-wide planning and decisions
├── scripts/                   # Cross-project maintenance tools
├── tests/                     # Cross-project and repository integration tests
└── projects/
    ├── projectOne/
    │   ├── src/
    │   ├── documentation/
    │   ├── project/
    │   ├── scripts/
    │   └── tests/
    └── projectTwo/
        ├── src/
        ├── documentation/
        ├── project/
        ├── scripts/
        └── tests/
```

Use the nearest owning boundary:

- repository-level `tests/` contains cross-project integration tests and tests
  for repository-level tooling;
- `<project>/tests/` contains tests for that project's code and behaviour;
- repository-level `documentation/`, `project/`, and `scripts/` contain shared
  or cross-project material;
- the corresponding folders beneath a project contain material owned solely by
  that project;
- dependencies, configuration, entry points, build output and generated output
  should likewise live at the narrowest boundary that owns them;
- `.github/` remains repository-wide because GitHub reads it from the repository
  root. Use a nested `AGENTS.md` when a project needs additional agent guidance.

Do not make a repository-level test suite import project-internal test helpers
unless they are deliberately exposed as shared test utilities. Cross-project
tests should exercise projects through their supported interfaces.

Generated output, local caches, virtual environments, secrets and real user
data do not belong in version control. A routine that creates output
files should write them beneath a root-level `output/` directory, which should
normally be ignored unless an export is deliberately approved for publication.

## Inside `project/`

| Path | Purpose |
| --- | --- |
| `project/project.yaml` | Current project purpose, scope, audience, risks and milestones. |
| `project/requirements/features/` | Requirement records at every lifecycle stage, kept at stable paths. |
| `project/requirements/templates/` | Templates used to create consistent project records. |
| `project/adr/` | Significant project-shaping decisions and their consequences. |
| `project/reviews/` | Point-in-time assessments that should not be mistaken for living guidance. |
| `project/roadmap.md` | Current sequencing and priorities. |

When a repository uses requirements or ADR workflows, their detailed naming
rules should live in `project/requirements/README.md` and
`project/adr/README.md` respectively.

## Requirement conventions

Keep every requirement permanently under `project/requirements/features/`.
Do not move completed or retired records: treat the allocated path as a stable
interface for documentation, prompts, commits and external references. Record
lifecycle changes in the requirement's status and requirements index instead.

The requirements index uses these workflow sections:

- `ToDo`
- `In Progress`
- `Completed`

Requirement filenames use a permanent project identifier:

```text
<PREFIX>-ddd-name.md
```

- `<PREFIX>` is the owning project's stable uppercase identifier.
- `ddd` is a zero-padded sequential number that is never changed or reused.
- `name` is a concise camelCase description.

Each project's `project/requirements/README.md` records its prefix, next
available number, status index and any project-specific requirement details.
The identifier must also appear inside the requirement record.

Living documentation owned by one requirement belongs in a directory named
after the requirement without its prefix, number or `.md` extension:

```text
project/requirements/features/FMP-003-viewManagement.md
documentation/viewManagement/
```

General documentation spanning multiple requirements remains directly under
the owning project's `documentation/` directory.

## Documentation conventions

- Keep only `README.md` as the main documentation entry point at the repository
  root; place other maintained guides under `documentation/` or the directory
  whose contents they introduce.
- Use camelCase Markdown filenames, except for `README.md` and records with a
  stable identifier such as an ADR or requirement.
- Put a directory-specific `README.md` in a directory when readers need an
  index or instructions for working with its contents.
- Keep Mermaid source (`.mmd`) beside the document or subject it explains.
- Link from the root README to living guides so contributors can discover them.
- Prefer relative links so documentation works both locally and on GitHub.

## Applying this shared layout

This is a managed baseline stored at `.github/repositoryLayout.md` in every
repository. Do not edit a downstream copy directly because a later sync will
replace it.

When applying the layout in another repository:

1. keep the `project/` versus `documentation/` distinction unless the project
   has a documented reason to use a different model;
2. interpret `src/` as the repository's actual source-package directory;
3. use optional directories such as `app/`, `brand/`, `data/`, `ui/` or `qt/`
   only when they represent a genuine top-level concern;
4. record project-specific additions or exceptions in
   `.github/additional-instructions.md`, linking back to this managed baseline;
5. link this guide from the project's root `README.md`.

Avoid copying empty directories merely to resemble this repository. Each
top-level directory should represent a real, distinct responsibility.

## Placement examples

| New item | Location | Reason |
| --- | --- | --- |
| A requirement at any lifecycle stage | `project/requirements/features/` | Its stable path remains valid as status changes. |
| The decision to use a particular implementation approach | `project/adr/` | It records a consequential choice and rationale. |
| An explanation of implemented behaviour | `documentation/` | It is maintained product or technical knowledge. |
| A review of project risks on a particular date | `project/reviews/` | It is a point-in-time assessment. |
| The current security model | `documentation/securityModel.md` | It is living guidance. |
| A fictional fixture used by tests | `data/` | It is structured, safe project data. |
| A command used to regenerate icons | `scripts/` | It is a repeatable maintainer task. |
| A test for one contained project | `<project>/tests/` | It is owned by that project's code and lifecycle. |
| A workflow spanning two contained projects | `tests/` | It verifies repository-level integration. |

When a document changes category, move it rather than copying it, update links
in the same change and preserve its version-control history.
