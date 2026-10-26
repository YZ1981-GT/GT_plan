# -*- coding: utf-8 -*-
"""F2-P11：既有 contract golden digest 零回归。

spec: f2-sync-coverage-four-entry-lanes · Task 5 · Requirements 7.3
Property 11: F2 新增 provider 不得改变既有契约文件的任何字节。

判据：逐文件 sha256(file_bytes) 与基线逐字比对。
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

CONTRACTS_DIR = _BACKEND / "data" / "workpaper_sync_contracts"

# ── 基线：2026-09-26 现算（Task 5 冻结）──────────────────────────────────
# key = filename, value = sha256 前 16 位（足够唯一，全长见证据文件）
GOLDEN_BASELINE: dict[str, str] = {
    "_example.candidate.json": "4e85a633550b8f60",
    # 🔴 2026-09-27 更新（`91beaa2a284fd8d2` → 本值）：B60 的契约新增了 `review.html_store`
    #    段并给行表字段填了 `store_item_id`，把 OO→HTML 方向打通。
    #    此前 B60 是 `NON_STORE_BACKED_ADAPTERS` 的唯一成员，理由「契约无 html_store ⇒
    #    纯 Excel entry」—— 那描述的是「前端还没有 HTML 面」这个时点事实，
    #    `b60/GtB60HourBudgetPanel.vue` 落地后不再成立。契约是**真的变了**，
    #    不是度量漂移，故更新基线而非改判据形态。
    "b60.hour_budget.json": "aadb548da7f60e11",
    # 🔴 2026-09-28 更新（`62b589551bd99050` → 本值）：D1-4 三区的 `json_key` 与前端
    #    实际持久化键**不一致**（实测 13 列），契约里的 `json_pointer` 因此全是死指针
    #    —— materialize 取不到值会把 Excel 格写成 `0`/清空，extract 把值写进前端从不读
    #    的键。按裁决 B1（spec 对齐前端，前端是写入方且真库已有数据）改 spec 后重生契约。
    #    契约是**真的变了**，不是度量漂移，故更新基线而非改判据形态（同上方 b60 先例）。
    #    详见 `.kiro/specs/d1-sync-row-table-engine-and-d1-coverage/tasks.md` K 节
    #    与 `test_d1_json_key_matches_frontend_store.py`。
    # 🔴 2026-09-28 二次更新（`5cf83e3fcdfd9ea5` → 本值）：D1-4 第三区（票据种类小计
    #    R23-24）的**静态受管区**已进契约 —— `d14-managed` 多出第三个 table
    #    `bad_debt_notetype_rows`（2 固定行 × 9 列 = 18 field，无 `row_identity`
    #    ⇒ `has_dynamic_rows=False` ⇒ 归入 `static_tables`）。
    #    此前契约的 `static_tables` **全空**，该 item 没有任何 stable field key 可投影。
    #    🔴 **T7 裁决 A（2026-09-28）把静态 table 撤回**，契约从 19 table 回到 18 table
    #    （与 D4 `phase5_d4_policy_check_sheet` 相同处置，待 marker-relative content 字段落地后再扩），
    #    digest 回到 L 节改名后、O 节加静态 table 前的值。详见 tasks.md T7 节。
    # 🔴 2026-09-28 三次更新（`5cf83e3fcdfd9ea5` → 本值）：整册门根因修复。
    #    entry 模块 `phase5_d1_notes_receivable` 补出复数 `instrumentation_specs()`
    #    薄转发，并把 `instrumentation_definition_payload` 改走
    #    `build_instrumentation_payload_for_sheets`（18 组 spec，原先只投 1 组）。
    #    契约里 **只有** `instrumentation_definition_sha256` 这一个单向引用变了，
    #    `sheets` 与结构清册（248 项）逐项不变 —— 由
    #    `test_d1_full_book_gate_open_pg.py::test_root_cause_was_missing_plural_instrumentation_entry`
    #    以「差异字段集合 == 恰好这一项」的形式钉死，不是靠这里的注释自证。
    #    根因与变异证明详见 `test_d1_instrumentation_specs_forwarder.py`。
    # 🔴 2026-10-03 批量更新（D 系列 + F1）：公式推送引擎 / 逐循环 spec 实施期间
    #    D1~D7 的契约均因 instrumentation / sheet spec 扩容而变化（各 spec tasks.md
    #    有逐次变更说明），F1 因宿主接桥 + 契约重算而变。这些变化均已由各自 spec
    #    的守卫测试覆盖，此处只同步基线 digest。
    # 🔴 2026-10-26 更新 d1 / d4 / d5 / d6 / f1 / g7（spec oo-writeback-template-parity-closure R1）：
    #    这些契约的权威模板按会计口径修了公式（清单 `scripts/fix/fix_template_formula_defects.py`），
    #    契约里随之变的只有模板 sha / 结构哈希 / 定义哈希与审核依据文本，由各生成器重算。
    #    d1 / f1 的旧基线在 HEAD 上本就已过期（各自 spec 改契约时未同步本表），一并更新到现值。
    "d1.notes_receivable_detail.json": "75f1b401764fa7c9",
    # 🔴 2026-10-10 更新 d2（`1714d5719d558446` → 本值），两次契约变化一并同步：
    #    ① 299c216a9（10-07）把 `d21-managed` 的 locator 从 TABLE_SHEET_ANCHOR 改为
    #       defined_name_ref，当时未同步本基线（HEAD 上本条已红：`cd80314142ae5bdf`）；
    #    ② spec d2-online-edit-platform-closure（R2）：契约里**只有**
    #       `instrumentation_definition_sha256` 一个字段变了（`46f3c617…` 单数、只覆盖 D2-2
    #       → `9e88e86b…` 复数、覆盖 D2-2/D2-3/D2-1 三张受管 sheet），与上方 D1「三次更新」
    #       同型。单数 instrumentation 正是 D2 在线编辑失败的根因之一；「契约 sheet 必须被
    #       已发布 instrumentation 覆盖」由 `test_published_instrumentation_covers_contract_sheets.py`
    #       守护。契约是**真的变了**，不是度量漂移，故更新基线。
    "d2.receivable_detail.json": "56007587080236ac",
    "d3.prepaid_receipts_detail.json": "a32e531ac342e7cc",
    "d4.revenue_detail.json": "7b1d6362eeba4a7d",
    "d5.receivables_financing_detail.json": "b76e345cc29797b5",
    "d6.contract_assets_detail.json": "eeb454b0dcd45cbc",
    "d7.contract_liabilities_detail.json": "735d194bc8072405",
    "e1.monetary_fund_detail.json": "4a0cf6c928566c96",
    "f1.prepayment_detail.json": "0439591e2e504c74",
    "g7.soe_subsidiary_disclosure.json": "6fdd12a7e008eb24",
    "h1.disposal_check.json": "e7d6c1b75af2d600",
}


class TestF2P11GoldenDigestZeroRegression:
    """既有 13 个契约文件在 F2 开发期间不得被改动。"""

    @pytest.mark.parametrize("filename,expected_prefix", list(GOLDEN_BASELINE.items()))
    def test_contract_file_unchanged(self, filename: str, expected_prefix: str) -> None:
        path = CONTRACTS_DIR / filename
        assert path.is_file(), f"契约文件丢失: {filename}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest.startswith(expected_prefix), (
            f"{filename} 的 digest 变了: {digest[:16]} != {expected_prefix}"
        )

    def test_no_baseline_file_deleted(self) -> None:
        """基线里的文件不得被删除。"""
        for filename in GOLDEN_BASELINE:
            assert (CONTRACTS_DIR / filename).is_file(), f"基线文件 {filename} 被删除"

    def test_baseline_count_is_13(self) -> None:
        """基线包含 13 个文件（含 example.candidate）。"""
        assert len(GOLDEN_BASELINE) == 13
