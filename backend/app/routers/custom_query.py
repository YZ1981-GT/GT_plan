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
  GET    /api/custom-query/indicators           — 获取可查询指标库（树形）
  GET    /api/custom-query/templates            — 列出查询模板（私有 + 全局）
  POST   /api/custom-query/templates            — 创建查询模板
  GET    /api/custom-query/templates/{id}       — 获取模板详情
  PUT    /api/custom-query/templates/{id}       — 更新模板
  DELETE /api/custom-query/templates/{id}       — 删除模板（仅创建者或 admin）
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.custom_query_models import CustomQueryTemplate

router = APIRouter(prefix="/api/custom-query", tags=["custom-query"])


class QueryRequest(BaseModel):
    project_id: str
    year: int
    source: str  # report | trial_balance | disclosure | adjustment | worksheet | workpaper | account_balance | ledger_entries | report_lines | workhours
    filters: dict = {}  # report_type, account_name, section_id, company_code, etc.
    columns: list[str] = []  # 要查询的列（空=全部）
    limit: int = 500
    offset: int = 0


@router.get("/indicators")
async def get_indicators(
    project_id: str | None = Query(default=None, description="项目 ID — 传入后报表/附注树会按项目模板类型动态生成"),
    db: AsyncSession = Depends(get_db),
):
    """获取可查询指标库（树形结构）

    传入 project_id 时：
      - 报表大类下展示项目模板类型（国企/上市）对应的具体报表
      - 附注大类下展示项目实际配置的章节（按 parent_section 分组成子大类）
    未传 project_id 时：报表/附注用通用降级树（仅显示报表类型，无国企/上市区分）
    """
    template_type = await _resolve_project_template_type(db, project_id)
    standard_label = _STANDARD_LABEL.get(template_type, "通用")

    # ─── 报表树：项目模板类型决定大类标签 + 报表清单 ───────────────
    # 6 张报表：BS / IS / CFS / CFS-补充资料 / 权益变动 / 减值准备表
    # 减值准备表 (impairment_provision) 仅 soe 模板有数据，listed 自动隐藏避免误点
    report_children = [
        {"key": "report_balance_sheet", "label": f"资产负债表（{standard_label}）", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "standard": template_type},
        {"key": "report_income_statement", "label": f"利润表（{standard_label}）", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "standard": template_type},
        {"key": "report_cash_flow_statement", "label": f"现金流量表（{standard_label}）", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "standard": template_type},
        {"key": "report_cash_flow_supplement", "label": f"现金流量表补充资料（{standard_label}）", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "standard": template_type},
        {"key": "report_equity_statement", "label": f"所有者权益变动表（{standard_label}）", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "standard": template_type},
    ]
    if template_type == "soe":
        report_children.append(
            {"key": "report_impairment_provision", "label": f"减值准备表（{standard_label}）", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "standard": template_type}
        )

    # ─── 附注树：按 parent_section 分组成大类→明细两层 ─────────────
    disclosure_children = await _build_disclosure_tree(template_type)

    # ─── 合并范围单位树（仅合并项目可见）────────────────────────
    consol_units_node = await _build_consol_units_tree(db, project_id)

    base_tree: list[dict] = []
    base_tree.append({
        "key": "report",
        "label": f"📊 报表（{standard_label}）" if project_id else "📊 报表",
        "icon": "📊",
        "children": report_children,
    })
    base_tree.append({
        "key": "trial_balance", "label": "📋 试算表", "icon": "📋",
        "children": [
            {"key": "tb_detail", "label": "科目明细", "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"]},
            {"key": "tb_summary", "label": "试算平衡表", "columns": ["row_code", "row_name", "unadjusted", "aje_dr", "aje_cr", "rcl_dr", "rcl_cr", "audited"]},
        ],
    })
    base_tree.append({
        "key": "disclosure",
        "label": f"📝 附注（{standard_label}）" if project_id else "📝 附注",
        "icon": "📝",
        "children": disclosure_children,
    })
    # 合并范围节点：仅合并项目（report_scope=consolidated 且至少 1 家纳入单位）展示
    if consol_units_node:
        base_tree.append(consol_units_node)
    base_tree.append({
        "key": "adjustment", "label": "📐 调整分录", "icon": "📐",
        "children": [
            {"key": "adj_aje", "label": "审计调整分录(AJE)", "columns": ["entry_number", "account_name", "debit_amount", "credit_amount", "description"]},
            {"key": "adj_rcl", "label": "重分类调整(RCL)", "columns": ["entry_number", "account_name", "debit_amount", "credit_amount", "description"]},
        ],
    })
    base_tree.append({
        "key": "worksheet", "label": "📑 工作底稿", "icon": "📑",
        "children": [
            {"key": "ws_info", "label": "基本信息表", "columns": ["company_name", "company_code", "holding_type", "non_common_ratio"]},
            {"key": "ws_elimination", "label": "抵消分录", "columns": ["direction", "subject", "amount", "desc"]},
            {"key": "ws_consol_tb", "label": "合并试算平衡表", "columns": ["row_code", "row_name", "summary", "equity_dr", "equity_cr", "audited"]},
        ],
    })
    base_tree.append({
        "key": "workpaper", "label": "📄 底稿列表", "icon": "📄",
        "children": await _build_workpaper_tree(db, project_id),
    })
    base_tree.append({
        "key": "account_balance", "label": "💰 科目余额", "icon": "💰",
        "children": [
            {"key": "account_balance", "label": "科目余额表", "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"]},
        ],
    })
    base_tree.append({
        "key": "ledger_entries", "label": "📜 序时账", "icon": "📜",
        "children": [
            {"key": "ledger_entries", "label": "序时账明细", "columns": ["voucher_date", "voucher_no", "account_code", "account_name", "debit_amount", "credit_amount", "summary"]},
        ],
    })
    base_tree.append({
        "key": "report_lines", "label": "📈 报表行次", "icon": "📈",
        "children": [
            {"key": "report_lines", "label": "报表行次配置", "columns": ["row_code", "row_name", "report_type", "applicable_standard", "indent_level", "is_total_row", "formula"]},
        ],
    })
    base_tree.append({
        "key": "workhours", "label": "⏱️ 工时记录", "icon": "⏱️",
        "children": [
            {"key": "workhours", "label": "工时记录", "columns": ["work_date", "hours", "description", "status", "staff_id"]},
        ],
    })
    return base_tree


