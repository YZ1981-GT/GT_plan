"""报表差异检测的**映射保真** — deliverable-lineage-wiring-… Wave 4 修正（2026-08-05）

## 这个文件在守什么

差异检测必须与 `ReportExcelExporter` **同源**地解析「哪个 sheet 的哪个格该放哪个
row_code」。旧实现按 `cell_mapping.json` 的 `sheet` 键 + `sheet_aliases` 只取**第一个**
匹配 sheet，而资产负债表在四个变体里**都拆成「主表 + 续表」两个 sheet**、两侧 row_code
在 JSON 里共用同一个 `sheet` 键 `balance_sheet` 且**坐标重叠**：

- soe 主表 `C6` = `BS-002 货币资金`；soe 续表 `C6` = `BS-055 短期借款`
- soe 主表 `C11` = `BS-007 应收票据`；soe 续表 `C11` = `BS-060 应付票据`

⇒ 续表的 row_code 全去主表取值 ⇒ 报出「应付票据拿到应收票据余额」这类**系统性错位**。
真实库项目 `0ec33ac9` 报表 v8 实测 22 处差异全部由此而来；修正后同一版本降到 5 处
（且经模板逐格核对确认是真差异），另一真实报表（`2aa00f57` / soe_standalone）
从「成片假差异」变为 **checked=452 / diffs=0 完全一致**。

判据全部落在**真实模板文件**上（`backend/data/audit_report_templates/financial_statements/`），
不用合成 fixture —— 这个缺陷的成因正是「真实模板拆了主表续表」，合成 fixture 测不出来。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.services.financial_report_drift_service import (
    CellSpec,
    DriftUnavailable,
    _is_later,
    compare_cell_specs,
    compare_cells,
    resolve_expected_cell_specs,
)

BACKEND = Path(__file__).resolve().parents[1]

VARIANTS = (
    "listed_consolidated",
    "listed_standalone",
    "soe_consolidated",
    "soe_standalone",
)


def _strip_py_comments(src: str) -> str:
    """剥掉 `#` 行注释与三引号 docstring（读源码型守卫必备）。"""
    out: list[str] = []
    i, n = 0, len(src)
    in_str: str | None = None
    while i < n:
        if in_str:
            if src.startswith(in_str, i):
                i += len(in_str)
                in_str = None
            else:
                i += 1
            continue
        if src.startswith('"""', i) or src.startswith("'''", i):
            in_str = src[i : i + 3]
            i += 3
            continue
        ch = src[i]
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def test_strip_comments_selfcheck():
    sample = 'a = 1  # read_sheet_values\n"""doc read_sheet_values"""\nb = 2\n'
    stripped = _strip_py_comments(sample)
    assert sample.count("read_sheet_values") == 2
    assert "read_sheet_values" not in stripped
    assert "a = 1" in stripped and "b = 2" in stripped


# ─── 映射解析：真实模板上的不变式 ───────────────────────────────────────────


#: 行业适用性标记 —— 平台在报表行名里用它标「特定行业适用」，
#: 模板 A 列与 cell_mapping 的 row_name **不保证同时带**（实测 `IS-027`：
#: JSON 写 `△利息收入`、模板写 `利息收入`）。比对行名时两侧都剥掉。
_ROW_NAME_MARKERS = "△▲※*"


def _norm_label(text: str) -> str:
    """行名归一：去全部空白 + 去行业适用性标记。**刻意不做更激进的归一化。**"""
    out = "".join(ch for ch in text if not ch.isspace())
    return out.strip(_ROW_NAME_MARKERS).replace("△", "").replace("▲", "")


def test_label_norm_still_catches_real_misalignment():
    """反向自检：归一化不得宽到放过真实错位。

    「短期借款」落在「货币资金」行上必须仍判不符；而只差标记符号的必须判相符。
    """
    assert _norm_label("短期借款") not in _norm_label("  货币资金")
    assert _norm_label("应付票据") not in _norm_label("  应收票据")
    assert _norm_label("△利息收入") in _norm_label("            利息收入")
    assert _norm_label("其中：应付利息") in _norm_label("  其中：应付利息")


