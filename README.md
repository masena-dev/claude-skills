# masena-skills

Go and TypeScript engineering patterns for multi-tenant B2B SaaS — enforced as
Claude Code skills and PostToolUse hooks.

## Installation

```bash
# Via Claude Code marketplace
claude plugin marketplace add masena-skills

# Or install from local path
claude plugin install /path/to/claude-skills
```

## Skills

| Skill | Description |
|---|---|
| `go-check-masena-go-first` | Validates Go files against Masena architecture invariants |
| `go-codegen-patterns` | sqlc + oapi-codegen generation workflow for Go services |
| `go-multi-tenant-db` | Row-level security, tenant isolation, and pool setup for PostgreSQL |
| `ts-nextjs-bff` | Next.js BFF conventions: route handlers, orval API client, React Query |

## Enforcement Hook

After every `Write`, `Edit`, or `MultiEdit` tool call the hook
`hooks/scripts/enforce-masena-patterns.py` scans the modified file and prints
any violations directly in the agent's context window.

**Go checks:**
- Migration files: `ENABLE ROW LEVEL SECURITY` without a matching `FORCE`
- API handlers calling `db.Queries` directly instead of the service layer
- NATS `.Publish(` without `WithContext` (breaks distributed tracing)
- `pgxpool.New` without a nearby `AfterRelease` (required for `RESET ROLE`)

**TypeScript checks:**
- Client-side state libraries (zustand, redux, jotai, recoil, mobx) — use
  React Query + Context instead
- Next.js route handlers importing database libraries directly
- Raw `fetch('/api/…')` in component files — use the generated orval client

Violations are informational only (exit 0). The agent sees them and can correct
the code before finishing the task.

## Auto-update

Skills defined in `skills/*/SKILL.md` are reloaded automatically when the
plugin is updated. No Claude Code restart required.

## License

MIT
