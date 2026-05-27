"""单测 — disclosure_engine binding 分支 + _build_with_binding（Sprint 1 Task 1.3）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.3
Reqs:   R1.1 验收标准 1（binding 路径覆盖）

涵盖：
- _build_with_binding 算法（≥ 15 用例）
- _build_table_data legacy 兼容（≥ 5 用例）
- binding loader（≥ 5 用例）
- 资源完整性（≥ 5 用例）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import note_template_bindings_loader as loader
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_source_resolvers import (
    SOURCE_RESOLVERS,
    VALID_SOURCES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _three_col_template() -> dict:
    return {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {"label": "原材料", "row_type": "data"},
            {"label": "库存商品", "row_type": "data"},
            {"label": "合计", "row_type": "total", "is_total": True},
        ],
    }


def _three_col_binding(section_number: str = "五、1 存货") -> dict:
    return {
        "table_index": 0,
        "table_name": "存货",
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期末余额", "semantic": "closing_balance"},
            {"text": "期初余额", "semantic": "opening_balance"},
        ],
        "rows": {
            "原材料": {
                "row_type": "data",
                "binding": {
                    "closing_balance": {
                        "source": "trial_balance",
                        "field": "audited_amount",
                        "account_codes": ["1401"],
                        "mode": "auto",
                        "agg": "sum",
                    },
                    "opening_balance": {
                        "source": "trial_balance",
                        "field": "opening_balance",
                        "account_codes": ["1401"],
                        "mode": "auto",
                        "agg": "sum",
                    },
                },
            },
            "库存商品": {
                "row_type": "data",
                "binding": {
                    "closing_balance": {
                        "source": "trial_balance",
                        "field": "audited_amount",
                        "account_codes": ["1405"],
                        "mode": "auto",
                        "agg": "sum",
                    },
                    "opening_balance": {
                        "source": "trial_balance",
                        "field": "opening_balance",
                        "account_codes": ["1405"],
                        "mode": "auto",
                        "agg": "sum",
                    },
                },
            },
            "合计": {
                "row_type": "total",
                "formula": "sum(detail)",
                "mode": "auto",
            },
        },
    }


# ===========================================================================
# _build_with_binding 算法（≥ 15 用例）
# ===========================================================================


@pytest.mark.asyncio
async def test_build_with_binding_basic_three_col():
    """标准 3 列（项目/期末/期初）走 trial_balance — 全命中."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1000.0, "opening": 800.0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 500.0, "opening": 400.0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    assert out["headers"] == ["项目", "期末余额", "期初余额"]
    rows = out["rows"]
    assert len(rows) == 3
    assert rows[0]["label"] == "原材料"
    assert rows[0]["values"] == [1000.0, 800.0]
    assert rows[1]["label"] == "库存商品"
    assert rows[1]["values"] == [500.0, 400.0]


@pytest.mark.asyncio
async def test_build_with_binding_total_row_backfilled():
    """合计行回填 = 上方非合计行 sum."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1000.0, "opening": 800.0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 500.0, "opening": 400.0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    total = out["rows"][2]
    assert total["is_total"] is True
    assert total["row_type"] == "total"
    assert total["values"] == [1500.0, 1200.0]


@pytest.mark.asyncio
async def test_build_with_binding_row_type_field_written():
    """row_type 字段从 template_rows 取，不再启发式判定."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    assert out["rows"][0]["row_type"] == "data"
    assert out["rows"][1]["row_type"] == "data"
    assert out["rows"][2]["row_type"] == "total"


@pytest.mark.asyncio
async def test_build_with_binding_cell_meta_binding_id_format():
    """_cell_meta.binding_id 格式 = section_number.label.semantic."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    meta_0 = out["rows"][0]["_cell_meta"]["0"]
    assert meta_0["binding_id"] == "五、1 存货.原材料.closing_balance"
    assert meta_0["semantic"] == "closing_balance"
    assert meta_0["manual_value"] is None


@pytest.mark.asyncio
async def test_build_with_binding_cell_modes_recorded():
    """_cell_modes 记录每列的 mode（auto / manual / locked）."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    modes_0 = out["rows"][0]["_cell_modes"]
    assert modes_0["0"] == "auto"
    assert modes_0["1"] == "auto"


