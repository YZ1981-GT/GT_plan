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
from app.deps import (
    assert_project_permission,
    get_current_user,
    require_project_access,
    require_role,
)
from app.models.core import User
from app.models.report_models import FinancialReportType, ReportConfig
from app.models.report_schemas import ReportConfigCloneRequest, ReportConfigRow
from app.services import report_config_execute
from app.services.formula_settings import legacy_report
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.propagation import publish_events
from app.services.report_config_service import ReportConfigService

router = APIRouter(
    prefix="/api/report-config",
    tags=["report-config"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Task 5.3 / ADR-FMC-06 · report_config 写鉴权分流
#
# report_config 是**全局模板表**（无 project_id 列，按 applicable_standard 四标准区分）：
#   · 全局模板行（applicable_standard ∈ {enterprise, small_business, listed, ...}，
#     即非 "project:{uuid}"）：对所有项目共享，**写操作须限 admin**。任意登录用户
#     篡改全局模板会污染所有项目取数。
#   · 项目克隆行（applicable_standard == "project:{uuid}"）：属该项目，写按
#     require_project_access("edit") —— 非该项目成员（含有角色但无项目归属者）被 403。
#
# 两条依赖工厂（require_role / require_project_access）不能在同一函数签名里按行内容
# 条件挂载，故在函数体内显式分流（直调 assert_project_permission，避免「依赖工厂每次
# 返回新对象」的 override 失效坑，memory 教训㉕①）。
# ─────────────────────────────────────────────────────────────────────────────


def _project_id_from_standard(applicable_standard: str | None) -> UUID | None:
    """项目克隆行的 applicable_standard 形如 "project:{uuid}"，解析出 project_id；
    全局模板行返回 None。"""
    std = (applicable_standard or "").strip()
    if not std.startswith("project:"):
        return None
    try:
        return UUID(std.removeprefix("project:"))
    except ValueError:
        return None


async def _authorize_report_config_write(
    db: AsyncSession,
    current_user: User,
    applicable_standard: str | None,
) -> None:
    """report_config 写鉴权分流：项目克隆行 → require_project_access("edit")；
    全局模板行 → admin only。非 admin 写全局模板 / 非成员写项目克隆行 → 403。"""
    project_id = _project_id_from_standard(applicable_standard)
    if project_id is not None:
        # 项目克隆行：项目级 edit 归属校验（admin 在 assert_project_permission 内放行）。
        await assert_project_permission(db, current_user, project_id, "edit")
        return
    # 全局模板行：仅 admin 可写。
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="权限不足：全局报表模板写操作仅限 admin")


async def _authorize_report_config_read(
    db: AsyncSession,
    current_user: User,
    *,
    project_id: UUID | None,
    applicable_standard: str | None,
) -> UUID | None:
    """校验 report_config 读/执行上下文，禁止用 project:{id} 绕过项目鉴权。"""
    standard_project_id = _project_id_from_standard(applicable_standard)
    if (
        project_id is not None
        and standard_project_id is not None
        and project_id != standard_project_id
    ):
        raise HTTPException(status_code=403, detail="project_id 与 applicable_standard 项目不一致")
    effective_project_id = project_id or standard_project_id
    if effective_project_id is not None:
        await assert_project_permission(
            db, current_user, effective_project_id, "readonly"
        )
    return effective_project_id


async def _legacy_write(db: AsyncSession, coro) -> dict:
    """旧写路径经公式设置同步内核（formula-global-settings-sync R9）：
    业务错误（428 / 409 / 400）回滚并转 HTTP；成功 commit 之后才发变更事件。"""
    try:
        result = await coro
    except FormulaSettingError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    await db.commit()
    await publish_events(result.get("events") or [], domain="report", source="direct_edit",
                         token=result.get("publish_id"))
    return result


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

    Task 5.3 / ADR-FMC-06：给定 project_id 时按 readonly 做项目级鉴权（禁任意登录
    用户用他人 project_id 解析其 applicable_standard）；无 project_id 的全局模板读
    保持登录门控（全局模板非敏感，design §5 步骤 5 未要求收紧全局读）。
    """
    effective_project_id = await _authorize_report_config_read(
        db,
        current_user,
        project_id=project_id,
        applicable_standard=applicable_standard,
    )
    if not applicable_standard and effective_project_id:
        applicable_standard = await ReportConfigService.resolve_applicable_standard(
            db, effective_project_id
        )
    if not applicable_standard:
        applicable_standard = "enterprise"
    svc = ReportConfigService(db)
    rows = await svc.list_configs(
        report_type=report_type,
        applicable_standard=applicable_standard,
    )
    return [ReportConfigRow.model_validate(r) for r in rows]


# 报表子类标签（与前端 FormulaManagerDialog.vue REPORT_SUBTYPE_LABELS_FALLBACK 对齐）。
_REPORT_TYPE_LABELS: dict[str, str] = {
    "balance_sheet": "资产负债表",
    "income_statement": "利润表",
    "cash_flow_statement": "现金流量表",
    "equity_statement": "权益变动表",
    "cash_flow_supplement": "现金流附表",
    "impairment_provision": "资产减值准备表",
}


# ⚠️ 路由顺序铁律（§1 #8 / design §5 步骤 6）：静态路径 `GET /types` 必须声明在
# 动态路径 `GET /{config_id}`（config_id: UUID）**之前**，否则 `/types` 会被 UUID 路由
# 先匹配、解析失败返 422。FastAPI 按声明顺序匹配，先声明者优先。
@router.get("/types")
async def list_report_types(
    project_id: UUID | None = Query(None),
    applicable_standard: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回当前项目（标准）下的报表子类列表及每类公式行数。

    契约（前端 FormulaManagerDialog.vue loadReportTypes / docStructureTree
    buildDocStructureDynamic 消费）：返回 `[{report_type, label, formula_count}]`。

    优先级与 list_report_configs 一致：applicable_standard 显式传入 > 从 project_id
    自动解析 > 降级 enterprise。给定 project_id 时按 readonly 做项目级鉴权（Task 5.3 /
    ADR-FMC-06 同口径，禁任意登录用户用他人 project_id 解析其 applicable_standard）。
    """
    effective_project_id = await _authorize_report_config_read(
        db,
        current_user,
        project_id=project_id,
        applicable_standard=applicable_standard,
    )
    if not applicable_standard and effective_project_id:
        applicable_standard = await ReportConfigService.resolve_applicable_standard(
            db, effective_project_id
        )
    if not applicable_standard:
        applicable_standard = "enterprise"

    svc = ReportConfigService(db)
    rows = await svc.list_configs(applicable_standard=applicable_standard)

    # 统计每个报表子类的公式行数（有 formula 的行计入）。
    counts: dict[str, int] = {}
    for r in rows:
        rt = r.report_type.value if hasattr(r.report_type, "value") else str(r.report_type)
        if (r.formula or "").strip():
            counts[rt] = counts.get(rt, 0) + 1

    # 枚举全部报表子类（固定 6 类），formula_count 从统计填充（无公式则 0）。
    return [
        {
            "report_type": rt.value,
            "label": _REPORT_TYPE_LABELS.get(rt.value, rt.value),
            "formula_count": counts.get(rt.value, 0),
        }
        for rt in FinancialReportType
    ]


@router.get("/{config_id}")
async def get_report_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询单行配置详情。

    Task 5.3 / ADR-FMC-06：项目克隆行（applicable_standard=project:{uuid}）按 readonly
    做项目级鉴权；全局模板行读保持登录门控（非敏感）。
    """
    svc = ReportConfigService(db)
    row = await svc.get_config(config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置行不存在")
    project_id = _project_id_from_standard(getattr(row, "applicable_standard", None))
    if project_id is not None:
        await assert_project_permission(db, current_user, project_id, "readonly")
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

    Task 5.3 / ADR-FMC-06：克隆是把全局模板物化成**目标项目**的项目级公式（写入
    ``project:{data.project_id}`` 行），属项目级写 → 对 ``data.project_id`` 做
    ``require_project_access("edit")``（非目标项目成员被 403）。
    """
    await assert_project_permission(db, current_user, data.project_id, "edit")
    svc = ReportConfigService(db)
    try:
        if data.mode == "sync":
            result = await svc.materialize_project_presets(
                project_id=data.project_id,
                applicable_standard=data.applicable_standard,
                overwrite=data.overwrite,
                user_id=current_user.id,
            )
            await db.commit()
            await publish_events(result.pop("events", []), domain="report", source="materialize")
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
    """修改配置行。

    Task 5.3 / ADR-FMC-06：写鉴权按行分流 —— 项目克隆行
    （applicable_standard=project:{uuid}）→ require_project_access("edit")；
    全局模板行 → admin only。body 的 project_id 与行归属不一致时 403
    （防以 A 的归属改 B 的行 / 伪造 project_id 绕过）。
    """
    svc = ReportConfigService(db)
    try:
        # Capture old formula for event payload
        old_row = await svc.get_config(config_id)
        if old_row is None:
            raise HTTPException(status_code=404, detail="配置行不存在")
        old_formula = old_row.formula if old_row else None

        # ── 写鉴权分流（必须在任何写操作前）──
        row_std = getattr(old_row, "applicable_standard", None)
        row_pid = _project_id_from_standard(row_std)
        # body/query 携带的 project_id 若与行归属不一致 → 403（不以入参冒充归属）。
        body_pid_raw = str(updates.get("project_id") or "").strip()
        if body_pid_raw:
            try:
                body_pid = UUID(body_pid_raw)
            except ValueError:
                body_pid = None
            if body_pid is not None and row_pid is not None and body_pid != row_pid:
                raise HTTPException(
                    status_code=403, detail="权限不足：project_id 与配置行归属不一致"
                )
        await _authorize_report_config_write(db, current_user, row_std)

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

        # spec formula-global-settings-sync R9：全局行 = 直接发布（全部应用 + 冲突交项目确认），
        # 项目行 = 保存本项目适配；改公式须带 expected_version（缺失 428、不一致 409）。
        # commit 之后才发变更事件（受影响项目标过期重算 + 反向索引失效）。
        result = await _legacy_write(db, legacy_report.update_row(db, old_row, updates, user_id=current_user.id))
        return ReportConfigRow.model_validate(result["row"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_report_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新增配置行。

    Task 5.3 / ADR-FMC-06：项目克隆行（applicable_standard=project:{uuid}）→
    require_project_access("edit")；全局模板行 → admin only。
    """
    await _authorize_report_config_write(
        db, current_user, body.get("applicable_standard")
    )
    # R9：全局 = 新增公式位的发布；项目 = 本项目适配（项目独有行带结构）
    result = await _legacy_write(db, legacy_report.create_row(db, body, user_id=current_user.id))
    return ReportConfigRow.model_validate(result["row"])


@router.delete("/{config_id}")
async def delete_report_config(
    config_id: UUID,
    expected_version: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除配置行。

    Task 5.3 / ADR-FMC-06：写鉴权按行分流 —— 项目克隆行 →
    require_project_access("edit")；全局模板行 → admin only。
    R9：全局行 = 删除公式位的发布（须带 ``expected_version``）；项目行 = 恢复为全局。
    """
    import sqlalchemy as sa
    result = await db.execute(
        sa.select(ReportConfig).where(ReportConfig.id == config_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="行不存在")
    await _authorize_report_config_write(
        db, current_user, getattr(row, "applicable_standard", None)
    )
    await _legacy_write(db, legacy_report.delete_row(db, row, user_id=current_user.id,
                                                     expected_version=expected_version))
    return {"deleted": True}


@router.post("/seed")
async def load_seed_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """加载种子数据并填充公式（全局模板写操作，仅 admin）。"""
    from app.services.report_formula_service import report_formula_service

    svc = ReportConfigService(db)
    count = await svc.load_seed_data()
    await db.commit()

    # 自动填充公式（幂等，已有公式的行跳过）；填出的公式经全局发布，commit 后对有效定义变化的项目发事件
    try:
        formula_stats = await report_formula_service.fill_all_formulas(db, standard="all", user_id=current_user.id)
    except FormulaSettingError as exc:  # 并发修改（409）等：回滚填充，种子行已提交
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    await db.commit()
    await publish_events(formula_stats.pop("events", []), domain="report", source="seed")

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

    try:
        stats = await report_formula_service.fill_all_formulas(db, standard=standard, user_id=current_user.id)
    except FormulaSettingError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    await db.commit()
    await publish_events(stats.pop("events", []), domain="report", source="seed")

    return {
        "total": stats["total"],
        "updated": stats["updated"],
        "skipped": stats["skipped"],
        "coverage": f"{stats['coverage_pct']}%",
    }


@router.post("/execute-formula")
async def execute_formula(
    body: report_config_execute.ExecuteFormulaBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """公式试算：请求体 ``project_id`` / ``year``（必填）/ ``formula`` / ``row_values``。

    有项目时按 readonly 鉴权；求值、预算与返回形状见 ``services/report_config_execute.execute_one``。
    """
    project_id = report_config_execute.parse_project_id(body.project_id)
    if project_id is not None:
        await assert_project_permission(db, current_user, project_id, "readonly")
    return await report_config_execute.execute_one(db, project_id, body)


@router.post("/execute-formulas-batch")
async def execute_formulas_batch(
    body: report_config_execute.ExecuteFormulasBatchBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量公式试算：请求体 ``project_id`` / ``year``（必填）/ ``formulas: [{row_code, formula}]``。

    有项目时按 readonly 鉴权；行次依赖拓扑序串行、整批一个时限、上限 1000 条，见
    ``services/report_config_execute.execute_batch``。
    """
    project_id = report_config_execute.parse_project_id(body.project_id)
    if project_id is not None:
        await assert_project_permission(db, current_user, project_id, "readonly")
    return await report_config_execute.execute_batch(db, current_user, project_id, body)


# ─────────────────────────────────────────────────────────────────────────────
# 2026-10-20 迁出、路径不变（自带 /api/report-config 前缀，在 router_registry/report.py §4 紧随本路由注册）：
#   试算表「科目明细」公式 → ``routers/tb_detail_formulas.py``（spec formula-global-settings-sync，存 formula_setting）
#   合并报表汇总穿透 → ``routers/report_drill_down.py``（本文件超行数门）
# ─────────────────────────────────────────────────────────────────────────────


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
