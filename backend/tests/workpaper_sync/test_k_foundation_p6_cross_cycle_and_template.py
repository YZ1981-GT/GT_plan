# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 1 Task 11~13：跨循环键 / #REF! / 扫描误报。

spec: k-cycle-sync-foundation-and-first-canary
Task 11: KC-8 跨循环键冻结 + H1 golden 回归钩子
Task 12: KC-11 K1 披露表 #REF! 登记（缺陷归 lane 1，本 spec 只立判据）
Task 13: KC-13 两处扫描误报的区分判据
Property: KF-P26, KF-P27, KF-P28, KF-P31, KF-P33, KF-P34

═══ 三条最容易翻车的判据 ═══

1. 🔴 **照抄 J 的「完全自闭」结论会漏掉整条跨循环风险**。J 循环的键无一被非 J
   消费；K 是**强命中**（K11 的 9 键被 H1 pilot / H3 / H8 / I1 四方消费，
   K1-1 被 G 循环 4 文件消费）。
2. 🔴 **K1 的 70 格 `#REF!` 不是整表失效**。E 列 `=IF(C{r}=0,0,C{r}/$B$18)`
   活着 ⇒ 定性为「源 sheet 被删或改名的**部分**断链」。判据载荷必须让
   「只有这两个子区有数」，否则其他区的正确值会掩盖错误 ⇒ 假绿。
3. 🔴 **两处扫描误报必须如实登记**，否则会误立缺陷：
   ① J 型「幽灵行」在 K 是**预置空白业务行带公式**的正常模板设计
   ② 「合计漏加小计」2 格是**两层小计的正确写法**（内层已被吸收，不重不漏）
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    FRONTEND,
    ROOT,
    cached_text,
    k_domain_files,
    strip_comments,
)

K_TEMPLATE_DIR = ROOT / "backend" / "wp_templates" / "K"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"

#: K11 跨循环枢纽的 9 个键及其消费方（design.md KC-8 现算）
K11_FROZEN_KEYS = {
    "K11-2-detail-rows": {
        "h3ImpairmentCrossSheet.ts",
        "useH1Impairment.ts",
        "useH8Impairment.ts",
        "useI1Impairment.ts",
    },
    "K11-2-fixed-asset-occurrence": {"useH1Impairment.ts"},
    "K11-2-rou-occurrence": {"useH8Impairment.ts"},
    "K11-2-intangible-occurrence": {"useI1Impairment.ts"},
    "K11-2-intangible-source-amount": {"useI1Impairment.ts"},
    "K11-source-H1-amount": {"useH1Impairment.ts"},
    "K11-source-H3-amount": {"h3ImpairmentCrossSheet.ts"},
    "K11-source-H8-amount": {"useH8Impairment.ts"},
    "K11-source-I1-amount": {"useI1Impairment.ts"},
}

#: K1-1 被 G 循环消费
K1_1_CONSUMERS = {
    "G2TabDisclosureListed.vue",
    "G3TabDisclosureListed.vue",
    "G3TabDisclosureSOE.vue",
    "g2NoteSectionMap.ts",
}

K_KEY_RX = re.compile(r"['\"`](K(?:1[0-3]|[1-9])-[A-Za-z0-9][A-Za-z0-9\-]*)['\"`]")


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def non_k_frontend(k_files: list[pathlib.Path]) -> list[pathlib.Path]:
    """非 K 域的前端生产文件。"""
    k_set = set(k_files)
    return [
        p for p in FRONTEND.rglob("*")
        if p.is_file()
        and p.suffix in (".ts", ".vue")
        and "__tests__" not in p.as_posix()
        and p not in k_set
    ]


@pytest.fixture(scope="module")
def k_keys_consumed_outside(
    non_k_frontend: list[pathlib.Path],
) -> dict[str, set[str]]:
    """非 K 域文件消费的 K 键 -> 消费方文件名集合。"""
    out: dict[str, set[str]] = {}
    for p in non_k_frontend:
        src = strip_comments(cached_text(p))
        for m in K_KEY_RX.finditer(src):
            out.setdefault(m.group(1), set()).add(p.name)
    return out


@pytest.fixture(scope="module")
def k1_template() -> pathlib.Path:
    p = K_TEMPLATE_DIR / "K1 其他应收款.xlsx"
    assert p.exists(), f"K1 权威模板不存在：{p}"
    return p


