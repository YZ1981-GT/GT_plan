"""抵消分录服务 — 异步 ORM"""

from decimal import Decimal
from uuid import UUID, uuid4
from datetime import datetime, timezone

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


def _serialize_lines(lines: list[EliminationEntryLine]) -> tuple[list[dict], Decimal, Decimal]:
    """明细行 → JSONB 行 + 借贷合计；借贷不平衡、没有明细行、明细行缺科目 ⇒ ValueError。"""
    if not lines:
        raise ValueError("分录至少需要一行明细")
    zero = Decimal("0")
    total_debit = sum((l.debit_amount or zero for l in lines), zero)
    total_credit = sum((l.credit_amount or zero for l in lines), zero)
    if total_debit != total_credit:
        raise ValueError(f"借贷不平衡: 借方合计={total_debit}, 贷方合计={total_credit}")
    for i, l in enumerate(lines, 1):
        if not (l.account_code or "").strip():
            raise ValueError(f"第 {i} 行没有科目")
    rows = [
        {
            "account_code": l.account_code.strip(),
            "account_name": l.account_name,
            "debit_amount": str(l.debit_amount or zero),
            "credit_amount": str(l.credit_amount or zero),
        }
        for l in lines
    ]
    return rows, total_debit, total_credit


def _clean_branch_code(value: str | None) -> str | None:
    return (value or "").strip() or None


_STATUS_LABELS: dict[ReviewStatusEnum, str] = {
    ReviewStatusEnum.draft: "草稿",
    ReviewStatusEnum.pending_review: "待审批",
    ReviewStatusEnum.approved: "已审批",
    ReviewStatusEnum.rejected: "已驳回",
}


async def validate_entry_attribution(
    db: AsyncSession, project_id: UUID, branch_entity_code: str | None,
) -> str:
    """校验分录归属的差额节点（spec consol-tree-three-code-autobuild 需求 6.2），返回其 node_key。

    与合并计算同一归属函数（``consol_calc_basis.attribute_entry``）：能保存的分录恰是会被计入的分录。
    找不到节点 / 节点由其他合并项目承载 ⇒ ValueError（路由转 400），说明应到哪个合并项目录入。
    """
    from app.services.consol_calc_basis import EntryRecord, attribute_entry, index_tree
    from app.services.consol_tree_service import build_tree

    tree = await build_tree(db, project_id)
    if tree is None:
        raise ValueError("项目不存在，无法录入合并分录")
    if tree.role != "consol":
        raise ValueError("只有合并报表项目可以录入合并分录")
    probe = EntryRecord(
        id=uuid4(), project_id=project_id, entry_no="", entry_type="",
        branch_entity_code=_clean_branch_code(branch_entity_code), lines=(),
    )
    key, reason = attribute_entry(probe, index_tree(tree))
    if key is None:
        raise ValueError(reason or "找不到分录归属的差额节点")
    return key


