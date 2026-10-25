# -*- coding: utf-8 -*-
"""从 `phase5_g1_trading_financial_assets.build_contract_payload()` 生成/校验磁盘契约。

spec: `g-cycle-single-region-detail-lanes` · Task 14 / C-13（发布链第①环，九条最后一条）

用法：
  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g1_contract.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_g1_contract.py --apply

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。

🔴 G1 这一步要盯五处形态（打印出来便于核对）：
① **三个 tables**（区①②③）共用一个 `store_item_id`，`row_section_value` 逐区不同；
② 🔴 区① 的 `formula_mask` 比区②③ **多一列 `T`** —— 那是跨表公式（引 `公允价值测试表G1-6`），
   区②③ 的 `T` 整格无公式 ⇒ 判 `editable`。三区共用一份 formula_columns 就是 P6 要打红的漂移；
③ `header_rows` 必须是 **2**；
④ 三区 `uuid_col` 必须**互不相同**（AB/AC/AD）—— 同一格会让三区互相覆盖；
⑤ payload 列是 **`conclusion`**（`conclusion_only` 族，与另七条的 remark 相反）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import (  # noqa: E402
    phase5_g1_trading_financial_assets as m,
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
        f"managed_sheets={m.all_managed_sheet_names()} "
        f"uuid_cols={[i.uuid_col for i in m.instrumentation_specs()]}"
    )
    print(f"[payload] column={m.PAYLOAD_COLUMN} mode={m.PAYLOAD_COLUMN_MODE}")
    for sheet in parsed.sheets:
        for table in sheet.tables:
            by_mode: dict[str, list[str]] = {}
            for f in table.fields:
                if f.cell is not None:
                    by_mode.setdefault(f.mode.value, []).append(f.cell.column)
            ident = table.row_identity
            ident_str = f"identity={ident.kind.value} pointer={ident.json_pointer}" if ident else "identity=none"
            print(
                f"[table] {table.table_key}: header_rows={table.header_rows} "
                f"anchor={table.anchor} {ident_str}"
            )
            print(f"         mask={list(table.formula_mask)}")
            print(
                "         "
                + " | ".join(f"{k}={','.join(v)}" for k, v in sorted(by_mode.items()))
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
