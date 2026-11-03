"""集团级附注披露模板下推服务。

合并负责人把某章节绑定的集团明细模板版本下推到企业树全部数据叶子：在子企业单体附注里与合并章节对应的
那张表上，给模板行打上行身份（``_pushed_row_id`` / ``_pushed_category``），子企业缺的模板行补成空行。合并
拉数时这些行按 ``_pushed_row_id`` 精确对应（匹配方式 ``exact_id``），不靠行名。

写入规则（spec note-pull-header-formula-closure R6.1；修订归档 spec consol-note-template-push-to-subsidiaries
的做法 —— 原实现导入不存在的模块、对每家子企业都失败，推送日志 SQL 也执行不了，从未写成过）：

- 章节：按合并项目附注口径（国企 / 上市）的章节映射换成单体章节号，取不到按单体章节标题取（与拉数同一口径）；
- 表：按映射子表名 / 合并表标题在单体章节里选表（``pick_standalone_table``），选不出给中文原因、跳过；
- 行：已有 ``_pushed_row_id`` 的按 id 认领；首次下推按行名 / 别名认领已有行 —— 行名、数值、位置都不动
  （改行名会让子企业公式推送按行名找不到行）；缺的模板行插在下一个已认领模板行之前（后面没有就接在上一个
  模板行之后），值按本表列宽补空；模板里已没有的下推行只去掉下推标记（不删行、不删数）；
- 不写：子企业没有该章节附注（不替子企业新建残缺章节）、标为本期无此情形、由底稿披露表同步（行结构以底稿为准）、
  表里没有一行对得上模板（多半选错了表）、操作人在子企业没有附注编辑权限 / 项目归档 / 合并锁定；
- 每家一个保存点，一家失败只回滚这一家；写入以操作人身份盖「最近一次编辑」；
- 不写动态行区占位行：附注编辑器、Word 导出、空表判定都不认它（会显示 / 导出成一条空行）。

Service 只 flush 不 commit。
"""
from __future__ import annotations

import copy
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.services.consol_note_detail_suggest import _label_key, is_placeholder_label

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("required", "optional", "dynamic_zone")
#: 由底稿披露表同步的章节：行结构以底稿为准，下推不改
_WORKPAPER_SOURCES = frozenset({"workpaper", "workpaper_html"})
_PUSH_KEYS = ("_pushed_row_id", "_pushed_category", "_pushed_optional_active")
_TEMPLATE_TYPE_LABELS = {"soe": "国企", "listed": "上市"}


class PushTemplateError(ValueError):
    """下推前置校验失败（模板版本不存在 / 不属于该章节 / 口径不符 / 没有行 / 没有企业树），路由回 400。"""


# ── 结果 ──


@dataclass
class EntityResult:
    node_key: str
    project_id: UUID | None
    company_name: str = ""
    status: str = "pending"  # success / skipped / failed
    reason: str | None = None
    table_name: str | None = None
    claimed: int = 0   # 认领为下推行的已有行（含按行身份认领）
    added: int = 0     # 补上的模板行
    released: int = 0  # 模板里已没有、去掉下推标记的行


@dataclass
class PushResult:
    section_id: str
    entity_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    skip_count: int = 0
    entities: list[EntityResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "entity_count": self.entity_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "skip_count": self.skip_count,
            "entities": [
                {"node_key": e.node_key, "project_id": str(e.project_id) if e.project_id else None,
                 "company_name": e.company_name, "status": e.status, "reason": e.reason,
                 "table_name": e.table_name, "claimed": e.claimed, "added": e.added, "released": e.released}
                for e in self.entities
            ],
        }


@dataclass
class MergePlan:
    """下推到一张表的结果：``rows`` 为新的行序列（已有行深拷贝后改标记）。"""

    rows: list[Any]
    claimed: int = 0
    added: int = 0
    released: int = 0
    claimed_detail: int = 0  # 认领到的明细行（不含合计 / 小计）：一行都没有 ⇒ 多半选错了表


# ── 行规则（纯函数） ──


def pushable_template_rows(rows: Any) -> list[dict[str, Any]]:
    """可下推的模板行：动态行区占位不写进子企业附注，没有行身份的行跳过。

    「……」这类可扩位占位行按行名认（模板标成固定行也不推）：推进去就成了子企业附注里删不掉的空行
    （下推的固定行编辑器不让删），2026-10-26 浏览器实测【测试】甲 五、5 被补了一行「……」。
    """
    return [
        r for r in (rows if isinstance(rows, list) else [])
        if isinstance(r, dict) and r.get("category", "required") != "dynamic_zone"
        and not is_placeholder_label(r.get("canonical_name"))
        and str(r.get("target_row_id") or "").strip()
    ]


