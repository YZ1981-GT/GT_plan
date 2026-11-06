# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 0 Task 1：manifest 与 slice 分歧门（BP-9）。

spec: k-cycle-sync-foundation-and-first-canary
Task 1: manifest 与 slice 分歧门（BP-9），验证 13 条 entry 边界
Property: KF-P1, KF-P2, KF-P3, KF-P4

═══ 判据 ═══

KF-P1: 按 selection_rule 从 manifest 现算 K 前缀 xlsx 独立 entry == slice 的
       independent_entries，大小 **13**。
KF-P2: manifest 里 13 条 K entry 的 capability 全 `single_onlyoffice` /
       html_store 全 `unresolved` / adapter_id 全 null / **0 条有 capability_target**。
       🔴 这是 overlay 默认值机械展开的结果，不是裁决（KC-1）。
KF-P3: slice 现算 bidirectional 条数 == 0 且 capability_verdict_pending == 13；
       守卫断言 manifest 与 slice **不相等**并指向 BP-9。
KF-P4: parent_entry_id ∈ 13 条 == 0 ∧ overlay parent_rules 含 /k\\d 的 == 0 ∧
       slice 顶层无 parent_duplicate_summary 键。

═══ 与 test_task53 的关系 ═══

test_task53_k_cycle_migration.py 的 TestSliceScopeIsRecomputable 已覆盖
selection_rule 现算、scope counter、parent_duplicate 两侧验。本文件**聚焦
foundation spec 独有的精确判据**：KC-1 的 manifest 原值四字段逐条验、
slice 与 manifest 的不等式方向验、entry 全名等值。不重复 test_task53 的判据，
而是**加入它未覆盖的精确维度**。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY_PATH = DATA / "workpaper_sync_entry_overlay.json"

#: 13 条 entry 的全名（全名，无缩写，与 design.md 切分表等值）
K_ENTRY_IDS = frozenset({
    "xlsx/gt-k1-other-receivables",
    "xlsx/gt-k2-other-current-assets",
    "xlsx/gt-k3-other-payables",
    "xlsx/gt-k4-other-current-liabilities",
    "xlsx/gt-k5-provisions",
    "xlsx/gt-k6-held-for-sale",
    "xlsx/gt-k7-deferred-income",
    "xlsx/gt-k8-selling-expenses",
    "xlsx/gt-k9-admin-expenses",
    "xlsx/gt-k10-other-income",
    "xlsx/gt-k11-asset-impairment-loss",
    "xlsx/gt-k12-non-operating-income",
    "xlsx/gt-k13-non-operating-expense",
})


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _n_of_entry(entry_id: str) -> int:
    """`xlsx/gt-k{n}-…` → n（与 `TestKFP2ManifestOriginalValues._split` 同一提取口径）。"""
    m = re.match(r"^xlsx/gt-k(1[0-3]|[1-9])-", entry_id)
    assert m, entry_id
    return int(m.group(1))


def _k_prefixed_xlsx_independent(full_manifest: dict) -> list[dict]:
    """按 slice 的 selection_rule 从 manifest 现算 K 前缀 xlsx 独立 entry。"""
    out = []
    for e in full_manifest["entries"]:
        pats = (e.get("wp_match") or {}).get("wp_code_patterns") or []
        if (
            any(str(p).startswith("K") for p in pats)
            and e["document_type"] == "xlsx"
            and e["independent_entry"]
        ):
            out.append(e)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def overlay() -> dict:
    return _load(OVERLAY_PATH)


