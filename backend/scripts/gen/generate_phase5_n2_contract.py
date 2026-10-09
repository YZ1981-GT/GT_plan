#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 phase5_n2_taxes_payable.build_contract_payload() 生成/校验磁盘契约。"""
from __future__ import annotations
import json, sys
from pathlib import Path
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
from app.services.workpaper_sync import phase5_n2_taxes_payable as m  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()
    parsed = parse_contract(payload, adapter_id=m.ADAPTER_ID)
    print(f"[schema] OK: sheets={[s.sheet_key for s in parsed.sheets]} tables={[[t.table_key for t in s.tables] for s in parsed.sheets]}")
    print(f"[shape] store_item_ids={m.all_store_item_ids()} uuid_cols={[i.uuid_col for i in m.instrumentation_specs()]}")
    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        print(f"[apply] wrote {path} (digest={canonical_digest(payload)[:16]})")
        return 0
    if not path.exists():
        print(f"[check] MISSING {path}")
        return 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        print(f"[check] DRIFT")
        return 1
    print(f"[check] OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
