# -*- coding: utf-8 -*-
"""生成 / 校验 D2 检查工作簿 entry 的 per-entry contract 磁盘文件。

spec: d2-inspection-sync-coverage · Phase 4

payload 真源：
:func:`app.services.workpaper_sync.pilot_d2_inspection.build_contract_payload`

用法（仓库根）::

    python backend/scripts/gen/generate_d2_inspection_contract.py --check
    python backend/scripts/gen/generate_d2_inspection_contract.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _render(payload: dict) -> bytes:
    """稳定序列化：键排序 + 2 空格缩进 + LF + 末尾换行。"""
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="D2 inspection 契约生成/校验")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只校验磁盘与真源一致")
    group.add_argument("--apply", action="store_true", help="重写磁盘契约")
    args = parser.parse_args()

    from app.services.workpaper_sync import pilot_d2_inspection as P
    from app.services.workpaper_sync.contracts import parse_contract

    payload = P.build_contract_payload()
    contract = parse_contract(payload, adapter_id=P.ADAPTER_ID)
    blob = _render(payload)
    path = P.contract_file_path()

    if args.check:
        if not path.is_file():
            print(f"MISSING {path}")
            return 1
        on_disk = path.read_bytes()
        if on_disk != blob:
            print(f"STALE {path}: 磁盘 {len(on_disk)} 字节 != 真源 {len(blob)} 字节")
            return 1
        print(
            f"OK {path.name} bytes={len(blob)} "
            f"fields={len(contract.all_fields())} "
            f"canonical_sha256={contract.canonical_sha256}"
        )
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    print(
        f"WROTE {path} bytes={len(blob)} "
        f"fields={len(contract.all_fields())} "
        f"canonical_sha256={contract.canonical_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
