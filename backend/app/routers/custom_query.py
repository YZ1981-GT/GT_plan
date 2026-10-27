"""自定义查询 API — 支持多维度跨模块数据查询

支持查询维度：
  - report: 报表数据（report_config）
  - trial_balance: 试算表数据（trial_balance_entries）
  - disclosure: 附注数据（consol_note_data）
  - adjustment: 调整分录（adjustments）
  - worksheet: 工作底稿数据（consol_worksheet_data）
  - workpaper: 底稿列表（working_paper）— Sprint 6 新增
  - account_balance: 科目余额（tb_balance）— Sprint 6 新增
  - ledger_entries: 序时账（tb_ledger）— Sprint 6 新增
  - report_lines: 报表行次（report_config / financial_report）— Sprint 6 新增
  - workhours: 工时记录（work_hours）— Sprint 6 新增

支持过滤：
  - project_id: 项目
  - year: 年度
  - company_code: 单位
  - report_type: 报表类型
  - account_name: 科目名
  - section_id: 附注章节

API:
  POST   /api/custom-query/execute              — 执行查询
  POST   /api/custom-query/export               — 导出全部（服务端流式，> 1,000,000 行 400）
  GET    /api/custom-query/indicators           — 获取可查询指标库（树形）
  GET    /api/custom-query/templates            — 列出查询模板（私有 + 全局）
  POST   /api/custom-query/templates            — 创建查询模板
  GET    /api/custom-query/templates/{id}       — 获取模板详情
  PUT    /api/custom-query/templates/{id}       — 更新模板
  DELETE /api/custom-query/templates/{id}       — 删除模板（仅创建者或 admin）
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, get_visible_project_ids, require_project_access
from app.models.core import Project, ProjectUser, User
from app.models.custom_query_models import CustomQueryTemplate
# 模板治理三件套在模块级 import：既是「唯一消费方」的落点，也使契约测试可对
# router 命名空间做 monkeypatch（函数内 import 会绕过替身）。
from app.services.custom_query.template_scope_adapter import (
    NormalizedTemplateScope,
    TemplateScopeAdapter,
    TemplateScopeValidationError,
)
from app.services.custom_query.template_service import template_service
from app.services.custom_query.pagination import (
    MAX_LIMIT as PAGE_MAX_LIMIT,
    MIN_LIMIT as PAGE_MIN_LIMIT,
)
# 取数器下沉（advanced-query-linkage-closure 任务 7 / 17 / 18）：SQL 源由 source_registry + paged_fetch 在数据库内
# 计数 / 排序 / 分页，JSON 内存源与底稿选区辅助在 fetchers/，本模块不再有取数器；wp-sheet-preview 的只读取数在
# fetchers/workpaper_cells（任务 16）。
from app.services.custom_query.fetchers.disclosure import _query_disclosure  # noqa: F401 — 再导出（test_note_table_payload_readers_pg）
from app.services.custom_query.fetchers.workpaper_cells import render_sheet_preview
from app.services.custom_query.source_registry import resolve_source
from app.services.custom_query.strict_model import AcnrTargetList, StrictRequestModel
from app.services.wp_template_registry import wp_template_registry_service

router = APIRouter(prefix="/api/custom-query", tags=["custom-query"])

logger = logging.getLogger(__name__)


class SortSpec(BaseModel):
    """单个排序项。

    声明为模型而非裸 dict：非法方向能在 router 层即被 pydantic 拦成 422，
    不必等进到编排器；同时前端拿到的错误定位到具体字段。
    """

    field: str = Field(..., min_length=1, max_length=100)
    direction: Literal["asc", "desc"] = "asc"


class ConditionSpec(BaseModel):
    """一条结构化条件（advanced-query-linkage-closure R6.1）。

    算子与字段的合法性由注册表在取数层判定（未登记 → 400 ``OP_NOT_ALLOWED`` / ``UNKNOWN_CONDITION_FIELD``，
    message 指明可用项），这里只限长度；值由 ``param_sql_builder`` 按列类型转换并参数化绑定。
    """

    field: str = Field(..., min_length=1, max_length=64)
    op: str = Field(..., min_length=1, max_length=32)
    value: Any | None = None


class QueryRequest(StrictRequestModel):
    project_id: str
    year: int = Field(..., ge=2000, le=2100)
    source: str  # 注册源键 / 别名 / consol_unit: / workpaper: / disclosure_note: 形态（source_registry.resolve_source）
    filters: dict = {}  # 旧筛选键：SQL 源只认注册表登记的键（未登记 → 400 UNKNOWN_FILTER_KEY）
    #: 要返回的显示列（空 = 全部；未登记 → 400 UNKNOWN_COLUMN），下钻所需键随行返回不显示
    columns: list[str] = Field(default_factory=list, max_length=60)
    #: 结构化条件（字段、算子、值）与组合逻辑：只有注册表 SQL 源支持，内存源带条件 → 400 CONDITIONS_UNSUPPORTED
    conditions: list[ConditionSpec] = Field(default_factory=list, max_length=20)
    condition_logic: Literal["and", "or"] = "and"
    # 分页边界与 pagination.MIN_LIMIT / MAX_LIMIT 保持一致（R4.6）。
    # 改造前 limit 无约束、offset 声明后全文件零使用（14 个取数器只拼 LIMIT :lim），
    # 前端却一直在传 offset ⇒ 业务视图从来没有第 2 页。
    limit: int = Field(default=500, ge=PAGE_MIN_LIMIT, le=PAGE_MAX_LIMIT)
    offset: int = Field(default=0, ge=0)
    #: 排序项：SQL 源在数据库内排序（可空列空值在后），内存源由 StablePagination 消费。非法方向在此层即 422（R4.7）。
    sort: list[SortSpec] = Field(default_factory=list, max_length=5)
    #: 分组配置 {"dimensions": [...], "aggregates": [{"field","op","alias"}]}。
    group: dict | None = None
    #: 透视配置 {"row_dims","col_dims","value_field","agg","max_cols"}。
    pivot: dict | None = None
    #: ACNR 寻址目标（addr_id / uri / report:/note:/tb: 语法糖）。
    #: 改造前该字段未被 pydantic 声明 ⇒ 前端发送后被静默丢弃、无 warning。
    acnr_targets: AcnrTargetList = Field(default_factory=list)


@router.get("/indicators")
async def get_indicators(
    project_id: str | None = Query(default=None, description="项目 ID — 传入后报表/附注树会按项目模板类型动态生成"),
    depth: int | None = Query(
        default=None,
        ge=1,
        le=9,
        description="1=仅返回骨架（重分支子节点留空并标 lazy），省略=全量（向后兼容）",
    ),
    branch: str | None = Query(
        default=None,
        description="按分支懒加载子节点（disclosure / workpaper），与 depth 配合使用",
    ),
    response: Response = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取可查询指标库（树形结构）

    响应头：
      - X-Indicators-Schema-Version：树结构版本号，前端用此值做缓存键，schema 升版自动失效
      - Cache-Control：private, max-age=0, must-revalidate（每次都校验，但允许 ETag 复用）

    传入 project_id 时：
      - 报表大类下展示项目模板类型（国企/上市）对应的具体报表
      - 附注大类下展示项目实际配置的章节（按 parent_section 分组成子大类）
    未传 project_id 时：报表/附注用通用降级树（仅显示报表类型，无国企/上市区分）

    ─── 认证与归属校验（R1.1 / R1.2 / R1.3）───────────────────────────────
    改造前本端点仅 ``Depends(get_db)``：未认证直连实测返回 200、约 700KB 响应，
    泄露项目模板类型、合并范围全部子公司名单与底稿清单。归属校验必须**先于**
    任何领域读取 —— ``_resolve_project_template_type`` / ``_build_consol_units_tree``
    / ``_build_workpaper_tree`` 都以 project_id 直接查库，放在校验之后才有意义。
    """
    if project_id:
        from app.services.custom_query.ownership_guard import ownership_guard

        await ownership_guard.assert_target_accessible(
            user=current_user, project_id=project_id, db=db
        )

    template_type = await _resolve_project_template_type(db, project_id)
    standard_label = _STANDARD_LABEL.get(template_type, "通用")

    # ─── 分支懒加载（R12.2）：只构建被展开的那一支 ────────────────────────
    # 🔴 用 isinstance 而非真值判断：本端点也被契约测试**直接调用**（不经 FastAPI
    # 依赖注入），此时未传的参数保留的是 `Query(...)` 实例而不是 None ——
    # `if branch:` 会恒为真。同理 depth 也必须按真实类型判断。
    branch_key = branch if isinstance(branch, str) and branch else None
    if branch_key:
        return await _build_indicator_branch(branch_key, db, project_id, template_type)

    # depth=1 → 骨架：重分支（附注 / 底稿）子节点留空并标 lazy。
    # 实测全量树约 578KB / 3089 节点 / 2766 叶子、慢请求监控 3391ms，其中绝大部分
    # 来自底稿树（全部 wp_code × 全部 sheet）与附注树（全部章节）。
    # depth 省略时仍返回全量 —— 未改造的调用方行为不变（R12 为 opt-in）。
    skeleton = isinstance(depth, int) and depth <= 1

    # ─── 报表树：项目模板类型决定大类标签 + 报表清单 ───────────────
    # 6 张报表：BS / IS / CFS / CFS-补充资料 / 权益变动 / 减值准备表
    # 减值准备表 (impairment_provision) 仅 soe 模板有数据，listed 自动隐藏避免误点
    report_columns = _registry_columns("report")
    report_children = [
        {"key": "report_balance_sheet", "label": f"资产负债表（{standard_label}）", "columns": report_columns, "standard": template_type},
        {"key": "report_income_statement", "label": f"利润表（{standard_label}）", "columns": report_columns, "standard": template_type},
        {"key": "report_cash_flow_statement", "label": f"现金流量表（{standard_label}）", "columns": report_columns, "standard": template_type},
        {"key": "report_cash_flow_supplement", "label": f"现金流量表补充资料（{standard_label}）", "columns": report_columns, "standard": template_type},
        {"key": "report_equity_statement", "label": f"所有者权益变动表（{standard_label}）", "columns": report_columns, "standard": template_type},
    ]
    if template_type == "soe":
        report_children.append(
            {"key": "report_impairment_provision", "label": f"减值准备表（{standard_label}）", "columns": report_columns, "standard": template_type}
        )

    # ─── 附注树：按 parent_section 分组成大类→明细两层 ─────────────
    disclosure_children = [] if skeleton else await _build_disclosure_tree(template_type)

    # ─── 合并范围单位树（仅合并项目可见）────────────────────────
    consol_units_node = await _build_consol_units_tree(db, project_id)

    base_tree: list[dict] = []
    base_tree.append({
        "key": "report",
        "label": f"📊 报表（{standard_label}）" if project_id else "📊 报表",
        "icon": "📊",
        "domain": "report",
        "children": report_children,
    })
    base_tree.append({
        "key": "trial_balance", "label": "📑 试算平衡表", "icon": "📑",
        "domain": "tb",
        "children": [
            {"key": "tb_detail", "label": "科目明细", "columns": _registry_columns("tb_detail")},
            {"key": "tb_summary", "label": "试算平衡表", "columns": ["row_code", "row_name", "unadjusted", "aje_dr", "aje_cr", "rcl_dr", "rcl_cr", "audited"]},
            {"key": "account_balance", "label": "科目余额表", "columns": _registry_columns("account_balance")},
            {"key": "ledger_entries", "label": "序时账明细", "columns": _registry_columns("ledger_entries")},
        ],
    })
    base_tree.append({
        "key": "disclosure",
        "label": f"📝 附注（{standard_label}）" if project_id else "📝 附注",
        "icon": "📝",
        "domain": "note",
        "children": disclosure_children,
        "lazy": skeleton,
    })
    # 合并范围节点：仅合并项目（report_scope=consolidated 且至少 1 家纳入单位）展示
    if consol_units_node:
        base_tree.append(consol_units_node)
    base_tree.append({
        "key": "adjustment", "label": "📐 调整分录", "icon": "📐",
        "domain": "wp",
        "children": [
            {"key": "adj_aje", "label": "审计调整分录(AJE)", "columns": _registry_columns("adj_aje")},
            {"key": "adj_rcl", "label": "重分类调整(RCL)", "columns": _registry_columns("adj_rcl")},
        ],
    })
    base_tree.append({
        "key": "worksheet", "label": "📑 工作底稿", "icon": "📑",
        "domain": "wp",
        "children": [
            {"key": "ws_info", "label": "基本信息表", "columns": ["company_name", "company_code", "holding_type", "non_common_ratio"]},
            {"key": "ws_elimination", "label": "抵消分录", "columns": ["direction", "subject", "amount", "desc"]},
            {"key": "ws_consol_tb", "label": "合并试算平衡表", "columns": ["row_code", "row_name", "summary", "equity_dr", "equity_cr", "audited"]},
        ],
    })
    base_tree.append({
        "key": "workpaper", "label": "📋 底稿", "icon": "📋",
        "domain": "wp",
        "children": [] if skeleton else await _build_workpaper_tree(db, project_id),
        "lazy": skeleton,
    })
    base_tree.append({
        "key": "report_lines", "label": "📈 报表行次", "icon": "📈",
        "domain": "report",
        "children": [
            {"key": "report_lines", "label": "报表行次配置", "columns": _registry_columns("report_lines")},
        ],
    })
    base_tree.append({
        "key": "workhours", "label": "⏱️ 工时记录", "icon": "⏱️",
        "domain": "aux",
        "children": [
            {"key": "workhours", "label": "工时记录", "columns": _registry_columns("workhours")},
        ],
    })
    if response is not None:
        # version = max(static schema version, DB registry max version)
        try:
            db_max_version = await wp_template_registry_service.get_max_version(db)
            effective_version = max(_INDICATORS_SCHEMA_VERSION, db_max_version)
        except Exception:
            effective_version = _INDICATORS_SCHEMA_VERSION
        response.headers["X-Indicators-Schema-Version"] = str(effective_version)
        response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    return base_tree


