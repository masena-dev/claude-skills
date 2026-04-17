---
name: go-event-patterns
description: >-
  Event-driven patterns with NATS JetStream, notification pipelines, and SSE.
  Triggers when writing NATS consumers/publishers, building notification systems,
  implementing SSE endpoints, or designing event-driven workflows.
  Enforces determine-vs-send split and SSE-as-invalidation-hint patterns.
license: MIT
---

# Go Event Patterns

Never send notifications directly from domain event handlers. Domain handlers determine and persist; processors claim, batch, and deliver.

## When to use

- Writing a NATS JetStream consumer or publisher
- Building a notification system (in-app, email, or both)
- Implementing an SSE endpoint
- Designing an event-driven workflow with multi-step processing
- Adding a new notification type to an existing pipeline

## The rule

**Determine in the handler. Persist a row. Process asynchronously.**

Domain handlers write a `notification_events` row with per-channel statuses. A separate scheduled processor claims rows, batches, delivers, and updates status. SSE consumers receive an event and publish a cache invalidation hint — not the notification data itself.

## Determine vs send

```go
// WRONG: Sending directly from domain handler
func (h *OrderHandler) HandleEvent(ctx context.Context, evt OrderCreated) error {
    sendEmail(evt.CustomerEmail, "Order confirmed")  // NO!
    sseManager.Publish(ctx, notification)              // NO!
    return nil
}

// RIGHT: Handler writes a pending notification_events row
func (h *OrderHandler) HandleEvent(ctx context.Context, evt OrderCreated) error {
    channels := h.determineChannels(ctx, evt.UserID)
    return h.db.CreateNotificationEvent(ctx, CreateNotificationEventParams{
        UserID:      evt.UserID,
        EventType:   "order_created",
        EntityID:    evt.OrderID,
        InappStatus: statusFromPref(channels.InApp), // 'pending' or 'disabled'
        EmailStatus: statusFromPref(channels.Email),  // 'pending' or 'disabled'
    })
}
```

## notification_events table

```sql
CREATE TABLE notification_events (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    inapp_status notification_processing_status NOT NULL DEFAULT 'disabled',
    email_status notification_processing_status NOT NULL DEFAULT 'disabled',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Partial indexes for processor queries
CREATE INDEX idx_notif_inapp_pending ON notification_events (inapp_status, user_id)
    WHERE inapp_status = 'pending';
CREATE INDEX idx_notif_email_pending ON notification_events (email_status, created_at)
    WHERE email_status = 'pending';
```

Status enum: `disabled → pending → processing → completed / failed`

`disabled` means the user has that channel turned off — the row is written but never processed. `pending` means it needs processing. `processing` is held by a processor. Terminal states are `completed` and `failed`.

## Processor claim pattern

```sql
WITH claimed AS (
    SELECT id FROM notification_events
    WHERE inapp_status = 'pending'
    ORDER BY user_id, event_type, entity_id
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE notification_events SET inapp_status = 'processing', updated_at = NOW()
FROM claimed WHERE notification_events.id = claimed.id
RETURNING notification_events.*;
```

`FOR UPDATE SKIP LOCKED` is mandatory when multiple processor instances run concurrently. Without it, two processors claim the same row and the user receives duplicate notifications.

## SSE consumer pattern

Each server instance registers a unique ephemeral consumer. Fan-out works because every instance receives every NATS message and forwards to its own SSE connections.

```go
// Each server instance gets a unique consumer name for fan-out
consumerName := fmt.Sprintf("sse-notifications-%s", uuid.New().String())
consumer, _ := nats.NewEventConsumer(consumerName, js, logger, handler,
    nats.WithDeliverNew(),
    nats.WithInactiveThreshold(10 * time.Minute),
)
```

`WithDeliverNew` means the consumer only receives messages published after it connects — correct for live SSE updates. `WithInactiveThreshold` ensures NATS cleans up the ephemeral consumer when the instance disconnects.

See [references/sse-fanout.md](references/sse-fanout.md) for the full per-instance pattern and frontend invalidation approach.

## Why

Sending from a domain handler couples delivery latency to the event processing path. A slow email provider blocks NATS message acknowledgement, causing redelivery and duplicate sends. The two-phase design (write row → process separately) decouples these concerns and makes retries safe.

A single status column for multi-channel notifications forces either separate tables or a complex bitmask. Separate `inapp_status` and `email_status` columns are explicit, indexable, and independently processable.

## Anti-patterns

**Sending email or SSE directly from a NATS event handler.** Couples delivery to the event processing path. Slow delivery = NATS redelivery = duplicate sends.

**SSE events carrying the full notification payload.** SSE is a hint that the client should re-fetch. Putting data in the SSE event creates a second source of truth and bypasses the notification read/unread lifecycle.

**Single status column for multi-channel notifications.** Forces separate tables or a bitmask. `inapp_status` and `email_status` are separate, indexable, processable independently.

**Durable consumer names for SSE.** NATS durable consumers accumulate messages when the instance is offline. On reconnect the instance replays stale notifications to live SSE connections. Use per-instance UUID consumers with `WithDeliverNew`.

**Processing without FOR UPDATE SKIP LOCKED.** Concurrent processors claim the same row. The user receives duplicates.

**Using `publisher.Publish(event)` instead of `PublishWithContext(ctx, event)`.** Loses trace context across the async boundary. See go-check-masena-go-first.

## References

- [go-check-masena-go-first](../go-check-masena-go-first/SKILL.md) — masena-go provides `nats.NewEventConsumer`, `nats.NewBatchConsumer`, `publisher.PublishWithContext`, and `sse.SSEManager`; use them
- [Notification pipeline (3-phase detail)](references/notifications-pipeline.md)
- [SSE fan-out and frontend invalidation](references/sse-fanout.md)
