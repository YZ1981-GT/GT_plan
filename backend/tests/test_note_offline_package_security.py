"""附注离线包必须绑定项目、年度、准则和导出时章节基线。"""
from __future__ import annotations

import json
import uuid
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.services.note_offline_export_service import export_sections_to_xlsx
from app.services.note_offline_import_service import ConflictResolution, NoteOfflineImportService, validate_import_file
from app.services.note_offline_package import context_errors

PID = uuid.UUID("11111111-1111-4111-8111-111111111111")
YEAR = 2025


def _section(value: int = 1) -> dict:
    return {
        "section_id": "s1", "note_section": "八、1", "section_title": "货币资金",
        "guidance_text": "请核对", "table_data": {
            "headers": ["项目", "金额"], "rows": [{"label": "A", "values": [value]}],
        },
    }


def _signed(section: dict | None = None) -> bytes:
    payload, _ = export_sections_to_xlsx(
        [section or _section()], project_name="测试", year=YEAR,
        package_context={"project_id": PID, "year": YEAR, "template_type": "soe"},
    )
    return payload


def _rewrite(payload: bytes, mutate) -> bytes:
    wb = load_workbook(BytesIO(payload))
    mutate(wb)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_signed_package_roundtrip_and_context_baseline() -> None:
    validation = validate_import_file(_signed())
    assert validation.valid is True and validation.legacy_unsigned is False
    assert validation.manifest["project_id"] == str(PID)
    assert context_errors(
        validation.manifest, project_id=PID, year=YEAR, template_type="soe",
        current_sections=[_section()], write_section_ids=["s1"],
    ) == []


@pytest.mark.parametrize("field,value", [
    ("project_id", "22222222-2222-4222-8222-222222222222"),
    ("year", 2024),
    ("template_type", "listed"),
])
def test_manifest_identity_tampering_breaks_signature(field, value) -> None:
    def mutate(wb):
        manifest = json.loads(wb["_meta_"]["B6"].value)
        manifest[field] = value
        wb["_meta_"]["B6"] = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    result = validate_import_file(_rewrite(_signed(), mutate))
    assert result.valid is False
    assert any("签名校验失败" in error for error in result.errors)


def test_meta_tamper_is_rejected_even_when_public_hash_is_recomputed() -> None:
    import hashlib

    def mutate(wb):
        compressed = wb["_meta_"]["B1"].value + "A"
        wb["_meta_"]["B1"] = compressed
        wb["_meta_"]["B3"] = hashlib.sha256(compressed.encode("utf-8")).hexdigest()

    result = validate_import_file(_rewrite(_signed(), mutate))
    assert result.valid is False
    assert any("解压失败" in error or "meta 摘要" in error for error in result.errors)


def test_sheet_identity_must_match_manifest_and_meta() -> None:
    def mutate(wb):
        section_sheet = next(ws for ws in wb.worksheets if ws.title not in {"注意事项", "章节清单", "_meta_"})
        section_sheet["A2"] = "section_id:other"

    result = validate_import_file(_rewrite(_signed(), mutate))
    assert result.valid is False
    assert any("章节 sheet" in error for error in result.errors)


def test_cross_project_year_standard_and_stale_baseline_are_rejected() -> None:
    manifest = validate_import_file(_signed()).manifest
    assert any("其他项目" in e for e in context_errors(
        manifest, project_id=uuid.uuid4(), year=YEAR, template_type="soe", current_sections=[_section()],
    ))
    assert any("其他年度" in e for e in context_errors(
        manifest, project_id=PID, year=2024, template_type="soe", current_sections=[_section()],
    ))
    assert any("准则" in e for e in context_errors(
        manifest, project_id=PID, year=YEAR, template_type="listed", current_sections=[_section()],
    ))
    assert any("导出后已变化" in e for e in context_errors(
        manifest, project_id=PID, year=YEAR, template_type="soe", current_sections=[_section(2)],
    ))


@pytest.mark.asyncio
async def test_legacy_unsigned_package_is_preview_only() -> None:
    legacy, _ = export_sections_to_xlsx([_section()], project_name="测试", year=YEAR)
    validation = validate_import_file(legacy)
    assert validation.valid is True and validation.legacy_unsigned is True
    result = await NoteOfflineImportService(None).execute_import(
        legacy, PID, YEAR, str(uuid.uuid4()), {"s1": ConflictResolution.OVERWRITE},
    )
    assert result.success is False
    assert "只能预览" in result.errors[0]
