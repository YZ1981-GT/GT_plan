"""CSV 编码自适应探测（xlsx 是二进制不需要）。

职责（见 design.md §17 / Sprint 1 Task 7 / 需求 14）：

`detect_encoding(content: bytes) -> tuple[str, float]` 按以下顺序：

1. BOM 检测（置信度 1.0）
   - ``\\xef\\xbb\\xbf``                    → ``utf-8-sig``
   - ``\\xff\\xfe\\x00\\x00``               → ``utf-32-le``   （必须在 UTF-16 之前判，
     否则会被 ``\\xff\\xfe`` 前缀误识别为 UTF-16 LE）
   - ``\\x00\\x00\\xfe\\xff``               → ``utf-32-be``
   - ``\\xff\\xfe``                         → ``utf-16-le``
   - ``\\xfe\\xff``                         → ``utf-16-be``
2. 候选列表试解码前 4KB（置信度 0.85）
   ``utf-8`` → ``gb18030`` → ``gbk`` → ``big5`` → ``latin1``
   注意 ``gb18030`` 必须排在 ``gbk`` 之前（前者是后者的超集）；
   ``latin1`` 可以 decode 任何字节序列，放在末尾作为最后一个尝试。
3. ``chardet`` 第三方库兜底（置信度 > 0.7 时采信，归一化为小写）
4. 最终兜底 ``latin1``（不失败但可能乱码）→ 置信度 0.3

``decode_content(content: bytes) -> tuple[str | None, str, float]`` 是便捷函数，
先调用 ``detect_encoding`` 拿到编码，再执行 ``content.decode(encoding)``；如果最终
解码失败返回 ``(None, 'latin1', 0.0)``。

置信度 < 0.5 时前端 UI 应弹窗请用户确认编码。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["detect_encoding", "decode_content"]

# 探测用的前缀长度；64KB 避免在 GBK/GB18030 多字节字符边界截断
# （4KB 对大文件 GBK 不够——常在双字节中间切断导致 decode 失败，
#  而 latin1 永远成功从而误判）
_PROBE_BYTES = 65536

# chardet 兜底时的扫描窗口（越大越准但越慢）
_CHARDET_WINDOW = 65536

# chardet 对 CJK 编码的置信度阈值（降低到 0.3，因为 chardet 对 GBK/GB18030
# 短文本常给出 0.3-0.5 的置信度但结果仍然正确）
_CHARDET_CJK_THRESHOLD = 0.3
_CHARDET_OTHER_THRESHOLD = 0.7

# CJK 编码名称集合（用于判断是否降低 chardet 阈值）
_CJK_ENCODINGS = frozenset({
    "gb2312", "gbk", "gb18030", "big5", "euc-jp", "shift_jis",
    "euc-kr", "iso-2022-jp", "hz-gb-2312",
})

# 候选编码试解码顺序；gb18030 是 gbk 的超集，必须排在 gbk 之前
# 注意：latin1 不在此列表中（它能 decode 任何字节序列，会掩盖真实编码）
# latin1 仅作为最终兜底在所有其他方法失败后使用
_CSV_ENCODING_CANDIDATES: tuple[str, ...] = (
    "utf-8",
    "gb18030",
    "gbk",
    "big5",
)


def detect_encoding(content: bytes) -> tuple[str, float]:
    """探测 ``content`` 的文本编码，返回 ``(encoding_name, confidence_0_to_1)``。

    绝不抛异常：失败时兜底 ``("latin1", 0.3)``。
    """

    # 1. BOM — 100% 置信度
    # 注意 UTF-32 要在 UTF-16 之前判，否则 \xff\xfe\x00\x00 会被识别为 UTF-16 LE
    if content.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le", 1.0
    if content.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be", 1.0
    if content.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", 1.0
    if content.startswith(b"\xff\xfe"):
        return "utf-16-le", 1.0
    if content.startswith(b"\xfe\xff"):
        return "utf-16-be", 1.0

    # 2. 候选列表逐个试解码前 4KB
    probe = content[:_PROBE_BYTES]
    for enc in _CSV_ENCODING_CANDIDATES:
        try:
            probe.decode(enc)
        except UnicodeDecodeError:
            continue
        else:
            return enc, 0.85

    # 3. chardet 兜底（装了才用；没装不报错）
    try:  # pragma: no cover - 取决于 chardet 是否安装
        import chardet  # type: ignore
    except ImportError:
        chardet = None  # type: ignore[assignment]

    if chardet is not None:
        try:
            result = chardet.detect(content[:_CHARDET_WINDOW]) or {}
        except Exception:  # noqa: BLE001 - chardet 内部异常不应阻塞
            logger.debug("chardet.detect raised, falling back to latin1", exc_info=True)
            result = {}
        guessed = result.get("encoding")
        confidence = result.get("confidence") or 0.0
        if guessed:
            normalized_guess = guessed.lower()
            # CJK 编码用更低的阈值（chardet 对 GBK 短文本常给 0.3-0.5 但仍正确）
            threshold = (
                _CHARDET_CJK_THRESHOLD
                if normalized_guess in _CJK_ENCODINGS
                else _CHARDET_OTHER_THRESHOLD
            )
            if confidence >= threshold:
                return normalized_guess, float(confidence)

    # 4. 最终兜底：latin1 永远不会 decode 失败，但可能乱码
    return "latin1", 0.3


def decode_content(content: bytes) -> tuple[str | None, str, float]:
    """用探测到的编码解码 ``content``，返回 ``(text, encoding, confidence)``。

    - 正常：``(decoded_str, encoding, confidence)``
    - 所有尝试都失败：``(None, "latin1", 0.0)``

    调用方可结合 ``confidence`` 决定是否要求用户确认；置信度 < 0.5 时建议给前端
    附加 ``HEADER_ROW_AMBIGUOUS`` 风格的 warning。
    """

    encoding, confidence = detect_encoding(content)
    try:
        text = content.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        # 理论上不会到这里（latin1 兜底不会失败），但保险起见再做一次
        # latin1 终极尝试；失败则返回 None 让调用方走失败路径
        try:
            return content.decode("latin1"), "latin1", 0.0
        except UnicodeDecodeError:
            return None, "latin1", 0.0
    return text, encoding, confidence
