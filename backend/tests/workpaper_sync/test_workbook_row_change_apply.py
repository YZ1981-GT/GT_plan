# -*- coding: utf-8 -*-
"""Task 13 —— `apply_workbook_row_change`（插行分支）判据。

spec: excel-workbook-wide-row-change-propagation / Wave 2 Task 13
Requirements: 2.1, 4.4, 5.2, 5.4
Properties: **P21**（声明 == 实测）/ **P22**（部件变化面）/ **P31**（产物可打开）

═══ 本文件与 Task 10/11 的分工 ═══

Task 10/11 判**传播器的输出**（一条公式进、一条公式出）。本文件判**产物**：
真实 xlsx 进、真实 xlsx 出，逐部件核对谁变了、产物打不打得开、声明与实测对不对得上。

═══ 三条最要紧的判据 ═══

1. `test_only_declared_parts_change` —— 传播的作用面跨多张 sheet + workbook.xml，
   比插行大得多。「除声明部件外零字节变化」是唯一能拦住「顺手改了别的地方」的判据。
2. `test_self_qualified_reference_shifts_exactly_once` —— 受管 sheet 在 apply 里过**两遍**
   改写（`shift_sheet_rows` 再 `propagate_reference_side`）。自限定引用若两遍都动就是
   双重位移，产物仍能打开 ⇒ 静默错行两格。D2 上恰好没有这类引用，所以必须用注入取证。
3. `test_numeric_character_reference_sheet_names_are_propagated` —— 全库 **2,591 处**公式
   把 sheet 名写成 `&#24213;&#31295;&#30446;&#24405;`（6 份模板）。不还原实体就命中不到
   `target_sheet` ⇒ 那些引用被静默漏传播。
"""

from __future__ import annotations

import io
import os
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

TEMPLATE_ROOT = _BACKEND / "wp_templates"

D2_REL = "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
D2_SHEET = "明细表D2-2"
D2_AT, D2_COUNT, D2_STYLE_FROM = 13, 1, 12
D2_REGION = (11, 25)

#: D2 实测冻结值（apply 侧）。与 Task 8/12 的扫描侧分母同源但**单位不同**：
#: 这里是**A1 片段**数（与改写器 `changed` 同单位），扫描侧是**引用处**数。
D2_APPLY_EXPECTED: dict[str, int] = {
    "sites": 46,
    "entries": 44,          # 46 处里有 2 处一个片段都不动（Print_Titles / hyperlink A1）
    "formula_pieces": 60,
    "defined_name_pieces": 2,
    "changed_parts": 5,     # workbook.xml + 受管 sheet + 3 张引用侧 sheet
    "total_parts": 48,
}


def _load_d2() -> tuple[bytes, dict[str, str], N1.ReferenceScan]:
    path = TEMPLATE_ROOT / D2_REL
    if not path.is_file():  # pragma: no cover - 模板缺失时不冒充通过
        pytest.skip(f"D2 权威模板不在磁盘上：{D2_REL}")
    data = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        scan = N1.scan_reference_carriers(
            zf, target_sheet=D2_SHEET, sheet_parts=parts, defined_names=defined
        )
    return data, parts, scan


@pytest.fixture(scope="module")
def d2() -> tuple[bytes, dict[str, str], N1.ReferenceScan, N1.WorkbookRowChangePlan]:
    data, parts, scan = _load_d2()
    plan = N1.build_insert_plan(
        scan,
        managed_sheet_name=D2_SHEET,
        managed_sheet_part=parts[D2_SHEET],
        at=D2_AT,
        count=D2_COUNT,
        style_from=D2_STYLE_FROM,
        region_first_row=D2_REGION[0],
        region_last_row=D2_REGION[1],
    )
    return data, parts, scan, plan


@pytest.fixture(scope="module")
def d2_applied(
    d2: tuple[bytes, dict[str, str], N1.ReferenceScan, N1.WorkbookRowChangePlan],
) -> tuple[bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan]:
    data, parts, _scan, plan = d2
    produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
    return data, produced, report, plan


