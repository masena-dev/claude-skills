# Notifications Pipeline

Three phases, each independently deployable and independently scalable.

## Status transitions

```
disabled   — channel turned off by user preference; row written, never claimed
pending    — channel enabled; waiting for processor
processing — claimed by a processor with FOR UPDATE SKIP LOCKED
completed  — delivered successfully
failed     — delivery failed after retries
```

A notification_events row always has two independent status columns (`inapp_status`, `email_status`). Each transitions independently. A row is "done" when both statuses are terminal.

## Phase 1: Domain handler → determine → persist

The domain event handler runs inside the NATS consumer callback. Its only job is to write a row.

Steps: NATS event arrives → determine channels (query user preferences, map to `pending`/`disabled`) → write `notification_events` row → acknowledge NATS message.

The handler must not call any external service (email provider, SSE manager). If it does, a slow provider blocks the NATS ack, causing redelivery.

## Phase 2: Scheduled processor → claim → batch → deliver → publish

The processor runs on a tick (e.g., every 5 seconds). Steps: claim batch with `FOR UPDATE SKIP LOCKED` → group by `(user_id, event_type, entity_id)` to deduplicate rapid-fire events → for each group: INSERT notification record, deliver via channel, publish NATS event for SSE fan-out, update status to `completed`/`failed`.

Batching by `(user, type, entity)` prevents a user from receiving five "item updated" notifications when five rapid writes happen to the same entity.

### In-app claim query

```sql
WITH claimed AS (
    SELECT id FROM notification_events
    WHERE inapp_status = 'pending'
    ORDER BY user_id, event_type, entity_id
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE notification_events
    SET inapp_status = 'processing', updated_at = NOW()
FROM claimed
WHERE notification_events.id = claimed.id
RETURNING notification_events.*;
```

### Email claim query

```sql
WITH claimed AS (
    SELECT id FROM notification_events
    WHERE email_status = 'pending'
    ORDER BY created_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE notification_events
    SET email_status = 'processing', updated_at = NOW()
FROM claimed
WHERE notification_events.id = claimed.id
RETURNING notification_events.*;
```

## Phase 3: SSE consumer → fan-out → frontend invalidation

```
NATS message arrives at SSE consumer
    │
    ▼
SSEManager.Publish(ctx, Event{ClientID: userID, Type: Notification, Data: hint})
    — hint contains only: event_type, entity_id, timestamp
    — no notification body, no read/unread state
    │
    ▼
Browser EventSource receives hint
    │
    ▼
React Query invalidates notification list query
    — debounced 200ms to collapse rapid-fire hints
    │
    ▼
Client re-fetches /notifications from API
    — single source of truth; read/unread managed server-side
```

The SSE payload is intentionally minimal. It tells the frontend "something changed for you" — not what changed or what the notification says. The frontend always re-fetches from the API. This keeps the SSE path stateless and the notification state owned by the database.
