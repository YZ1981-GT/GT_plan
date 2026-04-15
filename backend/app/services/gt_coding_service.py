"""致同底稿编码体系服务

功能：
- 加载种子数据（幂等）
- 获取编码体系列表/详情/树形结构
- 获取三测联动关系
- 为项目自动生成底稿索引
- 获取标准底稿模板库目录

Validates: Requirements 7.1-7.6
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gt_coding_models import (
    GTWpCoding,
    GTWpType,
    GT_CODING_SEED_DATA,
    THREE_TEST_LINKAGE,
)
from app.models.workpaper_models import WpIndex, WpStatus

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class GTCodingService:
    """致同底稿编码体系服务"""

    # ------------------------------------------------------------------
    # 种子数据加载（幂等）
    # ------------------------------------------------------------------

    async def load_seed_data(self, db: AsyncSession) -> dict:
        """加载致同底稿编码种子数据（幂等：已存在则跳过）"""
        result = await db.execute(
            sa.select(sa.func.count()).select_from(GTWpCoding).where(
                GTWpCoding.is_deleted == sa.false()
            )
        )
        existing_count = result.scalar() or 0

        if existing_count > 0:
            return {"loaded": 0, "existing": existing_count, "message": "种子数据已存在"}

        loaded = 0
        for item in GT_CODING_SEED_DATA:
            coding = GTWpCoding(
                code_prefix=item["code_prefix"],
                code_range=item["code_range"],
                cycle_name=item["cycle_name"],
                wp_type=item["wp_type"],
                description=item.get("description"),
                parent_cycle=item.get("parent_cycle"),
                sort_order=item.get("sort_order"),
            )
            db.add(coding)
            loaded += 1

        await db.flush()
        return {"loaded": loaded, "existing": 0, "message": f"已加载 {loaded} 条编码数据"}

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def list_codings(
        self,
        db: AsyncSession,
        wp_type: str | None = None,
        code_prefix: str | None = None,
    ) -> list[dict]:
        """获取编码体系列表（支持按类型和前缀筛选）"""
        stmt = (
            sa.select(GTWpCoding)
            .where(GTWpCoding.is_deleted == sa.false(), GTWpCoding.is_active == sa.true())
        )
        if wp_type:
            stmt = stmt.where(GTWpCoding.wp_type == wp_type)
        if code_prefix:
            stmt = stmt.where(GTWpCoding.code_prefix == code_prefix)
        stmt = stmt.order_by(GTWpCoding.sort_order)

        result = await db.execute(stmt)
        return [self._to_dict(c) for c in result.scalars().all()]

    async def get_coding(self, db: AsyncSession, coding_id: UUID) -> dict | None:
        """获取编码详情"""
        result = await db.execute(
            sa.select(GTWpCoding).where(GTWpCoding.id == coding_id)
        )
        coding = result.scalar_one_or_none()
        return self._to_dict(coding) if coding else None

    async def get_tree(self, db: AsyncSession) -> list[dict]:
        """获取编码树形结构（按类型分组）"""
        codings = await self.list_codings(db)

        type_groups: dict[str, list[dict]] = {}
        type_labels = {
            "preliminary": "初步业务活动",
            "risk_assessment": "风险评估与穿行测试",
            "control_test": "控制测试",
            "substantive": "实质性程序",
            "completion": "完成阶段",
            "specific": "特定项目程序",
            "general": "通用底稿",
            "permanent": "永久性档案",
        }

        for c in codings:
            t = c["wp_type"]
            if t not in type_groups:
                type_groups[t] = []
            type_groups[t].append(c)

        tree = []
        for wp_type, label in type_labels.items():
            children = type_groups.get(wp_type, [])
            if children:
                tree.append({
                    "key": wp_type,
                    "label": label,
                    "children": children,
                })
        return tree

    def get_three_test_linkage(self) -> list[dict]:
        """获取三测联动关系"""
        return THREE_TEST_LINKAGE

    # ------------------------------------------------------------------
    # 底稿索引自动生成
    # ------------------------------------------------------------------

    async def generate_project_index(
        self,
        db: AsyncSession,
        project_id: UUID,
        template_set: str = "standard",
    ) -> dict:
        """根据致同编码体系为项目自动生成底稿索引

        Args:
            project_id: 项目ID
            template_set: 模板集名称（standard/simplified/listed/ipo/soe_notes/listed_notes）
        """
        # 检查项目是否已有索引
        existing = await db.execute(
            sa.select(sa.func.count()).select_from(WpIndex).where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == sa.false(),
            )
        )
        existing_count = existing.scalar() or 0
        if existing_count > 0:
            return {
                "generated": 0,
                "existing": existing_count,
                "message": "项目已有底稿索引，跳过生成",
            }

        # 获取所有活跃编码
        codings = await self.list_codings(db)

        generated = 0
        for coding in codings:
            # 根据模板集过滤（简化版跳过部分底稿）
            if template_set == "simplified" and coding["wp_type"] in ("specific", "general"):
                continue

            wp_index = WpIndex(
                project_id=project_id,
                wp_code=coding["code_range"],
                wp_name=coding["cycle_name"],
                audit_cycle=coding["code_prefix"],
                status=WpStatus.not_started,
            )
            db.add(wp_index)
            generated += 1

        await db.flush()
        return {
            "generated": generated,
            "existing": 0,
            "message": f"已生成 {generated} 条底稿索引",
        }

    # ------------------------------------------------------------------
    # 自定义编码体系（Task 9.4）
    # ------------------------------------------------------------------

    async def create_custom_coding(
        self,
        db: AsyncSession,
        code_prefix: str,
        code_range: str,
        cycle_name: str,
        wp_type: str,
        description: str | None = None,
        parent_cycle: str | None = None,
        sort_order: int | None = None,
        project_id: UUID | None = None,
    ) -> dict:
        """创建自定义编码条目

        Args:
            project_id: 如果指定，则为项目级自定义编码；否则为事务所级
        """
        # 检查编码前缀+范围是否已存在
        stmt = sa.select(GTWpCoding).where(
            GTWpCoding.code_prefix == code_prefix,
            GTWpCoding.code_range == code_range,
            GTWpCoding.is_deleted == sa.false(),
        )
        existing = await db.execute(stmt)
        if existing.scalar_one_or_none():
            raise ValueError(f"编码 {code_prefix}/{code_range} 已存在")

        # 验证 wp_type
        valid_types = [e.value for e in GTWpType]
        if wp_type not in valid_types:
            raise ValueError(f"无效的底稿类型: {wp_type}，允许: {valid_types}")

        coding = GTWpCoding(
            code_prefix=code_prefix,
            code_range=code_range,
            cycle_name=cycle_name,
            wp_type=wp_type,
            description=description,
            parent_cycle=parent_cycle,
            sort_order=sort_order or 999,
        )
        db.add(coding)
        await db.flush()
        return self._to_dict(coding)

    async def update_custom_coding(
        self,
        db: AsyncSession,
        coding_id: UUID,
        updates: dict,
    ) -> dict:
        """更新自定义编码条目"""
        result = await db.execute(
            sa.select(GTWpCoding).where(
                GTWpCoding.id == coding_id,
                GTWpCoding.is_deleted == sa.false(),
            )
        )
        coding = result.scalar_one_or_none()
        if not coding:
            raise ValueError("编码不存在")

        allowed_fields = {"code_range", "cycle_name", "description", "parent_cycle", "sort_order", "is_active"}
        for key, val in updates.items():
            if key in allowed_fields and val is not None:
                setattr(coding, key, val)

        await db.flush()
        return self._to_dict(coding)

    async def delete_custom_coding(self, db: AsyncSession, coding_id: UUID) -> dict:
        """软删除自定义编码条目"""
        result = await db.execute(
            sa.select(GTWpCoding).where(
                GTWpCoding.id == coding_id,
                GTWpCoding.is_deleted == sa.false(),
            )
        )
        coding = result.scalar_one_or_none()
        if not coding:
            raise ValueError("编码不存在")

        coding.soft_delete()
        await db.flush()
        return {"id": str(coding_id), "deleted": True}

    async def clone_coding_for_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        source_prefix: str | None = None,
    ) -> dict:
        """克隆标准编码体系到项目级自定义（允许项目独立修改）

        Args:
            project_id: 目标项目ID
            source_prefix: 只克隆指定前缀的编码，None=全部
        """
        stmt = sa.select(GTWpCoding).where(
            GTWpCoding.is_deleted == sa.false(),
            GTWpCoding.is_active == sa.true(),
        )
        if source_prefix:
            stmt = stmt.where(GTWpCoding.code_prefix == source_prefix)

        result = await db.execute(stmt)
        sources = result.scalars().all()

        cloned = 0
        for src in sources:
            clone = GTWpCoding(
                code_prefix=src.code_prefix,
                code_range=f"{src.code_range}@{str(project_id)[:8]}",
                cycle_name=src.cycle_name,
                wp_type=src.wp_type,
                description=f"[项目自定义] {src.description or ''}",
                parent_cycle=src.parent_cycle,
                sort_order=src.sort_order,
            )
            db.add(clone)
            cloned += 1

        await db.flush()
        return {"cloned": cloned, "project_id": str(project_id)}

    # ------------------------------------------------------------------
    # 标准底稿模板库（Task 9.3）
    # ------------------------------------------------------------------

    def get_template_library(self, wp_type: str | None = None, cycle_prefix: str | None = None) -> dict:
        """获取致同标准底稿模板库目录

        Args:
            wp_type: 按底稿类型筛选
            cycle_prefix: 按循环前缀筛选
        """
        lib_path = DATA_DIR / "gt_template_library.json"
        if not lib_path.exists():
            return {"templates": [], "total": 0}
        with open(lib_path, encoding="utf-8-sig") as f:
            data = json.load(f)
        templates = data.get("templates", [])
        if wp_type:
            templates = [t for t in templates if t.get("wp_type") == wp_type]
        if cycle_prefix:
            templates = [t for t in templates if t.get("cycle_prefix") == cycle_prefix]
        return {"templates": templates, "total": len(templates)}

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _to_dict(self, coding: GTWpCoding) -> dict:
        return {
            "id": str(coding.id),
            "code_prefix": coding.code_prefix,
            "code_range": coding.code_range,
            "cycle_name": coding.cycle_name,
            "wp_type": coding.wp_type.value if hasattr(coding.wp_type, "value") else str(coding.wp_type),
            "description": coding.description,
            "parent_cycle": coding.parent_cycle,
            "sort_order": coding.sort_order,
            "is_active": coding.is_active,
        }
