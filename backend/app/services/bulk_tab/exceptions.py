"""bulk_tab 模块异常定义

集中定义编排层可能抛出的业务异常，供路由层捕获并转为 HTTP 错误响应。

注意：ConflictRejected 异常定义在 conflict_resolver.py 中（与策略逻辑共存），
可通过 `from app.services.bulk_tab import ConflictRejected` 或
`from app.services.bulk_tab.conflict_resolver import ConflictRejected` 引用。
"""
from __future__ import annotations


class AcnrCatalogUnavailableError(Exception):
    """ACNR catalog 不可用时抛出。

    当 ManifestBuilder 尝试从 ACNR catalog 加载路由元数据失败时，
    抛出此异常以阻止 bulk 操作继续，绝不静默退回分散 JSON。

    路由层应捕获此异常并返回 HTTP 503 + 提示「ACNR catalog 不可用」。

    Requirements: 7.4
    """

    def __init__(self, message: str = "ACNR catalog 不可用", cause: Exception | None = None) -> None:
        self.cause = cause
        super().__init__(message)
