"""R1 stale 单一写入口的磁盘变异证明。"""
from __future__ import annotations

from pathlib import Path

from tests.test_consol_status_mutations import _assert_mutation_is_red

_BACKEND = Path(__file__).resolve().parents[1]
_NOTES = _BACKEND / "app" / "services" / "consol_push_notes.py"
_DETAIL = _BACKEND / "app" / "services" / "consol_note_detail_apply_service.py"
_FORMULA = _BACKEND / "app" / "services" / "consol_note_formula_service.py"
_GUARD = "tests/test_consol_note_stale_writers_guard.py"


def test_batch_mark_without_reason_is_red():
    _assert_mutation_is_red(
        _NOTES,
        b".values(**stale_values(ConsolNoteStaleSource.CONSOL_PUSH))",
        b".values(is_stale=True)",
        "推送批量置位不写 stale_reason",
        _GUARD,
    )


def test_clear_without_reason_is_red():
    _assert_mutation_is_red(
        _DETAIL,
        b"clear_stale(note_record)",
        b"note_record.is_stale = False",
        "清除 stale 时丢失原因和时间",
        _GUARD,
    )


def test_copy_without_inheriting_reason_is_red():
    _assert_mutation_is_red(
        _FORMULA,
        b"**inherit_values(source),",
        b"is_stale=bool(source.is_stale),",
        "复制节点行不继承 stale_reason/stale_at",
        _GUARD,
    )


def test_frontend_stale_tag_render_mutation_is_red():
    import subprocess
    import sys

    frontend = _BACKEND.parent / "audit-platform" / "frontend"
    source = frontend / "src" / "components" / "consolidation" / "ConsolNoteTab.vue"
    original = source.read_bytes()
    old = b':is-stale="selectedNoteSection.isStale"'
    assert old in original
    source.write_bytes(original.replace(old, b':is-stale="false"', 1))
    try:
        command = [
            "npx.cmd", "vitest", "run",
            "src/components/consolidation/__tests__/ConsolNoteTab.spec.ts",
            "-t", "待更新原因标签",
        ]
        result = subprocess.run(
            command,
            cwd=frontend,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        assert result.returncode != 0, "前端移除 stale 标签渲染后，标签回归仍全绿"
    finally:
        source.write_bytes(original)
        assert source.read_bytes() == original