# ─── 辅助函数：项目模板类型解析 + 附注树构建 ───────────────────────────────

_STANDARD_LABEL = {"soe": "国企", "listed": "上市"}
# indicators 树结构 schema 版本：树字段/叶子 key 形态有变更时升 1，前端用此值自动失效旧缓存
# 历史演进：v1 扁平 → v2 项目级 → v3 6 报表 → v4 合并模块 → v5 底稿 3 层 → v6 sheet 全集 → v7 disabled → v8 sheet 辅助灰度 + ancestorKeys → v9 wp_template_registry DB
# v10：节点新增 `lazy` 字段 + 支持 depth/branch 懒加载（R12），旧缓存需失效
# v11：注册表 SQL 源的叶子 columns 由 source_registry 生成（advanced-query-linkage-closure 任务 7）——
#      execute 起对未登记列返回 400 UNKNOWN_COLUMN，旧缓存里「科目明细」的 account_code / closing_balance 等
#      试算表没有的列必须失效
# v12：报表、报表行次、调整分录（含合并单位）切到注册表，叶子 columns 同样由它生成（任务 17 / 18：调整分录旧叶子声明
#      表里没有的 entry_number，页面版按叶子列发 columns 会 400）；同批任务 22 的试算表重分类列、余额方向列共用 v12
_INDICATORS_SCHEMA_VERSION = 12


def _registry_columns(source: str) -> list[str]:
    """指标树叶子声明的列 = 注册表显示列（同一定义生成，R5.7；只用于注册表 SQL 源的叶子）。"""
    spec = resolve_source(source).spec
    assert spec is not None, f"指标树叶子 {source} 不是注册表 SQL 源"
    return list(spec.display_keys)

#: 支持按分支懒加载的大类 key → 子节点构建器名（见 _build_indicator_branch）
LAZY_INDICATOR_BRANCHES: tuple[str, ...] = ("disclosure", "workpaper")


async def _build_indicator_branch(
    branch: str, db: AsyncSession, project_id: str | None, template_type: str
) -> list[dict]:
    """按分支返回子节点（R12.2）。

    未登记的分支显式 400 而非返回空数组 —— 静默空会让前端展开后看到「没有内容」，
    分不清是「真没有」还是「参数写错了」。
    """
    if branch == "disclosure":
        return await _build_disclosure_tree(template_type)
    if branch == "workpaper":
        return await _build_workpaper_tree(db, project_id)
    raise HTTPException(
        status_code=400,
        detail={
            "error_code": "UNKNOWN_INDICATOR_BRANCH",
            "message": f"未知指标树分支 '{branch}'",
            "allowed": list(LAZY_INDICATOR_BRANCHES),
        },
    )
_DISCLOSURE_CACHE: dict[str, list[dict]] = {}
_WP_MAPPING_CACHE: list[dict] | None = None

# 14 审计循环代号 → 中文名（与 memory.md 沉淀对齐：A=报表/调整 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金 / F=采购存货 / G=投资 / H=固定资产+在建工程+使用权资产+租赁负债 / I=无形资产+商誉+开发支出 / J=职工薪酬+股份支付 / K=管理 / L=筹资 / M=股东权益 / N=税费 / S=专项程序）
_CYCLE_NAMES: dict[str, str] = {
    "A": "报表/调整",
    "B": "控制了解",
    "C": "控制测试",
    "D": "销售收入",
    "E": "货币资金",
    "F": "采购存货",
    "G": "投资",
    "H": "固定资产+在建+使用权",
    "I": "无形资产+商誉",
    "J": "职工薪酬+股份支付",
    "K": "管理",
    "L": "筹资",
    "M": "股东权益",
    "N": "税费",
    "S": "专项程序",
}


async def _resolve_project_template_type(db: AsyncSession, project_id: str | None) -> str:
    """从项目读 template_type，未配置或未传 project_id 则降级为 'soe'"""
    if not project_id:
        return "soe"
    try:
        proj_uuid = uuid.UUID(project_id)
    except (TypeError, ValueError):
        return "soe"
    proj = await db.get(Project, proj_uuid)
    if proj and proj.template_type in _STANDARD_LABEL:
        return proj.template_type
    return "soe"


