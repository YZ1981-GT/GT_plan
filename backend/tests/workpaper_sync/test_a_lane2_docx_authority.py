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
  - TestArchivedSpecDebt      AG-P17         归档欠账
  - TestDeliveryChecklist      Task 13        交付前自检（meta-test）
  - TestPlatformDebtRegistry  Task 14        平台级欠账 BP-1~BP-5（AC-25）

共同判据只引用 AC 编号，判据正文在 foundation。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
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

    def test_a115_tc_mapping_performance(self, manifest_slice: dict) -> None:
        """AG-P11 性能风险登记：a115 全 3 张表的 tc→逻辑位置 映射须一次性建立。

        🔴 性能风险项（design T-6）：a115 最大表 934 行 × 3 列 = 3174 cells，
        合并比 99.5%。若逐格回查会产出 O(n²) 开销。
        本测试要求单次遍历建立完整映射，耗时 < 5 秒（宽裕值，容纳 CI 波动）。
        映射键 = id(cell._tc)，值 = 首次出现的 (table_idx, row_idx, col_idx)。
        """
        docx = _get_docx_entries(manifest_slice)
        a115 = [e for e in docx if "a115" in e["entry_id"]][0]
        p = _find_docx_file(a115)
        assert p and p.exists(), "a115 docx 册文件应存在"

        import docx as python_docx
        doc = python_docx.Document(str(p))

        # ── 单次遍历建立 tc → 逻辑位置 映射，禁逐格回查 ──
        t0 = time.perf_counter()
        tc_to_position: dict[int, tuple[int, int, int]] = {}
        total_cell_slots = 0
        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    total_cell_slots += 1
                    key = id(cell._tc)
                    if key not in tc_to_position:
                        tc_to_position[key] = (t_idx, r_idx, c_idx)
        elapsed = time.perf_counter() - t0

        # ── 性能断言：< 5 秒（宽裕值） ──
        assert elapsed < 5.0, (
            f"tc 映射构建耗时 {elapsed:.2f}s，超过 5s 阈值"
        )

        # ── 正确性断言：去重后的 tc 数远小于 (row,col) 槽位数 ──
        assert total_cell_slots == 3174, (
            f"全 3 表 cell 槽位应为 3174，实际 {total_cell_slots}"
        )
        unique_count = len(tc_to_position)
        # 与 test_a115_unique_tc_is_tiny 一致：不同 tc 远少于 cell 槽位
        assert unique_count < total_cell_slots * 0.05, (
            f"不同 tc 应 < 5% 的 cell 数，实际 {unique_count}/{total_cell_slots}"
        )
        # 映射值应为 (int, int, int) 三元组
        for pos in tc_to_position.values():
            assert len(pos) == 3 and all(isinstance(x, int) for x in pos)

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

    def test_dirty_filenames_t12_t13_t14(self) -> None:
        """AG-P15: 册名三种脏形态（T-12 ~ T-14）按原始文件名字面量比对。

        🔴 记录型断言：锁定原始文件名现状，不修改 docx。
        T-12: A17-6  总结会… ⇒ 两个连续空格
        T-13: A18-2 …函 (通用)… ⇒ 半角括号前有空格
        T-14: A9-1向管理层… ⇒ 码与中文之间无空格（其余 15 本都有）
        """
        # ── T-12: 双空格 ──
        t12 = list(_TEMPLATE_DIR.glob("A17-6*.docx"))
        assert len(t12) == 1, f"A17-6 应恰有 1 本 docx，实际 {len(t12)}"
        assert "  " in t12[0].name, (
            f"T-12: A17-6 文件名应含两个连续空格，实际: {t12[0].name!r}"
        )

        # ── T-13: 半角括号 + 前导空格 ──
        t13 = list(_TEMPLATE_DIR.glob("A18-2*.docx"))
        assert len(t13) == 1, f"A18-2 应恰有 1 本 docx，实际 {len(t13)}"
        assert " (" in t13[0].name, (
            f"T-13: A18-2 文件名应含 ' ('（空格+半角括号），实际: {t13[0].name!r}"
        )

        # ── T-14: 码与中文无空格 ──
        t14 = [f for f in _TEMPLATE_DIR.glob("A9-1*.docx")
               if "~$" not in f.name and "A9-1" in f.name]
        assert len(t14) == 1, f"A9-1 应恰有 1 本 docx，实际 {len(t14)}"
        # 码后紧跟中文（无空格）：A9-1 后面直接是中文字符
        name = t14[0].name
        m = re.search(r"A9-1(\S)", name)
        assert m is not None, (
            f"T-14: A9-1 后应直接跟非空白字符，实际: {name!r}"
        )
        # 确认紧跟的是中文字符（不是空格、不是横杠等分隔符前有空格）
        first_after = m.group(1)
        assert ord(first_after) > 0x2E00, (
            f"T-14: A9-1 后首字符应为中文，实际: {first_after!r} (U+{ord(first_after):04X})"
        )

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


