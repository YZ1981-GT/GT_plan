"""multipart 流式摄取与 private quarantine 隔离区。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.6, 3.7

## 本模块交付什么、不交付什么

**交付**：把 multipart 字节流式写进 private quarantine、流式 SHA-256、
扩展名/MIME/ZIP magic 三重校验、UploadArtifact 状态机、TTL 幂等清理。

**不交付**（边界由测试锁死，防止误接线）：

* 🔴 **不生成** HTML / OnlyOffice config / WOPI URL / project artifact /
  runtime inventory entry。Requirement 3.2「preflight 前不得公开、执行、
  交给 OnlyOffice、生成项目底稿或进入 active runtime inventory」在这里的
  实现方式是**结构性**的：本模块没有任何产出这类对象的函数，`storage key`
  只由随机 id 构造、只落在 quarantine 子树内。
* 不实现 package scanner / semantic preflight（Task 5 / 6）。
* 不做 DB 持久化——Task 7 的四 lifecycle repositories 才是状态真源；
  本模块的 manifest JSON 是隔离区内的本地索引，遵循平台既有
  `ledger_import_upload_service` 范式（`sharedfs://` URI + `manifest.json`）。

## 平台既有范式（禁复制第二份）

参照 `app/services/ledger_import_upload_service.py`：`uuid4().hex` 随机
identity、1MiB chunk 流式写、逐块大小上限校验、`manifest.json` 落盘、
`shutil.rmtree` 失败清理。本模块与其**并列**，不复用其 project bundle 结构
（账表上传是「多文件 bundle + 导入流水线」，模板摄取是「单文件 + 安全隔离」，
生命周期不同，混用会让 TTL 语义串台）。

## 文件名只作展示值（Requirement 3.1）

原文件名经 ``display_filename`` 清洗后**只用于 UI 展示与日志**，绝不参与
storage identity 构造。否则「同名覆盖」「路径穿越」两条攻击面同时打开。
storage key = ``{random_id}/{random_id}.bin``，与输入文件名零关联。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Protocol, Sequence

from app.services.custom_template_ingestion.policy import (
    POLICY_V1,
    CustomTemplateIngestionPolicy,
    ResourceObservation,
    validate_against_policy,
)

logger = logging.getLogger(__name__)

#: 流式读取块大小，与 ledger 上传保持一致（1 MiB）。
CHUNK_SIZE: int = 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# 0) 可注入时钟与可注入文件源（Requirement 6.7：测试不得依赖真实墙钟）
# ─────────────────────────────────────────────────────────────────────────────


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """生产时钟。timestamptz 回写必须 Python 侧转 datetime。"""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def _utc_now(clock: Clock) -> datetime:
    value = clock.now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class FileSource(Protocol):
    """上传文件的最小接口。

    与 FastAPI ``UploadFile`` 兼容（有 async ``read`` 与可选 ``filename``），
    测试可用纯内存实现注入，不必构造真实 multipart。
    """

    @property
    def filename(self) -> str | None: ...

    @property
    def content_type(self) -> str | None: ...

    async def read(self, size: int | None = None) -> bytes: ...


# ─────────────────────────────────────────────────────────────────────────────
# 1) UploadArtifact 状态机（Requirement 6.1 / 3.2）
# ─────────────────────────────────────────────────────────────────────────────


class ArtifactState(str, Enum):
    """UploadArtifact 生命周期状态。

    🔴 Requirement 6.1：本枚举**只表达 quarantine/preflight 域**，绝不含
    publication 或 project current 状态。枚举成员封闭即结构性保证。
    """

    QUARANTINED = "QUARANTINED"
    PREFLIGHT_READY = "PREFLIGHT_READY"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


#: 允许的状态迁移。未登记 = 非法。
ALLOWED_TRANSITIONS: dict[ArtifactState, frozenset[ArtifactState]] = {
    ArtifactState.QUARANTINED: frozenset({
        ArtifactState.PREFLIGHT_READY,
        ArtifactState.PREFLIGHT_FAILED,
        ArtifactState.REJECTED,
        ArtifactState.EXPIRED,
    }),
    ArtifactState.PREFLIGHT_READY: frozenset({
        ArtifactState.REJECTED,
        ArtifactState.EXPIRED,
    }),
    ArtifactState.PREFLIGHT_FAILED: frozenset({
        ArtifactState.REJECTED,
        ArtifactState.EXPIRED,
    }),
    ArtifactState.REJECTED: frozenset({ArtifactState.EXPIRED}),
    ArtifactState.EXPIRED: frozenset(),
}

#: 非 active 终态 —— 这些状态下的字节可以被 retention 删除。
#: PREFLIGHT_READY 仍持有可继续推进的字节，不可当终态删。
TERMINAL_STATES: frozenset[ArtifactState] = frozenset({
    ArtifactState.PREFLIGHT_FAILED,
    ArtifactState.REJECTED,
    ArtifactState.EXPIRED,
})


class InvalidTransition(ValueError):
    """非法状态迁移。"""


def transition(current: ArtifactState, to: ArtifactState) -> None:
    """校验并声明一次状态迁移。

    🔴 未登记的迁移抛错而不是静默允许 —— 静默允许会让「QUARANTINED → ACTIVE」
    这类跨域跳转成为可能，正是 Requirement 6.1 禁止的混合状态表达。
    """
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if to not in allowed:
        raise InvalidTransition(
            f"非法状态迁移: {current.value} → {to.value}（允许 {sorted(s.value for s in allowed)}）"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2) 文件名清洗 —— 只作展示值（Requirement 3.1 / 3.7）
# ─────────────────────────────────────────────────────────────────────────────

#: 允许扩展的白名单（Requirement 4.3 / 4.4：只 .xlsx 可 preflight，.xlsm 可隔离）。
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".xlsm"})

#: ZIP 文件 magic（OOXML 是 zip 容器）。
ZIP_MAGIC: bytes = b"PK\x03\x04"

#: 展示文件名允许的最大长度。
MAX_DISPLAY_FILENAME_LEN: int = 200

#: Windows 保留设备名。作为目录名（即使带扩展名）在 win32 上非法，
#: 命中时追加尾部点 ``.`` 使其失去保留语义。
WINDOWS_RESERVED_NAMES: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

# _safe_org_component 内部使用（模块私有别名，保持调用点简洁）
_WINDOWS_RESERVED_NAMES: frozenset[str] = WINDOWS_RESERVED_NAMES

#: 控制字符与路径分隔符（含反斜杠，防 Windows 路径穿越展示）。
_FILENAME_STRIP_RE = re.compile(r"[\x00-\x1f\x7f/\\\\]")


def display_filename(raw: str | None) -> str:
    """清洗原文件名为纯展示值。

    🔴 返回值**禁止**用于构造 storage key。清洗后为空则回落到字面量，
    而不是抛错——上传流程不应因文件名怪异而失败。

    清洗规则：
    1. 取 basename（去掉所有 ``/`` 与 ``\\``）；
    2. 剥控制字符（含 NUL、退格、ESC、BEL）；
    3. 剥首尾的多余点与空格（防 Windows ``file..`` / 隐藏文件语义），
       但**保留扩展名前的点**——否则 ``.xlsx`` 会变成 ``xlsx``，
       扩展名白名单判定（``extension_of``）随之失效；
    4. 截断到 ``MAX_DISPLAY_FILENAME_LEN``。
    """
    if not raw:
        return "upload.bin"
    name = str(raw).strip().replace("\\", "/").rsplit("/", 1)[-1]
    name = _FILENAME_STRIP_RE.sub("", name)
    name = _strip_surrounding(name)
    if not name:
        return "upload.bin"
    if len(name) > MAX_DISPLAY_FILENAME_LEN:
        name = name[:MAX_DISPLAY_FILENAME_LEN]
    return name


def _strip_surrounding(name: str) -> str:
    """剥首尾的点与空格，但保留扩展名前那个点，并折叠扩展名前多余空格。

    规则：
    * 头部：剥空格与点，直到第一个非点非空格字符。``...hidden.xlsx`` →
      ``hidden.xlsx``。若整串只有点/空格（``"..."``）或只有扩展名（``.xlsx``），
      剥光会让扩展名判定失效，故这类情况**不剥头**。
    * 尾部：剥空格与多余的点，直到命中第一个非点非空格字符（文件名主体末字符）
      为止。``file...`` → ``file``，``file.xlsx`` → ``file.xlsx``。
    * 扩展名前的所有空格被剥掉（``spaced   .xlsx`` → ``spaced.xlsx``）——
      Windows 会保留尾部空格并视作不同文件，且会让扩展名判定不稳定。

    🔴 顺序：先判"整串是否无主体"，再剥头，最后剥尾。剥头必须在剥尾之前判断，
    否则 ``.xlsx`` 会被当成"只有点"而保留，但先剥尾又会让 ``file..`` 的尾部
    点被吃掉——两阶段各取一段，互不覆盖。
    """
    result = name.strip(" ")
    if not result:
        return result

    # 判"主体"是否非空：取最后一个点之后的 stem 段，剥掉点/空格后仍有内容
    # 才算有主体。注意扩展名字符本身（``.xlsx`` 里的 ``xlsx``）**不算主体**，
    # 否则 ``.xlsx`` 会被判为"有主体"从而剥掉扩展名前的点。
    stem = result.rsplit(".", 1)[0] if "." in result else result
    has_body = any(c not in ". " for c in stem)
    if has_body:
        # 有主体 → 可以安全剥头
        start = 0
        while start < len(result) and result[start] in ". ":
            start += 1
        body = result[start:]
    else:
        # 无主体（"... " 或 ".xlsx"）→ 不剥头，保留原样
        body = result

    # 剥尾：剥空格与点，剥到遇到非点非空格即停
    end = len(body)
    while end > 0 and body[end - 1] in ". ":
        end -= 1
    body = body[:end]

    # 剥掉扩展名前的所有空格（``spaced   .xlsx`` → ``spaced.xlsx``）
    body = re.sub(r" +(\.[^ .]+)$", r"\1", body)
    return body


def extension_of(raw: str | None) -> str:
    """取扩展名（小写，含点）。用于白名单判定，不用于 storage key。

    🔴 ``raw`` 为空时返回空串而非回落展示名的扩展名——``display_filename(None)``
    回落 ``upload.bin`` 只用于 UI 展示，把 ``.bin`` 当成上传扩展名会让空上传
    通过白名单判定之外的推断路径。
    """
    if not raw:
        return ""
    name = display_filename(raw)
    dot = name.rfind(".")
    if dot <= 0:
        return ""
    return name[dot:].casefold()


def is_allowed_extension(raw: str | None) -> bool:
    return extension_of(raw) in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# 3) 失败原因与结构化 finding
# ─────────────────────────────────────────────────────────────────────────────


class RejectionCode(str, Enum):
    """结构化拒绝原因。稳定字符串，用于审计与 UI 精确文案。"""

    EMPTY_FILE = "EMPTY_FILE"
    EXTENSION_NOT_ALLOWED = "EXTENSION_NOT_ALLOWED"
    MIME_NOT_ALLOWED = "MIME_NOT_ALLOWED"
    ZIP_MAGIC_MISMATCH = "ZIP_MAGIC_MISMATCH"
    OVERSIZE = "OVERSIZE"
    READ_ERROR = "READ_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: MIME 白名单：xlsx/xlsm 的官方 MIME 与常见误传值。
ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.macroenabled",
    # 客户端常见误传（LibreOffice / 旧版 Excel）
    "application/octet-stream",
    "application/zip",
    "application/x-zip-compressed",
})


@dataclass(frozen=True, slots=True)
class RejectionReason:
    """结构化失败原因（Requirement 3.6 / 3.7）。

    🔴 日志只记 code 与大小，**不记**文件名正文内容、token 或 PII。
    ``display_name`` 是经 ``display_filename`` 清洗的展示值，仍可能含个人信息
    （如 ``张三-工资表.xlsx``），故不进入日志，只回给提交者本人。
    """

    code: RejectionCode
    detail: str
    observed_bytes: int | None = None
    limit_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "detail": self.detail,
            "observedBytes": self.observed_bytes,
            "limitBytes": self.limit_bytes,
        }


class QuarantineError(Exception):
    """quarantine 失败。携带结构化原因，不静默、不返回空报告。"""

    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(f"{reason.code.value}: {reason.detail}")
        self.reason = reason


# ─────────────────────────────────────────────────────────────────────────────
# 4) QuarantineArtifact —— 隔离区内的单文件产物
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class QuarantineArtifact:
    """一次上传的隔离产物元数据（内存视图）。

    Attributes:
        artifact_id: 随机 identity（``uuid4().hex``），**唯一** storage key 依据。
        organization_id: 归属组织，由服务端推导（承接 Task 2 的 scope）。
        display_name: 清洗后的展示文件名，禁止用于路径。
        state: 生命周期状态。
        sha256: 流式计算的正文摘要。
        size_bytes: 实际写入字节数。
        mime_type: 客户端声明的 MIME（不可信，仅记录）。
        detected_extension: 由文件名推导的扩展名。
        created_at: 创建时刻（注入时钟）。
        expires_at: TTL 到期时刻。
        rejection: 失败原因（成功时为 None）。
        resource_observations: 实测资源用量，供 Task 5 scanner 与 policy 校验。
        policy_version: 本次摄取使用的政策版本。
        scope: 归属 scope dict，来自 Task 2 的 ``Scope.to_dict()``。
    """

    artifact_id: str
    organization_id: str
    display_name: str
    state: ArtifactState
    sha256: str
    size_bytes: int
    mime_type: str | None
    detected_extension: str
    created_at: datetime
    expires_at: datetime
    scope: dict[str, Any]
    policy_version: str
    rejection: RejectionReason | None = None
    resource_observations: ResourceObservation = field(default_factory=ResourceObservation)
    #: storage 内相对路径（相对于 quarantine root），只含随机 id。
    relative_path: str = ""
    #: 迁移前的旧状态，用于审计迁移是否合法。
    previous_state: ArtifactState | None = None

    @property
    def is_active(self) -> bool:
        """是否仍持有可推进的字节（非终态）。"""
        return self.state not in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        """可序列化视图（用于 manifest 与 API 响应）。

        🔴 **不含** storage 绝对路径与 ``relative_path`` 原文的枚举提示——
        storage key 不得公开枚举（Requirement 16.1）。``relative_path`` 只含
        随机 id，无敏感信息，仍不外露，改由 service 层按需构造。
        """
        return {
            "artifactId": self.artifact_id,
            "organizationId": self.organization_id,
            "scope": dict(self.scope),
            "displayName": self.display_name,
            "state": self.state.value,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "mimeType": self.mime_type,
            "detectedExtension": self.detected_extension,
            "createdAt": self.created_at.isoformat(),
            "expiresAt": self.expires_at.isoformat(),
            "policyVersion": self.policy_version,
            "rejection": self.rejection.to_dict() if self.rejection else None,
            "previousState": self.previous_state.value if self.previous_state else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5) PrivateQuarantine —— 隔离区存储内核
# ─────────────────────────────────────────────────────────────────────────────


class PrivateQuarantine:
    """private quarantine 存储与摄取内核。

    🔴 所有公开 API 都不接受客户端传入的路径片段：``artifact_id`` 由
    ``uuid4().hex`` 生成，目录层级只含服务端推导的 ``organization_id``。

    Args:
        root: quarantine 根目录。测试注入 tmp dir；生产用
            ``storage/custom_template_quarantine``。
        policy: 摄取政策，默认 ``POLICY_V1``（唯一真源）。
        clock: 可注入时钟。
        incoming_ttl: TTL 覆盖，默认取 policy 的 24h。
    """

    def __init__(
        self,
        *,
        root: Path | str,
        policy: CustomTemplateIngestionPolicy = POLICY_V1,
        clock: Clock = SystemClock(),
        incoming_ttl: timedelta | None = None,
    ) -> None:
        self._root = Path(root)
        self._policy = policy
        self._clock = clock
        self._ttl = incoming_ttl or timedelta(seconds=policy.incoming_ttl_seconds)

    # ── 路径构造 ──

    @staticmethod
    def _safe_org_component(organization_id: str) -> str:
        """把组织 id 转成**文件系统安全**的目录名。

        🔴 ``organization_id`` 由服务端推导（如 ``org:bj1``），但仍做 sanitize
        —— 防止未来任何调用方传入含 ``..`` 的值造成目录穿越。

        除常规非法字符外，本函数额外处理**Windows 平台特异性**的两类字符：

        1. ``:`` —— Windows 把它当 ADS（备用数据流）分隔符或 drive letter
           前缀。``org:bj1`` 作为目录名会被 ``os.mkdir`` 拒绝
           （``NotADirectoryError: [WinError 267] 目录名称无效``）。**这是真实的
           平台级缺陷**：如果只在 Linux 上测，这里永远不会暴露。故把 ``:``
           替换成 ``-``，而非仅加入常规黑名单。
        2. Windows reserved device names（``CON``/``PRN``/``AUX``/``NUL``/
           ``COM1``..``COM9``/``LPT1``..``LPT9``）—— 即使带扩展名也非法。
           命中时追加尾部点（``CON.``）使其失去保留语义。
        """
        component = re.sub(r"[^A-Za-z0-9._-]", "-", organization_id)[:128] or "unknown"
        component = component.strip(". ") or "unknown"
        stem = component.rsplit(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            component = component + "."
        return component

    def _org_dir(self, organization_id: str) -> Path:
        """按组织隔离的 quarantine 子目录（磁盘路径，已 sanitize）。"""
        directory = self._root / "org" / self._safe_org_component(organization_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def logical_org_component(self, organization_id: str) -> str:
        """返回用于**逻辑表示**（``relative_path`` / manifest / 跨平台对比）
        的组织名。

        🔴 与 ``_safe_org_component`` 分离是有意的：磁盘目录名必须在 Windows
        上合法（故把 ``:`` 换成 ``-``），但 ``relative_path`` 是给跨平台
        消费者与审计日志读的**逻辑标识**，保留原始 ``org:bj1`` 才能与
        Task 2 的 scope 真源对齐。两者若合一，Windows 部署会把逻辑标识
        悄悄改写，scope 比对就会静默失配。
        """
        return organization_id.strip() or "unknown"

    def _artifact_dir(self, organization_id: str, artifact_id: str) -> Path:
        return self._org_dir(organization_id) / artifact_id

    def _bytes_path(self, organization_id: str, artifact_id: str) -> Path:
        """字节文件路径。固定 ``artifact.bin``，不含任何用户输入。"""
        return self._artifact_dir(organization_id, artifact_id) / "artifact.bin"

    def _manifest_path(self, organization_id: str, artifact_id: str) -> Path:
        return self._artifact_dir(organization_id, artifact_id) / "manifest.json"

    def contains(self, path: Path) -> bool:
        """判定一个路径是否落在 quarantine 根内（防路径穿越）。"""
        try:
            path.resolve().relative_to(self._root.resolve())
        except ValueError:
            return False
        return True

    # ── 摄取 ──

    async def ingest(
        self,
        source: FileSource,
        *,
        organization_id: str,
        scope: dict[str, Any] | None = None,
    ) -> QuarantineArtifact:
        """流式摄取一个上传文件进 private quarantine。

        流程（Requirement 3.1 / 4.2）：

        1. 校验扩展名白名单 → 不通过即拒绝，**不写任何字节**；
        2. 分配随机 identity，创建隔离目录；
        3. 逐块写入并流式计算 SHA-256，逐块校验大小上限；
        4. 关闭流后校验 ZIP magic 与 MIME；
        5. 落 manifest，返回 QUARANTINED 状态产物。

        🔴 失败时**幂等清理**整个隔离目录，不留半成品字节；并返回结构化
        ``RejectionReason``，绝不返回空报告或 ``valid=True``（Requirement 3.6）。
        """
        artifact_id = uuid.uuid4().hex
        extension = extension_of(source.filename)

        # 扩展名白名单先于任何写入 —— 非 xlsx/xlsm 不占用隔离区资源。
        if not is_allowed_extension(source.filename):
            await _safe_close(source)
            return self._build_rejected_artifact(
                artifact_id=artifact_id,
                organization_id=organization_id,
                display_name=display_filename(source.filename),
                extension=extension,
                mime_type=getattr(source, "content_type", None),
                scope=scope,
                reason=RejectionReason(
                    code=RejectionCode.EXTENSION_NOT_ALLOWED,
                    detail=f"扩展名 {extension or '(无扩展名)'} 不在允许列表 {sorted(ALLOWED_EXTENSIONS)}",
                ),
            )

        declared_mime = getattr(source, "content_type", None)
        if declared_mime and declared_mime.casefold() not in ALLOWED_MIME_TYPES:
            await _safe_close(source)
            return self._build_rejected_artifact(
                artifact_id=artifact_id,
                organization_id=organization_id,
                display_name=display_filename(source.filename),
                extension=extension,
                mime_type=declared_mime,
                scope=scope,
                reason=RejectionReason(
                    code=RejectionCode.MIME_NOT_ALLOWED,
                    detail=f"MIME {declared_mime} 不在允许列表",
                ),
            )

        max_bytes = self._policy.max_upload_bytes
        artifact_dir = self._artifact_dir(organization_id, artifact_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        bytes_path = self._bytes_path(organization_id, artifact_id)

        sha256 = hashlib.sha256()
        size = 0
        try:
            with bytes_path.open("wb") as target:
                while True:
                    chunk = await source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        # 超过上限：立即停流、清理、结构化拒绝。
                        await _safe_close(source)
                        raise QuarantineError(RejectionReason(
                            code=RejectionCode.OVERSIZE,
                            detail=f"文件 {size} 字节超过政策上限 {max_bytes}",
                            observed_bytes=size,
                            limit_bytes=max_bytes,
                        ))
                    target.write(chunk)
                    sha256.update(chunk)
            await _safe_close(source)
        except QuarantineError:
            self._cleanup_directory(artifact_dir)
            raise
        except Exception as exc:
            await _safe_close(source)
            self._cleanup_directory(artifact_dir)
            raise QuarantineError(RejectionReason(
                code=RejectionCode.READ_ERROR,
                detail=f"读取上传流失败: {type(exc).__name__}",
            )) from exc

        if size == 0:
            self._cleanup_directory(artifact_dir)
            raise QuarantineError(RejectionReason(
                code=RejectionCode.EMPTY_FILE,
                detail="上传文件为空，禁止零字节产物",
                observed_bytes=0,
            ))

        if bytes_path.read_bytes()[:4] != ZIP_MAGIC:
            # 🔴 内容校验失败 = **正常拒绝结果**，不是异常。与扩展名/MIME 判定
            # 同一语义：返回 REJECTED 产物（字节已清理），让调用方能把结构化
            # 原因直接回给提交者，而不是走 exception path。
            self._cleanup_directory(artifact_dir)
            return self._build_rejected_artifact(
                artifact_id=artifact_id,
                organization_id=organization_id,
                display_name=display_filename(source.filename),
                extension=extension,
                mime_type=declared_mime,
                scope=scope,
                reason=RejectionReason(
                    code=RejectionCode.ZIP_MAGIC_MISMATCH,
                    detail="文件不是 ZIP/OOXML 容器（magic 不匹配），禁止非 Excel 字节进隔离区",
                    observed_bytes=size,
                ),
            )

        created_at = _utc_now(self._clock)
        expires_at = created_at + self._ttl
        artifact = QuarantineArtifact(
            artifact_id=artifact_id,
            organization_id=organization_id,
            display_name=display_filename(source.filename),
            state=ArtifactState.QUARANTINED,
            sha256=sha256.hexdigest(),
            size_bytes=size,
            mime_type=declared_mime,
            detected_extension=extension,
            created_at=created_at,
            expires_at=expires_at,
            scope=dict(scope or {}),
            policy_version=self._policy.version,
            resource_observations=ResourceObservation(
                upload_bytes=size,
                organization_active_preflights=0,
                organization_storage_used_bytes=0,
            ),
            relative_path=f"org/{self.logical_org_component(organization_id)}/{artifact_id}",
        )
        self._write_manifest(organization_id, artifact_id, artifact)
        # 🔴 日志只记 artifact_id + 状态 + 大小，绝不记文件名正文（Requirement 3.7）。
        logger.info("quarantine accepted artifact_id=%s size=%d", artifact_id, size)
        return artifact

    # ── 状态推进 ──

    def mark_state(
        self,
        artifact: QuarantineArtifact,
        to: ArtifactState,
    ) -> QuarantineArtifact:
        """推进状态机并回写 manifest。非法迁移抛 ``InvalidTransition``。"""
        transition(artifact.state, to)
        previous = artifact.state
        artifact.previous_state = previous
        artifact.state = to
        if to in TERMINAL_STATES:
            artifact.rejection = RejectionReason(
                code=RejectionCode.INTERNAL_ERROR,
                detail=f"状态迁移至 {to.value}",
            )
        self._write_manifest(artifact.organization_id, artifact.artifact_id, artifact)
        return artifact

    # ── 读取 ──

    @staticmethod
    def _assert_safe_artifact_id(artifact_id: str) -> None:
        """校验 artifact_id 是纯标识符，不是路径片段。

        🔴 **这是与 ``contains()`` 互补而非重复的一层**。``contains()`` 检查的是
        ``path.resolve()`` 之后是否落在 quarantine 根内——但 ``..`` 被 resolve
        后会折叠掉，``q/org/x/../artifact.bin`` 解析成 ``q/org/artifact.bin``
        仍然在根内，于是通过。对**调用方可控的标识符**，正确判据是字面量
        检查：任何含 ``/``、``\\``、``..``、空字节或为空的 id 都是穿越尝试，
        必须直接拒绝，而不是靠"解析后仍在根内"这种可被折叠绕过的判据。

        artifact_id 恒由 ``uuid4().hex`` 生成（64 个十六进制字符），故此校验
        在生产路径上恒通过；它拦的是被污染的调用方输入。
        """
        if not artifact_id or "/" in artifact_id or "\\" in artifact_id:
            raise QuarantineError(RejectionReason(
                code=RejectionCode.INTERNAL_ERROR,
                detail="storage key 含路径分隔符，拒绝访问",
            ))
        if ".." in artifact_id or "\x00" in artifact_id:
            raise QuarantineError(RejectionReason(
                code=RejectionCode.INTERNAL_ERROR,
                detail="storage key 越界，拒绝访问",
            ))

    def load_manifest(self, organization_id: str, artifact_id: str) -> dict[str, Any]:
        """读取 manifest；不存在或越界即抛错（fail-closed）。"""
        self._assert_safe_artifact_id(artifact_id)
        path = self._manifest_path(organization_id, artifact_id)
        if not path.exists() or not self.contains(path):
            raise FileNotFoundError(f"quarantine manifest 不存在: {artifact_id}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuarantineError(RejectionReason(
                code=RejectionCode.INTERNAL_ERROR,
                detail=f"manifest 损坏: {type(exc).__name__}",
            )) from exc

    def artifact_bytes_path(self, organization_id: str, artifact_id: str) -> Path:
        """返回字节路径，**仅限服务端内部使用**。

        🔴 双重校验：先字面量校验 ``artifact_id`` 不是路径片段（防 ``..`` 折叠
        绕过），再 ``contains()`` 确认解析后仍在 quarantine 根内。返回值禁止
        回给客户端。
        """
        self._assert_safe_artifact_id(artifact_id)
        path = self._bytes_path(organization_id, artifact_id)
        if not self.contains(path):
            raise QuarantineError(RejectionReason(
                code=RejectionCode.INTERNAL_ERROR,
                detail="storage key 越界，拒绝访问",
            ))
        return path

    # ── 清理 ──

    def delete_artifact(self, organization_id: str, artifact_id: str) -> bool:
        """幂等删除单个产物。

        🔴 重复调用返回 False 而不抛错——retention 需可重试（Requirement 6.7），
        抛错会让 cleanup 循环卡在第一轮失败处。
        """
        directory = self._artifact_dir(organization_id, artifact_id)
        if not directory.exists():
            return False
        self._cleanup_directory(directory)
        return True

    def cleanup_expired(self, organization_id: str | None = None) -> list[str]:
        """按 TTL 清理过期产物，返回被删除的 artifact_id 列表。

        🔴 使用注入时钟，测试不得依赖 sleep 或真实墙钟（Requirement 6.7）。
        manifest 缺失或损坏时按过期处理——残留无索引字节最危险。
        """
        deleted: list[str] = []
        now = _utc_now(self._clock)
        base = self._root / "org"
        if not base.exists():
            return deleted
        org_dirs = (
            [self._root / "org" / self._safe_org_component(organization_id)]
            if organization_id else list(base.iterdir())
        )
        for org_dir in org_dirs:
            if not org_dir.is_dir():
                continue
            for artifact_dir in sorted(org_dir.iterdir()):
                if not artifact_dir.is_dir():
                    continue
                manifest_path = artifact_dir / "manifest.json"
                expired = True
                try:
                    if manifest_path.exists():
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                        # manifest 用 camelCase（``expiresAt``）；兼容历史 snake_case
                        raw_expires = data.get("expiresAt") or data.get("expires_at") or ""
                        expires_at = datetime.fromisoformat(raw_expires)
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        expired = now >= expires_at
                except (ValueError, TypeError, json.JSONDecodeError):
                    expired = True
                if expired:
                    self._cleanup_directory(artifact_dir)
                    deleted.append(artifact_dir.name)
        if deleted:
            logger.info("quarantine cleanup deleted %d artifacts", len(deleted))
        return deleted

    def total_storage_bytes(self) -> int:
        """统计 quarantine 根目录内实际字节数，供组织 quota 准入。"""
        total = 0
        if not self._root.exists():
            return total
        for path in self._root.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total

    # ── 内部工具 ──

    def _cleanup_directory(self, directory: Path) -> None:
        """best-effort 删除目录。"""
        shutil.rmtree(directory, ignore_errors=True)

    def _write_manifest(
        self, organization_id: str, artifact_id: str, artifact: QuarantineArtifact
    ) -> None:
        self._manifest_path(organization_id, artifact_id).write_text(
            json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_rejected_artifact(
        self,
        *,
        artifact_id: str,
        organization_id: str,
        display_name: str,
        extension: str,
        mime_type: str | None,
        scope: dict[str, Any] | None,
        reason: RejectionReason,
    ) -> QuarantineArtifact:
        """构造被拒绝的产物。

        🔴 **不落盘**：拒绝发生在写入前，不留任何字节（Requirement 3.2
        「preflight 前不得公开/执行」的最强形态——连隔离区都不占）。
        """
        created_at = _utc_now(self._clock)
        logger.warning("quarantine rejected artifact_id=%s code=%s", artifact_id, reason.code.value)
        return QuarantineArtifact(
            artifact_id=artifact_id,
            organization_id=organization_id,
            display_name=display_name,
            state=ArtifactState.REJECTED,
            sha256="",
            size_bytes=0,
            mime_type=mime_type,
            detected_extension=extension,
            created_at=created_at,
            expires_at=created_at + self._ttl,
            scope=dict(scope or {}),
            policy_version=self._policy.version,
            rejection=reason,
        )


async def _safe_close(source: FileSource) -> None:
    """尽力关闭上传流，不吞掉调用方的原始异常。"""
    close = getattr(source, "close", None)
    if close is None:
        return
    try:
        result = close()
        if hasattr(result, "__await__"):
            await result
    except Exception:
        pass
