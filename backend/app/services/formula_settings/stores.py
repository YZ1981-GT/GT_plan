"""各域存储适配（design §12）。

* 报表域：``report_config`` —— 准则行 = 全局，``project:{id}`` 行 = 本项目适配。
* 其余域：``formula_setting`` —— layer=global / project。
* 模板层（全部域）：``formula_setting`` layer=template（见 ``templates``）。

订阅模板以「物化」实现：模板定义写成本项目层行，``base_origin='template'`` 记上游来源。
因此所有消费方只需「本项目行 → 全局 → 系统预设」三层，旧的「项目行优先」读取方零改动。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaSetting
from app.models.report_models import FinancialReportType, ReportConfig
from app.services.formula_settings.definitions import (
    ANY_SCOPE,
    DISABLED_KEY,
    exec_hash,
    get_spec,
    is_disabled,
)
from app.services.formula_settings.sync import LocalState

REPORT_FIELDS = ("formula", "aje_formula", "rje_formula", "formula_category",
                 "formula_description", "formula_source")
REPORT_STRUCTURE = ("row_number", "row_name", "indent_level", "is_total_row", "parent_row_code")


@dataclass
class SlotRecord:
    """某层上一个公式位的定义与元数据。"""

    slot_key: str
    definition: dict | None
    version: int = 1
    label: str = ""
    base_definition: dict | None = None
    base_version: int | None = None
    pinned: bool = False
    base_origin: str | None = None
    base_template_id: uuid.UUID | None = None
    row_id: uuid.UUID | None = None
    structure: dict = field(default_factory=dict)
    #: 所在层：global / preset / project / template
    layer: str = ""

    def local_state(self) -> LocalState:
        return LocalState(self.definition, self.base_definition, self.base_version, self.pinned)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DomainStore:
    """存储适配基类。子类实现全局层与本项目层的读写。"""

    domain: str = ""

    @property
    def spec(self):
        return get_spec(self.domain)

    async def project_scope(self, db: AsyncSession, project_id: uuid.UUID) -> str:
        """项目在本域的全局作用范围（与批量口径 ``projects.scope_of`` 同一函数）。"""
        if self.spec.scope_kind == "any":
            return ANY_SCOPE
        from app.models.core import Project
        from app.services.formula_settings.projects import scope_of

        row = (await db.execute(
            sa.select(Project.template_type, Project.report_scope).where(
                Project.id == project_id, Project.is_deleted == sa.false())
        )).one_or_none()
        if row is None:
            return scope_of(self.domain, None, None) if self.spec.scope_kind == "template_type" else "enterprise"
        return scope_of(self.domain, row[0], row[1])

    #: 全局层是否有通用作用范围 ``*``（精确范围优先、回退 ``*``）
    supports_any_scope: bool = True

    def slot_label(self, slot_key: str, structure: dict | None = None) -> str:
        return slot_key

    async def list_global(self, db: AsyncSession, scope: str) -> dict[str, SlotRecord]:
        raise NotImplementedError

    async def list_global_exact(self, db: AsyncSession, scope: str) -> dict[str, SlotRecord]:
        """只取恰好该作用范围的全局行（不回退 ``*``）；CAS 与发布写入按它判断。"""
        return await self.list_global(db, scope)

    async def list_project_many(self, db: AsyncSession,
                                project_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, SlotRecord]]:
        return {pid: await self.list_project(db, pid) for pid in project_ids}

    async def list_project(self, db: AsyncSession, project_id: uuid.UUID) -> dict[str, SlotRecord]:
        raise NotImplementedError

    async def write_global(self, db: AsyncSession, scope: str, slot_key: str, definition: dict | None, *,
                           user_id: uuid.UUID | None, label: str = "", structure: dict | None = None) -> int:
        raise NotImplementedError

    async def write_project(self, db: AsyncSession, project_id: uuid.UUID, slot_key: str, *,
                            definition: dict, base_definition: dict | None, base_version: int | None,
                            pinned: bool, base_origin: str | None, base_template_id: uuid.UUID | None,
                            user_id: uuid.UUID | None, label: str = "",
                            structure: dict | None = None) -> None:
        raise NotImplementedError

    async def delete_project(self, db: AsyncSession, project_id: uuid.UUID, slot_key: str) -> None:
        raise NotImplementedError

    async def system_presets(self, db: AsyncSession, scope: str) -> dict[str, SlotRecord]:
        """系统预设层（只读）；默认无。"""
        return {}


# ── 报表域：report_config ─────────────────────────────────────────────────────

_REPORT_TYPE_LABELS = {
    "balance_sheet": "资产负债表", "income_statement": "利润表", "cash_flow_statement": "现金流量表",
    "equity_statement": "权益变动表", "cash_flow_supplement": "现金流附表", "impairment_provision": "资产减值准备表",
}


def report_slot_key(report_type: Any, row_code: str) -> str:
    rt = report_type.value if hasattr(report_type, "value") else str(report_type)
    return f"{rt}:{row_code}"


def parse_report_slot(slot_key: str) -> tuple[FinancialReportType, str]:
    rt, _, code = slot_key.partition(":")
    if not code:
        raise ValueError(f"报表公式位格式应为「报表类型:行次」：{slot_key}")
    return FinancialReportType(rt), code


def _report_definition(row: ReportConfig) -> dict:
    return {f: getattr(row, f, None) for f in REPORT_FIELDS}


def _report_structure(row: ReportConfig) -> dict:
    return {f: getattr(row, f, None) for f in REPORT_STRUCTURE}


def _report_label(row: ReportConfig) -> str:
    rt = row.report_type.value if hasattr(row.report_type, "value") else str(row.report_type)
    return f"{_REPORT_TYPE_LABELS.get(rt, rt)} {row.row_code} {row.row_name or ''}".strip()


def _apply_report_definition(row: ReportConfig, definition: dict | None) -> None:
    disabled = is_disabled(definition)
    for f in REPORT_FIELDS:
        value = None if disabled or definition is None else definition.get(f)
        if isinstance(value, str):
            value = value.strip() or None
        setattr(row, f, value)


class ReportStore(DomainStore):
    domain = "report"
    supports_any_scope = False

    def _record(self, row: ReportConfig) -> SlotRecord:
        return SlotRecord(
            slot_key=report_slot_key(row.report_type, row.row_code),
            definition=_report_definition(row),
            version=row.formula_version or 1,
            label=_report_label(row),
            base_definition=row.base_definition,
            base_version=row.base_version,
            pinned=bool(row.pinned),
            base_origin=row.base_origin,
            base_template_id=row.base_template_id,
            row_id=row.id,
            structure=_report_structure(row),
            layer="project" if (row.applicable_standard or "").startswith("project:") else "global",
        )

    async def _rows(self, db: AsyncSession, standard: str, *, include_deleted: bool = False):
        q = sa.select(ReportConfig).where(ReportConfig.applicable_standard == standard)
        if not include_deleted:
            q = q.where(ReportConfig.is_deleted == sa.false())
        return list((await db.execute(q)).scalars().all())

    async def list_global(self, db, scope):
        return {r.slot_key: r for r in map(self._record, await self._rows(db, scope))}

    async def list_project(self, db, project_id):
        return {r.slot_key: r for r in map(self._record, await self._rows(db, f"project:{project_id}"))}

    async def list_project_many(self, db, project_ids):
        if not project_ids:
            return {}
        stds = {f"project:{pid}": pid for pid in project_ids}
        rows = (await db.execute(sa.select(ReportConfig).where(
            ReportConfig.applicable_standard.in_(list(stds)), ReportConfig.is_deleted == sa.false()
        ))).scalars().all()
        out: dict[uuid.UUID, dict[str, SlotRecord]] = {pid: {} for pid in project_ids}
        for row in rows:
            rec = self._record(row)
            out[stds[row.applicable_standard]][rec.slot_key] = rec
        return out

    async def _find(self, db: AsyncSession, standard: str, slot_key: str) -> ReportConfig | None:
        rt, code = parse_report_slot(slot_key)
        rows = (await db.execute(sa.select(ReportConfig).where(
            ReportConfig.applicable_standard == standard,
            ReportConfig.report_type == rt,
            ReportConfig.row_code == code,
        ))).scalars().all()
        live = [r for r in rows if not r.is_deleted]
        return live[0] if live else (rows[0] if rows else None)

    def _new_row(self, slot_key: str, standard: str, structure: dict, label: str) -> ReportConfig:
        rt, code = parse_report_slot(slot_key)
        return ReportConfig(
            report_type=rt, row_code=code, applicable_standard=standard,
            row_number=int(structure.get("row_number") or 0),
            row_name=str(structure.get("row_name") or label or code),
            indent_level=int(structure.get("indent_level") or 0),
            is_total_row=bool(structure.get("is_total_row") or False),
            parent_row_code=structure.get("parent_row_code"),
            formula_version=1,
        )

    async def write_global(self, db, scope, slot_key, definition, *, user_id, label="", structure=None):
        row = await self._find(db, scope, slot_key)
        if definition is None:
            if row is None or row.is_deleted:
                return 0
            row.is_deleted = True
            row.formula_version = (row.formula_version or 1) + 1
            row.updated_by, row.updated_at = user_id, _now()
            return row.formula_version
        if row is None:
            st = dict(structure or definition.get("_structure") or {})
            row = self._new_row(slot_key, scope, st, label)
            _apply_report_definition(row, definition)
            row.updated_by = user_id
            db.add(row)
            await db.flush()
            return 1
        row.is_deleted = False
        _apply_report_definition(row, definition)
        row.formula_version = (row.formula_version or 1) + 1
        row.updated_by, row.updated_at = user_id, _now()
        return row.formula_version

    async def write_project(self, db, project_id, slot_key, *, definition, base_definition, base_version,
                            pinned, base_origin, base_template_id, user_id, label="", structure=None):
        std = f"project:{project_id}"
        row = await self._find(db, std, slot_key)
        if row is None:
            st = dict(structure or {})
            if not st:
                scope = await self.project_scope(db, project_id)
                g = await self._find(db, scope, slot_key)
                st = _report_structure(g) if g is not None else dict((definition or {}).get("_structure") or {})
            row = self._new_row(slot_key, std, st, label)
            db.add(row)
        else:
            row.formula_version = (row.formula_version or 1) + (0 if row.is_deleted else 1)
            row.is_deleted = False
        _apply_report_definition(row, definition)
        row.base_definition = dict(base_definition) if base_definition is not None else None
        row.base_version = base_version
        row.pinned = bool(pinned)
        row.base_origin = base_origin
        row.base_template_id = base_template_id
        row.updated_by, row.updated_at = user_id, _now()
        row.is_stale = False
        await db.flush()

    async def delete_project(self, db, project_id, slot_key):
        rt, code = parse_report_slot(slot_key)
        await db.execute(sa.delete(ReportConfig).where(
            ReportConfig.applicable_standard == f"project:{project_id}",
            ReportConfig.report_type == rt,
            ReportConfig.row_code == code,
        ))


# ── 通用域：formula_setting ───────────────────────────────────────────────────


def _setting_record(row: FormulaSetting) -> SlotRecord:
    return SlotRecord(
        slot_key=row.slot_key,
        definition=dict(row.definition or {}),
        version=row.version or 1,
        label=row.slot_label or row.slot_key,
        base_definition=row.base_definition,
        base_version=row.base_version,
        pinned=bool(row.pinned),
        base_origin=row.base_origin,
        base_template_id=row.base_template_id,
        row_id=row.id,
        structure=dict((row.definition or {}).get("_structure") or {}),
        layer=row.layer,
    )


class SettingStore(DomainStore):
    """全局层与本项目层都在 ``formula_setting``。"""

    def __init__(self, domain: str) -> None:
        self.domain = domain

    def _q(self, layer: str):
        return sa.select(FormulaSetting).where(
            FormulaSetting.domain == self.domain,
            FormulaSetting.layer == layer,
            FormulaSetting.is_deleted == sa.false(),
        )

    async def list_global(self, db, scope):
        scopes = [ANY_SCOPE] if scope == ANY_SCOPE else [ANY_SCOPE, scope]
        rows = (await db.execute(self._q("global").where(FormulaSetting.scope.in_(scopes)))).scalars().all()
        out: dict[str, SlotRecord] = {}
        # 精确作用范围覆盖通用（*）
        for row in sorted(rows, key=lambda r: 0 if r.scope == ANY_SCOPE else 1):
            out[row.slot_key] = _setting_record(row)
        return out

    async def list_global_exact(self, db, scope) -> dict[str, SlotRecord]:
        rows = (await db.execute(self._q("global").where(FormulaSetting.scope == scope))).scalars().all()
        return {r.slot_key: _setting_record(r) for r in rows}

    async def list_project(self, db, project_id):
        rows = (await db.execute(self._q("project").where(FormulaSetting.project_id == project_id))).scalars().all()
        return {r.slot_key: _setting_record(r) for r in rows}

    async def list_project_many(self, db, project_ids):
        out: dict[uuid.UUID, dict[str, SlotRecord]] = {pid: {} for pid in project_ids}
        if not project_ids:
            return out
        rows = (await db.execute(self._q("project").where(
            FormulaSetting.project_id.in_(list(project_ids))
        ))).scalars().all()
        for r in rows:
            out[r.project_id][r.slot_key] = _setting_record(r)
        return out

    async def _find(self, db, layer: str, slot_key: str, *, scope: str | None = None,
                    project_id: uuid.UUID | None = None) -> FormulaSetting | None:
        q = self._q(layer).where(FormulaSetting.slot_key == slot_key)
        if scope is not None:
            q = q.where(FormulaSetting.scope == scope)
        if project_id is not None:
            q = q.where(FormulaSetting.project_id == project_id)
        return (await db.execute(q)).scalars().first()

    async def write_global(self, db, scope, slot_key, definition, *, user_id, label="", structure=None):
        row = await self._find(db, "global", slot_key, scope=scope)
        if definition is None:
            if row is None:
                return 0
            row.is_deleted = True
            row.version = (row.version or 1) + 1
            row.updated_by, row.updated_at = user_id, _now()
            return row.version
        payload = dict(definition)
        if structure:
            payload["_structure"] = dict(structure)
        if row is None:
            row = FormulaSetting(domain=self.domain, layer="global", scope=scope, slot_key=slot_key,
                                 slot_label=label or slot_key, definition=payload, version=1,
                                 created_by=user_id, updated_by=user_id)
            row.definition_hash = exec_hash(self.domain, payload)
            db.add(row)
            await db.flush()
            return 1
        row.definition = payload
        row.definition_hash = exec_hash(self.domain, payload)
        row.slot_label = label or row.slot_label
        row.version = (row.version or 1) + 1
        row.updated_by, row.updated_at = user_id, _now()
        return row.version

    async def write_project(self, db, project_id, slot_key, *, definition, base_definition, base_version,
                            pinned, base_origin, base_template_id, user_id, label="", structure=None):
        row = await self._find(db, "project", slot_key, project_id=project_id)
        payload = dict(definition or {DISABLED_KEY: True})
        if structure:
            payload["_structure"] = dict(structure)
        if row is None:
            row = FormulaSetting(domain=self.domain, layer="project", scope="", project_id=project_id,
                                 slot_key=slot_key, slot_label=label or slot_key, version=1,
                                 created_by=user_id)
            db.add(row)
        else:
            row.version = (row.version or 1) + 1
            row.slot_label = label or row.slot_label
        row.definition = payload
        row.definition_hash = exec_hash(self.domain, payload)
        row.base_definition = dict(base_definition) if base_definition is not None else None
        row.base_version = base_version
        row.pinned = bool(pinned)
        row.base_origin = base_origin
        row.base_template_id = base_template_id
        row.updated_by, row.updated_at = user_id, _now()
        await db.flush()

    async def delete_project(self, db, project_id, slot_key):
        await db.execute(sa.delete(FormulaSetting).where(
            FormulaSetting.domain == self.domain,
            FormulaSetting.layer == "project",
            FormulaSetting.project_id == project_id,
            FormulaSetting.slot_key == slot_key,
        ))


_STORES: dict[str, DomainStore] = {}


def register_store(store: DomainStore) -> DomainStore:
    _STORES[store.domain] = store
    return store


def get_store(domain: str) -> DomainStore:
    get_spec(domain)  # 未知域 → UnknownDomain
    store = _STORES.get(domain)
    if store is None:
        if domain == "report":
            store = ReportStore()
        elif domain in ("wp", "note", "consol_note"):
            from app.services.formula_settings import domain_stores

            store = {"wp": domain_stores.WpStore, "note": domain_stores.NoteStore,
                     "consol_note": domain_stores.ConsolNoteStore}[domain]()
        else:
            store = SettingStore(domain)
        store = register_store(store)
    return store
