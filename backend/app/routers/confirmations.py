"""函证管理路由

能力域 D — global-refinement-v5-closure：
完整 CRUD + 状态机推进端点。
router 统一 commit（项目铁律）。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services import confirmation_service

router = APIRouter(prefix="/projects/{project_id}/confirmations", tags=["函证管理"])


# ─── Request / Response schemas ────────────────────────────────────────────


class ConfirmationCreate(BaseModel):
    confirm_type: str = Field(..., description="函证类型: receivable/payable/bank/loan")
    counterparty: str = Field(..., description="函证对象名称")
    wp_id: str | None = None
    account_code: str | None = None
    book_amount: float | None = None
    confirmed_amount: float | None = None
    diff_amount: float | None = None
    diff_note: str | None = None


class ConfirmationUpdate(BaseModel):
    confirm_type: str | None = None
    counterparty: str | None = None
    wp_id: str | None = None
    account_code: str | None = None
    book_amount: float | None = None
    confirmed_amount: float | None = None
    diff_amount: float | None = None
    diff_note: str | None = None


class TransitionRequest(BaseModel):
    target_status: str = Field(..., description="目标状态")
    # 可选：终态（returned/matched/discrepancy）时用于发布 CONFIRMATION_RECEIVED
    # → 下游 stale 传播。调用方（如前端 syncHub）传入源函证底稿循环码与年度以精确路由。
    wp_code: str | None = Field(None, description="源函证底稿循环码 D0/F0/G0…（用于下游 stale 路由）")
    year: int | None = Field(None, description="审计年度（stale 传播按年度）")
    reply_amount: float | None = Field(None, description="回函金额（可选）")


class ReverseRequest(BaseModel):
    """撤回请求"""
    target_status: str = Field(..., description="撤回目标状态（须严格早于当前）")
    reason: str | None = Field(None, description="撤回原因（可选，记入留痕）")


# ─── Endpoints ─────────────────────────────────────────────────────────────


@router.get("")
async def list_confirmations(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取项目函证列表"""
    pid = uuid.UUID(project_id)
    items = await confirmation_service.list_confirmations(db, pid)
    await db.commit()
    return {"items": items, "total": len(items)}


