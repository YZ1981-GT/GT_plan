"""K1/K2 收进声明真源后的 **characterization** 守卫（Requirement 3.1~3.4）。

**为什么需要**

Task 4 把 K1/K2 收进 `K_CYCLE_SPECS`，但两个 render 当时**仍在文件内字面构造**
`ReportLineAccountSpec` ⇒ 同一循环两份科目声明 = 双真源，改一处另一处不动。
Task 6 把 render 改为从声明表派生（`K_CYCLE_SPECS['K1'].spec_for(...)`）。

**本文件的判据是「派生值必须与改造前逐字段相同」** —— 不是「派生成功即可」。
实测这次改造一度丢掉三处（都不报错、测试也不红）：

===================================  ==================  ==================
字段                                  改造前               首版派生（错）
===================================  ==================  ==================
K1 ``fallback_provision``            ``('1231-03',)``    ``()``
K1 ``provision_name_filter``         ``'其他应收款'``      ``'其他应收'``
K2 ``extra_standard_codes``          ``('1131',)``       ``()``
===================================  ==================  ==================

- `fallback_provision` 丢失最重：报表公式没解析出备抵码时（listed 侧 `BS-009`
  就是 `TB('1221','期末余额')` 不含备抵）备抵侧会**彻底取不到坏账**，
  K1-1 审定表「减：坏账准备」恒 0 ⇒ 净额虚高。
- `provision_name_filter` 变窄成「其他应收」看似等价，实际是**不同的过滤集**
  （宽前缀 `1231` 下要挡掉 `1231-02 坏账准备-应收账款`）；这类「差一个字」
  的改动最容易被当成笔误顺手改回去。
- K2 的 `1131` 是「报表公式引用但不并入原值」的附加科目（已属 BS-009/K1），
  丢了会让 K2 的「与报表核对」区少一项。

⚠️ 基线值**写死在本文件**（`_BASELINE`）而不是从声明表读 —— 从声明表读就是
拿被测对象证明自己。要改基线必须写明依据（哪个 DB 实证 / 哪次裁决）。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/ (Task 6)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.four_table.k_cycle_specs import (
    CYCLES_EXEMPT_FROM_ACCOUNT_SPEC,
    K_CYCLE_SPECS,
)

# ─────────────────────────────────────────────────────────────────────────────
# 改造前基线（2026-08-09 从 render 文件内的字面 spec 逐字段抄录）
# ─────────────────────────────────────────────────────────────────────────────

#: 循环 → {字段名: 期望值}。改造前 render 里的 `ReportLineAccountSpec(...)` 原值。
_BASELINE: dict[str, dict[str, object]] = {
    "K1": {
        "row_code": "BS-009",
        "fallback_gross": ("1221",),
        # 🔴 报表公式在 listed 侧不含备抵（`TB('1221','期末余额')`）⇒ 备抵只能靠兜底
        "fallback_provision": ("1231-03",),
        # 🔴 完整词「其他应收款」 —— 写成「其他应收」是**另一个过滤集**
        "provision_name_filter": "其他应收款",
        # 1131 应收股利 / 1132 应收利息：报表行含它们但 K1-1 第一段明确排除
        "extra_standard_codes": ("1131", "1132"),
        "provision_row_code": None,
        "is_liability": False,
        "gross_direction": None,
    },
    "K2": {
        "row_code": "BS-014",
        "fallback_gross": ("1901",),
        "fallback_provision": (),  # 其他流动资产无备抵科目
        "provision_name_filter": None,
        "extra_standard_codes": ("1131",),  # 应收股利已属 BS-009，不并入原值
        "provision_row_code": None,
        "is_liability": False,
        "gross_direction": None,
    },
}

_STANDARD_SETS: tuple[tuple[str, list[str]], ...] = (
    ("soe", ["soe_standalone", "soe", "standalone"]),
    ("listed", ["listed_standalone", "listed", "standalone"]),
)

_RENDER_DIR = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_render_strategies"
_RENDER_FILES = {
    "K1": "_k1_other_receivables.py",
    "K2": "_k2_other_current_assets.py",
}


def _strip_comments(src: str) -> str:
    """剥 `#` 行注释与三引号 docstring（判据不得把说明文字数成真实代码）。"""
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    out = re.sub(r"(?m)#.*$", "", out)
    return out


def _render_source(wp: str) -> str:
    return (_RENDER_DIR / _RENDER_FILES[wp]).read_text("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 判据自检（类 A：应当全绿）
# ─────────────────────────────────────────────────────────────────────────────


def test_baseline_and_render_files_exist():
    """反向自检：基线非空 + render 文件真的读到了，否则下面全是空转。"""
    assert set(_BASELINE) == {"K1", "K2"}
    for wp in _BASELINE:
        assert _BASELINE[wp], f"{wp} 基线为空"
        src = _render_source(wp)
        assert len(src) > 2000, f"{_RENDER_FILES[wp]} 读到的内容过短（{len(src)} 字符）"


def test_strip_comments_actually_strips():
    """反向自检：剥注释真的生效（否则「禁字面构造」那条会被说明文字骗）。"""
    sample = '"""doc ReportLineAccountSpec( in docstring"""\nx = 1  # ReportLineAccountSpec(\n'
    assert "ReportLineAccountSpec(" in sample
    assert "ReportLineAccountSpec(" not in _strip_comments(sample)


def test_k1_k2_are_in_the_declaration_table():
    """Requirement 3.1：K1/K2 必须已在声明真源里。"""
    for wp in ("K1", "K2"):
        assert wp in K_CYCLE_SPECS, f"{wp} 未收进 K_CYCLE_SPECS（Requirement 3.1）"


# ─────────────────────────────────────────────────────────────────────────────
# characterization：派生值逐字段 == 改造前
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp", sorted(_BASELINE))
@pytest.mark.parametrize("label,stds", _STANDARD_SETS, ids=[s[0] for s in _STANDARD_SETS])
def test_derived_spec_matches_pre_migration_baseline(wp: str, label: str, stds: list[str]):
    """派生出的 `ReportLineAccountSpec` 必须与改造前逐字段相同。

    两准则都要过 —— K1/K2 实测两侧同号，若哪天分变体，本断言会强制先更新基线。
    """
    spec = K_CYCLE_SPECS[wp].spec_for(stds)
    want = _BASELINE[wp]
    diffs: list[str] = []
    for field, expected in want.items():
        got = getattr(spec, field, "<MISSING>")
        if got != expected:
            diffs.append(f"  {field}: 派生={got!r} 基线={expected!r}")
    assert not diffs, (
        f"{wp}（{label} 准则）派生 spec 与改造前不一致 —— 收进声明真源"
        f"**不得改变取数行为**：\n" + "\n".join(diffs)
    )


@pytest.mark.parametrize("wp", sorted(_BASELINE))
def test_no_literal_spec_construction_left_in_render(wp: str):
    """双真源已消除：render 里不得再字面构造 `ReportLineAccountSpec`。

    判据落在**剥注释后**的代码上 —— 说明文字里提到该类名是合法的
    （改造记载正是下个会话需要的信息）。
    """
    code = _strip_comments(_render_source(wp))
    hits = len(re.findall(r"\bReportLineAccountSpec\s*\(", code))
    assert hits == 0, (
        f"{_RENDER_FILES[wp]} 仍有 {hits} 处字面构造 `ReportLineAccountSpec(` —— "
        f"应改为 `K_CYCLE_SPECS['{wp}'].spec_for(...)`，否则声明表与 render 是双真源"
    )


@pytest.mark.parametrize("wp", sorted(_BASELINE))
def test_render_actually_consumes_the_declaration_table(wp: str):
    """正向：render 必须真的引用声明表（防「删了字面构造但也没接上」）。"""
    code = _strip_comments(_render_source(wp))
    assert "K_CYCLE_SPECS" in code, (
        f"{_RENDER_FILES[wp]} 未引用 K_CYCLE_SPECS —— 上一条只保证「没有字面构造」，"
        f"这条保证「真的接到了真源」"
    )


@pytest.mark.parametrize("wp", sorted(_BASELINE))
def test_legacy_module_constants_still_exported(wp: str):
    """兼容常量必须保留 —— 外部消费方（含导入导出模块与既有守卫）在读它们。

    实测消费方：`_k1_import_export._resolve_k1_gross_prefixes` 读 `K1_ACCOUNT_SPEC`；
    `test_k1_adjudication_prefill` 读 `K1_REPORT_ROW_CODE` / `K1_ACCOUNT_SPEC`。
    删掉这些名字会让它们 ImportError，而 `get_diagnostics` 查不出。
    """
    import importlib

    mod = importlib.import_module(
        f"app.routers.wp_render_strategies.{_RENDER_FILES[wp][:-3]}"
    )
    expected: dict[str, object] = {
        "K1": {
            "K1_REPORT_ROW_CODE": "BS-009",
            "K1_FALLBACK_GROSS": "1221",
            "K1_FALLBACK_PROVISION": "1231-03",
            "K1_DIVIDEND_STANDARD": "1131",
            "K1_INTEREST_STANDARD": "1132",
            "K1_PROVISION_NAME_FILTER": "其他应收款",
        },
        "K2": {
            "K2_REPORT_ROW_CODE": "BS-014",
            "K2_FALLBACK_GROSS": "1901",
            "K2_DIVIDEND_STANDARD": "1131",
        },
    }[wp]
    missing: list[str] = []
    wrong: list[str] = []
    for name, val in expected.items():
        if not hasattr(mod, name):
            missing.append(name)
        elif getattr(mod, name) != val:
            wrong.append(f"{name}: {getattr(mod, name)!r} != {val!r}")
    assert not missing, f"{wp} 兼容常量缺失（外部消费方会 ImportError）：{missing}"
    assert not wrong, f"{wp} 兼容常量取值漂移：{wrong}"
    # `X_ACCOUNT_SPEC` 也必须仍在（导入导出模块直接用它）
    assert hasattr(mod, f"{wp}_ACCOUNT_SPEC"), f"{wp}_ACCOUNT_SPEC 丢失"


# ─────────────────────────────────────────────────────────────────────────────
# K0 豁免登记
# ─────────────────────────────────────────────────────────────────────────────


def test_k0_is_explicitly_exempt_with_reason():
    """Requirement 3.4：K0 是函证循环、无科目余额 ⇒ 显式豁免且必须写理由。"""
    assert "K0" in CYCLES_EXEMPT_FROM_ACCOUNT_SPEC, (
        "K0 必须显式登记豁免 —— 「不在 K_CYCLE_SPECS 里」与「忘了加」不可区分"
    )
    reason = str(CYCLES_EXEMPT_FROM_ACCOUNT_SPEC["K0"] or "")
    assert len(reason) >= 10, f"K0 豁免理由过短：{reason!r}"
    assert "函证" in reason, f"K0 豁免理由应说明它是函证循环：{reason!r}"


def test_exempt_cycles_are_not_in_the_spec_table():
    """反向：登记豁免的循环不得同时出现在声明表里（两者互斥）。"""
    both = sorted(set(CYCLES_EXEMPT_FROM_ACCOUNT_SPEC) & set(K_CYCLE_SPECS))
    assert not both, f"以下循环既登记豁免又在声明表里，语义冲突：{both}"
