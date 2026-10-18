---
name: nestjs-initializing-setup
description: Guided workflow for starting a brand-new NestJS backend from scratch, preset to a specific default stack — NestJS + MongoDB (Mongoose) with real multi-document ACID transactions, an in-memory cache layer, Swagger/OpenAPI, ESLint + Husky, and TDD via Jest. Same discovery → locked-spec (spec.rp.md) → docs/ → scaffold → enforced-dev-loop workflow as the general backend-initializing-setup skill, but skips the stack question since it's fixed. Use this whenever a developer wants to "set up a new NestJS backend/API", "scaffold a Nest project", "start a Nest.js service", or asks for a backend with this Nest+Mongo combination specifically. If they want a different database, cache, or framework, point them to backend-initializing-setup instead.
user-invocable: true
---

# NestJS Initializing Setup

This is the same discipline as the general backend-scaffolding workflow —
a discovery pass, a spec the developer confirms and then locks, a `docs/`
folder for everything after that, a scaffold, and a permanent development
loop — but with the stack decision already made: **NestJS, MongoDB via
Mongoose with real transactions, and an in-memory cache layer**, wired
together with the practices that make that combination safe (SOLID module
boundaries, ACID-correct multi-document writes, TDD via Jest, Swagger kept
current, ESLint + Husky).

Because the stack is fixed, Phase 1 is shorter than the general skill's —
don't re-litigate the framework/database choice, spend the discovery time
on the actual domain instead.

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
"describe the project's domain") for things that can't be reduced to
options.

## Phase 1 — Discovery

State the default stack up front so it's not a silent assumption:
**NestJS, MongoDB (Mongoose), an in-memory cache, Swagger/OpenAPI, ESLint +
Husky, Jest.** If the developer wants a different database, a shared/
distributed cache (Redis, etc.), or a different framework, this is the
wrong skill for them — point them to `backend-initializing-setup` instead
rather than trying to bend this one.

With the stack settled, ask about what actually varies per project:

- The domain: what the service does, its core entities, and any docs,
  design images, or reference APIs the developer can share.
- Auth model (session, JWT, OAuth, none) and any role/permission structure.
- Deployment target — this matters concretely here, because MongoDB
  transactions require a replica set. A managed service like Atlas already
  runs as a replica set; a bare local `mongod` does not. Confirm the
  target so Phase 5's local-dev setup is accurate, and flag this
  requirement now rather than as a surprise later.
- Whether the in-memory cache's limitation is acceptable for this project:
  it lives in a single Node process, so it's lost on restart and isn't
  shared across horizontally-scaled instances. If the project is expected
  to scale to multiple instances soon, say so now — it doesn't block using
  this skill's default, but it should be a decision the developer makes
  knowingly, not one they discover in production.
- Anything else load-bearing for the data model, auth, or API surface that
  hasn't been covered.

Don't move on while one of these is still unresolved.

## Phase 2 — Draft `spec.rp.md` and get explicit confirmation

Write `spec.rp.md` at the project root using
[references/spec-template.md](references/spec-template.md) — it has the
tech stack section pre-filled with the defaults above so discovery time
isn't spent restating them. Fill the rest from Phase 1.

Show the developer the result and get an explicit confirmation — a clear
yes, not silence or a vague "looks fine." Edit freely until they confirm;
the lock in Phase 3 only starts afterward.

## Phase 3 — Lock-in

Once confirmed, `spec.rp.md` is frozen. Say so explicitly: "This spec is
now locked; I won't change it unless you explicitly ask me to."

New ideas or things discovered mid-build go into `docs/decisions.md`, not
into the spec. If a real gap or contradiction surfaces later, ask the
developer whether to amend the spec (needs their explicit go-ahead) or
treat it as an implementation detail that doesn't touch it. The developer
saying "let's change X" later is itself the permission needed — make the
edit then, and note what changed and when.

## Phase 4 — Set up `docs/`

