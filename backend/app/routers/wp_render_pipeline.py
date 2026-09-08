"""``render-config`` 七阶段协调流水线的显式状态模型与前置阶段。

本模块先承载不涉及 sheet 物化的阶段。异常边界刻意复刻旧协调器：模板版本仅
吞 ``HTTPException``，分类缺失回退为空，工作包失败 rollback 后回退原分类，
项目年度/业务类别查询失败只记录并继续。不要在这里把既有 fail-open 改成
fail-fast；行为裁决由独立任务处理。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Awaitable, Callable, Mapping
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpCrossRef, WpIndex, WorkingPaper
from app.routers.wp_render_config_helpers import (
    _confirmation_initial_data,
    _extract_field_sources,
    _inject_confirmation_population,
    _inject_h0_book_amounts,
    _inject_l0_book_amounts,
    _maybe_custom_classifications,
    _resolve_sheet_type,
    _resolve_template_path,
    _unpack_sheet_schema,
)
from app.schemas.render_config_contract import CrossRefItem
from app.services.component_capability_registry import (
    ComponentCapabilityRegistry,
    load_component_capability_registry,
)
from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES
from app.services.project_audit_year import (
    PROJECT_AUDIT_YEAR_BIZ_SQL,
    PROJECT_AUDIT_YEAR_SQL,
)
from app.services.wp_account_package_resolver import resolve_package_sheets
from app.services.wp_classification_service import (
    ClassificationNotFoundError,
    ClassificationResult,
    WpClassificationService,
    derive_component_type,
)
from app.services.wp_template_version_service import WpTemplateVersionService

logger = logging.getLogger(__name__)

TemplateVersionServiceFactory = Callable[[AsyncSession], Any]
ClassificationServiceFactory = Callable[[AsyncSession], Any]
MaybeCustomResolver = Callable[..., Awaitable[list[ClassificationResult]]]
PackageResolver = Callable[..., Awaitable[list[ClassificationResult] | None]]
TemplatePathResolver = Callable[[WorkingPaper, str], str | None]


@dataclass(frozen=True, slots=True)
class RenderSubject:
    """完成存在性检查并在任何 rollback 前固化的底稿身份。"""

    wp_id: UUID
    working_paper: WorkingPaper
    project_id: UUID
    wp_code: str
    wp_name: str | None
    audit_cycle: str | None
    user_id: UUID


@dataclass(frozen=True, slots=True)
class ClassificationResolution:
    """模板版本、基础分类与工作包覆盖的一次裁决结果。"""

    template_version_id: UUID | None
    template_version: str | None
    classifications: tuple[ClassificationResult, ...]
    package_sheets: tuple[ClassificationResult, ...] | None
    package_applied: bool
    winning_source: str
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ScopeResolution:
    """scope 与 redirect 的纯裁决结果。"""

    scope: str
    is_real_workpaper: bool
    redirect_applied: bool
    delegated_module: str | None = None
    target_path: str | None = None

    def to_redirect_response(
        self,
        *,
        subject: RenderSubject,
        template_version: str | None,
    ) -> dict[str, Any]:
        """生成与旧入口逐字段相同的 redirect wire payload。"""
        if not self.redirect_applied:
            raise ValueError("非 redirect 裁决不能生成 redirect response")
        response: dict[str, Any] = {
            "wp_id": str(subject.wp_id),
            "wp_code": subject.wp_code,
            "project_id": str(subject.project_id),
            "scope": self.scope,
            "template_version": template_version,
            "sheets": [],
            "is_real_workpaper": self.is_real_workpaper,
            "redirect": True,
            "delegated_module": self.delegated_module,
        }
        if self.target_path is not None:
            response["target_path"] = self.target_path
        return response


@dataclass(frozen=True, slots=True)
class CommonRenderFacts:
    """sheet planning/materialization 共用且只加载一次的事实。"""

    html_data_all: Any
    cross_ref_items: tuple[CrossRefItem, ...]
    project_year: int | None
    business_category: str
    template_path: str | None


@dataclass(frozen=True, slots=True)
class SheetPlan:
    """单 sheet 的纯裁决；物化阶段不得再次选择 componentType。"""

    classification: ClassificationResult
    component_type: str
    host_policy: str
    override_hit: bool
    winning_source: str
    candidate_sources: tuple[str, ...]
    is_multi_sheet: bool
    renderer_available: bool
    whole_workbook_dedicated: bool
    force_applied: bool = False
    g_onlyoffice_shortcut: bool = False
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RenderDecision:
    """可序列化、脱敏的单 sheet 裁决轨迹。"""

    sheet_key: str
    chosen_component_type: str
    candidate_sources: tuple[str, ...]
    winning_source: str
    override_hit: bool
    redirect_applied: bool
    fallback_reason: str | None = None

    def to_wire(self) -> dict[str, Any]:
        return {
            "sheet_key": self.sheet_key,
            "chosen_component_type": self.chosen_component_type,
            "candidate_sources": list(self.candidate_sources),
            "winning_source": self.winning_source,
            "override_hit": self.override_hit,
            "redirect_applied": self.redirect_applied,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True, slots=True)
class RenderPlan:
    sheets: tuple[SheetPlan, ...]
    decisions: tuple[RenderDecision, ...]
    ordered_classifications: tuple[ClassificationResult, ...]


@dataclass(frozen=True, slots=True)
class MaterializationState:
    """请求内物化状态；memo 必须区分未命中与已缓存 ``None``。"""

    sheets: list[dict[str, Any]]
    dedicated_render_memo: dict[str, dict[str, Any] | None]


async def load_render_subject(
    *,
    wp_id: UUID,
    db: AsyncSession,
    current_user: Any,
) -> RenderSubject:
    """加载底稿、项目与索引，并保持旧 404 次序。"""
    working_paper = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if not working_paper:
        raise HTTPException(status_code=404, detail="底稿不存在")

    project_id = working_paper.project_id
    project_deleted = (
        await db.execute(
            sa.text("SELECT is_deleted FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
    ).scalar()
    if project_deleted:
        raise HTTPException(status_code=404, detail="项目已删除")

    wp_index = (
        await db.execute(
            sa.select(WpIndex).where(
                WpIndex.id == working_paper.wp_index_id,
                WpIndex.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if not wp_index:
        raise HTTPException(status_code=404, detail="底稿索引不存在")

    return RenderSubject(
        wp_id=wp_id,
        working_paper=working_paper,
        project_id=project_id,
        wp_code=wp_index.wp_code,
        wp_name=wp_index.wp_name,
        audit_cycle=wp_index.audit_cycle,
        user_id=current_user.id,
    )


def build_classification_api_subject(
    *,
    wp_code: str,
    project_id: UUID,
    wp_index: WpIndex,
    working_paper: WorkingPaper,
) -> RenderSubject:
    """classifications API 与 render-config 共享的 subject 构造（身份已由调用方校验）。"""
    return RenderSubject(
        wp_id=working_paper.id,
        working_paper=working_paper,
        project_id=project_id,
        wp_code=wp_code,
        wp_name=wp_index.wp_name,
        audit_cycle=wp_index.audit_cycle,
        user_id=working_paper.id,
    )


def format_classification_plan_divergence(
    *,
    classification_component_type: str,
    plan_component_type: str | None,
    winning_source: str | None = None,
    fallback_reason: str | None = None,
    override_hit: bool = False,
) -> str | None:
    """当 classifications API 基线类型与 render-config plan 分叉时返回显式原因。

    同身份一致则返回 None；禁止静默取任一方。
    """
    if plan_component_type is None:
        return (
            f"classifications_api={classification_component_type};"
            "render_plan=missing_sheet"
        )
    if classification_component_type == plan_component_type:
        return None
    parts = [
        f"classifications_api={classification_component_type}",
        f"render_plan={plan_component_type}",
        f"winning_source={winning_source or 'unknown'}",
    ]
    if fallback_reason:
        parts.append(f"fallback_reason={fallback_reason}")
    if override_hit:
        parts.append("override_hit=true")
    return ";".join(parts)


async def resolve_common_classification_resolution(
    *,
    db: AsyncSession,
    wp_code: str,
    project_id: UUID,
    template_version_id: UUID | None,
    wp_index: WpIndex,
    working_paper: WorkingPaper,
    template_version_service_factory: TemplateVersionServiceFactory = WpTemplateVersionService,
    classification_service_factory: ClassificationServiceFactory = WpClassificationService,
    maybe_custom_resolver: MaybeCustomResolver = _maybe_custom_classifications,
    package_resolver: PackageResolver = resolve_package_sheets,
) -> ClassificationResolution:
    """render-config 与 classifications API 共享的完整分类源裁决。"""
    subject = build_classification_api_subject(
        wp_code=wp_code,
        project_id=project_id,
        wp_index=wp_index,
        working_paper=working_paper,
    )
    return await resolve_classification_sources(
        subject=subject,
        db=db,
        template_version_id=template_version_id,
        template_version_service_factory=template_version_service_factory,
        classification_service_factory=classification_service_factory,
        maybe_custom_resolver=maybe_custom_resolver,
        package_resolver=package_resolver,
    )


async def resolve_common_classification_sources(
    *,
    db: AsyncSession,
    wp_code: str,
    project_id: UUID,
    template_version_id: UUID | None,
    wp_index: WpIndex,
    working_paper: WorkingPaper,
    template_version_service_factory: TemplateVersionServiceFactory = WpTemplateVersionService,
    classification_service_factory: ClassificationServiceFactory = WpClassificationService,
    maybe_custom_resolver: MaybeCustomResolver = _maybe_custom_classifications,
    package_resolver: PackageResolver = resolve_package_sheets,
) -> list[ClassificationResult]:
    """render-config 与 classifications API 共享的纯分类源裁决。

    调用方必须先按各自入口契约解析身份；本函数只复用模板版本、
    classification、custom fallback 和 account package 的统一顺序。
    """
    resolution = await resolve_common_classification_resolution(
        db=db,
        wp_code=wp_code,
        project_id=project_id,
        template_version_id=template_version_id,
        wp_index=wp_index,
        working_paper=working_paper,
        template_version_service_factory=template_version_service_factory,
        classification_service_factory=classification_service_factory,
        maybe_custom_resolver=maybe_custom_resolver,
        package_resolver=package_resolver,
    )
    return list(resolution.classifications)


async def resolve_classification_sources(
    *,
    subject: RenderSubject,
    db: AsyncSession,
    template_version_id: UUID | None = None,
    template_version_service_factory: TemplateVersionServiceFactory = WpTemplateVersionService,
    classification_service_factory: ClassificationServiceFactory = WpClassificationService,
    maybe_custom_resolver: MaybeCustomResolver = _maybe_custom_classifications,
    package_resolver: PackageResolver = resolve_package_sheets,
) -> ClassificationResolution:
    """按旧顺序裁决模板版本、classification、自定义底稿与工作包。"""
    template_version: str | None = None
    if template_version_id is None:
        try:
            version = await template_version_service_factory(db).get_current_version()
            template_version = version.version
            template_version_id = version.id
        except HTTPException:
            pass
    else:
        try:
            version = await template_version_service_factory(db).get_version_by_id(
                template_version_id
            )
            template_version = version.version
        except HTTPException:
            pass

    try:
        classifications = await classification_service_factory(db).get_classification(
            wp_code=subject.wp_code,
            project_id=subject.project_id,
            template_version_id=template_version_id,
        )
    except ClassificationNotFoundError:
        classifications = []

    classifications = await maybe_custom_resolver(
        db,
        subject.project_id,
        subject.wp_code,
        subject.wp_name,
        classifications,
        subject.working_paper,
    )

    package_sheets: list[ClassificationResult] | None
    fallback_reason: str | None = None
    try:
        package_sheets = await package_resolver(
            db,
            subject.wp_code,
            subject.project_id,
        )
    except Exception as exc:  # noqa: BLE001 — 忠实保留旧 fail-open
        logger.warning("科目工作包聚合失败 wp_code=%s: %s", subject.wp_code, exc)
        package_sheets = None
        fallback_reason = f"package_resolver_error:{type(exc).__name__}"
        try:
            await db.rollback()
        except Exception:
            pass

    package_applied = bool(package_sheets)
    if package_applied:
        classifications = package_sheets or []

    return ClassificationResolution(
        template_version_id=template_version_id,
        template_version=template_version,
        classifications=tuple(classifications),
        package_sheets=(
            tuple(package_sheets) if package_sheets is not None else None
        ),
        package_applied=package_applied,
        winning_source="account_package" if package_applied else "classification",
        fallback_reason=fallback_reason,
    )


def resolve_scope_redirect(
    *,
    subject: RenderSubject,
    resolution: ClassificationResolution,
    overrides: Mapping[str, str],
) -> ScopeResolution:
    """保持 scope redirect 高于 materiality redirect 的原优先级。"""
    first = resolution.classifications[0] if resolution.classifications else None
    scope = first.scope if first is not None else "standalone"
    is_real = first.is_real_workpaper if first is not None else True

    if scope in {"consolidated", "parent_only"}:
        return ScopeResolution(
            scope=scope,
            is_real_workpaper=is_real,
            redirect_applied=True,
            delegated_module=(
                (first.delegated_module if first is not None else None)
                or "consolidation_hub"
            ),
        )
    if overrides.get(subject.wp_code) == "redirect-materiality":
        return ScopeResolution(
            scope=scope,
            is_real_workpaper=False,
            redirect_applied=True,
            delegated_module="materiality",
            target_path="/materiality",
        )
    return ScopeResolution(
        scope=scope,
        is_real_workpaper=is_real,
        redirect_applied=False,
    )


async def load_common_render_facts(
    *,
    subject: RenderSubject,
    db: AsyncSession,
    template_path_resolver: TemplatePathResolver = _resolve_template_path,
) -> CommonRenderFacts:
    """加载 parsed data、cross refs、第一次年度查询与模板路径。"""
    html_data_all = (subject.working_paper.parsed_data or {}).get("html_data", {})
    cross_refs = (
        await db.execute(
            sa.select(WpCrossRef).where(
                WpCrossRef.source_wp_id == subject.wp_id,
                WpCrossRef.project_id == subject.project_id,
            )
        )
    ).scalars().all()
    cross_ref_items = tuple(
        CrossRefItem(wp_code=item.target_wp_code, cell=item.cell_reference)
        for item in cross_refs
    )

    project_year: int | None = None
    business_category = "C"
    try:
        project = (
            await db.execute(
                PROJECT_AUDIT_YEAR_BIZ_SQL,
                {"pid": str(subject.project_id)},
            )
        ).first()
        if project:
            project_year = project[0]
            business_category = project[1] or "C"
    except Exception as exc:  # noqa: BLE001 — 忠实保留旧 fail-open
        logger.warning(
            "查询项目年度/业务类别失败 pid=%s: %s",
            subject.project_id,
            exc,
        )

    return CommonRenderFacts(
        html_data_all=html_data_all,
        cross_ref_items=cross_ref_items,
        project_year=project_year,
        business_category=business_category,
        template_path=template_path_resolver(
            subject.working_paper,
            subject.wp_code,
        ),
    )


# ─── Stage 5: pure sheet planning ────────────────────────────────────────────

_SHEET_CODE_RE = re.compile(r"([A-Z]\d+(?:-\d+)*[A-Z]?)(?:-新增)?\s*$")
_PUNCT_NORM = str.maketrans("（），：；", "(),:;")
_WHITESPACE_STRIP = str.maketrans("", "", " \u3000\t")
_WHOLE_WP_MULTISHEET_DEDICATED = frozenset(DEDICATED_COMPONENT_TYPES)


@lru_cache(maxsize=1)
def _capability_registry() -> ComponentCapabilityRegistry:
    return load_component_capability_registry()


def sheet_name_matches(actual: str | None, requested: str | None) -> bool:
    """与 legacy sheet filter 等价的名称匹配。"""
    if actual == requested:
        return True
    if not actual or not requested:
        return False
    if actual.translate(_WHITESPACE_STRIP) == requested.translate(_WHITESPACE_STRIP):
        return True
    actual_code = _SHEET_CODE_RE.search(actual)
    requested_code = _SHEET_CODE_RE.search(requested)
    if actual_code and requested_code:
        left, right = actual_code.group(1), requested_code.group(1)
        if left == right and left[-1:].isalpha():
            return True
    return (
        actual.translate(_PUNCT_NORM).translate(_WHITESPACE_STRIP)
        == requested.translate(_PUNCT_NORM).translate(_WHITESPACE_STRIP)
    )


def _sheet_filter_reason(
    *,
    classification: ClassificationResult,
    requested_sheet_name: str | None,
    wp_code: str,
    overrides: Mapping[str, str],
    parent_override: str | None,
) -> str | None:
    sheet_name = classification.sheet_name
    if requested_sheet_name and not sheet_name_matches(sheet_name, requested_sheet_name):
        return "request_sheet_mismatch"
    if sheet_name and "GT_Custom" in sheet_name:
        return "gt_custom_hidden"
    if sheet_name and overrides.get(sheet_name) == "skip":
        return "sheet_name_skip_override"
    if sheet_name and (
        sheet_name.endswith("-原版") or sheet_name.endswith("-原")
    ):
        return "legacy_original_suffix"
    if sheet_name and (
        "原版本备份" in sheet_name
        or sheet_name.startswith("参考用-")
        or sheet_name.endswith("（原）")
    ):
        return "legacy_backup_sheet"
    if sheet_name and "删除" in sheet_name:
        return "deleted_sheet_marker"
    if not sheet_name:
        return None

    tail_match = _SHEET_CODE_RE.search(sheet_name)
    if tail_match and overrides.get(tail_match.group(1)) == "skip":
        return "tail_code_skip_override"
    if not tail_match:
        prefix_match = re.match(r"([A-Z]\d+(?:-\d+)*)", sheet_name)
        if prefix_match and overrides.get(prefix_match.group(1)) == "skip":
            return "prefix_code_skip_override"
    if overrides.get(f"{wp_code}-{sheet_name}") == "skip":
        return "composite_skip_override"

    if parent_override and parent_override in _WHOLE_WP_MULTISHEET_DEDICATED:
        is_bundle = parent_override.endswith("-bundle")
        if (
            "选项清单" in sheet_name
            or "不归档" in sheet_name
            or "不打印" in sheet_name
            or sheet_name.startswith("示例")
            or (is_bundle and "底稿目录" in sheet_name)
        ):
            return "dedicated_auxiliary_sheet"
    return None


def _resolve_sheet_override(
    *,
    wp_code: str,
    sheet_name: str | None,
    is_multi_sheet: bool,
    overrides: Mapping[str, str],
) -> tuple[str | None, str | None]:
    if not is_multi_sheet or not sheet_name:
        return None, None
    match = _SHEET_CODE_RE.search(sheet_name)
    if match:
        value = overrides.get(match.group(1))
        if value:
            return value, "sheet_code_override"
    value = overrides.get(sheet_name)
    if value:
        return value, "sheet_name_override"
    value = overrides.get(f"{wp_code}-{sheet_name}")
    if value:
        return value, "composite_sheet_override"
    return None, None


def _append_reason(current: str | None, value: str) -> str:
    return f"{current};{value}" if current else value


async def plan_sheets(
    *,
    subject: RenderSubject,
    resolution: ClassificationResolution,
    facts: CommonRenderFacts,
    requested_sheet_name: str | None,
    force_component_type: str | None,
    overrides: Mapping[str, str],
    template_order_loader: Callable[[str], Mapping[str, int]],
    capabilities: ComponentCapabilityRegistry | None = None,
) -> RenderPlan:
    """纯裁决 sheet 可见性、component winner 与 host fate。

    schema、持久化数据、renderer 和 DB 注入均留给 materialize 阶段。host policy
    仅在 legacy 也会降级的多 sheet/无 renderer 路径生效；单 sheet 仍保留原
    componentType。
    """
    registry = capabilities or _capability_registry()
    classifications = list(resolution.classifications)
    parent_override = overrides.get(subject.wp_code)

    real_sheets = [
        item
        for item in classifications
        if not (item.sheet_name and "GT_Custom" in item.sheet_name)
        and not (getattr(item, "class_code", "") or "").startswith("I-")
        and overrides.get(item.sheet_name) != "skip"
        and not (
            item.sheet_name
            and (
                item.sheet_name.endswith("-原版")
                or item.sheet_name.endswith("-原")
            )
        )
    ]
    is_multi_sheet = len(real_sheets) > 1

    if (
        is_multi_sheet
        and not resolution.package_sheets
        and facts.template_path
        and str(facts.template_path).endswith((".xlsx", ".xls"))
    ):
        template_order = await asyncio.to_thread(
            template_order_loader,
            str(facts.template_path),
        )
        if template_order:
            classifications = sorted(
                classifications,
                key=lambda item: template_order.get(item.sheet_name, 999),
            )

    plans: list[SheetPlan] = []
    decisions: list[RenderDecision] = []
    for classification in classifications:
        filter_reason = _sheet_filter_reason(
            classification=classification,
            requested_sheet_name=requested_sheet_name,
            wp_code=subject.wp_code,
            overrides=overrides,
            parent_override=parent_override,
        )
        if filter_reason:
            decisions.append(
                RenderDecision(
                    sheet_key=classification.sheet_name,
                    chosen_component_type="skip",
                    candidate_sources=(filter_reason,),
                    winning_source="visibility_filter",
                    override_hit="override" in filter_reason,
                    redirect_applied=False,
                    fallback_reason=filter_reason,
                )
            )
            continue

        candidates = [f"class_code:{classification.class_code or ''}"]
        if parent_override:
            candidates.append(f"wp_override:{parent_override}")
        sheet_override, sheet_override_source = _resolve_sheet_override(
            wp_code=subject.wp_code,
            sheet_name=classification.sheet_name,
            is_multi_sheet=is_multi_sheet,
            overrides=overrides,
        )
        if sheet_override:
            candidates.append(f"{sheet_override_source}:{sheet_override}")

        fallback_reason: str | None = None
        override_hit = False
        winning_source = "class_code"
        try:
            if is_multi_sheet:
                if sheet_override:
                    component_type = sheet_override
                    override_hit = True
                    winning_source = sheet_override_source or "sheet_override"
                elif parent_override in _WHOLE_WP_MULTISHEET_DEDICATED:
                    component_type = parent_override
                    override_hit = True
                    winning_source = "whole_workpaper_override"
                elif resolution.package_sheets and parent_override:
                    if (getattr(classification, "class_code", "") or "")[:2] == "B-":
                        try:
                            component_type = derive_component_type(
                                classification,
                                ignore_wp_code_override=True,
                            )
                        except ClassificationNotFoundError:
                            component_type = "b-index"
                            fallback_reason = "package_index_default"
                        winning_source = "package_index_class_code"
                    else:
                        component_type = parent_override
                        override_hit = True
                        winning_source = "package_parent_override"
                else:
                    try:
                        component_type = derive_component_type(
                            classification,
                            ignore_wp_code_override=True,
                        )
                    except ClassificationNotFoundError:
                        component_type = parent_override or "skip"
                        fallback_reason = "classification_not_found"
                        if parent_override:
                            override_hit = True
                            winning_source = "wp_override_fallback"
                        else:
                            winning_source = "skip_fallback"
            else:
                if parent_override:
                    component_type = parent_override
                    override_hit = True
                    winning_source = "wp_override"
                else:
                    component_type = derive_component_type(classification)
        except ClassificationNotFoundError:
            component_type = "skip"
            fallback_reason = "classification_not_found"
            winning_source = "skip_fallback"

        class_code = getattr(classification, "class_code", "") or ""
        g_shortcut = (
            is_multi_sheet
            and class_code.startswith("G-")
            and not sheet_override
            and not (
                parent_override
                and component_type == parent_override
            )
        )
        force_applied = False
        if g_shortcut:
            component_type = "onlyoffice-sheet"
            winning_source = "g_multi_sheet_shortcut"
            fallback_reason = _append_reason(
                fallback_reason,
                "g_multi_sheet_onlyoffice",
            )
        elif (
            force_component_type
            and force_component_type in registry.backend_renderer_types
        ):
            candidates.append(f"forced_component:{force_component_type}")
            component_type = force_component_type
            force_applied = True
            winning_source = "forced_component"

        capability = registry.get(component_type)
        renderer_available = bool(
            capability and capability.has_backend_renderer
        )
        host_policy = capability.host_policy if capability else "unresolved"
        if (
            is_multi_sheet
            and not renderer_available
            and host_policy in {"onlyoffice", "unresolved"}
        ):
            if component_type != "onlyoffice-sheet":
                candidates.append(f"host_policy:{host_policy}")
                component_type = "onlyoffice-sheet"
                winning_source = "manifest_host_policy"
                fallback_reason = _append_reason(
                    fallback_reason,
                    (
                        "unregistered_component_legacy_onlyoffice"
                        if host_policy == "unresolved"
                        else "manifest_onlyoffice_fallback"
                    ),
                )
            host_policy = "onlyoffice"
            renderer_available = False

        whole_dedicated = (
            component_type == parent_override
            and parent_override in _WHOLE_WP_MULTISHEET_DEDICATED
        )
        plan = SheetPlan(
            classification=classification,
            component_type=component_type,
            host_policy=host_policy,
            override_hit=override_hit,
            winning_source=winning_source,
            candidate_sources=tuple(candidates),
            is_multi_sheet=is_multi_sheet,
            renderer_available=renderer_available,
            whole_workbook_dedicated=whole_dedicated,
            force_applied=force_applied,
            g_onlyoffice_shortcut=g_shortcut,
            fallback_reason=fallback_reason,
        )
        plans.append(plan)
        decisions.append(
            RenderDecision(
                sheet_key=classification.sheet_name,
                chosen_component_type=component_type,
                candidate_sources=plan.candidate_sources,
                winning_source=winning_source,
                override_hit=override_hit,
                redirect_applied=False,
                fallback_reason=fallback_reason,
            )
        )

    return RenderPlan(
        sheets=tuple(plans),
        decisions=tuple(decisions),
        ordered_classifications=tuple(classifications),
    )


# ─── Stage 6: sheet materialization ─────────────────────────────────────────

async def materialize_sheet(
    *,
    plan: SheetPlan,
    render_plan: RenderPlan,
    state: MaterializationState,
    subject: RenderSubject,
    resolution: ClassificationResolution,
    facts: CommonRenderFacts,
    db: AsyncSession,
    schema_service: Any,
    renderer_dispatch: Mapping[str, Callable[[Any], Awaitable[Any]]],
) -> None:
    """物化一个已裁决 sheet；不得重新选择 componentType/host。"""
    from app.routers.wp_render_strategies._context import RenderContext
    from app.routers.wp_render_strategies._context import CrossRefItem as ContextCrossRef

    classification = plan.classification
    component_type = plan.component_type
    schema_data: dict[str, Any] | None = None
    try:
        schema_data = schema_service.load_schema(
            wp_code=subject.wp_code,
            template_version_id=resolution.template_version_id,
        )
    except FileNotFoundError:
        pass
    sheet_schema = _unpack_sheet_schema(schema_data, classification.sheet_name)
    sheet_html_data = facts.html_data_all.get(classification.sheet_name)
    cross_refs = [item.model_dump() for item in facts.cross_ref_items]

    # Legacy G- shortcut 位于 force 与 renderer 之前，且输出字段刻意更少。
    if plan.g_onlyoffice_shortcut:
        state.sheets.append(
            {
                "sheet_name": classification.sheet_name,
                "componentType": component_type,
                "schema": sheet_schema,
                "html_data": {
                    "onlyoffice": True,
                    "sheet_name": classification.sheet_name,
                },
                "cross_refs": cross_refs,
            }
        )
        return

    renderer = renderer_dispatch.get(component_type)
    if renderer and plan.whole_workbook_dedicated and component_type in state.dedicated_render_memo:
        memoized = state.dedicated_render_memo[component_type]
        if memoized is not None:
            sheet_html_data = memoized
    elif renderer:
        from app.services.wp_metrics import wp_metrics

        wp_metrics.inc_renderer_invocation(component_type)
        context = RenderContext(
            db=db,
            project_id=subject.project_id,
            wp_id=subject.wp_id,
            wp_code=subject.wp_code,
            working_paper=subject.working_paper,
            classification=classification,
            component_type=component_type,
            sheet_html_data=sheet_html_data,
            sheet_schema=sheet_schema,
            template_file_path=facts.template_path,
            year=facts.project_year,
            business_category=facts.business_category,
            cross_ref_items=[
                ContextCrossRef(wp_code=item.wp_code, cell=item.cell)
                for item in facts.cross_ref_items
            ],
            prep_info=None,
            classifications=list(render_plan.ordered_classifications),
            audit_cycle=subject.audit_cycle,
            source_files=list(
                getattr(classification, "source_files", []) or []
            ),
            user_id=subject.user_id,
        )
        try:
            result = await renderer(context)
            if result is not None:
                sheet_html_data = result
            if plan.whole_workbook_dedicated:
                # 赋值必须发生在 result=None 时，缓存存在性本身可阻止第二次调用。
                state.dedicated_render_memo[component_type] = result
            if (
                context.sheet_schema is not None
                and context.sheet_schema != sheet_schema
            ):
                sheet_schema = context.sheet_schema
        except Exception as exc:  # noqa: BLE001 — 单 sheet 失败不影响后续 sheet
            logger.warning(
                "sheet '%s' 渲染失败 (componentType=%s): %s",
                classification.sheet_name,
                component_type,
                exc,
            )
            try:
                await db.rollback()
            except Exception:
                pass
    else:
        if plan.is_multi_sheet and plan.host_policy == "onlyoffice":
            sheet_html_data = {
                "onlyoffice": True,
                "sheet_name": classification.sheet_name,
            }
        elif (
            not sheet_html_data
            and plan.is_multi_sheet
            and plan.host_policy == "confirmation"
        ):
            sheet_html_data = _confirmation_initial_data(component_type)
        elif (
            not sheet_html_data
            and facts.template_path
            and plan.is_multi_sheet
        ):
            try:
                from app.services.wp_grid_extract import extract_grid, strip_standard_header

                grid = extract_grid(
                    facts.template_path,
                    classification.sheet_name,
                )
                if isinstance(grid, dict) and grid.get("cells"):
                    sheet_html_data = strip_standard_header(grid)
            except Exception:  # noqa: BLE001 — 与 legacy 一致静默保留空数据
                pass

    if component_type == "custom":
        try:
            from app.services.custom_workpaper_projection import project_if_empty

            sheet_html_data = project_if_empty(
                subject.working_paper,
                classification.sheet_name,
                sheet_html_data,
            )
        except Exception as exc:  # noqa: BLE001 — 补齐失败不阻断渲染
            logger.warning(
                "custom 投影补齐失败 wp_id=%s sheet=%s: %s",
                subject.wp_id,
                classification.sheet_name,
                exc,
            )

    if component_type == "skip":
        return

    if component_type == "confirmation-summary" and isinstance(sheet_html_data, dict):
        # 三个注入器必须保持独立 try；任一失败不得阻止后续注入器。
        try:
            await _inject_confirmation_population(
                db,
                subject.project_id,
                facts.project_year,
                sheet_html_data,
            )
        except Exception:
            pass
        try:
            await _inject_h0_book_amounts(
                db,
                subject.project_id,
                facts.project_year,
                subject.wp_code,
                sheet_html_data,
            )
        except Exception:
            pass
        try:
            await _inject_l0_book_amounts(
                db,
                subject.project_id,
                facts.project_year,
                subject.wp_code,
                sheet_html_data,
            )
        except Exception:
            pass

    state.sheets.append(
        {
            "sheet_name": classification.sheet_name,
            "componentType": component_type,
            "schema": sheet_schema,
            "html_data": sheet_html_data,
            "cross_refs": cross_refs,
            "sheet_type": _resolve_sheet_type(
                sheet_schema,
                schema_data,
                classification.sheet_name,
            ),
            "field_sources": _extract_field_sources(
                sheet_schema,
                schema_data,
                classification.sheet_name,
            ),
        }
    )


# ─── Stage 7: response finalization ─────────────────────────────────────────

async def finalize_render_response(
    *,
    subject: RenderSubject,
    resolution: ClassificationResolution,
    scope: ScopeResolution,
    facts: CommonRenderFacts,
    render_plan: RenderPlan,
    materialized_sheets: list[dict[str, Any]],
    parent_component_type: str | None,
    self_contained_types: frozenset[str] | set[str],
    db: AsyncSession,
    auto_fill_resolver: Callable[..., Awaitable[dict[str, Any]]],
    annotate_sheets: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    guidance_loader: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    """按固定顺序完成 collapse → auto-fill → sign → standards → identity → response。"""
    sheets = materialized_sheets

    if parent_component_type in self_contained_types and sheets:
        representative = next(
            (
                sheet
                for sheet in sheets
                if sheet["componentType"] == parent_component_type
            ),
            sheets[0],
        )
        sheets = [{**representative, "html_data": {}}]

    # 第二次年度查询独立存在：不要复用 facts.project_year。
    fill_results: dict[str, Any] = {}
    try:
        year_row = (
            await db.execute(
                PROJECT_AUDIT_YEAR_SQL,
                {"pid": str(subject.project_id)},
            )
        ).first()
        if year_row and year_row[0]:
            combined = {
                "sheets": {
                    sheet["sheet_name"]: sheet["schema"]
                    for sheet in sheets
                    if isinstance(sheet.get("schema"), dict)
                }
            }
            try:
                fill_results = await auto_fill_resolver(
                    schema=combined,
                    project_id=subject.project_id,
                    year=year_row[0],
                    db=db,
                )
            except Exception as exc:
                logger.warning(
                    "auto-fill 取数失败 pid=%s: %s",
                    subject.project_id,
                    exc,
                )
    except Exception as exc:
        logger.warning(
            "auto-fill 年度查询失败 pid=%s: %s",
            subject.project_id,
            exc,
        )
        try:
            await db.rollback()
        except Exception:
            pass

    sign_status: str | None = None
    permissions: dict[str, bool] | None = None
    first_component_type = sheets[0]["componentType"] if sheets else None
    if first_component_type == "word-template" and facts.project_year:
        sign_scope = (
            f"word_template:A16:{subject.wp_code}"
            if subject.wp_code.startswith("A16-")
            else f"word_template:{subject.wp_code}"
        )
        try:
            from app.services.field_override_service import FieldOverrideService

            sign_status = await FieldOverrideService(db).get(
                project_id=subject.project_id,
                year=facts.project_year,
                scope=sign_scope,
                item_key="sign_status",
                field="value",
            )
        except Exception as exc:  # noqa: BLE001 — 保持 draft fail-open
            logger.warning(
                "sign_status 查询失败 wp_code=%s: %s",
                subject.wp_code,
                exc,
            )
        if not sign_status:
            sign_status = "draft"
        permissions = {"edit": sign_status != "signed"}

    standards: list[str] = []
    try:
        from app.routers.wp_render_config_helpers import inject_applicable_standards
        from app.services.standard_unification_service import (
            StandardUnificationService,
            derive_applicable_standards,
        )

        standards = derive_applicable_standards(
            await StandardUnificationService(db).get_standard(subject.project_id)
        )
        inject_applicable_standards(sheets, standards)
    except Exception as exc:  # noqa: BLE001 — 保持旧 fail-open
        logger.warning(
            "applicable_standards 注入失败 pid=%s: %s",
            subject.project_id,
            exc,
        )

    # 此调用保持 fail-fast，且必须位于 standards 后、guidance 前。
    annotate_sheets(sheets)

    response: dict[str, Any] = {
        "wp_id": str(subject.wp_id),
        "wp_code": subject.wp_code,
        "project_id": str(subject.project_id),
        "scope": scope.scope,
        "is_real_workpaper": scope.is_real_workpaper,
        "template_version": resolution.template_version,
        "audit_year": facts.project_year,
        "applicable_standards": standards,
        "sheets": sheets,
        "fill_results": fill_results,
        "guidance": guidance_loader(subject.wp_code),
        "decision_trace": [
            decision.to_wire() for decision in render_plan.decisions
        ],
    }
    if sign_status is not None:
        response["sign_status"] = sign_status
        response["permissions"] = permissions
    return response
