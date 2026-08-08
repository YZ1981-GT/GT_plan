"""归档前完整性自检报告服务

Requirements: 3.2, 3.3, 3.4, 3.5

四类检查：
1. missing — 缺失底稿（WpIndex 有记录但无对应 WorkingPaper）
2. unsigned — 未签字底稿（status 非 review_passed / archived）
3. unresolved_reviews — 有未解决复核意见
4. stale — 数据过期底稿（prefill_stale=true）

每类计算 count + items 列表 + is_blocking 标记。
can_proceed = True 当且仅当无 blocking 类别有 count > 0。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.staff_models import StaffMember
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WpIndex,
    WorkingPaper,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers: 底稿编号自然排序 + 责任人中文名解析
# ---------------------------------------------------------------------------

_WP_CODE_RE = re.compile(r"^([A-Za-z]+)(\d+)")


def _wp_sort_key(wp_code: str) -> tuple:
    """底稿编号自然排序键：先按字母前缀（A-T），再按数字升序，避免
    字符串排序把 A10 排在 A2 之前、或 A22→A5 跳号乱序。

    形如 ``A1`` → ('A', 1, 'A1')；带后缀 ``D2-1`` → ('D', 2, 'D2-1')；
    无法解析的自定义编号（如 ``PWXD6AS9``）排到最后（前缀置 '~'）。
    """
    m = _WP_CODE_RE.match(wp_code or "")
    if not m:
        return ("~", 0, wp_code or "")
    return (m.group(1).upper(), int(m.group(2)), wp_code)


async def _resolve_assignee_names(
    db: AsyncSession, items: list["CheckItem"]
) -> None:
    """把 items 里的 assignee（users.id 字符串）就地替换为中文姓名。

    优先取 staff_members.name（与 user 关联），降级用 users.username。
    无法解析的保持原值（或 None）。
    """
    raw_ids: set[str] = {
        it.assignee for it in items if it.assignee
    }
    if not raw_ids:
        return

    user_uuids: list[UUID] = []
    for rid in raw_ids:
        try:
            user_uuids.append(UUID(rid))
        except (ValueError, AttributeError):
            continue
    if not user_uuids:
        return

    # staff_members.name 优先
    staff_rows = await db.execute(
        select(StaffMember.user_id, StaffMember.name).where(
            StaffMember.user_id.in_(user_uuids),
            StaffMember.is_deleted == False,  # noqa: E712
        )
    )
    name_map: dict[str, str] = {
        str(uid): name for uid, name in staff_rows.all() if uid
    }

    # 补齐 staff 缺失的：用 users.username 降级
    missing = [u for u in user_uuids if str(u) not in name_map]
    if missing:
        user_rows = await db.execute(
            select(User.id, User.username).where(User.id.in_(missing))
        )
        for uid, uname in user_rows.all():
            name_map[str(uid)] = uname

    for it in items:
        if it.assignee and it.assignee in name_map:
            it.assignee = name_map[it.assignee]


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class CheckItem(BaseModel):
    wp_code: str
    wp_name: str
    assignee: str | None
    status: str


class CheckCategory(BaseModel):
    category: Literal[
        "missing",
        "unsigned",
        "unresolved_reviews",
        "stale",
        # 抽样记录不完整（sampling-evaluation-and-governance-closure R8.4）。
        # 非阻断，理由见 get_archive_completeness_report 内注释。
        "sampling_records",
    ]
    count: int
    items: list[CheckItem]
    is_blocking: bool


class CompletenessReportResponse(BaseModel):
    categories: list[CheckCategory]  # 固定 5 类
    can_proceed: bool  # 无 blocking 项时 True
    generated_at: datetime


# ---------------------------------------------------------------------------
# Blocking rules
# ---------------------------------------------------------------------------

# missing 和 unsigned 是 blocking（阻断归档）
# unresolved_reviews 和 stale 是 blocking（阻断归档）
BLOCKING_CATEGORIES: set[str] = {"missing", "unsigned", "unresolved_reviews", "stale"}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


async def get_archive_completeness_report(
    db: AsyncSession,
    project_id: UUID,
) -> CompletenessReportResponse:
    """生成归档前完整性自检报告。

    Returns 4 categories with counts, items, and blocking flags.
    can_proceed is True only if no blocking category has count > 0.
    """

    # --- 1. 缺失底稿：WpIndex 有记录但无对应 WorkingPaper ---
    missing_items = await _check_missing(db, project_id)

    # --- 2. 未签字底稿：status 非 review_passed / archived ---
    unsigned_items = await _check_unsigned(db, project_id)

    # --- 3. 未解决复核意见 ---
    unresolved_items = await _check_unresolved_reviews(db, project_id)

    # --- 4. Stale 底稿 ---
    stale_items = await _check_stale(db, project_id)

    # --- 5. 抽样记录不完整（sampling-evaluation-and-governance-closure R8.4）---
    sampling_items = await _check_sampling_records(db, project_id)

    # 底稿编号自然排序（A1→A2→...→A10，按字母前缀+数字，不跳号）
    for _items in (missing_items, unsigned_items, unresolved_items, stale_items):
        _items.sort(key=lambda it: _wp_sort_key(it.wp_code))

    # 责任人 UUID → 中文姓名（staff_members.name 优先，降级 users.username）
    await _resolve_assignee_names(
        db,
        [*missing_items, *unsigned_items, *unresolved_items, *stale_items, *sampling_items],
    )

    # Build categories
    categories = [
        CheckCategory(
            category="missing",
            count=len(missing_items),
            items=missing_items,
            is_blocking=True,
        ),
        CheckCategory(
            category="unsigned",
            count=len(unsigned_items),
            items=unsigned_items,
            is_blocking=True,
        ),
        CheckCategory(
            category="unresolved_reviews",
            count=len(unresolved_items),
            items=unresolved_items,
            is_blocking=True,
        ),
        CheckCategory(
            category="stale",
            count=len(stale_items),
            items=stale_items,
            is_blocking=True,
        ),
        # 抽样记录不完整：**非阻断**。
        # 理由：抽样记录的补齐是审计判断（补评价、确认结论、复核过期抽样框），
        # 与「底稿缺失/未签字」这类客观状态不同；把它设成阻断会在存量项目上
        # 立刻卡住全部归档（真实库已有批次缺评价）。先报出、由项目组处置。
        CheckCategory(
            category="sampling_records",
            count=len(sampling_items),
            items=sampling_items,
            is_blocking=False,
        ),
    ]

    # can_proceed: True iff no blocking category has count > 0
    can_proceed = all(
        not (cat.is_blocking and cat.count > 0) for cat in categories
    )

    return CompletenessReportResponse(
        categories=categories,
        can_proceed=can_proceed,
        generated_at=datetime.now(timezone.utc),
    )


async def _check_missing(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """缺失底稿：WpIndex 有记录但无对应 WorkingPaper（或已删除）。"""
    # Subquery: wp_index_ids that have a non-deleted WorkingPaper
    existing_wp_subq = (
        select(WorkingPaper.wp_index_id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
        .scalar_subquery()
    )

    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WpIndex.assigned_to,
        )
        .where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == False,  # noqa: E712
            WpIndex.id.notin_(
                select(WorkingPaper.wp_index_id).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == False,  # noqa: E712
                )
            ),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status="missing",
        )
        for row in rows
    ]


async def _check_unsigned(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """未签字底稿：status 非 review_passed / archived。"""
    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WorkingPaper.assigned_to,
            WorkingPaper.status,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.status.notin_(["review_passed", "archived"]),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status=row[3].value if hasattr(row[3], "value") else str(row[3]),
        )
        for row in rows
    ]


async def _check_unresolved_reviews(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """有未解决复核意见的底稿。"""
    # Find working papers with open review comments
    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WorkingPaper.assigned_to,
            WorkingPaper.status,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.id.in_(
                select(ReviewRecord.working_paper_id)
                .where(
                    ReviewRecord.status == ReviewCommentStatus.open,
                    ReviewRecord.is_deleted == False,  # noqa: E712
                )
                .distinct()
            ),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status="unresolved_reviews",
        )
        for row in rows
    ]


async def _check_stale(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """Stale 底稿：prefill_stale=true。"""
    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WorkingPaper.assigned_to,
            WorkingPaper.status,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.prefill_stale == True,  # noqa: E712
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status="stale",
        )
        for row in rows
    ]


async def _check_sampling_records(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """抽样记录不完整的底稿（sampling-evaluation-and-governance-closure R8.4）。

    判据**复用** `sampling_qc_rules.evaluate_sampling_completeness` —— 与 QC-12 同一函数，
    避免两处各写一套导致「QC 说不合规、归档说完整」这种结论打架。

    读的是权威留痕 `workpaper_extraction_log.extraction_criteria`（未撤销的
    `voucher_sampling` 批次），而非投影表 —— 投影可能因 fail-open 未写入，
    归档闸门不该因投影缺失而放行。

    fail-open：查询异常时返回空清单 + WARNING，不阻断归档报告生成
    （本类别本身非阻断，缺它不会误放行阻断项）。
    """
    try:
        from app.models.audit_platform_models import WorkpaperExtractionLog
        from app.models.workpaper_models import WorkingPaper, WpIndex
        from app.services.sampling_qc_rules import (
            SamplingBatchView,
            evaluate_sampling_completeness,
        )

        rows = (
            await db.execute(
                select(
                    WorkpaperExtractionLog.workpaper_id,
                    WorkpaperExtractionLog.batch_id,
                    WorkpaperExtractionLog.extraction_criteria,
                    WpIndex.wp_code,
                    WpIndex.wp_name,
                )
                .select_from(WorkpaperExtractionLog)
                .join(
                    WorkingPaper,
                    WorkingPaper.id == WorkpaperExtractionLog.workpaper_id,
                    isouter=True,
                )
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id, isouter=True)
                .where(
                    WorkpaperExtractionLog.project_id == project_id,
                    WorkpaperExtractionLog.extraction_type == "voucher_sampling",
                    WorkpaperExtractionLog.is_undone.is_(False),
                )
            )
        ).all()
    except Exception:  # noqa: BLE001 — 非阻断类别，查询失败不影响归档报告
        logger.warning(
            "抽样记录完整性检查失败，本次归档报告不含该类别 project=%s",
            project_id,
            exc_info=True,
        )
        return []

    items: list[CheckItem] = []
    for wp_id, batch_id, criteria, wp_code, wp_name in rows:
        view = SamplingBatchView(
            batch_id=str(batch_id) if batch_id else None,
            criteria=criteria if isinstance(criteria, dict) else {},
            # dataset_stale 需要当前 active dataset，归档报告不做该判定
            # （QC-12 已覆盖，此处重复查询会让归档报告变慢且结论可能不一致）
            dataset_stale=False,
            wp_code=wp_code,
        )
        for msg in evaluate_sampling_completeness([view]):
            items.append(
                CheckItem(
                    wp_code=wp_code or str(wp_id)[:8],
                    wp_name=wp_name or "底稿名称未知",
                    assignee=None,
                    status=msg,
                )
            )
    return items
