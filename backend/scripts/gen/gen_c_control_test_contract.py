#!/usr/bin/env python3
"""生成 C 控制测试汇总表的生产契约 JSON。

spec: c-cycle-sync-foundation-and-first-canary · Task 22

用法（仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/gen/gen_c_control_test_contract.py

🔴 改了 provider 常量后必须重跑本脚本，否则 `assert_contract_file_matches_source()`
   会以「契约漂移」打红（双重漂移门的设计意图）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_c_control_test as provider  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402


def main() -> int:
    provider.assert_entry_selectable()
    payload = provider.build_contract_payload()

    # 生成前先过引擎强校验，避免把非法契约写进目录
    parse_contract(payload, adapter_id=provider.ADAPTER_ID)

    target = provider.contract_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.write_bytes(text.encode("utf-8"))

    print(f"written: {target.relative_to(_BACKEND.parent)}")
    print(f"  contract_id   = {payload['contract_id']}")
    print(f"  review_status = {payload['review_status']}")
    print(f"  sheets        = {len(payload['sheets'])}")
    print(f"  fields        = {len(payload['sheets'][0]['tables'][0]['fields'])}")
    print(f"  mapping_digest= {provider.mapping_digest()}")

    # 生成后立刻验双重漂移门
    provider.assert_contract_file_matches_source()
    print("  drift gate    = OK（磁盘与 provider 现算一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
