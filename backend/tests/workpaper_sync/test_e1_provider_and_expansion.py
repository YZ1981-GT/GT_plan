# -*- coding: utf-8 -*-
"""E1 provider 与扩容判据（E1 Tasks 3 / 7 / 13 / 14）。

spec: e1-sync-coverage-and-first-canary · Requirements 1.2 / 1.5 / 2.1 / 3.3 / 4.5

═══ 判据面 ═══

* **Task 7**：provider 可 import、模板哨兵校验通过、选型守卫在真 manifest 上核四条事实。
* **E1-P1 红判据**（Task 3）：canary 未通时 `migrationState` / reasonCodes 必红 ——
  断言 slice 现状是 `legacy_fake_bidirectional` + `adapter_id=None`（**现状必红**，
  记录红的形态；转绿归 Task 9 的发布链五环，卡 upstream_gap）。
* **Task 13/14**：逐张开关生效、受管区按预期增长、静态区寄生在首个动态 spec 上。
* **需求 4.5**：跨册键降级行为已显式登记（不得因缺失判成空/0）。
* **需求 3.3**：两方向 store item 单一口径、无重复。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_e1_02_cash_detail as E102
from app.services.workpaper_sync import phase5_e1_04_digital as E104
from app.services.workpaper_sync import phase5_e1_11_commitment as E111
from app.services.workpaper_sync import phase5_e1_monetary_fund as E

_SLICE = _BACKEND / "data" / "workpaper_sync_e_cycle_manifest_slice.json"


# ═══════════════════════════════════════════════════════════════════════════
# Task 7：provider 基础
# ═══════════════════════════════════════════════════════════════════════════


def test_template_sentinel_matches_real_bytes() -> None:
    """模板字节哨兵必须与磁盘实测一致（`backend/wp_templates/` 运行时只读）。"""
    data = E.read_authoritative_template()  # 内部比对哨兵，不符即抛
    assert len(data) > 0
    assert E.authoritative_template_path().name.startswith("E1-1至E1-11")


def test_identity_constants_are_frozen_from_slice() -> None:
    """entry_id / profile 与 E 循环 slice 逐字一致（Task 1 的 slice 核对结论）。"""
    payload = json.loads(_SLICE.read_text(encoding="utf-8"))
    entries = payload["independent_entries"]
    ids = [e.get("entry_id") for e in entries]
    assert E.ENTRY_ID in ids, f"slice 里没有 {E.ENTRY_ID}"
    entry = next(e for e in entries if e.get("entry_id") == E.ENTRY_ID)
    assert entry.get("scenario_profile_id") == E.EXPECTED_PROFILE_ID


def test_adapter_id_shape_is_registry_compatible() -> None:
    """adapter_id 形态必须能被注册表的 looks_like_adapter_id 识别（否则回写会被跳过）。"""
    from app.services.workpaper_sync.store_item_registry import looks_like_adapter_id

    assert looks_like_adapter_id(E.ADAPTER_ID), (
        f"{E.ADAPTER_ID!r} 不符 adapter_id 形态 ⇒ oo_to_html 的三态入口会当它「不是 adapter」"
        "而静默跳过镜像（D4-35 恒空的同款后果）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# E1-P1 红判据（Task 3）：canary 未通时的现状形态
# ═══════════════════════════════════════════════════════════════════════════


def test_e1p1_current_state_is_red_legacy_fake_bidirectional() -> None:
    """🔴 E1-P1 先打红：slice 实测 E1 仍是 `legacy_fake_bidirectional` + `adapter_id=None`。

    转绿归 Task 9 的契约发布链五环，而第③环（published representation）是 umbrella BP-61-1
    登记的**平台级约束**（三表近空，186 个 planned entry 一个都注册不上）⇒ 如实标 upstream_gap，
    **不得**以合成测试冒充真栈（spec Task 9 明令）。
    """
    payload = json.loads(_SLICE.read_text(encoding="utf-8"))
    entry = next(
        e for e in payload["independent_entries"] if e.get("entry_id") == E.ENTRY_ID
    )
    assert entry.get("migration_state") == "legacy_fake_bidirectional", (
        "若已变成 adapter_registered，说明发布链已通 ⇒ 本红判据应转为绿判据并更新 spec 状态"
    )
    assert entry.get("adapter_id") is None, "adapter 尚未注册（E1-P1 的红形态）"


# ═══════════════════════════════════════════════════════════════════════════
# Task 13/14：逐张开关与受管区增长
# ═══════════════════════════════════════════════════════════════════════════


def test_switches_off_equals_zero_managed_regions() -> None:
    assert E._INCLUDE_E102_CASH_DETAIL is False
    assert E._INCLUDE_E104_DIGITAL is False
    assert E._INCLUDE_E111_COMMITMENT_STATIC is False
    assert E.instrumentation_specs() == ()
    assert E.all_store_item_ids() == ()


def test_enabling_canary_adds_one_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(E, "_INCLUDE_E102_CASH_DETAIL", True)
    specs = E.instrumentation_specs()
    assert len(specs) == 1
    assert specs[0].resolved_sheet_key == E102.SHEET_KEY_E102
    assert E.all_store_item_ids() == (E102.STORE_ITEM_ID_E102,)


def test_enabling_second_sheet_adds_another_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task 13：第二张（E1-4）接入后受管区 1→2，且**无需改框架层**。"""
    monkeypatch.setattr(E, "_INCLUDE_E102_CASH_DETAIL", True)
    monkeypatch.setattr(E, "_INCLUDE_E104_DIGITAL", True)
    specs = E.instrumentation_specs()
    assert len(specs) == 2
    keys = {s.resolved_sheet_key for s in specs}
    assert keys == {E102.SHEET_KEY_E102, E104.SHEET_KEY_E104}
    assert set(E.all_store_item_ids()) == {
        E102.STORE_ITEM_ID_E102, E104.STORE_ITEM_ID_E104
    }


