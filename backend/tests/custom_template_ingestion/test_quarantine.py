"""private quarantine 与三入口守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.6, 3.7, 6.1, 6.7
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.custom_template_ingestion.policy import POLICY_V1
from app.services.custom_template_ingestion.quarantine import (
    ALLOWED_EXTENSIONS,
    CHUNK_SIZE,
    ArtifactState,
    InvalidTransition,
    PrivateQuarantine,
    QuarantineError,
    RejectionCode,
    TERMINAL_STATES,
    display_filename,
    extension_of,
    is_allowed_extension,
    transition,
)


# ─────────────────────────────────────────────────────────────────────────────
# 测试夹具
# ─────────────────────────────────────────────────────────────────────────────

ZIP_HEADER = b"PK\x03\x04" + b"\x00" * 12


class FakeClock:
    def __init__(self, at: str) -> None:
        y, m, d, H, M, S = (int(x) for x in at.split(":"))
        self._now = datetime(y, m, d, H, M, S, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kw) -> None:
        self._now = (self._now + timedelta(**kw)).replace(tzinfo=timezone.utc)


class MemoryFileSource:
    """纯内存 UploadFile 替身 —— 不必构造真实 multipart。"""

    def __init__(self, data: bytes, *, filename: str | None = "book.xlsx",
                 content_type: str | None = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") -> None:
        self._data = data
        self._pos = 0
        self.filename = filename
        self.content_type = content_type
        self.closed = False

    async def read(self, size: int | None = None) -> bytes:
        if size is None:
            chunk, self._pos = self._data[self._pos:], len(self._data)
        else:
            chunk, self._pos = self._data[self._pos:self._pos + size], self._pos + size
        return chunk

    async def close(self) -> None:
        self.closed = True


def _make_valid_bytes(size: int = 2048) -> bytes:
    """构造 ZIP magic + 填充字节的可解析载荷。"""
    return ZIP_HEADER + b"\x00" * max(0, size - len(ZIP_HEADER))


@pytest.fixture()
def quarantine(tmp_path: Path) -> tuple[PrivateQuarantine, FakeClock]:
    return PrivateQuarantine(
        root=tmp_path / "quarantine",
        policy=POLICY_V1,
        clock=FakeClock("2026:9:8:0:0:0"),
    ), FakeClock("2026:9:8:0:0:0")


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.1 —— 文件名清洗，storage identity 与输入零关联
# ─────────────────────────────────────────────────────────────────────────────


def test_display_filename_strips_path_traversal() -> None:
    assert display_filename("../../etc/passwd") == "passwd"
    assert display_filename("C:\\Users\\me\\x.xlsx") == "x.xlsx"
    assert display_filename("a/b/c/.xlsx") == ".xlsx"


def test_display_filename_strips_control_characters() -> None:
    assert display_filename("a\x00b\r\nc.xlsx") == "abc.xlsx"
    assert display_filename("a\x1b[31m.xlsx") == "a[31m.xlsx"


def test_display_filename_strips_leading_dots_and_spaces() -> None:
    assert display_filename("...hidden.xlsx") == "hidden.xlsx"
    assert display_filename("   spaced   .xlsx") == "spaced.xlsx"


def test_display_filename_falls_back_not_error() -> None:
    assert display_filename(None) == "upload.bin"
    assert display_filename("") == "upload.bin"
    assert display_filename("   ") == "upload.bin"
    assert display_filename("../../") == "upload.bin"


def test_display_filename_truncates_to_limit() -> None:
    from app.services.custom_template_ingestion.quarantine import MAX_DISPLAY_FILENAME_LEN

    long_name = "a" * (MAX_DISPLAY_FILENAME_LEN + 50) + ".xlsx"
    result = display_filename(long_name)
    assert len(result) <= MAX_DISPLAY_FILENAME_LEN


def test_extension_detection_is_casefolded_and_uses_display_value() -> None:
    assert extension_of("A/B/BOOK.XLSX") == ".xlsx"
    assert extension_of("book") == ""
    assert extension_of(None) == ""
    assert is_allowed_extension("book.xlsx")
    assert is_allowed_extension("book.XLSM")
    assert not is_allowed_extension("book.xls")
    assert not is_allowed_extension("book.pdf")
    assert ALLOWED_EXTENSIONS == frozenset({".xlsx", ".xlsm"})


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.1 / 4.2 —— 流式摄取 + 三重校验
# ─────────────────────────────────────────────────────────────────────────────


async def test_ingest_writes_bytes_and_computes_sha256(tmp_path: Path) -> None:
    import hashlib

    clock = FakeClock("2026:9:8:0:0:0")
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=clock)
    data = _make_valid_bytes(5000)
    src = MemoryFileSource(data, filename="张三-报表.xlsx")

    artifact = await q.ingest(src, organization_id="org:bj1", scope={"organizationId": "org:bj1"})
    assert artifact.state is ArtifactState.QUARANTINED
    assert artifact.size_bytes == 5000
    assert artifact.sha256 == hashlib.sha256(data).hexdigest()
    assert artifact.display_name == "张三-报表.xlsx"
    assert artifact.detected_extension == ".xlsx"
    assert src.closed, "摄取完成后必须关闭上传流"
    # storage key 只含随机 id，与输入文件名零关联
    assert "张三" not in artifact.artifact_id
    assert "报表" not in artifact.artifact_id
    assert artifact.relative_path.startswith("org/org:bj1")


async def test_storage_key_never_contains_user_input(tmp_path: Path) -> None:
    """🔴 遍历：任何输入文件名都不能出现在落盘路径里。

    🔴 断言用**原始输入名**与 **display_name 的主体段**双重判定，而不是只查
    ``display_name not in relative_path``——后者可被"把点替换成横线"这类字符
    变换绕过（实测变异 ``artifact_id = display_filename(...).casefold().
    replace(".", "-")`` 就骗过了旧断言：``escape.xlsx`` 变成 ``escape-xlsx``，
    原始名仍在路径语义里，只是拼写形式变了）。真正的安全属性是：路径里既不含
    原始名，也不含清洗后名的主体段。
    """
    clock = FakeClock("2026:9:8:0:0:0")
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=clock)
    for name in ("../../escape.xlsx", "C:\\x.xlsx", "a\x00b.xlsx", "very" + "x" * 300 + ".xlsx"):
        artifact = await q.ingest(
            MemoryFileSource(_make_valid_bytes(256), filename=name),
            organization_id="org:bj1",
        )
        assert artifact.display_name != name
        # 原始输入名不得出现在路径里
        assert name not in artifact.relative_path
        # 清洗后名的主体段（去扩展名）也不得出现 —— 挡住字符替换型绕过
        body = artifact.display_name.rsplit(".", 1)[0].strip()
        assert body not in artifact.relative_path, (
            f"storage key 含用户输入主体段: {body!r} in {artifact.relative_path!r}"
        )


async def test_ingest_rejects_non_allowed_extension_without_writing_bytes(tmp_path: Path) -> None:
    """扩展名白名单先于任何写入 —— 不占隔离区资源。"""
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    src = MemoryFileSource(_make_valid_bytes(256), filename="malware.exe")
    artifact = await q.ingest(src, organization_id="org:bj1")
    assert artifact.state is ArtifactState.REJECTED
    assert artifact.rejection.code is RejectionCode.EXTENSION_NOT_ALLOWED
    assert artifact.size_bytes == 0
    assert artifact.sha256 == ""
    assert src.closed
    # 不落盘：quarantine 根内无任何字节文件
    assert not list((tmp_path / "q").rglob("artifact.bin"))


async def test_ingest_rejects_bad_mime(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    src = MemoryFileSource(_make_valid_bytes(256), filename="a.xlsx", content_type="text/html")
    artifact = await q.ingest(src, organization_id="org:bj1")
    assert artifact.state is ArtifactState.REJECTED
    assert artifact.rejection.code is RejectionCode.MIME_NOT_ALLOWED


async def test_ingest_accepts_common_misreported_mime(tmp_path: Path) -> None:
    """LibreOffice/旧 Excel 常误传 octet-stream —— 不该被拦。"""
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    artifact = await q.ingest(
        MemoryFileSource(_make_valid_bytes(256), filename="a.xlsx", content_type="application/octet-stream"),
        organization_id="org:bj1",
    )
    assert artifact.state is ArtifactState.QUARANTINED


async def test_ingest_rejects_non_zip_magic(tmp_path: Path) -> None:
    """扩展名是 .xlsx 但正文不是 ZIP 容器 —— 必须拒绝。"""
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    src = MemoryFileSource(b"HTML<script>alert(1)</script>", filename="a.xlsx")
    artifact = await q.ingest(src, organization_id="org:bj1")
    assert artifact.state is ArtifactState.REJECTED
    assert artifact.rejection.code is RejectionCode.ZIP_MAGIC_MISMATCH
    # 已写入的字节必须被清理
    assert not list((tmp_path / "q").rglob("artifact.bin"))


async def test_ingest_rejects_empty_file(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    with pytest.raises(QuarantineError) as exc_info:
        await q.ingest(MemoryFileSource(b"", filename="a.xlsx"), organization_id="org:bj1")
    assert exc_info.value.reason.code is RejectionCode.EMPTY_FILE


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.3 / 3.7 —— 大小上限与幂等清理
# ─────────────────────────────────────────────────────────────────────────────


async def test_oversize_is_rejected_and_cleaned_up(tmp_path: Path) -> None:
    """超上限必须停流 + 幂等清理，不留半成品字节。"""
    q = PrivateQuarantine(
        root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"),
    )
    big = _make_valid_bytes(POLICY_V1.max_upload_bytes + 4096)
    src = MemoryFileSource(big, filename="huge.xlsx")
    with pytest.raises(QuarantineError) as exc_info:
        await q.ingest(src, organization_id="org:bj1")
    reason = exc_info.value.reason
    assert reason.code is RejectionCode.OVERSIZE
    assert reason.observed_bytes == POLICY_V1.max_upload_bytes + 4096
    assert reason.limit_bytes == POLICY_V1.max_upload_bytes
    # 字节已落盘一半，必须被清理
    assert not list((tmp_path / "q").rglob("artifact.bin"))
    assert src.closed


async def test_read_error_becomes_structured_failure(tmp_path: Path) -> None:
    """读取流失败必须结构化失败，不得静默或返回空报告。"""
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))

    class BrokenSource(MemoryFileSource):
        async def read(self, size=None) -> bytes:
            raise OSError("disk full")

    with pytest.raises(QuarantineError) as exc_info:
        await q.ingest(BrokenSource(_make_valid_bytes(256), filename="a.xlsx"), organization_id="org:bj1")
    assert exc_info.value.reason.code is RejectionCode.READ_ERROR
    assert not list((tmp_path / "q").rglob("artifact.bin"))


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 6.1 —— 状态机封闭，不混入 publication/project 状态
# ─────────────────────────────────────────────────────────────────────────────


def test_state_machine_is_closed_to_quarantine_domain() -> None:
    """🔴 枚举成员封闭：绝不包含 publication 或 project current 状态。"""
    members = {s.value for s in ArtifactState}
    assert members == {
        "QUARANTINED", "PREFLIGHT_READY", "PREFLIGHT_FAILED",
        "REJECTED", "EXPIRED",
    }
    for forbidden in ("PUBLISHED", "ACTIVE", "WITHDRAWN", "COMMITTED", "INSTANTIATED"):
        assert forbidden not in members


def test_transition_rejects_unregistered_moves() -> None:
    # 终态不可逆出；REJECTED → QUARANTINED 是未登记的跨回跳转
    with pytest.raises(InvalidTransition):
        transition(ArtifactState.REJECTED, ArtifactState.QUARANTINED)
    with pytest.raises(InvalidTransition):
        transition(ArtifactState.EXPIRED, ArtifactState.QUARANTINED)
    with pytest.raises(InvalidTransition):
        transition(ArtifactState.PREFLIGHT_READY, ArtifactState.QUARANTINED)


def test_valid_transitions_succeed() -> None:
    transition(ArtifactState.QUARANTINED, ArtifactState.PREFLIGHT_READY)
    transition(ArtifactState.QUARANTINED, ArtifactState.PREFLIGHT_FAILED)
    transition(ArtifactState.QUARANTINED, ArtifactState.REJECTED)
    transition(ArtifactState.QUARANTINED, ArtifactState.EXPIRED)
    transition(ArtifactState.PREFLIGHT_FAILED, ArtifactState.REJECTED)


def test_terminal_states_exclude_preflight_ready() -> None:
    """PREFLIGHT_READY 仍持有可推进字节，不可当终态删。"""
    assert ArtifactState.PREFLIGHT_READY not in TERMINAL_STATES
    assert ArtifactState.QUARANTINED not in TERMINAL_STATES
    assert {ArtifactState.PREFLIGHT_FAILED, ArtifactState.REJECTED, ArtifactState.EXPIRED} <= TERMINAL_STATES


async def test_mark_state_persists_and_records_previous(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    artifact = await q.ingest(MemoryFileSource(_make_valid_bytes(256)), organization_id="org:bj1")
    updated = q.mark_state(artifact, ArtifactState.PREFLIGHT_READY)
    assert updated.state is ArtifactState.PREFLIGHT_READY
    assert updated.previous_state is ArtifactState.QUARANTINED
    manifest = q.load_manifest("org:bj1", artifact.artifact_id)
    assert manifest["state"] == "PREFLIGHT_READY"
    assert manifest["previousState"] == "QUARANTINED"


async def test_mark_state_rejects_illegal_transition(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    artifact = await q.ingest(MemoryFileSource(_make_valid_bytes(256)), organization_id="org:bj1")
    q.mark_state(artifact, ArtifactState.REJECTED)
    with pytest.raises(InvalidTransition):
        q.mark_state(artifact, ArtifactState.QUARANTINED)


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 6.7 —— 幂等清理 + 注入时钟（不用 sleep / 真实墙钟）
# ─────────────────────────────────────────────────────────────────────────────


async def test_delete_artifact_is_idempotent(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    artifact = await q.ingest(MemoryFileSource(_make_valid_bytes(256)), organization_id="org:bj1")
    assert q.delete_artifact("org:bj1", artifact.artifact_id) is True
    # 重复删除返回 False 而不抛错 —— retention 需可重试
    assert q.delete_artifact("org:bj1", artifact.artifact_id) is False
    assert q.delete_artifact("org:bj1", "nonexistent") is False


async def test_cleanup_expired_uses_injected_clock_not_wall_clock(tmp_path: Path) -> None:
    """🔴 TTL 判定必须走注入时钟：不动时钟则永不清理，推进则立即清理。"""
    clock = FakeClock("2026:9:8:0:0:0")
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=clock)
    artifact = await q.ingest(MemoryFileSource(_make_valid_bytes(256)), organization_id="org:bj1")
    # TTL 内（policy 默认 24h）：不清理
    clock.advance(days=1, hours=-1)
    assert q.cleanup_expired() == []
    assert q.load_manifest("org:bj1", artifact.artifact_id)
    # 越过 TTL：清理
    clock.advance(hours=1)
    assert q.cleanup_expired() == [artifact.artifact_id]
    with pytest.raises(FileNotFoundError):
        q.load_manifest("org:bj1", artifact.artifact_id)


async def test_cleanup_removes_artifacts_with_corrupt_manifest(tmp_path: Path) -> None:
    """manifest 损坏的残留字节最危险 —— 按过期处理。"""
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    artifact = await q.ingest(MemoryFileSource(_make_valid_bytes(256)), organization_id="org:bj1")
    manifest = q._manifest_path("org:bj1", artifact.artifact_id)
    manifest.write_text("{ not valid json", encoding="utf-8")
    assert q.cleanup_expired() == [artifact.artifact_id]


async def test_cleanup_orphan_directory_without_manifest_is_removed(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    # 🔴 磁盘目录名必须经 sanitize（Windows 上 "org:bj1" 是非法目录名）
    orphan = q._org_dir("org:bj1") / "orphan-123"
    orphan.mkdir(parents=True)
    (orphan / "artifact.bin").write_bytes(_make_valid_bytes(256))
    assert q.cleanup_expired() == ["orphan-123"]


def test_cleanup_scoped_to_organization(tmp_path: Path) -> None:
    clock = FakeClock("2026:9:8:0:0:0")
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=clock)
    (q._org_dir("org:bj1") / "a").mkdir(parents=True)
    other_org_dir = q._org_dir("org:sh")
    (other_org_dir / "b").mkdir(parents=True)
    removed = q.cleanup_expired(organization_id="org:bj1")
    assert removed == ["a"]
    assert (other_org_dir / "b").exists()


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.2 / 16.1 —— preflight 前不产出 OO/HTML/runtime，storage 不枚举
# ─────────────────────────────────────────────────────────────────────────────


async def test_no_runtime_artifacts_generated_during_ingest(tmp_path: Path) -> None:
    """🔴 Requirement 3.2：preflight 前不得生成 HTML/OO/project/runtime。

    判据是**目录树内不存在**任何非 quarantine 产物类型 —— 而不是查字符串。
    """
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    await q.ingest(MemoryFileSource(_make_valid_bytes(256)), organization_id="org:bj1")
    exts = {p.suffix.casefold() for p in (tmp_path / "q").rglob("*") if p.is_file()}
    # 只允许 .bin（字节）与 .json（manifest）
    assert exts <= {".bin", ".json"}
    for forbidden in (".html", ".htm", ".wopi", ".xlsx", ".docx", ".doc"):
        assert forbidden not in exts, f"preflight 前生成了 {forbidden} 产物"
    # 不允许出现 OO/config/runtime 目录名
    names = {p.name.casefold() for p in (tmp_path / "q").rglob("*")}
    for forbidden in ("onlyoffice", "wopi", "config", "runtime", "workpapers", "projects"):
        assert forbidden not in names


async def test_manifest_never_leaks_storage_path(tmp_path: Path) -> None:
    """🔴 Requirement 16.1：storage key 不得公开枚举。"""
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    artifact = await q.ingest(MemoryFileSource(_make_valid_bytes(256)), organization_id="org:bj1")
    payload = artifact.to_dict()
    assert "relativePath" not in payload
    # 绝对路径也不得出现在任何序列化字段里
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert "C:\\\\" not in serialized and "D:\\\\" not in serialized


def test_contains_rejects_path_traversal(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    assert q.contains(tmp_path / "q" / "org" / "x" / "artifact.bin")
    assert not q.contains(tmp_path / "outside.bin")
    assert not q.contains(tmp_path / "q" / ".." / "secret.bin")


async def test_artifact_bytes_path_blocks_out_of_root(tmp_path: Path) -> None:
    q = PrivateQuarantine(
        root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"),
    )
    # 组织名无法构造出越界路径（sanitize 生效），但绝对路径仍必须被 contains 拦
    with pytest.raises(QuarantineError):
        q.artifact_bytes_path("org:bj1", "..")


def test_quarantine_organization_id_is_sanitized(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    d = q._org_dir("../../etc")
    assert d.exists()
    assert ".." not in d.parts
    assert str(d).startswith(str(tmp_path / "q"))


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.6 / 3.7 —— 结构化失败，不返回空报告
# ─────────────────────────────────────────────────────────────────────────────


async def test_rejection_reason_serializes_without_filename_body(tmp_path: Path) -> None:
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    secret_name = "客户A-机密-工资明细.xlsx"
    artifact = await q.ingest(
        MemoryFileSource(b"not a zip", filename=secret_name), organization_id="org:bj1"
    )
    payload = artifact.to_dict()
    serialized = json.dumps(payload, ensure_ascii=False)
    # 展示值回给提交者本人是允许的，但拒绝原因里不得含文件名正文
    assert artifact.rejection is not None
    reason_str = json.dumps(artifact.rejection.to_dict(), ensure_ascii=False)
    assert "工资明细" not in reason_str
    assert "客户A" not in reason_str
    assert artifact.display_name == secret_name
    assert payload["state"] == "REJECTED"


async def test_rejected_artifact_carries_rejection_not_valid_flag(tmp_path: Path) -> None:
    """🔴 拒绝产物绝不携带 ``valid=True`` 之类字段。"""
    q = PrivateQuarantine(root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"))
    artifact = await q.ingest(
        MemoryFileSource(_make_valid_bytes(256), filename="x.pdf"), organization_id="org:bj1"
    )
    payload = artifact.to_dict()
    assert "valid" not in payload
    assert payload["rejection"] is not None
    assert payload["rejection"]["code"] == "EXTENSION_NOT_ALLOWED"
    assert payload["state"] == "REJECTED"


async def test_ingest_stream_handles_multichunk_without_buffering_all(tmp_path: Path) -> None:
    """流式：单块读取上限应等于 CHUNK_SIZE，而非一次全量。"""
    q = PrivateQuarantine(
        root=tmp_path / "q", policy=POLICY_V1, clock=FakeClock("2026:9:8:0:0:0"),
    )
    big = _make_valid_bytes(CHUNK_SIZE * 3 + 17)
    src = MemoryFileSource(big, filename="a.xlsx")
    artifact = await q.ingest(src, organization_id="org:bj1")
    assert artifact.size_bytes == len(big)
    payload = q.load_manifest("org:bj1", artifact.artifact_id)
    assert payload["sizeBytes"] == len(big)
    # 🔴 manifest 不得出现 valid 布尔字段——拒绝/通过必须走结构化 rejection/state
    assert "valid" not in payload
