"""
底稿依赖关系服务 — B/C/D三类底稿联动

审计工作流逻辑顺序：
  B类（风险评估）→ C类（控制测试）→ D-N类（实质性程序）

本服务提供：
1. 依赖关系定义（哪个底稿依赖哪个）
2. 依赖状态检查（前置底稿是否已完成）
3. 控制测试结论联动（C类结论影响D类程序范围）
4. 三式联动顺序保证（生成structure.json的正确顺序）
"""
import logging
from typing import Any, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 1. 依赖关系定义
# ═══════════════════════════════════════════

# 循环前缀 → 关联的B类(业务层面控制) + C类(控制测试) 编码
CYCLE_DEPENDENCIES: dict[str, dict[str, list[str]]] = {
    "D": {
        "b_controls": ["B23-1", "B23-11"],   # 销售循环+税金业务层面控制
        "c_tests": ["C2", "C12"],             # 销售循环+税金控制测试
        "description": "收入循环",
    },
    "E": {
        "b_controls": ["B23-2"],              # 货币资金业务层面控制
        "c_tests": ["C3"],                    # 货币资金控制测试
        "description": "货币资金循环",
    },
    "F": {
        "b_controls": ["B23-3"],
        "c_tests": ["C4"],
        "description": "存货循环",
    },
    "G": {
        "b_controls": ["B23-4"],
        "c_tests": ["C5"],
        "description": "投资循环",
    },
    "H": {
        "b_controls": ["B23-5", "B23-6", "B23-13"],  # 固定资产+在建工程+租赁
        "c_tests": ["C6", "C7", "C14"],
        "description": "固定资产循环",
    },
    "I": {
        "b_controls": ["B23-7", "B23-8"],    # 无形资产+研发
        "c_tests": ["C8", "C9"],
        "description": "无形资产循环",
    },
    "J": {
        "b_controls": ["B23-9"],
        "c_tests": ["C10"],
        "description": "职工薪酬循环",
    },
    "K": {
        "b_controls": ["B23-10"],
        "c_tests": ["C11"],
        "description": "管理循环",
    },
    "L": {
        "b_controls": ["B23-12"],
        "c_tests": ["C13"],
        "description": "债务循环",
    },
    "M": {
        "b_controls": [],
        "c_tests": [],
        "description": "权益循环（通常无独立控制测试）",
    },
    "N": {
        "b_controls": ["B23-11"],             # 税金业务层面控制
        "c_tests": ["C12"],                   # 税金控制测试
        "description": "税金循环",
    },
    "Q": {
        "b_controls": ["B23-14"],
        "c_tests": ["C15"],
        "description": "关联方循环",
    },
}

# 控制测试结论 → 实质性程序范围建议
CONTROL_EFFECTIVENESS_IMPACT = {
    "effective": {
        "label": "控制有效",
        "impact": "可适当减少实质性程序范围",
        "sampling_factor": 0.7,  # 抽样量系数（相对基准）
        "suggested_procedures": "可减少细节测试范围，侧重分析性程序",
    },
    "partially_effective": {
        "label": "部分有效",
        "impact": "维持标准实质性程序范围",
        "sampling_factor": 1.0,
        "suggested_procedures": "执行标准范围的细节测试和分析性程序",
    },
    "ineffective": {
        "label": "控制无效",
        "impact": "需扩大实质性程序范围",
        "sampling_factor": 1.5,
        "suggested_procedures": "扩大细节测试范围，增加截止测试和函证程序",
    },
    "not_tested": {
        "label": "未测试",
        "impact": "按控制无效处理，执行扩大的实质性程序",
        "sampling_factor": 1.5,
        "suggested_procedures": "按控制无效处理",
    },
}


# ═══════════════════════════════════════════
# 2. 依赖状态检查
# ═══════════════════════════════════════════

