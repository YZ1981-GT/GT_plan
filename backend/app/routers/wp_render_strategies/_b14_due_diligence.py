"""B1-4 尽职调查（预备调查）报告 — 专属渲染策略.

component_type = "b1-4-due-diligence-report"
13 章折叠卡片（textarea/table/mixed）+ 签字区 + 左侧导航 + 变体切换。
变体：standard(标准版,全13章) / simplified(简化版,隐藏ch11+ch12)。
数据持久化在 checklist_responses 表，item_id 前缀 `b14-`。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─── 13 章节元数据 ──────────────────────────────────────────────────────────
CHAPTERS_META: list[dict] = [
    {"id": "ch1", "number": 1, "title": "序言", "type": "textarea", "variant_only": None},
    {"id": "ch2", "number": 2, "title": "报告概要", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "purpose", "title": "调查目的", "type": "textarea"},
         {"id": "scope", "title": "调查范围", "type": "textarea"},
         {"id": "method", "title": "调查方法", "type": "textarea"},
         {"id": "team", "title": "项目团队", "type": "table", "table_id": "team"},
     ]},
    {"id": "ch3", "number": 3, "title": "释义", "type": "textarea", "variant_only": None},
    {"id": "ch4", "number": 4, "title": "公司基本情况", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "history", "title": "历史沿革", "type": "textarea"},
         {"id": "organization", "title": "组织架构", "type": "textarea"},
         {"id": "shareholders", "title": "股东信息", "type": "table", "table_id": "shareholders"},
         {"id": "hr", "title": "人力资源", "type": "table", "table_id": "hr"},
     ]},
    {"id": "ch5", "number": 5, "title": "公司经营情况", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "business", "title": "主营业务", "type": "textarea"},
         {"id": "customers", "title": "主要客户", "type": "table", "table_id": "customers"},
         {"id": "suppliers", "title": "主要供应商", "type": "table", "table_id": "suppliers"},
         {"id": "market_position", "title": "行业地位", "type": "textarea"},
     ]},
    {"id": "ch6", "number": 6, "title": "财务信息分析", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "balance_sheet", "title": "资产负债", "type": "textarea"},
         {"id": "income", "title": "利润", "type": "textarea"},
         {"id": "cashflow", "title": "现金流", "type": "textarea"},
         {"id": "ratios", "title": "关键比率", "type": "textarea"},
     ]},
    {"id": "ch7", "number": 7, "title": "同行业比较", "type": "table", "variant_only": None,
     "table_id": "industry_comparison"},
    {"id": "ch8", "number": 8, "title": "税项", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "tax_status", "title": "纳税情况", "type": "textarea"},
         {"id": "tax_benefit", "title": "税收优惠", "type": "textarea"},
     ]},
    {"id": "ch9", "number": 9, "title": "内部控制", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "control_env", "title": "控制环境", "type": "textarea"},
         {"id": "risk_assess", "title": "风险评估", "type": "textarea"},
         {"id": "control_act", "title": "控制活动", "type": "textarea"},
     ]},
    {"id": "ch10", "number": 10, "title": "关联方关系及交易", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "related_parties", "title": "关联方清单", "type": "table", "table_id": "related_parties"},
         {"id": "related_transactions", "title": "关联交易", "type": "table", "table_id": "related_transactions"},
     ]},
    {"id": "ch11", "number": 11, "title": "上市条件分析", "type": "mixed", "variant_only": "standard",
     "sections": [
         {"id": "ipo_general", "title": "发行条件", "type": "textarea"},
         {"id": "mainboard", "title": "主板条件", "type": "textarea"},
         {"id": "star_market", "title": "科创板条件", "type": "textarea"},
     ]},
    {"id": "ch12", "number": 12, "title": "财务尽职调查的结果", "type": "textarea", "variant_only": "standard"},
    {"id": "ch13", "number": 13, "title": "公司存在的主要问题及建议", "type": "mixed", "variant_only": None,
     "sections": [
         {"id": "issues", "title": "主要问题", "type": "textarea"},
         {"id": "suggestions", "title": "建议措施", "type": "textarea"},
     ]},
]

# 签字区字段
SIGNATURE_FIELDS = ["partner", "partner_date", "manager", "manager_date", "report_date"]


async def render(ctx: RenderContext) -> dict | None:
    """B1-4 尽职调查报告渲染策略.

    返回:
    {
        "chapters": { "ch1": {...}, "ch2": {...}, ... },
        "variant": "standard" | "simplified",
        "signature": { "partner": null, ... },
        "project_context": { "client_name": "", "industry": "", "audit_period": "", "firm_name": "" }
    }
    """
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    # ─── 1. 加载 checklist_responses (item_id LIKE 'b14-%') ─────────────
    responses: dict[str, tuple[str | None, str | None]] = {}  # item_id -> (conclusion, remark)
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'b14-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses[row.item_id] = (row.conclusion, row.remark)
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-4 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 2. 解析 variant ────────────────────────────────────────────────
    variant = "standard"
    meta_variant = responses.get("b14-meta-variant")
    if meta_variant and meta_variant[0] in ("standard", "simplified"):
        variant = meta_variant[0]

    # ─── 3. 解析 signature ──────────────────────────────────────────────
    signature: dict[str, str | None] = {}
    for field in SIGNATURE_FIELDS:
        sig_key = f"b14-signature-{field}"
        sig_data = responses.get(sig_key)
        signature[field] = sig_data[0] if sig_data else None

    # ─── 4. 组装 chapters ───────────────────────────────────────────────
    chapters: dict[str, dict] = {}
    for meta in CHAPTERS_META:
        ch_id = meta["id"]
        ch_num = meta["number"]
        ch_type = meta["type"]
        visible = True
        if meta["variant_only"] == "standard" and variant == "simplified":
            visible = False

        ch_data: dict = {
            "id": ch_id,
            "title": meta["title"],
            "type": ch_type,
            "visible": visible,
        }

        if ch_type == "textarea":
            # b14-ch{N}-content → remark
            content_key = f"b14-ch{ch_num}-content"
            content_data = responses.get(content_key)
            ch_data["content"] = content_data[1] if content_data else None

        elif ch_type == "table":
            # b14-ch{N}-table-{tableId} → remark (JSON)
            table_id = meta.get("table_id", "")
            table_key = f"b14-ch{ch_num}-table-{table_id}"
            table_data = responses.get(table_key)
            rows: list[dict] = []
            if table_data and table_data[1]:
                try:
                    parsed = json.loads(table_data[1])
                    if isinstance(parsed, list):
                        rows = parsed
                except (json.JSONDecodeError, TypeError):
                    logger.warning("B1-4 ch%d table JSON 解析失败", ch_num)
            ch_data["rows"] = rows
            ch_data["table_id"] = table_id

        elif ch_type == "mixed":
            # 各子节
            sections: list[dict] = []
            for sec_meta in meta.get("sections", []):
                sec_id = sec_meta["id"]
                sec_type = sec_meta["type"]
                sec_data: dict = {
                    "id": sec_id,
                    "title": sec_meta["title"],
                    "type": sec_type,
                }

                if sec_type == "textarea":
                    # b14-ch{N}-{section_id} → remark
                    sec_key = f"b14-ch{ch_num}-{sec_id}"
                    sec_resp = responses.get(sec_key)
                    sec_data["content"] = sec_resp[1] if sec_resp else None
                elif sec_type == "table":
                    # b14-ch{N}-table-{tableId} → remark (JSON)
                    table_id = sec_meta.get("table_id", sec_id)
                    table_key = f"b14-ch{ch_num}-table-{table_id}"
                    table_resp = responses.get(table_key)
                    rows = []
                    if table_resp and table_resp[1]:
                        try:
                            parsed = json.loads(table_resp[1])
                            if isinstance(parsed, list):
                                rows = parsed
                        except (json.JSONDecodeError, TypeError):
                            logger.warning("B1-4 ch%d section %s table JSON 解析失败", ch_num, sec_id)
                    sec_data["rows"] = rows
                    sec_data["table_id"] = table_id

                sections.append(sec_data)
            ch_data["sections"] = sections

        chapters[ch_id] = ch_data

    # ─── 5. 加载项目上下文 ──────────────────────────────────────────────
    project_context = await _load_project_context(project_id, db)

    # ─── 6. 财务指标预填（ch6 用） ──────────────────────────────────────────
    financial_indicators = await _load_financial_indicators(project_id, db, project_context)

    # ─── 7. 关联方清单预填（ch10 用） ────────────────────────────────────────
    related_parties = await _load_related_parties(project_id, db)

    return {
        # 供前端「在线编辑」双模式定位 OnlyOffice tab（须与源 xlsx tab 名一致）
        "source_sheet": (getattr(ctx.classification, "sheet_name", "") or "尽职调查报告B1-4"),
        "chapters": chapters,
        "variant": variant,
        "signature": signature,
        "project_context": project_context,
        "financial_indicators": financial_indicators,
        "related_parties": related_parties,
    }


async def _load_project_context(project_id, db) -> dict:
    """从 projects 表加载项目上下文信息."""
    project_context: dict = {
        "client_name": "",
        "industry": "",
        "audit_period": "",
        "firm_name": "致同会计师事务所（特殊普通合伙）",
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            year = proj_row.audit_year
            if year:
                project_context["audit_period"] = f"{year}年度"
            # business_category 作为 industry 的近似值
            project_context["industry"] = proj_row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-4 project context 查询失败: %s", e)
    return project_context


async def _load_financial_indicators(project_id, db, project_context: dict) -> dict:
    """从 trial_balance 取关键财务指标，供 ch6（财务信息分析）预填.

    返回: {
        "total_assets": float,       # 资产总计 (1xxx 期末)
        "total_liabilities": float,  # 负债总计 (2xxx 期末)
        "equity": float,             # 所有者权益 (资产-负债)
        "revenue": float,            # 营业收入 (6001)
        "cost_of_sales": float,      # 营业成本 (6401)
        "net_profit": float,         # 净利润 (近似: 收入-成本, 粗算)
        "cash": float,               # 货币资金 (1001+1002+1012)
        "receivables": float,        # 应收账款 (1122)
        "inventory": float,          # 存货 (1401+1402+1403+1405)
        "fixed_assets": float,       # 固定资产 (1601-1602)
    }
    """
    indicators: dict = {}
    try:
        year = None
        period = project_context.get("audit_period", "")
        if period:
            try:
                year = int(period.replace("年度", "").strip())
            except (ValueError, TypeError):
                pass
        if not year:
            return indicators

        # 一次查询取全部需要的科目大类
        result = await db.execute(
            sa.text("""
                SELECT standard_account_code,
                       COALESCE(audited_amount, unadjusted_amount, 0) AS amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
            """),
            {"pid": str(project_id), "year": year},
        )
        rows = result.fetchall()

        # 按科目前缀汇总
        sums: dict[str, float] = {}
        for row in rows:
            code = row.standard_account_code or ""
            amt = float(row.amount or 0)
            for prefix in ("1001", "1002", "1012", "1122", "1401", "1402", "1403", "1405",
                           "1601", "1602", "6001", "6401"):
                if code.startswith(prefix):
                    sums[prefix] = sums.get(prefix, 0) + amt
            # 资产大类(1xxx) / 负债大类(2xxx)
            if code and code[0] == "1":
                sums["assets"] = sums.get("assets", 0) + amt
            elif code and code[0] == "2":
                sums["liabilities"] = sums.get("liabilities", 0) + amt

        indicators["total_assets"] = round(sums.get("assets", 0), 2)
        indicators["total_liabilities"] = round(abs(sums.get("liabilities", 0)), 2)
        indicators["equity"] = round(indicators["total_assets"] - indicators["total_liabilities"], 2)
        indicators["revenue"] = round(sums.get("6001", 0), 2)
        indicators["cost_of_sales"] = round(sums.get("6401", 0), 2)
        indicators["net_profit"] = round(indicators["revenue"] - indicators["cost_of_sales"], 2)
        indicators["cash"] = round(
            sums.get("1001", 0) + sums.get("1002", 0) + sums.get("1012", 0), 2
        )
        indicators["receivables"] = round(sums.get("1122", 0), 2)
        indicators["inventory"] = round(
            sums.get("1401", 0) + sums.get("1402", 0)
            + sums.get("1403", 0) + sums.get("1405", 0),
            2,
        )
        indicators["fixed_assets"] = round(
            sums.get("1601", 0) - abs(sums.get("1602", 0)), 2
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-4 财务指标查询失败: %s", e)
    return indicators


async def _load_related_parties(project_id, db) -> list[dict]:
    """从 related_party_registry 加载关联方清单，供 ch10（关联方关系及交易）预填.

    返回: [{"name": "...", "relation_type": "..."}, ...]
    """
    parties: list[dict] = []
    try:
        result = await db.execute(
            sa.text(
                "SELECT name, relation_type, detail "
                "FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false "
                "AND name IS NOT NULL AND name <> '' "
                "ORDER BY name"
            ),
            {"pid": str(project_id)},
        )
        for row in result.fetchall():
            parties.append({
                "name": row.name or "",
                "relation_type": row.relation_type or "",
                "detail": row.detail if hasattr(row, "detail") else None,
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-4 关联方清单查询失败: %s", e)
    return parties
