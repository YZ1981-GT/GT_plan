# -*- coding: utf-8 -*-
"""从 `phase5_g8_other_equity.build_contract_payload()` 生成/校验磁盘契约。

spec: `g-cycle-single-region-detail-lanes` · Task 9b / C-8（发布链第①环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g8_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g8_contract.py --apply

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。
`phase5_g8_other_equity.assert_contract_file_matches_source()` 会在 adapter 注册路径上
现算比对，磁盘与源不一致即 `EntrySelectionError`。

🔴 写盘前先跑 `parse_contract`（照 G2/G9/G10 生成器）。G8 这一步尤其关键：它的
`mode=formula` 列受 **CS-13**（必须落在 `formula_mask` 内）约束，而 `R`/`T` 两列因模板
部分行无公式只能判 `editable` —— 形态错了这里就不落盘（本轮首版把 `M/P/R/T` 全判
formula 而 `formula_columns` 只放四列，`parse_contract` 直接抛，正是这道门拦住的）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_g8_other_equity as m  # noqa: E402
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
    table = parsed.sheets[0].tables[0]
    print(
        f"[shape] store_item_ids={m.all_store_item_ids()} "
        f"managed_sheets={m.all_managed_sheet_names()} "
        f"uuid_cols={[i.uuid_col for i in m.instrumentation_specs()]}"
    )
    print(
        "[modes] formula="
        + ",".join(
            f.cell.column for f in table.fields
            if f.cell is not None and f.mode.value == "formula"
        )
        + " | formula_mask="
        + ",".join(table.formula_mask)
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
