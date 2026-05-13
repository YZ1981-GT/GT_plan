"""报表格式配置 API

覆盖：
- GET  列表（按 report_type / applicable_standard 筛选）
- GET  详情
- POST 克隆标准配置到项目
- PUT  修改配置行
- POST 加载种子数据
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.models.report_models import FinancialReportType, ReportConfig
from app.models.report_schemas import ReportConfigCloneRequest, ReportConfigRow
from app.services.report_config_service import ReportConfigService

router = APIRouter(
    prefix="/api/report-config",
    tags=["report-config"],
)


@router.get("")
async def list_report_configs(
    report_type: FinancialReportType | None = Query(None),
    applicable_standard: str | None = Query(None),
    project_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询报表配置列表。
    
    优先级：applicable_standard 显式传入 > 从 project_id 自动解析 > 降级 enterprise
    """
    if not applicable_standard and project_id:
        applicable_standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
    if not applicable_standard:
        applicable_standard = "enterprise"
    svc = ReportConfigService(db)
    rows = await svc.list_configs(
        report_type=report_type,
        applicable_standard=applicable_standard,
    )
    return [ReportConfigRow.model_validate(r) for r in rows]


@router.get("/{config_id}")
async def get_report_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询单行配置详情"""
    svc = ReportConfigService(db)
    row = await svc.get_config(config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置行不存在")
    return ReportConfigRow.model_validate(row)


@router.post("/clone")
async def clone_report_config(
    data: ReportConfigCloneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """克隆标准配置到项目"""
    svc = ReportConfigService(db)
    try:
        count = await svc.clone_report_config(
            project_id=data.project_id,
            applicable_standard=data.applicable_standard,
        )
        await db.commit()
        return {"message": f"成功克隆 {count} 行配置", "count": count}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{config_id}")
async def update_report_config(
    config_id: UUID,
    updates: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """修改配置行"""
    svc = ReportConfigService(db)
    try:
        row = await svc.update_config(config_id, updates, user_id=current_user.id)
        await db.commit()
        return ReportConfigRow.model_validate(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_report_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新增配置行"""
    rc = ReportConfig(
        report_type=FinancialReportType(body["report_type"]),
        row_number=body.get("row_number", 0),
        row_code=body.get("row_code", ""),
        row_name=body.get("row_name", ""),
        indent_level=body.get("indent_level", 0),
        formula=body.get("formula"),
        applicable_standard=body.get("applicable_standard", "enterprise"),
        is_total_row=body.get("is_total_row", False),
        parent_row_code=body.get("parent_row_code"),
    )
    db.add(rc)
    await db.flush()
    await db.commit()
    return ReportConfigRow.model_validate(rc)