# ─── 辅助函数：项目模板类型解析 + 附注树构建 ───────────────────────────────

_STANDARD_LABEL = {"soe": "国企", "listed": "上市"}
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
                {"key": f"consol_unit:{cc}:account_balance", "label": "科目余额", "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"], "company_code": cc},
                {"key": f"consol_unit:{cc}:ledger_entries", "label": "序时账明细", "columns": ["voucher_date", "voucher_no", "account_code", "account_name", "debit_amount", "credit_amount", "summary"], "company_code": cc},
                {"key": f"consol_unit:{cc}:tb_detail", "label": "试算表（个体）", "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"], "company_code": cc},
                {"key": f"consol_unit:{cc}:adjustment", "label": "调整分录", "columns": ["entry_number", "account_name", "debit_amount", "credit_amount", "description"], "company_code": cc},
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
    """读 backend/data/consol_note_sections_{template_type}.json（带模块级缓存）"""
    if template_type in _DISCLOSURE_CACHE:
        return _DISCLOSURE_CACHE[template_type]
    data_path = Path(__file__).resolve().parent.parent.parent / "data" / f"consol_note_sections_{template_type}.json"
    if not data_path.exists():
        _DISCLOSURE_CACHE[template_type] = []
        return []
    try:
        with data_path.open("r", encoding="utf-8") as f:
            sections = json.load(f)
        _DISCLOSURE_CACHE[template_type] = sections if isinstance(sections, list) else []
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


