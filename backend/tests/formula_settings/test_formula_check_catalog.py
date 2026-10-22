"""全平台校对规则目录（spec formula-governance-coverage-closure R3，design §5）。

登记守卫（规则文件全登记或带理由排除、无失效条目）+ 双向变异；静态来源计数与规则文件现算一致；
全局设置来源只读全局层；单个来源失败不拖垮目录；端点只要登录、三种查询形态。
"""
from __future__ import annotations

import dataclasses
import json
import uuid

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.formula_setting_models import FormulaSetting
from app.services import formula_check_catalog as cat
from app.services.formula_check_catalog import (
    DATA_DIR, EXCLUDED, SOURCES, CheckSource, build_check_catalog, cycle_rule_files, registration_problems,
)

from ._env import BS, add_global_row, add_project, make_db


def _data(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


# ── 登记守卫 ──────────────────────────────────────────────────────────────────


def test_every_rule_like_data_file_is_registered_or_excluded():
    assert registration_problems() == []
    assert len({s.key for s in SOURCES}) == len(SOURCES), "来源键不得重复"
    assert all(why.strip() for why in EXCLUDED.values())


def test_registration_guard_catches_unregistered_stale_and_reasonless_entries(tmp_path):
    (tmp_path / "a_rules.json").write_text("[]", encoding="utf-8")
    (tmp_path / "x_check_list.json").write_text("[]", encoding="utf-8")  # 新增却没登记
    (tmp_path / "keep_rules.json").write_text("[]", encoding="utf-8")
    (tmp_path / "plain.json").write_text("[]", encoding="utf-8")  # 文件名不带 rule / check：不归守卫管
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "h1.disposal_check.json").write_text("{}", encoding="utf-8")
    source = CheckSource("t", "测试", "报表", "", "", lambda: [], files=("a_rules.json", "missing_rules.json"))
    problems = registration_problems(tmp_path, sources=(source,), excluded={
        "keep_rules.json": "不是校对规则", "contracts/": "目录整体排除", "gone_rules.json": "已删的文件",
        "no_reason_check.json": " ",
    })
    assert problems == [
        "未登记：x_check_list.json（是校对规则就登记进 SOURCES，不是就写进 EXCLUDED 并写明理由）",
        "SOURCES 登记的文件不存在：missing_rules.json",
        "EXCLUDED 条目已失效：gone_rules.json",
        "EXCLUDED 缺理由：no_reason_check.json",
        "EXCLUDED 条目已失效：no_reason_check.json",
    ]


# ── 静态来源：加载成功、计数与规则文件现算一致 ────────────────────────────────────


def test_static_sources_load_and_counts_match_files():
    from app.services.formula_management.logic_check import _CROSS_CHECK_SEEDS
    from app.services.note_check_rules import load_all_check_rules

    presets = _data("note_check_preset_formulas.json")
    expected = {
        "report_builtin": len(_CROSS_CHECK_SEEDS),
        "cross_check_preset": len(_data("cross_check_preset_rules.json")["rules"]),
        "consol_note_checks": sum(len(v) for std in ("soe", "listed") for v in load_all_check_rules(std).values()),
        "note_preset_checks": sum(1 for std in ("soe", "listed") for r in presets[std]
                                  if r.get("category") in ("logic_check", "reasonability")),
        "note_disclosure_balance": len(_data("note_disclosure_balance_rules.json")["rules"]),
        "wp_cross_account": len(_data("cross_account_rules.json")["rules"]),
        "cycle_validation": sum(len(_data(n)["rules"]) for n in cycle_rule_files()),
        "a17_consistency": len(_data("a17_consistency_rules.json")),
        "qc_rules": len(_data("qc_rule_definitions_seed.json")) + len(_data("audit_log_rules_seed.json")),
        "cross_wp_references": len(_data("cross_wp_references.json")["references"]),
    }
    static = {s.key: s for s in SOURCES if not s.from_db}
    assert set(static) == set(expected), "新增静态来源要在这里写明现算口径"
    assert len(cycle_rule_files()) == 12
    for key, s in static.items():
        rules = s.loader()
        assert len(rules) == expected[key] > 0, key
        assert all(r["id"] and (r["label"] or r["expression"]) for r in rules), key
        assert len({r["id"] for r in rules}) == len(rules) or key == "cycle_validation", f"{key} 规则编号重复"


