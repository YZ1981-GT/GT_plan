"""N3 / N4 / N5 公式预设纯净性守卫（Property 8 / 9 / 10）。

spec: `.kiro/specs/n345-four-table-extraction-alignment/` R8

拦下列已实证缺陷（全部 DB / 活体只读证据）：

1. **`1812` 不存在** —— 活体 `tb_balance` 全库 0 命中；递延所得税负债是 `2901`
   （`report_config` 四准则 `BS-067 = TB('2901','期末余额')`）。
2. **N3 审定表块是从 N5 复制来的** —— 曾 `wp_name='所得税费用审定表'` + `account_codes=['6801']`。
3. **损益类用了 `期末余额`** —— `IS-003 = TB('6403','本期发生额')` /
   `IS-023 = TB('6801','本期发生额')`，平台铁律亦为「损益取发生额」。
4. **`6001` 被当利润总额** —— `6001` 是营业收入；`IS-022 利润总额` 是 `ROW()` 派生行。
5. **按 `6403` 子科目编码取税种** —— 活体 `6403.01` 某客户是「印花税」，
   `6403.02` 既是「城市维护建设税」也是「车船税」→ 编码语义客户间冲突。
6. **`cell_ref` 在 wp_code 内撞键** —— `page_key = workpaper:{wp_code}` 忽略 sheet，
   同名必互相遮蔽（`seed_formula_presets --check` 的 `Skipped (duplicate ...)` 即被吞条数）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
MAPPING_PATH = BACKEND / "data" / "prefill_formula_mapping.json"

# 各循环允许引用的科目前缀（每条都有源模板 / report_config 依据）
ALLOWED: dict[str, tuple[str, ...]] = {
    # N3 递延所得税负债（BS-067）
    "N3": ("2901",),
    # N4 税金及附加（IS-003）
    "N4": ("6403", "2221"),  # 2221 仅出现在跨底稿 WP('N2',...) 的描述性引用中，不作 TB 取数
    # N5 所得税费用（IS-023）+ 递延核对表引 1811/2901
    "N5": ("6801", "1811", "2901"),
}

FORBIDDEN_CODES = {
    "1812": "活体 tb_balance 全库 0 命中的不存在科目码（递延所得税负债是 2901）",
    "6001": "营业收入，不是利润总额（IS-022 是 ROW() 派生行）",
}

# 损益类科目 → 必须用本期发生额
INCOME_CODES = ("6403", "6801")

_TB_RE = re.compile(r"TB\w*\('([^']+)'\s*,\s*'([^']*)'\)")
_TB_CODE_RE = re.compile(r"(?:TB\w*|ADJ)\('([^']+)'")


@pytest.fixture(scope="module")
def blocks() -> dict[str, list[dict]]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {"N3": [], "N4": [], "N5": []}
    for m in data.get("mappings", []) or []:
        wc = str(m.get("wp_code") or "").strip()
        if wc in out:
            out[wc].append(m)
    return out


def _cells(bs: list[dict]) -> list[tuple[str, str, str]]:
    """→ [(sheet, cell_ref, formula)]，跳过 PLACEHOLDER（formula 为 null）。"""
    return [
        (str(b.get("sheet") or ""), str(c.get("cell_ref") or ""), str(c.get("formula")))
        for b in bs
        for c in (b.get("cells") or [])
        if c.get("formula")
    ]


# ─── 反向自检 ────────────────────────────────────────────────────────────────


def test_self_check_blocks_non_empty(blocks):
    for wc in ("N3", "N4", "N5"):
        assert blocks[wc], f"{wc} 应有预设块（提取逻辑失效？）"
    assert len(_cells(blocks["N5"])) >= 8, "N5 cell 数异常偏少 → 正则或结构变了"


# ─── Property 9: 科目白名单 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", ["N3", "N4", "N5"])
def test_no_forbidden_codes(blocks, wp_code):
    bad: list[str] = []
    for sheet, ref, f in _cells(blocks[wp_code]):
        for code in _TB_CODE_RE.findall(f):
            head = code.split("~")[0].split(".")[0]
            if head in FORBIDDEN_CODES:
                bad.append(f"{sheet}::{ref}::{code}（{FORBIDDEN_CODES[head]}）")
    assert bad == [], f"{wp_code} 预设引用了禁用科目：{bad}"


@pytest.mark.parametrize("wp_code", ["N3", "N4", "N5"])
def test_accounts_whitelisted(blocks, wp_code):
    bad: list[str] = []
    for sheet, ref, f in _cells(blocks[wp_code]):
        for code in _TB_CODE_RE.findall(f):
            for part in code.split("~"):
                if not part.startswith(ALLOWED[wp_code]):
                    bad.append(f"{sheet}::{ref}::{part}")
    assert bad == [], (
        f"{wp_code} 预设引用了白名单外科目：{bad}；"
        f"允许前缀 {ALLOWED[wp_code]}（新增须有 report_config / 源模板依据）"
    )


@pytest.mark.parametrize("wp_code", ["N3", "N4", "N5"])
def test_block_account_codes_whitelisted(blocks, wp_code):
    bad = [
        f"{b.get('sheet')}::{c}"
        for b in blocks[wp_code]
        for c in (b.get("account_codes") or [])
        if not str(c).startswith(ALLOWED[wp_code])
    ]
    assert bad == [], f"{wp_code} 块的 account_codes 含白名单外科目：{bad}"


def test_n3_block_is_not_a_copy_of_n5(blocks):
    """N3 审定表块曾整块从 N5 复制（名称与科目都是所得税费用）。"""
    adj = [b for b in blocks["N3"] if "N3-1" in str(b.get("sheet") or "")]
    assert adj, "应有 N3-1 审定表块"
    for b in adj:
        assert b.get("account_codes") == ["2901"], b.get("account_codes")
        assert "递延所得税负债" in str(b.get("wp_name") or ""), b.get("wp_name")


def test_no_6403_subaccount_tax_type_lookup(blocks):
    """按 6403 子科目**编码**取税种是错的（编码语义客户间冲突）→ 不得出现 `TB('6403.xx')`。"""
    bad = [
        f"{sheet}::{ref}::{f}"
        for sheet, ref, f in _cells(blocks["N4"])
        if re.search(r"TB\w*\('6403\.\d", f)
    ]
    assert bad == [], (
        f"不得按 6403 子科目编码取税种（活体 6403.01 某客户是印花税）：{bad}；"
        "按税种取数已由后端 `_classify_n4_subaccount` 按名称实现"
    )


# ─── Property 8: 损益类恒取本期发生额 ────────────────────────────────────────


@pytest.mark.parametrize("wp_code", ["N4", "N5"])
def test_income_accounts_use_period_amount(blocks, wp_code):
    bad: list[str] = []
    for sheet, ref, f in _cells(blocks[wp_code]):
        for code, col in _TB_RE.findall(f):
            head = code.split(".")[0]
            if head in INCOME_CODES and col in ("期末余额", "期初余额", "未审数"):
                bad.append(f"{sheet}::{ref}::TB('{code}','{col}')")
    assert bad == [], (
        f"{wp_code} 损益类科目用了余额口径：{bad}；"
        "report_config 实证 IS-003 / IS-023 均为 `本期发生额`（平台铁律「损益取发生额」）"
    )


def test_balance_accounts_still_use_balance(blocks):
    """反向：余额类（N3 的 2901 / N5-8 的 1811·2901）**必须**用余额口径，防一刀切改错。"""
    cols = {
        col
        for _, _, f in _cells(blocks["N3"])
        for code, col in _TB_RE.findall(f)
        if code.startswith("2901")
    }
    assert cols and cols <= {"期末余额", "期初余额"}, f"N3 余额类口径异常：{cols}"


# ─── Property 10: cell_ref 唯一 ─────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", ["N3", "N4", "N5"])
def test_cell_refs_unique_within_wp_code(blocks, wp_code):
    """`page_key = workpaper:{wp_code}` 忽略 sheet → 同名 cell_ref 互相遮蔽。"""
    seen: dict[str, list[str]] = {}
    for b in blocks[wp_code]:
        for c in b.get("cells") or []:
            ref = str(c.get("cell_ref") or "")
            seen.setdefault(ref, []).append(f"{b.get('sheet')}={c.get('formula')}")
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    assert dups == {}, f"{wp_code} 内 cell_ref 撞键（page_key 忽略 sheet）：{dups}"


# ─── PLACEHOLDER 必须写明正确来源 ────────────────────────────────────────────


def test_placeholders_document_correct_source(blocks):
    """降级为 PLACEHOLDER 的 cell 必须在描述里写明正确来源，否则等于静默删功能。"""
    for wc in ("N3", "N4", "N5"):
        for b in blocks[wc]:
            for c in b.get("cells") or []:
                if c.get("formula"):
                    continue
                desc = str(c.get("description") or "")
                assert len(desc) >= 20, f"{wc}::{c.get('cell_ref')} PLACEHOLDER 描述过短：{desc!r}"


def test_profit_total_is_placeholder_not_revenue(blocks):
    """N5-4「利润总额」必须是 PLACEHOLDER（IS-022 是 ROW 派生行），不得取 6001。"""
    cells = [
        c
        for b in blocks["N5"]
        if "N5-4" in str(b.get("sheet") or "")
        for c in (b.get("cells") or [])
        if "利润总额" in str(c.get("cell_ref") or "")
    ]
    assert cells, "N5-4 应保留「利润总额」占位以记录正确来源"
    for c in cells:
        assert c.get("formula") is None, f"利润总额不应有取数公式：{c.get('formula')}"
        assert "IS-022" in str(c.get("description") or "")


# ─── 表达式可解析 ────────────────────────────────────────────────────────────

_PREFILL_ONLY_FUNCS = {"ADJ"}
_UNKNOWN_FUNC_RE = re.compile(r"未知函数:\s*([A-Z_]+)\(\)")


@pytest.mark.parametrize("wp_code", ["N3", "N4", "N5"])
def test_all_formulas_parse(blocks, wp_code):
    from app.services.formula_engine import validate_formula

    bad: list[str] = []
    for sheet, ref, f in _cells(blocks[wp_code]):
        expr = f[1:] if f.startswith("=") else f
        errors = validate_formula(expr)
        real = [
            m
            for m in errors
            if not (
                (hit := _UNKNOWN_FUNC_RE.search(m)) and hit.group(1) in _PREFILL_ONLY_FUNCS
            )
        ]
        if real:
            bad.append(f"{sheet}::{ref}::{f} → {real}")
    assert bad == [], f"{wp_code} 存在无法解析的表达式：{bad}"


def test_prefill_only_func_allowlist_still_needed():
    """反向自检：ADJ 若注册进 formula_engine，本豁免应移除。"""
    from app.services.formula_engine import _REGISTRY

    assert _PREFILL_ONLY_FUNCS & set(_REGISTRY.known_function_names()) == set()


# ─── 幂等脚本 ────────────────────────────────────────────────────────────────


def test_fix_script_reports_no_pending_work():
    import importlib

    mod = importlib.import_module("scripts.fix.fix_n345_prefill_presets")
    assert mod.apply(check_only=True) is False, "预设与脚本目标不一致，请重跑 fix 脚本"


def test_converted_presets_are_clean():
    from app.services.formula_management.preset_library import convert_prefill_presets

    entries = convert_prefill_presets()
    for wc in ("N3", "N4", "N5"):
        page = [e for e in entries if e.page_key == f"workpaper:{wc}"]
        assert page, f"workpaper:{wc} 应有预设条目"
        refs = [e.target_cell for e in page]
        assert len(refs) == len(set(refs)), f"workpaper:{wc} target_cell 撞键：{refs}"
        for e in page:
            for code in _TB_CODE_RE.findall(e.expression):
                head = code.split("~")[0]
                assert head.startswith(ALLOWED[wc]), (
                    f"公式管理里 {wc} 出现白名单外科目：{e.target_cell} → {e.expression}"
                )
