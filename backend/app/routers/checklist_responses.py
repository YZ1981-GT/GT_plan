"""核对表填写响应 CRUD 端点

GET /api/workpapers/{wp_id}/checklist-responses — 获取已填写数据
PUT /api/workpapers/{wp_id}/checklist-responses — 批量保存（单次提交整章节）

章节适用性: 使用特殊 item_id 前缀 TOC-S01, TOC-S02 等存储章节级 applicable(Y/N)
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_wp_edit_permission
from app.models.core import User
from app.routers._wp_gate import enforce_wp_gate
from app.services.review_rbac_guard import check_rbac, check_sign_lock, extract_base_level

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers/{wp_id}/checklist-responses",
    tags=["checklist-responses"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ChecklistResponseItem(BaseModel):
    """单条核对表响应。if_match 缺省时保持兼容的 last-write-wins。"""
    item_id: str
    conclusion: Optional[str] = None  # 'Y'/'N'/'NA'/null
    remark: Optional[str] = None
    wp_ref: Optional[str] = None
    if_match: Optional[str] = None


class ChecklistResponseOut(BaseModel):
    """返回给前端的稳定响应，version 可用于下一次 if_match。"""
    id: uuid.UUID
    item_id: str
    conclusion: Optional[str] = None
    remark: Optional[str] = None
    wp_ref: Optional[str] = None
    updated_by: Optional[uuid.UUID] = None
    updated_at: Optional[str] = None
    version: Optional[str] = None
    overwritten: bool = False


class BatchSaveRequest(BaseModel):
    """批量保存请求体"""
    project_id: Optional[uuid.UUID] = None
    items: list[ChecklistResponseItem]


# ---------------------------------------------------------------------------
# GET — 获取该底稿所有填写数据
# ---------------------------------------------------------------------------


def _version_of(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _collection_etag(items: list[ChecklistResponseOut]) -> str:
    material = "\n".join(f"{item.item_id}:{item.version or ''}" for item in items)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f'W/"{digest}"'


@router.get("", response_model=list[ChecklistResponseOut])
async def get_checklist_responses(
    wp_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定底稿的所有核对表填写响应（含稳定版本和集合 ETag）。"""
    # Wp_Bound_Gate：读取任何 checklist 正文之前完成授权判定（Req 8.1/8.5）。
    # 无 project_id → gate 从 wp_id 反查资源真实 project（Binding_Minimum）。
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.checklist_read", action="read_checklist", method="GET",
        wp_id=wp_id, entry_family="checklist",
        route_name="/api/workpapers/{wp_id}/checklist-responses",
    )
    result = await db.execute(
        text("""
            SELECT id, item_id, conclusion, remark, wp_ref, updated_by, updated_at
            FROM checklist_responses
            WHERE wp_id = :wp_id
            ORDER BY item_id
        """),
        {"wp_id": str(wp_id)},
    )
    rows = result.fetchall()
    items = [
        ChecklistResponseOut(
            id=row.id,
            item_id=row.item_id,
            conclusion=row.conclusion,
            remark=row.remark,
            wp_ref=row.wp_ref,
            updated_by=row.updated_by,
            updated_at=_version_of(row.updated_at),
            version=_version_of(row.updated_at),
        )
        for row in rows
    ]
    response.headers["ETag"] = _collection_etag(items)
    return items


# ---------------------------------------------------------------------------
# PUT — 批量保存（UPSERT 整章节）
# ---------------------------------------------------------------------------