async def create_entry(db: AsyncSession, project_id: UUID, data: EliminationCreate) -> EliminationEntry:
    """创建抵消分录（草稿）：校验借贷平衡与归属节点，明细行即金额口径，首行科目作表头代表科目。"""
    lines, total_debit, total_credit = _serialize_lines(data.lines)
    branch_code = _clean_branch_code(data.branch_entity_code)
    await validate_entry_attribution(db, project_id, branch_code)

    entry_no = await _generate_entry_no(db, project_id, data.year, data.entry_type)
    first_line = lines[0]
    entry = EliminationEntry(
        id=uuid4(),
        project_id=project_id,
        entry_no=entry_no,
        year=data.year,
        entry_type=data.entry_type,
        description=data.description,
        account_code=first_line["account_code"],
        account_name=first_line["account_name"],
        lines=lines,
        entry_group_id=uuid4(),
        related_company_codes=data.related_company_codes,
        branch_entity_code=branch_code,
        review_status=ReviewStatusEnum.draft,
        debit_amount=total_debit,
        credit_amount=total_credit,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_entry(db: AsyncSession, entry_id: UUID, project_id: UUID) -> EliminationEntry | None:
    """读取单笔分录（已软删的视为不存在，需求 6.5）。"""
    result = await db.execute(
        sa.select(EliminationEntry).where(
            EliminationEntry.id == entry_id,
            EliminationEntry.project_id == project_id,
            EliminationEntry.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


def _parse_node_key(node_key: str) -> tuple[str, str | None]:
    """``{企业代码}:{角色}`` → (角色, 企业代码)；只接受两类差额节点。"""
    code, _, role = (node_key or "").partition(":")
    if role not in ("consol_elim", "branch_elim") or not code:
        raise ValueError(f"只能按差额节点筛选分录（合并差额 / 母分差额），收到 {node_key!r}")
    return role, code


async def get_entries(
    db: AsyncSession,
    project_id: UUID,
    year: int | None = None,
    entry_type: EliminationEntryType | None = None,
    review_status: ReviewStatusEnum | None = None,
    node_key: str | None = None,
) -> list[EliminationEntry]:
    """分录列表；``node_key`` 按归属差额节点筛选（需求 6.6）：
    ``{本企业}:consol_elim`` = 归属为空的分录；``{企业}:branch_elim`` = 归属该企业的分录。"""
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
    if node_key:
        role, code = _parse_node_key(node_key)
        if role == "consol_elim":
            stmt = stmt.where(sa.or_(
                EliminationEntry.branch_entity_code.is_(None), EliminationEntry.branch_entity_code == "",
            ))
        else:
            stmt = stmt.where(EliminationEntry.branch_entity_code == code)
    stmt = stmt.order_by(EliminationEntry.entry_no)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_entry(
    db: AsyncSession, entry_id: UUID, project_id: UUID, data: EliminationEntryUpdate,
) -> EliminationEntry | None:
    """修改草稿/已驳回分录：明细行与表头代表科目、借贷合计一并更新（需求 6.5）；改归属须重新校验。"""
    entry = await get_entry(db, entry_id, project_id)
    if not entry:
        return None
    if entry.review_status not in (ReviewStatusEnum.draft, ReviewStatusEnum.rejected):
        raise ValueError("只有草稿或已驳回状态的分录可以修改")

    changes = data.model_dump(exclude_unset=True)
    if "branch_entity_code" in changes:
        branch_code = _clean_branch_code(changes["branch_entity_code"])
        await validate_entry_attribution(db, project_id, branch_code)
        entry.branch_entity_code = branch_code
    if data.lines is not None:
        lines, total_debit, total_credit = _serialize_lines(data.lines)
        entry.lines = lines
        entry.account_code = lines[0]["account_code"]
        entry.account_name = lines[0]["account_name"]
        entry.debit_amount = total_debit
        entry.credit_amount = total_credit
    for key in ("entry_type", "description", "related_company_codes"):
        if key in changes:
            setattr(entry, key, changes[key])

    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_entry(db: AsyncSession, entry_id: UUID, project_id: UUID) -> bool:
    entry = await get_entry(db, entry_id, project_id)
    if not entry:
        return False
    if entry.review_status == ReviewStatusEnum.approved:
        raise ValueError("已审批的分录不能删除")
    entry.soft_delete()
    await db.commit()
    return True


class EntryLockedError(ValueError):
    """合并项目（或其上层合并项目）已锁定，拒绝改变已计入合并的分录（路由转 423）。"""


async def assert_push_targets_unlocked(db: AsyncSession, project_id: UUID, what: str) -> None:
    """撤销审批会重算本项目及全部上层合并项目：任一已合并锁定 ⇒ 拒绝并说明（需求 8.2）。"""
    from app.services.consol_push_service import locked_targets, push_targets

    names = await locked_targets(db, await push_targets(db, project_id))
    if names:
        raise EntryLockedError(f"{'、'.join(names)} 已合并锁定，不能{what}；请先解锁")


async def change_review_status(
    db: AsyncSession, entry_id: UUID, project_id: UUID,
    action: EliminationReviewAction, reviewer_id: UUID | None = None,
) -> EliminationEntry | None:
    """复核状态机：草稿/已驳回 --提交--> 待审批；草稿/待审批 --审批--> 已审批 | --驳回--> 已驳回；
    已审批 --撤销审批--> 草稿（合并项目或其上层合并项目锁定时拒绝，需求 8.2）。

    提交与审批前重新校验归属节点（企业树可能在录入后变化）：能审批 ⇔ 审批后会被计入（需求 6.2 / 6.4）。
    """
    entry = await get_entry(db, entry_id, project_id)
    if not entry:
        return None

    current = entry.review_status
    if action.action == "revoke":
        if current != ReviewStatusEnum.approved:
            raise ValueError(f"当前状态 {_STATUS_LABELS.get(current, current.value)} 不能撤销审批（只有已审批的分录可以撤销）")
        await assert_push_targets_unlocked(db, project_id, "撤销审批")
        entry.review_status = ReviewStatusEnum.draft
        entry.reviewer_id = None
        entry.reviewed_at = None
        await db.commit()
        await db.refresh(entry)
        return entry
    if action.action == "submit":
        if current not in (ReviewStatusEnum.draft, ReviewStatusEnum.rejected):
            raise ValueError(f"当前状态 {_STATUS_LABELS.get(current, current.value)} 不能提交审批")
        await validate_entry_attribution(db, project_id, entry.branch_entity_code)
        entry.review_status = ReviewStatusEnum.pending_review
        await db.commit()
        await db.refresh(entry)
        return entry
    if action.action == "approve":
        if current not in (ReviewStatusEnum.draft, ReviewStatusEnum.pending_review):
            raise ValueError(f"当前状态 {_STATUS_LABELS.get(current, current.value)} 不能审批")
        await validate_entry_attribution(db, project_id, entry.branch_entity_code)
        entry.review_status = ReviewStatusEnum.approved
    elif action.action == "reject":
        if current not in (ReviewStatusEnum.draft, ReviewStatusEnum.pending_review):
            raise ValueError(f"当前状态 {_STATUS_LABELS.get(current, current.value)} 不能驳回")
        entry.review_status = ReviewStatusEnum.rejected
        if action.rejection_reason:
            entry.description = (entry.description or "") + f"\n驳回原因: {action.rejection_reason}"

    if reviewer_id:
        entry.reviewer_id = reviewer_id
    entry.reviewed_at = datetime.now(timezone.utc)

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
