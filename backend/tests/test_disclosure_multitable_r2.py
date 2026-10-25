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

# 2026-10-25 国企 13 → 15（spec consol-note-header-library-and-node-reaggregate R8.4 批 9b-2：两张组合计提表按底稿
# 拆成期末 / 「（续：期初数）」两张；母公司章 十二、应收账款 同步）
AR_SECTIONS = {
    "八、5": ("soe", 15),
    "十二、应收账款": ("soe", 15),
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

    @pytest.mark.parametrize("section,expected", [(s, n) for s, (_, n) in AR_SECTIONS.items()])
    def test_table_count(self, section: str, expected: int):
        tables = _load_binding_tables(section)
        assert len(tables) == expected, (
            f"{section}: binding {len(tables)} 表 ≠ 预期 {expected}"
        )

    @pytest.mark.parametrize("section", list(AR_SECTIONS))
    def test_binding_tables_follow_template_order(self, section: str):
        """binding 按 table_index 消费（get_binding_for_table）⇒ 表名逐位与模板相同，否则取数套到别的表上。"""
        template_type, _ = AR_SECTIONS[section]
        names = [t.get("name") for t in _load_template_tables(template_type, section)]
        assert [t.get("table_name") for t in _load_binding_tables(section)] == names


#: 表名 / 表头列数与模板逐位不齐的 binding 章节（既有欠账，只许删不许加）：两版同号的「十一、关联交易情况」
#: 「十一、关联方应收应付款项」binding 只能存一份，两版表清单不同（不是本 spec 改的）
_KNOWN_MISALIGNED = {"十一、关联交易情况", "十一、关联方应收应付款项"}


def _all_template_tables() -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {}
    for std, fp in (("listed", TEMPLATE_LISTED), ("soe", TEMPLATE_SOE)):
        data = json.loads(fp.read_text("utf-8"))
        out[std] = {s.get("section_number"): s.get("tables") or [] for s in data.get("sections", [])}
    return out


def test_every_binding_section_follows_its_template_by_index():
    """全部 binding 章节：表名、表头列数逐位与模板相同（两版同号时两版都按这一份 binding 生成 ⇒ 两版都要齐）。

    2026-10-25 批 9b-2：9b-1 改了 五、23 / 五、62 / 八、14 / 八、18 / 八、42 等的表清单没同步 binding，取数按 index
    套到别的表上；本批逐节对齐后加此守卫（模板改表清单必须同改 binding）。
    """
    templates = _all_template_tables()
    data = json.loads(BINDINGS_PATH.read_text("utf-8"))
    bad = []
    for key, sec in data["bindings"].items():
        mine = [(t.get("table_name"), len(t.get("header_normalize") or [])) for t in sec.get("tables") or []]
        variants = [[(t.get("name"), len(t.get("headers") or [])) for t in tables]
                    for std in ("listed", "soe") if (tables := templates[std].get(key))]
        if not variants or any(mine != v for v in variants):
            bad.append(key)
    assert set(bad) == _KNOWN_MISALIGNED, f"新增不齐 {sorted(set(bad) - _KNOWN_MISALIGNED)}；已修好可删 {sorted(_KNOWN_MISALIGNED - set(bad))}"


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
        if not calibrate_script.exists():
            pytest.skip("校准脚本 _disc_ar_calibrate.py 已删除（一次性脚本）")
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
