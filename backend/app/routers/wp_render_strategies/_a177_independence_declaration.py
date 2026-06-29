"""A17-7 审计项目团队成员独立性声明书 — 专属渲染策略.

component_type = "a17-7-independence-declaration"
双变体(variant)：A17-7→team(全员独立性声明), A17-7A→committee(独立性判断委员会声明)
两者共用一个 componentType，通过 wp_code 自动判别 variant。

数据结构：
  variant + meta_info + declaration_text + period_data
  + team_sign_table + partner_section + threat_records
  + guidance_notes + project_context

数据持久化在 checklist_responses 表 (item_id LIKE '{prefix}%')。
prefix = "a177-" (team) | "a177a-" (committee)
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─── 常量 ──────────────────────────────────────────────────────────────────────

TEAM_DECLARATION_TEXT = (
    "本人确认，在本项目的业务期间及财务报告期间内，"
    "本人及直系亲属与被审计单位之间不存在可能影响独立性的利害关系，"
    "包括但不限于经济利益、贷款与担保、商业关系、家庭与私人关系等。"
    "如存在上述情形，已在附件中如实披露并采取了适当防范措施。"
)

COMMITTEE_DECLARATION_TEXT = (
    "本人作为专业技术委员会审核委员，确认在参与本项目的独立性判断过程中，"
    "本人与被审计单位之间不存在可能影响判断客观性的利害关系。"
    "如存在上述情形，已在附件中如实披露并采取了适当防范措施。"
)

GUIDANCE_NOTES = [
    "1. 独立性声明书应在业务承接阶段签署，并在项目执行过程中如有变化及时更新。",
    "2. 经济利益包括直接经济利益和重大间接经济利益，含股票、债券、基金等投资。",
    "3. 贷款与担保包括项目组成员或其近亲属与客户之间的贷款或担保关系。",
    "4. 商业关系是指与客户存在的商品购销、服务提供等可能产生自身利益威胁的关系。",
    "5. 如发现独立性问题，应及时向项目合伙人和质量管理部门报告，采取消除或降低威胁的措施。",
]


def _determine_variant(wp_code: str) -> tuple[str, str]:
    """根据 wp_code 确定 variant 和 item_id 前缀."""
    if wp_code and wp_code.upper() == "A17-7A":
        return "committee", "a177a-"
    return "team", "a177-"


def _safe_parse_json(raw: str | None) -> dict | list | None:
    """安全解析 JSON，失败返回 None."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


_DEFAULT_COMMITMENT_ITEMS = [
    {"id": "economic", "label": "本人及直系亲属不持有被审计单位及其关联方的直接或重大间接经济利益（包括股票、债券、基金等金融投资）"},
    {"id": "loan", "label": "本人及直系亲属与被审计单位及其关联方之间不存在贷款或担保关系"},
    {"id": "business", "label": "本人及直系亲属与被审计单位及其关联方之间不存在可能产生自身利益威胁的商业关系"},
    {"id": "family", "label": "本人的近亲属未在被审计单位及其关联方担任董事、经理或特定会计岗位"},
    {"id": "employment", "label": "本人未曾在被审计单位担任董事、经理或特定会计岗位（或已满足冷却期要求）"},
]


def _build_commitment_items(responses: dict) -> list[dict]:
    """构建承诺事项列表，合并已保存的应答."""
    items = []
    for default in _DEFAULT_COMMITMENT_ITEMS:
        cid = default["id"]
        saved = responses.get(cid, {})
        items.append({
            "id": cid,
            "label": default["label"],
            "answer": saved.get("answer") if saved else None,
            "explanation": saved.get("explanation") if saved else None,
        })
    return items


async def _load_team_members(project_id, db) -> list[dict]:
    """查询 project_assignments JOIN users 获取团队成员名单.

    返回 [{name: str}] 列表。
    """
    members: list[dict] = []
    try:
        result = await db.execute(
            sa.text(
                "SELECT u.display_name "
                "FROM project_assignments pa "
                "JOIN users u ON pa.staff_id = u.id "
                "WHERE pa.project_id = :pid "
                "ORDER BY pa.created_at"
            ),
            {"pid": str(project_id)},
        )
        for row in result.fetchall():
            members.append({"name": row.display_name or ""})
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-7 team members 查询失败 project_id=%s: %s", project_id, e)
    return members


