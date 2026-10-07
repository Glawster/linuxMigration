# User configuration and VS Code extensions

## Managed files

Files that should be identical across machines live under `configs/`. Declare a
source and home-relative destination in a role or host profile, separated by a
pipe:

```yaml
managedFiles:
  - shell/aliases|.bash_aliases
  - vscode/settings.json|.config/Code/User/settings.json
```

The bootstrap compares content before proposing a change. In apply mode it
creates the destination directory when needed and installs the file with mode
`0644`. Both paths must be relative and cannot contain `..`; this keeps sources
inside `configs/` and destinations inside the invoking user's home directory.

The shared aliases file is declared by `profiles/common.yaml`, so edits to
`configs/shell/aliases` are applied to every host inheriting `common`. Commit
only portable configuration. Do not add tokens, passwords, private keys,
machine identifiers, or application state to managed files.

Application settings files are replaced as a whole. First copy a reviewed,
secret-free file into `configs/`, declare it in the desired profile, preview the
change, and then apply it:

```bash
./bootstrap.sh --profile tv-pc --status
./bootstrap.sh --profile tv-pc --confirm
```

## VS Code extensions

Extensions are declared separately so their installation remains idempotent:

```yaml
vscodeExtensions:
  - openai.chatgpt
  - vscodevim.vim
```

The `code` command must already be available. Status mode lists installed and
pending extensions; apply mode installs only missing extension identifiers.
The `andy-pc` and `tv-pc` host profiles currently share the extensions detected
on `tv-pc` when this feature was introduced.
