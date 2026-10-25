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
    """克隆标准配置到项目。

    ``mode=sync``（默认）：幂等把**有公式的行**落成项目级配置（``project:{id}``），
    供取数层按项目优先读取；可反复执行，返回 created/updated/skipped。

    ``mode=strict``（legacy，需显式传）：全量克隆（含无公式结构行），项目级已存在则 400。
    """
    svc = ReportConfigService(db)
    try:
        if data.mode == "sync":
            result = await svc.materialize_project_presets(
                project_id=data.project_id,
                applicable_standard=data.applicable_standard,
                overwrite=data.overwrite,
            )
            await db.commit()
            return {
                "message": (
                    f"已落入 {result['created']} 条项目级公式"
                    f"（更新 {result['updated']}，跳过 {result['skipped']}）"
                ),
                "count": result["created"],
                **result,
            }
        count = await svc.clone_report_config(
            project_id=data.project_id,
            applicable_standard=data.applicable_standard or "enterprise",
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
        # Capture old formula for event payload
        old_row = await svc.get_config(config_id)
        old_formula = old_row.formula if old_row else None

        # P2-2: 公式保存前校验地址有效性（悬空引用拒绝保存）
        new_formula = updates.get("formula")
        if new_formula and new_formula != old_formula:
            project_id = updates.get("project_id", "")
            year = updates.get("year", 0)
            template_type = updates.get("template_type", "soe")
            # 尝试从 applicable_standard 推导 project_id
            if not project_id and old_row:
                std = old_row.applicable_standard or ""
                if std.startswith("project:"):
                    project_id = std.removeprefix("project:")
            if project_id and year:
                from app.services.acnr.formula_validation import (
                    validate_refs_via_acnr,
                )
                issues = await validate_refs_via_acnr(
                    db, str(project_id), int(year), new_formula, template_type
                )
                if issues:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "error_code": "FORMULA_DANGLING_REFS",
                            "message": "公式含悬空引用，拒绝保存",
                            "issues": issues,
                        },
                    )

        row = await svc.update_config(config_id, updates, user_id=current_user.id)
        await db.commit()

        # Publish FORMULA_CONFIG_CHANGED event if formula changed
        # 🔴 修复前 project_id 传的是 current_user.id（「row has no project_id」的兜底），
        #    下游 stale_engine 于是按一个**用户 id** 去标 stale、年份再猜 2025 ——
        #    全局模板行的编辑对任何真实项目都不起作用，对项目克隆行也标错对象。
        #    正解：只有项目克隆行（applicable_standard='project:{uuid}'）才有项目可标；
        #    全局模板行的传播由 REPORT_CONFIG_MASTER_UPDATED（report-config-baseline）负责，
        #    不在这里冒充项目事件。
        try:
            new_formula = row.formula if row else None
            std = (row.applicable_standard or "") if row else ""
            if old_formula != new_formula:
                # 反向索引（「谁引用了该单元格」面板）按 report_config 全表构建，与项目无关：
                # 模板行 / 克隆行改公式都要失效。原先靠 handler 顺带失效（且因 project_id
                # 是用户 id 才恰好每次都跑到）；事件只对克隆行发布后必须在此直接失效，
                # 否则模板行编辑后面板显示过时引用关系。
                from app.services.formula_reverse_index import invalidate_reverse_index
                invalidate_reverse_index()
            if old_formula != new_formula and std.startswith("project:"):
                from uuid import UUID as _UUID

                from app.models.audit_platform_schemas import EventPayload, EventType
                from app.services.event_bus import event_bus

                await event_bus.publish(EventPayload(
                    event_type=EventType.FORMULA_CONFIG_CHANGED,
                    project_id=_UUID(std.removeprefix("project:")),
                    extra={
                        "row_code": row.row_code if row else "",
                        "old_formula": old_formula,
                        "new_formula": new_formula,
                    },
                ))
        except Exception:
            pass  # Never block main operation

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


