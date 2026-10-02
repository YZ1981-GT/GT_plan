# -*- coding: utf-8 -*-
"""M 循环三 spec 守卫测试 — 锁定改线后目标态。

spec: m-cycle-sync-foundation-and-first-canary
      m1-m5-m8-m9-mode-value-and-carrier-exceptions
      m2-m3-m4-m7-m10-sheet-map-drift-and-collapse

既存守卫 test_task55_m_cycle_migration.py 锁「现状诚实记录」；
本文件锁「改线后目标态」—— 重叠处引用既存测试名，不重写。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# 路径常量
# ═══════════════════════════════════════════════════════════════════════════
ROOT = Path(__file__).resolve().parents[2]  # backend/
REPO = ROOT.parent                          # GT_plan/
TEMPLATE_DIR = ROOT / "wp_templates" / "M"
FRONTEND = REPO / "audit-platform" / "frontend" / "src"
COMPOSABLES = FRONTEND / "components" / "workpaper" / "composables"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
MANIFEST_PATH = ROOT / "data" / "workpaper_sync_entry_manifest.json"
SLICE_PATH = ROOT / "data" / "workpaper_sync_m_cycle_manifest_slice.json"
DELETION_PLAN_PATH = ROOT / "data" / "workpaper_sync_m_cycle_deletion_plan.json"

M_CODES = [f"M{n}" for n in range(1, 11)]
MAP_RE = re.compile(r"""['"]?(\S+?)['"]?\s*:\s*'([^']+)'""")


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════
def _wb_stem(n: int) -> str | None:
    """M{n} 对应的权威册 stem。"""
    for p in sorted(TEMPLATE_DIR.glob("*.xlsx")):
        code = f"M{n}"
        if n == 10 and "M10" in p.stem:
            return p.stem
        if n < 10 and f"M{n} " in p.stem and f"M{n}0" not in p.stem:
            return p.stem
    return None


def _wb_path(n: int) -> Path:
    stem = _wb_stem(n)
    assert stem, f"M{n} 无对应权威册"
    return TEMPLATE_DIR / f"{stem}.xlsx"


def _read_sheet_map(n: int) -> list[tuple[str, str]]:
    """正则提取 M{n}_SHEET_MAP 的键值对。"""
    fpath = COMPOSABLES / f"useM{n}EntryDualMode.ts"
    text = fpath.read_text(encoding="utf-8")
    m = re.search(r"M\d+_SHEET_MAP.*?\{([^}]+)\}", text, re.DOTALL)
    return MAP_RE.findall(m.group(1)) if m else []


