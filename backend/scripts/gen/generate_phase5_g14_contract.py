# -*- coding: utf-8 -*-
"""从 `phase5_g14_credit_impairment.build_contract_payload()` 生成/校验磁盘契约。

spec: `g-cycle-single-region-detail-lanes` · Task 10 / C-9（发布链第①环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g14_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g14_contract.py --apply

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。
`assert_contract_file_matches_source()` 会在 adapter 注册路径上现算比对。

🔴 写盘前先跑 `parse_contract`（照 G2/G9/G10/G8 生成器）。G14 这一步要盯两处形态：
① 行身份是 **`rowKey`**（`stable_template_row_key`，全 G 循环唯一）—— 打印出来便于核对
   没被误写成 `rowId`；
② `L` 列是**布尔**校验列（`value_type=boolean` + `mode=formula`，裁决 G1R-H4）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_g14_credit_impairment as m  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    payload = m.build_contract_payload()

    parsed = parse_contract(payload, adapter_id=m.ADAPTER_ID)
    table = parsed.sheets[0].tables[0]
    print(
        f"[schema] parse_contract OK: sheets={[s.sheet_key for s in parsed.sheets]} "
        f"tables={[[t.table_key for t in s.tables] for s in parsed.sheets]} "
        f"canonical_sha256={parsed.canonical_sha256}"
    )
    print(
        f"[shape] store_item_ids={m.all_store_item_ids()} "
        f"managed_sheets={m.all_managed_sheet_names()} "
        f"uuid_cols={[i.uuid_col for i in m.instrumentation_specs()]}"
    )
    print(
        f"[identity] kind={table.row_identity.kind.value} "
        f"pointer={table.row_identity.json_pointer}"
    )
    print(
        "[modes] formula="
        + ",".join(
            f.cell.column for f in table.fields
            if f.cell is not None and f.mode.value == "formula"
        )
        + " | boolean="
        + ",".join(
            f.cell.column for f in table.fields
            if f.cell is not None and f.value_type.value == "boolean"
        )
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
