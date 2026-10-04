# -*- coding: utf-8 -*-
"""从各 J provider 的 `build_contract_payload()` 生成/校验磁盘契约。

spec: `j-cycle-sync-foundation-and-first-canary` · Task 22（发布链第①环）

用法：
  校验全部: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_j_contracts.py
  写盘全部: & …/python.exe backend/scripts/gen/generate_phase5_j_contracts.py --apply
  只作用一条: … generate_phase5_j_contracts.py --only j1 [--apply]

🔴 **双向锁**：契约只能从模块 payload 生成，**不得手改磁盘 json**。
各 provider 的 `assert_contract_file_matches_source()` 会在 adapter 注册路径上现算比对，
磁盘与源不一致即抛。

🔴 **写盘前必跑 `parse_contract`**（F1 教训：它的生成器只写不校验 ⇒ 磁盘契约 schema 过不了、
`assert_contract_file_matches_source()` 从未通过）。本脚本写盘即经 schema 校验。

🔴 **登记表驱动，新增一条 entry 只加一行** —— 与 `generate_phase5_i_contracts.py` /
H 的 9 家共用一个生成器同口径（G/F 是一条 entry 一份脚本，到 G2 已有 5 份、90% 逐字相同）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

#: `(标签, provider 模块名)` —— 新增 entry 只加一行。
#: 🔴 J 循环 manifest 只有 **2 条 J entry**（1 独立 + 1 parent_duplicate）⇒ 本表恒 1 行。
_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("j1", "phase5_j1_employee_compensation"),
)


def _run_one(label: str, module_name: str, *, apply: bool) -> int:
    import importlib

    mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
    payload = mod.build_contract_payload()

    # 🔴 schema 门：不合法就别写盘
    parsed = parse_contract(payload, adapter_id=mod.ADAPTER_ID)
    print(
        f"[{label}][schema] parse_contract OK: "
        f"sheets={[s.sheet_key for s in parsed.sheets]} "
        f"canonical_sha256={parsed.canonical_sha256}"
    )

    path = mod.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        print(f"[{label}][apply] wrote {path} (canonical_digest={canonical_digest(payload)})")
        return 0
    if not path.exists():
        print(f"[{label}][check] MISSING {path} —— 需 --apply 生成")
        return 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        print(
            f"[{label}][check] DRIFT disk={canonical_digest(on_disk)} "
            f"source={canonical_digest(payload)}"
        )
        return 1
    print(f"[{label}][check] OK canonical_digest={canonical_digest(payload)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写盘（缺省只校验）")
    ap.add_argument("--only", default="", help="只作用于某个标签（如 j1）")
    args = ap.parse_args()

    rows = [r for r in _PROVIDERS if not args.only or r[0] == args.only]
    if not rows:
        print(f"没有匹配 --only {args.only!r} 的 provider；已登记：{[r[0] for r in _PROVIDERS]}")
        return 2
    rc = 0
    for label, module_name in rows:
        rc |= _run_one(label, module_name, apply=args.apply)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
