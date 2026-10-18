# Keeping Swagger/OpenAPI current

Wire up OpenAPI generation during Phase 5, while the API surface is still
small — retrofitting documentation onto a large, undocumented API later is
far more work than keeping it current from the first endpoint.

## The rule that matters most

Any change to a controller, service, or endpoint — a new route, a renamed
field, a new optional query param, a changed status code — updates the
corresponding OpenAPI annotation **in the same step**, not as a follow-up.
An endpoint change without a doc update in the same diff is not finished.
This applies even to changes that feel minor; a stale doc that's "close
enough" is worse than an obviously-missing one because it's trusted.

## Setup per stack

- **Express** — `swagger-jsdoc` + `swagger-ui-express`. Write JSDoc-style
  OpenAPI comments directly above each route handler; generate the spec
  from those comments and serve it at a `/docs` route.
- **NestJS** — `@nestjs/swagger`. Decorate controllers and DTOs
  (`@ApiTags`, `@ApiOperation`, `@ApiProperty`, etc.) and call
  `SwaggerModule.setup(...)` in `main.ts`. Prefer this over hand-written
  JSDoc comments since Nest already has the decorator metadata to draw
  from.
- **Django** — `drf-spectacular` (or `drf-yasg`) generates the schema from
  DRF serializers/viewsets with minimal extra annotation.
- **Spring Boot** — `springdoc-openapi`, which generates the schema from
  existing controller/DTO annotations.
- **Anything else** — look for the ecosystem's standard OpenAPI generator
  before hand-writing a spec file; hand-written specs drift from the code
  fast because nothing forces them to stay in sync.

## Practical checklist for every endpoint change

- [ ] Request shape (path/query/body params) reflected in the schema
- [ ] Response shape(s), including error responses, reflected
- [ ] Auth requirement on the endpoint annotated (or explicitly marked public)
- [ ] Example values still make sense after the change
