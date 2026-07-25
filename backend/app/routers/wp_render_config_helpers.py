"""底稿渲染配置 —— 纯辅助函数与常量（从 wp_render_config.py 抽离）

行为保持一致的重构：本模块仅承载 wp_render_config.py 中自包含的纯/辅助逻辑
（sheet_type 推断、字段来源提取、schema 解包、模板路径解析、confirmation 初始数据、
自定义归类合成、语义注册表缓存）。原路由文件通过 re-import 使这些名字在其命名空间
内仍可解析，故所有既有调用点无需改动。

本模块 **不得** 从 wp_render_config.py 导入（避免循环依赖）。
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import (
    WorkingPaper,
    WpSourceType,
)
from app.services.wp_classification_service import ClassificationResult

# confirmation 组件首次打开时的空初始数据（_format 标记让前端识别为新格式，显示可编辑空表）
_CONFIRMATION_FORMAT_MAP: dict[str, str] = {
    "confirmation-summary": "confirmation-v1",
    "confirmation-entity-verify": "entity-verify-v1",
    "confirmation-followup": "confirmation-followup-v1",
    "confirmation-diff-reconcile": "diff-reconcile-v1",
    "confirmation-diff-checklist": "diff-checklist-v1",
    "confirmation-alternative-d05": "alternative-d05-v1",
    "confirmation-alternative-d06": "alternative-d06-v1",
    "confirmation-alternative-f05": "alternative-f05-v1",
    "confirmation-alternative-f06": "alternative-f06-v1",
    "confirmation-diff-securities": "diff-securities-v1",
    "confirmation-alternative-g06": "alternative-g06-v1",
    "confirmation-alternative-h05": "alternative-h05-v1",
    "confirmation-alternative-k05": "alternative-k05-v1",
    "confirmation-alternative-k06": "alternative-k06-v1",
    "confirmation-reliability": "reliability-v1",
    "confirmation-fraud-risk": "fraud-risk-d08-v1",
}


def _confirmation_initial_data(component_type: str) -> dict:
    """为 confirmation 精细组件生成空的新格式初始数据。

    前端组件检测 `_format` 字段 → 识别为新格式 → 显示可编辑空表。
    无 `_format` 则前端降级为"旧格式只读"（设计意图：区分新旧数据）。
    """
    fmt = _CONFIRMATION_FORMAT_MAP.get(component_type, "confirmation-v1")
    return {"_format": fmt, "rows": [], "sampling": {}, "notes": {}, "conclusion": {}}


# ─── 函证覆盖率 population（科目审定总额）解析与注入 ──────────────────────────
# 中文科目名 → TB 标准科目编码前缀（confirmation 相关科目 canonical 子集）
_ACCOUNT_TYPE_TO_CODE_PREFIX: dict[str, str] = {
    "库存现金": "1001", "银行存款": "1002", "其他货币资金": "1012",
    "应收票据": "1121", "应收账款": "1122", "预付账款": "1123",
    "其他应收款": "1221", "长期应收款": "1531",
    "应付票据": "2201", "应付账款": "2202", "预收账款": "2203",
    "其他应付款": "2241", "合同负债": "2203",
    "短期借款": "2001", "长期借款": "2501",
}


async def _resolve_confirmation_population(
    db: AsyncSession,
    project_id: UUID | str,
    year: int | None,
    rows: list[dict],
) -> float | None:
    """从函证行的科目类型解析科目审定总额（Σ 相关科目 trial_balance 审定）。

    - 中文科目名（account_type）→ 编码前缀 → SUM(audited_amount) LIKE '前缀%'。
    - 每前缀净额取绝对值后累加（科目账面余额量级；trial_balance v2 本为自然正数，abs 为安全兜底）。
    - 无法映射任一前缀 / year 缺失 / SUM 为 0 → None（Skip-on-missing，不臆测、不返回 0 冒充）。
    - 查询异常 → None（fail-open，不阻断渲染）。
    """
    if not rows or year is None:
        return None
    types = {str(r.get("account_type") or "").strip() for r in rows if isinstance(r, dict)}
    prefixes = {p for t in types if (p := _ACCOUNT_TYPE_TO_CODE_PREFIX.get(t))}
    if not prefixes:
        return None
    total = 0.0
    matched = False
    try:
        for prefix in prefixes:
            result = await db.execute(
                sa.text(
                    "SELECT SUM(audited_amount) AS s FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "AND standard_account_code LIKE :pat"
                ),
                {"pid": str(project_id), "year": year, "pat": f"{prefix}%"},
            )
            s = result.scalar()
            if s is not None:
                matched = True
                total += abs(float(s))
    except Exception:  # noqa: BLE001 — 取数失败不阻断渲染
        return None
    if not matched or total <= 0:
        return None
    return total


async def _inject_confirmation_population(
    db: AsyncSession,
    project_id: UUID | str,
    year: int | None,
    sheet_html_data: dict,
) -> None:
    """向 confirmation-summary 的 htmlData 加法式注入 project_context.population_amount。

    - 仅处理含 confirmation-v1 rows 的 dict；不改 rows/_format/其它字段（additive）。
    - population 不可解析 → 注入 null（前端据此显示"不可用"，不用 0 冒充）。
    """
    if not isinstance(sheet_html_data, dict):
        return
    rows = sheet_html_data.get("rows")
    population = await _resolve_confirmation_population(
        db, project_id, year, rows if isinstance(rows, list) else []
    )
    ctx = sheet_html_data.setdefault("project_context", {})
    if isinstance(ctx, dict):
        ctx["population_amount"] = population


# 标准底稿编号判定：统一使用 ACNR grammar_v1 的 STANDARD_WP_CODE_RE (R12.2)
# 旧版 [A-I]\d 已修正为 [A-S]\d，覆盖 J~S 循环（R12.4, R12.5）
from app.services.acnr.grammar import is_standard_wp_code as _is_standard_wp_code_fn


# ─── sheet_type 推断辅助（Task 2.1: schema 显式 > 启发式 > null）─────────────

# 从 wp_generic_processor._detect_sheet_type 提取的启发式映射表
# 将旧式返回值（summary/detail/analysis/procedure 等）映射到 SheetContentType 枚举
_HEURISTIC_TO_SHEET_CONTENT_TYPE: dict[str, str] = {
    "summary": "audit_sheet",
    "detail": "detail_table",
    "analysis": "analysis",
    "procedure": "procedure",
    "adjustment": "adjustment",
    "disclosure": "disclosure",
    "movement": "detail_table",
    "aging": "analysis",
}


def _infer_sheet_type_from_schema(sheet_schema: dict | None, full_schema: dict | None) -> str | None:
    """从 schema YAML 中提取显式 sheet_type（优先 per-sheet，否则顶层）。

    Returns:
        显式配置的 sheet_type 字符串，或 None（schema 未配置）。
    """
    # per-sheet schema 中有 sheet_type
    if isinstance(sheet_schema, dict) and sheet_schema.get("sheet_type"):
        return str(sheet_schema["sheet_type"])
    # 顶层 schema 有 sheet_type（单 sheet yaml）
    if isinstance(full_schema, dict) and full_schema.get("sheet_type"):
        return str(full_schema["sheet_type"])
    return None


def _infer_sheet_type_by_heuristic(sheet_name: str) -> str | None:
    """用中文关键词启发式推断 sheet_type（与 wp_generic_processor._detect_sheet_type 同口径）。

    Returns:
        SheetContentType 枚举字符串，或 None（无法推断）。
    """
    name = sheet_name or ""
    # 顺序很重要：更具体的关键词优先匹配
    if "函证" in name or "询证" in name:
        return "confirmation_summary"
    if "控制测试" in name:
        return "control_test"
    if "内控" in name and "了解" in name:
        return "control_understanding"
    if "控制" in name and "了解" in name:
        return "control_understanding"
    if "控制" in name and "测试" in name:
        return "control_test"
    if "审定" in name or "汇总" in name:
        return "audit_sheet"
    if "明细" in name or "清单" in name:
        return "detail_table"
    if "分析" in name or "测算" in name or "复核" in name:
        return "analysis"
    if "程序" in name:
        return "procedure"
    if "调整" in name:
        return "adjustment"
    if "披露" in name or "附注" in name:
        return "disclosure"
    if "结论" in name:
        return "conclusion"
    if "目录" in name or "索引" in name or "驾驶" in name or "控制台" in name:
        return "control_panel"
    return None


def _load_semantic_registry() -> dict:
    """加载 D1/D2 语义标注注册表（缓存于模块级变量）。"""
    global _SEMANTIC_REGISTRY_CACHE
    if _SEMANTIC_REGISTRY_CACHE is not None:
        return _SEMANTIC_REGISTRY_CACHE
    import json
    # schema 文件实际位于 backend/data/ledger_adapters/wp_render_schema/
    registry_path = Path(__file__).parent.parent.parent / "data" / "ledger_adapters" / "wp_render_schema" / "d1_d2_semantic_registry.json"
    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            _SEMANTIC_REGISTRY_CACHE = data.get("sheets", {})
        except (json.JSONDecodeError, OSError):
            _SEMANTIC_REGISTRY_CACHE = {}
    else:
        _SEMANTIC_REGISTRY_CACHE = {}
    return _SEMANTIC_REGISTRY_CACHE


_SEMANTIC_REGISTRY_CACHE: dict | None = None


def _infer_sheet_type_from_registry(sheet_name: str) -> str | None:
    """从 D1/D2 语义标注注册表查找 sheet_type。"""
    registry = _load_semantic_registry()
    entry = registry.get(sheet_name)
    if entry and isinstance(entry, dict):
        st = entry.get("sheet_type")
        if st and isinstance(st, str):
            return st
    return None


def _resolve_sheet_type(
    sheet_schema: dict | None,
    full_schema: dict | None,
    sheet_name: str,
) -> str | None:
    """按优先级确定 sheet_type: schema 显式 > registry > 启发式 > None。"""
    # 1. schema 显式值
    explicit = _infer_sheet_type_from_schema(sheet_schema, full_schema)
    if explicit:
        return explicit
    # 2. 注册表（D1/D2 试点标注）
    registry_value = _infer_sheet_type_from_registry(sheet_name)
    if registry_value:
        return registry_value
    # 3. 启发式
    heuristic = _infer_sheet_type_by_heuristic(sheet_name)
    if heuristic:
        return heuristic
    # 4. 无法确定
    return None


def _extract_field_sources(sheet_schema: dict | None, full_schema: dict | None, sheet_name: str = "") -> dict:
    """从 schema YAML 或 registry 中提取 field_sources 配置。

    优先级: per-sheet schema > full schema > registry。

    Returns:
        字段来源配置 dict，或空 {}（schema 未配置）。
    """
    # per-sheet schema 中有 field_sources
    if isinstance(sheet_schema, dict) and isinstance(sheet_schema.get("field_sources"), dict):
        return sheet_schema["field_sources"]
    # 顶层 schema 有 field_sources（单 sheet yaml）
    if isinstance(full_schema, dict) and isinstance(full_schema.get("field_sources"), dict):
        return full_schema["field_sources"]
    # 注册表中查找 field_sources（Task 4.4）
    if sheet_name:
        registry = _load_semantic_registry()
        entry = registry.get(sheet_name)
        if entry and isinstance(entry, dict) and isinstance(entry.get("field_sources"), dict):
            return entry["field_sources"]
    return {}


async def _has_custom_procedure(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> bool:
    n = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.wp_code == wp_code,
                ProcedureInstance.is_custom == True,  # noqa: E712
                ProcedureInstance.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar() or 0
    return n > 0


def _looks_like_standard_wp_code(wp_code: str) -> bool:
    return _is_standard_wp_code_fn(wp_code)


async def _maybe_custom_classifications(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
    wp_name: str | None,
    classifications: list,
    working_paper: WorkingPaper,
) -> list:
    """无模板归类时，为自定义程序/自建底稿合成 CUSTOM → componentType=custom。"""
    if classifications:
        return classifications
    use_custom = await _has_custom_procedure(db, project_id, wp_code)
    if not use_custom and working_paper.source_type == WpSourceType.manual:
        use_custom = not _looks_like_standard_wp_code(wp_code)
    if not use_custom:
        return classifications
    # sheet_name 与 parsed_data.html_data 的键一致（保存时用 wp_code 作 sheet 名）
    sheet_name = wp_code
    return [
        ClassificationResult(
            wp_code=wp_code,
            sheet_name=sheet_name,
            class_code="CUSTOM",
            class_="自定义底稿",
            scope="standalone",
            is_real_workpaper=True,
            delegated_module=None,
            render_schema_path=None,
            template_version_id=None,
        )
    ]


def _unpack_sheet_schema(schema_data: dict | None, sheet_name: str) -> dict | None:
    """按 sheet 名解包 schema（前端组件读顶层 sub_tables/fields）。"""
    if not isinstance(schema_data, dict):
        return None
    nested = schema_data.get("sheets")
    if isinstance(nested, dict) and sheet_name in nested:
        per_sheet = nested[sheet_name]
        if isinstance(per_sheet, dict):
            merged = {k: v for k, v in schema_data.items() if k != "sheets"}
            merged.update(per_sheet)
            return merged
    if schema_data.get("sub_tables") or schema_data.get("fields"):
        return schema_data
    return None


def _resolve_template_path(working_paper, wp_code: str) -> str | None:
    """模板文件路径：优先 file_path，否则回退 wp_templates 库。"""
    fp = working_paper.file_path
    if fp and Path(fp).is_file():
        return fp
    try:
        from app.services.wp_template_init_service import find_template_file_any
        t = find_template_file_any(wp_code)
        return str(t) if t else fp
    except Exception:  # noqa: BLE001
        return fp
