#!/usr/bin/env python3
"""从 G6 entry 模块生成/校验磁盘契约。"""
from __future__ import annotations
import json, sys
from pathlib import Path
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
from app.services.workpaper_sync import phase5_g6_other_bond as m
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.definitions import canonical_digest

def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()
    parsed = parse_contract(payload, adapter_id=m.ADAPTER_ID)
    print(f"[schema] OK: tables={[[t.table_key for t in s.tables] for s in parsed.sheets]} digest={parsed.canonical_sha256}")
    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        print(f"[apply] wrote {path} (digest={canonical_digest(payload)})")
        return 0
    if not path.exists():
        print(f"[check] MISSING {path}")
        return 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        print("[check] DRIFT")
        return 1
    print(f"[check] OK digest={canonical_digest(payload)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
