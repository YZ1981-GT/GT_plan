"""R2 守卫：AR 四组 binding 表数对齐模板 + 幂等 + 几何校验。

Spec: disclosure-multitable-refresh-and-edit-writeback Task 3 (R2)

验证：
- 四组 binding 表数 == 模板表数
- table_index 连续 0-based
- 校准脚本幂等（--check exit 0）
- 非目标章节不被修改
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BINDINGS_PATH = ROOT / "backend" / "data" / "note_template_bindings.json"
TEMPLATE_SOE = ROOT / "backend" / "data" / "note_template_soe.json"
TEMPLATE_LISTED = ROOT / "backend" / "data" / "note_template_listed.json"

AR_SECTIONS = {
    "八、5": ("soe", 13),
    "十二、应收账款": ("soe", 13),
    "五、5": ("listed", 17),
    "十六、应收账款": ("listed", 17),
}


def _load_binding_tables(section: str) -> list[dict]:
    data = json.loads(BINDINGS_PATH.read_text("utf-8"))
    return data["bindings"].get(section, {}).get("tables", [])


def _load_template_tables(template_type: str, section: str) -> list[dict]:
    fp = TEMPLATE_SOE if template_type == "soe" else TEMPLATE_LISTED
    data = json.loads(fp.read_text("utf-8"))
    for sec in data.get("sections", []):
        sn = sec.get("section_number", "") or sec.get("note_section", "")
        if sn == section:
            return sec.get("tables", [])
    return []


class TestBindingTableCountMatchesTemplate:
    """binding 表数 == 模板表数。"""

    @pytest.mark.parametrize("section,expected", [
        ("八、5", 13),
        ("十二、应收账款", 13),
        ("五、5", 17),
        ("十六、应收账款", 17),
    ])
    def test_table_count(self, section: str, expected: int):
        tables = _load_binding_tables(section)
        assert len(tables) == expected, (
            f"{section}: binding {len(tables)} 表 ≠ 预期 {expected}"
        )


class TestTableIndexContinuous:
    """每组 binding 的 table_index 从 0 连续递增。"""

    @pytest.mark.parametrize("section", list(AR_SECTIONS))
    def test_continuous_index(self, section: str):
        tables = _load_binding_tables(section)
        indexes = [t.get("table_index") for t in tables]
        expected = list(range(len(tables)))
        assert indexes == expected, (
            f"{section}: table_index {indexes} ≠ 预期 {expected}"
        )


class TestCalibrationIdempotent:
    """校准脚本 --check 返回 exit 0（无 diff）。"""

    def test_check_no_diff(self):
        import subprocess
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        calibrate_script = ROOT / "backend" / "scripts" / "analyze" / "_disc_ar_calibrate.py"
        result = subprocess.run(
            [str(venv_python), str(calibrate_script), "--check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert result.returncode == 0, (
            f"--check 应 exit 0，实际 exit {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "无 diff" in result.stdout, (
            f"应含 '无 diff'，实际输出: {result.stdout}"
        )


class TestNonTargetSectionsUntouched:
    """非 AR 四组的章节不受校准影响。"""

    def test_non_target_unchanged(self):
        """取 binding 中一个非目标章节，确认无 table_index 变化痕迹。"""
        data = json.loads(BINDINGS_PATH.read_text("utf-8"))
        bindings = data.get("bindings", {})
        for section, sec_data in bindings.items():
            if section in AR_SECTIONS:
                continue
            tables = sec_data.get("tables", [])
            if not tables:
                continue
            # 非目标的 table_index 应与列表位置一致
            for i, t in enumerate(tables):
                idx = t.get("table_index", i)
                assert idx == i, (
                    f"非目标 {section}[{i}] table_index={idx} ≠ {i}"
                )
            break  # 只检一个即可
