"""自定义底稿公式绑定持久化服务（custom-workpaper-formula-binding 组①第三层）。

三层一致第三层：DB 迁移 V052__wp_formula.sql + ORM WpFormula(Mapped[]) + 本 service。

职责：
- save：按 (wp_id, sheet_name, target_cell) 维度 upsert（已存在覆盖更新
  expression/category/description，不存在则新建）。save 前先调用
  ACNR-backed ``validate_refs_via_acnr`` 校验悬空引用（WP 域走 full_resolve，
  非 WP 域走 legacy，resolver 故障 fail-open 回退 legacy），含 ``not_found``
  项则不写库，返回 issues 列表供 router 转 422（Req 6.4 / acnr-consumer-wiring Req 9）。
- list_by_wp：列出某 wp_id 的全部公式。
- delete：按 formula_id 删除单条。

工程铁律（遵循 memory）：
- service 只 ``flush`` 不 ``commit``（跨 service 编排由 router 统一 commit 保原子）。
- 全 async（AsyncSession + select/execute async 风格）。
- ``address_registry`` 为模块级单例，直接 import 使用。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula
from app.services.acnr.formula_validation import validate_refs_via_acnr

logger = logging.getLogger(__name__)

# 三类型公式（formula-management-library Req 14.5 / 5-7）：
#   auto_calc     — 求值并回填目标单元（执行后记 last_computed_at）
#   logic_check   — 产出问题清单，绝不改值
#   reasonability — 产出提醒清单，绝不改值
_VALID_FORMULA_TYPES = ("auto_calc", "logic_check", "reasonability")

# 公式三来源（formula-management-library Req 25）：
#   preset    — 一键预设套用
#   custom    — 用户自定义编辑（默认）
#   reference — 参照另一条已保存公式（复用其 expression，见 reference_resolver）
_VALID_FORMULA_SOURCES = ("preset", "custom", "reference")


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    """将 str / UUID 统一为 UUID（容忍已是 UUID 的入参）。"""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _normalize_refs(refs: list | None) -> list:
    """规范化引用列表（refs 列，Req 11.5：禁裸字符串，用 addr_id / formula_ref）。

    - None → []。
    - 逐项容忍两种形态：dict（``{addr_id | formula_ref, ...}``）直接保留；
      str（``formula_ref`` 文本，如 ``WP('D1','B5')``）包装为
      ``{"formula_ref": <str>}``，避免落库裸字符串失去结构。
    """
    if not refs:
        return []
    normalized: list = []
    for item in refs:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, str) and item.strip():
            normalized.append({"formula_ref": item.strip()})
    return normalized


class WpFormulaService:
    """自定义底稿公式 CRUD（save / list / delete）。"""

    async def save(
        self,
        db: AsyncSession,
        *,
        project_id: uuid.UUID | str,
        wp_id: uuid.UUID | str,
        sheet_name: str,
        target_cell: str,
        expression: str,
        year: int,
        template_type: str = "soe",
        category: str | None = None,
        description: str | None = None,
        created_by: uuid.UUID | str | None = None,
        formula_type: str = "auto_calc",
        refs: list | None = None,
        issue_description: str | None = None,
        hint_text: str | None = None,
        formula_source: str = "custom",
        reference_formula_id: uuid.UUID | str | None = None,
    ) -> tuple[WpFormula | None, list[dict]]:
        """保存（upsert）一条底稿公式（formula-management-library 三类型契约）。

        以 (wp_id, sheet_name, target_cell) 为唯一维度：已存在则覆盖更新
        expression/formula_type/refs/category/description/issue_description/
        hint_text，不存在则新建。

        保存前调用 ACNR-backed ``validate_refs_via_acnr``（封装 full_resolve）
        校验 expression 中引用的地址是否有效；若含悬空引用（``not_found``，
        found=false），**不写库**，返回 ``(None, issues)`` 供 router 转 422
        （Req 9.5 / 14.4）。校验通过返回 ``(WpFormula, [])``。

        三类型（Req 14.5）：``formula_type ∈ {auto_calc, logic_check,
        reasonability}``，非法类型直接返回 ``(None, issues)``。仅 ``auto_calc``
        执行后回填目标单元（由 router 求值写回）并记 ``last_computed_at``；
        ``logic_check`` / ``reasonability`` **绝不改值**、不记 last_computed_at。

        只 flush 不 commit（router 统一 commit）。

        Args:
            db: AsyncSession。
            project_id: 所属项目 id。
            wp_id: 所属底稿 working_paper.id。
            sheet_name: sheet 名称。
            target_cell: 写入目标单元格（如 B5）。
            expression: 公式表达式。
            year: 校验悬空引用所需年度（传给 validate_formula_refs）。
            template_type: 模板类型，默认 'soe'（传给 validate_formula_refs）。
            category: 公式分类（可选，兼容旧字段）。
            description: 描述（可选）。
            created_by: 创建人 user id（可选，仅新建时写入）。
            formula_type: 公式类型 auto_calc / logic_check / reasonability。
            refs: 规范化引用列表（addr_id / formula_ref dict 或 formula_ref str）。
            issue_description: logic_check 不通过时的问题描述（可选）。
            hint_text: reasonability 触发时的提示文案（可选）。

        Returns:
            (WpFormula, []) 保存成功；(None, issues) 含悬空引用或非法类型未写库。
        """
        project_uuid = _as_uuid(project_id)
        wp_uuid = _as_uuid(wp_id)
        created_by_uuid = _as_uuid(created_by) if created_by is not None else None

        # ── 三类型校验（Req 14.5）：非法类型拒绝写库，返回 issue 供 router 转 422 ──
        ftype = (formula_type or "auto_calc").strip()
        if ftype not in _VALID_FORMULA_TYPES:
            return None, [
                {
                    "ref": None,
                    "uri": None,
                    "status": "invalid_formula_type",
                    "reason": "invalid_formula_type",
                    "message": (
                        f"不支持的公式类型 '{formula_type}'，"
                        f"须为 {'/'.join(_VALID_FORMULA_TYPES)} 之一"
                    ),
                }
            ]

        normalized_refs = _normalize_refs(refs)

        # ── 来源校验（Req 25.1/25.6）：非法来源拒绝写库 ──
        fsource = (formula_source or "custom").strip()
        if fsource not in _VALID_FORMULA_SOURCES:
            return None, [
                {
                    "ref": None,
                    "uri": None,
                    "status": "invalid_formula_source",
                    "reason": "invalid_formula_source",
                    "message": (
                        f"不支持的公式来源 '{formula_source}'，"
                        f"须为 {'/'.join(_VALID_FORMULA_SOURCES)} 之一"
                    ),
                }
            ]

        reference_uuid = (
            _as_uuid(reference_formula_id)
            if reference_formula_id is not None
            else None
        )

        # ── reference 来源解引用（Req 25.5）：复用被参照源公式 expression 而非重录 ──
        # 悬空（源公式不存在/已删除）→ fail-open 记 issue、不写库（不静默产错值，Req 25.7）。
        if fsource == "reference":
            from app.services.formula_management.reference_resolver import (
                resolve_reference_expression,
            )

            ref_res = await resolve_reference_expression(
                db, reference_formula_id=reference_uuid
            )
            if not ref_res.resolved:
                logger.info(
                    "wp_formula save 拒绝：reference 来源悬空/无效 wp_id=%s cell=%s ref=%s",
                    wp_uuid, target_cell, reference_formula_id,
                )
                return None, [
                    {
                        "ref": str(reference_formula_id)
                        if reference_formula_id is not None
                        else None,
                        "uri": None,
                        "status": "reference_dangling",
                        "reason": "reference_dangling",
                        "message": (
                            ref_res.issue.description
                            if ref_res.issue is not None
                            else "参照来源公式不存在（可能已删除）"
                        ),
                    }
                ]
            # 复用源公式表达式（复用而非重录）。
            expression = ref_res.expression or expression

        # ── 悬空引用校验（Req 9.5 / 14.4 / acnr-consumer-wiring Req 9）：──
        # 经 ACNR full_resolve 统一校验（WP 域走 full_resolve，非 WP 域走 legacy，
        # resolver 故障 fail-open 回退 legacy）；含 not_found 则不写库。
        issues = await validate_refs_via_acnr(
            db, str(project_uuid), year, expression, template_type
        )
        if issues:
            logger.info(
                "wp_formula save 拒绝：公式含悬空引用 wp_id=%s cell=%s issues=%d",
                wp_uuid, target_cell, len(issues),
            )
            return None, issues

        # auto_calc 执行后回填目标单元并记最近计算时间（Req 14.3 / P9）；
        # logic_check / reasonability 不改值、不记 last_computed_at（P5）。
        computed_at = (
            datetime.now(timezone.utc) if ftype == "auto_calc" else None
        )

        # ── upsert：按 (wp_id, sheet_name, target_cell) 维度 ──
        existing = (
            await db.execute(
                sa.select(WpFormula).where(
                    WpFormula.wp_id == wp_uuid,
                    WpFormula.sheet_name == sheet_name,
                    WpFormula.target_cell == target_cell,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.expression = expression
            existing.formula_type = ftype
            existing.refs = normalized_refs
            existing.category = category
            existing.description = description
            existing.issue_description = issue_description
            existing.hint_text = hint_text
            existing.formula_source = fsource
            existing.reference_formula_id = reference_uuid
            existing.last_computed_at = computed_at
            existing.updated_at = datetime.now(timezone.utc)
            await db.flush()
            # 源变更失效传播（Req 25.7）：本公式被更新即为潜在"被参照源变更"，
            # 经 ACNR 失效链使所有引用方标失效并可重算（复用不自建）。
            await self._invalidate_reference_dependents(
                db, source_formula_id=existing.id, project_id=project_uuid
            )
            return existing, []

        formula = WpFormula(
            project_id=project_uuid,
            wp_id=wp_uuid,
            sheet_name=sheet_name,
            target_cell=target_cell,
            expression=expression,
            formula_type=ftype,
            refs=normalized_refs,
            category=category,
            description=description,
            issue_description=issue_description,
            hint_text=hint_text,
            formula_source=fsource,
            reference_formula_id=reference_uuid,
            last_computed_at=computed_at,
            created_by=created_by_uuid,
        )
        db.add(formula)
        await db.flush()
        return formula, []

    async def list_by_wp(
        self, db: AsyncSession, wp_id: uuid.UUID | str
    ) -> list[WpFormula]:
        """列出某底稿的全部公式（按 sheet_name, target_cell 排序）。"""
        wp_uuid = _as_uuid(wp_id)
        result = await db.execute(
            sa.select(WpFormula)
            .where(WpFormula.wp_id == wp_uuid)
            .order_by(WpFormula.sheet_name, WpFormula.target_cell)
        )
        return list(result.scalars().all())

    async def delete(self, db: AsyncSession, formula_id: uuid.UUID | str) -> bool:
        """按 formula_id 删除单条公式。

        只 flush 不 commit（router 统一 commit）。

        Returns:
            True 已删除；False 记录不存在（无操作）。
        """
        formula_uuid = _as_uuid(formula_id)
        obj = (
            await db.execute(
                sa.select(WpFormula).where(WpFormula.id == formula_uuid)
            )
        ).scalar_one_or_none()
        if obj is None:
            return False
        # 源删除失效传播（Req 25.7）：删除被参照源公式前，先经 ACNR 失效链使引用方
        # 标失效——删除后引用方即变悬空，须在执行期 fail-open 记 Issue 不产错值。
        project_uuid = obj.project_id
        await self._invalidate_reference_dependents(
            db, source_formula_id=obj.id, project_id=project_uuid
        )
        await db.delete(obj)
        await db.flush()
        return True

    async def _invalidate_reference_dependents(
        self,
        db: AsyncSession,
        *,
        source_formula_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> int:
        """被参照源公式变更/删除时，经 ACNR 失效链使引用方标失效（Req 25.7）。

        委托 ``reference_resolver.invalidate_reference_dependents``（复用
        ``acnr.events.invalidate`` canonical 失效链，不自建）。失效不阻断主流程。
        """
        try:
            from app.services.formula_management.reference_resolver import (
                invalidate_reference_dependents,
            )

            return await invalidate_reference_dependents(
                db,
                source_formula_id=source_formula_id,
                project_id=project_id,
            )
        except Exception as exc:  # noqa: BLE001 — 失效不阻断保存/删除主流程
            logger.warning(
                "reference 源变更失效传播失败（不阻断）: source=%s project=%s: %s",
                source_formula_id, project_id, exc,
            )
            return 0


# 模块级单例（与 address_registry 等保持一致的使用风格）
wp_formula_service = WpFormulaService()
