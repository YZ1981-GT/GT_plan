"""程序裁剪页的程序目录与补齐（spec trim-generation-plan-linkage R5 / R3.4 / R3.7）。

程序裁剪页按程序行裁剪（``procedure_instances``，目录 = 项目选用的模板库，没有则 ``gt_template_library.json``），
生成底稿按模板编码（``wp_account_mapping.json``，与标准年审模板集同一份）。两份目录不一一对应（程序目录
331 行、模板编码 1025 个），中间靠编码谱系 / 区间展开换算（``procedure_scope_retention.TrimmedScope``）。

换算不到的编码（B1-3、B5-1~B5-9-2、A18、S32 等计划 / 完成阶段 / 专项文档）原先在裁剪页上既裁不掉也指派
不了底稿主编；同一程序行管的底稿业务分类适用性不同时（A1 行里只有 A1-12 / A1-16 是上市专用），按业务
分类给的裁剪建议也没法落到行上。初始化循环时把这两类编码补成程序行：编码 = 底稿编码、名称取模板清单，
排在原有程序行之后；没有程序行管的补「执行」，适用性分裂的子码沿用原决定行的状态与理由（补齐前后生成
判定不变，见 :func:`supplement_entries`）。

补齐只在初始化接口里做（委派人门 + 咨询锁）；读取程序行（GET）只读，不补。
"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance
from app.services.business_category_service import (
    get_template_list_with_applicability,
    is_template_applicable,
    template_mappings,
)
from app.services.procedure_identity import normalize_cycle, normalize_procedure_identity
from app.services.procedure_scope_retention import (
    RANGE_SEPARATOR,
    TrimmedScope,
    TrimScopeUnavailable,
    lock_project_procedure_scope,
    normalize_code,
)
from app.services.procedure_task_transition_service import SCOPE_STATUS_EXECUTE, SCOPE_TRIMMED_STATUSES

_LIBRARY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gt_template_library.json"

#: 质控业务分类组别（与 ``project_classification.CATEGORY_GROUPS`` 同值；未填写按 C 类判断）。
CATEGORIES = ("A", "B", "C")
DEFAULT_CATEGORY = "C"

ORIGIN_CATALOG = "catalog"
ORIGIN_SUPPLEMENT = "supplement"
ORIGIN_CUSTOM = "custom"

PROCEDURE_CATALOG_UNAVAILABLE = "procedure_catalog_unavailable"
PROCEDURE_CATALOG_UNAVAILABLE_MESSAGE = "无法读取项目程序目录，未执行初始化，请稍后重试"


class ProcedureCatalogUnavailable(TrimScopeUnavailable):
    """项目模板目录查询失败；不得伪装成「项目未选择模板」后写入全局默认目录。"""

    def http_detail(self) -> dict:
        return {"error": PROCEDURE_CATALOG_UNAVAILABLE, "message": PROCEDURE_CATALOG_UNAVAILABLE_MESSAGE}


# ── 目录 ──────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _library_items() -> tuple[dict, ...]:
    if not _LIBRARY_PATH.exists():
        return ()
    raw = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8-sig"))
    items = raw.get("templates", []) if isinstance(raw, dict) else raw
    return tuple(i for i in items if isinstance(i, dict))


async def catalog_items(db: AsyncSession, project_id: UUID, cycle: str) -> list[dict]:
    """该循环的程序目录（初始化建行的来源）：项目选用的模板库优先，没有则 ``gt_template_library.json``。

    选用模板库的条目形如 ``{wp_code, wp_name, cycle_prefix}``，目录文件的条目形如 ``{code, name, cycle_prefix}``
    （与初始化原有读法相同）。两处都没有返回 ``[]``，由初始化再降级到 ``wp_template``。
    模板库表不可用时只回滚自己的保存点（原先裸 ``try/except`` 在 PG 上会让外层事务进入 aborted）。
    """
    cycle = normalize_cycle(cycle)
    items: list[dict] = []
    try:
        from app.models.template_library_models import (
            ProjectTemplateSelection,
            TemplateLibraryItem,
            TemplateType,
        )

        sel_q = (
            sa.select(TemplateLibraryItem)
            .join(ProjectTemplateSelection, ProjectTemplateSelection.template_id == TemplateLibraryItem.id)
            .where(
                ProjectTemplateSelection.project_id == project_id,
                ProjectTemplateSelection.is_active == sa.true(),
                TemplateLibraryItem.template_type == TemplateType.workpaper_preset,
                TemplateLibraryItem.audit_cycle == cycle,
                TemplateLibraryItem.is_deleted == sa.false(),
            )
            .order_by(TemplateLibraryItem.wp_code)
        )
        async with db.begin_nested():
            for item in (await db.execute(sel_q)).scalars().all():
                items.append({"wp_code": item.wp_code, "wp_name": item.name, "cycle_prefix": item.audit_cycle})
    except (SQLAlchemyError, ImportError) as exc:
        raise ProcedureCatalogUnavailable(f"读取项目程序目录失败：{exc}") from exc
    if not items:
        items = [dict(i) for i in _library_items()
                 if str(i.get("cycle_prefix") or "").strip().upper() == cycle]
    return items


def item_code(item: Mapping[str, Any]) -> str:
    """目录条目的编码（两种条目形态共用）。"""
    return normalize_code(item.get("wp_code") or item.get("code"))


async def catalog_codes_by_cycle(db: AsyncSession, project_id: UUID) -> dict[str, set[str]]:
    """各循环程序目录的编码（与 :func:`catalog_items` 同一优先级，一次查询全部循环；生成计划用）。"""
    out: dict[str, set[str]] = {}
    for item in _library_items():
        out.setdefault(str(item.get("cycle_prefix") or "").strip().upper(), set()).add(item_code(item))
    selected: dict[str, set[str]] = {}
    try:
        from app.models.template_library_models import (
            ProjectTemplateSelection,
            TemplateLibraryItem,
            TemplateType,
        )

        q = (
            sa.select(TemplateLibraryItem.audit_cycle, TemplateLibraryItem.wp_code)
            .join(ProjectTemplateSelection, ProjectTemplateSelection.template_id == TemplateLibraryItem.id)
            .where(
                ProjectTemplateSelection.project_id == project_id,
                ProjectTemplateSelection.is_active == sa.true(),
                TemplateLibraryItem.template_type == TemplateType.workpaper_preset,
                TemplateLibraryItem.is_deleted == sa.false(),
            )
        )
        async with db.begin_nested():
            for cycle, code in (await db.execute(q)).all():
                selected.setdefault(str(cycle or "").strip().upper(), set()).add(normalize_code(code))
    except (SQLAlchemyError, ImportError) as exc:
        raise ProcedureCatalogUnavailable(f"读取项目程序目录编码失败：{exc}") from exc
    out.update(selected)  # 有选用模板库的循环以选用的为准（与初始化同一优先级）
    return out


def row_origin(code: str | None, *, is_custom: bool, catalog_codes: set[str], template_codes: set[str]) -> str:
    """程序行来源：自定义 / 程序目录里的行 / 补齐的行（编码不在目录、但是本循环的模板编码）。"""
    norm = normalize_code(code)
    if is_custom:
        return ORIGIN_CUSTOM
    if norm in catalog_codes or norm not in template_codes:
        return ORIGIN_CATALOG
    return ORIGIN_SUPPLEMENT


def standard_template_cycle(code: str | None) -> str | None:
    """标准模板编码所属循环；非标准编码返回 ``None``（自定义编码不按首字母猜）。"""
    norm = normalize_code(code)
    for item in template_mappings():
        if normalize_code(item.get("wp_code")) == norm:
            cycle = str(item.get("cycle") or norm[:1]).strip().upper()
            return cycle or None
    return None


def cycle_template_items(cycle: str) -> list[dict[str, Any]]:
    """映射表里该循环的模板（标准年审模板集、生成计划同一份），保持文件顺序。"""
    cycle = normalize_cycle(cycle)
    return [m for m in template_mappings()
            if str(m.get("cycle") or str(m.get("wp_code") or "")[:1]).strip().upper() == cycle]


def category_restriction(item: Mapping[str, Any]) -> frozenset[str]:
    """该模板在 A / B / C 哪几类业务分类下不适用（与生成弹窗、业务分类建议同一判定）。"""
    return frozenset(c for c in CATEGORIES if not is_template_applicable(dict(item), c))


# ── 补齐 ──────────────────────────────────────────────────────────────────


def supplement_items(
    rows: Iterable[tuple[str | None, str | None]],
    cycle_items: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """要补成程序行的模板（纯函数，保持模板顺序）。

    ``rows``：本项目全部未删除程序行的 ``(编码, 状态)``（与生成判定同一来源）；``cycle_items``：该循环的模板。

    两类：
    1. 没有任何程序行决定（自己、母码链、区间、跟随下级都没有）的编码；
    2. 适用性分裂：决定它的程序行（不是它自己、也不是跟随下级）还管着业务分类适用性不同的底稿。
       程序行本身是模板编码时以它为准；区间行等不是模板编码的，以它所管底稿里最多的那一种为准。
    区间编码不补；已有程序行的编码由那条行自己决定（判定规则 1，``decided_by`` 回报它自己），两类都不会选中，
    不另做「已有行」判断（另做的那份判断与规则 1 等价，变异删掉它测不出差别）。
    """
    scope = TrimmedScope.from_rows(rows)
    by_code = {normalize_code(m.get("wp_code")): m for m in template_mappings()}
    order: dict[str, int] = {}
    picked: set[str] = set()
    owned: dict[str, list[str]] = {}
    for pos, item in enumerate(cycle_items):
        code = normalize_code(item.get("wp_code"))
        if not code or RANGE_SEPARATOR in code or code in order:
            continue
        order[code] = pos
        verdict = scope.decided_by(code)
        if verdict is None:
            picked.add(code)
        elif verdict[0] != code and not scope.follows_children(code):
            owned.setdefault(verdict[0], []).append(code)
    restriction = {code: category_restriction(by_code.get(code) or {"wp_code": code}) for code in order}
    for owner, codes in owned.items():
        if owner in by_code:
            base = category_restriction(by_code[owner])
        else:
            base = Counter(restriction[c] for c in codes).most_common(1)[0][0]
        picked.update(c for c in codes if restriction[c] != base)
    return [cycle_items[order[c]] for c in sorted(picked, key=order.__getitem__)]


def supplement_entries(
    rows: Iterable[tuple[str | None, str | None]],
    cycle_items: Sequence[Mapping[str, Any]],
    reasons: Mapping[str, str] | None = None,
) -> list[tuple[Mapping[str, Any], str, str | None]]:
    """要补的模板 + 补进去的状态与理由（纯函数）：补齐前后每个编码的生成判定不变。

    没有程序行决定的编码补「执行」（原本就照常生成）。适用性分裂的子码沿用原决定行：原决定行已裁
    （如 A1 整行裁掉）⇒ 补的 A1-12 / A1-16 也已裁、理由沿用 —— 一律补「执行」会让已裁掉的底稿在下次
    打开裁剪页时悄悄恢复生成。``reasons``：已裁程序行的 ``{规范化编码: 裁剪理由}``。
    """
    rows = list(rows)
    scope = TrimmedScope.from_rows(rows)
    trimmed_status: dict[str, str] = {}
    for code, status in rows:
        norm, value = normalize_code(code), (status or "").strip().lower()
        if norm and value in SCOPE_TRIMMED_STATUSES:
            trimmed_status.setdefault(norm, value)
    out: list[tuple[Mapping[str, Any], str, str | None]] = []
    for item in supplement_items(rows, cycle_items):
        verdict = scope.decided_by(item.get("wp_code"))
        if verdict is not None and verdict[1]:
            owner = verdict[0]
            reason = (reasons or {}).get(owner) or f"随程序行 {owner} 一起裁剪"
            out.append((item, trimmed_status.get(owner, SCOPE_TRIMMED_STATUSES[-1]), reason))
        else:
            out.append((item, SCOPE_STATUS_EXECUTE, None))
    return out


async def lock_cycle_init(db: AsyncSession, project_id: UUID, cycle: str) -> None:
    """同一项目同一循环的初始化 / 补齐串行（事务级咨询锁，提交或回滚时释放）。

    V225（原 V217）已增加 active 规范化唯一索引；咨询锁仍保留，用于把初始化的「查目录 → 建行 → 补齐」整段串行，
    让并发请求幂等重读而不是依赖唯一冲突回滚。SQLite 测试库不支持 PG 咨询锁，跳过。
    """
    cycle = normalize_cycle(cycle)
    await lock_project_procedure_scope(db, project_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await db.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                         {"k": f"procedure_init:{project_id}:{cycle}"})


async def _project_rows(db: AsyncSession, project_id: UUID) -> list[tuple[str, str, str, int, str]]:
    """本项目全部未删除程序行：``(编码, 状态, 循环, 排序, 裁剪理由)``。"""
    rows = (await db.execute(
        sa.select(
            sa.func.coalesce(ProcedureInstance.wp_code, ProcedureInstance.procedure_code),
            ProcedureInstance.status,
            ProcedureInstance.audit_cycle,
            ProcedureInstance.sort_order,
            ProcedureInstance.skip_reason,
        ).where(ProcedureInstance.project_id == project_id, ProcedureInstance.is_deleted == sa.false())
    )).all()
    return [(normalize_code(r[0]), r[1] or "", str(r[2] or "").strip().upper(),
             int(r[3] or 0), (r[4] or "").strip()) for r in rows]


async def ensure_supplement_rows(db: AsyncSession, project_id: UUID, cycle: str) -> int:
    """把该循环缺的程序行补上（调用方已取 :func:`lock_cycle_init`），返回补了几行（只 flush）。

    幂等：补过之后每个编码都由某条程序行决定、且没有适用性分裂，再调用补 0 行。不改已有行的状态与理由；
    补的行状态见 :func:`supplement_entries`（补齐前后生成判定不变）。
    """
    cycle = normalize_cycle(cycle)
    rows = await _project_rows(db, project_id)
    reasons: dict[str, str] = {}
    for code, status, _, _, reason in rows:
        if reason and status.strip().lower() in SCOPE_TRIMMED_STATUSES:
            reasons.setdefault(normalize_code(code), reason)
    entries = supplement_entries([(c, s) for c, s, *_ in rows], cycle_template_items(cycle), reasons)
    if not entries:
        return 0
    base = max((o for _, _, cyc, o, _ in rows if cyc == cycle), default=-10)
    for k, (item, status, reason) in enumerate(entries, start=1):
        identity = normalize_procedure_identity(cycle, item.get("wp_code"), item.get("wp_code"))
        db.add(ProcedureInstance(
            project_id=project_id, audit_cycle=identity.audit_cycle, procedure_code=identity.procedure_code,
            procedure_name=str(item.get("wp_name") or identity.procedure_code)[:500], sort_order=base + 10 * k,
            status=status, skip_reason=reason, wp_code=identity.wp_code,
        ))
    await db.flush()
    return len(entries)


# ── 读取标注（GET 程序行用，只读）──────────────────────────────────────────


async def project_category(db: AsyncSession, project_id: UUID) -> tuple[str, bool]:
    """项目质控业务分类组别与「是否没有填写、按默认 C 类」（``project_classification`` 单一来源）。

    分类码只认参考标准登记的码；空值、未登记值（含 V219 迁移前残留的 ``IPO`` / ``refinancing``）按未填写处理。
    """
    from app.services.project_classification import load_project_classification

    classification = await load_project_classification(db, project_id)
    return classification.category_group, classification.defaulted


def category_lookup(category: str) -> dict[str, tuple[bool, str]]:
    """``{编码: (是否适用, 不适用的原因)}``（映射表全部模板）。"""
    return {
        normalize_code(i.get("wp_code")): (bool(i.get("applicable")), str(i.get("applicable_reason") or ""))
        for i in get_template_list_with_applicability(category)
    }


def category_hint_text(category: str, defaulted: bool, codes: Sequence[str], reasons: Iterable[str]) -> str:
    """业务分类建议的理由（也是「按建议裁剪」填进裁剪理由的文字）。"""
    who = f"{category} 类" + ("（项目未填写 A / B / C 业务分类，按 C 类判断）" if defaulted else "")
    detail = "；".join(dict.fromkeys(r for r in reasons if r))
    return f"按项目业务分类 {who}，本行 {len(codes)} 个底稿均不适用" + (f"：{detail}" if detail else "")


def annotate_rows(
    rows: list[dict],
    cycle: str,
    *,
    catalog_codes: set[str],
    category: str,
    defaulted: bool,
) -> None:
    """给 ``get_procedures`` 的每行加 ``origin`` 与 ``category_hint``（原地，纯计算）。

    - ``origin``：``custom``（自定义）/ ``catalog``（程序目录里的行）/ ``supplement``（补齐的行）。
    - ``category_hint``：本行决定的模板（不含跟随下级的母码）按项目业务分类全部不适用时为
      ``{"reason": 理由, "codes": [编码…]}``，否则 ``None``。
    """
    templates = cycle_template_items(cycle)
    template_codes = {normalize_code(t.get("wp_code")) for t in templates}
    scope = TrimmedScope.from_rows((r.get("wp_code") or r.get("procedure_code"), r.get("status")) for r in rows)
    decided: dict[str, list[str]] = {}
    for t in templates:
        code = normalize_code(t.get("wp_code"))
        verdict = scope.decided_by(code)
        if verdict is not None and not scope.follows_children(code):
            decided.setdefault(verdict[0], []).append(code)
    lookup = category_lookup(category)
    for row in rows:
        code = normalize_code(row.get("wp_code") or row.get("procedure_code"))
        row["origin"] = row_origin(code, is_custom=bool(row.get("is_custom")), catalog_codes=catalog_codes,
                                   template_codes=template_codes)
        codes = decided.get(code) or []
        verdicts = [lookup.get(c, (True, "")) for c in codes]
        if codes and not any(ok for ok, _ in verdicts):
            row["category_hint"] = {
                "reason": category_hint_text(category, defaulted, codes, (r for _, r in verdicts)),
                "codes": codes,
            }
        else:
            row["category_hint"] = None
