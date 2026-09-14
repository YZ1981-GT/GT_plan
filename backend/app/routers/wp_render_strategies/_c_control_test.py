"""C2~C15 业务循环控制测试 — 专属渲染策略.

componentType: c-control-test
覆盖 C2~C15 共 14 个循环，每个循环含 5~7 个 sheet。
前端 GtCControlTest.vue 弹窗层叠模式（L0汇总表+L1详情+L2偏差评价）。

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免被 onlyoffice-sheet 吞掉。
2. 返回 sheets 配置供前端接收。
3. 回读已持久化的数据（checklist_responses，item_id 前缀 C{n}-）。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# backend/app/routers/wp_render_strategies/_c_control_test.py
#   parents[0] = wp_render_strategies
#   parents[1] = routers
#   parents[2] = app
#   parents[3] = backend
# → backend/data/wp_guidance
GUIDANCE_DIR = Path(__file__).resolve().parents[3] / "data" / "wp_guidance"


def _load_guidance(wp_code: str) -> dict | None:
    """加载 guidance JSON 纯函数，缺失或解析失败返回 None。

    行为:
    - 文件 ``{wp_code}.json`` 不存在时返回 None（不抛异常）
    - JSON 解析失败时 logger.warning 并返回 None
    - OSError 时返回 None
    - data 必须是 dict 且包含 "sections" key，否则返回 None
    - 成功时返回解析的 dict
    """
    filename = f"{wp_code}.json"
    filepath = GUIDANCE_DIR / filename
    if not filepath.exists():
        return None
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning("C control test guidance: JSON 解析失败 %s: %s", filename, e)
        return None
    except OSError as e:
        logger.warning("C control test guidance: 读取失败 %s: %s", filename, e)
        return None
    if isinstance(data, dict) and "sections" in data:
        return data
    return None


async def render(ctx: RenderContext) -> dict | None:
    """C2~C15 控制测试渲染策略：返回 componentType + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    # 从 wp_code 提取循环编号
    wp_code = getattr(ctx, "wp_code", "") or ""

    # 回读已持久化的 checklist_responses
    responses_snapshot: dict = {}
    try:
        # C{n}- 前缀匹配（如 C2- / C10- 等）
        prefix_pattern = f"{wp_code}-%"
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE :prefix "
                "LIMIT 2000"
            ),
            {"wp_id": str(wp_id), "prefix": prefix_pattern},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("C control test render: checklist_responses 失败: %s", e)

    # 项目上下文
    project_context: dict = {"client_name": "", "audit_year": ""}
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
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("C control test render: project context 失败: %s", e)

    # 编制提示 guidance 加载
    # C2~C15 render 策略同时处理 L1 dialog 与 Cx-2 独立底稿，
    # Cx-2 独立底稿 wp_code 含 "-2" 后缀，需先剥离得到基础循环编码（如 C5-2 → C5），
    # 否则 L1 guidance 会去加载不存在的 "C5-2.json"。
    base_wp_code = re.sub(r"-\d+$", "", wp_code)
    guidance_l1 = _load_guidance(base_wp_code)  # 如 C5.json
    guidance_cx2 = _load_guidance(f"{base_wp_code}-2")  # 如 C5-2.json

    return {
        "component_type": "c-control-test",
        "wp_code": wp_code,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "guidance": guidance_l1,  # L1 Dialog 编制提示（缺失为 None）
        "guidance_cx2": guidance_cx2,  # Cx-2 偏差评价编制提示（缺失为 None）
    }