async def _resolve_project_report_scope(db: AsyncSession, project_id: str | None) -> str:
    """从项目读 report_scope（standalone / consolidated），默认 standalone"""
    if not project_id:
        return "standalone"
    try:
        proj_uuid = uuid.UUID(project_id)
    except (TypeError, ValueError):
        return "standalone"
    proj = await db.get(Project, proj_uuid)
    if proj and proj.report_scope in ("standalone", "consolidated"):
        return proj.report_scope
    return "standalone"


async def _build_consol_units_tree(db: AsyncSession, project_id: str | None) -> dict | None:
    """合并项目下生成「合并范围」顶层节点，children 是每家纳入合并的单位。

    判定 = report_scope=consolidated **或** consol_scope 表已有数据（向导未走完时兜底）
    每家单位下挂 4 个明细：科目余额 / 序时账 / 试算表（个体） / 调整分录（按 company_code）
    返回 None 表示当前项目非合并 / 无单位 / 无 project_id（不渲染该节点）
    """
    if not project_id:
        return None
    try:
        proj_uuid = uuid.UUID(project_id)
    except (TypeError, ValueError):
        return None
    # 取最新年度的纳入合并单位（按 ownership_ratio 排序）
    sql = text("""
        SELECT DISTINCT ON (company_code) company_code, company_name, company_type, ownership_ratio
        FROM consol_scope
        WHERE project_id = :pid AND is_included = true AND is_deleted = false
        ORDER BY company_code, year DESC
    """)
    try:
        rows = (await db.execute(sql, {"pid": str(proj_uuid)})).fetchall()
    except Exception:
        return None
    if not rows:
        # 兜底：若 consol_scope 无数据但 project.report_scope=consolidated，仍提示「待录入」节点
        scope = await _resolve_project_report_scope(db, project_id)
        if scope == "consolidated":
            return {
                "key": "consol_units",
                "label": "🏢 合并范围（待录入）",
                "icon": "🏢",
                "children": [
                    {"key": "consol_units_empty", "label": "⚠ 尚未配置纳入合并的单位"},
                ],
            }
        return None
    units: list[dict] = []
    for r in rows:
        cc = r[0]
        cname = r[1] or cc
        ctype = r[2] or ""
        ratio = float(r[3]) if r[3] is not None else None
        ratio_label = f" {ratio:.2f}%" if ratio is not None else ""
        type_label = {"parent": "母", "subsidiary": "子", "associate": "联", "joint_venture": "合营"}.get(str(ctype), "")
        unit_label = f"[{type_label}] {cname}{ratio_label}".strip()
        units.append({
            "key": f"consol_unit_group_{cc}",
            "label": unit_label,
            "company_code": cc,
            "children": [
                {"key": f"consol_unit:{cc}:account_balance", "label": "科目余额", "columns": _registry_columns("account_balance"), "company_code": cc},
                {"key": f"consol_unit:{cc}:ledger_entries", "label": "序时账明细", "columns": _registry_columns("ledger_entries"), "company_code": cc},
                {"key": f"consol_unit:{cc}:tb_detail", "label": "试算表（个体）", "columns": _registry_columns("tb_detail"), "company_code": cc},
                {"key": f"consol_unit:{cc}:adjustment", "label": "调整分录", "columns": _registry_columns("adjustment"), "company_code": cc},
            ],
        })
    return {
        "key": "consol_units",
        "label": f"🏢 合并范围（{len(units)}家）",
        "icon": "🏢",
        "children": units,
    }


async def _build_disclosure_tree(template_type: str) -> list[dict]:
    """读 consol_note_sections_{template_type}.json，按 parent_section 分组成两层树。

    返回结构：
      [
        { key: 'note_group_货币资金', label: '货币资金', children: [
            { key: 'disclosure_note:五-1-1', label: '五-1-1 货币资金', section_id: '五-1-1' },
            { key: 'disclosure_note:五-1-2', label: '五-1-2 受限制货币资金明细', section_id: '五-1-2' },
        ] },
        ...
      ]
    """
    sections = _load_disclosure_sections(template_type)
    if not sections:
        # 降级：未读到 JSON 时返回单一通用入口
        return [{"key": "disclosure_note", "label": "附注章节数据（通用）", "columns": ["section_id", "headers", "rows"]}]

    # 按 parent_section 分组（按 parent_seq 排序）
    groups: dict[str, dict] = {}
    for sec in sections:
        parent = sec.get("parent_section") or sec.get("title") or "其他"
        parent_seq = sec.get("parent_seq", 999)
        if parent not in groups:
            groups[parent] = {
                "key": f"note_group_{parent}",
                "label": parent,
                "_seq": parent_seq,
                "children": [],
            }
        section_id = sec.get("section_id", "")
        title = sec.get("title", "")
        groups[parent]["children"].append({
            "key": f"disclosure_note:{section_id}",
            "label": f"{section_id} {title}".strip(),
            "section_id": section_id,
            "columns": ["section_id", "headers", "rows"],
            "_seq": sec.get("seq", 999),
        })

    # 按 parent_seq 排序大类，按 seq 排序明细
    sorted_groups = sorted(groups.values(), key=lambda g: g["_seq"])
    for g in sorted_groups:
        g["children"].sort(key=lambda c: c["_seq"])
        for c in g["children"]:
            c.pop("_seq", None)
        g.pop("_seq", None)
    return sorted_groups


def _load_disclosure_sections(template_type: str) -> list[dict]:
    """读 backend/data/consol_note_sections_{template_type}.json（带模块级缓存）。

    自动将 multi_header 转换为 _column_groups。
    """
    if template_type in _DISCLOSURE_CACHE:
        return _DISCLOSURE_CACHE[template_type]
    data_path = Path(__file__).resolve().parent.parent.parent / "data" / f"consol_note_sections_{template_type}.json"
    if not data_path.exists():
        _DISCLOSURE_CACHE[template_type] = []
        return []
    try:
        with data_path.open("r", encoding="utf-8") as f:
            sections = json.load(f)
        sections = sections if isinstance(sections, list) else []
        # 补齐 _column_groups + columns + _row_types
        from app.services.consol_note_formula_service import (
            multi_header_to_column_groups,
            _ensure_columns,
            _ensure_row_types,
        )

        for section in sections:
            if not isinstance(section, dict):
                continue
            if not section.get("_column_groups"):
                mh = section.get("multi_header")
                if mh:
                    groups = multi_header_to_column_groups(mh)
                    if groups:
                        section["_column_groups"] = groups
            _ensure_columns(section)
            _ensure_row_types(section)
        _DISCLOSURE_CACHE[template_type] = sections
    except Exception:
        _DISCLOSURE_CACHE[template_type] = []
    return _DISCLOSURE_CACHE[template_type]


def _load_wp_mapping() -> list[dict]:
    """读 backend/data/wp_account_mapping.json（带模块级缓存）"""
    global _WP_MAPPING_CACHE
    if _WP_MAPPING_CACHE is not None:
        return _WP_MAPPING_CACHE
    data_path = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
    if not data_path.exists():
        _WP_MAPPING_CACHE = []
        return []
    try:
        with data_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _WP_MAPPING_CACHE = data.get("mappings", []) or []
        elif isinstance(data, list):
            _WP_MAPPING_CACHE = data
        else:
            _WP_MAPPING_CACHE = []
    except Exception:
        _WP_MAPPING_CACHE = []
    return _WP_MAPPING_CACHE


_STEP_SHEET_CACHE: dict[str, dict] | None = None
# wp_code → 真实模板 xlsx 的 sheet 列表（启动后惰性扫描，缺失则降级为 step_sheet_mapping）
_REAL_SHEETS_CACHE: dict[str, list[str]] = {}

# sheet 灰度判定：辅助 sheet 关键词（与 chain_orchestrator scenarioFilter 对齐）
# 业务规则：模板里这些 sheet 是给审计师参考的辅助资料，不参与正式数据填报，查询无意义
_AUX_SHEET_KEYWORDS = ("(修订前)", "（修订前）", "(示例)", "（示例）", "(提示)", "（提示）", "-修订前", "GT_Custom")


def _is_aux_sheet(sheet_name: str) -> bool:
    """判断 sheet 名是否为辅助 sheet（应灰显）"""
    if not sheet_name:
        return False
    return any(kw in sheet_name for kw in _AUX_SHEET_KEYWORDS)


