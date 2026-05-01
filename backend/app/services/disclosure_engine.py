"""附注生成引擎 — 模版驱动生成 + 数值自动填充 + 增量更新

核心功能：
- generate_notes: 根据附注模版种子数据生成附注初稿
- populate_table_data: 从试算表取数填充附注表格
- update_note_values: 增量更新受影响附注数值
- on_reports_updated: EventBus 事件处理器

Validates: Requirements 4.2, 4.3, 4.4, 4.7, 4.8, 4.9, 4.10, 8.1
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.audit_platform_schemas import EventPayload
from app.models.core import Project
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    SourceTemplate,
)
from app.services.note_template_service import NoteTemplateService

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_templates_seed.json"


def _load_seed_data() -> dict:
    """加载附注模版种子数据"""
    with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _extract_basic_info(wizard_state: dict | None) -> dict:
    state = wizard_state or {}
    return (
        state.get("steps", {}).get("basic_info", {}).get("data")
        or state.get("basic_info", {}).get("data")
        or {}
    )


class DisclosureEngine:
    """附注生成引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_project_basic_info(self, project_id: UUID) -> dict:
        result = await self.db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            return {}

        template_service = NoteTemplateService()
        wizard_state, _, changed = template_service.backfill_locked_template_snapshot(project.wizard_state)
        if changed:
            project.wizard_state = wizard_state
            await self.db.flush()
        return _extract_basic_info(project.wizard_state)

    async def _get_custom_template_sections(self, project_id: UUID) -> list[dict]:
        basic_info = await self._get_project_basic_info(project_id)
        template_service = NoteTemplateService()
        locked_snapshot = template_service.get_locked_template_snapshot(basic_info)
        if locked_snapshot is not None:
            return locked_snapshot.get("sections", [])

        template_id = basic_info.get("custom_template_id")
        if not template_id:
            logger.warning("project %s has no custom_template_id in wizard_state", project_id)
            raise HTTPException(status_code=400, detail="当前项目未绑定有效的自定义附注模板，请先在项目基本信息中选择")

        template = template_service.get_template(template_id)
        if template is None:
            logger.warning("custom note template %s not found for project %s", template_id, project_id)
            raise HTTPException(status_code=400, detail="当前项目绑定的自定义附注模板不存在或已失效，请重新选择")
        return template.get("sections", [])

    async def _load_templates(self, project_id: UUID, template_type: str) -> list[dict]:
        if template_type == "custom":
            sections = await self._get_custom_template_sections(project_id)
            return [
                {
                    "note_section": section.get("section_number", f"五、{idx + 1}"),
                    "section_title": section.get("section_title", ""),
                    "account_name": section.get("account_name") or section.get("section_title", ""),
                    "content_type": section.get("content_type")
                    or (
                        "mixed"
                        if section.get("table_template") and section.get("text_template")
                        else "table"
                        if section.get("table_template")
                        else "text"
                    ),
                    "sort_order": idx * 10,
                    "table_template": section.get("table_template") or {},
                    "text_template": section.get("text_template"),
                }
                for idx, section in enumerate(sections)
            ]

        # 从国企版/上市版完整模板文件加载
        if template_type == "listed":
            tpl_path = Path(__file__).resolve().parent.parent.parent / "data" / "note_template_listed.json"
        else:
            tpl_path = Path(__file__).resolve().parent.parent.parent / "data" / "note_template_soe.json"

        try:
            with open(tpl_path, encoding="utf-8-sig") as f:
                tpl_data = json.load(f)
            sections = tpl_data.get("sections", [])
        except Exception:
            # 降级到旧种子数据
            seed = _load_seed_data()
            sections_raw = seed.get("account_mapping_template", [])
            return sections_raw

        return [
            {
                "note_section": s.get("section_number", f"五、{idx + 1}"),
                "section_title": s.get("section_title", ""),
                "account_name": s.get("account_name") or s.get("section_title", ""),
                "content_type": s.get("content_type", "table"),
                "sort_order": idx * 10,
                "table_template": s.get("table_template") or {},
                "tables": s.get("tables", []),
                "text_template": s.get("text_template"),
                "text_sections": s.get("text_sections", []),
                "check_presets": s.get("check_presets", []),
                "wide_table_presets": s.get("wide_table_presets", []),
                "scope": s.get("scope", "both"),
            }
            for idx, s in enumerate(sections)
        ]

    async def _get_active_template_type(self, project_id: UUID) -> str:
        basic_info = await self._get_project_basic_info(project_id)
        template_type = basic_info.get("template_type")
        return template_type if isinstance(template_type, str) and template_type else "soe"

    @staticmethod
    def _persist_source_template(template_type: str) -> SourceTemplate | None:
        if template_type == SourceTemplate.soe.value:
            return SourceTemplate.soe
        if template_type == SourceTemplate.listed.value:
            return SourceTemplate.listed
        return None

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # LLM 辅助正文生成（预留接口）
    # ------------------------------------------------------------------
    async def _generate_text_with_llm(
        self,
        project_id: UUID,
        year: int,
        note_section: str,
        section_title: str,
        account_name: str,
        prompt_key: str | None = None,
    ) -> str | None:
        """调用LLM生成附注正文（每个章节可配置独立提示词）

        提示词优先级：
        1. prompt_key 指定的自定义提示词
        2. 按 section_title 匹配预设提示词
        3. 通用附注生成提示词

        返回 None 表示LLM不可用或未配置，降级到模板默认文字。
        """
        try:
            from app.services.llm_client import llm_client
            if not llm_client:
                return None

            # 构建上下文
            context_parts = [
                f"科目: {account_name}",
                f"章节: {note_section} {section_title}",
                f"年度: {year}",
            ]

            # 从试算表获取关键数据
            tb_data = getattr(self, '_tb_cache', {})
            tb_entry = tb_data.get(account_name)
            if tb_entry:
                context_parts.append(f"期末审定数: {tb_entry.get('audited', 0):,.2f}")
                context_parts.append(f"期初余额: {tb_entry.get('opening', 0):,.2f}")

            context = "\n".join(context_parts)

            # 提示词（预留自定义接口）
            system_prompt = (
                "你是一名资深审计师，正在编写财务报表附注。"
                "请根据提供的科目信息和数据，生成该章节的附注正文。"
                "要求：专业准确、符合企业会计准则披露要求、语言简洁。"
                "如果数据不足，请生成标准模板文字并标注需要补充的信息。"
            )

            result = await llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请为以下附注章节生成正文：\n\n{context}"},
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            if result and result.get("content"):
                return result["content"]
        except Exception as e:
            logger.debug("LLM text generation skipped for %s: %s", note_section, e)

        return None

    # ------------------------------------------------------------------
    # 构建附注表格数据
    # ------------------------------------------------------------------
    async def _preload_data_for_notes(self, project_id: UUID, year: int):
        """预加载底稿和试算表数据到缓存，避免 generate_notes 中165次重复查询"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        # 底稿数据
        try:
            wp_result = await self.db.execute(
                sa.select(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.parsed_data.isnot(None),
                )
            )
            for wp in wp_result.scalars().all():
                pd = wp.parsed_data or {}
                audited = pd.get("audited_amount")
                unadjusted = pd.get("unadjusted_amount")
                if audited is not None or unadjusted is not None:
                    idx_r = await self.db.execute(
                        sa.select(WpIndex.wp_code, WpIndex.wp_name).where(WpIndex.id == wp.wp_index_id)
                    )
                    idx = idx_r.first()
                    if idx:
                        self._wp_cache[idx[0]] = {
                            "audited": float(audited) if audited is not None else None,
                            "unadjusted": float(unadjusted) if unadjusted is not None else None,
                            "opening": None,
                        }
        except Exception as _wp_err:
            logger.warning("preload wp data failed: %s", _wp_err)
            try:
                await self.db.rollback()
            except Exception:
                pass

        # 底稿→科目映射
        try:
            mapping_file = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
            if mapping_file.exists():
                with open(mapping_file, "r", encoding="utf-8-sig") as f:
                    mappings = json.load(f).get("mappings", [])
                for m in mappings:
                    self._wp_account_cache[m.get("wp_code", "")] = m.get("account_name", "")
        except Exception:
            pass

        # 试算表数据
        try:
            result = await self.db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == project_id,
                    TrialBalance.year == year,
                    TrialBalance.is_deleted == sa.false(),
                )
            )
            for tb in result.scalars().all():
                code = tb.standard_account_code or tb.account_code or ""
                name = tb.account_name or tb.standard_account_name or ""
                entry = {
                    "audited": float(tb.audited_amount or 0),
                    "unadjusted": float(tb.unadjusted_amount or 0),
                    "opening": float(tb.opening_balance or 0),
                }
                self._tb_cache[name] = entry
                if code:
                    self._tb_cache[code] = entry
        except Exception as _tb_err:
            logger.warning("preload tb data failed: %s", _tb_err)
            try:
                await self.db.rollback()
            except Exception:
                pass

    async def _build_table_data(
        self,
        project_id: UUID,
        year: int,
        table_template: dict,
    ) -> dict | None:
        """从模板构建 table_data，优先从底稿parsed_data取数，降级从试算表取数。

        取数优先级：底稿parsed_data > 试算表 > 空值
        返回格式：{ headers: [...], rows: [{ label, values, is_total, ... }] }
        """
        if not table_template:
            return None

        headers = table_template.get("headers", ["项目", "期末余额", "期初余额"])
        template_rows = table_template.get("rows", [])
        if not template_rows:
            return {"headers": headers, "rows": []}

        # 使用预加载缓存（如果有），否则查询数据库
        wp_data = getattr(self, '_wp_cache', None)
        wp_account_map = getattr(self, '_wp_account_cache', None)
        tb_map = getattr(self, '_tb_cache', None)

        if wp_data is None:
            wp_data = {}
            try:
                from app.models.workpaper_models import WorkingPaper, WpIndex
                wp_result = await self.db.execute(
                    sa.select(WorkingPaper).where(
                        WorkingPaper.project_id == project_id,
                        WorkingPaper.is_deleted == sa.false(),
                        WorkingPaper.parsed_data.isnot(None),
                    )
                )
                for wp in wp_result.scalars().all():
                    pd = wp.parsed_data or {}
                    audited = pd.get("audited_amount")
                    unadjusted = pd.get("unadjusted_amount")
                    if audited is not None or unadjusted is not None:
                        idx_r = await self.db.execute(
                            sa.select(WpIndex.wp_code, WpIndex.wp_name).where(WpIndex.id == wp.wp_index_id)
                        )
                        idx = idx_r.first()
                        if idx:
                            wp_data[idx[0]] = {
                                "audited": float(audited) if audited is not None else None,
                                "unadjusted": float(unadjusted) if unadjusted is not None else None,
                                "opening": None,
                            }
            except Exception:
                pass

        if wp_account_map is None:
            wp_account_map = {}
            try:
                mapping_file = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
                if mapping_file.exists():
                    with open(mapping_file, "r", encoding="utf-8-sig") as f:
                        mappings = json.load(f).get("mappings", [])
                    for m in mappings:
                        wp_account_map[m.get("wp_code", "")] = m.get("account_name", "")
            except Exception:
                pass

        if tb_map is None:
            tb_map = {}
            try:
                result = await self.db.execute(
                    sa.select(TrialBalance).where(
                        TrialBalance.project_id == project_id,
                        TrialBalance.year == year,
                        TrialBalance.is_deleted == sa.false(),
                    )
                )
                for tb in result.scalars().all():
                    code = tb.standard_account_code or tb.account_code or ""
                    name = tb.account_name or tb.standard_account_name or ""
                    tb_map[name] = {
                        "audited": float(tb.audited_amount or 0),
                        "unadjusted": float(tb.unadjusted_amount or 0),
                        "opening": float(tb.opening_balance or 0),
                    }
                    if code:
                        tb_map[code] = tb_map[name]
            except Exception:
                pass

        # 构建底稿数据按科目名索引（优先级高于试算表）
        wp_by_account: dict[str, dict] = {}
        for wp_code, data in wp_data.items():
            account_name = wp_account_map.get(wp_code, "")
            if account_name:
                wp_by_account[account_name] = data

        rows = []
        for tr in template_rows:
            label = tr.get("label", "")
            is_total = tr.get("is_total", False)
            account_codes = tr.get("account_codes", [])

            values = []
            num_value_cols = len(headers) - 1
            for col_idx in range(num_value_cols):
                val = None
                if not is_total and (label or account_codes):
                    # 优先从底稿取数
                    wp_entry = wp_by_account.get(label)
                    if wp_entry and wp_entry.get("audited") is not None:
                        if col_idx == 0:
                            val = wp_entry.get("audited")
                        elif col_idx == 1:
                            val = wp_entry.get("opening")
                    else:
                        # 降级从试算表取数
                        tb_entry = tb_map.get(label) or (tb_map.get(account_codes[0]) if account_codes else None)
                        if tb_entry:
                            if col_idx == 0:
                                val = tb_entry.get("audited", 0)
                            elif col_idx == 1:
                                val = tb_entry.get("opening", 0)
                values.append(val)

            if is_total and rows:
                for ci in range(num_value_cols):
                    total = sum(
                        (r["values"][ci] or 0) for r in rows if not r.get("is_total") and r["values"][ci] is not None
                    )
                    values[ci] = total if total != 0 else None

            rows.append({
                "label": label,
                "values": values,
                "is_total": is_total,
            })

        return {"headers": headers, "rows": rows}

    # ------------------------------------------------------------------
    # 生成附注
    # ------------------------------------------------------------------
    async def generate_notes(
        self,
        project_id: UUID,
        year: int,
        template_type: str = "soe",
    ) -> list[dict]:
        """根据模版生成附注初稿，写入 disclosure_notes 表。

        Validates: Requirements 4.2, 4.3, 4.8, 4.9
        """
        templates = await self._load_templates(project_id, template_type)
        source_template = self._persist_source_template(template_type)
        results = []

        # 预加载底稿和试算表数据（避免165次重复查询导致事务超时）
        self._wp_cache = {}
        self._tb_cache = {}
        self._wp_account_cache = {}
        try:
            await self._preload_data_for_notes(project_id, year)
        except Exception as _pre_err:
            logger.warning("preload data for notes failed: %s", _pre_err)
            try:
                await self.db.rollback()
            except Exception:
                pass

        for tmpl in templates:
            note_section = tmpl["note_section"]
            section_title = tmpl["section_title"]
            account_name = tmpl.get("account_name") or section_title
            content_type_str = tmpl.get("content_type", "table")
            sort_order = tmpl.get("sort_order", 0)
            
            # 正文内容：三级优先填充策略
            # 1. 上年审计报告附注（如有）→ 2. LLM生成（预留接口）→ 3. 模板默认文字
            text_sections = tmpl.get("text_sections", [])
            text_content = None

            # 优先级1：从上年附注拉取（连续审计场景）
            try:
                prior_note = await self.db.execute(
                    sa.select(DisclosureNote.text_content).where(
                        DisclosureNote.project_id == project_id,
                        DisclosureNote.year == year - 1,
                        DisclosureNote.note_section == note_section,
                        DisclosureNote.is_deleted == sa.false(),
                        DisclosureNote.text_content.isnot(None),
                    )
                )
                prior_text = prior_note.scalar_one_or_none()
                if prior_text and len(prior_text) > 20:
                    text_content = prior_text
                    logger.info("note %s: filled from prior year", note_section)
            except Exception:
                pass

            # 优先级2：LLM生成（预留接口，通过 note_prompts 配置每章节独立提示词）
            if not text_content:
                try:
                    llm_text = await self._generate_text_with_llm(
                        project_id, year, note_section, section_title, account_name,
                        tmpl.get("llm_prompt_key"),
                    )
                    if llm_text and len(llm_text) > 20:
                        text_content = llm_text
                except Exception:
                    pass

            # 优先级3：模板默认文字
            if not text_content:
                text_content = "\n\n".join(text_sections) if text_sections else tmpl.get("text_template")

            if text_content and content_type_str == "table":
                content_type_str = "mixed"  # 有正文就升级为 mixed

            # 构建 table_data：支持多表格（tables 数组）
            table_data = None
            try:
                tables_list = tmpl.get("tables", [])
                if tables_list:
                    # 多表格模式
                    built_tables = []
                    for tbl in tables_list:
                        built = await self._build_table_data(
                            project_id, year,
                            {"headers": tbl.get("headers", []), "rows": tbl.get("rows", [])},
                        )
                        if built:
                            built["name"] = tbl.get("name", "")
                        built_tables.append(built or {"name": tbl.get("name", ""), "headers": tbl.get("headers", []), "rows": []})
                    # 存储为独立的 _tables 数组，避免循环引用
                    if built_tables:
                        table_data = {
                            "headers": built_tables[0].get("headers", []),
                            "rows": built_tables[0].get("rows", []),
                            "name": built_tables[0].get("name", ""),
                            "_tables": built_tables,
                        }
                elif content_type_str in ("table", "mixed"):
                    table_data = await self._build_table_data(
                        project_id, year, tmpl.get("table_template", {}),
                    )
            except Exception as _tbl_err:
                logger.warning("build table_data failed for %s: %s", note_section, _tbl_err)
                table_data = None

            # Upsert into disclosure_notes
            existing = await self.db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == note_section,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
            note = existing.scalar_one_or_none()

            if note:
                note.section_title = section_title
                note.account_name = account_name
                note.content_type = ContentType(content_type_str)
                note.table_data = table_data
                note.text_content = text_content
                note.source_template = source_template
                note.sort_order = sort_order
            else:
                note = DisclosureNote(
                    project_id=project_id,
                    year=year,
                    note_section=note_section,
                    section_title=section_title,
                    account_name=account_name,
                    content_type=ContentType(content_type_str),
                    table_data=table_data,
                    text_content=text_content,
                    source_template=source_template,
                    status=NoteStatus.draft,
                    sort_order=sort_order,
                )
                self.db.add(note)

            results.append({
                "note_section": note_section,
                "section_title": section_title,
                "account_name": account_name,
                "content_type": content_type_str,
            })

        await self.db.flush()

        # ── Phase 16: 版本链写入 ──
        try:
            from app.services.version_line_service import version_line_service
            latest = await version_line_service.get_latest_version(
                self.db, project_id, "note", project_id
            )
            await version_line_service.write_stamp(
                db=self.db,
                project_id=project_id,
                object_type="note",
                object_id=project_id,
                version_no=latest + 1,
            )
        except Exception as _vl_err:
            import logging
            logging.getLogger(__name__).warning(f"[VERSION_LINE] note write_stamp failed: {_vl_err}")

        return results

    # ------------------------------------------------------------------
    # 增量更新
    # ------------------------------------------------------------------
    async def update_note_values(
        self,
        project_id: UUID,
        year: int,
        changed_accounts: list[str] | None = None,
    ) -> int:
        """增量更新受影响附注的数值。

        简单实现：重新生成所有附注的 table_data。
        Validates: Requirements 8.1
        """
        template_type = await self._get_active_template_type(project_id)
        templates = await self._load_templates(project_id, template_type)
        updated = 0

        for tmpl in templates:
            content_type_str = tmpl.get("content_type", "table")
            if content_type_str not in ("table", "mixed"):
                continue

            note_section = tmpl["note_section"]
            table_template = tmpl.get("table_template", {})

            if changed_accounts:
                referenced_codes = set()
                for row in table_template.get("rows", []):
                    referenced_codes.update(row.get("account_codes", []))
                if referenced_codes and not referenced_codes.intersection(set(changed_accounts)):
                    continue

            table_data = await self._build_table_data(
                project_id, year, table_template,
            )

            existing = await self.db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == note_section,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
            note = existing.scalar_one_or_none()
            if note:
                note.table_data = table_data
                updated += 1

        await self.db.flush()
        return updated

    # ------------------------------------------------------------------
    # 获取附注
    # ------------------------------------------------------------------
    async def get_notes_tree(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict]:
        """获取附注目录树"""
        result = await self.db.execute(
            sa.select(DisclosureNote)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            )
            .order_by(DisclosureNote.sort_order)
        )
        notes = result.scalars().all()
        return [
            {
                "note_section": n.note_section,
                "section_title": n.section_title,
                "account_name": n.account_name,
                "content_type": n.content_type.value if n.content_type else None,
                "status": n.status.value if n.status else "draft",
                "sort_order": n.sort_order,
            }
            for n in notes
        ]

    async def get_note_detail(
        self,
        project_id: UUID,
        year: int,
        note_section: str,
    ) -> DisclosureNote | None:
        """获取指定附注章节详情

        如果 table_data 为空但模板有表格定义，自动从模板重建表格结构。
        """
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        note = result.scalar_one_or_none()

        # 自动修复：table_data 为空时从模板重建
        if note and not note.table_data and note.content_type in (ContentType.table, ContentType.mixed):
            try:
                template_type = "soe"
                if note.source_template and "listed" in str(note.source_template):
                    template_type = "listed"
                templates = await self._load_templates(project_id, template_type)
                tmpl = next((t for t in templates if t.get("note_section") == note_section), None)
                if tmpl:
                    tables_list = tmpl.get("tables", [])
                    if tables_list:
                        built_tables = []
                        for tbl in tables_list:
                            built = await self._build_table_data(
                                project_id, year,
                                {"headers": tbl.get("headers", []), "rows": tbl.get("rows", [])},
                            )
                            if built:
                                built["name"] = tbl.get("name", "")
                            built_tables.append(built or {"name": tbl.get("name", ""), "headers": tbl.get("headers", []), "rows": []})
                        if built_tables:
                            note.table_data = {
                                "headers": built_tables[0].get("headers", []),
                                "rows": built_tables[0].get("rows", []),
                                "name": built_tables[0].get("name", ""),
                                "_tables": built_tables,
                            }
                    elif tmpl.get("table_template"):
                        note.table_data = await self._build_table_data(
                            project_id, year, tmpl["table_template"],
                        )
                    if note.table_data:
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(note, "table_data")
                        await self.db.flush()
                        await self.db.commit()
            except Exception as e:
                logger.warning("auto rebuild table_data failed for %s: %s", note_section, e)

        return note

    async def update_note(
        self,
        note_id: UUID,
        table_data: dict | None = None,
        text_content: str | None = None,
        status: NoteStatus | None = None,
    ) -> DisclosureNote | None:
        """更新附注章节内容。

        Validates: Requirements 4.10
        """
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.id == note_id,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        note = result.scalar_one_or_none()
        if note is None:
            return None

        if table_data is not None:
            note.table_data = table_data
            # JSONB 字段需要显式标记为已修改，确保 _tables 等嵌套字段被持久化
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(note, "table_data")
        if text_content is not None:
            note.text_content = text_content
        if status is not None:
            note.status = status

        await self.db.flush()
        return note

    # ------------------------------------------------------------------
    # 事件处理器
    # ------------------------------------------------------------------
    async def on_reports_updated(self, payload: EventPayload) -> None:
        """监听 reports_updated 事件，触发附注增量更新。

        Validates: Requirements 8.1
        """
        logger.info(
            "on_reports_updated: project=%s, accounts=%s",
            payload.project_id, payload.account_codes,
        )
        year = payload.year
        if not year:
            logger.warning("on_reports_updated: missing year, skipping")
            return

        await self.update_note_values(
            payload.project_id, year, payload.account_codes,
        )
        await self.db.flush()

    # ------------------------------------------------------------------
    # 上年数据查询（Phase 11 Task 5.1 / 5.2）
    # ------------------------------------------------------------------
    async def get_prior_year_data(
        self, project_id: UUID, year: int, note_section: str,
    ) -> dict | None:
        """查询上年（year-1）同一附注章节的 table_data，用于前端双列对比。"""
        prior_year = year - 1
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == prior_year,
                DisclosureNote.note_section == note_section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        note = result.scalar_one_or_none()
        if note:
            return {
                "year": prior_year,
                "table_data": note.table_data,
                "text_content": note.text_content,
            }
        # 兜底：从上年试算表取审定数
        return await self._get_prior_from_trial_balance(project_id, prior_year, note_section)

    async def _get_prior_from_trial_balance(
        self, project_id: UUID, year: int, note_section: str,
    ) -> dict | None:
        """从上年试算表取审定数，构造简化的上年数据。"""
        # 通过 note_section 找到关联的科目编码（从种子数据映射）
        seed = _load_seed_data()
        account_codes: list[str] = []
        for section in seed.get("sections", []):
            if section.get("note_section") == note_section:
                account_codes = section.get("account_codes", [])
                break
        if not account_codes:
            return None

        result = await self.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.audited_amount,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        rows = result.all()
        if not rows:
            return None
        amounts = {r.standard_account_code: float(r.audited_amount or 0) for r in rows}
        return {"year": year, "table_data": None, "amounts": amounts}
