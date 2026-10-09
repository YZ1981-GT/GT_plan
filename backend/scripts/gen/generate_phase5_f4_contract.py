# -*- coding: utf-8 -*-
"""从 phase5_f4_accounts_payable.build_contract_payload() 生成/校验磁盘契约。

spec: f4-sync-coverage-and-first-canary · Task 8（发布链第①环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_f4_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_f4_contract.py --apply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_f4_accounts_payable as m  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()
    # 🔴 生成前先过 schema：F1 的手写 payload 就是在这一步之后才在 registry 侧炸的
    #    （`table anchor 必须是 A1 单元格，实得 None`）—— 生成器自己先验一次，
    #    落盘的契约必定可解析。
    parse_contract(payload, adapter_id=m.ADAPTER_ID)
    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        # 🔴 `write_bytes` 而非 `write_text`：Windows 上后者按 `\r\n` 写回，CRLF 被双向锁漏掉
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
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