# ════════════════════════════════════════════════════════════════════════════
# KF-P1: entry 集合等值
# ════════════════════════════════════════════════════════════════════════════
class TestKFP1EntrySetEquality:
    """selection_rule 从 manifest 现算的集合与 slice 声明的集合等值。"""

    def test_selection_rule_recomputes_exactly_13(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        recomputed = {
            e["entry_id"] for e in _k_prefixed_xlsx_independent(full_manifest)
        }
        declared = {
            e["entry_id"] for e in manifest_slice["independent_entries"]
        }
        assert declared == recomputed, (
            f"多写 {sorted(declared - recomputed)}，漏写 {sorted(recomputed - declared)}"
        )
        assert len(recomputed) == 13

    def test_entry_ids_match_the_design_table(
        self, manifest_slice: dict
    ) -> None:
        """与 design.md 的切分表等值比对——13 条全名一个不多一个不少。"""
        actual = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert actual == K_ENTRY_IDS, (
            f"与 design 表不符：多 {sorted(actual - K_ENTRY_IDS)}，"
            f"缺 {sorted(K_ENTRY_IDS - actual)}"
        )

    def test_slice_scope_count_equals_13(self, manifest_slice: dict) -> None:
        assert manifest_slice["slice_scope"]["independent_entry_count"] == 13


# ════════════════════════════════════════════════════════════════════════════
# KF-P2: manifest 原值四字段（KC-1：overlay 默认值，非裁决）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP2ManifestOriginalValues:
    """🔴 manifest 原值是 overlay 默认值机械展开的结果，不是逐 entry 裁决。"""

    # 🔴 2026-10-01 晋级后：原「13 条全 single_onlyoffice / unresolved / null」只对
    #    **未晋级**的 8 条成立；晋级的 5 条（K_BIDIRECTIONAL_ENTRIES）必须恰好是
    #    bidirectional + 具名 html_store + adapter_id == K_REVIEWED_CONTRACTS[n]。
    #    两侧都精确等值 ⇒ 多晋级 / 少晋级 / 晋级到别的 adapter 都会打红。
    @staticmethod
    def _split(full_manifest: dict) -> tuple[dict[int, dict], dict[int, dict]]:
        from tests.workpaper_sync.k_foundation_facts import K_BIDIRECTIONAL_ENTRIES

        by_n: dict[int, dict] = {}
        for e in _k_prefixed_xlsx_independent(full_manifest):
            m = re.match(r"^xlsx/gt-k(1[0-3]|[1-9])-", e["entry_id"])
            assert m, e["entry_id"]
            by_n[int(m.group(1))] = e
        promoted = {n: e for n, e in by_n.items() if n in K_BIDIRECTIONAL_ENTRIES}
        rest = {n: e for n, e in by_n.items() if n not in K_BIDIRECTIONAL_ENTRIES}
        return promoted, rest

    def test_all_13_capability_is_single_onlyoffice_in_manifest(
        self, full_manifest: dict
    ) -> None:
        """晋级的恰为 bidirectional；未晋级的是**待裁决**（capability=null + 三字段齐备）。

        🔴 2026-11-05：原判据要求未晋级的仍是 `single_onlyoffice`。umbrella spec
        `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的 task 1.1 把未逐项裁决的
        entry 统一落成 `capability=null` + pending 三字段（AC 1.3：拒绝继续用组件默认值当裁决）
        ⇒ 剩下的 K10 现算 null，原判据恒红。**保留 `== "single_onlyoffice"` 等于要求把 overlay
        默认值写回去当裁决**，那正是 AP-3 明禁的。判据改成验 pending 态本身。
        """
        from tests.workpaper_sync.k_foundation_facts import K_BIDIRECTIONAL_ENTRIES

        ks = _k_prefixed_xlsx_independent(full_manifest)
        assert len(ks) == 13
        promoted, rest = self._split(full_manifest)
        assert sorted(promoted) == sorted(K_BIDIRECTIONAL_ENTRIES)
        assert rest, "没有未晋级的 entry ⇒ 本判据的 pending 分母空了，K 循环已全部晋级，判据要改写"
        for n, e in rest.items():
            assert e["capability"] is None, (
                f"K{n}: manifest capability={e['capability']!r} —— 未逐项裁决的 entry 只能是 null"
            )
            for field in ("capability_target", "capability_verdict_stage", "capability_target_blocked_by"):
                assert e.get(field), f"K{n} 的 pending 三字段缺 {field}"
        bidir = sorted(
            n for n, e in {**promoted, **rest}.items()
            if e["capability"] == "bidirectional"
        )
        assert bidir == sorted(K_BIDIRECTIONAL_ENTRIES)

    def test_all_13_html_store_is_unresolved_in_manifest(
        self, full_manifest: dict
    ) -> None:
        promoted, rest = self._split(full_manifest)
        for n, e in rest.items():
            assert e["html_store"] == "unresolved", (
                f"K{n}: manifest html_store={e['html_store']!r}"
            )
        for n, e in promoted.items():
            expected = (
                "checklist_responses_k1_writeoff_dict"
                if n == 1
                else rf"checklist_responses_k{n}_adjustment_(entries|rows)"
            )
            assert re.fullmatch(expected, e["html_store"]), (
                f"K{n}: 晋级后 html_store={e['html_store']!r}"
            )

    def test_all_13_adapter_id_is_null_in_manifest(
        self, full_manifest: dict
    ) -> None:
        from tests.workpaper_sync.k_foundation_facts import K_REVIEWED_CONTRACTS

        promoted, rest = self._split(full_manifest)
        for n, e in rest.items():
            assert e["adapter_id"] is None, (
                f"K{n}: manifest adapter_id={e['adapter_id']!r}"
            )
        for n, e in promoted.items():
            assert e["adapter_id"] == K_REVIEWED_CONTRACTS[n], (
                f"K{n}: adapter_id={e['adapter_id']!r}"
            )

    def test_zero_entries_have_capability_target_field_in_manifest(
        self, full_manifest: dict
    ) -> None:
        """原 KC-1：manifest 原值里 0 条带 capability_target —— 🔴 断言已按 pending 裁决制重写。

        KC-1 当初的论点是「manifest 给的是 overlay 默认值，不是逐项裁决，所以**没有** target 这种
        裁决产物」。task 1.1 之后恰好相反：没裁决的 entry **必须**带 target（pending 三字段），
        带 target 的那条正是「还没裁」的标记。⇒ 判据翻面并带上分界：pending 的带 target，
        已晋级的不带（晋级就是裁决完成，再留 target 会让人以为还没裁）。
        """
        promoted, rest = TestKFP2ManifestOriginalValues._split(full_manifest)
        assert [e["entry_id"] for e in rest.values() if "capability_target" not in e] == [], (
            "有未晋级的 entry 不带 capability_target ⇒ pending 态没有记录目标，无法复核"
        )
        leftover = [e["entry_id"] for e in promoted.values() if "capability_target" in e]
        assert leftover == [], f"已晋级的 entry 还留着 capability_target：{leftover}"

    def test_these_values_come_from_overlay_defaults_not_per_entry_ruling(
        self, full_manifest: dict, overlay: dict
    ) -> None:
        """overlay 仍声明组件默认值，但未晋级的 entry **不再**采用它（AC 1.3 的落点）。

        🔴 2026-11-05：原判据是「未晋级的 7 条 capability / html_store 逐值等于 overlay 默认值」。
        两件事都变了：晋级后 rest 只剩 K10 一条；且 task 1.1 让它走 pending（capability=null）而
        不是默认值。默认值声明本身仍是事实、仍要验（它是「默认值存在但不被当裁决」的前提）⇒
        判据改成：默认值照旧声明 `single_onlyoffice` / `unresolved`，而未晋级的 entry 的 capability
        **不等于**该默认值 —— 这正是 AC 1.3 要求的「拒绝用组件默认值当裁决」。
        """
        defaults = overlay.get("defaults_by_component", {}).get("GtOnlyOfficeSheet", {})
        assert defaults.get("capability") == "single_onlyoffice"
        assert defaults.get("html_store") == "unresolved"
        _promoted, rest = TestKFP2ManifestOriginalValues._split(full_manifest)
        assert rest, "pending 分母空了 ⇒ 本判据失去对象"
        for e in rest.values():
            assert e["capability"] != defaults["capability"], (
                f"{e['entry_id']} 的 capability 又回到 overlay 默认值 {defaults['capability']!r} "
                "⇒ 组件默认值被当成了逐项裁决（AC 1.3 / AP-3 明禁）"
            )
            # html_store 仍是默认值：它描述的是「HTML 侧落点尚未解析」，与 capability 裁决无关
            assert e["html_store"] == defaults["html_store"]


# ════════════════════════════════════════════════════════════════════════════
# KF-P3: slice 与 manifest 不相等（BP-9）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP3SliceManifestDivergence:
    """守卫断言 manifest 与 slice 在 capability 上不相等并指向 BP-9。"""

    def test_slice_bidirectional_count_is_zero(
        self, manifest_slice: dict
    ) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        assert s["adjudicated_as_bidirectional"] == 0

    def test_slice_capability_verdict_pending_is_13(
        self, manifest_slice: dict
    ) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        assert s["capability_verdict_pending"] == 13

    def test_all_13_slice_entries_have_null_capability(
        self, manifest_slice: dict
    ) -> None:
        """slice 的 capability 全 null（待裁决），manifest 的是 single_onlyoffice。"""
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] is None, (
                f"{e['entry_id']}: slice capability={e['capability']!r}，应为 null（待裁决）"
            )

    def test_manifest_and_slice_are_not_equal_and_point_to_bp9(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 分歧集合必须恰是「已晋级」那一批，且分歧已登记为 BP-9。

        🔴 2026-11-05：原判据写死「13/13 全不一致」。那是晋级前的状态（slice 冻结 null、manifest
        给 overlay 默认值 single_onlyoffice）。现在两侧都变了：晋级的 12 条 live 已是
        bidirectional（仍与 slice 的 null 不等），未晋级的 K10 走 pending、live 也是 null ⇒ 与
        slice **相等**。写死 13 会把「K10 的分歧已消除」报成判据失败 ⇒ 改成「分歧集合 == 晋级集合」：
        少一条（有人把晋级的写回 null）或多一条（pending 的被塞成默认值）都打红。
        """
        from tests.workpaper_sync.k_foundation_facts import K_BIDIRECTIONAL_ENTRIES

        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        diverged = sorted(
            _n_of_entry(e["entry_id"])
            for e in manifest_slice["independent_entries"]
            if by_id[e["entry_id"]]["capability"] != e["capability"]
        )
        assert diverged == sorted(K_BIDIRECTIONAL_ENTRIES), (
            f"capability 分歧集合现算 K{diverged}，期望恰是已晋级的 K{sorted(K_BIDIRECTIONAL_ENTRIES)} —— "
            "断言全部相等就是把 overlay 默认值当裁决（AP-3 明禁），断言全部不等则会把已消除的分歧算进来"
        )
        # BP-9 必须存在于阻断项列表
        bp_ids = {b["id"] for b in manifest_slice["blocking_preconditions"]}
        assert "BP-9" in bp_ids, "BP-9 不在阻断项列表里"

    def test_manifest_mirror_documents_the_divergence(
        self, manifest_slice: dict
    ) -> None:
        """每条 entry 的 manifest_mirror 须指出 why_not_adopted 含 BP-9。"""
        for e in manifest_slice["independent_entries"]:
            mirror = e["manifest_mirror"]
            assert mirror["capability"] == "single_onlyoffice", (
                f"{e['entry_id']}: 镜像值期望 single_onlyoffice"
            )
            assert "BP-9" in mirror["why_not_adopted"], (
                f"{e['entry_id']}: why_not_adopted 不含 BP-9"
            )


# ════════════════════════════════════════════════════════════════════════════
# KF-P4: parent_duplicate 为 0（两侧都验）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP4ParentDuplicateZero:
    """KD-5: parent_duplicate == 0，且 slice 顶层无 parent_duplicate_summary。"""

    #: 🔴 2026-10-07（`ae318ce9d`）起 K 的 5 张调整子 Tab + K1 核销检查子 Tab 各自挂
    #: 共享同步宿主 `WorkpaperSyncEditorHost` 并声明父 entry 身份。它们与 KD-5 说的
    #: 「legacy parent_duplicate」不是一回事（冻结时还不存在），逐条登记。
    SYNC_HOST_SUBTABS = (
        "xlsx/k1/inspection/k1-tab-writeoff-check",
        "xlsx/k11/core/k11-tab-adjustment",
        "xlsx/k12/core/k12-tab-adjustment",
        "xlsx/k13/core/k13-tab-adjustment",
        "xlsx/k8/core/k8-tab-adjustment",
        "xlsx/k9/core/k9-tab-adjustment",
    )

    def test_no_manifest_entry_has_parent_in_k_set(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 KD-5 要的是 **legacy** parent_duplicate 为 0；同步宿主子页逐条登记。

        原判据是「任何以 K entry 为 parent 的子入口都不许有」。`ae318ce9d`
        （2026-10-07）之后，K 的 6 张子 Tab 开始挂共享同步宿主并声明父 entry 身份，
        这条就红在那 6 条上。它们**不是** legacy 重复面：
          · `mount_components == ['WorkpaperSyncEditorHost']`（统一同步宿主，
            不是 `GtOnlyOfficeSheet` / `OnlyOfficeWordDialog` 那类 legacy 面）；
          · `independent_entry is False` 且 `adjudication_state == 'inherited'`
            ⇒ 不产生独立裁决，裁决只在父 entry 上；
          · `adapter_id is None` ⇒ 不会被当成「已迁移 adapter」重复计数（AC 1.6 的实质）。

        口径与 `test_task57_abcs_and_shared_migration.py` 的
        `global_parent_duplicate_count`（legacy 52 中剔除挂同步宿主的 40 条）**一致** ——
        同一个平台现象在两处用同一把尺子，不是各自放宽。
        """
        k_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        children = [
            e for e in full_manifest["entries"]
            if e.get("parent_entry_id") in k_ids
        ]
        legacy = [
            e["entry_id"] for e in children
            if "WorkpaperSyncEditorHost" not in (e.get("mount_components") or [])
        ]
        assert legacy == [], (
            f"manifest 里有 K 的 legacy parent_duplicate 子入口：{legacy}"
        )
        assert sorted(e["entry_id"] for e in children) == sorted(
            self.SYNC_HOST_SUBTABS
        ), (
            "同步宿主子页清单对不上（左=现算，右=登记）："
            f"{sorted(e['entry_id'] for e in children)} vs {sorted(self.SYNC_HOST_SUBTABS)}"
        )
        # 逐条结构判据：登记它们的前提是「继承父裁决 + 不冒充已迁移 adapter」
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        for e in children:
            eid = e["entry_id"]
            assert e.get("independent_entry") is False, f"{eid} 变成独立入口了"
            assert e.get("adjudication_state") == "inherited", (
                f"{eid} 的 adjudication_state={e.get('adjudication_state')!r}"
                " ⇒ 子页开始自己裁决，须重新登记"
            )
            assert e.get("adapter_id") is None, f"{eid} 被当成已迁移 adapter 计数了"
            parent = by_id.get(e["parent_entry_id"])
            assert parent is not None and parent.get("independent_entry") is True, (
                f"{eid} 的父 entry {e['parent_entry_id']!r} 不是独立入口"
            )

    def test_overlay_has_no_k_parent_rules(self, overlay: dict) -> None:
        k_rules = [
            r for r in overlay.get("parent_rules", [])
            if re.search(r"/k\d+/", str(r.get("file_glob", "")))
        ]
        assert k_rules == [], (
            f"overlay parent_rules 含 K 的 file_glob：{k_rules}"
        )

    def test_slice_scope_count_is_zero(self, manifest_slice: dict) -> None:
        assert manifest_slice["slice_scope"]["parent_duplicate_count"] == 0

    def test_no_parent_duplicate_summary_key_in_slice(
        self, manifest_slice: dict
    ) -> None:
        """🔴 触发条件不成立时写空节 = additive 死声明（KD-5）。"""
        assert "parent_duplicate_summary" not in manifest_slice

    def test_k0_has_template_but_no_entry(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 KD-4 / KF-P7: K0 有册但无 entry（与 J0 的都返 None 相反）。"""
        k0_hits = [
            e["entry_id"] for e in full_manifest["entries"]
            if "k0" in e["entry_id"].lower()
        ]
        assert k0_hits == [], f"manifest 出现 K0 entry：{k0_hits}"
        # K0 权威模板存在
        k_template_dir = ROOT / "backend" / "wp_templates" / "K"
        k0_file = k_template_dir / "K0 管理循环函证.xlsx"
        assert k0_file.exists(), "K0 册不存在 ⇒ 与 KD-4 登记矛盾"
        # slice 里 K0 被排除且有 excluded_reason
        at = manifest_slice["authoritative_templates"]
        k0_rec = next(
            (f for f in at["files"] if f["name"] == "K0 管理循环函证.xlsx"), None
        )
        assert k0_rec is not None, "slice 的 authoritative_templates 没有 K0 册"
        assert k0_rec["belongs_to_entry"] is None
        assert k0_rec.get("excluded_reason"), "K0 无 excluded_reason"