def _craft(
    managed_xml: str,
    *,
    referring_xml: str | None = None,
    workbook_xml: str | None = None,
    extra: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    """在内存里造一份最小 xlsx（不落盘）。返回 `(字节, sheet_parts)`。"""
    managed_part = "xl/worksheets/sheet1.xml"
    referring_part = "xl/worksheets/sheet2.xml"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(managed_part, managed_xml)
        if referring_xml is not None:
            zf.writestr(referring_part, referring_xml)
        zf.writestr(
            "xl/workbook.xml",
            workbook_xml
            or (
                '<?xml version="1.0" encoding="UTF-8"?><workbook><sheets>'
                '<sheet name="受管表" sheetId="1" r:id="rId1"/>'
                '<sheet name="引用表" sheetId="2" r:id="rId2"/>'
                "</sheets></workbook>"
            ),
        )
        for name, body in (extra or {}).items():
            zf.writestr(name, body)
    parts = {"受管表": managed_part}
    if referring_xml is not None:
        parts["引用表"] = referring_part
    return buffer.getvalue(), parts


#: OOXML worksheet 命名空间 —— **必须**带上，否则 openpyxl 把所有单元格读成 None。
#: （注入判据若只比对 XML 字节就发现不了这一点，而 `test_crafted_product_opens` 会红。）
_SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _managed_sheet(rows: str, *, dimension: str = "A1:C30") -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{_SHEET_NS}"><dimension ref="{dimension}"/>'
        f"<sheetData>{rows}</sheetData></worksheet>"
    )


def _apply_crafted(
    data: bytes,
    parts: dict[str, str],
    *,
    at: int = 13,
    count: int = 1,
    style_from: int = 12,
    region: tuple[int, int] = (11, 25),
) -> tuple[bytes, N1.PropagationReport, N1.WorkbookRowChangePlan]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        scan = N1.scan_reference_carriers(
            zf, target_sheet="受管表", sheet_parts=parts, defined_names=()
        )
    plan = N1.build_insert_plan(
        scan,
        managed_sheet_name="受管表",
        managed_sheet_part=parts["受管表"],
        at=at,
        count=count,
        style_from=style_from,
        region_first_row=region[0],
        region_last_row=region[1],
    )
    produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
    return produced, report, plan


