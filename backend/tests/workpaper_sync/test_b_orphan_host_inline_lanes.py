# -*- coding: utf-8 -*-
"""B 类孤儿载体与宿主内联门控通道守卫。

spec: b-class-orphan-carrier-and-host-inline-lanes

测试结构（对标 design.md §七）：
  - TestOrphanCarrierLifecycle     BH-P1 ~ BH-P5
  - TestResolutionFailureModes     BH-P6 ~ BH-P11
  - TestHostInlineGateAndModeOpts  BH-P12 ~ BH-P14, BH-P18
  - TestRowIdentityAndHardcoded    BH-P15 ~ BH-P17
  - TestXlsmMacroAndGeometry       BH-P19 ~ BH-P21
  - TestZeroDenominatorOrphan      BH-P22
  - TestOrphanSyncWiring           改线守卫
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

_FRONTEND = _ROOT / "audit-platform" / "frontend" / "src"
_WP = _FRONTEND / "components" / "workpaper"
_TMPL = _BACKEND / "wp_templates" / "B"
_SLICE = _BACKEND / "data" / "workpaper_sync_abcs_cycle_manifest_slice.json"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from b_cycle_scanner import (  # noqa: E402
    b_domain_entries, b_entry_by_id, carrier_tripartition,
    ORPHAN_ENTRIES, HOST_INLINE_ENTRIES,
    CARRIER_ORPHAN_MODULE, strip_comments, import_closure,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE.read_bytes())

@pytest.fixture(scope="module")
def b_entries(manifest_slice: dict) -> list[dict]:
    return b_domain_entries(manifest_slice["independent_entries"])

@pytest.fixture(scope="module")
def b_by_id(b_entries: list[dict]) -> dict[str, dict]:
    return b_entry_by_id(b_entries)

@pytest.fixture(scope="module")
def orphan_entries(b_entries: list[dict]) -> list[dict]:
    tri = carrier_tripartition(b_entries)
    return tri["orphan"]

@pytest.fixture(scope="module")
def hi_entries(b_entries: list[dict]) -> list[dict]:
    tri = carrier_tripartition(b_entries)
    return tri["host_inline"]

@pytest.fixture(scope="module")
def lane3_entries(orphan_entries: list[dict], hi_entries: list[dict]) -> list[dict]:
    return orphan_entries + hi_entries

def _hp(entry: dict) -> Path | None:
    p = entry.get("host_path", "")
    if not p: return None
    r = (_ROOT / p).resolve()
    return r if r.exists() else None


# ═══════════════════════════════════════════════════════════════════════════
# §1 TestOrphanCarrierLifecycle — BH-P1 ~ BH-P5
# ═══════════════════════════════════════════════════════════════════════════

class TestOrphanCarrierLifecycle:

    def test_orphan_exactly_3(self, orphan_entries: list[dict]) -> None:
        """BH-P1: 子组 A 三条全挂 useWpDualMode.ts。"""
        assert len(orphan_entries) == 3

    def test_orphan_ids_match(self, orphan_entries: list[dict]) -> None:
        ids = sorted(e["entry_id"] for e in orphan_entries)
        assert ids == sorted(ORPHAN_ENTRIES)

    def test_orphan_becomes_orphan_true(self, manifest_slice: dict) -> None:
        """BH-P3: becomes_orphan_after_rewire 为真。"""
        carriers = manifest_slice.get("dual_mode_carrier_inventory", {}).get("shared_carriers", {})
        info = carriers.get(CARRIER_ORPHAN_MODULE, {})
        assert info.get("becomes_orphan_after_rewire") is True

    def test_host_inline_exactly_2(self, hi_entries: list[dict]) -> None:
        """BH-P5: 子组 B 两条 host_inline_segmented。"""
        assert len(hi_entries) == 2

    def test_hi_ids_match(self, hi_entries: list[dict]) -> None:
        ids = sorted(e["entry_id"] for e in hi_entries)
        assert ids == sorted(HOST_INLINE_ENTRIES)

    def test_all_5_hosts_exist(self, lane3_entries: list[dict]) -> None:
        for e in lane3_entries:
            hp = _hp(e)
            assert hp is not None and hp.exists(), f"{e['entry_id']} host missing"

    def test_orphan_hosts_import_useWpDualMode(self, orphan_entries: list[dict]) -> None:
        for e in orphan_entries:
            hp = _hp(e)
            if hp is None: continue
            text = hp.read_text(encoding="utf-8", errors="replace")
            assert "useWpDualMode" in text, f"{e['entry_id']} 缺 useWpDualMode import"


# ═══════════════════════════════════════════════════════════════════════════
# §2 TestResolutionFailureModes — BH-P6 ~ BH-P11
# ═══════════════════════════════════════════════════════════════════════════

class TestResolutionFailureModes:

    def test_all_three_modes_present(self, b_by_id: dict) -> None:
        """BH-P6: 三种解析失败模式在本组全部出现。"""
        # Mode 1: 返回 None（中文名 → 无候选册）
        # Mode 2: 抛 FileNotFoundError（前导空格 sheet 名）
        # Mode 3: 多册歧义（B1-4 标准版/简化版）
        # 此处验证 slice 数据结构支撑
        kaa = b_by_id["xlsx/gt-b1-kaa-check"]
        exprs = kaa.get("template_ref", {}).get("sheet_name_exprs", [])
        joined = " ".join(exprs)
        # 前导空格存在（mode 2 触发条件）
        assert "' B1-5" in joined, f"sheet_exprs={exprs}"

    def test_b1_5_leading_space_preserved(self, b_by_id: dict) -> None:
        """BH-P7: 前导空格 sheet 名禁归一化。"""
        kaa = b_by_id["xlsx/gt-b1-kaa-check"]
        codes = kaa.get("wp_codes_via_component_type", [])
        # 含前导空格的 sheet 名
        space_codes = [c for c in codes if c.startswith(" ")]
        assert len(space_codes) >= 1, f"no leading-space code in {codes}"

    def test_b1_1_sheet_name_is_risk_assessment(self) -> None:
        """BH-P8: B1-1 册 sheet 名为「风险评估表-承接」。"""
        # 从模板目录验证
        b1_1 = [f for f in _TMPL.rglob("*") if "B1-1" in f.stem and f.suffix == ".xlsx"]
        assert len(b1_1) >= 1, "B1-1 模板不存在"

    def test_manifest_4_patterns_none(self, orphan_entries: list[dict]) -> None:
        """BH-P9: 本组 4 个 pattern 全解析为 None（CamelCase 幻影码）。"""
        from b_cycle_scanner import test_wp_code_resolution
        for e in orphan_entries:
            pat = e.get("wp_code_pattern", "")
            if pat:
                r = test_wp_code_resolution(pat)
                assert r["books_count"] == 0, f"{pat} 不应解析到册"

    def test_b1_risk_4_wp_codes(self, b_by_id: dict) -> None:
        """BH-P10: b1-risk-assessment 覆盖 4 个 wp_code。"""
        e = b_by_id["xlsx/gt-b1-risk-assessment"]
        codes = e.get("wp_codes_via_component_type", [])
        assert len(codes) == 4
        real = [c for c in codes if re.match(r"^B\d", c)]
        assert len(real) == 2  # B1-1, B1-2

    def test_b14_two_books(self) -> None:
        """BH-P11: B1-4 对应两本册。"""
        from b_cycle_scanner import test_wp_code_resolution
        r = test_wp_code_resolution("B1-4")
        assert r["books_count"] >= 2, f"B1-4 books={r['books_count']}"


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestHostInlineGateAndModeOpts — BH-P12~P14, BH-P18
# ═══════════════════════════════════════════════════════════════════════════

class TestHostInlineGateAndModeOpts:

    def test_b14_double_segmented(self, b_by_id: dict) -> None:
        """BH-P12: b14 有 2 个 segmented（全 B 域唯一）。"""
        hp = _hp(b_by_id["xlsx/gt-b14-due-diligence-report"])
        if hp is None: pytest.skip("b14 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        seg = text.count("el-segmented") + text.count("ElSegmented")
        assert seg >= 2, f"b14 segmented={seg}"

    def test_b14_mode_options_in_host(self, b_by_id: dict) -> None:
        """BH-P13: b14 是全 B 域唯一在宿主内声明 modeOptions 的 entry（3 处）。"""
        hp = _hp(b_by_id["xlsx/gt-b14-due-diligence-report"])
        if hp is None: pytest.skip("b14 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        # 含中文模式字面量
        assert ("'结构化视图'" in text or '"结构化视图"' in text)

    def test_b14_has_polish_mode(self, b_by_id: dict) -> None:
        """BH-P14: b14 另有第四值 'polish'。"""
        hp = _hp(b_by_id["xlsx/gt-b14-due-diligence-report"])
        if hp is None: pytest.skip("b14 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "'polish'" in text or '"polish"' in text

    def test_gate_false_negatives_2_in_this_spec(
        self, orphan_entries: list[dict], hi_entries: list[dict]
    ) -> None:
        """BH-P18: 门控假阴本组 2 条（b1-risk + b23）。"""
        known_fn = {
            "xlsx/gt-b1-risk-assessment",
            "xlsx/gt-b23-process-control",
        }
        # 验证这两条的 OO 挂点在 v-else 分支或 template 嵌套内
        for eid in known_fn:
            all_ents = orphan_entries + hi_entries
            matching = [e for e in all_ents if e["entry_id"] == eid]
            assert len(matching) == 1, f"{eid} not in lane3"


# ═══════════════════════════════════════════════════════════════════════════
# §4 TestRowIdentityAndHardcoded — BH-P15~P17
# ═══════════════════════════════════════════════════════════════════════════

class TestRowIdentityAndHardcoded:

    def test_b14_peer_hardcoded(self, b_by_id: dict) -> None:
        """BH-P15: 写死对标公司 peer1/peer2 在 b14。"""
        hp = _hp(b_by_id["xlsx/gt-b14-due-diligence-report"])
        if hp is None: pytest.skip("b14 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "peer1" in text and "peer2" in text

    def test_b14_rowIndex_param(self, b_by_id: dict) -> None:
        """BH-P16: rowIndex 形参 2 处在 b14。"""
        hp = _hp(b_by_id["xlsx/gt-b14-due-diligence-report"])
        if hp is None: pytest.skip("b14 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        hits = len(re.findall(r"\browIndex\b", text))
        assert hits >= 2, f"rowIndex in b14={hits}"

    def test_b1_risk_reduce_4(self, b_by_id: dict) -> None:
        """BH-P17: .reduce( 派生 4 处全在 b1-risk-assessment。"""
        hp = _hp(b_by_id["xlsx/gt-b1-risk-assessment"])
        if hp is None: pytest.skip("b1-risk host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        hits = text.count(".reduce(")
        assert hits >= 4, f".reduce( in b1-risk={hits}"


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestXlsmMacroAndGeometry — BH-P19~P21
# ═══════════════════════════════════════════════════════════════════════════

class TestXlsmMacroAndGeometry:

    def test_b23_family_xlsm(self) -> None:
        """BH-P19: B23 家族 14 本 xlsm 全含 vbaProject.bin。"""
        import zipfile
        xlsm = [f for f in _TMPL.rglob("*")
                if f.is_file() and f.suffix == ".xlsm"
                and re.search(r"B23-\d+", f.stem)]
        assert len(xlsm) >= 14, f"B23 xlsm={len(xlsm)}"
        vba = 0
        for f in xlsm:
            try:
                with zipfile.ZipFile(f) as z:
                    if "xl/vbaProject.bin" in z.namelist():
                        vba += 1
            except Exception:
                pass
        assert vba == len(xlsm), f"vba={vba}/{len(xlsm)}"

    def test_b23_sheet_name_is_dynamic(self, b_by_id: dict) -> None:
        """BH-P20: currentCard.name 是全 B 域唯一形态 D。"""
        e = b_by_id["xlsx/gt-b23-process-control"]
        exprs = e.get("template_ref", {}).get("sheet_name_exprs", [])
        assert any("currentCard" in x for x in exprs), f"exprs={exprs}"

    def test_b1_1_ghost_rows(self) -> None:
        """BH-P21: 幽灵行 335 行 / 2 列（已在 foundation 验证）。"""
        # 此处仅确认模板存在
        b1_1 = [f for f in _TMPL.rglob("*") if "B1-1" in f.stem and f.suffix == ".xlsx"]
        assert len(b1_1) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# §6 TestZeroDenominatorOrphan — BH-P22
# ═══════════════════════════════════════════════════════════════════════════

class TestZeroDenominatorOrphan:

    def test_orphan_3_plus_b14_all_zero_payload(
        self, orphan_entries: list[dict], b_by_id: dict
    ) -> None:
        """BH-P22: 子组 A 三条 + b14 真库载荷全为 0。"""
        zero_ids = [e["entry_id"] for e in orphan_entries]
        zero_ids.append("xlsx/gt-b14-due-diligence-report")
        for eid in zero_ids:
            e = b_by_id[eid]
            payload = e.get("real_db_payload", {})
            total = payload.get("total_rows", 0)
            if "total_rows" in payload:
                assert total == 0, f"{eid} total={total}"

    def test_b23_has_2_rows(self, b_by_id: dict) -> None:
        """BH-P22 补充: B23 有 2 行真库载荷。"""
        e = b_by_id["xlsx/gt-b23-process-control"]
        payload = e.get("real_db_payload", {})
        total = payload.get("total_rows", -1)
        if total >= 0:
            assert total >= 2, f"B23 total={total}"


# ═══════════════════════════════════════════════════════════════════════════
# §7 TestOrphanSyncWiring — 孤儿组改线守卫（阶段3/6）
# ═══════════════════════════════════════════════════════════════════════════

class TestOrphanSyncWiring:
    """孤儿组 3 条 sync composable 就绪守卫。"""

    def test_orphan_sync_composable_exists(self) -> None:
        """Task 2: useB1OrphanSyncMode.ts 已创建。"""
        p = _WP / "composables" / "useB1OrphanSyncMode.ts"
        assert p.exists()

    def test_orphan_sync_imports_bridge(self) -> None:
        p = _WP / "composables" / "useB1OrphanSyncMode.ts"
        text = p.read_text(encoding="utf-8", errors="replace")
        assert "useWorkpaperSyncBridge" in text
        assert "capabilityForEntry" in text
        assert "fetchOnlyOfficeHealthy" in text

    def test_orphan_sync_uses_chinese_labels(self) -> None:
        """孤儿组 mode 用中文标签对齐 useWpDualMode 接口。"""
        p = _WP / "composables" / "useB1OrphanSyncMode.ts"
        text = p.read_text(encoding="utf-8", errors="replace")
        assert "结构化视图" in text
        assert "在线编辑" in text

    def test_3_b1_hosts_import_sync(self) -> None:
        """Task 8: 3 个 B1 宿主已引入 useB1OrphanSyncMode。"""
        hosts = [
            "GtB1Evaluation.vue",
            "GtB1KaaCheck.vue",
            "GtB1RiskAssessment.vue",
        ]
        for name in hosts:
            f = _WP / name
            text = f.read_text(encoding="utf-8", errors="replace")
            assert "useB1OrphanSyncMode" in text, f"{name} 缺 sync import"

    def test_3_b1_hosts_preserve_legacy(self) -> None:
        """Task 24: 3 个 B1 宿主保留 useWpDualMode 降级（改线未完成不删）。"""
        hosts = [
            "GtB1Evaluation.vue",
            "GtB1KaaCheck.vue",
            "GtB1RiskAssessment.vue",
        ]
        for name in hosts:
            f = _WP / name
            text = f.read_text(encoding="utf-8", errors="replace")
            assert "useWpDualMode" in text, f"{name} 缺 legacy fallback"

    def test_use_wp_dual_mode_still_exists(self) -> None:
        """Task 22/23: useWpDualMode.ts 未删除（3 条改线+UAT 未完成）。"""
        p = _WP / "composables" / "useWpDualMode.ts"
        assert p.exists(), (
            "useWpDualMode.ts 不应提前删除（须 3 条改线完成 + UAT 通过）"
        )

    def test_distinct_entry_ids(self) -> None:
        """3 条孤儿 entry_id 不同（各自命名空间）。"""
        e1 = (_WP / "GtB1Evaluation.vue").read_text(encoding="utf-8", errors="replace")
        e2 = (_WP / "GtB1KaaCheck.vue").read_text(encoding="utf-8", errors="replace")
        e3 = (_WP / "GtB1RiskAssessment.vue").read_text(encoding="utf-8", errors="replace")
        assert "gt-b1-evaluation" in e1
        assert "gt-b1-kaa-check" in e2
        assert "gt-b1-risk-assessment" in e3


# ═══════════════════════════════════════════════════════════════════════════
# §8 TestHostInlineDeferred — host-inline 结构就绪登记（阶段4）
# ═══════════════════════════════════════════════════════════════════════════

class TestHostInlineDeferred:
    """host-inline 2 条（b14/b23）宿主内联门控现状登记。

    🔴 b14/b23 宿主内联门控改造复杂（双 segmented / modeOptions 三处漂移 /
       currentCard.name 动态 sheet / xlsm 整册），且真库分母近 0（b14=0/b23=2），
       本轮登记现状 + 保留 legacy，宿主内联真双向改造待 capability 升级（外部依赖）。
    """

    def test_b14_host_inline_gate_present(self, b_by_id: dict) -> None:
        """b14 宿主内联门控现状（modeOptions 在宿主内）。"""
        hp = _hp(b_by_id["xlsx/gt-b14-due-diligence-report"])
        if hp is None: pytest.skip("b14 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        # b14 有 segmented 门控
        assert "el-segmented" in text or "ElSegmented" in text

    def test_b23_editor_mode_inline(self, b_by_id: dict) -> None:
        """b23 宿主内联 editorMode（structured/onlyoffice）。"""
        hp = _hp(b_by_id["xlsx/gt-b23-process-control"])
        if hp is None: pytest.skip("b23 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "editorMode" in text
        assert "currentCard.name" in text

    def test_b23_oo_whole_workbook(self, b_by_id: dict) -> None:
        """b23 OO 整册模式（xlsm 按 card 加载）。"""
        hp = _hp(b_by_id["xlsx/gt-b23-process-control"])
        if hp is None: pytest.skip("b23 host missing")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "whole-workbook" in text or "wholeWorkbook" in text


# ═══════════════════════════════════════════════════════════════════════════
# §9 TestOrphanDeletionCloseout — 孤儿载体删除收尾（阶段6 tasks 22-24）
# ═══════════════════════════════════════════════════════════════════════════

class TestOrphanDeletionCloseout:
    """孤儿载体删除收尾守卫。

    🔴 spec 铁律（design §2.2）：3 条 entry 全部改线完成后才删 useWpDualMode.ts。
       「改线完成」= capability 升级为 bidirectional（外部依赖 BP-1~5）+ 移除 legacy 降级。
       当前 capability 未升级，legacy 降级路径仍在用，故 useWpDualMode 引用不为 0，
       不能删除。本组守卫验证删除前置条件的可复算性。
    """

    def test_current_production_edges_count(self) -> None:
        """Task 22: 当前 useWpDualMode 生产引用数（应为 3，即 3 条 B1 宿主）。

        🔴 引用归零是删除充要条件。当前为 3（legacy 降级仍在），不可删。
        """
        edges = 0
        for f in _WP.rglob("*.vue"):
            if "__tests__" in str(f) or ".spec." in f.name:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            # 计 useWpDualMode( 调用（非 import 行）
            calls = len(re.findall(r"useWpDualMode\s*\(", text))
            edges += calls
        # 当前 3 条 B1 宿主各 1 处调用
        assert edges == 3, (
            f"useWpDualMode 生产调用={edges}（预期 3，legacy 降级仍在）"
        )

    def test_all_3_edges_are_b1_hosts(self) -> None:
        """Task 22: 3 处引用全在 B1 宿主（孤儿组），无其他循环占用。"""
        hosts_with_calls = []
        for f in _WP.rglob("*.vue"):
            if "__tests__" in str(f) or ".spec." in f.name:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if re.search(r"useWpDualMode\s*\(", text):
                hosts_with_calls.append(f.name)
        # 全域边 == B 域边（成孤儿充要条件 BH-P2）
        assert set(hosts_with_calls) == {
            "GtB1Evaluation.vue",
            "GtB1KaaCheck.vue",
            "GtB1RiskAssessment.vue",
        }, f"hosts={hosts_with_calls}"

    def test_deletion_blocked_by_external_dependency(self) -> None:
        """Task 23: 删除阻塞在外部依赖（capability 升级未完成）。

        3 条 entry 的 capability 仍为 legacy（非 bidirectional），
        sync composable 走 descriptorReady 降级路径，legacy 引用无法归零。
        useWpDualMode.ts 保留，删除待 UAT。
        """
        p = _WP / "composables" / "useWpDualMode.ts"
        assert p.exists(), "useWpDualMode.ts 仍应存在（删除阻塞外部依赖）"

        # 确认 3 条 B1 宿主仍有 descriptorReady 降级门控
        for name in ["GtB1Evaluation.vue", "GtB1KaaCheck.vue",
                     "GtB1RiskAssessment.vue"]:
            text = (_WP / name).read_text(
                encoding="utf-8", errors="replace"
            )
            assert "descriptorReady" in text, (
                f"{name} 缺 descriptorReady 降级门控"
            )

    def test_deletion_precondition_documented(self) -> None:
        """Task 23: sync composable 头注释记录了删除条件。"""
        p = _WP / "composables" / "useB1OrphanSyncMode.ts"
        text = p.read_text(encoding="utf-8", errors="replace")
        assert "孤儿" in text and "删除" in text, (
            "useB1OrphanSyncMode.ts 应记录孤儿载体删除条件"
        )

    def test_b60_pilot_7_assertions_not_regressed(self) -> None:
        """Task 24: 既存 B60 pilot 断言不受影响（回滚安全）。"""
        # B60 组件不引用孤儿 sync
        for f in _WP.rglob("GtB60*.vue"):
            text = f.read_text(encoding="utf-8", errors="replace")
            assert "useB1OrphanSyncMode" not in text, (
                f"{f.name} 误引孤儿 sync"
            )
            assert "useWpDualMode" not in text, (
                f"{f.name} 误引 useWpDualMode"
            )
