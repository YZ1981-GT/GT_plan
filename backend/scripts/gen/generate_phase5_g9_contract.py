# -*- coding: utf-8 -*-
"""从 `phase5_g9_other_noncurrent.build_contract_payload()` 生成/校验磁盘契约。

spec: `g-cycle-single-region-detail-lanes` · Task 8 / C-5（发布链第①环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g9_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g9_contract.py --apply

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。
`phase5_g9_other_noncurrent.assert_contract_file_matches_source()` 会在 adapter
注册路径上现算比对，磁盘与源不一致即 `EntrySelectionError`。

🔴 写盘前先跑 `parse_contract`（照 G2 生成器，不照 F1 的只写不校验形态 —— F1 的磁盘
契约是一份 `parse_contract` 过不了的形态，于是它的 source-locked 断言从未通过）。

🔴 G9 的契约形态与前十一家不同：**一张 sheet、三条 tables**（`明细表G9-2` 的三个
受管区共享 `sheet_key="g902-managed"`，`template_id` 逐区不同 `G92R1/R2/R3`）。
本脚本顺带把这一点打印出来，便于肉眼核对不是退化成一条。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import (  # noqa: E402
    phase5_g9_other_noncurrent as m,
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
    print(
        f"[shape] store_item_ids={m.all_store_item_ids()} "
        f"sections={[s.row_section_value for s in m.section_specs()]}"
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