def _load_step_sheet_mapping() -> dict[str, dict]:
    """读 backend/data/step_sheet_mapping.json — 全集 wp_code → {wp_name, available_sheets[]}

    覆盖率 100% (179 底稿 / 1040 sheet)，是底稿全 sheet 列表的权威源。
    首次加载时与 wp_account_mapping.json 主底稿做漂移检测，差异写 logger.warning（提醒维护对齐）。
    """
    global _STEP_SHEET_CACHE
    if _STEP_SHEET_CACHE is not None:
        return _STEP_SHEET_CACHE
    data_path = Path(__file__).resolve().parent.parent.parent / "data" / "step_sheet_mapping.json"
    if not data_path.exists():
        _STEP_SHEET_CACHE = {}
        return {}
    try:
        with data_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        _STEP_SHEET_CACHE = data.get("mappings", {}) if isinstance(data, dict) else {}
    except Exception:
        _STEP_SHEET_CACHE = {}

    # 双源漂移检测（首次加载时执行一次）
    # 注意：两个文件设计目的不同，部分 wp_code 单边出现是合理的：
    # - 程序文档型底稿（如 B22 控制环境/S33 程序修订）只在 step_sheet_mapping
    # - 纯账户审定型底稿（如 K14-K18 各类收益审定表）只在 wp_account_mapping
    # 因此 drift 信息记 DEBUG（开发参考），不再 WARNING 刷屏
    try:
        wp_codes_step = {c for c in _STEP_SHEET_CACHE.keys() if "-" not in c}
        wp_codes_acc = {m.get("wp_code") for m in _load_wp_mapping() if m.get("wp_code") and "-" not in m.get("wp_code", "")}
        only_in_step = wp_codes_step - wp_codes_acc
        only_in_acc = wp_codes_acc - wp_codes_step
        if only_in_step or only_in_acc:
            logger.debug(
                "wp mapping double-source drift (expected for doc-only/account-only codes): "
                "step_sheet has %d codes not in wp_account (%s...), "
                "wp_account has %d codes not in step_sheet (%s...).",
                len(only_in_step), sorted(list(only_in_step))[:5],
                len(only_in_acc), sorted(list(only_in_acc))[:5],
            )
    except Exception as e:
        logger.debug("drift detection skipped: %s", e)
    return _STEP_SHEET_CACHE


async def _build_workpaper_tree(db: AsyncSession, project_id: str | None) -> list[dict]:
    """底稿树：循环 → 主底稿（科目名）→ sheet 程序明细。

    - 优先从 wp_template_registry 表读取（Req 4），降级到 JSON 文件
    - 传入 project_id 时，从 wp_index 取该项目实际有的 wp_code 集合（裁剪后），
      不在集合里的节点标 disabled=true 灰显不可选；
      项目实际有但全集没的（罕见）补充到全集末尾
    """
    # 优先从 DB 读取
    registry_data: list[dict] | None = None
    try:
        if await wp_template_registry_service.table_exists(db):
            registry_data = await wp_template_registry_service.load_tree(db)
            if not registry_data:
                registry_data = None
    except Exception as e:
        logger.debug("wp_template_registry read failed, fallback to JSON: %s", e)
        registry_data = None

    if registry_data:
        # Build from DB registry
        map_by_code: dict[str, dict] = {r["wp_code"]: r for r in registry_data}
        primaries: list[dict] = []
        for r in registry_data:
            sheets_list = r.get("sheets") or []
            sheet_names = [s["name"] if isinstance(s, dict) else s for s in sheets_list]
            primaries.append({
                "wp_code": r["wp_code"],
                "wp_name": r["wp_name"],
                "cycle": r["cycle"],
                "account_name": "",
                "sheets": sheet_names,
            })
    else:
        # Fallback to JSON files
        mapping = _load_wp_mapping()
        sheet_map = _load_step_sheet_mapping()
        map_by_code = {m.get("wp_code", ""): m for m in mapping if m.get("wp_code")}

        primaries = []
        seen: set[str] = set()
        for m in mapping:
            code = m.get("wp_code", "")
            if not code or "-" in code or code in seen:
                continue
            seen.add(code)
            primaries.append({
                "wp_code": code,
                "wp_name": m.get("wp_name", ""),
                "cycle": m.get("cycle") or (code[:1] if code else ""),
                "account_name": m.get("account_name") or "",
                "sheets": sheet_map.get(code, {}).get("available_sheets") or [],
            })
        for code, info in sheet_map.items():
            if "-" in code or code in seen:
                continue
            seen.add(code)
            primaries.append({
                "wp_code": code,
                "wp_name": info.get("wp_name", ""),
                "cycle": code[:1] if code else "",
                "account_name": "",
                "sheets": info.get("available_sheets") or [],
            })

    # 项目级实际有的 wp_code 集合（用于判定 disabled）
    available_codes: set[str] | None = None
    if project_id:
        try:
            proj_uuid = uuid.UUID(project_id)
            sql = text("""
                SELECT wp_code FROM wp_index
                WHERE project_id = :pid AND is_deleted = false
            """)
            rows = (await db.execute(sql, {"pid": str(proj_uuid)})).fetchall()
            available_codes = {r[0] for r in rows if r[0]}
        except (TypeError, ValueError):
            available_codes = None

    # 按 cycle 分组
    cycle_groups: dict[str, list[dict]] = {}
    for p in primaries:
        cy = (p["cycle"] or "").upper() or "其他"
        cycle_groups.setdefault(cy, []).append(p)

    def _cycle_sort_key(cy: str) -> tuple:
        order = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "S"]
        return (order.index(cy) if cy in order else 99, cy)

    def _is_disabled(code: str) -> bool:
        """传 project_id 时，wp_code 不在 available_codes 即灰显"""
        if available_codes is None:
            return False
        return code not in available_codes

    result: list[dict] = []
    for cy in sorted(cycle_groups.keys(), key=_cycle_sort_key):
        primary_list = sorted(cycle_groups[cy], key=lambda x: x["wp_code"])
        primary_nodes: list[dict] = []
        cycle_active_count = 0
        for p in primary_list:
            code = p["wp_code"]
            acc = p.get("account_name") or ""
            wpname = p.get("wp_name") or ""
            primary_label = f"{code} {acc or wpname}".strip()
            primary_disabled = _is_disabled(code)
            if not primary_disabled:
                cycle_active_count += 1
            sheets = p.get("sheets") or []
            children_nodes: list[dict] = []
            children_nodes.append({
                "key": f"workpaper:{code}",
                "label": f"{code}（汇总）",
                "wp_code": code,
                "disabled": primary_disabled,
                "columns": ["wp_code", "wp_name", "audit_cycle", "status", "review_status"],
                "columns_source": "metadata",
            })
            for s_name in sheets:
                sheet_aux = _is_aux_sheet(s_name)
                children_nodes.append({
                    "key": f"workpaper:{code}|{s_name}",
                    "label": s_name,
                    "wp_code": code,
                    "sheet_name": s_name,
                    "disabled": primary_disabled or sheet_aux,
                    "disabled_reason": "辅助 sheet" if sheet_aux and not primary_disabled else None,
                    "columns": None,
                    "columns_source": "dynamic_from_data",
                })
            primary_nodes.append({
                "key": f"wp_primary_{code}",
                "label": f"{primary_label}（{len(sheets)}）",
                "disabled": primary_disabled,
                "children": children_nodes,
            })
        # 循环节点 label 显示 "活跃数/总数"（项目模式）或 "总数"（全集模式）
        if available_codes is not None:
            cycle_label = f"{cy} {_CYCLE_NAMES.get(cy, '')}".strip() + f"（{cycle_active_count}/{len(primary_list)}）"
        else:
            cycle_label = f"{cy} {_CYCLE_NAMES.get(cy, '')}".strip() + f"（{len(primary_list)}）"
        # 整个循环全部灰则循环本身也 disabled
        cycle_all_disabled = available_codes is not None and cycle_active_count == 0
        result.append({
            "key": f"wp_cycle_{cy}",
            "label": cycle_label,
            "disabled": cycle_all_disabled,
            "children": primary_nodes,
        })
    return result


