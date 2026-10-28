"""合并抵销分录汇总表同源重写（spec consol-autotree-linkage-closure R9 / R5.2，design §3.7）。

真 SQLite + 真 ORM 行 + 真 service（夹具复用 ``test_consol_push``：G ⊃ A ⊃ A1、G ⊃ B 的合成集团）。

🔴 旧实现：另一条 SQL 只按类型分组、只看本项目、不认归属，``other`` 的标签键写成 ``other_adjustment``。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.base import UserRole
from app.models.consolidation_models import EliminationEntryType as T, ReviewStatusEnum as S
from tests.test_consol_push import (  # noqa: F401  夹具（factory / db / group / client_for）随导入注册
    Y,
    _entry,
    _User,
    client_for,
    db,
    factory,
    group,
)

D = Decimal
AR_AP = [("2202", "应付账款", "50", "0"), ("1122", "应收账款", "0", "50")]


async def _summary(db, project):
    from app.services.consol_entry_summary_service import entry_summary

    return await entry_summary(db, project.id, Y)


def _row(res, node_key, account, entry_type):
    return next(r for r in res["rows"] if (r["node_key"], r["account_code"], r["entry_type"]) == (node_key, account, entry_type))


class TestSameSourceRows:
    @pytest.mark.asyncio
    async def test_node_account_type_rows_with_natural_direction_net(self, db, group):
        db.add(_entry(group["G"], "IA-1", T.internal_ar_ap, AR_AP))
        db.add(_entry(group["G"], "IA-2", T.internal_ar_ap, [("2202", "应付账款", "9", "0"), ("1122", "应收账款", "0", "9")],
                      status=S.draft))
        db.add(_entry(group["G"], "OT-1", T.other, [("6001", "主营业务收入", "0", "5"), ("1001", "货币资金", "5", "0")]))
        db.add(_entry(group["A"], "IT-1", T.internal_trade, [("6001", "主营业务收入", "30", "0"), ("6401", "主营业务成本", "0", "30")]))
        db.add(_entry(group["G"], "XX-1", T.internal_ar_ap, AR_AP, status=S.rejected))
        await db.commit()
        res = await _summary(db, group["G"])
        ar = _row(res, "G:consol_elim", "1122", "internal_ar_ap")
        ap = _row(res, "G:consol_elim", "2202", "internal_ar_ap")
        assert (ar["debit"], ar["credit"], ar["net"], ar["draft_net"]) == ("0.00", "50.00", "-50.00", "-59.00")
        assert (ap["net"], ap["entry_count"], ap["type_label"], ap["measure"], ap["hosted_here"]) == \
            ("-50.00", 1, "内部往来抵销", "elim_trade", True)
        other = _row(res, "G:consol_elim", "6001", "other")
        assert (other["type_label"], other["measure"], other["net"]) == ("其他调整", "adjustment", "5.00"), \
            "🔴 旧标签键 other_adjustment 与枚举 other 对不上"
        sub = _row(res, "A:consol_elim", "6001", "internal_trade")
        assert sub["hosted_here"] is False and sub["net"] == "-30.00", "下级合并项目承载的差额节点也计入（树内全部）"
        assert [t["entry_type"] for t in res["by_type"]] == ["internal_ar_ap", "internal_trade", "other"]
        assert next(t for t in res["by_type"] if t["entry_type"] == "internal_ar_ap")["entry_count"] == 1, \
            "笔数按分录去重（一笔两行算 1 笔）；已驳回 / 草稿不计"
        assert res["totals"]["balanced"] is True and res["totals"]["entry_count"] == 3
        assert res["reconcile"]["matched"] is True and res["reconcile"]["mismatches"] == []

    @pytest.mark.asyncio
    async def test_draft_only_rows_listed(self, db, group):
        db.add(_entry(group["G"], "IT-9", T.internal_trade, [("6001", "主营业务收入", "8", "0"), ("6401", "主营业务成本", "0", "8")],
                      status=S.pending_review))
        await db.commit()
        res = await _summary(db, group["G"])
        row = _row(res, "G:consol_elim", "6001", "internal_trade")
        assert (row["net"], row["draft_net"], row["entry_count"]) == ("0.00", "-8.00", 0)


class TestReconcileOrphansWarnings:
    @pytest.mark.asyncio
    async def test_persisted_stale_until_recalculated(self, db, group):
        from app.services.consol_trial_service import recalculate_trial

        db.add(_entry(group["G"], "IA-1", T.internal_ar_ap, AR_AP))
        await db.commit()
        before = await _summary(db, group["G"])
        assert before["reconcile"]["persisted_stale"] is True and before["reconcile"]["stale_accounts"] == ["1122", "2202"]
        assert any("请重新推送" in w for w in before["warnings"])
        await recalculate_trial(db, group["G"].id, Y)
        await db.commit()
        after = await _summary(db, group["G"])
        assert after["reconcile"]["persisted_stale"] is False and not any("请重新推送" in w for w in after["warnings"])

    @pytest.mark.asyncio
    async def test_orphans_listed_not_counted_and_direction_warning(self, db, group):
        db.add(_entry(group["G"], "OR-1", T.internal_ar_ap, AR_AP, branch="B"))  # B 没有分公司 ⇒ 无母分差额节点
        db.add(_entry(group["G"], "WR-1", T.internal_ar_ap,
                      [("1122", "应收账款", "7", "0"), ("2202", "应付账款", "0", "7")]))  # 方向录反
        db.add(_entry(group["G"], "OK-1", T.internal_ar_ap, AR_AP))
        await db.commit()
        res = await _summary(db, group["G"])
        assert [o["entry_no"] for o in res["orphans"]] == ["OR-1"] and "没有母分差额节点" in res["orphans"][0]["reason"]
        assert res["orphans"][0]["review_status_label"] == "已审批"
        assert _row(res, "G:consol_elim", "1122", "internal_ar_ap")["entry_count"] == 2, "孤儿不计入"
        direction = [w for w in res["warnings"] if "方向可能录反" in w]
        assert len(direction) == 1 and "WR-1" in direction[0] and "内部往来抵销" in direction[0]

    def test_system_dict_labels_match_entry_enum(self):
        """系统字典「抵销分录类型」与分录枚举标签同一口径（R9.3：``other`` = 其他调整，进调整列）。"""
        from app.routers.system_dicts import _DICTS
        from app.services.consol_elimination_sheet_service import ENTRY_TYPE_LABELS

        labels = {d["value"]: d["label"] for d in _DICTS["elimination_entry_type"]}
        assert labels == ENTRY_TYPE_LABELS, "两处标签不一致 ⇒ 字典页 / 汇总表 / 试算穿透对同一类型叫法不同"
        assert labels["other"] == "其他调整"

    @pytest.mark.asyncio
    async def test_endpoint(self, db, group, client_for):
        db.add(_entry(group["G"], "IA-1", T.internal_ar_ap, AR_AP))
        await db.commit()
        async with client_for(_User(UserRole.admin)) as c:
            resp = await c.get("/api/consolidation/worksheet/entry-summary", params={"project_id": str(group["G"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) >= {"year", "rows", "by_type", "totals", "reconcile", "orphans", "warnings"}
        assert body["year"] == Y and D(body["totals"]["debit"]) == D(body["totals"]["credit"]) == D("50")
