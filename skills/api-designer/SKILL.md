---
name: api-designer
description: >-
  OpenAPI 3.0 API design — endpoint creation, schema composition, oapi-codegen
  extensions, and API review. Use when adding or modifying endpoints in
  openapi.yaml, designing new API resources, reviewing API specs for
  consistency, or setting up public/private endpoint separation. Also use when
  asking about naming conventions, pagination, error handling, security scopes,
  schema reuse, or when generated Go code doesn't match expectations.
allowed-tools: Read, Glob, Grep, Write, Edit, Bash
---

# OpenAPI Design

API-first design conventions for Go projects using OpenAPI 3.0 with oapi-codegen for code generation.

## When to Use

- Adding or modifying endpoints in `openapi.yaml`
- Designing new API resources or schemas
- Reviewing API specs for consistency and convention adherence
- Setting up public/private endpoint separation
- Generated Go code doesn't match expectations (wrong types, missing fields, pointer issues)

## Before You Start

Read the project's existing `openapi.yaml` and `AGENTS.md` to understand current conventions. Use `ctx7` (`npx ctx7@latest`) for OpenAPI or oapi-codegen docs if unsure about a feature or extension.

## Endpoint Design Checklist

1. Define path following [path conventions](#path-conventions)
2. Define or compose schemas from existing base schemas — check `components/schemas` first
3. Add security scopes (`resource:action` or `resource:action:qualifier`)
4. Add cursor pagination if list endpoint
5. Add standard error responses via `$ref` (400, 401, 403, 404, 409, 500)
6. Add oapi-codegen extensions as needed (see [references/extensions.md](references/extensions.md))
7. Mark `x-public: true` if the endpoint should be externally visible
8. Verify response wrapping matches convention
9. Regenerate: `make generate-api` from the backend directory
10. Verify generated types in `apitypes/types.gen.go` match expectations

## Path Conventions

Pattern: `/api/v1/<domain>[/<subresource>][/{identifier}][/<action>]`

- **Kebab-case** path segments: `/team-members`, `/link-metadata`, `/audit-logs`
- **Snake_case** path parameters: `{post_slug}`, `{context_id}`, `{report_id}`
- **Action sub-paths** for state transitions: `/{id}/approve`, `/{id}/submit`, `/{id}/join`
- **Admin prefix**: `/api/v1/admin/...`
- **Current user**: `/api/v1/me/...` for user-scoped resources

```
/api/v1/posts                           # collection
/api/v1/posts/{post_slug}               # single resource
/api/v1/posts/{post_slug}/comments      # nested collection
/api/v1/posts/{post_slug}/vote          # action
/api/v1/admin/users/{username}/ban      # admin action
/api/v1/me/posts                        # current user's resources
```

Path parameters are always `required: true`. Use `string` for slugs/usernames, `integer` with `format: int64` for numeric IDs.

## Schema Composition Strategy

Every entity that appears in multiple response contexts must have a base schema. Extend via `allOf` — never duplicate fields across schemas. This is the most important convention for keeping APIs uniform.

### When to Create a Base Schema

- The entity appears in 2+ responses with different field sets
- Different endpoints need different "views" of the same entity (list vs detail, user-facing vs admin)

### What Goes in the Base

- Identity fields (slug, id, username, title)
- Core data fields that every view needs
- Fields that would cause bugs if inconsistently defined across views

### What Goes in Extensions

- Relationship fields (`is_following`, `joined_at`)
- Computed/contextual fields (`vote_count`, `user_vote`)
- Admin-only fields (`internal_status`, `review_flags`)
- View-specific fields (`reading_time_mins` for detail, not summary)

### Naming Hierarchy

```
Base<Entity>                          Core identity + universal fields
  └── <Entity>WithContext             + viewer-relative fields (is_following)
        ├── <Entity><SpecificView>    + context-specific fields (TeamMember + joined_at)
        └── Admin<Entity>             + admin-only fields
  └── <Entity>Summary                 + list-view subset (compose from base, don't duplicate)
```

Example:

```yaml
BaseUser:                             # username, names, pic, role, bio
  allOf children:
    UserWithContext:                   # + is_following
      allOf children:
        TeamMember:                   # + joined_at
        TeamRoleHolder:               # + team_role, joined_at
        AdminUser:                    # + admin-specific fields
```

### The Anti-Pattern

Never create independent schemas with overlapping fields:

```yaml
# BAD — fields duplicated, will drift
Post:
  properties: { slug: ..., title: ..., author: ..., created_at: ... }

PostSummary:
  properties: { slug: ..., title: ..., author: ..., created_at: ... }
```

```yaml
# GOOD — compose from base
BasePost:
  required: [slug, title, author, created_at]
  properties:
    slug: { type: string }
    title: { type: string }
    author: { $ref: "#/components/schemas/UserWithContext" }
    created_at: { type: string, format: date-time }

Post:
  allOf:
    - $ref: "#/components/schemas/BasePost"
    - type: object
      properties:
        is_graphic: { type: boolean }
        reading_time_mins: { type: integer }

PostSummary:
  allOf:
    - $ref: "#/components/schemas/BasePost"
    - type: object
      properties:
        thumbnail_url: { type: string, format: uri }
```

## $ref Reuse Rules

- Define schemas, parameters, responses, and enums in `components/` — `$ref` everywhere
- Never inline a schema that appears in more than one place
- Never duplicate an enum — define once as a named schema, `$ref` it
- Standard error responses (400–500) are shared components in `components/responses` — `$ref`, don't redefine
- The `Paging` schema is a shared component — always compose list responses via `allOf` with it

## Schema Naming and Properties

- **PascalCase** schema names: `BaseUser`, `PostSummary`, `CreatePostRequest`, `GetSpacePostsResponse`
- **Snake_case** properties: `first_name`, `created_at`, `has_next_page`, `is_platform_content`
- **Schema reuse with `readOnly`** vs separate request/response schemas: pick per the project's existing convention and what its generators support. See [Request/Response Schema Reuse](#requestresponse-schema-reuse) below.
- **IDs**: `string` for slugs/usernames, `integer` with `format: int64` for numeric IDs
- **Timestamps**: `type: string, format: date-time`
- **Dates**: `type: string, format: date`
- **Enums**: standalone named schemas with lowercase or SCREAMING_SNAKE_CASE values
- **Polymorphism**: `oneOf` with `discriminator` and explicit `mapping`

## Request/Response Schema Reuse

**First, match the project.** Check the existing `openapi.yaml`: if it already standardises on separate `Create<Entity>Request` / response schemas, follow that — consistency within a spec beats either pattern in the abstract. For greenfield resources where you're setting the convention, the reuse pattern below is a strong default *where the toolchain supports it* (see [Generator Configuration](#generator-configuration)).

**The reuse pattern**: one schema for both request and response, marking server-populated fields with `readOnly: true`.

**Why it's attractive**: lower drift risk — one source of truth instead of two schemas whose shared fields can silently diverge. **The catch**: the request/response distinction lives entirely in `readOnly` markers, and only some generators enforce it on the wire. Where the generator doesn't, the constraint is server-side only (see below).

### Pattern

```yaml
Schedule:
  type: object
  required: [id, name, date, version]
  properties:
    id:
      type: string
      format: uuid
      readOnly: true
    name:
      type: string
    date:
      type: string
      format: date
    version:
      type: integer
      readOnly: true
    created_at:
      type: string
      format: date-time
      readOnly: true
    updated_at:
      type: string
      format: date-time
      readOnly: true
```

Use the same `Schedule` schema as the body of `POST /schedules`, the body of `PATCH /schedules/{id}`, and the response of `GET /schedules/{id}`.

### How Creation Works (server-generated id)

Per OpenAPI 3.0: a property marked `readOnly: true` SHOULD NOT be sent in a request. If it appears in the `required` list, the `required` constraint applies **to the response only** — not to requests.

So with the schema above, `POST /schedules` accepts:

```json
{ "name": "Morning plan", "date": "2026-06-01" }
```

The server generates `id`, `version`, `created_at`, `updated_at` and returns the full resource:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Morning plan",
  "date": "2026-06-01",
  "version": 1,
  "created_at": "2026-06-01T08:00:00Z",
  "updated_at": "2026-06-01T08:00:00Z"
}
```

Validators (`kin-openapi`) honor the readOnly+required pairing per spec. Orval strips readOnly fields from generated TS request types so the client can't send them.

### Generator Configuration

**Orval (TypeScript)**: set `preserveReadonlyRequestBodies: 'strip'` (the default). Generated request types omit `readOnly` fields automatically; response types include them.

```typescript
// orval.config.ts
export default defineConfig({
  api: {
    output: {
      override: {
        preserveReadonlyRequestBodies: 'strip',  // default — stays explicit for clarity
      },
    },
  },
});
```

**swagger-typescript-api (TypeScript)**: does NOT strip `readOnly` fields from generated request types — they land in both request and response interfaces. So the "client can't send `readOnly` fields" guarantee does **not** hold under this generator. Treat schema reuse as a codegen/documentation convenience and enforce the constraint server-side (ignore `readOnly` fields on input). If you need the wire-level guarantee, use Orval or define separate request schemas.

**oapi-codegen (Go)**: does NOT differentiate by `readOnly`. Generates one Go struct used for both request and response, with `readOnly` fields as `*Type` with `omitempty`. The handler is responsible for ignoring `readOnly` fields on inputs (validation pass or simply not reading them in create/update logic). This is a small discipline cost, not a generated-code disaster.

### When Separate Schemas Are Still Right

- The input shape differs meaningfully from the output shape (different required fields, different validation rules, different field shapes — not just "server adds an id")
- The input is genuinely a different concept (e.g., `BulkImportRequest` carries a CSV blob; the resulting `Schedule` is a different shape entirely)
- One side has fields the other cannot meaningfully represent

In these cases, define separate schemas explicitly. Do not allOf-compose them — they are different concepts, not views of the same entity.

## Response Wrapping

**Whether to wrap is a project convention — match the existing spec.** Some projects wrap every response in an envelope (`{ message, <resource> }`); others return the resource or list directly and reserve a top-level `message` for errors only. Neither is more correct; pick whatever the host `openapi.yaml` already does and stay consistent. The examples below show the envelope style — drop the `message` field and wrapper object if the project returns bare resources.

Single resource (envelope style):
```yaml
GetPostResponse:
  required: [message, post]
  properties:
    message: { type: string }
    post: { $ref: "#/components/schemas/Post" }
