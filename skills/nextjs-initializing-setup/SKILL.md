---
name: nextjs-initializing-setup
description: Guided workflow for starting a brand-new backend/API built with Next.js from scratch, preset to a specific default stack — Next.js App Router Route Handlers as the API layer, MongoDB (Mongoose) with real multi-document ACID transactions, an in-memory cache layer, Swagger/OpenAPI docs, ESLint + Husky, and TDD via Jest. Same discovery → locked-spec (spec.rp.md) → docs/ → scaffold → enforced-dev-loop workflow as the general backend-initializing-setup skill, but skips the stack question since it's fixed. Use this whenever a developer wants to "set up a Next.js backend/API", "scaffold a Next.js project as a backend", "use Next.js route handlers for an API", or asks for a backend with this Next+Mongo combination specifically. Not for a Next.js project that's purely a frontend with no API layer of its own — for a different database, cache, or framework, point them to backend-initializing-setup instead.
user-invocable: true
---

# Next.js Initializing Setup

Next.js is a frontend framework that also happens to run a real backend
through App Router Route Handlers — which is exactly the mode this skill
targets. It follows the same discipline as the general backend-scaffolding
workflow — discovery, a spec the developer confirms and then locks, a
`docs/` folder, a scaffold, and a permanent development loop — with the
stack already decided: **Next.js (App Router) as the API layer, MongoDB
via Mongoose with real transactions, and an in-memory cache**, plus the
practices that make that combination safe without Nest's dependency
injection to lean on (manual SOLID layering, ACID-correct writes, TDD via
Jest, Swagger kept current, ESLint + Husky).

Because the stack is fixed, Phase 1 is shorter than the general skill's —
spend the discovery time on the domain, not the framework choice.

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

State the default stack up front: **Next.js App Router with Route
Handlers as the API, MongoDB (Mongoose), an in-memory cache, Swagger/
OpenAPI docs, ESLint + Husky, Jest.** If the developer wants the older
Pages Router API routes instead, a different database, a shared/
distributed cache (Redis, etc.), or wants Next.js purely as a frontend
with the backend living elsewhere, this is the wrong skill — the Pages
Router case can still work here with a quick confirmation, but a different
database/cache/framework belongs in `backend-initializing-setup` instead.

With the stack settled, ask about what actually varies per project:

- The domain: what the service does, its core entities, and any docs,
  design images, or reference APIs the developer can share.
- Auth model (session, JWT, OAuth, none) and any role/permission structure.
- Deployment target — this matters concretely twice over here. First,
  MongoDB transactions require a replica set (a managed service like Atlas
  already is one; a bare local `mongod` is not). Second, if the target is
  a serverless platform (e.g. Vercel), the in-memory cache and the
  database connection both need the serverless-aware handling covered in
  Phase 5 — confirm the target now so that setup is accurate.
- Whether the in-memory cache's limitation is acceptable: it lives in a
  single server process, so on a serverless platform where each invocation
  may run in a fresh instance, it can behave more like "occasionally
  helpful" than "reliable" — worth surfacing as a real tradeoff rather
  than a hidden surprise, not a reason to silently swap in something else.
- Anything else load-bearing for the data model, auth, or API surface.

Don't move on while one of these is still unresolved.

## Phase 2 — Draft `spec.rp.md` and get explicit confirmation

Write `spec.rp.md` at the project root using
[references/spec-template.md](references/spec-template.md), which has the
tech stack section pre-filled. Fill the rest from Phase 1, show it to the
developer, and get an explicit confirmation — a clear yes, not silence.
Edit freely until then; the lock in Phase 3 only starts afterward.

## Phase 3 — Lock-in

Once confirmed, `spec.rp.md` is frozen: "This spec is now locked; I won't
change it unless you explicitly ask me to."

New ideas or things discovered mid-build go into `docs/decisions.md`, not
into the spec. A real gap or contradiction found later gets asked about —
amend the spec (with explicit go-ahead) or handle it as an implementation
detail that doesn't touch it. "Let's change X" from the developer later is
itself the permission — make the edit then, noting what changed and when.

## Phase 4 — Set up `docs/`