@pytest.mark.asyncio
async def test_build_with_binding_missing_row_returns_none_values():
    """模板有行但 binding 缺这行 → 整行 values 为 None，不报错."""
    eng = _make_engine()
    template = _three_col_template()
    template["rows"].insert(0, {"label": "委托加工材料", "row_type": "data"})
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        template, _three_col_binding(),
    )
    extra = out["rows"][0]
    assert extra["label"] == "委托加工材料"
    # binding 缺该 row → 每列 manual placeholder + values None
    assert extra["values"] == [None, None]
    assert extra["_cell_modes"]["0"] == "manual"
    assert extra["_cell_modes"]["1"] == "manual"
    # 但语义仍记录（来自 header_normalize）
    assert extra["_cell_meta"]["0"]["semantic"] == "closing_balance"


@pytest.mark.asyncio
async def test_build_with_binding_manual_mode_uses_manual_value():
    """mode=manual 直接读 binding.manual_value."""
    eng = _make_engine()
    binding = _three_col_binding()
    binding["rows"]["原材料"]["binding"]["closing_balance"] = {
        "source": "manual",
        "field": "value",
        "manual_value": 999.0,
        "mode": "manual",
        "account_codes": [],
    }
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), binding,
    )
    assert out["rows"][0]["values"][0] == 999.0
    assert out["rows"][0]["_cell_modes"]["0"] == "manual"


@pytest.mark.asyncio
async def test_build_with_binding_locked_mode_skips_resolver():
    """mode=locked 不调 resolver，values 留 None（由 caller merge 接管）."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1000.0, "opening": 800.0, "unadjusted": 0}
    binding = _three_col_binding()
    binding["rows"]["原材料"]["binding"]["closing_balance"]["mode"] = "locked"
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), binding,
    )
    # locked → 新算值 None；merge 阶段才保留 old
    assert out["rows"][0]["values"][0] is None
    assert out["rows"][0]["_cell_modes"]["0"] == "locked"


@pytest.mark.asyncio
async def test_build_with_binding_header_normalize_short_falls_back_to_manual():
    """header_normalize 长度不足 → 兜底 manual placeholder."""
    eng = _make_engine()
    binding = _three_col_binding()
    binding["header_normalize"] = [{"text": "项目", "semantic": "manual_text"}]
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), binding,
    )
    # 期末 / 期初 column 都没 semantic → manual + None
    row = out["rows"][0]
    assert row["values"] == [None, None]
    assert row["_cell_modes"]["0"] == "manual"
    assert row["_cell_meta"]["0"]["semantic"] is None


@pytest.mark.asyncio
async def test_build_with_binding_empty_template_rows():
    """template_rows 空 → 返 {headers, rows: []}."""
    eng = _make_engine()
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        {"headers": ["项目", "期末余额"], "rows": []},
        _three_col_binding(),
    )
    assert out == {"headers": ["项目", "期末余额"], "rows": []}


@pytest.mark.asyncio
async def test_build_with_binding_total_row_no_data_keeps_none():
    """合计行无明细数据 → values 仍 None（不强制为 0）."""
    eng = _make_engine()
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    # 没有 _tb_cache → 明细全 None → 合计行也保持 None
    total = out["rows"][2]
    assert total["values"] == [None, None]


@pytest.mark.asyncio
async def test_build_with_binding_partial_data_total_partial():
    """部分明细有值 → 合计行用现有部分求和."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 100.0, "opening": 50.0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    total = out["rows"][2]
    assert total["values"] == [100.0, 50.0]


