"""切换耗时报告工具的离线守卫（spec workpaper-sync-switch-performance · 需求 1.4）。"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts/analyze/report_sync_switch_timings.py"


def _module():
    spec = importlib.util.spec_from_file_location("report_sync_switch_timings", _PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


T0 = datetime(2026, 10, 11, 11, 0, tzinfo=timezone.utc)


def test_html_to_oo_reports_the_path_taken() -> None:
    mod = _module()
    rows = [
        {"direction": "html_to_oo", "state": "applied", "created_at": T0,
         "finished_at": T0 + timedelta(seconds=1.5), "last_stage": "business_identity_reused"},
        {"direction": "html_to_oo", "state": "applied", "created_at": T0,
         "finished_at": T0 + timedelta(seconds=14), "last_stage": "descriptor_issued"},
        {"direction": "html_to_oo", "state": "applied", "created_at": T0,
         "finished_at": T0 + timedelta(seconds=0.4), "last_stage": "store_fingerprint_reused"},
        {"direction": "html_to_oo", "state": "error", "created_at": T0, "finished_at": None,
         "last_stage": "content_commit", "error_code": "x"},
    ]
    out = mod.summarize(rows)
    assert [r["path"] for r in out] == ["业务身份复用", "全量物化", "store 指纹直通", "content_commit"]
    assert [r["total_s"] for r in out] == [1.5, 14.0, 0.4, None]
    assert out[3]["error_code"] == "x"


def test_oo_to_html_splits_durable_and_apply() -> None:
    mod = _module()
    row = {
        "direction": "oo_to_html", "state": "applied", "created_at": T0,
        "durable_at": T0 + timedelta(seconds=1.4),
        "application_finished_at": T0 + timedelta(seconds=23.5),
        "finished_at": T0 + timedelta(seconds=23.5),
    }
    (rec,) = mod.summarize([row])
    assert rec["durable_s"] == 1.4 and rec["apply_s"] == 22.1 and rec["total_s"] == 23.5
    assert "落盘=1.4s" in mod.render([rec])


def test_empty_result_renders_a_placeholder() -> None:
    mod = _module()
    assert mod.render(mod.summarize([])) == "（无记录）"


def test_the_query_is_read_only() -> None:
    mod = _module()
    sql = mod._SQL.upper()
    for verb in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE"):
        assert verb not in sql
