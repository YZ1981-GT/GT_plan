"""A10-1 与治理层沟通函 — 专属渲染策略.

component_type = "a10-1-governance-communication"
大型多章节沟通函（16章）+ 左侧导航 + 服务费表格 + GtIndexChip跳转。
跨引用联动: A9-2 (内控缺陷沟通函)、A13 (错报汇总)。
数据持久化在 checklist_responses 表，item_id 前缀 `a101-`。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 固定引言段
INTRODUCTION_TEXTS = [
    "在审计贵公司{audit_period}财务报表过程中，我们认为以下事项需要与治理层进行沟通。",
    "根据《中国注册会计师审计准则第1151号——与治理层的沟通》的要求，我们将审计中发现的重大事项向治理层通报如下：",
]

# 提示说明
GUIDANCE_NOTES = "本沟通函依据《中国注册会计师审计准则第1151号——与治理层的沟通》编制，旨在向治理层通报审计过程中发现的重大事项。本函所涉事项并不构成对贵公司财务报表的审计意见，亦不影响我们对贵公司财务报表发表的审计意见。"

# 16 章节元数据
CHAPTERS_META = [
    {"number": 1, "title": "审计的范围和时间安排", "cross_ref": None},
    {"number": 2, "title": "审计中发现的重大问题", "cross_ref": None},
    {"number": 3, "title": "非审计服务费用", "cross_ref": None},
    {"number": 4, "title": "独立性声明", "cross_ref": None},
    {"number": 5, "title": "审计中发现的重大错报", "cross_ref": None},
    {"number": 6, "title": "已更正的错报", "cross_ref": None},
    {"number": 7, "title": "已向管理层通报的内部控制缺陷", "cross_ref": None},
    {"number": 8, "title": "会计估计和相关披露", "cross_ref": None},
    {"number": 9, "title": "其他需要通报的内部控制缺陷", "cross_ref": "A9-2"},
    {"number": 10, "title": "审计中遇到的重大困难", "cross_ref": None},
    {"number": 11, "title": "与管理层讨论的重大问题", "cross_ref": None},
    {"number": 12, "title": "修改后的计划审计范围和时间安排", "cross_ref": None},
    {"number": 13, "title": "未更正错报", "cross_ref": "A13"},
    {"number": 14, "title": "其他需要注意的事项", "cross_ref": None},
    {"number": 15, "title": "与审计相关的其他信息", "cross_ref": None},
    {"number": 16, "title": "致同就被审计单位治理层的提醒", "cross_ref": None},
]

# 5 个固定服务费行
SERVICE_FEE_NAMES = ["审计服务", "审阅服务", "其他鉴证服务", "税务服务", "其他服务"]

# 跨引用 wp_code 列表
CROSS_REF_WP_CODES = ["A9-2", "A13"]


async def _load_cross_references(project_id, db) -> dict:
    """查找 A9-2, A13 底稿的 wp_id.

    通过 wp_index JOIN working_papers 定位同项目下的目标底稿。
    返回 dict: {a9_2_wp_id, a13_wp_id}，缺失时对应值为 None。
    """
    cross_refs: dict[str, str | None] = {
        "a9_2_wp_id": None,
        "a13_wp_id": None,
    }

    key_map = {
        "A9-2": "a9_2_wp_id",
        "A13": "a13_wp_id",
    }

    try:
        result = await db.execute(
            sa.text(
                "SELECT wi.wp_code, wp.id AS wp_id "
                "FROM wp_index wi "
                "JOIN working_papers wp ON wp.wp_index_id = wi.id "
                "WHERE wi.wp_code IN :codes AND wp.project_id = :project_id"
            ),
            {"codes": tuple(CROSS_REF_WP_CODES), "project_id": str(project_id)},
        )
        for row in result.fetchall():
            dict_key = key_map.get(row.wp_code)
            if dict_key:
                cross_refs[dict_key] = str(row.wp_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("A10-1 跨引用查询失败 project_id=%s: %s", project_id, e)

    return cross_refs


async def render(ctx: RenderContext) -> dict | None:
    """A10-1 与治理层沟通函渲染策略.

    返回 {meta_info, recipient, introduction_text, chapters(16),
           service_fees(5), signing_section, guidance_notes,
           cross_references, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    # ─── 1. 加载 checklist_responses (item_id LIKE 'a101-%') ─────────────
    recipient: str | None = None
    chapters_data: dict[int, str | None] = {}
    service_fees_raw: list[dict] | None = None
    signing: dict = {"firm_name": None, "partner_name": None, "date": None}

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a101-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id = row.item_id
            if item_id == "a101-recipient":
                recipient = row.conclusion or row.remark or None
            elif item_id.startswith("a101-ch") and item_id.endswith("-content"):
                # a101-ch{N}-content
                try:
                    rest = item_id.removeprefix("a101-ch").removesuffix("-content")
                    ch_num = int(rest)
                    if 1 <= ch_num <= 16:
                        chapters_data[ch_num] = row.remark or row.conclusion or None
                except (ValueError, IndexError):
                    pass
            elif item_id == "a101-fee":
                # remark = JSON array of 5 fee rows [{name, amount}]
                if row.remark:
                    try:
                        data = json.loads(row.remark)
                        if isinstance(data, list):
                            service_fees_raw = data
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("A10-1 fee JSON 解析失败")
            elif item_id == "a101-sign-firm":
                signing["firm_name"] = row.conclusion or row.remark or None
            elif item_id == "a101-sign-partner":
                signing["partner_name"] = row.conclusion or row.remark or None
            elif item_id == "a101-sign-date":
                signing["date"] = row.conclusion or row.remark or None
    except Exception as e:  # noqa: BLE001
        logger.warning("A10-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 2. 加载项目上下文 ───────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_period": "",
        "firm_name": "致同会计师事务所（特殊普通合伙）",
    }
    try:
        proj_result = await db.execute(
            sa.text("SELECT client_name, audit_year FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            year = proj_row.audit_year
            if year:
                project_context["audit_period"] = f"{year}年度"
    except Exception as e:  # noqa: BLE001
        logger.warning("A10-1 project context 查询失败: %s", e)

    # ─── 3. 加载跨引用 wp_ids ────────────────────────────────────────────
    cross_references = await _load_cross_references(project_id, db)

    # ─── 4. 构建 chapters 数组 (16) ──────────────────────────────────────
    chapters: list[dict] = []
    for meta in CHAPTERS_META:
        num = meta["number"]
        chapters.append({
            "number": num,
            "title": meta["title"],
            "content": chapters_data.get(num),
            "cross_ref": meta["cross_ref"],
        })

    # ─── 5. 构建 service_fees (5) ────────────────────────────────────────
    service_fees: list[dict] = []
    for i, name in enumerate(SERVICE_FEE_NAMES):
        amount: float | None = None
        if service_fees_raw and i < len(service_fees_raw):
            raw_item = service_fees_raw[i]
            if isinstance(raw_item, dict):
                raw_amount = raw_item.get("amount")
                if raw_amount is not None:
                    try:
                        amount = float(raw_amount)
                    except (ValueError, TypeError):
                        pass
        service_fees.append({"name": name, "amount": amount})

    # ─── 6. 构建 introduction_text ───────────────────────────────────────
    audit_period = project_context["audit_period"] or "本年度"
    introduction_text = [
        t.format(audit_period=audit_period) for t in INTRODUCTION_TEXTS
    ]

    # ─── 7. 自动填充签发事务所名 ─────────────────────────────────────────
    if not signing["firm_name"]:
        signing["firm_name"] = project_context["firm_name"]

    # ─── 8. 构建 meta_info ───────────────────────────────────────────────
    meta_info = {
        "client_name": project_context["client_name"],
        "audit_period": project_context["audit_period"],
        "index_no": "A10-1",
    }

    return {
        "meta_info": meta_info,
        "recipient": recipient,
        "introduction_text": introduction_text,
        "chapters": chapters,
        "service_fees": service_fees,
        "signing_section": signing,
        "guidance_notes": GUIDANCE_NOTES,
        "cross_references": cross_references,
        "project_context": project_context,
    }
