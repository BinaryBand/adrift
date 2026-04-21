# VS Code setup (template)

<!-- cspell: words pyrightconfig venv virtualenv pyproject charliermarsh -->

Brief template describing the VS Code configuration used in this repository and a small set of snippets you can copy to other projects.

This focuses on: Lizard (complexity), Vulture (dead code), Ruff (lint/format), Pyright (type checking), and how to avoid enforcing workspace Pylance type-checking standards.

---

## Quick summary

- Purpose: provide a small, portable `.vscode` configuration and task examples to run the project's quality gates from the editor.
- Tools: `ruff`, `lizard`, `vulture`, `pyright` (CLI or VS Code extension).
- Pylance: disable workspace type-checking and prefer a project `pyrightconfig.json` for per-project rules.

## Install (recommended)

Install CLI tools into the project's virtualenv and Pyright via npm (or use the VS Code extension):

```bash
python -m pip install --upgrade ruff lizard vulture
# If you want the Pyright CLI (optional):
npm install --save-dev pyright
```

Alternatively rely on the VS Code extensions (`ms-python.vscode-pylance` or `ms-pyright.pyright`) for inline type checking.

## Recommended VS Code extensions

- `ms-python.python` — core Python extension
- `ms-python.vscode-pylance` — language server (can be configured to *not* enforce strict workspace checks)
- `ms-pyright.pyright` — optional, if you prefer Pyright integration
- `charliermarsh.ruff` — optional ruff integration/formatting

Note: Lizard and Vulture are typically run as CLI tasks — there isn't a standard VS Code extension for them.

## Example `.vscode/settings.json`

Copy this into `.vscode/settings.json` and adapt the interpreter path if you don't use `.venv`:

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.analysis.typeCheckingMode": "off",
  "python.analysis.diagnosticMode": "openFilesOnly",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": { "source.fixAll": true },
  "[python]": { "editor.defaultFormatter": "charliermarsh.ruff" }
}
```

Explanation:

- `python.analysis.typeCheckingMode: "off"` disables Pylance workspace type-checking so the extension won't impose stricter checks; use `pyrightconfig.json` to opt-in per-project.
- `python.defaultInterpreterPath` points VS Code to the project's venv.

## Example `.vscode/tasks.json` (templates)

Below are tasks you can copy; adjust paths to your project's layout and virtual environment.

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Ruff: Check",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/bin/ruff",
      "args": ["check", "src", "tests", "typings"],
      "group": "build"
    },
    {
      "label": "Ruff: Format Check",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/bin/ruff",
      "args": ["format", "--check", "src", "tests", "typings"],
      "group": "build"
    },
    {
      "label": "Complexity: Lizard",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["runbook/quality/check_complexity.py", "src", "--ccn", "8", "--length", "25", "--params", "4"],
      "group": "build"
    },
    {
      "label": "Dead Code: Vulture",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["runbook/quality/check_dead_code.py", "src"],
      "group": "build"
    },
    {
      "label": "Pyright: Check",
      "type": "shell",
      "command": "npx",
      "args": ["pyright"],
      "group": "build"
    }
  ]
}
```

Notes:

- If you install Pyright as a dev dependency, `npx pyright` runs the local CLI. If you install pyright globally, replace the command with `pyright` or point to the binary.
- Adjust the `args` shown for `ruff` and other tools to match what you want scanned.

## Minimal `pyrightconfig.json` (per-project rules)

Use a `pyrightconfig.json` at project root to declare type-checking behavior for this project rather than using Pylance workspace defaults.

```json
{
  "typeCheckingMode": "off",
  "exclude": ["**/.venv/**", "**/build/**", "**/typings/**"]
}
```

Switch `typeCheckingMode` to `basic` or `strict` when you want stricter checks for that repository.

## Porting checklist (how to copy this to a new project)

1. Copy `.vscode/settings.json` and `.vscode/tasks.json` from this repo into the new repo.
2. Add dev tooling to the project's dev deps (pip `requirements-dev.txt` or `pyproject`, and `package.json` for `pyright`):
   - `ruff`, `lizard`, `vulture` via pip
   - `pyright` via npm (optional)
3. Update `python.defaultInterpreterPath` if the venv name/path differs.
4. Add or tune `pyrightconfig.json` to enable project-specific type checking.
5. Run the tasks from VS Code: `Terminal` → `Run Task...` and verify outputs.

## Notes and best practices

- Keep most type-checking rules in `pyrightconfig.json` (version-controlled) rather than pushing stricter Pylance workspace settings to everyone.
- Prefer running `ruff` as a formatter on save (via editor settings) and as a CI check via the same CLI arguments.
- Consider a small `dev-setup` script (or Makefile) that bootstraps the venv and installs dev dependencies — this simplifies porting.

---

If you'd like, I can also add a `.vscode` template folder to the repo and a small `scripts/` helper to copy it into other projects.
