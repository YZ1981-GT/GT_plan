"""A-程序表中控台生成策略

当 a-program-console / a1-dashboard / a2-adjustment-console / a3-consolidation-console
类型的 sheet 无持久化 programs 时，从模板 xlsx 或 procedure_table_templates 生成程序清单。
返回结构与 GtAProgramConsole.vue 的 AProgramHtmlData 接口一致。
"""

from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)


def _parse_sub_steps(content: str) -> tuple[str, list[dict]]:
    """解析程序 content 为父描述 + 子步骤列表。

    模板 content 格式：
        "获取或编制应收账款明细表，执行以下程序：\n（1）复核加计…\n（2）检查…"
    解析为：
        parent_desc = "获取或编制应收账款明细表，执行以下程序："
        sub_steps = [{"no": 1, "text": "复核加计…"}, {"no": 2, "text": "检查…"}]

    支持中文括号（N）和英文括号(N)两种编号格式。
    无子步骤时 sub_steps 为空列表，parent_desc 为原始 content。
    """
    import re

    if not content:
        return "", []

    # 按换行拆分（模板中 \n 已为实际换行）
    lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
    if not lines:
        return content.strip(), []

    # 匹配子步骤行：以（N）或 (N) 开头
    step_pattern = re.compile(r"^[（\(](\d+)[）\)]\s*(.*)")

    parent_lines: list[str] = []
    sub_steps: list[dict] = []
    in_steps = False

    for line in lines:
        m = step_pattern.match(line)
        if m:
            in_steps = True
            sub_steps.append({"no": int(m.group(1)), "text": m.group(2)})
        elif in_steps and sub_steps:
            # 续行（子步骤跨行）
            sub_steps[-1]["text"] += line
        else:
            parent_lines.append(line)

    parent_desc = "\n".join(parent_lines) if parent_lines else (lines[0] if lines else content)
    return parent_desc, sub_steps