async def _build_workpaper_tree(db: AsyncSession, project_id: str | None) -> list[dict]:
    """底稿树：循环 → 主底稿（科目名）→ sheet 程序明细。

    数据源双轨：
      - 传入 project_id：从 `wp_index` 取项目实际配置的底稿（裁剪后）
      - 未传 project_id：从 `wp_account_mapping.json` 取全集
    主底稿 = wp_code 不含连字符的根节点（如 E1 / D2），sheet 程序 = 同 cycle 下 wp_code-N 形式的子项
    """
    mapping = _load_wp_mapping()
    # mapping 索引：wp_code -> {account_name, account_codes, ...}
    map_by_code: dict[str, dict] = {m.get("wp_code", ""): m for m in mapping if m.get("wp_code")}

    # 取底稿条目：项目级走 wp_index，否则走全集 mapping
    items: list[dict] = []
    if project_id:
        try:
            proj_uuid = uuid.UUID(project_id)
            sql = text("""
                SELECT wp_code, wp_name, audit_cycle
                FROM wp_index
                WHERE project_id = :pid AND is_deleted = false
                ORDER BY audit_cycle, wp_code
            """)
            rows = (await db.execute(sql, {"pid": str(proj_uuid)})).fetchall()
            for r in rows:
                code = r[0] or ""
                items.append({
                    "wp_code": code,
                    "wp_name": r[1] or "",
                    "cycle": r[2] or (code[:1] if code else ""),
                    "account_name": map_by_code.get(code, {}).get("account_name") or "",
                })
        except (TypeError, ValueError):
            items = []
    if not items:
        # 全集兜底：用 mapping JSON
        for m in mapping:
            code = m.get("wp_code", "")
            if not code:
                continue
            items.append({
                "wp_code": code,
                "wp_name": m.get("wp_name", ""),
                "cycle": m.get("cycle") or (code[:1] if code else ""),
                "account_name": m.get("account_name") or "",
            })

    # 按 cycle 分组 → 主底稿 → sheet 程序两层
    cycle_groups: dict[str, list[dict]] = {}
    for it in items:
        cy = (it["cycle"] or "").upper() or "其他"
        cycle_groups.setdefault(cy, []).append(it)

    # cycle 节点排序：A-N 字母序 + S 末尾，未知字母兜底
    def _cycle_sort_key(cy: str) -> tuple:
        order = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "S"]
        return (order.index(cy) if cy in order else 99, cy)

    result: list[dict] = []
    for cy in sorted(cycle_groups.keys(), key=_cycle_sort_key):
        members = cycle_groups[cy]
        # 主底稿：wp_code 无连字符的（如 E1 / D2）；sheet 程序：含连字符（如 E1-1）
        primaries = sorted([m for m in members if "-" not in m["wp_code"]], key=lambda x: x["wp_code"])
        sheets_by_primary: dict[str, list[dict]] = {p["wp_code"]: [] for p in primaries}
        for m in members:
            if "-" not in m["wp_code"]:
                continue
            base = m["wp_code"].split("-", 1)[0]
            sheets_by_primary.setdefault(base, []).append(m)
        # 处理孤儿（只有 sheet 子项无主底稿）：把 base 当伪主底稿
        primary_codes = {p["wp_code"] for p in primaries}
        for base, ss in sheets_by_primary.items():
            if base not in primary_codes and ss:
                primaries.append({"wp_code": base, "wp_name": base, "cycle": cy, "account_name": ""})
        primaries.sort(key=lambda x: x["wp_code"])

        primary_nodes: list[dict] = []
        for p in primaries:
            code = p["wp_code"]
            acc = p.get("account_name") or ""
            wpname = p.get("wp_name") or ""
            # label: "E1 货币资金" 优先用科目名，否则用 wp_name
            primary_label = f"{code} {acc or wpname}".strip()
            sheet_children = sheets_by_primary.get(code, [])
            children_nodes: list[dict] = []
            # 主底稿自己作为 sheet 列表的"汇总入口"叶子（点它查整张主表）
            children_nodes.append({
                "key": f"workpaper:{code}",
                "label": f"{code}（汇总）",
                "wp_code": code,
                "columns": ["wp_code", "wp_name", "cycle", "status", "review_status"],
            })
            for s in sorted(sheet_children, key=lambda x: x["wp_code"]):
                s_code = s["wp_code"]
                s_acc = s.get("account_name") or s.get("wp_name") or ""
                children_nodes.append({
                    "key": f"workpaper:{s_code}",
                    "label": f"{s_code} {s_acc}".strip(),
                    "wp_code": s_code,
                    "columns": ["wp_code", "wp_name", "cycle", "status", "review_status"],
                })
            primary_nodes.append({
                "key": f"wp_primary_{code}",
                "label": primary_label,
                "children": children_nodes,
            })
        cycle_label = f"{cy} {_CYCLE_NAMES.get(cy, '')}".strip() + f"（{len(primaries)}）"
        result.append({
            "key": f"wp_cycle_{cy}",
            "label": cycle_label,
            "children": primary_nodes,
        })
    return result


