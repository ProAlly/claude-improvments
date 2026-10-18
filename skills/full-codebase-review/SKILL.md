---
name: full-codebase-review
description: Full-coverage, whole-repository code review — not just the current diff. Reads every source file in the target codebase (via parallel subagents, chunked by module/directory) and hunts for clean-code/readability problems, SOLID and OOP-design violations, architectural and layering problems, race conditions and other concurrency bugs, database/transaction bugs (missing rollback, non-atomic multi-step writes, N+1 queries), uncaught exceptions and swallowed errors, and any other correctness bug — no matter how minor. Use this whenever the user asks for a "full codebase review", "deep code audit", "review the whole repo/codebase", "check for architectural problems", "find race conditions / N+1 queries / DB transaction bugs", "audit for SOLID/clean code violations", or wants an /ultrareview-style pass that runs locally without GitHub/cloud billing. This is NOT for reviewing just the current diff or a single PR — for that, use the code-review skill instead; this skill is specifically for exhaustive, repo-wide coverage.
user-invocable: true
---

# Full Codebase Review

A whole-repository audit, not a diff review. The point is coverage: every
source file gets read in full by something, and the bug bar is low — a
minor nitpick-level bug is still worth surfacing, not just the kind that
would block a merge. This trades speed and cost for thoroughness; say so
up front so the user can scope it down if they want.

This skill complements, not replaces, the `code-review` skill (fast,
diff-scoped, tuned for PRs) and `/code-review ultra` (cloud, multi-agent,
billed, GitHub-PR-shaped). This one runs entirely in-session, has no
billing step, and is meant for "review everything we have," not "review
what changed."

## Phase 0 — Confirm scope and get access

1. **Resolve the target directory.** If the current working directory is
   a throwaway/scratch workspace rather than a real project, or the user
   named a different project, get the session moved there first (the
   `change_directory` tool, or `request_directory` if the path isn't
   known) before reading anything. Never run this review against a
   scratch workspace by accident.
2. **Confirm it's actually a codebase.** A git repo is preferred (it gives
   you `git ls-files`, which respects `.gitignore` for free) but not
   required — Glob works too, you'll just need to hand-exclude build
   output yourself. If there's no `.git`, mention that a review still
   works but ask whether to `git init` only if the user brings it up —
   don't do it unprompted.
3. **Surface access problems instead of silently skipping.** If a Read,
   Grep, or Bash call against part of the tree gets denied (permission
   prompt declined, path outside an allowed root, submodule not checked
   out, etc.), don't quietly drop that area from coverage. Tell the user
   what's inaccessible and why, ask them to grant access or point you
   elsewhere, and if they can't/won't, carry the gap forward into the
   final report as an explicit "not reviewed" note rather than pretending
   coverage was complete.
4. **Optional scope narrowing.** If the skill was invoked with an argument
   (a path, glob, or module name), treat that as the review root instead
   of the whole repo. Otherwise default to the whole repo.

## Phase 1 — Inventory and chunk the codebase

Build the full file list and split it into review chunks sized for a
subagent's context, grouped by module/directory (not arbitrary line
counts) so each chunk stays architecturally coherent. See
[references/chunking.md](references/chunking.md) for the exact inventory
command, exclusion list, and sizing heuristic.

Before spawning anything, tell the user the scope in one line — file
count, chunk count, languages detected — so a surprisingly large monorepo
doesn't burn a huge amount of work before they get a chance to scope it
down. For a small/medium repo, just proceed. For something in the
thousands-of-files range, pause and confirm they want the full sweep
rather than a narrower scope.

## Phase 2 — Per-chunk deep review (parallel subagents)

Spawn one `general-purpose` Agent per chunk, **all in the same message**
so they run in parallel. Each subagent gets:

- The exact file list for its chunk (absolute paths).
- An instruction to **read every one of those files in full** — not grep
  excerpts, not a sample. Skimming defeats the point of a full-coverage
  review.
- The checklist from
  [references/checklist.md](references/checklist.md) — paste the
  categories inline in the prompt (subagents don't inherit this skill's
  context) or tell it to Read that file path directly if the path is
  reachable from its cwd.
- The bug threshold: **flag even minor issues** — style-level clean-code
  problems and nitpicks belong in the output, not just merge-blockers.
  The floor is on severity, not on rigor: every finding still needs a
  concrete failure scenario (specific input/state → specific wrong
  output, crash, or corruption), not a vague "this could be a problem."
  If a subagent can't articulate a concrete scenario, it's not a finding
  yet — it's a hunch, and hunches get left out.
- The required output shape (see
  [references/report-format.md](references/report-format.md)) — each
  finding as `file`, `line`, `category`, `verdict`
  (CONFIRMED/PLAUSIBLE), `short_summary`, `summary`, `failure_scenario`.
  Consistent shape is what makes aggregation in Phase 4 mechanical instead
  of another round of interpretation.

Run these in the background (the default) and let notifications land
rather than polling.

## Phase 3 — Cross-cutting architecture pass

Per-chunk review catches everything visible inside one module, but
architecture problems, race conditions, and transaction/N+1 patterns
often only show up *across* modules — a shared cache touched by two
services, a repository-layer method that's fine alone but triggers N+1
from every caller, inconsistent error-handling between two modules that
do the same kind of thing. Once the chunk reviews are back, do one more
pass — inline, or as its own subagent — that specifically reads:

- Entry points (route/controller/handler files) and the shared
  interfaces or base classes underneath them.
- The data-access layer (repositories, ORM models, query builders) as a
  whole, looking for transaction boundaries and N+1 call patterns that
  span multiple chunk boundaries.
- Anything the chunk reviews already flagged as suspicious, to check
  whether it's an isolated bug or a repeated pattern elsewhere.

## Phase 4 — Aggregate, dedupe, rank

Merge every chunk's findings plus the cross-cutting pass. Drop exact
duplicates (same file+line+claim surfaced by two chunks whose boundary
overlapped). Rank most-severe first: data-integrity/race-condition/
transaction bugs and uncaught exceptions above architecture/SOLID
violations, which rank above clean-code nitpicks. Keep low-confidence
findings rather than dropping them — mark them `PLAUSIBLE` instead of
`CONFIRMED` so the user can triage, per the low-bug-threshold ask. If two
findings describe the same underlying defect from different files
(e.g. a missing transaction wrapper reported from both the caller and
the repository method), merge them into one finding rather than double
counting.

## Phase 5 — Report

1. Call `ReportFindings` once with the final ranked list.
2. Also write a persistent Markdown report — this run asked for both.
   Save it under `<repo-root>/.claude/code-reviews/<UTC timestamp>-full-review.md`
   using the template in
   [references/report-format.md](references/report-format.md), and
   include the coverage summary (files reviewed, chunk count, any
   inaccessible paths from Phase 0). Link the file back to the user as a
   relative markdown link so they can open it, and mention it's safe to
   diff against next run to see what got fixed vs. what's new.
3. If the report file lands somewhere the user would want to see
   directly (not just referenced), consider `SendUserFile` for it — but a
   link is normally enough since it's already in their working tree.

## Reference files

- [references/chunking.md](references/chunking.md) — inventory command,
  exclusion list, and how to size/group chunks
- [references/checklist.md](references/checklist.md) — the full bug/
  design checklist to hand to each chunk subagent
- [references/report-format.md](references/report-format.md) — required
  per-finding shape, severity ordering, and the Markdown report template