@pytest.fixture(scope="module")
def specs_by_variant() -> dict[str, list[CellSpec]]:
    out: dict[str, list[CellSpec]] = {}
    for vk in VARIANTS:
        specs = resolve_expected_cell_specs(vk)
        assert specs, f"变体 {vk} 未解析出映射格（模板或 cell_mapping 缺失？）"
        out[vk] = specs
    return out


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_two_row_codes_share_one_cell(variant, specs_by_variant):
    """🔴 核心不变式：同一 `(sheet, 坐标)` 不得对应多个 row_code。

    这是「错位」的**直接判据** —— 旧实现下资产负债表续表的 row_code 会和主表
    的 row_code 落到同一 `(balance_sheet, C6)`，这条断言必红。
    """
    clash: dict[tuple[str, str], set[str]] = {}
    for s in specs_by_variant[variant]:
        clash.setdefault((s.sheet, s.coord), set()).add(s.row_code)
    bad = {k: sorted(v) for k, v in clash.items() if len(v) > 1}
    assert not bad, f"{variant} 存在一格对多 row_code（映射错位）: {list(bad.items())[:5]}"


@pytest.mark.parametrize("variant", VARIANTS)
def test_balance_sheet_main_and_continuation_are_distinct_sheets(
    variant, specs_by_variant
):
    """资产负债表主表与续表必须是**两个不同的 sheet 名**。

    JSON 里它们共用 `sheet` 键 `balance_sheet`，只有按真实 sheet 名区分才不串味。
    """
    sheets = sorted({s.sheet for s in specs_by_variant[variant] if "资产负债表" in s.sheet})
    assert len(sheets) >= 2, f"{variant} 资产负债表只解析出 {sheets}（主表/续表未分开）"
    assert len(set(sheets)) == len(sheets)


@pytest.mark.parametrize("variant", VARIANTS)
def test_spec_row_name_matches_template_label(variant, specs_by_variant):
    """每个 spec 的 `row_name` 必须与模板**同行 A 列**文字一致（语义正确性）。

    这条是「错位」的语义判据：错位时 `BS-055 短期借款` 会落在写着「货币资金」的行上。

    归一化只做两件事（见 `_norm_label`）：去空白、去行业适用性标记 `△▲※*`。
    后者是平台在用的记号（模板 A 列实测有 `▲应收保费`、JSON 有 `△利息收入`），
    同一行两侧标不标记并不一致 —— 实测 `IS-027` 就是 JSON 带 `△`、模板不带。
    **不做更激进的归一化**，并由 `test_label_norm_still_catches_real_misalignment`
    钉住「归一化没有宽到放过真错位」。
    """
    from app.services.report_excel_exporter import ReportExcelExporter

    wb = ReportExcelExporter(None)._load_template(variant)  # noqa: SLF001
    assert wb is not None, f"{variant} 模板缺失"
    try:
        mismatched: list[str] = []
        checked = 0
        for s in specs_by_variant[variant]:
            if s.row_name == s.row_code or s.sheet not in wb.sheetnames:
                continue
            ws = wb[s.sheet]
            label = ws.cell(row=ws[s.coord].row, column=1).value
            if not isinstance(label, str):
                continue
            checked += 1
            if _norm_label(s.row_name) not in _norm_label(label):
                mismatched.append(
                    f"{s.row_code} {s.row_name!r} @ {s.sheet}!{s.coord} 模板A={label!r}"
                )
    finally:
        wb.close()

    assert checked > 50, f"{variant} 只核对了 {checked} 格 ⇒ 判据近乎空转"
    assert not mismatched, (
        f"{variant} 有 {len(mismatched)} 处 row_name 与模板行名不符（映射错位）: "
        f"{mismatched[:8]}"
    )


