"""多语言支持服务

功能：
- 获取支持的语言列表
- 获取翻译字典
- 获取审计术语翻译
- 设置用户语言偏好

Validates: Requirements 4.1-4.4
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User

SUPPORTED_LANGUAGES = [
    {"code": "zh-CN", "name": "简体中文"},
    {"code": "en-US", "name": "English"},
]

TRANSLATIONS = {
    "zh-CN": {
        "app_title": "审计作业平台",
        "project": "项目",
        "workpaper": "底稿",
        "trial_balance": "试算表",
        "adjustment": "调整分录",
        "report": "报表",
        "audit_report": "审计报告",
        "materiality": "重要性水平",
        "sampling": "抽样",
        "disclosure": "附注",
        "save": "保存",
        "cancel": "取消",
        "confirm": "确认",
        "delete": "删除",
        "export": "导出",
        "import": "导入",
    },
    "en-US": {
        "app_title": "Audit Workbench",
        "project": "Project",
        "workpaper": "Workpaper",
        "trial_balance": "Trial Balance",
        "adjustment": "Adjustment Entry",
        "report": "Financial Report",
        "audit_report": "Audit Report",
        "materiality": "Materiality",
        "sampling": "Sampling",
        "disclosure": "Disclosure Notes",
        "save": "Save",
        "cancel": "Cancel",
        "confirm": "Confirm",
        "delete": "Delete",
        "export": "Export",
        "import": "Import",
    },
}

AUDIT_TERMS = {
    "zh-CN": {
        "AJE": "审计调整分录",
        "RJE": "重分类分录",
        "TB": "试算表",
        "PBC": "客户提供资料清单",
        "WP": "工作底稿",
        "KAM": "关键审计事项",
        "ISA": "国际审计准则",
        "CAS": "中国审计准则",
        "CAAT": "计算机辅助审计技术",
        "SAS": "审计抽样",
    },
    "en-US": {
        "AJE": "Audit Adjustment Entry",
        "RJE": "Reclassification Entry",
        "TB": "Trial Balance",
        "PBC": "Prepared By Client",
        "WP": "Working Paper",
        "KAM": "Key Audit Matter",
        "ISA": "International Standards on Auditing",
        "CAS": "China Auditing Standards",
        "CAAT": "Computer Assisted Audit Techniques",
        "SAS": "Statistical Audit Sampling",
    },
}


class I18nService:
    """多语言支持服务"""

    def get_languages(self) -> list[dict]:
        """返回支持的语言列表"""
        return SUPPORTED_LANGUAGES

    def get_translations(self, lang: str) -> dict:
        """返回指定语言的翻译字典"""
        if lang not in TRANSLATIONS:
            raise ValueError(f"不支持的语言: {lang}")
        return TRANSLATIONS[lang]

    def get_audit_terms(self, lang: str) -> dict:
        """返回审计术语翻译"""
        if lang not in AUDIT_TERMS:
            raise ValueError(f"不支持的语言: {lang}")
        return AUDIT_TERMS[lang]

    async def set_user_language(self, db: AsyncSession, user_id: UUID, lang: str) -> dict:
        """设置用户语言偏好"""
        valid_codes = [l["code"] for l in SUPPORTED_LANGUAGES]
        if lang not in valid_codes:
            raise ValueError(f"不支持的语言: {lang}")

        result = await db.execute(sa.select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")

        user.language = lang
        await db.flush()
        return {"user_id": str(user_id), "language": lang}
