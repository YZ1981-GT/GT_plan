"""附注公式来源信封、运行记录与手工值保护（S5；承接 S2 ADR-CCN-02）。"""
from __future__ import annotations

import asyncio
import inspect
import weakref
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Awaitable, Callable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _same_amount(left: Any, right: Any) -> bool:
    a, b = _decimal(left), _decimal(right)
    return a is not None and b is not None and abs(a - b) <= Decimal("0.005")


def quantize_amount(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def as_decimal(value: Any) -> Decimal | None:
    return _decimal(value)


def same_amount(left: Any, right: Any) -> bool:
    return _same_amount(left, right)


def _dialect_name(db: Any) -> str | None:
    try:
        bind = db.get_bind()
        if inspect.isawaitable(bind):
            close = getattr(bind, "close", None)
            if callable(close):
                close()
            return None
        return str(bind.dialect.name)
    except Exception:
        return None


async def table_available(db: AsyncSession, table: str) -> bool:
    dialect = _dialect_name(db)
    if dialect == "postgresql":
        return True
    if dialect != "sqlite":
        return False
    try:
        result = await db.execute(sa.text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"
        ), {"name": table})
        return result.scalar_one_or_none() == 1
    except Exception:
        return False


def note_formula_identity(
    note_section: str, key: str, formula_def: dict[str, Any], effective_slots: dict[str, Any],
) -> Any:
    from app.services.formula_provenance import definition_identity, note_definition_identity

    for slot_key in (f"{note_section}|{key}", key):
        slot = effective_slots.get(slot_key)
        if slot is not None:
            return note_definition_identity(slot)
    snapshot = {
        field: formula_def.get(field)
        for field in ("expression", "type", "category", "source", "binding_id")
        if formula_def.get(field) is not None
    }
    return definition_identity(
        version=int(formula_def.get("version") or 1),
        layer="project" if formula_def.get("source") in {"user", "user_formula"} else "preset",
        kind="formula_setting" if formula_def.get("source") in {"user", "user_formula"} else "preset",
        source_id=f"{note_section}:{key}",
        snapshot=snapshot or {"expression": str(formula_def.get("expression") or "")},
    )


def make_note_attempt(
    *, note_section: str, key: str, formula_def: dict[str, Any], effective_slots: dict[str, Any],
    run_id: UUID, computed_by: UUID | None, value: Any, status: str, error_code: str | None,
    inputs: list[Any],
) -> Any:
    from app.services.formula_provenance import build_attempt

    return build_attempt(
        domain="note",
        identity=note_formula_identity(note_section, key, formula_def, effective_slots),
        run_id=run_id,
        computed_at=datetime.now(timezone.utc),
        computed_by=computed_by,
        calc_version="note:1",
        inputs=inputs,
        calculated_value=value if status == "succeeded" else None,
        calculation_status=status,
        error_code=error_code,
    )


def save_note_final_provenance(
    provenance: dict[str, Any], addr_id: str, attempt: Any, *, value_state: str, applied: bool,
) -> None:
    from app.services.formula_provenance import advance_final_value

    provenance[addr_id] = advance_final_value(
        provenance.get(addr_id), value_slot="current", value_state=value_state,
        attempt=attempt, calculation_applied=applied,
    ).model_dump(mode="json")


def note_check_outcome(
    *, key: str, formula_def: dict[str, Any], expected: Decimal | None,
    actual: Any, reason: str | None,
) -> dict[str, Any]:
    from app.services.check_outcome import failed, not_executed, passed

    source = "note_formula"
    severity = str(formula_def.get("severity") or "warning")
    actual_value = _decimal(actual)
    if expected is None:
        return not_executed(
            rule_id=key, source=source, reason=reason or "公式未返回结果", severity=severity,
        ).to_dict()
    if actual_value is None:
        return not_executed(
            rule_id=key, source=source, reason="目标单元格没有可比较数值", severity=severity,
        ).to_dict()
    diff = abs(expected - actual_value)
    common = {
        "left": float(expected), "right": float(actual_value), "diff": float(diff),
        "severity": severity,
    }
    if diff <= Decimal("0.005"):
        return passed(rule_id=key, source=source, reason="校对一致", **common).to_dict()
    return failed(
        rule_id=key, source=source, reason="公式结果与当前值不一致", **common,
    ).to_dict()


def _stored_last_value(td: dict[str, Any], key: str, formula_def: dict[str, Any]) -> Decimal | None:
    direct = _decimal(formula_def.get("last_value"))
    if direct is not None:
        return direct
    values = td.get("_formula_last_values")
    return _decimal(values.get(key)) if isinstance(values, dict) else None


