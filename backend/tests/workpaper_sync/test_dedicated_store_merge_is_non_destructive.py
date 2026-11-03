# -*- coding: utf-8 -*-
"""dedicated store merge 的非破坏性：空投影不得清掉既有数据。

为什么单独立一条：注册表常量改名（`STORE_ITEM_ID_D4x_DICT` → `STORE_ITEM_ID_D4x`）之前，
D4-8 / D4-33 / D4-34 / D4-36 这四个 dedicated 块被 `hasattr` 软跳过 —— 旧名只存在于 bridge
的条件导出别名上，不存在于 dedicated 自己的 provider 模块。改名把它们接通，含义不是
「把静默跳过换成显式失败」，而是**它们从此第一次真正接受 OO→HTML 镜像写入**。
所以必须先证明「开始写」不会写坏既有数据。

🔴 判据写到第四版才站得住，前三版都是**夹具造成的误报**，教训记在这里免得再犯：
  1. 统一夹具 `{unmanaged, tables:{rows}}` ⇒ 把 D4-35 误报成缺陷
     （它的契约只返回 `{rows, sampling, periodAmount}`，正确地忽略了不属于自己的键）；
  2. 行统一用 `{"id": ...}` ⇒ 把 D1-memo-rows 误报
     （它声明 `ROW_IDENTITY_KEY = "rowId"`，没有身份键的行被正确跳过）；
  3. 行不带身份键 ⇒ 把 D4-34 / D4-36 误报
     （它们 `if r.get("id")` 过滤无身份行，再按 order 重建列表）。
  所以现在按**每个 item 自己的真实载荷形态与身份键**手写最小非空基线；形态不是猜的，
  是逐个读 merge 源码得出的，并在 `test_handmade_bases_match_the_canonical_shape` 里
  与 merge 自己产出的空载荷对账，夹具漂了就打红。

Spec: workpaper-writeback-data-loss-and-mirror-consistency-closure，design §7.4。
"""
from __future__ import annotations

import copy
import importlib
from typing import Any

import pytest

from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

SENTINEL = "哨兵-不得被清掉"

#: 改名接通的四个；它们是本轮「第一次真正写入」的那批，必须在分母里。
NEWLY_CONNECTED = ("D4-8-products", "D4-33-data", "D4-34-data", "D4-36-data")

#: 按各自契约手写的最小非空基线（形态与身份键逐个读 merge 源码得出）。
HANDMADE_BASES: dict[str, Any] = {
    "D4-33-data": {
        "bizTypes": [{"id": "b1", "name": "业务一"}, {"id": "b2", "name": "业务二"}],
        "months": {"b1": [{"revenue": "100", "cost": "60"} for _ in range(12)]},
        "priorYear": {"b1": SENTINEL},
    },
    "D4-34-data": {
        "rentals": [{"id": "r1", "name": SENTINEL, "amount": "1"}],
        "consults": [{"id": "c1", "name": SENTINEL, "amount": "2"}],
    },
    "D4-36-data": {
        "forward": [{"id": "f1", "voucher": SENTINEL}],
        "backward": [{"id": "b1", "voucher": SENTINEL}],
    },
    "D1-memo-rows": {
        # 身份键是 rowId，不是 id
        "bankRows": [{"rowId": "bk1", "note": SENTINEL}],
        "commercialRows": [{"rowId": "cm1", "note": SENTINEL}],
    },
}

#: 载荷形态尚未手写的 item：只由「幂等」那条覆盖。显式登记而不是静默少测。
NOT_HANDMADE = ("D4-35-data", "D4-9-data", "D4-8-products")


class _EmptyProjection:
    """空投影：没有任何受管字段变化，所以 merge 只应原样带回基线。"""

    def stable_keys(self):
        return ()

    def get(self, _key):  # pragma: no cover - 空投影不会被取值
        return None


def _call(merge: Any, base: Any) -> tuple[Any, int]:
    """dedicated merge 的入参名在 dict / list 形态间不统一，两种都试。"""
    try:
        result = merge(projection=_EmptyProjection(), base_state=base)
    except TypeError:
        result = merge(projection=_EmptyProjection(), base_rows=base)
    return result[0], result[1]


def _count_sentinels(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_sentinels(child) for child in value.values())
    if isinstance(value, list):
        return sum(_count_sentinels(child) for child in value)
    return 1 if value == SENTINEL else 0


def _dedicated_cases() -> list[tuple[str, str, Any]]:
    cases: list[tuple[str, str, Any]] = []
    for adapter_id, plan in sorted(STORE_MERGE_REGISTRY.items()):
        for dedicated in plan.dedicated_items:
            module = importlib.import_module(
                f"app.services.workpaper_sync.{dedicated.provider_module}"
            )
            cases.append((
                adapter_id,
                getattr(module, dedicated.item_id_const),
                getattr(module, dedicated.merge_fn),
            ))
    return cases


