"""项目级账龄配置服务（AgingConfigService）

管理 D2/D3/F1/K1/K3/G5 往来款明细表的账龄段配置：
- 三种预设方案：THREE_YEAR (4段) / FIVE_YEAR (6段) / CUSTOM (2-10段)
- 项目级存储于 wizard_state.aging_config
- 科目级 subject_overrides 覆盖
- 段配置校验（段数/非空label/唯一label）

铁律：
- service 只 flush 不 commit（由 router 统一 commit）
- 纯逻辑方法（validate/resolve）无需 db 依赖

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.5, 10.1
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project


# ─── 枚举 & Pydantic 模型 ────────────────────────────────────────────────────


class AgingPreset(str, Enum):
    """账龄段预设方案"""

    THREE_YEAR = "THREE_YEAR"   # 4段: 1年以内/1-2年/2-3年/3年以上
    FIVE_YEAR = "FIVE_YEAR"    # 6段: 1年以内/1-2年/2-3年/3-4年/4-5年/5年以上
    CUSTOM = "CUSTOM"          # 自定义 2-10 段


class AgingSegment(BaseModel):
    """单个账龄段定义"""

    key: str            # 唯一标识 (e.g. "within1", "y1to2", "seg_custom_1")
    label: str          # 显示名 (e.g. "1年以内", "1-2年")
    dayFrom: int        # 起始天数 (含)
    dayTo: int | None   # 结束天数 (含), None=无上限


class AgingConfigPayload(BaseModel):
    """账龄配置写入请求体"""

    preset: AgingPreset
    custom_segments: list[AgingSegment] | None = None  # 仅 CUSTOM 时必填
    subject_overrides: dict[str, AgingPreset] | None = None  # e.g. {"D3": "THREE_YEAR"}


class AgingConfigResponse(BaseModel):
    """账龄配置响应体"""

    preset: AgingPreset
    effective_segments: list[AgingSegment]  # 最终生效的段列表
    subject_overrides: dict[str, AgingPreset]


# ─── 预定义常量 ──────────────────────────────────────────────────────────────


PRESET_SEGMENTS: dict[AgingPreset, list[AgingSegment]] = {
    AgingPreset.THREE_YEAR: [
        AgingSegment(key="within1", label="1年以内", dayFrom=0, dayTo=365),
        AgingSegment(key="y1to2", label="1-2年", dayFrom=366, dayTo=730),
        AgingSegment(key="y2to3", label="2-3年", dayFrom=731, dayTo=1095),
        AgingSegment(key="over3", label="3年以上", dayFrom=1096, dayTo=None),
    ],
    AgingPreset.FIVE_YEAR: [
        AgingSegment(key="within1", label="1年以内", dayFrom=0, dayTo=365),
        AgingSegment(key="y1to2", label="1-2年", dayFrom=366, dayTo=730),
        AgingSegment(key="y2to3", label="2-3年", dayFrom=731, dayTo=1095),
        AgingSegment(key="y3to4", label="3-4年", dayFrom=1096, dayTo=1460),
        AgingSegment(key="y4to5", label="4-5年", dayFrom=1461, dayTo=1825),
        AgingSegment(key="over5", label="5年以上", dayFrom=1826, dayTo=None),
    ],
}

# 科目默认预设映射：D2/K1/K3/G5→FIVE_YEAR, D3/F1/G2→THREE_YEAR
DEFAULT_SUBJECT_PRESETS: dict[str, AgingPreset] = {
    "D2": AgingPreset.FIVE_YEAR,
    "K1": AgingPreset.FIVE_YEAR,
    "K3": AgingPreset.FIVE_YEAR,
    "G5": AgingPreset.FIVE_YEAR,
    "D3": AgingPreset.THREE_YEAR,
    "F1": AgingPreset.THREE_YEAR,
    "G2": AgingPreset.THREE_YEAR,
}


# ─── 纯逻辑方法 ──────────────────────────────────────────────────────────────


def resolve_segments(
    preset: AgingPreset,
    custom_segments: list[AgingSegment] | None = None,
) -> list[AgingSegment]:
    """根据 preset 解析最终生效的段列表。

    - THREE_YEAR/FIVE_YEAR: 返回对应的预定义段列表
    - CUSTOM: 返回 custom_segments（调用方需确保非空）
    """
    if preset == AgingPreset.CUSTOM:
        return custom_segments if custom_segments else []
    return PRESET_SEGMENTS[preset]


def validate_config(payload: AgingConfigPayload) -> list[str]:
    """校验账龄配置，返回错误列表（空列表表示校验通过）。

    校验规则：
    - CUSTOM 预设时，segments 数量必须在 2-10 之间
    - 所有 segment label 不可为空或纯空白
    - 所有 segment label 不可重复
    """
    errors: list[str] = []

    # 解析生效的 segments
    segments = resolve_segments(payload.preset, payload.custom_segments)

    # CUSTOM 预设段数校验
    if payload.preset == AgingPreset.CUSTOM:
        count = len(segments)
        if count < 2 or count > 10:
            errors.append(
                f"INVALID_SEGMENT_COUNT:自定义账龄段数量必须在2-10之间,当前{count}段"
            )

    # 非空 label 校验
    for i, seg in enumerate(segments):
        if not seg.label or not seg.label.strip():
            errors.append(
                f"EMPTY_SEGMENT_LABEL:账龄段名称不能为空:segments[{i}]"
            )

    # 唯一 label 校验
    seen: set[str] = set()
    for i, seg in enumerate(segments):
        stripped = seg.label.strip() if seg.label else ""
        if stripped and stripped in seen:
            errors.append(
                f"DUPLICATE_SEGMENT_LABEL:账龄段名称重复:{stripped}"
            )
        if stripped:
            seen.add(stripped)

    # subject_overrides 不允许 CUSTOM（无法携带独立 custom_segments）
    if payload.subject_overrides:
        for subject, override in payload.subject_overrides.items():
            if override == AgingPreset.CUSTOM:
                errors.append(
                    f"INVALID_SUBJECT_OVERRIDE:{subject}科目覆盖不支持CUSTOM，请使用全局CUSTOM或THREE_YEAR/FIVE_YEAR"
                )

    return errors


# ─── 持久化方法（async，需 db session） ────────────────────────────────────────


async def _get_project_or_404(db: AsyncSession, project_id: UUID) -> Project:
    """获取项目，不存在则抛 404。"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def get_config(project_id: UUID, db: AsyncSession) -> AgingConfigResponse:
    """读取项目级账龄配置。

    - 若 wizard_state.aging_config 存在，解析并返回
    - 若无配置，返回默认值 (FIVE_YEAR preset, 无 subject_overrides)

    Requirements: 1.2, 1.3, 2.5, 10.1
    """
    project = await _get_project_or_404(db, project_id)

    ws = project.wizard_state or {}
    aging_cfg = ws.get("aging_config")

    if aging_cfg is None:
        # 无配置时返回默认: FIVE_YEAR preset
        preset = AgingPreset.FIVE_YEAR
        return AgingConfigResponse(
            preset=preset,
            effective_segments=resolve_segments(preset, None),
            subject_overrides={},
        )

    # 解析已存储的配置
    preset = AgingPreset(aging_cfg.get("preset", "FIVE_YEAR"))
    custom_segments: list[AgingSegment] | None = None
    if aging_cfg.get("custom_segments"):
        custom_segments = [
            AgingSegment(**seg) for seg in aging_cfg["custom_segments"]
        ]
    subject_overrides: dict[str, AgingPreset] = {}
    if aging_cfg.get("subject_overrides"):
        subject_overrides = {
            k: AgingPreset(v)
            for k, v in aging_cfg["subject_overrides"].items()
        }

    effective = resolve_segments(preset, custom_segments)

    return AgingConfigResponse(
        preset=preset,
        effective_segments=effective,
        subject_overrides=subject_overrides,
    )


