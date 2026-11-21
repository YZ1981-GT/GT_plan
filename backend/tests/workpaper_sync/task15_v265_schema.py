"""V265 evidence overlay for the Task 15 PostgreSQL scratch schema.

Task 15 intentionally starts from the V151 content-mutation baseline. The production
ORM has since gained V265 content-version evidence columns, so the scratch schema must
apply the same migration fragment before SQLAlchemy flushes a content version. The
fragment is read from the real migration file; it never writes the shared/public schema.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.migration_runner import MigrationRunner


async def apply_v265_content_evidence_overlay(
    engine: Any,
    *,
    backend_root: Path,
) -> dict[str, list[str] | int]:
    """Apply and verify only V265 statements for working_paper_content_version."""
    migration = backend_root / "migrations" / "V265__add_export_unit_policy_columns.sql"
    statements = [
        statement
        for statement in MigrationRunner._split_sql_statements(
            migration.read_text(encoding="utf-8")
        )
        if "working_paper_content_version" in statement.lower()
    ]
    for statement in statements:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(statement)

    async with engine.connect() as conn:
        columns = list(
            (
                await conn.exec_driver_sql(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'working_paper_content_version' "
                    "AND column_name IN ('export_surface_class', 'unit_policy_snapshot', "
                    "'unit_policy_digest', 'source_storage_unit') "
                    "ORDER BY column_name"
                )
            ).scalars().all()
        )
        constraints = list(
            (
                await conn.exec_driver_sql(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'working_paper_content_version'::regclass "
                    "AND conname = 'ck_wpcv_export_unit_evidence'"
                )
            ).scalars().all()
        )
    expected_columns = [
        "export_surface_class",
        "source_storage_unit",
        "unit_policy_digest",
        "unit_policy_snapshot",
    ]
    if len(statements) < 6 or columns != expected_columns or constraints != [
        "ck_wpcv_export_unit_evidence"
    ]:
        raise RuntimeError(
            "V265 scratch schema overlay 不完整："
            f"statements={len(statements)}, columns={columns}, constraints={constraints}"
        )
    return {"statement_count": len(statements), "columns": columns, "constraints": constraints}
