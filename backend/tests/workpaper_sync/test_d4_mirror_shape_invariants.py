"""D4 OO→HTML 镜像形态不变量守卫。

背景（2026-09-20 实证的 P0/P1/P2 缺口）：
- ``store_mirror.mirror_projection_into_store`` 在 ``for item_id, (merged_rows, applied,
  _v, _t) in updates.items()`` 处**硬解包 4-tuple**（生产回写路径，无 try/except）。
  🔴 该硬解包原在 ``oo_to_html._mirror_d4_dual_stores``，spec
  workpaper-sync-managed-row-convergence Task 3 把三个 ``_mirror_*`` 抽到会话无关模块
  ``store_mirror``（OO callback 与 adopt-substrate 共用，避免第二真源），
  ``oo_to_html`` 侧只剩薄转发。下方判据的扫描目标已随之改为 ``store_mirror``。
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
        # 🔴 锚点随执行层迁移（spec workpaper-sync-managed-row-convergence Task 3）：
        # 三个 _mirror_* 方法已从 oo_to_html 抽到会话无关模块 store_mirror（OO callback 与
        # adopt-substrate 共用，避免第二真源）。判据意图不变（D4-8 专用块真存在），扫描目标
        # 改为逻辑真身 store_mirror，并额外断言 OO 侧确有薄转发（防转发被误删）。
        from app.services.workpaper_sync import store_mirror as MIRROR

        src = inspect.getsource(MIRROR)
        assert "STORE_ITEM_ID_D48_DICT" in src, (
            "store_mirror 未引用 STORE_ITEM_ID_D48_DICT —— D4-8 无专用块，oo→html 静默丢弃"
        )
        assert "merge_d48_from_projection" in src, (
            "store_mirror 未调用 merge_d48_from_projection —— D4-8 专用块缺失"
        )
        assert "mirror_projection_into_store" in inspect.getsource(OO), (
            "oo_to_html 不再转发到 store_mirror —— OO callback 落地将不镜像 store，§9.6 回归"
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


class TestD44AdjustmentMirrorWiring:
    """D4-4 营业收入调整分录汇总的消费侧接线（spec d4-4-… Task 7 / Task 8）。

    上面三类守卫是**泛化**的（对所有 item 断言），D4-4 会被自动覆盖 —— 但泛化守卫
    无法回答「D4-4 到底走 rows 循环还是专用块」「漏登记 RAW_PAYLOAD 会怎样」这两个
    本表特有问题。这一类补上，并把两条**变异反证**实做（tasks.md Task 8 要求）。
    """

    def _d44(self):
        from app.services.workpaper_sync.phase5_d4_adjustment_sheet import (
            STORE_ITEM_ID_D44,
            TABLE_KEY_D44,
        )

        return STORE_ITEM_ID_D44, TABLE_KEY_D44

    def test_d44_is_reachable_by_rows_loop(self) -> None:
        """T7：D4-4 必须出现在 rows 循环的基础集合里。

        `store_mirror` 的 `_rows_loop_item_ids` 取 `all_store_item_ids()`
        （回退 `STORE_ITEM_IDS`），所以这里两个口径都断言。
        """
        item_id, _ = self._d44()
        assert item_id in set(D4.STORE_ITEM_IDS), (
            f"{item_id} 不在 STORE_ITEM_IDS ⇒ mirror 读 base 恒空，merge 会用空基线覆写"
        )
        all_ids_fn = getattr(D4, "all_store_item_ids", None)
        if callable(all_ids_fn):
            assert item_id in set(all_ids_fn()), (
                f"{item_id} 不在 all_store_item_ids() ⇒ rows 循环取不到它的 base"
            )

    def test_d44_is_not_a_dict_store_item(self) -> None:
        """T7：D4-4 是 **list 形态** ⇒ 走既有 rows 循环，**不得**进专用块排除集。

        进了排除集的后果：rows 循环跳过它 ⇒ base 恒 `[]` ⇒ 而又没有专用块消费
        ⇒ 回写静默丢失（D4-8 的 180 cell 就是这么丢的）。
        """
        item_id, _ = self._d44()
        assert item_id not in _dict_store_item_ids(), (
            f"{item_id} 被放进了 dict-store 排除集，但它没有专用块 ⇒ 回写会静默丢失"
        )

    def test_d44_merge_value_is_four_tuple_with_payload(self, contract: Any) -> None:
        """带真实载荷跑一遍（空载荷验形态，这里验语义）。"""
        item_id, table_key = self._d44()
        rows = [{"rowId": "d4a-t-1", "description": "d", "debitAmount": 1.0}]
        projection = D4.build_combined_store_projection({item_id: rows}, contract=contract)
        updates = D4.merge_projection_into_all_d4_stores(
            projection=projection, base_by_item={item_id: rows}
        )
        got = updates.get(item_id)
        assert isinstance(got, tuple) and len(got) == 4, (
            f"{item_id} 的 merge 返回不是 4-tuple 而是 {type(got).__name__}"
        )
        merged_rows, applied, _visited, touched = got
        assert applied == 10, f"applied 应为受管字段数 10，实得 {applied}"
        assert touched == {"d4a-t-1"}
        assert len(merged_rows) == 1

    def test_hard_unpack_of_d44_does_not_raise(self, contract: Any) -> None:
        """复刻 `store_mirror` 的硬解包语句本身，确认不抛。"""
        item_id, _ = self._d44()
        rows = [{"rowId": "d4a-t-1", "description": "d"}]
        projection = D4.build_combined_store_projection({item_id: rows}, contract=contract)
        updates = D4.merge_projection_into_all_d4_stores(
            projection=projection, base_by_item={item_id: rows}
        )
        # 与 store_mirror 里那一行逐字同构
        for _iid, (_merged_rows, _applied, _visited, _touched) in updates.items():
            pass

    def test_mutation_dropping_normalize_reproduces_value_error(
        self, contract: Any, monkeypatch
    ) -> None:
        """🔴 变异反证 1（Task 8 要求实做）：monkeypatch 掉归一 → 复现非 4-tuple + ValueError。

        证明「归一这一步是必需的」而不是可有可无：去掉它，D4-4 的 merge 返回裸 list，
        `store_mirror` 的硬解包当场 `ValueError` ⇒ 打挂**整个 entry** 的回写。
        """
        item_id, _ = self._d44()
        monkeypatch.setattr(
            D4, "_normalize_merge_updates", lambda raw, *, projection: dict(raw), raising=True
        )
        rows = [{"rowId": "d4a-t-1", "description": "d"}]
        projection = D4.build_combined_store_projection({item_id: rows}, contract=contract)
        updates = D4.merge_projection_into_all_d4_stores(
            projection=projection, base_by_item={item_id: rows}
        )
        got = updates.get(item_id)
        assert not (isinstance(got, tuple) and len(got) == 4), (
            "去掉归一后 D4-4 仍是 4-tuple ⇒ 说明它不经过归一，本条判据无区分力"
        )
        with pytest.raises(ValueError):
            for _iid, (_a, _b, _c, _d) in updates.items():
                pass

    def test_mutation_dropping_raw_payload_registration_collapses_applied(
        self, contract: Any, monkeypatch
    ) -> None:
        """🔴 变异反证 2：摘掉 `_RAW_PAYLOAD_ITEM_TABLE_KEYS` 登记 → `applied` 塌成 0。

        这一条是实施中实测发现的、design 未覆盖的判据：

        `merge_projection_into_all_d4_stores` **末尾自己就调了**归一，所以「归一后是
        4-tuple」这个断言对「登记生效」与「登记冗余」**无法区分**（重复归一是幂等透传）。
        必须把登记摘掉才能看出差别。

        `applied=0` 的真实后果不是报错，而是 `store_mirror` 的护栏
        ``if applied <= 0 and base_rows: continue`` 把 D4-4 的回写**静默丢掉**
        （不报错、不落库）—— 比 ValueError 难查得多。
        """
        item_id, table_key = self._d44()
        rows = [{"rowId": "d4a-t-1", "description": "d"}]
        projection = D4.build_combined_store_projection({item_id: rows}, contract=contract)
        raw_bare = {item_id: rows}  # 裸 list，即 provider 的真实返回形态

        with_reg = D4._normalize_merge_updates(raw_bare, projection=projection)
        applied_good = with_reg[item_id][1]

        mutated = {
            k: v for k, v in D4._RAW_PAYLOAD_ITEM_TABLE_KEYS.items() if k != item_id
        }
        monkeypatch.setattr(D4, "_RAW_PAYLOAD_ITEM_TABLE_KEYS", mutated, raising=True)
        without_reg = D4._normalize_merge_updates(raw_bare, projection=projection)
        applied_bad = without_reg[item_id][1]

        assert applied_good == 10, f"带登记时 applied 应为 10，实得 {applied_good}"
        assert applied_bad == 0, (
            f"摘掉登记后 applied 仍为 {applied_bad}（非 0）⇒ 登记是冗余的，"
            "或者本条判据无区分力，需重新裁决"
        )

    def test_raw_payload_registration_maps_to_the_right_table_key(self) -> None:
        """登记的 table_key 必须与契约里的一致，否则 applied 统计会落空。"""
        item_id, table_key = self._d44()
        assert D4._RAW_PAYLOAD_ITEM_TABLE_KEYS.get(item_id) == (table_key,)
        sheet = next(
            s for s in D4.build_contract_payload()["sheets"] if s["sheet_key"] == "d44-managed"
        )
        assert sheet["tables"][0]["table_key"] == table_key
