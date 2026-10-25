"""合并抵消分录明细表后端（spec consol-elimination-single-source-push 任务 6，design §九 / §十二）。

- 科目映射（纯函数）：本集团科目优先 → 合并报表单科目行 → 标准科目表；别名、「（或…）」、行首标记、明细子科目 /
  父科目兜底；同名多码取落在报表取数范围内的；权益变动表项目与少数股东权益不映射并给原因；
- 生成计划（纯函数）：负金额换向、零金额行跳过、方向 / 金额认不出、借贷不平、类型与来源不符 ⇒ 不生成并给原因；
- P6 幂等：同输入两次 ⇒ 第二次 ``created=0 updated=0``；P7 已审批分录不被改写，来源消失也不删；
- 草稿随来源更新（同一笔分录）、来源不再产出 ⇒ 软删（只动声明负责的来源）、已驳回且来源没变 ⇒ 不推翻驳回；
- 明细行：全树分录（下级合并项目的只读）、计入 == 已审批且归属成功、孤儿与坏明细行给原因、三行合计；
- 旧版明细表：自定义行识别、按借贷平衡切分、转入幂等、删除后不转回；
- 端点：真发请求，固定路径不被 ``/{entry_id}`` 截走、非成员 403、只读成员不能写。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.base import PermissionLevel, UserRole
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum
from app.services.account_chart_service import standard_chart_entries
from app.services.consol_elimination_sheet_service import (
    ORIGIN_EQUITY_SIM,
    ORIGIN_INTERNAL_ARAP,
    ORIGIN_INTERNAL_TRADE,
    SheetError,
    SourceGroup,
    SourceLine,
    build_mapper,
    generate_from_worksheet,
    legacy_custom_rows,
    legacy_groups,
    legacy_sheet,
    plan_group,
    tree_lines,
)
from app.services.consol_report_values import ReportRow
from tests.test_consol_push import (  # noqa: F401  复用同一套集团与端点夹具
    Y,
    _entry,
    _persist,
    _User,
    client_for,
    db,
    factory,
    group,
)

D = Decimal

# ─────────────────────────────── 科目映射（纯函数） ───────────────────────────────

_ROWS = [
    ReportRow("balance_sheet", "BS-006", "应收账款", 1, "TB('1122','期末余额')"),
    ReportRow("balance_sheet", "BS-010", "存货", 2, "SUM_TB('1401~1499','期末余额')"),
    ReportRow("balance_sheet", "BS-024", "长期股权投资", 3, "TB('1511','期末余额')"),
    ReportRow("balance_sheet", "BS-034", "商誉", 4, "TB('1711','期末余额')"),
    ReportRow("balance_sheet", "BS-045", "应付账款", 5, "TB('2202','期末余额')"),
    ReportRow("balance_sheet", "BS-081", "实收资本（或股本）", 6, "TB('4001','期末余额')"),
    ReportRow("balance_sheet", "BS-083", "资本公积", 7, "TB('4002','期末余额')"),
    ReportRow("balance_sheet", "BS-088", "未分配利润", 8, "TB('4104','期末余额')"),
    ReportRow("balance_sheet", "BS-124", "△一般风险准备", 9, "TB('4102','期末余额')"),
    ReportRow("balance_sheet", "BS-090", "少数股东权益", 10, None),
    ReportRow("income_statement", "IS-001", "一、营业收入", 1, "SUM_TB('6001~6099','本期发生额')"),
    ReportRow("income_statement", "IS-002", "减：营业成本", 2, "SUM_TB('6401~6499','本期发生额')"),
    ReportRow("income_statement", "IS-011", "（一）加：投资收益", 3, "TB('6111','本期发生额')"),
    ReportRow("impairment_provision", "IMP-009", "八、长期股权投资减值准备", 1, "TB('1512','期末余额')"),
    ReportRow("impairment_provision", "IMP-012", "十一、在建工程减值准备", 2, "TB('1604','期末余额')"),  # 真库配错的行
]
_TREE = [
    ("1122", "应收账款"), ("2202", "应付账款"), ("6001", "营业收入"), ("6401", "主营业务成本"),
    ("1511", "长期股权投资"), ("4104", "利润分配"), ("3002", "资本公积"), ("1406", "库存商品"), ("1405", "库存商品"),
]


def _mapper(tree=_TREE, rows=_ROWS):
    return build_mapper(tree, standard_chart_entries(), rows, "soe_consolidated")


class TestSubjectMapper:
    @pytest.mark.parametrize(("subject", "detail", "code", "name", "source", "note"), [
        ("应收账款", None, "1122", "应收账款", "本集团科目", None),
        (" 应收 账款 ", None, "1122", "应收账款", "本集团科目", None),  # 空白（含全角）不影响
        ("营业收入", None, "6001", "营业收入", "本集团科目", None),       # 本集团同名科目优先于别名
        ("营业成本", None, "6401", "主营业务成本", "本集团科目", "按「主营业务成本」匹配"),
        ("年初未分配利润", None, "4104", "利润分配", "本集团科目", "按「利润分配」匹配"),
        ("存货", None, "1405", "库存商品", "本集团科目", "按「库存商品」匹配"),  # 同名两码：都在取数范围 ⇒ 小码
        ("投资收益", None, "6111", "投资收益", "合并报表行次", None),     # 本集团没有 ⇒ 报表单科目行（行首序号与「加：」去掉）
        ("实收资本（或股本）", None, "4001", "实收资本（或股本）", "合并报表行次", None),
        ("△一般风险准备", None, "4102", "一般风险准备", "合并报表行次", None),  # 行首标记两边都去掉
        ("商誉", None, "1711", "商誉", "合并报表行次", None),
        ("长期股权投资", "减值准备", "1512", "长期股权投资减值准备", "标准科目表", None),  # 「名称+明细」整体匹配
        ("长期股权投资", "损益调整", "1511", "长期股权投资-损益调整", "本集团科目",
         "明细「损益调整」没有对应子科目，按父科目 1511 入账"),
    ])
    def test_maps(self, subject, detail, code, name, source, note):
        m = _mapper().map(subject, detail)
        assert (m.account_code, m.account_name, m.source, m.note, m.reason) == (code, name, source, note, None)
        assert m.in_report and m.warning is None

    def test_tree_convention_beats_report_and_warns(self):
        """本集团用 3002 记资本公积（报表按 4002 取）：仍用 3002 —— 否则抵销与个别数落在两个编码上抵不掉；给警告。"""
        m = _mapper().map("资本公积")
        assert (m.account_code, m.in_report, m.reason) == ("3002", False, None)
        assert "3002" in m.warning and "合并报表看不到" in m.warning

    def test_chart_duplicate_names_prefer_report_range(self):
        """标准科目表 5001 / 6001 都叫「主营业务收入」：合并报表取 6001~6099 ⇒ 6001。"""
        m = _mapper(tree=[]).map("主营业务收入")
        assert (m.account_code, m.source, m.in_report) == ("6001", "标准科目表", True)

    def test_sub_account_under_parent(self):
        m = _mapper(tree=[*_TREE, ("151102", "损益调整")]).map("长期股权投资", "损益调整")
        assert (m.account_code, m.account_name, m.note) == ("151102", "损益调整", None)

    @pytest.mark.parametrize(("subject", "detail", "why"), [
        ("少数股东权益", None, "合并报表列报项目"),
        ("少数股权损益", None, "合并报表列报项目"),
        ("4-3对所有者的分配", "（四）利润分配", "所有者权益变动表项目"),
        ("2-3股份支付计入所有者权益的金额", None, "所有者权益变动表项目"),
        ("专项储备", "（二）所有者投入和减少资本", "所有者权益变动表项目"),
        ("生产成本", None, "都找不到"),     # 标准表 4 开头成本类不参与（报表 4 开头是权益）
        ("在建工程减值准备", None, "都找不到"),  # 减值准备表「十一、在建工程减值准备」配成 TB('1604')，附表不作依据
        ("", None, "没有科目名称"),
    ])
    def test_not_mapped(self, subject, detail, why):
        m = _mapper(tree=[]).map(subject, detail)
        assert m.account_code is None and why in m.reason


def _group(origin, key, lines, *, entry_type=None, desc=None, related=()):
    return SourceGroup(origin, key, desc, [SourceLine(*ln) for ln in lines], entry_type, list(related))


class TestPlanGroup:
    def test_balanced_negative_flip_and_zero_skip(self):
        plan = plan_group(_group(ORIGIN_INTERNAL_ARAP, "arap:1", [
            ("应付账款", None, "借", "50"),
            ("应收账款", None, "借", "-50"),   # 负数借方 = 贷方
            ("应收账款", None, "贷", "0"),     # 0 不入账
        ], related=["B", "A", "A"]), _mapper())
        assert plan.action == "" and plan.reasons == [] and plan.entry_type == "internal_ar_ap"
        assert [(ln.mapped.account_code, ln.debit, ln.credit) for ln in plan.lines] == [
            ("2202", D("50.00"), D("0")), ("1122", D("0"), D("50.00")),
        ]
        assert [ln.index for ln in plan.lines] == [1, 2] and plan.related == ["A", "B"]
        assert plan.description == "内部往来抵销自动生成"

    def test_unbalanced_unmapped_bad_values_blocked_with_reasons(self):
        plan = plan_group(_group(ORIGIN_EQUITY_SIM, "eq:1", [
            ("长期股权投资", "损益调整", "借", "100"),
            ("少数股东权益", None, "贷", "30"),
            ("资本公积", None, "左", "5"),
            ("盈余公积", None, "贷", "abc"),
        ]), _mapper())
        assert plan.action == "blocked"
        joined = "；".join(plan.reasons)
        for part in ("第 2 行（少数股东权益）", "第 3 行（资本公积）借贷方向「左」", "第 4 行（盈余公积）金额无法识别", "借贷不平衡"):
            assert part in joined, part

    def test_all_zero_is_empty_and_type_must_match_origin(self):
        assert plan_group(_group(ORIGIN_INTERNAL_TRADE, "t:1", [("营业收入", None, "借", "0")]), _mapper()).action == "empty"
        plan = plan_group(_group(ORIGIN_INTERNAL_TRADE, "t:2", [("营业收入", None, "借", "9"), ("营业成本", None, "贷", "9")],
                                 entry_type="equity"), _mapper())
        assert plan.action == "blocked" and "不能生成「权益抵销」" in plan.reasons[0]
        ok = plan_group(_group(ORIGIN_INTERNAL_TRADE, "t:3", [("营业成本", None, "借", "9"), ("存货", None, "贷", "9")],
                               entry_type="unrealized_profit"), _mapper())
        assert ok.reasons == [] and ok.entry_type == "unrealized_profit"


# ─────────────────────────────── 真库：生成、幂等、审批后不改 ───────────────────────────────


def _arap(key="arap:G|B", amount="50", related=("G", "B")):
    return _group(ORIGIN_INTERNAL_ARAP, key, [("应付账款", None, "借", amount), ("应收账款", None, "贷", amount)],
                  related=related, desc="内部往来抵销（本方 / 对方）")


def _trade(key="trade:revenue", amount="120"):
    return _group(ORIGIN_INTERNAL_TRADE, key, [("营业收入", None, "借", amount), ("营业成本", None, "贷", amount)])


async def _live(db, project, origin=None):
    """未删分录。可传项目 id：回滚会让测试会话里的 ORM 对象过期，异步会话不能懒加载。"""
    pid = project if isinstance(project, uuid.UUID) else project.id
    stmt = sa.select(EliminationEntry).where(EliminationEntry.project_id == pid,
                                             EliminationEntry.is_deleted == sa.false())
    if origin:
        stmt = stmt.where(EliminationEntry.origin == origin)
    return list((await db.execute(stmt.order_by(EliminationEntry.entry_no))).scalars().all())


class TestGenerate:
    @pytest.mark.asyncio
    async def test_p6_idempotent_and_update_same_entry(self, db, group):
        g = group["G"]
        first = await generate_from_worksheet(db, g.id, Y, [_arap(), _trade()])
        await db.commit()
        assert (first.count("created"), first.count("updated")) == (2, 0)
        (arap,) = await _live(db, g, ORIGIN_INTERNAL_ARAP)
        assert (arap.review_status, arap.entry_type, arap.origin_key) == (
            ReviewStatusEnum.draft, EliminationEntryType.internal_ar_ap, "arap:G|B")
        assert [(ln["account_code"], ln["debit_amount"], ln["credit_amount"]) for ln in arap.lines] == [
            ("2202", "50.00", "0"), ("1122", "0", "50.00")]
        assert (arap.debit_amount, arap.credit_amount, arap.account_code) == (D("50.00"), D("50.00"), "2202")
        assert arap.related_company_codes == ["B", "G"] and arap.entry_no.startswith("IA-")
        (trade,) = await _live(db, g, ORIGIN_INTERNAL_TRADE)
        assert [ln["account_code"] for ln in trade.lines] == ["6001", "6401"]  # 营业收入 / 营业成本 ⇒ 本集团编码

        again = await generate_from_worksheet(db, g.id, Y, [_arap(), _trade()])
        await db.commit()
        assert (again.count("created"), again.count("updated"), again.count("unchanged")) == (0, 0, 2), "P6"

        changed = await generate_from_worksheet(db, g.id, Y, [_arap(amount="70"), _trade()])
        await db.commit()
        assert (changed.count("created"), changed.count("updated")) == (0, 1)
        (arap2,) = await _live(db, g, ORIGIN_INTERNAL_ARAP)
        assert arap2.id == arap.id and arap2.entry_no == arap.entry_no, "同一来源键更新同一笔，不另建"
        assert (arap2.debit_amount, arap2.lines[0]["debit_amount"]) == (D("70.00"), "70.00")

    @pytest.mark.asyncio
    async def test_p7_approved_untouched_and_reported(self, db, group):
        g = group["G"]
        await generate_from_worksheet(db, g.id, Y, [_arap(), _trade()])
        await db.commit()
        (arap,) = await _live(db, g, ORIGIN_INTERNAL_ARAP)
        arap.review_status = ReviewStatusEnum.approved
        (trade,) = await _live(db, g, ORIGIN_INTERNAL_TRADE)
        trade.review_status = ReviewStatusEnum.pending_review
        await db.commit()
        before = (arap.lines, arap.debit_amount, arap.description)

        res = await generate_from_worksheet(db, g.id, Y, [_arap(amount="999")], origins=[ORIGIN_INTERNAL_ARAP, ORIGIN_INTERNAL_TRADE])
        await db.commit()
        await db.refresh(arap)
        await db.refresh(trade)
        assert (arap.lines, arap.debit_amount, arap.description) == before, "P7：已审批分录不被改写"
        assert arap.review_status == ReviewStatusEnum.approved
        assert trade.is_deleted is False, "来源不再产出，待审批分录也不删"
        notes = {n["origin_key"]: n["reason"] for n in res.changed_after_review}
        assert "来源数据已变化，已审批分录未改动" in notes["arap:G|B"] and "撤销审批" in notes["arap:G|B"]
        assert "不再产出" in notes["trade:revenue"] and "驳回" in notes["trade:revenue"]
        assert res.count("updated") == 0 and res.deleted == []
        same = await generate_from_worksheet(db, g.id, Y, [_arap()])
        assert same.count("unchanged") == 1 and same.changed_after_review == [], "内容相同 ⇒ 不报变化"

    @pytest.mark.asyncio
    async def test_soft_delete_only_declared_origins_and_keep_rejection(self, db, group):
        g = group["G"]
        await generate_from_worksheet(db, g.id, Y, [_arap(), _arap("arap:G|A", "8", ("G", "A")), _trade()])
        await db.commit()
        # 只声明内部往来：内部交易的草稿不受影响；往来里消失的键 ⇒ 软删
        res = await generate_from_worksheet(db, g.id, Y, [_arap()], origins=[ORIGIN_INTERNAL_ARAP])
        await db.commit()
        assert [d["origin_key"] for d in res.deleted] == ["arap:G|A"]
        assert [e.origin_key for e in await _live(db, g, ORIGIN_INTERNAL_ARAP)] == ["arap:G|B"]
        assert len(await _live(db, g, ORIGIN_INTERNAL_TRADE)) == 1, "未声明的来源不动"
        # 某来源本次一组都没算出：显式声明它才清理
        cleared = await generate_from_worksheet(db, g.id, Y, [], origins=[ORIGIN_INTERNAL_TRADE])
        await db.commit()
        assert cleared.to_dict()["deleted"] == 1 and await _live(db, g, ORIGIN_INTERNAL_TRADE) == []
        # 已驳回：来源没变 ⇒ 不推翻驳回（说明里的驳回原因也不算变化）；来源变了 ⇒ 改写回草稿、保留驳回原因
        (arap,) = await _live(db, g, ORIGIN_INTERNAL_ARAP)
        arap.review_status = ReviewStatusEnum.rejected
        arap.description = f"{arap.description}\n驳回原因: 金额待核"
        await db.commit()
        kept = await generate_from_worksheet(db, g.id, Y, [_arap()])
        assert kept.count("unchanged") == 1 and arap.review_status == ReviewStatusEnum.rejected
        redo = await generate_from_worksheet(db, g.id, Y, [_arap(amount="55")])
        await db.commit()
        await db.refresh(arap)
        assert redo.count("updated") == 1 and arap.review_status == ReviewStatusEnum.draft
        assert arap.description == "内部往来抵销（本方 / 对方）\n驳回原因: 金额待核"
        assert arap.reviewer_id is None and arap.debit_amount == D("55.00")

    @pytest.mark.asyncio
    async def test_blocked_group_keeps_existing_draft_and_dry_run_writes_nothing(self, db, group):
        g = group["G"]
        gid = g.id
        await generate_from_worksheet(db, gid, Y, [_arap()])
        await db.commit()
        (arap,) = await _live(db, g)
        broken = _group(ORIGIN_INTERNAL_ARAP, "arap:G|B", [("应付账款", None, "借", "50"), ("少数股东权益", None, "贷", "50")])
        res = await generate_from_worksheet(db, g.id, Y, [broken])
        await db.commit()
        await db.refresh(arap)
        assert res.count("blocked") == 1 and res.deleted == [], "映射失败 ≠ 来源消失：已有草稿不删"
        assert arap.is_deleted is False and arap.lines[1]["account_code"] == "1122"
        body = res.to_dict()
        assert body["blocked"][0]["entry_id"] == str(arap.id) and "少数股东权益" in body["blocked"][0]["reason"]

        preview = await generate_from_worksheet(db, gid, Y, [_arap(amount="1"), _trade()], dry_run=True)
        assert (preview.count("updated"), preview.count("created")) == (1, 1)
        assert preview.to_dict()["groups"][1]["lines"][0]["account_code"] == "6001"
        await db.rollback()  # 预演若改过内存对象，回滚后重读即现原形
        (after,) = await _live(db, gid)
        assert after.debit_amount == D("50.00"), "预演不写库"

    @pytest.mark.asyncio
    async def test_request_errors(self, db, group):
        g, b = group["G"], group["B"]
        with pytest.raises(SheetError, match="只有合并报表项目"):
            await generate_from_worksheet(db, b.id, Y, [_arap()])
        with pytest.raises(SheetError, match="来源键重复"):
            await generate_from_worksheet(db, g.id, Y, [_arap(), _arap()])
        with pytest.raises(SheetError, match="不在本次声明的来源"):
            await generate_from_worksheet(db, g.id, Y, [_arap()], origins=[ORIGIN_INTERNAL_TRADE])
        with pytest.raises(SheetError, match="不能由本接口生成"):
            await generate_from_worksheet(db, g.id, Y, [], origins=["legacy_sheet"])
        with pytest.raises(SheetError) as missing:
            await generate_from_worksheet(db, uuid.uuid4(), Y, [])
        assert missing.value.status == 404


# ─────────────────────────────── 明细行 ───────────────────────────────


class TestTreeLines:
    @pytest.mark.asyncio
    async def test_whole_tree_readonly_counted_orphans_totals(self, db, group):
        g, a = group["G"], group["A"]
        pair = lambda amt: [("2202", "应付账款", amt, "0"), ("1122", "应收账款", "0", amt)]  # noqa: E731
        db.add(_entry(g, "IA-1", EliminationEntryType.internal_ar_ap, pair("50")))
        db.add(_entry(g, "IA-2", EliminationEntryType.internal_ar_ap, pair("9"), status=ReviewStatusEnum.draft))
        db.add(_entry(g, "IA-3", EliminationEntryType.internal_ar_ap, pair("3"), branch="ZZ"))  # 归属节点不存在
        broken = _entry(g, "IA-4", EliminationEntryType.internal_ar_ap, pair("4"))
        broken.lines = {"坏": "数据"}
        db.add(broken)
        db.add(_entry(a, "IA-A", EliminationEntryType.internal_ar_ap, pair("7")))
        db.add(_entry(a, "IA-X", EliminationEntryType.internal_ar_ap, pair("1")))
        await db.flush()
        (await _live(db, a))[-1].soft_delete()
        await db.commit()

        body = await tree_lines(db, g.id)
        rows = body["rows"]
        assert [(r["entry_no"], r["line_index"]) for r in rows] == [
            ("IA-1", 1), ("IA-1", 2), ("IA-2", 1), ("IA-2", 2), ("IA-3", 1), ("IA-3", 2), ("IA-4", 1),
            ("IA-A", 1), ("IA-A", 2),
        ], "本项目在前，下级合并项目承载的随后；已删的不列"
        by = {r["entry_no"]: r for r in rows}
        assert (by["IA-1"]["counted"], by["IA-1"]["node_key"], by["IA-1"]["readonly"]) == (True, "G:consol_elim", False)
        assert by["IA-1"]["node_label"] == "某集团（合并差额）" and by["IA-1"]["origin_label"] == "手工录入"
        assert by["IA-2"]["counted"] is False and by["IA-2"]["orphan_reason"] is None, "草稿不计入但不是孤儿"
        assert by["IA-3"]["counted"] is False and "ZZ" in by["IA-3"]["orphan_reason"]
        assert by["IA-4"]["account_code"] is None and "明细行无法识别" in by["IA-4"]["orphan_reason"]
        assert (by["IA-A"]["readonly"], by["IA-A"]["counted"], by["IA-A"]["host_project_name"]) == (True, True, "甲公司")
        assert by["IA-A"]["node_key"] == "A:consol_elim" and by["IA-A"]["host_project_id"] == str(a.id)
        assert body["totals"] == {
            "all": {"debit": "69.00", "credit": "69.00", "difference": "0.00", "entry_count": 5},
            "approved": {"debit": "60.00", "credit": "60.00", "difference": "0.00", "entry_count": 4},
            "counted": {"debit": "57.00", "credit": "57.00", "difference": "0.00", "entry_count": 2},
        }
        assert body["hosted_nodes"] == [
            {"node_key": "G:consol_elim", "label": "某集团（合并差额）", "branch_entity_code": None},
        ]
        # 下级合并项目只看自己子树
        sub = await tree_lines(db, a.id)
        assert {r["entry_no"] for r in sub["rows"]} == {"IA-A"} and sub["rows"][0]["readonly"] is False
        with pytest.raises(SheetError, match="只有合并报表项目"):
            await tree_lines(db, group["B"].id)


# ─────────────────────────────── 旧版明细表 ───────────────────────────────


def _legacy_rows():
    auto = {"source": "权益抵消", "direction": "借", "subject": "实收资本", "detail": "", "amount": 999, "desc": ""}
    custom = lambda d, s, amt, desc="": {"source": "", "direction": d, "subject": s, "detail": "", "amount": amt,  # noqa: E731
                                         "desc": desc, "_custom": True}
    return [
        auto,
        custom("借", "应付账款", 100, "往来甲"), custom("贷", "应收账款", 100),
        custom("借", "营业收入", 30, "交易乙"), custom("贷", "营业成本", 30),
        custom("借", "应收账款", 5),
        {"source": "", "direction": "借", "subject": "", "amount": None, "_custom": True},   # 空白行
        custom("贷", "商誉", 0),                                                           # 0 金额
    ]


class TestLegacySheet:
    def test_custom_rows_and_balanced_runs(self):
        rows, skipped = legacy_custom_rows({"rows": _legacy_rows()})
        assert [r["subject"] for r in rows] == ["应付账款", "应收账款", "营业收入", "营业成本", "应收账款"]
        assert skipped == 1
        groups = legacy_groups(rows)
        assert [len(g.lines) for g in groups] == [2, 2, 1]
        assert groups[0].description == "旧版明细表转入：往来甲" and groups[0].origin_key.startswith("legacy:001:")
        assert legacy_groups(rows)[1].origin_key == groups[1].origin_key, "来源键确定"
        assert legacy_custom_rows({"rows": {"equity": [{"direction": "借", "subject": "实收资本", "values": [1]}]}}) == ([], 0)
        assert legacy_custom_rows(None) == ([], 0)

    @pytest.mark.asyncio
    async def test_detect_convert_idempotent_and_deleted_not_restored(self, db, group):
        g = group["G"]
        empty = await legacy_sheet(db, g.id, Y)
        assert (empty["custom_row_count"], empty["pending"], empty["message"]) == (0, 0, "没有旧版自定义抵销行")
        db.add(ConsolWorksheetData(project_id=g.id, year=Y, sheet_key="elimination", data={"rows": _legacy_rows()}))
        await db.commit()

        seen = await legacy_sheet(db, g.id, Y)
        assert seen["message"] == "检测到旧版自定义抵销行 5 条，旧版数据未参与合并计算"
        assert (seen["group_count"], seen["created"], len(seen["blocked"]), seen["pending"]) == (3, 2, 1, 3)
        assert "借贷不平衡" in seen["blocked"][0]["reason"] and await _live(db, g) == [], "检测只预演"

        done = await legacy_sheet(db, g.id, Y, convert=True)
        await db.commit()
        assert (done["created"], len(done["blocked"]), done["pending"]) == (2, 1, 1)
        entries = await _live(db, g, "legacy_sheet")
        assert [(e.entry_type, e.review_status) for e in entries] == [(EliminationEntryType.other, ReviewStatusEnum.draft)] * 2
        assert [ln["account_code"] for ln in entries[1].lines] == ["6001", "6401"]

        entries[0].description = "审计师改过说明"
        await db.commit()
        again = await legacy_sheet(db, g.id, Y, convert=True)
        await db.commit()
        assert (again["created"], again["unchanged"]) == (0, 2)
        await db.refresh(entries[0])
        assert entries[0].description == "审计师改过说明", "转入后分录归审计师，不按旧数据改写"

        entries[0].soft_delete()
        await db.commit()
        after_delete = await legacy_sheet(db, g.id, Y, convert=True)
        await db.commit()
        assert (after_delete["created"], after_delete["discarded"], after_delete["unchanged"]) == (0, 1, 1)
        assert len(await _live(db, g, "legacy_sheet")) == 1, "删掉的不转回来"


# ─────────────────────────────── 端点 ───────────────────────────────

_BASE = "/api/consolidation/eliminations"


def _payload(amount="50", *, dry_run=False, origins=None):
    body = {
        "year": Y, "dry_run": dry_run,
        "groups": [{
            "origin": ORIGIN_INTERNAL_ARAP, "origin_key": "arap:G|B", "description": "往来抵销",
            "related_company_codes": ["G", "B"],
            "lines": [{"subject": "应付账款", "direction": "借", "amount": amount},
                      {"subject": "应收账款", "direction": "贷", "amount": amount}],
        }],
    }
    if origins is not None:
        body["origins"] = origins
    return body


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_routes_generate_tree_lines_legacy(self, db, group, client_for):
        admin = _User(UserRole.admin)
        g_id = group["G"].id
        gid = str(g_id)

        async def committed_count() -> int:
            """回滚后再读：端点与测试共用一个会话，且内存 SQLite 所有会话共用一个连接（StaticPool）——
            另开会话也看得见未提交的写入；回滚后还在的才是已提交的。"""
            await db.rollback()
            return len(await _live(db, g_id))
        db.add(ConsolWorksheetData(project_id=g_id, year=Y, sheet_key="elimination", data={"rows": _legacy_rows()}))
        await db.commit()
        b_id = group["B"].id
        async with client_for(admin) as c:
            preview = await c.post(f"{_BASE}/generate-from-worksheet", params={"project_id": gid},
                                   json=_payload(dry_run=True))
            assert preview.status_code == 200, preview.text
            assert preview.json()["created"] == 1 and preview.json()["dry_run"] is True
            lines = (await c.get(f"{_BASE}/tree-lines", params={"project_id": gid})).json()
            assert lines["rows"] == [], "预演不写库"

            assert await committed_count() == 0
            made = (await c.post(f"{_BASE}/generate-from-worksheet", params={"project_id": gid}, json=_payload())).json()
            assert (made["created"], made["groups"][0]["entry_no"][:3]) == (1, "IA-")
            assert await committed_count() == 1, "生成已提交"
            again = (await c.post(f"{_BASE}/generate-from-worksheet", params={"project_id": gid}, json=_payload())).json()
            assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 1)

            got = await c.get(f"{_BASE}/tree-lines", params={"project_id": gid, "year": Y})
            assert got.status_code == 200, "固定路径声明在 /{entry_id} 之前，不被当成分录 id"
            rows = got.json()["rows"]
            assert [(r["account_code"], r["debit"], r["credit"], r["origin_label"]) for r in rows] == [
                ("2202", "50.00", "0.00", "内部往来"), ("1122", "0.00", "50.00", "内部往来")]

            legacy = (await c.get(f"{_BASE}/legacy-sheet", params={"project_id": gid, "year": Y})).json()
            assert (legacy["custom_row_count"], legacy["pending"]) == (5, 3)
            converted = await c.post(f"{_BASE}/legacy-sheet/convert", params={"project_id": gid},
                                     json={"year": Y, "entry_type": "internal_ar_ap"})
            assert converted.status_code == 200 and converted.json()["created"] == 2
            assert await committed_count() == 3, "转入已提交"
            kinds = {r["origin"]: r["entry_type"] for r in (await c.get(f"{_BASE}/tree-lines", params={"project_id": gid})).json()["rows"]}
            assert kinds == {ORIGIN_INTERNAL_ARAP: "internal_ar_ap", "legacy_sheet": "internal_ar_ap"}

            bad = await c.post(f"{_BASE}/generate-from-worksheet", params={"project_id": gid},
                               json={**_payload(), "origins": ["legacy_sheet"]})
            assert bad.status_code == 422, "旧版来源只能走转入端点"
            dup = await c.post(f"{_BASE}/generate-from-worksheet", params={"project_id": gid},
                               json={**_payload(), "groups": _payload()["groups"] * 2})
            assert dup.status_code == 400 and "来源键重复" in dup.json()["detail"]
            standalone = await c.get(f"{_BASE}/tree-lines", params={"project_id": str(b_id)})
            assert standalone.status_code == 400 and "只有合并报表项目" in standalone.json()["detail"]

    @pytest.mark.asyncio
    async def test_auth(self, db, group, client_for):
        outsider = await _persist(db, _User(UserRole.auditor))
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        gid = str(group["G"].id)
        reads = [(f"{_BASE}/tree-lines", {"project_id": gid}), (f"{_BASE}/legacy-sheet", {"project_id": gid})]
        writes = [(f"{_BASE}/generate-from-worksheet", _payload()), (f"{_BASE}/legacy-sheet/convert", {"year": Y})]
        async with client_for(outsider) as c:
            for url, params in reads:
                assert (await c.get(url, params=params)).status_code == 403, url
            for url, body in writes:
                assert (await c.post(url, params={"project_id": gid}, json=body)).status_code == 403, url
        async with client_for(reader) as c:
            for url, params in reads:
                assert (await c.get(url, params=params)).status_code == 200, url
            for url, body in writes:
                assert (await c.post(url, params={"project_id": gid}, json=body)).status_code == 403, url
        assert await _live(db, group["G"]) == []
