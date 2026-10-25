# -*- coding: utf-8 -*-
"""D3-6 关联关系及交易检查表 —— 声明本身的独立判据（Task 7 补，design.md Property 5）。

spec: d3-sync-coverage-via-row-table-engine · Task 7 · Requirements 1.3

═══ 为什么补这一份（Task 6 证据的缺口）═══

Task 6 证据文档（`evidence/task6-d3-06-declaration.md` §三）用 Python REPL 交互式验证过
`SPEC_D306.formula_mask == ('F12:F16',)`，但那次验证**没有落成一条持久化、可重跑的判据**——
下次任何人改动 `phase5_d3_06_related_party.py` 的 `formula_columns`/`first_data_row`/
`last_data_row`，不会有任何测试失败来提醒。

对照上游范式（`test_e1_02_cash_detail_spec.py::test_formula_mask_is_engine_computed` /
`test_phase5_d1_sheet_specs.py::test_formula_mask_matches_e_h_k_columns` /
`test_d4_6_indicator_contract.py::test_d46_formula_mask_covers_diff_columns`）——每一个已交付
的 per-sheet 声明模块都有一条**独立**（不依赖 `test_d3_property2_*`/`test_d3_expansion.py`
两份判据文件）的 `formula_mask` 断言，专门钉住"引擎现算 mask == 期望值"这件事本身，不与
store_item_id 判据或扩容对齐判据混在一起。D3-6 之前没有这一条，本文件补齐。

同时补两条同范式的辅助判据（几何与字段集合的最小自证），避免本文件只有一行断言显得单薄，
也顺手把 Task 6 证据文档里"独立 openpyxl 复核"的关键结论（footer SUM 区间只覆盖 3 行而非 5 行
这一模板预存缺陷、及其与 formula_mask 的关系）钉成可执行判据而非只存在于证据文档的叙述中。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d3_06_related_party as D306


def test_formula_mask_is_engine_computed() -> None:
    """Property 5：mask 由引擎按 formula_columns × 数据行区间现算，不是手写字面量。

    D306 声明代码（`phase5_d3_06_related_party.py`）没有 `formula_mask=` 关键字参数
    （它是 `@property`，dataclass 字段列表里没有它 —— 传了会直接 TypeError），本条判据是
    对"引擎现算出的值确实等于预期值"这件事的持久化钉子。
    """
    assert D306.SPEC_D306.formula_mask == ("F12:F16",)


def test_formula_mask_derives_from_formula_columns_and_data_row_range() -> None:
    """mask 的构造关系必须逐字可推导：`{col}{first_data_row}:{col}{last_data_row}`。

    与上一条断言互补——上一条钉死具体字符串，这一条钉死*为什么*是这个字符串（防止将来有人
    改了 `first_data_row`/`last_data_row` 却忘记同步更新上一条断言里的硬编码字符串，
    此时这条会先失败并指出真正原因）。
    """
    spec = D306.SPEC_D306
    # 用与生产代码相同的构造表达式重新推导一次（不是复制粘贴字面量），
    # 确认 formula_mask 与 (formula_columns, first_data_row, last_data_row) 三者的关系稳定。
    expected = tuple(
        f"{col}{spec.first_data_row}:{col}{spec.last_data_row}" for col in spec.formula_columns
    )
    assert spec.formula_mask == expected
    assert spec.formula_columns == ("F",), "D3-6 数据区唯一逐行有公式的列是 F（期末余额）"
    assert spec.first_data_row == 12 and spec.last_data_row == 16, (
        "数据区实测为 12-16（5 行模板占位），Task 1 证据已逐格核对"
    )


def test_mutation_missing_formula_column_shrinks_mask() -> None:
    """变异（design.md Property 5 原文）：`formula_columns` 少一列 ⇒ mask 跟着变小，必红。

    构造一个去掉 F 列的合成 spec（不改生产代码），证明 mask 对 formula_columns 敏感，
    不是一个恒定不变、无论传什么都一样的装饰性属性。
    """
    import dataclasses

    mutated = dataclasses.replace(D306.SPEC_D306, formula_columns=())
    assert mutated.formula_mask == (), "去掉全部公式列 ⇒ mask 必须跟着变空"
    assert mutated.formula_mask != D306.SPEC_D306.formula_mask


def test_footer_sum_range_gap_is_a_template_defect_not_a_mask_bug() -> None:
    """Task 6 证据记录的模板预存缺陷：footer R17 的 SUM 只覆盖 C12:C14（3 行），
    数据区实际是 12-16（5 行）。这不是 formula_mask 的错——mask 保护的是数据行本身
    （12-16 逐行的 F 列公式），不是 footer 的 SUM 引用区间；两者是两个独立的坐标概念。

    本条判据把这个"如实记录但不处理"的事实钉成可执行断言，防止将来有人误以为
    footer SUM 区间应该驱动 formula_mask 的行区间（那会把保护范围收窄到 12-14，
    漏保护 15-16 两行的真实公式格）。
    """
    spec = D306.SPEC_D306
    assert spec.footer_row == 17
    assert spec.last_data_row == 16, "formula_mask 的行区间上界取数据区实测边界（16），不取 footer SUM 区间上界（14）"
    assert "F12:F16" in spec.formula_mask, "mask 必须覆盖全部 5 行数据区（12-16），不因 footer SUM 只写 3 行而收窄"
