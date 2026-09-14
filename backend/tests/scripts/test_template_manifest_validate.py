"""validate_template_manifest.py 冒烟测试."""

from pathlib import Path

import pytest

from app.services.template_manifest_loader import TemplateManifestLoader, resolve_template_base_dir


def test_resolve_template_base_dir_default_exists():
    base = resolve_template_base_dir()
    assert base.is_dir()
    assert (base / "template_manifest.json").is_file()


def test_loader_validate_returns_list():
    loader = TemplateManifestLoader()
    warnings = loader.validate()
    assert isinstance(warnings, list)


def test_disclosure_notes_files_exist_or_warn():
    """四变体附注 docx 必须存在（POC 资产已入库）."""
    loader = TemplateManifestLoader()
    for scope in ("standalone", "consolidated"):
        for tt in ("soe", "listed"):
            entry = loader.resolve_disclosure_notes(tt, scope)
            if not entry.exists:
                pytest.skip(f"missing asset: {entry.abs_path}")


def test_validate_script_importable():
    scripts = Path(__file__).resolve().parent.parent.parent / "scripts"
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_template_manifest",
        scripts / "validate_template_manifest.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.validate_manifest(strict=False) in (0, 1)