async def render(ctx: RenderContext) -> dict | None:
    """A17-7 独立性声明书渲染策略.

    返回 {variant, meta_info, declaration_text, period_data,
          team_sign_table, partner_section, threat_records,
          guidance_notes, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db
    wp_code = ctx.wp_code or ""

    # ─── 1. 确定 variant 和 prefix ────────────────────────────────────────
    variant, prefix = _determine_variant(wp_code)

    # ─── 2. 默认结构 ──────────────────────────────────────────────────────
    meta_info: dict = {
        "client_name": "",
        "audit_year": "",
        "index_no": wp_code or "A17-7",
    }

    declaration_text = TEAM_DECLARATION_TEXT if variant == "team" else COMMITTEE_DECLARATION_TEXT

    period_data: dict = {
        "business_start": None,
        "business_end": None,
        "report_start": None,
        "report_end": None,
    }

    team_sign_table: list[dict] = []

    partner_section: dict = {
        "confirmed": None,
        "explanation": None,
        "partner_sign": {"name": None, "date": None},
        "manager_sign": {"name": None, "date": None},
    }

    threat_records: dict = {
        "economic_interest": [],
        "loan_guarantee": [],
        "business_relation": [],
    }

    commitment_responses: dict = {}

    # ─── 3. 从 checklist_responses 加载已保存数据 ─────────────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE :prefix"
            ),
            {"wp_id": str(wp_id), "prefix": f"{prefix}%"},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            suffix = item_id[len(prefix):]
            remark = row.remark or ""
            conclusion = row.conclusion or ""

            # Period data
            if suffix == "period-business-start":
                period_data["business_start"] = remark or None
            elif suffix == "period-business-end":
                period_data["business_end"] = remark or None
            elif suffix == "period-report-start":
                period_data["report_start"] = remark or None
            elif suffix == "period-report-end":
                period_data["report_end"] = remark or None

            # Team sign table rows (JSON in remark)
            elif suffix.startswith("sign-"):
                parsed = _safe_parse_json(remark)
                if isinstance(parsed, dict):
                    team_sign_table.append({
                        "index": int(suffix.removeprefix("sign-") or "0"),
                        "name": parsed.get("name", ""),
                        "signed": parsed.get("signed", False),
                        "date": parsed.get("date"),
                    })

            # Partner section
            elif suffix == "partner-confirmed":
                partner_section["confirmed"] = conclusion.upper() == "Y" if conclusion else None
            elif suffix == "partner-explanation":
                partner_section["explanation"] = remark or None
            elif suffix == "partner-sign":
                parsed = _safe_parse_json(remark)
                if isinstance(parsed, dict):
                    partner_section["partner_sign"] = {
                        "name": parsed.get("name"),
                        "date": parsed.get("date"),
                    }
            elif suffix == "manager-sign":
                parsed = _safe_parse_json(remark)
                if isinstance(parsed, dict):
                    partner_section["manager_sign"] = {
                        "name": parsed.get("name"),
                        "date": parsed.get("date"),
                    }

            # Threat records
            elif suffix.startswith("threat-economic-"):
                parsed = _safe_parse_json(remark)
                if isinstance(parsed, dict):
                    threat_records["economic_interest"].append(parsed)
            elif suffix.startswith("threat-loan-"):
                parsed = _safe_parse_json(remark)
                if isinstance(parsed, dict):
                    threat_records["loan_guarantee"].append(parsed)
            elif suffix.startswith("threat-business-"):
                parsed = _safe_parse_json(remark)
                if isinstance(parsed, dict):
                    threat_records["business_relation"].append(parsed)

            # Commitment items
            elif suffix.startswith("commit-"):
                cid = suffix.removeprefix("commit-")
                commitment_responses[cid] = {"answer": conclusion or None, "explanation": remark or None}

    except Exception as e:  # noqa: BLE001
        logger.warning("A17-7 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # Sort sign table by index
    team_sign_table.sort(key=lambda r: r.get("index", 0))

    # ─── 4. 项目上下文 + 团队预填 ────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "team_members": [],
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year) if proj_row.audit_year else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-7 project context 查询失败: %s", e)

    # Team member pre-fill
    team_members = await _load_team_members(ctx.project_id, db)
    project_context["team_members"] = team_members
    project_context["project_id"] = str(ctx.project_id)

    # Auto-fill meta
    if not meta_info["client_name"]:
        meta_info["client_name"] = project_context["client_name"]
    if not meta_info["audit_year"]:
        meta_info["audit_year"] = project_context["audit_year"]

    # Pre-fill sign table from assignments if empty
    if not team_sign_table and team_members:
        team_sign_table = [
            {"index": i + 1, "name": m["name"], "signed": False, "date": None}
            for i, m in enumerate(team_members)
        ]

    # ─── 5. 承诺事项数据 ─────────────────────────────────────────────────
    commitment_items = _build_commitment_items(commitment_responses)

    return {
        "variant": variant,
        "meta_info": meta_info,
        "declaration_text": declaration_text,
        "period_data": period_data,
        "commitment_items": commitment_items,
        "team_sign_table": team_sign_table,
        "partner_section": partner_section,
        "threat_records": threat_records,
        "guidance_notes": GUIDANCE_NOTES,
        "project_context": project_context,
    }
