# -*- coding: utf-8 -*-
"""从 phase5_d6_contract_assets.build_contract_payload() 生成/校验磁盘契约。

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_d6_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_d6_contract.py --apply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_d6_contract_assets as m  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()
    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.write_text(text, encoding="utf-8")
        print(f"[apply] wrote {path} (canonical_digest={canonical_digest(payload)})")
        return 0
    if not path.exists():
        print(f"[check] MISSING {path} —— 需 --apply 生成")
        return 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        print(f"[check] DRIFT disk={canonical_digest(on_disk)} source={canonical_digest(payload)}")
        return 1
    print(f"[check] OK canonical_digest={canonical_digest(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