async def test_catalog_summary_counts_and_keyword_search():
    out = await build_check_catalog(None)
    by_key = {s["key"]: s for s in out["sources"]}
    assert list(by_key) == [s.key for s in SOURCES]
    assert all("rules" not in s for s in out["sources"]), "不带参数只给来源清单"
    assert out["total"] == sum(s["rule_count"] for s in out["sources"])
    assert by_key["note_disclosure_balance"]["runs_in"].startswith("暂未接入执行"), "如实标注无调用方"
    assert (by_key["cross_check_global"]["editable"], by_key["consol_note_checks"]["editable"]) == (True, False)
    found = await build_check_catalog(None, keyword="货币资金")
    hits = {s["key"]: s["matched"] for s in found["sources"] if s.get("matched")}
    assert hits.get("note_preset_checks", 0) > 0 and hits.get("cross_wp_references", 0) > 0, hits


async def test_one_failing_source_does_not_break_the_catalog(monkeypatch):
    def boom():
        raise ValueError("文件坏了")

    broken = tuple(dataclasses.replace(s, loader=boom) if s.key == "a17_consistency" else s for s in SOURCES)
    monkeypatch.setattr(cat, "SOURCES", broken)
    cat._cache.pop("a17_consistency", None)
    out = await build_check_catalog(None)
    by_key = {s["key"]: s for s in out["sources"]}
    assert by_key["a17_consistency"]["error"] == "加载失败：文件坏了" and by_key["a17_consistency"]["rule_count"] == 0
    assert by_key["wp_cross_account"]["error"] is None and by_key["wp_cross_account"]["rule_count"] > 0


# ── 全局设置来源：只读全局层 ──────────────────────────────────────────────────


async def _seed_global_layers(db, pid):
    rule = {"label": "货币资金勾稽", "left_ref": "ROW('BS-001')", "operator": "=", "right_ref": "NOTE('五、1','合计')"}
    for layer, slot, definition, kw in (
        ("global", "report_bs#0001", rule, {"scope": "soe_standalone"}),
        ("global", "report_bs#0002", {"disabled": True}, {"scope": "*"}),  # 全局层停用
        ("global", "report_bs#0003", {**rule, "label": "已删除"}, {"scope": "*", "is_deleted": True}),
        ("project", "report_bs#0004", {**rule, "label": "本项目的"}, {"project_id": pid}),
    ):
        db.add(FormulaSetting(domain="cross_check", layer=layer, slot_key=slot, definition=definition, **kw))
    ok = await add_global_row(db, "BS-901", "ROW('BS-001')>=0", row_name="货币资金非负")
    ok.formula_category, ok.formula_description = "logic_check", "不得为负"
    await add_global_row(db, "BS-902", "ROW('BS-001')", row_number=2)  # 自动运算：不是校对
    (await add_global_row(db, "BS-903", " ", row_number=3)).formula_category = "reasonability"  # 空公式
    (await add_global_row(db, "BS-904", "1", row_number=4, standard=f"project:{pid}")).formula_category = "logic_check"
    await db.commit()


async def test_db_sources_read_only_live_global_layers():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "目录")
        await _seed_global_layers(db, pid)
        cc = (await build_check_catalog(db, source="cross_check_global"))["sources"][0]
        audit = (await build_check_catalog(db, source="report_audit"))["sources"][0]
    assert [(r["id"], r["scope"]) for r in cc["rules"]] == [("report_bs#0001", "国企单体")]
    assert cc["rules"][0]["expression"] == "ROW('BS-001') = NOTE('五、1','合计')"
    assert [(r["id"], r["label"], r["severity_label"]) for r in audit["rules"]] == [
        (f"{BS.value}:BS-901", "货币资金非负：不得为负", "勾稽")]


# ── 端点 ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    from app.routers.formula_catalog import router

    async with make_db() as factory:
        app = FastAPI()
        app.include_router(router)

        async def _db():
            async with factory() as s:
                yield s

        app.dependency_overrides[get_db] = _db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            yield app, c


async def test_endpoint_requires_login_and_serves_three_query_shapes(client):
    app, c = client
    url = "/api/formula-catalog/check-rules"
    assert (await c.get(url)).status_code in (401, 403), "未登录不给看"
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": uuid.uuid4(), "is_active": True})()
    summary = (await c.get(url)).json()
    assert len(summary["sources"]) == len(SOURCES) and all("rules" not in s for s in summary["sources"])
    presets = (await c.get(url, params={"source": "cross_check_preset"})).json()["sources"]
    [preset] = presets
    assert preset["rule_count"] == len(preset["rules"]) > 0
    assert set(preset["rules"][0]["fields"]) == {"label", "left_ref", "operator", "right_ref", "tolerance",
                                                  "description"}, "选用预置要带原始字段"
    found = (await c.get(url, params={"q": "XR-01"})).json()["sources"]
    assert [(s["key"], s["matched"]) for s in found if s.get("matched")] == [("wp_cross_account", 1)]
    assert (await c.get(url, params={"source": "nope"})).status_code == 404
