# -*- coding: utf-8 -*-
"""从 `phase5_g13_fair_value_changes.build_contract_payload()` 生成/校验磁盘契约。

spec: `g-cycle-single-region-detail-lanes` · Task 12 / C-11（发布链第①环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g13_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g13_contract.py --apply

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。

🔴 G13 这一步要盯四处形态（打印出来便于核对）：
① store item 必须是 **`G13-detail-skeleton`**（分类骨架）而不是工具明细键
   `G13-detail-rows` —— 后者与模板固定 10 行不同构，接错载体会按序把第 N 条工具
   写进第 N 个损益项目行（产出错数）；
② **两级表头** ⇒ `header_rows` 必须是 **2**（横向组 B9:D9 / F9:J9）；
③ `B`/`C` 必须是 **editable**（两列只有父行 R11/R14/R17 三格有公式，列级 mode 对
   「3 行公式 + 7 行空」无解 —— 判 formula 会对 7 格抛、判 auto_source 会对 3 格抛）；
④ 行身份键是 **`rowKey`**（业务键，同 G14），不是工具明细的 `rowId`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_g13_fair_value_changes as m  # noqa: E402
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
    print(f"[header] header_rows={table.header_rows} anchor={table.anchor}")
    print(
        f"[identity] kind={table.row_identity.kind.value} "
        f"pointer={table.row_identity.json_pointer}"
    )
    by_mode: dict[str, list[str]] = {}
    for f in table.fields:
        if f.cell is not None:
            by_mode.setdefault(f.mode.value, []).append(f.cell.column)
    print("[modes] " + " | ".join(f"{k}={','.join(v)}" for k, v in sorted(by_mode.items())))
    print(f"[mask] formula_mask={list(table.formula_mask)}")
    booleans = [
        f.cell.column for f in table.fields
        if f.cell is not None and f.value_type.value == "boolean"
    ]
    print(f"[boolean] columns={booleans}（K 是核对列 =J{{r}}=D{{r}}）")

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
