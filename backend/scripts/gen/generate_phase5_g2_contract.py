# -*- coding: utf-8 -*-
"""从 `phase5_g2_interest_receivable.build_contract_payload()` 生成/校验磁盘契约。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 14（发布链第①环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g2_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g2_contract.py --apply

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。
`phase5_g2_interest_receivable.assert_contract_file_matches_source()` 会在
adapter 注册路径上现算比对，磁盘与源不一致即 `EntrySelectionError`。

🔴 写盘前**先跑一遍 `parse_contract`**（本脚本比 F1 的版本多这一道）：
本轮实测 F1 的契约在磁盘上是一份 `parse_contract` **过不了**的形态
（`table anchor 必须是 A1 单元格，实得 None`），因为它的生成器只写不校验 ——
于是 `assert_contract_file_matches_source()` 在 F1 上从来没能通过。
G2 不重复该形态：写盘即经 schema 校验。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import (  # noqa: E402
    phase5_g2_interest_receivable as m,
)
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()

    # 🔴 schema 门：不合法就别写盘（见模块 docstring 的 F1 教训）
    parsed = parse_contract(payload, adapter_id=m.ADAPTER_ID)
    print(
        f"[schema] parse_contract OK: sheets={[s.sheet_key for s in parsed.sheets]} "
        f"canonical_sha256={parsed.canonical_sha256}"
    )

    path = m.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        print(f"[apply] wrote {path} (canonical_digest={canonical_digest(payload)})")
        return 0
    if not path.exists():
        print(f"[check] MISSING {path} —— 需 --apply 生成")
        return 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        print(
            f"[check] DRIFT disk={canonical_digest(on_disk)} "
            f"source={canonical_digest(payload)}"
        )
        return 1
    print(f"[check] OK canonical_digest={canonical_digest(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
