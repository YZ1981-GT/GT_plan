"""抵消分录服务

抵消分录在数据库中按行式存储（一个科目一行），通过 entry_group_id 关联。
API 层面以 lines 列表形式输入/输出，service 层负责行-组转换。
"""

from decimal import Decimal
from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.consolidation_models import (
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)
from app.models.consolidation_schemas import (
    EliminationEntryCreate,
    EliminationEntryLine,
    EliminationEntryResponse,
    EliminationEntryUpdate,
    EliminationReviewAction,
    EliminationSummary,
)


# ---------------------------------------------------------------------------
# 编号生成
# ---------------------------------------------------------------------------

_PREFIX_MAP = {
    EliminationEntryType.equity: "CE",          # 权益抵消
    EliminationEntryType.internal_trade: "IT",  # 内部交易
    EliminationEntryType.internal_ar_ap: "IA", # 内部往来
    EliminationEntryType.unrealized_profit: "UP",  # 未实现利润
    EliminationEntryType.other: "OT",           # 其他
}


def _next_entry_no(db: Session, project_id: UUID, year: int, entry_type: EliminationEntryType) -> str:
    prefix = _PREFIX_MAP.get(entry_type, "CE")
    pattern = f"{prefix}-{year}-%"
    last = (
        db.query(func.max(EliminationEntry.entry_no))
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.entry_no.like(pattern),
            EliminationEntry.is_deleted.is_(False),
        )
        .scalar()
    )
    seq = 1
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}-{year}-{seq:03d}"


# ---------------------------------------------------------------------------
# 分录组 CRUD
# ---------------------------------------------------------------------------


def _get_group_rows(
    db: Session, entry_group_id: UUID, project_id: UUID
) -> list[EliminationEntry]:
    return (
        db.query(EliminationEntry)
        .filter(
            EliminationEntry.entry_group_id == entry_group_id,
            EliminationEntry.project_id == project_id,
            EliminationEntry.is_deleted.is_(False),
        )
        .order_by(EliminationEntry.account_code)
        .all()
    )


def _group_to_response(rows: list[EliminationEntry]) -> EliminationEntryResponse:
    """将一组行转换为 API 响应"""
    first = rows[0]
    return EliminationEntryResponse(
        id=first.id,
        project_id=first.project_id,
        year=first.year,
        entry_no=first.entry_no,
        entry_type=first.entry_type,
        description=first.description,
        lines=[
            EliminationEntryLine(
                account_code=r.account_code,
                account_name=r.account_name,
                debit_amount=r.debit_amount,
                credit_amount=r.credit_amount,
            )
            for r in rows
        ],
        entry_group_id=first.entry_group_id,
        is_continuous=first.is_continuous,
        prior_year_entry_id=first.prior_year_entry_id,
        review_status=first.review_status,
        reviewer_id=first.reviewer_id,
        reviewed_at=first.reviewed_at,
        is_deleted=first.is_deleted,
        created_at=first.created_at,
        updated_at=first.updated_at,
    )


def create_entry(
    db: Session, project_id: UUID, data: EliminationEntryCreate
) -> EliminationEntryResponse:
    """
    创建抵消分录组。
    - 校验借贷平衡
    - 自动生成编号
    - 写入 entry_group_id 相同的多行数据
    """
    total_debit = sum(l.debit_amount or Decimal("0") for l in data.lines)
    total_credit = sum(l.credit_amount or Decimal("0") for l in data.lines)
    if total_debit != total_credit:
        raise ValueError(f"借贷不平衡: 借方={total_debit}, 贷方={total_credit}")

    entry_no = _next_entry_no(db, project_id, data.year, data.entry_type)
    group_id = uuid4()

    rows: list[EliminationEntry] = []
    for line in data.lines:
        rows.append(
            EliminationEntry(
                project_id=project_id,
                year=data.year,
                entry_no=entry_no,
                entry_type=data.entry_type,
                description=data.description,
                account_code=line.account_code,
                account_name=line.account_name,
                debit_amount=line.debit_amount or Decimal("0"),
                credit_amount=line.credit_amount or Decimal("0"),
                entry_group_id=group_id,
                related_company_codes=data.related_company_codes,
                review_status=ReviewStatusEnum.draft,
            )
        )
    db.add_all(rows)
    db.commit()

    # 以第一条的 id 作为组的代表 id
    db.refresh(rows[0])
    return _group_to_response(rows)


def get_entry(
    db: Session, entry_group_id: UUID, project_id: UUID
) -> EliminationEntryResponse | None:
    rows = _get_group_rows(db, entry_group_id, project_id)
    return _group_to_response(rows) if rows else None


