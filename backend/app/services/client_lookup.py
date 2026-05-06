"""客户串联辅助

用于跨年/跨项目识别同一客户。在 R3 需求 7 引入后，应由 R3 统一提供
``resolve_same_client``；本文件作为 R5 需求 7 的兜底实现，当 R3 落地后
应把此处的 ``normalize_client_name`` 迁移到 R3 的模块。

归一规则（v1）：
- 去除首尾空白
- 统一全角逗号/句号/括号到半角
- 删除常见公司后缀变体（有限公司/股份有限公司/集团有限公司/Co.,Ltd/Inc./ Ltd. / Group）
- 大小写统一为小写（中文不受影响）

真实匹配策略：先归一后精确相等。Round 6+ 可升级为模糊匹配（Levenshtein）。
"""

from __future__ import annotations

import re

_SUFFIX_PATTERNS = [
    r"股份有限公司$",
    r"有限责任公司$",
    r"有限公司$",
    r"集团股份有限公司$",
    r"集团有限公司$",
    r"集团公司$",
    r"\(集团\)$",
    r"\(中国\)$",
    r"\s*co\.?\s*,?\s*ltd\.?$",
    r"\s*inc\.?$",
    r"\s*group$",
    r"\s*corp\.?$",
    r"\s*company$",
]

_FULLWIDTH_MAP = str.maketrans({
    "，": ",", "。": ".", "（": "(", "）": ")",
    "：": ":", "；": ";", "、": ",",
})


def normalize_client_name(name: str | None) -> str:
    """归一化客户名称用于跨年匹配。"""
    if not name:
        return ""
    s = name.strip()
    s = s.translate(_FULLWIDTH_MAP)
    s_lower = s.lower()
    for pattern in _SUFFIX_PATTERNS:
        s_lower = re.sub(pattern, "", s_lower, flags=re.IGNORECASE)
    return s_lower.strip()


def client_names_match(a: str | None, b: str | None) -> bool:
    """判断两个客户名称是否指向同一客户（归一后相等）。"""
    na = normalize_client_name(a)
    nb = normalize_client_name(b)
    if not na or not nb:
        return False
    return na == nb
