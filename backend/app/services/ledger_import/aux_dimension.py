"""辅助维度解析 — 6 种格式 + 多维组合。

职责（见 design.md §6 / Sprint 2 Task 24-26）：

7 种单维格式按顺序尝试，首个命中即返回：

1. JSON          : `{"客户":"001","项目":"P01"}`
2. colon_code_name: `类型:编码 名称` / `类型：编码 名称`
3. slash_separated: `类型/编码/名称`
4. pipe_separated : `类型|编码|名称`
5. colon_name_only: `类型: 名称`（无编码）
6. code_name      : `编码 名称`（无类型）
7. arrow          : `类型 -> 名称` / `类型 → 名称`

多维组合：按 `,` 或 `;`、`；` 分隔后逐段解析。

列自动识别：detect_aux_columns 根据表头关键词判断哪些列可能是辅助维度。
"""

from __future__ import annotations

import json
import re
from typing import Optional

__all__ = ["parse_aux_dimension", "detect_aux_columns", "PATTERNS"]

# 顺序匹配，首个命中即返回
PATTERNS: list[tuple[str, str]] = [
    # JSON: {"客户":"001","项目":"P01"}
    (r"^\{.*\}$", "json"),
    # 类型:编码,名称 | 类型：编码,名称（旧引擎格式，对齐 write_four_tables）
    (r"^(?P<type>[^:：/|]+)[:：](?P<code>[^,，\s]+)[,，](?P<name>.+)$", "colon_code_comma_name"),
    # 类型:编码 名称 | 类型：编码 名称
    (r"^(?P<type>[^:：/|]+)[:：](?P<code>\S+)\s+(?P<name>.+)$", "colon_code_name"),
    # 类型/编码/名称
    (r"^(?P<type>[^/]+)/(?P<code>[^/]+)/(?P<name>.+)$", "slash_separated"),
    # 类型|编码|名称
    (r"^(?P<type>[^|]+)\|(?P<code>[^|]+)\|(?P<name>.+)$", "pipe_separated"),
    # 类型: 名称（无编码）
    (r"^(?P<type>[^:：]+)[:：]\s*(?P<name>.+)$", "colon_name_only"),
    # 编码 名称（无类型）
    (r"^(?P<code>[A-Z0-9]+)\s+(?P<name>.+)$", "code_name"),
    # 箭头: 项目 -> 研发部
    (r"^(?P<type>[^→\->]+?)\s*[->→]+\s*(?P<name>.+)$", "arrow"),
]

# 辅助维度列识别关键词（case-insensitive substring match）
_AUX_KEYWORDS: list[str] = [
    "核算项目",
    "辅助核算",
    "辅助项目",
    "客户",
    "供应商",
    "项目",
    "部门",
    "员工",
    "存货",
    "往来",
    "auxiliary",
    "dimension",
]


def parse_aux_dimension(raw: Optional[str]) -> list[dict]:
    """解析辅助维度字符串，返回维度列表 [{"aux_type", "aux_code", "aux_name"}]。

    - 空/None 输入返回 []
    - 多维度首选 ; 或 ； 分隔（强分隔符）
    - 逗号 `,` 可作为多维度分隔（仅当后段以 `类型:` 开头时，
      避免误切"类型:编码,名称"这种单维度格式）
    - 无法解析的段返回 {"aux_type": None, "aux_code": None, "aux_name": raw_part}
    """
    if not raw or not raw.strip():
        return []
    raw = raw.strip()

    # JSON 特殊处理：整体是 JSON 对象时不做分隔
    if raw.startswith("{") and raw.endswith("}"):
        try:
            obj = json.loads(raw)
            result: list[dict] = []
            for k, v in obj.items():
                result.append({
                    "aux_type": k,
                    "aux_code": None,
                    "aux_name": str(v),
                })
            return result
        except (json.JSONDecodeError, TypeError, ValueError):
            pass  # 不是合法 JSON，走正常分隔逻辑

    # 优先按 ; 或 ； 分隔（强分隔符）
    if re.search(r"[;；]", raw):
        parts = re.split(r"[;；]\s*", raw)
    else:
        # 智能逗号分隔：仅当逗号后段以 "xxx:" 开头（即另一个类型）才切
        # 这样既支持 "客户:001 北京某科技,项目:P01 新产品"（多维度）
        # 又支持 "金融机构:YG0001,工商银行"（单维度，类型:编码,名称）
        parts = _smart_comma_split(raw)

    result: list[dict] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        _parse_single_dimension(part, result)

    return result


def _smart_comma_split(raw: str) -> list[str]:
    """智能逗号分隔：只在"逗号后紧接类型:"的地方切分。

    例：
    - "客户:001 北京某科技,项目:P01 新产品" → 2 段（项目:... 是新类型）
    - "金融机构:YG0001,工商银行" → 1 段（工商银行不含 `:`）
    - "类型A:001,名称A;类型B:002,名称B" → 已被 ; 预切分，不走此函数
    """
    parts: list[str] = []
    # 用 lookahead 查找"逗号后跟着'xxx:'"的位置作为分隔点
    # pattern: `,` 后紧跟 非冒号非逗号字符 + `:/：`
    splits = re.split(r"[,，](?=[^:：,，]+[:：])", raw)
    return splits


def _parse_single_dimension(part: str, result: list[dict]) -> None:
    """解析单个维度段，将结果追加到 result 列表。"""
    for pattern, fmt in PATTERNS:
        m = re.match(pattern, part)
        if m:
            if fmt == "json":
                try:
                    obj = json.loads(part)
                    for k, v in obj.items():
                        result.append({
                            "aux_type": k,
                            "aux_code": None,
                            "aux_name": str(v),
                        })
                except (json.JSONDecodeError, TypeError, ValueError):
                    # JSON 解析失败，当作不可解析
                    result.append({
                        "aux_type": None,
                        "aux_code": None,
                        "aux_name": part,
                    })
                return

            gd = m.groupdict()
            result.append({
                "aux_type": gd.get("type", "").strip() or None,
                "aux_code": gd.get("code", "").strip() or None,
                "aux_name": gd.get("name", "").strip() or None,
            })
            return

    # 无法解析，原样存
    result.append({"aux_type": None, "aux_code": None, "aux_name": part})


def detect_aux_columns(headers: list[str]) -> list[int]:
    """根据表头名称启发式识别辅助维度列，返回 0-based 列索引列表。

    匹配规则：header 去空白后，若包含任一 _AUX_KEYWORDS 关键词（不区分大小写），
    则认为该列可能是辅助维度列。
    """
    indices: list[int] = []
    for i, header in enumerate(headers):
        h = header.strip().lower()
        if any(kw.lower() in h for kw in _AUX_KEYWORDS):
            indices.append(i)
    return indices
