"""程序链端到端用例的公共夹具（真实 PostgreSQL + 真实应用，每例一个外层事务，结束整体回滚）。

``db``：``create_savepoint`` 会话（路由里的 commit / rollback 只动保存点）；底稿文件生成到 tmp_path。
``side_writes``（自动启用）：操作日志 / 拒绝记录 / 哈希链审计走独立连接，会在真库留下引用回滚数据的行 ⇒ 换成内存记录。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.services import wp_template_init_service
from app.services.wp_visibility.epoch_cache import reset_epoch_cache


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", tmp_path / "wp_storage")
    monkeypatch.chdir(tmp_path)
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    reset_epoch_cache()
    try:
        yield s
    finally:
        try:
            from app.main import app

            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
        finally:  # 回滚不依赖任何导入成功
            await s.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()
            reset_epoch_cache()


@pytest.fixture(autouse=True)
def side_writes(monkeypatch):
    from app.middleware import audit_log
    from app.services import audit_logger_enhanced
    from app.services.wp_visibility.denial import DenialResponder

    seen: dict[str, list] = {"logs": [], "denials": [], "audit": []}

    async def _log(**kw):
        seen["logs"].append(kw)

    async def _denial(self, **kw):
        seen["denials"].append(kw)

    async def _audit(self, *args, **kw):
        seen["audit"].append(kw)

    monkeypatch.setattr(audit_log, "_write_log", _log)
    monkeypatch.setattr(DenialResponder, "_write_outbox", _denial)
    monkeypatch.setattr(type(audit_logger_enhanced.audit_logger), "log_action", _audit)
    return seen
