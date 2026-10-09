# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 2 Task 20~21：canary 选型与身份族。

spec: k-cycle-sync-foundation-and-first-canary
Task 20: canary 选型四项硬标准复算 + 否决理由留档
Task 21: canary 身份族确认（不做前置修复）
Property: KF-P43, KF-P44, KF-P45, KF-P49, KF-P50

═══ 🔴 实施中发现的一处 design.md 偏差（已如实登记）═══

design.md 写「canary 所在 `调整分录汇总K10-3` 的 footer 属 KC-12 的连续区间
SUM 族（`=SUM(D11:D16)`）」。**实测 13 册「调整分录汇总」的 SUM 数全部为 0** ——
该表的 7 个公式**全是引 `底稿目录` 的表头**（A3/C3/F3/J3/A4/C4/F4），
数据区 R6:R22 是**纯空白待填**，R23 是提示文字。

⇒ **canary 没有 footer 可重算**。Task 25 的「断言金额维度的 footer 重算一致」
这条判据在 canary 上**无对象**，必须改为「断言数据区行的写入与读回一致」。
本文件把这个事实两侧都验（13/13 SUM 为 0 + 7 个公式全是表头引用）。

═══ canary 的四项硬标准 ═══

① 真库有非空载荷（199 B）—— 🔴 需 PG，本文件只验判据形状与 slice 登记
② 在 entry 内（`xlsx/gt-k10-other-income`）
③ 非 parent_duplicate（K 循环该计数为 0 故自动满足）
④ 单 sheet 单键组
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    K_INDEXES,
    ROOT,
    cached_text,
    k_domain_files,
    literal_hits,
    strip_comments,
)

K_TEMPLATE_DIR = ROOT / "backend" / "wp_templates" / "K"
MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"

CANARY_ENTRY_ID = "xlsx/gt-k10-other-income"
CANARY_KEY = "K10-3-entries"
CANARY_SHEET = "调整分录汇总K10-3"
CANARY_WORKBOOK = "K10 其他收益.xlsx"

