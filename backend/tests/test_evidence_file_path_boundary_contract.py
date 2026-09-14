"""Wave 0 契约冻结测试 — file_path 存储边界 / opaque locator / 零字节 I/O。

Spec: attachment-ocr-ai-evidence-governance-hardening, Task 1.2
Requirements: R1, R14
Properties: P1(项目隔离-脱敏), P2(存储边界封闭)

本文件冻结 Wave 0 契约，供 Wave 2 (task 3.4/3.5) 的 StorageBoundaryResolver /
LocatorProjection 实现遵循。冻结项：

  C1  scope/权限校验先于任何 stat/open/read（scope-first）。
  C2  规范化后仍在 Storage_Boundary 内的路径才允许字节 I/O；
      边界或权限失败时 open/stat/read 调用计数必须为 0。
  C3  兼容响应中的 file_path 只能是 opaque/脱敏 locator 或受控下载 URL，
      绝不返回绝对路径、storage key 或 token。

契约以本模块内的**参考模型**（reference model）表达并用 spy 冻结语义；
参考模型是可执行规范，Wave 2 的真实实现必须满足同一契约。
纯谓词属性使用全局 `fast` profile（conftest 注册，默认 max_examples=5）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

try:
    from hypothesis import given
    from hypothesis import strategies as st
    _HAS_HYPOTHESIS = True
except Exception:  # pragma: no cover - hypothesis 缺失时降级
    _HAS_HYPOTHESIS = False


# ─────────────────────────────────────────────────────────────────────────────
# 参考模型：Storage Boundary 解析 + opaque locator 投影
# ─────────────────────────────────────────────────────────────────────────────

class BoundaryError(Exception):
    """脱敏边界/权限失败。对外统一为 SCOPE_NOT_FOUND_OR_FORBIDDEN，不含路径。"""

    error_code = "SCOPE_NOT_FOUND_OR_FORBIDDEN"


class ByteIOSpy:
    """记录字节读取器（open/stat/read）调用次数的 spy。

    C2 契约要求：边界/权限失败时该计数恒为 0。
    """

    def __init__(self) -> None:
        self.open_calls = 0
        self.stat_calls = 0
        self.read_calls = 0

    @property
    def total(self) -> int:
        return self.open_calls + self.stat_calls + self.read_calls

    def open(self, path: str) -> object:
        self.open_calls += 1
        return object()

    def stat(self, path: str) -> object:
        self.stat_calls += 1
        return object()

    def read(self, path: str) -> bytes:
        self.read_calls += 1
        return b""


def _normalize_within_boundary(boundary_root: str, file_path: str) -> Path | None:
    """把 file_path 规范化到 boundary_root 内的真实路径。

    返回 None 表示越界（含 traversal / 绝对逃逸 / paperless:// 远程）。
    纯路径运算，不触碰文件系统（不 stat/exists）。
    """
    if not file_path or file_path.startswith("paperless://"):
        return None
    root = Path(os.path.normpath(boundary_root)).absolute()
    # 相对路径按 boundary_root 归一；绝对路径直接归一
    raw = Path(file_path)
    if raw.is_absolute():
        candidate = Path(os.path.normpath(str(raw))).absolute()
    else:
        candidate = Path(os.path.normpath(str(root / file_path))).absolute()
    try:
        # containment：candidate 必须在 root 之内（含相等）
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def resolve_for_read(
    *,
    boundary_root: str,
    file_path: str,
    has_scope: bool,
    spy: ByteIOSpy,
) -> Path:
    """参考实现：scope-first → 边界 containment → 才允许后续字节 I/O。

    失败一律抛脱敏 BoundaryError，且抛出前不得调用 spy 的任何 I/O 方法。
    返回规范化后的安全路径（调用方随后才可 spy.open）。
    """
    # C1 scope-first：权限先于路径解析与任何 I/O
    if not has_scope:
        raise BoundaryError()
    # C2 边界 containment 先于字节 I/O
    safe = _normalize_within_boundary(boundary_root, file_path)
    if safe is None:
        raise BoundaryError()
    return safe


def project_locator(file_path: str, attachment_id: str) -> str:
    """C3：把内部 file_path 投影为对外 opaque locator。

    - paperless:// → 保留为 opaque scheme（非绝对文件系统路径）。
    - 其他一律返回受控下载 URL，绝不回传绝对路径/storage key。
    """
    if file_path.startswith("paperless://"):
        return file_path  # 已是 opaque scheme
    return f"/api/attachments/{attachment_id}/download"


def _looks_like_absolute_path(value: str) -> bool:
    """判定字符串是否泄露了绝对文件系统路径（POSIX 或 Windows 盘符/UNC）。"""
    if not value:
        return False
    if value.startswith("paperless://"):
        return False
    if value.startswith("/api/") or value.startswith("http://") or value.startswith("https://"):
        return False
    if value.startswith("/"):
        return True  # POSIX 绝对路径
    if len(value) >= 3 and value[1] == ":" and value[2] in ("\\", "/"):
        return True  # Windows 盘符 C:\ or C:/
    if value.startswith("\\\\"):
        return True  # UNC
    return False


# ─────────────────────────────────────────────────────────────────────────────
# C1 / C2 — 边界与权限失败时零字节 I/O
# ─────────────────────────────────────────────────────────────────────────────

BOUNDARY_ROOT = "/srv/audit/storage"

# 越界样本：traversal、绝对逃逸、UNC、paperless 远程
OUT_OF_BOUNDARY = [
    "../../etc/passwd",
    "../../../root/.ssh/id_rsa",
    "/etc/passwd",
    "/srv/audit/storage/../secret.key",
    "subdir/../../escape.txt",
    "paperless://documents/9",
]

# 合法样本：boundary 内相对路径
IN_BOUNDARY = [
    "projects/p1/general/a.pdf",
    "projects/p1/invoice/2025/b.xlsx",
    "nested/deep/dir/c.png",
]


@pytest.mark.parametrize("bad_path", OUT_OF_BOUNDARY)
def test_boundary_failure_zero_byte_io(bad_path: str) -> None:
    """C2：越界路径在字节 I/O 前被拒绝，open/stat/read 计数恒为 0。"""
    spy = ByteIOSpy()
    with pytest.raises(BoundaryError) as exc:
        resolve_for_read(
            boundary_root=BOUNDARY_ROOT,
            file_path=bad_path,
            has_scope=True,
            spy=spy,
        )
    assert exc.value.error_code == "SCOPE_NOT_FOUND_OR_FORBIDDEN"
    # 脱敏：错误不含目标路径
    assert bad_path not in str(exc.value)
    assert spy.total == 0, f"边界失败但发生了字节 I/O: {vars(spy)}"


@pytest.mark.parametrize("any_path", IN_BOUNDARY + OUT_OF_BOUNDARY)
def test_scope_first_before_byte_io(any_path: str) -> None:
    """C1：无 scope 权限时，先于路径解析/字节 I/O 拒绝，计数为 0。"""
    spy = ByteIOSpy()
    with pytest.raises(BoundaryError):
        resolve_for_read(
            boundary_root=BOUNDARY_ROOT,
            file_path=any_path,
            has_scope=False,
            spy=spy,
        )
    assert spy.total == 0


@pytest.mark.parametrize("good_path", IN_BOUNDARY)
def test_in_boundary_resolves_and_allows_io(good_path: str) -> None:
    """合法边界内路径解析成功，随后字节 I/O 才被允许。"""
    spy = ByteIOSpy()
    safe = resolve_for_read(
        boundary_root=BOUNDARY_ROOT,
        file_path=good_path,
        has_scope=True,
        spy=spy,
    )
    assert safe is not None
    # 解析阶段本身不做 I/O
    assert spy.total == 0
    # 解析后调用方才可读取
    spy.open(str(safe))
    assert spy.open_calls == 1
    # 解析结果必须落在 boundary 内
    safe.relative_to(Path(os.path.normpath(BOUNDARY_ROOT)).absolute())


# ─────────────────────────────────────────────────────────────────────────────
# C3 — opaque locator：兼容响应 file_path 绝不返回绝对路径
# ─────────────────────────────────────────────────────────────────────────────

RAW_LOCATORS = [
    ("/srv/audit/storage/projects/p1/general/a.pdf", "att-1"),
    ("C:\\storage\\projects\\p1\\b.xlsx", "att-2"),
    ("\\\\fileserver\\share\\c.docx", "att-3"),
    ("storage/projects/p1/general/d.png", "att-4"),
    ("paperless://documents/42", "att-5"),
]


@pytest.mark.parametrize("raw,att_id", RAW_LOCATORS)
def test_opaque_locator_never_absolute_path(raw: str, att_id: str) -> None:
    """C3：投影后的 locator 绝不是绝对文件系统路径。"""
    projected = project_locator(raw, att_id)
    assert not _looks_like_absolute_path(projected), (
        f"opaque locator 泄露了绝对路径: {projected!r} (raw={raw!r})"
    )
    # 必须是 opaque scheme 或受控下载 URL
    assert projected.startswith("paperless://") or projected.startswith("/api/attachments/")


def test_absolute_path_detector_sanity() -> None:
    """自检：绝对路径探测器正确识别各形态（避免 C3 因探测器失灵而假绿）。"""
    assert _looks_like_absolute_path("/etc/passwd") is True
    assert _looks_like_absolute_path("C:\\x\\y") is True
    assert _looks_like_absolute_path("C:/x/y") is True
    assert _looks_like_absolute_path("\\\\srv\\share") is True
    assert _looks_like_absolute_path("/api/attachments/att-1/download") is False
    assert _looks_like_absolute_path("paperless://documents/1") is False
    assert _looks_like_absolute_path("") is False


# ─────────────────────────────────────────────────────────────────────────────
# 属性测试（全局 fast profile：max_examples=5）
# ─────────────────────────────────────────────────────────────────────────────

if _HAS_HYPOTHESIS:

    _segment = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
        min_size=1,
        max_size=8,
    )

    @given(st.lists(_segment, min_size=1, max_size=5))
    def test_property_p2_in_boundary_always_contained(segments: list[str]) -> None:
        """P2：纯相对路径(无 ..)规范化后恒在 boundary 内且不触发 I/O。"""
        rel = "/".join(segments)
        spy = ByteIOSpy()
        safe = resolve_for_read(
            boundary_root=BOUNDARY_ROOT,
            file_path=rel,
            has_scope=True,
            spy=spy,
        )
        assert spy.total == 0
        safe.relative_to(Path(os.path.normpath(BOUNDARY_ROOT)).absolute())

    @given(st.lists(_segment, min_size=1, max_size=4))
    def test_property_p2_traversal_always_rejected_zero_io(segments: list[str]) -> None:
        """P2：任意含 ../ 逃逸的路径恒被拒绝且零字节 I/O。"""
        # 构造保证逃逸出 root 的 traversal（前缀足量 ..）
        escape = "/".join([".."] * (len(segments) + 4) + segments)
        spy = ByteIOSpy()
        with pytest.raises(BoundaryError):
            resolve_for_read(
                boundary_root=BOUNDARY_ROOT,
                file_path=escape,
                has_scope=True,
                spy=spy,
            )
        assert spy.total == 0

    @given(
        st.one_of(
            st.just(""),
            st.text(min_size=1, max_size=20),
        ),
        st.text(alphabet="abcdef0123456789-", min_size=1, max_size=12),
    )
    def test_property_p1_locator_never_absolute(raw: str, att_id: str) -> None:
        """P1/C3：任意 raw locator 投影后绝不泄露绝对路径。"""
        projected = project_locator(raw, att_id)
        assert not _looks_like_absolute_path(projected)


# ─────────────────────────────────────────────────────────────────────────────
# 调用方清单冻结：inventory JSON 结构与覆盖校验（CI 阻止漂移）
# ─────────────────────────────────────────────────────────────────────────────

_SPEC_DIR = (
    Path(__file__).resolve().parents[2]
    / ".kiro" / "specs" / "attachment-ocr-ai-evidence-governance-hardening"
)
_INVENTORY = _SPEC_DIR / "file_path_caller_inventory.json"

_REQUIRED_CALLER_FIELDS = {
    "id",
    "owner",
    "call_path",
    "io_type",
    "detail",
    "target_adapter",
    "migration_phase",
    "verification_evidence",
    "due_date",
}

_ALLOWED_IO_TYPES = {
    "write-locator",
    "write-bytes",
    "read-bytes",
    "download",
    "preview",
    "expose-locator",
    "export",
    "archive",
    "associate",
    "consume-locator",
}


def _load_inventory() -> dict:
    with open(_INVENTORY, encoding="utf-8") as f:
        return json.load(f)


def test_inventory_exists_and_parses() -> None:
    assert _INVENTORY.exists(), f"caller inventory 缺失: {_INVENTORY}"
    data = _load_inventory()
    assert data["spec"] == "attachment-ocr-ai-evidence-governance-hardening"
    assert data["task"] == "1.2"
    assert set(data["requirements"]) == {"R1", "R14"}


def test_inventory_every_caller_has_required_fields() -> None:
    data = _load_inventory()
    callers = data["callers"]
    assert callers, "caller inventory 为空"
    ids = [c["id"] for c in callers]
    assert len(ids) == len(set(ids)), "caller id 重复"
    for c in callers:
        missing = _REQUIRED_CALLER_FIELDS - set(c.keys())
        assert not missing, f"{c.get('id')} 缺少字段: {missing}"
        assert c["io_type"] in _ALLOWED_IO_TYPES, f"{c['id']} 非法 io_type {c['io_type']}"


def test_inventory_covers_p0_surface() -> None:
    """冻结：三大 P0 高危面(download/preview/expose-locator)必须已登记。"""
    data = _load_inventory()
    io_types = {c["io_type"] for c in data["callers"]}
    for critical in ("download", "preview", "expose-locator", "write-locator", "archive"):
        assert critical in io_types, f"P0 高危面 {critical} 未在 inventory 中登记"

    # 已实证的关键调用方必须在册（防止 CI 静默丢失）
    call_paths = " ".join(c["call_path"] for c in data["callers"])
    for needle in (
        "attachments.py::download_attachment",
        "attachments.py::preview_attachment",
        "office_preview.py::preview_office_as_pdf",
        "attachment_service.py::AttachmentService._to_dict",
    ):
        assert needle in call_paths, f"关键调用方未登记: {needle}"


def test_inventory_frozen_contracts_present() -> None:
    data = _load_inventory()
    fc = data["frozen_contracts"]
    for key in ("C1_scope_first", "C2_boundary_before_io", "C3_opaque_locator"):
        assert key in fc and fc[key].strip(), f"冻结契约 {key} 缺失"
