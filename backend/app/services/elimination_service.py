"""抵消分录服务 — 异步 ORM"""

from decimal import Decimal
from uuid import UUID
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum
from app.models.consolidation_schemas import (
    EliminationCreate,
    EliminationEntryResponse,
    EliminationEntryLine,
    EliminationEntryUpdate,
    EliminationReviewAction,
    EliminationSummary,
)


async def _generate_entry_no(db: AsyncSession, project_id: UUID, year: int, entry_type: EliminationEntryType) -> str:
    """生成抵消分录编号 CE-001 格式"""
    prefix_map = {
        EliminationEntryType.equity: "EQ",
        EliminationEntryType.internal_trade: "IT",
        EliminationEntryType.internal_ar_ap: "IA",
        EliminationEntryType.unrealized_profit: "UP",
        EliminationEntryType.other: "OT",
    }
    prefix = prefix_map.get(entry_type, "CE")
    suffix = f"{year}"
    pattern = f"{prefix}-{suffix}-%"

    result = await db.execute(
        sa.select(func.max(EliminationEntry.entry_no)).where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.entry_no.like(pattern),
            EliminationEntry.is_deleted.is_(False),
        )
    )
    max_no = result.scalar()
    if max_no:
        try:
            last_seq = int(max_no.split("-")[-1])
            new_seq = last_seq + 1
        except (ValueError, IndexError):
            new_seq = 1
    else:
        new_seq = 1
    return f"{prefix}-{suffix}-{new_seq:03d}"


