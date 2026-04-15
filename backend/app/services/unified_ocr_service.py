"""统一OCR服务层 — PaddleOCR(精度) + Tesseract(速度) + MinerU(兜底)

提供统一OCR接口，根据文件类型自动选择最优引擎：
- 发票/合同/回函 → PaddleOCR（精度优先）
- 通用文档 → Tesseract（速度优先）
- PaddleOCR/Tesseract 失败 → MinerU（兜底，复杂文档解析）
- 支持延迟初始化，按需加载引擎（PaddleOCR ~500MB）
- 引擎不可用时自动回退到另一引擎
"""

from __future__ import annotations

import asyncio
import logging
import re
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class OCREngine(str, Enum):
    PADDLE = "paddle"
    TESSERACT = "tesseract"
    MINERU = "mineru"
    AUTO = "auto"


class UnifiedOCRService:
    """统一OCR服务层 — 整合PaddleOCR、Tesseract和MinerU"""

    def __init__(self):
        from app.core.config import settings

        self._paddle = None  # lazy init
        self._tesseract = None  # lazy init
        self._mineru_service = None  # lazy init
        self._paddle_available: bool | None = (
            None if getattr(settings, "OCR_PADDLE_ENABLED", True) else False
        )
        self._tesseract_available: bool | None = (
            None if getattr(settings, "OCR_TESSERACT_ENABLED", True) else False
        )
        self._mineru_available: bool | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def recognize(
        self,
        image_path: str,
        mode: OCREngine = OCREngine.AUTO,
    ) -> dict:
        """统一OCR接口

        Returns:
            {"text": "...", "engine": "paddle|tesseract|mineru", "regions": [...]}
        """
        selected = await self._select_engine(image_path, mode)

        if selected == OCREngine.PADDLE:
            try:
                return await self._paddle_recognize(image_path)
            except Exception as exc:
                logger.warning("PaddleOCR failed, trying Tesseract fallback: %s", exc)
                if self._check_tesseract_available():
                    try:
                        return await self._tesseract_recognize(image_path)
                    except Exception as exc2:
                        logger.warning("Tesseract also failed, trying MinerU fallback: %s", exc2)
                        return await self._mineru_fallback(image_path)
                return await self._mineru_fallback(image_path)
        elif selected == OCREngine.TESSERACT:
            try:
                return await self._tesseract_recognize(image_path)
            except Exception as exc:
                logger.warning("Tesseract failed, trying PaddleOCR fallback: %s", exc)
                if self._check_paddle_available():
                    try:
                        return await self._paddle_recognize(image_path)
                    except Exception as exc2:
                        logger.warning("PaddleOCR also failed, trying MinerU fallback: %s", exc2)
                        return await self._mineru_fallback(image_path)
                return await self._mineru_fallback(image_path)
        elif selected == OCREngine.MINERU:
            return await self._mineru_fallback(image_path)
        else:  # AUTO
            # Try PaddleOCR first
            try:
                return await self._paddle_recognize(image_path)
            except Exception as exc:
                logger.warning("PaddleOCR failed, trying Tesseract: %s", exc)
                # Try Tesseract
                try:
                    return await self._tesseract_recognize(image_path)
                except Exception as exc2:
                    logger.warning("Tesseract also failed, trying MinerU: %s", exc2)
                    return await self._mineru_fallback(image_path)

    async def health_check(self) -> dict:
        """OCR引擎健康检查"""
        paddle_ok = self._check_paddle_available()
        tesseract_ok = self._check_tesseract_available()
        mineru_ok = await self._check_mineru_available()

        return {
            "status": "healthy" if (paddle_ok or tesseract_ok or mineru_ok) else "unhealthy",
            "engines": {
                "paddle": {"available": paddle_ok},
                "tesseract": {"available": tesseract_ok},
                "mineru": {"available": mineru_ok},
            },
            "default_engine": (
                "paddle" if paddle_ok else "tesseract" if tesseract_ok else "mineru" if mineru_ok else None
            ),
        }

    # ------------------------------------------------------------------
    # Engine selection
    # ------------------------------------------------------------------

    # Filename patterns that benefit from PaddleOCR (structured docs)
    _STRUCTURED_PATTERNS = [
        r"发票|invoice|receipt|vat",
        r"合同|contract|agreement",
        r"回函|confirmation|reply",
        r"银行|bank|statement|对账单",
        r"凭证|voucher|记账",
    ]

    async def _select_engine(
        self, image_path: str, mode: OCREngine
    ) -> OCREngine:
        """Auto-select: 发票/合同/回函 → PaddleOCR, 通用文档 → Tesseract"""
        if mode != OCREngine.AUTO:
            # User forced a specific engine — honour it if available
            if mode == OCREngine.PADDLE and self._check_paddle_available():
                return OCREngine.PADDLE
            if mode == OCREngine.TESSERACT and self._check_tesseract_available():
                return OCREngine.TESSERACT
            # Requested engine unavailable — fall through to auto logic

        file_name = Path(image_path).name.lower()

        for pattern in self._STRUCTURED_PATTERNS:
            if re.search(pattern, file_name):
                if self._check_paddle_available():
                    return OCREngine.PADDLE
                break  # pattern matched but paddle unavailable

        # General document → Tesseract (speed)
        if self._check_tesseract_available():
            return OCREngine.TESSERACT

        # Last resort
        if self._check_paddle_available():
            return OCREngine.PADDLE

        raise RuntimeError("没有可用的OCR引擎")

    # ------------------------------------------------------------------
    # Engine availability checks (lazy)
    # ------------------------------------------------------------------

    def _check_paddle_available(self) -> bool:
        if self._paddle_available is not None:
            return self._paddle_available
        try:
            from paddleocr import PaddleOCR  # noqa: F401

            self._paddle_available = True
        except Exception:
            self._paddle_available = False
        return self._paddle_available

    def _check_tesseract_available(self) -> bool:
        if self._tesseract_available is not None:
            return self._tesseract_available
        try:
            import pytesseract  # noqa: F401

            self._tesseract_available = True
        except Exception:
            self._tesseract_available = False
        return self._tesseract_available

    async def _check_mineru_available(self) -> bool:
        if self._mineru_available is not None:
            return self._mineru_available
        try:
            from app.services.mineru_service import MinerUService

            self._mineru_service = MinerUService()
            self._mineru_available = await self._mineru_service.is_available()
        except Exception:
            self._mineru_available = False
        return self._mineru_available

    # ------------------------------------------------------------------
    # Engine-specific recognition
    # ------------------------------------------------------------------

    def _init_paddle(self):
        """Lazy-init PaddleOCR (~500MB, only load when needed)"""
        if self._paddle is None:
            try:
                from paddleocr import PaddleOCR

                self._paddle = PaddleOCR(
                    use_angle_cls=True, lang="ch", use_gpu=False, show_log=False
                )
            except Exception as exc:
                logger.warning("PaddleOCR init failed: %s", exc)
                self._paddle_available = False
                raise
        return self._paddle

    def _init_tesseract(self):
        """Lazy-init Tesseract"""
        if self._tesseract is None:
            try:
                import pytesseract

                self._tesseract = pytesseract
            except Exception as exc:
                logger.warning("Tesseract init failed: %s", exc)
                self._tesseract_available = False
                raise
        return self._tesseract

    async def _paddle_recognize(self, image_path: str) -> dict:
        paddle = self._init_paddle()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: paddle.ocr(image_path, cls=True)
        )

        text_lines: list[str] = []
        regions: list[dict] = []
        if result:
            for page in result:
                if not page:
                    continue
                for item in page:
                    box, (text, confidence) = item
                    text_lines.append(text)
                    regions.append(
                        {"text": text, "box": box, "confidence": confidence}
                    )

        return {
            "text": "\n".join(text_lines),
            "engine": "paddle",
            "regions": regions,
        }

    async def _tesseract_recognize(self, image_path: str) -> dict:
        tess = self._init_tesseract()
        from PIL import Image

        loop = asyncio.get_running_loop()
        image = await loop.run_in_executor(None, Image.open, image_path)
        text = await loop.run_in_executor(
            None, lambda: tess.image_to_string(image, lang="chi_sim+eng")
        )

        return {
            "text": text.strip() if text else "",
            "engine": "tesseract",
            "regions": [],
        }

    async def _mineru_fallback(self, image_path: str) -> dict:
        """MinerU 兜底方案 - 用于复杂文档解析"""
        if not await self._check_mineru_available():
            raise RuntimeError("所有OCR引擎均不可用（PaddleOCR、Tesseract、MinerU）")

        try:
            return await self._mineru_service.recognize_for_ocr(image_path)
        except Exception as exc:
            logger.error("MinerU fallback failed: %s", exc)
            raise RuntimeError(f"所有OCR引擎均失败: {exc}")
