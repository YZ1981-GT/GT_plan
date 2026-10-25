# -*- coding: utf-8 -*-
"""N2 / N5 整表 JSON 行身份与跨 entry 只读 —— lane3 守卫。

spec: `.kiro/specs/n2-n5-json-table-identity-and-cross-entry-readonly`
Properties: NB-P1 ~ NB-P22 · 共同判据只引 NC 编号（判据正文在 foundation）

口径与基线全部复用 foundation 的扫描器 `n_cycle_scanner.py` 与 `n_cycle_facts.py`，
本文件不另写第二份口径。

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_lane3_json_table_identity.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.analyze import n_cycle_scanner as S  # noqa: E402
from tests.workpaper_sync import n_cycle_facts as F  # noqa: E402

C = S.WP_COMPOSABLES
W = S.WP_COMPONENTS
N2_WB = F.ENTRY_WORKBOOKS[F.N2]
N5_WB = F.ENTRY_WORKBOOKS[F.N5]


def _eq(label, computed, expected) -> None:
    assert computed == expected, f"{label}: 现算 {computed!r} ≠ 基线 {expected!r}"


def _code(path: Path) -> str:
    return S.strip_comments(S.read_text(path))


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return S.load_json(S.SLICE_PATH)


@pytest.fixture(scope="module")
def tf() -> S.TemplateFacts:
    return S.collect_template_facts()


@pytest.fixture(scope="module")
def prod_files():
    return S.production_files(S.scan_domain_files())


# ═══ Task 1 · 归属基线（NB-P1 ~ NB-P3 · NC-1 · NC-22） ═══════════════════════
class TestLane3Attribution:
    def test_entries_and_account_nature(self) -> None:
        _eq("lane3 entry", F.LANE3_ENTRIES, (F.N2, F.N5))
        # NB-P1：科目跨类 —— 2221 负债/贷 vs 6801 损益/借
        _eq("N2", F.ENTRY_ACCOUNTS[F.N2][1:], ("2221", "负债", "贷"))
        _eq("N5", F.ENTRY_ACCOUNTS[F.N5][1:], ("6801", "损益", "借"))

    def test_bp_counts_and_members(self, slice_doc) -> None:
        """NB-P2：BP 数 N2 8 / N5 10，且 BP-12 只属 N5、BP-8 两者都有。"""
        per = {e["entry_id"]: e["capability_target_blocked_by"] for e in slice_doc["independent_entries"]}
        _eq("N2 BP", len(per[F.N2]), 8)
        _eq("N5 BP", len(per[F.N5]), 10)
        assert "BP-12" in per[F.N5] and "BP-12" not in per[F.N2]
        assert "BP-8" in per[F.N2] and "BP-8" in per[F.N5]

    def test_majority_share(self, tf) -> None:
        """NB-P3：三项过半 —— sheets 34/59 · 公式格 1194/2185 · 带 fx 30/49。"""
        mine = [f for f in tf.sheets if f.workbook in (N2_WB, N5_WB)]
        _eq("sheets", len(mine), 34)
        _eq("公式格", sum(f.formula_cells for f in mine), 1194)
        _eq("带 fx", sum(1 for f in mine if f.formula_cells), 30)
        assert len(mine) * 2 > F.TOTAL_SHEETS


# ═══ Task 2 / 3 · BP-12 跨 entry 只读契约（NB-P4 ~ NB-P8 · NC-19 · NC-5） ═════
class TestCrossEntryReadOnly:
    def test_eight_foreign_keys_locked(self) -> None:
        """NB-P4：8 键跨 5 命名空间，新增/删除显式失败。"""
        text = _code(C / "useN5CrossSheet.ts")
        found = sorted(set(re.findall(r"'((?:A|I2|I6|N1|N3)-[A-Za-z0-9-]+)'", text)))
        _eq("外引键", tuple(found), tuple(sorted(F.N5_FOREIGN_READONLY_KEYS)))

    def test_no_write_into_foreign_namespaces(self) -> None:
        """NB-P5：🔴 对 5 个外部命名空间无任何写入路径（只读单向）。"""
        text = _code(C / "useN5CrossSheet.ts")
        writes = re.findall(r"(?:_persistCrossData|saveField|debouncedSave|item_id:)\s*\(?\s*'([^']+)'", text)
        bad = [w for w in writes if w.split("-")[0] + "-" in F.N5_FOREIGN_NAMESPACES]
        _eq("对外写入", bad, [])
        assert writes, "一个写站点都没扫到 ⇒ 判据空跑"
        _eq("N5 自有写键", sorted(set(w for w in writes if w.startswith("N5-cross-"))),
            sorted(F.N5_CROSS_WRITE_KEYS))

    def test_n_keys_referenced_from_outside(self) -> None:
        """NB-P6/P7：N 键被外部引用的一侧（双向都要登记）。"""
        refs = {
            C / "nCycleTaxConsistency.ts": 10,
        }
        for path, expected in refs.items():
            hits = len(re.findall(r"'N[1-5]-[^']+'", _code(path)))
            assert hits >= expected, (path.name, hits)

    def test_nCycle_file_needs_ref_branch(self) -> None:
        """🔴 `nCycleTaxConsistency.ts` 连 `^n[1-5]` 都不匹配 ⇒ 文件集判据须三路取并（NC-5）。"""
        assert not re.match(r"^n[1-5]", "nCycleTaxConsistency.ts")
        hit = [f for f in S.scan_domain_files() if f.name == "nCycleTaxConsistency.ts"]
        assert hit and "ref" in hit[0].branches

    def test_key_counts_per_entry(self, slice_doc) -> None:
        """NB-P8：N5 10 键（含 5 cross）· N2 7 键。"""
        decls = {d["id"]: d for d in slice_doc["transport_key_resolution"]["declarations"]}
        _eq("N5 键", len(decls["TK-6"]["keys"]), 10)
        _eq("N5 cross", sum(1 for k in decls["TK-6"]["keys"] if "-cross-" in k), 5)
        _eq("N2 键", len(decls["TK-3"]["keys"]), 7)


# ═══ Task 4 · 行身份改造（NB-P9 / NB-P10 · NC-6 · NC-7） ══════════════════════
_LANE3_TABLES = {
    "useN5TaxAdjustment.ts": ("removeRow", "updateRow"),
    "useN5DeferredReconcile.ts": ("removeRow", "updateRow"),
    "useN5RdSuperDeduction.ts": ("removeProject", "updateRow"),
    "useN2OtherTaxCalc.ts": (None, "updateManualRow"),
}


class TestLane3RowIdentity:
    @pytest.mark.parametrize("name", sorted(_LANE3_TABLES))
    def test_tables_address_rows_by_identity(self, name) -> None:
        """NB-P9：增删改按 rowKey 寻址，`rowIndex` / 按下标 filter 全部消失。"""
        text = _code(C / name)
        remove, update = _LANE3_TABLES[name]
        if remove:
            assert re.search(rf"function {remove}\(rowKey: StableRowKey\)", text), name
        assert re.search(rf"function {update}\(\s*rowKey: StableRowKey", text), name
        assert "rowIndex" not in text, f"{name} 残留 rowIndex"
        assert not re.search(r"\.filter\(\(\s*_?\w*,\s*i\s*\)\s*=>\s*i\s*!==", text), f"{name} 残留按下标 filter"
        assert "stableRowIdentity" in text, f"{name} 没走正面样板（禁自建新范式）"

    def test_row_type_carries_identity(self) -> None:
        for name in _LANE3_TABLES:
            text = _code(C / name)
            assert re.search(r"rowKey: StableRowKey", text), name

    def test_render_key_family_cleared(self) -> None:
        """N2-8 的 `manual-${idx}` 位置化渲染键（A' 族唯一一处）消失。"""
        src = {"x": _code(C / "useN2OtherTaxCalc.ts")}
        _eq("A' 族", S.scan_row_identity_families(src)["A2_positional_render_key"], [])

    def test_tabs_pass_row_identity_not_template_index(self) -> None:
        """模板侧：改传 `row.rowKey`，不再传过滤/分组子表里的行下标。"""
        for rel in ("n5/calc/N5TabTaxAdjustment.vue", "n5/calc/N5TabDeferredReconcile.vue",
                    "n5/benefit/N5TabRdSuperDeduction.vue"):
            text = _code(W / rel)
            assert "row.rowKey" in text, rel
            assert not re.search(r"handle\w*\(\$index", text), f"{rel} 仍传 $index"

    def test_n2_8_component_uses_current_row_model(self) -> None:
        """真浏览器回归：组件不得再引用已从 composable 删除的月度/季度 API。"""
        text = _code(W / "n2" / "calc" / "N2TabOtherTaxCalc.vue")
        assert "otherTaxCalc.allCalcRows.value" in text
        for obsolete in ("monthlyRows", "quarterSummaries", "exemptMonths", "setMonthlyData"):
            assert obsolete not in text, f"N2-8 残留已废弃 API {obsolete}"
        assert "removeManualRow(row.key)" in text
        # 页面不再重复发布第二种不合契约的 tax-accrual 载荷；发布唯一归 composable。
        assert "eventBus.emit('tax-accrual:updated'" not in text
        calc = _code(C / "useN2OtherTaxCalc.ts")
        for field in ("accruals:", "totalAccrual:", "timestamp:"):
            assert field in calc, field

    def test_by_index_monotone_down(self, prod_files) -> None:
        """NB-P10：by_index 单调降（相对动手前基线）。"""
        hist = S.remove_call_histogram(S.scan_remove_row_calls(S.stripped_sources(prod_files)))
        assert hist["by_index"] < F.REMOVE_HISTOGRAM_BEFORE["by_index"], hist

    def test_frontend_roundtrip_spec_exists(self) -> None:
        text = S.read_text(C / "__tests__" / "nCycleLane3RowIdentity.spec.ts")
        for marker in ("删中间行", "资本化子表", "旧数据（无身份、按位置存）"):
            assert marker in text, marker


