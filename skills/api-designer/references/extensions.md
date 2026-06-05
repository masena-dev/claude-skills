# oapi-codegen Extension Decision Guide

Load this file when choosing which oapi-codegen extensions to apply to a field or parameter in `openapi.yaml`.

---

## x-go-type

**Problem it solves**: oapi-codegen's default type mappings don't fit every use case. A `type: object` with no schema becomes `map[string]interface{}`. A `type: string` with no format becomes `string`. Neither is right for freeform JSON blobs or monetary values.

**When to use**:
- Field holds freeform JSON (rich text editor content, rule configs, arbitrary metadata) → map to `json.RawMessage`
- Field is monetary or financial → map to `decimal.Decimal` (requires `x-go-type-import`)
- Default integer mapping is too narrow → force `int64` or `float64` for precision-sensitive values

**Before / after**:

```yaml
# Before — generates *string, loses semantic intent
content:
  type: string
  nullable: true
```

```yaml
# After — generates json.RawMessage, correct for rich text content
content:
  x-go-type: json.RawMessage
```

```yaml
# Before — generates string, no decimal precision
amount:
  type: string
```

```yaml
# After — generates decimal.Decimal with correct import
amount:
  type: string
  x-go-type: decimal.Decimal
  x-go-type-import:
    path: github.com/shopspring/decimal
```

**Watch out**: `x-go-type` alone only works for standard library types (`json.RawMessage`, `int64`, etc.). For any type from an external package, you must also add `x-go-type-import` — missing it produces a compilation error.

---

## x-go-type-import

**Problem it solves**: When `x-go-type` references a type from an external package, the generated file won't compile unless the import is declared. `x-go-type-import` injects the import.

**When to use**: Always alongside `x-go-type` when the type lives outside the standard library.

**Example**:

```yaml
cost:
  type: string
  x-go-type: decimal.Decimal
  x-go-type-import:
    path: github.com/shopspring/decimal
```

For `json.RawMessage`, no import is needed (`encoding/json` is part of the standard library and always available).

**Watch out**: The `path` field is the full Go import path, not a package alias. If the last path segment doesn't match what you want as the package qualifier (e.g., a fork with a different module name), add a `name` field:

```yaml
x-go-type-import:
  name: dec
  path: github.com/some-fork/decimal-v2
```

---

## x-go-type-skip-optional-pointer

**Problem it solves**: oapi-codegen wraps every optional field in a pointer (`*bool`, `*string`, `*int`). For some fields, a pointer is wrong — either because `false` and `0` are meaningful values (not "unset"), or because the field uses a type that already handles optionality.

**When to use**:
- Optional boolean where `false` is a real value, not "not provided" — e.g., `remember_me`, `is_nsfw`
- Array fields where `nil` vs empty slice doesn't matter to the consumer — e.g., `fields: []ErrorField`
- Fields using `nullable.Nullable` wrapper (already distinguishes null from omitted — a pointer on top adds nothing)

**Before / after**:

```yaml
# Before — generates *bool, but false means the checkbox is checked, not absent
remember_me:
  type: boolean
```

```yaml
# After — generates bool
remember_me:
  type: boolean
  x-go-type-skip-optional-pointer: true
```

```yaml
# Before — generates *[]ErrorField
fields:
  type: array
  items:
    $ref: "#/components/schemas/ErrorField"
```

```yaml
# After — generates []ErrorField
fields:
  type: array
  items:
    $ref: "#/components/schemas/ErrorField"
  x-go-type-skip-optional-pointer: true
```

**Watch out**: Don't apply this when `nil` genuinely means "the field was not sent". For example, a PATCH body field where omission means "leave unchanged" and `null` means "clear the value" — in that case, you want the pointer (or a `Nullable` type, not a skip).

---

## x-omitempty: false

**Problem it solves**: Optional nullable fields get `json:",omitempty"` by default, which means they're dropped from the JSON response when null. This breaks frontend code that expects the field key to always be present.

**When to use**:
- Profile fields that can be explicitly null — profile pictures, bios, social links, published dates
- Any field where the frontend must distinguish "field is null" from "field was never in the response"
- Response fields where a null signals an intentional state (unpublished, not set) rather than absence of data

**Before / after**:

```yaml
# Before — generates json:"bio,omitempty" — bio is dropped when null
bio:
  type: string
  nullable: true
```

```yaml
# After — generates json:"bio" — bio is always present, serialized as null when empty
bio:
  type: string
  nullable: true
  x-omitempty: false
```

