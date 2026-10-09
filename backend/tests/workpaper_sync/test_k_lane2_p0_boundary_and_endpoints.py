# -*- coding: utf-8 -*-
"""K 循环 lane 2 — Task 0~3：前置门 + 5 个 live composable 端点清册。

spec: k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub
Task 0: entry 边界与切分自检
Task 1: 反向对照门（证明本 lane 的非零结论不是漏扫）
Task 2: 端点扫描器与行数口径
Task 3: 5 个 live composable 的端点清册
Property: KB-P1, KB-P2, KB-P3, KB-P4, KB-P5, KB-P6, KB-P7, KB-P8

═══ 上游 ═══

共同裁决 **KC-1 ~ KC-24** 在 `k-cycle-sync-foundation-and-first-canary/design.md`。
🔴 本 spec 只**引用编号**，不复述正文。
口径真源复用 `tests/workpaper_sync/k_foundation_facts.py`（唯一真源）。

═══ 本 lane 的定位 ═══

BP-6 全集 6 条（K8~K13），**K10 已在 foundation 作 canary 完整交付** ⇒ 本 lane 是
剩余 **5** 条。canary 与本 lane 同属 BP-6 组 ⇒ **canary 的形态判据可直接外推**
（这是本 lane 相对 lane 1 的优势，lane 1 的 BP-5 形态完全无 canary 覆盖）。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_INDEXES,
    BP6_INDEXES,
    BP8_BASELINE_DEFECT_BY_ENTRY,
    BP8_BASELINE_ZERO_DEFECT_ENTRIES,
    BP8_CONVERGED_ENTRIES,
    DATA,
    FRONTEND,
    K_HOSTS,
    K_INDEXES,
    ROOT,
    business_keys,
    cached_text,
    defect_by_entry,
    dual_mode_path,
    endpoint_index,
    host_path,
    k_domain_files,
    line_count,
    line_count_splitlines,
    strip_comments,
)

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"

#: 本 lane 的 5 条 entry 序号（BP-6 去掉 canary K10）
LANE2 = (8, 9, 11, 12, 13)
#: foundation 的 canary
CANARY_INDEX = 10

#: 5 条 entry_id 全名
LANE2_ENTRY_IDS = frozenset({
    "xlsx/gt-k8-selling-expenses",
    "xlsx/gt-k9-admin-expenses",
    "xlsx/gt-k11-asset-impairment-loss",
    "xlsx/gt-k12-non-operating-income",
    "xlsx/gt-k13-non-operating-expense",
})

EP_HEALTH = "/api/workpapers/onlyoffice/health"
EP_CONFIG = "/api/workpapers/{X}/sheets/{X}/onlyoffice-config"

_STMT_RX = re.compile(r"(?:from|import\(|vi\.mock\()\s*['\"]([^'\"]+)['\"]")


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(MANIFEST_SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def all_frontend() -> list[pathlib.Path]:
    return [
        p for p in FRONTEND.rglob("*")
        if p.is_file() and p.suffix in (".ts", ".vue")
    ]


def _consumer_edges(
    all_frontend: list[pathlib.Path], n: int
) -> tuple[list[str], list[str]]:
    """返回 (生产边文件名, 测试边文件名)。

    🔴 口径：只认 statement-position 形态 + **路径 stem 相等**（不是子串），
    且排除目标文件自身。
    """
    target = f"useK{n}DualMode"
    prod: list[str] = []
    test: list[str] = []
    for p in all_frontend:
        if p.name == f"useK{n}DualMode.ts":
            continue
        src = strip_comments(cached_text(p))
        for m in _STMT_RX.finditer(src):
            stem = m.group(1).rsplit("/", 1)[-1]
            if stem != target:
                continue
            if "__tests__" in p.as_posix() or ".spec." in p.name:
                test.append(p.name)
            else:
                prod.append(p.name)
            break
    return prod, test


# ════════════════════════════════════════════════════════════════════════════
# Task 0 / KB-P1~P2：entry 边界与切分自检
# ════════════════════════════════════════════════════════════════════════════
class TestKBP1EntryBoundary:
    """5 条 entry 与 foundation / lane 1 三者无交集，并集 13。"""

    def test_five_entry_ids_listed_in_full(self, manifest_slice: dict) -> None:
        declared = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert LANE2_ENTRY_IDS <= declared, (
            f"lane 2 的 entry 不在 slice 里：{sorted(LANE2_ENTRY_IDS - declared)}"
        )
        assert len(LANE2_ENTRY_IDS) == 5

    def test_three_way_disjoint_union_is_13(self, manifest_slice: dict) -> None:
        """foundation 1 + lane1 7 + lane2 5 == 13，两两无交集。"""
        foundation = {"xlsx/gt-k10-other-income"}
        lane1 = {
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if "BP-5" in e["capability_target_blocked_by"]
        }
        assert len(lane1) == 7
        assert foundation & LANE2_ENTRY_IDS == set()
        assert lane1 & LANE2_ENTRY_IDS == set()
        assert foundation & lane1 == set()
        union = foundation | lane1 | LANE2_ENTRY_IDS
        assert len(union) == 13
        declared = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert union == declared


class TestKBP2Bp6Membership:
    """🔴 5 条全部含 BP-6；BP-6 全集恰 K8~K13 共 6 条，去 K10 后是这 5 条。"""

    def test_all_five_are_blocked_by_bp6(self, manifest_slice: dict) -> None:
        by_id = {
            e["entry_id"]: e for e in manifest_slice["independent_entries"]
        }
        for eid in LANE2_ENTRY_IDS:
            blocked = by_id[eid]["capability_target_blocked_by"]
            assert "BP-6" in blocked, f"{eid} 不含 BP-6：{blocked}"

    def test_bp6_holders_are_exactly_k8_to_k13(
        self, manifest_slice: dict
    ) -> None:
        """两侧都验：BP-6 持有者恰好 6 条。"""
        holders = {
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if "BP-6" in e["capability_target_blocked_by"]
        }
        assert len(holders) == 6, f"BP-6 持有者期望 6 条，实得 {len(holders)}"
        assert holders - {"xlsx/gt-k10-other-income"} == LANE2_ENTRY_IDS

    def test_bp6_index_set_matches_facts_layer(self) -> None:
        """与 facts 层的 BP6_INDEXES 常量一致。"""
        assert set(BP6_INDEXES) == set(LANE2) | {CANARY_INDEX}
        assert len(BP6_INDEXES) == 6

    def test_bp4_and_bp5_do_not_land_here(self, manifest_slice: dict) -> None:
        """🔴 KB-P42：BP-4 与 BP-5 都不落本 lane（全在 lane 1）。"""
        by_id = {
            e["entry_id"]: e for e in manifest_slice["independent_entries"]
        }
        for eid in LANE2_ENTRY_IDS:
            blocked = set(by_id[eid]["capability_target_blocked_by"])
            assert "BP-4" not in blocked, f"{eid} 含 BP-4"
            assert "BP-5" not in blocked, f"{eid} 含 BP-5"


class TestLane2ScaleMatchesDesign:
    """本 lane 六项规模现算并与 design 等值。"""

    def test_sheets_is_49(self) -> None:
        """sheets 49 = K8 12 + K9 12 + K11 7 + K12 9 + K13 9。"""
        from openpyxl import load_workbook
        k_tpl = ROOT / "backend" / "wp_templates" / "K"
        expected = {8: 12, 9: 12, 11: 7, 12: 9, 13: 9}
        total = 0
        for n, exp in expected.items():
            cand = [
                f for f in k_tpl.iterdir()
                if re.match(rf"^K{n}(?![0-9])", f.name) and f.suffix == ".xlsx"
            ]
            assert len(cand) == 1, f"K{n} 册匹配 {[c.name for c in cand]}"
            wb = load_workbook(cand[0], read_only=True)
            try:
                actual = len(wb.sheetnames)
            finally:
                wb.close()
            assert actual == exp, f"K{n}: sheets 期望 {exp}，实得 {actual}"
            total += actual
        assert total == 49

    def test_k11_has_the_fewest_sheets_in_all_k(self) -> None:
        """🔴 K11 只 7 张是全 K 最少。"""
        from openpyxl import load_workbook
        k_tpl = ROOT / "backend" / "wp_templates" / "K"
        counts: dict[int, int] = {}
        for n in K_INDEXES:
            cand = [
                f for f in k_tpl.iterdir()
                if re.match(rf"^K{n}(?![0-9])", f.name) and f.suffix == ".xlsx"
            ]
            wb = load_workbook(cand[0], read_only=True)
            try:
                counts[n] = len(wb.sheetnames)
            finally:
                wb.close()
        assert counts[11] == min(counts.values()), (
            f"K11 不是最少：{sorted(counts.items(), key=lambda kv: kv[1])[:3]}"
        )

    def test_bare_if_is_424(self) -> None:
        """裸 IF 424 = K9 175 + K8 136 + K11 39 + K12 37 + K13 37。"""
        from openpyxl import load_workbook
        k_tpl = ROOT / "backend" / "wp_templates" / "K"
        rx = re.compile(r"(?<![A-Z])IF\(")
        expected = {8: 136, 9: 175, 11: 39, 12: 37, 13: 37}
        total = 0
        for n, exp in expected.items():
            cand = [
                f for f in k_tpl.iterdir()
                if re.match(rf"^K{n}(?![0-9])", f.name) and f.suffix == ".xlsx"
            ]
            wb = load_workbook(cand[0], read_only=True, data_only=False)
            try:
                c = 0
                for sn in wb.sheetnames:
                    for row in wb[sn].iter_rows():
                        for cell in row:
                            v = cell.value
                            if (
                                isinstance(v, str)
                                and v.startswith("=")
                                and rx.search(v)
                            ):
                                c += 1
            finally:
                wb.close()
            assert c == exp, f"K{n}: 裸 IF 期望 {exp}，实得 {c}"
            total += c
        assert total == 424

    def test_bare_if_is_59_percent_of_13_entry_books(self) -> None:
        """🔴 424 占 13 entry 册 715 的 59%，三份 spec 里最高。"""
        pct = 424 / 715
        assert 0.58 <= pct <= 0.60, f"占比 {pct:.1%} 不在 59% 附近"

    def test_defined_name_is_zero_for_all_five(self) -> None:
        """definedName 5 册全 0（K 循环 82 个全在 foundation 1 + lane1 81）。"""
        from openpyxl import load_workbook
        k_tpl = ROOT / "backend" / "wp_templates" / "K"
        for n in LANE2:
            cand = [
                f for f in k_tpl.iterdir()
                if re.match(rf"^K{n}(?![0-9])", f.name) and f.suffix == ".xlsx"
            ]
            wb = load_workbook(cand[0], read_only=False, data_only=False)
            try:
                count = len(list(wb.defined_names.values()))
            finally:
                wb.close()
            assert count == 0, f"K{n}: definedName 期望 0，实得 {count}"

    def test_bp8_is_21_with_k13_as_control_group(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """BP-8 **基线** 21 处：K8 8 · K9 7 · K11 4 · K12 2；🔴 K13 为 0 是对照组。

        本 lane 的**交付规模**由基线定义（Task 13 已把现算收敛到 0）。规模判据
        按基线判，收敛判据按现算判 —— 两者都要，缺一个就分不清「做完了」和
        「本来就没有」。
        """
        baseline = {n: BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE2}
        assert baseline == {8: 8, 9: 7, 11: 4, 12: 2, 13: 0}, baseline
        assert sum(baseline.values()) == 21
        # 🔴 K13 的 0 是**基线本来就 0**（对照组），不是被收敛出来的
        assert 13 in BP8_BASELINE_ZERO_DEFECT_ENTRIES

    def test_bp8_is_fully_converged_in_this_lane(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 收敛判据：本 lane 5 条 entry 现算全 0（Task 13 交付）。"""
        de = defect_by_entry(k_files)
        residue = {n: de[n] for n in LANE2 if de.get(n, 0)}
        assert residue == {}, f"本 lane 仍有位置化残留：{residue}"
        # 🔴 收敛账本现已是**全 13 条**（lane 1 Task 15 后）⇒ 本 lane 是其子集
        assert set(LANE2) <= set(BP8_CONVERGED_ENTRIES)

    def test_bp8_baseline_sums_to_45_with_lane1(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """本 lane 基线 21 + lane 1 基线 24 == 45；现算则只剩 lane 1 的 24。"""
        b1 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in BP5_INDEXES)
        b2 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE2)
        assert (b1, b2) == (24, 21)
        assert b1 + b2 == 45
        # 🔴 lane 1 随后也收敛完了 ⇒ 现算全域归零（不再是「只剩 lane 1 的 24」）
        de = defect_by_entry(k_files)
        assert sum(de.values()) == 0, f"全域仍有位置化缺陷：{dict(de)}"

    def test_frontend_literal_key_count(self, k_files: list[pathlib.Path]) -> None:
        """本 lane 前端字面量键 **201**。

        🔴 design 的 323 是真库口径；前端字面量扫描得 201
        （K8 54 · K9 58 · K11 29 · K12 30 · K13 30）。两个口径都对，混用会算错。
        """
        keys = business_keys(k_files)
        by_entry: dict[int, int] = {}
        for k in keys:
            m = re.match(r"^K(1[0-3]|[1-9])(?![0-9])", k)
            if m:
                e = int(m.group(1))
                by_entry[e] = by_entry.get(e, 0) + 1
        expected = {8: 54, 9: 58, 11: 29, 12: 30, 13: 30}
        for n, exp in expected.items():
            assert by_entry.get(n, 0) == exp, (
                f"K{n}: 键数期望 {exp}，实得 {by_entry.get(n, 0)}"
            )
        assert sum(by_entry.get(n, 0) for n in LANE2) == 201


