#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""净化 G4 债权投资权威模板的外部链接（过首版发布 OOXML `external_relationships` 门）。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 11

范式：照 `sanitize_n4_template_external_links.py` / `sanitize_i_cycle_template_external_links.py`
—— `backend/wp_templates/` 运行时只读，模板真要升级必须显式净化 + 留 `.preclean.bak`
+ 重算 sha256 + 重生成契约 + 重发布。**复用 I 循环的 `sanitize_bytes` 内核**。

用法（仓库根）：
  & .venv/Scripts/python.exe backend/scripts/fix/sanitize_g4_template_external_links.py          # 预演
  & .venv/Scripts/python.exe backend/scripts/fix/sanitize_g4_template_external_links.py --apply  # 写盘 + .bak
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "backend"))

from scripts.fix.sanitize_i_cycle_template_external_links import sanitize_bytes  # noqa: E402

_TPL_DIR = _REPO / "backend" / "wp_templates" / "G"
_TEMPLATE = "G4 债权投资.xlsx"
_MANAGED_SHEETS = ["明细表G4-2", "有价证券盘点表G4-7", "债权投资三阶段划分G4-9"]


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    path = _TPL_DIR / _TEMPLATE
    before = path.read_bytes()
    sha_before = hashlib.sha256(before).hexdigest()
    print(f"[before] {_TEMPLATE}: {len(before):,} bytes, sha256={sha_before[:16]}…")

    after, facts = sanitize_bytes(before)
    sha_after = hashlib.sha256(after).hexdigest()
    print(f"[after]  {_TEMPLATE}: {len(after):,} bytes, sha256={sha_after[:16]}…")
    print(f"[facts]  {facts}")

    if after == before:
        print("[skip] 无变更")
        return 0

    if not apply:
        print("[dry-run] 需要 --apply 才写盘")
        return 0

    bak = path.with_suffix(".preclean.bak")
    if not bak.exists():
        bak.write_bytes(before)
        print(f"[backup] {bak.name}")
    path.write_bytes(after)
    print(f"[apply] wrote {path.name}")
    print(f"[NOTE] 新 sha256={sha_after}")
    print(f"  需要更新 phase5_g4_bond_investment.py 的 TEMPLATE_SHA256")
    print(f"  需要更新 phase5_g4_ecl_entry.py（通过 import 共用）")
    print(f"  然后重生成契约: python backend/scripts/gen/generate_phase5_g4_contract.py --apply")
    print(f"  然后重生成契约: python backend/scripts/gen/generate_phase5_g4_ecl_contract.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
