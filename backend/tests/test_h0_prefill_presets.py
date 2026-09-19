"""test_h0_prefill_presets.py — H0 函证公式预设纠偏守卫.

spec: h0-confirmation-source-fidelity-and-linkage · Requirements 11 / Property 27, 28

裁决者：源模板 `backend/wp_templates/H/H0 固定资产循环函证.xlsx`（9 sheet 全 visible）
+ 取数真源 `app/services/four_table/h0_book_amounts.py`。

钉死四件事：
1. `sheet` 指向源模板真实存在的 tab（不得复活 `审定表H0-1`）；
2. 取数条目不得写死单一科目码（九品种口径 → 一律 PLACEHOLDER + 语义定位说明）；
3. 只触碰 H0 块（其余 257 块逐字节不变）；
4. 幂等脚本 `--check` 归零，且 round-trip 自检有效。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import openpyxl
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAPPING = _REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"
_H0_XLSX = _REPO_ROOT / "backend" / "wp_templates" / "H" / "H0 固定资产循环函证.xlsx"
_FIX_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "fix" / "fix_h0_prefill_presets.py"


@pytest.fixture(scope="module")
def raw() -> str:
    return _MAPPING.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def data(raw: str) -> dict:
    return json.loads(raw)


@pytest.fixture(scope="module")
def h0_block(data: dict) -> dict:
    blocks = [m for m in data["mappings"] if str(m.get("wp_code", "")) == "H0"]
    assert len(blocks) == 1, f"H0 块应恰好 1 个，实为 {len(blocks)}"
    return blocks[0]


@pytest.fixture(scope="module")
def sheet_names() -> set[str]:
    return set(openpyxl.load_workbook(_H0_XLSX).sheetnames)


@pytest.fixture(scope="module")
def fix_module():
    spec = importlib.util.spec_from_file_location("fix_h0_prefill_presets", _FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── Property 27：sheet 名指向源模板真实 tab ─────────────────────────────────


def test_h0_sheet_points_to_real_tab(h0_block: dict, sheet_names: set[str]):
    """H0 预设的 sheet 必须是源模板真实存在的 tab."""
    sheet = str(h0_block.get("sheet") or "")
    assert sheet, "H0 块缺 sheet 字段"
    assert sheet in sheet_names, f"H0 预设 sheet「{sheet}」不在源模板中：{sorted(sheet_names)}"
    assert sheet == "函证结果汇总表H0-1"


def test_obsolete_sheet_name_not_revived(raw: str, sheet_names: set[str]):
    """反向自检：`审定表H0-1` 在源模板中确实不存在，且预设里不得复活它."""
    assert "审定表H0-1" not in sheet_names, "源模板竟有该 tab → 本守卫前提失效"
    # 该字面量只允许出现在纠偏脚本的 OBSOLETE_SHEET 常量里，不允许回到数据文件
    assert "审定表H0-1" not in raw


def test_function_confirmation_has_no_adjudication_sheet(sheet_names: set[str]):
    """函证枢纽没有审定表（9 张 sheet 全实证），故任何「审定表H0-*」都是贴错标签."""
    assert not [n for n in sheet_names if n.startswith("审定表")]
    assert len(sheet_names) == 9


# ─── Property 28：取数不得写死单一科目码 ─────────────────────────────────────


def test_h0_cells_are_placeholder_not_single_account(h0_block: dict):
    """九品种口径 → 两条取数一律 PLACEHOLDER，禁 TB('1601') 单科目硬编码."""
    cells = h0_block.get("cells") or []
    assert len(cells) == 2, f"H0 应有 2 条 cell，实为 {len(cells)}"
    assert [c["cell_ref"] for c in cells] == ["期初余额", "未审数"]
    for c in cells:
        assert c["formula_type"] == "PLACEHOLDER", c["cell_ref"]
        assert str(c["formula"]).startswith("=PLACEHOLDER("), c["cell_ref"]
        # 公式里不得残留任何 4 位科目码调用
        assert not re.search(r"TB\(\s*'\d{4}", str(c["formula"])), c["cell_ref"]


def test_h0_description_names_the_real_data_source(h0_block: dict):
    """description 必须写明真源模块名，否则下个会话会把它改回 TB()."""
    desc = " ".join(str(c.get("description") or "") for c in h0_block["cells"])
    assert "h0_book_amounts" in desc
    assert "semantic_account_resolver" in desc
    # 必须说明「本项目无该科目时不显示 0」这条宁缺勿造语义
    assert "本项目无此科目" in desc


def test_h0_reference_codes_cover_nine_categories(h0_block: dict):
    """account_codes 降级为九品种参考码，且与 h0_book_amounts 的品种数一致."""
    from app.services.four_table.h0_book_amounts import H0_MATRIX_CATEGORY_SPECS

    codes = h0_block.get("account_codes") or []
    assert len(codes) == len(H0_MATRIX_CATEGORY_SPECS) == 9
    assert codes[0] == "1601"  # primary_code 仍是固定资产（无 TB 类 cell 消费它）
    assert len(set(codes)) == 9, "参考码不得重复"


def test_no_tb_formula_consumes_primary_code(h0_block: dict):
    """既然 account_codes 只作参考，H0 块里就不能有 TB/TB_SUM/ADJ/LEDGER 类 cell.

    `wp_template_init_service` 用 `account_codes[0]` 当 primary_code 喂 TB 类公式 →
    留着 TB 类 cell 就会把固定资产原值当成九品种账面金额。
    """
    consuming = {"TB", "TB_SUM", "ADJ", "LEDGER", "LEDGER_DETAIL", "AUX", "TB_AUX"}
    for c in h0_block["cells"]:
        assert c["formula_type"] not in consuming, c["cell_ref"]


# ─── 只触碰 H0 块 + 幂等 ─────────────────────────────────────────────────────


def test_only_h0_block_touched(data: dict):
    """块总数与 H0 之外的块结构不变（258 块，H0 恰 1 个）."""
    assert len(data["mappings"]) == 258
    assert sum(1 for m in data["mappings"] if str(m.get("wp_code")) == "H0") == 1


def test_fix_script_reports_zero_debt(fix_module):
    """幂等：脚本对当前文件应报 0 项欠账."""
    changes, blk = fix_module._plan(json.loads(_MAPPING.read_text(encoding="utf-8")))
    assert blk is not None
    assert changes == [], f"仍有欠账: {changes}"


def test_fix_script_roundtrip_selfcheck_is_effective(fix_module, raw: str):
    """round-trip 自检有效：原文可复现；人为改缩进后必判否（防写盘整体重排）."""
    assert fix_module._roundtrip_ok(raw) is True
    reindented = json.dumps(json.loads(raw), ensure_ascii=False, indent=4)
    assert fix_module._roundtrip_ok(reindented) is False


def test_fix_script_plan_detects_regression(fix_module):
    """反向自检：把 sheet 改回 `审定表H0-1` / cells 改回 TB，_plan 必须报欠账."""
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    blk = next(m for m in data["mappings"] if str(m.get("wp_code")) == "H0")

    blk["sheet"] = "审定表H0-1"
    changes, _ = fix_module._plan(data)
    assert any("sheet" in c for c in changes)

    blk["sheet"] = fix_module.TARGET_SHEET
    blk["cells"] = [
        {
            "cell_ref": "期初余额",
            "formula": "=TB('1601','期初余额')",
            "formula_type": "TB",
            "description": "旧口径",
        }
    ]
    changes, _ = fix_module._plan(data)
    assert any("cells" in c for c in changes)


def test_fix_script_rejects_wrong_target_sheet(fix_module, monkeypatch):
    """反向自检：目标 sheet 若不在源模板中，脚本必须报 FATAL 而非静默写入."""
    monkeypatch.setattr(fix_module, "TARGET_SHEET", "不存在的表H0-9")
    err = fix_module._verify_target_sheet_exists()
    assert err and "不在源模板中" in err


# ─── PLACEHOLDER 作为一等 formula_type 的三处白名单（2026-08-04 实测补齐） ────


def test_placeholder_is_registered_in_pending_allowlist():
    """`PLACEHOLDER` 必须在 ACNR pending 白名单里（否则 grammar 闭合守卫打红）.

    它是**有意永久 pending** 的伪函数（语义 = 取数真源在别处，grammar_v1 里
    不会有等价函数头），不是「待迁移」。存量用法：N1 / E1×2 / N3 / H0-1×2。
    """
    from app.services.formula_management.preset_acnr_migration import (
        PENDING_FUNCTION_ALLOWLIST,
    )

    assert "PLACEHOLDER" in PENDING_FUNCTION_ALLOWLIST


def test_placeholder_is_registered_in_h_prefill_formula_types():
    """`PLACEHOLDER` 必须在 H 循环 prefill 的 formula_type 白名单里."""
    import importlib.util

    p = _REPO_ROOT / "backend" / "tests" / "test_h_prefill_extension.py"
    spec = importlib.util.spec_from_file_location("_h_prefill_ext", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "PLACEHOLDER" in mod.VALID_FORMULA_TYPES
    # 顺带钉死 H 类真实科目码（原清单把使用权资产写成 1621/1622、租赁负债写成 2802/2803）
    for code in ("1525", "1526", "1527", "1641", "1642", "1643", "2601", "2602"):
        assert code in mod.VALID_H_ACCOUNT_CODES, code


#: 允许使用 `PLACEHOLDER` 的 wp_code 及其理由（2026-08-04 全库实测）。
#: 🔴 这是**登记表**不是逃逸阀 —— 新增 wp_code 必须在此写明「为什么这个格子
#: 写不成公式」，否则「取数写不出来就塞 PLACEHOLDER」会变成静默兜底。
_PLACEHOLDER_REGISTRY: dict[str, str] = {
    "N1": "税会差异汇总需跨全部循环聚合（应收坏账+存货跌价+固定资产折旧差异…），逻辑复杂",
    "E1": "数字货币 / 存放财务公司款项按准则解释15号「可增设」，无一级标准科目",
    "N3": "递延负债本期变动 = 期末 − 期初，余额类科目无「借方发生额」列口径",
    "H0": "H0-1 账面金额是九品种逐品种口径，真源 four_table/h0_book_amounts 语义定位",
    "G0": "并发 spec g0-confirmation-source-alignment 的同款九/多品种口径",
    "N5": "利润总额等派生行由 ROW()/REPORT() 组合，prefill 引擎无该解析器",
}


def test_placeholder_usage_is_bounded():
    """全库 `PLACEHOLDER` 用法必须都在登记表里（新增须写理由）."""
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    wps: set[str] = set()
    for m in data["mappings"]:
        for c in m.get("cells") or []:
            if c.get("formula_type") == "PLACEHOLDER":
                wps.add(str(m.get("wp_code")))
    assert wps, "全库竟无 PLACEHOLDER → 前提失效（本组断言会空转）"
    unregistered = wps - set(_PLACEHOLDER_REGISTRY)
    assert not unregistered, f"以下 wp_code 用了 PLACEHOLDER 但未登记理由: {sorted(unregistered)}"
    for wp, reason in _PLACEHOLDER_REGISTRY.items():
        assert len(reason) >= 15, f"{wp} 的理由过短，说不清为什么写不成公式: {reason!r}"
    assert "H0" in wps