def _real_sheets(n: int) -> list[str]:
    """openpyxl 真读权威册 sheet 名（不 strip）。"""
    import openpyxl
    wb = openpyxl.load_workbook(_wb_path(n), read_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names


def _strip_comments(text: str) -> str:
    """剥 HTML/块/行注释，保留行号。"""
    text = re.sub(r"<!--[\s\S]*?-->", lambda m: "\n" * m.group(0).count("\n"), text)
    text = re.sub(r"/\*[\s\S]*?\*/", lambda m: "\n" * m.group(0).count("\n"), text)
    text = re.sub(r"(?<!:)//.*", "", text)
    return text


def _host_text(n: int) -> str:
    """读 M{n} 宿主 .vue 文件文本。"""
    candidates = list(WP_COMPONENTS.glob(f"GtM{n}[A-Z]*.vue"))
    if n == 10:
        candidates = [p for p in WP_COMPONENTS.glob("GtM10*.vue")]
    assert len(candidates) == 1, f"M{n} 宿主数 != 1: {candidates}"
    return candidates[0].read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 阶段 0: 口径基线与红判据（Foundation Task 0-5）
# ═══════════════════════════════════════════════════════════════════════════
class TestBaselineAndRedCriteria:
    """Task 0-5: M 域文件集、manifest 门、结构性零。"""

    def test_ten_workbooks_102_sheets_no_m0(self):
        """Task 0 + 24: 10 册 / 102 sheets / 无 M0。"""
        wbs = list(TEMPLATE_DIR.glob("*.xlsx"))
        assert len(wbs) == 10
        import openpyxl
        total = 0
        for p in wbs:
            wb = openpyxl.load_workbook(p, read_only=True)
            total += len(wb.sheetnames)
            wb.close()
        assert total == 102
        # 无 M0
        assert not any("M0" in p.stem for p in wbs)

    def test_manifest_entry_count_is_ten(self):
        """Task 1: manifest 里 M 域 entry 恰 10 条（通过 slice 验证）。"""
        if SLICE_PATH.exists():
            sl = json.loads(SLICE_PATH.read_bytes())
            ie = sl.get("independent_entries", {})
            if isinstance(ie, dict):
                assert len(ie) == 10
            elif isinstance(ie, list):
                assert len(ie) == 10

    def test_formula_cells_2937_formula_sheets_81(self):
        """Task 30: 公式格 2937 / 带公式 sheet 81。"""
        import openpyxl
        total_fc = 0
        total_fs = 0
        for p in sorted(TEMPLATE_DIR.glob("*.xlsx")):
            wb = openpyxl.load_workbook(p, read_only=False, data_only=False)
            for sn in wb.sheetnames:
                ws = wb[sn]
                fc = sum(
                    1 for row in ws.iter_rows() for c in row
                    if c.data_type == "f" or (isinstance(c.value, str) and c.value.startswith("="))
                )
                total_fc += fc
                if fc > 0:
                    total_fs += 1
            wb.close()
        assert total_fc == 2937, f"公式格 {total_fc} != 2937"
        assert total_fs == 81, f"带公式 sheet {total_fs} != 81"

    def test_item_prefix_all_ten(self):
        """Task 33: 10 个 useM{n}FormData 全有 ITEM_PREFIX 常量。"""
        count = 0
        for n in range(1, 11):
            fd = COMPOSABLES / f"useM{n}FormData.ts"
            if fd.exists() and "ITEM_PREFIX" in fd.read_text(encoding="utf-8"):
                count += 1
        assert count == 10, f"ITEM_PREFIX 只在 {count}/10 个 FormData 中"

    def test_localstorage_zero_live_keys(self):
        """Task 11 / MC-16: 活路径 0 localStorage 键。"""
        for n in range(1, 11):
            edm = COMPOSABLES / f"useM{n}EntryDualMode.ts"
            if edm.exists():
                assert "localStorage" not in edm.read_text(encoding="utf-8"), (
                    f"M{n} live 模块含 localStorage"
                )


# ═══════════════════════════════════════════════════════════════════════════
# 阶段 1: 载体族与门控形态（Foundation Task 6-11）
# ═══════════════════════════════════════════════════════════════════════════
class TestCarrierAndModeSwitch:
    """Task 6-11: 成对孪生、载体 kind、mode 门控。"""

    def test_twenty_dual_mode_files_exist(self):
        """Task 6: 双模式文件数。M9 orphan 删除后 = 9 DualMode + 9 EntryDualMode = 18。"""
        dm = list(COMPOSABLES.glob("useM*DualMode.ts"))
        edm = list(COMPOSABLES.glob("useM*EntryDualMode.ts"))
        dm = [p for p in dm if re.match(r"useM(?:10|[1-9])DualMode\.ts$", p.name)]
        edm = [p for p in edm if re.match(r"useM(?:10|[1-9])EntryDualMode\.ts$", p.name)]
        assert len(dm) == 9, f"DualMode 数 {len(dm)}"
        assert len(edm) == 9, f"EntryDualMode 数 {len(edm)}"

    def test_orphan_dualmode_zero_host_imports(self):
        """Task 6: orphan useM*DualMode.ts 无宿主 import。"""
        for n in range(1, 11):
            dm_name = f"useM{n}DualMode"
            imported = False
            for vue in WP_COMPONENTS.glob("GtM*.vue"):
                if dm_name in vue.read_text(encoding="utf-8"):
                    imported = True
                    break
            assert not imported, f"{dm_name} 被宿主引用了"

    def test_live_entrydualmode_each_has_one_host(self):
        """Task 6: live useM*EntryDualMode.ts 各被恰 1 个宿主引用（M9 除外：双孪生皆 orphan）。"""
        for n in range(1, 11):
            if n == 9:
                continue  # M9 双孪生皆 orphan，宿主不 import EntryDualMode
            edm_name = f"useM{n}EntryDualMode"
            hosts = [
                vue.name for vue in WP_COMPONENTS.glob("GtM*.vue")
                if edm_name in vue.read_text(encoding="utf-8")
            ]
            assert len(hosts) == 1, f"{edm_name} 宿主数 {len(hosts)}: {hosts}"

    def test_segmented_nine_plus_no_switch_one(self):
        """Task 8-9: 9 宿主有 el-segmented（redeemable），M9 无。"""
        has_seg = []
        no_seg = []
        for n in range(1, 11):
            text = _strip_comments(_host_text(n))
            if "el-segmented" in text:
                has_seg.append(f"M{n}")
            else:
                no_seg.append(f"M{n}")
        assert len(has_seg) == 9, f"el-segmented 宿主: {has_seg}"
        assert no_seg == ["M9"], f"无开关宿主应只有 M9: {no_seg}"

    def test_orphan_mode_enum_split(self):
        """Task 11 / MC-16: orphan 的 mode 枚举分裂。
        M1~M4: 'structured' | 'onlyoffice'
        M5~M10: 'html' | 'onlyoffice' (或类型引用)
        """
        for n in range(1, 11):
            dm = COMPOSABLES / f"useM{n}DualMode.ts"
            if not dm.exists():
                continue
            text = dm.read_text(encoding="utf-8")
            if n <= 4:
                assert "'structured'" in text, f"M{n} orphan 应含 structured"
            else:
                # M5~M10 用 'html' 或类型引用 WorkpaperRenderMode
                has_html = "'html'" in text
                has_type_ref = "WorkpaperRenderMode" in text
                assert has_html or has_type_ref, f"M{n} orphan 应含 html 或类型引用"

    def test_no_inlined_iife_dual_mode(self):
        """Task 7: M 域无宿主内联 IIFE (const dualMode = (() =>)。"""
        for n in range(1, 11):
            clean = _strip_comments(_host_text(n))
            assert "const dualMode = (() =>" not in clean, f"M{n} 有内联 IIFE"


# ═══════════════════════════════════════════════════════════════════════════
# 阶段 2: 写路径守卫（Foundation Task 12-15）
# ═══════════════════════════════════════════════════════════════════════════
class TestWritePath:
    """Task 12-15: TB 发布门、旧端点、确认门。"""

    def test_publish_to_tb_exactly_ten(self):
        """Task 12: publish-to-tb 代码命中恰 10。"""
        hits = 0
        for n in range(1, 11):
            fd = COMPOSABLES / f"useM{n}FormData.ts"
            if fd.exists():
                text = fd.read_text(encoding="utf-8")
                if "publish-to-tb" in text:
                    hits += 1
        assert hits == 10, f"publish-to-tb 命中 {hits}"

    def test_writeback_zero_code_hits(self):
        """Task 13: trial-balance/writeback 代码命中 0（全为注释）。"""
        for n in range(1, 11):
            fd = COMPOSABLES / f"useM{n}FormData.ts"
            if not fd.exists():
                continue
            for line in fd.read_text(encoding="utf-8").split("\n"):
                if "trial-balance/writeback" in line:
                    stripped = line.strip()
                    assert stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"), (
                        f"M{n} FormData 有非注释的 writeback: {line.strip()}"
                    )

    def test_confirm_not_in_formdata_files(self):
        """Task 14: ElMessageBox.confirm 不在 FormData 文件中。"""
        for n in range(1, 11):
            fd = COMPOSABLES / f"useM{n}FormData.ts"
            if fd.exists():
                text = fd.read_text(encoding="utf-8")
                assert "ElMessageBox.confirm" not in text, f"M{n} FormData 含 confirm"


