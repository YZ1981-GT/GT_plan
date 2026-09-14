"""示例行判定收紧（全字段相等）—— Property 4 / Property 5。

spec: adjustment-import-export-contract / Task 1.3

Property 4（示例行判定单调）
  数据行与 Example_Row 全部可比字段相等 ⟺ 被跳过；
  任一可比字段不同 ⟹ 必被当作数据行导入；被跳过的示例行不计入 failed。

Property 5（模板示例仍被跳过）
  以内置示例原样提交的模板，其示例行仍被识别并跳过
  （收紧判定不得让示例行变成脏数据）。

PBT 用 hypothesis `max_examples=5`（平台 fast profile 亦为 5）。
"""
from __future__ import annotations

import io

import openpyxl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.import_template_service import (
    TEMPLATE_COLUMNS,
    TEMPLATE_EXAMPLE_ROWS,
    ImportType,
    _is_example_row,
    generate_template,
    parse_import_data,
    validate_import_file,
)

_ADJ_COLUMNS = TEMPLATE_COLUMNS[ImportType.adjustments]
_ADJ_HEADERS = [c[0] for c in _ADJ_COLUMNS]

# 富模板（GET /adjustments/export-template）AJE模板 / RJE模板 的 4 行内置示例，
# 数值列按模板真实写法给成数字（读取端 `str(v or "")` 会把 0 读成 ""）。
_AJE_EXAMPLES: list[tuple] = [
    ("AJE-001", "AJE", "补提应收账款减值", "", "应收账款", "", "", "", 0, 100000.00),
    ("AJE-001", "AJE", "补提应收账款减值", "", "信用减值损失", "", "", "", 100000.00, 0),
]
_RJE_EXAMPLES: list[tuple] = [
    ("RJE-001", "RJE", "长投重分类为其他权益工具", "", "其他权益工具投资", "", "", "", 50000.00, 0),
    ("RJE-001", "RJE", "长投重分类为其他权益工具", "", "长期股权投资", "", "", "", 0, 50000.00),
]
_BLANK_EXAMPLE_ROW: tuple = ("", "", "", "", "", "", "", "", 0, 0)


def _as_read(row: tuple) -> list[str]:
    """模拟读取端 `str(v or "").strip()` 的取值（0 → ""）。"""
    return [str(v or "").strip() for v in row]


def _all_builtin_example_rows() -> list[tuple]:
    return _AJE_EXAMPLES + _RJE_EXAMPLES


# ═══════════════════════════════════════════════════════════════════════════
# Property 5: 模板内置示例仍被跳过
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("row", _all_builtin_example_rows())
def test_p5_all_rich_template_example_rows_are_skipped(row):
    """富模板 4 行内置示例（AJE/RJE 各借贷两行）逐行仍被识别为示例。"""
    assert _is_example_row(_as_read(row), _ADJ_COLUMNS) is True


@pytest.mark.parametrize("import_type", sorted(TEMPLATE_COLUMNS, key=lambda t: t.value))
def test_p5_generic_template_example_row_is_skipped(import_type):
    """通用裸模板（generate_template）第 2 行示例对每种导入类型仍被跳过。"""
    columns = TEMPLATE_COLUMNS[import_type]
    example_row = [str(c[3]) for c in columns]
    assert _is_example_row(example_row, columns) is True


def test_p5_registry_covers_every_rich_template_example_row():
    """登记表 + TEMPLATE_COLUMNS 单示例必须覆盖模板里的每一行内置示例。

    否则收紧判定会让未登记的示例行变成脏数据。
    """
    single = [str(c[3]) for c in _ADJ_COLUMNS]
    registered = [single] + TEMPLATE_EXAMPLE_ROWS[ImportType.adjustments]
    for row in _all_builtin_example_rows():
        read = _as_read(row)
        assert any(
            all(
                str(a).strip() == str(b).strip()
                or (str(b).strip() == "")
                or _num_eq(a, b)
                for a, b in zip(read, cand)
            )
            for cand in registered
        ), f"示例行未被任何候选覆盖: {read}"


def _num_eq(a, b) -> bool:
    try:
        return float(str(a).replace(",", "")) == float(str(b).replace(",", ""))
    except (ValueError, TypeError):
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Property 4: 判定单调（任一可比字段不同 ⟹ 数据行）
# ═══════════════════════════════════════════════════════════════════════════


def _matchable_indexes(candidate: list[str]) -> list[int]:
    return [i for i, v in enumerate(candidate) if str(v).strip()]


_EXAMPLE_INDEX = st.integers(min_value=0, max_value=len(_all_builtin_example_rows()) - 1)


