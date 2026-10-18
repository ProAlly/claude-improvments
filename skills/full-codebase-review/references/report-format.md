# Reporting format

## Per-finding shape (used by every chunk subagent, and by the final
## `ReportFindings` call)

Each finding is:

- `file` — repo-relative path.
- `line` — the anchoring line number.
- `category` — short kebab-case slug: `clean-code`, `solid`,
  `architecture`, `concurrency`, `db-transactions`, `n-plus-one`,
  `error-handling`, `correctness`, etc.
- `verdict` — `CONFIRMED` (traced through the actual code path and
  certain) or `PLAUSIBLE` (a real concern but couldn't fully trace every
  branch/caller to be certain). Never drop a `PLAUSIBLE` finding just for
  being unconfirmed — that's what the low bug-threshold in this skill is
  for. Only drop a finding that has no concrete failure scenario at all.
- `short_summary` — ≤60 chars, the claim alone.
- `summary` — one sentence stating the defect.
- `failure_scenario` — concrete inputs/state → wrong output/crash/
  corruption. This is the field that separates a real finding from a
  hunch; require it from every subagent.

Ask each chunk subagent to return findings in this exact shape (as a
plain list in its final message is fine — it doesn't need to call
`ReportFindings` itself, only the parent does, once, at the end).

## Severity ordering for the final ranked list

Most severe first:

1. Data-integrity bugs: transaction/rollback issues, race conditions
   that can corrupt or duplicate data.
2. Uncaught exceptions / unhandled rejections that can crash a process
   or silently drop work.
3. N+1 queries and other DB performance bugs.
4. Architecture and layering violations.
5. SOLID/OOP design violations.
6. Other correctness bugs (off-by-one, null derefs, etc.) not already
   covered above.
7. Clean-code/readability nitpicks.

Within a category, `CONFIRMED` findings rank above `PLAUSIBLE` ones.

## Deduping across chunks

Two chunks can both flag the same underlying defect from different
files (a caller and the repository method it calls, both pointing at a
missing transaction). Merge these into one finding whose `file`/`line`
points at the actual root cause (usually the callee, since that's where
the fix belongs), and mention the caller(s) affected in the summary.

## Markdown report template

Write to `<repo-root>/.claude/code-reviews/<UTC timestamp>-full-review.md`:

```markdown
# Full Codebase Review — <UTC timestamp>

## Coverage
- Files reviewed: <N> across <M> chunks
- Not reviewed (access denied / out of scope): <list, or "none">
- Languages: <list>

## Summary
<N findings — X confirmed, Y plausible. Breakdown by category.>

## Findings

### 1. <short_summary> — <file>:<line>
- **Category:** <category> · **Verdict:** <CONFIRMED|PLAUSIBLE>
- **Issue:** <summary>
- **Failure scenario:** <failure_scenario>

### 2. ...
```

Order findings in the file the same way as the severity ordering above,
so the file and the `ReportFindings` UI output agree with each other.
