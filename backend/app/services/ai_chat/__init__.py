"""AI 对话受控内核（Feature: dsh-agent-panel-integration）

Phase A 的安全边界从本包开始：任何 AI 端点在读取资源 label / 摘要 / 正文 / 索引片段
之前，必须先经 ``access.ResourceAccessResolver`` 取得允许决策。

模块边界：
  - ``contracts``：宿主/资源/动作/拒绝码/决策的服务端单一真源（无 IO）。
  - ``access``：``ResourceAccessResolver`` —— 只编排既有公开权限服务，不复制权限算法。
  - ``host_context``：``HostContextResolver`` —— 把客户端 ``HostRef`` 反查成可信
    ``AuthorizedHostContext``（每宿主专属业务 loader，客户端值只作一致性断言）。
"""

from app.services.ai_chat import access, contracts, host_context  # noqa: F401

__all__ = ["access", "contracts", "host_context"]
