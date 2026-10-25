# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 3 Task 28~29：空分母报告与交接。

spec: k-cycle-sync-foundation-and-first-canary
Task 28: 空分母报告（Property 20 / 24 / 69 / 70）
Task 29: 交接给两份 lane spec
Property: KF-P52, KF-P53, KF-P54, KF-P55, KF-P56, KF-P57, KF-P62

═══ 空分母纪律 ═══

🔴 「没有 contract 所以 Property 通过」这种重言式必须被显式拒绝。
每条 Property 分两半报：
  - **不宣称通过的部分**：分母为空（contract 数 0 / adapter 数 0 / 回写路径不存在）
  - **真验的部分**：前提方向、非空分母

═══ 🔴 一处口径演进（如实登记）═══

design.md 的共享基类消费方 **窄 29 / 宽 33 / 差集 4**，实测 **窄 27 / 宽 27 /
差集 0**。平台侧演进（部分消费方已迁移或删除），且两口径已收敛为一致。
**K 循环贡献 0 边这条结论不变**（这才是本 spec 关心的）。
"""
from __future__ import annotations

import itertools
import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    FRONTEND,
    K_INDEXES,
    NON_CONTRACT_FILES_IN_CONTRACT_DIR,
    ROOT,
    cached_text,
    contract_dir_split,
    derived_total_keys,
    k_domain_files,
    strip_comments,
)

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_k_cycle_deletion_plan.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
SHARED_BASE = FRONTEND / "components/workpaper/composables/useWorkpaperEntryDualMode.ts"
REGISTRY = ROOT / "backend/app/services/workpaper_sync/adapters/registry.py"

#: 八个 slice 的循环码
SLICE_CYCLES = ("D", "E", "F", "G", "H", "I", "J", "K")

#: 交接清单：项 -> 去向 lane
HANDOFF = {
    "BP-4（K1-9 writeoff adapter 化，五常量五跳写路径）": "lane1",
    "BP-5（7 个一阶 orphan + 宿主内联 IIFE）": "lane1",
    "BP-8 的 24 处（K1 3 · K3 1 · K5 7 · K6 7 · K7 6）": "lane1",
    "KC-11 的 70 格 #REF! 实际修复（覆盖层）": "lane1",
    "KC-20 的 4 个孤儿 per-row 键清理": "lane1",
    "KC-21 的 审定表K2-1 纯派生标注": "lane1",
    "KC-9 的 definedName 断链 65 个 + 81 个基线（K2 29 + K4 36）": "lane1",
    "KC-7 的下标族 removeRow（K2~K7）": "lane1",
    "BP-6 的其余 5 条（legacy 端点 + localStorage 收敛）": "lane2",
    "BP-8 的 21 处（K8 8 · K9 7 · K11 4 · K12 2）": "lane2",
    "KC-8 的跨循环枢纽 K11（H1 pilot golden 回归）": "lane2",
    "KC-15 的 K8/K9 disabled 门控形态": "lane2",
    "K8/K9 截止性测试双 sheet（方向变体）": "lane2",
    "K11 / K13 真库 0 行 ⇒ 合成载荷": "lane2",
}

#: lane 1 的 7 条 entry
LANE1_ENTRY_IDS = frozenset({
    "xlsx/gt-k1-other-receivables",
    "xlsx/gt-k2-other-current-assets",
    "xlsx/gt-k3-other-payables",
    "xlsx/gt-k4-other-current-liabilities",
    "xlsx/gt-k5-provisions",
    "xlsx/gt-k6-held-for-sale",
    "xlsx/gt-k7-deferred-income",
})

#: lane 2 的 5 条 entry
LANE2_ENTRY_IDS = frozenset({
    "xlsx/gt-k8-selling-expenses",
    "xlsx/gt-k9-admin-expenses",
    "xlsx/gt-k11-asset-impairment-loss",
    "xlsx/gt-k12-non-operating-income",
    "xlsx/gt-k13-non-operating-expense",
})

#: foundation 的 1 条
FOUNDATION_ENTRY_ID = "xlsx/gt-k10-other-income"


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(MANIFEST_SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return json.loads(FULL_MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def slice_entry_sets() -> dict[str, set[str]]:
    """八个 slice 的 entry_id 集合。"""
    out: dict[str, set[str]] = {}
    for c in SLICE_CYCLES:
        p = DATA / f"workpaper_sync_{c.lower()}_cycle_manifest_slice.json"
        assert p.exists(), f"slice 不存在：{p}"
        doc = json.loads(p.read_text(encoding="utf-8"))
        out[c] = {e["entry_id"] for e in doc["independent_entries"]}
    return out


# ════════════════════════════════════════════════════════════════════════════
# KF-P53：Property 20 —— contract 维度不宣称通过
# ════════════════════════════════════════════════════════════════════════════
class TestKFP53Property20EmptyContractDenominator:
    """🔴 「registry 拒绝 col_ 占位」这部分**不宣称通过**（分母为空）。"""

    def test_k_cycle_production_contract_count_is_zero(self) -> None:
        """K 循环已发布**生产**契约数 == 0 ⇒ 分母为空。"""
        k_owned: list[str] = []
        for p in sorted(CONTRACT_DIR.glob("*.json")):
            doc = json.loads(p.read_text(encoding="utf-8"))
            if doc.get("review_status") != "reviewed":
                continue
            owner = (doc.get("review") or {}).get("entry_id") or ""
            if re.match(r"^xlsx/gt-k(1[0-3]|[1-9])(?![0-9])-", owner):
                k_owned.append(p.name)
        # 🔴 2026-10-01 晋级后：K 生产契约**恰好**是晋级账本的 6 份（不再是 0）。
        from tests.workpaper_sync.k_foundation_facts import K_REVIEWED_CONTRACTS

        assert sorted(k_owned) == sorted(
            f"{cid}.json" for cid in K_REVIEWED_CONTRACTS.values()
        ), f"K 循环生产契约与晋级账本不符：{k_owned}"

    def test_the_empty_part_is_explicitly_not_claimed(
        self, manifest_slice: dict
    ) -> None:
        """slice 的 property_denominators 显式标 not_claimed_passing。"""
        pd = manifest_slice["property_denominators"]["property_20"]
        assert pd["not_claimed_passing"] is True
        assert pd["not_claimed_passing_part"].strip()
        assert pd["carrier_for_the_empty_part"].strip()
        assert "分母为空" in pd["k_cycle_denominator"]

    def test_premise_direction_1_contract_ownership_read_per_file(self) -> None:
        """前提方向①：契约归属逐文件读 `review.entry_id`（不按文件名猜）。

        🔴 口径勘误（与 p8 `test_contract_directory_counts` 同源）：遍历范围是
        **契约文件**而不是目录下所有 `*.json` —— 该目录另有一张 L 循环的键映射表
        （无 `review_status`），按「全是契约」遍历会要求它也带 `review.entry_id`，
        红的原因与 K 循环无关。白名单的可伪证性由 p8 的两条判据守住。
        """
        contracts, others = contract_dir_split()
        assert contracts, "契约目录为空 ⇒ 判据空跑"
        assert set(others) == set(NON_CONTRACT_FILES_IN_CONTRACT_DIR), (
            f"非契约文件集变了：{sorted(others)}"
        )
        for name, doc in contracts.items():
            if doc.get("review_status") == "candidate":
                assert (doc.get("review") or {}).get("entry_id") is None, (
                    f"{name} 是 candidate 却带 entry_id"
                )
                continue
            owner = (doc.get("review") or {}).get("entry_id")
            assert owner, f"{name} 的 review.entry_id 缺失"

    def test_premise_direction_2_registry_has_zero_k_adapter(self) -> None:
        """前提方向②：registry 里 K adapter 数 == 0。"""
        assert REGISTRY.exists(), f"registry 不存在：{REGISTRY}"
        src = REGISTRY.read_text(encoding="utf-8")
        for n in K_INDEXES:
            needle = f"gt-k{n}-"
            assert needle not in src, (
                f"registry 出现 {needle} ⇒ K 循环已注册 adapter"
            )

    def test_premise_direction_3_hosts_make_no_bidirectional_claim(
        self, manifest_slice: dict
    ) -> None:
        """前提方向③：13 宿主模板无「可双向回写」字样。"""
        for e in manifest_slice["independent_entries"]:
            src = strip_comments(cached_text(ROOT / e["host_path"]))
            start = src.find("<template>")
            end = src.rfind("</template>")
            tpl = src[start:end] if start >= 0 and end > start else src
            for claim in ("可双向回写", "双向回写"):
                assert claim not in tpl, (
                    f"{e['entry_id']}: 宿主模板出现「{claim}」但 adapter 未注册"
                )

    def test_premise_direction_4_all_13_adapter_id_null(
        self, manifest_slice: dict
    ) -> None:
        """前提方向④：13 条 adapter_id 全 null。"""
        for e in manifest_slice["independent_entries"]:
            assert e["adapter_id"] is None, f"{e['entry_id']} 有 adapter_id"


# ════════════════════════════════════════════════════════════════════════════
# KF-P54：Property 24 —— 两个分母分开报
# ════════════════════════════════════════════════════════════════════════════
class TestKFP54Property24TwoDenominators:
    """🔴 空的是「回写时保护公式格」，实的是 83 个派生态键。"""

    def test_empty_part_writeback_path_does_not_exist(
        self, manifest_slice: dict
    ) -> None:
        """空分母：OO↔HTML 回写路径不存在（13 条全 legacy_fake_bidirectional）。"""
        for e in manifest_slice["independent_entries"]:
            assert e["migration_state"] == "legacy_fake_bidirectional", (
                f"{e['entry_id']} 的 migration_state 变了 ⇒ 回写路径可能已存在"
            )

    def test_empty_part_is_explicitly_not_claimed(
        self, manifest_slice: dict
    ) -> None:
        pd = manifest_slice["property_denominators"]["property_24"]
        assert pd["not_claimed_passing"] is True
        assert pd["not_claimed_passing_part"].strip()
        assert pd["carrier_for_the_empty_part"].strip()

    def test_non_empty_part_83_derived_total_keys(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 非空分母：K 域派生态 checklist 键 **83 个**（KC-16）。"""
        full = derived_total_keys(k_files, include_infix=True)
        assert len(full) == 83, f"derived_total 期望 83，实得 {len(full)}"

    def test_non_empty_part_is_really_verifiable(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """83 个键是真对象：每个都能定位到源码命中点。"""
        full = derived_total_keys(k_files, include_infix=True)
        sample = sorted(full)[:5]
        for key in sample:
            found = any(
                key in strip_comments(cached_text(p)) for p in k_files
            )
            assert found, f"派生键 {key} 在源码里找不到 ⇒ 分母是假的"

    def test_canary_contract_declares_no_input_mode_for_derived(self) -> None:
        """canary 契约对派生态不标 `mode:"input"`（Property 24 的落点）。

        🔴 canary 的数据区无公式 ⇒ `formula_mask` 为空、无 derived_fields。
        这不是「Property 24 通过」，是「canary 上没有派生格这个对象」。
        """
        # 🔴 2026-10-01：canary 草案已晋级为 reviewed 生产契约（草案归档到 spec evidence）
        #    ⇒ 判据落点改读生产契约；reviewed 契约的 review 块不再带 derived_fields 键。
        draft_path = CONTRACT_DIR / "k10.other_income_adjustment.json"
        assert draft_path.exists()
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        assert draft["review_status"] == "reviewed"
        table = draft["sheets"][0]["tables"][0]
        assert table["formula_mask"] == []
        assert not draft["review"].get("derived_fields")
        modes = {f["mode"] for f in table["fields"]}
        assert modes == {"editable"}, (
            f"canary 字段 mode 集合 {sorted(modes)} ⇒ 有派生格须验保护"
        )


# ════════════════════════════════════════════════════════════════════════════
# KF-P55：Property 69 —— 只作负向真验
# ════════════════════════════════════════════════════════════════════════════
class TestKFP55Property69NegativeOnly:
    """🔴 13 条 UNVERIFIABLE 各带非空 reasons + 无一条空口 VERIFIED。"""

    def test_all_13_are_unverifiable(self, manifest_slice: dict) -> None:
        states = [
            e["evidence"]["verification_state"]
            for e in manifest_slice["independent_entries"]
        ]
        assert states == ["UNVERIFIABLE"] * 13, (
            f"verification_state 集合：{sorted(set(states))}"
        )

    def test_each_has_non_empty_reasons(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            reasons = e["evidence"].get("unverifiable_reasons") or []
            assert reasons, f"{e['entry_id']} 的 unverifiable_reasons 为空"
            for r in reasons:
                assert str(r).strip(), f"{e['entry_id']} 有空白 reason"

    def test_no_entry_claims_verified(self, manifest_slice: dict) -> None:
        """🔴 无一条空口声称 VERIFIED。"""
        verified = [
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if e["evidence"]["verification_state"] == "VERIFIED"
        ]
        assert verified == [], f"有 entry 声称 VERIFIED：{verified}"

    def test_reasons_point_to_the_blocking_preconditions(
        self, manifest_slice: dict
    ) -> None:
        """reasons 指向真实存在的 BP（不是含糊措辞）。"""
        bp_ids = {b["id"] for b in manifest_slice["blocking_preconditions"]}
        for e in manifest_slice["independent_entries"]:
            blob = " ".join(e["evidence"]["unverifiable_reasons"])
            hit = [bp for bp in bp_ids if bp in blob]
            assert hit, (
                f"{e['entry_id']} 的 reasons 不指向任何 BP：{blob[:80]}"
            )

    def test_positive_direction_is_blocked_by_bp3(
        self, manifest_slice: dict
    ) -> None:
        """正向逐 scenario 闭合待 BP-3（真 OO 9.4 探针）。"""
        bp_ids = {b["id"] for b in manifest_slice["blocking_preconditions"]}
        assert "BP-3" in bp_ids
        for e in manifest_slice["independent_entries"]:
            assert "BP-3" in e["capability_target_blocked_by"], (
                f"{e['entry_id']} 不受 BP-3 阻塞 ⇒ 正向可验，登记须更新"
            )


# ════════════════════════════════════════════════════════════════════════════
# KF-P56：Property 70 —— 真验非空分母
# ════════════════════════════════════════════════════════════════════════════
class TestKFP56Property70CrossEntryIsolation:
    """🔴 八 slice 两两不相交共 28 个配对（非空分母，真验）。"""

    def test_eight_slices_exist(self, slice_entry_sets: dict[str, set[str]]) -> None:
        assert len(slice_entry_sets) == 8
        assert set(slice_entry_sets) == set(SLICE_CYCLES)

    def test_28_pairs_are_all_disjoint(
        self, slice_entry_sets: dict[str, set[str]]
    ) -> None:
        """28 个配对逐对验零交集。"""
        pairs = list(itertools.combinations(sorted(slice_entry_sets), 2))
        assert len(pairs) == 28, f"配对数期望 28，实得 {len(pairs)}"
        overlaps = [
            (a, b, sorted(slice_entry_sets[a] & slice_entry_sets[b]))
            for a, b in pairs
            if slice_entry_sets[a] & slice_entry_sets[b]
        ]
        assert overlaps == [], f"有交集的配对：{overlaps}"

    def test_each_slice_is_non_empty(
        self, slice_entry_sets: dict[str, set[str]]
    ) -> None:
        """每个 slice 非空（分母不塌）。"""
        for c, ids in slice_entry_sets.items():
            assert ids, f"slice {c} 为空 ⇒ 配对判据对它空跑"

    def test_13_template_workbooks_are_distinct(
        self, manifest_slice: dict
    ) -> None:
        """13 条 `template_ref.workbook` 两两不同（集合大小 == 13）。"""
        wbs = [
            e["template_ref"]["workbook"]
            for e in manifest_slice["independent_entries"]
        ]
        assert len(wbs) == 13
        assert len(set(wbs)) == 13, (
            f"有重复 workbook：{[w for w in set(wbs) if wbs.count(w) > 1]}"
        )

    def test_14_template_files_single_injection(
        self, manifest_slice: dict
    ) -> None:
        """14 册 `belongs_to_entry` 单射（13 非 null + 1 null）。"""
        files = manifest_slice["authoritative_templates"]["files"]
        owners = [f["belongs_to_entry"] for f in files if f["belongs_to_entry"]]
        assert len(owners) == 13
        assert len(set(owners)) == 13, "belongs_to_entry 有重复 ⇒ 非单射"
        nulls = [f for f in files if f["belongs_to_entry"] is None]
        assert len(nulls) == 1 and nulls[0].get("excluded_reason")

    def test_deletion_paths_are_disjoint_from_other_slices(self) -> None:
        """删除路径与其余七份 slice 不相交。"""
        k_plan = json.loads(DELETION_PLAN_PATH.read_text(encoding="utf-8"))

        def _collect_ts_paths(node: object, out: set[str]) -> None:
            """递归收集所有以 `.ts` / `.vue` 结尾的**真实路径**字符串。

            🔴 只认带 `/` 且以源码后缀结尾的串 —— 否则 `counters` 这类**键名**
            会被当成路径，然后在别的 slice 里必然命中（每份计划都有 counters 节）。
            """
            if isinstance(node, str):
                if "/" in node and node.endswith((".ts", ".vue")):
                    out.add(node)
            elif isinstance(node, dict):
                for v in node.values():
                    _collect_ts_paths(v, out)
            elif isinstance(node, list):
                for v in node:
                    _collect_ts_paths(v, out)

        collected: set[str] = set()
        _collect_ts_paths(k_plan, collected)
        assert collected, "K 删除计划里提取不到任何源码路径 ⇒ 判据空跑"

        # 🔴 排除**共享件**路径：删除计划会引用共享基类等作参照（不是删除目标），
        #    它们天然出现在每份 slice 里，算进「不相交」会必然假红。
        shared_markers = ("useWorkpaperEntryDualMode", "/sync/", "/shared/")
        k_paths = {
            p for p in collected
            if not any(m in p for m in shared_markers)
        }
        shared_refs = collected - k_paths
        assert k_paths, "K 域专属删除路径为空 ⇒ 不相交判据空跑"
        # 专属路径全落 K 域（证明提取口径对）
        for path in k_paths:
            assert re.search(r"[kK](1[0-3]|[1-9])(?![0-9])", path), (
                f"提取到非 K 域专属路径 {path} ⇒ 收集口径有误"
            )
        # 共享引用确实存在（证明排除不是空操作）
        assert shared_refs, (
            "删除计划不引用任何共享件 ⇒ 本条排除逻辑多余，可简化"
        )
        for c in SLICE_CYCLES:
            if c == "K":
                continue
            p = DATA / f"workpaper_sync_{c.lower()}_cycle_deletion_plan.json"
            if not p.exists():
                continue
            other = p.read_text(encoding="utf-8")
            for path in k_paths:
                assert path not in other, (
                    f"K 的删除路径 {path} 出现在 {c} 循环的删除计划里"
                )


# ════════════════════════════════════════════════════════════════════════════
# KF-P57：契约与 adapter 分母分开算
# ════════════════════════════════════════════════════════════════════════════
class TestKFP57ContractAdapterDenominatorsSeparate:
    """🔴 「契约已发」≠「adapter 已注册」。"""

    def test_reviewed_contracts_far_exceed_registered_adapters(
        self, full_manifest: dict
    ) -> None:
        reviewed = sum(
            1 for p in CONTRACT_DIR.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("review_status")
            == "reviewed"
        )
        non_null = sum(1 for e in full_manifest["entries"] if e.get("adapter_id"))
        assert reviewed > non_null, (
            f"reviewed {reviewed} 不大于 adapter_id 非空 {non_null}"
            " ⇒ 「契约已发 ≠ adapter 已注册」这条登记须撤"
        )

    def test_manifest_has_no_adapter_registered_field(
        self, full_manifest: dict
    ) -> None:
        """🔴 manifest 无 `adapter_registered` 字段 ⇒ 按它判恒得 0。"""
        has = [
            e["entry_id"] for e in full_manifest["entries"]
            if "adapter_registered" in e
        ]
        assert has == [], f"出现 adapter_registered 字段：{has[:3]}"

    def test_candidate_denominator_is_non_empty(self) -> None:
        """candidate 反例分母非空（含本 spec 的 canary 草案）。"""
        candidates = [
            p.name for p in CONTRACT_DIR.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("review_status")
            == "candidate"
        ]
        assert candidates, "candidate 分母为空 ⇒ 「不得进生产」判据无对象"
        # 🔴 K10 草案已晋级（不得再以 candidate 身份留在目录里）；K 循环剩余 candidate
        #    只有 K2 一份未晋级草案。
        assert "k10.other_income_adjustment.candidate.json" not in candidates
        assert {c for c in candidates if c.startswith("k")} == {
            "k2.adjudication_derived.candidate.json",
        }


# ════════════════════════════════════════════════════════════════════════════
# KF-P62：共享基类 K 贡献 0 边
# ════════════════════════════════════════════════════════════════════════════
class TestKFP62SharedBaseZeroContribution:
    """🔴 KD-3：K 对共享基类贡献 **0** 边（本任务前后不变）。

    ═══ 一处口径演进（如实登记）═══
    design.md 记 窄 **29** / 宽 **33** / 差集 **4**；实测 窄 **27** / 宽 **27** /
    差集 **0**。平台侧演进（部分消费方已迁移或删除），两口径已收敛为一致。
    **K 贡献 0 边这条结论不变** —— 这才是本 spec 关心的。
    """

    _STMT_RX = re.compile(r"(?:from|import\(|vi\.mock\()\s*['\"]([^'\"]+)['\"]")

    @pytest.fixture(scope="class")
    def all_frontend(self) -> list[pathlib.Path]:
        return [
            p for p in FRONTEND.rglob("*")
            if p.is_file()
            and p.suffix in (".ts", ".vue")
            and "__tests__" not in p.as_posix()
        ]

    def test_shared_base_exists(self) -> None:
        assert SHARED_BASE.exists(), f"共享基类不存在：{SHARED_BASE}"

    def test_narrow_and_wide_calibers_are_both_non_empty(
        self, all_frontend: list[pathlib.Path]
    ) -> None:
        """两口径都非空（分母不塌）。"""
        wide = [
            p for p in all_frontend
            if p != SHARED_BASE
            and "useWorkpaperEntryDualMode" in strip_comments(cached_text(p))
        ]
        narrow = [
            p for p in all_frontend
            if p != SHARED_BASE
            and any(
                "useWorkpaperEntryDualMode" in m.group(1)
                for m in self._STMT_RX.finditer(strip_comments(cached_text(p)))
            )
        ]
        assert wide, "宽口径为 0 ⇒ 基类无消费方，判据空跑"
        assert narrow, "窄口径为 0 ⇒ statement-position 解析失效"
        assert len(narrow) <= len(wide), "窄口径不应超过宽口径"

    def test_k_cycle_contributes_zero_edges(
        self, all_frontend: list[pathlib.Path], k_files: list[pathlib.Path]
    ) -> None:
        """🔴 核心结论：K 域文件对共享基类贡献 0 条 statement-position 边。"""
        k_set = set(k_files)
        k_consumers = [
            p.name for p in all_frontend
            if p in k_set
            and any(
                "useWorkpaperEntryDualMode" in m.group(1)
                for m in self._STMT_RX.finditer(strip_comments(cached_text(p)))
            )
        ]
        assert k_consumers == [], (
            f"K 域有 {len(k_consumers)} 个文件消费共享基类：{k_consumers}"
            " ⇒ KD-3 的「K 贡献 0 边」结论须更新"
        )

    def test_all_13_dual_mode_composables_do_not_import_the_base(self) -> None:
        """逐条验：`useK{n}DualMode.ts` 都不 import 共享基类。

        🔴 分母从 13 降为 **6** —— BP-5 删掉了 7 个 orphan。「K 贡献 0 边」这个
        结论不变（删掉的那 7 个删前也是 0 边），但分母必须如实缩小，
        否则读文件会 FileNotFoundError。
        """
        from tests.workpaper_sync.k_foundation_facts import (
            BP5_DELETED_ORPHAN_ENTRIES,
            dual_mode_path,
        )

        checked = 0
        for n in K_INDEXES:
            p = dual_mode_path(n)
            if n in BP5_DELETED_ORPHAN_ENTRIES:
                assert not p.exists(), f"useK{n}DualMode.ts 仍在 ⇒ 删除未生效"
                continue
            src = strip_comments(cached_text(p))
            hits = [
                m.group(1) for m in self._STMT_RX.finditer(src)
                if "useWorkpaperEntryDualMode" in m.group(1)
            ]
            assert hits == [], f"useK{n}DualMode.ts import 了基类：{hits}"
            checked += 1
        assert checked == 6, f"实检 {checked} 个（13 − 7 已删）"

    def test_symbol_name_grep_would_be_misleading(self) -> None:
        """🔴 反证：按**符号名** grep 会把只在文档注释里提到它的文件算成消费方。

        slice 明文记录：`useK9DualMode.ts` 曾只在文档注释里提到该符号，
        符号名口径会把它算成消费方 ⇒ 「K 贡献 0 边」结论会翻。
        本判据用 statement-position 路径解析，剥注释后再匹配。
        """
        from tests.workpaper_sync.k_foundation_facts import dual_mode_path

        # 🔴 只在**仍存在**的文件上比（BP-5 删掉 7 个）
        alive = [n for n in K_INDEXES if dual_mode_path(n).exists()]
        assert len(alive) == 6, f"仍存在的 DualMode 文件 {alive}"
        # 剥注释前后对比：若某文件注释里提到基类，剥注释后应消失
        raw_hits = []
        stripped_hits = []
        for n in alive:
            p = dual_mode_path(n)
            if "useWorkpaperEntryDualMode" in cached_text(p):
                raw_hits.append(p.name)
            if "useWorkpaperEntryDualMode" in strip_comments(cached_text(p)):
                stripped_hits.append(p.name)
        # 剥注释后必须不多于剥前；且最终 statement-position 口径为 0
        assert len(stripped_hits) <= len(raw_hits)
        assert not any(
            any(
                "useWorkpaperEntryDualMode" in m.group(1)
                for m in self._STMT_RX.finditer(
                    strip_comments(cached_text(dual_mode_path(n)))
                )
            )
            for n in alive
        ), "statement-position 口径下仍有 K 域消费方"


# ════════════════════════════════════════════════════════════════════════════
# Task 29 / KF-P52：交接给两份 lane spec
# ════════════════════════════════════════════════════════════════════════════
SPECS_DIR = ROOT / ".kiro" / "specs"
LANE1_SPEC = SPECS_DIR / "k1-k7-inlined-iife-hosts-and-orphan-cleanup"
LANE2_SPEC = SPECS_DIR / "k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub"
FOUNDATION_SPEC = SPECS_DIR / "k-cycle-sync-foundation-and-first-canary"


class TestKFP52HandoffToTwoLanes:
    """🔴 交接清单逐条指名（不含模糊表述）+ 三者 entry 无交集并集 13。"""

    def test_both_lane_specs_exist_with_three_artifacts(self) -> None:
        """两份 lane spec 三件套齐备。"""
        for spec in (LANE1_SPEC, LANE2_SPEC, FOUNDATION_SPEC):
            assert spec.is_dir(), f"spec 目录不存在：{spec}"
            for name in ("requirements.md", "design.md", "tasks.md"):
                assert (spec / name).exists(), f"{spec.name} 缺 {name}"

    def test_three_entry_sets_are_disjoint_and_union_is_13(
        self, manifest_slice: dict
    ) -> None:
        """foundation 1 + lane1 7 + lane2 5 == 13，两两无交集。"""
        assert len(LANE1_ENTRY_IDS) == 7
        assert len(LANE2_ENTRY_IDS) == 5
        foundation = {FOUNDATION_ENTRY_ID}
        assert foundation & LANE1_ENTRY_IDS == set()
        assert foundation & LANE2_ENTRY_IDS == set()
        assert LANE1_ENTRY_IDS & LANE2_ENTRY_IDS == set()
        union = foundation | LANE1_ENTRY_IDS | LANE2_ENTRY_IDS
        assert len(union) == 13
        declared = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert union == declared, (
            f"多 {sorted(union - declared)}，缺 {sorted(declared - union)}"
        )

    def test_lane1_is_exactly_the_bp5_holders(
        self, manifest_slice: dict
    ) -> None:
        """lane 1 的 7 条 == BP-5 持有者全集。"""
        bp5 = {
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if "BP-5" in e["capability_target_blocked_by"]
        }
        assert bp5 == LANE1_ENTRY_IDS, (
            f"多 {sorted(bp5 - LANE1_ENTRY_IDS)}，缺 {sorted(LANE1_ENTRY_IDS - bp5)}"
        )

    def test_lane2_is_bp6_minus_canary(self, manifest_slice: dict) -> None:
        """lane 2 的 5 条 == BP-6 全集去掉 canary（K10）。"""
        bp6 = {
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if "BP-6" in e["capability_target_blocked_by"]
        }
        assert len(bp6) == 6, f"BP-6 持有者期望 6 条，实得 {len(bp6)}"
        assert bp6 - {FOUNDATION_ENTRY_ID} == LANE2_ENTRY_IDS

    def test_handoff_list_has_no_vague_wording(self) -> None:
        """🔴 交接清单每条都指名（含 BP 号或 KC 号或具体对象）。"""
        assert len(HANDOFF) == 14, f"交接项数变了：{len(HANDOFF)}"
        vague = ("等等", "相关", "若干", "部分内容", "其他事项")
        for item in HANDOFF:
            for v in vague:
                assert v not in item, f"交接项含模糊措辞「{v}」：{item}"
            has_anchor = (
                re.search(r"BP-\d+", item)
                or re.search(r"KC-\d+", item)
                or re.search(r"K(1[0-3]|[1-9])(?![0-9])", item)
            )
            assert has_anchor, f"交接项无可定位锚点：{item}"

    def test_handoff_split_is_8_and_6(self) -> None:
        """交接分摊：lane1 8 项 + lane2 6 项 == 14。"""
        lane1 = [k for k, v in HANDOFF.items() if v == "lane1"]
        lane2 = [k for k, v in HANDOFF.items() if v == "lane2"]
        assert len(lane1) == 8, f"lane1 交接项期望 8，实得 {len(lane1)}"
        assert len(lane2) == 6, f"lane2 交接项期望 6，实得 {len(lane2)}"
        assert len(lane1) + len(lane2) == 14

    def test_lane_specs_reference_kc_numbers_without_restating(self) -> None:
        """🔴 两份 lane spec 只**引用** KC-x 编号，不复述正文。

        判据：lane spec 里出现 KC-x 引用，但**不含** foundation design.md 里
        KC 条文的独特长句（抽样三条最长的裁决正文）。
        """
        foundation_design = (FOUNDATION_SPEC / "design.md").read_text(encoding="utf-8")
        # 抽 KC 正文里的独特长句（≥20 字且只在 foundation 出现）
        signatures = [
            "这三个值**不是裁决**",
            "按 H 的「载体有 `http.put`」或按「每条 entry 都得有",
            "内层明细 R9-R11 已被 R12 吸收",
        ]
        for sig in signatures:
            assert sig in foundation_design, (
                f"签名句不在 foundation design 里，抽样失效：{sig[:20]}"
            )
        for spec in (LANE1_SPEC, LANE2_SPEC):
            for name in ("requirements.md", "design.md", "tasks.md"):
                text = (spec / name).read_text(encoding="utf-8")
                for sig in signatures:
                    assert sig not in text, (
                        f"{spec.name}/{name} 复述了 KC 正文：{sig[:20]}"
                    )

    def test_lane_specs_do_cite_kc_numbers(self) -> None:
        """两份 lane spec 确实引用了 KC 编号（不是完全不提）。"""
        for spec in (LANE1_SPEC, LANE2_SPEC):
            blob = "".join(
                (spec / n).read_text(encoding="utf-8")
                for n in ("requirements.md", "design.md", "tasks.md")
            )
            cited = set(re.findall(r"KC-\d+", blob))
            assert len(cited) >= 8, (
                f"{spec.name} 只引用了 {len(cited)} 个 KC 编号：{sorted(cited)}"
            )

    def test_property_prefixes_are_spec_scoped(self) -> None:
        """三份 spec 各用独立 Property 前缀（KF-P / KA-P / KB-P）。"""
        expected = {
            FOUNDATION_SPEC: "KF-P",
            LANE1_SPEC: "KA-P",
            LANE2_SPEC: "KB-P",
        }
        for spec, prefix in expected.items():
            blob = "".join(
                (spec / n).read_text(encoding="utf-8")
                for n in ("requirements.md", "design.md", "tasks.md")
            )
            own = set(re.findall(rf"{prefix}\d+", blob))
            assert own, f"{spec.name} 找不到自己的前缀 {prefix}"
            # 不得大量使用别人的前缀（引用个别编号可接受，≤3 个）
            for other_prefix in set(expected.values()) - {prefix}:
                foreign = set(re.findall(rf"{other_prefix}\d+", blob))
                assert len(foreign) <= 3, (
                    f"{spec.name} 大量使用了 {other_prefix}：{sorted(foreign)[:6]}"
                )


class TestHandoffItemsAreRealObjects:
    """交接项指向的对象真实存在（不是空交接）。"""

    def test_lane1_bp4_writeoff_owner_exists(self) -> None:
        p = FRONTEND / "components/workpaper/composables/useK1WriteoffCheck.ts"
        assert p.exists(), f"BP-4 的 owner 不存在：{p}"

    def test_lane1_seven_orphans_have_been_deleted(self) -> None:
        """🔴 交接项已兑现：lane 1 的 Task 5 把这 7 个 orphan **删掉了**。

        foundation 阶段这条判据验的是「交接对象真实存在」（不是空交接）。
        lane 1 接手并删除后，判据翻面 —— 验「确已删除」+「删的是登记的那 7 个」。
        """
        from tests.workpaper_sync.k_foundation_facts import (
            BP5_DELETED_ORPHAN_ENTRIES,
            dual_mode_path,
        )

        assert tuple(range(1, 8)) == BP5_DELETED_ORPHAN_ENTRIES
        for n in BP5_DELETED_ORPHAN_ENTRIES:
            assert not dual_mode_path(n).exists(), (
                f"orphan useK{n}DualMode.ts 仍在 ⇒ lane 1 的 BP-5 处置未完成"
            )
        # 两侧都验：BP-6 组的 6 个一个没少（删除没越界）
        for n in (8, 9, 10, 11, 12, 13):
            assert dual_mode_path(n).exists(), (
                f"useK{n}DualMode.ts 被误删 ⇒ 它属 BP-6 组"
            )

    def test_lane1_k2_k4_defined_names_are_the_65(self) -> None:
        """definedName 断链 65 个全在 lane 1（K2 29 + K4 36）。"""
        from openpyxl import load_workbook
        total = 0
        for name in ("K2 其他流动资产.xlsx", "K4 其他流动负债.xlsx"):
            wb = load_workbook(
                ROOT / "backend/wp_templates/K" / name,
                read_only=False, data_only=False,
            )
            try:
                total += sum(
                    1 for dn in wb.defined_names.values()
                    if "#REF!" in str(
                        dn.attr_text if hasattr(dn, "attr_text") else dn.value
                    )
                )
            finally:
                wb.close()
        assert total == 65, f"K2+K4 的 #REF! definedName 期望 65，实得 {total}"

    def test_lane2_k11_frozen_keys_are_consumed_cross_cycle(self) -> None:
        """K11 的跨循环键真被消费（交接对象非空）。"""
        rx = re.compile(r"['\"`](K11-[A-Za-z0-9\-]+)['\"`]")
        k_set = set(k_domain_files())
        consumed: set[str] = set()
        for p in FRONTEND.rglob("*"):
            if (
                not p.is_file()
                or p.suffix not in (".ts", ".vue")
                or "__tests__" in p.as_posix()
                or p in k_set
            ):
                continue
            consumed |= {m.group(1) for m in rx.finditer(strip_comments(cached_text(p)))}
        assert len(consumed) >= 9, (
            f"K11 跨循环被消费键只有 {len(consumed)} 个：{sorted(consumed)}"
        )

    def test_lane2_k8_k9_cutoff_sheets_exist(self) -> None:
        """K8/K9 截止性测试四张 sheet 真实存在。"""
        from openpyxl import load_workbook
        for book, codes in (
            ("K8 销售费用.xlsx", ("K8-6", "K8-7")),
            ("K9 管理费用.xlsx", ("K9-6", "K9-7")),
        ):
            wb = load_workbook(
                ROOT / "backend/wp_templates/K" / book, read_only=True
            )
            try:
                names = wb.sheetnames
            finally:
                wb.close()
            for code in codes:
                assert any(code in n for n in names), (
                    f"{book} 找不到 {code}：{names}"
                )
