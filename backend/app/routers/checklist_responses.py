"""核对表填写响应 CRUD 端点

GET /api/workpapers/{wp_id}/checklist-responses — 获取已填写数据
PUT /api/workpapers/{wp_id}/checklist-responses — 批量保存（单次提交整章节）

章节适用性: 使用特殊 item_id 前缀 TOC-S01, TOC-S02 等存储章节级 applicable(Y/N)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
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
    """单条核对表响应"""
    item_id: str
    conclusion: Optional[str] = None  # 'Y'/'N'/'NA'/null
    remark: Optional[str] = None
    wp_ref: Optional[str] = None


class ChecklistResponseOut(BaseModel):
    """返回给前端的响应"""
    id: uuid.UUID
    item_id: str
    conclusion: Optional[str] = None
    remark: Optional[str] = None
    wp_ref: Optional[str] = None
    updated_by: Optional[uuid.UUID] = None
    updated_at: Optional[str] = None


class BatchSaveRequest(BaseModel):
    """批量保存请求体"""
    project_id: Optional[uuid.UUID] = None
    items: list[ChecklistResponseItem]


# ---------------------------------------------------------------------------
# GET — 获取该底稿所有填写数据
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ChecklistResponseOut])
async def get_checklist_responses(
    wp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定底稿的所有核对表填写响应（含章节适用性）"""
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
    return [
        ChecklistResponseOut(
            id=row.id,
            item_id=row.item_id,
            conclusion=row.conclusion,
            remark=row.remark,
            wp_ref=row.wp_ref,
            updated_by=row.updated_by,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# PUT — 批量保存（UPSERT 整章节）
# ---------------------------------------------------------------------------


@router.put("", response_model=list[ChecklistResponseOut])
async def batch_save_checklist_responses(
    wp_id: uuid.UUID,
    body: BatchSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量保存核对表填写数据（UPSERT by wp_id + item_id）

    支持条目级填写和章节适用性（item_id 前缀 TOC-S01 等）。
    """
    if not body.items:
        return []

    # --- 自动解析 project_id（如果前端未传） ---
    resolved_project_id = body.project_id
    if not resolved_project_id:
        pid_row = await db.execute(
            text("SELECT project_id FROM working_paper WHERE id = :wp_id LIMIT 1"),
            {"wp_id": str(wp_id)},
        )
        pid_val = pid_row.scalar_one_or_none()
        if pid_val:
            resolved_project_id = pid_val
        else:
            raise HTTPException(status_code=400, detail="无法确定 project_id，请确认底稿存在")

    # --- Review-checklist RBAC + Sign-Lock 前置校验 ---
    # 从 wp_index 获取 wp_code，判断是否为复核表
    wp_code_row = await db.execute(
        text("""
            SELECT wi.wp_code FROM wp_index wi
            JOIN working_paper wp ON wp.wp_index_id = wi.id
            WHERE wp.id = :wp_id
            LIMIT 1
        """),
        {"wp_id": str(wp_id)},
    )
    wp_code_val = wp_code_row.scalar_one_or_none()

    if wp_code_val and extract_base_level(wp_code_val):
        # 是 A2[1-5] 复核表 → 执行 guard
        rbac_denied = await check_rbac(db, current_user.id, resolved_project_id, wp_code_val)
        if rbac_denied:
            raise HTTPException(status_code=403, detail="无权编辑此级别复核表")

        locked, _, _ = await check_sign_lock(db, resolved_project_id, wp_code_val)
        if locked:
            raise HTTPException(status_code=403, detail="复核表已锁定")

    now = datetime.now(timezone.utc)

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

    try:
        results = await _do_batch_save(db, wp_id, body, current_user, upsert_sql, now, resolved_project_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("checklist_responses batch_save 未预期异常: wp_id=%s error=%s", wp_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存异常: {type(e).__name__}: {str(e)[:200]}")

    await db.commit()
    return results


async def _do_batch_save(db, wp_id, body, current_user, upsert_sql, now, resolved_project_id):
    """实际执行批量保存逻辑（从主函数抽出以支持全局 try/except）。"""

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
            else:
                allowed = ("Y", "X/I", "X/W", "N/A")
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
        results.append(
            ChecklistResponseOut(
                id=r.id,
                item_id=r.item_id,
                conclusion=r.conclusion,
                remark=r.remark,
                wp_ref=r.wp_ref,
                updated_by=r.updated_by,
                updated_at=r.updated_at.isoformat() if r.updated_at else None,
            )
        )

    await db.commit()
    return results
