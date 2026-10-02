# -*- coding: utf-8 -*-
"""N1 / N3 宿主内联路由与共享路由采纳 —— lane2 守卫。

spec: `.kiro/specs/n1-n3-host-inline-router-and-shared-adoption`
Properties: NA-P1 ~ NA-P22 · 共同判据只引 NC 编号（判据正文在 foundation）

口径与基线复用 `n_cycle_scanner.py` / `n_cycle_facts.py`，不另写第二份。

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_lane2_host_inline_router.py -q
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
N1_HOST = W / "GtN1DeferredTaxAssets.vue"
N3_HOST = W / "GtN3DeferredTaxLiabilities.vue"
N1_WB = F.ENTRY_WORKBOOKS[F.N1]
N3_WB = F.ENTRY_WORKBOOKS[F.N3]


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
def graph():
    return S.build_import_graph()


@pytest.fixture(scope="module")
def prod_files():
    return S.production_files(S.scan_domain_files())


# ═══ Task 1 · 归属基线（NA-P1 / NA-P2 · NC-1 · NC-22） ═══════════════════════
class TestLane2Attribution:
    def test_entries_and_opposite_directions(self) -> None:
        _eq("lane2", F.LANE2_ENTRIES, (F.N1, F.N3))
        _eq("N1", F.ENTRY_ACCOUNTS[F.N1][1:], ("1811", "资产", "借"))
        _eq("N3", F.ENTRY_ACCOUNTS[F.N3][1:], ("2901", "负债", "贷"))

    def test_bp_members(self, slice_doc) -> None:
        per = {e["entry_id"]: e["capability_target_blocked_by"] for e in slice_doc["independent_entries"]}
        _eq("N1 BP", len(per[F.N1]), 9)
        _eq("N3 BP", len(per[F.N3]), 9)
        assert "BP-4" in per[F.N3] and "BP-4" not in per[F.N1]
        assert "BP-10" in per[F.N1] and "BP-10" in per[F.N3]

    def test_attribution_shares(self, tf) -> None:
        """归属份额：sheets 16 / 公式格 755 / 带 fx 12（与 foundation 算术表同行）。"""
        mine = [f for f in tf.sheets if f.workbook in (N1_WB, N3_WB)]
        _eq("sheets", len(mine), 16)
        _eq("公式格", sum(f.formula_cells for f in mine), 755)
        _eq("带 fx", sum(1 for f in mine if f.formula_cells), 12)


# ═══ Task 2 / 3 · BP-10 收口 + 门控语义保留（NA-P3 ~ NA-P6 · NC-10 · NC-13） ═══
class TestLane2SharedRouter:
    @pytest.mark.parametrize("name", ["n1SheetRouting.ts", "n3SheetRouting.ts"])
    def test_routing_modules_use_shared_router(self, name) -> None:
        """NA-P3：沿用 n2/n4/n5SheetRouting 形态，经 `makeCycleSheetRouter`。"""
        text = _code(C / name)
        assert "makeCycleSheetRouter" in text and "./shared/cycleSheetRouting" in text

    def test_hosts_use_routing_modules_not_inline_regex(self) -> None:
        n1 = _code(N1_HOST)
        n3 = _code(N3_HOST)
        assert "normalizeN1SheetName" in n1 and "isN1HtmlSheet" in n1
        assert "normalizeN3SheetName" in n3 and "isN3HtmlSheet" in n3
        assert not re.search(r"name\.match\(/N1-\[1-5\]/\)", n1), "N1 仍有内联 wp_code 正则"
        assert not re.search(r"name\.match\(/\(N3A\|N3-", n3), "N3 仍有内联 wp_code 正则"

    def test_adopters_now_five(self, graph) -> None:
        """采用方 3 → 5，BP-10 成员集变空。"""
        m = S.module_reachability([C / "shared" / "cycleSheetRouting.ts"], graph)[0]
        adopters = sorted(Path(c).name for c in m.production_consumers
                          if re.search(r"/n[1-5]SheetRouting\.ts$", c))
        _eq("采用方", adopters, [f"n{i}SheetRouting.ts" for i in range(1, 6)])
        _eq("采用方数", len(adopters), F.SHARED_ROUTER_ADOPTERS_AFTER)

    def test_routing_modules_reachable_from_hosts(self, graph) -> None:
        for name, host in (("n1SheetRouting.ts", N1_HOST), ("n3SheetRouting.ts", N3_HOST)):
            m = S.module_reachability([C / name], graph)[0]
            assert any(c.endswith(host.name) for c in m.production_consumers), name

    def test_n1_gate_semantics_preserved(self) -> None:
        """NA-P4：🔴 N1 保留 `isSwitchableSheet && dualMode.isOnlyOffice.value`（不得换成 isHtmlSheet）。"""
        n1 = S.read_text(N1_HOST)
        assert 'v-if="isSwitchableSheet && dualMode.isOnlyOffice.value"' in n1

    def test_n3_gate_keeps_three_conditions(self) -> None:
        """NA-P5：🔴 N3 保留三条件门控（不得简化为两条件）。"""
        n3 = S.read_text(N3_HOST)
        assert "isHtmlSheet && renderMode === 'onlyoffice' && ooHealthy" in n3

    def test_gate_variant_recognition(self) -> None:
        """NA-P6：识别带泛型 ref 与 isOnlyOffice 计算属性两种变体（NC-13）。"""
        assert re.search(r"ref<'html'\s*\|\s*'onlyoffice'>\(", _code(N3_HOST))
        assert re.search(r"const\s+isOnlyOffice\s*=\s*computed", _code(C / "useN1DualMode.ts"))


# ═══ Task 4 / 5 / 6 / 7 · health / 拒切提示 / config / 三值载体（NA-P7 ~ NA-P11） ═══
class TestLane2Capability:
    def test_n3_health_through_capability_layer(self) -> None:
        """NA-P8 / BP-4：N3 宿主不再直调 health 端点。"""
        n3 = _code(N3_HOST)
        assert "fetchOnlyOfficeHealthy" in n3
        assert "onlyoffice/health" not in n3

    def test_health_code_hits_shrink_to_capability_layer(self, prod_files) -> None:
        """🔴 spec 写「收敛后 health 命中仍为 5（不增不减）」—— 那是改线**前**每 entry 一处的形态。

        现算：N 域生产代码 0 处直调，全部经 `sync/onlyOfficeHealth.ts`（N 域外、唯一实现）。
        与 spec 原文不一致处已登记（见 tasks.md 实施记录）：收敛的正确终态是 0，不是 5。
        """
        code, _ = S.count_literal_code_vs_comment(prod_files, F.OO_HEALTH_LITERAL)
        _eq("N 域 health 直调", code, [])
        cap = S.ROOT / F.OO_HEALTH_CAPABILITY_MODULE
        assert "/api/workpapers/onlyoffice/health" in _code(cap), "能力层里也没有 ⇒ 扫描空跑"

    def test_n3_refusal_is_explicit(self) -> None:
        """NA-P7：🔴 拒切 OO 必须显式反馈（不可用原因 + 已回落 HTML），SHALL NOT 只加日志。"""
        n3 = _code(N3_HOST)
        fn = n3[n3.find("async function onModeChange"):][:900]
        assert "ElMessage.warning(" in fn and "已保持 HTML 模式" in fn
        assert not re.search(r"if \(val === 'onlyoffice' && !ooHealthy\.value\) return\s*\n", fn)

    def test_config_prefetch_converged(self, prod_files) -> None:
        """NA-P9：`onlyoffice-config` 直调收敛 —— N 域 0 处，能力层唯一一处。"""
        code, _ = S.count_literal_code_vs_comment(prod_files, "onlyoffice-config")
        _eq("N 域 config 直调", code, [])
        cap = W / "sync" / "onlyOfficeSheetConfig.ts"
        assert "onlyoffice-config" in _code(cap)
        assert "prefetchOnlyOfficeSheetConfig" in _code(C / "useN1DualMode.ts")

    def test_n1_three_mode_contract_kept(self, graph) -> None:
        """NA-P10：三值载体保 matrix + 9 个被消费成员 + 5 条生产边。"""
        text = _code(C / "useN1DualMode.ts")
        assert "'structured' | 'matrix' | 'onlyoffice'" in text
        ret = text[text.rfind("return {"):]
        for member in ("mode", "modeOptions", "switchMode", "fetchingConfig", "isOOHealthy",
                       "ooConfigReady", "isOnlyOffice", "isMatrix", "onOoLoadFailed"):
            assert re.search(rf"\b{member}\b", ret), member
        m = S.module_reachability([C / "useN1DualMode.ts"], graph)[0]
        _eq("生产边", len(m.production_consumers), 5)

    def test_n1_storage_key_wp_scoped(self) -> None:
        """NA-P11：localStorage 键 `n1-dual-mode` 按 wp 分区。"""
        text = _code(C / "useN1DualMode.ts")
        assert "STORAGE_KEY_PREFIX = 'n1-dual-mode'" in text
        assert "${STORAGE_KEY_PREFIX}:${wpId.value}" in text

    def test_n1_refusal_is_explicit_too(self) -> None:
        text = _code(C / "useN1DualMode.ts")
        assert "已保持结构化视图" in text


# ═══ Task 8 / 9 / 10 · A 族改造 / transport_key / parent_duplicate（NA-P12 ~ NA-P16） ═══
class TestLane2Identity:
    def test_a_family_is_zero(self, prod_files) -> None:
        """NA-P16：A 族（位置化持久化键）降至 0，`N1-1-adj` 键不再含数组下标。"""
        fam = S.scan_row_identity_families(S.stripped_sources(prod_files))
        _eq("A 族", fam["A_positional_persistence_key"], [])

    def test_a_family_scanner_not_constant_zero(self) -> None:
        sample = {"x.ts": "formData.debouncedSave(`${ITEM_PREFIX}-${index}`, v)"}
        assert S.scan_row_identity_families(sample)["A_positional_persistence_key"]

    def test_n1_writes_only_template_row_keys(self) -> None:
        text = _code(C / "useN1Adjudication.ts")
        persist = text[text.find("function _persistRow"):][:500]
        assert "n1AdjudicationItemId(category)" in persist
        assert "legacyPositionalItemId" not in persist, "旧位置键被用于写入"
        # 旧键只在读路径出现
        uses = [m.start() for m in re.finditer(r"legacyPositionalItemId\(", text)]
        _eq("旧键用法（定义 + 读兜底）", len(uses), 2)

    def test_template_row_mapping_matches_categories(self) -> None:
        text = _code(C / "useN1Adjudication.ts")
        cats = re.search(r"N1_ADJUDICATION_CATEGORIES[^=]*=\s*\[(.*?)\]", text, re.S).group(1)
        mapping = re.search(r"N1_ADJUDICATION_TEMPLATE_ROW[^=]*=\s*\{(.*?)\}", text, re.S).group(1)
        _eq("类目", re.findall(r"'([^']+)'", cats), re.findall(r"'([^']+)':", mapping))
        _eq("模板行", re.findall(r":\s*'(A\d+)'", mapping), [f"A{i}" for i in range(7, 14)])

    def test_tk2_dual_condition_still_holds(self) -> None:
        """NA-P13~15：TK-2 双条件（owner 常量 + 展开数 7）；字面量 N1-1-adj-0 恒 0。"""
        text = _code(C / "useN1Adjudication.ts")
        assert "ITEM_PREFIX = 'N1-1-adj'" in text
        assert len(re.findall(r"'A\d+'", text)) == F.N1_ADJUDICATION_CATEGORY_COUNT
        assert "N1-1-adj-0" not in text

    def test_n1_two_owner_declarations(self) -> None:
        assert "ITEM_PREFIX = 'N1-'" in _code(C / "useN1FormData.ts")
        assert "ITEM_PREFIX = 'N3-'" in _code(C / "useN3FormData.ts")

    def test_guessed_keys_zero(self, prod_files) -> None:
        src = S.stripped_sources(prod_files)
        for k in ("N1-1-rows", "N1-1-adjudication-rows", "N3-1-rows"):
            _eq(k, [s for q in "'\"`" for s in S.scan_literal(src, f"{q}{k}{q}")], [])

    def test_parent_duplicate_data_side(self, slice_doc) -> None:
        """NA-P12：4 条子入口全名 + 全挂 N1 + 宿主文件存在 + 都有自己的 OO 挂点。"""
        kids = slice_doc["parent_duplicate_summary"]["children"]
        _eq("全名", tuple(k["entry_id"] for k in kids), F.PARENT_DUPLICATE_CHILDREN)
        for k in kids:
            host = S.ROOT / k["host_path"]
            assert host.is_file()
            assert "<GtOnlyOfficeSheet" in _code(host), k["entry_id"]
            assert "useN1DualMode" in _code(host), f"{k['entry_id']} 不经父 entry 载体"

    def test_frontend_spec_exists(self) -> None:
        text = S.read_text(C / "__tests__" / "nCycleLane2RouterAndKeys.spec.ts")
        for marker in ("BP-10 防护", "旧位置键数据仍能读出", "写入只走新键"):
            assert marker in text


# ═══ Task 11 / 12 · 契约与真库（NA-P17 / NA-P18） ═══════════════════════════
class TestLane2PayloadAndLiveDb:
    def test_n1_payload_lives_in_conclusion(self) -> None:
        """NA-P17：N1-1 读写走 conclusion 列（与真库/设计一致）。"""
        text = _code(C / "useN1Adjudication.ts")
        assert "stored?.conclusion" in text and "conclusion: JSON.stringify(data)" in text

    def test_live_db_lane2(self) -> None:
        """NA-P18（现算）：真库 N1/N3 0 行 ⇒ 空分母（design 记 19 行 / 污染 2），不宣称通过。"""
        from tests.workpaper_sync.test_n_cycle_foundation_canary import _live_db_rows

        rows = _live_db_rows()
        mine = [r for r in rows if r["item_id"].startswith(("N1-", "N3-"))]
        _eq("lane2 真库行", len(mine), 0)


# ═══ Task 13 / 14 · 模板缺陷登记（NA-P19 ~ NA-P22） ═══════════════════════════
class TestLane2TemplateDefects:
    def test_a2_family_n3_2(self, tf) -> None:
        """NA-P19：N3-2 H11~H21 整列 `=F#+O#`，与 A1 分开计数。"""
        a2 = [h for h in tf.overflow if h.family == "A2_structural_residue"]
        _eq("A2", len(a2), 11)
        assert all(h.workbook == N3_WB for h in a2)
        assert all(re.fullmatch(r"=F(\d+)\+O\d+", h.formula) for h in a2)

    def test_n3_2_e23_legal(self, tf) -> None:
        b = [(h.sheet, h.cell) for h in tf.overflow if h.family == "B_range_end" and h.workbook == N3_WB]
        _eq("合法区间终点", b, [("递延所得税负债明细表N3-2", "E23")])

    def test_de_form_literals(self, tf) -> None:
        """「表的{码}」3 处全在 lane2 两册，按原始字面量锁定。"""
        de = sorted(f.sheet for f in tf.sheets if re.search(r"表的N\d", f.sheet))
        _eq("表的{码}", de, sorted([
            "递延所得税资产审计程序表的N1A",
            "可用以后年度税前利润弥补的亏损检查表的N1-5",
            "递延所得税负债审计程序表的N3A",
        ]))

    def test_defined_names_lane2(self, tf) -> None:
        mine = [d for d in tf.defined_names if d.workbook in (N1_WB, N3_WB)]
        _eq("lane2 definedName", (len(mine), sum(d.broken for d in mine)), (48, 28))

    def test_wide_sheet_and_n1_4_density(self, tf) -> None:
        """NA-P21：超宽表遍历上界取 last_value_col；N1-4 为全域双料最密。"""
        wide = [(f.sheet, f.max_col - f.last_value_col) for f in S.wide_sheets(tf.sheets) if f.workbook == N1_WB]
        _eq("N1 超宽", wide, [("附注披露信息（国企）", 249)])
        n1_4 = next(f for f in tf.sheets if f.sheet == "递延所得税资产（负债）测算表N1-4")
        _eq("N1-4 公式格", n1_4.formula_cells, max(f.formula_cells for f in tf.sheets))
        _eq("N1-4 裸 IF", n1_4.bare_if_cells, max(f.bare_if_cells for f in tf.sheets))

    def test_n3_extremes_and_empty_disclosure(self, tf) -> None:
        """NA-P22：🔴 N3 无附注披露（n=0）⇒ disclosure 判据空分母；sheets 最少 6 / 公式格最少 162。"""
        n3 = [f for f in tf.sheets if f.workbook == N3_WB]
        _eq("N3 附注 sheet", [f.sheet for f in n3 if "附注" in f.sheet], [])
        per_wb: dict[str, int] = {}
        fx: dict[str, int] = {}
        for f in tf.sheets:
            per_wb[f.workbook] = per_wb.get(f.workbook, 0) + 1
            fx[f.workbook] = fx.get(f.workbook, 0) + f.formula_cells
        _eq("sheets 最少", min(per_wb, key=per_wb.get), N3_WB)
        _eq("公式格最少", min(fx, key=fx.get), N3_WB)
        assert not list(W.glob("n3/**/N3TabDisclosure*.vue")), "N3 披露组件又出现了"


# ═══ Task 15 / 16 · orphan 与 N3A 碰撞 ═══════════════════════════════════════
class TestLane2Collision:
    def test_lane2_orphans_deleted(self) -> None:
        for name in F.ORPHAN_OWNED_BY_LANE2:
            rel = (C / name).relative_to(S.ROOT).as_posix()
            assert rel in F.DELETED_ORPHANS, name
            assert not (C / name).exists(), name

    def test_n3a_collision_by_pair(self, tf) -> None:
        """🔴 按 (册, sheet 名) 定位；对端断言见 lane3
        `test_n_lane3_json_table_identity.py::TestLane3OrphansAndCollision`。"""
        pairs = sorted((f.workbook, f.sheet) for f in tf.sheets if "N3A" in f.sheet)
        _eq("N3A", pairs, [(N3_WB, "递延所得税负债审计程序表的N3A"),
                          ("N5 所得税费用.xlsx", "所得税审计程序表N3A (原底稿)")])

    def test_foreign_letter_codes_empty_for_lane2(self, tf) -> None:
        """外来字母码 O1A/O2A 对本 spec 空分母（显式声明）。"""
        hits = [f.sheet for f in tf.sheets if f.workbook in (N1_WB, N3_WB) and re.search(r"O\dA", f.sheet)]
        _eq("lane2 外来码", hits, [])
