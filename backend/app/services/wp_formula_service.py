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

Ownership 守卫（formula-runtime-convergence Req 10）：
- save/list/delete 均须传入 project_id 并校验 wp_id/formula_id 归属。
- 未提供 project_id 拒绝写入与执行操作。
- 跨项目访问返回授权错误，不泄露目标敏感元数据。

生命周期修正（formula-runtime-convergence Req 5 / P5）：
- save 只保存定义并设置 lifecycle_state='saved'，绝不写 last_computed_at。
- 定义更新递增 definition_version（若列可用）。
- 成功执行时间戳留给 runtime coordinator。

工程铁律（遵循 memory）：
- service 只 ``flush`` 不 ``commit``（跨 service 编排由 router 统一 commit 保原子）。
- 全 async（AsyncSession + select/execute async 风格）。
- ``address_registry`` 为模块级单例，直接 import 使用。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula, WorkingPaper
from app.services.acnr.formula_validation import validate_refs_via_acnr

logger = logging.getLogger(__name__)

# 三类型公式（formula-management-library Req 14.5 / 5-7）：
#   auto_calc     — 求值并回填目标单元（执行后由 coordinator 记 last_computed_at）
#   logic_check   — 产出问题清单，绝不改值
#   reasonability — 产出提醒清单，绝不改值
_VALID_FORMULA_TYPES = ("auto_calc", "logic_check", "reasonability")

# 公式三来源（formula-management-library Req 25）：
#   preset    — 一键预设套用
#   custom    — 用户自定义编辑（默认）
#   reference — 参照另一条已保存公式（复用其 expression，见 reference_resolver）
_VALID_FORMULA_SOURCES = ("preset", "custom", "reference")


# ── Ownership error 工厂 ─────────────────────────────────────────────────────

class OwnershipError(Exception):
    """跨项目 ownership 校验失败（Req 10.4：不泄露敏感元数据）。"""

    def __init__(self, message: str = "授权错误：实体不属于请求项目"):
        super().__init__(message)
        self.message = message


def _ownership_issue(reason: str = "ownership_denied") -> list[dict]:
    """生成 ownership 校验失败的 issue（不含目标敏感元数据，Req 10.4）。"""
    return [
        {
            "ref": None,
            "uri": None,
            "status": reason,
            "reason": reason,
            "message": "授权错误：实体不属于请求项目",
        }
    ]


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