def get_entries(
    db: Session,
    project_id: UUID,
    year: int | None = None,
    entry_type: EliminationEntryType | None = None,
    review_status: ReviewStatusEnum | None = None,
) -> list[EliminationEntryResponse]:
    """返回分录组列表（每个组只取第一条行用于展示）"""
    q = (
        db.query(EliminationEntry)
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.is_deleted.is_(False),
        )
        .group_by(EliminationEntry.entry_group_id)
    )
    if year:
        q = q.filter(EliminationEntry.year == year)
    if entry_type:
        q = q.filter(EliminationEntry.entry_type == entry_type)
    if review_status:
        q = q.filter(EliminationEntry.review_status == review_status)

    # 取每组第一条
    sub = (
        db.query(func.min(EliminationEntry.id))
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.is_deleted.is_(False),
        )
        .group_by(EliminationEntry.entry_group_id)
        .subquery()
    )
    rows = (
        db.query(EliminationEntry)
        .filter(EliminationEntry.id.in_(sub))
        .order_by(EliminationEntry.entry_no)
        .all()
    )

    # 按 group_id 聚合
    groups: dict[UUID, list[EliminationEntry]] = {}
    for r in rows:
        groups.setdefault(r.entry_group_id, []).append(r)

    return [_group_to_response(g) for g in groups.values()]


def update_entry(
    db: Session,
    entry_group_id: UUID,
    project_id: UUID,
    data: EliminationEntryUpdate,
) -> EliminationEntryResponse | None:
    rows = _get_group_rows(db, entry_group_id, project_id)
    if not rows:
        return None
    if rows[0].review_status not in (ReviewStatusEnum.draft, ReviewStatusEnum.rejected):
        raise ValueError("只有草稿/已驳回状态的分录可以修改")

    if data.lines is not None:
        total_debit = sum(l.debit_amount or Decimal("0") for l in data.lines)
        total_credit = sum(l.credit_amount or Decimal("0") for l in data.lines)
        if total_debit != total_credit:
            raise ValueError("借贷不平衡")

    # 软删除旧行
    for r in rows:
        r.is_deleted = True

    # 写入新行（复用原 entry_no 和 group_id）
    new_rows: list[EliminationEntry] = []
    lines = data.lines if data.lines is not None else [
        EliminationEntryLine(
            account_code=r.account_code,
            account_name=r.account_name,
            debit_amount=r.debit_amount,
            credit_amount=r.credit_amount,
        )
        for r in rows
    ]
    for line in lines:
        new_rows.append(
            EliminationEntry(
                project_id=project_id,
                year=rows[0].year,
                entry_no=rows[0].entry_no,
                entry_type=data.entry_type or rows[0].entry_type,
                description=data.description if data.description is not None else rows[0].description,
                account_code=line.account_code,
                account_name=line.account_name,
                debit_amount=line.debit_amount or Decimal("0"),
                credit_amount=line.credit_amount or Decimal("0"),
                entry_group_id=entry_group_id,
                related_company_codes=data.related_company_codes or rows[0].related_company_codes,
                review_status=rows[0].review_status,
            )
        )
    db.add_all(new_rows)
    db.commit()
    return _group_to_response(new_rows)


def delete_entry(db: Session, entry_group_id: UUID, project_id: UUID) -> bool:
    rows = _get_group_rows(db, entry_group_id, project_id)
    if not rows:
        return False
    if rows[0].review_status == ReviewStatusEnum.approved:
        raise ValueError("已审批的分录不能删除")
    for r in rows:
        r.is_deleted = True
    db.commit()
    return True


# ---------------------------------------------------------------------------
# 复核状态机
# ---------------------------------------------------------------------------


def change_review_status(
    db: Session,
    entry_group_id: UUID,
    project_id: UUID,
    action: EliminationReviewAction,
    reviewer_id: UUID | None = None,
) -> EliminationEntryResponse | None:
    rows = _get_group_rows(db, entry_group_id, project_id)
    if not rows:
        return None

    current = rows[0].review_status
    now = datetime.utcnow()

    if action.action == "approve":
        if current not in (ReviewStatusEnum.draft, ReviewStatusEnum.pending_review):
            raise ValueError(f"状态 {current.value} 不允许审批")
        new_status = ReviewStatusEnum.approved
    elif action.action == "reject":
        if current not in (ReviewStatusEnum.draft, ReviewStatusEnum.pending_review):
            raise ValueError(f"状态 {current.value} 不允许驳回")
        new_status = ReviewStatusEnum.rejected
        for r in rows:
            r.description = (r.description or "") + f"\n[驳回] {action.rejection_reason or ''}"
    else:
        raise ValueError(f"未知操作: {action.action}")

    for r in rows:
        r.review_status = new_status
        if reviewer_id:
            r.reviewer_id = reviewer_id
        r.reviewed_at = now

    db.commit()
    return _group_to_response(rows)


