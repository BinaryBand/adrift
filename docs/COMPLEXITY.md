# Complexity Resolution Protocol (AI/Human Dual-Access)

<!-- cspell: words NLOC -->

This document provides an abstract, project-agnostic protocol for detecting, prioritizing,
and resolving code complexity violations reported by static analysis tools (for
example, Lizard). It is intended to be followed by both human developers and
automation (scripts or agents).

## 1. Complexity Scan

Run your chosen complexity analysis tool over the target paths using sensible
thresholds for your project. Example invocation with Lizard (replace placeholders
as appropriate):

```sh
python -m lizard <paths> -C <ccn> -L <length> -a <params> [-w]
```

The analysis output typically reports per-function metrics such as: NLOC (lines
of code), CCN (cyclomatic complexity), parameter count, and starting line
location.

## 2. Violation Extraction (Script-able)

- Extract lines that indicate metric violations or warnings from the tool's
  output.
- For each violation record:
  - file path
  - function name or location
  - metrics (NLOC, CCN, parameter count, length)

Keep this representation machine-readable (JSON, CSV, or structured text) so
automation can sort and prioritize violations.

## 3. Triage & Prioritization

Prioritize the violations using clear, project-specific rules. A typical order
is:

1. CCN (descending)
2. NLOC (descending)
3. Parameter count (descending)
4. File path or module ownership (alphabetical or by subsystem)

Define what constitutes "high-risk" in your project. Example thresholds (treat
as configurable): CCN ≥ 9, NLOC ≥ 25.

## 4. Resolution Protocol

For each violation (start with highest-risk):

4.1 Analyze the function

- Read the function and nearby code to understand behavior and constraints.
- Identify the sources of complexity (deep nesting, many conditional branches,
  inlined helper logic, large switch/if chains, multiple responsibilities).

4.2 Refactor options (choose the smallest change that reduces complexity)

- Extract Method: move logical blocks into well-named helper functions.
- Reduce Nesting: use guard clauses/early returns to flatten structure.
- Simplify Conditionals: consolidate or replace with tables/strategy objects.
- Limit Parameters: group related parameters into small value objects or
  context objects.
- Rename & Document: clarify intent with naming and brief rationale comments
  when complexity is unavoidable.

4.3 Validate

- Rerun the complexity scan for the modified scope.
- Confirm the target function's metrics are below thresholds or that
  complexity is documented and justified.

## 5. Documentation & Tracking

Maintain a concise resolution log for each addressed violation. Each entry
should include:

- file and function
- before metrics (NLOC, CCN, params, length)
- after metrics (same fields)
- refactor summary (list of atomic changes such as "Extracted X to helper Y")
- justification when complexity remains (brief explanation)
- link or reference to the code review/commit that implemented the change

Store logs in a machine-readable format (JSON/YAML) or append to a
project-level document so automation can surface progress.

## 6. Automation Hooks

Design the protocol so that these steps can be automated or assisted by agents:

- Run the scan and parse violations into structured records.
- Automatically prioritize and assign violations for triage.
- Run suggested lightweight refactors (e.g., extract small helpers) as
  candidate patches for review.
- Re-run the scan and publish a resolution log entry upon successful
  validation.

## 7. Example Violation Record (Template)

```json
{
  "file": "<path/to/file.py>",
  "function": "<function_name>",
  "before": {"NLOC": 42, "CCN": 8, "PARAM": 3, "length": 42},
  "after": {"NLOC": 18, "CCN": 3, "PARAM": 2, "length": 18},
  "refactor": ["Extracted helper _compute_x", "Replaced nested ifs with guard clauses"],
  "justified": false,
  "notes": "Reduced complexity below threshold; see commit <sha>"
}
```

## 8. Running the Protocol

- Use the project's existing complexity script (if present) or the tool's CLI
  to collect violations.
- Triage and perform refactors in small, reviewable commits.
- Prefer minimal, behavior-preserving changes and include tests where useful.

## 9. Maintenance

- Keep thresholds and tooling configuration in source control (so scans are
  reproducible).
- Periodically review the protocol and update thresholds or steps as the
  codebase evolves.
- Ensure CI enforces or reports complexity regressions according to project
  policy.
- **Justification:**
