"""试算表 API"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import get_current_user, require_project_access, get_user_scope_cycles
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import User
from app.deps import check_consol_lock
from app.services.cache_service import CacheService
from app.services.mapping_service import get_codes_by_cycles
from app.services.event_bus import event_bus
from app.services.ledger_import.sign_convention_guard import check_sign_convention_readiness
from app.services.materiality_service import MaterialityService
from app.services.trial_balance_service import TrialBalanceService

router = APIRouter(
    prefix="/api/projects/{project_id}/trial-balance",
    tags=["trial-balance"],
)


@router.get("")
async def get_trial_balance(
    project_id: UUID,
    year: int = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取试算表（四列结构），含重要性水平高亮标记"""
    cache_svc = CacheService(redis)

    # 尝试从 Redis 缓存获取（60s TTL）
    cached = await cache_svc.get_tb_cache(project_id, year, company_code)
    if cached is not None:
        # 缓存命中：仍需做 scope_cycles 过滤（用户级别不同）
        scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
        if scope_cycles is not None:
            allowed_codes = await get_codes_by_cycles(project_id, scope_cycles)
            cached = [r for r in cached if r.get("standard_account_code") in allowed_codes]
        return cached

    svc = TrialBalanceService(db)
    rows = await svc.get_trial_balance(project_id, year, company_code)

    # 获取重要性水平用于高亮
    mat_svc = MaterialityService(db)
    materiality = await mat_svc.get_current(project_id, year)
    overall_mat = float(materiality.overall_materiality) if materiality else None
    trivial_thr = float(materiality.trivial_threshold) if materiality else None

    from app.services.ledger_import.direction_resolver import resolve_account_direction

    result = []
    for r in rows:
        audited = float(r.audited_amount) if r.audited_amount is not None else 0
        # 权威方向（direction_resolver 判定,前端直接使用无需自行推断）
        direction, _ = resolve_account_direction(
            r.standard_account_code, r.account_name or ""
        )
        item = {
            "standard_account_code": r.standard_account_code,
            "account_name": r.account_name,
            "account_category": r.account_category.value if r.account_category else None,
            "direction": direction,  # "debit" | "credit"
            "unadjusted_amount": str(r.unadjusted_amount) if r.unadjusted_amount is not None else None,
            "rje_adjustment": str(r.rje_adjustment),
            "aje_adjustment": str(r.aje_adjustment),
            "audited_amount": str(r.audited_amount) if r.audited_amount is not None else None,
            "opening_balance": str(r.opening_balance) if r.opening_balance is not None else None,
            "exceeds_materiality": abs(audited) >= overall_mat if overall_mat else False,
            "below_trivial": abs(audited) < trivial_thr if trivial_thr else False,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        result.append(item)

    # 写入 Redis 缓存（全量数据，scope 过滤在读取时做）
    await cache_svc.set_tb_cache(project_id, year, company_code, result)

    # scope_cycles 过滤
    scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
    if scope_cycles is not None:
        allowed_codes = await get_codes_by_cycles(project_id, scope_cycles)
        result = [r for r in result if r.get("standard_account_code") in allowed_codes]

    # 过渡期语义（Task 7.1 / 需求 10）：检测 v1 残留，附加 warning 不阻断
    readiness = await check_sign_convention_readiness(db, project_id, year)
    if readiness.has_legacy:
        return {
            "data": result,
            "warning": readiness.warning,
            "sign_convention_ready": False,
        }

    return result


@router.post("/recalc")
async def recalc_trial_balance(
    project_id: UUID,
    year: int = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _lock_check=Depends(check_consol_lock),
    current_user: User = Depends(require_project_access("edit")),
):
    """手动触发全量重算（合并锁定期间禁止，需编辑权限）"""
    from app.services.prerequisite_checker import PrerequisiteChecker

    check = await PrerequisiteChecker().check(db, project_id, year, "recalc")
    if not check["ok"]:
        raise HTTPException(status_code=400, detail=check)

    svc = TrialBalanceService(db)
    await svc.full_recalc(project_id, year, company_code)
    await db.commit()

    # 重算后收敛底稿 stale 标记（否则 stale-summary 永远返回旧计数，
    # 「一键重算 / 点击重算」横幅点完仍常亮）。失败不阻断重算主操作。
    stale_resolution: dict[str, int] = {"cleared": 0, "refilled": 0, "kept_stale": 0}
    try:
        from app.services.prefill_engine import resolve_stale_after_recalc
        stale_resolution = await resolve_stale_after_recalc(db, project_id, year)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # Best-effort: 重算后自动创建版本快照（content_hash 去重，相同内容不重复）
    try:
        from app.services.tb_snapshot_service import TbSnapshotService
        from app.models.audit_platform_models import TrialBalance as TbModel
        snap_svc = TbSnapshotService()
        # 读取重算后的最新试算表行
        snap_rows_stmt = sa.select(TbModel).where(
            TbModel.project_id == project_id,
            TbModel.year == year,
            TbModel.is_deleted == sa.false(),
        )
        snap_result = await db.execute(snap_rows_stmt)
        snap_rows = [
            {
                "standard_account_code": r.standard_account_code,
                "account_name": r.account_name,
                "unadjusted_amount": str(r.unadjusted_amount) if r.unadjusted_amount is not None else None,
                "aje_adjustment": str(r.aje_adjustment) if r.aje_adjustment is not None else None,
                "rje_adjustment": str(r.rje_adjustment) if r.rje_adjustment is not None else None,
                "audited_amount": str(r.audited_amount) if r.audited_amount is not None else None,
            }
            for r in snap_result.scalars().all()
        ]
        await snap_svc.create_snapshot(
            db, str(project_id), year,
            trigger="recalc",
            actor_id=str(current_user.id) if current_user else None,
            detail_rows=snap_rows,
        )
        await db.commit()
    except Exception:
        # 快照失败不阻断重算主操作
        try:
            await db.rollback()
        except Exception:
            pass

    # 失效 TB 缓存
    cache_svc = CacheService(redis)
    await cache_svc.invalidate_tb_cache(project_id, year)

    await event_bus.publish_immediate(EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project_id,
        year=year,
    ))
    return {"message": "重算完成", "stale_resolution": stale_resolution}