def _row_label(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("label") or "")
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "")
    return ""


def _template_is_total(tr: dict[str, Any]) -> bool:
    from app.services.note_total_terms import label_row_type

    return str(tr.get("row_type") or "") in ("total", "subtotal") or label_row_type(tr.get("canonical_name")) != "data"


def _existing_is_total(row: dict[str, Any]) -> bool:
    from app.services.note_total_terms import label_row_type, row_kind

    return row_kind(row) in ("total", "subtotal") or label_row_type(row.get("label")) != "data"


def _mark(row: dict[str, Any], tr: dict[str, Any]) -> None:
    """打上下推行身份；子企业已取消勾选的可选行保持取消。"""
    category = str(tr.get("category") or "required")
    row["_pushed_row_id"] = str(tr["target_row_id"])
    row["_pushed_category"] = category
    if category == "optional":
        row.setdefault("_pushed_optional_active", True)
    else:
        row.pop("_pushed_optional_active", None)


def _new_row(tr: dict[str, Any], width: int) -> dict[str, Any]:
    """子企业缺的模板行：模板行名，值按本表列宽补空。"""
    row: dict[str, Any] = {
        "label": str(tr.get("canonical_name") or ""),
        "values": [None] * max(width, 0),
        "row_type": str(tr.get("row_type") or "data"),
    }
    _mark(row, tr)
    return row


def build_skeleton_rows(template_rows: list[dict[str, Any]], width: int = 0) -> list[dict[str, Any]]:
    """表里一行都没有时的下推行（不含动态行区占位）。"""
    return [_new_row(tr, width) for tr in pushable_template_rows(template_rows)]


def plan_merge(template_rows: list[dict[str, Any]], existing_rows: list[Any], *, width: int = 0) -> MergePlan:
    """把模板行认领 / 补进子企业的一张表（已有行的行名、数值、顺序都不动）。

    ① 已下推过的行按 ``_pushed_row_id`` 认领；② 其余模板行按行名 / 别名（去空白比）认领未下推的已有行，同名多行
    （多个「小计」）从上一个认领行往下按顺序对应；行类型不参与比对 —— 同名即同一行，声明的类型两边不一致时
    不认领反而会补出一条重名行；③ 已不在模板里的下推行去掉下推标记；④ 缺的模板行插在下一个已认领模板行之前，
    后面没有就接在上一个模板行之后。
    """
    template = pushable_template_rows(template_rows)
    rows = [copy.deepcopy(r) for r in (existing_rows or [])]
    tids = {str(tr["target_row_id"]) for tr in template}
    owner: dict[int, int] = {}  # 模板行序号 → 表内行序号
    taken: set[int] = set()

    by_id = {str(r["_pushed_row_id"]): i for i, r in enumerate(rows) if isinstance(r, dict) and r.get("_pushed_row_id")}
    for ti, tr in enumerate(template):
        ri = by_id.get(str(tr["target_row_id"]))
        if ri is not None and ri not in taken:
            owner[ti] = ri
            taken.add(ri)

    def claimable(ri: int, keys: set[str]) -> bool:
        r = rows[ri]
        return (ri not in taken and isinstance(r, dict) and str(r.get("_pushed_row_id") or "") not in tids
                and _label_key(_row_label(r)) in keys)

    cursor = 0
    for ti, tr in enumerate(template):
        if ti in owner:
            cursor = owner[ti] + 1
            continue
        keys = {_label_key(tr.get("canonical_name"))} | {_label_key(a) for a in tr.get("aliases") or []}
        keys.discard("")
        ri = next((i for i in range(cursor, len(rows)) if claimable(i, keys)), None)
        if ri is None:
            ri = next((i for i in range(min(cursor, len(rows))) if claimable(i, keys)), None)
        if ri is not None:
            owner[ti] = ri
            taken.add(ri)
            cursor = ri + 1

    plan = MergePlan(rows=[], claimed=len(owner),
                     claimed_detail=sum(1 for ti in owner if not _template_is_total(template[ti])))
    for ti, ri in owner.items():
        _mark(rows[ri], template[ti])
    for ri, r in enumerate(rows):
        if ri not in taken and isinstance(r, dict) and r.get("_pushed_row_id") and str(r["_pushed_row_id"]) not in tids:
            for key in _PUSH_KEYS:
                r.pop(key, None)
            plan.released += 1

    out = list(rows)
    previous: Any = None  # 上一个已放置的模板行（对象引用）
    for ti, tr in enumerate(template):
        if ti in owner:
            previous = rows[owner[ti]]
            continue
        new = _new_row(tr, width)
        following = next((rows[owner[tj]] for tj in range(ti + 1, len(template)) if tj in owner), None)
        if following is not None:
            out.insert(next(i for i, r in enumerate(out) if r is following), new)
        elif previous is not None:
            out.insert(next(i for i, r in enumerate(out) if r is previous) + 1, new)
        else:
            out.append(new)
        previous = new
        plan.added += 1
    plan.rows = out
    return plan


