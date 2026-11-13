"""合并底稿稳定 sheet/row/cell 身份（批 6 / ADR-CRW-006 / 任务 6.3）。

合并薄壳（``A3-CONSOL`` 的 ``WorkingPaper``）复用通用 ``EvidenceLink``：证据按
``EvidenceLink.wp_id = 壳的 working_paper_id`` 挂，位置用稳定的
``node:<key>/row:<identity>/col:<identity>`` 写进 ``EvidenceLink.cell_ref``，
``sheet_name`` 放合并表键（``sheet_key`` / ``consol_trial`` / ``consol_report`` /
``section_id``）。**绝不只用行号**（R8.3 / ADR-CRW-006）。

关键不变量（任务 6.3 / 插删行身份不漂移）
------------------------------------------------------------------
行身份派生自权威业务键，不派生自数组下标：

- ``consol_trial`` / ``consol_report`` 行：``standard_account_code``（科目码天然稳定）。
- ``consol_note_data`` 行：优先读行内稳定 id（``_rid`` / ``row_id`` / ``id`` / ``key``），
  否则按行的业务标识字段（科目 / 名称 / 项目名）内容 SHA 得 ``h:<摘要>``。
- ``consol_worksheet_data`` 行：优先读行内稳定 id，否则按业务标识字段内容 SHA。

因此在某行之前插入 / 删除另一行，**不改变**该行自身的 ``node:.../row:...`` 串，
证据不会漂到相邻行。只有当行自身的业务键被改掉时身份才变（符合预期：那已是另一行）。

本模块只做**身份映射与解析**；上传 / 引用 / 小眼睛预览 / EvidenceLink 落库全部复用既有
``workpaper_evidence_intake`` + ``wp_evidence_service``（本 spec 对附件 owner 单向依赖，不重建）。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

# ─── 常量 ──────────────────────────────────────────────────────────────────

#: cell_ref 身份串的段分隔符与前缀
_NODE = "node:"
_ROW = "row:"
_COL = "col:"
_SEP = "/"

#: 行自带稳定 id 的候选字段（按优先级）；任何一个非空即作行身份，不读数组下标
_ROW_ID_FIELDS: tuple[str, ...] = ("_rid", "row_id", "rowId", "rowKey", "id", "key", "uid")

#: 没有稳定 id 时，参与内容摘要的业务标识字段（按此集合求稳定行身份）
_ROW_BUSINESS_FIELDS: tuple[str, ...] = (
    "standard_account_code", "account_code", "code",
    "company_code", "entity_code", "subsidiary_code",
    "item", "item_name", "project_name", "name", "account_name", "label",
    "section_id", "node_key", "row_no", "seq",
)

#: 内容摘要截断长度（十六进制字符数）——足够避免同表内碰撞，又让 cell_ref 不超 100 字
_DIGEST_LEN = 16

#: EvidenceLink.cell_ref 列上限（V213：VARCHAR(100)）
MAX_CELL_REF = 100


# ─── 行身份派生（无漂移核心）─────────────────────────────────────────────────


def _clean(value: Any) -> str:
    """值规范化：None → ''；去首尾空白；统一成字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def _digest(parts: list[str]) -> str:
    """把若干字段值拼成稳定内容摘要（NUL 分隔避免歧义）。"""
    raw = "\x00".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_DIGEST_LEN]


def stable_row_identity(row: Any) -> str:
    """从一行（dict）派生稳定行身份，**不依赖数组下标**。

    1. 行自带稳定 id（``_rid`` / ``row_id`` / ``id`` / ``key`` ...）⇒ ``id:<值>``；
    2. 否则按业务标识字段内容摘要 ⇒ ``h:<摘要>``；
    3. 两者都取不到（纯空行）⇒ ``h:<空摘要>``（调用方应避免给纯空行挂证据）。

    同一行内容在插删别的行前后调用，结果恒定；只有本行业务键改变才变。
    """
    if not isinstance(row, dict):
        # 标量 / 列表行：按其字符串内容摘要（仍不含位置）
        return "h:" + _digest([_clean(row)])

    for field in _ROW_ID_FIELDS:
        if field in row:
            raw = _clean(row.get(field))
            if raw:
                return "id:" + _sanitize_segment(raw)

    parts = [_clean(row.get(field)) for field in _ROW_BUSINESS_FIELDS if field in row]
    # 没有任何已知业务字段时，退回对整行键值对的稳定摘要（排序保证顺序无关）
    if not any(parts):
        parts = [f"{k}={_clean(v)}" for k, v in sorted(row.items()) if not str(k).startswith("_")]
    return "h:" + _digest(parts)


# ─── 段清洗与合成 ────────────────────────────────────────────────────────────

# cell_ref 里用 `/` 和 `:` 做结构分隔，业务值里出现时转义，解析才能无歧义还原
_ESCAPE_MAP = {"%": "%25", "/": "%2F", ":": "%3A"}
_UNESCAPE_RE = re.compile(r"%(25|2F|3A)")
_UNESCAPE_MAP = {"25": "%", "2F": "/", "3A": ":"}