@router.get("/wp-id-by-code")
async def wp_id_by_code(
    project_id: str = Query(..., description="项目 ID"),
    wp_code: str = Query(..., description="底稿编码（如 D2）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """wp_code → working_paper.id 映射（供前端穿透跳转 WorkpaperEditor 用）

    改造前本端点无认证：匿名枚举 project_id 即可确认底稿存在性并取得 wp_id（R1.1）。
    """
    try:
        proj_uuid = uuid.UUID(project_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid project_id")

    from app.services.custom_query.ownership_guard import ownership_guard

    await ownership_guard.assert_target_accessible(
        user=current_user, project_id=str(proj_uuid), db=db
    )
    row = (await db.execute(text("""
        SELECT w.id FROM working_paper w
        JOIN wp_index i ON w.wp_index_id = i.id
        WHERE i.project_id = :pid AND i.wp_code = :wpc AND w.is_deleted = false
        LIMIT 1
    """), {"pid": str(proj_uuid), "wpc": wp_code})).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"底稿 {wp_code} 在当前项目不存在")
    return {"wp_id": str(row[0]), "wp_code": wp_code, "project_id": project_id}


@router.get("/wp-sheet-preview")
async def wp_sheet_preview(
    project_id: str = Query(..., description="项目 ID"),
    wp_code: str = Query(..., description="底稿编码（如 D2）"),
    sheet_name: str | None = Query(None, description="目标 sheet 名称（缺省返回首个 sheet）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """高级查询 sheet 选区器专用端点：返回 cellData 用于网格预览（只读，R4.4）。

    数据源优先级：
      1. `working_paper.parsed_data['univer_snapshot']` — 用户保存底稿时已落库（首选，零计算）
      2. storage xlsx → openpyxl 解析缓存值；没有文件返回 `available: false`，不从模板生成
    """
    try:
        proj_uuid = uuid.UUID(project_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid project_id")

    # ─── 认证 + 归属校验（R1.1 / R1.2 / R1.4）─────────────────────────────
    # 本端点直接返回底稿单元格值（含公式），改造前无任何认证 —— 实测未认证直连
    # 返回 200。改造前下方降级分支还会从模板生成文件（写 storage，AQ-23，任务 16 已改为只读）；
    # 守卫仍须在此、先于一切读取。
    from app.services.custom_query.ownership_guard import ownership_guard

    await ownership_guard.assert_target_accessible(
        user=current_user, project_id=str(proj_uuid), db=db
    )

    # 1. wp_id + parsed_data 一次查询
    row = (await db.execute(text("""
        SELECT w.id, w.parsed_data FROM working_paper w
        JOIN wp_index i ON w.wp_index_id = i.id
        WHERE i.project_id = :pid AND i.wp_code = :wpc AND w.is_deleted = false
        LIMIT 1
    """), {"pid": str(proj_uuid), "wpc": wp_code})).first()
    if not row:
        return {"available": False, "reason": "底稿在当前项目中不存在", "wp_code": wp_code}

    # 2. 预览只读（R4.4）：snapshot 优先、其次 storage xlsx 缓存值；没有文件不从模板生成（fetchers/workpaper_cells）
    parsed_data = row[1] if isinstance(row[1], dict) else {}
    return await render_sheet_preview(proj_uuid, row[0], wp_code, parsed_data, sheet_name)


@router.post("/execute")
async def execute_query(
    body: QueryRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行自定义查询 —— 经 ExecuteCompatibilityAdapter 的唯一执行路径。

    改造前此处是 14 条内联 ``if/elif`` 直接分发取数器，`ExecuteCompatibilityAdapter`
    与 `QueryOrchestrator` 因此被完整绕过（router 引用数 0）。现在：

    - 归属校验、寻址、缓存、分组、透视、分页统一由编排器 step1~step8 负责；
    - router 只保留 HTTP 层职责：降级响应头、缓存命中头、审计、错误映射；
    - 异常分类明确 —— ``HTTPException`` 原样上抛保留状态码；其余回滚并转 500 带
      correlation_id。改造前的 ``except Exception`` 把超时/中断/列不存在全吞成
      ``200 {"rows": [], "error": ...}``，失败在前端表现为「查不到数据」。

    _Requirements: 3.1, 3.2, 3.7, 5.1, 5.2, 5.3_
    """
    # ─── GIN index degradation: add header when index is building ────────
    from app.services.gin_index_monitor import is_index_building
    if is_index_building():
        response.headers["X-Index-Status"] = "building"

    from app.services.custom_query.audit_helper import record_query_rejected
    from app.services.custom_query.business_fetchers import business_fetcher
    from app.services.custom_query.execute_compatibility import (
        ExecuteCompatibilityAdapter,
    )

    source = body.source
    pid = body.project_id
    year = body.year
    filters = body.filters

    adapter = ExecuteCompatibilityAdapter(business_fetcher=business_fetcher)
    try:
        result = await adapter.execute(body, user=current_user, db=db)
    except HTTPException as http_exc:
        # 领域 4xx（FORBIDDEN_PROJECT / TARGET_UNRESOLVABLE / UNKNOWN_SOURCE /
        # INVALID_SORT_FIELD …）原样上抛：不 rollback（编排链只读，无脏事务），
        # 也不降级为 2xx。
        # 超时 / 预算超限 / PII 越权额外记一条可区分审计（R5.5）——
        # record_query_rejected 内部吞异常，审计失败不会掩盖这里的原始错误。
        detail = http_exc.detail if isinstance(http_exc.detail, dict) else {}
        await record_query_rejected(
            user_id=current_user.id,
            error_code=detail.get("error_code"),
            source=source,
            project_id=pid,
            details={"status_code": http_exc.status_code},
        )
        raise
    except Exception:
        correlation_id = uuid.uuid4().hex
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception(
            "custom_query execute 失败 [correlation_id=%s source=%s project=%s]",
            correlation_id, source, pid,
        )
        # 追踪号同时进响应头：异常响应体可能被网关/前端拦截改写，响应头是用户能
        # 稳定复制给支持人员的那一份。
        response.headers["X-Correlation-ID"] = correlation_id
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": "查询执行失败，请稍后重试；如持续失败请提供追踪号联系管理员",
                "correlation_id": correlation_id,
            },
        )

    if result.get("cache_hit"):
        response.headers["X-Cache"] = "HIT"

    # 原「触达取数硬上限」warning 已删（advanced-query-linkage-closure 任务 7）：它拿本页行数比 5,000，
    # 永不触发；现在 SQL 源的 total 来自数据库 COUNT，内存源超过上限直接 400，不再返回截断结果。

    # 审计日志（关键路径：底稿/合并/附注/调整 写日志，普通试算/报表/工时跳过避免噪声）
    # 查询执行按 60s 窗口节流为 1 条（advanced-query-module R14.4，audit_helper 单点接线）
    _SENSITIVE_PREFIXES = ("workpaper:", "consol_unit:", "disclosure_note:", "adj_", "disclosure")
    if source.startswith(_SENSITIVE_PREFIXES) or source in ("workpaper", "adjustment", "disclosure"):
        try:
            from app.core.redis import get_redis
            from app.services.custom_query.audit_helper import record_query_execution

            redis = await get_redis()
            await record_query_execution(
                redis=redis,
                user_id=current_user.id,
                source=source,
                filters=filters,
                project_id=pid,
                action="custom_query.execute",
                details={
                    "source": source,
                    "year": year,
                    "filters": {k: v for k, v in filters.items() if not isinstance(v, (dict, list)) or len(str(v)) < 200},
                    "row_count": result.get("total", 0),
                    "has_error": "error" in result,
                },
            )
        except Exception as audit_e:
            logger.warning("audit_log enqueue failed for custom_query: %s", audit_e)

    return result


class QueryExportRequest(QueryRequest):
    """「导出全部」请求（advanced-query-linkage-closure R8.1）：查询同 execute（``limit`` / ``offset`` 不参与导出），另带
    界面所见列名 ``headers``（键为列键；标签真源是前端 queryColumnLabels）与下载文件名。"""

    headers: dict[str, str] = Field(default_factory=dict, max_length=200)
    file_name: str | None = Field(default=None, max_length=200)