```

List with pagination:
```yaml
ListPostsResponse:
  allOf:
    - $ref: "#/components/schemas/Paging"
    - type: object
      required: [posts]
      properties:
        posts:
          type: array
          items: { $ref: "#/components/schemas/PostSummary" }
```

- **Create (POST)**: 201 with wrapped resource
- **Mutation/action**: 204 no body

## Cursor Pagination

Query parameters:
```yaml
parameters:
  - name: cursor
    in: query
    allowEmptyValue: true
    schema: { type: string }
  - name: limit
    in: query
    schema: { type: integer }
```

Response schema (compose via `allOf`):
```yaml
Paging:
  type: object
  required: [cursor, has_next_page, limit]
  properties:
    cursor: { type: string }
    has_next_page: { type: boolean }
    limit: { type: integer }
```

The cursor is opaque to clients — base64-encoded composite (typically `created_at, id`).

## Error Format

```yaml
Error:
  type: object
  required: [message, code]
  properties:
    message: { type: string }
    code: { $ref: "#/components/schemas/ErrorCode" }

BadRequestError:
  allOf:
    - $ref: "#/components/schemas/Error"
    - type: object
      properties:
        fields:
          type: array
          items: { $ref: "#/components/schemas/ErrorField" }

ErrorField:
  required: [field, message]
  properties:
    field: { type: string }     # nested fields joined with '.'
    message: { type: string }