@router.post("/drill-down")
async def report_drill_down(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """汇总穿透：合并报表某行由企业树各节点怎样构成（spec consol-elimination-single-source-push 需求 9.3）。

    与报表差额表同一求值（``consol_report_view_service.child_contributions``）：``rows`` = 所选汇总节点
    （默认根合并节点）的直接子节点，``leaf_rows`` = 子树全部末级节点；线性行两层之和都 = 合并数。
    不再读 ``consol_worksheet_data['info']``、不再按持股比例估算。项目在请求体里 ⇒ 函数体内做项目级鉴权。

    请求体：``project_id``、``year``（可选，默认项目审计年度）、``report_type``、``row_code``、``node_key``（可选）。
    """
    from app.deps import assert_project_permission
    from app.services.consol_report_view_service import ViewError, child_contributions, load_view_context

    try:
        project_id = UUID(str(body.get("project_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="缺少或无效的 project_id") from exc
    row_code = str(body.get("row_code") or "").strip()
    if not row_code:
        raise HTTPException(status_code=400, detail="缺少 row_code")
    await assert_project_permission(db, current_user, project_id, "readonly")
    year_val = body.get("year")
    ctx = await load_view_context(db, project_id, int(year_val) if year_val else None)
    if ctx is None:
        raise HTTPException(status_code=404, detail="不是合并报表项目或没有审计年度，无法穿透")
    try:
        result = await child_contributions(
            ctx.basis, ctx.rows, report_type=str(body.get("report_type") or "balance_sheet"),
            row_code=row_code, node_key=body.get("node_key") or None,
        )
    except ViewError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"year": ctx.year, "applicable_standard": ctx.standard, **result}


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

    阶段 2 改造（Task 11）：统一走 L1 内核（formula_engine.execute），
    不再使用 formula_parser.evaluate_formula 独立求值器。
    Validates: Requirements 1.1, 1.3, 7.3
    """
    from decimal import Decimal
    from uuid import UUID

    from app.services.formula_engine import execute as fe_execute, FormulaContext, FormulaResult
    from app.services.amount_resolver import TrialBalanceResolver
    from app.services.report_engine import evaluate_formula as re_evaluate

    project_id_str = body.get("project_id", "")
    year_val = body.get("year", 2024)
    formula = body.get("formula", "")
    row_values_raw = body.get("row_values", {})

    if not formula:
        return {"value": None, "trace": [], "error": "公式不能为空"}

    try:
        pid = UUID(project_id_str) if project_id_str else None
    except ValueError:
        pid = None

    row_values = {k: Decimal(str(v)) for k, v in row_values_raw.items()} if row_values_raw else None

    try:
        # 使用 L2 编排层（report_engine.evaluate_formula）→ 委托 L1 内核
        # L2 负责 async 取数（经 TrialBalanceResolver）→ 构建 FormulaContext → 调 L1 execute
        resolver = TrialBalanceResolver(db, pid, year_val) if pid else None

        if resolver:
            value = await re_evaluate(
                formula,
                resolver=resolver,
                row_cache=row_values,
            )
            # 为了保持返回结构兼容，也跑一次 L1 内核获取 trace
            ctx = FormulaContext(
                tb_data={},
                row_cache={k: Decimal(str(v)) for k, v in (row_values or {}).items()},
            )
            result_obj = fe_execute(formula, ctx)
            trace = result_obj.trace
        else:
            # 无 project_id 时直接走 L1 内核纯求值（无取数）
            ctx = FormulaContext(
                tb_data={},
                row_cache={k: Decimal(str(v)) for k, v in (row_values or {}).items()},
            )
            result_obj = fe_execute(formula, ctx)
            value = result_obj.value
            trace = result_obj.trace

        return {
            'value': float(value),
            'trace': trace,
            'error': None,
        }
    except Exception as e:
        return {
            'value': None,
            'trace': [],
            'error': f'执行错误: {e}',
        }


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

    阶段 2 改造（Task 11）：统一走 L1 内核（formula_engine），
    不再使用 formula_parser 独立求值器。
    Validates: Requirements 1.1, 1.3, 7.3
    """
    from app.services.formula_engine import (
        parse_to_ast, ASTRowRef, ASTRangeSum, ASTBinOp, ASTFuncCall,
        execute as fe_execute, FormulaContext, FormulaParseError,
    )
    from app.services.amount_resolver import TrialBalanceResolver
    from app.services.report_engine import evaluate_formula as re_evaluate
    from decimal import Decimal
    from uuid import UUID

    project_id_str = body.get("project_id", "")
    year_val = body.get("year", 2024)
    formulas = body.get("formulas", [])

    try:
        pid = UUID(project_id_str) if project_id_str else None
    except ValueError:
        pid = None

    row_values: dict[str, Decimal] = {}
    results = []

    # 简单拓扑排序：先执行无依赖的，再执行有依赖的
    # 第一轮：收集所有行引用依赖
    def collect_deps(node) -> set[str]:
        deps = set()
        if isinstance(node, ASTRowRef):
            deps.add(node.row_code)
        elif isinstance(node, ASTRangeSum):
            deps.add(f"RANGE:{node.start_code}:{node.end_code}")
        elif isinstance(node, ASTBinOp):
            deps |= collect_deps(node.left)
            deps |= collect_deps(node.right)
        elif isinstance(node, ASTFuncCall):
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
            ast = parse_to_ast(formula_str)
            deps = collect_deps(ast)
            parsed.append((code, formula_str, ast, deps))
        except (FormulaParseError, Exception) as e:
            parsed.append((code, formula_str, None, set()))
            results.append({"row_code": code, "value": None, "error": str(e)})

    # 构建 resolver（L2 取数适配层）
    resolver = TrialBalanceResolver(db, pid, year_val) if pid else None

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
            try:
                if resolver:
                    value = await re_evaluate(
                        formula_str,
                        resolver=resolver,
                        row_cache=row_values,
                    )
                    return code, {'value': float(value), 'trace': [], 'error': None}
                else:
                    ctx = FormulaContext(
                        tb_data={},
                        row_cache={k: Decimal(str(v)) for k, v in row_values.items()},
                    )
                    result_obj = fe_execute(formula_str, ctx)
                    return code, {
                        'value': float(result_obj.value),
                        'trace': result_obj.trace,
                        'error': result_obj.errors[0] if result_obj.errors else None,
                    }
            except Exception as e:
                return code, {'value': None, 'trace': [], 'error': f'执行错误: {e}'}

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

    # 记录审计日志（统一走哈希链 append_audit_log）
    try:
        from app.services.audit_log_helper import append_audit_log
        for r in results:
            if r.get("value") is not None:
                formula_str_log = next((f.get("formula", "") for f in formulas if f.get("row_code") == r["row_code"]), "")
                await append_audit_log(db, {
                    "user_id": current_user.id,
                    "project_id": pid,
                    "action": "formula.changed",
                    "resource_type": "report_config",
                    "resource_id": r["row_code"],
                    "details": {
                        "event_type": "formula_changed",
                        "module": "report",
                        "row_code": r["row_code"],
                        "action": "execute",
                        "old_formula": "",
                        "new_formula": formula_str_log,
                        "result_value": str(r["value"]),
                        "trace": r.get("trace", []),
                    },
                })
        await db.commit()
    except Exception:
        pass  # 日志记录失败不影响主流程

    return {"results": results, "row_values": {k: float(v) for k, v in row_values.items()}}


# ─────────────────────────────────────────────────────────────────────────────
# 试算表「科目明细」公式（tb_detail）项目级覆盖 + 自定义新增
#
# 背景：公式管理中心「试算平衡表 > 科目明细」节点原为按科目动态生成
# TB('科目','期末余额') 只读预设，无法二次编辑/新增，预设不对时无从修正。
# 现改为：默认预设仍自动生成（分类=自动运算），但支持用户覆盖某科目公式、
# 或新增自定义公式行，持久化到 project.wizard_state.tb_detail_formulas。
#
# 复用 aging_config 的 wizard_state JSONB 项目级存储范式（无新表/迁移）。
# ─────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel as _TbBaseModel  # noqa: E402
from sqlalchemy import select  # noqa: E402 — 🔴 此前漏 import：两个端点每次调用都 NameError
from app.models.core import Project as _TbProject  # noqa: E402


class TbDetailFormulaItem(_TbBaseModel):
    row_code: str
    row_name: str | None = None
    formula: str | None = None
    # 用户要求：分类默认为自动运算类型
    formula_category: str | None = "auto_calc"
    formula_description: str | None = None


class TbDetailFormulasPayload(_TbBaseModel):
    # overrides：科目编码 → 覆盖项（覆盖默认 TB() 预设）
    overrides: dict[str, TbDetailFormulaItem] = {}
    # added：用户新增的自定义公式行
    added: list[TbDetailFormulaItem] = []


async def _tb_get_project_or_404(db: AsyncSession, project_id: UUID) -> _TbProject:
    result = await db.execute(select(_TbProject).where(_TbProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("/tb-detail-formulas/{project_id}")
async def get_tb_detail_formulas(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取试算表科目明细公式的项目级覆盖 + 自定义新增。

    返回 {overrides: {code: {...}}, added: [{...}]}；无配置时返回空结构。
    """
    project = await _tb_get_project_or_404(db, project_id)
    ws = project.wizard_state or {}
    cfg = ws.get("tb_detail_formulas") or {}
    return {
        "overrides": cfg.get("overrides") or {},
        "added": cfg.get("added") or [],
    }


@router.put("/tb-detail-formulas/{project_id}")
async def save_tb_detail_formulas(
    project_id: UUID,
    body: TbDetailFormulasPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(["admin", "partner", "signing_partner", "manager"])
    ),
):
    """保存试算表科目明细公式覆盖 + 自定义新增到 wizard_state.tb_detail_formulas。

    铁律：合并写入 wizard_state（不覆盖其他字段）。
    """
    from sqlalchemy.orm.attributes import flag_modified

    project = await _tb_get_project_or_404(db, project_id)

    overrides = {
        code: item.model_dump() for code, item in (body.overrides or {}).items()
    }
    added = [item.model_dump() for item in (body.added or [])]

    ws = dict(project.wizard_state) if project.wizard_state else {}
    ws["tb_detail_formulas"] = {"overrides": overrides, "added": added}
    project.wizard_state = ws
    flag_modified(project, "wizard_state")

    await db.flush()
    await db.commit()
    return {
        "overrides": overrides,
        "added": added,
        "message": "科目明细公式已保存",
    }


@router.get("/row-note-mapping")
async def get_row_note_mapping(
    applicable_standard: str = Query(..., description="变体标识如 soe_standalone/listed_standalone"),
    current_user: User = Depends(get_current_user),
):
    """返回指定变体的「报表行次→附注章节」映射（含全局连续序号）。

    来源: report_row_note_mapping.json（静态数据，按变体区分）。
    返回 {row_code: {section_code, section_title, seq}} 。
    seq 为全报表连续编号（BS→IS→CFS→EQ→CFSS→IMP 顺序），供前端直接显示「五、N」。
    """
    from app.services.report_excel_exporter import _load_note_ref_mapping

    all_mappings = _load_note_ref_mapping()
    variant = all_mappings.get(applicable_standard, {})
    # 为每个条目加全局连续序号（按 JSON 键出现顺序=BS→IS→CFS→EQ→CFSS→IMP）
    result = {}
    seq = 0
    for row_code, info in variant.items():
        seq += 1
        entry = dict(info) if isinstance(info, dict) else {"section_code": str(info)}
        entry["seq"] = seq
        result[row_code] = entry
    return result
