<!-- deployed from Glawster/organiseMyProjects release 0.9 -- do not edit directly -->
# Repository layout

This managed guide defines the standard OMP repository structure and where new
material belongs. Repository-specific additions or exceptions belong in
`.github/additional-instructions.md`.

The central convention is to keep project-management records separate from the
durable documentation and content a project produces.

Status has one owner. Requirements describe obligations, design documentation
describes behaviour, and Git records delivery history.
`project/currentIncrement.md` alone records transient implementation status.

## README and directory-index convention

OMP uses one repository README rule:

- `README.md` is reserved for the repository root.
- Do not create OMP-owned `README.md` files in subdirectories.
- When a directory genuinely needs an index, navigation page, catalogue or
  directory-specific instructions, derive the filename from the directory as
  `<folderName>Index.md`.
- Do not create an index merely because a directory exists.
- Named artifacts such as requirements, prompts, ADRs, specifications and
  guides keep descriptive filenames rather than being stored as a directory
  `README.md` or generic index file.
- OMP cleanup must preserve arbitrary user-owned or third-party nested README
  files unless a deterministic OMP migration proves ownership and destination.

The standard OMP project-management indexes are:

```text
project/requirements/requirementsIndex.md
project/adr/adrIndex.md
```

## Choosing between `project/` and `documentation/`

Use `project/` for records about planning, governing and delivering the work.
Use `documentation/` for maintained explanations of the product, its domain and
the principles contributors need to understand it.

A useful test is:

- if the document answers **what have we decided, committed to, reviewed or
  scheduled?**, put it in `project/`;
- if it answers **what is this product, how does it work, or what does a
  contributor need to understand?**, put it in `documentation/`.

A proposed outcome belongs in `project/requirements/`. A durable explanation of
the resulting behaviour belongs in `documentation/`. A consequential technical
choice belongs in `project/adr/`. Do not duplicate the same explanation in both
places; link to the authoritative document.

## Standard Python project layout

New OMP Python projects use a root-level Python package named after the project.
OMP does not use a generic `src/` directory for newly scaffolded projects.

For a project named `footballVision`:

```text
footballVision/
├── .github/
├── .vscode/
├── documentation/
├── project/
│   ├── adr/
│   │   ├── adrIndex.md
│   │   └── templates/
│   ├── requirements/
│   │   ├── requirementsIndex.md
│   │   ├── features/
│   │   ├── prompt/
│   │   └── templates/
│   ├── reviews/
│   ├── currentIncrement.md
│   ├── project.yaml
│   └── roadmap.md
├── footballVision/
│   ├── __init__.py
│   └── ...
├── tests/
├── pyproject.toml
├── footballVisionEnvironment.yml
├── README.md
└── .gitignore
```

The package directory is the primary home for project Python code. Individual
`.py` files inside it are modules; the importable directory containing
`__init__.py` is the Python package.

## Top-level directories

| Path | Purpose | Examples |
| --- | --- | --- |
| `<projectName>/` | Required Python package for newly scaffolded Python projects. | Domain models, application services, CLI modules and reusable project code. |
| `app/` | Optional non-package application resources where a genuine separate concern exists. | Static resources or deployment wrappers. |
| `brand/` | Optional approved visual identity assets and guidance. | Logos, icons, imagery, colours and style guidance. |
| `data/` | Optional structured, non-secret data. | Schemas, safe fixtures and fictional examples. |
| `documentation/` | Living product, domain and contributor documentation. | Architecture, product vision, glossary and technical guides. |
| `project/` | Planning, governance and historical delivery records. | Requirements, ADRs, roadmap and point-in-time reviews. |
| `scripts/` | Maintainer tools and repeatable development tasks. | Repository-maintenance and asset-generation scripts. |
| `tests/` | Automated tests arranged around package behaviour. | Unit, integration and application tests. |

Do not introduce a top-level `src/` directory in a newly scaffolded OMP
project. Existing projects that already use `src/` are not automatically
reorganised by ordinary updates.

## Entry-point conventions

Every new OMP Python project is importable as a package. Executable behaviour
depends on project role:

- reusable library packages require no executable entry point;
- command-line tools declare console-script entry points in `pyproject.toml`;
- GUI or standalone applications expose their application entry point from the
  project package; and
- `package/__main__.py` may be used when `python -m package` is an intended
  interface.

A root-level `main.py` is not part of the standard OMP 0.6 scaffold.

## Packaging and environment conventions

- `pyproject.toml` is the authoritative package metadata, dependency and entry
  point definition.
- Use `<projectName>Environment.yml` as the project-specific camelCase Conda
  environment filename.
- Document Conda before alternative virtual-environment workflows.
- Install the project editable during development.
- Do not make `requirements.txt` the primary dependency mechanism for newly
  scaffolded packaged projects.
- Do not auto-install dependencies at runtime.
- Validate required external tools explicitly and fail fast when missing.

## Repositories containing multiple projects

A repository may contain several independently runnable or releasable projects.
Treat the repository root and each contained project as separate ownership
boundaries.

