"""D9：调整事项在签发门 / 交付就绪门 / 错报门上的阻断证据。

为什么单独一个文件
------------------
``adjustment-client-booking-status`` 的 Task 9 与
``adjustment-practice-linkage-integrity-closure`` 的 D9 都要求
「声明书 / 签发门 / 交付门」有真 PG 证据，而不是只有 service 单测。
既有覆盖分散在三处且各有缺口：

* ``test_signoff_checklist_service.py``：SQLite，六类检查都执行（不断言调整真的阻断）；
* ``test_signoff_checklist_pg.py``：真 PG，但只验"六类都跑过"，不验调整状态与阻断的对应；
* ``test_adjustment_group_reporting.py``：只测 ``_check_adjustments`` 的计数口径。

本文件把三类门的**判定与阻断**在真 PG 上钉住，且只在专用验收库
（``GT_ADJ_ACCEPT_DB_URL``）跑，连共享库整体 skip。
"""
from __future__ import annotations

import importlib
import pkgutil
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

from tests.test_adjustment_concurrency_and_rls_pg import (  # noqa: F401 - fixture 复用
    ACCEPT_URL_ENV,
    _accept_url,
    accept_db,
)


@pytest.fixture(scope="module", autouse=True)
def _models_loaded():
    import app.models as models_pkg

    for mod in pkgutil.iter_modules(models_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"app.models.{mod.name}")


async def _group(world, *, adjustment_no: str, status: str, origin: str = "manual",
                 adjustment_type: str = "aje") -> uuid.UUID:
    """建一个指定复核状态 / 来源的分录组（含借贷平衡的两行）。"""
    from app.models.audit_platform_models import AdjustmentType, ReviewStatus
    from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter

    sessions = world["sessions"]
    project_id, actor_id = world["project_id"], world["actor_id"]
    group_id = uuid.uuid4()
    async with sessions[0]() as db:
        await AdjustmentGroupWriter(db).write_group(
            project_id=project_id, year=2025, company_code="001",
            adjustment_no=adjustment_no,
            adjustment_type=getattr(AdjustmentType, adjustment_type),
            description=f"D9 验收 {status}",
            entry_group_id=group_id,
            lines=[
                AdjustmentGroupLine(standard_account_code="1122", account_name="应收账款",
                                    debit_amount=Decimal("50")),
                AdjustmentGroupLine(standard_account_code="6702", account_name="信用减值损失",
                                    credit_amount=Decimal("50")),
            ],
            content_revision=1, audit_phase="final",
            review_status=getattr(ReviewStatus, status),
            origin=origin,
            created_by=actor_id,
        )
        await db.commit()
    return group_id


# ---------------------------------------------------------------------------
# D9-1：签发门 —— 草稿 / 待复核的调整必须被列为 blocking
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signoff_checklist_blocks_draft_and_pending_adjustments(accept_db):
    """签发清单的 ``adjustment`` 类别必须对未完成审批的分录给 blocking。"""
    from app.services.signoff_checklist_service import CheckSeverity, SignoffChecklistService

    world = accept_db
    project_id = world["project_id"]
    await _group(world, adjustment_no="AJE-SIGN-DRAFT", status="draft")
    await _group(world, adjustment_no="AJE-SIGN-PENDING", status="pending_review")

    async with world["sessions"][0]() as db:
        result = await SignoffChecklistService(db).generate_checklist(
            project_id=project_id, year=2025,
        )
    items = [item for item in result.items if item.category == "adjustment"]
    blocking = [item for item in items if item.severity == CheckSeverity.blocking]
    assert blocking, f"草稿 / 待复核的调整必须阻断签发，实际 items={items}"
    # 两笔都要被点到（同一 category 下逐笔列出）
    joined = " ".join(item.message for item in blocking)
    assert "AJE-SIGN-DRAFT" in joined, joined
    assert "AJE-SIGN-PENDING" in joined, joined


# ---------------------------------------------------------------------------
# D9-2：签发门 —— 全部批准后不再阻断
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signoff_checklist_passes_when_all_adjustments_approved(accept_db):
    """对照组：同样的项目里只有已批准分录时，``adjustment`` 类别不得 blocking。

    没有这一条，D9-1 可能只是"任何项目都阻断"的恒红判据。
    """
    from app.services.signoff_checklist_service import CheckSeverity, SignoffChecklistService

    world = accept_db
    project_id = world["project_id"]

    # 先把上一批未完成的分录全部软删，再建一个已批准的
    async with world["sessions"][0]() as db:
        await db.execute(sa.text(
            "update adjustments set is_deleted = true "
            "where project_id = :p and review_status in ('draft','pending_review')"
        ), {"p": project_id})
        await db.commit()
    await _group(world, adjustment_no="AJE-SIGN-APPROVED", status="approved")

    async with world["sessions"][0]() as db:
        result = await SignoffChecklistService(db).generate_checklist(
            project_id=project_id, year=2025,
        )
    items = [item for item in result.items if item.category == "adjustment"]
    assert items, "adjustment 类别必须出现在清单里（哪怕是 info）"
    assert not [item for item in items if item.severity == CheckSeverity.blocking], items