@pytest.mark.asyncio
async def test_build_with_binding_same_semantic_multi_col_variant():
    """同 semantic 多列变体（closing_balance_col2）通过前缀回退命中."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    binding = _three_col_binding()
    # 把 row 的 closing_balance 改名为 closing_balance_col1，模拟 generator 行为
    binding["rows"]["原材料"]["binding"]["closing_balance_col1"] = (
        binding["rows"]["原材料"]["binding"].pop("closing_balance")
    )
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), binding,
    )
    # 仍能取到值（通过前缀匹配）
    assert out["rows"][0]["values"][0] is not None


@pytest.mark.asyncio
async def test_build_with_binding_subtotal_row_type():
    """row_type=subtotal 也走合计回填路径."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 100.0, "opening": 0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 50.0, "opening": 0, "unadjusted": 0}
    template = _three_col_template()
    template["rows"][2] = {"label": "小计", "row_type": "subtotal"}
    binding = _three_col_binding()
    binding["rows"]["小计"] = binding["rows"].pop("合计")
    binding["rows"]["小计"]["row_type"] = "subtotal"
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        template, binding,
    )
    sub = out["rows"][2]
    assert sub["row_type"] == "subtotal"
    assert sub["is_total"] is True
    assert sub["values"][0] == 150.0


@pytest.mark.asyncio
async def test_build_with_binding_default_row_type_is_data():
    """row_type 缺省 → data."""
    eng = _make_engine()
    template = _three_col_template()
    template["rows"][0].pop("row_type", None)
    eng._tb_cache["1401"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        template, _three_col_binding(),
    )
    assert out["rows"][0]["row_type"] == "data"


