"""真实 OnlyOffice 9.4 Excel identity instrumentation 黑盒探针（spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 5）

目的（design.md §Identity probe 决策门 / Requirement 6.13–6.17 / Property 66）：
在建通用 Excel engine 之前，用**真实 OO 9.4 容器 + 平台自有真实模板**取证三类 identity 载体
经真实编辑器往返后是否保留：

  1. hidden `_GT_SYNC` metadata sheet
  2. workbook 级 / sheet-local defined names
  3. Excel Table（`xl/tables/tableN.xml`）+ 隐藏 row UUID 列

操作矩阵（Task 5 硬要求，逐操作各采一次 artifact 并比结构指纹）：
  edit / insert_row / delete_row / sort / copy / paste / rename_sheet / forcesave / download / reopen

与 Task 4 探针的关系：
  - 复用同一套 document host + callback collector + Command Service 客户端 + JWT + 脱敏骨架；
  - **新增**「OOXML 结构指纹」采集（Task 4 只读回指定单元格值，无法判断载体是否被剥离）；
  - **新增** zip 级 instrumentation（把三类载体注入 staging 副本）与 visible-equivalence 报告。

🔴 硬约束：
  - `backend/wp_templates/` 是运行时权威源，**只读**。所有 instrumentation 只作用于
    evidence/staging 目录里的副本；`verify-source` 子命令在开工/收工各核一次源文件 sha256。
  - 不接通生产 callback、不写业务库、不改 OO 容器配置。
  - 采集异常一律记 ERROR 态（`errors` 数组 / `probe_verdict=failed`），禁止吞成「无数据」。

用法（Windows，仓库根）：
    python backend/scripts/diagnose/probe_oo94_excel_identity.py verify-source --stage before
    python backend/scripts/diagnose/probe_oo94_excel_identity.py instrument
    python backend/scripts/diagnose/probe_oo94_excel_identity.py serve --doc k11
    python backend/scripts/diagnose/probe_oo94_excel_identity.py mark --op edit
    python backend/scripts/diagnose/probe_oo94_excel_identity.py command --c forcesave --userdata op-edit
    python backend/scripts/diagnose/probe_oo94_excel_identity.py snapshot --op edit --source download
    python backend/scripts/diagnose/probe_oo94_excel_identity.py analyze
    python backend/scripts/diagnose/probe_oo94_excel_identity.py verify-source --stage after
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from jose import jwt

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.excel_structure_fingerprint import (  # noqa: E402
    GT_SYNC_SHEET_NAME,
    FingerprintError,
    identity_inventory,
    structure_fingerprint,
    visible_equivalence_report,
)

SPEC_DIR = (
    REPO_ROOT
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
DEFAULT_EVIDENCE_DIR = SPEC_DIR / "evidence" / "task5-oo94-excel-identity"

# Task 4 实测环境事实（build 9.4.0-129 / JWT_ENABLED=true / header Authorization / inBody=false）。
OO_SECRET = os.environ.get("PROBE_OO_SECRET", "onlyoffice-dev-secret-2026")
OO_URL_FROM_HOST = os.environ.get("PROBE_OO_URL", "http://localhost:8080")
HOST_FROM_CONTAINER = os.environ.get("PROBE_HOST_FOR_OO", "host.docker.internal")
#: Task 4 用了 9991，本探针换端口避免残留冲突。
DEFAULT_PORT = 9993

#: Task 5 操作矩阵（顺序即执行顺序；`reopen` 必须最后）。
OPERATIONS = (
    "baseline",
    "edit",
    "insert_row",
    "delete_row",
    "sort",
    "copy",
    "paste",
    "rename_sheet",
    "forcesave",
    "download",
    "reopen",
)


# ---------------------------------------------------------------------------
# 探针文档定义（平台自有真实模板 + instrumentation 参数）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeDoc:
    key: str
    #: `backend/wp_templates/` 下的相对路径（**只读权威源**）
    template_rel: str
    template_id: str
    #: 承载 Excel Table + 隐藏 UUID 列的业务 sheet 展示名（instrumentation 时刻）
    managed_sheet: str
    #: 受管动态行范围（1-based，含端点）
    first_data_row: int
    last_data_row: int
    footer_row: int
    #: 受管业务列（Table 从 A 列起覆盖到 UUID 列）
    managed_last_col: str
    #: 隐藏 UUID 列列标
    uuid_col: str
    #: OO 内可安全编辑的业务单元格（非公式格）
    edit_cell: str
    #: 是否注入 Excel Table 载体（C24 已自带 Table 且含 8 个 chart，只注入前两类载体）
    inject_table: bool
    table_name: str
    note: str = ""


PROBE_DOCS: dict[str, ProbeDoc] = {
    "k11": ProbeDoc(
        key="k11",
        template_rel="backend/wp_templates/K/K11 资产减值损失.xlsx",
        template_id="K11",
        managed_sheet="审定表K11-1",
        first_data_row=7,
        last_data_row=25,
        footer_row=26,
        managed_last_col="L",
        uuid_col="N",
        edit_cell="J7",
        inject_table=True,
        table_name="GT_K11_1_ROWS",
        note=(
            "K11-1 审定表：A7:A25 为跨表引用动态行，A26 为 SUM footer，"
            "全表 7 sheet / 190 公式 / 8 merge / 1 drawing，无 external link（OO 不会弹外链提示）。"
        ),
    ),
    "c24": ProbeDoc(
        key="c24",
        template_rel="backend/wp_templates/C/C24 会计分录 - 细节测试.xlsx",
        template_id="C24",
        managed_sheet="C24-0汇总表",
        first_data_row=8,
        last_data_row=20,
        footer_row=21,
        managed_last_col="H",
        uuid_col="N",
        edit_cell="B8",
        inject_table=False,
        table_name="",
        note=(
            "全平台 351 个模板里**唯一**含 chart 部件者（8 chart / 3 drawing / 1 media / 1 既有 Excel Table）"
            "⇒ 用来取证 instrumentation 与 OO 往返是否破坏 drawing/chart。"
        ),
    ),
}


# ---------------------------------------------------------------------------
# 通用工具（脱敏 / hash / 时间）
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_ref(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


_URL_FIELDS = ("url", "changesurl", "historyurl")
_SIGNED_QUERY_KEYS = {"md5", "token", "signature", "sig"}


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    pairs = []
    for raw in parts.query.split("&"):
        if "=" not in raw:
            pairs.append(raw)
            continue
        key, value = raw.split("=", 1)
        pairs.append(f"{key}={_digest_ref(value)}" if key.lower() in _SIGNED_QUERY_KEYS else f"{key}={value}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(pairs), parts.fragment))


def redact_payload(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key == "token" and isinstance(value, str):
                out[key] = _digest_ref(value)
            elif key in _URL_FIELDS and isinstance(value, str):
                out[key] = _redact_url(value)
            else:
                out[key] = redact_payload(value)
        return out
    if isinstance(obj, list):
        return [redact_payload(item) for item in obj]
    return obj


def _rewrite_download_host(url: str) -> str:
    base = urlsplit(OO_URL_FROM_HOST)
    cur = urlsplit(url)
    if not base.netloc or cur.netloc == base.netloc:
        return url
    return urlunsplit((base.scheme or cur.scheme, base.netloc, cur.path, cur.query, cur.fragment))


def _sign(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, OO_SECRET, algorithm="HS256")


def _col_index(letters: str) -> int:
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx


# ---------------------------------------------------------------------------
# instrumentation（zip 级定点注入；probe 级实现，生产版由 Task 17 承接）
# ---------------------------------------------------------------------------

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_GT_SYNC_REL_ID = "rIdGTSYNC"
_GT_TABLE_REL_ID = "rIdGTTBL1"
_GT_SYNC_SHEET_PART = "xl/worksheets/sheetGtSync.xml"
_GT_TABLE_PART = "xl/tables/tableGtRowId.xml"

_SHEET_TAIL_ORDER = ("extLst",)


class InstrumentationError(RuntimeError):
    """instrumentation 注入失败。禁止降级为「跳过该载体」。"""


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _gt_sync_sheet_xml(pairs: list[tuple[str, str]]) -> bytes:
    """自撰 hidden metadata sheet（inlineStr，不依赖共享字符串表）。"""
    rows = []
    for index, (key, value) in enumerate(pairs, start=1):
        rows.append(
            f'<row r="{index}">'
            f'<c r="A{index}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(key)}</t></is></c>'
            f'<c r="B{index}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(value)}</t></is></c>'
            f"</row>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<worksheet xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">'
        f'<dimension ref="A1:B{max(len(pairs), 1)}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="14.25"/>'
        '<cols><col min="1" max="1" width="34" customWidth="1"/>'
        '<col min="2" max="2" width="72" customWidth="1"/></cols>'
        f'<sheetData>{"".join(rows)}</sheetData>'
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        "</worksheet>"
    ).encode("utf-8")


def _table_xml(*, table_id: int, name: str, ref: str, column_count: int) -> bytes:
    """`headerRowCount=0` 的 Excel Table：不覆盖业务两级表头，也不需要在单元格里写列名。"""
    cols = "".join(
        f'<tableColumn id="{i}" name="GTCol{i}"/>' for i in range(1, column_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<table xmlns="{_MAIN_NS}" id="{table_id}" name="{name}" displayName="{name}" '
        f'ref="{ref}" headerRowCount="0" totalsRowShown="0">'
        f'<tableColumns count="{column_count}">{cols}</tableColumns>'
        '<tableStyleInfo showFirstColumn="0" showLastColumn="0" showRowStripes="0" showColumnStripes="0"/>'
        "</table>"
    ).encode("utf-8")


def _insert_before(text: str, needle: str, addition: str, *, what: str) -> str:
    idx = text.find(needle)
    if idx < 0:
        raise InstrumentationError(f"注入 {what} 失败：找不到锚点 {needle!r}")
    return text[:idx] + addition + text[idx:]


def _next_sheet_id(workbook_xml: str) -> int:
    ids = [int(m) for m in re.findall(r'<sheet [^>]*sheetId="(\d+)"', workbook_xml)]
    return (max(ids) + 1) if ids else 1


def _next_rel_number(rels_xml: str) -> int:
    nums = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels_xml)]
    return (max(nums) + 1) if nums else 1


def _sheet_part_for(workbook_xml: str, rels_xml: str, sheet_name: str) -> str:
    match = re.search(
        r'<sheet [^>]*name="' + re.escape(_xml_escape(sheet_name)) + r'"[^>]*r:id="(rId\d+)"',
        workbook_xml,
    )
    if not match:
        raise InstrumentationError(f"workbook.xml 中找不到 sheet {sheet_name!r}")
    rid = match.group(1)
    rel = re.search(r'Id="' + rid + r'"[^>]*Target="([^"]+)"', rels_xml)
    if not rel:
        raise InstrumentationError(f"workbook rels 中找不到 {rid}")
    target = rel.group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _sheet_id_for(workbook_xml: str, sheet_name: str) -> str:
    match = re.search(
        r'<sheet [^>]*name="' + re.escape(_xml_escape(sheet_name)) + r'"[^>]*?sheetId="(\d+)"',
        workbook_xml,
    )
    if not match:
        match = re.search(
            r'<sheet [^>]*sheetId="(\d+)"[^>]*name="' + re.escape(_xml_escape(sheet_name)) + r'"',
            workbook_xml,
        )
    if not match:
        raise InstrumentationError(f"取不到 sheet {sheet_name!r} 的 sheetId")
    return match.group(1)


def _add_uuid_cells(sheet_xml: str, doc: ProbeDoc, uuids: dict[int, str]) -> str:
    """把隐藏 UUID 列的 inlineStr 单元格逐行插到对应 `<row>` 末尾。"""
    for row_no, uuid_value in sorted(uuids.items()):
        cell = (
            f'<c r="{doc.uuid_col}{row_no}" t="inlineStr">'
            f'<is><t>{_xml_escape(uuid_value)}</t></is></c>'
        )
        open_match = re.search(rf'<row r="{row_no}"(?:\s[^>]*)?/>', sheet_xml)
        if open_match:  # 空行（自闭合）→ 展开成带 UUID 单元格的行
            raw = open_match.group(0)
            expanded = raw[:-2] + ">" + cell + "</row>"
            sheet_xml = sheet_xml.replace(raw, expanded, 1)
            continue
        open_match = re.search(rf'<row r="{row_no}"(?:\s[^>]*)?>', sheet_xml)
        if not open_match:
            raise InstrumentationError(f"sheet 中找不到第 {row_no} 行，无法写 row UUID")
        close_idx = sheet_xml.find("</row>", open_match.end())
        if close_idx < 0:
            raise InstrumentationError(f"第 {row_no} 行缺少 </row>")
        sheet_xml = sheet_xml[:close_idx] + cell + sheet_xml[close_idx:]
    return sheet_xml


def _hide_uuid_column(sheet_xml: str, doc: ProbeDoc) -> str:
    col_no = _col_index(doc.uuid_col)
    col = f'<col min="{col_no}" max="{col_no}" width="9" hidden="1" customWidth="1"/>'
    if "<cols>" in sheet_xml:
        return _insert_before(sheet_xml, "</cols>", col, what="hidden UUID col")
    return _insert_before(sheet_xml, "<sheetData", f"<cols>{col}</cols>", what="cols block")


def _attach_table_part(sheet_xml: str) -> str:
    block = f'<tableParts count="1"><tablePart r:id="{_GT_TABLE_REL_ID}"/></tableParts>'
    for tail in _SHEET_TAIL_ORDER:
        idx = sheet_xml.find(f"<{tail}")
        if idx >= 0:
            return sheet_xml[:idx] + block + sheet_xml[idx:]
    return _insert_before(sheet_xml, "</worksheet>", block, what="tableParts")


def instrument_workbook(source: bytes, doc: ProbeDoc, *, run_id: str) -> tuple[bytes, dict[str, Any]]:
    """把三类 identity 载体注入 workbook 副本，返回 (新字节, instrumentation manifest)。

    manifest 只声明「载体定义 + 已发布 template digest」，不含自身 UUID/hash，也不引用
    contract/bundle digest（Requirement 6.14）。
    """
    template_sha = _sha256_bytes(source)
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(__import__("io").BytesIO(source)) as zf:
        names = list(zf.namelist())
        for name in names:
            entries[name] = zf.read(name)

    workbook_xml = entries["xl/workbook.xml"].decode("utf-8")
    wb_rels_xml = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    content_types = entries["[Content_Types].xml"].decode("utf-8")

    managed_sheet_id = _sheet_id_for(workbook_xml, doc.managed_sheet)
    target_part = _sheet_part_for(workbook_xml, wb_rels_xml, doc.managed_sheet)
    if target_part not in entries:
        raise InstrumentationError(f"目标 sheet 部件不存在: {target_part}")

    uuids = {
        row: f"GTROW-{doc.template_id}-{row:04d}"
        for row in range(doc.first_data_row, doc.last_data_row + 1)
    }
    table_ref = f"A{doc.first_data_row}:{doc.uuid_col}{doc.last_data_row}"
    table_column_count = _col_index(doc.uuid_col)

    # ---- 载体 1：hidden `_GT_SYNC` sheet ----
    sync_pairs: list[tuple[str, str]] = [
        ("GT_SYNC_SCHEMA_VERSION", "1"),
        ("GT_IDENTITY_SCHEMA_VERSION", "1.0.0"),
        ("GT_INSTRUMENTATION_VERSION", "1.0.0"),
        ("GT_TEMPLATE_ID", doc.template_id),
        ("GT_TEMPLATE_SHA256", template_sha),
        ("GT_PROBE_RUN_ID", run_id),
        # 🔴 identity 只绑 sheetId（不可变），展示名仅作审计线索（Requirement 6.14）。
        ("GT_MANAGED_SHEET_ID", managed_sheet_id),
        ("GT_MANAGED_SHEET_NAME_AT_INSTRUMENTATION", doc.managed_sheet),
        ("GT_MANAGED_RANGE", f"A{doc.first_data_row}:{doc.managed_last_col}{doc.last_data_row}"),
        ("GT_FOOTER_ROW", str(doc.footer_row)),
        ("GT_ROW_UUID_COLUMN", doc.uuid_col),
        ("GT_ROW_UUID_FIRST_ROW", str(doc.first_data_row)),
        ("GT_ROW_UUID_LAST_ROW", str(doc.last_data_row)),
    ]
    if doc.inject_table:
        sync_pairs += [("GT_MANAGED_TABLE", doc.table_name), ("GT_MANAGED_TABLE_REF", table_ref)]
    entries[_GT_SYNC_SHEET_PART] = _gt_sync_sheet_xml(sync_pairs)

    new_sheet_id = _next_sheet_id(workbook_xml)
    workbook_xml = _insert_before(
        workbook_xml,
        "</sheets>",
        f'<sheet name="{GT_SYNC_SHEET_NAME}" sheetId="{new_sheet_id}" state="hidden" '
        f'r:id="{_GT_SYNC_REL_ID}"/>',
        what="hidden _GT_SYNC sheet 声明",
    )
    wb_rels_xml = _insert_before(
        wb_rels_xml,
        "</Relationships>",
        f'<Relationship Id="{_GT_SYNC_REL_ID}" '
        f'Type="{_REL_NS}/worksheet" Target="worksheets/sheetGtSync.xml"/>',
        what="_GT_SYNC 关系",
    )
    content_types = _insert_before(
        content_types,
        "</Types>",
        f'<Override PartName="/{_GT_SYNC_SHEET_PART}" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>',
        what="_GT_SYNC content type",
    )

    # ---- 载体 2：defined names（workbook 级 + sheet-local 各取证）----
    quoted = f"'{doc.managed_sheet}'" if re.search(r"[\s\-()]", doc.managed_sheet) else doc.managed_sheet
    sheet_index = [
        m for m in re.findall(r'<sheet [^>]*name="([^"]+)"', workbook_xml)
    ].index(_xml_escape(doc.managed_sheet))
    defined: list[tuple[str, str, str | None]] = [
        (
            f"GT_MANAGED_REGION_{doc.template_id}",
            f"{quoted}!$A${doc.first_data_row}:${doc.managed_last_col}${doc.last_data_row}",
            None,
        ),
        (f"GT_FOOTER_ANCHOR_{doc.template_id}", f"{quoted}!$A${doc.footer_row}", None),
        (f"GT_SYNC_ANCHOR_{doc.template_id}", f"{GT_SYNC_SHEET_NAME}!$A$1", None),
        (
            f"GT_ROW_UUID_RANGE_{doc.template_id}",
            f"{quoted}!${doc.uuid_col}${doc.first_data_row}:${doc.uuid_col}${doc.last_data_row}",
            str(sheet_index),
        ),
    ]
    nodes = "".join(
        f'<definedName name="{name}"'
        + (f' localSheetId="{scope}"' if scope is not None else "")
        + f">{_xml_escape(ref)}</definedName>"
        for name, ref, scope in defined
    )
    if "<definedNames>" in workbook_xml:
        workbook_xml = _insert_before(workbook_xml, "</definedNames>", nodes, what="defined names")
    else:
        workbook_xml = _insert_before(
            workbook_xml, "</sheets>", "", what="sheets 锚点"
        ).replace("</sheets>", f"</sheets><definedNames>{nodes}</definedNames>", 1)

    # ---- 载体 3：Excel Table + 隐藏 UUID 列 ----
    sheet_xml = entries[target_part].decode("utf-8")
    sheet_xml = _add_uuid_cells(sheet_xml, doc, uuids)
    sheet_xml = _hide_uuid_column(sheet_xml, doc)
    dim = re.search(r'<dimension ref="([A-Z]+\d+):([A-Z]+)(\d+)"/>', sheet_xml)
    if dim and _col_index(dim.group(2)) < _col_index(doc.uuid_col):
        sheet_xml = sheet_xml.replace(
            dim.group(0), f'<dimension ref="{dim.group(1)}:{doc.uuid_col}{dim.group(3)}"/>', 1
        )
    if doc.inject_table:
        existing_ids = [
            int(m)
            for name, blob in entries.items()
            if name.startswith("xl/tables/")
            for m in re.findall(r'<table [^>]*\bid="(\d+)"', blob.decode("utf-8", "replace"))
        ]
        table_id = (max(existing_ids) + 1) if existing_ids else 1
        entries[_GT_TABLE_PART] = _table_xml(
            table_id=table_id, name=doc.table_name, ref=table_ref, column_count=table_column_count
        )
        sheet_xml = _attach_table_part(sheet_xml)
        rels_part = (
            f"{target_part.rsplit('/', 1)[0]}/_rels/{target_part.rsplit('/', 1)[1]}.rels"
        )
        rel_node = (
            f'<Relationship Id="{_GT_TABLE_REL_ID}" Type="{_REL_NS}/table" '
            f'Target="../tables/tableGtRowId.xml"/>'
        )
        if rels_part in entries:
            entries[rels_part] = _insert_before(
                entries[rels_part].decode("utf-8"), "</Relationships>", rel_node, what="table 关系"
            ).encode("utf-8")
        else:
            entries[rels_part] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f"{rel_node}</Relationships>"
            ).encode("utf-8")
        content_types = _insert_before(
            content_types,
            "</Types>",
            f'<Override PartName="/{_GT_TABLE_PART}" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>',
            what="table content type",
        )
    entries[target_part] = sheet_xml.encode("utf-8")
    entries["xl/workbook.xml"] = workbook_xml.encode("utf-8")
    entries["xl/_rels/workbook.xml.rels"] = wb_rels_xml.encode("utf-8")
    entries["[Content_Types].xml"] = content_types.encode("utf-8")

    buf = __import__("io").BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in list(dict.fromkeys(list(entries))):
            out.writestr(name, entries[name])
    result = buf.getvalue()

    manifest = {
        "template_id": doc.template_id,
        "template_rel": doc.template_rel,
        "template_sha256": template_sha,
        "instrumentation_version": "1.0.0",
        "identity_schema_version": "1.0.0",
        "identity_carriers": (
            ["hidden_sheet", "defined_name", "hidden_uuid_column"]
            if doc.inject_table
            else ["hidden_sheet", "defined_name"]
        ),
        "managed_sheet_name_at_instrumentation": doc.managed_sheet,
        "managed_sheet_id": managed_sheet_id,
        "managed_range": f"A{doc.first_data_row}:{doc.managed_last_col}{doc.last_data_row}",
        "footer_row": doc.footer_row,
        "row_uuid_column": doc.uuid_col,
        "row_uuids": {str(k): v for k, v in sorted(uuids.items())},
        "managed_table": doc.table_name if doc.inject_table else None,
        "managed_table_ref": table_ref if doc.inject_table else None,
        "defined_names": {name: ref for name, ref, _ in defined},
        "defined_name_scopes": {
            name: (doc.managed_sheet if scope is not None else None) for name, _, scope in defined
        },
        "visible_equivalence_policy": "strict",
        "ignored_by_business_sheet_enumerators": [GT_SYNC_SHEET_NAME],
        "instrumented_sha256": _sha256_bytes(result),
        "instrumented_bytes": len(result),
    }
    return result, manifest


def expected_identity_inventory(manifest: dict[str, Any]) -> dict[str, Any]:
    """instrumentation manifest → Property 66 的期望 identity inventory。"""
    return {
        "hidden_sheet": {
            "present": True,
            "is_hidden": True,
            "required_keys": [
                "GT_SYNC_SCHEMA_VERSION",
                "GT_IDENTITY_SCHEMA_VERSION",
                "GT_INSTRUMENTATION_VERSION",
                "GT_TEMPLATE_ID",
                "GT_TEMPLATE_SHA256",
                "GT_MANAGED_SHEET_ID",
                "GT_ROW_UUID_COLUMN",
            ],
            "excluded_from_business_enumeration": True,
        },
        "defined_name": {
            "present": True,
            "names": sorted(manifest["defined_names"]),
            "count": len(manifest["defined_names"]),
        },
        "excel_table": (
            {"present": True, "table_name": manifest["managed_table"], "table_ref": manifest["managed_table_ref"]}
            if manifest["managed_table"]
            else {"present": False, "reason": "该文档未注入 Table 载体（只取证前两类 + 裸隐藏列）"}
        ),
        "hidden_uuid_column": {
            "present": True,
            "uuid_column_letter": manifest["row_uuid_column"],
            "uuid_column_hidden": True,
            "row_uuid_values": sorted(manifest["row_uuids"].values()),
            "row_uuid_count": len(manifest["row_uuids"]),
            "resolved_sheet_by": "sheet_id",
        },
    }


# ---------------------------------------------------------------------------
# 探针状态与 HTTP host
# ---------------------------------------------------------------------------


def inventory_kwargs_for(doc: ProbeDoc, manifest: dict[str, Any]) -> dict[str, Any]:
    """按 instrumentation manifest 构造 identity_inventory 的定位参数。

    🔴 `uuid_sheet_id` 必填、`uuid_sheet_name` 只作对照：Requirement 6.14 禁止 identity
    依赖 sheet 展示名，所以「改名后还能不能定位」这一格必须由 sheetId 路径回答。
    """
    return {
        "expected_table": manifest.get("managed_table") or None,
        "uuid_column_letter": manifest["row_uuid_column"],
        "uuid_sheet_id": manifest["managed_sheet_id"],
        "uuid_sheet_name": manifest["managed_sheet_name_at_instrumentation"],
    }


class ProbeState:
    def __init__(
        self,
        *,
        evidence_dir: Path,
        doc: ProbeDoc,
        staged: Path,
        doc_key: str,
        port: int,
        inventory_kwargs: dict[str, Any],
    ):
        self.evidence_dir = evidence_dir
        self.artifacts_dir = evidence_dir / "artifacts"
        self.doc = doc
        self.staged = staged
        self.doc_key = doc_key
        self.port = port
        self.inventory_kwargs = inventory_kwargs
        self.current_op = "baseline"
        self.lock = threading.Lock()
        self.seq = 0
        self.callbacks: list[dict[str, Any]] = []
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.doc_bytes = staged.read_bytes()
        self.callback_log = evidence_dir / "callbacks.jsonl"

    def record(self, entry: dict[str, Any]) -> None:
        with self.lock:
            self.seq += 1
            entry["seq"] = self.seq
            self.callbacks.append(entry)
            with self.callback_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


STATE: ProbeState | None = None

EDITOR_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Task5 Excel identity probe</title>
<style>html,body,#ph{{height:100%;margin:0}}#bar{{position:fixed;z-index:9;right:8px;top:8px;
background:#fff;border:1px solid #ccc;padding:4px 8px;font:12px/1.6 sans-serif}}</style></head>
<body><div id="bar">doc=<b>{doc}</b> key=<span id="k"></span> state=<span id="st">boot</span></div>
<div id="ph"></div>
<script src="{oo_url}/web-apps/apps/api/documents/api.js"></script>
<script>
const st = document.getElementById('st');
fetch('/config').then(r => r.json()).then(cfg => {{
  document.getElementById('k').textContent = cfg.config.document.key;
  cfg.config.events = {{
    onAppReady: () => st.textContent = 'app-ready',
    onDocumentReady: () => st.textContent = 'doc-ready',
    onError: e => st.textContent = 'error:' + JSON.stringify(e && e.data),
    onWarning: e => st.textContent = 'warning:' + JSON.stringify(e && e.data),
    onDocumentStateChange: e => st.textContent = e.data ? 'dirty' : 'saved',
  }};
  window.__docEditor = new DocsAPI.DocEditor('ph', cfg.config);
}}).catch(e => st.textContent = 'config-failed:' + e);
</script></body></html>
"""