```text
repository/
├── README.md
├── .github/
├── documentation/
├── project/
├── scripts/
├── tests/
└── projects/
    ├── projectOne/
    │   ├── projectOne/
    │   ├── documentation/
    │   ├── project/
    │   ├── scripts/
    │   └── tests/
    └── projectTwo/
        ├── projectTwo/
        ├── documentation/
        ├── project/
        ├── scripts/
        └── tests/
```

Use the nearest owning boundary. Repository-level tests cover cross-project
integration and repository tooling; project-level tests cover that project's
code. `.github/` remains repository-wide because GitHub reads it from the
repository root.

Generated output, local caches, virtual environments, secrets and real user
data do not belong in version control. Generated output should normally live
beneath root-level `output/` and be ignored unless deliberately published.

## Inside `project/`

| Path | Purpose |
| --- | --- |
| `project/project.yaml` | Current project purpose, scope, audience, risks and milestones. |
| `project/currentIncrement.md` | Authoritative transient status for the active increment. |
| `project/requirements/requirementsIndex.md` | Requirement index and next-ID authority. |
| `project/requirements/features/` | Flat numbered requirement specifications at stable paths. |
| `project/requirements/prompt/` | Flat requirement prompts plus optional shared prompt support. |
| `project/requirements/templates/` | Requirement templates. |
| `project/adr/adrIndex.md` | ADR index and directory-level ADR guidance. |
| `project/adr/` | Numbered architecture decision records. |
| `project/reviews/` | Point-in-time assessments. |
| `project/roadmap.md` | Current sequencing and priorities. |

Detailed requirement naming and prompt rules live in
[`requirementsManagement.md`](requirementsManagement.md).

## Requirement and prompt placement

Requirements and prompts are named flat files, not per-artifact folders:

```text
project/requirements/features/003-viewManagement.md
project/requirements/prompt/003-viewManagement.md
```

When several prompts belong to one requirement:

```text
project/requirements/prompt/003a-viewManagement.md
project/requirements/prompt/003b-viewManagement.md
```

Do not create `features/003-viewManagement/README.md` or
`prompt/003-viewManagement/README.md` as a substitute for the named artifact.

## Documentation conventions

- Keep the sole OMP-standard `README.md` at repository root.
- Use `<folderName>Index.md` for a directory index only when that directory
  genuinely needs navigation, catalogue or local instructions.
- Use camelCase Markdown filenames except the root `README.md` and stable-ID
  records such as requirements and ADRs.
- Keep Mermaid source beside the subject it explains.
- Prefer relative links.
- Do not copy transient increment progress into requirements, ADRs or durable
  documentation.
- Requirement lifecycle state may remain in requirement records and the
  requirements index; it is distinct from transient implementation status.
- Use tests as executable evidence and Git as delivery history.

## Applying this shared layout

This managed baseline is stored at `documentation/repositoryLayout.md` in every
repository. Downstream projects should not edit the managed copy directly.

When applying it:

1. keep the `project/` versus `documentation/` distinction unless a documented
   exception is necessary;
2. use the root-level project package for new Python projects;
3. reserve `README.md` for repository root;
4. derive directory-index filenames as `<folderName>Index.md` only where an
   index is genuinely needed;
5. keep named artifacts in their canonical files;
6. use optional top-level directories only for real separate concerns; and
7. record project-specific exceptions in `.github/additional-instructions.md`.

## Placement examples

| New item | Location | Reason |
| --- | --- | --- |
| Project Python module | `<projectName>/<moduleName>.py` | Part of the importable project package. |
| Active development state | `project/currentIncrement.md` | Records current operational handoff. |
| Requirement specification | `project/requirements/features/nnn-requirementName.md` | Stable numbered requirement artifact. |
| Requirement prompt | `project/requirements/prompt/nnn-requirementName.md` | Matching durable prompt artifact. |
| Requirements index | `project/requirements/requirementsIndex.md` | Index/navigation for the requirements directory. |
| ADR index | `project/adr/adrIndex.md` | Index/navigation for the ADR directory. |
| Architecture decision | `project/adr/nnn-decisionName.md` | Consequential project decision. |
| Implemented-behaviour guide | `documentation/<guideName>.md` | Living product or technical knowledge. |
| Point-in-time review | `project/reviews/<reviewName>.md` | Historical assessment. |
| Test fixture | `data/` | Structured safe test/project data. |
| Maintainer command | `scripts/` | Repeatable repository maintenance. |

When a document changes category, move it rather than copying it and update
links in the same change.

## OMP 0.6 index migration

`manageProject --update` recognises historical or mistaken OMP index names and
migrates them to the folder-derived canonical names:

```text
project/requirements/README.md
project/requirements/folderIndex.md
    -> project/requirements/requirementsIndex.md

project/adr/README.md
project/adr/folderIndex.md
    -> project/adr/adrIndex.md
```

Only deterministic, no-loss migrations are applied. Collisions, ambiguous
content and arbitrary user-owned nested README files are preserved for manual
review. Dry-run reports intended operations without modifying files.

## Shared runtime infrastructure

The canonical runtime package is `organiseMyProjects`. Logging and related
helpers are imported from that package:

```python
from organiseMyProjects.logUtils import getLogger, setApplication
```

Do not add a second runtime package named `omp` inside the
`organiseMyProjects` repository. Project-specific application code belongs in
the project's own package.
