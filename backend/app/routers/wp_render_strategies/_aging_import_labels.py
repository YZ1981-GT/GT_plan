"""账龄导入 label 匹配工具 — 按列头 label 匹配当前配置的 segment。

导入 XLSX 时，解析列头中的账龄标签（如 "1年以内(期初)", "审定账龄(1~2年)"），
按 label 文本匹配当前项目配置的 segments，将值映射到 nested aging 结构。

核心规则：
- 不匹配的列报 warning 并跳过（不丢弃数据行，只跳过该列的值）
- 配置变更后导入旧模板时尝试按 label 映射（最大兼容）
- 支持多种 header 格式：
  · D2 风格: "{label}(期初)" / "{label}(期末)" / "{label}(审定)"
  · D3/F1 风格: "期初审定账龄({label})" / "审定账龄({label})"
  · K1/K3/G5 风格: 纯 label（如 "1年内", "1-2年"）
- label 匹配时去除空白、统一"年以下"→"年以内"、"~"→"-"等常见变体

设计文档 Property 13:
> For any imported XLSX with aging column headers labeled with segment names and any
> matching project aging config, the import service SHALL correctly map each column's values
> to the corresponding segment key in the nested aging structure. Columns whose labels do
> not match any current segment SHALL be skipped with warnings.

Requirements: 8.2, 8.3, 8.4
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.aging_config_service import AgingSegment


# ─── Label 标准化 ─────────────────────────────────────────────────────────────


def _normalize_label(text: str) -> str:
    """标准化账龄 label 用于模糊匹配。

    处理常见变体：
    - 去除首尾空白
    - 全角→半角括号
    - "~" → "-"
    - "年以下" → "年以内"
    - "以上" 保持不变
    - 去除多余空格
    """
    s = text.strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("～", "-").replace("~", "-")
    s = s.replace("年以下", "年以内")
    s = re.sub(r"\s+", "", s)
    return s


# ─── Header 解析 ──────────────────────────────────────────────────────────────

# 可识别的 period 后缀/前缀 pattern
_PERIOD_SUFFIXES: dict[str, str] = {
    "(期初)": "prior",
    "(期末)": "current",
    "(期末未审)": "current",
    "(审定)": "audited",
    "(期末审定)": "audited",
}

_PERIOD_PREFIXES: dict[str, str] = {
    "期初审定账龄": "prior",
    "期初账龄": "prior",
    "审定账龄": "audited",
    "期末审定账龄": "audited",
    "期末账龄": "current",
}


@dataclass
class ParsedAgingHeader:
    """解析后的账龄列头。"""
    original: str           # 原始列头文本
    label: str              # 提取的段名 (标准化后)
    label_raw: str          # 提取的段名 (原始)
    period: str             # "prior" | "current" | "audited"
    col_index: int          # 列索引 (0-based)


@dataclass
class AgingImportResult:
    """账龄导入匹配结果。"""
    matched_headers: list[ParsedAgingHeader] = field(default_factory=list)
    unmatched_headers: list[str] = field(default_factory=list)
    segment_key_map: dict[str, str] = field(default_factory=dict)  # normalized_label → segment.key


def parse_aging_header(header: str, col_index: int) -> ParsedAgingHeader | None:
    """尝试将单个列头解析为账龄段。

    返回 ParsedAgingHeader 或 None（不是账龄列头时）。
    """
    normalized = _normalize_label(header)

    # 尝试后缀 pattern: "{label}(期初)" etc.
    for suffix, period in _PERIOD_SUFFIXES.items():
        norm_suffix = _normalize_label(suffix)
        if normalized.endswith(norm_suffix):
            label_raw = normalized[: -len(norm_suffix)]
            if label_raw:
                return ParsedAgingHeader(
                    original=header,
                    label=label_raw,
                    label_raw=header.strip()[:-(len(suffix))].strip() if header.strip().endswith(suffix.replace("(", "（").replace(")", "）")) or header.strip().endswith(suffix) else label_raw,
                    period=period,
                    col_index=col_index,
                )

    # 尝试前缀 pattern: "期初审定账龄({label})" etc.
    for prefix, period in _PERIOD_PREFIXES.items():
        norm_prefix = _normalize_label(prefix)
        if normalized.startswith(norm_prefix):
            # 提取括号中的 label
            rest = normalized[len(norm_prefix):]
            if rest.startswith("(") and rest.endswith(")"):
                label_raw = rest[1:-1]
                if label_raw:
                    return ParsedAgingHeader(
                        original=header,
                        label=label_raw,
                        label_raw=label_raw,
                        period=period,
                        col_index=col_index,
                    )

    return None


# ─── Label 匹配引擎 ──────────────────────────────────────────────────────────


def build_label_index(segments: "list[AgingSegment]") -> dict[str, str]:
    """构建 normalized_label → segment.key 的查找索引。

    一个 segment 可能有多种 label 变体能匹配到它：
    - 标准 label (如 "1年以内")
    - "年以下" 变体 (如 "1年以下" → "1年以内")
    - "~" 变体 (如 "1~2年" → "1-2年")
    """
    index: dict[str, str] = {}
    for seg in segments:
        norm = _normalize_label(seg.label)
        index[norm] = seg.key

        # 生成额外变体以提高匹配率
        # "1年以内" → 也能匹配 "1年内"
        if "年以内" in norm:
            index[norm.replace("年以内", "年内")] = seg.key
        # "5年以上" → 也能匹配 "5年以上"（已是规范形式，但加上 >5 之类不太合理）
    return index


def match_aging_headers(
    actual_headers: list[str],
    segments: "list[AgingSegment]",
    *,
    is_three_period: bool = True,
    single_period: str | None = None,
) -> AgingImportResult:
    """匹配导入 XLSX 的列头与当前项目配置的 segments。

    Args:
        actual_headers: XLSX 第一行的列头文本列表
        segments: 当前项目的有效账龄段列表
        is_three_period: True=D2/K1/K3/G5 (3 period), False=D3/F1 (2 period)
        single_period: 若非 None，则所有账龄列均视为该 period（如 K1-2 纯期末账龄）

    Returns:
        AgingImportResult 含匹配结果和未匹配列名列表
    """
    label_index = build_label_index(segments)
    result = AgingImportResult(segment_key_map=label_index)

    for col_idx, header_text in enumerate(actual_headers):
        if not header_text or not header_text.strip():
            continue

        # 先尝试结构化解析（带 period 后缀/前缀）
        parsed = parse_aging_header(header_text, col_idx)
        if parsed:
            # 检查 label 是否匹配当前 segments
            if parsed.label in label_index:
                parsed_copy = ParsedAgingHeader(
                    original=parsed.original,
                    label=parsed.label,
                    label_raw=parsed.label_raw,
                    period=parsed.period,
                    col_index=col_idx,
                )
                result.matched_headers.append(parsed_copy)
            else:
                result.unmatched_headers.append(header_text.strip())
            continue

        # 如果没有 period 后缀/前缀，尝试作为纯 label 匹配（K1/K3/G5 风格）
        if single_period:
            norm = _normalize_label(header_text)
            if norm in label_index:
                result.matched_headers.append(ParsedAgingHeader(
                    original=header_text,
                    label=norm,
                    label_raw=header_text.strip(),
                    period=single_period,
                    col_index=col_idx,
                ))
            # 纯 label 没匹配到不算 aging 列，不报 warning

    return result


# ─── 行数据提取 ───────────────────────────────────────────────────────────────


def extract_aging_values(
    row_values: tuple | list,
    matched_headers: list[ParsedAgingHeader],
    segments: "list[AgingSegment]",
    label_index: dict[str, str],
) -> dict[str, dict[str, float]]:
    """从一行数据中提取账龄值到 nested 结构。

    Returns:
        { "prior": {key: val, ...}, "current": {...}, "audited": {...} }
        只含匹配到的 period。
    """
    result: dict[str, dict[str, float]] = {}

    for ph in matched_headers:
        seg_key = label_index.get(ph.label)
        if not seg_key:
            continue

        # 安全取值
        val = 0.0
        if ph.col_index < len(row_values):
            raw_val = row_values[ph.col_index]
            if raw_val is not None:
                try:
                    val = float(raw_val)
                except (ValueError, TypeError):
                    val = 0.0

        period = ph.period
        if period not in result:
            result[period] = {}
        result[period][seg_key] = val

    # 确保所有 segments 都有值 (匹配到的 period 中)
    for period_data in result.values():
        for seg in segments:
            if seg.key not in period_data:
                period_data[seg.key] = 0.0

    return result


def build_nested_aging_from_row(
    row_values: tuple | list,
    matched_headers: list[ParsedAgingHeader],
    segments: "list[AgingSegment]",
    label_index: dict[str, str],
    *,
    is_three_period: bool = True,
) -> dict[str, dict[str, float]]:
    """从一行数据中构建完整的 nested aging 对象。

    Returns:
        对于 3-period: { "agingPrior": {...}, "agingCurrent": {...}, "agingAudited": {...} }
        对于 2-period: { "agingPrior": {...}, "agingAudited": {...} }
    """
    extracted = extract_aging_values(row_values, matched_headers, segments, label_index)

    # 构建初始化为 0 的完整结构
    zero_data = {seg.key: 0.0 for seg in segments}

    result: dict[str, dict[str, float]] = {
        "agingPrior": {**zero_data, **extracted.get("prior", {})},
        "agingAudited": {**zero_data, **extracted.get("audited", {})},
    }
    if is_three_period:
        result["agingCurrent"] = {**zero_data, **extracted.get("current", {})}

    return result


# ─── 便捷函数：完整导入流程 ──────────────────────────────────────────────────


def import_aging_columns_from_headers(
    actual_headers: list[str],
    segments: "list[AgingSegment]",
    *,
    is_three_period: bool = True,
    single_period: str | None = None,
) -> tuple[AgingImportResult, list[str]]:
    """一步完成列头匹配 + 返回 warnings。

    Returns:
        (AgingImportResult, warnings) — warnings 是不匹配列头的提示列表
    """
    result = match_aging_headers(
        actual_headers, segments,
        is_three_period=is_three_period,
        single_period=single_period,
    )
    warnings: list[str] = []
    if result.unmatched_headers:
        cols_str = ", ".join(result.unmatched_headers[:10])
        if len(result.unmatched_headers) > 10:
            cols_str += f" 等共{len(result.unmatched_headers)}列"
        warnings.append(f"以下账龄列不匹配当前配置，已跳过: {cols_str}")

    return result, warnings