@pytest.mark.asyncio
async def test_build_with_binding_row_label_col_excluded():
    """col 0 是行 label 不参与值取数（num_value_cols = headers - 1）."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}
    out = await eng._build_with_binding(
        uuid4(), 2025, "五、1 存货",
        _three_col_template(), _three_col_binding(),
    )
    # values 长度 = headers - 1（去掉 row_label col）
    assert len(out["rows"][0]["values"]) == 2
    assert len(out["rows"][0]["_cell_modes"]) == 2


# ===========================================================================
# _build_table_data legacy 兼容（≥ 5 用例）
# ===========================================================================


@pytest.mark.asyncio
async def test_legacy_path_when_no_section_number(monkeypatch):
    """不传 section_number → 走 legacy 路径不变（不调 binding loader）."""
    eng = _make_engine()
    eng._tb_cache["原材料"] = {"audited": 100.0, "opening": 50.0, "unadjusted": 0}
    called: list[Any] = []

    def _mock_get(*_args, **_kw):
        called.append(True)
        return None

    monkeypatch.setattr(loader, "get_binding_for_section", _mock_get)
    out = await eng._build_table_data(
        uuid4(), 2025,
        {"headers": ["项目", "期末余额", "期初余额"],
         "rows": [{"label": "原材料"}]},
    )
    # 没传 section_number → loader 不应被调用
    assert called == []
    assert out is not None


@pytest.mark.asyncio
async def test_legacy_path_when_loader_returns_none(monkeypatch):
    """传 section_number 但 binding loader 返 None → 走 legacy."""
    eng = _make_engine()
    eng._tb_cache["原材料"] = {"audited": 100.0, "opening": 50.0, "unadjusted": 0}

    monkeypatch.setattr(loader, "get_binding_for_section", lambda _sn: None)

    out = await eng._build_table_data(
        uuid4(), 2025,
        {"headers": ["项目", "期末余额", "期初余额"],
         "rows": [{"label": "原材料"}]},
        section_number="未在 binding 的章节",
    )
    assert out is not None
    # legacy 行结构（无 _cell_modes / _cell_meta）
    assert "values" in out["rows"][0]
    # legacy 不写 _cell_modes
    assert "_cell_modes" not in out["rows"][0]


@pytest.mark.asyncio
async def test_binding_path_when_loader_returns_data(monkeypatch):
    """binding loader 命中 → 走新路径（输出含 _cell_modes / _cell_meta）."""
    eng = _make_engine()
    eng._tb_cache["1401"] = {"audited": 1000.0, "opening": 800.0, "unadjusted": 0}
    eng._tb_cache["1405"] = {"audited": 500.0, "opening": 400.0, "unadjusted": 0}
    fake_binding = {"tables": [_three_col_binding()]}
    monkeypatch.setattr(loader, "get_binding_for_section", lambda _sn: fake_binding)

    out = await eng._build_table_data(
        uuid4(), 2025, _three_col_template(),
        section_number="五、1 存货",
    )
    assert out is not None
    # 新路径行有 _cell_modes / _cell_meta / row_type
    assert "_cell_modes" in out["rows"][0]
    assert "_cell_meta" in out["rows"][0]
    assert out["rows"][0]["row_type"] == "data"
    assert out["rows"][0]["values"] == [1000.0, 800.0]


@pytest.mark.asyncio
async def test_binding_path_falls_back_on_exception(monkeypatch):
    """_build_with_binding 抛错 → 兜底走 legacy."""
    eng = _make_engine()
    eng._tb_cache["原材料"] = {"audited": 100.0, "opening": 50.0, "unadjusted": 0}
    monkeypatch.setattr(
        loader,
        "get_binding_for_section",
        lambda _sn: {"tables": [{"bad": "data"}]},  # 缺 header_normalize
    )

    async def _raise(*_args, **_kw):
        raise RuntimeError("bind path explode")

    monkeypatch.setattr(eng, "_build_with_binding", _raise)
    out = await eng._build_table_data(
        uuid4(), 2025,
        {"headers": ["项目", "期末余额", "期初余额"],
         "rows": [{"label": "原材料"}]},
        section_number="五、1 存货",
    )
    # legacy 兜底产出
    assert out is not None
    assert out["rows"][0]["label"] == "原材料"


@pytest.mark.asyncio
async def test_legacy_path_empty_table_template_returns_none():
    """legacy 路径 — 空 table_template 返回 None（与原行为一致）."""
    eng = _make_engine()
    out = await eng._build_table_data(uuid4(), 2025, {})
    assert out is None


@pytest.mark.asyncio
async def test_legacy_path_signature_kwarg_only():
    """section_number 必须 keyword-only — 防止误传 positional 破坏 legacy 调用."""
    import inspect
    sig = inspect.signature(DisclosureEngine._build_table_data)
    sn_param = sig.parameters["section_number"]
    assert sn_param.kind == inspect.Parameter.KEYWORD_ONLY


# ===========================================================================
# binding loader（≥ 5 用例）
# ===========================================================================


def test_loader_initial_state_not_loaded():
    """模块首次状态：reload 后 is_loaded=False."""
    loader.reload()
    assert loader.is_loaded() is False


def test_loader_get_then_loaded():
    """get_binding_for_section 触发 lazy-load → is_loaded=True."""
    loader.reload()
    loader.get_binding_for_section("any")
    assert loader.is_loaded() is True


def test_loader_returns_existing_section():
    """加载真实 json 后能取到真实 section."""
    loader.reload()
    # binding 文件存在时应至少有 1 条
    cache = loader._ensure_loaded()
    if not cache:
        pytest.skip("binding json empty (file missing or no sections)")
    first_key = next(iter(cache.keys()))
    sec = loader.get_binding_for_section(first_key)
    assert isinstance(sec, dict)
    assert "tables" in sec


def test_loader_returns_none_for_unknown_section():
    """未知 section_number → None（不抛错）."""
    loader.reload()
    loader._ensure_loaded()
    assert loader.get_binding_for_section("不存在的章节 xxxxxxxxx") is None


def test_loader_returns_none_for_invalid_input():
    """非 str / 空 str → None."""
    loader.reload()
    assert loader.get_binding_for_section(None) is None
    assert loader.get_binding_for_section("") is None
    assert loader.get_binding_for_section(123) is None  # type: ignore[arg-type]


def test_loader_get_binding_for_table_index_in_range():
    """table_index 在范围内取到表."""
    loader.reload()
    cache = loader._ensure_loaded()
    if not cache:
        pytest.skip("binding json empty")
    first_key = next(iter(cache.keys()))
    tbl = loader.get_binding_for_table(first_key, 0)
    assert isinstance(tbl, dict)


def test_loader_get_binding_for_table_index_out_of_range():
    """table_index 越界 → None."""
    loader.reload()
    cache = loader._ensure_loaded()
    if not cache:
        pytest.skip("binding json empty")
    first_key = next(iter(cache.keys()))
    assert loader.get_binding_for_table(first_key, 999) is None
    assert loader.get_binding_for_table(first_key, -1) is None


def test_loader_reload_resets_cache():
    """reload() 后 is_loaded=False，重新 get 触发 lazy load."""
    loader.reload()
    loader.get_binding_for_section("any")
    assert loader.is_loaded() is True
    loader.reload()
    assert loader.is_loaded() is False


def test_loader_handles_missing_file(monkeypatch, tmp_path):
    """文件不存在 → 返空 dict（不抛错）."""
    fake = tmp_path / "no_such_file.json"
    monkeypatch.setattr(loader, "BINDINGS_PATH", fake)
    loader.reload()
    assert loader._ensure_loaded() == {}
    assert loader.get_binding_for_section("any") is None


def test_loader_handles_invalid_json(monkeypatch, tmp_path):
    """JSON 解析失败 → 返空 dict."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(loader, "BINDINGS_PATH", bad)
    loader.reload()
    assert loader._ensure_loaded() == {}


