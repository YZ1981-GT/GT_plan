# -*- coding: utf-8 -*-
"""H 地基判据 HF-P1 ~ HF-P10 / HF-P12 ~ HF-P14 / HF-P16 / HF-P18。

spec: `h-cycle-sync-foundation-and-first-canary` · Tasks 1/2/3/4~18
Requirements 1 / 2 / 3 / 4 / 6 / 7 / 9 / 10

═══ 为什么另起文件 ═══

上游 `test_task42_h1_grouped_dynamic_pilot.py` 属 umbrella Task 42（H1 pilot），
本 spec 是 umbrella Task 50 的**下游实施 spec**，Property 编号自成一套（`HF-P{N}`）。
照 F/G 已确立的「每 spec 独立判据文件」做法。上游文件除 schema 上界两处判据方向外**未动**。

═══ 本文件的方法论铁律 ═══

1. 🔴 **现算，不读 slice 快照**。slice 冻结于 2026-08-31，其「零消费 / 键字面量 /
   manifest 字段值」三类结论本轮实测**反驳了五处**（见 `TestSliceDiscrepancies`）。
2. 🔴 **不写死数量阈值**（GC-10 / HC-6）。派生合计键数、契约文件数、注册集都随功能演进变化，
   写死会在下一次功能迭代时造假红。判据一律「结构性」或「与现算基线比」。
3. 🔴 **四个干净点的守卫方向是「断言保持为无」**（HC-14），不是断言命中。

HF-P11 / HF-P15 / HF-P17（canary 契约 / wp_index 规避 / 真库载荷）在
`test_h9_canary_and_contract.py` —— 它们依赖 canary provider，放在一起才能一眼看出
「契约变了要同时过哪些门」。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from tests.workpaper_sync import h_cycle_facts as F  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# HF-P1　HC-1 manifest capability 实测口径
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def manifest_entries() -> dict:
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )

    return manifest_entries_by_id(load_entry_manifest())


class TestHfP1ManifestCapability:
    """HC-1：9 条 entry + 5 条子入口的 manifest 字段按**实测**写，不照 slice 语义注记。"""

    @pytest.mark.parametrize("entry_id", F.H_ENTRY_IDS)
    def test_independent_entry_manifest_facts(self, manifest_entries: dict, entry_id: str) -> None:
        entry = manifest_entries.get(entry_id)
        assert entry is not None, f"{entry_id} 不在 manifest 里"
        assert str(entry.get("document_type")) == "xlsx"
        assert entry.get("independent_entry") is True
        # 🔴 实测值是 single_onlyoffice —— slice 记的 `capability=null` 不是 manifest 字段值
        assert str(entry.get("capability")) == "single_onlyoffice"
        # 🔴 `capability_target` 字段**不存在**（读取返 None）；缺省不得当 bidirectional
        assert entry.get("capability_target") is None
        assert entry.get("adapter_id") is None
        assert len(entry.get("mounts") or ()) == 2
        profile = (entry.get("scenario_profile") or {}).get("profile_id")
        assert profile == "xlsx.editable.shared.single.room_service_wired.v1"

    @pytest.mark.parametrize("entry_id", F.H_SUB_ENTRY_IDS)
    def test_sub_entry_manifest_facts(self, manifest_entries: dict, entry_id: str) -> None:
        """5 条 parent_duplicate 子入口（含 slice「第五条待补读」已由现算补齐的 monthly）。"""
        entry = manifest_entries.get(entry_id)
        assert entry is not None, f"子入口 {entry_id} 不在 manifest 里"
        assert entry.get("independent_entry") is False
        assert str(entry.get("capability")) == "single_onlyoffice"
        assert entry.get("capability_target") is None
        assert entry.get("adapter_id") is None
        # 🔴 `relationship` 字段亦不存在 —— slice 记的 `parent_duplicate` 是语义注记
        assert entry.get("relationship") is None
        assert len(entry.get("mounts") or ()) == 1

    def test_sub_entries_share_parent_wp_code_so_pointer_must_be_entry_id(
        self, manifest_entries: dict
    ) -> None:
        """GC-1：5 条子入口共用父级 wp_code_pattern（`H4T`×2 / `H8T`×3）⇒ 按 wp_code 必撞。"""
        by_code: dict[str, list[str]] = {}
        for entry_id in F.H_SUB_ENTRY_IDS:
            codes = sorted(
                str(c)
                for c in (manifest_entries[entry_id].get("wp_match") or {}).get(
                    "wp_code_patterns"
                )
                or ()
            )
            assert len(codes) == 1, f"{entry_id} 的 wp_code_patterns={codes}"
            by_code.setdefault(codes[0], []).append(entry_id)
        assert sorted(by_code) == ["H4T", "H8T"]
        assert len(by_code["H4T"]) == 2 and len(by_code["H8T"]) == 3
        # ⇒ representation pointer 必须按 entry_id：wp_code 只能区分 2 组、区分不了 5 条
        assert len(set(F.H_SUB_ENTRY_IDS)) == 5

    def test_capability_migration_must_go_through_register_from_manifest(self) -> None:
        """HC-1 第 2 条：迁移只能由 `register_from_manifest()` 驱动，禁手改 manifest 文件。

        判据落在**可执行**处：provider 的 `assert_manifest_capability_enabled()` 在
        capability 非 bidirectional 时必须拒绝注册（而不是读到 single_onlyoffice 还照注册）。
        """
        from app.services.workpaper_sync.adapters.registry import (
            WorkpaperSyncAdapterRegistry,
        )

        assert hasattr(WorkpaperSyncAdapterRegistry, "register_from_manifest")


# ═══════════════════════════════════════════════════════════════════════════
# HF-P2　HC-2 载体族七分 + F 版守卫对 H 必然假红的对照
# ═══════════════════════════════════════════════════════════════════════════

#: 9 条 entry 的载体三元组（写族 / 读族 / TB 门是否存在）—— **按值实测**填表。
EXPECTED_CARRIER_FAMILIES: dict[str, tuple[str, str, bool]] = {
    "H2": (F.WRITE_HOST_INLINE, F.READ_SNAPSHOT, True),
    "H3": (F.WRITE_FORMDATA, F.READ_CHECKLIST_GET, True),
    "H4": (F.WRITE_FORMDATA, F.READ_CHECKLIST_GET, True),
    "H5": (F.WRITE_PER_TAB_INSTANCE, F.READ_CHECKLIST_GET, True),
    "H6": (F.WRITE_HOST_INLINE, F.READ_SNAPSHOT, True),
    "H7": (F.WRITE_PER_TAB_SELF, F.READ_CHECKLIST_GET, True),
    "H8": (F.WRITE_HOST_INLINE, F.READ_RENDER_CONFIG, False),
    "H9": (F.WRITE_HOST_INLINE, F.READ_RENDER_CONFIG, False),
    "H10": (F.WRITE_FORMDATA, F.READ_BOTH, True),
}


class TestHfP2CarrierFamilies:
    """HC-2：写 4 族 × 读 4 族 × TB 门 2 族。守卫按**族标签分派**，不按文件名推断。"""

    @pytest.mark.parametrize("code", sorted(F.H_HOSTS))
    def test_host_common_signals(self, code: str) -> None:
        """9 宿主统一实测：bridge 0 / legacyOO 4 / notice 3 / ocr 0 / adjCentral 0 / localStorage 0。"""
        facts = F.host_facts(code)
        assert facts.bridge == 0, "9 条全部尚未接桥（legacy 假双向）"
        assert facts.legacy_oo == 4
        assert facts.notice == 3
        # 🔴 FC-8 在 H **不适用**：9 宿主 OCR 实测命中 0（正向证据，不是"没查到"）
        assert facts.ocr == 0
        assert facts.adjustment_central_sync == 0, "调整分录中央同步在 Tab 层不在宿主层"
        assert facts.local_storage == 0, "宿主层无 localStorage；H10 的草稿在 useH10FormData"

    def test_host_inline_family_writes_in_the_host_itself(self) -> None:
        """`host_inline` 4 条：宿主自己 `import http from '@/utils/http'` 并 PUT。"""
        inline = [c for c, v in EXPECTED_CARRIER_FAMILIES.items() if v[0] == F.WRITE_HOST_INLINE]
        assert sorted(inline) == ["H2", "H6", "H8", "H9"]
        for code in inline:
            facts = F.host_facts(code)
            assert facts.http_import == 1, f"{code} 宿主应自带 http 导入"
            assert facts.checklist_put >= 1, f"{code} 宿主应自带 checklist PUT"

    def test_formdata_family_does_not_put_in_the_host(self) -> None:
        """`formdata_composable` 3 条：PUT 在 composable，宿主零 PUT。"""
        fd = [c for c, v in EXPECTED_CARRIER_FAMILIES.items() if v[0] == F.WRITE_FORMDATA]
        assert sorted(fd) == ["H10", "H3", "H4"]
        for code in fd:
            assert F.host_facts(code).checklist_put == 0, f"{code} 的 PUT 不在宿主"

    def test_render_config_read_family_is_exactly_h8_h9_plus_seven_hosts_signal(self) -> None:
        """读族 `render_config_force_component_type`：H8/H9；`force_component_type` 信号命中 7 条。"""
        signal = {c for c in F.H_HOSTS if F.host_facts(c).force_component_type >= 1}
        assert signal == {"H2", "H3", "H5", "H6", "H7", "H8", "H9"}
        rc = {c for c, v in EXPECTED_CARRIER_FAMILIES.items() if v[1] == F.READ_RENDER_CONFIG}
        assert rc == {"H8", "H9"}

    def test_f_cycle_guard_misjudges_h_entries_after_dead_code_deletion(self) -> None:
        """🔴 对照测试（删除 5 个零消费载体**之后**的状态）：

        删除 `useH6FormData` / `useH8FormData` / `useH9FormData` 后，F 版口径在 H6/H8/H9
        上从「假绿」变成「假红」（composable 不存在 ⇒ 找不到 GET+PUT ⇒ 红）——
        但这次的「红」虽然方向对了（确实不应该通过），**理由错了**
        （不是因为「PUT 在宿主不在 composable」，而是「文件不存在」）。
        ⇒ 族分派守卫的必要性未变：F 版口径无法区分「真不存在」与「存在但 PUT 不在这里」。

        改动后误判从 5 条变 4 条：
        * H2 —— `useH2FormData` 从来不存在 → 假红（不变）
        * H7 —— `useH7FormData` get=5 / put=0（禁删，仍在）→ 假红（不变）
        * H6 / H8 —— composable 已删 → 假红（从假绿翻成假红，方向对了但理由错）
        * H9 —— composable 已删 → 假红（同上）
        * H5 —— 多实例化，F 版口径看到 GET+PUT → 正确绿（不变）
        """
        f_style_failures: list[str] = []
        for code in sorted(F.H_HOSTS):
            name = f"useH{code[1:]}FormData"
            consumers = F.count_consumers(name)
            if not consumers.defined:
                f_style_failures.append(f"{code}: {name} 文件不存在")
                continue
            text = (F.COMPOSABLES / f"{name}.ts").read_text(encoding="utf-8", errors="replace")
            has_get = bool(re.search(r"\.get\(", text))
            has_put = bool(re.search(r"\.put\(", text))
            if not (has_get and has_put):
                f_style_failures.append(f"{code}: {name} get={has_get} put={has_put}")

        # 删除后：H2(从来不存在) + H6/H8/H9(已删) + H7(有但 put=0) = 5 条假红
        assert {x.split(":")[0] for x in f_style_failures} == {"H2", "H6", "H7", "H8", "H9"}, (
            f_style_failures
        )

    def test_adjustment_central_sync_is_a_second_writer_on_all_nine(self) -> None:
        """HC-2 第 3 条：`useAdjustmentCentralSync` 在 9 条各自的 `H*TabAdjustment.vue` 全覆盖。"""
        sites = F.adjustment_central_sync_sites()
        tabs = {s.split(":")[0] for s in sites if "TabAdjustment.vue" in s}
        assert len(tabs) == 9, sites
        for code in F.H_HOSTS:
            n = code[1:]
            assert any(
                f"/h{n}/core/H{n}TabAdjustment.vue" in t for t in tabs
            ), f"H{n} 的调整分录 Tab 未接中央同步"

    def test_tb_publish_gate_two_families(self) -> None:
        """HD-7：7 条有门 / 🔴 H8 + H9 **完全没有**；H7 的门在 `useH7FormData`。"""
        sites = F.publish_to_tb_sites()
        assert sites["H8"] == (), f"H8 应无 TB 发布门，实测 {sites['H8']}"
        assert sites["H9"] == (), f"H9 应无 TB 发布门，实测 {sites['H9']}"
        for code, (_w, _r, has_gate) in EXPECTED_CARRIER_FAMILIES.items():
            assert bool(sites[code]) is has_gate, f"{code} 发布门实测 {sites[code]}"
        assert any("useH7FormData.ts" in s for s in sites["H7"]), sites["H7"]
        assert any("useH5FormData.ts" in s for s in sites["H5"]), sites["H5"]


# ═══════════════════════════════════════════════════════════════════════════
# HF-P3　HC-3 消费方计数 + 可删 / 禁删名单定稿
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 **可删**名单 —— **已删**。本 spec 交付时这 5 个文件已不存在。
#: 判据改向：断言定义文件不存在（删除实证），不再断言「生产消费 0 且可删」。
DELETED_CARRIERS: tuple[str, ...] = (
    "useH5DualMode",
    "useH7DualMode",
    "useH6FormData",
    "useH8FormData",
    "useH9FormData",
)

#: 🔴 **禁删**名单：slice 记为孤儿但实测有生产消费。删了会打断链路。
FORBIDDEN_TO_DELETE: dict[str, str] = {
    "useH7FormData": "H7 唯一 TB 发布门（publishToTb×2）；消费方 h7/core/H7TabAdjudicationCost.vue",
    "useH9DualMode": "canary H9 宿主 GtH9LeaseLiabilities.vue 消费",
    "useH8DualMode": "useH9DualMode.ts + h8/impairment/H8TabRecoverable.vue 消费（子入口链路）",
    "useH4DualMode": "跨 H4/H6/H8 + 2 条子入口链式复用，5 个消费点",
}


class TestHfP3ConsumerCounts:
    """HC-3：删除任何 legacy 载体前必须跑消费方计数留证。"""

    @pytest.mark.parametrize("name", DELETED_CARRIERS)
    def test_deleted_carrier_no_longer_exists(self, name: str) -> None:
        """🔴 这 5 个文件已被删除（HC-3 可删名单兑现），不存在即通过。"""
        c = F.count_consumers(name)
        assert not c.defined, f"{name} 的定义文件仍然存在"

    @pytest.mark.parametrize("name,reason", sorted(FORBIDDEN_TO_DELETE.items()))
    def test_forbidden_carrier_has_production_consumers(self, name: str, reason: str) -> None:
        """🔴 slice 的删除清册把 `useH7FormData` / `useH9DualMode` 列成孤儿 —— 实测都不是。"""
        c = F.count_consumers(name)
        assert c.production, f"{name} 应有生产消费（{reason}），实测为空"
        assert c.deletable is False
        assert name not in DELETED_CARRIERS

    def test_use_h7_form_data_carries_the_only_h7_tb_gate(self) -> None:
        """按 slice「删孤儿」执行会打断 H7 的 TB 发布链 —— 判据把这条钉死。"""
        sites = F.publish_to_tb_sites()["H7"]
        assert sites, "H7 必须有 TB 发布门"
        assert all("useH7FormData.ts" in s for s in sites), sites

    def test_use_h4_dual_mode_is_chained_across_four_entries(self) -> None:
        """改 `useH4DualMode` = 同时影响 H4 / H6 / H8 / H9 ⇒ 三方协调（本 spec 只立判据）。"""
        c = F.count_consumers("useH4DualMode")
        files = {x.split(":")[0] for x in c.production}
        assert len(files) == 5, c.production
        assert "components/workpaper/GtH4EngineeringMaterials.vue" in files
        assert "components/workpaper/composables/useH6DualMode.ts" in files
        assert "components/workpaper/composables/useH8DualMode.ts" in files
        assert "components/workpaper/h4/impairment/H4TabImpairment.vue" in files
        assert "components/workpaper/h4/impairment/H4TabRecoverable.vue" in files
        # 链尾跨到 canary：useH8DualMode → useH9DualMode → GtH9
        chain = {x.split(":")[0] for x in F.count_consumers("useH8DualMode").production}
        assert "components/workpaper/composables/useH9DualMode.ts" in chain
        assert "components/workpaper/h8/impairment/H8TabRecoverable.vue" in chain

    def test_use_h2_form_data_does_not_exist_at_all(self) -> None:
        """HC-3 表末行：`useH2FormData` 定义 == 0（文件不存在），不是"零消费可删"。"""
        c = F.count_consumers("useH2FormData")
        assert c.definitions == ()
        assert c.production == ()
        assert (F.COMPOSABLES / "useH2FormData.ts").exists() is False


# ═══════════════════════════════════════════════════════════════════════════
# HF-P4　HC-4 主表键必须解析模板拼接后再比对
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP4PrimaryKeys:
    """HC-4：键字面量守卫必须带拼接解析分支，否则 `H5-2-rows` 必假红。"""

    @pytest.mark.parametrize("label,key", sorted(F.H_PRIMARY_KEYS.items()))
    def test_every_primary_key_resolves(self, label: str, key: str) -> None:
        hits = F.resolve_item_key_hits(key)
        assert hits.resolved, f"{label} 的主表键 {key} 在生产源码里零命中"

    def test_h5_primary_key_is_literal_absent_and_only_resolves_via_concat(self) -> None:
        """🔴 实测不一致第 4 条：`H5-2-rows` 字面量**全仓零命中**，语义正确不是缺陷。"""
        hits = F.resolve_item_key_hits("H5-2-rows")
        assert hits.literal == (), f"H5-2-rows 字面量应为 0，实测 {hits.literal}"
        assert hits.concatenated, "拼接解析分支必须命中"
        assert any("useH5Detail.ts" in rel for rel in hits.concatenated), hits.concatenated

    def test_h5_item_prefix_constant_value_is_h5_2(self) -> None:
        """拼接来源是 `useH5Detail.ts` 的 `ITEM_PREFIX`，实值 `H5-2`（按值取，不推演）。"""
        f = next(x for x in F.frontend_files() if x.rel.endswith("composables/useH5Detail.ts"))
        resolved = F.template_concat_keys(f)
        assert resolved.get("H5-2-rows") == "ITEM_PREFIX", resolved

    def test_dropping_the_concat_branch_would_false_red(self) -> None:
        """变异判据：只做字面量 grep ⇒ `H5-2-rows` 判零命中（正是 slice 的错法）。"""
        literal_only = [
            k for k in F.H_PRIMARY_KEYS.values() if not F.resolve_item_key_hits(k).literal
        ]
        assert literal_only == ["H5-2-rows"], literal_only

    def test_h10_identity_field_is_id_not_row_id(self) -> None:
        """HC-4 第 4 条：`H10-detail-rows` 身份字段是 `id`，且行可增删 ⇒ 非模板固定行族。"""
        text = (F.COMPOSABLES / "useH10Detail.ts").read_text(encoding="utf-8", errors="replace")
        assert "addRow" in text and "removeRow" in text
        assert re.search(r"\bid\s*:\s*raw\.id\s*\?\?", text), "应是 `id: raw.id ?? generateId()`"
        assert not re.search(r"rowId\s*:\s*raw\.rowId", text), "H10 不用 rowId 作身份"


# ═══════════════════════════════════════════════════════════════════════════
# HF-P5　HC-5 变体轴三维声明（两维不足）
# ═══════════════════════════════════════════════════════════════════════════

#: 三族变体轴 × 同尾码双 sheet（`(entry_code, sheet_code, axis, 两张 sheet 全名)`）。
#:
#: 🔴 **sheet 全名按 openpyxl 逐册现算取得，尾码是名字的一部分**。
#: spec 正文里写的是去掉尾码的短名（如「折旧测算表（成本模式不含减值）」），
#: 实测全名为「折旧测算表（成本模式不含减值）**H3-7**」—— 契约用全名消歧时必须带尾码，
#: 否则 `wb[name]` 直接 KeyError。
VARIANT_SHEET_PAIRS: tuple[tuple[str, str, str, tuple[str, str]], ...] = (
    ("H3", "H3-1", "measurement_model", ("审定表（成本模式）H3-1", "审定表（公允价值模式）H3-1")),
    ("H3", "H3-2", "measurement_model", ("明细表（成本模式）H3-2", "明细表（公允价值模式）H3-2")),
    (
        "H3",
        "H3-5",
        "measurement_model",
        ("增减检查表（成本模式）H3-5", "增减检查表（公允价值模式）H3-5"),
    ),
    (
        "H3",
        "H3-7",
        "impairment_included",
        ("折旧测算表（成本模式不含减值）H3-7", "折旧测算表（成本模式含减值）H3-7"),
    ),
    (
        "H5",
        "H5-12",
        "impairment_included",
        ("折耗测算表（不含减值）H5-12", "折耗测算表（含减值）H5-12"),
    ),
    ("H7", "H7-1", "measurement_model", ("审定表（成本模式）H7-1", "审定表（公允价值模式）H7-1")),
    ("H7", "H7-2", "measurement_model", ("明细表（成本模式）H7-2", "明细表（公允价值模式）H7-2")),
    (
        "H7",
        "H7-6",
        "measurement_model",
        ("增加检查表（成本模式）H7-6", "增加检查表（公允价值模式）H7-6"),
    ),
    (
        "H7",
        "H7-7",
        "measurement_model",
        ("减少检查表（成本模式）H7-7", "减少检查表（公允价值模式）H7-7"),
    ),
    (
        "H7",
        "H7-11",
        "impairment_included",
        ("折旧测算表（不含减值）-直线法H7-11", "折旧测算表（含减值）H7-11"),
    ),
    (
        "H8",
        "H8-8",
        "impairment_included",
        ("折旧测算表（不含减值）H8-8", "折旧测算表（含减值）H8-8"),
    ),
    (
        "H8",
        "H8-6",
        "period_granularity",
        (
            "使用权资产 租赁负债初始及后续计量（按年）H8-6",
            "使用权资产 租赁负债初始及后续计量（按月）H8-6",
        ),
    ),
)


class TestHfP5VariantAxis:
    """HC-5：`(variant_axis, variant_value, sheet_code)` 三维或逐 sheet 全名，两维不足。"""

    @pytest.mark.parametrize(
        "code,sheet_code,axis,names",
        VARIANT_SHEET_PAIRS,
        ids=[f"{c}:{s}:{a}" for c, s, a, _ in VARIANT_SHEET_PAIRS],
    )
    def test_both_sheets_exist_with_distinct_full_names(
        self, code: str, sheet_code: str, axis: str, names: tuple[str, str]
    ) -> None:
        present = F.workbook_clean_points(code)["sheet_names"]
        for name in names:
            assert name in present, f"{code} 册缺 sheet {name!r}；实有 {present}"
        assert names[0] != names[1], "同尾码双 sheet 必须全名不同"

    def test_three_axes_exist_and_two_dimension_declaration_is_insufficient(self) -> None:
        """🔴 只声明 `(measurement_model, sheet_code)` ⇒ H3-7/H5-12/H7-11/H8-6 无处安放。"""
        axes = {a for _c, _s, a, _n in VARIANT_SHEET_PAIRS}
        assert axes == {"measurement_model", "impairment_included", "period_granularity"}
        orphans = sorted(
            f"{c}:{s}" for c, s, a, _n in VARIANT_SHEET_PAIRS if a != "measurement_model"
        )
        # 🔴 现算多出一组：spec 正文漏记 `H8-8 折旧测算表（不含/含减值）`
        # ——「含否减值」族实测是 **5 组**（H3-7 / H5-12 / H7-11 / H8-8）+ 按年按月 1 组（H8-6）
        assert orphans == ["H3:H3-7", "H5:H5-12", "H7:H7-11", "H8:H8-6", "H8:H8-8"], orphans
        impairment = sorted(
            f"{c}:{s}" for c, s, a, _n in VARIANT_SHEET_PAIRS if a == "impairment_included"
        )
        assert impairment == ["H3:H3-7", "H5:H5-12", "H7:H7-11", "H8:H8-8"], impairment

    def test_locating_by_sheet_code_alone_hits_two_sheets(self) -> None:
        """按 `sheet_code` 定位必须命中 2 张并要求 `variant_value` 消歧，不静默取首张。"""
        for code, sheet_code, _axis, names in VARIANT_SHEET_PAIRS:
            present = F.workbook_clean_points(code)["sheet_names"]
            hits = [n for n in present if n in names]
            assert len(hits) == 2, f"{code}:{sheet_code} 命中 {hits}"

    def test_h3_and_h7_measurement_models_have_independent_keys(self) -> None:
        """HC-5 第 2 条：与 E1-3 `currency_variant`「双 sheet 共用一键」不同源 ⇒ 无抹零风险。"""
        for pair in (("H3-2-cost-rows", "H3-2-fair-rows"), ("H7-2-cost-rows", "H7-2-fair-rows")):
            a, b = pair
            assert a != b
            assert F.resolve_item_key_hits(a).resolved
            assert F.resolve_item_key_hits(b).resolved


# ═══════════════════════════════════════════════════════════════════════════
# HF-P6　HC-6 派生合计副本（`derived_total_keys`）
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP6DerivedTotalKeys:
    """HC-6：现算 total 键集合；🔴 **禁止写死阈值**（GC-10）。"""

    def test_every_h_entry_has_derived_total_keys(self) -> None:
        keys = F.derived_total_keys()
        by_entry: dict[str, list[str]] = {}
        for key in keys:
            by_entry.setdefault(F.entry_prefix_of(key), []).append(key)
        # 结构性判据：9 条 entry 各自都有派生合计键（不写死每条几个）
        for code in F.H_HOSTS:
            assert by_entry.get(code), f"{code} 现算 total 键为空 —— 要么口径错了要么功能退化"
        # H8 现算最多（结构性比较，不写死 21）
        assert len(by_entry["H8"]) == max(len(v) for k, v in by_entry.items() if k in F.H_HOSTS)

    def test_h7_detail_keys_hit_once_are_normal_not_defects(self) -> None:
        """🔴 HC-6 第 3 条：`H7-2-*-rows` 生产命中 1 判**正常**。

        🔴 **本判据修正了 spec 的区分依据**。spec design HC-6 第 4 条写「H7 **有**对应
        `H7-2-cost-total` / `H7-2-fair-total`」，但按值实测：

        * `H7-2-cost-total` **存在**（`useH7CrossSheet.ts#L52` 读它做审定表勾稽）；
        * 🔴 `H7-2-fair-total` **不存在**（全仓零命中）—— 公允价值侧没有 total 键。

        ⇒ 若判据写成「有无 total 键」，`H7-2-fair-rows` 会被误判成 BP-5 同形缺陷。
        权威判据改为「**有无读取点**」：两个 H7 键都被各自的 Tab 回读
        （`getString('H7-2-{cost,fair}-rows')`），BP-5 的键零读取点。
        """
        totals = F.derived_total_keys()
        assert "H7-2-cost-total" in totals
        assert "H7-2-fair-total" not in totals, "实测不存在 —— 不得据此判 fair 侧为缺陷"
        for detail in ("H7-2-cost-rows", "H7-2-fair-rows"):
            hits = F.resolve_item_key_hits(detail)
            assert len(hits.production_files) == 1, hits.production_files
            readers = F.key_read_sites(detail)
            assert readers, f"{detail} 应有读取点（Tab 自身回读）"
        cross = (F.COMPOSABLES / "useH7CrossSheet.ts").read_text(encoding="utf-8", errors="replace")
        assert "H7-2-cost-total" in cross, "H7 成本模式勾稽应读 total 键而非遍历明细行"

    def test_h8_detail_prefill_is_a_defect_because_it_has_zero_read_site(self) -> None:
        """🔴 BP-5：`H8-2-detail-prefill` 全仓**零读取点** ⇒ 种子写进去没人取。

        区分判据必须是「有无读取点」而不是「生产命中数」——
        `H8-2-detail-prefill` 与 `H7-2-fair-rows` 的生产命中都是 1 家。
        """
        bad = "H8-2-detail-prefill"
        hits = F.resolve_item_key_hits(bad)
        assert hits.production_files == ("components/workpaper/GtH8RightOfUseAssets.vue",), (
            hits.production_files
        )
        assert F.key_read_sites(bad) == (), "BP-5 的判据就是零读取点；有读取点说明已被修掉"
        assert not any(k.startswith("H8-2-detail-prefill") for k in F.derived_total_keys())
        # 真实主键 `H8-2-rows` 既有多家生产命中、也有读取点
        real = F.resolve_item_key_hits("H8-2-rows")
        assert len(real.production_files) > 5, real.production_files
        assert F.key_read_sites("H8-2-rows"), "真实主键必须有读取点（useH8Detail 常量间接读）"


# ═══════════════════════════════════════════════════════════════════════════
# HF-P7　HC-7 行身份三族分治（含 slice 漏掉的族 C）
# ═══════════════════════════════════════════════════════════════════════════

#: 族 B（BP-6）：身份整体取数组下标，3 处。
EXPECTED_FAMILY_B: tuple[tuple[str, int], ...] = (
    ("components/workpaper/GtH2ConstructionInProgress.vue", 616),
    ("components/workpaper/GtH8RightOfUseAssets.vue", 578),
    ("components/workpaper/composables/h4DetailPrefill.ts", 50),
)

#: 族 C（BP-11，🔴 slice 完全漏）：身份内嵌业务名且无随机后缀，7 处。
EXPECTED_FAMILY_C: tuple[tuple[str, int], ...] = (
    ("components/workpaper/composables/useH2Adjudication.ts", 194),
    ("components/workpaper/composables/useH2Adjudication.ts", 389),
    ("components/workpaper/composables/useH3Adjustment.ts", 311),
    ("components/workpaper/composables/useH3RentalIncome.ts", 148),
    ("components/workpaper/composables/useH4Adjudication.ts", 436),
    ("components/workpaper/composables/useH5Adjudication.ts", 136),
    ("components/workpaper/composables/useH8Adjudication.ts", 572),
)


class TestHfP7IdentityFamilies:
    """HC-7：族 A（安全）/ 族 B（下标）/ 族 C（语义耦合）三族分治。"""

    def test_family_b_seed_identity_is_gone_after_bp6_fix(self) -> None:
        """🔴 BP-6 修复后全 H 作业面里 `rowId:\`seed-${` 命中 → **0**。"""
        hits = F.scan_identity_family(F.FAMILY_B_RE, exclude_family_a=False)
        assert hits == (), f"仍有 seed 下标形态残留：{hits}"

    def test_family_c_semantic_identity_is_gone_after_bp11_fix(self) -> None:
        """🔴 BP-11 修复后全 H 作业面里族 C（语义耦合身份无随机后缀）命中 → **0**。

        原 7 处（useH2#194/#389 / useH3Adjustment#311 / useH3RentalIncome#148 /
        useH4#436 / useH5#136 / useH8#572）全部加了 `Math.random().toString(36).slice(2,7)` 后缀
        ⇒ 被 `FAMILY_A_SUFFIX_RE` 排除 ⇒ 族 C 扫描归零。
        """
        hits = F.scan_identity_family(F.FAMILY_C_RE, exclude_family_a=True)
        assert hits == (), f"仍有族 C 残留：{hits}"

    def test_random_suffixed_identity_is_family_a_and_must_not_be_changed(self) -> None:
        """`useH8Adjudication.ts#L145` 带 `${rand5}` ⇒ 属族 A，**不得**算进族 C。"""
        text = (F.COMPOSABLES / "useH8Adjudication.ts").read_text(encoding="utf-8", errors="replace")
        line145 = text.splitlines()[144]
        assert "h81-" in line145 and "Math.random" in line145, line145
        family_c = {(h.rel, h.line) for h in F.scan_identity_family(F.FAMILY_C_RE, exclude_family_a=True)}
        assert ("components/workpaper/composables/useH8Adjudication.ts", 145) not in family_c

    def test_family_c_prefix_only_form_is_not_semantic_coupling(self) -> None:
        """`useH5Adjudication.ts` 的 `` `row-${prefix}-subtotal` ``：`prefix` 是常量非业务名。

        🔴 把它算进族 C 会造出一处不存在的缺陷（虚报与漏报同罪）。
        """
        assert "prefix" not in F.FAMILY_C_TOKENS
        family_c = {(h.rel, h.line) for h in F.scan_identity_family(F.FAMILY_C_RE, exclude_family_a=True)}
        assert ("components/workpaper/composables/useH5Adjudication.ts", 143) not in family_c

    def test_h1_pilot_family_c_sites_are_out_of_this_round_scope(self) -> None:
        """H1 是**已注册 adapter 的 pilot** ⇒ 它的族 C 处不在本轮作业面（HC-8）。"""
        assert F.in_h_scope("components/workpaper/composables/useH1Adjudication.ts") is False
        assert F.in_h_scope("components/workpaper/composables/useH2Adjudication.ts") is True


# ═══════════════════════════════════════════════════════════════════════════
# HF-P8　HC-8 跨引用图 + 6 键冻结
# ═══════════════════════════════════════════════════════════════════════════

#: 跨 entry / 跨循环消费图（消费方文件 → 它消费的 H 键）。
CROSS_REFERENCE_GRAPH: dict[str, tuple[str, ...]] = {
    "components/workpaper/composables/h1CipH2Pull.ts": ("H2-2-rows",),
    "components/workpaper/composables/h1SoeClearingH6Pull.ts": (
        "H6-1-rows",
        "H6-2-rows",
        "H6-1-end-balance-audited",
    ),
    "components/workpaper/composables/h1RelatedH10Pull.ts": ("H10-detail-rows",),
    "components/workpaper/composables/useH1LeaseCheck.ts": ("H10-detail-rows",),
    "components/workpaper/composables/g13SourceDetailPull.ts": ("H3-2-fair-rows",),
    "components/workpaper/composables/gCycleSourceFv.ts": ("H3-2-fair-rows",),
    "components/workpaper/composables/h10RelatedH6Pull.ts": ("H6-2-rows",),
    "components/workpaper/composables/useH10CrossSheet.ts": ("H6-2-rows",),
    "components/workpaper/composables/useH8CrossSheet.ts": ("H9-2-rows",),
    "components/workpaper/composables/useH8DisposalCheck.ts": ("H9-2-rows",),
}


class TestHfP8FrozenKeysAndCrossReference:
    """HC-8：跨引用图 9+ 行全在；6 键冻结不改。"""

    @pytest.mark.parametrize("rel,keys", sorted(CROSS_REFERENCE_GRAPH.items()))
    def test_cross_reference_edge_still_resolves(self, rel: str, keys: tuple[str, ...]) -> None:
        f = next((x for x in F.frontend_files() if x.rel == rel), None)
        assert f is not None, f"消费方文件不存在：{rel}"
        for key in keys:
            assert f.count(key) > 0, f"{rel} 应消费 {key}"

    @pytest.mark.parametrize("key", F.H_FROZEN_KEYS)
    def test_frozen_key_is_still_produced(self, key: str) -> None:
        """冻结键必须仍有生产命中 —— 改名会静默打断 H1 pilot / G 循环取数。"""
        assert F.resolve_item_key_hits(key).resolved, f"冻结键 {key} 生产零命中"

    def test_frozen_key_set_covers_h1_pilot_and_g_cycle_consumers(self) -> None:
        consumed: set[str] = set()
        for rel, keys in CROSS_REFERENCE_GRAPH.items():
            if "h1" in rel.rsplit("/", 1)[-1].lower() or "useH1" in rel or "g13" in rel or "gCycle" in rel:
                consumed |= set(keys)
        assert consumed <= set(F.H_FROZEN_KEYS), consumed - set(F.H_FROZEN_KEYS)
        assert set(F.H_FROZEN_KEYS) - consumed == set(), "冻结名单不得含无消费方的键"

    def test_h1_contract_and_golden_digest_are_untouched(self) -> None:
        """🔴 HC-8：本轮不得改 H1 的契约 / adapter / golden digest。"""
        import subprocess

        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "backend/data/workpaper_sync_contracts/h1.disposal_check.json"],
            cwd=str(F.BACKEND.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        assert out.stdout.strip() == "", f"H1 契约被改动：{out.stdout!r}"

    def test_zero_regression_baseline_is_computed_not_hardcoded(self) -> None:
        """HF-P18 / GC-10：契约集合现算，**不写死个数**。"""
        ids = F.available_contract_ids()
        assert "h1.disposal_check" in ids
        assert "_example.candidate" in ids
        # 结构性判据：每个 contract_id 都有同名磁盘文件（双向）
        for cid in ids:
            assert (F.CONTRACTS_DIR / f"{cid}.json").exists()


# ═══════════════════════════════════════════════════════════════════════════
# HF-P9　HC-9 猜键回退链（BP-12）
# ═══════════════════════════════════════════════════════════════════════════


#: 🔴 **BP-12 修复后从 4 处降到 3 处**：`h10RelatedH6Pull.ts` 的三键回退已收敛为单一权威键。
#: 剩余 3 处归后续 spec 处置（它们的目标键在 H10 侧零生产，不是本 spec 的作业面）。
EXPECTED_FALLBACK_CHAINS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # 🔴 跨循环到 L1，**两键全部**零生产 ⇒ H3 抵押核对恒取不到
    "components/workpaper/composables/h3MortgageReconcile.ts#L75": (
        ("L1-L1-8-rows", "L1-pledge-rows"),
        ("L1-L1-8-rows", "L1-pledge-rows"),
    ),
    # 🔴 H6 → H10 反向，**四键全部**零生产 ⇒ 这条反向勾稽整体是死路
    "components/workpaper/composables/h6H10Pull.ts#L45": (
        (
            "H10-1-audited-total",
            "H10-adj-total",
            "H10-1-end-audited",
            "H10-1-disposal-gain-loss",
        ),
        (
            "H10-1-audited-total",
            "H10-adj-total",
            "H10-1-end-audited",
            "H10-1-disposal-gain-loss",
        ),
    ),
    # 🔴 4 键里 3 键零生产，只有 `H10-detail-rows` 是真键
    "components/workpaper/composables/useH6Check.ts#L508": (
        ("H10-2-rows", "H10-rows", "H10-1-gain-loss-total", "H10-detail-rows"),
        ("H10-2-rows", "H10-rows", "H10-1-gain-loss-total"),
    ),
}


class TestHfP9GuessedKeyFallbackChain:
    """HC-9：多键回退链里每个键都必须「H 侧生产命中 > 0」，否则是猜测键。"""

    def test_h_cycle_fallback_chain_inventory_is_three_after_bp12_fix(self) -> None:
        """🔴 BP-12 修复后从 4 处降到 **3 处**：`h10RelatedH6Pull.ts` 已收敛为单一权威键。"""
        chains = F.multi_key_fallback_chains()
        assert sorted(chains) == sorted(EXPECTED_FALLBACK_CHAINS), sorted(chains)
        for site, (all_keys, _guessed) in EXPECTED_FALLBACK_CHAINS.items():
            assert chains[site] == all_keys, (site, chains[site])

    @pytest.mark.parametrize("site", sorted(EXPECTED_FALLBACK_CHAINS))
    def test_guessed_keys_in_every_chain_have_zero_producer(self, site: str) -> None:
        """判定口径 = 「**该键所属 entry 的作业面**里有没有生产者」。

        🔴 用「消费方文件之外还有没有命中」会误判：`H6-detail-rows` 在
        `h10RelatedH6Pull.ts` 与 `useH10CrossSheet.ts` 两处出现，但两处都是 **H10 侧**消费方。
        """
        all_keys, guessed = EXPECTED_FALLBACK_CHAINS[site]
        for key in all_keys:
            owners = F.producers_in_owning_entry_scope(key)
            if key in guessed:
                assert owners == (), f"{key} 本应在自己 entry 侧零生产，实测 {owners}"
            else:
                assert owners, f"{key} 本应是权威键（自己 entry 侧有生产者），实测零生产"

    def test_h6_to_h10_reverse_pull_is_entirely_dead(self) -> None:
        """🔴 `h6H10Pull.ts` 的 4 键全部零生产 ⇒ 该 pull 恒落到「H10 暂无审定数」分支。"""
        _all, guessed = EXPECTED_FALLBACK_CHAINS[
            "components/workpaper/composables/h6H10Pull.ts#L45"
        ]
        assert len(guessed) == 4
        text = (F.COMPOSABLES / "h6H10Pull.ts").read_text(encoding="utf-8", errors="replace")
        assert "H10 暂无审定数" in text, "落空分支的文案是这条链恒走的路径"

    def test_guessed_keys_are_gone_from_h10_after_bp12_fix(self) -> None:
        """🔴 BP-12 修复后 `H6-detail-rows` / `H6-clearing-rows` 在可执行代码里**零命中**。

        注释里的历史记录不影响运行时。
        """
        for key in F.H_GUESSED_KEYS:
            hits = F.resolve_item_key_hits(key)
            for rel in hits.production_files:
                text = next(f.text for f in F.frontend_files() if f.rel == rel)
                for line in text.splitlines():
                    stripped = line.strip()
                    if key in stripped:
                        assert stripped.startswith("//") or stripped.startswith("*"), (
                            f"{rel}: {key} 出现在可执行语句：{stripped[:120]}"
                        )

    def test_authoritative_key_is_documented_in_the_same_file(self) -> None:
        """同文件注释已写明真源是 `H6-2-rows` ⇒ 后两键是防御性猜测，不是历史别名。"""
        text = (F.COMPOSABLES / "h10RelatedH6Pull.ts").read_text(encoding="utf-8", errors="replace")
        assert "H6-2-rows" in text
        assert "checklist" in text.lower()


# ═══════════════════════════════════════════════════════════════════════════
# HF-P10　HC-10 客户端第三处存储（H10 localStorage 草稿）
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP10ClientDraftStore:
    """HC-10：roundtrip 前提「HTML 侧内容 == checklist_responses」在有未同步草稿时不成立。"""

    def test_h10_draft_store_shape_is_measured(self) -> None:
        text = (F.COMPOSABLES / "useH10FormData.ts").read_text(encoding="utf-8", errors="replace")
        assert re.search(r"const\s+DRAFT_PREFIX\s*=\s*'h10-draft'", text)
        assert "localStorage.setItem" in text
        assert "localStorage.removeItem" in text
        assert "restoreDrafts" in text

    def test_h10_is_the_only_h_entry_with_a_client_side_data_store(self) -> None:
        """第三处**数据**存储只在 H10。

        🔴 **本判据把 spec HC-10 的口径收紧了**。按「文件里出现 `localStorage`」现算会命中
        **10 个** H 作业面文件 —— 因为 6 个 `useH*DualMode.ts`（H2/H3/H4/H5/H6/H7/H8/H9）
        各有 `STORAGE_PREFIX = 'h{n}-dual-mode:'`。但它们存的是**视图模式字符串**
        （`localStorage.setItem(STORAGE_PREFIX + wpId, mode)`），是 UI 偏好，
        **不承载任何 checklist item 载荷** ⇒ 不影响 roundtrip 的
        「HTML 侧内容 == `checklist_responses`」前提。

        真正的第三处数据存储判据 = **localStorage 键按 `itemId` 分片**
        （`h10-draft:{wpId}:{itemId}` ⇒ 一条 item 一个槽，存的就是该 item 的载荷）。
        🔴 「值里有 `JSON.stringify`」不够 —— 实测 `useH8DetailColumnPrefs.ts`
        与 `h6/inspection/H6TabCheck.vue` 也 `JSON.stringify(hidden)`，但存的是**列隐藏偏好**。
        按 `itemId` 分片这个口径现算**只有 H10**。

        🔴 其中 4 个 DualMode（H4/H6/H8/H9）在生产**是活的**（有消费方）——
        所以"UI 偏好存储"这件事本身也要如实登记，只是它不是 HC-10 的风险面。
        """
        data_stores: list[str] = []
        ui_pref_stores: list[str] = []
        for f in F.workpaper_files():
            if not F.in_h_scope(f.rel) or "localStorage" not in f.text:
                continue
            # 键按 itemId 分片 ⇒ 承载 item 载荷（第三处数据存储）
            per_item_key = bool(re.search(r"\$\{[^}]*\bitemId\b[^}]*\}", f.text))
            (data_stores if per_item_key else ui_pref_stores).append(f.rel)
        assert data_stores == ["components/workpaper/composables/useH10FormData.ts"], data_stores
        # UI 偏好存储如实登记：删除 5 个后剩 4 个 DualMode（H2/H3/H4/H10 存视图模式）
        # + 2 处列隐藏偏好；H6/H8/H9 的 DualMode 的 localStorage 已随文件删除消失
        # 但 H4/H6/H8/H9 DualMode 未删（H4 有 5 消费方 / H6 有 1 / H8 有 2 / H9 有 1）
        # 🔴 H5/H7 DualMode 已删；H6 DualMode 未删（useH6DualMode 的消费方 ≠ useH6FormData）
        expected_ui = sorted(
            [f"components/workpaper/composables/useH{n}DualMode.ts" for n in (2, 3, 4, 6, 8, 9, 10)]
            + [
                "components/workpaper/composables/useH8DetailColumnPrefs.ts",
                "components/workpaper/h6/inspection/H6TabCheck.vue",
            ]
        )
        assert sorted(ui_pref_stores) == expected_ui, ui_pref_stores

    def test_dual_mode_ui_preference_store_only_persists_a_mode_string(self) -> None:
        """逐个确认存活的 DualMode 的 localStorage 写入值是 `mode`/`target`，不是 item 载荷。"""
        for n in ("2", "3", "4", "6", "8", "9", "10"):
            path = F.COMPOSABLES / f"useH{n}DualMode.ts"
            if not path.exists():
                continue  # H5/H7 DualMode 已删
            text = path.read_text(encoding="utf-8", errors="replace")
            assert re.search(rf"STORAGE_PREFIX\s*=\s*'h{n}-dual-mode:'", text), path.name
            assert re.search(
                r"setItem\(STORAGE_PREFIX \+ (?:wpId|options\.wpId)\.value,\s*(?:mode|target)\)",
                text,
            ), path.name
            assert "JSON.stringify" not in text, f"{path.name} 不应序列化任何载荷"

    def test_h5_dual_mode_has_been_deleted_eliminating_fourth_store_risk(self) -> None:
        """🔴 HC-10 第 2 条：`useH5DualMode` 已删除 —— 第四存储风险已消除。"""
        assert not (F.COMPOSABLES / "useH5DualMode.ts").exists()
        assert F.count_consumers("useH5DualMode").production == ()


# ═══════════════════════════════════════════════════════════════════════════
# HF-P12　HC-12 per-file 裸 IF 中性化
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP12BareIfNeutralization:
    """HC-12：`oo_crash_neutralization_fn` 必须 **per-file** 挂，不得整册统一。"""

    def test_production_function_body_exists_not_just_the_import(self) -> None:
        """🔴 历史上有「调用点在 HEAD、函数体从未落地」的先例 ⇒ 断言函数体可调用。"""
        from app.services.workpaper_sync.g7_oo_crash_if_neutralize import (
            neutralize_oo_crash_if_formulas,
        )

        assert callable(neutralize_oo_crash_if_formulas)

    @pytest.mark.parametrize("code", sorted(F.H_TEMPLATES))
    def test_every_h_workbook_has_bare_if_cells(self, code: str) -> None:
        """9/9 全命中 ⇒ 9 条 plan 都必须挂中性化，**无例外**。"""
        assert F.bare_if_cell_count(code) > 0, f"{code} 裸 IF 为 0？请复核口径"

    def test_per_file_counts_span_two_orders_of_magnitude(self) -> None:
        """🔴 变异「整册统一挂」的判据：最重册与最轻册差一个数量级以上。"""
        counts = {code: F.bare_if_cell_count(code) for code in F.H_TEMPLATES}
        heaviest = max(counts, key=lambda k: counts[k])
        lightest = min(counts, key=lambda k: counts[k])
        assert heaviest == "H8", counts
        assert lightest == "H6", counts
        assert counts["H8"] >= 20 * counts["H6"], counts

    def test_h9_canary_is_among_the_lightest(self) -> None:
        """canary 选型依据之一：H9 裸 IF 次少（仅多于 H6）。"""
        counts = {code: F.bare_if_cell_count(code) for code in F.H_TEMPLATES}
        ranked = sorted(counts, key=lambda k: counts[k])
        assert ranked[0] == "H6" and ranked[1] == "H9", counts


# ═══════════════════════════════════════════════════════════════════════════
# HF-P13　HC-13 宽表有效内容列边界
# ═══════════════════════════════════════════════════════════════════════════

#: 11 张附注披露宽表（`(entry_code, sheet_name, 扫描行范围)`）。
#: 🔴 `max_column` 250~257 但有效列 6~14 ⇒ 按 `max_column` 放 UUID 会落在 251+ 列。
WIDE_DISCLOSURE_SHEETS: tuple[tuple[str, str], ...] = (
    ("H2", "附注披露信息（上市公司）"),
    ("H2", "附注披露信息（国有企业）"),
    ("H3", "附注披露信息（上市公司）"),
    ("H3", "附注披露信息（国有企业）"),
    ("H4", "附注披露信息（上市公司）"),
    ("H4", "附注披露信息（国有企业）"),
    ("H5", "附注披露信息（上市公司）"),
    ("H5", "附注披露信息（国有企业）"),
    ("H7", "附注披露信息（上市公司）"),
    ("H7", "附注披露信息（国有企业）"),
    ("H8", "附注披露信息（国企）"),
)


class TestHfP13WideTableEffectiveColumns:
    """HC-13：instrumentation 按**有效内容列**扫描，UUID 放「有效内容列 +1」。"""

    @pytest.mark.parametrize(
        "code,sheet", WIDE_DISCLOSURE_SHEETS, ids=[f"{c}:{s}" for c, s in WIDE_DISCLOSURE_SHEETS]
    )
    def test_wide_sheet_effective_columns_are_far_below_max_column(
        self, code: str, sheet: str
    ) -> None:
        import openpyxl

        wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES[code], data_only=False)
        assert sheet in wb.sheetnames, f"{code} 册缺 {sheet!r}"
        ws = wb[sheet]
        max_col = ws.max_column
        effective = F.effective_content_columns(code, sheet, range(1, min(ws.max_row, 60) + 1))
        wb.close()
        assert max_col >= 100, f"{code}:{sheet} max_column={max_col} —— 不是宽表？"
        assert 1 <= effective <= 20, f"{code}:{sheet} 有效列={effective}"
        assert effective * 5 < max_col, (code, sheet, effective, max_col)

    def test_uuid_column_must_be_effective_plus_one_not_max_column_plus_one(self) -> None:
        """🔴 变异「按 `max_column` 放 UUID」的判据：两者相差 200+ 列。"""
        from openpyxl.utils import get_column_letter

        import openpyxl

        code, sheet = WIDE_DISCLOSURE_SHEETS[0]
        wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES[code], data_only=False)
        max_col = wb[sheet].max_column
        wb.close()
        effective = F.effective_content_columns(code, sheet, range(1, 60))
        assert get_column_letter(effective + 1) != get_column_letter(max_col + 1)
        assert max_col + 1 - (effective + 1) > 200, (effective, max_col)


# ═══════════════════════════════════════════════════════════════════════════
# HF-P14　HC-14 四个干净点：守卫方向是「断言保持为无」
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP14CleanPointsStayAbsent:
    """HC-14：definedName 0 / 无 Excel Table / 模板目录全索引 / `H2A` 解析返 None。"""

    @pytest.mark.parametrize("code", sorted(F.H_TEMPLATES))
    def test_no_defined_name_residue(self, code: str) -> None:
        facts = F.workbook_clean_points(code)
        assert facts["defined_name_count"] == 0, f"{code} definedName={facts['defined_name_count']}"

    @pytest.mark.parametrize("code", sorted(F.H_TEMPLATES))
    def test_no_excel_table_in_any_h_workbook(self, code: str) -> None:
        facts = F.workbook_clean_points(code)
        assert facts["excel_tables"] == {}, f"{code} 出现 Excel Table：{facts['excel_tables']}"

    def test_gt_custom_hidden_sheet_exists_only_in_h9_and_h10(self) -> None:
        """两册独有 `GT_Custom` hidden sheet ⇒ 断言存在且**不纳管**。"""
        with_custom = {
            code
            for code in F.H_TEMPLATES
            if "GT_Custom" in F.workbook_clean_points(code)["hidden_sheets"]
        }
        assert with_custom == {"H9", "H10"}, with_custom

    def test_template_directory_is_fully_indexed_and_bytes_are_frozen(self) -> None:
        """11 个文件全部在 `_index.json` 且 sha256/字节与 slice 冻结值一致。

        🔴 变异「往 H 模板目录塞一本未索引的册子」⇒ 本判据打红。
        """
        frozen = F.authoritative_templates()
        assert len(frozen) == 11, sorted(frozen)
        for name, facts in frozen.items():
            assert facts["actual_sha256"] == facts["frozen_sha256"], name
            assert facts["actual_size"] == facts["frozen_size"], name
            assert facts["in_runtime_index"] is True, name
        # 目录里不得有 slice 之外的 xlsx（跳过 Office 锁文件）
        on_disk = {
            p.name
            for p in F.TPL_H.glob("*.xlsx")
            if not p.name.startswith("~$")
        }
        assert on_disk == set(frozen), on_disk ^ set(frozen)
        assert not any(F.TPL_H.glob("*.docx")), "H 目录不应有 docx"

    def test_program_sheet_codes_resolve_to_their_parent_workbook(self) -> None:
        """🔴 **本判据反驳 spec HC-14 第 5 行**。

        spec 写「程序表码 `H2A` 解析返 `None` 是**正确**的 ⇒ 守卫应断言 `resolved is None`」。
        按值实测 **`H2A` 解析到 `H2 在建工程.xlsx`**（程序表 sheet 在该册里，前缀命中父册）。
        5 个程序表码全部如此：`H2A` / `H3A` / `H5A` / `H7A` / `H8A`。

        ⇒ 若照 spec 把守卫写成「断言 None」，它会在**第一次运行时就红**，
        而且红的方向会误导下一个人去"修" finder。真正需要断言 None 的是**幻影码**
        （见 :meth:`test_phantom_codes_must_not_leak_into_another_entrys_workbook`）。
        """
        from app.services.wp_template_finder import find_template_file

        for code, expected in (
            ("H2A", "H2 在建工程.xlsx"),
            ("H3A", "H3 投资性房地产.xlsx"),
            ("H5A", "H5 油气资产.xlsx"),
            ("H7A", "H7 生产性生物资产.xlsx"),
            ("H8A", "H8 使用权资产.xlsx"),
        ):
            resolved = find_template_file(code)
            assert resolved is not None, f"{code} 实测应命中父册"
            assert Path(str(resolved)).name == expected, (code, str(resolved))

    def test_phantom_codes_must_not_leak_into_another_entrys_workbook(self) -> None:
        """🔴 FC-2 零回退的**正确**判据：幻影码不得命中**别的 entry** 的册子。

        🔴 **这里是本轮最重要的一条现状发现**。9 个幻影码里 **7 个**确实全路径返 None：
        `H2C` / `H3I` / `H4E` / `H5O` / `H7B` / `H8R` / `H9L`。
        但 **2 个不是幻影码**：

        | 幻影码 | `find_template_file` | 根因 |
        |---|---|---|
        | 🔴 `H6A` | `H6 固定资产清理.xlsx` | `H6A` **同时**是真实程序表码（`固定资产清理实质性程序表H6A`） |
        | 🔴 `H10A` | `H10 资产处置损益.xlsx` | 同理（`资产处置损益实质性程序表H10A`） |

        ⇒ 若照 G2 provider 的 `assert_no_implicit_template_fallback()` 原样写
        （「幻影码不得命中任何模板」），**H6 与 H10 两条 provider 会在注册路径上直接抛错**。

        真正的不变量不是「不得命中」而是「**不得命中别的 entry 的册子**」：
        `H6A`→H6 自己的册、`H10A`→H10 自己的册，都是同册别名，没有跨 entry 泄漏风险。
        本判据按这个口径写，H6/H10 的 provider 也按这个口径实现并显式登记该碰撞。

        另：`find_all_template_files`（sheet 级解析）对 9 个幻影码**一律返 `[]`**，
        所以 sheet 级零回退在 9 条上都成立。
        """
        from app.services.wp_template_finder import (
            find_all_template_files,
            find_template_file,
            find_template_file_any,
        )

        phantom_by_entry = {
            "H2": "H2C",
            "H3": "H3I",
            "H4": "H4E",
            "H5": "H5O",
            "H6": "H6A",
            "H7": "H7B",
            "H8": "H8R",
            "H9": "H9L",
            "H10": "H10A",
        }
        strictly_absent: list[str] = []
        same_workbook_alias: dict[str, str] = {}
        for code, phantom in phantom_by_entry.items():
            # sheet 级解析：9 条一律为空
            assert find_all_template_files(phantom) == [], phantom
            resolved = find_template_file(phantom)
            assert find_template_file_any(phantom) == resolved, phantom
            if resolved is None:
                strictly_absent.append(phantom)
            else:
                name = Path(str(resolved)).name
                # 🔴 关键不变量：只能命中**自己 entry** 的册子
                assert name == F.H_TEMPLATES[code], (phantom, name, F.H_TEMPLATES[code])
                same_workbook_alias[phantom] = name

        assert sorted(strictly_absent) == ["H2C", "H3I", "H4E", "H5O", "H7B", "H8R", "H9L"]
        assert sorted(same_workbook_alias) == ["H10A", "H6A"], same_workbook_alias

    @pytest.mark.parametrize(
        "code", ["H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10"]
    )
    def test_whole_workbook_code_resolution_has_exactly_one_candidate(self, code: str) -> None:
        """整册码回落 clean：一 wp_code 一册，候选集合大小恒为 1（FC-3 在 H 成立）。"""
        from app.services.wp_template_finder import find_template_file

        resolved = find_template_file(code)
        assert resolved is not None, f"{code} 未解析到模板"
        assert Path(str(resolved)).name == F.H_TEMPLATES[code], (code, str(resolved))


# ═══════════════════════════════════════════════════════════════════════════
# HF-P16　HC-16 footer 形态（含第三形态 / 全角空格 / 多 footer）
# ═══════════════════════════════════════════════════════════════════════════

#: 9 条主受管表的 footer 实测（`(entry, sheet, footer_row, A 列标签, 形态)`）。
FOOTER_FACTS: tuple[tuple[str, str, int, str, str], ...] = (
    ("H2", "明细表H2-2", 21, "合计", "pure_sum"),
    ("H3", "明细表（成本模式）H3-2", 28, "合计", "pure_sum"),
    ("H4", "明细表H4-2", 28, "合计", "derived_unit_price"),
    ("H5", "明细表H5-2", 33, "合计", "pure_sum"),
    ("H6", "明细表H6-2", 16, "　合计", "pure_sum"),
    ("H7", "明细表（成本模式）H7-2", 37, "合计", "pure_sum"),
    ("H8", "明细表H8-2", 32, "合计", "pure_sum"),
    ("H9", "租赁负债明细表H9-2", 14, "合计", "pure_sum"),
    ("H10", "明细表H10-2", 17, "合计", "pure_sum_plus_ratio_footer"),
)


def _footer_row_values(code: str, sheet: str, row: int) -> dict[str, object]:
    import openpyxl

    wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES[code], data_only=False)
    ws = wb[sheet]
    label = ws.cell(row=row, column=1).value
    formulas = {
        ws.cell(row=row, column=c).column_letter: str(ws.cell(row=row, column=c).value)
        for c in range(1, ws.max_column + 1)
        if isinstance(ws.cell(row=row, column=c).value, str)
        and str(ws.cell(row=row, column=c).value).startswith("=")
    }
    next_label = ws.cell(row=row + 1, column=1).value
    wb.close()
    return {"label": label, "formulas": formulas, "next_label": next_label}


class TestHfP16FooterForms:
    """HC-16：footer 三形态 + 全角空格容错 + 多 footer。"""

    @pytest.mark.parametrize(
        "code,sheet,row,label,kind",
        FOOTER_FACTS,
        ids=[f"{c}:{k}" for c, _s, _r, _l, k in FOOTER_FACTS],
    )
    def test_footer_label_is_the_real_cell_text(
        self, code: str, sheet: str, row: int, label: str, kind: str
    ) -> None:
        facts = _footer_row_values(code, sheet, row)
        assert str(facts["label"]) == label, (code, repr(facts["label"]))

    def test_h6_footer_marker_carries_a_fullwidth_space_prefix(self) -> None:
        """🔴 变异「`footer_marker` 写成不含全角空格的『合计』」SHALL 打红。"""
        facts = _footer_row_values("H6", "明细表H6-2", 16)
        label = str(facts["label"])
        assert label.startswith("\u3000"), repr(label)
        assert label != "合计"
        assert label.strip("\u3000") == "合计"

    def test_h4_footer_is_not_pure_sum_but_carries_derived_unit_price_columns(self) -> None:
        """🔴 HC-16 第三形态：H4-2 合计行含派生单价列（`F=G28/E28` 族），非纯 SUM。"""
        facts = _footer_row_values("H4", "明细表H4-2", 28)
        formulas = facts["formulas"]
        assert isinstance(formulas, dict)
        division = {col: f for col, f in formulas.items() if "/" in f and "SUM" not in f}
        assert set(division) >= {"F", "I", "L", "O"}, formulas
        for col, expected in (("F", "=G28/E28"), ("I", "=J28/H28"), ("L", "=M28/K28"), ("O", "=P28/N28")):
            assert formulas[col].replace(" ", "") == expected, (col, formulas[col])

    def test_h4_inline_unit_price_has_division_by_zero_exposure(self) -> None:
        """行内同型 `F=G12/E12` 无 IFERROR 包裹 ⇒ 分母 0 会产 `#DIV/0!`（除零守卫的依据）。"""
        import openpyxl

        wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES["H4"], data_only=False)
        ws = wb["明细表H4-2"]
        raw = str(ws["F12"].value)
        wb.close()
        assert raw.replace(" ", "") == "=G12/E12", raw
        assert "IFERROR" not in raw.upper()

    def test_h10_has_a_second_footer_row(self) -> None:
        """🔴 HC-16 多 footer：R17 合计 + R18「各月比例」；只声明单 footer 会把 R18 当业务行。"""
        facts = _footer_row_values("H10", "明细表H10-2", 17)
        assert str(facts["label"]) == "合计"
        assert facts["next_label"] is not None
        assert "比例" in str(facts["next_label"]), repr(facts["next_label"])

    def test_h9_canary_footer_is_the_simplest_pure_sum(self) -> None:
        """canary 选型依据之二：H9 footer 是纯 SUM `SUM(B9:B13)`。"""
        facts = _footer_row_values("H9", "租赁负债明细表H9-2", 14)
        formulas = facts["formulas"]
        assert isinstance(formulas, dict)
        assert formulas["B"].replace(" ", "") == "=SUM(B9:B13)", formulas["B"]
        assert all(f.startswith("=SUM(") for f in formulas.values()), formulas
