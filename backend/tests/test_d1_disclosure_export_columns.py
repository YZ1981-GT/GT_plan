"""D1 披露导入导出列契约 + 往返自检。

背景（2026-07-30 实测）：导出模板的列名与界面、附注模板三方不一致 ——
`终止确认金额`（界面已是 `期末终止确认金额`）、`预期信用损失率（%）` 用全角括号
（附注模板与同步载荷都是半角）、上市核销第 2 列 `应收票据`（预设 F4-29 是 `应收票据性质`）；
且完全没覆盖「组合计提项目」明细与国企「转回或收回前累计已计提坏账准备金额」。

本守卫锁三件事：

1. **往返自检**：自家导出的模板必须能通过自家 `_validate_columns`（防表头与列定义漂移）
2. **列名单一真源**：直接读 `d1NoteSectionMap.ts` 源码，确认导出列名用的是同一套措辞
3. **覆盖面**：本轮新增的录入面（组合计提明细 / 国企其中明细 / 国企累计已计提列）都有区块

spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ R12.3
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.routers.wp_render_strategies._d1_disclosure_export import (
    SHEET_TITLES,
    TITLE_TO_SECTION,
    VARIANT_SECTIONS,
    _cols,
    _create_template_workbook,
    _multi_header,
    _validate_columns,
)

_REPO = Path(__file__).resolve().parent.parent.parent
_SECTION_MAP_TS = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
    / "composables" / "d1NoteSectionMap.ts"
)

VARIANTS = ["listed", "soe"]


# ─── 往返自检 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_exported_template_passes_own_validation(variant: str) -> None:
    """导出模板 → 立刻用导入校验器验一遍，必须零错误。"""
    wb = _create_template_workbook(variant)
    failures: list[str] = []
    for section in VARIANT_SECTIONS[variant]:
        title = SHEET_TITLES[section]
        assert title in wb.sheetnames, f"{variant} 缺 sheet「{title}」"
        invalid = _validate_columns(wb[title], section, variant)
        if invalid:
            failures.append(f"{section}({title}): {invalid}")
    assert failures == [], failures


@pytest.mark.parametrize("variant", VARIANTS)
def test_multi_header_row2_equals_columns(variant: str) -> None:
    """多层表头的第 2 行必须**等于**列定义（row2 由 `_cols` 派生，不得再手写）。"""
    for section in VARIANT_SECTIONS[variant]:
        mh = _multi_header(section, variant)
        if not mh:
            continue
        assert mh["row2"] == _cols(section, variant), f"{variant}/{section} row2 与列定义不一致"
        assert len(mh["row1"]) == len(mh["row2"]), f"{variant}/{section} row1 与 row2 列数不等"


def test_sheet_titles_unique_and_reversible() -> None:
    assert len(set(SHEET_TITLES.values())) == len(SHEET_TITLES), "sheet 标题重复 → 导入时区块互相覆盖"
    for section, title in SHEET_TITLES.items():
        assert TITLE_TO_SECTION[title] == section


# ─── 列名单一真源（读前端 .ts 源码）───────────────────────────────────────────

def _ts_source() -> str:
    if not _SECTION_MAP_TS.exists():
        pytest.skip(f"前端真源缺失：{_SECTION_MAP_TS}")
    return _SECTION_MAP_TS.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "label",
    [
        "期末终止确认金额",
        "期末未终止确认金额",
        "期末转应收账款金额",
        "期末已质押金额",
        "预期信用损失率(%)",
        "应收票据性质",
        "应收票据的性质",
        "是否由关联交易产生",
        "款项是否由关联交易产生",
        "原确定坏账准备的依据",
        "转回或收回前累计已计提坏账准备金额",
        "转回或收回原因、方式",
        "计提依据",
        "计提理由",
    ],
)
def test_export_label_exists_in_frontend_truth(label: str) -> None:
    """导出用到的列名措辞必须在前端列头真源里出现（防后端自造措辞）。"""
    assert label in _ts_source(), f"「{label}」未出现在 d1NoteSectionMap.ts → 后端自造措辞"


def test_no_fullwidth_paren_in_rate_columns() -> None:
    """🔴 附注模板与同步载荷用半角 `(%)`；导出用全角会让三方不一致。"""
    offenders = []
    for variant in VARIANTS:
        for section in VARIANT_SECTIONS[variant]:
            for c in _cols(section, variant):
                if "损失率" in c and "（" in c:
                    offenders.append(f"{variant}/{section}: {c}")
    assert offenders == [], offenders


def test_no_legacy_bill_kind_column() -> None:
    """质押 / 背书 / 转应收三表首列是「种类」（源模板与附注模板均然），不是「票据种类」。"""
    for variant in VARIANTS:
        for section in ("pledged", "endorsed", "transfer"):
            assert _cols(section, variant)[0] == "种类", f"{variant}/{section} 首列应为「种类」"


# ─── 覆盖面 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", VARIANTS)
def test_portfolio_sections_present(variant: str) -> None:
    """组合计提项目明细必须有导入导出区块（本轮新增的录入面）。"""
    sections = VARIANT_SECTIONS[variant]
    assert "portfolioBank" in sections
    assert "portfolioCommercial" in sections
    cols = _cols("portfolioBank", variant)
    assert cols[0] == "名称"
    assert "期末应收票据" in cols and "期末坏账准备" in cols
    if variant == "listed":
        # 上市源模板是一张表双期并列
        assert "上年年末应收票据" in cols and "上年年末坏账准备" in cols
    else:
        # 国企源模板只有期末
        assert "上年年末应收票据" not in cols


def test_soe_movement_detail_section_present() -> None:
    """国企变动表「其中：」明细（F4-20）必须可导入导出。"""
    assert "movementDetail" in VARIANT_SECTIONS["soe"]
    assert _cols("movementDetail", "soe") == ["类别", "期初数", "计提", "收回或转回", "核销", "其他变动"]
    # 上市变动表是竖排单列，无「其中：」明细
    assert "movementDetail" not in VARIANT_SECTIONS["listed"]


def test_soe_movement_main_is_wide_shape() -> None:
    """国企变动主表是横排 7 列（源模板 A46:G47），不是上市的竖排 2 列。"""
    assert _cols("badDebtMovementMain", "soe") == [
        "类别", "期初数", "计提", "收回或转回", "核销", "其他变动", "期末数",
    ]
    assert _cols("badDebtMovementMain", "listed") == ["项目", "坏账准备金额"]


def test_soe_reversal_has_cumulative_provision_column() -> None:
    cols = _cols("badDebtMovementDetail", "soe")
    assert cols == [
        "债务人名称", "转回或收回金额", "转回或收回前累计已计提坏账准备金额", "转回或收回原因、方式",
    ]


# ─── 数据往返（导出数据 → 解析回来，值不丢）────────────────────────────────

from app.routers.wp_render_strategies._d1_disclosure_export import (  # noqa: E402
    _fill_template_with_data,
    _parse_rows,
    _portfolio_import_rows,
)


def _response_map(variant: str) -> dict[str, str]:
    """构造一份最小但覆盖新增录入面的 checklist_responses 快照。"""
    import json

    p = f"D1-disc-{variant}-"
    return {
        p + "pledged-rows": json.dumps([
            {"category": "银行承兑票据", "pledgedAmount": 80000},
        ], ensure_ascii=False),
        p + "transfer-rows": json.dumps([
            {"category": "商业承兑票据", "transferAmount": 12000},
        ], ensure_ascii=False),
        p + "bank-portfolio-end-rows": json.dumps([
            {"drawerTypeOrAging": "1年以内（含1年）", "balance": 500000, "provision": 4000},
        ], ensure_ascii=False),
        p + "bank-portfolio-prior-rows": json.dumps([
            {"drawerTypeOrAging": "1年以内（含1年）", "balance": 400000, "provision": 3000},
        ], ensure_ascii=False),
        p + "movement-detail-rows": json.dumps([
            {"label": "银行承兑汇票", "priorBalance": 100, "provision": 50,
             "reversal": 10, "writeOff": 5, "transfer": 0, "other": 0, "endBalance": 135},
        ], ensure_ascii=False),
        p + "reversal-rows": json.dumps([
            {"companyName": "A公司", "reversalReason": "客户回款", "originalMethod": "银行转账",
             "reversalBasis": "单项评估", "cumulativeProvision": 12, "amount": 100},
        ], ensure_ascii=False),
    }


@pytest.mark.parametrize("variant", VARIANTS)
def test_portfolio_roundtrip_keeps_values(variant: str) -> None:
    """组合计提明细：导出数据 → 解析回来，名称与金额不丢。"""
    wb = _create_template_workbook(variant)
    _fill_template_with_data(wb, variant, _response_map(variant))
    ws = wb[SHEET_TITLES["portfolioBank"]]
    assert _validate_columns(ws, "portfolioBank", variant) == []
    rows, _ = _parse_rows(ws, "portfolioBank", variant)
    assert rows, "组合计提明细导出后解析为空"
    back = _portfolio_import_rows(rows, "end")
    assert len(back) == 1
    assert back[0]["drawerTypeOrAging"] == "1年以内（含1年）"
    assert back[0]["balance"] == 500000
    assert back[0]["provision"] == 4000
    # 损失率读时推导（不依赖导出列）
    assert abs(back[0]["lossRate"] - 4000 / 500000) < 1e-9
    if variant == "listed":
        prior = _portfolio_import_rows(rows, "prior")
        assert prior[0]["balance"] == 400000 and prior[0]["provision"] == 3000


def test_soe_movement_detail_roundtrip() -> None:
    wb = _create_template_workbook("soe")
    _fill_template_with_data(wb, "soe", _response_map("soe"))
    ws = wb[SHEET_TITLES["movementDetail"]]
    assert _validate_columns(ws, "movementDetail", "soe") == []
    rows, _ = _parse_rows(ws, "movementDetail", "soe")
    assert rows and str(rows[0]["类别"]) == "银行承兑汇票"
    assert rows[0]["计提"] == 50


def test_soe_reversal_cumulative_provision_roundtrip() -> None:
    wb = _create_template_workbook("soe")
    _fill_template_with_data(wb, "soe", _response_map("soe"))
    ws = wb[SHEET_TITLES["badDebtMovementDetail"]]
    assert _validate_columns(ws, "badDebtMovementDetail", "soe") == []
    rows, _ = _parse_rows(ws, "badDebtMovementDetail", "soe")
    assert rows[0]["债务人名称"] == "A公司"
    assert rows[0]["转回或收回前累计已计提坏账准备金额"] == 12
    assert rows[0]["转回或收回原因、方式"] == "客户回款"


@pytest.mark.parametrize("variant", VARIANTS)
def test_pledged_transfer_roundtrip_uses_new_labels(variant: str) -> None:
    wb = _create_template_workbook(variant)
    _fill_template_with_data(wb, variant, _response_map(variant))
    for section, first_col_value, amount_col, amount in (
        ("pledged", "银行承兑票据", "期末已质押金额", 80000),
        ("transfer", "商业承兑票据", "期末转应收账款金额", 12000),
    ):
        ws = wb[SHEET_TITLES[section]]
        assert _validate_columns(ws, section, variant) == []
        rows, _ = _parse_rows(ws, section, variant)
        assert rows[0]["种类"] == first_col_value
        assert rows[0][amount_col] == amount
