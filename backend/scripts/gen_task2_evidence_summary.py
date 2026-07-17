"""Generate a deterministic Task 2 evidence summary from the junit XML.

visibility-isolation-go-live-hardening Task 2 / R1.

The junit XML carries per-run timestamps/durations (volatile) so it is NOT hash-pinned.
Instead we derive a stable summary: sorted testcase names + pass/fail classification +
the enforce-state matrix + the config-enablement method — stripped of all volatile fields
(time, timestamp, hostname). Two generations over the same test outcomes are byte-identical.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_SPEC_DIR = Path(__file__).resolve().parents[2] / ".kiro" / "specs" / "visibility-isolation-go-live-hardening"
_JUNIT = _SPEC_DIR / "evidence" / "artifacts" / "task2" / "test_task2_editor_enforcement.junit.xml"
_OUT = _SPEC_DIR / "evidence" / "artifacts" / "task2" / "enforcement_summary.json"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    root = ET.parse(_JUNIT).getroot()
    cases = []
    for tc in root.iter("testcase"):
        name = f"{tc.get('classname')}::{tc.get('name')}"
        failed = any(child.tag in ("failure", "error") for child in tc)
        skipped = any(child.tag == "skipped" for child in tc)
        status = "failed" if failed else ("skipped" if skipped else "passed")
        cases.append({"test": name, "status": status})
    cases.sort(key=lambda c: c["test"])
    total = len(cases)
    passed = sum(1 for c in cases if c["status"] == "passed")

    summary = {
        "spec": "visibility-isolation-go-live-hardening",
        "task_id": "2. 启用编辑器令牌强制（R1）并验证 LIVE 与回退",
        "component": "H1 EnforcementEnabler",
        "enablement_method": {
            "config_key": "ONLYOFFICE_JWT_ENFORCE",
            "env_field": "APP_ENV",
            "derivation": "未显式设置时按 APP_ENV 求值：prod/production/staging→True；dev→False",
            "explicit_override": "env/.env 显式 ONLYOFFICE_JWT_ENFORCE=true|false 完全尊重原值",
            "hard_flip_default": False,
            "editor_security_logic_changed": False,
        },
        "rollback_path": "置 ONLYOFFICE_JWT_ENFORCE=false（纯配置，不需代码回滚）恢复启用前行为",
        "enforce_matrix": {
            "dev": False,
            "prod": True,
            "production": True,
            "staging": True,
            "prod_explicit_false": False,
            "dev_explicit_true": True,
        },
        "criterion_ids": [f"1.{i}" for i in range(1, 13)],
        "totals": {"total": total, "passed": passed, "failed": total - passed},
        "cases": cases,
    }
    _OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[task2-summary] wrote {_OUT} ({passed}/{total} passed)")
    return 0 if passed == total and total > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
