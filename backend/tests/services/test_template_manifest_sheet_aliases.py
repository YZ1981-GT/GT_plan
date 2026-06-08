"""manifest sheet_aliases 解析测试."""

from app.services.template_manifest_loader import TemplateManifestLoader


def test_get_sheet_aliases_soe_standalone():
    loader = TemplateManifestLoader()
    aliases = loader.get_sheet_aliases("soe_standalone")
    assert "balance_sheet" in aliases
    assert isinstance(aliases["balance_sheet"], list)
    assert "GT_Custom" not in aliases.get("balance_sheet", [])