async def _generate_a_program_data(
    file_path: str | None,
    sheet_name: str,
    existing: dict | None = None,
    *,
    db=None,
    project_id=None,
    wp_code: str | None = None,
    year: int | None = None,
    business_category: str = "C",
) -> dict:
    """当 a-program-console sheet 无持久化 programs 时，生成程序清单。

    两条数据源（优先级）：
    1. **procedure_table_templates.json 自动汇总**（A1~A17）：当 wp_code 命中模板且
       提供了 db+project_id 时，用 `ProcedureTableService` 生成带自动值的程序行
       （如 A2 的 AJE/RJE/Passed 笔数实时统计），summary 拼进 program_desc，
       ref_index 作为 linked_workpapers 渲染可点击索引 chip。
    2. **模板 xlsx 提取**（兜底）：无匹配模板或缺 db 时，从底稿 xlsx 解析程序清单。

    返回结构与 GtAProgramConsole.vue 的 AProgramHtmlData 接口一致。
    解析失败 / 文件缺失 → programs 为空列表（前端仍显示空态，不报错）。
    """
    from app.services.wp_program_extract import extract_program_rows

    programs: list[dict] = []

    # ─── 优先：procedure_table 模板 + 自动汇总（A1~A17 接线） ─────────────
    if db is not None and project_id is not None and wp_code:
        try:
            from app.services.procedure_table_auto_service import (
                ProcedureTableService,
                get_template,
            )

            if get_template(wp_code) is not None:
                svc = ProcedureTableService(db)
                table = await svc.get_procedure_table(
                    project_id, year or 0, wp_code, business_category
                )
                for it in table.get("items", []):
                    summary = it.get("summary")
                    desc = it.get("content", "")
                    applicable = it.get("applicable")
                    status = "not_applicable" if applicable == "na" else "pending"
                    # 解析子程序步骤：content 中 \n（N）... 格式为子步骤
                    parent_desc, sub_steps = _parse_sub_steps(desc)
                    programs.append({
                        "id": f"row-{it.get('seq')}",
                        "program_no": it.get("seq"),
                        "program_desc": parent_desc,
                        "program_category": "",
                        "assertions": {},
                        "linked_workpapers": it.get("ref_index", "") or "",
                        "status": status,
                        "phase": it.get("phase"),
                        "summary": summary or "",
                        "sub_steps": sub_steps,
                    })
        except Exception as e:  # noqa: BLE001 — 降级到 xlsx 提取，不阻塞渲染
            logger.warning("A-程序表模板自动汇总失败 %s: %s", wp_code, e)
            programs = []

    # ─── 兜底：从模板 xlsx 提取 ─────────────────────────────────────────
    if not programs and file_path:
        try:
            programs = extract_program_rows(file_path, sheet_name)
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning("A-程序表提取失败 %s/%s: %s", file_path, sheet_name, e)
            programs = []

    # ─── 终极兜底：程序行仍为空 → 从 xlsx 提取只读网格（至少显示模板原样） ──
    # 适用于：替代程序检查表(D0-5/D0-6)等非标准程序行结构的 sheet，
    # class_code 被标为 A- 但内容实际是表格型。
    grid_fallback: dict | None = None
    if not programs and file_path:
        try:
            from app.services.wp_grid_extract import extract_grid

            grid = extract_grid(file_path, sheet_name)
            if isinstance(grid, dict) and grid.get("cells"):
                grid_fallback = grid
        except Exception as e:  # noqa: BLE001
            logger.debug("A-程序表 grid 兜底提取失败 %s/%s: %s", file_path, sheet_name, e)

    result: dict = {
        "programs": programs,
        "trim_decisions": [],
    }

    # 如果有 grid 兜底数据，标记供前端切换到只读网格模式渲染
    if grid_fallback:
        result["grid_fallback"] = grid_fallback

    # ─── 合并已保存的用户覆盖值（execution_summary / status） ─────────────
    if db is not None and project_id is not None and wp_code and programs:
        try:
            from app.services.field_override_service import FieldOverrideService
            override_svc = FieldOverrideService(db)
            overrides = await override_svc.get_batch(project_id, year or 0, f"procedure_table:{wp_code}")
            for prog in programs:
                item_key = str(prog.get("program_no", ""))
                if item_key in overrides:
                    saved = overrides[item_key]
                    if "execution_summary" in saved:
                        prog["execution_summary"] = saved["execution_summary"]
                    if "status" in saved and saved["status"]:
                        prog["status"] = saved["status"]
        except Exception as e:  # noqa: BLE001
            logger.warning("加载程序表 override 失败 wp_code=%s: %s", wp_code, e)
            # 事务可能已 aborted → rollback 恢复以免影响后续查询
            try:
                await db.rollback()
            except Exception:
                pass

    # 保留已有签字信息（若 sheet 之前存过部分数据）
    if existing and isinstance(existing.get("signatures"), list):
        result["signatures"] = existing["signatures"]
    return result


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）。

    仅当 a-program-console 类 sheet 尚无持久化 programs 数据时才自动生成：
    - programs：审计程序行列表（序号/描述/分类/认定/底稿索引）
    - trim_decisions：裁剪决策列表
    - signatures：已有签字信息（保留）

    数据源优先级：
    1. procedure_table_templates 自动汇总（A1~A17）
    2. 模板 xlsx 兜底提取
    """
    # 已有持久化 programs 数据则不重新生成
    if isinstance(ctx.sheet_html_data, dict) and ctx.sheet_html_data.get("programs"):
        return None

    # 多文件聚合：程序表 sheet（如 D2 父码下的 "D2A 应收账款实质性程序表"）的
    # procedure_table 模板与模板文件应按 **sheet 级编码**（D2A）解析，而非父码 wp_code(D2)。
    # 从 sheet 名提取程序表编码（如 D2A/D4A），提取不到回退父 wp_code。
    import re as _re
    _sheet_code = ctx.wp_code
    _m = _re.search(r"([A-Z]\d+[A-Z](?:-\d+)*|[A-Z]\d+-\d+)", ctx.classification.sheet_name or "")
    if _m:
        _sheet_code = _m.group(1)
    # 程序表内容来自 sheet 自己的来源模板（聚合 source_files），否则全局模板路径
    _src_files = [f for f in (getattr(ctx, "source_files", None) or []) if f]
    _file_path = _src_files[0] if _src_files else ctx.template_file_path

    sheet_html_data = await _generate_a_program_data(
        file_path=_file_path,
        sheet_name=ctx.classification.sheet_name,
        existing=ctx.sheet_html_data if isinstance(ctx.sheet_html_data, dict) else None,
        db=ctx.db,
        project_id=ctx.project_id,
        wp_code=_sheet_code,
        year=ctx.year,
        business_category=ctx.business_category,
    )

    return sheet_html_data
