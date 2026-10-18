# `spec.rp.md` template

Copy this structure when drafting the spec in Phase 2. Fill every section
from what discovery actually established — leave nothing implied. If a
section genuinely doesn't apply (e.g. no external integrations), say so
explicitly rather than deleting it, so it's clear it was considered.

The **Open Questions** section must be empty by the time the developer
confirms the spec — anything still listed there is a load-bearing unknown
that belongs back in Phase 1, not something to lock in half-answered.

```markdown
# Project Specification

> Status: DRAFT — awaiting developer confirmation
> Confirmed: <fill in date + how confirmed once approved, e.g. "2026-09-08, confirmed in chat">

## 1. Overview

One or two paragraphs: what this backend does and why it exists.

## 2. Goals

What this project must accomplish, as a short list.

## 3. Non-Goals

What is explicitly out of scope for this phase — just as important as the
goals, since it's what stops scope creep later.

## 4. Target Users / Clients

Who or what calls this API — end users via a specific frontend, another
internal service, a third party, etc.

## 5. Tech Stack

- Language / runtime:
- Framework:
- Database:
- Other key infra (cache, queue, storage, etc.):

If the developer had no preference and one was recommended, note that here
along with the reasoning.

## 6. Data Model

Core entities and their relationships. A short ER-style list is fine here;
full schema detail belongs in migrations, not the spec.

## 7. API Surface (high level)

The main resources/endpoints expected, grouped by resource. Full request/
response detail belongs in the OpenAPI/Swagger docs generated during
Phase 5+, not duplicated here.

## 8. Auth & Authorization

Who can do what. Auth method (session, JWT, OAuth, API key, none), and any
role/permission model.

## 9. Non-Functional Requirements

Anything about scale, latency, uptime, compliance, or team conventions that
should shape architectural decisions.

## 10. External Integrations

Third-party services or APIs this backend talks to, and what for.

## 11. Open Questions

Must be empty before confirmation. If something is still unresolved, go
back and resolve it — don't lock in a guess.
```
