"""底稿 sheet 归类服务

实现 9 类（A~I）→ componentType 白名单映射 + 项目级覆盖合并。
Requirements: 1.2（9 类全覆盖）+ 3.9（决策树禁止 Univer 兜底）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_wp_sheet_override import ProjectWorkpaperSheetOverride
from app.models.workpaper_models import WorkpaperSheetClassification

logger = logging.getLogger(__name__)


# ─── componentType 白名单（design §7.2） ─────────────────────────────────────
VALID_COMPONENT_TYPES: set[str] = {
    "a-program-console",
    "b-index",
    "c-note-table",
    "d-form-table",
    "d-form-paragraph",
    "d-form-qa",
    "d-form-confirmation",
    "d-form-review",
    "e-control-test",
    "h-static-doc",
    "univer",
    "skip",
}

# ─── 9 类 class_code 前缀 → componentType 映射 ──────────────────────────────
# D 类需要 sub-routing（基于 class_code 子类型）
_CLASS_TO_COMPONENT: dict[str, str] = {
    "A-": "a-program-console",
    "B-": "b-index",
    "C-": "c-note-table",
    "E-": "e-control-test",
    "F-": "univer",
    "G-": "univer",
    "H-": "h-static-doc",
    "I-": "skip",
}

# D 类子路由映射（基于 class_code 具体值）
_D_SUB_ROUTING: dict[str, str] = {
    "D-函证": "d-form-confirmation",
    "D-盘点": "d-form-confirmation",
    "D-访谈": "d-form-confirmation",
    "D-询证": "d-form-confirmation",
    "D-政策检查": "d-form-paragraph",
    "D-业务模式": "d-form-qa",
    "D-复核记录": "d-form-review",
    "D-复核": "d-form-review",
}

# D 类默认 componentType（表格型检查表）
_D_DEFAULT = "d-form-table"


@dataclass
class ClassificationResult:
    """归类结果"""

    wp_code: str
    sheet_name: str
    class_code: str | None
    class_: str | None
    scope: str
    is_real_workpaper: bool
    delegated_module: str | None
    render_schema_path: str | None
    template_version_id: UUID | None
    # 项目级覆盖来源标记
    has_override: bool = False


class WpClassificationService:
    """底稿 sheet 归类服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_classification(
        self,
        wp_code: str,
        project_id: UUID,
        template_version_id: UUID | None = None,
    ) -> list[ClassificationResult]:
        """获取底稿所有 sheet 的归类信息（含项目级覆盖合并）

        流程：
        1. 查 workpaper_sheet_classification 获取模板级归类
        2. 查 project_workpaper_sheet_override 获取项目级覆盖
        3. 合并：override 字段优先覆盖 base classification
        """
        # ─── Step 1: 查模板级归类 ────────────────────────────────────────
        base_query = sa.select(WorkpaperSheetClassification).where(
            WorkpaperSheetClassification.wp_code == wp_code,
        )
        if template_version_id is not None:
            base_query = base_query.where(
                WorkpaperSheetClassification.template_version_id == template_version_id
            )

        base_rows = (await self.db.execute(base_query)).scalars().all()

        if not base_rows:
            raise ClassificationNotFoundError(
                f"No classification found for wp_code='{wp_code}' "
                f"(template_version_id={template_version_id}). "
                "Every sheet must have a classification — Univer fallback is prohibited."
            )

        # ─── Step 2: 查项目级覆盖 ────────────────────────────────────────
        override_query = sa.select(ProjectWorkpaperSheetOverride).where(
            ProjectWorkpaperSheetOverride.project_id == project_id,
            ProjectWorkpaperSheetOverride.wp_code == wp_code,
        )
        override_rows = (await self.db.execute(override_query)).scalars().all()

        # 按 sheet_name 索引覆盖记录
        overrides_by_sheet: dict[str, ProjectWorkpaperSheetOverride] = {
            o.sheet_name: o for o in override_rows
        }

        # ─── Step 3: 合并 ────────────────────────────────────────────────
        results: list[ClassificationResult] = []
        for base in base_rows:
            override = overrides_by_sheet.get(base.sheet_name)
            has_override = override is not None

            # 覆盖字段：class_override 覆盖 class_code/class_
            effective_class_code = base.class_code
            effective_class = base.class_
            effective_scope = base.scope

            if override:
                if override.class_override:
                    effective_class_code = override.class_override
                    effective_class = override.class_override
                if override.scope_override:
                    effective_scope = override.scope_override

            results.append(
                ClassificationResult(
                    wp_code=base.wp_code,
                    sheet_name=base.sheet_name,
                    class_code=effective_class_code,
                    class_=effective_class,
                    scope=effective_scope,
                    is_real_workpaper=base.is_real_workpaper,
                    delegated_module=base.delegated_module,
                    render_schema_path=base.render_schema_path,
                    template_version_id=base.template_version_id,
                    has_override=has_override,
                )
            )

        return results

    async def get_sheet_classification(
        self,
        wp_code: str,
        sheet_name: str,
        project_id: UUID,
        template_version_id: UUID | None = None,
    ) -> ClassificationResult:
        """获取单个 sheet 的归类信息（含项目级覆盖合并）"""
        # 查模板级归类
        base_query = sa.select(WorkpaperSheetClassification).where(
            WorkpaperSheetClassification.wp_code == wp_code,
            WorkpaperSheetClassification.sheet_name == sheet_name,
        )
        if template_version_id is not None:
            base_query = base_query.where(
                WorkpaperSheetClassification.template_version_id == template_version_id
            )

        base = (await self.db.execute(base_query)).scalars().first()

        if not base:
            raise ClassificationNotFoundError(
                f"No classification found for wp_code='{wp_code}', "
                f"sheet_name='{sheet_name}'. "
                "Every sheet must have a classification — Univer fallback is prohibited."
            )

        # 查项目级覆盖
        override_query = sa.select(ProjectWorkpaperSheetOverride).where(
            ProjectWorkpaperSheetOverride.project_id == project_id,
            ProjectWorkpaperSheetOverride.wp_code == wp_code,
            ProjectWorkpaperSheetOverride.sheet_name == sheet_name,
        )
        override = (await self.db.execute(override_query)).scalars().first()

        has_override = override is not None
        effective_class_code = base.class_code
        effective_class = base.class_
        effective_scope = base.scope

        if override:
            if override.class_override:
                effective_class_code = override.class_override
                effective_class = override.class_override
            if override.scope_override:
                effective_scope = override.scope_override

        return ClassificationResult(
            wp_code=base.wp_code,
            sheet_name=base.sheet_name,
            class_code=effective_class_code,
            class_=effective_class,
            scope=effective_scope,
            is_real_workpaper=base.is_real_workpaper,
            delegated_module=base.delegated_module,
            render_schema_path=base.render_schema_path,
            template_version_id=base.template_version_id,
            has_override=has_override,
        )


