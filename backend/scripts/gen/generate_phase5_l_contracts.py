# -*- coding: utf-8 -*-
"""从 L 循环各 provider 的 `build_contract_payload()` 生成/校验磁盘契约。

spec: l-cycle-true-adapter-registration（Task 5）

多 entry 合一（对标 `generate_phase5_h_contracts.py` / `i_contracts.py` / `j_contracts.py`），
不为每条 entry 建单独脚本 —— L 循环后续 L2~L8 接线时只往 `_PROVIDERS` 里加一行。

用法::

  校验: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_l_contracts.py
  写盘: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_l_contracts.py --apply
  单条: ... generate_phase5_l_contracts.py --only l1.short_term_loans --apply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import (  # noqa: E402
    phase5_l1_short_term_loans as _l1,
    phase5_l3_long_term_loans as _l3,
    phase5_l4_bonds_payable as _l4,
)
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

#: adapter_id → provider 模块。L2~L8 接线时在此追加。
_PROVIDERS = {
    _l1.ADAPTER_ID: _l1,
    _l3.ADAPTER_ID: _l3,
    _l4.ADAPTER_ID: _l4,
}


def _run_one(module, *, apply: bool) -> tuple[bool, str]:
    payload = module.build_contract_payload()
    path = module.contract_file_path()
    digest = canonical_digest(payload)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        # 🔴 `write_bytes` 而非 `write_text`：Windows 上后者按 `\r\n` 写回，
        # CRLF 会被双向锁（assert_contract_file_matches_source）漏掉。
        path.write_bytes(text.encode("utf-8"))
        return True, f"[apply] wrote {path.name} (canonical_digest={digest})"
    if not path.exists():
        return False, f"[check] MISSING {path.name} —— 需 --apply 生成"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        return False, (
            f"[check] DRIFT {path.name} disk={canonical_digest(on_disk)} source={digest}"
        )
    return True, f"[check] OK {path.name} canonical_digest={digest}"


def _stale_candidates() -> list[Path]:
    """已转 reviewed 的 adapter 仍留着 `.candidate.json` ⇒ 双源，必须清掉。"""
    out: list[Path] = []
    for adapter_id, module in _PROVIDERS.items():
        candidate = module.contract_file_path().with_name(f"{adapter_id}.candidate.json")
        if candidate.exists():
            out.append(candidate)
    return out


def main() -> int:
    argv = sys.argv[1:]
    apply = "--apply" in argv
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]

    targets = {k: v for k, v in _PROVIDERS.items() if only is None or k == only}
    if not targets:
        print(f"[error] --only {only!r} 未匹配任何 provider，可选：{sorted(_PROVIDERS)}")
        return 2

    rc = 0
    for adapter_id in sorted(targets):
        ok, msg = _run_one(targets[adapter_id], apply=apply)
        print(msg)
        if not ok:
            rc = 1

    for stale in _stale_candidates():
        print(
            f"[error] {stale.name} 仍在 —— 该 adapter 已交付 reviewed 生产契约，"
            "candidate 必须删除（两份同源契约会让 review_status 门失效）"
        )
        rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
