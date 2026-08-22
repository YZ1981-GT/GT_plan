# Feature: dsh-agent-panel-integration — Task 1 存量测试的宿主授权解耦件
"""放行 AI 宿主授权的**唯一**测试替身（供 mock-DB 存量单元/PBT 测试复用）。

## 为什么需要它

Task 1 起，``app.routers.doc_ai_chat`` 的每个端点在读取上下文 / 历史 / 写 ai_content_log
之前先过公共 ``ResourceAccessResolver``（Req 2.1）；Task 2 起该前置升级为
``HostContextResolver``（授权 + 服务端反查可信 HostContext，Req 2.3/3.x）。存量的
``test_doc_ai_chat_router`` / ``test_doc_ai_chat_integration`` / ``test_doc_ai_chat_pbt``
测的是 **adopt 确认流、history 持久化、SSE streaming 这些机制**，用的是 ``AsyncMock``
数据库 —— 真实 ``gate_wp`` / ``VisibilityQueryService`` / ``ProjectUser`` 判定在 mock DB
上无法成立（且靠 ``AsyncMock`` 恰好"真值"通过属于偶然，不是判据）。

## 为什么这不是假绿

1. 授权行为本身由 ``backend/tests/dsh_agent_panel/test_task1_resource_access.py``
   在**真实 PostgreSQL** 上用真实 ``gate_wp`` / ``KnowledgeAccessPolicy`` /
   ``VisibilityRoleClassifier`` 守卫，并有变异检验 M01（把端点授权门换成"直接 allow"）
   证明"摘掉门就打红"。
2. 本替身以**函数名耦合**方式 patch ``_authorize_doc_host``：一旦该函数被删除或改名，
   ``mock.patch`` 立即抛 ``AttributeError``，这批测试会**响亮失败**而不是静默放行。
3. 替身只负责"宿主已授权"这一前提，端点内部的 project 绑定、fail-closed、写确认流等行为
   仍由存量断言真实执行。

单一真源：三个存量文件都从本模块导入，禁止再各自复制一份放行逻辑。
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

__all__ = ["patch_ai_host_authorization", "allow_ai_host"]

#: 被替换的目标（函数名耦合点；改名即让存量测试报错，不会静默放行）。
_TARGET = "app.routers.doc_ai_chat._authorize_doc_host"

#: 必须有项目绑定的宿主（真实服务端从业务模型反查得到，见 host_context 各 locate 方法）。
_PROJECT_BOUND_HOSTS = frozenset({"workpaper", "note", "report"})

#: 替身反查出的确定性项目 ID（固定值，便于断言；不与任何真实项目冲突）。
_STUB_RESOLVED_PROJECT_ID = uuid.UUID("00000000-0000-4000-8000-00000000dead")


async def _allow(
    db: Any,
    current_user: Any,
    *,
    doc_type: str,
    doc_id: str,
    project_id: str | None,
    action: Any,
    entrypoint: str,
    year: int | None = None,
):
    """返回与真实 resolver **同形**的已授权宿主上下文。

    形状由 ``AuthorizedHostContext.__post_init__`` 自校验：resource_id 不得为空串、
    项目类宿主必须有 project_id、全局知识模式不得携带 project_id —— 因此替身无法伪造出
    真实 ``HostContextResolver`` 不可能产生的上下文（Task 2 / Req 3.3）。

    注意替身**不做**服务端反查：note/report 的权威 project/year 反查、客户端断言一致性
    与"loader 唯一映射"由 ``tests/dsh_agent_panel/test_task2_host_context.py`` 在真实
    PostgreSQL 上守卫，并有 Task 2 变异脚本反证。
    """
    from app.services.ai_chat.contracts import HostType
    from app.services.ai_chat.host_context import AuthorizedHostContext

    host_type = HostType(doc_type)
    if host_type is HostType.global_knowledge:
        from app.services.ai_chat.contracts import GLOBAL_KNOWLEDGE_HOST_ID

        doc_id = GLOBAL_KNOWLEDGE_HOST_ID
    resolved_project = uuid.UUID(project_id) if project_id else None
    if resolved_project is None and host_type in _PROJECT_BOUND_HOSTS:
        # 真实 resolver 会从业务模型**反查**项目（history/clear 端点的 project_id 查询参数
        # 是可选的，正是因为服务端不依赖它）。替身用确定性 sentinel 模拟这一步，
        # 而不是留 None —— 留 None 会伪造出真实服务端不可能产生的"无项目底稿宿主"。
        resolved_project = _STUB_RESOLVED_PROJECT_ID
    return AuthorizedHostContext(
        principal_id=current_user.id,
        project_id=resolved_project,
        year=year,
        resource_type=host_type,
        resource_id=doc_id,
        display_label=f"{host_type.value} 测试替身",
        permission_binding="test:stub",
        allowed_actions=frozenset({action.value}),
    )


@contextmanager
def patch_ai_host_authorization():
    """上下文管理器形态（hypothesis ``@given`` 内使用，避免函数级 fixture 与例数交互）。"""
    with patch(_TARGET, _allow):
        yield


@pytest.fixture
def allow_ai_host():
    """pytest fixture 形态（普通 async 用例使用）。"""
    with patch(_TARGET, _allow):
        yield
