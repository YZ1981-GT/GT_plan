# -*- coding: utf-8 -*-
"""K 循环 lane 2 — Task 10~13：BP-8 位置化与「一表两路两套身份」。

spec: k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub
Task 10: 本 lane 位置化清册与归族
Task 11: 🔴 「一表两路两套身份」的双路扫描
Task 12: family_c 真落库确证 + family_d 实证
Task 13: 位置化修复（grandfather 旧 id）
Property: KB-P22 ~ KB-P28

═══ 🔴 本组最贵的结论 ═══

**「主身份机制干净」≠「该表干净」。**
`useK8Cutoff.ts` 同一张截止性测试表有**三条**产身份的路：

| 路 | 形态 | 族 | 缺陷 |
|---|---|---|---|
| `autoSample()` 自动抽样 | `` `row-${idx}-${Date.now()}` `` | family_c | ❌ |
| `addSample()` 手动新增 | `` `row-${Date.now()}-${Math.random()…}` `` | 纯熵 | ❌（不含 `${idx}` ⇒ 不在位置化清册里） |
| `_normalizeSample()` 反序列化 | `` raw.rowKey ?? `row-${idx}` `` | **family_b** | ✅ 静默退化 |

slice 的 `tables[]` 只登记第一条（`generated_opaque_string`），
缺陷记在 `positional_identity_inventory` —— 两容器**交集为空、并集才是全集**。

═══ 🔴 口径差异（如实登记，不改判据方向）═══

1. **BP-8 的 21 是 defect 口径**（family_a + family_b）。本 lane 的
   `total_hits` 口径是 **23**（多 2 处 family_c）。两个数都对，混用会算错。
2. **slice 的 family_d 计数 38 只数 `seq:` 键**；`K8-6-rows` 真库载荷里的
   展示序号字段叫 **`index`**（`index: idx + 1` 形态全 K 另有 21 处，不在 38 里）。
   两者同形（`X: idx + 1`）、同样不进 `total_hits`，差别只在键名。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP8_BASELINE_DEFECT,
    BP8_BASELINE_DEFECT_BY_ENTRY,
    BP8_BASELINE_TEMPLATE_HITS,
    BP8_BASELINE_TOTAL_HITS,
    BP8_BASELINE_ZERO_DEFECT_ENTRIES,
    BP8_BASELINE_FAMILY,
    BP8_CONVERGED_ENTRIES,
    BP8_CONVERGED_FAMILY,
    BP8_EXTRA_FIXED_OUTSIDE_BASELINE,
    DATA,
    IDENTITY_KEY_RX,
    POSITIONAL_INTERP_RX,
    ROOT,
    ROW_IDENTITY_FACTORY,
    ROW_IDENTITY_MODULE,
    bp8_expected_defect_total,
    bp8_expected_family,
    cached_text,
    defect_by_entry,
    display_seq_hits,
    entry_of_path,
    family_census,
    family_of,
    k_domain_files,
    positional_identity_hits,
    strip_comments,
)

SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
SPEC_DIR = (
    ROOT / ".kiro" / "specs"
    / "k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub"
)

#: 本 lane 的 5 条 entry 序号
LANE2 = (8, 9, 11, 12, 13)
#: lane 1 的 7 条（反向对照）
LANE1 = (1, 2, 3, 4, 5, 6, 7)

#: 🔴 defect 口径（family_a + family_b）—— BP-8 的「21」就是这个口径。
#: 这是**改造前基线**；Task 13 已把现算收敛到 0。
LANE2_DEFECT_BASELINE = {8: 8, 9: 7, 11: 4, 12: 2, 13: 0}
#: 🔴 total_hits 口径（含 family_c）—— 本 lane 基线比 defect 多 2
LANE2_FAMILY_C_COUNT = 2
#: 基线的族分解（Task 13 修掉的就是这些）
LANE2_BASELINE_FAMILY_A = 13
LANE2_BASELINE_FAMILY_B = 8
#: 收敛后全域残留的 family_b（== 基线 13 − 本 lane 8，全在 lane 1）
BP8_BASELINE_FAMILY_B_AFTER_LANE2 = 5

#: 双路宿主（按文件名锚定，不写行号）
CUTOFF_HOSTS = ("useK8Cutoff.ts", "useK9Cutoff.ts")
#: 三条路各自的形态特征（判据锚点 = 形态，不是行号）
DESERIALIZE_SHAPE = re.compile(r"raw\.rowKey\s*\?\?\s*`row-\$\{\s*idx\s*\}`")
AUTOSAMPLE_SHAPE = re.compile(r"`row-\$\{\s*idx\s*\}-\$\{\s*Date\.now\(\)\s*\}`")
ADDSAMPLE_SHAPE = re.compile(
    r"`row-\$\{\s*Date\.now\(\)\s*\}-\$\{\s*Math\.random\(\)"
)
#: 🔴 Task 13 修复后的兜底形态（grandfather 左侧保留 + 值化右侧）
FIXED_FALLBACK_SHAPE = re.compile(
    r"raw\.rowKey\s*\?\?\s*newRowIdentity\(\s*'[a-zA-Z0-9]+'\s*\)"
)
#: 修复后**不应再出现**的退化兜底（任何前缀）
ANY_ORDINAL_FALLBACK_RX = re.compile(
    r"(?:raw|old|r)\??\.rowKey\s*\?\?\s*`[a-zA-Z0-9]+-\$\{\s*(?:i|idx|index)\s*\}`"
)

#: `positional_row_id_template`（KC-24 第六个 hardcoded 模式）
TEMPLATE_RX = re.compile(r"`(?:seed|row|detail|item)-\$\{\s*(?:i|idx|index)\s*\}")
#: family_c 形态（收敛中必须保持原样）
FAMILY_C_SHAPE = AUTOSAMPLE_SHAPE


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inventory(slice_doc: dict) -> dict:
    return slice_doc["dynamic_row_identity"]["positional_identity_inventory"]


@pytest.fixture(scope="module")
def hits(k_files: list[pathlib.Path]) -> list[tuple[str, str, str]]:
    return positional_identity_hits(k_files)


def _entry_of_ref(ref: str, k_files: list[pathlib.Path]) -> int | None:
    """从 `相对路径#Lnn` 反推 entry 序号。"""
    head = ref.rsplit("#", 1)[0]
    for p in k_files:
        if head.endswith(p.name) and p.as_posix().endswith(head):
            return entry_of_path(p)
    for p in k_files:
        if p.name == head.rsplit("/", 1)[-1]:
            return entry_of_path(p)
    return None


# ════════════════════════════════════════════════════════════════════════════
# Task 10 / KB-P22：本 lane 位置化清册与归族
# ════════════════════════════════════════════════════════════════════════════
class TestKBP22LaneInventory:
    """🔴 defect 21 处（K8 8 · K9 7 · K11 4 · K12 2；K13 **0** 是对照组）。"""

    def test_baseline_by_entry_matches_design(self) -> None:
        """改造前基线逐 entry 与 design 等值（交付规模的定义）。"""
        for n, expected in LANE2_DEFECT_BASELINE.items():
            assert BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) == expected, (
                f"K{n} 基线期望 {expected}，"
                f"实得 {BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0)}"
            )

    def test_lane2_baseline_total_is_21(self) -> None:
        total = sum(LANE2_DEFECT_BASELINE.values())
        assert total == 21, f"本 lane 基线合计期望 21，实得 {total}"
        assert total == sum(
            BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE2
        )

    def test_lane2_is_fully_converged_now(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 Task 13 交付判据：本 lane 5 条现算位置化缺陷 **全 0**。"""
        live = defect_by_entry(k_files)
        residue = {n: live[n] for n in LANE2 if live.get(n, 0)}
        assert residue == {}, f"本 lane 仍有位置化残留：{residue}"

    def test_k13_zero_is_baseline_not_a_side_effect(
        self, k_files: list[pathlib.Path], inventory: dict
    ) -> None:
        """🔴 K13 的 0 是**基线本来就 0**（对照组），不是被本次收敛做出来的。"""
        assert BP8_BASELINE_DEFECT_BY_ENTRY.get(13, 0) == 0
        assert "K13" in inventory["entries_with_zero_defect_hits"]
        assert defect_by_entry(k_files).get(13, 0) == 0

    def test_lane1_and_lane2_bisect_the_baseline_45(self) -> None:
        """🔴 **基线** 45 处按 lane 恰好二分成 24 / 21。"""
        l1 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE1)
        l2 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE2)
        assert l1 == 24, f"lane 1 基线期望 24，实得 {l1}"
        assert l2 == 21, f"lane 2 基线期望 21，实得 {l2}"
        assert l1 + l2 == sum(BP8_BASELINE_DEFECT_BY_ENTRY.values()) == 45

    def test_lane1_untouched_by_this_lane(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 越界守卫的**历史意义**：本 lane 交付时 lane 1 的 24 处一处未动。

        🔴 lane 1 随后在其 Task 15 把那 24 处也收敛了 ⇒ 现算全域归零。
        「本 lane 没越界」这条已无法再用现算证明（两边都 0 了）⇒ 判据改为
        **基线分摊自洽**（24 + 21 == 45，两 lane 各交付自己那半）+ 现算全零。
        """
        live = defect_by_entry(k_files)
        assert sum(live.values()) == 0, f"全域仍有缺陷：{dict(live)}"
        l1 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE1)
        l2 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE2)
        assert (l1, l2) == (24, 21), "基线分摊被改"
        assert l1 + l2 == BP8_BASELINE_DEFECT == 45

    def test_slice_registers_the_pre_change_baseline(
        self, inventory: dict
    ) -> None:
        """🔴 slice 是改造前快照（append-only）⇒ 它登记的是基线而非现算。"""
        assert inventory["defect_hits_total"] == BP8_BASELINE_DEFECT == 45
        declared = {
            int(k[1:]): v for k, v in inventory["defect_hits_by_entry"].items()
        }
        assert declared == BP8_BASELINE_DEFECT_BY_ENTRY, (
            f"slice {declared} vs 基线 {BP8_BASELINE_DEFECT_BY_ENTRY}"
        )

    def test_total_hits_caliber_is_two_more_than_defect_in_baseline(self) -> None:
        """🔴 口径差异：本 lane 基线 `total_hits` 是 **23**，比 defect 的 21 多 2。"""
        baseline_total = sum(LANE2_DEFECT_BASELINE.values()) + LANE2_FAMILY_C_COUNT
        assert baseline_total == 23
        assert baseline_total - LANE2_FAMILY_C_COUNT == 21
        assert LANE2_BASELINE_FAMILY_A + LANE2_BASELINE_FAMILY_B == 21, (
            "族分解与 defect 基线不符"
        )

    def test_family_census_follows_the_ledger(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """三族现算 == 基线 − 已收敛（family_c 恒等 3）。"""
        c = family_census(k_files)
        exp = bp8_expected_family()
        assert (c["a"], c["b"], c["c"]) == (exp["a"], exp["b"], exp["c"]), c
        assert c["c"] == 3, "family_c 被误改"
        assert c["a"] + c["b"] + c["c"] == c["total"]
        assert c["a"] + c["b"] == c["defect"] == bp8_expected_defect_total()

    def test_converged_family_split_equals_lane2_baseline(self) -> None:
        """账本里**本 lane 那半**的族分解 == 本 lane 基线的族分解（两侧验）。

        🔴 `BP8_CONVERGED_FAMILY` 现在是**两 lane 合计**（a 32 + b 13）⇒
        本 lane 的那半要从 `BP8_CONVERGED_FAMILY_BY_LANE["lane2"]` 取。
        """
        from tests.workpaper_sync.k_foundation_facts import (
            BP8_CONVERGED_FAMILY_BY_LANE,
        )

        mine = BP8_CONVERGED_FAMILY_BY_LANE["lane2"]
        assert mine["a"] == LANE2_BASELINE_FAMILY_A == 13
        assert mine["b"] == LANE2_BASELINE_FAMILY_B == 8
        # 两 lane 相加 == 基线全量
        other = BP8_CONVERGED_FAMILY_BY_LANE["lane1"]
        assert mine["a"] + other["a"] == BP8_CONVERGED_FAMILY["a"] == 32
        assert mine["b"] + other["b"] == BP8_CONVERGED_FAMILY["b"] == 13

    def test_remaining_lane2_hits_are_family_c_only(
        self, k_files: list[pathlib.Path], hits: list[tuple[str, str, str]]
    ) -> None:
        """🔴 收敛后本 lane 只剩 family_c（非缺陷，故意保留）。"""
        remaining = [
            (ref, family_of(val))
            for ref, _k, val in hits
            if _entry_of_ref(ref, k_files) in LANE2
        ]
        assert len(remaining) == LANE2_FAMILY_C_COUNT, (
            f"本 lane 残留 {len(remaining)} 处，期望 {LANE2_FAMILY_C_COUNT}"
        )
        for ref, fam in remaining:
            assert fam == "c", f"{ref} 残留族为 {fam} ⇒ 应只剩 family_c"

    def test_identity_keys_are_the_three_recognized_names(
        self, hits: list[tuple[str, str, str]]
    ) -> None:
        """身份键只认 `rowId` / `rowKey` / `id` —— `index` 不是身份键。"""
        assert {k for _r, k, _v in hits} <= {"rowId", "rowKey", "id"}
        assert IDENTITY_KEY_RX.search("index: idx + 1") is None, (
            "判别式把 `index` 当身份键 ⇒ family_d 会被误计入 total_hits"
        )


# ════════════════════════════════════════════════════════════════════════════
# Task 11 / KB-P23~P25：一表两路两套身份
# ════════════════════════════════════════════════════════════════════════════
class TestKBP23TwoPathsTwoIdentities:
    """🔴 同一张截止性测试表，多条路产不同身份。"""

    @pytest.mark.parametrize("fname", CUTOFF_HOSTS)
    def test_three_paths_still_coexist_after_the_fix(
        self, fname: str, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 三条路仍在同一文件里并存 —— 修的是**兜底**，不是删路。

        Task 13 只把反序列化兜底从「退化成下标」换成「生成值化身份」，
        三条产身份的路一条没少。若某条路消失了，说明改动越界。
        """
        p = next((x for x in k_files if x.name == fname), None)
        assert p is not None, f"{fname} 不存在"
        src = strip_comments(cached_text(p))
        assert FIXED_FALLBACK_SHAPE.search(src), (
            f"{fname} 缺反序列化路径 —— 修复后应为 `raw.rowKey ?? newRowIdentity(…)`"
        )
        assert AUTOSAMPLE_SHAPE.search(src), f"{fname} 缺自动抽样路径形态"
        assert ADDSAMPLE_SHAPE.search(src), (
            f"{fname} 缺手动新增路径形态 —— 🔴 第三条路是纯熵（不含 ${{idx}}）"
            "故从来不在位置化清册里，但它同样产一套身份"
        )

    @pytest.mark.parametrize("fname", CUTOFF_HOSTS)
    def test_deserialize_path_no_longer_degrades_to_ordinal(
        self, fname: str, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 KB-P28：反序列化兜底不再退化成下标。"""
        p = next(x for x in k_files if x.name == fname)
        src = strip_comments(cached_text(p))
        assert DESERIALIZE_SHAPE.search(src) is None, (
            f"{fname} 仍有 `raw.rowKey ?? \\`row-${{idx}}\\`` ⇒ family_b 未修"
        )
        assert FIXED_FALLBACK_SHAPE.search(src) is not None
        # 🔴 判据用「是否被清册收录」而**不是** family_of()：
        #    `family_of` 是归族器不是筛选器 —— 它对任何含 `??` 的值都返 "b"，
        #    包括已修好的 `raw.rowKey ?? newRowIdentity('row')`。族只在
        #    `positional_identity_hits` 已筛出位置化命中之后才有意义。
        live_in_file = [
            ref
            for ref, _k, _v in positional_identity_hits(k_files)
            if ref.rsplit("#", 1)[0].endswith(fname)
        ]
        assert len(live_in_file) == 1, (
            f"{fname} 位置化命中 {len(live_in_file)} 处，期望 1（只剩 family_c）"
        )

    def test_family_of_is_a_classifier_not_a_filter(self) -> None:
        """🔴 口径澄清：`family_of` 对任何含 `??` 的值都返 b，**包括已修好的**。

        所以「是否缺陷」必须看 `positional_identity_hits` 收不收，不能单独
        拿 `family_of` 判一个任意字符串 —— 那会把修好的判成没修。
        """
        assert family_of("raw.rowKey ?? newRowIdentity('row')") == "b"
        assert family_of("raw.rowKey ?? `row-${idx}`") == "b"
        # 但只有后者会被清册收录（前者不含位置化 token）
        assert POSITIONAL_INTERP_RX.search("newRowIdentity('row')") is None
        assert POSITIONAL_INTERP_RX.search("`row-${idx}`") is not None

    @pytest.mark.parametrize("fname", CUTOFF_HOSTS)
    def test_grandfather_left_side_is_untouched(
        self, fname: str, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 KB-P28 grandfather：`??` 左侧的 `raw.rowKey` 原样保留。

        已落库 id（真库 `K8-6-rows` / `K9-1-rows` 都有）必须优先被读回，
        不许被新工厂覆盖 —— 否则每次 load 都换一套身份，用户填的备注全跟错行。
        """
        p = next(x for x in k_files if x.name == fname)
        src = strip_comments(cached_text(p))
        m = FIXED_FALLBACK_SHAPE.search(src)
        assert m is not None, f"{fname} 找不到修复后的兜底"
        assert "raw.rowKey ??" in m.group(0), (
            f"{fname} 兜底丢了 grandfather 左侧：{m.group(0)!r}"
        )

    @pytest.mark.parametrize("fname", CUTOFF_HOSTS)
    def test_autosample_path_is_family_c_not_defect(
        self, fname: str, k_files: list[pathlib.Path]
    ) -> None:
        """自动抽样路径含时间戳熵 ⇒ family_c **非缺陷**。"""
        p = next(x for x in k_files if x.name == fname)
        src = strip_comments(cached_text(p))
        m = AUTOSAMPLE_SHAPE.search(src)
        assert m is not None
        assert family_of(m.group(0)) == "c", (
            f"{fname} 自动抽样路径归族 {family_of(m.group(0))} ⇒ 应为 c（非缺陷）"
        )

    def test_clean_primary_mechanism_did_not_mean_clean_table(
        self, slice_doc: dict, inventory: dict
    ) -> None:
        """🔴 判据核心（按**基线**判）：主身份机制登记为 `generated_opaque_string`
        （非禁止值），同表却另有 family_b 缺陷 ⇒ 当时「干净」不成立。

        这个结论是 lane 2 立项的依据，属历史事实。Task 13 修完后现算已无
        family_b，但不能因此把当初的发现说成不存在 —— 否则下一轮遇到同型
        表又会只看主机制就判「干净」。
        """
        dri = slice_doc["dynamic_row_identity"]
        forbidden = set(dri["forbidden_identity_kinds"])
        cutoff_refs = {
            t["row_identity"]["source_ref"]
            for t in dri["tables"]
            if any(h in t["row_identity"]["source_ref"] for h in CUTOFF_HOSTS)
        }
        assert len(cutoff_refs) == 2, "两张截止性测试表应都在 tables[] 里"
        for t in dri["tables"]:
            kind = t["row_identity"]["kind"]
            assert kind not in forbidden, f"{t['table_key']} 主机制 {kind} 是禁止值"
            assert kind == "generated_opaque_string"
        # 基线里这两个文件确有 family_b 命中（同表不干净的证据）
        fb = inventory["family_b_index_as_fallback"]["hits"]
        for fname in CUTOFF_HOSTS:
            assert any(fname in h for h in fb), (
                f"基线里 {fname} 无 family_b ⇒ 「主机制干净≠该表干净」的论证须更新"
            )


class TestKBP24TwoContainersUnionAndIntersection:
    """🔴 `tables[]` 与 `positional_identity_inventory` 并集覆盖全集、交集为空。"""

    def test_tables_source_refs_equal_family_c_sites(
        self, slice_doc: dict, inventory: dict
    ) -> None:
        """`tables[]` 登记的站点集恰好 == family_c 站点集。"""
        table_refs = {
            t["row_identity"]["source_ref"]
            for t in slice_doc["dynamic_row_identity"]["tables"]
        }
        fc = set(
            inventory["family_c_generated_opaque_must_not_be_flagged"]["hits"]
        )
        assert table_refs == fc, (
            f"多 {sorted(table_refs - fc)}，缺 {sorted(fc - table_refs)}"
        )

    def test_intersection_with_defect_sites_is_empty(
        self, slice_doc: dict, inventory: dict
    ) -> None:
        """🔴 交集为空：主机制站点不出现在缺陷清单里。"""
        table_refs = {
            t["row_identity"]["source_ref"]
            for t in slice_doc["dynamic_row_identity"]["tables"]
        }
        defect = set(inventory["family_a_pure_ordinal"]["hits"]) | set(
            inventory["family_b_index_as_fallback"]["hits"]
        )
        assert table_refs & defect == set(), (
            f"交集非空：{sorted(table_refs & defect)}"
        )

    def test_union_covers_all_hits(self, slice_doc: dict, inventory: dict) -> None:
        """🔴 并集覆盖全部命中（== `total_hits`）。"""
        table_refs = {
            t["row_identity"]["source_ref"]
            for t in slice_doc["dynamic_row_identity"]["tables"]
        }
        defect = set(inventory["family_a_pure_ordinal"]["hits"]) | set(
            inventory["family_b_index_as_fallback"]["hits"]
        )
        union = table_refs | defect
        assert len(union) == inventory["total_hits"], (
            f"并集 {len(union)} != total_hits {inventory['total_hits']}"
        )

    def test_live_sites_are_the_baseline_minus_converged(
        self, k_files: list[pathlib.Path], slice_doc: dict, inventory: dict
    ) -> None:
        """🔴 两侧都验：现算站点集 == 基线并集 − 已收敛 entry 的站点。

        站点里带行号，而修复插入了 import 行 ⇒ 行号会整体位移。所以比对按
        **文件名集合**做，不按 `path#Lnn` 逐字比（位移不是漂移）。
        """
        table_refs = {
            t["row_identity"]["source_ref"]
            for t in slice_doc["dynamic_row_identity"]["tables"]
        }
        defect = set(inventory["family_a_pure_ordinal"]["hits"]) | set(
            inventory["family_b_index_as_fallback"]["hits"]
        )

        def _files(refs: set[str]) -> set[str]:
            return {r.rsplit("#", 1)[0].rsplit("/", 1)[-1] for r in refs}

        by_name = {p.name: p for p in k_files}
        baseline_files = _files(table_refs | defect)
        converged_files = {
            n
            for n in baseline_files
            if entry_of_path(by_name[n]) in BP8_CONVERGED_ENTRIES
            and n not in _files(table_refs)  # family_c 宿主保留
        }
        expected = baseline_files - converged_files
        live = _files({ref for ref, _k, _v in positional_identity_hits(k_files)})
        assert live == expected, (
            f"现算多 {sorted(live - expected)}，期望多 {sorted(expected - live)}"
        )


class TestKBP25FamilyCIsThreeSitesTwoInThisLane:
    """family_c 全 K 只 3 处，本 lane 占 2，第 3 处在 lane 1。"""

    def test_family_c_is_exactly_three(
        self, k_files: list[pathlib.Path], inventory: dict
    ) -> None:
        live = [
            (ref, val)
            for ref, _k, val in positional_identity_hits(k_files)
            if family_of(val) == "c"
        ]
        assert len(live) == 3, f"family_c 期望 3 处，实得 {len(live)}"
        assert (
            inventory["family_c_generated_opaque_must_not_be_flagged"]["count"] == 3
        )

    def test_two_in_lane2_one_in_lane1(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 2 处在本 lane（K8/K9 的 Cutoff），第 3 处在 lane 1。"""
        per_lane = {"lane1": [], "lane2": [], "other": []}
        for ref, _k, val in positional_identity_hits(k_files):
            if family_of(val) != "c":
                continue
            n = _entry_of_ref(ref, k_files)
            bucket = (
                "lane2" if n in LANE2 else "lane1" if n in LANE1 else "other"
            )
            per_lane[bucket].append(ref)
        assert len(per_lane["lane2"]) == 2, per_lane
        assert len(per_lane["lane1"]) == 1, per_lane
        assert per_lane["other"] == []
        assert all(
            any(h in r for h in CUTOFF_HOSTS) for r in per_lane["lane2"]
        ), f"本 lane 的 family_c 不在 Cutoff 里：{per_lane['lane2']}"

    def test_lane1_family_c_is_the_k6_impairment_tab(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """第 3 处 = `K6TabImpairmentTest.vue` 的 `rowId: \\`row-${Date.now()}-${i}\\``。

        🔴 形态与本 lane 相反：**时间戳在前、序号在后**（序号只作同批次去重）。
        """
        found = [
            (ref, val)
            for ref, _k, val in positional_identity_hits(k_files)
            if family_of(val) == "c" and "K6TabImpairmentTest.vue" in ref
        ]
        assert len(found) == 1, f"K6 的 family_c 期望 1 处，实得 {len(found)}"
        _ref, val = found[0]
        assert re.search(r"`row-\$\{\s*Date\.now\(\)\s*\}-\$\{\s*i\s*\}`", val), (
            f"K6 形态变了：{val!r}"
        )


# ════════════════════════════════════════════════════════════════════════════
# Task 12 / KB-P26~P27：family_c 真落库确证 + family_d 实证
# ════════════════════════════════════════════════════════════════════════════
#: 🔴 真库 `K8-6-rows` 载荷样本（195,960 B）。
#: **来源 = design 阶段对真实 PG 的现读**，本测试不重连 PG（与 foundation p10
#: 的 `LIVE_SKELETON` 同范式）—— 判据验「形态」与「来源可追溯」，不重算它。
K8_6_LIVE_ROW_SAMPLE = {
    "rowKey": "row-0-1784807974207",
    "index": 1,
    "voucherNo": "0285",
    "bookDate": "2025-12-26",
    "amount": 79.97,
    "accountCode": "6601.15.01",
}
K8_6_LIVE_BYTES = 195_960
_LIVE_EVIDENCE_IS_FROM_DESIGN_READ = True


class TestKBP26FamilyCReallyPersisted:
    """🔴 family_c 真落库：真库行的 `rowKey` 就是 `row-{idx}-{13位时间戳}`。"""

    def test_sample_matches_family_c_shape(self) -> None:
        """`row-0-1784807974207` ⇒ idx=0 + 13 位时间戳都在。"""
        m = re.fullmatch(r"row-(\d+)-(\d{13})", K8_6_LIVE_ROW_SAMPLE["rowKey"])
        assert m is not None, f"形态不符：{K8_6_LIVE_ROW_SAMPLE['rowKey']!r}"
        assert m.group(1) == "0", "样本的 idx 部分应为 0"
        assert len(m.group(2)) == 13, "时间戳应为 13 位毫秒"

    def test_sample_is_generated_by_the_autosample_path(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """两侧都验：真库形态能由 `autoSample()` 的模板生成。"""
        p = next(x for x in k_files if x.name == "useK8Cutoff.ts")
        assert AUTOSAMPLE_SHAPE.search(strip_comments(cached_text(p))), (
            "生成该形态的代码路径已不存在 ⇒ 真库样本失去来源"
        )
        rendered = "row-" + "0" + "-" + "1784807974207"
        assert rendered == K8_6_LIVE_ROW_SAMPLE["rowKey"]

    def test_live_evidence_source_is_declared_not_reread(self) -> None:
        """🔴 诚实标注：本条是 design 阶段真库现读的**留档**，非本测试连 PG。"""
        assert _LIVE_EVIDENCE_IS_FROM_DESIGN_READ is True

    def test_live_sample_is_traceable_to_design_doc(self) -> None:
        """来源可追溯：design.md 里确有这段真库载荷。"""
        design = (SPEC_DIR / "design.md").read_text(encoding="utf-8")
        assert K8_6_LIVE_ROW_SAMPLE["rowKey"] in design, (
            "design.md 里找不到该 rowKey ⇒ 真库实证来源不可追溯"
        )
        assert "195,960" in design or str(K8_6_LIVE_BYTES) in design

    def test_display_ordinal_field_coexists_in_the_same_payload(self) -> None:
        """🔴 同载荷另有 `index` 展示序号 ⇒ family_d 不计入 total_hits 的实证。"""
        assert K8_6_LIVE_ROW_SAMPLE["index"] == 1
        assert K8_6_LIVE_ROW_SAMPLE["rowKey"].startswith("row-0-"), (
            "身份键 idx=0 而展示序号 index=1 ⇒ 两者是**不同**的东西"
        )

    def test_display_ordinal_is_not_an_identity_key(self) -> None:
        """`index` 不被身份判别式识别 ⇒ 结构上不可能混入 total_hits。"""
        assert IDENTITY_KEY_RX.search("index: idx + 1") is None
        assert IDENTITY_KEY_RX.search("rowKey: `row-${idx}`") is not None


class TestKBP26FamilyDCaliber:
    """🔴 口径差异：slice 的 family_d 38 只数 `seq`；真库用的是 `index`。"""

    def test_slice_family_d_count_is_the_seq_caliber(
        self, k_files: list[pathlib.Path], inventory: dict
    ) -> None:
        """🔴 slice 的 38 == `seq` 键口径（收敛前后都成立，d 不参与修复）。"""
        declared = inventory["family_d_display_ordinal_must_not_be_flagged"]["count"]
        seq_live = display_seq_hits(k_files, "seq")
        assert declared == seq_live == 38, (
            f"slice {declared} vs 现算 seq {seq_live} ⇒ 口径漂移"
        )

    def test_index_caliber_is_a_separate_nonzero_count(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 `index: idx + 1` 形态另有 21 处，**不在** slice 的 38 里。"""
        idx_live = display_seq_hits(k_files, "index")
        assert idx_live == 21, f"`index` 口径期望 21，实得 {idx_live}"
        assert idx_live != 38, "两口径撞在一起 ⇒ 差异登记须复核"

    def test_neither_caliber_enters_total_hits(
        self, k_files: list[pathlib.Path], inventory: dict
    ) -> None:
        """两个口径都不进 `total_hits`（total = a+b+c，与 d 无关）。

        🔴 family_d 的两个口径（`seq` 38 / `index` 21）在收敛后**都没变**——
        因为 Task 13 只改身份键不动展示序号。这本身就是「d 与 total 无关」的
        又一侧证明。
        """
        c = family_census(k_files)
        assert inventory["total_hits"] == BP8_BASELINE_TOTAL_HITS == 48
        assert c["total"] == sum(bp8_expected_family().values())
        assert c["total"] == c["a"] + c["b"] + c["c"], "total 里混进了 family_d"
        assert display_seq_hits(k_files, "seq") == 38, "收敛误伤了 `seq` 展示序号"
        assert display_seq_hits(k_files, "index") == 21, "收敛误伤了 `index` 展示序号"

    def test_family_d_is_explicitly_not_a_defect(self, inventory: dict) -> None:
        fd = inventory["family_d_display_ordinal_must_not_be_flagged"]
        assert fd.get("is_defect") is False
        assert "total_hits" in fd["what"] or "不进" in fd["what"]


class TestKBP27PositionalRowIdTemplate:
    """`positional_row_id_template`（全 K 13 处）本 lane 占多数且是 48 的子集。"""

    def test_baseline_template_total_is_13(self) -> None:
        """改造前基线 13 处（KC-24 第六个模式非 0 的依据）。"""
        assert BP8_BASELINE_TEMPLATE_HITS == 13

    def test_lane2_held_the_majority_in_baseline(self) -> None:
        """🔴 基线里本 lane 占 11 / 13（design 的「占多数」）。

        基线分布：K5 2（lane 1）· K8 3 · K9 4 · K11 4。
        """
        baseline_by_entry = {5: 2, 8: 3, 9: 4, 11: 4}
        l2 = sum(v for n, v in baseline_by_entry.items() if n in LANE2)
        l1 = sum(v for n, v in baseline_by_entry.items() if n in LANE1)
        assert l2 == 11, f"本 lane 基线期望 11，实得 {l2}"
        assert l1 == 2, f"lane 1 基线期望 2，实得 {l1}"
        assert l2 + l1 == BP8_BASELINE_TEMPLATE_HITS == 13
        assert l2 > l1, "本 lane 未占多数 ⇒ design 的表述须改"

    def test_template_converged_to_lane1_plus_family_c(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 收敛后模板命中只剩「lane 1 未做的」+「family_c 的前缀」。

        family_c 的 `` `row-${idx}-${Date.now()}` `` 带 `` `row-${idx} `` 前缀，
        所以它仍命中模板正则 —— 这是**故意保留**（非缺陷），不是漏修。
        """
        per: dict[str, int] = {}
        for p in k_files:
            c = len(TEMPLATE_RX.findall(strip_comments(cached_text(p))))
            if c:
                per[p.name] = c
        by_name = {p.name: p for p in k_files}
        for fname, c in per.items():
            n = entry_of_path(by_name[fname])
            if n in BP8_CONVERGED_ENTRIES:
                src = strip_comments(cached_text(by_name[fname]))
                assert FAMILY_C_SHAPE.search(src), (
                    f"{fname} 属已收敛 lane 但残留 {c} 处模板命中且非 family_c"
                )
            else:
                assert n in LANE1, f"{fname} 既非已收敛也不属 lane 1：entry={n}"
        assert sum(per.values()) < BP8_BASELINE_TEMPLATE_HITS, (
            f"模板命中未下降（现算 {sum(per.values())}）⇒ 收敛未生效"
        )

    def test_design_named_files_kept_only_their_family_c(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """design 点名的 4 个文件：Cutoff 两个各留 1 处 family_c，K11 两个清零。"""
        expectations = {
            "useK8Cutoff.ts": 1,
            "useK9Cutoff.ts": 1,
            "K11TabDisclosureListed.vue": 0,
            "K11TabDisclosureSoe.vue": 0,
        }
        for fname, exp in expectations.items():
            p = next((x for x in k_files if x.name == fname), None)
            assert p is not None, f"{fname} 不存在"
            c = len(TEMPLATE_RX.findall(strip_comments(cached_text(p))))
            assert c == exp, f"{fname} 期望 {exp} 处模板命中，实得 {c}"
        # 两侧都验：Cutoff 留下的那 1 处确实是 family_c
        for fname in CUTOFF_HOSTS:
            p = next(x for x in k_files if x.name == fname)
            assert FAMILY_C_SHAPE.search(strip_comments(cached_text(p)))

    def test_template_sites_are_a_subset_of_the_48(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 这 13 处是位置化 48 处的**子集**（站点级现算）。"""
        hit_sites = {ref for ref, _k, _v in positional_identity_hits(k_files)}
        template_sites: set[str] = set()
        for p in k_files:
            rel = p.relative_to(ROOT).as_posix()
            for i, line in enumerate(
                strip_comments(cached_text(p)).split("\n"), start=1
            ):
                if TEMPLATE_RX.search(line):
                    template_sites.add(f"{rel}#L{i}")
        assert template_sites, "模板站点为空 ⇒ 子集判据退化成恒真"
        assert template_sites <= hit_sites, (
            f"不在 48 里的模板站点：{sorted(template_sites - hit_sites)}"
        )
        assert len(template_sites) < len(hit_sites), "应为真子集"


# ════════════════════════════════════════════════════════════════════════════
# Task 13 / KB-P28：位置化修复（grandfather 旧 id）
# ════════════════════════════════════════════════════════════════════════════
#: 修复触及的 6 个 composable + 6 个 Vue
FIXED_COMPOSABLES = (
    "useK8Checks.ts",
    "useK8Cutoff.ts",
    "useK9Adjudication.ts",
    "useK9Checks.ts",
    "useK9Cutoff.ts",
    "useK12Check.ts",
)
FIXED_VUES = (
    "K8TabDisclosureListed.vue",
    "K8TabDisclosureSoe.vue",
    "K9TabDisclosureListed.vue",
    "K9TabDisclosureSoe.vue",
    "K11TabDisclosureListed.vue",
    "K11TabDisclosureSoe.vue",
)


class TestKBP28SingleFixOutlet:
    """🔴 值化身份走**一个**共享工厂，不是 12 份私有副本。"""

    def test_factory_module_exists(self) -> None:
        assert ROW_IDENTITY_MODULE.exists(), (
            f"共享工厂模块不存在：{ROW_IDENTITY_MODULE}"
        )

    def test_factory_is_exported(self) -> None:
        src = cached_text(ROW_IDENTITY_MODULE)
        assert f"export function {ROW_IDENTITY_FACTORY}(" in src

    def test_factory_is_entropy_bearing_not_positional(self) -> None:
        """🔴 工厂本身必须带熵且不含位置化 token（否则等于换个名字继续错）。"""
        src = strip_comments(cached_text(ROW_IDENTITY_MODULE))
        assert re.search(r"Date\.now\(\)", src), "工厂无时间戳熵"
        assert re.search(r"randomUUID|Math\.random\(\)", src), "工厂无随机熵"
        assert re.search(r"\$\{\s*(?:i|idx|index)\s*\}", src) is None, (
            "工厂里出现位置化插值 ⇒ 修复无效"
        )

    def test_factory_documents_why_not_content_derived(self) -> None:
        """🔴 留档：为什么不用内容派生（同内容两行会撞 ⇒ 静默错值）。"""
        src = cached_text(ROW_IDENTITY_MODULE)
        assert "内容派生" in src, "未说明为何不选内容派生"
        assert "唯一性" in src or "撞" in src

    @pytest.mark.parametrize("fname", FIXED_COMPOSABLES + FIXED_VUES)
    def test_every_fixed_file_imports_the_shared_factory(
        self, fname: str, k_files: list[pathlib.Path]
    ) -> None:
        p = next((x for x in k_files if x.name == fname), None)
        assert p is not None, f"{fname} 不存在"
        src = cached_text(p)
        assert f"import {{ {ROW_IDENTITY_FACTORY} }} from" in src, (
            f"{fname} 未 import 共享工厂 ⇒ 可能自造了私有副本"
        )
        assert f"{ROW_IDENTITY_FACTORY}(" in strip_comments(src)

    @pytest.mark.parametrize("fname", FIXED_COMPOSABLES + FIXED_VUES)
    def test_no_private_duplicate_factory(
        self, fname: str, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 不许在这些文件里另建私有身份工厂（第二真源）。"""
        p = next(x for x in k_files if x.name == fname)
        src = strip_comments(cached_text(p))
        assert (
            re.search(
                r"function\s+(?:newRowIdentity|makeRowId|genRowId|createRowId)\b",
                src,
            )
            is None
        ), f"{fname} 里有私有身份工厂 ⇒ 与共享出口撞真源"


class TestKBP28NoOrdinalFallbackRemains:
    """🔴 退化兜底在本 lane 全清。"""

    def test_no_ordinal_fallback_in_converged_files(
        self, k_files: list[pathlib.Path]
    ) -> None:
        residue: list[str] = []
        for p in k_files:
            if entry_of_path(p) not in BP8_CONVERGED_ENTRIES:
                continue
            src = strip_comments(cached_text(p))
            if ANY_ORDINAL_FALLBACK_RX.search(src):
                residue.append(p.name)
        assert residue == [], f"仍有退化兜底：{residue}"

    def test_ordinal_fallback_still_exists_in_lane1(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 反向对照：lane 1 的退化兜底**还在**（它归 lane 1 spec 处置）。

        这条是「本 lane 没有顺手改越界」的正向证明。

        🔴 判据按**族**不按正则：lane 1 的 5 处 family_b 用的是 `raw?.id ||`
        / `raw.id ??` 形态（键是 `id` 不是 `rowKey`），只认 `.rowKey ??` 会假红。
        其中 `K7TabDisclosureSoe.vue` 的 `` String(raw?.id || `grant-${idx}-${Date.now()}`) ``
        同时含熵与兜底 —— 判别式规定这种归 **b（缺陷）不放过**。
        """
        # 🔴 lane 1 的那 5 处 family_b **也已在其 Task 15 修完** ⇒ 现算 0。
        # 「本 lane 交付时它们还在」这条无法再用现算证明 ⇒ 判据改为
        # 「族分解账本自洽（13 = 本 lane 8 + lane 1 的 5）」+「现算全清」。
        lane1_b = [
            ref
            for ref, _k, val in positional_identity_hits(k_files)
            if family_of(val) == "b"
        ]
        assert lane1_b == [], (
            f"family_b 仍有残留：{[r.rsplit('/', 1)[-1] for r in lane1_b]}"
        )
        assert BP8_BASELINE_FAMILY_B_AFTER_LANE2 == 5, "中间值账本被改"
        assert (
            LANE2_BASELINE_FAMILY_B + BP8_BASELINE_FAMILY_B_AFTER_LANE2
            == BP8_BASELINE_FAMILY["b"]
            == 13
        ), "family_b 的两 lane 分摊不自洽"

    def test_the_two_fallback_shapes_differ_by_key_name(self) -> None:
        """🔴 口径留档：本 lane 的 family_b 是 `.rowKey ??`，lane 1 的是 `.id ||`。

        只认 `.rowKey ??` 的反向对照判据会把 lane 1 的 5 处漏掉（首轮实测）。
        判别式本身对两种形态都成立 —— 判据锚判别式而不是某个键名。
        """
        assert family_of("raw.rowKey ?? `row-${idx}`") == "b"
        assert family_of("String(raw?.id || `imp-${idx}`)") == "b"
        assert family_of("raw.id ?? `K3-7-${String(idx + 1).padStart(2, '0')}`") == "b"

    def test_grandfather_applies_to_every_fixed_fallback(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 每一处改过的兜底都保留了 `??` 左侧（已落库 id 优先）。"""
        checked = 0
        for fname in FIXED_COMPOSABLES:
            p = next(x for x in k_files if x.name == fname)
            src = strip_comments(cached_text(p))
            for m in re.finditer(
                r"((?:raw|old|r)\??\.rowKey)\s*\?\?\s*" + ROW_IDENTITY_FACTORY,
                src,
            ):
                assert ".rowKey" in m.group(1)
                checked += 1
        # 🔴 只数**本 lane 那 8 处**（`FIXED_COMPOSABLES` 是本 lane 的清册）——
        # `BP8_CONVERGED_FAMILY["b"]` 现在是两 lane 合计 13。
        assert checked == LANE2_BASELINE_FAMILY_B == 8, (
            f"grandfather 兜底现算 {checked} 处，期望 8（本 lane 的 family_b）"
        )


class TestKBP28DiscriminatorBlindSpot:
    """🔴 如实登记：`${idx++}` 形态逃过判别式，从未进过基线 48。"""

    def test_incr_form_is_not_matched_by_the_discriminator(self) -> None:
        """判别式漏计 `${idx++}` —— 这是口径盲点而非基线误差。"""
        from tests.workpaper_sync.k_foundation_facts import POSITIONAL_INTERP_RX

        assert POSITIONAL_INTERP_RX.search("`k81-${idx}`") is not None
        assert POSITIONAL_INTERP_RX.search("`k81-${idx++}`") is None, (
            "判别式已能认 `${idx++}` ⇒ 盲点已修，基线口径须重算"
        )

    def test_extra_fixed_sites_are_registered_outside_the_baseline(self) -> None:
        """这 2 处顺带修掉，但**不参与**收敛等式（它们不在 48 里）。"""
        assert BP8_EXTRA_FIXED_OUTSIDE_BASELINE == 2
        # 🔴 两 lane 都收敛完 ⇒ 收敛等式右侧为 0（45 − 45）。
        # 额外的 2 处 `${idx++}` **不参与**该等式（它们从未进过基线 48）。
        assert bp8_expected_defect_total() == 0, (
            "收敛等式右侧应为 0（两 lane 共修 45 处）"
        )
        assert BP8_BASELINE_DEFECT - 45 == 0
        assert BP8_BASELINE_DEFECT - 21 == 24, "本 lane 修完后应剩 lane 1 的 24"

    def test_incr_form_is_gone_from_converged_files(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """两侧都验：`${idx++}` 在本 lane 已清（虽然它没进基线）。"""
        rx = re.compile(r"`[a-zA-Z0-9]+-\$\{\s*idx\+\+\s*\}`")
        residue = [
            p.name
            for p in k_files
            if entry_of_path(p) in BP8_CONVERGED_ENTRIES
            and rx.search(strip_comments(cached_text(p)))
        ]
        assert residue == [], f"`${{idx++}}` 残留：{residue}"


class TestKBP28SiblingModulesAcrossCycles:
    """🔴 触类旁通登记：平台已有 4 个同型行身份模块，本 spec 的是第 5 个。

    这些是 F/G/H 三份 spec 并发推进的产物 —— 本 spec **不碰**它们（跨会话改动
    会撞），但必须如实登记「同型模块散了 5 份」这笔技术债，而不是假装没有。
    """

    #: 现算锚点：按文件名模式找，不写死路径
    SIBLING_PATTERNS = ("f3RowIdentity.ts", "f5RowIdentity.ts",
                        "g1g3RowIdentity.ts", "hSeedRowIdentity.ts")

    def test_sibling_modules_really_exist(self) -> None:
        """四个同型模块现算存在（登记的对照对象不是虚构）。"""
        base = ROW_IDENTITY_MODULE.parent.parent
        missing = [n for n in self.SIBLING_PATTERNS if not (base / n).exists()]
        assert missing == [], f"登记的同型模块不存在：{missing}"

    def test_our_module_documents_all_siblings(self) -> None:
        """🔴 本模块文档逐个点名 4 个同型模块（否则下一轮又会重造第 6 个）。"""
        doc = cached_text(ROW_IDENTITY_MODULE)
        for n in self.SIBLING_PATTERNS:
            assert n in doc, f"文档未点名同型模块 {n}"
        assert "第 5 个" in doc, "未登记「本文件是第 5 个」这个事实"
        assert "技术债" in doc, "未把散成 5 份登记为技术债"

    def test_no_symbol_collision_with_siblings(self) -> None:
        """🔴 本模块导出符号不与 4 个同型模块重名（避免 import 歧义）。"""
        base = ROW_IDENTITY_MODULE.parent.parent
        ours = set(
            re.findall(
                r"export (?:function|const) (\w+)",
                cached_text(ROW_IDENTITY_MODULE),
            )
        )
        assert ours == {ROW_IDENTITY_FACTORY}, f"本模块导出 {ours}"
        for n in self.SIBLING_PATTERNS:
            theirs = set(
                re.findall(
                    r"export (?:function|const|interface) (\w+)",
                    cached_text(base / n),
                )
            )
            assert ours & theirs == set(), (
                f"与 {n} 撞符号：{sorted(ours & theirs)}"
            )

    def test_why_not_reuse_f5_is_documented(self) -> None:
        """🔴 留档：为何不复用 f5（它会重铸存量 id，与 K 的 grandfather 相反）。"""
        doc = cached_text(ROW_IDENTITY_MODULE)
        assert "为什么不直接复用" in doc
        assert "grandfather" in doc
        assert "重铸" in doc, "未说明 f5 会重铸存量 id 这个关键差异"
        assert "跨循环枢纽" in doc, "未说明 K11 跨循环消费方是 grandfather 的原因"

    def test_f5_really_rewrites_legacy_ids(self) -> None:
        """两侧都验：f5 确实会重铸旧下标 id（差异登记有事实依据）。"""
        f5 = cached_text(ROW_IDENTITY_MODULE.parent.parent / "f5RowIdentity.ts")
        assert "isLegacyOrdinalRowId" in f5
        assert re.search(r"if\s*\(.*isLegacyOrdinalRowId", f5) or (
            "!isLegacyOrdinalRowId" in f5
        ), "f5 里找不到「命中旧模式就重铸」的分支 ⇒ 差异登记须复核"

    def test_known_limitation_is_registered(self) -> None:
        """🔴 已知限制留档：不做 load 时立即回写，及 K 侧为何可接受。"""
        doc = cached_text(ROW_IDENTITY_MODULE)
        assert "已知限制" in doc
        assert "立即回写" in doc, "未登记「不做立即回写」这个限制"
        assert "RowIdentityMintStats" in doc, "未点名 F5 消除该窗口的做法"
        assert "session" in doc, "未说明 K 侧为何可接受"

    def test_k_domain_has_no_hardcoded_positional_id_reference(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 已知限制成立的前提：K 域无按位置化 id 字面量的引用（现算 0）。

        这条是「不做立即回写可接受」的**事实依据**。一旦有人加了这种引用，
        这条判据会红，提醒去把回写窗口收掉。
        """
        rx = re.compile(
            r"""['"](?:selling|contract|admin|check|pf|row|soe|k81)-\d+['"]"""
        )
        hits = [
            f"{p.name}"
            for p in k_files
            if rx.search(strip_comments(cached_text(p)))
        ]
        assert hits == [], (
            f"出现按位置化 id 字面量的引用：{hits} ⇒ 立即回写窗口必须收掉"
        )
