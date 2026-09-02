# -*- coding: utf-8 -*-
"""生成/校验简单 checklist Excel pilot 的 per-entry contract。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 40

真源是 :mod:`app.services.workpaper_sync.pilot_simple_checklist`（它逐字段的
`source_ref` 指向权威模板 `backend/wp_templates/B/B60-1 审计项目工时预算与控制表.xlsx`
的真实单元格）。本脚本只负责把现算 payload 落成磁盘契约，或在 `--check` 下比对。

用法（仓库根）::

    py -3 backend/scripts/gen/generate_pilot_simple_checklist_contract.py --check
    py -3 backend/scripts/gen/generate_pilot_simple_checklist_contract.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402
from app.services.workpaper_sync.pilot_simple_checklist import (  # noqa: E402
    PILOT_ADAPTER_ID,
    PILOT_ENTRY_ID,
    assert_pilot_entry_selectable,
    build_contract_payload,
    contract_file_path,
)


def _render(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入磁盘契约")
    parser.add_argument("--check", action="store_true", help="只比对，不写")
    args = parser.parse_args(argv)
    if args.apply == args.check:
        parser.error("必须且只能给一个 --apply / --check")

    # 选型必要条件先在真实 manifest 上重新推导：entry 漂移时不允许生成契约。
    assert_pilot_entry_selectable()
    payload = build_contract_payload()
    contract = parse_contract(payload, adapter_id=PILOT_ADAPTER_ID)
    digest = canonical_digest(payload)
    path = contract_file_path()
    rendered = _render(payload)

    print(f"[pilot-contract] entry={PILOT_ENTRY_ID}")
    print(f"[pilot-contract] contract_id={contract.contract_id} digest={digest}")
    print(
        f"[pilot-contract] template_definition_sha256={contract.template_definition_sha256}"
    )
    print(
        "[pilot-contract] instrumentation_definition_sha256="
        f"{contract.instrumentation_definition_sha256}"
    )
    print(
        f"[pilot-contract] managed_fields={len(contract.all_fields())} "
        f"editable={len(contract.editable_field_keys())} "
        f"protected={len(contract.protected_field_keys())}"
    )

    if args.apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print(f"[pilot-contract] written {path.relative_to(_REPO)}")
        return 0

    if not path.exists():
        print(f"[pilot-contract] MISSING {path.relative_to(_REPO)} —— 先跑 --apply")
        return 1
    on_disk = path.read_text(encoding="utf-8")
    if on_disk != rendered:
        print(
            f"[pilot-contract] STALE {path.relative_to(_REPO)} —— "
            f"disk_digest={canonical_digest(json.loads(on_disk))} source_digest={digest}"
        )
        return 1
    print(f"[pilot-contract] fresh {path.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