# ═══ Task 5 · transport_key（NB-P11 / NB-P12 · NC-30） ════════════════════════
class TestLane3TransportKeys:
    def test_single_owner_each(self) -> None:
        for name, prefix in (("useN2FormData.ts", "N2-"), ("useN5FormData.ts", "N5-")):
            text = _code(C / name)
            _eq(f"{name} owner", len(re.findall(r"ITEM_PREFIX\s*=\s*'", text)), 1)
            assert f"ITEM_PREFIX = '{prefix}'" in text

    def test_guessed_keys_are_zero(self, prod_files) -> None:
        src = S.stripped_sources(prod_files)
        for k in ("N2-1-rows", "N5-1-rows", "N5-5-rows"):
            _eq(k, [s for q in "'\"`" for s in S.scan_literal(src, f"{q}{k}{q}")], [])
        assert S.scan_literal(src, "'N5-5-adjustment-rows'"), "真实键 0 ⇒ 扫描空跑"


# ═══ Task 6 / 7 · inert 修复与薄封装（NB-P13 ~ NB-P16 · NC-13 · NC-11） ═══════
class TestLane3Carriers:
    def test_n5_inert_fixed_with_foundation_form(self) -> None:
        """NB-P13：N5 与 N4 用同一已验证形态（空实现消失 + 统一能力层 + 显式回落）。"""
        n4 = _code(W / "GtN4TaxesAndSurcharges.vue")
        n5 = _code(W / "GtN5IncomeTaxExpense.vue")
        for t in (n4, n5):
            assert "onModeChange: () => {}" not in t
            assert "fetchOnlyOfficeHealthy(true)" in t
            assert "已保持 HTML 模式" in t
        assert F.N5 in F.REDEEMED_SWITCH_ENTRIES

    def test_n5_mode_options_stays_plain_array(self) -> None:
        """NB-P14：`modeOptions` 保持普通数组（模板里不带 `.value`）。"""
        n5 = S.read_text(W / "GtN5IncomeTaxExpense.vue")
        assert ':options="dualMode.modeOptions"' in n5
        assert ':options="dualMode.modeOptions.value"' not in n5

    def test_n2_thin_wrapper_kept_and_edge_counted(self, ) -> None:
        """NB-P15：N2 薄封装**保留**（评估结论：移除只省 17 行却要改宿主载体，收益低于风险）。

        🔴 保留 ⇒ 共享基类 N 域边仍 1 条（不得把「移除后 −1」当已发生）。
        """
        wrapper = C / "useN2DualMode.ts"
        assert wrapper.is_file()
        assert S.count_lines(S.read_text(wrapper)) <= 20
        g = S.build_import_graph()
        m = S.module_reachability([C / "useWorkpaperEntryDualMode.ts"], g)[0]
        n_edges = [c for c in m.production_consumers if "useN2DualMode" in c]
        _eq("N 域边", len(n_edges), F.SHARED_BASE_N_EDGES)

    def test_bp10_is_empty_denominator_for_lane3(self) -> None:
        """NB-P16：🔴 BP-10 对本 spec 空分母（N2/N5 已采用共享路由），禁写「已验证正常」。"""
        for name in ("n2SheetRouting.ts", "n5SheetRouting.ts"):
            assert "makeCycleSheetRouter" in _code(C / name), name
        _eq("BP-10 成员", F.BP_DISCRIMINATING["BP-10"], (F.N1, F.N3))


