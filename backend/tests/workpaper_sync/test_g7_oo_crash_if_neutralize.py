"""G7 `editor_error_-82` 裸 IF() 中性化 —— 生产函数的防御判据。

背景（真实缺陷，不是快照到期）：`adapters/excel.py` 的 `materialize` 与
`verify_unmanaged_regions` 两处都 import
`pilot_g7_two_level_dynamic.neutralize_oo_crash_if_formulas`，调用点随 commit
`82f58ea44` 上了线，**函数本体从未随任何 commit 落地**
（`git log -S "def neutralize_oo_crash_if_formulas" --all -- ":(glob)backend/**/*.py"`
零命中）⇒ HEAD 上 G7 整条 materialize/verify 路径带着 `ImportError` 在跑，
`test_task75_entry_adapter_roundtrip::TestRealRun` 就是被它打红的。

口径来源（已被真实 OO 栈验收）：`.kiro/specs/workpaper-html-onlyoffice-bidirectional-
writeback-closure/evidence/g4-1-g7-host-unified-path/README.md` §「本轮修复」第 2 条 ——
**zip 级剥离裸 `IF()` + 丢 `calcChain`；检测用 OOXML 词界 IF（忽略 SUMIF/COUNTIF）；
verify_unmanaged 对比前同样 neutralize**。
"""

from __future__ import annotations

import io
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from app.services.workpaper_sync.pilot_g7_two_level_dynamic import (
    _BARE_IF_CALL,
    _F_ELEMENT,
    _strip_bare_if_cells,
    authoritative_template_path,
    neutralize_oo_crash_if_formulas,
)

ADAPTER_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "workpaper_sync"
    / "adapters"
    / "excel.py"
)


def _bare_if_formula_count(data: bytes) -> int:
    """整册里还剩几个含词界 `IF(` 的 `<f>`。"""
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not (name.startswith("xl/worksheets/") and name.endswith(".xml")):
                continue
            xml = zf.read(name).decode("utf-8")
            for fm in _F_ELEMENT.finditer(xml):
                if _BARE_IF_CALL.search(fm.group("body") or ""):
                    total += 1
    return total


class TestCallerImportIsSatisfied:
    """两处生产调用点必须真的能 import 到它（这正是 task75 红的那条）。"""

    def test_both_call_sites_still_reference_this_symbol(self) -> None:
        source = ADAPTER_SOURCE.read_text(encoding="utf-8")
        assert source.count("neutralize_oo_crash_if_formulas") == 4, (
            "adapters/excel.py 的调用点数量变了 —— 若是刻意改接线，本判据要一起改"
        )

    def test_the_import_the_adapter_performs_resolves(self) -> None:
        # 逐字复刻 adapters/excel.py 的 import 形态（函数内延迟 import）。
        from app.services.workpaper_sync.pilot_g7_two_level_dynamic import (  # noqa: F401
            neutralize_oo_crash_if_formulas as _resolved,
        )

        assert callable(_resolved)


class TestWordBoundaryDetection:
    """检测必须是 OOXML 词界 IF —— SUMIF/COUNTIF/IFERROR 不能被牵连。"""

    @pytest.mark.parametrize(
        "formula,expect_dropped",
        [
            ("IF(A1=0,0,B1)", True),
            ("IF (A1=0,0,B1)", True),  # 函数名与括号间允许空白
            ("SUM(IF(A1&gt;0,1,0))", True),  # 嵌在里面的 IF 一样进 cIF
            ("IFERROR(IF(A1,1,2),0)", True),  # 内层裸 IF ⇒ 命中
            ("SUMIF(A:A,1,B:B)", False),
            ("COUNTIF(A:A,1)", False),
            ("AVERAGEIF(A:A,1,B:B)", False),
            ("IFERROR(VLOOKUP(A1,B:C,2,0),0)", False),
            ("IFS(A1=1,1,A1=2,2)", False),
            ("IFNA(VLOOKUP(A1,B:C,2,0),0)", False),
            ("_xlfn.IFS(A1=1,1)", False),
            ("SUM(A1:A9)", False),
        ],
    )
    def test_only_bare_if_is_dropped(self, formula: str, expect_dropped: bool) -> None:
        xml = f'<sheetData><row r="1"><c r="A1"><f>{formula}</f><v>7</v></c></row></sheetData>'
        new_xml, refs = _strip_bare_if_cells(xml)
        assert bool(refs) is expect_dropped, (formula, refs)
        if expect_dropped:
            assert "<f>" not in new_xml
            assert "<v>7</v>" in new_xml, "缓存值必须留着 —— 摘的是计算不是数"
            assert refs == ["A1"]
        else:
            assert new_xml == xml

    def test_shared_dependents_are_dropped_with_their_master(self) -> None:
        """主格命中 ⇒ 同 si 的从格一起摘，否则从格指向已消失的主格。"""
        xml = (
            '<sheetData><row r="1">'
            '<c r="A1"><f t="shared" ref="A1:A2" si="3">IF(B1=0,0,1)</f><v>0</v></c>'
            '<c r="A2"><f t="shared" si="3"/><v>1</v></c>'
            '<c r="A3"><f t="shared" si="9"/><v>2</v></c>'
            "</row></sheetData>"
        )
        new_xml, refs = _strip_bare_if_cells(xml)
        assert refs == ["A1", "A2"]
        assert 'si="3"' not in new_xml
        assert 'si="9"' in new_xml, "无关的共享组不得被牵连"