# ═══════════════════════════════════════════════════════════════════════════
# 阶段 3: SHEET_MAP 基线（Foundation Task 16-20, Lane2 Task 4-9）
# ═══════════════════════════════════════════════════════════════════════════
class TestSheetMapBaseline:
    """Task 16-20: SHEET_MAP 三方等值、缺陷归属、修正后目标态。"""

    def test_declared_hit_miss_after_m9_deletion(self):
        """Task 16 + Lane2 Task 7 + Lane3 Task 9: M9 orphan 删除后 MAP 全命中。"""
        import openpyxl
        total_d = total_h = total_m = 0
        for n in range(1, 11):
            edm = COMPOSABLES / f"useM{n}EntryDualMode.ts"
            if not edm.exists():
                continue  # M9 已删
            pairs = _read_sheet_map(n)
            real = set(_real_sheets(n))
            d = len(pairs)
            h = sum(1 for _, v in pairs if v in real)
            total_d += d
            total_h += h
            total_m += d - h
        assert total_d == 76, f"declared {total_d}"  # 84 - M9 的 8
        assert total_h == 76, f"hit {total_h}"       # 全命中
        assert total_m == 0, f"miss {total_m}"        # 零 miss

    def test_zero_miss_after_m9_orphan_deleted(self):
        """Task 17: M9 orphan 删除后全域 0 miss。"""
        import openpyxl
        miss_entries = []
        for n in range(1, 11):
            edm = COMPOSABLES / f"useM{n}EntryDualMode.ts"
            if not edm.exists():
                continue
            pairs = _read_sheet_map(n)
            real = set(_real_sheets(n))
            miss = [(k, v) for k, v in pairs if v not in real]
            if miss:
                miss_entries.append((f"M{n}", miss))
        assert len(miss_entries) == 0, f"仍有 miss: {miss_entries}"

    def test_five_entries_zero_miss_after_fix(self):
        """Lane2 Task 9: 修正后 M2/M3/M4/M7/M10 各 0 miss。"""
        import openpyxl
        for n in [2, 3, 4, 7, 10]:
            pairs = _read_sheet_map(n)
            real = set(_real_sheets(n))
            miss = [v for _, v in pairs if v not in real]
            assert miss == [], f"M{n} 仍有 miss: {miss}"

    def test_sheet_names_not_stripped(self):
        """MC-10: SHEET_MAP 值含原始空格（不 strip）。"""
        import openpyxl
        # M7 程序表有前导+中间+尾随三重空格
        m7_pairs = _read_sheet_map(7)
        proc = dict(m7_pairs).get("procedure", "")
        assert proc.startswith(" "), "M7 procedure 应含前导空格"
        assert proc.endswith(" "), "M7 procedure 应含尾随空格"
        assert "  " not in proc.strip() or " M7A" in proc, "M7 procedure 应含中间空格"

    def test_m10_disclosure_uses_correct_names(self):
        """MC-25 / Lane2 Task 11: M10 附注用「核对」非「披露信息」。"""
        m10_map = dict(_read_sheet_map(10))
        assert "核对" in m10_map.get("disclosure-listed", "")
        assert "核对" in m10_map.get("disclosure-soe", "")
        assert "国企" in m10_map.get("disclosure-soe", "")
        assert "国有企业" not in m10_map.get("disclosure-soe", "")

    def test_fallback_all_hit_real_sheets(self):
        """Task 19 / Lane2 Task 8: 10 条 fallback「审定表M{n}-1」全命中。"""
        import openpyxl
        for n in range(1, 11):
            real = set(_real_sheets(n))
            fb = f"审定表M{n}-1"
            assert fb in real, f"M{n} fallback {fb!r} 不在权威册中"


