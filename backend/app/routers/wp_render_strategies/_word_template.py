"""word-template 通用渲染策略 — 返回模板结构 + 已填响应.

适用所有 25 个 word-template wp_code（A8-1, A8-2, ... S34-1-1）。
解析 docx 模板提取占位符/段落/表格结构，合并 checklist_responses 当前值。

数据持久化：checklist_responses 表，item_id 前缀 `wt-{wp_code}-`。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


def _carrier_absence_payload(wp_code: str) -> dict | None:
    """拿不到模板结构时，回答「是不是因为这个 wp_code 本来就没有可用 DOCX 载体」。

    spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 63
    Requirements: 7.7, 9.4, 9.5, 12.8

    ═══ 为什么必须区分两种「拿不到」═══

    原实现三处失败一律 `return None`，于是 render-config 里这个 sheet 没有
    `template_structure`，前端结构化视图落到 `<el-empty description="模板解析失败，
    请使用在线编辑模式"/>`。对 `S33-REV` 这类**模板库零载体**的 wp_code，在线编辑
    同样是死路（自取 `onlyoffice-config` 也找不到模板）⇒ 审计师被指向一条不存在的
    路。这正是 Task 63 要移除的假切换，而它的根因是「载体不存在」与「载体存在但这次
    读失败」被压成了同一个返回值。

    因此只有 Task 58 resolver **现算**判定无可用载体（`template_missing` /
    `document_type_mismatch`）时才返回裁决载荷；`resolved_docx` 却读不到属于真实
    异常（磁盘/权限/解析器），保持 `None` 原样冒泡，**不得**被裁决载荷掩盖成
    「本来就没有」—— 那会把一次可修的故障变成永久的「此底稿无模板」。

    Returns:
        无可用载体时返回带 `word_carrier` 的载荷；否则 None（保持原行为）。
    """
    from app.services.workpaper_sync.canonical_paths import PathBoundaryError
    from app.services.workpaper_sync.word_resolution import word_carrier_verdict

    try:
        verdict = word_carrier_verdict(wp_code)
    except PathBoundaryError:
        # 🔴 窄接、记 ERROR、不放行编辑。越界 wp_code 走到 render 期意味着上游校验
        #    有洞，是接线错误而不是「本底稿无模板」；但也不能让它把整个 render-config
        #    打成 500，故退回原 `None` 行为并留下可检索的 ERROR。
        logger.error(
            "word-template 载体裁决遇到越界 wp_code=%s —— 这是上游校验缺口，"
            "不是「无模板」，请按 Requirement 9.12 追查调用链",
            wp_code,
        )
        return None
    if verdict.has_usable_docx_carrier:
        return None
    return {
        "template_structure": None,
        "filled_responses": {},
        "sign_status": None,
        # 宿主门控的唯一判据。前端**不得**按 wp_code 字面量判无载体：
        # 那会在下一个零载体 wp_code 出现时静默失效，且把裁决权从后端搬进组件。
        "word_carrier": {
            "wp_code": wp_code,
            "verdict": verdict.value,
            "has_usable_carrier": False,
        },
    }


async def render(ctx: RenderContext) -> dict | None:
    """word-template 渲染策略：返回 template_structure + filled_responses + sign_status.

    Returns:
        dict with template_structure, filled_responses, sign_status
        无可用 DOCX 载体（Task 58 resolver 现算判 template_missing /
        document_type_mismatch）时返回仅含 `word_carrier` 裁决的载荷，供宿主门控掉
        在线编辑入口；载体应存在却读失败时仍返回 None（真实异常不被掩盖）。
    """
    from app.services.wp_docx_template_parser import get_cached_structure

    wp_id = ctx.wp_id
    wp_code = ctx.wp_code
    db = ctx.db

    # ─── 1. 解析模板文件路径 ─────────────────────────────────────────────
    file_path = ctx.template_file_path
    if not file_path:
        logger.debug("word-template 模板文件路径为空, wp_code=%s, wp_id=%s", wp_code, wp_id)
        return _carrier_absence_payload(wp_code)

    # ─── 2. 获取缓存的 TemplateStructure ─────────────────────────────────
    try:
        structure = get_cached_structure(file_path, wp_code)
    except FileNotFoundError:
        logger.debug("word-template 模板文件不存在: %s, wp_code=%s", file_path, wp_code)
        return _carrier_absence_payload(wp_code)
    except (ValueError, Exception) as e:  # noqa: BLE001
        logger.warning("word-template 模板解析失败 wp_code=%s: %s", wp_code, e)
        return _carrier_absence_payload(wp_code)

    # ─── 3. 查询 checklist_responses (item_id LIKE 'wt-{wp_code}-%') ────
    filled_responses: dict[str, str] = {}
    prefix = f"wt-{wp_code}-"

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
            ),
            {"wp_id": str(wp_id), "prefix": f"{prefix}%"},
        )
        for row in result.fetchall():
            # 从 item_id 提取 field_id: "wt-A8-1-entity_name" → "entity_name"
            field_id = row.item_id[len(prefix):]
            # conclusion 优先（短文本），remark 备选（长文本/textarea）
            value = row.conclusion or row.remark or ""
            if value:
                filled_responses[field_id] = value
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "word-template checklist_responses 查询失败 wp_id=%s: %s", wp_id, e
        )

    # ─── 4. 合并 current_value 到 placeholders ──────────────────────────
    template_structure = _serialize_structure(structure, filled_responses)

    return {
        "template_structure": template_structure,
        "filled_responses": filled_responses,
        "sign_status": None,  # placeholder for future signing integration
    }


def _serialize_structure(structure, filled_responses: dict[str, str]) -> dict:
    """将 TemplateStructure 序列化为 API 响应格式，合并 current_value."""
    from dataclasses import asdict as _asdict

    placeholders = []
    for p in structure.placeholders:
        p_dict = _asdict(p)
        p_dict["current_value"] = filled_responses.get(p.field_id, "")
        placeholders.append(p_dict)

    paragraphs = [_asdict(para) for para in structure.paragraphs]
    tables = [_asdict(tbl) for tbl in structure.tables]

    return {
        "placeholders": placeholders,
        "paragraphs": paragraphs,
        "tables": tables,
        "metadata": structure.metadata,
    }
