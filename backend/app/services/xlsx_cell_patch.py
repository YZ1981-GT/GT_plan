"""xlsx / xlsm 只改目标格（spec post-push-residual-defect-closure R4）。

填表头原先是 openpyxl 改格后整册重存：丢 x14 数据验证（39 个模板 190 条）、条件格式扩展、全部公式缓存值、
自定义 XML，`.xlsm` 怕丢宏干脆不填。这里只重写含目标格的工作表部件，其余部件连 ``ZipInfo`` 原样搬过去：

* 格级改写复用在线编辑回写的 :func:`excel_materialize.patch_sheet_xml_indexed`（同一套写法，不另写第二份）：
  文字写成内联字符串、保留样式；公式改写保留 ``<f>`` 属性、写新缓存值；缺格按列序插入、缺行按行序插入。
* 共享公式 / 数组公式格不改（改主格会让整组失效），返回 ``skipped`` 由调用方回报。
* 有公式格被改成文字 ⇒ 删 ``xl/calcChain.xml``（残留条目指向非公式格，Excel 打开会提示修复；它会重建计算链）。
* 结构性自检：部件集合只少 calcChain、除改动部件外每个部件字节逐字相等，不满足就抛错、原文件不动。
"""

from __future__ import annotations

import io
import math
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.services.workpaper_sync.excel_extract import _sheet_parts
from app.services.workpaper_sync.excel_materialize import (
    CellWrite,
    CellWriteKind,
    build_sheet_cell_index,
    patch_sheet_xml_indexed,
)

CALC_CHAIN_PART = "xl/calcChain.xml"
CONTENT_TYPES_PART = "[Content_Types].xml"
WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"

_COORD_RE = re.compile(r"^[A-Z]{1,3}[1-9]\d*$")
_CALC_CHAIN_OVERRIDE_RE = re.compile(r'<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>')
_CALC_CHAIN_REL_RE = re.compile(r'<Relationship\b[^>]*Target="(?:/xl/)?calcChain\.xml"[^>]*/>')


class XlsxPatchError(RuntimeError):
    """补丁无法安全落盘（找不到页签、坐标非法、自检不过）—— 原文件未改。"""


@dataclass(frozen=True)
class CellPatch:
    """一格的改写：``text`` 写成静态文字；``formula``（不带 ``=``）改写公式，``cached`` 是它的新缓存值。

    只给 ``cached``（``formula`` 为 None）⇒ 公式原样保留、只换缓存值（引用被改格的格）。
    """

    sheet: str
    cell: str
    text: str | None = None
    formula: str | None = None
    cached: str | None = None


@dataclass
class PatchOutcome:
    applied: list[CellPatch] = field(default_factory=list)
    #: (改写, 原因)：共享 / 数组公式格、只改缓存值但格不是公式等
    skipped: list[tuple[CellPatch, str]] = field(default_factory=list)
    calc_chain_removed: bool = False
    changed_parts: list[str] = field(default_factory=list)


def _write_for(patch: CellPatch, view) -> CellWrite | str:
    """改写 → ``CellWrite``；不能改返回原因。"""
    fattrs = view.formula_attrs if view is not None and view.has_formula else ""
    if 't="shared"' in fattrs or 't="array"' in fattrs or 't="dataTable"' in fattrs:
        return "共享公式 / 数组公式格，改写会让整组公式失效"
    if patch.text is not None:
        return CellWrite(coord=patch.cell, kind=CellWriteKind.inline_text, value=patch.text)
    if view is None or not view.has_formula:
        return "目标格不是公式格，不能只改缓存值"
    if patch.formula is not None:
        # 整格换成新公式 + 新缓存值（缓存值未知则不写 <v>）；样式保留、类型标记按值重算
        return CellWrite(coord=patch.cell, kind=CellWriteKind.formula_restored,
                         value=patch.cached, formula_text=patch.formula)
    if patch.cached is None:
        return CellWrite(coord=patch.cell, kind=CellWriteKind.cached_value_cleared, value=None)
    return CellWrite(coord=patch.cell, kind=CellWriteKind.cached_value_only, value=patch.cached)


def _clone_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    """与 ``excel_sheet_visibility._replace_workbook_part`` 同一搬法：保留日期 / 压缩方式 / 属性位。"""
    clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    clone.compress_type = info.compress_type
    clone.external_attr = info.external_attr
    clone.internal_attr = info.internal_attr
    clone.create_system = info.create_system
    clone.flag_bits = info.flag_bits & ~0x08  # 不用 data descriptor
    return clone


