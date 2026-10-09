"""附注模板 JSON 与 Word 权威源对齐守卫。

验证:
1. 合并模板中 multi_header 非 null 的表都有一致的 _column_groups
2. multi_header 中无换行符
3. headers 列数 == multi_header 每行列数
4. 合并模板覆盖率基线（表总数不退化）

spec: note-template-full-alignment-with-word-authority
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# ─── 导入 multi_header_to_column_groups ────────────────────────────
import importlib.util

_SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed" / "seed_consol_note_sections.py"
_spec = importlib.util.spec_from_file_location("seed_consol_note_sections", _SEED_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
multi_header_to_column_groups = _mod.multi_header_to_column_groups


# ─── 合并模板基线 ──────────────────────────────────────────────────
# 2026-10-09: P0-P3 全量对齐后的基线
CONSOL_BASELINES = {
    "soe": {"total": 321, "with_mh": 37},
    "listed": {"total": 432, "with_mh": 115},
}


class TestConsolMultiHeaderConsistency:
    """合并模板 multi_header / _column_groups 一致性。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_mh_tables_have_correct_column_groups(self, std: str):
        """有 multi_header 的表 _column_groups 必须与 multi_header_to_column_groups() 结果一致。"""
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data:
            mh = t.get("multi_header")
            if not mh:
                continue
            expected_cg = multi_header_to_column_groups(mh)
            actual_cg = t.get("_column_groups")
            assert actual_cg == expected_cg, (
                f"{std} {t['section_id']}: _column_groups 不一致\n"
                f"  expected: {expected_cg}\n  actual: {actual_cg}"
            )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_no_mh_no_column_groups(self, std: str):
        """无 multi_header 的表不应有 _column_groups。"""
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data:
            if not t.get("multi_header"):
                assert "_column_groups" not in t, (
                    f"{std} {t['section_id']}: 无 multi_header 却有 _column_groups"
                )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_no_newlines_in_multi_header(self, std: str):
        """multi_header 中不得有换行符。"""
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data:
            mh = t.get("multi_header")
            if not mh:
                continue
            for ri, row in enumerate(mh):
                for ci, cell in enumerate(row):
                    if cell:
                        assert "\n" not in cell, (
                            f"{std} {t['section_id']} mh[{ri}][{ci}]: "
                            f"含换行符 {repr(cell)}"
                        )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_mh_row_lengths_match_headers(self, std: str):
        """multi_header 每行列数 == headers 列数。"""
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data:
            mh = t.get("multi_header")
            if not mh:
                continue
            n_hdr = len(t.get("headers", []))
            for ri, row in enumerate(mh):
                assert len(row) == n_hdr, (
                    f"{std} {t['section_id']} mh[{ri}]: "
                    f"{len(row)} cols != headers {n_hdr} cols"
                )


class TestConsolCoverageBaseline:
    """合并模板覆盖率基线——只许增不许减。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_total_tables_not_regressed(self, std: str):
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        baseline = CONSOL_BASELINES[std]["total"]
        assert len(data) >= baseline, (
            f"{std}: 表总数 {len(data)} < 基线 {baseline}，不允许退化"
        )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_mh_count_not_regressed(self, std: str):
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        with_mh = sum(1 for t in data if t.get("multi_header"))
        baseline = CONSOL_BASELINES[std]["with_mh"]
        assert with_mh >= baseline, (
            f"{std}: multi_header 表数 {with_mh} < 基线 {baseline}，不允许退化"
        )


class TestStandaloneGroupCoverage:
    """单体模板 columns.group / flat 覆盖完整性。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_all_tables_have_group_or_flat(self, std: str):
        """每张有 columns 的表都应该有 group 或 flat 标记。"""
        path = DATA_DIR / f"note_template_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        gaps = []
        for s in data.get("sections", []):
            for ti, t in enumerate(s.get("tables", [])):
                cols = t.get("columns", [])
                if not cols:
                    continue
                has_group = any(c.get("group") for c in cols if isinstance(c, dict))
                has_flat = any(c.get("flat") for c in cols if isinstance(c, dict))
                if not has_group and not has_flat:
                    gaps.append(f"{s.get('section_number', '?')} t[{ti}] {t.get('name', '')[:40]}")
        assert gaps == [], f"{std}: {len(gaps)} 张表缺 group/flat:\n" + "\n".join(gaps[:10])

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_no_newlines_in_columns(self, std: str):
        """columns.label / columns.group 中不得有换行符。"""
        path = DATA_DIR / f"note_template_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for s in data.get("sections", []):
            for ti, t in enumerate(s.get("tables", [])):
                for ci, c in enumerate(t.get("columns", [])):
                    if not isinstance(c, dict):
                        continue
                    for field in ("label", "group"):
                        val = c.get(field, "")
                        if val and "\n" in val:
                            pytest.fail(
                                f"{std} {s.get('section_number', '?')} t[{ti}] "
                                f"columns[{ci}].{field}: 含换行符 {repr(val)}"
                            )



class TestSectionIdStability:
    """section_id 集合棘轮——只许增不许减。"""

    # 2026-10-09 基线
    SECTION_ID_BASELINES = {
        "soe": 321,
        "listed": 432,
    }

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_section_id_count_not_regressed(self, std: str):
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        sids = {t["section_id"] for t in data}
        baseline = self.SECTION_ID_BASELINES[std]
        assert len(sids) >= baseline, (
            f"{std}: section_id 数量 {len(sids)} < 基线 {baseline}，不允许退化"
        )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_no_duplicate_section_ids(self, std: str):
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        sids = [t["section_id"] for t in data]
        dupes = [sid for sid in sids if sids.count(sid) > 1]
        assert not dupes, f"{std}: 重复 section_id: {set(dupes)}"

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_no_empty_title(self, std: str):
        """所有表必须有非空 title。"""
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        empty = [t["section_id"] for t in data if not (t.get("title") or "").strip()]
        assert empty == [], f"{std}: {len(empty)} 张表无 title: {empty[:5]}"