async def check_dependencies(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
) -> dict[str, Any]:
    """检查底稿的前置依赖是否已完成

    返回：
    {
        "wp_code": "E1",
        "cycle": "E",
        "dependencies": [
            {"code": "B23-2", "type": "b_control", "status": "completed", "message": ""},
            {"code": "C3", "type": "c_test", "status": "not_started", "message": "控制测试未开始"},
        ],
        "all_satisfied": false,
        "warnings": ["货币资金控制测试(C3)尚未完成，建议先完成控制测试"],
        "control_effectiveness": "not_tested",
        "impact": {...}
    }
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex, WpFileStatus

    cycle = wp_code[0].upper() if wp_code else ""
    dep_def = CYCLE_DEPENDENCIES.get(cycle, {})
    if not dep_def:
        return {
            "wp_code": wp_code, "cycle": cycle,
            "dependencies": [], "all_satisfied": True, "warnings": [],
            "control_effectiveness": None, "impact": None,
        }

    dependencies = []
    warnings = []
    control_effectiveness = "not_tested"

    # 检查B类依赖
    for b_code in dep_def.get("b_controls", []):
        status = await _get_wp_status(db, project_id, b_code)
        dep = {
            "code": b_code, "type": "b_control",
            "status": status, "label": f"业务层面控制({b_code})",
        }
        dependencies.append(dep)
        if status not in ("review_passed", "archived", "edit_complete"):
            warnings.append(f"业务层面控制({b_code})尚未完成")

    # 检查C类依赖
    for c_code in dep_def.get("c_tests", []):
        status = await _get_wp_status(db, project_id, c_code)
        dep = {
            "code": c_code, "type": "c_test",
            "status": status, "label": f"控制测试({c_code})",
        }
        dependencies.append(dep)

        if status in ("review_passed", "archived"):
            # 从parsed_data读取控制测试结论
            effectiveness = await _get_control_effectiveness(db, project_id, c_code)
            if effectiveness:
                control_effectiveness = effectiveness
        elif status not in ("edit_complete",):
            warnings.append(f"控制测试({c_code})尚未完成，建议先完成控制测试再确定实质性程序范围")

    all_satisfied = len(warnings) == 0
    impact = CONTROL_EFFECTIVENESS_IMPACT.get(control_effectiveness)

    return {
        "wp_code": wp_code,
        "cycle": cycle,
        "cycle_name": dep_def.get("description", ""),
        "dependencies": dependencies,
        "all_satisfied": all_satisfied,
        "warnings": warnings,
        "control_effectiveness": control_effectiveness,
        "impact": impact,
    }


async def _get_wp_status(db: AsyncSession, project_id: UUID, wp_code_prefix: str) -> str:
    """获取底稿状态（按编码前缀匹配）"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper.status)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WpIndex.wp_code.startswith(wp_code_prefix),
            WorkingPaper.is_deleted == sa.false(),
        )
        .order_by(WorkingPaper.updated_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return "not_found"
    return row.value if hasattr(row, 'value') else str(row)


async def _get_control_effectiveness(
    db: AsyncSession, project_id: UUID, c_code: str
) -> Optional[str]:
    """从C类底稿的parsed_data中读取控制测试结论"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper.parsed_data)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WpIndex.wp_code.startswith(c_code),
            WorkingPaper.is_deleted == sa.false(),
            WorkingPaper.parsed_data.isnot(None),
        )
        .limit(1)
    )
    pd = result.scalar_one_or_none()
    if pd and isinstance(pd, dict):
        return pd.get("control_effectiveness")
    return None


# ═══════════════════════════════════════════
# 3. 三式联动顺序
# ═══════════════════════════════════════════

def get_generation_order(wp_codes: list[str]) -> list[str]:
    """按B→C→D-N顺序排列底稿编码，确保依赖方先生成

    三式联动（structure.json生成）时，D类引用C类结论需要C类先就绪。
    """
    def _sort_key(code: str) -> tuple:
        prefix = code[0].upper() if code else 'Z'
        # B类=0, C类=1, D-N类=2+, 其他=9
        if prefix == 'B':
            return (0, code)
        elif prefix == 'C':
            return (1, code)
        elif prefix in 'DEFGHIJKLMNQ':
            return (2, code)
        elif prefix == 'A':
            return (3, code)  # 完成阶段最后
        elif prefix == 'S':
            return (4, code)
        else:
            return (9, code)

    return sorted(wp_codes, key=_sort_key)


# ═══════════════════════════════════════════
# 4. 获取循环完整依赖图
# ═══════════════════════════════════════════

def get_cycle_dependency_graph(cycle: str) -> dict:
    """获取指定循环的完整依赖关系图（供前端可视化）"""
    dep = CYCLE_DEPENDENCIES.get(cycle.upper(), {})
    if not dep:
        return {"cycle": cycle, "nodes": [], "edges": []}

    nodes = []
    edges = []

    # B类节点
    for b in dep.get("b_controls", []):
        nodes.append({"id": b, "type": "b_control", "label": f"业务控制 {b}"})

    # C类节点
    for c in dep.get("c_tests", []):
        nodes.append({"id": c, "type": "c_test", "label": f"控制测试 {c}"})
        # B→C 边
        for b in dep.get("b_controls", []):
            edges.append({"from": b, "to": c, "label": "识别控制点"})

    # D类节点（实质性程序）
    d_node = f"{cycle}类实质性程序"
    nodes.append({"id": d_node, "type": "substantive", "label": d_node})
    for c in dep.get("c_tests", []):
        edges.append({"from": c, "to": d_node, "label": "控制结论→程序范围"})

    return {
        "cycle": cycle,
        "cycle_name": dep.get("description", ""),
        "nodes": nodes,
        "edges": edges,
    }