def test_enabling_static_region_parasites_on_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task 14：static_region 寄生在首个动态 spec 的 static_sheets 上（不单独成 spec）。"""
    monkeypatch.setattr(E, "_INCLUDE_E102_CASH_DETAIL", True)
    monkeypatch.setattr(E, "_INCLUDE_E111_COMMITMENT_STATIC", True)
    specs = E.instrumentation_specs()
    assert len(specs) == 1, "静态区不占一个 instrumentation spec（它寄生在动态 spec 上）"
    static = specs[0].static_sheets
    assert static, "静态区未寄生"
    assert static[0]["region_kind"] == "static"
    assert static[0]["defined_name"] == E111.DEFINED_NAME_E111
    # store item 含 E1-11 的三条 fixed_text 键
    items = set(E.all_store_item_ids())
    assert set(E111.STORE_ITEM_IDS_E111) <= items


def test_static_region_alone_yields_no_instrumentation_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 边界：只开静态区而无动态区 ⇒ 无处寄生 ⇒ specs 为空（须显式知道这个后果）。

    这不是 bug 而是 `static_sheets` 的寄生机制决定的：它是挂在动态 primary spec 上的字段。
    ⇒ 接入顺序必须**先 canary（动态）再 static_region**，spec Task 14 排在 Task 8 之后正是此因。
    """
    monkeypatch.setattr(E, "_INCLUDE_E111_COMMITMENT_STATIC", True)
    assert E.instrumentation_specs() == (), (
        "无动态 spec 时静态区无处寄生 —— 接入顺序须先动态后静态"
    )
    # 但 store item 清单仍会包含它（出方向靠 store 键而非 instrumentation）
    assert set(E111.STORE_ITEM_IDS_E111) <= set(E.all_store_item_ids())


def test_store_item_ids_no_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(E, "_INCLUDE_E102_CASH_DETAIL", True)
    monkeypatch.setattr(E, "_INCLUDE_E104_DIGITAL", True)
    monkeypatch.setattr(E, "_INCLUDE_E111_COMMITMENT_STATIC", True)
    items = E.all_store_item_ids()
    assert len(items) == len(set(items)), f"重复：{items}"
    assert len(items) == 5  # cash-detail + digital + 3 条 E1-11 fixed_text


# ═══════════════════════════════════════════════════════════════════════════
# 需求 4.5：跨册键降级行为
# ═══════════════════════════════════════════════════════════════════════════


def test_cross_volume_key_degradation_is_declared() -> None:
    """🔴 E1-1 读的 `E1-accrued-interest-rows` 属第 3 册 ⇒ 本 entry 内永远读不到。

    必须显式登记「上游未受管」而非让该格默默变成空/0（否则审计师会以为该项真为零）。
    """
    assert "E1-accrued-interest-rows" in E.CROSS_VOLUME_KEYS
    reason = E.CROSS_VOLUME_KEYS["E1-accrued-interest-rows"]
    assert "第 3 册" in reason
    assert "而非空" in reason or "不得" in reason or "而非空/0" in reason


def test_only_first_volume_is_covered() -> None:
    """裁决 H2：本 entry 只覆盖第一册；后四册需新建宿主另立 entry。"""
    assert "E1-1至E1-11" in E.TEMPLATE_RELATIVE_PATH
    # 本 entry 声明的三张 sheet 全在第一册
    import glob

    import openpyxl

    p = [x for x in glob.glob(str(_BACKEND / "wp_templates" / "E" / "*.xlsx"))
         if "E1-1至E1-11" in x][0]
    names = set(openpyxl.load_workbook(p, read_only=True).sheetnames)
    for sheet in (
        E102.MANAGED_SHEET_E102, E104.MANAGED_SHEET_E104, E111.MANAGED_SHEET_E111
    ):
        assert sheet in names, f"{sheet} 不在第一册里"