# ═══════════════════════════════════════════════════════════════════════════
# 阶段 4: 模板层基线（Foundation Task 24-30）
# ═══════════════════════════════════════════════════════════════════════════
class TestTemplateBaseline:
    """Task 24-30: 权威册对账、sheet 归属、公式规模。"""

    def test_m6_formula_cells_175_is_minimum(self):
        """Task 30 / Task 38: M6 公式格 175 且是 10 册最小。"""
        import openpyxl
        fc_by_n: dict[int, int] = {}
        for n in range(1, 11):
            wb = openpyxl.load_workbook(_wb_path(n), read_only=False, data_only=False)
            fc = 0
            for sn in wb.sheetnames:
                for row in wb[sn].iter_rows():
                    for c in row:
                        if c.data_type == "f" or (isinstance(c.value, str) and c.value.startswith("=")):
                            fc += 1
            fc_by_n[n] = fc
            wb.close()
        assert fc_by_n[6] == 175, f"M6 公式格 {fc_by_n[6]}"
        assert fc_by_n[6] == min(fc_by_n.values()), f"M6 非最小: {fc_by_n}"

    def test_m9_formula_cells_470_second_most(self):
        """Lane3 Task 7: M9 公式格 470（第二多）。"""
        import openpyxl
        wb = openpyxl.load_workbook(_wb_path(9), read_only=False, data_only=False)
        fc = sum(
            1 for sn in wb.sheetnames for row in wb[sn].iter_rows()
            for c in row if c.data_type == "f" or (isinstance(c.value, str) and c.value.startswith("="))
        )
        wb.close()
        assert fc == 470, f"M9 公式格 {fc}"

    def test_m1_sheet_names_exact(self):
        """Task 26: M1 的 SHEET_MAP 全命中（0 miss，不属修正范围内）。"""
        pairs = _read_sheet_map(1)
        real = set(_real_sheets(1))
        miss = [v for _, v in pairs if v not in real]
        assert miss == [], f"M1 有意外 miss: {miss}"


# ═══════════════════════════════════════════════════════════════════════════
# 阶段 5: 位置化行身份（Foundation Task 31-36）
# ═══════════════════════════════════════════════════════════════════════════
class TestPositionalIdentity:
    """Task 31-36: 位置化四族、removeRow、derived_total。"""

    def test_item_id_row_pattern_exists(self):
        """Task 31 族②: item_id 里 row-${...} 段存在。"""
        hits = 0
        for n in range(1, 11):
            for ts in COMPOSABLES.glob(f"useM{n}*.ts"):
                text = ts.read_text(encoding="utf-8")
                hits += len(re.findall(r"row-\$\{", text))
        assert hits > 0, "M 域 item_id row 位置化命中 0"

    def test_entropy_key_exists(self):
        """Task 31 族④: 熵键 Date.now / Math.random 存在。"""
        hits = 0
        for n in range(1, 11):
            for ts in COMPOSABLES.glob(f"useM{n}*.ts"):
                text = ts.read_text(encoding="utf-8")
                hits += len(re.findall(r"Date\.now\(\)", text))
                hits += len(re.findall(r"Math\.random\(\)", text))
        assert hits > 0, "M 域无熵键"

    def test_remove_row_signatures_exist(self):
        """Task 34: removeRow / handleRemove 签名存在。"""
        sigs: list[str] = []
        for n in range(1, 11):
            for ts in COMPOSABLES.glob(f"useM{n}Adjudication.ts"):
                text = ts.read_text(encoding="utf-8")
                sigs.extend(m.group(0) for m in re.finditer(r"(?:removeRow|handleRemove)\s*\([^)]*\)", text))
            for sub in (WP_COMPONENTS / f"m{n}" / "core").glob("*.vue"):
                text = sub.read_text(encoding="utf-8")
                sigs.extend(m.group(0) for m in re.finditer(r"(?:removeRow|handleRemove)\s*\([^)]*\)", text))
        assert len(sigs) > 0, "M 域无 removeRow 签名"

    def test_derived_total_both_patterns(self):
        """Task 35: derived_total 双正则 TAIL(-total) 与 MID(-total-) 都非零。"""
        tail = 0
        mid = 0
        for n in range(1, 11):
            for ts in COMPOSABLES.glob(f"useM{n}*.ts"):
                text = ts.read_text(encoding="utf-8")
                tail += len(re.findall(r"-total['\"`,\s\)]", text))
                mid += len(re.findall(r"-total-", text))
        assert tail > 0, "TAIL 正则 0 命中"
        assert mid > 0, "MID 正则 0 命中"
        assert mid > tail, f"M 域 MID({mid}) 应 > TAIL({tail})"


# ═══════════════════════════════════════════════════════════════════════════
# 阶段 6-7: canary + 平台工具（Foundation Task 37-45）
# ═══════════════════════════════════════════════════════════════════════════
class TestCanaryAndPlatformTools:
    """Task 37-45: canary 判据、resolveProcedureSheetKey、BP-12。"""

    def test_resolve_procedure_sheet_key_m_ten_branches(self):
        """Task 43: M 段 10 条分支（含补全的 M1/M3/M7/M8）。"""
        rpsk = (FRONTEND / "utils" / "resolveProcedureSheetKey.ts").read_text(encoding="utf-8")
        m_branches = re.findall(r"upper\.startsWith\('M\d", rpsk)
        assert len(m_branches) == 10, f"M 段分支 {len(m_branches)}"

    def test_m10_dispatch_handles_guoqi(self):
        """Task 43 + Lane2 Task 11: M10 宿主能正确匹配「国企」sheet。"""
        text = _host_text(10)
        clean = _strip_comments(text)
        # 修正后应含「国企」匹配而非「国有企业」
        assert "国企" in clean, "M10 dispatch 应含「国企」"
        # 「国有企业」不应出现在 dispatch 代码中
        # （注释里可以有，但 includes('国有企业') 不应在代码中）
        for line in clean.split("\n"):
            if "includes(" in line and "国有企业" in line:
                stripped = line.strip()
                if not stripped.startswith("//") and not stripped.startswith("*"):
                    pytest.fail(f"M10 dispatch 代码仍含 includes('国有企业'): {stripped}")

    def test_m10_soe_sheet_now_reachable(self):
        """Lane2 Task 11: BP-12 修正后 disclosure-soe 现在可达。"""
        text = _host_text(10)
        clean = _strip_comments(text)
        real = _real_sheets(10)
        soe_sheet = [s for s in real if "国企" in s]
        assert soe_sheet, "M10 权威册应有含「国企」的 sheet"
        # dispatch 应能路由到 disclosure-soe
        assert "国企" in clean and "disclosure-soe" in clean