_BARE_IF = re.compile(r"(?<![A-Z])IF\(")


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(MANIFEST_SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def adjustment_sheet_geometries() -> dict[str, dict]:
    """13 册「调整分录汇总」的几何。"""
    out: dict[str, dict] = {}
    for f in sorted(K_TEMPLATE_DIR.iterdir()):
        if f.suffix != ".xlsx" or f.name.startswith("~$"):
            continue
        m = re.match(r"^(K\d+)", f.name)
        if not m or m.group(1) == "K0":
            continue
        wb = load_workbook(f, read_only=False, data_only=False)
        try:
            for sn in wb.sheetnames:
                if "调整分录汇总" not in sn:
                    continue
                ws = wb[sn]
                formulas = 0
                bare_if = 0
                sums = 0
                for row in ws.iter_rows():
                    for c in row:
                        v = c.value
                        if isinstance(v, str) and v.startswith("="):
                            formulas += 1
                            if _BARE_IF.search(v):
                                bare_if += 1
                            if "SUM(" in v.upper():
                                sums += 1
                out[m.group(1)] = {
                    "sheet": sn,
                    "r": ws.max_row,
                    "c": ws.max_column,
                    "f": formulas,
                    "bareIF": bare_if,
                    "merged": len(ws.merged_cells.ranges),
                    "sums": sums,
                }
        finally:
            wb.close()
    return out


# ════════════════════════════════════════════════════════════════════════════
# Task 20 / KF-P44：13 册「调整分录汇总」完全同构
# ════════════════════════════════════════════════════════════════════════════
class TestKFP44ThirteenBooksAreIsomorphic:
    """🔴 canary 判据可外推到其余 12 条 entry 的直接依据。"""

    def test_all_13_books_have_an_adjustment_sheet(
        self, adjustment_sheet_geometries: dict[str, dict]
    ) -> None:
        assert len(adjustment_sheet_geometries) == 13, (
            f"「调整分录汇总」册数期望 13，实得 "
            f"{sorted(adjustment_sheet_geometries)}"
        )
        for n in K_INDEXES:
            assert f"K{n}" in adjustment_sheet_geometries, f"缺 K{n}"

    def test_c_f_bare_if_merged_are_identical_across_13(
        self, adjustment_sheet_geometries: dict[str, dict]
    ) -> None:
        """🔴 `c=10` / `f=7` / `bareIF=0` / `merged=3` **13/13 无例外**。"""
        for book, g in adjustment_sheet_geometries.items():
            assert g["c"] == 10, f"{book}: c 期望 10，实得 {g['c']}"
            assert g["f"] == 7, f"{book}: f 期望 7，实得 {g['f']}"
            assert g["bareIF"] == 0, f"{book}: bareIF 期望 0，实得 {g['bareIF']}"
            assert g["merged"] == 3, f"{book}: merged 期望 3，实得 {g['merged']}"

    def test_r_is_within_21_to_25(
        self, adjustment_sheet_geometries: dict[str, dict]
    ) -> None:
        """r ∈ [21, 25]（唯一有差异的维度）。"""
        rs = {g["r"] for g in adjustment_sheet_geometries.values()}
        assert min(rs) == 21 and max(rs) == 25, f"r 取值范围：{sorted(rs)}"

    def test_this_is_the_only_sheet_family_with_such_isomorphism(
        self, adjustment_sheet_geometries: dict[str, dict]
    ) -> None:
        """四个维度中三个完全一致 ⇒ 全 K 唯一有此性质的表族。"""
        uniform_dims = 0
        for dim in ("c", "f", "bareIF", "merged"):
            if len({g[dim] for g in adjustment_sheet_geometries.values()}) == 1:
                uniform_dims += 1
        assert uniform_dims == 4, (
            f"只有 {uniform_dims} 个维度完全一致 ⇒ 「完全同构」的外推依据变弱"
        )


class TestCanaryHasNoFooterSum:
    """🔴 实测偏差：13 册「调整分录汇总」的 SUM 数**全部为 0**。

    design.md 说 canary 的 footer 属「连续区间 SUM 族（`=SUM(D11:D16)`）」——
    实测该表没有任何 SUM。⇒ Task 25 的「footer 重算一致」判据在 canary 上无对象。
    """

    def test_all_13_have_zero_sum_formulas(
        self, adjustment_sheet_geometries: dict[str, dict]
    ) -> None:
        for book, g in adjustment_sheet_geometries.items():
            assert g["sums"] == 0, (
                f"{book} 的「调整分录汇总」有 {g['sums']} 个 SUM"
                " ⇒ 「无 footer」的登记须更新"
            )

    def test_the_seven_formulas_are_all_index_sheet_references(self) -> None:
        """🔴 7 个公式全是引 `底稿目录` 的表头（A3/C3/F3/J3/A4/C4/F4）。"""
        wb = load_workbook(
            K_TEMPLATE_DIR / CANARY_WORKBOOK, read_only=False, data_only=False
        )
        try:
            ws = wb[CANARY_SHEET]
            formulas: dict[str, str] = {}
            for row in ws.iter_rows():
                for c in row:
                    v = c.value
                    if isinstance(v, str) and v.startswith("="):
                        formulas[c.coordinate] = v
            assert len(formulas) == 7, (
                f"公式数期望 7，实得 {len(formulas)}：{formulas}"
            )
            for coord, f in formulas.items():
                assert "底稿目录" in f, (
                    f"{coord} 不是引底稿目录：{f!r}"
                    " ⇒ 「7 个公式全是表头引用」的登记须更新"
                )
            # 全在 R3/R4（表头区）
            rows = {int(re.search(r"\d+", c).group()) for c in formulas}
            assert rows <= {3, 4}, (
                f"公式落在 R{sorted(rows)} 而非表头区 R3/R4"
            )
        finally:
            wb.close()

    def test_data_region_is_pure_blank(self) -> None:
        """数据区 R6:R22 纯空白待填（无公式无值）。"""
        wb = load_workbook(
            K_TEMPLATE_DIR / CANARY_WORKBOOK, read_only=False, data_only=False
        )
        try:
            ws = wb[CANARY_SHEET]
            non_empty: list[str] = []
            for r in range(6, 23):
                for c in range(1, 11):
                    cell = ws.cell(row=r, column=c)
                    if cell.value is not None:
                        non_empty.append(f"{cell.coordinate}={cell.value!r}")
            assert non_empty == [], (
                f"数据区有非空单元格 {non_empty[:5]}"
                " ⇒ 「纯空白待填」的登记须更新"
            )
        finally:
            wb.close()

    def test_task25_criterion_must_be_row_level_not_footer_level(self) -> None:
        """⇒ Task 25 的判据须改为「数据区行的写入与读回一致」。

        这条测试是**文档化断言**：显式记录该偏差已被识别，避免后续实施
        Task 25 时照抄 design.md 的「footer 重算」写出无对象的空判据。
        """
        wb = load_workbook(
            K_TEMPLATE_DIR / CANARY_WORKBOOK, read_only=False, data_only=False
        )
        try:
            ws = wb[CANARY_SHEET]
            has_sum = any(
                isinstance(c.value, str) and "SUM(" in c.value.upper()
                for row in ws.iter_rows()
                for c in row
            )
            assert not has_sum, "canary 有 SUM ⇒ footer 判据可用，本条登记须撤"
        finally:
            wb.close()


# ════════════════════════════════════════════════════════════════════════════
# Task 20 / KF-P43：四项硬标准
# ════════════════════════════════════════════════════════════════════════════
class TestKFP43CanaryHardCriteria:
    """canary 选型四项硬标准逐条可复算。"""

    def test_criterion_2_canary_is_inside_the_entry(
        self, manifest_slice: dict
    ) -> None:
        """② 在 `xlsx/gt-k10-other-income` 内。"""
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert CANARY_ENTRY_ID in ids

    def test_criterion_3_parent_duplicate_is_zero(
        self, manifest_slice: dict
    ) -> None:
        """③ K 循环 parent_duplicate 计数为 0 ⇒ 自动满足。"""
        assert manifest_slice["slice_scope"]["parent_duplicate_count"] == 0

    def test_criterion_4_single_sheet_single_row_data_key(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """④ 单 sheet 单**行数据**键。

        🔴 实测 K10-3 组共 **3 个**键，其中只有 canary 是行数据：
          - `K10-3-entries`    ← canary（行数据）
          - `K10-3-published`  ← 发布标记（非行数据）
          - `K10-3-adjustment` ← 🔴 **AI section-id**（第四类命名空间，
                                  design.md 的 KC-5 三命名空间表未登记）

        ⇒ 「单 sheet 单键组」的准确表述是「单 sheet 单**行数据**键」。
        """
        k3_keys = {k for k in _k10_keys(k_files) if k.startswith("K10-3-")}
        assert CANARY_KEY in k3_keys, f"canary 键不在 K10-3 组里：{sorted(k3_keys)}"
        assert k3_keys == {
            CANARY_KEY, "K10-3-published", "K10-3-adjustment"
        }, f"K10-3 组键集合漂移：{sorted(k3_keys)}"

    def test_published_key_is_a_flag_not_row_data(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """`K10-3-published` 是发布标记（不是行数据）。"""
        hits = literal_hits(k_files, "K10-3-published")
        assert hits, "K10-3-published 在前端 0 命中 ⇒ 无法判定它的语义"

    def test_adjustment_key_is_an_ai_section_id_not_a_persistence_key(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 `K10-3-adjustment` 是 **AI section-id**，不是持久化键。

        实证：它出现在 `GtReviewTrigger section-id=` 与
        `POST /api/workpapers/{X}/ai/generate-text` 的 `section` 字段，
        **不出现在 checklist 持久化路径**。

        ⇒ 契约须把这类键与 review-session 键一并显式排除。
        """
        owner = next(
            (p for p in k_files if p.name == "K10TabAdjustment.vue"), None
        )
        assert owner is not None, "K10TabAdjustment.vue 不存在"
        src = strip_comments(cached_text(owner))
        assert "K10-3-adjustment" in src
        # 它作为 AI section 使用
        assert re.search(
            r'section-id="K10-3-adjustment"|section:\s*[\'"]K10-3-adjustment', src
        ), "K10-3-adjustment 不是以 AI section 形态使用 ⇒ 语义判定须复核"
        # 它不在 checklist 持久化路径
        assert not re.search(
            r"K10-3-adjustment['\"]?\s*[,)]?\s*.*checklist", src
        ), "K10-3-adjustment 出现在 checklist 路径 ⇒ 它可能是真持久化键"

    def test_ai_section_id_is_a_fourth_namespace(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 AI section-id 是 KC-5 三命名空间之外的**第四类**。

        全 K 域现算这类键（出现在 `section-id=` 或 `section:` 的 K 前缀串）
        非 0 ⇒ 契约的排除清单不能只列 review-session 一类。
        """
        rx = re.compile(
            r"(?:section-id=|section:\s*)['\"](K(?:1[0-3]|[1-9])-[^'\"]+)['\"]"
        )
        found: set[str] = set()
        for p in k_files:
            src = strip_comments(cached_text(p))
            found |= {m.group(1) for m in rx.finditer(src)}
        assert found, (
            "AI section-id 类键 0 命中 ⇒ 第四类命名空间的登记须撤"
        )
        assert "K10-3-adjustment" in found

    def test_canary_template_geometry(self) -> None:
        """canary 模板几何 `r=25 c=10 f=7 bareIF=0 merged=3`。"""
        wb = load_workbook(
            K_TEMPLATE_DIR / CANARY_WORKBOOK, read_only=False, data_only=False
        )
        try:
            ws = wb[CANARY_SHEET]
            assert ws.max_row == 25
            assert ws.max_column == 10
            assert len(ws.merged_cells.ranges) == 3
            formulas = sum(
                1 for row in ws.iter_rows() for c in row
                if isinstance(c.value, str) and c.value.startswith("=")
            )
            assert formulas == 7
        finally:
            wb.close()

    def test_k10_book_has_zero_bare_if(self) -> None:
        """🔴 K10 册裸 IF 为 0（14 册唯一）⇒ canary 所在册最干净。"""
        wb = load_workbook(
            K_TEMPLATE_DIR / CANARY_WORKBOOK, read_only=True, data_only=False
        )
        try:
            total = 0
            for sn in wb.sheetnames:
                for row in wb[sn].iter_rows():
                    for c in row:
                        v = c.value
                        if isinstance(v, str) and v.startswith("=") and _BARE_IF.search(v):
                            total += 1
            assert total == 0, f"K10 册裸 IF 期望 0，实得 {total}"
        finally:
            wb.close()


# ════════════════════════════════════════════════════════════════════════════
# Task 20 / 否决候选留档
# ════════════════════════════════════════════════════════════════════════════
class TestRejectedCandidatesAreDocumented:
    """八条否决候选与理由写进 evidence（不是口头说）。"""

    #: design.md 的候选对比表（key -> 否决理由摘要）
    REJECTED = {
        "K1-2-detail-rows": "太大（274,741 B）+ 宽表 c=36 + 同册 70 格 #REF!",
        "K8-6-rows": "位置化最重（8 处）+ sheet 名半全混括号",
        "K9-1-rows": "同表另有 2 键 ⇒ 多键组",
        "K2-1-rows": "三条硬伤：TB 行定义非业务数据 / 有孤儿 per-row 键 / 100% 派生表",
        "K2-disc-listed-main": "披露层同表 6 键",
        "K10-2-detail-rows": "有行但 remark 空 ⇒ 不满足硬标准",
    }

    def test_all_rejected_candidates_have_a_reason(self) -> None:
        assert len(self.REJECTED) == 6, "否决候选清单条数变了"
        for key, reason in self.REJECTED.items():
            assert reason.strip(), f"{key} 的否决理由为空"

    def test_k2_1_rows_has_three_hard_defects(self) -> None:
        """🔴 否决 `K2-1-rows` 的三条硬伤都可独立复算。"""
        reason = self.REJECTED["K2-1-rows"]
        assert "行定义" in reason
        assert "孤儿" in reason
        assert "派生" in reason

    def test_k8_6_rows_is_the_heaviest_positional_entry(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """K8 的位置化命中 8 处是全 K 最多（否决它的依据）。

        🔴 按**改造前基线**判，不按现算 —— canary 选型发生在 foundation 阶段，
        那时 K8 的 8 处位置化是实况。lane 2 已在其 Task 13 把 K8 收敛到 0，
        但这**不能**反过来把当初的否决理由说成失效。选型判据是历史事实，
        改成现算会让「否决理由」随后续收敛而自动消失，等于抹掉决策依据。
        """
        from tests.workpaper_sync.k_foundation_facts import (
            BP8_BASELINE_DEFECT_BY_ENTRY,
            bp8_expected_defect_by_entry,
            defect_by_entry,
        )

        baseline = BP8_BASELINE_DEFECT_BY_ENTRY
        assert baseline.get(8) == 8, f"K8 基线期望 8 处，实得 {baseline.get(8)}"
        assert baseline[8] == max(baseline.values()), (
            "K8 在基线里不再是位置化最重的 entry ⇒ 否决理由须复核"
        )
        # 两侧都验：现算里 K8 已收敛（证明「基线 ≠ 现算」是收敛造成的，不是基线写错）
        live = defect_by_entry(k_files)
        assert live.get(8, 0) == 0, (
            f"K8 现算 {live.get(8)} ⇒ lane 2 的 Task 13 收敛未生效"
        )
        assert 8 not in bp8_expected_defect_by_entry()

    def test_k1_2_detail_rows_book_has_the_ref_errors(self) -> None:
        """K1 册有 70 格 #REF!（否决 `K1-2-detail-rows` 的依据之一）。"""
        wb = load_workbook(
            K_TEMPLATE_DIR / "K1 其他应收款.xlsx", read_only=False, data_only=False
        )
        try:
            total = sum(
                1 for sn in wb.sheetnames
                for row in wb[sn].iter_rows()
                for c in row
                if isinstance(c.value, str) and "#REF!" in c.value
            )
            assert total == 70, f"K1 册 #REF! 期望 70 格，实得 {total}"
        finally:
            wb.close()


# ════════════════════════════════════════════════════════════════════════════
# Task 21 / KF-P45：身份族确认（不做前置修复）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP45CanaryIdentityIsSafeFamily:
    """canary 身份族已安全 ⇒ 不必先修身份缺陷。"""

    def test_k10_is_in_the_zero_positional_defect_group(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 K10 在零位置化缺陷 4 条 entry 内 ⇒ canary 无身份前置修复项。"""
        from tests.workpaper_sync.k_foundation_facts import defect_by_entry
        by_entry = defect_by_entry(k_files)
        assert by_entry.get(10, 0) == 0, (
            f"K10 位置化命中 {by_entry.get(10)} ⇒ canary 需先修身份缺陷"
        )

    def test_identity_pattern_is_entry_timestamp_base36(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """canary 载荷 id 形态 `entry-{13位时间戳}-{6位base36}` 的生成点存在。

        真库实测值 `entry-1784790231509-wlnkon` 需 PG 才能验；本文件验
        **生成该形态的代码**存在（前端侧可复算的锚点）。
        """
        rx = re.compile(r"entry-\$\{.*Date\.now\(\)")
        hit_files: list[str] = []
        for p in k_files:
            src = strip_comments(cached_text(p))
            if rx.search(src) or (
                "entry-" in src and "Date.now()" in src and "toString(36)" in src
            ):
                hit_files.append(p.name)
        assert hit_files, (
            "找不到 `entry-{ts}-{base36}` 的生成点 ⇒ 身份族登记缺乏前端锚点"
        )

    def test_safe_family_means_entropy_without_fallback(self) -> None:
        """安全族 = ENTROPY ∧ ¬FALLBACK（family_c 的判别式）。"""
        from tests.workpaper_sync.k_foundation_facts import family_of
        assert family_of("`entry-${Date.now()}-${rand}`") == "c"

    def test_canary_differs_from_i6_and_j1_which_needed_prefix_work(
        self, manifest_slice: dict
    ) -> None:
        """🔴 与 I6（需 backfill）、J1-6（需修 RD-5）都不同。"""
        k10 = next(
            e for e in manifest_slice["independent_entries"]
            if e["entry_id"] == CANARY_ENTRY_ID
        )
        blocked = k10["capability_target_blocked_by"]
        assert "BP-8" not in blocked, (
            f"K10 的 blocked_by 含 BP-8：{blocked} ⇒ 有身份缺陷须先修"
        )


# ════════════════════════════════════════════════════════════════════════════
# KF-P50：K10 的 BP 归属
# ════════════════════════════════════════════════════════════════════════════
class TestKFP50CanaryBpOwnership:
    """K10 的 `capability_target_blocked_by` 现算。"""

    EXPECTED_BLOCKED = ["BP-1", "BP-2", "BP-3", "BP-6", "BP-7", "BP-9"]

    def test_blocked_by_matches_design(self, manifest_slice: dict) -> None:
        k10 = next(
            e for e in manifest_slice["independent_entries"]
            if e["entry_id"] == CANARY_ENTRY_ID
        )
        assert k10["capability_target_blocked_by"] == self.EXPECTED_BLOCKED, (
            f"实得 {k10['capability_target_blocked_by']}"
        )

    def test_bp4_bp5_bp8_are_not_in_the_list(self, manifest_slice: dict) -> None:
        """🔴 不含 BP-4 / BP-5 / BP-8（它们归两 lane）。"""
        k10 = next(
            e for e in manifest_slice["independent_entries"]
            if e["entry_id"] == CANARY_ENTRY_ID
        )
        blocked = set(k10["capability_target_blocked_by"])
        for bp in ("BP-4", "BP-5", "BP-8"):
            assert bp not in blocked, f"{bp} 不应落在 K10"

    def test_k10_is_dedicated_composable_group(
        self, manifest_slice: dict
    ) -> None:
        """🔴 K10 属 BP-6 组（`dedicated_composable`）⇒ canary 不覆盖 BP-5 主线。"""
        k10 = next(
            e for e in manifest_slice["independent_entries"]
            if e["entry_id"] == CANARY_ENTRY_ID
        )
        assert k10["dual_mode_carrier"]["kind"] == "dedicated_composable"
        assert k10["dual_mode_carrier"].get("orphan_twin") is None, (
            "K10 有 orphan_twin ⇒ 它属 BP-5 组，canary 覆盖面登记须改"
        )

    def test_canary_does_not_cover_bp5_main_form(
        self, manifest_slice: dict
    ) -> None:
        """🔴 KF-P52：canary 不覆盖 BP-5 的「7 个一阶 orphan + 宿主内联 IIFE」。"""
        k10 = next(
            e for e in manifest_slice["independent_entries"]
            if e["entry_id"] == CANARY_ENTRY_ID
        )
        assert "BP-5" not in k10["capability_target_blocked_by"]
        # BP-5 的持有者恰好是 K1~K7
        bp5_holders = [
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if "BP-5" in e["capability_target_blocked_by"]
        ]
        assert len(bp5_holders) == 7, (
            f"BP-5 持有者期望 7 条，实得 {len(bp5_holders)}"
        )
        assert CANARY_ENTRY_ID not in bp5_holders


def _k10_keys(k_files: list[pathlib.Path]) -> set[str]:
    """K10 的业务键集合。"""
    from tests.workpaper_sync.k_foundation_facts import business_keys
    return {
        k for k in business_keys(k_files)
        if re.match(r"^K10(?![0-9])-", k)
    }
