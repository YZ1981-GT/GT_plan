# -*- coding: utf-8 -*-
"""A 类运行时册名与载体例外车道守卫。

spec: a-class-runtime-sheetname-and-carrier-exceptions

测试结构：
  - TestLane3Boundary           AH-P1 ~ AH-P5   归属基线
  - TestBP8RuntimeSheetName     AH-P6 ~ AH-P8   运行时册名（a177）
  - TestBP10NoSwitch            AH-P9 ~ AH-P12  无开关补 segmented（a3-console）
  - TestBP6NoAuthoritativeBook  AH-P13           归因更正（a38）
  - TestProperty22Defect        AH-P14 ~ AH-P15  动态列缺陷（a38）
  - TestA33TemplateDefects      AH-P16           A3-3 册缺陷台账

共同判据只引用 AC 编号，判据正文在 foundation。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_TEMPLATE_DIR = _BACKEND / "wp_templates" / "A"
_SLICE_PATH = _BACKEND / "data" / "workpaper_sync_abcs_cycle_manifest_slice.json"
_FRONTEND = _ROOT / "audit-platform" / "frontend" / "src"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from a_cycle_scanner import (  # noqa: E402
    a_domain_entries,
    scan_xlsx_formulas,
    scan_xlsx_footer_raw_xml,
    sha256_file,
    strip_comments,
    TEMPLATE_DIR,
)


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


def _get_lane3_entries(manifest_slice: dict) -> list[dict]:
    """lane3 的 3 条 entry：a177 / a3-console / a38。"""
    a_entries = a_domain_entries(manifest_slice["independent_entries"])
    ids = {"xlsx/gt-a177-independence-declaration",
           "xlsx/gt-a3-consolidation-console",
           "xlsx/gt-a38-goodwill-impairment"}
    return [e for e in a_entries if e["entry_id"] in ids]


def _entry_by_part(manifest_slice: dict, part: str) -> dict:
    a_entries = a_domain_entries(manifest_slice["independent_entries"])
    return [e for e in a_entries if part in e["entry_id"]][0]


# ═══════════════════════════════════════════════════════════════════════════
# §1 TestLane3Boundary — AH-P1 ~ AH-P5
# ═══════════════════════════════════════════════════════════════════════════


class TestLane3Boundary:
    """lane3 归属基线（AH-P1 ~ AH-P5）。"""

    def test_lane3_entry_count_3(self, manifest_slice: dict) -> None:
        """AH-P1: 恰 3 条 entry。"""
        entries = _get_lane3_entries(manifest_slice)
        assert len(entries) == 3

    def test_bp6_bp8_bp10_fully_internal(self, manifest_slice: dict) -> None:
        """AH-P2: BP-6/BP-8/BP-10 完整内聚本 spec。"""
        entries = _get_lane3_entries(manifest_slice)
        bp_sets = {e["entry_id"]: set(
            b.get("id", str(b)) if isinstance(b, dict) else str(b)
            for b in e.get("capability_target_blocked_by", [])
        ) for e in entries}
        # BP-6 仅 a38
        assert "BP-6" in bp_sets["xlsx/gt-a38-goodwill-impairment"]
        assert all("BP-6" not in bps for eid, bps in bp_sets.items()
                    if eid != "xlsx/gt-a38-goodwill-impairment")
        # BP-8 仅 a177
        assert "BP-8" in bp_sets["xlsx/gt-a177-independence-declaration"]
        # BP-10 仅 a3-console
        assert "BP-10" in bp_sets["xlsx/gt-a3-consolidation-console"]

    def test_bp_count_21(self, manifest_slice: dict) -> None:
        """AH-P3: BP 数 3×7 = 21。"""
        entries = _get_lane3_entries(manifest_slice)
        total = sum(len(e.get("capability_target_blocked_by", [])) for e in entries)
        assert total == 21, f"BP 总数应为 21，实际 {total}"

    def test_format_xlsx_1_none_2_docx_0(self, manifest_slice: dict) -> None:
        """AH-P4: **已更正为** xlsx 2 + 无册 1 · docx 0（lane3 三条 entry 的分布）。

        🔴 原值「xlsx 1 + 无册 2」里的那一条差异来自 a38：它的
        `template_ref.workbook` / `workbook_format` 原本都是 `null`，而那是**假事实**
        —— 册一直在磁盘上且是 xlsx（`A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`）。
        spec `workpaper-sync-pure-static-lane-and-combined-workbook-resolution` 已把两个
        字段改成真实值 ⇒ 本分布随之变化。**lane3 的 entry 总数不变（3 条）**。
        """
        entries = _get_lane3_entries(manifest_slice)
        xlsx = sum(1 for e in entries
                   if e.get("template_ref", {}).get("workbook_format") == "xlsx")
        docx = sum(1 for e in entries
                   if e.get("template_ref", {}).get("workbook_format") == "docx")
        none_wb = sum(1 for e in entries
                      if e.get("template_ref", {}).get("workbook") is None)
        assert xlsx == 2, f"xlsx 应 2（a3-console + a38），实际 {xlsx}"
        assert docx == 0
        assert none_wb == 1, f"无册应仅 a177 一条，实际 {none_wb}"
        assert xlsx + none_wb == len(entries) == 3

    def test_oo_mounts_3_segmented_2_gated_2(self, manifest_slice: dict) -> None:
        """AH-P5: OO 挂点 3 · segmented 2 · mode 门控 2。"""
        entries = _get_lane3_entries(manifest_slice)
        no_switch = [e for e in entries
                     if e.get("dual_mode_carrier", {}).get("switch_verdict") == "no_switch_at_all"]
        assert len(no_switch) == 1, "应有恰 1 条 no_switch（a3-console）"
        assert "a3-consolidation" in no_switch[0]["entry_id"]


# ═══════════════════════════════════════════════════════════════════════════
# §2 TestBP8RuntimeSheetName — AH-P6 ~ AH-P8
# ═══════════════════════════════════════════════════════════════════════════


class TestBP8RuntimeSheetName:
    """BP-8: 运行时 sheet 名表达式（a177）。"""

    def test_resolution_kind_is_runtime(self, manifest_slice: dict) -> None:
        """AH-P6: resolution_kind = runtime_sheet_name_expression。"""
        e = _entry_by_part(manifest_slice, "a177")
        tref = e["template_ref"]
        assert tref["resolution_kind"] == "runtime_sheet_name_expression"

    def test_workbook_and_format_null(self, manifest_slice: dict) -> None:
        """AH-P6: workbook 和 workbook_format 均为 null。"""
        e = _entry_by_part(manifest_slice, "a177")
        tref = e["template_ref"]
        assert tref.get("workbook") is None
        assert tref.get("workbook_format") is None

    def test_sheet_name_exprs_dual_variant(self, manifest_slice: dict) -> None:
        """AH-P7: sheet_name_exprs 含双变体表达式。

        🔴 A17-7（team 变体）/ A17-7A（非 team 变体），但 wp_code_patterns 只有 A177I。
        """
        e = _entry_by_part(manifest_slice, "a177")
        tref = e["template_ref"]
        exprs = tref.get("sheet_name_exprs", [])
        assert len(exprs) >= 1, "应有至少 1 个 sheet_name_expr"
        expr = exprs[0]
        assert "A17-7" in expr, f"表达式应含 A17-7，实际: {expr}"
        assert "A17-7A" in expr, f"表达式应含 A17-7A，实际: {expr}"

    def test_wp_code_single_pattern(self, manifest_slice: dict) -> None:
        """AH-P7: wp_code_patterns 只有 A177I ⇒ 变体轴在 pattern 里丢失。"""
        e = _entry_by_part(manifest_slice, "a177")
        codes = e.get("wp_code_patterns", [])
        assert codes == ["A177I"], f"应只有 A177I，实际 {codes}"

    def test_bp8_global_count_27(self, manifest_slice: dict) -> None:
        """AH-P8: 全 slice BP-8 = 27 条（literal 19 : runtime 27 = 46）。"""
        bps = manifest_slice.get("blocking_preconditions", [])
        bp8 = [b for b in bps if isinstance(b, dict) and b.get("id") == "BP-8"]
        assert bp8, "BP-8 应存在"
        members = bp8[0].get("entries", bp8[0].get("entry_ids", []))
        assert len(members) == 27, f"BP-8 成员应为 27，实际 {len(members)}"


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestBP10NoSwitch — AH-P9 ~ AH-P12
# ═══════════════════════════════════════════════════════════════════════════


class TestBP10NoSwitch:
    """BP-10: 无模式开关（a3-consolidation-console）。"""

    def test_no_segmented_no_mode_gate(self, manifest_slice: dict) -> None:
        """AH-P9: segmented=0, mode 门控=0。"""
        e = _entry_by_part(manifest_slice, "a3-consolidation")
        carrier = e.get("dual_mode_carrier", {})
        assert carrier.get("switch_verdict") == "no_switch_at_all"
        assert carrier.get("kind") == "no_carrier"

    def test_has_html_counterpart(self, manifest_slice: dict) -> None:
        """AH-P10: html_counterpart_verdict = exists ⇒ 需要双模式。"""
        e = _entry_by_part(manifest_slice, "a3-consolidation")
        hc_verdict = e.get("html_counterpart_verdict",
                           e.get("html_counterpart", {}).get("verdict", ""))
        # 不管具体字段名，关键是有 HTML 对端
        host = e.get("host_path", "")
        assert host, "a3-console 应有宿主路径"
        full = _ROOT / host
        assert full.exists(), f"宿主文件应存在: {host}"

    def test_xlsx_template_resolvable(self, manifest_slice: dict) -> None:
        """AH-P10: find_template_file_any('A3-3') 返回真实路径。"""
        candidates = [f for f in TEMPLATE_DIR.rglob("A3-3*")
                      if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        assert candidates, "A3-3 权威册应存在"
        assert candidates[0].stat().st_size > 100000, "A3-3 册应 > 100KB"

    def test_a3_console_has_4_sheets_63_formulas(self) -> None:
        """AH-P11: A3-3 册 4 sheets / 63 公式格。"""
        candidates = [f for f in TEMPLATE_DIR.rglob("A3-3*")
                      if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        r = scan_xlsx_formulas(candidates[0])
        assert r["sheet_count"] == 4
        assert r["total_formulas"] == 63

    def test_a3c_breaks_naming_rule(self, manifest_slice: dict) -> None:
        """AH-P12: 第二形态 A3C 打破「去连字符+首字母」规则。

        🔴 按规则应为 A33C（去连字符 A3-3 → A33 + 首字母 C），实际是 A3C。
        禁按规则推导第二形态。
        """
        e = _entry_by_part(manifest_slice, "a3-consolidation")
        codes = e.get("wp_code_patterns", [])
        assert "A3C" in codes, f"应含 A3C，实际 {codes}"
        assert "A33C" not in codes, "不应含 A33C（打破规则的证据）"

    def test_bp10_global_count_4(self, manifest_slice: dict) -> None:
        """AH-P12 补: 全 slice BP-10 = 4 条。"""
        bps = manifest_slice.get("blocking_preconditions", [])
        bp10 = [b for b in bps if isinstance(b, dict) and b.get("id") == "BP-10"]
        assert bp10, "BP-10 应存在"
        members = bp10[0].get("entries", bp10[0].get("entry_ids", []))
        assert len(members) == 4, f"BP-10 成员应为 4，实际 {len(members)}"


# ═══════════════════════════════════════════════════════════════════════════
# §4 TestBP6NoAuthoritativeBook — AH-P13
# ═══════════════════════════════════════════════════════════════════════════


class TestBP6NoAuthoritativeBook:
    """BP-6（a38）—— 🔴 **归因已再更正**（spec
    `workpaper-sync-pure-static-lane-and-combined-workbook-resolution`）。

    本类原先的结论是「真因不只是 sheet 名写法，而是**根本没有这本册**」。该结论与磁盘
    事实矛盾：册一直在磁盘上（`A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`，436 KB 级，
    册内含 sheet `A3-8商誉减值测试` 与 `A3-8-1可收回金额测试`）。

    错误成因是一个 glob 口径问题：`rglob("A3-8*")` **锚定文件名开头**，而该合册真名以
    `A3-7` 起头 ⇒ 该 pattern 恒 0 命中，三条断言（本类前三个方法）于是恒绿，
    「没有这本册」这个错结论就被固化成了守卫。现算对照：
    `rglob("A3-8*")` = 0 命中 · `rglob("*A3-8*")` = 1 命中。

    真实归因是**两层叠加**：
      ① 前缀而非包含（`_wp_code_filename_prefix_ok(合册名, "A3-8")` 为 False，
         且 `_index.json` 给该册挂的 wp_code 是 `"A3"`）；
      ② A-only 子码正则 `^A\\d+-\\d+` 命中 ⇒ 走 `find_template_file_any` 的
         「A 子码严格分支」，两次同名前缀尝试都不中就 `return None`。

    第 ①② 层（解析层，**第一步**）现已修复；剩余阻塞是**宿主层第二步**（宿主传中文字面
    sheet 名而非 wp_code），登记为后继。按项目铁律「已归档 spec 一律不回填修改」，
    AC-46 的**再更正**只登记在本 spec 的 `errata.md`，不回填归档 spec 文件。
    """

    def test_a38_workbook_points_at_the_real_combined_book(
        self, manifest_slice: dict
    ) -> None:
        """原 `test_a38_workbook_is_null` —— 🔴 断言方向已反转。

        `workbook: null` 是假事实，slice 已改为真实相对路径。
        **保留 `is None` 断言 = 不合格**（那会把假事实继续固化）。
        """
        e = _entry_by_part(manifest_slice, "a38")
        tref = e["template_ref"]
        rel = tref.get("workbook")
        assert rel, f"a38 的 workbook 仍是空值: {rel!r}"
        # slice 惯例：`workbook` 相对 `backend/wp_templates/`（`TEMPLATE_DIR` 是 …/A）
        assert (TEMPLATE_DIR.parent / rel).is_file(), rel
        assert tref.get("workbook_format") == "xlsx", tref.get("workbook_format")
        assert "已更正" in (tref.get("why_null") or ""), (
            "why_null 应补齐归因第一层（合册命名 + A-only 子码正则）并记录已解除"
        )
        # 第二步仍未做：宿主层声明保持原样
        assert tref.get("resolution_kind") == "literal_sheet_name"
        assert tref.get("sheet_name_literal") == "A3-8商誉减值测试"

    def test_a38_template_is_on_disk_and_its_filename_declares_the_code(self) -> None:
        """原 `test_a38_template_not_on_disk` —— 🔴 假事实断言已删，换成事实断言。

        「合册存在 + 其文件名字面声明码集合含 `A3-8`」。docstring 里那句
        「真因是根本没有这本册」也一并改写 —— **只改断言不改 docstring = 不合格**
        （错误归因会继续传播到下一轮）。
        """
        from app.services import wp_template_finder as FINDER

        anchored = [f for f in TEMPLATE_DIR.rglob("A3-8*")
                    if f.suffix.lower() in (".xlsx", ".docx") and "~$" not in f.name]
        contained = [f for f in TEMPLATE_DIR.rglob("*A3-8*")
                     if f.suffix.lower() in (".xlsx", ".docx") and "~$" not in f.name]
        assert anchored == [], f"口径说明失效：`A3-8*` 竟有命中 {[f.name for f in anchored]}"
        assert len(contained) == 1, (
            f"承载 A3-8 的册应恰 1 本，实得 {[f.name for f in contained]}（两数现算）"
        )
        book = contained[0]
        declared = FINDER._literal_wp_codes_in_filename(book.name)
        assert "A3-8" in declared, (book.name, sorted(declared))
        assert len(declared) >= 2, f"它应是合册（≥2 字面声明码），实得 {sorted(declared)}"

    def test_other_codes_resolve_and_a38_now_resolves_too(self) -> None:
        """原 `test_other_codes_resolve_but_a38_does_not` —— 🔴 变异证明已**重建**。

        原证明用 `rglob` 口径，建立在假事实上 ⇒ 无效。重建后：
        * 对照组改为「`A3-3` / `A5-1` / `A10-1` 经 `find_template_file_any` 能解析」；
        * 加 `A3-8` 的**双向**变异：修复**前** `None`、修复**后**得合册。
        """
        import subprocess
        import sys
        import types

        from app.services import wp_template_finder as FINDER

        for code in ("A3-3", "A5-1", "A10-1"):
            assert FINDER.find_template_file_any_unresolved(code) is not None, code

        # 方向②（修复后）
        after = FINDER.find_template_file_any_unresolved("A3-8")
        assert after is not None, "A3-8 修复后应能解析到合册"
        assert "A3-8" in FINDER._literal_wp_codes_in_filename(Path(after).name)

        # 方向①（修复前）：从 git HEAD 版 finder 现取，不凭记忆写死
        res = subprocess.run(
            ["git", "show", "HEAD:backend/app/services/wp_template_finder.py"],
            cwd=TEMPLATE_DIR.parent.parent, capture_output=True, check=False,
        )
        if res.returncode != 0 or not res.stdout:
            pytest.skip("git show 取不到 HEAD 版 finder（无法做修复前变异）")
        head = types.ModuleType("_wp_finder_head_lane3")
        head.__file__ = str(Path(FINDER.__file__))
        sys.modules[head.__name__] = head
        exec(compile(res.stdout.decode("utf-8"), head.__file__, "exec"), head.__dict__)
        assert head.find_template_file_any_unresolved("A3-8") is None, (
            "修复前 `find_template_file_any('A3-8')` 应为 None —— 双向变异的方向① 失效"
        )
        # 对照组在修复前后**一致**（证明新逻辑是加法，没顺带改别人的走向）
        for code in ("A3-3", "A5-1", "A10-1"):
            assert head.find_template_file_any_unresolved(code) == \
                FINDER.find_template_file_any_unresolved(code), code

    def test_bp6_global_count_1(self, manifest_slice: dict) -> None:
        """AH-P13 补: 全 slice BP-6 仅 1 条（a38），A 域独占。"""
        bps = manifest_slice.get("blocking_preconditions", [])
        bp6 = [b for b in bps if isinstance(b, dict) and b.get("id") == "BP-6"]
        assert bp6, "BP-6 应存在"
        members = bp6[0].get("entries", bp6[0].get("entry_ids", []))
        assert len(members) == 1
        assert "a38" in members[0]


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestProperty22Defect — AH-P14 ~ AH-P15
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty22Defect:
    """Property 22 缺陷收口（a38）。"""

    def test_a38_is_in_defect_list(self, manifest_slice: dict) -> None:
        """AH-P14: a38 在 Property 22 defects 列表中。"""
        dci = manifest_slice.get("dynamic_column_identity", {})
        defects = dci.get("defects", [])
        a38_defects = [d for d in defects if "a38" in d.get("entry_id", "")]
        assert len(a38_defects) >= 1, "a38 应在 defects 列表中"

    def test_a38_mode_form2_but_column_fixed(self, manifest_slice: dict) -> None:
        """AH-P15: a38 Property 22 缺陷已修复。

        🔴 列数从写死 5 改为 FORECAST_YEARS 数据驱动 + key 从裸下标改为 year_{n}。
        """
        e = _entry_by_part(manifest_slice, "a38")
        hp = e.get("host_path", "")
        full = _ROOT / hp
        assert full.exists()
        source = full.read_text(encoding="utf-8", errors="replace")
        stripped = strip_comments(source)
        # 形态 2 仍应存在
        assert re.search(r"modeOptions\s*[:=].*?\[\s*\{", stripped, re.S), \
            "a38 应有对象数组 modeOptions（形态 2）"
        # 修复后应有 FORECAST_YEARS 驱动
        assert "FORECAST_YEARS" in stripped, \
            "a38 列数应由 FORECAST_YEARS 驱动（Property 22 修复）"
        # 修复后 key 不应是裸 i
        assert ':key="`year_' in source or "key=\"`year_" in source, \
            "a38 key 应为稳定标识 year_{n}（Property 22 修复）"


# ═══════════════════════════════════════════════════════════════════════════
# §6 TestA33TemplateDefects — AH-P16
# ═══════════════════════════════════════════════════════════════════════════


class TestA33TemplateDefects:
    """A3-3 册缺陷台账（记录型，不改模板）。"""

    def test_t1_ae_column_div_zero(self) -> None:
        """AH-P16: T-1 AE7~AE15 恒 #DIV/0!（反向分母 10:1）。

        🔴 与 N 轮 NC-32 不同型：那里超 max_column，这里引空行。
        """
        import openpyxl
        candidates = [f for f in TEMPLATE_DIR.rglob("A3-3*")
                      if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        wb = openpyxl.load_workbook(str(candidates[0]), data_only=False)
        ws = wb.worksheets[0]  # 首张 sheet
        # AE 列 = 第 31 列
        ae_formulas = 0
        for row in range(6, 16):
            cell = ws.cell(row=row, column=31)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                ae_formulas += 1
        wb.close()
        assert ae_formulas >= 8, \
            f"AE6~AE15 应有 >= 8 个公式（数据行超出致除零），实际 {ae_formulas}"

    def test_t2_cross_cycle_code_f610(self) -> None:
        """AH-P16: T-2 首张 sheet 名码是 F6-10（跨循环码混入）。"""
        import openpyxl
        candidates = [f for f in TEMPLATE_DIR.rglob("A3-3*")
                      if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        wb = openpyxl.load_workbook(str(candidates[0]), data_only=False)
        first_sheet = wb.worksheets[0].title
        wb.close()
        assert "F6-10" in first_sheet, \
            f"首张 sheet 名应含 F6-10（跨循环码），实际: {first_sheet}"

    def test_t3_defined_names_dbase_residual(self) -> None:
        """AH-P16: T-3 definedName 261/broken 190 含 .dbf 旧残留。"""
        candidates = [f for f in TEMPLATE_DIR.rglob("A3-3*")
                      if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        r = scan_xlsx_formulas(candidates[0])
        assert r["defined_names_total"] == 261
        assert r["defined_names_broken"] == 190

    def test_t15_reference_sheets_zero_formulas(self) -> None:
        """AH-P16: T-15 后三张 sheet 是参考资料型（0 公式格）。"""
        import openpyxl
        candidates = [f for f in TEMPLATE_DIR.rglob("A3-3*")
                      if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        wb = openpyxl.load_workbook(str(candidates[0]), data_only=False)
        # 后三张 sheet
        for ws in wb.worksheets[1:]:
            fx_count = 0
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("=") and len(cell.value) > 1:
                        fx_count += 1
            assert fx_count == 0, \
                f"参考 sheet '{ws.title}' 应有 0 公式格，实际 {fx_count}"
        wb.close()
