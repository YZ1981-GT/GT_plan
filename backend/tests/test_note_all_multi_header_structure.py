"""全量验证所有多层表头表的结构一致性。

覆盖四套模板中每张有 multi_header（合并）或 columns.group（单体）的表：
1. multi_header 每行列数 == headers 列数
2. rows 每行列数 == headers 列数（合并模板 list[list]）
3. _column_groups start+span 不越界
4. 单体 columns.group 分组的列在 headers 范围内
5. 合并模板 multi_header 与 _column_groups 一致（multi_header_to_column_groups 重算）

spec: note-template-full-alignment-with-word-authority + note-sub-table-formula-and-cross-check
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

import importlib.util

_SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed" / "seed_consol_note_sections.py"
_spec = importlib.util.spec_from_file_location("seed_consol_note_sections", _SEED_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
multi_header_to_column_groups = _mod.multi_header_to_column_groups


# ═══════════════════════════════════════════════════════════════════
# 合并模板
# ═══════════════════════════════════════════════════════════════════


def _consol_tables(std: str) -> list[dict]:
    return json.loads((DATA_DIR / f"consol_note_sections_{std}.json").read_text("utf-8"))


def _consol_mh_tables(std: str) -> list[dict]:
    return [t for t in _consol_tables(std) if t.get("multi_header")]


class TestConsolMultiHeaderAll:
    """合并模板中所有有 multi_header 的表。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_mh_row_lengths(self, std: str):
        """multi_header 每行列数 == headers 列数。"""
        errors = []
        for t in _consol_mh_tables(std):
            n = len(t["headers"])
            for ri, row in enumerate(t["multi_header"]):
                if len(row) != n:
                    errors.append(f"{t['section_id']} mh[{ri}]: {len(row)} != {n}")
        assert errors == [], f"{std}: {len(errors)} 行列数不一致\n" + "\n".join(errors[:10])

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_rows_column_count(self, std: str):
        """rows 每行列数 == headers 列数（只检查 list[list] 行）。"""
        errors = []
        for t in _consol_mh_tables(std):
            n = len(t["headers"])
            for ri, row in enumerate(t.get("rows", [])):
                if isinstance(row, list) and len(row) != n:
                    errors.append(f"{t['section_id']} row[{ri}]: {len(row)} != {n}")
        assert errors == [], f"{std}: {len(errors)} 行列数不一致\n" + "\n".join(errors[:10])

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_column_groups_bounds(self, std: str):
        """_column_groups start+span 不越界。"""
        errors = []
        for t in _consol_mh_tables(std):
            n = len(t["headers"])
            for cg in t.get("_column_groups") or []:
                end = cg["start"] + cg["span"]
                if end > n:
                    errors.append(f"{t['section_id']} cg '{cg['group']}': end {end} > {n}")
        assert errors == [], f"{std}: {len(errors)} 越界\n" + "\n".join(errors[:10])

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_column_groups_consistent_with_mh(self, std: str):
        """_column_groups 与 multi_header_to_column_groups 重算结果一致。"""
        errors = []
        for t in _consol_mh_tables(std):
            expected = multi_header_to_column_groups(t["multi_header"])
            actual = t.get("_column_groups")
            if actual != expected:
                errors.append(f"{t['section_id']}: actual={actual} != expected={expected}")
        assert errors == [], f"{std}: {len(errors)} 不一致\n" + "\n".join(errors[:10])


class TestConsolAllTablesRowWidth:
    """合并模板中所有表（含无 multi_header 的）的行列一致性。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_all_rows_match_headers(self, std: str):
        """每张表的 rows 每行列数 == headers 列数。"""
        errors = []
        for t in _consol_tables(std):
            n = len(t.get("headers", []))
            if n == 0:
                continue
            for ri, row in enumerate(t.get("rows", [])):
                if isinstance(row, list) and len(row) != n:
                    errors.append(f"{t['section_id']} row[{ri}]: {len(row)} != {n}")
        assert errors == [], f"{std}: {len(errors)} 行列数不一致\n" + "\n".join(errors[:20])


# ═══════════════════════════════════════════════════════════════════
# 单体模板
# ═══════════════════════════════════════════════════════════════════


def _standalone_data(std: str) -> dict:
    return json.loads((DATA_DIR / f"note_template_{std}.json").read_text("utf-8"))


def _standalone_tables_with_group(std: str) -> list[tuple[str, dict]]:
    """返回 (section_number, table) 列表，只含有 columns.group 的表。"""
    data = _standalone_data(std)
    result = []
    for s in data.get("sections", []):
        sn = s.get("section_number", "?")
        for t in s.get("tables", []):
            cols = t.get("columns", [])
            if any(c.get("group") for c in cols if isinstance(c, dict)):
                result.append((sn, t))
    return result


class TestStandaloneMultiHeaderAll:
    """单体模板中所有有 columns.group 的表。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_group_columns_within_headers(self, std: str):
        """columns.group 涉及的列在 headers 范围内。"""
        errors = []
        for sn, t in _standalone_tables_with_group(std):
            headers = t.get("headers", [])
            cols = t.get("columns", [])
            for ci, c in enumerate(cols):
                if not isinstance(c, dict) or c.get("is_label"):
                    continue
                # columns 的索引（跳过 is_label 后）应与 headers 对齐
                if ci >= len(headers):
                    errors.append(f"{sn} '{t.get('name','')}' col[{ci}]: 超出 headers ({len(headers)})")
        assert errors == [], f"{std}: {len(errors)} 越界\n" + "\n".join(errors[:10])

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_pre_computed_column_groups_valid(self, std: str):
        """有 _column_groups 的表，start+span 不越界。"""
        errors = []
        for sn, t in _standalone_tables_with_group(std):
            cg = t.get("_column_groups")
            if not cg:
                continue
            n = len(t.get("headers", []))
            for g in cg:
                if not isinstance(g, dict) or "start" not in g:
                    continue
                end = g["start"] + g.get("span", 1)
                if end > n:
                    errors.append(f"{sn} '{t.get('name','')}' cg '{g.get('group','')}': end {end} > {n}")
        assert errors == [], f"{std}: {len(errors)} 越界\n" + "\n".join(errors[:10])

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_group_count(self, std: str):
        """验证有 group 的表数量未退化。"""
        tables = _standalone_tables_with_group(std)
        baselines = {"soe": 69, "listed": 95}
        assert len(tables) >= baselines[std], (
            f"{std}: group 表 {len(tables)} < 基线 {baselines[std]}"
        )
