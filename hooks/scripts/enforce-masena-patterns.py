#!/usr/bin/env python3
"""
Masena pattern enforcement hook.

Runs as a PostToolUse hook after Write/Edit/MultiEdit operations.
Prints violations to stdout so the agent sees them.
Exits 0 always — violations are informational, not blocking.
"""

import os
import re
import sys


def check_go_file(path: str, content: str) -> list[str]:
    violations = []

    # 1. Migration RLS: ENABLE without FORCE
    if "migrations/" in path:
        enable_tables = set(
            re.findall(
                r"ALTER TABLE\s+(\S+)\s+ENABLE ROW LEVEL SECURITY",
                content,
                re.IGNORECASE,
            )
        )
        force_tables = set(
            re.findall(
                r"ALTER TABLE\s+(\S+)\s+FORCE ROW LEVEL SECURITY",
                content,
                re.IGNORECASE,
            )
        )
        missing_force = enable_tables - force_tables
        for table in sorted(missing_force):
            violations.append(
                f"RLS: Table {table} has ENABLE but missing FORCE ROW LEVEL SECURITY"
            )

    # 2. Handler bypassing service layer
    normalized = path.replace("\\", "/")
    if "/internal/api/" in normalized:
        if re.search(r"\.Queries\.", content):
            violations.append(
                "Architecture: Handlers should call through service layer, not db.Queries directly"
            )

    # 3. Publish without context propagation
    # Match .Publish( that is NOT PublishWithContext, PublishBatch, or PublishMsgAsync
    for match in re.finditer(r"\.\bPublish\(", content):
        start = match.start()
        # Look back up to 30 chars to check method name prefix
        prefix_start = max(0, start - 30)
        surrounding = content[prefix_start : match.end()]
        if not re.search(
            r"\b(PublishWithContext|PublishBatch|PublishMsgAsync)\($", surrounding
        ):
            violations.append(
                "Tracing: Use PublishWithContext for trace propagation, not Publish"
            )
            break  # One violation per file is enough

    # 4. pgxpool without AfterRelease
    pool_match = re.search(r"\bpgxpool\.(New|NewWithConfig)\(", content)
    if pool_match:
        pool_pos = pool_match.start()
        lines = content.splitlines()
        # Find the line number of the pool call
        pool_line = content[: pool_pos].count("\n")
        window_start = max(0, pool_line - 10)
        window_end = min(len(lines), pool_line + 50)
        window = "\n".join(lines[window_start:window_end])
        if "AfterRelease" not in window:
            violations.append(
                "Security: Pool must configure AfterRelease with RESET ROLE + RESET ALL"
            )

    return violations


def check_ts_file(path: str, content: str) -> list[str]:
    violations = []

    # 5. Client-side state management libraries
    state_libs = [
        "zustand",
        "redux",
        "@reduxjs/toolkit",
        "jotai",
        "recoil",
        "mobx",
    ]
    for lib in state_libs:
        if re.search(rf"""['"]{re.escape(lib)}['"/]""", content):
            violations.append(
                "State: Use React Query for server state, React Context for ephemeral UI state"
            )
            break

    # 6. Next.js route handlers with direct DB access
    normalized = path.replace("\\", "/")
    is_api_route = "/app/api/" in normalized or "/pages/api/" in normalized
    if is_api_route:
        db_libs = ["prisma", "drizzle", r"\bpg\b", "pgx", "knex", "sequelize"]
        for lib in db_libs:
            if re.search(rf"""['"]{lib}['"/]""", content, re.IGNORECASE):
                violations.append(
                    "Architecture: Next.js route handlers must not contain business logic or DB access"
                )
                break

    # 7. Raw fetch('/api/ in component files (not lib/ or utils/)
    is_component = not ("/lib/" in normalized or "/utils/" in normalized)
    if is_component and re.search(r"""fetch\s*\(\s*['"`]/api/""", content):
        violations.append(
            "Codegen: Use generated API client from orval, not raw fetch"
        )

    return violations


def main() -> None:
    file_path = os.environ.get("CLAUDE_TOOL_INPUT_FILE_PATH", "")
    if not file_path:
        sys.exit(0)

    if not os.path.isfile(file_path):
        sys.exit(0)

    try:
        with open(file_path, encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
    except OSError:
        sys.exit(0)

    violations: list[str] = []

    if file_path.endswith(".go"):
        violations = check_go_file(file_path, content)
    elif file_path.endswith((".ts", ".tsx")):
        violations = check_ts_file(file_path, content)

    if violations:
        print(f"[masena-patterns] Violations in {os.path.basename(file_path)}:")
        for v in violations:
            print(f"  - {v}")

    sys.exit(0)


if __name__ == "__main__":
    main()