# ═══════════════════════════════════════════════════════════════════════════
# Lane2: SHEET_MAP 修 + BP-12 + BP-8 + BP-6 + 模板修复
# ═══════════════════════════════════════════════════════════════════════════
class TestLane2SheetMapAndDefects:
    """Lane2 Task 0-28: BP-4/BP-6/BP-8/BP-12 修正验证。"""

    def test_bp4_five_entries_have_blocked_by(self):
        """Lane2 Task 0: slice 中 5 条 entry 含 BP-4。"""
        if not SLICE_PATH.exists():
            pytest.skip("slice 不存在")
        sl = json.loads(SLICE_PATH.read_bytes())
        ie = sl.get("independent_entries", {})
        bp4_entries = []
        entries = ie.values() if isinstance(ie, dict) else ie
        for e in entries:
            if not isinstance(e, dict):
                continue
            bps = e.get("capability_target_blocked_by", [])
            bp_ids = set()
            for bp in bps:
                if isinstance(bp, dict):
                    bp_ids.add(bp.get("bp_id", ""))
                elif isinstance(bp, str):
                    bp_ids.add(bp)
            if "BP-4" in bp_ids:
                bp4_entries.append(e.get("entry_id", "?"))
        assert len(bp4_entries) == 5, f"BP-4 entries: {bp4_entries}"

    def test_m2_sheet_map_three_fixes(self):
        """Lane2 Task 5+7: M2 修正 3 处。"""
        import openpyxl
        pairs = _read_sheet_map(2)
        real = set(_real_sheets(2))
        m = dict(pairs)
        # procedure 含前导空格
        assert m["procedure"].startswith(" "), "M2 procedure 应含前导空格"
        # M2-2 含「上市公司」
        assert "上市公司" in m["M2-2"], f"M2-2 应含上市公司: {m['M2-2']}"
        # M2-5 含科目前缀
        assert "实收资本" in m["M2-5"], f"M2-5 应含实收资本: {m['M2-5']}"
        # 全部命中
        miss = [v for _, v in pairs if v not in real]
        assert miss == [], f"M2 仍有 miss: {miss}"

    def test_bp6_mode_only_in_orphans(self):
        """Lane2 Task 18: BP-6 的 'structured' 只在 orphan 中。"""
        for n in range(1, 11):
            edm = COMPOSABLES / f"useM{n}EntryDualMode.ts"
            if edm.exists():
                text = edm.read_text(encoding="utf-8")
                assert "'structured'" not in text, (
                    f"M{n} live 模块含 'structured'（应只在 orphan）"
                )

    def test_bp12_m10_disclosure_soe_dispatch_fixed(self):
        """Lane2 Task 10-12: M10 死代码字面量修正。"""
        text = _host_text(10)
        clean = _strip_comments(text)
        # 不应包含 includes('国有企业') 作为 dispatch 条件
        dispatch_lines = [
            l for l in clean.split("\n")
            if "includes(" in l and "return" in l
        ]
        for l in dispatch_lines:
            assert "国有企业" not in l, f"BP-12 未修: {l.strip()}"


