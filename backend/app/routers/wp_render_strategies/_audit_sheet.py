"""审定表（audit-sheet）TB 取数策略

当 component_type=audit-sheet 时，从模板 xlsx 解析行项目结构（持久化优先），
TB 取数实时填充 tb_values。返回结构与 GtAuditSheet.vue 的 AuditSheetHtmlData 一致。
"""

from __future__ import annotations

import logging

from app.services.wp_audit_sheet_tb_service import (
    fetch_audit_sheet_tb_values as _fetch_audit_sheet_tb_values,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）。

    为 audit-sheet（审定表）准备结构化行数据 + TB 取数（持久化优先 + 实时取数）。

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
    existing = ctx.sheet_html_data if isinstance(ctx.sheet_html_data, dict) else None

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
        if ctx.template_file_path:
            try:
                audit_rows, col_defs = extract_audit_rows_with_values_from_file(
                    ctx.template_file_path, ctx.classification.sheet_name
                )
                if col_defs and not column_defs:
                    column_defs = col_defs
            except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
                logger.warning(
                    "审定表行提取失败 %s/%s: %s",
                    ctx.template_file_path, ctx.classification.sheet_name, e,
                )
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
        if ctx.template_file_path:
            try:
                audit_sections = extract_audit_sections(
                    ctx.template_file_path, ctx.classification.sheet_name
                )
            except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
                logger.warning(
                    "审定表说明区提取失败 %s/%s: %s",
                    ctx.template_file_path, ctx.classification.sheet_name, e,
                )

    # ─── 2. TB 取数：实时查 trial_balance（Req 3.1~3.3），不持久化 ─────────
    tb_values = await _fetch_audit_sheet_tb_values(
        audit_rows, db=ctx.db, project_id=ctx.project_id
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
