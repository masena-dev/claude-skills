# masena-go API Inventory (v1.2.0)

> Last updated: 2026-04-17. Source: `github.com/masena-dev/masena-go`

## Package `auth`

Authentication primitives: password hashing (Argon2id), token generation, sliding session expiry.

### Types

```go
type Token struct {
    Plaintext string    // 26-char base32 (sent to client)
    Hash      []byte    // SHA256 (stored in database)
    Expiry    time.Time // Absolute expiry
}

type SessionConfig struct {
    AbsoluteTTL      time.Duration // Max session lifetime (default: 12h)
    IdleTTL          time.Duration // Inactivity timeout (default: 60m)
    WarningThreshold time.Duration // Warning before expiry (default: 2m)
}

type SessionExpiry struct {
    AbsoluteExpiry time.Time
    IdleExpiry     time.Time
    ServerTime     time.Time
}

type ExpiryType int // ExpiryTypeIdle | ExpiryTypeAbsolute
```

### Functions

```go
// Password
func ValidatePassword(password string) error
func HashPassword(password string) (string, error)
func HashPasswordWithParams(password string, params *argon2id.Params) (string, error)
func VerifyPassword(password, hash string) (bool, error)

// Token
func GenerateToken(ttl time.Duration) (*Token, error)
func HashToken(plaintext string) []byte
func VerifyToken(plaintext string, storedHash []byte) bool

// Session
func DefaultSessionConfig() SessionConfig
func CalculateExpiry(config SessionConfig, createdAt, lastActivity time.Time) SessionExpiry
func CalculateExpiryNow(config SessionConfig, createdAt time.Time) SessionExpiry
func CORSExposeHeaders() []string

// SessionExpiry methods
func (e SessionExpiry) EffectiveExpiry() time.Time
func (e SessionExpiry) TimeRemaining() time.Duration
func (e SessionExpiry) NeedsWarning(threshold time.Duration) bool
func (e SessionExpiry) IsExpired() bool
func (e SessionExpiry) ClosestExpiryType() ExpiryType
func (e SessionExpiry) SetSessionHeaders(w http.ResponseWriter)
```

### Constants

```go
const MinPasswordLength = 12
const MaxPasswordLength = 72
const DefaultAbsoluteTTL = 12 * time.Hour
const DefaultIdleTTL = 60 * time.Minute
const DefaultWarningThreshold = 2 * time.Minute

const HeaderSessionAbsoluteExpiry = "X-Session-Absolute-Expiry"
const HeaderSessionIdleExpiry = "X-Session-Idle-Expiry"
const HeaderServerTime = "X-Server-Time"
```

### Sentinel errors

```go
var ErrPasswordTooShort   = errors.New("password must be at least 12 characters")
var ErrPasswordTooLong    = errors.New("password must be at most 72 characters")
var ErrPasswordNotComplex = errors.New("password must contain at least 3 of: lowercase, uppercase, digit, special character")
```

---

## Package `tenancy`

Multi-tenant context management and PostgreSQL RLS transaction wrappers.

### Types

```go
// SetContextFunc sets tenant or user context in a transaction.
// Default implementations: DefaultSetTenantContext(), DefaultSetUserContext()
type SetContextFunc func(ctx context.Context, tx pgx.Tx, id string) error
```

### Functions

```go
// Context helpers
func WithTenantID(ctx context.Context, id string) context.Context
func TenantIDFromContext(ctx context.Context) (string, bool)
func MustTenantID(ctx context.Context) string
func WithUserID(ctx context.Context, id string) context.Context
func UserIDFromContext(ctx context.Context) (string, bool)
func MustUserID(ctx context.Context) string

// SetContextFunc factories
func DefaultSetTenantContext() SetContextFunc  // SET LOCAL app.tenant_id
func DefaultSetUserContext() SetContextFunc    // SET LOCAL app.user_id

// Transaction wrappers (handle begin/commit/rollback + RLS context)
func WithTenantTx(ctx, pool, tenantID, setContext, fn) error      // Write tx with tenant context
func WithReadTenantTx(ctx, pool, tenantID, setContext, fn) error   // Read-only tx with tenant context
func WithUserTx(ctx, pool, userID, setContext, fn) error           // Write tx with user context
func WithReadUserTx(ctx, pool, userID, setContext, fn) error       // Read-only tx with user context
```

---

## Package `nats`

JetStream publishers, consumers, OTel trace propagation, stream management.

### Interfaces

