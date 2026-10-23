"""PREV 三参（上年同底稿取数）与上年数据来源（spec formula-fetch-and-wp-generation-defect-closure R2）。

修复前：``PREV('底稿','表','字段')`` 在 L1 内核里把底稿编码当科目查上年试算表 ⇒ 恒 0；底稿可编辑公式与严格路径
直接拒收；两参 PREV 只认同项目上年、L1 还忽略列名（恒取期末余额）。

真 ORM 行（SQLite）：上年项目四种情形、字段定义三层（本项目 > 全局 > 系统预设）、审定表「未审数」换列、
函数白名单、缺数不写 0；严格代入 / 统一预载层 + L1 / L1 降级路径三条求值路径同一口径；两参 PREV 同一上年来源 + 列名。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.dataset_models import LedgerDataset
from app.models.formula_setting_models import FormulaSetting
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex
from app.services import formula_engine, formula_ref_preload
from app.services.formula_preloader import preload
from app.services.formula_settings import domain_stores
from app.services.formula_settings.stores import SlotRecord
from app.services.prev_wp_field import PriorWpFieldResolver
from app.services.prior_year_context import find_prior_project, resolve_prior_source
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._env import make_db

EXTRA = (TrialBalance, LedgerDataset, WpIndex, WorkingPaper, WpFormula)
YEAR = 2025
SHEET = "审定表D1-1"
PREV_AUDITED = f"PREV('D1','{SHEET}','审定数')"

#: 受控的系统预设层（替换 prefill_formula_mapping.json，避免随真实预设改动漂移）
PRESETS = {
    f"D1|{SHEET}|未审数": "=TB('1121','期末余额')",
    f"D1|{SHEET}|上年审定数": f"={PREV_AUDITED}",
    "D1|附注披露信息|期末账面价值": "=TB('1121','期末余额')-TB('1231-01','期末余额')",
    "D1|明细表D1-2|区间": "=TB_SUM('1121~1122','期末余额')",
    "D1|明细表D1-2|占位": "=PLACEHOLDER()",
    "D1|明细表D1-2|序时": "=LEDGER('1121','credit','全年')",
    "D1|明细表D1-2|套娃": f"={PREV_AUDITED}",
    "D1|明细表D1-2|引用": "=WP('D2','审定表D2-1','审定数')",
    "D1|核对|定义": "=TB('1121','期末余额')",
    "D1|单参表|未审数": "=TB('1121')",
    "D1|混合表|未审数": "=TB('1121','期末余额')+TB('1122')",
}


@pytest.fixture(autouse=True)
def _presets(monkeypatch):
    records = {slot: SlotRecord(slot_key=slot, definition={"expression": f, "formula_type": "auto_calc"},
                                version=0, label=slot, layer="preset") for slot, f in PRESETS.items()}
    monkeypatch.setattr(domain_stores, "_mapping_records", lambda: records)


async def _project(db, name, *, year=YEAR, code="C001", scope="standalone", prior=None, deleted=False):
    pid = uuid.uuid4()
    db.add(Project(id=pid, name=name, client_name=name, status=ProjectStatus.execution, template_type="soe",
                   report_scope=scope, audit_year=year, company_code=code, prior_year_project_id=prior,
                   is_deleted=deleted))
    await db.flush()
    return pid


def _tb(pid, year, code, audited, opening="0"):
    return TrialBalance(project_id=pid, year=year, company_code="001", standard_account_code=code,
                        account_name=code, account_category=AccountCategory.asset,
                        audited_amount=Decimal(audited), opening_balance=Decimal(opening))


async def _wp(db, pid, code="D1"):
    idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=code)
    db.add(idx)
    await db.flush()
    wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path="x.xlsx", source_type="template")
    db.add(wp)
    await db.flush()
    return wp.id


async def _world(db):
    """本年项目（2025，只有本年试算表）+ 上年项目（同企业代码 / 口径，2024 试算表）。"""
    cur = await _project(db, "本年")
    prior = await _project(db, "上年", year=YEAR - 1)
    db.add_all([_tb(cur, YEAR, "1121", "900"),
                _tb(prior, YEAR - 1, "1121", "800", opening="100"), _tb(prior, YEAR - 1, "1122", "200"),
                _tb(prior, YEAR - 1, "1123", "50"), _tb(prior, YEAR - 1, "1231-01", "30")])
    await _wp(db, cur)
    await db.commit()
    return cur, prior


# ── 上年数据来源（四种情形 + 原因） ────────────────────────────────────────────────────────


async def test_same_project_prior_year_tb_wins_over_prior_project():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, prior = await _world(db)
        db.add(_tb(cur, YEAR - 1, "1121", "777"))
        await db.commit()
        source = await resolve_prior_source(db, cur, YEAR)
        assert (source.project_id, source.year, source.same_project) == (cur, YEAR - 1, True)


async def test_explicit_link_then_company_code_same_scope_unique():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, prior = await _world(db)
        source = await resolve_prior_source(db, cur, YEAR)
        assert (source.project_id, source.same_project, source.reason) == (prior, False, "")
        # 显式关联优先于企业代码查找（关联的项目企业代码不同也认）；关联到已删除项目 ⇒ 回到企业代码查找
        linked = await _project(db, "显式上年", year=YEAR - 1, code="OTHER")
        db.add(_tb(linked, YEAR - 1, "1121", "1"))
        dead = await _project(db, "已删除", year=YEAR - 1, code="OTHER", deleted=True)
        cur_row = await db.get(Project, cur)
        cur_row.prior_year_project_id = linked
        await db.commit()
        assert (await find_prior_project(db, cur, YEAR)).project_id == linked
        cur_row.prior_year_project_id = dead
        await db.commit()
        assert (await find_prior_project(db, cur, YEAR)).project_id == prior
        # 口径不同的同企业代码项目不算候选
        await _project(db, "合并口径", year=YEAR - 1, scope="consolidated")
        await db.commit()
        assert (await find_prior_project(db, cur, YEAR)).project_id == prior


async def test_ambiguous_prior_projects_are_not_guessed():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, _ = await _world(db)
        await _project(db, "另一个上年", year=YEAR - 1)
        await db.commit()
        found = await find_prior_project(db, cur, YEAR)
        assert found.project_id is None and "不唯一" in found.reason and "C001" in found.reason
        source = await resolve_prior_source(db, cur, YEAR)
        assert source.project_id is None and "本项目没有 2024 年试算表" in source.reason and "不唯一" in source.reason


async def test_missing_company_code_or_prior_tb_is_reported():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        orphan = await _project(db, "无企业代码", code=None)
        await db.commit()
        assert "没有企业代码" in (await resolve_prior_source(db, orphan, YEAR)).reason
        cur = await _project(db, "本年2", code="C9")
        await _project(db, "上年无表", year=YEAR - 1, code="C9")
        await db.commit()
        assert (await resolve_prior_source(db, cur, YEAR)).reason == "上年项目没有 2024 年试算表"


# ── 字段定义（三层 + 审定表换列 + 白名单） ──────────────────────────────────────────────────


async def test_definition_layers_project_over_global_over_preset():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, _ = await _world(db)
        slot = "D1|核对|定义"
        wp_id = (await db.execute(WorkingPaper.__table__.select().where(WorkingPaper.project_id == cur))).first().id
        db.add(FormulaSetting(domain="wp", layer="global", scope="*", slot_key=slot,
                              definition={"expression": "TB('1122','期末余额')", "formula_type": "auto_calc"}))
        own = WpFormula(id=uuid.uuid4(), project_id=cur, wp_id=wp_id, sheet_name="核对", target_cell="定义",
                        expression="=TB('1123','期末余额')", formula_type="auto_calc", formula_source="custom")
        db.add(own)
        await db.commit()
        assert (await PriorWpFieldResolver(db, cur, YEAR).resolve("D1", "核对", "定义")).value == Decimal("50")
        await db.delete(own)
        await db.commit()
        assert (await PriorWpFieldResolver(db, cur, YEAR).resolve("D1", "核对", "定义")).value == Decimal("200")
        await db.execute(FormulaSetting.__table__.delete())
        await db.commit()
        assert (await PriorWpFieldResolver(db, cur, YEAR).resolve("D1", "核对", "定义")).value == Decimal("800")


async def test_audited_table_field_uses_unadjusted_slot_with_column_rewritten():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, _ = await _world(db)
        resolver = PriorWpFieldResolver(db, cur, YEAR)
        audited = await resolver.resolve("D1", SHEET, "审定数")
        assert (audited.value, audited.reason, audited.expression) == (Decimal("800"), "", "TB('1121','审定数')")
        opening = await resolver.resolve("D1", SHEET, "年初余额")  # 换列真的换了（期末 / 审定同值，用期初证明）
        assert (opening.value, opening.expression) == (Decimal("100"), "TB('1121','年初余额')")
        carrying = await resolver.resolve("D1", "附注披露信息", "期末账面价值")  # 本公式位自己的定义（备抵正数）
        assert carrying.value == Decimal("770")
        span = await resolver.resolve("D1", "明细表D1-2", "区间")  # TB_SUM → SUM_TB
        assert (span.value, span.expression) == (Decimal("1000"), "SUM_TB('1121~1122','期末余额')")


async def test_missing_or_non_recomputable_definitions_give_reasons_not_zero():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, _ = await _world(db)
        resolver = PriorWpFieldResolver(db, cur, YEAR)
        cases = {
            ("D1", SHEET, "上年账面价值"): "没有「上年账面价值」的取数定义",
            ("D1", "明细表D1-2", "审定数"): "没有「审定数」的取数定义",  # 该表无「未审数」公式位 ⇒ 不换列
            ("D1", "明细表D1-2", "占位"): "是占位（需人工填写）",
            ("D1", "明细表D1-2", "序时"): "用了 LEDGER",
            ("D1", "明细表D1-2", "套娃"): "用了 PREV",
            ("D1", "明细表D1-2", "引用"): "用了 WP",
            # 「未审数」定义里的单参 TB 换不到列：按缺省列取会把期末数当期初数（800 ≠ 100），不取
            ("D1", "单参表", "年初余额"): "不是「科目, 列」写法",
            ("D1", "混合表", "年初余额"): "不是「科目, 列」写法",  # 只要有一个换不到就不取
        }
        for key, reason in cases.items():
            hit = await resolver.resolve(*key)
            assert hit.value is None and reason in hit.reason, (key, hit)


# ── 三条求值路径同一口径 ───────────────────────────────────────────────────────────────


async def test_strict_path_wp_evaluator_uses_prior_year_value():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, _ = await _world(db)
        value, errs = await evaluate_wp_formula_expression(
            db, project_id=cur, year=YEAR, expression=f"={PREV_AUDITED} + TB('1121','期末余额')")
        assert (value, errs) == (Decimal("1700"), [])  # 上年 800（上年项目）+ 本年 900
        _, errs = await evaluate_wp_formula_expression(
            db, project_id=cur, year=YEAR, expression="PREV('D1','明细表D1-2','占位')")
        assert errs and "是占位" in errs[0], errs
        sub = await formula_ref_preload.substitute_prev_aux(
            "PREV('D1','附注披露信息','上年账面价值')", db=db, project_id=cur, year=YEAR)
        assert sub.missing and "没有「上年账面价值」的取数定义" in sub.missing[0]


async def test_preload_feeds_l1_kernel_and_missing_is_an_error_not_zero():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, _ = await _world(db)
        missing = "PREV('D1','明细表D1-2','序时')"
        gaps: list[str] = []
        ctx = await preload(db, cur, YEAR, [PREV_AUDITED, missing], gaps=gaps)
        assert ctx.prev_wp_data == {("D1", SHEET, "审定数"): Decimal("800")}
        assert formula_engine.execute(f"{PREV_AUDITED} + 1", ctx).value == Decimal("801")
        result = formula_engine.execute(f"{missing} + 1", ctx)
        assert not result.ok and any("用了 LEDGER" in e for e in result.errors), result.errors
        assert any("用了 LEDGER" in g for g in gaps), gaps
        # 降级 regex 路径与 AST 同一取值函数
        assert formula_engine._execute_regex(f"{PREV_AUDITED}+1", ctx).value == Decimal("801")
        degraded = formula_engine._execute_regex(f"{missing}+1", ctx)
        assert any("用了 LEDGER" in e for e in degraded.errors), degraded.errors


async def test_two_arg_prev_uses_shared_prior_source_and_honors_column():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur, _ = await _world(db)
        expr = "PREV('1121','年初余额') + PREV(TB('1121','期末余额'))"
        sub = await formula_ref_preload.substitute_prev_aux(expr, db=db, project_id=cur, year=YEAR)
        assert sub.missing == [] and "(100.00)" in sub.expression and "(800.00)" in sub.expression, sub
        ctx = await preload(db, cur, YEAR, [expr])
        assert formula_engine.execute(expr, ctx).value == Decimal("900")  # 列名生效（原先两项都取期末 = 1600）
        bad = formula_engine.execute("PREV('1121','不存在的列')", ctx)
        assert not bad.ok and "未注册" in bad.errors[0]


async def test_no_prior_source_is_reported_on_every_path():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        cur = await _project(db, "孤立", code="ALONE")
        await _wp(db, cur)
        db.add(_tb(cur, YEAR, "1121", "900"))
        await db.commit()
        _, errs = await evaluate_wp_formula_expression(db, project_id=cur, year=YEAR, expression=PREV_AUDITED)
        assert errs and "本项目没有 2024 年试算表" in errs[0] and "没有上年项目" in errs[0], errs
        gaps: list[str] = []
        ctx = await preload(db, cur, YEAR, [PREV_AUDITED, "PREV('1121','期末余额')"], gaps=gaps)
        result = formula_engine.execute(PREV_AUDITED, ctx)
        assert not result.ok and "没有上年项目" in result.errors[0]
        assert any(g.startswith("PREV 上年试算表：") for g in gaps), gaps


async def test_save_validation_does_not_flag_three_arg_prev_as_dangling(monkeypatch):
    """三参 PREV 不是本年目录里的地址：引用校验跳过它（两参 PREV 仍按试算表域校验）。"""
    from app.services.address_registry import address_registry

    async def _no_entries(self, *_a, **_k):
        return []

    # 在类上替换：在单例实例上 setattr 的话，monkeypatch 撤销时会把原方法写成实例属性留下来，
    # 之后别的用例在类上替换 _get_domain 都被它挡住（同进程跑 test_address_registry_limit 时实测取到真实地址）
    monkeypatch.setattr(type(address_registry), "_get_domain", _no_entries)
    issues = await address_registry.validate_formula_refs(None, "p", YEAR, f"{PREV_AUDITED} + PREV('1121','期末余额')")
    assert [i["ref"] for i in issues] == ["PREV('1121','期末余额')"]
