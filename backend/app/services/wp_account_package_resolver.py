"""科目工作包多文件聚合解析器

消费已实施的 `account_package_registry.json`（经 AccountPackageRegistryService），
将一个科目（父码，如 D2 应收账款）声明的全部 sheet 聚合为
`list[ClassificationResult]`，供 get_render_config 替换单文件回退的 classifications。

核心规则（spec workpaper-account-multifile-aggregation design §1/§2）：
- sheet_type → class_code → componentType，确保落在 HTML 白名单（杜绝 univer 空白）
- 解析 source_wp_code → 模板文件路径，填充 ClassificationResult.source_files
- GT_Custom / 占位 sheet 跳过
- 科目无注册表条目 → 返回 None（调用方回退原 get_classification，零回归）
- 忽略 registry 的 mapping_status 字段（pending_inventory_reconciliation 不作消费门控）

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1-2.7
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.account_package_registry_service import (
    AccountPackageRegistryService,
)
from app.services.wp_classification_service import ClassificationResult
from app.services.wp_component_type_mapping import class_code_to_component
from app.services.wp_template_finder import find_template_file_any

logger = logging.getLogger(__name__)


# ─── sheet_type → class_code 映射（design §2，已核验全部命中 HTML 白名单） ─────
# 每个 class_code 经 class_code_to_component 返回非 None 且为 HTML 类：
#   A-*      → a-program-console
#   F-审定表 / F-明细表 → audit-sheet（_F_SUB_ROUTING 精确命中，非 univer）
#   D-调整   → d-form-table（D- 默认）
#   C-*      → c-note-table
#   D-政策检查 → d-form-paragraph
# ⚠ 禁止映射到 "F-分析表"/"G-*" 等 fallback 到 univer 的键（会渲染空白）。
_SHEET_TYPE_TO_CLASS: dict[str, str] = {
    "control_panel": "A-实质性程序",  # → a-program-console
    "procedure": "A-检查程序",         # → a-program-console
    "audit_sheet": "F-审定表",         # → audit-sheet
    "detail_table": "F-明细表",        # → audit-sheet
    "analysis": "F-明细表",            # → audit-sheet（非 univer，根治"显示不出来"）
    "adjustment": "D-调整",            # → d-form-table
    "disclosure": "C-附注披露",        # → c-note-table
    "conclusion": "D-政策检查",        # → d-form-paragraph
    "confirmation_summary": "A-实质性程序",  # → a-program-console（函证汇总卡）
    "grid_table": "C-附注披露",        # → c-note-table（只读网格兜底，用于检查表/测算表等无 schema 的表格型 sheet）
}

# HTML 可渲染白名单（排除 univer / skip）——聚合 sheet 的 componentType 必须落在此集合。
HTML_RENDERABLE_COMPONENTS: frozenset[str] = frozenset({
    "a-program-console",
    "b-index",
    "c-note-table",
    "d-form-table",
    "d-form-paragraph",
    "d-form-qa",
    "d-form-confirmation",
    "d-form-review",
    "e-control-test",
    "audit-sheet",
    "bad-debt-sheet",
})


def _is_placeholder_sheet(sheet_name: str | None) -> bool:
    """GT_Custom 等占位 sheet 跳过（需求 1.5）。"""
    if not sheet_name:
        return True
    return "GT_Custom" in sheet_name


import re as _re

# 审定表 sheet 名中的子码（如 "审定表D2-1" → "D2-1"），供联动回写 handler
# (_on_d_audit_determination_saved 匹配 ^[D-N]\d+-1$) 在聚合场景下取得正确 wp_code。
_DETERMINATION_CODE_RE = _re.compile(r"([D-N]\d+-1)\b")


def extract_determination_wp_code(sheet_name: str | None) -> str | None:
    """从聚合审定表 sheet 名提取审定表子码（如 "审定表D2-1" → "D2-1"）。

    用于多文件聚合：父码底稿（D2）保存审定表 sheet 时，联动回写 handler 需要
    sheet 级子码（D2-1）才能匹配 ^[D-N]\\d+-1$ 触发 trial_balance.audited_amount 回写。
    无法提取返回 None。
    """
    if not sheet_name:
        return None
    m = _DETERMINATION_CODE_RE.search(sheet_name)
    return m.group(1) if m else None


def _sheet_type_to_component(sheet_type: str) -> str | None:
    """sheet_type → componentType（经 class_code 链）。None 表示无法映射到 HTML 类。"""
    class_code = _SHEET_TYPE_TO_CLASS.get(sheet_type)
    if class_code is None:
        return None
    component = class_code_to_component(class_code)
    if component is None or component not in HTML_RENDERABLE_COMPONENTS:
        # 不允许 fallback 到 univer/未知类型导致空白
        return None
    return component


def _find_package_by_wp_code(
    registry: AccountPackageRegistryService, wp_code: str
) -> dict | None:
    """按 primary_wp_code 匹配工作包（注册表用 account_package_id 标识，父码在 primary_wp_code）。"""
    for pkg in registry.get_packages():
        if pkg.get("primary_wp_code") == wp_code:
            return pkg
    return None


async def resolve_package_sheets(
    db: AsyncSession,
    wp_code: str,
    project_id: UUID,
    *,
    registry: AccountPackageRegistryService | None = None,
    firm_id: UUID | None = None,
) -> list[ClassificationResult] | None:
    """读注册表 → 返回聚合 sheet 的 ClassificationResult 列表。

    None 表示该科目无注册表条目（调用方回退原 get_classification，零回归）。

    解析优先级（需求 6.5）：项目级自定义 > 事务所级自定义 > 内置 registry。

    流程（design §2）：
    1. 先查 custom_account_packages（项目>事务所）；命中用其 sheets
    2. 否则按 primary_wp_code 查内置 package；无 → None
    3. 对每个 sheet：跳过占位 → sheet_type 映射 class_code/componentType
    4. 解析 source_wp_code → 模板文件路径，填充 source_files
    5. 组装 ClassificationResult（含 source_files）

    忽略 package 的 mapping_status（不作消费门控）。
    """
    # ① 自定义工作包优先（项目级 > 事务所级）
    custom_pkg = None
    if db is not None:
        try:
            from app.services.custom_account_package_service import get_custom_package

            custom_pkg = await get_custom_package(
                db, wp_code=wp_code, project_id=project_id, firm_id=firm_id
            )
        except Exception as e:  # noqa: BLE001 — 自定义查询失败降级到内置 registry
            logger.warning("查询自定义科目工作包失败 wp_code=%s: %s", wp_code, e)
            custom_pkg = None
            # 查询失败可能导致事务 aborted → rollback 恢复以免级联影响后续查询
            try:
                await db.rollback()
            except Exception:
                pass

    if custom_pkg is not None:
        sheets = custom_pkg.get("sheets") or []
        if sheets:
            _primary = custom_pkg.get("primary_wp_code") or custom_pkg.get("wp_code") or wp_code
            return _build_results(wp_code, _primary, sheets)

    # ② 内置 registry
    registry = registry or AccountPackageRegistryService()
    try:
        pkg = _find_package_by_wp_code(registry, wp_code)
    except Exception as e:  # noqa: BLE001 — 注册表读取/解析失败按"无条目"降级，零回归
        logger.warning("读取科目工作包注册表失败 wp_code=%s: %s", wp_code, e)
        return None

    if pkg is None:
        return None

    sheets = pkg.get("sheets") or []
    if not sheets:
        return None

    return _build_results(wp_code, pkg.get("primary_wp_code") or wp_code, sheets)


def _build_results(
    wp_code: str, primary_wp_code: str, sheets: list[dict]
) -> list[ClassificationResult] | None:
    """把 sheets 声明（内置/自定义同结构）组装为 ClassificationResult 列表。

    首位插入一个合成「底稿目录」b-index sheet（需求 5.2：聚合后仍按审计阶段
    分类展示全部 sheet 导航），其 navigation_rows 由 _b_index 策略遍历全部
    classifications 自动生成。
    """
    # source_wp_code → 模板文件路径缓存（同一 package 内多 sheet 常共用同源文件）
    _template_cache: dict[str, str | None] = {}

    def _resolve_source_file(source_wp_code: str | None) -> str | None:
        if not source_wp_code:
            return None
        if source_wp_code not in _template_cache:
            path = find_template_file_any(source_wp_code)
            _template_cache[source_wp_code] = str(path) if path else None
        return _template_cache[source_wp_code]

    results: list[ClassificationResult] = []

    # 合成底稿目录（b-index）——置顶，供前端架构树 4 阶段分类导航
    results.append(
        ClassificationResult(
            wp_code=wp_code,
            sheet_name="底稿目录",
            class_code="B-目录",  # → b-index（_CLASS_TO_COMPONENT["B-"]）
            class_=None,
            scope="standalone",
            is_real_workpaper=True,
            delegated_module=None,
            render_schema_path=None,
            template_version_id=None,
            has_override=False,
            source_files=[],
        )
    )

    for sheet in sheets:
        sheet_name = sheet.get("sheet_name")
        if _is_placeholder_sheet(sheet_name):
            continue

        sheet_type = sheet.get("sheet_type") or ""
        component = _sheet_type_to_component(sheet_type)
        if component is None:
            logger.warning(
                "科目 %s sheet '%s' 的 sheet_type=%s 无法映射到 HTML 组件，跳过",
                wp_code, sheet_name, sheet_type,
            )
            continue

        class_code = _SHEET_TYPE_TO_CLASS[sheet_type]
        source_wp_code = sheet.get("source_wp_code") or primary_wp_code
        source_path = _resolve_source_file(source_wp_code)
        source_files = [source_path] if source_path else []

        results.append(
            ClassificationResult(
                wp_code=wp_code,
                sheet_name=sheet_name or "",
                class_code=class_code,
                class_=None,
                scope="standalone",
                is_real_workpaper=True,
                delegated_module=None,
                render_schema_path=sheet.get("schema_ref"),
                template_version_id=None,
                has_override=False,
                source_files=source_files,
            )
        )

    # 仅有合成底稿目录、无任何真实 sheet → 视为无有效聚合，返回 None 回退原逻辑
    if len(results) <= 1:
        return None

    return results
