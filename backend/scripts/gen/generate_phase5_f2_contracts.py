# -*- coding: utf-8 -*-
"""从 F2 main / stocktake 的 build_contract_payload() 生成/校验磁盘契约。

用法：
  校验: ..\.venv\Scripts\python.exe scripts/gen/generate_phase5_f2_contracts.py
  写盘: ..\.venv\Scripts\python.exe scripts/gen/generate_phase5_f2_contracts.py --apply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

_ENTRIES = [
    ("f2.inventory_main", "app.services.workpaper_sync.phase5_f2_inventory_main"),
    ("f2.stocktake_bundle", "app.services.workpaper_sync.phase5_f2_stocktake_bundle"),
    ("f2.inventory_valuation", "app.services.workpaper_sync.phase5_f2_inventory_valuation"),
    ("f2.inventory_special", "app.services.workpaper_sync.phase5_f2_inventory_special"),
]


def main() -> int:
    import importlib

    apply = "--apply" in sys.argv[1:]
    ok = True
    for adapter_id, module_path in _ENTRIES:
        mod = importlib.import_module(module_path)
        payload = mod.build_contract_payload()
        # 🔴 预检：必须过 parse_contract（原手写版在这一步抛 anchor=None）
        parse_contract(payload, adapter_id=adapter_id)
        path: Path = mod.contract_file_path()
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        digest = canonical_digest(payload)
        if apply:
            path.write_bytes(text.encode("utf-8"))
            print(f"[apply] {adapter_id} → {path.name} (digest={digest})")
        else:
            if not path.exists():
                print(f"[MISSING] {adapter_id} → {path} ⇒ 需 --apply")
                ok = False
            else:
                on_disk = json.loads(path.read_text(encoding="utf-8"))
                if canonical_digest(on_disk) != digest:
                    print(f"[STALE] {adapter_id} digest 不一致 ⇒ 需 --apply")
                    ok = False
                else:
                    print(f"[OK] {adapter_id} (digest={digest})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