# ════════════════════════════════════════════════════════════════════════════
# Task 1 / KB-P3~P4：反向对照门
# ════════════════════════════════════════════════════════════════════════════
class TestKBP3LiveComposablesHaveExactlyOneEdge:
    """5 个 live composable 各恰 1 条生产边、测试边 0。"""

    def test_each_has_exactly_one_production_edge(
        self, all_frontend: list[pathlib.Path]
    ) -> None:
        for n in LANE2:
            prod, test = _consumer_edges(all_frontend, n)
            assert len(prod) == 1, (
                f"useK{n}DualMode.ts 生产边期望 1 条，实得 {prod}"
            )
            assert test == [], (
                f"useK{n}DualMode.ts 测试边期望 0 条，实得 {test}"
            )

    def test_the_edge_points_to_the_declared_host(
        self, all_frontend: list[pathlib.Path], manifest_slice: dict
    ) -> None:
        """🔴 边指向的宿主与 slice 的 `dual_mode_carrier.site` 一致。"""
        by_id = {
            e["entry_id"]: e for e in manifest_slice["independent_entries"]
        }
        eid_by_index = {
            8: "xlsx/gt-k8-selling-expenses",
            9: "xlsx/gt-k9-admin-expenses",
            11: "xlsx/gt-k11-asset-impairment-loss",
            12: "xlsx/gt-k12-non-operating-income",
            13: "xlsx/gt-k13-non-operating-expense",
        }
        for n in LANE2:
            prod, _ = _consumer_edges(all_frontend, n)
            assert prod == [K_HOSTS[n]], (
                f"K{n} 的边指向 {prod}，期望 [{K_HOSTS[n]}]"
            )
            site = by_id[eid_by_index[n]]["dual_mode_carrier"]["site"]
            assert K_HOSTS[n] in site, (
                f"K{n}: slice 的 site={site} 与实测宿主 {K_HOSTS[n]} 不符"
            )

    def test_carrier_kind_is_dedicated_composable(
        self, manifest_slice: dict
    ) -> None:
        """5 条的 `dual_mode_carrier.kind` 全是 `dedicated_composable`。"""
        by_id = {
            e["entry_id"]: e for e in manifest_slice["independent_entries"]
        }
        for eid in LANE2_ENTRY_IDS:
            carrier = by_id[eid]["dual_mode_carrier"]
            assert carrier["kind"] == "dedicated_composable", (
                f"{eid}: kind={carrier['kind']!r}"
            )
            assert carrier.get("orphan_twin") is None, (
                f"{eid} 有 orphan_twin ⇒ 它属 BP-5 组"
            )