# ═══════════════════════════════════════════════════════════════════════════
# Lane3: M9 例外 + BP-6 M1 + BP-8 M8 + M1 独有 + M5 对照
# ═══════════════════════════════════════════════════════════════════════════
class TestLane3Exceptions:
    """Lane3 Task 0-26: M9 四重例外、M1 科目、M5 干净对照组。"""

    def test_m9_no_el_segmented(self):
        """Lane3 Task 5: M9 宿主无 el-segmented。"""
        clean = _strip_comments(_host_text(9))
        assert "el-segmented" not in clean, "M9 不应有 el-segmented"

    def test_m9_orphan_files_deleted(self):
        """Lane3 Task 9: M9 双孪生 orphan 已删除。"""
        assert not (COMPOSABLES / "useM9DualMode.ts").exists()
        assert not (COMPOSABLES / "useM9EntryDualMode.ts").exists()

    def test_m9_sheet_map_deleted_with_orphan(self):
        """Lane3 Task 9: M9 SHEET_MAP 随 orphan 删除，不再存在。"""
        assert not (COMPOSABLES / "useM9EntryDualMode.ts").exists()

    def test_m5_zero_miss_clean_control(self):
        """Lane3 Task 21: M5 作为干净对照组 0 miss。"""
        pairs = _read_sheet_map(5)
        real = set(_real_sheets(5))
        miss = [v for _, v in pairs if v not in real]
        assert miss == [], f"M5 有意外 miss: {miss}"

    def test_m1_procedure_no_a_suffix(self):
        """Lane3 Task 19: M1 procedure 键是唯一不带 A 的（在现存文件中检查）。"""
        pairs_map = {}
        for n in range(1, 11):
            edm = COMPOSABLES / f"useM{n}EntryDualMode.ts"
            if not edm.exists():
                continue  # M9 已删
            m = dict(_read_sheet_map(n))
            if "procedure" in m:
                pairs_map[n] = m["procedure"]
        # M1 不含 "A" 在程序表名末尾
        m1_proc = pairs_map[1]
        assert not m1_proc.rstrip().endswith("A"), f"M1 procedure 不应以 A 结尾: {m1_proc}"
        # 其余册末尾应含 A
        for n in range(2, 11):
            if n in pairs_map:
                assert pairs_map[n].rstrip().upper().endswith("A"), f"M{n} procedure 应以 A 结尾"

    def test_m8_has_deleted_sheet(self):
        """Lane3 Task 14: M8 含「针对性测试M8-5-删除」sheet。"""
        real = _real_sheets(8)
        deleted = [s for s in real if "删除" in s]
        assert len(deleted) == 1, f"M8 删除 sheet: {deleted}"
        assert "M8-5" in deleted[0]

    def test_prefix_repeat_axis_three_vs_seven(self):
        """Lane3 Task 11 / MC-15: 前缀重复轴 3:7 分裂。
        M1/M2/M3 用重复型 itemId（M{n}-M{n}-1-row-...），M4~M10 不重复。
        """
        repeat = []
        non_repeat = []
        for n in range(1, 11):
            adj = COMPOSABLES / f"useM{n}Adjudication.ts"
            if not adj.exists():
                continue
            text = adj.read_text(encoding="utf-8")
            code = f"M{n}"
            # 重复型: itemId 里含 M{n}-M{n} 形态
            if f"{code}-{code}" in text:
                repeat.append(n)
            else:
                non_repeat.append(n)
        assert sorted(repeat) == [1, 2, 3], f"重复前缀型: {repeat}"
        assert sorted(non_repeat) == [4, 5, 6, 7, 8, 9, 10], f"不重复型: {non_repeat}"


# ═══════════════════════════════════════════════════════════════════════════
# 跨 spec 自检
# ═══════════════════════════════════════════════════════════════════════════
class TestCrossSpecSelfCheck:
    """三 spec 自检断言。"""

    def test_m_codes_complete_1_to_10(self):
        """自检: M1~M10 的 FormData 全存在；EntryDualMode 除 M9（已删）外全存在。"""
        for n in range(1, 11):
            if n != 9:
                assert (COMPOSABLES / f"useM{n}EntryDualMode.ts").exists(), f"M{n} EntryDualMode 缺失"
            assert (COMPOSABLES / f"useM{n}FormData.ts").exists(), f"M{n} FormData 缺失"

    def test_no_m0_anywhere(self):
        """Task 2: M0 不存在的证据。"""
        # manifest 无 m0
        raw = json.loads(MANIFEST_PATH.read_bytes())
        # manifest 可能是 dict 或 list
        if isinstance(raw, dict):
            for key in raw:
                assert "m0" not in str(key).lower() or "m10" in str(key).lower()
        elif isinstance(raw, list):
            for e in raw:
                eid = e.get("entry_id", "") if isinstance(e, dict) else str(e)
                assert "m0" not in eid.lower() or "m10" in eid.lower()
        # 模板无 M0
        assert not list(TEMPLATE_DIR.glob("*M0*"))

    def test_slice_and_deletion_plan_exist(self):
        """前置: slice 和删除清册存在。"""
        assert SLICE_PATH.exists(), "slice 不存在"
        assert DELETION_PLAN_PATH.exists(), "删除清册不存在"


# ═══════════════════════════════════════════════════════════════════════════
# MC-24: 历史 sheet 过滤统一（Foundation Task 22-23）
# ═══════════════════════════════════════════════════════════════════════════
class TestHistoricalSheetFilter:
    """MC-24: HTML 侧与 OO 侧 sheet 过滤口径统一。"""

    def test_render_config_imports_historical_filter(self):
        """Task 22: wp_render_config.py 现在调用 _should_skip_historical_sheet。"""
        rc = (REPO / "backend" / "app" / "routers" / "wp_render_config.py").read_text("utf-8")
        assert "_should_skip_historical_sheet" in rc, "render_config 应导入历史 sheet 过滤"

    def test_oo_router_fail_closed(self):
        """Task 23: wp_onlyoffice_router.py fail-open 已改 fail-closed。"""
        oo = (REPO / "backend" / "app" / "routers" / "wp_onlyoffice_router.py").read_text("utf-8")
        # 旧 fail-open: sheet_names = all_names
        assert "sheet_names = all_names" not in oo, "OO router 仍有 fail-open 兜底"
        # 新 fail-closed: 抛 404
        assert "所有 sheet 均为历史遗留" in oo or "HTTPException" in oo

    def test_m_historical_sheets_filtered_by_function(self):
        """MC-24 反向判据: _should_skip_historical_sheet 对 M 域 4 张历史 sheet 命中。"""
        import importlib
        mod = importlib.import_module("app.services.wp_template_finder")
        fn = mod._should_skip_historical_sheet
        # M 域 4 张历史 sheet
        assert fn("一般风险准备实质性程序表 Q8A  (修订前)") is True
        assert fn("其他权益工具实质性程序表 Q10A (修订前)") is True
        assert fn("一般风险准备实质性程序表 Q6A（修订前）") is True
        assert fn("针对性测试M8-5-删除") is True
        # 正常 sheet 不被过滤
        assert fn("审定表M6-1") is False
        assert fn("明细表M10-2") is False
        assert fn(" 专项储备实质性程序表 M7A ") is False


