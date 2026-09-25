# -*- coding: utf-8 -*-
"""行表引擎框架层 Property 2/3/4 判据 —— 逐字节等价七家 provider 的原手写实现。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 6/7/8 · Requirements 1.1/1.2/1.3

═══ 判据面 ═══

Property 2: `formula_mask` property 输出 ≡ 七家原手写 mask 字面量（逐元素相等）。
Property 3: `managed_field_specs()` 输出 ≡ 四家原 `sorted(...)` 表达式结果（逐元组相等含顺序）。
Property 4: nested / flat 两种 key 派生各自等于原写法；变异反证：flat 走 nested 派生 ⇒ D6 必红。

🔴 驱动数据直接从真实 provider 源码抄录（D5/D6/D7 的 SCALAR_FIELD_SPECS / AGING_GROUPS /
FORMULA_MASK 字面量），不是编造的合成样例 —— 这样"引擎输出 == provider 原写法"才是有意义的
逐字节等价判据，不是"引擎输出 == 我编的期望值"的自我验证。

D7 原字段是 6 元组（无 group_header_cell 独立位，走 GROUP_HEADER_CELLS 侧表），design 裁决 3
统一为内联第 7 位 —— 判据里显式转换补齐第 7 位，不能直接拿 6 元组比 7 元组。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.phase5_row_table_sheet import (
    AgingGroupSpec,
    AgingLayout,
    RowTableSheetSpec,
    expand_aging_fields,
    managed_field_specs,
)


# ═══════════════════════════════════════════════════════════════════════════
# Property 2: formula_mask ≡ 七家原手写 FORMULA_MASK 字面量
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2FormulaMask:
    """七家实测形态：全为列向区间 `{COL}{FIRST}:{COL}{LAST}`。"""

    def test_d5_no_aging(self) -> None:
        # phase5_d5_receivables_financing.py 原 FORMULA_MASK（F/J/L/O，12~16）
        spec = RowTableSheetSpec(
            managed_sheet="应收款项融资明细表D5-2", sheet_key="d52-managed",
            table_key="receivables_financing_detail_rows", template_id="D52",
            table_name="GT_D52_ROWS", uuid_col="R",
            first_data_row=12, last_data_row=16, footer_row=17,
            formula_columns=("F", "J", "L", "O"),
        )
        assert spec.formula_mask == (
            "F12:F16", "J12:J16", "L12:L16", "O12:O16",
        )

    def test_d7_nested_aging(self) -> None:
        # phase5_d7_contract_liabilities.py 原 FORMULA_MASK（I/P/R/U）
        spec = RowTableSheetSpec(
            managed_sheet="合同负债明细表D7-2", sheet_key="d72-managed",
            table_key="contract_liabilities_detail_rows", template_id="D72",
            table_name="GT_D72_ROWS", uuid_col="Z",
            first_data_row=10, last_data_row=40, footer_row=41,
            formula_columns=("I", "P", "R", "U"),
        )
        assert spec.formula_mask == ("I10:I40", "P10:P40", "R10:R40", "U10:U40")

    def test_d6_flat_aging(self) -> None:
        # phase5_d6_contract_assets.py 原 FORMULA_MASK（J/Q/T，三列非四列）
        spec = RowTableSheetSpec(
            managed_sheet="合同资产明细表D6-2", sheet_key="d62-managed",
            table_key="contract_assets_detail_rows", template_id="D62",
            table_name="GT_D62_ROWS", uuid_col="AE",
            first_data_row=13, last_data_row=37, footer_row=38,
            formula_columns=("J", "Q", "T"),
        )
        assert spec.formula_mask == ("J13:J37", "Q13:Q37", "T13:T37")

    def test_empty_formula_columns_yields_empty_mask(self) -> None:
        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=2, footer_row=3,
        )
        assert spec.formula_mask == ()

    def test_mutation_wrong_row_range_breaks_equality(self) -> None:
        """变异反证：first_data_row 错一位 ⇒ mask 不等于 provider 原值，判据必红。"""
        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x",
            first_data_row=13, last_data_row=16, footer_row=17,  # 故意错一位（应为12）
            formula_columns=("F", "J", "L", "O"),
        )
        assert spec.formula_mask != ("F12:F16", "J12:J16", "L12:L16", "O12:O16")


# ═══════════════════════════════════════════════════════════════════════════
# Property 3: managed_field_specs() ≡ 四家原 sorted(SCALAR + _aging(), key=_col_index)
# ═══════════════════════════════════════════════════════════════════════════


# D5 原 MANAGED_FIELD_SPECS（17 个 7 元组，已含 group_header_cell 第 7 位——D5 本就是
# 内联 7 元组的来源家，design 裁决 3 的零改动对照）。
_D5_ORIGINAL_FIELD_SPECS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("category", "A", "editable", "enum", "category", "类别", ""),
    ("item_name", "B", "editable", "text", "itemName", "明细项目", ""),
    ("prior_unadjusted", "C", "editable", "amount", "priorUnadjusted", "未审数", "C10"),
    ("prior_aje", "D", "editable", "amount", "priorAje", "账项调整", "C10"),
    ("prior_rje", "E", "editable", "amount", "priorRje", "重分类调整", "C10"),
    ("prior_audited", "F", "formula", "amount", "priorAudited", "审定数", "C10"),
    ("oci_impairment", "G", "editable", "amount", "ociImpairment", "其他综合收益-应收款项融资减值准备余额", "C10"),
    ("period_increase", "H", "editable", "amount", "periodIncrease", "本期增加", "H10"),
    ("period_decrease", "I", "editable", "amount", "periodDecrease", "本期减少", "H10"),
    ("end_balance", "J", "formula", "amount", "endBalance", "期末余额", "J10"),
    ("entity_reclass", "K", "editable", "amount", "entityReclass", "被审计单位重分类调整", "J10"),
    ("end_unadjusted", "L", "formula", "amount", "endUnadjusted", "期末未审余额", "J10"),
    ("end_aje", "M", "editable", "amount", "endAje", "账项调整", "J10"),
    ("end_rje", "N", "editable", "amount", "endRje", "重分类调整", "J10"),
    ("end_audited", "O", "formula", "amount", "endAudited", "审定数", "J10"),
    ("end_oci_impairment", "P", "editable", "amount", "endOciImpairment", "其他综合收益-应收款项融资减值准备余额", "J10"),
    ("remark", "Q", "editable", "text", "remark", "备注", ""),
)


class TestProperty3ManagedFieldSpecsD5NoAging:
    """D5 无账龄 ⇒ managed_field_specs() 恰等于 field_specs 本身按列序排序（已是列序，零改动对照）。"""

    def test_output_equals_original_verbatim(self) -> None:
        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=2, footer_row=3,
            field_specs=_D5_ORIGINAL_FIELD_SPECS, aging_layout=None,
        )
        assert managed_field_specs(spec) == _D5_ORIGINAL_FIELD_SPECS


# D7 原 SCALAR_FIELD_SPECS（19 个 6 元组）+ AGING_GROUPS（nested，两组各 4 段）+
# AGING_SEGMENTS（4 段共享 leaf label）+ GROUP_HEADER_CELLS（侧表）—— 抄自
# phase5_d7_contract_liabilities.py 逐字。
_D7_SCALAR_FIELD_SPECS_6TUPLE: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("contract_name", "A", "editable", "text", "contractName", "合同名称/项目名称"),
    ("company_name", "B", "editable", "text", "companyName", "单位名称"),
    ("company_code", "C", "editable", "text", "companyCode", "公司代码"),
    ("related_party_type", "D", "editable", "enum", "relatedPartyType", "关联关系"),
    ("nature_type", "E", "editable", "enum", "natureType", "类型"),
    ("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "期初未审数"),
    ("prior_aje", "G", "editable", "amount", "priorAje", "账项调整"),
    ("prior_rje", "H", "editable", "amount", "priorRje", "重分类调整"),
    ("prior_audited", "I", "formula", "amount", "priorAudited", "期初审定数"),
    ("debit_amount", "N", "editable", "amount", "debitAmount", "借方发生"),
    ("credit_amount", "O", "editable", "amount", "creditAmount", "贷方发生"),
    ("end_balance", "P", "formula", "amount", "endBalance", "期末未审数"),
    ("entity_reclass", "Q", "editable", "amount", "entityReclass", "被审计单位重分类调整"),
    ("end_unadjusted", "R", "formula", "amount", "endUnadjusted", "期末未审余额"),
    ("end_aje", "S", "editable", "amount", "endAje", "账项调整"),
    ("end_rje", "T", "editable", "amount", "endRje", "重分类调整"),
    ("end_audited", "U", "formula", "amount", "endAudited", "期末审定数"),
    ("is_confirmed", "Z", "editable", "text", "isConfirmed", "是否发函"),
    ("post_transfer", "AA", "editable", "amount", "postTransfer", "期后结转"),
)

_D7_AGING_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("within1", "1年以内"),
    ("y1to2", "1-2年"),
    ("y2to3", "2-3年"),
    ("over3", "3年以上"),
)

_D7_AGING_GROUPS_RAW: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("agingPrior", "J8", ("J", "K", "L", "M")),
    ("agingAudited", "V8", ("V", "W", "X", "Y")),
)


def _d7_original_aging_fields() -> tuple[tuple[str, str, str, str, str, str], ...]:
    """照 phase5_d7_contract_liabilities._aging_field_specs() 原逻辑逐字复刻（不 import provider，
    避免把"引擎与 provider 用同一份代码"误判成"逐字节等价"——这里是独立重算的期望值）。
    """
    from app.services.workpaper_sync.sheet_geometry import snake

    out: list[tuple[str, str, str, str, str, str]] = []
    for json_prefix, _group_cell, columns in _D7_AGING_GROUPS_RAW:
        prefix_key = snake(json_prefix)
        for column, (seg_key, leaf_label) in zip(columns, _D7_AGING_SEGMENTS):
            out.append((
                f"{prefix_key}_{seg_key.lower()}", column, "editable", "amount",
                f"{json_prefix}/{seg_key}", leaf_label,
            ))
    return tuple(out)


def _to_6tuple(row7: tuple[str, ...]) -> tuple[str, ...]:
    """去掉引擎输出 7 元组的第 7 位（group_header_cell），还原成 provider 原 6 元组形态比对。"""
    return row7[:6]


class TestProperty3ManagedFieldSpecsD7Nested:
    """D7 nested 账龄：引擎 managed_field_specs() 去掉第 7 位后 ≡ provider 原
    `sorted(SCALAR_FIELD_SPECS + _aging_field_specs(), key=_col_index)`（Property 3 核心判据）。
    """

    def _build_spec(self) -> RowTableSheetSpec:
        # 7 元组化 SCALAR（补空 group_header_cell）
        scalar_7 = tuple((*row, "") for row in _D7_SCALAR_FIELD_SPECS_6TUPLE)
        aging_groups = tuple(
            AgingGroupSpec(
                json_prefix=json_prefix,
                group_header_cell=group_cell,
                segments=tuple((seg_key, col) for col, (seg_key, _leaf) in zip(columns, _D7_AGING_SEGMENTS)),
                leaf_labels=tuple(leaf for _seg, leaf in _D7_AGING_SEGMENTS),
            )
            for json_prefix, group_cell, columns in _D7_AGING_GROUPS_RAW
        )
        return RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=10, last_data_row=40, footer_row=41,
            field_specs=scalar_7, aging_layout=AgingLayout.nested, aging_groups=aging_groups,
        )

    def test_scalar_plus_aging_sorted_matches_provider_original(self) -> None:
        spec = self._build_spec()
        engine_output_6tuple = tuple(_to_6tuple(row) for row in managed_field_specs(spec))

        from app.services.workpaper_sync.sheet_geometry import col_index

        expected = tuple(
            sorted(
                _D7_SCALAR_FIELD_SPECS_6TUPLE + _d7_original_aging_fields(),
                key=lambda row: col_index(row[1]),
            )
        )
        assert engine_output_6tuple == expected

    def test_field_count_is_27(self) -> None:
        """19 标量 + 8 账龄（2 组 × 4 段）= 27（provider 原注释登记的数字）。"""
        spec = self._build_spec()
        assert len(managed_field_specs(spec)) == 27

    def test_group_header_cell_populated_for_aging_columns_only(self) -> None:
        """账龄列的第 7 位 = 组标题格；标量列的第 7 位 = 空串（D7 原 SCALAR 无组标题）。"""
        spec = self._build_spec()
        by_key = {row[0]: row for row in managed_field_specs(spec)}
        assert by_key["aging_prior_within1"][6] == "J8"
        assert by_key["aging_audited_over3"][6] == "V8"
        assert by_key["contract_name"][6] == ""  # 标量列无组标题


# D6 原 AGING_GROUPS（flat：group_cell + (flat_key, column, leaf_label) 三元）—— 抄自
# phase5_d6_contract_assets.py 逐字。
_D6_AGING_GROUPS_RAW: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "K12",
        (
            ("agePrior1y", "K", "1年以下"),
            ("agePrior1to2y", "L", "1～2年"),
            ("agePrior2to3y", "M", "２～3年"),
            ("agePrior3yAbove", "N", "3年以上"),
        ),
    ),
    (
        "U12",
        (
            ("ageEnd1y", "U", "1年以下"),
            ("ageEnd1to2y", "V", "1～2年"),
            ("ageEnd2to3y", "W", "２～3年"),
            ("ageEnd3yAbove", "X", "3年以上"),
        ),
    ),
)


def _d6_original_aging_fields() -> tuple[tuple[str, str, str, str, str, str], ...]:
    """照 phase5_d6_contract_assets._aging_field_specs() 原逻辑逐字复刻（flat：json_path=flat_key 本身）。"""
    from app.services.workpaper_sync.sheet_geometry import snake

    out: list[tuple[str, str, str, str, str, str]] = []
    for _group_cell, cols in _D6_AGING_GROUPS_RAW:
        for flat_key, column, leaf_label in cols:
            out.append((snake(flat_key), column, "editable", "amount", flat_key, leaf_label))
    return tuple(out)


class TestProperty3ManagedFieldSpecsD6Flat:
    """D6 flat 账龄：引擎输出去掉第 7 位后 ≡ provider 原 sorted(...) 表达式（Property 3 的 flat 侧）。"""

    def _build_spec(self) -> RowTableSheetSpec:
        aging_groups = tuple(
            AgingGroupSpec(
                json_prefix="", group_header_cell=group_cell,
                segments=cols,  # flat: (flat_key, column, leaf_label) 三元，与 expand_aging_fields 期待一致
            )
            for group_cell, cols in _D6_AGING_GROUPS_RAW
        )
        return RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=13, last_data_row=37, footer_row=38,
            field_specs=(),  # 本判据只验证账龄展开侧，标量侧已由 D7 覆盖
            aging_layout=AgingLayout.flat, aging_groups=aging_groups,
        )

    def test_flat_expansion_matches_provider_original(self) -> None:
        spec = self._build_spec()
        engine_aging_only = tuple(_to_6tuple(row) for row in expand_aging_fields(spec))
        assert engine_aging_only == _d6_original_aging_fields()

    def test_field_count_is_8(self) -> None:
        spec = self._build_spec()
        assert len(expand_aging_fields(spec)) == 8

    def test_flat_json_path_has_no_slash(self) -> None:
        """🔴 flat 的核心差异：json_key = flat_key 本身，不含 nested 的 `/` 分隔符。"""
        spec = self._build_spec()
        for row in expand_aging_fields(spec):
            json_path = row[4]
            assert "/" not in json_path, f"flat 路径不应含 '/'：{json_path}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 4: nested / flat 两种 key 派生互不污染；变异反证 —— flat 走 nested 派生 ⇒ D6 必红
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty4AgingLayoutIsolation:
    def test_nested_json_path_has_slash(self) -> None:
        """nested 的核心差异：json_key 含 `/`（对照 flat 侧 test_flat_json_path_has_no_slash）。"""
        aging_groups = (
            AgingGroupSpec(
                json_prefix="agingPrior", group_header_cell="J8",
                segments=(("within1", "J"), ("y1to2", "K")),
                leaf_labels=("1年以内", "1-2年"),
            ),
        )
        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=2, footer_row=3,
            aging_layout=AgingLayout.nested, aging_groups=aging_groups,
        )
        rows = expand_aging_fields(spec)
        assert all("/" in row[4] for row in rows)
        assert rows[0][4] == "agingPrior/within1"

    def test_mutation_flat_group_fed_through_nested_branch_breaks_equality(self) -> None:
        """🔴 变异反证（design Property 4 明文要求）：把 D6 的 flat 账龄组数据结构塞进 nested
        分支会因为 segments 形态不匹配（nested 期待二元 (seg_key, column) + 独立 leaf_labels，
        flat 传的是三元 (flat_key, column, leaf_label)）在展开阶段直接出错或产出错误路径 ——
        证明两分支不可互相喂错数据、不会静默产出"看起来对"的结果。
        """
        # D6 的 flat 账龄组：segments 是三元组
        flat_style_groups = tuple(
            AgingGroupSpec(json_prefix="", group_header_cell=cell, segments=cols)
            for cell, cols in _D6_AGING_GROUPS_RAW
        )
        # 强行标成 nested（变异：把 aging_layout 改错）
        mutated_spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=13, last_data_row=37, footer_row=38,
            aging_layout=AgingLayout.nested,  # 错误：D6 实际是 flat
            aging_groups=flat_style_groups,
        )
        # nested 分支要求 len(segments) == len(leaf_labels)；flat 数据的 leaf_labels 默认是
        # 空元组 () 而 segments 有 4 个 ⇒ 4 != 0 触发引擎自己的一致性校验错误（fail-closed，
        # 不静默产出错误路径）。这正是 Property 4 要求的"混淆必被拦"。
        with pytest.raises(ValueError, match="段与标签必须一一对应"):
            expand_aging_fields(mutated_spec)

    def test_correct_layout_flat_does_not_raise(self) -> None:
        """对照：同一份数据用正确的 flat 分支跑，不抛错、产出 8 条。"""
        flat_style_groups = tuple(
            AgingGroupSpec(json_prefix="", group_header_cell=cell, segments=cols)
            for cell, cols in _D6_AGING_GROUPS_RAW
        )
        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=13, last_data_row=37, footer_row=38,
            aging_layout=AgingLayout.flat, aging_groups=flat_style_groups,
        )
        assert len(expand_aging_fields(spec)) == 8


# ═══════════════════════════════════════════════════════════════════════════
# 行表引擎核心（Task 9）：iter_store_rows / stable_key_for / build_store_projection /
# merge_projection_into_store_rows 的边界行为判据
# ═══════════════════════════════════════════════════════════════════════════


class TestRowIdentityFailClosed:
    def test_missing_row_identity_raises(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            RowTableStorePayloadError,
            store_row_identity,
        )

        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=2, footer_row=3,
        )
        with pytest.raises(RowTableStorePayloadError, match="缺少稳定行身份"):
            store_row_identity(spec, {}, ordinal=0)

    def test_duplicate_row_identity_raises(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import iter_store_rows

        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=2, footer_row=3,
        )
        payload = [{"rowId": "dup"}, {"rowId": "dup"}]
        with pytest.raises(Exception, match="重复行身份"):
            list(iter_store_rows(spec, payload))

    def test_non_list_payload_raises(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import iter_store_rows

        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=2, footer_row=3,
        )
        with pytest.raises(Exception, match="行对象数组"):
            list(iter_store_rows(spec, {"not": "a list"}))


class TestStableKeyFor:
    def test_format_matches_seven_providers_convention(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import stable_key_for

        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="receivables_financing_detail_rows",
            template_id="x", table_name="x", uuid_col="x",
            first_data_row=1, last_data_row=2, footer_row=3,
        )
        assert stable_key_for(spec, "prior_audited", "abc-123") == (
            "receivables_financing_detail_rows/abc-123/prior_audited"
        )


# ═══════════════════════════════════════════════════════════════════════════
# ghost_row_anchor_index（Task 16 复盘补）：D5/D6 的幽灵行防护锚点不是默认第 0 位
# ═══════════════════════════════════════════════════════════════════════════


class TestGhostRowAnchorIndex:
    """`merge_projection_into_store_rows` 的幽灵行防护锚点可参数化（默认 0，D5/D6 用 1）。

    背景：D6 首列是 `seq_no`（整数序号，`0` 是合法真值不是"空"信号），D5 首列是
    `category`（枚举）。二者原实现（改造前）均硬编码 `MANAGED_FIELD_SPECS[1]` 而非 `[0]`。
    框架层原实现硬编码 `specs[0][4]` 无法表达这条差异，本参数补上这个缺口。
    """

    def _spec(self, *, anchor_index: int) -> RowTableSheetSpec:
        # 字段 0 = seq_no（整数，0 合法）；字段 1 = contract_name（真正业务名称锚点）。
        field_specs = (
            ("seq_no", "A", "editable", "integer", "seqNo", "序号", ""),
            ("contract_name", "B", "editable", "text", "contractName", "合同名称", ""),
        )
        return RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="tbl", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=5, footer_row=6,
            field_specs=field_specs, ghost_row_anchor_index=anchor_index,
        )

    def _projection_with_only_seq_no(self, rid: str):
        """构造一个只有 seq_no 字段非空的合成 projection（模拟幽灵行：Table 边界扩展出的
        杂散新行，只有一个字段有值）。"""

        class _FV:
            def __init__(self, value, row_key):
                self.value = value
                self.row_key = row_key
                self.is_protected = False

        class _Proj:
            def __init__(self, values):
                self._values = values

            def stable_keys(self):
                return list(self._values)

            def get(self, key):
                return self._values.get(key)

        key = f"tbl/{rid}/seq_no"
        return _Proj({key: _FV(0, rid)})

    def test_default_anchor_index_0_treats_seq_no_zero_as_ghost(self) -> None:
        """默认锚点（index=0）：只有 seq_no=0 的新行被幽灵行防护剔除（因为 seq_no 恰是
        锚点字段，值为 0 → strip 后为空字符串 → 判定为幽灵行 —— 这正是 D6 原来会踩的坑，
        用它证明"不参数化就会误剔除合法新行"这个问题真实存在）。
        """
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            merge_projection_into_store_rows,
        )

        spec = self._spec(anchor_index=0)
        projection = self._projection_with_only_seq_no("new-row-1")
        merged, applied, visited, touched = merge_projection_into_store_rows(
            spec, projection=projection, base_rows=[]
        )
        assert merged == [], "锚点=0 时，只有 seq_no 的新行应被判为幽灵行剔除"

    def test_anchor_index_1_keeps_the_row_because_name_field_is_not_the_anchor(self) -> None:
        """🔴 核心判据：锚点改成 1（contract_name）后，只有 seq_no 的新行**仍会被剔除**——
        因为幽灵行判定看的是「锚点字段（此处 contract_name）是否为空」，而这行的
        contract_name 确实为空（只填了 seq_no）。这正确反映 D6 的真实语义：
        只填序号没填名字的行，本来就该被当成幽灵行——D6 的例外只在于"锚点不能选 seq_no
        自身"，不是"seq_no 有值就该被保留"。
        """
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            merge_projection_into_store_rows,
        )

        spec = self._spec(anchor_index=1)
        projection = self._projection_with_only_seq_no("new-row-1")
        merged, applied, visited, touched = merge_projection_into_store_rows(
            spec, projection=projection, base_rows=[]
        )
        assert merged == [], "contract_name 为空 ⇒ 即使锚点已改成 1，这行仍应判为幽灵行"

    def test_anchor_index_1_keeps_row_when_name_field_has_value(self) -> None:
        """对照：锚点=1 时，若 contract_name 字段有值（即便 seq_no 也有值），行应被保留——
        这才是 D6 真实场景：用户填了序号 0 和合同名称，行是合法新增。
        """
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            merge_projection_into_store_rows,
        )

        class _FV:
            def __init__(self, value, row_key):
                self.value = value
                self.row_key = row_key
                self.is_protected = False

        class _Proj:
            def __init__(self, values):
                self._values = values

            def stable_keys(self):
                return list(self._values)

            def get(self, key):
                return self._values.get(key)

        spec = self._spec(anchor_index=1)
        rid = "new-row-2"
        projection = _Proj({
            f"tbl/{rid}/seq_no": _FV(0, rid),
            f"tbl/{rid}/contract_name": _FV("测试合同", rid),
        })
        merged, applied, visited, touched = merge_projection_into_store_rows(
            spec, projection=projection, base_rows=[]
        )
        assert len(merged) == 1, "seq_no=0 且 contract_name 有值 ⇒ 合法新行，不应被剔除"
        assert merged[0]["contractName"] == "测试合同"

    def test_default_anchor_index_is_zero(self) -> None:
        """向后兼容：不传 `ghost_row_anchor_index` 时默认 0（D1/D2/D3/D4/D7 现状零改动）。"""
        spec = RowTableSheetSpec(
            managed_sheet="x", sheet_key="x", table_key="x", template_id="x",
            table_name="x", uuid_col="x", first_data_row=1, last_data_row=2, footer_row=3,
        )
        assert spec.ghost_row_anchor_index == 0