@settings(max_examples=5, deadline=None)
@given(
    ex_idx=_EXAMPLE_INDEX,
    field_pick=st.integers(min_value=0, max_value=9),
    suffix=st.text(alphabet="真实数据XY0123", min_size=1, max_size=4),
)
def test_p4_changing_any_matchable_field_makes_it_a_data_row(ex_idx, field_pick, suffix):
    """任一可比字段被改动（值不同）⟹ 必被当作数据行（不跳过）。"""
    base_row = _as_read(_all_builtin_example_rows()[ex_idx])

    # 可比字段 = 任一候选示例中非空的位置（并集）；只改这些位置才有语义
    candidates = [[str(c[3]) for c in _ADJ_COLUMNS]] + TEMPLATE_EXAMPLE_ROWS[
        ImportType.adjustments
    ]
    matchable = sorted({i for c in candidates for i in _matchable_indexes(c)})
    target = matchable[field_pick % len(matchable)]

    mutated = list(base_row)
    mutated[target] = f"{mutated[target]}{suffix}_改"
    assert mutated[target] != base_row[target]

    assert _is_example_row(mutated, _ADJ_COLUMNS) is False, (
        f"改动第 {target} 列后仍被判为示例行（会静默吞掉真实数据）"
    )


@settings(max_examples=5, deadline=None)
@given(ex_idx=_EXAMPLE_INDEX)
def test_p4_unmodified_example_row_is_skipped(ex_idx):
    """未改动的内置示例行 ⟹ 跳过（判定双向成立）。"""
    assert _is_example_row(_as_read(_all_builtin_example_rows()[ex_idx]), _ADJ_COLUMNS) is True


def test_p4_real_data_row_overwriting_example_position_is_imported():
    """回归本 spec 要修的缺陷：在示例行位置覆盖填写第一笔真实分录必须被导入。"""
    # 编号/类型/科目 与示例相同，摘要与金额是真实值 → 3/5 可比字段相同
    row = ["AJE-001", "AJE", "计提本期坏账", "", "应收账款", "", "", "", "0", "888888"]
    assert _is_example_row(row, _ADJ_COLUMNS) is False


def test_p4_amount_only_difference_is_data_row():
    """仅金额不同（其余全同）也必须是数据行。"""
    row = _as_read(_AJE_EXAMPLES[0])
    row[9] = "100001"  # 贷方金额 100000 → 100001
    assert _is_example_row(row, _ADJ_COLUMNS) is False


def test_p4_zero_amount_column_is_comparable():
    """示例金额为 0 的列同样可比：在示例行填入借方金额即成为数据行。

    （富模板 AJE 第 1 行借方=0，读取端读成 ""；若把空值当"不可比"，
      用户在该格填真实金额仍会被吞 —— hypothesis 抓到过这个漏洞。）
    """
    row = _as_read(_AJE_EXAMPLES[0])
    assert row[8] == "", "借方金额 0 被读取端读成空字符串"
    row[8] = "123456"
    assert _is_example_row(row, _ADJ_COLUMNS) is False


@pytest.mark.parametrize("ex_idx", range(len(_all_builtin_example_rows())))
def test_p4_exhaustive_single_field_mutation_yields_data_row(ex_idx):
    """穷举：每行内置示例 × 每个可比列，改动任一列后都必须落数据行（Property 4）。"""
    from app.services.import_template_service import (
        _example_comparable_pairs,
        _example_row_candidates,
    )

    base = _as_read(_all_builtin_example_rows()[ex_idx])
    assert _is_example_row(base, _ADJ_COLUMNS) is True

    # 命中该示例行的候选 → 其可比列即需逐列验证的集合
    comparable: set[int] = set()
    for cand in _example_row_candidates(_ADJ_COLUMNS):
        pairs = _example_comparable_pairs(base, cand, _ADJ_COLUMNS)
        if pairs and all(
            str(a).strip() == str(b).strip() or _num_eq(a, b) for a, b in pairs
        ):
            for idx, (_a, example) in enumerate(zip(base, cand)):
                dtype = str(_ADJ_COLUMNS[idx][2])
                if str(example).strip() or "数值" in dtype:
                    comparable.add(idx)
    assert comparable, "未定位到命中的候选示例行"

    for idx in sorted(comparable):
        mutated = list(base)
        mutated[idx] = "9" if "数值" in str(_ADJ_COLUMNS[idx][2]) else "真实值"
        if mutated[idx] == base[idx]:
            continue
        assert _is_example_row(mutated, _ADJ_COLUMNS) is False, (
            f"示例行 {ex_idx} 改动第 {idx} 列（{_ADJ_HEADERS[idx]}）后仍被判为示例行"
        )


def test_p4_empty_row_is_not_example():
    assert _is_example_row([], _ADJ_COLUMNS) is False


def test_p4_blank_example_row_is_not_matched_as_example():
    """富模板的 3 行空白示例行不靠示例判定跳过（由全空行检查跳过），不得误判。"""
    assert _is_example_row(_as_read(_BLANK_EXAMPLE_ROW), _ADJ_COLUMNS) is False


