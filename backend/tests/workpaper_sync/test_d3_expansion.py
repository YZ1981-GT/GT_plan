# -*- coding: utf-8 -*-
"""D3 多受管 sheet 扩容判据（Task 6）。

spec: d3-sync-coverage-via-row-table-engine · Task 6 · Requirements 1.1 / 1.4 / 6.6

═══ 判据面（参照 D1 同名判据 `test_d1_instrumentation_specs_expansion.py`，按 D3-6 单区
最简场景裁剪——本任务不含 D1 那种静态区寄生分支，Task 1 已实测确认六张 D3 sheet 均非
static_region）═══

1. **开关全 False ⇒ 与现状等价**（扩容面 `managed_row_table_specs()`/`instrumentation_specs()`
   均为空 tuple，`all_store_item_ids()` 只有 D3-2 自身的 `D3-det-rows`）。
2. **打开 D3-6 开关 ⇒ 受管区按预期增长**（受管区计数 1→2，`store_item_id` 出现 `D3-rp-rows`）。
3. **翻译正确性**：`ExcelInstrumentationSpec` 的几何 == `RowTableSheetSpec` 的几何。
4. **两方向 store item 同源**：`all_store_item_ids()` 含 D3-2 自身 + 扩容面，无重复。
5. **对齐计数守卫**：specs 与契约 sheets 不对齐 ⇒ fail-closed 且精确报差集（D4-35 事故形态）。
6. **循环层 `build_contract_payload()` 开关 False 时零回归**（Property 1 的另一角度实证：
   契约 payload 的 `sheets` 长度与字段在开关关闭时不受本任务改动影响）。

═══ ✅ Task 10（阶段 2 验收）迁移 ═══

D3-6 / D3-4 / D3-5 三个开关在 Task 10 统一打开（默认值 True）。原本依赖"默认值 = False"的
判据改为用 `monkeypatch` **显式关掉**开关再断言回到 D3-2 单区（原意图不变，不再依赖默认值）；
另补 `test_default_state_has_d306_d304_d305_enabled` 钉住新默认状态。

🔴 monkeypatch 关开关后现算 payload 必然与磁盘契约不一致（磁盘契约按默认开关生成），这类用例
   **不调** `assert_contract_file_matches_source()`；需要磁盘契约时用 `load_contract_from_disk()`
   且在 monkeypatch 之前取。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d3_04_analysis as D304
from app.services.workpaper_sync import phase5_d3_05_long_term as D305
from app.services.workpaper_sync import phase5_d3_06_related_party as D306
from app.services.workpaper_sync import phase5_d3_expansion as P
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as ENTRY
from app.services.workpaper_sync.models import SyncDomainError

#: 扩容面全部灰度开关（顺序即 `managed_row_table_specs()` 的枚举顺序）。
_ALL_SWITCHES: tuple[str, ...] = (
    "_INCLUDE_D306_RELATED_PARTY",
    "_INCLUDE_D304_ANALYSIS",
    "_INCLUDE_D305_LONG_TERM",
    "_INCLUDE_D307_VOUCHER_CHECK",
)

#: Task 10 后的默认 store item 全集（D3-2 自身 + D3-6 + D3-4 两区 + D3-5 + D3-7 两区，逐字取前端 composable）。
_STAGE2_STORE_ITEMS: tuple[str, ...] = (
    "D3-det-rows",
    "D3-rp-rows",
    "D3-ana-debit-rows",
    "D3-ana-credit-rows",
    "D3-lt-rows",
    "D3-vc-current-rows",
    "D3-vc-post-rows",
)


def _switch_all_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ALL_SWITCHES:
        monkeypatch.setattr(P, name, False)


def test_default_state_has_d306_d304_d305_enabled() -> None:
    """默认状态：四张已开（D3-6/D3-4/D3-5/D3-7），扩容面含全部 spec（Excel 行序）。"""
    from app.services.workpaper_sync import phase5_d3_07_voucher_check as D307
    for name in _ALL_SWITCHES:
        assert getattr(P, name) is True, f"{name} 默认应为 True"

    specs = P.managed_row_table_specs()
    assert specs == (
        D306.SPEC_D306,
        D304.SPEC_D304_DEBIT, D304.SPEC_D304_CREDIT,
        D305.SPEC_D305,
        D307.SPEC_D307_CURRENT, D307.SPEC_D307_POST,
    )
    assert [s.resolved_sheet_key for s in P.instrumentation_specs()] == [
        "d36-managed",
        "d34-managed",
        "d34-managed",
        "d35-managed",
        "d37-managed",
        "d37-managed",
    ]
    assert P.all_store_item_ids() == _STAGE2_STORE_ITEMS
    # 默认状态下磁盘契约与现算一致且与扩容面对齐（真实发布面，不是 monkeypatch 出来的形状）。
    P.assert_specs_align_with_contract_sheets(ENTRY.assert_contract_file_matches_source())


def test_switches_off_reverts_to_d3_2_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """开关全关（显式 monkeypatch，不依赖默认值）⇒ 扩容面为空，store item 只有 D3-det-rows。"""
    _switch_all_off(monkeypatch)

    specs = P.managed_row_table_specs()
    assert specs == ()
    assert P.instrumentation_specs() == ()
    assert P.all_store_item_ids() == (ENTRY.STORE_ITEM_ID,)


def test_enabling_d306_adds_one_managed_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """只开 D3-6（其余显式关）⇒ 受管区 1→2，store_item_id 集合含 D3-rp-rows。"""
    _switch_all_off(monkeypatch)
    monkeypatch.setattr(P, "_INCLUDE_D306_RELATED_PARTY", True)
    specs = P.managed_row_table_specs()
    assert len(specs) == 1
    assert specs[0] is D306.SPEC_D306

    instr = P.instrumentation_specs()
    keys = [s.resolved_sheet_key for s in instr]
    assert len(instr) == 1, f"受管区应 1→2（扩容面自身应新增 1 项），实得 {keys}"
    assert D306.SHEET_KEY_D306 in keys

    items = set(P.all_store_item_ids())
    assert items == {ENTRY.STORE_ITEM_ID, D306.STORE_ITEM_ID_D306}


def test_translation_preserves_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    """翻译正确性：ExcelInstrumentationSpec 的几何 == RowTableSheetSpec 的几何。"""
    monkeypatch.setattr(P, "_INCLUDE_D306_RELATED_PARTY", True)
    instr = P._instrumentation_of(D306.SPEC_D306)
    assert instr.managed_sheet == D306.SPEC_D306.managed_sheet
    assert instr.first_data_row == D306.SPEC_D306.first_data_row
    assert instr.last_data_row == D306.SPEC_D306.last_data_row
    assert instr.footer_row == D306.SPEC_D306.footer_row
    assert instr.uuid_col == D306.SPEC_D306.uuid_col
    assert instr.table_name == D306.SPEC_D306.table_name
    assert instr.resolved_sheet_key == D306.SPEC_D306.sheet_key

    from app.services.workpaper_sync.sheet_geometry import col_index

    assert col_index(instr.uuid_col) > col_index(instr.managed_last_col)


def test_store_item_ids_have_no_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认状态（三张全开，D3-4 两区各一个 store 键）与只开 D3-6 两种状态下都无重复。"""
    items = P.all_store_item_ids()
    assert len(items) == len(set(items)), f"store item 重复：{items}"
    assert items == _STAGE2_STORE_ITEMS, items

    _switch_all_off(monkeypatch)
    monkeypatch.setattr(P, "_INCLUDE_D306_RELATED_PARTY", True)
    items = P.all_store_item_ids()
    assert len(items) == len(set(items)), f"store item 重复：{items}"
    assert len(items) == 2, items  # D3-det-rows + D3-rp-rows


