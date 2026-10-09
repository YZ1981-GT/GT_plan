# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 1 Task 4~6：载体族 / 端点扫描 / TB 发布门。

spec: k-cycle-sync-foundation-and-first-canary
Task 4: KC-2 载体族二分支判据
Task 5: KC-3 端点扫描器（认反引号）+ 变异反证
Task 6: KC-4 TB 发布门四层载体清册
Property: KF-P9, KF-P10, KF-P11, KF-P12, KF-P13, KF-P14, KF-P15

═══ 三条会让判据假红的陷阱（都已踩过）═══

1. 🔴 **端点正则不认反引号** ⇒ 9 处 `onlyoffice-config` 直调漏登记成 0
   （slice 的 `endpoint_scan_recipe` 明文记录首轮实测即因此打红）
2. 🔴 **载体族按单一分支写** ⇒ K5 假红（它走 `useChecklistPersistence`，
   裸端点 0 不是缺陷，是 `shared_platform_persistence_adapter` 族）
3. 🔴 **TB 发布门按单一载体层写** ⇒ 必漏（分布在四层，含唯一在宿主层的 K6）
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_HEALTH_AFTER_HOST_CONVERGENCE,
    BP5_DELETED_COUNT,
    BP5_DELETED_ORPHAN_ENTRIES,
    BP5_HEALTH_AFTER_LANE2_CONVERGENCE,
    BP5_HEALTH_AFTER_ORPHAN_DELETION,
    BP5_HEALTH_DESIGN_BASELINE,
    DATA,
    K_HOSTS,
    K_INDEXES,
    ROOT,
    WP_COMPONENTS,
    WP_COMPOSABLES,
    BP5_INDEXES,
    BP6_INDEXES,
    cached_text,
    dual_mode_path,
    endpoint_index,
    form_data_path,
    host_path,
    k_domain_files,
    line_count,
    line_count_splitlines,
    literal_hits,
    strip_comments,
)

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"