# ═══════════════════════════════════════════════════════════════════════════
# 被跳过的示例行以独立口径可见，且不计入 failed（R2.3 / R2.2）
# ═══════════════════════════════════════════════════════════════════════════


def _build_adjustment_workbook(
    *, aje_rows: list[tuple], rje_rows: list[tuple]
) -> bytes:
    wb = openpyxl.Workbook()
    ws_notes = wb.active
    ws_notes.title = "关注事项"  # parse 阶段应跳过的说明型 sheet
    ws_notes.cell(row=1, column=1, value="说明")

    for sheet_name, rows in (("AJE模板", aje_rows), ("RJE模板", rje_rows)):
        ws = wb.create_sheet(sheet_name)
        for col, h in enumerate(_ADJ_HEADERS, 1):
            ws.cell(row=1, column=col, value=h)
        for r, row in enumerate(rows, 2):
            for col, v in enumerate(row, 1):
                ws.cell(row=r, column=col, value=v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_REAL_ROW: tuple = (
    "AJE-100", "AJE", "计提本期坏账", "", "应收账款", "", "", "", 0, 888888.00,
)
_REAL_ROW_AT_EXAMPLE_POSITION: tuple = (
    "AJE-001", "AJE", "计提本期坏账", "", "应收账款", "", "", "", 0, 888888.00,
)


def test_parse_skips_only_example_rows_and_reports_count():
    """内置示例原样提交 + 真实行 → 示例被跳过并计数，真实行全部保留。"""
    content = _build_adjustment_workbook(
        aje_rows=[*_AJE_EXAMPLES, _REAL_ROW],
        rje_rows=[*_RJE_EXAMPLES, _BLANK_EXAMPLE_ROW],
    )
    stats: dict = {}
    rows = parse_import_data(ImportType.adjustments, content, stats=stats)

    assert stats["example_skipped"] == 4, "4 行内置示例应全部被跳过"
    # 真实数据行必须保留
    assert [r.get("编号") for r in rows if r.get("编号")] == ["AJE-100"]
    # 富模板的空白示例行金额写 0（非空字符串）→ parse 阶段不算全空行而保留，
    # 由 `_import_adjustments` 的「无科目且借贷均 0」判定忽略（既有行为，不在本 task 范围）
    assert len(rows) == 2
    blank = [r for r in rows if not r.get("编号")][0]
    assert not (blank.get("二级科目名称") or "") and float(blank.get("贷方金额") or 0) == 0


def test_parse_keeps_real_row_written_over_example_position():
    """审计师在示例行位置（第 2 行）覆盖填写真实分录 → 不得被吞。"""
    content = _build_adjustment_workbook(
        aje_rows=[_REAL_ROW_AT_EXAMPLE_POSITION], rje_rows=[]
    )
    stats: dict = {}
    rows = parse_import_data(ImportType.adjustments, content, stats=stats)

    assert stats["example_skipped"] == 0
    assert len(rows) == 1
    assert rows[0]["摘要"] == "计提本期坏账"


def test_parse_stats_optional_and_contract_unchanged():
    """不传 stats 时返回值契约不变（仅 list）。"""
    content = _build_adjustment_workbook(aje_rows=[_REAL_ROW], rje_rows=[])
    rows = parse_import_data(ImportType.adjustments, content)
    assert isinstance(rows, list) and len(rows) == 1


def test_validate_counts_example_rows_without_errors():
    """校验阶段：示例行被跳过时计入 example_skipped_count，且不产生任何 error。"""
    content = _build_adjustment_workbook(
        aje_rows=[*_AJE_EXAMPLES, _REAL_ROW], rje_rows=[]
    )
    result = validate_import_file(ImportType.adjustments, content, "t.xlsx")

    assert result.example_skipped_count == 2
    assert result.row_count == 1, "示例行不计入有效数据行"
    assert result.valid is True and result.errors == []
    assert result.to_dict()["example_skipped_count"] == 2


def test_validate_dict_omits_example_key_when_none_skipped():
    """无示例行被跳过时响应结构逐字节不变（不附带 example_skipped_count）。"""
    content = _build_adjustment_workbook(aje_rows=[_REAL_ROW], rje_rows=[])
    result = validate_import_file(ImportType.adjustments, content, "t.xlsx")

    assert result.example_skipped_count == 0
    assert "example_skipped_count" not in result.to_dict()


def test_generic_template_roundtrip_still_skips_its_example_row():
    """通用裸模板（staff）导出→原样导入：示例行仍被跳过，不产生数据行。"""
    content = generate_template(ImportType.staff)
    stats: dict = {}
    rows = parse_import_data(ImportType.staff, content, stats=stats)

    assert stats["example_skipped"] == 1
    assert rows == []