def build_config(state: ProbeState) -> dict[str, Any]:
    base = f"http://{HOST_FROM_CONTAINER}:{state.port}"
    config = {
        "document": {
            "fileType": "xlsx",
            "key": state.doc_key,
            "title": f"task5_{state.doc.key}_probe.xlsx",
            "url": f"{base}/doc?key={state.doc_key}",
            "permissions": {"edit": True, "download": True, "print": True},
        },
        "documentType": "cell",
        "editorConfig": {
            "mode": "edit",
            "lang": "zh-CN",
            "callbackUrl": f"{base}/callback?probe=task5&doc={state.doc.key}",
            "user": {"id": "probe5", "name": "Task5 探针"},
            "customization": {"forcesave": True, "compactHeader": False},
        },
        "type": "desktop",
    }
    return {"config": {**config, "token": _sign(config)}, "oo_url": OO_URL_FROM_HOST}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("[probe5-http] " + (fmt % args) + "\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        assert STATE is not None
        parts = urlsplit(self.path)
        route = parts.path
        if route == "/health":
            self._json(200, {"ok": True, "doc_key": STATE.doc_key, "op": STATE.current_op})
        elif route == "/doc":
            self._send(
                200,
                STATE.doc_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        elif route == "/config":
            self._json(200, build_config(STATE))
        elif route == "/editor":
            self._send(
                200,
                EDITOR_HTML.format(doc=STATE.doc.key, oo_url=OO_URL_FROM_HOST).encode("utf-8"),
                "text/html; charset=utf-8",
            )
        elif route == "/state":
            self._json(
                200,
                {
                    "doc_key": STATE.doc_key,
                    "doc": STATE.doc.key,
                    "op": STATE.current_op,
                    "count": len(STATE.callbacks),
                    "callbacks": STATE.callbacks,
                },
            )
        else:
            self._json(404, {"error": "no such probe route", "path": route})

    def do_POST(self) -> None:  # noqa: N802
        assert STATE is not None
        parts = urlsplit(self.path)
        if parts.path == "/control/op":
            op = (parse_qs(parts.query).get("name") or ["baseline"])[0]
            if op not in OPERATIONS:
                self._json(400, {"error": "unknown op", "op": op, "known": list(OPERATIONS)})
                return
            with STATE.lock:
                STATE.current_op = op
            self._json(200, {"op": op})
            return
        if parts.path != "/callback":
            self._json(404, {"error": "no such probe route", "path": parts.path})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        entry: dict[str, Any] = {
            "ts": _now(),
            "op": STATE.current_op,
            "doc": STATE.doc.key,
            "doc_key_expected": STATE.doc_key,
            "query": parse_qs(parts.query),
            "raw_body_sha256": _sha256_bytes(raw),
            "raw_body_len": len(raw),
        }
        auth = self.headers.get("Authorization")
        entry["authorization_present"] = auth is not None
        if auth:
            token = auth[7:] if auth.lower().startswith("bearer ") else auth
            try:
                jwt.decode(token, OO_SECRET, algorithms=["HS256"])
                entry["jwt_verified"] = True
            except Exception as exc:  # noqa: BLE001 — 如实记录
                entry["jwt_verified"] = False
                entry["jwt_error"] = f"{type(exc).__name__}: {exc}"
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:  # noqa: BLE001
            entry["body_parse_error"] = f"{type(exc).__name__}: {exc}"
            STATE.record(entry)
            self._json(200, {"error": 0})
            return

        entry["status"] = body.get("status")
        entry["body_keys"] = sorted(body.keys())
        entry["body"] = redact_payload(body)
        entry["userdata"] = body.get("userdata")

        url = body.get("url")
        if url:
            fetch_url = _rewrite_download_host(url)
            try:
                req = urllib.request.Request(fetch_url, method="GET")
                with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 — 固定 OO 主机
                    data = resp.read()
                entry["artifact_bytes"] = len(data)
                entry["artifact_sha256"] = _sha256_bytes(data)
                name = (
                    f"{STATE.doc.key}_{STATE.current_op}_cb{STATE.seq + 1:02d}"
                    f"_status{body.get('status')}.xlsx"
                )
                (STATE.artifacts_dir / name).write_bytes(data)
                entry["artifact_file"] = f"artifacts/{name}"
                # 🔴 结构指纹采集失败必须记 ERROR 态（不得吞成「无 identity」）。
                try:
                    entry["identity_inventory"] = identity_inventory(
                        data, **STATE.inventory_kwargs
                    )
                    fp = structure_fingerprint(data)
                    entry["structure"] = {
                        "sheet_names": fp.sheet_names,
                        "hidden_sheet_names": fp.hidden_sheet_names,
                        "defined_name_count": len(fp.defined_names),
                        "table_count": len(fp.tables),
                        "protected_parts": {k: len(v) for k, v in fp.protected_parts.items()},
                        "aspect_digests": fp.aspect_digests(),
                        "collection_errors": fp.errors,
                    }
                except FingerprintError as exc:
                    entry["structure_error"] = f"ERROR FingerprintError: {exc}"
            except Exception as exc:  # noqa: BLE001 — 如实记录下载失败
                entry["artifact_error"] = f"ERROR {type(exc).__name__}: {exc}"
        STATE.record(entry)
        self._json(200, {"error": 0})


# ---------------------------------------------------------------------------
# Command Service / build info
# ---------------------------------------------------------------------------


def call_command_service(payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{OO_URL_FROM_HOST}/coauthoring/CommandService.ashx"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + _sign({"payload": payload})}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — 固定 OO 主机
            raw = resp.read()
            return {
                "http_status": resp.status,
                "elapsed_ms": round((time.time() - started) * 1000),
                "body": json.loads(raw.decode("utf-8")) if raw else None,
            }
    except urllib.error.HTTPError as exc:
        return {"http_status": exc.code, "body": exc.read().decode("utf-8", "replace")}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"ERROR {type(exc).__name__}: {exc}"}


def oo_build_info() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, path in (("healthcheck", "/healthcheck"), ("info", "/info/info.json")):
        try:
            with urllib.request.urlopen(OO_URL_FROM_HOST + path, timeout=10) as resp:  # noqa: S310
                out[name] = resp.read(4000).decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            out[name] = f"ERROR {type(exc).__name__}: {exc}"
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _staging_dir(evidence_dir: Path) -> Path:
    return evidence_dir / "staging"


def cmd_verify_source(args: argparse.Namespace) -> int:
    """核 `backend/wp_templates/` 源文件 sha256 未变（开工/收工各跑一次）。"""
    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {"stage": args.stage, "checked_at": _now(), "templates": {}, "lock_files": []}
    for doc in PROBE_DOCS.values():
        path = REPO_ROOT / doc.template_rel
        if not path.exists():
            out["templates"][doc.template_rel] = {"error": "ERROR missing"}
            continue
        data = path.read_bytes()
        out["templates"][doc.template_rel] = {"sha256": _sha256_bytes(data), "bytes": len(data)}
    out["lock_files"] = [
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in (REPO_ROOT / "backend" / "wp_templates").rglob("~$*")
    ]
    path = evidence_dir / f"source_template_sha_{args.stage}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    before = evidence_dir / "source_template_sha_before.json"
    if args.stage == "after" and before.exists():
        prev = json.loads(before.read_text(encoding="utf-8"))
        drift = [
            rel
            for rel, info in out["templates"].items()
            if prev["templates"].get(rel, {}).get("sha256") != info.get("sha256")
        ]
        print(json.dumps({"source_sha_drift": drift}, ensure_ascii=False))
        return 1 if drift else 0
    return 0


def cmd_instrument(args: argparse.Namespace) -> int:
    """复制真实模板到 staging 并注入三类载体，同时生成 visible-equivalence 报告。"""
    evidence_dir = Path(args.evidence_dir)
    staging = _staging_dir(evidence_dir)
    staging.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or f"task5-{int(time.time())}"
    report: dict[str, Any] = {"run_id": run_id, "generated_at": _now(), "docs": {}}
    exit_code = 0
    for key, doc in PROBE_DOCS.items():
        if args.doc and key != args.doc:
            continue
        source_path = REPO_ROOT / doc.template_rel
        source = source_path.read_bytes()
        before_path = staging / f"{key}_before.xlsx"
        after_path = staging / f"{key}_instrumented.xlsx"
        before_path.write_bytes(source)  # staging 副本，权威源保持只读
        try:
            instrumented, manifest = instrument_workbook(source, doc, run_id=run_id)
        except InstrumentationError as exc:
            report["docs"][key] = {"error": f"ERROR InstrumentationError: {exc}"}
            exit_code = 1
            continue
        after_path.write_bytes(instrumented)
        try:
            equivalence = visible_equivalence_report(
                source,
                instrumented,
                allow_added_hidden_columns={doc.managed_sheet: [doc.uuid_col]},
                allow_added_table_columns={},
                label_before="pre_instrumentation",
                label_after="post_instrumentation",
            )
            inventory = identity_inventory(instrumented, **inventory_kwargs_for(doc, manifest))
            pre_inventory = identity_inventory(source, **inventory_kwargs_for(doc, manifest))
        except FingerprintError as exc:
            report["docs"][key] = {"error": f"ERROR FingerprintError: {exc}"}
            exit_code = 1
            continue
        report["docs"][key] = {
            "template_rel": doc.template_rel,
            "template_sha256": _sha256_bytes(source),
            "instrumented_sha256": _sha256_bytes(instrumented),
            "note": doc.note,
            "manifest": manifest,
            "inventory_locator_kwargs": inventory_kwargs_for(doc, manifest),
            "expected_identity_inventory": expected_identity_inventory(manifest),
            "identity_inventory_before_instrumentation": pre_inventory,
            "actual_identity_inventory_after_instrumentation": inventory,
            "visible_equivalence": equivalence,
        }
        if not equivalence["equivalent"]:
            exit_code = 1
    (evidence_dir / "instrumentation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        key: {
            "equivalent": (info.get("visible_equivalence") or {}).get("equivalent"),
            "aspect_verdicts": (info.get("visible_equivalence") or {}).get("aspect_verdicts"),
            "error": info.get("error"),
        }
        for key, info in report["docs"].items()
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


def cmd_serve(args: argparse.Namespace) -> int:
    global STATE
    evidence_dir = Path(args.evidence_dir)
    doc = PROBE_DOCS[args.doc]
    staged = (
        Path(args.seed)
        if getattr(args, "seed", None)
        else _staging_dir(evidence_dir) / f"{args.doc}_instrumented.xlsx"
    )
    if not staged.exists():
        print(f"FATAL 尚未 instrument 或 seed 不存在: {staged}（先跑 instrument 子命令）")
        return 2
    report_path = evidence_dir / "instrumentation_report.json"
    if not report_path.exists():
        print(f"FATAL 缺少 instrumentation_report.json: {report_path}")
        return 2
    manifest = json.loads(report_path.read_text(encoding="utf-8"))["docs"][args.doc]["manifest"]
    doc_key = args.doc_key or f"t5{args.doc}{int(time.time())}"
    STATE = ProbeState(
        evidence_dir=evidence_dir,
        doc=doc,
        staged=staged,
        doc_key=doc_key,
        port=args.port,
        inventory_kwargs=inventory_kwargs_for(doc, manifest),
    )
    meta = {
        "probe": "task5-oo94-excel-identity",
        "doc": args.doc,
        "started_at": _now(),
        "oo_url_from_host": OO_URL_FROM_HOST,
        "host_for_oo": HOST_FROM_CONTAINER,
        "probe_port": args.port,
        "doc_key": doc_key,
        "template_rel": doc.template_rel,
        "staged_sha256": _sha256_bytes(STATE.doc_bytes),
        "operations": list(OPERATIONS),
        "oo_secret_ref": _digest_ref(OO_SECRET),
        "oo_build_endpoints": oo_build_info(),
    }
    (evidence_dir / f"run_meta_{args.doc}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"serving": True, "doc": args.doc, "doc_key": doc_key, "port": args.port},
                     ensure_ascii=False))
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
    return 0


def _probe_get(port: int, path: str) -> Any:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def cmd_mark(args: argparse.Namespace) -> int:
    req = urllib.request.Request(
        f"http://127.0.0.1:{args.port}/control/op?name={args.op}", data=b"", method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — 本机探针
        print(resp.read().decode("utf-8"))
    return 0


def cmd_command(args: argparse.Namespace) -> int:
    state = _probe_get(args.port, "/state")
    payload: dict[str, Any] = {"c": args.c, "key": state["doc_key"]}
    if args.userdata:
        payload["userdata"] = args.userdata
    result = call_command_service(payload)
    record = {"ts": _now(), "op": state["op"], "request": payload, "result": result}
    log = Path(args.evidence_dir) / "commands.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    state = _probe_get(args.port, "/state")
    summary = [
        {
            "seq": c.get("seq"),
            "op": c.get("op"),
            "status": c.get("status"),
            "artifact_sha256": (c.get("artifact_sha256") or "")[:16],
            "sheets": (c.get("structure") or {}).get("sheet_names"),
            "hidden": (c.get("structure") or {}).get("hidden_sheet_names"),
            "dn": (c.get("structure") or {}).get("defined_name_count"),
            "tables": (c.get("structure") or {}).get("table_count"),
            "errors": [k for k in ("artifact_error", "structure_error") if c.get(k)],
        }
        for c in state["callbacks"]
    ]
    print(json.dumps({"doc_key": state["doc_key"], "op": state["op"], "count": state["count"],
                      "summary": summary}, ensure_ascii=False, indent=2))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """按操作矩阵把 artifact 折成「操作 × 载体」实测表 + 与期望 inventory 的逐项判定。"""
    evidence_dir = Path(args.evidence_dir)
    instrumentation = json.loads((evidence_dir / "instrumentation_report.json").read_text(encoding="utf-8"))
    log = evidence_dir / "callbacks.jsonl"
    entries = [
        json.loads(line)
        for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else [])
        if line.strip()
    ]
    # callback 之外的 artifact（编辑器「文件→下载为 XLSX」走的是浏览器下载，不经 callback）
    # 也必须进矩阵，否则 `download` 这一格只剩关闭保存的 status 2，缺了真正的用户下载路径。
    orphan_specs = [
        {"artifact_file": f"artifacts/{path.name}", "op": "download", "doc": path.name.split("_")[0],
         "status": None, "seq": f"editor-saveas:{path.name}", "delivery": "editor_download_not_callback"}
        for path in sorted((evidence_dir / "artifacts").glob("*_editor_saveas.xlsx"))
    ]
    logged = {e.get("artifact_file") for e in entries}
    entries = entries + [o for o in orphan_specs if o["artifact_file"] not in logged]

    matrix: list[dict[str, Any]] = []
    for entry in entries:
        rel = entry.get("artifact_file")
        if not rel:
            continue
        path = evidence_dir / rel
        if not path.exists():
            matrix.append({"op": entry.get("op"), "doc": entry.get("doc"),
                           "error": f"ERROR artifact 缺失 {rel}"})
            continue
        doc_key = entry.get("doc") or "k11"
        doc = PROBE_DOCS[doc_key]
        expected = instrumentation["docs"][doc_key]["expected_identity_inventory"]
        manifest = instrumentation["docs"][doc_key]["manifest"]
        data = path.read_bytes()
        try:
            inv = identity_inventory(data, **inventory_kwargs_for(doc, manifest))
            fp = structure_fingerprint(data)
        except FingerprintError as exc:
            matrix.append({"op": entry.get("op"), "doc": doc_key,
                           "error": f"ERROR FingerprintError: {exc}"})
            continue
        row = {
            "op": entry.get("op"),
            "doc": doc_key,
            "seq": entry.get("seq"),
            "status": entry.get("status"),
            "delivery": entry.get("delivery", "oo_callback"),
            "artifact_file": rel,
            "artifact_sha256": _sha256_bytes(data),
            "sheet_names": fp.sheet_names,
            "hidden_sheet_names": fp.hidden_sheet_names,
            "managed_sheet_present": doc.managed_sheet in fp.sheet_names,
            "carriers": {
                "hidden_sheet": {
                    "present": inv["hidden_sheet"]["present"],
                    "is_hidden": inv["hidden_sheet"]["is_hidden"],
                    "pair_count": inv["hidden_sheet"]["pair_count"],
                    "missing_keys": [
                        k
                        for k in expected["hidden_sheet"]["required_keys"]
                        if k not in inv["hidden_sheet"]["pairs"]
                    ],
                    "excluded_from_business_enumeration": inv["hidden_sheet"][
                        "excluded_from_business_enumeration"
                    ],
                },
                "defined_name": {
                    "present": inv["defined_name"]["present"],
                    "count": inv["defined_name"]["count"],
                    "names": sorted(inv["defined_name"]["names"]),
                    "missing_names": [
                        n for n in expected["defined_name"]["names"] if n not in inv["defined_name"]["names"]
                    ],
                    "refs": inv["defined_name"]["names"],
                    "scopes": inv["defined_name"]["scopes"],
                },
                "excel_table": inv["excel_table"],
                "hidden_uuid_column": {
                    **inv["hidden_uuid_column"],
                    "missing_row_uuids": sorted(
                        v
                        for v in manifest["row_uuids"].values()
                        if v not in set(inv["hidden_uuid_column"]["row_uuids"].values())
                    ),
                    "added_row_uuids": sorted(
                        v
                        for v in inv["hidden_uuid_column"]["row_uuids"].values()
                        if v and v not in set(manifest["row_uuids"].values())
                    ),
                },
            },
            "protected_parts": {k: len(v) for k, v in fp.protected_parts.items()},
            "collection_errors": fp.errors + inv["errors"],
        }
        # 相对 instrumented 基线的可见等价（只对同一 doc 比）
        staged = _staging_dir(evidence_dir) / f"{doc_key}_instrumented.xlsx"
        if staged.exists():
            row["equivalence_vs_instrumented"] = visible_equivalence_report(
                staged.read_bytes(),
                data,
                allow_added_hidden_columns={doc.managed_sheet: [doc.uuid_col]},
                label_before="instrumented",
                label_after=f"after_{entry.get('op')}",
            )["aspect_verdicts"]
        matrix.append(row)
    out = {"generated_at": _now(), "operations_declared": list(OPERATIONS), "matrix": matrix}
    (evidence_dir / "operation_matrix.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(
        [
            {
                "doc": r.get("doc"),
                "op": r.get("op"),
                "delivery": r.get("delivery"),
                "status": r.get("status"),
                "hidden_sheet": (r.get("carriers") or {}).get("hidden_sheet", {}).get("present"),
                "gt_sync_missing_keys": (r.get("carriers") or {}).get("hidden_sheet", {}).get("missing_keys"),
                "dn_missing": (r.get("carriers") or {}).get("defined_name", {}).get("missing_names"),
                "table": (r.get("carriers") or {}).get("excel_table", {}).get("table_name"),
                "table_ref": (r.get("carriers") or {}).get("excel_table", {}).get("table_ref"),
                "sheet_id_anchor_holds": (r.get("carriers") or {})
                .get("hidden_uuid_column", {})
                .get("sheet_id_anchor_holds"),
                "uuid_n": (r.get("carriers") or {}).get("hidden_uuid_column", {}).get("row_uuid_count"),
                "uuid_dup": (r.get("carriers") or {}).get("hidden_uuid_column", {}).get("duplicate_row_uuids"),
                "uuid_missing": (r.get("carriers") or {}).get("hidden_uuid_column", {}).get("missing_row_uuids"),
                "protected": r.get("protected_parts"),
                "collection_errors": r.get("collection_errors"),
                "error": r.get("error"),
            }
            for r in matrix
        ],
        ensure_ascii=False,
        indent=1,
    ))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """对任意本地 xlsx 直接采一次结构指纹 + identity inventory（供离线核对）。"""
    path = Path(args.path)
    data = path.read_bytes()
    doc = PROBE_DOCS[args.doc]
    report_path = Path(args.evidence_dir) / "instrumentation_report.json"
    manifest = json.loads(report_path.read_text(encoding="utf-8"))["docs"][args.doc]["manifest"]
    payload = {
        "path": str(path),
        "sha256": _sha256_bytes(data),
        "identity_inventory": identity_inventory(data, **inventory_kwargs_for(doc, manifest)),
        "structure": structure_fingerprint(data).to_json(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:8000])
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def cmd_attribute(args: argparse.Namespace) -> int:
    """把「OO 自身归一化」与「instrumentation 影响」分开归因（Requirement 6.17 的控制组）。

    三条对比：
      A. 源模板 vs instrumented              → instrumentation 自身影响（期望 0 差异）
      B. 源模板 vs 源模板过 OO（控制组）      → 纯 OO 归一化规模
      C. instrumented vs instrumented 过 OO  → 实测规模（应与 B 逐项相等）
    B == C 且 A 全零，才能断言「OO 往返差异与 instrumentation 无关」。
    """
    evidence_dir = Path(args.evidence_dir)
    staging = _staging_dir(evidence_dir)
    artifacts = evidence_dir / "artifacts"
    doc = PROBE_DOCS[args.doc]
    paths = {
        "pristine": staging / f"{args.doc}_before.xlsx",
        "instrumented": staging / f"{args.doc}_instrumented.xlsx",
        "oo_pristine": artifacts / args.control_artifact,
        "oo_instrumented": artifacts / args.treated_artifact,
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(json.dumps({"error": f"ERROR 缺少归因输入: {missing}"}, ensure_ascii=False))
        return 2
    allow = {doc.managed_sheet: [doc.uuid_col]}
    cases = {
        "case_A_instrumentation_only": ("pristine", "instrumented", allow),
        "case_B_pristine_through_oo": ("pristine", "oo_pristine", {}),
        "case_C_instrumented_through_oo": ("instrumented", "oo_instrumented", allow),
    }
    report: dict[str, Any] = {
        "generated_at": _now(),
        "doc": args.doc,
        "inputs": {
            k: {"file": str(p.relative_to(evidence_dir)).replace("\\", "/"),
                "sha256": _sha256_bytes(p.read_bytes())}
            for k, p in paths.items()
        },
        "cases": {},
    }
    for name, (before_key, after_key, al) in cases.items():
        rep = visible_equivalence_report(
            paths[before_key].read_bytes(),
            paths[after_key].read_bytes(),
            allow_added_hidden_columns=al,
            label_before=before_key,
            label_after=after_key,
        )
        report["cases"][name] = {
            "before": before_key,
            "after": after_key,
            "aspect_verdicts": rep["aspect_verdicts"],
            "diff_counts": {k: rep["aspects"][k].get("diff_count") for k in rep["aspects"]},
            "style_first_diffs": rep["aspects"]["styles"]["first_diffs"][:5],
            "protected_first_diffs": rep["aspects"]["protected_parts"]["first_diffs"][:5],
            "value_first_diffs": rep["aspects"]["business_values"]["first_diffs"][:5],
            "collection_errors": rep["collection_errors"],
        }
    counts_b = report["cases"]["case_B_pristine_through_oo"]["diff_counts"]
    counts_c = report["cases"]["case_C_instrumented_through_oo"]["diff_counts"]
    counts_a = report["cases"]["case_A_instrumentation_only"]["diff_counts"]
    report["conclusion"] = {
        "instrumentation_contributes_zero_diffs": all(
            (v or 0) == 0 for v in counts_a.values()
        ),
        "oo_normalization_identical_with_and_without_instrumentation": counts_b == counts_c,
        "meaning": (
            "A 全零且 B==C ⇒ OO 往返的全部差异由 OO 自身重序列化造成，instrumentation 贡献为 0。"
        ),
    }
    (evidence_dir / "oo_normalization_attribution.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"cases": {k: v["diff_counts"] for k, v in report["cases"].items()},
                      "conclusion": report["conclusion"]}, ensure_ascii=False, indent=2))
    return 0 if all(report["conclusion"][k] for k in
                    ("instrumentation_contributes_zero_diffs",
                     "oo_normalization_identical_with_and_without_instrumentation")) else 1


