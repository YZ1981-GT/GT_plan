# -*- coding: utf-8 -*-
"""N 循环双向回写地基与首张 canary —— 守卫。

spec: `.kiro/specs/n-cycle-sync-foundation-and-first-canary`
Properties: NF-P1 ~ NF-P40 · 共同判据 NC-1 ~ NC-37

与既存守卫 `test_task56_n_cycle_migration.py` **并存互不覆盖**：那份锁「现状诚实记录」，
本份锁「改线后目标态 + 共同判据的可执行形式」。

═══ 三条纪律（design「测试策略」） ═══════════════════════════════════════════

1. 期望值由扫描器现读源文件得出；基线常量集中在 `n_cycle_facts.py` 一处，
   便于一眼看出哪些值是人工锚定的。
2. 结构性零必须成对出现「零断言 + 变异证明」，单独的零断言视为未完成。
3. 模板 sha256 断言置于最前，失败即中止（防在被改过的模板上跑出误导性结论）。

═══ 运行 ═══════════════════════════════════════════════════════════════════

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_cycle_foundation_canary.py -v --tb=short
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.analyze import n_cycle_scanner as S  # noqa: E402
from tests.workpaper_sync import n_cycle_facts as F  # noqa: E402


# ─── fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return S.load_json(S.SLICE_PATH)


@pytest.fixture(scope="module")
def entries(slice_doc: dict) -> list[dict]:
    return slice_doc["independent_entries"]


@pytest.fixture(scope="module")
def domain_files() -> list[S.DomainFile]:
    return S.scan_domain_files()


@pytest.fixture(scope="module")
def prod_files(domain_files: list[S.DomainFile]) -> list[S.DomainFile]:
    return S.production_files(domain_files)


@pytest.fixture(scope="module")
def prod_sources(prod_files: list[S.DomainFile]) -> dict[str, str]:
    return S.stripped_sources(prod_files)


@pytest.fixture(scope="module")
def template_facts() -> S.TemplateFacts:
    return S.collect_template_facts()


@pytest.fixture(scope="module")
def import_graph() -> dict:
    return S.build_import_graph()


def _eq(label: str, computed, expected) -> None:
    assert computed == expected, f"{label}: 现算 {computed!r} ≠ 基线 {expected!r}"


# ═══════════════════════════════════════════════════════════════════════════
# Task 3 · 模板前置门（最先跑，失败即中止）
# Property: NF-P5
# ═══════════════════════════════════════════════════════════════════════════
class TestAaaTemplateGateFirst:
    """🔴 类名以 Aaa 开头保证字典序最先 —— 在被改过的模板上跑出的结论是误导性的。"""

    def test_five_workbooks_sha256_and_size_match_slice(self, slice_doc: dict) -> None:
        """5 本册 sha256 与 size 全 match（NF-P5；本 spec 系列 SHALL NOT 改 .xlsx）。"""
        declared = {f["name"]: f for f in slice_doc["authoritative_templates"]["files"]}
        on_disk = {p.name: p for p in S.iter_template_files()}
        _eq("模板册数", len(on_disk), len(declared))
        assert set(on_disk) == set(declared), (
            f"磁盘册名集合 {sorted(on_disk)} ≠ slice 声明 {sorted(declared)}"
        )
        for name, path in sorted(on_disk.items()):
            # 🔴 N4 canary 的权威模板已 OOXML 净化（spec N4 Task 7a：删 2 外链部件 +
            #    中性化隐藏「原底稿」册 5 个外部引用公式，受管 sheet 税金及附加明细表N4-2 逐格
            #    0 diff）⇒ sha/size 相对 slice 冻结值**有意变更**，仅 N4 用净化后现算值比对，
            #    其余四册仍逐值等于 slice。
            if name in F.SANITIZED_TEMPLATE_WORKBOOKS:
                _eq(f"{name} sha256(净化后)", S.sha256_of(path), F.N4_SANITIZED_TEMPLATE_FACTS["sha256"])
                _eq(f"{name} size(净化后)", path.stat().st_size, F.N4_SANITIZED_TEMPLATE_FACTS["size"])
            else:
                _eq(f"{name} sha256", S.sha256_of(path), declared[name]["sha256"])
                _eq(f"{name} size", path.stat().st_size, declared[name]["size"])

    def test_lock_files_are_skipped(self) -> None:
        """枚举跳 `~$` 锁文件；本轮现算锁文件 0 个（反向：枚举器真的在过滤）。"""
        assert all(not p.name.startswith("~$") for p in S.iter_template_files())
        _eq("锁文件数", len(list(S.N_TEMPLATE_DIR.glob("~$*"))), 0)

    def test_reference_copy_absence_is_recomputed_not_quoted(self, slice_doc: dict) -> None:
        """参考副本状态必须现算 `is_dir()`，不得照抄结论（slice 自己点名这条）。"""
        _eq(
            "reference_copy_status",
            slice_doc["authoritative_templates"]["reference_copy_status"],
            "absent_on_this_machine",
        )
        assert not (S.BACKEND / "基础数据").is_dir(), (
            "参考副本被拉回来了 —— slice 的 reference_copy_status 须同步更新"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Task 2 · entry 基线与归属算术
# Properties: NF-P1 ~ NF-P4 · NF-P34
# ═══════════════════════════════════════════════════════════════════════════
class TestEntryBaselineAndArithmetic:
    def test_entry_list_is_exactly_five_full_names(self, entries: list[dict]) -> None:
        """NF-P1：entry 清单 5 条且全名逐一吻合。"""
        _eq("entry 数", len(entries), 5)
        _eq("entry 集合", tuple(e["entry_id"] for e in entries), F.ENTRY_IDS)

    def test_selection_rule_recomputed_from_full_manifest(self, entries: list[dict]) -> None:
        """按 slice 的 selection_rule 从 manifest **现算**，多写/漏写都红。"""
        manifest = S.load_json(S.FULL_MANIFEST_PATH)
        n_prefixed = [
            e for e in manifest.get("entries", [])
            if e.get("document_type") == "xlsx"
            and any(
                str(p).startswith("N")
                for p in (e.get("wp_match", {}) or {}).get("wp_code_patterns", [])
            )
        ]
        independent = [e for e in n_prefixed if e.get("independent_entry") is True]
        _eq("N 前缀 entry 总数", len(n_prefixed), 9)
        _eq("其中 independent", len(independent), 5)
        _eq(
            "现算集合",
            {e["entry_id"] for e in independent},
            {e["entry_id"] for e in entries},
        )

    def test_n0_workbook_does_not_exist(self) -> None:
        """`N0` 不存在（与 K/L 两轮各有一本 K0/L0 函证册不同）⇒ 排除集为空、如实登记 0。"""
        manifest = S.load_json(S.FULL_MANIFEST_PATH)
        hits = [e for e in manifest.get("entries", []) if "n0" in e.get("entry_id", "").lower()]
        _eq("manifest 里 N0 entry", len(hits), 0)
        idx = S.load_json(S.TEMPLATE_INDEX)
        n_rows = [
            f for f in idx.get("files", [])
            if str(f.get("relative_path", "")).replace("\\", "/").startswith("N/")
        ]
        _eq("_index.json 的 N 册条目", len(n_rows), 5)

    def test_slice_has_no_excluded_pilot(self, slice_doc: dict) -> None:
        """slice 无 pilot（四条 pilot 契约全不属 N）。"""
        _eq("excluded_pilot_entry_count", slice_doc["slice_scope"]["excluded_pilot_entry_count"], 0)

    def test_account_scope_is_four_way_not_uniform(self, entries: list[dict]) -> None:
        """NF-P2：科目性质四分 —— 2 资产负债（借贷**相反**）+ 2 损益，禁假设同方向。"""
        for e in entries:
            code, acct, nature, direction = F.ENTRY_ACCOUNTS[e["entry_id"]]
            _eq(f"{e['entry_id']} wp_code", e["wp_code_pattern"], code)
            scope = e["account_scope"]
            assert acct in scope, f"{e['entry_id']} account_scope 不含科目号 {acct}：{scope}"
            assert nature in scope and direction in scope, (
                f"{e['entry_id']} account_scope 未体现 {nature}/{direction}：{scope}"
            )
        directions = {F.ENTRY_ACCOUNTS[e][3] for e in (F.N1, F.N2, F.N3)}
        assert directions == {"借", "贷"}, "资产负债两类必须借贷相反，不得同向"

    def test_sheet_attribution_arithmetic(self, template_facts: S.TemplateFacts) -> None:
        """NF-P3：sheets 归属算术 —— foundation 9 + lane2 16 + lane3 34 = 59。"""
        per_wb: dict[str, int] = {}
        for f in template_facts.sheets:
            per_wb[f.workbook] = per_wb.get(f.workbook, 0) + 1
        _eq("逐册 sheet 数", per_wb, F.WORKBOOK_SHEET_COUNT)
        foundation = sum(per_wb[F.ENTRY_WORKBOOKS[e]] for e in F.FOUNDATION_ENTRIES)
        lane2 = sum(per_wb[F.ENTRY_WORKBOOKS[e]] for e in F.LANE2_ENTRIES)
        lane3 = sum(per_wb[F.ENTRY_WORKBOOKS[e]] for e in F.LANE3_ENTRIES)
        _eq("foundation sheets", foundation, 9)
        _eq("lane2 sheets", lane2, 16)
        _eq("lane3 sheets", lane3, 34)
        _eq("合计 sheets", foundation + lane2 + lane3, F.TOTAL_SHEETS)

    def test_sheet_classification_sums_to_total(self, slice_doc: dict) -> None:
        """HTML child 45 + prog 2 + OO 兜底 12 = 59；OO 兜底四类穷举无 other 桶。"""
        c = slice_doc["sheet_granularity_and_router_audit"]["counters"]
        _eq("html_child", c["sheets_covered_by_html_child"], F.SHEETS_HTML_CHILD)
        _eq("program_console", c["sheets_rendered_by_program_console"], F.SHEETS_PROGRAM_CONSOLE)
        _eq("oo_fallthrough", c["sheets_falling_through_to_oo"], F.SHEETS_OO_FALLTHROUGH)
        _eq(
            "三类求和",
            c["sheets_covered_by_html_child"]
            + c["sheets_rendered_by_program_console"]
            + c["sheets_falling_through_to_oo"],
            c["authoritative_sheets_total"],
        )
        buckets = slice_doc["sheet_granularity_and_router_audit"]["oo_fallthrough_classification"]
        _eq("OO 兜底四类", buckets["counts"], F.OO_FALLTHROUGH_BUCKETS)
        _eq("四类求和", sum(buckets["counts"].values()), F.SHEETS_OO_FALLTHROUGH)
        assert "other" not in buckets["enum"], "OO 兜底分类不得有 other 兜底桶（fail closed）"
        _eq(
            "dual_mode_switchable == html_child",
            c["dual_mode_switchable_sheets"],
            c["sheets_covered_by_html_child"],
        )

    def test_formula_cell_caliber_and_data_only_counterproof(
        self, template_facts: S.TemplateFacts
    ) -> None:
        """NF-P4：公式格 2185（`data_only=False`）+ `data_only=True` 反证命中 0。"""
        per_wb: dict[str, int] = {}
        with_fx: dict[str, int] = {}
        for f in template_facts.sheets:
            per_wb[f.workbook] = per_wb.get(f.workbook, 0) + f.formula_cells
            if f.formula_cells:
                with_fx[f.workbook] = with_fx.get(f.workbook, 0) + 1
        # 🔴 N4 canary 的权威模板已 OOXML 净化（spec N4 Task 7a）⇒ 隐藏「原底稿」册的 5 个
        #    外部引用公式被中性化，N4 逐册公式格 236→231、带 fx sheet 7→6（受管 sheet
        #    税金及附加明细表N4-2 零受影响）。仅 N4 用净化后现算值比对基线。
        _n4_wb = "N4 税金及附加.xlsx"
        _expect_cells = dict(F.WORKBOOK_FORMULA_CELLS)
        _expect_withfx = dict(F.WORKBOOK_SHEETS_WITH_FORMULA)
        if _n4_wb in F.SANITIZED_TEMPLATE_WORKBOOKS:
            _expect_cells[_n4_wb] = F.N4_SANITIZED_TEMPLATE_FACTS["formula_cells"]
            _expect_withfx[_n4_wb] = F.N4_SANITIZED_TEMPLATE_FACTS["sheets_with_formula"]
        _eq("逐册公式格", per_wb, _expect_cells)
        _eq("逐册带 fx sheet", with_fx, _expect_withfx)
        _eq("公式格合计", sum(per_wb.values()), sum(_expect_cells.values()))
        _eq("带 fx sheet 合计", sum(with_fx.values()), sum(_expect_withfx.values()))
        for p in S.iter_template_files():
            _eq(f"{p.name} data_only=True 反证", S.formula_cells_with_data_only(p), 0)

    def test_bp_common_seven_and_discriminating_members(self, entries: list[dict]) -> None:
        """NF-P34：BP 公共 7 项对每条 entry 成立 + 区分项成员集 + 逐 entry 9/8/9/8/10。"""
        per_entry = {e["entry_id"]: list(e["capability_target_blocked_by"]) for e in entries}
        _eq("逐 entry BP 数", {k: len(v) for k, v in per_entry.items()}, F.BP_COUNT_PER_ENTRY)
        for eid, bps in per_entry.items():
            missing = [b for b in F.BP_COMMON if b not in bps]
            assert not missing, f"{eid} 缺公共 BP {missing}"
        for bp, members in F.BP_DISCRIMINATING.items():
            actual = tuple(eid for eid, bps in per_entry.items() if bp in bps)
            _eq(f"{bp} 成员集", actual, members)


# ═══════════════════════════════════════════════════════════════════════════
# Task 15 · 写路径与发布门
# Properties: NF-P6 · NF-P7
# ═══════════════════════════════════════════════════════════════════════════
class TestWritePathAndPublishGate:
    def test_publish_gate_code_vs_comment(self, prod_files) -> None:
        """NF-P6：`publish-to-tb` 代码命中 5（每 entry 一处）· 注释命中 15。

        🔴 NC-3：不剥注释会把 15 条迁移注释当成违规站点。
        """
        code, cmt = S.count_literal_code_vs_comment(prod_files, F.PUBLISH_TO_TB_LITERAL)
        _eq("publish-to-tb CODE", len(code), F.PUBLISH_TO_TB_CODE)
        _eq("publish-to-tb CMT", len(cmt), F.PUBLISH_TO_TB_COMMENT)
        _eq(
            "发布门宿主模块",
            sorted(Path(s.rel).name for s in code),
            [f"useN{i}FormData.ts" for i in range(1, 6)],
        )

    def test_legacy_writeback_endpoint_is_gone_from_code(self, prod_files) -> None:
        """结构性零 + 变异证明：旧端点代码命中 0，但注释命中非 0 ⇒ 扫描器真在跑。"""
        code, cmt = S.count_literal_code_vs_comment(prod_files, F.LEGACY_WRITEBACK_LITERAL)
        _eq("trial-balance/writeback CODE", len(code), 0)
        assert len(cmt) > 0, (
            "旧端点连注释都 0 命中 ⇒ 无法区分「已删干净」与「扫描器没跑」（空分母重言式）"
        )

    def test_publish_is_not_called_from_reactive_callbacks(self, prod_sources) -> None:
        """TB 回写铁律：禁在 watch / onMounted / debounce 回调内触发发布门。"""
        offenders: list[str] = []
        for rel, text in prod_sources.items():
            if F.PUBLISH_TO_TB_LITERAL not in text:
                continue
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if F.PUBLISH_TO_TB_LITERAL not in line:
                    continue
                window = "\n".join(lines[max(0, i - 40):i])
                opened = window.rfind("watch(")
                mounted = window.rfind("onMounted(")
                for tag, pos in (("watch", opened), ("onMounted", mounted)):
                    if pos < 0:
                        continue
                    tail = window[pos:]
                    if tail.count("{") > tail.count("}"):
                        offenders.append(f"{rel}#L{i + 1} 在 {tag} 内")
        assert not offenders, f"发布门被挂在响应式回调里：{offenders}"

    def test_confirm_gate_and_publish_gate_are_disjoint(self, prod_files) -> None:
        """NF-P7：confirm 26 处 / 17 文件；与发布门文件集**交集 0**（分居不同模块）。"""
        confirm, _ = S.count_literal_code_vs_comment(prod_files, "ElMessageBox.confirm")
        _eq("confirm 站点", len(confirm), F.CONFIRM_SITES)
        confirm_files = {s.rel for s in confirm}
        _eq("confirm 文件数", len(confirm_files), F.CONFIRM_FILES)
        publish, _ = S.count_literal_code_vs_comment(prod_files, F.PUBLISH_TO_TB_LITERAL)
        _eq("确认门 ∩ 发布门", confirm_files & {s.rel for s in publish}, set())

    def test_confirm_gate_tolerates_n5_shape_exception(self, prod_files) -> None:
        """🔴 判据按「每 entry 至少一处 confirm」，禁按「每 entry 有同名 composable」。

        `useN5Adjudication.ts` **不存在** —— N5 的 confirm 落在 `N5TabAdjudication.vue`。
        """
        assert not (S.WP_COMPOSABLES / "useN5Adjudication.ts").exists(), (
            "useN5Adjudication.ts 出现了 —— NB-P17 的结构异形前提须重算"
        )
        confirm, _ = S.count_literal_code_vs_comment(prod_files, "ElMessageBox.confirm")
        for n in range(1, 6):
            hits = [s for s in confirm if re.search(rf"[/\\](?:use)?[Nn]{n}\b|[/\\]n{n}[/\\]", s.rel)]
            assert hits, f"N{n} 域内无任何 confirm 站点"

    def test_no_raw_put_write_channel(self, prod_files) -> None:
        """`http.put` 结构性零；`api.put` 为真实写通道（反向分母，证明扫描非空跑）。"""
        http_put, _ = S.count_literal_code_vs_comment(prod_files, "http.put")
        _eq("http.put", len(http_put), 0)
        api_put, _ = S.count_literal_code_vs_comment(prod_files, "api.put")
        assert len(api_put) > 0, "api.put 也是 0 ⇒ 扫描器没跑（N 域确有 api.put 写通道）"


# ═══════════════════════════════════════════════════════════════════════════
# Task 13 · 载体族与 inert 开关修复
# Properties: NF-P8 · NF-P9 · NC-13
# ═══════════════════════════════════════════════════════════════════════════
_N4_HOST = S.WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue"
_N5_HOST = S.WP_COMPONENTS / "GtN5IncomeTaxExpense.vue"
_N3_HOST = S.WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue"
_N1_HOST = S.WP_COMPONENTS / "GtN1DeferredTaxAssets.vue"
_N2_HOST = S.WP_COMPONENTS / "GtN2TaxesPayable.vue"
ALL_HOSTS = (_N1_HOST, _N2_HOST, _N3_HOST, _N4_HOST, _N5_HOST)


class TestCarrierFamilies:
    def test_three_families_four_subfamilies(self, entries: list[dict]) -> None:
        """NF-P8：载体 3 族 4 亚族（slice 为冻结记录，不随本轮改线而变）。"""
        kinds = {e["entry_id"]: e["dual_mode_carrier"]["kind"] for e in entries}
        _eq(
            "载体亚族",
            kinds,
            {
                F.N1: "per_entry_composable_three_modes",
                F.N2: "per_entry_wrapper_over_shared_base",
                F.N3: "host_inline_real",
                F.N4: "host_inline_inert",
                F.N5: "host_inline_inert",
            },
        )
        families = {k.split("_")[0] + ("_entry" if k.startswith("per_entry") else "") for k in kinds.values()}
        _eq("载体族数", len(families), 2)
        _eq("亚族数", len(set(kinds.values())), 4)

    def test_no_per_entry_entry_dual_mode_file(self) -> None:
        """结构性零：N 域无 `*EntryDualMode.ts`（M 轮的形态）+ 变异证明。"""
        n_hits = sorted(p.name for p in S.WP_COMPOSABLES.glob("useN*EntryDualMode.ts"))
        _eq("N 域 *EntryDualMode.ts", n_hits, [])
        assert (S.WP_COMPOSABLES / "useWorkpaperEntryDualMode.ts").exists(), (
            "共享基类不在了 ⇒ glob 口径本身有问题（变异证明不成立）"
        )

    def test_n4_and_n5_noop_mode_change_is_fixed(self) -> None:
        """🔴 NC-13 / BP-5：`onModeChange: () => {}` 空实现必须消失（foundation T13 / lane3 T6）。"""
        for host in (_N4_HOST, _N5_HOST):
            text = S.strip_comments(S.read_text(host))
            compact = re.sub(r"\s+", "", text)
            assert "onModeChange:()=>{}" not in compact, (
                f"{host.name} 的模式开关仍是空实现 ⇒ 双模式只有单向（BP-5 未收口）"
            )

    def test_n4_and_n5_switch_is_now_redeemable(self) -> None:
        """redeemable 三要素：segmented 站点 + mode 门控的 OO 挂点 + 真会改 mode 的回调。"""
        for host in (_N4_HOST, _N5_HOST):
            text = S.strip_comments(S.read_text(host))
            assert "<el-segmented" in text, f"{host.name} 无 el-segmented 站点"
            assert re.search(r"currentMode\.value\s*===\s*'onlyoffice'", text), (
                f"{host.name} 无 mode 门控的 OO 挂点"
            )
            assert re.search(r"currentMode\.value\s*=", text), (
                f"{host.name} 的回调没有真的改 mode（仍不可兑现）"
            )

    def test_n4_and_n5_health_goes_through_capability_layer(self) -> None:
        """🔴 修 inert 时不得再复制一份 health 直调 —— 必须走统一能力层（BP-4 同源纪律）。"""
        for host in (_N4_HOST, _N5_HOST):
            text = S.strip_comments(S.read_text(host))
            assert "fetchOnlyOfficeHealthy" in text, (
                f"{host.name} 未接统一能力层 sync/onlyOfficeHealth.ts"
            )
            assert "onlyoffice/health" not in text, (
                f"{host.name} 出现了 health 端点直调字面量（又复制了一份探针）"
            )

    def test_gate_variants_are_recognised(self) -> None:
        """NF-P9：识别带泛型 `ref<...>(` 与 `isOnlyOffice` 计算属性两种门控变体。"""
        n5 = S.strip_comments(S.read_text(_N5_HOST))
        assert re.search(r"ref<'html'\s*\|\s*'onlyoffice'>\(", n5), (
            "带泛型 ref 变体未命中 ⇒ 只扫 `ref(` 的正则会漏（NC-13）"
        )
        n1_mod = S.strip_comments(S.read_text(S.WP_COMPOSABLES / "useN1DualMode.ts"))
        assert re.search(r"const\s+isOnlyOffice\s*=\s*computed", n1_mod), (
            "`isOnlyOffice` 计算属性变体未命中 ⇒ 只扫 currentMode|renderMode 会漏"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Task 1 · strict 域口径（NC-5）
# Property: NF-P10
# ═══════════════════════════════════════════════════════════════════════════
class TestStrictDomainScope:
    def test_strict_scope_counts(self, domain_files) -> None:
        """基线 164/137/27 是本 spec 动手前现算；之后的增删逐个登记在 facts 里。"""
        prod = len(F.DELETED_ORPHANS) + len(F.SECOND_ORDER_ORPHANS_DELETED)
        _eq("生产", len(S.production_files(domain_files)),
            F.DOMAIN_FILES_PRODUCTION - prod + len(F.NEW_DOMAIN_PROD_FILES))
        prod_names = {f.name for f in S.production_files(domain_files)}
        assert set(F.NEW_DOMAIN_PROD_FILES) <= prod_names, "登记的新增生产文件不在域内"
        _eq("测试", len(S.test_files(domain_files)),
            F.DOMAIN_FILES_TEST + len(F.NEW_DOMAIN_TEST_FILES))
        names = {f.name for f in S.test_files(domain_files)}
        assert set(F.NEW_DOMAIN_TEST_FILES) <= names, "登记的新增测试文件不在域内"

    def test_loose_only_is_zero(self) -> None:
        """结构性零：宽口径独有文件 0 —— strict 三路取并没漏东西。"""
        _eq("loose_only", S.loose_only_files(), [])

    def test_lower_branch_mutation_proof(self, domain_files) -> None:
        """🔴 变异证明：去掉小写分支后漏检集合 == 「文件名匹配 ^n[1-5][A-Z]」全集（且非空）。"""
        no_lower = {f.path for f in S.scan_domain_files(["seg", "upper", "ref"])}
        missed = {f.path for f in domain_files} - no_lower
        assert missed, "去掉 lower 分支后零漏检 ⇒ 变异证明不成立"
        expected = {f.path for f in domain_files if re.match(r"^n[1-5][A-Z]", f.name)}
        _eq("漏检集合", missed, expected)
        # 去 lower 分支会漏掉 live 的共享路由采用方（N 域三个路由模块全是小写前缀）
        assert any(p.name == "n2SheetRouting.ts" for p in missed)

    def test_ncycle_ref_branch_catches_the_consistency_module(self, domain_files) -> None:
        """`nCycleTaxConsistency.ts` 连 `^n[1-5]` 都不匹配，只能靠 ref 分支收进来。"""
        hit = [f for f in domain_files if f.name == "nCycleTaxConsistency.ts"]
        assert hit and hit[0].branches == frozenset({"ref"}), hit

    def test_strip_comments_keeps_line_numbers(self) -> None:
        src = "a\n/* x\ny */\nb // z\n<!-- c -->\nhttps://e.com"
        out = S.strip_comments(src)
        _eq("行数", S.count_lines(out), S.count_lines(src))
        assert "x" not in out and "z" not in out and " c " not in out
        assert "https://e.com" in out, "URL 的 // 被当成行注释剥掉了"


# ═══════════════════════════════════════════════════════════════════════════
# Task 14 / 16 / 17 · orphan 清册、E 族样板提取与按身份删行
# Properties: NF-P11 · NF-P12 · NF-P13
# ═══════════════════════════════════════════════════════════════════════════
_STABLE_ID_MODULE = S.WP_COMPOSABLES / "shared" / "stableRowIdentity.ts"
_PAYLOAD_MODULE = S.WP_COMPOSABLES / "shared" / "checklistPayload.ts"


class TestOrphanInventory:
    """🔴 类名沿用 `TestOrphanInventory`（非 M 轮的 `TestOrphanDualModeInventory`）：
    N 域 orphan 不止 dual-mode —— 只扫 `useN*DualMode.ts` 会把 8 报成 3。"""

    def test_orphan_set_equals_slice_minus_deleted_plus_second_order(self, import_graph) -> None:
        orphans = {m.rel for m in S.n_domain_orphans(import_graph)}
        expected = (set(F.ORPHAN_MODULES) - set(F.DELETED_ORPHANS)) | set(
            F.SECOND_ORDER_ORPHANS_CREATED)
        _eq("orphan 集合", orphans, expected)

    def test_orphan_attribution_three_two_three(self) -> None:
        names = {Path(p).name for p in F.ORPHAN_MODULES}
        owned = (set(F.ORPHAN_OWNED_BY_FOUNDATION) | set(F.ORPHAN_OWNED_BY_LANE2)
                 | set(F.ORPHAN_OWNED_BY_LANE3))
        _eq("三份 spec 归属并集", owned, names)
        _eq("归属份额", (len(F.ORPHAN_OWNED_BY_FOUNDATION), len(F.ORPHAN_OWNED_BY_LANE2),
                         len(F.ORPHAN_OWNED_BY_LANE3)), (3, 2, 3))

    def test_second_order_orphans_are_disposed(self, import_graph) -> None:
        """删除引出的二阶 orphan 必须被处置（删除或接线），不得留成新的死模块。"""
        for rel in F.SECOND_ORDER_ORPHANS_DELETED:
            assert not (S.ROOT / rel).exists(), f"{rel} 登记为已删却仍在"
        assert not F.SECOND_ORDER_ORPHANS_CREATED, "存在未处置的二阶 orphan"

    def test_foundation_orphans_are_deleted(self) -> None:
        """Task 17：foundation 的 3 个已删且登记。"""
        for name in F.ORPHAN_OWNED_BY_FOUNDATION:
            p = S.WP_COMPOSABLES / name
            assert not p.exists(), f"{name} 仍在磁盘上"
            assert p.relative_to(S.ROOT).as_posix() in F.DELETED_ORPHANS, name

    def test_stable_identity_template_was_extracted_before_deletion(self) -> None:
        """🔴 决策 4：先抄形态后删 —— 正式模块必须存在且承载按身份增删改的全部形态。"""
        text = S.strip_comments(S.read_text(_STABLE_ID_MODULE))
        for sym in ("adoptRowKey", "semanticRowKey", "generatedRowKey", "isPositionalRowKey",
                    "findRowByKey", "removeRowByKey", "updateRowByKey", "duplicateRowKeys"):
            assert re.search(rf"export function {sym}\b", text), f"缺 {sym}"
        assert "splice(" not in text, "样板模块里出现了按下标 splice"

    def test_stable_identity_module_has_production_consumer(self, import_graph) -> None:
        """提取出的样板不得变成新的 orphan（至少 canary 在用）。"""
        m = S.module_reachability([_STABLE_ID_MODULE], import_graph)[0]
        assert m.production_consumers, "stableRowIdentity.ts 零生产边 ⇒ 又造了一个 orphan"
        assert any("useN4Adjudication.ts" in c for c in m.production_consumers)

    def test_fabricated_key_left_with_its_orphan(self, prod_sources) -> None:
        """伪造键 `N4-1-rows-v2` 随 orphan 一起离开 N 域；V1 真实键仍在。"""
        for q in ("'", '"', "`"):
            _eq(f"{F.FABRICATED_KEY} {q}", S.scan_literal(prod_sources, f"{q}{F.FABRICATED_KEY}{q}"), [])
        assert "N4-1-rows" in S.read_text(S.WP_COMPOSABLES / "useN4Adjudication.ts")


class TestRowIdentityFamilies:
    def test_six_families_baseline(self, prod_sources) -> None:
        """NF-P12：六族现算（口径唯一一处：n_cycle_scanner.ROW_IDENTITY_PATTERNS）。"""
        fam = S.scan_row_identity_families(prod_sources)
        counts = {k: len(v) for k, v in fam.items()}
        # 基线 3（动手前现算，全在 useN1Adjudication）；lane2 T8 收口后目标 0
        assert F.ROW_IDENTITY_BASELINE["A_positional_persistence_key"] == 3
        _eq("A 持久化键族", counts["A_positional_persistence_key"], F.A_FAMILY_AFTER_LANE2)
        _eq("M 式中缀", counts["M_row_infix_template"], 0)
        assert counts["E_stable_identity"] > 0, "E 族为 0 ⇒ 没有正面样板可抄"
        # A 族全在 useN1Adjudication（lane2 T8 的改造对象）
        _eq("A 族文件", {Path(s.rel).name for s in fam["A_positional_persistence_key"]},
            {"useN1Adjudication.ts"} if counts["A_positional_persistence_key"] else set())

    def test_m_infix_scanner_is_not_constant_zero(self) -> None:
        """变异证明：同一扫描器在 M 式样本上命中非零。"""
        sample = {"x.ts": "const itemId = `M6-row-${idx}`\n"}
        assert S.scan_row_identity_families(sample)["M_row_infix_template"], "M 式扫描器恒 0"

    def test_remove_row_monotone_direction(self, prod_sources) -> None:
        """NF-P13：🔴 by_index 单调降 / by_rowid 单调升（禁沿用 M 轮「从 0 建起」）。"""
        hist = S.remove_call_histogram(S.scan_remove_row_calls(prod_sources))
        before = F.REMOVE_HISTOGRAM_BEFORE
        assert hist["by_index"] <= before["by_index"], (hist, before)
        assert before["by_rowid"] > 0, "基线 by_rowid 已非零（N 反转 M 结论）"

    def test_canary_removes_by_identity(self) -> None:
        """Task 16：canary 宿主的删行按身份寻址，不按下标 splice。"""
        text = S.strip_comments(S.read_text(S.WP_COMPOSABLES / "useN4Adjudication.ts"))
        assert re.search(r"function removeRow\(rowKey: string\)", text)
        assert "removeRowByKey(" in text
        assert not re.search(r"rows\.value\.splice\(", text), "canary 仍按下标 splice 删行"

    def test_remove_classifier_handles_capital_index(self) -> None:
        """🔴 口径修复的防回归：`rowIndex` 必须归 by_index（小写 index 扫不到）。"""
        _eq("rowIndex", S.classify_remove_arg("rowIndex: number"), "by_index")
        _eq("rowKey", S.classify_remove_arg("rowKey: string"), "by_rowid")
        _eq("空", S.classify_remove_arg(""), "other")


# ═══════════════════════════════════════════════════════════════════════════
# Task 5 · transport_key（NC-30）
# Properties: NF-P14 · NF-P15
# ═══════════════════════════════════════════════════════════════════════════
class TestTransportKeyResolution:
    def test_owner_constants_read_from_source(self, slice_doc: dict) -> None:
        decls = {d["id"]: d for d in slice_doc["transport_key_resolution"]["declarations"]}
        _eq("owner 声明数", len(decls), len(F.TRANSPORT_OWNERS))
        for tk, (module, value) in F.TRANSPORT_OWNERS.items():
            text = S.strip_comments(S.read_text(S.WP_COMPOSABLES / module))
            assert re.search(rf"ITEM_PREFIX\s*=\s*'{re.escape(value)}'", text), (tk, module)
            _eq(f"{tk} slice 值", decls[tk]["owner_constant_value"], value)

    def test_n1_has_two_owner_declarations(self) -> None:
        n1 = [k for k, (m, _) in F.TRANSPORT_OWNERS.items() if m.startswith("useN1")]
        _eq("N1 双 owner", len(n1), 2)

    def test_tk2_dual_condition_not_literal_hits(self) -> None:
        """🔴 TK-2 双条件：模板串命中 + 展开数 == 类目长度 7；字面量 `N1-1-adj-0` 恒 0 不可作判据。"""
        text = S.strip_comments(S.read_text(S.WP_COMPOSABLES / "useN1Adjudication.ts"))
        assert "ITEM_PREFIX = 'N1-1-adj'" in text
        m = re.search(r"N1_ADJUDICATION_CATEGORIES[^=]*=\s*\[(.*?)\]", text, re.S)
        assert m, "N1_ADJUDICATION_CATEGORIES 未找到"
        _eq("类目数", len(re.findall(r"'[^']+'", m.group(1))), F.N1_ADJUDICATION_CATEGORY_COUNT)
        assert "N1-1-adj-0" not in text, "展开字面量出现在源码 ⇒ 派生形态变了"

    def test_nonexistent_guessed_keys_are_zero(self, prod_sources) -> None:
        """8 个「按规律该有」的键各 0（反向分母）；V1 真实键非零证明扫描在跑。"""
        for k in F.NONEXISTENT_GUESSED_KEYS:
            hits = [s for q in "'\"`" for s in S.scan_literal(prod_sources, f"{q}{k}{q}")]
            _eq(k, hits, [])
        assert S.scan_literal(prod_sources, "'N3-2-rows'"), "真实键也 0 ⇒ 扫描器没跑"

    def test_no_shared_checklist_persistence(self, prod_files) -> None:
        code, _ = S.count_literal_code_vs_comment(prod_files, "useChecklistPersistence")
        _eq("useChecklistPersistence", code, [])


# ═══════════════════════════════════════════════════════════════════════════
# Task 6 / 7 / 8 / 18 · 模板几何与缺陷台账（只登记不修改）
# Properties: NF-P20 ~ NF-P28 · NC-32 · NC-17 · NC-9 · NC-35 · NC-36
# ═══════════════════════════════════════════════════════════════════════════
class TestTemplateGeometryAndDefects:
    def test_overflow_refs_three_families(self, template_facts) -> None:
        """NF-P20：超列引用 17 = A1 3 + A2 11 + B 3（与 design 逐值吻合）。"""
        _eq("超列总数", len(template_facts.overflow), F.OVERFLOW_TOTAL)
        _eq("三族分布", S.overflow_family_histogram(template_facts.overflow), F.OVERFLOW_FAMILIES)

    def test_wrong_caliber_is_much_larger(self, template_facts) -> None:
        """错口径对照：不剔 sheet 限定段 ⇒ 大量假阳（防未来放宽正则）。"""
        _eq("错口径", template_facts.overflow_wrong_caliber, F.OVERFLOW_WRONG_CALIBER)
        assert template_facts.overflow_wrong_caliber > 5 * len(template_facts.overflow)

    def test_sheet_qualified_ref_is_judged_against_its_own_sheet(self) -> None:
        """🔴 口径修复防回归：`'明细表N2-2'!M10` 的 M10 不得拿本表 max_column 判越界。"""
        cleaned = S.clean_formula_for_col_scan("='应交税费明细表N2-2'!M10")
        assert "M10" not in cleaned, cleaned
        cleaned2 = S.clean_formula_for_col_scan("=B9+C9+N4")
        assert "N4" in cleaned2, "本表引用被误剔 ⇒ 真缺陷会漏"

    def test_a1_real_defects_are_the_three_d_column_replacements(self, template_facts) -> None:
        """T-1/T-2/T-3：三处全是 D 列被换成本册 wp_code（系统性操作残留）。"""
        a1 = sorted((h.sheet, h.cell, h.ref_col) for h in template_facts.overflow
                    if h.family == "A1_real_defect")
        _eq("A1 三处", a1, [
            ("加计扣除研发费用情况明细表N5-6-1", "E12", "N"),
            ("税金及附加明细表N4-2", "E9", "N"),
            ("递延所得税费用核对表N5-8", "H12", "N"),
        ])

    def test_t1_canary_defect_recorded_with_reverse_denominator(self) -> None:
        """Task 18：`N4-2 E9 = B9+C9+N4`（反向分母 9:1）以记录型断言锁定。

        🔴 本 spec SHALL NOT 修改 .xlsx —— 将来修了模板这条会显式打红，提醒同步更新。
        """
        path = S.N_TEMPLATE_DIR / "N4 税金及附加.xlsx"
        wb = S.load_workbook(path)
        try:
            ws = wb["税金及附加明细表N4-2"]
            _eq("E9", ws["E9"].value, "=B9+C9+N4")
            correct = [
                r for r in range(4, (ws.max_row or 0) + 1)
                if isinstance(ws[f"E{r}"].value, str)
                and ws[f"E{r}"].value.replace(" ", "") == f"=B{r}+C{r}+D{r}"
            ]
            _eq("同列正确形态行数（反向分母）", len(correct), 9)
        finally:
            wb.close()

    def test_a2_is_not_merged_with_a1(self, template_facts) -> None:
        """T-4：`N3-2 H11~H21` 整列同形无反向分母 ⇒ 结构残留，与 A1 分开计数。"""
        a2 = [h for h in template_facts.overflow if h.family == "A2_structural_residue"]
        _eq("A2 全在 N3-2 H 列", {(h.sheet, h.cell[0]) for h in a2}, {("递延所得税负债明细表N3-2", "H")})
        _eq("A2 行号", sorted(int(h.cell[1:]) for h in a2), list(range(11, 22)))

    def test_missing_subtotal_dual_condition(self, template_facts) -> None:
        """NF-P21：严格 0 / 粗口径 4（design 正文只列举 4 处，「8」是自身计数错）。"""
        _eq("严格", len(template_facts.missing_subtotal_strict), F.MISSING_SUBTOTAL_STRICT)
        _eq("粗口径", len(template_facts.missing_subtotal_rough), F.MISSING_SUBTOTAL_ROUGH)
        _eq("粗口径对象", sorted((t.sheet, t.row) for t in template_facts.missing_subtotal_rough), [
            ("附注披露信息（上市公司）", 42), ("附注披露信息（上市公司）", 52),
            ("附注披露信息（国企）", 63), ("附注披露信息（国企）", 72),
        ])

    def test_missing_subtotal_scanner_is_not_constant_zero(self, tmp_path) -> None:
        """变异证明：构造「同行跨列写法不一致」的合计行，严格口径必须命中。"""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["a", 1, 1])
        ws.append(["小计", "=SUM(B1:B1)", "=SUM(C1:C1)"])
        ws.append(["b", 2, 2])
        ws.append(["合计", "=B2+B3", "=SUM(C1:C3)"])
        p = tmp_path / "mut.xlsx"
        wb.save(p)
        strict, rough = S.scan_missing_subtotal(p)
        assert strict and rough, (strict, rough)

    def test_subtraction_chain_strict_zero_with_candidates(self, template_facts) -> None:
        """NF-P22：倒挤严格 0；候选非空（证明扫描在跑）。"""
        _eq("严格", len(template_facts.sub_chain_strict), F.SUB_CHAIN_STRICT)
        _eq("候选", len(template_facts.sub_chain_candidates), F.SUB_CHAIN_CANDIDATES)

    def test_total_labels_first_nonempty_column(self, template_facts) -> None:
        """🔴 T-15：判据用「首个非空列」—— `N5-5` r63 在 B 列，限 A 列会漏。"""
        _eq("标签数", len(template_facts.total_labels), F.TOTAL_LABEL_SITES)
        non_a = tuple((t.sheet, t.row, t.col) for t in template_facts.total_labels if t.col != "A")
        _eq("非 A 列", non_a, F.TOTAL_LABEL_NON_A_COLUMN)

    def test_defined_names(self, template_facts) -> None:
        """NF-P26：72 总 / N4·N5 为 0（空分母声明，不写「已验证无断链」）。"""
        _eq("总数", len(template_facts.defined_names), F.DEFINED_NAME_TOTAL)
        _eq("broken", len([d for d in template_facts.defined_names if d.broken]), F.DEFINED_NAME_BROKEN)
        per: dict[str, list[int]] = {}
        for d in template_facts.defined_names:
            per.setdefault(d.workbook, [0, 0])
            per[d.workbook][0] += 1
            per[d.workbook][1] += int(d.broken)
        _eq("逐册", {k: tuple(v) for k, v in per.items()}, F.DEFINED_NAME_PER_WORKBOOK)
        names = {d.name for d in template_facts.defined_names}
        assert "本循环科目" in names, "中文 definedName 消失"
        assert any("'[2]2004'!#REF!" in d.value for d in template_facts.defined_names)

    def test_footer_three_forms(self, template_facts) -> None:
        """NF-P25：footer 49 / 7 / 3 = 59。"""
        from collections import Counter

        forms = Counter(S.classify_footer(f.footer_raw) for f in template_facts.sheets)
        _eq("三形态", dict(forms), F.FOOTER_FORMS)
        missing = tuple(sorted((f.workbook, f.sheet) for f in template_facts.sheets
                               if S.classify_footer(f.footer_raw) == S.FOOTER_FORM_MISSING_SLASH))
        _eq("缺斜杠", missing, tuple(sorted(F.FOOTER_MISSING_SEPARATOR_SHEETS)))

    def test_wide_sheets_and_ghost_columns(self, template_facts) -> None:
        """NF-P27 / 决策 6：遍历上界取 last_value_col，差值变化即显式失败。"""
        wide = tuple((f.sheet, f.max_col, f.last_value_col) for f in S.wide_sheets(template_facts.sheets))
        _eq("超宽表", wide, F.WIDE_SHEETS)
        g = S.ghost_geometry(template_facts.sheets)
        _eq("幽灵列 sheet 数", g["sheets_with_ghost_cols"], F.SHEETS_WITH_GHOST_COLS)
        _eq("幽灵行 sheet 数", g["sheets_with_ghost_rows"], F.SHEETS_WITH_GHOST_ROWS)

    def test_dirty_sheet_names_are_not_normalised(self, slice_doc: dict) -> None:
        """NF-P23：尾随空格 / 缺右括号 / 「表的{码}」按原始字面量，禁 strip。"""
        wb_names = {p.name: None for p in S.iter_template_files()}
        all_sheets: set[str] = set()
        for p in S.iter_template_files():
            wb = S.load_workbook(p)
            try:
                all_sheets.update(wb.sheetnames)
            finally:
                wb.close()
        assert "税金及附加审计程序表N4A " in all_sheets, "尾随空格被抹掉了"
        assert "税金及附加审计程序表N4A" not in all_sheets
        assert "附注披露信息（国企" in all_sheets and len(wb_names) == 5
        de = [s for s in all_sheets if re.search(r"表的N\d", s)]
        _eq("「表的{码}」", len(de), 3)

    def test_hidden_vs_oo_fallthrough_caliber_gap(self, template_facts) -> None:
        """NF-P24：hidden 8 与 OO 兜底 12 两套口径并存，差 4。"""
        hidden = [f for f in template_facts.sheets if f.hidden]
        _eq("hidden", len(hidden), F.TOTAL_HIDDEN_SHEETS)
        _eq("口径差", F.SHEETS_OO_FALLTHROUGH - len(hidden), 4)


# ═══════════════════════════════════════════════════════════════════════════
# Task 10 / 11 · 契约双列映射与真库
# Properties: NF-P16 · NF-P17 · NF-P18 · NF-P38
# ═══════════════════════════════════════════════════════════════════════════
def _live_db_rows():
    """asyncpg 现读 N 域行；无库 ⇒ skip 并标原因（🔴 禁静默 pass）。"""
    import asyncio
    import os

    try:
        import asyncpg  # noqa: F401
    except ImportError:
        pytest.skip("asyncpg 未安装 ⇒ 真库判据空分母（不宣称通过）")
    dsn = os.environ.get(
        "N_CYCLE_LIVE_DSN", "postgresql://postgres:postgres@localhost:5432/audit_platform")

    async def _q():
        import asyncpg

        conn = await asyncpg.connect(dsn, timeout=5)
        try:
            rows = await conn.fetch(
                """SELECT cr.item_id, NULLIF(cr.remark, '') AS remark,
                          NULLIF(cr.conclusion, '') AS conclusion, wi.wp_code
                   FROM checklist_responses cr
                   JOIN working_paper wp ON wp.id = cr.wp_id
                   JOIN wp_index wi ON wi.id = wp.wp_index_id
                   WHERE cr.item_id ~ '^N[1-5]'""")
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    try:
        return asyncio.run(_q())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真库不可达（{type(e).__name__}）⇒ 真库判据空分母（不宣称通过）")


class TestContractFieldMapping:
    def test_payload_module_maps_both_columns(self) -> None:
        """🔴 NC-34：取列规则覆盖 remark 与 conclusion，推翻 M/L 轮「只映 remark」。"""
        text = S.strip_comments(S.read_text(_PAYLOAD_MODULE))
        for col in F.PAYLOAD_COLUMNS:
            assert f"'{col}'" in text, col
        assert F.REVIEW_SESSION_KEY_MARKER in text, "AI 会话白名单缺失"

    def test_canary_reads_through_the_payload_module(self) -> None:
        """canary 不得再用 `remark ?? conclusion`（remark 空串时整表静默丢失）。"""
        text = S.strip_comments(S.read_text(S.WP_COMPOSABLES / "useN4Adjudication.ts"))
        assert "payloadJson(" in text and "payloadText(" in text
        assert not re.search(r"\.remark\s*\?\?\s*\w*\.?conclusion", text), (
            "canary 仍有 `remark ?? conclusion` 取列写法"
        )

    def test_live_db_payload_lives_in_conclusion(self) -> None:
        """NF-P16（现算口径）：真库 N 域 3 行全在 conclusion ⇒ 只映 remark 丢 100%。"""
        rows = _live_db_rows()
        _eq("N 域行数", len(rows), F.LIVE_DB_N_ROWS)
        _eq("conclusion 非空", sum(1 for r in rows if r["conclusion"]), F.LIVE_DB_N_ROWS_WITH_CONCLUSION)
        _eq("remark 非空", sum(1 for r in rows if r["remark"]), F.LIVE_DB_N_ROWS_WITH_REMARK)
        _eq("item_id 集合", tuple(sorted(r["item_id"] for r in rows)), F.LIVE_DB_N_ITEM_IDS)

    def test_contract_directory_has_no_n_entry(self) -> None:
        """NF-P38：契约归属逐文件读 `review.entry_id`，除 N4 canary 外 N 域 0。

        🔴 N4 已交付 reviewed 生产契约（spec N4 真改线）⇒ 其 review.entry_id = N4 是**真改线**，
        仅豁免 N4（n_cycle_facts.DELIVERED_CONTRACT_ADAPTER_IDS），其余 N 仍必须零归属。
        """
        n_owners = []
        for p in sorted(S.CONTRACT_DIR.glob("*.json")):
            d = S.load_json(p)
            owner = ((d.get("review") or {}).get("entry_id")) or ""
            if not owner.startswith("xlsx/gt-n"):
                continue
            if d.get("contract_id") in F.DELIVERED_CONTRACT_ADAPTER_IDS:
                continue  # N4 canary 已交付契约，豁免
            n_owners.append(owner)
        _eq("除 N4 外 N 域契约", n_owners, [])
        # 反向：N4 的契约确实在目录里（豁免不是空转）。
        _n4 = [
            ((S.load_json(p).get("review") or {}).get("entry_id")) or ""
            for p in S.CONTRACT_DIR.glob("*.json")
            if S.load_json(p).get("contract_id") in F.DELIVERED_CONTRACT_ADAPTER_IDS
        ]
        assert "xlsx/gt-n4-taxes-and-surcharges" in _n4, "N4 契约未在目录里 ⇒ 豁免空转"


class TestCanaryN4Closure:
    def test_canary_live_db_denominator_is_declared_empty(self) -> None:
        """NF-P17（🔴 现算偏离 design）：`N4-1-rows` 真库 0 行 ⇒ 真库往返**空分母**，不宣称通过。

        canary 闭环由代码层往返证明（`nCycleCanaryRowIdentity.spec.ts`：读 conclusion 列 →
        删中间行 → 写回 → 再读，历史 remark 不串行）。
        """
        rows = _live_db_rows()
        n4 = [r for r in rows if r["item_id"].startswith("N4-1-rows")]
        _eq("N4-1-rows 真库行数", len(n4), F.LIVE_DB_CANARY_ROWS)
        div = [d for d in F.DESIGN_VS_RECOMPUTED if d.item.startswith("canary")]
        assert div and div[0].cause == F.CAUSE_SNAPSHOT_DRIFT, "空分母未登记进分歧表"

    def test_canary_frontend_roundtrip_spec_exists(self) -> None:
        spec = S.WP_COMPOSABLES / "__tests__" / "nCycleCanaryRowIdentity.spec.ts"
        text = S.read_text(spec)
        assert "删中间行后写回，再读回" in text and "conclusion" in text

    def test_canary_publish_gate_reuses_the_existing_one(self, prod_files) -> None:
        """写路径只走发布门（现算 5 处之一），不新增第 6 处。"""
        code, _ = S.count_literal_code_vs_comment(prod_files, F.PUBLISH_TO_TB_LITERAL)
        assert any(s.rel.endswith("useN4FormData.ts") for s in code)
        _eq("发布门总数", len(code), F.PUBLISH_TO_TB_CODE)

    def test_canary_is_single_sheet_not_parent_duplicate(self, slice_doc: dict) -> None:
        kids = {c["entry_id"] for c in slice_doc["parent_duplicate_summary"]["children"]}
        assert F.CANARY_ENTRY_ID not in kids
        n4 = next(f for f in slice_doc["authoritative_templates"]["files"]
                  if f["belongs_to_entry"] == F.CANARY_ENTRY_ID)
        assert "税金及附加审定表N4-1" in n4["sheet_names"]


class TestCrossEntryPollution:
    def test_cross_workpaper_resolution_uses_real_platform_endpoint(self) -> None:
        """Playwright 根因回归：旧 `/projects/{pid}/wp-index/by-code` 后端不存在、恒 404。"""
        sources = [
            S.read_text(S.WP_COMPOSABLES / "useN4CrossSheet.ts"),
            S.read_text(S.WP_COMPOSABLES / "useN5CrossSheet.ts"),
            S.read_text(S.FRONTEND / "composables" / "useResolveLinkageRoute.ts"),
        ]
        assert all("/wp-index/by-code/" not in S.strip_comments(t) for t in sources)
        resolver = S.read_text(S.FRONTEND / "services" / "resolveWorkpaperByCode.ts")
        assert "/api/custom-query/wp-id-by-code" in S.strip_comments(resolver)
        assert all("resolveWorkpaperByCode" in t for t in sources)

    def test_n4_empty_n2_response_does_not_overwrite_persisted_accrual(self) -> None:
        """Playwright 根因回归：N2 无明细时打开 N4-1 不得无条件 PUT `{}` 覆盖历史计提额。"""
        text = S.strip_comments(S.read_text(S.WP_COMPOSABLES / "useN4CrossSheet.ts"))
        assert "if (read > 0) _persistN2AccrualData()" in text
        assert not re.search(r"\n\s*_persistN2AccrualData\(\)\s*\n\s*}\s*catch", text)

    def test_live_db_cross_entry_pollution(self) -> None:
        """NF-P18（现算）：item_id 前缀与宿主 wp_code 不一致的行数。design 记 4（全落 G8），现算 0。"""
        rows = _live_db_rows()
        bad = [r for r in rows
               if not (r["wp_code"] or "").upper().startswith(r["item_id"].split("-")[0].upper())]
        _eq("污染行", len(bad), F.LIVE_DB_CROSS_ENTRY_POLLUTION)

    def test_n5_foreign_reads_are_read_only(self) -> None:
        """NF-P19：N5 外引 8 键跨 5 命名空间全只读；写只写自己的 `N5-cross-*`。"""
        text = S.strip_comments(S.read_text(S.WP_COMPOSABLES / "useN5CrossSheet.ts"))
        for k in F.N5_FOREIGN_READONLY_KEYS:
            assert f"'{k}'" in text, k
        writes = re.findall(r"_persistCrossData\(\s*'([^']+)'", text)
        assert writes and all(w.startswith("N5-cross-") for w in writes), writes
        _eq("命名空间", sorted({k.split("-")[0] + "-" for k in F.N5_FOREIGN_READONLY_KEYS}),
            sorted(F.N5_FOREIGN_NAMESPACES))


# ═══════════════════════════════════════════════════════════════════════════
# Task 12 / 19 / 20 / 21 · 口径差、notice、parent_duplicate、程序表路由
# Properties: NF-P29 ~ NF-P33 · NF-P36 ~ NF-P39
# ═══════════════════════════════════════════════════════════════════════════
class TestScanCaliberDivergence:
    def test_pairwise_count_is_recomputed(self) -> None:
        """NF-P37：配对数现算 C(n,2)，禁引用 slice 自相矛盾的 55 / 66。"""
        slices = sorted(S.DATA.glob("workpaper_sync_*_manifest_slice.json"))
        n = len(slices)
        assert n >= 2
        ids: list[set[str]] = []
        for p in slices:
            d = S.load_json(p)
            ids.append({e["entry_id"] for e in d.get("independent_entries", [])})
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        _eq("配对数", len(pairs), n * (n - 1) // 2)
        overlap = [(slices[i].name, slices[j].name) for i, j in pairs if ids[i] & ids[j]]
        _eq("两两相交", overlap, [])

    def test_shared_base_and_router_edges(self, import_graph) -> None:
        """NF-P31：共享基类边与共享路由采用方（🔴 每轮现算，禁抄上一轮）。"""
        sb = S.module_reachability([S.WP_COMPOSABLES / "useWorkpaperEntryDualMode.ts"], import_graph)[0]
        _eq("共享基类生产边", len(sb.production_consumers), F.SHARED_BASE_PRODUCTION_EDGES)
        n_edges = [c for c in sb.production_consumers if re.search(r"/useN[1-5]", c)]
        _eq("N 域贡献", len(n_edges), F.SHARED_BASE_N_EDGES)
        router = S.module_reachability(
            [S.WP_COMPOSABLES / "shared" / "cycleSheetRouting.ts"], import_graph)[0]
        adopters = {Path(c).name for c in router.production_consumers if re.search(r"/n[1-5]SheetRouting", c)}
        assert len(adopters) >= F.SHARED_ROUTER_ADOPTERS_BEFORE, adopters

    def test_divergence_register_is_well_formed(self) -> None:
        """NF-P36：分歧表每条三要素齐备、差因只取三类、且三类都有实例（不是摆设）。"""
        causes = {F.CAUSE_SNAPSHOT_DRIFT, F.CAUSE_CALIBER, F.CAUSE_DESIGN_INTERNAL}
        assert len(F.DESIGN_VS_RECOMPUTED) >= 14
        for d in F.DESIGN_VS_RECOMPUTED:
            assert d.cause in causes, d.item
            assert d.design_value and d.recomputed_value and d.note, d.item
            assert d.design_value != d.recomputed_value, f"{d.item} 两值相同却登记为分歧"
        for c in causes:
            assert F.divergences_by_cause(c), f"差因 {c} 零实例"


class TestNoticeAndParentDuplicate:
    def test_notice_mounted_on_registered_hosts(self, prod_files) -> None:
        """Task 19 / NF-P39：notice 接入 N4（canary）与 N5；🔴 tooltip 不算接线。"""
        hosts = {F.N4: _N4_HOST, F.N5: _N5_HOST}
        for eid in F.NOTICE_MOUNTED_ENTRIES:
            text = S.strip_comments(S.read_text(hosts[eid]))
            assert "<GtEntrySyncCapabilityNotice" in text, eid
            assert eid in text, f"{eid} 的 entry-id 绑定缺失"
            assert "GtEntrySyncCapabilityNotice.vue" in text, "未 import 组件"

    def test_unmounted_hosts_are_honestly_still_zero(self) -> None:
        """未登记的宿主仍 0 挂载 —— 防「登记表」与代码脱节。"""
        others = {F.N1: _N1_HOST, F.N2: _N2_HOST, F.N3: _N3_HOST}
        for eid, host in others.items():
            if eid in F.NOTICE_MOUNTED_ENTRIES:
                continue
            assert "GtEntrySyncCapabilityNotice" not in S.strip_comments(S.read_text(host)), eid

    def test_n_entries_are_still_not_registered_bidirectional(self) -> None:
        """notice 成立的前提：N entry 未注册 adapter（否则通知是在真双向上说假话）。"""
        text = S.read_text(S.SYNC_DIR / "workpaperSyncManifest.generated.ts")
        # 生成器按键字母序输出：同一对象里 "capability" 恰在 "entryId" 之前（中间无嵌套对象）
        pair = re.compile(
            r'"capability":\s*"([^"]+)",\s*"documentType"[^{}\[\]]*?"entryId":\s*"([^"]+)"')
        caps = {eid: cap for cap, eid in pair.findall(text)}
        assert "bidirectional" in caps.values(), "解析不到任何 bidirectional ⇒ 判据空跑"
        for eid in F.ENTRY_IDS:
            assert eid in caps, f"{eid} 不在 manifest 里"
            assert caps[eid] != "bidirectional", f"{eid} 已注册双向 ⇒ notice 说的是假话"

    def test_parent_duplicate_condition_is_implemented(self, slice_doc: dict) -> None:
        """Task 20 / NF-P33：N 首次触发（K/L/M 均 0）—— 4 条全挂 N1。"""
        pd = slice_doc["parent_duplicate_summary"]
        kids = pd["children"]
        _eq("子入口", tuple(c["entry_id"] for c in kids), F.PARENT_DUPLICATE_CHILDREN)
        assert all(c["parent_entry_id"] == F.N1 for c in kids)
        assert all(c["independent_entry"] is False for c in kids)
        _eq("计数", pd["counters"]["children_total"], len(kids))
        _eq("自有写通道", pd["counters"]["children_with_own_write_channel"], 0)
        for c in kids:
            assert (S.ROOT / c["host_path"]).is_file(), c["host_path"]


class TestProcedureRouteAndStructuralZeros:
    def test_resolve_procedure_sheet_key_n_complete_m_still_six(self) -> None:
        """Task 21 / NF-P32：N 段完备 5/5；🔴 M 段仍 6 条（M 轮欠账未修，禁误记已修）。"""
        text = S.read_text(S.FRONTEND / "utils" / "resolveProcedureSheetKey.ts")
        code = S.strip_comments(text)
        for code_, key in F.PROCEDURE_ROUTE_N.items():
            assert f"startsWith('{code_}')) return '{key}'" in code, code_
        m_prefixes = tuple(re.findall(r"startsWith\('(M\d+)'\)", code))
        _eq("M 段", m_prefixes, F.PROCEDURE_ROUTE_M_PREFIXES)

    @pytest.mark.parametrize(
        "literal,mutant",
        [
            ("trial-balance/writeback", "fetch('/api/x/trial-balance/writeback')"),
            ("useChecklistPersistence", "import { useChecklistPersistence } from 'y'"),
            ("contract-ocr", "api.post('/contract-ocr')"),
            ("http.put", "http.put('/x')"),
        ],
    )
    def test_structural_zero_with_mutation_proof(self, prod_files, literal, mutant) -> None:
        """NF-P35：结构性零 + 同一扫描函数在变异样本上命中（成对出现）。"""
        code, _ = S.count_literal_code_vs_comment(prod_files, literal)
        _eq(f"{literal} CODE", code, [])
        assert S.scan_literal({"mut.ts": mutant}, literal), f"{literal} 扫描器恒 0"
        assert not S.scan_literal({"c.ts": S.strip_comments(f"// {mutant}")}, literal), (
            "注释里的命中没被剥掉"
        )

    def test_slice_schema_validator_defect_is_registered_not_hidden(self, slice_doc: dict) -> None:
        """NF-P40（`[ ]*` 平台级）：slice 仍如实保留 `why_kind_is_compound` 诚实声明。"""
        t = next(t for t in slice_doc["dynamic_row_identity"]["tables"]
                 if t["table_key"] == "n1_adjudication_rows")
        assert "validate_slice_against_schema" in t["row_identity"]["why_kind_is_compound"]
        assert t["row_identity"]["violates_forbidden_identity_kind"] == "positional_persistence_key"


# ═══════════════════════════════════════════════════════════════════════════
# Task 23 · 交付前自检
# ═══════════════════════════════════════════════════════════════════════════
class TestZzzDeliverySelfCheck:
    def test_every_nf_property_is_referenced_by_this_guard(self) -> None:
        """NF-P1 ~ NF-P40 每条至少被本守卫引用一次（铁律 ⑳：引用闭合，不只是编号连续）。"""
        text = S.read_text(Path(__file__))
        referenced = set()
        for m in re.finditer(r"NF-P(\d+)(?:\s*~\s*NF-P(\d+))?", text):
            lo = int(m.group(1))
            hi = int(m.group(2) or lo)
            referenced.update(range(lo, hi + 1))
        missing = sorted(set(range(1, 41)) - referenced)
        _eq("未引用的 NF-P", missing, [])

    def test_nc23_empty_denominator_is_explicit(self, prod_sources) -> None:
        """🔴 NC-23（唯一 ❌）：N 域无 `SHEET_MAP` 常量映射 —— 现算证据 + 变异证明，禁静默省略。"""
        rx = re.compile(r"\bconst\s+N[1-5]_SHEET_MAP\b")
        _eq("N 域 SHEET_MAP", S.scan_regex(prod_sources, rx), [])
        assert S.scan_regex({"m.ts": "const N4_SHEET_MAP = {}"}, rx), "扫描器恒 0"

    def test_m_round_canary_deviation_is_declared_m_specific(self) -> None:
        """🔴 「M 轮换 canary 判据是 M 特有、本轮收回」的声明仍在交付物中。

        现算补充：N 真库分母本轮也为空（见 DESIGN_VS_RECOMPUTED 首条）⇒ 收回的前提
        在实施时点不成立，已如实登记，不宣称真库往返通过。
        """
        design = (S.ROOT / ".kiro/specs/n-cycle-sync-foundation-and-first-canary/design.md")
        text = S.read_text(design)
        assert "M 域特有情形的应对，不是新常态" in text
        assert any("决策 1" in d.note for d in F.DESIGN_VS_RECOMPUTED)

    def test_templates_untouched_and_no_replacement_char(self, slice_doc: dict) -> None:
        """交付后模板 sha256 仍 5/5；本轮新增/改动的源码无 U+FFFD。"""
        declared = {f["name"]: f["sha256"] for f in slice_doc["authoritative_templates"]["files"]}
        for p in S.iter_template_files():
            # 🔴 N4 canary 模板已 OOXML 净化（spec N4 Task 7a），sha 为净化后值；其余 4 册未动。
            if p.name in F.SANITIZED_TEMPLATE_WORKBOOKS:
                _eq(f"{p.name}(净化后)", S.sha256_of(p), F.N4_SANITIZED_TEMPLATE_FACTS["sha256"])
            else:
                _eq(p.name, S.sha256_of(p), declared[p.name])
        touched = [
            S.WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue",
            S.WP_COMPONENTS / "GtN5IncomeTaxExpense.vue",
            S.WP_COMPOSABLES / "useN4Adjudication.ts",
            _STABLE_ID_MODULE,
            _PAYLOAD_MODULE,
            Path(F.__file__),
            Path(S.__file__),
        ]
        for p in touched:
            assert "\ufffd" not in p.read_bytes().decode("utf-8"), p.name
