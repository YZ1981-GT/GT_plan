"""B-Index 底稿目录自动生成策略

当 B-Index sheet 无持久化 html_data 时，从项目元数据 + 同底稿 sheets 自动生成。
返回结构与 GtBIndex.vue 的 BIndexHtmlData 接口一致。
"""

from __future__ import annotations

import logging
import re

from ._context import RenderContext

logger = logging.getLogger(__name__)

# sheet 级索引号嵌在 sheet_name 末尾（如「审定表D1-1」→ D1-1，
# 「应收票据审计程序表D1A」→ D1A）；wp_code 仅父级（D1），不能用作 index_ref。
_SHEET_INDEX_PATTERN = re.compile(r"([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$")


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）。

    仅当 B-Index sheet 尚无持久化数据时才自动生成：
    - preparation_info：编制信息（实体名/期末/编制人等）
    - navigation_rows：当前底稿内各 sheet 索引导航
    - cycle_workpapers：同审计循环全部底稿跨底稿跳转目录
    """
    # 已有持久化数据则不重新生成
    if ctx.sheet_html_data:
        return None

    from app.services.wp_classification_service import derive_component_type

    # ─── 编制信息（lazy prep_info） ───────────────────────────────────────
    if ctx.prep_info is None:
        from app.services.wp_preparation_info_service import build_preparation_info

        ctx.prep_info = await build_preparation_info(ctx.db, ctx.project_id, ctx.wp_id)

    preparation_info = ctx.prep_info

    # ─── 索引导航行（同底稿其他 sheet → 行） ─────────────────────────────
    navigation_rows: list[dict] = []
    seq = 1
    for cls in ctx.classifications:
        # 跳过 B-Index 自身
        try:
            ct = derive_component_type(cls)
        except Exception:
            ct = "skip"
        if ct == "b-index":
            continue

        # 从 sheet_name 末尾提取该 sheet 的真实索引号；提取不到则回退父 wp_code
        sheet_index = ""
        m = _SHEET_INDEX_PATTERN.search(cls.sheet_name or "")
        if m:
            sheet_index = m.group(1)
        else:
            sheet_index = getattr(cls, "wp_code", "") or ""

        navigation_rows.append({
            "seq": seq,
            "content": cls.sheet_name,
            "index_ref": sheet_index,
            "component_type": ct,
            "no_print": False,
        })
        seq += 1

    # ─── 循环底稿目录（跨底稿，同 audit_cycle 全部底稿） ──────────────────
    from app.services.wp_cycle_directory import build_cycle_workpapers

    cycle_workpapers = await build_cycle_workpapers(
        db=ctx.db,
        project_id=ctx.project_id,
        audit_cycle=ctx.audit_cycle,
        current_wp_id=ctx.wp_id,
    )

    return {
        "preparation_info": preparation_info,
        "navigation_rows": navigation_rows,
        "cycle_workpapers": cycle_workpapers,
    }
