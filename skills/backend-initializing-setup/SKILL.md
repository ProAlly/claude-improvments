---
name: backend-initializing-setup
description: Guided workflow for starting a brand-new backend service or API from scratch — a discovery interview, a developer-confirmed and then locked requirements spec (spec.rp.md), project scaffolding, and an enforced development loop (SOLID boundaries, ACID-safe data access, TDD, linting/pre-commit hooks, and always-current Swagger/OpenAPI docs). Use this whenever a developer wants to "set up a new backend", "scaffold an API project", "start a new service from scratch", "bootstrap a backend repo", or describes an app idea and needs help turning it into a real backend project — even if they haven't picked a stack yet or only have a rough idea, a design image, or a doc to share. Also use it whenever spec.rp.md is mentioned, or when continuing work on a project that already has one.
user-invocable: true
---

# Backend Initializing Setup

Bootstrapping a backend badly compounds forever — a vague spec, a skipped
test, or an undocumented endpoint from day one turns into weeks of drift
later. This skill exists to front-load a clear, developer-confirmed spec and
then hold the line on it and on a few non-negotiable engineering habits
while the project actually gets built.

The workflow has six phases. The first three happen once, near the start.
Phase 6 applies to every single change for the rest of the project's life —
treat it as the default mode of working, not a one-time checklist.

## Asking the developer questions

Every phase below involves asking the developer things. Whenever a
question has a reasonably enumerable set of answers, ask it as an
interactive multiple-choice prompt (the AskUserQuestion tool, if your
environment provides one) instead of an open-ended question — picking from
2-4 clear options is faster and less error-prone for the developer than
typing back a paragraph of context. Keep the wording plain and short:
describe the choice in everyday terms, skip unexplained jargon, and always
leave room for "something else" (a free-text/"Other" option), since
multiple choice should never trap the real answer. If no interactive-
question tool is available, present the same options as a short lettered
list in your reply instead. Reserve genuinely open-ended questions (e.g.
"describe the project") for things that can't be reduced to options.

## Phase 1 — Discovery

Ask the developer to describe the project in their own words: what it does,
who uses it, the core features, and anything they can share — a doc, a
design image, a wireframe, a link to a similar API, an existing repo to
match conventions with. Read whatever they hand over closely; if a design
image implies a data model or a flow, extract it rather than re-asking for
something already shown.

Then fill the gaps yourself by asking about anything load-bearing that
wasn't mentioned: tech stack preference (or "no preference — you recommend
one"), database choice, auth model, deployment target, expected scale or
team size, and any conventions the developer already has elsewhere. Small
stylistic choices can default sensibly and get confirmed later in the spec
review — but anything that would reshape the data model, the auth story, or
the API surface needs an answer before you draft the spec, not a guess.

Don't move to Phase 2 while a load-bearing unknown remains. Guessing here is
the single most expensive mistake this skill can make, because the spec
built on top of a wrong guess is the thing that then gets locked.

## Phase 2 — Draft `spec.rp.md` and get explicit confirmation

Write the requirements spec at the project root as `spec.rp.md`, using
[references/spec-template.md](references/spec-template.md) for the shape.
Fill it from what Phase 1 established — don't introduce new requirements
here that the developer didn't state or agree to.

Show the developer the result (the file itself, or a clear summary of it)
and ask for explicit confirmation — something unambiguous like "yes, that's
right" or "confirmed", not silence or a vague "looks fine, keep going" that
could just mean "I skimmed it." If they want changes, make them freely; the
lock described in Phase 3 only begins once they've actually confirmed.

## Phase 3 — Lock-in

Once confirmed, `spec.rp.md` is frozen. Say so explicitly at confirmation
time so it's not a surprise later — something like "This spec is now
locked; I won't change it unless you explicitly ask me to."

From this point on:

- New ideas, scope creep, or things discovered mid-build never get folded
  into `spec.rp.md` silently. They go into `docs/decisions.md` as a
  decision, or get raised as a question to the developer.
- If a genuine gap or contradiction in the spec surfaces later, ask the
  developer whether to (a) amend the spec — which needs their explicit
  go-ahead — or (b) treat it as an implementation-level decision that
  doesn't touch the spec at all. Don't decide that split yourself.
- The developer saying "actually, let's change X" later **is** explicit
  permission. Edit it then, and note what changed and when — either at the
  bottom of the file or in `docs/decisions.md`, whichever the developer
  prefers.

