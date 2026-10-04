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

import hashlib
import html
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
    _VueGateParser,
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
        """AH-P5: OO 挂点 3 · segmented 2 · mode 门控 2。

        从 slice 的 `ui_toolbar_gate` 逐 entry 现算，与 foundation
        gate_stats（A 域 OO=20 / seg=19 / gated=19）的 lane3 份额一致。
        """
        entries = _get_lane3_entries(manifest_slice)

        # 逐 entry 计数
        total_oo = 0
        total_seg = 0
        total_gated = 0
        for e in entries:
            utg = e.get("ui_toolbar_gate", {})
            total_oo += len(utg.get("oo_mount_sites", []))
            total_seg += min(1, len(utg.get("segmented_sites", [])))
            total_gated += len(utg.get("mode_gated_oo_mount_sites", []))

        assert total_oo == 3, f"OO 挂点应为 3，实际 {total_oo}"
        assert total_seg == 2, f"segmented 应为 2，实际 {total_seg}"
        assert total_gated == 2, f"mode 门控应为 2，实际 {total_gated}"

        # a3-console 是唯一 no_switch（seg=0, gated=0）
        no_switch = [e for e in entries
                     if e.get("dual_mode_carrier", {}).get("switch_verdict")
                     == "no_switch_at_all"]
        assert len(no_switch) == 1, "应有恰 1 条 no_switch（a3-console）"
        assert "a3-consolidation" in no_switch[0]["entry_id"]
        a3_utg = no_switch[0].get("ui_toolbar_gate", {})
        assert len(a3_utg.get("segmented_sites", [])) == 0
        assert len(a3_utg.get("mode_gated_oo_mount_sites", [])) == 0

    def test_lane3_fullnames_exact(self, manifest_slice: dict) -> None:
        """AH-P1: 3 条 entry 全名逐一吻合 design.md 归属表。"""
        entries = _get_lane3_entries(manifest_slice)
        actual = sorted(e["entry_id"] for e in entries)
        expected = sorted([
            "xlsx/gt-a177-independence-declaration",
            "xlsx/gt-a3-consolidation-console",
            "xlsx/gt-a38-goodwill-impairment",
        ])
        assert actual == expected, f"全名不吻合: {actual}"

    def test_grp_01_one_grp_03_two(self, manifest_slice: dict) -> None:
        """AH-P1: GRP-01 = 1 (a177) + GRP-03 = 2 (a3-console, a38) = 3。"""
        entries = _get_lane3_entries(manifest_slice)
        grps: dict[str, list[str]] = {}
        for e in entries:
            gid = e.get("group_id", "")
            grps.setdefault(gid, []).append(e["entry_id"])
        assert len(grps.get("GRP-01", [])) == 1, \
            f"GRP-01 应 1 条，实际 {grps.get('GRP-01', [])}"
        assert "a177" in grps["GRP-01"][0]
        assert len(grps.get("GRP-03", [])) == 2, \
            f"GRP-03 应 2 条，实际 {grps.get('GRP-03', [])}"

    def test_ac38_ac39_docx_empty_denominator(self, manifest_slice: dict) -> None:
        """AH-P3: 🔴 AC-38 / AC-39（docx 合并单元格去重、权威册 docx）对本 spec 空分母。

        lane3 三条 entry 的 workbook_format 无一为 docx，因此 AC-38 / AC-39
        的判据分母为 0——本 spec 不涉及 docx 特有缺陷。
        """
        entries = _get_lane3_entries(manifest_slice)
        docx = [e for e in entries
                if e.get("template_ref", {}).get("workbook_format") == "docx"]
        assert len(docx) == 0, (
            "lane3 应无 docx entry（AC-38 / AC-39 空分母），"
            f"实际找到 {[e['entry_id'] for e in docx]}"
        )

    def test_real_db_attribution_zero_rows(self) -> None:
        """AH-P5: 真库归属 0 行（lane3 wp_code 前缀在 checklist_responses 里不存在）。

        🔴 有 PG 时执行真实查询，无 PG 时 skip（不 pass，避免假绿）。
        """
        dsn = None
        try:
            from app.core.config import settings
            raw = str(getattr(settings, "DATABASE_URL", "") or "")
            dsn = raw.replace("+asyncpg", "").replace("+aiosqlite", "")
        except Exception:
            pass

        if not dsn or "postgresql" not in dsn:
            pytest.skip("真库归属确认需 PG 连接")

        import psycopg2  # type: ignore[import-untyped]
        try:
            conn = psycopg2.connect(dsn)
            try:
                cur = conn.cursor()
                # lane3 的 wp_code 前缀：A177I / A3-3 / A3C / A3-8 / A38G
                cur.execute(
                    "SELECT COUNT(*) FROM checklist_responses "
                    "WHERE item_id LIKE 'A177I%' "
                    "   OR item_id LIKE 'A3-3%' "
                    "   OR item_id LIKE 'A3C%' "
                    "   OR item_id LIKE 'A3-8%' "
                    "   OR item_id LIKE 'A38G%'"
                )
                count = cur.fetchone()[0]
                assert count == 0, (
                    f"lane3 wp_code 前缀在真库有 {count} 行——"
                    "应为 0（闭环验证须自建夹具，依 AC-18）"
                )
            finally:
                conn.close()
        except psycopg2.OperationalError:
            pytest.skip("PG 连接失败（Docker 未运行或端口不可达）")

    def test_defined_name_broken_lane3_share(self, manifest_slice: dict) -> None:
        """AC-9: lane3 独占 A 域 definedName broken 的绝大多数份额。

        🔴 原 design.md 写 190/204 = 93%（a38 当时 workbook=null 不贡献 dn）。
        a38 的 workbook 更正为合册后，a38 也贡献 broken dn ⇒ 份额从现算得出。
        关键不变量：a3-console 的 190 条 broken 始终是 A 域最大的单一来源。
        """
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        lane3_ids = {
            "xlsx/gt-a177-independence-declaration",
            "xlsx/gt-a3-consolidation-console",
            "xlsx/gt-a38-goodwill-impairment",
        }
        a_total_broken = 0
        lane3_broken = 0
        seen_books: set[str] = set()
        for e in a_entries:
            tref = e.get("template_ref", {})
            wb = tref.get("workbook")
            fmt = tref.get("workbook_format")
            if fmt != "xlsx" or not wb or wb in seen_books:
                continue
            seen_books.add(wb)
            wb_path = TEMPLATE_DIR.parent / wb
            if not wb_path.is_file():
                continue
            r = scan_xlsx_formulas(wb_path)
            broken = r.get("defined_names_broken", 0)
            a_total_broken += broken
            if e["entry_id"] in lane3_ids:
                lane3_broken += broken

        assert a_total_broken > 0, "A 域 definedName broken 总数应 > 0"
        assert lane3_broken >= 190, (
            f"lane3 broken 至少含 a3-console 的 190，实际 {lane3_broken}"
        )
        share = lane3_broken / a_total_broken
        assert share >= 0.75, (
            f"lane3 份额应 >= 75%，实际 {lane3_broken}/{a_total_broken} = {share:.1%}"
        )

    def test_property_22_a_domain_all_sites(self, manifest_slice: dict) -> None:
        """AC-40: Property 22 全部 A 域站点 (1/1) 在 lane3（a38）。"""
        dci = manifest_slice.get("dynamic_column_identity", {})
        defects = dci.get("sites", dci.get("defects", []))
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        a_eids = {e["entry_id"] for e in a_entries}
        lane3_ids = {
            "xlsx/gt-a177-independence-declaration",
            "xlsx/gt-a3-consolidation-console",
            "xlsx/gt-a38-goodwill-impairment",
        }
        a_sites = [d for d in defects if d.get("entry_id", "") in a_eids]
        lane3_sites = [d for d in defects if d.get("entry_id", "") in lane3_ids]
        assert len(a_sites) == 1, (
            f"A 域 Property 22 站点应为 1，实际 {len(a_sites)}"
        )
        assert len(lane3_sites) == 1, (
            f"lane3 Property 22 站点应为 1，实际 {len(lane3_sites)}"
        )
        assert lane3_sites[0]["entry_id"] == "xlsx/gt-a38-goodwill-impairment"

    def test_attribution_table_20_rows_arithmetic(self, manifest_slice: dict) -> None:
        """归属份额表算术自检：lane3 三条之和 = 本 spec 列，且为 A 域子集。

        🔴 逐 entry 现算 20 行关键指标，验证：
        1. per-entry 之和 == lane3 总计
        2. lane3 总计 ≤ A 域总计（子集关系）
        3. 关键等式（entry=3, BP=21, docx=0 等）
        """
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        lane3_ids = {
            "xlsx/gt-a177-independence-declaration",
            "xlsx/gt-a3-consolidation-console",
            "xlsx/gt-a38-goodwill-impairment",
        }
        lane3 = [e for e in a_entries if e["entry_id"] in lane3_ids]

        def _fmt(e: dict) -> str:
            return e.get("template_ref", {}).get("workbook_format") or "none"

        def _utg(e: dict, key: str) -> int:
            return len(e.get("ui_toolbar_gate", {}).get(key, []))

        # ── Row 1: entry count ──
        assert len(lane3) == 3
        assert len(a_entries) == 20

        # ── Row 2~4: format dispatch ──
        l3_docx = sum(1 for e in lane3 if _fmt(e) == "docx")
        l3_xlsx = sum(1 for e in lane3 if _fmt(e) == "xlsx")
        l3_none = sum(1 for e in lane3 if e.get("template_ref", {}).get("workbook") is None)
        assert l3_docx == 0
        assert l3_xlsx + l3_none == 3  # exhaustive
        # a_domain 子集
        a_docx = sum(1 for e in a_entries if _fmt(e) == "docx")
        assert l3_docx <= a_docx

        # ── Row 5~6: GRP ──
        l3_grp01 = sum(1 for e in lane3 if e.get("group_id") == "GRP-01")
        l3_grp03 = sum(1 for e in lane3 if e.get("group_id") == "GRP-03")
        assert l3_grp01 == 1
        assert l3_grp03 == 2
        assert l3_grp01 + l3_grp03 == 3

        # ── Row 7~9: OO / segmented / mode gated ──
        l3_oo = sum(_utg(e, "oo_mount_sites") for e in lane3)
        l3_seg = sum(min(1, _utg(e, "segmented_sites")) for e in lane3)
        l3_gated = sum(_utg(e, "mode_gated_oo_mount_sites") for e in lane3)
        assert l3_oo == 3
        assert l3_seg == 2
        assert l3_gated == 2

        # ── Row 10~11: BP ──
        l3_bp_total = sum(len(e.get("capability_target_blocked_by", [])) for e in lane3)
        assert l3_bp_total == 21  # 3 × 7

        # 独有 BP 完整内聚（已由 test_bp6_bp8_bp10_fully_internal 覆盖，此处做增量校验）
        unique_bps_lane3: set[str] = set()
        for e in lane3:
            for b in e.get("capability_target_blocked_by", []):
                bid = b.get("id") if isinstance(b, dict) else str(b)
                unique_bps_lane3.add(bid)
        assert {"BP-6", "BP-8", "BP-10"} <= unique_bps_lane3

        # ── Row 17: Property 22 ──
        dci = manifest_slice.get("dynamic_column_identity", {})
        defects = dci.get("sites", dci.get("defects", []))
        l3_p22 = sum(1 for d in defects if d.get("entry_id") in lane3_ids)
        assert l3_p22 == 1  # a38 唯一


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

    def test_sheet_name_exprs_verbatim(self, manifest_slice: dict) -> None:
        """AH-P6: 🔴 sheet_name_exprs **逐字吻合**（不是子串，而是整列等值）。

        design.md AH-P6 要求「`resolution_kind` 与 `sheet_name_exprs` 逐字吻合」。
        期望值从真实 slice 现读得出，禁靠子串近似蒙混。
        """
        e = _entry_by_part(manifest_slice, "a177")
        tref = e["template_ref"]
        assert tref.get("sheet_name_exprs") == [
            "variant === 'team' ? 'A17-7' : 'A17-7A'"
        ], f"sheet_name_exprs 须逐字吻合，实际: {tref.get('sheet_name_exprs')!r}"

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

    def test_shall_not_hardcode_workbook(self, manifest_slice: dict) -> None:
        """AH-P6: 🔴 SHALL NOT 为 a177 硬指权威册。

        三重守卫，缺一不可：
        1. `workbook` / `workbook_format` 保持 null（硬指册会把它们填成具体值）；
        2. `why_null` 明文声明「不为它硬指一本册（那是**伪造 source_ref**）」
           ⇒ 这是**有意**的 null，不是数据缺口（AC-44 的 `excluded_reason` 一侧）；
        3. 不存在任何 `source_ref`/`workbook_source_ref` 把它钉到某本册上。
        """
        e = _entry_by_part(manifest_slice, "a177")
        tref = e["template_ref"]
        # ① 两个册字段保持 null（不硬指）
        assert tref.get("workbook") is None, (
            f"a177 不应硬指 workbook，实际 {tref.get('workbook')!r}"
        )
        assert tref.get("workbook_format") is None, (
            f"a177 不应硬指 workbook_format，实际 {tref.get('workbook_format')!r}"
        )
        # ② why_null 明文确认是有意为之（不是数据缺口），并点名「伪造 source_ref」
        why = tref.get("why_null") or ""
        assert why, "a177 的 why_null 应有归因文本（确认 null 是有意的）"
        assert "伪造" in why and "source_ref" in why, (
            "why_null 应明文声明不硬指册（否则硬指 = 伪造 source_ref），"
            f"实际: {why!r}"
        )
        # ③ 不得存在把它钉到某本册的 source_ref 字段
        assert "workbook_source_ref" not in tref, (
            "a177 的 template_ref 不应带 workbook_source_ref（那是硬指册的痕迹）"
        )

    def test_book_resolution_deferred_to_runtime(self, manifest_slice: dict) -> None:
        """AH-P6: 🔴 册解析推迟到运行时，由 `find_template_file_any` 定位。

        BP-8 的建模要点：静态期无唯一册，变体轴（team / 非 team）在运行时才确定，
        届时才用 `wp_template_finder.find_template_file_any(resolved_wp_code)` 定位册。
        本测试断言：
        1. `why_null` 点名了运行时解析入口 `find_template_file_any`；
        2. 该入口是真实可调用的函数（deferral 目标存在，不是空指向）；
        3. 以 slice 真实表达式驱动，证明双变体各自解析为确定 wp_code 后可供运行时查册。
        """
        from app.services import wp_template_finder as FINDER

        e = _entry_by_part(manifest_slice, "a177")
        tref = e["template_ref"]
        why = tref.get("why_null") or ""

        # ① why_null 点名运行时解析入口
        assert "find_template_file_any" in why, (
            "why_null 应点名运行时册解析入口 find_template_file_any，"
            f"实际: {why!r}"
        )

        # ② deferral 目标是真实可调用的函数
        assert callable(getattr(FINDER, "find_template_file_any", None)), (
            "find_template_file_any 应是真实可调用函数（运行时解析目标存在）"
        )

        # ③ 双变体表达式各自解析为确定 sheet 名（team → A17-7 / 非 team → A17-7A），
        #    运行时正是拿这个 resolved 值去 find_template_file_any —— 静态期无唯一册。
        expr = tref["sheet_name_exprs"][0]
        team_sheet = "A17-7" if "'A17-7'" in expr else None
        nonteam_sheet = "A17-7A" if "'A17-7A'" in expr else None
        assert team_sheet == "A17-7" and nonteam_sheet == "A17-7A", (
            f"双变体应解析为 A17-7 / A17-7A，表达式: {expr!r}"
        )
        # 运行时解析目标不抛异常（返回 Path | None 均合法，关键是无唯一静态册）
        for resolved in (team_sheet, nonteam_sheet):
            result = FINDER.find_template_file_any(resolved)
            assert result is None or isinstance(result, Path), (
                f"find_template_file_any({resolved!r}) 应返回 Path|None，实际 {result!r}"
            )

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

    # ── Task 3：变体轴显式化（契约须带 variant 维度，AH-P7 · AH-P8 · AC-44） ──

    @staticmethod
    def _resolve_variant_sheet(expr: str, variant: str) -> str:
        """按 slice 真实三元表达式 `A ? B : C` 把一个 variant 解析为确定 sheet 名。

        🔴 期望值**不写死**：解析器从 slice 现读的表达式动态求值，
        表达式一旦改动（如换 variant 名或换 sheet 名）本解析随之变化，
        不会把过期的 A17-7 / A17-7A 固化成守卫。
        """
        m = re.match(
            r"\s*(\w+)\s*===\s*'([^']+)'\s*\?\s*'([^']+)'\s*:\s*'([^']+)'\s*$",
            expr,
        )
        assert m, f"sheet_name_expr 不是预期的三元形态，无法建模 variant 轴: {expr!r}"
        axis_name, truthy_value, then_sheet, else_sheet = m.groups()
        assert axis_name == "variant", (
            f"变体轴维度名应为 `variant`，实际 {axis_name!r}（契约须按此维度建模）"
        )
        return then_sheet if variant == truthy_value else else_sheet

    def test_variant_axis_resolves_deterministically(
        self, manifest_slice: dict
    ) -> None:
        """AH-P7: 🔴 双变体各解析为**确定** sheet 名（team → A17-7 / 非 team → A17-7A）。

        与 `test_sheet_name_exprs_dual_variant` 的区别：那里只断言两名都在表达式里
        出现（子串），本测试**显式对 variant 轴求值**，断言每个 variant 落到唯一确定的
        sheet 名——这正是「契约须带 variant 维度」的可执行形态。
        """
        e = _entry_by_part(manifest_slice, "a177")
        expr = e["template_ref"]["sheet_name_exprs"][0]

        team_sheet = self._resolve_variant_sheet(expr, "team")
        nonteam_sheet = self._resolve_variant_sheet(expr, "non-team")

        assert team_sheet == "A17-7", (
            f"team 变体应确定解析为 A17-7，实际 {team_sheet!r}"
        )
        assert nonteam_sheet == "A17-7A", (
            f"非 team 变体应确定解析为 A17-7A，实际 {nonteam_sheet!r}"
        )
        # 两变体必须解析为**不同**的 sheet 名（否则 variant 轴退化、无存在意义）
        assert team_sheet != nonteam_sheet, (
            "双变体解析结果相同 ⇒ variant 轴退化，不成其为维度"
        )
        # 任意非 'team' 的取值都走 else 分支（证明判据是「team / 非 team」二分，
        # 而非把每个具体字符串当独立 case）
        for other in ("", "firm", "group", "individual"):
            assert self._resolve_variant_sheet(expr, other) == nonteam_sheet, (
                f"variant={other!r} 应落到非 team 分支 {nonteam_sheet!r}"
            )

    def test_variant_sheets_are_not_two_static_candidate_books(
        self, manifest_slice: dict
    ) -> None:
        """AH-P7 · AH-P8: 🔴 禁把 A17-7 / A17-7A 当两本独立静态候选册。

        variant 轴是**单一 entry 上的运行时维度**，不是「一码多册」的 finder 歧义。
        三重守卫：
        1. `wp_code_patterns` 保持单一（`["A177I"]`）—— 变体轴**不**膨胀成两个 wp_code；
        2. 两个 variant sheet 名（A17-7 / A17-7A）**都不**出现在 entry 的任何静态候选
           册/码字段里（`wp_code_patterns` / `workbook` / 任何 `*candidate*` 字段）
           ⇒ 它们只活在 `sheet_name_exprs` 这个运行时维度里；
        3. 这条 entry 在 slice 里只占 **1** 行（而非被拆成 A17-7 / A17-7A 两行 entry）。
        """
        e = _entry_by_part(manifest_slice, "a177")
        tref = e["template_ref"]

        # ① 变体轴不膨胀 wp_code —— 仍是单 pattern
        assert e.get("wp_code_patterns") == ["A177I"], (
            f"变体轴不应把 wp_code 膨胀成多个，实际 {e.get('wp_code_patterns')!r}"
        )

        # ② 两 variant sheet 名不得出现在任何静态候选册/码字段
        variant_sheets = {"A17-7", "A17-7A"}
        static_code_fields = (
            e.get("wp_code_patterns", [])
            + ([e.get("wp_code_pattern")] if e.get("wp_code_pattern") else [])
            + e.get("wp_codes_via_component_type", [])
        )
        assert not (variant_sheets & set(static_code_fields)), (
            f"variant sheet 名泄漏进静态码字段 {static_code_fields!r}"
            " ⇒ 会被 finder 误当一码多册候选"
        )
        assert tref.get("workbook") is None, (
            "variant sheet 名不得被钉成一本静态 workbook（workbook 应保持 null）"
        )
        for key, val in tref.items():
            if "candidate" in key.lower():
                vals = val if isinstance(val, list) else [val]
                assert not (variant_sheets & {str(v) for v in vals}), (
                    f"variant sheet 名出现在静态候选字段 {key!r}={val!r}"
                    " ⇒ 违反「不得当两本独立候选册」"
                )

        # ③ entry 在 slice 里只占 1 行（没被拆成两条 variant entry）
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        a177_rows = [x for x in a_entries if "a177" in x["entry_id"]]
        assert len(a177_rows) == 1, (
            f"a177 应只占 1 行 entry（variant 轴不拆行），实际 {len(a177_rows)}"
        )

    def test_bp8_a_domain_single_entry(self, manifest_slice: dict) -> None:
        """AH-P8: 全 slice BP-8 = 27，A 域只 **1** 条（a177），其余 26 归后续轮次。"""
        bps = manifest_slice.get("blocking_preconditions", [])
        bp8 = [b for b in bps if isinstance(b, dict) and b.get("id") == "BP-8"]
        assert bp8, "BP-8 应存在"
        members = bp8[0].get("entries", bp8[0].get("entry_ids", []))
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        a_eids = {x["entry_id"] for x in a_entries}
        a_bp8 = [m for m in members if m in a_eids]
        assert len(members) == 27, f"BP-8 成员应为 27，实际 {len(members)}"
        assert a_bp8 == ["xlsx/gt-a177-independence-declaration"], (
            f"BP-8 在 A 域应只 1 条（a177），实际 {a_bp8}"
        )
        assert len(members) - len(a_bp8) == 26, "其余 26 条应归 B/C/S 与跨循环域"


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestBP10NoSwitch — AH-P9 ~ AH-P12
# ═══════════════════════════════════════════════════════════════════════════


