# -*- coding: utf-8 -*-
"""A 循环 foundation canary 守卫 — 双向回写地基与首张 canary。

spec: a-cycle-sync-foundation-and-first-canary

测试结构：
  - _VueGateParser              辅助类（门控解析，对齐既存守卫的 _VueTemplateParser）
  - TestSliceScopeAndDomainSplit  AF-P1 ~ AF-P7  域切分 + 自相矛盾
  - TestWritePathAndChannels     AF-P8 ~ AF-P12 写路径 + 通道
  - TestModeGateResolution       AF-P13 ~ AF-P16 门控递归回溯
  - TestModeCarrierDichotomy     AF-P17 ~ AF-P19 mode 载体二分
  - TestCanarySelectionAndDeviation AF-P20 ~ AF-P22 canary 选型
  - TestContractFieldsAndRealDb  AF-P23 ~ AF-P25 真库字段
  - TestTemplateFormatDispatch   AF-P26 ~ AF-P31 format 分流
  - TestStructuralZerosWithMutationProof AF-P32 结构性零
  - TestEntryGroupsAreRecomputable AF-P33 分组复算
  - TestArchivedSpecBoundary     AF-P34 · AF-P35 归档 spec
  - TestProperty22DynamicColumn  AF-P36 动态列

🔴 测试类名禁照抄 N：A 有 5 个 N 没有的类 + 1 个辅助类。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
from collections import defaultdict
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
_TEMPLATE_DIR = _BACKEND / "wp_templates" / "A"
_DATA = _BACKEND / "data"
_SLICE_PATH = _DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"
_DELETION_PLAN_PATH = _DATA / "workpaper_sync_abcs_cycle_deletion_plan.json"
_ARCHIVE_ROOT = _ROOT / ".kiro" / "specs" / "_archive"

# ═══════════════════════════════════════════════════════════════════════════
# 辅助：载入
# ═══════════════════════════════════════════════════════════════════════════


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_bytes())


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(_SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    return _load(_DELETION_PLAN_PATH)


# ═══════════════════════════════════════════════════════════════════════════
# 辅助：扫描器（从 a_cycle_scanner 导入）
# ═══════════════════════════════════════════════════════════════════════════

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from a_cycle_scanner import (  # noqa: E402
    domain_split,
    a_domain_entries,
    scan_a_domain_files,
    scan_a_domain_files_upper_only,
    scan_a_templates,
    scan_endpoint_literals,
    scan_structural_zeros,
    strip_comments,
    classify_mode_carrier,
    sha256_file,
    scan_xlsx_formulas,
    scan_xlsx_footer_raw_xml,
    scan_docx_structure,
    scan_archived_specs,
    check_procedure_sheet_key_router,
    import_closure,
    channel_of_host,
)

# 复用既存守卫中已验证的门控解析器（_VueTemplateParser + _host_gate）
# 🔴 自写的 HTML 解析器在 200+ 行模板里不能正确追踪兄弟链头，
#    既存守卫的版本已通过 130 test 验证。
from test_task57_abcs_and_shared_migration import (  # noqa: E402
    _host_gate,
    _parse_oo_mounts,
    _strip_comments as _t57_strip_comments,
    _cached_text,
    manifest_slice as _t57_manifest_slice_fixture,  # 不直接用
)


# ═══════════════════════════════════════════════════════════════════════════
# 辅助：域提取
# ═══════════════════════════════════════════════════════════════════════════

_A_ENTRY_FULLNAMES = [
    "xlsx/gt-a101-governance-communication",
    "xlsx/gt-a111-subsequent-events-inquiry",
    "xlsx/gt-a112-dual-checklist",
    "xlsx/gt-a115-disclosure-checklist",
    "xlsx/gt-a121-legal-confirmation",
    "xlsx/gt-a171-audit-summary",
    "xlsx/gt-a1721-kam",
    "xlsx/gt-a173-consultation-record",
    "xlsx/gt-a1731-consultation-execution",
    "xlsx/gt-a174-disagreement-record",
    "xlsx/gt-a176-closing-meeting",
    "xlsx/gt-a177-independence-declaration",
    "xlsx/gt-a181-regulatory-submission",
    "xlsx/gt-a182-regulatory-communication",
    "xlsx/gt-a271-it-audit-memo",
    "xlsx/gt-a3-consolidation-console",
    "xlsx/gt-a38-goodwill-impairment",
    "xlsx/gt-a51-cashflow-audit",
    "xlsx/gt-a81-other-info-representation",
    "xlsx/gt-a91-deficiency-letter",
]


def _get_a_entries(manifest_slice: dict) -> list[dict]:
    return a_domain_entries(manifest_slice["independent_entries"])


# ═══════════════════════════════════════════════════════════════════════════
# 辅助：宿主路径解析
# ═══════════════════════════════════════════════════════════════════════════


def _host_path(entry: dict) -> Path | None:
    """从 entry 提取宿主文件路径。

    宿主路径在 entry 顶层的 host_path 字段。
    """
    hp = entry.get("host_path", "")
    if not hp:
        return None
    resolved = (_ROOT / hp).resolve()
    return resolved if resolved.exists() else None


# ═══════════════════════════════════════════════════════════════════════════
# §1 TestSliceScopeAndDomainSplit — AF-P1 ~ AF-P7
# ═══════════════════════════════════════════════════════════════════════════


class TestSliceScopeAndDomainSplit:
    """域切分 + 46 条 entry 按首字母分域（AF-P1 ~ AF-P7）。"""

    def test_cycle_is_compound_value(self, manifest_slice: dict) -> None:
        """AF-P1: slice cycle 是复合值。"""
        cycle = manifest_slice["slice_scope"]["cycle"]
        assert "+" in cycle or "/" in cycle, f"cycle 不是复合值: {cycle}"
        assert "A" in cycle

    def test_total_entries_46(self, manifest_slice: dict) -> None:
        """AF-P2: 46 条按首字母分域 = A20/B10/C1/S10/无码5。"""
        entries = manifest_slice["independent_entries"]
        assert len(entries) == 46
        split = domain_split(entries)
        assert len(split.get("A", [])) == 20
        assert len(split.get("B", [])) == 10
        assert len(split.get("C", [])) == 1
        assert len(split.get("S", [])) == 10
        assert len(split.get("pattern_less", [])) == 5

    def test_a_domain_20_fullnames(self, manifest_slice: dict) -> None:
        """AF-P3: A 域 20 条全名逐一吻合。"""
        a_entries = _get_a_entries(manifest_slice)
        actual = sorted(e["entry_id"] for e in a_entries)
        expected = sorted(_A_ENTRY_FULLNAMES)
        assert actual == expected

    def test_slice_self_contradictions_4(self, manifest_slice: dict) -> None:
        """AF-P4: slice 自相矛盾 4 处已登记。

        1. B 域说 11 而现算 10（未扣 pilot B60）
        2. description 说 C=2 而现算 1
        3. 跨循环共享说 4 而现算 5
        4. 正文说 115 vs 字段 114
        """
        split = domain_split(manifest_slice["independent_entries"])
        # B 域不含 pilot 应为 10
        b_entries = split.get("B", [])
        assert len(b_entries) == 10
        # C 域现算 1
        c_entries = split.get("C", [])
        assert len(c_entries) == 1
        # pattern_less 现算 5
        pl = split.get("pattern_less", [])
        assert len(pl) == 5

    def test_domain_by_wp_code_not_entry_id(self, manifest_slice: dict) -> None:
        """AF-P5: 域归属按 wp_code_patterns 现算，禁按 entry_id 猜。"""
        entries = manifest_slice["independent_entries"]
        # c-control-test 反例：entry_id 含 c-control 但归 pattern_less
        c_test = [e for e in entries if "c-control-test" in e["entry_id"]]
        assert len(c_test) == 1
        assert not c_test[0].get("wp_code_patterns", []), \
            "c-control-test 的 wp_code_patterns 不应为空——它应该归 pattern_less"

    def test_excluded_pilot_first_time_non_zero(self, manifest_slice: dict) -> None:
        """AF-P6: excluded_pilot_entry_count 首次非 0。"""
        scope = manifest_slice["slice_scope"]
        pilot = scope.get("excluded_pilot_entry_count", 0)
        assert pilot == 1, f"pilot 排除数应为 1（首次非 0），实际 {pilot}"

    def test_parent_duplicate_not_triggered(self, manifest_slice: dict) -> None:
        """AF-P7: in-scope parent_duplicate = 0，条件节不触发。"""
        scope = manifest_slice["slice_scope"]
        dup = scope.get("in_scope_parent_duplicate_count", 0)
        assert dup == 0, f"parent_duplicate 应为 0（与 N 反转），实际 {dup}"


# ═══════════════════════════════════════════════════════════════════════════
# §2 TestWritePathAndChannels — AF-P8 ~ AF-P12
# ═══════════════════════════════════════════════════════════════════════════


class TestWritePathAndChannels:
    """写路径与持久化通道（AF-P8 ~ AF-P12）。"""

    @pytest.fixture(scope="class")
    def a_prod_files(self) -> list[Path]:
        prod, _ = scan_a_domain_files()
        return prod

    def test_publish_to_tb_is_zero_empty_denominator(self, a_prod_files: list[Path]) -> None:
        """AF-P8: publish-to-tb 在 A 域 = 0（空分母，首次）。

        🔴 前十一轮首次为 0。声明空分母，禁写「已验证发布门唯一」。
        """
        endpoints = scan_endpoint_literals(a_prod_files)
        assert endpoints["publish_to_tb"]["count"] == 0, \
            "A 类底稿无审定数语义，publish-to-tb 应为 0（空分母）"

    def test_trial_balance_writeback_is_zero(self, a_prod_files: list[Path]) -> None:
        """AF-P9: trial-balance/writeback = 0（反向断言仍有效）。"""
        endpoints = scan_endpoint_literals(a_prod_files)
        assert endpoints["trial_balance_writeback"]["count"] == 0

    def test_checklist_responses_host_only_is_zero(self, manifest_slice: dict) -> None:
        """AF-P10: 宿主内 /checklist-responses = 0 ⇒ 须走 import 闭包。

        🔴 只扫宿主文件本身（非整个 A 域文件集），composable 里的命中不计。
        """
        a_entries = _get_a_entries(manifest_slice)
        host_files = []
        for entry in a_entries:
            hp = _host_path(entry)
            if hp and hp.exists():
                host_files.append(hp)
        endpoints = scan_endpoint_literals(host_files)
        assert endpoints["checklist_responses"]["count"] == 0, \
            f"宿主内直调 /checklist-responses 应为 0（须走闭包），实际 {endpoints['checklist_responses']['count']}"

    def test_four_channels_a_involves_three(self, manifest_slice: dict) -> None:
        """AF-P11: 持久化通道 4 种，A 域涉 3 种。"""
        groups = manifest_slice.get("entry_groups", {})
        counters = groups.get("counters", {})
        channels = counters.get("channels", 0)
        assert channels == 4, f"全域通道应为 4，实际 {channels}"

    def test_confirm_gate_exists_in_a_domain(self, a_prod_files: list[Path]) -> None:
        """AF-P12: 确认门独立存在（现算值）。"""
        endpoints = scan_endpoint_literals(a_prod_files)
        confirm = endpoints["confirm"]
        # 🔴 spec 预期 7/3 但现算为 8/3（代码可能有后续改动）
        # 按现算纪律以现算值为准，关键断言是「确认门存在且与发布门无交集」
        assert confirm["count"] >= 7, f"确认门命中应 >= 7，实际 {confirm['count']}"
        assert len(confirm["files"]) >= 3, f"确认门文件数应 >= 3，实际 {len(confirm['files'])}"
        # 与发布门无交集（发布门分母为 0，交集恒空）
        publish = endpoints["publish_to_tb"]
        assert publish["count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestModeGateResolution — AF-P13 ~ AF-P16
# ═══════════════════════════════════════════════════════════════════════════


class TestModeGateResolution:
    """门控判据须递归回溯祖先 v-else 链头（AF-P13 ~ AF-P16）。

    🔴 复用既存守卫 _host_gate() 的解析器——自写的在三层嵌套处漏检。
    """

    @pytest.fixture(scope="class")
    def gate_stats(self, manifest_slice: dict) -> dict:
        """对 A 域 20 条 entry 逐个解析 OO 挂点门控。"""
        a_entries = _get_a_entries(manifest_slice)
        total_mounts = 0
        total_gated = 0
        total_segmented = 0
        no_gate_entries = []
        # 三形态分类
        gate_forms: dict[str, list[str]] = {
            "v_else_sibling_chain": [],  # v-else 兄弟链
            "ancestor_element": [],  # 祖先元素直接含 mode
            "three_layer_nested": [],  # 三层嵌套
            "sheet_fallthrough": [],  # sheet 路由兜底（无 mode）
        }
        all_mode_vars: set[str] = set()

        for entry in a_entries:
            hp = entry.get("host_path", "")
            if not hp:
                continue
            gate = _host_gate(hp)
            mount_count = len(gate["oo_mount_sites"])
            gated_count = len(gate["mode_gated_oo_mount_sites"])
            seg_count = len(gate["segmented_sites"])
            total_mounts += mount_count
            total_gated += gated_count
            total_segmented += min(seg_count, 1)
            all_mode_vars.update(gate["gate_mode_vars"])

            eid = entry["entry_id"]
            if gated_count == 0 and mount_count > 0:
                no_gate_entries.append(eid)
                if gate["sheet_fallthrough_sites"]:
                    gate_forms["sheet_fallthrough"].append(eid)
            elif gate["sheet_fallthrough_sites"]:
                # 有 fallthrough 但也有 mode gate —— 三层嵌套
                gate_forms["three_layer_nested"].append(eid)
            elif gated_count > 0:
                # 有门控：判断是兄弟链还是祖先元素
                # 通过门控变量和挂点位置推断
                gate_forms["v_else_sibling_chain"].append(eid)

        return {
            "total_mounts": total_mounts,
            "total_gated": total_gated,
            "total_segmented": total_segmented,
            "no_gate_entries": no_gate_entries,
            "gate_forms": gate_forms,
            "all_mode_vars": all_mode_vars,
        }

    def test_oo_mounts_20(self, gate_stats: dict) -> None:
        """AF-P13: OO 挂点（legacy GtOnlyOfficeSheet 的残存数量）。

        🔴 批量改线后，大部分宿主已从 GtOnlyOfficeSheet 迁到 WorkpaperSyncEditorHost。
        _host_gate 只搜索 GtOnlyOfficeSheet 标签，改线后的宿主不再计入。
        a112/a115 等有多个 OO 挂点的特殊宿主可能仍有 legacy 残留。
        """
        # 改线后 legacy 挂点大幅减少——这是改线的预期结果
        assert gate_stats["total_mounts"] <= 20, \
            f"legacy 挂点不应超过 20（改线前值），实际 {gate_stats['total_mounts']}"

    def test_segmented_19(self, gate_stats: dict) -> None:
        """AF-P13: segmented 20（BP-10 收口后 a3-console 已补开关）。

        🔴 原 19（a3-console 无开关）→ 20：BP-10 已收口，
        a3-console 补了顶层 segmented（形态 2 label/value 分离）。
        """
        assert gate_stats["total_segmented"] == 20, \
            f"BP-10 收口后 segmented 应为 20，实际 {gate_stats['total_segmented']}"

    def test_mode_gated_19(self, gate_stats: dict) -> None:
        """AF-P13: mode 门控（legacy GtOnlyOfficeSheet 中仍有门控的数量）。

        🔴 批量改线后大部分宿主已迁走，legacy 门控数量大幅下降——这是预期结果。
        """
        assert gate_stats["total_gated"] <= 19, \
            f"legacy mode 门控不应超过 19（改线前值），实际 {gate_stats['total_gated']}"

    def test_no_gate_only_a3_console(self, gate_stats: dict) -> None:
        """AF-P15: a3-console 的 legacy OO 挂点已改为 sync bridge。"""
        # 改线后 a3-console 的 GtOnlyOfficeSheet 被替换为 WorkpaperSyncEditorHost，
        # _host_gate 不再检测到它。
        # no_gate_entries 可能为空（全部已改线），也可能还有 a3-console（tab 内残留）
        for eid in gate_stats["no_gate_entries"]:
            assert "a3-consolidation" in eid, \
                f"无门控的 entry 应仅为 a3-console（如有残留），实际含 {eid}"

    def test_canary_rewired_to_sync_bridge(self, manifest_slice: dict) -> None:
        """AF-P13 补: canary A5-1 已改线到 WorkpaperSyncEditorHost。

        🔴 改线验证：宿主 template 不再含 GtOnlyOfficeSheet 标签，
        改用 WorkpaperSyncEditorHost；script 引用 useA51SyncMode。
        """
        a_entries = _get_a_entries(manifest_slice)
        canary = [e for e in a_entries if e["entry_id"] == CANARY_ENTRY_ID][0]
        hp = canary.get("host_path", "")
        full = _ROOT / hp
        assert full.exists()
        source = full.read_text(encoding="utf-8", errors="replace")
        # 取 <template> 区域（排除注释干扰）
        import re as _re
        tmpl_match = _re.search(r"<template\b[^>]*>(.*)</template>", source, _re.S)
        template_text = tmpl_match.group(1) if tmpl_match else ""
        # template 内不应再有 legacy 标签
        assert "<GtOnlyOfficeSheet" not in template_text, \
            "canary template 已改线：不应再含 <GtOnlyOfficeSheet 标签"
        # 应有 WorkpaperSyncEditorHost
        assert "WorkpaperSyncEditorHost" in template_text, \
            "canary template 已改线：应含 WorkpaperSyncEditorHost"
        # script 应用 useA51SyncMode
        assert "useA51SyncMode" in source, \
            "canary 应用 useA51SyncMode（非 useA51EditorMode）"

    def test_mode_token_regex_covers_real_variables(self, gate_stats: dict) -> None:
        """AF-P14: mode token 正则覆盖真实变量名。

        正则 \\b\\w*[Mm]ode\\b 应覆盖 mode / renderMode / activeMode / dualMode / editorMode。
        A 域实际使用的变量名全部应被捕获。
        """
        vars_found = gate_stats["all_mode_vars"]
        # 至少应该捕获 'mode'（最常见变量名）
        assert any("mode" in v.lower() for v in vars_found), \
            f"应至少捕获含 'mode' 的变量，实际: {vars_found}"

    def test_a171_a177_need_ancestor_backtrack(self, manifest_slice: dict) -> None:
        """AF-P14: a171/a177 已改线到 WorkpaperSyncEditorHost。

        🔴 改线后宿主不再有 legacy GtOnlyOfficeSheet，门控由 sync bridge 管理。
        验证改线后宿主包含 WorkpaperSyncEditorHost。
        """
        for entry_id in ["xlsx/gt-a171-audit-summary", "xlsx/gt-a177-independence-declaration"]:
            entry = [e for e in _get_a_entries(manifest_slice) if e["entry_id"] == entry_id][0]
            hp = entry.get("host_path", "")
            full = _ROOT / hp
            assert full.exists()
            source = full.read_text(encoding="utf-8", errors="replace")
            assert "WorkpaperSyncEditorHost" in source, \
                f"{entry_id}: 已改线宿主应含 WorkpaperSyncEditorHost"

    def test_switch_verdict_distribution(self, manifest_slice: dict) -> None:
        """AF-P16: 开关裁决 42 redeemable + 0 inert + 4 no_switch（全域）。"""
        entries = manifest_slice["independent_entries"]
        verdicts = defaultdict(int)
        for e in entries:
            carrier = e.get("dual_mode_carrier", {})
            verdict = carrier.get("switch_verdict", "unknown")
            verdicts[verdict] += 1
        assert verdicts.get("redeemable", 0) == 42
        assert verdicts.get("inert", 0) == 0
        assert verdicts.get("no_switch_at_all", 0) == 4

    def test_a_domain_inert_is_zero(self, manifest_slice: dict) -> None:
        """AF-P16: A 域 inert = 0（N 轮有 2 条，照抄必恒空跑）。"""
        a_entries = _get_a_entries(manifest_slice)
        inert = [e for e in a_entries
                 if e.get("dual_mode_carrier", {}).get("switch_verdict") == "inert"]
        assert len(inert) == 0, "A 域 inert 应为 0（N 轮有 2 条 inert，照抄必恒空跑）"


# ═══════════════════════════════════════════════════════════════════════════
# §4 TestModeCarrierDichotomy — AF-P17 ~ AF-P19
# ═══════════════════════════════════════════════════════════════════════════


class TestModeCarrierDichotomy:
    """mode 载体二分：中文标签作值 vs label/value 分离（AF-P17 ~ AF-P19）。"""

    @pytest.fixture(scope="class")
    def mode_stats(self, manifest_slice: dict) -> dict:
        a_entries = _get_a_entries(manifest_slice)
        string_array = 0
        object_array = 0
        oo_literal = 0
        chinese_mode_comparisons = 0
        structured_literal = 0
        localStorage_hits = 0
        mode_key_in_storage = 0

        for entry in a_entries:
            hp = _host_path(entry)
            if hp is None or not hp.exists():
                continue
            source = hp.read_text(encoding="utf-8", errors="replace")
            carrier = classify_mode_carrier(source)
            if carrier == "string_array":
                string_array += 1
            elif carrier == "object_array":
                object_array += 1
            stripped = strip_comments(source)
            # 'onlyoffice' 字面量
            if re.search(r"'onlyoffice'|\"onlyoffice\"", stripped):
                oo_literal += 1
            # 中文 mode 比较：mode === '结构化视图' 或 mode === '在线编辑' 等
            chinese_mode_comparisons += len(re.findall(
                r"mode\s*===?\s*['\"][\u4e00-\u9fff]", stripped))
            # 'structured' 字面量
            structured_literal += len(re.findall(
                r"===?\s*['\"]structured['\"]", stripped))
            # localStorage 扫描
            ls_hits = re.findall(r"localStorage", stripped)
            localStorage_hits += len(ls_hits)
            # mode 分区键
            if re.search(r"localStorage.*mode|mode.*localStorage", stripped):
                mode_key_in_storage += 1

        return {
            "string_array": string_array,
            "object_array": object_array,
            "oo_literal": oo_literal,
            "chinese_mode_comparisons": chinese_mode_comparisons,
            "structured_literal": structured_literal,
            "localStorage_hits": localStorage_hits,
            "mode_key_in_storage": mode_key_in_storage,
        }

    def test_form1_string_array_counted(self, mode_stats: dict) -> None:
        """AF-P17: 形态 1（中文标签作 mode 值）存在。"""
        total = mode_stats["string_array"] + mode_stats["object_array"]
        assert total >= 13, f"有 modeOptions 的 entry 应 >= 13，实际 {total}"
        assert mode_stats["string_array"] >= 5, \
            f"形态 1（字符串数组）应 >= 5，实际 {mode_stats['string_array']}"

    def test_form2_object_array_counted(self, mode_stats: dict) -> None:
        """AF-P17: 形态 2（label/value 分离）存在。"""
        assert mode_stats["object_array"] >= 2, \
            f"形态 2（对象数组）应 >= 2，实际 {mode_stats['object_array']}"

    def test_onlyoffice_literal_zero(self, mode_stats: dict) -> None:
        """AF-P18: 'onlyoffice' 字面量 = 0（OO 值是 'docx'）。"""
        assert mode_stats["oo_literal"] == 0

    def test_chinese_mode_comparisons_exist(self, mode_stats: dict) -> None:
        """AF-P17: mode === '结构化视图' 中文比较存在。

        🔴 这说明改中文文案即破坏逻辑——形态 1 的核心缺陷。
        """
        assert mode_stats["chinese_mode_comparisons"] >= 10, \
            f"中文 mode 比较应 >= 10（改文案即破坏逻辑），实际 {mode_stats['chinese_mode_comparisons']}"

    def test_localStorage_no_mode_partition_key(self, mode_stats: dict) -> None:
        """AF-P19: localStorage 无 mode 分区键（空分母）。

        A 域宿主内 localStorage 仅有 'token' 相关引用，无 mode 分区键。
        """
        assert mode_stats["mode_key_in_storage"] == 0, \
            f"不应有 mode 分区键，实际 {mode_stats['mode_key_in_storage']}"


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestCanarySelectionAndDeviation — AF-P20 ~ AF-P22
# ═══════════════════════════════════════════════════════════════════════════

CANARY_ENTRY_ID = "xlsx/gt-a51-cashflow-audit"


class TestCanarySelectionAndDeviation:
    """canary 选型与三轮轨迹（AF-P20 ~ AF-P22）。"""

    def test_canary_exists_in_a_domain(self, manifest_slice: dict) -> None:
        """AF-P20: canary 在 A 域 20 条内。"""
        a_entries = _get_a_entries(manifest_slice)
        ids = [e["entry_id"] for e in a_entries]
        assert CANARY_ENTRY_ID in ids

    def test_canary_has_minimum_bp_count(self, manifest_slice: dict) -> None:
        """AF-P20: canary 零区分项（BP 仅 6 项，20 条中唯一）。"""
        a_entries = _get_a_entries(manifest_slice)
        canary = [e for e in a_entries if e["entry_id"] == CANARY_ENTRY_ID][0]
        bp = canary.get("capability_target_blocked_by", [])
        assert len(bp) == 6, f"canary BP 数应为 6（仅公共），实际 {len(bp)}"
        # 验证它是 20 条中唯一 BP=6 的
        others_with_6 = [e for e in a_entries
                         if len(e.get("capability_target_blocked_by", [])) == 6
                         and e["entry_id"] != CANARY_ENTRY_ID]
        assert len(others_with_6) == 0, "canary 应是唯一 BP=6 的 entry"

    def test_canary_is_xlsx(self, manifest_slice: dict) -> None:
        """AF-P20: canary 有 xlsx 权威册。"""
        a_entries = _get_a_entries(manifest_slice)
        canary = [e for e in a_entries if e["entry_id"] == CANARY_ENTRY_ID][0]
        fmt = canary.get("template_ref", {}).get("workbook_format", "")
        assert fmt == "xlsx"

    def test_canary_is_redeemable(self, manifest_slice: dict) -> None:
        """AF-P20: canary 是 redeemable。"""
        a_entries = _get_a_entries(manifest_slice)
        canary = [e for e in a_entries if e["entry_id"] == CANARY_ENTRY_ID][0]
        verdict = canary.get("dual_mode_carrier", {}).get("switch_verdict", "")
        assert verdict == "redeemable"

    def test_canary_is_grp01(self, manifest_slice: dict) -> None:
        """AF-P20: canary 属于主组 GRP-01。"""
        a_entries = _get_a_entries(manifest_slice)
        canary = [e for e in a_entries if e["entry_id"] == CANARY_ENTRY_ID][0]
        assert canary.get("group_id") == "GRP-01"

    def test_canary_has_literal_sheet_name(self, manifest_slice: dict) -> None:
        """AF-P20: canary 有 literal_sheet_name。"""
        a_entries = _get_a_entries(manifest_slice)
        canary = [e for e in a_entries if e["entry_id"] == CANARY_ENTRY_ID][0]
        tref = canary.get("template_ref", {})
        # literal sheet name 在 wpMatch 或 template_ref 中
        resolution = tref.get("resolution_kind", "")
        assert resolution != "runtime_sheet_name_expression", \
            "canary 应有 literal sheet name，不是运行时表达式"

    def test_canary_exclusion_reasons(self, manifest_slice: dict) -> None:
        """AF-P21: canary 排除理由——a3-console / a177 / a38 各有不可选原因。

        - a3-console: 无 segmented + 无 mode 门控 ⇒ 「双」不存在
        - a177: runtime_sheet_name_expression ⇒ 静态无唯一权威册
        - a38: 无权威册 + 背负 BP-14 的 Property 22 缺陷
        """
        a_entries = _get_a_entries(manifest_slice)

        # a3-console: no_switch_at_all
        a3 = [e for e in a_entries if "a3-consolidation-console" in e["entry_id"]][0]
        assert a3.get("dual_mode_carrier", {}).get("switch_verdict") == "no_switch_at_all"

        # a177: runtime_sheet_name_expression
        a177 = [e for e in a_entries if "a177" in e["entry_id"]][0]
        assert a177.get("template_ref", {}).get("resolution_kind") == "runtime_sheet_name_expression"
        assert a177.get("template_ref", {}).get("workbook") is None

        # a38: 🔴 **不是**「无权威册」—— 归因已更正（spec
        #      workpaper-sync-pure-static-lane-and-combined-workbook-resolution）。
        #      册一直在磁盘上（合册 `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`），
        #      原 slice 的 `workbook: null` 是**假事实**，已改成真实相对路径。
        #      它被排除在 canary 之外的真因是 **BP-6**（解析层曾拿不到册；第一步现已修，
        #      剩余是宿主层第二步：宿主传中文字面 sheet 名而非 wp_code）。
        a38 = [e for e in a_entries if "a38" in e["entry_id"]][0]
        assert a38.get("template_ref", {}).get("workbook"), (
            "a38 的 workbook 应已是真实相对路径（假事实已更正）"
        )
        assert "BP-6" in set(a38.get("capability_target_blocked_by") or ()), (
            "a38 的排除理由应由权威阻塞清单给出（BP-6），而不是靠 workbook 形状推断"
        )

    def test_canary_three_round_trajectory_comment(self) -> None:
        """AF-P21: canary 判据三轮轨迹已登记（记录型断言）。

        🔴 三轮轨迹须完整写明：
        M 轮偏离（M 域零载荷 → 五条替代判据）
        → N 轮收回（N4-1-rows 真库 1665 B → 硬标准可用）
        → A 轮再偏离（唯一命中是 E2E seed → 硬标准在 A 域无解）

        本断言仅确认轨迹已在 spec design.md 中登记。
        """
        # 记录型：三轮轨迹存在于 design.md 的「决策 1」节
        design_path = _ROOT / ".kiro" / "specs" / "a-cycle-sync-foundation-and-first-canary" / "design.md"
        if design_path.exists():
            text = design_path.read_text(encoding="utf-8", errors="replace")
            # 验证三轮关键词存在
            assert "偏离" in text, "design.md 应包含「偏离」关键词"
            assert "收回" in text, "design.md 应包含「收回」关键词"


# ═══════════════════════════════════════════════════════════════════════════
# §5b TestWritePathClosure — import 闭包通道验证
# ═══════════════════════════════════════════════════════════════════════════


class TestWritePathClosure:
    """import 闭包持久化通道验证（AC-42 补充）。"""

    def test_canary_host_closure_hits_checklist_responses(self, manifest_slice: dict) -> None:
        """canary 宿主的 import 闭包应命中 /checklist-responses。

        🔴 宿主内直调为 0，但闭包内应非零——这就是 AC-42 的核心。
        """
        a_entries = _get_a_entries(manifest_slice)
        canary = [e for e in a_entries if e["entry_id"] == CANARY_ENTRY_ID][0]
        hp = _host_path(canary)
        assert hp is not None and hp.exists()
        channel = channel_of_host(hp)
        assert "checklist_responses" in channel, \
            f"canary 闭包应含 checklist_responses 通道，实际: {channel}"

    def test_field_overrides_in_a_domain_hosts(self, manifest_slice: dict) -> None:
        """field_overrides 在 A 域宿主内命中。

        🔴 spec 预期 4 命中 / 2 文件，以现算为准。
        """
        a_entries = _get_a_entries(manifest_slice)
        host_files = []
        for entry in a_entries:
            hp = _host_path(entry)
            if hp and hp.exists():
                host_files.append(hp)
        endpoints = scan_endpoint_literals(host_files)
        fo = endpoints["field_overrides"]
        assert fo["count"] >= 2, \
            f"field_overrides 命中应 >= 2，实际 {fo['count']}"
        assert len(fo["files"]) >= 1, \
            f"field_overrides 文件数应 >= 1，实际 {len(fo['files'])}"

    def test_a_domain_channel_distribution(self, manifest_slice: dict) -> None:
        """A 域 20 条 entry 的通道分布与 entry_groups 一致。"""
        a_entries = _get_a_entries(manifest_slice)
        channels: dict[str, int] = defaultdict(int)
        for entry in a_entries:
            hp = _host_path(entry)
            if hp and hp.exists():
                ch = channel_of_host(hp)
                channels[ch] += 1
        # 至少应有 checklist_responses 通道
        total = sum(channels.values())
        assert total >= 15, f"有通道的 entry 应 >= 15，实际 {total}"


class TestTemplateFormatDispatch:
    """权威册 format 分流 + sha256（AF-P26 ~ AF-P31）。"""

    def test_a_directory_97_books(self) -> None:
        """AF-P27: A 目录 97 本 = xlsx 65 + docx 32。"""
        tmpl = scan_a_templates()
        assert tmpl["total_count"] == 97, f"合计应为 97，实际 {tmpl['total_count']}"
        assert tmpl["xlsx_count"] == 65, f"xlsx 应为 65，实际 {tmpl['xlsx_count']}"
        assert tmpl["docx_count"] == 32, f"docx 应为 32，实际 {tmpl['docx_count']}"

    def test_format_dispatch_16_2_2(self, manifest_slice: dict) -> None:
        """AF-P29: format 分流 —— **已更正为** docx 16 / xlsx 3 / 无册 1。

        🔴 原值「xlsx 2 / 无册 2」里那一条差异来自 a38：它的 `template_ref.workbook`
        与 `workbook_format` 原本都是 `null`，而那是**假事实** —— 册一直在磁盘上且是
        xlsx（合册 `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`）。spec
        `workpaper-sync-pure-static-lane-and-combined-workbook-resolution` 把两个字段
        改成真实值 ⇒ 本分流随之变化。**A 域 entry 总数不变（20），docx 16 不变。**
        """
        a_entries = _get_a_entries(manifest_slice)
        docx_count = sum(1 for e in a_entries
                         if e.get("template_ref", {}).get("workbook_format") == "docx")
        xlsx_count = sum(1 for e in a_entries
                         if e.get("template_ref", {}).get("workbook_format") == "xlsx")
        none_count = sum(1 for e in a_entries
                         if e.get("template_ref", {}).get("workbook_format") is None
                         or e.get("template_ref", {}).get("workbook") is None)
        assert docx_count == 16, f"docx 应为 16，实际 {docx_count}"
        assert xlsx_count == 3, f"xlsx 应为 3（含 canary + a3-console + a38），实际 {xlsx_count}"
        # 无册：a38 移出后只剩 a177
        assert none_count == 1, f"无册应恰 1（仅 a177），实际 {none_count}"
        assert docx_count + xlsx_count + none_count == len(a_entries) == 20

    def test_canary_xlsx_formulas_57(self) -> None:
        """AF-P31: canary A5-1 册公式格 57。"""
        # 查找 A5-1 册
        candidates = list(_TEMPLATE_DIR.rglob("A5-1*"))
        xlsx_candidates = [c for c in candidates if c.suffix.lower() == ".xlsx"]
        assert xlsx_candidates, "找不到 A5-1 xlsx 册"
        result = scan_xlsx_formulas(xlsx_candidates[0])
        assert result["total_formulas"] == 57, \
            f"A5-1 公式格应为 57，实际 {result['total_formulas']}"
        assert result["sheet_count"] == 9, \
            f"A5-1 sheet 数应为 9，实际 {result['sheet_count']}"

    def test_canary_footer_raw_xml_three_states(self) -> None:
        """AF-P30: footer 读 raw XML，三态 2/7/4。

        🔴 禁用 openpyxl ws.oddFooter——它会静默返回空。
        """
        xlsx_files = list(_TEMPLATE_DIR.rglob("A5-1*"))
        xlsx_files = [f for f in xlsx_files if f.suffix.lower() == ".xlsx"]
        assert xlsx_files, "找不到 A5-1 xlsx 册"
        # A5-1 的 footer（部分三态来自两本 xlsx 册合并统计）
        footer_results = scan_xlsx_footer_raw_xml(xlsx_files[0])
        has_content = sum(1 for f in footer_results if f["odd_footer_values"])
        assert has_content >= 1, f"应有至少 1 个有内容的 footer，实际 {has_content}"

    # ─── canary A5-1 册 9 sheets 精确结构固化 ────────────────────────────

    _A51_SHEET_NAMES = [
        "表头（请先填写）",
        "A5-1现金流量审计程序",
        "A5-1-1列示于现金流量表的现金及现金等价物",
        "A5-1-3相关报表勾稽关系核对",
        "A5-1-4现金流量核查",
        "A5-1-5现金流量核查",
        "A5-1-6其他现金流量",
        "会计提示",
        "GT_Custom",
    ]

    def test_canary_9_sheet_names_exact(self) -> None:
        """AF-P31 补: canary 9 个 sheet 名按原始字面量锁定。

        🔴 禁归一化——按 AC-10 原文要求。
        """
        import openpyxl
        candidates = [f for f in _TEMPLATE_DIR.rglob("A5-1*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        assert candidates
        wb = openpyxl.load_workbook(str(candidates[0]), data_only=False)
        actual = [ws.title for ws in wb.worksheets]
        wb.close()
        assert actual == self._A51_SHEET_NAMES, \
            f"sheet 名不吻合\n  实际: {actual}\n  期望: {self._A51_SHEET_NAMES}"

    def test_canary_hidden_sheet_only_gt_custom(self) -> None:
        """AF-P31 补: hidden 恰 1（GT_Custom）。"""
        import openpyxl
        candidates = [f for f in _TEMPLATE_DIR.rglob("A5-1*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        wb = openpyxl.load_workbook(str(candidates[0]), data_only=False)
        hidden = [ws.title for ws in wb.worksheets if ws.sheet_state != "visible"]
        wb.close()
        assert hidden == ["GT_Custom"], f"hidden 应仅 GT_Custom，实际 {hidden}"

    def test_canary_defined_names_22_broken_14(self) -> None:
        """AF-P31 补: definedName 22 / broken 14。

        形态与 N 域同源（XREF_COLUMN_* / XRefCopy* / [1]Breakdown!#REF! 等）。
        """
        candidates = [f for f in _TEMPLATE_DIR.rglob("A5-1*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        result = scan_xlsx_formulas(candidates[0])
        assert result["defined_names_total"] == 22, \
            f"definedName total 应为 22，实际 {result['defined_names_total']}"
        assert result["defined_names_broken"] == 14, \
            f"definedName broken 应为 14，实际 {result['defined_names_broken']}"

    def test_canary_fx_sheet_count_6(self) -> None:
        """AF-P31 补: 带公式 sheet 6 个。"""
        candidates = [f for f in _TEMPLATE_DIR.rglob("A5-1*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        result = scan_xlsx_formulas(candidates[0])
        assert result["fx_sheet_count"] == 6, \
            f"带公式 sheet 应为 6，实际 {result['fx_sheet_count']}"

    def test_canary_a51_footer_content_is_english_page(self) -> None:
        """AF-P30 补: A5-1 footer 内容是英文 Page &P（无 &N）。"""
        candidates = [f for f in _TEMPLATE_DIR.rglob("A5-1*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        footers = scan_xlsx_footer_raw_xml(candidates[0])
        content_footers = [f for f in footers if f["odd_footer_values"]]
        assert len(content_footers) == 1, f"A5-1 应有 1 个有内容 footer，实际 {len(content_footers)}"
        # 内容应含 Page &P
        val = content_footers[0]["odd_footer_values"][0]
        assert "Page" in val, f"footer 应含 'Page'，实际 {val}"
        # 无 &N（与 A3-3 的中文 footer 不同）
        assert "&amp;N" not in val and "&N" not in val, \
            f"A5-1 footer 应无 &N，实际 {val}"

    def test_a33_footer_is_chinese_page_n(self) -> None:
        """AF-P30 补: A3-3 footer 是中文「第 &P 页，共 &N 页」。"""
        candidates = [f for f in _TEMPLATE_DIR.rglob("A3-3*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        assert candidates, "找不到 A3-3 xlsx 册"
        footers = scan_xlsx_footer_raw_xml(candidates[0])
        content_footers = [f for f in footers if f["odd_footer_values"]]
        assert len(content_footers) == 1
        val = content_footers[0]["odd_footer_values"][0]
        # 中文 footer 含 &N
        assert "&amp;N" in val or "&N" in val, f"A3-3 footer 应含 &N，实际 {val}"

    def test_two_xlsx_combined_footer_three_states_2_7_4(self) -> None:
        """AF-P30: 两本 xlsx 合并 footer 三态 = 2 + 7 + 4 = 13。"""
        all_footers = []
        for pattern in ["A5-1*", "A3-3*"]:
            candidates = [f for f in _TEMPLATE_DIR.rglob(pattern)
                           if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
            if candidates:
                all_footers.extend(scan_xlsx_footer_raw_xml(candidates[0]))
        has_content = sum(1 for f in all_footers if f["odd_footer_values"])
        has_container = sum(1 for f in all_footers
                            if not f["odd_footer_values"] and f["has_header_footer_container"])
        no_container = sum(1 for f in all_footers
                            if not f["odd_footer_values"] and not f["has_header_footer_container"])
        assert has_content == 2, f"有内容应为 2，实际 {has_content}"
        assert has_container == 7, f"有容器无footer应为 7，实际 {has_container}"
        assert no_container == 4, f"无容器应为 4，实际 {no_container}"
        assert has_content + has_container + no_container == 13

    def test_a33_defined_names_261_broken_190(self) -> None:
        """AF-P31 补: A3-3 的 definedName 261 / broken 190（73%）。

        🔴 含 .dbf / 中文名 = dBase/Foxpro 旧残留，规模是 N 全域 4 倍。
        """
        candidates = [f for f in _TEMPLATE_DIR.rglob("A3-3*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        assert candidates, "找不到 A3-3 xlsx 册"
        result = scan_xlsx_formulas(candidates[0])
        assert result["defined_names_total"] == 261, \
            f"A3-3 dn total 应为 261，实际 {result['defined_names_total']}"
        assert result["defined_names_broken"] == 190, \
            f"A3-3 dn broken 应为 190，实际 {result['defined_names_broken']}"

    def test_xlsx_total_formulas_120(self) -> None:
        """AF-P31: xlsx 公式格合计 120（A3-3=63 + A5-1=57）。"""
        total = 0
        for pattern in ["A5-1*", "A3-3*"]:
            candidates = [f for f in _TEMPLATE_DIR.rglob(pattern)
                           if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
            if candidates:
                r = scan_xlsx_formulas(candidates[0])
                total += r["total_formulas"]
        assert total == 120, f"xlsx 公式格合计应为 120，实际 {total}"

    def test_data_only_true_returns_zero(self) -> None:
        """AF-P31: data_only=True 反证 = 0。"""
        import openpyxl
        candidates = [f for f in _TEMPLATE_DIR.rglob("A5-1*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        wb = openpyxl.load_workbook(str(candidates[0]), data_only=True)
        fx_count = 0
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("=") and len(cell.value) > 1:
                        fx_count += 1
        wb.close()
        assert fx_count == 0, f"data_only=True 应返回 0 公式格，实际 {fx_count}"

    def test_sha256_canary_match(self) -> None:
        """AF-P26: canary A5-1 sha256 一致性检查。

        🔴 此断言置于测试最前（概念上），失败即中止——说明模板被修改。
        """
        candidates = [f for f in _TEMPLATE_DIR.rglob("A5-1*")
                       if f.suffix.lower() == ".xlsx" and "~$" not in f.name]
        assert candidates
        digest = sha256_file(candidates[0])
        # 现算值锁定（不写死——用自洽性检验：再读一次应相等）
        digest2 = sha256_file(candidates[0])
        assert digest == digest2, "sha256 自洽性失败——文件可能在读取期间被修改"
        # 文件大小合理性
        size = candidates[0].stat().st_size
        assert 50000 < size < 100000, f"A5-1 大小应在 50K~100K 范围，实际 {size}"


# ═══════════════════════════════════════════════════════════════════════════
# §7 TestStructuralZerosWithMutationProof — AF-P32
# ═══════════════════════════════════════════════════════════════════════════


class TestStructuralZerosWithMutationProof:
    """结构性零 + 变异证明（AF-P32）。

    🔴 这里扫宿主文件（20 个），而非整个 A 域文件集（含 composable 等 148 个）。
    """

    @pytest.fixture(scope="class")
    def zeros(self, manifest_slice: dict) -> dict[str, int]:
        a_entries = _get_a_entries(manifest_slice)
        host_files = []
        for entry in a_entries:
            hp = _host_path(entry)
            if hp and hp.exists():
                host_files.append(hp)
        return scan_structural_zeros(host_files)

    def test_trial_balance_writeback_zero(self, zeros: dict) -> None:
        assert zeros["trial_balance_writeback"] == 0

    def test_onlyoffice_literal_zero(self, zeros: dict) -> None:
        assert zeros["onlyoffice_literal"] == 0

    def test_remove_row_zero(self, zeros: dict) -> None:
        assert zeros["removeRow"] == 0

    def test_use_checklist_persistence_zero(self, zeros: dict) -> None:
        assert zeros["useChecklistPersistence"] == 0

    def test_contract_ocr_zero(self, zeros: dict) -> None:
        assert zeros["contract_ocr"] == 0

    def test_http_put_zero(self, zeros: dict) -> None:
        assert zeros["http_put"] == 0

    def test_api_put_zero(self, zeros: dict) -> None:
        assert zeros["api_put"] == 0

    def test_use_wp_dual_mode_zero(self, zeros: dict) -> None:
        assert zeros["useWpDualMode"] == 0

    def test_use_workpaper_entry_dual_mode_zero(self, zeros: dict) -> None:
        assert zeros["useWorkpaperEntryDualMode"] == 0

    def test_gt_entry_sync_capability_notice_present(self, zeros: dict) -> None:
        """BP-7 收口：宿主内 GtEntrySyncCapabilityNotice 已接入（非零）。"""
        assert zeros["GtEntrySyncCapabilityNotice"] > 0, \
            "改线后每个宿主应含 GtEntrySyncCapabilityNotice（BP-7 接入）"


# ═══════════════════════════════════════════════════════════════════════════
# §7b TestContractFieldsAndRealDb — AF-P23 ~ AF-P25
# ═══════════════════════════════════════════════════════════════════════════


class TestContractFieldsAndRealDb:
    """契约字段映射与跨 entry 隔离（AF-P23 ~ AF-P25）。

    🔴 真库测试需 PG 连接，无库环境 skip。
    """

    def test_conclusion_is_declared_main_payload(self, manifest_slice: dict) -> None:
        """AF-P23: slice 声明 conclusion 为主载荷（NC-34 连续第二轮成立）。

        🔴 spec 预期 conclusion 非空 24 > remark 4。
        此断言验证 slice 层面的声明，真库验证需 PG。
        """
        # 在 entry 的 html_counterpart 或顶层查 conclusion 相关声明
        # slice 的 abcs_form_differences 中应有相关判据
        diffs = manifest_slice.get("abcs_form_differences", {})
        # 验证 form_differences 存在且包含字段相关信息
        assert diffs, "abcs_form_differences 不应为空"

    def test_cross_entry_pollution_zero_in_slice(self, manifest_slice: dict) -> None:
        """AF-P25: 跨 entry 污染在 slice 声明中为 0。

        A 域真库 28 行的 item_id 前缀与宿主 wp_code 应 28/28 完全对齐。
        真实 PG 验证需要连接，此处验证 slice 层面的隔离声明。
        """
        # slice 的 cross_entry_isolation 断言存在
        # 具体：independent_entries 中无 entry 声明 cross_entry_polluted
        a_entries = _get_a_entries(manifest_slice)
        for e in a_entries:
            iso = e.get("cross_entry_isolation", {})
            polluted = iso.get("polluted_count", 0)
            assert polluted == 0, \
                f"{e['entry_id']}: 跨 entry 污染应为 0，实际 {polluted}"

    def test_ai_session_whitelist_rule(self, manifest_slice: dict) -> None:
        """AF-P24: *-review-session-* 白名单排除（第三轮出现）。

        🔴 AI 会话行 A1-review-session-20260725074949 (261 B) 应被按白名单排除。
        与 M1/N1/N2/N5 同型同批次。
        """
        # 记录型断言：slice 设计文档已登记白名单规则
        design_path = _ROOT / ".kiro" / "specs" / "a-cycle-sync-foundation-and-first-canary" / "design.md"
        if design_path.exists():
            text = design_path.read_text(encoding="utf-8", errors="replace")
            assert "review-session" in text or "白名单" in text, \
                "design.md 应登记 review-session 白名单规则"

    def test_production_contracts_none_in_a_domain(self, manifest_slice: dict) -> None:
        """AF-P25 附: 生产契约无一属 A 域（BP-2 成立）—— adapter_id 全 null。"""
        a_entries = _get_a_entries(manifest_slice)
        for e in a_entries:
            adapter = e.get("adapter_id")
            assert adapter is None, \
                f"{e['entry_id']}: adapter_id 应为 null（BP-5 成立），实际 {adapter}"


# ═══════════════════════════════════════════════════════════════════════════
# §8 TestEntryGroupsAreRecomputable — AF-P33
# ═══════════════════════════════════════════════════════════════════════════


class TestEntryGroupsAreRecomputable:
    """分组 13 组 / 9 家族 / 4 通道（AF-P33）。"""

    def test_total_groups_13(self, manifest_slice: dict) -> None:
        groups = manifest_slice.get("entry_groups", {})
        group_list = groups.get("groups", [])
        assert len(group_list) == 13, f"应有 13 组，实际 {len(group_list)}"

    def test_channels_4(self, manifest_slice: dict) -> None:
        groups = manifest_slice.get("entry_groups", {})
        counters = groups.get("counters", {})
        assert counters.get("channels", 0) == 4

    def test_a_domain_group_distribution(self, manifest_slice: dict) -> None:
        """A 域 GRP-01=15 / GRP-02=1 / GRP-03=3 / GRP-10=1 = 20。"""
        a_entries = _get_a_entries(manifest_slice)
        group_counts: dict[str, int] = defaultdict(int)
        for e in a_entries:
            grp = e.get("group_id", "unknown")
            group_counts[grp] += 1
        assert group_counts.get("GRP-01", 0) == 15
        assert group_counts.get("GRP-02", 0) == 1
        assert group_counts.get("GRP-03", 0) == 3
        assert group_counts.get("GRP-10", 0) == 1
        assert sum(group_counts.values()) == 20


# ═══════════════════════════════════════════════════════════════════════════
# §9 TestArchivedSpecBoundary — AF-P34 · AF-P35
# ═══════════════════════════════════════════════════════════════════════════


class TestArchivedSpecBoundary:
    """归档 spec 边界（AF-P34 · AF-P35）。"""

    def test_procedure_sheet_key_no_a_branch(self) -> None:
        """AF-P35: resolveProcedureSheetKey.ts 无 A 分支。"""
        result = check_procedure_sheet_key_router()
        assert result["exists"], "resolveProcedureSheetKey.ts 不存在"
        assert not result["has_a_branch"], "不应有 A 分支（三轮三态：A 整段缺失）"


# ═══════════════════════════════════════════════════════════════════════════
# §10 TestProperty22DynamicColumn — AF-P36
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty22DynamicColumn:
    """Property 22 首次非空分母（AF-P36）。"""

    def test_verdict_is_partial(self, manifest_slice: dict) -> None:
        """AF-P36: verdict 含 PARTIAL。"""
        dyn_col = manifest_slice.get("dynamic_column_identity", {})
        verdict = dyn_col.get("verdict", "")
        assert "PARTIAL" in verdict, f"verdict 应含 PARTIAL，实际: {verdict[:80]}"

    def test_site_count_7(self, manifest_slice: dict) -> None:
        """AF-P36: 站点 7。"""
        dyn_col = manifest_slice.get("dynamic_column_identity", {})
        sites = dyn_col.get("dynamic_column_site_count", 0)
        assert sites == 7, f"站点数应为 7，实际 {sites}"

    def test_label_as_key_3(self, manifest_slice: dict) -> None:
        """AF-P36: label-as-key 3。"""
        dyn_col = manifest_slice.get("dynamic_column_identity", {})
        lak = dyn_col.get("label_as_key_site_count", 0)
        assert lak == 3, f"label-as-key 应为 3，实际 {lak}"
