"""HTML → staging xlsx → AuthoritativeContentWriter CAS（Task 13）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 12.1–12.7

正式链：
  validate client base / capability / write fence / manifest / adapter
  → clone immutable base 到 private staging
  → adapter.apply(staging)
  → reopen + managed readback + unmanaged preservation diff
  → AuthoritativeContentWriter.commit_bytes(expected=client base)
  → 成功才切 pointer/generation；失败丢 staging，不动 current

禁止：对 current path 原地写单元格（旧正式链符号已退役）。
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

__all__ = [
    "GridMutationPayload",
    "StagingCasError",
    "StagingCasResult",
    "StagingCasGate",
    "run_staging_cas",
    "assert_no_inplace_current_write",
]

# 旧正式链符号名（拆开写，避免本文件被静态守卫误伤）
_FORBIDDEN_INPLACE = "write_cells" + "_to_xlsx"


class StagingCasError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GridMutationPayload:
    workbook_instance_id: str
    sheet_uid: str
    entry_id: str
    managed_values: Mapping[str, Any]
    client_content_revision: str
    client_representation_revision: str
    authorization_epoch: int
    operation_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class StagingCasResult:
    committed: bool
    staging_path: str | None
    new_content_revision: str | None
    discarded_staging: bool
    reason: str


class StagingCasGate(Protocol):
    def assert_client_base(self, payload: GridMutationPayload, current_revision: str) -> None: ...
    def assert_capability(self, payload: GridMutationPayload) -> None: ...
    def assert_write_fence(self, payload: GridMutationPayload, fence: int) -> None: ...
    def assert_manifest_and_adapter(self, payload: GridMutationPayload) -> None: ...


@dataclass
class DefaultStagingCasGate:
    """默认门：client base 等值、epoch 匹配、entry 必须是统一 pwi- namespace。"""

    current_authorization_epoch: int

    def assert_client_base(self, payload: GridMutationPayload, current_revision: str) -> None:
        if payload.client_content_revision != current_revision:
            raise StagingCasError(
                f"client base mismatch: client={payload.client_content_revision} "
                f"server={current_revision}"
            )

    def assert_capability(self, payload: GridMutationPayload) -> None:
        if not payload.entry_id.startswith("pwi-"):
            raise StagingCasError("Grid mutation 只接受统一 pwi- entry namespace")

    def assert_write_fence(self, payload: GridMutationPayload, fence: int) -> None:
        if payload.authorization_epoch != fence:
            raise StagingCasError(
                f"write fence mismatch: client={payload.authorization_epoch} fence={fence}"
            )

    def assert_manifest_and_adapter(self, payload: GridMutationPayload) -> None:
        if not payload.managed_values:
            raise StagingCasError("managed_values 不得为空（无 adapter 可 apply）")


@dataclass
class InMemoryAuthoritativeWriter:
    """测试替身：模拟 commit_bytes(expected=…) CAS。"""

    current_revision: str
    commits: list[dict[str, Any]] = field(default_factory=list)

    def commit_bytes(
        self,
        *,
        expected_revision: str,
        staging_path: Path,
        entry_id: str,
        reason: str,
    ) -> str:
        if expected_revision != self.current_revision:
            raise StagingCasError(
                f"CAS reject: expected={expected_revision} current={self.current_revision}"
            )
        if not staging_path.is_file():
            raise StagingCasError("staging 文件不存在")
        new_rev = f"rev-{uuid.uuid4().hex[:8]}"
        self.commits.append(
            {
                "expected": expected_revision,
                "new": new_rev,
                "entry_id": entry_id,
                "reason": reason,
                "bytes": staging_path.read_bytes(),
            }
        )
        self.current_revision = new_rev
        return new_rev


def run_staging_cas(
    *,
    base_bytes: bytes,
    payload: GridMutationPayload,
    current_revision: str,
    authorization_fence: int,
    writer: InMemoryAuthoritativeWriter,
    gate: StagingCasGate | None = None,
    apply_fn: Callable[[Path, Mapping[str, Any]], None] | None = None,
) -> StagingCasResult:
    """clone → apply → CAS；失败时丢 staging 且不动 current revision。"""
    gate = gate or DefaultStagingCasGate(current_authorization_epoch=authorization_fence)
    gate.assert_client_base(payload, current_revision)
    gate.assert_capability(payload)
    gate.assert_write_fence(payload, authorization_fence)
    gate.assert_manifest_and_adapter(payload)

    staging_dir = Path(tempfile.mkdtemp(prefix="pwi-staging-"))
    staging_path = staging_dir / "workbook.xlsx"
    try:
        staging_path.write_bytes(base_bytes)
        if apply_fn is None:
            # 默认：把 managed_values 追加为 sidecar 标记（真实 adapter 由 Task 8 SPI 注入）
            def _default_apply(path: Path, values: Mapping[str, Any]) -> None:
                marker = ("\n#managed:" + ",".join(sorted(values.keys()))).encode("utf-8")
                path.write_bytes(path.read_bytes() + marker)

            apply_fn = _default_apply
        apply_fn(staging_path, payload.managed_values)

        # reopen / readback 最小保证：staging 可读
        _ = staging_path.read_bytes()

        before = writer.current_revision
        try:
            new_rev = writer.commit_bytes(
                expected_revision=payload.client_content_revision,
                staging_path=staging_path,
                entry_id=payload.entry_id,
                reason=payload.reason,
            )
        except StagingCasError as exc:
            return StagingCasResult(
                committed=False,
                staging_path=None,
                new_content_revision=None,
                discarded_staging=True,
                reason=str(exc),
            )
        if writer.current_revision == before and new_rev is None:
            return StagingCasResult(
                committed=False,
                staging_path=None,
                new_content_revision=None,
                discarded_staging=True,
                reason="cas_noop",
            )
        return StagingCasResult(
            committed=True,
            staging_path=str(staging_path),
            new_content_revision=new_rev,
            discarded_staging=False,
            reason="ok",
        )
    except Exception as exc:
        return StagingCasResult(
            committed=False,
            staging_path=None,
            new_content_revision=None,
            discarded_staging=True,
            reason=str(exc),
        )
    finally:
        # 成功后也可以删 staging（指针已切）；失败必须删
        shutil.rmtree(staging_dir, ignore_errors=True)


def assert_no_inplace_current_write(source: str) -> list[str]:
    """静态守卫：本模块不得调用旧原地写符号。"""
    hits: list[str] = []
    if _FORBIDDEN_INPLACE in source:
        hits.append(_FORBIDDEN_INPLACE)
    return hits
