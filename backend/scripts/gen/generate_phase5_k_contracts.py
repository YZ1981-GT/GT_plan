# -*- coding: utf-8 -*-
"""从 K 循环各 provider 的 `build_contract_payload()` 生成/校验磁盘契约。

spec: k-cycle-sync-foundation-and-first-canary（Task 22）·
      k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub（Task 18）·
      k1-k7-inlined-iife-hosts-and-orphan-cleanup（Task 12）

对标 `generate_phase5_l_contracts.py`：多 entry 合一，K 后续 entry 接线时只往
`_PROVIDERS` 里加一行。

用法::

  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_k_contracts.py
  写盘: ... generate_phase5_k_contracts.py --apply
  单条: ... generate_phase5_k_contracts.py --only k10.other_income_adjustment --apply
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

#: provider 模块（adapter_id 从模块常量现取，不写第二份）。
_MODULES = (
    "app.services.workpaper_sync.phase5_k1_baddebt_reversal_writeoff",
    "app.services.workpaper_sync.phase5_k8_selling_expenses",
    "app.services.workpaper_sync.phase5_k9_admin_expenses",
    "app.services.workpaper_sync.phase5_k10_other_income",
    "app.services.workpaper_sync.phase5_k11_asset_impairment_loss",
    "app.services.workpaper_sync.phase5_k12_non_operating_income",
    "app.services.workpaper_sync.phase5_k13_non_operating_expense",
)


def _providers() -> dict[str, object]:
    out: dict[str, object] = {}
    for name in _MODULES:
        mod = importlib.import_module(name)
        out[str(getattr(mod, "ADAPTER_ID"))] = mod
    return out


def _run_one(module, *, apply: bool) -> tuple[bool, str]:
    payload = module.build_contract_payload()
    path = module.contract_file_path()
    digest = canonical_digest(payload)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        # 🔴 write_bytes：Windows 上 write_text 会写 CRLF，被双向锁漏掉。
        path.write_bytes(text.encode("utf-8"))
        return True, f"[apply] wrote {path.name} (canonical_digest={digest})"
    if not path.exists():
        return False, f"[check] MISSING {path.name} —— 需 --apply 生成"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != digest:
        return False, f"[check] DRIFT {path.name} disk={canonical_digest(on_disk)} source={digest}"
    return True, f"[check] OK {path.name} canonical_digest={digest}"


def main() -> int:
    argv = sys.argv[1:]
    apply = "--apply" in argv
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    providers = _providers()
    targets = {k: v for k, v in providers.items() if only is None or k == only}
    if not targets:
        print(f"[error] --only {only!r} 未匹配，可选：{sorted(providers)}")
        return 2
    rc = 0
    for adapter_id in sorted(targets):
        ok, msg = _run_one(targets[adapter_id], apply=apply)
        print(msg)
        rc |= 0 if ok else 1
    for adapter_id, module in providers.items():
        stale = module.contract_file_path().with_name(f"{adapter_id}.candidate.json")
        if stale.exists():
            print(
                f"[error] {stale.name} 仍在 —— 已交付 reviewed 生产契约，candidate 必须删除"
                "（两份同源契约会让 review_status 门失效）"
            )
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
