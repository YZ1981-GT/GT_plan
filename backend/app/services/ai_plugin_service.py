"""AI能力预留接口服务

功能：
- 插件注册/列表/详情
- 启用/禁用插件
- 更新插件配置
- 预设插件列表与种子加载

Validates: Requirements 13.1-13.8
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extension_models import AIPlugin

PRESET_PLUGINS = [
    {
        "plugin_id": "invoice_verify",
        "plugin_name": "发票验真",
        "plugin_version": "0.1.0",
        "description": "对接税务系统自动验证发票真伪",
        "config": {"api_endpoint": "", "timeout": 30},
    },
    {
        "plugin_id": "business_info",
        "plugin_name": "企业工商信息查询",
        "plugin_version": "0.1.0",
        "description": "查询企业工商注册、股东、变更等信息",
        "config": {"api_endpoint": "", "timeout": 30},
    },
    {
        "plugin_id": "bank_reconcile",
        "plugin_name": "银行对账单智能核对",
        "plugin_version": "0.1.0",
        "description": "自动匹配银行对账单与账面记录",
        "config": {"match_threshold": 0.95},
    },
    {
        "plugin_id": "seal_check",
        "plugin_name": "印章识别与核验",
        "plugin_version": "0.1.0",
        "description": "OCR识别文档印章并与备案印章比对",
        "config": {"confidence_threshold": 0.9},
    },
    {
        "plugin_id": "voice_note",
        "plugin_name": "语音笔记转写",
        "plugin_version": "0.1.0",
        "description": "将审计现场语音笔记转为文字记录",
        "config": {"language": "zh-CN", "model": "whisper"},
    },
    {
        "plugin_id": "wp_review",
        "plugin_name": "底稿智能复核",
        "plugin_version": "0.1.0",
        "description": "AI辅助底稿质量复核与问题发现",
        "config": {"review_dimensions": 5},
    },
    {
        "plugin_id": "continuous_audit",
        "plugin_name": "持续审计监控",
        "plugin_version": "0.1.0",
        "description": "实时监控关键财务指标异常变动",
        "config": {"check_interval_hours": 24},
    },
    {
        "plugin_id": "team_chat",
        "plugin_name": "团队协作助手",
        "plugin_version": "0.1.0",
        "description": "审计团队内部AI辅助沟通与任务分配",
        "config": {"max_members": 50},
    },
]


class PluginExecutor:
    """插件执行器基类 — 所有插件 stub 的统一接口"""

    async def execute(self, params: dict) -> dict:
        raise NotImplementedError("子类必须实现 execute 方法")


class InvoiceVerifyExecutor(PluginExecutor):
    """发票验真插件（stub）— 对接税务局发票查验接口"""

    async def execute(self, params: dict) -> dict:
        # TODO: 对接税务局发票查验 API
        return {
            "plugin": "invoice_verify",
            "status": "stub",
            "message": "发票验真接口尚未对接，当前为占位实现",
            "params_received": params,
            "result": None,
        }


class BusinessInfoExecutor(PluginExecutor):
    """工商信息查询插件（stub）— 对接天眼查/企查查 API"""

    async def execute(self, params: dict) -> dict:
        # TODO: 对接天眼查/企查查 API 或定期导入缓存
        return {
            "plugin": "business_info",
            "status": "stub",
            "message": "工商信息查询接口尚未对接，当前为占位实现",
            "params_received": params,
            "result": None,
        }


class BankReconcileExecutor(PluginExecutor):
    """银行对账插件（stub）— 银行流水与账面逐笔自动对账"""

    async def execute(self, params: dict) -> dict:
        # TODO: 实现银行流水自动匹配算法
        return {
            "plugin": "bank_reconcile",
            "status": "stub",
            "message": "银行对账接口尚未实现，当前为占位实现",
            "params_received": params,
            "result": None,
        }


class SealCheckExecutor(PluginExecutor):
    """印章检测插件（stub）— 对比历史印章样本"""

    async def execute(self, params: dict) -> dict:
        # TODO: 实现印章 OCR 识别与比对
        return {
            "plugin": "seal_check",
            "status": "stub",
            "message": "印章检测接口尚未实现，当前为占位实现",
            "params_received": params,
            "result": None,
        }


class VoiceNoteExecutor(PluginExecutor):
    """语音笔记插件（stub）— 语音转文字"""

    async def execute(self, params: dict) -> dict:
        # TODO: 对接 Whisper 或其他 ASR 服务
        return {
            "plugin": "voice_note",
            "status": "stub",
            "message": "语音笔记接口尚未实现，当前为占位实现",
            "params_received": params,
            "result": None,
        }


class WpReviewExecutor(PluginExecutor):
    """底稿复核插件（stub）— AI 辅助检查底稿完整性"""

    async def execute(self, params: dict) -> dict:
        # TODO: 实现 LLM 驱动的底稿质量复核
        return {
            "plugin": "wp_review",
            "status": "stub",
            "message": "底稿智能复核接口尚未实现，当前为占位实现",
            "params_received": params,
            "result": None,
        }


class ContinuousAuditExecutor(PluginExecutor):
    """持续审计插件（stub）— 对接被审计单位 ERP"""

    async def execute(self, params: dict) -> dict:
        # TODO: 实现 ERP 数据实时监控
        return {
            "plugin": "continuous_audit",
            "status": "stub",
            "message": "持续审计接口尚未实现，当前为占位实现",
            "params_received": params,
            "result": None,
        }


class TeamChatExecutor(PluginExecutor):
    """团队协作插件（stub）— 多人 AI 群聊协作"""

    async def execute(self, params: dict) -> dict:
        # TODO: 实现多人 AI 协同对话空间
        return {
            "plugin": "team_chat",
            "status": "stub",
            "message": "团队协作接口尚未实现，当前为占位实现",
            "params_received": params,
            "result": None,
        }


# 插件 ID → 执行器映射
PLUGIN_EXECUTORS: dict[str, type[PluginExecutor]] = {
    "invoice_verify": InvoiceVerifyExecutor,
    "business_info": BusinessInfoExecutor,
    "bank_reconcile": BankReconcileExecutor,
    "seal_check": SealCheckExecutor,
    "voice_note": VoiceNoteExecutor,
    "wp_review": WpReviewExecutor,
    "continuous_audit": ContinuousAuditExecutor,
    "team_chat": TeamChatExecutor,
}


class AIPluginService:
    """AI插件服务"""

    async def register_plugin(
        self,
        db: AsyncSession,
        plugin_id: str,
        plugin_name: str,
        plugin_version: str,
        description: str | None = None,
        config: dict | None = None,
    ) -> dict:
        """注册新插件"""
        # 检查是否已存在
        existing = await db.execute(
            sa.select(AIPlugin).where(
                AIPlugin.plugin_id == plugin_id,
                AIPlugin.is_deleted == sa.false(),
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"插件 {plugin_id} 已存在")

        plugin = AIPlugin(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            plugin_description=description,
            config=config,
        )
        db.add(plugin)
        await db.flush()
        return self._to_dict(plugin)

    async def list_plugins(self, db: AsyncSession) -> list[dict]:
        """列出所有插件"""
        stmt = (
            sa.select(AIPlugin)
            .where(AIPlugin.is_deleted == sa.false())
            .order_by(AIPlugin.plugin_id)
        )
        result = await db.execute(stmt)
        return [self._to_dict(p) for p in result.scalars().all()]

    async def get_plugin(self, db: AsyncSession, plugin_id: str) -> dict | None:
        """获取插件详情"""
        result = await db.execute(
            sa.select(AIPlugin).where(
                AIPlugin.plugin_id == plugin_id,
                AIPlugin.is_deleted == sa.false(),
            )
        )
        plugin = result.scalar_one_or_none()
        return self._to_dict(plugin) if plugin else None

    async def enable_plugin(self, db: AsyncSession, plugin_id: str) -> dict:
        """启用插件"""
        plugin = await self._get_or_raise(db, plugin_id)
        plugin.is_enabled = True
        await db.flush()
        return self._to_dict(plugin)

    async def disable_plugin(self, db: AsyncSession, plugin_id: str) -> dict:
        """禁用插件"""
        plugin = await self._get_or_raise(db, plugin_id)
        plugin.is_enabled = False
        await db.flush()
        return self._to_dict(plugin)

    async def update_config(self, db: AsyncSession, plugin_id: str, config: dict) -> dict:
        """更新插件配置"""
        plugin = await self._get_or_raise(db, plugin_id)
        plugin.config = config
        await db.flush()
        return self._to_dict(plugin)

    def get_preset_plugins(self) -> list[dict]:
        """返回8个预设插件stub"""
        return PRESET_PLUGINS

    async def load_preset_plugins(self, db: AsyncSession) -> dict:
        """加载预设插件到数据库（幂等）"""
        loaded = 0
        skipped = 0
        for preset in PRESET_PLUGINS:
            existing = await db.execute(
                sa.select(AIPlugin).where(AIPlugin.plugin_id == preset["plugin_id"])
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            plugin = AIPlugin(
                plugin_id=preset["plugin_id"],
                plugin_name=preset["plugin_name"],
                plugin_version=preset["plugin_version"],
                plugin_description=preset.get("description"),
                config=preset.get("config"),
            )
            db.add(plugin)
            loaded += 1
        await db.flush()
        return {"loaded": loaded, "skipped": skipped, "message": f"已加载 {loaded} 个预设插件"}

    async def _get_or_raise(self, db: AsyncSession, plugin_id: str) -> AIPlugin:
        result = await db.execute(
            sa.select(AIPlugin).where(
                AIPlugin.plugin_id == plugin_id,
                AIPlugin.is_deleted == sa.false(),
            )
        )
        plugin = result.scalar_one_or_none()
        if not plugin:
            raise ValueError(f"插件 {plugin_id} 不存在")
        return plugin

    def _to_dict(self, plugin: AIPlugin) -> dict:
        return {
            "id": str(plugin.id),
            "plugin_id": plugin.plugin_id,
            "plugin_name": plugin.plugin_name,
            "plugin_version": plugin.plugin_version,
            "description": plugin.plugin_description,
            "is_enabled": plugin.is_enabled,
            "config": plugin.config,
        }

    async def execute_plugin(
        self, db: AsyncSession, plugin_id: str, params: dict
    ) -> dict:
        """执行插件（调用对应的 stub 执行器）"""
        plugin = await self._get_or_raise(db, plugin_id)
        if not plugin.is_enabled:
            raise ValueError(f"插件 {plugin_id} 未启用")

        executor_cls = PLUGIN_EXECUTORS.get(plugin_id)
        if not executor_cls:
            raise ValueError(f"插件 {plugin_id} 没有对应的执行器")

        executor = executor_cls()
        return await executor.execute(params)
