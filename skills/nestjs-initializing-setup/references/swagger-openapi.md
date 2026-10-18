# Keeping Swagger current in NestJS

## Setup

```ts
// main.ts
const config = new DocumentBuilder()
  .setTitle('<project name>')
  .setVersion('1.0')
  .addBearerAuth() // if using JWT/bearer auth
  .build();
const document = SwaggerModule.createDocument(app, config);
SwaggerModule.setup('docs', app, document);
```

Wire this in during Phase 5, before the first real feature is added — a
near-empty API served at `/docs` is fine and keeps the habit of annotating
alive from the start.

## Annotating as you go

Nest generates most of the schema from decorators already on controllers
and DTOs, so there's little separate "documentation work" if the code is
annotated properly in the first place:

- `@ApiTags('resource-name')` on the controller
- `@ApiOperation({ summary: '...' })` and `@ApiResponse({ status, description, type })`
  on each handler, including error responses (400/401/403/404 as relevant)
- `@ApiProperty()` on every DTO field, since `class-validator` DTOs don't
  auto-document without it
- `@ApiBearerAuth()` (or the relevant auth decorator) on protected routes

## The rule that matters most

Any change to a controller, service, or endpoint — a new route, a renamed
field, a new optional query param, a changed status code — updates the
corresponding decorators in the **same** step, not as a follow-up. A
service-layer change that doesn't touch the controller/DTO shape doesn't
need a Swagger update; a controller or DTO change almost always does.
