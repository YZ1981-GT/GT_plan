"""NotePriorYearImportService — 上年附注导入与继承

Requirements: 51.1, 51.2, 51.3, 51.4, 51.5, 51.7, 51.8

- 上年附注 .docx：按标题对上本年章节，填正文（内容模板写过的不覆盖；上年正文只是「本期无此项业务。」这类占位话的
  不导入，R7.3）与表格期初列（上年期末 → 本年期初，只填空格），
  标记「待更新」。表格逐张规划见 ``note_prior_year_plan``（spec consol-note-header-library-and-node-reaggregate R6.6）：
  ``mode="auto"`` 只写自动认出的表（原端点行为），``preview`` 只返回逐表规划，``apply`` 按用户逐表确认写入
  （重传文件、校验 sha256，服务端不存临时文件）。
- 连续审计项目从本库上一年度附注继承正文。
"""
from __future__ import annotations

import copy
import hashlib
import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.note_edit_stamp import stamp_note_edit
from app.services.note_prior_year_plan import (
    STATUS_AUTO,
    STATUS_CONFIRM,
    STATUS_NONE,
    PriorDoc,
    TablePlan,
    apply_col_map,
    match_sections,
    note_tables,
    parse_prior_docx,
    plan_note_tables,
)

logger = logging.getLogger(__name__)

IMPORT_MODES = ("auto", "preview", "apply")


def _importable_text(text: str | None) -> bool:
    """上年正文值得导入 / 继承：有字，且不只是「本期无此项业务。」这类占位话（与交付件过滤同一判定，R7.3）。"""
    from app.services.note_deliverable_filter import is_placeholder_text

    return bool((text or "").strip()) and not is_placeholder_text(text)


class PriorYearImportError(ValueError):
    """请求与预览 / 文件对不上：``status`` 供路由转 400 / 409，消息是给用户看的中文。"""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _decisions(raw: Any, plans: list[TablePlan], doc: PriorDoc) -> dict[str, tuple[str, dict[int, int]]]:
    """用户逐表确认 → {本年表键: (上年表, 本年列 → 上年列)}；``prior_table_id`` 为空 = 不导入。逐项校验，不合法整单拒绝。"""
    if not isinstance(raw, list):
        raise PriorYearImportError("确认内容格式不对，请重新预览")
    by_key = {p.key: p for p in plans}
    out: dict[str, tuple[str, dict[int, int]]] = {}
    for i, item in enumerate(raw, 1):
        plan = by_key.get(item.get("key")) if isinstance(item, dict) else None
        if plan is None:
            raise PriorYearImportError(f"第 {i} 项确认对不上本年附注的表格（附注可能已被修改），请重新预览")
        tid = item.get("prior_table_id")
        if not tid:
            continue
        prior = doc.tables.get(str(tid))
        if prior is None:
            raise PriorYearImportError(f"第 {i} 项指定的上年表格不存在，请重新预览")
        opening = {k.index for k in plan.opening}
        col_map: dict[int, int] = {}
        try:
            pairs = [(int(c), int(p)) for c, p in (item.get("col_map") or {}).items()]
        except (TypeError, ValueError, AttributeError):
            pairs = None
        if pairs is None or any(c not in opening or not 0 < p < len(prior.keys) for c, p in pairs):
            raise PriorYearImportError(f"「{plan.section_title}」{plan.table_name or '表格'}：列对应不合法，请重新预览")
        col_map.update(pairs)
        if col_map:
            out[plan.key] = (prior.id, col_map)
    return out


def _summary(doc: PriorDoc, notes: list[Any], sections: list[int | None]) -> dict[str, Any]:
    """章节对应概况：对上的本年章节；没对上、也不在已对上标题之下、且有内容的上年标题。"""
    matched = {h for h in sections if h is not None}

    def covered(index: int | None) -> bool:
        while index is not None:
            if index in matched:
                return True
            index = doc.headings[index].parent
        return False

    unmatched = [h.title for h in doc.headings if (h.text or h.tables) and not covered(h.index)]
    return {
        "matched": len(matched),
        "unmatched": len(unmatched),
        "matched_sections": [n.section_title for n, h in zip(notes, sections) if h is not None][:20],
        "unmatched_sections": unmatched[:20],
        "total_prior_sections": len(doc.headings),
    }


