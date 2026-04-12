"""商誉计算服务

功能覆盖：
- calculate_goodwill：计算初始商誉（含负商誉处理）
- record_impairment：记录减值 + 自动生成减值抵消分录 + 发布事件
- CRUD：create/get/update/delete goodwill_calc 记录
- 数据模型：goodwill_calc 表

负商誉（廉价购买）处理规则：
- 负商誉金额直接计入当期"营业外收入"或"其他收益"，不入商誉科目
- 初始商誉记录 goodwill_amount = 0，is_negative_goodwill = True
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.consolidation_models import (
    EliminationEntry,
    EliminationEntryType,
    GoodwillCalc,
    ReviewStatusEnum,
)
from app.models.consolidation_schemas import (
    EliminationEntryBatchCreate,
    EliminationEntryLine,
    GoodwillCalcResponse,
    GoodwillInput,
)
from app.services.event_bus import event_bus


# ---------------------------------------------------------------------------
# 商誉计算
# ---------------------------------------------------------------------------

def calculate_goodwill(
    acquisition_cost: Decimal | None,
    identifiable_net_assets_fv: Decimal | None,
    parent_share_ratio: Decimal | None,
) -> tuple[Decimal | None, bool, str | None, str | None]:
    """
    计算初始商誉。

    公式：商誉 = 合并成本 - 可辨认净资产公允价值 × 母公司持股比例

    参数：
        acquisition_cost       - 合并成本
        identifiable_net_assets_fv - 可辨认净资产公允价值
        parent_share_ratio     - 母公司持股比例（以小数表示，如 80% 传 0.80）

    返回：
        (goodwill_amount, is_negative, goodwill_type, notes)
        - goodwill_amount: None 表示参数不足无法计算
        - is_negative: True 表示负商誉（廉价购买）
        - goodwill_type: "positive" | "negative" | None
        - notes: 计算说明或负商誉处理建议
    """
    if acquisition_cost is None or identifiable_net_assets_fv is None or parent_share_ratio is None:
        return None, False, None, None

    # 净资产公允价值 × 持股比例 = 母公司享有的份额
    parent_share = identifiable_net_assets_fv * parent_share_ratio
    goodwill = acquisition_cost - parent_share

    if goodwill < 0:
        is_negative = True
        goodwill_type = "negative"
        # 负商誉（廉价购买）直接计入当期损益，不入商誉
        # 记录入账方式
        abs_goodwill = abs(goodwill)
        if abs_goodwill <= acquisition_cost * Decimal("0.25"):
            treatment = "计入当期营业外收入"
        else:
            treatment = "计入递延收益，分期计入损益"
        notes = (
            f"负商誉 {abs_goodwill} = 合并成本 {acquisition_cost} - 净资产公允价值份额 {parent_share}。"
            f"处理方式：{treatment}"
        )
        # 负商誉不入商誉科目，记录为零
        goodwill = Decimal("0")
    else:
        is_negative = False
        goodwill_type = "positive"
        notes = (
            f"正商誉 {goodwill} = 合并成本 {acquisition_cost} - 净资产公允价值份额 {parent_share}。"
            f"持股比例 {parent_share_ratio:.2%}，净资产公允价值 {identifiable_net_assets_fv}"
        )

    return goodwill, is_negative, goodwill_type, notes


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _recalc_carrying_amount(record: GoodwillCalc) -> Decimal:
    """重新计算账面价值 = 初始商誉 - 累计减值"""
    if record.goodwill_amount is None:
        return Decimal("0")
    accumulated = record.accumulated_impairment or Decimal("0")
    return max(record.goodwill_amount - accumulated, Decimal("0"))


def _publish_goodwill_event(project_id: UUID, year: int, extra: dict | None = None) -> None:
    """发布商誉变更事件（同步，不阻塞）"""
    try:
        import asyncio
        payload = EventPayload(
            event_type=EventType.GOODWILL_IMPAIRED,
            project_id=project_id,
            year=year,
            account_codes=["商誉"],  # 商誉科目编码占位
            extra=extra or {},
        )
        loop = asyncio.get_event_loop()
        loop.create_task(event_bus.publish(payload))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def get_goodwill_list(db: Session, project_id: UUID, year: int) -> list[GoodwillCalc]:
    """获取指定项目和年度的全部商誉记录"""
    return (
        db.query(GoodwillCalc)
        .filter(
            GoodwillCalc.project_id == project_id,
            GoodwillCalc.year == year,
            GoodwillCalc.is_deleted.is_(False),
        )
        .order_by(GoodwillCalc.subsidiary_company_code)
        .all()
    )


def get_goodwill(db: Session, goodwill_id: UUID, project_id: UUID) -> GoodwillCalc | None:
    """根据 ID 获取单条商誉记录"""
    return (
        db.query(GoodwillCalc)
        .filter(
            GoodwillCalc.id == goodwill_id,
            GoodwillCalc.project_id == project_id,
            GoodwillCalc.is_deleted.is_(False),
        )
        .first()
    )


def get_goodwill_by_company(
    db: Session, project_id: UUID, year: int, company_code: str
) -> GoodwillCalc | None:
    """根据公司和年度获取商誉记录"""
    return (
        db.query(GoodwillCalc)
        .filter(
            GoodwillCalc.project_id == project_id,
            GoodwillCalc.year == year,
            GoodwillCalc.subsidiary_company_code == company_code,
            GoodwillCalc.is_deleted.is_(False),
        )
        .first()
    )


def create_goodwill(
    db: Session,
    project_id: UUID,
    data: GoodwillInput,
) -> GoodwillCalc:
    """
    创建商誉计算记录。

    - 自动执行 calculate_goodwill，计算 goodwill_amount
    - 负商誉时 goodwill_amount = 0，is_negative_goodwill = True
    - 初始 accumulated_impairment = 0
    - carrying_amount = goodwill_amount（尚未减值）
    """
    goodwill_amount, is_negative, goodwill_type, notes = calculate_goodwill(
        data.acquisition_cost,
        data.identifiable_net_assets_fv,
        data.parent_share_ratio,
    )

    # carrying_amount 初始等于 goodwill_amount
    carrying_amount = goodwill_amount

    goodwill = GoodwillCalc(
        project_id=project_id,
        year=data.year,
        subsidiary_company_code=data.subsidiary_company_code,
        acquisition_date=data.acquisition_date,
        acquisition_cost=data.acquisition_cost,
        identifiable_net_assets_fv=data.identifiable_net_assets_fv,
        parent_share_ratio=data.parent_share_ratio,
        goodwill_amount=goodwill_amount,
        is_negative_goodwill=is_negative,
        negative_goodwill_treatment=notes,
        carrying_amount=carrying_amount,
        accumulated_impairment=Decimal("0"),
        current_year_impairment=Decimal("0"),
    )
    db.add(goodwill)
    db.commit()
    db.refresh(goodwill)
    return goodwill


def update_goodwill(
    db: Session,
    goodwill_id: UUID,
    project_id: UUID,
    data: GoodwillInput,
) -> GoodwillCalc | None:
    """
    更新商誉计算记录。

    - 若 acquisition_cost / identifiable_net_assets_fv / parent_share_ratio 变化，
      则重新执行 calculate_goodwill
    - carrying_amount 同步更新
    """
    goodwill = get_goodwill(db, goodwill_id, project_id)
    if not goodwill:
        return None

    # 更新输入字段
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(goodwill, key, value)

    # 若关键参数变化则重算商誉
    recalc = any(
        k in changes
        for k in ("acquisition_cost", "identifiable_net_assets_fv", "parent_share_ratio")
    )
    if recalc:
        goodwill_amount, is_negative, _, notes = calculate_goodwill(
            goodwill.acquisition_cost,
            goodwill.identifiable_net_assets_fv,
            goodwill.parent_share_ratio,
        )
        goodwill.goodwill_amount = goodwill_amount
        goodwill.is_negative_goodwill = is_negative
        goodwill.negative_goodwill_treatment = notes
        # 重算 carrying_amount = goodwill_amount - accumulated
        goodwill.accumulated_impairment = goodwill.accumulated_impairment or Decimal("0")
        goodwill.carrying_amount = _recalc_carrying_amount(goodwill)

    db.commit()
    db.refresh(goodwill)
    return goodwill


# ---------------------------------------------------------------------------
# 减值记录（核心业务逻辑）
# ---------------------------------------------------------------------------

def record_impairment(
    db: Session,
    project_id: UUID,
    company_code: str,
    year: int,
    impairment_amount: Decimal,
    notes: str | None = None,
) -> GoodwillCalc | None:
    """
    记录商誉减值，并自动生成对应的减值抵消分录。

    业务规则：
    1. 根据 company_code + year 查找 goodwill_calc 记录（读取初始商誉）
    2. 校验减值金额：单次记录不得超出 initial_goodwill - accumulated_impairment
    3. 更新 goodwill_calc：
       - current_year_impairment += impairment_amount
       - accumulated_impairment += impairment_amount
       - carrying_amount = goodwill_amount - accumulated_impairment
    4. 自动生成抵消分录（调用 EliminationService.create_entry）：
       - 借：资产减值损失（商誉减值损失科目）
       - 贷：商誉减值准备（备抵类科目）
    5. 发布 GOODWILL_IMPAIRED 事件

    参数：
        project_id        - 项目 ID
        company_code      - 子公司代码
        year              - 减值所属年度
        impairment_amount  - 本次减值金额（正数）
        notes             - 减值说明（写入分录描述）

    返回：
        更新后的 GoodwillCalc 记录，失败时返回 None

    抛出：
        ValueError - 减值金额超限、记录不存在或已软删除
    """
    if impairment_amount <= 0:
        raise ValueError("减值金额必须大于 0")

    goodwill = get_goodwill_by_company(db, project_id, year, company_code)
    if not goodwill:
        raise ValueError(f"未找到商誉记录: company_code={company_code}, year={year}")

    if goodwill.is_deleted:
        raise ValueError(f"商誉记录已删除: company_code={company_code}, year={year}")

    # 允许的减值上限 = 初始商誉 - 已累计减值
    initial = goodwill.goodwill_amount or Decimal("0")
    accumulated = goodwill.accumulated_impairment or Decimal("0")
    max_allowed = initial - accumulated

    if impairment_amount > max_allowed:
        raise ValueError(
            f"减值金额 {impairment_amount} 超出允许上限 {max_allowed} "
            f"(初始商誉 {initial} - 已累计减值 {accumulated})"
        )

    # 正商誉才能减值（负商誉不入商誉科目，无减值问题）
    if goodwill.is_negative_goodwill:
        raise ValueError("负商誉不入商誉科目，无需记录减值")

    # 更新减值字段
    goodwill.current_year_impairment = (
        (goodwill.current_year_impairment or Decimal("0")) + impairment_amount
    )
    goodwill.accumulated_impairment = accumulated + impairment_amount
    goodwill.carrying_amount = _recalc_carrying_amount(goodwill)

    db.commit()
    db.refresh(goodwill)

    # 生成减值抵消分录
    _create_impairment_elimination(
        db=db,
        project_id=project_id,
        year=year,
        company_code=company_code,
        impairment_amount=impairment_amount,
        notes=notes,
    )

    # 发布事件
    _publish_goodwill_event(
        project_id=project_id,
        year=year,
        extra={
            "company_code": company_code,
            "impairment_amount": str(impairment_amount),
            "accumulated_impairment": str(goodwill.accumulated_impairment),
            "carrying_amount": str(goodwill.carrying_amount),
        },
    )

    return goodwill


def _create_impairment_elimination(
    db: Session,
    project_id: UUID,
    year: int,
    company_code: str,
    impairment_amount: Decimal,
    notes: str | None,
) -> None:
    """
    为商誉减值生成抵消分录。

    分录模板：
        借：资产减值损失 — 商誉减值损失
        贷：商誉减值准备

    分录类型标记为 other（商誉减值不归属其他四类）
    """
    description = notes or f"商誉减值准备 - {company_code}"
    if impairment_amount:
        description += f" {impairment_amount} 元"

    # 查找该年度已有的商誉减值分录数量，用于生成连续编号
    prefix = "GW"
    last_entry = (
        db.query(EliminationEntry.entry_no)
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.entry_no.like(f"{prefix}-{year}-%"),
            EliminationEntry.is_deleted.is_(False),
        )
        .order_by(EliminationEntry.entry_no.desc())
        .first()
    )
    seq = 1
    if last_entry:
        try:
            seq = int(last_entry[0].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    entry_no = f"{prefix}-{year}-{seq:03d}"

    group_id = uuid4()

    # 商誉减值抵消分录：借贷平衡（同一金额两行）
    lines = [
        EliminationEntryLine(
            account_code="6701",          # 资产减值损失
            account_name="资产减值损失",
            debit_amount=impairment_amount,
            credit_amount=Decimal("0"),
        ),
        EliminationEntryLine(
            account_code="1602",          # 商誉减值准备（备抵类资产科目）
            account_name="商誉减值准备",
            debit_amount=Decimal("0"),
            credit_amount=impairment_amount,
        ),
    ]

    for line in lines:
        db.add(
            EliminationEntry(
                project_id=project_id,
                year=year,
                entry_no=entry_no,
                entry_type=EliminationEntryType.other,
                description=description,
                account_code=line.account_code,
                account_name=line.account_name,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                entry_group_id=group_id,
                related_company_codes=[company_code],
                is_continuous=False,
                review_status=ReviewStatusEnum.draft,
            )
        )

    db.commit()


# ---------------------------------------------------------------------------
# 软删除
# ---------------------------------------------------------------------------

def delete_goodwill(db: Session, goodwill_id: UUID, project_id: UUID) -> bool:
    """软删除商誉记录"""
    goodwill = get_goodwill(db, goodwill_id, project_id)
    if not goodwill:
        return False
    goodwill.is_deleted = True
    db.commit()
    return True


# ---------------------------------------------------------------------------
# 商誉结转
# ---------------------------------------------------------------------------


def carry_forward(
    db: Session,
    project_id: UUID,
    from_year: int,
    to_year: int,
) -> dict:
    """
    结转上年商誉数据到当年，累计减值自动更新。

    业务规则：
    1. 查询 from_year 的所有非删除 goodwill_calc 记录
    2. 对每条记录，在 to_year 中查找是否已存在（按 company_code 匹配）
    3. 若存在：更新 accumulated_impairment、current_year_impairment=0、carrying_amount 重算
    4. 若不存在：创建新记录，copies acquisition_cost / identifiable_net_assets_fv /
                 parent_share_ratio / goodwill_amount / accumulated_impairment（从 from_year 来），
                 current_year_impairment=0，carrying_amount 重算
    5. 发布 GOODWILL_IMPAIRED 事件

    参数：
        project_id  - 项目 ID
        from_year   - 上年年度
        to_year     - 当年年度

    返回：
        CarryForwardResult 结构 dict，包含结转统计
    """
    from app.models.consolidation_schemas import CarryForwardResult

    prior_records = (
        db.query(GoodwillCalc)
        .filter(
            GoodwillCalc.project_id == project_id,
            GoodwillCalc.year == from_year,
            GoodwillCalc.is_deleted.is_(False),
        )
        .all()
    )

    carried = 0
    new_records = 0
    updated_records = 0
    details: list[dict] = []

    for prior in prior_records:
        # 查找当年是否已有记录
        existing = (
            db.query(GoodwillCalc)
            .filter(
                GoodwillCalc.project_id == project_id,
                GoodwillCalc.year == to_year,
                GoodwillCalc.subsidiary_company_code == prior.subsidiary_company_code,
                GoodwillCalc.is_deleted.is_(False),
            )
            .first()
        )

        if existing:
            # 更新：继承商誉基础数据，累计减值从上年结转过来
            existing.acquisition_cost = prior.acquisition_cost
            existing.identifiable_net_assets_fv = prior.identifiable_net_assets_fv
            existing.parent_share_ratio = prior.parent_share_ratio
            existing.goodwill_amount = prior.goodwill_amount
            existing.acquisition_date = prior.acquisition_date
            existing.is_negative_goodwill = prior.is_negative_goodwill
            existing.negative_goodwill_treatment = prior.negative_goodwill_treatment
            existing.accumulated_impairment = prior.accumulated_impairment
            existing.current_year_impairment = Decimal("0")
            existing.carrying_amount = _recalc_carrying_amount(existing)
            updated_records += 1
            detail = {
                "company_code": prior.subsidiary_company_code,
                "action": "updated",
                "accumulated_impairment": str(prior.accumulated_impairment or Decimal("0")),
                "carrying_amount": str(existing.carrying_amount),
            }
        else:
            # 创建：复制上年数据到当年
            new_rec = GoodwillCalc(
                project_id=project_id,
                year=to_year,
                subsidiary_company_code=prior.subsidiary_company_code,
                acquisition_date=prior.acquisition_date,
                acquisition_cost=prior.acquisition_cost,
                identifiable_net_assets_fv=prior.identifiable_net_assets_fv,
                parent_share_ratio=prior.parent_share_ratio,
                goodwill_amount=prior.goodwill_amount,
                is_negative_goodwill=prior.is_negative_goodwill,
                negative_goodwill_treatment=prior.negative_goodwill_treatment,
                accumulated_impairment=prior.accumulated_impairment or Decimal("0"),
                current_year_impairment=Decimal("0"),
                carrying_amount=_recalc_carrying_amount(prior),
            )
            db.add(new_rec)
            new_records += 1
            detail = {
                "company_code": prior.subsidiary_company_code,
                "action": "created",
                "accumulated_impairment": str(prior.accumulated_impairment or Decimal("0")),
                "carrying_amount": str(new_rec.carrying_amount),
            }

        details.append(detail)
        carried += 1

    db.commit()

    _publish_goodwill_event(project_id, to_year, {"from_year": from_year, "action": "carry_forward"})

    return {
        "carried_records": carried,
        "new_records": new_records,
        "updated_records": updated_records,
        "details": details,
    }


# ---------------------------------------------------------------------------
# 权益抵消分录
# ---------------------------------------------------------------------------


def generate_equity_elimination(
    db: Session,
    project_id: UUID,
    year: int,
    data: dict,
) -> dict:
    """
    生成权益抵消分录（子公司账面权益 vs 母公司长期股权投资）。

    抵消逻辑（完全合并法）：
    借：实收资本           （子公司个别报表账面值）
        资本公积           （子公司个别报表账面值）
        盈余公积           （子公司个别报表账面值）
        未分配利润         （子公司个别报表账面值）
        [商誉]             （若 goodwill_amount > 0）
        贷：长期股权投资     （母公司个别报表中对子公司的投资账面值）
            少数股东权益     （净资产 × 少数股东持股比例）

    若商誉为零（负商誉情况），则不包含商誉行；若为负商誉，贷方增加营业外收入。

    参数：
        project_id  - 项目 ID
        year       - 年度
        data       - EquityEliminationInput 结构的 dict，需包含：
                     subsidiary_company_code, share_capital, capital_reserve,
                     surplus_reserve, undistributed_profit, long_term_equity_investment,
                     goodwill_amount（从 goodwill_calc 表读取，传 Decimal("0") 表示无商誉）,
                     minority_equity_amount（从 minority_interest 表读取）

    返回：
        EquityEliminationResult dict，包含分录编号、组ID、所有行项

    抛出：
        ValueError - 借贷不平衡
    """
    from app.models.consolidation_schemas import EquityEliminationInput, EquityEliminationResult

    input_data = EquityEliminationInput(**data)
    subsidiary = input_data.subsidiary_company_code

    # 商誉金额（从 goodwill_calc 表读，为 0 或 None 表示无商誉）
    goodwill_amount = input_data.goodwill_amount or Decimal("0")

    # 计算子公司账面权益合计
    equity_total = (
        (input_data.share_capital or Decimal("0"))
        + (input_data.capital_reserve or Decimal("0"))
        + (input_data.surplus_reserve or Decimal("0"))
        + (input_data.undistributed_profit or Decimal("0"))
    )

    # 长期股权投资（母公司个别报表账面值）
    lte_investment = input_data.long_term_equity_investment or Decimal("0")

    # 少数股东权益
    minority_equity = input_data.minority_equity_amount or Decimal("0")

    # 商誉（正向）
    goodwill_val = goodwill_amount

    # 计算贷方合计
    credit_total = lte_investment + minority_equity

    # 检查借贷平衡（允许极小误差）
    diff = abs(equity_total + goodwill_val - credit_total)
    if diff > Decimal("0.01"):
        raise ValueError(
            f"权益抵消分录借贷不平衡：借方合计={equity_total + goodwill_val}, "
            f"贷方合计={credit_total}，差异={diff}"
        )

    # 生成编号
    prefix = "CE"
    last_entry = (
        db.query(EliminationEntry.entry_no)
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.entry_no.like(f"{prefix}-{year}-%"),
            EliminationEntry.is_deleted.is_(False),
        )
        .order_by(EliminationEntry.entry_no.desc())
        .first()
    )
    seq = 1
    if last_entry:
        try:
            seq = int(last_entry[0].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    entry_no = f"{prefix}-{year}-{seq:03d}"
    group_id = uuid4()

    # 构建分录行
    lines: list[EliminationEntryLine] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")

    # --- 借方行（子公司权益科目） ---
    if (input_data.share_capital or Decimal("0")) > 0:
        lines.append(EliminationEntryLine(
            account_code="4001",
            account_name="实收资本",
            debit_amount=input_data.share_capital or Decimal("0"),
            credit_amount=Decimal("0"),
        ))
        total_debit += input_data.share_capital or Decimal("0")

    if (input_data.capital_reserve or Decimal("0")) > 0:
        lines.append(EliminationEntryLine(
            account_code="4002",
            account_name="资本公积",
            debit_amount=input_data.capital_reserve or Decimal("0"),
            credit_amount=Decimal("0"),
        ))
        total_debit += input_data.capital_reserve or Decimal("0")

    if (input_data.surplus_reserve or Decimal("0")) > 0:
        lines.append(EliminationEntryLine(
            account_code="4101",
            account_name="盈余公积",
            debit_amount=input_data.surplus_reserve or Decimal("0"),
            credit_amount=Decimal("0"),
        ))
        total_debit += input_data.surplus_reserve or Decimal("0")

    if (input_data.undistributed_profit or Decimal("0")) > 0:
        lines.append(EliminationEntryLine(
            account_code="4103",
            account_name="未分配利润",
            debit_amount=input_data.undistributed_profit or Decimal("0"),
            credit_amount=Decimal("0"),
        ))
        total_debit += input_data.undistributed_profit or Decimal("0")

    # 商誉借方行（仅正向商誉）
    if goodwill_val > 0:
        lines.append(EliminationEntryLine(
            account_code="1701",
            account_name="商誉",
            debit_amount=goodwill_val,
            credit_amount=Decimal("0"),
        ))
        total_debit += goodwill_val

    # --- 贷方行 ---
    if lte_investment > 0:
        lines.append(EliminationEntryLine(
            account_code="1503",
            account_name="长期股权投资",
            debit_amount=Decimal("0"),
            credit_amount=lte_investment,
        ))
        total_credit += lte_investment

    if minority_equity > 0:
        lines.append(EliminationEntryLine(
            account_code="3003",
            account_name="少数股东权益",
            debit_amount=Decimal("0"),
            credit_amount=minority_equity,
        ))
        total_credit += minority_equity

    # 写入数据库
    description = f"权益抵消（子公司 {subsidiary}，年度 {year}）"
    for line in lines:
        db.add(EliminationEntry(
            project_id=project_id,
            year=year,
            entry_no=entry_no,
            entry_type=EliminationEntryType.equity,
            description=description,
            account_code=line.account_code,
            account_name=line.account_name,
            debit_amount=line.debit_amount,
            credit_amount=line.credit_amount,
            entry_group_id=group_id,
            related_company_codes=[subsidiary],
            is_continuous=False,
            review_status=ReviewStatusEnum.draft,
        ))

    db.commit()

    return {
        "entry_group_id": str(group_id),
        "entry_no": entry_no,
        "description": description,
        "lines": [
            {"account_code": l.account_code, "account_name": l.account_name,
             "debit_amount": str(l.debit_amount), "credit_amount": str(l.credit_amount)}
            for l in lines
        ],
        "goodwill_amount": str(goodwill_val),
        "minority_equity_amount": str(minority_equity),
        "total_debit": str(total_debit),
        "total_credit": str(total_credit),
    }
