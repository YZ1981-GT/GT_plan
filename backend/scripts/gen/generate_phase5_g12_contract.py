# -*- coding: utf-8 -*-
"""从 `phase5_g12_net_hedge_gains.build_contract_payload()` 生成/校验磁盘契约。

spec: `g-cycle-single-region-detail-lanes` · Task 13 / C-12（发布链第①环）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g12_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g12_contract.py --apply

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。

🔴 G12 这一步要盯五处形态（打印出来便于核对）：
① **两级表头** ⇒ `header_rows` 必须是 **2** —— spec 原文的「无表头行」前提已被 Task 2
   实测推翻（R7/R8 是两级表头、R9 起数据），写 0 或 1 都是回退；
② `formula_mask` 必须**为空** —— 数据区 R9-R13 没有任何一列每行都有公式
   （`G` 只 R9 一格、`I` 只 R9/R10 两格）；
③ `G` 列必须是 **editable + boolean** —— 判 formula 会让 materialize 在 R10-R13 四格抛
   `ProtectedRegionWriteError`；
④ `uuid_col` 必须是 **K** —— 有效列 10（A..J）小于 `max_column=15`，按**有效列**右移一列取；
   取 `P` 会把 5 个空尾列圈进受管区；
⑤ 行身份键是 **`rowId`**（生成器后缀取 3 位，与 G11/G13 的 4 位不同）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_g12_net_hedge_gains as m  # noqa: E402
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
    print(f"[mask] formula_mask={list(table.formula_mask)}（🔴 应为空）")
    booleans = [
        f.cell.column for f in table.fields
        if f.cell is not None and f.value_type.value == "boolean"
    ]
    print(f"[boolean] columns={booleans}（G 是校验列 =D{{r}}=SUM(E{{r}}:F{{r}})）")

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
