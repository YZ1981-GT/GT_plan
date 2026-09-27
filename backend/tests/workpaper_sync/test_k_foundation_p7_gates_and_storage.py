# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 1 Task 14 + 17：门控 / notice / localStorage。

spec: k-cycle-sync-foundation-and-first-canary
Task 14: KC-14 + KC-15 门控与 notice 判据
Task 17: KC-18 localStorage 分类 + step 5 范围界定
Property: KF-P35, KF-P36, KF-P39

（Task 15 的 KC-16 derived_total 双正则已在
 `test_k_foundation_p5_keys_and_identity.py::TestKFP37DerivedTotalDualRegex` 落地，
 因为它与键全集同源 —— 不在此重复。）

═══ 三条会让判据假红的陷阱 ═══

1. 🔴 **门控判据统一写「必须有 `v-if`」会假红 K8/K9**。它们用 D4 的
   「always-visible + disabled」范式，`disabled: !isOoAvailable` 在
   **composable 的 `modeOptions` computed** 里，宿主层命中 0。
2. 🔴 **按宿主层扫 `isOoAvailable` 会漏 K8**（宿主层 0 命中，全在 composable）。
3. 🔴 **localStorage 的两种用途必须分清**。step 5 `unify_mode_values` 只收敛
   「模式偏好」类；「列显示偏好」类（5 个 `*ColumnPrefs.ts`）**不得一并收敛**。
   J 循环 localStorage 为 0 故 step 5 不适用；**K 适用**，照抄 J 会漏做。
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_HOSTS_GAINED_PERSISTENCE,
    BP5_HOSTS_PREFIX_CONVERGED,
    BP7_NOTICE_MOUNTED_ENTRIES,
    bp5_expected_localstorage_files,
    bp5_expected_mode_pref_files,
    BP5_DELETED_COUNT,
    BP5_DELETED_ORPHAN_ENTRIES,
    BP5_DELETED_ORPHAN_NAMES,
    BP5_DUALMODE_ENTRIES_REMAINING,
    BP5_INDEXES,
    BP5_LOCALSTORAGE_FILES_BASELINE,
    BP5_MODE_PREF_FILES_BASELINE,
    BP6_INDEXES,
    FRONTEND,
    K_HOSTS,
    K_INDEXES,
    cached_text,
    dual_mode_path,
    host_path,
    k_domain_files,
    strip_comments,
)

NOTICE_COMPONENT_NAME = "GtEntrySyncCapabilityNotice"
NOTICE_MODULE_NAME = "workpaperEntrySyncNotice"


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def all_frontend() -> list[pathlib.Path]:
    return [
        p for p in FRONTEND.rglob("*")
        if p.is_file()
        and p.suffix in (".ts", ".vue")
        and "__tests__" not in p.as_posix()
    ]


