"""B1-3 业务评价表 — 专属渲染策略.

component_type = "b1-3-business-evaluation"

源模板结构（业务评价表，适用全部项目立项，含简化立项程序）：
- 一、业务基本信息（客户名称/地址/项目名称/业务分类/行业/控股股东/分子公司/关联方/关键成员/财务人员/会计准则/审计目的/收费/是否KAA/前任沟通/承接渠道）
- 二、对客户的评价（诚信/经营/财务 描述 + 高中低风险评价 → 客户风险评价结论）
- 三、确定审计的前提条件是否存在（3 项 是/否 判断）
- 四、项目组的独立性及胜任能力（方法论 + 4 项 是/否 判断）
- 五、预计收取的费用及可收回比率（textarea）
- 六、业务评价结论（关键要素结论 + 承接承做意见 可以承接/可以保持）

自动结论提示：独立性存在问题 或 任一客户风险=高 → 提示需进一步评估/审批。

数据持久化 checklist_responses，item_id 前缀 `b1eval-`：
- 基本信息:  b1eval-basic-{field}          (remark)
- 客户评价:  b1eval-client-{rowId}          (textarea→remark / risk→conclusion 高中低)
- 前提条件:  b1eval-pre-{itemId}            (conclusion 是/否/N/A) + -note(remark)
- 独立性:    b1eval-indep-{itemId}          (conclusion 是/否/N/A) + -note(remark)
- 费用:      b1eval-fee                     (remark)
- 结论要素:  b1eval-elem-{elemId}           (remark)
- 承接意见:  b1eval-opinion                 (conclusion accept/retain/reject)
- 意见说明:  b1eval-opinion-note            (remark)
- 签名:      b1eval-sign-{partner|date}     (remark)
"""

from __future__ import annotations

import json
import logging
import os

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # app/
    "data",
    "b1_3_evaluation_schema.json",
)

_schema_cache: dict | None = None
_schema_mtime: float = 0.0


def _load_schema() -> dict:
    global _schema_cache, _schema_mtime
    try:
        mtime = os.path.getmtime(_SCHEMA_PATH)
        if _schema_cache is None or mtime != _schema_mtime:
            with open(_SCHEMA_PATH, encoding="utf-8") as f:
                _schema_cache = json.load(f)
            _schema_mtime = mtime
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-3 业务评价表 schema 加载失败: %s", e)
        return {}
    return _schema_cache or {}


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    schema = _load_schema()

    # ─── 加载已存响应 ───
    responses: dict[str, tuple[str | None, str | None]] = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'b1eval-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses[row.item_id] = (row.conclusion, row.remark)
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-3 业务评价表 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    def _conc(item_id: str) -> str:
        v = responses.get(item_id)
        return (v[0] if v else "") or ""

    def _remark(item_id: str) -> str:
        v = responses.get(item_id)
        return (v[1] if v else "") or ""

    # ─── 组装 values ───
    values: dict[str, dict] = {}
    high_client_risk = False
    independence_issue = False
    for sec in schema.get("sections", []):
        sk = sec.get("key")
        if sk == "basic":
            for f in sec.get("fields", []):
                values[f"basic-{f['field']}"] = {"value": _remark(f"b1eval-basic-{f['field']}")}
        elif sk == "client_eval":
            for r in sec.get("rows", []):
                rid = r["id"]
                if r["type"] == "risk":
                    val = _conc(f"b1eval-client-{rid}")
                    values[f"client-{rid}"] = {"value": val}
                    if val == "high":
                        high_client_risk = True
                else:
                    values[f"client-{rid}"] = {"value": _remark(f"b1eval-client-{rid}")}
        elif sk in ("precondition", "independence"):
            prefix = "pre" if sk == "precondition" else "indep"
            for it in sec.get("items", []):
                iid = it["id"]
                conc = _conc(f"b1eval-{prefix}-{iid}")
                values[f"{prefix}-{iid}"] = {
                    "value": conc,
                    "note": _remark(f"b1eval-{prefix}-{iid}-note"),
                }
                if sk == "independence" and iid == "has_independence_issue" and conc == "是":
                    independence_issue = True
        elif sk == "fee":
            values["fee"] = {"value": _remark("b1eval-fee")}
            # 结构化费用字段（前端 InputNumber 独立存储）
            values["fee-estimated_fee"] = {"value": _remark("b1eval-fee-estimated_fee")}
            values["fee-estimated_cost"] = {"value": _remark("b1eval-fee-estimated_cost")}
            values["fee-recover_rate"] = {"value": _remark("b1eval-fee-recover_rate")}
        elif sk == "conclusion":
            for el in sec.get("key_elements", []):
                values[f"elem-{el['id']}"] = {"value": _remark(f"b1eval-elem-{el['id']}")}

    opinion = _conc("b1eval-opinion")
    opinion_note = _remark("b1eval-opinion-note")
    sign_partner = _remark("b1eval-sign-partner")
    sign_date = _remark("b1eval-sign-date")

    # ─── 自动风险提示 ───
    risk_alert = ""
    if independence_issue:
        risk_alert = "独立性存在问题，须在承接前评估应对措施或考虑拒绝承接。"
    elif high_client_risk:
        risk_alert = "存在高风险客户评价项，须进一步评估并履行审批程序。"

    # ─── 项目上下文预填（客户名 + 行业）───
    project_context = await _load_project_context(project_id, db)
    if not values.get("basic-client_name", {}).get("value") and project_context.get("client_name"):
        values.setdefault("basic-client_name", {})["value"] = project_context["client_name"]
    if not values.get("basic-industry", {}).get("value") and project_context.get("industry"):
        values.setdefault("basic-industry", {})["value"] = project_context["industry"]

    # ─── 跨表联动：读同工作簿 B1-1/B1-2 总体风险结论（b1risk-overall-conclusion）───
    risk_assessment_conclusion = await _load_risk_conclusion(ctx.wp_id, db)

    return {
        # 供前端「在线编辑」双模式定位 OnlyOffice tab（须与源 xlsx tab 名一致）
        "source_sheet": (getattr(ctx.classification, "sheet_name", "") or "业务评价表B1-3"),
        "sections": schema.get("sections", []),
        "opinion_options": schema.get("opinion_options", []),
        "risk_options": schema.get("risk_options", []),
        "values": values,
        "opinion": opinion,
        "opinion_note": opinion_note,
        "sign_partner": sign_partner,
        "sign_date": sign_date,
        "risk_alert": risk_alert,
        "project_context": project_context,
        "risk_assessment_conclusion": risk_assessment_conclusion,
    }


async def _load_risk_conclusion(wp_id, db) -> str | None:
    """读同工作簿 B1-1/B1-2 风险评估总体结论（b1risk-overall-conclusion）。

    返回 low_risk/medium_risk/high_risk 或 None。供 B1-3 综合客户风险一致性提示。
    """
    try:
        row = (await db.execute(
            sa.text(
                "SELECT conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = 'b1risk-overall-conclusion' LIMIT 1"
            ),
            {"wp_id": str(wp_id)},
        )).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-3 读取 B1-1 风险结论联动失败 wp_id=%s: %s", wp_id, e)
        return None
    return (row.conclusion if row and row.conclusion else None) or None


async def _load_project_context(project_id, db) -> dict:
    project_context: dict = {"client_name": "", "audit_period": "", "industry": ""}
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            if proj_row.audit_year:
                project_context["audit_period"] = f"{proj_row.audit_year}年度"
            project_context["industry"] = proj_row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-3 业务评价表 project context 查询失败: %s", e)
    return project_context
