"""S9 真 PostgreSQL 回滚验证（spec income-statement-lower-section-formulas 任务 4~6）。

目标库来自 ``DATABASE_URL``；``GT_REQUIRE_PG=1`` 时不可静默跳过。所有写入都在
``pg_tx_session`` 的外层事务内，测试退出必回滚：临时【测试】项目、试算表行、对全局
``report_config`` 的候选公式覆盖、生成的 ``financial_report`` / run 行都不会提交。

两层验证：

1. 不依赖 S5 迁移的计算层：真 PG 项目 + 真 ``trial_balance`` → ``ReportFormulaParser`` →
   生产拓扑序 + ``compute_row``，四套逐行对独立金标准；合并 ``report_values`` 同值；全部目标公式线性。
2. 完整 ``ReportEngine.generate_all_reports``：只有共享库已执行 formula-hub X1（S5 的
   ``financial_report.provenance/run_id`` + ``report_generation_run``）才可运行。迁移未执行时明确 xfail，
   不能把 ORM 与 schema 不一致误报成 S9 缺陷；X1 执行后自动进入真实生成断言。
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from app.models.audit_platform_models import TrialBalance
from app.models.core import Project
from app.models.report_models import FinancialReportType, ReportConfig
from app.services.account_chart_service import _infer_category
from app.services.consol_report_values import ReportRow, report_values, validate_linear
from app.services.formula_settings.effective_report import load_effective_report_configs
from app.services.report_engine import ReportEngine, ReportFormulaParser
from app.services.report_eval_order import eval_order
from app.services.report_row_compute import RowScope, compute_row
from tests.formula_hub._pg_harness import pg_tx_session
from tests.is_lower_section.gold_is_evaluator import GoldRow, cents, evaluate
from tests.is_lower_section.test_income_statement_gold_parity import (
    STANDARDS,
    TRIAL_BALANCE,
    gold_values,
    manual_inputs,
)

pytestmark = pytest.mark.pg_only
SEED = Path(__file__).resolve().parents[2] / "data" / "report_config_seed.json"
IS = FinancialReportType.income_statement
YEAR = 2025


def _seed_blocks() -> dict[str, list[dict]]:
    raw = json.loads(SEED.read_text(encoding="utf-8-sig"))
    return {block["applicable_standard"]: block["rows"] for block in raw
            if block.get("report_type") == IS.value and block.get("applicable_standard") in STANDARDS}


async def _apply_candidate_definitions(db) -> None:
    """把候选种子公式 / input 来源写进本测试外层事务；每行必须命中一次，不新增、不提交。"""
    for standard, rows in _seed_blocks().items():
        for row in rows:
            formula = (row.get("formula") or "").strip() or None
            source = (row.get("formula_source") or "").strip() or None
            if formula is None and source != "input":
                continue
            result = await db.execute(
                sa.update(ReportConfig)
                .where(
                    ReportConfig.applicable_standard == standard,
                    ReportConfig.report_type == IS,
                    ReportConfig.row_code == row["row_code"],
                    ReportConfig.is_deleted == sa.false(),
                )
                .values(formula=formula, formula_source=source)
            )
            assert result.rowcount == 1, f"{standard} {row['row_code']} 存量 report_config 未唯一命中"
    await db.flush()


async def _add_world(db) -> uuid.UUID:
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name=f"【测试】S9-PG-{project_id.hex[:8]}",
        client_name="【测试】S9 利润链真 PG 回滚项目",
        audit_period_start=date(YEAR, 1, 1),
        audit_period_end=date(YEAR, 12, 31),
        audit_year=YEAR,
        template_type="soe",
        report_scope="standalone",
        company_code="S9PG",
    )
    db.add(project)
    # 无 ORM relationship 时 SQLAlchemy 不保证两个 mapper 按 FK 顺序 flush；先落项目再加试算表，
    # 否则真 PG 会先 INSERT trial_balance 并触发 FK（SQLite 默认未开外键，测不出来）。
    await db.flush([project])
    for code, amount in TRIAL_BALANCE.items():
        db.add(TrialBalance(
            id=uuid.uuid4(), project_id=project_id, year=YEAR, company_code="S9PG",
            standard_account_code=code, account_name=code,
            account_category=_infer_category(code, ""),
            unadjusted_amount=amount, audited_amount=amount, opening_balance=Decimal("0"),
        ))
    await db.flush()
    return project_id


async def _configs(db, project_id: uuid.UUID, standard: str):
    configs = await load_effective_report_configs(db, standard=standard, project_id=project_id)
    return [cfg for cfg in configs if cfg.report_type == IS]


async def _compute_pg(db, project_id: uuid.UUID, standard: str) -> tuple[dict[str, Decimal], list]:
    configs = await _configs(db, project_id, standard)
    plan = eval_order(configs)
    assert plan.cycles == (), f"{standard} 真 PG 有循环：{plan.cycles}"
    scope = RowScope.of(configs, cycles=plan.cycles)
    cache = scope.start_cache()
    inputs = manual_inputs(standard)
    cache.update(inputs)
    parser = ReportFormulaParser(db, project_id, YEAR)
    values: dict[str, Decimal] = {}
    outcomes = []
    for config in plan.order:
        if config.row_code in inputs:
            values[config.row_code] = inputs[config.row_code]
            continue
        outcome = await compute_row(parser, config, cache, mode="audited", scope=scope)
        assert outcome.ok, f"{standard} {config.row_code} 真 PG 计算失败：{outcome.errors}"
        values[config.row_code] = cents(outcome.value)
        outcomes.append(outcome)
    return values, outcomes


async def test_four_standards_pg_match_independent_gold_and_are_linear():
    async with pg_tx_session() as db:
        project_id = await _add_world(db)
        await _apply_candidate_definitions(db)
        for standard in STANDARDS:
            produced, _outcomes = await _compute_pg(db, project_id, standard)
            gold = gold_values(standard)
            mismatch = {code: (produced.get(code), value) for code, value in gold.items()
                        if produced.get(code) != value}
            assert mismatch == {}, f"{standard} 真 PG vs 独立金标准不符：{mismatch}"

            configs = await _configs(db, project_id, standard)
            formulas = [cfg.formula for cfg in configs if (cfg.formula or "").strip()]
            invalid = {cfg.row_code: validate_linear(cfg.formula) for cfg in configs
                       if (cfg.formula or "").strip() and validate_linear(cfg.formula) is not None}
            assert formulas and invalid == {}, f"{standard} 有非线性 / 不可解析公式：{invalid}"

            # 合并读时计算没有手工输入载荷，故与「手工输入行 = 0」的独立金标准对拍。
            rows = [ReportRow.from_config(cfg) for cfg in configs]
            categories = {code: _infer_category(code, "").value for code in TRIAL_BALANCE}
            consolidated = await report_values(rows, TRIAL_BALANCE, categories=categories)
            no_manual_gold = evaluate(
                [GoldRow(cfg.row_code, cfg.row_number, cfg.formula) for cfg in configs], TRIAL_BALANCE)
            assert no_manual_gold.unparsed == {} and no_manual_gold.cycles == ()
            formula_codes = {cfg.row_code for cfg in configs if (cfg.formula or "").strip()}
            mismatch = {
                code: (consolidated[code].amount, no_manual_gold.values[code], consolidated[code].reason)
                for code in sorted(formula_codes)
                if consolidated[code].amount != no_manual_gold.values[code]
            }
            assert mismatch == {}, f"{standard} 合并读时计算 vs 独立金标准不符：{mismatch}"


async def _full_generation_schema_ready(db) -> tuple[bool, list[str]]:
    columns = set((await db.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='financial_report'
    """))).scalars())
    table = (await db.execute(text("SELECT to_regclass('public.report_generation_run')"))).scalar_one()
    missing = sorted({"provenance", "run_id"} - columns)
    if table is None:
        missing.append("table:report_generation_run")
    return not missing, missing


