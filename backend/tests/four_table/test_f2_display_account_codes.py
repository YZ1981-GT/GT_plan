"""守卫：`F2_CATEGORIES[].account`（展示 / 兜底元数据）声明的码必须真实存在。

**为什么需要**（2026-08-03 实证）

F2 的取数真源是 `classify_f2_leaf`（**按科目名称**归类，因为库内并存两套标准存货
科目表，同一个 `1406` 一半项目是「库存商品」另一半是「发出商品」）。
`account` 字段只作展示 + `build_default_bindings` 的兜底绑定。

但「只是展示」不等于可以写不存在的码：`合同履约成本` 原写 `1410`、
`商品进销差价` 原写 `1412`，两者在 `account_chart` **全库零命中**
（连 `is_deleted = true` 的行都没有）→ 溯源面板显示一个查不到的码、
兜底绑定 `TB('1410', …)` 恒空，属静默错误。

本文件把「码是否存在」冻结成断言：存在性集合来自 postgres 只读对账
（`account_chart`，10 个项目、`client` + `standard` 两个 source 的并集），
**不连库故 CI 可跑**。改 `account` 声明必须同步改这里并附新的实证依据。

🔴 本守卫只查**存在性**，不查「码 ↔ 名是否相符」—— 后者在两套编码体系下无解
（`1401` 在两套体系里都是「材料采购」而不是「原材料」，但它确实存在，
且取数不据此），强行断言名称相符会逼出「按某一变体写死」的错误方向。

spec: semantic-account-resolver-full-rollout（Task 29）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routers.wp_render_strategies._f2_inventory_main import F2_CATEGORIES

#: DB 实证：`account_chart` 里存货区间（`^14\d{2}$`）**实际存在**的一级码
#: （2026-08-03，`is_deleted = false`，`client` ∪ `standard`，10 个项目）。
#: 括注 = 该码在库里的实际科目名（多个 = 项目间不一致，正是「两套编码体系」的表现）。
ACCOUNT_CHART_INVENTORY_CODES: dict[str, tuple[str, ...]] = {
    "1401": ("材料采购",),
    "1402": ("在途物资",),
    "1403": ("原材料",),
    "1404": ("材料成本差异",),
    "1405": ("库存商品", "自制半成品"),
    "1406": ("发出商品", "库存商品"),
    "1407": ("发出商品", "商品进销差价"),
    "1408": ("商品进销差价", "委托加工物资"),
    "1409": ("周转材料",),
    "1411": ("周转材料", "委托加工物资"),
    "1416": ("存货跌价准备",),
    "1421": ("消耗性生物资产",),
    "1431": ("贵金属",),
    "1441": ("抵债资产",),
    "1451": ("包装物", "损余物资"),
    "1452": ("低值易耗品",),
    "1461": ("存货跌价准备",),
    "1471": ("存货跌价准备", "合同取得成本"),
    "1472": ("合同履约成本",),
    "1481": ("持有待售资产",),
    "1482": ("持有待售资产减值准备",),
}

#: 🔴 已修的两个零命中码 —— 全库任何 source、任何项目、含已删行都查不到。
#: 留在这里防「顺手改回去」。
KNOWN_NONEXISTENT_CODES: tuple[str, ...] = ("1410", "1412", "1499")

_STANDARD_CHART_JSON = (
    Path(__file__).resolve().parents[2] / "data" / "standard_account_chart.json"
)


def _committed_inventory_codes() -> set[str]:
    """从仓库内 `standard_account_chart.json` 取存货区间一级码（非自证锚点）。

    该文件是 CAS 2006 变体（一个真实变体，不是全部）→ 只能用来给上面的冻结表
    做**子集**校验，不能当唯一真源（它没有旧变体独有的 `1409`/`1416`/`1452`）。
    """
    data = json.loads(_STANDARD_CHART_JSON.read_text(encoding="utf-8"))
    return {
        a["code"]
        for a in data.get("accounts", [])
        if a.get("level") == 1 and "1401" <= str(a.get("code", "")) <= "1499"
    }


class TestDeclaredAccountCodesExist:
    """Property: `account` 声明的每个码都必须在 `account_chart` 至少一个项目存在。"""

    def test_categories_discovered(self):
        assert len(F2_CATEGORIES) == 13, f"F2-1 分类行应为 13 行，实为 {len(F2_CATEGORIES)}"

    @pytest.mark.parametrize(
        "cat", F2_CATEGORIES, ids=lambda c: f'{c["rowKey"]}@{c["account"]}'
    )
    def test_account_code_exists_in_chart(self, cat):
        code = str(cat["account"])
        assert code in ACCOUNT_CHART_INVENTORY_CODES, (
            f'F2_CATEGORIES["{cat["rowKey"]}"]（{cat["label"]}）声明的码 {code} '
            "在 account_chart 全库零命中 —— 展示元数据也不许写不存在的码"
            "（溯源面板会显示查不到的码、兜底绑定 TB() 恒空）。"
            f"实证存在的存货码：{sorted(ACCOUNT_CHART_INVENTORY_CODES)}"
        )

    @pytest.mark.parametrize("code", KNOWN_NONEXISTENT_CODES)
    def test_known_nonexistent_codes_not_reintroduced(self, code):
        declared = {str(c["account"]) for c in F2_CATEGORIES}
        assert code not in declared, (
            f"{code} 是全库零命中码（2026-08-03 实证），不得重新出现在 F2_CATEGORIES"
        )

    def test_two_fixed_codes_are_the_evidenced_values(self):
        by_key = {c["rowKey"]: str(c["account"]) for c in F2_CATEGORIES}
        assert by_key["contract-performance"] == "1472", (
            "合同履约成本真码 = 1472（standard 6 个项目实证）"
        )
        assert by_key["price-difference"] in ("1407", "1408"), (
            "商品进销差价项目间不一致，只能是 1407 / 1408 二选一"
        )


class TestFetchStaysNameBased:
    """Property: 取数真源仍是按名称归类，修展示码不得让取数改回按码。"""

    def test_prefill_classifies_by_name_not_by_declared_code(self):
        """同一个码配不同科目名，必须归到各自名称对应的桶（证明按名不按码）。"""
        from app.routers.wp_render_strategies._f2_inventory_main import (
            build_category_prefill,
        )
        from app.services.four_table import LeafRow

        rows = [
            LeafRow(
                account_code="1408",
                account_name="商品进销差价",
                opening=10.0,
                closing=10.0,
                debit=0.0,
                credit=0.0,
                dataset_id=None,
            ),
            LeafRow(
                account_code="1408",
                account_name="委托加工物资",
                opening=20.0,
                closing=20.0,
                debit=0.0,
                credit=0.0,
                dataset_id=None,
            ),
        ]
        out = build_category_prefill(rows)
        assert out.get("price-difference", {}).get("closing") == 10.0
        assert out.get("outsourced-processing", {}).get("closing") == 20.0

    def test_render_strategy_has_no_code_based_lookup_for_categories(self):
        """源码级：分类归集不得按 `account` 字段做 LIKE / startswith 取数。"""
        src = (
            Path(__file__).resolve().parents[2]
            / "app" / "routers" / "wp_render_strategies" / "_f2_inventory_main.py"
        ).read_text(encoding="utf-8")
        assert "classify_f2_leaf" in src, "取数真源 classify_f2_leaf 不见了"
        for banned in ('cat["account"]', "cat['account']", 'c["account"]'):
            assert banned not in src, (
                f"渲染策略里出现 {banned} —— 疑似把 account 字段用回取数（应按名称归类）"
            )


class TestReverseSelfCheck:
    """反向自检：证明断言不空转。"""

    def test_fake_code_1499_would_be_caught(self):
        """放一个假码 1499 进去必须打红（任务要求的反向自检）。"""
        fake = {"rowKey": "fake-row", "label": "假类别", "account": "1499"}
        assert fake["account"] not in ACCOUNT_CHART_INVENTORY_CODES
        with pytest.raises(AssertionError):
            TestDeclaredAccountCodesExist().test_account_code_exists_in_chart(fake)

    def test_old_wrong_codes_would_be_caught(self):
        """旧的 1410 / 1412 若还在，存在性断言必须判否。"""
        for code, label in (("1410", "合同履约成本"), ("1412", "商品进销差价")):
            assert code not in ACCOUNT_CHART_INVENTORY_CODES
            with pytest.raises(AssertionError):
                TestDeclaredAccountCodesExist().test_account_code_exists_in_chart(
                    {"rowKey": "x", "label": label, "account": code}
                )

    def test_frozen_table_anchored_by_committed_chart(self):
        """冻结表必须覆盖仓库内 CAS 2006 科目表的存货码（防冻结表被削小成自证）。"""
        committed = _committed_inventory_codes()
        assert committed, "standard_account_chart.json 没读出存货一级码 —— 锚点失效"
        missing = committed - set(ACCOUNT_CHART_INVENTORY_CODES)
        assert not missing, f"冻结表缺少仓库科目表里的码：{sorted(missing)}"
        assert "1472" in committed, "1472 合同履约成本 应在 CAS 2006 科目表里"
        assert "1410" not in committed and "1412" not in committed