@router.post("/export")
async def export_query(
    body: QueryExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务视图「导出全部」：按当前查询（条件、列、排序）服务端流式导出全量结果（R8，ADR-AQL-14，design §3.5）。

    项目归属在本函数体内直接校验（端点鉴权基线按函数体识别项目级判定，第 4 轮评审 #5）；解析校验与 execute 相同，分组 400、
    导出闸 429、COUNT 预检 400、首块预取与审计在 ``services/custom_query/query_export``。
    """
    from app.services.custom_query.ownership_guard import ownership_guard
    from app.services.custom_query.query_export import export_business_query

    await ownership_guard.assert_target_accessible(user=current_user, project_id=body.project_id, db=db)
    return await export_business_query(body, user=current_user, db=db)


async def _legacy_business_fetcher(req, resolved, db):
    """编排器 ``business_fetcher`` 的 router 侧入口（R3.7 / R4.8）。

    实现委托 ``services.custom_query.business_fetchers.business_fetcher``，不构成第二条分派路径；返回
    ``FetchPage``（注册表 SQL 源 / JSON 内存源）或 ``(rows, columns)``（跨模块单元格源，任务 34 删除）。
    """
    from app.services.custom_query.business_fetchers import business_fetcher

    return await business_fetcher(req, resolved, db)


# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.6 — 自定义查询模板 CRUD 端点
# ──────────────────────────────────────────────────────────────────────────


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    data_source: str = Field(..., min_length=1, max_length=50)
    config: dict
    # legacy `global` / `personal` 仍接受为输入，输出恒为 canonical（R8.1）
    scope: Literal["private", "team", "project", "public", "global", "personal"] = "private"
    shared_project_ids: list[str] = Field(default_factory=list)


class TemplateUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    data_source: str | None = None
    config: dict | None = None
    scope: Literal["private", "team", "project", "public", "global", "personal"] | None = None
    shared_project_ids: list[str] | None = None


class TemplateExecuteRequest(BaseModel):
    """模板执行请求：只带目标项目，其余查询参数取自模板 config。"""

    project_id: str


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str | None
    data_source: str
    config: dict
    scope: str
    created_by: str
    is_owner: bool
    created_at: str
    updated_at: str


def _serialize_template(tpl: CustomQueryTemplate, current_user_id: uuid.UUID) -> dict:
    # scope 经 TemplateScopeAdapter 归一后对外呈现：legacy `global` / `personal`
    # 只作为**输入**接受，输出恒为 canonical（`public` / `private`），前端因此不必
    # 各自维护一份别名表（R8.1）。
    config = tpl.config or {}
    normalized = TemplateScopeAdapter.normalize_record(
        tpl.scope,
        getattr(tpl, "shared_project_ids", None),
        config_project_id=config.get("project_id") if isinstance(config, dict) else None,
    )
    owner_id = getattr(tpl, "creator_id", None) or tpl.created_by
    return {
        "id": str(tpl.id),
        "name": tpl.name,
        "description": tpl.description,
        "data_source": tpl.data_source,
        "config": config,
        "scope": normalized.scope,
        "shared_project_ids": [str(pid) for pid in normalized.shared_project_ids],
        "created_by": str(tpl.created_by),
        "is_owner": owner_id == current_user_id,
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
    }


# ── 依赖可 patch 符号的授权 helper 留在本模块 ──────────────────────────────
# 契约测试 monkeypatch 的是本模块命名空间里的 get_visible_project_ids /
# require_project_access；helper 若搬到别的模块会读那边的全局名、替身失效。
async def _assert_template_scope_edit(
    normalized: "NormalizedTemplateScope",
    *,
    current_user: Any,
    db: Any,
) -> None:
    """对分享目标**逐个**鉴权（R8.3）。

    顺序按 UUID 文本升序（``TemplateScopeAdapter`` 已排序），使鉴权与落库顺序一致、
    失败定位稳定。改造前分享列表整体不鉴权 —— 用户可把模板分享给无权项目。
    """
    for project_id in normalized.shared_project_ids:
        dependency = require_project_access("edit")
        # 传 UUID 原值而非字符串：依赖内部按 UUID 比对可访问集合，字符串会恒不命中。
        await dependency(
            project_id=project_id, current_user=current_user, db=db
        )


async def _assert_writeback_authorized(
    *,
    body: Any,
    db: AsyncSession,
    current_user: Any,
    operation: str,
) -> None:
    """回写类端点的统一准入（R9.2 / R9.3 / R9.4）。

    校验顺序固定，且每一步都必须在**触达 preview/snapshot 服务之前**完成：

    1. 项目可见性 —— 不可见即 403，此时尚未查权限表（无权用户不该触发额外查询）；
    2. 编辑权限 —— 只读成员 403（``readonly`` / ``view`` 等非 ``edit`` 级别）；
    3. 逐目标项目归属 —— 多目标中任一不可访问即整体 403，**不产生部分写入**。

    第 3 步是「全有或全无」的落点：改造前 cell-writeback 只校验请求体顶层的
    project_id，targets 里携带的其它 project_id 从不校验。
    """
    project_uuid = uuid.UUID(str(body.project_id))

    # ① 项目可见性
    visible_ids = await get_visible_project_ids(current_user, db)
    if project_uuid not in visible_ids:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "PROJECT_NOT_VISIBLE",
                "message": "无权访问该项目数据",
            },
        )

    # ② 编辑权限（admin / partner 免查）
    role_value = getattr(getattr(current_user, "role", None), "value", None)
    if role_value not in ("admin", "partner"):
        pu_result = await db.execute(
            select(ProjectUser).where(
                ProjectUser.project_id == project_uuid,
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        member = pu_result.scalar_one_or_none()
        level = getattr(getattr(member, "permission_level", None), "value", None)
        if level != "edit":
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "WRITEBACK_FORBIDDEN",
                    "message": f"只读用户不可执行{operation}",
                },
            )

    # ③ 逐目标项目归属（全有或全无）
    from app.services.custom_query.ownership_guard import ownership_guard

    seen: set[str] = set()
    for target in body.targets or []:
        target_pid = (
            target.get("project_id")
            if isinstance(target, dict)
            else getattr(target, "project_id", None)
        ) or str(body.project_id)
        if target_pid in seen:
            continue
        seen.add(target_pid)
        await ownership_guard.assert_target_accessible(
            user=current_user, project_id=target_pid, db=db
        )


# ─────────────────────────────────────────────────────────────────────────────
# 已抽到伴生模块（pre-commit 行数门禁指引「优先拆分或抽伴生模块」）：
#   · 回写预览/确认端点组 → routers/custom_query_writeback.py
#   · 模板作用域治理 helper → services/custom_query/template_scope_guard.py
# 此处 re-export，保持契约测试对 router_module.writeback_preview /
# _normalize_template_scope 等的直调与 monkeypatch 不变。
# ─────────────────────────────────────────────────────────────────────────────
from app.routers.custom_query_writeback import (  # noqa: E402
    WritebackConfirmRequest,
    WritebackPreviewRequest,
    WritebackTargetSpec,
    _to_writeback_targets,
    writeback_confirm,
    writeback_preview,
)
from app.services.custom_query.template_scope_guard import (  # noqa: E402
    _assert_template_visible,
    _normalize_template_scope,
    _template_owner_id,
)

@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出可见模板：本人创建的所有 + 全局共享。

    按 updated_at 倒序排列（最近编辑置顶）。
    """
    stmt = (
        select(CustomQueryTemplate)
        .where(
            or_(
                CustomQueryTemplate.created_by == current_user.id,
                CustomQueryTemplate.scope == "global",
            )
        )
        .order_by(CustomQueryTemplate.updated_at.desc())
    )
    result = await db.execute(stmt)
    templates = result.scalars().all()
    return {
        "templates": [_serialize_template(t, current_user.id) for t in templates],
        "total": len(templates),
    }


@router.post("/templates", status_code=201)
async def create_template(
    body: TemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建查询模板（R8.1~R8.4）。

    分享目标在**任何写入之前**逐个鉴权，任一失败即 rollback 后 403 —— 保证不落库
    部分结果。改造前 router 直接 `db.add` + `commit`，分享列不鉴权也不归一。
    """
    normalized = _normalize_template_scope(
        body.scope, body.shared_project_ids, body.config
    )
    try:
        await _assert_template_scope_edit(
            normalized, current_user=current_user, db=db
        )
    except HTTPException:
        # 写前回滚：本请求可能已在同一 session 里读过数据，显式回滚避免脏事务
        # 影响后续请求（R8.4）。
        await db.rollback()
        raise

    tpl = await template_service.save_template(
        db=db,
        creator_id=current_user.id,
        name=body.name,
        scope=normalized.scope,
        config=body.config,
        description=body.description,
        data_source=body.data_source,
        shared_project_ids=list(normalized.shared_project_ids),
    )
    await db.commit()
    await db.refresh(tpl)
    return _serialize_template(tpl, current_user.id)


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板详情。"""
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})
    # 权限：本人 or 全局可见
    if tpl.scope != "global" and tpl.created_by != current_user.id:
        raise HTTPException(status_code=403, detail={"error_code": "TEMPLATE_NOT_VISIBLE"})
    return _serialize_template(tpl, current_user.id)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模板（仅创建者）。"""
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})
    await _assert_template_visible(tpl, current_user=current_user, db=db)
    # 仅创建者可改 —— **admin 也不例外**（R8.5）。模板承载的是个人查询习惯与分享
    # 意图，管理员改他人模板会让对方看到与自己意图不符的结果却无从察觉。
    if _template_owner_id(tpl) != current_user.id:
        raise HTTPException(status_code=403, detail={"error_code": "ONLY_OWNER_CAN_UPDATE"})

    if body.scope is not None or body.shared_project_ids is not None:
        normalized = _normalize_template_scope(
            body.scope if body.scope is not None else tpl.scope,
            body.shared_project_ids
            if body.shared_project_ids is not None
            else getattr(tpl, "shared_project_ids", None),
            body.config if body.config is not None else tpl.config,
        )
        try:
            await _assert_template_scope_edit(
                normalized, current_user=current_user, db=db
            )
        except HTTPException:
            await db.rollback()
            raise
        tpl.scope = normalized.scope
        tpl.shared_project_ids = list(normalized.shared_project_ids)

    if body.name is not None:
        tpl.name = body.name
    if body.description is not None:
        tpl.description = body.description
    if body.data_source is not None:
        tpl.data_source = body.data_source
    if body.config is not None:
        tpl.config = body.config
    if body.scope is not None:
        tpl.scope = body.scope
    tpl.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tpl)
    return _serialize_template(tpl, current_user.id)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除模板 —— **仅创建者**，admin 亦不可删他人模板（R8.5）。"""
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})
    await _assert_template_visible(tpl, current_user=current_user, db=db)
    if _template_owner_id(tpl) != current_user.id:
        raise HTTPException(status_code=403, detail={"error_code": "ONLY_OWNER_CAN_DELETE"})
    await db.delete(tpl)
    await db.commit()
    return None


