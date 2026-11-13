"""R5 前端调整审批回执的磁盘变异证明。"""
from __future__ import annotations

import subprocess
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_FRONTEND = _BACKEND.parent / "audit-platform" / "frontend"
_SOURCE = _FRONTEND / "src" / "composables" / "useAdjustmentHallActions.ts"
_TARGET = "src/composables/__tests__/useAdjustmentHallActions.spec.ts"


def _assert_red(old: bytes, new: bytes, label: str) -> None:
    original = _SOURCE.read_bytes()
    assert old in original, f"{label} 变异靶点不存在"
    _SOURCE.write_bytes(original.replace(old, new, 1))
    try:
        result = subprocess.run(
            ["npx.cmd", "vitest", "run", _TARGET, "-t", "审批回执"],
            cwd=_FRONTEND,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        assert result.returncode != 0, f"{label} 变异存活：\n{(result.stdout + result.stderr)[-4000:]}"
    finally:
        _SOURCE.write_bytes(original)
        assert _SOURCE.read_bytes() == original


def test_tb_status_summary_mutation_is_red():
    _assert_red(
        b"const committed = statuses.filter((status) => status === 'committed').length",
        b"const committed = 0",
        "删除 tb_update_status 汇总",
    )


def test_downstream_failed_warning_mutation_is_red():
    _assert_red(
        b"if (downstream && downstream.failed > 0)",
        b"if (downstream && downstream.failed < 0)",
        "删除 downstream.failed 警告",
    )
