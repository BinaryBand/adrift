# Architecture Refactoring Playbook

This playbook defines how to reorganize code safely when complexity grows.

Use this process when:

- Lizard shows repeated complexity pressure.
- Files are too large or blend multiple responsibilities.
- Team velocity slows because changes require touching many unrelated modules.

## Recommended Strategy

Use a hybrid strategy in this order:

1. Mikado Method for execution safety.
2. Hotspot prioritization for choosing targets.
3. Package by feature for final structure.
4. Bounded contexts for long-term folder boundaries.

Do not use clustering output as an automatic move engine.
Treat it as a proposal generator that requires review.

## Complexity Budgets (Lizard)

Use Lizard as a rough success guide, not a hard architecture truth.

### Function-Level Guardrails

Keep existing function guardrails:

- CCN <= 5
- Function length <= 25
- Parameter count <= 4

### File-Level Budget (Rough)

Use these as default targets for Python modules:

- File total CCN budget: <= 60
- Average CCN per function: <= 3
- Functions at CCN ceiling (5): <= 20% of functions in file

Interpretation:

- Exceeding the total file budget suggests mixed responsibilities.
- High average CCN suggests broad branching pressure.
- Too many near-ceiling functions suggests a refactor queue.

### Folder-Level Budget (Rough)

Track folder complexity as an aggregate to detect architecture drift.

Suggested targets per top-level feature folder:

- Folder total CCN budget: <= 300
- Any one file should contribute <= 35% of folder CCN
- Hotspot concentration: top 3 files should contribute <= 70% of folder CCN

Interpretation:

- A single dominant file often indicates a hidden subsystem.
- Top-heavy concentration suggests extracting submodules.

### Success Criteria Using Budgets

Treat a reorganization as successful when all are true:

- Target file falls below function and file budgets.
- Folder concentration improves or stays stable.
- Tests pass with unchanged behavior.
- No new circular dependencies are introduced.

### Reporting Cadence

Run budget reporting at two cadences:

- On every PR: function-level checks (existing `check_complexity.py`).
- Weekly or before large refactors: file and folder aggregate report.

The weekly report should guide prioritization, not block merges.

## 1. Prioritize With Hotspots

Pick refactoring targets by combining:

- Complexity: Lizard metrics (CCN, function length, parameter count).
- Churn: change frequency from git history.

Prioritize areas that are high in both.

Suggested scoring model:

- Hotspot score = normalized complexity x normalized churn.
- Tackle highest score first.

## 2. Execute With Mikado

For each hotspot:

1. Define one target outcome.
2. Attempt the smallest direct change.
3. If blocked, record prerequisite changes.
4. Revert partial attempt if needed.
5. Implement prerequisites first in dependency order.
6. Re-attempt target change.

Keep each step small and reversible.

## 3. Refactor Order (Function -> File -> Folder)

Always refactor in this sequence:

1. Split large functions.

2. Split large files.

3. Reorganize folders by feature and domain.

### 3.1 Split Large Functions

- Extract pure helper functions first.
- Keep behavior unchanged.
- Preserve public function signatures unless migration is explicit.

### 3.2 Split Large Files

- Identify distinct responsibilities.
- Move private helpers to concern-specific modules.
- Keep a thin facade in the original file if imports depend on it.

### 3.3 Reorganize Folders

- Group by business capability, not technical layer alone.
- Keep shared utilities small and clearly owned.

## 4. Relationship Tree and Clustering (Advisory)

Build a relationship graph to guide decisions:

- Function call graph.
- Import/dependency graph.
- Data model usage graph.
- Optional: co-change graph from git.

Use graph clustering to suggest module boundaries:

- Community detection (Louvain or Leiden) for graph structure.
- Hierarchical clustering for semantic similarity.

Human review is required before any move.
Reject clusters that create circular imports or cross bounded contexts.

## 5. Boundaries and Ownership

Define each module with:

- One primary responsibility.
- A clear owner.
- Stable public interface.
- Explicit dependency direction.

Boundary rules:

- Core/domain modules do not import infrastructure details.
- Inward dependencies only for business-critical layers.
- Shared helpers must remain generic; otherwise move to feature scope.

## 6. Safety Rails

For every refactor batch:

- Keep changes small enough to review quickly.
- Run tests and quality checks after each batch.
- Fail fast on behavior regressions.
- Avoid broad renames and relocations in one commit.

Minimum verification for each batch:

- Unit tests in affected areas.
- Ruff check and format check.
- Lizard check for touched modules.

## 7. Done Criteria

A refactor is done when:

- Complexity reduced in target hotspot.
- File/module cohesion improved.
- Coupling and import fan-out reduced or unchanged.
- Public behavior preserved.
- Tests and checks pass.

## 8. Practical Workflow for This Repository

1. Generate hotspot list from Lizard plus recent git churn.
2. Select one hotspot at a time.
3. Apply Mikado steps for that hotspot.
4. Split function-level concerns first.
5. Promote coherent helper groups into new modules.
6. Keep compatibility facades where imports are already widespread.
7. Re-run checks and tests.
8. Repeat.

## 9. Anti-Patterns

Avoid:

- Big-bang folder reorgs.
- Moving code based only on naming similarity.
- Deleting symbols solely due to low-confidence dead-code reports.
- Mixing architectural migration with unrelated feature work.

## 10. Decision Log Template

For each major reorganization decision, record:

- Context: what pain point was observed.
- Decision: what boundary or move was chosen.
- Alternatives: what was considered and rejected.
- Consequences: trade-offs and follow-up work.

This keeps architectural intent explicit and reviewable over time.
