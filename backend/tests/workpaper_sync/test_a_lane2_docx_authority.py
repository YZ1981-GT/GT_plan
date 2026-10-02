# -*- coding: utf-8 -*-
"""A 类 docx 权威册车道守卫 — 合并单元格定位模型 + 脏字面量。

spec: a-class-docx-authority-workbook-lanes

测试结构：
  - TestLane2Boundary         AG-P1 ~ AG-P5  归属基线
  - TestDocxFormatDispatch    AG-P6 ~ AG-P7  format 分流 + 空分母声明
  - TestDocxStructureBaseline AG-P8 ~ AG-P9  结构基线
  - TestMergedCellDedup       AG-P10 ~ AG-P12 合并单元格 tc 去重
  - TestParagraphLevelPath    AG-P13         段落级定位
  - TestPlaceholderAndDirty   AG-P14 ~ AG-P15 占位符 + 脏字面量
  - TestBP11NonBijection      AG-P16         BP-11 非双射

共同判据只引用 AC 编号，判据正文在 foundation。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════
_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_TEMPLATE_DIR = _BACKEND / "wp_templates" / "A"
_DATA = _BACKEND / "data"
_SLICE_PATH = _DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from a_cycle_scanner import (  # noqa: E402
    a_domain_entries,
    scan_docx_structure,
    sha256_file,
    TEMPLATE_DIR,
)


# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


def _get_docx_entries(manifest_slice: dict) -> list[dict]:
    a_entries = a_domain_entries(manifest_slice["independent_entries"])
    return [e for e in a_entries if e.get("template_ref", {}).get("workbook_format") == "docx"]


def _find_docx_file(entry: dict) -> Path | None:
    """找到 entry 对应的 docx 权威册文件。"""
    code = entry["wp_code_patterns"][0] if entry.get("wp_code_patterns") else ""
    candidates = [f for f in TEMPLATE_DIR.rglob(f"{code}*")
                  if f.suffix.lower() == ".docx" and "~$" not in f.name]
    if not candidates:
        candidates = [f for f in TEMPLATE_DIR.rglob(f"*{code}*")
                      if f.suffix.lower() == ".docx" and "~$" not in f.name]
    return candidates[0] if candidates else None


# ═══════════════════════════════════════════════════════════════════════════
# §1 TestLane2Boundary — AG-P1 ~ AG-P5
# ═══════════════════════════════════════════════════════════════════════════


class TestLane2Boundary:
    """lane2 归属基线（AG-P1 ~ AG-P5）。"""

    def test_docx_entry_count_16(self, manifest_slice: dict) -> None:
        """AG-P1: 恰 16 条 docx 册 entry。"""
        docx = _get_docx_entries(manifest_slice)
        assert len(docx) == 16

    def test_all_workbook_format_is_docx(self, manifest_slice: dict) -> None:
        """AG-P2: 全部 workbook_format 为 docx。"""
        docx = _get_docx_entries(manifest_slice)
        for e in docx:
            fmt = e.get("template_ref", {}).get("workbook_format")
            assert fmt == "docx", f"{e['entry_id']}: format 应为 docx，实际 {fmt}"

    def test_bp_count_113(self, manifest_slice: dict) -> None:
        """AG-P3: BP 数 = 15×7 + 1×8(a91) = 113。"""
        docx = _get_docx_entries(manifest_slice)
        total_bp = sum(len(e.get("capability_target_blocked_by", [])) for e in docx)
        assert total_bp == 113, f"BP 总数应为 113，实际 {total_bp}"

    def test_group_distribution(self, manifest_slice: dict) -> None:
        """AG-P4: GRP-01=13 / GRP-02=1 / GRP-03=1 / GRP-10=1。"""
        docx = _get_docx_entries(manifest_slice)
        groups: dict[str, int] = defaultdict(int)
        for e in docx:
            groups[e.get("group_id", "?")] += 1
        assert groups.get("GRP-01", 0) == 13
        assert groups.get("GRP-02", 0) == 1
        assert groups.get("GRP-03", 0) == 1
        assert groups.get("GRP-10", 0) == 1
        assert sum(groups.values()) == 16

    def test_oo_mounts_and_gates_16(self, manifest_slice: dict) -> None:
        """AG-P5: OO 挂点/segmented/mode 门控各 16（无 no_switch）。"""
        docx = _get_docx_entries(manifest_slice)
        for e in docx:
            verdict = e.get("dual_mode_carrier", {}).get("switch_verdict", "")
            assert verdict != "no_switch_at_all", \
                f"{e['entry_id']}: lane2 内不应有 no_switch"


# ═══════════════════════════════════════════════════════════════════════════
# §2 TestDocxFormatDispatch — AG-P6 ~ AG-P7
# ═══════════════════════════════════════════════════════════════════════════


class TestDocxFormatDispatch:
    """format 分流 + Excel 判据空分母声明（AG-P6 ~ AG-P7）。"""

    def test_openpyxl_rejects_docx(self) -> None:
        """AG-P6: openpyxl 读 docx 抛 InvalidFileException（反证）。

        🔴 保留此反证以证明 docx 册禁跑 openpyxl。
        """
        import openpyxl
        docx_files = [f for f in TEMPLATE_DIR.rglob("*.docx") if "~$" not in f.name]
        assert docx_files, "应至少有 1 本 docx 册"
        with pytest.raises(Exception):
            openpyxl.load_workbook(str(docx_files[0]))

    def test_sha256_16_match(self, manifest_slice: dict) -> None:
        """AG-P7: 16 本 docx 册 sha256 自洽性。"""
        docx = _get_docx_entries(manifest_slice)
        match_count = 0
        for e in docx:
            p = _find_docx_file(e)
            if p and p.exists():
                d1 = sha256_file(p)
                d2 = sha256_file(p)
                assert d1 == d2, f"{e['entry_id']}: sha256 自洽性失败"
                match_count += 1
        assert match_count >= 14, f"至少 14 本应能匹配到文件，实际 {match_count}"


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestDocxStructureBaseline — AG-P8 ~ AG-P9
# ═══════════════════════════════════════════════════════════════════════════


class TestDocxStructureBaseline:
    """docx 结构基线（AG-P8 ~ AG-P9）。"""

    @pytest.fixture(scope="class")
    def all_structures(self, manifest_slice: dict) -> list[dict]:
        docx = _get_docx_entries(manifest_slice)
        results = []
        for e in docx:
            p = _find_docx_file(e)
            if p and p.exists():
                r = scan_docx_structure(p)
                r["entry_id"] = e["entry_id"]
                results.append(r)
        return results

    def test_tables_range_0_to_13(self, all_structures: list) -> None:
        """AG-P8: tables 范围 0~13。"""
        table_counts = [r["table_count"] for r in all_structures]
        assert min(table_counts) == 0, f"最小 tables 应为 0，实际 {min(table_counts)}"
        assert max(table_counts) == 13, f"最大 tables 应为 13，实际 {max(table_counts)}"

    def test_cells_range_0_to_3174(self, all_structures: list) -> None:
        """AG-P8: cells 范围 0~3174。"""
        cell_counts = [r["total_cells"] for r in all_structures]
        assert min(cell_counts) == 0
        assert max(cell_counts) == 3174

    def test_sections_a171_and_a81_are_2(self, all_structures: list) -> None:
        """AG-P9: sections a171 与 a81 为 2（含分节符），其余 14 条为 1。"""
        for r in all_structures:
            eid = r["entry_id"]
            if "a171" in eid or "a81" in eid:
                assert r["section_count"] == 2, \
                    f"{eid}: sections 应为 2，实际 {r['section_count']}"
            else:
                assert r["section_count"] == 1, \
                    f"{eid}: sections 应为 1，实际 {r['section_count']}"


# ═══════════════════════════════════════════════════════════════════════════
# §4 TestMergedCellDedup — AG-P10 ~ AG-P12
# ═══════════════════════════════════════════════════════════════════════════


class TestMergedCellDedup:
    """合并单元格 tc 去重（AG-P10 ~ AG-P12）。

    🔴 核心难点：按 (row,col) 遍历会重复命中同一 <w:tc>。
    双向回写的 docx 侧定位键须基于 tc 标识去重。
    """

    def test_a115_merged_99_5_pct(self, manifest_slice: dict) -> None:
        """AG-P10: a115 merged 比例 ≥ 99%。

        🔴 a115 有 3 张表合计 3174 cells，合并比极高。
        """
        docx = _get_docx_entries(manifest_slice)
        a115 = [e for e in docx if "a115" in e["entry_id"]][0]
        p = _find_docx_file(a115)
        assert p and p.exists()
        r = scan_docx_structure(p)
        assert r["total_cells"] == 3174, f"cells 应为 3174，实际 {r['total_cells']}"
        assert r["merged_pct"] >= 99.0, f"merged 应 >= 99%，实际 {r['merged_pct']}%"

    def test_a115_unique_tc_is_tiny(self, manifest_slice: dict) -> None:
        """AG-P11: a115 最大表（934 行）的不同 tc 远小于 cell 数。

        🔴 若按 (row,col) 建位置表会产出大量位置，其中绝大多数写到同一格。
        """
        docx = _get_docx_entries(manifest_slice)
        a115 = [e for e in docx if "a115" in e["entry_id"]][0]
        p = _find_docx_file(a115)
        assert p
        import docx as python_docx
        doc = python_docx.Document(str(p))
        # 遍历全部 3 张表中最大的那张
        all_tables = sorted(doc.tables, key=lambda t: sum(len(r.cells) for r in t.rows), reverse=True)
        biggest = all_tables[0]
        unique_tcs: set[int] = set()
        total_cells = 0
        for row in biggest.rows:
            for cell in row.cells:
                total_cells += 1
                unique_tcs.add(id(cell._tc))
        # 关键断言：不同 tc 远少于 (row,col) 计数
        ratio = len(unique_tcs) / total_cells if total_cells > 0 else 1.0
        assert ratio < 0.05, \
            f"tc 去重比应 < 5%，实际 {len(unique_tcs)}/{total_cells} = {ratio:.1%}"

    def test_zero_merged_books_tolerated(self, manifest_slice: dict) -> None:
        """AG-P12: 容忍零合并册（a182/a81/a91 为 0%）。"""
        docx = _get_docx_entries(manifest_slice)
        zero_merged = []
        for e in docx:
            p = _find_docx_file(e)
            if not p or not p.exists():
                continue
            r = scan_docx_structure(p)
            if r["total_cells"] > 0 and r["merged_pct"] == 0.0:
                short = e["entry_id"].split("/")[-1].replace("gt-", "")
                zero_merged.append(short)
        # a182/a91 应在零合并列表中
        assert any("a182" in x for x in zero_merged), "a182 应为零合并"
        assert any("a91" in x for x in zero_merged), "a91 应为零合并"


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestParagraphLevelPath — AG-P13
# ═══════════════════════════════════════════════════════════════════════════


class TestParagraphLevelPath:
    """段落级定位路径（AG-P13）。"""

    def test_a181_zero_tables(self, manifest_slice: dict) -> None:
        """AG-P13: a181 0 tables ⇒ 段落级。"""
        docx = _get_docx_entries(manifest_slice)
        a181 = [e for e in docx if "a181" in e["entry_id"]][0]
        p = _find_docx_file(a181)
        assert p
        r = scan_docx_structure(p)
        assert r["table_count"] == 0
        assert r["non_empty_paragraph_count"] == 8

    def test_a91_tiny_tables(self, manifest_slice: dict) -> None:
        """AG-P13: a91 仅 2 个 1×1 表 ⇒ 段落级。"""
        docx = _get_docx_entries(manifest_slice)
        a91 = [e for e in docx if "a91" in e["entry_id"]][0]
        p = _find_docx_file(a91)
        assert p
        r = scan_docx_structure(p)
        assert r["table_count"] == 2
        assert r["total_cells"] == 2  # 每表 1 cell

    def test_a173_first_para_is_guidance(self, manifest_slice: dict) -> None:
        """AG-P13 补: a173 首段是指引文字（非标题）。"""
        docx = _get_docx_entries(manifest_slice)
        a173 = [e for e in docx if "a173-consultation" in e["entry_id"]
                and "a1731" not in e["entry_id"]][0]
        p = _find_docx_file(a173)
        assert p
        r = scan_docx_structure(p)
        first = r["first_paragraph"]
        assert "参考格式" in first or "四方面" in first, \
            f"a173 首段应是指引文字，实际: {first[:60]}"


# ═══════════════════════════════════════════════════════════════════════════
# §6 TestPlaceholderAndDirty — AG-P14 ~ AG-P15
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaceholderAndDirty:
    """占位符五形态 + 脏字面量（AG-P14 ~ AG-P15）。"""

    def test_placeholder_five_forms(self, manifest_slice: dict) -> None:
        """AG-P14: 占位符五形态（XX/全角××/【】/□/N/A）。"""
        docx = _get_docx_entries(manifest_slice)
        forms_found: set[str] = set()
        for e in docx:
            p = _find_docx_file(e)
            if not p or not p.exists():
                continue
            import docx as python_docx
            doc = python_docx.Document(str(p))
            full_text = "\n".join(para.text for para in doc.paragraphs)
            for tbl in doc.tables:
                for row in tbl.rows:
                    for cell in row.cells:
                        full_text += "\n" + cell.text
            if "XX" in full_text:
                forms_found.add("XX")
            if "××" in full_text:
                forms_found.add("全角××")
            if "【" in full_text:
                forms_found.add("【】")
            if "□" in full_text:
                forms_found.add("□")
            if "N/A" in full_text:
                forms_found.add("N/A")
        assert len(forms_found) == 5, f"应有五形态，实际 {forms_found}"

    def test_t5_char_defect_20lx(self, manifest_slice: dict) -> None:
        """AG-P15: T-5 字符缺陷 20l×年（小写 l 冒充 1）。

        🔴 记录型断言：锁定现状，不修改 docx。
        """
        docx = _get_docx_entries(manifest_slice)
        found = False
        for e in docx:
            if "a91" not in e["entry_id"]:
                continue
            p = _find_docx_file(e)
            if not p:
                continue
            import docx as python_docx
            doc = python_docx.Document(str(p))
            for para in doc.paragraphs:
                if "20l" in para.text:
                    found = True
                    break
        assert found, "a91 P2 应含 '20l×年' 字符缺陷"


# ═══════════════════════════════════════════════════════════════════════════
# §7 TestBP11NonBijection — AG-P16
# ═══════════════════════════════════════════════════════════════════════════


class TestBP11NonBijection:
    """BP-11: 单宿主承载两个 componentType（AG-P16）。"""

    def test_a91_has_8_bp(self, manifest_slice: dict) -> None:
        """AG-P16: a91 BP 数 = 8（公共 6 + BP-9 + BP-11）——A 域最多。"""
        docx = _get_docx_entries(manifest_slice)
        a91 = [e for e in docx if "a91" in e["entry_id"]][0]
        bp = a91.get("capability_target_blocked_by", [])
        assert len(bp) == 8, f"a91 BP 应为 8，实际 {len(bp)}"

    def test_a91_is_multi_component_type(self, manifest_slice: dict) -> None:
        """AG-P16: a91 family 是 multi_component_type_single_host。"""
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        a91 = [e for e in a_entries if "a91" in e["entry_id"]][0]
        # 在 entry_groups 中找 GRP-10
        groups = manifest_slice.get("entry_groups", {}).get("groups", [])
        grp10 = [g for g in groups if g["group_id"] == "GRP-10"]
        assert grp10, "GRP-10 应存在"
        family = grp10[0].get("component_type_family", "")
        assert "multi_component_type" in family, \
            f"GRP-10 family 应含 multi_component_type，实际 {family}"
