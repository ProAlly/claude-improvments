# Global Claude Code instructions

Use family aliases (`haiku`, `sonnet`, `opus`), not pinned model IDs, unless a project file overrides them (never to `fable`).

## Role & Model Assignment Rules
* **Orchestrator Model:** Always use **Opus**. If the lead session is not on `opus`, tell the user before planning a complex task, and wait for them to switch or confirm continuing.
* **Reviewer Roles (both Opus):** a **plan reviewer** (optional Opus subagent that critiques the Execution Proposal Table) and a **diff reviewer** (checks the result after execution).
* **Approval comes only from the user.** Reviewer feedback is advisory and never counts as approval.
* **Excluded Models:** `fable` is strictly forbidden and must never be assigned or used.

---

## Task Decomposition & Execution Workflow

### 1. Planning & Atomic Breakdown
* When analyzing a task with multiple components (e.g., X, Y, Z):
  * Identify complex components (e.g., X and Z).
  * Generate a high-level plan for complex components **before** creating individual subtasks.
  * Deconstruct complex components into the **smallest possible, isolated atomic subtasks**.
* **Simple Task (handle directly, no subtasks, no subagents):** meets all of these:
  * touches **≤ 3 files**
  * stays within a **single module**
  * fits in the **current context window** without heavy search, logs, or test output
  * If any condition fails, treat it as complex and decompose it.

### 2. Model Assignment & Review Proposal
* Assign a model (`sonnet`, `haiku`, `opus`; never `fable`) to every subtask in the table. Start at the cheapest model that can do the job; assign stronger models to more complex subtasks, and verify the assignment matches the complexity before proposing.
* If requirements are underspecified, do not guess critical details: use retrievable context or state the assumption explicitly.
* Present an **Execution Proposal Table** to the user (and the optional Opus plan reviewer) containing:
  - `ID`
  - `Component`
  - `Subtask Description`
  - `Assigned Model`
  - `Dependencies`

### 3. Interactive Review Gate
* **PAUSE execution** immediately after presenting the table.
* The plan reviewer (if used) and the user assess the proposal.
* Ask for feedback and allow adjustments to subtask boundaries or model assignments.
* **Approval is once per plan:** one explicit approval covers every batch in that plan. Do not re-ask per batch.
* **Re-approval on change:** any later change to a subtask's boundaries (scope, files, split/merge) or assigned model invalidates approval for that subtask. Present the revised row(s) and get explicit approval **before that subtask runs**. Unchanged subtasks may continue.
* Do not proceed to execution until explicit approval is granted.

### 4. Subagent Execution Constraints
* Upon final approval, launch subagents to execute the subtasks.
* **Strict Concurrency Limit:** at most **7 concurrent subagents/subtasks** per batch, including verify spawns (aim for 5–7 when enough independent subtasks exist). With more than 7 subtasks, run successive batches of at most 7 in dependency order: a subtask is scheduled only after all its `Dependencies` finished in an earlier batch.
* **Model Locking:** every spawn MUST pass an explicit `model` set to the exact approved model for its subtask. Never omit it, because an omitted `model` inherits the parent's model.
  * `fable` is never passed and never inherited. If the parent runs on `fable`, an explicit non-`fable` `model` is mandatory.
  * No automatic fallbacks, model switching, or substitutions. If the approved model is unavailable, stop and re-propose.
* **Memory writes:** only the orchestrator writes memory files. Workers report candidate memory updates in their return format.

### 5. Verify
* After execution, the Opus diff reviewer checks the diff against the plan; `haiku` runs tests, lint and typecheck. On a simple task, the orchestrator self-reviews and runs tests once inline instead.
* Verify spawns (Opus diff reviewer, `haiku` test runner) and the fix-and-rerun loop (see Tests) are implicitly approved with those exact models; they still pass an explicit `model`.
* Review findings: mechanical → fix-and-rerun loop; scope or design → re-propose per §3.

---

## Model routing

