# -*- coding: utf-8 -*-
"""从 phase5_d4_revenue_detail.build_contract_payload() 生成/校验磁盘契约。

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_d4_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_d4_contract.py --apply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_d4_revenue_detail as m  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()
    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 🔴 必须显式 `newline="\n"`：不传时 `write_text` 按 `os.linesep`（Windows=`\r\n`）
        # 写回，会把 JSON 腌成 CRLF。契约的 canonical digest 对 CR 不可见（`json.loads`
        # 后比较 dict），双向锁因此假绿；而运行时按字节读到的契约与生成器产出不一致。
        # 用 `write_bytes` 让字节序完全由本行 text 决定，与生成器 `--check` 的字节断言对齐。
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