def test_alignment_guard_reports_exact_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    """对齐计数守卫：specs 与契约 sheets 不对齐 ⇒ fail-closed 且精确报差集（D4-35 事故形态）。"""
    from app.services.workpaper_sync.contracts import parse_contract

    # 对照：开关全关时现算的契约（只有 D3-2 自身一张）与空扩容面对齐。
    _switch_all_off(monkeypatch)
    contract = parse_contract(ENTRY.build_contract_payload(), adapter_id=ENTRY.ADAPTER_ID)
    P.assert_specs_align_with_contract_sheets(contract)

    # 变异：打开 D3-6 开关但契约未加该 sheet（用开关关闭时装配的契约做对照）⇒ 必抛
    monkeypatch.setattr(P, "_INCLUDE_D306_RELATED_PARTY", True)
    with pytest.raises(SyncDomainError) as exc:
        P.assert_specs_align_with_contract_sheets(contract)
    msg = str(exc.value)
    assert D306.SHEET_KEY_D306 in msg, "未精确报出差集"
    assert "attach fail-closed" in msg or "打挂整个 entry" in msg


def test_alignment_guard_catches_disk_contract_missing_a_sheet_when_one_more_switch_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """反方向变异：磁盘契约（默认三张全开）+ 关掉 D3-5 开关 ⇒ 契约有而 spec 缺，精确报 d35。"""
    contract = ENTRY.load_contract_from_disk()  # 🔴 必须在 monkeypatch 之前取
    P.assert_specs_align_with_contract_sheets(contract)

    monkeypatch.setattr(P, "_INCLUDE_D305_LONG_TERM", False)
    with pytest.raises(SyncDomainError) as exc:
        P.assert_specs_align_with_contract_sheets(contract)
    msg = str(exc.value)
    assert "契约有而 spec 缺: ['d35-managed']" in msg, msg


def test_alignment_guard_passes_when_switch_and_contract_are_both_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开关打开后重新装配契约（`build_contract_payload()` 会追加扩容面 sheet）⇒ 对齐守卫通过。

    证明循环层的 `_expansion_sheets_payload()` 追加逻辑与扩容面的 `instrumentation_specs()`
    是同一份灰度开关驱动、不会互相脱钩（D4-35 事故的反面：specs 与 sheets 始终同步增减）。
    """
    from app.services.workpaper_sync.contracts import parse_contract

    _switch_all_off(monkeypatch)
    monkeypatch.setattr(P, "_INCLUDE_D306_RELATED_PARTY", True)
    contract = parse_contract(ENTRY.build_contract_payload(), adapter_id=ENTRY.ADAPTER_ID)
    P.assert_specs_align_with_contract_sheets(contract)


def test_build_contract_payload_unchanged_when_switch_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Property 1 零回归的另一角度：开关全关时契约 `sheets` 只有 D3-2 自身那一项，
    且该项与默认（三张全开）时的 D3-2 项逐字段相等 —— 扩容面只追加、不改 D3-2。

    Task 10 起开关默认 True，本条改为显式 monkeypatch 关开关（原意图不变）。与
    `check_sync_provider_golden_digest.py` 的整段 digest 校验互补：本条直接断言契约结构的
    可读形状，失败时能直接定位到字段，不必反查 digest 不一致的原因。
    """
    d32_when_on = ENTRY.build_contract_payload()["sheets"][0]
    _switch_all_off(monkeypatch)
    payload = ENTRY.build_contract_payload()
    assert len(payload["sheets"]) == 1
    assert payload["sheets"][0]["sheet_key"] == ENTRY.SHEET_KEY
    assert payload["sheets"][0] == d32_when_on, "扩容面开关改变了 D3-2 自身那一项（应只追加）"
