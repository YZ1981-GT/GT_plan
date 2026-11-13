"""高级查询版本向量采集内核（AQF §4）。"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.custom_query.execution_guard import cancellable_query
from app.services.custom_query.version_registry import (
    VersionDeclaration,
    declarations_for_builder,
    declarations_for_business,
)
from app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)
CONTENT_MAX_ROWS = 50_000
ROW_VERSION_MAX_ROWS = 200_000
CAPTURE_TIMEOUT_MS = 2_000


def _json_default(value: Any) -> Any:
    if isinstance(value, (UUID, date, datetime, Decimal, Enum)):
        return value.value if isinstance(value, Enum) else str(value)
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def digest_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VersionComponent:
    key: str
    table: str
    label: str
    basis: str
    scope: dict[str, Any]
    rows: int | None
    digest: str | None
    latest_update: str | None
    dataset: dict[str, Any] | None
    weak: bool
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VersionVector:
    components: tuple[VersionComponent, ...]
    vector_hash: str
    weak: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "components": [item.as_dict() for item in self.components],
            "vector_hash": self.vector_hash,
            "weak": self.weak,
        }

    @property
    def version_vector(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.components]


def vector_hash(components: Iterable[VersionComponent]) -> str:
    """摘要只含可比较字段，故 latest_update 的显示变化不会造成假 stale。"""
    payload = [
        [item.key, item.basis, item.rows, item.digest, item.error is not None]
        for item in sorted(components, key=lambda value: value.key)
    ]
    return digest_payload(payload)


def _table_map() -> dict[str, sa.Table]:
    from app.models.base import Base
    from app.models.consol_note_data_models import ConsolNoteData
    from app.models.consol_worksheet_data_models import ConsolWorksheetData
    from app.models.report_models import DisclosureNote
    from app.models.audit_platform_models import UnadjustedMisstatement, ReportLineMapping, AccountChart, Materiality
    from app.models.staff_models import StaffMember, WorkHour
    from app.models.core import Project
    # Explicit imports make model registration deterministic in a clean process.
    _ = (ConsolNoteData, ConsolWorksheetData, DisclosureNote, UnadjustedMisstatement, ReportLineMapping,
         AccountChart, Materiality, StaffMember, WorkHour, Project)
    return dict(Base.metadata.tables)


def _scope_parts(table: sa.Table, scope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    columns = table.c
    project_ids = scope.get("project_ids")
    project_id = scope.get("project_id")
    if "project_id" in columns:
        if project_ids is not None:
            ids = list(dict.fromkeys(str(item) for item in project_ids))
            if not ids:
                return "FALSE", {}
            names = []
            for index, value in enumerate(ids):
                name = f"pid_{index}"
                names.append(f":{name}")
                params[name] = value
            clauses.append(f"t.project_id IN ({','.join(names)})")
        elif project_id is not None:
            clauses.append("t.project_id = :project_id")
            params["project_id"] = str(project_id)
    if "year" in columns and scope.get("year") is not None:
        clauses.append("t.year = :year")
        params["year"] = int(scope["year"])
    if "work_date" in columns and scope.get("year") is not None:
        clauses.append("EXTRACT(YEAR FROM t.work_date) = :year")
        params["year"] = int(scope["year"])
    if "is_deleted" in columns:
        clauses.append("t.is_deleted = FALSE")
    if "applicable_standard" in columns and scope.get("standard"):
        clauses.append("(t.applicable_standard = :standard OR t.applicable_standard = :project_standard)")
        params["standard"] = str(scope["standard"])
        params["project_standard"] = f"project:{scope.get('project_id')}"
    if scope.get("company_code") and "company_code" in columns:
        clauses.append("t.company_code = :company_code")
        params["company_code"] = str(scope["company_code"])
    return (" AND ".join(clauses) or "TRUE"), params


def _scope_for_declaration(declaration: VersionDeclaration, scope: dict[str, Any]) -> dict[str, Any]:
    value = dict(scope)
    if declaration.scope_kind == "project":
        value.pop("year", None)
    if declaration.scope_kind == "standard":
        value.pop("year", None)
    return value


def _stringify_timestamp(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value is not None else None)


async def _dataset_component(db: AsyncSession, declaration: VersionDeclaration, scope: dict[str, Any]) -> VersionComponent | None:
    if scope.get("project_ids") is not None:
        ids = list(dict.fromkeys(str(item) for item in scope["project_ids"]))
        stmt = sa.select(LedgerDataset.project_id, LedgerDataset.year, LedgerDataset.id, LedgerDataset.activated_at).where(
            LedgerDataset.status == DatasetStatus.active,
            LedgerDataset.project_id.in_(ids),
        )
        if scope.get("year") is not None:
            stmt = stmt.where(LedgerDataset.year == int(scope["year"]))
        stmt = stmt.order_by(LedgerDataset.project_id, LedgerDataset.year,
                             LedgerDataset.activated_at.desc().nullslast(), LedgerDataset.created_at.desc())
        rows = (await db.execute(stmt)).all()
        selected: dict[tuple[str, int], tuple[Any, Any]] = {}
        for project, year, dataset_id, activated_at in rows:
            selected.setdefault((str(project), int(year)), (dataset_id, activated_at))
        digest = digest_payload([[key[0], key[1], str(value[0])] for key, value in sorted(selected.items())])
        latest = max((_stringify_timestamp(value[1]) for value in selected.values() if value[1] is not None), default=None)
        return VersionComponent(declaration.key, declaration.table, declaration.label, "dataset", scope,
                                len(selected), digest, latest, {"count": len(selected)}, False, None)
    project_id = scope.get("project_id")
    year = scope.get("year")
    if project_id is None or year is None:
        return VersionComponent(declaration.key, declaration.table, declaration.label, "dataset", scope,
                                0, digest_payload([]), None, None, False, "缺少项目或年度，无法采集生效数据集")
    stmt = sa.select(LedgerDataset.id, LedgerDataset.activated_at).where(
        LedgerDataset.project_id == str(project_id), LedgerDataset.year == int(year),
        LedgerDataset.status == DatasetStatus.active,
    ).order_by(LedgerDataset.activated_at.desc().nullslast(), LedgerDataset.created_at.desc()).limit(1)
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    dataset_id, activated_at = row
    return VersionComponent(declaration.key, declaration.table, declaration.label, "dataset", scope, 1,
                            str(dataset_id), _stringify_timestamp(activated_at),
                            {"id": str(dataset_id), "activated_at": _stringify_timestamp(activated_at)}, False, None)


async def _count_pg(db: AsyncSession, table: sa.Table, where: str, params: dict[str, Any]) -> int:
    result = await db.execute(sa.text(f"SELECT count(*) FROM {table.name} AS t WHERE {where}"), params)
    return int(result.scalar_one())


async def _aggregate_pg(db: AsyncSession, table: sa.Table, basis: str, where: str, params: dict[str, Any]) -> tuple[int, str | None, str | None]:
    latest = "max(t.updated_at)" if "updated_at" in table.c else "NULL"
    if basis == "content":
        expression = "md5(coalesce(string_agg(md5((to_jsonb(t) - 'created_at' - 'updated_at')::text), '' ORDER BY t.id), ''))"
    elif basis == "row_version":
        expression = "md5(coalesce(string_agg(t.id::text || ':' || t.xmin::text, ',' ORDER BY t.id), ''))"
    else:
        expression = "NULL"
    result = await db.execute(sa.text(f"SELECT count(*), {expression}, {latest} FROM {table.name} AS t WHERE {where}"), params)
    rows, digest, updated = result.one()
    return int(rows), str(digest) if digest is not None else None, _stringify_timestamp(updated)


async def _aggregate_sqlite(db: AsyncSession, table: sa.Table, basis: str, scope: dict[str, Any]) -> tuple[int, str | None, str | None]:
    clauses: list[Any] = []
    if "project_id" in table.c and scope.get("project_id") is not None:
        clauses.append(table.c.project_id == scope["project_id"])
    if "project_id" in table.c and scope.get("project_ids") is not None:
        clauses.append(table.c.project_id.in_(list(scope["project_ids"])))
    if "year" in table.c and scope.get("year") is not None:
        clauses.append(table.c.year == int(scope["year"]))
    if "is_deleted" in table.c:
        clauses.append(table.c.is_deleted.is_(False))
    if "standard" in scope and "applicable_standard" in table.c:
        clauses.append(sa.or_(table.c.applicable_standard == scope["standard"],
                              table.c.applicable_standard == f"project:{scope.get('project_id')}"))
    result = await db.execute(sa.select(table).where(*clauses).order_by(table.c.id if "id" in table.c else sa.text("1")))
    rows = [dict(row) for row in result.mappings().all()]
    latest_values = [row.get("updated_at") for row in rows if row.get("updated_at") is not None]
    latest = max(latest_values, key=str, default=None)
    if basis == "content":
        payload = [{key: value for key, value in row.items() if key not in {"created_at", "updated_at"}} for row in rows]
    else:
        payload = [{"id": row.get("id"), "row": row} for row in rows]
    return len(rows), digest_payload(payload), _stringify_timestamp(latest)


async def _table_component(db: AsyncSession, declaration: VersionDeclaration, scope: dict[str, Any]) -> VersionComponent:
    tables = _table_map()
    table = tables.get(declaration.table)
    if table is None:
        return VersionComponent(declaration.key, declaration.table, declaration.label, declaration.basis, scope,
                                None, None, None, None, declaration.basis == "timestamp", f"来源表「{declaration.table}」不存在")
    dialect = str(db.get_bind().dialect.name).lower()
    try:
        async with db.begin_nested():
            async with cancellable_query(db, CAPTURE_TIMEOUT_MS):
                if dialect in {"postgres", "postgresql"}:
                    where, params = _scope_parts(table, scope)
                    rows = await _count_pg(db, table, where, params)
                    basis = declaration.basis
                    if basis == "content" and rows > CONTENT_MAX_ROWS:
                        basis = "row_version"
                    if basis == "row_version" and rows > ROW_VERSION_MAX_ROWS:
                        basis = "timestamp"
                    count, digest, latest = await _aggregate_pg(db, table, basis, where, params)
                else:
                    basis = declaration.basis
                    count, digest, latest = await _aggregate_sqlite(db, table, basis, scope)
                    if basis == "content" and count > CONTENT_MAX_ROWS:
                        basis = "row_version"
                    if basis == "row_version" and count > ROW_VERSION_MAX_ROWS:
                        basis = "timestamp"
                    if basis == "timestamp":
                        # SQLite 没有 xmin，按现有内容的最新更新时间作明确的弱判据。
                        digest = digest_payload([count, latest])
                return VersionComponent(declaration.key, declaration.table, declaration.label, basis, scope,
                                        count, digest, latest, None, basis == "timestamp", None)
    except Exception as exc:  # noqa: BLE001 - 单个分量失败不得影响查询
        logger.warning("高级查询版本分量采集失败 %s: %s", declaration.key, exc)
        return VersionComponent(declaration.key, declaration.table, declaration.label, declaration.basis, scope,
                                None, None, None, None, declaration.basis == "timestamp", _capture_error(exc))


def _capture_error(exc: BaseException) -> str:
    text = str(exc).strip()
    if "QUERY_TIMEOUT" in text or "57014" in text or "timeout" in text.lower():
        return "采集超时"
    return f"采集失败：{text[:160] or type(exc).__name__}"


async def capture_component(db: AsyncSession, declaration: VersionDeclaration, scope: dict[str, Any]) -> VersionComponent:
    """采集单个分量；每个分量拥有独立 SAVEPOINT。"""
    if declaration.basis == "scope":
        value = {key: scope.get(key) for key in sorted(scope)}
        return VersionComponent(declaration.key, declaration.table, declaration.label, "scope", scope,
                                None, digest_payload(value), None, None, False, None)
    if declaration.basis == "dataset":
        try:
            async with db.begin_nested():
                async with cancellable_query(db, CAPTURE_TIMEOUT_MS):
                    component = await _dataset_component(db, declaration, scope)
            if component is not None:
                return component
        except Exception as exc:  # active dataset 失败也应隔离
            return VersionComponent(declaration.key, declaration.table, declaration.label, "dataset", scope,
                                    None, None, None, None, False, _capture_error(exc))
        if declaration.fallback_table:
            fallback = VersionDeclaration(declaration.key, declaration.fallback_table, declaration.label,
                                          "row_version", declaration.scope_kind)
            component = await _table_component(db, fallback, scope)
            return VersionComponent(component.key, component.table, f"{component.label}（未有生效数据集）",
                                    component.basis, component.scope, component.rows, component.digest,
                                    component.latest_update, component.dataset, component.weak, component.error)
    return await _table_component(db, declaration, _scope_for_declaration(declaration, scope))


async def capture_version_vector(
    db: AsyncSession,
    declarations: Iterable[VersionDeclaration],
    *,
    scope: dict[str, Any] | None = None,
    include_scope: bool = True,
) -> VersionVector:
    """按声明顺序采集版本向量，重复表声明按 key 去重。"""
    query_scope = dict(scope or {})
    unique: dict[str, VersionDeclaration] = {item.key: item for item in declarations}
    if include_scope:
        unique.setdefault("scope", VersionDeclaration("scope", "scope", "查询范围", "scope", "scope"))
    components = tuple(await _capture_in_order(db, unique.values(), query_scope))
    return VersionVector(components, vector_hash(components), any(item.weak for item in components))


async def _capture_in_order(db: AsyncSession, declarations: Iterable[VersionDeclaration], scope: dict[str, Any]) -> list[VersionComponent]:
    result: list[VersionComponent] = []
    for declaration in declarations:
        result.append(await capture_component(db, declaration, scope))
    return result


async def capture_business_vector(db: AsyncSession, source: str, *, scope: dict[str, Any], acnr_targets: bool = False) -> VersionVector:
    return await capture_version_vector(db, declarations_for_business(source, acnr_targets=acnr_targets), scope=scope)


async def capture_builder_vector(db: AsyncSession, tables: Iterable[str], *, scope: dict[str, Any]) -> VersionVector:
    return await capture_version_vector(db, declarations_for_builder(tuple(tables)), scope=scope)


__all__ = [
    "CONTENT_MAX_ROWS", "ROW_VERSION_MAX_ROWS", "CAPTURE_TIMEOUT_MS", "VersionComponent", "VersionVector",
    "canonical_json", "digest_payload", "vector_hash", "capture_component", "capture_version_vector",
    "capture_business_vector", "capture_builder_vector",
]


async def recapture_vector(
    db: AsyncSession,
    components: list[dict[str, Any]],
) -> list[VersionComponent]:
    """按已有分量的 key/table/basis/scope 重新采集一次（用于过期判定，R3.1/R3.2）。

    不重新解析数据源——即使数据源已下线也能判定。
    """
    result = []
    for item in components:
        decl = VersionDeclaration(
            key=item.get("key", ""),
            table=item.get("table", ""),
            label=item.get("label", ""),
            basis=item.get("basis", "content"),
            scope_kind="project",
        )
        scope = dict(item.get("scope") or {})
        comp = await capture_component(db, decl, scope)
        result.append(comp)
    return result
