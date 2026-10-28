"""A 类签字件与精确匹配声明键（spec attachment-archive-and-a-class-evidence 需求 7，ADR-AE-10）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import workpaper_evidence_requirements as wer
from app.services.attachment_upload_policy import ATTACHMENT_TYPES
from app.services.workpaper_evidence_intake import EVIDENCE_TYPES, default_evidence_type

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "backend" / "data" / "workpaper_evidence_requirements.json"

#: 本 spec 声明签字件的底稿（design §9）；精确键只匹配编码本身
SIGNED_DECLARED = ["A16", "A10", "A10-1", "A9-1", "A9-2", "A8-1", "A17-6", "A17-7", "A17-7A", "A18-1", "A18-2"]
#: 不应带签字件声明：A16 / A10 的变体（精确键不继承）、平台自有签发表单 A1-11
NOT_DECLARED = ["A16-1", "A16-7", "A16A", "A10-2", "A10A", "A1-11", "A17-5", "A9", "A8"]


@pytest.fixture(autouse=True)
def _fresh_config():
    wer.clear_evidence_requirements_cache()
    yield
    wer.clear_evidence_requirements_cache()


def test_signed_registered_in_both_backend_registries():
    assert "signed" in ATTACHMENT_TYPES
    assert "signed" in EVIDENCE_TYPES


@pytest.mark.parametrize("wp_code", SIGNED_DECLARED)
def test_a_class_signed_declared(wp_code):
    reqs = wer.resolve_requirements_for_wp_code(wp_code)
    assert [r["type"] for r in reqs] == ["signed"], wp_code
    assert reqs[0]["label"].endswith("签字件")


@pytest.mark.parametrize("wp_code", NOT_DECLARED)
def test_variants_do_not_inherit(wp_code):
    assert all(r["type"] != "signed" for r in wer.resolve_requirements_for_wp_code(wp_code)), wp_code


def test_exact_key_wins_over_prefix(monkeypatch):
    cfg = {
        "A16": [{"type": "voucher", "label": "前缀"}],
        "=A16": [{"type": "signed", "label": "精确"}],
        "=E1": [{"type": "signed", "label": "精确 E1"}],
        "E1": [{"type": "bank_statement", "label": "前缀 E1"}],
    }
    monkeypatch.setattr(wer, "load_evidence_requirements_config", lambda: cfg)
    assert [r["label"] for r in wer.resolve_requirements_for_wp_code("A16")] == ["精确"]
    # 变体只看前缀键：精确键不参与最长前缀竞争
    assert [r["label"] for r in wer.resolve_requirements_for_wp_code("A16-1")] == ["前缀"]
    assert [r["label"] for r in wer.resolve_requirements_for_wp_code("E1A")] == ["前缀 E1"]
    assert [r["label"] for r in wer.resolve_requirements_for_wp_code("E1")] == ["精确 E1"]
    # 精确键不被当成前缀：「=A1」不应匹配 A1-11
    cfg2 = {"=A1": [{"type": "signed", "label": "只 A1"}]}
    monkeypatch.setattr(wer, "load_evidence_requirements_config", lambda: cfg2)
    assert wer.resolve_requirements_for_wp_code("A1-11") == []
    assert wer.resolve_requirements_for_wp_code("A1") == [{"type": "signed", "label": "只 A1"}]


def test_config_exact_keys_are_well_formed():
    raw = json.loads(CONFIG.read_bytes().decode("utf-8"))
    exact = [k for k in raw if k.startswith("=")]
    assert sorted(exact) == ["=A10", "=A16"]
    for k in exact:
        assert k[1:] and not k[1:].startswith("="), k
        assert k[1:] not in raw, f"{k} 与同名前缀键并存会让人读错"
    assert "=" in raw["_comment"]


@pytest.mark.parametrize(
    ("wp_code", "expected"),
    [("A16", "signed"), ("A17-7A", "signed"), ("A16-1", "evidence"), ("A1-11", "evidence"), ("A10-2", "evidence")],
)
def test_default_evidence_type_follows_signed_declaration(wp_code, expected):
    assert default_evidence_type(wp_code, native_type=None, native_prefix=None) == expected
