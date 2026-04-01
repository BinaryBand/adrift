# Contributing

Bounded constraints for contributors. The goal is a solution space tight enough that any output passing these rules is consistent, reviewable, and mergeable without negotiation.

See `ARCHITECTURE.md` for tool responsibilities and structural decisions.

* * *

## Setup

WSL with base Debian compatibility is the development target.

```bash
poetry install
pre-commit install --hook-type pre-push
```

Open in VS Code from inside WSL:

```bash
code .
```

### Universal Config Files

All tooling behaviour is driven by committed config files — editor-agnostic, picked up automatically by any LSP-capable editor.

**`pyproject.toml`** — includes the following configurations:

```toml
[tool.ruff]
target-version = "py311"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "strict"
venvPath = "."
venv = ".venv"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.importlinter]
root_package = "src"

[[tool.importlinter.contracts]]
name = "Reconciler must not import utils"
type = "forbidden"
source_modules = ["src.reconciler"]
forbidden_modules = ["src.utils"]

[[tool.importlinter.contracts]]
name = "Utils must not import reconciler"
type = "forbidden"
source_modules = ["src.utils"]
forbidden_modules = ["src.reconciler"]

[[tool.importlinter.contracts]]
name = "Models must not import anything internal"
type = "forbidden"
source_modules = ["src.models"]
forbidden_modules = ["src.reconciler", "src.utils"]
```

**`.ansible-lint`:**

```yaml
profile: production
exclude_paths:
  - ansible/molecule.yml
warn_list:
  - experimental
skip_list: []
```

**`.editorconfig`:**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
indent_style = space
indent_size = 4

[*.{yml,yaml,toml,json,j2}]
indent_style = space
indent_size = 2
```

**`.pre-commit-config.yaml`** — ensures consistent quality gates on every push:

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff
        name: Ruff lint
        entry: .venv/bin/ruff check
        language: system
        types: [python]

      - id: ruff-format
        name: Ruff format
        entry: .venv/bin/ruff format --check
        language: system
        types: [python]

      - id: pyright
        name: Pyright type check
        entry: .venv/bin/pyright
        language: system
        types: [python]
        pass_filenames: false

      - id: lizard
        name: Lizard complexity check
        entry: .venv/bin/lizard
        language: system
        args: ["src/", "-C", "5", "-L", "25", "-a", "4"]
        pass_filenames: false

      - id: import-linter
        name: Import linter
        entry: .venv/bin/lint-imports
        language: system
        pass_filenames: false

      - id: contract-validation
        name: Service contract validation
        entry: .venv/bin/python -m src.utils.validate_contract
        language: system
        pass_filenames: false

      - id: duplicate-values
        name: Duplicate value check
        entry: .venv/bin/python -m src.utils.validate_no_duplicates
        language: system
        pass_filenames: false
```

### VS Code

| Extension | ID | Required |
| --- | --- | --- |
| Remote - WSL | `ms-vscode-remote.remote-wsl` | Yes |
| Python | `ms-python.python` | Yes |
| Pylance | `ms-python.vscode-pylance` | Optional |
| Ruff | `charliermarsh.ruff` | Optional |
| Ansible | `redhat.ansible` | Optional |
| Error Lens | `usernamehehe.errorlens` | Optional |
| Even Better TOML | `tamasfe.even-better-toml` | Optional |
| Jinja | `samuelcolvin.jinjahtml` | Optional |

**`.vscode/settings.json`:**

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "python.languageServer": "Pylance",
  "python.analysis.typeCheckingMode": "strict",
  "terminal.integrated.defaultProfile.linux": "bash",
  "terminal.integrated.shell.linux": "/bin/bash",
  "files.associations": { "*.j2": "jinja-yaml", "*.toml": "toml" },
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
      "label": "Validate: Service Contract",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/bin/python -m src.utils.validate_contract",
      "group": "test",
      "presentation": { "reveal": "always", "panel": "shared", "clear": true },
      "problemMatcher": {
        "owner": "contract",
        "fileLocation": ["relative", "${workspaceFolder}"],
        "pattern": {
          "regexp": "^(ERROR|WARN)\\s+(.+):(\\d+):\\s+(.+)$",
          "severity": 1, "file": 2, "line": 3, "message": 4
        }
      },
      "runOptions": { "runOn": "folderOpen" }
    },
    {
      "label": "Test: Molecule",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/bin/molecule test -c ansible/molecule.yml",
      "group": "test",
      "presentation": { "reveal": "always", "panel": "dedicated", "clear": true },
      "problemMatcher": []
    },
    {
      "label": "Check: Complexity",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/bin/lizard src/ -C 5 -L 25 -a 4 --output-file /tmp/lizard_out.txt; cat /tmp/lizard_out.txt",
      "group": "test",
      "presentation": { "reveal": "always", "panel": "shared", "clear": true },
      "problemMatcher": {
        "owner": "lizard",
        "fileLocation": ["relative", "${workspaceFolder}"],
        "pattern": {
          "regexp": "^(.+):(\\d+):\\s+(.+)\\s+\\(complexity:\\s*(\\d+)\\)$",
          "file": 1, "line": 2, "message": 3
        }
      }
    }
  ]
}
```

* * *

## Rules

Every rule is paired with its enforcement tier. Rules marked **review** have no automated mechanism — they are candidates for future tooling.

| Rule | Tier | Mechanism |
| --- | --- | --- |
| Function length ≤ 25 lines | Automated | Ruff |
| Cyclomatic complexity ≤ 5 | Automated | Lizard |
| Nesting depth ≤ 3 | Review | — |
| Parameters per function ≤ 4 | Automated | Ruff |
| No type errors | Automated | Pyright (`strict`) |
| No lint violations | Automated | Ruff |
| No mutable globals | Automated | Pyright (`strict`) |
| No silent exception swallowing | Automated | Ruff (`B001`, `S110`) |
| No shell scripts — Python only | Automated | Ruff + pre-commit |
| Service contract consistent | Automated | `src.utils.validate_contract` — pre-push hook |
| No value declared in two places | Automated | `src.utils.validate_no_duplicates` — pre-push hook |
| No business logic outside `src/reconciler/` and `src/models/` | Automated | `import-linter` — pre-push hook |
| No vars, secrets, or paths outside Ansible | Review | — |
| No Ansible queries mid-reconciliation | Review | — |
| No CQS violations — functions either mutate or return, not both | Review | — |

Prefer early returns over nested conditionals. If a function needs more than 25 lines, it has more than one responsibility — split it.

* * *

## Contribution Workflow

```text
0. After cloning:              poetry install && pre-commit install --hook-type pre-push
1. Branch from main
2. Run quality checks:         python3 runbook/quality-checks
3. Run tests:                  pytest
4. Push — pre-commit hooks run automatically
5. Open PR — check checklist
```

### PR Checklist

- [ ] All automated checks pass
- [ ] No vars, secrets, or paths declared outside Ansible
- [ ] No Ansible queries mid-reconciliation
- [ ] No CQS violations — functions either mutate or return, not both
- [ ] Tests added or updated
- [ ] `ARCHITECTURE.md` updated if any structural decision changed