Create `docs/decisions.md`, `docs/prompts.md`, `docs/bugs.md`, and
`docs/notes.md` alongside the spec — see
[references/docs-folder.md](references/docs-folder.md). `scripts/scaffold_docs.py --root <path>`
creates this skeleton (and an initial `spec.rp.md`, only if one doesn't
already exist) in one step.

## Phase 5 — Scaffold the project

Full commands, file layout, and code patterns are in
[references/scaffold-guide.md](references/scaffold-guide.md) — read it
before scaffolding, since Next.js has no DI container, so the SOLID
layering, the database connection, and the transaction/cache wiring all
need to be done by hand rather than leaning on a framework convention. In
short:

- `create-next-app` for the base project (TypeScript, App Router, ESLint).
- API surface as Route Handlers (`app/api/<resource>/route.ts`) that stay
  thin: parse and validate the request, call a service function, shape the
  response. Business logic lives in `lib/services/`, data access in
  `lib/repositories/` — the same controller/service/repository separation
  as any SOLID backend, just plain modules instead of decorators, with
  repositories passed into services as an argument (or a small composition
  root) rather than imported directly, so services stay testable.
- A cached, serverless-safe MongoDB connection helper — this is the one
  Next.js-specific gotcha that isn't optional, since the naive
  `mongoose.connect()` call reconnects on every invocation/hot-reload and
  exhausts connections in production.
- The same transaction/unit-of-work helper pattern as any Mongoose-backed
  service, adapted to a plain function instead of an injectable — see
  [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md).
- The in-memory cache, implemented as a small TTL-aware singleton module
  (not a framework feature) — same reference file, including the
  serverless caveat spelled out concretely.
- Swagger/OpenAPI via `next-swagger-doc` generating a spec from JSDoc on
  the route handlers, served at a docs route. See
  [references/swagger-openapi.md](references/swagger-openapi.md).
- ESLint (ships with `create-next-app`) plus Husky for a pre-commit hook.
  See [references/tooling-and-testing.md](references/tooling-and-testing.md),
  which also covers testing Route Handlers directly and the transaction
  test setup.

## Phase 6 — The development loop (applies to every change, forever)

- **Test-first.** Write or update tests alongside the code change — a
  change without a test isn't done. Anything touching the unit-of-work
  helper or a repository needs a test proving the rollback path actually
  works, not just the happy path.
- **Docs stay current.** Any change to a route handler, service, or
  endpoint shape — however small — gets its JSDoc/OpenAPI annotation
  updated in the same step, never queued as follow-up.
- **Report minor bugs, don't bury them.** If something looks off while
  working on something else, say so explicitly and ask whether to fix it
  now or later, rather than silently patching or silently ignoring it.
- **Stay in scope.** Build what was asked — no extra routes, fields, or
  abstractions added speculatively. If the task seems to need something
  unspecified, ask instead of assuming.
- **Ask instead of guessing** on small in-the-weeds ambiguities — whether
  a given write actually needs a transaction, a validation rule, a naming
  choice.
- **Keep comments minimal** — a short header comment per file/unit is
  fine; comments narrating what the code below does are not.

## Reference files

- [references/spec-template.md](references/spec-template.md) — the
  `spec.rp.md` shape, with tech stack pre-filled
- [references/scaffold-guide.md](references/scaffold-guide.md) — concrete
  CLI commands, project layout, and SOLID layering without a DI container
- [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md) —
  the transaction/unit-of-work pattern, the serverless-safe connection
  helper, and the in-memory cache pattern, with code
- [references/tooling-and-testing.md](references/tooling-and-testing.md) —
  ESLint + Husky setup and the Jest/TDD loop, including testing Route
  Handlers directly and transactions without a real database
- [references/swagger-openapi.md](references/swagger-openapi.md) — wiring
  `next-swagger-doc` and keeping it current
- [references/docs-folder.md](references/docs-folder.md) — templates for
  `docs/decisions.md`, `docs/prompts.md`, `docs/bugs.md`, `docs/notes.md`
- `scripts/scaffold_docs.py` — one-shot script creating the `docs/`
  skeleton and an initial `spec.rp.md`
