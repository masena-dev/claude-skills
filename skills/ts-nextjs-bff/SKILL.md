---
name: ts-nextjs-bff
description: >-
  Next.js as a pure Backend-For-Frontend proxy. Triggers when setting up
  next.config.mjs rewrites, writing middleware for auth token injection,
  creating API route handlers, or deciding what logic belongs in Next.js
  vs the Go backend.
license: MIT
---

## The Rule

Next.js is a proxy, not a backend. All business logic lives in Go. Next.js handles exactly 5 concerns: auth cookie management, SSE streaming, server actions, infrastructure (health), and SSR data helpers.

## Rewrites Configuration (MANDATORY)

```javascript
// next.config.mjs
async rewrites() {
  return [
    {
      source: '/api/v1/:path*',
      destination: `${process.env.API_BASE_URL}/api/v1/:path*`
    },
    // Auth routes are handled by Next.js route handlers (not proxied)
    { source: '/api/auth/login', destination: '/api/auth/login' },
    { source: '/api/logout', destination: '/api/logout' },
  ];
}
```

## Middleware Token Injection (MANDATORY)

```typescript
// src/middleware.ts
if (request.nextUrl.pathname.startsWith('/api/v1')) {
  const token = request.cookies.get('session_token')?.value;
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
}
```

## Two API Client Pattern

```typescript
// Browser → Next.js proxy (client components)
export const clientApiClient = new Api({
  baseUrl: typeof window === 'undefined' ? '' : window.location.origin
});

// Server → Go backend directly (server components, SSR)
export const apiClient = new Api({
  baseUrl: process.env.API_BASE_URL,
  securityWorker: async (data) => ({
    headers: { Authorization: `Bearer ${data.token}` }
  })
});
```

## Allowed Route Handler Categories

| Category | Example | Why it's in Next.js |
|----------|---------|---------------------|
| Auth cookie management | `/api/auth/login` | httpOnly cookie must be set server-side |
| SSE streaming | `/api/sse` | Proxy with token injection + TransformStream |
| Server actions | `/api/actions/*` | Next.js form actions for progressive enhancement |
| Infrastructure | `/api/health` | Next.js-specific health check |
| SSR data helpers | Layout data fetching | Server component data loading |

## Anti-Patterns

- Business logic in route handlers (validation, DB queries, domain calculations)
- Direct database connections from Next.js
- Exposing JWT to browser JavaScript — must be httpOnly cookie only
- Using `getServerSideProps` or API routes for data the Go backend already serves
- Rewrites pointing to internal services — only proxy to the Go API gateway