def _compute_definition_hash(expression: str, formula_type: str, refs: list) -> str:
    """计算影响执行的定义字段 hash（definition_hash）。

    仅含 expression + formula_type + sorted refs 序列化。
    """
    import json
    payload = json.dumps(
        {"expression": expression, "formula_type": formula_type, "refs": refs},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class WpFormulaService:
    """自定义底稿公式 CRUD（save / list / delete）。

    全部操作校验 project ownership（Req 10.1 / 10.4 / 10.6）。
    """

    # ── Ownership 校验 ────────────────────────────────────────────────────────

    async def _verify_wp_ownership(
        self, db: AsyncSession, wp_id: uuid.UUID, project_id: uuid.UUID
    ) -> bool:
        """校验 wp_id 属于 project_id（Req 10.1）。"""
        result = await db.execute(
            sa.select(WorkingPaper.project_id).where(WorkingPaper.id == wp_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        return row == project_id

    async def _verify_formula_ownership(
        self, db: AsyncSession, formula_id: uuid.UUID, project_id: uuid.UUID
    ) -> bool:
        """校验 formula_id 属于 project_id（Req 10.1）。"""
        result = await db.execute(
            sa.select(WpFormula.project_id).where(WpFormula.id == formula_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        return row == project_id

    # ── Public API ────────────────────────────────────────────────────────────

    async def save(
        self,
        db: AsyncSession,
        *,
        project_id: uuid.UUID | str | None = None,
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
        """保存（upsert）一条底稿公式。

        Lifecycle 修正（Req 5 / P5）：
        - save 只保存定义，绝不写 last_computed_at。
        - 定义更新递增 definition_version / 重算 definition_hash。
        - lifecycle_state 置为 'saved'（若列可用）。

        Ownership 守卫（Req 10）：
        - 必须传入 project_id（Req 10.6：未提供拒绝写入）。
        - 校验 wp_id 属于 project_id（Req 10.1 / 10.4）。

        Returns:
            (WpFormula, []) 保存成功；(None, issues) 校验失败未写库。
        """
        # ── Req 10.6：project_id 必填 ──
        if project_id is None:
            return None, _ownership_issue("project_id_required")

        project_uuid = _as_uuid(project_id)
        wp_uuid = _as_uuid(wp_id)
        created_by_uuid = _as_uuid(created_by) if created_by is not None else None

        # ── Req 10.1 / 10.4：wp 归属校验 ──
        wp_owned = await self._verify_wp_ownership(db, wp_uuid, project_uuid)
        if not wp_owned:
            logger.warning(
                "wp_formula save 拒绝：wp_id=%s 不属于 project=%s",
                wp_uuid, project_uuid,
            )
            return None, _ownership_issue()

        # ── 三类型校验（Req 14.5）：非法类型拒绝写库 ──
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

        # ── reference 来源解引用（Req 25.5）──
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
            # reference 仅存关系（Req 7.1）：不复制 expression 作为权威定义。
            # 运行时递归解析当前源公式（由 coordinator 在执行期解引用）。
            # 这里保留 expression 字段为调用方传入值或 ref_res.expression 做参考，
            # 但 reference_formula_id 才是权威关系。
            expression = ref_res.expression or expression

        # ── 悬空引用校验（Req 9.5 / 14.4 / acnr-consumer-wiring Req 9）──
        issues = await validate_refs_via_acnr(
            db, str(project_uuid), year, expression, template_type
        )
        if issues:
            logger.info(
                "wp_formula save 拒绝：公式含悬空引用 wp_id=%s cell=%s issues=%d",
                wp_uuid, target_cell, len(issues),
            )
            return None, issues

        # ── 计算 definition_hash ──
        def_hash = _compute_definition_hash(expression, ftype, normalized_refs)

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
            # ── Req 10.1：二次校验 existing formula 归属 ──
            if existing.project_id != project_uuid:
                return None, _ownership_issue()

            existing.expression = expression
            existing.formula_type = ftype
            existing.refs = normalized_refs
            existing.category = category
            existing.description = description
            existing.issue_description = issue_description
            existing.hint_text = hint_text
            existing.formula_source = fsource
            existing.reference_formula_id = reference_uuid
            # ── P5：save 绝不写 last_computed_at ──
            # existing.last_computed_at 保持原值不动
            existing.updated_at = datetime.now(timezone.utc)
            # ── definition_version 递增（若 ORM 列可用）──
            if hasattr(existing, "definition_version") and existing.definition_version is not None:
                existing.definition_version = existing.definition_version + 1
            elif hasattr(existing, "definition_version"):
                existing.definition_version = 1
            # ── definition_hash 更新 ──
            if hasattr(existing, "definition_hash"):
                existing.definition_hash = def_hash
            # ── lifecycle_state 置为 saved（若 ORM 列可用）──
            if hasattr(existing, "lifecycle_state"):
                existing.lifecycle_state = "saved"
            await db.flush()
            # 源变更失效传播（Req 25.7）
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
            # ── P5：save 绝不写 last_computed_at（保持 NULL）──
            last_computed_at=None,
            created_by=created_by_uuid,
        )
        # ── definition_version 初始化（若 ORM 列可用）──
        if hasattr(formula, "definition_version"):
            formula.definition_version = 1
        if hasattr(formula, "definition_hash"):
            formula.definition_hash = def_hash
        if hasattr(formula, "lifecycle_state"):
            formula.lifecycle_state = "saved"
        db.add(formula)
        await db.flush()
        return formula, []

    async def list_by_wp(
        self,
        db: AsyncSession,
        wp_id: uuid.UUID | str,
        *,
        project_id: uuid.UUID | str | None = None,
    ) -> list[WpFormula]:
        """列出某底稿的全部公式（按 sheet_name, target_cell 排序）。

        Ownership 守卫（Req 10.1 / 10.6）：
        - 若提供 project_id，校验 wp_id 归属。
        - 未提供 project_id 则拒绝操作（返回空列表）。
        """
        # ── Req 10.6：project_id 必填 ──
        if project_id is None:
            logger.warning("wp_formula list_by_wp 拒绝：未提供 project_id")
            return []

        project_uuid = _as_uuid(project_id)
        wp_uuid = _as_uuid(wp_id)

        # ── Req 10.1：wp 归属校验 ──
        wp_owned = await self._verify_wp_ownership(db, wp_uuid, project_uuid)
        if not wp_owned:
            logger.warning(
                "wp_formula list_by_wp 拒绝：wp_id=%s 不属于 project=%s",
                wp_uuid, project_uuid,
            )
            return []

        result = await db.execute(
            sa.select(WpFormula)
            .where(WpFormula.wp_id == wp_uuid, WpFormula.project_id == project_uuid)
            .order_by(WpFormula.sheet_name, WpFormula.target_cell)
        )
        return list(result.scalars().all())

    async def delete(
        self,
        db: AsyncSession,
        formula_id: uuid.UUID | str,
        *,
        project_id: uuid.UUID | str | None = None,
    ) -> bool:
        """按 formula_id 删除单条公式。

        Ownership 守卫（Req 10.1 / 10.6）：
        - 必须传入 project_id。
        - 校验 formula_id 属于 project_id。

        Returns:
            True 已删除；False 记录不存在或 ownership 不匹配（无操作）。
        """
        # ── Req 10.6：project_id 必填 ──
        if project_id is None:
            logger.warning("wp_formula delete 拒绝：未提供 project_id")
            return False

        project_uuid = _as_uuid(project_id)
        formula_uuid = _as_uuid(formula_id)

        obj = (
            await db.execute(
                sa.select(WpFormula).where(WpFormula.id == formula_uuid)
            )
        ).scalar_one_or_none()
        if obj is None:
            return False

        # ── Req 10.1 / 10.4：formula 归属校验 ──
        if obj.project_id != project_uuid:
            logger.warning(
                "wp_formula delete 拒绝：formula_id=%s 不属于 project=%s",
                formula_uuid, project_uuid,
            )
            return False

        # 源删除失效传播（Req 25.7）
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
