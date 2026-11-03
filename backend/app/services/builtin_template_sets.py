"""内置底稿模板集初始化（spec trim-followup-residual-findings-closure R2）。

原先生成弹窗每次打开都先 ``POST /api/template-sets/seed``：只读账号也发写请求，任何登录用户都能
改写内置集。现在由启动任务 ``seed_builtin_template_sets``（singleton：热重载交接时只在 primary 跑）
幂等初始化；手动端点 ``/api/template-sets/seed``（admin / partner）与种子一键加载走同一函数。

内置集定义仍是 :data:`app.services.template_engine.BUILTIN_TEMPLATE_SETS`（编码取自
``wp_account_mapping.json``）：按名称已存在且编码集合相同 ⇒ 不动；编码变了 ⇒ 更新编码与说明；
不存在 ⇒ 新建。每个内置集一个保存点：并发插入撞上 ``set_name`` 唯一约束时只回滚这一个、按已存在处理。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpTemplateSet

logger = logging.getLogger(__name__)


@dataclass
class BuiltinSeedResult:
    """一次初始化的结果：``changed`` = 新建 + 更新的模板集行。"""

    changed: list[WpTemplateSet] = field(default_factory=list)
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"inserted": self.inserted, "updated": self.updated, "unchanged": self.unchanged}


async def seed_builtin_template_sets_safely(db: AsyncSession) -> BuiltinSeedResult:
    """幂等写入内置模板集。只 flush 不 commit（调用方统一提交）。"""
    from app.services.template_engine import BUILTIN_TEMPLATE_SETS

    result = BuiltinSeedResult()
    for data in BUILTIN_TEMPLATE_SETS:
        try:
            async with db.begin_nested():
                existing = (await db.execute(
                    sa.select(WpTemplateSet).where(WpTemplateSet.set_name == data["set_name"])
                )).scalar_one_or_none()
                if existing is None:
                    row = WpTemplateSet(
                        set_name=data["set_name"],
                        template_codes=data["template_codes"],
                        applicable_audit_type=data["applicable_audit_type"],
                        applicable_standard=data.get("applicable_standard"),
                        description=data["description"],
                    )
                    db.add(row)
                    await db.flush()
                    result.changed.append(row)
                    result.inserted += 1
                    continue
                old_codes = existing.template_codes or []
                new_codes = data["template_codes"]
                if len(old_codes) == len(new_codes) and set(old_codes) == set(new_codes):
                    result.unchanged += 1
                    continue
                existing.template_codes = new_codes
                existing.description = data["description"]
                await db.flush()
                result.changed.append(existing)
                result.updated += 1
        except IntegrityError:
            # 别的进程刚插入同名内置集（set_name 唯一）：保存点已回滚，按已存在处理
            logger.info("内置模板集「%s」已由其他进程创建", data["set_name"])
            result.unchanged += 1
    return result


async def ensure_builtin_template_sets() -> BuiltinSeedResult:
    """启动任务入口：自开会话、初始化并提交。失败抛出（启动注册表按 best_effort 记失败、不挡启动）。"""
    from app.core.database import async_session

    async with async_session() as db:
        result = await seed_builtin_template_sets_safely(db)
        await db.commit()
    if result.inserted or result.updated:
        logger.warning("[启动] 内置模板集初始化：新建 %d、更新 %d", result.inserted, result.updated)
    return result
