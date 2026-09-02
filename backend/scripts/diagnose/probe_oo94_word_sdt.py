"""真实 OnlyOffice 9.4 Word tagged SDT 载体黑盒探针（spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 6）

目的（design.md §Word SDT Engine / §OO 9.4 pilot 门 / Requirement 7.2 7.5 7.6 14.4 14.16 / Property 33）：
在建 Word engine 之前，用**真实 OO 9.4 容器 + 平台自有真实模板的隔离副本**取证
tagged SDT 载体经真实编辑器往返后「tag 集合 / 层级 / row_uuid 集合是否不减少」。

只回答载体保留能力这一个问题。**不**产出生产 extractor、**不**声明缺 tag fail-closed
已实现、**不**声明 operation 回写已实现（分别由 Tasks 59/61/68 承接）。
禁止 paragraph-index / regex fallback —— 本探针连读值都只走 `w:tag`。

载体候选（design §Identity probe 决策门 Word 行）：
  1. `field_sdt_inline`  —— run 级 SDT（段内），含跨 run、同段多实例、同 stable key 多实例
  2. `field_sdt_block`   —— block 级 SDT（包整段），内层再嵌 inline SDT ⇒ 取证**层级**
  3. `row_sdt`           —— row 级 SDT（包 `w:tr`），tag 内含稳定 `row_uuid`
  4. `sdt_external_body` —— SDT 外正文（Word-only 自由正文）是否逐字保留

候选锚点（与载体分开裁决；这一栏专门用来**证伪**不稳定锚点）：
  - `w_tag`            —— 正式协议锚点
  - `sdt_id`           —— `w:sdtPr/w:id`，OO 是否重编号
  - `alias_display_name` —— `w:sdtPr/w:alias`，展示名是否保留/可否当锚点
  - `paragraph_index`  —— 段落绝对序号（Requirement 7.1 明令禁止；本探针给出证伪数据）

🔴 硬约束：
  - `backend/wp_templates/` 是运行时权威源，**只读**。注入只作用于 evidence/staging 副本；
    `verify-source` 在开工/收工各核一次源文件 sha256。
  - 不接通生产 callback、不写业务库、不改 OO 容器配置、不建生产 Word engine。
  - 采集异常一律记 ERROR 态（`errors` 数组 / `*_error` 字段），禁止吞成「无 tag」。
  - 注入**不加** `<w:lock>`：加锁会让 OO 无法删除 SDT，等于替载体作弊；本探针要的是
    「OO 在无保护下是否自发保留 tag」。该事实写进 manifest 的 `lock_policy`。

用法（Windows，仓库根）：
    python backend/scripts/diagnose/probe_oo94_word_sdt.py verify-source --stage before
    python backend/scripts/diagnose/probe_oo94_word_sdt.py instrument
    python backend/scripts/diagnose/probe_oo94_word_sdt.py serve --doc f222
    python backend/scripts/diagnose/probe_oo94_word_sdt.py mark --op edit_in_sdt
    python backend/scripts/diagnose/probe_oo94_word_sdt.py command --c forcesave --userdata op-edit
    python backend/scripts/diagnose/probe_oo94_word_sdt.py state
    python backend/scripts/diagnose/probe_oo94_word_sdt.py snapshot --path <docx> --doc f222
    python backend/scripts/diagnose/probe_oo94_word_sdt.py analyze
    python backend/scripts/diagnose/probe_oo94_word_sdt.py verify-source --stage after
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from jose import jwt

REPO_ROOT = Path(__file__).resolve().parents[3]

SPEC_DIR = (
    REPO_ROOT
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
DEFAULT_EVIDENCE_DIR = SPEC_DIR / "evidence" / "task6-oo94-word-tagged-sdt"

# Task 4/5 实测环境事实（build 9.4.0-129 / JWT_ENABLED=true / header Authorization / inBody=false）。
OO_SECRET = os.environ.get("PROBE_OO_SECRET", "onlyoffice-dev-secret-2026")
OO_URL_FROM_HOST = os.environ.get("PROBE_OO_URL", "http://localhost:8080")
HOST_FROM_CONTAINER = os.environ.get("PROBE_HOST_FOR_OO", "host.docker.internal")
#: Task 4 用 9991、Task 5 用 9993，本探针换 9995 避免残留冲突。
DEFAULT_PORT = 9995

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

#: Task 6 操作矩阵（顺序即执行顺序；`reopen` 必须最后）。
#:
#: `edit_outside_sdt` 单独成一格：Requirement 7.3 的自由正文保留是 Word 载体的**另一半**，
#: 只测 SDT 内编辑会漏掉「OO 改了 SDT 外正文后 tag 是否仍在」这条。
OPERATIONS = (
    "baseline",
    "edit_in_sdt",
    "edit_outside_sdt",
    "insert_paragraph",
    "delete_paragraph",
    "insert_row",
    "delete_row",
    "forcesave",
    "download",
    "reopen",
)

#: 每个探针文档**声明**要跑的操作子集（未声明的格子在矩阵里是 `not_applicable`，
#: 不是「漏做」）。F2-22/F2-23 零表格 ⇒ 行操作不适用，这一事实由 manifest 自证。
DOC_OPERATIONS: dict[str, tuple[str, ...]] = {
    "f222": (
        "baseline",
        "edit_in_sdt",
        "edit_outside_sdt",
        "insert_paragraph",
        "delete_paragraph",
        "forcesave",
        "download",
        "reopen",
    ),
    "f223": ("baseline", "edit_in_sdt", "forcesave", "download", "reopen"),
    "b30112": (
        "baseline",
        "edit_in_sdt",
        "insert_row",
        "delete_row",
        "forcesave",
        "download",
        "reopen",
    ),
}


# ---------------------------------------------------------------------------
# 注入声明（隔离副本；生产迁移工具由 Task 59/61 承接）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldInjection:
    """一条 field SDT 注入声明。

    :param inj_id: 注入编号（同 doc 内唯一），同时作为 seed 文本的一部分
    :param paragraph_index: 目标段落在 `w:body` 直接子 `w:p` 序列里的 0-based 序号
    :param target_text: 段内要被包进 SDT 的原文子串（`${token}` 或标签片段）
    :param stable_field_key: contract 的 stable field key（进 tag）
    :param scenario: 该注入取证的 Requirement 7.5 场景
    :param run_split: 把 seed 值切成几个 run 放进同一个 sdtContent（>1 即跨 run）
    :param wrap_block: True 时额外把整段包一层 block SDT（内层仍是 inline SDT）⇒ 层级
    :param alias: 是否写 `w:alias`（只给部分注入写，用来测展示名锚点）
    """

    inj_id: str
    paragraph_index: int
    target_text: str
    stable_field_key: str
    scenario: str
    run_split: int = 1
    wrap_block: bool = False
    alias: str = ""


@dataclass(frozen=True)
class RowInjection:
    """一条 row SDT 注入声明（包住 `w:tr`，tag 内含 row_uuid）。

    :param inj_id: 注入编号
    :param table_index: 目标表在 `w:body` 里的 0-based 序号
    :param row_index: 目标行在该表 `w:tr` 序列里的 0-based 序号
    :param cell_index: 行内要额外注入 inline field SDT 的单元格 0-based 序号
    :param row_field_key: 行内字段的 stable field key 后缀
    """

    inj_id: str
    table_index: int
    row_index: int
    cell_index: int
    row_field_key: str


@dataclass(frozen=True)
class ProbeDoc:
    key: str
    #: `backend/wp_templates/` 下的相对路径（**只读权威源**）
    template_rel: str
    wp_code: str
    contract_id: str
    fields: tuple[FieldInjection, ...]
    rows: tuple[RowInjection, ...] = ()
    note: str = ""


#: F2-22 存货监盘计划：Requirement 7.6 指定的 Word pilot。
#: 实测事实（本探针 survey）：0 个 `w:tbl` / 0 个 `w:tr` / 0 个既有 SDT，
#: 33 段全是单 run `${token}` 段落 ⇒ 行载体在此文档上**不可取证**（见 findings.md）。
_F222_FIELDS = (
    FieldInjection(
        inj_id="F01",
        paragraph_index=6,
        target_text="${purpose}",
        stable_field_key="plan/purpose",
        scenario="single_run",
        alias="监盘目的",
    ),
    FieldInjection(
        inj_id="F02",
        paragraph_index=8,
        target_text="${scope}",
        stable_field_key="plan/scope",
        scenario="cross_run",
        run_split=3,
    ),
    FieldInjection(
        inj_id="F03",
        paragraph_index=4,
        target_text="${entityName}",
        stable_field_key="plan/entity_name",
        scenario="same_paragraph_multi+duplicate_instance",
    ),
    FieldInjection(
        inj_id="F04",
        paragraph_index=4,
        target_text="${bsDate}",
        stable_field_key="plan/bs_date",
        scenario="same_paragraph_multi",
    ),
    FieldInjection(
        inj_id="F05",
        paragraph_index=1,
        target_text="${entityName}",
        stable_field_key="plan/entity_name",
        scenario="duplicate_instance",
    ),
    FieldInjection(
        inj_id="F06",
        paragraph_index=10,
        target_text="${warehouses}",
        stable_field_key="plan/warehouses",
        scenario="nested_block_over_inline",
        wrap_block=True,
        alias="监盘地点",
    ),
    FieldInjection(
        inj_id="F07",
        paragraph_index=14,
        target_text="${auditors}",
        stable_field_key="plan/auditors",
        scenario="inline_with_preserved_label_prefix",
    ),
    FieldInjection(
        inj_id="F08",
        paragraph_index=26,
        target_text="${requirements}",
        stable_field_key="plan/requirements",
        scenario="single_run",
    ),
)

_F223_FIELDS = (
    FieldInjection(
        inj_id="G01",
        paragraph_index=6,
        target_text="${purpose}",
        stable_field_key="summary/purpose",
        scenario="single_run",
        alias="监盘目的",
    ),
    FieldInjection(
        inj_id="G02",
        paragraph_index=12,
        target_text="${countDate}",
        stable_field_key="summary/count_date",
        scenario="cross_run",
        run_split=2,
    ),
    FieldInjection(
        inj_id="G03",
        paragraph_index=25,
        target_text="${conclusionBlock}",
        stable_field_key="summary/conclusion",
        scenario="nested_block_over_inline",
        wrap_block=True,
    ),
)

#: B30-11-2 内部控制缺陷汇总与评估：tbl0 = 1 表头 + 3 个结构相同的空数据行（10 列），
#: 平台内少见的**干净重复行**表 ⇒ 用来取证 row 级 SDT + row_uuid（Requirement 7.2）。
_B30112_FIELDS = (
    FieldInjection(
        inj_id="H01",
        paragraph_index=1,
        target_text="内部控制缺陷汇总与评估",
        stable_field_key="deficiencies/title",
        scenario="single_run_outside_table",
    ),
)

_B30112_ROWS = (
    RowInjection(inj_id="R01", table_index=0, row_index=1, cell_index=1, row_field_key="deficiency"),
    RowInjection(inj_id="R02", table_index=0, row_index=2, cell_index=1, row_field_key="deficiency"),
    RowInjection(inj_id="R03", table_index=0, row_index=3, cell_index=1, row_field_key="deficiency"),
)


PROBE_DOCS: dict[str, ProbeDoc] = {
    "f222": ProbeDoc(
        key="f222",
        template_rel="backend/wp_templates/F/F2-22 存货监盘计划.docx",
        wp_code="F2-22",
        contract_id="f2.stocktake.plan",
        fields=_F222_FIELDS,
        rows=(),
        note=(
            "Requirement 7.6 指定的 Word pilot。实测 0 表格 / 0 既有 SDT / 33 段单 run "
            "${token} ⇒ field 载体的全部 7.5 场景都能在此取证，但 row 载体不可取证。"
        ),
    ),
    "f223": ProbeDoc(
        key="f223",
        template_rel="backend/wp_templates/F/F2-23 存货监盘小结.docx",
        wp_code="F2-23",
        contract_id="f2.stocktake.summary",
        fields=_F223_FIELDS,
        rows=(),
        note=(
            "Requirement 7.6 的第二个 pilot 文档。作用是证明 field 载体结论不是单文档偶然，"
            "只跑 7.6 明列的 打开/编辑/forcesave/callback/重开 五步。"
        ),
    ),
    "b30112": ProbeDoc(
        key="b30112",
        template_rel="backend/wp_templates/B/B30-11-2 内部控制缺陷汇总与评估.docx",
        wp_code="B30-11-2",
        contract_id="b30.11.2.deficiencies",
        fields=_B30112_FIELDS,
        rows=_B30112_ROWS,
        note=(
            "F2-22/F2-23 零表格 ⇒ Requirement 7.2 的 row-level SDT + row_uuid 必须换一个"
            "真有重复行的平台模板取证。tbl0 = 表头 + 3 个同构空数据行（10 列）。"
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
        pairs.append(
            f"{key}={_digest_ref(value)}" if key.lower() in _SIGNED_QUERY_KEYS else f"{key}={value}"
        )
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


# ---------------------------------------------------------------------------
# SDT 注入（zip + 字符串级定点手术；design 明令「不得用 python-docx 重建整文档」）
# ---------------------------------------------------------------------------


class InjectionError(RuntimeError):
    """SDT 注入失败。禁止降级为「跳过该载体」。"""


class InventoryError(RuntimeError):
    """tag inventory 采集失败。必须记 ERROR 态，禁止当成「无 tag」。"""


_P_RE = re.compile(r"<w:p(?: [^>]*)?>.*?</w:p>|<w:p(?: [^>]*)?/>", re.S)
_TBL_RE = re.compile(r"<w:tbl>.*?</w:tbl>", re.S)
_TR_RE = re.compile(r"<w:tr(?: [^>]*)?>.*?</w:tr>", re.S)
_TC_RE = re.compile(r"<w:tc>.*?</w:tc>", re.S)
_R_RE = re.compile(r"<w:r(?: [^>]*)?>.*?</w:r>", re.S)
_RPR_RE = re.compile(r"<w:rPr>.*?</w:rPr>", re.S)
_T_RE = re.compile(r"<w:t(?: [^>]*)?>(.*?)</w:t>", re.S)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _sdt_numeric_id(tag: str) -> int:
    """`w:id` 由 tag 派生（确定性），便于事后判断 OO 是否重编号。"""
    return int(hashlib.sha256(tag.encode("utf-8")).hexdigest()[:7], 16) % 900_000_000 + 1000


def _sdt_pr(tag: str, *, alias: str = "") -> str:
    parts = [f'<w:tag w:val="{_xml_escape(tag)}"/>', f'<w:id w:val="{_sdt_numeric_id(tag)}"/>']
    if alias:
        parts.insert(0, f'<w:alias w:val="{_xml_escape(alias)}"/>')
    # 🔴 不写 <w:lock>：见模块 docstring 的 lock_policy 说明。
    return "<w:sdtPr>" + "".join(parts) + "</w:sdtPr>"


def _wrap_sdt(inner: str, tag: str, *, alias: str = "") -> str:
    return f"<w:sdt>{_sdt_pr(tag, alias=alias)}<w:sdtContent>{inner}</w:sdtContent></w:sdt>"


def _make_runs(text: str, rpr: str, *, split: int) -> str:
    """把 seed 文本切成 `split` 个 run（>1 用来取证跨 run 读写）。"""
    split = max(1, min(split, len(text)))
    size = len(text) // split
    chunks = [text[i * size : (i + 1) * size] for i in range(split - 1)]
    chunks.append(text[(split - 1) * size :])
    return "".join(
        f'<w:r>{rpr}<w:t xml:space="preserve">{_xml_escape(c)}</w:t></w:r>' for c in chunks if c
    )


def _plain_run(text: str, rpr: str) -> str:
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_xml_escape(text)}</w:t></w:r>'


def _body_paragraph_spans(doc: str) -> list[tuple[int, int]]:
    """`w:body` 直接子 `w:p` 的 span（排除表格内段落）。"""
    body_start = doc.index("<w:body>") + len("<w:body>")
    body_end = doc.index("</w:body>")
    table_spans = [(m.start(), m.end()) for m in _TBL_RE.finditer(doc)]
    out: list[tuple[int, int]] = []
    for m in _P_RE.finditer(doc, body_start, body_end):
        if any(a <= m.start() < b for a, b in table_spans):
            continue
        out.append((m.start(), m.end()))
    return out


def _paragraph_edit(
    doc: str, paragraph_index: int, injections: list[FieldInjection], *, contract_id: str
) -> tuple[tuple[int, int], str, list[dict[str, Any]]]:
    """算出**同一段**全部 field 注入的 (替换 span, 新段 XML, 记录列表)。不落盘。

    🔴 必须按段批量处理，不能一条条独立算 span：F2-22 的 p04 一个 run 里就有
    `${entityName}` 与 `${bsDate}` 两个 token（Requirement 7.5 的「同段多 token」正是
    这种形态），逐条算会得到两个重叠 span 而互相吞掉。
    """
    spans = _body_paragraph_spans(doc)
    if paragraph_index >= len(spans):
        raise InjectionError(
            f"paragraph_index={paragraph_index} 越界（body 段落数 {len(spans)}）"
        )
    p_start, p_end = spans[paragraph_index]
    para = doc[p_start:p_end]

    pending = {inj.target_text: inj for inj in injections}
    if len(pending) != len(injections):
        raise InjectionError(
            f"段 {paragraph_index} 有重复 target_text —— 同段同 token 无法区分注入目标"
        )
    records: list[dict[str, Any]] = []
    new_para_pieces: list[str] = []
    cursor = 0

    for rm in _R_RE.finditer(para):
        run_xml = rm.group(0)
        t_m = _T_RE.search(run_xml)
        if t_m is None:
            continue
        full_text = t_m.group(1)
        hits = sorted(
            (full_text.index(tok), tok) for tok in pending if tok in full_text
        )
        if not hits:
            continue
        rpr_m = _RPR_RE.search(run_xml)
        rpr = rpr_m.group(0) if rpr_m else ""

        pieces: list[str] = []
        pos = 0
        for idx, tok in hits:
            inj = pending.pop(tok)
            if idx > pos:
                pieces.append(_plain_run(full_text[pos:idx], rpr))
            seed = f"GT-{inj.inj_id}-SEED"
            tag = f"gt:field:{contract_id}:{inj.stable_field_key}"
            pieces.append(
                _wrap_sdt(_make_runs(seed, rpr, split=inj.run_split), tag, alias=inj.alias)
            )
            records.append(
                {
                    "inj_id": inj.inj_id,
                    "level": "inline",
                    "tag": tag,
                    "alias": inj.alias,
                    "sdt_id": _sdt_numeric_id(tag),
                    "stable_field_key": inj.stable_field_key,
                    "scenario": inj.scenario,
                    "seed_text": seed,
                    "run_split": inj.run_split,
                    "paragraph_index_at_injection": paragraph_index,
                    "replaced_token": tok,
                    "wrap_block": inj.wrap_block,
                }
            )
            pos = idx + len(tok)
        if pos < len(full_text):
            pieces.append(_plain_run(full_text[pos:], rpr))

        new_para_pieces.append(para[cursor : rm.start()])
        new_para_pieces.append("".join(pieces))
        cursor = rm.end()

    if pending:
        raise InjectionError(
            f"段 {paragraph_index} 内找不到含 {sorted(pending)} 的 run"
        )
    new_para_pieces.append(para[cursor:])
    new_para = "".join(new_para_pieces)

    # block SDT：包整段（内层 inline SDT 不变）⇒ 制造 depth=2 的层级
    block_injs = [inj for inj in injections if inj.wrap_block]
    if len(block_injs) > 1:
        raise InjectionError(f"段 {paragraph_index} 声明了多个 wrap_block —— 层级会不确定")
    if block_injs:
        inj = block_injs[0]
        block_tag = f"gt:block:{contract_id}:{inj.stable_field_key}"
        new_para = _wrap_sdt(new_para, block_tag, alias=inj.alias)
        for rec in records:
            if rec["inj_id"] == inj.inj_id:
                rec["block_tag"] = block_tag
                rec["block_sdt_id"] = _sdt_numeric_id(block_tag)
                rec["level"] = "inline_inside_block"
    return (p_start, p_end), new_para, records


def _row_edit(
    doc: str, inj: RowInjection, *, contract_id: str, row_uuid: str
) -> tuple[tuple[int, int], str, dict[str, Any]]:
    """算出一条 row 注入的 (替换 span, 新 XML, 记录)。不落盘。"""
    tables = list(_TBL_RE.finditer(doc))
    if inj.table_index >= len(tables):
        raise InjectionError(f"{inj.inj_id}: table_index={inj.table_index} 越界（表数 {len(tables)}）")
    tm = tables[inj.table_index]
    tbl = tm.group(0)
    rows = list(_TR_RE.finditer(tbl))
    if inj.row_index >= len(rows):
        raise InjectionError(f"{inj.inj_id}: row_index={inj.row_index} 越界（行数 {len(rows)}）")
    rm = rows[inj.row_index]
    tr = rm.group(0)

    cells = list(_TC_RE.finditer(tr))
    if inj.cell_index >= len(cells):
        raise InjectionError(f"{inj.inj_id}: cell_index={inj.cell_index} 越界（单元格数 {len(cells)}）")
    cm = cells[inj.cell_index]
    cell = cm.group(0)
    cell_paras = list(_P_RE.finditer(cell))
    if not cell_paras:
        raise InjectionError(f"{inj.inj_id}: 目标单元格无 w:p，无法放 inline SDT")
    cp = cell_paras[0]
    cell_para = cp.group(0)

    seed = f"GT-{inj.inj_id}-SEED"
    field_tag = f"gt:field:{contract_id}:rows/{row_uuid}/{inj.row_field_key}"
    inner = _make_runs(seed, "", split=1)
    field_sdt = _wrap_sdt(inner, field_tag)
    # 把 inline SDT 插到该段最后一个 </w:p> 之前（段落属性等原样保留）
    insert_at = cell_para.rindex("</w:p>")
    new_cell_para = cell_para[:insert_at] + field_sdt + cell_para[insert_at:]
    new_cell = cell[: cp.start()] + new_cell_para + cell[cp.end() :]
    new_tr = tr[: cm.start()] + new_cell + tr[cm.end() :]

    row_tag = f"gt:row:{contract_id}:rows:{row_uuid}"
    row_sdt = _wrap_sdt(new_tr, row_tag)

    abs_start = tm.start() + rm.start()
    abs_end = tm.start() + rm.end()
    record = {
        "inj_id": inj.inj_id,
        "level": "row",
        "row_tag": row_tag,
        "row_sdt_id": _sdt_numeric_id(row_tag),
        "row_uuid": row_uuid,
        "field_tag": field_tag,
        "field_sdt_id": _sdt_numeric_id(field_tag),
        "seed_text": seed,
        "table_index_at_injection": inj.table_index,
        "row_index_at_injection": inj.row_index,
        "cell_index_at_injection": inj.cell_index,
        "scenario": "row_level_sdt_with_row_uuid",
    }
    return (abs_start, abs_end), row_sdt, record


def _stable_row_uuid(doc_key: str, inj_id: str, run_id: str) -> str:
    """确定性 row_uuid（uuid4 形态字符串，但由 run_id 派生以便复现）。"""
    h = hashlib.sha256(f"{run_id}|{doc_key}|{inj_id}".encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def inject_sdt(source: bytes, doc: ProbeDoc, *, run_id: str) -> tuple[bytes, dict[str, Any]]:
    """在隔离副本上注入 field/row SDT，返回 (新 docx 字节, manifest)。"""
    with zipfile.ZipFile(io_bytes(source)) as z:
        parts = {n: z.read(n) for n in z.namelist()}
        order = list(z.namelist())
    if "word/document.xml" not in parts:
        raise InjectionError("缺少 word/document.xml")
    xml = parts["word/document.xml"].decode("utf-8")

    edits: list[tuple[tuple[int, int], str]] = []
    field_records: list[dict[str, Any]] = []
    row_records: list[dict[str, Any]] = []

    by_paragraph: dict[int, list[FieldInjection]] = {}
    for inj in doc.fields:
        by_paragraph.setdefault(inj.paragraph_index, []).append(inj)
    for p_idx, injs in sorted(by_paragraph.items()):
        span, new_xml, recs = _paragraph_edit(xml, p_idx, injs, contract_id=doc.contract_id)
        edits.append((span, new_xml))
        field_records.extend(recs)
    for inj in doc.rows:
        uuid = _stable_row_uuid(doc.key, inj.inj_id, run_id)
        span, new_xml, rec = _row_edit(xml, inj, contract_id=doc.contract_id, row_uuid=uuid)
        edits.append((span, new_xml))
        row_records.append(rec)

    # 重叠检查：同段两次 inline 注入必须落在不同 run（否则后一次的 span 会被前一次吞掉）
    spans = sorted(s for s, _ in edits)
    for (a1, b1), (a2, _b2) in zip(spans, spans[1:]):
        if a2 < b1:
            raise InjectionError(
                f"注入 span 重叠：({a1},{b1}) 与 ({a2},...)。同段多注入必须落在不同 run"
            )

    # 从后往前应用，保持前面的 span 有效
    for (start, end), new_xml in sorted(edits, key=lambda e: -e[0][0]):
        xml = xml[:start] + new_xml + xml[end:]

    parts["word/document.xml"] = xml.encode("utf-8")
    out = _rezip(order, parts)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "doc": doc.key,
        "wp_code": doc.wp_code,
        "contract_id": doc.contract_id,
        "template_rel": doc.template_rel,
        "sdt_schema_version": "1.0.0-probe6",
        "lock_policy": "no_w_lock_injected",
        "lock_policy_why": (
            "加 <w:lock w:val=\"sdtLocked\"/> 会让 OO 无法删除 SDT，等于替载体作弊；"
            "本探针要证明的是 OO 在无保护下是否自发保留 tag。"
        ),
        "declared_operations": list(DOC_OPERATIONS.get(doc.key, OPERATIONS)),
        "fields": field_records,
        "rows": row_records,
        "expected_tags": sorted(
            {r["tag"] for r in field_records}
            | {r["block_tag"] for r in field_records if r.get("block_tag")}
            | {r["row_tag"] for r in row_records}
            | {r["field_tag"] for r in row_records}
        ),
        "expected_tag_multiset": _tag_multiset_from_records(field_records, row_records),
        "expected_row_uuids": sorted(r["row_uuid"] for r in row_records),
        "expected_hierarchy": _expected_hierarchy(field_records, row_records),
        "note": doc.note,
    }
    return out, manifest


def _tag_multiset_from_records(
    field_records: list[dict[str, Any]], row_records: list[dict[str, Any]]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in field_records:
        counts[r["tag"]] = counts.get(r["tag"], 0) + 1
        if r.get("block_tag"):
            counts[r["block_tag"]] = counts.get(r["block_tag"], 0) + 1
    for r in row_records:
        counts[r["row_tag"]] = counts.get(r["row_tag"], 0) + 1
        counts[r["field_tag"]] = counts.get(r["field_tag"], 0) + 1
    return dict(sorted(counts.items()))


def _expected_hierarchy(
    field_records: list[dict[str, Any]], row_records: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """tag → 期望的祖先 tag 链（由外到内）。空链 = 顶层 SDT。"""
    out: dict[str, list[str]] = {}
    for r in field_records:
        out.setdefault(r["tag"], [r["block_tag"]] if r.get("block_tag") else [])
        if r.get("block_tag"):
            out.setdefault(r["block_tag"], [])
    for r in row_records:
        out.setdefault(r["row_tag"], [])
        out.setdefault(r["field_tag"], [r["row_tag"]])
    return dict(sorted(out.items()))


def io_bytes(data: bytes):
    import io

    return io.BytesIO(data)


#: 固定 zip 条目时间戳，使 `instrument` 的输出**字节可复现**。
#: 不固定的话 `writestr(str, ...)` 会写入当前本地时间 ⇒ 同一 run_id 重跑得到不同
#: sha256，Requirement 14.16 要求的「同环境同 commit 可复算」就没法自证。
_ZIP_FIXED_DATETIME = (2026, 1, 1, 0, 0, 0)


def _rezip(order: list[str], parts: dict[str, bytes]) -> bytes:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in order:
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_FIXED_DATETIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, parts[name])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# tag inventory（探针级测量；**不是**生产 extractor —— 不产业务 projection）
# ---------------------------------------------------------------------------


def _text_of(el: ET.Element) -> str:
    return "".join(t.text or "" for t in el.iter(f"{W}t"))


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def sdt_inventory(docx: bytes) -> dict[str, Any]:
    """采一份 DOCX 的 SDT 载体清册（tag / 层级 / row_uuid / SDT 外正文）。

    🔴 只按 `w:tag` 定位，绝不按段落序号或正则猜内容 —— 这既是 Requirement 7.1 的
    协议要求，也让「tag 丢了」这件事无法被悄悄绕过（丢了就是 tag 不在清册里）。
    """
    errors: list[str] = []
    try:
        with zipfile.ZipFile(io_bytes(docx)) as z:
            raw = z.read("word/document.xml")
    except Exception as exc:  # noqa: BLE001
        raise InventoryError(f"读取 word/document.xml 失败: {type(exc).__name__}: {exc}") from exc
    try:
        root = ET.fromstring(raw)
    except Exception as exc:  # noqa: BLE001
        raise InventoryError(f"document.xml 解析失败: {type(exc).__name__}: {exc}") from exc

    body = root.find(f"{W}body")
    if body is None:
        raise InventoryError("document.xml 无 w:body")

    # 父指针 + body 直接子段落序号
    parent: dict[ET.Element, ET.Element] = {}
    for el in root.iter():
        for child in el:
            parent[child] = el

    body_paragraph_index: dict[ET.Element, int] = {}
    seq = 0
    for child in body:
        # body 直接子里，段落既可能是裸 w:p，也可能被 block SDT 包住
        if child.tag == f"{W}p":
            body_paragraph_index[child] = seq
            seq += 1
        elif child.tag == f"{W}sdt":
            content = child.find(f"{W}sdtContent")
            for sub in content if content is not None else []:
                if sub.tag == f"{W}p":
                    body_paragraph_index[sub] = seq
                    seq += 1

    def ancestor_sdt_tags(el: ET.Element) -> list[str]:
        chain: list[str] = []
        cur = parent.get(el)
        while cur is not None:
            if cur.tag == f"{W}sdt":
                t = cur.find(f"{W}sdtPr/{W}tag")
                chain.append(t.get(f"{W}val", "") if t is not None else "<no-tag>")
            cur = parent.get(cur)
        return list(reversed(chain))

    def level_of(el: ET.Element) -> str:
        p = parent.get(el)
        if p is None:
            return "unknown"
        if p.tag == f"{W}body":
            return "block"
        if p.tag == f"{W}p":
            return "inline"
        if p.tag == f"{W}tbl":
            return "row"
        if p.tag == f"{W}tr":
            return "cell"
        if p.tag == f"{W}sdtContent":
            gp = parent.get(p)
            gpp = parent.get(gp) if gp is not None else None
            if gpp is not None and gpp.tag == f"{W}body":
                return "block"
            if gpp is not None and gpp.tag == f"{W}p":
                return "inline"
            if gpp is not None and gpp.tag == f"{W}tbl":
                return "row"
            return f"nested_in_{gpp.tag.split('}')[-1] if gpp is not None else 'unknown'}"
        return f"in_{p.tag.split('}')[-1]}"

    def enclosing_paragraph_index(el: ET.Element) -> int | None:
        cur: ET.Element | None = el
        while cur is not None:
            if cur.tag == f"{W}p" and cur in body_paragraph_index:
                return body_paragraph_index[cur]
            cur = parent.get(cur)
        return None

    instances: list[dict[str, Any]] = []
    for sdt in root.iter(f"{W}sdt"):
        pr = sdt.find(f"{W}sdtPr")
        tag_el = pr.find(f"{W}tag") if pr is not None else None
        alias_el = pr.find(f"{W}alias") if pr is not None else None
        id_el = pr.find(f"{W}id") if pr is not None else None
        content = sdt.find(f"{W}sdtContent")
        tag_val = tag_el.get(f"{W}val") if tag_el is not None else None
        if tag_val is None:
            errors.append("发现无 w:tag 的 w:sdt（无法作为协议载体）")
        instances.append(
            {
                "tag": tag_val,
                "alias": alias_el.get(f"{W}val") if alias_el is not None else None,
                "sdt_id": id_el.get(f"{W}val") if id_el is not None else None,
                "level": level_of(sdt),
                "ancestor_tags": ancestor_sdt_tags(sdt),
                "depth": len(ancestor_sdt_tags(sdt)),
                "text": _norm_ws(_text_of(content)) if content is not None else None,
                "run_count": len(list(content.iter(f"{W}r"))) if content is not None else 0,
                "body_paragraph_index": enclosing_paragraph_index(sdt),
            }
        )

    tags = [i["tag"] for i in instances if i["tag"]]
    multiset: dict[str, int] = {}
    for t in tags:
        multiset[t] = multiset.get(t, 0) + 1

    # SDT 外正文：所有不在任何 sdtContent 内的 w:t
    inside: set[ET.Element] = set()
    for sdt in root.iter(f"{W}sdt"):
        content = sdt.find(f"{W}sdtContent")
        if content is not None:
            for el in content.iter():
                inside.add(el)
    external_texts = [
        (t.text or "") for t in root.iter(f"{W}t") if t not in inside and (t.text or "").strip()
    ]
    external_norm = [_norm_ws(t) for t in external_texts if _norm_ws(t)]
    #: SDT 外正文的**连写**形态：OO 会把一个 `w:t` 拆成多个（run 重排），
    #: 逐行比会把纯重排误报成正文丢失，故 Requirement 7.3 的判据用连写串。
    external_concat = re.sub(r"\s+", "", "".join(external_norm))
    full_concat = re.sub(r"\s+", "", "".join(_norm_ws(t.text or "") for t in root.iter(f"{W}t")))

    # 表格拓扑（行 SDT 会把 w:tr 挪到 sdtContent 下，故按 iter 统计）
    tables: list[dict[str, Any]] = []
    for tbl in root.iter(f"{W}tbl"):
        trs = list(tbl.iter(f"{W}tr"))
        tables.append(
            {
                "row_count": len(trs),
                "cells_per_row": [len(list(tr.iter(f"{W}tc"))) for tr in trs],
                "rows_wrapped_in_sdt": sum(
                    1
                    for tr in trs
                    if (parent.get(tr) is not None and parent[tr].tag == f"{W}sdtContent")
                ),
            }
        )

    #: row_uuid 有**两个独立来源**，必须分开统计。
    #: 实测（2026-08-24 OO 9.4.0-129）row 级 `w:sdt`（包 `w:tr`）被 OO 剥离，
    #: 而同一 uuid 若还写在**单元格内 inline field SDT** 的 tag 里则完好无损 ——
    #: 合成一个数字会把「行载体失效但行身份仍在」这条最关键的结论抹平。
    row_uuids_from_row_sdt = sorted(
        {
            m.group(1)
            for t in tags
            if (m := re.match(r"^gt:row:[^:]+:[^:]+:([0-9a-f-]{36})$", t or ""))
        }
    )
    row_uuids_from_field_tags = sorted(
        {
            m.group(1)
            for t in tags
            if (m := re.match(r"^gt:field:[^:]+:rows/([0-9a-f-]{36})/.+$", t or ""))
        }
    )
    row_uuids = sorted(set(row_uuids_from_row_sdt) | set(row_uuids_from_field_tags))

    return {
        "sdt_count": len(instances),
        "tags_sorted": sorted(set(tags)),
        "tag_multiset": dict(sorted(multiset.items())),
        "instances": instances,
        "by_tag": {
            t: [i for i in instances if i["tag"] == t] for t in sorted(set(tags))
        },
        "row_uuids": row_uuids,
        "row_uuids_from_row_sdt": row_uuids_from_row_sdt,
        "row_uuids_from_field_tags": row_uuids_from_field_tags,
        "hierarchy": {
            t: sorted({tuple(i["ancestor_tags"]) for i in instances if i["tag"] == t})
            and [list(x) for x in sorted({tuple(i["ancestor_tags"]) for i in instances if i["tag"] == t})]
            for t in sorted(set(tags))
        },
        "levels": {
            t: sorted({i["level"] for i in instances if i["tag"] == t}) for t in sorted(set(tags))
        },
        "body_paragraph_count": seq,
        "tables": tables,
        "external_body_line_count": len(external_norm),
        "external_body_digest": hashlib.sha256(external_concat.encode("utf-8")).hexdigest(),
        "external_body_concat": external_concat,
        "external_body_lines": external_norm,
        "full_text_concat": full_concat,
        "full_text_digest": hashlib.sha256(full_concat.encode("utf-8")).hexdigest(),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# 探针状态与 HTTP host
# ---------------------------------------------------------------------------


class ProbeState:
    def __init__(
        self,
        *,
        evidence_dir: Path,
        doc: ProbeDoc,
        staged: Path,
        doc_key: str,
        port: int,
    ):
        self.evidence_dir = evidence_dir
        self.artifacts_dir = evidence_dir / "artifacts"
        self.doc = doc
        self.staged = staged
        self.doc_key = doc_key
        self.port = port
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
<html lang="zh-CN"><head><meta charset="utf-8"><title>Task6 Word SDT probe</title>
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
            "fileType": "docx",
            "key": state.doc_key,
            "title": f"task6_{state.doc.key}_probe.docx",
            "url": f"{base}/doc?key={state.doc_key}",
            "permissions": {"edit": True, "download": True, "print": True},
        },
        "documentType": "word",
        "editorConfig": {
            "mode": "edit",
            "lang": "zh-CN",
            "callbackUrl": f"{base}/callback?probe=task6&doc={state.doc.key}",
            "user": {"id": "probe6", "name": "Task6 探针"},
            "customization": {"forcesave": True, "compactHeader": False},
        },
        "type": "desktop",
    }
    return {"config": {**config, "token": _sign(config)}, "oo_url": OO_URL_FROM_HOST}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("[probe6-http] " + (fmt % args) + "\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        self._send(
            code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"
        )

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
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
                    f"_status{body.get('status')}.docx"
                )
                (STATE.artifacts_dir / name).write_bytes(data)
                entry["artifact_file"] = f"artifacts/{name}"
                # 🔴 inventory 采集失败必须记 ERROR 态（不得吞成「无 tag」）。
                try:
                    inv = sdt_inventory(data)
                    entry["inventory_summary"] = {
                        "sdt_count": inv["sdt_count"],
                        "tags_sorted": inv["tags_sorted"],
                        "row_uuids": inv["row_uuids"],
                        "external_body_digest": inv["external_body_digest"],
                        "collection_errors": inv["errors"],
                    }
                except InventoryError as exc:
                    entry["inventory_error"] = f"ERROR InventoryError: {exc}"
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
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + _sign({"payload": payload}),
    }
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
    out: dict[str, Any] = {
        "stage": args.stage,
        "checked_at": _now(),
        "templates": {},
        "lock_files": [],
    }
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
    """复制真实模板到 staging 并注入 SDT，同时做 zip 级回读校验。"""
    evidence_dir = Path(args.evidence_dir)
    staging = _staging_dir(evidence_dir)
    staging.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or f"task6-{int(time.time())}"
    report: dict[str, Any] = {"run_id": run_id, "generated_at": _now(), "docs": {}}
    exit_code = 0
    for key, doc in PROBE_DOCS.items():
        if args.doc and key != args.doc:
            continue
        source_path = REPO_ROOT / doc.template_rel
        source = source_path.read_bytes()
        before_path = staging / f"{key}_before.docx"
        after_path = staging / f"{key}_instrumented.docx"
        before_path.write_bytes(source)  # staging 副本；权威源保持只读
        try:
            pre_inv = sdt_inventory(source)
            injected, manifest = inject_sdt(source, doc, run_id=run_id)
            post_inv = sdt_inventory(injected)
        except (InjectionError, InventoryError) as exc:
            report["docs"][key] = {"error": f"ERROR {type(exc).__name__}: {exc}"}
            exit_code = 1
            continue
        after_path.write_bytes(injected)

        # design §SDT migration 第 5 步：保存后重新打开 zip 验证 tag 集合/计数/层级
        verify = {
            "tags_match_manifest": post_inv["tags_sorted"] == manifest["expected_tags"],
            "tag_multiset_match": post_inv["tag_multiset"] == manifest["expected_tag_multiset"],
            "row_uuids_match": post_inv["row_uuids"] == manifest["expected_row_uuids"],
            "hierarchy_match": all(
                [list(exp)] == post_inv["hierarchy"].get(tag)
                or list(exp) in post_inv["hierarchy"].get(tag, [])
                for tag, exp in manifest["expected_hierarchy"].items()
            ),
            "visible_skeleton_preserved": _visible_skeleton_digest(post_inv, manifest)
            == _visible_skeleton_digest(pre_inv, manifest),
            "visible_skeleton_digest": _visible_skeleton_digest(post_inv, manifest),
            "pre_injection_sdt_count": pre_inv["sdt_count"],
            "post_injection_sdt_count": post_inv["sdt_count"],
            "collection_errors": post_inv["errors"],
        }
        with zipfile.ZipFile(io_bytes(injected)) as z:
            document_xml_sha = _sha256_bytes(z.read("word/document.xml"))
        report["docs"][key] = {
            "template_rel": doc.template_rel,
            "template_sha256": _sha256_bytes(source),
            "instrumented_sha256": _sha256_bytes(injected),
            #: OO 只消费 `word/document.xml`；它的 sha 才是「载体注入内容」的
            #: 稳定指纹（zip 容器层可能因压缩器版本差异而变）。
            "instrumented_document_xml_sha256": document_xml_sha,
            "zip_determinism": f"fixed_entry_datetime={_ZIP_FIXED_DATETIME}",
            "note": doc.note,
            "manifest": manifest,
            "pre_injection_inventory": {
                "sdt_count": pre_inv["sdt_count"],
                "tags_sorted": pre_inv["tags_sorted"],
                "body_paragraph_count": pre_inv["body_paragraph_count"],
                "tables": pre_inv["tables"],
                "external_body_digest": pre_inv["external_body_digest"],
                "external_body_line_count": pre_inv["external_body_line_count"],
            },
            "post_injection_inventory": post_inv,
            "zip_reopen_verification": verify,
        }
        if not all(
            verify[k]
            for k in (
                "tags_match_manifest",
                "tag_multiset_match",
                "row_uuids_match",
                "hierarchy_match",
                "visible_skeleton_preserved",
            )
        ):
            exit_code = 1
    (evidence_dir / "instrumentation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: info.get("zip_reopen_verification") or {"error": info.get("error")}
                for key, info in report["docs"].items()
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return exit_code


def _visible_skeleton_digest(inv: dict[str, Any], manifest: dict[str, Any]) -> str:
    """可见文本「骨架」digest：把注入涉及的 token 与 seed 全部抹掉后剩下的连写串。

    注入唯一被允许的改动是 `${token}` → `GT-xx-SEED`（以及往空单元格写 seed）。
    抹掉两侧词表后，pre 与 post 的骨架必须逐字相等 —— 这才是「注入没顺手改动
    自由正文」的判据。逐行比会把「一个 w:t 被切成三个」误报成正文丢失。
    """
    text = inv["full_text_concat"]
    words = sorted(
        {r["replaced_token"] for r in manifest["fields"] if r.get("replaced_token")}
        | {r["seed_text"] for r in manifest["fields"]}
        | {r["seed_text"] for r in manifest["rows"]},
        key=len,
        reverse=True,
    )
    for w in words:
        text = text.replace(re.sub(r"\s+", "", w), "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cmd_serve(args: argparse.Namespace) -> int:
    global STATE
    evidence_dir = Path(args.evidence_dir)
    doc = PROBE_DOCS[args.doc]
    staged = (
        Path(args.seed)
        if getattr(args, "seed", None)
        else _staging_dir(evidence_dir) / f"{args.doc}_instrumented.docx"
    )
    if not staged.exists():
        print(f"FATAL 尚未 instrument 或 seed 不存在: {staged}（先跑 instrument 子命令）")
        return 2
    report_path = evidence_dir / "instrumentation_report.json"
    if not report_path.exists():
        print(f"FATAL 缺少 instrumentation_report.json: {report_path}")
        return 2
    doc_key = args.doc_key or f"t6{args.doc}{int(time.time())}"
    STATE = ProbeState(
        evidence_dir=evidence_dir, doc=doc, staged=staged, doc_key=doc_key, port=args.port
    )
    meta = {
        "probe": "task6-oo94-word-tagged-sdt",
        "doc": args.doc,
        "wp_code": doc.wp_code,
        "started_at": _now(),
        "oo_url_from_host": OO_URL_FROM_HOST,
        "host_for_oo": HOST_FROM_CONTAINER,
        "probe_port": args.port,
        "doc_key": doc_key,
        "template_rel": doc.template_rel,
        "seed_file": str(staged).replace("\\", "/"),
        "staged_sha256": _sha256_bytes(STATE.doc_bytes),
        "operations": list(DOC_OPERATIONS.get(args.doc, OPERATIONS)),
        "oo_secret_ref": _digest_ref(OO_SECRET),
        "oo_build_endpoints": oo_build_info(),
    }
    meta_path = evidence_dir / f"run_meta_{args.doc}.json"
    if meta_path.exists():
        prev = json.loads(meta_path.read_text(encoding="utf-8"))
        history = prev.get("previous_runs", [])
        history.append({k: prev[k] for k in ("started_at", "doc_key", "seed_file", "staged_sha256") if k in prev})
        meta["previous_runs"] = history
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"serving": True, "doc": args.doc, "doc_key": doc_key, "port": args.port},
            ensure_ascii=False,
        )
    )
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
    record = {"ts": _now(), "op": state["op"], "doc": state["doc"], "request": payload, "result": result}
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
            "sdt": (c.get("inventory_summary") or {}).get("sdt_count"),
            "tags": len((c.get("inventory_summary") or {}).get("tags_sorted") or []),
            "row_uuids": len((c.get("inventory_summary") or {}).get("row_uuids") or []),
            "errors": [k for k in ("artifact_error", "inventory_error") if c.get(k)],
        }
        for c in state["callbacks"]
    ]
    print(
        json.dumps(
            {
                "doc_key": state["doc_key"],
                "doc": state["doc"],
                "op": state["op"],
                "count": state["count"],
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


#: `userdata` → 规范 op 名。`userdata` 是**发 forcesave 那一刻**由脚本写死的，
#: 比 `mark` 的进程内状态可靠：mark 与 callback 到达之间有竞态（实测 b30112 有 3 格
#: 因为「同一行 PowerShell 里 command 后紧跟 mark」而被贴上下一格的标签）。
_USERDATA_OP_ALIASES = {
    "op-baseline": "baseline",
    "op-edit-in-sdt": "edit_in_sdt",
    "op-edit-outside-sdt": "edit_outside_sdt",
    "op-insert-paragraph": "insert_paragraph",
    "op-delete-paragraph": "delete_paragraph",
    "op-insert-row": "insert_row",
    "op-delete-row": "delete_row",
    "op-forcesave-1": "forcesave",
    "op-forcesave-2": "forcesave",
    "op-reopen": "reopen",
    "op-reopen-r2": "reopen",
}

#: 用户**有意**删除的载体（不是 OO 剥离）。删行是审计师的编辑意图，
#: 判据必须把它与「载体被静默剥离」分开，否则会把正常删除误判成载体失效。
#:
#: 🔴 语义是「从这一格起**持续生效**」：删掉的行不会在后续 forcesave / download /
#: reopen 里复活，所以期望集合必须按声明操作序的位置累积裁剪；只在 delete_row
#: 那一格减一次，会让它之后每一格都假红。
INTENTIONAL_DELETIONS: dict[tuple[str, str], list[str]] = {
    ("b30112", "delete_row"): ["R02"],
}


def _effective_op(entry: dict[str, Any]) -> tuple[str, str]:
    """返回 (effective_op, label_source)。"""
    ud = entry.get("userdata")
    if isinstance(ud, str) and ud in _USERDATA_OP_ALIASES:
        return _USERDATA_OP_ALIASES[ud], "callback_userdata"
    return entry.get("op") or "unknown", "probe_mark_fallback"


def _cumulative_intentional_deletions(manifest: dict[str, Any], doc_key: str, op: str) -> list[str]:
    """按声明操作序累积「这一格及之前」声明过的有意删除。"""
    order = list(manifest["declared_operations"])
    if op not in order:
        return list(INTENTIONAL_DELETIONS.get((doc_key, op), []))
    upto = order.index(op)
    out: list[str] = []
    for earlier in order[: upto + 1]:
        out.extend(INTENTIONAL_DELETIONS.get((doc_key, earlier), []))
    return out


def _expected_after_intentional_deletions(
    manifest: dict[str, Any], doc_key: str, op: str
) -> tuple[set[str], dict[str, int], set[str], dict[str, list[str]], list[str]]:
    """按声明的有意删除裁掉期望集合，返回 (tags, multiset, row_uuids, hierarchy, 删掉的 inj_id)。"""
    removed = _cumulative_intentional_deletions(manifest, doc_key, op)
    tags = set(manifest["expected_tags"])
    multiset = dict(manifest["expected_tag_multiset"])
    uuids = set(manifest["expected_row_uuids"])
    hierarchy = dict(manifest["expected_hierarchy"])
    for inj_id in removed:
        for rec in manifest["rows"]:
            if rec["inj_id"] != inj_id:
                continue
            for key in ("row_tag", "field_tag"):
                tag = rec[key]
                tags.discard(tag)
                multiset.pop(tag, None)
                hierarchy.pop(tag, None)
            uuids.discard(rec["row_uuid"])
        for rec in manifest["fields"]:
            if rec["inj_id"] != inj_id:
                continue
            for key in ("tag", "block_tag"):
                tag = rec.get(key)
                if tag:
                    tags.discard(tag)
                    multiset.pop(tag, None)
                    hierarchy.pop(tag, None)
    return tags, multiset, uuids, hierarchy, removed


def _row_for_artifact(
    evidence_dir: Path, entry: dict[str, Any], instrumentation: dict[str, Any]
) -> dict[str, Any]:
    rel = entry["artifact_file"]
    path = evidence_dir / rel
    doc_key = entry.get("doc") or ""
    if doc_key not in instrumentation["docs"]:
        return {"op": entry.get("op"), "doc": doc_key, "error": f"ERROR 未注入的 doc: {doc_key}"}
    manifest = instrumentation["docs"][doc_key]["manifest"]
    baseline_inv = instrumentation["docs"][doc_key]["post_injection_inventory"]
    op, label_source = _effective_op(entry)
    if not path.exists():
        return {"op": op, "doc": doc_key, "error": f"ERROR artifact 缺失 {rel}"}
    data = path.read_bytes()
    try:
        inv = sdt_inventory(data)
    except InventoryError as exc:
        return {"op": op, "doc": doc_key, "error": f"ERROR InventoryError: {exc}"}

    (
        expected_tags,
        expected_ms,
        expected_uuids,
        expected_hierarchy,
        intentionally_removed,
    ) = _expected_after_intentional_deletions(manifest, doc_key, op)
    got_tags = set(inv["tags_sorted"])
    got_ms: dict[str, int] = inv["tag_multiset"]
    got_uuids = set(inv["row_uuids"])

    hierarchy_regressions = []
    for tag, expected_chain in expected_hierarchy.items():
        got_chains = inv["hierarchy"].get(tag)
        if got_chains is None:
            hierarchy_regressions.append({"tag": tag, "expected": expected_chain, "got": None})
        elif list(expected_chain) not in [list(c) for c in got_chains]:
            hierarchy_regressions.append(
                {"tag": tag, "expected": expected_chain, "got": got_chains}
            )

    level_regressions = [
        {"tag": tag, "baseline": baseline_inv["levels"].get(tag), "got": inv["levels"].get(tag)}
        for tag in sorted(expected_tags)
        if inv["levels"].get(tag) is not None
        and baseline_inv["levels"].get(tag) != inv["levels"].get(tag)
    ]

    # 🔴 锚点稳定性只在**两侧都存在**的 tag 上比较。
    # 否则「载体被剥离」会连带把 alias/sdt_id/paragraph_index 三个锚点一起判不稳定，
    # 把一个失败伪装成四个 —— 载体裁决与锚点裁决必须互相独立。
    common_tags = sorted(set(baseline_inv["by_tag"]) & set(inv["by_tag"]))

    def _pluck(source: dict[str, Any], field: str) -> dict[str, Any]:
        return {
            t: sorted({i[field] for i in source[t] if i.get(field) is not None})
            for t in common_tags
        }

    alias_baseline = _pluck(baseline_inv["by_tag"], "alias")
    alias_now = _pluck(inv["by_tag"], "alias")
    sdt_id_baseline = _pluck(baseline_inv["by_tag"], "sdt_id")
    sdt_id_now = _pluck(inv["by_tag"], "sdt_id")
    para_baseline = _pluck(baseline_inv["by_tag"], "body_paragraph_index")
    para_now = _pluck(inv["by_tag"], "body_paragraph_index")

    return {
        "op": op,
        "op_label_source": label_source,
        "marked_op": entry.get("op"),
        "userdata": entry.get("userdata"),
        "op_label_disagreed_with_mark": entry.get("op") != op,
        "intentionally_removed_injections": intentionally_removed,
        "doc": doc_key,
        "seq": entry.get("seq"),
        "status": entry.get("status"),
        "delivery": entry.get("delivery", "oo_callback"),
        "artifact_file": rel,
        "artifact_sha256": _sha256_bytes(data),
        "carriers": {
            "w_tag": {
                "sdt_count": inv["sdt_count"],
                "tags_present": sorted(got_tags),
                "missing_tags": sorted(expected_tags - got_tags),
                "added_tags": sorted(got_tags - expected_tags),
                "tag_set_not_reduced": not (expected_tags - got_tags),
                "instance_count_deltas": {
                    t: {"expected": expected_ms.get(t, 0), "got": got_ms.get(t, 0)}
                    for t in sorted(expected_tags)
                    if got_ms.get(t, 0) != expected_ms.get(t, 0)
                },
                "instance_count_not_reduced": all(
                    got_ms.get(t, 0) >= expected_ms.get(t, 0) for t in expected_tags
                ),
            },
            "hierarchy": {
                "regressions": hierarchy_regressions,
                "hierarchy_preserved": not hierarchy_regressions,
                "level_regressions": level_regressions,
                "levels": inv["levels"],
            },
            "row_uuid": {
                "expected_count": len(expected_uuids),
                "present": sorted(got_uuids),
                "missing": sorted(expected_uuids - got_uuids),
                "added": sorted(got_uuids - expected_uuids),
                "row_uuid_set_not_reduced": not (expected_uuids - got_uuids),
                # 🔴 两个来源分开报：row 级 SDT 被剥离时，同 uuid 仍可能活在
                # 单元格 inline field SDT 的 tag 里 —— 这两件事必须能分别读出。
                "from_row_sdt": inv["row_uuids_from_row_sdt"],
                "from_field_tags": inv["row_uuids_from_field_tags"],
                #: 无 row 注入的文档判 `null`（不适用），不能判 false —— 那会把
                #: 「这份模板没有表格」说成「行载体在这份模板上失效」。
                "row_sdt_carrier_survived": (
                    bool(inv["row_uuids_from_row_sdt"]) if manifest["rows"] else None
                ),
                "row_sdt_wrapped_rows": [t["rows_wrapped_in_sdt"] for t in inv["tables"]],
                "tables": inv["tables"],
            },
            "sdt_external_body": {
                "digest": inv["external_body_digest"],
                "baseline_digest": baseline_inv["external_body_digest"],
                "matches_baseline": inv["external_body_digest"]
                == baseline_inv["external_body_digest"],
                "line_count": inv["external_body_line_count"],
                "baseline_line_count": baseline_inv["external_body_line_count"],
                "lines_lost": sorted(
                    set(baseline_inv["external_body_lines"]) - set(inv["external_body_lines"])
                ),
                "lines_added": sorted(
                    set(inv["external_body_lines"]) - set(baseline_inv["external_body_lines"])
                ),
            },
        },
        "anchors": {
            "alias_display_name": {
                "baseline": alias_baseline,
                "now": alias_now,
                "stable": alias_baseline == alias_now,
            },
            "sdt_id": {
                "baseline": sdt_id_baseline,
                "now": sdt_id_now,
                "stable": sdt_id_baseline == sdt_id_now,
            },
            "paragraph_index": {
                "baseline": para_baseline,
                "now": para_now,
                "stable": para_baseline == para_now,
            },
        },
        "values_read_through_tag": {
            t: sorted({i["text"] for i in insts if i["text"] is not None})
            for t, insts in inv["by_tag"].items()
        },
        "run_counts_per_tag": {
            t: sorted({i["run_count"] for i in insts}) for t, insts in inv["by_tag"].items()
        },
        "body_paragraph_count": inv["body_paragraph_count"],
        "baseline_body_paragraph_count": baseline_inv["body_paragraph_count"],
        "collection_errors": inv["errors"],
    }


def cmd_analyze(args: argparse.Namespace) -> int:
    """按操作矩阵把 artifact 折成「操作 × 载体」实测表 + 逐项判定。"""
    evidence_dir = Path(args.evidence_dir)
    instrumentation = json.loads(
        (evidence_dir / "instrumentation_report.json").read_text(encoding="utf-8")
    )
    log = evidence_dir / "callbacks.jsonl"
    entries = [
        json.loads(line)
        for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else [])
        if line.strip()
    ]
    # 编辑器「文件→下载为 DOCX」不经 callback，也必须进矩阵，否则 download 这一格
    # 只剩关闭保存的 status 2，缺了真正的用户下载路径。
    logged = {e.get("artifact_file") for e in entries}
    orphans = [
        {
            "artifact_file": f"artifacts/{p.name}",
            "op": "download",
            "userdata": None,
            "doc": p.name.split("_")[0],
            "status": None,
            "seq": f"editor-saveas:{p.name}",
            "delivery": "editor_download_not_callback",
        }
        for p in sorted((evidence_dir / "artifacts").glob("*_editor_saveas.docx"))
    ]
    entries = entries + [o for o in orphans if o["artifact_file"] not in logged]

    # 🔴 基线完整性：analyze 用的 baseline inventory 必须来自与报告同一份注入内容。
    # 只比 `word/document.xml`（OO 唯一消费的部件）—— zip 容器层的时间戳/压缩差异
    # 不改变载体内容，拿整包 sha 当判据会把无害差异误报成漂移。
    baseline_integrity: dict[str, Any] = {}
    for key, info in instrumentation["docs"].items():
        staged = _staging_dir(evidence_dir) / f"{key}_instrumented.docx"
        if not staged.exists():
            baseline_integrity[key] = {"error": f"ERROR staging 缺失 {staged}"}
            continue
        with zipfile.ZipFile(staged) as z:
            actual = _sha256_bytes(z.read("word/document.xml"))
        expected = info.get("instrumented_document_xml_sha256")
        baseline_integrity[key] = {
            "staging_document_xml_sha256": actual,
            "report_document_xml_sha256": expected,
            "matches": actual == expected,
        }

    matrix = [
        _row_for_artifact(evidence_dir, e, instrumentation) for e in entries if e.get("artifact_file")
    ]

    coverage: dict[str, Any] = {}
    for key, info in instrumentation["docs"].items():
        declared = info["manifest"]["declared_operations"]
        seen = {r["op"] for r in matrix if r.get("doc") == key and not r.get("error")}
        coverage[key] = {
            "declared_operations": declared,
            "covered_operations": sorted(seen),
            "uncovered_operations": [op for op in declared if op not in seen],
            "not_applicable_operations": [op for op in OPERATIONS if op not in declared],
            "has_tables": bool(info["pre_injection_inventory"]["tables"]),
            "row_carrier_probeable": bool(info["manifest"]["rows"]),
        }

    out = {
        "generated_at": _now(),
        "probe": "task6-oo94-word-tagged-sdt",
        "operations_declared_global": list(OPERATIONS),
        "op_label_policy": (
            "op 以 callback 的 userdata 为权威（发 forcesave 时写死），probe mark 只作兜底；"
            "两者不一致时保留 marked_op 与 op_label_disagreed_with_mark 供审计"
        ),
        "intentional_deletions": {f"{k[0]}/{k[1]}": v for k, v in INTENTIONAL_DELETIONS.items()},
        "baseline_integrity": baseline_integrity,
        "coverage": coverage,
        "matrix": matrix,
    }
    (evidence_dir / "operation_matrix.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            [
                {
                    "doc": r.get("doc"),
                    "op": r.get("op"),
                    "status": r.get("status"),
                    "delivery": r.get("delivery"),
                    "sdt": (r.get("carriers") or {}).get("w_tag", {}).get("sdt_count"),
                    "tag_ok": (r.get("carriers") or {}).get("w_tag", {}).get("tag_set_not_reduced"),
                    "missing_tags": (r.get("carriers") or {}).get("w_tag", {}).get("missing_tags"),
                    "count_ok": (r.get("carriers") or {})
                    .get("w_tag", {})
                    .get("instance_count_not_reduced"),
                    "hier_ok": (r.get("carriers") or {}).get("hierarchy", {}).get("hierarchy_preserved"),
                    "uuid_ok": (r.get("carriers") or {})
                    .get("row_uuid", {})
                    .get("row_uuid_set_not_reduced"),
                    "row_sdt_alive": (r.get("carriers") or {})
                    .get("row_uuid", {})
                    .get("row_sdt_carrier_survived"),
                    "label_src": r.get("op_label_source"),
                    "ext_body_ok": (r.get("carriers") or {})
                    .get("sdt_external_body", {})
                    .get("matches_baseline"),
                    "alias_stable": (r.get("anchors") or {})
                    .get("alias_display_name", {})
                    .get("stable"),
                    "sdt_id_stable": (r.get("anchors") or {}).get("sdt_id", {}).get("stable"),
                    "para_idx_stable": (r.get("anchors") or {})
                    .get("paragraph_index", {})
                    .get("stable"),
                    "errors": r.get("collection_errors"),
                    "error": r.get("error"),
                }
                for r in matrix
            ],
            ensure_ascii=False,
            indent=1,
        )
    )
    print(json.dumps({"coverage": coverage}, ensure_ascii=False, indent=1))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """对任意本地 docx 直接采一次 SDT inventory（供离线核对）。"""
    path = Path(args.path)
    data = path.read_bytes()
    inv = sdt_inventory(data)
    payload = {"path": str(path), "sha256": _sha256_bytes(data), "inventory": inv}
    print(json.dumps({k: v for k, v in payload.items() if k != "inventory"}, ensure_ascii=False))
    print(
        json.dumps(
            {
                "sdt_count": inv["sdt_count"],
                "tags_sorted": inv["tags_sorted"],
                "tag_multiset": inv["tag_multiset"],
                "row_uuids": inv["row_uuids"],
                "levels": inv["levels"],
                "hierarchy": inv["hierarchy"],
                "body_paragraph_count": inv["body_paragraph_count"],
                "tables": inv["tables"],
                "external_body_digest": inv["external_body_digest"],
                "errors": inv["errors"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    import subprocess

    dpkg = subprocess.run(  # noqa: S603 — 固定参数
        ["docker", "exec", "audit-onlyoffice", "dpkg", "-l", "onlyoffice-documentserver"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
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
    ap = argparse.ArgumentParser(description="真实 OO 9.4 Word tagged SDT 黑盒探针（Task 6）")
    ap.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("verify-source", help="核 backend/wp_templates 源文件 sha256")
    p.add_argument("--stage", required=True, choices=["before", "after"])
    p.set_defaults(func=cmd_verify_source)

    p = sub.add_parser("instrument", help="复制到 staging 并注入 field/row SDT + zip 回读校验")
    p.add_argument("--doc", default=None, choices=sorted(PROBE_DOCS))
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_instrument)

    p = sub.add_parser("serve", help="启动 document host + callback collector")
    p.add_argument("--doc", required=True, choices=sorted(PROBE_DOCS))
    p.add_argument("--doc-key", default=None)
    p.add_argument(
        "--seed",
        default=None,
        help="用指定 docx 作为宿主文档（reopen 用：喂上一轮 OO 产出的 artifact）",
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

    p = sub.add_parser("snapshot", help="对本地 docx 采 SDT inventory")
    p.add_argument("--path", required=True)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("build", help="记录 OO build 号")
    p.set_defaults(func=cmd_build)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