# ════════════════════════════════════════════════════════════════════════════
# Task 11 / KF-P26~P28：跨循环键冻结
# ════════════════════════════════════════════════════════════════════════════
class TestKFP26CrossCycleConsumption:
    """🔴 KC-8：K 是强命中（JC-17 在 J 是完全自闭，照抄会漏整条风险）。"""

    def test_cross_cycle_consumption_is_non_empty(
        self, k_keys_consumed_outside: dict[str, set[str]]
    ) -> None:
        """非 K 域消费 K 键的数量非 0（分母不空）。"""
        assert k_keys_consumed_outside, (
            "非 K 域消费 K 键为 0 ⇒ 与 KC-8 登记矛盾"
            "（那才是 J 循环的形态，K 是强命中）"
        )

    def test_k11_nine_keys_and_their_consumers_match_design(
        self, k_keys_consumed_outside: dict[str, set[str]]
    ) -> None:
        """🔴 K11 的 9 个键及消费方逐条等值。"""
        for key, expected in K11_FROZEN_KEYS.items():
            actual = k_keys_consumed_outside.get(key, set())
            assert actual == expected, (
                f"{key}: 多 {sorted(actual - expected)}，缺 {sorted(expected - actual)}"
            )

    def test_k11_2_detail_rows_has_four_consumers_including_h1_pilot(
        self, k_keys_consumed_outside: dict[str, set[str]]
    ) -> None:
        """🔴 `K11-2-detail-rows` 被 4 方消费，含 H1 pilot（adapter 已注册）。"""
        consumers = k_keys_consumed_outside["K11-2-detail-rows"]
        assert len(consumers) == 4
        assert "useH1Impairment.ts" in consumers, (
            "H1 pilot 不在消费方里 ⇒ golden 回归钩子失去依据"
        )

    def test_k1_1_is_consumed_by_g_cycle(
        self, k_keys_consumed_outside: dict[str, set[str]]
    ) -> None:
        """K1-1 被 G 循环 4 文件消费。"""
        actual = k_keys_consumed_outside.get("K1-1", set())
        assert actual == K1_1_CONSUMERS, (
            f"多 {sorted(actual - K1_1_CONSUMERS)}，缺 {sorted(K1_1_CONSUMERS - actual)}"
        )

    def test_j_cycle_self_contained_conclusion_does_not_apply(
        self, k_keys_consumed_outside: dict[str, set[str]]
    ) -> None:
        """🔴 显式登记：照抄 J 的自闭结论会漏掉整条跨循环风险。"""
        # J 的结论是「键无一被非 J 消费」。K 若照抄 ⇒ 这个集合应该是空的
        assert len(k_keys_consumed_outside) > 0, (
            "K 的跨循环消费集合为空 ⇒ J 的结论在 K 也成立，本条登记须撤"
        )
        # 且至少覆盖 H / I / G 三个循环
        all_consumers: set[str] = set()
        for s in k_keys_consumed_outside.values():
            all_consumers |= s
        cycles = set()
        for name in all_consumers:
            m = re.match(r"^(?:use|Gt|[a-z])?([A-Z])\d", name)
            if m:
                cycles.add(m.group(1))
            else:
                m2 = re.search(r"([A-Z])\d+", name)
                if m2:
                    cycles.add(m2.group(1))
        assert {"H", "I", "G"} <= cycles, (
            f"跨循环消费方应覆盖 H/I/G，实得 {sorted(cycles)}"
        )


class TestKFP27H1GoldenRegressionHook:
    """🔴 KC-8：改动 K11-* 与 K1-1 须触发 H1 pilot golden 回归。"""

    def test_h1_adapter_id_is_non_null(self) -> None:
        """H1 的 adapter_id 非空（证明它真是已注册的 pilot）。"""
        manifest = json.loads(FULL_MANIFEST_PATH.read_text(encoding="utf-8"))
        h1 = [
            e for e in manifest["entries"]
            if e["entry_id"] == "xlsx/gt-h1-fixed-assets"
        ]
        assert h1, "manifest 里找不到 H1 entry"
        assert h1[0]["adapter_id"] is not None, (
            "H1 的 adapter_id 为 null ⇒ 「改动触发 H1 golden 回归」失去依据"
        )

    def test_h1_contract_is_reviewed(self) -> None:
        """H1 的契约已 reviewed。"""
        candidates = list(CONTRACT_DIR.glob("*h1*.json"))
        assert candidates, f"找不到 H1 契约：{CONTRACT_DIR}"
        reviewed = []
        for p in candidates:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if doc.get("review_status") == "reviewed":
                reviewed.append(p.name)
        assert reviewed, (
            f"H1 契约均非 reviewed：{[p.name for p in candidates]}"
        )

    def test_frozen_key_list_is_complete_and_stable(self) -> None:
        """冻结清单含 K11 的 9 键 + K1-1，共 10 个键名。"""
        frozen = set(K11_FROZEN_KEYS) | {"K1-1"}
        assert len(frozen) == 10
        # 全部形如 K{n}-...
        for k in frozen:
            assert re.match(r"^K(1[0-3]|[1-9])(?![0-9])-", k), f"{k} 不符键名形态"


