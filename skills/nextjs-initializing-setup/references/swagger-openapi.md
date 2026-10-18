# Keeping OpenAPI docs current in Next.js

Next.js has no framework-native OpenAPI generation the way Nest does, so
this relies on annotating Route Handlers with JSDoc comments and
generating the spec from those.

## Setup

```bash
npm install next-swagger-doc swagger-ui-react
```

```ts
// lib/swagger.ts
import { createSwaggerSpec } from 'next-swagger-doc';

export function getApiDocs() {
  return createSwaggerSpec({
    apiFolder: 'app/api',
    definition: {
      openapi: '3.0.0',
      info: { title: '<project name>', version: '1.0' },
    },
  });
}
```

```tsx
// app/api-docs/page.tsx
'use client';
import SwaggerUI from 'swagger-ui-react';
import 'swagger-ui-react/swagger-ui.css';
import { getApiDocs } from '@/lib/swagger';

export default function ApiDocsPage() {
  return <SwaggerUI spec={getApiDocs()} />;
}
```

Wire this in during Phase 5, before the first real route is added, so
annotating stays a habit from the start rather than a retrofit.

## Annotating a route handler

```ts
/**
 * @swagger
 * /api/products/{id}:
 *   get:
 *     tags: [Products]
 *     summary: Get a product by id
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema: { type: string }
 *     responses:
 *       200:
 *         description: The product
 *       404:
 *         description: Not found
 */
export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  // ...
}
```

## The rule that matters most

Any change to a route handler's request shape, response shape, or status
codes gets its JSDoc block updated in the **same** step, not queued as
follow-up. A change confined to `lib/services/` or `lib/repositories/`
that doesn't alter what the route accepts or returns doesn't need a docs
update; a route handler change almost always does.