```

Standard response refs in `components/responses`: `BadRequestError` (400), `UnauthorizedError` (401), `ForbiddenError` (403), `NotFound` (404), `ConflictError` (409), `TooManyRequestsError` (429), `InternalServerError` (500).

`ErrorCode` enum uses SCREAMING_SNAKE_CASE values (`POST_NOT_FOUND`, `RATE_LIMIT_EXCEEDED`) with `x-enumNames` to map to PascalCase Go constants.

## Security

Two schemes — both required:
```yaml
securitySchemes:
  ApiKeyAuth:
    type: apiKey
    in: header
    name: X-API-KEY
  BearerAuth:
    type: http
    scheme: bearer
```

**Global**: `ApiKeyAuth` on every endpoint.

**Authenticated endpoint** with scopes:
```yaml
security:
  - BearerAuth: ["posts:create"]
    ApiKeyAuth: []
```

**Multiple permission levels** (owner OR admin):
```yaml
security:
  - BearerAuth: ["posts:delete:own"]
    ApiKeyAuth: []
  - BearerAuth: ["posts:delete:any"]
    ApiKeyAuth: []
```

**Public with optional auth** (anonymous access, richer data if logged in):
```yaml
security:
  - BearerAuth: []
    ApiKeyAuth: []
  - ApiKeyAuth: []