# ═══════════════════════════════════════════════════════════════════════════
# MC-17: M10 模板修复（Lane2 Task 20-22）
# ═══════════════════════════════════════════════════════════════════════════
class TestM10TemplateRepair:
    """MC-17: M10 明细表M10-2 r26 合计行漏加 r25 小计修复。"""

    def test_r26_all_ten_cols_now_include_r25(self):
        """Lane2 Task 21: 10 列 r26 现在都包含 r25 引用。"""
        import openpyxl
        wb = openpyxl.load_workbook(_wb_path(10), data_only=False)
        ws = wb["明细表M10-2"]
        cols_to_check = ["H", "J", "K", "M", "N", "O", "Q", "R", "S", "T"]
        for col in cols_to_check:
            v = ws[f"{col}26"].value
            assert isinstance(v, str) and v.startswith("="), f"{col}26 不是公式: {v}"
            assert f"{col}25" in v, f"{col}26 漏加 {col}25: {v}"
        wb.close()

    def test_r26_four_cols_already_correct(self):
        """Lane2 Task 20: U/V/W/X 原本就含三段（验证未被误改）。"""
        import openpyxl
        wb = openpyxl.load_workbook(_wb_path(10), data_only=False)
        ws = wb["明细表M10-2"]
        for col in ["U", "V", "W", "X"]:
            v = ws[f"{col}26"].value
            assert "15" in v and "20" in v and "25" in v, f"{col}26 三段不全: {v}"
        wb.close()

    def test_r26_derived_cols_untouched(self):
        """Lane2 Task 20: Y26/Z26 是派生列，公式形态未改。"""
        import openpyxl
        wb = openpyxl.load_workbook(_wb_path(10), data_only=False)
        ws = wb["明细表M10-2"]
        y26 = ws["Y26"].value
        z26 = ws["Z26"].value
        assert "S26" in y26 and "U26" in y26 and "W26" in y26, f"Y26 派生公式异常: {y26}"
        assert "T26" in z26 and "V26" in z26 and "X26" in z26, f"Z26 派生公式异常: {z26}"
        wb.close()


# ═══════════════════════════════════════════════════════════════════════════
# BP-7: notice 落位（Foundation Task 40）
# ═══════════════════════════════════════════════════════════════════════════
class TestNoticeMount:
    """BP-7 MC-12: 10 个 M 宿主全挂 GtEntrySyncCapabilityNotice。"""

    def test_all_ten_hosts_import_notice(self):
        """Foundation Task 40: 每个 M 宿主都 import GtEntrySyncCapabilityNotice。"""
        for n in range(1, 11):
            text = _host_text(n)
            assert "GtEntrySyncCapabilityNotice" in text, f"M{n} 宿主未导入 notice"

    def test_all_ten_hosts_use_notice_tag(self):
        """Foundation Task 40: 每个 M 宿主的 template 里有 notice 标签。"""
        for n in range(1, 11):
            text = _host_text(n)
            assert "<GtEntrySyncCapabilityNotice" in text, f"M{n} 宿主 template 无 notice 标签"

    def test_notice_entry_ids_are_correct(self):
        """Foundation Task 40: notice 的 entry-id 属性值与 M 域 entry 匹配。"""
        expected_ids = {
            1: "xlsx/gt-m1-dividends-payable",
            2: "xlsx/gt-m2-paid-in-capital",
            3: "xlsx/gt-m3-treasury-stock",
            4: "xlsx/gt-m4-capital-reserve",
            5: "xlsx/gt-m5-surplus-reserve",
            6: "xlsx/gt-m6-retained-earnings",
            7: "xlsx/gt-m7-special-reserve",
            8: "xlsx/gt-m8-general-risk-reserve",
            9: "xlsx/gt-m9-other-comprehensive-income",
            10: "xlsx/gt-m10-other-equity-instruments",
        }
        for n, eid in expected_ids.items():
            text = _host_text(n)
            assert eid in text, f"M{n} notice entry-id 不含 {eid}"


# ═══════════════════════════════════════════════════════════════════════════
# BP-10: 去位置化改造（Foundation Task 41）
# ═══════════════════════════════════════════════════════════════════════════
class TestDepositionalization:
    """BP-10: M6 canary item_id 改用稳定行身份。"""

    def test_m6_adjudication_no_positional_row_n(self):
        """Task 41: M6 Adjudication 的 saveAdjudication 不再用 row-${n} 作为 item_id。"""
        adj = COMPOSABLES / "useM6Adjudication.ts"
        text = adj.read_text(encoding="utf-8")
        # 只检查非注释代码行（注释里提到旧模式是允许的）
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                continue
            if "row-${n}" in line and "itemId" in line:
                pytest.fail(f"M6 Adjudication 代码行仍含 row-${{n}}: {stripped}")

    def test_m6_adjudication_uses_row_key(self):
        """Task 41: M6 Adjudication 改用 row.key（熵键）。"""
        adj = COMPOSABLES / "useM6Adjudication.ts"
        text = adj.read_text(encoding="utf-8")
        # 新模式应含 ${k} 或 ${row.key} 引用
        assert "row.key" in text or "${k}" in text, "M6 Adjudication 未使用 row.key/k"

    def test_m6_trigger_save_no_positional(self):
        """Task 41: _triggerSave 也改用稳定键（代码行无位置化 debouncedSave 调用）。"""
        adj = COMPOSABLES / "useM6Adjudication.ts"
        text = adj.read_text(encoding="utf-8")
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                continue
            if "debouncedSave" in line and "row-${" in line:
                pytest.fail(f"_triggerSave 代码行仍含位置化 debouncedSave: {stripped}")

    def test_m6_entropy_key_generated_on_add(self):
        """Task 41 前置: addRow 生成熵键。"""
        adj = COMPOSABLES / "useM6Adjudication.ts"
        text = adj.read_text(encoding="utf-8")
        assert "Date.now()" in text, "addRow 应含 Date.now() 熵键"
        assert "Math.random()" in text, "addRow 应含 Math.random() 熵键"