def derive_component_type(classification: ClassificationResult) -> str:
    """将归类结果映射到 componentType 白名单值

    映射规则（design §7.2 + task 1.6）：
    - A- (程序表) → 'a-program-console'
    - B- (底稿目录) → 'b-index'
    - C- (附注披露) → 'c-note-table'
    - D- (检查表) → 需 sub-routing:
        - D-函证/D-盘点/D-访谈/D-询证 → 'd-form-confirmation'
        - D-政策检查 → 'd-form-paragraph'
        - D-业务模式 → 'd-form-qa'
        - D-复核记录/D-复核 → 'd-form-review'
        - 其他 D- → 'd-form-table' (默认)
    - E- (控制测试) → 'e-control-test'
    - F- (数据表) → 'univer'
    - G- (测算表) → 'univer'
    - H- (辅助说明) → 'h-static-doc'
    - I- (占位) → 'skip'

    CRITICAL: 禁止 Univer 兜底！无归类时抛异常而非返回 'univer'。
    """
    class_code = classification.class_code

    if not class_code:
        raise ClassificationNotFoundError(
            f"Sheet '{classification.sheet_name}' (wp_code='{classification.wp_code}') "
            "has no class_code. Cannot derive componentType — "
            "Univer fallback is prohibited (Requirement 3.9)."
        )

    # 检查 D 类 sub-routing（精确匹配优先）
    if class_code.startswith("D-"):
        component_type = _D_SUB_ROUTING.get(class_code, _D_DEFAULT)
        return component_type

    # 其他类按前缀匹配
    for prefix, component_type in _CLASS_TO_COMPONENT.items():
        if class_code.startswith(prefix):
            return component_type

    # 无法匹配 → 抛异常（禁止 Univer 兜底）
    raise ClassificationNotFoundError(
        f"Unknown class_code='{class_code}' for sheet '{classification.sheet_name}' "
        f"(wp_code='{classification.wp_code}'). "
        "Cannot derive componentType — Univer fallback is prohibited (Requirement 3.9). "
        "Please add classification rule for this sheet."
    )


class ClassificationNotFoundError(Exception):
    """归类未找到异常

    当 sheet 没有归类记录或 class_code 无法映射到 componentType 时抛出。
    前端应显示 'pending' 错误状态，禁止降级到 Univer。
    """

    pass
