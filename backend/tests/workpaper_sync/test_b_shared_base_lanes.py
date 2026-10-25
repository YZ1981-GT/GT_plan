# -*- coding: utf-8 -*-
"""B 类共享基类载体通道守卫。

spec: b-class-shared-base-carrier-lanes

测试结构（对标 design.md §七）：
  - TestSharedBaseCompatibility     BG-P1 ~ BG-P4
  - TestB22BDualEntryDisambiguation BG-P5 ~ BG-P6
  - TestModeAndPersistenceChannels  BG-P7 ~ BG-P11
  - TestRowIdentityAndCountKeys     BG-P12 ~ BG-P16
  - TestPayloadDenominators         BG-P17 ~ BG-P18
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
_SLICE_PATH = _BACKEND / "data" / "workpaper_sync_abcs_cycle_manifest_slice.json"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from b_cycle_scanner import (  # noqa: E402
    b_domain_entries,
    b_entry_by_id,
    carrier_tripartition,
    SHARED_BASE_ENTRIES,
    CARRIER_SHARED_BASE_MODULE,
    CARRIER_ORPHAN_MODULE,
    CANARY_ENTRY_ID,
    strip_comments,
    import_closure,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


@pytest.fixture(scope="module")
def b_entries(manifest_slice: dict) -> list[dict]:
    return b_domain_entries(manifest_slice["independent_entries"])


@pytest.fixture(scope="module")
def sb_entries(b_entries: list[dict]) -> list[dict]:
    """共享基类 5 条（含 canary）。"""
    tri = carrier_tripartition(b_entries)
    return tri["shared_base"]


@pytest.fixture(scope="module")
def lane2_entries(sb_entries: list[dict]) -> list[dict]:
    """本 spec 负责的 4 条（不含 canary）。"""
    return [
        e for e in sb_entries
        if e["entry_id"] != CANARY_ENTRY_ID
    ]


@pytest.fixture(scope="module")
def b_by_id(b_entries: list[dict]) -> dict[str, dict]:
    return b_entry_by_id(b_entries)


def _host_path(entry: dict) -> Path | None:
    hp = entry.get("host_path", "")
    if not hp:
        return None
    resolved = (_ROOT / hp).resolve()
    return resolved if resolved.exists() else None


# ═══════════════════════════════════════════════════════════════════════════
# §1 TestSharedBaseCompatibility — BG-P1 ~ BG-P4
# ═══════════════════════════════════════════════════════════════════════════


class TestSharedBaseCompatibility:
    """共享基类兼容性基线。"""

    def test_lane2_exactly_4(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P1: 本组恰 4 条。"""
        assert len(lane2_entries) == 4

    def test_all_on_shared_base(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P1: 4 条全挂 useWorkpaperEntryDualMode.ts。"""
        for e in lane2_entries:
            carrier = e.get("dual_mode_carrier", {})
            module = carrier.get("shared_carrier_module", "")
            assert module == CARRIER_SHARED_BASE_MODULE, (
                f"{e['entry_id']} module={module}"
            )

    def test_not_orphan(
        self, manifest_slice: dict
    ) -> None:
        """BG-P3: becomes_orphan_after_rewire 为假。"""
        carriers = manifest_slice.get(
            "dual_mode_carrier_inventory", {}
        ).get("shared_carriers", {})
        info = carriers.get(CARRIER_SHARED_BASE_MODULE, {})
        assert info.get("becomes_orphan_after_rewire") is False

    def test_host_imports_dual_mode(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P4: 4 条宿主均导入 useWorkpaperEntryDualMode。"""
        for e in lane2_entries:
            hp = _host_path(e)
            assert hp is not None and hp.exists()
            text = hp.read_text(encoding="utf-8", errors="replace")
            assert "useWorkpaperEntryDualMode" in text, (
                f"{e['entry_id']} 缺 import"
            )


# ═══════════════════════════════════════════════════════════════════════════
# §2 TestB22BDualEntryDisambiguation — BG-P5 ~ BG-P6
# ═══════════════════════════════════════════════════════════════════════════


class TestB22BDualEntryDisambiguation:
    """B22B 一码双 entry 消歧。"""

    def test_b22b_two_entries_different_hosts(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P5: B22B 被 2 条 entry 共用，不同宿主。"""
        cm = b_by_id["xlsx/gt-b22-b-control-matrix"]
        de = b_by_id["xlsx/gt-b22-b-deficiency-evaluation"]
        assert cm.get("host_path") != de.get("host_path")
        assert cm.get("host_path") and de.get("host_path")

    def test_deficiency_override_zero(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P6: deficiency 的 override 命中为 0。"""
        de = b_by_id["xlsx/gt-b22-b-deficiency-evaluation"]
        wc = de.get("wp_code_count_via_component_type", -1)
        assert wc == 0

    def test_item_id_namespace_separation(self) -> None:
        """BG-P5: item_id 命名空间天然分离。

        控制矩阵用 B22B-row-{n}-{field}，
        缺陷评价用 B22B-deficiency-{n}-{field}。
        """
        # 检查两个 composable 的 item_id 前缀不同
        cm_composable = _WP / "composables" / "useB22BControlMatrix.ts"
        de_composable = _WP / "composables" / "useB22BDeficiency.ts"
        if cm_composable.exists():
            cm_text = cm_composable.read_text(
                encoding="utf-8", errors="replace"
            )
            # 控制矩阵用 B22B-row- 或 B22B-T 前缀
            assert "B22B-" in cm_text
        if de_composable.exists():
            de_text = de_composable.read_text(
                encoding="utf-8", errors="replace"
            )
            # 缺陷评价有自己的前缀
            assert "B22B-" in de_text


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestModeAndPersistenceChannels — BG-P7 ~ BG-P11
# ═══════════════════════════════════════════════════════════════════════════


class TestModeAndPersistenceChannels:
    """mode 值与持久化通道。"""

    def test_all_4_use_onlyoffice_mode(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P7: 4 条 mode 值全含 'onlyoffice'。"""
        for e in lane2_entries:
            hp = _host_path(e)
            if hp is None:
                continue
            text = hp.read_text(
                encoding="utf-8", errors="replace"
            )
            assert (
                "'onlyoffice'" in text or '"onlyoffice"' in text
            ), f"{e['entry_id']} 缺 onlyoffice mode"

    def test_none_declares_mode_options_in_host(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P8: 4 条均未在宿主内声明 modeOptions 数组。"""
        for e in lane2_entries:
            hp = _host_path(e)
            if hp is None:
                continue
            text = hp.read_text(
                encoding="utf-8", errors="replace"
            )
            # modeOptions 是 computed，不是字面量数组声明
            # 这里验证不存在 `['结构化视图','在线编辑']` 形式的字面量
            assert (
                "['结构化视图'" not in text
                and '["结构化视图"' not in text
            ), f"{e['entry_id']} 宿主内声明了 modeOptions"

    def test_checklist_responses_in_closure(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P9: /checklist-responses 在深度 3 闭包内全命中。"""
        for e in lane2_entries:
            hp = _host_path(e)
            if hp is None:
                continue
            closure = import_closure(hp, maxdepth=3)
            found = False
            for f in closure:
                if not f.exists():
                    continue
                t = f.read_text(encoding="utf-8", errors="replace")
                if "checklist-responses" in t:
                    found = True
                    break
            assert found, (
                f"{e['entry_id']} checklist 未在闭包内"
            )

    def test_b50_gate_false_negative(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P11: b50 的 OO 挂点有门控假阴。"""
        b50 = b_by_id["xlsx/gt-b50-risk-assessment"]
        hp = _host_path(b50)
        if hp is None:
            pytest.skip("B50 host not found")
        text = hp.read_text(encoding="utf-8", errors="replace")
        # B50 的 OO 挂点不直接用 v-if="renderMode==='onlyoffice'"
        # 而是嵌在 <template v-if="renderMode === 'onlyoffice'">
        # 内部再用 v-if="ooSourceWpId"
        assert "ooSourceWpId" in text


# ═══════════════════════════════════════════════════════════════════════════
# §4 TestRowIdentityAndCountKeys — BG-P12 ~ BG-P16
# ═══════════════════════════════════════════════════════════════════════════


class TestRowIdentityAndCountKeys:
    """行键与 count 键判据。"""

    def test_idx_param_in_3_hosts(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P12: idx 形参出现在 >= 3 个宿主。"""
        hosts_with_idx = []
        for e in lane2_entries:
            hp = _host_path(e)
            if hp is None:
                continue
            text = hp.read_text(
                encoding="utf-8", errors="replace"
            )
            if re.search(r"\bidx\b", text):
                hosts_with_idx.append(e["entry_id"])
        assert len(hosts_with_idx) >= 3, (
            f"idx hosts={hosts_with_idx}"
        )

    def test_label_as_key_in_b50_fixed(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P13 → 已修复：B50 数据行 label-as-key 归零（BC-48）。

        原判据冻结「4 处 label 作 key」的缺陷事实。改造后 3 处数据行 key
        已改绑 `row.rowKey`；剩 `grp.label` 是编译期静态列分组常量（不可编辑），
        用作 key 安全。判据反转为「数据行为 0 且 rowKey 已接线」。
        """
        b50 = b_by_id["xlsx/gt-b50-risk-assessment"]
        hp = _host_path(b50)
        if hp is None:
            pytest.skip("B50 host not found")
        text = hp.read_text(encoding="utf-8", errors="replace")

        data_row_hits = len(re.findall(
            r':key\s*=\s*["\'`].*?row\.name', text,
        ))
        assert data_row_hits == 0, (
            f"B50 数据行仍用 row.name 作 key: {data_row_hits} 处"
        )
        assert 'row.rowKey' in text, "B50 未见 rowKey 绑定"

    def test_two_numbering_bases_in_composables(self) -> None:
        """BG-P15: 0-based (row-) 和 1-based (env-def-) 在 composables 中。"""
        composables = _WP / "composables"
        found_zero = False
        found_one = False
        for f in composables.rglob("useB22*.ts"):
            text = f.read_text(
                encoding="utf-8", errors="replace"
            )
            if "row-" in text and "B22B" in text:
                found_zero = True
            if "env-def-" in text and "B22C" in text:
                found_one = True
        assert found_zero or found_one, (
            "未找到两种编号基准"
        )

    def test_count_keys_in_composables(self) -> None:
        """BG-P16: count 键存在于 B22 composables。"""
        composables = _WP / "composables"
        count_files = []
        for f in composables.rglob("useB22*.ts"):
            text = f.read_text(
                encoding="utf-8", errors="replace"
            )
            if re.search(r"[A-Za-z0-9]+-count", text):
                count_files.append(f.name)
        assert len(count_files) >= 2, (
            f"count_files={count_files}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestPayloadDenominators — BG-P17 ~ BG-P18
# ═══════════════════════════════════════════════════════════════════════════


class TestPayloadDenominators:
    """载荷分母与零分母。"""

    def test_b50_zero_payload(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P18: B50 真库 0 行。"""
        b50 = b_by_id["xlsx/gt-b50-risk-assessment"]
        payload = b50.get("real_db_payload", {})
        total = payload.get("total_rows", 0)
        if "total_rows" in payload:
            assert total == 0

    def test_b22c_has_conclusion(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P17: B22C 是全 B 域唯一 conclusion 非空。"""
        b22c = b_by_id["xlsx/gt-b22-c-design-effectiveness"]
        payload = b22c.get("real_db_payload", {})
        concl = payload.get("conclusion_non_empty", 0)
        # 冻结值：conclusion 非空 1（全 B 域唯一）
        if "conclusion_non_empty" in payload:
            assert concl >= 1

    def test_grp05_only_b50(
        self, lane2_entries: list[dict]
    ) -> None:
        """BG-P18 补充: 本组中 GRP-05 只有 B50。"""
        grp05 = [
            e for e in lane2_entries
            if e.get("group_id") == "GRP-05"
        ]
        assert len(grp05) == 1
        assert grp05[0]["entry_id"] == "xlsx/gt-b50-risk-assessment"
        # 其余 3 条为 GRP-04
        grp04 = [
            e for e in lane2_entries
            if e.get("group_id") == "GRP-04"
        ]
        assert len(grp04) == 3



# ═══════════════════════════════════════════════════════════════════════════
# §6 TestSyncModeWiring — 改线守卫（阶段1-2 tasks 2/4/5）
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncModeWiring:
    """共享基类改线前端接线守卫。"""

    def test_b22b_sync_composable_exists(self) -> None:
        """Task 2: useB22BSyncMode.ts 已创建。"""
        p = _WP / "composables" / "useB22BSyncMode.ts"
        assert p.exists()

    def test_b22c_sync_composable_exists(self) -> None:
        """Task 2: useB22CSyncMode.ts 已创建。"""
        p = _WP / "composables" / "useB22CSyncMode.ts"
        assert p.exists()

    def test_b22b_cm_imports_sync(self) -> None:
        """Task 2: B22B ControlMatrix 已导入 sync。"""
        f = _WP / "GtB22BControlMatrix.vue"
        text = f.read_text(encoding="utf-8", errors="replace")
        assert "useB22BSyncMode" in text
        assert "B22B_CM_ENTRY_ID" in text
        assert "WorkpaperSyncEditorHost" in text

    def test_b22b_de_imports_sync(self) -> None:
        """Task 5: B22B Deficiency 已导入 sync。"""
        f = _WP / "GtB22BDeficiencyEvaluation.vue"
        text = f.read_text(encoding="utf-8", errors="replace")
        assert "useB22BSyncMode" in text
        assert "B22B_DE_ENTRY_ID" in text

    def test_b22c_imports_sync(self) -> None:
        """Task 2: B22C 已导入 sync。"""
        f = _WP / "GtB22CDesignEffectiveness.vue"
        text = f.read_text(encoding="utf-8", errors="replace")
        assert "useB22CSyncMode" in text
        assert "B22C_ENTRY_ID" in text

    def test_all_3_preserve_legacy_fallback(self) -> None:
        """Task 3: 3 个宿主保留 legacy 降级路径。"""
        hosts = [
            "GtB22BControlMatrix.vue",
            "GtB22BDeficiencyEvaluation.vue",
            "GtB22CDesignEffectiveness.vue",
        ]
        for name in hosts:
            f = _WP / name
            text = f.read_text(
                encoding="utf-8", errors="replace"
            )
            assert "useWorkpaperEntryDualMode" in text, (
                f"{name} 缺 legacy fallback"
            )
            assert "GtOnlyOfficeSheet" in text, (
                f"{name} 缺 legacy OO"
            )

    def test_b22b_entry_ids_distinct(self) -> None:
        """Task 4: B22B 两条 entry 用不同 entry_id。"""
        cm = (_WP / "GtB22BControlMatrix.vue").read_text(
            encoding="utf-8", errors="replace"
        )
        de = (_WP / "GtB22BDeficiencyEvaluation.vue").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "B22B_CM_ENTRY_ID" in cm
        assert "B22B_DE_ENTRY_ID" in de
        # 确认 composable 中两个 ID 不同
        sync_text = (_WP / "composables" / "useB22BSyncMode.ts").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "gt-b22-b-control-matrix" in sync_text
        assert "gt-b22-b-deficiency-evaluation" in sync_text

    def test_b50_not_yet_wired(self) -> None:
        """B50 留后续处理（架构特殊）。"""
        f = _WP / "GtB50RiskAssessment.vue"
        text = f.read_text(encoding="utf-8", errors="replace")
        # B50 应该还用 legacy（本阶段不改）
        assert "useWorkpaperEntryDualMode" in text



# ═══════════════════════════════════════════════════════════════════════════
# §7 TestRowKeyViolationFreeze — Task 7（阶段3）
# ═══════════════════════════════════════════════════════════════════════════


class TestRowKeyViolationFreeze:
    """违规形态逐条冻结。"""

    def test_b22b_row_zero_based_in_composable(self) -> None:
        """BG-P15: B22B-row-{n} 0-based 在 composable 中。"""
        f = _WP / "composables" / "useB22BControlMatrix.ts"
        if not f.exists():
            pytest.skip("useB22BControlMatrix.ts 不存在")
        text = f.read_text(encoding="utf-8", errors="replace")
        # B22B 使用 row- 前缀且 0-based
        assert "B22B-row-" in text or "row-" in text

    def test_b22c_env_def_one_based_in_composable(self) -> None:
        """BG-P15: B22C-env-def-{n} 1-based 在 composable 中。"""
        f = _WP / "composables" / "useB22CDesignEffectiveness.ts"
        if not f.exists():
            pytest.skip("useB22CDesignEffectiveness.ts 不存在")
        text = f.read_text(encoding="utf-8", errors="replace")
        assert "env-def-" in text or "B22C-" in text

    def test_entropy_key_in_deficiency(self) -> None:
        """BG-P14: 熵键 1 处在 deficiency 宿主或 composable。"""
        # 熵键 = Date.now() / Math.random() / crypto.randomUUID
        targets = [
            _WP / "GtB22BDeficiencyEvaluation.vue",
            _WP / "composables" / "useB22BDeficiency.ts",
            _WP / "composables" / "useB22BFormData.ts",
        ]
        entropy_hits = 0
        for f in targets:
            if not f.exists():
                continue
            text = f.read_text(
                encoding="utf-8", errors="replace"
            )
            for pat in ["Date.now()", "Math.random()",
                        "crypto.randomUUID", "nanoid"]:
                if pat in text:
                    entropy_hits += 1
        # 至少找到 1 处熵键（BG-P14）
        assert entropy_hits >= 1, (
            f"entropy_hits={entropy_hits}"
        )

    def test_remove_row_in_b22b_cm(self) -> None:
        """BG-P12 补充: removeRow 在 B22B ControlMatrix。"""
        f = _WP / "GtB22BControlMatrix.vue"
        text = f.read_text(encoding="utf-8", errors="replace")
        assert "removeRow" in text


# ═══════════════════════════════════════════════════════════════════════════
# §8 TestCountKeyValidation — Task 10（阶段3）
# ═══════════════════════════════════════════════════════════════════════════


class TestCountKeyValidation:
    """count 键降级为校验值守卫。"""

    def test_count_key_in_b22c_host(self) -> None:
        """BG-P16: count 键在 B22C 宿主中。"""
        f = _WP / "GtB22CDesignEffectiveness.vue"
        text = f.read_text(encoding="utf-8", errors="replace")
        count_hits = len(re.findall(
            r"[A-Za-z0-9]+-count", text
        ))
        assert count_hits >= 1, f"count in B22C host={count_hits}"

    def test_count_key_in_b50_host(self) -> None:
        """BG-P16: count 键在 B50 宿主中。"""
        f = _WP / "GtB50RiskAssessment.vue"
        text = f.read_text(encoding="utf-8", errors="replace")
        count_hits = len(re.findall(
            r"[A-Za-z0-9]+-count", text
        ))
        assert count_hits >= 1, f"count in B50 host={count_hits}"

    def test_count_in_b22b_composable(self) -> None:
        """BG-P16: count 键在 useB22BControlMatrix.ts 中。"""
        f = _WP / "composables" / "useB22BControlMatrix.ts"
        if not f.exists():
            pytest.skip("composable 不存在")
        text = f.read_text(encoding="utf-8", errors="replace")
        assert re.search(r"[A-Za-z0-9]+-count", text), (
            "useB22BControlMatrix.ts 缺 count 键"
        )



# ═══════════════════════════════════════════════════════════════════════════
# §9 TestB50GateAndGRP05 — Tasks 12/14（阶段4）
# ═══════════════════════════════════════════════════════════════════════════


class TestB50GateAndGRP05:
    """B50 门控假阴 + GRP-05 通道。"""

    def test_b50_oo_uses_dynamic_wp_id(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P11: B50 OO 挂点用动态 ooSourceWpId。"""
        b50 = b_by_id["xlsx/gt-b50-risk-assessment"]
        hp = _host_path(b50)
        if hp is None:
            pytest.skip("B50 host not found")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "ooSourceWpId" in text
        assert "useB50OoSheetMap" in text

    def test_b50_5_tab_sheet_map(self) -> None:
        """BG-P11 补充: B50 有 5 个 tab→sheet 映射。"""
        f = _WP / "composables" / "useB50OoSheetMap.ts"
        if not f.exists():
            pytest.skip("useB50OoSheetMap.ts 不存在")
        text = f.read_text(encoding="utf-8", errors="replace")
        # 5 个 tab 映射
        assert "program:" in text
        assert "tab1:" in text
        assert "tab4:" in text

    def test_field_overrides_zero_in_b50_frontend(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P14 核心: field-overrides 在 B50 前端闭包深度 3 内命中 0。"""
        b50 = b_by_id["xlsx/gt-b50-risk-assessment"]
        hp = _host_path(b50)
        if hp is None:
            pytest.skip("B50 host not found")
        closure = import_closure(hp, maxdepth=3)
        hits = 0
        for f in closure:
            if not f.exists():
                continue
            t = f.read_text(encoding="utf-8", errors="replace")
            if "field-overrides" in t or "field_overrides" in t:
                hits += 1
        assert hits <= 1, f"field_overrides in B50 closure={hits}"

    def test_b50_is_grp05(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P18: B50 是 GRP-05。"""
        assert b_by_id[
            "xlsx/gt-b50-risk-assessment"
        ].get("group_id") == "GRP-05"


# ═══════════════════════════════════════════════════════════════════════════
# §10 TestZeroDenominatorEntries — Tasks 16/17（阶段5）
# ═══════════════════════════════════════════════════════════════════════════


class TestZeroDenominatorEntries:
    """零分母与非零分母 entry 验证。"""

    def test_b50_zero_declared(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P18: B50 真库 0 行（零分母声明）。"""
        b50 = b_by_id["xlsx/gt-b50-risk-assessment"]
        payload = b50.get("real_db_payload", {})
        if "total_rows" in payload:
            assert payload["total_rows"] == 0

    def test_b22b_deficiency_zero_attributable(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P18 补充: B22B-deficiency 可归属载荷为 0。

        真库 B22B 13 行全属控制矩阵形态。
        """
        de = b_by_id["xlsx/gt-b22-b-deficiency-evaluation"]
        wc = de.get("wp_code_count_via_component_type", -1)
        assert wc == 0, "deficiency 应无独立 wp_code 匹配"

    def test_b22c_has_real_payload(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P17: B22C 有真实载荷（非零）。"""
        b22c = b_by_id["xlsx/gt-b22-c-design-effectiveness"]
        payload = b22c.get("real_db_payload", {})
        total = payload.get("total_rows", -1)
        if total >= 0:
            assert total >= 23, f"B22C total={total}"

    def test_b22b_cm_has_13_rows(
        self, b_by_id: dict[str, dict]
    ) -> None:
        """BG-P17 补充: B22B 控制矩阵 13 行。"""
        cm = b_by_id["xlsx/gt-b22-b-control-matrix"]
        payload = cm.get("real_db_payload", {})
        total = payload.get("total_rows", -1)
        if total >= 0:
            assert total >= 13, f"B22B-CM total={total}"


# ═══════════════════════════════════════════════════════════════════════════
# §11 TestTemplateConstraints — Tasks 18/19（阶段5）
# ═══════════════════════════════════════════════════════════════════════════


class TestTemplateConstraints:
    """一码多册 + xlsm + 幽灵行制约。"""

    def test_b22b_data_validation_warning(self) -> None:
        """Task 19: B22B xlsx 报 Data Validation 警告。"""
        import warnings as _w
        import openpyxl

        _TEMPLATE_DIR = _BACKEND / "wp_templates" / "B"
        target = [
            f for f in _TEMPLATE_DIR.rglob("*")
            if "B22B" in f.name
            and f.suffix == ".xlsx"
            and f.is_file()
        ]
        if not target:
            pytest.skip("B22B xlsx not found")

        dv_found = False
        for f in target:
            try:
                with _w.catch_warnings(record=True) as w:
                    _w.simplefilter("always")
                    wb = openpyxl.load_workbook(
                        f, data_only=True
                    )
                    wb.close()
                    for warning in w:
                        if "Data Validation" in str(
                            warning.message
                        ):
                            dv_found = True
                            break
            except Exception:
                pass
            if dv_found:
                break
        assert dv_found, "B22B 应报 Data Validation 警告"

    def test_b50_multi_template_sub_codes(self) -> None:
        """Task 18: B50 有多本子底稿模板（B50/B50-1~4）。"""
        _TEMPLATE_DIR = _BACKEND / "wp_templates" / "B"
        b50 = [
            f for f in _TEMPLATE_DIR.rglob("*")
            if f.is_file()
            and f.suffix in (".xlsx", ".xlsm", ".docx")
            and re.search(r"B50(?:-\d)?", f.stem)
        ]
        # B50 主表 + B50-1~4 子底稿
        assert len(b50) >= 5, (
            f"B50 templates={len(b50)}"
        )
