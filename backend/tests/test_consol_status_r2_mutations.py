"""R2 前端重新汇总摘要接线的磁盘变异证明。"""
from __future__ import annotations

import subprocess
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_FRONTEND = _BACKEND.parent / "audit-platform" / "frontend"
_SOURCE = _FRONTEND / "src" / "views" / "ConsolidationIndex.vue"
_TARGET = "src/components/consolidation/__tests__/consolRefreshWiring.spec.ts"


def test_reaggregate_old_errors_mutation_is_red():
    original = _SOURCE.read_bytes()
    old = b"const summary = reaggregateSummary(result)"
    new = b"const errCount = Array.isArray(result.errors) ? result.errors.length : 0"
    assert old in original
    _SOURCE.write_bytes(original.replace(old, new, 1))
    try:
        result = subprocess.run(
            ["npx.cmd", "vitest", "run", _TARGET],
            cwd=_FRONTEND,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        assert result.returncode != 0, "合并总览恢复读取 result.errors 后 wiring 守卫仍全绿"
    finally:
        _SOURCE.write_bytes(original)
        assert _SOURCE.read_bytes() == original
