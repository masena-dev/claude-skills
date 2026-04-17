---
name: go-multi-tenant-db
description: >-
  Multi-tenant PostgreSQL with Row-Level Security. Triggers when writing migrations
  with RLS policies, configuring connection pools, setting up privilege checks,
  designing user/membership tables, or implementing OIDC account linking.
license: MIT
---

# Go Multi-Tenant DB

Every RLS table needs ENABLE + FORCE. Every pool connection needs AfterRelease with RESET ROLE + RESET ALL. Every startup needs a privilege check that hard-fails on superuser/BYPASSRLS.

## When to use

- Writing a migration that adds a new multi-tenant table
- Configuring `pgxpool` for tenant-scoped queries
- Designing `users` or `tenant_members` tables
- Implementing OIDC login or account linking
- Adding an RLS policy to an existing table

## The rule

**ENABLE + FORCE on every table. AfterRelease resets both ROLE and ALL. Privilege check runs at startup and hard-fails.**

## Migrations

```sql
-- Both statements required on EVERY RLS table
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

-- Standard tenant isolation policy
CREATE POLICY orders_tenant_select ON orders
    FOR SELECT
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE POLICY orders_tenant_insert ON orders
    FOR INSERT
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE POLICY orders_tenant_update ON orders
    FOR UPDATE
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE POLICY orders_tenant_delete ON orders
    FOR DELETE
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

## Pool safety hooks

```go
// AfterRelease: RESET ROLE then RESET ALL when returning connections to pool
config.AfterRelease = func(conn *pgx.Conn) bool {
    if _, err := conn.Exec(context.Background(), "RESET ROLE"); err != nil {
        return false // Destroy connection on error
    }
    if _, err := conn.Exec(context.Background(), "RESET ALL"); err != nil {
        return false
    }
    return true
}
```

## Startup privilege check

```go
func CheckPrivileges(ctx context.Context, conn *pgx.Conn) error {
    var sessionUser string
    var isSuper, bypassRLS bool
    err := conn.QueryRow(ctx, `
        SELECT session_user, rolsuper, rolbypassrls
        FROM pg_roles WHERE rolname = session_user
    `).Scan(&sessionUser, &isSuper, &bypassRLS)
    if err != nil {
        return fmt.Errorf("check RLS privileges: %w", err)
    }
    if isSuper {
        return fmt.Errorf("SECURITY: user %q is superuser", sessionUser)
    }
    if bypassRLS {
        return fmt.Errorf("SECURITY: user %q has BYPASSRLS", sessionUser)
    }
    return nil
}
```

Call this during application startup, before accepting traffic. A hard failure is correct — a misconfigured role means tenant data is exposed.

## Dual-context RLS for memberships

Some tables must be readable in two contexts: with a full tenant context, and during login when only a user ID is set.

```sql
-- SELECT: tenant context OR user-only login context
CREATE POLICY tenant_members_select ON tenant_members
FOR SELECT USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    OR (
        NULLIF(current_setting('app.tenant_id', true), '')::uuid IS NULL
        AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    )
);
-- WRITES: always require tenant context
CREATE POLICY tenant_members_insert ON tenant_members
FOR INSERT WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

## User table design

- `(oidc_issuer, oidc_subject)` composite unique — supports multiple IdPs per user
- `users.status` for account-level states (active, suspended, onboarding)
- `tenant_members.status` for membership-level states (active, invited, removed)
- Both status layers are needed — account suspension is different from membership removal
- `first_name + last_name` is appropriate for B2B SaaS; consumer apps may use a single `display_name` field; note that mononyms exist in some locales

See [references/oidc-linking.md](references/oidc-linking.md) for the full OIDC account-linking state machine.

## Why

`ENABLE` without `FORCE` means the table owner bypasses RLS entirely — any query running as the owner (including migrations, admin scripts, or a misconfigured pool user) silently reads across all tenants. `FORCE` closes that gap.

`RESET ALL` alone does not reset `SET ROLE`. If a request sets a role and panics before cleanup, the next request from the pool inherits it. Resetting ROLE first, then ALL, is the correct order.

`current_user` reflects the active role after `SET ROLE`. Only `session_user` reflects the login role and cannot be spoofed by `SET ROLE`. The privilege check must use `session_user`.

## Anti-patterns

**ENABLE without FORCE.** Table owner bypasses RLS — any code running as the owner reads across all tenants with no error.

**AfterRelease with only RESET ALL.** `SET ROLE` state is not cleared by `RESET ALL`. Role leaks between requests silently.

**Privilege check using `current_user`.** Vulnerable to `SET ROLE` bypass — an unprivileged user can set a privileged role and pass the check.

**Single `external_id` column for OIDC identity.** Breaks when you add a second IdP. Use `(oidc_issuer, oidc_subject)` composite unique from day one.

**Status only on `users` or only on `tenant_members`.** Account-level and membership-level states have different semantics and different owners. Collapsing them into one column creates ambiguity when a user is suspended globally but still has pending memberships.

## References

- [go-check-masena-go-first](../go-check-masena-go-first/SKILL.md) — masena-go has `tenancy.WithTenantTx`, `tenancy.WithReadTenantTx`, and `tenancy.WithUserTx` wrappers; use them instead of writing raw `SET LOCAL` calls
- [OIDC account-linking state machine](references/oidc-linking.md)
- [RLS setup checklist for new tables](references/rls-setup-checklist.md)