def test_loader_handles_bindings_not_dict(monkeypatch, tmp_path):
    """bindings 字段不是 dict → 返空 dict（防御）."""
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"bindings": ["not", "a", "dict"]}), encoding="utf-8"
    )
    monkeypatch.setattr(loader, "BINDINGS_PATH", bad)
    loader.reload()
    assert loader._ensure_loaded() == {}


# ===========================================================================
# 资源完整性（≥ 5 用例）
# ===========================================================================


def test_seven_sources_have_resolvers():
    """7 个 source 都有 resolver 函数."""
    assert len(VALID_SOURCES) == 7
    for src in VALID_SOURCES:
        assert src in SOURCE_RESOLVERS
        assert callable(SOURCE_RESOLVERS[src])


def test_resolvers_are_async():
    """每个 resolver 是 async."""
    import inspect
    for src, fn in SOURCE_RESOLVERS.items():
        assert inspect.iscoroutinefunction(fn), f"{src} not async"


def test_valid_sources_aligned_with_resolvers():
    """VALID_SOURCES 与 SOURCE_RESOLVERS keys 对齐."""
    assert set(VALID_SOURCES) == set(SOURCE_RESOLVERS.keys())


def test_binding_json_valid_sources_match():
    """note_template_bindings.json 的 valid_sources 与代码 VALID_SOURCES 对齐."""
    bindings_path = (
        Path(__file__).resolve().parents[3]
        / "backend" / "data" / "note_template_bindings.json"
    )
    if not bindings_path.exists():
        pytest.skip("binding json missing")
    payload = json.loads(bindings_path.read_text(encoding="utf-8"))
    assert set(payload.get("valid_sources", [])) == set(VALID_SOURCES)


def test_engine_has_build_with_binding_method():
    """DisclosureEngine 必须含 _build_with_binding（CI 卡点）."""
    assert hasattr(DisclosureEngine, "_build_with_binding")
    import inspect
    assert inspect.iscoroutinefunction(DisclosureEngine._build_with_binding)


def test_engine_has_backfill_totals_helper():
    """DisclosureEngine 必须含 _backfill_totals 辅助函数."""
    assert hasattr(DisclosureEngine, "_backfill_totals")


def test_disclosure_engine_imports_clean():
    """模块 import 不报错（防 circular import 或类型错误）."""
    from app.services import disclosure_engine  # noqa: F401
    from app.services import note_source_resolvers  # noqa: F401
    from app.services import note_template_bindings_loader  # noqa: F401


# ===========================================================================
# Sprint 3 Task 3.3：模板 union 算法接入 _load_templates（5 用例）
# ===========================================================================


@pytest.mark.asyncio
async def test_load_templates_merges_custom_override(monkeypatch, tmp_path):
    """custom 覆盖 baseline 同 section_number → _load_templates 输出取 custom 版本."""
    from app.services import note_custom_template_service as svc_mod
    from app.services.note_custom_template_service import NoteCustomTemplateService

    monkeypatch.setattr(svc_mod, "STORAGE_ROOT", tmp_path / "storage" / "projects")

    pid = uuid4()
    custom_svc = NoteCustomTemplateService(db=None, storage_root=tmp_path / "storage" / "projects")
    await custom_svc.save_custom_template(
        pid,
        [{
            "section_number": "八、1",
            "section_title": "货币资金（用户自定义）",
            "sort_order": 100,
            "tables": [{"table_name": "covered"}],
        }],
        uuid4(),
    )

    eng = _make_engine()
    sections = await eng._load_templates(pid, "soe")

    overridden = [s for s in sections if s["note_section"] == "八、1"]
    assert len(overridden) == 1, "应有且仅有一条同 section_number 的章节（custom 覆盖 baseline）"
    assert overridden[0]["section_title"] == "货币资金（用户自定义）"
    assert overridden[0]["tables"] == [{"table_name": "covered"}]


