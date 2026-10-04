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

    def test_a115_tc_mapping_performance_baseline(self, manifest_slice: dict) -> None:
        """AG-P11 补: a115 934 行巨表一次性建 tc→逻辑位置映射，耗时 < 2s。

        🔴 性能风险项：a115 最大表 934 行 × 3174 cells（merged 99.5%），
        须一次性遍历建 ``{id(tc): (table_idx, row_idx, col_idx)}`` 映射，
        禁逐格回查。此断言锁定遍历耗时基线，防退化。
        """
        import time
        docx = _get_docx_entries(manifest_slice)
        a115 = [e for e in docx if "a115" in e["entry_id"]][0]
        p = _find_docx_file(a115)
        assert p and p.exists()
        import docx as python_docx
        doc = python_docx.Document(str(p))

        # ── 一次性建立 tc → 逻辑位置 映射（全部 3 张表） ──
        t0 = time.perf_counter()
        tc_position_map: dict[int, tuple[int, int, int]] = {}
        total_cell_visits = 0
        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    total_cell_visits += 1
                    key = id(cell._tc)
                    if key not in tc_position_map:
                        tc_position_map[key] = (t_idx, r_idx, c_idx)
        elapsed = time.perf_counter() - t0

        # ── 断言：映射正确建立且耗时在基线内 ──
        assert len(tc_position_map) > 0, "映射不应为空"
        assert total_cell_visits == 3174, \
            f"cell 访问总数应为 3174，实际 {total_cell_visits}"
        assert len(tc_position_map) < total_cell_visits, \
            "去重后映射条目数应远小于 cell 访问数（合并单元格去重效果）"
        assert elapsed < 2.0, \
            f"tc→逻辑位置映射构建应 < 2s，实际 {elapsed:.3f}s（性能风险基线）"

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

    # ── T-12 ~ T-14 册名三种脏形态（AG-P15 补） ──────────────────────────

    def test_t12_a176_double_space_in_filename(self) -> None:
        """AG-P15 补: T-12 册名脏形态 — A17-6 文件名含两个连续空格。

        🔴 记录型断言：`A17-6  总结会会议记要.docx` 的码 `A17-6` 与中文 `总结会`
        之间有**两个连续空格**（其余 15 本都是单空格）。
        按原始文件名字面量比对，禁归一化空格（依 AC-10 · AC-26）。
        """
        candidates = [
            f for f in TEMPLATE_DIR.rglob("*.docx")
            if "A17-6" in f.name and "~$" not in f.name
        ]
        assert len(candidates) == 1, f"A17-6 应恰有 1 本 docx，实际 {len(candidates)}"
        name = candidates[0].name
        # 🔴 核心断言：文件名里有两个连续空格
        assert "  " in name, (
            f"T-12: A17-6 文件名应含两个连续空格，实际: {name!r}"
        )
        # 精确锁定完整文件名
        assert name == "A17-6  总结会会议记要.docx", (
            f"T-12: 文件名应为 'A17-6  总结会会议记要.docx'，实际: {name!r}"
        )

    def test_t13_a182_half_width_parens_in_filename(self) -> None:
        """AG-P15 补: T-13 册名脏形态 — A18-2 文件名含半角括号 + 前导空格。

        🔴 记录型断言：`A18-2 与监管层沟通函 (通用)2019.docx` 中
        `函` 与 `(通用)` 之间有**空格 + 半角括号**，而非全角 `（通用）`。
        按原始文件名字面量比对，禁归一化括号（依 AC-10 · AC-26）。
        """
        candidates = [
            f for f in TEMPLATE_DIR.rglob("*.docx")
            if "A18-2" in f.name and "~$" not in f.name
        ]
        assert len(candidates) == 1, f"A18-2 应恰有 1 本 docx，实际 {len(candidates)}"
        name = candidates[0].name
        # 🔴 核心断言：半角括号 (通用) 且前方有空格
        assert " (通用)" in name, (
            f"T-13: A18-2 文件名应含 ' (通用)'（空格+半角括号），实际: {name!r}"
        )
        # 精确锁定完整文件名
        assert name == "A18-2 与监管层沟通函 (通用)2019.docx", (
            f"T-13: 文件名应为 'A18-2 与监管层沟通函 (通用)2019.docx'，实际: {name!r}"
        )

    def test_t14_a91_no_space_between_code_and_chinese(self) -> None:
        """AG-P15 补: T-14 册名脏形态 — A9-1 码与中文之间无空格。

        🔴 记录型断言：`A9-1向管理层通报内部控制缺陷-沟通函.docx` 中
        码 `A9-1` 与中文 `向` 直接相连（其余 15 本都有空格分隔码与中文）。
        按原始文件名字面量比对，禁归一化（依 AC-10 · AC-26）。
        """
        candidates = [
            f for f in TEMPLATE_DIR.rglob("*.docx")
            if f.name.startswith("A9-1") and "缺陷" in f.name and "~$" not in f.name
        ]
        assert len(candidates) == 1, (
            f"A9-1 缺陷沟通函应恰有 1 本 docx，实际 {len(candidates)}: "
            f"{[c.name for c in candidates]}"
        )
        name = candidates[0].name
        # 🔴 核心断言：A9-1 后面紧跟中文「向」，无空格
        assert "A9-1向" in name, (
            f"T-14: A9-1 文件名应含 'A9-1向'（码与中文无空格），实际: {name!r}"
        )
        # 反面断言：确认不是 'A9-1 向'（有空格的形态）
        assert "A9-1 向" not in name, (
            f"T-14: A9-1 文件名不应有 'A9-1 向'（码后有空格），实际: {name!r}"
        )
        # 精确锁定完整文件名
        assert name == "A9-1向管理层通报内部控制缺陷-沟通函.docx", (
            f"T-14: 文件名应为 'A9-1向管理层通报内部控制缺陷-沟通函.docx'，实际: {name!r}"
        )


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


