# -*- coding: utf-8 -*-
"""Task 14~18 —— 删行判据（Property 10~15 + 35）。

spec: excel-workbook-wide-row-change-propagation / Wave 3 Task 14, 15, 16, 17, 18
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
Properties: **P10** ~ **P15** / **P35**

═══ 🔴 本文件更正了 requirements.md 的一处判据 ═══

3.8 原表述是「`undeletable_rows` = 受管区内**被引用侧引用到**的行」，实测证明那个口径
**过严**，会把本可安全删除的行锁死。三种引用形态在删行下的 Excel 语义完全不同：

| 形态 | 样本 | 删掉被指的那行 |
|---|---|---|
| **单格** | `'明细表D2-2'!AC26` | 🔴 变 `#REF!` —— 真的坏了 |
| 区间**端点** | `$AI$13:$AI$25` 删第 13 或 25 行 | ✅ 收缩成 `$AI$13:$AI$24`，仍有效 |
| 区间**内部** | 同上，删第 20 行 | ✅ 同样收缩 |
| 区间被**删光** | 13..25 全删 | 🔴 变 `#REF!` |

删掉区间内部的一行，Excel 的语义就是「那笔数据没了，合计少算一笔」—— 这正是删行
**应有**的效果，不是损坏。

⇒ 实测结论（已写回 requirements.md）：
* **D2** 数据区 `13..25`（`anchor=A11` + `header_rows=2`，`formula_mask` 印证）
  ⇒ `undeletable_rows` = **∅**，13 行全部可删。原文声明的 `{13, 25, 26}` 三个数
  逐个都不该在：13/25 只是区间端点；**26 是合计行**，不在数据区内。
* **K11** 数据区 `7..25` ⇒ **19 行全部**（每行各 6 处单格引用）⇒ 100% 阻断成立。

═══ 两个载体的分工（Wave 0 Gate 4 + 本次实测）═══

| 载体 | 角色 | 为什么 |
|---|---|---|
| **D2** | **正常路径**（删得成） | 唯一实测能走通删行全流程的载体 |
| **K11** | **阻断路径**（100% 拦下） | 单格引用覆盖全区，是 AC 3.8 存在的实证 |

🔴 只在 K11 上取证会让「删成功」这条路径**从未被执行过**；只在 D2 上取证则 fail-closed
分支从未被执行过。两个都要。
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
#: 🔴 数据区是 **13..24**（BP-21 后）—— `anchor='A11'` 是表头起点，`header_rows=2`
#: ⇒ 数据首行 = 11 + 2 = 13；末行 24 由 `formula_mask=('Q13:Q24',…)` 印证。
#: 第 25 行是排版占位 `……`（BP-21 剔出受管区），第 26 行是合计行。
D2_REGION = (13, 24)
#: 合计行（`A26` = `合计`，`footer_anchor.marker='合计'` 印证）。**不是**数据行。
D2_FOOTER_ROW = 26

K11_REL = "K/K11 资产减值损失.xlsx"
K11_SHEET = "审定表K11-1"
K11_REGION = (7, 25)

EXPECTED: dict[str, Any] = {
    "d2_undeletable": (),
    "d2_region_rows": 12,
    "d2_footer_single_cell_refs": 24,
    "k11_undeletable_count": 19,
    "k11_dangling_per_row": 6,
}


def _scan(rel: str, target: str) -> tuple[bytes, dict[str, str], N1.ReferenceScan]:
    path = TEMPLATE_ROOT / rel
    if not path.is_file():  # pragma: no cover - 模板缺失时不冒充通过
        pytest.skip(f"权威模板不在磁盘上：{rel}")
    data = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        scan = N1.scan_reference_carriers(
            zf, target_sheet=target, sheet_parts=parts, defined_names=defined
        )
    return data, parts, scan


@pytest.fixture(scope="module")
def d2() -> tuple[bytes, dict[str, str], N1.ReferenceScan]:
    return _scan(D2_REL, D2_SHEET)


@pytest.fixture(scope="module")
def k11() -> tuple[bytes, dict[str, str], N1.ReferenceScan]:
    return _scan(K11_REL, K11_SHEET)


def _managed_sheet(rows: str, *, dimension: str = "A1:C30") -> str:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{ns}"><dimension ref="{dimension}"/>'
        f"<sheetData>{rows}</sheetData></worksheet>"
    )


def _craft(managed: str, referring: str | None = None) -> tuple[bytes, dict[str, str]]:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", managed)
        if referring is not None:
            zf.writestr("xl/worksheets/sheet2.xml", referring)
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?><workbook><sheets>'
            '<sheet name="受管表" sheetId="1" r:id="rId1"/>'
            '<sheet name="引用表" sheetId="2" r:id="rId2"/>'
            "</sheets></workbook>",
        )
    parts = {"受管表": "xl/worksheets/sheet1.xml"}
    if referring is not None:
        parts["引用表"] = "xl/worksheets/sheet2.xml"
    return buffer.getvalue(), parts


def _scan_crafted(data: bytes, parts: dict[str, str]) -> N1.ReferenceScan:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return N1.scan_reference_carriers(
            zf, target_sheet="受管表", sheet_parts=parts, defined_names=()
        )


def _text_of(data: bytes, part: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read(part).decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Property 35 —— undeletable_rows（Requirement 3.8）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty35UndeletableRows:
    """🔴 两侧判据：D2 = ∅（可删）/ K11 = 19 行全锁。缺任一侧就有一条路径没被执行。"""

    def test_d2_has_no_undeletable_rows(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """D2 数据区 13 行**全部可删** —— 更正了 requirements.md 的 `{13, 25, 26}`。"""
        _data, _parts, scan = d2
        rows = N1.find_undeletable_rows(
            scan,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            count=1,
        )
        assert rows == EXPECTED["d2_undeletable"] == (), (
            f"D2 数据区实测锁了 {rows} —— 该区内一处单格引用都没有，应为空集。"
            "锁死会让 D2 的删行功能永远失败"
        )

    def test_d2_region_is_13_to_24_not_11_to_25(self) -> None:
        """🔴 分母前提：D2 数据区是 **13..24**（BP-21 后），不是 `anchor` 的 11、也不是 25。

        `anchor='A11'` 是**表头**起点，`header_rows=2` ⇒ 数据首行 13。末行由 BP-21 从 25
        收缩为 24（25 是排版占位 `……`）。判据从契约的 `formula_mask` 现算，不写死 ——
        契约改了这里会红。
        """
        from app.services.workpaper_sync.contracts import load_contract

        table = load_contract("d2.receivable_detail").sheets[0].tables[0]
        anchor_row = int("".join(ch for ch in table.anchor if ch.isdigit()))
        assert anchor_row == 11 and table.header_rows == 2
        assert anchor_row + table.header_rows == D2_REGION[0] == 13
        # formula_mask 印证末行 24（BP-21 后）
        assert any("13:" in m and m.endswith("24") for m in table.formula_mask), (
            f"formula_mask {table.formula_mask} 未印证数据区 13..24"
        )
        assert D2_REGION[1] - D2_REGION[0] + 1 == EXPECTED["d2_region_rows"]

    def test_d2_footer_row_is_outside_the_region(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """🔴 第 26 行是**合计行**，24 处单格引用指向它 —— 但它不在数据区内。

        原 requirements.md 把它列进 `undeletable_rows`，那是把「合计行会因删数据行而
        上移」（AC 3.3 的传播）与「这行不可删」（AC 3.8）混为一谈。
        """
        _data, _parts, scan = d2
        assert not (D2_REGION[0] <= D2_FOOTER_ROW <= D2_REGION[1])
        single_cell_hits = sum(
            1
            for site in scan.sites
            if ":" not in site.reference.token and D2_FOOTER_ROW in site.rows
        )
        assert single_cell_hits == EXPECTED["d2_footer_single_cell_refs"] == 24, (
            f"合计行的单格引用实测 {single_cell_hits} 处"
        )
        # 合计行确实是「合计」
        from app.services.workpaper_sync.contracts import load_contract

        footer = load_contract("d2.receivable_detail").sheets[0].tables[0].footer_anchor
        assert footer is not None and footer.marker == "合计"

    def test_d2_rows_13_and_25_are_only_range_endpoints(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """🔴 区间端点里落在数据区内的只有 13（BP-21 后区间末行 24，范围端点 25 已在区外），
        数据区内单格引用 0 处。

        这是「原文那三个数都不该在」的第二半证据。
        """
        _data, _parts, scan = d2
        region = range(D2_REGION[0], D2_REGION[1] + 1)
        single_in_region = sorted(
            {
                row
                for site in scan.sites
                if ":" not in site.reference.token
                for row in site.rows
                if row in region
            }
        )
        assert single_in_region == [], (
            f"数据区内出现了单格引用 {single_in_region} —— 与「D2 全部可删」矛盾"
        )
        endpoints = sorted(
            {
                row
                for site in scan.sites
                if ":" in site.reference.token
                for row in site.rows
                if row in region
            }
        )
        assert endpoints == [13], endpoints

    def test_k11_blocks_every_row_in_region(
        self, k11: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """K11 数据区 19 行**全部**不可删 —— AC 3.8 存在的实证。"""
        _data, _parts, scan = k11
        rows = N1.find_undeletable_rows(
            scan,
            region_first_row=K11_REGION[0],
            region_last_row=K11_REGION[1],
            count=1,
        )
        region = set(range(K11_REGION[0], K11_REGION[1] + 1))
        assert len(rows) == EXPECTED["k11_undeletable_count"] == 19
        assert set(rows) == region, sorted(region - set(rows))

    def test_both_sides_are_non_degenerate(
        self,
        d2: tuple[bytes, dict[str, str], N1.ReferenceScan],
        k11: tuple[bytes, dict[str, str], N1.ReferenceScan],
    ) -> None:
        """🔴 分母自检：两侧必须是**不同**的结果，否则判据分辨不出对错。

        若实现恒返回空集，K11 那条会红；若恒返回全区，D2 那条会红。本条把「两侧必须
        不同」本身写成判据 —— 它拦的是「两侧碰巧都对但实现其实是常量」这类退化。
        """
        _d, _p, d2_scan = d2
        _k, _q, k11_scan = k11
        d2_rows = N1.find_undeletable_rows(
            scan=d2_scan,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
        )
        k11_rows = N1.find_undeletable_rows(
            scan=k11_scan,
            region_first_row=K11_REGION[0],
            region_last_row=K11_REGION[1],
        )
        assert len(d2_rows) == 0 and len(k11_rows) == 19
        assert d2_rows != k11_rows

    def test_multi_row_delete_widens_the_locked_set(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """🔴 `count` 变大时锁定集必须相应变大 —— 删满整个数据区确实会让区间整体消失。

        没有这条，把第②条写成恒不命中（即只看单格引用）也能让上面的 D2 判据绿，
        而那会漏掉「删光整个区间」这类真损坏。
        """
        _data, _parts, scan = d2
        narrow = N1.find_undeletable_rows(
            scan,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            count=1,
        )
        # 🔴 range `$AI$13:$AI$25` 跨 13..25（末端 25 = 合计行前的排版占位行）。BP-21 后
        #    数据区末行是 24，所以删满 12 行数据区**不足以**删光该 range（行 25 仍在）——
        #    必须删到行 25 才会整体消失，即 count = 25 - 13 + 1 = 13。这正是「count 越大锁
        #    定集越大」的证据：删不到 range 末端不锁，删到才锁全区。
        collapse_count = 25 - D2_REGION[0] + 1  # = 13
        wide = N1.find_undeletable_rows(
            scan,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            count=collapse_count,
        )
        assert narrow == ()
        assert set(wide) == set(range(D2_REGION[0], D2_REGION[1] + 1)), (
            f"删到 range 末端（`$AI$13:$AI$25` 会被删光）时应锁全区，实得 {wide}"
        )

    def test_degenerate_single_row_range_is_locked(self) -> None:
        """退化区间 `A20:A20` 覆盖 1 行 ⇒ 删那行必然让它消失 ⇒ 锁定。

        D2 / K11 上都没有这形态（实测 0 处）⇒ 注入。
        """
        data, parts = _craft(
            _managed_sheet('<row r="20"><c r="A20"><v>1</v></c></row>'),
            _managed_sheet('<row r="5"><c r="A5"><f>SUM(\'受管表\'!A20:A20)</f></c></row>'),
        )
        scan = _scan_crafted(data, parts)
        rows = N1.find_undeletable_rows(
            scan, region_first_row=13, region_last_row=25, count=1
        )
        assert 20 in rows, (
            f"退化区间 A20:A20 未被锁定（实得 {rows}）—— 删第 20 行会让它变 #REF!"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 10 / 11 —— 受管 sheet 内的删行结构（Requirement 3.1 / 3.2 / 3.6）
# ═══════════════════════════════════════════════════════════════════════════


class TestShrinkSheetRows:
    """被删行移除、其后行上移 `count`、`dimension` 收缩。"""

    def test_rows_are_removed_and_following_rows_move_up(self) -> None:
        xml = _managed_sheet(
            '<row r="12"><c r="A12"><v>1</v></c></row>'
            '<row r="13"><c r="A13"><v>2</v></c></row>'
            '<row r="14"><c r="A14"><v>3</v></c></row>'
            '<row r="20"><c r="A20"><v>9</v></c></row>'
        )
        out, removed = N1.shrink_sheet_rows(xml, delete_at=13, count=1)
        assert removed == 1
        assert '<row r="12"' in out
        assert '<c r="A12"' in out
        # 原 14 → 13，原 20 → 19
        assert '<row r="13"' in out and '<c r="A13"><v>3</v>' in out
        assert '<row r="19"' in out and '<c r="A19"><v>9</v>' in out
        assert '<row r="14"' not in out and '<row r="20"' not in out

    def test_cell_coordinates_follow_the_row(self) -> None:
        """🔴 `<row r=>` 与其中每个 `<c r=>` 必须一起改 —— 只改一边产物会坏。

        ⚠ **公式文本里的行号刻意不动**（`SUM(A20:B20)` 原样保留）。`shrink_sheet_rows`
        只管**结构**（行号与单元格坐标），公式里的引用由传播那半处理。分开是因为「结构」
        与「引用」是两件事，混在一起时任何一边的 bug 都会被另一边掩盖 —— 本条用
        `<f>` 内容不变来把这个边界钉住。
        """
        xml = _managed_sheet(
            '<row r="20"><c r="A20"><v>1</v></c><c r="AB20"><v>2</v></c>'
            '<c r="C20"><f>SUM(A20:B20)</f></c></row>'
        )
        out, _removed = N1.shrink_sheet_rows(xml, delete_at=13, count=2)
        assert '<row r="18"' in out
        assert '<c r="A18"' in out and '<c r="AB18"' in out and '<c r="C18"' in out
        # 坐标属性里不得有残留的 20
        assert '<c r="A20"' not in out and '<c r="AB20"' not in out
        assert '<row r="20"' not in out
        # 公式文本原样保留 —— 这是 shrink 与传播的分工边界
        assert "<f>SUM(A20:B20)</f>" in out, out

    @pytest.mark.parametrize("count", [1, 2, 5])
    def test_multi_row_delete(self, count: int) -> None:
        rows = "".join(
            f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>' for r in range(13, 26)
        )
        out, removed = N1.shrink_sheet_rows(
            _managed_sheet(rows), delete_at=13, count=count
        )
        assert removed == count
        # 剩下 13 - count 行，且首行仍是 13
        assert f'<row r="13"' in out
        assert f'<v>{13 + count}</v>' in out, "上移后的首行值不对"

    def test_dimension_shrinks(self) -> None:
        xml = _managed_sheet("", dimension="A1:AM35")
        out, _removed = N1.shrink_sheet_rows(xml, delete_at=13, count=2)
        assert 'ref="A1:AM33"' in out, out

    def test_non_positive_count_is_refused(self) -> None:
        for bad in (0, -1):
            with pytest.raises(N1.RowChangeKindError, match="必须为正"):
                N1.shrink_sheet_rows(_managed_sheet(""), delete_at=13, count=bad)

    def test_delete_beyond_region_is_refused(self) -> None:
        """越过受管区边界抛 `RowChangeOutOfRegionError`（AC 3.6）。

        越界删行会删掉未管理区的行 —— 那是 projection 无权处置的数据。
        """
        data, parts = _craft(_managed_sheet('<row r="20"><c r="A20"><v>1</v></c></row>'))
        scan = _scan_crafted(data, parts)
        # 末行越界
        with pytest.raises(N1.RowChangeOutOfRegionError, match="越出受管区"):
            N1.build_delete_plan(
                scan,
                managed_sheet_name="受管表",
                managed_sheet_part=parts["受管表"],
                at=24,
                count=5,  # 24..28 越过 25
                region_first_row=13,
                region_last_row=25,
                row_uuids={r: f"u{r}" for r in range(13, 30)},
            )
        # 首行越界
        with pytest.raises(N1.RowChangeOutOfRegionError, match="越出受管区"):
            N1.build_delete_plan(
                scan,
                managed_sheet_name="受管表",
                managed_sheet_part=parts["受管表"],
                at=12,
                count=1,
                region_first_row=13,
                region_last_row=25,
                row_uuids={r: f"u{r}" for r in range(10, 30)},
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 14 —— 业务键留痕（Requirement 3.7）
# ═══════════════════════════════════════════════════════════════════════════


class TestDeletedRowKeys:
    """`row_uuid` → 稳定序号 → 抛。优先级不可颠倒。"""

    def test_row_uuid_wins_over_ordinal(self) -> None:
        """🔴 优先级：`row_uuid` 是行的**身份**，稳定序号只是**位置**。

        删行后序号会指到另一笔业务数据上，所以两者都在时必须取 uuid。
        """
        keys = N1.resolve_deleted_row_keys(
            [13, 14],
            row_uuids={13: "uuid-a", 14: "uuid-b"},
            stable_ordinals={13: "seq-1", 14: "seq-2"},
        )
        assert keys == ("uuid-a", "uuid-b")

    def test_falls_back_to_ordinal(self) -> None:
        keys = N1.resolve_deleted_row_keys(
            [13, 14], row_uuids={13: "uuid-a"}, stable_ordinals={14: "seq-2"}
        )
        assert keys == ("uuid-a", "seq-2")

    def test_missing_identity_is_refused(self) -> None:
        """无稳定键 ⇒ 拒绝删行。删除不可逆，无留痕无从审计。"""
        with pytest.raises(N1.MissingRowIdentityError, match="无留痕不得执行"):
            N1.resolve_deleted_row_keys([13, 14], row_uuids={13: "uuid-a"})

    def test_blank_identity_counts_as_missing(self) -> None:
        """空串 / 空白不算键 —— 否则「有键」会被空字符串蒙过去。"""
        for bad in ("", "   ", None):
            with pytest.raises(N1.MissingRowIdentityError):
                N1.resolve_deleted_row_keys([13], row_uuids={13: bad})  # type: ignore[dict-item]

    def test_duplicate_keys_are_refused(self) -> None:
        """重复键无法一一对应到被删行 ⇒ 事后无从复原删了哪几笔。"""
        with pytest.raises(N1.MissingRowIdentityError, match="重复"):
            N1.resolve_deleted_row_keys(
                [13, 14], row_uuids={13: "same", 14: "same"}
            )

    def test_plan_requires_one_key_per_deleted_row(self) -> None:
        """计划层的守卫：键数必须等于被删行数。"""
        data, parts = _craft(_managed_sheet('<row r="20"><c r="A20"><v>1</v></c></row>'))
        scan = _scan_crafted(data, parts)
        with pytest.raises(N1.MissingRowIdentityError):
            N1.build_delete_plan(
                scan,
                managed_sheet_name="受管表",
                managed_sheet_part=parts["受管表"],
                at=13,
                count=3,
                region_first_row=13,
                region_last_row=25,
                row_uuids={13: "a", 14: "b"},  # 缺第 15 行
            )

    def test_d2_plan_carries_keys_for_every_deleted_row(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """真实 D2：删 2 行 ⇒ 恰 2 个键。"""
        _data, parts, scan = d2
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name=D2_SHEET,
            managed_sheet_part=parts[D2_SHEET],
            at=18,
            count=2,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            row_uuids={r: f"row-{r}" for r in range(13, 26)},
        )
        assert plan.deleted_row_keys == ("row-18", "row-19")


# ═══════════════════════════════════════════════════════════════════════════
# Property 12 / 13 —— 悬空引用 fail-closed（Requirement 3.4 / 3.5）
# ═══════════════════════════════════════════════════════════════════════════


class TestDanglingFailClosed:
    """🔴 计划阶段就拦（不等写盘），且携带**完整**清单。"""

    def test_k11_mid_region_delete_is_refused(
        self, k11: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """Property 13：K11 受管区中间删一行 ⇒ 命中单格引用 ⇒ 拒绝。"""
        _data, parts, scan = k11
        with pytest.raises(N1.DanglingReferenceError) as excinfo:
            N1.build_delete_plan(
                scan,
                managed_sheet_name=K11_SHEET,
                managed_sheet_part=parts[K11_SHEET],
                at=16,
                count=1,
                region_first_row=K11_REGION[0],
                region_last_row=K11_REGION[1],
                row_uuids={r: f"row-{r}" for r in range(7, 26)},
            )
        message = str(excinfo.value)
        assert "#REF!" in message
        assert f"{EXPECTED['k11_dangling_per_row']} 处" in message, message
        assert K11_SHEET in message
        # 清单必须点名具体位置，不能只报个数
        assert "sheet4.xml" in message or "sheet5.xml" in message, message

    def test_dangling_list_is_complete_not_first_only(
        self, k11: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """🔴 只报第一处会让调用方逐个试错 —— 必须一次给全。"""
        _data, _parts, scan = k11
        sites = N1.find_dangling_sites(scan, delete_at=16, count=1)
        assert len(sites) == EXPECTED["k11_dangling_per_row"] == 6
        assert all(s.reason == "single_cell" for s in sites), [
            s.reason for s in sites
        ]
        assert all(16 in s.broken_rows for s in sites)

    def test_range_partially_deleted_is_not_dangling(self) -> None:
        """🔴 区间只被删掉**部分**行 ⇒ 不算坏（Excel 会收缩区间）。

        这是本文件更正 requirements.md 的核心一条。若实现把它判成 dangling，
        D2 的删行会永远失败。
        """
        data, parts = _craft(
            _managed_sheet(
                "".join(
                    f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>'
                    for r in range(13, 26)
                )
            ),
            _managed_sheet(
                '<row r="5"><c r="A5">'
                "<f>SUM('受管表'!$A$13:$A$25)</f></c></row>"
            ),
        )
        scan = _scan_crafted(data, parts)
        assert scan.sites, "扫描无结果，判据空转"
        # 删区间内部一行
        assert N1.find_dangling_sites(scan, delete_at=19, count=1) == ()
        # 删区间端点也不算坏
        assert N1.find_dangling_sites(scan, delete_at=13, count=1) == ()
        assert N1.find_dangling_sites(scan, delete_at=25, count=1) == ()

    def test_range_fully_deleted_is_dangling(self) -> None:
        """区间被**删光** ⇒ `range_emptied` ⇒ 拦下。"""
        data, parts = _craft(
            _managed_sheet(
                "".join(
                    f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>'
                    for r in range(13, 26)
                )
            ),
            _managed_sheet(
                '<row r="5"><c r="A5">'
                "<f>SUM('受管表'!$A$13:$A$25)</f></c></row>"
            ),
        )
        scan = _scan_crafted(data, parts)
        sites = N1.find_dangling_sites(scan, delete_at=13, count=13)
        assert len(sites) == 1 and sites[0].reason == "range_emptied", [
            s.as_dict() for s in sites
        ]

    def test_ref_errors_require_explicit_opt_in(
        self, k11: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """🔴 只有契约**显式**声明允许时才放行写 `#REF!`（AC 3.5）。

        默认 fail closed。静默写 `#REF!` 会让底稿在用户打开时才暴露损坏，那时已无从
        追溯是哪次同步造成的。
        """
        _data, parts, scan = k11
        kwargs = dict(
            managed_sheet_name=K11_SHEET,
            managed_sheet_part=parts[K11_SHEET],
            at=16,
            count=1,
            region_first_row=K11_REGION[0],
            region_last_row=K11_REGION[1],
            row_uuids={r: f"row-{r}" for r in range(7, 26)},
        )
        with pytest.raises(N1.DanglingReferenceError):
            N1.build_delete_plan(scan, **kwargs)  # type: ignore[arg-type]
        plan = N1.build_delete_plan(scan, allow_ref_errors=True, **kwargs)  # type: ignore[arg-type]
        assert plan.kind is N1.RowChangeKind.DELETE
        # 放行后，坏掉的那 6 处**不进**传播清单（它们不是「改行号」而是「坏了」）
        raws = {e.ref_before for e in plan.propagations}
        assert not any("16" in r and ":" not in r for r in raws), sorted(raws)[:6]

    def test_d2_mid_region_delete_succeeds(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """🔴 正常路径：D2 区中间删一行 **不**抛，计划正常建成。

        没有这条，把 fail-closed 写成「恒抛」也能让 K11 那条绿 —— 而那会让删行功能
        完全不可用。
        """
        _data, parts, scan = d2
        assert N1.find_dangling_sites(scan, delete_at=19, count=1) == ()
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name=D2_SHEET,
            managed_sheet_part=parts[D2_SHEET],
            at=19,
            count=1,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            row_uuids={r: f"row-{r}" for r in range(13, 26)},
        )
        assert plan.propagations, "删行竟无任何传播条目 ⇒ 判据空转"
        assert plan.undeletable_rows == ()


# ═══════════════════════════════════════════════════════════════════════════
# Property 15 —— 引用侧向上传播（Requirement 3.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestUpwardPropagation:
    """指向被删区间**之后**的引用行号 `-= count`。"""

    @pytest.mark.parametrize("count", [1, 2, 3])
    def test_refs_after_deleted_range_move_up(self, count: int) -> None:
        data, parts = _craft(
            _managed_sheet(
                "".join(
                    f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>'
                    for r in range(13, 30)
                )
            ),
            _managed_sheet(
                '<row r="5"><c r="A5"><f>\'受管表\'!A28</f></c>'
                '<c r="B5"><f>\'受管表\'!A14</f></c></row>'
            ),
        )
        scan = _scan_crafted(data, parts)
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name="受管表",
            managed_sheet_part=parts["受管表"],
            at=20,
            count=count,
            region_first_row=13,
            region_last_row=25,
            row_uuids={r: f"u{r}" for r in range(13, 30)},
        )
        produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
        out = _text_of(produced, parts["引用表"])
        # A28 在被删区间之后 ⇒ 上移
        assert f"'受管表'!A{28 - count}" in out, out
        # A14 在被删区间之前 ⇒ 不动
        assert "'受管表'!A14" in out, out
        report.assert_matches_plan(plan)

    def test_delta_is_negative_for_delete_plans(self) -> None:
        """🔴 删行的传播条目 `delta` 必须为**负** —— 方向错了等于把数据指到反方向。"""
        data, parts = _craft(
            _managed_sheet(
                "".join(
                    f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>'
                    for r in range(13, 30)
                )
            ),
            _managed_sheet('<row r="5"><c r="A5"><f>\'受管表\'!A28</f></c></row>'),
        )
        scan = _scan_crafted(data, parts)
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name="受管表",
            managed_sheet_part=parts["受管表"],
            at=20,
            count=2,
            region_first_row=13,
            region_last_row=25,
            row_uuids={r: f"u{r}" for r in range(13, 30)},
        )
        assert plan.propagations
        for entry in plan.propagations:
            assert entry.delta == -2, entry.as_dict()

    def test_d2_footer_row_reference_moves_up(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """🔴 真实形态：D2 合计行（26）的 24 处引用在删数据行后**上移**。

        这正是 requirements.md 原文把 26 列进 `undeletable_rows` 所混淆的那件事 ——
        合计行不是「不可删」，是「会因删数据行而上移」，属本条（AC 3.3）。
        """
        data, parts, scan = d2
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name=D2_SHEET,
            managed_sheet_part=parts[D2_SHEET],
            at=19,
            count=1,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            row_uuids={r: f"row-{r}" for r in range(13, 26)},
        )
        footer_entries = [
            e for e in plan.propagations if e.row_before == D2_FOOTER_ROW
        ]
        assert len(footer_entries) == EXPECTED["d2_footer_single_cell_refs"] == 24, (
            f"合计行的传播条目实测 {len(footer_entries)} 条"
        )
        for entry in footer_entries:
            assert entry.row_after == D2_FOOTER_ROW - 1 == 25, entry.as_dict()

        produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
        report.assert_matches_plan(plan)
        # 抽查产物：AC26 → AC25
        changed_text = "".join(
            _text_of(produced, part)
            for part in plan.touched_parts
            if part.startswith("xl/worksheets/")
        )
        assert "'明细表D2-2'!AC25" in changed_text, "合计行引用未上移"
        assert "'明细表D2-2'!AC26" not in changed_text, "还有未上移的合计行引用"

    def test_range_endpoints_shrink_on_delete(self) -> None:
        """区间引用在删行后**收缩**：`$A$13:$A$25` 删 1 行 → `$A$13:$A$24`。

        🔴 这是「删区间内部不算坏」在**产物**上的对应证据 —— 前面的判据只验了
        「不抛」，本条验「收缩后的文本确实对」。
        """
        data, parts = _craft(
            _managed_sheet(
                "".join(
                    f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>'
                    for r in range(13, 26)
                )
            ),
            _managed_sheet(
                '<row r="5"><c r="A5">'
                "<f>SUM('受管表'!$A$13:$A$25)</f></c></row>"
            ),
        )
        scan = _scan_crafted(data, parts)
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name="受管表",
            managed_sheet_part=parts["受管表"],
            at=19,
            count=1,
            region_first_row=13,
            region_last_row=25,
            row_uuids={r: f"u{r}" for r in range(13, 26)},
        )
        produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
        out = _text_of(produced, parts["引用表"])
        assert "'受管表'!$A$13:$A$24" in out, out
        report.assert_matches_plan(plan)


# ═══════════════════════════════════════════════════════════════════════════
# 产物级：删行的 apply（Requirement 3.1 端到端）
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteProduct:
    """真实 D2 上删行的产物：部件面、可打开性、行数。"""

    def test_d2_delete_product_opens_and_loses_one_row(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan], tmp_path: Path
    ) -> None:
        openpyxl = pytest.importorskip("openpyxl")
        data, parts, scan = d2
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name=D2_SHEET,
            managed_sheet_part=parts[D2_SHEET],
            at=19,
            count=1,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            row_uuids={r: f"row-{r}" for r in range(13, 26)},
        )
        produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
        report.assert_matches_plan(plan)

        before = tmp_path / "before.xlsx"
        after = tmp_path / "after.xlsx"
        before.write_bytes(data)
        after.write_bytes(produced)

        wb_before = openpyxl.load_workbook(before)
        rows_before = wb_before[D2_SHEET].max_row
        names = list(wb_before.sheetnames)
        wb_before.close()

        wb_after = openpyxl.load_workbook(after)
        try:
            assert list(wb_after.sheetnames) == names, "sheet 集合变了"
            assert wb_after[D2_SHEET].max_row == rows_before - 1, (
                f"删 1 行后 max_row={wb_after[D2_SHEET].max_row}，"
                f"删前 {rows_before}"
            )
        finally:
            wb_after.close()

    def test_only_declared_parts_change_on_delete(
        self, d2: tuple[bytes, dict[str, str], N1.ReferenceScan]
    ) -> None:
        """删行同样受「除声明部件外零字节变化」约束。"""
        data, parts, scan = d2
        plan = N1.build_delete_plan(
            scan,
            managed_sheet_name=D2_SHEET,
            managed_sheet_part=parts[D2_SHEET],
            at=19,
            count=1,
            region_first_row=D2_REGION[0],
            region_last_row=D2_REGION[1],
            row_uuids={r: f"row-{r}" for r in range(13, 26)},
        )
        produced, _report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
        allowed = (
            set(plan.touched_parts)
            | {plan.managed_sheet_part}
            | {N1.WORKBOOK_PART}
        )
        with zipfile.ZipFile(io.BytesIO(data)) as a, zipfile.ZipFile(
            io.BytesIO(produced)
        ) as b:
            assert a.namelist() == b.namelist(), "部件集合变了"
            changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
        assert changed, "一个部件都没变 ⇒ 删行什么都没做"
        unexpected = sorted(set(changed) - allowed)
        assert not unexpected, f"未声明部件被改动：{unexpected}"

    def test_delete_plan_rejects_style_from(self) -> None:
        """删行不产生新行 ⇒ 不得声明 `style_from`。"""
        with pytest.raises(N1.RowChangeKindError, match="style_from"):
            N1.WorkbookRowChangePlan(
                kind=N1.RowChangeKind.DELETE,
                managed_sheet_name="受管表",
                managed_sheet_part="xl/worksheets/sheet1.xml",
                at=13,
                count=1,
                style_from=12,
                region_first_row=13,
                region_last_row=25,
                deleted_row_keys=("k",),
            )