class TestOnTheRealAuthoritativeWorkbook:
    """在真实权威模板副本上跑 —— 不用合成 xlsx 糊过去。"""

    @pytest.fixture()
    def workbook_copy(self, tmp_path: Path) -> Path:
        source = authoritative_template_path()
        assert source.exists(), source
        target = tmp_path / "g7.g7-noif.xlsx"
        shutil.copy2(source, target)
        return target

    def test_every_bare_if_is_gone_and_parts_survive(self, workbook_copy: Path) -> None:
        before = workbook_copy.read_bytes()
        assert _bare_if_formula_count(before) > 0, "模板里本来就没有裸 IF，判据失去意义"

        neutralized = neutralize_oo_crash_if_formulas(workbook_copy)

        after = workbook_copy.read_bytes()
        assert _bare_if_formula_count(after) == 0
        assert len(neutralized) > 0
        with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
            io.BytesIO(after)
        ) as b:
            names_before = set(a.namelist())
            names_after = set(b.namelist())
        # 只允许丢 calcChain（本模板本来就没有）——其余部件一个都不许少。
        assert names_before - names_after <= {"xl/calcChain.xml"}
        assert names_after - names_before == set(), "不得凭空多出部件"

    def test_workbook_is_still_openable(self, workbook_copy: Path) -> None:
        neutralize_oo_crash_if_formulas(workbook_copy)
        openpyxl = pytest.importorskip("openpyxl")
        book = openpyxl.load_workbook(workbook_copy, data_only=False)
        try:
            assert len(book.sheetnames) == 22
        finally:
            book.close()

    def test_is_idempotent_to_the_byte(self, workbook_copy: Path) -> None:
        """第二遍必须 0 改动 —— verify 侧能用同一口径比 before/after 全靠这条。"""
        neutralize_oo_crash_if_formulas(workbook_copy)
        once = workbook_copy.read_bytes()
        again = neutralize_oo_crash_if_formulas(workbook_copy)
        assert again == ()
        assert workbook_copy.read_bytes() == once

    def test_calc_chain_and_its_references_are_dropped_together(
        self, tmp_path: Path, workbook_copy: Path
    ) -> None:
        """本模板没有 calcChain，就地造一个出来，验「丢部件 + 清悬空引用」。"""
        seeded = tmp_path / "seeded.xlsx"
        with zipfile.ZipFile(workbook_copy) as src, zipfile.ZipFile(
            seeded, "w"
        ) as out:
            for info in src.infolist():
                payload = src.read(info.filename)
                if info.filename == "[Content_Types].xml":
                    payload = payload.replace(
                        b"</Types>",
                        b'<Override PartName="/xl/calcChain.xml" ContentType='
                        b'"application/vnd.openxmlformats-officedocument.'
                        b'spreadsheetml.calcChain+xml"/></Types>',
                    )
                if info.filename == "xl/_rels/workbook.xml.rels":
                    payload = payload.replace(
                        b"</Relationships>",
                        b'<Relationship Id="rIdCalc" Type="http://schemas.'
                        b'openxmlformats.org/officeDocument/2006/relationships/'
                        b'calcChain" Target="calcChain.xml"/></Relationships>',
                    )
                out.writestr(info.filename, payload)
            out.writestr("xl/calcChain.xml", b'<calcChain><c r="A1" i="1"/></calcChain>')

        with zipfile.ZipFile(seeded) as zf:
            assert "xl/calcChain.xml" in zf.namelist()

        neutralize_oo_crash_if_formulas(seeded)

        with zipfile.ZipFile(seeded) as zf:
            assert "xl/calcChain.xml" not in zf.namelist()
            content_types = zf.read("[Content_Types].xml").decode("utf-8")
            rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        assert "calcChain" not in content_types, "悬空 Override 会让 Excel 报需要修复"
        assert not re.search(r'Target="calcChain\.xml"', rels)
