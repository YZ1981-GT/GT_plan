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
    "custom",
    "audit-sheet",
    "bad-debt-sheet",
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

# F 类子路由映射（精确匹配优先于 _CLASS_TO_COMPONENT["F-"] 前缀 fallback）
# F-审定表 / F-明细表 → audit-sheet（可编辑表格组件，列结构从模板动态解析）；
# 其余 F-（F-分析表/F-汇总表 等）仍 fallback 到 univer
_F_SUB_ROUTING: dict[str, str] = {
    "F-审定表": "audit-sheet",
    "F-明细表": "audit-sheet",
}

# ─── sheet 名级专用路由（优先于 class_code 派生） ────────────────────────────
# 坏账准备明细表（D2-3 等）的 class_code 是共享的 "F-明细表"，无法靠 class_code
# 区分。但坏账准备明细表是两层嵌套结构专用底稿（计提类别父行 → 明细子行 → 合计），
# 必须路由到专用组件 bad-debt-sheet（GtBadDebtSheet）。故按 sheet 名前缀匹配，
# 优先于 class_code 派生。
def _match_sheet_name_override(sheet_name: str | None) -> str | None:
    """按 sheet 名匹配专用 componentType（None 表示无专用路由，走 class_code 派生）。"""
    if not sheet_name:
        return None
    # 坏账准备明细表（各循环的坏账准备嵌套明细表，如 D2-3/D1-4/G2-3 等）
    if sheet_name.startswith("坏账准备明细表"):
        return "bad-debt-sheet"
    return None


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
        2. 若精确 wp_code 无记录，按以下顺序回退：
           a. parent code（strip trailing -N，如 D1-1 → D1）
           b. base code（仅保留首字母+首数字，如 H1-12 → H1）
        3. 查 project_workpaper_sheet_override 获取项目级覆盖
        4. 合并：override 字段优先覆盖 base classification
        """
        # 候选 wp_code 列表（精确 → 父级 → 基础）
        candidates = self._build_wp_code_candidates(wp_code)

        # ─── Step 1: 按候选顺序查模板级归类 ──────────────────────────────
        base_rows = []
        matched_code = None
        for candidate in candidates:
            base_query = sa.select(WorkpaperSheetClassification).where(
                WorkpaperSheetClassification.wp_code == candidate,
            )
            if template_version_id is not None:
                base_query = base_query.where(
                    WorkpaperSheetClassification.template_version_id == template_version_id
                )
            rows = (await self.db.execute(base_query)).scalars().all()
            if rows:
                base_rows = rows
                matched_code = candidate
                if candidate != wp_code:
                    logger.info(
                        "[WP_CLASSIFICATION] wp_code=%s fallback → matched parent=%s",
                        wp_code, candidate,
                    )
                break

        if not base_rows:
            raise ClassificationNotFoundError(
                f"No classification found for wp_code='{wp_code}' "
                f"(template_version_id={template_version_id}). "
                "Every sheet must have a classification — Univer fallback is prohibited. "
                "Run: python backend/scripts/seed_workpaper_sheet_classification.py"
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

    @staticmethod
    def _build_wp_code_candidates(wp_code: str) -> list[str]:
        """构建 wp_code 查询候选列表（精确 → 父级 → 基础）

        示例：
        - "D2-3"   → ["D2-3"]            （精确匹配，模板里就有 D2-3 sheets）
        - "D2"     → ["D2", "D2-1"]      （umbrella code，回退到 D2-1 模板）
        - "D1-1"   → ["D1-1", "D1"]      （回退到 D1 父级）
        - "H1-12"  → ["H1-12", "H1"]     （回退到 H1 父级）
        - "B22A-4" → ["B22A-4", "B22A", "B22"]  （多级回退）
        """
        import re

        candidates = [wp_code]

        # umbrella code（无 dash 的纯字母+数字，如 D2/D4/F2/H1）
        # → 加上 -1 作为 fallback（致同模板里审定表通常是 -1 编号）
        if re.match(r"^[A-Z]\d+$", wp_code):
            candidates.append(f"{wp_code}-1")

        # 逐级 strip trailing "-N"
        cur = wp_code
        while "-" in cur:
            cur = cur.rsplit("-", 1)[0]
            if cur not in candidates:
                candidates.append(cur)

        return candidates

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
    - F- (数据表) → 需 sub-routing:
        - F-审定表 → 'audit-sheet'（可编辑审定表组件）
        - 其他 F- → 'univer' (默认)
    - G- (测算表) → 'univer'
    - H- (辅助说明) → 'h-static-doc'
    - I- (占位) → 'skip'

    sheet 名级专用路由（优先于 class_code 派生）：
    - 坏账准备明细表* → 'bad-debt-sheet'（两层嵌套结构专用组件）

    CRITICAL: 禁止 Univer 兜底！无归类时抛异常而非返回 'univer'。
    """
    class_code = classification.class_code

    if class_code and class_code.upper().startswith("CUSTOM"):
        return "custom"

    # sheet 名级专用路由优先（坏账准备明细表嵌套结构 → bad-debt-sheet）
    sheet_override = _match_sheet_name_override(classification.sheet_name)
    if sheet_override:
        return sheet_override

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

    # 检查 F 类 sub-routing（精确匹配优先于前缀 fallback）
    # F- 是 _CLASS_TO_COMPONENT 的前缀键（→ univer），若直接走下方前缀循环
    # 会把所有 F- 一律映射到 univer，因此必须在前缀匹配前先查 _F_SUB_ROUTING。
    if class_code.startswith("F-"):
        component_type = _F_SUB_ROUTING.get(class_code)
        if component_type:
            return component_type
        # fallback: 其余 F-（F-明细表/F-分析表/F-汇总表 等）仍返回 univer
        return "univer"

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
