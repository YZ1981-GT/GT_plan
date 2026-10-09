# -*- coding: utf-8 -*-
"""K 循环 lane 1 — Task 13~15：BP-8 位置化 + 下标族双重叠 + 修复。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup
Task 13: 本 lane 24 处位置化清册与归族
Task 14: 🔴 组合判据（位置化身份 × 下标族删行）
Task 15: 位置化身份修复（grandfather 旧 id）
Property: KA-P35, KA-P36, KA-P37, KA-P38

═══ 🔴 本组四处口径裁定 ═══

**① BP-8 的 24 是 defect 口径。** 本 lane `total_hits` 是 **25** —— 多的 1 处是
`K6TabImpairmentTest.vue` 的 `rowId: \\`row-${Date.now()}-${i}\\``（family_c，
时间戳在前、序号只作同批次去重）。与 lane 2 的「21 defect / 23 total」同型。

**② 下标族 removeRow 在本 lane 是 K2~K7 六条，不是 design 写的 K3~K7 五条。**
🔴 `K2TabDisclosureListed.vue` / `K2TabDisclosureSoe.vue` 的 `removeMainRow(index: number)`
也是下标族。而 K2 的位置化身份**基线就是 0**（对照组）⇒ K2 恰好是
「有下标族删行 **但** 无位置化身份」的组合 —— 这正是组合判据的必要性证明：
  · 只看位置化身份 ⇒ K2 判「干净」，看不到它的删行按下标
  · 只看下标族 removeRow ⇒ K2 判「有风险」，但它的身份是安全的
两条单独判据对 K2 给出相反结论，只有组合判据能说清「风险等级不同」。

**③ 修复正则必须锚独立标识符。** 首轮 `(?:i|idx|index)` 无边界时匹配到
`toStr` + **i** + `ng` ⇒ 误改 4 处「有兜底 + 有熵 + 无位置化」的安全项
（`raw.rowId ?? \\`lo-${Math.random()…}\\``）。已回退并加越界守卫。

**④ 两种 family_b 形态。** 本 lane 的 5 处是 `raw?.id ||` / `raw.id ??`（键是 `id`），
lane 2 的 8 处是 `raw.rowKey ??`。只认某个键名的判据会漏掉另一半。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP8_BASELINE_DEFECT,
    BP8_BASELINE_DEFECT_BY_ENTRY,
    BP8_BASELINE_FAMILY,
    BP8_CONVERGED_ENTRIES,
    BP8_CONVERGED_FAMILY_BY_LANE,
    DATA,
    POSITIONAL_PARAM_NAMES,
    ROW_IDENTITY_FACTORY,
    ROW_IDENTITY_MODULE,
    cached_text,
    defect_by_entry,
    family_census,
    family_of,
    k_domain_files,
    positional_identity_hits,
    positional_remove_row_sites,
    remove_row_definitions,
    strip_comments,
)
from tests.workpaper_sync.k_lane1_facts import (  # noqa: E402
    FRONTEND_SRC,
    LANE1_INDEXES,
    LANE2_INDEXES,
    WP_COMPOSABLES,
)

SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"

#: 🔴 本 lane 的**改造前基线**（defect 口径，逐 entry）
LANE1_DEFECT_BASELINE = {1: 3, 2: 0, 3: 1, 4: 0, 5: 7, 6: 7, 7: 6}
#: 本 lane 的 total_hits 口径 = defect 24 + family_c 1
LANE1_FAMILY_C_COUNT = 1
LANE1_TOTAL_HITS_BASELINE = 25
#: 族分解（Task 15 修掉的就是这些）
LANE1_BASELINE_FAMILY_A = 19
LANE1_BASELINE_FAMILY_B = 5

#: 🔴 本 lane 唯一的 family_c（时间戳在前、序号在后 —— 与 lane 2 形态相反）
LANE1_FAMILY_C_HOST = "K6TabImpairmentTest.vue"
LANE1_FAMILY_C_SHAPE = re.compile(r"`row-\$\{\s*Date\.now\(\)\s*\}-\$\{\s*i\s*\}`")

#: Task 15 触及的文件（现算清册）。
#: 🔴 2026-10-01 勘误：原清册 13 个，其中 `k1AdjK11Writeback.ts` /
#: `k1AdjudicationModel.ts` / `K5TabAdjudication.vue` 三处是**固定槽位持久化键**
#: （rowKey 是 item_id 的一段），被值化后造成存量读不回 / 读写键分叉，已撤回为
#: 确定性槽位号 ⇒ 移出本清册，改由 `TestFixedSlotKeysAreDeterministic` 反向守住。
#: 依据与逐条证据见 `k_foundation_facts.FIXED_SLOT_PERSISTED_KEY_SITES`。
FIXED_FILES = (
    "k1DisclosureModel.ts",
    "useK3Checks.ts",
    "useK6NoteBlocks.ts",
    "useK7Adjudication.ts",
    "K5TabDisclosureListed.vue",
    "K5TabDisclosureSoe.vue",
    "K6TabDisclosureListed.vue",
    "K6TabDisclosureSoe.vue",
    "K7TabDisclosureListed.vue",
    "K7TabDisclosureSoe.vue",
)

#: 🔴 下标族 removeRow 现算落在这 6 条（design 只写 K3~K7 五条）
LANE1_INDEX_FAMILY_ENTRIES = (2, 3, 4, 5, 6, 7)
#: 🔴 K2 是「有下标族删行 + 无位置化身份」的组合样本
COMBINED_CRITERION_WITNESS = 2

#: 🔴 纯熵兜底（有 `??`/`||` + 熵 + 无位置化）—— **不得**被 Task 15 改动
ENTROPY_FALLBACK_RX = re.compile(
    r"(?:raw|old|r)\??\.(?:id|rowId|rowKey)\s*(?:\?\?|\|\|)\s*"
    r"`[a-zA-Z0-9\-]*\$\{\s*Math\.random\(\)"
)
ENTROPY_FALLBACK_AFTER_FIX = 46

#: 真库已落库 id 形态（grandfather 的实证；来源 = design 阶段真库现读留档）
LIVE_ID_SHAPES = {
    1: re.compile(r"^K1-2-r-[0-9a-f]+$"),
    2: re.compile(r"^r-[0-9a-z]+$"),
}
LIVE_ID_SAMPLES = {1: "K1-2-r-3f9c1a", 2: "r-jil2dvsb"}
_LIVE_EVIDENCE_IS_FROM_DESIGN_READ = True


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inventory(slice_doc: dict) -> dict:
    return slice_doc["dynamic_row_identity"]["positional_identity_inventory"]


# ════════════════════════════════════════════════════════════════════════════
# Task 13 / KA-P35, KA-P36：24 处清册与归族
# ════════════════════════════════════════════════════════════════════════════
class TestKAP35LaneInventory:
    """基线 24 处：K5 7 · K6 7 · K7 6 · K1 3 · K3 1；K2/K4 为 0。"""

    def test_baseline_by_entry(self) -> None:
        got = {n: BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE1_INDEXES}
        assert got == LANE1_DEFECT_BASELINE == {
            1: 3, 2: 0, 3: 1, 4: 0, 5: 7, 6: 7, 7: 6,
        }, got
        assert sum(got.values()) == 24

    def test_k2_and_k4_are_the_control_group(self, inventory: dict) -> None:
        """🔴 K2/K4 基线零缺陷（K 循环零缺陷 4 条里的 2 条）。"""
        assert LANE1_DEFECT_BASELINE[2] == 0
        assert LANE1_DEFECT_BASELINE[4] == 0
        zeros = inventory["entries_with_zero_defect_hits"]
        assert "K2" in zeros and "K4" in zeros

    def test_lane1_24_plus_lane2_21_is_45(self) -> None:
        l1 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE1_INDEXES)
        l2 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE2_INDEXES)
        assert (l1, l2) == (24, 21)
        assert l1 + l2 == BP8_BASELINE_DEFECT == 45

    def test_family_split_is_19_plus_5(self) -> None:
        """族分解：family_a 19 + family_b 5 == 24。"""
        mine = BP8_CONVERGED_FAMILY_BY_LANE["lane1"]
        assert mine["a"] == LANE1_BASELINE_FAMILY_A == 19
        assert mine["b"] == LANE1_BASELINE_FAMILY_B == 5
        assert mine["a"] + mine["b"] == 24

    def test_total_hits_caliber_is_one_more(self) -> None:
        """🔴 口径差异：本 lane `total_hits` 是 **25**，比 defect 的 24 多 1 处 family_c。"""
        assert LANE1_TOTAL_HITS_BASELINE == 24 + LANE1_FAMILY_C_COUNT == 25
        assert LANE1_FAMILY_C_COUNT == 1

    def test_the_only_family_c_is_the_k6_impairment_tab(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 本 lane 唯一的 family_c：**时间戳在前、序号在后**（与 lane 2 相反）。"""
        p = next((x for x in k_files if x.name == LANE1_FAMILY_C_HOST), None)
        assert p is not None, f"{LANE1_FAMILY_C_HOST} 不存在"
        src = strip_comments(cached_text(p))
        m = LANE1_FAMILY_C_SHAPE.search(src)
        assert m is not None, "K6 的 family_c 形态变了"
        assert family_of(m.group(0)) == "c"
        # 与 lane 2 的形态相反（lane 2 是 `row-${idx}-${Date.now()}`）
        assert family_of("`row-${idx}-${Date.now()}`") == "c"
        assert m.group(0) != "`row-${idx}-${Date.now()}`"

    def test_family_c_survived_the_fix(self, k_files: list[pathlib.Path]) -> None:
        """🔴 family_c 不参与修复 ⇒ 全 K 恒 3 处（2 在 lane 2 + 1 在本 lane）。"""
        c = family_census(k_files)
        assert c["c"] == BP8_BASELINE_FAMILY["c"] == 3
        hosts = {
            ref.rsplit("#", 1)[0].rsplit("/", 1)[-1]
            for ref, _k, val in positional_identity_hits(k_files)
            if family_of(val) == "c"
        }
        assert LANE1_FAMILY_C_HOST in hosts
        assert hosts == {LANE1_FAMILY_C_HOST, "useK8Cutoff.ts", "useK9Cutoff.ts"}