class TestKBP4ReverseComparisonWithLane1:
    """🔴 反向对照：lane 1 的 7 个 orphan 生产边与测试边各为 0、config 全 0。

    两侧都验，证明本 lane 的「各 1 条边 + config 非 0」不是漏扫。
    """

    def test_lane1_seven_orphans_have_zero_production_edges(
        self, all_frontend: list[pathlib.Path]
    ) -> None:
        for n in BP5_INDEXES:
            prod, _ = _consumer_edges(all_frontend, n)
            assert prod == [], (
                f"useK{n}DualMode.ts 有生产边 {prod} ⇒ 它不是 orphan，"
                "本 lane 的反向对照失效"
            )

    def test_lane1_seven_orphans_have_zero_config_hits(self) -> None:
        """lane 1 的 7 个 orphan `onlyoffice-config` 全为 0。

        🔴 这 7 个已被 lane 1 的 Task 5 **删除** ⇒ 「config 命中 0」从「读文件
        读不到」变成「文件都不在了」。反向对照的结论**更强**（0 vs 6 变成
        「不存在 vs 6」），但判据必须如实翻面，不能继续读已删文件。
        """
        for n in BP5_INDEXES:
            p = dual_mode_path(n)
            assert not p.exists(), (
                f"useK{n}DualMode.ts 仍在 ⇒ lane 1 的 BP-5 删除未生效"
            )
        # 两侧都验：本 lane 的 6 个仍在且**确有** config 直调（对照的另一端）
        from tests.workpaper_sync.k_foundation_facts import BP6_INDEXES

        for n in BP6_INDEXES:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "onlyoffice-config" in src, (
                f"useK{n}DualMode.ts 无 config 直调 ⇒ 对照的另一端失效"
            )

    def test_lane2_five_have_non_zero_config(self) -> None:
        """本 lane 5 个 config 非 0（对照成立的另一侧）。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "onlyoffice-config" in src, (
                f"useK{n}DualMode.ts 无 config 直调 ⇒ 与 BP-6 登记矛盾"
            )

    def test_the_two_groups_are_mutually_exclusive(
        self, all_frontend: list[pathlib.Path]
    ) -> None:
        """两组的生产边数形成 0 vs 1 的清晰二分。"""
        lane1_edges = sum(
            len(_consumer_edges(all_frontend, n)[0]) for n in BP5_INDEXES
        )
        lane2_edges = sum(
            len(_consumer_edges(all_frontend, n)[0]) for n in LANE2
        )
        assert lane1_edges == 0, f"lane 1 生产边合计 {lane1_edges}，期望 0"
        assert lane2_edges == 5, f"lane 2 生产边合计 {lane2_edges}，期望 5"


# ════════════════════════════════════════════════════════════════════════════
# Task 2 / KB-P7~P8：端点扫描器与行数口径
# ════════════════════════════════════════════════════════════════════════════
class TestKBP7BacktickRecognition:
    """🔴 端点正则必须认反引号，否则 config 命中降为 0。"""

    def test_config_hits_with_backtick(self, k_files: list[pathlib.Path]) -> None:
        by_file, _ = endpoint_index(k_files, recognize_backtick=True)
        files = by_file.get(EP_CONFIG, set())
        # 本 lane 的 5 个全在（K10 也在，属 foundation）
        for n in LANE2:
            assert f"useK{n}DualMode.ts" in files, (
                f"useK{n}DualMode.ts 不在 config 命中集合里：{sorted(files)}"
            )

    def test_config_drops_to_zero_without_backtick(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 变异反证：只认单/双引号时 config 命中降为 0。"""
        by_file_nb, _ = endpoint_index(k_files, recognize_backtick=False)
        assert by_file_nb.get(EP_CONFIG, set()) == set(), (
            "不认反引号时 config 仍有命中 ⇒ 反证失效"
        )

    def test_substring_caliber_shows_8_sites(self) -> None:
        """子串口径：本 lane 8 处（K8/K9/K11 各 2 + K12/K13 各 1）。

        🔴 多出的 3 处是 `throw new Error('empty onlyoffice-config')` 错误消息
        （K8/K9/K11 各 1），不是端点直调 —— 与 foundation 的同源发现一致。
        """
        expected = {8: 2, 9: 2, 11: 2, 12: 1, 13: 1}
        total = 0
        error_msg_files: list[str] = []
        for n, exp in expected.items():
            src = strip_comments(cached_text(dual_mode_path(n)))
            c = len(re.findall(r"onlyoffice-config", src))
            assert c == exp, f"useK{n}DualMode.ts: 子串期望 {exp}，实得 {c}"
            total += c
            if c == 2:
                assert re.search(r"empty onlyoffice-config", src), (
                    f"useK{n}DualMode.ts 的第二处不是错误消息"
                )
                error_msg_files.append(f"useK{n}DualMode.ts")
        assert total == 8
        assert len(error_msg_files) == 3, (
            f"带错误消息的文件应为 3 个（K8/K9/K11），实得 {error_msg_files}"
        )


