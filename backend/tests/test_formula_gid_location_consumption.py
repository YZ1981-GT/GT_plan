"""Formula Task 4 — consume G-ID StableSheetIdentity (no name/index identity)."""

from __future__ import annotations

from app.services.guidance_gid import (
    GID_CONTRACT_ID,
    GID_CONTRACT_VERSION,
    sheet_identity_from_authority,
)


def test_formula_consumes_gid_contract_constants() -> None:
    assert GID_CONTRACT_ID == "G-ID"
    assert GID_CONTRACT_VERSION == "1.0"


def test_sheet_identity_null_reason_when_uid_missing() -> None:
    ident = sheet_identity_from_authority(
        wp_code="D0",
        sheet_uid=None,
        sheet_code="D0-1",
        snapshot=None,
    )
    assert ident.sheet_uid is None
    assert ident.null_reason == "sheet_uid_unavailable"
    # Name/index are not part of catalog key
    assert ident.catalog_key.endswith("|D0|")


def test_sheet_identity_catalog_key_uses_uid_not_code_alone() -> None:
    a = sheet_identity_from_authority(
        wp_code="D0",
        sheet_uid="uid-a",
        sheet_code="D0-1",
        snapshot=None,
    )
    b = sheet_identity_from_authority(
        wp_code="D0",
        sheet_uid="uid-b",
        sheet_code="D0-1",
        snapshot=None,
    )
    assert a.catalog_key != b.catalog_key
    assert a.sheet_code == b.sheet_code
