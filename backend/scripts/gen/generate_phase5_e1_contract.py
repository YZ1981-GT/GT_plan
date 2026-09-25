# -*- coding: utf-8 -*-
"""从 phase5_e1_monetary_fund.build_contract_payload() 生成/校验磁盘契约。

spec: e1-sync-coverage-and-first-canary · Task 9（契约发布链第一环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_e1_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_e1_contract.py --apply

🔴 契约内容随 provider 的 `_INCLUDE_*` 灰度开关变化（受管 sheet 增减 ⇒ sheets/tables 增减）。
   开关改动后**必须**重跑 `--apply`，否则 `assert_contract_file_matches_source()` 会打红
   （那是双向锁死的设计意图：契约与代码不得单边漂移）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_e1_monetary_fund as m  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()
    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        # 🔴 `write_bytes` 而非 `write_text`：Windows 上后者按 `\r\n` 写回，CRLF 被双向锁漏掉
        path.write_bytes(text.encode("utf-8"))
        sheets = [(s["sheet_key"], len(s["tables"])) for s in payload["sheets"]]
        print(f"[apply] wrote {path}")
        print(f"        canonical_digest={canonical_digest(payload)}")
        print(f"        sheets={sheets} store_items={payload['review']['html_store']['item_ids']}")
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
