"""C24 分录规则词表生成器测试。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.gen import gen_journal_entry_rules_ts as generator

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "backend" / "data" / "custom_query_presets.json"
OUTPUT_PATH = ROOT / "audit-platform" / "frontend" / "src" / "generated" / "journalEntryRules.ts"


def _load_source() -> dict[str, object]:
    document = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_generated_file_matches_rendered_source_without_timestamp():
    rendered = generator.render(_load_source())
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert on_disk == rendered
    assert "export const SPECIAL_EVENT_KEYWORDS" in rendered
    assert "export const VAGUE_KEYWORDS_DEFAULT" in rendered
    assert "generated_at" not in rendered
    assert re.search(r"\b20\d{2}-\d{2}-\d{2}\b", rendered) is None


def test_write_is_idempotent_and_check_detects_drift(tmp_path: Path, monkeypatch):
    source = tmp_path / "custom_query_presets.json"
    output = tmp_path / "journalEntryRules.ts"
    source.write_bytes(SOURCE_PATH.read_bytes())
    monkeypatch.setattr(generator, "SOURCE_PATH", source)
    monkeypatch.setattr(generator, "OUTPUT_PATH", output)

    assert generator.main(["--write"]) == 0
    first = output.read_bytes()
    assert generator.main(["--write"]) == 0
    assert output.read_bytes() == first
    assert generator.main(["--check"]) == 0

    output.write_bytes(first + b"// drift\n")
    assert generator.main(["--check"]) == 2
