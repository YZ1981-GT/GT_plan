"""ZIP/XML/OOXML package security scanner 守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.7
"""
from __future__ import annotations

import ast
import io
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from app.services.custom_template_ingestion.package_scanner import (
    FINDING_CORRUPT,
    FINDING_SCAN_COMPLETE,
    SCANNER_BUILD_ID,
    scan_package_bytes,
)
from app.services.custom_template_ingestion.package_xml import (
    XmlRejectionCode,
    scan_xml_bytes,
)
from app.services.custom_template_ingestion.policy import (
    POLICY_V1,
    CustomTemplateIngestionPolicy,
    FeatureDecision,
    Severity,
    Verdict,
    decide_feature,
    finalize_allowed,
)

SCANNER_PATH = Path(__file__).resolve().parents[2] / "app/services/custom_template_ingestion/package_scanner.py"


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""

SHEET = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1"><f>SUM(B1:B2)</f><v>0</v></c></row>
  </sheetData>
</worksheet>
"""


def _xlsx(overrides: dict[str, str | bytes] | None = None) -> bytes:
    parts: dict[str, str | bytes] = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "xl/workbook.xml": WORKBOOK,
        "xl/_rels/workbook.xml.rels": WORKBOOK_RELS,
        "xl/worksheets/sheet1.xml": SHEET,
    }
    if overrides:
        parts.update(overrides)
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        for name, payload in parts.items():
            zf.writestr(name, payload)
    return buf.getvalue()


def _codes(result) -> set[str]:
    return {f.code for f in result.preflight.findings}


def test_minimal_xlsx_is_preflight_ready() -> None:
    result = scan_package_bytes(_xlsx(), filename_hint="ok.xlsx")
    assert result.is_valid is True
    assert result.preflight.verdict is Verdict.PREFLIGHT_READY
    assert FINDING_SCAN_COMPLETE in _codes(result)
    assert result.finalize_blocked is False
    assert result.container_kind == "xlsx"


def test_empty_bytes_never_valid() -> None:
    result = scan_package_bytes(b"")
    assert result.is_valid is False
    assert result.preflight.verdict is Verdict.BLOCKED
    assert FINDING_CORRUPT in _codes(result)


def test_empty_zip_missing_workbook_is_blocked() -> None:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "not a workbook")
    result = scan_package_bytes(buf.getvalue())
    assert result.is_valid is False
    assert FINDING_CORRUPT in _codes(result)


def test_dotdot_entry_is_blocked_and_skips_xml() -> None:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("xl/../evil.xml", "<root/>")
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
    result = scan_package_bytes(buf.getvalue())
    assert result.is_valid is False
    assert any(c.startswith("PACKAGE.path_") for c in _codes(result))


def test_vba_project_is_blocker_not_stripped() -> None:
    result = scan_package_bytes(_xlsx({"xl/vbaProject.bin": b"MZ"}), filename_hint="book.xlsx")
    assert result.is_valid is False
    assert any("vba_macro" in c for c in _codes(result))
    assert result.finalize_blocked is True


def test_xlsm_hint_is_finalize_blocked_even_without_vba_part() -> None:
    """Requirement 4.4：容器本身 PREFLIGHT_ONLY，不得改扩展名后发布。"""
    result = scan_package_bytes(_xlsx(), filename_hint="book.xlsm")
    assert result.finalize_blocked is True
    assert "container.xlsm" in result.observed_features
    # 没有 vba part 时 package scan 可以完成（WARNING），但 finalize 仍阻断。
    assert finalize_allowed(decide_feature("container.xlsm")) is False


def test_external_links_directory_is_blocker() -> None:
    result = scan_package_bytes(_xlsx({
        "xl/externalLinks/externalLink1.xml": "<externalLink/>",
    }))
    assert result.is_valid is False
    assert any("external_link" in c for c in _codes(result))


def test_external_relationship_target_mode_is_blocker() -> None:
    rels = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://evil.example" TargetMode="External"/>
</Relationships>
"""
    result = scan_package_bytes(_xlsx({"xl/worksheets/_rels/sheet1.xml.rels": rels}))
    assert result.is_valid is False
    assert any("external_relationship" in c for c in _codes(result))


