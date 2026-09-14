"""B1-5 KAA检查程序表 — 专属渲染策略.

component_type = "b1-5-kaa-check"

源模板结构：
- 一、确定是否达到KAA标准：12 个判定项（item7/item12 含子项），任一判定为"是"即达到 KAA 标准
- 二、完成KAA审批或报备流程：3 项（非央国企→GTI审批表；央国企/军工→报备表；其他→查政策）

自动结论：一节任一"是" → 达到 KAA 标准（需执行二节审批/报备）；全"否/N/A" → 未达到。

数据持久化在 checklist_responses，item_id 前缀 `b1kaa-`：
- 判定:   b1kaa-{sectionKey}-{seq}           (conclusion = 是/否/N/A)
- 说明:   b1kaa-{sectionKey}-{seq}-note       (remark = 执行情况说明)
- 子项:   b1kaa-{sectionKey}-{seq}-{subSeq}   (conclusion = 是/否/N/A)
- 头部:   b1kaa-hdr-{field}                   (remark)
- 结论:   b1kaa-overall-conclusion            (conclusion = reached/not_reached, 自动可覆盖)
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
    "b1_5_kaa_presets.json",
)

_preset_cache: dict | None = None
_preset_mtime: float = 0.0

_HEADER_FIELDS = [
    {"field": "audited_entity", "label": "被审计单位"},
    {"field": "accounting_period", "label": "会计期间"},
    {"field": "preparer", "label": "编制人（项目负责经理）"},
    {"field": "reviewer", "label": "复核人（项目合伙人）"},
]


def _load_presets() -> dict:
    global _preset_cache, _preset_mtime
    try:
        mtime = os.path.getmtime(_PRESET_PATH)
        if _preset_cache is None or mtime != _preset_mtime:
            with open(_PRESET_PATH, encoding="utf-8") as f:
                _preset_cache = json.load(f)
            _preset_mtime = mtime
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-5 KAA 预置加载失败: %s", e)
        return {}
    return _preset_cache or {}


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    preset = _load_presets()
    src_sections = preset.get("sections", [])

    # ─── 加载已存响应 ───
    responses: dict[str, tuple[str | None, str | None]] = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'b1kaa-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses[row.item_id] = (row.conclusion, row.remark)
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-5 KAA checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 组装 sections ───
    reached = False
    sections: list[dict] = []
    for sec in src_sections:
        sk = sec.get("key", "")
        items_out: list[dict] = []
        for it in sec.get("items", []):
            seq = it.get("seq", "")
            base_id = f"b1kaa-{sk}-{seq}"
            ans = responses.get(base_id)
            note = responses.get(f"{base_id}-note")
            answer = (ans[0] if ans else "") or ""
            subs_out: list[dict] = []
            for sub in it.get("sub_items", []):
                sub_seq = sub.get("seq", "")
                sub_id = f"{base_id}-{sub_seq}"
                sub_ans = responses.get(sub_id)
                sub_answer = (sub_ans[0] if sub_ans else "") or ""
                subs_out.append(
                    {"seq": sub_seq, "text": sub.get("text", ""), "answer": sub_answer}
                )
                if sk == "standard" and sub_answer == "是":
                    reached = True
            if sk == "standard" and answer == "是":
                reached = True
            items_out.append(
                {
                    "seq": seq,
                    "text": it.get("text", ""),
                    "kind": it.get("kind", "judge"),
                    "answer": answer,
                    "note": (note[1] if note else "") or "",
                    "sub_items": subs_out,
                }
            )
        sections.append({"key": sk, "title": sec.get("title", ""), "items": items_out})

    # ─── 头部信息 ───
    header: dict[str, str] = {}
    for hf in _HEADER_FIELDS:
        hd = responses.get(f"b1kaa-hdr-{hf['field']}")
        header[hf["field"]] = (hd[1] if hd else "") or ""

    # ─── 综合结论（自动，可被持久化覆盖）───
    oc = responses.get("b1kaa-overall-conclusion")
    manual_conclusion = oc[0] if oc else ""
    auto_conclusion = "reached" if reached else "not_reached"
    conclusion = manual_conclusion or auto_conclusion
    cn = responses.get("b1kaa-conclusion-note")
    conclusion_note = (cn[1] if cn else "") or ""

    # ─── 项目上下文预填被审计单位 ───
    project_context = await _load_project_context(project_id, db)
    if not header.get("audited_entity") and project_context.get("client_name"):
        header["audited_entity"] = project_context["client_name"]
    if not header.get("accounting_period") and project_context.get("audit_period"):
        header["accounting_period"] = project_context["audit_period"]

    return {
        # 优先用当前 sheet 真实 tab 名（含前导空格），回退 preset，供前端「在线编辑」精确定位
        "source_sheet": (getattr(ctx.classification, "sheet_name", "") or preset.get("source_sheet", "")),
        "sections": sections,
        "header_fields": _HEADER_FIELDS,
        "header": header,
        "auto_conclusion": auto_conclusion,
        "conclusion": conclusion,
        "conclusion_note": conclusion_note,
        "reached": reached,
        "project_context": project_context,
    }


async def _load_project_context(project_id, db) -> dict:
    project_context: dict = {"client_name": "", "audit_period": ""}
    try:
        proj_result = await db.execute(
            sa.text("SELECT client_name, audit_year FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            if proj_row.audit_year:
                project_context["audit_period"] = f"{proj_row.audit_year}年度"
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-5 KAA project context 查询失败: %s", e)
    return project_context