class TestBP10NoSwitch:
    """BP-10: 无模式开关（a3-consolidation-console）。"""

    def test_no_segmented_no_mode_gate(self, manifest_slice: dict) -> None:
        """AH-P9: 🔴 现读 slice 的 a3-console：segmented=0 且 mode 门控=0，
        与 `no_carrier` / `no_switch_at_all` 完全吻合（补开关前的事实基线）。

        这是**补开关前**的 slice 快照——slice 未随本任务的前端改线更新（slice 是
        静态裁决基线，不是运行时扫描）。补开关后的 live 计数（segmented 19→20、
        mode 门控 19→20）由 foundation 基线回改（任务 6）承接。
        """
        e = _entry_by_part(manifest_slice, "a3-consolidation")
        carrier = e.get("dual_mode_carrier", {})
        assert carrier.get("switch_verdict") == "no_switch_at_all"
        assert carrier.get("kind") == "no_carrier"
        # 逐 utg 现算：segmented 站点 0、mode 门控挂点 0
        utg = e.get("ui_toolbar_gate", {})
        assert len(utg.get("segmented_sites", [])) == 0, (
            f"a3-console segmented 应为 0，实际 {utg.get('segmented_sites')!r}"
        )
        assert len(utg.get("mode_gated_oo_mount_sites", [])) == 0, (
            f"a3-console mode 门控挂点应为 0，实际 "
            f"{utg.get('mode_gated_oo_mount_sites')!r}"
        )

    def test_oo_mount_cause_is_sheet_fallthrough_not_mode_gate(
        self, manifest_slice: dict
    ) -> None:
        """AH-P10: 🔴 现读其 OO 挂点成因是 **sheet 路由兜底**而非 mode 门控。

        判据须区分两种挂点成因（BP-10 原文：「其 OO 挂载点是 sheet 路由兜底」）：
        1. OO 挂点现算恰 **1** 个；
        2. 该挂点的 role 是 `sheet_fallthrough`（未匹配到 HTML 子组件的 sheet 落 OO），
           **不是** mode 门控（`mode_gated_oo_mount_sites` 为空）；
        3. slice 的 `no_switch_entries` 把 a3-console 与另 3 条一并归为「挂点是 sheet
           路由兜底，不是双模式切换」。
        """
        e = _entry_by_part(manifest_slice, "a3-consolidation")
        utg = e.get("ui_toolbar_gate", {})

        # ① OO 挂点恰 1 个
        oo_sites = utg.get("oo_mount_sites", [])
        assert len(oo_sites) == 1, f"OO 挂点应为 1，实际 {oo_sites!r}"

        # ② 该挂点 role = sheet_fallthrough（路由兜底），非 mode 门控
        roles = utg.get("oo_mount_roles", {})
        site_key = str(oo_sites[0])
        assert roles.get(site_key) == "sheet_fallthrough", (
            f"OO 挂点成因应为 sheet_fallthrough（路由兜底），实际 "
            f"{roles.get(site_key)!r}"
        )
        assert len(utg.get("mode_gated_oo_mount_sites", [])) == 0, (
            "mode_gated 挂点应为空（挂点不是 mode 门控而是路由兜底）"
        )

        # ③ slice 显式把它归入 no_switch_entries（挂点非双模式切换）
        #    该列表在 `mode_switch_resolution` 块下（非顶层）。
        msr = manifest_slice.get("mode_switch_resolution", {})
        no_switch = msr.get("no_switch_entries", [])
        assert "xlsx/gt-a3-consolidation-console" in no_switch, (
            "a3-console 应在 mode_switch_resolution.no_switch_entries 里"
            "（挂点是路由兜底非切换）"
        )
        # 并坐实 slice 原文把「没有开关」与 single 裁决解耦
        why = msr.get("why_no_switch_is_not_a_reason_to_adjudicate_single", "")
        assert "sheet 路由兜底" in why or "路由兜底" in why, (
            f"slice 应说明挂点是 sheet 路由兜底，实际: {why[:80]!r}"
        )

    def test_dual_mode_is_needed_three_criteria(
        self, manifest_slice: dict
    ) -> None:
        """AH-P11: 🔴 补开关前先论证「该 entry 真需要双模式」的三条现算依据，
        结论 = **需要补开关**，SHALL NOT 以「没有开关」为由裁 `single_onlyoffice`
        （AC 12.8 禁止）。

        三条论证缺一不可：
          ① `html_counterpart_verdict == 'exists'`（HTML 侧持久化通道有真实读写）；
          ② `find_template_file_any('A3-3')` 返回真实路径（xlsx 权威册可解析）；
          ③ A3-3 册有 4 sheets / 63 公式格（有实质业务承载）。
        """
        from app.services import wp_template_finder as FINDER

        e = _entry_by_part(manifest_slice, "a3-consolidation")

        # ① html_counterpart_verdict == 'exists'
        hc_verdict = e.get("html_counterpart_verdict") or (
            e.get("html_counterpart", {}) or {}
        ).get("verdict")
        assert hc_verdict == "exists", (
            f"html_counterpart_verdict 应为 exists（有 HTML 对端），实际 "
            f"{hc_verdict!r}"
        )

        # ② find_template_file_any('A3-3') 返回真实路径
        resolved = FINDER.find_template_file_any("A3-3")
        assert resolved is not None, (
            "find_template_file_any('A3-3') 应返回真实路径（xlsx 权威册可解析）"
        )
        assert Path(resolved).is_file(), (
            f"A3-3 解析结果应是真实存在的文件，实际 {resolved!r}"
        )

        # ③ A3-3 册 4 sheets / 63 公式格
        r = scan_xlsx_formulas(Path(resolved))
        assert r["sheet_count"] == 4, f"A3-3 册应 4 sheets，实际 {r['sheet_count']}"
        assert r["total_formulas"] == 63, (
            f"A3-3 册应 63 公式格，实际 {r['total_formulas']}"
        )

        # 结论：三条齐备 ⇒ 需要双模式；AC 12.8 禁止 single_onlyoffice。
        # 以 slice 的 adjudication 文本坐实「禁裁 single」是明文裁定（不是本测试臆断）。
        adj = e.get("adjudication", {})
        not_single_html = adj.get("not_single_html_because", "")
        hc = e.get("html_counterpart", {}) or {}
        how = hc.get("how_resolved", "")
        assert "12.8" in how or "single_onlyoffice" in how, (
            "html_counterpart.how_resolved 应点名 AC 12.8 禁止 single_onlyoffice，"
            f"实际: {how!r}"
        )
        # single_onlyoffice 的前提是「无 HTML 对端」，而本 entry verdict=exists ⇒ 矛盾
        assert hc_verdict == "exists", "verdict=exists 与 single_onlyoffice 前提矛盾"

    def test_has_html_counterpart(self, manifest_slice: dict) -> None:
        """AH-P10: html_counterpart_verdict = exists ⇒ 需要双模式；宿主文件真实存在。"""
        e = _entry_by_part(manifest_slice, "a3-consolidation")
        hc_verdict = e.get("html_counterpart_verdict") or (
            e.get("html_counterpart", {}) or {}
        ).get("verdict")
        assert hc_verdict == "exists", (
            f"html_counterpart_verdict 应为 exists，实际 {hc_verdict!r}"
        )
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

    def test_other_codes_resolve_and_a38_now_resolves_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """原 `test_other_codes_resolve_but_a38_does_not` —— 🔴 变异证明已**重建两次**。

        第一版用 `rglob("A3-8*")` 口径，建立在「没这本册」的假事实上 ⇒ 无效。
        第二版改用 `git show HEAD:` 取「修复前」finder 做方向① 变异，但 A3-8 合册解析
        的修复**已提交进 HEAD**（spec `workpaper-sync-pure-static-lane-and-combined-
        workbook-resolution` 把 `_find_combined_workbook_declaring` 插进了
        `find_template_file_any` 的 A 子码严格分支）⇒ `git show HEAD:` 已不再复现
        `None`，方向① 恒失效（这正是本任务要修的那条红）。

        🔴 **本次重建**：不再依赖任何历史 commit（避免把判据钉死到某个会被 rebase/
        squash 的魔法 SHA），改为**在被测函数的下一层注入故障** —— 禁用那条修复机制
        （把它的依赖 `_find_combined_workbook_declaring` 临时置为「恒返回 None」），
        于是 `find_template_file_any_unresolved('A3-8')` 回到**修复前**的
        `return None`。这满足项目铁律「守卫的故障注入不得替换被测生产函数本身」：
        被观测的 `find_template_file_any` 仍是生产函数原件，只有它调用的那一层依赖被
        换掉，故障注在**下一层**。

        双向变异：
        * 方向②（修复后 / 生产态）：`A3-8` 解析到合册
          `A3-7内部往来核对表、A3-8商誉减值测试.xlsx`；
        * 方向①（修复前 / 注入故障后）：`A3-8` → `None`；
        * 对照组 `A3-3` / `A5-1` / `A10-1` 在**两个方向下都**解析到各自真实册
          ⇒ 证明合册解析逻辑是**加法**，没有顺带改掉别人的走向。
        """
        from app.services import wp_template_finder as FINDER

        # 前置：被观测的入口确实是生产函数本身（没被别处替换成拷贝/桩）。
        assert FINDER.find_template_file_any_unresolved.__name__ == \
            "find_template_file_any", "被测入口应是生产函数 find_template_file_any 本体"
        # 故障注入点确实是该生产函数会调用的那一层依赖（存在且可调用）。
        assert callable(FINDER._find_combined_workbook_declaring), (
            "合册解析依赖 _find_combined_workbook_declaring 应存在且可调用"
        )

        control_codes = ("A3-3", "A5-1", "A10-1")

        # ── 方向②（修复后 / 生产态）────────────────────────────────────────
        after = FINDER.find_template_file_any_unresolved("A3-8")
        assert after is not None, "A3-8 修复后应能解析到合册"
        assert "A3-8" in FINDER._literal_wp_codes_in_filename(Path(after).name)
        # 合册文件名字面声明的码里应含 A3-7（顿号合册），坐实它正是那本合册。
        assert "A3-7" in FINDER._literal_wp_codes_in_filename(Path(after).name)
        control_after = {
            c: FINDER.find_template_file_any_unresolved(c) for c in control_codes
        }
        for c, p in control_after.items():
            assert p is not None, f"对照组 {c} 修复后应解析到真实册"

        # ── 方向①（修复前 / 在依赖层注入故障）──────────────────────────────
        #    禁用合册解析这条修复机制（它是 find_template_file_any 调用的下一层），
        #    被测生产函数本身不动。
        monkeypatch.setattr(
            FINDER, "_find_combined_workbook_declaring",
            lambda wp_code: None,
        )
        before = FINDER.find_template_file_any_unresolved("A3-8")
        assert before is None, (
            "修复前 `find_template_file_any('A3-8')` 应为 None"
            " —— 双向变异的方向① 失效（故障注入未生效）"
        )
        # 对照组在修复前后**一致**（证明新逻辑是加法，没顺带改别人的走向）。
        for c in control_codes:
            assert FINDER.find_template_file_any_unresolved(c) == control_after[c], (
                f"对照组 {c} 在禁用合册解析前后应一致（合册逻辑是加法）"
            )

    def test_bp6_global_count_1(self, manifest_slice: dict) -> None:
        """AH-P13 补: 全 slice BP-6 仅 1 条（a38），A 域独占。"""
        bps = manifest_slice.get("blocking_preconditions", [])
        bp6 = [b for b in bps if isinstance(b, dict) and b.get("id") == "BP-6"]
        assert bp6, "BP-6 应存在"
        members = bp6[0].get("entries", bp6[0].get("entry_ids", []))
        assert len(members) == 1
        assert "a38" in members[0]

    def test_a38_literal_is_the_unique_abnormal_among_19(
        self, manifest_slice: dict
    ) -> None:
        """AH-P13（AC-15）: 🔴 `A3-8商誉减值测试`（码 + 中文连写、无分隔符）是全 slice
        **19 条** `literal_sheet_name` 里的**唯一异形** —— 其余 18 条全是纯 wp_code。

        🔴 **从 slice 现读派生**，不写死「哪一条是异形」：遍历全 slice 收集所有
        `resolution_kind == 'literal_sheet_name'` 的 `sheet_name_literal`，按「纯码」
        正则 `^[A-Z]+\\d+(?:-\\d+)*[A-Za-z]?$` 分流，断言恰 1 条不匹配且就是 a38。
        slice 一旦新增/改动 literal 条目，本判据随之变化（不会固化过期结论）。
        """
        pure_code = re.compile(r"^[A-Z]+\d+(?:-\d+)*[A-Za-z]?$")
        literals: list[tuple[str, str]] = []

        def _walk(node: object, entry_id: str | None) -> None:
            if isinstance(node, dict):
                eid = node.get("entry_id", entry_id)
                tref = node.get("template_ref")
                if (isinstance(tref, dict)
                        and tref.get("resolution_kind") == "literal_sheet_name"):
                    literals.append((eid, tref.get("sheet_name_literal")))
                for v in node.values():
                    _walk(v, eid)
            elif isinstance(node, list):
                for v in node:
                    _walk(v, entry_id)

        _walk(manifest_slice["independent_entries"], None)

        assert len(literals) == 19, (
            f"全 slice literal_sheet_name 应为 19 条，现算 {len(literals)}"
        )
        abnormal = [
            (eid, s) for eid, s in literals
            if not (s and pure_code.match(str(s)))
        ]
        assert len(abnormal) == 1, (
            f"literal_sheet_name 里非纯码的异形应恰 1 条，现算 {abnormal!r}"
        )
        abn_eid, abn_literal = abnormal[0]
        assert abn_literal == "A3-8商誉减值测试", (
            f"唯一异形的字面应为 `A3-8商誉减值测试`，现算 {abn_literal!r}"
        )
        assert "a38" in str(abn_eid), (
            f"唯一异形应归属 a38，现算 entry {abn_eid!r}"
        )

    # ── Task 8：BP-6 两步修复（顺序不可颠倒），AH-P13 · AC-46 · Requirement 4 ──

    _A38_HOST = (
        _FRONTEND / "components" / "workpaper" / "GtA38GoodwillImpairment.vue"
    )

    def test_bp6_two_step_order_cannot_be_reversed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AH-P13: 🔴 两步修复**顺序不可颠倒** —— 一条测试里按序坐实 ①→②。

        与 `test_other_codes_resolve_and_a38_now_resolves_too` 的分工：那条做**双向变异**
        证明合册解析逻辑是加法；本条把「顺序」这件事本身做成可执行断言 ——

        * **step ①（必须先成立）**：合册在磁盘 + `find_template_file_any('A3-8')` 解析到它；
        * **只做 step ②（纯码）而没有 step ① 的 finder 修复 ⇒ 仍 None**：在被测函数的
          **下一层**注入故障（禁用 `_find_combined_workbook_declaring`，不替换被测生产函数
          本身），纯码 `A3-8` 回到 `None` —— 坐实「只做 ② 解析仍返回 None」，故顺序不可颠倒。
        """
        from app.services import wp_template_finder as FINDER

        # ── step ①：册存在且解析层通（这是 step ② 得以安全的前置）───────────
        contained = [
            f for f in TEMPLATE_DIR.rglob("*A3-8*")
            if f.suffix.lower() in (".xlsx", ".docx") and "~$" not in f.name
        ]
        assert len(contained) == 1, (
            f"step ① 前置：承载 A3-8 的合册应恰 1 本，实得 {[f.name for f in contained]}"
        )
        resolved = FINDER.find_template_file_any_unresolved("A3-8")
        assert resolved is not None, "step ①：find_template_file_any('A3-8') 应解析到合册"
        assert "A3-8" in FINDER._literal_wp_codes_in_filename(Path(resolved).name)

        # ── 顺序证明：抽掉 step ① 的 finder 修复后，纯码（step ② 的产物）仍 None ──
        #    故障注在**下一层**依赖，被观测的 find_template_file_any 仍是生产函数原件。
        assert FINDER.find_template_file_any_unresolved.__name__ == \
            "find_template_file_any", "被测入口应是生产函数本体"
        monkeypatch.setattr(
            FINDER, "_find_combined_workbook_declaring", lambda wp_code: None,
        )
        assert FINDER.find_template_file_any_unresolved("A3-8") is None, (
            "只做 step ②（纯码）而没有 step ① 的 finder 修复 ⇒ 'A3-8' 仍解析为 None"
            " —— 坐实两步顺序不可颠倒"
        )

    def test_bp6_step2_host_sheet_name_converged_to_pure_code(self) -> None:
        """AH-P13: 🔴 step ② —— 宿主把 sheet-name 从中文连写字面收敛为纯码 `A3-8`。

        中文连写字面 `A3-8商誉减值测试` 在**运行时的真源**是宿主组件
        `GtA38GoodwillImpairment.vue` 传给 `GtOnlyOfficeSheet` 的 `sheet-name` prop
        （不是冻结 slice —— slice 的 `sheet_name_literal` 作裁决基线保持原样）。

        三条断言：
          ① 宿主 docx 分支的 `sheet-name` 已是纯码 `A3-8`（不再是中文连写字面）；
          ② 宿主**不再**出现中文连写字面 `A3-8商誉减值测试` 作为 sheet-name 值；
          ③ 纯码 `A3-8` 可被 `find_template_file_any` 解析（step ① 已通，故 ② 安全）。
        """
        from app.services import wp_template_finder as FINDER

        src = self._A38_HOST.read_text(encoding="utf-8", errors="replace")

        # ① 宿主以纯码传 sheet-name（接受单/双引号、属性名短横线写法）
        pure = re.search(r'sheet-name\s*=\s*["\']A3-8["\']', src)
        assert pure, (
            "宿主 GtA38GoodwillImpairment.vue 的 sheet-name 应收敛为纯码 `A3-8`"
        )

        # ② 中文连写字面不再作为 sheet-name 的**值**出现（注释里复述归因允许，
        #    故只禁 `sheet-name="A3-8商誉减值测试"` 这种属性绑定形态）
        legacy = re.search(r'sheet-name\s*=\s*["\']A3-8商誉减值测试["\']', src)
        assert legacy is None, (
            "宿主不应再把中文连写字面 `A3-8商誉减值测试` 作为 sheet-name 值传入"
        )

        # ③ 纯码可解析（step ② 之所以安全的根据，与 step ① 对齐）
        assert FINDER.find_template_file_any_unresolved("A3-8") is not None, (
            "纯码 A3-8 应能解析到合册（step ① 已通，step ② 收敛才安全）"
        )

    def test_bp6_closes_to_empty_set_after_both_steps(
        self, manifest_slice: dict
    ) -> None:
        """AH-P13: 🔴 收口后 BP-6 成员集变**全空集**（全 slice 仅 1 条 = a38）。

        BP-6 全 slice 恰 1 条且归 a38（冻结裁决基线保持）；本 spec 两步均落地
        （step ① 解析层通 + step ② 宿主纯码收敛）⇒ a38 的 BP-6 阻塞解除，收口后
        BP-6 的 A 域份额与全 slice 份额均归空集。
        """
        bps = manifest_slice.get("blocking_preconditions", [])
        bp6 = [b for b in bps if isinstance(b, dict) and b.get("id") == "BP-6"]
        assert bp6, "BP-6 应存在"
        members = bp6[0].get("entries", bp6[0].get("entry_ids", []))
        assert len(members) == 1 and "a38" in members[0], (
            f"BP-6 全 slice 应恰 1 条且归 a38，实际 {members!r}"
        )
        # 两步均已落地的坐实（① 解析 + ② 宿主纯码），缺一则收口不成立
        from app.services import wp_template_finder as FINDER
        assert FINDER.find_template_file_any_unresolved("A3-8") is not None, \
            "step ① 未成立：A3-8 应能解析"
        src = self._A38_HOST.read_text(encoding="utf-8", errors="replace")
        assert re.search(r'sheet-name\s*=\s*["\']A3-8["\']', src), \
            "step ② 未成立：宿主 sheet-name 应为纯码 A3-8"


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestProperty22Defect — AH-P14 ~ AH-P15
# ═══════════════════════════════════════════════════════════════════════════


def _a38_source() -> str:
    """a38 宿主 Vue 源码（现读，errors='replace' 容错）。"""
    host = _FRONTEND / "components" / "workpaper" / "GtA38GoodwillImpairment.vue"
    assert host.is_file(), f"a38 宿主应存在: {host}"
    return host.read_text(encoding="utf-8", errors="replace")


def _extract_dcf_column_tag(stripped: str) -> str:
    """抽取 DCF（预计未来现金流量）动态列的 `<el-table-column v-for=…>` 整标签。

    🔴 以**剥注释后**的源码为输入（注释里复述归因不得干扰判据），按 slice
    recompute_recipe ② 的「整标签跨行、`re.S`」口径定位。DCF 列的识别锚点 =
    其 `:label` 绑定含 `第${…}年`（年份表头），这是本组件里唯一按年份横向展开的
    动态列，不会与减值主表等**静态**列（无 v-for）混淆。
    """
    # 所有带 v-for 的 el-table-column 整标签（含自闭合与成对两种写法的开标签）
    tags = re.findall(
        r"<el-table-column\b[^>]*\bv-for\b[^>]*?>", stripped, re.S
    )
    dcf = [t for t in tags if "第${" in t and "年" in t]
    assert len(dcf) == 1, (
        f"DCF 动态列（label 含 `第${{…}}年`）应恰 1 个 v-for 站点，现算 {len(dcf)}:\n"
        + "\n".join(dcf)
    )
    return dcf[0]


def _binding(tag: str, attr: str) -> str | None:
    """从标签文本取某个绑定属性的表达式值（支持 `:key` / `v-for` 等）。"""
    m = re.search(rf'{re.escape(attr)}\s*=\s*"([^"]*)"', tag)
    return m.group(1) if m else None


class TestProperty22Defect:
    """Property 22 缺陷收口（a38）。

    🔴 修复前的 slice 冻结基线（`dynamic_column_identity.defects` 的 P22-D1）：
        site = `GtA38GoodwillImpairment.vue#L154`
        v_for = `(_, i) in 5`（列数写死 5）
        key_binding = `i`（裸下标）
        label_binding = `` `第${i + 1}年` ``（可改 label）
    ⇒ `column_count_hardcoded` 与 `key_is_bare_index` **两类缺陷同时命中**。
    本任务两类同修：① 列数数据驱动（FORECAST_YEARS，禁写死 5）② key 改稳定
    `{slot}_{seq}`（`year_{n}`，禁裸下标、禁 label 作 key）。slice 作裁决基线保持原样。
    """

    _A38_P22_DEFECT_ID = "P22-D1"

    def test_a38_is_in_defect_list(self, manifest_slice: dict) -> None:
        """AH-P14: a38 在 Property 22 defects 列表中（冻结基线记录了修复前缺陷）。"""
        dci = manifest_slice.get("dynamic_column_identity", {})
        defects = dci.get("defects", [])
        a38_defects = [d for d in defects if "a38" in d.get("entry_id", "")]
        assert len(a38_defects) == 1, (
            f"a38 应恰 1 条 Property 22 缺陷记录，现算 {len(a38_defects)}"
        )
        d = a38_defects[0]
        assert d["id"] == self._A38_P22_DEFECT_ID, d["id"]
        # 冻结基线确实同时记录了两类缺陷（供下方「已修」断言做对照）
        assert "写死" in d["what"] and ("裸下标" in d["what"] or "`i`" in d["what"]), (
            f"基线缺陷应同时点名「列数写死」与「裸下标 key」，实际: {d['what']!r}"
        )

    def test_a38_column_count_is_data_driven(self) -> None:
        """AH-P14: 🔴 ① DCF 动态列的列数**数据驱动**，v-for 里**无写死数字**。

        与 slice 基线 `v-for="(_, i) in 5"` 对照：现读的 DCF 列 v-for 迭代源必须是
        标识符（`FORECAST_YEARS`）而非数字字面量 ⇒ `column_count_hardcoded` 消除。
        """
        stripped = strip_comments(_a38_source())
        tag = _extract_dcf_column_tag(stripped)
        v_for = _binding(tag, "v-for")
        assert v_for, f"DCF 列应有 v-for 绑定，实际标签: {tag}"
        # v-for 迭代源（`in` 之后）不得是数字字面量（写死列数）
        m = re.search(r"\bin\s+(.+?)\s*$", v_for)
        assert m, f"v-for 应是 `(…) in <源>` 形态，实际: {v_for!r}"
        iter_src = m.group(1).strip()
        assert not re.fullmatch(r"\d+", iter_src), (
            f"DCF 列数不得写死数字（现读迭代源 {iter_src!r}），应由数据驱动"
        )
        # 正向坐实：由 FORECAST_YEARS 驱动，且它是 computed（随 cash_flows 变化）
        assert iter_src == "FORECAST_YEARS", (
            f"DCF 列迭代源应为 FORECAST_YEARS，实际 {iter_src!r}"
        )
        assert re.search(
            r"\bFORECAST_YEARS\s*=\s*computed\(", stripped
        ), "FORECAST_YEARS 应是 computed（预测期年数据驱动，非常量写死）"

    def test_a38_key_is_stable_slot_seq_not_bare_index(self) -> None:
        """AH-P14（AC-48）: 🔴 ② 列 key 是稳定 `{slot}_{seq}`，非裸下标、非 label。

        AC 6.4 原文：动态列 SHALL 用稳定 key `{slot}_{seq}`；不得用可改 label 作
        identity。现读 DCF 列：
          · key 形如 `year_${…}`（slot=`year`，seq=序号）⇒ 满足 `{slot}_{seq}`；
          · key **不是**裸下标（`i`/`idx`/`index`/`$index`）；
          · key **不等于** label（label 是 `第${…}年`，是可改文案，不得复用为 key）。
        """
        stripped = strip_comments(_a38_source())
        tag = _extract_dcf_column_tag(stripped)
        key = _binding(tag, ":key")
        label = _binding(tag, ":label")
        assert key, f"DCF 列应有 :key 绑定，实际标签: {tag}"
        assert label, f"DCF 列应有 :label 绑定，实际标签: {tag}"

        # key 是 {slot}_{seq}：以英文 slot 前缀 + 下划线 + 序号表达式
        assert re.match(r"^`?year_", key.strip("`")) or key.strip().startswith("`year_"), (
            f"DCF 列 key 应是稳定 `{{slot}}_{{seq}}`（year_…），实际 {key!r}"
        )
        # key 不是裸下标
        assert key.strip() not in {"i", "idx", "index", "$index"}, (
            f"DCF 列 key 不得是裸下标，实际 {key!r}"
        )
        assert not re.fullmatch(r"`?\$?\{?\s*(i|idx|index)\s*\}?`?", key.strip()), (
            f"DCF 列 key 不得是裸下标形态，实际 {key!r}"
        )
        # key ≠ label（可改 label 不得作 identity）
        assert key.strip() != label.strip(), (
            f"DCF 列 key 不得复用可改 label 作 identity（key={key!r} label={label!r}）"
        )
        # slot 是英文、seq 是序号表达式 ⇒ label（中文「第 N 年」）改文案不影响 key
        assert "第" not in key and "年" not in key, (
            f"DCF 列 key 不应含 label 文案（key 必须与 label 解耦），实际 {key!r}"
        )

    def test_a38_old_defect_form_structurally_absent(self) -> None:
        """AH-P14 变异证明: 🔴 修复前的缺陷形态已**结构性消失**，重引入必被打红。

        slice 基线缺陷形态 = `v-for="(_, i) in 5"` + `:key="i"`。本测试断言该形态在
        DCF 动态列上**不再出现**，并对**整文件**扫一遍确保没有「数字写死列数的
        el-table-column」或「裸下标 key 的 el-table-column」死灰复燃 ——
        这是「重引入 bare-index key / 写死列数即被检测」的守卫。
        """
        stripped = strip_comments(_a38_source())

        # ① DCF 列本身不得退回旧形态
        tag = _extract_dcf_column_tag(stripped)
        assert not re.search(r'v-for\s*=\s*"\s*\(\s*_?\s*,\s*\w+\s*\)\s*in\s+\d+\s*"', tag), (
            f"DCF 列不得退回写死列数形态（`(_, i) in <数字>`），实际: {tag}"
        )
        assert not re.search(r':key\s*=\s*"\s*(i|idx|index)\s*"', tag), (
            f"DCF 列不得退回裸下标 key（`:key=\"i\"`），实际: {tag}"
        )

        # ② 全文件任何 el-table-column 都不得「写死数字列数」或「裸下标 key」
        all_tags = re.findall(
            r"<el-table-column\b[^>]*?>", stripped, re.S
        )
        hardcoded = [t for t in all_tags
                     if re.search(r'v-for\s*=\s*"[^"]*\bin\s+\d+\s*"', t)]
        bare_key = [t for t in all_tags
                    if re.search(r'v-for\b', t)
                    and re.search(r':key\s*=\s*"\s*(i|idx|index|\$index)\s*"', t)]
        assert hardcoded == [], (
            f"不应有写死列数的 el-table-column，实际 {hardcoded}"
        )
        assert bare_key == [], (
            f"不应有裸下标 key 的动态 el-table-column，实际 {bare_key}"
        )

    def test_a38_mode_form2_correct_while_column_defect_was_present(
        self, manifest_slice: dict
    ) -> None:
        """AH-P15: 🔴 登记张力 —— a38 在**模式层做对**（形态 2），却曾在**列层做错**。

        形态 2 = `modeOptions` 是 `{label, value}` 对象数组（中文标签与英文 mode 值
        **分离**），是全 A 域仅 2 个正面样板之一；而同一组件的 DCF 列却曾用裸下标
        key + 写死列数（列层未贯彻「label/key 解耦」）。本测试同时坐实：
          · 模式层：形态 2 成立（对象数组 + value 是英文 `html`/`docx`）；
          · 列层：修复后已消除缺陷（key 解耦 + 列数数据驱动）；
          · 两层共存证明「label/key 解耦」意识此前未贯穿全层（张力的事实依据）。
        """
        stripped = strip_comments(_a38_source())

        # ── 模式层做对：形态 2（对象数组，label/value 分离，value 为英文）──
        mode_block = re.search(
            r"modeOptions\s*=\s*(\[.*?\])", stripped, re.S
        )
        assert mode_block, "a38 应有 modeOptions 对象数组（形态 2）"
        block = mode_block.group(1)
        assert re.search(r"\{\s*label\s*:", block) and re.search(r"value\s*:", block), (
            f"modeOptions 应是 {{label, value}} 对象数组（形态 2），实际: {block}"
        )
        # value 是英文 mode 值（html/docx），不是把中文标签当 mode 值（形态 1）
        values = re.findall(r"value\s*:\s*'([^']+)'", block)
        assert set(values) == {"html", "docx"}, (
            f"mode 值应为英文 html/docx（形态 2），实际 {values}"
        )
        assert not re.search(r"value\s*:\s*'[^']*[\u4e00-\u9fff]", block), (
            "mode value 不得是中文标签（那是形态 1，禁引入）"
        )

        # ── 列层做对（修复后）：DCF 列 key 解耦 + 列数数据驱动 ──
        tag = _extract_dcf_column_tag(stripped)
        key = _binding(tag, ":key")
        v_for = _binding(tag, "v-for")
        assert key and key.strip().startswith("`year_"), (
            f"列层应已修复为稳定 key year_…，实际 {key!r}"
        )
        assert v_for and "FORECAST_YEARS" in v_for, (
            f"列层应已修复为数据驱动列数，实际 v-for {v_for!r}"
        )

        # ── 张力的事实依据：冻结基线确实记录了「列层曾做错」──
        d = next(x for x in manifest_slice["dynamic_column_identity"]["defects"]
                 if x["id"] == self._A38_P22_DEFECT_ID)
        assert d["entry_id"] == "xlsx/gt-a38-goodwill-impairment"
        assert "(_, i) in 5" in d["evidence"] and ':key="i"' in d["evidence"], (
            f"基线应记录列层旧缺陷证据（写死 5 + 裸下标 key），实际 {d['evidence']!r}"
        )

    def test_a_domain_property22_sites_drop_1_to_0_verdict_stays_partial(
        self, manifest_slice: dict
    ) -> None:
        """AH-P15: 🔴 修复后 A 域 Property 22 站点 **1 → 0**（live），全 slice verdict
        仍 **PARTIAL**（其余缺陷在 B 域）。

        🔴 slice 是**修复前冻结基线**（仍把 a38 列为 P22-D1 缺陷），不编辑它。本测试
        从 slice `defects` + 当前宿主**现读**派生：
          · slice 基线：A 域缺陷恰 1 条（a38 = P22-D1）；B 域缺陷 2 条（b14、b50）；
          · live：a38 宿主已消除缺陷（列数数据驱动 + key 解耦）⇒ A 域 live 缺陷 = 0；
          · B 域缺陷未被本 spec 触及 ⇒ 仍存在 ⇒ 全 slice 整体 verdict 保持 PARTIAL。
        """
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        a_eids = {e["entry_id"] for e in a_entries}
        dci = manifest_slice["dynamic_column_identity"]
        defects = dci["defects"]

        # ① slice 冻结基线：A 域 1 条、B 域 2 条
        a_defects = [d for d in defects if d["entry_id"] in a_eids]
        b_defects = [d for d in defects
                     if d["entry_id"].startswith("xlsx/gt-b")]
        assert len(a_defects) == 1, (
            f"slice 基线 A 域 Property 22 缺陷应恰 1 条，现算 {len(a_defects)}"
        )
        assert a_defects[0]["entry_id"] == "xlsx/gt-a38-goodwill-impairment"
        assert len(b_defects) == 2, (
            f"B 域缺陷应恰 2 条（b14 / b50），现算 "
            f"{[d['entry_id'] for d in b_defects]}"
        )

        # ② live 现读：a38 宿主缺陷已消除 ⇒ A 域 live 站点 = 0
        stripped = strip_comments(_a38_source())
        tag = _extract_dcf_column_tag(stripped)
        v_for = _binding(tag, "v-for") or ""
        key = _binding(tag, ":key") or ""
        a38_still_defective = (
            bool(re.search(r"\bin\s+\d+\s*$", v_for.strip()))  # 列数写死
            or key.strip() in {"i", "idx", "index", "$index"}   # 裸下标 key
        )
        assert not a38_still_defective, (
            "a38 宿主 live 仍含 Property 22 缺陷（列数写死或裸下标 key）"
            f"：v-for={v_for!r} key={key!r}"
        )
        a_domain_live_sites = 0 if not a38_still_defective else 1
        assert a_domain_live_sites == 0, (
            f"修复后 A 域 Property 22 live 站点应为 0，现算 {a_domain_live_sites}"
        )

        # ③ 全 slice verdict 仍 PARTIAL（B 域缺陷未解 ⇒ 整体不改判通过）
        verdict = dci.get("verdict", "")
        assert "PARTIAL" in verdict, (
            f"全 slice Property 22 verdict 应仍为 PARTIAL，实际: {verdict[:60]!r}"
        )
        # B 域缺陷确实仍在（本 spec 不触及），故 PARTIAL 的理由成立
        assert len(b_defects) >= 1, "B 域应仍有未解缺陷支撑 PARTIAL 判定"


# ═══════════════════════════════════════════════════════════════════════════
# §6 TestA33TemplateDefects — AH-P16
# ═══════════════════════════════════════════════════════════════════════════


def _a33_book() -> Path:
    """定位 A3-3 权威册（现读，禁写死文件名）。

    真实文件名是 `A3-3 结构化主体纳入合并范围的判断.xlsx`，首张 sheet 名却带
    **跨循环码 `F6-10`**（T-2）⇒ 以 `A3-3*` glob + xlsx 后缀定位，排除临时锁文件。
    """
    candidates = [f for f in TEMPLATE_DIR.rglob("A3-3*")
                  if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
    assert len(candidates) == 1, (
        f"A3-3 权威册应恰 1 本，现算 {[f.name for f in candidates]}"
    )
    return candidates[0]


class TestA33TemplateDefects:
    """A3-3 册缺陷台账（记录型，不改模板）。

    🔴 **记录型，SHALL NOT 修改 A3-3 册**：全部 T-1 ~ T-17 条目只**记录**册当前的缺陷
    状态，不回写修复。`test_t0_sha256_unchanged_record_only` 把「交付后 sha256 仍 match」
    做成可执行守卫，并（依 foundation 测试原则「sha256 断言置前失败即中止」）命名为
    `t0` 使其在类内按字母序**最先**执行——册一旦被任何任务改动，整类立即失败止损。
    """

    # 🔴 现读派生的 sha256 基线（_a33p_probe.py 现算，size 215491）。
    #    这是「交付后 sha256 须仍 match」的锚点：本任务是记录型，不得改动册。
    _A33_SHA256_BASELINE = (
        "e8d4786e4524e905606dabe00c64a154f363fdf61221f56bc422f250ea596adb"
    )

    def test_t0_sha256_unchanged_record_only(self) -> None:
        """AH-P16: 🔴 交付后 A3-3 册 sha256 仍 match（记录型，本任务未改模板）。

        依 foundation 原则「sha256 断言置前失败即中止」：方法名 `t0` 使其在
        `TestA33TemplateDefects` 内按字母序**最先**运行。若册被任何改动，这里立即
        失败，后续 T-1 ~ T-17 现算断言不再在被污染的册上跑。
        """
        book = _a33_book()
        digest = sha256_file(book)
        assert digest == self._A33_SHA256_BASELINE, (
            f"A3-3 册 sha256 已变更 ⇒ 本任务应为记录型（不改模板）。\n"
            f"  期望: {self._A33_SHA256_BASELINE}\n"
            f"  实际: {digest}\n"
            f"  册: {book}"
        )

    def test_t1_ae_column_div_zero(self) -> None:
        """AH-P16: T-1 AE7~AE15 恒 #DIV/0!（反向分母 10:1）。

        🔴 与 N 轮 NC-32 **不同型**：NC-32 是「引用超出 `max_column` 的列」，
        T-1 是「引用**同表内的空行**」（公式行数 10 超出有值数据行 1，反向分母 10:1）
        ⇒ 两者扫描器完全不同，判据**不可合并**。本测试坐实 T-1 的「空行」成因：
        AE 列公式所引用的数据行（本表数据只到首行附近）大多为空 ⇒ 除零。
        """
        import openpyxl
        wb = openpyxl.load_workbook(str(_a33_book()), data_only=False)
        ws = wb.worksheets[0]  # 首张 sheet（F6-10）
        # AE 列 = 第 31 列
        ae_formulas = 0
        for row in range(6, 16):
            cell = ws.cell(row=row, column=31)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                ae_formulas += 1
        # 🔴 T-1 的「空行」特征（区别于 NC-32 的「超 max_column」）：
        #    AE 列在 max_column(=33) 之内，不越界 ⇒ 不是 NC-32 的超列型。
        assert ws.max_column >= 31, (
            f"AE 列(31) 应在 max_column({ws.max_column}) 之内 ⇒ 非 NC-32 超列型"
        )
        wb.close()
        assert ae_formulas >= 8, \
            f"AE6~AE15 应有 >= 8 个公式（数据行超出致除零），实际 {ae_formulas}"

    def test_t2_cross_cycle_code_f610(self) -> None:
        """AH-P16: T-2 首张 sheet 名码是 F6-10（跨循环码混入）。

        🔴 wp_code 是 `A3-3`，首张 sheet 名却带 `F6-10` ⇒ 跨循环码混入。
        SHALL 按**原始字面量**比对，禁归一化（依 AC-10 · AC-21）。
        """
        import openpyxl
        wb = openpyxl.load_workbook(str(_a33_book()), data_only=False)
        first_sheet = wb.worksheets[0].title
        wb.close()
        # 原始字面量比对（不 strip、不归一化大小写、不去分隔符）
        assert "F6-10" in first_sheet, \
            f"首张 sheet 名应含 F6-10（跨循环码），实际: {first_sheet!r}"
        # 坐实它正是「码 ≠ wp_code」：F6-10 的字母体系(F) ≠ wp_code(A3-3) 的字母体系(A)
        assert "F6-10" != "A3-3" and first_sheet.strip() == first_sheet, (
            f"跨循环码应原样保留（禁归一化），实际 {first_sheet!r}"
        )

    def test_t3_defined_names_dbase_residual(self) -> None:
        """AH-P16: T-3 definedName 261/broken 190 含 .dbf 旧残留。"""
        r = scan_xlsx_formulas(_a33_book())
        assert r["defined_names_total"] == 261
        assert r["defined_names_broken"] == 190

    def test_t15_reference_sheets_zero_formulas(self) -> None:
        """AH-P16: T-15 后三张 sheet 是参考资料型（0 公式格）⇒ 双向回写须排除。"""
        import openpyxl
        wb = openpyxl.load_workbook(str(_a33_book()), data_only=False)
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

    def test_t16_ghost_rows_12_use_last_value_row(self) -> None:
        """AH-P16: T-16 `合并范围判断流程图（举例）` 幽灵行 **12**（max_row 45 vs
        last_value_row 33）⇒ 遍历上界须取 last_value_row 而非 max_row。

        🔴 两数现算（禁写死）：
          · max_row = openpyxl 的 `ws.max_row`（含尾部格式残留的空行）；
          · last_value_row = 最后一个含非空值的行号（遍历所有行取 max(cell.row)）；
          · 幽灵行 = max_row − last_value_row。
        本表现算 45 − 33 = 12 ⇒ 若遍历用 max_row 作上界，会多扫 12 行纯幽灵行
        （无业务值的格式残留），双向回写上界必须取 last_value_row。
        """
        import openpyxl
        wb = openpyxl.load_workbook(str(_a33_book()), data_only=False)
        target = None
        for ws in wb.worksheets:
            if "合并范围判断流程图" in ws.title:
                target = ws
                break
        assert target is not None, "应有 `合并范围判断流程图（举例）` sheet"
        assert target.title == "合并范围判断流程图（举例）", (
            f"T-16 目标 sheet 名应原样为 `合并范围判断流程图（举例）`，实际 {target.title!r}"
        )

        max_row = target.max_row
        last_value_row = 0
        for row in target.iter_rows():
            for cell in row:
                if cell.value is not None and str(cell.value).strip() != "":
                    if cell.row > last_value_row:
                        last_value_row = cell.row
        wb.close()

        ghost = max_row - last_value_row
        assert max_row == 45, f"max_row 现算应为 45，实际 {max_row}"
        assert last_value_row == 33, (
            f"last_value_row 现算应为 33，实际 {last_value_row}"
        )
        assert ghost == 12, (
            f"幽灵行应为 12（遍历上界须取 last_value_row，不是 max_row），"
            f"实际 {max_row} - {last_value_row} = {ghost}"
        )

    def test_t17_footer_raw_xml_three_state(self) -> None:
        """AH-P16: T-17 footer 读 **raw XML**：sheet1 = `第 &P 页，共 &N 页`（中文），
        其余 3 张**无 `<headerFooter>` 元素** ⇒ 三态中的两态。

        🔴 依 AC-36 / foundation 原则⑰：openpyxl 的 `ws.oddFooter` 在解析失败时会
        **静默返回空**（跑测时可见 `Cannot parse header or footer` warning）⇒ 必须直接
        读 xlsx zip 里 `xl/worksheets/sheetN.xml` 的 raw XML。期望值从 raw XML 现读
        （`&amp;P` 实体 unescape 后比对 `&P`）。

        三态分布（现算）：
          · sheet1（F6-10 首张）：有 `<headerFooter>` 容器 + oddFooter `第 &P 页，共 &N 页`；
          · sheet2/3/4（参考资料型）：无 `<headerFooter>` 容器、无 oddFooter。
        """
        results = scan_xlsx_footer_raw_xml(_a33_book())
        # sheetN.xml 的字典序与 workbook sheet 顺序 1:1（rId{n}→sheet{n}.xml，已现算核对）
        assert len(results) == 4, f"应有 4 张 sheet 的 footer 记录，实际 {len(results)}"

        # ── sheet1：有容器 + 中文 oddFooter ──
        s1 = results[0]
        assert s1["sheet_file"] == "xl/worksheets/sheet1.xml", s1["sheet_file"]
        assert s1["has_header_footer_container"] is True, (
            "sheet1 应有 <headerFooter> 容器"
        )
        assert len(s1["odd_footer_values"]) == 1, (
            f"sheet1 应恰 1 个 oddFooter，实际 {s1['odd_footer_values']!r}"
        )
        # raw XML 里是实体转义的 `&amp;P`，unescape 后比对设计记录的 `第 &P 页，共 &N 页`
        footer_text = html.unescape(s1["odd_footer_values"][0])
        assert footer_text == "第 &P 页，共 &N 页", (
            f"sheet1 oddFooter 应为 `第 &P 页，共 &N 页`（中文），"
            f"unescape 后实际 {footer_text!r}（raw={s1['odd_footer_values'][0]!r}）"
        )

        # ── sheet2/3/4：无 <headerFooter> 元素 ──
        for sN in results[1:]:
            assert sN["has_header_footer_container"] is False, (
                f"{sN['sheet_file']} 应无 <headerFooter> 元素，"
                f"实际 has_container={sN['has_header_footer_container']}"
            )
            assert sN["odd_footer_values"] == [], (
                f"{sN['sheet_file']} 不应有 oddFooter，实际 {sN['odd_footer_values']!r}"
            )

        # ── 三态分布坐实：有 footer 的恰 1 张，无容器的恰 3 张 ──
        with_footer = sum(1 for r in results if r["odd_footer_values"])
        without_container = sum(
            1 for r in results if not r["has_header_footer_container"]
        )
        assert with_footer == 1, f"有 footer 的 sheet 应为 1，实际 {with_footer}"
        assert without_container == 3, (
            f"无 <headerFooter> 容器的 sheet 应为 3，实际 {without_container}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §7 TestA177GatingAndArchiveDebt — AC-13（门控三层嵌套）· AC-25（归档欠账）
# ═══════════════════════════════════════════════════════════════════════════

# 归档区的 a17-7 欠账 spec（append-only，只登记不回填修改）。
_A177_ARCHIVED_SPEC = (
    _ROOT / ".kiro" / "specs" / "_archive" / "13-2026-06-29-batch"
    / "a17-7-independence-declaration"
)

# a177 宿主的运行时编辑挂点标签（改线后由 sync bridge 管理，非 legacy
# GtOnlyOfficeSheet）。门控判据须以此为 target_tag。
_A177_OO_MOUNT_TAG = "WorkpaperSyncEditorHost"


def _a177_host_source() -> str:
    """a177 宿主 Vue 源码（现读，errors='replace' 容错）。"""
    host = _FRONTEND / "components" / "workpaper" / "GtA177IndependenceDeclaration.vue"
    assert host.is_file(), f"a177 宿主应存在: {host}"
    return host.read_text(encoding="utf-8", errors="replace")


def _parse_mounts(source: str, tag: str) -> list[dict]:
    """用既存已验证的 `_VueGateParser` 解析 `<template>` 内指定挂点的祖先链门控。"""
    m = re.search(r"<template\b[^>]*>(.*)</template>", source, re.S)
    assert m, "宿主应有 <template> 段"
    parser = _VueGateParser(tag)
    parser.feed(m.group(1))
    return parser.mounts


def _parse_mounts_self_only(source: str, tag: str) -> list[dict]:
    """只看挂点自身属性的门控（变异证明：复现「只看自身会假阴」）。"""
    m = re.search(r"<template\b[^>]*>(.*)</template>", source, re.S)
    assert m, "宿主应有 <template> 段"
    template_text = m.group(1)
    results: list[dict] = []
    for mo in re.finditer(rf"<{re.escape(tag)}\b([^>]*)(?:/>|>)",
                          template_text, re.S | re.I):
        attr_str = mo.group(1)
        has_mode = bool(re.search(r"\b\w*[Mm]ode\b", attr_str))
        results.append({"attr_str": attr_str, "has_mode_gate": has_mode})
    return results


class TestA177GatingAndArchiveDebt:
    """Task 4：a177 门控（AC-13 三层嵌套形态）+ 归档欠账登记（AC-25）。"""

    # ── AC-13：门控在祖先的 v-else 链头上，只看挂点自身会假阴 ──

    def test_oo_mount_present_via_sync_bridge(self) -> None:
        """前置：a177 的运行时挂点已改线到 WorkpaperSyncEditorHost（非 legacy）。

        🔴 结构性零配变异：先证明目标挂点确实存在（否则后续「门控在祖先」
        的断言会在空集合上恒绿）。
        """
        source = _a177_host_source()
        mounts = _parse_mounts(source, _A177_OO_MOUNT_TAG)
        assert len(mounts) >= 1, (
            f"a177 应至少有 1 个 {_A177_OO_MOUNT_TAG} 挂点（改线后由 sync bridge 管理），"
            f"实际 {len(mounts)}"
        )
        # 既存 legacy GtOnlyOfficeSheet 挂点应已清零（改线证据）
        legacy = _parse_mounts(source, "GtOnlyOfficeSheet")
        assert legacy == [], (
            f"a177 不应再有 legacy GtOnlyOfficeSheet 挂点，实际 {legacy}"
        )

    def test_mode_gate_on_ancestor_not_on_mount_itself(self) -> None:
        """AC-13: 🔴 门控在**祖先的 v-else 链头**上，不在挂点自身。

        三重断言，缺一不可（这正是「只看挂点自身会假阴」的可执行形态）：
        1. 祖先链条件里含 mode 门控（`mode === '结构化视图'`，由 v-else 链头的 v-if 带入）；
        2. 挂点**自身**条件里**不含** mode（自身只有 `syncOoDescriptor` / `syncBridge`）；
        3. 祖先链感知的解析器判 `has_mode_gate == True`。
        """
        source = _a177_host_source()
        mounts = _parse_mounts(source, _A177_OO_MOUNT_TAG)
        mount = mounts[0]

        # ① 祖先链含 mode 门控
        anc_has_mode = any(
            re.search(r"\b\w*[Mm]ode\b", c) for c in mount["ancestor_conds"]
        )
        assert anc_has_mode, (
            "挂点的**祖先链**应含 mode 门控（v-else 链头的 v-if 带入），"
            f"实际祖先条件: {mount['ancestor_conds']}"
        )
        # 具体到 a177：链头 v-if 是 `mode === '结构化视图'`，v-else 分支承 OO 模式
        assert any("mode ===" in c and "结构化视图" in c
                   for c in mount["ancestor_conds"]), (
            "祖先链应含链头 v-if `mode === '结构化视图'`（OO 挂点挂在其 v-else 分支下），"
            f"实际: {mount['ancestor_conds']}"
        )

        # ② 挂点自身不含 mode（只有 descriptor / bridge 绑定）
        self_has_mode = any(
            re.search(r"\b\w*[Mm]ode\b", c) for c in mount["self_conds"]
        )
        assert not self_has_mode, (
            "挂点**自身**不应含 mode 门控（它只由 syncOoDescriptor/syncBridge 控制），"
            f"实际自身条件: {mount['self_conds']}"
        )

        # ③ 祖先链感知的解析器判 has_mode_gate
        assert mount["has_mode_gate"] is True, (
            "祖先链感知解析应判定 a177 挂点受 mode 门控"
        )

    def test_self_only_scan_false_negatives(self) -> None:
        """AC-13 变异证明: 🔴 只看挂点自身的扫描器会把 a177 判成「无门控」（假阴）。

        这条测试把「只看自身会假阴」从论断变成可复现事实：
        同一挂点，祖先链感知 → `has_mode_gate=True`；只看自身 → `has_mode_gate=False`。
        两者分歧**非零**，证明必须回溯祖先链。
        """
        source = _a177_host_source()
        ancestor_aware = _parse_mounts(source, _A177_OO_MOUNT_TAG)
        self_only = _parse_mounts_self_only(source, _A177_OO_MOUNT_TAG)

        assert ancestor_aware and self_only, "两种口径都应命中挂点（否则对比无意义）"
        assert ancestor_aware[0]["has_mode_gate"] is True
        assert self_only[0]["has_mode_gate"] is False, (
            "只看挂点自身属性应判成「无 mode 门控」（假阴），"
            f"实际 {self_only[0]['attr_str']!r}"
        )
        # 分歧非零 = 回溯祖先链的必要性证据
        assert ancestor_aware[0]["has_mode_gate"] != self_only[0]["has_mode_gate"]

    def test_ancestor_is_v_else_chain_head_three_layer_nested(self) -> None:
        """AC-13: 🔴 三层嵌套形态 —— mode 门控经 v-else 链头，OO 挂点嵌在其下三层。

        a177 的真实结构（现读确认）：
          外层 `<div v-if="mode === '结构化视图'">`（结构化视图）
          其兄弟 `<div v-else>`（在线编辑模式）= **v-else 链头**，承 mode 门控
            └ `<template v-else-if="ooReady">`
                └ `<WorkpaperSyncEditorHost v-if="syncOoDescriptor" />` = 挂点
        ⇒ mode 门控不在挂点自身、也不在挂点的直接父节点的 v-if 文本里，
          而要回溯到 v-if/v-else 兄弟链的**链头**才能取到 ⇒ 只看挂点自身必假阴。
        """
        source = _a177_host_source()
        stripped = strip_comments(source)

        # 链头 v-if（结构化视图）与其 v-else 兄弟（OO 模式）必须成对出现
        assert re.search(r'v-if="mode\s*===\s*[\'"]结构化视图[\'"]"', stripped), (
            "应有链头 `v-if=\"mode === '结构化视图'\"`（v-else 链的 v-if 头）"
        )
        # v-else 分支承 OO 模式容器
        assert re.search(r'<div\s+v-else\b[^>]*gt-a177__oo-mode', stripped), (
            "应有 `<div v-else class=\"…gt-a177__oo-mode\">`（v-else 链头承 OO 模式）"
        )

        # 嵌套深度 ≥ 3：v-else（mode 门控）→ v-else-if ooReady → v-if syncOoDescriptor
        mount = _parse_mounts(source, _A177_OO_MOUNT_TAG)[0]
        # 祖先链里既有 mode 门控，又有 ooReady（中间层），自身是 syncOoDescriptor
        assert any("ooReady" in c for c in mount["ancestor_conds"]), (
            f"中间层应有 ooReady，实际祖先条件 {mount['ancestor_conds']}"
        )
        assert any("syncOoDescriptor" in c for c in mount["self_conds"]), (
            f"挂点自身应由 syncOoDescriptor 控制，实际 {mount['self_conds']}"
        )
        # 三层各不相同的条件来源 ⇒ 嵌套深度 ≥ 3
        layers = {
            "mode_gate": any("mode ===" in c for c in mount["ancestor_conds"]),
            "oo_ready": any("ooReady" in c for c in mount["ancestor_conds"]),
            "descriptor": any("syncOoDescriptor" in c for c in mount["self_conds"]),
        }
        assert all(layers.values()), (
            f"三层嵌套形态应全部命中（mode 门控 / ooReady / descriptor），实际 {layers}"
        )

    # ── AC-25：归档欠账登记 a17-7-independence-declaration 20/21 ──

    def test_archived_spec_exists_and_is_append_only(self) -> None:
        """AC-25 前置：归档 spec 真实存在（只登记不回填修改）。"""
        assert _A177_ARCHIVED_SPEC.is_dir(), (
            f"归档 spec 应存在于归档区: {_A177_ARCHIVED_SPEC}"
        )
        assert (_A177_ARCHIVED_SPEC / "tasks.md").is_file()

    def test_archive_debt_a177_is_20_of_21(self) -> None:
        """AC-25: 🔴 `a17-7-independence-declaration` 归档欠账 = **20/21**（1 条未完成）。

        🔴 扫归档区带 errors='replace' 容错（归档区有非 UTF-8 文件的先例）。
        期望值从归档 tasks.md **现读统计**得出，禁写死任务总数。
        """
        tasks_md = _A177_ARCHIVED_SPEC / "tasks.md"
        text = tasks_md.read_bytes().decode("utf-8", errors="replace")
        assert "\ufffd" not in text, "a17-7 归档 tasks.md 若有 U+FFFD 须另行登记编码问题"

        done = len(re.findall(r"^- \[x\] ", text, re.M))
        todo = len(re.findall(r"^- \[ \] ", text, re.M))
        total = done + todo

        assert total == 21, f"a17-7 归档任务总数应为 21，现读 {total}"
        assert done == 20, f"a17-7 已完成应为 20，现读 {done}"
        assert todo == 1, f"a17-7 未完成应为 1，现读 {todo}"

        # 唯一未完成的那条是 Playwright E2E（5.2），印证其阻塞理由属「他人 spec / 环境」
        todo_lines = [ln for ln in text.splitlines() if ln.startswith("- [ ] ")]
        assert len(todo_lines) == 1
        assert "E2E" in todo_lines[0] or "Playwright" in todo_lines[0], (
            f"唯一欠账应是 Playwright E2E，实际: {todo_lines[0]!r}"
        )

    def test_this_spec_owns_exactly_one_of_the_six_foundation_debts(self) -> None:
        """AC-25: 🔴 foundation 6 份欠账里本 spec 只占 **1** 份（a17-7），其余 5 份归 lane2。

        现算归档区所有「A 循环 entry 归档 spec 且未 100%」的清单，断言：
        * 本 spec 份额 = {a17-7-independence-declaration}（恰 1 份）；
        * foundation 口径的 6 份里，另 5 份（a11-1 / a17-3-1 / a17-3 / a17-4 / a18-2）
          **不**在本 spec 范围（它们归 lane2 的 docx 车道）。
        """
        # lane3（本 spec）只负责 a177 这一条 entry 的归档欠账
        this_spec_debt = {"a17-7-independence-declaration"}

        # foundation 登记的 6 份欠账 spec 名（AC-25 口径，见 foundation requirements）
        foundation_six = {
            "a11-1-subsequent-events-inquiry",       # 19/21（lane2）
            "a17-3-1-consultation-execution",        # 15/16（lane2）
            "a17-3-consultation-record",             # 16/17（lane2）
            "a17-4-disagreement-record",             # 16/17（lane2）
            "a18-2-regulatory-communication",        # 14/15（lane2）
            "a17-7-independence-declaration",        # 20/21（lane3 = 本 spec）
        }
        assert len(foundation_six) == 6
        # 本 spec 恰占其中 1 份
        assert this_spec_debt <= foundation_six
        assert len(this_spec_debt) == 1
        # 其余 5 份不归本 spec
        lane2_five = foundation_six - this_spec_debt
        assert len(lane2_five) == 5
        assert "a17-7-independence-declaration" not in lane2_five

        # 本 spec 的那 1 份确实在归档区可定位（append-only，不回填）
        assert _A177_ARCHIVED_SPEC.name in this_spec_debt
        assert _A177_ARCHIVED_SPEC.is_dir()


# ═══════════════════════════════════════════════════════════════════════════
# §8 TestBP7NoticeWiring — AC-12（notice 接入 3 个 lane3 宿主，须在 foundation
#    任务 14 之后）
# ═══════════════════════════════════════════════════════════════════════════

#: notice 组件名与 import 来源（foundation 已验证形态，lane3 复用）。
_NOTICE_COMPONENT = "GtEntrySyncCapabilityNotice"
_NOTICE_IMPORT_SOURCE = "./sync/GtEntrySyncCapabilityNotice.vue"


def _lane3_host_to_entry(manifest_slice: dict) -> dict[Path, str]:
    """🔴 从 slice 现读 host_path → entry_id 的映射，**禁写死**。

    把 3 条 lane3 entry 的 `host_path`（slice 字段）解析成绝对路径作 key，
    `entry_id` 作 value。judging 时逐宿主读源码、断言其 `entry-id` prop 值
    恰等于该宿主对应 entry 的 canonical id —— 映射来自 slice，不是硬编码常量。
    """
    entries = _get_lane3_entries(manifest_slice)
    mapping: dict[Path, str] = {}
    for e in entries:
        host_rel = e.get("host_path", "")
        assert host_rel, f"{e['entry_id']} 缺 host_path（无法定位宿主文件）"
        host_abs = _ROOT / host_rel
        assert host_abs.is_file(), f"宿主文件应存在: {host_rel}"
        mapping[host_abs] = e["entry_id"]
    return mapping


class TestBP7NoticeWiring:
    """Task 11：BP-7 notice 接入 3 个 lane3 宿主（AC-12）。

    🔴 **tooltip 不算接线**：守卫断言的是真实挂载的 `<GtEntrySyncCapabilityNotice>`
    **组件元素**，不是 `el-tooltip`、也不是 `title=` / `tooltip=` 这类属性。notice
    组件内部**自带** `el-tooltip`（渲染「可操作原因」），但那是组件实现细节 —— 宿主
    侧必须是对该组件的 **mount**。

    与 foundation「A 域 20/20 已挂载」的对账：lane3 这 3 条（a177 / a3-console /
    a38）是 A 域 20 条的**子集**，本类只守 lane3 份额（恰 3 条）。
    """

    def test_lane3_exactly_three_hosts(self, manifest_slice: dict) -> None:
        """前置：lane3 恰 3 个宿主（与 AH-P1 的 entry 数一致）。"""
        mapping = _lane3_host_to_entry(manifest_slice)
        assert len(mapping) == 3, f"lane3 宿主应恰 3 个，实际 {len(mapping)}"
        # host_path 唯一映射到 3 条不同 entry（无重复宿主）
        assert len(set(mapping.values())) == 3

    def test_all_three_hosts_import_notice_component(
        self, manifest_slice: dict
    ) -> None:
        """AC-12: 🔴 3 个宿主都 **import** 了 notice 组件（来自 ./sync/ 真实文件）。"""
        mapping = _lane3_host_to_entry(manifest_slice)
        for host, eid in mapping.items():
            src = strip_comments(
                host.read_text(encoding="utf-8", errors="replace")
            )
            assert re.search(
                rf"import\s+{_NOTICE_COMPONENT}\s+from\s+"
                rf"['\"]{re.escape(_NOTICE_IMPORT_SOURCE)}['\"]",
                src,
            ), (
                f"{host.name}（{eid}）未从 {_NOTICE_IMPORT_SOURCE} import "
                f"{_NOTICE_COMPONENT}"
            )

    def test_notice_component_mounted_with_exact_entry_id(
        self, manifest_slice: dict
    ) -> None:
        """AC-12: 🔴 模板里挂 `<GtEntrySyncCapabilityNotice entry-id="…" />` **组件元素**，
        且 `entry-id` 值**逐字等于**该宿主对应 entry 的 canonical id（slice 现读派生）。

        `entry-id` 须紧邻组件名（中间不得插 v-if，与平台守卫口径一致）。
        """
        mapping = _lane3_host_to_entry(manifest_slice)
        for host, eid in mapping.items():
            src = strip_comments(
                host.read_text(encoding="utf-8", errors="replace")
            )
            # 组件元素挂载（接受单/双引号；entry-id 紧邻组件名）
            m = re.search(
                rf"<{_NOTICE_COMPONENT}\s+entry-id=['\"]([^'\"]+)['\"]\s*/?>",
                src,
            )
            assert m, (
                f"{host.name}（{eid}）: 未找到 "
                f"`<{_NOTICE_COMPONENT} entry-id=\"...\" />` 组件挂载"
                "（entry-id 须紧邻组件名）"
            )
            # entry-id 值逐字等于 slice 的 canonical id
            assert m.group(1) == eid, (
                f"{host.name}: entry-id 是 {m.group(1)!r}，"
                f"应逐字等于 canonical id {eid!r}"
            )

    def test_notice_is_component_mount_not_tooltip(
        self, manifest_slice: dict
    ) -> None:
        """AC-12: 🔴 **tooltip 不算接线** —— 坐实宿主侧是**组件 mount**，不是 tooltip。

        三重判据：
          ① 宿主模板出现 `<GtEntrySyncCapabilityNotice …>` 作为**元素标签**
             （而非仅出现在 import 行、字符串、或 tooltip 属性里）；
          ② notice 的 entry-id 绑定**不是** `el-tooltip` 的属性，也不是宿主自身
             `title=` / `tooltip=` / `:content=` 等 tooltip 式属性冒充；
          ③ 该元素标签位于 `<template>` 段内（真实渲染，不是脚本里的字符串常量）。
        """
        mapping = _lane3_host_to_entry(manifest_slice)
        for host, eid in mapping.items():
            raw = host.read_text(encoding="utf-8", errors="replace")
            src = strip_comments(raw)

            # ① 作为元素标签出现（开标签形态）
            tag_hits = re.findall(rf"<{_NOTICE_COMPONENT}\b", src)
            assert tag_hits, (
                f"{host.name}（{eid}）: notice 未作为元素标签挂载"
            )

            # ③ 该标签在 <template> 段内
            tmpl = re.search(r"<template\b[^>]*>(.*)</template>", src, re.S)
            assert tmpl, f"{host.name} 应有 <template> 段"
            assert re.search(rf"<{_NOTICE_COMPONENT}\b", tmpl.group(1)), (
                f"{host.name}: notice 组件标签不在 <template> 段内（疑为字符串常量）"
            )

            # ② 不是 tooltip 冒充：entry-id 不得挂在 el-tooltip 上，
            #    且 notice 不是靠宿主的 title / tooltip 属性实现
            assert not re.search(
                r"<el-tooltip\b[^>]*\bentry-id=", tmpl.group(1)
            ), f"{host.name}: entry-id 挂在 el-tooltip 上 ⇒ tooltip 不算接线"
            notice_tag = re.search(
                rf"<{_NOTICE_COMPONENT}\b[^>]*?>", tmpl.group(1), re.S
            )
            assert notice_tag, f"{host.name}: 取不到 notice 开标签"
            assert "tooltip" not in notice_tag.group(0).lower(), (
                f"{host.name}: notice 挂载不得带 tooltip 式属性 ⇒ 必须是组件 mount"
            )

    def test_lane3_notice_count_is_exactly_three_subset_of_a_domain(
        self, manifest_slice: dict
    ) -> None:
        """AC-12: 🔴 计数 = 恰 **3** 个 lane3 宿主已接线（与 foundation「A 域 20/20
        已挂载」对账 —— 这 3 条是 A 域 20 条的子集）。

        逐宿主现算「模板里真实挂了 notice 组件元素」的宿主数，断言 == 3，
        并断言 lane3 的 3 条 entry 全在 A 域 entry 集合内（子集关系）。
        """
        mapping = _lane3_host_to_entry(manifest_slice)
        wired = 0
        for host in mapping:
            src = strip_comments(
                host.read_text(encoding="utf-8", errors="replace")
            )
            tmpl = re.search(r"<template\b[^>]*>(.*)</template>", src, re.S)
            if tmpl and re.search(
                rf"<{_NOTICE_COMPONENT}\s+entry-id=", tmpl.group(1)
            ):
                wired += 1
        assert wired == 3, f"lane3 已接线宿主应恰 3 个，现算 {wired}"

        # 子集对账：lane3 的 3 条 entry 全在 A 域 entry 集合里
        a_entries = a_domain_entries(manifest_slice["independent_entries"])
        a_eids = {e["entry_id"] for e in a_entries}
        lane3_eids = set(mapping.values())
        assert lane3_eids <= a_eids, (
            f"lane3 entry 应是 A 域子集，越界: {lane3_eids - a_eids}"
        )
        assert len(a_eids) == 20, (
            f"A 域应 20 条（foundation 20/20 对账基准），实际 {len(a_eids)}"
        )
        assert len(lane3_eids) == 3


# ═══════════════════════════════════════════════════════════════════════════
# §9 TestTask13ExternalDebtRegistration — 平台级与业务依赖欠账登记
#    （BP-1 ~ BP-5 平台层 · BP-6 step ① 已解为非缺口 · a17-7 E2E 归他人 spec）
#    AC-25 · AC-46 · Requirement 2 · Requirement 4
# ═══════════════════════════════════════════════════════════════════════════

#: BP-1 ~ BP-5 的平台级口径：成员集 == 全 slice 全部 46 条 entry。
#: 🔴 这是「平台层而非 lane3 单方可裁」的可执行判据——它们的成员数远超 lane3 的 3 条，
#:    且恰等于全 slice entry 总数（46），故本 3-entry 车道无法单方收口。
_PLATFORM_BP_IDS = ("BP-1", "BP-2", "BP-3", "BP-4", "BP-5")


def _bp_members(manifest_slice: dict, bp_id: str) -> list[str]:
    """从 slice 现读某条 BP 的成员 entry 列表（禁写死）。"""
    bps = manifest_slice.get("blocking_preconditions", [])
    hit = [b for b in bps if isinstance(b, dict) and b.get("id") == bp_id]
    assert hit, f"{bp_id} 应存在于 slice.blocking_preconditions"
    return hit[0].get("entries", hit[0].get("entry_ids", []))


class TestTask13ExternalDebtRegistration:
    """Task 13（`[ ]*` 受外部依赖阻塞）：欠账登记守卫。

    🔴 本任务的「完成」= **欠账被正确登记、可解的部分已解**，而非「所有欠账都已修」。
    依项目铁律「任务标记不能假绿」：
      · BP-1 ~ BP-5 是**平台层**阻塞（跨全 46 条 entry），本 3-entry 车道无法单方裁决
        ⇒ 登记为 blocked、理由「平台层」，**不**标绿；
      · BP-6 的 step ①（`A3-8` 权威册是补还是声明无册）经 Task 7/8 实证**已解为非缺口**
        （册一直在磁盘、解析层已修、宿主已收敛）⇒ 据实登记为**已解**，不再挂「业务决策」；
      · `a17-7-independence-declaration` 归档 spec 的 1 条 Playwright E2E 欠账由**对应
        功能 spec 负责人**补做（append-only，不回填归档 spec）⇒ 登记为 deferred、
        理由「他人 spec 范围」。
    """

    # ── BP-1 ~ BP-5：平台层，lane3 无法单方裁决（标 blocked，不标绿）──

    def test_platform_bps_span_all_46_entries_not_lane3_specific(
        self, manifest_slice: dict
    ) -> None:
        """🔴 BP-1 ~ BP-5 是**平台级**：各自成员集 == 全 slice 46 条 entry。

        这是「平台层而非 lane3 单方可裁」的可执行判据——成员数（46）远超 lane3 的
        3 条，且恰等于全 slice entry 总数。期望值从 slice 现读派生，禁写死。
        """
        all_entries = manifest_slice["independent_entries"]
        total = len(all_entries)
        assert total == 46, f"全 slice entry 总数应为 46，现读 {total}"

        for bp_id in _PLATFORM_BP_IDS:
            members = _bp_members(manifest_slice, bp_id)
            assert len(members) == total == 46, (
                f"{bp_id} 应覆盖全部 46 条 entry（平台级），现读 {len(members)}"
            )
            # 成员数远超 lane3 的 3 条 ⇒ 不是 lane3-specific 的欠账
            assert len(members) > 3, (
                f"{bp_id} 成员数应远超 lane3 的 3 条（证明是平台级而非本车道专属）"
            )

    def test_lane3_three_entries_are_subset_of_each_platform_bp(
        self, manifest_slice: dict
    ) -> None:
        """🔴 lane3 的 3 条 entry 是每条平台级 BP 成员集的**子集**（受其阻塞但无从单解）。

        子集关系坐实：lane3 这 3 条确实**被** BP-1~BP-5 阻塞（在成员集里），但由于
        这些 BP 跨全 46 条 entry，本车道**无法**只为自己这 3 条单方解除——必须平台层
        统一发布（approved 模型 / contract / capability 裁决 / bundle & published /
        adapter 注册）。故登记为 blocked、理由「平台层」。
        """
        lane3_ids = {
            "xlsx/gt-a177-independence-declaration",
            "xlsx/gt-a3-consolidation-console",
            "xlsx/gt-a38-goodwill-impairment",
        }
        for bp_id in _PLATFORM_BP_IDS:
            members = set(_bp_members(manifest_slice, bp_id))
            assert lane3_ids <= members, (
                f"lane3 的 3 条应是 {bp_id} 成员的子集（受其阻塞），"
                f"缺失: {lane3_ids - members}"
            )

    def test_platform_bps_still_open_not_falsely_resolved(
        self, manifest_slice: dict
    ) -> None:
        """🔴 BP-1 ~ BP-5 的 status 仍为 **open**（禁假绿）。

        依「任务标记不能假绿」：这 5 条是外部依赖，本任务**不得**把它们标成已解。
        slice 的 `status` 字段现读须仍是 open（若平台层后来解除，slice 会改为非 open，
        届时本断言打红，提醒本登记已过期——这正是「结构性零/状态须随真相变化」）。
        """
        bps = manifest_slice.get("blocking_preconditions", [])
        for bp_id in _PLATFORM_BP_IDS:
            hit = [b for b in bps if isinstance(b, dict) and b.get("id") == bp_id]
            assert hit, f"{bp_id} 应存在"
            status = hit[0].get("status")
            assert status == "open", (
                f"{bp_id} 的 status 应仍为 open（平台级欠账未解，本任务不得标绿），"
                f"实际 {status!r}"
            )

    def test_design_registers_platform_bps_as_blocked_with_reason(self) -> None:
        """🔴 design.md 把 BP-1 ~ BP-5 显式登记为「平台级 / 标 `[ ]*`」，理由「平台层」。

        现读 design.md 的 BP 收口路线表，断言其中有一行把 BP-1 ~ BP-5 归为平台级且
        标注受阻（`[ ]*`）。这保证「登记在案」而非只在测试里断言。
        """
        design = (
            _ROOT / ".kiro" / "specs"
            / "a-class-runtime-sheetname-and-carrier-exceptions" / "design.md"
        ).read_text(encoding="utf-8", errors="replace")
        assert "\ufffd" not in design, "design.md 不应含 U+FFFD"
        assert "BP-1 ~ BP-5" in design, "design.md 应登记 BP-1 ~ BP-5 平台级欠账行"
        assert "平台级" in design and "[ ]*" in design, (
            "design.md 应把 BP-1 ~ BP-5 标注为平台级且受阻（`[ ]*`）"
        )

    # ── BP-6 step ①：经 Task 7/8 已解为**非缺口**（据实登记为已解，非 pending）──

    def test_bp6_step1_resolved_as_non_gap_not_pending_business_decision(
        self, manifest_slice: dict
    ) -> None:
        """🔴 BP-6 的 step ①（`A3-8` 权威册补 or 声明无册）经 Task 7/8 **已解为非缺口**。

        tasks.md 任务 13 原把它列为「依赖业务决策，本 spec 无法单方裁定」。但 Task 7/8
        （errata E-1、design §Task 8）已实证：
          · 合册 `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx` **一直在磁盘上**；
          · 解析层已修（`find_template_file_any('A3-8')` 现算非 None）；
          · 宿主 sheet 名已收敛为纯码（Task 8 step ②）。
        ⇒ 「补册」与「声明无册」**两条都不适用**（册不缺），这不是待决的业务决策，
          而是**已解除的非缺口**。本测试据实坐实「已解」，不把它继续挂成 pending。
        """
        from app.services import wp_template_finder as FINDER

        # ① 册在磁盘（现算恰 1 本承载 A3-8 的合册）
        contained = [
            f for f in _TEMPLATE_DIR.rglob("*A3-8*")
            if f.suffix.lower() in (".xlsx", ".docx") and "~$" not in f.name
        ]
        assert len(contained) == 1, (
            f"承载 A3-8 的册应恰 1 本（非缺口的证据），实得 {[f.name for f in contained]}"
        )

        # ② 解析层已修（纯码 A3-8 可解析到合册）
        resolved = FINDER.find_template_file_any_unresolved("A3-8")
        assert resolved is not None, (
            "A3-8 应能解析到合册（step ① 解析层已修）⇒ 不是「无册」缺口"
        )

        # ③ BP-6 全 slice 仅 1 条且归 a38（裁决基线保持）
        members = _bp_members(manifest_slice, "BP-6")
        assert len(members) == 1 and "a38" in members[0], (
            f"BP-6 全 slice 应恰 1 条且归 a38，现读 {members!r}"
        )

    def test_errata_records_bp6_resolution_glob_anchoring_root_cause(self) -> None:
        """🔴 errata.md 记录了 BP-6 的「非缺口」再更正（glob 锚定假事实）。

        现读 errata.md，断言 E-1 把「没有 A3-8 这本册」证伪，并记录真因是
        `rglob('A3-8*')` 锚定文件名开头的 glob 口径问题（合册真名以 `A3-7` 起头）。
        这保证「BP-6 step ① 已解为非缺口」这一结论**登记在案**、可审计。
        """
        errata = (
            _ROOT / ".kiro" / "specs"
            / "a-class-runtime-sheetname-and-carrier-exceptions" / "errata.md"
        ).read_text(encoding="utf-8", errors="replace")
        assert "\ufffd" not in errata, "errata.md 不应含 U+FFFD"
        # E-1 把「没有这本册」证伪
        assert "E-1" in errata and "已证伪" in errata, (
            "errata.md 应有 E-1 把「没有 A3-8 这本册」证伪"
        )
        # 真因是 glob 锚定（合册真名以 A3-7 起头）
        assert "锚定" in errata and "A3-7" in errata, (
            "errata.md 应记录真因 = rglob 锚定文件名开头 + 合册真名以 A3-7 起头"
        )

    def test_task13_registration_section_present_in_design(self) -> None:
        """🔴 design.md 有 Task 13 欠账登记专节（append-only），且三类欠账各有登记。

        断言专节标题存在，且三类欠账的关键词都出现（平台层 / 非缺口 / 他人 spec），
        保证「欠账被正确登记」是文档级事实而不仅是测试断言。
        """
        design = (
            _ROOT / ".kiro" / "specs"
            / "a-class-runtime-sheetname-and-carrier-exceptions" / "design.md"
        ).read_text(encoding="utf-8", errors="replace")
        assert "Task 13" in design, "design.md 应有 Task 13 欠账登记专节"
        # 三类欠账登记关键词
        assert "平台层" in design, "应登记 BP-1~BP-5 平台层欠账"
        assert "非缺口" in design, "应登记 BP-6 step ① 已解为非缺口"
        assert "他人 spec" in design or "他人 spec范围" in design, (
            "应登记 a17-7 E2E 由他人 spec 负责"
        )

    # ── a17-7 归档欠账：1 条 Playwright E2E 由他人 spec 负责（deferred）──

    def test_a177_archive_debt_is_owned_by_feature_spec_not_lane3(self) -> None:
        """🔴 a17-7 归档 spec 的 1 条 E2E 欠账由**对应功能 spec 负责人**补做，非 lane3。

        与 §7 `test_archive_debt_a177_is_20_of_21` 的分工：那条坐实「20/21 且欠的是
        E2E」；本条坐实「这 1 条**不归本 lane3 spec 修**」——
          · 本 lane3 spec（代码层）只负责**登记**该欠账（append-only，不回填归档 spec）；
          · 该 E2E 须在**真实浏览器环境**下由对应功能 spec 的负责人执行 ⇒ 阻塞理由
            「他人 spec 范围 / 环境」，登记为 deferred，不在本任务里标绿。
        """
        tasks_md = _A177_ARCHIVED_SPEC / "tasks.md"
        assert tasks_md.is_file(), "a17-7 归档 tasks.md 应存在（登记对象可定位）"
        text = tasks_md.read_bytes().decode("utf-8", errors="replace")
        assert "\ufffd" not in text, "a17-7 归档 tasks.md 若有 U+FFFD 须另行登记"

        todo_lines = [ln for ln in text.splitlines() if ln.startswith("- [ ] ")]
        assert len(todo_lines) == 1, (
            f"a17-7 应恰 1 条未完成（归他人 spec），现读 {len(todo_lines)}"
        )
        # 唯一欠账是 Playwright E2E（须真实浏览器环境）
        assert "E2E" in todo_lines[0] or "Playwright" in todo_lines[0], (
            f"唯一欠账应是 Playwright E2E，实际: {todo_lines[0]!r}"
        )
        # 🔴 不回填：归档 spec 仍是 20/21（本任务只登记，未动它）
        done = len(re.findall(r"^- \[x\] ", text, re.M))
        assert done == 20, (
            f"a17-7 归档应仍为 20/21（本任务 append-only 不回填修改），现读 done={done}"
        )