async def save_config(
    project_id: UUID,
    payload: AgingConfigPayload,
    db: AsyncSession,
) -> AgingConfigResponse:
    """保存项目级账龄配置到 wizard_state.aging_config。

    铁律：只 flush 不 commit（由 router 统一 commit）。

    Requirements: 1.3
    """
    project = await _get_project_or_404(db, project_id)

    # 构建存储结构
    aging_data: dict = {
        "preset": payload.preset.value,
        "custom_segments": (
            [seg.model_dump() for seg in payload.custom_segments]
            if payload.custom_segments
            else None
        ),
        "subject_overrides": (
            {k: v.value for k, v in payload.subject_overrides.items()}
            if payload.subject_overrides
            else {}
        ),
    }

    # 写入 wizard_state (合并，不覆盖其他字段)
    ws = dict(project.wizard_state) if project.wizard_state else {}
    ws["aging_config"] = aging_data
    project.wizard_state = ws

    await db.flush()

    # 返回响应
    effective = resolve_segments(payload.preset, payload.custom_segments)
    subject_overrides = (
        {k: v for k, v in payload.subject_overrides.items()}
        if payload.subject_overrides
        else {}
    )

    return AgingConfigResponse(
        preset=payload.preset,
        effective_segments=effective,
        subject_overrides=subject_overrides,
    )


async def get_effective_segments(
    project_id: UUID,
    subject: str,
    db: AsyncSession,
) -> list[AgingSegment]:
    """获取特定科目的有效账龄段列表。

    解析逻辑：
    1. 读取项目 aging_config
    2. 如果 subject_overrides 中有该 subject 的覆盖预设，使用覆盖预设
    3. 否则使用全局 preset
    4. 如果项目无配置，基于 subject 推断默认 preset

    Requirements: 1.2, 2.5, 10.1
    """
    project = await _get_project_or_404(db, project_id)

    ws = project.wizard_state or {}
    aging_cfg = ws.get("aging_config")

    if aging_cfg is None:
        # 无配置时基于 subject 推断默认 preset
        default_preset = DEFAULT_SUBJECT_PRESETS.get(
            subject, AgingPreset.FIVE_YEAR
        )
        return resolve_segments(default_preset, None)

    # 解析全局配置
    global_preset = AgingPreset(aging_cfg.get("preset", "FIVE_YEAR"))
    custom_segments: list[AgingSegment] | None = None
    if aging_cfg.get("custom_segments"):
        custom_segments = [
            AgingSegment(**seg) for seg in aging_cfg["custom_segments"]
        ]

    # 检查 subject_overrides
    overrides = aging_cfg.get("subject_overrides") or {}
    if subject in overrides:
        override_preset = AgingPreset(overrides[subject])
        # subject override 只支持预定义 preset (不支持 CUSTOM 覆盖)
        if override_preset == AgingPreset.CUSTOM:
            # 非法历史配置：回退全局 preset，避免空段
            return resolve_segments(global_preset, custom_segments)
        return resolve_segments(override_preset, None)

    # 使用全局 preset
    return resolve_segments(global_preset, custom_segments)