@router.get("/balance-check")
async def check_trial_balance(
    project_id: UUID,
    year: int = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """试算平衡校验：直接从 tb_balance 原始数据验证(保持与入库数据同源)。

    tb_balance.closing_balance 是 v1 口径(借正贷负),SUM 应=0(完美平衡)。
    trial_balance 经过 v2 变换(贷方取 abs + 损益取发生额)后不再保持算术平衡,
    所以平衡校验必须用 tb_balance 原始数据而非 trial_balance。

    返回 {debit_total, credit_total, diff, is_balanced, has_pnl_rows}。
    """
    import sqlalchemy as sa
    from decimal import Decimal
    from app.models.audit_platform_models import TbBalance, TrialBalance
    from app.services.dataset_query import get_active_filter

    tb = TbBalance.__table__
    active_filter = await get_active_filter(db, tb, project_id, year)

    # 原始 tb_balance level=1 的借贷总和(v1:正=借方余额,负=贷方余额)
    result = await db.execute(
        sa.select(
            sa.func.coalesce(
                sa.func.sum(sa.case((tb.c.closing_balance > 0, tb.c.closing_balance), else_=sa.literal(0))),
                0
            ).label("debit_total"),
            sa.func.coalesce(
                sa.func.sum(sa.case((tb.c.closing_balance < 0, sa.func.abs(tb.c.closing_balance)), else_=sa.literal(0))),
                0
            ).label("credit_total"),
        ).where(
            active_filter,
            tb.c.level == 1,
        )
    )
    row = result.first()
    debit_total = float(row.debit_total) if row else 0
    credit_total = float(row.credit_total) if row else 0
    diff = debit_total - credit_total

    # 检查是否含损益类
    tb2 = TrialBalance.__table__
    pnl_count = await db.execute(
        sa.select(sa.func.count()).select_from(tb2).where(
            tb2.c.project_id == project_id,
            tb2.c.year == year,
            tb2.c.is_deleted == sa.false(),
            sa.or_(
                tb2.c.standard_account_code.like("5%"),
                tb2.c.standard_account_code.like("6%"),
            ),
            tb2.c.unadjusted_amount != 0,
        )
    )
    has_pnl = (pnl_count.scalar_one() or 0) > 0

    return {
        "debit_total": debit_total,
        "credit_total": credit_total,
        "diff": diff,
        "is_balanced": abs(diff) < 1.0,
        "has_pnl_rows": has_pnl,
    }


@router.get("/trace")
async def trace_to_balance(
    project_id: UUID,
    year: int = Query(...),
    standard_account_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """数据溯源：查询标准科目对应的所有客户科目及其余额表原始数据。

    返回该标准科目由哪些客户科目汇总而来，每个客户科目的期末余额/借方发生额/贷方发生额。
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import AccountMapping, TbBalance
    from app.services.dataset_query import get_active_filter

    mp = AccountMapping.__table__
    bal = TbBalance.__table__
    balance_filter = await get_active_filter(db, bal, project_id, year)

    # 查询映射到该标准科目的所有客户科目
    q = (
        sa.select(
            bal.c.account_code,
            bal.c.account_name,
            sa.func.coalesce(bal.c.closing_balance, 0).label("closing_balance"),
            sa.func.coalesce(bal.c.debit_amount, 0).label("debit_amount"),
            sa.func.coalesce(bal.c.credit_amount, 0).label("credit_amount"),
            sa.func.coalesce(bal.c.opening_balance, 0).label("opening_balance"),
        )
        .select_from(
            bal.join(
                mp,
                sa.and_(
                    mp.c.project_id == bal.c.project_id,
                    mp.c.original_account_code == bal.c.account_code,
                    mp.c.is_deleted == sa.false(),
                ),
            )
        )
        .where(
            balance_filter,
            mp.c.standard_account_code == standard_account_code,
        )
        .order_by(bal.c.account_code)
    )

    result = await db.execute(q)
    sources = [
        {
            "account_code": r.account_code,
            "account_name": r.account_name,
            "closing_balance": float(r.closing_balance),
            "debit_amount": float(r.debit_amount),
            "credit_amount": float(r.credit_amount),
            "opening_balance": float(r.opening_balance),
        }
        for r in result.fetchall()
    ]
    return {"sources": sources}


@router.get("/summary-with-adjustments")
async def get_summary_with_adjustments(
    project_id: UUID,
    year: int = Query(...),
    report_type: str = Query("balance_sheet", description="报表类型: balance_sheet / income_statement / cash_flow_statement"),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """
    试算平衡表汇总（按报表行次），AJE/RJE 从 adjustments 表自动汇总。
    替代前端手动输入 AJE/RJE 的方案，确保数据与调整分录页面一致。
    """
    svc = TrialBalanceService(db)
    rows = await svc.get_summary_with_adjustments(project_id, year, report_type, company_code)
    return {"rows": rows}


@router.get("/consistency-check")
async def consistency_check(
    project_id: UUID,
    year: int = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """数据一致性校验"""
    svc = TrialBalanceService(db)
    issues = await svc.check_consistency(project_id, year, company_code)
    return {"consistent": len(issues) == 0, "issues": issues}


# ─── TB Writeback 旧端点已删除（spec tb-writeback-explicit-publish-gate Task 19 / Req 9.3） ──
#
# 原 `PUT /api/projects/{project_id}/trial-balance/writeback`（handler
# `writeback_audited_amount` + 请求体 `TBWritebackBody`）是 D~N 专属组件审定数**绕过
# 显式发布门**的直写旁路：无二次确认、无幂等 token、无 `publish_confirmed`，直接改
# `trial_balance.audited_amount`。本 spec 已将全部活路径（D/E/F/G/H/I/J/K/L/M/N）逐组件
# 迁移到显式发布门 `POST /api/workpapers/{wp_id}/audit-determination/publish-to-tb`
# （task 2~15），死代码全清（task 17），前端零直调 + CI 守卫锁定（task 18）。
#
# Task 19 删除决策证据（grep 实证 0 调用方）：
#   - 前端 audit-platform/frontend/src/**：`trial-balance/writeback` 零活调用（仅收口注释
#     与 `.not.toContain` 守卫断言），CI 守卫 check_tb_writeback_no_direct_call.py 锁定。
#   - 后端内部：无任何路由/服务 await 此 handler 或 HTTP 调此端点。同名
#     `writeback_audited_amount` 全部属 S 类独立 service
#     （SEstimateTBWritebackService / STransactionTBWritebackService，正交，不碰）。
#   - 后端测试：无集成测试经 HTTP client 命中此端点。
# 删端点后同步重生成 coverage ledger（wp_bound_entry_coverage.json），移除该条 http 条目，
# 使 coverage_guard 双向漂移守卫（live⇔ledger）保持 is_clean。


# ─── 试算表锁定/解锁（团队可见，持久化到 project.wizard_state） ──────────────


@router.get("/freeze-status")
async def get_freeze_status(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取试算表锁定状态（任何已认证用户可查看）。"""
    from app.models.core import Project
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    ws = project.wizard_state or {}
    freeze_key = f"tb_freeze_{year}"
    freeze_data = ws.get(freeze_key)

    if not freeze_data or not isinstance(freeze_data, dict):
        return {"is_frozen": False, "frozen_by": None, "frozen_at": None}

    return {
        "is_frozen": bool(freeze_data.get("is_frozen")),
        "frozen_by": freeze_data.get("frozen_by"),
        "frozen_at": freeze_data.get("frozen_at"),
    }


@router.put("/freeze")
async def set_freeze_status(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """锁定/解锁试算表（需编辑权限：现场经理及以上角色）。

    body: { is_frozen: bool, year: int }
    持久化到 project.wizard_state.tb_freeze_{year} = { is_frozen, frozen_by, frozen_at }
    """
    from app.models.core import Project
    from datetime import datetime, timezone
    from sqlalchemy.orm import attributes

    is_frozen = bool(body.get("is_frozen", False))
    year = body.get("year")
    if not year:
        raise HTTPException(400, "缺少 year 参数")

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    freeze_key = f"tb_freeze_{year}"

    # 就地修改 JSONB 不触发脏标记，需重新赋值
    ws = dict(project.wizard_state or {})
    if is_frozen:
        ws[freeze_key] = {
            "is_frozen": True,
            "frozen_by": current_user.username or str(current_user.id),
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        ws[freeze_key] = {"is_frozen": False, "frozen_by": None, "frozen_at": None}

    project.wizard_state = ws
    attributes.flag_modified(project, "wizard_state")
    await db.flush()
    await db.commit()

    return {
        "message": "已锁定" if is_frozen else "已解锁",
        "is_frozen": is_frozen,
        "frozen_by": ws[freeze_key].get("frozen_by"),
        "frozen_at": ws[freeze_key].get("frozen_at"),
    }