@router.post("/execute")
async def execute_query(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """执行自定义查询"""
    source = body.source
    pid = body.project_id
    year = body.year
    filters = body.filters
    limit = min(body.limit, 2000)

    try:
        # disclosure_note:section_id 形式（树叶子点击）→ 走 disclosure 并把 section_id 注入 filters
        if source.startswith("disclosure_note:"):
            sid = source.split(":", 1)[1]
            new_filters = {**filters, "section_id": sid}
            return await _query_disclosure(db, pid, year, new_filters, limit)
        # consol_unit:{company_code}:{kind} 形式（合并单位树叶子点击）
        if source.startswith("consol_unit:"):
            parts = source.split(":", 2)
            if len(parts) == 3:
                _, cc, kind = parts
                new_filters = {**filters, "company_code": cc}
                if kind == "account_balance":
                    return await _query_account_balance(db, pid, year, new_filters, limit)
                if kind == "ledger_entries":
                    return await _query_ledger_entries(db, pid, year, new_filters, limit)
                if kind == "tb_detail":
                    return await _query_trial_balance(db, pid, year, new_filters, limit)
                if kind == "adjustment":
                    # 调整分录按 company_code 暂走通用查询（adjustments 表无 company_code 列时返回空）
                    return await _query_adjustments(db, pid, year, {**filters, "adjustment_type": "AJE"}, limit)
            return {"rows": [], "columns": [], "total": 0, "error": f"未知合并单位查询: {source}"}
        # workpaper:{wp_code} 形式（底稿树叶子点击）
        if source.startswith("workpaper:"):
            wp_code = source.split(":", 1)[1]
            return await _query_workpaper(db, pid, year, {**filters, "wp_code": wp_code}, limit)
        if source == 'report' or source.startswith('report_'):
            return await _query_report(db, pid, year, filters, limit)
        elif source == 'trial_balance' or source == 'tb_detail':
            return await _query_trial_balance(db, pid, year, filters, limit)
        elif source == 'tb_summary':
            return await _query_tb_summary(db, pid, year, filters, limit)
        elif source == 'disclosure' or source == 'disclosure_note':
            return await _query_disclosure(db, pid, year, filters, limit)
        elif source.startswith('adj_') or source == 'adjustment':
            return await _query_adjustments(db, pid, year, filters, limit)
        elif source.startswith('ws_') or source == 'worksheet':
            return await _query_worksheet(db, pid, year, filters, limit)
        elif source == 'workpaper':
            return await _query_workpaper(db, pid, year, filters, limit)
        elif source == 'account_balance':
            return await _query_account_balance(db, pid, year, filters, limit)
        elif source == 'ledger_entries':
            return await _query_ledger_entries(db, pid, year, filters, limit)
        elif source == 'report_lines':
            return await _query_report_lines(db, pid, year, filters, limit)
        elif source == 'workhours':
            return await _query_workhours(db, pid, year, filters, limit)
        else:
            return {"rows": [], "columns": [], "total": 0, "error": f"未知数据源: {source}"}
    except Exception as e:
        # 失败时回滚事务（防止 asyncpg session 污染影响后续请求）
        try:
            await db.rollback()
        except Exception:
            pass
        return {"rows": [], "columns": [], "total": 0, "error": str(e)}


async def _query_report(db, pid, year, filters, limit):
    report_type = filters.get("report_type", "balance_sheet")
    # standard 优先级：filters.standard > 项目 (template_type + report_scope) 推断 > 默认 soe_standalone
    standard = filters.get("standard")
    if not standard:
        template_type = await _resolve_project_template_type(db, pid)
        scope = await _resolve_project_report_scope(db, pid)
        # report_config 取值：soe_standalone / listed_standalone / listed_consolidated
        # soe 暂无 consolidated 数据，强制走 standalone
        if template_type == "soe":
            standard = "soe_standalone"
        else:
            standard = f"listed_{scope or 'standalone'}"
    # 优先查项目级数据，降级查全局模板
    query = "SELECT row_code, row_name, current_period_amount, prior_period_amount, indent_level, is_total_row FROM report_config WHERE report_type = :rt AND applicable_standard = :std AND is_deleted = false"
    params: dict = {"rt": report_type, "std": standard, "lim": limit}
    if pid:
        query += " AND (project_id = :pid OR project_id IS NULL)"
        params["pid"] = pid
    query += " ORDER BY row_number LIMIT :lim"
    result = await db.execute(text(query), params)
    rows = [{"row_code": r[0], "row_name": r[1], "current_period_amount": float(r[2]) if r[2] else None, "prior_period_amount": float(r[3]) if r[3] else None, "indent": r[4], "is_total": r[5]} for r in result.fetchall()]
    return {"rows": rows, "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "total": len(rows), "applicable_standard": standard}


async def _query_trial_balance(db, pid, year, filters, limit):
    query = "SELECT account_code, account_name, opening_balance, closing_balance, debit_amount, credit_amount FROM trial_balance_entries WHERE project_id = :pid AND year = :y"
    params: dict = {"pid": pid, "y": year, "lim": limit}
    if filters.get("account_name"):
        query += " AND account_name LIKE :an"
        params["an"] = f"%{filters['account_name']}%"
    if filters.get("company_code"):
        query += " AND company_code = :cc"
        params["cc"] = filters["company_code"]
    query += " ORDER BY account_code LIMIT :lim"
    result = await db.execute(text(query), params)
    rows = [{"account_code": r[0], "account_name": r[1], "opening_balance": float(r[2]) if r[2] else None, "closing_balance": float(r[3]) if r[3] else None, "debit_amount": float(r[4]) if r[4] else None, "credit_amount": float(r[5]) if r[5] else None} for r in result.fetchall()]
    return {"rows": rows, "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"], "total": len(rows)}


async def _query_tb_summary(db, pid, year, filters, limit):
    sheet_type = filters.get("report_type", "balance_sheet")
    result = await db.execute(
        text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": pid, "y": year, "sk": f"tb_summary_{sheet_type}"},
    )
    row = result.fetchone()
    if row and isinstance(row[0], dict):
        rows = row[0].get("rows", [])[:limit]
        return {"rows": rows, "columns": ["row_code", "row_name", "unadjusted", "aje_dr", "aje_cr", "rcl_dr", "rcl_cr", "audited"], "total": len(rows)}
    return {"rows": [], "columns": [], "total": 0}


async def _query_disclosure(db, pid, year, filters, limit):
    section_id = filters.get("section_id", "")
    if section_id:
        result = await db.execute(
            text("SELECT section_id, data FROM consol_note_data WHERE project_id = :pid AND year = :y AND section_id = :sid"),
            {"pid": pid, "y": year, "sid": section_id},
        )
    else:
        result = await db.execute(
            text("SELECT section_id, data FROM consol_note_data WHERE project_id = :pid AND year = :y LIMIT :lim"),
            {"pid": pid, "y": year, "lim": limit},
        )
    # 将附注数据展平为表格行（每个章节的每行数据变成一条记录）
    flat_rows = []
    all_headers: list[str] = []
    for r in result.fetchall():
        data = r[1] if isinstance(r[1], dict) else {}
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        if headers and not all_headers:
            all_headers = ["section_id"] + headers
        for row_data in rows[:100]:  # 每章节最多100行
            obj: dict = {"section_id": r[0]}
            for hi, h in enumerate(headers):
                obj[h] = row_data[hi] if hi < len(row_data) else ''
            flat_rows.append(obj)
    columns = all_headers if all_headers else ["section_id"]
    return {"rows": flat_rows[:limit], "columns": columns, "total": len(flat_rows)}


async def _query_adjustments(db, pid, year, filters, limit):
    adj_type = filters.get("adjustment_type", "AJE")
    result = await db.execute(
        text("SELECT entry_number, account_name, debit_amount, credit_amount, description, status FROM adjustments WHERE project_id = :pid AND year = :y AND adjustment_type = :at AND is_deleted = false ORDER BY entry_number LIMIT :lim"),
        {"pid": pid, "y": year, "at": adj_type, "lim": limit},
    )
    rows = [{"entry_number": r[0], "account_name": r[1], "debit_amount": float(r[2]) if r[2] else None, "credit_amount": float(r[3]) if r[3] else None, "description": r[4], "status": r[5]} for r in result.fetchall()]
    return {"rows": rows, "columns": ["entry_number", "account_name", "debit_amount", "credit_amount", "description", "status"], "total": len(rows)}


async def _query_worksheet(db, pid, year, filters, limit):
    sheet_key = filters.get("sheet_key", "info")
    result = await db.execute(
        text("SELECT data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": pid, "y": year, "sk": sheet_key},
    )
    row = result.fetchone()
    if row and isinstance(row[0], dict):
        data = row[0]
        rows = data.get("rows", [])[:limit]
        columns = list(rows[0].keys()) if rows else []
        return {"rows": rows, "columns": columns, "total": len(rows), "updated_at": str(row[1]) if row[1] else None}
    return {"rows": [], "columns": [], "total": 0}



# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.4 — 新增 5 个数据源查询函数
# ──────────────────────────────────────────────────────────────────────────


async def _query_workpaper(db, pid, year, filters, limit):
    """底稿列表（working_paper + wp_index）— working_paper 无 year 字段，year 仅用于过滤兼容"""
    sql = """
        SELECT wi.wp_code, wi.wp_name, wi.audit_cycle, wp.status, wp.review_status,
               wp.assigned_to, wp.created_at, wp.updated_at
        FROM working_paper wp
        LEFT JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE wp.project_id = :pid AND wp.is_deleted = false
    """
    params: dict = {"pid": pid, "lim": limit}
    if filters.get("status"):
        sql += " AND wp.status = :st"
        params["st"] = filters["status"]
    if filters.get("review_status"):
        sql += " AND wp.review_status = :rs"
        params["rs"] = filters["review_status"]
    if filters.get("cycle"):
        sql += " AND wi.audit_cycle = :cy"
        params["cy"] = filters["cycle"]
    if filters.get("wp_code"):
        # 支持精确单底稿查询（树叶子点击）+ 同 cycle 下子表前缀模糊（wp_code='E1' 时也带出 E1-1/E1-2）
        sql += " AND (wi.wp_code = :wpc OR wi.wp_code LIKE :wpc_like)"
        params["wpc"] = filters["wp_code"]
        params["wpc_like"] = f"{filters['wp_code']}-%"
    sql += " ORDER BY wi.wp_code LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "wp_code": r[0],
            "wp_name": r[1],
            "audit_cycle": r[2],
            "status": r[3],
            "review_status": r[4],
            "assigned_to": str(r[5]) if r[5] else None,
            "created_at": str(r[6]) if r[6] else None,
            "updated_at": str(r[7]) if r[7] else None,
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["wp_code", "wp_name", "audit_cycle", "status", "review_status", "assigned_to"],
        "total": len(rows),
    }