async def create_entry(db: AsyncSession, project_id: UUID, data: EliminationCreate) -> EliminationEntry:
    """创建抵消分录"""
    total_debit = sum(l.debit_amount or Decimal("0") for l in data.lines)
    total_credit = sum(l.credit_amount or Decimal("0") for l in data.lines)
    if total_debit != total_credit:
        raise ValueError(f"借贷不平衡: 借方合计={total_debit}, 贷方合计={total_credit}")

    entry_no = await _generate_entry_no(db, project_id, data.year, data.entry_type)

    entry = EliminationEntry(
        project_id=project_id,
        entry_no=entry_no,
        year=data.year,
        entry_type=data.entry_type,
        description=data.description,
        related_company_codes=data.related_company_codes,
        review_status=ReviewStatusEnum.DRAFT,
        debit_amount=total_debit,
        credit_amount=total_credit,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_entry(db: AsyncSession, entry_id: UUID, project_id: UUID) -> EliminationEntry | None:
    result = await db.execute(
        sa.select(EliminationEntry).where(
            EliminationEntry.id == entry_id,
            EliminationEntry.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def get_entries(
    db: AsyncSession,
    project_id: UUID,
    year: int | None = None,
    entry_type: EliminationEntryType | None = None,
    review_status: ReviewStatusEnum | None = None,
) -> list[EliminationEntry]:
    stmt = sa.select(EliminationEntry).where(
        EliminationEntry.project_id == project_id,
        EliminationEntry.is_deleted.is_(False),
    )
    if year:
        stmt = stmt.where(EliminationEntry.year == year)
    if entry_type:
        stmt = stmt.where(EliminationEntry.entry_type == entry_type)
    if review_status:
        stmt = stmt.where(EliminationEntry.review_status == review_status)
    stmt = stmt.order_by(EliminationEntry.entry_no)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_entry(
    db: AsyncSession, entry_id: UUID, project_id: UUID, data: EliminationEntryUpdate,
) -> EliminationEntry | None:
    entry = await get_entry(db, entry_id, project_id)
    if not entry:
        return None
    if entry.review_status not in (ReviewStatusEnum.DRAFT, ReviewStatusEnum.REJECTED):
        raise ValueError("只有草稿或已驳回状态的分录可以修改")

    if data.lines is not None:
        total_debit = sum(l.debit_amount or Decimal("0") for l in data.lines)
        total_credit = sum(l.credit_amount or Decimal("0") for l in data.lines)
        if total_debit != total_credit:
            raise ValueError("借贷不平衡")
        entry.debit_amount = total_debit
        entry.credit_amount = total_credit

    for key, value in data.model_dump(exclude_unset=True).items():
        if key != "lines":
            setattr(entry, key, value)

    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_entry(db: AsyncSession, entry_id: UUID, project_id: UUID) -> bool:
    entry = await get_entry(db, entry_id, project_id)
    if not entry:
        return False
    if entry.review_status == ReviewStatusEnum.APPROVED:
        raise ValueError("已审批的分录不能删除")
    entry.soft_delete()
    await db.commit()
    return True


async def change_review_status(
    db: AsyncSession, entry_id: UUID, project_id: UUID,
    action: EliminationReviewAction, reviewer_id: UUID | None = None,
) -> EliminationEntry | None:
    """复核状态机"""
    entry = await get_entry(db, entry_id, project_id)
    if not entry:
        return None

    current = entry.review_status
    if action.action == "approve":
        if current not in (ReviewStatusEnum.DRAFT, ReviewStatusEnum.PENDING_REVIEW):
            raise ValueError(f"当前状态 {current.value} 不能审批")
        entry.review_status = ReviewStatusEnum.APPROVED
    elif action.action == "reject":
        if current not in (ReviewStatusEnum.DRAFT, ReviewStatusEnum.PENDING_REVIEW):
            raise ValueError(f"当前状态 {current.value} 不能驳回")
        entry.review_status = ReviewStatusEnum.REJECTED
        if action.rejection_reason:
            entry.description = (entry.description or "") + f"\n驳回原因: {action.rejection_reason}"

    if reviewer_id:
        entry.reviewer_id = reviewer_id
    entry.reviewed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(entry)
    return entry


async def get_summary(db: AsyncSession, project_id: UUID, year: int) -> list[EliminationSummary]:
    """按类型分组汇总"""
    entries = await get_entries(db, project_id, year)
    type_map: dict[EliminationEntryType, dict] = {}
    for e in entries:
        if e.entry_type not in type_map:
            type_map[e.entry_type] = {"count": 0, "debit": Decimal("0"), "credit": Decimal("0")}
        type_map[e.entry_type]["count"] += 1
        for line in (e.lines or []):
            type_map[e.entry_type]["debit"] += Decimal(str(line.get("debit_amount") or 0))
            type_map[e.entry_type]["credit"] += Decimal(str(line.get("credit_amount") or 0))

    return [
        EliminationSummary(
            entry_type=t, count=v["count"],
            total_debit=v["debit"], total_credit=v["credit"],
        )
        for t, v in type_map.items()
    ]


async def get_summary_center(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict:
    """
    合并抵消分录表汇总中心 [R11.2]

    返回 5 个区域的汇总数据：
    1. 权益抵消区 — equity 类型分录汇总
    2. 内部交易区 — internal_trade 类型分录汇总
    3. 内部往来区 — internal_ar_ap 类型分录汇总
    4. 未实现利润区 — unrealized_profit 类型分录汇总
    5. 其他调整区 — other 类型分录汇总

    每个区域包含：分录列表、借方合计、贷方合计、净额、分录数量
    """
    entries = await get_entries(db, project_id, year)

    areas: dict[str, dict] = {
        "equity": {"label": "权益抵消", "entries": [], "total_debit": Decimal("0"), "total_credit": Decimal("0")},
        "internal_trade": {"label": "内部交易", "entries": [], "total_debit": Decimal("0"), "total_credit": Decimal("0")},
        "internal_ar_ap": {"label": "内部往来", "entries": [], "total_debit": Decimal("0"), "total_credit": Decimal("0")},
        "unrealized_profit": {"label": "未实现利润", "entries": [], "total_debit": Decimal("0"), "total_credit": Decimal("0")},
        "other": {"label": "其他调整", "entries": [], "total_debit": Decimal("0"), "total_credit": Decimal("0")},
    }

    for e in entries:
        area_key = e.entry_type.value if e.entry_type.value in areas else "other"
        area = areas[area_key]
        entry_debit = Decimal("0")
        entry_credit = Decimal("0")
        for line in (e.lines or []):
            entry_debit += Decimal(str(line.get("debit_amount") or 0))
            entry_credit += Decimal(str(line.get("credit_amount") or 0))

        area["entries"].append({
            "id": str(e.id),
            "entry_no": e.entry_no,
            "description": e.description,
            "debit_amount": str(entry_debit),
            "credit_amount": str(entry_credit),
            "review_status": e.review_status.value if e.review_status else "draft",
            "related_companies": e.related_company_codes,
        })
        area["total_debit"] += entry_debit
        area["total_credit"] += entry_credit

    # 转换为可序列化格式
    result = {}
    grand_total_debit = Decimal("0")
    grand_total_credit = Decimal("0")
    for key, area in areas.items():
        result[key] = {
            "label": area["label"],
            "count": len(area["entries"]),
            "entries": area["entries"],
            "total_debit": str(area["total_debit"]),
            "total_credit": str(area["total_credit"]),
            "net_amount": str(area["total_debit"] - area["total_credit"]),
        }
        grand_total_debit += area["total_debit"]
        grand_total_credit += area["total_credit"]

    result["grand_total"] = {
        "total_debit": str(grand_total_debit),
        "total_credit": str(grand_total_credit),
        "net_amount": str(grand_total_debit - grand_total_credit),
        "entry_count": len(entries),
    }

    return result
