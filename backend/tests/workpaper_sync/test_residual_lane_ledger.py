"""Task 4.1 residual lane 交接清册守卫（AC 12.1, 12.8, 12.9）。

守的是清册本身的结构完整性与一致性，不是 per-entry 对账（那是 4.2~4.8 的事）。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent

LEDGER_PATH = _BACKEND / "data" / "workpaper_sync_residual_lane_ledger.json"
CURRENT_STATE_PATH = _BACKEND / "data" / "workpaper_sync_current_state.json"
MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
GENERATOR = _BACKEND / "scripts" / "gen" / "generate_residual_lane_ledger.py"


@pytest.fixture(scope="module")
def ledger() -> dict:
    assert LEDGER_PATH.is_file(), f"{LEDGER_PATH.name} 不在 —— 先 --write"
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def current_state() -> dict:
    return json.loads(CURRENT_STATE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_every_independent_entry_has_a_row(ledger: dict, current_state: dict) -> None:
    """清册必须覆盖全部 independent entry，不漏项。"""
    cs_ids = {e["entry_id"] for e in current_state["entries"] if e.get("independent_entry")}
    ledger_ids = {e["entry_id"] for e in ledger["entries"]}
    assert cs_ids == ledger_ids, (
        f"清册缺 {sorted(cs_ids - ledger_ids)[:5]} / 多 {sorted(ledger_ids - cs_ids)[:5]}"
    )


def test_every_row_has_required_fields(ledger: dict) -> None:
    """每行必须含全部交接字段。"""
    required = {
        "entry_id", "owner_task", "cycle", "capability", "migration_state",
        "host_path", "representation_status", "rollback_condition", "release_condition",
    }
    for row in ledger["entries"]:
        missing = required - set(row)
        assert not missing, f"{row['entry_id']} 缺字段 {sorted(missing)}"


def test_owner_task_covers_all_cycles(ledger: dict) -> None:
    """每个循环字母都有对应的 owner_task。"""
    cycles = {row["cycle"] for row in ledger["entries"] if row["cycle"]}
    # 至少 D~N + A/B/C/S = 14 个字母
    assert len(cycles) >= 14, f"只覆盖 {len(cycles)} 个循环字母 —— 有 entry 漏分"


def test_no_parent_duplicates_in_ledger(ledger: dict, manifest: dict) -> None:
    """parent duplicates 不进清册（它们跟随 effective_entry_id）。"""
    parent_ids = {
        e["entry_id"] for e in manifest["entries"]
        if e.get("parent_entry_id") and not e.get("independent_entry", True)
    }
    ledger_ids = {e["entry_id"] for e in ledger["entries"]}
    overlap = parent_ids & ledger_ids
    assert not overlap, f"parent duplicate 混进清册：{sorted(overlap)[:5]}"


def test_summary_matches_entries(ledger: dict) -> None:
    """summary 计数必须与 entries 一致。"""
    assert ledger["summary"]["independent_entry_count"] == len(ledger["entries"])
    by_owner = ledger["summary"]["by_owner_task"]
    actual: dict[str, int] = {}
    for row in ledger["entries"]:
        actual[row["owner_task"]] = actual.get(row["owner_task"], 0) + 1
    for ot, stats in by_owner.items():
        assert stats["total"] == actual.get(ot, 0), f"{ot} total 不一致"


def test_check_mode_passes() -> None:
    """`--check` 必须通过且输出有内容。"""
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=str(_REPO),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=900,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, f"--check 失败：{out[-400:]}"
    assert "逐字节一致" in out, f"--check 没输出比对结论：{out[-300:]}"


def test_input_digest_matches_disk(ledger: dict) -> None:
    """输入 digest 必须与磁盘文件一致——上游变了清册要重生成。"""
    actual_cs = hashlib.sha256(CURRENT_STATE_PATH.read_bytes()).hexdigest()
    assert ledger["input_digests"]["current_state"] == actual_cs
    actual_m = hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    assert ledger["input_digests"]["manifest"] == actual_m