CASES = _dedicated_cases()
IDS = [f"{a}:{i}" for a, i, _fn in CASES]
HANDMADE_CASES = [c for c in CASES if c[1] in HANDMADE_BASES]


def test_denominator_covers_the_newly_connected_four() -> None:
    """分母保护：清单塌了或四个没被接通，下面的参数化就会空转变绿。"""
    item_ids = {item_id for _a, item_id, _fn in CASES}
    assert len(CASES) >= 6, CASES
    missing = [item for item in NEWLY_CONNECTED if item not in item_ids]
    assert missing == [], f"改名接通的 item 不在 dedicated 清单里：{missing}"


def test_every_item_is_either_handmade_or_explicitly_registered_as_not() -> None:
    """不许静默少测：每个 dedicated item 要么有手写基线，要么在 NOT_HANDMADE 里登记。"""
    item_ids = {item_id for _a, item_id, _fn in CASES}
    uncovered = sorted(item_ids - set(HANDMADE_BASES) - set(NOT_HANDMADE))
    assert uncovered == [], f"既无手写基线也未登记：{uncovered}"
    stale = sorted((set(HANDMADE_BASES) | set(NOT_HANDMADE)) - item_ids)
    assert stale == [], f"清单有失效条目（item 已不存在）：{stale}"
    overlap = sorted(set(HANDMADE_BASES) & set(NOT_HANDMADE))
    assert overlap == [], f"同时出现在两张清单里：{overlap}"
    # 四个新接通的里，除 D4-8（空载荷自带产品骨架，由幂等覆盖）都要有手写基线
    assert set(NEWLY_CONNECTED) - set(HANDMADE_BASES) == {"D4-8-products"}


@pytest.mark.parametrize("adapter_id, item_id, merge", CASES, ids=IDS)
def test_empty_projection_is_idempotent_on_the_canonical_payload(
    adapter_id: str, item_id: str, merge: Any
) -> None:
    """空投影 + 自己产出的空载荷 ⇒ 原样带回、零写入。"""
    canonical, applied_empty = _call(merge, None)
    assert applied_empty == 0, f"{item_id}: 空投影 + 空基线竟然 applied={applied_empty}"
    again, applied = _call(merge, copy.deepcopy(canonical))
    assert applied == 0, f"{item_id}: 空投影不得产生写入，实得 applied={applied}"
    assert again == canonical, (
        f"{item_id}: 空投影不是幂等的\n before={canonical!r}\n after={again!r}"
    )


@pytest.mark.parametrize(
    "adapter_id, item_id, merge",
    HANDMADE_CASES,
    ids=[f"{a}:{i}" for a, i, _fn in HANDMADE_CASES],
)
def test_handmade_bases_match_the_canonical_shape(
    adapter_id: str, item_id: str, merge: Any
) -> None:
    """夹具防漂：手写基线的顶层键必须就是 merge 自己产出的那些键。

    夹具一漂（provider 改了载荷形态），下面那条就会变成「测了个不相干的结构」。
    """
    canonical, _ = _call(merge, None)
    handmade = HANDMADE_BASES[item_id]
    assert isinstance(canonical, dict) and isinstance(handmade, dict), item_id
    assert set(handmade) == set(canonical), (
        f"{item_id}: 手写基线的键 {sorted(handmade)} 与 merge 产出的 "
        f"{sorted(canonical)} 不一致 —— 夹具漂了"
    )


@pytest.mark.parametrize(
    "adapter_id, item_id, merge",
    HANDMADE_CASES,
    ids=[f"{a}:{i}" for a, i, _fn in HANDMADE_CASES],
)
def test_empty_projection_preserves_a_populated_base(
    adapter_id: str, item_id: str, merge: Any
) -> None:
    """核心判据：空投影作用在非空基线上，必须原样带回（这才是「开始写不会写坏」）。"""
    handmade = HANDMADE_BASES[item_id]
    expected = _count_sentinels(handmade)
    assert expected > 0, f"{item_id}: 手写基线里没有哨兵，判据会空转"
    merged, applied = _call(merge, copy.deepcopy(handmade))
    assert applied == 0, f"{item_id}: 空投影不得产生写入，实得 applied={applied}"
    assert _count_sentinels(merged) == expected, (
        f"{item_id}: 空投影清掉了既有数据 —— 注入 {expected} 个哨兵，剩 "
        f"{_count_sentinels(merged)} 个；merged={merged!r}"
    )
    assert merged == handmade, (
        f"{item_id}: 空投影改动了非空基线\n before={handmade!r}\n after={merged!r}"
    )