def matches_last_value(td: dict[str, Any], key: str, current: Any, formula_def: dict[str, Any]) -> bool:
    return _same_amount(current, _stored_last_value(td, key, formula_def))


def record_formula_last_value(
    td: dict[str, Any], key: str, formula_def: dict[str, Any], value: float,
) -> None:
    formula_def["last_value"] = value
    td.setdefault("_formula_last_values", {})[key] = value
    stored = td.get("_formulas")
    if isinstance(stored, dict) and isinstance(stored.get(key), dict):
        stored[key]["last_value"] = value
    users = td.get("_user_formulas")
    if isinstance(users, list):
        from app.services.note_formula_tables import formula_key, parse_formula_key
        for rec in users:
            if not isinstance(rec, dict):
                continue
            parsed = parse_formula_key(rec.get("target") or rec.get("target_cell"))
            if parsed is not None and formula_key(*parsed) == key:
                rec["last_value"] = value


_NOTE_RUN_LOCKS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _note_run_lock(project_id: UUID, year: int, section: str) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), str(project_id), int(year), section)
    lock = _NOTE_RUN_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _NOTE_RUN_LOCKS[key] = lock
    return lock


async def _advisory_lock(db: AsyncSession, project_id: UUID, year: int, section: str) -> None:
    if _dialect_name(db) != "postgresql":
        return
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"note_formula:{project_id}:{year}:{section}"},
    )


async def execute_with_run(
    body: Callable[..., Awaitable[dict[str, Any]]],
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
    *,
    affected_addr_ids: set[str] | None,
    cross_data: dict[str, Any] | None,
    regenerate: bool,
    triggered_by: UUID | None,
    trigger: str,
) -> dict[str, Any]:
    """按章节加 fence，并在调用方事务内登记可查询运行记录。"""
    from app.models.note_formula_models import NoteFormulaRun

    async with _note_run_lock(project_id, year, note_section):
        await _advisory_lock(db, project_id, year, note_section)
        run = None
        if await table_available(db, "note_formula_run"):
            run = NoteFormulaRun(
                project_id=project_id, year=year, note_section=note_section,
                trigger=trigger, triggered_by=triggered_by,
                started_at=datetime.now(timezone.utc),
            )
            db.add(run)
            await db.flush()
        try:
            result = await body(
                db, project_id, year, note_section,
                affected_addr_ids=affected_addr_ids,
                cross_data=cross_data,
                regenerate=regenerate,
                provenance_run_id=run.id if run is not None else None,
                provenance_computed_by=triggered_by,
            )
        except Exception as exc:
            if run is not None:
                run.status = "failed"
                run.failed_count = 1
                run.error_summary = f"{type(exc).__name__}: {exc}"[:4000]
                run.finished_at = datetime.now(timezone.utc)
                await db.flush()
            raise
        if run is None:
            return result
        rows = result.get("results") or []
        run.executed_count = int(result.get("executed") or 0)
        run.updated_count = int(result.get("updated") or 0)
        run.failed_count = sum(
            1 for item in rows
            if item.get("status") in {"failed", "error"}
            or (item.get("status") == "skipped" and item.get("reason") != "审核类公式不回填单元格")
        )
        run.status = "partial" if run.failed_count else "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        await db.flush()
        result["run_id"] = str(run.id)
        return result


class NoteProvenanceRecorder:
    """把执行器各分支的来源写入收口成一个调用，避免分支复制信封构造。"""

    def __init__(
        self, provenance: dict[str, Any] | None, *, note_section: str,
        effective_slots: dict[str, Any], run_id: UUID | None, computed_by: UUID | None,
    ) -> None:
        self.provenance = provenance
        self.note_section = note_section
        self.effective_slots = effective_slots
        self.run_id = run_id
        self.computed_by = computed_by

    @property
    def active(self) -> bool:
        return self.provenance is not None and self.run_id is not None

    def record(
        self, *, key: str, formula_def: dict[str, Any], addr_id: str,
        value: Any, status: str, error_code: str | None, inputs: list[Any],
        value_state: str, applied: bool,
    ) -> bool:
        if not self.active:
            return False
        attempt = make_note_attempt(
            note_section=self.note_section, key=key, formula_def=formula_def,
            effective_slots=self.effective_slots, run_id=self.run_id,
            computed_by=self.computed_by, value=value, status=status,
            error_code=error_code, inputs=inputs,
        )
        save_note_final_provenance(
            self.provenance, addr_id, attempt, value_state=value_state, applied=applied,
        )
        return True