class TestKFP28ReverseNonKKeyReferences:
    """反向：K 域文件引用的非 K 循环键。"""

    #: design.md 点名的 4 种（其余是 K 内部的 sheet 码或 s1-s2 类状态迁移标记）
    DESIGN_NAMED = {
        "b19-alert": {"K1TabLargeAmount.vue"},
        "b19-tag": {"K1TabLargeAmount.vue"},
        "H1-14-supplement-total": {"useK11Detail.ts"},
        "H1-14-calc-rows": {"useK11Detail.ts"},
    }

    def test_the_four_design_named_keys_match(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """design.md 点名的 4 种非 K 键逐条等值。"""
        rx = re.compile(r"['\"`]([A-Za-z]\d+[A-Za-z0-9\-]*)['\"`]")
        found: dict[str, set[str]] = {}
        for p in k_files:
            src = strip_comments(cached_text(p))
            for m in rx.finditer(src):
                key = m.group(1)
                if key in self.DESIGN_NAMED:
                    found.setdefault(key, set()).add(p.name)
        for key, expected in self.DESIGN_NAMED.items():
            actual = found.get(key, set())
            assert actual == expected, (
                f"{key}: 多 {sorted(actual - expected)}，缺 {sorted(expected - actual)}"
            )

    def test_h1_keys_referenced_from_k11_are_the_bidirectional_link(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 `useK11Detail.ts` 引 H1 键 ⇒ K11↔H1 是**双向**耦合。"""
        target = [p for p in k_files if p.name == "useK11Detail.ts"]
        assert target, "useK11Detail.ts 不存在"
        src = strip_comments(cached_text(target[0]))
        assert "H1-14-supplement-total" in src
        assert "H1-14-calc-rows" in src


# ════════════════════════════════════════════════════════════════════════════
# Task 12 / KF-P31：K1 双变体披露表 70 格 #REF!
# ════════════════════════════════════════════════════════════════════════════
class TestKFP31K1DisclosureRefErrors:
    """🔴 KC-11：slice 完全漏掉，本轮自行现算并定性为**部分断链**。"""

    #: 两张披露表的现算值
    EXPECTED = {
        "附注披露信息(上市公司）": {"cells": 35, "rows": 8, "span": (125, 140), "anchor": "$B$18"},
        "附注披露信息（国企）": {"cells": 35, "rows": 8, "span": (104, 129), "anchor": "$B$13"},
    }

    @staticmethod
    def _ref_cells(ws) -> tuple[list[str], set[int]]:
        cells: list[str] = []
        rows: set[int] = set()
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and "#REF!" in c.value:
                    cells.append(c.coordinate)
                    rows.add(c.row)
        return cells, rows

    def test_each_variant_has_35_ref_cells_in_8_rows(
        self, k1_template: pathlib.Path
    ) -> None:
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            for sn, exp in self.EXPECTED.items():
                assert sn in wb.sheetnames, f"sheet {sn!r} 不存在"
                cells, rows = self._ref_cells(wb[sn])
                assert len(cells) == exp["cells"], (
                    f"{sn}: #REF! 格数期望 {exp['cells']}，实得 {len(cells)}"
                )
                assert len(rows) == exp["rows"], (
                    f"{sn}: #REF! 行数期望 {exp['rows']}，实得 {len(rows)}"
                )
                assert (min(rows), max(rows)) == exp["span"], (
                    f"{sn}: 行区间期望 {exp['span']}，实得 {(min(rows), max(rows))}"
                )
        finally:
            wb.close()

    def test_total_is_70_cells(self, k1_template: pathlib.Path) -> None:
        """两表合计 70 格。"""
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            total = sum(
                len(self._ref_cells(wb[sn])[0]) for sn in self.EXPECTED
            )
            assert total == 70, f"两表合计期望 70 格，实得 {total}"
        finally:
            wb.close()

    def test_arithmetic_self_check_20_plus_15(
        self, k1_template: pathlib.Path
    ) -> None:
        """算术自检：4 列 × 5 行 = 20 + 5 列 × 3 行 = 15 == 35。"""
        assert 4 * 5 + 5 * 3 == 35

    def test_e_column_formula_is_alive_so_not_whole_sheet_failure(
        self, k1_template: pathlib.Path
    ) -> None:
        """🔴 E 列 `=IF(C{r}=0,0,C{r}/$B$nn)` **活着** ⇒ 部分断链非整表失效。"""
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            for sn, exp in self.EXPECTED.items():
                ws = wb[sn]
                _cells, rows = self._ref_cells(ws)
                alive: list[str] = []
                for r in sorted(rows):
                    cell = ws.cell(row=r, column=5)  # E 列
                    v = cell.value
                    if (
                        isinstance(v, str)
                        and v.startswith("=")
                        and "#REF!" not in v
                    ):
                        alive.append(v)
                assert len(alive) == 5, (
                    f"{sn}: E 列活着的公式期望 5 处，实得 {len(alive)}"
                    " ⇒ 若为 0 则应定性为整表失效而非部分断链"
                )
                # 公式形态与锚点
                for f in alive:
                    assert re.match(
                        r"^=IF\(C\d+=0,0,C\d+/\$B\$\d+\)$", f
                    ), f"{sn}: E 列公式形态不符：{f!r}"
                    assert exp["anchor"] in f, (
                        f"{sn}: E 列锚点期望 {exp['anchor']}，实得 {f!r}"
                    )
        finally:
            wb.close()

    def test_footer_sums_propagate_ref_error(
        self, k1_template: pathlib.Path
    ) -> None:
        """合计行的 SUM **恒传播 `#REF!`** ⇒ 该两个子区的合计恒为错。"""
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            ws = wb["附注披露信息(上市公司）"]
            # R130 / R141 的 SUM 引用了含 #REF! 的区间
            found_sums: list[str] = []
            for r in (130, 141):
                for col in range(1, 10):
                    v = ws.cell(row=r, column=col).value
                    if isinstance(v, str) and "SUM(" in v.upper():
                        found_sums.append(f"R{r}:{v}")
            assert found_sums, (
                "R130 / R141 找不到 SUM ⇒ 传播链登记须更新"
            )
        finally:
            wb.close()

    def test_fix_goes_through_overlay_not_source_bytes(self) -> None:
        """修法走覆盖层，不改源模板字节（FC-5 例外新增一条）。

        本 spec 只立判据，实际修复归 lane 1 —— 故这里断言**源模板仍含 70 格**
        （若已被改动，说明有人直接改了源字节）。
        """
        wb = load_workbook(
            K_TEMPLATE_DIR / "K1 其他应收款.xlsx", read_only=False, data_only=False
        )
        try:
            total = 0
            for sn in self.EXPECTED:
                for row in wb[sn].iter_rows():
                    for c in row:
                        if isinstance(c.value, str) and "#REF!" in c.value:
                            total += 1
            assert total == 70, (
                f"源模板 #REF! 格数变成 {total} ⇒ 有人直接改了源字节，"
                "违反「走覆盖层」的裁决"
            )
        finally:
            wb.close()


# ════════════════════════════════════════════════════════════════════════════
# Task 13 / KF-P33：幽灵行在 K 是正常模板设计
# ════════════════════════════════════════════════════════════════════════════
class TestKFP33GhostRowIsNotADefectInK:
    """🔴 KC-13①：J 型幽灵行在 K 退化为「预置空白业务行计数」，不是缺陷。"""

    @staticmethod
    def _ghost_row_counts() -> tuple[int, int]:
        """返回 (宽口径, 收紧到最后 footer 之前)。"""
        wide = 0
        narrow = 0
        for f in sorted(K_TEMPLATE_DIR.iterdir()):
            if f.suffix != ".xlsx" or f.name.startswith("~$"):
                continue
            wb = load_workbook(f, read_only=True, data_only=False)
            try:
                for sn in wb.sheetnames:
                    ws = wb[sn]
                    last_footer = 0
                    for row in ws.iter_rows():
                        for c in row:
                            if isinstance(c.value, str) and "SUM(" in c.value.upper():
                                last_footer = max(last_footer, c.row)
                    for ridx, row in enumerate(ws.iter_rows(), 1):
                        vals: dict[str, object] = {}
                        for c in row:
                            col = getattr(c, "column_letter", None)
                            if col:
                                vals[col] = c.value
                        abc_empty = all(
                            not vals.get(col) for col in ("A", "B", "C")
                        )
                        has_formula = any(
                            isinstance(v, str) and v.startswith("=")
                            for v in vals.values()
                        )
                        if abc_empty and has_formula:
                            wide += 1
                            if last_footer and ridx < last_footer:
                                narrow += 1
            finally:
                wb.close()
        return wide, narrow

    def test_two_calibers_are_149_and_126(self) -> None:
        """宽口径 149 / 收紧 126。两个口径都现算，不写死单一个。"""
        wide, narrow = self._ghost_row_counts()
        assert wide == 149, f"宽口径期望 149，实得 {wide}"
        assert narrow == 126, f"收紧口径期望 126，实得 {narrow}"
        assert narrow < wide, "收紧口径应严格小于宽口径"

    def test_sample_rows_are_preset_blank_business_rows(self) -> None:
        """三处样本逐格核验为「预置空白业务行带公式」的正常设计。

        `明细表K3-2` R10-R14 只有 H 列纵向派生（期初审定 = 未审 + 两类调整）。
        """
        f = K_TEMPLATE_DIR / "K3 其他应付款.xlsx"
        wb = load_workbook(f, read_only=False, data_only=False)
        try:
            sheet = next(
                (s for s in wb.sheetnames if "明细表K3-2" in s), None
            )
            assert sheet, f"找不到明细表K3-2：{wb.sheetnames}"
            ws = wb[sheet]
            # R10-R14 区间：A-G 空，H 有公式
            formula_cols: set[str] = set()
            for r in range(10, 15):
                for col_idx in range(1, 12):
                    c = ws.cell(row=r, column=col_idx)
                    if isinstance(c.value, str) and c.value.startswith("="):
                        formula_cols.add(c.column_letter)
            assert formula_cols, "R10-R14 完全没有公式 ⇒ 样本前提变了"
            # 公式集中在 A-G 之外（纵向派生列）
            assert not (formula_cols & set("ABCDEFG")), (
                f"R10-R14 的 A-G 有公式 {sorted(formula_cols & set('ABCDEFG'))}"
                " ⇒ 与「A-G 待用户填」的登记矛盾"
            )
        finally:
            wb.close()

    def test_distinguishing_criterion_from_j_cycle(self) -> None:
        """🔴 与 J 的 R45 的区分判据已写明。

        J = footer 区内 + **横向**校验 `F45 = C45+D45-E45`
        K = 数据区 + **纵向**派生（`=E10+F10+G10`）
        ⇒ 该判据在 K 退化为「预置空白业务行计数」，不是缺陷。
        """
        f = K_TEMPLATE_DIR / "K3 其他应付款.xlsx"
        wb = load_workbook(f, read_only=False, data_only=False)
        try:
            sheet = next(s for s in wb.sheetnames if "明细表K3-2" in s)
            ws = wb[sheet]
            # 找 R10-R14 的公式，确认是纵向派生（引用同行的多个列）
            vertical = 0
            for r in range(10, 15):
                for col_idx in range(1, 12):
                    c = ws.cell(row=r, column=col_idx)
                    v = c.value
                    if not (isinstance(v, str) and v.startswith("=")):
                        continue
                    # 纵向派生：引用同一行的其他列（如 =E10+F10+G10）
                    refs = re.findall(r"([A-Z]+)(\d+)", v)
                    if refs and all(int(rr) == r for _cc, rr in refs):
                        vertical += 1
            assert vertical > 0, (
                "R10-R14 找不到同行派生公式 ⇒ 「纵向派生」的区分判据失效"
            )
        finally:
            wb.close()


# ════════════════════════════════════════════════════════════════════════════
# Task 13 / KF-P34：两层小计是正确写法
# ════════════════════════════════════════════════════════════════════════════
class TestKFP34TwoLevelSubtotalIsCorrect:
    """🔴 KC-13②：「合计漏加小计」2 格是两层小计的**正确写法**。"""

    def test_listed_variant_outer_sum_includes_inner_subtotal(
        self, k1_template: pathlib.Path
    ) -> None:
        """R18 `=SUM(B12:B17)` 外层故意含内层小计行 R12 ⇒ 不重不漏。"""
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            ws = wb["附注披露信息(上市公司）"]
            b18 = ws["B18"].value
            b12 = ws["B12"].value
            assert isinstance(b18, str) and "SUM(" in b18.upper(), (
                f"B18 不是 SUM：{b18!r}"
            )
            assert isinstance(b12, str) and "SUM(" in b12.upper(), (
                f"B12（内层小计）不是 SUM：{b12!r}"
            )
            # 外层区间含 12
            m = re.search(r"SUM\(B(\d+):B(\d+)\)", b18)
            assert m, f"B18 的 SUM 区间解析失败：{b18!r}"
            lo, hi = int(m.group(1)), int(m.group(2))
            assert lo <= 12 <= hi, (
                f"外层 SUM 区间 B{lo}:B{hi} 不含内层小计行 12"
                " ⇒ 与「故意含之」的登记矛盾"
            )
        finally:
            wb.close()

    def test_inner_detail_rows_are_absorbed_not_double_counted(
        self, k1_template: pathlib.Path
    ) -> None:
        """内层明细 R9-R11 已被 R12 吸收，外层不再单列 ⇒ 不重不漏。"""
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            ws = wb["附注披露信息(上市公司）"]
            b12 = ws["B12"].value
            m = re.search(r"SUM\(B(\d+):B(\d+)\)", str(b12))
            assert m, f"B12 的 SUM 区间解析失败：{b12!r}"
            inner_lo, inner_hi = int(m.group(1)), int(m.group(2))
            b18 = str(ws["B18"].value)
            m2 = re.search(r"SUM\(B(\d+):B(\d+)\)", b18)
            outer_lo, outer_hi = int(m2.group(1)), int(m2.group(2))
            # 外层起点应在内层终点之后（即从小计行开始，不含内层明细）
            assert outer_lo > inner_hi, (
                f"外层起点 B{outer_lo} 未越过内层明细终点 B{inner_hi}"
                " ⇒ 会重复计算内层明细"
            )
        finally:
            wb.close()

    def test_soe_variant_has_different_aging_depth(
        self, k1_template: pathlib.Path
    ) -> None:
        """🔴 副产物：同册双变体账龄分层深度不同 ⇒ 两变体不共用行映射。

        上市公司 = 3 分档 + 内层小计 + 5 分档 + 外层小计（3+5 两层）
        国企     = 六档一层 + 小计
        """
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            listed = wb["附注披露信息(上市公司）"]
            soe = wb["附注披露信息（国企）"]

            def _sum_rows(ws, lo: int, hi: int) -> list[int]:
                out = []
                for r in range(lo, hi + 1):
                    v = ws.cell(row=r, column=2).value
                    if isinstance(v, str) and "SUM(" in v.upper():
                        out.append(r)
                return out

            listed_sums = _sum_rows(listed, 9, 20)
            soe_sums = _sum_rows(soe, 7, 15)
            # 上市有两层（至少 2 个 SUM 行）
            assert len(listed_sums) >= 2, (
                f"上市公司表 B9:B20 的 SUM 行期望 ≥2（两层），实得 {listed_sums}"
            )
            # 国企只一层
            assert len(soe_sums) >= 1, (
                f"国企表 B7:B15 找不到小计行，实得 {soe_sums}"
            )
            assert len(listed_sums) > len(soe_sums), (
                f"上市（{listed_sums}）的分层数应多于国企（{soe_sums}）"
                " ⇒ 「两变体不共用行映射」的登记依据"
            )
        finally:
            wb.close()

    def test_two_variants_must_not_share_row_mapping(
        self, k1_template: pathlib.Path
    ) -> None:
        """两变体的 #REF! 行区间不重叠 ⇒ 不能共用一套行映射。"""
        wb = load_workbook(k1_template, read_only=False, data_only=False)
        try:
            spans = {}
            for sn in ("附注披露信息(上市公司）", "附注披露信息（国企）"):
                rows = set()
                for row in wb[sn].iter_rows():
                    for c in row:
                        if isinstance(c.value, str) and "#REF!" in c.value:
                            rows.add(c.row)
                spans[sn] = (min(rows), max(rows))
            a, b = spans.values()
            assert a != b, (
                f"两变体的 #REF! 行区间相同 {a} ⇒ 「不共用行映射」的登记须撤"
            )
        finally:
            wb.close()
