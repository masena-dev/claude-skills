---
name: go-check-masena-go-first
description: >-
  Check masena-go shared library before writing cross-cutting Go code.
  Triggers when implementing: password hashing, token generation, session expiry,
  tenant context, RLS transaction wrappers, NATS publishers/consumers, OTel trace
  propagation, SSE event streaming, or any infrastructure concern that might
  already exist in masena-go.
license: MIT
---

# Check masena-go First

Before writing any cross-cutting Go infrastructure, check whether `masena-go` already provides it. Reimplementing what the shared library offers creates drift across projects and doubles the maintenance surface.

## When to use

Use this skill when you are about to write any of the following:

- Password hashing or validation
- Session token generation, hashing, or verification
- Session expiry calculation or HTTP headers
- Tenant/user context injection or extraction
- RLS transaction wrappers (`SET LOCAL app.tenant_id`)
- NATS JetStream publishers, consumers, or stream management
- OpenTelemetry trace propagation over NATS
- Server-Sent Events (SSE) connection management
- Any utility that feels like "every project needs this"

## The rule

**Use masena-go or extend it. Never reimplement.**

```
Is this a cross-cutting concern?
├── YES → Does masena-go provide it? (see inventory below)
│   ├── YES → Import and use it. Do not wrap, copy, or rewrite.
│   ├── PARTIALLY → Extend masena-go with what's missing, then consume.
│   └── NO → Is it project-specific logic?
│       ├── YES → Implement in the project.
│       └── NO → Add it to masena-go first, then consume.
└── NO → Implement in the project.
```

## Why

Three projects (and growing) share the same infrastructure patterns. When one project fixes a bug or tightens a security check in its local copy, the others don't get the fix. masena-go exists to be the single source for these concerns. Reimplementing is not a shortcut — it's a maintenance liability.

## Quick inventory (masena-go v1.2.0)

| Package | You need | Use this |
|---------|----------|----------|
| `auth` | Hash a password | `auth.HashPassword(password)` |
| `auth` | Verify a password | `auth.VerifyPassword(password, hash)` |
| `auth` | Generate a session token | `auth.GenerateToken(ttl)` → `Token{Plaintext, Hash, Expiry}` |
| `auth` | Verify a token from a request | `auth.VerifyToken(plaintext, storedHash)` |
| `auth` | Calculate session expiry | `auth.CalculateExpiryNow(config, createdAt)` |
| `auth` | Set session headers on response | `expiry.SetSessionHeaders(w)` |
| `tenancy` | Store tenant ID in context | `tenancy.WithTenantID(ctx, id)` |
| `tenancy` | Read tenant ID from context | `tenancy.TenantIDFromContext(ctx)` or `tenancy.MustTenantID(ctx)` |
| `tenancy` | Run a write query with RLS | `tenancy.WithTenantTx(ctx, pool, tenantID, setCtx, fn)` |
| `tenancy` | Run a read query with RLS | `tenancy.WithReadTenantTx(ctx, pool, tenantID, setCtx, fn)` |
| `tenancy` | Run a query with user context (login flow) | `tenancy.WithUserTx(ctx, pool, userID, setCtx, fn)` |
| `nats` | Publish an event with tracing | `publisher.PublishWithContext(ctx, event)` |
| `nats` | Publish a batch atomically | `publisher.PublishBatch(ctx, events)` |
| `nats` | Consume events one at a time | `nats.NewEventConsumer[E](name, js, logger, handler)` |
| `nats` | Consume events in batches | `nats.NewBatchConsumer[E](name, js, logger, handler)` |
| `nats` | Manage consumer lifecycle | `nats.NewConsumerManager(logger)` → `.AddConsumers()` → `.Start()` / `.Stop()` |
| `nats` | Inject/extract OTel trace context | `nats.InjectTraceContext(ctx, msg)` / `nats.ExtractTraceContext(ctx, msg)` |
| `nats` | Name a span consistently | `nats.FormatOperationName("publish", "order.created")` |
| `nats` | Test event publishing | `nats.NewEventTester[E](js, logger)` → `.Events()` |
| `sse` | Manage SSE connections | `sse.NewSSEManager(logger, sse.WithOnSubscribe(cb))` |
| `sse` | Push an event to a client | `manager.Publish(ctx, sse.Event{ClientID: id, Type: sse.Notification, Data: payload})` |
| `sse` | Subscribe a client | `manager.Subscribe(w, clientID)` → `sub.EventChan()` |

For full function signatures, see [references/inventory.md](references/inventory.md).

## Example

End-to-end publisher + consumer setup using masena-go:

```go
// Define your event type
type OrderCreated struct {
    OrderID  string `json:"order_id"`
    TenantID string `json:"tenant_id"`
}

func (e OrderCreated) Subject() string { return "orders.created" }
func (e OrderCreated) Stream() string  { return "ORDERS" }

// Publish with trace propagation (in your service)
publisher, _ := nats.NewPublisher[OrderCreated](js, logger)
publisher.PublishWithContext(ctx, OrderCreated{OrderID: "abc", TenantID: tenantID})

// Consume in a worker (in main.go wiring)
consumer, _ := nats.NewEventConsumer("order-processor", js, logger, handler)
manager := nats.NewConsumerManager(logger)
manager.AddConsumers(consumer)
manager.Start(ctx)
defer manager.Stop()
```

## Anti-patterns

**Copying a function into your project instead of importing it.** Even if you "only need one function," import the package. Copies drift.

**Wrapping masena-go in a project-local abstraction.** If the masena-go API doesn't fit, fix the API upstream — don't paper over it with a wrapper that the next project won't have.

**Using `publisher.Publish(event)` instead of `PublishWithContext(ctx, event)`.** The context-free `Publish` method exists for backwards compatibility and loses trace propagation. Always use `PublishWithContext`.

**Writing your own `SET LOCAL app.tenant_id` logic.** Use `tenancy.WithTenantTx` and its variants. They handle begin/commit/rollback and context injection correctly.

**Hand-rolling SSE connection management.** `sse.SSEManager` handles concurrent connections, graceful shutdown, client ID validation, and event fan-out. Your hand-rolled version will miss at least one of these.

## Planned additions (masena-go roadmap)

These packages are coming. If you need one of these before it ships, build it in masena-go — not in your project.

| Version | Package | What it provides |
|---------|---------|-----------------|
| v1.3.0 | `csv` | BOM strip, delimiter auto-detect, typed row errors |
| v1.4.0 | `logging` | slog wrapper with OTel ContextHandler (trace_id/span_id injection) |
| v1.5.0 | `db` | `ConfigurePoolForRLS` (AfterRelease + PrivilegeError) |
| v1.6.0 | `tenancy` | `WithTenantTxValue[T]`, `AuditContext`, `WithSubTxValue` |
| v1.7.0 | `testutil`, `otel`, `server` | Testcontainers helpers, OTel init, GracefulRunner |

## References

- [Full API inventory](references/inventory.md) — every exported type, function, and constant
- masena-go source: `github.com/masena-dev/masena-go`

## Updating this skill

When masena-go ships new packages or changes existing signatures, this inventory must be regenerated. For v0.1.0 this is manual — update `references/inventory.md` and bump the version in the skill body. A CI workflow to auto-regen from masena-go release tags is planned for a later version of claude-skills.
