"""K2 公式管理预设契约 + 披露 sheet 名三处一致（Property 10, 11）。

🔴 K2 预设**整块原是销售费用**（复制粘贴事故）：`wp_name='销售费用审定表'`、
`account_codes=['6601']`、公式全 `TB('6601',…)` / `ADJ('6601',…)`。
`report_config` 实证四准则 `BS-014 其他流动资产 = TB('1901','期末余额')`
（`listed_standalone` 另加 `TB('1131')`，但 1131 已属 `BS-009`/K1，本表不并入）。

同时锁死 sheet 名三处一致：源 xlsx tab 名 ↔ 后端 `K2_SHEETS` ↔ 前端
`k2NoteSectionMap.K2_DISCLOSURE_SHEET_NAME`（`?sheet=` 深链按名精确匹配，
一处漂移就落空）。

spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 4.2
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
DATA = BACKEND / "data" / "prefill_formula_mapping.json"
K2_MAP_TS = (
    REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "composables"
    / "k2NoteSectionMap.ts"
)


def _blocks() -> list[dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return raw["mappings"] if isinstance(raw, dict) and "mappings" in raw else raw


@pytest.fixture(scope="module")
def k2_adjudication() -> dict:
    hit = [b for b in _blocks() if b.get("wp_code") == "K2" and b.get("sheet") == "审定表K2-1"]
    assert hit, "prefill_formula_mapping 缺 K2 审定表K2-1 块"
    assert len(hit) == 1, "K2 审定表块应恰好 1 个"
    return hit[0]


def _formulas(block: dict) -> list[str]:
    return [str(c.get("formula") or "") for c in block.get("cells") or []]


# ── Property 10：科目口径 ───────────────────────────────────────────────────


def test_block_is_other_current_assets_not_selling_expense(k2_adjudication: dict) -> None:
    assert k2_adjudication["wp_name"] == "其他流动资产审定表"
    assert k2_adjudication.get("account_codes") == ["1901"]
    # 只查 cell_ref / formula —— `description` 允许写「历史误用销售费用 6601」这类溯源说明
    for cell in k2_adjudication.get("cells") or []:
        assert "销售费用" not in str(cell.get("cell_ref") or "")
        assert "销售费用" not in str(cell.get("formula") or "")


@pytest.mark.parametrize(
    "snippet",
    [
        "TB('1901','期初余额')",
        "TB('1901','期末余额')",
        "ADJ('1901','aje_net')",
        "ADJ('1901','rje_net')",
        "PREV('K2','审定表K2-1','审定数')",
    ],
)
def test_adjudication_covers_required_formulas(k2_adjudication: dict, snippet: str) -> None:
    assert any(snippet in f for f in _formulas(k2_adjudication)), f"缺公式 {snippet}"


def test_no_selling_expense_or_bad_debt_accounts(k2_adjudication: dict) -> None:
    """反向钉子：不得残留 6601（销售费用）与 1231（应收款项坏账准备）。"""
    joined = "\n".join(_formulas(k2_adjudication))
    assert "6601" not in joined, f"残留销售费用科目：{joined}"
    assert "1231" not in joined, f"残留坏账准备科目：{joined}"
    # 反向自检：确实存在 1901 公式（否则上面两条断言空转）
    assert "1901" in joined


def test_dividend_code_not_in_k2_gross(k2_adjudication: dict) -> None:
    """1131 应收股利已属 BS-009（K1），不得并入 K2 原值口径。"""
    joined = json.dumps(k2_adjudication, ensure_ascii=False)
    assert "TB('1131'" not in joined
    assert "1131" not in (k2_adjudication.get("account_codes") or [])


# ── Property 10：跨底稿取数方向 ─────────────────────────────────────────────


def test_adjudication_has_cross_workpaper_pulls(k2_adjudication: dict) -> None:
    joined = "\n".join(_formulas(k2_adjudication))
    assert "WP('K2','明细表K2-2'" in joined, "缺 K2-1 ← K2-2 明细期末合计"
    assert "WP('K2','合同取得成本明细表K2-4'" in joined, "缺 K2-1 ← K2-4 合同取得成本"


def test_detail_sheets_have_no_wp_reference() -> None:
    """K2-2 / K2-4 明细块禁引 WP() —— 否则 K2-1 ← K2-2 ← K2-1 成环。

    当前这两个 sheet **无预设块**（合法态：空即无环）；一旦有人加块，本断言接着守。
    """
    detail_blocks = [
        b for b in _blocks()
        if b.get("wp_code") == "K2" and b.get("sheet") in {"明细表K2-2", "合同取得成本明细表K2-4"}
    ]
    for b in detail_blocks:
        assert "WP(" not in json.dumps(b, ensure_ascii=False), f"{b.get('sheet')} 不得引 WP()"


# ── Property 10：收敛进公式管理 ─────────────────────────────────────────────


def _k2_preset_entries() -> list:
    """`convert_prefill_presets()` 里归属 `workpaper:K2` 的条目。

    `PresetEntry` 字段是 `page_key` / `expression`（不是 `scope` / `formula`）。
    """
    from app.services.formula_management import preset_library as pl

    return [e for e in pl.convert_prefill_presets() if e.page_key == "workpaper:K2"]


def test_presets_converge_into_workpaper_scope() -> None:
    entries = _k2_preset_entries()
    assert entries, "K2 预设未收敛进 workpaper:K2"
    for e in entries:
        assert e.formula_type == "auto_calc", f"{e.target_cell} 应为 auto_calc"


def test_k2_presets_expression_scope_is_correct() -> None:
    entries = _k2_preset_entries()
    cells = {e.target_cell for e in entries}
    for want in ("期初余额", "未审数", "AJE调整", "RJE调整", "明细表期末合计"):
        assert want in cells, f"公式管理缺条目 {want}"

    joined = "\n".join(str(e.expression or "") for e in entries)
    assert "TB('1901','期初余额')" in joined
    assert "TB('1901','期末余额')" in joined
    assert "WP('K2','明细表K2-2'" in joined
    # 反向钉子：错误科目不得进公式管理
    assert "6601" not in joined
    assert "1231" not in joined


# ── Property 11：sheet 名三处一致 ───────────────────────────────────────────


def _source_xlsx() -> Path | None:
    root = BACKEND / "wp_templates"
    if not root.exists():
        return None
    hits = [
        p for p in root.rglob("*.xlsx")
        if p.name.startswith("K2 ") and not p.name.startswith("~$")
    ]
    return hits[0] if hits else None


def _frontend_sheet_names() -> dict[str, str]:
    """从前端 `k2NoteSectionMap.ts` 抽 `K2_DISCLOSURE_SHEET_NAME`（文本扫描，防双真源漂移）。"""
    src = K2_MAP_TS.read_text(encoding="utf-8")
    m = re.search(
        r"K2_DISCLOSURE_SHEET_NAME[^=]*=\s*\{(.*?)\}", src, re.S
    )
    assert m, "前端未声明 K2_DISCLOSURE_SHEET_NAME"
    body = m.group(1)
    out: dict[str, str] = {}
    for key, val in re.findall(r"(listed|soe)\s*:\s*'([^']+)'", body):
        out[key] = val
    assert out, f"未解析出 sheet 名（body={body!r}）"
    return out


def test_backend_and_frontend_sheet_names_match() -> None:
    from app.routers.wp_render_strategies._k2_other_current_assets import (
        K2_DISCLOSURE_SHEET_LISTED,
        K2_DISCLOSURE_SHEET_SOE,
    )

    fe = _frontend_sheet_names()
    assert fe["listed"] == K2_DISCLOSURE_SHEET_LISTED
    assert fe["soe"] == K2_DISCLOSURE_SHEET_SOE
    # 🔴 国企侧是「国企」而非「国有企业」，且括号全角
    assert "国有企业" not in K2_DISCLOSURE_SHEET_SOE
    for name in (K2_DISCLOSURE_SHEET_LISTED, K2_DISCLOSURE_SHEET_SOE):
        assert "(" not in name and ")" not in name, f"半角括号：{name}"


def test_sheet_names_match_source_xlsx_tabs() -> None:
    """openpyxl 直读源 xlsx tab 名交叉比对（唯一裁决者）。"""
    xlsx = _source_xlsx()
    if xlsx is None:
        pytest.skip("backend/wp_templates 无 K2 源模板（运行时权威目录未就位）")
    openpyxl = pytest.importorskip("openpyxl")

    from app.routers.wp_render_strategies._k2_other_current_assets import (
        K2_DISCLOSURE_SHEET_LISTED,
        K2_DISCLOSURE_SHEET_SOE,
    )

    wb = openpyxl.load_workbook(xlsx, read_only=True)
    try:
        tabs = list(wb.sheetnames)
    finally:
        wb.close()

    assert K2_DISCLOSURE_SHEET_LISTED in tabs, f"上市 tab 名不在源模板：{tabs}"
    assert K2_DISCLOSURE_SHEET_SOE in tabs, f"国企 tab 名不在源模板：{tabs}"
