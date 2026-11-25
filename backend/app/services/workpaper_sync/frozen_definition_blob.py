"""冻结 definition child 的 blob 读取与 digest 复核 —— **全仓唯一实现**。

═══ 为什么抽这个模块（spec frozen-contract-read-path ADR-FC-002） ═══

两处能力在 :mod:`published_identity_observer` 里已经写对，但它们此前是
`PublishedIdentityObserver` 的**私有方法**，且只在 instrumentation / template 两个 slot
上被调用过：

* ``_resolve_definition_blob`` —— 按 child 行上冻结的 ``blob_artifact_id`` 读 artifact row，
  再交 :class:`~app.services.workpaper_sync.artifacts.CanonicalArtifactRepository`
  解析相对路径；
* ``_read_definition_payload`` —— 读字节 → ``json.loads`` → ``canonical_digest`` 复核。

contract slot 从未走过这条路 ⇒ 历史 operation 的冻结契约在库里完好却读不回来
（spec 现状：definition 行 `approved`、blob `published`、磁盘 352 KB 在位，但没有任何
代码会按 ``contract_slot_ref`` 把它读出来）。

本模块把那两段提取成模块级函数，observer 与
:mod:`~app.services.workpaper_sync.frozen_contract_reader` 共用。

═══ 两条纪律（不可在第二份实现里忘掉） ═══

1. **不自拼** ``definition_store/{kind}/…`` 布局。那是
   :class:`ArtifactStorageLayout` 的领地，抄一份就是第二真源 —— 布局一改，读侧会安静地
   读到不存在的路径。
2. **错误语义逐项保留**：读不到文件与 digest 不符是**两类**失败（前者是运维/数据缺失，
   后者是「已 approved 的 definition 被改写」），不得合并；stage 由调用方传入，
   新调用方按需映射自己的错误类型，**不降级诊断**。

═══ 谁在用它 ═══

* :meth:`PublishedIdentityObserver._read_definition_payload` / `_resolve_definition_blob`
  —— 保留同名薄壳委派（3 个外部调用方 + 5 个测试文件 monkeypatch 它们，删名即断）。
* :class:`~app.services.workpaper_sync.frozen_contract_reader.FrozenContractReader`
  —— 按 bundle 的 ``contract_slot_ref`` 把冻结契约读回来。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping as AbcMapping
from pathlib import Path
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import WorkpaperSyncDefinitionArtifact
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.models import SyncDomainError

__all__ = [
    "FrozenDefinitionBlobError",
    "FrozenDefinitionBlobMissingError",
    "FrozenDefinitionBlobUnreadableError",
    "FrozenDefinitionBlobDigestMismatchError",
    "resolve_definition_blob_path",
    "read_definition_payload",
    "read_definition_blob_bytes",
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 错误（四类各自可辨 —— 不得统一报「契约漂移」）
# ═══════════════════════════════════════════════════════════════════════════


class FrozenDefinitionBlobError(SyncDomainError):
    """冻结 definition blob 读取失败的基类。

    ``diagnostics`` 是**只读**的结构化诊断，调用方可以原样塞进自己的错误里：
    ``definition_id`` / ``blob_artifact_id`` / ``relative_path`` / ``path``。
    它刻意不含「哪个 slot 在读」—— slot 是调用方的语境，不是本模块的事实。
    """

    error_code = "frozen_definition_blob_error"

    def __init__(self, message: str, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics: Mapping[str, Any] = dict(diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            **dict(self.diagnostics),
        }


class FrozenDefinitionBlobMissingError(FrozenDefinitionBlobError):
    """definition 行或它的 blob artifact row 不存在（**数据缺失**）。

    与「文件不在盘」分开：前者的正确处置是查数据链，后者是查存储卷。
    """

    error_code = "frozen_definition_blob_missing"


class FrozenDefinitionBlobUnreadableError(FrozenDefinitionBlobError):
    """artifact row 在库、路径也解析出来了，但**磁盘上读不到字节**（OSError）。"""

    error_code = "frozen_definition_blob_unreadable"


class FrozenDefinitionBlobDigestMismatchError(FrozenDefinitionBlobError):
    """读回的 payload 与冻结 digest 不符 —— 「已 approved 的 definition 不可被改写」。"""

    error_code = "frozen_definition_blob_digest_mismatch"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 读取
# ═══════════════════════════════════════════════════════════════════════════


def _definition_id_text(value: object) -> str:
    """``uuid.UUID`` 与字符串都能进诊断（不 ``str(None)`` 造出 "None"）。"""
    return "" if value is None else str(value)


def _blob_id_of(child: object) -> str:
    """``blob_artifact_id`` 的容错读取。

    🔴 不能直接 ``child.blob_artifact_id``：本模块的诊断字段会被**成功路径**也填一遍，
    而若干既有测试夹具（``SimpleNamespace(id=…, sha256=…)``）刻意只给两个字段 ——
    在那里读第三个字段会把「成功读回」变成 ``AttributeError``。诊断缺失该字段无妨，
    把一个正确的读取结果变成异常才是真问题。
    """
    return _definition_id_text(getattr(child, "blob_artifact_id", None))


async def resolve_definition_blob_path(
    *,
    session: AsyncSession,
    artifacts: Any,
    child: WorkpaperSyncDefinitionArtifact,
    diagnostics: Mapping[str, Any] | None = None,
) -> Path:
    """definition blob 的物理路径：按**冻结 FK** 读 artifact row，再交仓储解析相对路径。

    🔴 ``artifacts`` 由调用方提供（生产恒是
    :class:`~app.services.workpaper_sync.artifacts.CanonicalArtifactRepository`）。
    本模块**不自拼** ``definition_store/{kind}/…`` 布局 —— 那是
    :class:`ArtifactStorageLayout` 的领地，抄一份就是第二真源（布局一改，读侧会安静地
    读到不存在的路径）。

    Raises:
        FrozenDefinitionBlobError: 仓储未装配（``error_code`` 仍是
            ``frozen_definition_blob_error``，原因是「装配缺失」而非数据缺失）。
        FrozenDefinitionBlobMissingError: blob artifact row 不存在。
    """
    from app.models.workpaper_sync_models import WorkpaperArtifact

    base = dict(diagnostics or {})
    base.setdefault("definition_id", _definition_id_text(child.id))

    if artifacts is None:
        raise FrozenDefinitionBlobError(
            "未装配 artifact 仓储 —— 读侧不得自拼 definition store 布局（那是第二真源）",
            diagnostics=base,
        )
    row = (
        await session.execute(
            sa.select(WorkpaperArtifact).where(
                WorkpaperArtifact.id == child.blob_artifact_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise FrozenDefinitionBlobMissingError(
            f"definition {child.id} 的 blob artifact {child.blob_artifact_id} 不存在",
            diagnostics={
                **base,
                "blob_artifact_id": _blob_id_of(child),
            },
        )
    relative = str(row.relative_path or "")
    return artifacts.resolve_relative_path(relative)


async def read_definition_blob_bytes(
    *,
    session: AsyncSession,
    artifacts: Any,
    child: WorkpaperSyncDefinitionArtifact,
    diagnostics: Mapping[str, Any] | None = None,
) -> bytes:
    """读 definition blob 的**原始字节**（不解析、不复核）。

    只有确实要字节本体（例如需要 ``sha256(file_bytes)`` 而非 canonical digest）的调用方
    才用这个；要 payload 请用 :func:`read_definition_payload`。
    """
    base = dict(diagnostics or {})
    base.setdefault("definition_id", _definition_id_text(child.id))
    path = await resolve_definition_blob_path(
        session=session, artifacts=artifacts, child=child, diagnostics=base
    )
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise FrozenDefinitionBlobUnreadableError(
            f"definition {child.id} 的 artifact 读不到: {path} "
            f"({type(exc).__name__}: {exc})",
            diagnostics={
                **base,
                "blob_artifact_id": _blob_id_of(child),
                "path": str(path),
            },
        ) from exc


async def read_definition_payload(
    *,
    session: AsyncSession,
    artifacts: Any,
    child: WorkpaperSyncDefinitionArtifact,
    diagnostics: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """读 child definition 的 canonical payload 并按 **row 上冻结的 sha256** 复核。

    三步顺序即判据，不可交换：
    ① 按冻结 FK 解析路径（:func:`resolve_definition_blob_path`）；
    ② 读字节 + ``json.loads``（非法 UTF-8 / 非法 JSON 都算「不可用」）；
    ③ ``canonical_digest(payload)`` 必须等于 ``child.sha256``。

    🔴 第 ③ 步不是冗余：artifact row 的 ``sha256`` 与 definition row 的 ``sha256`` 是两列，
    前者是文件字节 hash，后者是 **canonical payload** digest。只有第 ③ 步能证明
    「已 approved 的 definition 没有被改写」。

    Raises:
        FrozenDefinitionBlobMissingError / FrozenDefinitionBlobUnreadableError: 路径层失败。
        FrozenDefinitionBlobError: payload 不是合法 UTF-8 JSON，或根不是对象。
        FrozenDefinitionBlobDigestMismatchError: canonical digest 与冻结值不符。
    """
    base = dict(diagnostics or {})
    base.setdefault("definition_id", _definition_id_text(child.id))
    path = await resolve_definition_blob_path(
        session=session, artifacts=artifacts, child=child, diagnostics=base
    )
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise FrozenDefinitionBlobUnreadableError(
            f"definition {child.id} 的 artifact 读不到: {path} "
            f"({type(exc).__name__}: {exc})",
            diagnostics={
                **base,
                "blob_artifact_id": _blob_id_of(child),
                "path": str(path),
            },
        ) from exc

    return decode_and_verify_definition_payload(
        raw=raw, child=child, path=path, diagnostics=base
    )


def decode_and_verify_definition_payload(
    *,
    raw: bytes,
    child: WorkpaperSyncDefinitionArtifact,
    path: Path | str | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """把**已经读到的字节**解析成 payload 并按 row 上冻结的 ``sha256`` 复核。

    与 :func:`read_definition_payload` 的分工：这个函数不碰路径、不碰 IO，只做
    「decode + 根类型 + canonical digest」三步 —— 于是「路径怎么来的」留给调用方，
    「字节怎么校验的」全仓只有这一份。

    🔴 需要它的理由：``PublishedIdentityObserver._read_definition_payload`` 的既有调用方与
    5 个测试文件会 monkeypatch ``_resolve_definition_blob``（替换**路径解析**那一层）。
    若薄壳整体走 :func:`read_definition_payload`（它自己解析路径），那些 monkeypatch 就
    失效了 —— 表现为「测试在测一个不再是生产路径的分支」。

    Raises:
        FrozenDefinitionBlobError: payload 不是合法 UTF-8 JSON，或根不是对象。
        FrozenDefinitionBlobDigestMismatchError: canonical digest 与冻结值不符。
    """
    base = dict(diagnostics or {})
    base.setdefault("definition_id", _definition_id_text(child.id))
    payload = _decode_payload(raw=raw, child=child, base=base, path=path)
    frozen = str(child.sha256 or "").strip()
    actual = canonical_digest(payload)
    if actual != frozen:
        raise FrozenDefinitionBlobDigestMismatchError(
            f"definition {child.id} 的 payload canonical digest {actual!r} 与 row 上冻结的 "
            f"{frozen!r} 不一致 —— 已 approved 的 definition 不可被改写",
            diagnostics={
                **base,
                "blob_artifact_id": _blob_id_of(child),
                "path": "" if path is None else str(path),
                "frozen_sha256": frozen,
                "actual_sha256": actual,
            },
        )
    return payload


def _decode_payload(
    *,
    raw: bytes,
    child: WorkpaperSyncDefinitionArtifact,
    base: Mapping[str, Any],
    path: Path | str | None,
) -> Mapping[str, Any]:
    """字节 → 对象。两类失败（编码/语法、根类型）共用本模块基类，但消息各自说清。"""
    shown_path = "" if path is None else str(path)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrozenDefinitionBlobError(
            f"definition {child.id} 的 canonical payload 不是合法 UTF-8 JSON: {exc}",
            diagnostics={
                **dict(base),
                "blob_artifact_id": _blob_id_of(child),
                "path": shown_path,
            },
        ) from exc
    if not isinstance(payload, AbcMapping):
        raise FrozenDefinitionBlobError(
            f"definition {child.id} 的 canonical payload 根不是对象，实得 "
            f"{type(payload).__name__}",
            diagnostics={
                **dict(base),
                "blob_artifact_id": _blob_id_of(child),
                "path": shown_path,
            },
        )
    return payload
