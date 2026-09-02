"""Word OOXML SDT 结构指纹 / 载体清册 / 正文保留报告（可复用模块）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure
Requirements 7.1 / 7.2 / 7.3 / 7.4 / 7.5 / 7.6 / 7.8 / 14.4
Task 6（真实 OO 9.4 Word tagged SDT 载体黑盒 probe）产出，Property 33 的判据来源。

Task 5 的 `excel_structure_fingerprint` 是同族模块，两者分工一致：

  1. `structure_fingerprint()` —— 只描述**事实**（SDT 节点、层级、SDT 外正文、表格形状、
     受保护部件、part digest），不做任何通过与否的判断。
  2. `sdt_inventory()` —— 从事实里投影出 Word 侧四类载体/能力的清册（Property 33 的比对对象）：
     field SDT / row SDT（含 `row_uuid`）/ 同 key 多实例 / SDT 外自由正文。
  3. `body_preservation_report()` —— 两份 DOCX 的逐 aspect 保留判定（Requirement 7.3/7.9）。

🔴 三条硬约束（写在代码里而不是注释里）：

  - **不得 fail-open**：任何采集失败都抛 `WordFingerprintError`，或在 `errors` 里留 ERROR
    记录并让调用方守卫打红。绝不把解析失败降级成「无 SDT / 空 inventory」—— 那会让
    「tag 被 OO 剥离」与「采集器坏了」两种完全不同的事实产生同一个结论。
  - **段落索引与 `w:id` 只作伪锚点取证对象**：Requirement 7.1 明文禁止段落绝对索引作为
    正式回写协议，design「明确拒绝的方案」第 7 条同样禁止 paragraph index / placeholder
    regex / 整段回填。本模块**只**把它们算出来供 probe 证伪，`sdt_inventory()` 里它们
    位于 `anchors` 而不是 `carriers`，任何调用方都不得拿它们定位字段。
  - **XPath 是「报告用位置」不是「identity」**：Requirement 7.4 要求冲突能列出全部 OO 位置，
    所以每个 SDT 实例都带 XPath；但 identity 永远是 `w:tag`，XPath 只在读取时现算。

tag 方案（design §Word SDT 协议；probe 阶段固定 v1）：

    field:  gtsdt/v1/field/{field_key}
    row:    gtsdt/v1/row/{table_key}/{row_uuid}

`row_uuid` 落在 tag 内部（Requirement 7.2 明文禁止用表格行号识别），因此「插删行后
row_uuid 是否仍能定位」这一格由 tag 解析而非行序回答。
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

__all__ = [
    "WordFingerprintError",
    "FIELD_TAG_PREFIX",
    "ROW_TAG_PREFIX",
    "TAG_SCHEME_VERSION",
    "SDT_KINDS",
    "PRESERVATION_ASPECTS",
    "SdtNode",
    "DocumentFingerprint",
    "structure_fingerprint",
    "fingerprint_bytes",
    "sdt_inventory",
    "body_preservation_report",
    "parse_row_tag",
    "parse_field_tag",
]

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _W}

TAG_SCHEME_VERSION = "1"
FIELD_TAG_PREFIX = "gtsdt/v1/field/"
ROW_TAG_PREFIX = "gtsdt/v1/row/"

#: SDT 载体形态。`unknown` 保留给「OO 产出了我们没声明过的 SDT 形态」这种必须暴露的情况。
SDT_KINDS = ("field_inline", "field_block", "row", "cell", "unknown")

#: Requirement 7.3/7.9 + Property 33 要求逐项比对的 aspect（保留报告的固定列）。
PRESERVATION_ASPECTS = (
    "sdt_tag_set",
    "sdt_hierarchy",
    "row_uuid_set",
    "outside_sdt_text",
    "table_shape",
    "protected_parts",
)

#: 「受保护部件」= 平台不管理、instrumentation 与 OO 往返都不得丢失的 OOXML 部件类别。
_PROTECTED_PART_PATTERNS: dict[str, re.Pattern[str]] = {
    "media": re.compile(r"^word/media/"),
    "embeddings": re.compile(r"^word/embeddings/"),
    "chart": re.compile(r"^word/charts/"),
    "diagram": re.compile(r"^word/diagrams/"),
    "header": re.compile(r"^word/header\d*\.xml$"),
    "footer": re.compile(r"^word/footer\d*\.xml$"),
    "footnotes": re.compile(r"^word/footnotes\.xml$"),
    "endnotes": re.compile(r"^word/endnotes\.xml$"),
    "numbering": re.compile(r"^word/numbering\.xml$"),
    "styles": re.compile(r"^word/styles\.xml$"),
    "custom_xml": re.compile(r"^customXml/"),
    "vba": re.compile(r"^word/vbaProject\.bin$"),
}

#: 块级容器（正文投影时按它们分组）。
_BLOCK_TAGS = ("p", "tbl", "tr", "tc", "sdt", "sdtContent", "body")


class WordFingerprintError(RuntimeError):
    """结构采集失败。**不得**被调用方降级为「无 SDT / 无数据」。"""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_lines(lines: Sequence[str]) -> str:
    return _sha256("\n".join(lines).encode("utf-8"))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalise_text(text: str) -> str:
    """正文比较用的规范化：NFKC + 全角空白与 NBSP 归一 + 折叠连续空白 + 去首尾。

    为什么必须规范化：OO 会重排 run、把 `w:t` 拆合、在段落里插 `w:proofErr`；如果按
    原始字节比，「OO 只是重序列化」和「OO 抹了正文」会得到同一个红色结论，归因就没了。
    """
    out = unicodedata.normalize("NFKC", text)
    out = out.replace("\u00a0", " ").replace("\u3000", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", out).strip()


def parse_field_tag(tag: str) -> str | None:
    """`gtsdt/v1/field/entityName` → `entityName`；非本方案返回 None。"""
    if not tag.startswith(FIELD_TAG_PREFIX):
        return None
    key = tag[len(FIELD_TAG_PREFIX):]
    return key or None


def parse_row_tag(tag: str) -> tuple[str, str] | None:
    """`gtsdt/v1/row/{table_key}/{row_uuid}` → `(table_key, row_uuid)`；非本方案返回 None。"""
    if not tag.startswith(ROW_TAG_PREFIX):
        return None
    rest = tag[len(ROW_TAG_PREFIX):]
    if "/" not in rest:
        return None
    table_key, row_uuid = rest.rsplit("/", 1)
    if not table_key or not row_uuid:
        return None
    return table_key, row_uuid


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SdtNode:
    """一个 SDT 实例的事实描述。identity 恒为 :attr:`tag`，其余字段只作报告/取证。"""

    tag: str
    alias: str
    #: `w:sdtPr/w:id/@w:val`。🔴 伪锚点候选，只用于证伪，不得当 identity。
    w_id: str | None
    kind: str
    #: 报告用位置（Requirement 7.4「列出全部 OO 位置」）。
    xpath: str
    #: 层级链：结构容器 + 祖先 SDT tag，形如 `body/tbl[2]/sdt(row:...)/tr/tc[1]/p`。
    container_path: str
    #: 祖先 SDT 的 tag 链（外→内）。
    ancestor_tags: tuple[str, ...]
    depth: int
    text: str
    run_count: int
    #: `w:sdtContent` 的直接子元素本地名（判 kind 与「层级是否被压扁」用）。
    content_children: tuple[str, ...]
    #: 🔴 伪锚点候选：该 SDT 所属块在 `w:body` 直接子节点里的序号（0-based，不在 body 直挂时为 -1）。
    body_child_index: int


@dataclass
class DocumentFingerprint:
    """一份 DOCX 的结构事实。只描述，不判定。"""

    part_names: list[str] = field(default_factory=list)
    part_digests: dict[str, str] = field(default_factory=dict)
    sdt_nodes: list[SdtNode] = field(default_factory=list)
    #: SDT 外正文投影：`[{"path":..., "text":...}]`，只含规范化后非空者。
    outside_sdt_blocks: list[dict[str, Any]] = field(default_factory=list)
    #: `w:body` 直接子节点序列（本地名），插删段落的结构判据。
    body_child_kinds: list[str] = field(default_factory=list)
    paragraph_count: int = 0
    table_shapes: list[dict[str, Any]] = field(default_factory=list)
    protected_parts: dict[str, list[str]] = field(default_factory=dict)
    fonts_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # --- 投影 -------------------------------------------------------------

    def tag_set(self) -> list[str]:
        return sorted({n.tag for n in self.sdt_nodes if n.tag})

    def untagged_sdt_count(self) -> int:
        return sum(1 for n in self.sdt_nodes if not n.tag)

    def tag_instances(self) -> dict[str, list[SdtNode]]:
        out: dict[str, list[SdtNode]] = {}
        for node in self.sdt_nodes:
            if node.tag:
                out.setdefault(node.tag, []).append(node)
        return out

    def hierarchy_map(self) -> dict[str, list[str]]:
        """tag → 该 tag 全部实例的层级链（排序后）。Property 33 的「层级」就是它。"""
        out: dict[str, list[str]] = {}
        for tag, nodes in self.tag_instances().items():
            out[tag] = sorted(n.container_path for n in nodes)
        return out

    def kind_map(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for tag, nodes in self.tag_instances().items():
            out[tag] = sorted({n.kind for n in nodes})
        return out

    def row_uuids(self) -> dict[str, list[str]]:
        """table_key → row_uuid 列表（按文档出现顺序，可含重复以便检出复制行）。"""
        out: dict[str, list[str]] = {}
        for node in self.sdt_nodes:
            parsed = parse_row_tag(node.tag)
            if parsed:
                out.setdefault(parsed[0], []).append(parsed[1])
        return out

    def outside_sdt_texts(self) -> list[str]:
        return [b["text"] for b in self.outside_sdt_blocks]

    def aspect_digests(self) -> dict[str, str]:
        return {
            "sdt_tag_set": _hash_lines(self.tag_set()),
            "sdt_hierarchy": _hash_lines(
                [f"{t}={p}" for t, paths in sorted(self.hierarchy_map().items()) for p in paths]
            ),
            "row_uuid_set": _hash_lines(
                [f"{k}:{u}" for k, us in sorted(self.row_uuids().items()) for u in sorted(us)]
            ),
            "outside_sdt_text": _hash_lines(self.outside_sdt_texts()),
            "table_shape": _hash_lines([str(t) for t in self.table_shapes]),
            "protected_parts": _hash_lines(
                [f"{k}={len(v)}" for k, v in sorted(self.protected_parts.items())]
            ),
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "part_count": len(self.part_names),
            "sdt_count": len(self.sdt_nodes),
            "untagged_sdt_count": self.untagged_sdt_count(),
            "tag_set": self.tag_set(),
            "kind_map": self.kind_map(),
            "hierarchy_map": self.hierarchy_map(),
            "row_uuids": self.row_uuids(),
            "paragraph_count": self.paragraph_count,
            "body_child_kinds": self.body_child_kinds,
            "outside_sdt_block_count": len(self.outside_sdt_blocks),
            "outside_sdt_text_digest": _hash_lines(self.outside_sdt_texts()),
            "table_shapes": self.table_shapes,
            "protected_parts": {k: len(v) for k, v in sorted(self.protected_parts.items())},
            "fonts_used": self.fonts_used,
            "aspect_digests": self.aspect_digests(),
            "errors": self.errors,
            "sdt_nodes": [
                {
                    "tag": n.tag,
                    "alias": n.alias,
                    "w_id": n.w_id,
                    "kind": n.kind,
                    "xpath": n.xpath,
                    "container_path": n.container_path,
                    "ancestor_tags": list(n.ancestor_tags),
                    "depth": n.depth,
                    "text": n.text,
                    "run_count": n.run_count,
                    "content_children": list(n.content_children),
                    "body_child_index": n.body_child_index,
                }
                for n in self.sdt_nodes
            ],
        }


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------


def _read_document_xml(zf: zipfile.ZipFile) -> bytes:
    try:
        return zf.read("word/document.xml")
    except KeyError as exc:  # pragma: no cover - 非 DOCX
        raise WordFingerprintError("缺少 word/document.xml，不是有效 DOCX") from exc


def _sdt_kind(content_children: tuple[str, ...], parent_local: str) -> str:
    if "tr" in content_children:
        return "row"
    if "tc" in content_children:
        return "cell"
    if parent_local == "p":
        return "field_inline"
    if "p" in content_children or "tbl" in content_children:
        return "field_block"
    if content_children and set(content_children) <= {"r", "hyperlink", "bookmarkStart", "bookmarkEnd", "proofErr"}:
        # `w:sdtContent` 直接挂 run 但父不是 `w:p` —— 结构异常，必须暴露而不是猜。
        return "unknown"
    return "unknown"


def _node_text(elem: ET.Element) -> str:
    return "".join(t.text or "" for t in elem.iter(f"{{{_W}}}t"))


def structure_fingerprint(data: bytes) -> DocumentFingerprint:
    """采集一份 DOCX 的结构事实。解析失败抛 :class:`WordFingerprintError`。"""
    fp = DocumentFingerprint()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise WordFingerprintError(f"不是合法 zip/DOCX: {exc}") from exc
    with zf:
        fp.part_names = sorted(zf.namelist())
        for name in fp.part_names:
            try:
                fp.part_digests[name] = _sha256(zf.read(name))
            except Exception as exc:  # noqa: BLE001 - 如实记录，不静默跳过
                fp.errors.append(f"ERROR part_read {name}: {type(exc).__name__}: {exc}")
        for category, pattern in _PROTECTED_PART_PATTERNS.items():
            hits = [n for n in fp.part_names if pattern.match(n)]
            if hits:
                fp.protected_parts[category] = hits
        doc_bytes = _read_document_xml(zf)

    try:
        root = ET.fromstring(doc_bytes)
    except ET.ParseError as exc:
        raise WordFingerprintError(f"word/document.xml 解析失败: {exc}") from exc
    body = root.find(f"{{{_W}}}body")
    if body is None:
        raise WordFingerprintError("word/document.xml 缺少 w:body")

    fp.fonts_used = sorted(
        {
            v
            for rfonts in root.iter(f"{{{_W}}}rFonts")
            for v in (
                rfonts.get(f"{{{_W}}}ascii"),
                rfonts.get(f"{{{_W}}}eastAsia"),
                rfonts.get(f"{{{_W}}}hAnsi"),
            )
            if v
        }
    )

    # body 直接子节点序列 + 每个子节点的序号（伪锚点 `paragraph index` 取证用）
    body_children = list(body)
    fp.body_child_kinds = [_local(c.tag) for c in body_children]
    index_of: dict[int, int] = {id(c): i for i, c in enumerate(body_children)}

    counters: dict[int, dict[str, int]] = {}

    def child_position(parent: ET.Element, child: ET.Element) -> int:
        key = id(parent)
        bucket = counters.setdefault(key, {})
        name = _local(child.tag)
        bucket[name] = bucket.get(name, 0) + 1
        return bucket[name]

    def walk(
        elem: ET.Element,
        xpath: str,
        container_path: str,
        ancestor_tags: tuple[str, ...],
        depth: int,
        body_index: int,
        inside_sdt: bool,
    ) -> None:
        for child in list(elem):
            local = _local(child.tag)
            pos = child_position(elem, child)
            child_xpath = f"{xpath}/w:{local}[{pos}]"
            child_body_index = index_of.get(id(child), body_index)
            if local == "sdt":
                content = child.find(f"{{{_W}}}sdtContent")
                pr = child.find(f"{{{_W}}}sdtPr")
                tag_el = pr.find(f"{{{_W}}}tag") if pr is not None else None
                alias_el = pr.find(f"{{{_W}}}alias") if pr is not None else None
                id_el = pr.find(f"{{{_W}}}id") if pr is not None else None
                tag = (tag_el.get(f"{{{_W}}}val") or "") if tag_el is not None else ""
                alias = (alias_el.get(f"{{{_W}}}val") or "") if alias_el is not None else ""
                w_id = (id_el.get(f"{{{_W}}}val") or None) if id_el is not None else None
                if content is None:
                    fp.errors.append(
                        f"ERROR sdt_without_content xpath={child_xpath} tag={tag!r}"
                    )
                    content_children: tuple[str, ...] = ()
                    text = ""
                    run_count = 0
                else:
                    content_children = tuple(_local(c.tag) for c in list(content))
                    text = _node_text(content)
                    run_count = len(list(content.iter(f"{{{_W}}}r")))
                kind = _sdt_kind(content_children, _local(elem.tag))
                node = SdtNode(
                    tag=tag,
                    alias=alias,
                    w_id=w_id,
                    kind=kind,
                    xpath=child_xpath,
                    container_path=container_path or "body",
                    ancestor_tags=ancestor_tags,
                    depth=depth,
                    text=normalise_text(text),
                    run_count=run_count,
                    content_children=content_children,
                    body_child_index=child_body_index,
                )
                fp.sdt_nodes.append(node)
                if content is not None:
                    marker = f"sdt({kind}:{tag or '<untagged>'})"
                    walk(
                        content,
                        f"{child_xpath}/w:sdtContent[1]",
                        f"{container_path or 'body'}/{marker}",
                        ancestor_tags + ((tag or "<untagged>"),),
                        depth + 1,
                        child_body_index,
                        True,
                    )
                continue

            if local == "p":
                fp.paragraph_count += 1
                if not inside_sdt:
                    # 段落里可能嵌 inline SDT ⇒ 只收「不属于任何 SDT」的 run 文本
                    text = _collect_free_text(child)
                    norm = normalise_text(text)
                    if norm:
                        fp.outside_sdt_blocks.append(
                            {"path": child_xpath, "kind": "p", "text": norm}
                        )
                # 段落内部仍要继续走，才能发现 inline SDT
                walk(
                    child,
                    child_xpath,
                    f"{container_path or 'body'}/p",
                    ancestor_tags,
                    depth + 1,
                    child_body_index,
                    inside_sdt,
                )
                continue

            if local == "tbl":
                fp.table_shapes.append(_table_shape(child, child_xpath))
                walk(
                    child,
                    child_xpath,
                    f"{container_path or 'body'}/tbl",
                    ancestor_tags,
                    depth + 1,
                    child_body_index,
                    inside_sdt,
                )
                continue

            if local in _BLOCK_TAGS:
                walk(
                    child,
                    child_xpath,
                    f"{container_path or 'body'}/{local}",
                    ancestor_tags,
                    depth + 1,
                    child_body_index,
                    inside_sdt,
                )
                continue

            # 其它元素（w:r / w:sectPr / …）仍要下探，SDT 可能嵌在 hyperlink 等容器里
            if list(child):
                walk(
                    child,
                    child_xpath,
                    container_path or "body",
                    ancestor_tags,
                    depth + 1,
                    child_body_index,
                    inside_sdt,
                )

    walk(body, "/w:document[1]/w:body[1]", "body", (), 0, -1, False)
    return fp


def _collect_free_text(paragraph: ET.Element) -> str:
    """段落里**不属于任何 SDT** 的 run 文本（Requirement 7.3 的「自由正文」）。"""
    parts: list[str] = []

    def rec(elem: ET.Element) -> None:
        for child in list(elem):
            local = _local(child.tag)
            if local == "sdt":
                continue  # SDT 内的内容不算自由正文
            if local == "t":
                parts.append(child.text or "")
                continue
            if list(child):
                rec(child)

    rec(paragraph)
    return "".join(parts)


def _table_shape(tbl: ET.Element, xpath: str) -> dict[str, Any]:
    """表格形状：行数、每行是否被 row SDT 包裹、每行首格文本。"""
    rows: list[dict[str, Any]] = []
    for child in list(tbl):
        local = _local(child.tag)
        if local == "tr":
            rows.append({"sdt_wrapped": False, "row_tag": None, "cells": _row_cells(child)})
        elif local == "sdt":
            content = child.find(f"{{{_W}}}sdtContent")
            pr = child.find(f"{{{_W}}}sdtPr")
            tag_el = pr.find(f"{{{_W}}}tag") if pr is not None else None
            tag = (tag_el.get(f"{{{_W}}}val") or "") if tag_el is not None else ""
            inner_rows = list(content.findall(f"{{{_W}}}tr")) if content is not None else []
            for tr in inner_rows:
                rows.append({"sdt_wrapped": True, "row_tag": tag, "cells": _row_cells(tr)})
            if not inner_rows:
                rows.append({"sdt_wrapped": True, "row_tag": tag, "cells": [], "empty_sdt": True})
    return {
        "xpath": xpath,
        "row_count": len(rows),
        "sdt_wrapped_row_count": sum(1 for r in rows if r["sdt_wrapped"]),
        "rows": rows,
    }


def _row_cells(tr: ET.Element) -> list[str]:
    return [normalise_text(_node_text(tc))[:40] for tc in tr.findall(f"{{{_W}}}tc")]


def fingerprint_bytes(data: bytes) -> dict[str, Any]:
    return structure_fingerprint(data).to_json()


# ---------------------------------------------------------------------------
# 载体清册（Property 33 的比对对象）
# ---------------------------------------------------------------------------


def sdt_inventory(
    data: bytes,
    *,
    expected_field_keys: Sequence[str] = (),
    expected_row_uuids: Sequence[str] = (),
    expected_table_key: str | None = None,
    expected_sdt_ids: dict[str, str] | None = None,
    expected_body_child_index: dict[str, int] | None = None,
    multi_instance_keys: Sequence[str] = (),
) -> dict[str, Any]:
    """从结构事实投影出四类 Word 载体/能力的清册。

    ``expected_*`` 来自 instrumentation manifest；它们让「载体丢了」与「载体从没注入过」
    这两件事产生**不同**的结论，避免把采集缺口读成通过。

    ``expected_sdt_ids`` / ``expected_body_child_index`` 是两个**伪锚点**的期望值，
    只用于证伪（见模块 docstring 第二条硬约束）。
    """
    fp = structure_fingerprint(data)
    errors = list(fp.errors)
    instances = fp.tag_instances()

    # ---- 载体 1：field 级 SDT（带稳定 w:tag）----
    field_nodes = {
        key: [n for n in nodes if parse_field_tag(n.tag)]
        for key, nodes in ((parse_field_tag(t) or "", v) for t, v in instances.items())
        if key
    }
    present_field_keys = sorted(field_nodes)
    missing_field_keys = sorted(set(expected_field_keys) - set(present_field_keys))
    unexpected_field_keys = sorted(set(present_field_keys) - set(expected_field_keys))
    field_carrier = {
        "present": bool(present_field_keys),
        "field_key_count": len(present_field_keys),
        "field_keys": present_field_keys,
        "missing_field_keys": missing_field_keys,
        "unexpected_field_keys": unexpected_field_keys,
        "instance_count": {k: len(v) for k, v in sorted(field_nodes.items())},
        "kinds": {k: sorted({n.kind for n in v}) for k, v in sorted(field_nodes.items())},
        "values": {
            k: [n.text for n in sorted(v, key=lambda n: n.xpath)]
            for k, v in sorted(field_nodes.items())
        },
        "xpaths": {
            k: [n.xpath for n in sorted(v, key=lambda n: n.xpath)]
            for k, v in sorted(field_nodes.items())
        },
        "run_counts": {
            k: [n.run_count for n in sorted(v, key=lambda n: n.xpath)]
            for k, v in sorted(field_nodes.items())
        },
        "untagged_sdt_count": fp.untagged_sdt_count(),
    }

    # ---- 载体 2：row 级 SDT（tag 内含稳定 row_uuid）----
    row_nodes: list[SdtNode] = [n for n in fp.sdt_nodes if parse_row_tag(n.tag)]
    row_pairs = [parse_row_tag(n.tag) for n in row_nodes]
    table_keys = sorted({p[0] for p in row_pairs if p})
    observed_uuids = [p[1] for p in row_pairs if p]
    if expected_table_key is not None:
        scoped = [p[1] for p in row_pairs if p and p[0] == expected_table_key]
    else:
        scoped = observed_uuids
    duplicates = sorted({u for u in scoped if scoped.count(u) > 1})
    row_carrier = {
        "present": bool(row_nodes),
        "table_keys": table_keys,
        "expected_table_key": expected_table_key,
        "table_key_resolvable": (expected_table_key in table_keys) if expected_table_key else None,
        "row_uuid_count": len(scoped),
        "distinct_row_uuid_count": len(set(scoped)),
        "row_uuids": sorted(set(scoped)),
        "row_uuid_order": scoped,
        "duplicate_row_uuids": duplicates,
        "missing_row_uuids": sorted(set(expected_row_uuids) - set(scoped)),
        "added_row_uuids": sorted(set(scoped) - set(expected_row_uuids)),
        "kinds": sorted({n.kind for n in row_nodes}),
        "all_wrapped_rows_are_row_kind": all(n.kind == "row" for n in row_nodes),
        "rows_without_uuid": _rows_without_uuid(fp, expected_table_key),
        "table_shapes": [
            {
                "xpath": t["xpath"],
                "row_count": t["row_count"],
                "sdt_wrapped_row_count": t["sdt_wrapped_row_count"],
            }
            for t in fp.table_shapes
        ],
    }

    # ---- 载体 3：同一 stable field key 的多实例 ----
    multi = {}
    for key in sorted(set(multi_instance_keys) | {k for k, v in field_nodes.items() if len(v) > 1}):
        nodes = sorted(field_nodes.get(key, []), key=lambda n: n.xpath)
        values = [n.text for n in nodes]
        multi[key] = {
            "instance_count": len(nodes),
            "xpaths": [n.xpath for n in nodes],
            "container_paths": [n.container_path for n in nodes],
            "values": values,
            "values_consistent": len(set(values)) <= 1,
            "distinct_values": sorted(set(values)),
            "all_positions_enumerable": len(nodes) == len([n for n in nodes if n.xpath]),
        }
    multi_carrier = {
        "declared_keys": sorted(set(multi_instance_keys)),
        "keys_with_multiple_instances": sorted(k for k, v in multi.items() if v["instance_count"] > 1),
        "per_key": multi,
    }

    # ---- 载体 4：SDT 外自由正文 ----
    outside = {
        "block_count": len(fp.outside_sdt_blocks),
        "text_digest": _hash_lines(fp.outside_sdt_texts()),
        "texts": fp.outside_sdt_texts(),
        "paragraph_count": fp.paragraph_count,
        "body_child_kinds": fp.body_child_kinds,
    }

    # ---- 伪锚点（只证伪）----
    actual_ids = {
        tag: sorted({n.w_id for n in nodes if n.w_id is not None})
        for tag, nodes in sorted(instances.items())
    }
    id_anchor: dict[str, Any] = {
        "actual_w_ids": actual_ids,
        "distinct_w_id_count": len({n.w_id for n in fp.sdt_nodes if n.w_id is not None}),
        "sdt_with_w_id": sum(1 for n in fp.sdt_nodes if n.w_id is not None),
        "sdt_total": len(fp.sdt_nodes),
    }
    if expected_sdt_ids:
        drift = {
            tag: {"expected": want, "actual": actual_ids.get(tag, [])}
            for tag, want in sorted(expected_sdt_ids.items())
            if actual_ids.get(tag, []) != [want]
        }
        id_anchor["expected_w_ids"] = dict(sorted(expected_sdt_ids.items()))
        id_anchor["drifted_tags"] = sorted(drift)
        id_anchor["drift_detail"] = drift
        id_anchor["anchor_holds"] = not drift
    else:
        id_anchor["anchor_holds"] = None

    actual_index = {
        tag: sorted({n.body_child_index for n in nodes})
        for tag, nodes in sorted(instances.items())
    }
    index_anchor: dict[str, Any] = {"actual_body_child_index": actual_index}
    if expected_body_child_index:
        drift_idx = {
            tag: {"expected": want, "actual": actual_index.get(tag, [])}
            for tag, want in sorted(expected_body_child_index.items())
            if actual_index.get(tag, []) != [want]
        }
        index_anchor["expected_body_child_index"] = dict(sorted(expected_body_child_index.items()))
        index_anchor["drifted_tags"] = sorted(drift_idx)
        index_anchor["drift_detail"] = drift_idx
        index_anchor["anchor_holds"] = not drift_idx
    else:
        index_anchor["anchor_holds"] = None

    return {
        "field_sdt": field_carrier,
        "row_sdt": row_carrier,
        "multi_instance": multi_carrier,
        "outside_sdt_body": outside,
        "hierarchy": fp.hierarchy_map(),
        "kind_map": fp.kind_map(),
        "anchors": {"sdt_w_id": id_anchor, "paragraph_body_index": index_anchor},
        "protected_parts": {k: len(v) for k, v in sorted(fp.protected_parts.items())},
        "fonts_used": fp.fonts_used,
        "aspect_digests": fp.aspect_digests(),
        "errors": errors,
    }


def _rows_without_uuid(fp: DocumentFingerprint, table_key: str | None) -> int:
    """受管表格里**没有** row SDT 包裹的数据行数（Requirement 7.2 的新行判据）。

    受管表格 = 至少有一行被目标 `table_key` 的 row SDT 包裹的那张表；只数它，避免把
    文档里其它未受管表格的行也算进来。
    """
    total = 0
    for shape in fp.table_shapes:
        row_tags = {r.get("row_tag") for r in shape["rows"] if r["sdt_wrapped"]}
        managed = any(
            (parse_row_tag(t or "") or ("", ""))[0] == table_key for t in row_tags
        ) if table_key else bool(row_tags)
        if not managed:
            continue
        total += sum(1 for r in shape["rows"] if not r["sdt_wrapped"])
    return total


# ---------------------------------------------------------------------------
# 保留报告（Requirement 7.3 / 7.9 / Property 33）
# ---------------------------------------------------------------------------


def body_preservation_report(
    before: bytes,
    after: bytes,
    *,
    label_before: str = "before",
    label_after: str = "after",
    allow_added_outside_texts: Sequence[str] = (),
    allow_removed_outside_texts: Sequence[str] = (),
    allow_tag_additions: bool = True,
) -> dict[str, Any]:
    """逐 aspect 比较两份 DOCX 的载体/正文保留情况。

    Property 33 的口径是「**不减少**」而不是「完全相等」：tag/层级/row_uuid 集合允许新增
    （OO 内新增行会带来新 tag），但不允许缺失。`outside_sdt_text` 的允许增删由
    ``allow_added_outside_texts`` / ``allow_removed_outside_texts`` 显式声明 ——
    在 OO 里主动改过的正文必须**列出来**，不能靠放宽判据蒙过去。
    """
    fp_a = structure_fingerprint(before)
    fp_b = structure_fingerprint(after)

    tags_a, tags_b = set(fp_a.tag_set()), set(fp_b.tag_set())
    lost_tags = sorted(tags_a - tags_b)
    new_tags = sorted(tags_b - tags_a)

    hier_a, hier_b = fp_a.hierarchy_map(), fp_b.hierarchy_map()
    hierarchy_diffs = {
        tag: {"before": hier_a[tag], "after": hier_b.get(tag, [])}
        for tag in sorted(tags_a & tags_b)
        if hier_a[tag] != hier_b.get(tag, [])
    }

    ru_a, ru_b = fp_a.row_uuids(), fp_b.row_uuids()
    lost_uuids = {
        k: sorted(set(v) - set(ru_b.get(k, [])))
        for k, v in sorted(ru_a.items())
        if set(v) - set(ru_b.get(k, []))
    }
    new_uuids = {
        k: sorted(set(v) - set(ru_a.get(k, [])))
        for k, v in sorted(ru_b.items())
        if set(v) - set(ru_a.get(k, []))
    }

    out_a, out_b = fp_a.outside_sdt_texts(), fp_b.outside_sdt_texts()
    allowed_add = {normalise_text(t) for t in allow_added_outside_texts}
    allowed_del = {normalise_text(t) for t in allow_removed_outside_texts}
    removed_outside = [
        t for t in out_a if t not in out_b and not any(a in t or t in a for a in allowed_del)
    ]
    added_outside = [
        t for t in out_b if t not in out_a and not any(a in t or t in a for a in allowed_add)
    ]

    shapes_a = [(s["row_count"], s["sdt_wrapped_row_count"]) for s in fp_a.table_shapes]
    shapes_b = [(s["row_count"], s["sdt_wrapped_row_count"]) for s in fp_b.table_shapes]

    parts_a = {k: len(v) for k, v in fp_a.protected_parts.items()}
    parts_b = {k: len(v) for k, v in fp_b.protected_parts.items()}
    part_regressions = {
        k: {"before": n, "after": parts_b.get(k, 0)}
        for k, n in sorted(parts_a.items())
        if parts_b.get(k, 0) < n
    }

    verdicts = {
        "sdt_tag_set": not lost_tags and (allow_tag_additions or not new_tags),
        "sdt_hierarchy": not hierarchy_diffs,
        "row_uuid_set": not lost_uuids,
        "outside_sdt_text": not removed_outside and not added_outside,
        "table_shape": len(shapes_a) == len(shapes_b),
        "protected_parts": not part_regressions,
    }
    return {
        "label_before": label_before,
        "label_after": label_after,
        "aspect_verdicts": verdicts,
        "preserved": all(verdicts.values()),
        "aspects": {
            "sdt_tag_set": {
                "before_count": len(tags_a),
                "after_count": len(tags_b),
                "lost_tags": lost_tags,
                "new_tags": new_tags,
                "diff_count": len(lost_tags) + (0 if allow_tag_additions else len(new_tags)),
            },
            "sdt_hierarchy": {"diff_count": len(hierarchy_diffs), "diffs": hierarchy_diffs},
            "row_uuid_set": {
                "diff_count": sum(len(v) for v in lost_uuids.values()),
                "lost": lost_uuids,
                "new": new_uuids,
            },
            "outside_sdt_text": {
                "before_count": len(out_a),
                "after_count": len(out_b),
                "removed": removed_outside[:20],
                "added": added_outside[:20],
                "diff_count": len(removed_outside) + len(added_outside),
                "declared_allowed_added": sorted(allowed_add),
                "declared_allowed_removed": sorted(allowed_del),
            },
            "table_shape": {
                "before": shapes_a,
                "after": shapes_b,
                "diff_count": 0 if shapes_a == shapes_b else 1,
            },
            "protected_parts": {
                "before": parts_a,
                "after": parts_b,
                "regressions": part_regressions,
                "diff_count": len(part_regressions),
            },
        },
        "collection_errors": {label_before: fp_a.errors, label_after: fp_b.errors},
        "fonts": {label_before: fp_a.fonts_used, label_after: fp_b.fonts_used},
    }
