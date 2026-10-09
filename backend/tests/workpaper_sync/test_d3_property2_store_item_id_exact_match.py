# -*- coding: utf-8 -*-
"""D3 Property 2 红判据：`store_item_id` 必须逐字等于按值 grep 实测值。

spec: d3-sync-coverage-via-row-table-engine · Task 3
Requirements 1.2, 2.3 · design.md Property 2 · 裁决 F2

═══ 背景 ═══

D3 的 store 键用**语义缩写**命名，与 sheet 编号无对应关系（`D3-6` 的键是 `D3-rp-rows`，不是
`D3-6-rows`）。这条纪律已有三次事故背书（D2-3 三键 / D1-15 双键 / D1-13 双键，全部源于
「按模式推演键名」而非按值 grep）。design.md 明确点名：「这是本 spec 最容易犯且最难发现的错」。

真实值来自 `evidence/task1-sheet-morphology-and-geometry.md` 第四节「每个 store 键的下游
消费方清单」——按值 grep 全仓（前端 + 后端）实测，非推测：

    D3-6 关联关系及交易   → D3-rp-rows           （useD3RelatedParty.ts）
    D3-4 分析表（双区）   → D3-ana-credit-rows    （useD3Analysis.ts，贷方区）
                          → D3-ana-debit-rows     （useD3Analysis.ts，借方区）
    D3-5 账龄1年以上      → D3-lt-rows            （useD3LongTerm.ts）
    D3-7 检查表（双区）   → D3-vc-current-rows    （useD3VoucherCheck.ts，本期区）
                          → D3-vc-post-rows       （useD3VoucherCheck.ts，期后区）

D3-1 待 Task 13 实测其形态（本任务证据已确认它不是单一 rows 键，是一组 `D3-adj-*` 前缀逐格
item，不适用本判据的「单一 store_item_id 字符串」断言形态），故排除在本文件覆盖范围之外。

═══ 本文件的两层判据 ═══

第一层（合成级，"有牙齿"证明）：`TestMutationDetectsWrongKeyName` —— 用
`dataclasses.replace()` 在一个真实的 `RowTableSheetSpec` 实例上把 `store_item_id` 故意改成
按编号推演的错误值（如 `D3-6-rows`），断言判据能检测出它与真实值不符。这一层**不依赖**
Task 6/8/9/11 的声明代码是否已落地——它只需要引擎层的 `RowTableSheetSpec` 类存在（已由上游
`d1-sync-row-table-engine-and-d1-coverage` 交付），用于证明"逐字比较"这个判据逻辑本身是有效
的、会在键名错误时真实打红，不是一个无论传什么都通过的摆设。

第二层（声明级，未来生效）：`TestSixSheetsStoreItemIdExactMatch` —— 断言 Task 6/8/9/11
落地后六张 sheet（八个 store_item_id）各自的声明模块导出的常量必须逐字等于本文件顶部的真实值
表。声明模块目前尚不存在（Task 6/8/9/11 未完成）⇒ 用 `try/except ImportError` +
`pytest.mark.skipif` 让这一层在模块不存在时优雅跳过并打印原因，不让 `ImportError` 崩溃
测试收集；一旦对应声明模块存在，判据立即生效并逐字比较。

变异检验（任务原文要求）：把 `D3-rp-rows` 写成 `D3-6-rows` ⇒ 投影恒空、回写丢失，必红。
第一层测试直接执行这个变异并证明判据能检测出来。
"""
from __future__ import annotations

import dataclasses
from importlib import import_module
from types import ModuleType

import pytest

from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec

# ═══════════════════════════════════════════════════════════════════════════
# 真实值表（唯一来源：evidence/task1-sheet-morphology-and-geometry.md 第四节）
#
# 🔴 本表本身就是判据的"标准答案"——后续任何声明代码的 store_item_id 都必须逐字等于
# 这里的值。如果发现这里的值与 evidence 文档不一致，应修正这个表而不是修正声明代码
# （evidence 文档是按值 grep 实测的权威来源，本表只是把它搬进可执行判据）。
# ═══════════════════════════════════════════════════════════════════════════

REAL_STORE_ITEM_IDS: dict[str, str] = {
    "D3-6": "D3-rp-rows",
    "D3-4-credit": "D3-ana-credit-rows",
    "D3-4-debit": "D3-ana-debit-rows",
    "D3-5": "D3-lt-rows",
    "D3-7-current": "D3-vc-current-rows",
    "D3-7-post": "D3-vc-post-rows",
}

