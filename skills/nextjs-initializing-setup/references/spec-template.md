# `spec.rp.md` template (Next.js + MongoDB preset)

Same shape and confirmation rule as any other project spec: draft it, get
an explicit confirmation, then it's frozen (Phase 3 of SKILL.md). The tech
stack section is pre-filled since this skill's whole point is that the
stack is already decided — don't turn that section into an open question.

The **Open Questions** section must be empty before confirmation. If
something's still unresolved, that belongs back in Phase 1, not locked in
as a guess.

```markdown
# Project Specification

> Status: DRAFT — awaiting developer confirmation
> Confirmed: <fill in date + how confirmed once approved>

## 1. Overview

One or two paragraphs: what this backend does and why it exists.

## 2. Goals

## 3. Non-Goals

## 4. Target Users / Clients

## 5. Tech Stack

- Language / runtime: TypeScript / Node.js
- Framework: Next.js (App Router), API surface via Route Handlers
- Database: MongoDB (Mongoose), multi-document writes use real transactions
  (requires a replica set — see deployment note below)
- Cache: in-memory (module-level TTL cache), single-process — see the
  serverless caveat noted under Non-Functional Requirements
- API docs: Swagger/OpenAPI via `next-swagger-doc`
- Deployment target: <fill in — must support a MongoDB replica set for
  transactions; note whether it's serverless (e.g. Vercel) or a
  long-running Node process, since that changes how much the in-memory
  cache can be relied on>

## 6. Data Model

Core entities/collections and their relationships. Note which write
operations span more than one collection/document — those need the
transaction helper in Phase 5.

## 7. API Surface (high level)

The main resources/routes, grouped by resource. Full request/response
detail lives in the generated OpenAPI docs, not duplicated here.

## 8. Auth & Authorization

Auth method and any role/permission model.

## 9. Non-Functional Requirements

Scale, latency, uptime, compliance, or team conventions — including
whether the in-memory cache's single-instance (and, if serverless,
per-invocation) limitation is acceptable for this project.

## 10. External Integrations

Third-party services this backend talks to, and what for.

## 11. Open Questions

Must be empty before confirmation.
```