# ═══ Task 8 / 9 / 10 · 确认门异形、契约双列、真库（NB-P17 ~ NB-P20） ═════════
class TestLane3GatesAndPayload:
    def test_confirm_gate_tolerates_missing_composable(self, prod_files) -> None:
        """NB-P17：`useN5Adjudication.ts` 不存在，confirm 在 `N5TabAdjudication.vue`。"""
        assert not (C / "useN5Adjudication.ts").exists()
        code, _ = S.count_literal_code_vs_comment(prod_files, "ElMessageBox.confirm")
        assert any(s.rel.endswith("n5/core/N5TabAdjudication.vue") for s in code)
        assert any("/n2/" in s.rel or "useN2" in s.rel for s in code)

    def test_publish_gate_lane3_two_sites(self, prod_files) -> None:
        """NB-P18：发布门本 spec 2 处（N2 / N5 FormData），不新增第 3 处；与确认门交集 0。"""
        pub, _ = S.count_literal_code_vs_comment(prod_files, F.PUBLISH_TO_TB_LITERAL)
        mine = sorted(Path(s.rel).name for s in pub if re.search(r"useN[25]FormData", s.rel))
        _eq("lane3 发布门", mine, ["useN2FormData.ts", "useN5FormData.ts"])
        conf, _ = S.count_literal_code_vs_comment(prod_files, "ElMessageBox.confirm")
        _eq("交集", {s.rel for s in pub} & {s.rel for s in conf}, set())

    def test_payload_dual_column_in_lane3_readers(self) -> None:
        """NB-P19：lane3 行表读取一律走双列取列规则（实际非空列优先）。"""
        for name in ("useN5TaxAdjustment.ts", "useN5DeferredReconcile.ts",
                     "useN5RdSuperDeduction.ts", "useN2OtherTaxCalc.ts"):
            text = _code(C / name)
            assert "payloadJson(" in text, name
            assert not re.search(r"if \(resp\?\.conclusion\)\s*\{\s*try \{ raw = JSON\.parse", text), name

    def test_review_session_rows_are_excluded_before_parse(self) -> None:
        """NB-P19：AI 会话键白名单在解析**前**生效。"""
        text = _code(C / "shared" / "checklistPayload.ts")
        pick = text[text.find("export function pickPayload"):]
        assert pick.find("isReviewSessionKey") < pick.find("JSON") or "JSON" not in pick

    def test_soe_sheet_name_kept_literal(self, tf) -> None:
        """🔴 N5 国企版 sheet 名缺右括号须按原始字面量匹配，禁补括号。"""
        names = {f.sheet for f in tf.sheets if f.workbook == N5_WB}
        assert "附注披露信息（国企" in names and "附注披露信息（国企）" not in names
        assert "国企" in _code(C / "shared" / "cycleSheetRouting.ts"), "SOE 判定不再用包含「国企」"

    def test_cross_workpaper_resolution_uses_real_endpoint(self) -> None:
        """Playwright 抓到旧 `/projects/{pid}/wp-index/by-code/*` 恒 404；生产代码必须清零。"""
        for name in ("useN4CrossSheet.ts", "useN5CrossSheet.ts"):
            text = _code(C / name)
            assert "resolveWorkpaperByCode" in text, name
            assert "/wp-index/by-code/" not in text, name
        resolver = _code(S.FRONTEND / "services" / "resolveWorkpaperByCode.ts")
        assert "'/api/custom-query/wp-id-by-code'" in resolver

    def test_empty_n2_does_not_overwrite_persisted_n4_cross_data(self) -> None:
        """旧端点修好后暴露：N2 无行时曾无条件写 `{}` 覆盖历史；现在只有 read>0 才持久化。"""
        text = _code(C / "useN4CrossSheet.ts")
        assert "if (read > 0) _persistN2AccrualData()" in text
        assert "_persistN2AccrualData()\n    }" not in text

    def test_n5_cross_fetch_uses_real_resolver_for_all_five_upstreams(self) -> None:
        """N5 的 N1/N3/I6/I2/A 五路取数不再打恒 404 的死端点。"""
        text = _code(C / "useN5CrossSheet.ts")
        assert "/wp-index/by-code/" not in text
        for code in ("N1", "N3", "I6", "I2", "A"):
            assert f"resolveWorkpaperByCode(pid, '{code}')" in text, code

    def test_live_db_lane3_rows(self) -> None:
        """NB-P20（现算）：真库 lane3 归属行数与污染。design 记 10 行 / 污染 2，现算 3 / 0。"""
        from tests.workpaper_sync.test_n_cycle_foundation_canary import _live_db_rows

        rows = _live_db_rows()
        mine = [r for r in rows if r["item_id"].startswith(("N2-", "N5-"))]
        _eq("lane3 真库行", len(mine), 3)
        bad = [r for r in mine if not (r["wp_code"] or "").startswith(r["item_id"][:2])]
        _eq("污染", bad, [])


