"""附件上传策略：附件类型枚举、扩展名白名单、恶意内容检查（spec attachment-security-baseline 需求 1）。

为什么单独成模块：
- ``attachment_type`` 会被拼进本地存储目录（``{root}/{project_id}/{attachment_type}/``），
  过去不做任何校验，传 ``../../x`` 即可把文件写到存储根之外。枚举在这里登记，服务层两个入口
  （``upload_attachment_file`` / ``create_attachment``）都调用 :func:`validate_attachment_type`。
- 扩展名白名单以附件管理页 ``ACCEPT_TYPES`` 为准（ADR-ASB-01）。治理侧
  ``ATTACHMENT_ALLOWED_MEDIA_TYPES`` 比平台支持的格式窄（缺 eml / msg / ofd / dwg / dxf / rar / 7z /
  heic / webp / md），直接套用会让现有格式上传失败；两边一致由
  ``tests/attachment_security_baseline/test_upload_policy.py`` 守住。
- 恶意内容检查复用治理侧 ``build_malware_scanner``（可执行 / 脚本签名 + 可选 ClamAV），
  不另写一份判定。
"""

from __future__ import annotations

from pathlib import Path

#: 附件类型登记表 = 现有写入方实际使用的取值 ∪ 证据声明（``workpaper_evidence_requirements.json``）的类型。
#: 新增取值必须先登记在这里；前端字面量与证据声明类型由守卫逐项核对。
ATTACHMENT_TYPES: frozenset[str] = frozenset({
    # 现有写入方
    "general",          # 上传表单默认值（附件管理页）
    "evidence",         # 底稿内上传（拖放区、C 类控制测试、底稿附件抽屉）
    "support",          # E1 授信 / 账户清单 / 承诺函识别自动建附件
    "workpaper_item",   # 行级附件（ItemAttachment、F2/F3/F4 行内上传）
    "confirmation",     # 函证发函件 / 回函件
    "bank_statement",   # E1 银行对账单识别自动建附件
    # 证据声明类型（尚无写入方，Spec B 起由上传时的证据类型选择写入）
    "voucher",
    "contract",
    "stocktake",
    "note",
})

#: 允许上传的扩展名（小写、含点）。与 ``AttachmentManagement.vue`` 的 ``ACCEPT_TYPES`` 逐项一致。
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf",
    ".doc", ".docx",
    ".xls", ".xlsx",
    ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif",
    ".txt", ".csv", ".md",
    ".heic", ".heif",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz",
    ".eml", ".msg",
    ".dxf", ".dwg", ".ofd",
})


class UploadRejected(ValueError):
    """上传被策略拒绝。``code`` 稳定、``message`` 为用户可读中文。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def as_detail(self) -> dict[str, str]:
        return {"error_code": self.code, "message": self.message}


def validate_attachment_type(attachment_type: str | None) -> str:
    """返回规范化后的附件类型；不在登记表内抛 :class:`UploadRejected`。

    ``None`` / 空串视为表单默认值 ``general``（与既有行为一致）。
    """
    value = (attachment_type or "general").strip()
    if value not in ATTACHMENT_TYPES:
        raise UploadRejected("ATTACHMENT_TYPE_NOT_ALLOWED", "不支持的附件类型")
    return value


def validate_extension(file_name: str | None) -> str:
    """返回小写扩展名；不在白名单内抛 :class:`UploadRejected`。"""
    suffix = Path(file_name or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UploadRejected("FILE_TYPE_NOT_ALLOWED", "不支持的文件类型")
    return suffix


async def scan_content(content: bytes) -> None:
    """恶意内容检查（可执行 / 脚本签名、EICAR，``CLAMAV_ENABLED`` 时再过 ClamAV）。

    装配与开关完全复用 ``build_malware_scanner``：两道检查都关闭时它返回 ``None``，这里随之放行。
    """
    from app.services.evidence_governance.attachment_security_gates import build_malware_scanner

    scanner = build_malware_scanner()
    if scanner is None:
        return
    if not await scanner(content):
        raise UploadRejected("UNSAFE_CONTENT", "文件内容不安全（可执行文件或脚本），已拒绝上传")


async def validate_upload(file_name: str | None, attachment_type: str | None, content: bytes) -> str:
    """上传前的整套校验，返回规范化后的附件类型。任何一项不通过都在落盘与建行之前抛出。"""
    normalized = validate_attachment_type(attachment_type)
    validate_extension(file_name)
    await scan_content(content)
    return normalized


def ensure_within_root(target: Path, root: Path) -> Path:
    """``target`` resolve 后必须位于 ``root`` 内，否则抛 :class:`UploadRejected`（纵深防御）。"""
    resolved_target = target.resolve()
    resolved_root = root.resolve()
    if resolved_target != resolved_root and not resolved_target.is_relative_to(resolved_root):
        raise UploadRejected("STORAGE_PATH_REJECTED", "附件存储路径不合法")
    return resolved_target
