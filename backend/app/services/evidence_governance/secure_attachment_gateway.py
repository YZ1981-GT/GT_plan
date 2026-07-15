"""SecureAttachmentGateway — 上传攻击面前置审计与文件名清洗（Task 3.2, Wave 2）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R12
Design: §4.0 UploadAttempt/失败审计/隔离区, §5.1 流式上传与异步 finalize, §3.2 Facade
Properties: P1 (项目隔离), P3 (创建主体完备), P25 (command-root 唯一 + 同事务)

本模块实现 R1.1 的 **"先审计后验证"** 上传生命周期最小闭环，作为 Task 3.3（流式
hash/MIME/大小/恶意内容检查 + staged→finalize）、3.4（安全读取链）、3.5（版本替换）
的公共入口骨架。3.2 只负责：

1. **attempt-first 最小审计**（``begin_upload_attempt``）：每次上传尝试 **在任何内容验证前**
   先经 facade 持久一条最小 ``UploadAttempt(pending)``（project/year、清洗文件名、声明媒体
   类型、actor、attempted_at、outcome='pending'）。``detected_media_type/received_byte_size/
   content_hash`` 未可得时保持 NULL（design §4.0）。
2. **文件名清洗**（``sanitize_upload_filename``）：剥离路径分隔符/控制字符/前导点与
   traversal、限长；**只存清洗名**，绝不存原始未清洗文件名、绝对路径或凭据（design §4.0）。
3. **收敛同一 attempt**（``converge_upload_attempt``）：验证推进后 **更新同一条 attempt**
   （填 detected_media_type/received_byte_size/content_hash，并把 outcome 收敛为
   ``accepted|rejected|quarantined|failed`` + failure_category），**绝不另建匿名 attempt**
   （R1.1/R1.2）。
4. **facade 编排**：begin 与 converge 各是一条 facade 命令——command-root + 审计 transition +
   业务写 **同一事务**，scope/capability 受 ``attachment.create`` 门禁（design §3.1/§3.2/§7.1）。

事务/引擎边界（禁止分叉，见 ``check_evidence_no_fork``）：本网关不实现存储、不直连
Paperless/OCR；实际存储在 3.3 委托 :class:`AttachmentService`。begin 提交 pending attempt（使
崩溃仍留最小审计痕迹），内容验证在长事务之外进行，converge 再以第二条命令就地更新 **同一**
attempt——begin 命令一 command-root、converge 命令一 command-root、单 attempt 行。

设计留缝（forward-compatible）：``begin_upload_attempt`` / ``converge_upload_attempt`` 是稳定
seam——3.3 的流式接收在两者之间插入分块 hash/嗅探/背压/staged→finalize，算得
detected_media_type/received_byte_size/content_hash 与终态后调用 converge，无需改本文件签名。
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment
from app.models.evidence_governance_models import AttachmentVersion, QuarantineHandle, UploadAttempt
from app.services.evidence_governance.facade import (
    CommandRequest,
    CommandTxn,
    EvidenceGovernanceFacade,
)
from app.services.evidence_governance.frozen_contracts import (
    ERROR_CODE_HTTP_STATUS,
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)

# ---------------------------------------------------------------------------
# UploadAttempt outcome 值集（与 DB CHECK chk_upload_attempt_outcome 对齐）
# ---------------------------------------------------------------------------

#: attempt 初建状态。
UPLOAD_OUTCOME_PENDING = "pending"

#: attempt 可收敛到的终态集合（design §4.0）。
UPLOAD_TERMINAL_OUTCOMES: frozenset[str] = frozenset(
    {"accepted", "rejected", "quarantined", "failed"}
)

#: 全部合法 outcome（含 pending）。
UPLOAD_OUTCOMES: frozenset[str] = frozenset({UPLOAD_OUTCOME_PENDING}) | UPLOAD_TERMINAL_OUTCOMES

#: begin/converge 的稳定 command_type（幂等键在其上派生子键）。
_CMD_BEGIN = "attachment.upload.attempt"
_CMD_CONVERGE = "attachment.upload.converge"

#: 门禁能力（design §2.2）。
_CAPABILITY = "attachment.create"

#: 清洗后文件名最大长度（列 sanitized_file_name 为 VARCHAR(500)，保守取 255）。
DEFAULT_MAX_FILENAME_LENGTH = 255

_FALLBACK_FILENAME = "unnamed"

# 控制字符（含 DEL）与保留/设备/路径字符。
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_RESERVED_RE = re.compile(r'[/\\:*?"<>|]')
_PATH_SPLIT_RE = re.compile(r"[\\/]")


def sanitize_upload_filename(
    raw_file_name: str | None,
    *,
    max_length: int = DEFAULT_MAX_FILENAME_LENGTH,
) -> str:
    """把不可信原始文件名清洗为安全、可存审计的 basename（design §4.0）。

    保证（无论原始是绝对路径、traversal 还是含控制字符）：
      - 只保留最后一段 basename——所有路径分隔符（``/`` 与 ``\\``）及其之前的目录被丢弃，
        故绝对路径 / traversal 前缀不进入存储；
      - 剥离控制字符（``\\x00–\\x1f``、``\\x7f``）；
      - 保留/设备字符 ``/ \\ : * ? " < > |`` 替换为 ``_``；
      - 去掉前导点与空白（挫败 ``..``、``.hidden``、前导点 traversal），残留 ``..`` 归一为 ``_``；
      - 限长（超长时尽量保留扩展名）；空/纯点/纯空白结果回退为 ``"unnamed"``。

    仅返回清洗名——原始未清洗文件名/绝对路径/凭据绝不由本函数外泄或持久。
    """
    if not raw_file_name or not str(raw_file_name).strip():
        return _FALLBACK_FILENAME

    # 1) 只取最后一段 basename（同时兼容 POSIX 与 Windows 分隔符）。
    name = _PATH_SPLIT_RE.split(str(raw_file_name))[-1]
    # 2) 丢弃控制字符。
    name = _CONTROL_RE.sub("", name)
    # 3) 保留/设备/路径字符 → 下划线。
    name = _RESERVED_RE.sub("_", name)
    # 4) 去前导点/空白 + 两端空白（挫败 ".."/".hidden"/前导点 traversal）。
    name = name.lstrip(". ").strip()
    # 5) 残留连续点（traversal 主体）归一。
    name = name.replace("..", "_").strip()
    if not name:
        return _FALLBACK_FILENAME

    # 6) 限长，尽量保留扩展名。
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and 0 < len(ext) < max_length - 1:
            keep = max_length - len(ext) - 1
            name = f"{stem[:keep]}.{ext}"
        else:
            name = name[:max_length]
        name = name.strip() or _FALLBACK_FILENAME
    return name


def _actor_columns(actor: ActorContext) -> dict:
    """actor XOR 物理列投影（对齐 design Data Models 的 actor CHECK；P3）。"""
    return {
        "actor_type": actor.actor_type.value,
        "actor_user_id": actor.actor_user_id,
        "actor_service_identity_id": actor.actor_service_identity_id,
    }


@dataclass
class UploadAttemptRecord:
    """一次上传尝试的最小审计结果句柄。"""

    attempt_id: uuid.UUID
    command_root_id: uuid.UUID
    replayed: bool
    outcome: str


# ===========================================================================
# Task 3.3 (Wave 2) — 固定块流式接收 / 背压 / staged→finalize 状态机
# Requirements: R1, R2, R15 · Design: §4.0(quarantine/staging), §5.1(流式上传与异步
# finalize), §9.1/§9.2(SLO/背压) · Properties: P2, P4, P5, P29
# ===========================================================================

#: 固定读取块大小（流式接收边界；避免把整个 multipart 读入内存）。
DEFAULT_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MiB

#: 平台配置的单附件字节上限（design §4.0 "超过平台配置上限"）。
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MiB

#: quarantine/staging 缓冲高水位（背压 §9.2）；超过则 429 CAPACITY_BACKPRESSURE。
DEFAULT_QUARANTINE_HIGH_WATER_BYTES = 512 * 1024 * 1024  # 512 MiB

#: 嗅探所需的首部字节数。
_SNIFF_HEAD_BYTES = 512

# --- 稳定失败类别（写入 UploadAttempt.failure_category；design §4.0/§7.2）----------
FAILURE_EMPTY = "empty"
FAILURE_TOO_LARGE = "too_large"
FAILURE_TYPE_NOT_ALLOWED = "declared_type_not_allowed"
FAILURE_TYPE_MISMATCH = "media_type_mismatch"
FAILURE_BACKPRESSURE = "capacity_backpressure"
FAILURE_MALWARE = "malware_detected"
FAILURE_UNREADABLE = "unreadable"
FAILURE_FINALIZE = "finalize_failed"

# quarantine/version/attachment 状态命名（与 DB CHECK 对齐）。
_QUARANTINE_STAGED = "staged"
_QUARANTINE_QUARANTINED = "quarantined"
_QUARANTINE_PURGED = "purged"
_QUARANTINE_PROMOTED = "promoted"

_VERSION_STAGED = "staged"
_VERSION_AVAILABLE = "available"
_ATTACHMENT_PENDING = "pending"
_ATTACHMENT_AVAILABLE = "available"

# 命令类型（各是一条 facade 命令；幂等键在上层 key 上派生子键）。
_CMD_STAGE = "attachment.upload.stage"
_CMD_PROMOTE = "attachment.upload.promote"
_CMD_QUARANTINE = "attachment.upload.quarantine"


# ---------------------------------------------------------------------------
# magic-number MIME 嗅探（纯函数；新治理逻辑，不分叉任何引擎）
# ---------------------------------------------------------------------------

#: (魔数前缀, 规范化 detected media type)。顺序敏感（长前缀在前）。
_MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
    (b"PK\x03\x04", "application/zip"),  # OOXML(docx/xlsx/pptx)/zip
    (b"PK\x05\x06", "application/zip"),  # 空 zip
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/x-ole-storage"),  # legacy doc/xls/ppt
    (b"%!PS", "application/postscript"),
)

#: 声明类型 → 允许的 magic 家族（用于声明-识别一致性；未列出的声明类型从宽）。
_DECLARED_MAGIC_FAMILY: dict[str, frozenset[str]] = {
    "application/pdf": frozenset({"application/pdf"}),
    "image/png": frozenset({"image/png"}),
    "image/jpeg": frozenset({"image/jpeg"}),
    "image/gif": frozenset({"image/gif"}),
    "image/bmp": frozenset({"image/bmp"}),
    "image/tiff": frozenset({"image/tiff"}),
    "application/zip": frozenset({"application/zip"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset(
        {"application/zip"}
    ),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": frozenset(
        {"application/zip"}
    ),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": frozenset(
        {"application/zip"}
    ),
    "application/msword": frozenset({"application/x-ole-storage"}),
    "application/vnd.ms-excel": frozenset({"application/x-ole-storage"}),
    "application/vnd.ms-powerpoint": frozenset({"application/x-ole-storage"}),
}


def sniff_media_type(head: bytes | None) -> str | None:
    """从首部字节 magic number 识别 media type；未知返回 ``None``（纯函数）。

    只读首部，不解析全文；供流式接收边接收边嗅探（design §5.1）。
    """
    if not head:
        return None
    for prefix, media_type in _MAGIC_SIGNATURES:
        if head.startswith(prefix):
            return media_type
    return None


def media_types_compatible(declared: str | None, detected: str | None) -> bool:
    """声明类型与安全识别的实际类型是否一致（design §5.1）。

    - ``detected`` 无法识别（None）→ 不据此判定不一致（无法证伪，从宽）。
    - 已知声明类型必须落在其 magic 家族内（如声明 pdf 却识别为 png → 不一致）。
    - 未登记映射的声明类型（如 text/plain）从宽放行（不误伤纯文本/未知合法类型）。
    """
    if detected is None:
        return True
    fam = _DECLARED_MAGIC_FAMILY.get((declared or "").lower())
    if fam is None:
        return True
    return detected in fam


# ---------------------------------------------------------------------------
# QuarantineStore — 不可公开读取的隔离/暂存缓冲（design §4.0；新治理组件）
# ---------------------------------------------------------------------------


class InMemoryQuarantineStore:
    """进程内隔离/暂存缓冲（默认实现）。

    内容不可经附件下载/预览/EvidenceRef/OCR/AI/FormalOutput/archive 访问——本 store
    只被 gateway 内部持有，且拒绝内容在被拒时删除或加密擦除（``purge``）。生产可注入
    磁盘/对象存储实现；接口保持一致。

    单附件字节由 ``max_bytes`` 上限约束，全局在途字节由 ``buffered_bytes`` 暴露供背压。
    """

    def __init__(self) -> None:
        self._blobs: dict[str, bytearray] = {}

    def begin(self, key: str) -> None:
        self._blobs.setdefault(key, bytearray())

    def write(self, key: str, chunk: bytes) -> None:
        self._blobs.setdefault(key, bytearray()).extend(chunk)

    def size(self, key: str) -> int:
        return len(self._blobs.get(key, b""))

    def read(self, key: str) -> bytes:
        blob = self._blobs.get(key)
        if blob is None:
            raise KeyError(key)
        return bytes(blob)

    def buffered_bytes(self) -> int:
        return sum(len(b) for b in self._blobs.values())

    def purge(self, key: str, *, crypto_erase: bool = True) -> None:
        """删除或加密擦除隔离内容——拒绝后内容不得成为可访问文件（R1.2/design §4.0）。"""
        blob = self._blobs.get(key)
        if blob is not None and crypto_erase:
            for i in range(len(blob)):
                blob[i] = 0
        self._blobs.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._blobs


#: storage_finalizer 契约：把隔离内容委托给 AttachmentService 存储，返回永久 locator。
StorageFinalizer = Callable[..., "Awaitable[dict[str, str]]"]

#: 恶意内容检查钩子：返回 True 表示 clean（放行）；async 或 sync 皆可。
MalwareScanner = Callable[[bytes], "Awaitable[bool] | bool"]

#: 可读性检查钩子：返回 True 表示可读；async 或 sync 皆可。
ReadabilityChecker = Callable[[bytes, "str | None"], "Awaitable[bool] | bool"]


@dataclass
class _StreamedContent:
    """流式接收阶段的中间结果（未持久，尚未 staged）。"""

    quarantine_key: str
    quarantine_handle_id: uuid.UUID
    content_hash: str
    detected_media_type: str | None
    received_byte_size: int
    error_code: EvidenceErrorCode | None = None
    failure_category: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and self.failure_category is None


@dataclass
class UploadReceipt:
    """一次流式上传的结果。

    - ``outcome``：``accepted|rejected|quarantined|failed``（与 UploadAttempt 收敛终态一致）。
    - ``response_mode``：201（同步 finalize 完成）/ 202（staged，异步 finalize）/ 或失败 HTTP
      状态（413/415/422/429），供 router 映射；service 层不抛内容验证异常（scope/capability
      失败仍由 facade 抛 ``EvidenceGovernanceError``）。
    - staged/quarantined 内容不可被 EvidenceRef/OCR/AI/FormalOutput/Archive 引用
      （``availability != 'available'`` 且 attachment.state != 'available'）。
    """

    attempt_id: uuid.UUID
    outcome: str
    response_mode: int
    error_code: EvidenceErrorCode | None = None
    failure_category: str | None = None
    attachment_id: uuid.UUID | None = None
    attachment_version_id: uuid.UUID | None = None
    quarantine_handle_id: uuid.UUID | None = None
    content_hash: str | None = None
    detected_media_type: str | None = None
    received_byte_size: int = 0
    availability: str | None = None

    @property
    def is_available(self) -> bool:
        return self.outcome == "accepted" and self.availability == _VERSION_AVAILABLE


# ===========================================================================
# Task 3.4 (Wave 2) — 读取拒绝链：scope/权限/边界先于字节 I/O
# Requirements: R1, R12, R15 · Design: §3.1(信任边界), §5.1(read path), §7.2(稳定失败类别)
# Properties: P1(项目隔离), P2(存储边界封闭), P29(降级安全)
#
# 冻结契约（file_path_boundary_freeze.md / test_evidence_file_path_boundary_contract.py）：
#   C1 scope-first     — scope/权限校验先于目标名称、路径、stat/open/read。
#   C2 boundary-before-IO — 规范化后真实路径不在 Storage_Boundary 内时，字节读取器
#                          open/stat/read 调用计数必须为 0。
#   C3 opaque-locator  — 对外 locator 只能是 opaque/脱敏 locator 或受控下载 URL，
#                          绝不返回绝对路径/storage key/token。
# 本节的真实 StorageBoundaryResolver / LocatorProjection 满足同一 C1/C2/C3 语义。
# ===========================================================================

_STORAGE_TYPE_PAPERLESS = "paperless"
_PAPERLESS_SCHEME = "paperless://"

#: opaque scheme 前缀（``scheme://``）。paperless 之外的 opaque scheme（staged://、
#: quarantine://、evidence:// 等）都不是可读的本地文件系统路径 → 读取时拒绝。
_OPAQUE_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://")

# --- 读取拒绝原因类别（server-side 脱敏审计元数据；绝不返回给客户端/泄露路径）--------
READ_DENIAL_SCOPE = "scope_or_permission"
READ_DENIAL_BOUNDARY = "storage_boundary"
READ_DENIAL_UNAVAILABLE = "not_available"       # staged / quarantined / inactive
READ_DENIAL_INTEGRITY = "integrity_mismatch"    # version/hash 完整性失败
READ_DENIAL_MALWARE = "malware_gate"
READ_DENIAL_UNREADABLE = "readability_gate"
READ_DENIAL_STORAGE_DEGRADED = "storage_degraded"  # 存储不可用 → DEPENDENCY_DEGRADED

#: 读命令稳定 command_type（每次读是一条 facade 命令，记录 command-root 审计）。
_CMD_READ = "attachment.read"


@dataclass(frozen=True)
class ReadPlan:
    """``StorageBoundaryResolver`` 对一次读取的决策结果。

    - ``kind='local'``  ：规范化后仍在 Storage_Boundary 内的安全真实路径（``safe_path``）。
    - ``kind='remote'`` ：paperless 远程对象，字节由 ``AttachmentService`` 用服务凭据解析
      （治理层只委托，不本地读取）。
    - ``kind='rejected'``：越界 / 非法 opaque scheme / 空 key —— 字节读取器绝不被调用（C2）。
    """

    kind: str
    safe_path: str | None = None
    remote_locator: str | None = None

    @property
    def rejected(self) -> bool:
        return self.kind == "rejected"


class LocalByteReader:
    """默认本地字节读取器（spy-friendly：``stat`` / ``read`` 显式方法）。

    所有本地字节 I/O 都经此类的 ``read``/``stat`` 单一入口，测试可注入 spy 断言
    「scope/权限/边界失败时调用计数为 0」（C2）。本类不做边界判定——边界 containment
    在 :class:`StorageBoundaryResolver` 完成后才允许调用本类。
    """

    def stat(self, path: str) -> int:
        return os.stat(path).st_size

    def read(self, path: str) -> bytes:
        with open(path, "rb") as fh:
            return fh.read()


class StorageBoundaryResolver:
    """把 DB 中的 opaque ``storage_key`` 规范化为 Storage_Boundary 内的真实路径。

    冻结契约（C2 boundary-before-IO）：本类只做 **纯路径运算**，绝不触碰文件系统
    （不 ``stat``/``open``/``exists``）。规范化后仍位于某个 boundary root 内时返回安全路径，
    否则判为越界（traversal / 绝对逃逸 / UNC / 非 paperless opaque scheme），调用方据此在
    调用字节读取器 **之前** 拒绝，保证边界失败时字节 I/O 计数为 0。

    Storage_Boundary 根：``settings.ATTACHMENT_LOCAL_STORAGE_ROOT``（附件）与
    ``settings.STORAGE_ROOT``（底稿/模板/交付件/归档）。paperless 对象为远程，由
    ``AttachmentService`` 用服务凭据解析，不参与本地边界（design §3.1 第 3 条）。
    """

    def __init__(self, boundary_roots: Iterable[str | Path]) -> None:
        roots: list[Path] = []
        for r in boundary_roots:
            if not r:
                continue
            roots.append(Path(os.path.normpath(str(r))).absolute())
        self._roots: tuple[Path, ...] = tuple(roots)

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def normalize_within_boundary(self, path_value: str | None) -> Path | None:
        """把 ``path_value`` 规范化到某个 boundary root 内的真实路径（纯路径，无 I/O）。

        返回 ``None`` 表示越界。绝对路径按自身归一；相对路径同时按 CWD 与各 boundary root
        归一（存储层 ``_write_local_file`` 产出的 key 相对 CWD 已含 boundary 前缀），返回第一个
        落在 boundary 内的候选；任一含 ``..`` 逃逸出 root 的路径两种解释都不在 boundary 内 → 拒绝。
        """
        if not path_value:
            return None
        raw = Path(str(path_value))
        candidates: list[Path] = []
        if raw.is_absolute():
            candidates.append(Path(os.path.normpath(str(raw))).absolute())
        else:
            # (i) 相对 CWD（真实 _write_local_file 产出的 posix key 相对 CWD，已含 boundary 前缀）
            candidates.append(Path(os.path.normpath(str(Path.cwd() / raw))).absolute())
            # (ii) 相对各 boundary root（参考模型风格的纯相对 key）
            for root in self._roots:
                candidates.append(Path(os.path.normpath(str(root / raw))).absolute())
        for cand in candidates:
            for root in self._roots:
                try:
                    cand.relative_to(root)
                    return cand  # 返回落在 boundary 内的确定候选（读取的正是该受控路径）
                except ValueError:
                    continue
        return None

    def resolve_read_plan(self, storage_type: str | None, storage_key: str | None) -> ReadPlan:
        """把 ``(storage_type, storage_key)`` 解析为读取计划（纯路径运算，零 I/O）。"""
        key = (storage_key or "").strip()
        if not key:
            return ReadPlan(kind="rejected")
        # paperless 远程对象 → 委托 AttachmentService（服务凭据），不做本地边界。
        if key.startswith(_PAPERLESS_SCHEME) or (storage_type or "").lower() == _STORAGE_TYPE_PAPERLESS:
            return ReadPlan(kind="remote", remote_locator=key)
        # 其他 opaque scheme（staged://、quarantine://、evidence:// 等）不是可读本地文件 → 拒绝。
        if _OPAQUE_SCHEME_RE.match(key):
            return ReadPlan(kind="rejected")
        safe = self.normalize_within_boundary(key)
        if safe is None:
            return ReadPlan(kind="rejected")
        return ReadPlan(kind="local", safe_path=str(safe))

    def project_read_locator(self, attachment_id: uuid.UUID | str, storage_key: str | None = None) -> str:
        """C3：对外 opaque locator —— paperless scheme 或受控下载 URL，绝不返回绝对路径。"""
        if storage_key and storage_key.startswith(_PAPERLESS_SCHEME):
            return storage_key
        return f"/api/attachments/{attachment_id}/download"


def _effective_storage(version: "AttachmentVersion", attachment: "Attachment") -> tuple[str | None, str | None]:
    """确定可读版本的实际存储位置。

    finalize 后 ``AttachmentVersion.storage_key`` 保持不可变（staged locator），真实永久
    存储写在 ``config_snapshot['finalized_storage']`` 与 ``Attachment.file_path/storage_type``。
    读取以 finalized_storage 为准，回退 attachment.file_path/storage_type。
    """
    snap = version.config_snapshot or {}
    fin = snap.get("finalized_storage") if isinstance(snap, dict) else None
    fin = fin if isinstance(fin, dict) else {}
    storage_type = fin.get("storage_type") or attachment.storage_type
    storage_key = fin.get("storage_key") or fin.get("file_path") or attachment.file_path
    return storage_type, storage_key


@dataclass
class AttachmentReadResult:
    """一次安全读取的结果（内容字节 + 版本证据元数据）。"""

    attachment_id: uuid.UUID
    attachment_version_id: uuid.UUID
    version_no: int
    content: bytes
    content_hash: str | None
    media_type: str | None
    byte_size: int


class SecureAttachmentGateway:
    """上传攻击面前置审计与文件名清洗网关（3.2 最小闭环；3.3/3.4/3.5 在此扩展）。

    ``attachment_service`` 为 3.3 委托实际存储预留（本阶段不使用，禁止在此复制存储逻辑）。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        facade: EvidenceGovernanceFacade | None = None,
        attachment_service=None,  # 3.3 委托 AttachmentService 做实际存储/finalize
        quarantine_store: InMemoryQuarantineStore | None = None,
        storage_finalizer: StorageFinalizer | None = None,
        malware_scanner: MalwareScanner | None = None,
        readability_checker: ReadabilityChecker | None = None,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        quarantine_high_water_bytes: int = DEFAULT_QUARANTINE_HIGH_WATER_BYTES,
        allowed_media_types: Iterable[str] | None = None,
        mime_sniffer: Callable[[bytes | None], str | None] | None = None,
        # --- Task 3.4：安全读取链依赖 ---
        storage_boundary: StorageBoundaryResolver | None = None,
        boundary_roots: Iterable[str | Path] | None = None,
        byte_reader: LocalByteReader | None = None,
        remote_byte_reader: Callable[[str], "Awaitable[bytes] | bytes"] | None = None,
    ) -> None:
        self._db = db
        self._facade = facade or EvidenceGovernanceFacade(db)
        # 委托实际存储/finalize（禁止分叉：只包装 AttachmentService）。
        self._attachment_service = attachment_service
        self._quarantine = quarantine_store or InMemoryQuarantineStore()
        self._storage_finalizer = storage_finalizer
        self._malware_scanner = malware_scanner
        self._readability_checker = readability_checker
        self._max_upload_bytes = max_upload_bytes
        self._chunk_size = max(1, chunk_size)
        self._high_water = quarantine_high_water_bytes
        self._allowed_media_types = (
            frozenset(m.lower() for m in allowed_media_types)
            if allowed_media_types is not None
            else None
        )
        self._sniff = mime_sniffer or sniff_media_type
        # 安全读取链：StorageBoundaryResolver + spy-friendly 字节读取器。
        if storage_boundary is not None:
            self._storage_boundary = storage_boundary
        else:
            roots = boundary_roots
            if roots is None:
                from app.core.config import settings

                roots = [
                    settings.ATTACHMENT_LOCAL_STORAGE_ROOT,
                    settings.STORAGE_ROOT,
                ]
            self._storage_boundary = StorageBoundaryResolver(roots)
        self._byte_reader = byte_reader or LocalByteReader()
        self._remote_byte_reader = remote_byte_reader

    # -- 阶段一：内容验证前的最小 attempt（R1.1）--------------------------------

    async def begin_upload_attempt(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        raw_file_name: str | None,
        declared_media_type: str | None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        trace_id: str | None = None,
    ) -> UploadAttemptRecord:
        """在 **任何内容验证之前** 持久一条最小 ``UploadAttempt(pending)``。

        经 facade 命令执行：scope + ``attachment.create`` capability 门禁、command-root、
        审计 transition 与业务写同事务。``detected_media_type/received_byte_size/
        content_hash`` 保持 NULL，待 converge 更新（design §4.0/§5.1）。

        只存清洗后的文件名——原始未清洗文件名/绝对路径不进入审计记录。
        """
        sanitized = sanitize_upload_filename(raw_file_name)
        attempt_id = uuid.uuid4()
        actor_cols = _actor_columns(actor)

        async def _create(txn: CommandTxn):
            row = UploadAttempt(
                id=attempt_id,
                project_id=txn.project_id,
                audit_year=txn.audit_year,
                sanitized_file_name=sanitized,
                declared_media_type=declared_media_type,
                validation_outcome=UPLOAD_OUTCOME_PENDING,
                command_root_id=txn.command_root_id,
                **actor_cols,
            )
            self._db.add(row)
            await self._db.flush()
            await txn.record_transition(
                transition_type="upload_attempt.created",
                to_state=UPLOAD_OUTCOME_PENDING,
                metadata={"declared_media_type": declared_media_type},
            )
            return {"attempt_id": str(attempt_id)}

        req = CommandRequest(
            command_type=_CMD_BEGIN,
            idempotency_key=f"{idempotency_key}:attempt",
            actor=actor,
            actor_role=actor_role,
            project_id=project_id,
            audit_year=audit_year,
            capability=_CAPABILITY,
            trace_id=trace_id,
        )
        result = await self._facade.execute(req, _create)

        if result.replayed:
            # 重放：facade 未重跑业务 → 按 begin root 回读既有 attempt（幂等，不新建）。
            existing = await self._load_attempt_by_root(result.command_root_id)
            if existing is not None:
                return UploadAttemptRecord(
                    attempt_id=existing["id"],
                    command_root_id=result.command_root_id,
                    replayed=True,
                    outcome=existing["validation_outcome"],
                )
        return UploadAttemptRecord(
            attempt_id=attempt_id,
            command_root_id=result.command_root_id,
            replayed=result.replayed,
            outcome=UPLOAD_OUTCOME_PENDING,
        )

    # -- 阶段二：验证推进后收敛同一 attempt（R1.1）------------------------------

    async def converge_upload_attempt(
        self,
        *,
        attempt_id: uuid.UUID,
        outcome: str,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        project_id: uuid.UUID | None = None,
        audit_year: int | None = None,
        failure_category: str | None = None,
        detected_media_type: str | None = None,
        received_byte_size: int | None = None,
        content_hash: str | None = None,
        trace_id: str | None = None,
    ) -> UploadAttemptRecord:
        """把 **同一条** attempt 收敛到终态（不另建匿名 attempt；R1.1）。

        经 facade 命令执行：以 ``upload_attempt`` 对象重解析权威 scope（project 隔离）+
        capability 门禁 + command-root + 审计。填 detected_media_type/received_byte_size/
        content_hash 并把 ``validation_outcome`` 收敛为 accepted|rejected|quarantined|failed。

        ``outcome`` 必须是终态之一，否则 ``INVALID_STATE_TRANSITION``（目标零变化）。已处于终态
        的 attempt 再次收敛为无副作用（command 层幂等 + 业务层守卫）。
        """
        if outcome not in UPLOAD_TERMINAL_OUTCOMES:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                "converge outcome must be terminal",
            )

        async def _update(txn: CommandTxn):
            row = await self._db.get(UploadAttempt, attempt_id)
            # 权威 scope 已由 facade 对象解析校验；此处再确认对象存在且归属一致（脱敏）。
            if row is None or row.project_id != txn.project_id:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "upload attempt not found or forbidden",
                )

            prior = row.validation_outcome
            if prior in UPLOAD_TERMINAL_OUTCOMES:
                # 已收敛：幂等无副作用（不覆盖历史终态）。
                return {"attempt_id": str(attempt_id), "outcome": prior}

            if detected_media_type is not None:
                row.detected_media_type = detected_media_type
            if received_byte_size is not None:
                row.received_byte_size = received_byte_size
            if content_hash is not None:
                row.content_hash = content_hash
            row.validation_outcome = outcome
            row.failure_category = failure_category
            row.updated_at = datetime.now(timezone.utc)
            await self._db.flush()

            await txn.record_transition(
                transition_type="upload_attempt.converged",
                from_state=prior,
                to_state=outcome,
                metadata={
                    "failure_category": failure_category,
                    "detected_media_type": detected_media_type,
                    "received_byte_size": received_byte_size,
                    "content_hash": content_hash,
                },
            )
            return {"attempt_id": str(attempt_id), "outcome": outcome}

        req = CommandRequest(
            command_type=_CMD_CONVERGE,
            idempotency_key=f"{idempotency_key}:converge",
            actor=actor,
            actor_role=actor_role,
            project_id=project_id,
            audit_year=audit_year,
            capability=_CAPABILITY,
            object_type="upload_attempt",
            object_id=attempt_id,
            trace_id=trace_id,
        )
        result = await self._facade.execute(req, _update)

        # 重放时 facade 不重跑业务、result.result 为 None → 回读当前终态。
        final_outcome = outcome
        if result.result is not None:
            final_outcome = result.result.get("outcome", outcome)
        else:
            row = await self._db.get(UploadAttempt, attempt_id)
            if row is not None:
                final_outcome = row.validation_outcome
        return UploadAttemptRecord(
            attempt_id=attempt_id,
            command_root_id=result.command_root_id,
            replayed=result.replayed,
            outcome=final_outcome,
        )

    async def _load_attempt_by_root(self, command_root_id: uuid.UUID) -> dict | None:
        """按 begin command-root 回读既有 attempt（重放路径）。"""
        row = (
            (
                await self._db.execute(
                    sa.text(
                        "SELECT id, validation_outcome, failure_category, sanitized_file_name "
                        "FROM evidence_upload_attempts WHERE command_root_id = :r LIMIT 1"
                    ),
                    {"r": str(command_root_id)},
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    # =======================================================================
    # Task 3.3 — 固定块流式接收 + staged→finalize 状态机
    # =======================================================================

    async def receive_upload(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        raw_file_name: str | None,
        declared_media_type: str | None,
        chunks: "AsyncIterator[bytes] | Iterable[bytes]",
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        source_type: str | None = None,
        provider: str | None = None,
        obtained_at: datetime | None = None,
        is_key_evidence: bool = False,
        synchronous_finalize: bool = True,
        trace_id: str | None = None,
    ) -> UploadReceipt:
        """完整流式上传编排（begin → 流式接收 → staged → finalize/202 → converge）。

        插在 3.2 的 ``begin_upload_attempt``（内容验证前最小审计）与
        ``converge_upload_attempt``（收敛同一 attempt）之间：

        1. begin：先建 ``UploadAttempt(pending)``（不改 3.2 签名，内部调用）。
        2. 固定块流式：边接收边算 SHA-256 / 嗅探 magic MIME / 累加字节，执行 empty/超限/
           声明允许清单/声明-识别一致性/背压检查；任何失败都不创建可用 Attachment/Version，
           删除或加密擦除隔离内容，并把 **同一** attempt 收敛为 rejected/quarantined/failed。
        3. staged：初检通过后短事务持久 ``QuarantineHandle(staged)`` + ``Attachment(pending)``
           + ``AttachmentVersion(staged)``——内容仍不可被任何正式路径引用。
        4. finalize：
           - 同步（预算内）：跑恶意/可读性 gate + 委托 ``AttachmentService`` 存储，成功后短事务
             标记 version/current ``available`` 并收敛 attempt=accepted，返回 201。
           - 异步：返回 202（staged），finalize 交 ``finalize_staged_upload`` 由 worker 完成。
        """
        attempt = await self.begin_upload_attempt(
            project_id=project_id,
            audit_year=audit_year,
            raw_file_name=raw_file_name,
            declared_media_type=declared_media_type,
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

        # 声明类型允许清单（配置时）——在读取字节后仍可判定，但声明清单可先于内容判定。
        if (
            self._allowed_media_types is not None
            and (declared_media_type or "").lower() not in self._allowed_media_types
        ):
            return await self._reject_streaming(
                attempt=attempt,
                project_id=project_id,
                audit_year=audit_year,
                actor=actor,
                actor_role=actor_role,
                idempotency_key=idempotency_key,
                error_code=EvidenceErrorCode.MEDIA_TYPE_MISMATCH,
                failure_category=FAILURE_TYPE_NOT_ALLOWED,
                detected_media_type=None,
                received_byte_size=0,
                content_hash=None,
                quarantine_key=None,
                trace_id=trace_id,
            )

        # --- 2) 固定块流式接收到隔离缓冲 ---------------------------------------
        streamed = await self._stream_to_quarantine(
            attempt_id=attempt.attempt_id,
            chunks=chunks,
            declared_media_type=declared_media_type,
        )

        if not streamed.ok:
            # 无效内容：删除/加密擦除隔离缓冲，收敛同一 attempt=rejected（不创建 Attachment/Version）。
            self._quarantine.purge(streamed.quarantine_key, crypto_erase=True)
            return await self._reject_streaming(
                attempt=attempt,
                project_id=project_id,
                audit_year=audit_year,
                actor=actor,
                actor_role=actor_role,
                idempotency_key=idempotency_key,
                error_code=streamed.error_code,
                failure_category=streamed.failure_category,
                detected_media_type=streamed.detected_media_type,
                received_byte_size=streamed.received_byte_size,
                content_hash=None,
                quarantine_key=streamed.quarantine_key,
                trace_id=trace_id,
            )

        content = self._quarantine.read(streamed.quarantine_key)

        # --- 恶意内容检查（启用时）：隔离 + 加密擦除，绝不成为可访问文件 ------------
        if not await self._run_hook_bool(self._malware_scanner, content, default=True):
            return await self._quarantine_and_reject(
                attempt=attempt,
                streamed=streamed,
                project_id=project_id,
                audit_year=audit_year,
                actor=actor,
                actor_role=actor_role,
                idempotency_key=idempotency_key,
                failure_category=FAILURE_MALWARE,
                trace_id=trace_id,
            )

        # --- 3) staged：短事务持久 QuarantineHandle + Attachment + Version -------
        sanitized = sanitize_upload_filename(raw_file_name)
        staged = await self._persist_staged(
            attempt=attempt,
            project_id=project_id,
            audit_year=audit_year,
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            sanitized_file_name=sanitized,
            streamed=streamed,
            source_type=source_type,
            provider=provider,
            obtained_at=obtained_at,
            is_key_evidence=is_key_evidence,
            trace_id=trace_id,
        )

        if not synchronous_finalize:
            # 异步 finalize：返回 202；staged 内容不可被任何正式路径引用。
            return UploadReceipt(
                attempt_id=attempt.attempt_id,
                outcome=UPLOAD_OUTCOME_PENDING,
                response_mode=202,
                attachment_id=staged["attachment_id"],
                attachment_version_id=staged["version_id"],
                quarantine_handle_id=streamed.quarantine_handle_id,
                content_hash=streamed.content_hash,
                detected_media_type=streamed.detected_media_type,
                received_byte_size=streamed.received_byte_size,
                availability=_VERSION_STAGED,
            )

        # --- 4) 同步 finalize：gate + 委托存储 + 提交 available + 收敛 accepted ----
        return await self.finalize_staged_upload(
            attempt_id=attempt.attempt_id,
            attachment_id=staged["attachment_id"],
            attachment_version_id=staged["version_id"],
            quarantine_handle_id=streamed.quarantine_handle_id,
            quarantine_key=streamed.quarantine_key,
            sanitized_file_name=sanitized,
            content_hash=streamed.content_hash,
            detected_media_type=streamed.detected_media_type,
            received_byte_size=streamed.received_byte_size,
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            project_id=project_id,
            audit_year=audit_year,
            trace_id=trace_id,
            response_mode=201,
        )

    async def finalize_staged_upload(
        self,
        *,
        attempt_id: uuid.UUID,
        attachment_id: uuid.UUID,
        attachment_version_id: uuid.UUID,
        quarantine_handle_id: uuid.UUID,
        quarantine_key: str,
        sanitized_file_name: str,
        content_hash: str,
        detected_media_type: str | None,
        received_byte_size: int,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        project_id: uuid.UUID,
        audit_year: int | None,
        trace_id: str | None = None,
        response_mode: int = 201,
    ) -> UploadReceipt:
        """finalize：恶意/可读性 gate → 委托 ``AttachmentService`` 存储 → 提交 available。

        只有 finalize 存储、恶意检查（启用时）与可读性验证全部成功后，才在短事务中把
        版本/current 标记 ``available`` 并收敛 attempt=accepted（design §5.1）。任一失败：
        不创建可用 Attachment/Version（保持 staged 或转 quarantined），收敛 attempt 为
        quarantined/failed，删除或加密擦除隔离内容。
        """
        try:
            content = self._quarantine.read(quarantine_key)
        except KeyError:
            # 隔离内容缺失（已被清理）→ 安全失败，不产生 available 终态。
            return await self._reject_terminal(
                attempt_id=attempt_id,
                project_id=project_id,
                audit_year=audit_year,
                actor=actor,
                actor_role=actor_role,
                idempotency_key=idempotency_key,
                outcome="failed",
                error_code=EvidenceErrorCode.DEPENDENCY_DEGRADED,
                failure_category=FAILURE_FINALIZE,
                detected_media_type=detected_media_type,
                received_byte_size=received_byte_size,
                content_hash=content_hash,
                trace_id=trace_id,
                attachment_id=attachment_id,
                version_id=attachment_version_id,
            )

        # 恶意内容检查（异步 finalize 也在此把关一次）。
        if not await self._run_hook_bool(self._malware_scanner, content, default=True):
            self._quarantine.purge(quarantine_key, crypto_erase=True)
            await self._set_quarantine_state(
                quarantine_handle_id, _QUARANTINE_QUARANTINED, project_id=project_id,
                audit_year=audit_year, actor=actor, actor_role=actor_role,
                idempotency_key=idempotency_key, failure_category=FAILURE_MALWARE, trace_id=trace_id,
            )
            return await self._reject_terminal(
                attempt_id=attempt_id, project_id=project_id, audit_year=audit_year, actor=actor,
                actor_role=actor_role, idempotency_key=idempotency_key, outcome="quarantined",
                error_code=None, failure_category=FAILURE_MALWARE,
                detected_media_type=detected_media_type, received_byte_size=received_byte_size,
                content_hash=content_hash, trace_id=trace_id, attachment_id=attachment_id,
                version_id=attachment_version_id, availability=_VERSION_STAGED,
            )

        # 可读性验证。
        if not await self._run_hook_bool2(
            self._readability_checker, content, detected_media_type, default=True
        ):
            self._quarantine.purge(quarantine_key, crypto_erase=True)
            await self._set_quarantine_state(
                quarantine_handle_id, _QUARANTINE_QUARANTINED, project_id=project_id,
                audit_year=audit_year, actor=actor, actor_role=actor_role,
                idempotency_key=idempotency_key, failure_category=FAILURE_UNREADABLE, trace_id=trace_id,
            )
            return await self._reject_terminal(
                attempt_id=attempt_id, project_id=project_id, audit_year=audit_year, actor=actor,
                actor_role=actor_role, idempotency_key=idempotency_key, outcome="failed",
                error_code=None, failure_category=FAILURE_UNREADABLE,
                detected_media_type=detected_media_type, received_byte_size=received_byte_size,
                content_hash=content_hash, trace_id=trace_id, attachment_id=attachment_id,
                version_id=attachment_version_id, availability=_VERSION_STAGED,
            )

        # 委托 AttachmentService 做实际永久存储（禁止分叉存储逻辑）。
        try:
            finalized = await self._finalize_storage(
                project_id=project_id,
                file_name=sanitized_file_name,
                content=content,
                media_type=detected_media_type,
            )
        except EvidenceGovernanceError:
            # 存储降级：保持 staged，收敛 failed（不产生 available 终态，P29）。
            return await self._reject_terminal(
                attempt_id=attempt_id, project_id=project_id, audit_year=audit_year, actor=actor,
                actor_role=actor_role, idempotency_key=idempotency_key, outcome="failed",
                error_code=EvidenceErrorCode.DEPENDENCY_DEGRADED, failure_category=FAILURE_FINALIZE,
                detected_media_type=detected_media_type, received_byte_size=received_byte_size,
                content_hash=content_hash, trace_id=trace_id, attachment_id=attachment_id,
                version_id=attachment_version_id, availability=_VERSION_STAGED,
            )

        # 短事务：提交 available（version + attachment.state/current + quarantine promoted）。
        await self._promote_available(
            attachment_id=attachment_id,
            attachment_version_id=attachment_version_id,
            quarantine_handle_id=quarantine_handle_id,
            finalized=finalized,
            project_id=project_id,
            audit_year=audit_year,
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

        # 隔离缓冲已升格为永久存储 → 清除暂存副本（内容已在 AttachmentService 永久存储）。
        self._quarantine.purge(quarantine_key, crypto_erase=False)

        # 收敛同一 attempt=accepted（回填 detected/bytes/hash）。
        await self.converge_upload_attempt(
            attempt_id=attempt_id,
            outcome="accepted",
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            project_id=project_id,
            audit_year=audit_year,
            detected_media_type=detected_media_type,
            received_byte_size=received_byte_size,
            content_hash=content_hash,
            trace_id=trace_id,
        )

        return UploadReceipt(
            attempt_id=attempt_id,
            outcome="accepted",
            response_mode=response_mode,
            attachment_id=attachment_id,
            attachment_version_id=attachment_version_id,
            quarantine_handle_id=quarantine_handle_id,
            content_hash=content_hash,
            detected_media_type=detected_media_type,
            received_byte_size=received_byte_size,
            availability=_VERSION_AVAILABLE,
        )

    # -- 流式接收 ----------------------------------------------------------

    async def _stream_to_quarantine(
        self,
        *,
        attempt_id: uuid.UUID,
        chunks: "AsyncIterator[bytes] | Iterable[bytes]",
        declared_media_type: str | None,
    ) -> _StreamedContent:
        """固定块流式读取：增量 SHA-256 / magic 嗅探 / 累加字节 / 大小 / 背压。

        绝不把整个 multipart 读入内存——按 ``chunk_size`` 固定块处理，隔离缓冲达高水位时
        立即以 ``CAPACITY_BACKPRESSURE`` 拒绝（不无限缓存）。
        """
        quarantine_handle_id = uuid.uuid4()
        quarantine_key = f"quarantine://{quarantine_handle_id}"
        self._quarantine.begin(quarantine_key)

        hasher = hashlib.sha256()
        head = bytearray()
        received = 0

        def _fail(code: EvidenceErrorCode, category: str) -> _StreamedContent:
            return _StreamedContent(
                quarantine_key=quarantine_key,
                quarantine_handle_id=quarantine_handle_id,
                content_hash=hasher.hexdigest(),
                detected_media_type=sniff_media_type(bytes(head)) if head else None,
                received_byte_size=received,
                error_code=code,
                failure_category=category,
            )

        async for block in self._iter_fixed_blocks(chunks):
            if not block:
                continue
            # 背压：隔离/暂存缓冲达高水位 → 429（不无限缓存整个 multipart）。
            if self._quarantine.buffered_bytes() + len(block) > self._high_water:
                return _fail(EvidenceErrorCode.CAPACITY_BACKPRESSURE, FAILURE_BACKPRESSURE)
            # 大小上限（边接收边判定，超限即停）。
            if received + len(block) > self._max_upload_bytes:
                return _fail(EvidenceErrorCode.ATTACHMENT_TOO_LARGE, FAILURE_TOO_LARGE)
            if len(head) < _SNIFF_HEAD_BYTES:
                head.extend(block[: _SNIFF_HEAD_BYTES - len(head)])
            hasher.update(block)
            received += len(block)
            self._quarantine.write(quarantine_key, block)

        detected = self._sniff(bytes(head)) if head else None
        content_hash = hasher.hexdigest()

        # 空文件拒绝。
        if received == 0:
            return _StreamedContent(
                quarantine_key=quarantine_key,
                quarantine_handle_id=quarantine_handle_id,
                content_hash=content_hash,
                detected_media_type=detected,
                received_byte_size=0,
                error_code=EvidenceErrorCode.METADATA_INCOMPLETE,
                failure_category=FAILURE_EMPTY,
            )

        # 声明-识别一致性。
        if not media_types_compatible(declared_media_type, detected):
            return _StreamedContent(
                quarantine_key=quarantine_key,
                quarantine_handle_id=quarantine_handle_id,
                content_hash=content_hash,
                detected_media_type=detected,
                received_byte_size=received,
                error_code=EvidenceErrorCode.MEDIA_TYPE_MISMATCH,
                failure_category=FAILURE_TYPE_MISMATCH,
            )

        return _StreamedContent(
            quarantine_key=quarantine_key,
            quarantine_handle_id=quarantine_handle_id,
            content_hash=content_hash,
            detected_media_type=detected,
            received_byte_size=received,
        )

    async def _iter_fixed_blocks(
        self, source: "AsyncIterator[bytes] | Iterable[bytes]"
    ) -> "AsyncIterator[bytes]":
        """把任意 async/sync 字节源重切为 <= chunk_size 的固定块（有界内存）。"""
        size = self._chunk_size
        buf = bytearray()
        if hasattr(source, "__aiter__"):
            async for part in source:  # type: ignore[union-attr]
                buf.extend(part)
                while len(buf) >= size:
                    yield bytes(buf[:size])
                    del buf[:size]
        else:
            for part in source:  # type: ignore[union-attr]
                buf.extend(part)
                while len(buf) >= size:
                    yield bytes(buf[:size])
                    del buf[:size]
        if buf:
            yield bytes(buf)

    # -- staged 持久化 -----------------------------------------------------

    async def _persist_staged(
        self,
        *,
        attempt: UploadAttemptRecord,
        project_id: uuid.UUID,
        audit_year: int | None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        sanitized_file_name: str,
        streamed: _StreamedContent,
        source_type: str | None,
        provider: str | None,
        obtained_at: datetime | None,
        is_key_evidence: bool,
        trace_id: str | None,
    ) -> dict:
        """短事务：QuarantineHandle(staged) + Attachment(pending) + AttachmentVersion(staged)。"""
        attachment_id = uuid.uuid4()
        version_id = uuid.uuid4()
        actor_cols = _actor_columns(actor)
        file_type = _guess_file_type(sanitized_file_name, streamed.detected_media_type)
        staged_locator = f"staged://{streamed.quarantine_handle_id}"

        async def _stage(txn: CommandTxn):
            attachment = Attachment(
                id=attachment_id,
                project_id=txn.project_id,
                audit_year=txn.audit_year,
                file_name=sanitized_file_name,
                file_path=staged_locator,  # opaque staged locator（绝不返回绝对路径）
                file_type=file_type,
                file_size=streamed.received_byte_size,
                original_file_name=sanitized_file_name,
                source_type=source_type,
                obtained_at=obtained_at,
                provider=provider,
                is_key_evidence=is_key_evidence,
                metadata_status="incomplete",
                state=_ATTACHMENT_PENDING,
                storage_type="staged",
                ocr_status="pending",
                **actor_cols,
            )
            self._db.add(attachment)
            await self._db.flush()

            version = AttachmentVersion(
                id=version_id,
                attachment_id=attachment_id,
                project_id=txn.project_id,
                audit_year=txn.audit_year,
                version_no=1,
                storage_type="quarantine",
                storage_key=staged_locator,  # 不可变列：staged 时设定，之后不改
                media_type=streamed.detected_media_type,
                byte_size=streamed.received_byte_size,
                content_hash=streamed.content_hash,
                availability=_VERSION_STAGED,
                previous_version_id=None,
                **actor_cols,
            )
            self._db.add(version)
            await self._db.flush()

            handle = QuarantineHandle(
                id=streamed.quarantine_handle_id,
                upload_attempt_id=attempt.attempt_id,
                project_id=txn.project_id,
                audit_year=txn.audit_year,
                storage_key=streamed.quarantine_key,
                handle_state=_QUARANTINE_STAGED,
                content_hash=streamed.content_hash,
                byte_size=streamed.received_byte_size,
                detected_media_type=streamed.detected_media_type,
                is_publicly_readable=False,
                **actor_cols,
            )
            self._db.add(handle)
            await self._db.flush()

            await txn.record_transition(
                transition_type="attachment.staged",
                to_state=_VERSION_STAGED,
                metadata={
                    "attachment_id": str(attachment_id),
                    "version_id": str(version_id),
                    "content_hash": streamed.content_hash,
                },
            )
            await txn.enqueue_outbox(
                "attachment.staged",
                {"attachment_id": str(attachment_id), "version_id": str(version_id)},
            )
            return {"attachment_id": str(attachment_id), "version_id": str(version_id)}

        req = CommandRequest(
            command_type=_CMD_STAGE,
            idempotency_key=f"{idempotency_key}:stage",
            actor=actor,
            actor_role=actor_role,
            project_id=project_id,
            audit_year=audit_year,
            capability=_CAPABILITY,
            trace_id=trace_id,
        )
        await self._facade.execute(req, _stage)
        return {"attachment_id": attachment_id, "version_id": version_id}

    async def _promote_available(
        self,
        *,
        attachment_id: uuid.UUID,
        attachment_version_id: uuid.UUID,
        quarantine_handle_id: uuid.UUID,
        finalized: dict[str, str],
        project_id: uuid.UUID,
        audit_year: int | None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        trace_id: str | None,
    ) -> None:
        """短事务：version staged→available，attachment pending→available + current，quarantine promoted。"""

        async def _promote(txn: CommandTxn):
            version = await self._db.get(AttachmentVersion, attachment_version_id)
            attachment = await self._db.get(Attachment, attachment_id)
            if (
                version is None
                or attachment is None
                or attachment.project_id != txn.project_id
            ):
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "staged attachment not found or forbidden",
                )
            if version.availability == _VERSION_AVAILABLE:
                return {"attachment_id": str(attachment_id), "version_id": str(attachment_version_id)}

            # 只改可变列（availability / config_snapshot）；storage_key/hash/byte_size 不可变。
            version.availability = _VERSION_AVAILABLE
            version.config_snapshot = {"finalized_storage": dict(finalized)}
            await self._db.flush()

            attachment.state = _ATTACHMENT_AVAILABLE
            attachment.current_version_id = attachment_version_id
            attachment.storage_type = finalized.get("storage_type", attachment.storage_type)
            attachment.file_path = finalized.get("file_path", attachment.file_path)
            attachment.updated_at = datetime.now(timezone.utc)
            await self._db.flush()

            handle = await self._db.get(QuarantineHandle, quarantine_handle_id)
            if handle is not None and handle.handle_state == _QUARANTINE_STAGED:
                handle.handle_state = _QUARANTINE_PROMOTED
                await self._db.flush()

            await txn.record_transition(
                transition_type="attachment.available",
                from_state=_VERSION_STAGED,
                to_state=_VERSION_AVAILABLE,
                metadata={"attachment_id": str(attachment_id), "version_id": str(attachment_version_id)},
            )
            await txn.enqueue_outbox(
                "attachment.available",
                {"attachment_id": str(attachment_id), "version_id": str(attachment_version_id)},
            )
            return {"attachment_id": str(attachment_id), "version_id": str(attachment_version_id)}

        req = CommandRequest(
            command_type=_CMD_PROMOTE,
            idempotency_key=f"{idempotency_key}:promote",
            actor=actor,
            actor_role=actor_role,
            project_id=project_id,
            audit_year=audit_year,
            capability=_CAPABILITY,
            object_type="attachment",
            object_id=attachment_id,
            trace_id=trace_id,
        )
        await self._facade.execute(req, _promote)

    async def _set_quarantine_state(
        self,
        quarantine_handle_id: uuid.UUID,
        state: str,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        failure_category: str | None,
        trace_id: str | None,
    ) -> None:
        """把既有 QuarantineHandle 置为 quarantined/purged（含 purged_at）。"""

        async def _update(txn: CommandTxn):
            handle = await self._db.get(QuarantineHandle, quarantine_handle_id)
            if handle is None or handle.project_id != txn.project_id:
                return {}
            handle.handle_state = state
            handle.purged_at = datetime.now(timezone.utc)
            await self._db.flush()
            await txn.record_transition(
                transition_type=f"quarantine.{state}",
                to_state=state,
                metadata={"failure_category": failure_category},
            )
            return {"handle_id": str(quarantine_handle_id)}

        req = CommandRequest(
            command_type=_CMD_QUARANTINE,
            idempotency_key=f"{idempotency_key}:quarantine:{state}",
            actor=actor,
            actor_role=actor_role,
            project_id=project_id,
            audit_year=audit_year,
            capability=_CAPABILITY,
            trace_id=trace_id,
        )
        await self._facade.execute(req, _update)

    # -- 拒绝/隔离路径 ------------------------------------------------------

    async def _reject_streaming(
        self,
        *,
        attempt: UploadAttemptRecord,
        project_id: uuid.UUID,
        audit_year: int | None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        error_code: EvidenceErrorCode | None,
        failure_category: str | None,
        detected_media_type: str | None,
        received_byte_size: int,
        content_hash: str | None,
        quarantine_key: str | None,
        trace_id: str | None,
    ) -> UploadReceipt:
        """流式验证失败：收敛同一 attempt=rejected（不创建 Attachment/Version）。"""
        if quarantine_key is not None and self._quarantine.exists(quarantine_key):
            self._quarantine.purge(quarantine_key, crypto_erase=True)
        await self.converge_upload_attempt(
            attempt_id=attempt.attempt_id,
            outcome="rejected",
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            project_id=project_id,
            audit_year=audit_year,
            failure_category=failure_category,
            detected_media_type=detected_media_type,
            received_byte_size=received_byte_size or None,
            content_hash=content_hash,
            trace_id=trace_id,
        )
        return UploadReceipt(
            attempt_id=attempt.attempt_id,
            outcome="rejected",
            response_mode=(ERROR_CODE_HTTP_STATUS[error_code] if error_code else 422),
            error_code=error_code,
            failure_category=failure_category,
            content_hash=content_hash,
            detected_media_type=detected_media_type,
            received_byte_size=received_byte_size,
        )

    async def _quarantine_and_reject(
        self,
        *,
        attempt: UploadAttemptRecord,
        streamed: _StreamedContent,
        project_id: uuid.UUID,
        audit_year: int | None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        failure_category: str,
        trace_id: str | None,
    ) -> UploadReceipt:
        """恶意内容：持久 QuarantineHandle(quarantined) + 加密擦除 + 收敛 attempt=quarantined。"""

        async def _quar(txn: CommandTxn):
            handle = QuarantineHandle(
                id=streamed.quarantine_handle_id,
                upload_attempt_id=attempt.attempt_id,
                project_id=txn.project_id,
                audit_year=txn.audit_year,
                storage_key=streamed.quarantine_key,
                handle_state=_QUARANTINE_QUARANTINED,
                content_hash=streamed.content_hash,
                byte_size=streamed.received_byte_size,
                detected_media_type=streamed.detected_media_type,
                is_publicly_readable=False,
                purged_at=datetime.now(timezone.utc),
                **_actor_columns(actor),
            )
            self._db.add(handle)
            await self._db.flush()
            await txn.record_transition(
                transition_type="quarantine.quarantined",
                to_state=_QUARANTINE_QUARANTINED,
                metadata={"failure_category": failure_category},
            )
            return {"handle_id": str(streamed.quarantine_handle_id)}

        req = CommandRequest(
            command_type=_CMD_QUARANTINE,
            idempotency_key=f"{idempotency_key}:quarantine",
            actor=actor,
            actor_role=actor_role,
            project_id=project_id,
            audit_year=audit_year,
            capability=_CAPABILITY,
            trace_id=trace_id,
        )
        await self._facade.execute(req, _quar)

        # 加密擦除隔离缓冲——恶意内容绝不成为可访问文件。
        self._quarantine.purge(streamed.quarantine_key, crypto_erase=True)

        await self.converge_upload_attempt(
            attempt_id=attempt.attempt_id,
            outcome="quarantined",
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            project_id=project_id,
            audit_year=audit_year,
            failure_category=failure_category,
            detected_media_type=streamed.detected_media_type,
            received_byte_size=streamed.received_byte_size,
            content_hash=streamed.content_hash,
            trace_id=trace_id,
        )
        return UploadReceipt(
            attempt_id=attempt.attempt_id,
            outcome="quarantined",
            response_mode=422,
            failure_category=failure_category,
            quarantine_handle_id=streamed.quarantine_handle_id,
            content_hash=streamed.content_hash,
            detected_media_type=streamed.detected_media_type,
            received_byte_size=streamed.received_byte_size,
        )

    async def _reject_terminal(
        self,
        *,
        attempt_id: uuid.UUID,
        project_id: uuid.UUID,
        audit_year: int | None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        outcome: str,
        error_code: EvidenceErrorCode | None,
        failure_category: str | None,
        detected_media_type: str | None,
        received_byte_size: int,
        content_hash: str | None,
        trace_id: str | None,
        attachment_id: uuid.UUID | None = None,
        version_id: uuid.UUID | None = None,
        availability: str | None = None,
    ) -> UploadReceipt:
        """finalize 阶段失败：收敛 attempt 到 quarantined/failed，不产生 available 终态（P29）。"""
        await self.converge_upload_attempt(
            attempt_id=attempt_id,
            outcome=outcome,
            actor=actor,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            project_id=project_id,
            audit_year=audit_year,
            failure_category=failure_category,
            detected_media_type=detected_media_type,
            received_byte_size=received_byte_size or None,
            content_hash=content_hash,
            trace_id=trace_id,
        )
        return UploadReceipt(
            attempt_id=attempt_id,
            outcome=outcome,
            response_mode=(ERROR_CODE_HTTP_STATUS[error_code] if error_code else 422),
            error_code=error_code,
            failure_category=failure_category,
            attachment_id=attachment_id,
            attachment_version_id=version_id,
            content_hash=content_hash,
            detected_media_type=detected_media_type,
            received_byte_size=received_byte_size,
            availability=availability,
        )

    # -- 存储 finalize 委托（禁止分叉：只包装 AttachmentService）--------------

    async def _finalize_storage(
        self,
        *,
        project_id: uuid.UUID,
        file_name: str,
        content: bytes,
        media_type: str | None,
    ) -> dict[str, str]:
        """委托实际永久存储给注入的 finalizer 或 ``AttachmentService`` 存储原语。"""
        if self._storage_finalizer is not None:
            result = self._storage_finalizer(
                project_id=project_id,
                file_name=file_name,
                content=content,
                media_type=media_type,
            )
            if _is_awaitable(result):
                result = await result  # type: ignore[assignment]
            return dict(result)  # type: ignore[arg-type]
        return await self._default_finalize_storage(
            project_id=project_id, file_name=file_name, content=content
        )

    async def _default_finalize_storage(
        self, *, project_id: uuid.UUID, file_name: str, content: bytes
    ) -> dict[str, str]:
        """默认委托 ``AttachmentService`` 的存储原语（不复制 Paperless/local 逻辑）。"""
        svc = self._attachment_service
        if svc is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.DEPENDENCY_DEGRADED,
                "storage backend unavailable",
                retryable=True,
            )
        # 委托（非分叉）：调用 AttachmentService 既有存储原语，不在治理层重写它们。
        if getattr(svc, "primary_storage", "local") == "paperless" and svc.paperless_enabled():
            tmp = svc._write_temp_file(file_name, content)
            try:
                doc_id = await svc.upload_to_paperless(tmp.as_posix(), {"title": file_name})
            finally:
                tmp.unlink(missing_ok=True)
            if doc_id is not None:
                loc = svc._paperless_uri(doc_id)
                return {"storage_type": "paperless", "storage_key": loc, "file_path": loc}
        path = svc._write_local_file(
            project_id=project_id,
            file_name=file_name,
            content=content,
            attachment_type="evidence",
        )
        return {"storage_type": "local", "storage_key": path, "file_path": path}

    # =======================================================================
    # Task 3.4 — 安全读取链：scope/权限/边界先于字节 I/O
    # =======================================================================

    async def read_attachment_content(
        self,
        *,
        attachment_id: uuid.UUID | str,
        actor: ActorContext,
        actor_role: str,
        requested_project_id: uuid.UUID | None = None,
        requested_year: int | None = None,
        version_id: uuid.UUID | str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
        verify_integrity: bool = True,
    ) -> AttachmentReadResult:
        """安全读取附件内容，执行严格顺序的拒绝链（design §5.1 read path）。

        顺序（scope/权限/边界失败时字节读取器 open/stat/read 计数恒为 0，C1/C2）：
          (a) legacy/new ID 解析为确定根 + 确定版本（纯 DB 读，无字节 I/O）；
          (b) ``ProjectYearScopeGuard`` scope + 成员权限（由 facade 在业务回调 **之前** 执行）；
          (c) ``StorageBoundaryResolver`` 把 opaque storage_key 规范化为真实路径并确认
              仍在 Storage_Boundary 内（纯路径运算，零字节 I/O）。
        即使 (a)(b)(c) 全通过，仍在以下情形拒绝（脱敏审计）：
          - staged/quarantined/inactive（版本或附件非 available）→ 内容永不可读；
          - 存储不可用 → ``DEPENDENCY_DEGRADED``（P29，不产生可读结果）；
          - version/hash 完整性失败；malware/readability gate 失败。

        所有 scope/权限/边界/可用性/完整性/gate 失败对外统一返回脱敏
        ``SCOPE_NOT_FOUND_OR_FORBIDDEN``（不泄露路径或目标项目）；存储不可用返回
        ``DEPENDENCY_DEGRADED``。每次读取（含拒绝）经 facade 记录一条 command-root 审计事件。
        """
        idem = idempotency_key or f"read:{uuid.uuid4().hex}"
        # (a) 预解析 legacy alias → 确定根 + 确定版本（纯 DB 读，无字节 I/O）。
        root_id, alias_version_id = await self._resolve_alias_or_self(attachment_id)
        target_version_id = version_id or alias_version_id

        # facade 在业务回调之前执行 scope/权限门禁（scope-first）；这些拒绝发生在
        # command-root 之前，需在此补记脱敏安全审计事件（R1.3/R12.2：所有拒绝均记安全事件）。
        entered = {"business": False}

        async def _read(txn: CommandTxn) -> AttachmentReadResult:
            entered["business"] = True
            # (a) 载入确定根 + 版本（scope 已由 facade 用 object_type='attachment' 权威解析）。
            loaded = await self._load_read_target(root_id, target_version_id, txn.project_id)
            if loaded is None:
                raise self._read_denied()
            attachment, version = loaded

            # 可用性 gate：staged/quarantined/inactive 内容永不可读（先于边界与字节 I/O）。
            if attachment.state != _ATTACHMENT_AVAILABLE or version.availability != _VERSION_AVAILABLE:
                raise self._read_denied()

            # (c) 边界 containment（纯路径运算，零字节 I/O）。
            storage_type, storage_key = _effective_storage(version, attachment)
            plan = self._storage_boundary.resolve_read_plan(storage_type, storage_key)
            if plan.rejected:
                # 边界失败 → 在调用字节读取器之前拒绝（C2：open/stat/read 计数为 0）。
                raise self._read_denied()

            # ---- scope/权限/边界均已通过：字节 I/O 允许 ----
            content = await self._read_plan_bytes(plan)  # 存储不可用抛 DEPENDENCY_DEGRADED

            # version/hash 完整性校验（内容变化不能通过旧 hash；P5）。
            if verify_integrity and version.content_hash:
                if hashlib.sha256(content).hexdigest() != version.content_hash:
                    raise self._read_denied()

            # malware / readability gate（读路径再把关一次；失败脱敏拒绝）。
            if not await self._run_hook_bool(self._malware_scanner, content, default=True):
                raise self._read_denied()
            if not await self._run_hook_bool2(
                self._readability_checker, content, version.media_type, default=True
            ):
                raise self._read_denied()

            await txn.record_transition(
                transition_type="attachment.read",
                to_state="read",
                metadata={"version_no": version.version_no},
            )
            return AttachmentReadResult(
                attachment_id=attachment.id,
                attachment_version_id=version.id,
                version_no=version.version_no,
                content=content,
                content_hash=version.content_hash,
                media_type=version.media_type,
                byte_size=len(content),
            )

        req = CommandRequest(
            command_type=_CMD_READ,
            idempotency_key=idem,
            actor=actor,
            actor_role=actor_role,
            project_id=requested_project_id,
            audit_year=requested_year,
            capability=None,  # 读取由 scope 成员权限门禁（readonly 亦可读）；非高风险写能力。
            object_type="attachment",
            object_id=root_id,
            trace_id=trace_id,
        )
        try:
            result = await self._facade.execute(req, _read)
        except EvidenceGovernanceError as exc:
            # scope/权限失败发生在 facade 业务回调之前（无 command-root）→ 补记脱敏安全审计事件。
            # 业务回调内抛出的拒绝（可用性/边界/完整性/gate）已由 facade 记录 reject transition。
            if not entered["business"]:
                await self._record_read_denial(
                    attachment_root_id=root_id,
                    requested_project_id=requested_project_id,
                    requested_year=requested_year,
                    actor=actor,
                    idem=idem,
                    exc=exc,
                    trace_id=trace_id,
                )
            raise
        return result.result

    async def _record_read_denial(
        self,
        *,
        attachment_root_id: uuid.UUID,
        requested_project_id: uuid.UUID | None,
        requested_year: int | None,
        actor: ActorContext,
        idem: str,
        exc: EvidenceGovernanceError,
        trace_id: str | None,
    ) -> None:
        """scope/权限拒绝发生在 facade command-root 之前时，补记一条脱敏安全审计事件。

        使用请求 scope（若提供）或从对象重新解析的权威 scope 记录 ``attachment.read.denied``
        command-root + reject transition（reason_code 为脱敏错误码，绝不含路径/目标项目）。
        对象不存在而无法确定 scope 时保持脱敏 not-found，不强行伪造 project 上下文。
        """
        pid = requested_project_id
        ay = requested_year
        if pid is None:
            scope = await self._facade.scope_guard.resolve_object_scope(
                "attachment", attachment_root_id
            )
            if scope is not None:
                pid, ay = scope.project_id, scope.audit_year
        if pid is None:
            return
        # 清理 facade scope 检查遗留的只读事务状态，再以独立短事务记录安全事件。
        await self._db.rollback()
        root, created = await self._facade.audit.upsert_command_root(
            command_type="attachment.read.denied",
            idempotency_key=f"{idem}:denied",
            project_id=pid,
            audit_year=ay,
            actor=actor,
            trace_id=trace_id,
        )
        if created or root.result is None:
            await self._facade.audit.record_transition(
                command_root_id=root.id,
                transition_type="read_denied",
                actor=actor,
                to_state="rejected",
                metadata={"reason_code": exc.error_code.value},
            )
            await self._facade.audit.finalize_root(
                root, result="rejected", reason_code=exc.error_code.value
            )
        await self._db.commit()

    async def _resolve_alias_or_self(
        self, attachment_id: uuid.UUID | str
    ) -> tuple[uuid.UUID, uuid.UUID | None]:
        """legacy 旧 ID 经别名表解析为 (根, 确定版本)；新 ID 原样返回（版本后解析）。

        纯 DB 读（无字节 I/O）。旧 ID 不静默当作 "当前版本"（design §4.1）。
        """
        row = (
            (
                await self._db.execute(
                    sa.text(
                        "SELECT attachment_id, attachment_version_id "
                        "FROM legacy_attachment_alias WHERE old_attachment_id = :oid LIMIT 1"
                    ),
                    {"oid": str(attachment_id)},
                )
            )
            .mappings()
            .first()
        )
        if row is not None:
            return (
                uuid.UUID(str(row["attachment_id"])),
                uuid.UUID(str(row["attachment_version_id"])),
            )
        root = attachment_id if isinstance(attachment_id, uuid.UUID) else uuid.UUID(str(attachment_id))
        return root, None

    async def _load_read_target(
        self,
        root_id: uuid.UUID,
        version_id: uuid.UUID | str | None,
        project_id: uuid.UUID,
    ) -> tuple[Attachment, AttachmentVersion] | None:
        """载入确定根 + 确定版本；scope 归属再确认一致（脱敏，纯 DB 读）。"""
        attachment = await self._db.get(Attachment, root_id)
        if attachment is None or attachment.project_id != project_id or attachment.is_deleted:
            return None
        if version_id is not None:
            vid = version_id if isinstance(version_id, uuid.UUID) else uuid.UUID(str(version_id))
            version = await self._db.get(AttachmentVersion, vid)
        elif attachment.current_version_id is not None:
            version = await self._db.get(AttachmentVersion, attachment.current_version_id)
        else:
            version = None
        if (
            version is None
            or version.attachment_id != root_id
            or version.project_id != project_id
        ):
            return None
        return attachment, version

    async def _read_plan_bytes(self, plan: ReadPlan) -> bytes:
        """按读取计划取字节：本地经 spy-friendly 字节读取器；远程委托 AttachmentService。

        存储不可用（本地 I/O 失败 / 远程读取器缺失或失败）→ ``DEPENDENCY_DEGRADED``（P29）。
        """
        if plan.kind == "local":
            try:
                return self._byte_reader.read(plan.safe_path)  # type: ignore[arg-type]
            except EvidenceGovernanceError:
                raise
            except Exception as exc:  # 文件缺失/权限/IO 错误 → 存储不可用（不泄露路径）。
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.DEPENDENCY_DEGRADED,
                    "storage unavailable",
                    retryable=True,
                ) from exc
        if plan.kind == "remote":
            if self._remote_byte_reader is None:
                # paperless 字节由 AttachmentService 用服务凭据解析；未注入 → 降级。
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.DEPENDENCY_DEGRADED,
                    "remote storage reader unavailable",
                    retryable=True,
                )
            try:
                result = self._remote_byte_reader(plan.remote_locator)  # type: ignore[arg-type]
                if _is_awaitable(result):
                    result = await result
                if result is None:
                    raise EvidenceGovernanceError(
                        EvidenceErrorCode.DEPENDENCY_DEGRADED,
                        "remote storage unavailable",
                        retryable=True,
                    )
                return bytes(result)
            except EvidenceGovernanceError:
                raise
            except Exception as exc:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.DEPENDENCY_DEGRADED,
                    "remote storage unavailable",
                    retryable=True,
                ) from exc
        # 理论不可达：rejected 计划在字节 I/O 前已被拦截。
        raise self._read_denied()

    @staticmethod
    def _read_denied() -> EvidenceGovernanceError:
        """统一脱敏读取拒绝（不泄露路径/目标项目；scope/权限/边界/可用性/完整性/gate 共用）。"""
        return EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "attachment not found or forbidden",
        )

    # -- 钩子执行 ----------------------------------------------------------

    @staticmethod
    async def _run_hook_bool(hook, arg, *, default: bool) -> bool:
        if hook is None:
            return default
        result = hook(arg)
        if _is_awaitable(result):
            result = await result
        return bool(result)

    @staticmethod
    async def _run_hook_bool2(hook, a, b, *, default: bool) -> bool:
        if hook is None:
            return default
        result = hook(a, b)
        if _is_awaitable(result):
            result = await result
        return bool(result)