def _text_of(data: bytes, part: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read(part).decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 1. 声明 == 实测（Property 21 / Requirement 5.2）
# ═══════════════════════════════════════════════════════════════════════════


class TestDeclarationMatchesMeasurement:
    """apply 的实测传播量必须等于计划的**声明**片段数。"""

    def test_d2_report_reconciles_with_plan(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """真实 D2 上逐载体对账 —— 不抛即通过。"""
        _before, _after, report, plan = d2_applied
        report.assert_matches_plan(plan)
        assert report.counts_by_carrier() == plan.propagation_piece_counts()

    def test_d2_frozen_denominators(
        self,
        d2: tuple[
            bytes, dict[str, str], N1.ReferenceScan, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """分母冻结：46 处扫到 → 44 条声明 → 60 + 2 个片段。

        🔴 **46 ≠ 44 不是漏了**：`Print_Titles`（`$2:$6`，整个区间在插入点之上）与
        `hyperlink@location` 的 `A1` 都是**一个片段都不动**，按定义不进传播清单
        （进了会让声明量虚高，对账必然失败）。
        """
        _data, _parts, scan, plan = d2
        assert len(scan.sites) == D2_APPLY_EXPECTED["sites"]
        assert len(plan.propagations) == D2_APPLY_EXPECTED["entries"]
        pieces = plan.propagation_piece_counts()
        assert pieces["formula"] == D2_APPLY_EXPECTED["formula_pieces"]
        assert pieces["defined_name"] == D2_APPLY_EXPECTED["defined_name_pieces"]

    def test_sites_excluded_from_entries_are_genuinely_static(
        self,
        d2: tuple[
            bytes, dict[str, str], N1.ReferenceScan, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """🔴 被排除的那 2 处必须**真的**一个片段都不动，不是被静默丢掉。

        判据形态：把每个未进清单的 site 单独跑一遍改写器，`changed` 必须为 0。
        没有这条，`build_propagation_entry` 里任何「返回 None」的 bug 都会表现为
        「声明少了但对账依然吻合」—— 因为实测那侧也少了。
        """
        from app.services.workpaper_sync.excel_row_shift import _rewrite_formula_refs

        _data, _parts, scan, plan = d2
        declared = {(e.part, e.locator) for e in plan.propagations}

        def remap(row: int) -> int:
            return row + D2_COUNT if row >= D2_AT else row

        excluded = [
            site
            for site in scan.sites
            if (site.part, f"{site.locator}#{site.reference.start}") not in declared
        ]
        assert len(excluded) == (
            D2_APPLY_EXPECTED["sites"] - D2_APPLY_EXPECTED["entries"]
        ), [s.as_dict() for s in excluded]
        for site in excluded:
            _out, changed = _rewrite_formula_refs(
                site.reference.raw,
                remap=remap,
                propagate_sheets=frozenset({D2_SHEET}),
                qualified_only=True,
            )
            assert changed == 0, (
                f"被排除的 site 其实会改动：{site.as_dict()} —— "
                "声明里少了它，而实测会改它 ⇒ 对账会失败（或更糟：两边都少，静默漏传播）"
            )

    def test_drift_is_detected_when_report_is_tampered(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """🔴 反向自检：把实测报告改一个数，对账必须报警。

        没有这条，上面那条在「`assert_matches_plan` 是空实现」时也会绿。
        """
        _before, _after, report, plan = d2_applied
        tampered = N1.PropagationReport(
            formulas_changed=report.formulas_changed - 1,
            defined_names_changed=report.defined_names_changed,
        )
        with pytest.raises(N1.PropagationDriftError) as excinfo:
            tampered.assert_matches_plan(plan)
        assert "formula" in str(excinfo.value)

    def test_apply_to_path_reconciles_before_replacing(self, tmp_path: Path) -> None:
        """落盘版在 `os.replace` **之前**对账 ⇒ 声明不符时零产物。"""
        data, parts = _craft(
            _managed_sheet(
                '<row r="12"><c r="A12"><v>1</v></c></row>'
                '<row r="20"><c r="A20"><v>2</v></c></row>'
            ),
            referring_xml=_managed_sheet(
                '<row r="5"><c r="A5"><f>\'受管表\'!A20</f></c></row>'
            ),
        )
        target = tmp_path / "book.xlsx"
        target.write_bytes(data)

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            scan = N1.scan_reference_carriers(
                zf, target_sheet="受管表", sheet_parts=parts, defined_names=()
            )
        plan = N1.build_insert_plan(
            scan,
            managed_sheet_name="受管表",
            managed_sheet_part=parts["受管表"],
            at=13,
            count=1,
            style_from=12,
            region_first_row=11,
            region_last_row=25,
        )
        report = N1.apply_workbook_row_change_to_path(
            target, plan, sheet_parts=parts
        )
        assert report.formulas_changed == 1
        assert "'受管表'!A21" in _text_of(target.read_bytes(), parts["引用表"])
        # 临时文件不得残留
        assert list(tmp_path.glob("*.tmp")) == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. 部件变化面（Property 22 / Requirement 5.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestOnlyDeclaredPartsChange:
    """🔴 传播不是「允许随便改」的通行证。

    上游 openpyxl 那版能长期在生产路径上丢 20 个部件、把 12 个共享公式组展平，就是因为
    没有任何判据在看「除了我要改的那几处，别的动了没有」。传播的作用面跨多张 sheet +
    workbook.xml，比插行大得多，所以这道判据更要紧。
    """

    def test_part_set_is_identical(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """部件集合**逐位**相等（顺序也不变）—— 少一个就是丢部件。"""
        before, after, _report, _plan = d2_applied
        with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
            io.BytesIO(after)
        ) as b:
            assert a.namelist() == b.namelist()
            assert len(a.namelist()) == D2_APPLY_EXPECTED["total_parts"]

    def test_only_declared_parts_change(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """字节变化的部件 ⊆ {受管 sheet} ∪ `touched_parts` ∪ {workbook.xml}。"""
        before, after, _report, plan = d2_applied
        allowed = (
            set(plan.touched_parts)
            | {plan.managed_sheet_part}
            | {N1.WORKBOOK_PART}
        )
        with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
            io.BytesIO(after)
        ) as b:
            changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
        assert changed, "一个部件都没变 ⇒ apply 什么都没做，判据空转"
        assert len(changed) == D2_APPLY_EXPECTED["changed_parts"], changed
        unexpected = sorted(set(changed) - allowed)
        assert not unexpected, (
            f"未声明的部件被改动：{unexpected}\n  声明可改：{sorted(allowed)}"
        )

    def test_managed_sheet_is_among_changed(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """分母对照：受管 sheet 必须在变化清单里 —— 否则插行根本没执行。"""
        before, after, _report, plan = d2_applied
        with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
            io.BytesIO(after)
        ) as b:
            assert a.read(plan.managed_sheet_part) != b.read(plan.managed_sheet_part)

    def test_unrelated_parts_are_byte_identical(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """无关部件（styles / sharedStrings / theme / rels）逐字节相等。

        单列出来是因为这几类最容易被全量重写路径悄悄改掉，而它们一变就意味着样式、
        共享字符串表或关系图被重排 —— 那是产物级损坏的典型前兆。
        """
        before, after, _report, _plan = d2_applied
        watched = (
            "xl/styles.xml",
            "xl/sharedStrings.xml",
            "xl/theme/theme1.xml",
            "xl/_rels/workbook.xml.rels",
            "[Content_Types].xml",
        )
        with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
            io.BytesIO(after)
        ) as b:
            names = set(a.namelist())
            checked = 0
            for name in watched:
                if name not in names:
                    continue
                assert a.read(name) == b.read(name), f"{name} 的字节被改动"
                checked += 1
        assert checked >= 3, f"只核到 {checked} 个无关部件，判据偏弱"

    def test_zipinfo_metadata_is_preserved(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """未改动部件的 `ZipInfo` 元数据也不变（`date_time` / `compress_type`）。

        让「除声明部件外一个字节都没动」这句话在 zip 元数据层面也成立 —— 否则
        mtime 全部轮转会让下游任何基于 zip 元数据的比对失效。
        """
        before, after, _report, plan = d2_applied
        changed_allowed = (
            set(plan.touched_parts)
            | {plan.managed_sheet_part}
            | {N1.WORKBOOK_PART}
        )
        with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
            io.BytesIO(after)
        ) as b:
            infos_before = {i.filename: i for i in a.infolist()}
            infos_after = {i.filename: i for i in b.infolist()}
            checked = 0
            for name, info in infos_before.items():
                clone = infos_after[name]
                assert clone.date_time == info.date_time, f"{name} 的 date_time 变了"
                assert clone.compress_type == info.compress_type, (
                    f"{name} 的 compress_type 变了"
                )
                if name not in changed_allowed:
                    checked += 1
        assert checked > 30, f"只核到 {checked} 个部件的元数据，判据偏弱"

    def test_repack_detector_fires_on_injected_part_mutation(self) -> None:
        """🔴 反向自检：偷偷改一个未声明部件，结构性自检必须抛。

        没有这条，上面那些判据在「`_assert_only_declared_parts_changed` 是空实现」时
        全都会绿。
        """
        data, parts = _craft(
            _managed_sheet('<row r="12"><c r="A12"><v>1</v></c></row>'),
            extra={"xl/styles.xml": "<styleSheet/>"},
        )
        tampered = N1._repack(data, {"xl/styles.xml": b"<styleSheet><!--x--/></styleSheet>"})
        with pytest.raises(N1.PropagationDriftError, match="未声明部件"):
            N1._assert_only_declared_parts_changed(
                data, tampered, allowed=frozenset({parts["受管表"]})
            )

    def test_part_set_change_detector_fires(self) -> None:
        """🔴 反向自检：部件集合变化必须抛（丢部件是最严重的产物损坏）。"""
        data, _parts = _craft(
            _managed_sheet('<row r="12"><c r="A12"><v>1</v></c></row>'),
            extra={"xl/styles.xml": "<styleSheet/>"},
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(
            buffer, "w"
        ) as out:
            for info in src.infolist():
                if info.filename == "xl/styles.xml":
                    continue  # 丢一个部件
                out.writestr(info, src.read(info.filename))
        with pytest.raises(N1.PropagationDriftError, match="部件集合变了"):
            N1._assert_only_declared_parts_changed(
                data, buffer.getvalue(), allowed=frozenset()
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 受管 sheet 过两遍改写 —— 不得双重位移
# ═══════════════════════════════════════════════════════════════════════════


class TestManagedSheetPassesThroughTwice:
    """🔴 受管 sheet 在 apply 里过**两遍**改写，自限定引用必须只位移一次。

    ═══ 风险从哪来 ═══

    `apply_workbook_row_change` 对受管 sheet 先跑 `shift_sheet_rows`（行重编号 + 裸引用
    位移），再跑 `propagate_reference_side`（限定引用传播）。自限定引用 `'受管表'!A20`
    写在受管表上、指向受管表自己 —— 它**同时**落在两遍的定义域边缘：

    * 若 `shift_sheet_rows` 已位移它（传了 `current_sheet` ⇒ 自限定按等价裸引用处理），
      第二遍再传播一次 ⇒ **双重位移**（A20 → A22），产物仍能打开 ⇒ 静默错行两格。

    实测结论：`shift_sheet_rows` **不传** `current_sheet`（默认 None）⇒ 自限定引用落进
    「其余」分支逐字不动，第二遍的传播正好补上，净效果位移一次。

    ⚠ **这是靠一个巧合成立的**，所以必须钉成判据：哪天有人给 `shift_sheet_rows` 补上
    `current_sheet`（看起来是"修正"），这里会当场变红。D2 上恰好没有自限定引用，
    只能用注入取证。
    """

    def test_self_qualified_reference_shifts_exactly_once(self) -> None:
        """自限定引用（`>= at`）位移**一次**：A20 → A21，不是 A22。"""
        data, parts = _craft(
            _managed_sheet(
                '<row r="12"><c r="A12" s="1"><v>1</v></c></row>'
                # 自限定 + 裸引用并列，两者都在 `>= at` 之上
                '<row r="20"><c r="A20" s="1"><f>\'受管表\'!A20+A20</f></c></row>'
            ),
            referring_xml=_managed_sheet(
                '<row r="5"><c r="A5"><f>\'受管表\'!A20</f></c></row>'
            ),
        )
        produced, report, plan = _apply_crafted(data, parts)
        managed_out = _text_of(produced, parts["受管表"])

        assert "'受管表'!A21" in managed_out, managed_out
        assert "'受管表'!A22" not in managed_out, (
            "自限定引用被**双重位移** —— `shift_sheet_rows` 与 "
            "`propagate_reference_side` 都动了它。产物仍能打开 ⇒ 静默错行两格"
        )
        report.assert_matches_plan(plan)

    def test_self_qualified_reference_below_insert_point_is_untouched(self) -> None:
        """自限定引用（`< at`）逐字不动 —— 两遍都不该碰它。"""
        data, parts = _craft(
            _managed_sheet(
                '<row r="12"><c r="A12" s="1"><v>1</v></c></row>'
                '<row r="20"><c r="A20" s="1"><f>\'受管表\'!A12+A12</f></c></row>'
            ),
            referring_xml=_managed_sheet(
                '<row r="5"><c r="A5"><f>\'受管表\'!A20</f></c></row>'
            ),
        )
        produced, _report, _plan = _apply_crafted(data, parts)
        managed_out = _text_of(produced, parts["受管表"])
        assert "'受管表'!A12" in managed_out, managed_out
        assert "'受管表'!A13" not in managed_out, "插入点之上的自限定引用被位移了"

    def test_shift_sheet_rows_does_not_pass_current_sheet(self) -> None:
        """🔴 把上面那个「巧合」钉成结构判据。

        用 AST 查 `shift_sheet_rows` 链路上给 `translate_formula_rows` /
        `_rewrite_formula_refs` 传的关键字实参里**有没有** `current_sheet`。

        若哪天有人补上它，本条会红并指向真正的问题：受管 sheet 会被双重位移，
        届时 apply 必须改成「受管 sheet 只跑 `shift_sheet_rows`，不再跑传播」。
        """
        import ast
        import inspect
        import textwrap

        from app.services.workpaper_sync import excel_row_shift as RS

        source = textwrap.dedent(inspect.getsource(RS.shift_sheet_rows))
        tree = ast.parse(source)
        passed: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in ("_rewrite_formula_refs", "translate_formula_rows", "_shift_formula"):
                passed |= {kw.arg for kw in node.keywords if kw.arg}
        assert "current_sheet" not in passed, (
            "`shift_sheet_rows` 现在给改写器传了 `current_sheet` ⇒ 自限定引用会被它位移，"
            "而 apply 之后还会再传播一次 ⇒ **双重位移**。"
            "修法：让 apply 对受管 sheet 只跑 `shift_sheet_rows`，不再跑 "
            "`propagate_reference_side`"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. XML 实体：数字字符引用形态的 sheet 名
# ═══════════════════════════════════════════════════════════════════════════


class TestNumericCharacterReferences:
    """🔴 全库 **2,591 处**公式把 sheet 名写成 `&#24213;&#31295;&#30446;&#24405;`。

    分布在 6 份模板（G4 / G5 / G6 / G7 / H1 / H10）。其中 **1,842 处**在不还原实体时
    取到的名字命中不到任何真实 sheet 名 ⇒ 与 `propagate_sheets` 比对必然失配 ⇒
    那些引用被**静默漏传播**。

    所以 apply 必须「还原 → 改写 → 重新转义」，而不是在转义后的文本上直接改。
    """

    def test_numeric_character_reference_sheet_names_are_propagated(self) -> None:
        """把 `受管表` 写成数字字符引用，传播仍须命中。"""
        encoded = "".join(f"&#{ord(ch)};" for ch in "受管表")
        data, parts = _craft(
            _managed_sheet('<row r="12"><c r="A12"><v>1</v></c></row>'),
            referring_xml=_managed_sheet(
                f'<row r="5"><c r="A5"><f>{encoded}!A20</f></c></row>'
            ),
        )
        produced, report, plan = _apply_crafted(data, parts)
        assert report.formulas_changed == 1, (
            "数字字符引用形态的 sheet 名没被命中 ⇒ 静默漏传播（全库 1,842 处）"
        )
        referring_out = _text_of(produced, parts["引用表"])
        assert "A21" in referring_out, referring_out
        report.assert_matches_plan(plan)

    def test_unchanged_formulas_keep_original_entity_bytes(self) -> None:
        """🔴 **没被改动**的公式必须保留原始实体字节，不得被"顺手规范化"。

        若无条件走「还原 → 重新转义」，那些没有任何改动的公式也会产生字节差异
        （`&#24213;` → `底`）⇒ 「除声明条目外零字节变化」这条判据会对一大批无关公式
        报警，把真正的越权改动淹掉。
        """
        encoded = "".join(f"&#{ord(ch)};" for ch in "别的表")
        target_encoded = "".join(f"&#{ord(ch)};" for ch in "受管表")
        data, parts = _craft(
            _managed_sheet('<row r="12"><c r="A12"><v>1</v></c></row>'),
            referring_xml=_managed_sheet(
                # 第一条会被改，第二条指向别的表 ⇒ 不该动，实体形态须保留
                f'<row r="5"><c r="A5"><f>{target_encoded}!A20</f></c>'
                f'<c r="B5"><f>{encoded}!A20</f></c></row>'
            ),
        )
        produced, report, _plan = _apply_crafted(data, parts)
        referring_out = _text_of(produced, parts["引用表"])
        assert report.formulas_changed == 1
        assert encoded in referring_out, (
            "未被改动的公式的实体字节被规范化了 —— 那会让零字节变化判据对无关公式报警"
        )

    def test_standard_entities_round_trip(self) -> None:
        """`&lt;` / `&gt;` / `&amp;` 在被改写的公式里必须正确往返。

        🔴 `&amp;` 是最容易错的：还原顺序不对会把 `&amp;quot;` 二次还原成 `"`，
        重新转义时就丢了一层。这里用 `IF(A1&lt;&gt;0,...)` 这类真实形态取证。
        """
        data, parts = _craft(
            _managed_sheet('<row r="12"><c r="A12"><v>1</v></c></row>'),
            referring_xml=_managed_sheet(
                '<row r="5"><c r="A5">'
                "<f>IF('受管表'!A20&lt;&gt;0,'受管表'!A20&amp;\"x\",0)</f>"
                "</c></row>"
            ),
        )
        produced, report, _plan = _apply_crafted(data, parts)
        referring_out = _text_of(produced, parts["引用表"])
        assert report.formulas_changed == 2, referring_out
        assert "&lt;&gt;" in referring_out, f"`<>` 的转义丢了：{referring_out}"
        assert "&amp;" in referring_out, f"`&` 的转义丢了：{referring_out}"
        assert "A21" in referring_out and "A20" not in referring_out, referring_out


# ═══════════════════════════════════════════════════════════════════════════
# 5. 产物可打开性（Property 31 的 apply 侧）
# ═══════════════════════════════════════════════════════════════════════════


class TestProducedWorkbookOpens:
    """产物必须能被真实 Excel 读取器加载。

    ⚠ 「能打开」是**必要不充分**条件 —— 静默错行的产物照样能打开。所以它只是最后一道
    兜底，不能替代前面的逐处比对与部件变化面判据。Wave 5 Task 25 会补真实 Excel COM
    的重算取证。
    """

    def test_openpyxl_loads_the_product(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
        tmp_path: Path,
    ) -> None:
        """openpyxl 真实加载 + 受管 sheet 的行数确实增加了。"""
        openpyxl = pytest.importorskip("openpyxl")
        before, after, _report, _plan = d2_applied

        out = tmp_path / "after.xlsx"
        out.write_bytes(after)
        src = tmp_path / "before.xlsx"
        src.write_bytes(before)

        wb_before = openpyxl.load_workbook(src)
        rows_before = wb_before[D2_SHEET].max_row
        names_before = list(wb_before.sheetnames)
        wb_before.close()

        wb_after = openpyxl.load_workbook(out)
        try:
            assert list(wb_after.sheetnames) == names_before, "sheet 集合变了"
            assert wb_after[D2_SHEET].max_row == rows_before + D2_COUNT, (
                f"受管 sheet 行数 {wb_after[D2_SHEET].max_row}，"
                f"期望 {rows_before + D2_COUNT}"
            )
        finally:
            wb_after.close()

    def test_propagated_formulas_are_readable_by_openpyxl(
        self,
        d2_applied: tuple[
            bytes, bytes, N1.PropagationReport, N1.WorkbookRowChangePlan
        ],
        tmp_path: Path,
    ) -> None:
        """🔴 抽查被传播的公式在 openpyxl 里读出来是**改后**的文本。

        直接读 XML 只能证明字节改了；经 openpyxl 解析一遍能证明改完仍是**合法公式**
        （形态坏掉时 openpyxl 会读成 None 或抛错）。
        """
        openpyxl = pytest.importorskip("openpyxl")
        _before, after, _report, plan = d2_applied

        out = tmp_path / "after.xlsx"
        out.write_bytes(after)
        wb = openpyxl.load_workbook(out)
        try:
            part_to_sheet = {}
            for name in wb.sheetnames:
                part_to_sheet[name] = wb[name]
            checked = 0
            for entry in plan.propagations:
                if entry.carrier != "formula":
                    continue
                locator = entry.locator.split("#")[0]
                for sheet in part_to_sheet.values():
                    try:
                        value = sheet[locator].value
                    except Exception:  # noqa: BLE001 - 坐标不在该 sheet 上
                        continue
                    if isinstance(value, str) and entry.ref_after in value:
                        checked += 1
                        break
            assert checked > 0, (
                "没有任何被传播的公式能在 openpyxl 里读出改后文本 —— "
                "要么公式形态坏了，要么 locator 对不上"
            )
        finally:
            wb.close()

    def test_crafted_product_opens(self) -> None:
        """注入用例的产物也要能打开 —— 否则前面那些注入判据只验了字节。"""
        openpyxl = pytest.importorskip("openpyxl")
        import tempfile

        data, parts = _craft(
            _managed_sheet(
                '<row r="12"><c r="A12" s="0"><v>1</v></c></row>'
                '<row r="20"><c r="A20" s="0"><f>\'受管表\'!A20+A20</f></c></row>',
                dimension="A1:C30",
            ),
            referring_xml=_managed_sheet(
                '<row r="5"><c r="A5"><f>\'受管表\'!A20</f></c></row>'
            ),
            extra={
                "[Content_Types].xml": (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    "</Types>"
                ),
                "_rels/.rels": (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                    "</Relationships>"
                ),
                "xl/_rels/workbook.xml.rels": (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
                    "</Relationships>"
                ),
            },
            workbook_xml=(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                "<sheets>"
                '<sheet name="受管表" sheetId="1" r:id="rId1"/>'
                '<sheet name="引用表" sheetId="2" r:id="rId2"/>'
                "</sheets></workbook>"
            ),
        )
        produced, _report, _plan = _apply_crafted(data, parts)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "crafted.xlsx"
            out.write_bytes(produced)
            wb = openpyxl.load_workbook(out)
            try:
                assert wb.sheetnames == ["受管表", "引用表"]
                assert wb["引用表"]["A5"].value == "='受管表'!A21"
            finally:
                wb.close()


# ═══════════════════════════════════════════════════════════════════════════
# 6. 边界与 fail-closed
# ═══════════════════════════════════════════════════════════════════════════


class TestApplyBoundaries:
    """kind 边界、part 缺失、以及「失败即零产物」。"""

    def test_delete_kind_is_now_implemented(self) -> None:
        """🔴 **本条在 Wave 3 翻转过。**

        Task 13 交付时 delete 分支未实现，这里钉的是「必须显式拒绝，不得静默当 insert
        处理」。Wave 3（Task 14~17）实现了 delete 之后，那条判据**必然变红** —— 这正是
        它该有的行为：它钉住的是「当时还没有的能力」，能力到位就该翻。

        翻转后钉的是新的事实：delete 计划走 `shrink_sheet_rows`（移除 + 上移），
        与 insert 的 `shift_sheet_rows`（造行 + 下移）是两条独立路径。
        """
        rows = "".join(
            f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>' for r in range(13, 26)
        )
        data, parts = _craft(_managed_sheet(rows))
        plan = N1.WorkbookRowChangePlan(
            kind=N1.RowChangeKind.DELETE,
            managed_sheet_name="受管表",
            managed_sheet_part=parts["受管表"],
            at=19,
            count=1,
            style_from=None,
            region_first_row=13,
            region_last_row=25,
            deleted_row_keys=("k19",),
        )
        produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
        managed_out = _text_of(produced, parts["受管表"])
        # 第 19 行被移除，其后行上移
        assert '<c r="A19"><v>20</v>' in managed_out, managed_out[:400]
        assert '<row r="25"' not in managed_out, "末行未随删行收缩"
        assert report.total_changed == 0, "本例没有引用侧条目"

    def test_missing_managed_part_is_refused(self) -> None:
        """受管 part 不在 zip 里 ⇒ fail closed（说明 part 是拼出来的）。"""
        data, parts = _craft(
            _managed_sheet('<row r="12"><c r="A12"><v>1</v></c></row>')
        )
        plan = N1.WorkbookRowChangePlan(
            kind=N1.RowChangeKind.INSERT,
            managed_sheet_name="受管表",
            managed_sheet_part="xl/worksheets/sheet99.xml",
            at=13,
            count=1,
            style_from=12,
            region_first_row=11,
            region_last_row=25,
        )
        with pytest.raises(N1.RowChangeOutOfRegionError, match="不在 zip 里"):
            N1.apply_workbook_row_change(data, plan, sheet_parts=parts)

    def test_input_bytes_are_not_mutated(
        self,
        d2: tuple[
            bytes, dict[str, str], N1.ReferenceScan, N1.WorkbookRowChangePlan
        ],
    ) -> None:
        """入参字节不被修改 —— 调用方可以安全复用它做前后比对。"""
        data, parts, _scan, plan = d2
        snapshot = bytes(data)
        N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
        assert data == snapshot, "入参 bytes 被修改了"

    def test_zero_propagation_still_shifts_managed_sheet(self) -> None:
        """没有任何引用侧条目时，受管 sheet 仍要插行（传播为空 ≠ 不用插行）。"""
        data, parts = _craft(
            _managed_sheet(
                '<row r="12"><c r="A12"><v>1</v></c></row>'
                '<row r="20"><c r="A20"><v>2</v></c></row>'
            )
        )
        produced, report, plan = _apply_crafted(data, parts)
        assert plan.propagations == ()
        assert report.total_changed == 0
        managed_out = _text_of(produced, parts["受管表"])
        assert '<row r="21"' in managed_out, managed_out
        report.assert_matches_plan(plan)

    def test_failure_leaves_target_untouched(self, tmp_path: Path) -> None:
        """🔴 落盘版失败时原文件完好无损，且不留临时文件。

        用一个必然对账失败的计划（篡改声明）触发失败路径。
        """
        data, parts = _craft(
            _managed_sheet('<row r="12"><c r="A12"><v>1</v></c></row>'),
            referring_xml=_managed_sheet(
                '<row r="5"><c r="A5"><f>\'受管表\'!A20</f></c></row>'
            ),
        )
        target = tmp_path / "book.xlsx"
        target.write_bytes(data)
        original = target.read_bytes()

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            scan = N1.scan_reference_carriers(
                zf, target_sheet="受管表", sheet_parts=parts, defined_names=()
            )
        good = N1.build_insert_plan(
            scan,
            managed_sheet_name="受管表",
            managed_sheet_part=parts["受管表"],
            at=13,
            count=1,
            style_from=12,
            region_first_row=11,
            region_last_row=25,
        )
        # 篡改：多声明一条 —— 实测必然对不上
        extra = N1.PropagationEntry(
            carrier="formula",
            part=parts["引用表"],
            locator="Z99#0",
            ref_before="'受管表'!A30",
            ref_after="'受管表'!A31",
            row_before=30,
            row_after=31,
        )
        tampered = N1.WorkbookRowChangePlan(
            kind=good.kind,
            managed_sheet_name=good.managed_sheet_name,
            managed_sheet_part=good.managed_sheet_part,
            at=good.at,
            count=good.count,
            style_from=good.style_from,
            region_first_row=good.region_first_row,
            region_last_row=good.region_last_row,
            propagations=good.propagations + (extra,),
            unpropagated=good.unpropagated,
        )
        with pytest.raises(N1.PropagationDriftError):
            N1.apply_workbook_row_change_to_path(
                target, tampered, sheet_parts=parts
            )
        assert target.read_bytes() == original, "失败后原文件被改动了"
        assert list(tmp_path.glob("*.tmp")) == [], "临时文件残留"