Create `docs/decisions.md`, `docs/prompts.md`, `docs/bugs.md`, and
`docs/notes.md` alongside the spec — see
[references/docs-folder.md](references/docs-folder.md) for what belongs in
each. `scripts/scaffold_docs.py --root <path>` creates this skeleton (and
an initial `spec.rp.md` from the template, only if one doesn't already
exist) in one step.

## Phase 5 — Scaffold the project

Full commands, file layout, and code patterns are in
[references/scaffold-guide.md](references/scaffold-guide.md) — read it
before scaffolding rather than improvising from memory, since the
transaction and cache wiring specifically are easy to get subtly wrong.
In short:

- `nest new` for the base project, then feature modules laid out as
  controller → service → repository, with services depending on a
  repository *interface* (Nest custom provider token), not directly on a
  Mongoose `Model` — that's what keeps the SOLID boundary real and makes
  services testable without a database.
- MongoDB wired through `@nestjs/mongoose`, with connection config through
  `@nestjs/config` and env validation so a missing/bad env var fails at
  boot, not at first request.
- A small transaction/unit-of-work helper around Mongoose sessions so
  every multi-document write goes through one path instead of every
  service hand-rolling `session.withTransaction`. See
  [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md)
  for the pattern and why a plain standalone `mongod` won't support it.
- The in-memory cache via `@nestjs/cache-manager`, used cache-aside
  (check cache → miss → read Mongo → populate cache with a TTL), with
  writes invalidating the relevant keys. Same reference file covers this.
- Swagger via `@nestjs/swagger`, wired in `main.ts` from the start, even
  with a near-empty API. See
  [references/swagger-openapi.md](references/swagger-openapi.md).
- ESLint (ships with `nest new`) plus Husky added for a pre-commit hook
  that runs lint and tests. See
  [references/tooling-and-testing.md](references/tooling-and-testing.md),
  which also covers the Jest/TDD setup, including testing transactional
  code without a real database via `mongodb-memory-server`.

## Phase 6 — The development loop (applies to every change, forever)

- **Test-first.** Write or update tests alongside the code change — a
  change without a test isn't done. For anything touching the
  transaction/unit-of-work helper or a repository, that includes a test
  proving the failure path actually rolls back.
- **Docs stay current.** Any change to a controller, service, or endpoint
  — however small — gets its Swagger annotation updated in the same step,
  never queued as follow-up.
- **Report minor bugs, don't bury them.** If something looks off while
  working on something else, say so explicitly and ask whether to fix it
  now or later, rather than silently patching or silently ignoring it.
- **Stay in scope.** Build what was asked — no extra endpoints, fields, or
  abstractions added speculatively. If the task seems to need something
  not specified, ask instead of assuming.
- **Ask instead of guessing** on small in-the-weeds ambiguities — a
  validation rule, a naming choice, whether a given write actually needs a
  transaction or is safely single-document.
- **Keep comments minimal** — a short header comment per file/unit is
  fine; comments narrating what the code below does are not.

## Reference files

- [references/spec-template.md](references/spec-template.md) — the
  `spec.rp.md` shape, with tech stack pre-filled
- [references/scaffold-guide.md](references/scaffold-guide.md) — concrete
  CLI commands, project layout, and SOLID layering for Nest + Mongoose
- [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md) —
  the transaction/unit-of-work pattern and the in-memory cache pattern,
  with code
- [references/tooling-and-testing.md](references/tooling-and-testing.md) —
  ESLint + Husky setup and the Jest/TDD loop, including testing
  transactions without a real database
- [references/swagger-openapi.md](references/swagger-openapi.md) — wiring
  `@nestjs/swagger` and keeping it current
- [references/docs-folder.md](references/docs-folder.md) — templates for
  `docs/decisions.md`, `docs/prompts.md`, `docs/bugs.md`, `docs/notes.md`
- `scripts/scaffold_docs.py` — one-shot script creating the `docs/`
  skeleton and an initial `spec.rp.md`