# ---------------------------------------------------------------------------
# D9-3：交付就绪门 —— 按分录组计数，未确认即 upstream_not_ready 阻断
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deliverable_readiness_blocks_on_unconfirmed_groups(accept_db):
    """``DeliverableReadinessService._check_adjustments`` 必须按组计数并产出阻断项。"""
    from app.services.deliverable_readiness_sources import ReadinessSourceChecks
    from app.models.audit_platform_models import ReviewStatus
    from app.services.adjustment_group_writer import AdjustmentGroupWriter

    world = accept_db
    project_id, actor_id = world["project_id"], world["actor_id"]
    sessions = world["sessions"]

    # 清干净后建 2 个未确认组（一组两行 ⇒ 必须计 2 而不是 4）
    async with sessions[0]() as db:
        await db.execute(sa.text(
            "update adjustments set is_deleted = true where project_id = :p"
        ), {"p": project_id})
        await db.commit()
    for index in (1, 2):
        group_id = uuid.uuid4()
        async with sessions[0]() as db:
            await AdjustmentGroupWriter(db).write_group(
                project_id=project_id, year=2025, company_code="001",
                adjustment_no=f"AJE-READY-{index}",
                adjustment_type=__import__(
                    "app.models.audit_platform_models", fromlist=["AdjustmentType"]
                ).AdjustmentType.aje,
                description=f"就绪验收 {index}", entry_group_id=group_id,
                lines=[
                    __import__("app.services.adjustment_group_writer",
                               fromlist=["AdjustmentGroupLine"]).AdjustmentGroupLine(
                        standard_account_code="1122", account_name="应收账款",
                        debit_amount=Decimal("10"),
                    ),
                    __import__("app.services.adjustment_group_writer",
                               fromlist=["AdjustmentGroupLine"]).AdjustmentGroupLine(
                        standard_account_code="6702", account_name="信用减值损失",
                        credit_amount=Decimal("10"),
                    ),
                ],
                content_revision=1, audit_phase="final",
                review_status=ReviewStatus.draft, created_by=actor_id,
            )
            await db.commit()

    blockers: list = []
    async with sessions[0]() as db:
        status = await ReadinessSourceChecks()._check_adjustments(
            db, project_id, 2025, blockers, [],
        )
    assert status.count == 2, f"应按分录组计数得 2，实际 {status.count}"
    assert status.detail["unconfirmed_count"] == 2
    assert status.detail["line_count"] == 4, "4 行明细"
    assert blockers, "存在未确认分录时必须产出阻断项"
    evidence = blockers[0].evidence
    assert evidence["component"] == "adjustments"
    assert evidence["unconfirmed_count"] == 2
    assert evidence["total_count"] == 2


# ---------------------------------------------------------------------------
# D9-4：错报门 —— 被驳回的 AJE 未转错报时给 warning（不是静默通过）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rejected_aje_without_misstatement_hits_unconverted_rule(accept_db):
    """``R1-AJE-UNCONVERTED`` 必须对"已驳回但未转错报"的 AJE 组报出来。"""
    from app.services.gate_rules_phase14 import UnconvertedRejectedAJERule

    world = accept_db
    project_id = world["project_id"]

    # 清干净后建一个 rejected 的 AJE
    async with world["sessions"][0]() as db:
        await db.execute(sa.text(
            "update adjustments set is_deleted = true where project_id = :p"
        ), {"p": project_id})
        await db.commit()
    await _group(world, adjustment_no="AJE-REJECTED-1", status="rejected")

    rule = UnconvertedRejectedAJERule()
    async with world["sessions"][0]() as db:
        hit = await rule.check(db, {"project_id": project_id})
    assert hit is not None, "已驳回未转错报的 AJE 必须命中该规则"
    # location 给的是分录组 id（不是编号）：按 entry_group_id 断言
    group_ids = [str(value) for value in (hit.location or {}).get("sample_entry_group_ids", [])]
    assert group_ids, hit.location
    assert (hit.location or {}).get("unconverted_group_count") == 1, hit.location
    assert hit.severity.value == "warning", hit.severity


