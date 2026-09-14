"""ZIP entry 路径规范化与穿越/碰撞拒绝（Requirement 4.1）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 4.1, 4.2

本模块只裁决「这个 ZIP 名字能不能作为受控 temp 内的相对路径」。它不打开
ZIP、不解析 XML、不执行公式。scanner 必须先过这里再读 entry 字节。

规范化顺序（design §4.2，顺序不可交换）：

1. ``\\`` → ``/``；
2. Unicode NFKC；
3. 拒绝绝对路径、drive、UNC、``.`` / ``..``、空 segment；
4. 拒绝尾随点/空格、冒号/ADS、Windows reserved device names；
5. 调用方再读 ZIP external attrs，拒绝 symlink/reparse（本模块只提供
   ``is_symlink_external_attr``，不自己打开 ZIP）；
6. 对规范化路径做 Unicode casefold，调用方用它检测 duplicate/collision；
7. 若真要落盘，``assert_inside_temp_root`` 用 ``Path.resolve()`` 验证边界。

🔴 路径判定全部是**字面量 + 规范化**，不用 ``os.path.commonpath`` 单独当防线
（``..`` 折叠后仍可能落在根内，quarantine 已用字面量闸补过一次）。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

# Windows 保留设备名（Requirement 4.1）。比较前会去掉尾随点，并忽略扩展名。
_WINDOWS_RESERVED: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

#: Unix ZIP external_attr 高 16 位的文件类型掩码 / 符号链接。
_S_IFMT: int = 0o170000
_S_IFLNK: int = 0o120000

#: 拒绝空 segment、``.``、``..`` 的拆分后检查。
_BAD_SEGMENTS: frozenset[str] = frozenset({"", ".", ".."})


class PathRejectionCode(str, Enum):
    """路径拒绝的稳定机器码。scanner finding.code 直接复用。"""

    ABSOLUTE = "PACKAGE.path_absolute"
    DRIVE = "PACKAGE.path_drive"
    UNC = "PACKAGE.path_unc"
    DOT_SEGMENT = "PACKAGE.path_dot_segment"
    EMPTY_SEGMENT = "PACKAGE.path_empty_segment"
    TRAILING_DOT_OR_SPACE = "PACKAGE.path_trailing_dot_or_space"
    ADS_OR_COLON = "PACKAGE.path_ads_or_colon"
    RESERVED_DEVICE = "PACKAGE.path_reserved_device"
    SYMLINK = "PACKAGE.path_symlink"
    COLLISION = "PACKAGE.path_collision"
    OUTSIDE_ROOT = "PACKAGE.path_outside_root"
    CONTROL_CHAR = "PACKAGE.path_control_char"
    EMPTY_NAME = "PACKAGE.path_empty"


@dataclass(frozen=True, slots=True)
class PathRejection:
    code: PathRejectionCode
    original: str
    detail: str


@dataclass(frozen=True, slots=True)
class CanonicalZipPath:
    """通过全部路径闸的 ZIP entry。

    Attributes:
        original: ZIP 中央目录里的原始名字（未清洗，仅用于 finding locator）。
        posix: 正斜杠、NFKC 后的相对路径，不含 ``.`` / ``..``。
        casefold_key: Unicode casefold 后的碰撞键。
    """

    original: str
    posix: str
    casefold_key: str


def inspect_zip_entry_name(raw: str | None) -> CanonicalZipPath | PathRejection:
    """对单个 ZIP entry 名做 Requirement 4.1 的全部字面量闸。

    返回 ``CanonicalZipPath`` 或 ``PathRejection``，永不抛给调用方当「解析失败
    当放行」。空名字也是拒绝。
    """
    if raw is None or raw == "":
        return PathRejection(
            code=PathRejectionCode.EMPTY_NAME,
            original="" if raw is None else raw,
            detail="ZIP entry 名为空",
        )
    if any(ord(ch) < 32 for ch in raw):
        return PathRejection(
            code=PathRejectionCode.CONTROL_CHAR,
            original=raw,
            detail="ZIP entry 名含控制字符",
        )

    unified = raw.replace("\\", "/")
    normalized = unicodedata.normalize("NFKC", unified)

    if normalized.startswith("//") or normalized.startswith("\\\\"):
        return PathRejection(
            code=PathRejectionCode.UNC,
            original=raw,
            detail="UNC / 双斜杠路径",
        )
    if normalized.startswith("/"):
        return PathRejection(
            code=PathRejectionCode.ABSOLUTE,
            original=raw,
            detail="绝对 POSIX 路径",
        )
    if re.match(r"^[A-Za-z]:(/|$)", normalized):
        return PathRejection(
            code=PathRejectionCode.DRIVE,
            original=raw,
            detail="drive 前缀",
        )
    if ":" in normalized:
        return PathRejection(
            code=PathRejectionCode.ADS_OR_COLON,
            original=raw,
            detail="冒号/ADS 流",
        )

    parts = normalized.split("/")
    if any(seg in _BAD_SEGMENTS for seg in parts):
        # 区分空 segment 与 . / ..，便于 remediation。
        if any(seg == "" for seg in parts):
            return PathRejection(
                code=PathRejectionCode.EMPTY_SEGMENT,
                original=raw,
                detail="空路径段",
            )
        return PathRejection(
            code=PathRejectionCode.DOT_SEGMENT,
            original=raw,
            detail="含 . 或 .. 段",
        )

    for seg in parts:
        if seg.endswith(".") or seg.endswith(" "):
            return PathRejection(
                code=PathRejectionCode.TRAILING_DOT_OR_SPACE,
                original=raw,
                detail="段尾随点或空格",
            )
        stem = seg.split(".", 1)[0].rstrip(".").upper()
        if stem in _WINDOWS_RESERVED:
            return PathRejection(
                code=PathRejectionCode.RESERVED_DEVICE,
                original=raw,
                detail=f"Windows reserved device name {stem}",
            )

    posix = "/".join(parts)
    return CanonicalZipPath(
        original=raw,
        posix=posix,
        casefold_key=unicodedata.normalize("NFKC", posix).casefold(),
    )


def is_symlink_external_attr(external_attr: int) -> bool:
    """ZIP Unix 外部属性是否表示符号链接（Requirement 4.1）。

    ``external_attr`` 高 16 位是 Unix st_mode。FAT/DOS 条目高位为 0，不会误伤。
    """
    unix_mode = (int(external_attr) >> 16) & 0xFFFF
    return (unix_mode & _S_IFMT) == _S_IFLNK


def find_casefold_collisions(
    paths: list[CanonicalZipPath],
) -> list[tuple[CanonicalZipPath, CanonicalZipPath]]:
    """同一 casefold 键出现两次即 collision（Requirement 4.1）。"""
    seen: dict[str, CanonicalZipPath] = {}
    collisions: list[tuple[CanonicalZipPath, CanonicalZipPath]] = []
    for path in paths:
        prior = seen.get(path.casefold_key)
        if prior is not None:
            collisions.append((prior, path))
        else:
            seen[path.casefold_key] = path
    return collisions


def assert_inside_temp_root(root: Path, candidate: Path) -> PathRejection | None:
    """落盘前的 realpath 边界闸（Requirement 4.1 第 6 步）。

    必须在 ``inspect_zip_entry_name`` 通过之后调用。``..`` 字面量已在前面拒绝，
    这里拦的是 symlink 跟随与大小写折叠后的越界。
    """
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return PathRejection(
            code=PathRejectionCode.OUTSIDE_ROOT,
            original=str(candidate),
            detail="realpath 越出受控 temp root",
        )
    return None


def posix_join_under(root: Path, posix: str) -> Path:
    """把已通过闸的 posix 相对路径接到 root 上，不经用户原始字符串。"""
    rel = PurePosixPath(posix)
    if rel.is_absolute():
        raise ValueError("canonical posix 不得为绝对路径")
    return root.joinpath(*rel.parts)
