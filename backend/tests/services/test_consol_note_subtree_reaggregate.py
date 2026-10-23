"""合并附注「🔄 重新汇总」= 节点子树逐节点更新 + 自下而上汇总（真实 SQLite 全表，全程调用生产函数）。

spec: consol-note-header-library-and-node-reaggregate（Task 14 / design §8 §9）

企业树（三码推导）：
  G:consol ─ G:consol_elim / G:parent（无单体项目）/ A:consol / B:subsidiary
  A:consol ─ A:consol_elim / A:parent（A本部）/ A1:subsidiary
数据叶子按已确认映射从单体附注「八、1 货币资金」拉数；差额节点按抵销分录 + 附注公式（银行存款期末
= TB('1002')）算差额；汇总节点 = Σ 直接下级 + 差额。试算表 1002 故意与单体附注不同（B 附注没填银行存款、
试算表有 300），用来证明个别数取自单体附注而不是试算表。
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import ConsolNoteFormula
from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum
from app.models.core import Project, User
from app.services import consol_note_formula_service as formula_service
from app.services import consol_note_subtree_reaggregate as reaggregate_module
from app.services.consol_note_detail_source_service import preview_detail_refresh
from app.services.consol_note_subtree_reaggregate import reaggregate_subtree
from tests.services.test_consol_note_pull_e2e import (
    A_ROWS,
    _bind_template_from_suggestion,
    _confirm_all_groups,
    _seed_cash_note,
    _seed_workpaper_cash_note,
    _tables_row,
)

_YEAR = 2025
_SECTION = "五-1-1"          # 货币资金（已绑定明细模板、有一条差额公式）
_UNBOUND = "五-1-2"          # 受限制的货币资金明细（未绑定模板、没有公式）
D = Decimal

B_ROWS = [
    _tables_row("库存现金", 1000.0, 1000.0),
    _tables_row("银行存款", None, None),
    _tables_row("其他货币资金", None, None),
    _tables_row("数字货币", None, None),
    _tables_row("合计", 1000.0, 1000.0, total=True),
    _tables_row("其中：存放在境外的款项总额", None, None),
]


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(factory) -> AsyncSession:
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(id=uuid.uuid4(), username="tester", email="t@test.com", hashed_password="x", role="partner")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def group(db: AsyncSession) -> dict[str, Project]:
    def _p(name: str, code: str, parent: str | None, scope: str) -> Project:
        return Project(
            id=uuid.uuid4(), name=f"{name}_{_YEAR}", client_name=name, company_code=code,
            parent_company_code=parent, ultimate_company_code="G",
            relation_to_parent="subsidiary" if parent else None, report_scope=scope,
            audit_year=_YEAR, audit_period_end=date(_YEAR, 12, 31),
        )
    projects = {
        "G": _p("G集团合并", "G", None, "consolidated"),
        "A_consol": _p("A合并", "A", "G", "consolidated"),
        "A": _p("A本部", "A", "G", "standalone"),
        "A1": _p("A1子公司", "A1", "A", "standalone"),
        "B": _p("B子公司", "B", "G", "standalone"),
    }
    db.add_all(projects.values())
    await db.flush()
    return projects


def _tb(project: Project, amount: str) -> TrialBalance:
    return TrialBalance(
        id=uuid.uuid4(), project_id=project.id, year=_YEAR, company_code=project.company_code,
        standard_account_code="1002", account_name="银行存款", account_category=AccountCategory.asset,
        audited_amount=D(amount),
    )


def _entry(project: Project, no: str, credit_bank: str) -> EliminationEntry:
    """已审批抵销分录：贷 银行存款 / 借 应付账款。"""
    amount = D(credit_bank)
    return EliminationEntry(
        id=uuid.uuid4(), project_id=project.id, year=_YEAR, entry_no=no,
        entry_type=EliminationEntryType.internal_ar_ap, account_code="1002", entry_group_id=uuid.uuid4(),
        lines=[{"account_code": "1002", "account_name": "银行存款", "debit_amount": "0", "credit_amount": credit_bank},
               {"account_code": "2202", "account_name": "应付账款", "debit_amount": credit_bank, "credit_amount": "0"}],
        debit_amount=amount, credit_amount=amount, review_status=ReviewStatusEnum.approved,
    )


async def _setup(db: AsyncSession, user: User, group: dict[str, Project], *, with_b: bool = True) -> None:
    """单体附注 + 试算表 + A 合并的抵销分录 + 差额公式 + 明细模板绑定 + 确认映射。"""
    await _seed_cash_note(db, group["A"], A_ROWS)
    await _seed_workpaper_cash_note(db, group["A1"])
    if with_b:
        await _seed_cash_note(db, group["B"], B_ROWS)
    db.add_all([_tb(group["A"], "1000000"), _tb(group["A1"], "2000"), _tb(group["B"], "300"),
                _entry(group["A_consol"], "IA-1", "100")])
    db.add(ConsolNoteFormula(template_type="soe", section_id=_SECTION, row_index=1, col_index=1,
                             formula="TB('1002','期末余额')", source="manual"))
    await db.flush()
    await _bind_template_from_suggestion(db, user, group["G"])
    preview = await preview_detail_refresh(db, project_id=group["G"].id, section_id=_SECTION, year=_YEAR)
    await _confirm_all_groups(db, user, group["G"], preview)


async def _rec(db: AsyncSession, group, node_key: str, section: str = _SECTION) -> ConsolNoteData | None:
    return (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == group["G"].id, ConsolNoteData.section_id == section,
        ConsolNoteData.node_key == node_key,
    ).execution_options(populate_existing=True))).scalar_one_or_none()


def _rows(record: ConsolNoteData) -> dict[str, tuple]:
    def amount(v):
        return D(str(v)) if str(v).strip() else None
    return {str(r[0]).replace(" ", ""): (amount(r[1]), amount(r[2])) for r in record.data["rows"]}


def _nodes(result: dict) -> dict[str, dict]:
    return {n["node_key"]: n for n in result["nodes"]}


def _formula_value(record: ConsolNoteData) -> D | None:
    cells = (record.last_formula_value or {}).get("cells") or []
    hit = [c["value"] for c in cells if (c["row_index"], c["col_index"]) == (1, 1)]
    return D(str(hit[0])) if hit and hit[0] is not None else None


class TestSubtreeBottomUp:

    @pytest.mark.asyncio
    async def test_root_pulls_leaves_fills_elims_and_sums_bottom_up(self, db, user, group):
        await _setup(db, user, group)
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])

        assert result["mode"] == "subtree" and result["status"] == "persisted", result["failures"]
        assert result["sections_updated"] == 1 and result["results"][0]["status"] == "persisted"
        assert result["pending_entities"] == []
        nodes = _nodes(result)
        assert [nodes[k]["action"] for k in ("A:parent", "A1:subsidiary", "B:subsidiary")] == ["pull"] * 3
        assert all(nodes[k]["written"] == 1 for k in (
            "A:parent", "A1:subsidiary", "B:subsidiary", "A:consol_elim", "G:consol_elim", "A:consol", "G:consol"))
        assert nodes["G:parent"]["written"] == 0
        assert nodes["G:parent"]["reasons"][0]["reason"].startswith("没有单体项目")

        # 叶子 = 本企业单体附注（A1 是底稿投影、行名「现金」经别名对到库存现金；合计按本表重算）
        a1 = await _rec(db, group, "A1:subsidiary")
        assert a1.data["_last_write_source"] == "detail_mapping"
        assert _rows(a1)["库存现金"] == (D("100.00"), D("50.00"))
        assert _rows(a1)["合计"] == (D("2600.00"), D("1050.00"))
        # 差额 = A 合并的抵销分录（贷 银行存款 100）
        elim = await _rec(db, group, "A:consol_elim")
        assert elim.data["_last_write_source"] == "formula"
        assert _rows(elim)["银行存款"][0] == D("-100")

        # A 合并 = A本部 + A1 + A 差额
        a_consol = _rows(await _rec(db, group, "A:consol"))
        assert a_consol["库存现金"] == (D("476.73"), D("336.73"))
        assert a_consol["银行存款"] == (D("1001900.00"), D("801000.00"))
        assert a_consol["其他货币资金"] == (D("500.00"), D("0.00"))
        assert a_consol["合计"] == (D("1002876.73"), D("801336.73"))
        assert a_consol["其中：存放在境外的款项总额"] == (None, None)

        # G 合并 = G 差额 + A 合并（本轮汇总结果）+ B；G 母公司没有单体项目不计
        root = await _rec(db, group, "G:consol")
        g = _rows(root)
        assert g["库存现金"] == (D("1476.73"), D("1336.73"))
        assert g["银行存款"] == (D("1001900.00"), D("801000.00"))
        assert g["合计"] == (D("1003876.73"), D("802336.73"))
        assert root.data["_last_write_source"] == "subtree_aggregate" and root.is_stale is False
        assert root.data["_subtree_child_count"] == 2          # A 合并 + B；差额不算「下级企业」
        children = {c["node_key"]: c for c in root.data["_subtree_provenance"]["children"]}
        assert children["A:consol"]["included"] and children["A:consol"]["source"] == "subtree_aggregate"
        assert children["B:subsidiary"]["source"] == "detail_mapping"
        assert children["G:consol_elim"]["included"] and children["G:consol_elim"]["source"] == "formula"
        assert children["G:parent"] == {**children["G:parent"], "included": False, "reason": "没有数据"}
        # 公式值快照取试算表口径（1000000 + 2000 - 100 + 300），汇总数是单体附注口径（B 附注没填银行存款）
        assert _formula_value(root) == D("1002200")
        assert g["银行存款"][0] != _formula_value(root)

    @pytest.mark.asyncio
    async def test_mid_level_node_only_touches_its_subtree(self, db, user, group):
        await _setup(db, user, group)
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="A:consol", section_ids=[_SECTION])

        assert result["node_key"] == "A:consol" and result["sections_updated"] == 1
        assert set(_nodes(result)) == {"A:consol", "A:consol_elim", "A:parent", "A1:subsidiary"}
        assert _rows(await _rec(db, group, "A:consol"))["银行存款"] == (D("1001900.00"), D("801000.00"))
        assert await _rec(db, group, "G:consol") is None
        assert await _rec(db, group, "B:subsidiary") is None


class TestProtectionAndSkips:

    @pytest.mark.asyncio
    async def test_manual_cell_kept_and_counted_in_total(self, db, user, group):
        await _setup(db, user, group)
        db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_SECTION, node_key="G:consol",
                              data={"rows": [["库存现金", "", ""], ["银行存款", "999.00", ""]],
                                    "manual_cells": [{"row": 1, "col": 1}]}))
        await db.flush()
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])

        g = _rows(await _rec(db, group, "G:consol"))
        assert g["银行存款"] == (D("999.00"), D("801000.00"))
        assert g["合计"][0] == D("1476.73") + D("999.00") + D("500.00")
        assert result["results"][0]["kept_manual_count"] == 1

    @pytest.mark.asyncio
    async def test_locked_mid_node_is_skipped_and_its_saved_rows_feed_the_parent(self, db, user, group):
        await _setup(db, user, group)
        db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_SECTION, node_key="A:consol",
                              cell_state="locked", data={"rows": [["库存现金", "1.00", "2.00"]]}))
        await db.flush()
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])

        nodes = _nodes(result)
        assert nodes["A:consol"]["written"] == 0 and nodes["A:consol"]["reasons"][0]["reason"] == "整节锁定，未覆盖"
        assert _rows(await _rec(db, group, "A:consol"))["库存现金"] == (D("1.00"), D("2.00"))
        assert _rows(await _rec(db, group, "G:consol"))["库存现金"] == (D("1001.00"), D("1002.00"))

    @pytest.mark.asyncio
    async def test_trial_balance_formula_child_is_excluded_and_unconfirmed_entity_is_pending(self, db, user, group):
        """B 没有单体附注 ⇒ 没有确认映射（待确认）；它旧的「按公式填入」行是试算表数，不能计入合并。"""
        await _setup(db, user, group, with_b=False)
        db.add_all([
            ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_SECTION, node_key="B:subsidiary",
                           data={"rows": [["库存现金", "777.00", ""]], "_last_write_source": "formula"}),
            # 来源标记出现之前的「按公式填入」：没有标记、有公式值快照 ⇒ 同样按试算表数排除
            ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_SECTION, node_key="G:parent",
                           data={"rows": [["库存现金", "555.00", ""]]}, last_formula_value={"cells": []}),
        ])
        await db.flush()
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])

        assert result["pending_entities"] == [{
            "node_key": "B:subsidiary", "label": result["pending_entities"][0]["label"], "section_count": 1,
            "sections": [_SECTION], "reasons": ["未确认映射（或单体附注没有该表）"],
        }]
        root = await _rec(db, group, "G:consol")
        assert _rows(root)["库存现金"] == (D("476.73"), D("336.73"))   # 只有 A 合并
        children = {c["node_key"]: c for c in root.data["_subtree_provenance"]["children"]}
        for key in ("B:subsidiary", "G:parent"):
            assert children[key]["included"] is False and "试算表公式" in children[key]["reason"]

    @pytest.mark.asyncio
    async def test_excluded_entity_is_not_pulled_and_its_old_rows_are_not_counted(self, db, user, group):
        from app.models.consol_note_mapping_models import ConsolNoteMappingBinding

        await _setup(db, user, group)
        await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])
        binding = (await db.execute(sa.select(ConsolNoteMappingBinding).where(
            ConsolNoteMappingBinding.entity_node_key == "B:subsidiary"))).scalar_one()
        binding.status = "excluded"          # 映射弹窗里把 B 排除
        await db.flush()
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])

        assert _nodes(result)["B:subsidiary"]["reasons"][0]["reason"] == "映射中已排除该企业，不计入"
        assert result["pending_entities"] == []
        root = await _rec(db, group, "G:consol")
        assert _rows(root)["库存现金"] == (D("476.73"), D("336.73"))   # B 上次拉的 1000 不再计入
        children = {c["node_key"]: c for c in root.data["_subtree_provenance"]["children"]}
        assert children["B:subsidiary"]["included"] is False and children["B:subsidiary"]["reason"] == "映射中已排除"

    @pytest.mark.asyncio
    async def test_unbound_section_elim_only_is_not_written_until_an_entity_has_data(self, db, user, group):
        await _setup(db, user, group)
        db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_UNBOUND, node_key="G:consol_elim",
                              data={"rows": [["银行承兑汇票保证金", "-8.00", ""]]}))
        await db.flush()
        first = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_UNBOUND])

        nodes = _nodes(first)
        assert first["status"] == "skipped" and first["sections_updated"] == 0
        assert nodes["A:parent"]["reasons"][0]["reason"].startswith("本章节未绑定明细模板")
        assert nodes["G:consol_elim"]["reasons"][0]["reason"].startswith("本章节没有差额公式")
        assert nodes["G:consol"]["reasons"][0]["reason"].startswith("下级企业都没有可汇总的单体附注数据")
        assert await _rec(db, group, "G:consol", _UNBOUND) is None

        # 手工录入的下级数（没有来源标记也没有公式值快照）算企业数据：按合并附注模板行汇总
        db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_UNBOUND, node_key="B:subsidiary",
                              data={"rows": [["银行承兑汇票保证金", "88.00", ""]]}))
        await db.flush()
        second = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_UNBOUND])
        assert second["sections_updated"] == 1
        assert _rows(await _rec(db, group, "G:consol", _UNBOUND))["银行承兑汇票保证金"][0] == D("80.00")


    @pytest.mark.asyncio
    async def test_embedded_sub_header_row_is_kept_verbatim(self, db, user, group, monkeypatch):
        """未绑定章节按合并附注模板行汇总：表内嵌的子表头行原样保留、不参与求和。

        R7.6 后国企种子已没有表内嵌子表头（原 五-10-5 坏账准备三阶段按 Word 改成多级表头，现 五-9-12）；
        模板表首行重复首列表头的判定与 ``_ensure_row_types`` 同一条，这里用这种形态的模板表钉住汇总的处理。"""
        section = "五-9-12"
        real = formula_service.find_table("soe", section)
        header = ["坏账准备", "未来12个月预期信用损失", "整个存续期预期信用损失（未发生信用减值）",
                  "整个存续期预期信用损失（已发生信用减值）", "合计"]
        legacy = {**real, "headers": ["坏账准备", "第一阶段", "第二阶段", "第三阶段", "合计"], "multi_header": None,
                  "rows": [header] + [list(r) for r in real["rows"]]}
        monkeypatch.setattr(reaggregate_module, "find_table", lambda tt, sid: legacy if (tt, sid) == ("soe", section)
                            else formula_service.find_table(tt, sid))
        db.add_all([
            ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=section, node_key=key,
                           data={"rows": [list(header), ["期初余额", amount, "", "", amount]]})
            for key, amount in (("B:subsidiary", "10.00"), ("A:parent", "5.00"))
        ])
        await db.flush()
        await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[section])

        rows = (await _rec(db, group, "G:consol", section)).data["rows"]
        assert rows[0] == list(header)
        assert rows[1][:2] == ["期初余额", "15.00"] and rows[1][4] == "15.00"


    @pytest.mark.asyncio
    async def test_failed_elim_stops_aggregation_upward_but_not_the_pulls(self, db, user, group):
        """A 差额算不出（手工格元数据损坏，公式内核拒写）⇒ A 合并、G 合并本章都不汇总；叶子照常拉数。"""
        await _setup(db, user, group)
        db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_SECTION, node_key="A:consol_elim",
                              data={"rows": [], "manual_cells": "坏了"}))
        await db.flush()
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])

        nodes = _nodes(result)
        assert nodes["A:consol_elim"]["failed"] == 1
        assert nodes["A:consol"]["reasons"][0]["reason"].startswith("下级「")
        assert nodes["G:consol"]["written"] == 0 and nodes["G:consol"]["reasons"][0]["reason"].startswith("下级「")
        assert result["status"] == "partial" and result["sections_updated"] == 0
        assert [(f["node_key"], "manual_cells" in f["error"]) for f in result["failures"]] == [("A:consol_elim", True)]
        assert await _rec(db, group, "A:consol") is None and await _rec(db, group, "G:consol") is None
        assert (await _rec(db, group, "B:subsidiary")).data["_last_write_source"] == "detail_mapping"


class TestSectionIsolation:

    @pytest.mark.asyncio
    async def test_unexpected_error_rolls_back_whole_section_and_next_section_continues(
        self, db, user, group, monkeypatch,
    ):
        await _setup(db, user, group)
        db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_UNBOUND, node_key="B:subsidiary",
                              data={"rows": [["银行承兑汇票保证金", "88.00", ""]]}))
        await db.flush()
        real = reaggregate_module.build_table_rows

        def broken(skeleton, *args, **kwargs):
            if skeleton and skeleton[0][0] == "库存现金":     # 只让「货币资金」章节的汇总出错
                raise RuntimeError("汇总写入失败")
            return real(skeleton, *args, **kwargs)

        monkeypatch.setattr(reaggregate_module, "build_table_rows", broken)
        result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol",
                                           section_ids=[_SECTION, _UNBOUND])

        assert result["status"] == "partial"
        assert [(f["section_id"], f["node_key"]) for f in result["failures"]] == [(_SECTION, "A:consol")]
        # 同章节先写的叶子拉数、差额都随章节回滚
        assert await _rec(db, group, "A:parent") is None and await _rec(db, group, "A:consol_elim") is None
        assert all(n["failed"] == 1 for n in result["nodes"])
        assert _rows(await _rec(db, group, "G:consol", _UNBOUND))["银行承兑汇票保证金"][0] == D("88.00")


class TestBackgroundRefreshKeepsPulledData:

    @pytest.mark.asyncio
    async def test_preserve_pulled_marks_stale_only_when_formula_values_change(self, db, user, group):
        await _setup(db, user, group)
        await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])
        pulled_rows = (await _rec(db, group, "G:consol")).data["rows"]

        same = await formula_service.fill_note_sections(
            db, group["G"].id, _YEAR, [_SECTION], node_key="G:consol", template_type="soe", preserve_pulled=True)
        assert same["results"][0]["status"] == "kept_pulled" and same["results"][0]["stale_marked"] is False
        assert same["sections_updated"] == 0 and same["sections_kept_pulled"] == 1
        assert (await _rec(db, group, "G:consol")).is_stale is False

        db.add(_entry(group["G"], "IA-2", "50"))       # G 层新增抵销：合并数的公式值变了
        await db.flush()
        changed = await formula_service.fill_note_sections(
            db, group["G"].id, _YEAR, [_SECTION], node_key="G:consol", template_type="soe", preserve_pulled=True)
        assert changed["results"][0]["stale_marked"] is True
        root = await _rec(db, group, "G:consol")
        assert root.is_stale is True and root.data["rows"] == pulled_rows
        assert _formula_value(root) == D("1002150")
        # 差额节点来源是公式：后台照常刷新
        elim = await formula_service.fill_note_sections(
            db, group["G"].id, _YEAR, [_SECTION], node_key="G:consol_elim", template_type="soe", preserve_pulled=True)
        assert elim["results"][0]["status"] == "persisted"
        assert _rows(await _rec(db, group, "G:consol_elim"))["银行存款"][0] == D("-50")

        # 用户主动「按公式填入」不变：按试算表口径覆盖
        manual = await formula_service.fill_by_formula(db, group["G"].id, _YEAR, _SECTION, node_key="G:consol",
                                                       template_type="soe")
        assert manual["status"] == "persisted"
        root = await _rec(db, group, "G:consol")
        assert root.data["_last_write_source"] == "formula"
        assert _rows(root)["银行存款"][0] == D("1002150")

    @pytest.mark.asyncio
    async def test_push_refresh_keeps_pulled_rows_and_leaves_them_stale(self, db, user, group, monkeypatch):
        from app.services.consol_push_service import _refresh_notes

        await _setup(db, user, group)
        await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])
        await db.commit()
        before = {k: (await _rec(db, group, k)).data["rows"] for k in ("G:consol", "A:consol", "B:subsidiary")}
        table = formula_service.find_table("soe", _SECTION)
        monkeypatch.setattr(formula_service, "consol_note_tables", lambda _tt: [table])

        stats = await _refresh_notes(db, group["G"].id, _YEAR)

        assert stats["kept_pulled_count"] == 5          # A本部 / A1 / B / A 合并 / G 合并
        for key, rows in before.items():
            record = await _rec(db, group, key)
            assert record.data["rows"] == rows and record.is_stale is True   # 推送后待重新汇总
        assert (await _rec(db, group, "A:consol_elim")).is_stale is False


class TestEndpoint:

    @pytest.mark.asyncio
    async def test_reaggregate_endpoint_runs_subtree_and_commits(self, factory, db, user, group):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.core.database import get_db
        from app.deps import get_current_user
        from app.models.base import UserRole
        from app.routers.consol_notes import router

        await _setup(db, user, group)
        await db.commit()
        app = FastAPI()
        app.include_router(router)
        actor = type("Actor", (), {"id": user.id, "username": "tester", "role": UserRole.admin,
                                   "is_active": True, "is_deleted": False})()

        async def override_db():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: actor
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/consolidation/notes/{group['G'].id}/{_YEAR}/reaggregate",
                                     json={"section_ids": [_SECTION], "node_key": "G:consol", "template_type": "soe"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "subtree" and body["success"] is True and body["sections_updated"] == 1
        assert body["node_key"] == "G:consol" and body["legacy_null"] is False
        assert {n["node_key"] for n in body["nodes"]} >= {"G:consol", "A:consol", "A1:subsidiary"}
        async with factory() as fresh:
            record = (await fresh.execute(sa.select(ConsolNoteData).where(
                ConsolNoteData.node_key == "G:consol", ConsolNoteData.section_id == _SECTION))).scalar_one()
        assert record.data["_last_write_source"] == "subtree_aggregate"


def test_record_write_source_falls_back_to_snapshot_then_manual():
    record = type("R", (), {})
    record.data, record.last_formula_value = {"_last_write_source": "detail_mapping"}, None
    assert formula_service.record_write_source(record) == "detail_mapping"
    record.data, record.last_formula_value = {"rows": []}, {"cells": []}
    assert formula_service.record_write_source(record) == "formula"
    record.data, record.last_formula_value = {"rows": []}, None
    assert formula_service.record_write_source(record) == "manual"
