"""B1-1 / B1-2 A、B类鉴证业务风险评估表 — 专属渲染策略.

component_type = "b1-risk-assessment"

源模板是**分章节固定问卷表**（事项 | 事实或描述 | 说明或附件），而非通用风险矩阵：
- B1-1 承接：9 章 89 项固定评估事项
- B1-2 保持：9 章 94 项固定评估事项（含上年度项目团队/风险等级承继）

变体（由 wp_code 判定）：
- acceptance (B1-1 承接)
- retention  (B1-2 保持)

预置事项来自 backend/app/data/b1_risk_assessment_presets.json（脚本从源 xlsx 提取）。
数据持久化在 checklist_responses 表，item_id 前缀 `b1risk-`。

item_id 方案（section/item 索引稳定，preset 从源模板固定提取）：
- 事项答案:   b1risk-a-{si}-{ii}   (remark = 值；choice 存 是/否/N/A)
- 事项说明:   b1risk-n-{si}-{ii}   (remark = 说明或附件文本)
- 头部信息:   b1risk-hdr-{field}   (remark = 值)
- 综合结论:   b1risk-overall-conclusion (conclusion = 枚举值)
- 综合说明:   b1risk-overall-explanation (remark = 文本)
"""

from __future__ import annotations

import json
import logging
import os

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

_PRESET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # app/
    "data",
    "b1_risk_assessment_presets.json",
)

# preset 缓存（模块级，mtime 失效）
_preset_cache: dict | None = None
_preset_mtime: float = 0.0

# 头部字段（承接/保持略有差异）
_HEADER_FIELDS_ACCEPTANCE = [
    {"field": "audited_entity", "label": "被审计单位"},
    {"field": "office", "label": "所属办公室"},
    {"field": "partner", "label": "拟承接合伙人"},
    {"field": "manager", "label": "项目负责经理"},
]
_HEADER_FIELDS_RETENTION = [
    {"field": "audited_entity", "label": "被审计单位"},
    {"field": "office", "label": "所属办公室"},
    {"field": "partner", "label": "项目合伙人"},
    {"field": "manager", "label": "项目负责经理"},
]

_CONCLUSION_OPTIONS_ACCEPTANCE = [
    {"value": "low_risk", "label": "低风险—可承接", "class": "success"},
    {"value": "medium_risk", "label": "中风险—需进一步评估审批", "class": "warning"},
    {"value": "high_risk", "label": "高风险—建议拒绝承接", "class": "danger"},
]
_CONCLUSION_OPTIONS_RETENTION = [
    {"value": "low_risk", "label": "低风险—继续保持", "class": "success"},
    {"value": "medium_risk", "label": "中风险—需进一步评估审批", "class": "warning"},
    {"value": "high_risk", "label": "高风险—建议解除业务关系", "class": "danger"},
]


def _load_presets() -> dict:
    """加载预置事项 JSON（mtime 热重载缓存）."""
    global _preset_cache, _preset_mtime
    try:
        mtime = os.path.getmtime(_PRESET_PATH)
        if _preset_cache is None or mtime != _preset_mtime:
            with open(_PRESET_PATH, encoding="utf-8") as f:
                _preset_cache = json.load(f)
            _preset_mtime = mtime
    except Exception as e:  # noqa: BLE001
        logger.warning("B1 风险评估预置加载失败: %s", e)
        return {}
    return _preset_cache or {}


def _detect_variant(wp_code: str, sheet_name: str = "") -> str:
    """判定变体。优先 wp_code(B1-2→retention)，回退 sheet_name(含"保持"→retention)。

    多 sheet 工作簿中承接/保持两张表可能共用父 wp_code=B1，故补 sheet_name 兜底。
    """
    code = (wp_code or "").upper().replace(" ", "")
    if code.startswith("B1-2"):
        return "retention"
    if code.startswith("B1-1"):
        return "acceptance"
    # wp_code 无法判定（如父码 B1）时按 sheet 名兜底
    if "保持" in (sheet_name or ""):
        return "retention"
    return "acceptance"