async def _query_account_balance(db, pid, year, filters, limit):
    """科目余额表（tb_balance）— B' 视图架构按 is_deleted=false 过滤"""
    sql = """
        SELECT account_code, account_name, opening_balance, closing_balance,
               debit_amount, credit_amount, currency_code
        FROM tb_balance
        WHERE project_id = :pid AND year = :y AND is_deleted = false
    """
    params: dict = {"pid": pid, "y": year, "lim": limit}
    if filters.get("account_code"):
        sql += " AND account_code LIKE :ac"
        params["ac"] = f"{filters['account_code']}%"
    if filters.get("account_name"):
        sql += " AND account_name LIKE :an"
        params["an"] = f"%{filters['account_name']}%"
    if filters.get("company_code"):
        sql += " AND company_code = :cc"
        params["cc"] = filters["company_code"]
    sql += " ORDER BY account_code LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "account_code": r[0],
            "account_name": r[1],
            "opening_balance": float(r[2]) if r[2] is not None else None,
            "closing_balance": float(r[3]) if r[3] is not None else None,
            "debit_amount": float(r[4]) if r[4] is not None else None,
            "credit_amount": float(r[5]) if r[5] is not None else None,
            "currency_code": r[6],
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount", "currency_code"],
        "total": len(rows),
    }


