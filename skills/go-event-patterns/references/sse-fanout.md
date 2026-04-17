# SSE Fan-Out Pattern

Per-instance ephemeral consumers ensure all server instances receive all events for fan-out to their connected clients.

## Why per-instance consumers

In a multi-instance deployment, each server has its own set of SSE connections. A durable consumer would load-balance messages across instances — meaning only one instance sees each event. For SSE, every instance needs every event so it can deliver to whichever clients are connected to it.

## Setup

```go
// Each instance generates a unique consumer name on startup
consumerName := fmt.Sprintf("sse-notifications-%s", uuid.New().String())

consumer, err := nats.NewEventConsumer(consumerName, js, logger, handler,
    nats.WithDeliverNew(),                        // Only new events, no replay
    nats.WithInactiveThreshold(10 * time.Minute), // Auto-delete when instance stops
)
```

**`WithDeliverNew()`** — SSE clients don't need historical events. They reconnect and refetch via React Query.

**`WithInactiveThreshold(10m)`** — When an instance shuts down, its consumer is automatically cleaned up by NATS after 10 minutes of inactivity. No manual cleanup needed.

## Handler routing

The SSE handler routes events to connected clients by user ID:

```go
func (h *handler) HandleEvent(ctx context.Context, evt NotificationEvent) error {
    return h.sseManager.Publish(ctx, sse.Event{
        ClientID: evt.UserID,          // Route to specific user's connections
        Type:     sse.Notification,
        Data:     NotificationHint{ID: evt.NotificationID, Type: evt.Type},
    })
}
```

## SSE events are hints, not data

SSE events carry only the notification ID and type — never the full payload. The frontend uses SSE events to trigger React Query cache invalidation:

```typescript
// Frontend: SSE event triggers refetch, not cache update
eventSource.addEventListener('notification', () => {
  // Debounce: invalidate 1s after last event (handles burst scenarios)
  scheduleInvalidation();
});

const scheduleInvalidation = () => {
  clearTimeout(timeoutRef.current);
  timeoutRef.current = setTimeout(() => {
    queryClient.invalidateQueries({ queryKey: ['notifications'], refetchType: 'active' });
  }, 1000);
};
```

**Why not carry data?**
1. SSE has no guaranteed ordering across instances
2. React Query already manages staleness and caching
3. Carrying data means the SSE event becomes a second source of truth
4. Invalidation-only is simpler and avoids consistency bugs

## Anti-patterns

- **Durable consumer names for SSE** — load-balances events instead of fanning out
- **`WithDeliverAll()`** — replays historical events to every new instance
- **Carrying full notification payload in SSE** — creates dual source of truth with API
- **`setQueryData` from SSE handler** — stale data if SSE arrives out of order; use `invalidateQueries` instead