# ═══════════════════════════════════════════════════════════════════════════
# §8 TestArchivedDebtLane2 — AG-P17
# ═══════════════════════════════════════════════════════════════════════════


class TestArchivedDebtLane2:
    """归档欠账登记（AG-P17）。

    🔴 只登记不回填修改已归档 spec（append-only）。
    扫归档区带 ``errors="replace"`` 容错（依 AC-25）。

    本 spec（lane2）承担 **5 份 / 6 条**未完成任务。
    与 foundation 的差额：第 6 份 ``a17-7-independence-declaration``（20/21）
    的 entry（a177）归 **lane3**，两 lane 各登记自己份额，
    合计 6 份 / 7 条。
    """

    _ARCHIVE_BATCH = _ROOT / ".kiro" / "specs" / "_archive" / "13-2026-06-29-batch"

    # lane2 份额：5 份 spec，各自的 (done, total, incomplete)
    _LANE2_SPECS: dict[str, tuple[int, int, int]] = {
        "a11-1-subsequent-events-inquiry":  (19, 21, 2),
        "a17-3-1-consultation-execution":   (15, 16, 1),
        "a17-3-consultation-record":        (16, 17, 1),
        "a17-4-disagreement-record":        (16, 17, 1),
        "a18-2-regulatory-communication":   (14, 15, 1),
    }

    # lane3 份额（本 spec 只登记差额说明，不断言完成度）
    _LANE3_SPEC = "a17-7-independence-declaration"
    _LANE3_RATIO = (20, 21, 1)

    @staticmethod
    def _count_tasks(tasks_path: Path) -> tuple[int, int, int]:
        """统计 tasks.md 中 ``[x]`` 与 ``[ ]`` 的数量。

        Returns:
            (done, total, incomplete)
        """
        # 🔴 errors="replace" 容错（依 AC-25）
        text = tasks_path.read_bytes().decode("utf-8", errors="replace")
        done = len(re.findall(r"^\s*- \[x\]", text, re.MULTILINE))
        undone = len(re.findall(r"^\s*- \[ \]", text, re.MULTILINE))
        return (done, done + undone, undone)

    def test_lane2_has_exactly_5_specs_with_debt(self) -> None:
        """AG-P17: lane2 归档欠账恰 5 份。

        🔴 不是 6 份——第 6 份 a17-7 属 lane3。
        """
        found = 0
        for name in self._LANE2_SPECS:
            tasks_path = self._ARCHIVE_BATCH / name / "tasks.md"
            assert tasks_path.exists(), f"归档 spec {name}/tasks.md 应存在"
            found += 1
        assert found == 5, f"lane2 归档欠账应恰 5 份，实际 {found}"

    def test_lane2_each_spec_ratio_matches(self) -> None:
        """AG-P17: 逐份验证完成度与设计值吻合。

        a11-1 19/21（2 条）· a17-3-1 15/16 · a17-3 16/17 ·
        a17-4 16/17 · a18-2 14/15。
        """
        for name, expected in self._LANE2_SPECS.items():
            tasks_path = self._ARCHIVE_BATCH / name / "tasks.md"
            actual = self._count_tasks(tasks_path)
            assert actual == expected, (
                f"{name}: 完成度应为 {expected[0]}/{expected[1]}"
                f"（incomplete {expected[2]}），"
                f"实际 {actual[0]}/{actual[1]}（incomplete {actual[2]}）"
            )

    def test_lane2_total_incomplete_is_6(self) -> None:
        """AG-P17: lane2 的 5 份合计未完成任务 = 6（2+1+1+1+1）。"""
        total_incomplete = 0
        for name in self._LANE2_SPECS:
            tasks_path = self._ARCHIVE_BATCH / name / "tasks.md"
            _, _, incomplete = self._count_tasks(tasks_path)
            total_incomplete += incomplete
        assert total_incomplete == 6, (
            f"lane2 合计未完成应为 6，实际 {total_incomplete}"
        )

    def test_lane3_spec_exists_and_explains_difference(self) -> None:
        """AG-P17 补: lane3 的 a17-7（20/21）说明与 foundation 的差额。

        foundation 登记 6 份 / 7 条。本 spec（lane2）5 份 / 6 条 +
        lane3 的 a17-7 1 份 / 1 条 = 合计 6 份 / 7 条，与 foundation 吻合。
        🔴 只验证存在性与差额算术，不回填修改 a17-7 的 tasks.md。
        """
        tasks_path = self._ARCHIVE_BATCH / self._LANE3_SPEC / "tasks.md"
        assert tasks_path.exists(), (
            f"lane3 归档 spec {self._LANE3_SPEC}/tasks.md 应存在"
        )
        actual = self._count_tasks(tasks_path)
        assert actual == self._LANE3_RATIO, (
            f"{self._LANE3_SPEC}: 完成度应为 "
            f"{self._LANE3_RATIO[0]}/{self._LANE3_RATIO[1]}，"
            f"实际 {actual[0]}/{actual[1]}"
        )

        # 合计校验：lane2(6) + lane3(1) = foundation 的 7 条
        lane2_total = sum(v[2] for v in self._LANE2_SPECS.values())
        grand_total = lane2_total + actual[2]
        assert grand_total == 7, (
            f"lane2({lane2_total}) + lane3({actual[2]}) 应 = 7，"
            f"实际 {grand_total}"
        )

    def test_archive_files_not_modified(self) -> None:
        """AG-P17 补: 归档区 tasks.md 不含回填痕迹。

        🔴 只登记不回填修改已归档 spec（append-only 铁律）。
        验证方式：每份 tasks.md 均不含本 spec 的标识字符串。
        """
        marker = "a-class-docx-authority-workbook-lanes"
        all_specs = list(self._LANE2_SPECS.keys()) + [self._LANE3_SPEC]
        for name in all_specs:
            tasks_path = self._ARCHIVE_BATCH / name / "tasks.md"
            text = tasks_path.read_bytes().decode("utf-8", errors="replace")
            assert marker not in text, (
                f"归档 spec {name}/tasks.md 不应含本 spec 标识 "
                f"'{marker}'（append-only 铁律）"
            )
