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
