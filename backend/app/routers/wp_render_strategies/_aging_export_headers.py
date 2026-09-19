"""账龄动态列头生成工具 — 供所有往来款明细表导入导出使用。

根据项目账龄配置 (AgingConfigService) 动态生成导出 XLSX 的账龄列头，
替代硬编码的 "1年以内/1-2年/2-3年/3-4年/4-5年/5年以上" 等固定列。

核心规则：
- 3-period subjects (D2/K1/K3/G5): 每段生成 3 列 → `{label}(期初)`, `{label}(期末未审)`, `{label}(期末审定)`
  或按实际需要生成 `{label}(期初)` / `{label}(期末)` / `{label}(审定)` 等变体
- 2-period subjects (D3/F1): 每段生成 2 列 → `{label}(期初)`, `{label}(期末审定)` 或 `期初审定账龄({label})` / `审定账龄({label})` 等

设计文档 Property 12:
> For any bands array of length N derived from a valid aging config, the export service
> SHALL generate column headers containing all N segment labels with appropriate period prefixes,
> resulting in 3N headers for three-period subjects and 2N headers for two-period subjects.

Requirements: 8.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.services.aging_config_service import AgingSegment


# ─── 3-period subjects (D2/K1/K3/G5) ─────────────────────────────────────────


def generate_3period_aging_headers(
    segments: "list[AgingSegment]",
    prior_suffix: str = "(期初)",
    current_suffix: str = "(期末)",
    audited_suffix: str = "(审定)",
) -> list[str]:
    """为 3-period 科目 (D2/K1/K3/G5) 生成账龄列头。

    每段生成 3 列：{label}{prior_suffix}, {label}{current_suffix}, {label}{audited_suffix}
    总计返回 3×N 列头。
    """
    headers: list[str] = []
    for seg in segments:
        headers.append(f"{seg.label}{prior_suffix}")
        headers.append(f"{seg.label}{current_suffix}")
        headers.append(f"{seg.label}{audited_suffix}")
    return headers


def generate_3period_aging_headers_grouped(
    segments: "list[AgingSegment]",
    prior_suffix: str = "(期初)",
    current_suffix: str = "(期末)",
    audited_suffix: str = "(审定)",
) -> tuple[list[str], list[str], list[str]]:
    """为 3-period 科目生成按 period 分组的列头。

    返回 (prior_headers, current_headers, audited_headers) 各含 N 列头。
    """
    prior = [f"{seg.label}{prior_suffix}" for seg in segments]
    current = [f"{seg.label}{current_suffix}" for seg in segments]
    audited = [f"{seg.label}{audited_suffix}" for seg in segments]
    return prior, current, audited


# ─── 2-period subjects (D3/F1) ────────────────────────────────────────────────


def generate_2period_aging_headers(
    segments: "list[AgingSegment]",
    prior_suffix: str = "(期初)",
    audited_suffix: str = "(期末审定)",
) -> list[str]:
    """为 2-period 科目 (D3/F1) 生成账龄列头。

    每段生成 2 列：{label}{prior_suffix}, {label}{audited_suffix}
    总计返回 2×N 列头。
    """
    headers: list[str] = []
    for seg in segments:
        headers.append(f"{seg.label}{prior_suffix}")
        headers.append(f"{seg.label}{audited_suffix}")
    return headers


def generate_2period_aging_headers_grouped(
    segments: "list[AgingSegment]",
    prior_prefix: str = "期初审定账龄",
    audited_prefix: str = "审定账龄",
) -> tuple[list[str], list[str]]:
    """为 2-period 科目生成按 period 分组的列头（D3-2 风格：前缀(段名)）。

    返回 (prior_headers, audited_headers) 各含 N 列头。
    """
    prior = [f"{prior_prefix}({seg.label})" for seg in segments]
    audited = [f"{audited_prefix}({seg.label})" for seg in segments]
    return prior, audited


# ─── 单 period 列头 (K1/K3/G5 等只有期末账龄) ─────────────────────────────────


def generate_single_period_aging_headers(
    segments: "list[AgingSegment]",
) -> list[str]:
    """生成单 period 的账龄列头（纯段名，不加期间后缀）。

    适用于 K1-2/K3-2/G5-2 等只有"当前余额账龄分布"的明细表。
    """
    return [seg.label for seg in segments]


# ─── 从 DB 获取项目有效 segments ─────────────────────────────────────────────


async def get_project_segments_from_wp(
    db: AsyncSession,
    wp_id: str,
    subject: str,
) -> "list[AgingSegment]":
    """通过 wp_id 获取项目的有效账龄段列表。

    1. 从 working_paper 获取 project_id
    2. 调用 AgingConfigService.get_effective_segments
    """
    import sqlalchemy as sa
    from app.services.aging_config_service import (
        AgingPreset,
        DEFAULT_SUBJECT_PRESETS,
        PRESET_SEGMENTS,
        get_effective_segments,
        resolve_segments,
    )

    result = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"),
        {"wp_id": wp_id},
    )
    project_id = result.scalar_one_or_none()
    if not project_id:
        # 找不到底稿时返回 subject 默认预设的 segments
        default_preset = DEFAULT_SUBJECT_PRESETS.get(subject, AgingPreset.FIVE_YEAR)
        return resolve_segments(default_preset, None)

    return await get_effective_segments(UUID(str(project_id)), subject, db)


# ─── 段 key 列表 (用于 export_row 时取值) ────────────────────────────────────


def get_segment_keys(segments: "list[AgingSegment]") -> list[str]:
    """提取段 key 列表，用于从行数据的 agingPrior/agingCurrent/agingAudited 中取值。"""
    return [seg.key for seg in segments]


# ═══════════════════════════════════════════════════════════════════════════════
# 动态列计划引擎（headers + export + import label 匹配）
#
# 供 D2/D3/F1/K1/K3/G5 明细表导入导出复用。核心思想：用一份"列计划"(column plan)
# 同时驱动 ①导出列头 ②导出取值 ③导入按列头匹配。账龄列由当前项目 segments 动态生成，
# 存储读写走 nested keyed 结构 (agingPrior/agingCurrent/agingAudited[seg_key])。
#
# Requirements: 8.1 (动态列头) / 8.2 8.3 8.4 (label 匹配 + unmatched warning)
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re

# 列计划条目：
#   ("F", header, key, kind)          固定列，kind ∈ {"num","str","bool"}
#   ("A", header, period, seg_key)    账龄列，取值 row[period][seg_key]
FixedCol = tuple  # ("F", str, str, str)
AgingCol = tuple  # ("A", str, str, str)

# 账龄期间在 row 上的 nested 字段名
PERIOD_PRIOR = "agingPrior"
PERIOD_CURRENT = "agingCurrent"
PERIOD_AUDITED = "agingAudited"

# 账龄列头识别正则（用于 unmatched warning 检测）：形如 "1年以内(期初)" / "期初审定账龄(1-2年)" / "3年以上"
_AGING_SUFFIX_RE = _re.compile(r".*[（(](?:期初|期末|期末未审|期末审定|审定)[)）]\s*$")
_AGING_PREFIX_RE = _re.compile(r"^(?:期初审定账龄|审定账龄|期初账龄|期末账龄)[（(].*[)）]\s*$")
_YEAR_LABEL_RE = _re.compile(r"^\s*\d+\s*年")  # "1年以内" / "5年以上" 等纯段名


def _to_float(val: object) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _to_str(val: object) -> str:
    return "" if val is None else str(val).strip()


def _to_bool_cn(val: object) -> bool:
    s = _to_str(val).lower()
    return s in ("是", "yes", "true", "1", "y")


def build_aging_cols(
    segments: "list[AgingSegment]",
    period: str,
    header_fn,
) -> list:
    """为单个 period 构建账龄列计划片段。

    header_fn(seg) -> str 决定列头文本（支持 suffix / prefix_paren 等风格）。
    """
    return [("A", header_fn(seg), period, seg.key) for seg in segments]


def plan_headers(plan: list) -> list[str]:
    """从列计划提取列头列表。"""
    return [entry[1] for entry in plan]


def plan_export_row(row: dict, plan: list) -> list:
    """按列计划从 row 提取一行导出值（账龄读 nested keyed）。"""
    out: list = []
    for entry in plan:
        if entry[0] == "F":
            _, _header, key, kind = entry
            val = row.get(key)
            if kind == "bool":
                out.append("是" if val else "")
            elif kind == "num":
                out.append(_to_float(val) if val not in (None, "") else "")
            else:
                out.append("" if val is None else val)
        else:  # aging
            _, _header, period, seg_key = entry
            aging_obj = row.get(period) or {}
            out.append(_to_float(aging_obj.get(seg_key)) if isinstance(aging_obj, dict) else 0.0)
    return out


def _looks_like_aging(header: str) -> bool:
    """判断某列头是否"看起来像账龄列"（用于 unmatched warning 检测）。"""
    h = (header or "").strip()
    if not h:
        return False
    return bool(
        _AGING_SUFFIX_RE.match(h)
        or _AGING_PREFIX_RE.match(h)
        or _YEAR_LABEL_RE.match(h)
    )


def plan_parse_row(
    values: tuple,
    actual_headers: list[str],
    plan: list,
    *,
    extra: dict | None = None,
) -> tuple[dict, list[str]]:
    """按列计划解析一行导入数据（账龄按列头精确匹配 → nested keyed）。

    返回 (row_dict, unmatched_aging_headers)。
    - 固定列：按列头在 actual_headers 中的位置取值。
    - 账龄列：在 actual_headers 中查找该列头；命中则写入 row[period][seg_key]，
      缺失则该段初始化为 0（满足配置变更后旧模板缺列的情况）。
    - unmatched：actual_headers 中"看起来像账龄"但不属于当前列计划的列 → 报 warning 并跳过。

    Requirements: 8.2 (label 匹配) / 8.3 (unmatched warning+skip) / 8.4 (旧模板按 label 映射)
    """
    vals = list(values) + [None] * max(0, len(actual_headers) - len(values))

    def _col(header: str) -> object:
        try:
            idx = actual_headers.index(header)
        except ValueError:
            return None
        return vals[idx] if idx < len(vals) else None

    row: dict = {}
    if extra:
        row.update(extra)

    expected_headers: set[str] = set()
    # 初始化 nested 账龄容器
    for entry in plan:
        if entry[0] == "A":
            _, header, period, seg_key = entry
            expected_headers.add(header)
            row.setdefault(period, {})
            row[period][seg_key] = _to_float(_col(header))
        else:
            _, header, key, kind = entry
            expected_headers.add(header)
            raw = _col(header)
            if kind == "num":
                row[key] = _to_float(raw)
            elif kind == "bool":
                row[key] = _to_bool_cn(raw)
            else:
                row[key] = _to_str(raw)

    # unmatched 账龄列检测
    unmatched = [
        h for h in actual_headers
        if h and h not in expected_headers and _looks_like_aging(h)
    ]
    return row, unmatched


# ─── header_fn 工厂（不同风格） ──────────────────────────────────────────────

def suffix_header_fn(suffix: str):
    """列头 = {label}{suffix}，如 '1年以内(期初)'。"""
    return lambda seg: f"{seg.label}{suffix}"


def prefix_paren_header_fn(prefix: str):
    """列头 = {prefix}({label})，如 '期初审定账龄(1年以内)'。"""
    return lambda seg: f"{prefix}({seg.label})"


def plain_label_header_fn():
    """列头 = {label}（单 period 纯段名，如 K1-2/K3-2/G5-2）。"""
    return lambda seg: seg.label