def _drop_calc_chain_refs(entries: dict[str, bytes]) -> None:
    ct = entries[CONTENT_TYPES_PART].decode("utf-8")
    entries[CONTENT_TYPES_PART] = _CALC_CHAIN_OVERRIDE_RE.sub("", ct, count=1).encode("utf-8")
    if WORKBOOK_RELS_PART in entries:
        rels = entries[WORKBOOK_RELS_PART].decode("utf-8")
        entries[WORKBOOK_RELS_PART] = _CALC_CHAIN_REL_RE.sub("", rels, count=1).encode("utf-8")


def _rewrite_zip(path: Path, infos: list[zipfile.ZipInfo], entries: dict[str, bytes], added: list[str],
                 before: bytes, allowed: set[str], dropped: set[str]) -> None:
    """按原顺序搬原有部件（``ZipInfo`` 原样）+ 末尾追加 ``added`` 部件，自检后原子替换。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for info in infos:
            if info.filename in entries:
                out.writestr(_clone_info(info), entries[info.filename])
        for name in added:
            out.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), entries[name],
                         compress_type=zipfile.ZIP_DEFLATED)
    new_data = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(io.BytesIO(new_data)) as b:
        expected = [n for n in a.namelist() if n not in dropped] + added
        if b.namelist() != expected:
            raise XlsxPatchError(f"zip 部件集合变了：应为 {len(expected)} 个、实为 {len(b.namelist())} 个")
        for name in a.namelist():
            if name not in dropped and name not in allowed and a.read(name) != b.read(name):
                raise XlsxPatchError(f"部件 {name} 不在改写范围内却被改动")
    tmp = path.with_name(f"{path.name}.cellpatch.tmp")
    try:
        tmp.write_bytes(new_data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# ── 追加只含值的工作表（多文件底稿合并）────────────────────────────────────────────────

WORKBOOK_PART = "xl/workbook.xml"
STYLES_PART = "xl/styles.xml"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WS_REL_TYPE = f"{_REL_NS}/worksheet"
_WS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_SHEET_TAG_RE = re.compile(r"<sheet\b[^>]*?/>", re.S)
_ATTR_RE = r'\b{name}="([^"]*)"'
_ILLEGAL_XML_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
#: Excel 内置日期 / 日期时间格式（追加页里的日期格用它们，与 openpyxl 写 datetime 时的取法一致）
_DATE_NUMFMT, _DATETIME_NUMFMT = 14, 22


@dataclass(frozen=True)
class ValueSheet:
    """一张只含值的工作表：``cells`` = [(行, 列, 值)]（行列从 1 开始）。"""

    title: str
    cells: list[tuple[int, int, object]]


def _attr(tag: str, name: str) -> str | None:
    m = re.search(_ATTR_RE.format(name=re.escape(name)), tag)
    return m.group(1) if m else None


def _unescape(text: str) -> str:
    return (text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&apos;", "'").replace("&amp;", "&"))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def workbook_sheet_names(path: Path | str) -> list[str]:
    """工作簿里的页签名（按 ``xl/workbook.xml`` 顺序，含隐藏页）。"""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read(WORKBOOK_PART).decode("utf-8")
    return [_unescape(_attr(t, "name") or "") for t in _SHEET_TAG_RE.findall(xml)]


def _unique_title(title: str, taken: set[str]) -> str:
    """Excel 页签名不分大小写、最长 31 字；重名时与 openpyxl 一样追加 1、2…"""
    base = title[:31]
    if base.lower() not in taken:
        return base
    i = 1
    while True:
        suffix = str(i)
        candidate = base[: 31 - len(suffix)] + suffix
        if candidate.lower() not in taken:
            return candidate
        i += 1


def _ensure_date_styles(entries: dict[str, bytes]) -> dict[int, int]:
    """styles.xml 的 cellXfs 末尾追加日期 / 日期时间两个格式（仅在追加页里有日期时调用），返回 {numFmtId: xf 下标}。"""
    xml = entries[STYLES_PART].decode("utf-8")
    m = re.search(r"<cellXfs\b(?P<attrs>[^>]*)>(?P<body>.*?)</cellXfs>", xml, re.S)
    if m is None:
        raise XlsxPatchError("styles.xml 没有 cellXfs")
    existing = len(re.findall(r"<xf\b", m.group("body")))
    extra = "".join(f'<xf numFmtId="{n}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
                    for n in (_DATE_NUMFMT, _DATETIME_NUMFMT))
    attrs = re.sub(r'\bcount="\d+"', f'count="{existing + 2}"', m.group("attrs"))
    if 'count="' not in attrs:
        attrs += f' count="{existing + 2}"'
    entries[STYLES_PART] = (xml[: m.start()] + f"<cellXfs{attrs}>{m.group('body')}{extra}</cellXfs>"
                            + xml[m.end():]).encode("utf-8")
    return {_DATE_NUMFMT: existing, _DATETIME_NUMFMT: existing + 1}


def _excel_serial(value) -> float:
    from datetime import date, datetime

    epoch = datetime(1899, 12, 30)
    if isinstance(value, datetime):
        delta = value.replace(tzinfo=None) - epoch
        return delta.days + delta.seconds / 86400 + delta.microseconds / 86400e6
    assert isinstance(value, date)
    return float((datetime(value.year, value.month, value.day) - epoch).days)


def _cell_xml(coord: str, value, date_styles: dict[int, int]) -> str:
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(value, bool):
        return f'<c r="{coord}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float, Decimal)):
        finite = value.is_finite() if isinstance(value, Decimal) else math.isfinite(value)
        if finite:
            text = format(value, "f") if isinstance(value, Decimal) else repr(value)
            return f'<c r="{coord}"><v>{text}</v></c>'
        value = str(value)  # NaN / inf 不是合法数值，按文字写
    if isinstance(value, (datetime, date)):
        style = date_styles[_DATETIME_NUMFMT if isinstance(value, datetime) else _DATE_NUMFMT]
        return f'<c r="{coord}" s="{style}"><v>{repr(_excel_serial(value))}</v></c>'
    text = _ILLEGAL_XML_RE.sub("", str(value))
    return f'<c r="{coord}" t="inlineStr"><is><t xml:space="preserve">{_escape(text)}</t></is></c>'


def _sheet_xml(cells: list[tuple[int, int, object]], date_styles: dict[int, int]) -> str:
    from openpyxl.utils import get_column_letter

    rows: dict[int, list[tuple[int, object]]] = {}
    for r, c, v in cells:
        rows.setdefault(r, []).append((c, v))
    body = []
    for r in sorted(rows):
        cols = sorted(rows[r], key=lambda x: x[0])
        body.append(f'<row r="{r}">' + "".join(_cell_xml(f"{get_column_letter(c)}{r}", v, date_styles)
                                                 for c, v in cols) + "</row>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<worksheet xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}"><sheetData>{"".join(body)}</sheetData></worksheet>')


def append_value_sheets(path: Path | str, sheets: list[ValueSheet]) -> list[str]:
    """把只含值的工作表追加到工作簿末尾，返回实际页签名（重名追加 1、2…，与 openpyxl 同）。

    多文件底稿合并用：原先 openpyxl 打开主文件、建页写值后整册重存，主文件的 x14 数据验证、条件格式扩展、公式缓存值、
    自定义 XML 全丢（C2~C15 的「评价控制偏差」等）。这里主文件原有部件除 ``workbook.xml`` / 其关系表 /
    ``[Content_Types].xml``（有日期格时另加 ``styles.xml``）外逐字节不变。
    """
    path = Path(path)
    if not sheets:
        return []
    data = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        entries = {info.filename: zf.read(info.filename) for info in infos}
    workbook = entries[WORKBOOK_PART].decode("utf-8")
    sheets_block = re.search(r"<sheets\b[^>]*>(?P<body>.*?)</sheets>", workbook, re.S)
    if sheets_block is None:
        raise XlsxPatchError("workbook.xml 结构不认识（没有 sheets）")
    tags = _SHEET_TAG_RE.findall(sheets_block.group("body"))
    taken = {_unescape(_attr(t, "name") or "").lower() for t in tags}
    next_sheet_id = max((int(_attr(t, "sheetId") or 0) for t in tags), default=0) + 1
    rels = entries[WORKBOOK_RELS_PART].decode("utf-8")
    rel_ids = set(re.findall(r'\bId="([^"]+)"', rels))
    part_numbers = [int(m.group(1)) for n in entries for m in [re.match(r"xl/worksheets/sheet(\d+)\.xml$", n)] if m]
    next_part = max(part_numbers, default=0) + 1
    from datetime import date as _date

    has_dates = any(isinstance(v, _date) for s in sheets for _r, _c, v in s.cells)
    date_styles = _ensure_date_styles(entries) if has_dates else {}

    titles, new_tags, new_rels, new_overrides, added = [], [], [], [], []
    for sheet in sheets:
        title = _unique_title(sheet.title, taken)
        taken.add(title.lower())
        part = f"xl/worksheets/sheet{next_part}.xml"
        while part in entries:
            next_part += 1
            part = f"xl/worksheets/sheet{next_part}.xml"
        rid, k = f"rIdGt{next_part}", 0
        while rid in rel_ids:
            k += 1
            rid = f"rIdGt{next_part}_{k}"
        rel_ids.add(rid)
        entries[part] = _sheet_xml(sheet.cells, date_styles).encode("utf-8")
        added.append(part)
        # 关系命名空间在元素上自带声明：Excel 写的 workbook.xml 在根上声明 r，openpyxl 写的在每个 <sheet> 上声明
        new_tags.append(f'<sheet xmlns:r="{_REL_NS}" name="{_escape(title)}" sheetId="{next_sheet_id}" r:id="{rid}"/>')
        new_rels.append(f'<Relationship Id="{rid}" Type="{_WS_REL_TYPE}" Target="worksheets/sheet{next_part}.xml"/>')
        new_overrides.append(f'<Override PartName="/{part}" ContentType="{_WS_CONTENT_TYPE}"/>')
        titles.append(title)
        next_sheet_id += 1
        next_part += 1

    end = sheets_block.end("body")
    entries[WORKBOOK_PART] = (workbook[:end] + "".join(new_tags) + workbook[end:]).encode("utf-8")
    entries[WORKBOOK_RELS_PART] = rels.replace("</Relationships>", "".join(new_rels) + "</Relationships>", 1).encode("utf-8")
    ct = entries[CONTENT_TYPES_PART].decode("utf-8")
    entries[CONTENT_TYPES_PART] = ct.replace("</Types>", "".join(new_overrides) + "</Types>", 1).encode("utf-8")
    allowed = {WORKBOOK_PART, WORKBOOK_RELS_PART, CONTENT_TYPES_PART} | ({STYLES_PART} if has_dates else set())
    _rewrite_zip(path, infos, entries, added, data, allowed, set())
    return titles


def patch_cells(path: Path | str, patches: list[CellPatch]) -> PatchOutcome:
    """把 ``patches`` 落到 ``path``（xlsx / xlsm）。没有可落的改写时不落盘。"""
    path = Path(path)
    outcome = PatchOutcome()
    if not patches:
        return outcome
    data = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        entries = {info.filename: zf.read(info.filename) for info in infos}
        parts = _sheet_parts(zf)

    by_part: dict[str, list[CellPatch]] = {}
    for p in patches:
        if not _COORD_RE.match(p.cell):
            raise XlsxPatchError(f"非法坐标 {p.cell!r}")
        part = parts.get(p.sheet)
        if part is None:
            raise XlsxPatchError(f"工作簿里没有页签「{p.sheet}」")
        by_part.setdefault(part, []).append(p)

    removed_formula = False
    for part, items in by_part.items():
        xml = entries[part].decode("utf-8")
        index = build_sheet_cell_index(xml)
        writes: list[CellWrite] = []
        for p in items:
            view = index.view(p.cell)
            write = _write_for(p, view)
            if isinstance(write, str):
                outcome.skipped.append((p, write))
                continue
            if write.kind is CellWriteKind.inline_text and view is not None and view.has_formula:
                removed_formula = True
            writes.append(write)
            outcome.applied.append(p)
        if writes:
            patched = patch_sheet_xml_indexed(xml, writes)
            if patched != xml:
                entries[part] = patched.encode("utf-8")
                outcome.changed_parts.append(part)

    if not outcome.changed_parts:
        return outcome
    dropped: set[str] = set()
    allowed = set(outcome.changed_parts)
    if removed_formula and CALC_CHAIN_PART in entries:
        del entries[CALC_CHAIN_PART]
        _drop_calc_chain_refs(entries)
        dropped.add(CALC_CHAIN_PART)
        allowed |= {CONTENT_TYPES_PART, WORKBOOK_RELS_PART}
        outcome.calc_chain_removed = True

    # 原子替换 + 自检：除改动部件外逐字节不变（失败时原文件完好）
    _rewrite_zip(path, infos, entries, [], data, allowed, dropped)
    return outcome