# ═══ Task 11 ~ 13 · 模板缺陷登记（记录型，不改 .xlsx）（NB-P21 / NB-P22） ═════
class TestLane3TemplateDefects:
    def test_a1_two_defects_in_n5(self, tf) -> None:
        a1 = sorted((h.sheet, h.cell) for h in tf.overflow
                    if h.family == "A1_real_defect" and h.workbook == N5_WB)
        _eq("N5 A1", a1, [("加计扣除研发费用情况明细表N5-6-1", "E12"), ("递延所得税费用核对表N5-8", "H12")])

    @pytest.mark.parametrize("sheet,cell,formula,pattern,expected", [
        ("加计扣除研发费用情况明细表N5-6-1", "E12", "=C12+N5", r"^=C(\d+)\+D\1$", 37),
        ("递延所得税费用核对表N5-8", "H12", "=C12-B12+N5-E12-F12+G12",
         r"^=C(\d+)-B\1\+D\1-E\1-F\1\+G\1$", 28),
    ])
    def test_a1_reverse_denominators(self, sheet, cell, formula, pattern, expected) -> None:
        """反向分母 37:1 / 28:1（同列正确形态行数）。"""
        wb = S.load_workbook(S.N_TEMPLATE_DIR / N5_WB)
        try:
            ws = wb[sheet]
            _eq(cell, ws[cell].value, formula)
            col = re.match(r"[A-Z]+", cell).group(0)
            ok = sum(1 for r in range(1, (ws.max_row or 0) + 1)
                     if isinstance(ws[f"{col}{r}"].value, str)
                     and re.match(pattern, ws[f"{col}{r}"].value.replace(" ", "")))
            _eq(f"{sheet} 反向分母", ok, expected)
        finally:
            wb.close()

    def test_n5_8_total_row_is_contaminated(self) -> None:
        """🔴 连带影响：N5-8 r39 合计 `=SUM(H10:H38)` 因 H12 恒空而连带错（全域唯一）。"""
        wb = S.load_workbook(S.N_TEMPLATE_DIR / N5_WB)
        try:
            _eq("H39", wb["递延所得税费用核对表N5-8"]["H39"].value, "=SUM(H10:H38)")
        finally:
            wb.close()

    def test_no_a2_in_lane3(self, tf) -> None:
        """本 spec 无族 A2（空分母声明）。"""
        _eq("lane3 A2", [h for h in tf.overflow if h.family == "A2_structural_residue"
                         and h.workbook in (N2_WB, N5_WB)], [])

    def test_footer_and_dirty_literals(self, tf) -> None:
        """NB-P22：footer 缺斜杠 2 处 · 外来码 O1A（N2 册）· 出口退税示例 visible。"""
        miss = sorted((f.workbook, f.sheet) for f in tf.sheets
                      if f.workbook in (N2_WB, N5_WB)
                      and S.classify_footer(f.footer_raw) == S.FOOTER_FORM_MISSING_SLASH)
        _eq("缺斜杠", miss, [(N2_WB, "出口退税额复核示例"), (N5_WB, "所得税审计程序表N3A (原底稿)")])
        n2 = {f.sheet: f for f in tf.sheets if f.workbook == N2_WB}
        assert any("O1A" in s for s in n2)
        assert n2["出口退税额复核示例"].hidden is False, "visible 口径前提变了"

    def test_defined_names_n2_and_empty_n5(self, tf) -> None:
        """N2 24 / broken 14（现算；design 记 15）· 🔴 N5 0/0 ⇒ 空分母，禁写「已验证无断链」。"""
        n2 = [d for d in tf.defined_names if d.workbook == N2_WB]
        n5 = [d for d in tf.defined_names if d.workbook == N5_WB]
        _eq("N2", (len(n2), sum(d.broken for d in n2)), F.DEFINED_NAME_PER_WORKBOOK[N2_WB])
        _eq("N5", len(n5), 0)

    def test_wide_sheet_and_total_label_in_b(self, tf) -> None:
        wide = [f for f in S.wide_sheets(tf.sheets) if f.workbook == N5_WB]
        _eq("N5 超宽", [(f.sheet, f.max_col - f.last_value_col) for f in wide], [("附注披露信息（国企", 251)])
        b = [t for t in tf.total_labels if t.col != "A"]
        _eq("非 A 列标签", [(t.workbook, t.sheet, t.row, t.col) for t in b],
            [(N5_WB, "纳税调整明细表N5-5", 63, "B")])

    def test_subtraction_candidates_not_strict(self, tf) -> None:
        """倒挤形态候选严格口径 0：N5-8 H10~H38 / N2-6 F39 / N5-1 B8 均为正常业务。"""
        strict = [s for s in tf.sub_chain_strict if s.workbook in (N2_WB, N5_WB)]
        _eq("严格", strict, [])
        cands = {(s.sheet, s.cell) for s in tf.sub_chain_candidates if s.workbook in (N2_WB, N5_WB)}
        assert ("递延所得税费用核对表N5-8", "H10") in cands, "候选扫描没跑到 N5-8"