@router.put("", response_model=list[ChecklistResponseOut])
async def batch_save_checklist_responses(
    wp_id: uuid.UUID,
    body: BatchSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_wp_edit_permission()),
):
    """原子批量 UPSERT；可选 if_match 冲突保护，缺省保持 LWW 兼容。"""
    import time as _time
    from app.services.wp_metrics import wp_metrics

    if not body.items:
        return []

    _save_t0 = _time.perf_counter()
    _save_status = "success"

    # Wp_Bound_Gate：产生任何持久化副作用之前完成授权判定（Req 8.1/8.5）。
    # save_checklist 为内容写；assignee 仅在被委派 sheet 上允许、reviewer 禁止通用 checklist 写、
    # History_Only 写入统一 404（矩阵与 grant 已保证）。无 project_id → gate 反查。
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.checklist_save", action="save_checklist", method="PUT",
        wp_id=wp_id, project_id=body.project_id, entry_family="checklist",
        route_name="/api/workpapers/{wp_id}/checklist-responses",
    )

    context_result = await db.execute(
        text("""
            SELECT wp.project_id, wi.wp_code, p.audit_year
            FROM working_paper wp
            LEFT JOIN wp_index wi ON wi.id = wp.wp_index_id
            LEFT JOIN projects p ON p.id = wp.project_id
            WHERE wp.id = :wp_id
            LIMIT 1
        """),
        {"wp_id": str(wp_id)},
    )
    context = context_result.fetchone()
    if context is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    resolved_project_id = context.project_id
    if body.project_id and str(body.project_id) != str(resolved_project_id):
        raise HTTPException(status_code=422, detail={
            "code": "project_mismatch",
            "message": "project_id 与目标底稿所属项目不一致",
            "atomic": True,
        })

    duplicate_ids = sorted({
        item.item_id for item in body.items
        if sum(candidate.item_id == item.item_id for candidate in body.items) > 1
    })
    if duplicate_ids:
        raise HTTPException(status_code=422, detail={
            "code": "duplicate_item",
            "item_id": duplicate_ids[0],
            "message": "同一批次不得重复提交相同 item_id",
            "atomic": True,
        })

    # 复核表继续叠加既有专项 RBAC/签字锁；通用编辑权已由依赖统一校验。
    wp_code_val = context.wp_code
    if wp_code_val and extract_base_level(wp_code_val):
        rbac_denied = await check_rbac(db, current_user.id, resolved_project_id, wp_code_val)
        if rbac_denied:
            raise HTTPException(status_code=403, detail="无权编辑此级别复核表")
        locked, _, _ = await check_sign_lock(db, resolved_project_id, wp_code_val)
        if locked:
            raise HTTPException(status_code=403, detail="复核表已锁定")

    try:
        existing_versions = await _lock_and_check_versions(db, wp_id, body.items)
        results = await _do_batch_save(
            db,
            wp_id,
            body,
            current_user,
            datetime.now(timezone.utc),
            resolved_project_id,
            existing_versions,
        )
        await db.commit()
    except HTTPException as exc:
        await db.rollback()
        _save_status = "conflict" if exc.status_code == 409 else "error"
        _elapsed_ms = (_time.perf_counter() - _save_t0) * 1000
        wp_metrics.observe_save(_elapsed_ms, status=_save_status)
        if not isinstance(exc.detail, dict):
            exc.detail = {
                "code": "invalid_item" if exc.status_code == 422 else "save_failed",
                "item_id": _infer_error_item_id(body.items, str(exc.detail)),
                "message": str(exc.detail),
                "atomic": True,
            }
        raise
    except Exception as exc:
        await db.rollback()
        _save_status = "error"
        _elapsed_ms = (_time.perf_counter() - _save_t0) * 1000
        wp_metrics.observe_save(_elapsed_ms, status=_save_status)
        logger.error(
            "checklist_responses batch_save 未预期异常: wp_id=%s error=%s",
            wp_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={
            "code": "save_failed",
            "message": f"保存异常: {type(exc).__name__}",
            "atomic": True,
        }) from exc

    # 成功路径：记录指标
    _elapsed_ms = (_time.perf_counter() - _save_t0) * 1000
    wp_metrics.observe_save(_elapsed_ms, status="success")

    await _publish_checklist_saved(
        project_id=resolved_project_id,
        wp_id=wp_id,
        wp_code=wp_code_val,
        year=context.audit_year,
        item_ids=[item.item_id for item in body.items],
    )
    return results


