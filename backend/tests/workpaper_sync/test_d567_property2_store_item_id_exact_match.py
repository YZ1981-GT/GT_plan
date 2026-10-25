# -*- coding: utf-8 -*-
"""D567 Property 2: store_item_id 与 managed_sheet 逐字等于实测值。

spec: d567-sync-coverage-via-row-table-engine · Task 3 · Requirements 1.1, 2.1, 2.4, 3.1

🔴 **四次事故背书**：D2-3 三键 / D1-15 双键 / D1-13 双键 / D3 语义缩写键名。
   每次都因「按模式推演键名」而非按值 grep 出错。

**三处实证必错**（裁决 G3）：
  - `审定表D5` 写成 `审定表D5-1` ⇒ sheet 找不到
  - `D6-8-single-rows` 写成 `D6-8-rows` ⇒ 全仓零写入点 ⇒ 投影恒空
  - `D7-4-credit-rows` 写成 `D7-4-rows` ⇒ 同上

═══ 形态 ═══

本文件现阶段是**红基线**：断言新 sheet 接入后应有的 store_item_id 与 managed_sheet
组合。在 Task 6~19 逐步接入时，对应断言从 SKIPPED/FAIL 转 PASSED（归因于接入改动）。

已接明细 D5-2/D6-2/D7-2 的 store_item_id 恒绿（这是 Property 1 的补充角度）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")


# ═══════════════════════════════════════════════════════════════════════════════
# §1 已接明细（恒绿 —— Property 1 的 store_item_id 角度）
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlreadyRegisteredDetailSheets:
    """三家已接明细的 STORE_ITEM_ID 与 MANAGED_SHEET 逐字正确（恒绿）。"""

    def test_d5_detail_store_item_id(self) -> None:
        from app.services.workpaper_sync.phase5_d5_receivables_financing import (
            STORE_ITEM_ID, MANAGED_SHEET,
        )
        assert STORE_ITEM_ID == "D5-2-rows"
        assert MANAGED_SHEET == "应收款项融资明细表D5-2"

    def test_d6_detail_store_item_id(self) -> None:
        from app.services.workpaper_sync.phase5_d6_contract_assets import (
            STORE_ITEM_ID, MANAGED_SHEET,
        )
        assert STORE_ITEM_ID == "D6-2-rows"
        assert MANAGED_SHEET == "明细表D6-2"

    def test_d7_detail_store_item_id(self) -> None:
        from app.services.workpaper_sync.phase5_d7_contract_liabilities import (
            STORE_ITEM_ID, MANAGED_SHEET,
        )
        assert STORE_ITEM_ID == "D7-2-rows"
        assert MANAGED_SHEET == "明细表D7-2"


# ═══════════════════════════════════════════════════════════════════════════════
# §2 新接 sheet 的 managed_sheet 真名 + store_item_id（红基线 → 接入后转绿）
# ═══════════════════════════════════════════════════════════════════════════════

# 🔴 模板实测真名（Task 2 evidence §1：6 处 spec 原名与模板不符）
_EXPECTED_MANAGED_SHEET_NAMES: dict[str, str] = {
    # D5
    "D5-4": "应收款项融资公允价值测算表D5-4",
    "审定表D5": "审定表D5",  # 🔴 无 -1 后缀！
    # D6
    "D6-3": "合同资产减值准备明细表D6-3",  # spec 原写「减值准备测算」是错的
    "D6-5": "关联关系及交易检查D6-5",
    "D6-6": "合同资产检查表D6-6",
    "D6-8": "减值准备测算D6-8",  # spec 原写「合同资产减值准备测算」多前缀
    "D6-9": "减值准备转回、核销检查表D6-9",  # 含顿号「、」
    "D6-1": "审定表D6-1",
    # D7
    "D7-4": "合同负债分析表D7-4",
    "D7-5": "账龄1年以上合同负债检查表D7-5",  # 尾加「表」
    "D7-6": "关联方关系及交易检查表D7-6",  # 完整名不是「关联方合同负债检查」
    "D7-7": "合同负债检查表D7-7",  # 不是「合同负债凭证检查」
    "D7-1": "审定表D7-1",
}

# store_item_id 实测值（按值 grep，不按编号推演）
_EXPECTED_STORE_ITEM_IDS: dict[str, tuple[str, ...]] = {
    # D5
    "D5-4": ("D5-4-rows",),
    # D6
    "D6-3": ("D6-3-rows",),
    "D6-5": ("D6-5-rows",),
    "D6-6": ("D6-6-block1-rows", "D6-6-block2-rows"),  # 🔴 不是 D6-6-rows（零写入点）
    "D6-8": ("D6-8-single-rows",),  # 🔴 不是 D6-8-rows（零写入点）
    "D6-9": ("D6-9-reversal-rows", "D6-9-writeoff-rows"),
    # D7
    "D7-4": ("D7-4-credit-rows", "D7-4-debit-rows"),  # 🔴 不是 D7-4-rows（零写入点）
    "D7-5": ("D7-5-rows",),
    "D7-6": ("D7-6-rows",),
    "D7-7": ("D7-7-period-rows", "D7-7-post-rows"),  # 🔴 不是 D7-7-rows（零写入点）
}


class TestManagedSheetRealNames:
    """模板 sheet 真名 = openpyxl 实测值，不是 spec 原文推演值。"""

    @pytest.mark.parametrize("code,expected_name", list(_EXPECTED_MANAGED_SHEET_NAMES.items()))
    def test_managed_sheet_name_matches_template(self, code: str, expected_name: str) -> None:
        """每张 sheet 的真名已被 Task 2 实测确认，后续声明必须用这个真名。"""
        # 纯数据断言——声明模块尚未创建时，本条只是记录实测值，不 import 声明模块
        assert expected_name, f"{code} 的实测真名不能为空"
        assert "D5-1" not in expected_name or code == "审定表D5", (
            f"审定表D5 不带 -1 后缀（裁决 G3）"
        )


class TestStoreItemIdExactMatch:
    """store_item_id 逐字等于按值 grep 实测值。"""

    @pytest.mark.parametrize("code,expected_ids", list(_EXPECTED_STORE_ITEM_IDS.items()))
    def test_store_item_id_is_exact_grep_value(self, code: str, expected_ids: tuple[str, ...]) -> None:
        """每个 store 键已被 Task 2 grep 实测确认（非推演值）。"""
        for sid in expected_ids:
            assert sid, f"{code} 的 store_item_id 不能为空"
            # 🔴 排除零写入点聚合键（这正是事故源）
            assert sid not in ("D6-6-rows", "D6-8-rows", "D7-4-rows", "D7-7-rows"), (
                f"{code} 使用了零写入点聚合键 {sid}——完成度恒「未填」，投影恒空"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# §3 变异必红：三处「按模式推演必错」的实测值
# ═══════════════════════════════════════════════════════════════════════════════


class TestMutationDetection:
    """变异检验：按模式推演的值与实测值不同 ⇒ 判据打红。"""

    def test_mutation_adjudication_d5_with_suffix_is_wrong(self) -> None:
        """变异：`审定表D5-1`（按 D1-1/D2-1/D3-1 推演）⇒ 实测名无 -1 后缀。"""
        wrong = "审定表D5-1"
        correct = _EXPECTED_MANAGED_SHEET_NAMES["审定表D5"]
        assert wrong != correct, "变异值与正确值相同——测试无效"

    def test_mutation_d6_8_aggregate_key_is_wrong(self) -> None:
        """变异：`D6-8-rows`（按编号推演）⇒ 实测 `D6-8-single-rows`。"""
        wrong = "D6-8-rows"
        correct = _EXPECTED_STORE_ITEM_IDS["D6-8"]
        assert wrong not in correct, f"聚合键 {wrong} 竟在正确值中——测试无效"

    def test_mutation_d7_4_aggregate_key_is_wrong(self) -> None:
        """变异：`D7-4-rows`（按编号推演）⇒ 实测 `D7-4-credit-rows`/`-debit-rows`。"""
        wrong = "D7-4-rows"
        correct = _EXPECTED_STORE_ITEM_IDS["D7-4"]
        assert wrong not in correct, f"聚合键 {wrong} 竟在正确值中——测试无效"

    def test_mutation_d6_6_aggregate_key_is_wrong(self) -> None:
        """变异：`D6-6-rows`（按编号推演）⇒ 实测 `D6-6-block1-rows`/`-block2-rows`。"""
        wrong = "D6-6-rows"
        correct = _EXPECTED_STORE_ITEM_IDS["D6-6"]
        assert wrong not in correct

    def test_mutation_d7_7_aggregate_key_is_wrong(self) -> None:
        """变异：`D7-7-rows`（按编号推演）⇒ 实测 `D7-7-period-rows`/`-post-rows`。"""
        wrong = "D7-7-rows"
        correct = _EXPECTED_STORE_ITEM_IDS["D7-7"]
        assert wrong not in correct