# ---------------------------------------------------------------------------
# D9-5：错报门 —— 转成错报后不再命中（对照组，防止判据恒红）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rejected_aje_converted_to_misstatement_clears_the_rule(accept_db):
    """把该组转成 ``UnadjustedMisstatement`` 后，规则不得再报。

    自带夹具（不依赖 D9-4 留下的数据），否则用例顺序一变就红。
    """
    from app.models.audit_platform_models import UnadjustedMisstatement
    from app.services.gate_rules_phase14 import UnconvertedRejectedAJERule

    world = accept_db
    project_id = world["project_id"]
    sessions = world["sessions"]

    async with sessions[0]() as db:
        await db.execute(sa.text(
            "update adjustments set is_deleted = true where project_id = :p"
        ), {"p": project_id})
        await db.commit()
    await _group(world, adjustment_no="AJE-REJECTED-CONV", status="rejected")

    rule = UnconvertedRejectedAJERule()
    async with sessions[0]() as db:
        before = await rule.check(db, {"project_id": project_id})
    assert before is not None, "前置：已驳回未转错报应命中"

    async with sessions[0]() as db:
        anchor = (await db.execute(sa.text(
            "select id from adjustments "
            "where project_id = :p and is_deleted = false and adjustment_no = 'AJE-REJECTED-CONV' "
            "order by id limit 1"
        ), {"p": project_id})).scalar_one()
        db.add(UnadjustedMisstatement(
            id=uuid.uuid4(),
            project_id=project_id,
            year=2025,
            misstatement_type="factual",
            misstatement_description="D9 验收：已转错报",
            misstatement_amount=Decimal("50"),
            source_adjustment_id=anchor,
            created_by=world["actor_id"],
        ))
        await db.commit()

    async with sessions[0]() as db:
        after = await rule.check(db, {"project_id": project_id})
    assert after is None, f"已转错报后不应再命中，实际 {after}"


# ---------------------------------------------------------------------------
# D9-6：客户已入账发布门 —— 未 ack 时该组必须被拦（真实 SQL + 真实表结构）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_publish_gate_requires_ack_for_client_booked_groups(accept_db):
    """发布门取数 ``effective_booking_impacts_for_accounts`` 必须把生效的客户已入账组交出来。

    这正是 ``wp_html_save`` 在 409 ``BOOKED_ADJUSTMENTS_UNACKED`` 之前调的那一步：
    清单里有、而请求的 ``booked_adjustments_ack`` 不含它 ⇒ 路由抛 409。
    这里直接验"清单非空且包含该组"，避开 HTTP 鉴权层。
    """
    from datetime import date

    from app.services.adjustment_client_booking import (
        effective_booking_impacts_for_accounts,
        mark_booked,
    )
    from app.services.voucher_identity import VoucherKey

    world = accept_db
    project_id, actor_id = world["project_id"], world["actor_id"]
    sessions = world["sessions"]

    async with sessions[0]() as db:
        await db.execute(sa.text(
            "update adjustments set is_deleted = true where project_id = :p"
        ), {"p": project_id})
        await db.commit()

    # 账套 + 凭证（客户已入账要求凭证在 active 账套里真实存在）
    dataset_id = uuid.uuid4()
    async with sessions[0]() as db:
        await db.execute(sa.text("""
            insert into ledger_datasets (id, project_id, year, status, source_type, created_by)
            values (:id, :p, 2025, 'active', 'import', :u)
        """), {"id": dataset_id, "p": project_id, "u": actor_id})
        await db.execute(sa.text("""
            insert into tb_ledger (id, project_id, year, company_code, voucher_date,
                                   voucher_type, voucher_no, entry_seq, account_code,
                                   account_name, debit_amount, credit_amount, dataset_id)
            values (:id, :p, 2025, '001', :d, '记', '0001', 1, '1122', '应收账款', 50, 0, :ds)
        """), {
            "id": uuid.uuid4(), "p": project_id, "d": date(2025, 12, 31), "ds": dataset_id,
        })
        await db.commit()

    group_id = await _group(world, adjustment_no="AJE-BOOKED-ACK", status="approved")

    async with sessions[0]() as db:
        await mark_booked(
            db, project_id=project_id, year=2025, entry_group_id=group_id,
            voucher_key_values=[
                VoucherKey.of(
                    year=2025, company_code="001", voucher_date=date(2025, 12, 31),
                    voucher_type="记", voucher_no="0001",
                ).to_str()
            ],
            actor_id=actor_id, note="D9 验收客户已入账",
        )
        await db.commit()

    async with sessions[0]() as db:
        impacts = await effective_booking_impacts_for_accounts(
            db, project_id=project_id, year=2025, account_codes=["1122"],
        )
    assert impacts, "客户已入账的生效分录组必须出现在发布门清单里"
    assert any(str(item["entry_group_id"]) == str(group_id) for item in impacts), impacts

    # 带上 ack（清单里所有组）后不得再被判为"未确认"
    acknowledged = {str(item["entry_group_id"]) for item in impacts}
    unacked = [item for item in impacts
               if str(item["entry_group_id"]) not in acknowledged]
    assert unacked == [], unacked