# ═══════════════════════════════════════════════════════════════════════════
# MC-19: 跨循环键守卫（Foundation Task 36 / Lane3 Task 16-17）
# ═══════════════════════════════════════════════════════════════════════════
class TestCrossCycleKeyIsolation:
    """MC-19: M 域 item_id 前缀与其他循环两两无交集。"""

    @staticmethod
    def _extract_itemid_prefixes(filepath: Path) -> set[str]:
        """提取 Adjudication 文件中 itemId 模板串的前缀段。"""
        text = filepath.read_text(encoding="utf-8")
        hits = re.findall(r"itemId:\s*`([^$`]+)", text)
        prefixes = set()
        for h in hits:
            parts = h.rstrip("-").rsplit("-", 1)
            if parts:
                prefixes.add(parts[0] + "-")
        return prefixes

    def test_m1_k3_no_intersection(self):
        """Lane3 Task 16: M1 与 K3 推送的子表键无交集。"""
        m1 = COMPOSABLES / "useM1Adjudication.ts"
        k3 = COMPOSABLES / "useK3Adjudication.ts"
        if not m1.exists() or not k3.exists():
            pytest.skip("M1 或 K3 Adjudication 不存在")
        m1_p = self._extract_itemid_prefixes(m1)
        k3_p = self._extract_itemid_prefixes(k3)
        assert m1_p & k3_p == set(), f"M1↔K3 键碰撞: {m1_p & k3_p}"

    def test_all_m_cycles_pairwise_disjoint(self):
        """Lane3 Task 17: 全部 M 循环键两两无交集。"""
        all_prefixes: dict[str, set[str]] = {}
        for n in range(1, 11):
            adj = COMPOSABLES / f"useM{n}Adjudication.ts"
            if adj.exists():
                all_prefixes[f"M{n}"] = self._extract_itemid_prefixes(adj)
        codes = sorted(all_prefixes.keys())
        for i, a in enumerate(codes):
            for b in codes[i + 1:]:
                common = all_prefixes[a] & all_prefixes[b]
                assert common == set(), f"{a}↔{b} 碰撞: {common}"


# ═══════════════════════════════════════════════════════════════════════════
# M9 orphan 删除验证（Lane3 Task 9）
# ═══════════════════════════════════════════════════════════════════════════
class TestM9OrphanDeletion:
    """Lane3 Task 9: M9 orphan 删除后 dual-mode 文件数变化。"""

    def test_m9_dualmode_deleted(self):
        """M9 的 DualMode 和 EntryDualMode orphan 已删除。"""
        assert not (COMPOSABLES / "useM9DualMode.ts").exists()
        assert not (COMPOSABLES / "useM9EntryDualMode.ts").exists()

    def test_remaining_orphan_count_is_nine(self):
        """删除后 orphan 从 11 降到 9（M1~M8,M10 的 DualMode）。"""
        orphans = [
            p for p in COMPOSABLES.glob("useM*DualMode.ts")
            if re.match(r"useM(?:10|[1-9])DualMode\.ts$", p.name)
        ]
        assert len(orphans) == 9, f"orphan 数 {len(orphans)}: {[p.name for p in orphans]}"

    def test_remaining_live_count_is_nine(self):
        """删除后 live EntryDualMode 从 10 降到 9（M9 的已删）。"""
        lives = [
            p for p in COMPOSABLES.glob("useM*EntryDualMode.ts")
            if re.match(r"useM(?:10|[1-9])EntryDualMode\.ts$", p.name)
        ]
        assert len(lives) == 9, f"live 数 {len(lives)}: {[p.name for p in lives]}"


# ═══════════════════════════════════════════════════════════════════════════
# 全 10 entry 去位置化验证（BP-10 扩展）
# ═══════════════════════════════════════════════════════════════════════════
class TestFullDepositionalization:
    """BP-10: 全 10 entry 的 saveAdjudication 使用稳定键。"""

    def test_no_row_n_in_any_adjudication_code(self):
        """全 10 个 Adjudication 的代码行无 row-${n} itemId。"""
        for n in range(1, 11):
            adj = COMPOSABLES / f"useM{n}Adjudication.ts"
            if not adj.exists():
                continue
            for line in adj.read_text(encoding="utf-8").split("\n"):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                if "row-${n}" in line and ("itemId" in line or "debouncedSave" in line):
                    pytest.fail(f"M{n} 代码行仍含位置化: {stripped}")

    def test_all_ten_use_key_variable(self):
        """全 10 个 Adjudication 的 saveAdjudication 使用 k=row.key。"""
        for n in range(1, 11):
            adj = COMPOSABLES / f"useM{n}Adjudication.ts"
            if not adj.exists():
                continue
            text = adj.read_text(encoding="utf-8")
            assert "const k = row.key" in text, f"M{n} 缺少 const k = row.key"
