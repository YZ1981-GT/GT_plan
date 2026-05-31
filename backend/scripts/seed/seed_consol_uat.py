"""合并模块 UAT 合成集团种子脚本（封板交付物 ②）

在 **真实 PG** 中幂等创建一个最小合成合并集团，解锁合并四阶段「PG 0 个
consolidated 项目」导致的真实 UAT data-blocked 死结。

造数据内容：
- 1 个合并母项目（report_scope="consolidated", consolidation_type="subsidiary"）
- 2 个子项目（parent_project_id 指向母，report_scope="standalone"）
- 每个子项目若干 trial_balance 行（standard_account_code + audited_amount）
- 2 条 EliminationEntry（一条 draft、一条 approved）+ 1 条 InternalTrade
  → 让 B1 汇总 / 抵销 / breakdown 溯源都有可观测数据

幂等机制（IDEMPOTENT）：
- 用稳定确定的 client_name 作为业务键（母「【UAT】合成集团母公司」、子 A/B）。
- 每次运行先按 client_name 预查询 projects；存在则复用其 id（不新建、不重复）。
- trial_balance 按其唯一约束 (project_id, year, company_code, standard_account_code)
  预查询去重；EliminationEntry 按 (project_id, year, entry_no) 去重。
- 打印「created / skipped」明细，重复运行不会产生重复行。

用法：
    python backend/scripts/seed/seed_consol_uat.py            # 真实写入 PG
    python backend/scripts/seed/seed_consol_uat.py --dry-run  # 只打印计划，不连库、不写入
    python backend/scripts/seed/seed_consol_uat.py --year 2024 # 指定年度（默认 2025）

注意：真实写入需要 live PG（先跑 start-dev.bat / docker 起 audit-postgres）。
--dry-run 不连接数据库，可离线验证脚本逻辑。
运行后会打印母项目 project_id + year，供 UAT 操作员填入 Playwright 环境变量
CONSOL_PROJECT_ID / CONSOL_YEAR。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

# 允许以脚本方式直接运行（scripts 非包），把 backend/ 加入 sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_YEAR = 2025

# 稳定业务键（幂等去重锚点）——切勿随意改名，否则重复运行会造重复集团
PARENT_NAME = "【UAT】合成集团母公司"
PARENT_CODE = "UAT_GRP_PARENT"
CHILD_A_NAME = "【UAT】子公司A"
CHILD_A_CODE = "UAT_SUB_A"
CHILD_B_NAME = "【UAT】子公司B"
CHILD_B_CODE = "UAT_SUB_B"


# ---------------------------------------------------------------------------
# 计划数据结构（纯数据，无 DB —— 便于 --dry-run 离线构建/打印）
# ---------------------------------------------------------------------------


@dataclass
class TBSpec:
    code: str
    name: str
    category: str  # AccountCategory 成员名: asset/liability/equity/revenue/expense
    amount: str    # str(Decimal)，无 float 中转


@dataclass
class ElimSpec:
    entry_no: str
    entry_type: str        # EliminationEntryType 成员名
    review_status: str     # ReviewStatusEnum 成员名: draft/approved
    account_code: str
    debit: str
    credit: str
    description: str
    lines: list[dict] = field(default_factory=list)


@dataclass
class ChildSpec:
    name: str
    company_code: str
    tb_rows: list[TBSpec]


@dataclass
class GroupPlan:
    year: int
    parent_name: str
    parent_code: str
    children: list[ChildSpec]
    eliminations: list[ElimSpec]


def build_plan(year: int) -> GroupPlan:
    """构建合成集团造数计划（纯函数，无 DB）。"""
    child_a = ChildSpec(
        name=CHILD_A_NAME,
        company_code=CHILD_A_CODE,
        tb_rows=[
            TBSpec("1001", "货币资金", "asset", "1200000.00"),
            TBSpec("1122", "应收账款", "asset", "300000.00"),   # 对子B内部往来
            TBSpec("1601", "累计折旧", "asset", "-150000.00"),  # 负数科目
            TBSpec("6001", "营业收入", "revenue", "800000.00"), # 含对子B内部销售
        ],
    )
    child_b = ChildSpec(
        name=CHILD_B_NAME,
        company_code=CHILD_B_CODE,
        tb_rows=[
            TBSpec("1001", "货币资金", "asset", "450000.00"),
            TBSpec("2202", "应付账款", "liability", "300000.00"),  # 对子A内部往来
            TBSpec("1601", "累计折旧", "asset", "-60000.00"),
            TBSpec("6401", "营业成本", "expense", "500000.00"),    # 含对子A内部采购
        ],
    )

    eliminations = [
        # ① 已审批：内部销售收入抵销（approved → 应被 recalculate_trial 消费）
        ElimSpec(
            entry_no="UAT-ELIM-01",
            entry_type="internal_trade",
            review_status="approved",
            account_code="6001",
            debit="200000.00",
            credit="0",
            description="抵销子A对子B内部销售收入",
            lines=[
                {"account_code": "6001", "debit_amount": "200000.00", "credit_amount": "0"},
                {"account_code": "6401", "debit_amount": "0", "credit_amount": "200000.00"},
            ],
        ),
        # ② 草稿：内部往来抵销（draft → 不应被消费，验证 APPROVED-only 过滤）
        ElimSpec(
            entry_no="UAT-ELIM-02",
            entry_type="internal_ar_ap",
            review_status="draft",
            account_code="1122",
            debit="0",
            credit="300000.00",
            description="抵销子A应收子B（草稿，未审批不生效）",
            lines=[
                {"account_code": "1122", "debit_amount": "0", "credit_amount": "300000.00"},
                {"account_code": "2202", "debit_amount": "300000.00", "credit_amount": "0"},
            ],
        ),
    ]

    return GroupPlan(
        year=year,
        parent_name=PARENT_NAME,
        parent_code=PARENT_CODE,
        children=[child_a, child_b],
        eliminations=eliminations,
    )


def print_plan(plan: GroupPlan) -> None:
    """打印造数计划（--dry-run 用，无 DB）。"""
    print("=" * 64)
    print("【DRY-RUN】合并 UAT 合成集团造数计划（不写入数据库）")
    print("=" * 64)
    print(f"年度: {plan.year}")
    print(f"母项目: {plan.parent_name}  (company_code={plan.parent_code}, "
          f"report_scope=consolidated, consolidation_type=subsidiary)")
    for child in plan.children:
        print(f"\n  子项目: {child.name}  (company_code={child.company_code}, "
              f"report_scope=standalone, parent_project_id→母)")
        for tb in child.tb_rows:
            print(f"      TB {tb.code} {tb.name:<8} [{tb.category}] audited={tb.amount}")
    print(f"\n  抵销分录（{len(plan.eliminations)} 条）:")
    for e in plan.eliminations:
        print(f"      {e.entry_no} [{e.entry_type}/{e.review_status}] "
              f"{e.account_code} 借{e.debit}/贷{e.credit} — {e.description}")
    print("\n（dry-run 结束，未连接数据库、未写入任何行）")
    print("=" * 64)


# ---------------------------------------------------------------------------
# 真实写入（幂等 upsert，需 live PG）
# ---------------------------------------------------------------------------


async def seed(plan: GroupPlan) -> dict:
    """幂等写入合成集团到真实数据库。返回统计 + 母项目 id。"""
    import sqlalchemy as sa

    from app.core.database import async_session
    from app.models.audit_platform_models import AccountCategory, TrialBalance
    from app.models.base import UserRole
    from app.models.consolidation_models import (
        EliminationEntry,
        EliminationEntryType,
        InternalTrade,
        ReviewStatusEnum,
        TradeType,
    )
    from app.models.core import Project, User

    stats = {"created": [], "skipped": []}

    async def _get_project_by_name(db, name: str) -> "Project | None":
        res = await db.execute(
            sa.select(Project).where(
                Project.client_name == name,
                Project.is_deleted == sa.false(),
            )
        )
        return res.scalars().first()

    async with async_session() as db:
        # ── 0) 造一个 UAT 负责人 user（幂等：按 username）────────────────────
        uat_username = "uat_consol_seed"
        res = await db.execute(sa.select(User).where(User.username == uat_username))
        user = res.scalars().first()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                username=uat_username,
                email="uat_consol_seed@uat.local",
                hashed_password="!uat-seed-not-loginable!",
                role=UserRole.admin,
            )
            db.add(user)
            await db.flush()
            stats["created"].append(f"user:{uat_username}")
        else:
            stats["skipped"].append(f"user:{uat_username}")

        # ── 1) 母项目（幂等：按 client_name）─────────────────────────────────
        parent = await _get_project_by_name(db, plan.parent_name)
        if parent is None:
            parent = Project(
                id=uuid.uuid4(),
                name=plan.parent_name,
                client_name=plan.parent_name,
                company_code=plan.parent_code,
                ultimate_company_code=plan.parent_code,
                report_scope="consolidated",
                consolidation_type="subsidiary",
                consol_level=2,
                manager_id=user.id,
            )
            db.add(parent)
            await db.flush()
            stats["created"].append(f"parent_project:{plan.parent_name}")
        else:
            stats["skipped"].append(f"parent_project:{plan.parent_name}")

        # ── 2) 子项目 + trial_balance（幂等）─────────────────────────────────
        for child_spec in plan.children:
            child = await _get_project_by_name(db, child_spec.name)
            if child is None:
                child = Project(
                    id=uuid.uuid4(),
                    name=child_spec.name,
                    client_name=child_spec.name,
                    company_code=child_spec.company_code,
                    parent_company_code=plan.parent_code,
                    ultimate_company_code=plan.parent_code,
                    parent_project_id=parent.id,
                    report_scope="standalone",
                    consol_level=1,
                    manager_id=user.id,
                )
                db.add(child)
                await db.flush()
                stats["created"].append(f"child_project:{child_spec.name}")
            else:
                # 确保父子关系正确（修正历史脏数据）
                if child.parent_project_id != parent.id:
                    child.parent_project_id = parent.id
                stats["skipped"].append(f"child_project:{child_spec.name}")

            # trial_balance 行（按唯一键去重）
            existing = await db.execute(
                sa.select(TrialBalance.standard_account_code).where(
                    TrialBalance.project_id == child.id,
                    TrialBalance.year == plan.year,
                    TrialBalance.company_code == child_spec.company_code,
                )
            )
            existing_codes = {row[0] for row in existing.all()}
            for tb in child_spec.tb_rows:
                if tb.code in existing_codes:
                    stats["skipped"].append(f"tb:{child_spec.company_code}/{tb.code}")
                    continue
                db.add(TrialBalance(
                    id=uuid.uuid4(),
                    project_id=child.id,
                    year=plan.year,
                    company_code=child_spec.company_code,
                    standard_account_code=tb.code,
                    account_name=tb.name,
                    account_category=AccountCategory[tb.category],
                    audited_amount=Decimal(tb.amount),
                    is_deleted=False,
                ))
                stats["created"].append(f"tb:{child_spec.company_code}/{tb.code}")

        # ── 3) 抵销分录（幂等：按 entry_no）─────────────────────────────────
        existing_elim = await db.execute(
            sa.select(EliminationEntry.entry_no).where(
                EliminationEntry.project_id == parent.id,
                EliminationEntry.year == plan.year,
            )
        )
        existing_entry_nos = {row[0] for row in existing_elim.all()}
        for e in plan.eliminations:
            if e.entry_no in existing_entry_nos:
                stats["skipped"].append(f"elim:{e.entry_no}")
                continue
            db.add(EliminationEntry(
                id=uuid.uuid4(),
                project_id=parent.id,
                year=plan.year,
                entry_no=e.entry_no,
                entry_type=EliminationEntryType[e.entry_type],
                description=e.description,
                account_code=e.account_code,
                debit_amount=Decimal(e.debit),
                credit_amount=Decimal(e.credit),
                lines=e.lines,
                entry_group_id=uuid.uuid4(),
                review_status=ReviewStatusEnum[e.review_status],
                is_deleted=False,
            ))
            stats["created"].append(f"elim:{e.entry_no}")

        # ── 4) 内部交易 1 条（幂等：按 seller/buyer/year 预查）──────────────
        res = await db.execute(
            sa.select(InternalTrade).where(
                InternalTrade.project_id == parent.id,
                InternalTrade.year == plan.year,
                InternalTrade.seller_company_code == CHILD_A_CODE,
                InternalTrade.buyer_company_code == CHILD_B_CODE,
            )
        )
        if res.scalars().first() is None:
            db.add(InternalTrade(
                id=uuid.uuid4(),
                project_id=parent.id,
                year=plan.year,
                seller_company_code=CHILD_A_CODE,
                buyer_company_code=CHILD_B_CODE,
                trade_type=TradeType.goods,
                trade_amount=Decimal("200000.00"),
                cost_amount=Decimal("150000.00"),
                unrealized_profit=Decimal("50000.00"),
                description="子A向子B销售商品（UAT 合成内部交易）",
            ))
            stats["created"].append("internal_trade:A→B")
        else:
            stats["skipped"].append("internal_trade:A→B")

        await db.commit()
        parent_id = str(parent.id)

    return {"stats": stats, "parent_id": parent_id, "year": plan.year}


def _print_result(result: dict) -> None:
    stats = result["stats"]
    print("=" * 64)
    print("合并 UAT 合成集团种子写入完成")
    print("=" * 64)
    print(f"新建 ({len(stats['created'])}):")
    for c in stats["created"]:
        print(f"  + {c}")
    print(f"跳过/已存在 ({len(stats['skipped'])}):")
    for s in stats["skipped"]:
        print(f"  = {s}")
    print("-" * 64)
    print(f"母项目 project_id = {result['parent_id']}")
    print(f"年度 year         = {result['year']}")
    print("\nUAT 操作员请设置 Playwright 环境变量：")
    print(f"  CONSOL_PROJECT_ID={result['parent_id']}")
    print(f"  CONSOL_YEAR={result['year']}")
    print("=" * 64)


def main() -> None:
    parser = argparse.ArgumentParser(description="合并模块 UAT 合成集团幂等种子脚本")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印造数计划，不连接数据库、不写入")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR,
                        help=f"报告年度（默认 {DEFAULT_YEAR}）")
    args = parser.parse_args()

    plan = build_plan(args.year)

    if args.dry_run:
        print_plan(plan)
        return

    result = asyncio.run(seed(plan))
    _print_result(result)


if __name__ == "__main__":
    main()