EP_HEALTH = "/api/workpapers/onlyoffice/health"
EP_CONFIG = "/api/workpapers/{X}/sheets/{X}/onlyoffice-config"
EP_CHECKLIST = "/api/workpapers/{X}/checklist-responses"
EP_PUBLISH = "/api/workpapers/{X}/audit-determination/publish-to-tb"
EP_AI_TEXT = "/api/workpapers/{X}/ai/generate-text"
EP_TB = "/api/projects/{X}/trial-balance"
EP_DISCLOSURE = "/api/projects/{X}/disclosure-notes/sync-from-workpaper"


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(MANIFEST_SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def endpoints(k_files: list[pathlib.Path]):
    return endpoint_index(k_files, recognize_backtick=True)


# ════════════════════════════════════════════════════════════════════════════
# Task 5 / KF-P11~P14：端点扫描器
# ════════════════════════════════════════════════════════════════════════════
class TestKFP11BacktickRecognition:
    """🔴 KC-3：正则必须认反引号，否则 config 直调漏成 0。"""

    def test_config_endpoint_hits_6_files_6_sites(self, endpoints) -> None:
        """端点口径：6 文件 / 6 处真实端点直调（每文件恰 1 处）。"""
        by_file, hits = endpoints
        assert len(by_file.get(EP_CONFIG, set())) == 6, (
            f"config 文件数：期望 6，实得 {len(by_file.get(EP_CONFIG, set()))}"
        )
        assert hits.get(EP_CONFIG, 0) == 6, (
            f"config 端点处数：期望 6（每文件 1 处），实得 {hits.get(EP_CONFIG, 0)}"
        )

    def test_substring_caliber_overcounts_by_3(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 口径反证：子串 `onlyoffice-config` 命中 9 处 vs 端点口径 6 处。

        多出的 3 处是 `throw new Error('empty onlyoffice-config')` 的**错误消息
        字符串**（K8 / K9 / K11 各 1），不是端点直调。design.md 的「9 处」是
        子串口径；需要收口的**端点直调**是 6 处。两个口径都对，混用会算错。
        """
        substring_total = 0
        error_msg_files: list[str] = []
        for n in BP6_INDEXES:
            p = dual_mode_path(n)
            src = strip_comments(cached_text(p))
            c = len(re.findall(r"onlyoffice-config", src))
            substring_total += c
            if c == 2:
                assert re.search(r"empty onlyoffice-config", src), (
                    f"{p.name}: 2 处子串命中但第二处不是错误消息 ⇒ 口径解释失效"
                )
                error_msg_files.append(p.name)
        assert substring_total == 9, (
            f"子串口径合计：期望 9，实得 {substring_total}"
        )
        assert len(error_msg_files) == 3, (
            f"带错误消息的文件应为 3 个（K8/K9/K11），实得 {error_msg_files}"
        )
        assert substring_total - 6 == 3, "子串口径比端点口径多 3 处"

    def test_config_drops_to_zero_without_backtick(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 变异反证：只认单/双引号时 config 命中降为 0。"""
        by_file_nb, _ = endpoint_index(k_files, recognize_backtick=False)
        assert by_file_nb.get(EP_CONFIG, set()) == set(), (
            "不认反引号时 config 仍有命中 ⇒ 反证失效，判据无法证明反引号是必需的"
        )

    def test_config_literals_are_all_template_strings(self) -> None:
        """8+1 处 config 全是反引号模板字面量形态。"""
        rx = re.compile(r"`[^`]*onlyoffice-config[^`]*`")
        for n in BP6_INDEXES:
            p = dual_mode_path(n)
            src = strip_comments(cached_text(p))
            if "onlyoffice-config" not in src:
                continue
            assert rx.search(src), (
                f"{p.name}: config 不是反引号模板字面量形态"
            )


class TestKFP12EndpointUniverse:
    """K 域端点全集与 Top 7 命中数。"""

    #: 🔴 已收敛到单源探针 `sync/onlyOfficeHealth.ts` 的 entry（逐条推进）。
    #: K10 = foundation canary（Task 26）；K8/K9/K11/K12/K13 = lane 2（Task 4）。
    #: 余下 K1~K7 的 health 直调分两处（orphan composable 7 + 宿主内联 IIFE 7），归 lane 1。
    HEALTH_CONVERGED_ENTRIES = (8, 9, 10, 11, 12, 13)

    def test_health_hits_follow_the_two_ledgers(self, endpoints) -> None:
        """health 直调走**两本账**：BP-6 收敛账 + BP-5 删除账。

        🔴 三段式（顺序要紧）：
          ① design 基线 = 7 宿主 + 13 composable = **20**
          ② lane 2 收敛 6 个 live composable ⇒ **14**
          ③ lane 1 删 7 个 orphan ⇒ **7**（只剩宿主内联）
          ④ lane 1 Task 7 宿主改走 bridge ⇒ **0**
        design 写的「20 降为 13」是 ①→② 未发生时的预期；实际 lane 2 先做。
        """
        by_file, hits = endpoints
        # 🔴 第 ④ 段已达成：7 宿主也改走探针 ⇒ K 域 health 直调 **0**
        expected = BP5_HEALTH_AFTER_HOST_CONVERGENCE
        assert expected == 0, "账本第 ④ 段常量被改"
        assert (
            BP5_HEALTH_DESIGN_BASELINE
            - len(self.HEALTH_CONVERGED_ENTRIES)
            - BP5_DELETED_COUNT
            == BP5_HEALTH_AFTER_ORPHAN_DELETION
            == 7
        ), "第 ③ 段账本不自洽"
        assert BP5_HEALTH_AFTER_ORPHAN_DELETION - 7 == expected, (
            "第 ③→④ 段：7 宿主收敛后应归零"
        )
        assert len(by_file.get(EP_HEALTH, set())) == expected, (
            f"health 直调文件数期望 {expected}，实得 "
            f"{len(by_file.get(EP_HEALTH, set()))}"
        )
        assert hits.get(EP_HEALTH, 0) == expected

    def test_the_intermediate_value_after_lane2_was_14(self) -> None:
        """🔴 账本留档：lane 2 收敛完但 lane 1 未删时是 14（= 7 宿主 + 7 orphan）。"""
        assert (
            BP5_HEALTH_DESIGN_BASELINE - len(self.HEALTH_CONVERGED_ENTRIES)
            == BP5_HEALTH_AFTER_LANE2_CONVERGENCE
            == 14
        )

    def test_converged_composables_use_the_single_source_probe(self) -> None:
        """🔴 已收敛的 composable 走 `fetchOnlyOfficeHealthy`，不再自己打端点。"""
        for n in self.HEALTH_CONVERGED_ENTRIES:
            p = dual_mode_path(n)
            assert p.exists(), (
                f"useK{n}DualMode.ts 不存在 —— 它属 BP-6 组不该被 BP-5 删除波及"
            )
            src = strip_comments(cached_text(p))
            assert "fetchOnlyOfficeHealthy" in src, (
                f"useK{n}DualMode.ts 未用单源探针 ⇒ 收敛不完整"
            )
            assert "onlyoffice/health" not in src, (
                f"useK{n}DualMode.ts 仍直调 health 端点 ⇒ 收敛不彻底"
            )

    def test_deleted_orphans_are_gone_not_converged(self) -> None:
        """🔴 区分「删掉」与「收敛」：BP-5 的 7 个是**删除**，文件不该还在。"""
        for n in BP5_DELETED_ORPHAN_ENTRIES:
            assert not dual_mode_path(n).exists(), (
                f"useK{n}DualMode.ts 仍在 ⇒ BP-5 删除未生效"
            )
        assert set(BP5_DELETED_ORPHAN_ENTRIES) & set(
            self.HEALTH_CONVERGED_ENTRIES
        ) == set(), "删除集合与收敛集合相交 ⇒ 两本账撞了"

    def test_health_both_sides_converged_to_zero(
        self, endpoints, manifest_slice: dict
    ) -> None:
        """🔴 两侧都归零（原基线 20 = 13 composable + 7 宿主）。

        三段账：20 → 14（BP-6 收敛 6）→ 7（BP-5 删 7）→ **0**（宿主收敛 7）。
        """
        by_file, _ = endpoints
        files = by_file.get(EP_HEALTH, set())
        # 🔴 三段账全走完 ⇒ **两侧都归零**：
        #   composable 侧 = 13 − 6（BP-6 收敛）− 7（BP-5 删除）= 0
        #   宿主侧       = 7 − 7（lane 1 Task 7 改走探针）= 0
        assert files == set(), f"health 直调应全清，实得 {sorted(files)}"
        assert 13 - len(self.HEALTH_CONVERGED_ENTRIES) - BP5_DELETED_COUNT == 0
        assert BP5_HEALTH_AFTER_ORPHAN_DELETION - 7 == (
            BP5_HEALTH_AFTER_HOST_CONVERGENCE
        )
        # 与 slice 双向吻合（宿主内联的**载体形态**未变，只是端点换了出口）
        s = manifest_slice["honest_adjudication_summary"]
        assert s["hosts_with_inlined_iife_dual_mode"] == 7
        # 与 slice 双向吻合（宿主侧 7 处未动）
        s = manifest_slice["honest_adjudication_summary"]
        assert s["hosts_with_inlined_iife_dual_mode"] == 7

    def test_the_seven_hosts_that_had_health_are_now_on_the_probe(
        self, endpoints
    ) -> None:
        """🔴 曾直调 health 的 7 宿主（BP-5 组）现在全走单源探针。

        原判据是「直调 health 的宿主恰好是 BP-5 组」；Task 7 收敛后
        直调集合为空 ⇒ 判据翻面为「这 7 个都有探针调用且都无直调」。
        """
        by_file, _ = endpoints
        hosts = {f for f in by_file.get(EP_HEALTH, set()) if f.startswith("GtK")}
        assert hosts == set(), f"仍有宿主直调 health：{sorted(hosts)}"
        for n in BP5_INDEXES:
            src = strip_comments(cached_text(host_path(n)))
            assert "fetchOnlyOfficeHealthy" in src, (
                f"{K_HOSTS[n]}: 未改走单源探针"
            )
            assert "onlyoffice/health" not in src

    def test_top_endpoints_match_design(self, endpoints) -> None:
        """Req 3.2 的 Top 端点逐条等值。"""
        by_file, _ = endpoints
        expected = {
            EP_AI_TEXT: 47,
            EP_TB: 28,
            EP_DISCLOSURE: 26,
            # 🔴 三段账全走完：20 −6(BP-6 收敛) −7(BP-5 删除) −7(宿主收敛) = 0
            EP_HEALTH: BP5_HEALTH_AFTER_HOST_CONVERGENCE,
            # 🔴 16→17：K1-9 真双向接桥 `k1WriteoffSync.ts` 的 flushHtml 直写
            #    `/checklist-responses`（第 17 个命中文件）。登记原值 16 + 晋级增量 1。
            EP_CHECKLIST: 17,
            EP_PUBLISH: 14,
            EP_CONFIG: 6,
        }
        for ep, count in expected.items():
            actual = len(by_file.get(ep, set()))
            assert actual == count, f"{ep}: 期望 {count} 文件，实得 {actual}"


class TestKFP14EndpointAnomalies:
    """两处须登记的端点异常。"""

    def test_hardcoded_account_code_1221_in_url(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 科目码 1221 硬编码在 URL 里。"""
        hits = literal_hits(k_files, "ledger/entries/1221")
        assert hits, "硬编码科目码 1221 的端点消失了 ⇒ 登记须更新"

    def test_force_component_type_for_k1(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """K1 用 force_component_type 强制组件类型。"""
        hits = literal_hits(k_files, "force_component_type=k1-other-receivables")
        assert hits, "force_component_type 参数消失了 ⇒ 登记须更新"


# ════════════════════════════════════════════════════════════════════════════
# Task 4 / KF-P9~P10：载体族二分支
# ════════════════════════════════════════════════════════════════════════════
class TestKFP9CarrierFamilyBranching:
    """🔴 KC-2：判据必须二分支写，否则 K5 假红。"""

    def test_checklist_endpoint_hits_16_files(self, endpoints) -> None:
        """🔴 16→17：K1-9 真双向接桥 `k1WriteoffSync.ts` 新增一个命中文件（flushHtml
        直写 `/checklist-responses`）。登记原值 16 + 晋级增量 1，且增量确来自该接桥。"""
        by_file, _ = endpoints
        files = by_file.get(EP_CHECKLIST, set())
        assert len(files) == 17
        assert any("k1WriteoffSync.ts" in str(f) for f in files), (
            "17 这个增量不是来自 K1 真双向接桥 ⇒ 口径须复核"
        )

    def test_12_formdata_composables_have_2_bare_endpoints_each(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """formdata_composable_bare_endpoint 族：12 条各 2 处。"""
        family = [n for n in K_INDEXES if n != 5]
        assert len(family) == 12
        for n in family:
            p = form_data_path(n)
            assert p.exists(), f"{p.name} 不存在"
            src = strip_comments(cached_text(p))
            c = len(re.findall(r"checklist-responses", src))
            assert c == 2, f"{p.name}: 期望 2 处裸端点，实得 {c}"

    def test_k5_is_shared_adapter_family_not_a_defect(self) -> None:
        """🔴 K5 裸端点 0 / useChecklistPersistence 3 ⇒ 不是缺陷。"""
        p = form_data_path(5)
        src = strip_comments(cached_text(p))
        bare = len(re.findall(r"checklist-responses", src))
        ucp = len(re.findall(r"\buseChecklistPersistence\b", src))
        assert bare == 0, (
            f"useK5FormData.ts 裸端点应为 0，实得 {bare}"
            " —— 若非 0 则 K5 不再是共享适配器族，KC-2 的二分支前提变了"
        )
        assert ucp == 3, f"useK5FormData.ts useChecklistPersistence 期望 3，实得 {ucp}"

    def test_a_single_branch_criterion_would_falsely_red_k5(self) -> None:
        """反证：按「每条 entry 都有 checklist-responses 裸端点」判会假红 K5。"""
        failing = []
        for n in K_INDEXES:
            p = form_data_path(n)
            src = strip_comments(cached_text(p))
            if "checklist-responses" not in src:
                failing.append(n)
        assert failing == [5], (
            f"单分支判据的假红集合应恰好是 {{5}}，实得 {failing}"
            " —— 这条反证保证 KC-2 的二分支不是多余的"
        )

    def test_all_13_hosts_have_zero_bare_endpoint_and_3_ucp(self) -> None:
        """13 宿主裸端点全 0（都在 composable 层），UCP 各 3 处（13×3=39）。"""
        total_ucp = 0
        for n in K_INDEXES:
            p = host_path(n)
            src = strip_comments(cached_text(p))
            bare = len(re.findall(r"checklist-responses", src))
            ucp = len(re.findall(r"\buseChecklistPersistence\b", src))
            assert bare == 0, f"{p.name}: 宿主层裸端点应为 0，实得 {bare}"
            assert ucp == 3, f"{p.name}: UCP 期望 3，实得 {ucp}"
            total_ucp += ucp
        assert total_ucp == 39


class TestKFP10K5TabsEmitOnly:
    """K5 的 Tab 层全部只 emit('save')，由宿主收口。"""

    def test_k5_host_has_ucp_and_emit_save(self) -> None:
        p = host_path(5)
        src = strip_comments(cached_text(p))
        assert len(re.findall(r"\buseChecklistPersistence\b", src)) == 3

    def test_k5_tabs_have_no_own_endpoint(self) -> None:
        """K5 各 Tab 无自有 checklist 端点。"""
        k5_dir = WP_COMPONENTS / "k5"
        if not k5_dir.is_dir():
            pytest.skip("k5 目录不存在")
        tabs = [
            p for p in k5_dir.rglob("K5Tab*.vue")
            if "__tests__" not in p.as_posix()
        ]
        assert tabs, "K5 Tab 分母为空 ⇒ 判据空跑"
        for p in tabs:
            src = strip_comments(cached_text(p))
            assert "checklist-responses" not in src, (
                f"{p.name}: Tab 层出现自有 checklist 端点 ⇒ K5 的收口模型变了"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 6 / KF-P15：TB 发布门四层载体
# ════════════════════════════════════════════════════════════════════════════
class TestKFP15TbPublishGateFourLayers:
    """🔴 KC-4：13/13 全有，但载体分布在四层共 14 处（K5 占 2）。"""

    #: 四层归类（design.md KC-4 现算）
    EXPECTED_LAYERS = {
        "form_data": {
            "useK1FormData.ts",
            "useK3FormData.ts",
            "useK4FormData.ts",
            "useK5FormData.ts",
            "useK10FormData.ts",
        },
        "adjudication_composable": {
            "useK8Adjudication.ts",
            "useK9Adjudication.ts",
            "useK11Adjudication.ts",
        },
        "tab_adjudication": {
            "K2TabAdjudication.vue",
            "K5TabAdjudication.vue",
            "K7TabAdjudication.vue",
            "K12TabAdjudication.vue",
            "K13TabAdjudication.vue",
        },
        "host": {"GtK6HeldForSale.vue"},
    }

    def test_publish_gate_hits_14_files(self, endpoints) -> None:
        by_file, hits = endpoints
        assert len(by_file.get(EP_PUBLISH, set())) == 14
        assert hits.get(EP_PUBLISH, 0) == 14

    def test_carriers_split_into_exactly_four_layers(self, endpoints) -> None:
        by_file, _ = endpoints
        actual = by_file[EP_PUBLISH]
        expected_all = set()
        for layer in self.EXPECTED_LAYERS.values():
            expected_all |= layer
        assert actual == expected_all, (
            f"多 {sorted(actual - expected_all)}，缺 {sorted(expected_all - actual)}"
        )

    def test_layer_counts_are_5_3_5_1(self, endpoints) -> None:
        """5 + 3 + 5 + 1 = 14。"""
        by_file, _ = endpoints
        actual = by_file[EP_PUBLISH]
        counts = {
            name: len(actual & layer)
            for name, layer in self.EXPECTED_LAYERS.items()
        }
        assert counts == {
            "form_data": 5,
            "adjudication_composable": 3,
            "tab_adjudication": 5,
            "host": 1,
        }, f"四层分布不符：{counts}"
        assert sum(counts.values()) == 14

    def test_k6_is_the_only_host_layer_carrier(self, endpoints) -> None:
        """🔴 GtK6HeldForSale.vue 是全 K 唯一在宿主层的 TB 发布门。"""
        by_file, _ = endpoints
        hosts = {f for f in by_file[EP_PUBLISH] if f.startswith("GtK")}
        assert hosts == {"GtK6HeldForSale.vue"}

    def test_all_13_entries_are_covered(self, endpoints) -> None:
        """13/13 全覆盖（K5 占 2 处）。"""
        by_file, _ = endpoints
        covered: set[int] = set()
        for fname in by_file[EP_PUBLISH]:
            m = re.match(r"^(?:use|Gt)?K(1[0-3]|[1-9])(?![0-9])", fname)
            assert m, f"无法从 {fname} 反推 entry 序号"
            covered.add(int(m.group(1)))
        assert covered == set(K_INDEXES), (
            f"未覆盖的 entry：{sorted(set(K_INDEXES) - covered)}"
        )
        # K5 占 2 处 ⇒ 14 处 / 13 entry
        k5_carriers = {
            f for f in by_file[EP_PUBLISH]
            if re.match(r"^(?:use|Gt)?K5(?![0-9])", f)
        }
        assert len(k5_carriers) == 2, f"K5 应占 2 处，实得 {sorted(k5_carriers)}"

    def test_symbol_name_criterion_would_miss_the_gate(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 反证：按符号名 `publishToTb` 判与按端点判结果不同。"""
        by_symbol = literal_hits(k_files, "publishToTb")
        by_endpoint, _ = endpoint_index(k_files)
        endpoint_files = by_endpoint.get(EP_PUBLISH, set())
        assert set(by_symbol) != endpoint_files, (
            "符号名口径与端点口径结果相同 ⇒ 这条反证失去意义"
            "（J 轮已证该符号名可以全域 0 命中而端点命中）"
        )


# ════════════════════════════════════════════════════════════════════════════
# 行数口径门（KF-P61 的 foundation 侧落地）
# ════════════════════════════════════════════════════════════════════════════
class TestLineCountCaliber:
    """🔴 KC-22②：行数一律 `split("\\n")`，`splitlines()` 恒少 1。"""

    def test_remaining_dual_mode_files_differ_by_exactly_one(self) -> None:
        """🔴 只遍历**仍存在**的 6 个 —— BP-5 已删掉 7 个 orphan。"""
        checked = 0
        for n in K_INDEXES:
            p = dual_mode_path(n)
            if n in BP5_DELETED_ORPHAN_ENTRIES:
                assert not p.exists(), f"{p.name} 仍在 ⇒ BP-5 删除未生效"
                continue
            assert p.exists(), f"{p.name} 不存在（它不在删除范围里）"
            a = line_count(p)
            b = line_count_splitlines(p)
            assert a - b == 1, (
                f"{p.name}: split={a} splitlines={b}，差 {a-b} 而非 1"
            )
            checked += 1
        assert checked == 13 - BP5_DELETED_COUNT == 6, f"实检 {checked} 个"

    def test_orphan_line_counts_are_a_frozen_pre_deletion_baseline(self) -> None:
        """🔴 7 个 orphan 的行数只能作**删除前基线**留档，文件已不在。

        基线 115/115/115/126/126/125/116 = **838**（splitlines 831，各少 1）。
        这组数字的用途是：日后有人想「恢复」这些文件时，能对账恢复的是不是同一份。
        ⇒ 判据只验算术自洽 + 文件确已删除，不再读文件。
        """
        baseline = {1: 115, 2: 115, 3: 115, 4: 126, 5: 126, 6: 125, 7: 116}
        assert sum(baseline.values()) == 838
        # splitlines 口径 = 每个各少 1
        assert sum(v - 1 for v in baseline.values()) == 831
        assert set(baseline) == set(BP5_DELETED_ORPHAN_ENTRIES)
        for n in baseline:
            assert not dual_mode_path(n).exists(), (
                f"useK{n}DualMode.ts 仍在 ⇒ 这组数字应改回现算判据"
            )

    #: 🔴 收敛**前**基线 —— 这组是真实测得的（与 slice / design 登记逐值相符）。
    BEFORE = {8: 189, 9: 182, 10: 155, 11: 154, 12: 158, 13: 158}
    #: 🔴 收敛**后**现算 —— 见下方 docstring 的勘误说明。
    AFTER = {8: 274, 9: 260, 10: 241, 11: 236, 12: 244, 13: 244}

    def test_bp6_line_counts_after_convergence(self) -> None:
        """6 个 live composable 行数（BP-6 全集收敛后）。

        ═══ 🔴 勘误：本条原先写的是**实施前的预测值**，不是测量值 ═══

        本判据首版写 `{8: 260, 9: 252, 10: 229, 11: 224, 12: 230, 13: 230}`，并把它
        描述成「收敛后现算」。但那组数字是**在 foundation Task 26 与 lane 2 Task 4~5
        落地之前**写下的 —— 当时 6 个文件都还是 `BEFORE` 的行数，不可能测出 `AFTER`。
        收敛实施完成后现算得 `AFTER`（净增 85/78/86/82/86/86），与预测差 8~14 行。

        口径与方法论铁律 ㉖ 同向：换掉一个过期/臆测的数字时，**新数字必须用同一标准
        测出来并写明口径**，否则只是把一个错数换成另一个错数。这里的口径是
        `len(text.split("\\n"))`（KF-P61），由 `line_count()` 单一出口计算。

        🔴 绝对行数是**快照**不是性质 —— 它只用于「有人悄悄大改这些文件时打红」。
        真正的性质判据是另外三条：两口径差恒为 1、净增量区间自洽、增长来源逐条可复算
        （`test_line_growth_is_from_convergence_not_noise`）。
        """
        for n, exp in self.AFTER.items():
            actual = line_count(dual_mode_path(n))
            assert actual == exp, f"useK{n}DualMode.ts: 期望 {exp} 行，实得 {actual}"
        assert sum(self.AFTER.values()) == 1499
        assert set(self.AFTER) == set(BP6_INDEXES)

    def test_growth_is_uniform_and_in_the_declared_band(self) -> None:
        """🔴 性质判据：6 个净增量同量级（同一套改动，不是随手堆注释）。

        现算 85/78/86/82/86/86 —— 带宽 8 行，差异来源可逐条指认：
        K9 少 8 行是因为它的 `modeOptions` 原本就是单行写法、且无 `readPersistedMode()`
        二次读（K10/K12/K13 的 onMounted 要用它）。
        """
        deltas = {n: self.AFTER[n] - self.BEFORE[n] for n in BP6_INDEXES}
        assert all(75 <= d <= 95 for d in deltas.values()), (
            f"净增量离散：{deltas} ⇒ 改动不一致须复核"
        )
        assert max(deltas.values()) - min(deltas.values()) <= 10, (
            f"净增量带宽 {max(deltas.values()) - min(deltas.values())} > 10 ⇒ 六者改动不同型"
        )

    def test_both_calibers_differ_by_exactly_one(self) -> None:
        """🔴 KF-P61 的真正性质：`splitlines()` 比 `split("\\n")` 恒少 1。"""
        for n in BP6_INDEXES:
            p = dual_mode_path(n)
            assert line_count(p) - line_count_splitlines(p) == 1, (
                f"useK{n}DualMode.ts 两口径差值不是 1"
            )

    def test_line_growth_is_from_convergence_not_noise(self) -> None:
        """🔴 6 个 composable 的行数增长来源逐条可复算（不是随手加注释）。"""
        for n in BP6_INDEXES:
            src = cached_text(dual_mode_path(n))
            assert "fetchOnlyOfficeHealthy" in src, f"K{n} 缺单源探针 import"
            assert "workpaperSyncModeKey" in src, f"K{n} 缺统一键生成器"
            assert "migrateWorkpaperSyncMode" in src, f"K{n} 缺旧键迁移"
            assert "missing_adapter" in src, (
                f"K{n} 缺「为什么 config 直调保留」的说明 ⇒ 后来者会以为是漏做"
            )


# ════════════════════════════════════════════════════════════════════════════
# BP-5 / BP-6 两组互斥（切分自检）
# ════════════════════════════════════════════════════════════════════════════
class TestBp5Bp6Disjoint:
    """KD-2：内联 IIFE 与 import 专用 composable 两集合互斥。"""

    _IIFE_RX = re.compile(r"const\s+dualMode\s*=\s*\(\(\)\s*=>")

    def test_bp5_hosts_have_iife_and_no_import(self) -> None:
        for n in BP5_INDEXES:
            src = strip_comments(cached_text(host_path(n)))
            iife = len(self._IIFE_RX.findall(src))
            imp = len(re.findall(rf"import\s*\{{\s*useK{n}DualMode", src))
            assert iife == 1, f"{K_HOSTS[n]}: IIFE 期望 1 处，实得 {iife}"
            assert imp == 0, f"{K_HOSTS[n]}: import 期望 0 处，实得 {imp}"

    def test_bp6_hosts_have_import_and_no_iife(self) -> None:
        for n in BP6_INDEXES:
            src = strip_comments(cached_text(host_path(n)))
            iife = len(self._IIFE_RX.findall(src))
            imp = len(re.findall(rf"import\s*\{{\s*useK{n}DualMode", src))
            assert iife == 0, f"{K_HOSTS[n]}: IIFE 期望 0 处，实得 {iife}"
            assert imp == 1, f"{K_HOSTS[n]}: import 期望 1 处，实得 {imp}"

    def test_groups_partition_all_13(self) -> None:
        assert set(BP5_INDEXES) | set(BP6_INDEXES) == set(K_INDEXES)
        assert set(BP5_INDEXES) & set(BP6_INDEXES) == set()
        assert len(BP5_INDEXES) == 7 and len(BP6_INDEXES) == 6
