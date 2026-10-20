"""统一OCR服务层 — PaddleOCR(精度) + Tesseract(速度) + MinerU(兜底)

提供统一OCR接口，根据文件类型自动选择最优引擎：
- 发票/合同/回函 → PaddleOCR（精度优先）
- 通用文档 → Tesseract（速度优先）
- PaddleOCR/Tesseract 失败 → MinerU（兜底，复杂文档解析）
- 支持延迟初始化，按需加载引擎（PaddleOCR ~500MB）
- 引擎不可用时自动回退到另一引擎

v2: OCR 服务化 — 配置了 OCR_SERVICE_URL 时本机引擎改走独立 OCR 容器，降低 web worker 内存占用。
v3（V197）: 本机优先、服务器兜底 —— 按能力槽在已启用模型中先试本机，再试远程 PaddleX。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from enum import Enum
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# OCR 服务 URL（环境变量配置，为空则走 in-process fallback）
OCR_SERVICE_URL = os.environ.get("OCR_SERVICE_URL", "").rstrip("/")
# HTTP 超时配置
OCR_HTTP_TIMEOUT = float(os.environ.get("OCR_HTTP_TIMEOUT", "30"))


class OCREngine(str, Enum):
    PADDLE = "paddle"
    TESSERACT = "tesseract"
    MINERU = "mineru"
    LAYOUT_PARSING = "layout_parsing"
    AUTO = "auto"


class OCRServiceUnavailableError(RuntimeError):
    """OCR 远程服务不可达（HTTP 超时/连接错误）→ 调用方应返回 503

    ``kinds``：各候选失败的类别（与 ``LLMRuntimeError.kind`` 同一口径）。全是 ``request``
    说明是文件本身的问题（过大 / 格式不被接受），换时间重试也没用；后台任务据此决定是否重试。
    """

    def __init__(self, message: str = "", *, kinds: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.kinds = kinds


#: 只有这两类失败说明候选本身不可用，才让它进入全局冷却（spec dsh-kb-ocr-local-first-routing
#: ADR-DKR-006）：文件过大 / 格式被拒（request）、读超时（timeout）是这一份文件的问题，冷却会让
#: 一份坏 PDF 把服务器 OCR 对所有人停 30 秒。
_COOLING_KINDS = frozenset({"unavailable", "config"})


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
        """统一OCR接口：本机优先、服务器兜底（ADR-ROUTE-009）。

        候选按能力槽（文字识别 / 版面解析）取已启用模型，本机在前：本机行 = 进程内引擎链
        （PaddleOCR / Tesseract / MinerU）或旧 ``OCR_SERVICE_URL`` 容器，环回 PaddleX 也算本机；
        服务器行 = 远程 PaddleX。没有启用行时文字识别走本机进程内引擎（旧行为），
        版面解析报「未配置」。OCR 幂等，前序候选任何失败都换下一个；最后一个失败才报错。
        显式点名 ``TESSERACT`` / ``MINERU`` 时只走本机引擎。

        Returns:
            {"text": "...", "engine": "...", "regions": [...], "route": {...}}

        Raises:
            OCRServiceUnavailableError: 全部候选不可用（逐个列出原因）
        """
        if mode in {OCREngine.TESSERACT, OCREngine.MINERU}:
            return await self._local_recognize(image_path, mode)

        from app.services.llm_route import (
            cooling_notes,
            mark_available,
            mark_unavailable,
            plan_attempts,
        )
        from app.services.remote_ocr_runtime import (
            RemoteOCRRuntimeError,
            recognize_remote_file,
            resolve_ocr_route,
        )

        capability = "layout_parsing" if mode == OCREngine.LAYOUT_PARSING else "ocr"
        try:
            route = await resolve_ocr_route(capability)
        except RemoteOCRRuntimeError as exc:
            raise OCRServiceUnavailableError(str(exc)) from exc
        if not route:
            raise OCRServiceUnavailableError("未配置已启用的版面解析模型")

        planned = plan_attempts(route)
        failures: list[tuple[str, str, str]] = []
        for candidate in planned:
            try:
                if candidate.local_engine:
                    result = await self._local_recognize(image_path, mode)
                elif candidate.config is None:
                    raise candidate.error or RemoteOCRRuntimeError("invalid_ocr_config", "OCR 配置无效")
                else:
                    result = await recognize_remote_file(candidate.config, image_path)
            except FileNotFoundError:
                raise  # 文件本身不存在：换候选也没用
            except Exception as exc:  # noqa: BLE001 — OCR 幂等，任何失败都换下一个候选
                reason = str(exc) or type(exc).__name__
                kind = str(getattr(exc, "kind", "unavailable"))
                if (
                    candidate.config is not None
                    and candidate.config.is_remote
                    and kind in _COOLING_KINDS
                ):
                    mark_unavailable(candidate.identity, reason)
                failures.append((candidate.label, reason, kind))
                logger.warning("OCR 候选失败 %s：%s", candidate.label, reason)
                continue
            if candidate.config is not None and candidate.config.is_remote:
                mark_available(candidate.identity)
            notes = [f"{label}：{reason}" for label, reason, _ in failures]
            notes.extend(cooling_notes(route, planned))
            result["route"] = {
                "deployment": candidate.deployment,
                "model_name": candidate.model_name,
                "fallback_used": candidate is not route[0],
                "attempts": notes,
            }
            return result
        skipped = cooling_notes(route, planned)
        kinds = tuple(kind for _, _, kind in failures)
        if len(failures) == 1 and not skipped:
            raise OCRServiceUnavailableError(failures[0][1], kinds=kinds)
        raise OCRServiceUnavailableError(
            "；".join([f"{label}：{reason}" for label, reason, _ in failures] + skipped)
            or "没有可用的 OCR 引擎",
            kinds=kinds,
        )

    async def _local_recognize(
        self, image_path: str, mode: OCREngine = OCREngine.AUTO
    ) -> dict:
        """本机引擎：旧固定 OCR 容器优先，否则进程内引擎链。"""
        if OCR_SERVICE_URL:
            try:
                return await self._http_recognize(image_path, mode)
            except OCRServiceUnavailableError:
                raise  # 不 fallback — 保护 web worker 内存
            except Exception as exc:
                logger.warning(
                    "OCR HTTP call failed unexpectedly: %s, returning 503", exc
                )
                raise OCRServiceUnavailableError(
                    f"OCR 服务异常: {exc}"
                ) from exc

        # Fallback: in-process OCR（仅在未配置 OCR_SERVICE_URL 时使用）
        return await self._in_process_recognize(image_path, mode)

    async def _http_recognize(
        self, image_path: str, mode: OCREngine = OCREngine.AUTO
    ) -> dict:
        """HTTP 调用 OCR 服务容器

        POST /recognize with file upload
        """
        engine_param = mode.value if mode != OCREngine.AUTO else "auto"
        file_name = Path(image_path).name

        async with httpx.AsyncClient(timeout=OCR_HTTP_TIMEOUT) as client:
            try:
                with open(image_path, "rb") as f:
                    resp = await client.post(
                        f"{OCR_SERVICE_URL}/recognize",
                        params={"engine": engine_param},
                        files={"file": (file_name, f)},
                    )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.warning(
                    "OCR service unreachable (url=%s): %s",
                    OCR_SERVICE_URL, exc,
                )
                raise OCRServiceUnavailableError(
                    f"OCR 服务超时/连接失败: {exc}"
                ) from exc

        if resp.status_code == 200:
            return resp.json()
        else:
            logger.warning(
                "OCR service returned HTTP %d: %s",
                resp.status_code, resp.text[:200],
            )
            raise OCRServiceUnavailableError(
                f"OCR 服务返回 HTTP {resp.status_code}"
            )

    async def _in_process_recognize(
        self, image_path: str, mode: OCREngine = OCREngine.AUTO
    ) -> dict:
        """In-process OCR fallback（仅在未配置远程服务时使用）

        注意：此路径会加载 PaddleOCR 模型（~500MB），不应在生产 web worker 中使用。
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

    async def local_engine_status(self) -> dict:
        """本机 OCR 引擎能否用（只查安装与配置，不加载模型、不识别）。

        路由状态与启用本机 OCR 行的校验共用这一份判定。
        """
        if OCR_SERVICE_URL:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(3.0, connect=2.0), mounts={}, trust_env=False
                ) as client:
                    response = await client.get(f"{OCR_SERVICE_URL}/health")
                ok = response.status_code == 200
                reason = "本机 OCR 容器可用" if ok else f"本机 OCR 容器返回 HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                ok, reason = False, f"本机 OCR 容器不可达（{type(exc).__name__}）"
            return {"available": ok, "engines": {"container": ok}, "reason": reason}
        engines = {
            "paddle": self._check_paddle_available(),
            "tesseract": self._check_tesseract_available(),
            "mineru": (
                await self._check_mineru_available()
                if getattr(settings, "MINERU_ENABLED", False)
                else False
            ),
        }
        names = {"paddle": "PaddleOCR", "tesseract": "Tesseract", "mineru": "MinerU"}
        ready = [names[key] for key, ok in engines.items() if ok]
        if ready:
            return {"available": True, "engines": engines, "reason": "可用：" + " / ".join(ready)}
        return {
            "available": False,
            "engines": engines,
            "reason": "本机未安装 PaddleOCR / Tesseract，MinerU 未启用",
        }

    async def health_check(self) -> dict:
        """OCR引擎健康检查（禁用 MinerU 时不探测，避免拖慢 /api/ai/health）"""
        paddle_ok = self._check_paddle_available()
        tesseract_ok = self._check_tesseract_available()
        if getattr(settings, "MINERU_ENABLED", False):
            mineru_ok = await self._check_mineru_available()
        else:
            mineru_ok = False
            self._mineru_available = False

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
            if mode == OCREngine.MINERU and await self._check_mineru_available():
                return OCREngine.MINERU
            # layout_parsing 只能由上层远程 adapter 处理，不可伪降级成普通 OCR。
            if mode == OCREngine.LAYOUT_PARSING:
                raise RuntimeError("未配置可用的版面解析引擎")
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
        # Paddle / Tesseract 都不可用时 MinerU 仍是本机引擎（旧实现在这里直接抛错，MinerU 永远轮不到）
        if await self._check_mineru_available():
            return OCREngine.MINERU

        raise RuntimeError("没有可用的本机 OCR 引擎（PaddleOCR / Tesseract 未安装，MinerU 未启用）")

    # ------------------------------------------------------------------
    # Engine availability checks (lazy)
    # ------------------------------------------------------------------

    def _check_paddle_available(self) -> bool:
        if self._paddle_available is not None:
            return self._paddle_available
        # OCR 服务化后，web worker 不应加载 PaddleOCR 模型
        if OCR_SERVICE_URL:
            self._paddle_available = False
            return False
        try:
            from paddleocr import PaddleOCR  # noqa: F401

            self._paddle_available = True
        except Exception:
            self._paddle_available = False
        return self._paddle_available

    def _check_tesseract_available(self) -> bool:
        if self._tesseract_available is not None:
            return self._tesseract_available
        # OCR 服务化后，web worker 不应加载 tesseract
        if OCR_SERVICE_URL:
            self._tesseract_available = False
            return False
        try:
            import pytesseract

            # 只装 Python 包不装 tesseract 程序时，识别到 image_to_string 才报错 ⇒ 这里一并检查。
            cmd = str(getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract") or "tesseract")
            self._tesseract_available = bool(
                os.path.isfile(cmd) if os.path.isabs(cmd) else shutil.which(cmd)
            )
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
