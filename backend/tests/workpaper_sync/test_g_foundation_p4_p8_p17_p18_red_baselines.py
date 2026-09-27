# -*- coding: utf-8 -*-
"""G 地基四条红基线：GF-P4 BP-5 · GF-P8 裸 IF · GF-P17 prefill · GF-P18 TB 缺口。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 3
　　　Requirements 2.1 / 3.1 / 3.2 / 5.1 / 5.2 / 6.1

「另起文件」的理由同 `test_g_foundation_p1_p3_fc_reinterpretation.py` 模块头。

═══ 红判据先行 ═══
本文件的四组判据在 Task 5/6/7/8 修复**之前必红**，修复后转绿。
每组都带反向自检（变异必红），防判据空转。
现状红证据留在 `evidence/task3-red-baselines.md`。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

TPL_G = _BACKEND / "wp_templates" / "G"
PREFILL_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"
FRONTEND = _REPO / "audit-platform" / "frontend" / "src"
G1_LABELS = FRONTEND / "components" / "workpaper" / "composables" / "g1SheetLabels.ts"

#: 13 册 owner 模板（G0 / G7 已排除），与 slice `authoritative_templates` 一致。
G_WORKBOOKS: tuple[str, ...] = (
    "G1 交易性金融资产.xlsx",
    "G2 应收利息.xlsx",
    "G3 应收股利.xlsx",
    "G4 债权投资.xlsx",
    "G5 长期应收款.xlsx",
    "G6 其他债权投资.xlsx",
    "G8 其他权益工具投资.xlsx",
    "G9 其他非流动金融资产.xlsx",
    "G10 交易性金融负债.xlsx",
    "G11 投资收益.xlsx",
    "G12 净敞口套期收益.xlsx",
    "G13 公允价值变动收益.xlsx",
    "G14 信用减值损失.xlsx",
)


def _parse_label_map(src: str) -> dict[str, str]:
    """从 `g1SheetLabels.ts` 抠出 `G1_SHEET_LABEL_MAP` 的 18 条键值。

    🔴 必须**只**取该常量的块，不能全文件正则 —— 文件里还有 `extractG1SheetCode` /
    `resolveG1SheetLabel` 的字符串字面量，全文扫会把它们也算成条目。
    """
    m = re.search(
        r"G1_SHEET_LABEL_MAP\s*:\s*Record<string,\s*string>\s*=\s*\{(?P<body>.*?)\n\}",
        src,
        re.DOTALL,
    )
    assert m, "找不到 G1_SHEET_LABEL_MAP 常量块 —— 文件结构变了，判据须改写"
    out: dict[str, str] = {}
    for line in m.group("body").splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("//"):
            continue
        # 形如 `底稿目录: '底稿目录'` 或 `'G1-1': '审定表G1-1'`
        km = re.match(r"^'?(?P<k>[^':]+)'?\s*:\s*'(?P<v>.*)'$", line)
        assert km, f"解析不了这一行: {line!r}"
        out[km.group("k")] = km.group("v")
    return out


@pytest.fixture(scope="module")
def g1_tab_names() -> list[str]:
    wb = openpyxl.load_workbook(TPL_G / "G1 交易性金融资产.xlsx", read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


# ═══════════════════════════════════════════════════════════════════════════
# GF-P4：BP-5 —— G1_SHEET_LABEL_MAP 18 条全部命中模板真实 tab（含空格）
# ═══════════════════════════════════════════════════════════════════════════


class TestGfP4Bp5G1SheetLabels:
    """Validates: 2.1

    现状 **5 条不命中**（BP-5）；Task 5 修复后 18/18 全命中。
    """

    #: BP-5 逐字登记的五条错名 → 模板真名（2026-09-27 按值核，含尾部空格）。
    KNOWN_WRONG: dict[str, tuple[str, str]] = {
        "G1A": ("交易性金融资产实质性程序表G1A", "交易性金融资产实质性程序表G1A "),
        "G1-8": ("业务模式评估问卷G1-8", "业务模式分析G1-8"),
        "G1-10": ("合同现金流量特征测试表G1-10", "合同现金流量特征分析G1-10"),
        "G1-12": ("盘点倒轧表G1-12", "有价证券盘点倒轧表G1-12"),
        "附注国企": ("附注披露信息（国有企业）", "附注披露信息（国企）"),
    }

    def test_map_has_18_entries(self) -> None:
        labels = _parse_label_map(G1_LABELS.read_text(encoding="utf-8"))
        assert len(labels) == 18, f"MAP 条目数变了（现 {len(labels)}，基线 18）: {sorted(labels)}"

    def test_all_18_labels_hit_real_tabs(self, g1_tab_names: list[str]) -> None:
        """核心判据：18 条值全部 ∈ 模板 sheetnames（**逐字**，不 strip）。"""
        labels = _parse_label_map(G1_LABELS.read_text(encoding="utf-8"))
        names = set(g1_tab_names)
        miss = {k: v for k, v in labels.items() if v not in names}
        assert not miss, (
            "以下标签指向模板不存在的 sheet（BP-5）:\n"
            + "\n".join(f"  {k}: {v!r}" for k, v in sorted(miss.items()))
            + f"\n模板真实 tab: {g1_tab_names}"
        )

    def test_trailing_space_is_preserved_verbatim(self, g1_tab_names: list[str]) -> None:
        """🔴 `…G1A ` 的**尾部空格**是源模板事实，必须逐字保留。

        变异「strip 后比较」⇒ 空格缺陷复活而判据仍绿 ⇒ 本条正向锁住空格存在。
        """
        real = [n for n in g1_tab_names if n.startswith("交易性金融资产实质性程序表G1A")]
        assert real == ["交易性金融资产实质性程序表G1A "], f"模板真名变了: {real!r}"
        assert real[0].endswith(" "), "模板 tab 尾部空格消失 ⇒ BP-5 的空格事实不再成立"
        labels = _parse_label_map(G1_LABELS.read_text(encoding="utf-8"))
        assert labels["G1A"] == real[0], (
            f"G1A 标签 {labels['G1A']!r} 与模板真名 {real[0]!r} 不逐字相等"
            "（尾部空格必须保留 —— 这正是 BP-5 的一半）"
        )

    def test_mutation_strip_comparison_would_hide_the_space_defect(
        self, g1_tab_names: list[str]
    ) -> None:
        """自省变异：证明「strip 后比较」确实会放过空格缺陷（所以不许那么写）。"""
        stripped = {n.strip() for n in g1_tab_names}
        assert "交易性金融资产实质性程序表G1A" in stripped, (
            "strip 后错名居然还是不命中 —— 那 BP-5 的空格那一条就不是「strip 会放过」了，"
            "登记须改写"
        )

    @pytest.mark.parametrize("code", sorted(KNOWN_WRONG))
    def test_known_wrong_names_are_really_wrong_and_right_names_really_exist(
        self, code: str, g1_tab_names: list[str]
    ) -> None:
        """台账自检（照 `test_i_cycle_formula_presets.test_no_stale_sheet_label_whitelist`）：
        每个「错名」必须**确实不在**模板里，每个「真名」必须**确实在**。
        """
        wrong, right = self.KNOWN_WRONG[code]
        names = set(g1_tab_names)
        assert wrong not in names, (
            f"台账过期：{wrong!r} 现在确实存在于 G1 模板中 ⇒ 它不再是错名，请移除该条目"
        )
        assert right in names, f"台账的「正确名」{right!r} 不在 G1 模板中: {g1_tab_names}"


# ═══════════════════════════════════════════════════════════════════════════
# GF-P8：13 册裸 IF 按真实正则现算 + 13 条 StoreMergePlan 全挂中性化
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 权威口径 = 跑生产函数 `neutralize_oo_crash_if_formulas(副本)` 数返回的**格数**。
#: 为什么不是 spec RG-4 表里的数（G1 141 / G4 186 …）：那些是 `findall` 的**出现次数**，
#: 一格里嵌两层 IF 会算两次，而中性化是按 `<c>` 元素摘 `<f>`、一格只摘一次。
#: 反证：`g7_oo_crash_if_neutralize._strip_bare_if_cells` 的 docstring 写着
#: 「实测 G7 权威模板 **1065** 个裸 IF 格」—— 与格数口径一字不差（出现次数是 2325）。
#: 实质结论不受影响：13/13 册命中，两种口径都成立。
BARE_IF_CELLS_BASELINE: dict[str, int] = {
    "G1 交易性金融资产.xlsx": 71,
    "G2 应收利息.xlsx": 21,
    "G3 应收股利.xlsx": 18,
    "G4 债权投资.xlsx": 154,
    "G5 长期应收款.xlsx": 61,
    "G6 其他债权投资.xlsx": 137,
    "G8 其他权益工具投资.xlsx": 12,
    "G9 其他非流动金融资产.xlsx": 42,
    "G10 交易性金融负债.xlsx": 28,
    "G11 投资收益.xlsx": 95,
    "G12 净敞口套期收益.xlsx": 7,
    "G13 公允价值变动收益.xlsx": 11,
    "G14 信用减值损失.xlsx": 11,
}


def _neutralize_count(name: str) -> tuple[int, tuple[str, ...]]:
    """在**副本**上跑生产中性化函数，返回 (格数, refs)。权威模板字节一字不动。"""
    from app.services.workpaper_sync.g7_oo_crash_if_neutralize import (  # type: ignore
        neutralize_oo_crash_if_formulas,
    )

    src = TPL_G / name
    before = src.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / name
        shutil.copy2(src, copy)
        refs = neutralize_oo_crash_if_formulas(copy)
        again = neutralize_oo_crash_if_formulas(copy)
        assert again == (), f"{name} 中性化不幂等，复跑还摘到 {len(again)} 格"
    assert src.read_bytes() == before, f"🔴 {name} 权威模板字节被改动了（只许改 substrate 副本）"
    return len(refs), refs


class TestGfP8BareIfNeutralization:
    """Validates: 3.1, 3.2, 3.3, 3.4"""

    @pytest.mark.parametrize("name", G_WORKBOOKS)
    def test_every_workbook_has_bare_if_cells(self, name: str) -> None:
        """13/13 册命中裸 IF ⇒ GC-2「per-file 保守策略」成立。"""
        got, _ = _neutralize_count(name)
        assert got > 0, f"{name} 零裸 IF ⇒ GC-2 的「13 册全命中」前提不再成立"
        assert got == BARE_IF_CELLS_BASELINE[name], (
            f"{name} 裸 IF 格数漂移（现 {got}，基线 {BARE_IF_CELLS_BASELINE[name]}）"
            " ⇒ 模板被改过或口径变了，须复核后再改基线"
        )

    def test_all_13_adjudication_sheets_are_hit(self) -> None:
        """GF-H5 的共性证据①：13 张 `审定表G{N}-1` **全部**命中裸 IF。

        判据从 refs 的 sheet.xml 反查 tab 名（中性化返回的是部件名，不是 tab 名）。
        """
        missing: list[str] = []
        for name in G_WORKBOOKS:
            _, refs = _neutralize_count(name)
            parts = {r.split("!")[0] for r in refs}
            wb = openpyxl.load_workbook(TPL_G / name, read_only=True)
            try:
                # openpyxl 的 worksheets 顺序与 sheet{N}.xml 的序号不保证一致 ⇒
                # 用 workbook 的 rels 顺序：openpyxl 内部 `_sheets` 与 xml 顺序一致，
                # 这里改用「该册有没有任一命中部件对应审定表」的稳妥做法：
                # 审定表是该册唯一带「审定表」字样的 tab，按 tab 索引换算部件名。
                adj = [n for n in wb.sheetnames if "审定表" in n]
                assert len(adj) == 1, f"{name} 的审定表 tab 不唯一: {adj}"
                idx = wb.sheetnames.index(adj[0])
            finally:
                wb.close()
            # sheet{idx+1}.xml 是 openpyxl 顺序对应的部件名（G 目录 13 册实测成立）
            expect_part = f"xl/worksheets/sheet{idx + 1}.xml"
            if expect_part not in parts:
                missing.append(f"{name} 审定表 {adj[0]!r}（期望部件 {expect_part}，命中 {sorted(parts)}）")
        assert not missing, "以下册的审定表未命中裸 IF ⇒ GF-H5 共性证据①不成立:\n" + "\n".join(missing)

    def test_occurrence_count_caliber_differs_from_cell_caliber(self) -> None:
        """锁住「两种口径不同」这一事实本身，防将来有人把 spec 的数字直接当格数用。"""
        from app.services.workpaper_sync.g7_oo_crash_if_neutralize import (  # type: ignore
            _BARE_IF_CALL,
        )

        wb = openpyxl.load_workbook(TPL_G / "G5 长期应收款.xlsx")
        try:
            ws = wb["审定表G5-1"]
            cells = 0
            occurrences = 0
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and c.value.startswith("="):
                        n = len(_BARE_IF_CALL.findall(c.value))
                        if n:
                            cells += 1
                            occurrences += n
        finally:
            wb.close()
        assert cells == 61, f"审定表G5-1 格数漂移: {cells}"
        assert occurrences == 122, f"审定表G5-1 出现次数漂移: {occurrences}"
        assert occurrences == 2 * cells, (
            "两种口径不再是 2:1 ⇒ spec RG-4 表的「×2」解释须重核"
        )

    def test_heuristic_probe_would_undercount(self) -> None:
        """变异：改用「`IF(` 后跟 `IS*`/`AND`/`OR`」启发式 ⇒ G11-2 从 44 格降到更少。"""
        from app.services.workpaper_sync.g7_oo_crash_if_neutralize import (  # type: ignore
            _BARE_IF_CALL,
        )

        heuristic = re.compile(r"(?<![A-Za-z0-9_.])IF\s*\(\s*(IS[A-Z]+|AND|OR)\s*\(")
        wb = openpyxl.load_workbook(TPL_G / "G11 投资收益.xlsx")
        try:
            ws = wb["明细分析表G11-2"]
            real = heur = 0
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and c.value.startswith("="):
                        if _BARE_IF_CALL.search(c.value):
                            real += 1
                        if heuristic.search(c.value):
                            heur += 1
        finally:
            wb.close()
        assert real == 44, f"明细分析表G11-2 真实格数漂移: {real}"
        assert heur < real, (
            f"启发式({heur}) 没有低估真实值({real}) ⇒ 该变异不再能证明启发式有害，须换变异"
        )

    #: 🔴 17 条 G adapter 的**交付归属**（GC-2 覆盖面）。
    #:
    #: `StoreMergePlan` 的 `provider_module` 是必填字段 ⇒ plan **不能**在 provider 模块
    #: 存在之前声明。而 17 条 entry 分散在**四份** spec：
    #:
    #: | spec | entry |
    #: |---|---|
    #: | `g-cycle-sync-foundation-and-first-canary`（本 spec） | G2 |
    #: | `g4-g6-shared-workbook-three-entry-lanes` | G4×3 + G6×3 |
    #: | `g5-nested-sections-and-template-defects` | G5 |
    #: | `g-cycle-single-region-detail-lanes` | G1 G3 G8 G9 G10 G11 G12 G13 G14 |
    #:
    #: ⇒ 判据形态必须是「**已交付的**一律带中性化」+「未交付的登记归属」，
    #: 不能写成「17 条全在」—— 那会在最后一份 lane spec 交付前一直红，
    #: 而永久红的判据等于没有判据（大家学会忽略它）。
    ADAPTER_OWNER_SPEC: dict[str, str] = {
        "g2.interest_receivable_detail": "g-cycle-sync-foundation-and-first-canary",
        "g4.bond_main": "g4-g6-shared-workbook-three-entry-lanes",
        "g4.sppi_inventory": "g4-g6-shared-workbook-three-entry-lanes",
        "g4.ecl_stage": "g4-g6-shared-workbook-three-entry-lanes",
        "g6.other_bond_main": "g4-g6-shared-workbook-three-entry-lanes",
        "g6.sppi_fair_value": "g4-g6-shared-workbook-three-entry-lanes",
        "g6.ecl_stage": "g4-g6-shared-workbook-three-entry-lanes",
        "g5.long_term_receivable_detail": "g5-nested-sections-and-template-defects",
        "g1.trading_financial_assets_detail": "g-cycle-single-region-detail-lanes",
        "g3.dividend_receivable_detail": "g-cycle-single-region-detail-lanes",
        "g8.other_equity_detail": "g-cycle-single-region-detail-lanes",
        "g9.other_noncurrent_detail": "g-cycle-single-region-detail-lanes",
        "g10.trading_liabilities_detail": "g-cycle-single-region-detail-lanes",
        "g11.investment_income_detail": "g-cycle-single-region-detail-lanes",
        "g12.net_hedge_detail": "g-cycle-single-region-detail-lanes",
        "g13.fair_value_changes_detail": "g-cycle-single-region-detail-lanes",
        "g14.credit_impairment_detail": "g-cycle-single-region-detail-lanes",
    }

    def test_adapter_owner_registry_covers_17(self) -> None:
        assert len(self.ADAPTER_OWNER_SPEC) == 17, len(self.ADAPTER_OWNER_SPEC)

    def test_every_delivered_g_adapter_declares_neutralization(self) -> None:
        """🔴 Task 6 的转绿点（GC-2）：**已交付**的 G adapter 一律带中性化声明，无例外。

        「per-file 保守策略」：BP-4（真 OO 9.4 场景集）未交付前，不得以「裸 IF 数少」
        推断某册不需要 —— 13 册全命中裸 IF，13 条 plan 全挂。
        """
        from app.services.workpaper_sync.store_item_registry import (  # type: ignore
            STORE_MERGE_REGISTRY,
        )

        delivered = [a for a in self.ADAPTER_OWNER_SPEC if a in STORE_MERGE_REGISTRY]
        no_fn = sorted(
            a
            for a in delivered
            if getattr(STORE_MERGE_REGISTRY[a], "oo_crash_neutralization_fn", None)
            != "neutralize_oo_crash_if_formulas"
        )
        assert not no_fn, (
            "以下**已交付**的 G adapter 未挂 oo_crash_neutralization_fn ⇒ "
            f"开 OO 会 editor_error_-82: {no_fn}"
        )

    def test_undelivered_adapters_are_registered_with_owning_spec(self) -> None:
        """未交付的 G adapter 必须有归属 spec 登记（禁沉默欠账）。

        本判据在全部 17 条交付后自然变成空集检查 ⇒ 不会永久红。
        """
        from app.services.workpaper_sync.store_item_registry import (  # type: ignore
            STORE_MERGE_REGISTRY,
        )

        undelivered = {
            a: spec for a, spec in self.ADAPTER_OWNER_SPEC.items() if a not in STORE_MERGE_REGISTRY
        }
        unowned = sorted(a for a, spec in undelivered.items() if not spec)
        assert not unowned, f"以下未交付 adapter 无归属 spec: {unowned}"
        # 本 spec 自己的那一条（G2）在收口后必须已交付
        assert "g2.interest_receivable_detail" in self.ADAPTER_OWNER_SPEC

    def test_excel_adapter_has_no_adapter_id_literal_branch(self) -> None:
        """🔴 GC-2 禁令：`adapters/excel.py` 不得有 `if adapter_id == "…"` 字面量分支。"""
        p = _BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "excel.py"
        src = p.read_text(encoding="utf-8")
        hits = re.findall(r"adapter_id\s*==\s*['\"][a-z0-9_.]+['\"]", src)
        assert not hits, (
            "excel.py 出现 adapter_id 字面量分支（Task 13 已收敛掉两处，不得回退）: " f"{hits}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# GF-P17：prefill 两块 sheet 名（现状 2 块不命中 ⇒ 必红）
# ═══════════════════════════════════════════════════════════════════════════


def _g_prefill_blocks() -> list[tuple[int, dict]]:
    """G 循环（除 G0 / G7）prefill 块，带原始索引。

    🔴 `G7` 必须显式排除：`r"G(?:[1-9]|1[0-4])"` 的 `[1-9]` 含 7。
    """
    raw = json.loads(PREFILL_PATH.read_text(encoding="utf-8"))
    return [
        (i, b)
        for i, b in enumerate(raw["mappings"])
        if re.fullmatch(r"G(?:[1-9]|1[0-4])", b.get("wp_code", ""))
        and b.get("wp_code") != "G7"
    ]


@pytest.fixture(scope="module")
def g_template_tabs() -> dict[str, list[str]]:
    """{wp_code: [tab, ...]}，跳过 ~$ 锁文件。口径照
    `test_i_cycle_formula_presets._load_template_sheetnames`（**不新造第二套**）。"""
    out: dict[str, list[str]] = {}
    for p in sorted(TPL_G.glob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        m = re.match(r"^(G\d+)\s", p.stem)
        if not m:
            continue
        wb = openpyxl.load_workbook(p, read_only=True)
        out[m.group(1)] = list(wb.sheetnames)
        wb.close()
    return out


class TestGfP17PrefillSheetNames:
    """Validates: 5.1, 5.2, 5.3, 5.4

    现状 **2 块不命中**（块 [169] G13 / [170] G14）；Task 7 修复后全命中。
    """

    #: RG-5 逐字登记：块索引 → (错名, 真名)。
    KNOWN_WRONG: dict[int, tuple[str, str, str]] = {
        169: ("G13", "明细分析表G13-2", "明细表G13-2"),
        170: ("G14", "明细分析表G14-2", "明细表G14-2"),
    }

    def test_block_count_baseline(self) -> None:
        blocks = _g_prefill_blocks()
        assert len(blocks) == 47, f"G 块数变了（现 {len(blocks)}，基线 47）"

    def test_every_block_sheet_exists_in_template(
        self, g_template_tabs: dict[str, list[str]]
    ) -> None:
        """核心判据（GC-8 补的那条）：每个 G 块的 `sheet` ∈ 对应源 xlsx 真实 tab。

        🔴 **不 strip** —— G 目录有两个名字带空格的 tab
        （`交易性金融资产实质性程序表G1A ` 尾部空格 / `信用减值损失审计程序表G14A -修订前` 名中空格），
        strip 后比较会把空格缺陷放过。
        """
        bad: list[str] = []
        for i, b in _g_prefill_blocks():
            wp, sheet = b["wp_code"], b.get("sheet")
            tabs = g_template_tabs.get(wp)
            if tabs is None:
                bad.append(f"[{i}] {wp}: 源模板目录下找不到对应 xlsx")
                continue
            if sheet not in tabs:
                near = [n for n in tabs if sheet and sheet[-6:] in n]
                bad.append(f"[{i}] {wp} sheet={sheet!r} 不在模板中；形近真名: {near}")
        assert not bad, (
            "prefill 块指向源模板不存在的 sheet（预设看得见但预填写不进）:\n"
            + "\n".join(bad)
            + "\n⇒ 跑 `python backend/scripts/fix/fix_g_cycle_prefill_sheet_names.py --apply`"
        )

    @pytest.mark.parametrize("idx", sorted(KNOWN_WRONG))
    def test_known_wrong_names_really_wrong_and_right_names_really_exist(
        self, idx: int, g_template_tabs: dict[str, list[str]]
    ) -> None:
        """台账自检：错名确实不在模板里、真名确实在（防台账变逃逸阀 / 过期）。"""
        wp, wrong, right = self.KNOWN_WRONG[idx]
        tabs = g_template_tabs[wp]
        assert wrong not in tabs, f"台账过期：{wrong!r} 现在确实存在于 {wp} 模板中，请移除条目"
        assert right in tabs, f"台账真名 {right!r} 不在 {wp} 模板中: {tabs}"
        # 真名唯一：该册含「明细」的 tab 只有这一个 ⇒ 改名无歧义
        cand = [n for n in tabs if "明细" in n]
        assert cand == [right], f"{wp} 含「明细」的 tab 不唯一，改名有歧义: {cand}"

    def test_g11_prefix_is_genuinely_different(
        self, g_template_tabs: dict[str, list[str]]
    ) -> None:
        """错名根因锁定：G13/G14 照抄了 G11 的「明细分析表」前缀，而 G11 那个是真名。"""
        assert "明细分析表G11-2" in g_template_tabs["G11"], (
            "G11 的 `明细分析表G11-2` 不再是真名 ⇒ RG-5 的「照抄 G11 前缀」根因须重写"
        )

    def test_space_bearing_tabs_exist_so_strip_is_forbidden(
        self, g_template_tabs: dict[str, list[str]]
    ) -> None:
        """正向锁住「不得 strip」的前提：G 目录确实有带空格的 tab 名。"""
        assert "交易性金融资产实质性程序表G1A " in g_template_tabs["G1"]
        g14_with_space = [n for n in g_template_tabs["G14"] if " " in n]
        assert g14_with_space == ["信用减值损失审计程序表G14A -修订前"], g14_with_space

    def test_g13_g14_preset_counts_do_not_shrink(self) -> None:
        """需求 5.4：修复后 `convert_prefill_presets()` 的 G13/G14 计数不减少。"""
        from app.services.formula_management.preset_library import (  # type: ignore
            convert_prefill_presets,
        )

        from collections import Counter

        # 返回的是 list[PresetEntry]（不是 dict）⇒ 按 page_key 计数
        counts = Counter(e.page_key for e in convert_prefill_presets())
        assert counts["workpaper:G13"] >= 14, f"G13 预设数下降: {counts['workpaper:G13']}"
        assert counts["workpaper:G14"] >= 13, f"G14 预设数下降: {counts['workpaper:G14']}"
        # 13 个 G 科目全非零（与 F5 的 0 形成对比，需求 Introduction 的事实锚）
        zero = [
            f"G{n}"
            for n in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14)
            if counts[f"workpaper:G{n}"] == 0
        ]
        assert not zero, f"以下 G 科目预设为 0（F5 同型缺陷在 G 出现）: {zero}"


# ═══════════════════════════════════════════════════════════════════════════
# GF-P18：三家 TB 发布门缺口（G1 / G4-main / G6-main 的 publishToTb 为 0）
# ═══════════════════════════════════════════════════════════════════════════

COMPOSABLES = FRONTEND / "components" / "workpaper" / "composables"

#: 🔴 GC-9 裁决修正（2026-09-27 四层现算，详见 `evidence/task8-tb-gate-adjudication.md`）：
#: spec RG-6 说「G1 / G4-main / G6-main **三家**未接 TB 显式发布门」，
#: 但它只数了 `useG{N}Adjudication.ts` 一层。按**四层**（composable / FormData /
#: TabAdjudication.vue / 宿主）现算：
#:
#:   * **G1 其实已接** —— `G1TabAdjudication.vue:356` 有真 `async handlePublishToTb()`
#:     → `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，带中文二次确认，
#:     L251 按钮绑定；`useG1TraFinFormData.ts:107-108` 与宿主 L475 的引用是**注释**
#:     （记录旧路径已被 `tb-writeback-explicit-publish-gate` Task 12 移除）。
#:     ⇒ 缺口面从三家收窄为**两家**。
#:   * **G4-main 真缺口** —— 全仓 G4 文件零 `publishToTb`；`G4TabAdjudication.vue`
#:     只 read TB（`fetchTrialBalance()` / 显示 `trialBalanceAmount`），无任何发布入口。
#:   * **G6-main 真缺口且是回归** —— `useG6MainFormData.ts:401-406` 注释记载旧
#:     `writebackTB` 变体端点（`POST /api/projects/{pid}/trial_balance`）已作为
#:     「零消费死代码」移除、并声称「TB 回写走显式发布门 publish-to-tb」，
#:     但 `G6TabAdjudication.vue` **没有**该门 ⇒ 旧路径已删、新门未建，
#:     G6 审定数现在**没有任何** TB 回写通路。
GATE_CONNECTED_FAMILIES: tuple[str, ...] = ("G1",)
GATE_GAP_FAMILIES: tuple[str, ...] = ("G4-main", "G6-main")

#: 十一家「`useG{N}Adjudication.ts` 自带 publishToTb」的计数基线（RG-6 的那一层）。
TB_GATE_BASELINE: dict[str, int] = {
    "useG4MainAdjudication.ts": 0,
    "useG6MainAdjudication.ts": 0,
    "useG2Adjudication.ts": 3,
    "useG3Adjudication.ts": -1,  # -1 = 只断言 > 0，不锁具体值
    "useG5Adjudication.ts": 4,
    "useG8Adjudication.ts": -1,
    "useG9Adjudication.ts": -1,
    "useG10Adjudication.ts": -1,
    "useG11Adjudication.ts": -1,
    "useG12Adjudication.ts": -1,
    "useG13Adjudication.ts": -1,
    "useG14Adjudication.ts": -1,
}

#: `useG{N}Adjudication.ts` 层零 `publishToTb` 的三家（**不等于**「未接门」——见上方裁决）。
GAP_FAMILIES = ("useG1Adjudication.ts", "useG4MainAdjudication.ts", "useG6MainAdjudication.ts")

#: 四层探测面：{family: (glob 或相对路径, ...)}
GATE_LAYERS: dict[str, tuple[str, ...]] = {
    "G1": (
        "components/workpaper/composables/useG1Adjudication.ts",
        "components/workpaper/composables/useG1TraFinFormData.ts",
        "components/workpaper/g1-trading-financial-assets/core/G1TabAdjudication.vue",
        "components/workpaper/GtG1TradingFinancialAssets.vue",
    ),
    "G4-main": (
        "components/workpaper/composables/useG4MainAdjudication.ts",
        "components/workpaper/composables/useG4MainFormData.ts",
        "components/workpaper/g4-bond-investment-main/core/G4TabAdjudication.vue",
        "components/workpaper/GtG4BondInvestmentMain.vue",
    ),
    "G6-main": (
        "components/workpaper/composables/useG6MainAdjudication.ts",
        "components/workpaper/composables/useG6MainFormData.ts",
        "components/workpaper/g6-other-bond-investment-main/core/G6TabAdjudication.vue",
        "components/workpaper/GtG6OtherBondMain.vue",
    ),
}

#: 真发布门的判据 = 显式发布端点字面量（**不是** `publishToTb` 这个名字 ——
#: 名字可能只出现在注释里；端点字面量出现在代码里才是活路径）。
PUBLISH_ENDPOINT = "audit-determination/publish-to-tb"


def _find_composable(name: str) -> Path:
    p = COMPOSABLES / name
    if p.exists():
        return p
    hits = list(FRONTEND.rglob(name))
    assert hits, f"找不到 {name}"
    return hits[0]


class TestGfP18TbPublishGateGap:
    """Validates: 6.1, 6.2, 6.3"""

    def test_three_families_have_zero_publish_to_tb_in_adjudication_layer(self) -> None:
        """锁住 RG-6 实测的那一层事实：三家 `useG*Adjudication.ts` 的 `publishToTb` 为 0。

        🔴 这**只是一层**。「未接门」的结论不能由它单独推出 —— 见
        `test_gate_presence_by_layer` 的四层裁决（G1 的门在组件层）。
        """
        got = {
            n: _find_composable(n).read_text(encoding="utf-8").count("publishToTb")
            for n in GAP_FAMILIES
        }
        assert got == dict.fromkeys(GAP_FAMILIES, 0), (
            f"该层计数变了: {got}\n若某家在本层接上了 ⇒ evidence 须更新，不得静默放行"
        )

    @pytest.mark.parametrize("family", sorted(GATE_LAYERS))
    def test_gate_presence_by_layer(self, family: str) -> None:
        """🔴 GC-9 的核心判据：按**四层 + 端点字面量**判「有没有真发布门」。

        判「有门」= 任一层的**代码**（去注释后）含 `audit-determination/publish-to-tb`。
        用端点字面量而不是 `publishToTb` 名字：后者在 G1/G6 都出现在注释里
        （记录旧路径已移除），按名字数会把注释当成门。
        """
        code_hits: list[str] = []
        comment_only: list[str] = []
        for rel in GATE_LAYERS[family]:
            p = FRONTEND / rel
            if not p.exists():
                continue
            raw = p.read_text(encoding="utf-8")
            if PUBLISH_ENDPOINT not in raw:
                continue
            if PUBLISH_ENDPOINT in self._code_only(raw):
                code_hits.append(rel)
            else:
                comment_only.append(rel)

        if family in GATE_CONNECTED_FAMILIES:
            assert code_hits, (
                f"{family} 应已接显式发布门，但四层里没有一处**代码**含 {PUBLISH_ENDPOINT!r}；"
                f"只在注释里出现: {comment_only}\n"
                "⇒ GC-9 的裁决（G1 已接）不再成立，evidence 须重写"
            )
        else:
            assert not code_hits, (
                f"{family} 已接上显式发布门（代码命中 {code_hits}）⇒ 缺口已闭合，"
                "请把它从 GATE_GAP_FAMILIES 移到 GATE_CONNECTED_FAMILIES 并更新 evidence"
            )

    def test_gap_families_are_blocked_from_being_managed(self) -> None:
        """🔴 需求 6.2 的本地硬门：两家真缺口在裁决落地前**不得受管**。

        判据形态 = 「它们不得出现在已交付 provider 的 `STORE_MERGE_REGISTRY` 里」。
        G4-main / G6-main 一旦注册 adapter 而 TB 门仍缺 ⇒ 打红。
        """
        from app.services.workpaper_sync.store_item_registry import (  # type: ignore
            STORE_MERGE_REGISTRY,
        )

        gated_adapters = {"G4-main": "g4.bond_main", "G6-main": "g6.other_bond_main"}
        violations = [
            f"{fam} 的 adapter {aid!r} 已注册，但其 TB 显式发布门仍缺"
            for fam, aid in gated_adapters.items()
            if fam in GATE_GAP_FAMILIES and aid in STORE_MERGE_REGISTRY
        ]
        assert not violations, (
            "\n".join(violations)
            + "\n⇒ 先补显式发布门（属 tb-writeback-explicit-publish-gate 作业面），"
            "或在本 spec 的 evidence 里给出「受管不引入第二条 TB 写入路径」的书面裁决"
        )

    def test_g6_main_gate_removal_without_replacement_is_registered(self) -> None:
        """🔴 G6-main 的缺口是**回归**，把这个事实锁成不变式。

        `useG6MainFormData.ts` 注释声称「TB 回写走显式发布门 publish-to-tb」，
        而 `G6TabAdjudication.vue` 没有该门 ⇒ 旧路径已删、新门未建。
        本判据在补上门之后会打红，提示把 G6-main 移出 GATE_GAP_FAMILIES。
        """
        form = FRONTEND / "components/workpaper/composables/useG6MainFormData.ts"
        tab = FRONTEND / "components/workpaper/g6-other-bond-investment-main/core/G6TabAdjudication.vue"
        assert form.exists() and tab.exists()
        claim = form.read_text(encoding="utf-8")
        assert "publish-to-tb" in claim, (
            "useG6MainFormData.ts 不再声称走显式发布门 ⇒ 本回归登记的前提变了"
        )
        assert PUBLISH_ENDPOINT not in self._code_only(tab.read_text(encoding="utf-8")), (
            "G6TabAdjudication.vue 已补上显式发布门 ⇒ 回归已闭合，"
            "请把 G6-main 从 GATE_GAP_FAMILIES 移走并更新 evidence"
        )

    def test_other_ten_families_have_publish_to_tb(self) -> None:
        """对照面：其余十家**都有** `publishToTb` ⇒ 「三家是缺口」而非「全循环都没接」。"""
        zero: list[str] = []
        for n, expect in TB_GATE_BASELINE.items():
            if n in GAP_FAMILIES or expect == 0:
                continue
            c = _find_composable(n).read_text(encoding="utf-8").count("publishToTb")
            if c == 0:
                zero.append(n)
            elif expect > 0:
                assert c == expect, f"{n} 的 publishToTb 计数漂移（现 {c}，基线 {expect}）"
        assert not zero, f"以下 entry 也没接 publishToTb ⇒ 缺口面不止三家: {zero}"

    #: 注释行/块（判据必须剔除它们才能区分「活路径」与「注释残留」）。
    _LINE_COMMENT = re.compile(r"^\s*(//|\*|/\*)")

    @classmethod
    def _code_only(cls, src: str) -> str:
        """去掉行注释与块注释后的代码文本。

        🔴 为什么必须去注释：需求 6.1 要区分残留引用是**活路径**还是**注释/类型残留**。
        直接 `src.count("trial-balance")` 把两者混在一个数里 ——
        本轮实测过一次：为 GC-9 补一条说明性注释（里面提到
        `/api/trial-balance/query`）就把计数从 1 顶到 2，判据打红而生产行为毫无变化。
        那不是回归，是判据口径错。
        """
        out: list[str] = []
        in_block = False
        for line in src.splitlines():
            stripped = line.strip()
            if in_block:
                if "*/" in stripped:
                    in_block = False
                continue
            if stripped.startswith("/*"):
                if "*/" not in stripped:
                    in_block = True
                continue
            if cls._LINE_COMMENT.match(line):
                continue
            # 行尾注释：只截 `//` 之后（不处理字符串里的 `//`，G 这三家实测无此形态）
            out.append(line.split("//", 1)[0])
        return "\n".join(out)

    def test_gap_families_still_carry_trial_balance_references(self) -> None:
        """🔴 需求 6.1：三家残留 `trial-balance` / `writeback` 的**代码 vs 注释**分布。

        基线是**代码**计数（去注释后），与全文计数的差就是「注释残留」那一份 ——
        这个差本身就是 Task 8 要的裁决（逐处按值核的结果，见
        `evidence/task8-tb-gate-adjudication.md`）：

        | family | trial-balance 代码/全文 | writeback 代码/全文 | 裁决 |
        |---|---|---|---|
        | G1 | **0**/2 | 1/5 | 两处 `trial-balance` **全在注释**（JSDoc L481-487 记录 `g1:writeback-trial-balance` dispatch 已被 `tb-writeback-explicit-publish-gate` Task 12 移除）⇒ 死代码记录，非活路径 |
        | G4-main | 1/1 | 2/3 | 代码里确有引用（`fetchTrialBalance` 读 TB 的那条），但**只读不写** |
        | G6-main | 1/1 | 2/2 | 同 G4：只读 TB 做核对，无写入 |

        🔴 `writeback` 小写在代码里的那 1~2 处**不是 TB 回写** ——
        是「G1-3/G4-3/G6-4 调整分录净额回写到审定表行 store」（`lastWritebackNet` /
        `applyAdjustmentWriteback`），落点是 `checklist_responses`，不碰 `trial_balance`。
        FC-9 红线看的是对 `trial_balance` 的写次数，这几处不计入。
        """
        expect = {
            "useG1Adjudication.ts": (0, 1),
            "useG4MainAdjudication.ts": (1, 2),
            "useG6MainAdjudication.ts": (1, 2),
        }
        got = {}
        for n in expect:
            code = self._code_only(_find_composable(n).read_text(encoding="utf-8"))
            got[n] = (code.count("trial-balance"), code.count("writeback"))
        assert got == expect, f"三家残留**代码**引用计数漂移: {got}（基线 {expect}）"

    def test_g1_trial_balance_references_are_comments_only(self) -> None:
        """G1 裁决的正向锁：`trial-balance` 在**全文有、代码无** ⇒ 纯注释残留。"""
        raw = _find_composable("useG1Adjudication.ts").read_text(encoding="utf-8")
        assert raw.count("trial-balance") == 2, "全文计数变了，裁决须重核"
        assert "trial-balance" not in self._code_only(raw), (
            "G1 的 trial-balance 进了代码 ⇒ 从「注释残留」变成活路径，须重新裁决"
        )
        assert "g1:writeback-trial-balance" in raw, (
            "记录旧 dispatch 名的那条注释被删了 ⇒ 裁决失去溯源依据，不得删"
        )

    def test_no_gap_family_writes_trial_balance_directly(self) -> None:
        """FC-9 红线（三家侧）：代码里不得出现绕过显式门的 TB 写入端点。

        被禁的两种旧形态（`tb-writeback-explicit-publish-gate` 已裁定）：
        `PUT .../trial-balance/writeback` 与 `POST /api/projects/{pid}/trial_balance`。

        🔴 探针必须是**端点字面量**（带路径分隔符），不能是裸词 `trial_balance`：
        `G1TabAdjudication.vue:360` 的二次确认文案里有
        「写入试算表（trial_balance）」这句中文说明 —— 裸词探针会把**用户提示文案**
        判成绕过门的写入路径（本轮实测踩过一次）。
        """
        forbidden = ("trial-balance/writeback", "/trial_balance")
        bad: list[str] = []
        for fam, layers in GATE_LAYERS.items():
            for rel in layers:
                p = FRONTEND / rel
                if not p.exists():
                    continue
                code = self._code_only(p.read_text(encoding="utf-8"))
                for pat in forbidden:
                    if pat in code:
                        bad.append(f"{fam} / {rel}: 代码含 {pat!r}")
        assert not bad, "出现绕过显式发布门的 TB 写入路径（FC-9 红线）:\n" + "\n".join(bad)

    def test_comment_stripper_is_not_vacuous(self) -> None:
        """反向自检：去注释函数确实在工作（否则上一条会退化成全文计数）。"""
        src = _find_composable("useG6MainAdjudication.ts").read_text(encoding="utf-8")
        code = self._code_only(src)
        assert src.count("trial-balance") > code.count("trial-balance"), (
            "去注释后 trial-balance 计数没变 ⇒ 说明该文件的注释里本就没有它，"
            "或去注释函数失效（本轮 GC-9 注释里确实写了 /api/trial-balance/query）"
        )
        assert "const ITEM_ID_TB" in code, "去注释把真代码也删了"

    def test_g6_main_wrong_account_comment_is_fixed(self) -> None:
        """🔴 需求 6.4：`useG6MainAdjudication.ts` 那条「已纠正为 1505」的错注释须修为 1506。

        1505 本身在 `KNOWN_BAD_CODES['G6']` 里 ⇒ 注释把错码当真码。
        现状必红；Task 8 修复后转绿。
        """
        from tests.four_table.test_g_cycle_formula_presets import (  # type: ignore
            G_ACCOUNT_CODES,
            KNOWN_BAD_CODES,
        )

        assert G_ACCOUNT_CODES["G6"] == "1506"
        assert "1505" in KNOWN_BAD_CODES["G6"], "1505 不再是已纠偏错码 ⇒ 本判据前提须重核"
        src = _find_composable("useG6MainAdjudication.ts").read_text(encoding="utf-8")
        assert "已纠正为 1505" not in src and "已纠正为1505" not in src, (
            "错注释仍在：注释声称真码是 1505，而 1505 在 KNOWN_BAD_CODES['G6'] 里"
        )

    def test_tb_keys_are_taken_by_value_not_derived_from_account_code(self) -> None:
        """🔴 需求 6.4 / GF-P19：TB 键名**按值取**，不得按科目码推演。

        变异「按 `G_ACCOUNT_CODES` 生成 `G4-1-adj-tb-1504`」⇒ 与源码真键不符。
        """
        from tests.four_table.test_g_cycle_formula_presets import (  # type: ignore
            G_ACCOUNT_CODES,
        )

        cases = {
            "useG4MainAdjudication.ts": ("G4", "G4-1-adj-tb-1501"),
            "useG6MainAdjudication.ts": ("G6", "G6-1-adj-tb-1503"),
        }
        for fname, (wp, real_key) in cases.items():
            src = _find_composable(fname).read_text(encoding="utf-8")
            assert real_key in src, f"{fname} 里找不到真键 {real_key!r}（键名是稳定标识符，不得改）"
            derived = f"{wp}-1-adj-tb-{G_ACCOUNT_CODES[wp]}"
            assert derived != real_key, "推演键恰好等于真键 ⇒ 本变异失去意义，须换 entry"
            assert derived not in src, (
                f"{fname} 里出现了按科目码推演的键 {derived!r} —— 真库没有这个键，读不到数据"
            )

    def test_pl_cycles_use_current_period_caliber(self) -> None:
        """需求 6.5：损益类 G11/G12/G13/G14 的 TB 口径是本期发生额（`PL_CYCLES` 已冻结）。"""
        from tests.four_table.test_g_cycle_formula_presets import PL_CYCLES  # type: ignore

        assert PL_CYCLES == {"G11", "G12", "G13", "G14"}, PL_CYCLES