# ════════════════════════════════════════════════════════════════════════════
# Task 14 / KF-P35：BP-7 notice 从零补
# ════════════════════════════════════════════════════════════════════════════
class TestKFP35NoticeSymbols:
    """🔴 KC-14：判据必须写明用组件名还是模块名（两个口径都对，符号不同）。"""

    #: 🔴 已挂 notice 的 entry（逐条推进 —— **现已全集**）。
    #: K10 = foundation canary（Task 26）；K8/K9/K11/K12/K13 = lane 2（Task 6）；
    #: K1~K7 = lane 1（Task 8）⇒ BP-7 在 K 循环**全部兑现**。
    MOUNTED_ENTRIES = BP7_NOTICE_MOUNTED_ENTRIES

    def test_unmounted_hosts_have_neither_symbol(self) -> None:
        """🔴 BP-7 的未兑现部分：未挂载的 12 宿主两符号都是 0。

        分型判据：`MOUNTED_ENTRIES` 里的已挂，其余仍未挂。挂一条就挪进清单 ——
        不是放宽判据，是把「13 宿主全未挂」改成逐条推进的可复算清单。
        """
        for n in K_INDEXES:
            if n in self.MOUNTED_ENTRIES:
                continue
            src = strip_comments(cached_text(host_path(n)))
            for sym in (NOTICE_COMPONENT_NAME, NOTICE_MODULE_NAME):
                assert sym not in src, (
                    f"{K_HOSTS[n]} 已挂 {sym} ⇒ 须挪进 MOUNTED_ENTRIES"
                )

    def test_mounted_hosts_use_the_component_with_entry_id(self) -> None:
        """🔴 已挂载的宿主按 KC-14 口径用**组件名** + `entry-id` 绑定。

        守卫正则（`docs/operations/evidence/suite-triage/ac14-honest-mode-notice.md`）
        要求 `entry-id` 紧邻组件名 —— 中间插 `v-if` 会让平台守卫失配。
        """
        for n in self.MOUNTED_ENTRIES:
            src = cached_text(host_path(n))
            assert NOTICE_COMPONENT_NAME in src, (
                f"{K_HOSTS[n]} 未挂 {NOTICE_COMPONENT_NAME}"
            )
            # import 存在
            assert re.search(
                rf"import\s+{NOTICE_COMPONENT_NAME}\s+from", src
            ), f"{K_HOSTS[n]} 缺 {NOTICE_COMPONENT_NAME} 的 import"
            # 模板里 entry-id 紧邻组件名
            m = re.search(
                rf"<{NOTICE_COMPONENT_NAME}\s+entry-id=\"([^\"]+)\"\s*/?>", src
            )
            assert m, (
                f"{K_HOSTS[n]}: `<{NOTICE_COMPONENT_NAME} entry-id=\"...\" />` "
                "形态不符（entry-id 须紧邻组件名，中间不得插 v-if）"
            )
            # entry_id 正确（🔴 全 13 条 —— BP-7 已全部兑现）
            expected_ids = {
                1: "xlsx/gt-k1-other-receivables",
                2: "xlsx/gt-k2-other-current-assets",
                3: "xlsx/gt-k3-other-payables",
                4: "xlsx/gt-k4-other-current-liabilities",
                5: "xlsx/gt-k5-provisions",
                6: "xlsx/gt-k6-held-for-sale",
                7: "xlsx/gt-k7-deferred-income",
                8: "xlsx/gt-k8-selling-expenses",
                9: "xlsx/gt-k9-admin-expenses",
                10: "xlsx/gt-k10-other-income",
                11: "xlsx/gt-k11-asset-impairment-loss",
                12: "xlsx/gt-k12-non-operating-income",
                13: "xlsx/gt-k13-non-operating-expense",
            }
            assert m.group(1) == expected_ids[n], (
                f"{K_HOSTS[n]}: entry-id 是 {m.group(1)!r}，期望 {expected_ids[n]!r}"
            )

    def test_notice_is_inside_the_mode_toolbar_block(self) -> None:
        """notice 必须挂在模式切换工具栏块内（不是随便放）。"""
        for n in self.MOUNTED_ENTRIES:
            src = strip_comments(cached_text(host_path(n)))
            lines = src.split("\n")
            seg_line = next(
                (i for i, l in enumerate(lines) if "el-segmented" in l), None
            )
            notice_line = next(
                (i for i, l in enumerate(lines) if NOTICE_COMPONENT_NAME in l
                 and "import" not in l), None
            )
            assert seg_line is not None, f"{K_HOSTS[n]} 找不到 el-segmented"
            assert notice_line is not None, f"{K_HOSTS[n]} 模板里找不到 notice"
            assert abs(notice_line - seg_line) <= 12, (
                f"{K_HOSTS[n]}: notice 距 el-segmented {abs(notice_line-seg_line)} 行"
                " ⇒ 不在同一工具栏块内"
            )

    def test_mount_progress_is_13_of_13(self) -> None:
        """🔴 BP-7 进度 **13/13**（三份 spec 各交付自己那部分）。

        foundation 1 条（K10 canary）+ lane 2 五条（BP-6 余集）+ lane 1 七条（BP-5 全集）。
        """
        mounted = [
            n for n in K_INDEXES
            if NOTICE_COMPONENT_NAME in strip_comments(cached_text(host_path(n)))
        ]
        assert tuple(mounted) == self.MOUNTED_ENTRIES, (
            f"实际已挂 {mounted}，清单登记 {list(self.MOUNTED_ENTRIES)}"
        )
        assert len(mounted) == 13
        remaining = [n for n in K_INDEXES if n not in mounted]
        assert remaining == [], f"仍未挂载：{remaining}"
        # 三份 spec 的交付量分摊
        assert len([n for n in mounted if n == 10]) == 1
        assert len([n for n in mounted if n in BP6_INDEXES and n != 10]) == 5
        assert len([n for n in mounted if n in BP5_INDEXES]) == 7

    def test_mounted_set_is_now_the_whole_k_cycle(self) -> None:
        """🔴 已挂载集合 == **全 13 条**（BP-7 在 K 循环全部兑现）。

        推进轨迹：BP-6 全集 6 条（foundation + lane 2）→ 加上 BP-5 全集 7 条
        （lane 1 Task 8）= 13。两个 lane 的并集恰好覆盖全集，无重叠无遗漏。
        """
        assert set(self.MOUNTED_ENTRIES) == set(K_INDEXES), (
            f"已挂载 {sorted(self.MOUNTED_ENTRIES)} != 全集 {sorted(K_INDEXES)}"
        )
        assert set(BP6_INDEXES) | set(BP5_INDEXES) == set(K_INDEXES)
        assert set(BP6_INDEXES) & set(BP5_INDEXES) == set()

    def test_component_symbol_is_the_dominant_platform_caliber(
        self, all_frontend: list[pathlib.Path]
    ) -> None:
        """🔴 组件名是主流口径（全平台命中远多于模块名）⇒ 判据应选组件名。

        实测：组件名 46 / 模块名 1。两个口径都对，但组件名的分母大得多，
        故 BP-7 的挂载判据 SHALL 用**组件名**。
        """
        comp = [
            p.name for p in all_frontend
            if NOTICE_COMPONENT_NAME in strip_comments(cached_text(p))
        ]
        mod = [
            p.name for p in all_frontend
            if NOTICE_MODULE_NAME in strip_comments(cached_text(p))
        ]
        assert len(comp) >= 40, (
            f"组件名全平台命中 {len(comp)} ⇒ 分母塌了，判据选型依据失效"
        )
        assert len(mod) >= 1, (
            f"模块名全平台命中 {len(mod)} ⇒ 单一真源模块不存在了"
        )
        assert len(comp) > len(mod) * 10, (
            f"组件名 {len(comp)} 未显著多于模块名 {len(mod)}"
            " ⇒ 「选组件名」的理由须重新论证"
        )

    def test_notice_single_source_module_exists(self) -> None:
        """AC 1.4 文案真源模块与组件都存在（BP-7 有东西可挂）。"""
        sync_dir = FRONTEND / "components" / "workpaper" / "sync"
        module = sync_dir / f"{NOTICE_MODULE_NAME}.ts"
        component = sync_dir / f"{NOTICE_COMPONENT_NAME}.vue"
        assert module.exists(), f"文案真源模块不存在：{module}"
        assert component.exists(), f"提示组件不存在：{component}"


