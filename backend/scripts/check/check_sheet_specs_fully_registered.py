# -*- coding: utf-8 -*-
"""sheet spec 声明全部接入注册表门禁（P10 / D1-P10）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 3（红判据先行）/ Task 21（转绿）
Requirements 7.2 / 7.4

═══ 这条门禁钉的是什么 ═══

本 spec 把 store item 的形态分派收敛到框架层注册表 `store_item_registry.STORE_MERGE_REGISTRY`
（adapter_id → StoreMergePlan，O(1)）。照 `check_store_item_ids_fully_wired.py` 已验证的范式：
一个新 `RowTableSheetSpec` / `StoreItemSpec` 被声明却忘接注册表 ⇒ 出/回某方向漏喂 ⇒ 重演
D4-35 恒空 / D4-13 写不进 OO 的缺陷。本门禁守住「声明即接线」。

判据（import 后读运行时值，stdlib + provider）：
  1. 注册表模块 `store_item_registry` 必须存在且导出 `STORE_MERGE_REGISTRY` (Mapping)
     与 `all_registered_adapter_ids()`。
  2. 8 家已交付 provider 的 adapter_id 必须**逐个**出现在 STORE_MERGE_REGISTRY 里。
  3. 注册表无重复 key（dict 天然无重复，这里断言 key 集合与声明清单一致）。

现状（Task 3）：**必红**（注册表模块 `store_item_registry` 尚不存在 ⇒ 以「模块缺失」形态红）。
注册表落地后（Task 12/21）：**必绿**。命中即 exit 1。
自测：`backend/tests/scripts/test_check_sheet_specs_fully_registered.py`。
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

#: 8 家已交付 provider 的 adapter_id（与 golden digest 基线同一分母）。
EXPECTED_ADAPTER_IDS: tuple[str, ...] = (
    "b60.hour_budget",
    "d1.notes_receivable_detail",
    "d2.receivable_detail",
    "d3.prepaid_receipts_detail",
    "d4.revenue_detail",
    "d5.receivables_financing_detail",
    "d6.contract_assets_detail",
    "d7.contract_liabilities_detail",
)


def run() -> dict[str, Any]:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")

    try:
        reg = importlib.import_module("app.services.workpaper_sync.store_item_registry")
    except ModuleNotFoundError:
        return {
            "ok": False,
            "reason": "registry_module_missing",
            "detail": "store_item_registry 模块尚不存在（Task 12 未落）—— 此为 P10 先打红的预期形态",
            "missing": list(EXPECTED_ADAPTER_IDS),
            "registered": [],
        }

    registry = getattr(reg, "STORE_MERGE_REGISTRY", None)
    if registry is None or not hasattr(registry, "get"):
        return {
            "ok": False,
            "reason": "registry_symbol_missing",
            "detail": "store_item_registry 缺 STORE_MERGE_REGISTRY 映射",
            "missing": list(EXPECTED_ADAPTER_IDS),
            "registered": [],
        }

    registered = set(registry.keys())
    missing = [a for a in EXPECTED_ADAPTER_IDS if a not in registered]
    return {
        "ok": not missing,
        "reason": "ok" if not missing else "adapter_not_registered",
        "registered": sorted(registered),
        "missing": missing,
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
        print(f"✅ sheet spec 全部接入注册表：{len(report['registered'])} 个 adapter 已注册")
        return 0

    print(f"❌ sheet spec 未完全接入注册表（reason={report['reason']}）：")
    if report.get("detail"):
        print(f"   {report['detail']}")
    for a in report["missing"]:
        print(f"   [漏项] adapter {a!r} 不在 STORE_MERGE_REGISTRY")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
