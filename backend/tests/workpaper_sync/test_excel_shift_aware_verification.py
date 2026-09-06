# -*- coding: utf-8 -*-
"""四类位移敏感结构进入 `managed_sheet_structure` 判据 + 它们在位移函数里被处理（T2）。

spec: excel-structural-row-insertion-and-shift-aware-verification / Wave 0 + Wave 1
Tasks: 2 / 2.1（verifier 侧）· 7（位移侧的空集补齐）
Properties: **P2** / **P9**

═══ 为什么必须用 zip 级注入变体 ═══════════════════════════════════════════

实测五个权威模板的受管 sheet（受管 sheet 逐个由 `_parse_workbook_xml` 定位，不按 sheet
号推）：

    模板  受管 sheet              part          dimension  hyperlinks  autoFilter  rowBreaks
    K11   审定表K11-1              sheet3.xml        1          1          0          0
    B60   B60-1工时预算与控制表      sheet2.xml        1          1          0          0
    D2    明细表D2-2               sheet8.xml        1          1          0          0
    H1    减少检查表H1-8            sheet12.xml       1          1          0          0
    G7    附注披露信息（国企）        sheet5.xml        1          0          0          0

⇒ `autoFilter` / `rowBreaks` **全库为 0**。拿真实模板直接验它们等于在空集上恒真；
手搓一个最小 xlsx 更糟（那份 sheet 连 mergeCells / 共享公式 / 跨 sheet 引用都没有，
本域几乎所有判据都会退化）。所以本文件的做法是**往真实权威模板里 zip 级注入合法变体**。

🔴 注入位置不能随手挑：`CT_Worksheet` 是**有序 sequence**。
K11 受管 sheet 实测顶层顺序为
`sheetPr → dimension → sheetViews → sheetFormatPr → cols → sheetData → mergeCells →
phoneticPr → hyperlinks → printOptions → pageMargins → pageSetup → headerFooter`。
按 schema：`autoFilter` 排在 `mergeCells` **之前**、`dataValidations` 与
`conditionalFormatting` 排在 `hyperlinks` **之前**、`rowBreaks` 排在 `headerFooter`
**之后**。插错位置产出的是非法变体，「真实模板的合法变体」这个要求就落空了。

═══ 判据形态 ═══════════════════════════════════════════════════════════════

每一类结构两条判据，缺一不可：

1. **正向**：改动/注入该结构一处 ⇒ `managed_sheet_structure` 的 digest 变化
   （端到端一条：`verify_unmanaged_regions` 的 `first_difference` 命中该 aspect）。
2. **反向自检**：把该 tag 从 `_SHEET_STRUCTURE_BLOCKS` 里摘掉 ⇒ 同一份变体的 digest
   必须**恢复相等**。这一条证明"打红"是那个 tag 带来的，而不是别的东西顺带变了 ——
   只有正向的话，任何让 digest 变化的原因都会让用例通过（tasks.md Task 2.1 明写要这条）。
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Callable, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_row_shift as RS  # noqa: E402
from app.services.workpaper_sync.adapters.base import SubstrateRole  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState  # noqa: E402

# 🔴 与 Task 37 共用同一份 fixture 构造件：抄第二份就会出现「verifier 在 A 形态上验过、
#    位移在 B 形态上验过」，而本文件的整个论点是两者看到**同一份**字节。
from test_task37_excel_extract import (  # noqa: E402
    BINDING,
    CONTRACT_ID,
    LAST_ROW,
    MANAGED_SHEET,
    SPEC,
    TEMPLATE,
    TEMPLATE_SHA,
    _read_entries,
    _sheet_part_of,
    _write_entries,
    business_cells,
    contract_payload,
    patch_cells,
)

#: 本 spec 往 `_SHEET_STRUCTURE_BLOCKS` 补入的四项（Requirement 1.3）。
NEW_BLOCKS: tuple[str, ...] = ("dimension", "hyperlinks", "autoFilter", "rowBreaks")
#: 补入前的原始六项 —— 分母断言用，防止有人顺手把清单削短。
LEGACY_BLOCKS: tuple[str, ...] = (
    "sheetPr",
    "cols",
    "mergeCells",
    "dataValidations",
    "conditionalFormatting",
    "sheetProtection",
)

#: K11 受管 sheet 上**真实存在**的结构块（实测 5 个）。
#:
#: 🔴 不能拿「原始六项的个数」当基线期望：清单里的十项在任一具体 sheet 上都可能缺席。
#: K11 实测只有 `sheetPr` / `cols` / `mergeCells`（原始六项里的三项）+ `dimension` /
#: `hyperlinks`（本 spec 补入的两项）—— `dataValidations` / `conditionalFormatting` /
#: `sheetProtection` / `autoFilter` / `rowBreaks` 五项都不在。
K11_PRESENT_BLOCKS: frozenset[str] = frozenset(
    {"sheetPr", "cols", "mergeCells", "dimension", "hyperlinks"}
)
EXPECTED_BASE_FOUND = len(K11_PRESENT_BLOCKS)  # 5

#: 实测：`autoFilter` / `rowBreaks` 在全部权威模板受管 sheet 上都是 0 ⇒ 必须注入。
ABSENT_IN_ALL_TEMPLATES: frozenset[str] = frozenset({"autoFilter", "rowBreaks"})
#: 实测：K11 受管 sheet 上真实存在，可直接改动验证。
PRESENT_IN_K11: frozenset[str] = frozenset({"dimension", "hyperlinks"})


# ═══════════════════════════════════════════════════════════════════════════
# 1. fixture：真实权威模板 → instrumented → 业务值
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def instrumented_bytes() -> bytes:
    gate = EI.ExcelIdentityCarrierGate.load()
    return EI.instrument_workbook_bytes(
        TEMPLATE.read_bytes(), SPEC, gate=gate
    ).instrumented_bytes


@pytest.fixture(scope="module")
def sheet_part(instrumented_bytes: bytes) -> str:
    return _sheet_part_of(instrumented_bytes, MANAGED_SHEET)


@pytest.fixture(scope="module")
def base_bytes(instrumented_bytes: bytes, sheet_part: str) -> bytes:
    return patch_cells(instrumented_bytes, sheet_part, business_cells())


@pytest.fixture(scope="module")
def base_sheet_xml(base_bytes: bytes, sheet_part: str) -> str:
    return _read_entries(base_bytes)[sheet_part].decode("utf-8")


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shift_aware")


@pytest.fixture(scope="module")
def base_path(base_bytes: bytes, workdir: Path) -> Path:
    path = workdir / "base.xlsx"
    path.write_bytes(base_bytes)
    return path


@pytest.fixture(scope="module")
def contract() -> object:
    return parse_contract(contract_payload(), adapter_id=CONTRACT_ID)


@pytest.fixture(scope="module")
def region(base_path: Path, contract: object) -> X.ManagedRegion:
    with zipfile.ZipFile(base_path) as zf:
        return X.resolve_managed_region(zf, contract=contract, binding=BINDING)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 2. zip 级注入：四类结构各一个「合法变体」构造器
# ═══════════════════════════════════════════════════════════════════════════
#
# 每个构造器接受受管 sheet 的 XML，返回改过的 XML。断言「真的改了」写在构造器里 ——
# 一个什么都没改的构造器会让本文件全部用例静默失效（digest 相等 ⇒ 判据反向）。


def _inject_before(xml: str, *, anchor: str, snippet: str) -> str:
    index = xml.find(anchor)
    assert index > 0, f"注入锚点 {anchor!r} 在受管 sheet 上找不到 —— 模板形态变了"
    return xml[:index] + snippet + xml[index:]


def variant_dimension(xml: str) -> str:
    """把 `dimension@ref` 的末列往右挪一列（真实存在，直接改）。"""
    found = re.search(r'<dimension ref="(?P<head>[A-Z]+\d+):(?P<col>[A-Z]+)(?P<row>\d+)"', xml)
    assert found is not None, "受管 sheet 没有 <dimension> —— 冻结事实已失效"
    widened = f'<dimension ref="{found.group("head")}:{found.group("col")}Z{found.group("row")}"'
    # `AZ37` 这种形态是合法列标；只改末列，行号不动 —— 与行位移无关的改动也必须被抓住
    out = xml[: found.start()] + widened.replace("Z", "") + xml[found.end() :]
    if out == xml:  # 上一步没改成 ⇒ 换成加宽末行
        out = xml.replace(found.group(0), widened, 1)
    assert out != xml, "dimension 变体没改动任何字节"
    return out


def variant_hyperlinks(xml: str) -> str:
    """改 `hyperlink@ref`（K11 实测有 1 个 `ref="J3"`）。"""
    found = re.search(r'(<hyperlink\b[^>]*?\bref=")(?P<ref>[A-Z]+\d+)(")', xml)
    assert found is not None, "受管 sheet 没有 <hyperlink> —— 冻结事实已失效"
    out = (
        xml[: found.start()]
        + found.group(1)
        + "J9"
        + found.group(3)
        + xml[found.end() :]
    )
    assert out != xml and found.group("ref") != "J9", "hyperlink 变体没改动任何字节"
    return out


def variant_autofilter(xml: str) -> str:
    """注入 `<autoFilter>` —— schema 上排在 `mergeCells` 之前。"""
    assert "<autoFilter" not in xml, (
        "受管 sheet 已经有 <autoFilter> —— 冻结事实变了，本变体不再是「注入」"
    )
    return _inject_before(
        xml, anchor="<mergeCells", snippet='<autoFilter ref="A7:N25"/>'
    )


def variant_rowbreaks(xml: str) -> str:
    """注入 `<rowBreaks>` —— schema 上排在 `headerFooter` 之后（即 `</worksheet>` 前）。"""
    assert "<rowBreaks" not in xml, (
        "受管 sheet 已经有 <rowBreaks> —— 冻结事实变了，本变体不再是「注入」"
    )
    return _inject_before(
        xml,
        anchor="</worksheet>",
        snippet=(
            '<rowBreaks count="2" manualBreakCount="2">'
            '<brk id="20" max="16383" man="1"/>'
            '<brk id="30" max="16383" man="1"/>'
            "</rowBreaks>"
        ),
    )


def variant_data_validations(xml: str) -> str:
    """注入 `<dataValidations>` —— schema 上排在 `hyperlinks` 之前。

    `sqref` 刻意用**两个空格分隔的区间**：`_shift_sqref` 逐区间处理这条分支在真实模板上
    根本不可达（K11 受管 sheet 一个 `dataValidation` 都没有）。
    """
    assert "<dataValidations" not in xml, "受管 sheet 已经有 <dataValidations>"
    return _inject_before(
        xml,
        anchor="<hyperlinks",
        snippet=(
            '<dataValidations count="1">'
            '<dataValidation type="list" allowBlank="1" sqref="D13:D24 F30:F31">'
            "<formula1>\"是,否\"</formula1>"
            "</dataValidation>"
            "</dataValidations>"
        ),
    )


def variant_conditional_formatting(xml: str) -> str:
    """注入 `<conditionalFormatting>` —— schema 上排在 `dataValidations` 之前。"""
    assert "<conditionalFormatting" not in xml, "受管 sheet 已经有 <conditionalFormatting>"
    return _inject_before(
        xml,
        anchor="<hyperlinks",
        snippet=(
            '<conditionalFormatting sqref="B7:B25 B30:B31">'
            '<cfRule type="cellIs" dxfId="0" priority="1" operator="lessThan">'
            "<formula>0</formula></cfRule>"
            "</conditionalFormatting>"
        ),
    )


#: tag → (变体构造器, 该 tag 是否需要注入)
VARIANTS: Mapping[str, Callable[[str], str]] = {
    "dimension": variant_dimension,
    "hyperlinks": variant_hyperlinks,
    "autoFilter": variant_autofilter,
    "rowBreaks": variant_rowbreaks,
}


def _replace_sheet(data: bytes, part: str, xml: str) -> bytes:
    entries = _read_entries(data)
    assert part in entries, part
    entries[part] = xml.encode("utf-8")
    return _write_entries(entries)


def _structure_digest(data: bytes, part: str) -> tuple[str, int]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return X._sheet_structure_digest(zf, part)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 冻结事实
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenFacts:
    def test_authority_template_is_untouched(self) -> None:
        assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA, (
            "跑完权威模板字节必须原样（Requirement 9.9：运行时只读）"
        )

    def test_structure_blocks_contain_both_the_legacy_six_and_the_new_four(self) -> None:
        blocks = X._SHEET_STRUCTURE_BLOCKS
        assert len(blocks) == 10, blocks
        assert len(set(blocks)) == 10, "清单里有重复项"
        for tag in LEGACY_BLOCKS:
            assert tag in blocks, f"原始清单项 {tag} 被删了"
        for tag in NEW_BLOCKS:
            assert tag in blocks, f"本 spec 应补入的 {tag} 不在清单里"

    def test_only_five_of_the_ten_blocks_exist_on_this_sheet(
        self, base_bytes: bytes, base_sheet_xml: str, sheet_part: str
    ) -> None:
        """基线覆盖数的来源写成显式判据 —— 「十项清单」≠「某张 sheet 上有十项」。

        首版拿「原始六项的个数」当基线下限，实测 5 < 6 直接打红。原因是
        `dataValidations` / `conditionalFormatting` / `sheetProtection` 在 K11 受管 sheet 上
        **一个都没有**。这条把真实存在集写死，让「哪几项需要注入变体」有据可查。
        """
        present = {tag for tag in X._SHEET_STRUCTURE_BLOCKS if f"<{tag}" in base_sheet_xml}
        assert present == K11_PRESENT_BLOCKS, sorted(present)
        _, found = _structure_digest(base_bytes, sheet_part)
        assert found == EXPECTED_BASE_FOUND == 5, found

    def test_managed_sheet_structure_is_a_real_aspect(self) -> None:
        assert "managed_sheet_structure" in X.UNMANAGED_ASPECTS
        assert X.UNMANAGED_ASPECTS[-1] == "other_parts", "catch-all 不在末位"

    @pytest.mark.parametrize("tag", sorted(ABSENT_IN_ALL_TEMPLATES))
    def test_absent_structures_really_are_absent(
        self, base_sheet_xml: str, tag: str
    ) -> None:
        """分母断言的反面：这两类真的不在真实模板上 ⇒ 必须注入才能非空验证。"""
        assert f"<{tag}" not in base_sheet_xml, (
            f"{tag} 已出现在受管 sheet 上 —— 冻结事实变了，"
            "本文件的注入变体不再是「注入」，Open Gate 2 的裁决需重新做"
        )

    @pytest.mark.parametrize("tag", sorted(PRESENT_IN_K11))
    def test_present_structures_really_are_present(
        self, base_sheet_xml: str, tag: str
    ) -> None:
        assert base_sheet_xml.count(f"<{tag}") == 1, (
            f"{tag} 在受管 sheet 上的计数不是 1，实得 {base_sheet_xml.count(f'<{tag}')}"
        )

    def test_toplevel_element_order_matches_the_injection_anchors(
        self, base_sheet_xml: str
    ) -> None:
        """注入锚点依赖的顺序事实：`mergeCells` < `hyperlinks` < `</worksheet>`。

        `CT_Worksheet` 是有序 sequence；锚点顺序一变，注入出来的就是非法变体，
        而 `ET.iterparse` 不校验顺序 ⇒ digest 判据照样"通过"。所以这条必须显式钉住。
        """
        merge = base_sheet_xml.find("<mergeCells")
        links = base_sheet_xml.find("<hyperlinks")
        close = base_sheet_xml.find("</worksheet>")
        assert 0 < merge < links < close, (merge, links, close)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 2：四类结构各自能红 + 反向自检
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2NewStructureBlocksCanTurnRed:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 2: `_SHEET_STRUCTURE_BLOCKS` 覆盖四类新结构且各自能红**

    **Validates: Requirements 1.3, 1.4**
    """

    @pytest.mark.parametrize("tag", sorted(VARIANTS))
    def test_changing_the_structure_changes_the_aspect_digest(
        self, base_bytes: bytes, base_sheet_xml: str, sheet_part: str, tag: str
    ) -> None:
        base_digest, base_found = _structure_digest(base_bytes, sheet_part)
        assert base_found == EXPECTED_BASE_FOUND, (
            f"基线数到 {base_found} 个结构块（期望 {EXPECTED_BASE_FOUND}）—— "
            f"K11 受管 sheet 实测存在的是 {sorted(K11_PRESENT_BLOCKS)}；"
            "计数变了说明模板形态或清单变了，本文件的注入变体设计需重新裁决"
        )

        variant = _replace_sheet(
            base_bytes, sheet_part, VARIANTS[tag](base_sheet_xml)
        )
        digest, found = _structure_digest(variant, sheet_part)
        assert digest != base_digest, (
            f"{tag} 改动后 `managed_sheet_structure` digest 不变 ⇒ 它没进检查面"
        )
        if tag in ABSENT_IN_ALL_TEMPLATES:
            assert found == base_found + 1, (tag, base_found, found)
        else:
            assert found == base_found, (tag, base_found, found)

    @pytest.mark.parametrize("tag", sorted(VARIANTS))
    def test_removing_the_tag_from_the_block_list_makes_it_green_again(
        self,
        base_bytes: bytes,
        base_sheet_xml: str,
        sheet_part: str,
        tag: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """反向自检：把该 tag 从 `_SHEET_STRUCTURE_BLOCKS` 摘掉 ⇒ 同一份变体必须恢复相等。

        只有正向判据时，**任何**让 digest 变化的原因都会让用例通过 —— 包括「注入顺手
        改动了别的结构」这种。这一条把「红是这个 tag 带来的」变成可 falsify 的判据。
        """
        trimmed = tuple(item for item in X._SHEET_STRUCTURE_BLOCKS if item != tag)
        assert len(trimmed) == len(X._SHEET_STRUCTURE_BLOCKS) - 1, tag
        monkeypatch.setattr(X, "_SHEET_STRUCTURE_BLOCKS", trimmed)

        variant = _replace_sheet(
            base_bytes, sheet_part, VARIANTS[tag](base_sheet_xml)
        )
        base_digest, _ = _structure_digest(base_bytes, sheet_part)
        digest, _ = _structure_digest(variant, sheet_part)
        assert digest == base_digest, (
            f"把 {tag} 从清单里摘掉后 digest 仍不同 ⇒ 变体顺手改了清单里的**别的**结构，"
            "正向判据的红不能归因到 {tag}"
        )

    def test_end_to_end_first_difference_points_at_managed_sheet_structure(
        self,
        base_bytes: bytes,
        base_sheet_xml: str,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        workdir: Path,
    ) -> None:
        """端到端：注入 `autoFilter` ⇒ `verify_unmanaged_regions` 的 `first_difference` 命中该 aspect。

        Property 2 的原话是「让 `managed_sheet_structure` aspect 打红」——
        只测 digest 函数不足以证明 aspect 名真的被报出来（aspect 名与 digest 的接线
        本身可能错，那类缺陷 digest 判据看不见）。
        """
        after = workdir / "with-autofilter.xlsx"
        after.write_bytes(
            _replace_sheet(base_bytes, sheet_part, variant_autofilter(base_sheet_xml))
        )

        same = X.verify_unmanaged_regions(
            before=base_path,
            after=base_path,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
        )
        assert same.equivalent is True, same.first_difference
        assert same.inspected_aspects == X.UNMANAGED_ASPECTS

        report = X.verify_unmanaged_regions(
            before=base_path,
            after=after,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
        )
        assert report.equivalent is False, "注入 autoFilter 后仍判等价"
        assert "managed_sheet_structure" in (report.first_difference or ""), (
            report.first_difference
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Task 7：位移函数处理这些结构（真实模板上是空集的那几类）
# ═══════════════════════════════════════════════════════════════════════════


class TestShiftHandlesInjectedRowBearingStructures:
    """`shift_sheet_rows` 阶段 C/D 的空集补齐。

    **Validates: Requirements 1.1, 3.8**

    `dataValidation@sqref` / `conditionalFormatting@sqref` / `autoFilter@ref` /
    `brk@id` 在 K11 受管 sheet 上**一个都没有**，于是它们的位移分支在真实模板上不可达
    —— 「分支不可达 = 判据永久空转」。本类用 zip 级注入变体把四条分支各走一次，并逐处
    比对位移前后的坐标。
    """

    #: 插入点与插入数：追加到受管区末尾（`LAST_ROW=25` ⇒ 插入点 26）。
    INSERT_AT = LAST_ROW + 1
    COUNT = 2

    def _plan(self) -> RS.RowShiftPlan:
        return RS.RowShiftPlan(
            insert_at=self.INSERT_AT, count=self.COUNT, style_from=LAST_ROW
        )

    def test_data_validation_sqref_shifts_every_region(self, base_sheet_xml: str) -> None:
        """`sqref` 含两个空格分隔的区间 ⇒ **逐区间**位移，不是只动第一个。"""
        xml = variant_data_validations(base_sheet_xml)
        assert 'sqref="D13:D24 F30:F31"' in xml

        after, report = RS.shift_sheet_rows(xml, self._plan())
        # D13:D24 全在插入点之上 ⇒ 不动；F30:F31 在插入点之下 ⇒ 各 +2
        assert 'sqref="D13:D24 F32:F33"' in after, re.search(
            r'sqref="[^"]*"', after
        )
        assert report.shifted_refs.get("dataValidation@sqref") == 1, report.as_dict()

    def test_conditional_formatting_sqref_shifts_every_region(
        self, base_sheet_xml: str
    ) -> None:
        xml = variant_conditional_formatting(base_sheet_xml)
        assert 'sqref="B7:B25 B30:B31"' in xml

        after, report = RS.shift_sheet_rows(xml, self._plan())
        assert 'sqref="B7:B25 B32:B33"' in after
        assert report.shifted_refs.get("conditionalFormatting@sqref") == 1, (
            report.as_dict()
        )

    def test_autofilter_ref_shifts(self, base_sheet_xml: str) -> None:
        """`autoFilter ref="A7:N25"` 末行恰是 `insert_at - 1` ⇒ 普通位移规则**不动**它。

        这不是缺陷而是刻意：`autoFilter` 的区间语义由用户设定，不由受管行区间决定；
        扩张它等于替审计师改筛选范围（design.md 拒绝方案第 8 条的同源理由）。
        本条把这个行为钉住 —— 若哪天要改成扩张，必须是有意的。
        """
        xml = variant_autofilter(base_sheet_xml)
        after, report = RS.shift_sheet_rows(xml, self._plan())
        assert 'ref="A7:N25"' in after, "autoFilter 被意外改动"
        assert report.shifted_refs.get("autoFilter@ref", 0) == 0, report.as_dict()

        # 反面：把 autoFilter 放到插入点**之下** ⇒ 必须整体位移
        below = xml.replace('<autoFilter ref="A7:N25"/>', '<autoFilter ref="A30:N35"/>', 1)
        assert below != xml
        after_below, report_below = RS.shift_sheet_rows(below, self._plan())
        assert 'ref="A32:N37"' in after_below, re.search(
            r'<autoFilter ref="[^"]+"', after_below
        )
        assert report_below.shifted_refs.get("autoFilter@ref") == 1, (
            report_below.as_dict()
        )

    def test_row_break_ids_shift(self, base_sheet_xml: str) -> None:
        """`<brk id>` 是**行号**（不是 A1 引用）：插入点之上不动、之下 +count。"""
        xml = variant_rowbreaks(base_sheet_xml)
        assert 'id="20"' in xml and 'id="30"' in xml

        after, report = RS.shift_sheet_rows(xml, self._plan())
        assert 'id="20"' in after, "插入点之上的分页符被误位移"
        assert 'id="32"' in after, re.findall(r'<brk id="\d+"', after)
        assert 'id="30"' not in after, "插入点之下的分页符没位移"
        assert report.shifted_refs.get("brk@id") == 1, report.as_dict()

    def test_hyperlink_below_the_insertion_point_shifts(
        self, base_sheet_xml: str
    ) -> None:
        """K11 真实的 `hyperlink ref="J3"` 在插入点之上 ⇒ 不动；挪到之下 ⇒ 必须位移。

        只用真实的 J3 验证时这条分支恒为「不动」，位移代码删掉也照样绿。
        """
        after, report = RS.shift_sheet_rows(base_sheet_xml, self._plan())
        assert 'ref="J3"' in after
        assert report.shifted_refs.get("hyperlink@ref", 0) == 0, report.as_dict()

        below = base_sheet_xml.replace('<hyperlink ref="J3"', '<hyperlink ref="J31"', 1)
        assert below != base_sheet_xml
        after_below, report_below = RS.shift_sheet_rows(below, self._plan())
        assert 'ref="J33"' in after_below, re.search(
            r'<hyperlink ref="[^"]+"', after_below
        )
        assert report_below.shifted_refs.get("hyperlink@ref") == 1, report_below.as_dict()

    def test_data_validation_formula1_range_shifts(self, base_sheet_xml: str) -> None:
        """`<formula1>` 的取值来源区间必须位移（全库实测 108 处带 A1 引用）。

        首版把 `formula1`/`formula2` 登记在 `_ROW_AGNOSTIC_TAGS`（= 声明它们不携带行号），
        于是位移后数据验证仍指向旧行 —— **静默错行**，产物照样能打开。
        """
        xml = _inject_before(
            base_sheet_xml,
            anchor="<hyperlinks",
            snippet=(
                '<dataValidations count="2">'
                '<dataValidation type="list" sqref="D13:D14">'
                "<formula1>$Q$8:$Q$20</formula1></dataValidation>"
                '<dataValidation type="list" sqref="D30:D31">'
                "<formula1>$Q$30:$Q$40</formula1></dataValidation>"
                "</dataValidations>"
            ),
        )
        after, report = RS.shift_sheet_rows(xml, self._plan())
        # 插入点之上（8..20）不动；之下（30..40）各 +2
        assert "<formula1>$Q$8:$Q$20</formula1>" in after, re.findall(
            r"<formula1>[^<]*</formula1>", after
        )
        assert "<formula1>$Q$32:$Q$42</formula1>" in after, re.findall(
            r"<formula1>[^<]*</formula1>", after
        )
        assert report.shifted_refs.get("formula1@text") == 1, report.as_dict()

    def test_conditional_formatting_rule_formula_shifts(
        self, base_sheet_xml: str
    ) -> None:
        """`<cfRule><formula>` 的表达式必须位移（全库实测 34 份模板 / 72 处带 A1 引用）。

        它在首版**两张清单里都没有** ⇒ `scan_unlisted_row_bearing_elements` 对那 34 份
        模板整体 fail closed，位移功能在它们上面根本不可用。
        """
        xml = _inject_before(
            base_sheet_xml,
            anchor="<hyperlinks",
            snippet=(
                '<conditionalFormatting sqref="B30:B31">'
                '<cfRule type="expression" dxfId="0" priority="1">'
                "<formula>$B30&lt;$C31</formula></cfRule>"
                "</conditionalFormatting>"
            ),
        )
        after, report = RS.shift_sheet_rows(xml, self._plan())
        assert "<formula>$B32&lt;$C33</formula>" in after, re.findall(
            r"<formula>[^<]*</formula>", after
        )
        assert 'sqref="B32:B33"' in after
        assert report.shifted_refs.get("formula@text") == 1, report.as_dict()

    def test_entity_escaped_string_literals_are_not_shifted(
        self, base_sheet_xml: str
    ) -> None:
        """`&quot;K30&quot;` 是**字符串**不是坐标 ⇒ 逐字不动；同一条里裸 `K30` 必须位移。

        实测形态来自权威模板：`<cfRule><formula>A8=&quot;&quot;</formula>`（WPS/Excel 把
        引号写成 XML 实体）。`&quot;` 后面紧跟的字符是 `;`，而 `;` 不在左边界黑名单里，
        所以只靠边界断言拦不住 —— 必须认实体形态的字面量。

        同一条用例里同时断言「字符串不动」与「裸引用要动」，两者缺一都会让判据退化成
        「什么都不改也通过」。
        """
        xml = _inject_before(
            base_sheet_xml,
            anchor="<hyperlinks",
            snippet=(
                '<conditionalFormatting sqref="B30:B31">'
                '<cfRule type="expression" dxfId="0" priority="1">'
                "<formula>IF($K30=&quot;K30&quot;,1,0)</formula></cfRule>"
                "</conditionalFormatting>"
            ),
        )
        after, _ = RS.shift_sheet_rows(xml, self._plan())
        got = re.search(r"<formula>(?P<text>[^<]*)</formula>", after)
        assert got is not None, after[-600:]
        text = got.group("text")
        assert text == "IF($K32=&quot;K30&quot;,1,0)", text
        """注入的四类结构都不得触发「清单外元素」fail closed。

        它们在 `ROW_BEARING_STRUCTURES` 或 `_ROW_AGNOSTIC_TAGS` 里都有登记；
        少登记一项的后果是位移函数在真实带这些结构的模板上整体不可用。
        """
        for builder in (
            variant_data_validations,
            variant_conditional_formatting,
            variant_autofilter,
            variant_rowbreaks,
        ):
            xml = builder(base_sheet_xml)
            unlisted = RS.scan_unlisted_row_bearing_elements(xml)
            assert unlisted == (), (builder.__name__, unlisted)

    def test_all_injected_structures_together(self, base_sheet_xml: str) -> None:
        """四类同时在场时一次位移全部处理到位 —— 逐 tag 的计数都必须非零。

        分开测时每条各自只走一条分支；合在一起才能发现「后一个注入把前一个的位移
        覆盖回去」这类顺序缺陷（`_shift_attr_everywhere` 是逐 tag 全文替换）。
        """
        xml = base_sheet_xml
        xml = variant_conditional_formatting(xml)
        xml = variant_data_validations(xml)
        xml = variant_autofilter(xml).replace(
            '<autoFilter ref="A7:N25"/>', '<autoFilter ref="A30:N35"/>', 1
        )
        xml = variant_rowbreaks(xml)

        after, report = RS.shift_sheet_rows(xml, self._plan())
        counts = dict(report.shifted_refs)
        for tag in (
            "mergeCell@ref",
            "dataValidation@sqref",
            "conditionalFormatting@sqref",
            "autoFilter@ref",
            "brk@id",
        ):
            assert counts.get(tag, 0) >= 1, (tag, counts)
        assert 'sqref="D13:D24 F32:F33"' in after
        assert 'sqref="B7:B25 B32:B33"' in after
        assert '<autoFilter ref="A32:N37"/>' in after
        assert 'id="32"' in after


# ═══════════════════════════════════════════════════════════════════════════
# 6. Wave 2：shift-aware 归一化（Task 9 / 10 / 10.1 / 11）
# ═══════════════════════════════════════════════════════════════════════════
#
# 判据形态：拿真实 K11 base artifact，用 `shift_sheet_rows` 造一份**按计划插行**的 after，
# 然后比对两种调用：
#
#   verify_unmanaged_regions(before, after)                  ⇒ 必须判**不等价**（位移就是漂移）
#   verify_unmanaged_regions(before, after, row_shift=plan)  ⇒ 必须判**等价**
#
# 两侧同时断言才有意义：只测后者时「归一化把整类检查关掉」也会通过。


def _shifted_artifact(
    base_bytes: bytes,
    sheet_part: str,
    plan: RS.RowShiftPlan,
    *,
    total_formula_rows: tuple[int, ...] = (),
    extra: Callable[[str], str] | None = None,
) -> bytes:
    """按 `plan` 对受管 sheet 做真实位移，产出 after 字节。

    `extra` 用于在位移**之后**再叠加一处与行位移无关的改动（Property 18 的五例）。
    """
    xml = _read_entries(base_bytes)[sheet_part].decode("utf-8")
    shifted, _ = RS.shift_sheet_rows(xml, plan, total_formula_rows=total_formula_rows)
    if extra is not None:
        shifted = extra(shifted)
    return _replace_sheet(base_bytes, sheet_part, shifted)


@pytest.fixture(scope="module")
def scan_and_definitions(base_bytes: bytes, base_path: Path, contract: object) -> tuple[object, object]:
    """真实 extract 出来的 `scan` —— `_managed_coordinates` 要用它定位受管行。"""
    from app.services.excel_structure_fingerprint import identity_inventory

    from test_task37_excel_extract import make_definitions

    inventory = identity_inventory(
        base_bytes,
        expected_table=BINDING.table_name,
        uuid_column_letter=BINDING.uuid_column,
    )
    definitions = make_definitions(contract, inventory)
    outcome = X.extract_projection(
        artifact=base_path,
        definitions=definitions,
        binding=BINDING,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )
    return outcome.scan, definitions


@pytest.fixture(scope="module")
def scan(scan_and_definitions: tuple[object, object]) -> object:
    return scan_and_definitions[0]


#: 追加插行：插入点 = 受管区末行 +1，样式来源 = 受管区末行。
PLAN_COUNT = 2

#: K11 真实合计行：`B26:G26` 是 `SUM(B7:B25)` 的共享公式主格。
#: 🔴 **不是** `test_task37.FOOTER_ROW`（=27，那是 footer **anchor** 的文本标签行，
#: B27..J27 上一处公式都没有）。首轮探针把 27 当合计行传进 `total_formula_rows`，
#: 于是扩张分支一处都没执行、看起来像"扩张没实现"。
TOTAL_ROW = 26


def _plan_for_region(region: X.ManagedRegion, *, count: int = PLAN_COUNT) -> RS.RowShiftPlan:
    return RS.RowShiftPlan(
        insert_at=region.last_row + 1, count=count, style_from=region.last_row
    )


def _verify(
    before: Path,
    after: Path,
    *,
    contract: object,
    region: X.ManagedRegion,
    scan: object,
    row_shift: RS.RowShiftPlan | None = None,
) -> object:
    return X.verify_unmanaged_regions(
        before=before,
        after=after,
        contract=contract,  # type: ignore[arg-type]
        region=region,
        binding=BINDING,
        scan=scan,  # type: ignore[arg-type]
        row_shift=row_shift,
    )


class TestNormalizationTablesAreDerivedNotHandwritten:
    """归一化用的三张表由 `ROW_BEARING_STRUCTURES` **派生**，不是在 verifier 侧手抄第二份。

    **Validates: Requirements 6.3**

    手抄第二份的后果有两个方向，都很贵：漏一项 ⇒ 那类结构的位移不被归一化 ⇒ 与计划一致的
    插行判成漂移（假红）；多一项 ⇒ 真实漂移被抹平（假绿）。
    """

    def test_every_listed_structure_lands_in_exactly_one_bucket(self) -> None:
        result = RS.assert_structure_normalization_covers_structures()
        total = (
            len(result["a1_attrs"])
            + len(result["bare_row_attrs"])
            + len(result["text_tags"])
            + len(result["delegated"])
        )
        assert total == len(RS.ROW_BEARING_STRUCTURES) == 15, (total, result)
        assert set(result["a1_attrs"]) == {
            "autoFilter@ref",
            "conditionalFormatting@sqref",
            "dataValidation@sqref",
            "dimension@ref",
            "hyperlink@ref",
            "mergeCell@ref",
        }, sorted(result["a1_attrs"])
        assert set(result["bare_row_attrs"]) == {"brk@id"}, result["bare_row_attrs"]
        assert set(result["text_tags"]) == {"formula", "formula1", "formula2"}, result[
            "text_tags"
        ]

    def test_an_unbucketed_structure_fails_closed(self) -> None:
        """反向自检：往清单里加一项而不给它归一化桶 ⇒ 派生自检必须打红。"""
        original = RS.ROW_BEARING_STRUCTURES
        try:
            RS.ROW_BEARING_STRUCTURES = original + (("pivotArea", "@ref"),)  # type: ignore[misc]
            with pytest.raises(RS.UnlistedRowBearingStructureError, match="归一化桶"):
                RS.assert_structure_normalization_covers_structures()
        finally:
            RS.ROW_BEARING_STRUCTURES = original  # type: ignore[misc]
        RS.assert_structure_normalization_covers_structures()

    def test_verifier_does_not_hardcode_a_second_structure_list(self) -> None:
        """`excel_extract` 里不得出现第二份「哪些属性携带行号」的手写清单。

        判据落在**对象身份**上：verifier 用的三张表必须与 `excel_row_shift` 的**同一个对象**，
        不是「内容恰好相等的另一份」。内容相等型判据挡不住「有人抄了一份、两份暂时还一样」。
        """
        assert X.STRUCTURE_ROW_BEARING_ATTRS is RS.STRUCTURE_ROW_BEARING_ATTRS
        assert X.STRUCTURE_BARE_ROW_ATTRS is RS.STRUCTURE_BARE_ROW_ATTRS
        assert X.STRUCTURE_ROW_BEARING_TEXT_TAGS is RS.STRUCTURE_ROW_BEARING_TEXT_TAGS


class TestProperty19NormalizationTouchesNoBytes:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 19: 归一化不改动任何 artifact 字节**

    **Validates: Requirements 6.7**
    """

    def test_digest_with_row_shift_does_not_write_to_the_artifact(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        plan = _plan_for_region(region)
        after = workdir / "p19-after.xlsx"
        after.write_bytes(_shifted_artifact(base_bytes, sheet_part, plan))

        before_sha = hashlib.sha256(base_path.read_bytes()).hexdigest()
        after_sha = hashlib.sha256(after.read_bytes()).hexdigest()
        assert before_sha != after_sha, "位移产物与 base 相同 ⇒ 位移根本没发生，判据会空转"

        for _ in range(2):
            X.unmanaged_region_digest(
                after,
                contract=contract,  # type: ignore[arg-type]
                region=region,
                binding=BINDING,
                scan=scan,  # type: ignore[arg-type]
                row_shift=plan,
            )
            _verify(
                base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
            )

        assert hashlib.sha256(base_path.read_bytes()).hexdigest() == before_sha
        assert hashlib.sha256(after.read_bytes()).hexdigest() == after_sha

    def test_repeated_digest_is_stable(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """同一份字节两次归一化 digest 必须相同（否则 verifier 会随机假红）。"""
        plan = _plan_for_region(region)
        after = workdir / "p19-stable.xlsx"
        after.write_bytes(_shifted_artifact(base_bytes, sheet_part, plan))
        first = X.unmanaged_region_digest(
            after,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
            row_shift=plan,
        )
        second = X.unmanaged_region_digest(
            after,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
            row_shift=plan,
        )
        assert first.aspects == second.aspects
        assert first.digest == second.digest


class TestProperty3ZeroShiftPathIsUnchanged:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 3: 位移计划为空时行为与本 spec 之前逐字节相同**

    **Validates: Requirements 2.3, 6.4**

    这是「加法而非行为翻转」的判据：`row_shift=None` 与**根本不传**该参数必须产出逐字节
    相同的 digest。它必须先绿，才有资格谈归一化。
    """

    def test_omitting_the_parameter_equals_passing_none(
        self,
        base_path: Path,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
    ) -> None:
        without = X.unmanaged_region_digest(
            base_path,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
        )
        explicit_none = X.unmanaged_region_digest(
            base_path,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
            row_shift=None,
        )
        assert without.aspects == explicit_none.aspects
        assert without.coverage == explicit_none.coverage
        assert without.digest == explicit_none.digest

    def test_identical_bytes_still_compare_equal_without_a_plan(
        self,
        base_path: Path,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
    ) -> None:
        report = _verify(base_path, base_path, contract=contract, region=region, scan=scan)
        assert report.equivalent is True, report.first_difference
        assert report.inspected_aspects == X.UNMANAGED_ASPECTS
        coverage = dict(report.details["coverage"])
        # 🔴 分母断言：**八个 aspect 全部 > 0**。空集恒等价不算通过 —— 手搓的最小 xlsx 上
        #    「未管理区域」是空集，`equivalent` 恒真，本文件几乎所有判据都会退化。
        #    实测这份 instrumented K11 上八项都非空（含 `shared_strings_prefix`：
        #    instrumentation 与 `patch_cells` 写入的文本进了 sharedStrings）。
        zero = sorted(name for name, count in coverage.items() if count <= 0)
        assert zero == [], coverage
        assert set(coverage) == set(X.UNMANAGED_ASPECTS), sorted(coverage)
        assert coverage["managed_sheet_unmanaged_cells"] > 0, coverage
        assert coverage["managed_sheet_structure"] == EXPECTED_BASE_FOUND, coverage


class TestProperty17PlannedInsertionIsEquivalent:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 17: 与计划一致的插行使全部 aspect 判等价**

    **Validates: Requirements 6.1, 6.2, 6.3, 6.5**
    """

    def test_planned_insertion_is_drift_without_the_plan_and_equivalent_with_it(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        plan = _plan_for_region(region)
        after = workdir / "p17-after.xlsx"
        after.write_bytes(_shifted_artifact(base_bytes, sheet_part, plan))

        # (1) 不给计划 ⇒ 位移就是漂移。这一半必须先成立，否则下一半证明不了任何事。
        naive = _verify(
            base_path, after, contract=contract, region=region, scan=scan
        )
        assert naive.equivalent is False, "插行在无计划时被判等价 ⇒ 判据本来就是空的"
        assert "managed_sheet" in (naive.first_difference or ""), naive.first_difference

        # (2) 给计划 ⇒ 全部 aspect 判等价
        aware = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert aware.equivalent is True, aware.first_difference
        assert aware.inspected_aspects == X.UNMANAGED_ASPECTS

    @pytest.mark.parametrize("count", [1, 2, 5])
    def test_equivalence_holds_for_several_insertion_counts(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
        count: int,
    ) -> None:
        plan = _plan_for_region(region, count=count)
        after = workdir / f"p17-count-{count}.xlsx"
        after.write_bytes(_shifted_artifact(base_bytes, sheet_part, plan))
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is True, (count, report.first_difference)

    def test_inserted_rows_are_excluded_from_the_unmanaged_set(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """Requirement 6.5：新插入行的格不进非受管集合 ⇒ 覆盖计数不因插行而增加。

        它们的 `unshift` 是**恒等映射**，进了集合就会与 before 侧同号的原始行别名。
        """
        plan = _plan_for_region(region)
        after = workdir / "p17-coverage.xlsx"
        after.write_bytes(_shifted_artifact(base_bytes, sheet_part, plan))

        base_digest = X.unmanaged_region_digest(
            base_path,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
        )
        aware = X.unmanaged_region_digest(
            after,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
            row_shift=plan,
        )
        naive = X.unmanaged_region_digest(
            after,
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
        )
        cells = "managed_sheet_unmanaged_cells"
        assert aware.coverage[cells] == base_digest.coverage[cells], (
            f"归一化后非受管格数 {aware.coverage[cells]} ≠ 基线 "
            f"{base_digest.coverage[cells]} —— 新插入行没被排除（Requirement 6.5）"
        )
        assert naive.coverage[cells] > base_digest.coverage[cells], (
            "不归一化时非受管格数没增加 ⇒ 新插入行根本没造出格来，本条判据空转"
        )


class TestProperty18NormalizationDoesNotLoosenUnrelatedJudgements:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 18: 归一化不放宽与行位移无关的判据**

    **Validates: Requirements 6.6, 6.8**

    五例全部叠加在**已按计划位移**的 after 之上 —— 也就是说，归一化把位移那部分抹平之后，
    剩下的这一处改动仍必须让 verifier 判不等价。只在未位移的 artifact 上测这五例证明不了
    「归一化没放宽」，因为那时归一化根本没被激活。
    """

    def _drifted(
        self,
        base_bytes: bytes,
        sheet_part: str,
        plan: RS.RowShiftPlan,
        workdir: Path,
        name: str,
        *,
        mutate_sheet: Callable[[str], str] | None = None,
        mutate_entries: Callable[[dict[str, bytes]], dict[str, bytes]] | None = None,
    ) -> Path:
        data = _shifted_artifact(base_bytes, sheet_part, plan, extra=mutate_sheet)
        if mutate_entries is not None:
            entries = dict(_read_entries(data))
            data = _write_entries(mutate_entries(entries))
        path = workdir / name
        path.write_bytes(data)
        return path

    def test_changing_an_unmanaged_cell_value_still_drifts(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """改**非受管格的 `v`** —— 归一化只动行号，救不了值。"""
        plan = _plan_for_region(region)

        def _mutate(xml: str) -> str:
            # A31（位移后）是受管区之下的文本标签格，肯定非受管
            found = re.search(r'(<c r="A31"[^>]*><v>)(\d+)(</v>)', xml)
            assert found is not None, "定位不到用于改值的非受管格 —— fixture 形态变了"
            return xml[: found.start()] + found.group(1) + "99999" + found.group(3) + xml[found.end() :]

        after = self._drifted(
            base_bytes, sheet_part, plan, workdir, "p18-value.xlsx", mutate_sheet=_mutate
        )
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, "改了非受管格的值仍判等价 ⇒ 归一化放宽了判据"
        assert "managed_sheet_unmanaged_cells" in (report.first_difference or ""), (
            report.first_difference
        )

    def test_changing_an_unmanaged_cell_style_still_drifts(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """改**非受管格的 `s`**。"""
        plan = _plan_for_region(region)

        def _mutate(xml: str) -> str:
            found = re.search(r'<c r="A31"([^>]*)s="(\d+)"', xml)
            assert found is not None, "定位不到带样式的非受管格"
            return (
                xml[: found.start()]
                + f'<c r="A31"{found.group(1)}s="7"'
                + xml[found.end() :]
            )

        after = self._drifted(
            base_bytes, sheet_part, plan, workdir, "p18-style.xlsx", mutate_sheet=_mutate
        )
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, "改了非受管格的样式仍判等价"

    def test_changing_an_unmanaged_formula_column_still_drifts(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """把非受管公式的**列标**改掉 —— 归一化只动行号，列变了必须仍判漂移。

        这一例最能说明「归一化不是放宽」：`C28-C29` 与 `D28-D29` 归一化后分别是
        `C26-C27` 与 `D26-D27`，仍然不等。
        """
        plan = _plan_for_region(region)

        def _mutate(xml: str) -> str:
            assert "C28-C29" in xml, "位移后的非受管公式形态变了"
            return xml.replace("C28-C29", "D28-D29", 1)

        after = self._drifted(
            base_bytes, sheet_part, plan, workdir, "p18-column.xlsx", mutate_sheet=_mutate
        )
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, "改了非受管公式的列标仍判等价"

    def test_changing_a_protected_part_still_drifts(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """改 `protected_parts`（K11 实测有 `xl/drawings/vmlDrawing1.vml`）。"""
        plan = _plan_for_region(region)
        target = "xl/drawings/vmlDrawing1.vml"
        assert target in _read_entries(base_bytes), (
            f"{target} 不在 zip 里 —— protected_parts 判据会空转"
        )

        def _mutate(entries: dict[str, bytes]) -> dict[str, bytes]:
            entries[target] = entries[target] + b"<!--drift-->"
            return entries

        after = self._drifted(
            base_bytes,
            sheet_part,
            plan,
            workdir,
            "p18-protected.xlsx",
            mutate_entries=_mutate,
        )
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, "改了 protected_parts 仍判等价"
        assert "protected_parts" in (report.first_difference or ""), report.first_difference

    def test_changing_another_sheet_part_still_drifts(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """改**跨 sheet 部件** —— 本 sheet 插行不该让别的 sheet 变化被放过。"""
        plan = _plan_for_region(region)
        others = sorted(
            name
            for name in _read_entries(base_bytes)
            if re.match(r"xl/worksheets/sheet\d+\.xml$", name) and name != sheet_part
        )
        assert others, "只有一张 sheet ⇒ other_sheet_parts 判据会空转"
        victim = others[0]

        def _mutate(entries: dict[str, bytes]) -> dict[str, bytes]:
            entries[victim] = entries[victim].replace(
                b"</worksheet>", b"<!--drift--></worksheet>", 1
            )
            return entries

        after = self._drifted(
            base_bytes,
            sheet_part,
            plan,
            workdir,
            "p18-othersheet.xlsx",
            mutate_entries=_mutate,
        )
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, f"改了 {victim} 仍判等价"
        assert "other_sheet_parts" in (report.first_difference or ""), report.first_difference

    def test_changing_a_structure_block_beyond_the_shift_still_drifts(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        """结构块里改一处**与行位移无关**的东西（合并区的列跨度）⇒ 仍判漂移。

        `E32:F32`（位移后）→ `E32:G32`：行号完全按计划，只有列变了。归一化不动列标，
        所以这一处必须仍然可见。
        """
        plan = _plan_for_region(region)

        def _mutate(xml: str) -> str:
            assert 'ref="E32:F32"' in xml, "位移后的 mergeCell 形态变了"
            return xml.replace('ref="E32:F32"', 'ref="E32:G32"', 1)

        after = self._drifted(
            base_bytes, sheet_part, plan, workdir, "p18-merge.xlsx", mutate_sheet=_mutate
        )
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, "结构块的列跨度被改仍判等价"
        assert "managed_sheet_structure" in (report.first_difference or ""), (
            report.first_difference
        )


class TestProperty20DeclaredCountMustMatchReality:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 20: 声明位移量与实测不符时判不等价**

    **Validates: Requirements 6.9**

    这是「归一化没有放宽判据」的核心论据：归一化用的是 materialize **之前冻结的声明值**，
    不是从 diff 事后推断的观测值。声明与实测不符时行号对不上 ⇒ 仍判漂移。
    """

    @pytest.mark.parametrize(
        ("actual", "declared"), [(3, 2), (2, 3), (1, 2), (5, 2), (2, 1)]
    )
    def test_mismatched_counts_are_not_equivalent(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
        actual: int,
        declared: int,
    ) -> None:
        real_plan = _plan_for_region(region, count=actual)
        after = workdir / f"p20-a{actual}-d{declared}.xlsx"
        after.write_bytes(_shifted_artifact(base_bytes, sheet_part, real_plan))

        # 先证明「声明 == 实测」这一支是通的，否则下面的不等价说明不了任何事
        assert _verify(
            base_path,
            after,
            contract=contract,
            region=region,
            scan=scan,
            row_shift=real_plan,
        ).equivalent is True

        lying_plan = _plan_for_region(region, count=declared)
        report = _verify(
            base_path,
            after,
            contract=contract,
            region=region,
            scan=scan,
            row_shift=lying_plan,
        )
        assert report.equivalent is False, (
            f"实测插 {actual} 行、声明插 {declared} 行仍判等价 ⇒ 归一化把位移量这一维放宽了"
        )

    def test_a_lying_plan_cannot_hide_a_no_op(
        self,
        base_path: Path,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
    ) -> None:
        """反面：**根本没插行**却声明插了 2 行 ⇒ 必判不等价。

        没有这一条时，「归一化 = 把 after 侧行号统一减 count」这种实现会在 before==after
        的场合下把两侧都算成同一份，从而让「声明了却没执行」静默通过。
        """
        plan = _plan_for_region(region)
        report = _verify(
            base_path, base_path, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, (
            "声明插 2 行但 before/after 是同一份字节，却判等价 —— "
            "「插行未执行却假装成功」会静默通过"
        )


class TestTotalFormulaExtensionCouplingIsRegistered:
    """🔴 Wave 2 收口时**实测发现并登记**的一条耦合，解决方案属 Wave 3。

    **Validates: Requirements 6.6**

    形态：合计行的**扩张**（`SUM(B7:B25)` → `SUM(B7:B27)`，Requirement 4.4）**不可能**被
    `plan.unshift` 还原 —— 那正是它的语义：合计范围真的变大了，不是被推下去了。
    `unshift(27) == 27`（27 < insert_at+count = 28），所以归一化后仍是 `SUM(B7:B27)`。

    而 K11 的合计格 `B26` 实测**不在**受管坐标集里（`_managed_coordinates` 只覆盖契约声明
    了 `cell` 的字段；K11 契约在 26/27/28 行只覆盖到 `B27`）。⇒ 扩张会让
    `managed_sheet_unmanaged_cells` 判漂移。

    **裁决方向（交 Wave 3 的 Task 14 落地，不在 Wave 2 放宽归一化）**：
    Requirement 4.6 说扩张只作用于「契约声明的 footer 行」。一个引擎会合法改写的格，
    按定义就该在契约管辖之内。所以正解是**契约必须用一个 `formula` 模式字段覆盖该合计格**，
    而不是让 verifier 去反向推断扩张量 —— 后者等于让被检查对象自己声明自己合法
    （design.md 拒绝方案第 3 条）。若契约声明了 `carries_total_formula` 却没有字段覆盖
    该格，Task 14 应 fail closed。

    本类把这条耦合**钉成可执行判据**，而不是只写在注释里：它现在是红的（xfail），
    Wave 3 落地后应变绿并删掉 xfail 标记。
    """

    def test_extension_without_contract_coverage_is_reported_as_drift(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        scan: object,
        workdir: Path,
    ) -> None:
        plan = _plan_for_region(region)
        after = workdir / "coupling-extension.xlsx"
        after.write_bytes(
            _shifted_artifact(
                base_bytes, sheet_part, plan, total_formula_rows=(TOTAL_ROW,)
            )
        )
        report = _verify(
            base_path, after, contract=contract, region=region, scan=scan, row_shift=plan
        )
        assert report.equivalent is False, (
            "合计扩张竟被判等价 —— 若这条变绿了，要么契约已覆盖该合计格（好事，"
            "把本用例改成断言等价并删掉本类的登记说明），要么归一化被放宽到能吞掉扩张"
            "（坏事，那是让被检查对象自己声明自己合法）"
        )
        assert "managed_sheet_unmanaged_cells" in (report.first_difference or ""), (
            report.first_difference
        )

    def test_the_total_cell_is_indeed_outside_the_managed_coordinates(
        self, contract: object, region: X.ManagedRegion, scan: object
    ) -> None:
        """把上一条的**根因**写成独立判据：合计格不在受管坐标集里。

        两条分开是刻意的：上一条只说「判漂移」，可能是任何原因；这一条钉住「因为
        `B26` 非受管」。契约哪天补上覆盖，这一条会先红，指向确切的下一步。
        """
        managed = X._managed_coordinates(
            contract=contract,  # type: ignore[arg-type]
            region=region,
            binding=BINDING,
            scan=scan,  # type: ignore[arg-type]
        )
        assert f"B{TOTAL_ROW}" not in managed, (
            f"B{TOTAL_ROW} 现在已在受管坐标集里 —— 上一条登记用例应改成断言等价"
        )
        assert f"B{TOTAL_ROW + 1}" in managed, (
            "受管坐标集里连 B27 都没有 ⇒ fixture 契约形态变了，本类的实测前提失效"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. Wave 3：footer 两门位移感知 + 契约字段（Task 12 / 13 / 14 / 15）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def runtime_binding(base_path: Path) -> Mapping[str, str]:
    """隐藏 `_GT_SYNC` 里冻结的 runtime binding（含 `GT_FOOTER_ROW`）。

    走 Task 37 的 `read_runtime_binding_pairs` 唯一读侧入口 —— 不在测试里手搓第二份
    XML 解析（生产侧首版就是因为抄了一份 `r:id="(rId\\d+)"` 而恒读空）。
    """
    with zipfile.ZipFile(base_path) as zf:
        return X.read_runtime_binding_pairs(zf)


#: K11 的 footer **anchor** marker 所在行 —— 实测 `GT_FOOTER_ROW = 26`，与 `TOTAL_ROW`
#: **同一行**（`B26:G26` 的 `SUM(B7:B25)` 就在这一行）。
#:
#: 🔴 本文件首版把它写成 27，8 条用例连带打红。27 行确实是一个纯文本标签行
#: （`A27` 为 `t="s"`、B27..J27 一处公式都没有），但它**不是** footer anchor；
#: `test_task37.FOOTER_ROW = 27` 指的是契约里另一处静态字段行，不是 anchor。
#: ⇒ 冻结事实一律现读 `read_runtime_binding_pairs`，不从别的常量名推。
FOOTER_ANCHOR_ROW = TOTAL_ROW

#: 一个**没有任何公式**的行 —— Property 16（声明带合计公式但行上无公式）的载体。
#: 实测 27 行：`A27` 是 `t="s"` 文本标签，B27..J27 全空。
FORMULA_FREE_ROW = 27


class TestFooterFixtureFacts:
    """两门判据的实测前提：anchor 行 / 合计行 / 冻结行号三者的真实取值。"""

    def test_frozen_footer_row_matches_the_anchor_row(
        self, runtime_binding: Mapping[str, str]
    ) -> None:
        assert "GT_FOOTER_ROW" in runtime_binding, sorted(runtime_binding)[:8]
        assert runtime_binding["GT_FOOTER_ROW"].strip() == str(FOOTER_ANCHOR_ROW), (
            runtime_binding["GT_FOOTER_ROW"]
        )

    def test_contract_declares_a_footer_anchor(self, contract: object) -> None:
        anchors = [
            table.footer_anchor
            for sheet in contract.sheets  # type: ignore[attr-defined]
            for table in sheet.tables
            if table.footer_anchor is not None
        ]
        assert len(anchors) == 1, anchors
        assert anchors[0].marker, anchors[0]

    def test_anchor_row_is_the_total_row_and_row_27_is_formula_free(
        self, base_sheet_xml: str
    ) -> None:
        """anchor 行**就是**合计行（26）；27 行是纯文本标签行，一处公式都没有。

        两条一起断言是刻意的：本文件首版把 anchor 记成 27，于是「anchor 行没有公式」
        这个错误前提看起来还挺自洽（27 行确实没公式）。分开钉住才能防止同类误推。
        """
        assert FOOTER_ANCHOR_ROW == TOTAL_ROW == 26
        total_block = re.search(
            rf'<row r="{TOTAL_ROW}"[^>]*>(?P<body>.*?)</row>', base_sheet_xml, re.S
        )
        free_block = re.search(
            rf'<row r="{FORMULA_FREE_ROW}"[^>]*>(?P<body>.*?)</row>', base_sheet_xml, re.S
        )
        assert total_block is not None and free_block is not None
        assert "SUM(B7:B25)" in total_block.group("body"), total_block.group("body")[:200]
        assert "<f" not in free_block.group("body"), (
            f"第 {FORMULA_FREE_ROW} 行上出现了公式 —— 冻结事实变了，"
            "Property 16 的 fixture 需重新裁决"
        )


class TestProperty15ContractFieldIsParsedAndDefaultsFalse:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 15: `FooterAnchorSpec.carries_total_formula` 被解析保留，默认假，且字段名不违反 CS-12**

    **Validates: Requirements 5.1, 5.3**
    """

    def test_default_is_false_for_existing_contracts(self, contract: object) -> None:
        """既有契约 JSON 没有该键 ⇒ 默认假（纯增量，Requirement 5.2）。"""
        anchor = next(
            table.footer_anchor
            for sheet in contract.sheets  # type: ignore[attr-defined]
            for table in sheet.tables
            if table.footer_anchor is not None
        )
        assert anchor.carries_total_formula is False, anchor

    def test_declared_true_is_retained(self) -> None:
        """声明为真时必须被**保留**（首版是静默丢弃 —— 写了没生效比没这功能更贵）。"""
        payload = contract_payload()
        rows = payload["sheets"][0]["tables"][0]
        assert "footer_anchor" in rows, "fixture 契约没有 footer_anchor，本条会空转"
        rows["footer_anchor"] = dict(rows["footer_anchor"])
        rows["footer_anchor"]["carries_total_formula"] = True
        parsed = parse_contract(payload, adapter_id=CONTRACT_ID)
        anchor = next(
            t.footer_anchor for s in parsed.sheets for t in s.tables if t.footer_anchor
        )
        assert anchor.carries_total_formula is True

    def test_silently_dropping_the_key_would_be_detectable(self) -> None:
        """反向自检：声明 `True` 与不声明必须产出**不同**的契约对象。

        这一条才是「不再被静默丢弃」的判据 —— 只断言 `is True` 时，一个恒返回 True 的
        实现也会通过。
        """
        without = parse_contract(contract_payload(), adapter_id=CONTRACT_ID)
        payload = contract_payload()
        payload["sheets"][0]["tables"][0]["footer_anchor"] = dict(
            payload["sheets"][0]["tables"][0]["footer_anchor"]
        )
        payload["sheets"][0]["tables"][0]["footer_anchor"]["carries_total_formula"] = True
        with_flag = parse_contract(payload, adapter_id=CONTRACT_ID)
        a = next(t.footer_anchor for s in without.sheets for t in s.tables if t.footer_anchor)
        b = next(t.footer_anchor for s in with_flag.sheets for t in s.tables if t.footer_anchor)
        assert a != b, "声明与不声明产出同一个 FooterAnchorSpec ⇒ 该键仍被丢弃"
        assert with_flag.canonical_sha256 != without.canonical_sha256, (
            "契约 canonical digest 不受该键影响 ⇒ 它没进 payload，发布链无从追踪"
        )

    def test_non_boolean_values_fail_closed(self) -> None:
        """`"true"` / `1` 这类形态必须拒绝 —— 接受字符串等于给「拼错也当真」留口子。"""
        from app.services.workpaper_sync.contracts import ContractSchemaError

        for bad in ("true", "false", 1, 0, "yes", []):
            payload = contract_payload()
            payload["sheets"][0]["tables"][0]["footer_anchor"] = dict(
                payload["sheets"][0]["tables"][0]["footer_anchor"]
            )
            payload["sheets"][0]["tables"][0]["footer_anchor"][
                "carries_total_formula"
            ] = bad
            with pytest.raises(ContractSchemaError, match="carries_total_formula"):
                parse_contract(payload, adapter_id=CONTRACT_ID)

    def test_field_name_does_not_violate_cs12(self) -> None:
        """CS-12 禁的是 `row` / `row_index` / `row_number` 三个键名（不得写死行号）。

        本字段声明的是「这一行有没有合计公式」这个**性质**，不是位置 —— 判据落在
        「三个禁用键仍被拒」+「本字段不在禁用集里」两侧，不是只看名字长相。
        """
        from app.services.workpaper_sync.contracts import ContractSchemaError

        assert "carries_total_formula" not in ("row", "row_index", "row_number")
        for forbidden in ("row", "row_index", "row_number"):
            payload = contract_payload()
            payload["sheets"][0]["tables"][0]["footer_anchor"] = dict(
                payload["sheets"][0]["tables"][0]["footer_anchor"]
            )
            payload["sheets"][0]["tables"][0]["footer_anchor"][forbidden] = 26
            with pytest.raises(ContractSchemaError, match=forbidden):
                parse_contract(payload, adapter_id=CONTRACT_ID)


class TestProperty21FooterAnchorIsShiftAware:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 21: footer anchor 判据为「实测 == 冻结 + 预期位移」，三值都出现在失败消息里**

    **Validates: Requirements 7.1, 7.3**
    """

    def test_zero_shift_path_is_unchanged(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: object,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """`row_shift=None` 与不传该参数都必须通过且返回同一行号（Requirement 7.2 / 7.6）。"""
        entries = _read_entries(base_bytes)
        without = M.assert_footer_anchor_stable(
            entries=entries,
            sheet_part=sheet_part,
            contract=contract,  # type: ignore[arg-type]
            runtime_binding=runtime_binding,
        )
        explicit = M.assert_footer_anchor_stable(
            entries=entries,
            sheet_part=sheet_part,
            contract=contract,  # type: ignore[arg-type]
            runtime_binding=runtime_binding,
            row_shift=None,
        )
        assert without == explicit == FOOTER_ANCHOR_ROW

    def test_planned_shift_is_accepted_and_unplanned_is_not(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        runtime_binding: Mapping[str, str],
    ) -> None:
        plan = _plan_for_region(region)
        shifted = _read_entries(
            _shifted_artifact(base_bytes, sheet_part, plan)
        )

        # (1) 不给计划 ⇒ footer 下移就是漂移。这一半必须先成立。
        with pytest.raises(M.FooterAnchorDriftError, match="已下移"):
            M.assert_footer_anchor_stable(
                entries=shifted,
                sheet_part=sheet_part,
                contract=contract,  # type: ignore[arg-type]
                runtime_binding=runtime_binding,
            )

        # (2) 给计划 ⇒ 通过，且返回的是**实测**行号（27 + 2 = 29）
        observed = M.assert_footer_anchor_stable(
            entries=shifted,
            sheet_part=sheet_part,
            contract=contract,  # type: ignore[arg-type]
            runtime_binding=runtime_binding,
            row_shift=plan,
        )
        assert observed == FOOTER_ANCHOR_ROW + plan.count == 28

    @pytest.mark.parametrize(("actual", "declared"), [(2, 3), (3, 2), (2, 1), (1, 2)])
    def test_mismatched_shift_still_drifts_and_message_carries_three_numbers(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        runtime_binding: Mapping[str, str],
        actual: int,
        declared: int,
    ) -> None:
        real = _plan_for_region(region, count=actual)
        shifted = _read_entries(_shifted_artifact(base_bytes, sheet_part, real))

        # 先证明「声明 == 实测」这一支通
        assert (
            M.assert_footer_anchor_stable(
                entries=shifted,
                sheet_part=sheet_part,
                contract=contract,  # type: ignore[arg-type]
                runtime_binding=runtime_binding,
                row_shift=real,
            )
            == FOOTER_ANCHOR_ROW + actual
        )

        lying = _plan_for_region(region, count=declared)
        with pytest.raises(M.FooterAnchorDriftError) as excinfo:
            M.assert_footer_anchor_stable(
                entries=shifted,
                sheet_part=sheet_part,
                contract=contract,  # type: ignore[arg-type]
                runtime_binding=runtime_binding,
                row_shift=lying,
            )
        message = str(excinfo.value)
        # Requirement 7.3：三个数值同时出现（实测行 / 冻结行 / 预期位移）
        assert str(FOOTER_ANCHOR_ROW + actual) in message, message
        assert str(FOOTER_ANCHOR_ROW) in message, message
        assert f"+{declared}" in message, message

    def test_footer_above_the_insertion_point_is_not_expected_to_move(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: object,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """footer 在插入点**之上**时插行不该动它 ⇒ 判据不得无条件加 `count`。

        判定走 `plan.shift(frozen)` 而不是 `frozen + count`：前者自带这个边界。
        这里造一个插入点在 footer 之下的计划（`insert_at=31`），footer 仍在 27 行，
        未位移的 base entries 必须**通过**。
        """
        plan = RS.RowShiftPlan(
            insert_at=FOOTER_ANCHOR_ROW + 5, count=2, style_from=FOOTER_ANCHOR_ROW
        )
        assert plan.shift(FOOTER_ANCHOR_ROW) == FOOTER_ANCHOR_ROW
        observed = M.assert_footer_anchor_stable(
            entries=_read_entries(base_bytes),
            sheet_part=sheet_part,
            contract=contract,  # type: ignore[arg-type]
            runtime_binding=runtime_binding,
            row_shift=plan,
        )
        assert observed == FOOTER_ANCHOR_ROW

    def test_non_numeric_frozen_row_fails_closed(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: object,
        region: X.ManagedRegion,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """冻结值不是行号时不得当成「随便什么都行」继续 —— 位移感知要拿它做算术。"""
        plan = _plan_for_region(region)
        polluted = dict(runtime_binding)
        polluted["GT_FOOTER_ROW"] = "footer"
        with pytest.raises(M.FooterAnchorDriftError, match="不是行号"):
            M.assert_footer_anchor_stable(
                entries=_read_entries(base_bytes),
                sheet_part=sheet_part,
                contract=contract,  # type: ignore[arg-type]
                runtime_binding=polluted,
                row_shift=plan,
            )


class TestProperty22And12FooterTotalUsesShiftedRegion:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 22: footer 合计判据用位移后区间求值；两道门的返回值语义不变**

    **Validates: Requirements 7.4, 7.5, 7.6**

    同时覆盖 **Property 12**（契约声明 `carries_total_formula` 为真时扩张后通过；为假时
    不改写任何公式并保持既有 fail-closed 语义）—— **Validates: Requirements 4.4, 4.5, 5.2**
    """

    def test_baseline_passes_and_returns_checked_coordinates(
        self, base_bytes: bytes, sheet_part: str, region: X.ManagedRegion
    ) -> None:
        checked = M.assert_footer_formula_covers_managed_rows(
            entries=_read_entries(base_bytes),
            sheet_part=sheet_part,
            footer_row=TOTAL_ROW,
            region=region,
        )
        # 返回值语义：非空 = 真检查过（Requirement 7.6）
        assert checked, "基线返回空清单 ⇒ 这条判据本次什么都没检查（空转）"
        assert f"B{TOTAL_ROW}" in checked, checked

    def test_shift_without_extension_still_fails_closed(
        self, base_bytes: bytes, sheet_part: str, region: X.ManagedRegion
    ) -> None:
        """位移了但合计区间**没扩张** ⇒ 仍报 `FooterFormulaRangeError`（Requirement 7.5）。

        这是「合计漏算新行」这一类真实审计缺陷的判据 —— 必须打红而不是发布出去。
        """
        plan = _plan_for_region(region)
        shifted = _read_entries(
            _shifted_artifact(base_bytes, sheet_part, plan, total_formula_rows=())
        )
        with pytest.raises(M.FooterFormulaRangeError, match="合计漏算"):
            M.assert_footer_formula_covers_managed_rows(
                entries=shifted,
                sheet_part=sheet_part,
                footer_row=TOTAL_ROW + plan.count,
                region=region,
                row_shift=plan,
            )

    def test_shift_with_declared_extension_passes(
        self, base_bytes: bytes, sheet_part: str, region: X.ManagedRegion
    ) -> None:
        """契约声明该 footer 带合计公式 ⇒ 区间已扩张 ⇒ 通过（Requirement 4.4 / 7.5）。"""
        plan = _plan_for_region(region)
        shifted = _read_entries(
            _shifted_artifact(
                base_bytes, sheet_part, plan, total_formula_rows=(TOTAL_ROW,)
            )
        )
        checked = M.assert_footer_formula_covers_managed_rows(
            entries=shifted,
            sheet_part=sheet_part,
            footer_row=TOTAL_ROW + plan.count,
            region=region,
            row_shift=plan,
            carries_total_formula=True,
        )
        assert checked, "扩张后返回空清单 ⇒ 判据空转"

    def test_extension_alone_is_not_enough_without_the_shift_aware_region(
        self, base_bytes: bytes, sheet_part: str, region: X.ManagedRegion
    ) -> None:
        """反向自检：扩张后的产物若**不**告知 `row_shift`，判据用旧区间求值 ⇒ 照样通过。

        这一条钉住「`row_shift` 真的参与了求值」：若它被忽略，
        `test_shift_without_extension_still_fails_closed` 就会变绿（旧区间 25 恒被覆盖）。
        两条合起来才证明位移量真的进了算式。
        """
        plan = _plan_for_region(region)
        shifted = _read_entries(
            _shifted_artifact(base_bytes, sheet_part, plan, total_formula_rows=())
        )
        # 不给 row_shift ⇒ 用旧区间（25）求值 ⇒ `SUM(B7:B25)` 恰好覆盖 ⇒ 通过
        checked = M.assert_footer_formula_covers_managed_rows(
            entries=shifted,
            sheet_part=sheet_part,
            footer_row=TOTAL_ROW + plan.count,
            region=region,
        )
        assert checked, "不给 row_shift 时也返回空 ⇒ fixture 形态变了"

    @pytest.mark.parametrize("count", [1, 2, 4])
    def test_extension_tracks_the_declared_count(
        self, base_bytes: bytes, sheet_part: str, region: X.ManagedRegion, count: int
    ) -> None:
        plan = _plan_for_region(region, count=count)
        shifted = _read_entries(
            _shifted_artifact(
                base_bytes, sheet_part, plan, total_formula_rows=(TOTAL_ROW,)
            )
        )
        xml = shifted[sheet_part].decode("utf-8")
        assert f"SUM(B7:B{region.last_row + count})" in xml, re.findall(
            r"SUM\(B7:B\d+\)", xml
        )
        M.assert_footer_formula_covers_managed_rows(
            entries=shifted,
            sheet_part=sheet_part,
            footer_row=TOTAL_ROW + count,
            region=region,
            row_shift=plan,
            carries_total_formula=True,
        )


class TestProperty16DeclaredTotalWithoutFormulaFailsClosed:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 16: `carries_total_formula` 为真但 footer 行一处公式都没有时 fail closed**

    **Validates: Requirements 5.4**
    """

    def test_declared_but_formula_free_row_fails_closed(
        self, base_bytes: bytes, sheet_part: str, region: X.ManagedRegion
    ) -> None:
        """把 anchor 行（27，纯文本标签）当合计行 + 声明为真 ⇒ 必须 fail closed。

        实测形态：K11 的 27 行 `A27` 是 `t="s"` 文本、B27..J27 全空。旧实现在这里
        **静默返回空 tuple** ⇒「扩张分支永远不执行」变成看不见的空转。
        """
        with pytest.raises(M.FooterFormulaRangeError, match="一处带公式文本的格都没有"):
            M.assert_footer_formula_covers_managed_rows(
                entries=_read_entries(base_bytes),
                sheet_part=sheet_part,
                footer_row=FORMULA_FREE_ROW,
                region=region,
                carries_total_formula=True,
            )

    def test_not_declared_keeps_the_old_silent_pass(
        self, base_bytes: bytes, sheet_part: str, region: X.ManagedRegion
    ) -> None:
        """未声明时同一份输入仍返回空 tuple（纯增量：既有行为逐字不变）。

        这一条是上一条的对照 —— 只有它绿，才证明 fail-closed 是**声明**带来的，
        而不是把这条路径整体改严了（那会打红一批既有契约）。
        """
        checked = M.assert_footer_formula_covers_managed_rows(
            entries=_read_entries(base_bytes),
            sheet_part=sheet_part,
            footer_row=FORMULA_FREE_ROW,
            region=region,
        )
        assert checked == (), checked


class TestProperty11SharedFormulaMasterRefTracksTheInsertionPoint:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 11: 主格在插入点之上且区间跨过插入点时 `ref` 末行 +count；主格在插入点之下时首末行整体 +count**

    **Validates: Requirements 4.2, 4.3**

    三种形态都用 K11 的真实组，不合成：
      si=0 `I7:I26`  主格 I7 在插入点（26）之上、区间**跨过**插入点 ⇒ 末行 +count
      si=1 `H8:H25`  主格在上、区间**不跨过** ⇒ 逐字不变
      si=5 `C28:G28` 主格在插入点**之下** ⇒ 首末行整体 +count
    """

    def test_three_master_positions_behave_as_declared(self, base_sheet_xml: str) -> None:
        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        before = RS.shared_formula_groups(base_sheet_xml)
        assert {0, 1, 5} <= set(before), sorted(before)
        assert before[0].ref == "I7:I26" and before[1].ref == "H8:H25"
        assert before[5].ref == "C28:G28"

        after_xml, _ = RS.shift_sheet_rows(base_sheet_xml, plan)
        after = RS.shared_formula_groups(after_xml)

        # 跨过插入点 ⇒ 末行 +count，首行不动
        assert after[0].ref == "I7:I28", after[0].ref
        # 不跨过 ⇒ 逐字不变
        assert after[1].ref == "H8:H25", after[1].ref
        # 主格在插入点之下 ⇒ 首末行整体 +count
        assert after[5].ref == "C30:G30", after[5].ref

    def test_master_below_the_insertion_point_moves_its_formula_text_too(
        self, base_sheet_xml: str
    ) -> None:
        """主格整体下移时公式文本里的相对引用同样位移（si=5 的 `C26-C27`→`C28-C29`）。"""
        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        before = RS.shared_formula_groups(base_sheet_xml)
        assert before[5].master_text == "C26-C27", before[5].master_text
        after = RS.shared_formula_groups(RS.shift_sheet_rows(base_sheet_xml, plan)[0])
        assert after[5].master_text == "C28-C29", after[5].master_text
