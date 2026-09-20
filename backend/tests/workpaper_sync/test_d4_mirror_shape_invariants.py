"""D4 OO→HTML 镜像形态不变量守卫。

背景（2026-09-20 实证的 P0/P1/P2 缺口）：
- ``oo_to_html._mirror_d4_dual_stores`` 在 ``for item_id, (merged_rows, applied,
  _v, _t) in updates.items()`` 处**硬解包 4-tuple**（生产回写路径，无 try/except）。
- 但 ``merge_projection_into_all_d4_stores`` 的 13 个 item（D4-6/10/11/17/18/19/20×4/
  30/31/32）返回**裸 list / dict**（非 4-tuple）→ 解包 ``ValueError`` 打挂**整个** D4
  entry 的 OO→HTML 回写（此前批已写入的 D4-2/3/… 因 commit 在循环后而一并丢失）。
- D4-8 有 3-tuple 门面 ``merge_d48_from_projection`` 但 oo_to_html 无专用块消费 → 180
  cell 静默永不回写。
- 15 个 item 不在 ``STORE_ITEM_IDS`` → mirror 读 base 恒空 → merge 空基线覆写丢字段。

本守卫钉死三条不变量（纯离线、秒级），是历史 4 次同源缺漏（D4-8 两次 / D4-9 /
D4-15/16）的统一判据面（清册所称「第四维：OO→HTML 消费侧接线」）。

spec: workpaper-sync-static-cell-sheet-writeback（第四维判据补强）
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import oo_to_html as OO  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402


@pytest.fixture(scope="module")
def contract() -> Any:
    D4.assert_contract_file_matches_source()
    return D4.assert_contract_file_matches_source()


@pytest.fixture(scope="module")
def updates(contract: Any) -> dict[str, Any]:
    """空载荷下的 merge 输出——形态与载荷无关，空载荷即可暴露形态缺陷。"""
    projection = D4.build_combined_store_projection({}, contract=contract)
    return D4.merge_projection_into_all_d4_stores(
        projection=projection, base_by_item={}
    )


def _dict_store_item_ids() -> set[str]:
    """oo_to_html 走专用块（不进 rows 4-tuple 循环）的 store item 集合。

    与 ``_mirror_d4_dual_stores`` 的 ``_dict_store_items`` 构造保持同一真源：
    单值 dict 门面 + D4-7 两 item 元组 + D4-8 list 门面。
    """
    names = (
        "STORE_ITEM_ID_D49_DICT",
        "STORE_ITEM_ID_D433_DICT",
        "STORE_ITEM_ID_D434_DICT",
        "STORE_ITEM_ID_D436_DICT",
        "STORE_ITEM_ID_D48_DICT",
        "STORE_ITEM_ID_D435_DICT",
    )
    ids = {str(getattr(D4, n, "") or "") for n in names}
    ids |= {str(s) for s in getattr(D4, "STORE_ITEM_IDS_D47_DEDICATED", ()) or ()}
    ids.discard("")
    return ids


class TestMergeReturnsFourTuple:
    """P0：``merge_projection_into_all_d4_stores`` 每个 value 必须是 4-tuple。"""

    def test_every_value_is_a_four_tuple(self, updates: dict[str, Any]) -> None:
        bad = {
            item_id: type(v).__name__
            for item_id, v in updates.items()
            if not (isinstance(v, tuple) and len(v) == 4)
        }
        assert not bad, (
            "以下 item 返回非 4-tuple，会在 oo_to_html 硬解包处打挂整个 D4 entry 回写："
            f"{bad}"
        )

    def test_hard_unpack_does_not_raise(self, updates: dict[str, Any]) -> None:
        """精确复刻 oo_to_html:2772 的解包，证明生产循环不再抛。"""
        try:
            for _item_id, (_rows, applied, _v, _t) in updates.items():
                _ = applied <= 0
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"mirror 硬解包抛 {type(exc).__name__}: {exc}")


class TestContractSheetsAreConsumable:
    """P1：契约每张 sheet 的 store item 必须能被 OO→HTML 消费（rows 循环或专用块）。"""

    def test_every_store_item_reachable(
        self, contract: Any, updates: dict[str, Any]
    ) -> None:
        rows_loop_ids = set(D4.STORE_ITEM_IDS)
        dedicated_ids = _dict_store_item_ids()
        reachable = rows_loop_ids | dedicated_ids

        contract_store_ids: set[str] = set()
        for sheet in contract.sheets:
            for table in sheet.tables:
                for field in table.fields:
                    sid = getattr(field, "store_item_id", None)
                    if sid:
                        contract_store_ids.add(str(sid))

        unreachable = contract_store_ids - reachable
        assert not unreachable, (
            "以下契约 store item 既不在 STORE_ITEM_IDS(rows 循环) 也不在专用块集合，"
            f"OO→HTML 无路径消费（静默不回写）：{sorted(unreachable)}"
        )

    def test_d4_8_has_dedicated_consumption_block(self) -> None:
        """D4-8 门面存在则 oo_to_html 必须真消费它（否则 180 cell 永不回写）。"""
        if not hasattr(D4, "merge_d48_from_projection"):
            pytest.skip("D4-8 未启用")
        src = inspect.getsource(OO)
        assert "STORE_ITEM_ID_D48_DICT" in src, (
            "oo_to_html 未引用 STORE_ITEM_ID_D48_DICT —— D4-8 无专用块，oo→html 静默丢弃"
        )
        assert "merge_d48_from_projection" in src, (
            "oo_to_html 未调用 merge_d48_from_projection —— D4-8 专用块缺失"
        )


class TestUpdatesSubsetOfStoreItems:
    """P2：merge 产出的 item 必须都在 STORE_ITEM_IDS（否则 mirror 读 base 恒空）。"""

    def test_updates_keys_subset_of_store_item_ids(
        self, updates: dict[str, Any]
    ) -> None:
        store_ids = set(D4.STORE_ITEM_IDS)
        missing = sorted(set(updates) - store_ids)
        assert not missing, (
            "以下 item 由 merge 产出但不在 STORE_ITEM_IDS，mirror 构造 base 时读不到"
            f"（基线恒空 → 覆写丢 HTML-only 字段/行）：{missing}"
        )
