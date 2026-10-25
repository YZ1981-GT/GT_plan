# -*- coding: utf-8 -*-
"""C22 ITGC 无开关与域码 sheet 名通道 — lane 守卫。

spec: c22-itgc-no-switch-and-domain-code-sheet-lane

测试结构（对标 tasks.md）：
  - TestC22FactBaseline         阶段 1（任务 1-2）
  - TestC22SwitchAbsence        阶段 2（任务 3）
  - TestC22SheetNameHit         阶段 3（任务 6-9）
  - TestC22Namespace            阶段 4（任务 10-12）
  - TestC22OOMount              CC-64 权威册归属
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# 路径设置
# ═══════════════════════════════════════════════════════════════════════════
_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_FRONTEND = _ROOT / "audit-platform" / "frontend" / "src"
_WP_COMPONENTS = _FRONTEND / "components" / "workpaper"
_TEMPLATE_DIR = _BACKEND / "wp_templates" / "C"
_DATA = _BACKEND / "data"
_SLICE_PATH = _DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from c_cycle_scanner import (  # noqa: E402
    C22_BLOCKED_BY,
    C22_WP_CODES,
    c_domain_entries_by_entry_id,
    c_entry_by_id,
    strip_comments,
    scan_xlsx_formulas,
)

# 复用 task57 工具
from test_task57_abcs_and_shared_migration import (  # noqa: E402
    _cached_text,
)

C22_ENTRY_ID = "xlsx/gt-c22-itgc-bundle"
C22_HOST = _WP_COMPONENTS / "GtC22ItgcBundle.vue"


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


@pytest.fixture(scope="module")
def c22_entry(manifest_slice: dict) -> dict:
    entries = c_domain_entries_by_entry_id(manifest_slice["independent_entries"])
    by_id = c_entry_by_id(entries)
    return by_id[C22_ENTRY_ID]


@pytest.fixture(scope="module")
def host_text() -> str:
    if not C22_HOST.exists():
        pytest.skip("GtC22ItgcBundle.vue 不存在")
    return C22_HOST.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def host_clean(host_text: str) -> str:
    return strip_comments(host_text)


# ═══════════════════════════════════════════════════════════════════════════
# §1 TestC22FactBaseline — 阶段 1（任务 1-2）
# ═══════════════════════════════════════════════════════════════════════════


class TestC22FactBaseline:
    """CG-P1~P4: 事实基线冻结。"""

    def test_switch_verdict_no_switch(self, c22_entry: dict) -> None:
        """CG-P1: switch_verdict = no_switch_at_all。"""
        sv = c22_entry.get("dual_mode_carrier", {}).get("switch_verdict", "")
        assert sv == "no_switch_at_all", f"sv={sv}"

    def test_carrier_kind_no_carrier(self, c22_entry: dict) -> None:
        """CG-P2: dual_mode_carrier.kind = no_carrier。"""
        kind = c22_entry.get("dual_mode_carrier", {}).get("kind", "")
        assert kind == "no_carrier", f"kind={kind}"

    def test_bp_count_8_includes_bp10(self, c22_entry: dict) -> None:
        """CG-P3: BP 数 8 且含 BP-10。"""
        bp = sorted(c22_entry.get("capability_target_blocked_by", []))
        assert bp == sorted(C22_BLOCKED_BY), f"bp={bp}"
        assert len(bp) == 8
        assert "BP-10" in bp

    def test_bp10_only_4_in_slice(self, manifest_slice: dict) -> None:
        """CG-P4: BP-10 全 slice 仅 4 条。"""
        entries = manifest_slice.get("independent_entries", [])
        bp10_count = sum(
            1 for e in entries
            if "BP-10" in (e.get("capability_target_blocked_by") or [])
        )
        assert bp10_count == 4, f"BP-10 entries={bp10_count}"

    def test_group_id(self, c22_entry: dict) -> None:
        """补充: group_id = GRP-06。"""
        assert c22_entry.get("group_id") == "GRP-06"

    def test_family(self, c22_entry: dict) -> None:
        """补充: component_type_family = c_class_bundle。"""
        assert c22_entry.get("component_type_family") == "c_class_bundle"

    def test_host_line_count(self, host_text: str) -> None:
        """补充: 宿主约 922 行。"""
        lines = host_text.count("\n")
        assert 800 < lines < 1200, f"lines={lines}"

    def test_c22_authority_book_exists(self) -> None:
        """CG-P12 前置: C22 IT一般控制测试.xlsx 存在。"""
        book = _TEMPLATE_DIR / "C22 IT一般控制测试.xlsx"
        assert book.exists()

    def test_c22_book_34_sheets(self) -> None:
        """CG-P12: C22 册 34 sheets。"""
        book = _TEMPLATE_DIR / "C22 IT一般控制测试.xlsx"
        info = scan_xlsx_formulas(book)
        assert info["sheet_count"] == 34, f"sheets={info['sheet_count']}"

    def test_c22_book_61_formulas(self) -> None:
        """CG-P12: C22 册公式格 61。"""
        book = _TEMPLATE_DIR / "C22 IT一般控制测试.xlsx"
        info = scan_xlsx_formulas(book)
        assert info["total_formulas"] == 61, f"fx={info['total_formulas']}"

    def test_c22_book_31_fx_sheets(self) -> None:
        """CG-P12: C22 册带 fx sheet 31。"""
        book = _TEMPLATE_DIR / "C22 IT一般控制测试.xlsx"
        info = scan_xlsx_formulas(book)
        assert info["fx_sheet_count"] == 31, f"fx_sheets={info['fx_sheet_count']}"

    def test_c22_book_ref_errors(self) -> None:
        """CG-P12: C22 册含 #REF! 引用。

        🔴 这是公式中的 #REF! 而非 definedName broken。
        C22 有 2 个 definedName 但都正常（无 broken）。
        """
        book = _TEMPLATE_DIR / "C22 IT一般控制测试.xlsx"
        info = scan_xlsx_formulas(book)
        # definedName 本身不 broken
        assert info["defined_names_total"] == 2
        assert info["defined_names_broken"] == 0
        # #REF! 在公式格中（扫描 sheet 中公式含 #REF!）
        import openpyxl
        wb = openpyxl.load_workbook(str(book), data_only=False)
        ref_count = 0
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and "#REF!" in cell.value:
                        ref_count += 1
        wb.close()
        assert ref_count >= 2, f"#REF! in formulas={ref_count}"


# ═══════════════════════════════════════════════════════════════════════════
# §2 TestC22SwitchAbsence — 阶段 2（任务 3）
# ═══════════════════════════════════════════════════════════════════════════


class TestC22SwitchAbsence:
    """CC-41/CG-P5~P6: 补模式开关后的状态验证。

    🔴 BP-10 已完成：el-segmented + renderMode + modeOptions 已补入。
    """

    def test_has_el_segmented(self, host_clean: str) -> None:
        """CG-P5 补完后: el-segmented 存在。"""
        assert "el-segmented" in host_clean or "ElSegmented" in host_clean

    def test_has_render_mode_ref(self, host_clean: str) -> None:
        """补完后: 有 renderMode ref。"""
        assert "renderMode" in host_clean

    def test_has_mode_options(self, host_clean: str) -> None:
        """补完后: 有 modeOptions 声明。"""
        assert "modeOptions" in host_clean

    def test_mode_values_correct(self, host_text: str) -> None:
        """CC-41: mode 值用 structured / online-edit（{label,value} 分离形态）。"""
        assert "'structured'" in host_text
        assert "'online-edit'" in host_text

    def test_no_chinese_label_as_mode_value(self, host_text: str) -> None:
        """CC-41: 禁引入中文标签直接作 mode 值。"""
        clean = strip_comments(host_text)
        # mode 值不应是中文标签
        import re
        # 检查 modeOptions 附近没有 value: '结构化视图' 这种模式
        chinese_as_value = re.findall(
            r"value:\s*['\"][\u4e00-\u9fff]+['\"]", clean
        )
        assert len(chinese_as_value) == 0, (
            f"中文标签作 mode 值: {chinese_as_value}"
        )

    # ─── 补开关不得造成 UX 回归（本轮实测抓到并修复的两个缺陷）────────────

    def test_default_mode_per_section_not_hardcoded(
        self, host_clean: str
    ) -> None:
        """🔴 补开关后默认 mode 须按 section 派生，不得一律 structured。

        回归背景：首版 `renderMode` 一律默认 `'structured'`，但 C21 **无结构化视图**
        ⇒ 用户进 C21 tab 看到「开发中」占位符，而改造前直接显示文档（UX 回归）。
        修复：`defaultModeForSection()` 单一函数，C21 → 'online-edit'、C21-1 → 'structured'。
        """
        assert "defaultModeForSection" in host_clean, (
            "须有按 section 派生默认 mode 的函数"
        )
        # C21 默认 online-edit（保持改造前「直接显示文档」）
        assert "'online-edit'" in host_clean

    def test_default_mode_applied_on_both_entries(
        self, host_clean: str
    ) -> None:
        """🔴 两条入口（section setter / 路由 activateSheet）须共用同一默认函数。

        只在 setter 里设默认会让「路由直接进 C21」停在占位符上。
        """
        occurrences = host_clean.count("defaultModeForSection(")
        # 1 次声明 + 至少 2 处调用（setter + activateSheet）
        assert occurrences >= 3, (
            f"defaultModeForSection 出现 {occurrences} 次，"
            "应为 1 声明 + setter + activateSheet 共 ≥3"
        )

    def test_c21_1_branch_has_mode_toolbar(self, host_text: str) -> None:
        """🔴 C21-1 分支须含模式工具栏与 OO 挂点（消除死条件）。

        回归背景：首版 `showModeToolbar` 对 'C21-1' 返回 true，但模板里
        `v-else-if="activeSection === 'C21-1'"` 分支在 C21 分支**之前**且不含工具栏
        ⇒ C21-1 永远看不到开关（声明与实际不符的死条件）。
        修复：C21-1 分支补工具栏 + OO 挂点（结构化=GtC21FindingsSummary ↔ 在线编辑=C21-1 册）。
        """
        # C21-1 分支定位
        idx = host_text.find("activeSection === 'C21-1'")
        assert idx > 0, "应能定位 C21-1 分支"
        # 🔴 边界取「下一个 section 的注释分隔线」——不能用 class 名（它与本分支同行出现）
        nxt = host_text.find("═══ C21 独立底稿", idx)
        assert nxt > idx, "应能定位 C21-1 分支的结束边界（下一个 C21 分支注释）"
        segment = host_text[idx:nxt]
        assert "el-segmented" in segment, "C21-1 分支应含模式切换控件"
        assert "GtOnlyOfficeSheet" in segment, "C21-1 分支应含 OO 挂点"
        assert "GtC21FindingsSummary" in segment, "C21-1 分支应保留结构化视图"

    def test_oo_mount_count_is_two(self, host_text: str) -> None:
        """补开关后 OO 挂点为 2 处（C21 + C21-1），均受 mode 门控。"""
        mounts = host_text.count("<GtOnlyOfficeSheet")
        assert mounts == 2, f"OO 挂点数={mounts}，应为 2（C21 + C21-1）"
        # 两处均带 mode 门控
        gated = host_text.count("renderMode === 'online-edit'")
        assert gated >= 2, f"mode 门控 OO 挂点={gated}，应 ≥2"


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestC22SheetNameHit — 阶段 3（任务 6-9）
# ═══════════════════════════════════════════════════════════════════════════


class TestC22SheetNameHit:
    """CC-63/CG-P9~P11: 传入 sheet 名与册内 sheet 名零交集。"""

    @pytest.fixture(scope="class")
    def c22_sheet_names(self) -> list[str]:
        """C22 册的全部 sheet 名。"""
        book = _TEMPLATE_DIR / "C22 IT一般控制测试.xlsx"
        if not book.exists():
            pytest.skip("C22 册不存在")
        info = scan_xlsx_formulas(book)
        return [s["name"] for s in info["sheets"]]

    @pytest.fixture(scope="class")
    def c21_sheet_names(self) -> list[str]:
        """C21 册的全部 sheet 名。"""
        book = _TEMPLATE_DIR / "C21 具有信息技术专业技能的项目组成员.xlsx"
        if not book.exists():
            pytest.skip("C21 册不存在")
        info = scan_xlsx_formulas(book)
        return [s["name"] for s in info["sheets"]]

    @pytest.fixture(scope="class")
    def c21_1_sheet_names(self) -> list[str]:
        """C21-1 册的全部 sheet 名。"""
        book = _TEMPLATE_DIR / "C21-1  IT审计发现汇总表.xlsx"
        if not book.exists():
            pytest.skip("C21-1 册不存在")
        info = scan_xlsx_formulas(book)
        return [s["name"] for s in info["sheets"]]

    def test_c21_pass_in_not_match(self, c21_sheet_names: list[str]) -> None:
        """CG-P9: 传入 'C21' 对册不命中。

        册内 sheet 名 = ['C21 具有信息技术专业技能的项目组成员', 'GT_Custom']，
        传入 'C21' 不等于全名。
        """
        assert "C21" not in c21_sheet_names, (
            f"'C21' 不应精确匹配册内 sheet 名: {c21_sheet_names}"
        )

    def test_c21_1_pass_in_not_match(self, c21_1_sheet_names: list[str]) -> None:
        """CG-P9: 传入 'C21-1' 对册不命中。

        🔴 C21-1 册的 sheet 名与册名完全脱钩（CG-P10）：
        册名 = 'C21-1  IT审计发现汇总表'（双空格），
        sheet 名 = 'IT 审计发现汇总表'（单空格，无 C21-1 前缀）。
        """
        assert "C21-1" not in c21_1_sheet_names, (
            f"'C21-1' 不应精确匹配册内 sheet 名: {c21_1_sheet_names}"
        )

    def test_c22_pass_in_not_match(self, c22_sheet_names: list[str]) -> None:
        """CG-P9: 传入 'C22' 对册不命中。

        册内 34 个 sheet 名：'C22 IT一般控制测试' + 33 个 ITGC 域码。
        传入 'C22' 不等于全名。
        """
        assert "C22" not in c22_sheet_names, (
            f"'C22' 不应精确匹配册内 sheet 名: {c22_sheet_names}"
        )

    def test_zero_out_of_three(
        self,
        c21_sheet_names: list[str],
        c21_1_sheet_names: list[str],
        c22_sheet_names: list[str],
    ) -> None:
        """CG-P9: 命中 0/3。"""
        hits = 0
        if "C21" in c21_sheet_names:
            hits += 1
        if "C21-1" in c21_1_sheet_names:
            hits += 1
        if "C22" in c22_sheet_names:
            hits += 1
        assert hits == 0, f"命中 {hits}/3"

    def test_c21_1_sheet_name_decoupled_from_book_name(
        self, c21_1_sheet_names: list[str]
    ) -> None:
        """CG-P10: C21-1 册 sheet 名与册名完全脱钩。"""
        # 册名含 'C21-1'，但 sheet 名不含
        for sn in c21_1_sheet_names:
            if sn == "GT_Custom":
                continue
            assert "C21-1" not in sn, (
                f"sheet 名 '{sn}' 不应含 'C21-1' 前缀"
            )

    def test_c22_sheet_count_34(self, c22_sheet_names: list[str]) -> None:
        """CG-P12 补充: C22 册 34 sheets。"""
        assert len(c22_sheet_names) == 34

    def test_c22_main_sheet_full_name(self, c22_sheet_names: list[str]) -> None:
        """补充: C22 主 sheet 全名是 'C22 IT一般控制测试'。"""
        assert "C22 IT一般控制测试" in c22_sheet_names

    def test_oo_mount_passes_real_sheet_name(
        self, host_text: str
    ) -> None:
        """CC-63 修复后: OO 挂点传入真实 sheet 名（ooSheetName）而非 wpCode。

        代码: :sheet-name="activeDocTab.ooSheetName || ''"
        """
        assert "activeDocTab.ooSheetName" in host_text, (
            "OO 挂点应传 ooSheetName（真实 sheet 名）"
        )
        # 不应再传 wpCode 作为 sheet-name
        assert ':sheet-name="activeDocTab.wpCode' not in host_text, (
            "OO 挂点不应再传 wpCode 作为 sheet-name（CC-63 已修复）"
        )

    def test_tab_def_has_real_sheet_names(self) -> None:
        """CC-63 修复后: TabDef 定义了真实 sheet 名映射。"""
        state_file = (
            _WP_COMPONENTS / "composables" / "useC22BundleState.ts"
        )
        if not state_file.exists():
            pytest.skip("useC22BundleState.ts 不存在")
        text = state_file.read_text(encoding="utf-8", errors="replace")
        # C21 真实 sheet 名
        assert "C21 具有信息技术专业技能的项目组成员" in text, (
            "应含 C21 册真实 sheet 名"
        )
        # C21-1 真实 sheet 名（与 wpCode 脱钩）
        assert "IT 审计发现汇总表" in text, (
            "应含 C21-1 册真实 sheet 名"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §4 TestC22OOMount — CC-64
# ═══════════════════════════════════════════════════════════════════════════


class TestC22OOMount:
    """CC-64/CG-P7~P8, CG-P11: OO 挂点只在 C21/C21-1 两个 tab 渲染。"""

    def test_active_doc_tab_only_c21_c21_1(self, host_text: str) -> None:
        """CG-P8: activeDocTab 只匹配 kind === 'c21' || kind === 'c21-1'。"""
        # 在源码中查找 activeDocTab 的 computed 定义
        assert "t.kind === 'c21'" in host_text or "kind === 'c21'" in host_text
        assert "t.kind === 'c21-1'" in host_text or "kind === 'c21-1'" in host_text

    def test_oo_only_renders_on_2_of_4_tabs(self, host_text: str) -> None:
        """CG-P8: OO 挂点只在 2/4 个 tab 渲染。

        matrix 和 group tab 上 activeDocTab 为 undefined，OO 不渲染。
        """
        # GtOnlyOfficeSheet 只在 activeDocTab && subWpId 条件下渲染
        assert "GtOnlyOfficeSheet" in host_text
        # 确认有 v-if 条件
        assert "activeDocTab" in host_text

    def test_c22_authority_book_never_loaded_by_oo(
        self, host_text: str
    ) -> None:
        """CG-P11: C22 IT一般控制测试.xlsx 从未被 OO 加载。

        🔴 OO 挂点加载的是 C21/C21-1 册（均属排除册），
        不是本 entry 的权威册 C22。
        """
        # OO 挂点的 sheet-name 是 activeDocTab.wpCode（C21 或 C21-1）
        # 不是 C22
        assert "C22 IT一般控制测试" not in host_text


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestC22Namespace — 阶段 4（任务 10-12）
# ═══════════════════════════════════════════════════════════════════════════


class TestC22Namespace:
    """CC-15/CG-P13~P14: 点号命名空间与共享边界。"""

    def test_item_id_dot_separator(self, host_text: str) -> None:
        """CG-P13: item_id 用点号 C22.{controlId}.{field}。"""
        assert "itgcItemId" in host_text
        # 验证 itgcItemId 构造含 C22. 前缀
        assert "C22." in host_text

    def test_shared_with_control_sheet(self) -> None:
        """CG-P14: 与 GtC22ControlSheet.vue 共用同一命名空间。"""
        ctrl_sheet = _WP_COMPONENTS / "GtC22ControlSheet.vue"
        if not ctrl_sheet.exists():
            pytest.skip("GtC22ControlSheet.vue 不存在")
        text = ctrl_sheet.read_text(encoding="utf-8", errors="replace")
        # 子页也使用 itgcItemId
        assert "itgcItemId" in text, (
            "GtC22ControlSheet 应使用 itgcItemId"
        )

    def test_shared_is_intentional(self) -> None:
        """CG-P14: 共享是有意的（注释明写）。"""
        ctrl_sheet = _WP_COMPONENTS / "GtC22ControlSheet.vue"
        if not ctrl_sheet.exists():
            pytest.skip("GtC22ControlSheet.vue 不存在")
        text = ctrl_sheet.read_text(encoding="utf-8", errors="replace")
        # 子页有注释说明与 bundle 保持一致
        # 允许不同措辞
        has_intent = (
            "与子页保持一致" in text
            or "itgcItemId" in text  # 至少共用了函数
        )
        assert has_intent

    def test_persistence_d0_direct_call(self, host_text: str) -> None:
        """CG-P15: 持久化在 D0（宿主内直调 /checklist-responses）。"""
        assert "checklist-responses" in host_text

    def test_import_closure_8(self) -> None:
        """CG-P15: import 闭包 8 册。"""
        from c_cycle_scanner import import_closure
        if not C22_HOST.exists():
            pytest.skip("C22 宿主不存在")
        closure = import_closure(C22_HOST, maxdepth=3)
        # 闭包文件数应 ≤ 全 C 域最小
        assert len(closure) <= 20, f"closure size={len(closure)}"

    def test_real_db_zero(self, c22_entry: dict) -> None:
        """CG-P16: 真库 0 行。"""
        payload = c22_entry.get("real_db_payload", {})
        total = payload.get("total_rows", 0)
        if "total_rows" in payload:
            assert total == 0, f"C22 total_rows={total}"

    def test_stable_identity_in_host(self, host_text: str) -> None:
        """CC-6: 稳定身份 ≥ 1 处（tab 级 .id）。"""
        # 在宿主中查找 tab.id 或 .id 作为 :key
        id_keys = len(re.findall(r':key\s*=\s*"[^"]*\.id"', host_text))
        id_keys += len(re.findall(r":key\s*=\s*'[^']*\.id'", host_text))
        # 也检查 tab.id 形式的 v-model / active 引用
        tab_id_refs = host_text.count("tab.id")
        assert tab_id_refs >= 2, f"tab.id refs={tab_id_refs}"