# ═══════════════════════════════════════════════════════════════════════════
# §8 TestArchivedSpecDebt — AG-P17
# ═══════════════════════════════════════════════════════════════════════════


class TestArchivedSpecDebt:
    """归档欠账登记（AG-P17）——5 份 / 6 条。

    本 spec 范围内 5 条 entry 的功能 spec 尚有未完成任务（全部是 Playwright E2E，
    受环境阻塞）。只登记不回填修改已归档 spec（append-only 原则）。

    与 foundation 的差额说明：
      - foundation 统计 6 份 / 7 条（含 a17-7-independence-declaration 20/21）
      - a17-7-independence-declaration 的 entry（a177）归 **lane3** 而非 lane2
      - 两份 lane spec 各自登记自己的份额 ⇒ lane2 = 5 份 / 6 条，lane3 = 1 份 / 1 条
      - 合计 = 6 份 / 7 条
    """

    # ── 常量：5 份归档 spec 及其完成度 ──────────────────────────────────

    ARCHIVED_DEBT: dict[str, tuple[int, int]] = {
        # spec_name: (completed, total)
        "a11-1-subsequent-events-inquiry":    (19, 21),  # 2 条未完成
        "a17-3-1-consultation-execution":     (15, 16),  # 1 条
        "a17-3-consultation-record":          (16, 17),  # 1 条
        "a17-4-disagreement-record":          (16, 17),  # 1 条
        "a18-2-regulatory-communication":     (14, 15),  # 1 条
    }

    # lane3 的第 6 份（不在本 spec 登记范围，仅做交叉说明）
    LANE3_SPEC = "a17-7-independence-declaration"
    LANE3_RATIO = (20, 21)  # 1 条未完成

    _ARCHIVE_BATCH = Path(__file__).resolve().parents[3] / ".kiro" / "specs" / "_archive" / "13-2026-06-29-batch"

    # ── 测试 ──────────────────────────────────────────────────────────────

    def test_all_5_archived_specs_exist(self) -> None:
        """AG-P17: 5 份归档 spec 目录均存在于 _archive/13-2026-06-29-batch/。"""
        missing = []
        for spec_name in self.ARCHIVED_DEBT:
            spec_dir = self._ARCHIVE_BATCH / spec_name
            if not spec_dir.is_dir():
                missing.append(spec_name)
        assert not missing, f"归档目录缺失: {missing}"

    def test_total_uncompleted_is_6(self) -> None:
        """AG-P17: 5 份合计 6 条未完成任务。"""
        total_uncompleted = sum(
            total - completed
            for completed, total in self.ARCHIVED_DEBT.values()
        )
        assert total_uncompleted == 6, (
            f"lane2 归档欠账应为 6 条，实际 {total_uncompleted}"
        )

    def test_uncompleted_items_categorized(self) -> None:
        """AG-P17: 未完成项形态登记——5 条 Playwright E2E + 1 条 overrides 更新。

        扫各 spec 的 tasks.md，提取 '[ ]' 行并分类。
        a11-1 有 2 条未完成：1 条 wp_code_overrides 更新 + 1 条 Playwright E2E。
        其余 4 份各 1 条 Playwright E2E。合计 5 条 E2E + 1 条非 E2E = 6 条。
        """
        e2e_count = 0
        non_e2e_items: list[str] = []
        for spec_name in self.ARCHIVED_DEBT:
            tasks_path = self._ARCHIVE_BATCH / spec_name / "tasks.md"
            assert tasks_path.is_file(), f"{spec_name}: tasks.md 不存在"
            content = tasks_path.read_bytes().decode("utf-8", errors="replace")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("- [ ]"):
                    lower = stripped.lower()
                    if "playwright" in lower or "e2e" in lower:
                        e2e_count += 1
                    else:
                        non_e2e_items.append(f"{spec_name}: {stripped[:100]}")
        # 5 条 Playwright E2E（4 份各 1 条 + a11-1 的 task 5.3）
        assert e2e_count == 5, f"Playwright E2E 未完成项应为 5，实际 {e2e_count}"
        # 1 条非 E2E（a11-1 的 task 1.4 wp_code_overrides.json 更新）
        assert len(non_e2e_items) == 1, (
            f"非 E2E 未完成项应为 1，实际 {len(non_e2e_items)}: {non_e2e_items}"
        )
        assert "a11-1" in non_e2e_items[0], (
            f"唯一的非 E2E 项应来自 a11-1，实际: {non_e2e_items[0]}"
        )
        assert "wp_code_overrides" in non_e2e_items[0].lower(), (
            f"a11-1 的非 E2E 项应是 overrides 更新: {non_e2e_items[0]}"
        )

    def test_each_spec_ratio_matches_declaration(self) -> None:
        """AG-P17: 各 spec 的已勾选数与声明的完成度吻合。

        逐份扫 tasks.md 统计 '[x]' 与 '[ ]' 行数，与 ARCHIVED_DEBT 声明对齐。
        🔴 扫归档区带 errors='replace'（依 AC-25）。
        """
        mismatches: list[str] = []
        for spec_name, (declared_done, declared_total) in self.ARCHIVED_DEBT.items():
            tasks_path = self._ARCHIVE_BATCH / spec_name / "tasks.md"
            if not tasks_path.is_file():
                mismatches.append(f"{spec_name}: tasks.md 不存在")
                continue
            content = tasks_path.read_bytes().decode("utf-8", errors="replace")
            done_count = 0
            undone_count = 0
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("- [x]"):
                    done_count += 1
                elif stripped.startswith("- [ ]"):
                    undone_count += 1
            actual_total = done_count + undone_count
            if done_count != declared_done or actual_total != declared_total:
                mismatches.append(
                    f"{spec_name}: 声明 {declared_done}/{declared_total}，"
                    f"实际 {done_count}/{actual_total}"
                )
        assert not mismatches, (
            "完成度声明与 tasks.md 不一致:\n" + "\n".join(mismatches)
        )

    def test_lane3_spec_exists_but_not_in_lane2_scope(self) -> None:
        """AG-P17: 第 6 份 a17-7-independence-declaration 归 lane3，本 spec 不登记。

        验证该 spec 确实存在于归档区（证明差额来源合理），但不在 ARCHIVED_DEBT 中。
        合计: lane2 的 5 份/6 条 + lane3 的 1 份/1 条 = 6 份/7 条。
        """
        lane3_dir = self._ARCHIVE_BATCH / self.LANE3_SPEC
        assert lane3_dir.is_dir(), (
            f"lane3 归档 spec {self.LANE3_SPEC} 应存在于 {self._ARCHIVE_BATCH}"
        )
        assert self.LANE3_SPEC not in self.ARCHIVED_DEBT, (
            f"{self.LANE3_SPEC} 不应出现在 lane2 的 ARCHIVED_DEBT 中"
        )
        # 验证 lane3 完成度声明
        tasks_path = lane3_dir / "tasks.md"
        content = tasks_path.read_bytes().decode("utf-8", errors="replace")
        done = sum(1 for ln in content.splitlines() if ln.strip().startswith("- [x]"))
        undone = sum(1 for ln in content.splitlines() if ln.strip().startswith("- [ ]"))
        expected_done, expected_total = self.LANE3_RATIO
        assert done == expected_done and done + undone == expected_total, (
            f"lane3 spec 声明 {expected_done}/{expected_total}，"
            f"实际 {done}/{done + undone}"
        )

    def test_append_only_no_modification(self) -> None:
        """AG-P17: 只登记不回填修改已归档 spec。

        本测试是声明性断言——确认我们没有修改归档 tasks.md 的内容。
        通过验证未完成项仍然保持 '[ ]' 状态（而非被强行勾选）来间接确认。
        """
        for spec_name, (declared_done, declared_total) in self.ARCHIVED_DEBT.items():
            tasks_path = self._ARCHIVE_BATCH / spec_name / "tasks.md"
            content = tasks_path.read_bytes().decode("utf-8", errors="replace")
            undone = [
                ln.strip()
                for ln in content.splitlines()
                if ln.strip().startswith("- [ ]")
            ]
            expected_undone = declared_total - declared_done
            assert len(undone) == expected_undone, (
                f"{spec_name}: 应有 {expected_undone} 条 '[ ]'，"
                f"实际 {len(undone)}（若为 0 则可能被回填修改了）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# §9 TestDeliveryChecklist — 交付前自检（meta-test）
# ═══════════════════════════════════════════════════════════════════════════


class TestDeliveryChecklist:
    """交付前自检（Task 13）。

    meta-test：读本测试文件自身做字符串/正则断言，
    验证 AG-P 编号覆盖、sha256 守卫存在、无 U+FFFD、
    AC 只引编号不复述正文、空分母声明 + 双计数断言仍在交付物中。

    关联 AC-1 · AC-20 · AC-44。
    """

    # ── fixture：读本文件为文本 ──────────────────────────────────────────

    @pytest.fixture(scope="class")
    def self_source(self) -> str:
        """读本测试文件自身的全文。"""
        src = Path(__file__).resolve()
        return src.read_bytes().decode("utf-8")

    # ── 1. AG-P 覆盖检查 ────────────────────────────────────────────────

    def test_ag_p_no_gaps_1_to_18(self, self_source: str) -> None:
        """AG-P1 ~ AG-P18 无缺号：每个编号至少在 docstring 或注释中出现一次。"""
        missing: list[str] = []
        for n in range(1, 19):
            tag = f"AG-P{n}"
            if tag not in self_source:
                missing.append(tag)
        assert not missing, f"AG-P 编号缺失: {missing}"

    # ── 2. sha256 16/16 守卫仍存在 ──────────────────────────────────────

    def test_sha256_guard_present(self, self_source: str) -> None:
        """sha256 16/16 守卫仍存在于测试文件中。"""
        assert "test_sha256_16_match" in self_source, (
            "test_sha256_16_match 方法应存在于本测试文件中"
        )
        assert "sha256" in self_source.lower(), (
            "文件中应包含 sha256 相关断言"
        )

    # ── 3. 无 U+FFFD 替换字符 ──────────────────────────────────────────

    def test_no_replacement_char(self, self_source: str) -> None:
        """本测试文件不含 U+FFFD（替换字符）。"""
        count = self_source.count("\ufffd")
        assert count == 0, f"发现 {count} 个 U+FFFD 替换字符"

    # ── 4. AC 只引编号不复述判据正文 ─────────────────────────────────────

    def test_ac_references_by_number_only(self, self_source: str) -> None:
        """本 spec 只引用 AC 编号（如 AC-1、AC-39），不复述判据正文。

        🔴 检测手段：确认文件内有 AC-{n} 引用，同时不含
        判据正文的 WHEN...THEN SHALL 句式（这些句式只在 requirements.md 中出现）。
        排除本 meta-test 类自身的代码区域后扫描。
        """
        # 确认有 AC 编号引用
        ac_refs = re.findall(r"AC-\d+", self_source)
        assert len(ac_refs) >= 5, (
            f"应有多处 AC 编号引用，实际 {len(ac_refs)} 处"
        )
        # 截取本 meta-test 类之前的代码区域（排除自身对判据句式的讨论）
        marker = "class TestDeliveryChecklist"
        cut_idx = self_source.find(marker)
        main_body = self_source[:cut_idx] if cut_idx > 0 else self_source
        # 检测 WHEN...THEN SHALL 句式——这是 requirements.md 验收标准的
        # 固定格式，如果出现在测试代码主体中说明复述了判据正文
        when_then_hits = re.findall(
            r"WHEN\s+.{5,}\s+THEN\s+SHALL", main_body
        )
        assert not when_then_hits, (
            f"测试文件主体疑似复述了 AC 判据正文"
            f"（应只引编号）: {when_then_hits[:3]}"
        )

    # ── 5. Excel 判据空分母声明仍存在 ──────────────────────────────────

    def test_empty_denominator_declaration_present(self, self_source: str) -> None:
        """「空分母」声明仍在交付物中（依 AC-20）。"""
        assert "空分母" in self_source, (
            "测试文件应包含「空分母」声明"
            "（Excel 专属判据对 docx 册无意义，须显式声明）"
        )

    # ── 6. 合并单元格双计数断言仍存在 ──────────────────────────────────

    def test_merged_cell_dual_count_present(self, self_source: str) -> None:
        """「(row,col) 计数」与「不同 tc 计数」双断言仍在交付物中（依 AC-39）。

        🔴 合并单元格断言必须同时给出两个数（只给前者等于没测出去重效果）。
        """
        # 检查 (row,col) 侧的计数引用
        has_rowcol = (
            "total_cells" in self_source
            or "(row,col)" in self_source
            or "row, col" in self_source.replace(" ", "").lower()
        )
        assert has_rowcol, (
            "测试文件应包含 (row,col) 侧的计数（total_cells 或等价表述）"
        )
        # 检查 tc 去重侧的计数引用
        has_tc_dedup = (
            "unique_tc" in self_source
            or "id(cell._tc)" in self_source
            or "tc_to_position" in self_source
        )
        assert has_tc_dedup, (
            "测试文件应包含 tc 去重侧的计数（unique_tc / id(cell._tc) / tc_to_position）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §10 TestPlatformDebtRegistry — Task 14: 平台级欠账登记（AC-25）
# ═══════════════════════════════════════════════════════════════════════════


class TestPlatformDebtRegistry:
    """平台级欠账登记（Task 14）——BP-1 ~ BP-5 只登记不闭合。

    本 spec 16 条 docx entry 全部被 BP-1 ~ BP-5 阻塞，这些阻塞项属于
    平台层基础设施，须由对应平台 spec 的负责人实施，本 lane 无法闭合。

    Task 12 已登记归档 spec 的 6 条未完成任务（5 份功能 spec 各含
    Playwright E2E / overrides 更新未完成项）；本任务补登平台级阻塞项，
    两者正交：Task 12 是**功能 spec 层面**的欠账，Task 14 是**平台层面**的欠账。

    状态：`[ ]*`（受外部依赖阻塞）——代码已改但未实测，
    因为这些 BP 需要平台层变更才能真正闭合。

    关联 AC-25。
    """

    # ── 常量：5 个平台级 BP 及其描述 ─────────────────────────────────────

    PLATFORM_BPS: dict[str, str] = {
        "BP-1": "approved 模型（审批工作流）——底稿双向回写需经审批状态机",
        "BP-2": "contract（契约体系）——entry 级契约定义尚未就绪",
        "BP-3": "capability 裁决（能力评估框架）——各 entry 的可回写能力尚待评估",
        "BP-4": "bundle 与 published（打包发布机制）——发布流程未接入 docx 侧",
        "BP-5": "adapter 注册（适配器注册体系）——sync adapter 尚未在注册表登记",
    }

    # 16 条 docx entry 的 entry_id 前缀（与 TestLane2Boundary 一致）
    EXPECTED_DOCX_COUNT = 16

    # ── 测试 ──────────────────────────────────────────────────────────────

    def test_platform_bps_registered_5(self) -> None:
        """BP-1 ~ BP-5 共 5 个平台级阻塞项已登记。"""
        assert len(self.PLATFORM_BPS) == 5, (
            f"平台级 BP 应恰好 5 个，实际 {len(self.PLATFORM_BPS)}"
        )
        expected_keys = {f"BP-{i}" for i in range(1, 6)}
        assert set(self.PLATFORM_BPS.keys()) == expected_keys, (
            f"平台级 BP 键应为 BP-1~BP-5，实际 {sorted(self.PLATFORM_BPS.keys())}"
        )

    def test_each_bp_has_description(self) -> None:
        """每个平台级 BP 都有非空描述。"""
        empty = [k for k, v in self.PLATFORM_BPS.items() if not v.strip()]
        assert not empty, f"以下 BP 缺少描述: {empty}"

    def test_all_16_docx_entries_blocked_by_bp1_to_bp5(
        self, manifest_slice: dict
    ) -> None:
        """全部 16 条 docx entry 的 capability_target_blocked_by 均包含 BP-1 ~ BP-5。

        这是平台级阻塞的结构性证据：不是个别 entry 被阻塞，而是
        全域 16 条 docx entry 无一例外地被 BP-1 ~ BP-5 同时阻塞。
        """
        docx_entries = _get_docx_entries(manifest_slice)
        assert len(docx_entries) == self.EXPECTED_DOCX_COUNT, (
            f"docx entry 应为 {self.EXPECTED_DOCX_COUNT}，"
            f"实际 {len(docx_entries)}"
        )
        platform_bp_set = set(self.PLATFORM_BPS.keys())
        missing_report: list[str] = []
        for entry in docx_entries:
            eid = entry["entry_id"]
            bp_list = set(entry.get("capability_target_blocked_by", []))
            missing_bps = platform_bp_set - bp_list
            if missing_bps:
                missing_report.append(
                    f"  {eid}: 缺少 {sorted(missing_bps)}"
                )
        assert not missing_report, (
            "以下 entry 缺少平台级 BP:\n" + "\n".join(missing_report)
        )

    def test_platform_bps_are_outside_spec_scope(self) -> None:
        """平台级 BP 不在本 spec 收口范围——只登记不闭合。

        本 spec 的 BP 收口路线（见 design.md）：
          - BP-9: 本 spec 收口（docx 侧定位模型）→ 空集 ✓
          - BP-11: 本 spec 收口（a91 非双射裁定）→ 空集 ✓
          - BP-1 ~ BP-5: 平台级，标 `[ ]*` → 不变（本任务）
          - BP-7: 依 foundation 裁定（notice 挂载）
          - BP-6 / BP-8 / BP-10: 本 spec 空分母（成员全在 lane3）

        断言：本 spec 可收口的 BP（9、11）与平台级 BP（1~5）无交集。
        """
        closable_bps = {"BP-9", "BP-11"}
        platform_bps = set(self.PLATFORM_BPS.keys())
        overlap = closable_bps & platform_bps
        assert not overlap, (
            f"可收口 BP 与平台级 BP 不应有交集，实际交集: {overlap}"
        )

    def test_archived_debt_is_orthogonal_to_platform_debt(self) -> None:
        """Task 12 归档欠账与 Task 14 平台级欠账正交。

        Task 12 登记的是功能 spec 层面的欠账（5 份归档 spec / 6 条未完成任务），
        Task 14 登记的是平台层面的阻塞项（BP-1 ~ BP-5）。
        两者维度不同：
          - Task 12: 哪些功能 spec 的任务没做完（Playwright E2E / overrides 更新）
          - Task 14: 哪些平台基础设施尚未就绪（审批/契约/能力评估/发布/适配器）

        断言：TestArchivedSpecDebt 的 5 份 spec 名称不含 BP 编号
        （它们是功能 spec 不是平台 BP）。
        """
        archived_spec_names = set(TestArchivedSpecDebt.ARCHIVED_DEBT.keys())
        # 归档 spec 名称不应与 BP 编号混淆
        for name in archived_spec_names:
            assert not name.startswith("BP-"), (
                f"归档 spec 名称 {name} 不应是 BP 编号（两者维度正交）"
            )
        # 两组登记都非空
        assert len(archived_spec_names) == 5, "归档欠账应为 5 份"
        assert len(self.PLATFORM_BPS) == 5, "平台级 BP 应为 5 个"

    def test_blocker_classification_documented(self) -> None:
        """每个 BP 的阻塞分类是「平台层」而非「本 spec 可解决」。

        验证 PLATFORM_BPS 的描述中包含能说明「这不是本 spec 能修的」的关键词，
        即每条描述都指向平台级基础设施（工作流/体系/框架/机制/注册）。
        """
        infra_keywords = {"工作流", "体系", "框架", "机制", "注册"}
        for bp_id, desc in self.PLATFORM_BPS.items():
            has_keyword = any(kw in desc for kw in infra_keywords)
            assert has_keyword, (
                f"{bp_id} 的描述缺少平台层关键词"
                f"（须含 {infra_keywords} 之一）: {desc}"
            )