## Phase 4 — Set up `docs/`

Create a `docs/` folder alongside `spec.rp.md` to hold everything that
isn't the frozen spec: `decisions.md`, `prompts.md`, `bugs.md`, and
`notes.md`. See [references/docs-folder.md](references/docs-folder.md) for
what belongs in each and templates to seed them with.

`scripts/scaffold_docs.py` creates this skeleton (and a `spec.rp.md` from
the template, only if one doesn't already exist) in one step:

```
python scripts/scaffold_docs.py --root /path/to/project
```

Keep these files updated live as the session progresses — they're the
project's working memory, distinct from the spec, which stays still.

## Phase 5 — Scaffold the project

Confirm the stack from `spec.rp.md`. If it was left open, propose one that
fits the requirements and get a thumbs-up before generating code — don't
default to Node because it's common if the spec implies something else.

- **Structure for SOLID from the first commit**: separate routing/
  controllers, business logic (services), and data access (repositories),
  with the boundaries between them depending on abstractions, not concrete
  implementations. See [references/engineering-principles.md](references/engineering-principles.md).
- **Wire the data layer for ACID correctness**: multi-step writes go inside
  transactions, there's no code path that leaves a partial write committed,
  and migrations are tracked from the very first schema change.
- **Set up the test framework before or alongside the first real feature**
  — TDD is the default working mode from here on, not a step that happens
  once at the end. Same reference file covers the expected loop.
- **Install linting and a pre-commit hook**: ESLint + Husky for Node/TS
  stacks, or the ecosystem-native equivalent for anything else. See
  [references/tooling-setup.md](references/tooling-setup.md) — ask the
  developer if it's genuinely unclear which tool is idiomatic for their
  stack rather than picking one silently.
- **Wire up Swagger/OpenAPI generation immediately**, even while the API
  surface is still nearly empty, so it's a living habit and not a
  retrofit. See [references/swagger-openapi.md](references/swagger-openapi.md).

## Phase 6 — The development loop (applies to every change, forever)

This is the mode to stay in for the rest of the project, whether it's the
initial scaffold or a change made months later:

- **Test-first.** Write or update tests alongside the code change, not
  after "if there's time." A change without a test isn't done.
- **Docs stay current.** Any change to a controller, service, or endpoint —
  even a small one, like a renamed field or a new optional query param —
  gets its Swagger/OpenAPI annotation updated in the *same* step. Never
  queue documentation as follow-up work.
- **Report minor bugs, don't bury them.** Noticing something broken or off
  while working on something else is common — say so explicitly ("Note: I
  noticed X looks wrong in Y — want me to fix it now or leave it?") instead
  of silently patching it or silently moving past it. Fix it unasked only
  when it's trivially inside the blast radius of the current change.
- **Stay in scope.** Build what was asked. Don't add extra endpoints,
  fields, config flags, or abstractions "while in there," and don't design
  for hypothetical future needs. If something genuinely seems required to
  do the task properly, ask — don't assume.
- **Ask instead of guessing.** For any small ambiguity — an edge case, a
  naming choice, an unclear validation rule — ask a specific question
  rather than picking a default and moving on. This is distinct from the
  big discovery questions in Phase 1; these are the small in-the-weeds
  ones that come up while building.
- **Keep comments minimal.** A short header comment on a file or exported
  unit explaining its purpose is fine. Inline comments narrating what the
  code below it does are not — if the code needs that, the code should be
  clearer instead.

## Reference files

Read these when the relevant phase comes up — don't load them all up front.

- [references/spec-template.md](references/spec-template.md) — the shape
  `spec.rp.md` should take.
- [references/engineering-principles.md](references/engineering-principles.md) —
  what SOLID, ACID, and TDD look like concretely in a backend scaffold.
- [references/tooling-setup.md](references/tooling-setup.md) — ESLint +
  Husky setup for Node/TS, and the equivalent tooling for other stacks.
- [references/swagger-openapi.md](references/swagger-openapi.md) — wiring
  up OpenAPI generation per stack and keeping it current.
- [references/docs-folder.md](references/docs-folder.md) — templates for
  `docs/decisions.md`, `docs/prompts.md`, `docs/bugs.md`, `docs/notes.md`.
- `scripts/scaffold_docs.py` — one-shot script that creates the `docs/`
  skeleton and an initial `spec.rp.md` from the template.