def test_reverse_selfcheck_json_only_view_really_clashes():
    """🔴 反向自检：复现旧口径（按 JSON `sheet` 键）**必须**出现一格对多 row_code。

    若这条不成立，说明 JSON 里主表/续表已不再共用键、上面几条断言就成了空转 ——
    那时应把本自检改成「JSON 已分键」的正向断言，而不是删掉。
    """
    from app.services.financial_report_drift_service import _load_variant_mapping

    variant = _load_variant_mapping("soe_standalone")
    assert variant is not None
    clash: dict[tuple[str, str], set[str]] = {}
    for code, entry in (variant.get("rows") or {}).items():
        if not isinstance(entry, dict):
            continue
        coord = entry.get("current")
        if coord:
            clash.setdefault((entry.get("sheet") or "", coord), set()).add(code)
    bad = {k: v for k, v in clash.items() if len(v) > 1}
    assert bad, (
        "cell_mapping.json 的 (sheet键, 坐标) 已不再撞码 —— "
        "旧口径不再产生错位，请把本自检改为正向断言"
    )
    # 具体钉住已知的那对（货币资金 / 短期借款 同为 balance_sheet!C6）
    assert ("balance_sheet", "C6") in bad
    assert {"BS-002", "BS-055"} <= bad[("balance_sheet", "C6")]


def test_specs_cover_all_four_report_types():
    """解析结果必须覆盖资产负债表 / 利润表 / 现金流量表（少一类等于漏检那张表）。"""
    specs = resolve_expected_cell_specs("soe_standalone") or []
    prefixes = {s.row_code.split("-", 1)[0] for s in specs}
    assert {"BS", "IS", "CFS"} <= prefixes, f"覆盖不足: {sorted(prefixes)}"


def test_unknown_variant_returns_none_not_raise():
    """未配变体 ⇒ 放行（None），不得抛（需求 10.5）。"""
    assert resolve_expected_cell_specs("no_such_variant") is None


def test_json_parse_failure_still_fail_closed(monkeypatch):
    """🔴 JSON 解析失败必须仍 fail-closed（需求 10.6），不得被内联占位符回退绕过。

    否则只要弄坏配置文件，「无内联占位符的 sheet」就会静默退出比对面 = 后门。
    """
    import app.services.financial_report_drift_service as mod

    def _boom(_key):
        raise DriftUnavailable("Cell_Mapping 解析失败: 坏了")

    monkeypatch.setattr(mod, "_load_variant_mapping", _boom)
    with pytest.raises(DriftUnavailable):
        mod.resolve_expected_cell_specs("soe_standalone")


def test_detect_uses_template_sourced_specs():
    """源码级：`detect()` 必须走模板解析 + 真实 sheet 名取值，不得再按 alias 猜。"""
    src = _strip_py_comments(
        (BACKEND / "app" / "services" / "financial_report_drift_service.py").read_text(
            encoding="utf-8"
        )
    )
    i = src.index("async def detect")
    j = src.index("async def _baseline_diff_keys")
    body = src[i:j]
    assert "resolve_expected_cell_specs(" in body, "detect 未走模板解析"
    assert "compare_cell_specs(" in body, "detect 未走 spec 比对"
    assert "read_values_for_sheets(" in body, "detect 未按真实 sheet 名取值"
    assert "read_sheet_values(" not in body, "detect 仍在用按 alias 猜 sheet 的旧读法"
    # 基线比对必须同口径，否则 pre_existing 标记会全错
    tail = src[j:]
    assert "compare_cell_specs(" in tail and "read_values_for_sheets(" in tail


def test_alias_guessing_reader_is_gone():
    """旧的按 `sheet_aliases` 猜 sheet 的读取函数必须已删除（防两份口径并存）。"""
    import app.services.financial_report_drift_service as mod

    assert not hasattr(mod, "read_sheet_values"), (
        "read_sheet_values 仍在 ⇒ 两份取值口径并存，改一处另一处不红"
    )
    assert hasattr(mod, "read_values_for_sheets")


# ─── compare_cells 薄壳零回归 ───────────────────────────────────────────────


