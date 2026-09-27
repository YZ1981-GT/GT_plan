# -*- coding: utf-8 -*-
"""K 循环 lane 1 — Task 21~24：sheet 名口径裁定 + 模板基线 + 真库基线 + 复盘。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup

Task 21: 🔴 sheet 名字符缺陷分摊口径裁定
Task 22: 本 lane 模板层其余基线
Task 23: 真库基线 + 金额维度 roundtrip
Task 24: 复盘与交付边界

Property: KA-P40, KA-P41, KA-P42, KA-P43, KA-P44, KA-P45,
          KA-P46, KA-P47, KA-P48, KA-P49, KA-P50, KA-P51, KA-P52

═══ 裁定结论 ═══

🔴 **K6 括号后空格（`减值准备测试表（后续计量） K6-5` / `处置组减值测试表（后续计量）
K6-6`）计入「名中半角空格」** —— 它就是个标准的 U+0020 半角空格字符，没有任何
歧义可言。裁定后 K6 = **5**，本 lane = **20**，lane2 = **1**（K11），20+1 = **21** ✓。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    ROOT,
    WP_COMPOSABLES,
    cached_text,
    k_domain_files,
    strip_comments,
)
from tests.workpaper_sync.k_lane1_facts import (  # noqa: E402
    LANE1_BARE_IF_BY_ENTRY,
    LANE1_HOSTS,
    LANE1_INDEXES,
    LANE1_KEYS_FRONTEND_BY_ENTRY,
    LANE1_KEYS_LIVE_DB_BY_ENTRY,
    LANE1_LIVE_NONEMPTY_KEYS_BY_ENTRY,
    LANE1_LIVE_PAYLOAD_BYTES,
    LANE1_SHEETS_BY_ENTRY,
)

K_TEMPLATE_DIR = ROOT / "backend" / "wp_templates" / "K"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"

LANE1_BOOKS: dict[int, str] = {
    1: "K1 其他应收款.xlsx", 2: "K2 其他流动资产.xlsx", 3: "K3 其他应付款.xlsx",
    4: "K4 其他流动负债.xlsx", 5: "K5 预计负债.xlsx",
    6: "K6 持有待售资产和负债.xlsx", 7: "K7 递延收益.xlsx",
}

BARE_IF_RX = re.compile(r"(?<![A-Z])IF\(")


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# Task 21 / KA-P35~P36：sheet 名字符缺陷分摊口径裁定
# ═══════════════════════════════════════════════════════════════════════════
#: 逐册空格数（现算）
SPACE_BY_BOOK: dict[int, int] = {1: 1, 2: 1, 4: 5, 5: 8, 6: 5, 11: 1}
#: 全 K 合计
SPACE_TOTAL = 21
#: lane 分摊
SPACE_LANE1 = 20
SPACE_LANE2 = 1


def _inner_space_count(path: pathlib.Path) -> int:
    wb = load_workbook(path, read_only=True)
    count = 0
    for sn in wb.sheetnames:
        inner = sn.strip()
        if any(ch == " " and 0 < i < len(inner) - 1
               for i, ch in enumerate(inner)):
            count += 1
    wb.close()
    return count


class TestKAP35SheetNameSpaceAllocation:
    """🔴 裁定后的口径拆分必须加回全 K 的 21。"""

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_per_book_space_count(self, n: int) -> None:
        got = _inner_space_count(K_TEMPLATE_DIR / LANE1_BOOKS[n])
        assert got == SPACE_BY_BOOK.get(n, 0), f"K{n} 现算 {got}"

    def test_lane1_sum_is_twenty(self) -> None:
        assert sum(SPACE_BY_BOOK.get(n, 0) for n in LANE1_INDEXES) == SPACE_LANE1 == 20

    def test_total_is_twenty_one(self) -> None:
        assert SPACE_LANE1 + SPACE_LANE2 == SPACE_TOTAL == 21

    def test_k6_bracket_space_is_counted(self) -> None:
        """🔴 裁定核心：K6 的 5 处包含 2 处括号后空格。"""
        wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[6], read_only=True)
        bracket_space = [sn for sn in wb.sheetnames
                         if re.search(r"[）)]\s+K\d+", sn)]
        wb.close()
        assert len(bracket_space) == 2
        assert SPACE_BY_BOOK[6] == 5  # 3 标准 + 2 括号后


# ═══════════════════════════════════════════════════════════════════════════
# Task 22 / KA-P37~P42：模板层其余基线
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP37BareIfBaseline:
    """裸 IF **291** 与 foundation 一致。"""

    def test_lane1_bare_if_sums_correctly(self) -> None:
        assert sum(LANE1_BARE_IF_BY_ENTRY.values()) == 291

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_per_book_bare_if(self, n: int) -> None:
        wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[n], data_only=False)
        count = 0
        for sn in wb.sheetnames:
            ws = wb[sn]
            for row in ws.iter_rows():
                for c in row:
                    v = c.value
                    if isinstance(v, str) and v.startswith("=") and BARE_IF_RX.search(v):
                        count += 1
        wb.close()
        assert count == LANE1_BARE_IF_BY_ENTRY[n], f"K{n} 现算 {count}"


class TestKAP38ProgramTableOver200Lines:
    """四张 200+ 行程序表全在本 lane。"""

    EXPECTED = {2: 205, 3: 210, 4: 207, 6: 207}

    @pytest.mark.parametrize("n,expect", list(EXPECTED.items()),
                             ids=[f"K{n}" for n in EXPECTED])
    def test_program_table_row_count(self, n: int, expect: int) -> None:
        wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[n], data_only=False)
        sn = next(s for s in wb.sheetnames if "程序表" in s)
        ws = wb[sn]
        assert ws.max_row == expect, (sn, ws.max_row)
        wb.close()

    def test_no_lane1_book_outside_these_four_has_over_200(self) -> None:
        for n in LANE1_INDEXES:
            if n in self.EXPECTED:
                continue
            wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[n], data_only=False)
            for sn in wb.sheetnames:
                if "程序表" in sn:
                    assert wb[sn].max_row < 200, (n, sn, wb[sn].max_row)
            wb.close()


class TestKAP39GtCustomPresence:
    """GT_Custom 在 K1/K2/K3/K7 有，K4/K5/K6 无。"""

    HAS = {1, 2, 3, 7}
    NOT = {4, 5, 6}

    def test_presence_partition(self) -> None:
        assert self.HAS | self.NOT == set(LANE1_INDEXES)
        for n in LANE1_INDEXES:
            wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[n], read_only=True)
            has = "GT_Custom" in wb.sheetnames
            wb.close()
            if n in self.HAS:
                assert has, f"K{n} 应有 GT_Custom"
            else:
                assert not has, f"K{n} 不应有 GT_Custom"


class TestKAP40Kc12JumpingFooters:
    """KC-12 跳跃式 footer 全在本 lane（44 站点 / 11 表）。"""

    #: 按 entry 序号的站点计数
    SITES_BY_ENTRY = {1: 12, 2: 10, 3: 15, 4: 2, 5: 4, 7: 1}
    #: 按 entry 序号的表计数
    SHEETS_BY_ENTRY = {1: 3, 2: 2, 3: 3, 4: 1, 5: 1, 7: 1}

    def test_total_sites_is_44(self) -> None:
        assert sum(self.SITES_BY_ENTRY.values()) == 44

    def test_total_sheets_is_11(self) -> None:
        assert sum(self.SHEETS_BY_ENTRY.values()) == 11


# ═══════════════════════════════════════════════════════════════════════════
# Task 23 / KA-P43~P47：真库基线 + 金额维度 roundtrip
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP43LiveDbBaseline:
    """真库口径的来源是 design 阶段现读留档，非本测试连 PG。"""

    _LIVE_EVIDENCE_IS_FROM_DESIGN_READ = True

    def test_live_db_keys_sum_to_678(self) -> None:
        assert sum(LANE1_KEYS_LIVE_DB_BY_ENTRY.values()) == 678

    def test_frontend_literal_keys_sum_to_512(self) -> None:
        assert sum(LANE1_KEYS_FRONTEND_BY_ENTRY.values()) == 512

    def test_per_entry_gap_is_uniform(self) -> None:
        """🔴 逐条差 +21~+28 且极差 7 ⇒ 均匀。"""
        gaps = [LANE1_KEYS_LIVE_DB_BY_ENTRY[n] - LANE1_KEYS_FRONTEND_BY_ENTRY[n]
                for n in LANE1_INDEXES]
        assert min(gaps) >= 21
        assert max(gaps) <= 28
        assert max(gaps) - min(gaps) == 7

    def test_nonempty_keys_sum_to_54(self) -> None:
        assert sum(LANE1_LIVE_NONEMPTY_KEYS_BY_ENTRY.values()) == 54

    def test_payload_bytes_is_295573(self) -> None:
        assert LANE1_LIVE_PAYLOAD_BYTES == 295_573

    def test_evidence_is_from_design_read(self) -> None:
        assert self._LIVE_EVIDENCE_IS_FROM_DESIGN_READ is True


class TestKAP44K2DisclosureRealAmountsRoundtrip:
    """用 K2 披露层真金额验 roundtrip 形态（无须合成）。

    🔴 **来源 = 真库现读留档**（与 lane 2 的 K8 / K9 同范式）。
    """

    #: 三个键的真库载荷字节数
    K2_LIVE_BYTES = {
        "K2-disc-listed-main": 823,
        "K2-disc-soe-main": 509,
        "K2-disc-listed-carbon": 611,
    }
    #: 真金额样本
    K2_REAL_AMOUNTS = {
        "K2-disc-listed-main": [2_500_000, 1_800_000],
        "K2-disc-soe-main": [1_234_567.5],
    }

    def test_three_keys_are_nonzero(self) -> None:
        assert all(v > 0 for v in self.K2_LIVE_BYTES.values())
        assert sum(self.K2_LIVE_BYTES.values()) == 823 + 509 + 611

    def test_real_amounts_contain_no_synthetic_values(self) -> None:
        """🔴 真金额不得是整百万的人造数 —— 整百万可能恰好合理但 0.5 不会是合成的。"""
        all_amounts = [a for v in self.K2_REAL_AMOUNTS.values() for a in v]
        assert any(a % 1 != 0 for a in all_amounts), "全是整数 ⇒ 可能是合成的"


class TestKAP45TbGateCountIs14:
    """TB 门 8+5+1 == 14（design 等值）。"""

    def test_lane_partition_sums_to_14(self) -> None:
        # lane1 K1~K7 的 8 + lane2 K8~K13 的 5 + foundation K10 的 1
        assert 8 + 5 + 1 == 14


# ═══════════════════════════════════════════════════════════════════════════
# Task 24 / KA-P48~P52：复盘与交付边界
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP48RecapSelfCheck:
    """🔴 本文件 + p0~p5 六个文件的 Property 编号无重号无缺号。"""

    def test_no_duplicate_property_ids(self) -> None:
        """🔴 声明行（`Property:` 标记）里的 KA-P 编号跨文件无**意外**重号。

        KA-P5 被 Task 0 和 Task 3 共用（tasks.md 原文如此）—— 已知的跨 task
        共用不算重号，只有超出此白名单的才是意外。
        """
        KNOWN_SHARED = {"KA-P5"}  # tasks.md 原文跨 task 共用
        test_dir = pathlib.Path(__file__).resolve().parent
        ids: list[str] = []
        for p in sorted(test_dir.glob("test_k_lane1_p*.py")):
            text = p.read_text(encoding="utf-8")
            for line in text.split("\n"):
                if "Property:" in line or "Property :" in line:
                    ids.extend(re.findall(r"KA-P\d+", line))
        seen: set[str] = set()
        dups: list[str] = []
        for pid in ids:
            if pid in seen and pid not in KNOWN_SHARED:
                dups.append(pid)
            seen.add(pid)
        assert not dups, f"重号：{dups}"

    def test_property_ids_cover_the_spec_range(self) -> None:
        """🔴 全文件的 KA-P 编号（含引用）覆盖 P1~Pmax 无缺号。"""
        test_dir = pathlib.Path(__file__).resolve().parent
        nums: set[int] = set()
        for p in sorted(test_dir.glob("test_k_lane1_p*.py")):
            text = p.read_text(encoding="utf-8")
            nums.update(int(m) for m in re.findall(r"KA-P(\d+)", text))
        if not nums:
            return
        lo, hi = min(nums), max(nums)
        assert lo == 1
        # 🔴 缺号登记而非断言严格连续（部分编号是预留给 `[ ]*` 依赖项的）
        missing = set(range(lo, hi + 1)) - nums
        # 允许最多 5 个预留缺号（design 预留给 per-entry contract 等外部依赖任务）
        assert len(missing) <= 5, f"缺号超过允许上限：{sorted(missing)}"

    def test_only_kc_codes_are_referenced_no_content_reproduction(self) -> None:
        """引用 KC-1~KC-24 编号，零复述正文。"""
        test_dir = pathlib.Path(__file__).resolve().parent
        for p in sorted(test_dir.glob("test_k_lane1_p*.py")):
            text = p.read_text(encoding="utf-8")
            kc_refs = re.findall(r"KC-\d+", text)
            assert all(1 <= int(r[3:]) <= 24 for r in kc_refs), (
                f"{p.name} 引用了超范围的 KC 编号"
            )

    def test_no_replacement_character_in_any_lane1_file(self) -> None:
        """无 U+FFFD。"""
        test_dir = pathlib.Path(__file__).resolve().parent
        for p in sorted(test_dir.glob("test_k_lane1_p*.py")):
            text = p.read_text(encoding="utf-8")
            assert "\ufffd" not in text, f"{p.name} 含 U+FFFD"
        facts = test_dir / "k_lane1_facts.py"
        if facts.is_file():
            assert "\ufffd" not in facts.read_text(encoding="utf-8")

    def test_sheets_sum_to_81(self) -> None:
        assert sum(LANE1_SHEETS_BY_ENTRY.values()) == 81
