# -*- coding: utf-8 -*-
"""CanonicalArtifactRepository：staging、incoming sealing、内容寻址不可变发布、
路径安全、Windows 诊断码、candidate 隔离与 orphan reconciliation。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 2.4, 3.4, 5.6, 5.7, 5.8, 5.9, 5.11, 9.6, 9.7, 10.7, 10.8, 14.11
Properties: P5 / P17 / P42 / P60

═══ 本模块的所有平台行为都来自 Task 7 实证，不是推测 ═══

`.kiro/specs/.../evidence/task7-staged-artifact-db-rollback/` 与版本化契约
`backend/data/workpaper_staged_artifact_boundary_contract.json` 固化了 14 个用例的原始
观测。以下五条是本实现**必须**遵守、且被守卫逐条锁死的事实：

1. **目录 fsync 在 Windows 不可用**（fs1：`os.open(dir)` 直接 `PermissionError`）。
   ⇒ 本模块只对**文件**做 `os.fsync`，:attr:`StagedArtifact.directory_fsync_performed`
   恒为 False。任何「rename 后 fsync 父目录」的注释或代码都是谎报。
2. **幂等尺度是 (目标路径, 目标 sha256)，不是文件身份**（fs2：重复 publish 后 NTFS
   file index 会变）。⇒ 禁止用 `st_ino` 判幂等；:meth:`_publish` 用「目标已存在且内容
   哈希相同」判定复用。
3. **跨卷没有原子原语**（fs4：`os.replace` 报 WinError 17；唯一 fallback 是 copy 语义，
   会让目标在内容完整前可见）。⇒ staging 必须与发布目录同卷，`publish_*` 在动手前
   先判卷并 fail visible。
4. **目标被任何 share 模式占用都无法替换**（fs5：含 `FILE_SHARE_DELETE` 一律 WinError 5；
   源被占用是 WinError 32）。⇒ 「让读者用 share-delete 打开」不是可行缓解；内容寻址
   目标名从不预先存在，current 切换交给 DB pointer。
5. **文件系统与 PostgreSQL 不是同一事务**（db2/db6）。⇒ 本模块只负责「先 durable/publish
   并校验」，DB 事务由 `ContentMutationService` 持有；事务失败只留下 resolver 不可见的
   orphan，由 :class:`OrphanReconciler` + `RetentionPolicyService` 处理。

═══ 为什么「禁令」要写成恒抛方法而不是「不提供」═══

:meth:`release_quarantined` / :meth:`promote_incoming_to_published` 恒抛异常。若只是
「不提供这些方法」，禁令就没有可执行判据 —— 变异检验无法证明它被锁住，未来的调用方
也只会自己写一段绕过。恒抛方法让「隔离永不解除」「incoming 永不 published」变成可测
行为（这与 `repository.delete_scope()` 恒抛同源）。
"""

from __future__ import annotations

import errno
import hashlib
import os
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import WorkpaperArtifact
from app.services.workpaper_sync.canonical_paths import (
    PathBoundaryError,
    assert_within_root,
    resolve_within_root,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    IncomingNotDurableError,
    QuarantinedIncomingError,
    SyncDomainError,
    assert_transition,
    is_digest,
)
from app.services.workpaper_sync.ooxml_security import (
    OoxmlReport,
    OoxmlSecurityError,
    OoxmlStructureError,
    validate_ooxml_artifact,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常（每个都带 error_code；禁止被宽泛 except 降级为成功）
# ═══════════════════════════════════════════════════════════════════════════


class ArtifactRepositoryError(SyncDomainError):
    error_code = "artifact_repository_error"


class ArtifactPathError(ArtifactRepositoryError):
    """路径安全拒绝（Property 42）：穿越、项目外绝对路径、UNC、软链接越界、跨项目复用。"""

    error_code = "artifact_path_rejected"

    def __init__(self, *, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"artifact 路径被拒（{reason}）：{detail}")


class FileInUseError(ArtifactRepositoryError):
    """Windows 文件占用（目标 WinError 5 / 源 WinError 32；Requirement 9.7 可诊断）。"""

    error_code = "FILE_IN_USE"

    def __init__(self, *, detail: str, winerror: int | None, held: str) -> None:
        self.winerror = winerror
        self.held = held
        super().__init__(f"FILE_IN_USE（{held} 被占用，winerror={winerror}）：{detail}")


class CrossVolumeError(ArtifactRepositoryError):
    """跨卷 rename（WinError 17 / EXDEV）。跨卷没有原子原语，必须 fail visible。"""

    error_code = "CROSS_VOLUME_RENAME"

    def __init__(self, *, detail: str, winerror: int | None = None) -> None:
        self.winerror = winerror
        super().__init__(f"CROSS_VOLUME_RENAME：{detail}")


class ArtifactPublishError(ArtifactRepositoryError):
    error_code = "artifact_publish_failed"


class ArtifactDigestMismatchError(ArtifactRepositoryError):
    """finalize 前/后的 digest 校验失败（Requirement 3.4：反读校验通过才允许指针指向）。"""

    error_code = "artifact_digest_mismatch"

    def __init__(self, *, stage: str, expected: str, observed: str, path: str) -> None:
        self.stage = stage
        super().__init__(
            f"artifact digest 不符（{stage}）：expected={expected} observed={observed} path={path}"
        )


class IncomingNotResolvableError(ArtifactRepositoryError):
    """incoming 永不进入 resolver / room / rollback / current pointer（Requirement 5.6）。"""

    error_code = "incoming_not_resolvable"


class CandidateNotResolvableError(ArtifactRepositoryError):
    """upgrade candidate 永不进入 resolver / room / download / current / substrate / evidence。"""

    error_code = "candidate_not_resolvable"


class ArtifactNotPublishedError(ArtifactRepositoryError):
    """resolver 只解析 `state=published` 的 canonical/projection artifact。"""

    error_code = "artifact_not_published"


class AuthorizationRequiredError(ArtifactRepositoryError):
    """authorization-first：授权判定必须发生在任何路径解析/文件打开之前（Requirement 10.6）。"""

    error_code = "authorization_required"


class QuarantineReleaseForbiddenError(ArtifactRepositoryError):
    """quarantined 永不 release / 转 durable（Requirement 5.6，与 V151 trigger 双向）。"""

    error_code = "quarantine_release_forbidden"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 常量与布局
# ═══════════════════════════════════════════════════════════════════════════

#: resolver 可解析的 kind（Task 7 契约 `db_boundary.resolver_exclusion.resolver_predicate`）。
RESOLVABLE_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.canonical, ArtifactKind.projection}
)

#: document_type → 扩展名。与 V151 的 `ck_wpa_document_type` 取值域一致。
DOCUMENT_EXTENSIONS: Final[dict[str, str]] = {
    "xlsx": ".xlsx",
    "docx": ".docx",
    "json": ".json",
    "json.gz": ".json.gz",
    "zip": ".zip",
}

#: 只有这两类需要跑 OOXML 安全门；json/json.gz 走 projection 预算门。
OOXML_DOCUMENT_TYPES: Final[frozenset[str]] = frozenset({"xlsx", "docx"})

