"""TemplateManifestLoader 单元测试."""

from pathlib import Path

import pytest

from app.services.template_manifest_loader import TemplateManifestLoader


@pytest.fixture
def loader() -> TemplateManifestLoader:
    return TemplateManifestLoader()


def test_version_non_empty(loader: TemplateManifestLoader):
    assert loader.version() == "2025-v1"


def test_resolve_disclosure_notes_four_variants(loader: TemplateManifestLoader):
    cases = [
        ("soe", "standalone", "disclosure_notes/soe_standalone.docx"),
        ("soe", "consolidated", "disclosure_notes/soe_consolidated.docx"),
        ("listed", "standalone", "disclosure_notes/listed_standalone.docx"),
        ("listed", "consolidated", "disclosure_notes/listed_consolidated.docx"),
    ]
    for template_type, scope, expected_rel in cases:
        entry = loader.resolve_disclosure_notes(template_type, scope)
        assert str(entry.rel_path).replace("\\", "/") == expected_rel
        assert entry.exists


def test_resolve_disclosure_notes_uses_variant_key_not_template_type_only(
    loader: TemplateManifestLoader,
):
    standalone = loader.resolve_disclosure_notes("soe", "standalone")
    consolidated = loader.resolve_disclosure_notes("soe", "consolidated")
    assert standalone.rel_path != consolidated.rel_path


def test_resolve_financial_statements(loader: TemplateManifestLoader):
    entry = loader.resolve_financial_statements("listed", "consolidated")
    assert str(entry.rel_path).replace("\\", "/") == (
        "financial_statements/listed_consolidated.xlsx"
    )
    assert entry.exists


def test_resolve_report_body_disclaimer_all(loader: TemplateManifestLoader):
    entry = loader.resolve_report_body("disclaimer", "_all", "simple")
    assert "1.4.1" in entry.rel_path.name


def test_resolve_report_body_scope_consolidated_vs_standalone(
    loader: TemplateManifestLoader,
):
    """report_body 双口径：standalone 走 standalone/ 子目录，默认/合并走原路径。"""
    consolidated = loader.resolve_report_body("unqualified", "type_a", "simple")
    standalone = loader.resolve_report_body(
        "unqualified", "type_a", "simple", "standalone"
    )
    default_scope = loader.resolve_report_body("unqualified", "type_a", "simple")

    assert "standalone/" in str(standalone.rel_path).replace("\\", "/")
    assert "standalone/" not in str(consolidated.rel_path).replace("\\", "/")
    # 缺省 report_scope 等同合并套（向后兼容）
    assert default_scope.rel_path == consolidated.rel_path
    assert consolidated.exists and standalone.exists


def test_resolve_report_body_unknown_scope_falls_back_consolidated(
    loader: TemplateManifestLoader,
):
    entry = loader.resolve_report_body("unqualified", "type_a", "simple", "bogus")
    assert "standalone/" not in str(entry.rel_path).replace("\\", "/")


def test_validate_warns_on_missing_file(tmp_path: Path):
    manifest = {
        "version": "test",
        "disclosure_notes": {"soe_standalone": "disclosure_notes/missing.docx"},
    }
    base = tmp_path
    (base / "template_manifest.json").write_text(
        __import__("json").dumps(manifest), encoding="utf-8"
    )
    loader = TemplateManifestLoader(base_dir=base)
    warnings = loader.validate()
    assert any("missing" in w.lower() for w in warnings)


def test_resolve_unknown_variant_raises(tmp_path: Path):
    manifest = {"version": "test", "disclosure_notes": {"soe_standalone": "x.docx"}}
    base = tmp_path
    (base / "template_manifest.json").write_text(
        __import__("json").dumps(manifest), encoding="utf-8"
    )
    loader = TemplateManifestLoader(base_dir=base)
    with pytest.raises(KeyError, match="disclosure_notes/soe_consolidated"):
        loader.resolve_disclosure_notes("soe", "consolidated")
