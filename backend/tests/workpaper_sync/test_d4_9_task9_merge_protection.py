# -*- coding: utf-8 -*-
"""D4-9 Task 9 守卫（bridge↔引擎）：真 merge 引擎分类器验证保护策略。

spec: d4-9-customer-structure-bidirectional-writeback / Task 9
Requirements: 5.3, 5.6, 4.1

═══ 这个守卫为什么存在（关闭 bridge↔engine 缺口）═══

`test_d4_9_task9_formula_protection.py` 只验证 bridge **自己**算出的 standalone 保护集
（`contract_protected_cells` / `runtime_protected_cells` / `is_cell_protected`）。它从不证明
D4-9 的契约喂进**真实 merge 引擎的分类器**（`merge.ContractIndex._protection`，经
`resolve(...).protection_policy` 暴露）时，D/F 占比列与合计会被判为 `read_only_formula`。

本文件把 D4-9 的**真契约**（`assert_contract_file_matches_source()`）喂进真实引擎
`ContractIndex`，通过公开入口 `resolve(stable_key) -> FieldLocator.protection_policy` 读出
每个字段经引擎裁决后的 `ProtectionPolicy`，做**行为级**断言：

* D 列（amount_ratio）/ F 列（quantity_ratio）在本期(R13-22)与上期(R27-36)两区都是
  `read_only_formula`（OO 改它们必产生受保护冲突而非静默覆盖公式）。
* 可编辑业务列（B 客户名 / C 销售金额 / E 销售数量 / G 上期排名）是 `editable`，
  证明 mask 是**列域**保护、不是整表封锁。
* `customer_totals` 静态标量（C24/E24/C38/E38）是 `editable`，证明总额默认可手工编辑
  （除非审计师显式设用户公式，那由运行时保护集承担、不在契约 mask 内）。
* 引擎模板携带的 `formula_mask` 与契约声明的 D/F 双区 mask 逐字一致（交叉锁死）。

**不在测试里重实现分类器** —— 全部经 `ContractIndex(contract).resolve(...)` 调真引擎。

═══ 变异/反向自检 ═══

`TestMutationBindsToEngine` 变异契约 payload 的**副本**（不碰磁盘、不碰入参），把 D 列公式
字段移出 mask（或改 mode），经真 `parse_contract` + `ContractIndex` 重新分类，断言分类**随之
改变**。这证明上面的绿不是重言式：分类真的由契约字节驱动。
"""

from __future__ import annotations

import copy

import pytest

from app.services.workpaper_sync import phase5_d4_customer_structure as M
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.merge import ContractIndex
from app.services.workpaper_sync.conflicts import ProtectionPolicy


# ── 固定行身份：引擎 resolve 需要把 {row_uuid} 实例化 ────────────────────
_RID = "row-8f21c7"


@pytest.fixture(scope="module")
def contract():
    return M.assert_contract_file_matches_source()


@pytest.fixture(scope="module")
def index(contract):
    return ContractIndex(contract)


def _resolve_row(index: ContractIndex, table_key: str, column_key: str) -> ProtectionPolicy:
    """把 bridge 的模板级 stable key 实例化成具体行键，喂真引擎 resolve，取保护策略。"""
    template_key = M.stable_key_for_row(table_key, column_key)
    concrete = template_key.replace("{row_uuid}", _RID)
    locator = index.resolve(concrete, declared_row_key=_RID)
    return locator.protection_policy


def _resolve_total(index: ContractIndex, field_key: str) -> ProtectionPolicy:
    return index.resolve(M.stable_key_for_total(field_key)).protection_policy


class TestRatioColumnsAreReadOnlyFormulaViaEngine:
    """D/F 占比列经真引擎分类 = read_only_formula（本期 + 上期两区）。"""

    @pytest.mark.parametrize("table_key", [M.CUR_TABLE_KEY, M.PRI_TABLE_KEY])
    @pytest.mark.parametrize("column_key", ["amount_ratio", "quantity_ratio"])
    def test_ratio_field_classifies_read_only_formula(
        self, index, table_key, column_key
    ) -> None:
        policy = _resolve_row(index, table_key, column_key)
        assert policy is ProtectionPolicy.read_only_formula, (
            f"{table_key}/{column_key} 经真 merge 引擎分类应为 read_only_formula，实得 {policy.value}"
        )
        # is_protected 是引擎据以在 merge 里拒绝静默覆盖公式的判据。
        assert policy.is_protected is True

    def test_both_regions_cover_D_and_F(self, index) -> None:
        # 逐区、逐列显式确认（D=amount_ratio, F=quantity_ratio），不依赖参数化聚合。
        for table_key in (M.CUR_TABLE_KEY, M.PRI_TABLE_KEY):
            assert _resolve_row(index, table_key, "amount_ratio") is ProtectionPolicy.read_only_formula
            assert _resolve_row(index, table_key, "quantity_ratio") is ProtectionPolicy.read_only_formula


class TestEditableBusinessColumnsNotProtected:
    """B/C/E/G 业务列经真引擎分类 = editable，证明 mask 是列域保护不是整表封锁。"""

    @pytest.mark.parametrize("table_key", [M.CUR_TABLE_KEY, M.PRI_TABLE_KEY])
    @pytest.mark.parametrize(
        "column_key", ["customer_name", "sales_amount", "sales_quantity", "prior_rank"]
    )
    def test_business_field_classifies_editable(self, index, table_key, column_key) -> None:
        policy = _resolve_row(index, table_key, column_key)
        assert policy is ProtectionPolicy.editable, (
            f"{table_key}/{column_key} 是可编辑业务列，经真引擎应为 editable，实得 {policy.value}"
        )
        assert policy.is_protected is False