def test_compare_cells_shim_delegates_to_spec_comparison():
    """`compare_cells`（JSON 口径薄壳）与 `compare_cell_specs` 结果必须一致。

    保留薄壳是为了既有守卫的纯比对单测；两者若各写一份比对逻辑就会漂移。
    """
    variant = {
        "rows": {
            "BS-006": {"sheet": "balance_sheet", "row_name": "应收票据", "current": "C6"},
            "BS-009": {"sheet": "balance_sheet", "row_name": "应收账款", "prior": "D12"},
        }
    }
    sheet_values = {"balance_sheet": {"C6": 1000.0, "D12": 500.0}}
    expected = {
        "BS-006": {"current_period_amount": "900.00"},
        "BS-009": {"prior_period_amount": "400.00"},
    }
    via_shim = compare_cells(variant, sheet_values, expected)
    via_specs = compare_cell_specs(
        [
            CellSpec("balance_sheet", "BS-006", "应收票据", "current", "C6"),
            CellSpec("balance_sheet", "BS-009", "应收账款", "prior", "D12"),
        ],
        sheet_values,
        expected,
    )
    key = lambda ds: sorted((d["row_code"], d["period"], d["diff"]) for d in ds)  # noqa: E731
    assert key(via_shim) == key(via_specs)
    assert len(via_shim) == 2


def test_compare_cell_specs_isolates_same_coord_across_sheets():
    """同坐标不同 sheet 必须各取各的值（这正是主表/续表能分开的机制）。"""
    specs = [
        CellSpec("主表", "BS-002", "货币资金", "current", "C6"),
        CellSpec("续表", "BS-055", "短期借款", "current", "C6"),
    ]
    sheet_values = {"主表": {"C6": 100.0}, "续表": {"C6": 700.0}}
    expected = {
        "BS-002": {"current_period_amount": "100.00"},
        "BS-055": {"current_period_amount": "700.00"},
    }
    assert compare_cell_specs(specs, sheet_values, expected) == []

    # 若两 sheet 的值被混淆（旧行为），两行都会报差异
    mixed = {"主表": {"C6": 100.0}, "续表": {"C6": 100.0}}
    diffs = compare_cell_specs(specs, mixed, expected)
    assert [d["row_code"] for d in diffs] == ["BS-055"]


# ─── 时区混用（真实库跑 detect 时暴露的真 bug）───────────────────────────────


def test_is_later_tolerates_naive_and_aware_mix():
    """🔴 平台时间戳混用 naive/aware，裸 `>` 比较会抛 TypeError。

    真实库跑 detect 时 `_attribute` 因此抛异常冒泡，被外层 `except Exception`
    吞成 warning ⇒ `drift_report` 恒 None、整个检测又变成死的
    （fail-open 把 bug 伪装成"无数据"）。
    """
    from datetime import datetime, timezone

    naive_late = datetime(2026, 1, 2)
    aware_early = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # 反向自检：裸比较确实会抛（证明这个函数不是多余的）
    with pytest.raises(TypeError):
        _ = naive_late > aware_early  # type: ignore[operator]

    assert _is_later(naive_late, aware_early) is True
    assert _is_later(aware_early, naive_late) is False
    # 任一为 None ⇒ 未知不算「晚」
    assert _is_later(None, aware_early) is False
    assert _is_later(naive_late, None) is False
    # 相等不算晚
    assert _is_later(aware_early, aware_early) is False


def test_attribute_does_not_compare_datetimes_bare():
    """源码级：`_attribute` 不得再裸比较两个 datetime。"""
    src = _strip_py_comments(
        (BACKEND / "app" / "services" / "financial_report_drift_service.py").read_text(
            encoding="utf-8"
        )
    )
    i = src.index("async def _attribute")
    j = src.index("async def _is_version_stale")
    body = src[i:j]
    assert "_is_later(" in body, "_attribute 未走时区归一比较"
    assert "> ver.created_at" not in body, "仍在裸比较 datetime ⇒ naive/aware 混用会抛"
