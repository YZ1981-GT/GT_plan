"""合并附注「⚡ 自动映射」：把能确定的明细映射一次做完（spec note-pull-header-formula-closure R6.3 任务 23）。

真库 0 个明细模板绑定、0 条确认映射 ⇒「🔄 重新汇总」对全部数据叶子按「未绑定」跳过；人工逐章节建模板、逐组确认
工作量大且多半是行名一字不差的行。本服务逐章节：

1. 章节未绑定明细模板 ⇒ 按 ``suggest_template_for_section`` 的建议建模板并绑定（合并附注模板骨架 + 来源独有的明细行；
   全局别名库认得的写法并进模板行别名）。同一操作人对同一口径同一章节已有模板 ⇒ 追加版本（模板唯一键是
   口径 + 章节 + 创建人）；一家子企业都没读到 ⇒ 不建模板；
2. 预览（``preview_detail_refresh``）后逐结构组：组内每条来源行的建议都可自动确认（``is_auto_confirmable``：
   下推行 / 精确 / 别名 / 通用别名 / 历史）⇒ ``confirm_mapping``；否则整组留给「📋 明细映射」人工确认，回报企业与
   未确定的行名（不做半组确认：规则按结构组整组生效，漏一行合并数就少一行）；
3. 组内企业都已按当前结构确认过 ⇒ 不重复确认；用户排除过的企业保持排除。

不写合并附注数据：自动映射后「🔄 重新汇总」或映射弹窗「确认并写入」照常写。每章节一个保存点，一章失败只回滚这一章。
Service 只 flush 不 commit。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["AutoMapError", "SectionAutoMap", "auto_map_sections"]


@dataclass
class SectionAutoMap:
    section_id: str
    status: str = "pending"  # mapped 全部确认 / partial 部分组待确认 / pending 都待确认 / skipped / failed
    reason: str | None = None
    template_action: str | None = None  # created 新建模板 / versioned 追加版本 / existing 用已绑定的
    confirmed: list[dict[str, Any]] = field(default_factory=list)   # 本次确认的企业
    already: list[dict[str, Any]] = field(default_factory=list)     # 之前已确认、来源未变
    pending: list[dict[str, Any]] = field(default_factory=list)     # {node_key, company_name, labels: [...]}

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id, "status": self.status, "reason": self.reason,
            "template_action": self.template_action, "confirmed": self.confirmed, "already": self.already,
            "pending": self.pending,
        }


async def _bound_version(
    db: AsyncSession, out: SectionAutoMap, *, project_id: UUID, section_id: str, year: int,
    template_type: str, user_id: UUID | None, tree: Any,
) -> str | None:
    """本章节绑定的模板版本；未绑定 ⇒ 按来源建议建模板（或追加版本）并绑定。没读到来源 ⇒ None（``out`` 记跳过）。"""
    from app.models.consol_note_mapping_models import ConsolNoteDetailTemplate
    from app.services.consol_note_detail_source_service import suggest_template_for_section
    from app.services.consol_note_detail_template_service import (
        add_version,
        bind_template_version,
        create_template,
        get_binding,
    )

    binding = await get_binding(db, project_id, section_id)
    if binding is not None:
        out.template_action = "existing"
        return str(binding["template_version_id"])
    suggestion = await suggest_template_for_section(db, project_id=project_id, section_id=section_id, year=year, tree=tree)
    rows = [{"canonical_name": r["canonical_name"], "aliases": r["aliases"], "row_type": r["row_type"],
             "category": r.get("category") or "required"}  # 「……」占位 = dynamic_zone（下推不写）
            for r in suggestion["suggested_rows"] if str(r.get("canonical_name") or "").strip()]
    if not suggestion["entity_count"] or not rows:
        out.status, out.reason = "skipped", "没有读到任何子企业的单体附注（未生成 / 本期无此情形 / 合并特有章节）"
        return None
    mine = (await db.execute(sa.select(ConsolNoteDetailTemplate.id).where(
        ConsolNoteDetailTemplate.template_type == template_type,
        ConsolNoteDetailTemplate.section_id == section_id,
        ConsolNoteDetailTemplate.created_by == user_id,
        ConsolNoteDetailTemplate.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if mine is None:
        created = await create_template(
            db, template_type=template_type, section_id=section_id, name=f"{section_id}（自动映射）", rows=rows,
            change_note="⚡ 自动映射按来源建议建立", created_by=user_id,
        )
        version_id, out.template_action = created["latest_version"]["id"], "created"
    else:
        version = await add_version(db, mine, rows=rows, change_note="⚡ 自动映射按来源建议追加", created_by=user_id)
        version_id, out.template_action = version["id"], "versioned"
    await bind_template_version(
        db, project_id=project_id, section_id=section_id, template_version_id=UUID(str(version_id)),
        bound_by=user_id, confirm=True,
    )
    return str(version_id)


def _suggestion_key(label: str, group: Any, group_occ: Any, occurrence: Any) -> tuple:
    """建议 / 来源行的对应键：按分组（R3）> 按第几次出现（R11）> 只按行名。"""
    if isinstance(group, str):
        return (label, "group", group, int(group_occ or 0))
    if isinstance(occurrence, int) and not isinstance(occurrence, bool):
        return (label, "occurrence", occurrence)
    return (label,)


def _mapping_selector(key: tuple) -> dict[str, Any]:
    """对应键 → 映射里的取行条件（``source_group`` + ``source_group_occurrence`` / ``source_occurrence`` / 无）。"""
    if len(key) == 4:
        return {"source_group": key[2], "source_group_occurrence": key[3]}
    if len(key) == 3:
        return {"source_occurrence": key[2]}
    return {}


def _no_source_reason(entity_sources: list[dict[str, Any]] | None) -> str:
    reasons = sorted({str(s.get("reason")) for s in entity_sources or [] if s.get("reason")})
    detail = f"（{reasons[0]}{' 等' if len(reasons) > 1 else ''}）" if reasons else ""
    return f"没有读到任何子企业的单体附注{detail}"


async def _map_section(
    db: AsyncSession, out: SectionAutoMap, *, project_id: UUID, section_id: str, year: int,
    template_type: str, user_id: UUID | None, tree: Any,
) -> None:
    from app.models.consol_note_mapping_models import ConsolNoteMappingBinding
    from app.services.consol_note_detail_source_service import preview_detail_refresh
    from app.services.consol_note_detail_suggest import is_auto_confirmable
    from app.services.consol_note_mapping_rule_service import confirm_mapping
    from app.services.consol_note_topn import section_topn_limit

    topn = section_topn_limit(template_type, section_id)
    if topn:  # 行是欠款单位、随数据变化：不建明细模板、不逐行映射（R10 / ADR-7）
        out.status = "skipped"
        out.reason = f"前 {topn} 名表按单位跨企业合并重排，不需逐行映射（「🔄 重新汇总」直接从单体附注取数）"
        return
    if await _bound_version(db, out, project_id=project_id, section_id=section_id, year=year,
                            template_type=template_type, user_id=user_id, tree=tree) is None:
        return
    preview = await preview_detail_refresh(db, project_id=project_id, section_id=section_id, year=year, tree=tree)
    if not preview["groups"]:
        out.status, out.reason = "skipped", _no_source_reason(preview.get("entity_sources"))
        return
    # 同名行按（分组, 组内序号）各有一条建议（R3：source_group）；只出现一次、模板也只有一个同名行的行名没有分组
    by_key = {_suggestion_key(s["source_label"], s.get("source_group"), s.get("source_group_occurrence"),
                              s.get("source_occurrence")): s for s in preview["suggestions"]}
    bindings = {b.entity_node_key: b for b in (await db.execute(sa.select(ConsolNoteMappingBinding).where(
        ConsolNoteMappingBinding.project_id == project_id, ConsolNoteMappingBinding.section_id == section_id,
    ))).scalars().all()}
    for group in preview["groups"]:
        excluded = [e["node_key"] for e in group["entities"]
                    if getattr(bindings.get(e["node_key"]), "status", None) == "excluded"]
        active = [{"node_key": e["node_key"], "company_name": e.get("company_name", "")}
                  for e in group["entities"] if e["node_key"] not in excluded]
        if all(getattr(bindings.get(e["node_key"]), "status", None) == "confirmed"
               and bindings[e["node_key"]].bound_source_hash == group["hash"] for e in active):
            out.already.extend(active)  # 都已按当前结构确认过（含整组都被排除）
            continue
        picked: dict[tuple, dict[str, Any]] = {}
        for sr in group["source_rows"]:
            label = str(sr.get("label") or "")
            if not label:
                continue
            candidates = (_suggestion_key(label, sr.get("group") or "", sr.get("group_occurrence") or 0, None),
                          _suggestion_key(label, None, None, sr.get("occurrence")), _suggestion_key(label, None, None, None))
            key = next((c for c in candidates if c in by_key), candidates[-1])
            picked.setdefault(key, by_key.get(key) or {})
        undecided = list(dict.fromkeys(k[0] for k, s in picked.items() if not is_auto_confirmable(s)))
        if undecided:
            out.pending.extend({**e, "labels": undecided} for e in active)
            continue
        await confirm_mapping(
            db, project_id=project_id, section_id=section_id, year=year,
            template_version_id=UUID(str(preview["template_version_id"])), source_structure_hash=group["hash"],
            mappings=[{"source_label": k[0], "target_row_id": s["suggested_target"]["target_row_id"],
                       "mapping_action": "map", **_mapping_selector(k)} for k, s in picked.items()],
            entity_node_keys=[{**e, "hash": group["hash"]} for e in group["entities"]],
            excluded_node_keys=excluded or None, confirmed_by=user_id,
        )
        out.confirmed.extend(active)
    out.status = "mapped" if not out.pending else ("partial" if out.confirmed or out.already else "pending")


class AutoMapError(ValueError):
    """自动映射前置条件不满足（合并项目没有企业树），路由回 400。"""


async def auto_map_sections(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    section_ids: list[str] | None = None,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """逐章节自动映射（``section_ids`` 为空 = 合并附注模板里有单体对应的全部章节）；企业树只建一次。"""
    from app.services.consol_note_detail_source_service import resolve_section_template_type
    from app.services.consol_note_section_mapping import all_mapped_sections
    from app.services.consol_tree_service import build_tree

    template_type = await resolve_section_template_type(db, project_id)
    tree = await build_tree(db, project_id)
    if tree is None:
        raise AutoMapError("合并项目没有企业树，无法自动映射")
    sections = list(dict.fromkeys(section_ids)) if section_ids else [
        str(e["consol_section_id"]) for e in all_mapped_sections(template_type)]

    results: list[SectionAutoMap] = []
    for sid in sections:
        out = SectionAutoMap(section_id=sid)
        try:
            async with db.begin_nested():
                await _map_section(db, out, project_id=project_id, section_id=sid, year=year,
                                   template_type=template_type, user_id=user_id, tree=tree)
        except Exception as exc:  # noqa: BLE001 —— 一章失败只回滚这一章，原因回报
            logger.warning("合并附注自动映射 %s 失败: %s", sid, exc, exc_info=True)
            out = SectionAutoMap(section_id=sid, status="failed",
                                 reason=f"自动映射失败：{getattr(exc, 'message', None) or exc}"[:200])
        results.append(out)

    def count(status: str) -> int:
        return sum(1 for r in results if r.status == status)

    return {
        "template_type": template_type,
        "sections": [r.to_dict() for r in results],
        "summary": {
            "sections": len(results), "mapped": count("mapped"), "partial": count("partial"),
            "pending": count("pending"), "skipped": count("skipped"), "failed": count("failed"),
            "templates_created": sum(1 for r in results if r.template_action in ("created", "versioned")),
            "confirmed_entities": sum(len(r.confirmed) for r in results),
            "pending_entities": sum(len(r.pending) for r in results),
        },
    }
