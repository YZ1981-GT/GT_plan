"""
Unit tests + PBT P2 (extraction idempotence) for ContentExtractor service.

Validates: Requirements 3 (Content Extraction)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.content_extractor import ContentExtractor, ExtractResult


# ─── Unit Tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_extension_returns_unsupported_format():
    """Unsupported file extension returns ExtractResult(None, 'unsupported_format', None)."""
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        f.write(b"some data")
        f.flush()
        result = await ContentExtractor.extract(f.name)

    assert result.content_text is None
    assert result.status == "unsupported_format"
    assert result.error is None


@pytest.mark.asyncio
async def test_txt_extraction_returns_content_correctly():
    """TXT extraction returns file content as-is (UTF-8)."""
    content = "这是一段测试文本。\n第二行内容。"
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        result = await ContentExtractor.extract(f.name)

    assert result.status == "extracted"
    assert result.error is None
    assert result.content_text == content


@pytest.mark.asyncio
async def test_md_extraction_returns_content_correctly():
    """MD extraction returns markdown content as-is (UTF-8)."""
    content = "# 标题\n\n## 二级标题\n\n- 列表项1\n- 列表项2"
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        result = await ContentExtractor.extract(f.name)

    assert result.status == "extracted"
    assert result.error is None
    assert result.content_text == content


@pytest.mark.asyncio
async def test_timeout_produces_extraction_failed_with_timeout_error():
    """Extraction timeout produces 'extraction_failed' status with 'timeout_60s' error."""
    # Create a txt file but mock the extractor to sleep longer than timeout
    content = "hello"
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        file_path = f.name

    # Monkey-patch the TXT extractor to simulate slow extraction
    import time

    def _slow_extractor(path: str) -> str:
        time.sleep(5)  # Sleep longer than our tiny timeout
        return Path(path).read_text("utf-8")

    original = ContentExtractor.EXTRACTORS[".txt"]
    ContentExtractor.EXTRACTORS[".txt"] = _slow_extractor
    try:
        # Use a very short timeout to trigger TimeoutError quickly
        result = await ContentExtractor.extract(file_path, timeout=1)
        assert result.content_text is None
        assert result.status == "extraction_failed"
        assert result.error == "timeout_60s"
    finally:
        ContentExtractor.EXTRACTORS[".txt"] = original


@pytest.mark.asyncio
async def test_corrupted_file_produces_extraction_failed():
    """Corrupted/unreadable file produces 'extraction_failed' status."""
    # Create a file with .txt extension but point to non-existent path
    result = await ContentExtractor.extract("/nonexistent/path/file.txt")

    assert result.content_text is None
    assert result.status == "extraction_failed"
    assert result.error is not None
    assert len(result.error) > 0


# ─── PBT P2: Extraction Idempotence ──────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    content=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters="\n\t ",
        ),
        min_size=1,
        max_size=500,
    )
)
@pytest.mark.asyncio
async def test_extraction_idempotence_txt(content: str):
    """
    **Validates: Requirements 3**

    PBT P2: Extracting the same file multiple times produces identical content_text.
    For TXT files, extracting N times must yield the same result each time.
    """
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        file_path = f.name

    result1 = await ContentExtractor.extract(file_path)
    result2 = await ContentExtractor.extract(file_path)

    # Both extractions must succeed
    assert result1.status == "extracted"
    assert result2.status == "extracted"

    # Content must be identical across extractions
    assert result1.content_text == result2.content_text

    # Clean up
    Path(file_path).unlink(missing_ok=True)
