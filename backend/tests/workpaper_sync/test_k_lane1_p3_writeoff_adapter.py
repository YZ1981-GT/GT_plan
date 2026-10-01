# -*- coding: utf-8 -*-
"""K 循环 lane 1 — Task 9~12：BP-4 writeoff 的 adapter 化。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup
Task 9:  5 hop 写路径逐跳实证 + 裁决
Task 10: 五个传输键的精确字面量口径 + 子串反证
Task 11: OO 对端映射与行数错配
Task 12: 发 K1 per-entry contract（`[ ]*` 依赖 BP-1）
Property: KA-P15 ~ KA-P24

═══ 🔴 本组三处口径裁定 ═══

**① `is_client_only == False`。** 5 hop 的末端 `backend/app/routers/checklist_responses.py`
真有 `@router.put("")` 处理器（不是 404）⇒ 写路径真落后端 ⇒ 裁 `must_be_adapter_borne`。
🔴 且「纯客户端」本身**不是**裁 `single_onlyoffice` 的理由 —— AC 12.8 的唯一判据是
「无 HTML 对端」，而 K1-9 的 HTML 对端**存在**（见 Task 11）。

**② 子串反证的成分与 design 表述不同。**
`K1-9-writeoff` 精确 **9** / 子串 **12**，差 **3** —— design 说这 3 处都是
`'K1-9-writeoff-total'` 被算进去，现算实为：
  · `k1IndexCrossCheck.ts` 的 `'K1-9-writeoff-total'`
  · `useK1WriteoffCheck.ts` 的 `WRITEOFF_TOTAL_KEY = 'K1-9-writeoff-total'`
  · 🔴 `K1TabWriteoffCheck.vue` 的 `section-id="K1-9-writeoff-header"` —— 是 **AI
    section-id**（另一命名空间），不是 `-total`。
⇒ 结论（守卫口径必须精确字面量）不变，成分登记须修正。

**③ 裸 `'K1-9'` 有两个都对的口径。**
  · **每处都计** = **13**（`K1TabIndex.vue` 3）← design 用的是这个
  · **每行至多一次** = **12**（`K1TabIndex.vue` 2）← slice 用的是这个
  · slice 另一处写的 **11** 不属任何口径 ⇒ **只有 11 错**。
design 说「slice 的 12 与 11 两个都错」不准确。两口径都验，差异登记。
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
    cached_text,
    exact_literal_hits,
    k_domain_files,
    strip_comments,
    substring_literal_hits,
)
from tests.workpaper_sync.k_lane1_facts import (  # noqa: E402
    WP_COMPOSABLES,
    host_path,
)

SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
K1_BOOK = ROOT / "backend" / "wp_templates" / "K" / "K1 其他应收款.xlsx"
K1_SHEET = "坏账准备转回（收回）、核销检查表K1-9"
BACKEND_PUT_HANDLER = ROOT / "backend" / "app" / "routers" / "checklist_responses.py"

K1_ENTRY_ID = "xlsx/gt-k1-other-receivables"
K1_CONTRACT_ID = "k1.baddebt_reversal_writeoff_check"

#: 🔴 五个传输键的**精确**字面量命中（现算）
FIVE_KEYS_EXACT = {
    "K1-9-writeoff": 10,
    "K1-9-reversal-total": 2,
    "K1-9-writeoff-total": 2,
    "K1-3-baddebt-rows": 8,
    "K1-11-related-party": 3,
}
#: 两个派生合计键（禁标 `mode:"input"`）
DERIVED_TOTAL_KEYS = ("K1-9-reversal-total", "K1-9-writeoff-total")
#: 两个跨 sheet 只读上游
CROSS_SHEET_READ_KEYS = ("K1-3-baddebt-rows", "K1-11-related-party")

#: 🔴 7 个「猜键」—— 非空反向分母（各应为 0）
GUESSED_KEYS = (
    "K1-9-rows",
    "K1-9-detail-rows",
    "K1-9-reversal-rows",
    "K1-9-writeoff-rows",
    "K1-9-entries",
    "K1-9-check-rows",
    "K1-9-data",
)

#: 裸 `'K1-9'` 的两个口径
BARE_K1_9_PER_OCCURRENCE = 14
BARE_K1_9_PER_LINE = 13
BARE_K1_9_FILES = 6
#: slice 里那个**错**的数
BARE_K1_9_SLICE_WRONG = 11

#: OO 对端 sheet 的几何
K1_9_GEOMETRY = {"r": 25, "c": 8, "merged": 2, "formulas": 9, "bare_if": 0}
#: payload ↔ 模板四行映射
ROW_MAPPING = {
    "reversal_rows": (12, 14),
    "writeoff_rows": (18, 20),
    "reversal_total": (15, "E"),
    "writeoff_total": (21, "C"),
}
#: 模板固定 3 行（12~14 与 18~20）
TEMPLATE_FIXED_ROWS = 3


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k1_9_sheet():
    wb = load_workbook(K1_BOOK, read_only=False, data_only=False)
    ws = wb[K1_SHEET]
    snap = {
        "r": ws.max_row,
        "c": ws.max_column,
        "merged": sorted(str(x) for x in ws.merged_cells.ranges),
        "formulas": {
            c.coordinate: c.value
            for row in ws.iter_rows()
            for c in row
            if isinstance(c.value, str) and c.value.startswith("=")
        },
        "cells": {
            f"{c.coordinate}": c.value
            for row in ws.iter_rows()
            for c in row
            if c.value is not None
        },
    }
    wb.close()
    return snap


def _bare_k1_9_counts() -> tuple[int, int, dict[str, int]]:
    """返回 (每处都计, 每行至多一次, 逐文件[每处都计])。"""
    rx = re.compile(r"""['"`]K1-9['"`]""")
    per_occ: dict[str, int] = {}
    per_line_total = 0
    for p in k_domain_files():
        src = strip_comments(cached_text(p))
        for line in src.split("\n"):
            ms = rx.findall(line)
            if ms:
                per_occ[p.name] = per_occ.get(p.name, 0) + len(ms)
                per_line_total += 1
    return sum(per_occ.values()), per_line_total, per_occ