async def _query_ledger_entries(db, pid, year, filters, limit):
    """序时账（tb_ledger）"""
    sql = """
        SELECT voucher_date, voucher_no, account_code, account_name,
               debit_amount, credit_amount, summary
        FROM tb_ledger
        WHERE project_id = :pid AND year = :y AND is_deleted = false
    """
    params: dict = {"pid": pid, "y": year, "lim": limit}
    if filters.get("account_code"):
        sql += " AND account_code LIKE :ac"
        params["ac"] = f"{filters['account_code']}%"
    if filters.get("voucher_no"):
        sql += " AND voucher_no LIKE :vn"
        params["vn"] = f"%{filters['voucher_no']}%"
    if filters.get("summary"):
        sql += " AND summary LIKE :sm"
        params["sm"] = f"%{filters['summary']}%"
    if filters.get("date_from"):
        sql += " AND voucher_date >= :df"
        params["df"] = filters["date_from"]
    if filters.get("date_to"):
        sql += " AND voucher_date <= :dt"
        params["dt"] = filters["date_to"]
    sql += " ORDER BY voucher_date DESC, voucher_no LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "voucher_date": str(r[0]) if r[0] else None,
            "voucher_no": r[1],
            "account_code": r[2],
            "account_name": r[3],
            "debit_amount": float(r[4]) if r[4] is not None else None,
            "credit_amount": float(r[5]) if r[5] is not None else None,
            "summary": r[6],
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["voucher_date", "voucher_no", "account_code", "account_name", "debit_amount", "credit_amount", "summary"],
        "total": len(rows),
    }