class TestKAP36TwoFallbackShapes:
    """🔴 两种 family_b 形态：本 lane 用 `.id`，lane 2 用 `.rowKey`。"""

    def test_both_shapes_go_to_b_by_the_discriminator(self) -> None:
        # 本 lane 的形态
        assert family_of("String(raw?.id || `imp-${idx}`)") == "b"
        assert family_of("raw.id ?? `K3-7-${String(idx + 1).padStart(2, '0')}`") == "b"
        assert family_of("String(raw?.id || `grant-${idx}-${Date.now()}`)") == "b"
        # lane 2 的形态
        assert family_of("raw.rowKey ?? `row-${idx}`") == "b"

    def test_a_key_name_specific_criterion_would_miss_half(self) -> None:
        """🔴 变异反证：只认 `.rowKey ??` 会把本 lane 的 5 处全漏掉。"""
        rowkey_only = re.compile(r"\.rowKey\s*\?\?")
        assert rowkey_only.search("raw.rowKey ?? `row-${idx}`") is not None
        assert rowkey_only.search("String(raw?.id || `imp-${idx}`)") is None

    def test_entropy_plus_fallback_still_goes_to_b(self) -> None:
        """🔴 同时含熵与兜底归 b（不放过）—— 本 lane 的 K7 grant 那处就是。"""
        assert family_of("String(raw?.id || `grant-${idx}-${Date.now()}`)") == "b"
        assert family_of("`grant-${idx}-${Date.now()}`") == "c"


