"""A-程序表中控台生成策略

当 a-program-console / a1-dashboard / a2-adjustment-console / a3-consolidation-console
类型的 sheet 无持久化 programs 时，从模板 xlsx 或 procedure_table_templates 生成程序清单。
返回结构与 GtAProgramConsole.vue 的 AProgramHtmlData 接口一致。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


from app.services.wp_program_sub_steps import enrich_program_row, parse_sub_steps


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
                    parent_desc, sub_steps = parse_sub_steps(desc)
                    programs.append({
                        "id": f"row-{it.get('seq')}",
                        "program_no": it.get("seq"),
                        "program_desc": parent_desc,
                        "program_category": it.get("category") or it.get("program_category") or "",
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
            # 事务可能已 aborted → rollback 恢复
            if db is not None:
                try:
                    await db.rollback()
                except Exception:
                    pass

    # ─── 兜底：从模板 xlsx 提取 ─────────────────────────────────────────
    if not programs and file_path:
        try:
            programs = extract_program_rows(file_path, sheet_name)
            programs = [enrich_program_row(p) for p in programs]
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning("A-程序表提取失败 %s/%s: %s", file_path, sheet_name, e)
            programs = []

    # ─── 兜底 2：按 sheet 级编码重新解析模板文件后再提取 ─────────────────
    # 多文件科目（如 F2）的父码模板可能不含该程序表 sheet（F2-55A 位于
    # "F2-55至F2-58 合同履约成本.xlsx"），用 sheet 编码定位真正来源文件。
    if not any(p.get("program_desc", "").strip() for p in programs) and wp_code:
        try:
            from app.services.wp_template_finder import find_template_file_any

            alt_path = find_template_file_any(wp_code)
            if alt_path and str(alt_path) != (file_path or ""):
                alt_programs = extract_program_rows(str(alt_path), sheet_name)
                alt_programs = [enrich_program_row(p) for p in alt_programs]
                if any(p.get("program_desc", "").strip() for p in alt_programs):
                    programs = alt_programs
                    file_path = str(alt_path)
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning("A-程序表按编码重解析失败 %s/%s: %s", wp_code, sheet_name, e)

    # 有效性检测：如果 extract_program_rows 提取的行全是空描述（无实质内容），
    # 说明该 sheet 不是程序表结构（如 D0-5/D0-6 替代程序检查表），清空让 grid_fallback 接管。
    if programs and not any(p.get("program_desc", "").strip() for p in programs):
        programs = []

    # ─── 终极兜底：程序行仍为空 → 从 xlsx 提取只读网格（至少显示模板原样） ──
    # 适用于：替代程序检查表(D0-5/D0-6)等非标准程序行结构的 sheet，
    # class_code 被标为 A- 但内容实际是表格型。
    grid_fallback: dict | None = None
    if not programs and file_path:
        try:
            from app.services.wp_grid_extract import extract_grid, strip_standard_header

            grid = extract_grid(file_path, sheet_name)
            if isinstance(grid, dict) and grid.get("cells"):
                grid_fallback = strip_standard_header(grid)
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
        # 防御：前面 get_procedure_table 中 resolver 失败可能让事务 abort 且 rollback 被吞，
        # 需确保事务可用后再查询（InFailedSQLTransaction 根因修复）。
        # SQLAlchemy AsyncSession 中检测方式：尝试一个轻量 SQL，失败则 rollback。
        try:
            await db.execute(sa.text("SELECT 1"))
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
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
    # 已有持久化 programs 数据则不重新生成——但若全是空描述且无用户编辑痕迹视同无效
    if isinstance(ctx.sheet_html_data, dict) and ctx.sheet_html_data.get("programs"):
        _persisted = ctx.sheet_html_data["programs"]
        # 有效性判定：有描述内容 OR 有用户编辑痕迹（status 非默认 pending/execution_summary 非空）
        _has_substance = any(
            p.get("program_desc", "").strip()
            or p.get("execution_summary", "").strip()
            or p.get("status") not in (None, "", "pending")
            for p in _persisted
        )
        if _has_substance:
            return None
        # 全空描述且无编辑 → 继续重新生成（grid_fallback 接管）

    # 多文件聚合：程序表 sheet（如 D2 父码下的 "D2A 应收账款实质性程序表"）的
    # procedure_table 模板与模板文件应按 **sheet 级编码**（D2A）解析，而非父码 wp_code(D2)。
    # 从 sheet 名提取程序表编码（如 D2A/D4A），提取不到回退父 wp_code。
    import re as _re
    _sheet_code = ctx.wp_code
    _m = _re.search(r"([A-Z]\d+(?:-\d+)?[A-Z](?:-\d+)*|[A-Z]\d+[A-Z](?:-\d+)*|[A-Z]\d+-\d+[A-Z]?)", ctx.classification.sheet_name or "")
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

    # procedure-delegation-notification / Task 4：叠加 task overlay（纯读，缺 task 标
    # materialization_required）。默认关闭（expand 阶段不改既有读语义），只有
    # PROCEDURE_ROW_TASKS_ENABLED=True 才注入；只读、失败降级、不阻塞渲染。
    await _apply_task_overlay(ctx, sheet_html_data)

    return sheet_html_data


async def _apply_task_overlay(ctx: RenderContext, sheet_html_data: dict) -> None:
    """纯读：把 ProcedureRowTask overlay 合并到 program 行（Design D3 / 需求 2.7）。

    绝不触发 upsert/materialize/任何写库；异常吞掉，渲染不受影响。
    """
    from app.core.config import settings

    if not getattr(settings, "PROCEDURE_ROW_TASKS_ENABLED", False):
        return
    programs = sheet_html_data.get("programs") if isinstance(sheet_html_data, dict) else None
    if not programs or ctx.db is None or ctx.project_id is None:
        return
    wp_index_id = getattr(getattr(ctx, "working_paper", None), "wp_index_id", None)
    if wp_index_id is None:
        return
    try:
        from app.services.procedure_task_materialization_service import (
            ProcedureTaskMaterializationService,
        )

        svc = ProcedureTaskMaterializationService(ctx.db)
        await svc.overlay_program_rows(ctx.project_id, wp_index_id, programs)
    except Exception as e:  # noqa: BLE001 — overlay 只读增强，失败不阻塞渲染
        logger.debug("program task overlay 跳过 wp_code=%s: %s", ctx.wp_code, e)
