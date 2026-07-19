"""
SemanticChunker: 语义分块器
将提取的文本按段落/句子边界切分为带重叠的语义片段。

设计要求:
- 段落边界分割 (双换行)
- 句子边界分割 (。！？)
- 条款标记检测 (第X条/CAS X/ISA X)
- 300-800 字符目标范围
- 80 字符重叠
- round-trip 属性: chunk→concat(remove overlaps) = original
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """语义分块"""

    text: str
    chunk_index: int
    total_chunks: int
    section_heading: str
    overlap_start: int  # 重叠区域长度（第一个 chunk 为 0）


# 条款标记正则
_ARTICLE_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百千零\d]+条|CAS\s*\d+|ISA\s*\d+|[（(]\d+[)）])",
    re.MULTILINE,
)

# 句子边界正则 (中文句号/感叹号/问号 + 后续空白或换行)
_SENTENCE_RE = re.compile(r"(?<=[。！？])\s*")

# 标题检测正则 (一、/ （一）/ # 格式)
_HEADING_RE = re.compile(
    r"^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|#+\s+).+",
    re.MULTILINE,
)


def semantic_chunk(
    text: str,
    min_size: int = 300,
    max_size: int = 800,
    overlap: int = 80,
) -> list[Chunk]:
    """
    语义分块：段落→句子→字符三级降级。

    保证 round-trip 属性:
      对每个 chunk[i] (i>0), chunk[i].text[:overlap_start] 是重叠区域,
      去掉后拼接即为原文。
    """
    if not text:
        return []

    # 短文本直接返回单 chunk
    if len(text) <= min_size:
        return [Chunk(text=text, chunk_index=0, total_chunks=1, section_heading="", overlap_start=0)]

    # Step 1: 找出所有分割点 (character positions in original text)
    split_points = _find_split_points(text, min_size, max_size)

    # Step 2: 按分割点切分原文为 raw chunks
    raw_chunks: list[str] = []
    prev = 0
    for sp in split_points:
        raw_chunks.append(text[prev:sp])
        prev = sp
    raw_chunks.append(text[prev:])

    # 过滤空 chunks
    raw_chunks = [c for c in raw_chunks if c]
    if not raw_chunks:
        return [Chunk(text=text, chunk_index=0, total_chunks=1, section_heading="", overlap_start=0)]

    # Step 3: 添加重叠
    chunks_with_overlap: list[tuple[str, int]] = [(raw_chunks[0], 0)]
    for i in range(1, len(raw_chunks)):
        prev_chunk = raw_chunks[i - 1]
        curr_chunk = raw_chunks[i]
        overlap_text = prev_chunk[-overlap:] if len(prev_chunk) >= overlap else prev_chunk
        actual_overlap = len(overlap_text)
        chunks_with_overlap.append((overlap_text + curr_chunk, actual_overlap))

    # Step 4: 填充 metadata
    total = len(chunks_with_overlap)
    result: list[Chunk] = []
    for i, (chunk_text, overlap_len) in enumerate(chunks_with_overlap):
        heading = _find_section_heading(text, chunk_text, overlap_len)
        result.append(
            Chunk(
                text=chunk_text,
                chunk_index=i,
                total_chunks=total,
                section_heading=heading,
                overlap_start=overlap_len,
            )
        )
    return result


def _find_split_points(text: str, min_size: int, max_size: int) -> list[int]:
    """
    找出文本中的最佳分割位置列表。
    保证每段长度在 [min_size, max_size] 范围内（尽量）。
    分割优先级: 条款标记 > 双换行 > 句子 > 硬切。
    """
    split_points: list[int] = []
    pos = 0
    text_len = len(text)

    while pos + max_size < text_len:
        # 搜索窗口: [pos+min_size, pos+max_size]
        window_start = pos + min_size
        window_end = min(pos + max_size, text_len)

        # 优先级1: 条款标记 (在窗口内找最靠前的)
        best = _find_article_split(text, window_start, window_end)
        if best is not None:
            split_points.append(best)
            pos = best
            continue

        # 优先级2: 双换行
        best = _find_paragraph_split(text, window_start, window_end)
        if best is not None:
            split_points.append(best)
            pos = best
            continue

        # 优先级3: 句子边界
        best = _find_sentence_split(text, window_start, window_end)
        if best is not None:
            split_points.append(best)
            pos = best
            continue

        # 优先级4: 硬切 at max_size
        split_points.append(pos + max_size)
        pos = pos + max_size

    return split_points


def _find_article_split(text: str, start: int, end: int) -> int | None:
    """在 [start, end) 范围内找条款标记的起始位置。"""
    segment = text[start:end]
    m = _ARTICLE_RE.search(segment)
    if m:
        return start + m.start()
    return None


def _find_paragraph_split(text: str, start: int, end: int) -> int | None:
    """在 [start, end) 范围内找双换行位置（取换行后的位置）。"""
    segment = text[start:end]
    # 找最后一个双换行（让前一段尽量长）
    idx = segment.rfind("\n\n")
    if idx >= 0:
        # 跳过换行符，分割点在换行后
        split_at = start + idx
        # 找到换行序列的末尾
        while split_at < end and text[split_at] == "\n":
            split_at += 1
        return split_at
    return None


def _find_sentence_split(text: str, start: int, end: int) -> int | None:
    """在 [start, end) 范围内找句子边界。"""
    segment = text[start:end]
    # 找最后一个句子结束标记
    matches = list(_SENTENCE_RE.finditer(segment))
    if matches:
        last_match = matches[-1]
        return start + last_match.end()
    return None


def _find_section_heading(full_text: str, chunk_text: str, overlap_len: int) -> str:
    """找到 chunk 之前最近的标题。"""
    # chunk 在原文中的近似位置
    content_start = chunk_text[overlap_len:overlap_len + 50] if overlap_len else chunk_text[:50]
    pos = full_text.find(content_start)
    if pos < 0:
        return ""

    # 在 pos 之前的文本中找最近标题
    preceding = full_text[:pos]
    matches = list(_HEADING_RE.finditer(preceding))
    if matches:
        return matches[-1].group(0).strip()
    return ""