**Watch out**: This increases response payload size for every resource returned. Only use it when the field's null state carries meaning. For internal fields or admin-only data where omission is fine, leave the default.

---

## x-order

**Problem it solves**: oapi-codegen doesn't guarantee field order in generated structs. Fields end up alphabetical or in spec-declaration order, making the struct harder to read when inspecting generated code.

**When to use**: Response schemas where field ordering aids readability — identifiers first, timestamps last is the conventional Go struct order.

**Example**:

```yaml
properties:
  slug:
    type: string
    x-order: 1
  title:
    type: string
    x-order: 2
  body:
    type: string
    x-order: 3
  created_at:
    type: string
    format: date-time
    x-order: 10
  updated_at:
    type: string
    format: date-time
    x-order: 11
```

**Watch out**: `x-order` only affects the generated Go struct layout. It has no effect on JSON serialization order (Go's `encoding/json` serializes by struct field order, but HTTP clients should not rely on JSON key order). Don't use it as a way to control API response key ordering.

---

## x-enumNames

**Problem it solves**: Enum values like `POST_NOT_FOUND` or `rate_limit_exceeded` generate Go constants with the same name, which is valid but doesn't follow Go naming conventions. `x-enumNames` lets you override the constant names independently of the wire values.

**When to use**: Any enum where the string values don't map cleanly to idiomatic Go identifiers — SCREAMING_SNAKE_CASE, values with hyphens or slashes, or values that would produce ambiguous constant names.

**Example**:

```yaml
ErrorCode:
  type: string
  enum:
    - POST_NOT_FOUND
    - INVALID_OTP
    - RATE_LIMIT_EXCEEDED
  x-enumNames:
    - PostNotFound
    - InvalidOtp
    - RateLimitExceeded
```

Generated:
```go
const (
    PostNotFound       ErrorCode = "POST_NOT_FOUND"
    InvalidOtp         ErrorCode = "INVALID_OTP"
    RateLimitExceeded  ErrorCode = "RATE_LIMIT_EXCEEDED"
)
```

**Watch out**: The arrays must be the same length and position-aligned. If `enum[2]` is `RATE_LIMIT_EXCEEDED`, then `x-enumNames[2]` must be `RateLimitExceeded`. oapi-codegen won't error on a mismatch — it silently assigns the wrong name to the wrong value. This is the most common source of subtle codegen bugs. Whenever you add or remove an enum value, update both arrays together and verify alignment before regenerating.

---

## x-go-type: NullableString (special case)

**Problem it solves**: A `*string` field can be `nil` (not provided) or `"value"` (provided), but it can't distinguish between the client sending `null` (explicit clear) and the client omitting the field entirely. PATCH endpoints need this distinction.

**When to use**: PATCH request body fields where a user can explicitly clear a previously set value — social media link URLs, optional profile fields, any field where `null` on the wire means "delete this value" and omission means "leave it alone".

**Pattern** — all three extensions are required together:

```yaml
facebook_url:
  type: string
  nullable: true
  x-go-type: NullableString
  x-go-type-skip-optional-pointer: true
```

This requires a type alias in the codebase pointing to the `oapi-codegen/nullable` package:

```go
type NullableString = nullable.Nullable[string]
```

The `Nullable[T]` type exposes `.IsNull()`, `.IsSpecified()`, and `.MustGet()` — handler code checks `IsSpecified()` first, then `IsNull()` to decide whether to clear or update.

**Watch out**: Only use this when null/omit distinction actually matters to business logic. For a GET response field that can be null, `x-omitempty: false` is sufficient. Overusing `Nullable` adds handler complexity for no benefit on most fields.

---

## allowEmptyValue: true

**Problem it solves**: OpenAPI treats an empty string query parameter as absent by default, which means `?cursor=` is silently dropped. Cursor pagination uses an empty cursor for the first page — without `allowEmptyValue`, the first page request is indistinguishable from a missing parameter in some client generators.

**When to use**:
- Cursor pagination params (first page has no cursor, client sends empty string)
- Redirect URI params where an empty redirect means "use default"

**Example**:

```yaml
parameters:
  - name: cursor
    in: query
    allowEmptyValue: true
    schema:
      type: string
  - name: limit
    in: query
    schema:
      type: integer
```

**Watch out**: `allowEmptyValue` is an OpenAPI parameter-level option, not a schema extension. It lives on the parameter object, not inside `schema`. Placing it inside `schema` has no effect and produces no error.