```go
type Event interface {
    Subject() string
    Stream() string
}

type DynamicSubjectEvent interface {
    Event
    WildcardSubject() string
}

type EventHandler[E Event] interface {
    HandleEvent(ctx context.Context, event E) error
}

type BatchEventHandler[E Event] interface {
    HandleBatchEvents(ctx context.Context, events []E) error
}
```

### Types

```go
type Client struct { jetstream.JetStream }
type ClientConfig struct {
    StreamReplicas     int
    AllowAtomicPublish bool
}
type Publisher[E Event] struct { /* ... */ }
type Consumer[E Event] struct { /* ... */ }
type ConsumerManager struct { /* ... */ }
type ConsumerOption func(*jetstream.ConsumerConfig)
type EventTester[T Event] struct { /* ... */ }  // testing utility
```

### Functions

```go
// Client
func NewClient(conn *nats.Conn, config ClientConfig) (*Client, error)
func (c *Client) Config() ClientConfig

// Publisher
func NewPublisher[E Event](js *Client, logger *slog.Logger) (*Publisher[E], error)
func (p *Publisher[E]) PublishWithContext(ctx context.Context, event E) error
func (p *Publisher[E]) PublishBatch(ctx context.Context, events []E) error
func (p *Publisher[E]) Publish(event E) error  // DEPRECATED: use PublishWithContext

// Consumer
func NewEventConsumer[E Event](name string, js *Client, logger *slog.Logger, handler EventHandler[E], opts ...ConsumerOption) (*Consumer[E], error)
func NewBatchConsumer[E Event](name string, js *Client, logger *slog.Logger, handler BatchEventHandler[E], opts ...ConsumerOption) (*Consumer[E], error)

// Consumer options
func WithDeliverNew() ConsumerOption
func WithDeliverAll() ConsumerOption
func WithInactiveThreshold(threshold time.Duration) ConsumerOption

// Consumer manager
func NewConsumerManager(logger *slog.Logger) *ConsumerManager
func (m *ConsumerManager) AddConsumers(c ...consumer)  // consumer is unexported; *Consumer[E] satisfies it
func (m *ConsumerManager) Start(ctx context.Context)
func (m *ConsumerManager) Stop()

// OTel trace propagation
func InjectTraceContext(ctx context.Context, msg *nats.Msg)
func ExtractTraceContext(ctx context.Context, msg *nats.Msg) context.Context
func StartConsumerSpan(ctx context.Context, msg *nats.Msg, operationName string) (context.Context, trace.Span)
func StartPublisherSpan(ctx context.Context, subject string, operationName string) (context.Context, trace.Span)
func RecordError(span trace.Span, err error, description string)
func WithEventAttributes(span trace.Span, attrs ...attribute.KeyValue)
func FormatOperationName(action, subject string) string

// Stream management
func EnsureStream(js *Client, logger *slog.Logger, stream string, subject string) error

// Utilities
func GetMessageID(ctx context.Context) string

// Testing
func NewEventTester[T Event](js *Client, logger *slog.Logger) (*EventTester[T], error)
func (t *EventTester[T]) Events() []T
func (t *EventTester[T]) Consumer() *Consumer[T]
func RunConsumer[T Event](ctx context.Context, consumer *Consumer[T], count int, timeout time.Duration) error
```

---

## Package `sse`

Server-Sent Events manager for real-time event streaming to HTTP clients.

### Types

```go
type SSEManager struct { /* ... */ }
type Subscription struct {
    Writer *EventWriter
}
type Event struct {
    ClientID string
    Data     any
    Type     EventType
    ID       string
}
type EventType string
type Option func(*SSEManager)
type OnSubscribeCallback func(sseMan *SSEManager, clientID string) error
```

### Functions

```go
func NewSSEManager(logger *slog.Logger, opts ...Option) *SSEManager
func WithOnSubscribe(callback OnSubscribeCallback) Option
func (s *SSEManager) Subscribe(w http.ResponseWriter, clientID string) (*Subscription, error)
func (s *SSEManager) Publish(ctx context.Context, e Event) error
func (s *SSEManager) Stop()
func (s *Subscription) EventChan() <-chan Event
func (s *Subscription) Close()
func (e Event) Build() (string, error)
```

### Pre-built events

```go
var Notification EventType = "notification"
var ClientConnected = Event{Data: "client connected", Type: connected}
var ClientDisconnected = Event{Data: "client disconnected", Type: disconnected}
```

### Sentinel errors

```go
var ErrSSEManagerClosed = errors.New("server-sent events manager has been shutdown")
var ErrClientIDEmpty = errors.New("client_id cannot be empty")
var ErrClientIDTooLong = errors.New("client_id exceeds maximum length")
```
