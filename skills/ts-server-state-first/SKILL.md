---
name: ts-server-state-first
description: >-
  React Query as the single source of truth for server state. Triggers when
  choosing state management libraries, writing data fetching hooks, implementing
  SSE real-time updates, or considering Zustand/Redux/Jotai for server data.
  Bans external state libraries for server state.
license: MIT
---

## The Rule

React Query is the store. No Zustand, Redux, Jotai, or Recoil for server state. React Context is for ephemeral UI state only (modal visibility, connection status). SSE events invalidate cache — they don't carry data.

## State Management Decision Tree

| Data type | Where it lives | Example |
|-----------|---------------|---------|
| Server data (API responses) | React Query cache | User profile, order list, notifications |
| Ephemeral UI state | React Context | Modal open/close, sidebar collapsed |
| Form state | React Hook Form / local state | Input values during editing |
| Optimistic updates | React Query mutations | Vote count before server confirms |
| Cross-tab persistence | SessionStorage (sparingly) | Back-button optimistic state |

## SSR Hydration (MANDATORY)

```typescript
// Server component (layout or page)
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';

export default async function Layout({ children }) {
  const queryClient = getQueryClient();

  const user = await fetchUser(token);
  queryClient.setQueryData(['user'], user);

  const dehydratedState = dehydrate(queryClient);
  return (
    <HydrationBoundary state={dehydratedState}>
      {children}
    </HydrationBoundary>
  );
}
```

## SSE Cache Invalidation (MANDATORY)

SSE events trigger React Query refetch — they never carry the payload.

```typescript
const scheduleInvalidation = useCallback(() => {
  if (timeoutRef.current) clearTimeout(timeoutRef.current);
  timeoutRef.current = setTimeout(() => {
    queryClient.invalidateQueries({
      queryKey: ['notifications'],
      refetchType: 'active'  // Only refetch queries actively rendered
    });
  }, 1000); // Debounce: 1s after last SSE event
}, [queryClient]);

eventSource.addEventListener('notification', () => {
  scheduleInvalidation(); // Invalidate, don't update cache directly
});
```

## Context Providers — What Belongs

All context providers should manage UI state only:

- `AuthModalProvider` — login/signup view state
- `ConfirmModalProvider` — confirmation dialog state
- `NotificationProvider` — SSE connection lifecycle + invalidation scheduling

## Anti-Patterns

- Importing zustand, redux, jotai, recoil, or mobx for server state
- Storing API responses in React Context or component state
- SSE events that carry full notification payloads (use invalidation hints)
- `queryClient.setQueryData` from SSE handler — use `invalidateQueries`, let RQ refetch with latest
- Skipping HydrationBoundary in SSR (causes client-side flash)
- Creating a global store for data that React Query already manages