def _infer_error_item_id(items: list[ChecklistResponseItem], detail: str) -> str | None:
    for item in items:
        if item.conclusion is not None and repr(item.conclusion) in detail:
            return item.item_id
    return items[0].item_id if items else None


async def _lock_and_check_versions(
    db: AsyncSession,
    wp_id: uuid.UUID,
    items: list[ChecklistResponseItem],
) -> dict[str, str]:
    """按稳定顺序锁定现存行，并在任何写入前完成整批冲突预检。"""
    existing: dict[str, str] = {}
    for item_id in sorted(item.item_id for item in items):
        row = (
            await db.execute(
                text("""
                    SELECT updated_at
                    FROM checklist_responses
                    WHERE wp_id = :wp_id AND item_id = :item_id
                    FOR UPDATE
                """),
                {"wp_id": str(wp_id), "item_id": item_id},
            )
        ).fetchone()
        if row and row.updated_at:
            existing[item_id] = _version_of(row.updated_at) or ""

    for item in items:
        if item.if_match is None:
            continue
        server_version = existing.get(item.item_id)
        if item.if_match != server_version:
            raise HTTPException(status_code=409, detail={
                "code": "version_conflict",
                "item_id": item.item_id,
                "client_version": item.if_match,
                "server_version": server_version,
                "message": "底稿条目已被其他客户端修改",
                "atomic": True,
            })
    return existing


async def _publish_checklist_saved(
    *,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    wp_code: str | None,
    year: int | None,
    item_ids: list[str],
) -> None:
    """提交成功后接入既有 WORKPAPER_SAVED；失败不回滚已提交数据。"""
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        await event_bus.publish(EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=project_id,
            year=year,
            extra={
                "wp_id": str(wp_id),
                "wp_code": wp_code,
                "trigger": "checklist_response_save",
                "item_ids": item_ids,
                "atomic": True,
            },
        ))
    except Exception as exc:  # 事件是提交后副作用，不得反向破坏持久化
        logger.warning(
            "checklist save event publish failed wp=%s items=%d: %s",
            wp_id,
            len(item_ids),
            exc,
        )