def _sanitize_segment(value: str) -> str:
    """把结构分隔符转义，使其能安全放进 cell_ref 段（先转义 %，再转义 / 与 :）。"""
    out = value.replace("%", _ESCAPE_MAP["%"])
    out = out.replace("/", _ESCAPE_MAP["/"])
    out = out.replace(":", _ESCAPE_MAP[":"])
    return out


def _desanitize_segment(value: str) -> str:
    return _UNESCAPE_RE.sub(lambda m: _UNESCAPE_MAP[m.group(1)], value)


@dataclass(frozen=True)
class ConsolCellIdentity:
    """解析后的合并单元格身份。``row_identity`` / ``col_identity`` 可空（节点级 / 行级证据）。"""

    node_key: str
    row_identity: str | None = None
    col_identity: str | None = None

    def to_cell_ref(self) -> str:
        """合成 ``node:<key>[/row:<identity>][/col:<identity>]``；超长按业务键摘要压缩（身份仍稳定）。"""
        parts = [_NODE + _sanitize_segment(self.node_key)]
        if self.row_identity:
            parts.append(_ROW + _sanitize_segment(self.row_identity))
        if self.col_identity:
            parts.append(_COL + _sanitize_segment(self.col_identity))
        cell_ref = _SEP.join(parts)
        if len(cell_ref) <= MAX_CELL_REF:
            return cell_ref
        # 超长：把 node/row/col 各自摘要化（仍只依赖业务值，无位置、可重算、无漂移）
        return _compress_cell_ref(self.node_key, self.row_identity, self.col_identity)


def _compress_cell_ref(node_key: str, row_identity: str | None, col_identity: str | None) -> str:
    node_seg = _NODE + "h:" + _digest([_clean(node_key)])
    parts = [node_seg]
    if row_identity:
        parts.append(_ROW + "h:" + _digest([_clean(row_identity)]))
    if col_identity:
        parts.append(_COL + "h:" + _digest([_clean(col_identity)]))
    return _SEP.join(parts)


def build_cell_ref(node_key: str, row_identity: str | None = None, col_identity: str | None = None) -> str:
    """便捷合成：等价 ``ConsolCellIdentity(...).to_cell_ref()``。"""
    return ConsolCellIdentity(node_key=node_key, row_identity=row_identity, col_identity=col_identity).to_cell_ref()


def parse_cell_ref(cell_ref: str | None) -> ConsolCellIdentity | None:
    """解析 ``node:.../row:.../col:...``；非本 scheme（旧 A1 / item: / row:{n}）返回 None。"""
    text = (cell_ref or "").strip()
    if not text.startswith(_NODE):
        return None
    node_key: str | None = None
    row_identity: str | None = None
    col_identity: str | None = None
    for seg in text.split(_SEP):
        if seg.startswith(_NODE):
            node_key = _desanitize_segment(seg[len(_NODE):])
        elif seg.startswith(_ROW):
            row_identity = _desanitize_segment(seg[len(_ROW):])
        elif seg.startswith(_COL):
            col_identity = _desanitize_segment(seg[len(_COL):])
    if not node_key:
        return None
    return ConsolCellIdentity(node_key=node_key, row_identity=row_identity or None, col_identity=col_identity or None)


# ─── 从权威源构造身份（按 sheet 类型分派）─────────────────────────────────────


def trial_row_cell_ref(standard_account_code: str, *, col: str | None = None) -> str:
    """合并试算表行：行身份 = 科目码（天然稳定，插删科目不漂移）。"""
    return build_cell_ref("consol_trial", row_identity="id:" + _sanitize_segment(_clean(standard_account_code)), col_identity=col)


def report_row_cell_ref(line_key: str, *, col: str | None = None) -> str:
    """合并报表行：行身份 = 报表行键（报表项目码 / 行次键，稳定）。"""
    return build_cell_ref("consol_report", row_identity="id:" + _sanitize_segment(_clean(line_key)), col_identity=col)


def note_row_cell_ref(section_id: str, row: Any, *, node_key: str | None = None, col: str | None = None) -> str:
    """合并附注行：节点 = ``section_id``（带 node_key 时拼 ``section_id@node_key``），
    行身份从行内容派生（无漂移）。"""
    node = section_id if not node_key else f"{section_id}@{node_key}"
    return build_cell_ref(node, row_identity=stable_row_identity(row), col_identity=col)


def worksheet_row_cell_ref(sheet_key: str, row: Any, *, col: str | None = None) -> str:
    """合并工作底稿行：节点 = ``sheet_key``，行身份从行内容派生（无漂移）。"""
    return build_cell_ref(sheet_key, row_identity=stable_row_identity(row), col_identity=col)


__all__ = [
    "MAX_CELL_REF",
    "ConsolCellIdentity",
    "stable_row_identity",
    "build_cell_ref",
    "parse_cell_ref",
    "trial_row_cell_ref",
    "report_row_cell_ref",
    "note_row_cell_ref",
    "worksheet_row_cell_ref",
]