@pytest.mark.asyncio
async def test_load_templates_inserts_custom_only_section(monkeypatch, tmp_path):
    """custom 独有的章节注入并标 _custom: True."""
    from app.services import note_custom_template_service as svc_mod
    from app.services.note_custom_template_service import NoteCustomTemplateService

    monkeypatch.setattr(svc_mod, "STORAGE_ROOT", tmp_path / "storage" / "projects")

    pid = uuid4()
    custom_svc = NoteCustomTemplateService(db=None, storage_root=tmp_path / "storage" / "projects")
    await custom_svc.save_custom_template(
        pid,
        [{
            "section_number": "九、Z99 用户自定义新增",
            "section_title": "用户自定义章节",
            "sort_order": 99999,
            "tables": [],
        }],
        uuid4(),
    )

    eng = _make_engine()
    sections = await eng._load_templates(pid, "soe")

    extras = [s for s in sections if s["note_section"] == "九、Z99 用户自定义新增"]
    assert len(extras) == 1
    assert extras[0]["_custom"] is True
    assert extras[0]["section_title"] == "用户自定义章节"


@pytest.mark.asyncio
async def test_load_templates_sorted_by_sort_order(monkeypatch, tmp_path):
    """custom 按 sort_order 插入到合并集中正确位置."""
    from app.services import note_custom_template_service as svc_mod
    from app.services.note_custom_template_service import NoteCustomTemplateService

    monkeypatch.setattr(svc_mod, "STORAGE_ROOT", tmp_path / "storage" / "projects")

    pid = uuid4()
    custom_svc = NoteCustomTemplateService(db=None, storage_root=tmp_path / "storage" / "projects")
    await custom_svc.save_custom_template(
        pid,
        [
            {"section_number": "九、Z01 first", "section_title": "first", "sort_order": -100},
            {"section_number": "九、Z99 last", "section_title": "last", "sort_order": 999999},
        ],
        uuid4(),
    )

    eng = _make_engine()
    sections = await eng._load_templates(pid, "soe")

    sort_orders = [s["sort_order"] for s in sections]
    # 输出按 sort_order 升序
    assert sort_orders == sorted(sort_orders)

    # 自定义章节分别落在头/尾
    assert sections[0]["note_section"] == "九、Z01 first"
    assert sections[-1]["note_section"] == "九、Z99 last"


@pytest.mark.asyncio
async def test_load_templates_no_custom_returns_baseline_only(monkeypatch, tmp_path):
    """缺 custom 文件 → baseline 全量 + 不抛异常 + _custom 全 False."""
    from app.services import note_custom_template_service as svc_mod

    monkeypatch.setattr(svc_mod, "STORAGE_ROOT", tmp_path / "storage" / "projects")

    pid = uuid4()  # 该 pid 下无 custom 文件
    eng = _make_engine()
    sections = await eng._load_templates(pid, "soe")

    assert len(sections) > 0  # baseline 至少几十条
    assert all(s.get("_custom") is False for s in sections)


@pytest.mark.asyncio
async def test_load_templates_custom_branch_unchanged(monkeypatch, tmp_path):
    """template_type='custom' 走 NoteTemplateService 旧机制，不调 union."""
    from app.services import note_custom_template_service as svc_mod
    monkeypatch.setattr(svc_mod, "STORAGE_ROOT", tmp_path / "storage" / "projects")

    eng = _make_engine()

    async def fake_get_custom(_pid):
        return [
            {"section_number": "X1", "section_title": "X1", "table_template": {"headers": ["h"]}},
        ]
    eng._get_custom_template_sections = fake_get_custom  # type: ignore[assignment]

    sections = await eng._load_templates(uuid4(), "custom")
    # custom 分支输出格式与 soe/listed 不同：'note_section' 直接来自 section_number 字段
    assert sections[0]["note_section"] == "X1"
    # 旧分支不会带 _custom 字段
    assert "_custom" not in sections[0]