#: definition store 的 kind → 子目录（design §Filesystem Layout）。
#: `markers` 不在 design 的枚举里，但 Task 11 明确要求「typed marker artifact 同样使用
#: 内容寻址不可变发布」，故按同一规则新增该子目录。
DEFINITION_SUBDIRS: Final[dict[str, str]] = {
    "template": "templates",
    "instrumentation": "instrumentation",
    "contract": "contracts",
    "authority_model": "authority-models",
    "bundle": "bundles",
    "marker": "markers",
}

DEFINITION_EXTENSIONS: Final[dict[str, str]] = {
    "template": ".ooxml",
    "instrumentation": ".json",
    "contract": ".json",
    "authority_model": ".json",
    "bundle": ".json",
    "marker": ".json",
}


def _now() -> datetime:
    """服务端时钟（aware）。timestamptz 必须在 Python 侧构造 datetime。"""
    return datetime.now(timezone.utc)


def sha12(digest: str) -> str:
    """内容寻址文件名里的短哈希（12 位）。"""
    if not is_digest(digest):
        raise ArtifactRepositoryError(f"短哈希输入不是合法 digest: {digest!r}")
    return digest[:12]


def same_volume(a: Path, b: Path) -> bool:
    """两个路径是否同卷。Windows 上按盘符/UNC 前缀判定。"""
    da = os.path.splitdrive(os.path.realpath(str(a)))[0]
    db = os.path.splitdrive(os.path.realpath(str(b)))[0]
    return da.lower() == db.lower()


def classify_os_error(exc: OSError) -> str:
    """把 `os.replace` 的失败映射到 Requirement 9.7 的诊断码。

    映射来自 Task 7 fs4/fs5 实测（契约 `publish.file_occupancy.diagnostic_mapping`）：

    ============  ======  ========  ======================
    情形          errno   winerror  语义码
    ============  ======  ========  ======================
    目标被占用    13      5         ``FILE_IN_USE``
    源被占用      13      32        ``FILE_IN_USE``
    跨卷 rename   18      17        ``CROSS_VOLUME_RENAME``
    ============  ======  ========  ======================
    """
    winerror = getattr(exc, "winerror", None)
    if winerror in (5, 32):
        return "FILE_IN_USE"
    if winerror == 17 or exc.errno == errno.EXDEV:
        return "CROSS_VOLUME_RENAME"
    return "PUBLISH_IO_ERROR"


