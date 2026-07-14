# Contributing

Bounded constraints for contributors. The goal is a solution space tight enough that any output passing these rules is consistent, reviewable, and mergeable without negotiation.

* * *

## Setup

WSL with base Debian compatibility is the development target.

```bash
uv sync --all-groups
```

There is no `.pre-commit-config.yaml`; quality gates run through pytest (`tests/test_lint.py`) or directly:

```bash
.venv/bin/ruff check adrift tests
.venv/bin/ruff format --check adrift tests
.venv/bin/ty check --project .
.venv/bin/python -m vulture adrift tests --min-confidence 80
.venv/bin/python -m lizard adrift -x 'adrift/cli/*' -C 8 -L 30 -a 9
npx jscpd --config static/rules/jscpd.json .
ast-grep scan --config sgconfig.yml
```

The optional Rust alignment extension is built with maturin (see the `rust-align:` tasks in `.vscode/tasks.json`):

```bash
uv run maturin develop --manifest-path rust/adrift_rust_alignment/Cargo.toml
```

Open in VS Code from inside WSL:

```bash
code .
```

### Universal Config Files

All tooling behaviour is driven by committed config files -- editor-agnostic, picked up automatically by any LSP-capable editor.

**`pyproject.toml`** -- repository defaults for runtime and tooling (excerpt):

```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "S101"]

[tool.ty.src]
include = ["adrift"]

[tool.ty.rules]
# Enforce strict typing by default.
all = "error"

[tool.pytest.ini_options]
addopts = "-m 'not slow'"
```

Type checking is done by `ty` (strict: every rule is an error), configured under `[tool.ty.*]` in `pyproject.toml` and run via `ty check --project .`.

Copy-paste detection (jscpd), dependency architecture (import-linter), scaffold shape checks (pytest, `tests/test_lint.py::TestScaffold`), and AST patterns (ast-grep) are configured across `pyproject.toml`, `static/rules/`, and `sgconfig.yml`.

### VS Code

Recommended extensions are committed in `.vscode/extensions.json`:

| Extension | ID | Notes |
| --- | --- | --- |
| Python | `ms-python.python` | Recommended |
| Ruff | `charliermarsh.ruff` | Recommended; default formatter |
| Run on Save | `emeraldwalk.runonsave` | Recommended |
| Pylance | `ms-python.vscode-pylance` | Explicitly unwanted (ty is the type checker) |

Workspace settings are committed in `.vscode/settings.json` (format on save with Ruff, Ruff fix-all and import organization on save, pytest test discovery). Build/benchmark tasks for the Rust alignment extension are in `.vscode/tasks.json`.

* * *

## Rules

Every rule is paired with its enforcement tier. Rules marked **review** have no automated mechanism -- they are candidates for future tooling. Automated rules are enforced by `tests/test_lint.py` (and can be run directly).

| Rule | Tier | Mechanism |
| --- | --- | --- |
| Function length <= 30 lines | Automated | Lizard (`adrift/cli/*` excluded) |
| Cyclomatic complexity <= 8 | Automated | Lizard (`adrift/cli/*` excluded) |
| Parameters per function <= 9 | Automated | Lizard (`-a 9`) |
| Nesting depth <= 3 | Review | -- |
| No type errors | Automated | ty (strict, `[tool.ty.rules] all = "error"`) |
| No lint violations | Automated | Ruff (`E`, `F`, `I`, `S101`) |
| No bare `assert` outside tests | Automated | Ruff (`S101`; `tests/**` exempt) |
| No copy-paste duplication | Automated | jscpd (`static/rules/jscpd.json`, `static/rules/jscpd.tests.json`) |
| No layering violations | Automated | import-linter (shell + layer + independence contracts in `pyproject.toml`) |
| Scaffold / process rules | Automated | pytest shape checks (`tests/test_lint.py::TestScaffold`) + ast-grep (`static/rules/ast-grep`) |
| Dead code confidence floor (80%+) | Automated | Vulture |
| No mutable globals | Review | -- |
| No silent exception swallowing | Review | Not currently selected in Ruff rules |
| No CQS violations -- functions either mutate or return, not both | Review | -- |

Prefer early returns over nested conditionals. If a function needs more than 30 lines, it has more than one responsibility -- split it.

Note: by default `tests/test_lint.py` runs `ruff check --fix` and `ruff format` before asserting, so local runs auto-fix trivial violations. Set `ADRIFT_RUFF_AUTOFIX=0` (or `CI=true`) to make it check-only.

* * *

## Contribution Workflow

```text
0. After cloning:              uv sync --all-groups
1. Branch from main
2. Run quality checks:         pytest tests/test_lint.py
                               (or the direct tooling commands listed under Setup)
3. Run tests:                  pytest
4. Push
5. Open PR -- check checklist
```

### PR Checklist

- [ ] All automated checks pass (`pytest tests/test_lint.py`)
- [ ] No CQS violations -- functions either mutate or return, not both
- [ ] Tests added or updated
- [ ] Docs (`docs/SPECS.md`, `docs/CONTRIBUTING.md`) updated if behaviour or tooling changed