class TestKBP8LineCountCaliber:
    """🔴 行数口径统一 `split("\\n")`；`splitlines()` 恒少 1。

    原基线 189/182/154/158/158 = 841；Task 4~5 收敛后各净增 ~70 行
    （单源探针 + 统一键迁移 + BP-6 边界 why-not 说明）。
    """

    #: 收敛前基线（design.md 登记值）—— 🔴 这组是**真实测得**的，现已不可复测
    #: （文件已改），但与 slice / design 的登记逐值相符，作冻结基线留档。
    BEFORE = {8: 189, 9: 182, 11: 154, 12: 158, 13: 158}
    #: 🔴 收敛后现算 —— 见下方 docstring 勘误说明。
    EXPECTED = {8: 274, 9: 260, 11: 236, 12: 244, 13: 244}

    def test_line_counts_after_convergence(self) -> None:
        """🔴 勘误：本条原先写的是**实施前的预测值**，不是测量值。

        首版写 `{8: 260, 9: 252, 11: 224, 12: 230, 13: 230}` 并描述为「收敛后现算」。
        但那组数字写在 Task 4~5 落地**之前** —— 当时 5 个文件都还是 `BEFORE` 的行数，
        不可能测出它。收敛实施完成后现算得 `EXPECTED`（净增 85/78/82/86/86），与预测
        差 8~14 行。

        换数字遵方法论铁律 ㉖：新值必须用同一口径测出并写明口径 ——
        `len(text.split("\\n"))`（KB-P8），由 `line_count()` 单一出口计算，
        与 foundation p4 的 `TestLineCountCaliber.AFTER` 同源（两处必须一致，见下）。

        🔴 绝对行数是**快照**不是性质，只用于「有人悄悄大改这些文件时打红」。
        性质判据是另外两条：两口径差恒为 1 + 净增量同量级。
        """
        total = 0
        for n, exp in self.EXPECTED.items():
            actual = line_count(dual_mode_path(n))
            assert actual == exp, (
                f"useK{n}DualMode.ts: 期望 {exp} 行，实得 {actual}"
            )
            total += actual
        assert total == 1258, f"合计期望 1258，实得 {total}"

    def test_the_two_specs_quote_the_same_snapshot(self) -> None:
        """🔴 同一快照在两份 spec 的守卫里各写了一遍 ⇒ 必须逐值锁死。

        foundation p4 管 BP-6 全集 6 条、本 lane 管其中 5 条。只改一处会留下
        「两个真源各说一套」的漂移面 —— 这条就是那道锁。
        """
        from tests.workpaper_sync.test_k_foundation_p4_endpoints_and_carriers import (
            TestLineCountCaliber,
        )

        for n, exp in self.EXPECTED.items():
            assert TestLineCountCaliber.AFTER[n] == exp, (
                f"K{n}: foundation 记 {TestLineCountCaliber.AFTER[n]}，本 lane 记 {exp}"
            )
        for n, before in self.BEFORE.items():
            assert TestLineCountCaliber.BEFORE[n] == before, (
                f"K{n} 收敛前基线两处不一致"
            )
        # canary K10 只在 foundation 侧有分母（本 lane 不含它）
        assert CANARY_INDEX not in self.EXPECTED
        assert CANARY_INDEX in TestLineCountCaliber.AFTER

    def test_growth_is_uniform_across_five(self) -> None:
        """🔴 5 个净增量接近（同一套改动，不是随手加注释）。"""
        deltas = {
            n: self.EXPECTED[n] - self.BEFORE[n] for n in self.EXPECTED
        }
        assert all(75 <= d <= 95 for d in deltas.values()), (
            f"净增量离散：{deltas} ⇒ 改动不一致须复核"
        )
        assert max(deltas.values()) - min(deltas.values()) <= 10, (
            f"净增量带宽 {max(deltas.values()) - min(deltas.values())} > 10"
            " ⇒ 五者改动不同型"
        )

    def test_splitlines_is_exactly_five_less(self) -> None:
        """`splitlines()` 比 `split("\\n")` 少 5（5 个各少 1）。"""
        a = sum(line_count(dual_mode_path(n)) for n in self.EXPECTED)
        b = sum(line_count_splitlines(dual_mode_path(n)) for n in self.EXPECTED)
        assert a - b == 5, f"两口径差值 {a - b} 不是 5"

    def test_each_differs_by_exactly_one(self) -> None:
        for n in LANE2:
            p = dual_mode_path(n)
            assert line_count(p) - line_count_splitlines(p) == 1, (
                f"useK{n}DualMode.ts 两口径差值不是 1"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 3 / KB-P5~P6：5 个 live composable 端点清册
# ════════════════════════════════════════════════════════════════════════════
class TestKBP5EndpointInventory:
    """health 直调已收敛（Task 4）· config 按端点口径各 1。

    🔴 原基线是 health 各 1（合 5）；Task 4 收敛到单源探针后**代码行 0 处**，
    只在 BP-6 说明注释里点名端点（说明需要指名它）。
    """

    def test_health_direct_call_is_zero_in_code(self) -> None:
        """🔴 5 个 composable 的 health 直调**代码行**全为 0。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            code = "\n".join(
                ln for ln in src.split("\n")
                if not ln.lstrip().startswith(("*", "//", "/*"))
            )
            assert "onlyoffice/health" not in code, (
                f"useK{n}DualMode.ts 仍有 health 直调代码 ⇒ Task 4 收敛被回退"
            )

    def test_all_five_use_the_single_source_probe(self) -> None:
        """5 个都走 `fetchOnlyOfficeHealthy`。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "fetchOnlyOfficeHealthy" in src, (
                f"useK{n}DualMode.ts 未接单源探针"
            )

    #: 🔴 `switchMode` 里带 health 兜底的 entry（点击路径须 forceRefresh）。
    #: K11 例外：它的 `switchMode` **本来就没有** health 兜底 —— 只在 onMounted
    #: 做后台探测（`void checkOoHealth().then(...)`），那里用缓存值是对的。
    HAS_CLICK_TIME_HEALTH_FALLBACK = (8, 9, 12, 13)

    def test_force_refresh_on_click_where_the_fallback_exists(self) -> None:
        """有点击期 health 兜底的用 `checkOoHealth(true)` 绕过缓存（D4 竞态兜底）。"""
        for n in self.HAS_CLICK_TIME_HEALTH_FALLBACK:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "checkOoHealth(true)" in src, (
                f"useK{n}DualMode.ts 的点击路径未用 forceRefresh"
            )

    def test_k11_has_no_click_time_fallback_by_design(self) -> None:
        """🔴 K11 的 `switchMode` 无 health 兜底（形态差异，不是漏改）。

        它只在 `onMounted` 做后台探测 `void checkOoHealth().then(...)` ——
        那里**该用缓存值**（不阻塞首屏）。统一要求 `checkOoHealth(true)`
        会假红 K11。
        """
        src = strip_comments(cached_text(dual_mode_path(11)))
        assert "void checkOoHealth()" in src, (
            "K11 的 onMounted 后台探测形态变了"
        )
        # switchMode 段内不含 health 兜底
        sm = src.index("async function switchMode")
        seg = src[sm:sm + 1200]
        assert "checkOoHealth" not in seg, (
            f"K11 的 switchMode 出现了 health 兜底 ⇒ 须挪进"
            f" HAS_CLICK_TIME_HEALTH_FALLBACK"
        )

    def test_the_two_forms_partition_all_five(self) -> None:
        """两种形态覆盖全部 5 条（无第三种）。"""
        assert set(self.HAS_CLICK_TIME_HEALTH_FALLBACK) | {11} == set(LANE2)
        assert 11 not in self.HAS_CLICK_TIME_HEALTH_FALLBACK

    def test_config_endpoint_caliber_is_one_each(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """端点口径（`/api/` 开头的反引号字面量）：每文件恰 1 处。"""
        _by_file, _hits = endpoint_index(k_files)
        rx = re.compile(r"`[^`]*?/api/[^`]*onlyoffice-config[^`]*`")
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            c = len(rx.findall(src))
            assert c == 1, (
                f"useK{n}DualMode.ts: config 端点字面量期望 1 处，实得 {c}"
            )


class TestKBP6ReconcileWithCanary:
    """🔴 与 foundation 的 K10 对账：BP-6 全集 6 个 composable。"""

    def test_canary_has_health_1_and_config_substring_1(self) -> None:
        """K10 的 health 已收敛（foundation Task 26），config 子串 1 处。

        🔴 与 design 的原始登记（health 1 / config 1）对比：health 那一处
        **已在 foundation Task 26 收敛到单源探针** ⇒ 现算为 0。
        """
        src = strip_comments(cached_text(dual_mode_path(CANARY_INDEX)))
        assert "onlyoffice/health" not in src, (
            "K10 仍直调 health ⇒ foundation Task 26 的收敛被回退了"
        )
        assert "fetchOnlyOfficeHealthy" in src, (
            "K10 未用单源探针 ⇒ foundation Task 26 的收敛被回退了"
        )
        assert len(re.findall(r"onlyoffice-config", src)) == 1, (
            "K10 的 config 子串数变了"
        )

    def test_bp6_config_substring_total_is_9(self) -> None:
        """🔴 BP-6 全集 6 个 composable 的 config **子串** 9 处 / 6 文件。

        slice 的 `dual_mode_modules_calling_legacy_config_endpoint = 6` 是
        **文件数不是处数**（引用 KC-3）。
        """
        total = 0
        files = 0
        for n in BP6_INDEXES:
            src = strip_comments(cached_text(dual_mode_path(n)))
            c = len(re.findall(r"onlyoffice-config", src))
            if c:
                files += 1
            total += c
        assert files == 6, f"config 文件数期望 6，实得 {files}"
        assert total == 9, f"config 子串处数期望 9，实得 {total}"

    def test_slice_six_is_file_count_not_site_count(
        self, manifest_slice: dict
    ) -> None:
        """slice 的 6 与文件数吻合、与处数 9 不吻合 ⇒ 口径写明。"""
        s = manifest_slice["honest_adjudication_summary"]
        declared = s.get("dual_mode_modules_calling_legacy_config_endpoint")
        if declared is None:
            pytest.skip("slice 未登记该计数")
        assert declared == 6, f"slice 登记 {declared}"
        assert declared != 9, "slice 的 6 若等于处数则本条口径说明多余"

    def test_lane2_is_bp6_minus_one(self) -> None:
        """本 lane 5 条 = BP-6 全集 6 条 − canary 1 条。"""
        assert len(BP6_INDEXES) - 1 == len(LANE2) == 5
        assert set(BP6_INDEXES) - {CANARY_INDEX} == set(LANE2)


class TestLocalStorageConvergence:
    """Task 5：localStorage 收敛到统一键。

    🔴 原基线是 5 前缀 / 12 处 legacy；收敛后全部走
    `workpaperSyncModeKey()` 生成的 `workpaper-sync-mode:{entryId}:{wpId}:{sheetKey}`。
    """

    #: 🔴 本 lane 5 条全部已收敛（Task 5）
    CONVERGED = LANE2

    def test_all_five_are_converged(self) -> None:
        assert set(self.CONVERGED) == set(LANE2)

    def test_legacy_prefix_is_gone(self) -> None:
        """5 个 composable 的 legacy 前缀**代码行**全无。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            code = "\n".join(
                ln for ln in src.split("\n")
                if not ln.lstrip().startswith(("*", "//", "/*"))
            )
            assert f"k{n}-dual-mode:" not in code, (
                f"useK{n}DualMode.ts 仍有 legacy 前缀代码 ⇒ 收敛不彻底"
            )

    def test_all_use_the_unified_key_generator(self) -> None:
        """走 `workpaperSyncModeKey()`，不内联前缀常量。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "workpaperSyncModeKey" in src, (
                f"useK{n}DualMode.ts 未用统一键生成器"
            )
            assert "WP_SYNC_MODE_KEY_PREFIX" not in src, (
                f"useK{n}DualMode.ts 内联了前缀常量 ⇒ 第二份真源"
            )

    def test_all_migrate_legacy_keys(self) -> None:
        """调 `migrateWorkpaperSyncMode()` 消费旧键（存量偏好不丢）。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "migrateWorkpaperSyncMode" in src, (
                f"useK{n}DualMode.ts 未调迁移函数 ⇒ 存量偏好会静默丢失"
            )

    def test_stored_value_domain_is_html_or_oo(self) -> None:
        """🔴 落盘值域是统一真源的 `'html' | 'oo'`，不是 `'onlyoffice'`。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "toStoredMode" in src and "fromStoredMode" in src, (
                f"useK{n}DualMode.ts 缺值域映射函数 ⇒ 可能直接落 'onlyoffice'"
            )
            assert "'oo'" in src, f"useK{n}DualMode.ts 未出现 'oo' 值"

    def test_persist_capability_trap_is_avoided(self) -> None:
        """🔴 不用 `persistWorkpaperSyncMode`（capability 陷阱）。

        本 entry 现为 `single_onlyoffice` ⇒ 它会对 `'html'` 抛
        `mode_not_supported_by_capability`，且 migrate 会把 html 回落成 oo
        （强推首屏到 OO）。只用 migrate 完成旧键清理，模式按统一键原始值判。
        """
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            code = "\n".join(
                ln for ln in src.split("\n")
                if not ln.lstrip().startswith(("*", "//", "/*"))
            )
            assert "persistWorkpaperSyncMode" not in code, (
                f"useK{n}DualMode.ts 用了 persistWorkpaperSyncMode ⇒ 会抛 capability 错"
            )


class TestKBP11HostsHaveNoLocalStorage:
    """🔴 KB-P11：5 宿主 `localStorage` 命中**全为 0**。

    与 lane 1 的 K4/K5/K6 各 2 处形成对照 ⇒ 本 lane 的模式偏好只在 composable 侧。
    """

    def test_five_hosts_have_zero_localstorage(self) -> None:
        for n in LANE2:
            src = strip_comments(cached_text(host_path(n)))
            c = len(re.findall(r"\blocalStorage\b", src))
            assert c == 0, (
                f"{K_HOSTS[n]}: localStorage 期望 0 处，实得 {c}"
            )

    def test_lane1_k4_k5_k6_hosts_have_two_each(self) -> None:
        """反向对照：lane 1 的 K4/K5/K6 宿主各 2 处（撞车）。"""
        for n in (4, 5, 6):
            src = strip_comments(cached_text(host_path(n)))
            c = len(re.findall(r"\blocalStorage\b", src))
            assert c == 2, (
                f"{K_HOSTS[n]}: 期望 2 处（撞车），实得 {c}"
                " ⇒ 本 lane 的「全为 0」对照失去意义"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 6 / KB-P12~P15：KC-15 的 K8/K9 disabled 门控二分支判据
# ════════════════════════════════════════════════════════════════════════════
NOTICE_COMPONENT = "GtEntrySyncCapabilityNotice"


class TestKBP12VifGateDistribution:
    """🔴 宿主 `v-if` 门控：K11/K12/K13 各 1、**K8/K9 为 0**。"""

    VIF_GATED = (11, 12, 13)
    DISABLED_GATED = (8, 9)

    def test_vif_gate_hits_three_hosts(self) -> None:
        for n in LANE2:
            src = strip_comments(cached_text(host_path(n)))
            hits = len(re.findall(r'v-if="dualMode\.isOoAvailable', src))
            expected = 1 if n in self.VIF_GATED else 0
            assert hits == expected, (
                f"{K_HOSTS[n]}: v-if 门控期望 {expected} 处，实得 {hits}"
            )

    def test_k8_k9_have_no_vif_gate(self) -> None:
        """🔴 统一写「必须有 v-if」会假红 K8/K9。"""
        for n in self.DISABLED_GATED:
            src = strip_comments(cached_text(host_path(n)))
            assert 'v-if="dualMode.isOoAvailable' not in src, (
                f"{K_HOSTS[n]} 有 v-if 门控 ⇒ KC-15 的二分支前提变了"
            )

    def test_single_branch_criterion_falsely_reds_k8_k9(self) -> None:
        """反证：单分支判据的假红集合恰好是 {K8, K9}。"""
        failing = [
            n for n in LANE2
            if 'v-if="dualMode.isOoAvailable'
            not in strip_comments(cached_text(host_path(n)))
        ]
        assert failing == list(self.DISABLED_GATED), (
            f"假红集合应恰好 {list(self.DISABLED_GATED)}，实得 {failing}"
        )


class TestKBP13DisabledIsInComposable:
    """🔴 K8/K9 的 `disabled: !isOoAvailable` 在 composable 的 modeOptions 里。"""

    def test_disabled_option_is_in_composable(self) -> None:
        for n in (8, 9):
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert re.search(r"disabled:\s*!isOoAvailable", src), (
                f"useK{n}DualMode.ts 找不到 `disabled: !isOoAvailable`"
            )
            assert "modeOptions" in src, (
                f"useK{n}DualMode.ts 找不到 modeOptions ⇒ disabled 落点说明失效"
            )

    def test_host_layer_has_no_disabled_option(self) -> None:
        """宿主层找不到该形态（证明必须去 composable 里找）。"""
        for n in (8, 9):
            src = strip_comments(cached_text(host_path(n)))
            assert not re.search(r"disabled:\s*!isOoAvailable", src), (
                f"{K_HOSTS[n]} 宿主层有 disabled 形态 ⇒ 登记须更新"
            )

    def test_two_branch_criterion_covers_all_five(self) -> None:
        """二分支判据：「有 v-if」**或**「composable 里有 disabled」⇒ 5/5 通过。"""
        uncovered: list[int] = []
        for n in LANE2:
            has_vif = 'v-if="dualMode.isOoAvailable' in strip_comments(
                cached_text(host_path(n))
            )
            has_disabled = bool(
                re.search(
                    r"disabled:\s*!isOoAvailable",
                    strip_comments(cached_text(dual_mode_path(n))),
                )
            )
            if not (has_vif or has_disabled):
                uncovered.append(n)
        assert uncovered == [], f"二分支判据未覆盖 K{uncovered}"


class TestKBP14IsOoAvailableInHostLayer:
    """🔴 宿主 `isOoAvailable` 现算 K8 **0** / K9 1 / K11 3 / K12 2 / K13 3。"""

    EXPECTED = {8: 0, 9: 1, 11: 3, 12: 2, 13: 3}

    def test_host_hits_match_design(self) -> None:
        for n, exp in self.EXPECTED.items():
            src = strip_comments(cached_text(host_path(n)))
            c = len(re.findall(r"\bisOoAvailable\b", src))
            assert c == exp, (
                f"{K_HOSTS[n]}: isOoAvailable 期望 {exp} 处，实得 {c}"
            )

    def test_k8_host_never_references_the_symbol(self) -> None:
        """🔴 K8 宿主完全不引用该符号 ⇒ 按宿主层扫会漏它。"""
        assert self.EXPECTED[8] == 0
        src = strip_comments(cached_text(dual_mode_path(8)))
        assert len(re.findall(r"\bisOoAvailable\b", src)) > 0, (
            "K8 的 composable 侧也找不到 isOoAvailable ⇒ 符号来源不明"
        )


class TestKBP15SegmentedAfterStrip:
    """`el-segmented` 剥注释后 5 宿主各恒 1 处。"""

    def test_exactly_one_after_strip(self) -> None:
        for n in LANE2:
            stripped = strip_comments(cached_text(host_path(n)))
            c = len(re.findall(r"el-segmented", stripped))
            assert c == 1, (
                f"{K_HOSTS[n]}: 剥注释后 el-segmented 期望 1 处，实得 {c}"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 6 / BP-7：5 宿主挂 notice
# ════════════════════════════════════════════════════════════════════════════
class TestBp7NoticeMounted:
    """🔴 BP-7：5 宿主各挂 notice（按 KC-14 口径用组件名）。"""

    EXPECTED_IDS = {
        8: "xlsx/gt-k8-selling-expenses",
        9: "xlsx/gt-k9-admin-expenses",
        11: "xlsx/gt-k11-asset-impairment-loss",
        12: "xlsx/gt-k12-non-operating-income",
        13: "xlsx/gt-k13-non-operating-expense",
    }

    def test_all_five_hosts_mount_the_component(self) -> None:
        for n in LANE2:
            src = cached_text(host_path(n))
            assert NOTICE_COMPONENT in src, (
                f"{K_HOSTS[n]} 未挂 {NOTICE_COMPONENT}"
            )

    def test_import_exists(self) -> None:
        for n in LANE2:
            src = cached_text(host_path(n))
            assert re.search(rf"import\s+{NOTICE_COMPONENT}\s+from", src), (
                f"{K_HOSTS[n]} 缺 {NOTICE_COMPONENT} 的 import"
            )

    def test_entry_id_is_adjacent_to_component_name(self) -> None:
        """🔴 平台守卫正则要求 `entry-id` 紧邻组件名（中间不得插 v-if）。"""
        for n, expected in self.EXPECTED_IDS.items():
            src = cached_text(host_path(n))
            m = re.search(
                rf'<{NOTICE_COMPONENT}\s+entry-id="([^"]+)"\s*/?>', src
            )
            assert m, (
                f"{K_HOSTS[n]}: `<{NOTICE_COMPONENT} entry-id=\"...\" />` 形态不符"
            )
            assert m.group(1) == expected, (
                f"{K_HOSTS[n]}: entry-id 是 {m.group(1)!r}，期望 {expected!r}"
            )

    def test_notice_is_inside_the_mode_toolbar_block(self) -> None:
        """notice 挂在模式切换工具栏块内。"""
        for n in LANE2:
            src = strip_comments(cached_text(host_path(n)))
            lines = src.split("\n")
            seg = next(
                (i for i, l in enumerate(lines) if "el-segmented" in l), None
            )
            notice = next(
                (
                    i for i, l in enumerate(lines)
                    if NOTICE_COMPONENT in l and "import" not in l
                ),
                None,
            )
            assert seg is not None and notice is not None
            assert abs(notice - seg) <= 12, (
                f"{K_HOSTS[n]}: notice 距 el-segmented {abs(notice-seg)} 行"
                " ⇒ 不在同一工具栏块内"
            )

    def test_no_local_v_if_condition(self) -> None:
        """🔴 不加本地 v-if：已注册 bidirectional 的 entry 由组件自己返 null。"""
        for n in LANE2:
            src = cached_text(host_path(n))
            m = re.search(rf"<{NOTICE_COMPONENT}[^>]*>", src)
            assert m, f"{K_HOSTS[n]} 找不到 notice 标签"
            assert "v-if" not in m.group(0), (
                f"{K_HOSTS[n]}: notice 带本地 v-if ⇒ 会让平台守卫正则失配"
            )


class TestConfigDirectCallIsExternallyBlocked:
    """🔴 `onlyoffice-config` 直调**保留**并登记为外部依赖。"""

    def test_config_direct_call_still_exists(self) -> None:
        """5 个 composable 的 config 直调仍在（不是漏做，是卡 BP-1/BP-2）。"""
        for n in LANE2:
            src = strip_comments(cached_text(dual_mode_path(n)))
            assert "onlyoffice-config" in src, (
                f"useK{n}DualMode.ts 的 config 直调消失了 ⇒ 若已接桥须更新登记"
            )

    def test_why_not_is_documented_in_each_file(self) -> None:
        """每个文件写明为什么保留（后来者不会以为是漏做）。"""
        for n in LANE2:
            src = cached_text(dual_mode_path(n))
            assert "missing_adapter" in src, (
                f"useK{n}DualMode.ts 缺 why-not 说明"
            )
            assert "StoreProjectionNotBackedError" in src, (
                f"useK{n}DualMode.ts 未指出 flushHtml 会抛什么"
            )

    def test_backend_registry_has_zero_k_adapter(self) -> None:
        """两侧都验：后端 registry 对 K 循环 0 命中（why-not 的事实依据）。"""
        registry = (
            ROOT / "backend/app/services/workpaper_sync/adapters/registry.py"
        )
        assert registry.exists()
        src = registry.read_text(encoding="utf-8")
        for n in K_INDEXES:
            assert f"gt-k{n}-" not in src, (
                f"registry 出现 gt-k{n}- ⇒ K 循环已有 adapter，why-not 须撤"
            )
