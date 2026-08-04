"""test_h0_book_amount_injection.py — H0 账面金额加法式注入守卫.

spec: h0-confirmation-source-fidelity-and-linkage
  Requirements 3.5 / 3.6 / 3.7 / 12.5；Property 10

核心断言：
1. **wp_code 前缀门控** —— 其余六枢纽（D0/E0/F0/G0/K0/L0）载荷注入前后深比较逐字节不变
2. **不劫持 RENDERER_DISPATCH** —— `confirmation-summary` 不得出现在 dispatch 表里
   （它是七枢纽共享 componentType，注册即全部改道）
3. **两态可区分** —— 「注入整体失败」= 键不存在；「本项目无此科目」= 键存在值为 None
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from app.routers import wp_render_config_helpers as helpers
from app.routers.wp_render_config_helpers import _inject_h0_book_amounts

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DISPATCH_SRC = (
    _REPO_ROOT / "backend" / "app" / "routers" / "wp_render_strategies" / "__init__.py"
).read_text(encoding="utf-8")
_CONFIG_SRC = (
    _REPO_ROOT / "backend" / "app" / "routers" / "wp_render_config.py"
).read_text(encoding="utf-8")

OTHER_CYCLES = ["D0", "D0-1", "E0", "E0-1", "F0-1", "G0-1", "K0-1", "L0-1"]


def _summary_payload() -> dict:
    """典型 confirmation-summary 载荷（含既有注入字段）。"""
    return {
        "_format": "confirmation-v1",
        "rows": [
            {"_row_id": "r1", "confirm_index": "H0-001", "account_type": "固定资产", "amount": 1000.0},
        ],
        "conclusion": "未见异常",
        "audit_note": "",
        "sampling": {"method": "统计抽样"},
        "project_context": {"population_amount": 5000.0, "applicable_standards": ["soe_standalone"]},
    }


class _FakeResult:
    def __init__(self, amounts, source_codes, conflicts=None):
        self.amounts = amounts
        self.source_codes = source_codes
        self.conflicts = conflicts or []


@pytest.fixture
def patched_resolver(monkeypatch):
    """替换取数为固定返回值（本文件只测注入契约，不测取数正确性）。"""
    calls: list[dict] = []

    async def fake_resolve(ctx, categories=None):
        calls.append({"project_id": ctx.project_id, "year": ctx.year, "categories": categories})
        return _FakeResult(
            amounts={"固定资产": 650.0, "工程物资": None},
            source_codes={
                "固定资产": {"found": True, "gross": ["1601"], "resolved_from": "account_chart_client"},
                "工程物资": {"found": False, "gross": [], "resolved_from": "none",
                             "absent_reason": "本项目科目表无该科目"},
            },
        )

    import app.services.four_table.h0_book_amounts as m
    monkeypatch.setattr(m, "resolve_h0_book_amounts", fake_resolve)
    return calls


# ─── Property 10: wp_code 前缀门控 ──────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("wp_code", OTHER_CYCLES)
async def test_other_cycles_payload_byte_identical(wp_code: str, patched_resolver):
    """其余六枢纽：注入前后载荷深比较逐字节不变（零回归支点）."""
    payload = _summary_payload()
    before = copy.deepcopy(payload)
    await _inject_h0_book_amounts(None, "pid", 2025, wp_code, payload)
    assert payload == before, f"{wp_code} 载荷被改动"
    assert patched_resolver == [], f"{wp_code} 不应触发取数"


@pytest.mark.asyncio
@pytest.mark.parametrize("wp_code", [None, "", "  ", "H1", "H1-1", "H10", "H"])
async def test_non_h0_wp_codes_are_gated(wp_code, patched_resolver):
    """空 wp_code 与 H 循环其它底稿（H1/H10）都不触发注入."""
    payload = _summary_payload()
    before = copy.deepcopy(payload)
    await _inject_h0_book_amounts(None, "pid", 2025, wp_code, payload)
    assert payload == before
    assert patched_resolver == []


@pytest.mark.asyncio
@pytest.mark.parametrize("wp_code", ["H0", "H0-1", "h0-1", " H0-1 "])
async def test_h0_triggers_injection(wp_code: str, patched_resolver):
    payload = _summary_payload()
    await _inject_h0_book_amounts(None, "pid", 2025, wp_code, payload)
    ctx = payload["project_context"]
    assert ctx["h0_book_amounts"] == {"固定资产": 650.0, "工程物资": None}
    assert ctx["h0_book_source_codes"]["固定资产"]["found"] is True
    assert len(patched_resolver) == 1


@pytest.mark.asyncio
async def test_injection_is_additive(patched_resolver):
    """只加两个键，rows/_format/其它 project_context 字段一字不动."""
    payload = _summary_payload()
    before = copy.deepcopy(payload)
    await _inject_h0_book_amounts(None, "pid", 2025, "H0-1", payload)

    assert payload["rows"] == before["rows"]
    assert payload["_format"] == before["_format"]
    assert payload["conclusion"] == before["conclusion"]
    assert payload["sampling"] == before["sampling"]
    # 既有注入字段保留
    assert payload["project_context"]["population_amount"] == 5000.0
    assert payload["project_context"]["applicable_standards"] == ["soe_standalone"]
    # 新增键恰好两个（无 conflicts 时不写第三个键）
    new_keys = set(payload["project_context"]) - set(before["project_context"])
    assert new_keys == {"h0_book_amounts", "h0_book_source_codes"}


@pytest.mark.asyncio
async def test_conflicts_key_only_when_present(monkeypatch):
    """有 report_config 冲突时才写 h0_book_conflicts（无冲突不产生空键）."""
    async def fake_resolve(ctx, categories=None):
        return _FakeResult({"固定资产": 1.0}, {"固定资产": {}}, conflicts=["BS-028 与科目表不一致"])

    import app.services.four_table.h0_book_amounts as m
    monkeypatch.setattr(m, "resolve_h0_book_amounts", fake_resolve)

    payload = _summary_payload()
    await _inject_h0_book_amounts(None, "pid", 2025, "H0-1", payload)
    assert payload["project_context"]["h0_book_conflicts"] == ["BS-028 与科目表不一致"]


@pytest.mark.asyncio
async def test_non_dict_payload_is_noop(patched_resolver):
    for bad in (None, [], "x", 0):
        await _inject_h0_book_amounts(None, "pid", 2025, "H0-1", bad)  # type: ignore[arg-type]
    assert patched_resolver == []


@pytest.mark.asyncio
async def test_non_dict_project_context_is_noop(patched_resolver):
    """project_context 被历史数据写成非 dict 时不崩、不注入."""
    payload = {"_format": "confirmation-v1", "rows": [], "project_context": "legacy-string"}
    before = copy.deepcopy(payload)
    await _inject_h0_book_amounts(None, "pid", 2025, "H0-1", payload)
    assert payload == before


# ─── 两态可区分：注入失败（无键） vs 无此科目（键在值为 None） ────────────────


@pytest.mark.asyncio
async def test_resolver_exception_leaves_no_keys(monkeypatch):
    """取数抛异常 → 由调用点 except 兜住，载荷里**不出现**这两个键.

    前端据此区分「未取数（可手填）」与「本项目无此科目」（后者键存在值为 None）。
    """
    async def boom(ctx, categories=None):
        raise RuntimeError("db down")

    import app.services.four_table.h0_book_amounts as m
    monkeypatch.setattr(m, "resolve_h0_book_amounts", boom)

    payload = _summary_payload()
    with pytest.raises(RuntimeError):
        await _inject_h0_book_amounts(None, "pid", 2025, "H0-1", payload)
    assert "h0_book_amounts" not in payload["project_context"]


def test_call_site_wraps_injection_in_try():
    """调用点必须 try/except 包裹（否则取数异常会把整个 render-config 打 500）."""
    idx = _CONFIG_SRC.find("_inject_h0_book_amounts(")
    assert idx > 0, "wp_render_config.py 未调用 _inject_h0_book_amounts"
    window = _CONFIG_SRC[max(0, idx - 400): idx]
    assert "try:" in window, "注入调用未包在 try 内"


# ─── Property: 不劫持 RENDERER_DISPATCH ─────────────────────────────────────


def test_confirmation_summary_not_in_renderer_dispatch():
    """`confirmation-summary` 是七枢纽共享 componentType，注册进 dispatch 即全部改道."""
    m = re.search(r"RENDERER_DISPATCH[^=]*=\s*\{", _DISPATCH_SRC)
    assert m, "未找到 RENDERER_DISPATCH"
    # 从 '{' 起做括号配对
    start = _DISPATCH_SRC.index("{", m.start())
    depth = 0
    end = -1
    for i in range(start, len(_DISPATCH_SRC)):
        ch = _DISPATCH_SRC[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end > start
    block = _DISPATCH_SRC[start:end]
    assert '"confirmation-summary"' not in block, (
        "confirmation-summary 不得注册 render 策略 —— 会劫持 D0/E0/F0/G0/H0/K0/L0 全部载荷；"
        "H0 专属数据走 wp_render_config_helpers 的加法式注入通道"
    )
    # 反向自检：H0-5 的专属 componentType 确实在 dispatch 里（证明正则抓对了块）
    assert '"confirmation-alternative-h05"' in block


def test_injector_exists_and_is_async():
    import inspect
    assert inspect.iscoroutinefunction(_inject_h0_book_amounts)
    src = inspect.getsource(_inject_h0_book_amounts)
    # 门控必须在任何取数之前
    gate = src.find("startswith")
    call = src.find("resolve_h0_book_amounts(")
    assert 0 < gate < call, "wp_code 门控必须早于取数调用"


def test_helpers_module_exposes_injector():
    assert hasattr(helpers, "_inject_h0_book_amounts")
