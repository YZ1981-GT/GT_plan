# -*- coding: utf-8 -*-
"""`check_store_item_two_way_parity.py` 门禁自测（缺陷③ 的棘轮基线）。

spec: d1-sync-row-table-engine-and-d1-coverage · 缺陷③
Requirements 3.1 / 3.3 / 7.3 / 7.4

═══ 这个卡点守的缺陷（2026-09-28 实测）═══

42 个已注册 adapter 里 **14 个**「声明了 N 个 store item，但装配链只看得到 1 个」，
合计 **48 个 item** 在出方向不可见。D1 最大：声明 18 / 可见 1 / 缺口 17。

根因是两方向各自的取法与「声明放在哪」不匹配：
  * 出方向 `store_projection_response` 的门槛是 `len(STORE_ITEM_IDS) > 1`（复数常量），
    entry 模块只有单数常量时，即使它暴露 `all_store_item_ids()` 也进不了 combined 分支；
  * 回方向 `store_mirror` 的分派点是 `plan.dual_store_fn`，为空则走单 item 路径、
    只读 `bridge.STORE_ITEM_ID`。
  * 而 D1/D3/D5/D6/D7 的扩容声明全在**伴生模块** `phase5_*_expansion` 里，两方向都不读它。

⇒ 伴生模块的 `all_store_item_ids()` 写得完整、per-sheet 判据全绿、golden digest 全绿，
  但**没有任何生产代码调用它**。这是「声明层封顶 ≠ 接入本体闭环」的精确断口。

═══ 一条必须钉住的方法论 ═══

本卡点的回方向复刻**第一版是错的**：直接套了 `_mirror_dual_stores` 内部那段
`getattr(bridge, "all_store_item_ids")`，于是把 b60/d2/g7/h1 判成「回方向 AttributeError」。
但它们是真栈验证过的（真库 D2 gen=2 / G7 gen=6 / H1 gen=2），真会抛早就崩了 —— 这个
**自相矛盾**才是发现复刻错误的线索。正确分派点在外层 `if plan.dual_store_fn:`。
`test_inbound_replica_dispatches_on_dual_store_fn` 把这条钉死，防回退。

覆盖：
  1. 现状通过 + 分母非空（防收集器坏掉恒绿）。
  2. 变异反证：出现一个**未登记**的断口 ⇒ 必红。
  3. 失效基线反证：基线里放一条已合规的 adapter ⇒ 必红。
  4. 基线纪律：恰 14 条、每条有归属 lane。
  5. D1 的缺口规模钉死 17（本 spec tasks 25~29 的硬前置；数字变了必须来改本判据）。
  6. 复刻正确性：回方向必须按 `plan.dual_store_fn` 分派。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_store_item_two_way_parity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_check_store_item_two_way_parity", _CHECK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_current_state_passes_with_nonempty_denominator() -> None:
    report = _load_module().run()
    assert report["ok"], (
        f"新增断口 {[r['adapter_id'] for r in report['new_unwired']]} / "
        f"失效基线 {report['stale_known_unwired']}"
    )
    assert report["adapters_checked"] >= 40, (
        f"只检查了 {report['adapters_checked']} 个 adapter —— 注册表读取可能坏了（恒绿风险）"
    )
    assert report["known_unwired_hit"], "基线一条都没命中 ⇒ 要么全修好了（该删基线）要么判据坏了"


def test_mutation_new_unwired_adapter_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """变异反证：把 D6 从基线里摘掉 ⇒ 它必须变成「新增断口」而打红。

    🔴 原来用 D1 做变异源，2026-09-28 D1 已接通、从基线出列 ⇒ 换成仍在基线里、
    缺口最大的 D6（声明 8 / 可见 1）。
    """
    mod = _load_module()
    victim = "d6.contract_assets_detail"
    without = {k: v for k, v in mod.KNOWN_UNWIRED.items() if k != victim}
    monkeypatch.setattr(mod, "KNOWN_UNWIRED", without)
    report = mod.run()
    assert not report["ok"], "基线漏登记时必须打红"
    ids = [r["adapter_id"] for r in report["new_unwired"]]
    assert victim in ids, ids


def test_stale_baseline_entry_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """失效基线反证：放一条已合规的 adapter 进基线 ⇒ 必红并点名。

    选 `f1.prepayment_detail`（现算 declared == visible，已合规）。
    """
    mod = _load_module()
    monkeypatch.setitem(
        mod.KNOWN_UNWIRED,
        "f1.prepayment_detail",
        "归属 lane：合成的失效条目，用于反证基线不得躺着失效项。",
    )
    report = mod.run()
    assert not report["ok"]
    assert "f1.prepayment_detail" in report["stale_known_unwired"], report[
        "stale_known_unwired"
    ]


def test_baseline_is_exactly_thirteen_with_owning_lanes() -> None:
    """基线恰 13 条（2026-09-28：D1 接通后从 14 变短，棘轮只许往这个方向走）。"""
    mod = _load_module()
    assert len(mod.KNOWN_UNWIRED) == 13, (
        f"基线应恰 13 条，实得 {len(mod.KNOWN_UNWIRED)}：{sorted(mod.KNOWN_UNWIRED)}。"
        "变长 ⇒ 有新断口被放行；变短 ⇒ 请同时更新本判据的期望数。"
    )
    assert "d1.notes_receivable_detail" not in mod.KNOWN_UNWIRED, (
        "D1 已于 2026-09-28 接通（声明 18 / 两方向各可见 18），不得回填进基线"
    )
    for adapter_id, reason in mod.KNOWN_UNWIRED.items():
        assert "归属 lane" in reason, f"{adapter_id} 未写归属 lane"


def test_d1_is_fully_wired_in_both_directions() -> None:
    """🔴 D1 两方向全通的正面钉子（2026-09-28 接通，防回退）。

    接通前：声明 18 / 出方向可见 1 / 回方向可见 1（缺口 17，全仓最大）。
    接通后三条缺一不可 —— 少任何一条都会退回「声明生效但数据不通」：
      ① entry 模块暴露 `all_store_item_ids()`（薄转发伴生模块，单源）
      ② PEP 562 `__getattr__` 延迟暴露复数 `STORE_ITEM_IDS`
         （出方向 combined 分支的门槛是 `len(STORE_ITEM_IDS) > 1`，不是「有没有 all_store_item_ids」）
      ③ `build_combined_store_projection` + `merge_projection_into_all_d1_stores`
         + 注册表 `dual_store_fn`/`merge_all_fn`
    """
    import importlib

    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    mod = _load_module()
    entry = importlib.import_module(
        "app.services.workpaper_sync.phase5_d1_notes_receivable"
    )
    plan = STORE_MERGE_REGISTRY["d1.notes_receivable_detail"]

    # ① + ②
    assert callable(getattr(entry, "all_store_item_ids", None))
    plural = getattr(entry, "STORE_ITEM_IDS", ())
    # 🔴 期望值按静态第三区开关**派生**，不写死（2026-09-28）。
    #    T7 裁决 A 把 `_INCLUDE_D104_NOTETYPE_STATIC` 翻 False（D1-4 票据种类小计撤回
    #    受管面），store item 从 18 掉到 17；本条原先写死 18 ⇒ 撤回态下假红。
    #    写死 17 又会在开关翻回 True 时假绿，所以两边都不写死。
    #    开关状态本身的权威断言在 `test_d104_static_region_excluded.py`。
    from app.services.workpaper_sync import phase5_d1_expansion as _exp

    expected = 18 if _exp._INCLUDE_D104_NOTETYPE_STATIC else 17
    assert len(plural) == expected, (
        f"复数常量应现算 {expected} 个（静态第三区开关="
        f"{_exp._INCLUDE_D104_NOTETYPE_STATIC}），实得 {len(plural)}"
    )
    assert set(plural) == set(entry.all_store_item_ids()), "复数常量与单一口径必须同源"
    # ③
    assert callable(getattr(entry, "build_combined_store_projection", None))
    assert callable(getattr(entry, "merge_projection_into_all_d1_stores", None))
    assert plan.dual_store_fn, "dual_store_fn 为空 ⇒ 回方向退回单 item 路径"
    assert plan.merge_all_fn == "merge_projection_into_all_d1_stores"

    # 两方向复刻结果必须相等且等于声明全集
    outbound = set(mod._visible_to_outbound(entry))
    inbound = set(mod._visible_to_inbound(entry, plan))
    declared = set(entry.all_store_item_ids())
    assert outbound == inbound == declared, (
        f"出 {len(outbound)} / 回 {len(inbound)} / 声明 {len(declared)}；"
        f"出-only={sorted(outbound - inbound)} 回-only={sorted(inbound - outbound)}"
    )


def test_d1_static_region_without_contract_table_is_registered() -> None:
    """🔴 无契约 table 的 store item 必须显式登记，不得藏在一个 `continue` 里。

    判据**不写死名单内容**，只锁「名单与契约互为补集」这条不变式：
      * 名单里的每一项，其 table 必须**真的不在**契约里（否则该条登记已失效，应删）；
      * `D1-bd-notetype-rows`（D1-4 第三区）作为可复算锚点：它**要么**在名单里
        （断口仍在）**要么** `bad_debt_notetype_rows` 已进契约（断口已修），不许两头都不落。

    🔴 2026-09-28 判据陈旧修正：原断言写死
    `== ("D1-bd-notetype-rows",)` + 「该 table 不在契约里」。第三区的静态受管区通路
    随后**已建成**（契约里有 `bad_debt_notetype_rows` 2 固定行 × 9 列 = 18 field，
    投影/回写走 `phase5_d1_04_bad_debt.build_notetype_store_projection` /
    `merge_projection_into_notetype_rows`），常量随之清空为 `()` ⇒ 两条断言同时翻转、
    恒红。生产代码那边的注释已写明「本常量保留为空元组并配反向断言」——
    本函数就是那个反向断言，改为按不变式判而不是按快照判，断口再出现也不必回头改判据。
    """
    import importlib

    entry = importlib.import_module(
        "app.services.workpaper_sync.phase5_d1_notes_receivable"
    )
    contract_tables = {
        t["table_key"]
        for sheet in entry.build_contract_payload()["sheets"]
        for t in (sheet.get("tables") or [])
    }
    assert contract_tables, "契约里一张 table 都没有 ⇒ 装配层解析失败，不是「断口」"

    # 🔴 2026-09-28 第二次修正：原二分法漏了**第三态**。
    #
    #    原不变式是「要么在断口名单、要么已进契约，不许两头都不落」。T7 裁决 A 把
    #    `_INCLUDE_D104_NOTETYPE_STATIC` 翻 False 之后出现了第三种情形：
    #    **整个静态第三区被撤回**，`D1-bd-notetype-rows` 这个 store item 根本不存在 ——
    #    既不在断口名单（没有断口要登记），也不在契约（整条通路同源空转）。
    #    二分法在这一态下必然报「两头都不落」，那是判据没覆盖新状态，不是生产缺陷。
    #
    #    三态判据：撤回态下该 item 必须**彻底不存在**（这本身是个强断言 —— 它禁止
    #    「开关关了但 store item 还挂着」这种半撤回状态）；非撤回态仍走原二分法。
    from app.services.workpaper_sync import phase5_d1_expansion as _exp

    if not _exp._INCLUDE_D104_NOTETYPE_STATIC:
        assert "D1-bd-notetype-rows" not in set(entry.all_store_item_ids()), (
            "静态第三区已按 T7 裁决 A 撤回，但 `D1-bd-notetype-rows` 还在 store item "
            "清单里 —— 存在绕过 `_INCLUDE_D104_NOTETYPE_STATIC` 的第二个装配点"
        )
        assert "bad_debt_notetype_rows" not in contract_tables, (
            "静态第三区已撤回，但契约里还有 `bad_debt_notetype_rows` ⇒ 契约与开关脱钩"
        )
        assert tuple(entry.STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE) == (), (
            "整个区都撤回了，断口名单里不该还留着它的登记"
        )
        return

    violations = _no_contract_table_violations(
        tuple(entry.STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE), contract_tables
    )
    assert violations == [], violations


#: `store_item_id → 契约里对应的 table_key`（判据要核验名单项，就必须知道查哪张表）。
_ITEM_TABLE_KEY = {"D1-bd-notetype-rows": "bad_debt_notetype_rows"}


def _no_contract_table_violations(
    registered: tuple[str, ...], contract_tables: set[str]
) -> list[str]:
    """「名单 与 契约」互为补集这条不变式的违规清单（纯函数，便于双向变异）。

    三类违规：
      1. 名单项没登记 item→table_key 映射 ⇒ 本判据核验不了它；
      2. 名单项的 table **已进契约** ⇒ 该条登记躺着失效，应删并接入投影；
      3. 锚点第三区「既不在名单、也没进契约」⇒ 断口被静默吞掉。
    """
    out: list[str] = []
    for item_id in registered:
        table_key = _ITEM_TABLE_KEY.get(item_id)
        if table_key is None:
            out.append(f"{item_id}: 未登记 item→table_key 映射，请补 _ITEM_TABLE_KEY")
            continue
        if table_key in contract_tables:
            out.append(
                f"{item_id}: {table_key} 已进契约 ⇒ 请从 "
                "STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE 删除并接入投影"
            )

    anchor_item, anchor_table = "D1-bd-notetype-rows", "bad_debt_notetype_rows"
    in_list = anchor_item in registered
    in_contract = anchor_table in contract_tables
    if not (in_list ^ in_contract):
        out.append(
            f"{anchor_item} 状态不自洽：在名单={in_list} / 进契约={in_contract}；"
            "两者必须恰好一个为真"
        )
    return out


@pytest.mark.parametrize(
    ("registered", "contract_tables", "expect_clean"),
    [
        # 断口已修：名单空 + table 进契约
        ((), {"bad_debt_notetype_rows", "other"}, True),
        # 断口仍在：名单有它 + table 不在契约
        (("D1-bd-notetype-rows",), {"other"}, True),
        # 名单躺着失效：两头都有
        (("D1-bd-notetype-rows",), {"bad_debt_notetype_rows"}, False),
        # 断口被静默吞掉：两头都没有
        ((), {"other"}, False),
        # 名单项无映射：核验不了
        (("D1-unknown-rows",), {"bad_debt_notetype_rows"}, False),
    ],
)
def test_no_contract_table_invariant_both_directions(
    registered, contract_tables, expect_clean
) -> None:
    """双向变异：两种自洽态必须放行，三种不自洽态必须逐一报出。

    没有这组用例，上面那条会退化成「名单空就绿」的永绿装饰
    —— 2026-09-28 该判据正是因为写死名单快照而恒红，修完必须证明它还咬人。
    """
    violations = _no_contract_table_violations(registered, contract_tables)
    assert (violations == []) is expect_clean, violations


def test_inbound_replica_dispatches_on_dual_store_fn() -> None:
    """🔴 回方向复刻必须按 `plan.dual_store_fn` 分派（第一版错法的防回退钉子）。

    错法是无条件套 `_mirror_dual_stores` 内部的 `all_store_item_ids()` 取法，
    那会把 `dual_store_fn` 为空的家（b60/d2/g7/h1）误判成回方向拿不到东西。
    """
    mod = _load_module()

    class _FakeBridge:
        STORE_ITEM_ID = "X-single"
        STORE_ITEM_IDS = ("X-a", "X-b", "X-c")

        @staticmethod
        def all_store_item_ids():
            return ("X-a", "X-b", "X-c", "X-d")

    class _PlanNoDual:
        dual_store_fn = None
        dedicated_items = ()

    class _PlanWithDual:
        dual_store_fn = "_mirror_x_dual_stores"
        dedicated_items = ()

    assert mod._visible_to_inbound(_FakeBridge, _PlanNoDual) == ("X-single",), (
        "dual_store_fn 为空时必须只看单数常量（走单 item 路径）"
    )
    assert set(mod._visible_to_inbound(_FakeBridge, _PlanWithDual)) == {
        "X-a",
        "X-b",
        "X-c",
        "X-d",
    }, "dual_store_fn 非空时才走 all_store_item_ids()"


def test_outbound_replica_threshold_is_plural_constant_length() -> None:
    """出方向复刻的门槛必须是 `len(STORE_ITEM_IDS) > 1`，不是「有没有 all_store_item_ids()」。

    这条钉住实测发现的那个反直觉点：8 家 entry 模块有 `all_store_item_ids()` 却用不上，
    因为没有复数常量就进不了 combined 分支。
    """
    mod = _load_module()

    class _HasFnButNoPlural:
        STORE_ITEM_ID = "Y-single"

        @staticmethod
        def all_store_item_ids():
            return ("Y-a", "Y-b", "Y-c")

        @staticmethod
        def build_combined_store_projection(*_a, **_k):  # pragma: no cover
            return None

    assert mod._visible_to_outbound(_HasFnButNoPlural) == ("Y-single",), (
        "没有复数常量时出方向只能看到单数那一个 —— 即使 all_store_item_ids() 存在"
    )
