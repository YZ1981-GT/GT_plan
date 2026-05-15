"""风险-底稿追溯服务

Sprint 8 Task 8.3: 风险→底稿映射 + 链路完整性检查。
追溯链路：B(风险评估) → C(控制测试) → D-N(实质性程序) → A(完成阶段)
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 审计阶段映射（用于链路完整性检查）
STAGE_ORDER = {
    "risk_assessment": 1,   # B 类
    "control_test": 2,      # C 类
    "substantive": 3,       # D-N 类
    "completion": 4,        # A 类
}

# 底稿编码前缀→阶段映射
CODE_TO_STAGE = {
    "B": "risk_assessment",
    "C": "control_test",
    "D": "substantive", "E": "substantive", "F": "substantive",
    "G": "substantive", "H": "substantive", "I": "substantive",
    "J": "substantive", "K": "substantive", "L": "substantive",
    "M": "substantive", "N": "substantive",
    "A": "completion",
    "S": "substantive",
}


class WpRiskTraceService:
    """风险追溯服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_risk_workpaper_map(self, project_id: UUID) -> list[dict]:
        """获取项目的风险→底稿映射

        Returns:
            [{risk_id, risk_description, workpapers: [{wp_id, wp_code, stage}]}]
        """
        # 从 issue_tickets (source='risk') 获取风险项
        risks = (await self.db.execute(sa.text("""
            SELECT id, title, description, severity
            FROM issue_tickets
            WHERE project_id = :pid AND source = 'risk' AND is_deleted = false
            ORDER BY severity DESC, created_at
        """), {"pid": str(project_id)})).fetchall()

        # 获取项目所有底稿
        wps = (await self.db.execute(sa.text("""
            SELECT w.id, i.wp_code, i.wp_name
            FROM working_paper w
            JOIN wp_index i ON w.wp_index_id = i.id
            WHERE w.project_id = :pid AND w.is_deleted = false
        """), {"pid": str(project_id)})).fetchall()

        wp_map = {r.id: {"wp_id": r.id, "wp_code": r.wp_code, "wp_name": r.wp_name} for r in wps}

        result = []
        for risk in risks:
            # 根据风险描述中的科目/循环关键词匹配底稿
            linked_wps = self._match_risk_to_workpapers(
                risk.title or "", risk.description or "", list(wp_map.values())
            )
            result.append({
                "risk_id": risk.id,
                "risk_title": risk.title,
                "severity": risk.severity,
                "workpapers": linked_wps,
            })

        return result

    async def check_trace_completeness(self, project_id: UUID) -> dict:
        """检查风险追溯链路完整性

        验证每个已识别风险是否有完整的 B→C→D→A 链路覆盖。

        Returns:
            {complete_count, incomplete_count, gaps: [{risk_id, missing_stages}]}
        """
        risk_map = await self.get_risk_workpaper_map(project_id)

        complete = 0
        incomplete = 0
        gaps = []

        for risk in risk_map:
            stages_covered = set()
            for wp in risk.get("workpapers", []):
                code = wp.get("wp_code", "")
                if code:
                    prefix = code[0].upper()
                    stage = CODE_TO_STAGE.get(prefix)
                    if stage:
                        stages_covered.add(stage)

            # 检查是否覆盖了所有必要阶段
            required = {"risk_assessment", "substantive"}  # 最低要求
            missing = required - stages_covered

            if not missing:
                complete += 1
            else:
                incomplete += 1
                gaps.append({
                    "risk_id": risk["risk_id"],
                    "risk_title": risk["risk_title"],
                    "covered_stages": sorted(stages_covered),
                    "missing_stages": sorted(missing),
                })

        return {
            "total_risks": len(risk_map),
            "complete_count": complete,
            "incomplete_count": incomplete,
            "gaps": gaps,
        }

    async def get_trace_chain(self, project_id: UUID, risk_id: str) -> dict:
        """获取单个风险的完整追溯链路

        Returns:
            {risk, chain: [{stage, stage_order, workpapers}]}
        """
        risk_map = await self.get_risk_workpaper_map(project_id)
        target = next((r for r in risk_map if r["risk_id"] == risk_id), None)

        if not target:
            return {"error": "风险项不存在"}

        # 按阶段分组
        chain: dict[str, list] = {}
        for wp in target.get("workpapers", []):
            code = wp.get("wp_code", "")
            prefix = code[0].upper() if code else ""
            stage = CODE_TO_STAGE.get(prefix, "unknown")
            chain.setdefault(stage, []).append(wp)

        # 按阶段顺序排列
        ordered_chain = []
        for stage, order in sorted(STAGE_ORDER.items(), key=lambda x: x[1]):
            ordered_chain.append({
                "stage": stage,
                "stage_order": order,
                "workpapers": chain.get(stage, []),
                "has_coverage": len(chain.get(stage, [])) > 0,
            })

        return {
            "risk_id": target["risk_id"],
            "risk_title": target["risk_title"],
            "chain": ordered_chain,
        }

    def _match_risk_to_workpapers(
        self, title: str, description: str, workpapers: list[dict]
    ) -> list[dict]:
        """根据风险描述匹配相关底稿（关键词匹配）"""
        text = (title + " " + description).lower()
        matched = []

        # 循环关键词映射
        cycle_keywords = {
            "D": ["应收", "收入", "销售", "函证"],
            "E": ["货币资金", "银行", "现金"],
            "F": ["存货", "成本"],
            "G": ["投资", "金融资产"],
            "H": ["固定资产", "折旧", "在建工程"],
            "I": ["无形资产", "摊销"],
            "J": ["薪酬", "工资", "社保"],
            "K": ["费用", "管理费", "销售费"],
            "L": ["借款", "负债", "债务"],
            "M": ["权益", "资本", "利润分配"],
            "N": ["税", "所得税", "增值税"],
        }

        for wp in workpapers:
            wp_code = wp.get("wp_code", "")
            wp_name = wp.get("wp_name", "").lower()
            prefix = wp_code[0].upper() if wp_code else ""

            # 直接名称匹配
            if any(kw in text for kw in [wp_name, wp_code.lower()]):
                stage = CODE_TO_STAGE.get(prefix, "unknown")
                matched.append({**wp, "stage": stage, "match_type": "direct"})
                continue

            # 循环关键词匹配
            keywords = cycle_keywords.get(prefix, [])
            if any(kw in text for kw in keywords):
                stage = CODE_TO_STAGE.get(prefix, "unknown")
                matched.append({**wp, "stage": stage, "match_type": "keyword"})

        return matched
