"""审计类型扩展服务

功能：
- 获取所有审计类型及描述
- 获取审计类型推荐配置（模板集、程序、报告模板）

Validates: Requirements 5.1-5.2
"""

from __future__ import annotations

AUDIT_TYPES = [
    {
        "type": "annual_financial",
        "name": "年度财务报表审计",
        "description": "对企业年度财务报表发表审计意见",
        "template_sets": ["standard", "listed"],
    },
    {
        "type": "ipo",
        "name": "IPO审计",
        "description": "首次公开发行股票相关审计",
        "template_sets": ["ipo"],
    },
    {
        "type": "soe",
        "name": "国有企业审计",
        "description": "国有企业专项审计",
        "template_sets": ["soe_notes"],
    },
    {
        "type": "internal",
        "name": "内部审计",
        "description": "企业内部控制与合规审计",
        "template_sets": ["simplified"],
    },
    {
        "type": "special_purpose",
        "name": "专项审计",
        "description": "特定目的审计（如清算审计、离任审计等）",
        "template_sets": ["simplified"],
    },
    {
        "type": "due_diligence",
        "name": "尽职调查",
        "description": "并购重组相关财务尽职调查",
        "template_sets": ["standard"],
    },
]

RECOMMENDATIONS = {
    "annual_financial": {
        "template_set": "standard",
        "procedures": [
            "风险评估程序", "控制测试", "实质性分析程序",
            "细节测试", "期后事项审查", "持续经营评估",
        ],
        "report_templates": ["standard_unqualified", "standard_qualified"],
    },
    "ipo": {
        "template_set": "ipo",
        "procedures": [
            "历史财务信息审计", "盈利预测审核", "内控有效性评价",
            "关联交易核查", "税务合规审查", "重大合同审查",
        ],
        "report_templates": ["ipo_audit_report", "ipo_comfort_letter"],
    },
    "soe": {
        "template_set": "soe_notes",
        "procedures": [
            "国有资产保值增值审计", "经济责任审计",
            "重大决策合规审查", "三重一大事项审查",
        ],
        "report_templates": ["soe_audit_report", "soe_management_letter"],
    },
    "internal": {
        "template_set": "simplified",
        "procedures": [
            "内部控制评价", "合规性测试", "运营效率评估",
        ],
        "report_templates": ["internal_audit_report"],
    },
    "special_purpose": {
        "template_set": "simplified",
        "procedures": [
            "专项审计程序", "特定事项核查",
        ],
        "report_templates": ["special_purpose_report"],
    },
    "due_diligence": {
        "template_set": "standard",
        "procedures": [
            "财务数据分析", "资产质量评估", "或有负债核查",
            "关联交易核查", "税务风险评估",
        ],
        "report_templates": ["dd_report"],
    },
}


class AuditTypeService:
    """审计类型扩展服务"""

    def get_audit_types(self) -> list[dict]:
        """返回所有审计类型及描述"""
        return AUDIT_TYPES

    def get_type_recommendation(self, audit_type: str) -> dict:
        """返回指定审计类型的推荐配置"""
        if audit_type not in RECOMMENDATIONS:
            raise ValueError(f"未知的审计类型: {audit_type}")
        rec = RECOMMENDATIONS[audit_type]
        # 找到对应的类型信息
        type_info = next((t for t in AUDIT_TYPES if t["type"] == audit_type), None)
        return {
            "audit_type": audit_type,
            "name": type_info["name"] if type_info else audit_type,
            **rec,
        }