def submit_for_review(
    db: Session, entry_group_id: UUID, project_id: UUID
) -> EliminationEntryResponse | None:
    rows = _get_group_rows(db, entry_group_id, project_id)
    if not rows:
        return None
    if rows[0].review_status not in (ReviewStatusEnum.draft, ReviewStatusEnum.rejected):
        raise ValueError(f"当前状态 {rows[0].review_status.value} 不允许提交复核")
    for r in rows:
        r.review_status = ReviewStatusEnum.pending_review
    db.commit()
    return _group_to_response(rows)


# ---------------------------------------------------------------------------
# 连续编制结转
# ---------------------------------------------------------------------------


def carry_forward_prior_year(
    db: Session, project_id: UUID, from_year: int, to_year: int
) -> list[EliminationEntryResponse]:
    """
    连续编制核心逻辑：
    1. 复制 from_year 所有 approved 分录到 to_year
    2. 损益科目替换为"未分配利润"（account_code 映射规则）
    3. 标记 is_continuous=True，建立 prior_year_entry_id 关联
    4. 触发重算事件（由调用方在 router 层发布）
    """
    prior_rows = (
        db.query(EliminationEntry)
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == from_year,
            EliminationEntry.review_status == ReviewStatusEnum.approved,
            EliminationEntry.is_deleted.is_(False),
        )
        .all()
    )
    if not prior_rows:
        return []

    # 按 group_id 分组
    groups: dict[UUID, list[EliminationEntry]] = {}
    for r in prior_rows:
        groups.setdefault(r.entry_group_id, []).append(r)

    new_groups: list[list[EliminationEntry]] = []
    for old_group in groups.values():
        new_group_id = uuid4()
        prior_group_id = old_group[0].entry_group_id
        new_entry_no = _next_entry_no(
            db, project_id, to_year, old_group[0].entry_type
        )
        group_rows: list[EliminationEntry] = []
        for old_row in old_group:
            # 收入/费用科目 → 未分配利润
            account_code = old_row.account_code
            account_name = old_row.account_name
            if _is_pl_account(account_code):
                account_code = "4103"  # 未分配利润标准编码
                account_name = "未分配利润"
                # 借贷方向翻转（收入/费用结转时方向反向）
                debit = old_row.credit_amount
                credit = old_row.debit_amount
            else:
                debit = old_row.debit_amount
                credit = old_row.credit_amount

            group_rows.append(
                EliminationEntry(
                    project_id=project_id,
                    year=to_year,
                    entry_no=new_entry_no,
                    entry_type=old_row.entry_type,
                    description=f"[结转] {old_row.description or ''}",
                    account_code=account_code,
                    account_name=account_name,
                    debit_amount=debit,
                    credit_amount=credit,
                    entry_group_id=new_group_id,
                    related_company_codes=old_row.related_company_codes,
                    is_continuous=True,
                    prior_year_entry_id=prior_group_id,
                    review_status=ReviewStatusEnum.draft,
                )
            )
        db.add_all(group_rows)
        new_groups.append(group_rows)

    db.commit()

    result: list[EliminationEntryResponse] = []
    for group_rows in new_groups:
        db.refresh(group_rows[0])
        result.append(_group_to_response(group_rows))
    return result


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def get_summary(
    db: Session, project_id: UUID, year: int
) -> list[EliminationSummary]:
    entries = get_entries(db, project_id, year)
    type_map: dict[EliminationEntryType, dict] = {}
    for e in entries:
        if e.entry_type not in type_map:
            type_map[e.entry_type] = {"count": 0, "debit": Decimal("0"), "credit": Decimal("0")}
        type_map[e.entry_type]["count"] += 1
        for line in e.lines:
            type_map[e.entry_type]["debit"] += line.debit_amount or Decimal("0")
            type_map[e.entry_type]["credit"] += line.credit_amount or Decimal("0")
    return [
        EliminationSummary(
            entry_type=t,
            count=v["count"],
            total_debit=v["debit"],
            total_credit=v["credit"],
        )
        for t, v in type_map.items()
    ]


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

# 收入类起始编码（可根据科目表定制）
_INCOME_CODES = {"5", "6001", "6002", "6051", "6111", "6301", "6401", "6402", "6601", "6602", "6603"}


def _is_pl_account(account_code: str) -> bool:
    """判断是否为损益类科目（收入或费用）"""
    if not account_code:
        return False
    first = account_code[0]
    # 4=成本费用, 5=损益收入, 6=期间费用
    return first in ("4", "5", "6") or account_code[:2] in _INCOME_CODES
