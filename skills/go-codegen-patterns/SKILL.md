---
name: go-codegen-patterns
description: >-
  Go code generation workflow with oapi-codegen, sqlc, and protobuf.
  Triggers when writing SQL queries, defining API types, adding endpoints,
  modifying openapi.yaml, configuring sqlc, or creating handler structs.
  Enforces spec-first development: edit the spec, regenerate, then implement.
license: MIT
---

# Go Codegen Patterns

All types are generated. Spec changes drive code — never the reverse.

## When to use

- Adding or modifying an API endpoint
- Writing a new SQL query
- Defining request/response structs
- Changing `openapi.yaml`, `sqlc.yaml`, or proto files
- Wiring a new handler to the router

## The rule

**Edit the spec, regenerate, then implement. Never hand-write types that a generator produces.**

Three type systems coexist — use the right one for each layer:

| Layer | Generator | Source of truth | Output |
|-------|-----------|----------------|--------|
| HTTP | oapi-codegen | `openapi.yaml` | `internal/apitypes/types.gen.go` + `internal/api/api.gen.go` |
| Database | sqlc | `.sql` files in `internal/db/queries/` | `internal/db/*.sql.go` |
| Events | protobuf (buf) | `.proto` files | `gen/` directory |

## Spec-first workflow

```
1. Edit openapi.yaml (add endpoint, modify schema)
2. make generate-api       → regenerates Go types + server interface
3. make generate-db        → regenerates sqlc query methods (if schema changed)
4. make generate-web       → regenerates frontend API client (orval)
5. Implement the handler   → compiler tells you what's missing
6. go build ./...          → verify everything compiles
```

## oapi-codegen two-config split

Types and server interface are generated separately into different packages:

**`internal/apitypes/types-codegen.yaml`** — models only:
```yaml
package: apitypes
generate:
  models: true
output-options:
  skip-prune: true
```

**`internal/api/api-codegen.yaml`** — server interface + embedded spec:
```yaml
package: api
generate:
  std-http-server: true
  embedded-spec: true
additional-imports:
  - alias: .
    package: github.com/your-org/your-project/internal/apitypes
compatibility:
  always-prefix-enum-values: true
```

The `.` alias import lets the `api` package reference generated types without the `apitypes.` prefix, keeping handler code clean.

### Compile-time contract

Every handler file must include this assertion:

```go
var _ ServerInterface = (*Server)(nil)
```

This fails at compile time when `openapi.yaml` adds a new endpoint you haven't implemented yet. No runtime surprises.

## sqlc configuration

```yaml
version: "2"
sql:
  - engine: "postgresql"
    queries: "./queries"
    schema: "./migrations"
    gen:
      go:
        package: "db"
        out: "./"
        sql_package: "pgx/v5"
        emit_methods_with_db_argument: true
        emit_json_tags: true
        emit_enum_valid_method: true
        emit_all_enum_values: true
```

**Non-negotiable flags:**
- `emit_methods_with_db_argument: true` — query methods accept `DBTX` (pool or transaction), enabling RLS wrappers
- `emit_enum_valid_method: true` — generates `Valid()` method on enums for input validation
- `emit_all_enum_values: true` — generates `Values()` returning all enum constants

## Example

Adding a new endpoint end-to-end:

```go
// 1. After editing openapi.yaml and running make generate-api,
//    the compiler enforces the new method via ServerInterface.

// 2. Use generated types — never hand-define request/response structs
func (s *Server) ListOrders(w http.ResponseWriter, r *http.Request, params ListOrdersParams) {
    tenantID, ok := s.requireTenantContext(w, r)
    if !ok {
        return
    }

    // 3. Use sqlc-generated query methods with DBTX argument
    orders, err := s.services.Orders.List(r.Context(), tenantID, db.ListOrdersParams{
        Limit:  params.Limit,
        Cursor: params.Cursor,
    })
    if err != nil {
        s.serverError(w, r, err)
        return
    }

    s.writeJSON(w, http.StatusOK, orders)
}
```

## Anti-patterns

**Hand-writing a struct that oapi-codegen already generates.** If you need `CreateOrderRequest`, it comes from `openapi.yaml` → `apitypes.CreateOrderRequest`. Defining it manually means it drifts from the spec.

**Writing raw SQL strings in Go code instead of sqlc queries.** Every query goes in `internal/db/queries/*.sql` with a `-- name:` annotation. sqlc generates the type-safe Go method.

**Implementing first, then updating the spec.** The spec is the contract. If you write code first, the spec becomes documentation — not a source of truth. Always spec → generate → implement.

**Skipping `emit_methods_with_db_argument`.** Without this flag, sqlc generates methods on a `Queries` struct bound to a single connection. You lose the ability to pass tenant-scoped transactions from RLS wrappers.

**Using `chi-server` in new projects.** The canonical config uses `std-http-server: true` (standard library HTTP handlers). Chi routing is configured separately. This keeps generated code free of router dependencies.

## References

- [go-check-masena-go-first](../go-check-masena-go-first/SKILL.md) — check shared library before writing infrastructure
- [sqlc documentation](https://docs.sqlc.dev) — query annotation syntax
- [oapi-codegen docs](https://github.com/oapi-codegen/oapi-codegen) — config file reference

## Updating this skill

When codegen tooling versions change or new generators are adopted, update the config examples and workflow steps. The two-config split and compile-time assertion patterns are stable — update only if the tool's config schema changes.