class NotePriorYearImportService:
    """Service for importing prior year notes from .docx or database."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_from_docx(
        self,
        project_id: UUID,
        year: int,
        file_bytes: bytes,
        *,
        user_id: UUID | None = None,
        mode: str = "auto",
        decisions: Any = None,
        file_sha256: str | None = None,
        import_text: bool = True,
    ) -> dict[str, Any]:
        """上年附注 .docx → 本年附注（只 flush）。

        ``mode``：``auto`` 写正文与自动认出的表（期初列全部对上、有表名或位置证据），响应多报待确认表数；
        ``preview`` 只返回章节对应与逐表规划（不写）；``apply`` 按 ``decisions`` 逐表写入，``file_sha256`` 须与本次上传一致。
        Requirements: 51.1, 51.2, 51.3, 51.4, 51.5
        """
        if mode not in IMPORT_MODES:
            raise PriorYearImportError(f"未知导入方式：{mode}")
        try:
            doc = parse_prior_docx(file_bytes)
        except Exception:  # noqa: BLE001  不是合法 Word（损坏 / 改了扩展名）
            logger.info("上年附注解析失败", exc_info=True)
            doc = None
        if doc is None or not (doc.headings or doc.tables):
            return {"status": "error", "message": "无法解析文档内容，请确认文件格式正确", "matched": 0, "unmatched": 0}
        sha = hashlib.sha256(file_bytes).hexdigest()
        if mode == "apply" and file_sha256 != sha:
            raise PriorYearImportError("上传的文件与预览时的文件不同，请重新预览", status=409)

        from app.models.report_models import DisclosureNote

        notes = list((await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            ).order_by(DisclosureNote.sort_order, DisclosureNote.note_section)
        )).scalars().all())
        if not notes:
            return {"status": "error", "message": "本年附注尚未生成，请先生成附注再导入上年数据",
                    "matched": 0, "unmatched": len(doc.headings)}

        sections = match_sections([n.section_title or "" for n in notes], doc)
        plans: list[TablePlan] = []
        for note, h in zip(notes, sections):
            plans += plan_note_tables(
                {"id": note.id, "note_section": note.note_section, "section_title": note.section_title,
                 "table_data": note.table_data},
                doc.headings[h] if h is not None else None, doc)
        counts = {s: sum(1 for p in plans if p.status == s) for s in (STATUS_AUTO, STATUS_CONFIRM, STATUS_NONE)}
        summary = _summary(doc, notes, sections)

        if mode == "preview":
            note_by_id = {str(n.id): n for n in notes}
            tables = []
            for plan in plans:
                item = plan.to_dict()
                table = note_tables(note_by_id[plan.note_id].table_data)[plan.table_index]
                # 有列对应的候选表各能填进几个空格（弹窗改选上年表时据此核对；行名对不上 / 本年已有值 ⇒ 0）；
                # 一列都对不上的不给数（「可填 0 格」会被读成行名对不上）
                item["candidate_fillable"] = {
                    tid: apply_col_map(copy.deepcopy(table), doc.tables[tid].word, cmap)
                    for tid, cmap in plan.candidate_maps.items() if cmap
                }
                item["fillable"] = item["candidate_fillable"].get(plan.prior_table_id, 0) if plan.col_map else 0
                tables.append(item)
            return {
                "status": "preview", "file_sha256": sha, **summary, "counts": counts, "tables": tables,
                "text_sections": sum(1 for n, h in zip(notes, sections)
                                     if h is not None and _importable_text(doc.headings[h].text) and not n.is_local_override),
                "prior_tables": [
                    {"id": t.id, "section": doc.headings[t.heading].title if t.heading is not None else "",
                     "caption": t.caption, "columns": t.columns(), "row_count": len(t.word.rows)}
                    for t in doc.tables.values()
                ],
            }

        chosen = (_decisions(decisions, plans, doc) if mode == "apply"
                  else {p.key: (p.prior_table_id, p.col_map) for p in plans if p.status == STATUS_AUTO})
        todo: dict[str, dict[int, tuple[str, dict[int, int]]]] = defaultdict(dict)
        for plan in plans:
            if plan.key in chosen:
                todo[plan.note_id][plan.table_index] = chosen[plan.key]
        filled_cells = tables_written = text_filled = 0
        changed_sections: list[str] = []
        for note, h in zip(notes, sections):
            changed = False
            text = doc.headings[h].text if h is not None else ""
            if import_text and _importable_text(text) and not note.is_local_override and note.text_content != text:
                note.text_content = text
                changed = True
                text_filled += 1
            work = todo.get(str(note.id))
            if work and isinstance(note.table_data, dict):
                td = copy.deepcopy(note.table_data)
                tables = note_tables(td)
                mirror = isinstance(td.get("_tables"), list) and isinstance(td.get("rows"), list)
                filled = 0
                for index, (tid, col_map) in work.items():
                    n = apply_col_map(tables[index], doc.tables[tid].word, col_map)
                    if index == 0 and mirror:
                        apply_col_map(td, doc.tables[tid].word, col_map)  # 顶层镜像第一张表
                    filled += n
                    tables_written += int(n > 0)
                if filled:
                    note.table_data = td  # 整体赋值：原地改 JSONB 不会被识别为改动
                    filled_cells += filled
                    changed = True
            if changed:
                lineage = dict(note.template_lineage) if isinstance(note.template_lineage, dict) else {}
                lineage["prior_year_imported"] = True
                lineage["prior_year_status"] = "pending_update"
                note.template_lineage = lineage
                stamp_note_edit(note, user_id)
                changed_sections.append(note.note_section)
        await self.db.flush()
        return {
            "status": "success", **summary, "filled_cells": filled_cells, "tables_written": tables_written,
            "text_filled": text_filled, "pending_tables": counts[STATUS_CONFIRM] if mode == "auto" else 0,
            "no_source_tables": counts[STATUS_NONE], "changed_sections": changed_sections,
        }

    async def inherit_from_prior_year(
        self,
        project_id: UUID,
        year: int,
        *,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Inherit notes from prior year database (continuous audit).

        For projects with prior year data in the same database,
        automatically copy text content and mark as "待更新".

        Requirements: 51.7, 51.8
        """
        from app.models.report_models import DisclosureNote

        prior_year = year - 1

        # Check if prior year notes exist（回收站里的不算）
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == prior_year,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        prior_notes = result.scalars().all()

        if not prior_notes:
            return {
                "status": "no_prior_data",
                "message": f"未找到 {prior_year} 年度附注数据",
                "inherited": 0,
            }

        # Load current year notes
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        current_notes = result.scalars().all()

        if not current_notes:
            return {
                "status": "error",
                "message": "本年附注尚未生成，请先生成附注",
                "inherited": 0,
            }

        # Build mapping by note_section (DisclosureNote 无 section_code 列，
        # 用 note_section 作为跨年匹配键，如 "五、1 存货")
        prior_by_section: dict[str, Any] = {}
        for pn in prior_notes:
            if pn.note_section:
                prior_by_section[pn.note_section] = pn

        inherited = 0
        for note in current_notes:
            if not note.note_section:
                continue
            prior = prior_by_section.get(note.note_section)
            if prior and _importable_text(prior.text_content):
                # 跳过 is_local_override 的章节：用户已通过内容模板写入自定义正文，
                # 上年继承不得覆盖（与 disclosure_engine / wp_disclosure_sync_service 同口径）
                if note.is_local_override or note.text_content == prior.text_content:
                    continue
                # Copy text content, mark as pending update
                note.text_content = prior.text_content
                # 在 template_lineage（JSONB）中记录继承来源（新字典赋值：原地改 JSONB 不会被识别为改动）
                lineage = dict(note.template_lineage) if isinstance(note.template_lineage, dict) else {}
                lineage["prior_year_inherited"] = True
                lineage["prior_year_status"] = "pending_update"
                lineage["prior_year_source"] = prior_year
                note.template_lineage = lineage
                stamp_note_edit(note, user_id)
                inherited += 1

        await self.db.flush()

        return {
            "status": "success",
            "inherited": inherited,
            "total_prior_notes": len(prior_notes),
            "total_current_notes": len(current_notes),
        }
