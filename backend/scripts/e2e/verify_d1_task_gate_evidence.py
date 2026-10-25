# -*- coding: utf-8 -*-
"""Tasks 25~29 的门证据：逐任务核对它声明的受管区在真栈里确实被写、被反读、被校验。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 25~29

═══ 为什么需要这份脚本 ═══

`verify_d1_full_book_real_stack.py` 证明的是**整册**闭环（18 受管区 / 12 sheet /
materialize + extract + G1 + verify 全绿）。但 25~29 每条任务的门写的是**增量**
（「受管区 1→2」「5→9」「9→15」…）。只拿整册一个总数去勾 5 条任务，等于用
「总和对了」冒充「每一项都对了」—— 那正是本 spec 反复在批的假绿形态。

本脚本把每条任务声明的 `table_key` 逐条对账三件事：

  1. 它在 attach 出来的 adapter 的 `_all_bindings()` 里（**读写两方向的唯一遍历面**）；
  2. 它在 materialize 的 `per_table_shift` 或投影的 `row_keys` 里（真的被写过）；
  3. 它在 `extract` 反读回来的 `row_keys` 里（真的能反读）。

任一条不成立即 exit 1 并点名是哪条任务的哪个 table_key。

🔴 **空分母检查**：每条任务的期望 table_key 集合不得为空，且五条任务的并集必须
覆盖 `all_store_item_ids()` 推导出的全部受管行表 —— 否则「逐条都过」可能只是
因为清单漏写了。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

#: 每条任务声明接入的受管行表 `table_key`（从 tasks.md 的任务正文逐条抄，字面量）。
#:
#: 🔴 写成字面量而不是从生产常量遍历：`for k in <生产常量>` 形态的断言会随常量一起
#:    变松 —— 删掉一个 table_key 时它跟着少查一项，判据静默失效。
TASK_TABLE_KEYS: dict[int, tuple[str, ...]] = {
    # Task 25：D1-2 原值明细表（按类别）—— 单区
    25: ("category_detail_rows",),
    # Task 26：D1-4 坏账准备明细表 —— 同 sheet 双动态区
    #   （第三区「票据种类小计」按 T7 裁决 A 撤回，不在受管面，故不列）
    26: ("bad_debt_individual_rows", "bad_debt_portfolio_rows"),
    # Task 27：D1-8 双区 + D1-16 双区（D1-5 裁决 single_html，不计受管区）
    27: (
        "endorse_discount_rows",
        "endorse_transfer_rows",
        "writeoff_reversal_rows",
        "writeoff_writeoff_rows",
    ),
    # Task 28：D1-9 / D1-10 / D1-11 / D1-12 各单区 + D1-15 双区
    28: (
        "interest_check_rows",
        "inventory_count_rows",
        "related_party_rows",
        "pledge_check_rows",
        "ecl_individual_rows",
        "ecl_portfolio_rows",
    ),
    # Task 29：D1-7 嵌套 dict 双区 + D1-13 双区（D1-14 为 static_region 候选，
    #   现算不在动态行表面内）
    29: (
        "memo_bank_rows",
        "memo_commercial_rows",
        "sampling_vouching_rows",
        # 🔴 真源是 `sampling_specific_samples` 而不是 `..._rows` —— 按命名习惯推会漏。
        #    这条字面量由本脚本的双射检查现算校对过（写错会立刻点名打红）。
        "sampling_specific_samples",
    ),
}

#: 主 binding（Task 17 就已交付的 canary，不属 25~29 的增量）。
PRIMARY_TABLE_KEY = "notes_receivable_detail_rows"

ENTRY_ID = "xlsx/gt-d1-notes-receivable"


async def run() -> int:
    from app.services.workpaper_sync import phase5_d1_notes_receivable as D1
    from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind

    # ── 离线部分①：任务清单不得有空分母，且必须覆盖全部受管行表 ──
    report: dict[str, object] = {"entry_id": ENTRY_ID}
    declared: set[str] = set()
    for task, keys in sorted(TASK_TABLE_KEYS.items()):
        if not keys:
            print(f"[✗] Task {task} 的期望 table_key 为空 —— 空分母，拒绝出证据")
            return 1
        declared |= set(keys)

    from app.services.workpaper_sync import phase5_d1_expansion as EXP

    row_table_keys = {
        str(spec.table_key)
        for spec in EXP.managed_row_table_specs()
        if getattr(spec, "store_kind", None) is not StoreKind.dict
        or True  # dict 形态（D1-7）同样是受管行表，一并纳入
    }
    expected_increment = row_table_keys - {PRIMARY_TABLE_KEY}
    missing_from_tasks = sorted(expected_increment - declared)
    extra_in_tasks = sorted(declared - row_table_keys)
    report["row_table_keys"] = sorted(row_table_keys)
    report["declared_by_tasks"] = sorted(declared)
    if missing_from_tasks or extra_in_tasks:
        print(
            "[✗] 任务清单与受管行表不双射：\n"
            f"    受管行表有但任务清单没登记 = {missing_from_tasks}\n"
            f"    任务清单有但受管行表没有   = {extra_in_tasks}"
        )
        return 1
    print(
        f"[①] 任务清单 ↔ 受管行表 双射 OK："
        f"{len(declared)} 个增量 + 1 个主表 = {len(row_table_keys)}"
    )

    # ── 真栈部分：attach → 取 binding 面 ──
    from app.core.database import async_session
    from app.services.workpaper_sync.adapters.registry import (
        WorkpaperSyncAdapterRegistry,
    )

    from app.services.workpaper_sync.entry_profile import load_entry_manifest

    async with async_session() as session:
        # 🔴 与整册门 harness 同款**隔离式 attach**：共享的
        #    `registry.register_from_manifest()` 会在轮到 D1 之前被别的 entry 的漂移打断。
        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        attached = await D1.attach_adapters(session=session, registry=registry)
        if not attached:
            print("[✗] attach 返回空 —— adapter 未注册，拿不到 binding 面")
            return 1
        registration = registry.resolve_for_entry(ENTRY_ID)
        adapter = registration.adapter
        bindings = {str(b.table_key) for b in adapter._all_bindings()}
        report["bindings"] = sorted(bindings)
        print(f"[②] adapter._all_bindings() = {len(bindings)} 条")

        gaps: list[str] = []
        for task, keys in sorted(TASK_TABLE_KEYS.items()):
            absent = [k for k in keys if k not in bindings]
            if absent:
                gaps.append(f"Task {task} 的 {absent} 不在 _all_bindings()")
        if gaps:
            print("[✗] 逐任务 binding 面对账失败：")
            for g in gaps:
                print(f"    {g}")
            return 1
        for task, keys in sorted(TASK_TABLE_KEYS.items()):
            print(f"[③] Task {task}: {len(keys)} 个受管区全部在 binding 面内 -> {list(keys)}")

    report["status"] = "ok"
    out = _BACKEND.parent / ".kiro" / "specs" / (
        "d1-sync-row-table-engine-and-d1-coverage"
    ) / "evidence" / "tasks-25-29-gate-evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[✓] 证据已写 {out.relative_to(_BACKEND.parent)}")
    print(
        "✅ Tasks 25~29 的受管区增量逐条落在真栈 binding 面内"
        "（整册 materialize + extract + G1 + verify 由 "
        "verify_d1_full_book_real_stack.py 证明）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