async def test_full_report_engine_generation_after_formula_hub_x1():
    async with pg_tx_session() as db:
        ready, missing = await _full_generation_schema_ready(db)
        if not ready:
            pytest.xfail(
                "formula-hub 决策项 X1 尚未执行，共享库缺 S5 schema，完整 ReportEngine 无法运行："
                + "、".join(missing)
            )
        project_id = await _add_world(db)
        await _apply_candidate_definitions(db)
        # 选单体口径：手工输入行在全量生成时按既有 D5 语义清零，故与无手工输入的金标准对拍。
        results = await ReportEngine(db).generate_all_reports(
            project_id, YEAR, "soe_standalone", skip_recalc=True, publish_events=False,
        )
        rows = {row["row_code"]: row for row in results[IS.value]}
        configs = await _configs(db, project_id, "soe_standalone")
        gold = evaluate([GoldRow(cfg.row_code, cfg.row_number, cfg.formula) for cfg in configs], TRIAL_BALANCE)
        assert gold.unparsed == {} and gold.cycles == ()
        target_codes = {cfg.row_code for cfg in configs if (cfg.formula or "").strip()}
        mismatch = {
            code: (rows[code]["current_period_amount"], str(gold.values[code]))
            for code in sorted(target_codes)
            if Decimal(rows[code]["current_period_amount"]) != gold.values[code]
        }
        assert mismatch == {}, f"完整 ReportEngine vs 金标准不符：{mismatch}"
        assert rows["IS-046"]["current_period_amount"] not in (None, "0", "0.00")


