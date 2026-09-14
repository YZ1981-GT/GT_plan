"""MarkItDown 文档转 Markdown 服务

本地部署的纯 Python 文档解析层，把多种格式（PDF/Word/Excel/PPT/HTML/CSV/JSON/EPub/图片）
统一转成 Markdown 文本，给知识库 RAG 索引和 doc-level AI chat 提供干净输入。

设计要点：
- **本地优先**：默认 enable_plugins=False、不传 llm_client、不调 Azure 端点，纯本地解析。
- **降级链路**：markitdown 不可用或抛错时返回 None，调用方走旧路径（MinerU OCR / PyPDF2 / python-docx）。
- **延迟初始化**：MarkItDown 实例首次使用时才构造，避免后端启动时加载 magika/onnxruntime 模型。
- **流式接口**：用 convert_stream(BytesIO, file_extension=...) 而非 convert(path)，安全策略最窄
  （不允许 markitdown 自行 fetch 远端 URI）。

支持扩展名（一致使用 markitdown[all] 内置 converter）：
  .pdf .docx .doc .xlsx .xls .pptx .ppt .html .htm .csv .json .xml .epub .md .txt
  .zip（迭代内容） .png .jpg .jpeg（EXIF + 可选 OCR） .wav .mp3（需 audio-transcription）

不接管：扫描件 PDF（无文本层）→ 仍走 MinerU OCR；Excel 模板结构提取 → 仍走 openpyxl。
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# 扩展名白名单：markitdown 能直接处理且优于现有 fallback 的格式
# 不含 .png/.jpg（需 LLM vision 才有意义，纯 EXIF 无价值）
# 不含 .wav/.mp3（需要额外 audio-transcription 配置 + 时间长）
SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".epub",
    ".md",
    ".txt",
    ".rtf",
})

# 输出长度上限（与现有 _extract_text_with_ocr 路径一致，便于切片入向量库）
MAX_OUTPUT_CHARS: Final[int] = 50_000


class MarkItDownService:
    """统一文档→Markdown 转换器（本地纯 Python 路径）"""

    _instance: "MarkItDownService | None" = None

    def __init__(self) -> None:
        self._md = None  # 延迟初始化的 MarkItDown 实例
        self._init_failed = False  # 初始化失败标志，避免重复尝试
        self._init_error: str | None = None

    @classmethod
    def get_instance(cls) -> "MarkItDownService":
        """单例入口，避免重复加载 magika/onnxruntime 模型"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_available(self) -> bool:
        """检查 markitdown 是否可用（懒加载首次调用时初始化）"""
        if self._init_failed:
            return False
        if self._md is not None:
            return True
        try:
            from markitdown import MarkItDown

            # 本地部署模式：禁用插件，不传 llm_client，不调远端
            self._md = MarkItDown(enable_plugins=False)
            return True
        except Exception as exc:
            self._init_failed = True
            self._init_error = str(exc)
            logger.warning("[MarkItDown] init failed: %s", exc)
            return False

    @staticmethod
    def is_supported(filename: str) -> bool:
        """文件名扩展名是否在白名单"""
        if not filename:
            return False
        ext = Path(filename).suffix.lower()
        return ext in SUPPORTED_EXTENSIONS

    def convert_bytes(
        self,
        content: bytes,
        filename: str,
        max_chars: int = MAX_OUTPUT_CHARS,
    ) -> str | None:
        """把字节流转 Markdown 文本

        Args:
            content: 文件字节内容
            filename: 原始文件名（用于推断扩展名）
            max_chars: 输出截断长度

        Returns:
            Markdown 文本（已 strip 并截断），失败返回 None
        """
        if not content:
            return None
        if not self.is_supported(filename):
            return None
        if not self.is_available():
            return None

        ext = Path(filename).suffix.lower()
        try:
            stream = io.BytesIO(content)
            # convert_stream 是 markitdown 提供的最窄安全接口：
            # 不会触发任何远端 fetch，仅在内存中处理字节
            result = self._md.convert_stream(stream, file_extension=ext)
            text = (result.text_content or "").strip()
            if not text:
                logger.info("[MarkItDown] empty output for %s", filename)
                return None
            if len(text) > max_chars:
                logger.info(
                    "[MarkItDown] truncated %d→%d chars for %s",
                    len(text),
                    max_chars,
                    filename,
                )
                text = text[:max_chars]
            return text
        except Exception as exc:
            logger.warning("[MarkItDown] convert failed for %s: %s", filename, exc)
            return None


def convert_bytes_to_markdown(
    content: bytes,
    filename: str,
    max_chars: int = MAX_OUTPUT_CHARS,
) -> str | None:
    """便捷函数：单例调用，调用方无需关心实例管理"""
    return MarkItDownService.get_instance().convert_bytes(
        content, filename, max_chars=max_chars
    )