async def render(ctx: RenderContext) -> dict | None:
    """B1-1 / B1-2 风险评估表渲染策略."""
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    sheet_name = getattr(ctx.classification, "sheet_name", "") or ""
    variant = _detect_variant(ctx.wp_code, sheet_name)
    preset_code = "B1-2" if variant == "retention" else "B1-1"
    presets = _load_presets()
    preset_data = presets.get(preset_code, {"sections": []})

    # ─── 1. 加载 checklist_responses (item_id LIKE 'b1risk-%') ───────────
    responses: dict[str, tuple[str | None, str | None]] = {}  # item_id -> (conclusion, remark)
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'b1risk-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses[row.item_id] = (row.conclusion, row.remark)
    except Exception as e:  # noqa: BLE001
        logger.warning("B1 风险评估 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 2. 组装 sections（预置事项 + 已保存答案）────────────────────────
    sections: list[dict] = []
    for si, sec in enumerate(preset_data.get("sections", [])):
        items: list[dict] = []
        for ii, it in enumerate(sec.get("items", [])):
            ans = responses.get(f"b1risk-a-{si}-{ii}")
            note = responses.get(f"b1risk-n-{si}-{ii}")
            items.append(
                {
                    "key": f"{si}-{ii}",
                    "item": it["item"],
                    "kind": it.get("kind", "text"),
                    "answer": (ans[1] if ans else "") or "",
                    "note": (note[1] if note else "") or "",
                }
            )
        sections.append({"title": sec.get("title", ""), "items": items})

    # ─── 3. 头部信息 ────────────────────────────────────────────────────
    header_fields = (
        _HEADER_FIELDS_RETENTION if variant == "retention" else _HEADER_FIELDS_ACCEPTANCE
    )
    header: dict[str, str] = {}
    for hf in header_fields:
        hd = responses.get(f"b1risk-hdr-{hf['field']}")
        header[hf["field"]] = (hd[1] if hd else "") or ""

    # ─── 4. 综合结论 ────────────────────────────────────────────────────
    oc = responses.get("b1risk-overall-conclusion")
    oe = responses.get("b1risk-overall-explanation")
    overall = {
        "conclusion": (oc[0] if oc else "") or "",
        "explanation": (oe[1] if oe else "") or "",
    }

    # ─── 5. 项目上下文（预填被审计单位）────────────────────────────────
    project_context = await _load_project_context(project_id, db)
    if not header.get("audited_entity") and project_context.get("client_name"):
        header["audited_entity"] = project_context["client_name"]

    # ─── 6. 上年度风险结论承继（保持场景，best-effort）──────────────────
    prior_year = None
    if variant == "retention":
        prior_year = await _load_prior_year_conclusion(project_id, db, project_context)

    # ─── 7. 跨表联动：读同工作簿 B1-5 KAA 检查结论（同 wp_id，item_id 前缀 b1kaa-）───
    kaa_hint = await _load_kaa_hint(wp_id, db)

    # ─── 8. 跨表联动：读同工作簿 B1-3 业务评价表 综合客户风险（b1eval-client-overall_client_risk）───
    eval_client_risk = await _load_eval_client_risk(wp_id, db)

    return {
        "variant": variant,
        "source_sheet": preset_data.get("source_sheet", ""),
        "sections": sections,
        "header_fields": header_fields,
        "header": header,
        "overall": overall,
        "conclusion_options": (
            _CONCLUSION_OPTIONS_RETENTION
            if variant == "retention"
            else _CONCLUSION_OPTIONS_ACCEPTANCE
        ),
        "project_context": project_context,
        "prior_year": prior_year,
        "kaa_hint": kaa_hint,
        "eval_client_risk": eval_client_risk,
    }


async def _load_eval_client_risk(wp_id, db) -> str | None:
    """读同工作簿 B1-3 业务评价表 综合客户风险（b1eval-client-overall_client_risk）。

    返回 high/medium/low 或 None（未填）。供 B1-1/B1-2 与总体风险结论一致性校验。
    """
    try:
        row = (await db.execute(
            sa.text(
                "SELECT conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = 'b1eval-client-overall_client_risk' LIMIT 1"
            ),
            {"wp_id": str(wp_id)},
        )).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("B1 风险评估读取 B1-3 客户风险联动失败 wp_id=%s: %s", wp_id, e)
        return None
    return (row.conclusion if row and row.conclusion else None) or None


async def _load_kaa_hint(wp_id, db) -> dict | None:
    """读同工作簿 B1-5 KAA 检查结论（同 wp_id 下 item_id 前缀 b1kaa-）。

    手工覆盖 b1kaa-overall-conclusion 优先；否则一节任一 b1kaa-standard-% 为"是"即达到。
    未填任何 KAA 项返回 None（前端不显示提示）。
    返回: {"reached": bool, "manual": bool}
    """
    try:
        rows = (await db.execute(
            sa.text(
                "SELECT item_id, conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND (item_id = 'b1kaa-overall-conclusion' "
                "OR item_id LIKE 'b1kaa-standard-%')"
            ),
            {"wp_id": str(wp_id)},
        )).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("B1 风险评估读取 KAA 联动失败 wp_id=%s: %s", wp_id, e)
        return None
    if not rows:
        return None
    manual = None
    reached = False
    for r in rows:
        if r.item_id == "b1kaa-overall-conclusion":
            manual = r.conclusion
        elif r.conclusion == "是":
            reached = True
    if manual:
        return {"reached": manual == "reached", "manual": True}
    return {"reached": reached, "manual": False}


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
            project_context["industry"] = proj_row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("B1 风险评估 project context 查询失败: %s", e)
    return project_context


async def _load_prior_year_conclusion(project_id, db, project_context) -> dict | None:
    """跨年度续审：查同客户上一年度项目的 B1-1/B1-2 综合结论（best-effort）.

    找到同 client_name 且 audit_year = 本年-1 的项目，读其 B1 风险评估结论。
    找不到返回 None（前端显示"无上年数据，请手工填写"）。
    """
    client_name = project_context.get("client_name")
    period = project_context.get("audit_period", "")
    if not client_name or not period:
        return None
    try:
        cur_year = int(period.replace("年度", "").strip())
    except (ValueError, TypeError):
        return None
    prior_year = cur_year - 1
    try:
        # 找上一年度同客户项目
        proj_result = await db.execute(
            sa.text(
                "SELECT id FROM projects "
                "WHERE client_name = :cn AND audit_year = :yr "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"cn": client_name, "yr": prior_year},
        )
        prior_proj = proj_result.fetchone()
        if not prior_proj:
            return None
        # 读其 B1 风险评估综合结论
        conc_result = await db.execute(
            sa.text(
                "SELECT cr.conclusion FROM checklist_responses cr "
                "WHERE cr.project_id = :pid "
                "AND cr.item_id = 'b1risk-overall-conclusion' "
                "LIMIT 1"
            ),
            {"pid": str(prior_proj.id)},
        )
        conc_row = conc_result.fetchone()
        if conc_row and conc_row.conclusion:
            return {"year": prior_year, "conclusion": conc_row.conclusion}
    except Exception as e:  # noqa: BLE001
        logger.warning("B1 风险评估上年结论查询失败: %s", e)
    return None
