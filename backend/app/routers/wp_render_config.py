"""底稿渲染配置端点

GET /api/workpapers/{wp_id}/render-config
按 design §5.1.1 实现：获取底稿渲染 schema + 项目数据 + 跨底稿引用。

Requirements: 1.2, 3.0.3, 3.0.5
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import (
    WpCrossRef,
    WpIndex,
    WorkingPaper,
    WpSourceType,
)
from app.services.wp_classification_service import (
    ClassificationNotFoundError,
    ClassificationResult,
    WpClassificationService,
    derive_component_type,
)
from app.services.wp_auto_fill_service import _resolve_auto_fill_values
from app.services.wp_render_schema_service import WpRenderSchemaService
from app.services.wp_template_version_service import WpTemplateVersionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-render-config"],
)

# ─── Singleton schema service (stateless + cache) ────────────────────────────
_schema_service = WpRenderSchemaService()

# 标准底稿编号：A~I + 数字（D1-1、E11）；CUST-01 等字母后非数字则视为自建
_STANDARD_WP_CODE = re.compile(r"^[A-I]\d", re.IGNORECASE)


async def _has_custom_procedure(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> bool:
    n = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.wp_code == wp_code,
                ProcedureInstance.is_custom == True,  # noqa: E712
                ProcedureInstance.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar() or 0
    return n > 0


def _looks_like_standard_wp_code(wp_code: str) -> bool:
    return bool(_STANDARD_WP_CODE.search((wp_code or "").strip()))


async def _maybe_custom_classifications(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
    wp_name: str | None,
    classifications: list,
    working_paper: WorkingPaper,
) -> list:
    """无模板归类时，为自定义程序/自建底稿合成 CUSTOM → componentType=custom。"""
    if classifications:
        return classifications
    use_custom = await _has_custom_procedure(db, project_id, wp_code)
    if not use_custom and working_paper.source_type == WpSourceType.manual:
        use_custom = not _looks_like_standard_wp_code(wp_code)
    if not use_custom:
        return classifications
    # sheet_name 与 parsed_data.html_data 的键一致（保存时用 wp_code 作 sheet 名）
    sheet_name = wp_code
    return [
        ClassificationResult(
            wp_code=wp_code,
            sheet_name=sheet_name,
            class_code="CUSTOM",
            class_="自定义底稿",
            scope="standalone",
            is_real_workpaper=True,
            delegated_module=None,
            render_schema_path=None,
            template_version_id=None,
        )
    ]


# ─── Response schemas ────────────────────────────────────────────────────────


class CrossRefItem(BaseModel):
    wp_code: str
    cell: str | None = None


class SheetRenderConfig(BaseModel):
    sheet_name: str
    componentType: str
    schema_: dict | None = None
    html_data: dict | None = None
    cross_refs: list[CrossRefItem] = []

    class Config:
        # Allow 'schema_' to be serialized as 'schema' in JSON
        populate_by_name = True

    def model_dump(self, **kwargs):
        """Override to rename schema_ → schema in output."""
        data = super().model_dump(**kwargs)
        data["schema"] = data.pop("schema_", None)
        return data


class RenderConfigResponse(BaseModel):
    wp_id: str
    wp_code: str
    project_id: str
    scope: str
    is_real_workpaper: bool
    template_version: str | None = None
    sheets: list[dict]  # Use dict to allow custom 'schema' key


# ─── B-Index 自动生成辅助 ─────────────────────────────────────────────────


async def _build_preparation_info(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
) -> dict[str, str]:
    """编制信息 JOIN（workpaper 级表头 + B-Index 共用）。无 accounting_period。"""
    info: dict[str, str] = {
        "entity_name": "",
        "period_end": "",
        "preparer": "",
        "prep_date": "",
        "reviewer": "",
        "review_date": "",
        "index_no": "",
    }
    try:
        proj_result = await db.execute(
            sa.text("SELECT name, audit_period_end FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.first()
        if proj_row:
            info["entity_name"] = proj_row[0] or ""
            info["period_end"] = str(proj_row[1])[:10] if proj_row[1] else ""
    except Exception as e:
        logger.warning("preparation_info: 项目信息失败: %s", e)

    if not info["entity_name"]:
        try:
            from app.models.core import Project

            proj = await db.get(Project, project_id)
            if proj:
                info["entity_name"] = proj.name or ""
                if not info["period_end"] and getattr(proj, "audit_period_end", None):
                    info["period_end"] = str(proj.audit_period_end)[:10]
        except Exception as e:
            logger.warning("preparation_info: ORM 项目信息降级失败: %s", e)

    try:
        staff_result = await db.execute(
            sa.text("""
                SELECT pa.role, s.name
                FROM project_assignments pa
                JOIN staff_members s ON s.id = pa.staff_id
                WHERE pa.project_id = :pid
                  AND pa.role IN ('preparer', 'reviewer', 'partner', 'manager')
            """),
            {"pid": str(project_id)},
        )
        for role, name in staff_result:
            if role == "preparer":
                info["preparer"] = name or ""
            elif role in ("reviewer", "manager"):
                if not info["reviewer"] or role == "reviewer":
                    info["reviewer"] = name or ""
    except Exception as e:
        logger.warning("preparation_info: 人员信息失败: %s", e)

    try:
        wp_row = (
            await db.execute(
                sa.select(WorkingPaper.created_at, WpIndex.wp_code)
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(WorkingPaper.id == wp_id)
            )
        ).first()
        if wp_row:
            if wp_row[0]:
                info["prep_date"] = str(wp_row[0])[:10]
            info["index_no"] = wp_row[1] or ""
    except Exception as e:
        logger.warning("preparation_info: 底稿信息失败: %s", e)

    return info


async def _generate_b_index_data(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    classifications: list,
    audit_cycle: str | None = None,
) -> dict:
    """当 B-Index sheet 无持久化 html_data 时，从项目元数据 + 同底稿 sheets 自动生成。

    返回结构与 GtBIndex.vue 的 BIndexHtmlData 接口一致：
    {
      preparation_info: { entity_name, period_end, preparer, prep_date, reviewer, review_date, index_no },
      navigation_rows: [ { seq, content, index_ref, no_print } ],
      cycle_workpapers: [ { wp_code, wp_name, wp_id, status, is_current } ]
    }

    - navigation_rows：当前底稿内部各 sheet（同 xlsx 内 sheet 切换）。
    - cycle_workpapers：同一审计循环的所有底稿（跨底稿 router.push 跳转），
      使「底稿目录」覆盖整个循环（如 D 循环含 D0~D7），而非仅当前 xlsx。
    """
    preparation_info = await _build_preparation_info(db, project_id, wp_id)

    # ─── 索引导航行（同底稿其他 sheet → 行） ─────────────────────────────
    # sheet 级索引号嵌在 sheet_name 末尾（如「审定表D1-1」→ D1-1，
    # 「应收票据审计程序表D1A」→ D1A）；wp_code 仅父级（D1），不能用作 index_ref。
    _SHEET_INDEX_PATTERN = re.compile(r"([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$")

    navigation_rows: list[dict] = []
    seq = 1
    for cls in classifications:
        # 跳过 B-Index 自身
        try:
            ct = derive_component_type(cls)
        except Exception:
            ct = "skip"
        if ct == "b-index":
            continue

        # 从 sheet_name 末尾提取该 sheet 的真实索引号；提取不到则回退父 wp_code
        sheet_index = ""
        m = _SHEET_INDEX_PATTERN.search(cls.sheet_name or "")
        if m:
            sheet_index = m.group(1)
        else:
            sheet_index = getattr(cls, "wp_code", "") or ""

        navigation_rows.append({
            "seq": seq,
            "content": cls.sheet_name,
            "index_ref": sheet_index,
            "component_type": ct,
            "no_print": False,
        })
        seq += 1

    # ─── 循环底稿目录（跨底稿，同 audit_cycle 全部底稿） ──────────────────
    from app.services.wp_cycle_directory import build_cycle_workpapers

    cycle_workpapers = await build_cycle_workpapers(
        db=db,
        project_id=project_id,
        audit_cycle=audit_cycle,
        current_wp_id=wp_id,
    )

    return {
        "preparation_info": preparation_info,
        "navigation_rows": navigation_rows,
        "cycle_workpapers": cycle_workpapers,
    }


# ─── A-程序表中控台自动生成辅助 ────────────────────────────────────────────


async def _generate_a_program_data(
    file_path: str | None,
    sheet_name: str,
    existing: dict | None = None,
) -> dict:
    """当 a-program-console sheet 无持久化 programs 时，从模板 xlsx 提取程序清单。

    返回结构与 GtAProgramConsole.vue 的 AProgramHtmlData 接口一致：
    {
      programs: [ { id, program_no, program_desc, program_category,
                    assertions, linked_workpapers, status } ],
      trim_decisions: [],
      signatures: [...]（保留 existing 中的签字信息）
    }

    解析失败 / 文件缺失 → programs 为空列表（前端仍显示空态，不报错）。
    """
    from app.services.wp_program_extract import extract_program_rows

    programs: list[dict] = []
    if file_path:
        try:
            programs = extract_program_rows(file_path, sheet_name)
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning("A-程序表提取失败 %s/%s: %s", file_path, sheet_name, e)
            programs = []

    result: dict = {
        "programs": programs,
        "trim_decisions": [],
    }
    # 保留已有签字信息（若 sheet 之前存过部分数据）
    if existing and isinstance(existing.get("signatures"), list):
        result["signatures"] = existing["signatures"]
    return result


# ─── univer 表格类底稿网格自动生成辅助 ─────────────────────────────────────


def _has_grid_cells(html_data: dict | None) -> bool:
    """判断 sheet html_data 是否已含可渲染的网格 cells。"""
    if not isinstance(html_data, dict):
        return False
    cells = html_data.get("cells")
    return isinstance(cells, dict) and len(cells) > 0


async def _generate_grid_data(
    file_path: str | None,
    sheet_name: str,
    existing: dict | None = None,
) -> dict:
    """当 univer 类 sheet 无持久化网格数据时，从模板 xlsx 提取只读网格。

    返回结构与 GtGridSheet.vue 的 GridHtmlData 接口一致：
    { cells, merged_cells, col_widths, max_row, max_col }

    解析失败 / 文件缺失 → 空网格（前端显示空态，不报错）。
    """
    from app.services.wp_grid_extract import extract_grid

    grid: dict = {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}
    if file_path:
        try:
            grid = extract_grid(file_path, sheet_name)
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning("univer 网格提取失败 %s/%s: %s", file_path, sheet_name, e)

    # 合并已有持久化数据（若用户曾编辑过部分单元格）
    if existing and isinstance(existing.get("cells"), dict) and existing["cells"]:
        grid = {**grid, **existing}
    return grid


# ─── 审定表（audit-sheet）结构化数据自动生成辅助 ───────────────────────────


def _decimal_to_float(value: Any) -> float | None:
    """Decimal / numeric → float（None → None，转换失败 → None）。

    trial_balance 金额列是 ``Numeric(20, 2)`` → SQLAlchemy 返回 ``Decimal``。
    前端 JSON 消费 float，故统一转换；保留 None 语义（TB 列为空时前端显示「—」）。
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _fetch_audit_sheet_tb_values(
    audit_rows: list[dict],
    *,
    db: AsyncSession | None,
    project_id: UUID | None,
) -> dict[str, dict]:
    """按 audit_rows 各行的 ``account_code`` 批量查 ``trial_balance`` 取数（Req 3.1~3.3）。

    返回 ``{ "row-{n}": { opening_unadjusted, current_unadjusted, sys_aje, sys_rje } }``
    （keyed by ``row["id"]``）：

    - ``opening_unadjusted`` ← ``trial_balance.opening_balance``（期初未审数）
    - ``current_unadjusted`` ← ``trial_balance.unadjusted_amount``（本期未审数）
    - ``sys_aje``            ← ``trial_balance.aje_adjustment``（系统汇总 AJE 参考值）
    - ``sys_rje``            ← ``trial_balance.rje_adjustment``（系统汇总 RJE 参考值）

    降级（graceful degradation，对齐 Req 3.3，绝不抛异常阻塞渲染）：
    - ``db`` / ``project_id`` 缺失、无 account_code、年度为空 → 返回 ``{}``；
    - 某行 account_code 无对应 TB 行 → 该行不进 tb_values（前端按缺失即 null/「—」处理）；
    - 任意 SQL / 数据异常 → 记 warning 并返回已构建部分（或 ``{}``）。

    年度来源：projects 表无 ``year`` 列，按系统标准做法从 ``audit_period_end`` 提取
    年份（见 render-config 内 ``year_query`` / rotation_check 等）；为 NULL 则跳过取数。
    """
    if db is None or project_id is None or not audit_rows:
        return {}

    # 收集去重后的非空 account_code（仅对这些行取数）
    account_codes = sorted(
        {
            str(r["account_code"]).strip()
            for r in audit_rows
            if r.get("account_code")
        }
    )
    if not account_codes:
        return {}

    try:
        # ─── 年度：从 audit_period_end 提取年份（NULL → 跳过取数）──────────
        year_result = await db.execute(
            sa.text(
                "SELECT EXTRACT(YEAR FROM audit_period_end)::int "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        year_row = year_result.first()
        year = year_row[0] if year_row and year_row[0] else None
        if not year:
            return {}

        # ─── 批量查 trial_balance（参数化 IN，绝不字符串拼接）──────────────
        from app.models.audit_platform_models import TrialBalance

        tb_result = await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.opening_balance,
                TrialBalance.unadjusted_amount,
                TrialBalance.aje_adjustment,
                TrialBalance.rje_adjustment,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb_by_code = {row[0]: row for row in tb_result.all()}

        # ─── 按 row.id 组装 tb_values（无 TB 行的科目自动省略）────────────
        tb_values: dict[str, dict] = {}
        for r in audit_rows:
            code = r.get("account_code")
            if not code:
                continue
            tb_row = tb_by_code.get(str(code).strip())
            if tb_row is None:
                continue  # 该 account_code 无 TB 行 → 省略（前端按缺失处理）
            tb_values[r["id"]] = {
                "opening_unadjusted": _decimal_to_float(tb_row[1]),
                "current_unadjusted": _decimal_to_float(tb_row[2]),
                "sys_aje": _decimal_to_float(tb_row[3]),
                "sys_rje": _decimal_to_float(tb_row[4]),
            }
        return tb_values
    except Exception as e:  # noqa: BLE001 — TB 取数降级不阻塞渲染（Req 3.3）
        logger.warning("审定表 TB 取数失败 project_id=%s: %s", project_id, e)
        return {}


async def _generate_audit_sheet_data(
    file_path: str | None,
    sheet_name: str,
    existing: dict | None = None,
    *,
    db: AsyncSession | None = None,
    project_id: UUID | None = None,
    wp_code: str | None = None,
) -> dict:
    """为 audit-sheet（审定表）准备结构化行数据 + TB 取数（持久化优先 + 实时取数）。

    返回结构与 GtAuditSheet.vue 消费的 html_data 接口一致：
    {
      audit_rows: AuditSheetRow[],   # 行结构 + 用户编辑列（adj/reclass/reason）
      tb_values: { "row-{n}": { opening_unadjusted, current_unadjusted,
                                sys_aje, sys_rje } },  # TB 实时值，不持久化
    }

    数据准备策略：
    1. 行结构（``audit_rows``）：持久化优先 —— 若 ``existing.audit_rows`` 已有且非空，
       沿用用户编辑过的行结构 + 调整值（不被模板默认行覆盖，对齐 Req 4.3）；
       否则调 ``extract_audit_rows`` 从底稿模板 xlsx 解析默认行项目结构。
    2. TB 取数（``tb_values``）：**每次加载实时查 ``trial_balance``**（不持久化，对齐
       design「持久化分层原则」）—— 按各行 ``account_code`` 批量取期初/本期未审数 +
       系统 AJE/RJE，用户重新导入 TB 后刷新自动反映（Req 3.1、3.4）。

    降级（绝不抛异常阻塞渲染）：
    - 模板缺失 / 解析失败 → audit_rows 为空列表（前端空态 + 手动新增，对齐 Req 2.3）；
    - TB 不存在（项目未导入账套 / 该 account_code 无 TB 行）→ tb_values 对应键缺失，
      不影响编辑（graceful degradation，对齐 Req 3.3）。
    """
    # ─── 1. 行结构：持久化优先（Req 4.3），否则从模板提取 ─────────────────
    # 多列明细表（如 D1-2 有 10 数据列）也需要列定义供前端动态渲染。
    column_defs: list[dict] | None = existing.get("column_defs") if existing else None
    if existing and existing.get("audit_rows"):
        audit_rows: list[dict] = existing["audit_rows"]
    else:
        from app.services.wp_audit_sheet_extract import (
            extract_audit_rows_with_values_from_file,
        )

        audit_rows = []
        if file_path:
            try:
                audit_rows, col_defs = extract_audit_rows_with_values_from_file(
                    file_path, sheet_name
                )
                if col_defs and not column_defs:
                    column_defs = col_defs
            except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
                logger.warning("审定表行提取失败 %s/%s: %s", file_path, sheet_name, e)
                audit_rows = []

    # ─── 1b. 审计说明 / 审计结论区：持久化优先，否则从模板提取默认文本 ────
    # 审定表数据网格之后有「审计说明」（变动大科目原因+质押/贴现说明）+「审计结论」
    # （是否认可列报）两块说明区，旧逻辑随表体截断丢失。此处单独提取作为默认占位，
    # 用户编辑后持久化（existing.audit_sections 优先，不被模板覆盖）。
    audit_sections: dict
    if existing and isinstance(existing.get("audit_sections"), dict):
        audit_sections = existing["audit_sections"]
    else:
        from app.services.wp_audit_sheet_extract import extract_audit_sections

        audit_sections = {
            "notes": "", "conclusion": "",
            "notes_label": "审计说明", "conclusion_label": "审计结论",
        }
        if file_path:
            try:
                audit_sections = extract_audit_sections(file_path, sheet_name)
            except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
                logger.warning("审定表说明区提取失败 %s/%s: %s", file_path, sheet_name, e)

    # ─── 2. TB 取数：实时查 trial_balance（Req 3.1~3.3），不持久化 ─────────
    tb_values = await _fetch_audit_sheet_tb_values(
        audit_rows, db=db, project_id=project_id
    )

    # 保留 existing 中的其他键（若有），覆盖 audit_rows + tb_values（tb 永远实时）
    result: dict = dict(existing) if isinstance(existing, dict) else {}
    result["audit_rows"] = audit_rows
    result["audit_sections"] = audit_sections
    result["tb_values"] = tb_values
    # 多列明细表列定义（前端 GtAuditSheet 动态渲染，标准审定表为 None → 走默认列）
    if column_defs:
        result["column_defs"] = column_defs
    return result


@router.post("/{wp_id}/audit-sheet-refresh")
async def refresh_audit_sheet_from_ledger(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """一键刷新：从四表库（试算表/辅助余额表）预填充审定表/明细表数据。

    对于按客户明细表（如 D1-3），从 tb_aux_balance 按 account_code 查询辅助余额，
    按 aux_name（客户名称）聚合为行，填入 column_defs 对应列。
    对于按类别明细表（如 D1-2），从 trial_balance 按 account_code 查询余额。

    返回预填充后的 audit_rows（前端可直接覆盖 tableData）。
    """
    # 查 working_paper → wp_index → wp_code + project_id
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    wp_index = (
        await db.execute(
            sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id)
        )
    ).scalars().first()
    wp_code = wp_index.wp_code if wp_index else ""
    project_id = wp.project_id

    # 获取年度
    year_result = await db.execute(
        sa.text("SELECT EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    year_row = year_result.first()
    project_year = year_row[0] if year_row and year_row[0] else None

    if not project_year:
        return {"rows": [], "message": "项目未设置审计期间，无法取数"}

    # 确定科目编码（从 wp_account_mapping 或直接根据 wp_code）
    import json
    from pathlib import Path as _Path

    mapping_file = _Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
    account_codes: list[str] = []
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            mappings = json.load(f)
        for m in mappings:
            if m.get("wp_code") == wp_code:
                account_codes = m.get("account_codes", [])
                break
    except Exception:
        pass

    if not account_codes:
        # D1 系列默认 1121（应收票据）
        if wp_code.startswith("D1"):
            account_codes = ["1121"]
        else:
            return {"rows": [], "message": f"未找到 {wp_code} 的科目映射"}

    # 从辅助余额表查询按客户/辅助核算维度的余额
    try:
        aux_result = await db.execute(
            sa.text("""
                SELECT aux_name, opening_balance, debit_amount, credit_amount, closing_balance
                FROM tb_aux_balance
                WHERE project_id = :pid
                  AND year = :year
                  AND account_code = ANY(:codes)
                  AND is_deleted = false
                  AND aux_name IS NOT NULL AND aux_name != ''
                ORDER BY closing_balance DESC NULLS LAST
            """),
            {"pid": str(project_id), "year": project_year, "codes": account_codes},
        )
        aux_rows = aux_result.all()
    except Exception as e:
        logger.warning("audit-sheet-refresh 辅助余额查询失败: %s", e)
        aux_rows = []

    if not aux_rows:
        # 回退到试算表查询
        try:
            tb_result = await db.execute(
                sa.text("""
                    SELECT standard_account_code, opening_balance, unadjusted_amount,
                           aje_adjustment, rje_adjustment
                    FROM trial_balance
                    WHERE project_id = :pid
                      AND year = :year
                      AND standard_account_code = ANY(:codes)
                      AND is_deleted = false
                """),
                {"pid": str(project_id), "year": project_year, "codes": account_codes},
            )
            tb_rows = tb_result.all()
        except Exception as e:
            logger.warning("audit-sheet-refresh TB 查询失败: %s", e)
            tb_rows = []

        if not tb_rows:
            return {"rows": [], "message": "四表库中未找到该科目数据"}

        # TB 数据返回（简单行）
        rows = []
        for i, tr in enumerate(tb_rows):
            rows.append({
                "id": f"refresh-{i+1}",
                "item": tr[0] or "",
                "isCustom": True,
                "opening_unadjusted": float(tr[1]) if tr[1] else None,
                "current_unadjusted": float(tr[2]) if tr[2] else None,
                "sys_aje": float(tr[3]) if tr[3] else None,
                "sys_rje": float(tr[4]) if tr[4] else None,
            })
        return {"rows": rows, "message": f"已从试算表预填充 {len(rows)} 行"}

    # 辅助余额数据 → 明细行
    rows = []
    for i, ar in enumerate(aux_rows):
        rows.append({
            "id": f"refresh-{i+1}",
            "item": ar[0] or "",  # 客户名称
            "isCustom": True,
            "col_opening": float(ar[1]) if ar[1] else None,
            "col_debit": float(ar[2]) if ar[2] else None,
            "col_credit": float(ar[3]) if ar[3] else None,
            "col_closing": float(ar[4]) if ar[4] else None,
        })

    return {"rows": rows, "message": f"已从辅助余额表预填充 {len(rows)} 行（按客户）"}


@router.get("/{wp_id}/preparation-info")
async def get_preparation_info(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """workpaper 级编制信息（7 字段，无 accounting_period）。"""
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return await _build_preparation_info(db, wp.project_id, wp_id)


@router.post("/generate-from-index")
async def generate_workpaper_from_index(
    wp_index_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动从 wp_index 幂等生成 working_paper。"""
    from app.services.workpaper_generation_service import workpaper_generation_service

    wp_index = (
        await db.execute(
            sa.select(WpIndex).where(
                WpIndex.id == wp_index_id,
                WpIndex.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if wp_index is None:
        raise HTTPException(status_code=404, detail="底稿索引不存在")

    wp = await workpaper_generation_service.ensure_working_paper(
        db,
        wp_index.project_id,
        wp_index_id,
        created_by=user.id,
    )
    await db.commit()
    return {
        "working_paper_id": str(wp.id),
        "wp_index_id": str(wp_index_id),
        "wp_code": wp_index.wp_code,
        "file_path": wp.file_path,
    }


@router.get("/{wp_id}/render-config")
async def get_render_config(
    wp_id: UUID,
    sheet_name: str | None = Query(None, description="可选，仅返回单 sheet 数据"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿渲染 schema + 项目数据 + 跨底稿引用。

    EARS:
    - IF wp_id 不存在 THEN 返回 404
    - IF scope = 'consolidated' OR 'parent_only' THEN 返回 redirect 提示
    - WHEN 项目 template_version_id IS NULL THEN 默认按 current version 返回 schema
    """
    # ─── Step 1: 查 working_paper 获取基本信息 ────────────────────────────
    wp_query = sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    wp_result = await db.execute(wp_query)
    working_paper = wp_result.scalars().first()

    if working_paper is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    project_id = working_paper.project_id

    # ─── Step 2: 查 wp_index 获取 wp_code ────────────────────────────────
    wp_index_query = sa.select(WpIndex).where(
        WpIndex.id == working_paper.wp_index_id,
        WpIndex.is_deleted == False,  # noqa: E712
    )
    wp_index_result = await db.execute(wp_index_query)
    wp_index = wp_index_result.scalars().first()

    if wp_index is None:
        raise HTTPException(status_code=404, detail="底稿索引不存在")

    wp_code = wp_index.wp_code

    # ─── Step 3: 获取模板版本 ────────────────────────────────────────────
    # 注：projects 表无 template_version_id 列（该列属于 workpaper_sheet_classification，
    #     从无 projects 级定义）。历史代码曾 SELECT projects.template_version_id，
    #     在 PG 中该语句失败会使整个事务进入 aborted 状态，后续查询全部 500
    #     （render-config 对所有底稿普适 500 的根因）。故移除该探测查询，
    #     统一按 current version 解析（项目级版本绑定由 classification 层承担）。
    project_template_version_id = None

    # 获取版本字符串
    template_version_str: str | None = None
    version_service = WpTemplateVersionService(db)
    try:
        # 默认按 current version
        version_obj = await version_service.get_current_version()
        template_version_str = version_obj.version
        project_template_version_id = version_obj.id
    except HTTPException:
        # 版本表可能未初始化，降级继续
        logger.warning("Template version lookup failed, continuing without version info")
        template_version_str = None
        project_template_version_id = None

    # ─── Step 4: 获取 classifications ────────────────────────────────────
    classification_service = WpClassificationService(db)
    try:
        classifications = await classification_service.get_classification(
            wp_code=wp_code,
            project_id=project_id,
            template_version_id=project_template_version_id,
        )
    except ClassificationNotFoundError:
        # 归类未找到时降级：返回空 sheets（前端显示 pending 状态）
        logger.warning(
            "No classification found for wp_code=%s, project_id=%s",
            wp_code, project_id,
        )
        classifications = []

    classifications = await _maybe_custom_classifications(
        db,
        project_id,
        wp_code,
        wp_index.wp_name,
        classifications,
        working_paper,
    )

    # ─── Step 5: 检查 scope（EARS: consolidated/parent_only → redirect） ──
    # 取第一个 sheet 的 scope 作为底稿级 scope
    scope = "standalone"
    is_real_workpaper = True
    if classifications:
        scope = classifications[0].scope
        is_real_workpaper = classifications[0].is_real_workpaper

    if scope in ("consolidated", "parent_only"):
        # 返回 redirect 提示，前端跳合并模块
        delegated_module = classifications[0].delegated_module if classifications else None
        return {
            "wp_id": str(wp_id),
            "wp_code": wp_code,
            "project_id": str(project_id),
            "scope": scope,
            "is_real_workpaper": is_real_workpaper,
            "template_version": template_version_str,
            "redirect": True,
            "delegated_module": delegated_module or "consolidation_hub",
            "sheets": [],
        }

    # ─── Step 6: 加载 schema + html_data + cross_refs per sheet ──────────
    parsed_data = working_paper.parsed_data or {}
    html_data_all = parsed_data.get("html_data", {})

    # 获取跨底稿引用
    cross_ref_query = sa.select(WpCrossRef).where(
        WpCrossRef.source_wp_id == wp_id,
        WpCrossRef.project_id == project_id,
    )
    cross_ref_result = await db.execute(cross_ref_query)
    cross_refs_all = cross_ref_result.scalars().all()

    # 按 target_wp_code 分组（简化：所有 cross_refs 挂到每个 sheet）
    cross_ref_items = [
        CrossRefItem(wp_code=cr.target_wp_code, cell=cr.cell_reference)
        for cr in cross_refs_all
    ]

    sheets: list[dict] = []

    # 模板文件路径解析：优先用 working_paper.file_path（项目已生成的底稿文件），
    # 缺失/不存在时回退到 wp_templates/ 标准模板库（按 wp_code 查找）。
    # 这样即使底稿未初始化文件（file_path 为空），A-程序表/审定表/网格仍能从
    # 标准模板提取内容展示（修复「暂无审计程序」等空态回归）。
    def _resolve_template_file_path() -> str | None:
        fp = working_paper.file_path
        if fp and Path(fp).is_file():
            return fp
        try:
            from app.services.wp_template_init_service import find_template_file_any

            tpl = find_template_file_any(wp_code)
            if tpl is not None:
                return str(tpl)
        except Exception as e:  # noqa: BLE001 — 模板回退失败不阻塞渲染
            logger.warning("模板文件回退解析失败 wp_code=%s: %s", wp_code, e)
        return fp  # 兜底返回原值（可能为 None，下游各生成器自行降级）

    _template_file_path = _resolve_template_file_path()

    for classification in classifications:
        # 如果指定了 sheet_name，只返回匹配的 sheet
        if sheet_name and classification.sheet_name != sheet_name:
            continue

        # 派生 componentType
        try:
            component_type = derive_component_type(classification)
        except ClassificationNotFoundError as e:
            logger.warning("Cannot derive componentType: %s", e)
            component_type = "skip"

        # 加载 schema YAML
        schema_data: dict | None = None
        try:
            schema_data = _schema_service.load_schema(
                wp_code=wp_code,
                template_version_id=project_template_version_id,
            )
        except FileNotFoundError:
            # schema 文件不存在时返回 None（前端可降级处理）
            logger.debug(
                "No render schema found for wp_code=%s, sheet=%s",
                wp_code, classification.sheet_name,
            )

        # ─── 按 sheet 名解包 schema（前端组件读顶层 sub_tables/fields）────────
        # schema YAML 用 `sheets: { <sheet_name>: {...} }` 嵌套承载多 sheet 配置，
        # 但 GtCNoteTable / GtDForm 等组件读的是 props.schema 顶层的 sub_tables /
        # fields / version_variants 等键。故此处把当前 sheet 对应的子配置解包到顶层，
        # 同时保留 wp_code/template_version 等公共元信息。匹配不到当前 sheet（如审定表
        # sheet 在 C-disclosure schema 里无对应键）→ sheet_schema 置 None，走各自兜底。
        sheet_schema: dict | None = None
        if isinstance(schema_data, dict):
            nested = schema_data.get("sheets")
            if isinstance(nested, dict) and classification.sheet_name in nested:
                per_sheet = nested[classification.sheet_name]
                if isinstance(per_sheet, dict):
                    # 合并公共元信息（不覆盖 per_sheet 已有键）
                    sheet_schema = {
                        k: v for k, v in schema_data.items() if k != "sheets"
                    }
                    sheet_schema.update(per_sheet)
            elif schema_data.get("sub_tables") or schema_data.get("fields"):
                # 无 sheets 嵌套但顶层直接是单 sheet 配置（兼容旧格式）
                sheet_schema = schema_data

        # 获取 sheet 级 html_data
        sheet_html_data = html_data_all.get(classification.sheet_name)

        # ─── B-Index 自动生成逻辑：编制信息 + 索引导航 ─────────────────
        if component_type == "b-index" and not sheet_html_data:
            sheet_html_data = await _generate_b_index_data(
                db=db,
                project_id=project_id,
                wp_id=wp_id,
                classifications=classifications,
                audit_cycle=wp_index.audit_cycle,
            )

        # ─── A-程序表中控台自动生成：从模板 xlsx 提取审计程序行 ─────────
        # GtAProgramConsole 消费 html_data.programs；当 sheet 无持久化 programs
        # 时，从底稿模板 xlsx 解析程序清单（序号/描述/分类/5项认定/底稿索引），
        # 否则中控台永远显示「暂无审计程序」（模板里的程序内容无法体现）。
        if component_type == "a-program-console" and not (
            isinstance(sheet_html_data, dict) and sheet_html_data.get("programs")
        ):
            sheet_html_data = await _generate_a_program_data(
                file_path=_template_file_path,
                sheet_name=classification.sheet_name,
                existing=sheet_html_data if isinstance(sheet_html_data, dict) else None,
            )

        # ─── 审定表（F-审定表）自动生成：结构化可编辑行 + TB 取数 ──────────
        # component_type=audit-sheet 时，从模板 xlsx 解析行项目结构（持久化优先），
        # TB 取数在组④填充 tb_values。
        if component_type == "audit-sheet":
            sheet_html_data = await _generate_audit_sheet_data(
                file_path=_template_file_path,
                sheet_name=classification.sheet_name,
                existing=sheet_html_data if isinstance(sheet_html_data, dict) else None,
                db=db,
                project_id=project_id,
                wp_code=wp_code,
            )

        # ─── univer 表格类底稿网格自动生成：从模板 xlsx 提取只读网格 ──────
        # 混合底稿（含 HTML sheet + univer sheet）整本走 GtWpRenderer 时，
        # univer sheet（审定表/明细表/测算表）之前只显示死占位「数据尚未导入」，
        # 模板网格结构完全不体现。此处补 cells/merged_cells 让模板内容可见（只读），
        # TB 取数后续再填。
        if component_type == "univer" and not _has_grid_cells(sheet_html_data):
            sheet_html_data = await _generate_grid_data(
                file_path=_template_file_path,
                sheet_name=classification.sheet_name,
                existing=sheet_html_data if isinstance(sheet_html_data, dict) else None,
            )

        # ─── C-附注披露无 schema 时的只读网格兜底 ──────────────────────────
        # GtCNoteTable 是 schema 驱动（需手工编排 sub_tables/fields）；当某附注披露
        # sheet 没有配套 render schema（如尚未编写 C-{wp_code}-disclosure.yaml 的循环），
        # 组件只会显示「附注披露表尚未配置」空态，模板里的多级披露表格完全不可见。
        # 此处与 univer 同款：无解包后的 sheet_schema.sub_tables 且无持久化网格时，
        # 从模板 xlsx 提取只读网格（cells/merged_cells/样式），前端 GtWpRenderer 用
        # GtGridSheet 还原模板外观（只读）。已有配套 disclosure schema 的附注（如
        # C-D1-disclosure / C-D2-disclosure）走 GtCNoteTable 结构化卡片渲染，不进此兜底。
        if (
            component_type == "c-note-table"
            and not (isinstance(sheet_schema, dict) and sheet_schema.get("sub_tables"))
            and not _has_grid_cells(sheet_html_data)
        ):
            sheet_html_data = await _generate_grid_data(
                file_path=_template_file_path,
                sheet_name=classification.sheet_name,
                existing=sheet_html_data if isinstance(sheet_html_data, dict) else None,
            )

        # ─── 解析 fixed_cells 中的 ${...} 占位（附注披露表头实体名/截止日/索引号）──
        # schema.fixed_cells 用 ${entity_name}/${period_end}/${index_no} 等占位，
        # GtCNoteTable 直接读 fixed_cells.A3/A4/I3 渲染表头，故此处用编制信息实际值替换，
        # 避免界面显示字面量 "${entity_name}"。仅 c-note-table 且有 fixed_cells 时解析。
        if (
            component_type == "c-note-table"
            and isinstance(sheet_schema, dict)
            and isinstance(sheet_schema.get("fixed_cells"), dict)
        ):
            prep_info = await _build_preparation_info(db, project_id, wp_id)
            subst = {
                "${entity_name}": prep_info.get("entity_name", ""),
                "${period_end}": prep_info.get("period_end", ""),
                "${index_no}": prep_info.get("index_no", "") or wp_code,
                "${page_no}": "1",
            }
            resolved_cells = {}
            for cell, val in sheet_schema["fixed_cells"].items():
                if isinstance(val, str) and val in subst:
                    resolved_cells[cell] = subst[val]
                else:
                    resolved_cells[cell] = val
            # 浅拷贝避免污染 schema service 缓存
            sheet_schema = {**sheet_schema, "fixed_cells": resolved_cells}

        sheet_config = {
            "sheet_name": classification.sheet_name,
            "componentType": component_type,
            "schema": sheet_schema,
            "html_data": sheet_html_data,
            "cross_refs": [item.model_dump() for item in cross_ref_items],
        }
        sheets.append(sheet_config)

    # ─── Step 7: 批量解析 auto-fill 取数值（US-15）────────────────────────
    fill_results: dict = {}
    # 获取项目年度：projects 表无 year 列，年度从 audit_period_end 提取年份
    # （系统标准做法，见 rotation_check/client_quality_trend 等）。
    # 该字段可能为 NULL → project_year=None → 跳过 auto-fill（降级，不报错）。
    project_year = None
    try:
        year_query = sa.text(
            "SELECT EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :pid"
        )
        year_result = await db.execute(year_query, {"pid": str(project_id)})
        year_row = year_result.first()
        project_year = year_row[0] if year_row and year_row[0] else None
    except Exception as e:
        logger.warning("项目年度解析失败，跳过 auto-fill: %s", e)
        project_year = None

    if project_year:
        # 合并所有 sheet 的 schema 用于批量取数（schema 已在上方按 sheet 解包到顶层，
        # 直接以 sheet_name 为键组装即可，无需再 .get("sheets")）。
        combined_schema: dict = {"sheets": {}}
        for sheet_cfg in sheets:
            if sheet_cfg.get("schema") and isinstance(sheet_cfg["schema"], dict):
                combined_schema["sheets"][sheet_cfg["sheet_name"]] = sheet_cfg["schema"]
        try:
            fill_results = await _resolve_auto_fill_values(
                schema=combined_schema,
                project_id=project_id,
                year=project_year,
                db=db,
            )
        except Exception as e:
            logger.warning("Auto-fill resolution failed: %s", e)
            fill_results = {}

    return {
        "wp_id": str(wp_id),
        "wp_code": wp_code,
        "project_id": str(project_id),
        "scope": scope,
        "is_real_workpaper": is_real_workpaper,
        "template_version": template_version_str,
        "sheets": sheets,
        "fill_results": fill_results,
    }