@router.delete("/{config_id}")
async def delete_report_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除配置行"""
    import sqlalchemy as sa
    result = await db.execute(
        sa.select(ReportConfig).where(ReportConfig.id == config_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="行不存在")
    row.is_deleted = True
    await db.commit()
    return {"deleted": True}


@router.post("/seed")
async def load_seed_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """加载种子数据，完成后自动填充公式（确保新部署自动就绪）"""
    from app.services.report_formula_service import report_formula_service

    svc = ReportConfigService(db)
    count = await svc.load_seed_data()
    await db.commit()

    # 自动填充公式（幂等，已有公式的行跳过）
    formula_stats = await report_formula_service.fill_all_formulas(db, standard="all")
    await db.commit()

    return {
        "message": f"成功加载 {count} 行种子数据，填充 {formula_stats['updated']} 行公式",
        "count": count,
        "formula_stats": formula_stats,
    }


@router.post("/fill-formulas")
async def fill_formulas(
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """填充报表公式（幂等，admin 权限）。

    请求体（可选）:
      standard: "all" | "soe" | "listed"（默认 "all"）

    返回:
      {total, updated, skipped, coverage_pct}
    """
    from app.services.report_formula_service import report_formula_service

    standard = "all"
    if body and isinstance(body, dict):
        standard = body.get("standard", "all")

    stats = await report_formula_service.fill_all_formulas(db, standard=standard)
    await db.commit()

    return {
        "total": stats["total"],
        "updated": stats["updated"],
        "skipped": stats["skipped"],
        "coverage": f"{stats['coverage_pct']}%",
    }


@router.post("/batch-update")
async def batch_update_report_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量更新报表行的金额（从试算平衡表审定数回填）"""
    import sqlalchemy as sa

    project_id = body.get("project_id")
    report_type_str = body.get("report_type", "balance_sheet")
    applicable_standard = body.get("applicable_standard", "soe_consolidated")
    updates = body.get("updates", [])

    if not project_id or not updates:
        return {"updated": 0, "message": "无数据"}

    try:
        report_type = FinancialReportType(report_type_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的报表类型: {report_type_str}")

    updated = 0
    for upd in updates:
        row_code = upd.get("row_code")
        amount = upd.get("current_period_amount")
        if not row_code or amount is None:
            continue

        result = await db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.report_type == report_type,
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.row_code == row_code,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.current_period_amount = float(amount)
            updated += 1

    if updated:
        await db.commit()

    return {"updated": updated, "message": f"已更新 {updated} 行"}


@router.post("/drill-down")
async def report_drill_down(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """汇总穿透：查询各子企业在指定报表行次的实际金额

    请求体:
      project_id: 项目ID
      year: 年度
      report_type: 报表类型 (balance_sheet/income_statement/cash_flow_statement)
      row_code: 行次编码
      col_field: 列字段 (current_period_amount/prior_period_amount)
      company_codes: 子企业代码列表（可选，不传则查所有）
    """
    import json
    from sqlalchemy import text as sa_text

    project_id = body.get("project_id")
    year_val = body.get("year")
    report_type = body.get("report_type", "balance_sheet")
    row_code = body.get("row_code", "")
    col_field = body.get("col_field", "current_period_amount")
    company_codes = body.get("company_codes", [])

    if not project_id or not row_code:
        return {"rows": [], "message": "缺少 project_id 或 row_code"}

    # 1. 从 consol_worksheet_data 获取基本信息表（企业列表）
    result = await db.execute(
        sa_text("""
            SELECT data FROM consol_worksheet_data
            WHERE project_id = :pid AND year = :y AND sheet_key = 'info'
        """),
        {"pid": project_id, "y": year_val},
    )
    info_row = result.fetchone()
    companies = []
    if info_row and isinstance(info_row[0], dict):
        companies = info_row[0].get("rows", [])
    if not companies:
        return {"rows": [], "message": "未找到基本信息表数据"}

    # 2. 从各子企业的试算平衡表数据中提取指定行次的金额
    rows = []
    for comp in companies:
        code = comp.get("company_code", "")
        name = comp.get("company_name", "")
        if company_codes and code not in company_codes:
            continue

        # 查找该企业的试算平衡表数据
        tb_key = f"consol_tb_{report_type}_closing"
        tb_result = await db.execute(
            sa_text("""
                SELECT data FROM consol_worksheet_data
                WHERE project_id = :pid AND year = :y AND sheet_key = :sk
            """),
            {"pid": project_id, "y": year_val, "sk": tb_key},
        )
        tb_row = tb_result.fetchone()
        amount = None
        source = "无数据"

        if tb_row and isinstance(tb_row[0], dict):
            tb_rows = tb_row[0].get("rows", [])
            for tr in tb_rows:
                if tr.get("row_code") == row_code:
                    # 优先取审定数（audited），其次取汇总数（summary）
                    amount = tr.get("audited") or tr.get("summary")
                    source = "试算平衡表"
                    break

        # 如果试算表没有，尝试从 report_config 取
        if amount is None:
            try:
                rc_result = await db.execute(
                    sa_text("""
                        SELECT current_period_amount, prior_period_amount
                        FROM report_config
                        WHERE row_code = :rc AND report_type = :rt
                          AND is_deleted = false
                        LIMIT 1
                    """),
                    {"rc": row_code, "rt": report_type},
                )
                rc_row = rc_result.fetchone()
                if rc_row:
                    amount = float(rc_row[0]) if col_field == "current_period_amount" and rc_row[0] else (
                        float(rc_row[1]) if rc_row[1] else None
                    )
                    source = "报表配置"
            except Exception:
                pass

        ratio_val = comp.get("non_common_ratio") or comp.get("common_ratio") or 0
        rows.append({
            "company_code": code,
            "company_name": name,
            "amount": amount,
            "ratio": ratio_val,
            "source": source,
            "holding_type": comp.get("holding_type", "直接"),
            "parent_name": comp.get("indirect_holder", "母公司"),
        })

    # 计算占比
    total = sum(r["amount"] or 0 for r in rows)
    for r in rows:
        if total and r["amount"]:
            r["pct"] = round((r["amount"] / abs(total)) * 100, 2)
        else:
            r["pct"] = 0

    return {"rows": rows, "total": total, "row_code": row_code, "col_field": col_field}


@router.post("/execute-formula")
async def execute_formula(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行公式表达式，返回计算结果和执行追踪

    请求体:
      project_id: 项目ID
      year: 年度
      formula: 公式字符串（如 "TB('1001','期末余额') + 100"）
      row_values: 可选，行引用值映射（如 {"BS-002": 50000, "BS-003": 30000}）
    """
    from app.services.formula_parser import evaluate_formula
    from app.services.formula_engine import FormulaEngine

    project_id_str = body.get("project_id", "")
    year_val = body.get("year", 2024)
    formula = body.get("formula", "")
    row_values_raw = body.get("row_values", {})

    if not formula:
        return {"value": None, "trace": [], "error": "公式不能为空"}

    from decimal import Decimal
    from uuid import UUID
    try:
        pid = UUID(project_id_str) if project_id_str else None
    except ValueError:
        pid = None

    row_values = {k: Decimal(str(v)) for k, v in row_values_raw.items()} if row_values_raw else None

    engine = FormulaEngine()
    result = await evaluate_formula(
        formula=formula,
        db=db,
        project_id=pid,
        year=year_val,
        engine=engine,
        row_values=row_values,
    )
    return result


@router.post("/execute-formulas-batch")
async def execute_formulas_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量执行公式（带依赖排序）

    请求体:
      project_id: 项目ID
      year: 年度
      formulas: [{ row_code: "BS-002", formula: "TB('1001','期末余额')" }, ...]
    """
    from app.services.formula_parser import evaluate_formula, parse_formula, RowRefNode, RangeSumNode, BinOpNode, FuncCallNode
    from app.services.formula_engine import FormulaEngine
    from decimal import Decimal
    from uuid import UUID

    project_id_str = body.get("project_id", "")
    year_val = body.get("year", 2024)
    formulas = body.get("formulas", [])

    try:
        pid = UUID(project_id_str) if project_id_str else None
    except ValueError:
        pid = None

    engine = FormulaEngine()
    row_values: dict[str, Decimal] = {}
    results = []

    # 简单拓扑排序：先执行无依赖的，再执行有依赖的
    # 第一轮：收集所有行引用依赖
    def collect_deps(node) -> set[str]:
        deps = set()
        if isinstance(node, RowRefNode):
            deps.add(node.row_code)
        elif isinstance(node, RangeSumNode):
            deps.add(f"RANGE:{node.start_code}:{node.end_code}")
        elif isinstance(node, BinOpNode):
            deps |= collect_deps(node.left)
            deps |= collect_deps(node.right)
        elif isinstance(node, FuncCallNode):
            for arg in node.args:
                deps |= collect_deps(arg)
        return deps

    parsed = []
    for f in formulas:
        code = f.get("row_code", "")
        formula_str = f.get("formula", "")
        if not formula_str:
            parsed.append((code, formula_str, None, set()))
            continue
        try:
            ast = parse_formula(formula_str)
            deps = collect_deps(ast)
            parsed.append((code, formula_str, ast, deps))
        except Exception as e:
            parsed.append((code, formula_str, None, set()))
            results.append({"row_code": code, "value": None, "error": str(e)})

    # 拓扑排序执行（支持并行：同一轮次内无依赖的公式并行执行）
    executed = set()
    max_rounds = len(parsed) + 1
    for _round in range(max_rounds):
        # 收集本轮可执行的公式
        batch = []
        for code, formula_str, ast, deps in parsed:
            if code in executed:
                continue
            unmet = {d for d in deps if not d.startswith("RANGE:") and d not in executed}
            if unmet:
                continue
            if ast is None:
                executed.add(code)
                continue
            batch.append((code, formula_str))

        if not batch:
            break

        # 并行执行本轮所有公式
        import asyncio
        async def _exec_one(code: str, formula_str: str):
            return code, await evaluate_formula(
                formula=formula_str, db=db, project_id=pid, year=year_val,
                engine=engine, row_values=row_values,
            )

        batch_results = await asyncio.gather(*[_exec_one(c, f) for c, f in batch])

        for code, result in batch_results:
            if result.get("value") is not None:
                row_values[code] = Decimal(str(result["value"]))
            results.append({"row_code": code, **result})
            executed.add(code)

    # 未执行的（循环依赖）
    for code, formula_str, ast, deps in parsed:
        if code not in executed:
            results.append({"row_code": code, "value": None, "error": f"循环依赖: {deps - executed}"})

    # 记录审计日志
    try:
        from app.routers.formula_audit_log import ensure_table as ensure_fal_table
        await ensure_fal_table(db)
        import json as _json
        import uuid as _uuid
        from datetime import datetime as _dt
        for r in results:
            if r.get("value") is not None:
                formula_str_log = next((f.get("formula", "") for f in formulas if f.get("row_code") == r["row_code"]), "")
                await db.execute(
                    text("""INSERT INTO formula_audit_log (id, project_id, year, module, row_code, action, new_formula, result_value, trace, created_at)
                        VALUES (:id, :pid, :y, 'report', :rc, 'execute', :nf, :rv, CAST(:tr AS jsonb), :now)"""),
                    {"id": str(_uuid.uuid4()), "pid": project_id_str, "y": year_val,
                     "rc": r["row_code"], "nf": formula_str_log, "rv": r["value"],
                     "tr": _json.dumps(r.get("trace", []), ensure_ascii=False),
                     "now": _dt.utcnow()},
                )
        await db.commit()
    except Exception:
        pass  # 日志记录失败不影响主流程

    return {"results": results, "row_values": {k: float(v) for k, v in row_values.items()}}
