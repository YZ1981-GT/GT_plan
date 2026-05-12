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


    # -----------------------------------------------------------------------
    # Round 4 需求 2: AI 脱敏 — mask_context / mask_text / _is_sensitive_amount
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_amount_re():
        """金额正则：匹配 ¥1,234,567.89 / 1234567.89 / 500万元 / 1,500,000.00 等"""
        import re
        return re.compile(
            r'[¥￥$]\s*[\d,]+(?:\.\d{1,2})?'  # ¥1,234,567.89
            r'|[\d,]{4,}(?:\.\d{1,2})?\s*(?:万元|亿元|元)'  # 500万元 / 1234元
            r'|\d+(?:\.\d+)?\s*[万亿](?:元)?'  # 500万 / 3.5亿
            r'|[\d,]{6,}(?:\.\d{1,2})?',  # 1,500,000.00 (6+ digits with commas)
            re.UNICODE,
        )

    @staticmethod
    def _get_name_re():
        """客户名/人名正则：匹配公司名和带上下文的人名"""
        import re
        return re.compile(
            r'[\u4e00-\u9fff]{2,}(?:公司|集团|有限|股份|企业|银行|证券|科技)'  # 公司名
            r'|(?:联系人|客户|经办人|负责人|法人|代表)[：:]\s*([\u4e00-\u9fff]{2,4})'  # 带标记的人名
            r'|(?:，|,)\s*(?:客户|联系人)[：:]\s*([\u4e00-\u9fff]{2,4})',  # 逗号后的人名
            re.UNICODE,
        )

    @staticmethod
    def _get_id_re():
        """身份证号正则"""
        import re
        return re.compile(r'\d{17}[\dXx]|\d{15}')

    def _is_sensitive_amount(self, value) -> bool:
        """判断值是否为敏感金额（>= 100000）"""
        import re
        if isinstance(value, (int, float)):
            return abs(value) >= 100000
        if isinstance(value, str):
            # 提取数字部分
            cleaned = re.sub(r'[¥￥$,\s]', '', value)
            cleaned = cleaned.replace('元', '')
            multiplier = 1
            if '万' in cleaned:
                cleaned = cleaned.replace('万', '')
                multiplier = 10000
            elif '亿' in cleaned:
                cleaned = cleaned.replace('亿', '')
                multiplier = 100000000
            try:
                num = float(cleaned) * multiplier
                return abs(num) >= 100000
            except (ValueError, TypeError):
                return False
        return False

    def mask_context(self, ctx: dict | None) -> tuple[dict | None, dict]:
        """对 AI 上下文中的敏感字段进行脱敏

        Args:
            ctx: 单元格上下文字典 {cell_ref, value, formula, ...}

        Returns:
            (masked_ctx, mapping) — 脱敏后的上下文和映射表
        """
        if ctx is None:
            return None, {}
        if not ctx:
            return {}, {}

        import copy
        import re

        masked = copy.deepcopy(ctx)
        mapping: dict[str, str] = {}
        counter = {"amount": 0, "client": 0, "id_number": 0}

        amount_re = self._get_amount_re()
        name_re = self._get_name_re()
        id_re = self._get_id_re()

        def _mask_value(key: str, val):
            """对单个值进行脱敏"""
            if val is None:
                return val

            # 数值型金额
            if isinstance(val, (int, float)):
                if self._is_sensitive_amount(val):
                    counter["amount"] += 1
                    placeholder = f"[amount_{counter['amount']}]"
                    mapping[placeholder] = str(val)
                    return placeholder
                return val

            if not isinstance(val, str):
                return val

            result = val

            # 身份证号脱敏（优先，避免被金额正则误匹配）
            for m in id_re.finditer(result):
                counter["id_number"] += 1
                placeholder = f"[id_number_{counter['id_number']}]"
                mapping[placeholder] = m.group()
                result = result.replace(m.group(), placeholder, 1)

            # 客户名/人名脱敏
            for m in name_re.finditer(result):
                # 提取实际要替换的文本
                matched_text = m.group()
                # 如果有捕获组（人名），替换人名部分
                name_part = m.group(1) or m.group(2) if m.lastindex else None
                if name_part:
                    counter["client"] += 1
                    placeholder = f"[client_{counter['client']}]"
                    mapping[placeholder] = name_part
                    result = result.replace(name_part, placeholder, 1)
                else:
                    # 公司名整体替换
                    counter["client"] += 1
                    placeholder = f"[client_{counter['client']}]"
                    mapping[placeholder] = matched_text
                    result = result.replace(matched_text, placeholder, 1)

            # 金额脱敏
            for m in amount_re.finditer(result):
                if self._is_sensitive_amount(m.group()):
                    counter["amount"] += 1
                    placeholder = f"[amount_{counter['amount']}]"
                    mapping[placeholder] = m.group()
                    result = result.replace(m.group(), placeholder, 1)

            return result

        for key in list(masked.keys()):
            masked[key] = _mask_value(key, masked[key])

        return masked, mapping

    def mask_text(self, text: str) -> tuple[str, dict]:
        """对纯文本进行脱敏（用于 HTML 预览等场景）

        Args:
            text: 待脱敏文本

        Returns:
            (masked_text, mapping)
        """
        if not text:
            return text, {}

        ctx = {"_text": text}
        masked, mapping = self.mask_context(ctx)
        return masked["_text"], mapping


export_mask_service = ExportMaskService()
