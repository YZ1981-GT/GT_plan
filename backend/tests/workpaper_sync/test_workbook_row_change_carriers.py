# -*- coding: utf-8 -*-
"""Task 8 + 12 —— 引用载体扫描判据（Requirement 4 / AC 2.6 / 9.4）。

spec: excel-workbook-wide-row-change-propagation / Wave 2 Task 8, 12
Requirements: 2.6, 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 9.4
Properties: **P16** / **P17** / **P18** / **P19** / **P20**

═══ 本文件的核心一条 ═══

`test_scanner_agrees_with_rewriter_on_whole_corpus` —— 扫描器与改写器在**全库 351 份**上
必须同口径。这条是其余判据的地基：扫描算出声明传播量、改写器实际执行，两者口径不一致时
**要么**假红（与计划一致的传播被判漂移），**要么**漏扫一类载体让那类引用静默指向错行。

🔴 它实测抓到过一次真问题：首版按「去重行号数」对账，在 `'表'!E10:F10`（两个端点都是
行 10）上 12 处不吻合 —— 暴露出 `PropagationEntry` 缺 `piece_count`，声明与实测单位不同。

═══ 判据纪律 ═══

* **分母先立**：每条载体判据先断言该载体在语料里的处数 > 0（或显式声明是注入变体），
  否则判据在空集上恒真。全库为 0 的三类（3D / pivot / dv-cf 在多数模板上）一律用注入。
* **不手抄期望清单**：载体词表一致性走 `assert_carrier_tables_consistent()`。
* 真实模板优先：D2（首要载体，52 处）/ K11（114 处 19 行）都用权威模板本体。
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import (  # noqa: E402
    _normalise_part,
    _parse_workbook_xml,
)
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402
from app.services.workpaper_sync.excel_row_shift import (  # noqa: E402
    _F_RE,
    _rewrite_formula_refs,
    iter_qualified_references,
)

TEMPLATE_ROOT = _BACKEND / "wp_templates"

#: 首要判据载体（Wave 0 Gate 1 裁决）—— 今天唯一既有已审核契约又有真实跨 sheet 引用的 entry。
D2_REL = "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
D2_SHEET = "明细表D2-2"
#: 结构判据载体 —— 受管区 `A7:N25`，被 114 处引用覆盖 19 行。
K11_REL = "K/K11 资产减值损失.xlsx"
K11_SHEET = "审定表K11-1"

#: 冻结的实测分母。改这里必须同时改 design.md 与清册，三侧锁死。
#:
#: `d2_formula` + `d2_prefix_without_coordinate` = 52 = 清册的 `referencing_sites`
#: —— 清册数「有多少处引用指向这张 sheet」，扫描器把取不到坐标的 10 处分流到不传播登记。
EXPECTED: dict[str, int] = {
    "d2_formula": 42,
    "d2_defined_name": 3,
    "d2_hyperlink_location": 1,
    "d2_prefix_without_coordinate": 10,
    "d2_inventory_referencing_sites": 52,
    "k11_formula": 114,
    "k11_defined_name": 1,
    #: 🔴 这四个数被改动过**两次**，两次都是识别能力的修正，各自留痕：
    #:
    #: **① Task 8「带引号外部工作簿」盲区**（重分类，总量守恒）
    #:   sheet 145,106 → 144,155（-951）/ external 2,908 → 3,883（+975）/
    #:   no_target 203 → 179（-24），合计 **-951+975-24 = 0**。
    #:   成因：Excel 对含标点的外部工作簿名加引号，`[n]` 落在**引号内**
    #:   （`'[31]已审利润纵向分析A1-13-4'!$E$27`）⇒ `_QUALIFIED_PREFIX_RE` 的 `book`
    #:   分组不命中，整段被 `first` 吃掉，剥引号后得到含 `[n]` 的假 sheet 名。
    #:   实测 **2,971 处 / 150 份模板**被误判成本工作簿内的 sheet。
    #:
    #: **② Task 13「数字字符引用」**（纯识别修正，净增）
    #:   sheet 144,155 → **144,904（+749）**，其余三类 **各 +0**。
    #:   成因：`_unescape` 原是手写五个 `.replace()`，不认 `&#24213;` 这类数字字符引用
    #:   ⇒ `&#24213;&#31295;&#30446;&#24405;!A2`（= `底稿目录!A2`）压根不被识别成引用。
    #:   改用 `html.unescape` 后被正确识别。逐类归因实测确认 **+749 全部**来自含数字
    #:   字符引用的公式（2,941 条）⇒ 是「先前没看见」而不是「先前分错类」。
    "corpus_sheet_refs": 144904,
    "corpus_external_refs": 3883,
    "corpus_three_d_refs": 0,
    "corpus_no_target_refs": 179,
    "corpus_formulas": 126565,
    "corpus_templates": 351,
    #: chart 有真实样本（8 个部件 / `C24 会计分录 - 细节测试.xlsx`）；pivot 全库为 0。
    "corpus_chart_parts": 8,
    "corpus_pivot_parts": 0,
    #: definedNames 分类的**现口径**分母。与清册那组数的差异归因见
    #: `TestDefinedNameClassification.test_defined_name_five_way_classification`。
    "defined_name_classes": {
        "builtin_self_scope": 2465,
        "builtin_cross_sheet": 0,
        "user_self_scope": 267,
        "user_cross_sheet": 4,
        "global_scope": 197,
        "target_not_in_workbook": 6,
    },
}


def _scan(rel: str, target: str) -> N1.ReferenceScan:
    path = TEMPLATE_ROOT / rel
    if not path.is_file():  # pragma: no cover - 模板缺失时不冒充通过
        pytest.skip(f"权威模板不在磁盘上：{rel}")
    with zipfile.ZipFile(path) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        return N1.scan_reference_carriers(
            zf, target_sheet=target, sheet_parts=parts, defined_names=defined
        )


@pytest.fixture(scope="module")
def d2_scan() -> N1.ReferenceScan:
    return _scan(D2_REL, D2_SHEET)


@pytest.fixture(scope="module")
def k11_scan() -> N1.ReferenceScan:
    return _scan(K11_REL, K11_SHEET)


# ═══════════════════════════════════════════════════════════════════════════
# 地基判据 —— 扫描器与改写器全库同口径
# ═══════════════════════════════════════════════════════════════════════════


class TestScannerRewriterAgreement:
    """🔴 扫描与改写必须同口径，否则其余判据全部立不住。"""

    def test_scanner_agrees_with_rewriter_on_whole_corpus(self) -> None:
        """全库 351 份逐条公式：扫描器预期改动的 A1 片段数 == 改写器实际改动数。

        ═══ 这条抓到过什么 ═══

        首版按「去重行号数」对账，在 `'表'!E10:F10`（两个端点都是行 10）上 **12 处**
        不吻合 —— 暴露出 `PropagationEntry` 缺 `piece_count`：声明按引用处数、实测按 A1
        片段数，两个单位不同。若当时没做这条判据而直接接线，症状会是「与计划完全一致的
        传播被判漂移」，而那是最难查的一类假红。

        ═══ 为什么 `current_sheet` 传 None ═══

        传本 sheet 名时自限定引用（`'本表'!A1`）会走「自限定」分支而非传播分支，两侧口径
        就不可比了。这里要比的是**传播**分支。
        """
        total_formulas = 0
        compared = 0
        mismatched: list[str] = []
        kinds = {"sheet": 0, "three_d": 0, "external": 0, "no_target": 0}
        at = 7

        def remap(row: int) -> int:
            return row + 1 if row >= at else row

        files = sorted(
            p for p in TEMPLATE_ROOT.rglob("*.xlsx") if not p.name.startswith("~$")
        )
        assert len(files) == EXPECTED["corpus_templates"], (
            f"语料规模变了：{len(files)} 份，冻结值 {EXPECTED['corpus_templates']}"
        )

        for path in files:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
                sheets, _defined = _parse_workbook_xml(zf)
                for sheet in sheets:
                    part = _normalise_part(sheet["rel_target"])
                    if part not in names:
                        continue
                    xml = zf.read(part).decode("utf-8", "replace")
                    for fmatch in _F_RE.finditer(xml):
                        text = N1._unescape(fmatch.group("text") or "")
                        if not text:
                            continue
                        total_formulas += 1
                        refs = list(
                            iter_qualified_references(text, current_sheet=sheet["name"])
                        )
                        for ref in refs:
                            kinds[ref.kind] += 1

                        targets = frozenset(
                            r.sheet_name for r in refs if r.kind == "sheet"
                        )
                        if not targets:
                            continue

                        expected = 0
                        for ref in refs:
                            if ref.kind != "sheet" or not ref.token:
                                continue
                            for piece in ref.token.split(":"):
                                digits = "".join(c for c in piece if c.isdigit())
                                if digits and int(digits) >= at:
                                    expected += 1

                        _out, changed = _rewrite_formula_refs(
                            text, remap=remap, propagate_sheets=targets
                        )
                        _bare_out, bare = _rewrite_formula_refs(text, remap=remap)
                        if changed - bare == expected:
                            compared += 1
                        elif len(mismatched) < 8:
                            mismatched.append(
                                f"{path.name} / {sheet['name']}: {text[:70]!r} "
                                f"扫描器 {expected} vs 改写器 {changed - bare}"
                            )

        assert not mismatched, (
            f"扫描器与改写器口径漂移（{len(mismatched)} 例）：\n  "
            + "\n  ".join(mismatched)
            + "\n\n漂移的后果：声明传播量与实测对不上 ⇒ 与计划一致的传播被判漂移（假红）；"
            "更糟的是漏扫一类载体 ⇒ 那类引用静默指向错行"
        )
        assert compared > 70_000, f"实际比对的公式条数过少（{compared}），判据可能空转"
        assert total_formulas == EXPECTED["corpus_formulas"], (
            f"公式总数变了：{total_formulas}，冻结值 {EXPECTED['corpus_formulas']}"
        )
        for kind, frozen_key in (
            ("sheet", "corpus_sheet_refs"),
            ("external", "corpus_external_refs"),
            ("three_d", "corpus_three_d_refs"),
            ("no_target", "corpus_no_target_refs"),
        ):
            assert kinds[kind] == EXPECTED[frozen_key], (
                f"{kind} 类引用数变了：{kinds[kind]}，冻结值 {EXPECTED[frozen_key]}"
            )

    def test_three_d_is_empty_in_corpus_so_needs_injection(self) -> None:
        """🔴 分母声明：3D 引用全库实测 **0** 处 ⇒ 该分支判据必须用注入变体。

        本条存在的意义是把「这一类没有真实样本」写成可执行事实。若哪天语料里出现了真的
        3D 引用，本条会变红 —— 那时应该改用真实样本，而不是继续依赖注入。
        """
        assert EXPECTED["corpus_three_d_refs"] == 0
        # 注入变体：两种写法都必须被判成 three_d
        for text in (
            "=SUM(Sheet1:Sheet3!A20)",
            "=SUM('明细表K11-2:明细表K11-3'!F29)",
        ):
            refs = [r for r in iter_qualified_references(text)]
            assert refs, text
            assert all(r.kind == "three_d" for r in refs), [
                (r.kind, r.sheet_name) for r in refs
            ]


# ═══════════════════════════════════════════════════════════════════════════
# D2 —— 首要判据载体（Property 16 / 17）
# ═══════════════════════════════════════════════════════════════════════════


class TestD2PrimaryCarrier:
    """D2 上逐载体的实测处数被冻结成判据。"""

    def test_formula_carrier_count(self, d2_scan: N1.ReferenceScan) -> None:
        """`<f>` 是主载体 —— 42 处能定位到行号的引用。"""
        counts = d2_scan.counts_by_carrier()
        assert counts["formula"] == EXPECTED["d2_formula"], counts

    def test_defined_name_and_hyperlink_carriers(
        self, d2_scan: N1.ReferenceScan
    ) -> None:
        """definedNames 3 条 + hyperlink@location 1 条 —— 两类都是真实样本，非注入。

        definedNames 的三条是 `_FilterDatabase`（`$A$1:$AK$31`）、`Print_Area`
        （`$A$1:$AM$34`）、`Print_Titles`（`$2:$6` —— **整行区间**，无列标）。第三条正是
        Task 9 必须补 `_ROW_ONLY_PIECE_RE` 的原因：不补它这整类会被静默漏传播。
        """
        counts = d2_scan.counts_by_carrier()
        assert counts["defined_name"] == EXPECTED["d2_defined_name"], counts
        assert counts["hyperlink_location"] == EXPECTED["d2_hyperlink_location"], counts

        by_locator = {s.locator: s for s in d2_scan.sites if s.carrier == "defined_name"}
        assert set(by_locator) == {
            "_xlnm._FilterDatabase",
            "_xlnm.Print_Area",
            "_xlnm.Print_Titles",
        }, sorted(by_locator)
        # 整行区间形态必须被正确取到行号
        titles = by_locator["_xlnm.Print_Titles"]
        assert titles.reference.token == "$2:$6", titles.as_dict()
        assert titles.rows == (2, 6), titles.rows

    def test_prefix_without_coordinate_is_registered_not_skipped(
        self, d2_scan: N1.ReferenceScan
    ) -> None:
        """🔴 10 处 `'明细表D2-2'!#REF!` 必须**登记**，不得静默跳过（AC 4.3）。

        `_QUALIFIED_PREFIX_RE` 命中前缀但 `_REF_TOKEN_RE` 对 `#REF!` 返回 None ⇒ 传播器
        动不了它。传播器不动是对的，但扫描器静默跳过会让「有 10 处引用没被处理」这件事
        不可见 —— 而「不可见的漏改」正是本 spec 要消除的东西。
        """
        reasons = d2_scan.counts_by_reason()
        assert reasons["prefix_without_coordinate"] == (
            EXPECTED["d2_prefix_without_coordinate"]
        ), reasons
        registered = [
            c
            for c in d2_scan.unpropagated
            if c.reason == "prefix_without_coordinate"
        ]
        assert len(registered) == 1
        assert registered[0].count == 10
        assert D2_SHEET in registered[0].detail, registered[0].detail

    def test_reconciles_with_frozen_inventory(self, d2_scan: N1.ReferenceScan) -> None:
        """🔴 与清册（Wave 0 Task 24 产出）对账 —— 两条独立代码路径必须吻合。

        清册的 `referencing_sites` = 52 数的是「有多少处引用指向这张 sheet」，含取不到
        坐标的那 10 处。扫描器把它们分流到不传播登记，所以：

            formula(42) + prefix_without_coordinate(10) == 52

        两个口径都对、用途不同（清册量需求规模，扫描器定传播条目），但**必须能对上**——
        对不上说明其中一条路径的分词口径漂了。
        """
        import json

        inventory = json.loads(
            (_BACKEND / "data" / "workpaper_row_change_reachability.json").read_text(
                encoding="utf-8"
            )
        )
        managed = next(
            (
                m
                for e in inventory["contracted_entries"]
                for m in e["managed_sheets"]
                if m["excel_name"] == D2_SHEET
            ),
            None,
        )
        assert managed is not None, "清册里找不到 D2 的受管 sheet 登记"
        assert managed["referencing_sites"] == (
            EXPECTED["d2_inventory_referencing_sites"]
        ), managed

        counts = d2_scan.counts_by_carrier()
        reasons = d2_scan.counts_by_reason()
        assert (
            counts["formula"] + reasons["prefix_without_coordinate"]
            == managed["referencing_sites"]
        ), (
            f"与清册对不上：formula {counts['formula']} + "
            f"prefix_without_coordinate {reasons['prefix_without_coordinate']} != "
            f"清册 {managed['referencing_sites']}"
        )
        # 清册的 referenced_rows 只统计 `<f>` 侧 ⇒ 必须是扫描器 referenced_rows 的子集
        assert set(managed["referenced_rows"]) <= set(d2_scan.referenced_rows), (
            f"清册 {managed['referenced_rows']} 不是扫描 {d2_scan.referenced_rows} 的子集"
        )

    def test_referenced_rows_vs_covered_rows_are_different_questions(
        self, d2_scan: N1.ReferenceScan
    ) -> None:
        """🔴 `referenced_rows`（字面端点）与 `covered_rows`（区间展开）必须分开。

        D2 上 `Print_Area` 是 `$A$1:$AM$34` ⇒ 覆盖 34 行，而字面端点只有 `1` 和 `34`。

        混用两者会出错：
        * 用字面端点判「某行是否被引用到」⇒ 漏掉区间内部的行；
        * 用覆盖面当 `undeletable_rows` ⇒ 覆盖 34 行意味着几乎整表不可删，删行功能
          表现为「永远失败」。

        所以本类型只提供事实，「哪些行真的不可删」由 Wave 3 Task 16 裁决。
        """
        assert set(d2_scan.referenced_rows) <= set(d2_scan.covered_rows)
        assert len(d2_scan.covered_rows) > len(d2_scan.referenced_rows), (
            "覆盖面不大于字面端点集 ⇒ 语料里没有区间引用，本条空转"
        )
        assert 34 in d2_scan.referenced_rows
        assert 20 in d2_scan.covered_rows and 20 not in d2_scan.referenced_rows, (
            "行 20 落在 Print_Area 的 1..34 内部，应只出现在 covered_rows 里"
        )


# ═══════════════════════════════════════════════════════════════════════════
# K11 —— 结构判据载体（Property 9 的扫描侧前提）
# ═══════════════════════════════════════════════════════════════════════════


class TestDefinedNameClassification:
    """definedNames 五分类与 chart/pivot 规模（Task 12 收尾 / P16 / P34）。"""

    def test_defined_name_five_way_classification(self) -> None:
        """🔴 definedNames 分类的**现口径**分母。

        ═══ 口径定义（必须写死，否则判据锁在一个说不清的数上）═══

        对每个 `<definedName>` 的引用文本用 `iter_qualified_references` 分词，
        **只取 `kind == "sheet"`**（external / three_d / no_target 各归各类），
        再按 `scope`（`_parse_workbook_xml` 返回的字段，值是 sheet 名或 None）分六类。

        ═══ 🔴 为什么不沿用清册（Wave 0）那组数 ═══

        清册登记 `defined_name_cross=5002` / `target_not_in_workbook=2001` /
        `user_self_scope=292` / `user_cross_sheet=252`，与本口径实测
        （2,939 / 6 / 267 / 4）差距极大。**已定位归因，不是"口径说不清"**：

        清册生成器用的是它自己那份**历史**口径 `qualified_hits`，不认「带引号外部工作簿」
        （`'[31]已审利润纵向分析A1-13-4'!$E$27`）—— 那个盲区 Task 8 才修。实测历史口径在
        definedNames 上数出 **5,097** 条 `kind=sheet`，比现口径多 **2,158** 条，而那些
        现在被正确判成 `external`。于是清册的 `target_not_in_workbook=2001` 里绝大多数
        其实是**指向别的文件**的引用，被记成了「引用坏了」。

        ⇒ 本判据冻结**现口径**。清册那组数不动 —— 它是 Wave 0 的历史留痕，其生成器刻意
        保持历史口径以维持零回归基线分母的稳定（见 `iter_qualified_references` docstring）。
        """
        counts = dict.fromkeys(
            (
                "builtin_self_scope",
                "builtin_cross_sheet",
                "user_self_scope",
                "user_cross_sheet",
                "global_scope",
                "target_not_in_workbook",
            ),
            0,
        )
        for path in sorted(
            p for p in TEMPLATE_ROOT.rglob("*.xlsx") if not p.name.startswith("~$")
        ):
            with zipfile.ZipFile(path) as zf:
                sheets, defined = _parse_workbook_xml(zf)
                sheet_names = {s["name"] for s in sheets}
                for dn in defined:
                    ref = str(dn.get("ref") or "")
                    if not ref:
                        continue
                    is_builtin = str(dn.get("name") or "").startswith("_xlnm.")
                    scope = dn.get("scope")
                    for ref_hit in iter_qualified_references(N1._unescape(ref)):
                        if ref_hit.kind != "sheet":
                            continue
                        if ref_hit.sheet_name not in sheet_names:
                            key = "target_not_in_workbook"
                        elif not scope:
                            key = "global_scope"
                        elif ref_hit.sheet_name == scope:
                            key = (
                                "builtin_self_scope" if is_builtin else "user_self_scope"
                            )
                        else:
                            key = (
                                "builtin_cross_sheet"
                                if is_builtin
                                else "user_cross_sheet"
                            )
                        counts[key] += 1

        assert counts == EXPECTED["defined_name_classes"], (
            f"实测 {counts}\n冻结 {EXPECTED['defined_name_classes']}"
        )
        # 分母非空自检：三类主力都必须有量，否则判据在空集上恒真
        assert counts["builtin_self_scope"] > 2000, counts
        assert counts["user_self_scope"] > 100, counts
        assert counts["global_scope"] > 100, counts

    def test_chart_has_real_sample_while_pivot_needs_injection(self) -> None:
        """chart 有**真实样本**（8 个部件 / 1 份模板）；pivot 全库 **0** ⇒ 只能注入。

        把两者取证方式的差异写成判据，是为了不让「chart 也退化成注入」悄悄发生 ——
        有真实样本时用注入，等于放着真数据不验。
        """
        chart_parts = 0
        chart_templates: set[str] = set()
        pivot_parts = 0
        for path in sorted(
            p for p in TEMPLATE_ROOT.rglob("*.xlsx") if not p.name.startswith("~$")
        ):
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
            charts = [n for n in names if n.startswith("xl/charts/")]
            if charts:
                chart_parts += len(charts)
                chart_templates.add(path.name)
            pivot_parts += sum(
                1
                for n in names
                if n.startswith("xl/pivotCache/") or n.startswith("xl/pivotTables/")
            )

        assert chart_parts == EXPECTED["corpus_chart_parts"] == 8, chart_parts
        assert chart_templates == {"C24 会计分录 - 细节测试.xlsx"}, chart_templates
        assert pivot_parts == EXPECTED["corpus_pivot_parts"] == 0, (
            f"语料里出现了 {pivot_parts} 个 pivot 部件 ⇒ 那一类应改用真实样本，"
            "不再依赖注入变体"
        )


class TestK11StructuralCarrier:
    """K11 的 114 处引用覆盖受管区 19 行 —— 与清册 denominators 逐字对账。"""

    def test_formula_count_matches_inventory_denominator(
        self, k11_scan: N1.ReferenceScan
    ) -> None:
        import json

        inventory = json.loads(
            (_BACKEND / "data" / "workpaper_row_change_reachability.json").read_text(
                encoding="utf-8"
            )
        )
        denominators = inventory["denominators"]
        counts = k11_scan.counts_by_carrier()
        assert counts["formula"] == EXPECTED["k11_formula"] == (
            denominators["k11_managed_sheet_sites"]
        ), (counts, denominators)

    def test_referenced_rows_cover_managed_region(
        self, k11_scan: N1.ReferenceScan
    ) -> None:
        """受管区 `A7:N25` 的 19 行**全部**被引用到 —— 100% 阻断密度的实测来源。

        这条数是 AC 3.8 存在的理由：若删行只有 fail-closed 抛错，K11 上任何删行都必然
        失败。所以必须把拦的位置前移到 HTML 侧发起删行之前。
        """
        import json

        inventory = json.loads(
            (_BACKEND / "data" / "workpaper_row_change_reachability.json").read_text(
                encoding="utf-8"
            )
        )
        expected_rows = inventory["denominators"]["k11_managed_sheet_rows"]
        region = set(range(7, 26))
        hit = region & set(k11_scan.referenced_rows)
        assert len(hit) == expected_rows == 19, (
            f"受管区被引用行数 {len(hit)}，清册 {expected_rows}"
        )
        assert hit == region, f"未被引用的受管区行：{sorted(region - hit)}"


# ═══════════════════════════════════════════════════════════════════════════
# 载体词表边界（Property 18 / 19 / 20）
# ═══════════════════════════════════════════════════════════════════════════


class TestCarrierBoundaries:
    """哪些**不是**载体，以及未登记形态必须打红。"""

    def test_sqref_family_is_not_scanned(self) -> None:
        """🔴 `sqref` / `mergeCell@ref` / `hyperlink@ref` 结构性不含 sheet 前缀（AC 4.2）。

        Gate 2 全库实测 0/440、0/1223、0/37456、0/3950。本条用**注入**的方式取证扫描器
        真的不看它们：造一段带 `sqref="'别的表'!A1:B2"` 的 XML（Excel 不会产出这种，
        schema 也不允许），扫描器必须**不**把它算成载体。

        为什么用注入而不是真实样本：真实样本里这四类恒为 0，「扫不到」在空集上恒真。
        注入一个「若真去扫就会命中」的形态，才能证明扫描器确实没扫。
        """
        crafted = (
            '<worksheet><sheetData/>'
            '<conditionalFormatting sqref="\'明细表D2-2\'!A1:B2">'
            "<cfRule type=\"expression\" dxfId=\"0\" priority=\"1\">"
            "<formula>1=1</formula></cfRule></conditionalFormatting>"
            '<mergeCells><mergeCell ref="\'明细表D2-2\'!A1:B2"/></mergeCells>'
            '<hyperlinks><hyperlink ref="\'明细表D2-2\'!C3" display="x"/></hyperlinks>'
            '<dataValidations><dataValidation type="list" '
            'sqref="\'明细表D2-2\'!D4:D9" allowBlank="1">'
            "</dataValidation></dataValidations></worksheet>"
        )
        scan = self._scan_crafted(crafted, target=D2_SHEET)
        assert scan.sites == (), [s.as_dict() for s in scan.sites]
        assert scan.qualified_total == 0, (
            "扫描器碰了 sqref/merge/hyperlink@ref —— 那四类结构性不含 sheet 前缀，"
            "扫它们等于给「空集上恒真」留位置（AC 4.2）"
        )

    def test_data_validation_formula_content_is_scanned(self) -> None:
        """`dataValidation` 的 `<formula1>` 内容**是**载体（AC 4.6，真实样本存在）。

        真实样本：`B23-XX-5 职责分离 - 通用模板.xlsx` 的 `Data!$B$2:$B$3`。
        """
        crafted = (
            '<worksheet><sheetData/><dataValidations>'
            '<dataValidation type="list" sqref="D4:D9" allowBlank="1" '
            'error="您输入的科目不是报表标准科目" '
            'prompt="根据D2-2 审计调整前的账龄数据填写">'
            "<formula1>'明细表D2-2'!$B$2:$B$3</formula1>"
            "</dataValidation></dataValidations></worksheet>"
        )
        scan = self._scan_crafted(crafted, target=D2_SHEET)
        assert len(scan.sites) == 1, [s.as_dict() for s in scan.sites]
        site = scan.sites[0]
        assert site.carrier == "data_validation"
        assert site.reference.token == "$B$2:$B$3"
        assert site.locator == "D4:D9/formula1"

    def test_prompt_and_error_attributes_are_not_scanned(self) -> None:
        """🔴 `prompt=` / `error=` 属性里的文本**不得**被扫。

        实测事实（全库 351 份）：`error=` 48 处、`prompt=` 14 处含中文，其中被分词器判成
        限定引用的是 **0 处** —— `prompt=` 里确有「根据D2-2 审计调整前的账龄数据填写」这种
        含 sheet 名的提示，但其后没有 `!` 所以 `_QUALIFIED_PREFIX_RE` 不命中。

        ⚠ 所以「只扫子元素内容」在这一类上是**结构性预防**而非在修已发生的假阳性。本条
        用注入把「若扫了整个元素就会命中」的形态造出来：把提示文本改成带 `!` 的形态。
        """
        crafted = (
            '<worksheet><sheetData/><dataValidations>'
            '<dataValidation type="list" sqref="D4:D9" '
            "error=\"请从'明细表D2-2'!G7 名称列表中选择\" "
            "prompt=\"根据'明细表D2-2'!A13 填写\">"
            "<formula1>\"是,否\"</formula1>"
            "</dataValidation></dataValidations></worksheet>"
        )
        scan = self._scan_crafted(crafted, target=D2_SHEET)
        assert scan.sites == (), (
            "扫到了 prompt=/error= 属性里的文本 —— 那是给人看的提示，不是引用。"
            f"命中：{[s.as_dict() for s in scan.sites]}"
        )

    def test_string_literal_exclamation_is_not_a_reference(self) -> None:
        """🔴 字符串字面量里的**中文感叹号**不得被当成 sheet 前缀分隔符。

        这是**真实发生**的假阳性来源：`conditionalFormatting/formula` 全库 41 处含 `!` 的
        里有 **32 处**是 `"报表未调平!"` / `"调整事项未全部链入试算平衡表…!"` 这类中文提示，
        真跨 sheet 的只有 9 处。按 `!` 粗暴 grep 会把 32 处全算成跨 sheet 引用。

        挡住它的是分词器跳字符串字面量 —— 这就是「扫描必须走 `iter_qualified_references`、
        不得自己 grep」的实证理由。
        """
        for text in (
            '=IF(A1<>B1,"报表未调平!","")',
            '=IF(SUM(A:A)=0,"调整事项未全部链入试算平衡表，请检查调整科目是否为报表项目!",1)',
        ):
            refs = list(iter_qualified_references(text))
            assert refs == [], f"{text!r} 被判出限定引用 {[(r.kind, r.sheet_name) for r in refs]}"

    def test_conditional_format_formula_is_scanned(self) -> None:
        """`conditionalFormatting` 的 `<formula>` 内容**是**载体（AC 4.6）。"""
        crafted = (
            '<worksheet><sheetData/>'
            '<conditionalFormatting sqref="H7:M7">'
            '<cfRule type="expression" dxfId="0" priority="1">'
            "<formula>$H$7='明细表D2-2'!$B$3</formula>"
            "</cfRule></conditionalFormatting></worksheet>"
        )
        scan = self._scan_crafted(crafted, target=D2_SHEET)
        assert len(scan.sites) == 1, [s.as_dict() for s in scan.sites]
        assert scan.sites[0].carrier == "conditional_format"
        assert scan.sites[0].locator == "H7:M7/formula"

    def test_chart_and_pivot_parts_are_registered_unpropagated(self) -> None:
        """chart / pivot 部件登记为不传播（AC 4.3）。

        chart 有真实样本（全库 8 个部件 / 1 份模板）；pivot 全库 **0** 部件 ⇒ 注入。
        """
        scan = self._scan_crafted(
            "<worksheet><sheetData/></worksheet>",
            target=D2_SHEET,
            extra_parts={
                "xl/charts/chart1.xml": "<chartSpace/>",
                "xl/pivotTables/pivotTable1.xml": "<pivotTableDefinition/>",
                "xl/pivotCache/pivotCacheDefinition1.xml": "<pivotCacheDefinition/>",
            },
        )
        reasons = scan.counts_by_reason()
        assert reasons["chart"] == 1, reasons
        assert reasons["pivot"] == 2, reasons

    def test_external_workbook_is_registered_unpropagated(self) -> None:
        """外部工作簿登记不传播（AC 9.4）—— 真实样本 3,883 处。

        两种写法都造进来：不带引号的 `[1]底稿目录!`（全库 2,030 处形态）与带引号的
        `'[3]明细表H8-2'!`（134 处形态）。⚠ `[3]明细表H8-2!A33`（不带引号但名字含
        连字符）**不是** Excel 的合法写法 —— Excel 会给这种名字加引号。
        """
        crafted = (
            '<worksheet><sheetData><row r="1"><c r="A1">'
            "<f>[1]Sheet1!F29+'[3]明细表H8-2'!A33</f>"
            "</c></row></sheetData></worksheet>"
        )
        scan = self._scan_crafted(crafted, target=D2_SHEET)
        assert scan.counts_by_reason()["external_workbook"] == 2, scan.as_dict()
        assert scan.sites == ()

    @pytest.mark.parametrize(
        "text, want_kind",
        [
            # 不带引号 —— `book` 分组命中
            ("=[1]底稿目录!A2", "external"),
            ("=[1]Data!#REF!", "external"),
            # 🔴 带引号 —— `[n]` 落在引号内，`book` 分组**不**命中
            ("='[31]已审利润纵向分析A1-13-4'!$E$27", "external"),
            ("='[3]明细表H8-2'!A33:C33", "external"),
            # 3D 的两种写法
            ("=SUM(Sheet1:Sheet3!A20)", "three_d"),
            ("=SUM('明细表K11-2:明细表K11-3'!F29)", "three_d"),
            # 普通 sheet（分母对照 —— 否则上面几条在「全判 external」时也过）
            ("='明细表D2-2'!F13", "sheet"),
            ("=底稿目录!A2", "sheet"),
            ("='明细 表'!A20", "sheet"),
        ],
    )
    def test_quoted_book_and_3d_markers_inside_quotes_are_detected(
        self, text: str, want_kind: str
    ) -> None:
        """🔴 分隔标记落在**引号内**时仍须正确分类。

        ═══ 这条抓到过什么 ═══

        Task 8 实测：`'[31]已审利润纵向分析A1-13-4'!$E$27` 这种形态全库有
        **2,971 处 / 150 份模板**被误判成「本工作簿内的 sheet」。后果有两条：
        ① fill-down 下被平移（违反 AC 10.3 —— 外部工作簿的行与本簿无关）；
        ② 扫描时被误登记成 `target_not_in_workbook` 而不是 `external_workbook`，
        于是「有 2,971 处指向别的文件」这件事被记成了「有 2,971 处引用坏了」。

        与之前修掉的「带引号 3D」是**同一个成因**：Excel 对含标点的名字加引号，而分隔
        标记（3D 的 `:` / 外部簿的 `[n]`）落在引号内 ⇒ 正则的对应分组永不命中。修法也
        相同：剥引号**之后**再查一次标记。
        """
        refs = list(iter_qualified_references(text))
        assert refs, f"{text!r} 没分词出任何限定引用"
        assert all(r.kind == want_kind for r in refs), (
            f"{text!r} 期望全部判成 {want_kind}，实得 "
            f"{[(r.kind, r.sheet_name) for r in refs]}"
        )

    def test_quoted_external_workbook_is_not_propagated(self) -> None:
        """带引号外部工作簿在**传播**与 **fill-down** 两侧都必须逐字不动。

        分词判对了不等于改写也对 —— 本条直接验改写器的输出。
        """
        from app.services.workpaper_sync.excel_row_shift import translate_formula_rows

        text = "='[31]已审利润纵向分析A1-13-4'!$E$27+'[3]明细表H8-2'!A33"

        # 传播侧：把假 sheet 名放进 propagate_sheets 也不得生效
        out, changed = _rewrite_formula_refs(
            text,
            remap=lambda r: r + 1,
            propagate_sheets=frozenset(
                {"[31]已审利润纵向分析A1-13-4", "[3]明细表H8-2"}
            ),
        )
        assert out == text and changed == 0, f"传播侧被改动了：{out!r}"

        # fill-down 侧：AC 10.3
        assert translate_formula_rows(text, from_row=25, to_row=26) == text

    def test_target_not_in_workbook_is_registered(self) -> None:
        """目标 sheet 不在本工作簿内 —— 权威模板里**已坏**的引用，登记不传播。"""
        crafted = (
            '<worksheet><sheetData><row r="1"><c r="A1">'
            "<f>'压根不存在的表'!F29</f>"
            "</c></row></sheetData></worksheet>"
        )
        scan = self._scan_crafted(crafted, target=D2_SHEET)
        assert scan.counts_by_reason()["target_not_in_workbook"] == 1, scan.as_dict()

    def test_column_only_range_is_not_a_propagation_site(self) -> None:
        """整列区间 `$A:$C` 不含行号 ⇒ 不进传播候选（也不登记为不传播）。

        全库实测 66,059 处（VLOOKUP 惯用形态）。它不该进 sites（无行号可传播），也不该
        进不传播登记（登记它会让计数被无关项淹没 —— 6.6 万条）。
        """
        crafted = (
            '<worksheet><sheetData><row r="1"><c r="A1">'
            "<f>VLOOKUP(A1,'明细表D2-2'!$A:$C,3,0)</f>"
            "</c></row></sheetData></worksheet>"
        )
        scan = self._scan_crafted(crafted, target=D2_SHEET)
        assert scan.sites == (), [s.as_dict() for s in scan.sites]
        assert sum(scan.counts_by_reason().values()) == 0, scan.counts_by_reason()
        assert scan.qualified_total == 1, "整列区间仍应被分词器看到（只是不进任何清单）"

    @staticmethod
    def _scan_crafted(
        sheet_xml: str,
        *,
        target: str,
        extra_parts: dict[str, str] | None = None,
    ) -> N1.ReferenceScan:
        """把注入的 sheet XML 包成一份最小 xlsx 再扫。

        ⚠ 用 `io.BytesIO` 在内存里造，不落盘 —— 判据不产生临时文件。
        """
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
            for name, body in (extra_parts or {}).items():
                zf.writestr(name, body)
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as zf:
            return N1.scan_reference_carriers(
                zf,
                target_sheet=target,
                sheet_parts={target: "xl/worksheets/sheet1.xml"},
            )