# ════════════════════════════════════════════════════════════════════════════
# Task 14 / KA-P37：🔴 组合判据（位置化身份 × 下标族删行）
# ════════════════════════════════════════════════════════════════════════════
class TestKAP37CombinedCriterion:
    """🔴 两条单独判据都抓不到的风险，只有组合判据能说清。"""

    def test_index_family_remove_row_sites_are_six_entries(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 口径差异：现算落在 **K2~K7 六条**，design 只写 K3~K7 五条。"""
        sites = positional_remove_row_sites(k_files)
        lane1_hit = sorted(n for n in sites if n in LANE1_INDEXES)
        assert lane1_hit == list(LANE1_INDEX_FAMILY_ENTRIES) == [2, 3, 4, 5, 6, 7], (
            f"下标族 entry 集合 {lane1_hit}"
        )
        assert 2 in lane1_hit, "K2 不在下标族集里 ⇒ 组合判据的样本变了"

    def test_the_index_family_param_names(self) -> None:
        """下标族参数名清册（KC-7）。"""
        assert set(POSITIONAL_PARAM_NAMES) == {
            "$index", "idx", "actualIdx", "tableIndex", "index", "i",
        }

    def test_k2_is_index_delete_without_positional_identity(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 组合判据的**关键样本**：K2 有下标族删行但身份基线为 0。

        ⇒ 两条单独判据对 K2 给出**相反结论**：
          · 只看位置化身份 ⇒ 「干净」（基线 0）
          · 只看下标族 removeRow ⇒ 「有风险」
        只有组合判据能说清「风险等级不同」——K2 的删行按下标，但身份是安全的，
        所以删中间一行后剩余行的**身份集合不变**（删对了行）。
        """
        n = COMBINED_CRITERION_WITNESS
        assert n == 2
        assert LANE1_DEFECT_BASELINE[n] == 0, "K2 身份基线应为 0"
        sites = positional_remove_row_sites(k_files)
        assert n in sites, "K2 应在下标族删行集里"
        assert len(sites[n]) >= 2, f"K2 的下标族站点 {sites[n]}"

    def test_k5_k6_k7_had_both_dimensions(self, k_files: list[pathlib.Path]) -> None:
        """🔴 K5/K6/K7 **两个维度都命中** ⇒ 改造前的真双重叠。"""
        sites = positional_remove_row_sites(k_files)
        for n in (5, 6, 7):
            assert n in sites, f"K{n} 不在下标族集里"
            assert LANE1_DEFECT_BASELINE[n] > 0, f"K{n} 身份基线应 > 0"

    def test_overlap_is_now_empty_because_identity_was_fixed(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 重叠已消解 —— 因为**身份维度**修完了，不是因为两边都没了。"""
        idx_entries = set(positional_remove_row_sites(k_files))
        defect_entries = {n for n, c in defect_by_entry(k_files).items() if c > 0}
        assert defect_entries == set(), f"身份维度残留 {sorted(defect_entries)}"
        assert idx_entries, "下标族全消失 ⇒ 重叠消解的原因判断错了"
        assert idx_entries & defect_entries == set()

    def test_the_combined_criterion_row_identity_is_stable_after_delete(self) -> None:
        """🔴 组合判据本体：**删中间一行后，剩余行的身份集合不变**。

        用值化身份模拟：三行 → 删中间 → 剩余两行身份与原来相同。
        （改造前用位置化身份时，删中间行会让第 3 行的身份从 `row-2` 变成 `row-1`，
        剩余身份集合**变了** ⇒ 外部引用全错位。）
        """
        # 修复后：值化身份
        rows = [
            {"id": "imp-1700000000000-a1b2", "v": "A"},
            {"id": "imp-1700000000001-c3d4", "v": "B"},
            {"id": "imp-1700000000002-e5f6", "v": "C"},
        ]
        before = {r["id"] for r in rows}
        survivors = [r for r in rows if r["v"] != "B"]
        after = {r["id"] for r in survivors}
        assert after == before - {"imp-1700000000001-c3d4"}
        assert after == {"imp-1700000000000-a1b2", "imp-1700000000002-e5f6"}

    def test_the_combined_criterion_fails_on_positional_identity(self) -> None:
        """🔴 反证：位置化身份下，同样的删除让剩余行身份**全部漂移**。"""
        rows = [{"id": f"imp-{i}", "v": v} for i, v in enumerate("ABC")]
        before = {r["id"] for r in rows}
        assert before == {"imp-0", "imp-1", "imp-2"}
        # 删中间行后按位置重算身份（这正是改造前的行为）
        survivors = [r for r in rows if r["v"] != "B"]
        recomputed = {f"imp-{i}" for i, _ in enumerate(survivors)}
        assert recomputed == {"imp-0", "imp-1"}
        # 🔴 `imp-1` 现在指向原来的 C 行 ⇒ 身份集合变了、语义错位
        assert recomputed != before - {"imp-1"}, (
            "位置化身份下删中间行竟没造成漂移 ⇒ 反证不成立"
        )

    def test_neither_single_criterion_catches_it(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 两条单独判据的盲区各自现算证明。"""
        sites = positional_remove_row_sites(k_files)
        # 盲区①：只看位置化身份 —— 现在全 0，但下标族删行还在
        assert sum(defect_by_entry(k_files).values()) == 0
        assert sites, "只看身份维度会以为「全清了」"
        # 盲区②：只看下标族 removeRow —— 不知道身份是否也是下标
        defs = remove_row_definitions(k_files)
        idx_sigs = [s for s in defs if re.search(r"\b(?:idx|index|i)\s*:\s*number", s)]
        assert idx_sigs, "下标族签名清册为空 ⇒ 盲区②不成立"


# ════════════════════════════════════════════════════════════════════════════
# Task 15 / KA-P38：位置化身份修复（grandfather 旧 id）
# ════════════════════════════════════════════════════════════════════════════
class TestKAP38FixedWithSharedFactory:
    """24 处全走 `newRowIdentity()`（与 lane 2 同一出口，不造第二份）。"""

    def test_lane1_defect_is_now_zero(self, k_files: list[pathlib.Path]) -> None:
        live = defect_by_entry(k_files)
        residue = {n: live[n] for n in LANE1_INDEXES if live.get(n, 0)}
        assert residue == {}, f"本 lane 仍有位置化残留：{residue}"

    def test_whole_k_cycle_is_now_zero(self, k_files: list[pathlib.Path]) -> None:
        """🔴 两 lane 都收敛完 ⇒ **全 13 条零缺陷**。"""
        c = family_census(k_files)
        assert (c["a"], c["b"], c["defect"]) == (0, 0, 0), c
        assert c["c"] == 3, "family_c 被误改"
        assert c["total"] == 3
        assert set(BP8_CONVERGED_ENTRIES) == set(range(1, 14))

    @pytest.mark.parametrize("fname", FIXED_FILES)
    def test_each_fixed_file_uses_the_shared_factory(
        self, fname: str, k_files: list[pathlib.Path]
    ) -> None:
        p = next((x for x in k_files if x.name == fname), None)
        assert p is not None, f"{fname} 不存在"
        src = cached_text(p)
        assert f"import {{ {ROW_IDENTITY_FACTORY} }} from" in src, (
            f"{fname} 未 import 共享工厂 ⇒ 可能自造了私有副本"
        )
        assert f"{ROW_IDENTITY_FACTORY}(" in strip_comments(src)

    def test_no_private_duplicate_factory(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 不许在本 lane 另建私有身份工厂（第二真源）。"""
        offenders: list[str] = []
        for fname in FIXED_FILES:
            p = next(x for x in k_files if x.name == fname)
            src = strip_comments(cached_text(p))
            if re.search(
                r"function\s+(?:newRowIdentity|makeRowId|genRowId|createRowId)\b",
                src,
            ):
                offenders.append(fname)
        assert offenders == [], f"私有身份工厂：{offenders}"

    def test_factory_is_the_one_lane2_created(self) -> None:
        """🔴 两 lane 共用**同一个**工厂模块（不是各造一个）。"""
        assert ROW_IDENTITY_MODULE.exists()
        src = cached_text(ROW_IDENTITY_MODULE)
        assert f"export function {ROW_IDENTITY_FACTORY}(" in src
        defs = [
            p.name
            for p in WP_COMPOSABLES.parent.rglob("*.ts")
            if re.search(
                rf"export\s+function\s+{ROW_IDENTITY_FACTORY}\b", cached_text(p)
            )
        ]
        assert defs == [ROW_IDENTITY_MODULE.name], f"工厂有多处实现：{defs}"


class TestKAP38GrandfatherOldIds:
    """🔴 已落库 id **grandfather 不重写**。"""

    def test_fallback_left_side_is_preserved(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 5 处 family_b 的 `??` / `||` 左侧原样保留。"""
        checked = 0
        for fname in FIXED_FILES:
            p = next(x for x in k_files if x.name == fname)
            src = strip_comments(cached_text(p))
            for m in re.finditer(
                r"((?:raw|old|r)\??\.(?:id|rowId|rowKey))\s*(?:\?\?|\|\|)\s*"
                + ROW_IDENTITY_FACTORY,
                src,
            ):
                assert re.search(r"\.(?:id|rowId|rowKey)$", m.group(1))
                checked += 1
        assert checked == LANE1_BASELINE_FAMILY_B == 5, (
            f"grandfather 兜底现算 {checked} 处，期望 5（本 lane 的 family_b）"
        )

    def test_live_db_id_shapes_are_registered(self) -> None:
        """🔴 真库已落库形态：K1 的 `K1-2-r-{hex}` / K2 的 `r-{base36}`。

        来源 = design 阶段真库现读留档（本测试不重连 PG，与 foundation p10 同范式）。
        """
        assert _LIVE_EVIDENCE_IS_FROM_DESIGN_READ is True
        for n, rx in LIVE_ID_SHAPES.items():
            assert rx.fullmatch(LIVE_ID_SAMPLES[n]), (
                f"K{n} 的真库样本 {LIVE_ID_SAMPLES[n]} 不符登记形态"
            )

    def test_live_shapes_are_neither_positional_nor_the_new_factory(self) -> None:
        """🔴 grandfather 的必要性：真库形态既非位置化也非新工厂形态。

        若重写，这些身份会全变 ⇒ 用户填的数据跟错行。
        """
        from tests.workpaper_sync.k_foundation_facts import POSITIONAL_INTERP_RX

        for sample in LIVE_ID_SAMPLES.values():
            assert POSITIONAL_INTERP_RX.search(sample) is None
            # 新工厂产 `prefix-{13位ts}-{rand}` 三段；真库这两个不是
            assert not re.fullmatch(r"[a-zA-Z0-9\-]+-\d{13}-[0-9a-z]+", sample)

    def test_k1_shape_is_traceable_to_design(self) -> None:
        design = (
            DATA.parent.parent / ".kiro" / "specs"
            / "k1-k7-inlined-iife-hosts-and-orphan-cleanup" / "tasks.md"
        ).read_text(encoding="utf-8")
        assert "K1-2-r-" in design, "tasks.md 里找不到 K1 的真库形态 ⇒ 来源不可追溯"


class TestKAP38NoOverreach:
    """🔴 越界守卫：修复正则不得动「有兜底 + 有熵 + 无位置化」的安全项。"""

    def test_entropy_fallbacks_were_not_touched(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 首轮实测：`(?:i|idx|index)` 无边界时匹配 `toStr`+**i**+`ng`
        ⇒ 误改 4 处 `raw.rowId ?? \\`lo-${Math.random()…}\\``。已回退并收紧。
        """
        total = sum(
            len(ENTROPY_FALLBACK_RX.findall(strip_comments(cached_text(p))))
            for p in k_files
        )
        assert total == ENTROPY_FALLBACK_AFTER_FIX == 46, (
            f"纯熵兜底现算 {total} 处，期望 46 ⇒ 可能被越界改动"
        )

    def test_the_token_must_be_a_standalone_identifier(self) -> None:
        """🔴 收紧后的正则口径：位置化 token 必须是独立标识符。"""
        pos_token = re.compile(r"(?<![\w$])(?:i|idx|index)(?![\w$])")
        # 应命中
        assert pos_token.search("`row-${idx}`")
        assert pos_token.search("`r${i}`")
        # 不该命中（首轮踩的坑）
        assert pos_token.search("Math.random().toString(36)") is None
        assert pos_token.search("`p-${indexOf}`") is None

    def test_column_prefs_untouched(self) -> None:
        """🔴 列偏好类（KC-18）不在本组范围。"""
        for name in ("useK1DetailColumnPrefs.ts", "useK4DetailColumnPrefs.ts"):
            p = WP_COMPOSABLES / name
            assert p.exists()
            assert ROW_IDENTITY_FACTORY not in strip_comments(cached_text(p))

    def test_lane2_files_were_not_re_touched(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 lane 2 的 12 个文件不在本组清册里（各 lane 只改自己的）。"""
        lane2_fixed = {
            "useK8Checks.ts", "useK8Cutoff.ts", "useK9Adjudication.ts",
            "useK9Checks.ts", "useK9Cutoff.ts", "useK12Check.ts",
        }
        assert set(FIXED_FILES) & lane2_fixed == set(), (
            f"本组清册里混进了 lane 2 的文件：{set(FIXED_FILES) & lane2_fixed}"
        )


# ════════════════════════════════════════════════════════════════════════════
# 🔴 通用守卫：「有调用但无 import」全 K 域零容忍
# ════════════════════════════════════════════════════════════════════════════
#: 两 lane 引入的外部符号（都必须有 import 或本地定义）
INTRODUCED_SYMBOLS = (
    "newRowIdentity",
    "fetchOnlyOfficeHealthy",
    "workpaperSyncModeKey",
    "migrateWorkpaperSyncMode",
    "GtEntrySyncCapabilityNotice",
)


class TestNoUsageWithoutImport:
    """🔴 本轮**三次**踩同一类坑，必须判据化。

    根因：批量改造脚本的 `_inject_import` 守卫写成
    `if SYMBOL in src: return src` —— 它在**替换之后**才被调用，
    那时符号已经在 src 里了 ⇒ 守卫误判「已 import」直接返回。

    三次实测：
      · lane 1 Task 7 —— 7 宿主的 `fetchOnlyOfficeHealthy` /
        `workpaperSyncModeKey` / `migrateWorkpaperSyncMode` 全无 import
      · lane 1 Task 7 —— `_helpers()` 整块漏插入（`K{n}_ENTRY_ID` 等）
      · lane 1 Task 15 —— 13 个文件的 `newRowIdentity` 全无 import

    🔴 **eslint 抓不到**（TS 项目默认关 `no-undef`，交给 tsc）；而全仓
    `vue-tsc` 在本机 OOM ⇒ 这条判据是目前唯一的自动化拦截点。
    正确守卫：查 **import 语句**而不是符号名。
    """

    @staticmethod
    def _has_import(raw: str, symbol: str) -> bool:
        return (
            re.search(
                rf"import\s+(?:\{{[^}}]*\b{re.escape(symbol)}\b[^}}]*\}}"
                rf"|{re.escape(symbol)})\s+from",
                raw,
                flags=re.S,
            )
            is not None
        )

    @staticmethod
    def _has_local_def(src: str, symbol: str) -> bool:
        return (
            re.search(rf"(?:function|const|let|var)\s+{re.escape(symbol)}\b", src)
            is not None
        )

    @pytest.mark.parametrize("symbol", INTRODUCED_SYMBOLS)
    def test_every_usage_has_an_import(
        self, symbol: str, k_files: list[pathlib.Path]
    ) -> None:
        offenders: list[str] = []
        for p in k_files:
            raw = cached_text(p)
            src = strip_comments(raw)
            used = (
                re.search(rf"(?<![\w$]){re.escape(symbol)}\s*[(<]", src) is not None
                or f"<{symbol}" in src
            )
            if not used:
                continue
            if self._has_import(raw, symbol) or self._has_local_def(src, symbol):
                continue
            offenders.append(p.name)
        assert offenders == [], (
            f"{symbol} 被使用但无 import（运行时 ReferenceError）：{offenders}"
        )

    def test_the_guard_itself_is_not_vacuous(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 守卫非空：这些符号确实在 K 域被用到（否则判据恒真无意义）。"""
        used_any: dict[str, int] = {}
        for p in k_files:
            src = strip_comments(cached_text(p))
            for sym in INTRODUCED_SYMBOLS:
                if re.search(rf"(?<![\w$]){re.escape(sym)}\s*[(<]", src) or (
                    f"<{sym}" in src
                ):
                    used_any[sym] = used_any.get(sym, 0) + 1
        assert set(used_any) == set(INTRODUCED_SYMBOLS), (
            f"这些符号在 K 域无人使用：{set(INTRODUCED_SYMBOLS) - set(used_any)}"
        )
        assert used_any["newRowIdentity"] >= 13
        assert used_any["fetchOnlyOfficeHealthy"] >= 13
        assert used_any["GtEntrySyncCapabilityNotice"] >= 13

    def test_import_specifiers_resolve_to_real_files(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 两侧都验：import 的路径指向真实文件（不是拼错的相对路径）。"""
        from tests.workpaper_sync.k_lane1_facts import resolve_import

        bad: list[str] = []
        for p in k_files:
            raw = cached_text(p)
            for sym in INTRODUCED_SYMBOLS:
                m = re.search(
                    rf"import\s+(?:\{{[^}}]*\b{re.escape(sym)}\b[^}}]*\}}"
                    rf"|{re.escape(sym)})\s+from\s*['\"]([^'\"]+)['\"]",
                    raw,
                    flags=re.S,
                )
                if m is None:
                    continue
                resolved = resolve_import(m.group(1), p)
                if resolved is None:
                    continue
                if not any(
                    resolved.with_suffix(s).exists() for s in (".ts", ".vue", "")
                ):
                    bad.append(f"{p.name} -> {m.group(1)}")
        assert bad == [], f"import 路径解析失败：{bad}"


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 防御判据：新增 import 的**插入位置合法性**
# ═══════════════════════════════════════════════════════════════════════════
#
# 实测暴露的判据缺口：Task 13~15 的改造脚本把 `import { newRowIdentity } from …`
# 插在「第一条 `^import {` 之后」，而 3 个文件那一行是**多行 import 的开括号**
# ⇒ 新 import 落进花括号内部，整个文件 `Parsing error: Identifier expected`。
#
# 本文件原有 50 条判据**全部按文本命中**，对语法合法性零覆盖 ⇒ 全绿而生产代码坏。
# 现补形态判别式：开括号行的**下一行不得是一条完整 import 语句**。
#
#: 多行 import 的开括号（`import {` / `import type {` 后直接换行）
MULTILINE_IMPORT_OPEN_RX = re.compile(r"^\s*import\s*(?:type\s*)?\{\s*$")
#: 一条完整的 import 语句（带 from '…'）
COMPLETE_IMPORT_RX = re.compile(r"^\s*import\s.+from\s*['\"][^'\"]+['\"]\s*;?\s*$")
#: 判据分母的下限：K 域里 rowIdentity 的消费方不得骤降为 0
ROW_IDENTITY_CONSUMER_FLOOR = 1


def _misplaced_import_sites(paths) -> list[str]:
    """返回「完整 import 语句夹在多行 import 花括号内」的站点。"""
    out: list[str] = []
    for p in paths:
        lines = cached_text(p).split("\n")
        for i in range(1, len(lines)):
            if MULTILINE_IMPORT_OPEN_RX.match(lines[i - 1]) and COMPLETE_IMPORT_RX.match(
                lines[i]
            ):
                out.append(f"{p.name}#L{i + 1}")
    return out


class TestInsertedImportsAreSyntacticallyPlaced:
    """🔴 形态判别式，不锚站点：站点会被修，形态不会。"""

    def test_no_complete_import_sits_inside_a_multiline_import_block_in_k_domain(
        self,
    ) -> None:
        """K 域零错位 —— 这是 3 处 parsing error 的直接判据。"""
        bad = _misplaced_import_sites(k_domain_files())
        assert bad == [], f"import 插进了多行 import 花括号内 ⇒ 文件无法解析：{bad}"

    def test_no_complete_import_sits_inside_a_multiline_import_block_repo_wide(
        self,
    ) -> None:
        """🔴 触类旁通：同类反模式全仓归零（改造脚本不止改 K 域文件）。"""
        every = [
            p
            for p in FRONTEND_SRC.rglob("*")
            if p.is_file() and p.suffix in (".ts", ".tsx", ".vue", ".js")
        ]
        assert len(every) > 1000, f"分母可疑：只扫到 {len(every)} 个前端文件"
        bad = _misplaced_import_sites(every)
        assert bad == [], f"全仓仍有 import 错位：{bad}"

    def test_every_row_identity_import_is_a_top_level_statement(self) -> None:
        """🔴 逐条确认 rowIdentity 的 import 行自身闭合（分母非空）。"""
        consumers = 0
        for p in k_domain_files():
            text = cached_text(p)
            if ROW_IDENTITY_FACTORY not in text:
                continue
            lines = text.split("\n")
            hits = [
                (i + 1, ln)
                for i, ln in enumerate(lines)
                if ROW_IDENTITY_FACTORY in ln and ln.lstrip().startswith("import")
            ]
            if not hits:
                continue
            consumers += 1
            for lineno, ln in hits:
                assert COMPLETE_IMPORT_RX.match(ln), (
                    f"{p.name}#L{lineno} 的 rowIdentity import 不是完整语句：{ln.strip()!r}"
                )
                prev = lines[lineno - 2] if lineno >= 2 else ""
                assert not MULTILINE_IMPORT_OPEN_RX.match(prev), (
                    f"{p.name}#L{lineno} 紧跟多行 import 开括号 ⇒ 落在花括号内"
                )
        assert consumers >= ROW_IDENTITY_CONSUMER_FLOOR, (
            f"K 域 rowIdentity 消费方现算 {consumers} ⇒ 本条判据空跑"
        )


# ════════════════════════════════════════════════════════════════════════════
# 🔴 反向守卫：固定槽位持久化键必须保持确定性（2026-10-01 回归修复）
# ════════════════════════════════════════════════════════════════════════════
class TestFixedSlotKeysAreDeterministic:
    """🔴 Task 15 曾把 3 处**固定槽位**的 rowKey 也换成 `newRowIdentity()`。

    这些 rowKey 是持久化 item_id 的一段（`K1-1-aging-gross-a0-unadj` 等），
    行集合由常量 / 配置派生且条数固定 —— 下标就是槽位号。值化后：
      · K1 账龄档每次渲染换一套 key ⇒ 存量 AJE/RJE 读不回
      · K1-4→K1-1 回写写 `${rowKey}` 键、同函数读 `r${i}` 键 ⇒ 读写分叉
      · K5「从专项表带入」写进孤儿键 ⇒ 界面不显示
    本组判据守住「不要再修一次」，并要求每条豁免都可伪证。
    """

    def test_each_site_is_deterministic_and_not_factory_minted(self) -> None:
        from tests.workpaper_sync.k_foundation_facts import (
            FIXED_SLOT_PERSISTED_KEY_SITES,
            k_domain_files,
        )

        by_name = {p.name: p for p in k_domain_files()}
        for fname, value, _flow in FIXED_SLOT_PERSISTED_KEY_SITES:
            src = strip_comments(cached_text(by_name[fname]))
            assert re.search(rf"rowKey:\s*{re.escape(value)}", src), (
                f"{fname}: 找不到确定性槽位号 rowKey: {value} ⇒ 豁免条目已失效"
            )
            assert ROW_IDENTITY_FACTORY not in src, (
                f"{fname}: 又出现 {ROW_IDENTITY_FACTORY} ⇒ 固定槽位键被重新随机化"
            )

    def test_each_exemption_is_falsifiable_by_its_item_id_flow(self) -> None:
        """🔴 每条豁免必须给出「该值流入哪个 item_id」，且该证据在代码里真实存在。

        K1 账龄档的证据在模型文件注释里（`a{index}` 的历史 itemId 形态），
        其余两处的证据是同文件里的 item_id 模板串。
        """
        from tests.workpaper_sync.k_foundation_facts import (
            FIXED_SLOT_PERSISTED_KEY_SITES,
            k_domain_files,
        )

        by_name = {p.name: p for p in k_domain_files()}
        for fname, _value, flow in FIXED_SLOT_PERSISTED_KEY_SITES:
            raw = cached_text(by_name[fname])
            assert flow in raw, f"{fname}: 豁免依据 {flow!r} 在代码里不存在 ⇒ 名单须删"

    def test_k1_writeback_read_and_write_keys_agree(self) -> None:
        """🔴 读写分叉的正向判据：回写模块写入的槽位号 == 它读权重用的槽位号。"""
        src = strip_comments(
            cached_text(
                next(p for p in __import__(
                    "tests.workpaper_sync.k_foundation_facts", fromlist=["x"]
                ).k_domain_files() if p.name == "k1AdjK11Writeback.ts")
            )
        )
        assert "rowKey: `r${i}`" in src
        assert "`K1-1-${block}-r${i}-unadj`" in src, "读侧槽位号形态变了 ⇒ 须重新对账"