async def _do_batch_save(
    db,
    wp_id,
    body,
    current_user,
    now,
    resolved_project_id,
    existing_versions: dict[str, str],
):
    """实际执行批量保存；只写/flush，不 commit，由路由统一控制原子事务。"""

    # UPSERT: INSERT ... ON CONFLICT (wp_id, item_id) DO UPDATE
    upsert_sql = text("""
        INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, wp_ref, updated_by, created_at, updated_at)
        VALUES (:project_id, :wp_id, :item_id, :conclusion, :remark, :wp_ref, :updated_by, :now, :now)
        ON CONFLICT (wp_id, item_id) DO UPDATE SET
            conclusion = EXCLUDED.conclusion,
            remark = EXCLUDED.remark,
            wp_ref = EXCLUDED.wp_ref,
            updated_by = EXCLUDED.updated_by,
            updated_at = EXCLUDED.updated_at
        RETURNING id, item_id, conclusion, remark, wp_ref, updated_by, updated_at
    """)

    results = []
    for item in body.items:
        # Validate conclusion value
        if item.conclusion is not None:
            # TOC-前缀 = 章节适用性，用 Y/N
            if item.item_id.startswith("TOC-"):
                if item.conclusion not in ("Y", "N"):
                    raise HTTPException(
                        status_code=422,
                        detail=f"章节适用性 conclusion 值必须为 'Y'/'N' 或 null，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("A1-11-"):
                # A1-11 签发流转控制表：签字Y, 首次承接Y/N, 不适用NA, 业务分类A/B/C
                allowed = ("Y", "N", "NA", "A", "B", "C")
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"A1-11 conclusion 值必须为 Y/N/NA/A/B/C 或 null，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("B50-"):
                allowed = (
                    "H", "M", "L",
                    "Y", "N", "NA",
                    "B22A", "B23", "industry", "discussion",
                    "prior_audit", "management_interview", "other",
                    "control_env", "management_integrity",
                    "economic_env", "industry_factor",
                )
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"B50 conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("B22A-"):
                allowed = (
                    "设计有效", "设计无效", "已实施", "未实施", "不适用",
                    "Y", "N", "NA",
                    "有效", "部分有效", "无效",
                    "高", "中", "低",
                )
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"B22A conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("B22B-"):
                allowed = (
                    "重大缺陷", "重要缺陷", "一般缺陷",
                    "设计缺陷", "运行缺陷",
                    "Y", "N",
                    "存在重大缺陷", "存在重要缺陷", "仅存在一般缺陷", "未发现控制缺陷",
                )
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"B22B conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("B23-"):
                # B23 业务流程控制：流程结论 + 穿行测试结论 + 控制频率 + 签字/适用性标记
                allowed = (
                    "设计有效且已实施", "设计有效但未有效实施", "设计无效", "不适用",
                    "控制有效运行", "控制未有效运行", "未执行穿行",
                    "每笔", "每日", "每周", "每月", "每季", "每年", "不定期",
                    "Y", "N",
                )
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"B23 conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("B30-"):
                # B30 集团审计范围确定：分类 + 范围类型 + 组成部分类型 + 独立性 + 胜任能力 + 签字标记
                allowed = (
                    "重要组成部分", "非重要组成部分", "不重要组成部分",
                    "全面审计", "特定项目审计", "分析性程序", "不执行程序",
                    "子公司", "分公司", "合营企业", "联营企业", "分部",
                    "已确认", "未确认", "不适用",
                    "充分", "需补充", "不充分",
                    "Y", "N",
                )
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"B30 conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("a171-"):
                # A17-1 重大事项概要汇总：签字=任意字符串(姓名/日期)，章节=null(存remark)
                pass  # no validation — conclusion is freeform (name/date for signature, null for chapters)
            elif any(item.item_id.startswith(p) for p in (
                "a101-", "a121-", "a1721-", "a271-", "a91-", "a92-",
                "a117-", "a176-", "a181-", "a182-", "a81-", "a111-",
                "a173-", "a1731-", "a174-", "a177-", "a51-",
                "b14-", "wt-",
            )):
                # 专属组件自由格式：签字/日期/长文本均存 conclusion，跳过白名单校验
                pass
            elif item.item_id.startswith("C1-"):
                # C1 企业层面控制测试：适用性 Y/N + 段/整体结论 + 测试方法 + 控制频率 + 段裁剪
                allowed = (
                    "Y", "N", "NA",
                    "有效", "部分有效", "无效",
                    "控制有效运行", "控制存在偏差但可接受", "控制无效",
                    "询问", "观察", "检查", "重新执行", "抽样", "询问和观察",
                    "每笔", "每日", "每周", "每月", "每季", "每年",
                    "每月一次", "每季一次", "每年一次", "根据需要", "不定期",
                    "已执行", "尚未执行",
                )
                if item.conclusion and item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"C1 企业层面控制 conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif any(item.item_id.startswith(f"C{n}-") for n in range(2, 16)):
                # C2~C15 控制测试：控制点结论 + 样本结果 + 循环结论 + 测试方法 + 偏差性质 + 决策树 + 签字标记
                allowed = (
                    "控制有效运行", "控制存在偏差但可接受", "控制无效",
                    "控制有效", "构成控制缺陷",
                    "有效", "偏差", "不适用",
                    "全部有效", "部分偏差", "控制失效",
                    "询问", "观察", "检查", "重新执行",
                    "系统性偏差", "人为偏差", "随机性偏差",
                    "扩大样本量", "直接认定为偏差",
                    "是", "否",
                    "Y", "N",
                )
                if item.conclusion and item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"C控制测试 conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith(("C23A-", "C23-", "C24A-", "C24-", "C25-", "C26-", "C22.")):
                # C23~C26 专属组件：自由格式（步骤结论/分析文本/类别/要素/人员等均存 conclusion）
                # 数据模式多样（freeform text / comma-separated / null），跳过白名单校验
                pass
            elif item.item_id.startswith(("K6-", "K6A-")):
                # K6 持有待售资产和负债：自由格式（审定数/减值/分类结论等均存 remark，conclusion 偶有 Y/N/分类状态）
                pass
            elif item.item_id.startswith("G5-"):
                # G5 长期应收款：审计说明/审计结论等自由格式（remark 存文本，conclusion 恒为 null）
                pass
            elif item.item_id.startswith("G8-"):
                # G8 其他权益工具投资：审计说明/审计结论/明细行/审定数等自由格式
                # （remark 存文本或 JSON，conclusion 恒为 null 或审定数字符串），跳过白名单校验
                pass
            elif item.item_id.startswith(("G10-", "G10-adj")):
                # G10 交易性金融负债：审计说明/审计结论/明细行/审定数/分类/衍生等自由格式
                # （审定表 composable 将说明/结论/审定数存入 conclusion 字段[item_id 如
                #  G10-adj-note/G10-adj-conclusion/G10-1-adjudicated-amount]，其余存 remark，
                #  conclusion 为自由文本或审定数字符串），跳过白名单校验
                pass
            elif item.item_id.startswith("G11-"):
                # G11 投资收益：审计说明/审计结论/明细行/审定数/收益率/凭证检查等自由格式
                # （remark 存文本或 JSON，审计说明/结论 conclusion 恒为 null，审定数 composable
                #  可能存审定数/文本字符串到 conclusion），跳过白名单校验
                pass
            elif item.item_id.startswith("G12-"):
                # G12 净敞口套期收益：审计说明/审计结论/明细行/审定数等自由格式
                # （remark 存文本或 JSON，conclusion 恒为 null 或审定数/文本字符串），跳过白名单校验
                pass
            elif item.item_id.startswith("G13-"):
                # G13 公允价值变动损益：审计说明/审计结论/明细行/审定数/披露等自由格式
                # （remark 存文本或 JSON，审计说明/结论 conclusion 恒为 null 或自由文本，审定表
                #  composable 将说明/结论/审定数存入 conclusion 字段[如 G13-adj-note/
                #  G13-adj-conclusion/G13-1-adjudicated-amount]），跳过白名单校验
                pass
            elif item.item_id.startswith("G14-"):
                # G14 信用减值损失：审计说明/审计结论/明细行/审定数等自由格式
                # （审定表 composable 将说明/结论/审定数存入 conclusion 字段[如 G14-adj-note/
                #  G14-adj-conclusion/G14-1-adjudicated-amount]；逐 sheet 打磨的审计说明/结论
                #  存 remark、conclusion 恒为 null），跳过白名单校验
                pass
            elif item.item_id.startswith("D1-"):
                # D1 应收票据：程序表状态 + 业务模式 + 终止确认 + 披露结论 + 检查结论 + ECL方法 + 标记
                allowed = (
                    "未开始", "执行中", "已完成", "不适用",
                    "符合", "不符合",
                    "以摊余成本计量", "以公允价值计量且变动计入其他综合收益",
                    "以公允价值计量且变动计入当期损益",
                    "终止确认", "不终止确认",
                    "已披露且准确", "已披露但需修改", "未披露需补充",
                    "组合评估", "个别认定",
                    "AJE", "RJE",
                    "listed", "soe", "general",
                    "Y", "N", "是", "否",
                    "合理", "基本合理但需关注", "不合理",
                )
                if item.conclusion and item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"D1 应收票据 conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith("D2-"):
                # D2 应收账款：程序表状态 + 坏账方式 + 终止确认 + 披露结论 + 检查结论 + 标记
                allowed = (
                    "未开始", "执行中", "已完成", "不适用",
                    "符合", "不符合",
                    "单项计提", "账龄组合", "客户类型组合",
                    "终止确认", "不终止确认",
                    "已披露且准确", "已披露但需修改", "未披露需补充",
                    "组合评估", "个别认定",
                    "AJE", "RJE",
                    "Y", "N", "是", "否",
                    "跨期", "未跨期",
                )
                if item.conclusion and item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"D2 应收账款 conclusion 值无效，收到: '{item.conclusion}'",
                    )
            elif item.item_id.startswith(("S12-", "S13-", "S14-", "S15-", "S20-", "S21-")):
                # S12/S13/S14/S15/S20/S21 专项底稿子表：自由格式（评价行/明细行/结论
                # JSON 打包进 remark，conclusion 通常为 null；偶有评价结果字符串），
                # 跳过白名单校验
                pass
            elif item.item_id.startswith((
                "L1-", "L2-", "L3-", "L4-", "L5-", "L6-", "L7-", "L8-",
                "M1-", "M2-", "M3-", "M4-", "M5-", "M6-", "M7-", "M8-", "M9-", "M10-",
                "N1-", "N2-", "N3-", "N4-", "N5-",
            )):
                # L 筹资/负债循环（短期借款/应付利息/长期借款/应付债券/长期应付款/专项应付款/
                # 其他非流动负债/财务费用）、M 权益循环（应付股利/实收资本/库存股/资本公积/盈余
                # 公积/未分配利润/专项储备/一般风险准备/其他综合收益/其他权益工具）、N 税金循环
                # （递延所得税资产/应交税费/递延所得税负债/税金及附加/所得税费用）专属组件：
                # 审定数/明细行/测算表/审计说明/审计结论/检查项等均以自由文本或 JSON 存入
                # conclusion 或 remark，跳过白名单校验（与 G/K/S 循环同范式）。
                pass
            else:
                allowed = ("Y", "N", "X/I", "X/W", "N/A")
                if item.item_id.endswith("-sign-status"):
                    allowed = ("pending", "sent", "signed")
                elif item.item_id.startswith(("A17-1-ch", "A18-2")):
                    allowed = ("Y", "N", "done", "pending")
                elif item.item_id.endswith("-sign") and item.item_id.startswith(("A21-", "A22-", "A23-", "A24-", "A25-")):
                    allowed = ("pass", "reject")
                elif item.item_id.endswith("-record") and item.item_id.startswith(("A21-", "A22-", "A23-", "A24-", "A25-")):
                    allowed = ("done",)
                elif "-chk-" in item.item_id and item.item_id.startswith(("A21-", "A22-", "A23-", "A24-", "A25-")):
                    allowed = ("Y", "N", "NA")
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"conclusion 值无效，收到: '{item.conclusion}'",
                    )

        try:
            row = await db.execute(
                upsert_sql,
                {
                    "project_id": str(resolved_project_id),
                    "wp_id": str(wp_id),
                    "item_id": item.item_id,
                    "conclusion": item.conclusion,
                    "remark": item.remark,
                    "wp_ref": item.wp_ref,
                    "updated_by": str(current_user.id),
                    "now": now,
                },
            )
        except Exception as e:
            logger.error(
                "checklist_responses UPSERT 失败 wp_id=%s item_id=%s: %s",
                wp_id, item.item_id, e,
            )
            raise HTTPException(status_code=500, detail=f"保存失败: {item.item_id}: {str(e)[:200]}")
        r = row.fetchone()
        version = _version_of(r.updated_at)
        results.append(
            ChecklistResponseOut(
                id=r.id,
                item_id=r.item_id,
                conclusion=r.conclusion,
                remark=r.remark,
                wp_ref=r.wp_ref,
                updated_by=r.updated_by,
                updated_at=version,
                version=version,
                overwritten=(
                    item.if_match is None and item.item_id in existing_versions
                ),
            )
        )

    await db.flush()
    return results
