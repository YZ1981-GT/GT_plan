# -*- coding: utf-8 -*-
"""出/回两方向能取到的 store item 集合必须等于 provider 声明的全集（需求 3.3 的精确落点）。

spec: d1-sync-row-table-engine-and-d1-coverage · 缺陷③ 修复
Requirements 3.1 / 3.3 / 7.3

═══ 这条门禁钉的是什么（2026-09-28 实测发现的真缺陷，不是假设）═══

两个方向都从 **entry 模块**（`plan.provider_module` /
`DELIVERED_PER_ENTRY_CONTRACTS[].provider_module`）取 store item 清单：

* 回方向 `store_mirror.py`::

      _all_ids_fn = getattr(bridge, "all_store_item_ids", None)
      _rows_loop_item_ids = tuple(_all_ids_fn()) if callable(_all_ids_fn) \\
                            else tuple(bridge.STORE_ITEM_IDS)

* 出方向 `store_projection_response.py`::

      store_item_ids = tuple(getattr(provider, "STORE_ITEM_IDS", ()) or ())
      if len(store_item_ids) > 1 and hasattr(provider, "build_combined_store_projection"):
          all_ids_fn = getattr(provider, "all_store_item_ids", None)
          ...

🔴 **实测**：D1 / D3 / D5 / D6 / D7 五家的 entry 模块**既无** `all_store_item_ids()`
**也无** `STORE_ITEM_IDS`（复数），只有单数 `STORE_ITEM_ID`。而它们各自的扩容面
（D1 的 18 个 item / 12 张受管 sheet）全在**伴生模块** `phase5_*_expansion` 里。

后果：伴生模块的 `all_store_item_ids()` 写得完整、判据全绿，但**没有任何生产代码调用它** ——
出方向拿到空元组（`getattr` 默认值）⇒ 只喂单个 item；回方向 `bridge.STORE_ITEM_IDS`
属性不存在 ⇒ 直接 `AttributeError`。**扩容声明与装配链之间是断开的。**

这与 D4-35 恒空 / D4-13 写不进 OO 是**同一形态**（provider 声明了，某方向漏喂），
只是这次断口在「entry 模块 ↔ 伴生模块」之间，比 D4 当年的「常量 ↔ 并集」更隐蔽：
per-sheet 声明判据、instrumentation 判据、golden digest 全部覆盖不到这条边。

对照 D4（已验证可用的范式）：entry 模块**自己**暴露 `all_store_item_ids()`（46 个）
+ `STORE_ITEM_IDS`（37 个）⇒ 两方向都取得到。

═══ 判据 ═══

对每个已注册 adapter：

    出方向可见集合（复刻 store_projection_response 的取法）
        == provider 声明全集（entry ∪ 伴生模块的 all_store_item_ids()）

不等即「声明了但装配链看不到」。棘轮基线 `KNOWN_UNWIRED` 冻结当前已知的五家，
**只许变短**：任何新增不等的 adapter 立即打红。基线项修好后必须删（脚本会把失效项报红）。

🔴 为什么用棘轮而不是硬修：接通这条边需要同时改 ①entry 模块加薄转发 ②注册表 items 补齐
各 item 的 `kind` ③`store_mirror._dict_store_items` 从「按 D4 常量名硬编码」改为「按
`StoreItemSpec.kind` 收集」—— 第 ③ 步是框架层改动，影响全部 42 个 adapter，必须跑全套
零回归 + 整册 materialize 验证。它属各 lane 的**接入本体**任务（D1 侧 = tasks 25~29 的硬前置），
不是一个卡点该顺手做的事。本卡点负责让它不可能被忽略。

自测：`backend/tests/scripts/test_check_store_item_two_way_parity.py`（含变异反证）。
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"

#: 🔴 棘轮基线：已知「声明了但装配链看不到」的 adapter（只许变短）。
#:
#: 每条写明**归属 lane** 与**缺口规模**。修好后必须从本表删除 —— 脚本会把失效项报红
#: （见 `run()` 的 stale 检查），不允许躺着占位。
KNOWN_UNWIRED: dict[str, str] = {
    # ── D1 已于 2026-09-28 接通（棘轮变短，条目按纪律删除）───────────────────
    #    接法可作其余四家的范式：entry 模块加 ①`all_store_item_ids()` 薄转发伴生模块
    #    ②PEP 562 `__getattr__` 延迟暴露复数 `STORE_ITEM_IDS`（避开循环 import、保持单源）
    #    ③`build_combined_store_projection`（按 spec 泛化，遍历 `managed_row_table_specs()`）
    #    ④`merge_projection_into_all_d1_stores`（回方向整体镜像）；注册表那条加
    #    `dual_store_fn` + `merge_all_fn`。dict 形态走已有的 `dedicated_items`，
    #    无契约 table 的 static_region 显式登记在
    #    `phase5_d1_notes_receivable.STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE` 里并跳过。
    #
    # ── 有伴生扩容模块的四家：声明在 `phase5_*_expansion`，entry 模块两个常量都没有 ──
    "d3.prepaid_receipts_detail": (
        "归属 lane：d3-sync-coverage-via-row-table-engine。同型断口，声明 7 / 可见 1"
        "（扩容面在伴生模块 `phase5_d3_expansion`）。"
    ),
    "d5.receivables_financing_detail": (
        "归属 lane：d567-sync-coverage-via-row-table-engine。同型断口，声明 2 / 可见 1"
        "（扩容面在 `phase5_d5_expansion`）。"
    ),
    "d6.contract_assets_detail": (
        "归属 lane：d567-sync-coverage-via-row-table-engine。同型断口，声明 8 / 可见 1"
        "（扩容面在 `phase5_d6_expansion`）。"
    ),
    "d7.contract_liabilities_detail": (
        "归属 lane：d567-sync-coverage-via-row-table-engine。同型断口，声明 7 / 可见 1"
        "（扩容面在 `phase5_d7_expansion`）。"
    ),
    # ── 无伴生模块、entry 自己有 `all_store_item_ids()` 但缺复数常量的八家 ──
    #    出方向的门槛是 `len(STORE_ITEM_IDS) > 1`，没有复数常量就进不了 combined 分支 ⇒
    #    即使 `all_store_item_ids()` 写得完整也用不上。修法相对简单（补复数常量 +
    #    `build_combined_store_projection`），但仍需各 lane 自己验证 dict/dedicated 形态的排除。
    "e1.monetary_fund_detail": (
        "归属 lane：e1-sync-coverage-and-first-canary。声明 2 / 可见 1（E1-digital-rows 不可见）。"
    ),
    "f2.stocktake_bundle": (
        "归属 lane：f2-sync-coverage-four-entry-lanes。声明 2 / 可见 1（F2-25-floor-rows 不可见）。"
    ),
    "f3.notes_payable_detail": (
        "归属 lane：f3-sync-coverage-and-first-canary。声明 5 / 可见 1，缺口 4"
        "（F3-6-rows / F3-7-{credit,debit,subsequent}-rows）。"
    ),
    "f5.cost_of_sales_detail": (
        "归属 lane：f5-sync-coverage-and-first-canary。声明 2 / 可见 1"
        "（F5-1-adj-other-rows 不可见）。"
    ),
    "g4.bond_main": (
        "归属 lane：g4-g6-shared-workbook-three-entry-lanes。声明 1 / 可见 1 但**不是同一个**"
        "（声明 G4-7-items，可见的是单数常量的另一个值）⇒ 计数相等掩盖了集合不等，"
        "判据必须比集合而不是比 len。"
    ),
    "g6.other_bond_main": (
        "归属 lane：g4-g6-shared-workbook-three-entry-lanes。同 g4"
        "（声明 G6-5-fair-value-data 不在可见集合里）。"
    ),
    "h3.investment_property_detail": (
        "归属 lane：h3-h5-h7-variant-axis-and-dynamic-column-paradigm。声明 2 / 可见 1"
        "（H3-2-fair-rows 不可见）。"
    ),
    "h7.biological_assets_detail": (
        "归属 lane：h3-h5-h7-variant-axis-and-dynamic-column-paradigm。声明 2 / 可见 1"
        "（H7-2-fair-rows 不可见）。"
    ),
    # ── 唯一「两方向不等」的一家 ──
    "d2.receivable_detail": (
        "归属 lane：d2-sync-coverage-via-row-table-engine。**全仓唯一两方向不等**"
        "（出方向可见 1 / 回方向可见 0）：bridge 模块 `d2_bidirectional_bridge` 没有单数 "
        "`STORE_ITEM_ID`，而回方向单 item 路径正是读它 ⇒ 回方向拿不到任何 item。"
        "出方向另有自己的取法故仍可见 1。"
    ),
}

#: entry 模块名 → 伴生扩容模块名（现扫目录得出，不写死；命名约定 `*_expansion`）。
def _companion_of(entry_module: str) -> str | None:
    """entry 模块的伴生扩容模块（若存在）。"""
    sync = _BACKEND / "app" / "services" / "workpaper_sync"
    # phase5_d1_notes_receivable -> phase5_d1_expansion
    parts = entry_module.split("_")
    if len(parts) < 2:
        return None
    prefix = "_".join(parts[:2])  # phase5_d1
    candidate = f"{prefix}_expansion"
    return candidate if (sync / f"{candidate}.py").exists() else None


def _visible_to_outbound(module) -> tuple[str, ...]:
    """复刻 `store_projection_response.build_store_projection_payload` 的取法。

    🔴 逐字对照现读的源码（2026-09-28）：

        store_item_ids = tuple(getattr(provider, "STORE_ITEM_IDS", ()) or ())
        if len(store_item_ids) > 1 and hasattr(provider, "build_combined_store_projection"):
            all_ids_fn = getattr(provider, "all_store_item_ids", None)
            combined = tuple(all_ids_fn()) if callable(all_ids_fn) else store_item_ids + D45_FIXED
        else:
            <只投影单数 STORE_ITEM_ID 那一个>

    ⇒ **门槛是复数常量 `STORE_ITEM_IDS` 的长度**，不是 `all_store_item_ids()` 是否存在。
      entry 模块只有单数常量时，即使它暴露了 `all_store_item_ids()` 也进不了 combined 分支。
    """
    plural = tuple(getattr(module, "STORE_ITEM_IDS", ()) or ())
    if len(plural) > 1 and hasattr(module, "build_combined_store_projection"):
        fn = getattr(module, "all_store_item_ids", None)
        if callable(fn):
            return tuple(fn())
        return plural + tuple(getattr(module, "STORE_ITEM_IDS_D45_FIXED", ()) or ())
    single = getattr(module, "STORE_ITEM_ID", None)
    return (str(single),) if isinstance(single, str) and single else ()


def _visible_to_inbound(module, plan) -> tuple[str, ...]:
    """复刻 `store_mirror.mirror_projection_into_store` 的取法。

    🔴 逐字对照现读的源码（2026-09-28），**分派点是 `plan.dual_store_fn`**::

        plan = store_merge_plan_or_skip(adapter_id)
        bridge = import(plan.provider_module)
        if plan.dual_store_fn:
            await _mirror_dual_stores(...)      # 多 item 路径
            return
        store_item_id = bridge.STORE_ITEM_ID    # 单 item 路径：只镜像单数常量那一个

    多 item 路径（`_mirror_dual_stores` 内）才是::

        _all_ids_fn = getattr(bridge, "all_store_item_ids", None)
        _rows_loop_item_ids = tuple(_all_ids_fn()) if callable(_all_ids_fn) \\
                              else tuple(bridge.STORE_ITEM_IDS)

    🔴 **本函数第一版复刻错了**：直接套了 `_mirror_dual_stores` 内那段，于是把
    b60/d2/g7/h1 这些 `dual_store_fn` 为空的家判成「回方向 AttributeError」。而它们是真栈
    验证过的（真库 D2 gen=2 / G7 gen=6 / H1 gen=2），若真会抛早就崩了 —— 这个自相矛盾
    正是发现复刻错误的线索。**复刻生产逻辑时必须连控制流一起读，不能只按 grep 到的行拼。**
    """
    if getattr(plan, "dual_store_fn", None):
        fn = getattr(module, "all_store_item_ids", None)
        if callable(fn):
            return tuple(fn())
        return tuple(getattr(module, "STORE_ITEM_IDS", ()) or ())
    single = getattr(module, "STORE_ITEM_ID", None)
    inbound = [str(single)] if isinstance(single, str) and single else []
    # dedicated_items 走 `_mirror_dedicated_dict_stores`，与主路径并行（不是 else 分支）。
    for d in getattr(plan, "dedicated_items", ()) or ():
        item_const = getattr(d, "item_id_const", "")
        val = getattr(module, item_const, None) if item_const else None
        if isinstance(val, str) and val and val not in inbound:
            inbound.append(val)
    return tuple(inbound)


def _declared_全集(entry_module: str) -> tuple[tuple[str, ...], str | None]:
    """provider 声明的全部 item（entry ∪ 伴生模块的 `all_store_item_ids()`）。

    返回 `(items, unresolvable_reason)`。

    🔴 第二个返回值是 2026-09-28 加的：`importlib.import_module` 成功**不代表**
    `all_store_item_ids()` 能跑。D3/D5/D6/D7 的 expansion 模块在**函数体内** lazy import
    自己的 sheet 子模块（`from ... import phase5_d3_06_related_party as _d306`），
    那些子模块属别 lane 且**尚未入库** ⇒ 顶层 import 一切正常，一调用就 ImportError。
    纯 HEAD 检出上本门因此直接崩（traceback 退出），CI 上就是一个无从判读的红。

    静默 `continue` 也不行：那会让「声明 0 个 item」看起来像合规，把断口变成假绿。
    所以把原因带回去，由 `run()` 记为 `unresolvable` 单列并按棘轮登记。
    """
    out: list[str] = []
    reason: str | None = None
    for name in (entry_module, _companion_of(entry_module)):
        if not name:
            continue
        try:
            mod = importlib.import_module(f"app.services.workpaper_sync.{name}")
        except Exception:  # noqa: BLE001
            continue
        fn = getattr(mod, "all_store_item_ids", None)
        if callable(fn):
            try:
                items = list(fn())
            except Exception as exc:  # noqa: BLE001
                reason = f"{name}.all_store_item_ids(): {type(exc).__name__}: {exc}"
                continue
            for i in items:
                if i not in out:
                    out.append(str(i))
        else:
            for i in tuple(getattr(mod, "STORE_ITEM_IDS", ()) or ()):
                if i not in out:
                    out.append(str(i))
            single = getattr(mod, "STORE_ITEM_ID", None)
            if isinstance(single, str) and single and single not in out:
                out.append(single)
    return tuple(out), reason


def run() -> dict[str, Any]:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")

    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    unwired: list[dict[str, Any]] = []
    known_hit: list[dict[str, Any]] = []
    unresolvable: list[dict[str, Any]] = []
    checked = 0
    for adapter_id, plan in sorted(STORE_MERGE_REGISTRY.items()):
        entry_module = str(getattr(plan, "provider_module", "") or "")
        if not entry_module:
            continue
        try:
            entry = importlib.import_module(
                f"app.services.workpaper_sync.{entry_module}"
            )
        except ModuleNotFoundError as exc:
            # 🔴 entry 模块**在当前检出里不存在**（别 lane 的 provider 尚未入库：实测
            #    HEAD 上 g7/h1 的 `pilot_*_store_merge.py` 与 d5/d6/d7 的 provider 都是
            #    这种状态，而 registry 已提交对它们的引用）。这是检出状态而非接线缺陷，
            #    与「函数体内 lazy import 崩」同类，一并归入 unresolvable：
            #    不崩、不判红（除非是 `d1.*`）、也**不算**棘轮失效。
            unresolvable.append(
                {
                    "adapter_id": adapter_id,
                    "entry_module": entry_module,
                    "companion": _companion_of(entry_module),
                    "reason": f"entry 模块导入失败 {type(exc).__name__}: {exc}",
                }
            )
            continue
        except Exception as exc:  # noqa: BLE001
            # 模块存在但 import 时抛别的错 —— 那是真缺陷，照旧判红。
            unwired.append(
                {
                    "adapter_id": adapter_id,
                    "entry_module": entry_module,
                    "error": f"{type(exc).__name__}: {exc}",
                    "visible": [],
                    "declared": [],
                    "invisible": [],
                }
            )
            continue
        checked += 1
        outbound = set(_visible_to_outbound(entry))
        inbound = set(_visible_to_inbound(entry, plan))
        inbound_error = None
        declared_tuple, declared_unresolvable = _declared_全集(entry_module)
        if declared_unresolvable is not None:
            # 🔴 声明层在当前检出不可解析（别 lane 的 sheet 子模块未入库）。
            #    既不崩也不静默跳过 —— 单列出来，由棘轮登记决定是否阻塞。
            unresolvable.append(
                {
                    "adapter_id": adapter_id,
                    "entry_module": entry_module,
                    "companion": _companion_of(entry_module),
                    "reason": declared_unresolvable,
                }
            )
            continue
        declared = set(declared_tuple)
        invisible_out = sorted(declared - outbound)
        invisible_in = sorted(declared - inbound)
        if not invisible_out and not invisible_in:
            continue
        row = {
            "adapter_id": adapter_id,
            "entry_module": entry_module,
            "companion": _companion_of(entry_module),
            "declared_count": len(declared),
            "outbound_count": len(outbound),
            "inbound_count": len(inbound),
            "inbound_error": inbound_error,
            "invisible_count": len(invisible_out),
            "invisible": invisible_out,
            "invisible_inbound": invisible_in,
            "two_way_equal": outbound == inbound and not inbound_error,
            "entry_has_all_fn": callable(getattr(entry, "all_store_item_ids", None)),
            "entry_has_plural": hasattr(entry, "STORE_ITEM_IDS"),
        }
        if adapter_id in KNOWN_UNWIRED:
            known_hit.append({**row, "known_reason": KNOWN_UNWIRED[adapter_id]})
        else:
            unwired.append(row)

    hit_ids = {r["adapter_id"] for r in known_hit}
    unresolvable_ids = {r["adapter_id"] for r in unresolvable}
    # 🔴 声明层不可解析的 adapter 不能算「已失效」—— 它根本没被判定过。
    #    否则纯 HEAD 检出会要求删掉一批**仍然有效**的登记，删完等别 lane 入库就成漏报。
    stale = sorted(
        a for a in KNOWN_UNWIRED if a not in hit_ids and a not in unresolvable_ids
    )

    # 🔴 本 spec 自己的 provider **必须**永远可解析：它不可解析就是本 lane 漏提交了
    #    子模块（2026-09-28 实测过一次：6 个 D1 子模块漏提交，靠干净检出才发现）。
    #    别 lane 的不可解析只打印不判红 —— 那是他们的入库节奏，不该阻塞本门。
    own_unresolvable = sorted(
        r["adapter_id"] for r in unresolvable if r["adapter_id"].startswith("d1.")
    )

    return {
        "ok": not unwired and not stale and not own_unresolvable,
        "adapters_checked": checked,
        "new_unwired": sorted(unwired, key=lambda r: r["adapter_id"]),
        "known_unwired_hit": sorted(known_hit, key=lambda r: r["adapter_id"]),
        "stale_known_unwired": stale,
        # 声明层在当前检出不可解析（函数体内 lazy import 的子模块未入库）。
        "unresolvable_declarations": sorted(unresolvable, key=lambda r: r["adapter_id"]),
        "own_lane_unresolvable": own_unresolvable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    report = run()
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if report["ok"]:
        total_invisible = sum(
            r["invisible_count"] for r in report["known_unwired_hit"]
        )
        print(
            f"✅ 两方向 store item 集合无**新增**断口："
            f"检查 {report['adapters_checked']} 个 adapter，新增 0；"
            f"已登记缺口 {len(report['known_unwired_hit'])} 个 adapter / "
            f"{total_invisible} 个 item 装配链看不到（见 KNOWN_UNWIRED）"
        )
        for r in report["known_unwired_hit"]:
            print(
                f"   [已登记] {r['adapter_id']}：声明 {r['declared_count']} 个 / "
                f"出方向可见 {r['outbound_count']} / 回方向可见 {r['inbound_count']} "
                f"⇒ 出方向看不到 {r['invisible_count']} 个"
                + ("（两方向不等）" if not r["two_way_equal"] else "")
            )
        for r in report["unresolvable_declarations"]:
            print(
                f"   [声明层不可解析] {r['adapter_id']}（{r['entry_module']}）："
                f"{r['reason']}"
            )
        if report["unresolvable_declarations"]:
            print(
                "   （以上 provider 的 `all_store_item_ids()` 在**函数体内** lazy import"
                " 了尚未入库的 sheet 子模块 —— 属别 lane 的入库节奏，本门不判红但如实列出；"
                "若其中出现 `d1.*` 则一定是本 lane 漏提交，会判红）"
            )
        return 0

    if report["own_lane_unresolvable"]:
        print(
            f"❌ 本 lane（`d1.*`）有 {len(report['own_lane_unresolvable'])} 个 provider 的"
            f"声明层在当前检出**不可解析** —— 几乎一定是漏提交了 sheet 子模块："
        )
        for r in report["unresolvable_declarations"]:
            if r["adapter_id"] in report["own_lane_unresolvable"]:
                print(f"   [不可解析] {r['adapter_id']}：{r['reason']}")

    if report["stale_known_unwired"]:
        print(
            f"❌ KNOWN_UNWIRED 里有 {len(report['stale_known_unwired'])} 条**已失效**"
            f"（这些 adapter 现已接通）—— 请从棘轮基线删除："
        )
        for a in report["stale_known_unwired"]:
            print(f"   [失效] {a}")

    if not report["new_unwired"]:
        return 1

    for r in report["new_unwired"]:
        if r.get("error"):
            print(f"❌ {r['adapter_id']}：entry 模块导入失败 {r['error']}")
            continue
        print(
            f"❌ {r['adapter_id']}：声明 {r['declared_count']} 个 store item，"
            f"出方向可见 {r['outbound_count']} 个 / 回方向可见 "
            f"{r['inbound_error'] or r['inbound_count']} 个"
            f"（两方向相等={r['two_way_equal']}）"
        )
        print(
            f"   entry_module={r['entry_module']}"
            f"（all_store_item_ids()={r['entry_has_all_fn']}，"
            f"STORE_ITEM_IDS={r['entry_has_plural']}）"
            f" companion={r['companion']}"
        )
        if r["invisible"]:
            print(
                f"   出方向不可见：{r['invisible'][:8]}"
                f"{' …' if len(r['invisible']) > 8 else ''}"
            )
        if r["invisible_inbound"]:
            print(
                f"   回方向不可见：{r['invisible_inbound'][:8]}"
                f"{' …' if len(r['invisible_inbound']) > 8 else ''}"
            )
        print(
            "   修法：entry 模块暴露 `all_store_item_ids()`（可薄转发伴生模块，"
            "注意伴生模块在模块级 import entry 的常量 ⇒ 必须函数内延迟 import），"
            "并确认 `store_mirror` 能按 `StoreItemSpec.kind` 把 dict/dedicated 形态"
            "从 rows 循环里排除 —— 否则 dict 载荷会在 iter_store_rows 抛 "
            "RowTableStorePayloadError。参照 D4 的 entry 模块（46 个 item 两方向都可见）。"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
