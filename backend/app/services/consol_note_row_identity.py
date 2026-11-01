"""合并附注行身份统一规范化（spec note-table-structure-formula-pull-closure R17 / ADR-13）。

映射建议、分组、已保存行保护和父节点汇总共享同一行身份比较键。
「字面规范化」= 去空白、去编制提示、去可选行方括号、括号全角、区间连接符统一、去尾冒号
（``_label_key`` 的规范化）。与 ``consol_note_detail_suggest._label_key`` 同口径但从本模块导出，
各消费方统一 import 这一份。

不改结构指纹（``compute_source_structure_hash``），避免全量 stale。
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["note_row_key"]

_LABEL_WS = str.maketrans("", "", " \t\r\n\u3000")
_RANGE_RE = re.compile(r"(\d+)[-－—–~～至到](\d+)(?=年|个月|月|天|日)")
_HINT_RE = re.compile(r"【[^】]*】")
_OPTIONAL_RE = re.compile(r"[\[［](.+)[\]］]")
_PARENS = str.maketrans({"(": "（", ")": "）"})


def note_row_key(label: Any) -> str:
    """附注专用行名比较键（与 ``_label_key`` 同口径，公开导出供各模块统一消费）。"""
    raw = str(label or "").translate(_LABEL_WS)
    s = _HINT_RE.sub("", raw) or raw
    if optional := _OPTIONAL_RE.fullmatch(s):
        s = optional.group(1)
    s = _RANGE_RE.sub(r"\1至\2", s.translate(_PARENS))
    return s.rstrip(":").rstrip("：")
