# -*- coding: utf-8 -*-
"""K 循环 lane 1 — Task 0~2：前置门（entry 边界 / 消费边解析器 / 行数与 barrel）。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup
Task 0: entry 边界与切分自检
Task 1: 消费边解析器（口径先立，含双引号反例）
Task 2: 行数口径与 barrel 门
Property: KA-P1, KA-P2, KA-P3, KA-P5, KA-P6

═══ 🔴 本组先立的口径 ═══

**① 消费边必须排除双引号字符串内的匹配。**
`workpaperSyncLegacyBaseline.generated.ts` 的 JSON `"snippet"` 字段里含**完整的**
`from '...'` 形态（现算 9 处）。不排除就会把基线快照里的**文本**当成真实 import 边,
「orphan 生产边为 0」直接假红。本文件用它自己作反例双向自证。

**② 路径相等而非 stem 相等。** 同名文件在不同目录是不同模块。

**③ 一阶边 0 + barrel 不存在 ⇒ 二阶恒 0。** 两个条件缺一不可 ——
只验一阶边为 0 时，若存在 `composables/index.ts` 这种 barrel，模块仍可能被
`export * from './useK1DualMode'` 间接可达。

═══ 🔴 口径差异（如实登记）═══

**键数 678 是真库口径**，前端纯字面量现算 **512**，逐条差 +21~28 且分布均匀
（详见 `k_lane1_facts` 模块头）。与 lane 2 的「323 vs 201」同型。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP8_BASELINE_DEFECT_BY_ENTRY,
    DATA,
    ROOT,
    business_keys,
    cached_text,
    defect_by_entry,
    k_domain_files,
    keys_by_entry,
    line_count,
    line_count_splitlines,
    strip_comments,
)
from tests.workpaper_sync.k_lane1_facts import (  # noqa: E402
    BARREL_PATH,
    FOUNDATION_INDEXES,
    FRONTEND_SRC,
    IMPORT_FORMS,
    LANE1_BARE_IF_BY_ENTRY,
    LANE1_DEFINED_NAMES_BY_ENTRY,
    LANE1_ENTRY_IDS,
    LANE1_INDEXES,
    LANE1_KEYS_FRONTEND_BY_ENTRY,
    LANE1_KEYS_LIVE_DB_BY_ENTRY,
    LANE1_LIVE_NONEMPTY_KEYS_BY_ENTRY,
    LANE1_ORPHAN_LINE_COUNTS,
    LANE1_SHEETS_BY_ENTRY,
    LANE2_INDEXES,
    inside_double_quoted_string,
    orphan_path,
    resolve_import,
    statement_edges_to,
)

SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
TPL_DIR = ROOT / "backend" / "wp_templates" / "K"
LEGACY_BASELINE = (
    FRONTEND_SRC / "components" / "workpaper" / "sync"
    / "workpaperSyncLegacyBaseline.generated.ts"
)

FOUNDATION_ENTRY_ID = "xlsx/gt-k10-other-income"
LANE2_ENTRY_IDS = {
    "xlsx/gt-k8-selling-expenses",
    "xlsx/gt-k9-admin-expenses",
    "xlsx/gt-k11-asset-impairment-loss",
    "xlsx/gt-k12-non-operating-income",
    "xlsx/gt-k13-non-operating-expense",
}


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def books() -> dict[int, pathlib.Path]:
    out: dict[int, pathlib.Path] = {}
    for p in sorted(TPL_DIR.rglob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        m = re.match(r"^K(\d+)\s", p.name)
        if m:
            out[int(m.group(1))] = p
    return out


def _sheets(p: pathlib.Path) -> list[str]:
    wb = load_workbook(p, read_only=True, data_only=True)
    n = list(wb.sheetnames)
    wb.close()
    return n


def _bare_if(p: pathlib.Path) -> int:
    wb = load_workbook(p, read_only=True, data_only=False)
    c = sum(
        1
        for sn in wb.sheetnames
        for row in wb[sn].iter_rows()
        for cell in row
        if isinstance(cell.value, str)
        and re.search(r"\bIF\s*\(", cell.value)
        and not re.search(r"IFERROR|IFNA|IFS\s*\(", cell.value)
    )
    wb.close()
    return c


def _defined_names(p: pathlib.Path) -> tuple[int, int]:
    wb = load_workbook(p, read_only=False, data_only=False)
    tot = ref = 0
    for dn in wb.defined_names.values():
        tot += 1
        if "#REF!" in str(dn.value or ""):
            ref += 1
    for ws in wb.worksheets:
        loc = getattr(ws, "defined_names", None)
        if loc:
            for dn in loc.values():
                tot += 1
                if "#REF!" in str(dn.value or ""):
                    ref += 1
    wb.close()
    return tot, ref


# ════════════════════════════════════════════════════════════════════════════
# Task 0 / KA-P1：entry 边界与切分自检
# ════════════════════════════════════════════════════════════════════════════
class TestKAP1EntryBoundary:
    """7 条 entry 全名 + 三份 spec 无交集、并集 13。"""

    def test_seven_entry_ids_exist_in_slice(self, slice_doc: dict) -> None:
        declared = set(LANE1_ENTRY_IDS.values())
        assert len(declared) == 7
        live = {e["entry_id"] for e in slice_doc["independent_entries"]}
        assert declared <= live, f"slice 里缺：{sorted(declared - live)}"

    def test_three_specs_are_disjoint_and_union_is_13(
        self, slice_doc: dict
    ) -> None:
        lane1 = set(LANE1_ENTRY_IDS.values())
        lane2 = LANE2_ENTRY_IDS
        foundation = {FOUNDATION_ENTRY_ID}
        assert lane1 & lane2 == set()
        assert lane1 & foundation == set()
        assert lane2 & foundation == set()
        union = lane1 | lane2 | foundation
        assert len(union) == 13, f"并集 {len(union)}"
        live = {e["entry_id"] for e in slice_doc["independent_entries"]}
        assert union == live, (
            f"三份 spec 的并集 != slice 全集：多 {sorted(union - live)}，"
            f"缺 {sorted(live - union)}"
        )

    def test_entry_ids_are_full_names_without_abbreviation(self) -> None:
        """全名口径：`xlsx/gt-k{n}-{slug}`，slug 不得是缩写。"""
        for n, eid in LANE1_ENTRY_IDS.items():
            m = re.fullmatch(rf"xlsx/gt-k{n}-([a-z][a-z0-9\-]+)", eid)
            assert m is not None, f"K{n} 的 entry_id 形态不符：{eid}"
            assert len(m.group(1)) >= 9, f"K{n} 的 slug 过短疑似缩写：{m.group(1)}"


class TestKAP1BlockedByBP5:
    """🔴 7 条全含 BP-5，且含 BP-5 的恰好是这 7 条（两侧都验）。"""

    def test_all_seven_are_blocked_by_bp5(self, slice_doc: dict) -> None:
        by_id = {e["entry_id"]: e for e in slice_doc["independent_entries"]}
        for n, eid in LANE1_ENTRY_IDS.items():
            blocked = by_id[eid].get("capability_target_blocked_by") or []
            assert "BP-5" in blocked, f"K{n} 不含 BP-5：{blocked}"

    def test_bp5_set_is_exactly_these_seven(self, slice_doc: dict) -> None:
        """反向：K 循环里含 BP-5 的 entry 恰好是本 lane 这 7 条。"""
        hit = {
            e["entry_id"]
            for e in slice_doc["independent_entries"]
            if "BP-5" in (e.get("capability_target_blocked_by") or [])
        }
        assert hit == set(LANE1_ENTRY_IDS.values()), (
            f"多 {sorted(hit - set(LANE1_ENTRY_IDS.values()))}，"
            f"缺 {sorted(set(LANE1_ENTRY_IDS.values()) - hit)}"
        )

    def test_bp6_does_not_land_in_this_lane(self, slice_doc: dict) -> None:
        """🔴 BP-6 指向 K8~K13 ⇒ 本 lane 一条都不该有。"""
        by_id = {e["entry_id"]: e for e in slice_doc["independent_entries"]}
        for n, eid in LANE1_ENTRY_IDS.items():
            blocked = by_id[eid].get("capability_target_blocked_by") or []
            assert "BP-6" not in blocked, f"K{n} 含 BP-6 ⇒ 切分错了"

    def test_bp4_lands_only_on_k1(self, slice_doc: dict) -> None:
        """🔴 BP-4 只落 K1（本 lane 内唯一）。"""
        hit = {
            e["entry_id"]
            for e in slice_doc["independent_entries"]
            if "BP-4" in (e.get("capability_target_blocked_by") or [])
        }
        assert hit == {LANE1_ENTRY_IDS[1]}, f"BP-4 命中 {sorted(hit)}"


class TestKAP2ScaleMatchesDesign:
    """六项规模现算与 design 等值。"""

    def test_sheets_total_is_81(self, books: dict[int, pathlib.Path]) -> None:
        per = {n: len(_sheets(books[n])) for n in LANE1_INDEXES}
        assert per == LANE1_SHEETS_BY_ENTRY, f"逐册 sheets {per}"
        assert sum(per.values()) == 81

    def test_bare_if_total_is_291(self, books: dict[int, pathlib.Path]) -> None:
        per = {n: _bare_if(books[n]) for n in LANE1_INDEXES}
        assert per == LANE1_BARE_IF_BY_ENTRY, f"逐册裸 IF {per}"
        assert sum(per.values()) == 291

    def test_defined_names_total_is_81_with_65_broken(
        self, books: dict[int, pathlib.Path]
    ) -> None:
        """🔴 K 循环全部 65 个 `#REF!` 断链都在本 lane。"""
        per = {n: _defined_names(books[n]) for n in LANE1_INDEXES}
        assert per == LANE1_DEFINED_NAMES_BY_ENTRY, f"逐册 definedName {per}"
        assert sum(t for t, _ in per.values()) == 81
        assert sum(r for _t, r in per.values()) == 65

    def test_all_broken_defined_names_are_in_this_lane(
        self, books: dict[int, pathlib.Path]
    ) -> None:
        """两侧都验：lane 2 与 foundation 的册 `#REF!` 全 0。"""
        for n in LANE2_INDEXES + FOUNDATION_INDEXES:
            _tot, ref = _defined_names(books[n])
            assert ref == 0, f"K{n} 有 {ref} 个断链 definedName ⇒ 不该在本 lane 之外"

    def test_bp8_defect_is_24_with_k2_k4_as_control(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 BP-8 24 处：K5 7 · K6 7 · K7 6 · K1 3 · K3 1；K2/K4 为 0。"""
        live = defect_by_entry(k_files)
        expected = {n: BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE1_INDEXES}
        assert expected == {1: 3, 2: 0, 3: 1, 4: 0, 5: 7, 6: 7, 7: 6}, expected
        assert sum(expected.values()) == 24
        # 🔴 **本 lane 的 Task 15 已把这 24 处收敛完** ⇒ 现算全 0。
        # 规模判据按基线判（交付量），收敛判据按现算判（交付结果），两者都要。
        for n in LANE1_INDEXES:
            assert live.get(n, 0) == 0, (
                f"K{n} 仍有 {live.get(n, 0)} 处位置化缺陷 ⇒ Task 15 未收敛完"
            )

    def test_lane1_24_plus_lane2_21_is_45(self) -> None:
        l1 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE1_INDEXES)
        l2 = sum(BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in LANE2_INDEXES)
        assert (l1, l2) == (24, 21)
        assert l1 + l2 == 45

    def test_live_nonempty_keys_total_is_54(self) -> None:
        assert sum(LANE1_LIVE_NONEMPTY_KEYS_BY_ENTRY.values()) == 54
        assert LANE1_LIVE_NONEMPTY_KEYS_BY_ENTRY == {
            1: 26, 2: 11, 3: 3, 4: 2, 5: 6, 6: 5, 7: 1,
        }