# ════════════════════════════════════════════════════════════════════════════
# Task 9 / KA-P15, KA-P16：5 hop 写路径 + 裁决
# ════════════════════════════════════════════════════════════════════════════
class TestKAP15FiveHopWritePath:
    """逐跳按常量名与端点字面量定位（不写行号）。"""

    def test_hop1_build_save_payload_is_k1_only(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 hop1 `buildSavePayload()` 全 K 只 2 文件，都属 K1 ⇒ BP-4 是 K1 独有。"""
        hits = {
            p.name
            for p in k_files
            if re.search(r"\bbuildSavePayload\b", strip_comments(cached_text(p)))
        }
        assert hits == {"useK1WriteoffCheck.ts", "K1TabWriteoffCheck.vue"}, hits

    def test_hop2_emit_save_in_the_tab(self, k_files: list[pathlib.Path]) -> None:
        p = next(x for x in k_files if x.name == "K1TabWriteoffCheck.vue")
        c = len(re.findall(r"emit\(\s*'save'", strip_comments(cached_text(p))))
        assert c == 2, f"K1TabWriteoffCheck.vue 的 emit('save') 期望 2 处，实得 {c}"

    def test_hop3_handle_child_save_in_the_host(self) -> None:
        src = strip_comments(cached_text(host_path(1)))
        c = len(re.findall(r"\bhandleChildSave\b", src))
        assert c == 15, f"GtK1OtherReceivables.vue 的 handleChildSave 实得 {c}"

    def test_hop4_use_checklist_persistence_in_the_host(self) -> None:
        src = strip_comments(cached_text(host_path(1)))
        c = len(re.findall(r"\buseChecklistPersistence\b", src))
        assert c == 3, f"宿主的 useChecklistPersistence 实得 {c}"

    def test_hop5_backend_put_handler_really_exists(self) -> None:
        """🔴 末端处理器**真实存在**（非 404）⇒ `is_client_only == False`。"""
        assert BACKEND_PUT_HANDLER.exists(), (
            f"后端处理器不存在：{BACKEND_PUT_HANDLER}"
        )
        src = BACKEND_PUT_HANDLER.read_text(encoding="utf-8")
        verbs = re.findall(r"@router\.(\w+)\(", src)
        assert "put" in verbs, f"找不到 PUT 处理器，实得 {verbs}"

    def test_the_five_hops_form_an_unbroken_chain(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 链条不断：payload 构造在 Tab、emit 到宿主、宿主收口、后端落库。"""
        tab = strip_comments(
            cached_text(next(x for x in k_files if x.name == "K1TabWriteoffCheck.vue"))
        )
        host = strip_comments(cached_text(host_path(1)))
        assert "buildSavePayload" in tab and "emit(" in tab
        assert "handleChildSave" in host and "useChecklistPersistence" in host
        assert "@save" in host or "@save=" in host or "handleChildSave" in host


class TestKAP16AdjudicationIsAdapterBorne:
    """🔴 裁 `must_be_adapter_borne`，且登记「纯客户端不是裁 single 的理由」。"""

    def test_slice_registers_adapter_borne(self, slice_doc: dict) -> None:
        blob = json.dumps(slice_doc, ensure_ascii=False)
        assert "must_be_adapter_borne" in blob, (
            "slice 未登记 must_be_adapter_borne ⇒ 裁决无留档"
        )

    def test_client_only_is_false_because_backend_handles_it(self) -> None:
        """现算依据：后端处理器存在 ⇒ 写路径不是纯客户端。"""
        src = BACKEND_PUT_HANDLER.read_text(encoding="utf-8")
        assert re.search(r"@router\.put\(", src)
        # 且它真的落库（有 session / commit / flush 之类）
        assert re.search(r"\b(session|db)\b", src), "PUT 处理器不碰数据库 ⇒ 存疑"

    def test_pure_client_is_not_a_reason_for_single_onlyoffice(
        self, slice_doc: dict
    ) -> None:
        """🔴 AC 12.8 的唯一判据是「无 HTML 对端」 —— 这条须显式登记。

        K1-9 的 HTML 对端**存在**（`K1TabWriteoffCheck.vue`）且模板 sheet 也存在
        ⇒ 不该因为「写路径像纯客户端」就裁 `single_onlyoffice`。
        """
        blob = json.dumps(slice_doc, ensure_ascii=False)
        assert "不是" in blob and "无 HTML 对端" in blob, (
            "slice 未登记「不是无 HTML 对端」这个关键区分"
        )

    def test_the_html_counterpart_really_exists(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """两侧都验：HTML 对端组件与模板 sheet 都在。"""
        assert any(x.name == "K1TabWriteoffCheck.vue" for x in k_files)
        wb = load_workbook(K1_BOOK, read_only=True, data_only=True)
        names = list(wb.sheetnames)
        wb.close()
        assert K1_SHEET in names, f"模板缺 sheet {K1_SHEET}"


# ════════════════════════════════════════════════════════════════════════════
# Task 10 / KA-P17 ~ KA-P20：五键精确口径 + 子串反证
# ════════════════════════════════════════════════════════════════════════════
class TestKAP17FiveKeysExactCounts:
    """五键精确命中 9 / 2 / 2 / 8 / 3。"""

    @pytest.mark.parametrize("key,expected", sorted(FIVE_KEYS_EXACT.items()))
    def test_each_key_exact_count(
        self, key: str, expected: int, k_files: list[pathlib.Path]
    ) -> None:
        got = exact_literal_hits(k_files, key)
        assert len(got) == expected, (
            f"{key}: 精确命中期望 {expected}，实得 {len(got)}"
        )

    def test_the_five_are_distinct_keys(self) -> None:
        assert len(FIVE_KEYS_EXACT) == 5
        assert len(set(FIVE_KEYS_EXACT)) == 5

    def test_two_derived_totals_and_two_cross_sheet_reads(self) -> None:
        """五键分三类：1 主载荷 + 2 派生合计 + 2 跨 sheet 只读。"""
        assert set(DERIVED_TOTAL_KEYS) <= set(FIVE_KEYS_EXACT)
        assert set(CROSS_SHEET_READ_KEYS) <= set(FIVE_KEYS_EXACT)
        main = set(FIVE_KEYS_EXACT) - set(DERIVED_TOTAL_KEYS) - set(
            CROSS_SHEET_READ_KEYS
        )
        assert main == {"K1-9-writeoff"}, main


class TestKAP18SubstringCounterexample:
    """🔴 子串口径会多算 ⇒ 守卫必须用精确字面量。"""

    def test_writeoff_substring_is_three_more(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 晋级后：真双向接桥新增 1 处精确 `'K1-9-writeoff'`（`k1WriteoffSync.ts` 的
        store 键常量），精确 9→**10**、子串 12→**13**，**差仍为 3**（新增那处既进精确也进子串）。
        不变式「子串比精确多 3」才是本判据要守的东西，不是那两个绝对数。"""
        ex = exact_literal_hits(k_files, "K1-9-writeoff")
        sub = substring_literal_hits(k_files, "K1-9-writeoff")
        assert len(ex) == 10
        assert len(sub) == 13
        assert len(sub) - len(ex) == 3
        # 新增那处精确命中确来自真双向接桥（排除「数字对但来源错」）。
        assert any("k1WriteoffSync.ts" in h for h in ex)

    def test_the_three_extra_hits_composition_is_registered(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 成分修正：**2 处是 `-total`，第 3 处是 `-header`（AI section-id）**。

        design 说 3 处都是 `'K1-9-writeoff-total'` —— 现算不成立。
        """
        ex = set(exact_literal_hits(k_files, "K1-9-writeoff"))
        extra = sorted(set(substring_literal_hits(k_files, "K1-9-writeoff")) - ex)
        assert len(extra) == 3
        texts: list[str] = []
        for ref in extra:
            path, ln = ref.rsplit("#L", 1)
            line = (ROOT / path).read_text(encoding="utf-8").split("\n")[int(ln) - 1]
            texts.append(line)
        totals = [t for t in texts if "K1-9-writeoff-total" in t]
        headers = [t for t in texts if "K1-9-writeoff-header" in t]
        assert len(totals) == 2, f"`-total` 期望 2 处，实得 {len(totals)}"
        assert len(headers) == 1, f"`-header` 期望 1 处，实得 {len(headers)}"
        assert len(totals) + len(headers) == 3

    def test_the_header_hit_is_an_ai_section_id(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 那 1 处 `-header` 是 `GtReviewTrigger section-id=` ⇒ 另一命名空间。"""
        p = next(x for x in k_files if x.name == "K1TabWriteoffCheck.vue")
        src = strip_comments(cached_text(p))
        assert re.search(
            r'section-id="K1-9-writeoff-header"', src
        ), "找不到 AI section-id 形态 ⇒ 成分登记须复核"

    def test_exact_caliber_is_the_guard_caliber(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 守卫用精确口径 ⇒ 不会把派生键与 section-id 算成主载荷键。"""
        ex = exact_literal_hits(k_files, "K1-9-writeoff")
        for ref in ex:
            path, ln = ref.rsplit("#L", 1)
            line = (ROOT / path).read_text(encoding="utf-8").split("\n")[int(ln) - 1]
            assert re.search(r"""['"`]K1-9-writeoff['"`]""", line), (
                f"{ref} 不含精确字面量 ⇒ 精确口径实现有问题"
            )


class TestKAP19GuessedKeysAreTheEmptyDenominator:
    """🔴 7 个猜键各 0 —— 非空反向分母。"""

    @pytest.mark.parametrize("key", GUESSED_KEYS)
    def test_each_guessed_key_is_zero(
        self, key: str, k_files: list[pathlib.Path]
    ) -> None:
        got = exact_literal_hits(k_files, key)
        assert got == [], f"{key} 竟有命中 {got} ⇒ 猜键清单须更新"

    def test_the_denominator_is_non_empty(self) -> None:
        """🔴 「各 0」要有意义，猜键清单本身必须非空。"""
        assert len(GUESSED_KEYS) == 7

    def test_the_real_key_is_not_among_the_guesses(self) -> None:
        assert "K1-9-writeoff" not in GUESSED_KEYS
        for g in GUESSED_KEYS:
            assert g.startswith("K1-9-"), f"{g} 不是 K1-9 的猜键形态"


class TestKAP20BareK19IsASheetCode:
    """🔴 裸 `'K1-9'` 是 **sheet 码**不是 item_id；两个口径都对。"""

    def test_both_calibers_recompute(self) -> None:
        """🔴 晋级后：宿主 `GtK1OtherReceivables.vue` 新增 `isSyncManagedSheet === 'K1-9'`
        让 legacy OO 在受管页让位，`K1TabWriteoffCheck.vue` 新增受管页门控 ⇒ 每处口径
        13→**14**、每行口径 12→**13**（增量全落在 `K1TabWriteoffCheck.vue`：3→4）。"""
        per_occ, per_line, detail = _bare_k1_9_counts()
        assert per_occ == BARE_K1_9_PER_OCCURRENCE == 14, (
            f"每处都计口径期望 14，实得 {per_occ}（{detail}）"
        )
        assert per_line == BARE_K1_9_PER_LINE == 13, (
            f"每行至多一次口径期望 13，实得 {per_line}"
        )
        assert len(detail) == BARE_K1_9_FILES == 6, f"文件数 {sorted(detail)}"

    def test_only_the_slice_eleven_is_wrong(self) -> None:
        """🔴 口径差异登记：**13 与 12 都对**（不同口径），只有 slice 的 11 错。

        design 说「slice 的 12 与 11 两个都错」不准确：
          · 13 = 每处都计（design 用的）
          · 12 = 每行至多一次（slice 一处用的）
          · 11 = 不属任何口径 ⇒ 唯一的错
        """
        per_occ, per_line, _ = _bare_k1_9_counts()
        assert BARE_K1_9_SLICE_WRONG not in (per_occ, per_line), (
            "11 竟对应上某个口径 ⇒ 本裁定须撤"
        )
        assert {per_occ, per_line} == {BARE_K1_9_PER_OCCURRENCE, BARE_K1_9_PER_LINE}

    def test_the_two_calibers_differ_only_on_one_file(self) -> None:
        """🔴 差异全在 `K1TabIndex.vue`（一行里出现两次）。"""
        _occ, _line, detail = _bare_k1_9_counts()
        assert detail["K1TabIndex.vue"] == 3, (
            f"K1TabIndex.vue 每处都计期望 3，实得 {detail['K1TabIndex.vue']}"
        )
        others = {k: v for k, v in detail.items() if k != "K1TabIndex.vue"}
        assert sum(others.values()) == 11, others

    def test_the_hosts_are_sheet_level_consumers(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 判 sheet 码的依据：命中处的上下文是 sheet 清单/进度/导入导出。"""
        _occ, _line, detail = _bare_k1_9_counts()
        assert set(detail) == {
            "k1SheetProgress.ts",
            "useK1ImportExport.ts",
            "useK1WriteoffImportExport.ts",
            "GtK1OtherReceivables.vue",
            "K1TabIndex.vue",
            "K1TabWriteoffCheck.vue",
        }, sorted(detail)
        # 其中三个文件名本身就说明是 sheet 级用途
        assert {"k1SheetProgress.ts", "useK1ImportExport.ts"} <= set(detail)

    def test_it_is_not_in_the_five_transport_keys(self) -> None:
        assert "K1-9" not in FIVE_KEYS_EXACT


# ════════════════════════════════════════════════════════════════════════════
# Task 11 / KA-P21 ~ KA-P23：OO 对端映射与行数错配
# ════════════════════════════════════════════════════════════════════════════
class TestKAP21OoCounterpartIsAbsentNotMissing:
    """🔴 `oo_counterpart_status == absent`，**不是**「无 HTML 对端」。"""

    def test_the_sheet_exists_in_the_authority_template(self) -> None:
        wb = load_workbook(K1_BOOK, read_only=True, data_only=True)
        names = list(wb.sheetnames)
        wb.close()
        assert K1_SHEET in names

    def test_reviewed_contract_maps_the_keys(self) -> None:
        """🔴 晋级后，恰好一份 reviewed 契约映射 K1-9（多/少都会红）。"""
        mapped: list[str] = []
        for p in CONTRACT_DIR.glob("*.json"):
            doc = json.loads(p.read_text(encoding="utf-8"))
            if doc.get("review_status") != "reviewed":
                continue
            blob = json.dumps(doc, ensure_ascii=False)
            if "K1-9-writeoff" in blob or K1_SHEET in blob:
                mapped.append(p.name)
        assert mapped == [f"{K1_CONTRACT_ID}.json"]

    def test_absent_is_distinguished_from_no_html_counterpart(
        self, slice_doc: dict
    ) -> None:
        """🔴 两种状态语义不同：`absent`（缺映射）vs 无 HTML 对端（缺组件）。"""
        blob = json.dumps(slice_doc, ensure_ascii=False)
        assert "absent" in blob
        assert "不是" in blob and "无 HTML 对端" in blob


class TestKAP22SheetGeometryAndFormulas:
    """sheet `r=25 c=8 merged=2` / 裸 IF 0。"""

    def test_geometry(self, k1_9_sheet: dict) -> None:
        assert k1_9_sheet["r"] == K1_9_GEOMETRY["r"] == 25
        assert k1_9_sheet["c"] == K1_9_GEOMETRY["c"] == 8
        assert len(k1_9_sheet["merged"]) == K1_9_GEOMETRY["merged"] == 2
        assert k1_9_sheet["merged"] == ["A1:H1", "A2:H2"]

    def test_no_bare_if(self, k1_9_sheet: dict) -> None:
        bad = [
            f"{k}={v}"
            for k, v in k1_9_sheet["formulas"].items()
            if re.search(r"\bIF\s*\(", str(v))
            and not re.search(r"IFERROR|IFNA|IFS\s*\(", str(v))
        ]
        assert bad == [], f"出现裸 IF：{bad}"

    def test_formula_count_caliber(self, k1_9_sheet: dict) -> None:
        """🔴 口径差异：现算公式 **9**（design 说 6）。

        9 = 7 个表头引用（A3/C3/E3/H3/A4/C4/E4 引 `底稿目录`）+ 2 个合计 SUM
        （E15/C21）。design 的 6 不含某个子集 —— 两个数都可自洽，
        但**判据用现算的 9** 并把构成写清，免得日后又对不上。
        """
        f = k1_9_sheet["formulas"]
        assert len(f) == K1_9_GEOMETRY["formulas"] == 9, f"公式 {sorted(f)}"
        header_refs = {k: v for k, v in f.items() if "底稿目录" in str(v)}
        sums = {k: v for k, v in f.items() if str(v).startswith("=SUM(")}
        assert len(header_refs) == 7, f"表头引用 {sorted(header_refs)}"
        assert len(sums) == 2, f"合计 SUM {sorted(sums)}"
        assert len(header_refs) + len(sums) == 9

    def test_uuid_column_would_be_beyond_max_column(self) -> None:
        """🔴 UUID 列（第 9 列 / I 列）超出模板的 `max_column=8`。

        ⇒ 它是**契约要新增**的隐藏列，不是模板里已有的。
        """
        assert K1_9_GEOMETRY["c"] == 8
        uuid_col_index = 9
        assert uuid_col_index > K1_9_GEOMETRY["c"]


class TestKAP23PayloadToTemplateRowMapping:
    """payload ↔ 模板四行映射逐条现读。"""

    def test_reversal_rows_are_r12_to_r14(self, k1_9_sheet: dict) -> None:
        lo, hi = ROW_MAPPING["reversal_rows"]
        assert (lo, hi) == (12, 14)
        # R11 是表头（8 列都有字）
        headers = [
            k for k in k1_9_sheet["cells"] if re.fullmatch(r"[A-H]11", k)
        ]
        assert len(headers) == 8, f"R11 表头列数 {len(headers)}"

    def test_writeoff_rows_are_r18_to_r20(self, k1_9_sheet: dict) -> None:
        lo, hi = ROW_MAPPING["writeoff_rows"]
        assert (lo, hi) == (18, 20)
        headers = [
            k for k in k1_9_sheet["cells"] if re.fullmatch(r"[A-H]17", k)
        ]
        assert len(headers) == 8, f"R17 表头列数 {len(headers)}"

    def test_reversal_total_is_r15_column_e_only(self, k1_9_sheet: dict) -> None:
        """🔴 `reversalTotal` 只落 **E15**（不是整行）。"""
        row, col = ROW_MAPPING["reversal_total"]
        assert (row, col) == (15, "E")
        assert k1_9_sheet["formulas"].get("E15") == "=SUM(E12:E14)"
        # R15 其余列没有公式
        others = [
            k for k in k1_9_sheet["formulas"] if k.endswith("15") and k != "E15"
        ]
        assert others == [], f"R15 还有其他公式 {others}"

    def test_writeoff_total_is_r21_column_c_only(self, k1_9_sheet: dict) -> None:
        """🔴 `writeoffTotal` 只落 **C21**（列与上半表不同）。"""
        row, col = ROW_MAPPING["writeoff_total"]
        assert (row, col) == (21, "C")
        assert k1_9_sheet["formulas"].get("C21") == "=SUM(C18:C20)"
        others = [
            k for k in k1_9_sheet["formulas"] if k.endswith("21") and k != "C21"
        ]
        assert others == [], f"R21 还有其他公式 {others}"

    def test_the_two_totals_sit_in_different_columns(self) -> None:
        """🔴 两个合计**不同列**（E vs C）⇒ adapter 不能按同一列写。"""
        assert ROW_MAPPING["reversal_total"][1] != ROW_MAPPING["writeoff_total"][1]

    def test_sum_ranges_match_the_data_row_spans(self, k1_9_sheet: dict) -> None:
        """两侧都验：SUM 的范围与数据区行段一致。"""
        assert k1_9_sheet["formulas"]["E15"] == "=SUM(E12:E14)"
        assert ROW_MAPPING["reversal_rows"] == (12, 14)
        assert k1_9_sheet["formulas"]["C21"] == "=SUM(C18:C20)"
        assert ROW_MAPPING["writeoff_rows"] == (18, 20)


class TestKAP23RowCountMismatchStrategy:
    """🔴 adapter 须显式处理行数错配（模板固定 3 行 vs HTML 动态行）。"""

    def test_template_has_exactly_three_data_rows_per_block(self) -> None:
        for key in ("reversal_rows", "writeoff_rows"):
            lo, hi = ROW_MAPPING[key]
            assert hi - lo + 1 == TEMPLATE_FIXED_ROWS == 3, key

    def test_html_side_is_dynamic(self) -> None:
        """🔴 HTML 侧是动态行（有 add/remove）⇒ 错配是必然不是偶发。"""
        p = WP_COMPOSABLES / "useK1WriteoffCheck.ts"
        assert p.exists()
        src = strip_comments(cached_text(p))
        assert re.search(r"function\s+addRow\b|\.push\(", src), (
            "HTML 侧没有增行能力 ⇒ 错配前提不成立"
        )
        assert re.search(r"function\s+removeRow\b", src)

    def test_contract_declares_both_overflow_and_underflow_strategy(self) -> None:
        """🔴 契约必须给「超出 3 行」与「少于 3 行」两个策略（缺一即不完整）。"""
        p = CONTRACT_DIR / f"{K1_CONTRACT_ID}.json"
        assert p.exists(), f"生产契约不存在：{p}"
        doc = json.loads(p.read_text(encoding="utf-8"))
        rm = doc["review"]["row_count_mismatch"]
        assert rm["template_fixed_rows"] == 3
        assert rm["overflow_strategy"].strip(), "缺「超出 3 行」策略"
        assert rm["underflow_strategy"].strip(), "缺「少于 3 行」策略"
        assert "扩行" in rm["overflow_strategy"]
        assert "留空" in rm["underflow_strategy"] or "保留模板空行" in rm["underflow_strategy"]

    def test_overflow_must_shift_the_total_row(self) -> None:
        """🔴 扩行会推动合计行 ⇒ 策略必须说明 SUM 范围随之调整。"""
        doc = json.loads(
            (CONTRACT_DIR / f"{K1_CONTRACT_ID}.json").read_text(
                encoding="utf-8"
            )
        )
        s = doc["review"]["row_count_mismatch"]["overflow_strategy"]
        assert "SUM" in s, "扩行策略未说明 SUM 范围如何跟随"
        assert "合计" in s


# ════════════════════════════════════════════════════════════════════════════
# Task 12 / KA-P24：K1 per-entry reviewed contract + provider
# ════════════════════════════════════════════════════════════════════════════
class TestKAP24K1ReviewedContract:
    """Task 12 已晋级：生产契约与 provider source 必须逐 digest 一致。"""

    @pytest.fixture(scope="class")
    def contract(self) -> dict:
        p = CONTRACT_DIR / f"{K1_CONTRACT_ID}.json"
        assert p.exists(), f"生产契约不存在：{p}"
        return json.loads(p.read_text(encoding="utf-8"))

    def test_is_reviewed_with_k1_entry_id(self, contract: dict) -> None:
        assert contract["review_status"] == "reviewed"
        assert contract["semantic_version"] == "1.0.0"
        assert contract["review"]["entry_id"] == K1_ENTRY_ID
        assert contract["review"]["pilot_class"] == "k1_baddebt_reversal_writeoff_check"

    def test_managed_table_binds_key_to_sheet(self, contract: dict) -> None:
        """managed table = `K1-9-writeoff` ↔ `坏账准备转回（收回）、核销检查表K1-9`。"""
        assert contract["review"]["html_store"]["item_id"] == "K1-9-writeoff"
        assert contract["review"]["html_store"]["shape"] == "json_object_with_two_row_arrays"
        assert contract["sheets"][0]["excel_name"] == K1_SHEET
        tables = contract["sheets"][0]["tables"]
        assert [t["table_key"] for t in tables] == ["reversal", "writeoff"]
        assert [t["uuid_col"] for t in tables] == ["I", "J"]

    def test_derived_totals_are_not_input_mode(self, contract: dict) -> None:
        """🔴 两个 `derived_total` 键**禁标** `mode:"input"`。"""
        derived = contract["review"]["derived_total_fields"]
        assert set(derived) == set(DERIVED_TOTAL_KEYS)
        for key, spec in derived.items():
            assert spec["mode"] != "input", f"{key} 标了 input ⇒ Property 24 违反"
            assert spec["mode"] == "derived"
            assert spec["produced_by"] == "computed"
            assert spec["template_anchor"], f"{key} 缺模板 footer 锚点"

    def test_derived_totals_map_to_the_footer_cells(self, contract: dict) -> None:
        """🔴 两个派生键与模板 footer **一一对应**（E15 / C21）。"""
        derived = contract["review"]["derived_total_fields"]
        assert derived["K1-9-reversal-total"]["template_anchor"] == "E15"
        assert derived["K1-9-writeoff-total"]["template_anchor"] == "C21"

    def test_cross_sheet_reads_are_upstream_readonly(self, contract: dict) -> None:
        cs = contract["review"]["cross_sheet_read_fields"]
        assert set(cs) == set(CROSS_SHEET_READ_KEYS)
        for key, spec in cs.items():
            assert spec["access"] == "read_only", key
            assert spec["upstream_sheet"], f"{key} 未写明上游 sheet"

    def test_row_delete_api_kind_is_the_real_arity_two_shape(
        self, contract: dict
    ) -> None:
        """🔴 四元组按 K1 侧现算形态：`(section, id)` arity=2。"""
        rd = contract["review"]["row_delete_api_kind"]
        assert rd["arity"] == 2
        assert rd["param_order"] == ["section", "id"]
        assert rd["kind"] == "by_section_and_identity"
        # 两侧都验：源码里的签名确实是 arity=2
        src = strip_comments(cached_text(WP_COMPOSABLES / "useK1WriteoffCheck.ts"))
        m = re.search(r"function\s+removeRow\s*\(([^)]*)\)", src)
        assert m is not None
        assert m.group(1).count(",") + 1 == 2, f"签名 {m.group(1)!r}"
        assert "section" in m.group(1) and "id" in m.group(1)

    def test_call_sites_carry_the_section_literal(self, contract: dict) -> None:
        """🔴 调用点字面量 `('reversal', …)` / `('writeoff', …)` 都在。"""
        declared = contract["review"]["row_delete_api_kind"]["call_site_literals"]
        assert set(declared) == {"reversal", "writeoff"}
        src = strip_comments(
            cached_text(ROOT / contract["review"]["row_delete_api_kind"]["host"])
        )
        for lit in declared:
            assert re.search(rf"removeRow\(\s*'{lit}'", src), (
                f"找不到调用点 removeRow('{lit}', …)"
            )

    def test_template_sha256_matches(self, contract: dict) -> None:
        import hashlib

        rel = contract["template"]["relative_path"]
        book = ROOT / "backend" / "wp_templates" / rel
        assert book.exists()
        assert contract["template"]["template_sha256"] == hashlib.sha256(
            book.read_bytes()
        ).hexdigest()

    def test_source_locked_provider_matches_disk(self, contract: dict) -> None:
        from app.services.workpaper_sync import phase5_k1_baddebt_reversal_writeoff as provider
        from app.services.workpaper_sync.definitions import canonical_digest

        assert canonical_digest(contract) == canonical_digest(provider.build_contract_payload())
        assert provider.assert_contract_file_matches_source().contract_id == K1_CONTRACT_ID

    def test_exactly_one_reviewed_contract_claims_k1(self) -> None:
        """两侧都验：恰好本生产契约把 entry_id 指向 K1。"""
        owners = []
        for p in CONTRACT_DIR.glob("*.json"):
            doc = json.loads(p.read_text(encoding="utf-8"))
            if (doc.get("review") or {}).get("entry_id") == K1_ENTRY_ID:
                owners.append(p.name)
        assert owners == [f"{K1_CONTRACT_ID}.json"]


class TestKAP25K1DictStoreRoundtrip:
    """K1-9 主代码最小往返：双区独立字段映射 + 未受管标量保留。"""

    def test_two_regions_project_and_merge_without_cross_mapping(self) -> None:
        from app.services.workpaper_sync import phase5_k1_baddebt_reversal_writeoff as p

        contract = p.load_contract_from_disk()
        payload = {
            "tables": {
                "reversal": [{"id": "same-id", "unit": "甲", "amount": 100, "method": "现金"}],
                "writeoff": [{"id": "same-id", "unit": "乙", "amount": 200, "nature": "押金"}],
            },
            "auditProcedures": "保留程序", "auditNote": "保留说明",
            "conclusion": "保留结论", "conclusionOption": "无异常",
        }
        projection = p.build_store_projection(payload, contract=contract)
        assert projection.row_keys == {"reversal": ("same-id",), "writeoff": ("same-id",)}
        merged, applied, visited, touched = p.merge_projection_into_k1_store(
            projection=projection,
            base_state={
                **payload,
                "tables": {
                    "reversal": [{"id": "same-id", "unit": "旧甲", "amount": 0}],
                    "writeoff": [{"id": "same-id", "unit": "旧乙", "amount": 0}],
                },
            },
        )
        assert applied > 0 and visited == len(projection.values)
        assert touched == {"reversal:same-id", "writeoff:same-id"}
        assert merged["tables"]["reversal"][0]["method"] == "现金"
        assert merged["tables"]["writeoff"][0]["nature"] == "押金"
        for key in ("auditProcedures", "auditNote", "conclusion", "conclusionOption"):
            assert merged[key] == payload[key]

    def test_duplicate_identity_is_rejected_within_each_region(self) -> None:
        from app.services.workpaper_sync import phase5_k1_baddebt_reversal_writeoff as p

        contract = p.load_contract_from_disk()
        bad = {"tables": {"reversal": [{"id": "x"}, {"id": "x"}], "writeoff": []}}
        with pytest.raises(p.K1StorePayloadError, match="重复 id"):
            p.build_store_projection(bad, contract=contract)
