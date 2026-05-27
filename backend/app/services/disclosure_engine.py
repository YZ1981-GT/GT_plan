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
        self._wp_cache: dict = {}
        self._wp_account_cache: dict = {}
        self._tb_cache: dict = {}
        self._wp_fine_cache: dict = {}  # 底稿精细化明细行缓存

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

        # 底稿数据（汇总 + 精细化明细行）
        # 使用 JOIN 一次查完 WorkingPaper + WpIndex，消除原来的 N+1 查询
        # 只 SELECT 需要的字段，减少数据传输量
        try:
            wp_result = await self.db.execute(
                sa.select(
                    WorkingPaper.parsed_data,
                    WpIndex.wp_code,
                    WpIndex.wp_name,
                )
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.parsed_data.isnot(None),
                )
            )
            for parsed_data, wp_code, _wp_name in wp_result.all():
                if not wp_code:
                    continue
                pd = parsed_data or {}
                audited = pd.get("audited_amount")
                unadjusted = pd.get("unadjusted_amount")
                if audited is not None or unadjusted is not None:
                    self._wp_cache[wp_code] = {
                        "audited": float(audited) if audited is not None else None,
                        "unadjusted": float(unadjusted) if unadjusted is not None else None,
                        "opening": None,
                    }
                # 缓存精细化提取的明细行（fine_summary 中的 detail rows）
                fine_summary = pd.get("fine_summary", {})
                if fine_summary:
                    self._wp_fine_cache[wp_code] = fine_summary
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

        # 预加载上年附注（避免 generate_notes 循环中 165 次逐章节查询）
        try:
            prior_notes_result = await self.db.execute(
                sa.select(DisclosureNote.note_section, DisclosureNote.text_content).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year - 1,
                    DisclosureNote.is_deleted == sa.false(),
                    DisclosureNote.text_content.isnot(None),
                )
            )
            self._prior_notes_cache = {
                row.note_section: row.text_content
                for row in prior_notes_result.fetchall()
                if row.text_content and len(row.text_content) > 20
            }
        except Exception as _pn_err:
            logger.warning("preload prior notes failed: %s", _pn_err)
            self._prior_notes_cache = {}

    async def _build_table_data(
        self,
        project_id: UUID,
        year: int,
        table_template: dict,
        *,
        section_number: str | None = None,
    ) -> dict | None:
        """从模板构建 table_data，动态提取底稿明细行。

        设计原则：
        - 表格结构（表头、合计行位置、列含义）来自模板
        - 明细行数据从底稿 parsed_data.fine_summary 动态提取
        - 降级：底稿无数据时从试算表取数，再降级用模板预设行
        - 合计行自动求和
        - 单元格模式：auto（自动提数）/ manual（手动锁定）/ locked（公式锁定）

        取数优先级：底稿fine_summary明细行 > 底稿audited_amount > 试算表 > 模板预设行

        Sprint 1 Task 1.3 binding 分支（向后兼容）：
        - 当传入 ``section_number`` 且 binding 加载器命中 → 走新路径
          ``_build_with_binding``（按 binding 字段 7 source 解析器取数）
        - 未命中 / 不传 section_number → 走原 legacy 路径不变（不污染老代码）
        """
        # ── Sprint 1 Task 1.3 binding 分支 ─────────────────────────
        if section_number:
            try:
                from app.services.note_template_bindings_loader import (
                    get_binding_for_section,
                )
                sec_binding = get_binding_for_section(section_number)
            except Exception as _bl_err:
                logger.warning(
                    "binding loader failed for %s: %s; "
                    "falling back to legacy path",
                    section_number, _bl_err,
                )
                sec_binding = None
            if sec_binding:
                tables = sec_binding.get("tables") or []
                if tables and isinstance(tables[0], dict):
                    try:
                        return await self._build_with_binding(
                            project_id, year, section_number,
                            table_template, tables[0],
                        )
                    except Exception as _bind_err:
                        logger.warning(
                            "_build_with_binding failed for %s: %s; "
                            "falling back to legacy path",
                            section_number, _bind_err,
                        )
        # ── 原 legacy 路径（不修改） ───────────────────────────────
        if not table_template:
            return None

        headers = table_template.get("headers", ["项目", "期末余额", "期初余额"])
        template_rows = table_template.get("rows", [])
        if not template_rows:
            return {"headers": headers, "rows": []}

        # 使用预加载缓存
        wp_data = getattr(self, '_wp_cache', None) or {}
        wp_account_map = getattr(self, '_wp_account_cache', None) or {}
        tb_map = getattr(self, '_tb_cache', None) or {}
        # 底稿精细化提取结果缓存（detail rows）
        wp_fine_cache = getattr(self, '_wp_fine_cache', None) or {}

        # 构建底稿数据按科目名索引
        wp_by_account: dict[str, dict] = {}
        for wp_code, data in wp_data.items():
            account_name = wp_account_map.get(wp_code, "")
            if account_name:
                wp_by_account[account_name] = data

        # 检查模板是否有 detail_discovery 标记（表示明细行应动态生成）
        has_dynamic_detail = table_template.get("detail_discovery") or any(
            r.get("is_dynamic_detail") for r in template_rows
        )

        # 查找关联的底稿精细化数据（detail rows）
        # 通过附注科目名 → wp_account_map 反向查找底稿编码 → fine_cache
        wp_code_for_note = table_template.get("wp_code", "")
        if not wp_code_for_note:
            # 反向查找：从 wp_account_map 中找到科目名对应的 wp_code
            note_account = table_template.get("account_name", "")
            for wc, acct_name in (getattr(self, '_wp_account_cache', None) or {}).items():
                if acct_name == note_account:
                    wp_code_for_note = wc
                    break
        fine_detail_rows = []
        if wp_code_for_note and wp_code_for_note in wp_fine_cache:
            fine_data = wp_fine_cache[wp_code_for_note]
            # fine_data 结构：{"closing_audited": ..., "rows": {"detail_0": {...}, "total": {...}}}
            fine_rows = fine_data.get("rows", {}) if isinstance(fine_data, dict) else {}
            fine_detail_rows = [
                r for r in fine_rows.values()
                if isinstance(r, dict) and r.get("is_detail")
            ]

        num_value_cols = len(headers) - 1
        rows = []

        for tr in template_rows:
            label = tr.get("label", "")
            is_total = tr.get("is_total", False)
            account_codes = tr.get("account_codes", [])

            # 合计行：延迟计算
            if is_total:
                values = [None] * num_value_cols
                rows.append({"label": label, "values": values, "is_total": True})
                continue

            # 动态明细占位行：用底稿实际明细替换
            if tr.get("is_dynamic_detail") and fine_detail_rows:
                for dr in fine_detail_rows:
                    dr_label = dr.get("label", "")
                    dr_values = []
                    for col_idx in range(num_value_cols):
                        # 从精细化提取结果中取对应列的值
                        if col_idx == 0:
                            dr_values.append(dr.get("closing_audited") or dr.get("current_audited"))
                        elif col_idx == 1:
                            dr_values.append(dr.get("opening_audited") or dr.get("prior_audited"))
                        else:
                            dr_values.append(None)
                    rows.append({"label": dr_label, "values": dr_values, "is_detail": True})
                continue

            # 普通行：按优先级取数
            values = []
            for col_idx in range(num_value_cols):
                val = None
                if label or account_codes:
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

            rows.append({"label": label, "values": values, "is_total": False})

        # 回填合计行
        for i, row in enumerate(rows):
            if row.get("is_total") and i > 0:
                for ci in range(num_value_cols):
                    # 合计行 = 上方所有非合计行之和（到上一个合计行为止）
                    start = 0
                    for j in range(i - 1, -1, -1):
                        if rows[j].get("is_total"):
                            start = j + 1
                            break
                    total = sum(
                        (r["values"][ci] or 0) for r in rows[start:i]
                        if not r.get("is_total") and r["values"][ci] is not None
                    )
                    row["values"][ci] = total

        return {"headers": headers, "rows": rows}

    # ------------------------------------------------------------------
    # Sprint 1 Task 1.3 / 1.4 — binding 驱动的新路径
    # ------------------------------------------------------------------
    @staticmethod
    def _backfill_totals(rows: list[dict], num_value_cols: int) -> None:
        """合计/小计行回填：取上一个合计行之后到本行之前的非合计行 sum.

        与 legacy `_build_table_data` 末尾的回填算法等价（抽取为公共逻辑），
        新 binding 路径与老路径共用同一规则避免行为分裂。
        """
        for i, row in enumerate(rows):
            if not row.get("is_total"):
                continue
            if i == 0:
                continue
            for ci in range(num_value_cols):
                # 起点：上一个合计行之后；初始 0
                start = 0
                for j in range(i - 1, -1, -1):
                    if rows[j].get("is_total"):
                        start = j + 1
                        break
                total: float = 0.0
                has_val = False
                for r in rows[start:i]:
                    if r.get("is_total"):
                        continue
                    vals = r.get("values") or []
                    if ci < len(vals) and vals[ci] is not None:
                        try:
                            total += float(vals[ci])
                            has_val = True
                        except (TypeError, ValueError):
                            continue
                if has_val:
                    cur_vals = row.get("values") or []
                    if ci < len(cur_vals):
                        cur_vals[ci] = total
                        row["values"] = cur_vals

    async def _build_with_binding(
        self,
        project_id: UUID,
        year: int,
        section_number: str,
        table_template: dict,
        table_binding: dict,
    ) -> dict:
        """走 binding 驱动路径：按 header_normalize.semantic 调 7 source resolver.

        输出 row 结构兼容前端老代码 — 同时含 ``values`` + ``_cell_modes``
        + ``_cell_meta`` + ``row_type`` + ``label`` + ``is_total``（D1
        sidecar 兼容铁律）。

        合计行先 None 占位，最后用 ``_backfill_totals`` 回填。

        Args:
            project_id: 项目 UUID
            year:       附注会计年度
            section_number: 章节号（用于构造 binding_id）
            table_template: 模板表（含 headers / rows[*].label / row_type）
            table_binding:  binding json 中对应的表 dict（含 header_normalize /
                            rows[*].binding / rows[*].formula / row_type）

        Returns:
            ``{"headers": [...], "rows": [...]}``  与 legacy 同 schema.
        """
        from app.services.note_source_resolvers import dispatch_resolver

        headers = table_template.get("headers") or []
        template_rows = table_template.get("rows") or []
        if not template_rows:
            return {"headers": headers, "rows": []}

        # 构造 ctx — 注入预加载缓存 + db + project_id + year + section_number
        ctx: dict = {
            "project_id": project_id,
            "year": year,
            "db": self.db,
            "section_number": section_number,
            "_tb_cache": getattr(self, "_tb_cache", None) or {},
            "_wp_cache": getattr(self, "_wp_cache", None) or {},
            "_prior_notes_cache": getattr(self, "_prior_notes_cache", None) or {},
        }

        # binding.rows 是 dict (label -> row_binding)
        binding_rows = table_binding.get("rows") or {}
        if not isinstance(binding_rows, dict):
            binding_rows = {}

        # header_normalize 与 headers 一一对应（col 0 通常 row_label）
        header_normalize = table_binding.get("header_normalize") or []
        if not isinstance(header_normalize, list):
            header_normalize = []

        num_value_cols = max(0, len(headers) - 1)
        output_rows: list[dict] = []

        for tr in template_rows:
            if not isinstance(tr, dict):
                continue
            label = tr.get("label", "") or ""
            row_type_raw = tr.get("row_type")
            is_total_flag = bool(tr.get("is_total"))
            is_total = is_total_flag or row_type_raw in {"subtotal", "total"}

            if is_total:
                # 合计行：先 None 占位，最后回填
                output_rows.append({
                    "label": label,
                    "values": [None] * num_value_cols,
                    "is_total": True,
                    "row_type": row_type_raw or "total",
                    "_cell_modes": {},
                    "_cell_meta": {},
                })
                continue

            # 找到这行的 binding（按 label 精确匹配）
            row_binding = binding_rows.get(label) or {}
            cell_bindings = row_binding.get("binding") or {}
            if not isinstance(cell_bindings, dict):
                cell_bindings = {}

            values: list = []
            cell_modes: dict[str, str] = {}
            cell_meta: dict[str, dict] = {}

            for col_index in range(num_value_cols):
                actual_col = col_index + 1  # col 0 是行 label
                # 取该列 semantic
                semantic: str | None = None
                if actual_col < len(header_normalize) and isinstance(
                    header_normalize[actual_col], dict
                ):
                    semantic = header_normalize[actual_col].get("semantic")
                # header_normalize 缺位 → 兜底 manual
                if not semantic:
                    values.append(None)
                    cell_modes[str(col_index)] = "manual"
                    cell_meta[str(col_index)] = {
                        "manual_value": None,
                        "semantic": None,
                        "binding_id": None,
                    }
                    continue

                # 找 cell binding：先精确，再前缀（同 semantic 多列变体）
                cell = cell_bindings.get(semantic)
                if not cell:
                    prefix = semantic + "_col"
                    for k, v in cell_bindings.items():
                        if isinstance(k, str) and k.startswith(prefix):
                            cell = v
                            break
                if not isinstance(cell, dict):
                    # 缺 binding → values=None + manual placeholder
                    values.append(None)
                    cell_modes[str(col_index)] = "manual"
                    cell_meta[str(col_index)] = {
                        "manual_value": None,
                        "semantic": semantic,
                        "binding_id": None,
                    }
                    continue

                mode = cell.get("mode") or "auto"
                if mode not in {"auto", "manual", "locked"}:
                    mode = "auto"

                # 调 resolver — locked / manual 不走自动取数（值留 None 由后续合并接管）
                if mode == "locked":
                    val = None
                elif mode == "manual":
                    val = cell.get("manual_value")
                else:
                    val = await dispatch_resolver(cell, ctx)

                values.append(val)
                cell_modes[str(col_index)] = mode
                cell_meta[str(col_index)] = {
                    "manual_value": None,
                    "semantic": semantic,
                    "binding_id": f"{section_number}.{label}.{semantic}",
                }

            output_rows.append({
                "label": label,
                "values": values,
                "is_total": False,
                "row_type": row_type_raw or "data",
                "_cell_modes": cell_modes,
                "_cell_meta": cell_meta,
            })

        # 回填合计行
        self._backfill_totals(output_rows, num_value_cols)

        return {"headers": list(headers), "rows": output_rows}

    # ------------------------------------------------------------------
    # 生成附注
    # ------------------------------------------------------------------
    @staticmethod
    def select_md_template(template_type: str, report_scope: str) -> tuple[str, str]:
        """根据项目 template_type 和 report_scope 自动选择 MD 模板。

        Returns (template_type, scope) tuple for NoteMDTemplateParser.

        Requirements: 21.3
        """
        # Normalize inputs
        t = (template_type or "soe").lower().strip()
        s = (report_scope or "standalone").lower().strip()

        # Map to valid values
        if t not in ("soe", "listed"):
            t = "soe"
        if s not in ("consolidated", "standalone"):
            s = "standalone"

        return (t, s)

    async def generate_notes(
        self,
        project_id: UUID,
        year: int,
        template_type: str = "soe",
    ) -> list[dict]:
        """根据模版生成附注初稿，写入 disclosure_notes 表。

        Validates: Requirements 4.2, 4.3, 4.8, 4.9, 21.3
        """
        templates = await self._load_templates(project_id, template_type)
        source_template = self._persist_source_template(template_type)
        results = []

        # 预加载底稿和试算表数据（避免165次重复查询导致事务超时）
        self._wp_cache = {}
        self._tb_cache = {}
        self._wp_account_cache = {}
        self._wp_fine_cache = {}
        self._prior_notes_cache = {}
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

            # 优先级1：从上年附注拉取（连续审计场景）- 从预加载缓存取，避免逐章节查询
            prior_notes_cache = getattr(self, '_prior_notes_cache', {})
            prior_text = prior_notes_cache.get(note_section)
            if prior_text and len(prior_text) > 20:
                text_content = prior_text
                logger.info("note %s: filled from prior year (cache)", note_section)

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
                            section_number=note_section,
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
                        section_number=note_section,
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
                # D1 三态合并：已存在 note 且历史 table_data 非空 → 走合并保留 manual/locked
                if table_data is not None and note.table_data:
                    from sqlalchemy.orm.attributes import flag_modified

                    from app.services.note_cell_merge import (
                        merge_table_data_preserving_cell_modes,
                    )
                    note.table_data = merge_table_data_preserving_cell_modes(
                        note.table_data, table_data,
                    )
                    flag_modified(note, "table_data")
                else:
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
                # F50 / Sprint 8.19: 附注创建时绑定当前 active dataset
                try:
                    from app.services.dataset_query import bind_to_active_dataset
                    await bind_to_active_dataset(self.db, note, project_id, year)
                except Exception as _bind_err:
                    import logging
                    logging.getLogger(__name__).warning(
                        "disclosure_note dataset binding failed: section=%s err=%s",
                        note_section, _bind_err,
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

        D1 三态合并：通过 ``note_cell_merge.merge_table_data_preserving_cell_modes``
        保留用户在前端切到 manual / locked 的单元格值，仅 auto 单元格用新算的覆盖。

        Validates: Requirements 8.1, R1.3 验收 10/11/12
        """
        from sqlalchemy.orm.attributes import flag_modified

        from app.services.note_cell_merge import (
            merge_table_data_preserving_cell_modes,
        )

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

            new_td = await self._build_table_data(
                project_id, year, table_template,
                section_number=note_section,
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
                old_td = note.table_data or {}
                if old_td:
                    note.table_data = merge_table_data_preserving_cell_modes(old_td, new_td)
                else:
                    note.table_data = new_td
                # JSONB 字段需要显式标记，确保嵌套字段持久化
                flag_modified(note, "table_data")
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
                "id": str(n.id),
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
                                section_number=note_section,
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
                            section_number=note_section,
                        )
                    if note.table_data:
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(note, "table_data")
                        await self.db.flush()
                        await self.db.commit()
            except Exception as e:
                logger.warning("auto rebuild table_data failed for %s: %s", note_section, e)

        return note

    async def get_template_structure(
        self,
        project_id: UUID,
        year: int,
        note_section: str,
    ) -> dict | None:
        """获取附注章节的原始模板表格结构。

        返回模板定义的 headers 和 rows（仅结构，不含项目实际数据），
        用于前端"恢复模板结构"操作。

        Validates: Requirements 38.5, 38.6
        """
        # 确定模板类型
        template_type = await self._get_active_template_type(project_id)

        # 加载模板
        templates = await self._load_templates(project_id, template_type)
        tmpl = next((t for t in templates if t.get("note_section") == note_section), None)
        if not tmpl:
            return None

        # 从模板提取表格结构
        tables_list = tmpl.get("tables", [])
        if tables_list:
            # 多表格模板：返回第一个表格的结构（与 get_note_detail 一致）
            tbl = tables_list[0]
            headers = tbl.get("headers", [])
            template_rows = tbl.get("rows", [])
            # 构建标准化行结构
            rows = []
            for row_def in template_rows:
                if isinstance(row_def, dict):
                    rows.append({
                        "label": row_def.get("label", ""),
                        "values": [None] * max(0, len(headers) - 1),
                        "is_total": row_def.get("is_total", False),
                    })
                elif isinstance(row_def, list) and len(row_def) > 0:
                    rows.append({
                        "label": str(row_def[0]),
                        "values": [None] * max(0, len(headers) - 1),
                        "is_total": False,
                    })
            return {
                "headers": headers,
                "rows": rows,
                "name": tbl.get("name", ""),
            }

        # 单表格模板（旧格式）
        table_template = tmpl.get("table_template", {})
        if table_template:
            headers = table_template.get("headers", [])
            template_rows = table_template.get("rows", [])
            rows = []
            for row_def in template_rows:
                if isinstance(row_def, dict):
                    rows.append({
                        "label": row_def.get("label", ""),
                        "values": [None] * max(0, len(headers) - 1),
                        "is_total": row_def.get("is_total", False),
                    })
                elif isinstance(row_def, list) and len(row_def) > 0:
                    rows.append({
                        "label": str(row_def[0]),
                        "values": [None] * max(0, len(headers) - 1),
                        "is_total": False,
                    })
            if headers:
                return {
                    "headers": headers,
                    "rows": rows,
                    "name": "",
                }

        return None

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
