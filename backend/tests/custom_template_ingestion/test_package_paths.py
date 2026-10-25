"""ZIP 路径规范化守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 4.1
"""
from __future__ import annotations

from pathlib import Path

from app.services.custom_template_ingestion.package_paths import (
    CanonicalZipPath,
    PathRejection,
    PathRejectionCode,
    assert_inside_temp_root,
    find_casefold_collisions,
    inspect_zip_entry_name,
    is_symlink_external_attr,
    posix_join_under,
)


def _reject(raw: str) -> PathRejection:
    result = inspect_zip_entry_name(raw)
    assert isinstance(result, PathRejection), result
    return result


def test_relative_ooxml_path_is_accepted() -> None:
    result = inspect_zip_entry_name("xl/worksheets/sheet1.xml")
    assert isinstance(result, CanonicalZipPath)
    assert result.posix == "xl/worksheets/sheet1.xml"
    assert result.casefold_key == "xl/worksheets/sheet1.xml"


def test_backslash_is_normalized_to_slash() -> None:
    result = inspect_zip_entry_name("xl\\worksheets\\sheet1.xml")
    assert isinstance(result, CanonicalZipPath)
    assert result.posix == "xl/worksheets/sheet1.xml"


def test_absolute_posix_is_rejected() -> None:
    assert _reject("/xl/workbook.xml").code is PathRejectionCode.ABSOLUTE


def test_drive_prefix_is_rejected() -> None:
    assert _reject("C:/Windows/system32").code is PathRejectionCode.DRIVE


def test_unc_is_rejected() -> None:
    assert _reject("//server/share/file.xml").code is PathRejectionCode.UNC


def test_dotdot_is_rejected() -> None:
    assert _reject("xl/../workbook.xml").code is PathRejectionCode.DOT_SEGMENT


def test_dot_segment_is_rejected() -> None:
    assert _reject("xl/./sheet.xml").code is PathRejectionCode.DOT_SEGMENT


def test_empty_segment_is_rejected() -> None:
    assert _reject("xl//sheet.xml").code is PathRejectionCode.EMPTY_SEGMENT


def test_trailing_dot_is_rejected() -> None:
    assert _reject("xl/workbook.xml.").code is PathRejectionCode.TRAILING_DOT_OR_SPACE


def test_ads_colon_is_rejected() -> None:
    assert _reject("xl/workbook.xml:Zone.Identifier").code is PathRejectionCode.ADS_OR_COLON


def test_windows_reserved_device_is_rejected() -> None:
    assert _reject("xl/CON.xml").code is PathRejectionCode.RESERVED_DEVICE
    assert _reject("xl/COM1.xml").code is PathRejectionCode.RESERVED_DEVICE


def test_empty_name_is_rejected() -> None:
    assert _reject("").code is PathRejectionCode.EMPTY_NAME


def test_control_char_is_rejected() -> None:
    assert _reject("xl/\x00sheet.xml").code is PathRejectionCode.CONTROL_CHAR


def test_casefold_collision_is_detected() -> None:
    a = inspect_zip_entry_name("xl/Workbook.xml")
    b = inspect_zip_entry_name("xl/workbook.xml")
    assert isinstance(a, CanonicalZipPath)
    assert isinstance(b, CanonicalZipPath)
    collisions = find_casefold_collisions([a, b])
    assert len(collisions) == 1


def test_unix_symlink_external_attr_is_detected() -> None:
    symlink_attr = 0o120777 << 16
    assert is_symlink_external_attr(symlink_attr) is True
    regular_file = 0o100644 << 16
    assert is_symlink_external_attr(regular_file) is False
    fat_entry = 0
    assert is_symlink_external_attr(fat_entry) is False


def test_assert_inside_temp_root_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "q"
    root.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    rejection = assert_inside_temp_root(root, outside / "x")
    assert rejection is not None
    assert rejection.code is PathRejectionCode.OUTSIDE_ROOT


def test_posix_join_stays_under_root(tmp_path: Path) -> None:
    joined = posix_join_under(tmp_path, "xl/workbook.xml")
    assert joined == tmp_path / "xl" / "workbook.xml"
    assert assert_inside_temp_root(tmp_path, joined) is None
