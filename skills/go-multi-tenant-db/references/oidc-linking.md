# OIDC Account Linking State Machine

When a user authenticates via OIDC, five branches must be handled in order. Skipping any branch creates security gaps.

## The five branches

```
Incoming: (oidc_issuer, oidc_subject, email, email_verified)
│
├─ 1. Lookup by (oidc_issuer, oidc_subject)
│      └─ FOUND → existing OIDC user, proceed to session creation
│
├─ 2. Not found + email_verified = false
│      └─ REJECT — cannot link or create without a verified email
│
├─ 3. Lookup by email for linking (verified + active only)
│      └─ FOUND, no existing OIDC identity → link new identity, proceed
│
├─ 4. FOUND with a different OIDC identity already attached
│      └─ REJECT — prevent cross-account linking
│
└─ 5. No user found at all
       └─ CREATE new onboarding user
```

## Why the order matters

Branch 1 must run before branch 3. If you check by email first, you risk linking an IdP to the wrong account when two IdPs report the same email address for different people.

Branch 2 must gate branches 3 and 5. An unverified email can be claimed by anyone — allowing account creation or linking on unverified email enables pre-registration attacks where an attacker registers an email before the real owner does.

Branch 4 prevents re-linking. Once an email is associated with an OIDC identity, a second OIDC identity from the same or a different IdP cannot claim it by presenting the same email. The user must explicitly merge accounts through a separate flow.

## GetUserByEmailForLinking SQL

This query is security-critical. The `email_verified_at IS NOT NULL AND status = 'active'` constraints must be enforced at the SQL level, not in application code.

```sql
-- name: GetUserByEmailForLinking :one
SELECT
    u.id,
    u.email,
    u.status,
    u.email_verified_at,
    ui.oidc_issuer,
    ui.oidc_subject
FROM users u
LEFT JOIN user_identities ui ON ui.user_id = u.id
WHERE u.email = $1
  AND u.email_verified_at IS NOT NULL
  AND u.status = 'active'
LIMIT 1;
```

If this query returns a row, inspect `oidc_issuer` and `oidc_subject`:
- Both NULL → no identity linked yet → branch 3 (link)
- Either non-NULL → identity already exists → branch 4 (reject)

## User identity table

```sql
CREATE TABLE user_identities (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    oidc_issuer TEXT NOT NULL,
    oidc_subject TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (oidc_issuer, oidc_subject)
);
```

The `UNIQUE (oidc_issuer, oidc_subject)` constraint enforces at the database level that one IdP identity maps to at most one user. A unique index on `(user_id, oidc_issuer)` can additionally enforce that one user has at most one identity per IdP, if that constraint is desired.

## Onboarding user creation (branch 5)

New users are created with `status = 'onboarding'`, not `'active'`. They complete onboarding (profile setup, email verification confirmation, org creation or join) before becoming active. The transition from `onboarding` to `active` is an explicit application event, not an implicit side effect of login.
