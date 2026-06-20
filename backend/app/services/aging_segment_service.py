"""账龄段枚举配置服务（AgingSegmentService）

管理坏账准备明细表的账龄段字典配置：
- 预设方案（三年段/五年段）与自定义段列表
- 保存配置时同步 CREDIT_RISK_AGING 父行下的子行

铁律：
- service 只 flush 不 commit（由 router 统一 commit）
- upsert 使用原生 SQL ON CONFLICT 保证原子性

Requirements: 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod


# ─── 枚举 & Pydantic 模型 ────────────────────────────────────────────────────


class AgingPreset(str, Enum):
    """账龄段预设方案"""

    THREE_YEAR = "THREE_YEAR"   # 1年以内/1-2年/2-3年/3年以上
    FIVE_YEAR = "FIVE_YEAR"    # 1年以内/1-2年/2-3年/3-4年/4-5年/5年以上
    CUSTOM = "CUSTOM"          # 自定义


class AgingSegmentConfig(BaseModel):
    """账龄段配置（API 请求/响应模型）"""

    preset: AgingPreset
    segments: list[str]  # 有序段名列表


# ─── AgingSegmentService ─────────────────────────────────────────────────────


class AgingSegmentService:
    """账龄段枚举配置服务"""

    PRESETS: dict[AgingPreset, list[str]] = {
        AgingPreset.THREE_YEAR: ["1年以内", "1-2年", "2-3年", "3年以上"],
        AgingPreset.FIVE_YEAR: ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"],
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 段名校验 ────────────────────────────────────────────────────────────

    @staticmethod
    def validate_segments(segments: list[str]) -> list[str]:
        """校验段名列表，返回错误列表（空列表表示校验通过）。

        校验规则：
        - 段名不可为空字符串
        - 段名不可重复
        """
        errors: list[str] = []

        for i, seg in enumerate(segments):
            if not seg or not seg.strip():
                errors.append(f"EMPTY_SEGMENT_NAME:segments[{i}]")

        # 检查重复（忽略空名，空名已单独报错）
        seen: set[str] = set()
        for i, seg in enumerate(segments):
            stripped = seg.strip()
            if stripped and stripped in seen:
                errors.append(f"DUPLICATE_SEGMENT_NAME:segments[{i}]:{stripped}")
            seen.add(stripped)

        return errors

    # ─── get_config ──────────────────────────────────────────────────────────

    async def get_config(self, wp_index_id: uuid.UUID) -> AgingSegmentConfig | None:
        """获取当前底稿的账龄段配置（不存在返回 None）"""
        result = await self.db.execute(
            text(
                "SELECT preset, segments FROM aging_segments WHERE wp_index_id = :wp_id"
            ),
            {"wp_id": wp_index_id},
        )
        row = result.first()
        if row is None:
            return None
        return AgingSegmentConfig(preset=AgingPreset(row[0]), segments=row[1])

    # ─── save_config ─────────────────────────────────────────────────────────

    async def save_config(
        self, wp_index_id: uuid.UUID, config: AgingSegmentConfig
    ) -> None:
        """保存账龄段配置 + 同步 CREDIT_RISK_AGING 子行。

        步骤：
        1. upsert aging_segments 表
        2. 找到/创建 CREDIT_RISK_AGING 父行
        3. 删除旧子行，按 segments 列表依次创建新子行
        """
        # 1. Upsert aging_segments
        await self.db.execute(
            text("""
                INSERT INTO aging_segments (id, wp_index_id, preset, segments, created_at, updated_at)
                VALUES (gen_random_uuid(), :wp_id, :preset, :segments::jsonb, now(), now())
                ON CONFLICT (wp_index_id) DO UPDATE SET
                    preset = EXCLUDED.preset,
                    segments = EXCLUDED.segments,
                    updated_at = now()
            """),
            {
                "wp_id": wp_index_id,
                "preset": config.preset.value,
                "segments": _json_dumps(config.segments),
            },
        )
        await self.db.flush()

        # 2. 找到/创建 CREDIT_RISK_AGING 父行
        parent = await self._find_or_create_aging_parent(wp_index_id)

        # 3. 删除旧子行
        await self.db.execute(
            delete(BadDebtDetailRow).where(
                BadDebtDetailRow.parent_row_id == parent.id
            )
        )
        await self.db.flush()

        # 4. 按 segments 列表依次创建新子行
        for idx, seg_name in enumerate(config.segments):
            child = BadDebtDetailRow(
                id=uuid.uuid4(),
                wp_index_id=wp_index_id,
                parent_row_id=parent.id,
                provision_method=None,
                sort_order=(idx + 1) * 10,
                row_label=seg_name,
                version=1,
            )
            self.db.add(child)

        await self.db.flush()

    # ─── check_has_amounts ───────────────────────────────────────────────────

    async def check_has_amounts(self, wp_index_id: uuid.UUID) -> bool:
        """检查 CREDIT_RISK_AGING 子行是否有已填金额（用于前端警告）。

        只要任一子行的任一金额列非 NULL，即返回 True。
        """
        # 找到 CREDIT_RISK_AGING 父行
        parent_stmt = select(BadDebtDetailRow.id).where(
            BadDebtDetailRow.wp_index_id == wp_index_id,
            BadDebtDetailRow.parent_row_id.is_(None),
            BadDebtDetailRow.provision_method == ProvisionMethod.CREDIT_RISK_AGING.value,
        )
        parent_result = await self.db.execute(parent_stmt)
        parent_row = parent_result.first()
        if parent_row is None:
            return False

        parent_id = parent_row[0]

        # 检查子行是否有任何非空金额
        result = await self.db.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM bad_debt_detail_rows
                    WHERE parent_row_id = :parent_id
                    AND (
                        amount_b IS NOT NULL OR amount_c IS NOT NULL OR
                        amount_d IS NOT NULL OR amount_e IS NOT NULL OR
                        amount_f IS NOT NULL OR amount_g IS NOT NULL OR
                        amount_h IS NOT NULL OR amount_i IS NOT NULL OR
                        amount_j IS NOT NULL OR amount_k IS NOT NULL OR
                        amount_l IS NOT NULL OR amount_m IS NOT NULL OR
                        amount_n IS NOT NULL
                    )
                )
            """),
            {"parent_id": parent_id},
        )
        return result.scalar() or False

    # ─── 内部辅助 ────────────────────────────────────────────────────────────

    async def _find_or_create_aging_parent(
        self, wp_index_id: uuid.UUID
    ) -> BadDebtDetailRow:
        """找到或创建 CREDIT_RISK_AGING 父行。"""
        from sqlalchemy import func

        stmt = select(BadDebtDetailRow).where(
            BadDebtDetailRow.wp_index_id == wp_index_id,
            BadDebtDetailRow.parent_row_id.is_(None),
            BadDebtDetailRow.provision_method == ProvisionMethod.CREDIT_RISK_AGING.value,
        )
        result = await self.db.execute(stmt)
        parent = result.scalar_one_or_none()

        if parent is not None:
            return parent

        # 创建新父行：sort_order = 现有父行最大值 + 10
        max_stmt = select(func.max(BadDebtDetailRow.sort_order)).where(
            BadDebtDetailRow.wp_index_id == wp_index_id,
            BadDebtDetailRow.parent_row_id.is_(None),
        )
        max_order = (await self.db.execute(max_stmt)).scalar()
        next_order = (max_order or 0) + 10

        from app.models.bad_debt_models import PROVISION_METHOD_LABELS

        parent = BadDebtDetailRow(
            id=uuid.uuid4(),
            wp_index_id=wp_index_id,
            parent_row_id=None,
            provision_method=ProvisionMethod.CREDIT_RISK_AGING.value,
            sort_order=next_order,
            row_label=PROVISION_METHOD_LABELS[ProvisionMethod.CREDIT_RISK_AGING],
            version=1,
        )
        self.db.add(parent)
        await self.db.flush()
        return parent


# ─── 工具函数 ────────────────────────────────────────────────────────────────


def _json_dumps(segments: list[str]) -> str:
    """将段名列表序列化为 JSON 字符串（供 SQL 参数绑定）。"""
    import json
    return json.dumps(segments, ensure_ascii=False)
