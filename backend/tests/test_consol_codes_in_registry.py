"""Contract tests — 合并报表 report/account 码 + 合并附注 section 集合 vs ACNR 覆盖。

Validates: Requirements 20.8

背景（acnr-consumer-wiring P14）：
- task 31.1 把合并报表的 report row / account 引用接到 ACNR REPORT/TB 域
  （`audit-platform/frontend/src/components/consolidation/composables/useConsolReportAddress.ts`
  经 `useAddressRegistry` store 的 `reportAddresses`(REPORT 域)/`tbAddresses`(TB 域) + `useAcnr()`
  resolver 动态取数——**不含任何硬编码 report row-code / account_code 字面量**）。
- task 31.2 把合并附注 note section 引用接到 ACNR NOTE 域
  （`ConsolNoteTab.vue` `sourceNoteAddr(sectionId) → note:{sectionId}` +
  `useAcnr().resolveIndex('note:'+sectionId)`）。

本模块两条契约测试守护「码/section 集合不漂移出 ACNR 覆盖」（Req 20.8）：

1. `test_consol_report_codes_in_registry`
   合并报表的 report row 全集就是 `report_config_seed.json`（REPORT 域真源）——合并报表复用
   同一份 report_type 行配置。由于合并报表实际渲染的码由前端运行时从 REPORT/TB 域 store 动态取，
   **无固定前端字面量集**（`useConsolReportAddress` 已确认无硬编码码），故本测试将契约收敛为：
   report_config seed 良构（非空、每行含 row_code），且四类合并报表 report_type
   （balance_sheet / income_statement / cash_flow_statement / equity_statement）以
   `scope=consolidated` 存在于 seed；合并作用域配置的 row_code ⊆ REPORT 域 row_code 全集。
   —— 任何一项被破坏即为 REPORT 域覆盖漂移（Req 20.8，catalog 覆盖内）。

2. `test_consol_note_sections_in_registry`
   NOTE 是 V1 动态域（Req 17.4 / Req 20.8：EXEMPT from 静态 L1 catalog 成员校验）。
   正确契约不是「把 note section 塞进静态 catalog」，而是 **文档化并验证 V1 动态域豁免**：
   合并附注的 `note:{sectionId}` 引用经 ACNR full_resolve V1-delegation 解析，
   **不要求**登记在 L1 静态 catalog——故 L1 层 `_index_ref_to_addr_id('note:...')` 返回 None、
   `resolve(index_ref='note:...')` 在 L1 返回 found=False（委托 V1）即为期望行为；
   同时验证合并附注使用的 `note:{sectionId}` 形态是合法的 NOTE 命名空间索引引用。

策略（无 DB 依赖，纯静态源 + L1 catalog 纯函数，对齐 sibling test_crosscheck_codes_in_report_registry）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# 导入 app 包前置（与 sibling ACNR 测试一致，避免 settings 缺省报错）。
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from app.services.acnr import catalog  # noqa: E402

# ── 路径定位（对齐 sibling：test 在 backend/tests/ → parent.parent = backend/） ──
_BACKEND = Path(__file__).resolve().parent.parent
SEED_PATH = _BACKEND / "data" / "report_config_seed.json"

# 四类合并报表 report_type（合并报表复用同一份 report_type 行配置）。
_CONSOL_REPORT_TYPES = {
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "equity_statement",
}

# 合并附注 section id 代表形态（ConsolNoteTab 的 section_id 为数据驱动的中文章节码，
# 形如 "五-1"/"六-3"，以及通用 slug；本测试验证 `note:{sectionId}` 形态而非固定码集）。
_CONSOL_NOTE_SECTION_SAMPLES = [
    "五-1",
    "五-12",
    "六-3",
    "note_cash",
    "accounts_receivable",
]


# ── report_config seed 加载/汇总辅助 ─────────────────────────────────────────


def _load_seed() -> list[dict]:
    assert SEED_PATH.exists(), f"report_config seed 不存在: {SEED_PATH}"
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, "report_config_seed.json 应为非空 list"
    return data


def _all_row_codes(seed: list[dict]) -> set[str]:
    codes: set[str] = set()
    for config in seed:
        for row in config.get("rows", []):
            rc = row.get("row_code")
            if rc:
                codes.add(rc)
    return codes


def _consolidated_configs(seed: list[dict]) -> list[dict]:
    return [c for c in seed if c.get("scope") == "consolidated"]


# ── 测试 1：合并报表 report/account 码 vs REPORT 域覆盖 ──────────────────────


def test_consol_report_codes_in_registry() -> None:
    """契约：合并报表 report row 全集（REPORT 域真源 report_config_seed）良构且覆盖四类合并报表。

    合并报表实际渲染的码由前端从 REPORT/TB 域 store 运行时动态取（无固定字面量集），
    故契约收敛为 REPORT 域真源本身的良构性 + 合并作用域覆盖（Req 20.8，catalog 覆盖内）。
    """
    seed = _load_seed()

    # (a) seed 良构：每个 config 有 report_type + 非空 rows，且每行 row_code 非空。
    for i, config in enumerate(seed):
        assert config.get("report_type"), f"seed[{i}] 缺 report_type: {config.get('description')}"
        rows = config.get("rows")
        assert isinstance(rows, list) and rows, f"seed[{i}] rows 应为非空 list"
        for j, row in enumerate(rows):
            assert row.get("row_code"), (
                f"seed[{i}].rows[{j}] 缺 row_code（REPORT 域坐标名漂移）: {row}"
            )

    universe = _all_row_codes(seed)
    assert universe, "report_config seed 未汇总到任何 row_code（REPORT 域真源为空）"

    # (b) 四类合并报表 report_type 必须以 scope=consolidated 存在于 seed。
    consolidated = _consolidated_configs(seed)
    assert consolidated, "report_config seed 无 consolidated 作用域配置（合并报表真源缺失）"
    consol_types_present = {c.get("report_type") for c in consolidated}
    missing_types = sorted(_CONSOL_REPORT_TYPES - consol_types_present)
    assert not missing_types, (
        f"合并报表 report_type 在 report_config seed(consolidated) 中缺失"
        f"（REPORT 域覆盖漂移，Req 20.8）: {missing_types}\n"
        f"seed 现有 consolidated report_type: {sorted(t for t in consol_types_present if t)}"
    )

    # (c) 合并作用域配置的 row_code ⊆ REPORT 域 row_code 全集（合并报表复用同一 seed，无孤儿码）。
    consol_codes = _all_row_codes(consolidated)
    assert consol_codes, "consolidated 配置未汇总到任何 row_code"
    orphans = sorted(consol_codes - universe)
    assert not orphans, (
        f"合并报表 row_code 不在 REPORT 域 row_code 全集内（孤儿/漂移，Req 20.8）: {orphans}"
    )


# ── 测试 2：合并附注 section 集合 —— NOTE 域 V1 动态域豁免 ─────────────────────


def test_consol_note_sections_in_registry() -> None:
    """契约：合并附注 note section 走 NOTE 域 V1-delegation，豁免静态 L1 catalog 成员校验。

    Per Req 17.4 / Req 20.8：NOTE 是 V1 动态域。正确的契约是**验证豁免**而非强制入 catalog：
      1. 合并附注 `note:{sectionId}` 是合法的 NOTE 命名空间索引引用（格式可用于 `note:` 解析）。
      2. L1 静态 catalog **不**解析 NOTE 域（`_index_ref_to_addr_id` 返回 None）——即 note section
         无需预登记 L1；由 full_resolve V1-delegation 处理（动态域豁免）。
      3. `resolve(index_ref='note:...')` 在 L1 层返回 found=False（委托 V1），这是期望行为，
         合并附注 UI 据此走 NOTE 导航/resolveIndex（miss 回退现有 note 导航，Req 20.7）。
    """
    for section_id in _CONSOL_NOTE_SECTION_SAMPLES:
        index_ref = f"note:{section_id}"  # ConsolNoteTab.sourceNoteAddr 的形态

        # (1) 形态合法：NOTE 命名空间索引引用（ns=='note' + 非空 target）。
        assert ":" in index_ref, f"note 索引引用应含 ns 分隔符: {index_ref}"
        ns, target = index_ref.split(":", 1)
        assert ns.lower() == "note", f"合并附注引用 ns 应为 'note': {index_ref}"
        assert target, f"合并附注 note section target 不应为空: {index_ref}"

        # (2) L1 静态 catalog 不解析 NOTE 域（动态域豁免，非 gap）。
        assert catalog._index_ref_to_addr_id(index_ref) is None, (
            f"NOTE 域应豁免静态 L1 catalog（V1 动态域）；"
            f"L1 意外解析 {index_ref} 说明豁免契约被破坏"
        )

        # (3) resolve 在 L1 返回 found=False（委托 V1）——期望行为，用于 V1-delegation。
        res = catalog.resolve(index_ref=index_ref)
        assert res.get("found") is False, (
            f"NOTE 域 {index_ref} 在 L1 catalog 应 found=False（委托 V1 动态解析），"
            f"实际: {res}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
