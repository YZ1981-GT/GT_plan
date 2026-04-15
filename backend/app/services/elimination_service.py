"""抵消分录服务"""

from decimal import Decimal
from uuid import UUID
from datetime import datetime

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum
from app.models.consolidation_schemas import (
    EliminationCreate,
    EliminationEntryResponse,
    EliminationEntryLine,
    EliminationEntryUpdate,
    EliminationReviewAction,
    EliminationSummary,
)


def _generate_entry_no(db: Session, project_id: UUID, year: int, entry_type: EliminationEntryType) -> str:
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

    # 查找该类型最大序号
    pattern = f"{prefix}-{suffix}-%"
    result = (
        db.query(func.max(EliminationEntry.entry_no))
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.entry_no.like(pattern),
            EliminationEntry.is_deleted.is_(False),
        )
        .scalar()
    )
    if result:
        try:
            last_seq = int(result.split("-")[-1])
            new_seq = last_seq + 1
        except (ValueError, IndexError):
            new_seq = 1
    else:
        new_seq = 1

    return f"{prefix}-{suffix}-{new_seq:03d}"


def create_entry(db: Session, project_id: UUID, data: EliminationCreate) -> EliminationEntry:
    """创建抵消分录"""
    # 借贷平衡校验
    total_debit = sum(l.debit_amount or Decimal("0") for l in data.lines)
    total_credit = sum(l.credit_amount or Decimal("0") for l in data.lines)
    if total_debit != total_credit:
        raise ValueError(f"借贷不平衡: 借方合计={total_debit}, 贷方合计={total_credit}")

    entry_no = _generate_entry_no(db, project_id, data.year, data.entry_type)

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
    db.commit()
    db.refresh(entry)
    return entry


def get_entry(db: Session, entry_id: UUID, project_id: UUID) -> EliminationEntry | None:
    return (
        db.query(EliminationEntry)
        .filter(
            EliminationEntry.id == entry_id,
            EliminationEntry.project_id == project_id,
        )
        .first()
    )


def get_entries(
    db: Session,
    project_id: UUID,
    year: int | None = None,
    entry_type: EliminationEntryType | None = None,
    review_status: ReviewStatusEnum | None = None,
) -> list[EliminationEntry]:
    q = db.query(EliminationEntry).filter(
        EliminationEntry.project_id == project_id,
        EliminationEntry.is_deleted.is_(False),
    )
    if year:
        q = q.filter(EliminationEntry.year == year)
    if entry_type:
        q = q.filter(EliminationEntry.entry_type == entry_type)
    if review_status:
        q = q.filter(EliminationEntry.review_status == review_status)
    return q.order_by(EliminationEntry.entry_no).all()


def update_entry(
    db: Session,
    entry_id: UUID,
    project_id: UUID,
    data: EliminationEntryUpdate,
) -> EliminationEntry | None:
    entry = get_entry(db, entry_id, project_id)
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

    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, entry_id: UUID, project_id: UUID) -> bool:
    entry = get_entry(db, entry_id, project_id)
    if not entry:
        return False
    if entry.review_status == ReviewStatusEnum.APPROVED:
        raise ValueError("已审批的分录不能删除")
    entry.soft_delete()
    db.commit()
    return True


def change_review_status(
    db: Session,
    entry_id: UUID,
    project_id: UUID,
    action: EliminationReviewAction,
    reviewer_id: UUID | None = None,
) -> EliminationEntry | None:
    """复核状态机"""
    entry = get_entry(db, entry_id, project_id)
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

    db.commit()
    db.refresh(entry)
    return entry


def get_summary(db: Session, project_id: UUID, year: int) -> list[EliminationSummary]:
    """按类型分组汇总"""
    entries = get_entries(db, project_id, year)
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
            entry_type=t,
            count=v["count"],
            total_debit=v["debit"],
            total_credit=v["credit"],
        )
        for t, v in type_map.items()
    ]
