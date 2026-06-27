"""A9-2 向治理层通报内部控制缺陷沟通函 — 专属渲染策略.

component_type = "a9-2-deficiency-letter-governance"
复用 A9-1 核心逻辑，差异：
- variant = "governance"
- deficiency_list 无 "general" 键
- section_data 无 "response" 键
- item_id 前缀 a92-
"""

from __future__ import annotations

from dataclasses import asdict

from ._a91_deficiency_letter import (
    _load_b22b_deficiencies,
    _load_project_context,
    _load_section_data,
)
from ._context import RenderContext


async def render(ctx: RenderContext) -> dict | None:
    """A9-2 治理层内控缺陷沟通函渲染策略.

    返回 {variant, section_data, deficiency_list, project_context, b22b_warning}
    """
    # ─── 1. 加载 section_data（item_id LIKE 'a92-%'） ────────────────────
    section_data, manual_deficiencies = await _load_section_data(ctx, prefix="a92")

    # ─── 2. 移除 response section（治理层无管理层回复区） ─────────────────
    section_data.pop("response", None)

    # ─── 3. 从 B22B 加载缺陷数据（复用） ────────────────────────────────
    b22b_result = await _load_b22b_deficiencies(ctx.project_id, ctx.db)
    b22b_deficiencies: dict[str, list] = b22b_result["deficiencies"]
    b22b_warning: str | None = b22b_result["warning"]

    # ─── 4. 合并缺陷列表（B22B + 手动），排除 general ────────────────────
    deficiency_list: dict[str, list] = {"major": [], "significant": []}
    for severity in ("major", "significant"):
        deficiency_list[severity] = (
            [asdict(d) for d in b22b_deficiencies.get(severity, [])]
            + [asdict(d) for d in manual_deficiencies.get(severity, [])]
        )

    # ─── 5. 项目上下文 ──────────────────────────────────────────────────
    project_context = await _load_project_context(ctx)

    # 自动填充收件人
    if not section_data["addressee"]["client_name"]:
        section_data["addressee"]["client_name"] = project_context["client_name"]

    return {
        "variant": "governance",
        "section_data": section_data,
        "deficiency_list": deficiency_list,
        "project_context": project_context,
        "b22b_warning": b22b_warning,
    }