def merge_rows(
    template_rows: list[dict[str, Any]], existing_rows: list[Any], width: int = 0,
) -> list[dict[str, Any]]:
    """``plan_merge`` 的行序列。"""
    return plan_merge(template_rows, existing_rows, width=width).rows


def _table_width(table: dict[str, Any]) -> int:
    """值列数：表头列数 − 行名列，与已有行的值个数取大。"""
    headers = table.get("headers")
    widths = [len(headers) - 1] if isinstance(headers, list) and headers else []
    widths += [len(r["values"]) for r in table.get("rows") or [] if isinstance(r, dict) and isinstance(r.get("values"), list)]
    return max(widths + [0])


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


# ── 下推主流程 ──


async def _load_template_rows(
    db: AsyncSession, template_version_id: UUID, section_id: str, template_type: str,
) -> list[dict[str, Any]]:
    """模板版本须属于本章节、与合并项目附注口径一致，且有可下推的行。"""
    from app.models.consol_note_mapping_models import ConsolNoteDetailTemplate, ConsolNoteDetailTemplateVersion

    found = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion, ConsolNoteDetailTemplate)
        .join(ConsolNoteDetailTemplate, ConsolNoteDetailTemplate.id == ConsolNoteDetailTemplateVersion.template_id)
        .where(ConsolNoteDetailTemplateVersion.id == template_version_id)
    )).first()
    if found is None:
        raise PushTemplateError(f"模板版本 {template_version_id} 不存在")
    version, template = found
    if template.is_deleted:
        raise PushTemplateError("该明细模板已删除")
    if template.section_id != section_id:
        raise PushTemplateError(f"模板版本属于章节 {template.section_id}，不是 {section_id}")
    if template.template_type != template_type:
        raise PushTemplateError(
            f"模板口径（{_TEMPLATE_TYPE_LABELS.get(template.template_type, template.template_type)}）"
            f"与合并项目附注口径（{_TEMPLATE_TYPE_LABELS.get(template_type, template_type)}）不符")
    rows = pushable_template_rows(version.rows)
    if not rows:
        raise PushTemplateError("模板没有可下推的行")
    return rows


async def push_template_to_subsidiaries(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    year: int,
    template_version_id: UUID,
    actor: Any,
) -> PushResult:
    """下推集团模板到企业树全部数据叶子（逐家保存点）；记推送日志。

    ``actor`` 为操作人（``User``）：逐家按附注编辑门禁判权（含项目归档 / 合并锁定），写入以其身份盖章。下推行由子企业
    保存时的固定行校验保护（``note_pushed_row_guard``），不再写结构锁（V202 退役，spec note-pull-followup-closure R16）。
    """
    from app.services.consol_calc_basis import data_leaves
    from app.services.consol_note_detail_source_service import resolve_section_template_type
    from app.services.consol_tree_service import build_tree
    from app.services.note_edit_gate import note_edit_rejection_reason

    template_type = await resolve_section_template_type(db, consol_project_id)
    template_rows = await _load_template_rows(db, template_version_id, section_id, template_type)
    tree = await build_tree(db, consol_project_id)
    if tree is None:
        raise PushTemplateError("合并项目没有企业树，无法下推")

    leaves = [leaf for leaf in data_leaves(tree) if leaf.project_id is not None]
    result = PushResult(section_id=section_id, entity_count=len(leaves))
    for leaf in leaves:
        er = EntityResult(node_key=leaf.node_key, project_id=leaf.project_id,
                          company_name=getattr(leaf, "company_name", "") or "")
        try:
            async with db.begin_nested():
                await _push_to_one(db, er, section_id=section_id, year=year, template_rows=template_rows,
                                   template_type=template_type, actor=actor)
        except HTTPException as exc:  # 附注编辑门禁拒绝：无权限 / 项目归档 / 合并锁定
            er.status, er.reason = "skipped", note_edit_rejection_reason(exc)
        except Exception as exc:  # noqa: BLE001 —— 一家失败只回滚这一家，原因回报
            logger.warning("下推到 %s 失败: %s", leaf.node_key, exc, exc_info=True)
            er.status, er.reason = "failed", f"写入失败：{exc}"[:200]
        result.entities.append(er)
        if er.status == "success":
            result.success_count += 1
        elif er.status == "failed":
            result.failure_count += 1
        else:
            result.skip_count += 1

    actor_id = getattr(actor, "id", None)
    await _record_push_log(db, consol_project_id, section_id, template_version_id, actor_id, result)
    await db.flush()
    return result