async def _query_report_lines(db, pid, year, filters, limit):
    """报表行次配置（report_config）"""
    sql = """
        SELECT row_code, row_name, report_type, applicable_standard,
               indent_level, is_total_row, formula, sort_order
        FROM report_config
        WHERE is_deleted = false
    """
    params: dict = {"lim": limit}
    if filters.get("report_type"):
        sql += " AND report_type = :rt"
        params["rt"] = filters["report_type"]
    if filters.get("applicable_standard"):
        sql += " AND applicable_standard = :std"
        params["std"] = filters["applicable_standard"]
    if filters.get("has_formula") is True:
        sql += " AND formula IS NOT NULL AND formula != ''"
    elif filters.get("has_formula") is False:
        sql += " AND (formula IS NULL OR formula = '')"
    if filters.get("row_name"):
        sql += " AND row_name LIKE :rn"
        params["rn"] = f"%{filters['row_name']}%"
    sql += " ORDER BY applicable_standard, report_type, sort_order LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "row_code": r[0],
            "row_name": r[1],
            "report_type": r[2],
            "applicable_standard": r[3],
            "indent_level": r[4],
            "is_total_row": r[5],
            "formula": r[6],
            "sort_order": r[7],
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["row_code", "row_name", "report_type", "applicable_standard", "indent_level", "is_total_row", "formula", "sort_order"],
        "total": len(rows),
    }


