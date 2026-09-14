"""附件对外定位符投影（C3 opaque-locator 单一真源）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Baseline: R1/R14 §6.1 C3 — 兼容响应的 ``file_path`` 只能是 opaque 定位符
（受控下载 URL 或 ``paperless://`` scheme），**绝不返回绝对路径或原始 storage key**。

本模块是投影逻辑的唯一真源：
- 治理层 ``StorageBoundaryResolver.project_read_locator`` 委托本函数；
- legacy ``AttachmentService._to_dict`` 也委托本函数。

为什么单独成模块（而非从治理网关 import）：``secure_attachment_gateway`` 依赖
``EvidenceGovernanceFacade`` 等治理层重依赖，且治理层反向委托 ``AttachmentService``；
若 legacy 服务直接 import 治理网关会造成分层倒置/循环导入。本模块仅依赖 stdlib，
供两层共享，满足「禁止分叉」（no-fork）——投影语义只有一处实现。
"""

from __future__ import annotations

import uuid

#: paperless 远程对象的 opaque scheme 前缀（本身即脱敏 locator，可安全对外）。
PAPERLESS_SCHEME = "paperless://"
#: paperless storage_type 标识。
STORAGE_TYPE_PAPERLESS = "paperless"


def project_attachment_locator(
    attachment_id: uuid.UUID | str,
    *,
    storage_type: str | None = None,
    storage_key: str | None = None,
) -> str:
    """把存储位置投影为对外安全 opaque 定位符（C3）。

    - paperless（``storage_key`` 以 ``paperless://`` 开头）→ 返回该 opaque scheme；
    - 其他一切（本地绝对路径 / 原始 local storage key / 未知）→ 返回受控下载 URL
      ``/api/attachments/{id}/download``。

    ``storage_type`` 仅作辅助信号（paperless 附件的 ``file_path`` 在入库时已被
    规范化为 ``paperless://documents/{id}``，故 scheme 即权威判据）。任何情况下
    都不会返回绝对文件系统路径或原始 local storage key。
    """
    key = (storage_key or "").strip()
    if key.startswith(PAPERLESS_SCHEME):
        return key
    # storage_type 声明为 paperless 但 key 不是 scheme（异常/legacy 行）：
    # 无法凭空构造 scheme，退回受控下载 URL —— 仍是 opaque，绝不泄露真实位置。
    return f"/api/attachments/{attachment_id}/download"


__all__ = [
    "PAPERLESS_SCHEME",
    "STORAGE_TYPE_PAPERLESS",
    "project_attachment_locator",
]