@router.post("/templates/{template_id}/execute")
async def execute_template(
    template_id: str,
    body: TemplateExecuteRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行模板 —— 复用 execute 主链路并对目标项目重新鉴权（R8.6）。

    关键在于**不另走旁路**：模板只是一组查询参数，执行仍经 `execute_query` →
    `ExecuteCompatibilityAdapter` → 编排器，因此归属校验、分页、审计与直接查询
    完全一致。改造前根本没有此端点，模板「执行」由前端把 config 拼成 execute
    请求体自行发起，服务端无从校验模板可见性。
    """
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})

    # 模板可见即可执行（含 team/project 分享），判定复用 TemplateService
    await template_service.assert_executable(tpl, user=current_user, db=db)

    config = tpl.config if isinstance(tpl.config, dict) else {}
    query_body = QueryRequest(
        project_id=str(body.project_id),
        year=int(config.get("year") or 0),
        source=str(config.get("source") or tpl.data_source or ""),
        filters=config.get("filters") or {},
        columns=list(config.get("selected_columns") or config.get("columns") or []),
        limit=int(config.get("page_size") or config.get("limit") or 500),
        offset=int(config.get("offset") or 0),
        sort=list(config.get("sort") or []),
        group=config.get("group"),
        pivot=config.get("pivot"),
        acnr_targets=list(config.get("acnr_targets") or []),
    )
    return await execute_query(query_body, response, db, current_user)


# ─── Cell Writeback Endpoint (Req 2, Req 13) ────────────────────────────────


class CellWritebackRequest(BaseModel):
    project_id: str
    wp_code: str
    sheet_name: str
    cell_ref: str  # e.g. "B7"
    new_value: Any = None
    # tb / adj / report 写入实现已删除（任务 13，ADR-AQL-02）：审定数只经发布门、调整分录只经调整分录服务 ⇒ 422
    module: Literal["workpaper", "note"] = "workpaper"

    # ── 附注归属字段（module="note" 时必填）──────────────────────────────
    # 设计 §五.2：writeback schema 显式带归属元组，不得把 record id 视作权限边界。
    note_record_id: str | None = None        # consol_note_data.id（附注记录主键）
    note_section_id: str | None = None       # consol_note_data.section_id
    note_year: int | None = None             # consol_note_data.year（有效审计年度）
    note_node_key: str | None = None         # consol_note_data.node_key（None = legacy NULL 行）
    note_row: int | None = None              # 目标行索引（0-based data rows）
    note_column: str | None = None           # 目标列名（e.g. "year_end", "name"）

    @model_validator(mode="after")
    def _validate_note_ownership_fields(self) -> "CellWritebackRequest":
        """module='note' 时必须携带完整归属字段。

        需求 3.3：记录 ID 对应行的全部归属字段须与请求逐项相等，否则拒绝。
        """
        if self.module != "note":
            return self
        missing = []
        if not self.note_record_id:
            missing.append("note_record_id")
        if not self.note_section_id:
            missing.append("note_section_id")
        if self.note_year is None:
            missing.append("note_year")
        if self.note_row is None:
            missing.append("note_row")
        if not self.note_column:
            missing.append("note_column")
        # note_node_key 为 None 表示 legacy NULL 行，是合法的
        if missing:
            raise ValueError(
                f"module='note' 时以下归属字段必填: {', '.join(missing)}"
            )
        return self


@router.post("/cell-writeback")
async def cell_writeback(
    body: CellWritebackRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """双向写回单 cell（Req 2, Req 13）。

    Headers: X-File-Opened-At (ISO 8601)
    Response 200: {success: true, updated_at: str}
    Response 409: {conflict: true, latest_updated_at: str, latest_editor: str}
    Response 403: {error: "no_write_permission"} or {error: "non_workpaper_source"}
    """
    from app.services.custom_query.snapshot_writer import (
        AuditWriteFailed,
        WritebackConflict,
        WritebackPermissionDenied,
        WritebackResolveUnavailable,
        WritebackTargetNotFound,
        WritebackTargetUnresolvable,
        snapshot_writer,
    )
    from app.services.custom_query.snapshot_writer_modules import (
        NoteOwnershipMismatch,
        NoteRecordNotFound,
    )

    # 解析 X-File-Opened-At header
    opened_at_str = request.headers.get("X-File-Opened-At")
    if not opened_at_str:
        raise HTTPException(status_code=400, detail="Missing X-File-Opened-At header")

    try:
        opened_at = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid X-File-Opened-At format")

    # ─── 统一项目编辑权限校验（替代原角色白名单）§5.13 fix ────────────────
    visible_ids = await get_visible_project_ids(current_user, db)
    if uuid.UUID(body.project_id) not in visible_ids:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "PROJECT_NOT_VISIBLE"},
        )
    # 非 admin/partner 需验证项目级编辑权限
    if current_user.role.value not in ("admin", "partner"):
        pu_result = await db.execute(
            select(ProjectUser).where(
                ProjectUser.project_id == uuid.UUID(body.project_id),
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        member = pu_result.scalar_one_or_none()
        if not member or member.permission_level.value not in ("edit",):
            raise HTTPException(
                status_code=403,
                detail={"error_code": "NO_EDIT_PERMISSION"},
            )

    # 查找 wp_id（workpaper 模块通过 wp_code + project_id 查找）
    if body.module == "workpaper":
        result = await db.execute(
            # wp_code 在 wp_index 上（working_paper 无该列），须经 wp_index_id 关联
            text("SELECT wp.id FROM working_paper wp "
                 "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                 "WHERE wi.wp_code = :code AND wp.project_id = :pid LIMIT 1"),
            {"code": body.wp_code, "pid": body.project_id},
        )
        wp_row = result.first()
        if not wp_row:
            not_found = WritebackTargetNotFound(body.wp_code)
            raise HTTPException(status_code=404, detail={"error_code": not_found.error_code, "message": not_found.message})
        wp_id = str(wp_row[0])
    else:
        # 附注模块：记录以 note_record_id 定位，wp_code 只作兼容标识传递
        wp_id = body.wp_code

    try:
        write_result = await snapshot_writer.write_cell(
            db=db,
            user=current_user,
            wp_id=wp_id,
            sheet_name=body.sheet_name,
            cell_ref=body.cell_ref,
            new_value=body.new_value,
            opened_at=opened_at,
            module=body.module,
            project_id=body.project_id,
            # ── 附注归属字段（Task 3.4：FOR UPDATE + 逐项校验）──────────
            note_record_id=body.note_record_id,
            note_section_id=body.note_section_id,
            note_year=body.note_year,
            note_node_key=body.note_node_key,
            note_project_id=body.project_id if body.module == "note" else None,
        )
        await db.commit()
    except WritebackConflict as e:
        await db.rollback()
        return Response(
            content=json.dumps({
                "conflict": True,
                "latest_updated_at": e.latest_updated_at.isoformat() if e.latest_updated_at else None,
                "latest_editor": e.latest_editor,
            }),
            status_code=409,
            media_type="application/json",
        )
    except WritebackPermissionDenied as e:
        await db.rollback()
        raise HTTPException(
            status_code=403,
            detail={"error": e.reason},
        )
    except WritebackTargetNotFound as e:
        # R4.2：取行带请求项目，他项目底稿查不到即 404（不读、不锁）
        await db.rollback()
        raise HTTPException(status_code=404, detail={"error_code": e.error_code, "message": e.message})
    except WritebackTargetUnresolvable as e:
        # R3.4：回写目标无法解析为有效 addr_id → 中止、数据不变
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"error_code": e.error_code, "message": e.message},
        )
    except WritebackResolveUnavailable as e:
        # R3.5：resolve 不可用/5s 无响应 → 中止、数据不变
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error_code": e.error_code, "message": e.message},
        )
    except AuditWriteFailed as e:
        # R14.8「无审计不回写」：审计写入失败 → 回滚回写改动
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"error_code": e.error_code, "message": e.message},
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except NoteOwnershipMismatch as e:
        await db.rollback()
        raise HTTPException(
            status_code=403,
            detail={"error_code": "NOTE_OWNERSHIP_MISMATCH", "message": str(e)},
        )
    except NoteRecordNotFound as e:
        await db.rollback()
        raise HTTPException(
            status_code=404,
            detail={"error_code": "NOTE_RECORD_NOT_FOUND", "message": str(e)},
        )

    # Task 16 / Requirement 13.1 / Property 52：snapshot_writer 在事务内只把
    # WORKPAPER_SAVED 写成耐久 outbox 行，事件必须在 content commit 之后才发布。
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    await DurableEventOutboxService.publish_pending(db)

    # 审计日志 — 回写逐次记录（不节流，R14.3/R14.4）：操作者/UTC 秒级时间戳/操作类型/
    # 目标 addr_id 集合/新旧值/结果，经 audit_helper 单点接线。
    # workpaper 模块已在回写事务内记审计（R14.8「无审计不回写」，见 snapshot_writer 第 10 步），
    # 此处避免重复；其余模块仍在此按「不节流」补记。
    if not write_result.get("audit_logged"):
        try:
            from app.services.custom_query.audit_helper import record_writeback

            await record_writeback(
                user_id=current_user.id,
                addr_ids=write_result.get("addr_id"),
                old_value=write_result.get("old_value"),
                new_value=body.new_value,
                result="success",
                project_id=body.project_id,
                object_id=wp_id,
                extra={
                    "wp_code": body.wp_code,
                    "sheet_name": body.sheet_name,
                    "cell_ref": body.cell_ref,
                    "module": body.module,
                },
            )
        except Exception as audit_e:
            logger.warning("audit_log for cell_writeback failed: %s", audit_e)

    response: dict = {
        "success": True,
        "updated_at": write_result.get("updated_at"),
        "addr_id": write_result.get("addr_id"),
        "column_metadata": write_result.get("column_metadata"),
    }
    # 下游联动（file_version / prefill_stale / WORKPAPER_SAVED → cross_ref·stale·SSE）
    # 未触发时必须透传给调用方 —— 数据写回了但联动没跑，静默返回 success 会让用户
    # 以为一切正常，而其实别处的取数不会刷新。
    if write_result.get("warnings"):
        response["warnings"] = write_result["warnings"]
    return response


# ─── GIN Index Health Endpoint ───────────────────────────────────────────────


@router.get("/index-health")
async def get_index_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get GIN index health status (building state + size alert).

    Requirements: Req 5 AC 4, AC 5
    """
    from app.services.gin_index_monitor import (
        is_index_building,
        get_index_size_bytes,
        check_index_size_alert,
        INDEX_SIZE_ALERT_THRESHOLD_BYTES,
    )

    building = is_index_building()
    size_bytes = await get_index_size_bytes(db)
    alert = await check_index_size_alert(db)

    return {
        "index_name": "idx_wp_parsed_data_gin",
        "is_building": building,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2) if size_bytes else None,
        "threshold_mb": INDEX_SIZE_ALERT_THRESHOLD_BYTES / (1024 * 1024),
        "alert": alert,
    }