async def _query_workhours(db, pid, year, filters, limit):
    """工时记录（work_hours）"""
    sql = """
        SELECT work_date, hours, description, status, staff_id, project_id, created_at
        FROM work_hours
        WHERE is_deleted = false
    """
    params: dict = {"lim": limit}
    # 可选项目过滤（pid 可能为空字符串）
    if pid:
        sql += " AND project_id = :pid"
        params["pid"] = pid
    if year:
        sql += " AND EXTRACT(YEAR FROM work_date) = :y"
        params["y"] = year
    if filters.get("staff_id"):
        sql += " AND staff_id = :sid"
        params["sid"] = filters["staff_id"]
    if filters.get("status"):
        sql += " AND status = :st"
        params["st"] = filters["status"]
    if filters.get("date_from"):
        sql += " AND work_date >= :df"
        params["df"] = filters["date_from"]
    if filters.get("date_to"):
        sql += " AND work_date <= :dt"
        params["dt"] = filters["date_to"]
    sql += " ORDER BY work_date DESC LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "work_date": str(r[0]) if r[0] else None,
            "hours": float(r[1]) if r[1] is not None else 0,
            "description": r[2],
            "status": r[3],
            "staff_id": str(r[4]) if r[4] else None,
            "project_id": str(r[5]) if r[5] else None,
            "created_at": str(r[6]) if r[6] else None,
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["work_date", "hours", "description", "status", "staff_id"],
        "total": len(rows),
    }


# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.6 — 自定义查询模板 CRUD 端点
# ──────────────────────────────────────────────────────────────────────────


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    data_source: str = Field(..., min_length=1, max_length=50)
    config: dict
    scope: Literal["private", "global"] = "private"


class TemplateUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    data_source: str | None = None
    config: dict | None = None
    scope: Literal["private", "global"] | None = None


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
    return {
        "id": str(tpl.id),
        "name": tpl.name,
        "description": tpl.description,
        "data_source": tpl.data_source,
        "config": tpl.config or {},
        "scope": tpl.scope,
        "created_by": str(tpl.created_by),
        "is_owner": tpl.created_by == current_user_id,
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
    }


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
    """创建查询模板。"""
    tpl = CustomQueryTemplate(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        data_source=body.data_source,
        config=body.config,
        scope=body.scope,
        created_by=current_user.id,
    )
    db.add(tpl)
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
    user_role = getattr(current_user, "role", "")
    if tpl.created_by != current_user.id and user_role != "admin":
        raise HTTPException(status_code=403, detail={"error_code": "ONLY_OWNER_CAN_UPDATE"})

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
    """删除模板（仅创建者或 admin）。"""
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})
    user_role = getattr(current_user, "role", "")
    if tpl.created_by != current_user.id and user_role != "admin":
        raise HTTPException(status_code=403, detail={"error_code": "ONLY_OWNER_OR_ADMIN_CAN_DELETE"})
    await db.delete(tpl)
    await db.commit()
    return None
