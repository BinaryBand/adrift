# Contributing

Bounded constraints for contributors. The goal is a solution space tight enough that any output passing these rules is consistent, reviewable, and mergeable without negotiation.

See `PLAYBOOK.md` for tool responsibilities and structural decisions.

* * *

## Setup

WSL with base Debian compatibility is the development target.

```bash
poetry install
# Optional: create/activate a virtual environment with `poetry shell` or a `.venv`.
# This repository does not include a `.pre-commit-config.yaml` by default.
# Run quality checks manually (examples):
#   .venv/bin/ruff check adrift tests typings
#   .venv/bin/ruff format --check adrift tests typings
#   .venv/bin/ty check --project .
#   .venv/bin/python -m vulture adrift tests typings --min-confidence 80
#   .venv/bin/python -m lizard adrift -C 8 -L 30 -a 4
```

Open in VS Code from inside WSL:

```bash
code .
```

### Universal Config Files

All tooling behaviour is driven by committed config files — editor-agnostic, picked up automatically by any LSP-capable editor.

**`pyproject.toml`** — repository defaults for runtime and tooling:

```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.pyright]
venvPath = "."
venv = ".venv"
include = ["adrift", "tests", "typings"]
exclude = ["**/node_modules", "**/__pycache__", "**/.*", ".venv"]

[tool.pytest.ini_options]
addopts = "-m 'not slow'"
```

**`pyrightconfig.json`** — project type-checking policy:

```json
{
  "typeCheckingMode": "strict",
  "include": ["adrift", "tests", "typings"],
  "exclude": ["**/node_modules", "**/__pycache__", "**/.*", ".venv"]
}
```

Note: earlier versions of these docs referenced import-linter and local wrapper scripts
(`adrift.utils.validate_contract`, `adrift.utils.validate_no_duplicates`). Those files are not
included in this repository.

### VS Code

| Extension | ID | Required |
| --- | --- | --- |
| Remote - WSL | `ms-vscode-remote.remote-wsl` | Yes |
| Python | `ms-python.python` | Yes |
| Pylance | `ms-python.vscode-pylance` | Optional |
| Ruff | `charliermarsh.ruff` | Optional |
| Error Lens | `usernamehehe.errorlens` | Optional |
| Even Better TOML | `tamasfe.even-better-toml` | Optional |

**`.vscode/settings.json`:**

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "editor.formatOnSave": true,
  "[python]": { "editor.defaultFormatter": "charliermarsh.ruff" }
}
```

**`.vscode/tasks.json`:**

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Ruff: Check",
      "type": "shell",
      "command": "${config:python.defaultInterpreterPath}",
      "args": ["-m", "ruff", "check", "adrift", "tests", "typings"]
    },
    {
      "label": "Ruff: Format Check",
      "type": "shell",
      "command": "${config:python.defaultInterpreterPath}",
      "args": ["-m", "ruff", "format", "--check", "adrift", "tests", "typings"]
    },
    {
      "label": "Complexity: Lizard Check",
      "type": "shell",
      "command": "${config:python.defaultInterpreterPath}",
      "args": ["-m", "lizard", "adrift", "-C", "8", "-L", "30", "-a", "4"]
    }
  ]
}
```

* * *

## Rules

Every rule is paired with its enforcement tier. Rules marked **review** have no automated mechanism — they are candidates for future tooling.

| Rule | Tier | Mechanism |
| --- | --- | --- |
| Function length ≤ 30 lines | Automated | Lizard |
| Cyclomatic complexity ≤ 8 | Automated | Lizard |
| Nesting depth ≤ 3 | Review | — |
| Parameters per function ≤ 4 | Automated | Lizard |
| No type errors | Advisory | Pyright strict config in `pyrightconfig.json`; run via `check_static.py` |
| No lint violations | Automated | Ruff |
| Dead code confidence floor (80%+) | Automated | Vulture |
| No mutable globals | Review | Pyright can detect some cases when run |
| No silent exception swallowing | Review | Not currently selected in Ruff rules |
| No vars, secrets, or paths outside Ansible | Review | — |
| No Ansible queries mid-reconciliation | Review | — |
| No CQS violations — functions either mutate or return, not both | Review | — |

Prefer early returns over nested conditionals. If a function needs more than 30 lines, it has more than one responsibility — split it.

* * *

## Contribution Workflow

```text
0. After cloning:              poetry install
1. Branch from main
2. Run quality checks:         run the direct tooling commands or use the VS Code tasks
                              (see `.vscode/tasks.json`). Example:
                              `.venv/bin/ruff format --check adrift tests typings`
                              `.venv/bin/ruff check adrift tests typings`
                              `.venv/bin/python -m lizard adrift -C 8 -L 30 -a 4`
                              `.venv/bin/python -m vulture adrift tests typings --min-confidence 80`
                              `.venv/bin/ty check --project .`
3. Run tests:                  pytest
4. Push
5. Open PR — check checklist
```

### PR Checklist

- [ ] All automated checks pass
- [ ] No vars, secrets, or paths declared outside Ansible
- [ ] No Ansible queries mid-reconciliation
- [ ] No CQS violations — functions either mutate or return, not both
- [ ] Tests added or updated
- [ ] `PLAYBOOK.md` updated if any structural decision changed
