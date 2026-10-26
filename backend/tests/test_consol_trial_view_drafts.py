"""合并试算页读时视图扩展（spec consol-autotree-linkage-closure R5.1 / R8.5 / R10.1 / R10.3）。

真 SQLite + 真 ORM 行 + 真 service（夹具复用 ``test_consol_push``：G ⊃ A ⊃ A1、G ⊃ B 的合成集团）。

- 「含草稿预览」列 = 已审批 + 草稿 + 待审批分录的合并数（已驳回不计）；合并审定数仍只认已审批；
- ``node_kind / node_role``：任一节点（汇总 / 差额 / 数据）都能看；
- ``balance``：节点合并数按科目自然方向分借贷性质判平衡（个别数平衡、分录借贷相等 ⇒ 平衡）；
- 穿透：分录明细带类型中文与说明；个别数明细带所属上级；合并审定数列给完整构成（审定汇总 + 分录 = 合并数）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.audit_platform_models import AccountCategory
from app.models.base import UserRole
from app.models.consolidation_models import EliminationEntryType, ReviewStatusEnum
from tests.test_consol_push import (  # noqa: F401  夹具（factory / db / group / client_for）随导入注册
    Y,
    _entry,
    _tb,
    _User,
    client_for,
    db,
    factory,
    group,
)

D = Decimal


async def _entries(db, group):
    """G 层：已审批 IA-1（应付 50 / 应收 50）、草稿 IA-2（9）、待审批 IA-3（4）、已驳回 IA-4（100）。"""
    ar_ap = [("2202", "应付账款"), ("1122", "应收账款")]

    def lines(amount):
        return [(ar_ap[0][0], ar_ap[0][1], amount, "0"), (ar_ap[1][0], ar_ap[1][1], "0", amount)]

    db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap, lines("50")))
    db.add(_entry(group["G"], "IA-2", EliminationEntryType.internal_ar_ap, lines("9"), status=ReviewStatusEnum.draft))
    db.add(_entry(group["G"], "IA-3", EliminationEntryType.internal_ar_ap, lines("4"),
                  status=ReviewStatusEnum.pending_review))
    db.add(_entry(group["G"], "IA-4", EliminationEntryType.internal_ar_ap, lines("100"),
                  status=ReviewStatusEnum.rejected))
    await db.commit()


class TestDraftPreviewColumn:
    @pytest.mark.asyncio
    async def test_preview_counts_draft_and_pending_not_rejected(self, db, group):
        from app.services.consol_report_view_service import load_view_context, trial_view

        await _entries(db, group)
        ctx = await load_view_context(db, group["G"].id, Y, include_drafts=True)
        view = await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet", draft_basis=ctx.draft_basis)
        row = next(r for r in view["rows"] if r["row_code"] == "BS-006")
        # 应收：个别 400；已审批 −50 ⇒ 350；预览再减草稿 9 + 待审批 4（已驳回 100 不计）⇒ 337
        assert (row["consolidated"], row["consolidated_with_drafts"]) == ("350.00", "337.00")
        assert view["columns"][-1] == {"key": "consolidated_with_drafts", "label": "含草稿预览"}
        assert view["draft_pending_entries"] == 2
        plain = await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet")
        assert "consolidated_with_drafts" not in plain["rows"][0] and plain["draft_pending_entries"] is None


class TestNodeKindAndBalance:
    @pytest.mark.asyncio
    async def test_any_node_kind_and_balance(self, db, group):
        from app.services.consol_report_view_service import load_view_context, trial_view

        # 合成集团的个别数本身不平（G_s 借方性质 1350 对 实收资本 5000 等），根节点应如实报不平
        await _entries(db, group)
        ctx = await load_view_context(db, group["G"].id, Y)
        root = await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet")
        assert (root["node_kind"], root["node_role"]) == ("aggregate", "consol")
        assert root["balance"]["balanced"] is False, "合成集团个别数本身不平 ⇒ 如实报不平"
        elim = await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet", node_key="G:consol_elim")
        assert elim["node_kind"] == "elim"
        assert elim["balance"] == {"debit_total": "-50.00", "credit_total": "-50.00", "difference": "0.00",
                                   "balanced": True}, "分录借贷相等 ⇒ 差额节点按自然方向恒平"
        leaf = await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet", node_key="B:subsidiary")
        assert leaf["node_kind"] == "data" and leaf["balance"]["credit_total"] == "78.00"  # 应付 60 + 收入 7 + OCI 11

    @pytest.mark.asyncio
    async def test_balanced_group_reports_balanced(self, db, group):
        from app.services.consol_report_view_service import load_view_context, trial_view

        # 把 B 补平：借方性质补 78（成本 6401）⇒ B 自身平衡
        db.add(_tb(group["B"], "6401", "主营业务成本", AccountCategory.expense, "78"))
        await db.commit()
        ctx = await load_view_context(db, group["G"].id, Y)
        leaf = await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet", node_key="B:subsidiary")
        assert leaf["balance"] == {"debit_total": "78.00", "credit_total": "78.00", "difference": "0.00",
                                   "balanced": True}


class TestDrillCompleteness:
    @pytest.mark.asyncio
    async def test_entry_lines_labels_individual_parent_and_full_composition(self, db, group, client_for):
        await _entries(db, group)
        gid = str(group["G"].id)
        async with client_for(_User(UserRole.admin)) as c:
            trial = await c.get("/api/consolidation/worksheet/report-trial",
                                params={"project_id": gid, "report_type": "balance_sheet", "node_key": "A1:subsidiary"})
            assert trial.status_code == 200, trial.text
            assert trial.json()["node_kind"] == "data", "试算页可选任一节点（不限汇总节点）"
            drill = (await c.get("/api/consolidation/worksheet/drill/entries",
                                 params={"project_id": gid, "row_code": "BS-006", "measure": "consolidated"})).json()
            line = drill["lines"][0]
            assert (line["entry_no"], line["entry_type_label"], line["description"]) == ("IA-1", "内部往来抵销", None)
            assert [ln["entry_no"] for ln in drill["lines"]] == ["IA-1"], "穿透只计已审批"
            assert (drill["individual_total"], drill["total"], drill["consolidated_total"]) == ("400.00", "-50.00", "350.00")
            assert D(drill["individual_total"]) + D(drill["total"]) == D(drill["consolidated_total"])
            ind = (await c.get("/api/consolidation/worksheet/drill/individual",
                               params={"project_id": gid, "row_code": "BS-006"})).json()
            parents = {r["node_key"]: r["parent_label"] for r in ind["rows"]}
            assert parents["A1:subsidiary"] == parents["A:parent"] and parents["G:parent"] != parents["A1:subsidiary"]
