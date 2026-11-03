"""利润链存量发布工具（spec income-statement-lower-section-formulas 任务 5；ADR-ISL-03，决策项 D4）。

不连库的判据：目标取自种子（不自带公式文本）、四类动作判定、已知坏式逐字比对、归属行跳过、命令行参数。
写入形态（只读不写、``--apply`` 后等于目标、第二次 0 变更、第三种公式退出码 2）在 SQLite 真 ORM 的
``formula_settings._env`` 世界里直调工具函数验证 —— 共享库是真实业务库，本 spec 不在其中造写入。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from app.models.report_models import FinancialReportType, ReportConfig
from scripts.fix.publish_income_statement_chain import (
    ACTION_ALREADY,
    ACTION_BAD,
    ACTION_EMPTY,
    ACTION_INPUT,
    ACTION_SOURCE,
    ACTION_THIRD,
    ATTRIBUTION_CODES,
    KNOWN_BAD,
    PENDING_ACTIONS,
    STANDARDS,
    ArgumentProblem,
    SeedProblem,
    Target,
    ThirdFormulaFound,
    apply_publish,
    classify,
    dry_run,
    main,
    parse_args,
    run_session,
    seed_targets,
)
from tests.formula_settings._env import make_db

IS = FinancialReportType.income_statement
SEED = Path(__file__).resolve().parents[2] / "data" / "report_config_seed.json"
_WRITE_SQL = re.compile(r"^\s*(?:INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE)


def seed_rows_by_key() -> dict[tuple[str, str], dict]:
    blocks = json.loads(SEED.read_text(encoding="utf-8-sig"))
    return {(b["applicable_standard"], r["row_code"]): r for b in blocks
            if b.get("report_type") == IS.value and b.get("applicable_standard") in STANDARDS
            for r in b["rows"]}


# ─── 目标来自种子（不自带公式文本）──────────────────────────────────────────────


def test_targets_equal_seed_formulas_exactly():
    targets = seed_targets()
    seeded = seed_rows_by_key()
    assert targets, "种子没有解析出任何目标：守卫空转"
    for (standard, code), target in targets.items():
        row = seeded[(standard, code)]
        assert target.formula == ((row.get("formula") or "").strip() or None)
        assert target.formula_source == (row.get("formula_source") or "").strip()


def test_attribution_rows_are_skipped():
    """母 spec 的归属行（决策项 X2 另有工具）不在本工具范围内。"""
    targets = seed_targets()
    for standard, codes in ATTRIBUTION_CODES.items():
        for code in codes:
            assert (standard, code) not in targets, f"{standard} {code} 属归属行，本工具不应接管"


def test_all_four_standards_have_targets():
    targets = seed_targets()
    for standard in STANDARDS:
        assert [key for key in targets if key[0] == standard], f"{standard} 没有目标行"


def test_known_bad_rows_all_have_seed_targets():
    """已知坏式登记的每一行都必须在种子里有目标，否则 --apply 无从比对。"""
    targets = seed_targets()
    assert set(KNOWN_BAD) <= set(targets)


def test_seed_problem_when_standard_missing(tmp_path):
    partial = [b for b in json.loads(SEED.read_text(encoding="utf-8-sig"))
               if b.get("applicable_standard") != "listed_standalone"]
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SeedProblem, match="缺这些准则"):
        seed_targets(path)


def test_seed_problem_when_no_target_present(tmp_path):
    """种子利润表公式与来源全空 ⇒ 报错而不是「无事可做」静默成功。"""
    blocks = json.loads(SEED.read_text(encoding="utf-8-sig"))
    for block in blocks:
        if block.get("report_type") == IS.value:
            for row in block["rows"]:
                row["formula"] = None
                row["formula_source"] = None
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SeedProblem):
        seed_targets(path)


# ─── 四类动作判定 ───────────────────────────────────────────────────────────────


def _target(
    formula: str | None = "ROW('IS-044')-ROW('IS-045')",
    known_bad: str | None = None,
    source: str = "identity",
) -> Target:
    return Target("soe_standalone", "IS-046", "五、净利润", formula, source, known_bad)


@pytest.mark.parametrize(("old", "old_source", "expected"), [
    ("ROW('IS-044')-ROW('IS-045')", "identity", ACTION_ALREADY),
    ("  ROW('IS-044')-ROW('IS-045')  ", "identity", ACTION_ALREADY),
    ("ROW('IS-044')-ROW('IS-045')", None, ACTION_SOURCE),
    (None, None, ACTION_EMPTY),
    ("", None, ACTION_EMPTY),
    ("   ", None, ACTION_EMPTY),
    ("ROW('IS-044')", None, ACTION_THIRD),
], ids=["already", "already_padded", "source_only", "none", "empty", "blank", "third"])
def test_classify_without_known_bad(old, old_source, expected):
    assert classify(old, old_source, _target()) == expected


@pytest.mark.parametrize(("old", "expected"), [
    ("SUM_ROW('IS-054','IS-072')", ACTION_BAD),
    ("SUM_ROW('IS-054','IS-072') ", ACTION_THIRD),  # 逐字比对：带尾空格不算已知坏式
    ("SUM_ROW('IS-054','IS-071')", ACTION_THIRD),
], ids=["known_bad", "known_bad_padded", "other"])
def test_classify_with_known_bad(old, expected):
    assert classify(old, None, _target(known_bad="SUM_ROW('IS-054','IS-072')")) == expected


def test_known_bad_texts_match_design_record():
    """已知坏式文本是 design §1 第 4、5 行的现算结论：改掉它就不该再被 --apply 自动改写。"""
    assert len(KNOWN_BAD) == 7, "四条综合收益总额 + 三条利润总额坏式必须全部登记"
    assert KNOWN_BAD[("soe_consolidated", "IS-044")] == "SUM_ROW('IS-041','IS-043')"
    assert KNOWN_BAD[("soe_consolidated", "IS-073")] == "SUM_ROW('IS-054','IS-072')"
    assert KNOWN_BAD[("listed_consolidated", "IS-022")] == "SUM_ROW('IS-020','IS-021')"
    assert KNOWN_BAD[("listed_consolidated", "IS-050")] == "SUM_ROW('IS-032','IS-049')"


# ─── 写入形态（SQLite 真 ORM 世界）──────────────────────────────────────────────


async def _seed_world(factory, *, formulas: dict[tuple[str, str], str | None] | None = None) -> None:
    """按种子行次建四套利润表准则行；``formulas`` 指定的行用给定公式，其余留空。"""
    overrides = formulas or {}
    async with factory() as db:
        for (standard, code), row in seed_rows_by_key().items():
            db.add(ReportConfig(
                report_type=IS, row_code=code, row_name=row.get("row_name") or code,
                row_number=row["row_number"], indent_level=row.get("indent_level", 0),
                is_total_row=bool(row.get("is_total_row")),
                formula=overrides.get((standard, code)), formula_category="auto_calc",
                applicable_standard=standard, formula_version=1,
            ))
        await db.commit()


async def _definitions(factory) -> dict[tuple[str, str], tuple[str | None, str | None]]:
    async with factory() as db:
        rows = (await db.execute(sa.select(
            ReportConfig.applicable_standard, ReportConfig.row_code,
            ReportConfig.formula, ReportConfig.formula_source,
        ).where(ReportConfig.report_type == IS))).all()
    return {(r[0], r[1]): (r[2], r[3]) for r in rows}


async def _formulas(factory) -> dict[tuple[str, str], str | None]:
    return {key: value[0] for key, value in (await _definitions(factory)).items()}


@pytest.mark.asyncio
async def test_dry_run_lists_pending_and_writes_nothing():
    async with make_db() as factory:
        await _seed_world(factory)
        before = await _formulas(factory)
        writes: list[str] = []
        async with factory() as db:
            bind = db.get_bind()
            sync_engine = getattr(bind, "sync_engine", bind)

            @event.listens_for(sync_engine, "before_cursor_execute")
            def _spy(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
                if _WRITE_SQL.match(statement):
                    writes.append(statement)

            report = await dry_run(db, database="test")
            event.remove(sync_engine, "before_cursor_execute", _spy)
        assert report["mode"] == "dry-run"
        assert report["counts"][ACTION_EMPTY] > 0, "没有待发布公式行：用例空转"
        assert report["counts"][ACTION_INPUT] > 0, "没有待登记输入行：用例空转"
        assert report["counts"][ACTION_THIRD] == 0
        assert writes == [], f"只读模式有写语句：{writes}"
        assert await _formulas(factory) == before


@pytest.mark.asyncio
async def test_apply_publishes_all_targets_then_is_idempotent():
    async with make_db() as factory:
        await _seed_world(factory)
        targets = seed_targets()
        async with factory() as db:
            report = await apply_publish(db, database="test")
            await db.commit()
        assert report["counts"][ACTION_EMPTY] > 0
        after = await _definitions(factory)
        wrong = {
            key: after[key] for key, target in targets.items()
            if after[key] != (target.formula, target.formula_source)
        }
        assert wrong == {}, f"发布后这些行的公式 / 来源不等于目标：{wrong}"

        async with factory() as db:
            again = await apply_publish(db, database="test")
            await db.commit()
        assert again["counts"][ACTION_EMPTY] == 0 and again["counts"][ACTION_BAD] == 0
        assert again["counts"][ACTION_SOURCE] == 0 and again["counts"][ACTION_INPUT] == 0
        assert again["publishes"] == [], "第二次仍调用了 publish_global"
        assert again["counts"][ACTION_ALREADY] == len(targets)
        assert await _definitions(factory) == after, "第二次改动了数据"


@pytest.mark.asyncio
async def test_apply_rewrites_known_bad_rows():
    bad = {key: text for key, text in KNOWN_BAD.items()}
    async with make_db() as factory:
        await _seed_world(factory, formulas=bad)
        async with factory() as db:
            report = await apply_publish(db, database="test")
            await db.commit()
        assert report["counts"][ACTION_BAD] == len(bad), f"已知坏式未被识别：{report['counts']}"
        after = await _definitions(factory)
        targets = seed_targets()
        for key in bad:
            assert after[key] == (targets[key].formula, targets[key].formula_source)


@pytest.mark.asyncio
async def test_third_definition_blocks_apply_and_writes_nothing():
    """第三种定义（有人改过）⇒ 不改、报错；本次事务不留任何写入。"""
    hand_edited = {("soe_standalone", "IS-046"): "ROW('IS-044')"}
    async with make_db() as factory:
        await _seed_world(factory, formulas=hand_edited)
        before = await _formulas(factory)
        async with factory() as db:
            with pytest.raises(ThirdFormulaFound, match="第三种定义"):
                await apply_publish(db, database="test")
            await db.rollback()
        assert await _formulas(factory) == before


@pytest.mark.asyncio
async def test_run_session_returns_two_for_third_definition_in_dry_run():
    hand_edited = {("soe_standalone", "IS-046"): "ROW('IS-044')"}
    async with make_db() as factory:
        await _seed_world(factory, formulas=hand_edited)
        async with factory() as db:
            code, report = await run_session(db, apply=False, database="test")
        assert code == 2
        assert [r["row_code"] for r in report["third_formula"]] == ["IS-046"]


@pytest.mark.asyncio
async def test_run_session_rolls_back_and_returns_two_on_third_definition_apply():
    hand_edited = {("listed_standalone", "IS-024"): "ROW('IS-022')"}
    async with make_db() as factory:
        await _seed_world(factory, formulas=hand_edited)
        before = await _formulas(factory)
        async with factory() as db:
            code, report = await run_session(db, apply=True, database="test")
        assert code == 2 and "第三种定义" in report["error"]
        assert await _formulas(factory) == before


@pytest.mark.asyncio
async def test_missing_row_is_listed_not_inserted():
    """库里缺某一行 ⇒ 列出来、不新增行。"""
    async with make_db() as factory:
        await _seed_world(factory)
        async with factory() as db:
            await db.execute(sa.delete(ReportConfig).where(
                ReportConfig.applicable_standard == "soe_standalone", ReportConfig.row_code == "IS-046"))
            await db.commit()
        async with factory() as db:
            report = await dry_run(db, database="test")
        assert [(r["standard"], r["row_code"]) for r in report["missing_rows"]] == [("soe_standalone", "IS-046")]
        async with factory() as db:
            exists = (await db.execute(sa.select(sa.func.count()).select_from(ReportConfig).where(
                ReportConfig.applicable_standard == "soe_standalone", ReportConfig.row_code == "IS-046"))).scalar_one()
        assert exists == 0, "工具新增了库里原本没有的行"


# ─── 命令行 ────────────────────────────────────────────────────────────────────


def test_unknown_argument_is_rejected_in_chinese():
    with pytest.raises(ArgumentProblem, match="无法识别的参数"):
        parse_args(["--nope"])


def test_json_path_must_not_be_directory(tmp_path):
    with pytest.raises(ArgumentProblem, match="是目录"):
        parse_args(["--json", str(tmp_path)])


def test_json_parent_directory_must_exist(tmp_path):
    with pytest.raises(ArgumentProblem, match="目录不存在"):
        parse_args(["--json", str(tmp_path / "missing" / "out.json")])


def test_main_returns_two_on_bad_argument(capsys):
    assert main(["--nope"]) == 2
    assert "退出码 2" in capsys.readouterr().out


def test_default_mode_is_read_only():
    assert parse_args([]).apply is False
    assert parse_args(["--apply"]).apply is True


def test_pending_actions_are_exactly_safe_states():
    """只有空公式、已知坏式、来源补齐、空输入行登记可自动改；第三种定义绝不进集合。"""
    assert set(PENDING_ACTIONS) == {ACTION_EMPTY, ACTION_BAD, ACTION_SOURCE, ACTION_INPUT}


@pytest.mark.parametrize(("old", "old_source", "expected"), [
    (None, "input", ACTION_ALREADY),
    (None, None, ACTION_INPUT),
    ("", "", ACTION_INPUT),
    ("TB('6603','本期发生额')", "special", ACTION_THIRD),
    (None, "custom", ACTION_THIRD),
], ids=["input_already", "input_missing", "input_blank", "input_has_formula", "input_unknown_source"])
def test_classify_input_row(old, old_source, expected):
    """输入行只能从「空公式 + 空来源」自动登记；已有公式 / 未知来源绝不清除。"""
    assert classify(old, old_source, _target(formula=None, source="input")) == expected
