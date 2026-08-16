"""test_k0_formula_presets.py — K0 公式预设守卫 + 七枢纽 sheet 名存在性.

spec: k0-confirmation-source-alignment · Task 6
  Property 11（sheet 名必须存在于源 xlsx 可见 sheet 集合）
  Property 12（修订脚本幂等 + round-trip 安全 + 校验器只扫语义字段）

判据：**openpyxl 直读源 xlsx**（不连库、可进 CI）。不接受「拿脚本常量比自己写的 fixture」
这种自证 —— 故 sheet 名的裁决者是源模板，不是本文件的期望值表。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import openpyxl
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = _REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"
FIX_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "fix" / "fix_k0_prefill_presets.py"

#: 七个函证枢纽 → 源模板 xlsx 相对路径（文件名逐字实测，勿凭「应该叫什么」猜）
CONFIRM_CYCLE_XLSX: dict[str, str] = {
    "D0": "backend/wp_templates/D/D0 收入循环函证.xlsx",
    "E0": "backend/wp_templates/E/E0 货币资金 - 函证（Leap应对措施-函证）.xlsx",
    "F0": "backend/wp_templates/F/F0 存货循环函证.xlsx",
    "G0": "backend/wp_templates/G/G0 投资循环函证.xlsx",
    "H0": "backend/wp_templates/H/H0 固定资产循环函证.xlsx",
    "K0": "backend/wp_templates/K/K0 管理循环函证.xlsx",
    "L0": "backend/wp_templates/L/L0 债务循环函证.xlsx",
}

#: 🔴 已知预存在缺陷白名单（**只许变短**）：`(cycle, sheet) → 理由`。
#:
#: 判据 = 该块的 `sheet` 值不在源 xlsx **可见** sheet 名集合中。函证枢纽压根没有
#: 「审定表」这种 tab，故凡写 `审定表X0-1` 的都是贴错标签；D0 另有两条同族
#: （`分析程序D0-3` 真名是「跟函函证过程控制D0-3」，`函证汇总表D0-2` 真名是
#: 「核实被函证单位信息D0-2」—— 是把别的循环的命名习惯抄进来了）。
#:
#: G0 / H0 / K0 已修（G0·H0 由各自 spec，K0 由 `fix_k0_prefill_presets.py`）。
KNOWN_BAD_SHEET_NAMES: dict[tuple[str, str], str] = {
    # ("D0", "审定表D0-1") / ("D0", "分析程序D0-3") / ("D0", "函证汇总表D0-2")
    # 已于 d-cycle-four-table-extraction-and-disclosure-completion Task 18 按源模板正名
    # （→「函证结果汇总表D0-1」/「跟函函证过程控制D0-3」/「核实被函证单位信息D0-2」），
    # 按「白名单只许变短」规则移出。
    ("E0", "审定表E0-1"): "归属 e0-confirmation-completion 遗留；memory 已记，源 xlsx 无该 tab",
    ("F0", "审定表F0-1"): "归属 f0-confirmation-linkage-and-structural-enhancement；源 xlsx 无该 tab",
    # ("L0", "审定表L0-1") 已于 l0-confirmation-source-alignment Task 4 修好
    # （→「函证结果汇总表L0-1」），按「白名单只许变短」规则移出。
}

K0_TARGET_SHEET = "函证结果汇总表K0-1"
K0_MATRIX_CELL_REFS = [
    "K0-1-matrix-其他应收款-book_amount",
    "K0-1-matrix-其他应付款-book_amount",
]


# ─── fixtures / helpers ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def mapping_raw() -> str:
    return MAPPING_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def mapping(mapping_raw: str) -> dict:
    return json.loads(mapping_raw)


@pytest.fixture(scope="module")
def fix_module():
    spec = importlib.util.spec_from_file_location("fix_k0_prefill_presets", FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def visible_sheets(rel_path: str) -> set[str]:
    p = _REPO_ROOT / rel_path
    if not p.exists():
        pytest.fail(f"源模板不存在，无法裁决: {p}")
    wb = openpyxl.load_workbook(p, read_only=False)
    return {n for n in wb.sheetnames if wb[n].sheet_state == "visible"}


def blocks_of(mapping: dict, wp_code: str) -> list[dict]:
    return [m for m in mapping["mappings"] if str(m.get("wp_code", "")) == wp_code]


# ─── Property 11: 七枢纽 sheet 名必须存在于源 xlsx ────────────────────────────


@pytest.mark.parametrize("cycle", sorted(CONFIRM_CYCLE_XLSX))
def test_preset_sheet_names_exist_in_source_template(mapping: dict, cycle: str):
    """各函证枢纽预设块的 `sheet` 必须是源 xlsx 的**可见** sheet 名（R5.5）。

    已知预存在缺陷登记在 `KNOWN_BAD_SHEET_NAMES`（只许变短）。
    """
    visible = visible_sheets(CONFIRM_CYCLE_XLSX[cycle])
    for blk in blocks_of(mapping, cycle):
        sheet = str(blk.get("sheet") or "")
        if sheet in visible:
            continue
        assert (cycle, sheet) in KNOWN_BAD_SHEET_NAMES, (
            f"{cycle} 预设块 sheet「{sheet}」不在源模板可见 sheet 中，且未登记白名单。\n"
            f"源模板可见 sheet: {sorted(visible)}"
        )


def test_known_bad_sheet_names_still_bad(mapping: dict):
    """反向自检：白名单里的每条**当前确实仍是坏的** —— 修好即打红提醒移出。"""
    for (cycle, bad_sheet), reason in KNOWN_BAD_SHEET_NAMES.items():
        assert len(reason) >= 15, f"{cycle}/{bad_sheet} 白名单缺实证理由"
        visible = visible_sheets(CONFIRM_CYCLE_XLSX[cycle])
        assert bad_sheet not in visible, (
            f"{cycle} 的「{bad_sheet}」竟已存在于源模板 → 白名单前提失效，请核对"
        )
        sheets = {str(blk.get("sheet") or "") for blk in blocks_of(mapping, cycle)}
        assert bad_sheet in sheets, (
            f"{cycle} 已不再使用「{bad_sheet}」→ 请把它从 KNOWN_BAD_SHEET_NAMES 移出"
            f"（白名单只许变短）"
        )


def test_fixed_cycles_are_not_in_whitelist():
    """G0 / H0 / K0 已修，不得出现在白名单里（若被加回即打红）。"""
    fixed = {c for c, _ in KNOWN_BAD_SHEET_NAMES} & {"G0", "H0", "K0"}
    assert not fixed, f"已修循环竟在白名单中: {sorted(fixed)}"


# ─── K0 块目标状态 ───────────────────────────────────────────────────────────


def test_k0_block_exists_once(mapping: dict):
    assert len(blocks_of(mapping, "K0")) == 1


def test_k0_sheet_is_real_tab(mapping: dict):
    """K0 块 sheet = `函证结果汇总表K0-1`，且 `审定表K0-1` 在源 xlsx 不存在（R5.1）。"""
    blk = blocks_of(mapping, "K0")[0]
    assert blk["sheet"] == K0_TARGET_SHEET
    visible = visible_sheets(CONFIRM_CYCLE_XLSX["K0"])
    assert K0_TARGET_SHEET in visible
    assert "审定表K0-1" not in visible


def test_k0_cells_are_matrix_book_amounts(mapping: dict):
    """两条 cell_ref 指向矩阵账面金额（非审定表口径的期初余额/未审数）（R5.2）。"""
    blk = blocks_of(mapping, "K0")[0]
    refs = [c["cell_ref"] for c in blk["cells"]]
    assert refs == K0_MATRIX_CELL_REFS
    assert "期初余额" not in refs and "未审数" not in refs, "审定表口径的 cell_ref 未清除"


def test_k0_formulas_are_placeholder(mapping: dict):
    """公式一律 PLACEHOLDER —— 不得回退成 TB()（R5.2 / R4.5）。

    理由：BS-009 是净额口径（单个 TB() 表达不出），且 cell_ref 是手工覆盖键，
    写 TB() 会让「按码取到的 0」压住语义定位的 undefined。
    """
    blk = blocks_of(mapping, "K0")[0]
    for c in blk["cells"]:
        assert c["formula_type"] == "PLACEHOLDER", f"{c['cell_ref']} 不是 PLACEHOLDER"
        assert c["formula"].startswith("=PLACEHOLDER("), c["formula"]
        # 🔴 只扫**语义字段** —— description 会如实写出被纠正的反例 =TB('1221',...)
        assert "TB(" not in c["formula"]


def test_k0_account_codes_cover_both_categories(mapping: dict):
    """account_codes 覆盖两品种（含 BS-009 净额口径的加减项）（R5.2）。"""
    blk = blocks_of(mapping, "K0")[0]
    codes = blk["account_codes"]
    assert codes == ["1221", "1231-03", "1131", "2241", "2231"]
    assert "2241" in codes, "漏掉其他应付款侧"


def test_k0_descriptions_mention_row_code_matching(mapping: dict):
    """description 必须写明按 row_code 精确匹配与 BS-050（供审计追溯）。"""
    blk = blocks_of(mapping, "K0")[0]
    joined = "\n".join(c["description"] for c in blk["cells"])
    assert "BS-009" in joined and "BS-050" in joined
    assert "row_code" in joined
    assert "BS-075" in joined, "同名 NULL 行的坑必须留证"


# ─── Property 12: 脚本幂等 / round-trip / 校验器只扫语义字段 ──────────────────


def test_fix_script_reports_zero_debt(fix_module, mapping: dict):
    """`--check` 等价物：已修订状态下 `_plan` 返回 0 项欠账（幂等）。"""
    changes, blk = fix_module._plan(json.loads(json.dumps(mapping)))
    assert blk is not None
    assert changes == [], f"仍有欠账: {changes}"


def test_fix_script_roundtrip_guard_is_effective(fix_module, mapping_raw: str):
    """round-trip 自检对当前文件成立；被破坏格式时必须判否（反向自检）。"""
    assert fix_module._roundtrip_ok(mapping_raw) is True
    broken = mapping_raw.replace("\n  ", "\n    ", 1)  # 缩进被改
    assert fix_module._roundtrip_ok(broken) is False


def test_validator_does_not_scan_description(fix_module, mapping: dict):
    """🔴 校验器只扫语义字段：把被纠正的反例写进 description 不应产生欠账（R5.4）。"""
    data = json.loads(json.dumps(mapping))
    blk = [m for m in data["mappings"] if m.get("wp_code") == "K0"][0]
    blk["cells"][0]["description"] += "（反例：原写 =TB('1221','期初余额') 于 审定表K0-1）"
    changes, _ = fix_module._plan(data)
    assert changes == [], f"description 被当成语义字段扫了: {changes}"


def test_plan_detects_regression(fix_module, mapping: dict):
    """反向自检：把 sheet / cells / account_codes 改回旧值必须被 `_plan` 抓到。"""
    for mutate, label in (
        (lambda b: b.__setitem__("sheet", "审定表K0-1"), "sheet"),
        (lambda b: b.__setitem__("account_codes", ["1221"]), "account_codes"),
        (
            lambda b: b.__setitem__(
                "cells",
                [{"cell_ref": "期初余额", "formula": "=TB('1221','期初余额')",
                  "formula_type": "TB", "description": "x"}],
            ),
            "cells",
        ),
    ):
        data = json.loads(json.dumps(mapping))
        blk = [m for m in data["mappings"] if m.get("wp_code") == "K0"][0]
        mutate(blk)
        changes, _ = fix_module._plan(data)
        assert changes, f"回退 {label} 未被 `_plan` 抓到"


def test_script_target_constants_match_landed_state(fix_module, mapping: dict):
    """脚本常量与落盘状态一致（防「常量改了但没 apply」或反之）。"""
    blk = blocks_of(mapping, "K0")[0]
    assert fix_module.TARGET_SHEET == blk["sheet"]
    assert fix_module.K0_REFERENCE_ACCOUNT_CODES == blk["account_codes"]
    assert fix_module.TARGET_CELLS == blk["cells"]


def test_script_has_three_modes():
    """脚本提供 `--dry-run` / `--check` / `--apply` 三态（R5.3）。"""
    src = FIX_SCRIPT.read_text(encoding="utf-8")
    for flag in ("--dry-run", "--check", "--apply"):
        assert f'"{flag}"' in src, f"缺 {flag}"
    assert re.search(r"def _roundtrip_ok", src), "缺 round-trip 自检"