# ═══ Task 14 / 15 · orphan 删除与 N3A 跨册碰撞 ══════════════════════════════
class TestLane3OrphansAndCollision:
    def test_lane3_orphans(self) -> None:
        """Task 14：三个 orphan 的归属与处置（见 n_cycle_facts.DELETED_ORPHANS）。"""
        for name in F.ORPHAN_OWNED_BY_LANE3:
            rel = (C / name).relative_to(S.ROOT).as_posix()
            if rel in F.DELETED_ORPHANS:
                assert not (C / name).exists(), name
            else:
                g = S.build_import_graph()
                m = S.module_reachability([C / name], g)[0]
                assert m.is_orphan, f"{name} 未删且有了消费方 ⇒ 不再是 orphan"

    def test_n3a_collision_by_workbook_and_sheet(self, tf) -> None:
        """🔴 按 (册, sheet 名) 二元组定位，禁仅按码；对端断言见 lane2
        `test_n_lane2_host_inline_router.py::TestLane2Collision`。"""
        pairs = sorted((f.workbook, f.sheet) for f in tf.sheets if "N3A" in f.sheet)
        _eq("N3A", pairs, [
            ("N3 递延所得税负债.xlsx", "递延所得税负债审计程序表的N3A"),
            (N5_WB, "所得税审计程序表N3A (原底稿)"),
        ])

    def test_original_sheet_three_forms(self, tf) -> None:
        """「原底稿」三形态各不同（禁单一分隔符假设）；本 spec 占 2 张。"""
        orig = sorted((f.workbook, f.sheet) for f in tf.sheets if "原底稿" in f.sheet)
        _eq("原底稿", orig, [
            (N2_WB, "应交税费审计程序表O1A （原底稿）"),
            ("N4 税金及附加.xlsx", "税金及附加审计程序表O2A（原底稿）"),
            (N5_WB, "所得税审计程序表N3A (原底稿)"),
        ])

    def test_two_clean_program_sheets_both_here(self, tf) -> None:
        clean = sorted(f.sheet for f in tf.sheets
                       if re.search(r"审计程序表N\dA$", f.sheet) and "的" not in f.sheet)
        _eq("净程序表", clean, ["应交税费审计程序表N2A", "所得税审计程序表N5A"])
