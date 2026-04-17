# RLS Setup Checklist

Use this when adding a new table to a multi-tenant schema.

## Migration template

```sql
-- 1. Create the table with tenant_id as a non-nullable foreign key
CREATE TABLE your_table (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants(id),
    -- ... your columns
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Enable RLS — both statements, always
ALTER TABLE your_table ENABLE ROW LEVEL SECURITY;
ALTER TABLE your_table FORCE ROW LEVEL SECURITY;

-- 3. One policy per DML operation
CREATE POLICY your_table_select ON your_table
    FOR SELECT
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE POLICY your_table_insert ON your_table
    FOR INSERT
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE POLICY your_table_update ON your_table
    FOR UPDATE
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE POLICY your_table_delete ON your_table
    FOR DELETE
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

## Pool configuration checklist

- [ ] `AfterRelease` calls `RESET ROLE` first, then `RESET ALL`; returns `false` on any error
- [ ] `CheckPrivileges` runs at startup before accepting traffic
- [ ] Pool user is NOT a superuser and does NOT have `BYPASSRLS`
- [ ] Pool user has `SELECT`, `INSERT`, `UPDATE`, `DELETE` on the table — not `ALL PRIVILEGES`

## Privilege test (run in psql against the app role)

```sql
-- Should return false for both
SELECT rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname = current_user;

-- Should be empty (no superuser membership)
SELECT rolname FROM pg_roles
WHERE pg_has_role(current_user, oid, 'member')
  AND rolsuper = true;

-- Verify RLS is active on the table
SELECT relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname = 'your_table';
-- Expected: t | t
```

## Common mistakes

| Symptom | Cause |
|---------|-------|
| Table owner sees all rows | `FORCE` missing — add `ALTER TABLE ... FORCE ROW LEVEL SECURITY` |
| SET ROLE leaks between requests | `AfterRelease` missing `RESET ROLE` before `RESET ALL` |
| Privilege check passes but RLS is bypassed | Check using `current_user` not `session_user` |
| Policy silently filters nothing | `current_setting('app.tenant_id', true)` returns `''` — use `NULLIF(..., '')` to treat empty string as NULL |
