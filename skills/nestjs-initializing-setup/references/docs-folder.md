# The `docs/` folder

`spec.rp.md` is frozen after confirmation (Phase 3) — it's the record of
*what* was agreed to. `docs/` is where everything that happens *after*
that lives: decisions, discovered bugs, working notes, and the prompts
that shaped the session. Keep it updated live; it's working memory, not an
end-of-project writeup.

## `docs/decisions.md`

ADR-lite entries for anything decided during the build that wasn't already
pinned down in the spec — which local Mongo replica-set setup was chosen,
a schema tweak, a tradeoff on whether a given write needed a transaction.

```markdown
## <date> — <short decision title>

**Context:** why this came up
**Decision:** what was chosen
**Alternatives considered:** what else was on the table, and why not
```

## `docs/prompts.md`

A log of the significant instructions or requests given during the
session, so a future developer (or a future session) can see why the
project looks the way it does without reconstructing it from git blame.

```markdown
## <date>

> <the instruction or request, quoted or paraphrased>

Resulting change: <short pointer to what this led to>
```

## `docs/bugs.md`

Minor bugs noticed in passing but not immediately fixed. Every entry gets
a status so nothing quietly falls off the list.

```markdown
## <date> — <short bug description>

**Where:** file/module
**Status:** open | fixed (<date>) | deferred (<reason>)
```

## `docs/notes.md`

Free-form scratch space for anything that doesn't fit the other three —
open threads, things to revisit, context that's useful but not a formal
decision or bug.
