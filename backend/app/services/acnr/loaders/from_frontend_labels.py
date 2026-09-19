"""Loader: 14 份 *SheetLabels.ts → sheet_name_aliases。

读取前端 `audit-platform/frontend/src/components/workpaper/composables/*SheetLabels.ts`，
提取 LABEL_MAP 对象中的 {sheet_code → label_value}，转为 {sheet_code → list[aliases]}。

Requirements: 3.2, 22.4
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_LABELS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "composables"
)

_LABELS_FILE_PATTERN = re.compile(r"^[a-z]\d*SheetLabels\.ts$")

# 匹配 TS 对象中的键值对：'D2-2': '明细表D2-2', 或 "D2-2": "明细表D2-2"
# 也匹配无引号的键：D5: '底稿目录'
_KV_RE = re.compile(
    r"""
    [\s,{]                       # 前导空白/逗号/花括号
    ['"]?([A-Za-z0-9\u4e00-\u9fff-]+)['"]?  # 键（可有可无引号）
    \s*:\s*                       # 冒号分隔
    ['"]([^'"]+)['"]              # 值（引号包裹的字符串）
    """,
    re.VERBOSE,
)

# 匹配 LABEL_MAP / SHEET_LABEL_MAP 变量赋值块
_MAP_BLOCK_RE = re.compile(
    r"(?:SHEET_LABEL_MAP|LABEL_MAP)\s*(?::\s*Record<[^>]+>)?\s*=\s*\{([^}]+)\}",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def load_sheet_name_aliases(
    *,
    labels_dir: Path | None = None,
) -> dict[str, list[str]]:
    """从 14 份 *SheetLabels.ts 提取 sheet_name_aliases。

    Parameters
    ----------
    labels_dir
        SheetLabels.ts 文件所在目录（默认前端 composables 目录）。

    Returns
    -------
    dict[str, list[str]]
        键为 sheet_code（如 'D2-2'），值为别名列表（去重）。
    """
    base = labels_dir or _LABELS_DIR
    aliases: dict[str, list[str]] = {}

    # 收集所有 *SheetLabels.ts
    if not base.exists():
        return aliases

    label_files = sorted(
        f
        for f in base.iterdir()
        if f.is_file() and _LABELS_FILE_PATTERN.match(f.name)
    )

    for ts_file in label_files:
        content = ts_file.read_text(encoding="utf-8")
        _extract_aliases_from_content(content, aliases)

    return aliases


def _extract_aliases_from_content(
    content: str,
    aliases: dict[str, list[str]],
) -> None:
    """从单个 TS 文件内容中提取别名到 aliases dict。"""
    # 找到所有 LABEL_MAP 块
    blocks = _MAP_BLOCK_RE.findall(content)

    for block in blocks:
        for match in _KV_RE.finditer(block):
            sheet_code = match.group(1)
            label_value = match.group(2)

            # 跳过空值和纯 sheet_code 重复
            if not label_value or label_value == sheet_code:
                continue

            if sheet_code not in aliases:
                aliases[sheet_code] = []

            # 去重加入
            if label_value not in aliases[sheet_code]:
                aliases[sheet_code].append(label_value)
