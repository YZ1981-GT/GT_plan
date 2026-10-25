"""项目集团关系字段的规范化、两口径同步与派生链接（spec consol-tree-three-code-autobuild）。

集团关系 = 上级企业（名称/代码）+ 最终控制方（名称/代码）+ 与上级关系。它描述的是**企业**，
不是某个项目：同企业代码、同审计年度的合并项目与单户项目必须共享同一份集团关系（需求 1.8）。

本模块职责：
- ``prepare_group_fields``：建项/保存基本信息前的规范化与补齐（空串归 None、USCC 校验、
  关系取值校验；上级=本企业按顶层处理；建项时继承另一口径项目；按上级补控制方；按名称补关系默认）。
- ``propagate_to_counterpart``：保存后把集团关系写到另一口径项目（含其向导回填数据）。
- ``sync_group_links``：任何改变集团结构的写路径之后，按三码重算整年的派生链接 ``parent_project_id``。

同企业另一口径项目的定位**委托** ``parent_company_scope`` 的两个 resolver（不自拼三条件）。
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.group_relation import (
    RELATION_LABELS,
    SELF_REFERENCE_NOTICES,
    effective_parent_code,
    infer_relation_from_name,
    normalize_relation,
    self_reference_kind,
)
from app.services.note_section_catalog import normalize_report_scope
from app.services.parent_company_scope import (
    resolve_consolidated_sibling,
    resolve_parent_standalone_project,
)
from app.services.uscc_validator import validate_uscc

# 集团关系字段（顺序即向导表单顺序）
GROUP_FIELDS: tuple[str, ...] = (
    "parent_company_name",
    "parent_company_code",
    "relation_to_parent",
    "ultimate_company_name",
    "ultimate_company_code",
)

_SCOPE_LABELS = {"consolidated": "合并", "standalone": "单户"}


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _has_effective_parent(data: Any) -> bool:
    return effective_parent_code(getattr(data, "company_code", None), data.parent_company_code) is not None


def normalize_group_fields(data: Any) -> None:
    """就地规范化并校验集团关系字段（需求 1.3~1.5）。

    - 五个字段空串/空白 ⇒ None，其余去首尾空白；
    - 上级代码、控制方代码非空须通过统一社会信用代码校验；
    - 上级代码**可以**等于本企业代码：表示本企业就是上级企业（前端保存前已请用户确认），
      照存不拒绝，但不当作上级使用（``group_relation.effective_parent_code``）；
    - 与上级关系只能是子公司/分公司（中英文均可），没有有效上级时强制置 None。

    校验失败抛 ``HTTPException(422)``，detail 为中文原因。
    """
    for field in GROUP_FIELDS:
        setattr(data, field, _blank_to_none(getattr(data, field, None)))

    for field, label in (
        ("parent_company_code", "上级企业代码"),
        ("ultimate_company_code", "最终控制方代码"),
    ):
        code = getattr(data, field)
        if code is None:
            continue
        ok, err = validate_uscc(code)
        if not ok:
            raise HTTPException(status_code=422, detail=f"{label}：{err}")

    try:
        relation = normalize_relation(data.relation_to_parent)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    data.relation_to_parent = relation if _has_effective_parent(data) else None


async def find_counterpart(
    db: AsyncSession,
    *,
    project_id: UUID | None,
    company_code: str | None,
    audit_year: int | None,
    report_scope: str | None,
) -> Project | None:
    """同企业代码、同年度的另一口径项目（合并 ↔ 单户）。

    委托 ``parent_company_scope`` 的两个 resolver（三条件在那里写死，本层不重复），
    字段不齐时 resolver 自己返回 None。
    """
    probe = SimpleNamespace(
        id=project_id,
        company_code=company_code,
        audit_year=audit_year,
        report_scope=report_scope,
    )
    if normalize_report_scope(report_scope) == "consolidated":
        return await resolve_parent_standalone_project(db, probe)  # type: ignore[arg-type]
    return await resolve_consolidated_sibling(db, probe)  # type: ignore[arg-type]


def _counterpart_label(counterpart: Project) -> str:
    scope = _SCOPE_LABELS.get(normalize_report_scope(counterpart.report_scope), "单户")
    name = counterpart.client_name or counterpart.name or ""
    return f"{scope}项目「{name}」"


def inherit_from_counterpart(data: Any, counterpart: Project | None) -> list[str]:
    """建项时：本次未填的集团关系字段从另一口径项目带入（只填空，不覆盖）。"""
    if counterpart is None:
        return []
    inherited = False
    if data.parent_company_code is None and _blank_to_none(counterpart.parent_company_code):
        data.parent_company_code = counterpart.parent_company_code
        data.parent_company_name = data.parent_company_name or counterpart.parent_company_name
        if data.relation_to_parent is None:
            data.relation_to_parent = counterpart.relation_to_parent
        inherited = True
    elif (
        data.relation_to_parent is None
        and data.parent_company_code is not None
        and data.parent_company_code == _blank_to_none(counterpart.parent_company_code)
        and counterpart.relation_to_parent
    ):
        data.relation_to_parent = counterpart.relation_to_parent
        inherited = True
    if data.ultimate_company_code is None and _blank_to_none(counterpart.ultimate_company_code):
        data.ultimate_company_code = counterpart.ultimate_company_code
        data.ultimate_company_name = data.ultimate_company_name or counterpart.ultimate_company_name
        inherited = True
    if not inherited:
        return []
    return [f"已从同企业的{_counterpart_label(counterpart)}带入集团关系"]


async def infer_ultimate_from_parent(
    db: AsyncSession, data: Any, audit_year: int | None
) -> list[str]:
    """控制方代码为空而上级已建项时，沿用上级企业**已填写**的控制方代码（需求 1.9）。

    只抄落库值、不猜：上级自己也没填控制方时保持为空（「上级没有上级 ⇒ 上级即控制方」
    这类推断在上级漏填上级代码时会写出错数，且之后不会被纠正）。
    上级=本企业（本企业就是上级企业）时没有可沿用的上级，不补。
    """
    parent_code = effective_parent_code(getattr(data, "company_code", None), data.parent_company_code)
    if data.ultimate_company_code is not None or parent_code is None:
        return []
    stmt = sa.select(Project).where(
        Project.company_code == parent_code,
        Project.is_deleted == sa.false(),
    )
    if audit_year is not None:
        stmt = stmt.where(Project.audit_year == audit_year)
    rows = list((await db.execute(stmt)).scalars().all())
    # 单户项目优先（集团关系以单户为准，与企业树口径一致）
    rows.sort(key=lambda p: 0 if normalize_report_scope(p.report_scope) == "standalone" else 1)
    for upper in rows:
        ultimate = _blank_to_none(upper.ultimate_company_code)
        if ultimate is None:
            continue
        if ultimate == _blank_to_none(getattr(data, "company_code", None)):
            return []
        data.ultimate_company_code = ultimate
        if data.ultimate_company_name is None:
            data.ultimate_company_name = upper.ultimate_company_name
        return [f"最终控制方已按上级企业补齐为 {upper.ultimate_company_name or ultimate}"]
    return []


def default_relation_by_name(data: Any) -> list[str]:
    """有有效上级而关系未选时，按企业名称补默认关系（需求 2.3）。"""
    if not _has_effective_parent(data) or data.relation_to_parent is not None:
        return []
    data.relation_to_parent = infer_relation_from_name(getattr(data, "client_name", None))
    label = RELATION_LABELS[data.relation_to_parent]
    return [f"与上级关系未填写，已按企业名称默认为「{label}」"]


async def prepare_group_fields(
    db: AsyncSession,
    data: Any,
    *,
    project_id: UUID | None,
    report_scope: str | None,
    inherit: bool,
    previous_parent_code: str | None = None,
    previous_ultimate_code: str | None = None,
) -> list[str]:
    """建项/保存基本信息前处理集团关系字段，返回给用户看的说明（notices）。

    - ``inherit=True``（建项）：先从另一口径项目带入空字段。保存已有项目时不带入
      （用户清空视为有意操作），改由 ``propagate_to_counterpart`` 外推。
    - 控制方代码只在「新建」或「上级代码有变化」时按上级补齐 —— 上级没变而控制方为空，
      视为用户有意清空，不再回填。
    - 有有效上级而关系为空时按名称补默认（不变式：有有效上级 ⇔ 有关系）。
    - 上级=本企业（需求 1.5）：说明按「本企业就是上级企业」/「本企业即为最终控制方」处理；
      只在新建或这层含义变化时说一次，同一组代码再次保存不重复。
    """
    normalize_group_fields(data)
    notices: list[str] = []
    audit_year = getattr(data, "audit_year", None)
    company_code = _blank_to_none(getattr(data, "company_code", None))
    if inherit:
        counterpart = await find_counterpart(
            db,
            project_id=project_id,
            company_code=company_code,
            audit_year=audit_year,
            report_scope=report_scope,
        )
        notices += inherit_from_counterpart(data, counterpart)
    parent_changed = inherit or data.parent_company_code != _blank_to_none(previous_parent_code)
    if parent_changed:
        notices += await infer_ultimate_from_parent(db, data, audit_year)
    notices += default_relation_by_name(data)

    kind = self_reference_kind(company_code, data.parent_company_code, data.ultimate_company_code)
    previous_kind = None if inherit else self_reference_kind(
        company_code, previous_parent_code, previous_ultimate_code
    )
    if kind is not None and kind != previous_kind:
        notices.append(SELF_REFERENCE_NOTICES[kind])
    return notices


def _group_values(obj: Any) -> dict[str, str | None]:
    return {f: _blank_to_none(getattr(obj, f, None)) for f in GROUP_FIELDS}


def apply_group_values(project: Project, values: dict[str, str | None]) -> bool:
    """把集团关系写到项目的 ORM 列与向导回填数据（深拷贝后整体重赋值，保证 JSONB 变更被追踪）。

    返回是否有变化。只处理 ``GROUP_FIELDS`` 内的键。
    """
    values = {k: v for k, v in values.items() if k in GROUP_FIELDS}
    changed = False
    for key, value in values.items():
        if _blank_to_none(getattr(project, key, None)) != value:
            setattr(project, key, value)
            changed = True
    if isinstance(project.wizard_state, dict):
        ws = copy.deepcopy(project.wizard_state)
        basic = ws.get("steps", {}).get("basic_info", {})
        data = basic.get("data") if isinstance(basic, dict) else None
        if isinstance(data, dict) and any(data.get(k) != v for k, v in values.items()):
            data.update(values)
            project.wizard_state = ws
            changed = True
    return changed


async def propagate_to_counterpart(db: AsyncSession, project: Project) -> list[str]:
    """保存后：把本项目的集团关系写到另一口径项目（ORM 列 + 向导回填数据，需求 1.8）。"""
    counterpart = await find_counterpart(
        db,
        project_id=project.id,
        company_code=_blank_to_none(project.company_code),
        audit_year=project.audit_year,
        report_scope=project.report_scope,
    )
    if counterpart is None:
        return []
    values = _group_values(project)
    if _group_values(counterpart) == values:
        return []
    apply_group_values(counterpart, values)
    return [f"已同步集团关系到同企业的{_counterpart_label(counterpart)}"]


# ─────────────────────────────── 派生链接（spec 任务 6） ───────────────────────────────

_PENDING_BROADCAST = "group_links.pending_broadcast"
_LISTENERS_ON = "group_links.listeners"


def _flush_pending_broadcast(session: Any) -> None:
    pending = session.info.pop(_PENDING_BROADCAST, None)
    if not pending:
        return
    from app.services.consol_scope_service import _emit_scope_changed

    for project_id, year in sorted(pending, key=lambda item: (str(item[0]), item[1] or 0)):
        _emit_scope_changed(project_id, year)


def _drop_pending_broadcast(session: Any) -> None:
    session.info.pop(_PENDING_BROADCAST, None)


def _broadcast_after_commit(db: AsyncSession, project_ids: set[UUID], year: int) -> None:
    """合并范围变更广播挂到提交之后（前端收到广播会立刻重取企业树，提交前推送会读到旧数据）；回滚则丢弃。"""
    if not project_ids:
        return
    from sqlalchemy import event

    session = db.sync_session
    session.info.setdefault(_PENDING_BROADCAST, set()).update((pid, year) for pid in project_ids)
    if not session.info.get(_LISTENERS_ON):
        event.listen(session, "after_commit", _flush_pending_broadcast)
        event.listen(session, "after_rollback", _drop_pending_broadcast)
        session.info[_LISTENERS_ON] = True


async def sync_group_links(db: AsyncSession, year: int | None) -> set[UUID]:
    """按三码重算该审计年度全部项目的派生链接 ``parent_project_id``（ADR-CTREE-001，需求 7.1~7.3）。

    - 一次推导整年（与建项顺序无关，P5），只写值有变化的行；
    - 受影响的合并项目（变化行的新旧上级）⇒ 合并试算标陈旧 + 提交后广播合并范围变更；
    - 只 flush 不 commit（调用方统一提交）。返回受影响的合并项目 id。
    """
    if year is None:
        return set()
    from app.models.consolidation_models import ConsolTrial
    from app.services.consol_group_tree import derive_parent_links, load_year_records

    records = await load_year_records(db, year)
    links = derive_parent_links(records, year)
    affected: set[UUID] = set()
    for rec in records:
        new = links.get(rec.id)
        if new == rec.parent_project_id:
            continue
        await db.execute(
            sa.update(Project).where(Project.id == rec.id).values(parent_project_id=new)
        )
        affected.update(pid for pid in (rec.parent_project_id, new) if pid is not None)
    if affected:
        await db.execute(
            sa.update(ConsolTrial)
            .where(
                ConsolTrial.project_id.in_(affected),
                ConsolTrial.year == year,
                ConsolTrial.is_deleted == sa.false(),
                ConsolTrial.is_stale == sa.false(),
            )
            .values(is_stale=True)
            .execution_options(synchronize_session=False)
        )
        _broadcast_after_commit(db, affected, year)
    await db.flush()
    return affected


async def sync_group_links_for(db: AsyncSession, *projects: Any) -> set[UUID]:
    """对若干项目涉及的审计年度逐一重算链接（删除、恢复、改报表类型等写路径用）。"""
    from app.services.project_audit_year import resolve_project_audit_year

    years = sorted({y for y in (resolve_project_audit_year(p) for p in projects if p is not None) if y})
    affected: set[UUID] = set()
    for year in years:
        affected |= await sync_group_links(db, year)
    return affected


__all__ = [
    "GROUP_FIELDS",
    "apply_group_values",
    "default_relation_by_name",
    "find_counterpart",
    "infer_ultimate_from_parent",
    "inherit_from_counterpart",
    "normalize_group_fields",
    "prepare_group_fields",
    "propagate_to_counterpart",
    "sync_group_links",
    "sync_group_links_for",
]