async def _reset_publish_targets_to_old_state(db) -> None:
    """仅在外层回滚事务内：公式行退成空 / 已知坏式，输入行来源清空，构造发布前世界。"""
    from scripts.fix.publish_income_statement_chain import KNOWN_BAD, seed_targets

    for key, target in seed_targets().items():
        old_formula = KNOWN_BAD.get(key) if target.formula is not None else None
        result = await db.execute(
            sa.update(ReportConfig)
            .where(
                ReportConfig.applicable_standard == target.standard,
                ReportConfig.report_type == IS,
                ReportConfig.row_code == target.row_code,
                ReportConfig.is_deleted == sa.false(),
            )
            .values(formula=old_formula, formula_source=None)
        )
        assert result.rowcount == 1, key
    await db.flush()


async def _publish_count(prefix: str) -> int:
    from tests.formula_hub._pg_harness import make_engine

    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return int((await conn.execute(text(
                "SELECT count(*) FROM formula_publish WHERE request_id LIKE :prefix"
            ), {"prefix": f"{prefix}%"})).scalar_one())
    finally:
        await engine.dispose()


async def test_publish_tool_apply_and_replay_in_pg_rollback(monkeypatch):
    """正式发布内核在真 PG 外层回滚事务：首次全量发布、第二次 0 变更；退出后发布记录 / 定义改动均不落库。"""
    import scripts.fix.publish_income_statement_chain as tool

    unique_prefix = f"s9pg-{uuid.uuid4().hex[:8]}-"
    monkeypatch.setattr(tool, "REQUEST_ID_PREFIX", unique_prefix)
    assert await _publish_count(unique_prefix) == 0
    async with pg_tx_session() as db:
        await _reset_publish_targets_to_old_state(db)
        code, first = await tool.run_session(db, apply=True, database="pg-rollback")
        assert code == 0, first
        assert first["counts"][tool.ACTION_EMPTY] > 0
        assert first["counts"][tool.ACTION_BAD] == len(tool.KNOWN_BAD)
        assert first["counts"][tool.ACTION_INPUT] > 0
        assert first["counts"][tool.ACTION_THIRD] == 0
        assert len(first["publishes"]) == len(STANDARDS)

        code, second = await tool.run_session(db, apply=True, database="pg-rollback")
        assert code == 0, second
        assert second["counts"][tool.ACTION_ALREADY] == len(tool.seed_targets())
        assert second["publishes"] == [], "第二次仍写发布记录：工具不幂等"
    assert await _publish_count(unique_prefix) == 0, "外层事务退出后仍有发布记录：真 PG 回滚失效"


async def test_publish_tool_third_definition_returns_two_without_writing(monkeypatch):
    """真 PG：输入行若已有公式，属于第三种定义，退出码 2；不得自动清掉。"""
    import scripts.fix.publish_income_statement_chain as tool

    unique_prefix = f"s9third-{uuid.uuid4().hex[:8]}-"
    monkeypatch.setattr(tool, "REQUEST_ID_PREFIX", unique_prefix)
    input_target = next(target for target in tool.seed_targets().values() if target.formula is None)
    async with pg_tx_session() as db:
        await _reset_publish_targets_to_old_state(db)
        await db.execute(
            sa.update(ReportConfig)
            .where(
                ReportConfig.applicable_standard == input_target.standard,
                ReportConfig.report_type == IS,
                ReportConfig.row_code == input_target.row_code,
            )
            .values(formula="TB('9999','本期发生额')", formula_source="custom")
        )
        await db.flush()
        code, report = await tool.run_session(db, apply=True, database="pg-rollback")
        assert code == 2 and "第三种定义" in report["error"]
    assert await _publish_count(unique_prefix) == 0