@router.get("/candidates")
async def list_confirmation_candidates(
    project_id: str,
    confirm_type: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """从底稿（辅助余额表）提取指定类型的候选函证对象，供「从底稿导入」批量创建。

    注意：本路由须在 ``/{confirmation_id}`` 之前注册，避免 "candidates" 被当作 ID。
    """
    pid = uuid.UUID(project_id)
    if year is None:
        from app.services.project_audit_year import fetch_project_audit_year
        year = await fetch_project_audit_year(db, pid) or 0
    items = await confirmation_service.list_confirmation_candidates(
        db, pid, confirm_type, year
    )
    await db.commit()
    return {"items": items, "total": len(items)}


# NOTE: 原 GET /stats（confirmation_stats）已移除（confirmation-coverage-single-source spec）。
# 该端点零前端消费者、字段名 reply_rate/confirmation_coverage 与前端 ConfirmationCoverageMetrics
# 口径不一致（分母用 total_book 而非科目审定总额 TB population），属死端点 + 双算发散。
# 覆盖率唯一权威口径收敛到前端 useConfirmationData.coverageMetrics（以 TB population 为分母）。
# 如未来需服务端聚合，另起接 population 的实现，勿复活此死端点口径。


@router.post("")
async def create_confirmation(
    project_id: str,
    body: ConfirmationCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建函证"""
    pid = uuid.UUID(project_id)
    data = body.model_dump()
    data["created_by"] = user.id if hasattr(user, "id") else None
    result = await confirmation_service.create_confirmation(db, pid, data)
    await db.commit()
    return result


@router.get("/{confirmation_id}")
async def get_confirmation(
    project_id: str,
    confirmation_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取函证详情"""
    cid = uuid.UUID(confirmation_id)
    try:
        result = await confirmation_service.get_confirmation(db, cid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.put("/{confirmation_id}")
async def update_confirmation(
    project_id: str,
    confirmation_id: str,
    body: ConfirmationUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """更新函证"""
    cid = uuid.UUID(confirmation_id)
    data = body.model_dump(exclude_unset=True)
    try:
        result = await confirmation_service.update_confirmation(db, cid, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.delete("/{confirmation_id}")
async def delete_confirmation(
    project_id: str,
    confirmation_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除函证"""
    cid = uuid.UUID(confirmation_id)
    try:
        result = await confirmation_service.delete_confirmation(db, cid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.post("/{confirmation_id}/transition")
async def transition_confirmation(
    project_id: str,
    confirmation_id: str,
    body: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """状态推进"""
    cid = uuid.UUID(confirmation_id)
    try:
        result = await confirmation_service.transition_status(db, cid, body.target_status)
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    # 回函终态 → 发布 CONFIRMATION_RECEIVED，触发下游 stale 传播。
    # 源循环码优先用调用方显式传入的 wp_code（如前端 syncHub）；缺省时（G1：函证中心
    # 台账手动推进）从函证记录的 wp_id 反查 wp_code + 年度作兜底，使手动登记回函 / 确认
    # 相符不符也能传播下游 stale。仍反查不到 wp_code（无关联底稿）时不臆测源底稿。
    if body.target_status in ("returned", "matched", "discrepancy"):
        wp_code = body.wp_code
        year = body.year
        if not wp_code:
            try:
                derived_code, derived_year = (
                    await confirmation_service.derive_source_wp_code_and_year(db, cid)
                )
                wp_code = wp_code or derived_code
                if year is None:
                    year = derived_year
            except Exception:
                pass  # 反查失败不阻断
        if wp_code:
            try:
                await confirmation_service.apply_confirmation_result(
                    project_id=uuid.UUID(project_id),
                    year=year or 0,
                    confirmation_id=cid,
                    reply_status=body.target_status,
                    reply_amount=body.reply_amount,
                    wp_code=wp_code,
                    # #5: 传 db 原子回写 confirmed_amount/diff（避免 transition 与 update 竞态）
                    db=db if body.reply_amount is not None else None,
                )
            except Exception:
                pass  # 事件发布失败不阻断状态推进

    await db.commit()
    return result


# ─── M1 撤回端点（confirmation-attachment-ocr-linkage）──────────────────────


@router.post("/{confirmation_id}/reverse")
async def reverse_confirmation(
    project_id: str,
    confirmation_id: str,
    body: ReverseRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """撤回函证状态（反向回退，支持一步退到底至待发函）。

    权限：撤回终态（当前 matched/discrepancy）要求现场经理及以上；
    相邻非终态撤回允许编辑权。
    """
    cid = uuid.UUID(confirmation_id)

    # 先查当前状态判权限（终态撤回要求 manager+）
    current_record = await confirmation_service.get_confirmation(db, cid)
    current_status = current_record.get("status", "")
    if current_status in ("matched", "discrepancy"):
        # 终态撤回：现场经理及以上
        from app.deps import require_role
        require_role(user, ["admin", "partner", "signing_partner", "manager"])

    actor_id = getattr(user, "id", None)
    try:
        result = await confirmation_service.reverse_status(
            db, cid, body.target_status,
            reason=body.reason,
            actor_user_id=actor_id,
        )
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    await db.commit()
    return result


# ─── #4: 批量同步端点（减少前端 N+1 HTTP 请求） ────────────────────────────────


class BatchSyncItem(BaseModel):
    """单条函证同步请求"""
    confirm_type: str
    counterparty: str
    wp_id: str | None = None
    account_code: str | None = None
    book_amount: float | None = None
    confirmed_amount: float | None = None
    diff_amount: float | None = None
    diff_note: str | None = None
    target_status: str | None = Field(None, description="期望 Hub 目标状态")
    hub_confirmation_id: str | None = Field(None, description="已知 Hub ID（精确匹配）")


class BatchSyncRequest(BaseModel):
    items: list[BatchSyncItem] = Field(..., description="函证行列表")
    wp_id: str | None = Field(None, description="源底稿 ID（全局）")
    wp_code: str | None = Field(None, description="源循环码 D0/F0/G0…")
    year: int | None = Field(None, description="审计年度")


class BatchSyncResult(BaseModel):
    created: int = 0
    updated: int = 0
    transitioned: int = 0
    errors: list[str] = []
    hub_ids: dict[str, str] = Field(default_factory=dict, description="counterparty→hub_id 映射")


@router.post("/batch-sync")
async def batch_sync_confirmations(
    project_id: str,
    body: BatchSyncRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """批量同步函证（前端一次调用替代 N+1 逐行 create/update/transition）。

    逻辑：
    1. 按 hub_confirmation_id 精确匹配 → 按 counterparty+confirm_type 模糊匹配
    2. 不存在 → create；存在 → update 金额
    3. target_status 高于当前 → 逐步 transition（不回退）
    """
    pid = uuid.UUID(project_id)
    result = BatchSyncResult()

    # 预取所有 Hub 记录
    existing = await confirmation_service.list_confirmations(db, pid)
    hub_map_by_id: dict[str, dict] = {item["id"]: item for item in existing}
    hub_map_by_key: dict[str, dict] = {}
    for item in existing:
        key = f'{(item.get("counterparty") or "").strip().lower()}::{item.get("confirm_type") or ""}'
        hub_map_by_key[key] = item

    STATUS_RANK = {"pending": 0, "sent": 1, "returned": 2, "matched": 3, "discrepancy": 3}

    for item in body.items:
        name = (item.counterparty or "").strip()
        if not name:
            continue

        # 查找已有记录
        hub: dict | None = None
        if item.hub_confirmation_id:
            hub = hub_map_by_id.get(item.hub_confirmation_id)
        if not hub:
            key = f"{name.lower()}::{item.confirm_type}"
            hub = hub_map_by_key.get(key)

        try:
            if not hub:
                # Create
                data = {
                    "confirm_type": item.confirm_type,
                    "counterparty": name,
                    "wp_id": item.wp_id or body.wp_id or None,
                    "account_code": item.account_code or None,
                    "book_amount": item.book_amount,
                    "confirmed_amount": item.confirmed_amount,
                    "diff_amount": item.diff_amount,
                    "diff_note": item.diff_note or None,
                    "created_by": user.id if hasattr(user, "id") else None,
                }
                hub = await confirmation_service.create_confirmation(db, pid, data)
                result.created += 1
                # 注册到 map 供后续 dedup
                hub_map_by_id[hub["id"]] = hub
                key2 = f"{name.lower()}::{item.confirm_type}"
                hub_map_by_key[key2] = hub
            else:
                # Update 金额
                update_data: dict = {}
                if item.book_amount is not None:
                    update_data["book_amount"] = item.book_amount
                if item.confirmed_amount is not None:
                    update_data["confirmed_amount"] = item.confirmed_amount
                if item.diff_amount is not None:
                    update_data["diff_amount"] = item.diff_amount
                if item.wp_id or body.wp_id:
                    update_data["wp_id"] = item.wp_id or body.wp_id
                if item.account_code:
                    update_data["account_code"] = item.account_code
                if item.diff_note:
                    update_data["diff_note"] = item.diff_note
                if update_data:
                    hub = await confirmation_service.update_confirmation(
                        db, uuid.UUID(hub["id"]), update_data
                    )
                    result.updated += 1

            # Transition（仅正向推进）
            if item.target_status and hub:
                current = hub.get("status", "pending")
                target_rank = STATUS_RANK.get(item.target_status, -1)
                current_rank = STATUS_RANK.get(current, -1)
                if target_rank > current_rank:
                    # 构建推进路径
                    chain: list[str] = []
                    if item.target_status in ("matched", "discrepancy"):
                        chain = ["sent", "returned", item.target_status]
                    elif item.target_status == "returned":
                        chain = ["sent", "returned"]
                    elif item.target_status == "sent":
                        chain = ["sent"]

                    for step in chain:
                        step_rank = STATUS_RANK.get(step, -1)
                        if step_rank > STATUS_RANK.get(hub.get("status", "pending"), -1):
                            try:
                                hub = await confirmation_service.transition_status(
                                    db, uuid.UUID(hub["id"]), step
                                )
                                result.transitioned += 1
                            except ValueError:
                                break  # 状态机不允许

            # 记录映射
            if hub:
                result.hub_ids[name] = hub["id"] if isinstance(hub, dict) else str(hub.id)

        except Exception as e:
            result.errors.append(f"{name}: {str(e)}")

    # 终态行发 CONFIRMATION_RECEIVED（仅当有推进到终态）
    if result.transitioned > 0 and body.wp_code:
        try:
            year = body.year or 0
            # 用最后一个终态记录触发（一次事件即可，stale 按 wp_code 级传播）
            await confirmation_service.apply_confirmation_result(
                project_id=pid,
                year=year,
                confirmation_id=uuid.UUID(list(result.hub_ids.values())[-1]) if result.hub_ids else uuid.uuid4(),
                reply_status="batch_sync",
                reply_amount=None,
                wp_code=body.wp_code,
                db=None,  # 仅发事件
            )
        except Exception:
            pass

    await db.commit()
    return result.model_dump()
