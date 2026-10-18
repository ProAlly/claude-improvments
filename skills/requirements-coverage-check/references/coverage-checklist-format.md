# Final coverage report — shape

Keep it scannable. The developer should be able to read this in a few
seconds and know exactly where things stand — it's a checklist, not a
narrative writeup.

```markdown
## Requirements coverage check — <date>

**Source(s) checked:** spec.rp.md | docs/decisions.md | conversation history
<list whichever actually applied>

### Confirmed done
- <item> — <one-line evidence: file/commit/test>
- <item> — <one-line evidence>

### Already known and acknowledged
- <item> — <where it was already flagged, e.g. "docs/bugs.md, deferred 2026-09-08">

### Resolved this check
- <item> — was unclear, developer confirmed: <intentional skip | fixed now | other>
  <if fixed now: one-line pointer to the change>
  <if intentional: noted in docs/decisions.md>

### Still open
- <item> — <why it's still open, if anything is left pending>
```

Omit any section that's empty rather than showing it with "none" — an
empty "Still open" section is good news and shouldn't take up space saying
so at length; a one-line "Still open: none" is enough, or drop the heading
entirely.

If this is a project using `spec.rp.md`, don't let this report imply the
spec changed — it didn't, and doesn't, regardless of what this check
turns up. Anything that looks like it should change the spec gets handled
through the explicit-permission path in Phase 5 of SKILL.md, not through
this report.