@dataclass(frozen=True)
class ArtifactStorageLayout:
    """目录布局（design §Filesystem Layout）。

    `relative_path` 一律是**相对 `base_root` 的 POSIX 路径**，因此：

    * 项目内 artifact： ``storage/{project_id}/workpapers/.versions/{wp_id}/...``
    * definition blob： ``definition_store/bundles/{sha256}.json``

    这样 `working_paper_artifact.relative_path` 的全局唯一索引天然成立，且 V151 的
    `wpsync_check_artifact_incoming_path` 要求的 ``.incoming/{wp_id}/{delivery_id}/``
    片段仍在路径中（它用 `position(... in ...)`，允许前缀）。
    """

    base_root: Path
    storage_dirname: str = "storage"
    definition_dirname: str = "definition_store"

    # ── 根 ──
    @property
    def storage_root(self) -> Path:
        return self.base_root / self.storage_dirname

    @property
    def definition_root(self) -> Path:
        return self.base_root / self.definition_dirname

    def project_root(self, project_id: uuid.UUID) -> Path:
        return self.storage_root / str(project_id) / "workpapers"

    # ── 项目内子命名空间 ──
    def staging_dir(self, project_id: uuid.UUID, wp_id: uuid.UUID, stage_id: uuid.UUID) -> Path:
        return self.project_root(project_id) / ".staging" / str(wp_id) / str(stage_id)

    def candidate_dir(
        self, project_id: uuid.UUID, wp_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> Path:
        return (
            self.project_root(project_id) / ".upgrade-candidates" / str(wp_id) / str(candidate_id)
        )

    def content_dir(self, project_id: uuid.UUID, wp_id: uuid.UUID) -> Path:
        return self.project_root(project_id) / ".versions" / str(wp_id) / "content"

    def representation_dir(
        self, project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
    ) -> Path:
        return (
            self.project_root(project_id)
            / ".versions"
            / str(wp_id)
            / "representations"
            / entry_id
        )

    def versions_root(self, project_id: uuid.UUID, wp_id: uuid.UUID) -> Path:
        return self.project_root(project_id) / ".versions" / str(wp_id)

    def incoming_dir(
        self, project_id: uuid.UUID, wp_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> Path:
        return self.project_root(project_id) / ".incoming" / str(wp_id) / str(delivery_id)

    def evidence_dir(self, project_id: uuid.UUID, entry_id: str, test_run_id: uuid.UUID) -> Path:
        return self.project_root(project_id) / ".evidence" / entry_id / str(test_run_id)

    def definition_dir(self, kind: str) -> Path:
        try:
            return self.definition_root / DEFINITION_SUBDIRS[kind]
        except KeyError as exc:
            raise ArtifactRepositoryError(
                f"未登记的 definition kind {kind!r}（登记: {sorted(DEFINITION_SUBDIRS)}）"
            ) from exc

    # ── relative_path ──
    def relative_of(self, absolute: Path) -> str:
        """把绝对路径转成相对 `base_root` 的 POSIX 字符串。"""
        base = Path(os.path.realpath(str(self.base_root)))
        target = Path(os.path.realpath(str(absolute)))
        try:
            rel = target.relative_to(base)
        except ValueError as exc:
            raise ArtifactPathError(
                reason="outside_storage_base",
                detail=f"{target} 不在 base_root {base} 内",
            ) from exc
        return rel.as_posix()


# ═══════════════════════════════════════════════════════════════════════════
# 2. DTO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class StagedArtifact:
    """`.staging/{wp_id}/{artifact_stage_id}/` 里的已校验暂存产物。

    `artifact_stage_id` 是 staging 的唯一身份，**不依赖 operation/application** ——
    unmatched recovery 也要能先耐久（design §发布协议 步骤 1）。
    """

    artifact_stage_id: uuid.UUID
    project_id: uuid.UUID
    wp_id: uuid.UUID
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    document_type: str
    chunks_written: int
    file_fsync_performed: bool
    #: 恒为 False —— Windows 不允许 `os.open(dir)`（Task 7 fs1）。
    directory_fsync_performed: bool
    same_volume_as_publish_target: bool


@dataclass(frozen=True)
class PublishedArtifact:
    """已发布的不可变 artifact（`.versions` / `definition_store` / `.evidence`）。"""

    kind: ArtifactKind
    state: ArtifactState
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    document_type: str
    #: True = 目标已存在且内容哈希相同 ⇒ 幂等复用，未执行 `os.replace`。
    reused: bool
    verified_before_publish: bool
    verified_after_publish: bool


@dataclass(frozen=True)
class SealedIncoming:
    """`.incoming/{wp_id}/{delivery_id}/` 的 sealing 结果。

    两支互斥且不可互转（Requirement 5.6）：

    * 校验全过 ⇒ ``state=durable``、``durable_at`` 非空；
    * 任一门失败 ⇒ ``state=quarantined``、``quarantined_at`` 非空、``durable_at`` 恒 None。
    """

    delivery_id: uuid.UUID
    project_id: uuid.UUID
    wp_id: uuid.UUID
    state: ArtifactState
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    document_type: str
    durable_at: datetime | None
    quarantined_at: datetime | None
    report: OoxmlReport | None
    rejection_error_code: str | None
    rejection_gate: str | None
    rejection_detail: str | None

    @property
    def durable(self) -> bool:
        return self.state is ArtifactState.durable

    def raise_if_not_durable(self) -> None:
        """engine 入口的 fail-closed 断言。两种失败**必须是不同异常类型**。

        quarantine 是永久安全终态（只允许 download-only/expire/retention），
        「尚未 durable」是暂态。共用一个异常类型时，短路隔离分支会被暂态分支遮蔽
        （Task 10 已实测过这种 GREEN），故此处沿用 Task 10 拆好的两个类型。
        """
        if self.state is ArtifactState.quarantined:
            raise QuarantinedIncomingError(
                "quarantined incoming 永不得创建 application 或进入 engine"
                f"（gate={self.rejection_gate}, code={self.rejection_error_code}）"
            )
        if self.state is not ArtifactState.durable or self.durable_at is None:
            raise IncomingNotDurableError(
                f"incoming state={self.state.value} durable_at={self.durable_at!r}，只有 durable 可用"
            )


@dataclass(frozen=True)
class StagedCandidate:
    """non-current representation upgrade candidate（`.upgrade-candidates/`）。

    candidate 的 path/id **永不**进入 canonical resolver、room、download、current
    pointer、application substrate 或 evidence（Requirement 6.18 / 3.4）。
    """

    candidate_id: uuid.UUID
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    document_type: str
    equivalence_relative_path: str
    equivalence_sha256: str
    verified_before_move: bool
    verified_after_move: bool


@dataclass(frozen=True)
class DownloadAuthorization:
    """authorization-first 的显式授权快照。

    刻意用 dataclass 而不是 bool 参数：bool 参数太容易被 `True` 硬编码溜过去，
    而 dataclass 强制调用方写出 `actor_id` 与 `action`，在审计里留痕
    （Requirement 10.7：短期凭证、最小权限、可撤销）。
    """

    granted: bool
    actor_id: uuid.UUID | None
    action: str
    reason: str = ""


@dataclass
class ReconcileOutcome:
    """orphan reconciliation 结果（Task 7 db4 的两种形态）。"""

    scanned_files: int = 0
    known_paths: int = 0
    #: 磁盘有文件、DB 无 row ⇒ 登记为 `state=orphan`
    registered: list[str] = field(default_factory=list)
    #: DB 有 published row、无 representation 引用 ⇒ 标记为 orphan
    marked: list[str] = field(default_factory=list)
    #: DB row 指向的文件在磁盘上缺失（db6 的半成功态，必须可见地报告）
    missing_files: list[str] = field(default_factory=list)
    untouched: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. CanonicalArtifactRepository
# ═══════════════════════════════════════════════════════════════════════════


class CanonicalArtifactRepository:
    """文件系统侧唯一入口：staging / sealing / publish / 路径安全 / 命名空间扫描。

    **不持有数据库 session、不写 DB 行**。DB 侧由
    `WorkpaperSyncRepository.register_artifact()` 负责，事务边界由
    `ContentMutationService` 持有 —— 两者不是同一事务（Task 7 db2/db6 的正反证据）。
    """

    def __init__(
        self,
        base_root: Path | str,
        *,
        limits: SyncLimits | None = None,
        layout: ArtifactStorageLayout | None = None,
    ) -> None:
        self._layout = layout or ArtifactStorageLayout(Path(base_root))
        self._limits = limits or load_limits()

    @property
    def layout(self) -> ArtifactStorageLayout:
        return self._layout

    @property
    def limits(self) -> SyncLimits:
        return self._limits

    # ─────────────────────────────────────────────────────────────────
    # 3.1 路径安全（Property 42）
    # ─────────────────────────────────────────────────────────────────

    def resolve_within_project(self, project_id: uuid.UUID, relative: str) -> Path:
        """把「项目内相对路径」解析成绝对路径，越界即 :class:`ArtifactPathError`。

        判定规则来自 Task 7 fs7：**`os.path.realpath` 之后**必须仍等于项目根或以项目根
        为祖先。仅做字符串前缀比较拦不住软链接越界（fs7 的 `symlink_escape` 真建了链接，
        realpath 解析到 `C:\\...\\Temp\\...`）。
        """
        return self._resolve_within(
            self._layout.project_root(project_id), relative, boundary="project_root"
        )

    def resolve_relative_path(self, relative: str) -> Path:
        """把 `relative_path`（相对 base_root）解析成绝对路径并校验边界。"""
        return self._resolve_within(self._layout.base_root, relative, boundary="storage_base")

    def _resolve_within(self, root: Path, relative: str, *, boundary: str) -> Path:
        """委托 Task 12 的 `canonical_paths` —— 边界判据全平台只有**一份**实现。

        🔴 这里刻意不重写一遍 realpath 比较：`wp_export/wp_file_resolver.py`、WOPI 与
        storage/version 三个存量分叉在 Task 12 也接同一个函数。两份实现意味着改一处
        另一处不红，正是本 spec 要消灭的分叉形态。异常仍**包成**
        :class:`ArtifactPathError`，保留 Task 11 守卫锁死的 `error_code` 与 `reason` 契约。
        """
        try:
            return resolve_within_root(root, relative, boundary=boundary)
        except PathBoundaryError as exc:
            raise ArtifactPathError(reason=exc.reason, detail=exc.detail) from exc

    def assert_project_owns(self, project_id: uuid.UUID, absolute: Path) -> None:
        """跨项目复用判定：同一相对路径在不同 project 根下解析必须不同（fs7）。"""
        root = self._layout.project_root(project_id)
        try:
            assert_within_root(root, absolute, boundary="project_root")
        except PathBoundaryError as exc:
            raise ArtifactPathError(
                reason="cross_project_path",
                detail=f"{exc.detail}（project {project_id}）",
            ) from exc

    # ─────────────────────────────────────────────────────────────────
    # 3.2 流式 staging + 文件 fsync
    # ─────────────────────────────────────────────────────────────────

    def sha256_of_file(self, path: Path) -> tuple[str, int]:
        """流式重算文件哈希与大小（publish 前后各调用一次）。"""
        h = hashlib.sha256()
        total = 0
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(self._limits.chunk_bytes)
                if not chunk:
                    break
                h.update(chunk)
                total += len(chunk)
        return h.hexdigest(), total

    def stage_stream(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        chunks: Iterable[bytes],
        document_type: str,
        artifact_stage_id: uuid.UUID | None = None,
        filename: str = "artifact.tmp",
        expected_sha256: str | None = None,
        max_bytes: int | None = None,
    ) -> StagedArtifact:
        """边写边算 sha256，写完 `os.fsync(fd)`；**不做目录 fsync**（Windows 不支持）。

        :param max_bytes: 流式大小上限。默认取 Requirement 14.11 的
            `max_compressed_bytes` —— 下载/暂存阶段就必须有界，不能先整包落盘再判大小
            （Requirement 5.3 的「流式大小上限」）。
        """
        if document_type not in DOCUMENT_EXTENSIONS:
            raise ArtifactRepositoryError(
                f"未登记的 document_type {document_type!r}"
                f"（登记: {sorted(DOCUMENT_EXTENSIONS)}）"
            )
        stage_id = artifact_stage_id or uuid.uuid4()
        stage_dir = self._layout.staging_dir(project_id, wp_id, stage_id)
        stage_dir.mkdir(parents=True, exist_ok=True)
        target = stage_dir / filename
        cap = self._limits.max_compressed_bytes if max_bytes is None else max_bytes

        h = hashlib.sha256()
        total = 0
        written = 0
        with target.open("wb") as fh:
            for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > cap:
                    # 立即中止并删除半成品：越界后继续写就是「先落盘再判大小」。
                    fh.flush()
                    fh.close()
                    target.unlink(missing_ok=True)
                    self._limits.assert_compressed_size(total)
                h.update(chunk)
                fh.write(chunk)
                written += 1
            fh.flush()
            os.fsync(fh.fileno())
        digest = h.hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ArtifactDigestMismatchError(
                stage="staging", expected=expected_sha256, observed=digest, path=str(target)
            )
        return StagedArtifact(
            artifact_stage_id=stage_id,
            project_id=project_id,
            wp_id=wp_id,
            path=target,
            relative_path=self._layout.relative_of(target),
            sha256=digest,
            size_bytes=total,
            document_type=document_type,
            chunks_written=written,
            file_fsync_performed=True,
            directory_fsync_performed=False,
            same_volume_as_publish_target=same_volume(
                stage_dir, self._layout.project_root(project_id)
            ),
        )

    def stage_bytes(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        payload: bytes,
        document_type: str,
        artifact_stage_id: uuid.UUID | None = None,
        filename: str = "artifact.tmp",
        expected_sha256: str | None = None,
    ) -> StagedArtifact:
        """小载荷便捷入口（仍走同一流式路径与同一预算门）。"""
        return self.stage_stream(
            project_id=project_id,
            wp_id=wp_id,
            chunks=_iter_bytes(payload, self._limits.chunk_bytes),
            document_type=document_type,
            artifact_stage_id=artifact_stage_id,
            filename=filename,
            expected_sha256=expected_sha256,
        )

    # ─────────────────────────────────────────────────────────────────
    # 3.3 原子替换与内容寻址不可变发布
    # ─────────────────────────────────────────────────────────────────

    def atomic_replace(self, src: Path, dst: Path) -> None:
        """`os.replace` + Requirement 9.7 诊断码归类。

        不预判卷：跨卷失败的真实平台码（WinError 17 / EXDEV）必须能被这里归类，
        否则该分支变成不可达代码（`publish_*` 的同卷前置校验会先拦住）。
        """
        try:
            os.replace(src, dst)
        except OSError as exc:
            code = classify_os_error(exc)
            winerror = getattr(exc, "winerror", None)
            if code == "FILE_IN_USE":
                raise FileInUseError(
                    detail=f"src={src} dst={dst} strerror={exc.strerror}",
                    winerror=winerror,
                    held="source" if winerror == 32 else "target",
                ) from exc
            if code == "CROSS_VOLUME_RENAME":
                raise CrossVolumeError(
                    detail=f"src={src} dst={dst} strerror={exc.strerror}", winerror=winerror
                ) from exc
            raise ArtifactPublishError(
                f"os.replace 失败：src={src} dst={dst} errno={exc.errno} "
                f"winerror={winerror} strerror={exc.strerror}"
            ) from exc

    def verify_staged_digest(self, path: Path, expected_sha256: str) -> tuple[str, int]:
        """发布/校验之前重算 staged digest 并与声明值比对（Requirement 3.4）。

        🔴 必须早于 OOXML 安全门：被 kill 截断的半成品（Task 7 fs6）声明 hash 与实际不符，
        这是**最便宜**的拒绝判据。把它放到 zip 解析之后，半成品会先被当成「结构错误」，
        错误码指向 `ooxml_structure_invalid` 而真正原因是「内容不完整」。
        """
        if not is_digest(expected_sha256):
            raise ArtifactDigestMismatchError(
                stage="declared", expected="<64位非零小写hex>", observed=str(expected_sha256),
                path=str(path),
            )
        digest, size = self.sha256_of_file(path)
        if digest != expected_sha256:
            raise ArtifactDigestMismatchError(
                stage="pre_publish", expected=expected_sha256, observed=digest, path=str(path)
            )
        return digest, size

    def _publish(
        self,
        *,
        staged_path: Path,
        expected_sha256: str,
        target: Path,
        kind: ArtifactKind,
        document_type: str,
        state: ArtifactState = ArtifactState.published,
        pre_verified: tuple[str, int] | None = None,
    ) -> PublishedArtifact:
        """内容寻址不可变发布的唯一实现。

        顺序（每一步都有实证依据，改顺序即改语义）：

        1. **发布前**重算 staged digest 并与声明值比对（Requirement 3.4）；
        2. 判同卷 —— 跨卷没有原子原语（fs4），必须在动手前 fail visible；
        3. 目标已存在且内容相同 ⇒ 幂等复用，**不执行 replace**。这既是 fs2 的
           `(路径, sha256)` 幂等尺度，也顺带绕开 fs5 的占用问题（目标被任何 share
           模式打开都会让 replace 报 WinError 5）；
        4. `os.replace`；
        5. **发布后**从目标路径重算 digest 再比对一次。
        """
        pre_digest, pre_size = pre_verified or self.verify_staged_digest(
            staged_path, expected_sha256
        )

        target.parent.mkdir(parents=True, exist_ok=True)
        if not same_volume(staged_path, target.parent):
            raise CrossVolumeError(
                detail=(
                    f"staging {staged_path} 与发布目录 {target.parent} 不同卷；"
                    "跨卷 os.replace 在 Windows 报 WinError 17，唯一 fallback 是 copy 语义"
                    "（目标会在内容完整前可见），因此 staging 必须与发布目录同卷"
                )
            )

        reused = False
        if target.exists():
            existing_digest, _ = self.sha256_of_file(target)
            if existing_digest == expected_sha256:
                reused = True
                staged_path.unlink(missing_ok=True)
            else:
                raise ArtifactPublishError(
                    f"内容寻址目标 {target} 已存在但内容不同"
                    f"（existing={existing_digest} incoming={expected_sha256}）"
                    " —— 不可变命名空间不允许覆盖"
                )
        if not reused:
            self.atomic_replace(staged_path, target)

        post_digest, post_size = self.sha256_of_file(target)
        if post_digest != expected_sha256:
            raise ArtifactDigestMismatchError(
                stage="post_publish", expected=expected_sha256, observed=post_digest,
                path=str(target),
            )
        return PublishedArtifact(
            kind=kind,
            state=state,
            path=target,
            relative_path=self._layout.relative_of(target),
            sha256=post_digest,
            size_bytes=post_size,
            document_type=document_type,
            reused=reused,
            verified_before_publish=pre_size == post_size,
            verified_after_publish=True,
        )

    def publish_representation(
        self,
        *,
        entry_id: str,
        generation: int,
        staged: StagedArtifact,
        validate_ooxml: bool = True,
    ) -> PublishedArtifact:
        """发布 canonical representation 到 `.versions/{wp_id}/representations/{entry_id}/`。

        文件名 `{generation:09d}-{sha12}{ext}`（Task 7 契约 `target_name_pattern`）。
        """
        if generation < 1:
            raise ArtifactRepositoryError(f"representation generation 必须 >= 1，实得 {generation}")
        pre_verified = self.verify_staged_digest(staged.path, staged.sha256)
        if validate_ooxml and staged.document_type in OOXML_DOCUMENT_TYPES:
            validate_ooxml_artifact(
                staged.path, document_type=staged.document_type, limits=self._limits
            )
        ext = DOCUMENT_EXTENSIONS[staged.document_type]
        target = self._layout.representation_dir(
            staged.project_id, staged.wp_id, entry_id
        ) / f"{generation:09d}-{sha12(staged.sha256)}{ext}"
        return self._publish(
            staged_path=staged.path,
            expected_sha256=staged.sha256,
            target=target,
            kind=ArtifactKind.canonical,
            document_type=staged.document_type,
            pre_verified=pre_verified,
        )

    def publish_projection(
        self, *, revision: int, staged: StagedArtifact
    ) -> PublishedArtifact:
        """发布业务 projection 到 `.versions/{wp_id}/content/`。

        `revision` 允许为 **0**：V151 的 revision 0 是存量底稿的回填基线
        （Task 9 §revision 0 回填台账），不是非法值。
        """
        if revision < 0:
            raise ArtifactRepositoryError(f"content revision 不得为负，实得 {revision}")
        target = self._layout.content_dir(staged.project_id, staged.wp_id) / (
            f"{revision:09d}-{sha12(staged.sha256)}.projection{DOCUMENT_EXTENSIONS['json.gz']}"
        )
        return self._publish(
            staged_path=staged.path,
            expected_sha256=staged.sha256,
            target=target,
            kind=ArtifactKind.projection,
            document_type="json.gz",
        )

    def publish_definition_blob(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        definition_kind: str,
        payload: bytes,
    ) -> PublishedArtifact:
        """把 definition canonical bytes 内容寻址发布到 `definition_store/{子目录}/`。

        覆盖 template / instrumentation / contract / authority_model / **bundle** /
        **marker** 六类 —— Task 11 明确要求 bundle canonical bytes 与 typed marker
        artifact 同样走内容寻址不可变发布。
        """
        subdir = self._layout.definition_dir(definition_kind)
        ext = DEFINITION_EXTENSIONS[definition_kind]
        digest = hashlib.sha256(payload).hexdigest()
        doc_type = "zip" if ext == ".ooxml" else "json"
        staged = self.stage_bytes(
            project_id=project_id,
            wp_id=wp_id,
            payload=payload,
            document_type=doc_type,
            filename=f"definition-{definition_kind}.tmp",
            expected_sha256=digest,
        )
        target = subdir / f"{digest}{ext}"
        return self._publish(
            staged_path=staged.path,
            expected_sha256=digest,
            target=target,
            kind=ArtifactKind.definition
            if definition_kind != "template"
            else ArtifactKind.template,
            document_type=doc_type,
        )

    def publish_bundle_canonical_bytes(
        self, *, project_id: uuid.UUID, wp_id: uuid.UUID, canonical_bytes: bytes
    ) -> PublishedArtifact:
        """bundle canonical payload 的内容寻址不可变发布（Requirement 2.3 / 6.2）。"""
        return self.publish_definition_blob(
            project_id=project_id, wp_id=wp_id,
            definition_kind="bundle", payload=canonical_bytes,
        )

    def publish_typed_null_marker(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        marker_id: str,
        canonical_payload: bytes,
    ) -> PublishedArtifact:
        """版本化 typed null marker 的内容寻址不可变发布。

        `marker_id` 形如 `instrumentation:none:v1`。marker 也是 definition 身份的一部分，
        因此**不能**只存 DB 行 —— canonical bytes 必须与其他 child 一样可内容寻址复算。
        """
        if not marker_id or ":none:v" not in marker_id:
            raise ArtifactRepositoryError(
                f"typed null marker id 必须形如 '<slot>:none:v<N>'，实得 {marker_id!r}"
            )
        return self.publish_definition_blob(
            project_id=project_id, wp_id=wp_id,
            definition_kind="marker", payload=canonical_payload,
        )

    def publish_trace_bundle(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        test_run_id: uuid.UUID,
        scenario_id: str,
        payload: bytes,
    ) -> PublishedArtifact:
        """逐 scenario trace bundle（`.evidence/{entry_id}/{test_run_id}/scenarios/`）。"""
        digest = hashlib.sha256(payload).hexdigest()
        staged = self.stage_bytes(
            project_id=project_id, wp_id=wp_id, payload=payload,
            document_type="json.gz", filename="trace.tmp", expected_sha256=digest,
        )
        target = self._layout.evidence_dir(project_id, entry_id, test_run_id) / "scenarios" / (
            f"{scenario_id}-{sha12(digest)}.trace.json.gz"
        )
        return self._publish(
            staged_path=staged.path, expected_sha256=digest, target=target,
            kind=ArtifactKind.trace_bundle, document_type="json.gz",
        )

    def publish_evidence_manifest(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        test_run_id: uuid.UUID,
        payload: bytes,
    ) -> PublishedArtifact:
        """test run 级 evidence manifest。

        文件名带 sha12（design 的示意名 `evidence.json` 不含哈希，会被同名覆盖，
        与「不可变」冲突；这里按内容寻址规则取名，语义不变）。
        """
        digest = hashlib.sha256(payload).hexdigest()
        staged = self.stage_bytes(
            project_id=project_id, wp_id=wp_id, payload=payload,
            document_type="json", filename="evidence.tmp", expected_sha256=digest,
        )
        target = self._layout.evidence_dir(project_id, entry_id, test_run_id) / (
            f"evidence-{sha12(digest)}.json"
        )
        return self._publish(
            staged_path=staged.path, expected_sha256=digest, target=target,
            kind=ArtifactKind.evidence, document_type="json",
        )

    # ─────────────────────────────────────────────────────────────────
    # 3.4 incoming：durable sealing 与 quarantine
    # ─────────────────────────────────────────────────────────────────

    def stage_incoming(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        delivery_id: uuid.UUID,
        chunks: Iterable[bytes],
        document_type: str,
    ) -> StagedArtifact:
        """把 callback 下载流式落到 `.incoming/{wp_id}/{delivery_id}/download.tmp`。

        暂存就放在最终 sealing 目录里，理由有两条：sealing 变成**同目录 rename**（同卷
        由构造保证）；路径从第一个字节起就以 delivery identity sealing，**不依赖尚未
        存在或后绑定的 operation/application**（V151 的
        `wpsync_check_artifact_incoming_path` 正是这么锁的）。
        """
        stage_dir = self._layout.incoming_dir(project_id, wp_id, delivery_id)
        stage_dir.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        total = 0
        written = 0
        target = stage_dir / "download.tmp"
        with target.open("wb") as fh:
            for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > self._limits.max_compressed_bytes:
                    fh.flush()
                    fh.close()
                    target.unlink(missing_ok=True)
                    self._limits.assert_compressed_size(total)
                h.update(chunk)
                fh.write(chunk)
                written += 1
            fh.flush()
            os.fsync(fh.fileno())
        return StagedArtifact(
            artifact_stage_id=delivery_id,
            project_id=project_id,
            wp_id=wp_id,
            path=target,
            relative_path=self._layout.relative_of(target),
            sha256=h.hexdigest(),
            size_bytes=total,
            document_type=document_type,
            chunks_written=written,
            file_fsync_performed=True,
            directory_fsync_performed=False,
            same_volume_as_publish_target=True,
        )

    def seal_incoming(self, staged: StagedArtifact, *, delivery_id: uuid.UUID) -> SealedIncoming:
        """跑完安全门后 sealing 为 `durable` 或 `quarantined`。

        **不抛策略异常**：Requirement 5.7 要求校验失败时 callback 返回非零 error 且
        artifact 登记为 `quarantined`，因此调用方必须拿到隔离结果去落 DB 行。
        为了不给 fail-open 留口子，:meth:`SealedIncoming.raise_if_not_durable` 是
        engine 入口的强制断言，且 `rejection_error_code` 永远非空。
        """
        report: OoxmlReport | None = None
        rejection: tuple[str, str, str] | None = None
        if staged.document_type in OOXML_DOCUMENT_TYPES:
            try:
                report = validate_ooxml_artifact(
                    staged.path, document_type=staged.document_type, limits=self._limits
                )
            except (OoxmlSecurityError, OoxmlStructureError) as exc:
                rejection = (exc.error_code, exc.gate, str(exc))
            except SyncDomainError as exc:
                # 预算门（BudgetExceededError）也走隔离分支，但保留自己的 error_code。
                rejection = (exc.error_code, getattr(exc, "budget", "capacity"), str(exc))

        now = _now()
        ext = DOCUMENT_EXTENSIONS[staged.document_type]
        if rejection is None:
            assert_transition("incoming_artifact", ArtifactState.staged, ArtifactState.durable)
            target = staged.path.parent / f"callback-{sha12(staged.sha256)}{ext}"
            state = ArtifactState.durable
        else:
            assert_transition(
                "incoming_artifact", ArtifactState.staged, ArtifactState.quarantined
            )
            target = staged.path.parent / f"quarantined-{sha12(staged.sha256)}{ext}"
            state = ArtifactState.quarantined

        if target.exists():
            existing, _ = self.sha256_of_file(target)
            if existing != staged.sha256:
                raise ArtifactPublishError(
                    f"incoming sealing 目标 {target} 已存在且内容不同 —— 不可变命名空间不允许覆盖"
                )
            staged.path.unlink(missing_ok=True)
        else:
            self.atomic_replace(staged.path, target)

        post_digest, post_size = self.sha256_of_file(target)
        if post_digest != staged.sha256:
            raise ArtifactDigestMismatchError(
                stage="post_seal", expected=staged.sha256, observed=post_digest, path=str(target)
            )
        return SealedIncoming(
            delivery_id=delivery_id,
            project_id=staged.project_id,
            wp_id=staged.wp_id,
            state=state,
            path=target,
            relative_path=self._layout.relative_of(target),
            sha256=post_digest,
            size_bytes=post_size,
            document_type=staged.document_type,
            durable_at=now if state is ArtifactState.durable else None,
            quarantined_at=now if state is ArtifactState.quarantined else None,
            report=report,
            rejection_error_code=rejection[0] if rejection else None,
            rejection_gate=rejection[1] if rejection else None,
            rejection_detail=rejection[2] if rejection else None,
        )

    def open_incoming_for_engine(self, sealed: SealedIncoming) -> Path:
        """engine（extract/merge/retry/rematerialize）唯一入口：只接受 durable。"""
        sealed.raise_if_not_durable()
        self.assert_project_owns(sealed.project_id, sealed.path)
        return sealed.path

    def open_quarantined_for_download(
        self, sealed: SealedIncoming, *, authorization: DownloadAuthorization
    ) -> Path:
        """quarantined incoming 的唯一合法读路径：authorization-first download-only。

        🔴 授权判定必须**先于**任何路径解析或文件打开（Requirement 10.6 的不可交换
        顺序）。守卫用「文件根本不存在 + 未授权 ⇒ 仍然抛 AuthorizationRequiredError
        而不是 FileNotFoundError」证明这个顺序，而不是读代码。
        """
        if not authorization.granted:
            raise AuthorizationRequiredError(
                "quarantined incoming 只允许 authorization-first download-only；"
                f"当前授权未通过（action={authorization.action!r} reason={authorization.reason!r}）"
            )
        if authorization.action != "download_only":
            raise AuthorizationRequiredError(
                f"quarantined incoming 只允许 action='download_only'，实得 {authorization.action!r}"
            )
        if sealed.state is not ArtifactState.quarantined:
            raise ArtifactRepositoryError(
                f"open_quarantined_for_download 只处理 quarantined，实得 {sealed.state.value}"
            )
        self.assert_project_owns(sealed.project_id, sealed.path)
        if not sealed.path.exists():
            raise ArtifactRepositoryError(f"quarantined artifact 文件缺失: {sealed.path}")
        return sealed.path

    def release_quarantined(self, sealed: SealedIncoming) -> None:
        """恒抛：quarantined 永不 release、永不转 durable（Requirement 5.6）。"""
        raise QuarantineReleaseForbiddenError(
            "quarantined incoming 永不得 release 或转 durable —— 只允许 "
            "authorization-first download-only / expire / retention/legal-hold"
            f"（artifact={sealed.relative_path}）"
        )

    def promote_incoming_to_published(self, sealed: SealedIncoming) -> None:
        """恒抛：incoming 永不 published、永不成为 current/published representation。"""
        raise IncomingNotResolvableError(
            "incoming artifact 永不得晋升为 published/current representation；"
            "只有以 durable incoming 为**只读 substrate** 新生成的 result representation "
            f"才可独立执行 staged → published（artifact={sealed.relative_path}）"
        )

    # ─────────────────────────────────────────────────────────────────
    # 3.5 upgrade candidate 隔离
    # ─────────────────────────────────────────────────────────────────

    def stage_upgrade_candidate(
        self,
        *,
        staged: StagedArtifact,
        entry_id: str,
        candidate_id: uuid.UUID | None = None,
        equivalence_report: bytes,
    ) -> StagedCandidate:
        """把已校验 staged artifact 移入 `.upgrade-candidates/{wp_id}/{candidate_id}/`。

        candidate 只登记 non-current 候选：**不 publish、不切 pointer、不进 resolver**。
        `working_paper_representation_upgrade_candidate.staged_artifact_id` 只能引用
        这里产出的 artifact（V151 的 `wpsync_check_candidate_artifact` 是第二道锁）。
        """
        cid = candidate_id or uuid.uuid4()
        cdir = self._layout.candidate_dir(staged.project_id, staged.wp_id, cid)
        cdir.mkdir(parents=True, exist_ok=True)

        pre_digest, _ = self.sha256_of_file(staged.path)
        if pre_digest != staged.sha256:
            raise ArtifactDigestMismatchError(
                stage="pre_candidate", expected=staged.sha256, observed=pre_digest,
                path=str(staged.path),
            )
        target = cdir / f"artifact-{sha12(staged.sha256)}.candidate.ooxml"
        if target.exists():
            existing, _ = self.sha256_of_file(target)
            if existing != staged.sha256:
                raise ArtifactPublishError(
                    f"candidate 目标 {target} 已存在且内容不同 —— 不可变命名空间不允许覆盖"
                )
            staged.path.unlink(missing_ok=True)
        else:
            if not same_volume(staged.path, cdir):
                raise CrossVolumeError(
                    detail=f"staging {staged.path} 与 candidate 目录 {cdir} 不同卷"
                )
            self.atomic_replace(staged.path, target)
        post_digest, post_size = self.sha256_of_file(target)
        if post_digest != staged.sha256:
            raise ArtifactDigestMismatchError(
                stage="post_candidate", expected=staged.sha256, observed=post_digest,
                path=str(target),
            )

        eq_digest = hashlib.sha256(equivalence_report).hexdigest()
        eq_target = cdir / f"equivalence-{sha12(eq_digest)}.json"
        if not eq_target.exists():
            eq_staged = self.stage_bytes(
                project_id=staged.project_id, wp_id=staged.wp_id,
                payload=equivalence_report, document_type="json",
                filename="equivalence.tmp", expected_sha256=eq_digest,
            )
            self.atomic_replace(eq_staged.path, eq_target)
        eq_post, _ = self.sha256_of_file(eq_target)
        if eq_post != eq_digest:
            raise ArtifactDigestMismatchError(
                stage="post_candidate_equivalence", expected=eq_digest, observed=eq_post,
                path=str(eq_target),
            )

        return StagedCandidate(
            candidate_id=cid,
            project_id=staged.project_id,
            wp_id=staged.wp_id,
            entry_id=entry_id,
            path=target,
            relative_path=self._layout.relative_of(target),
            sha256=post_digest,
            size_bytes=post_size,
            document_type=staged.document_type,
            equivalence_relative_path=self._layout.relative_of(eq_target),
            equivalence_sha256=eq_digest,
            verified_before_move=True,
            verified_after_move=True,
        )

    def finalize_candidate_artifact(
        self, *, candidate: StagedCandidate, generation: int
    ) -> PublishedArtifact:
        """把 ready candidate 的字节复制成新的 immutable representation。

        **复制而不是移动**：candidate 的 artifact row 仍要存在（rollback target 与审计
        都引用它），移动会让那行指向不存在的文件 —— 正是 Task 7 db6 证明「物理上可能」
        的半成功态。复制路径复用 :meth:`stage_stream` ⇒ 重新流式算哈希，finalize
        前后各校验一次。
        """
        staged = self.stage_stream(
            project_id=candidate.project_id,
            wp_id=candidate.wp_id,
            chunks=_iter_file(candidate.path, self._limits.chunk_bytes),
            document_type=candidate.document_type,
            filename="candidate-finalize.tmp",
            expected_sha256=candidate.sha256,
        )
        return self.publish_representation(
            entry_id=candidate.entry_id, generation=generation, staged=staged
        )

    # ─────────────────────────────────────────────────────────────────
    # 3.6 resolver 可见性（Property 5 / 17）
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def assert_canonical_resolvable(
        *, kind: ArtifactKind | str, state: ArtifactState | str
    ) -> None:
        """resolver / room / rollback / download / current pointer 的统一可见性门。

        🔴 判定顺序：**kind 专属禁令先行**，通用 state 门在后。反过来写会让
        incoming/candidate 的专属 error_code 永久被 `ArtifactNotPublishedError` 遮蔽
        （二者都不是 published），成为不可达分支 —— 那样「incoming 不可解析」与
        「artifact 未发布」在诊断里无法区分，Requirement 5.12 要求的 error code 定位失效。
        """
        k = kind if isinstance(kind, ArtifactKind) else ArtifactKind(kind)
        s = state if isinstance(state, ArtifactState) else ArtifactState(state)
        if k is ArtifactKind.incoming:
            raise IncomingNotResolvableError(
                f"incoming artifact 永不可被 canonical resolver/room/rollback 解析"
                f"（state={s.value}）"
            )
        if k is ArtifactKind.upgrade_candidate:
            raise CandidateNotResolvableError(
                f"upgrade candidate 永不可进入 resolver/room/download/current/substrate/evidence"
                f"（state={s.value}）"
            )
        if s is not ArtifactState.published:
            raise ArtifactNotPublishedError(
                f"resolver 只解析 state=published 的 artifact，实得 {s.value}"
            )
        if k not in RESOLVABLE_KINDS:
            raise ArtifactNotPublishedError(
                f"kind={k.value} 不在 resolver 可解析集合 "
                f"{sorted(x.value for x in RESOLVABLE_KINDS)} 内"
            )

    def resolve_published_artifact(
        self, *, project_id: uuid.UUID, kind: ArtifactKind | str,
        state: ArtifactState | str, relative_path: str,
    ) -> Path:
        """canonical resolver 的唯一读路径：可见性门 → 路径安全 → 归属 → 存在性。"""
        self.assert_canonical_resolvable(kind=kind, state=state)
        absolute = self.resolve_relative_path(relative_path)
        self.assert_project_owns(project_id, absolute)
        if not absolute.exists():
            # Task 7 db6：「pointer 指向缺失 artifact」的半成功态物理上可能，
            # 必须可见地报错，不能返回一个不存在的 Path 让上层继续。
            raise ArtifactPublishError(
                f"published artifact 指针指向的文件不存在: {relative_path}"
                "（publish-then-commit 顺序被破坏，或已被 GC 误删）"
            )
        return absolute

    # ─────────────────────────────────────────────────────────────────
    # 3.7 命名空间扫描（reconciliation / retention 的输入）
    # ─────────────────────────────────────────────────────────────────

    def scan_versions_namespace(
        self, project_id: uuid.UUID, wp_id: uuid.UUID
    ) -> list[str]:
        """列出 `.versions/{wp_id}/` 下的全部文件（相对 base_root 的 POSIX 路径）。

        刻意**只**扫 `.versions`：`.staging` 半成品、`.incoming` 与
        `.upgrade-candidates` 都不在 resolver 命名空间里（Task 7 fs6 的三重理由之一）。
        """
        root = self._layout.versions_root(project_id, wp_id)
        if not root.is_dir():
            return []
        return sorted(
            self._layout.relative_of(p) for p in root.rglob("*") if p.is_file()
        )

    def scan_namespace(self, project_id: uuid.UUID, subdir: str) -> list[str]:
        """列出项目内某个子命名空间的全部文件（`.incoming` / `.upgrade-candidates` / `.staging`）。"""
        root = self._layout.project_root(project_id) / subdir
        if not root.is_dir():
            return []
        return sorted(
            self._layout.relative_of(p) for p in root.rglob("*") if p.is_file()
        )

    def delete_artifact_file(self, relative_path: str, *, project_id: uuid.UUID) -> bool:
        """按 relative_path 删除单个文件（retention apply 的唯一删除入口）。

        仍然走路径安全 + 项目归属判定 —— GC 是唯一「主动删文件」的路径，
        路径校验在这里被绕过的代价最大。
        """
        absolute = self.resolve_relative_path(relative_path)
        self.assert_project_owns(project_id, absolute)
        if not absolute.exists():
            return False
        try:
            absolute.unlink()
        except OSError as exc:
            code = classify_os_error(exc)
            if code == "FILE_IN_USE":
                raise FileInUseError(
                    detail=f"删除 {absolute} 失败：{exc.strerror}",
                    winerror=getattr(exc, "winerror", None),
                    held="target",
                ) from exc
            raise ArtifactPublishError(f"删除 {absolute} 失败: {exc}") from exc
        return True


def _iter_bytes(payload: bytes, chunk: int) -> Iterator[bytes]:
    for i in range(0, len(payload), chunk):
        yield payload[i : i + chunk]


def _iter_file(path: Path, chunk: int) -> Iterator[bytes]:
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                return
            yield block


# ═══════════════════════════════════════════════════════════════════════════
# 4. OrphanReconciler
# ═══════════════════════════════════════════════════════════════════════════


class OrphanReconciler:
    """把「文件系统与 DB 不一致」收敛成显式 orphan（Task 7 db4 的两种形态）。

    存在的唯一理由：文件系统与 PostgreSQL 不是同一事务。DB `ROLLBACK` 不回滚已 publish
    的文件（db2），DB `COMMIT` 也不创造文件（db6）。因此必须有一个可重入的对账器把两种
    不一致变成**可被 RetentionPolicy 处理的显式状态**，而不是留在那里等人发现。

    只 flush 不 commit —— 与 `WorkpaperSyncRepository` 同一事务边界约定。
    """

    def __init__(self, session: AsyncSession, artifacts: CanonicalArtifactRepository) -> None:
        self._session = session
        self._artifacts = artifacts

    async def reconcile(
        self, *, project_id: uuid.UUID, wp_id: uuid.UUID, document_type: str = "xlsx"
    ) -> ReconcileOutcome:
        out = ReconcileOutcome()
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperArtifact).where(
                        WorkpaperArtifact.project_id == project_id,
                        WorkpaperArtifact.wp_id == wp_id,
                    )
                )
            ).scalars()
        )
        by_path = {r.relative_path: r for r in rows}
        out.known_paths = len(by_path)

        disk = self._artifacts.scan_versions_namespace(project_id, wp_id)
        out.scanned_files = len(disk)

        # 形态一：磁盘有文件、DB 无 row（publish 后整个事务回滚，artifact row 也没了）
        for rel in disk:
            if rel in by_path:
                continue
            digest, size = self._artifacts.sha256_of_file(
                self._artifacts.resolve_relative_path(rel)
            )
            row = WorkpaperArtifact(
                id=uuid.uuid4(),
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.canonical.value,
                state=ArtifactState.orphan.value,
                relative_path=rel,
                sha256=digest,
                size_bytes=size,
                document_type=document_type,
                retention_class="orphan_canonical",
                orphaned_at=_now(),
            )
            self._session.add(row)
            out.registered.append(rel)

        # 形态二：DB 有 published row、但无任何 representation 引用它
        published = [
            r for r in rows
            if r.state == ArtifactState.published.value
            and r.kind in (ArtifactKind.canonical.value, ArtifactKind.projection.value)
        ]
        for row in published:
            referenced = (
                await self._session.execute(
                    sa.text(
                        "SELECT 1 FROM working_paper_content_representation "
                        "WHERE artifact_id = :aid "
                        "UNION ALL "
                        "SELECT 1 FROM working_paper_content_version "
                        "WHERE projection_artifact_id = :aid "
                        "   OR authoritative_artifact_id = :aid "
                        "LIMIT 1"
                    ),
                    {"aid": str(row.id)},
                )
            ).first()
            if referenced is None:
                row.state = ArtifactState.orphan.value
                row.orphaned_at = _now()
                # 🔴 必须同时改 retention class：`default` 类的 `applies_to_states` 只含
                # `published`，被标 orphan 后若仍留在 `default`，RetentionPolicy 会永远判
                # `class_scope_mismatch`（保留 + 告警）⇒ 形态二 orphan 永不可回收，
                # 而告警会持续刷屏。这一步让「对账结论」与「保留策略」对齐。
                if row.retention_class == "default":
                    row.retention_class = "orphan_canonical"
                out.marked.append(row.relative_path)
            else:
                out.untouched += 1

        # 形态三（db6 的反向证据）：DB row 存在但文件缺失 —— 必须可见地报告
        for rel, row in by_path.items():
            if row.state in (ArtifactState.deleted.value,):
                continue
            try:
                absolute = self._artifacts.resolve_relative_path(rel)
            except ArtifactPathError:
                out.missing_files.append(rel)
                continue
            if not absolute.exists():
                out.missing_files.append(rel)

        await self._session.flush()
        return out


__all__ = [
    "DEFINITION_EXTENSIONS",
    "DEFINITION_SUBDIRS",
    "DOCUMENT_EXTENSIONS",
    "OOXML_DOCUMENT_TYPES",
    "RESOLVABLE_KINDS",
    "ArtifactDigestMismatchError",
    "ArtifactNotPublishedError",
    "ArtifactPathError",
    "ArtifactPublishError",
    "ArtifactRepositoryError",
    "ArtifactStorageLayout",
    "AuthorizationRequiredError",
    "CanonicalArtifactRepository",
    "CandidateNotResolvableError",
    "CrossVolumeError",
    "DownloadAuthorization",
    "FileInUseError",
    "IncomingNotResolvableError",
    "OrphanReconciler",
    "PublishedArtifact",
    "QuarantineReleaseForbiddenError",
    "ReconcileOutcome",
    "SealedIncoming",
    "StagedArtifact",
    "StagedCandidate",
    "classify_os_error",
    "same_volume",
    "sha12",
]