async def _push_to_one(
    db: AsyncSession,
    er: EntityResult,
    *,
    section_id: str,
    year: int,
    template_rows: list[dict[str, Any]],
    template_type: str,
    actor: Any,
) -> None:
    """向一家子企业下推（结果写进 ``er``）；附注编辑门禁拒绝时抛 ``HTTPException``，由调用方记为跳过。"""
    from app.services import note_edit_gate
    from app.services.consol_note_detail_source_service import load_standalone_note
    from app.services.consol_note_section_mapping import resolve_mapping_entry
    from app.services.consol_note_standalone_reader import pick_standalone_table
    from app.services.note_edit_stamp import stamp_note_edit

    def skip(reason: str) -> None:
        er.status, er.reason = "skipped", reason

    entry = resolve_mapping_entry(template_type, section_id)
    standalone_section = (entry or {}).get("standalone_note_section")
    if not standalone_section:
        return skip("合并特有章节，没有对应的单体附注" if entry else f"章节映射未覆盖 {section_id}")
    await note_edit_gate.assert_note_edit_access(db, actor, er.project_id, consol_lock=True)
    note = await load_standalone_note(
        db, er.project_id, year, standalone_section, str(entry.get("standalone_section_title") or "").strip(),
    )
    if note is None:
        return skip(f"子企业附注未生成章节 {standalone_section}（先在子企业生成附注再下推）")
    if note.is_empty:
        return skip(f"子企业附注 {note.note_section} 标为本期无此情形")
    td = note.table_data if isinstance(note.table_data, dict) else {}
    sub = td.get("sub_table_data")
    if str(td.get("_source") or "") in _WORKPAPER_SOURCES or (isinstance(sub, dict) and sub):
        return skip(f"子企业附注 {note.note_section} 由底稿披露表同步，行结构以底稿为准")
    tables = td.get("_tables")
    if not isinstance(tables, list) or not any(isinstance(t, dict) for t in tables):
        return skip(f"子企业附注 {note.note_section} 没有表格")
    idx, reason = pick_standalone_table(
        tables, table_name=entry.get("standalone_table_name"), title=entry.get("consol_title"),
        section_title=note.section_title,
    )
    if idx is None or not isinstance(tables[idx], dict):
        return skip(reason or f"子企业附注 {note.note_section} 里认不出与合并章节对应的表")
    table = tables[idx]
    er.table_name = str(table.get("name") or "") or None
    existing = table.get("rows") if isinstance(table.get("rows"), list) else []
    plan = plan_merge(template_rows, existing, width=_table_width(table))
    has_detail = any(isinstance(r, dict) and _row_label(r).strip() and not _existing_is_total(r) for r in existing)
    if has_detail and plan.claimed_detail == 0:
        return skip(f"子企业附注 {note.note_section}「{er.table_name or '表格'}」没有一行明细与集团模板对得上，"
                    "未下推（请核对章节与表格）")
    er.claimed, er.added, er.released = plan.claimed, plan.added, plan.released
    er.status = "success"
    if _canonical(plan.rows) == _canonical(existing):
        er.reason = "已是最新，未改动"
        return

    new_td = copy.deepcopy(td)
    top = new_td.get("rows")
    mirrored = idx == 0 and isinstance(top, list) and [_row_label(r) for r in top] == [_row_label(r) for r in existing]
    new_td["_tables"][idx]["rows"] = plan.rows
    if mirrored:  # 顶层 rows 原是首表镜像 ⇒ 跟着改
        new_td["rows"] = copy.deepcopy(plan.rows)
    note.table_data = new_td
    flag_modified(note, "table_data")
    stamp_note_edit(note, getattr(actor, "id", None))
    await db.flush()


async def _record_push_log(
    db: AsyncSession,
    consol_project_id: UUID,
    section_id: str,
    template_version_id: UUID,
    pushed_by: UUID | None,
    result: PushResult,
) -> None:
    """记下推日志（V204 ``consol_note_template_push_log``）；``failures`` 列出失败与跳过的企业及原因。"""
    from app.models.consolidation_models import ConsolNoteTemplatePushLog

    db.add(ConsolNoteTemplatePushLog(
        id=uuid.uuid4(),
        consol_project_id=consol_project_id,
        section_id=section_id,
        template_version_id=template_version_id,
        pushed_by=pushed_by,
        pushed_at=datetime.now(timezone.utc),
        entity_count=result.entity_count,
        success_count=result.success_count,
        failure_count=result.failure_count,
        failures=[
            {"node_key": e.node_key, "company_name": e.company_name, "status": e.status, "reason": e.reason}
            for e in result.entities if e.status in ("failed", "skipped")
        ],
    ))
    await db.flush()