def cmd_build(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    import subprocess

    dpkg = subprocess.run(
        ["docker", "exec", "audit-onlyoffice", "dpkg", "-l", "onlyoffice-documentserver"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    payload = {
        "captured_at": _now(),
        "dpkg_onlyoffice_documentserver": " ".join(dpkg.stdout.split()),
        "endpoints": oo_build_info(),
    }
    (evidence_dir / "oo_build.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="真实 OO 9.4 Excel identity 黑盒探针（Task 5）")
    ap.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("verify-source", help="核 backend/wp_templates 源文件 sha256")
    p.add_argument("--stage", required=True, choices=["before", "after"])
    p.set_defaults(func=cmd_verify_source)

    p = sub.add_parser("instrument", help="复制到 staging 并注入三类载体 + 等价报告")
    p.add_argument("--doc", default=None, choices=sorted(PROBE_DOCS))
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_instrument)

    p = sub.add_parser("serve", help="启动 document host + callback collector")
    p.add_argument("--doc", required=True, choices=sorted(PROBE_DOCS))
    p.add_argument("--doc-key", default=None)
    p.add_argument(
        "--seed",
        default=None,
        help="用指定 xlsx 作为宿主文档（reopen 操作用：喂上一轮 OO 产出的 artifact）",
    )
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("mark", help="标记当前操作（写入后续 callback 的 op 字段）")
    p.add_argument("--op", required=True, choices=list(OPERATIONS))
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("command", help="调 OO Command Service")
    p.add_argument("--c", required=True, choices=["forcesave", "info", "version", "drop"])
    p.add_argument("--userdata", default=None)
    p.set_defaults(func=cmd_command)

    p = sub.add_parser("state", help="打印已收集 callback 摘要")
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("analyze", help="生成 operation_matrix.json")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("snapshot", help="对本地 xlsx 采结构指纹")
    p.add_argument("--path", required=True)
    p.add_argument("--doc", default="k11", choices=sorted(PROBE_DOCS))
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("attribute", help="OO 归一化 vs instrumentation 的归因控制组")
    p.add_argument("--doc", default="k11", choices=sorted(PROBE_DOCS))
    p.add_argument("--control-artifact", default="k11_baseline_cb02_status6.xlsx",
                   help="源模板（未 instrument）过一次 OO 的 artifact")
    p.add_argument("--treated-artifact", default="k11_edit_cb02_status6.xlsx",
                   help="instrumented 过一次 OO 的 artifact")
    p.set_defaults(func=cmd_attribute)

    p = sub.add_parser("build", help="记录 OO build 号")
    p.set_defaults(func=cmd_build)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