class TestStaticTotalsAreEditable:
    """customer_totals 静态标量 C24/E24/C38/E38 经真引擎分类 = editable（无 formula_mask）。"""

    @pytest.mark.parametrize(
        "field_key",
        [
            "current_total_amount",
            "current_total_quantity",
            "prior_total_amount",
            "prior_total_quantity",
        ],
    )
    def test_total_scalar_classifies_editable(self, index, field_key) -> None:
        policy = _resolve_total(index, field_key)
        assert policy is ProtectionPolicy.editable, (
            f"customer_totals/{field_key} 默认可手工编辑，经真引擎应为 editable，实得 {policy.value}"
        )
        assert policy.is_protected is False


class TestEngineTemplateMaskMatchesContractDeclaration:
    """引擎内部 _FieldTemplate 携带的 formula_mask 与契约声明的 D/F 双区 mask 逐字一致。"""

    def test_engine_template_carries_declared_mask(self, contract) -> None:
        # 直接读引擎索引里每个模板的 formula_mask（引擎分类第三类 read_only_masked_cell 的输入）。
        idx = ContractIndex(contract)
        by_table: dict[str, set[str]] = {}
        for template in idx._templates:  # noqa: SLF001 — 白盒断言引擎持有的 mask 与契约同源
            if template.table_key is None:
                continue
            by_table.setdefault(template.table_key, set()).update(template.formula_mask)

        cur_expected = set(M._current_formula_mask())  # noqa: SLF001
        pri_expected = set(M._prior_formula_mask())  # noqa: SLF001
        assert by_table.get(M.CUR_TABLE_KEY) == cur_expected, (
            f"本期区引擎 mask {by_table.get(M.CUR_TABLE_KEY)} != 契约声明 {cur_expected}"
        )
        assert by_table.get(M.PRI_TABLE_KEY) == pri_expected, (
            f"上期区引擎 mask {by_table.get(M.PRI_TABLE_KEY)} != 契约声明 {pri_expected}"
        )
        # totals 表无 formula_mask（证明总额未被列域保护）。
        assert by_table.get(M.TOTALS_TABLE_KEY, set()) == set()

    def test_declared_mask_columns_are_exactly_D_and_F(self, contract) -> None:
        # 交叉核对：契约两动态表 mask 的列集恰好 {D, F}（不多不少）。
        for sheet in contract.sheets:
            for table in sheet.tables:
                if table.table_key not in (M.CUR_TABLE_KEY, M.PRI_TABLE_KEY):
                    continue
                cols = {rng[0] for rng in table.formula_mask}
                assert cols == {"D", "F"}, (
                    f"{table.table_key} 的 mask 列集应恰为 {{D,F}}，实得 {sorted(cols)}"
                )


class TestMutationBindsToEngine:
    """反向自检：变异契约副本后，真引擎分类**随之改变** —— 证明绿不是重言式。

    不碰磁盘契约、不碰入参：全部走 build_contract_payload() 的深拷贝 + 真 parse_contract。
    """

    def test_drop_mask_and_flip_mode_makes_D_editable(self) -> None:
        payload = M.build_contract_payload()
        baseline = ContractIndex(parse_contract(payload, adapter_id=M.ADAPTER_ID))
        # 基线：D 列公式字段是 read_only_formula。
        assert (
            _resolve_row(baseline, M.CUR_TABLE_KEY, "amount_ratio")
            is ProtectionPolicy.read_only_formula
        )

        mutated = copy.deepcopy(payload)
        tbl = next(
            t for t in mutated["sheets"][0]["tables"] if t["table_key"] == M.CUR_TABLE_KEY
        )
        # 把 D 列 amount_ratio 从 formula 改成 editable，并把 D 区间移出 formula_mask。
        for field in tbl["fields"]:
            if field["column_key"] == "amount_ratio":
                field["mode"] = "editable"
        tbl["formula_mask"] = [rng for rng in tbl["formula_mask"] if not rng.startswith("D")]

        mutant = ContractIndex(parse_contract(mutated, adapter_id=M.ADAPTER_ID))
        # 变异后 D 列变可编辑（分类随契约字节改变）。
        assert (
            _resolve_row(mutant, M.CUR_TABLE_KEY, "amount_ratio")
            is ProtectionPolicy.editable
        )
        # 未触动的 F 列仍受保护（证明变异是定向的，不是整表塌陷）。
        assert (
            _resolve_row(mutant, M.CUR_TABLE_KEY, "quantity_ratio")
            is ProtectionPolicy.read_only_formula
        )

    def test_adding_business_column_to_mask_makes_it_masked_cell(self) -> None:
        # 另一方向：把可编辑业务列 C 塞进 mask ⇒ 引擎判 read_only_masked_cell（第三类保护）。
        payload = M.build_contract_payload()
        baseline = ContractIndex(parse_contract(payload, adapter_id=M.ADAPTER_ID))
        assert (
            _resolve_row(baseline, M.CUR_TABLE_KEY, "sales_amount")
            is ProtectionPolicy.editable
        )

        mutated = copy.deepcopy(payload)
        tbl = next(
            t for t in mutated["sheets"][0]["tables"] if t["table_key"] == M.CUR_TABLE_KEY
        )
        tbl["formula_mask"] = list(tbl["formula_mask"]) + [
            f"C{M.CUR_FIRST_DATA_ROW}:C{M.CUR_LAST_DATA_ROW}"
        ]

        mutant = ContractIndex(parse_contract(mutated, adapter_id=M.ADAPTER_ID))
        assert (
            _resolve_row(mutant, M.CUR_TABLE_KEY, "sales_amount")
            is ProtectionPolicy.read_only_masked_cell
        )
