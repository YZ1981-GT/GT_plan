#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 `phase5_m6_retained_earnings.build_contract_payload()` 生成/校验磁盘契约。

用法：
  校验: .venv\\Scripts\\python.exe backend/scripts/gen/generate_phase5_m6_contract.py
  写盘: .venv\\Scripts\\python.exe backend/scripts/gen/generate_phase5_m6_contract.py --apply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import (  # noqa: E402
    phase5_m6_retained_earnings as m,
)
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()

    parsed = parse_contract(payload, adapter_id=m.ADAPTER_ID)
    print(
        f"[schema] parse_contract OK: sheets={[s.sheet_key for s in parsed.sheets]} "
        f"tables={[[t.table_key for t in s.tables] for s in parsed.sheets]} "
        f"canonical_sha256={parsed.canonical_sha256}"
    )
    print(f"[shape] store_item_ids={m.all_store_item_ids()} uuid_cols={[i.uuid_col for i in m.instrumentation_specs()]}")

    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        print(f"[apply] wrote {path} (digest={canonical_digest(payload)[:16]})")
        return 0
    if not path.exists():
        print(f"[check] MISSING {path} — 需 --apply 生成")
        return 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        print(f"[check] DRIFT disk={canonical_digest(on_disk)[:16]} source={canonical_digest(payload)[:16]}")
        return 1
    print(f"[check] OK digest={canonical_digest(payload)[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
