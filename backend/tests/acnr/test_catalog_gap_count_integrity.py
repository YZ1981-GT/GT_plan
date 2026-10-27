"""目录报告结构守卫 `check_acnr_catalog_drift.py`（acnr-foundation-defect-closure T09，design §7.1 / R2-N2）。

旧版守的是 gap_count 守恒与 generated_at 陈旧度；T09 把报告改为四组 `{count, items}`，gap_count 等旧字段删除，
陈旧度判据与「内容不变不重写」的幂等规则冲突也删除。本文件改为：四组 count == len(items)、summary 一致、
blocking 为 0；读真实报告的用例（TestRealCatalogReport）断言同一判据。脚本经子进程跑并断言输出内容。
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_SCRIPT = _BACKEND / "scripts" / "check" / "check_acnr_catalog_drift.py"
_REPORT = _BACKEND / "data" / "acnr" / "catalog_report.json"
sys.path.insert(0, str(_SCRIPT.parent))

from check_acnr_catalog_drift import check_report  # noqa: E402


def _report(**groups: list) -> dict:
    out = {name: {"count": len(items), "items": items} for name, items in groups.items()}
    for name in ("blocking", "acknowledged", "deprecated", "info"):
        out.setdefault(name, {"count": 0, "items": []})
    out["summary"] = {"total_sheets": 1, "total_cells": 0, **{n: out[n]["count"] for n in ("blocking", "acknowledged", "deprecated", "info")}}
    return out


class TestBucketStructure:
    def test_empty_report_ok(self):
        assert check_report(_report()) == []

    def test_count_must_equal_len(self):
        r = _report(info=[{"kind": "x"}])
        r["info"]["count"] = 0
        assert any("info.count=0 与 items 条数 1 不符" in e for e in check_report(r))

    def test_summary_must_match(self):
        r = _report(deprecated=[{"addr_id": "A/A"}])
        r["summary"]["deprecated"] = 5
        assert any("summary.deprecated=5" in e for e in check_report(r))

    def test_missing_group_reported(self):
        r = _report()
        del r["acknowledged"]
        assert any("缺少分组 acknowledged" in e for e in check_report(r))

    def test_blocking_nonzero_reported(self):
        r = _report(blocking=[{"check": "alias", "addr_id": "", "detail": "未登记别名键「X」未处置"}])
        assert any("blocking=1" in e and "未处置" in e for e in check_report(r))


class TestRealCatalogReport:
    @pytest.fixture
    def real_report(self) -> dict:
        return json.loads(_REPORT.read_text(encoding="utf-8"))

    def test_real_report_buckets_consistent_and_blocking_zero(self, real_report):
        assert check_report(real_report) == []
        assert real_report["summary"]["blocking"] == 0

    def test_old_fields_removed(self, real_report):
        for key in ("gaps", "alias_conflicts", "unregistered_aliases", "acknowledged_conflicts", "manifest_blocked"):
            assert key not in real_report, key
        assert set(real_report["summary"]) == {"total_sheets", "total_cells", "blocking", "acknowledged", "deprecated", "info"}

    def test_script_strict_exit_codes_and_output(self, real_report, tmp_path):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        ok = subprocess.run([sys.executable, str(_SCRIPT), "--strict"], capture_output=True, env=env)
        out = ok.stdout.decode("utf-8", errors="replace")
        assert ok.returncode == 0 and "[OK] 四组分组结构一致，blocking 为 0" in out, out
        bad = copy.deepcopy(real_report)
        bad["info"]["count"] += 1
        p = tmp_path / "catalog_report.json"
        p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        red = subprocess.run([sys.executable, str(_SCRIPT), "--strict", "--report-path", str(p)], capture_output=True, env=env)
        out = red.stdout.decode("utf-8", errors="replace")
        assert red.returncode == 1 and "info.count=" in out and "[FAIL]" in out, out