def test_unknown_content_type_is_block_pending_policy() -> None:
    types = CONTENT_TYPES.replace(
        "</Types>",
        '<Override PartName="/xl/weird.xml" ContentType="application/x-unknown-gadget+xml"/>\n</Types>',
    )
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", types)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("xl/workbook.xml", WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", SHEET)
        zf.writestr("xl/weird.xml", "<gadget/>")
    result = scan_package_bytes(buf.getvalue())
    assert result.is_valid is False
    assert any("pending" in c for c in _codes(result))
    assert decide_feature("contenttype:application/x-unknown-gadget+xml") is FeatureDecision.BLOCK_PENDING_POLICY


def test_image_enters_preservation_inventory_not_silent_drop() -> None:
    result = scan_package_bytes(_xlsx({"xl/media/image1.png": b"\x89PNG\r\n"}))
    assert "image" in result.preflight.preservation_inventory
    assert "image" in result.observed_features


def test_dtd_is_rejected() -> None:
    xml = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><foo>&x;</foo>'
    rejection = scan_xml_bytes(xml, locator="evil.xml")
    from app.services.custom_template_ingestion.package_xml import XmlScanRejection
    assert isinstance(rejection, XmlScanRejection)
    assert rejection.code is XmlRejectionCode.DTD


def test_dtd_in_package_is_blocker() -> None:
    evil = '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x SYSTEM "http://127.0.0.1/x">]><workbook/>'
    result = scan_package_bytes(_xlsx({"xl/workbook.xml": evil}))
    assert result.is_valid is False
    assert any("xml" in c for c in _codes(result))


def test_xml_depth_budget_is_blocker() -> None:
    tight = CustomTemplateIngestionPolicy(max_xml_depth=3)
    deep = b"<a><b><c><d>x</d></c></b></a>"
    rejection = scan_xml_bytes(deep, locator="deep.xml", policy=tight)
    from app.services.custom_template_ingestion.package_xml import XmlScanRejection
    assert isinstance(rejection, XmlScanRejection)
    assert rejection.code is XmlRejectionCode.DEPTH


def test_corrupt_bytes_are_blocked() -> None:
    result = scan_package_bytes(b"PK\x03\x04not-a-zip")
    assert result.is_valid is False
    assert FINDING_CORRUPT in _codes(result)


def test_casefold_collision_is_blocker() -> None:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("xl/workbook.xml", WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", SHEET)
        zf.writestr("xl/Workbook.xml", WORKBOOK)
    result = scan_package_bytes(buf.getvalue())
    assert result.is_valid is False
    assert any("collision" in c for c in _codes(result))


def test_symlink_entry_is_blocker() -> None:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("xl/workbook.xml", WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", SHEET)
        info = ZipInfo("xl/link.xml")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, "<a/>")
    result = scan_package_bytes(buf.getvalue())
    assert result.is_valid is False
    assert any("symlink" in c for c in _codes(result))


def test_empty_findings_path_never_marks_valid() -> None:
    """Requirement 5.7：空/异常 report 永不 valid。扫描器 _finish 在空 findings 时补 BLOCKER。"""
    from app.services.custom_template_ingestion.package_scanner import _finish
    from app.services.custom_template_ingestion.policy import ResourceObservation

    result = _finish(
        [], set(), [], [], None, 0, 0, 0,
        ResourceObservation(), POLICY_V1,
    )
    assert result.is_valid is False
    assert any(f.severity is Severity.BLOCKER for f in result.preflight.findings)


def test_scanner_module_does_not_import_network_clients() -> None:
    """Requirement 4.2 / 5.1：worker 禁网是结构性的，不是运行时开关。"""
    source = SCANNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"urllib", "httpx", "requests", "aiohttp", "socket", "http"}
    assert imported.isdisjoint(forbidden), imported


def test_formulas_are_not_evaluated() -> None:
    """Requirement 4.3：公式只当文本过 XML。scanner 源码不得 import openpyxl 计算链。"""
    source = SCANNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "openpyxl" not in imported
    result = scan_package_bytes(_xlsx())
    assert result.is_valid is True
    # 公式格仍在包内，只是未被求值；scan 完成不等于公式被执行。
    assert FINDING_SCAN_COMPLETE in _codes(result)


def test_scanner_build_id_is_versioned() -> None:
    assert SCANNER_BUILD_ID.startswith("custom-template-package-scanner/v1")


def test_module_does_not_create_oo_or_html_artifacts() -> None:
    tree = ast.parse(SCANNER_PATH.read_text(encoding="utf-8"))
    func_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert not any("wopi" in n.lower() or "html" in n.lower() for n in func_names)
    assert "scan_package_bytes" in func_names