# ════════════════════════════════════════════════════════════════════════════
# Task 14 / KF-P36：两种 el-segmented 门控形态
# ════════════════════════════════════════════════════════════════════════════
class TestKFP36TwoGateForms:
    """🔴 KC-15 / KD-6：`v-if` 二级门控 11 条 + K8/K9 的 `disabled` 在 composable。"""

    #: 用 v-if 二级门控的 11 条（K1~K7 + K10~K13）
    VIF_GATED = tuple(list(BP5_INDEXES) + [10, 11, 12, 13])
    #: 用 disabled 范式的 2 条
    DISABLED_GATED = (8, 9)

    def test_vif_gate_hits_11_hosts(self) -> None:
        total = 0
        for n in K_INDEXES:
            src = strip_comments(cached_text(host_path(n)))
            hits = len(re.findall(r'v-if="dualMode\.isOoAvailable', src))
            expected = 1 if n in self.VIF_GATED else 0
            assert hits == expected, (
                f"{K_HOSTS[n]}: v-if 门控期望 {expected} 处，实得 {hits}"
            )
            total += hits
        assert total == 11, f"v-if 门控合计期望 11，实得 {total}"

    def test_k8_k9_have_no_vif_gate(self) -> None:
        """🔴 K8/K9 宿主层 v-if 为 0 —— 统一写「必须有 v-if」会假红它们。"""
        for n in self.DISABLED_GATED:
            src = strip_comments(cached_text(host_path(n)))
            assert 'v-if="dualMode.isOoAvailable' not in src, (
                f"{K_HOSTS[n]} 有 v-if 门控 ⇒ KC-15 的二分支前提变了"
            )

    def test_k8_k9_disabled_is_in_composable_mode_options(self) -> None:
        """🔴 `disabled: !isOoAvailable` 在 composable 的 `modeOptions` computed 里。

        按形态定位，不写行号。
        """
        for n in self.DISABLED_GATED:
            p = dual_mode_path(n)
            src = strip_comments(cached_text(p))
            assert re.search(r"disabled:\s*!isOoAvailable", src), (
                f"{p.name}: 找不到 `disabled: !isOoAvailable` ⇒ D4 范式登记须更新"
            )
            assert "modeOptions" in src, (
                f"{p.name}: 找不到 modeOptions ⇒ disabled 的落点说明失效"
            )

    def test_two_branch_criterion_covers_all_13(self) -> None:
        """二分支判据：「有 v-if」**或**「composable 里有 disabled」⇒ 13/13 通过。

        🔴 BP-5 删掉 7 个 orphan composable 后，那 7 条只剩宿主一侧可查 ——
        它们的门控本来就在**宿主内联的 IIFE** 里（这正是 BP-5 的形态），
        所以判据对它们只看宿主，不再去读已不存在的 composable。
        """
        uncovered: list[int] = []
        for n in K_INDEXES:
            host_src = strip_comments(cached_text(host_path(n)))
            has_vif = 'v-if="dualMode.isOoAvailable' in host_src
            if n in BP5_DELETED_ORPHAN_ENTRIES:
                # 内联形态：门控只可能在宿主里（v-if 或宿主内的 disabled）
                has_disabled = bool(
                    re.search(r"disabled:\s*!isOoAvailable", host_src)
                )
            else:
                cm_src = strip_comments(cached_text(dual_mode_path(n)))
                has_disabled = bool(
                    re.search(r"disabled:\s*!isOoAvailable", cm_src)
                )
            if not (has_vif or has_disabled):
                uncovered.append(n)
        assert uncovered == [], (
            f"二分支判据未覆盖 K{uncovered} ⇒ 还有第三种门控形态"
        )

    def test_single_branch_criterion_would_falsely_red_k8_k9(self) -> None:
        """反证：统一写「必须有 v-if」的假红集合恰好是 {K8, K9}。"""
        failing: list[int] = []
        for n in K_INDEXES:
            src = strip_comments(cached_text(host_path(n)))
            if 'v-if="dualMode.isOoAvailable' not in src:
                failing.append(n)
        assert failing == list(self.DISABLED_GATED), (
            f"单分支判据的假红集合应恰好是 {list(self.DISABLED_GATED)}，实得 {failing}"
            " —— 这条反证保证二分支不是多余的"
        )

    def test_is_oo_available_in_host_layer_would_miss_k8(self) -> None:
        """🔴 按宿主层扫 `isOoAvailable` 会漏 K8（命中 0，全在 composable）。"""
        host_hits = {}
        for n in K_INDEXES:
            src = strip_comments(cached_text(host_path(n)))
            host_hits[n] = len(re.findall(r"\bisOoAvailable\b", src))
        assert host_hits[8] == 0, (
            f"K8 宿主层 isOoAvailable 命中 {host_hits[8]} ⇒ 「全在 composable」登记须改"
        )
        # composable 侧非 0
        cm_src = strip_comments(cached_text(dual_mode_path(8)))
        assert len(re.findall(r"\bisOoAvailable\b", cm_src)) > 0, (
            "K8 的 composable 侧也找不到 isOoAvailable ⇒ 符号来源不明"
        )

    def test_el_segmented_is_exactly_one_after_strip(self) -> None:
        """🔴 KD-7：剥注释前多数宿主 2 处（第二处在块注释里），剥后 13/13 恒 1 处。"""
        for n in K_INDEXES:
            raw = cached_text(host_path(n))
            stripped = strip_comments(raw)
            after = len(re.findall(r"el-segmented", stripped))
            assert after == 1, (
                f"{K_HOSTS[n]}: 剥注释后 el-segmented 期望 1 处，实得 {after}"
            )

    def test_most_hosts_have_a_commented_second_segmented(self) -> None:
        """剥注释前多数宿主有 2 处（证明剥注释不是多余步骤）。"""
        two_before = 0
        for n in K_INDEXES:
            raw = cached_text(host_path(n))
            if len(re.findall(r"el-segmented", raw)) == 2:
                two_before += 1
        assert two_before >= 10, (
            f"剥注释前有 2 处的宿主只有 {two_before} 个"
            " ⇒ 「第二处在块注释里」的登记须复核"
        )