# ─── Cross-Sheet Trace Endpoint (Req 3) ──────────────────────────────────────


@router.get("/cross-sheet-trace")
async def cross_sheet_trace(
    wp_code: str = Query(..., description="底稿编码"),
    sheet_name: str = Query(..., description="起始 sheet 名"),
    cell_ref: str = Query(..., description="起始 cell 引用 (e.g. A2)"),
    project_id: str = Query(..., description="项目 ID"),
    max_depth: int = Query(default=3, ge=1, le=3, description="最大追溯深度 (上限 3)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """跨 sheet 公式追溯（BFS 最深 3 层）。

    Requirements: Req 3 AC 1-5
    - BFS 遍历 =Sheet!Cell 引用链
    - 环检测：visited set，发现重复 URI 标 cycle=True
    - 引用目标缺失标 missing=True 不阻塞其它分支
    - 敏感操作不参与审计节流（每次必记）
    """
    from app.services.custom_query.cross_sheet_trace_orchestrator import (
        cross_sheet_trace_orchestrator,
    )

    # ─── OwnershipGuard 单点准入（BEFORE 任何数据读取）R9.1/R9.2/R9.5 ─────────
    # 溯源（override/trace）路径统一经 OwnershipGuard 强制 project 归属校验（防 IDOR）；
    # 不通过 → 403 FORBIDDEN_PROJECT 且不触达 working_paper 读取层。
    from app.services.custom_query.ownership_guard import ownership_guard
    await ownership_guard.assert_target_accessible(
        user=current_user, project_id=project_id, db=db
    )

    # 查找 working_paper 的 parsed_data（限定 project_id，防跨项目 wp_code 撞车）
    result = await db.execute(
        text(
            # wp_code 在 wp_index 上（working_paper 无该列），须经 wp_index_id 关联
            "SELECT wp.id, wp.parsed_data FROM working_paper wp "
            "JOIN wp_index wi ON wi.id = wp.wp_index_id "
            "WHERE wi.wp_code = :code AND wp.project_id = CAST(:pid AS uuid) LIMIT 1"
        ),
        {"code": wp_code, "pid": project_id},
    )
    wp_row = result.first()
    if not wp_row:
        raise HTTPException(status_code=404, detail=f"Working paper not found: {wp_code}")

    wp_id = str(wp_row[0])
    parsed_data = wp_row[1] if wp_row[1] else {}

    # 如果 parsed_data 是字符串则解析
    if isinstance(parsed_data, str):
        try:
            parsed_data = json.loads(parsed_data)
        except (json.JSONDecodeError, TypeError):
            parsed_data = {}

    # 执行溯源：同步纯 BFS + async ACNR addr_id 解析（经 orchestrator，R4.2/R4.4/R8.4）
    #
    # 为什么不能直接调 cross_sheet_resolver.resolve()：本端点是 async，调用时事件循环
    # 正在运行，而同步 BFS 内部的 `_sync_resolve` 一探测到 running loop 就返回 None
    # 降级 → 每个链节点的 addr_id 恒为 None，溯源结果无法跳转、审计日志也拿不到真
    # addr_id。异步 IO 由 orchestrator 上浮：BFS 仍是同步纯函数，addr_id 经
    # AddressingService 一次性并发解析后合并回链。
    trace_result = await cross_sheet_trace_orchestrator.trace(
        parsed_data,
        sheet_name,
        cell_ref,
        project_id=project_id,
        db=db,
        max_depth=max_depth,
    )

    # 审计日志 — 跨 sheet 溯源逐次记录（不节流，R14.3/R14.4）：操作者/UTC 秒级时间戳/
    # 操作类型/目标 addr_id 集合/结果，经 audit_helper 单点接线
    try:
        from app.services.custom_query.audit_helper import record_cross_sheet_trace

        # 目标 addr_id 集合：根目标 + 溯源链节点的**真** addr_id（经 orchestrator 解析）。
        # 未能解析的节点（addr_id=None，优雅降级）退回 uri 形态占位，保证审计留痕完整。
        trace_addr_ids = [f"{wp_code}/{sheet_name}/{cell_ref}"]
        trace_addr_ids.extend(node.addr_id or node.uri for node in trace_result.chain)

        await record_cross_sheet_trace(
            user_id=current_user.id,
            addr_ids=trace_addr_ids,
            result="success",
            project_id=project_id,
            object_id=wp_id,
            extra={
                "wp_code": wp_code,
                "sheet_name": sheet_name,
                "cell_ref": cell_ref,
                "max_depth": max_depth,
                "chain_length": len(trace_result.chain),
                "has_cycle": trace_result.has_cycle,
            },
        )
    except Exception as audit_e:
        logger.warning("audit_log for cross_sheet_trace failed: %s", audit_e)

    return trace_result.model_dump()


# ─── Address Resolve Endpoint (Req 14 AC 2/3) ────────────────────────────────


class AddressResolveResponse(BaseModel):
    module: str  # workpaper / report / note / adj / tb
    template_wp_code: str | None = None
    template_name: str | None = None
    sheet_name: str | None = None
    cell_ref: str | None = None
    registered: bool = False  # wp_template_registry 是否已注册
    route_path: str = ""  # 前端跳转路径
    route_query: dict = Field(default_factory=dict)  # highlight 参数


@router.get("/address-resolve", response_model=AddressResolveResponse)
async def address_resolve(
    uri: str = Query(..., description="Source URI, e.g. 'workpaper:D2|审定表D2-1|B7'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """URI 反查模板信息（模板溯源）。

    Requirements: Req 14 AC 2, AC 3
    - 解析 URI 得到 module / wp_code / sheet / cell
    - 查 wp_template_registry 判断是否已注册
    - 返回前端跳转路径 + highlight 参数
    """
    from app.services.custom_query.module_cell_resolver import parse_source_uri

    parsed = parse_source_uri(uri)
    if not parsed:
        raise HTTPException(status_code=400, detail=f"Invalid source URI: {uri}")

    module = parsed.get("module", "")
    qualifier = parsed.get("qualifier", "")
    sheet_name = parsed.get("sheet_name")
    cell_range = parsed.get("cell_range")

    # 对于 workpaper 模块，qualifier 是 wp_code
    template_wp_code: str | None = None
    template_name: str | None = None
    registered = False
    route_path = ""
    route_query: dict = {}

    if module == "workpaper":
        template_wp_code = qualifier
        # 查 wp_template_registry 判断是否已注册
        result = await db.execute(
            text("SELECT wp_name FROM wp_template_registry WHERE wp_code = :code"),
            {"code": qualifier},
        )
        row = result.first()
        if row:
            registered = True
            template_name = row[0]
        # 前端跳转路径：模板库底稿详情
        route_path = "/template-library"
        route_query = {"tab": "workpaper", "wp_code": qualifier}
        if sheet_name:
            route_query["sheet"] = sheet_name
        if cell_range:
            route_query["highlight"] = cell_range

    elif module == "report":
        template_wp_code = None
        template_name = qualifier  # report_type as name
        registered = True  # 报表模板始终存在于 report_config
        route_path = "/template-library"
        route_query = {"tab": "report", "report_type": qualifier}
        if cell_range:
            route_query["highlight"] = cell_range

    elif module == "note":
        template_wp_code = None
        template_name = qualifier  # section_id as name
        registered = True  # 附注模板始终存在于 seed JSON
        route_path = "/template-library"
        route_query = {"tab": "note", "section_id": qualifier}
        if cell_range:
            route_query["highlight"] = cell_range

    elif module in ("adj", "tb"):
        template_wp_code = None
        template_name = qualifier
        registered = False
        route_path = "/template-library"
        route_query = {"tab": module, "qualifier": qualifier}
        if cell_range:
            route_query["highlight"] = cell_range

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported module: {module}")

    return AddressResolveResponse(
        module=module,
        template_wp_code=template_wp_code,
        template_name=template_name,
        sheet_name=sheet_name,
        cell_ref=cell_range,
        registered=registered,
        route_path=route_path,
        route_query=route_query,
    )
