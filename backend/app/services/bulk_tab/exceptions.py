"""bulk_tab 模块异常定义

集中定义编排层可能抛出的业务异常，供路由层捕获并转为 HTTP 错误响应。

注意：ConflictRejected 异常定义在 conflict_resolver.py 中（与策略逻辑共存），
可通过 `from app.services.bulk_tab import ConflictRejected` 或
`from app.services.bulk_tab.conflict_resolver import ConflictRejected` 引用。
"""
from __future__ import annotations

from fastapi import HTTPException


class BulkTabUserError(HTTPException):
    """批量导入导出面向用户的业务错误基类：中止操作，并把中文原因原样交给用户。

    直接继承 ``HTTPException``（本仓先例：``wp_visibility.denial.ExternalNotFound``）：
    FastAPI 原样转成 ``{code, message}`` 响应，同步导出路由无需逐个捕获 —— 路由与异步 runner
    的行号被 writer 清册（``backend/data/workpaper_writer_inventory.json``）钉扎，不能在那里加
    try/except。异步 runner 以 ``str(exc)`` 写任务错误，故 ``__str__`` 只返回中文原因
    （不带 ``422: `` / ``503: `` 前缀）。

    ``reason`` 供日志 / 测试区分失败类别，不参与响应体。
    """

    reason: str = "bulk_tab_error"

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(status_code=status_code, detail=message)

    def __str__(self) -> str:
        return str(self.detail)


class BulkExportPasswordInvalidError(BulkTabUserError):
    """导出密码含可打印 ASCII 以外的字符或超长 → HTTP 422（用户可改正，在任何导出工作之前）。

    限定字符集的原因：服务端按 UTF-8 编码密码加密，按本地代码页（如 GBK）处理密码的解压软件
    会对中文、全角字符算出不同的字节 ⇒ 密码明明输对了也打不开。只有 ASCII 在各编码下字节一致。
    """

    reason = "password_invalid"

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class BulkExportNothingToExportError(BulkTabUserError):
    """所选范围一张 Tab 都导不出来 → HTTP 422，不返回空 ZIP（原先静默返回、界面提示「已导出」）。

    ``counts``：按跳过类别计数（``manifest.skipped`` 的 ``skip_reason`` 与 ``unsupported_cycle``），
    只用于日志 / 测试；用户看到的是 ``detail`` 里的中文汇总。
    """

    reason = "nothing_to_export"

    def __init__(self, message: str, *, counts: dict[str, int] | None = None) -> None:
        super().__init__(message, status_code=422)
        self.counts: dict[str, int] = dict(counts or {})


class BulkExportEncryptionError(BulkTabUserError):
    """请求了密码保护却无法产出**加密** ZIP —— 一律中止导出，绝不退回明文 ZIP。"""

    reason: str = "encryption_error"


class BulkExportEncryptionUnavailableError(BulkExportEncryptionError):
    """服务器缺 AES 加密组件（pyzipper）→ HTTP 503（缺服务端组件，沿用 libreoffice_unavailable 惯例）。"""

    reason = "encryption_unavailable"

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class BulkExportEncryptionFailedError(BulkExportEncryptionError):
    """加密过程抛错，或产物复核发现未加密 / 条目不一致 → HTTP 500。"""

    reason = "encryption_failed"

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


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