def _is_awaitable(obj: Any) -> bool:
    return hasattr(obj, "__await__")


def _guess_file_type(file_name: str, media_type: str | None) -> str:
    """从文件名/识别类型推断粗粒度 file_type（legacy 兼容列填充）。"""
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext in {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff"}:
        return "image"
    if ext in {"xls", "xlsx", "csv"}:
        return "excel"
    if ext in {"doc", "docx"}:
        return "word"
    if ext == "pdf":
        return "pdf"
    if media_type == "application/pdf":
        return "pdf"
    if media_type and media_type.startswith("image/"):
        return "image"
    return ext or "unknown"


__all__ = [
    "SecureAttachmentGateway",
    "UploadAttemptRecord",
    "UploadReceipt",
    "InMemoryQuarantineStore",
    "sanitize_upload_filename",
    "sniff_media_type",
    "media_types_compatible",
    # Task 3.4 — 安全读取链
    "StorageBoundaryResolver",
    "ReadPlan",
    "LocalByteReader",
    "AttachmentReadResult",
    "READ_DENIAL_SCOPE",
    "READ_DENIAL_BOUNDARY",
    "READ_DENIAL_UNAVAILABLE",
    "READ_DENIAL_INTEGRITY",
    "READ_DENIAL_MALWARE",
    "READ_DENIAL_UNREADABLE",
    "READ_DENIAL_STORAGE_DEGRADED",
    "UPLOAD_OUTCOME_PENDING",
    "UPLOAD_TERMINAL_OUTCOMES",
    "UPLOAD_OUTCOMES",
    "DEFAULT_MAX_FILENAME_LENGTH",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_MAX_UPLOAD_BYTES",
    "DEFAULT_QUARANTINE_HIGH_WATER_BYTES",
    "FAILURE_EMPTY",
    "FAILURE_TOO_LARGE",
    "FAILURE_TYPE_NOT_ALLOWED",
    "FAILURE_TYPE_MISMATCH",
    "FAILURE_BACKPRESSURE",
    "FAILURE_MALWARE",
    "FAILURE_UNREADABLE",
    "FAILURE_FINALIZE",
]