```

**Scope format**: `resource:action` or `resource:action:qualifier`.

**Scope naming rules**:
- **Resource**: single word, plural noun — `posts`, `comments`, `users`, `spaces`, `reports`, `quality`. Never underscored (`moderation_rule` is wrong — use `moderation` or restructure)
- **Action**: single word, verb — `create`, `update`, `delete`, `view`, `review`, `ban`, `unban`
- **Qualifier**: optional, describes the access level — `own`, `any`, `temporary`, `permanent`, `all`, `deleted`
- Examples: `posts:create`, `posts:update:own`, `users:ban:temporary`, `admin:access`, `quality:override`

Scopes are defined as a named `Scope` enum in `components/schemas`. When adding a new endpoint that requires a new scope, add it to this enum — it generates into both the Go backend and the TypeScript frontend client. Keep the enum alphabetically ordered by resource to make it scannable.

```yaml
Scope:
  type: string
  enum:
    - "admin:access"
    - "comments:create"
    - "comments:delete:own"
    - "comments:delete:any"
    - "posts:create"
    - "posts:update:own"
    - "posts:update:any"
    # ... add new scopes in alphabetical order by resource
```

**Two-layer auth model**: API key identifies the *application* (web, mobile, partner integration). Bearer token identifies the *user*. Both are always required — mobile apps get their own API key, not a bypass.

**Mobile auth**: JWT access/refresh token flow. Login and refresh endpoints require `ApiKeyAuth` only (no bearer — you don't have a token yet). All other mobile endpoints use `BearerAuth` + `ApiKeyAuth` like web. See [references/patterns.md](references/patterns.md) for the endpoint pattern.

**Public/private boundary**: Mark externally visible operations with `x-public: true`. See [references/public-boundary.md](references/public-boundary.md).

## oapi-codegen Extensions

Quick reference — see [references/extensions.md](references/extensions.md) for decision guidance.

| Extension | Effect |
|-----------|--------|
| `x-go-type` | Override generated Go type (`json.RawMessage`, `decimal.Decimal`, `int64`, `float64`) |
| `x-go-type-import` | Import path for custom `x-go-type` |
| `x-go-type-skip-optional-pointer` | Optional field as value type, not `*T` |
| `x-omitempty: false` | Always serialize field, even as null |
| `x-order` | Struct field ordering in generated code |
| `x-enumNames` | Override Go constant names (must stay position-synced with enum values) |
| `allowEmptyValue: true` | Allow empty string as valid param value |

## oapi-codegen Setup

Standard two-pass generation:
- **Types** (`apitypes` package): `generate: { models: true }` — pure type definitions
- **Server** (`api` package): `generate: { chi-server: true, embedded-spec: true }` with `always-prefix-enum-values: true`
- The `api` package dot-imports `apitypes` via `additional-imports` with `alias: .`
- Hand-written handler code uses qualified `apitypes.Xxx` — dot import is generated code only

Regenerate after spec changes:
```bash
cd backend && make generate-api
```

## References

| Reference | Load When |
|-----------|-----------|
| [extensions.md](references/extensions.md) | Choosing which oapi-codegen extensions to use for a field or param |
| [patterns.md](references/patterns.md) | Need a copy-paste spec snippet for a specific endpoint type |
| [public-boundary.md](references/public-boundary.md) | Setting up or working with public/private endpoint separation |
