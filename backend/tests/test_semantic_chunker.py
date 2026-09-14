"""
PBT P1 (round-trip), P11 (size bounds), performance test for SemanticChunker.

Validates: Requirements 4 (Semantic Chunking)
"""

from __future__ import annotations

import time

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.semantic_chunker import semantic_chunk, Chunk


# ─── PBT P1: Round-trip property ─────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters="\n\t 。！？",
        ),
        min_size=1,
        max_size=2000,
    )
)
def test_round_trip_chunking(text: str):
    """
    **Validates: Requirements 4.5**

    PBT P1: chunk → concat(remove overlaps) = original.
    Chunking then concatenating chunks in order (removing overlap regions
    from each chunk after the first) produces output identical to original input.
    """
    assume(text.strip())  # skip empty-ish strings

    chunks = semantic_chunk(text)
    assert len(chunks) > 0

    # Reconstruct: first chunk full, subsequent chunks skip overlap
    reconstructed_parts: list[str] = []
    for chunk in chunks:
        if chunk.chunk_index == 0:
            reconstructed_parts.append(chunk.text)
        else:
            # Remove overlap prefix
            reconstructed_parts.append(chunk.text[chunk.overlap_start:])

    reconstructed = "".join(reconstructed_parts)
    assert reconstructed == text, (
        f"Round-trip failed.\n"
        f"Original length: {len(text)}\n"
        f"Reconstructed length: {len(reconstructed)}\n"
        f"Chunks: {len(chunks)}"
    )


# ─── PBT P11: Chunk size bounds ──────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters="\n\t 。！？",
        ),
        min_size=1,
        max_size=3000,
    )
)
def test_chunk_size_bounds(text: str):
    """
    **Validates: Requirements 4.2**

    PBT P11: For all chunks produced by semantic_chunk(),
    len(chunk.text) shall be in [1, 800] characters,
    EXCEPT when the entire input is < 300 chars (single chunk = full input).
    """
    assume(text.strip())

    chunks = semantic_chunk(text)
    assert len(chunks) > 0

    if len(text) < 300:
        # Single chunk containing entire input
        assert len(chunks) == 1
        assert chunks[0].text == text
    else:
        for chunk in chunks:
            # Each chunk text must be non-empty
            assert len(chunk.text) >= 1, f"Chunk {chunk.chunk_index} is empty"
            # Size upper bound (800 + overlap of up to 80 = 880 max with overlap)
            assert len(chunk.text) <= 880, (
                f"Chunk {chunk.chunk_index} exceeds size bound: "
                f"{len(chunk.text)} chars (max 880 with overlap)"
            )


# ─── Unit Tests: Metadata ────────────────────────────────────────────────────


def test_chunk_metadata_total_chunks():
    """Each chunk's total_chunks equals the actual number of chunks produced."""
    text = "第一条 合同约定。" * 50 + "\n\n" + "第二条 违约责任。" * 50
    chunks = semantic_chunk(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.total_chunks == len(chunks)


def test_chunk_index_sequential():
    """chunk_index values are 0-based and sequential."""
    text = "审计准则要求对重大错报风险进行评估。" * 100
    chunks = semantic_chunk(text)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_short_text_single_chunk():
    """Text shorter than min_size produces exactly one chunk."""
    text = "短文本测试"
    chunks = semantic_chunk(text)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].chunk_index == 0
    assert chunks[0].total_chunks == 1
    assert chunks[0].overlap_start == 0


def test_empty_text_no_chunks():
    """Empty string produces no chunks."""
    chunks = semantic_chunk("")
    assert chunks == []


def test_article_marker_starts_new_chunk():
    """Article markers (第X条) start a new chunk."""
    text = "前言部分。" * 60 + "\n\n第一条 总则内容。" * 60
    chunks = semantic_chunk(text)
    # Find the chunk that starts with 第一条 (after overlap)
    found = False
    for chunk in chunks:
        content_after_overlap = chunk.text[chunk.overlap_start:]
        if content_after_overlap.startswith("第一条"):
            found = True
            break
    assert found, "Article marker should start a new chunk boundary"


# ─── Performance Test ─────────────────────────────────────────────────────────


def test_chunking_performance_200k_chars():
    """
    **Validates: Requirements 4.7**

    Chunking shall complete within 2 seconds for documents up to 200,000 characters.
    """
    # Generate a 200k char document
    paragraph = "审计准则规定审计师应当对财务报表整体是否不存在由于舞弊或错误导致的重大错报获取合理保证。" * 10
    # Need many more paragraphs to reach 200k chars
    text = ("\n\n".join([paragraph] * 500))[:200_000]
    assert len(text) >= 195_000  # at least close to 200k

    start = time.perf_counter()
    chunks = semantic_chunk(text)
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, f"Chunking took {elapsed:.2f}s, exceeds 2s limit"
    assert len(chunks) > 0