# ════════════════════════════════════════════════════════════════════════════
# Task 17 / KF-P39：localStorage 三分类与 step 5 范围界定
# ════════════════════════════════════════════════════════════════════════════
class TestKFP39LocalStorageClassification:
    """🔴 KC-18：两种用途须分清，step 5 只收敛模式偏好类。"""

    #: 列显示偏好类 —— **不得一并收敛**
    COLUMN_PREFS_FILES = {
        "useK1DetailColumnPrefs.ts",
        "useK4DetailColumnPrefs.ts",
        "useK10DetailColumnPrefs.ts",
        "useK11DetailColumnPrefs.ts",
        "useK10GrantColumnPrefs.ts",
    }
    #: 其他用途（逐处判定）
    OTHER_FILES = {
        "K6TabDetail.vue",
        "K7TabDeferredCheck.vue",
        "K8TabSellingCheck.vue",
        "K9TabAdminCheck.vue",
        "K9TabDetail.vue",
    }
    #: 宿主层撞车的 3 条（与 composable 同值）
    COLLIDING_HOSTS = {
        "GtK4OtherCurrentLiabilities.vue",
        "GtK5Provisions.vue",
        "GtK6HeldForSale.vue",
    }

    @staticmethod
    def _ls_files(k_files: list[pathlib.Path]) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in k_files:
            src = strip_comments(cached_text(p))
            c = len(re.findall(r"\blocalStorage\b", src))
            if c:
                out[p.name] = c
        return out

    def test_localstorage_files_follow_the_deletion_ledger(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 现算 == 基线 26 − BP-5 删掉的 7 个 orphan。

        7 个 `useK{n}DualMode.ts`（n=1..7）各有 localStorage 读写，删文件即减 7。
        基线是 append-only 的改造前快照，不回填。
        """
        got = self._ls_files(k_files)
        expected = bp5_expected_localstorage_files()
        assert BP5_LOCALSTORAGE_FILES_BASELINE == 26, "基线被篡改"
        assert len(got) == expected, (
            f"localStorage 文件数：基线 26 − 已删 {BP5_DELETED_COUNT} "
            f"+ 新增持久化 {len(BP5_HOSTS_GAINED_PERSISTENCE)} = {expected}，"
            f"实得 {len(got)}"
        )

    def test_three_categories_still_partition_the_remainder(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """三分类互斥且并集 == 现算总数（列偏好类与其他类一个未动）。"""
        got = set(self._ls_files(k_files))
        mode_pref = got - self.COLUMN_PREFS_FILES - self.OTHER_FILES
        assert self.COLUMN_PREFS_FILES <= got, (
            f"列偏好类缺 {sorted(self.COLUMN_PREFS_FILES - got)} ⇒ 删除越界"
        )
        assert self.OTHER_FILES <= got, (
            f"其他类缺 {sorted(self.OTHER_FILES - got)} ⇒ 删除越界"
        )
        expected_mode = bp5_expected_mode_pref_files()
        assert len(mode_pref) == expected_mode, (
            f"模式偏好类：基线 16 − 已删 {BP5_DELETED_COUNT} "
            f"+ 新增 {len(BP5_HOSTS_GAINED_PERSISTENCE)} = {expected_mode}，"
            f"实得 {len(mode_pref)}\n{sorted(mode_pref)}"
        )
        assert (
            len(mode_pref) + len(self.COLUMN_PREFS_FILES) + len(self.OTHER_FILES)
            == len(got)
        )

    def test_mode_pref_is_remaining_composables_plus_3_hosts(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """模式偏好类 = 剩余 6 个 `useK{n}DualMode.ts` + 3 个撞车宿主。

        🔴 基线是 13 + 3 = 16；BP-5 删掉 7 个 composable ⇒ 6 + 3 = 9。
        撞车宿主（K4/K5/K6）**一个没少** —— 它们是 lane 1 Task 7 要收敛的目标，
        不在 Task 5 的删除范围里。
        """
        got = set(self._ls_files(k_files))
        mode_pref = got - self.COLUMN_PREFS_FILES - self.OTHER_FILES
        composables = {f for f in mode_pref if "DualMode" in f}
        hosts = {f for f in mode_pref if f.startswith("GtK")}
        expected_cm = 13 - BP5_DELETED_COUNT
        assert len(composables) == expected_cm == 6, (
            f"DualMode composable 期望 {expected_cm}，实得 {sorted(composables)}"
        )
        assert composables == {
            f"useK{n}DualMode.ts" for n in BP5_DUALMODE_ENTRIES_REMAINING
        }, f"剩余 composable 集合 {sorted(composables)}"
        # 🔴 Task 7 后宿主侧从 3 个（撞车组）变成 **7 个**（全 lane 都持久化了）
        expected_hosts = {K_HOSTS[n] for n in BP5_INDEXES}
        assert hosts == expected_hosts, (
            f"宿主侧期望 7 个（Task 7 统一目标态）{sorted(expected_hosts)}，"
            f"实得 {sorted(hosts)}"
        )
        assert self.COLLIDING_HOSTS <= hosts, (
            "原撞车 3 个宿主应仍在（它们改的是前缀不是删持久化）"
        )
        assert composables | hosts == mode_pref

    def test_deleted_orphans_no_longer_carry_localstorage(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 两侧都验：删掉的 7 个不在 localStorage 清册里。"""
        got = set(self._ls_files(k_files))
        for name in BP5_DELETED_ORPHAN_NAMES:
            assert name not in got, f"{name} 仍在 localStorage 清册里 ⇒ 删除未生效"

    def test_step5_must_not_touch_column_prefs(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 列偏好类是**另一用途**，不得一并收敛。"""
        for name in self.COLUMN_PREFS_FILES:
            p = next((x for x in k_files if x.name == name), None)
            assert p is not None, f"{name} 不存在"
            src = strip_comments(cached_text(p))
            # 它们不该带 dual-mode 前缀
            assert not re.search(r"['\"`]k\d+-dual-mode:", src), (
                f"{name} 带 dual-mode 前缀 ⇒ 分类判据须复核"
            )
            assert "localStorage" in src

    def test_three_colliding_hosts_share_prefix_with_their_composable(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 K4/K5/K6 宿主内联与 orphan composable 曾**同值撞车**。

        🔴 BP-5 删掉 orphan 后**撞车自动消解了一半** —— 宿主侧的 legacy 前缀仍在，
        那是 lane 1 Task 7 的收敛目标。判据改两侧：
          ① 宿主侧前缀**仍在**（Task 7 未做完，不许假绿）
          ② orphan 侧**已删**（撞车的另一半没了）
        """
        # 🔴 撞车**已彻底消解**（两侧都动过）：
        #   · orphan 侧：BP-5 删除（Task 5）
        #   · 宿主侧：legacy 前缀收敛到统一键（Task 7）
        # 判据翻面为「两侧都不在了」+「注释里留着迁移来源」。
        for n in (4, 5, 6):
            host_src = strip_comments(cached_text(host_path(n)))
            prefix = f"k{n}-dual-mode:"
            assert prefix not in host_src, (
                f"{K_HOSTS[n]}: 代码里仍有 legacy 前缀 {prefix!r} ⇒ Task 7 未收敛"
            )
            assert "workpaperSyncModeKey" in host_src, (
                f"{K_HOSTS[n]}: 未接统一键"
            )
            # 注释里应留迁移来源（可追溯）
            assert prefix in cached_text(host_path(n)), (
                f"{K_HOSTS[n]}: 注释里没留旧前缀，迁移来源不可追溯"
            )
            assert not dual_mode_path(n).exists(), (
                f"useK{n}DualMode.ts 仍在 ⇒ BP-5 删除未生效"
            )

    def test_four_twin_hosts_have_no_localstorage(self) -> None:
        """🔴 K1/K2/K3/K7 宿主内联**无** localStorage，而其 orphan 有。

        ⇒ 「模式偏好是否持久化」在 K 循环内部不一致，改线须明确目标态。
        """
        # 🔴 目标态**已裁定并落实**：Task 7 选「都持久化」⇒ 这 4 条**新增**了能力。
        # 原登记「宿主无 localStorage」是改造前事实，判据翻面为「现在有了 + 注释留档」。
        for n in (1, 2, 3, 7):
            host_src = strip_comments(cached_text(host_path(n)))
            assert "localStorage" in host_src, (
                f"{K_HOSTS[n]} 无 localStorage ⇒ Task 7 的「都持久化」未落实"
            )
            assert "workpaperSyncModeKey" in host_src, f"{K_HOSTS[n]} 未接统一键"
            assert "原先没有持久化" in cached_text(host_path(n)), (
                f"{K_HOSTS[n]}: 未登记「新增持久化」这个目标态裁定"
            )
            assert not dual_mode_path(n).exists(), (
                f"useK{n}DualMode.ts 仍在 ⇒ BP-5 删除未生效"
            )

    def test_collision_3_plus_no_persist_4_equals_7(self) -> None:
        """算术自检：撞车 3 + 无持久化 4 == 7（BP-5 全集，**改造前**分型）。

        🔴 Task 7 后两组都持久化了 ⇒ 现算全 7 条有 localStorage。分型仍要留档
        （它决定了两组的**改法不同**：一组改前缀、一组新增能力），
        判据改为「分型集合定义自洽 + 现算全部持久化 + 两组注释各留其来源」。
        """
        assert len(BP5_HOSTS_PREFIX_CONVERGED) == 3
        assert len(BP5_HOSTS_GAINED_PERSISTENCE) == 4
        assert set(BP5_HOSTS_PREFIX_CONVERGED) & set(
            BP5_HOSTS_GAINED_PERSISTENCE
        ) == set()
        assert set(BP5_HOSTS_PREFIX_CONVERGED) | set(
            BP5_HOSTS_GAINED_PERSISTENCE
        ) == set(BP5_INDEXES)
        for n in BP5_INDEXES:
            host_src = strip_comments(cached_text(host_path(n)))
            assert "localStorage" in host_src, (
                f"{K_HOSTS[n]}: Task 7 后应都持久化"
            )
        # 两组的**注释来源**不同（改法不同的留档）
        for n in BP5_HOSTS_PREFIX_CONVERGED:
            assert "撞车" in cached_text(host_path(n))
        for n in BP5_HOSTS_GAINED_PERSISTENCE:
            assert "原先没有持久化" in cached_text(host_path(n))

    def test_j_cycle_zero_conclusion_does_not_apply_to_k(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 J 循环 localStorage 为 0 故 step 5 不适用；K 适用，照抄会漏做。"""
        got = self._ls_files(k_files)
        assert len(got) > 0, (
            "K 域 localStorage 为 0 ⇒ 与 J 相同，step 5 不适用，本条登记须撤"
        )
        assert len(got) == bp5_expected_localstorage_files()

    #: 🔴 已完成 localStorage 收敛的 entry（逐条推进 —— **现已全集**）。
    #: K10 = foundation canary（Task 26）；K8/K9/K11/K12/K13 = lane 2（Task 5）；
    #: K1~K7 = lane 1（Task 7：撞车 3 条改前缀 + 无持久化 4 条新增能力）。
    CONVERGED_ENTRIES = tuple(range(1, 14))

    def test_unconverged_composables_still_have_legacy_prefix(self) -> None:
        """未收敛的 12 个 composable 仍带 `k{n}-dual-mode:`（收敛目标的分母）。

        🔴 分型判据：`CONVERGED_ENTRIES` 里的已走统一键，其余仍是 legacy 前缀。
        收敛一条就把它挪进 `CONVERGED_ENTRIES` —— 不是放宽判据，是把
        「全部未收敛」这条基线改成「逐条推进」的可复算清单。
        """
        # 🔴 **未收敛集合现已为空**（13/13 全收敛）。判据翻面为两条：
        #   ① 未收敛集合确实为空
        #   ② 全 13 条的**载体侧**（composable 或宿主）都接了统一键、都无 legacy 前缀
        unconverged = [n for n in K_INDEXES if n not in self.CONVERGED_ENTRIES]
        assert unconverged == [], f"仍有未收敛的 entry：{unconverged}"
        for n in K_INDEXES:
            carrier = (
                dual_mode_path(n) if dual_mode_path(n).exists() else host_path(n)
            )
            src = strip_comments(cached_text(carrier))
            assert "workpaperSyncModeKey" in src, (
                f"{carrier.name}: 未接统一键"
            )
            assert re.search(r"['\"]k\d+-dual-mode:", src) is None, (
                f"{carrier.name}: 代码里仍有 legacy 前缀"
            )

    def test_converged_carriers_use_the_unified_key_generator(self) -> None:
        """🔴 已收敛的**载体**走 `workpaperSyncModeKey()` 生成统一键。

        🔴 载体分两层：6 条在 `useK{n}DualMode.ts`（BP-6 组），
        7 条在宿主内联 IIFE（BP-5 组，其 composable 已被 Task 5 删除）。
        判据是「用生成器」而不是「含前缀字面量」—— 前缀常量只该在
        `workpaperSyncModeStorage.ts` 一处，调用方不得内联第二份
        （`usePilotBridgeAdapter.ts` 内联过，已被登记为 duplicate writer 缺陷）。
        """
        for n in self.CONVERGED_ENTRIES:
            carrier = (
                dual_mode_path(n) if dual_mode_path(n).exists() else host_path(n)
            )
            src = strip_comments(cached_text(carrier))
            assert "workpaperSyncModeKey" in src, (
                f"{carrier.name} 未用统一键生成器 ⇒ 收敛不完整"
            )
            assert f"k{n}-dual-mode:" not in src, (
                f"{carrier.name} 仍有 legacy 前缀字面量 ⇒ 收敛不彻底"
            )
            assert "WP_SYNC_MODE_KEY_PREFIX" not in src, (
                f"{carrier.name} 内联了前缀常量 ⇒ 第二份真源"
                "（应只调 workpaperSyncModeKey()）"
            )

    def test_converged_carriers_migrate_legacy_keys(self) -> None:
        """已收敛的**载体**调 `migrateWorkpaperSyncMode()` 消费旧键。

        不迁移会让存量用户的偏好静默丢失（旧键留在 localStorage 里没人读）。
        🔴 对 K1/K2/K3/K7（原无持久化）这个调用是幂等空操作，但仍要有 ——
        它防御更早版本可能遗留的键形态。
        """
        for n in self.CONVERGED_ENTRIES:
            carrier = (
                dual_mode_path(n) if dual_mode_path(n).exists() else host_path(n)
            )
            src = strip_comments(cached_text(carrier))
            assert "migrateWorkpaperSyncMode" in src, (
                f"{carrier.name} 未调迁移函数 ⇒ 存量偏好会静默丢失"
            )

    def test_convergence_progress_is_13_of_13(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 收敛进度 **13/13**（两 lane 各交付自己那半）。"""
        # 🔴 收敛进度 **13/13**：载体分两层 —— 6 个 composable（BP-6 组）
        # + 7 个宿主内联（BP-5 组，其 composable 已删）。按载体现算。
        using_generator: list[int] = []
        for n in K_INDEXES:
            carrier = (
                dual_mode_path(n) if dual_mode_path(n).exists() else host_path(n)
            )
            if "workpaperSyncModeKey" in strip_comments(cached_text(carrier)):
                using_generator.append(n)
        assert tuple(using_generator) == self.CONVERGED_ENTRIES, (
            f"实际已收敛 {using_generator}，清单登记 {list(self.CONVERGED_ENTRIES)}"
        )
        assert len(using_generator) == 13
        # 🔴 载体分层现算：6 条在 composable、7 条在宿主
        on_composable = [n for n in using_generator if dual_mode_path(n).exists()]
        on_host = [n for n in using_generator if not dual_mode_path(n).exists()]
        assert sorted(on_composable) == sorted(BP6_INDEXES), on_composable
        assert sorted(on_host) == sorted(BP5_INDEXES), on_host

    def test_converged_set_is_now_the_whole_k_cycle(self) -> None:
        """🔴 已收敛集合 == **全 13 条**（两 lane 各交付自己那半）。"""
        assert set(self.CONVERGED_ENTRIES) == set(K_INDEXES)
        assert set(BP6_INDEXES) | set(BP5_INDEXES) == set(K_INDEXES)