class TestKAP2KeyCountCaliberDifference:
    """🔴 键数 678 是真库口径；前端纯字面量现算 512。"""

    def test_live_db_caliber_sums_to_678(self) -> None:
        assert sum(LANE1_KEYS_LIVE_DB_BY_ENTRY.values()) == 678

    def test_frontend_caliber_recomputes_to_512(
        self, k_files: list[pathlib.Path]
    ) -> None:
        per = keys_by_entry(k_files)
        live = {n: len(per.get(n, set())) for n in LANE1_INDEXES}
        assert live == LANE1_KEYS_FRONTEND_BY_ENTRY, f"前端口径逐条 {live}"
        assert sum(live.values()) == 512

    def test_key_prefix_caliber_agrees_with_path_caliber(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """两种前端口径（按键名前缀 vs 按文件归属）应等值。"""
        bk = business_keys(k_files)
        by_prefix = {
            n: len([k for k in bk if re.match(rf"^K{n}-", k)])
            for n in LANE1_INDEXES
        }
        assert by_prefix == LANE1_KEYS_FRONTEND_BY_ENTRY, by_prefix

    def test_the_gap_is_uniform_not_concentrated(self) -> None:
        """🔴 逐条差 +21~28 且**分布均匀** ⇒ 差的是运行时生成键，不是某条 entry 漏扫。"""
        gaps = {
            n: LANE1_KEYS_LIVE_DB_BY_ENTRY[n] - LANE1_KEYS_FRONTEND_BY_ENTRY[n]
            for n in LANE1_INDEXES
        }
        assert all(21 <= g <= 28 for g in gaps.values()), f"差值 {gaps}"
        assert sum(gaps.values()) == 678 - 512 == 166
        # 均匀性：极差 ≤ 8 ⇒ 不是集中在某一条
        assert max(gaps.values()) - min(gaps.values()) <= 8, f"差值不均匀：{gaps}"


# ════════════════════════════════════════════════════════════════════════════
# Task 1 / KA-P3：消费边解析器（口径先立）
# ════════════════════════════════════════════════════════════════════════════
class TestKAP3ThreeImportForms:
    """三形态 statement-position 解析。"""

    @pytest.mark.parametrize(
        "line,expect",
        [
            ("import { useK1DualMode } from './useK1DualMode'", "./useK1DualMode"),
            ("const m = await import('./useK1DualMode')", "./useK1DualMode"),
            ("const m = require('./useK1DualMode')", "./useK1DualMode"),
            ("export * from '@/components/x'", "@/components/x"),
        ],
    )
    def test_each_form_is_recognized(self, line: str, expect: str) -> None:
        got = [
            m.group(1) for rx in IMPORT_FORMS for m in rx.finditer(line)
        ]
        assert expect in got, f"{line!r} 未解析出 {expect}"

    def test_symbol_name_grep_is_not_used(self) -> None:
        """🔴 禁符号名 grep：`useK1DualMode` 出现在类型注解里不构成消费边。"""
        line = "let x: ReturnType<typeof useK1DualMode> | null = null"
        got = [m.group(1) for rx in IMPORT_FORMS for m in rx.finditer(line)]
        assert got == [], f"符号名出现被误判成边：{got}"


class TestKAP3DoubleQuoteExclusion:
    """🔴 排除双引号字符串内的匹配 —— 用真实的基线快照文件作反例。"""

    def test_the_counterexample_file_exists(self) -> None:
        assert LEGACY_BASELINE.exists(), (
            f"反例素材不存在：{LEGACY_BASELINE} ⇒ 本组判据失去依据"
        )

    def test_it_really_contains_import_forms_inside_double_quotes(self) -> None:
        """🔴 现算实证：`"snippet"` 字段里确有完整的 `from '...'` 形态。"""
        src = cached_text(LEGACY_BASELINE)
        snippets = re.findall(r'"snippet"\s*:\s*"([^"]{0,200})', src)
        assert len(snippets) >= 300, f"snippet 字段只 {len(snippets)} 个"
        with_import = [s for s in snippets if re.search(r"from\s*'", s)]
        assert len(with_import) >= 5, (
            f"含 `from '` 的 snippet 只 {len(with_import)} 个 ⇒ 反例不成立"
        )

    def test_detector_flags_positions_inside_double_quotes(self) -> None:
        line = '  { "snippet": "import { useWpDualMode } from \'./useWpDualMode\'" },'
        m = next(IMPORT_FORMS[0].finditer(line))
        assert inside_double_quoted_string(line, m.start()) is True

    def test_detector_clears_positions_outside(self) -> None:
        line = "import { useK1DualMode } from './useK1DualMode'"
        m = next(IMPORT_FORMS[0].finditer(line))
        assert inside_double_quoted_string(line, m.start()) is False

    def test_detector_handles_escaped_quotes(self) -> None:
        """转义引号不得把状态算翻。"""
        line = '"a\\"b" + from \'./x\''
        m = next(IMPORT_FORMS[0].finditer(line))
        assert inside_double_quoted_string(line, m.start()) is False

    def test_not_excluding_would_create_phantom_edges(self) -> None:
        """🔴 变异反证：不排除双引号时，基线快照会贡献伪边。"""
        src = cached_text(LEGACY_BASELINE)
        phantom = 0
        for line in src.split("\n"):
            for rx in IMPORT_FORMS:
                for m in rx.finditer(line):
                    if inside_double_quoted_string(line, m.start()):
                        phantom += 1
        assert phantom >= 5, (
            f"基线快照只贡献 {phantom} 个双引号内匹配 ⇒ 反证样本变了"
        )


class TestKAP3PathEqualityNotStem:
    """🔴 路径相等而非 stem 相等。"""

    def test_alias_and_relative_resolve_to_the_same_path(self) -> None:
        importer = FRONTEND_SRC / "components" / "workpaper" / "GtK1OtherReceivables.vue"
        via_rel = resolve_import("./composables/useK1DualMode", importer)
        via_alias = resolve_import(
            "@/components/workpaper/composables/useK1DualMode", importer
        )
        assert via_rel is not None and via_alias is not None
        assert via_rel.resolve() == via_alias.resolve()

    def test_bare_specifier_is_not_resolved(self) -> None:
        """裸包名（`vue` / `element-plus`）不是仓库内模块。"""
        importer = FRONTEND_SRC / "x.ts"
        assert resolve_import("vue", importer) is None
        assert resolve_import("element-plus", importer) is None

    def test_same_stem_in_different_dirs_is_not_the_same_module(self) -> None:
        """🔴 stem 相等口径会把不同目录的同名文件当同一个。"""
        importer = FRONTEND_SRC / "a" / "b.ts"
        p1 = resolve_import("./useK1DualMode", importer)
        p2 = resolve_import("../c/useK1DualMode", importer)
        assert p1 is not None and p2 is not None
        assert p1.stem == p2.stem, "两者 stem 本就相同（前提）"
        assert p1.resolve() != p2.resolve(), "路径相等判定失效"


# ════════════════════════════════════════════════════════════════════════════
# Task 2 / KA-P5, KA-P6：行数口径与 barrel 门
# ════════════════════════════════════════════════════════════════════════════
class TestKAP5BarrelGate:
    """🔴 barrel 不存在是「一阶 0 ⇒ 二阶恒 0」的前提。"""

    def test_composables_barrel_does_not_exist(self) -> None:
        assert BARREL_PATH.exists() is False, (
            f"{BARREL_PATH} 出现了 ⇒ 二阶可达性须重算（barrel 可能 re-export orphan）"
        )

    def test_no_other_barrel_reexports_the_orphans(self) -> None:
        """🔴 两侧都验：没有任何文件 `export * from` 指向 7 个 orphan。"""
        offenders: list[str] = []
        for p in FRONTEND_SRC.rglob("*.ts"):
            src = strip_comments(cached_text(p))
            for m in re.finditer(
                r"""export\s+\*\s+from\s*['"]([^'"]+)['"]""", src
            ):
                resolved = resolve_import(m.group(1), p)
                if resolved is None:
                    continue
                for n in LANE1_INDEXES:
                    if resolved.with_suffix("") == orphan_path(n).with_suffix(""):
                        offenders.append(f"{p.name} -> K{n}")
        assert offenders == [], f"orphan 被 re-export：{offenders}"


class TestKAP6LineCountCaliber:
    """行数口径统一 `len(text.split("\\n"))`；`splitlines()` 恒少 1。

    🔴 7 个 orphan 已在 Task 5 删除 ⇒ 这组行数变成**删除前基线**留档。
    判据改为「算术自洽 + 确已删除」，不再读文件。用途：日后若有人想恢复，
    能对账恢复的是不是同一份。
    """

    def test_baseline_arithmetic_is_self_consistent(self) -> None:
        assert sum(LANE1_ORPHAN_LINE_COUNTS.values()) == 838
        # splitlines 口径 = 每个各少 1 ⇒ 合计 831
        assert sum(v - 1 for v in LANE1_ORPHAN_LINE_COUNTS.values()) == 831
        assert set(LANE1_ORPHAN_LINE_COUNTS) == set(LANE1_INDEXES)

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_each_orphan_is_deleted(self, n: int) -> None:
        p = orphan_path(n)
        assert not p.exists(), (
            f"{p.name} 仍在 ⇒ Task 5 的删除未生效（或被恢复了）"
        )

    def test_the_line_count_caliber_still_holds_on_remaining_files(self) -> None:
        """🔴 口径本身仍要验 —— 换到**没被删**的 6 个 BP-6 composable 上。"""
        from tests.workpaper_sync.k_foundation_facts import dual_mode_path

        checked = 0
        for n in (8, 9, 10, 11, 12, 13):
            p = dual_mode_path(n)
            assert p.exists(), f"{p.name} 不存在"
            assert line_count(p) - line_count_splitlines(p) == 1, (
                f"{p.name} 两口径差 {line_count(p) - line_count_splitlines(p)}"
            )
            checked += 1
        assert checked == 6

    def test_three_size_groups(self) -> None:
        """K1/K2/K3 同 115 · K4/K5 同 126 · K6 125 · K7 116 ⇒ 结构分组。"""
        groups: dict[int, list[int]] = {}
        for n, c in LANE1_ORPHAN_LINE_COUNTS.items():
            groups.setdefault(c, []).append(n)
        assert groups[115] == [1, 2, 3]
        assert groups[126] == [4, 5]
        assert groups[125] == [6]
        assert groups[116] == [7]
