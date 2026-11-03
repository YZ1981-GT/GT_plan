"""利润表归属行种子（spec formula-hub-integrity-closure 任务 18 第一段 B；需求 6.1、6.2、6.4、6.5；ADR-FHIC-23；D3、D14）。

需求 6.1（唯一权威文本）按行名写成 :data:`ATTRIBUTION`：国企两套 IS-074 = IS-048 + IS-054、合并 IS-075 = IS-049 + IS-072、
单体 IS-075 无公式；上市两套 IS-051 = IS-029 + IS-032、合并 IS-052 = IS-030 + IS-049、单体 IS-052 无公式。

- 种子：按行名定位合计行，公式（只许 ``ROW`` 相加）引用的行次与行名都与需求 6.1 一致；单体两条无公式。
- 种子加载路径（``POST /api/report-config/seed`` 的生产调用顺序：``load_seed_data`` → commit → ``fill_all_formulas`` → commit；
  SQLite 真 ORM）：新库 —— 6 行按种子原样插入（``load_seed_data`` 直写，不经同步内核），``fill_all_formulas`` 跳过已有公式的
  行 ⇒ 这些公式位不在任何 ``source="seed"`` 发布记录里（发布记录只含 fill 自动填出的公式位）；已存在的行（快照库坏式 / 空公式）
  —— 种子不覆盖。⇒ 已有库的 8 行要改只能经同步内核发布（任务 19 升级工具，决策项 X2）。
- 真 PG ``test_test_project_recalc``（需求 6.4、6.5）：``pg_tx`` 内新建【测试】项目（国企合并、上市合并各一），把种子里的归属行
  定义经 ``publish_global(domain="report", source="seed")`` 发布到该准则（留发布记录）→ 生成一次：合计行带 warning
  「组成行 … 未定义公式」→ 经项目层适配（``save_overrides``）给组成行写字面量 → 生产报表引擎重算：合计行 = 测试内按行名独立求和。
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from app.models.core import Project
from app.models.formula_setting_models import FormulaPublish
from app.models.report_models import FinancialReportType, ReportConfig
from app.services.formula_settings.project_ops import save_overrides
from app.services.formula_settings.publish import publish_global
from app.services.report_config_service import ReportConfigService
from app.services.report_engine import ReportEngine
from app.services.report_formula_service import report_formula_service
from app.services.report_freshness import CALC_VERSION
from scripts.fix.republish_report_seed_rows import KNOWN_BAD  # 快照库 8 行现存原文（任务 19 升级工具的同一份常量）
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX
from tests.formula_hub._report_definition_rows import require_snapshot, seed_blocks
from tests.formula_settings._env import make_db

IS = "income_statement"
YEAR = 2025
SOE_PARENT = ("IS-074", "归属于母公司所有者的综合收益总额",
              (("IS-048", "1.归属于母公司所有者的净利润"), ("IS-054", "归属于母公司所有者的其他综合收益的税后净额")))
SOE_MINOR = ("IS-075", "*归属于少数股东的综合收益总额",
             (("IS-049", "*2.少数股东损益"), ("IS-072", "*归属于少数股东的其他综合收益的税后净额")))
LISTED_PARENT = ("IS-051", "归属于母公司股东的综合收益总额",
                 (("IS-029", "其中：归属于母公司股东的净利润（净亏损以“-”号填列）"),
                  ("IS-032", "归属于母公司股东的其他综合收益的税后净额")))
LISTED_MINOR = ("IS-052", "归属于少数股东的综合收益总额",
                (("IS-030", "少数股东损益（净亏损以“-”号填列）"), ("IS-049", "归属于少数股东的其他综合收益的税后净额")))
#: 需求 6.1：准则 → ((合计行次, 合计行名, ((组成行次, 组成行名), …) 或 None = 无公式), …)
ATTRIBUTION = {
    "soe_consolidated": (SOE_PARENT, SOE_MINOR),
    "soe_standalone": (SOE_PARENT, (*SOE_MINOR[:2], None)),
    "listed_consolidated": (LISTED_PARENT, LISTED_MINOR),
    "listed_standalone": (LISTED_PARENT, (*LISTED_MINOR[:2], None)),
}
ROW_SUM = re.compile(r"ROW\([ \t]*'[^']+'[ \t]*\)(?:[ \t]*\+[ \t]*ROW\([ \t]*'[^']+'[ \t]*\))*")
ROW_CODE = re.compile(r"ROW\([ \t]*'([^']+)'[ \t]*\)")
DEFINITION_FIELDS = ("formula", "formula_category", "formula_description", "formula_source")


def _seed_is_rows(standard: str) -> list[dict]:
    rows = [b["rows"] for b in seed_blocks() if b["report_type"] == IS and b["applicable_standard"] == standard]
    assert len(rows) == 1, f"种子里 {standard} 利润表块 {len(rows)} 个"
    return rows[0]


def _one(rows: list[dict], key: str, value: str) -> dict | None:
    hits = [r for r in rows if r.get(key) == value]
    return hits[0] if len(hits) == 1 else None


# ─── 种子文本（非 PG）──────────────────────────────────────────────────────────


def test_seed_attribution_rows_follow_requirement_6_1():
    problems: list[str] = []
    for std, totals in ATTRIBUTION.items():
        rows = _seed_is_rows(std)
        for code, name, parts in totals:
            total = _one(rows, "row_name", name)
            if total is None or (total["row_code"], total.get("is_total_row")) != (code, True):
                problems.append(f"{std}「{name}」按行名没定位到恰 1 条合计行 {code}：{total}")
                continue
            formula = total.get("formula")
            if parts is None:
                if formula is not None:
                    problems.append(f"{std} {code}「{name}」应无公式，现为 {formula!r}")
                continue
            if not isinstance(formula, str) or not ROW_SUM.fullmatch(formula.strip()):
                problems.append(f"{std} {code}「{name}」公式应只是 ROW 相加，现为 {formula!r}")
                continue
            got = sorted((ref, (_one(rows, "row_code", ref) or {}).get("row_name")) for ref in ROW_CODE.findall(formula))
            if got != sorted(parts):
                problems.append(f"{std} {code}「{name}」{formula} 引用 {got} ≠ 需求 6.1 {sorted(parts)}")
    assert problems == [], problems


# ─── 种子加载路径（SQLite 真 ORM）────────────────────────────────────────────────


TARGET_SLOTS = {f"{IS}:{code}" for _, code in KNOWN_BAD}


async def _seed_endpoint_calls(factory) -> int:
    """``POST /api/report-config/seed`` 的生产调用顺序（路由 ``load_seed_data``；其后只发事件）。"""
    async with factory() as db:
        inserted = await ReportConfigService(db).load_seed_data()
        await db.commit()
    async with factory() as db:
        await report_formula_service.fill_all_formulas(db, standard="all", user_id=None)
        await db.commit()
    return inserted


async def _target_rows(db) -> dict[tuple[str, str], ReportConfig]:
    rows = (await db.execute(sa.select(ReportConfig).where(
        ReportConfig.report_type == FinancialReportType.income_statement, ReportConfig.is_deleted == sa.false(),
    ))).scalars().all()
    return {(r.applicable_standard, r.row_code): r for r in rows if (r.applicable_standard, r.row_code) in KNOWN_BAD}


@pytest.mark.parametrize("scenario", ["new", "existing_bad", "existing_null"])
async def test_seed_load_path_inserts_new_rows_and_keeps_existing(scenario):
    seed_total = sum(len(b["rows"]) for b in seed_blocks())
    seed_formula = {(std, code): (_one(_seed_is_rows(std), "row_code", code) or {}).get("formula") for std, code in KNOWN_BAD}
    async with make_db() as factory:
        if scenario != "new":  # 已有库：先建行，再把 8 行改成快照库坏式 / 空公式
            async with factory() as db:
                await ReportConfigService(db).load_seed_data()
                for key, row in (await _target_rows(db)).items():
                    row.formula = KNOWN_BAD[key] if scenario == "existing_bad" else None
                await db.commit()
        inserted = await _seed_endpoint_calls(factory)
        async with factory() as db:
            after = {key: row.formula for key, row in (await _target_rows(db)).items()}
            publishes = (await db.execute(sa.select(FormulaPublish))).scalars().all()
    expected = {"new": seed_formula, "existing_bad": KNOWN_BAD, "existing_null": dict.fromkeys(KNOWN_BAD)}[scenario]
    assert inserted == (seed_total if scenario == "new" else 0)
    assert after == expected, f"{scenario}：8 行加载后 {after}"
    seed_scopes = {p.scope for p in publishes if p.source == "seed" and p.target == "global"}
    assert seed_scopes == set(ATTRIBUTION), f"fill_all_formulas 没经同步内核发布（{seed_scopes}）：断言空转"
    touched = sorted({(p.scope, c.get("slot_key")) for p in publishes for c in (p.change_set or [])
                      if c.get("slot_key") in TARGET_SLOTS})
    assert touched == [], f"{scenario}：归属行公式位出现在发布记录里 {touched}"


# ─── 【测试】项目重算（真 PG，需求 6.4、6.5）──────────────────────────────────────


#: 组成行（按行名）→ 字面量公式（含负数与两位小数）
LITERALS = {
    "1.归属于母公司所有者的净利润": "1234.56", "归属于母公司所有者的其他综合收益的税后净额": "-200.07",
    "*2.少数股东损益": "88.10", "*归属于少数股东的其他综合收益的税后净额": "11.02",
    "其中：归属于母公司股东的净利润（净亏损以“-”号填列）": "5000.01", "归属于母公司股东的其他综合收益的税后净额": "0.99",
    "少数股东损益（净亏损以“-”号填列）": "-300.50", "归属于少数股东的其他综合收益的税后净额": "45.25",
}


async def _db_is_rows(db, standard: str) -> dict[str, ReportConfig]:
    rows = (await db.execute(sa.select(ReportConfig).where(
        ReportConfig.applicable_standard == standard, ReportConfig.is_deleted == sa.false(),
        ReportConfig.report_type == FinancialReportType.income_statement))).scalars().all()
    names = [r.row_name for r in rows]
    return {r.row_name: r for r in rows if names.count(r.row_name) == 1}


async def _stored(db, project_id) -> dict[str, dict]:
    rows = (await db.execute(text(
        "SELECT row_code, current_period_amount, is_stale, calc_error, calc_version, formula_used FROM financial_report "
        "WHERE project_id = :pid AND year = :year AND report_type = 'income_statement' AND is_deleted = false"),
        {"pid": project_id, "year": YEAR})).mappings().all()
    return {r["row_code"]: dict(r) for r in rows}


@pytest.mark.pg_only
@pytest.mark.parametrize("standard", ["soe_consolidated", "listed_consolidated"])
async def test_test_project_recalc(pg_tx, request, standard):
    await require_snapshot(pg_tx, "归属行重算用例")
    totals = ATTRIBUTION[standard]
    assert all(parts is not None for _, _, parts in totals)
    template_type, report_scope = standard.split("_")
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_t18_attr_recalc_{uuid.uuid4().hex[:10]}",
                      client_name=f"{TEST_PROJECT_PREFIX}公式中枢归属行", template_type=template_type,
                      report_scope=report_scope, audit_year=YEAR)
    pg_tx.add(project)
    await pg_tx.flush()
    pid = project.id
    assert await ReportConfigService.resolve_applicable_standard(pg_tx, pid) == standard

    seed = {r["row_name"]: r for r in _seed_is_rows(standard)}
    db_rows = await _db_is_rows(pg_tx, standard)
    names = [name for _, name, parts in totals] + [pname for _, _, parts in totals for _, pname in parts]
    located = {name: (seed[name]["row_code"], db_rows[name].row_code) for name in names}
    assert all(a == b for a, b in located.values()), f"按行名定位：种子与快照库行次不一致 {located}"

    # ① 种子里的归属行定义经同步内核发布到该准则（回滚事务内；source="seed"，留发布记录）
    request_id = f"fh-t18-attr-{uuid.uuid4().hex[:10]}"
    changes = [{"slot_key": f"{IS}:{code}", "label": name, "expected_version": db_rows[name].formula_version,
                "definition": {f: seed[name].get(f) for f in DEFINITION_FIELDS}} for code, name, _ in totals]
    await publish_global(pg_tx, domain="report", scope=standard, changes=changes, user_id=None, source="seed",
                         request_id=request_id, note="任务 18 测试：需求 6.1 归属行")
    record = (await pg_tx.execute(sa.select(FormulaPublish).where(FormulaPublish.request_id == request_id))).scalar_one()
    assert (record.source, record.scope, record.target, record.status) == ("seed", standard, "global", "published")
    assert sorted((c["slot_key"], (c.get("new") or {}).get("formula")) for c in record.change_set) == sorted(
        (f"{IS}:{code}", seed[name]["formula"]) for code, name, _ in totals)
    after_publish = await _db_is_rows(pg_tx, standard)
    assert {name: after_publish[name].formula for _, name, _ in totals} == {name: seed[name]["formula"] for _, name, _ in totals}

    # ② 组成行在快照库无公式（F34）：生成一次，合计行带 warning「组成行 … 未定义公式」（需求 6.4）
    engine = ReportEngine(pg_tx)
    first = await engine.generate_all_reports(pid, YEAR, applicable_standard=standard, skip_recalc=True, publish_events=False)
    first_rows = {r["row_code"]: r for r in first[IS]}
    for code, _, parts in totals:
        row = first_rows[code]
        assert row["warnings"] == [f"组成行 {'、'.join(c for c, _ in parts)} 未定义公式"], (code, row["warnings"])
        assert (Decimal(row["current_period_amount"]), row["formula_error"]) == (Decimal(0), None), row

    # ③ 经项目层适配给组成行写字面量（save_overrides：只动本项目，不动准则行）
    items = [{"slot_key": f"{IS}:{db_rows[pname].row_code}", "label": pname, "definition": {"formula": LITERALS[pname]}}
             for _, _, parts in totals for _, pname in parts]
    await save_overrides(pg_tx, domain="report", project_id=pid, items=items, user_id=None)

    # ④ 生产报表引擎重算：合计行 = 测试内按行名独立求和
    second = await engine.generate_all_reports(pid, YEAR, applicable_standard=standard, skip_recalc=True, publish_events=False)
    second_rows = {r["row_code"]: r for r in second[IS]}
    stored = await _stored(pg_tx, pid)
    got, want = {}, {}
    for code, name, parts in totals:
        want[code] = (sum((Decimal(LITERALS[pname]) for _, pname in parts), Decimal(0)), False, None, CALC_VERSION,
                      seed[name]["formula"], [])
        row = stored[code]
        got[code] = (Decimal(row["current_period_amount"]), row["is_stale"], row["calc_error"], row["calc_version"],
                     row["formula_used"], second_rows[code]["warnings"])
        for _, pname in parts:
            want[db_rows[pname].row_code] = Decimal(LITERALS[pname])
            got[db_rows[pname].row_code] = Decimal(stored[db_rows[pname].row_code]["current_period_amount"])
    request.node.user_properties.append(("recalc", str(sorted(got.items()))))
    assert got == want