| Phase | Model | Use for | Do not use for |
| --- | --- | --- | --- |
| Plan / architecture / “what should we change?” | `opus` | Tradeoffs, sequencing, API/schema design, migrations, blast-radius judgment | Mechanical edits, grepping, running tests |
| Review / “is this actually correct?” | `opus` | Final diff review, plan-vs-implementation check, security/architecture concerns | First-pass lint, formatting, log scraping |
| Implement / everyday agent work | `sonnet` | Coding, refactors, most debugging, most subagents, docs that need judgment | Cheap fan-out search; final architectural sign-off |
| Explore / search / classify | `haiku` | File discovery, pattern matching, summarizing logs, extracting facts | Design decisions, subtle reviews |
| Tests / tight feedback loops | `haiku` | `pytest` / `jest` / `vitest` / `go test` / typecheck / lint / format; parse output; rerun the failing slice | Interpreting a novel failure that needs a new design |

### Escalation
Move up a model only when the cheaper one is stuck, contradictory, or the cost of being wrong is high (auth, money, data loss, public API). Escalation is a change: re-propose the affected row(s) per §3 re-approval.

### Tests
- Implementation workers do not “declare done” without running the relevant tests, or stating exactly why they could not run.
- **Product/design** failure (wrong invariant, bad API) → back to `opus` for a revised plan; revised rows need re-approval per §3. Haiku never invents architecture.
- **Mechanical** failure (assertion, fixture, typo) → the subtask's approved implementation model fixes, `haiku` reruns. This fix-and-rerun loop is pre-approved as part of each implementation subtask.

---

## Worker prompts (keep them small)

Every spawned worker prompt should include:

- **Goal** in one sentence
- **In scope** files / symbols
- **Out of scope** (do not “while I’m here” adjacent modules)
- **Model** (the exact approved one)
- **Done when** (commands or checks)
- **Return format**: files changed, commands run, leftover risks, candidate memory updates — not a transcript dump

Prefer read-only workers for explore and review. Give write tools only to implementation workers.

---

## Anti-patterns

- One Opus session that searches, edits, reviews, and reruns the whole suite on a **complex** task (simple tasks, as defined in Task Decomposition §1, are still handled directly)
- Serial workers when the slices are independent
- Workers with vague “look around and improve things” prompts
- Reviewers that also rewrite the code they are reviewing (split review and fix)
- Haiku making schema, auth, or concurrency decisions
- Opus sitting in a `watch` / retry loop on tests (complex tasks only; on a simple task Opus may run the tests once inline, with no retry loop)

---

## Persistent Memory Protocol

Memory persists across sessions and is injected automatically at SessionStart via hooks.

## Memory Locations (Read/Write with Edit/Write tools)
- `~/.claude/memory/projects/<hash>/index.md` — Architecture, key files, patterns, active context
- `~/.claude/memory/projects/<hash>/decisions.md` — ADRs, design choices, rationale
- `~/.claude/memory/projects/<hash>/issues.md` — Bugs, fixes, gotchas, workarounds
- `~/.claude/memory/global/preferences.md` — Your personal coding standards

## Core Rules
1. **NEVER burn tokens reading the whole codebase.** Start with memory. If the context exists there, use it.
2. **Progressive Retrieval Only:** Memory → Grep/Search symbols → Read specific files → Verify.
3. **The orchestrator updates memory immediately** (workers only report candidates, see §4) after any significant architectural change, decision, or non-obvious bug fix:
   - New critical file → `index.md` Key Files
   - Design decision → append to `decisions.md` with rationale
   - Bug with subtle root cause → `issues.md`
   - Pattern/convention established → `index.md` Patterns
   - Personal preference discovered → `global/preferences.md`
4. **SOLID Compliance:** Check `decisions.md` before refactoring. Do not violate established patterns without documenting the exception.
5. **SessionStart = Ground Truth:** The memory injected at startup is your baseline. Confirm it is still valid; do not re-derive what you already know.
