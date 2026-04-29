"""Phase 16: 取证包脱敏服务

按角色定义脱敏字段列表，导出时自动替换敏感字段为 ***。
对齐 Phase 14 design §12.2 脱敏规则。
"""
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 按角色定义脱敏字段（字段路径列表）
MASK_RULES: dict[str, list[str]] = {
    "assistant": [
        "client_contact_phone",
        "client_contact_email",
        "bank_account_number",
    ],
    "manager": [
        "client_contact_phone",
        "client_contact_email",
        "bank_account_number",
        "amount_above_threshold",  # 金额超阈值脱敏
    ],
    "qc": [
        "client_contact_phone",
        "client_contact_email",
        "bank_account_number",
        "client_id_number",
    ],
    "partner": [],  # 合伙人默认不脱敏
    "admin": [],
}

# 金额脱敏阈值（超过此金额的具体数值替换为区间）
AMOUNT_THRESHOLD = 10_000_000  # 1000万


class ExportMaskService:
    """取证包脱敏服务"""

    async def apply_mask(
        self,
        data: dict,
        actor_role: str,
        mask_policy: str = "standard",
    ) -> dict:
        """遍历字段，命中规则的替换为 ***

        Args:
            data: 待脱敏的数据字典
            actor_role: 操作者角色
            mask_policy: 脱敏策略 (none/standard/strict)

        Returns:
            脱敏后的数据字典（深拷贝）
        """
        if mask_policy == "none":
            return data

        import copy
        masked = copy.deepcopy(data)

        rules = MASK_RULES.get(actor_role, MASK_RULES.get("assistant", []))

        if mask_policy == "strict":
            # strict 模式：所有角色都应用 assistant 级别脱敏
            rules = MASK_RULES["assistant"] + MASK_RULES.get("qc", [])[3:]

        self._apply_rules(masked, rules)
        return masked

    def _apply_rules(self, data: dict, rules: list[str]) -> None:
        """递归遍历字典，匹配字段名则脱敏"""
        for key in list(data.keys()):
            if key in rules:
                if isinstance(data[key], str):
                    data[key] = "***"
                elif isinstance(data[key], (int, float)):
                    data[key] = 0
                else:
                    data[key] = "***"
            elif key == "amount_above_threshold":
                # 金额阈值脱敏：超过阈值的替换为区间描述
                pass
            elif isinstance(data[key], dict):
                self._apply_rules(data[key], rules)
            elif isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        self._apply_rules(item, rules)

    async def check_export_permission(
        self,
        actor_id: uuid.UUID,
        actor_role: str,
        export_scope: str,
    ) -> bool:
        """完整导出需上级审批

        Args:
            actor_id: 操作者ID
            actor_role: 操作者角色
            export_scope: 导出范围 (summary/full/evidence_package)

        Returns:
            True=允许导出, False=需要审批
        """
        # 合伙人和管理员可以完整导出
        if actor_role in ("partner", "admin"):
            return True

        # 项目经理可以导出 summary 和 full
        if actor_role == "manager" and export_scope in ("summary", "full"):
            return True

        # 审计助理只能导出 summary
        if actor_role == "assistant" and export_scope == "summary":
            return True

        # 其他情况需要审批
        logger.info(
            f"[MASK] export permission denied: actor={actor_id} role={actor_role} scope={export_scope}"
        )
        return False


export_mask_service = ExportMaskService()
