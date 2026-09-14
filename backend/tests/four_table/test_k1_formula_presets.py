"""K1 公式管理预设契约（R6 / Property 10）。

锁定三件事：
1. K1-1 审定表预设覆盖坏账 `1231-03`（期初/期末）、应收股利 `1131`、应收利息 `1132`；
2. K1-1 有 `WP()` 跨底稿取数（← K1-2 明细 / ← K1-3 坏账明细），而 **K1-2 明细表禁 WP()**
   （防 K1-1↔K1-2 循环，与 `test_h1_two_level_chain` 同款约束）；
3. 预设经 `convert_prefill_presets()` 归入 `workpaper:K1` 且 `formula_type == 'auto_calc'`。

🔴 为什么坏账必须写 `1231-03` 而不是 `1231`：`1231` 下挂按应收款种类拆分的备抵子科目
（DB 实证 `1231-01` 应收票据 / `1231-02` 应收账款 / `1231-03` 其他应收款 / 长期应收款），
`TB('1231')` 走的是 `standard_account_code LIKE '1231%'` 前缀聚合 → 会把应收账款的坏账
一并算进 K1（实测项目 `0ec33ac9`：28,464,225.16 vs 真值 900,217.36，虚增 31.6 倍）。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "data" / "prefill_formula_mapping.json"


def _blocks() -> list[dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return raw["mappings"] if isinstance(raw, dict) and "mappings" in raw else raw


@pytest.fixture(scope="module")
def k1_adjudication() -> dict:
    hit = [b for b in _blocks() if b.get("wp_code") == "K1" and b.get("sheet") == "审定表K1-1"]
    assert hit, "prefill_formula_mapping 缺 K1 审定表K1-1 块"
    return hit[0]


@pytest.fixture(scope="module")
def k1_detail() -> dict:
    hit = [b for b in _blocks() if b.get("wp_code") == "K1" and b.get("sheet") == "明细表K1-2"]
    assert hit, "prefill_formula_mapping 缺 K1 明细表K1-2 块"
    return hit[0]


def _formulas(block: dict) -> list[str]:
    return [str(c.get("formula") or "") for c in block.get("cells") or []]


# ── R6.1：四表取数科目齐备且口径正确 ────────────────────────────────────────


@pytest.mark.parametrize(
    "snippet",
    [
        "TB('1221','期初余额')",
        "TB('1221','期末余额')",
        "TB('1231-03','期初余额')",
        "TB('1231-03','期末余额')",
        "TB('1131','期末余额')",
        "TB('1132','期末余额')",
    ],
)
def test_adjudication_covers_required_accounts(k1_adjudication: dict, snippet: str) -> None:
    assert any(snippet in f for f in _formulas(k1_adjudication)), f"缺公式 {snippet}"


def test_bad_debt_never_uses_wide_1231_prefix(k1_adjudication: dict) -> None:
    """反向钉子：不得出现 `TB('1231',...)` 宽口径（会含应收账款坏账）。"""
    for f in _formulas(k1_adjudication):
        assert "TB('1231'" not in f, f"宽口径坏账公式：{f}"
    # 反向自检：确实存在细分码公式（否则本断言空转）
    assert any("1231-03" in f for f in _formulas(k1_adjudication))


def test_account_codes_declared(k1_adjudication: dict) -> None:
    codes = k1_adjudication.get("account_codes") or []
    assert set(codes) >= {"1221", "1231-03", "1131", "1132"}


# ── R6.2 / R6.3：跨底稿取数方向 ─────────────────────────────────────────────


def test_adjudication_has_cross_workpaper_pulls(k1_adjudication: dict) -> None:
    joined = "\n".join(_formulas(k1_adjudication))
    assert "WP('K1','明细表K1-2'" in joined, "缺 K1-1 ← K1-2 原值合计"
    assert "WP('K1','坏账准备明细表K1-3'" in joined, "缺 K1-1 ← K1-3 坏账期末审定"


def test_detail_sheet_has_no_wp_reference(k1_detail: dict) -> None:
    """K1-2 明细表禁引 WP() —— 否则 K1-1 ← K1-2 ← K1-1 成环。"""
    assert "WP(" not in json.dumps(k1_detail, ensure_ascii=False)


def test_detail_sheet_aux_presets_removed_by_property_22(k1_detail: dict) -> None:
    """K1-2 的**项目专属**辅助项预设已按 Property 22 移除，且不得重新引入。

    🔴 2026-08-14 改写（spec `k-cycle-extraction-formula-and-disclosure-closure`
    Task 11 / Property 22）。原断言是 ``assert any("AUX(" in f ...)``（「块本身非空」
    的反向自检），与 Property 22「预设不得含具体辅助项编码」直接冲突。

    原 6 条形如 ``AUX('1221','三方收款标识','SKT211','期末余额')``，第三参是**某一个
    项目**的实际辅助项编码（description 自己写着「实测代表性 aux_code #1/#2/#3」）。
    `prefill_engine._resolve_aux_formula` 对 ``aux_code`` 用 ``==`` 精确匹配、
    **不支持通配** ⇒ 换任何别的项目这 6 条全部静默返 0。

    **后继方案（已登记，不在本 spec 作业面）**：按辅助项分行的明细表行集依项目而异，
    本质上不适合静态公式预设 —— 应走 render 侧动态预填（读 `tb_aux_balance` 按本项目
    实际 ``aux_code`` 建行，形如 K2/K4/K6 的 ``adjudication_prefill``）。

    本测试**不空转**：正向断言「无写死编码」+ 反向断言「移除留痕在案」。
    """
    import re as _re

    formulas = _formulas(k1_detail)
    hardcoded = [
        f for f in formulas if _re.search(r"AUX\([^)]*'(?:SKT\d+|YG\d+|A\d{3})'", f)
    ]
    assert not hardcoded, (
        f"K1-2 又出现写死的项目专属辅助项编码（Property 22 禁止）：{hardcoded}"
    )
    # 移除动作必须留痕（防「块被别的改动顺手清空」而无人知晓）
    if not formulas:
        assert k1_detail.get("_aux_removal_note"), (
            "K1-2 预设为空但缺 `_aux_removal_note` 留痕 —— 无法区分"
            "「按 Property 22 有意移除」与「被别的改动误清空」"
        )


# ── R6.4：收敛进公式管理 ────────────────────────────────────────────────────


def _k1_preset_entries() -> list:
    """`convert_prefill_presets()` 里归属 `workpaper:K1` 的条目。

    `PresetEntry` 的字段是 `page_key` / `expression`（不是 `scope` / `formula`）。
    """
    from app.services.formula_management import preset_library as pl

    return [e for e in pl.convert_prefill_presets() if e.page_key == "workpaper:K1"]


def test_presets_converge_into_workpaper_scope() -> None:
    entries = _k1_preset_entries()
    assert entries, "K1 预设未收敛进 workpaper:K1"
    for e in entries:
        assert e.formula_type == "auto_calc", f"{e.target_cell} 应为 auto_calc"


def test_k1_presets_include_new_cells() -> None:
    entries = _k1_preset_entries()
    cells = {e.target_cell for e in entries}
    for want in (
        "坏账准备期初余额", "坏账准备期末未审数",
        "应收股利审定数", "应收利息审定数",
        "明细表原值合计", "坏账准备期末审定数",
    ):
        assert want in cells, f"公式管理缺条目 {want}"

    joined = "\n".join(str(e.expression or "") for e in entries)
    assert "TB('1231-03','期初余额')" in joined
    assert "TB('1231-03','期末余额')" in joined
    assert "WP('K1','坏账准备明细表K1-3'" in joined
    assert "WP('K1','明细表K1-2'" in joined
    # 反向钉子：宽口径坏账不得出现在公式管理里
    assert "TB('1231','" not in joined