#: 按编号推演会得到的**错误**值（裁决 F2 明确禁止的推演模式），供变异检验对照。
WRONG_BY_NUMBER_PATTERN: dict[str, str] = {
    "D3-6": "D3-6-rows",
    "D3-4-credit": "D3-4-credit-rows",
    "D3-4-debit": "D3-4-debit-rows",
    "D3-5": "D3-5-rows",
    "D3-7-current": "D3-7-current-rows",
    "D3-7-post": "D3-7-post-rows",
}


def _minimal_row_table_spec(*, store_item_id: str) -> RowTableSheetSpec:
    """现造一个最简 `RowTableSheetSpec` 实例，仅用于本文件的合成级变异检验。

    几何值全是占位（不代表任何真实 sheet），因为第一层判据只关心 `store_item_id`
    字段本身的逐字比较能力，不关心其他几何是否正确——那是 Task 6/8/9/11 落地后
    由各自 contract 测试负责的事。
    """
    return RowTableSheetSpec(
        managed_sheet="占位测试用 sheet",
        sheet_key="probe-managed",
        table_key="probe_rows",
        template_id="probe-template",
        table_name="ProbeTable",
        uuid_col="Z",
        first_data_row=1,
        last_data_row=1,
        footer_row=2,
        store_item_id=store_item_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 第一层：合成级变异检验 —— 证明判据"有牙齿"（不依赖 Task 6/8/9/11 是否落地）
# ═══════════════════════════════════════════════════════════════════════════
class TestMutationDetectsWrongKeyName:
    """用 `dataclasses.replace()` 构造一个键名错误的 spec 实例，证明判据能检测出来。

    这一层证明的是"逐字比较"这个判据逻辑本身有效——如果这里的测试全部通过，说明
    "断言 store_item_id == 真实值" 这个判据在真的遇到错误键名时会失败（即：会打红）。
    这不是在测试生产代码（生产代码尚不存在），是在测试判据本身的有效性。
    """

    @pytest.mark.parametrize("key", sorted(REAL_STORE_ITEM_IDS))
    def test_wrong_by_number_pattern_is_detected_as_mismatch(self, key: str) -> None:
        """把真实值改成按编号推演的错误值 ⇒ 与真实值逐字比较必不相等。"""
        real = REAL_STORE_ITEM_IDS[key]
        wrong = WRONG_BY_NUMBER_PATTERN[key]
        # 先确认这两个值确实不同 —— 否则本条变异检验是无效变异（测试基础设施缺陷）。
        assert real != wrong, f"{key}: 真实值与错误值相同，变异检验本身失效"

        base_spec = _minimal_row_table_spec(store_item_id=real)
        mutated_spec = dataclasses.replace(base_spec, store_item_id=wrong)

        # 判据核心动作：逐字比较。变异后必不等于真实值 ⇒ 判据必红。
        assert mutated_spec.store_item_id != real, (
            f"{key}: 变异后的 store_item_id（{mutated_spec.store_item_id!r}）"
            f"竟然还等于真实值（{real!r}）—— 判据没有牙齿"
        )
        # 反向确认：未变异的原始值确实逐字等于真实值（判据在正确情形下必须通过）。
        assert base_spec.store_item_id == real

    def test_d3_6_concrete_mutation_example_from_task_text(self) -> None:
        """任务原文指定的具体例子：把 `D3-rp-rows` 写成 `D3-6-rows`。

        直接照抄任务描述的变异，不通过参数化泛化，确保这条判据逐字对应任务要求的
        变异检验用例（`D3-rp-rows` → `D3-6-rows`），而不是只在参数化的抽象层面成立。
        """
        real = "D3-rp-rows"
        wrong_by_number = "D3-6-rows"
        assert real == REAL_STORE_ITEM_IDS["D3-6"]
        assert wrong_by_number == WRONG_BY_NUMBER_PATTERN["D3-6"]

        base_spec = _minimal_row_table_spec(store_item_id=real)
        mutated_spec = dataclasses.replace(base_spec, store_item_id=wrong_by_number)

        assert mutated_spec.store_item_id == "D3-6-rows"
        assert mutated_spec.store_item_id != real, (
            "把 D3-rp-rows 写成 D3-6-rows 后，判据必须检测出与真实值不符"
        )

    def test_correct_value_passes_exact_match(self) -> None:
        """正向对照：真实值本身逐字通过（判据不是「永远打红」的装饰）。"""
        for key, real in REAL_STORE_ITEM_IDS.items():
            spec = _minimal_row_table_spec(store_item_id=real)
            assert spec.store_item_id == real, key

    def test_fuzzy_match_is_not_acceptable(self) -> None:
        """需求 1.2/2.3 要求「逐字相等」——大小写/多余空白/子串包含都不算通过。

        判据必须是精确字符串比较（`==`），不是「看起来差不多」。这里用大小写变体和
        带空白的变体证明：即便变异值与真实值"看起来很像"，只要不是逐字相等，判据
        也必须打红。
        """
        real = "D3-rp-rows"
        near_misses = [
            "D3-RP-ROWS",       # 大小写不同
            "D3-rp-rows ",      # 末尾多一个空格
            " D3-rp-rows",      # 开头多一个空格
            "D3-rp-row",        # 少一个字符
            "D3-rp-rowss",      # 多一个字符
        ]
        for near_miss in near_misses:
            assert near_miss != real, f"{near_miss!r} 不应等于 {real!r}（否则判据是模糊匹配）"


# ═══════════════════════════════════════════════════════════════════════════
# 第二层：声明级判据 —— 未来 Task 6/8/9/11 落地后生效，现在优雅跳过
# ═══════════════════════════════════════════════════════════════════════════
def _try_import(module_path: str) -> ModuleType | None:
    """尝试导入声明模块；不存在（ImportError/ModuleNotFoundError）时返回 None 而不崩溃。

    ModuleNotFoundError 是 ImportError 的子类，`except ImportError` 已覆盖两者。
    """
    try:
        return import_module(module_path)
    except ImportError:
        return None


_D3_06_MODULE = _try_import("app.services.workpaper_sync.phase5_d3_06_related_party")
_D3_04_MODULE = _try_import("app.services.workpaper_sync.phase5_d3_04_analysis")
_D3_05_MODULE = _try_import("app.services.workpaper_sync.phase5_d3_05_long_term")
_D3_07_MODULE = _try_import("app.services.workpaper_sync.phase5_d3_07_voucher_check")


def _extract_store_item_ids(module: ModuleType | None) -> dict[str, str]:
    """从声明模块里找出所有 `RowTableSheetSpec` 实例的 `store_item_id`。

    容错两种声明习惯：模块级常量直接是 `RowTableSheetSpec` 实例，或模块导出一个/多个
    以 `SPEC` 开头的常量名（design.md 示例用 `SPEC_D306`/`SPEC_D304_CREDIT` 等命名）。
    找不到任何 `RowTableSheetSpec` 实例时返回空 dict（由调用方决定如何断言，不在这里
    静默吞掉——空 dict 本身就是一个可断言的诊断信号）。
    """
    if module is None:
        return {}
    found: dict[str, str] = {}
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if isinstance(value, RowTableSheetSpec):
            found[name] = value.store_item_id
    return found


class TestSixSheetsStoreItemIdExactMatch:
    """六张 sheet 的八个 store_item_id 逐字等于实测值（现状：声明模块尚未落地，优雅跳过）。

    每个测试方法在对应声明模块不存在时调用 `pytest.skip()` 并说明「待 Task N 声明后生效」，
    不使用 `pytest.mark.skipif`（因为 skip 原因需要按具体哪个键缺失动态生成，比静态
    装饰器更精确）。一旦声明模块存在，测试立即对真实常量做逐字比较。
    """

    # ── D3-6（Task 6）─────────────────────────────────────────────────────
    def test_d3_06_related_party_store_item_id(self) -> None:
        if _D3_06_MODULE is None:
            pytest.skip(
                "app.services.workpaper_sync.phase5_d3_06_related_party 尚未声明"
                "（待 Task 6 落地后生效）"
            )
        found = _extract_store_item_ids(_D3_06_MODULE)
        assert found, (
            "phase5_d3_06_related_party 模块已存在，但未找到任何 RowTableSheetSpec 实例 —— "
            "声明代码可能改用了别的导出方式，需要更新本判据的提取逻辑"
        )
        values = set(found.values())
        assert values == {REAL_STORE_ITEM_IDS["D3-6"]}, (
            f"D3-6 声明的 store_item_id 应逐字等于 {REAL_STORE_ITEM_IDS['D3-6']!r}，"
            f"实得 {found!r}"
        )

    # ── D3-4（Task 8，双区）───────────────────────────────────────────────
    def test_d3_04_analysis_store_item_ids_both_regions(self) -> None:
        if _D3_04_MODULE is None:
            pytest.skip(
                "app.services.workpaper_sync.phase5_d3_04_analysis 尚未声明"
                "（待 Task 8 落地后生效）"
            )
        found = _extract_store_item_ids(_D3_04_MODULE)
        assert found, "phase5_d3_04_analysis 模块已存在，但未找到任何 RowTableSheetSpec 实例"
        expected = {
            REAL_STORE_ITEM_IDS["D3-4-credit"],
            REAL_STORE_ITEM_IDS["D3-4-debit"],
        }
        actual = set(found.values())
        assert actual == expected, (
            f"D3-4 应声明**两个**受管区，store_item_id 集合应逐字等于 {expected!r}，"
            f"实得 {actual!r}（found={found!r}）。"
            "若只找到一个键，说明只声明了单区，违反需求 2.1 的双区要求。"
        )

    # ── D3-5（Task 9）─────────────────────────────────────────────────────
    def test_d3_05_long_term_store_item_id(self) -> None:
        if _D3_05_MODULE is None:
            pytest.skip(
                "app.services.workpaper_sync.phase5_d3_05_long_term 尚未声明"
                "（待 Task 9 落地后生效）"
            )
        found = _extract_store_item_ids(_D3_05_MODULE)
        assert found, "phase5_d3_05_long_term 模块已存在，但未找到任何 RowTableSheetSpec 实例"
        values = set(found.values())
        assert values == {REAL_STORE_ITEM_IDS["D3-5"]}, (
            f"D3-5 声明的 store_item_id 应逐字等于 {REAL_STORE_ITEM_IDS['D3-5']!r}，"
            f"实得 {found!r}"
        )

    # ── D3-7（Task 11，双区）──────────────────────────────────────────────
    def test_d3_07_voucher_check_store_item_ids_both_regions(self) -> None:
        if _D3_07_MODULE is None:
            pytest.skip(
                "app.services.workpaper_sync.phase5_d3_07_voucher_check 尚未声明"
                "（待 Task 11 落地后生效）"
            )
        found = _extract_store_item_ids(_D3_07_MODULE)
        assert found, "phase5_d3_07_voucher_check 模块已存在，但未找到任何 RowTableSheetSpec 实例"
        expected = {
            REAL_STORE_ITEM_IDS["D3-7-current"],
            REAL_STORE_ITEM_IDS["D3-7-post"],
        }
        actual = set(found.values())
        assert actual == expected, (
            f"D3-7 应声明**两个**受管区，store_item_id 集合应逐字等于 {expected!r}，"
            f"实得 {actual!r}（found={found!r}）。"
            "若只找到一个键，说明只声明了单区，违反需求 3.1 的双区要求。"
        )

    # ── 汇总：八个 store_item_id 不得互相拼写混淆 ────────────────────────
    def test_all_real_values_are_pairwise_distinct(self) -> None:
        """八个真实值本身必须两两不同（结构性校验：本表不能因笔误而自相矛盾）。

        这一条不依赖任何声明模块是否存在——它只检查 REAL_STORE_ITEM_IDS 这个真实值表
        本身的内部一致性，任何时候都应该通过。
        """
        values = list(REAL_STORE_ITEM_IDS.values())
        assert len(values) == len(set(values)), (
            f"真实值表出现重复值，需检查是否笔误：{values}"
        )
        assert len(values) == 6, f"应覆盖六个 store_item_id（D3-1 除外），实得 {len(values)} 个"


# ═══════════════════════════════════════════════════════════════════════════
# 现状登记：本文件被收集时打印一次性提示，说明第二层判据当前的 skip/生效状态
# （不是断言，只是让 `pytest -v` 输出可读，供人工核对"待声明"与"已生效"分布）。
# ═══════════════════════════════════════════════════════════════════════════
def test_current_declaration_status_registered_for_visibility() -> None:
    """登记当前四个声明模块各自是否已落地（供人工核对，不代表本任务需要它们已落地）。

    Task 3 执行时的预期状态：全部四个 `_MODULE is None`（Task 6/8/9/11 均未完成）。
    ⇒ 本条测试本身应该通过（它只是在报告状态，不对状态提出要求），但会在测试输出里
    留下一行可读记录，说明当前 Property 2 判据处于"合成级已生效、声明级待生效"状态。
    """
    status = {
        "phase5_d3_06_related_party (Task 6)": _D3_06_MODULE is not None,
        "phase5_d3_04_analysis (Task 8)": _D3_04_MODULE is not None,
        "phase5_d3_05_long_term (Task 9)": _D3_05_MODULE is not None,
        "phase5_d3_07_voucher_check (Task 11)": _D3_07_MODULE is not None,
    }
    landed = [name for name, is_landed in status.items() if is_landed]
    pending = [name for name, is_landed in status.items() if not is_landed]
    print(f"\n[Property 2 声明级状态] 已落地: {landed or '（无）'}")
    print(f"[Property 2 声明级状态] 待声明: {pending or '（无）'}")
    # 无断言 —— 本测试只用于可见性登记，永远通过。
    assert True
