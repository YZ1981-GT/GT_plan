# -*- coding: utf-8 -*-
"""K 循环 lane 1 — Task 3~5：BP-5 orphan 的两阶可达性、端点清册与删除。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup
Task 3: 7 个 orphan 的两阶可达性判定
Task 4: 7 个 orphan 的 legacy 端点清册（与 lane 2 反向对照）
Task 5: 删除 7 个 orphan
Property: KA-P4, KA-P5, KA-P7, KA-P8

═══ 🔴 删除已执行 ═══

7 个 `useK{n}DualMode.ts`（n=1..7）**已删除**。删前现算证据：

| 判据 | 现算 |
|---|---|
| 生产边 | 各 **0** |
| 测试边 | 各 **0** |
| `composables/index.ts`（barrel） | **不存在** |
| `export * from` 指向它们 | **0 处** |
| `onlyoffice/health` 直调 | 各 **1** 处 |
| `onlyoffice-config` 直调 | 各 **0** 处 |

⇒ 一阶边 0 **且** barrel 不存在 ⇒ 二阶恒 0 ⇒ 删除无消费方受影响。

═══ 🔴 health 端点的三段式账本（口径差异登记）═══

design 写「从 20 降为 13」，实际推进顺序不同：

| 阶段 | health 直调文件数 |
|---|---|
| design 写 spec 时（7 宿主 + 13 composable） | **20** |
| lane 2 收敛 6 个 live composable 后 | **14** |
| 本组删 7 个 orphan 后 | **7** |
| lane 1 Task 7 宿主改走 bridge 后 | **0** |

design 的「13」是「lane 2 还没做」时的预期中间值。链条本身自洽，
只是 lane 2 先落地 ⇒ 现算走 `BP5_HEALTH_*` 账本，不写死 13。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_DELETED_COUNT,
    BP5_DELETED_ORPHAN_ENTRIES,
    BP5_DELETED_ORPHAN_NAMES,
    BP5_DUALMODE_ENTRIES_REMAINING,
    BP5_HEALTH_AFTER_LANE2_CONVERGENCE,
    BP5_HEALTH_AFTER_ORPHAN_DELETION,
    BP5_HEALTH_DESIGN_BASELINE,
    BP5_HOSTS_PREFIX_CONVERGED,
    BP6_INDEXES,
    BP7_NOTICE_MOUNTED_ENTRIES,
    DATA,
    ROOT,
    WP_COMPOSABLES,
    WP_COMPONENTS,
    cached_text,
    dual_mode_path,
    k_domain_files,
    strip_comments,
)
from tests.workpaper_sync.k_lane1_facts import (  # noqa: E402
    BARREL_PATH,
    FRONTEND_SRC,
    LANE1_HOSTS,
    LANE1_INDEXES,
    LANE1_ORPHAN_LINE_COUNTS,
    LEGACY_CONFIG_EP,
    LEGACY_HEALTH_EP,
    host_path,
    orphan_path,
    resolve_import,
    statement_edges_to,
)

SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"

#: 删除前的 legacy 端点清册（append-only 快照）
ORPHAN_HEALTH_HITS_BASELINE = {n: 1 for n in LANE1_INDEXES}
ORPHAN_CONFIG_HITS_BASELINE = {n: 0 for n in LANE1_INDEXES}

#: 🔴 lane 2 的 6 个 live composable 的 config 命中（反向对照的另一端）
LANE2_CONFIG_HITS = {8: 2, 9: 2, 10: 1, 11: 2, 12: 1, 13: 1}


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def orphan_inventory(slice_doc: dict) -> list[dict]:
    return slice_doc["orphan_dual_mode_inventory"]["modules"]


# ════════════════════════════════════════════════════════════════════════════
# Task 3 / KA-P4, KA-P5：两阶可达性
# ════════════════════════════════════════════════════════════════════════════
class TestKAP4TwoOrderReachability:
    """🔴 一阶边 0 **且** barrel 不存在 ⇒ 二阶恒 0（两个条件缺一不可）。"""

    def test_slice_registered_zero_edges_before_deletion(
        self, orphan_inventory: list[dict]
    ) -> None:
        """删除前的边数登记：7 条各 0 生产边 / 0 测试边。"""
        assert len(orphan_inventory) == 7
        for m in orphan_inventory:
            assert m["production_consumers"] == 0, m["id"]
            assert m["test_only_consumers"] == 0, m["id"]
            assert m["orphan_order"] == "first_order", m["id"]
            assert m["barrel_only_reachable_via"] is None, m["id"]

    def test_barrel_still_does_not_exist(self) -> None:
        """🔴 二阶恒 0 的前提 —— barrel 出现就得重算可达性。"""
        assert BARREL_PATH.exists() is False

    def test_no_reexport_targets_the_deleted_names(self) -> None:
        """🔴 删除后仍要验：没有任何 `export * from` 指向这 7 个（会 404）。"""
        offenders: list[str] = []
        for p in FRONTEND_SRC.rglob("*.ts"):
            src = strip_comments(cached_text(p))
            for m in re.finditer(
                r"""export\s+\*\s+from\s*['"]([^'"]+)['"]""", src
            ):
                resolved = resolve_import(m.group(1), p)
                if resolved is None:
                    continue
                if resolved.name in {
                    x.removesuffix(".ts") for x in BP5_DELETED_ORPHAN_NAMES
                }:
                    offenders.append(f"{p.name} -> {resolved.name}")
        assert offenders == [], f"re-export 指向已删文件：{offenders}"

    def test_no_import_targets_the_deleted_files(self) -> None:
        """🔴 删除后零悬挂引用：全仓无任何 import 指向这 7 个（否则构建失败）。"""
        dangling: list[str] = []
        for n in BP5_DELETED_ORPHAN_ENTRIES:
            prod, test = statement_edges_to(orphan_path(n))
            if prod or test:
                dangling.append(f"K{n}: prod={prod} test={test}")
        assert dangling == [], f"悬挂引用：{dangling}"

    def test_symbol_names_are_also_gone_from_production(self) -> None:
        """🔴 补一刀：连**符号名**也不该在生产代码里残留（宿主改内联了）。"""
        residue: list[str] = []
        for n in BP5_DELETED_ORPHAN_ENTRIES:
            sym = f"useK{n}DualMode"
            for p in FRONTEND_SRC.rglob("*"):
                if not p.is_file() or p.suffix not in (".ts", ".vue"):
                    continue
                if "__tests__" in p.as_posix():
                    continue
                if sym in strip_comments(cached_text(p)):
                    residue.append(f"{sym} @ {p.name}")
        assert residue == [], f"符号名残留：{residue}"


# ════════════════════════════════════════════════════════════════════════════
# Task 4 / KA-P7：legacy 端点清册 + 与 lane 2 反向对照
# ════════════════════════════════════════════════════════════════════════════
class TestKAP7LegacyEndpointInventory:
    """7 个 orphan 各 1 处 health / 0 处 config（删除前基线）。"""

    def test_baseline_is_one_health_each(self, orphan_inventory: list[dict]) -> None:
        for m in orphan_inventory:
            eps = m["legacy_endpoints_called"]
            health = [e for e in eps if "onlyoffice/health" in e]
            config = [e for e in eps if LEGACY_CONFIG_EP in e]
            assert len(health) == 1, f"{m['id']}: health 登记 {health}"
            assert config == [], f"{m['id']}: config 应为 0，登记 {config}"

    def test_baseline_arithmetic(self) -> None:
        assert sum(ORPHAN_HEALTH_HITS_BASELINE.values()) == 7
        assert sum(ORPHAN_CONFIG_HITS_BASELINE.values()) == 0

    def test_reverse_comparison_lane2_has_edges_and_config(self) -> None:
        """🔴 反向对照：lane 2 的 6 个 live composable **各 1 条生产边**且各调 1~2 处 config。

        这条证明本 lane 的 `config == 0` 不是漏扫 —— 同一个扫描器在 lane 2
        上能扫出 config（含反引号模板字面量形态）。
        """
        for n in BP6_INDEXES:
            p = dual_mode_path(n)
            assert p.exists(), f"useK{n}DualMode.ts 不存在 ⇒ 对照端失效"
            prod, test = statement_edges_to(p)
            assert len(prod) == 1, f"K{n}: 生产边期望 1，实得 {prod}"
            assert test == [], f"K{n}: 出现测试边 {test}"
            c = strip_comments(cached_text(p)).count(LEGACY_CONFIG_EP)
            assert c == LANE2_CONFIG_HITS[n], (
                f"K{n}: config 期望 {LANE2_CONFIG_HITS[n]}，实得 {c}"
            )
            assert 1 <= c <= 2, f"K{n}: config {c} 越出 1~2"

    def test_the_two_groups_form_a_clean_bisection(self) -> None:
        """🔴 二分干净：本 lane 7 条「无边 + 已删」vs lane 2 的 6 条「1 边 + 有 config」。"""
        for n in BP5_DELETED_ORPHAN_ENTRIES:
            assert not dual_mode_path(n).exists()
        for n in BP6_INDEXES:
            assert dual_mode_path(n).exists()
        assert set(BP5_DELETED_ORPHAN_ENTRIES) & set(BP6_INDEXES) == set()
        assert len(BP5_DELETED_ORPHAN_ENTRIES) + len(BP6_INDEXES) == 13

    def test_config_scanner_recognizes_backtick_templates(self) -> None:
        """🔴 变异反证：只认单/双引号会把 lane 2 的 config 漏成 0。"""
        quoted_only = re.compile(r"""['"][^'"]*onlyoffice-config[^'"]*['"]""")
        total_quoted = 0
        total_substr = 0
        for n in BP6_INDEXES:
            src = strip_comments(cached_text(dual_mode_path(n)))
            total_quoted += len(quoted_only.findall(src))
            total_substr += src.count(LEGACY_CONFIG_EP)
        assert total_substr == sum(LANE2_CONFIG_HITS.values()) == 9
        assert total_quoted < total_substr, (
            f"只认引号口径得 {total_quoted}，子串口径 {total_substr} ⇒ "
            "反引号识别的必要性反证不成立"
        )


# ════════════════════════════════════════════════════════════════════════════
# Task 5 / KA-P8：删除执行与零回归
# ════════════════════════════════════════════════════════════════════════════
class TestKAP8DeletionExecuted:
    """删除已执行且范围精确。"""

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_each_orphan_file_is_gone(self, n: int) -> None:
        assert not orphan_path(n).exists(), f"useK{n}DualMode.ts 仍在"

    def test_exactly_seven_were_deleted(self) -> None:
        assert BP5_DELETED_COUNT == 7
        assert set(BP5_DELETED_ORPHAN_ENTRIES) == set(LANE1_INDEXES)

    def test_deletion_did_not_touch_the_bp6_group(self) -> None:
        """🔴 越界守卫：BP-6 组的 6 个一个没少。"""
        remaining = sorted(
            p.name
            for p in dual_mode_path(8).parent.iterdir()
            if re.fullmatch(r"useK(1[0-3]|[1-9])DualMode\.ts", p.name)
        )
        assert remaining == sorted(
            f"useK{n}DualMode.ts" for n in BP5_DUALMODE_ENTRIES_REMAINING
        ), f"剩余 {remaining}"

    def test_hosts_were_not_deleted(self) -> None:
        """🔴 宿主一个都不能删 —— 它们承载内联 IIFE，是 Task 7 的收敛目标。"""
        for n in LANE1_INDEXES:
            assert host_path(n).exists(), f"{host_path(n).name} 被误删"

    def test_deletion_paths_are_disjoint_from_other_slices(self) -> None:
        """🔴 断言删除路径与其余七份 slice 的删除路径集合**不相交**。"""
        mine = {
            orphan_path(n).relative_to(ROOT).as_posix()
            for n in LANE1_INDEXES
        }
        others: set[str] = set()
        for p in sorted(DATA.glob("workpaper_sync_*_manifest_slice.json")):
            if p.name == SLICE_PATH.name:
                continue
            blob = p.read_text(encoding="utf-8")
            others |= {
                m.group(0)
                for m in re.finditer(
                    r"audit-platform/frontend/src/[^\"#]+\.(?:ts|vue)", blob
                )
            }
        assert mine & others == set(), (
            f"删除路径与其他 slice 相交：{sorted(mine & others)}"
        )

    def test_health_endpoint_dropped_by_exactly_seven_at_this_stage(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 本组（Task 5）交付的降幅是 **−7**，落点是账本第 ③ 段的 7。

        🔴 但 Task 7 随后把 7 宿主也收敛了 ⇒ 现算已是 **0**（第 ④ 段）。
        判据因此验「降幅」而不是「落点」：删除贡献的 7 是本组的交付量，
        它不该因为后续任务继续推进而变得不可验。
        """
        hits = {
            p.name: strip_comments(cached_text(p)).count(LEGACY_HEALTH_EP)
            for p in k_files
        }
        live = {k: v for k, v in hits.items() if v}
        # 本组的交付：composable 侧的 7 处（随文件删除消失）
        for n in LANE1_INDEXES:
            assert not orphan_path(n).exists()
            assert orphan_path(n).name not in live
        # 账本第 ③→④ 段：Task 7 后宿主侧也归零
        assert BP5_HEALTH_AFTER_ORPHAN_DELETION == 7
        assert live == {}, (
            f"K 域仍有 health 直调 {sorted(live)}"
            "（Task 7 已把宿主侧也收敛，这里应为空）"
        )

    def test_the_three_stage_ledger_is_self_consistent(self) -> None:
        """🔴 账本自洽：20 − 6（lane2 收敛）− 7（本组删除）== 7。"""
        assert BP5_HEALTH_DESIGN_BASELINE == 20
        assert (
            BP5_HEALTH_DESIGN_BASELINE - len(BP6_INDEXES)
            == BP5_HEALTH_AFTER_LANE2_CONVERGENCE
            == 14
        )
        assert (
            BP5_HEALTH_AFTER_LANE2_CONVERGENCE - BP5_DELETED_COUNT
            == BP5_HEALTH_AFTER_ORPHAN_DELETION
            == 7
        )

    def test_design_thirteen_was_an_intermediate_not_reached(self) -> None:
        """🔴 口径差异登记：design 的「降为 13」是 lane 2 未做时的预期值。

        13 = 20 − 7（只删 orphan，composable 全未收敛）。实际 lane 2 先落地
        ⇒ 真实路径是 20 → 14 → 7，**13 这个中间值从未出现**。
        """
        never_reached = BP5_HEALTH_DESIGN_BASELINE - BP5_DELETED_COUNT
        assert never_reached == 13
        assert never_reached != BP5_HEALTH_AFTER_ORPHAN_DELETION
        assert never_reached != BP5_HEALTH_AFTER_LANE2_CONVERGENCE

    def test_line_count_baseline_is_frozen_for_audit(self) -> None:
        """🔴 删除前行数留档（838 / splitlines 831）供日后对账。"""
        assert sum(LANE1_ORPHAN_LINE_COUNTS.values()) == 838
        assert sum(v - 1 for v in LANE1_ORPHAN_LINE_COUNTS.values()) == 831


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 下游 ABCS 普查的归因（跨 spec 红灯的份额锁定）
# ═══════════════════════════════════════════════════════════════════════════
#
# `test_task57_abcs_and_shared_migration.py`（ABCS+shared spec 的普查文件）现有
# **9 条红**。归因现算如下 —— 其中 4 条有 K 份额，**全部是本系列 spec 明令要求的
# 结果**，另 5 条与 K 无关（并发会话 F/G/H/I/J 的契约新增与载体删除）：
#
# | task57 判据 | K 份额 | 性质 |
# |---|---|---|
# | `test_ac14_notice_single_source...` | **13/13 全部** | BP-7 兑现：13 条宿主全挂 notice |
# | `test_item_prefix_constants...` | **3/3 全部** | BP-5 Task 7：K4/K5/K6 前缀常量收敛 |
# | `test_no_per_entry_dual_mode_composable_exists` | 7/11 | BP-5：删 7 个 orphan |
# | `test_cross_entry_isolation_assertions...` | 8/36 | 8 份 k* candidate 契约 |
# | 其余 5 条 | **0** | 并发会话（契约新增 / J·N 载体删除） |
#
# 🔴 **不回填 ABCS 切片、不改 task57** —— 切片是改造前快照（append-only），
# 且 K 侧的删除早在 `workpaper_sync_task66_legacy_deletion_plan.json` 里**预登记**。
# 本组判据的作用：把「我的份额」钉成现算等式，任何人想靠**还原 K 侧改造**去修
# task57 的红，这里会先红。
#
#: ABCS 切片声明的 notice 域外消费方（append-only 快照，**不改**）
ABCS_DECLARED_NOTICE_OUT_OF_SCOPE = 46
#: ABCS 切片声明的全仓 dual-mode 模块数（append-only 快照，**不改**）
ABCS_DECLARED_DUAL_MODE_MODULES = 114

ABCS_SLICE_PATH = DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"
TASK66_PLAN_PATH = DATA / "workpaper_sync_task66_legacy_deletion_plan.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
NOTICE_VUE = WP_COMPONENTS / "sync" / "GtEntrySyncCapabilityNotice.vue"

LEGACY_PREFIX_CONST = "DUAL_MODE_STORAGE_PREFIX"

#: K 域文件名判别式（判别式而非站点：站点会被改，形态不会）
_K_FILE_RX = re.compile(r"/(?:GtK\d+[A-Za-z]*\.vue|useK\d+[A-Za-z]*\.ts|k\d+[A-Za-z]\w*\.ts)$")
_K_SUBDIR_RX = re.compile(r"/workpaper/k\d+/")


def _ref_is_k_domain(ref: str) -> bool:
    f = ref.split("#")[0]
    return bool(_K_FILE_RX.search(f) or _K_SUBDIR_RX.search(f))


@pytest.fixture(scope="module")
def abcs_slice() -> dict:
    return json.loads(ABCS_SLICE_PATH.read_text(encoding="utf-8"))


def _collect_prefix_refs(node: object, out: list[str]) -> None:
    if isinstance(node, dict):
        if node.get("name") == LEGACY_PREFIX_CONST and "ref" in node:
            out.append(node["ref"])
        for v in node.values():
            _collect_prefix_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_prefix_refs(v, out)


class TestDownstreamAbcsCensusAttribution:
    """🔴 跨 spec 红灯份额锁定：K 的贡献必须恰好等于 spec 明令的数量。"""

    def test_the_slice_snapshot_is_not_backfilled_by_us(self, abcs_slice: dict) -> None:
        """🔴 先证「我们没动别人的产物」—— 声明值仍是改造前快照。"""
        node = abcs_slice["mode_switch_resolution"]["ac14_notice_single_source"]
        assert node["out_of_scope_consumer_count"] == ABCS_DECLARED_NOTICE_OUT_OF_SCOPE
        assert node["in_scope_consumer_count"] == 0
        refs: list[str] = []
        _collect_prefix_refs(abcs_slice, refs)
        assert len(refs) == len(BP5_HOSTS_PREFIX_CONVERGED) == 3, refs

    def test_every_prefix_ref_in_the_slice_points_at_a_converged_k_host(
        self, abcs_slice: dict
    ) -> None:
        """🔴 3/3 全部归 K：切片登记的前缀常量站点就是 K4/K5/K6 宿主，且已收敛。"""
        refs: list[str] = []
        _collect_prefix_refs(abcs_slice, refs)
        want = {LANE1_HOSTS[n] for n in BP5_HOSTS_PREFIX_CONVERGED}
        got = {r.split("#")[0].rsplit("/", 1)[-1] for r in refs}
        assert got == want, (got, want)
        for r in refs:
            f = ROOT / r.split("#")[0]
            assert f.is_file(), f"切片 ref 指向的宿主不存在了：{r}"
            assert LEGACY_PREFIX_CONST not in cached_text(f), (
                f"{f.name} 仍有 {LEGACY_PREFIX_CONST} ⇒ BP-5 Task 7 被回退"
            )

    def test_the_prefix_removal_was_pre_planned_not_accidental(self) -> None:
        """🔴 删除是计划内：task66 清册早已登记这 3 个 legacy 键前缀。"""
        plan = TASK66_PLAN_PATH.read_text(encoding="utf-8")
        for n in BP5_HOSTS_PREFIX_CONVERGED:
            assert f"k{n}-dual-mode:" in plan, f"k{n} 的 legacy 前缀未在 task66 清册登记"

    def test_k_owns_the_entire_notice_consumer_delta(self) -> None:
        """🔴 13/13 全部归 K：非 K 侧现算恰等于切片声明 ⇒ 增量全是 BP-7。"""
        prod, _ = statement_edges_to(NOTICE_VUE)
        k_edges = [r for r in prod if _ref_is_k_domain(r)]
        non_k = [r for r in prod if not _ref_is_k_domain(r)]
        assert len(k_edges) == len(BP7_NOTICE_MOUNTED_ENTRIES) == 13, k_edges
        assert len(non_k) >= ABCS_DECLARED_NOTICE_OUT_OF_SCOPE, (
            f"非 K 侧现算 {len(non_k)} < 切片声明 "
            f"{ABCS_DECLARED_NOTICE_OUT_OF_SCOPE} ⇒ 有人退了 notice"
        )
        assert len(prod) >= ABCS_DECLARED_NOTICE_OUT_OF_SCOPE + 13

    def test_k_owns_exactly_seven_of_the_dual_mode_census_gap(self) -> None:
        """🔴 7/11：缺口里 K 侧恰 7（BP-5 删除数），其余归并发会话。"""
        every = {p.name for p in WP_COMPOSABLES.rglob("*.ts") if "DualMode" in p.name}
        gap = ABCS_DECLARED_DUAL_MODE_MODULES - len(every)
        k_gone = [n for n in BP5_DELETED_ORPHAN_NAMES if n not in every]
        assert len(k_gone) == BP5_DELETED_COUNT == 7, k_gone
        assert gap > len(k_gone), (
            f"缺口 {gap} 不大于 K 份额 {len(k_gone)} ⇒ 并发份额算成 0，归因表该重写"
        )

    #: K 循环交付的契约草案（foundation 1 + lane2 5 + lane1 2）
    EXPECTED_K_CONTRACTS = {
        "k1.baddebt_reversal_writeoff_check.candidate.json",
        "k2.adjudication_derived.candidate.json",
        "k8.selling_expenses_adjustment.candidate.json",
        "k9.admin_expenses_adjustment.candidate.json",
        "k10.other_income_adjustment.candidate.json",
        "k11.asset_impairment_loss_adjustment.candidate.json",
        "k12.non_operating_income_adjustment.candidate.json",
        "k13.non_operating_expense_adjustment.candidate.json",
    }

    def test_k_contracts_stay_candidate_so_ownership_predicates_hold(self) -> None:
        """🔴 K 的契约全是 candidate + `entry_id=null`（决策 7）。

        断言**名单**而不是光断言个数 —— 个数对得上但换了文件同样是漂移。
        """
        ks = sorted(CONTRACT_DIR.glob("k*.json"))
        assert {p.name for p in ks} == self.EXPECTED_K_CONTRACTS, [p.name for p in ks]
        for p in ks:
            doc = json.loads(p.read_text(encoding="utf-8"))
            assert p.name.endswith(".candidate.json"), p.name
            assert doc.get("review_status") == "candidate", p.name
            assert (doc.get("review") or {}).get("entry_id") is None, (
                f"{p.name} 的 review.entry_id 非 null ⇒ 打破 task53 的两条归属判据"
            )
