"""OCR 独立 HTTP 服务 — PaddleOCR + Tesseract

API 规范:
  POST /recognize
    - Content-Type: multipart/form-data
    - Body: file (image/pdf)
    - Query: engine=auto|paddle|tesseract
    - Response: {"text": "...", "engine": "paddle", "regions": [...]}

  GET /health
    - Response: {"status": "healthy", "engines": {...}}
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OCR_PORT = int(os.environ.get("OCR_PORT", "9990"))
PADDLE_ENABLED = os.environ.get("OCR_PADDLE_ENABLED", "true").lower() == "true"
TESSERACT_ENABLED = os.environ.get("OCR_TESSERACT_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Lazy-loaded engines
# ---------------------------------------------------------------------------

_paddle_instance = None
_tesseract_module = None


def _get_paddle():
    global _paddle_instance
    if _paddle_instance is None and PADDLE_ENABLED:
        try:
            from paddleocr import PaddleOCR
            _paddle_instance = PaddleOCR(
                use_angle_cls=True, lang="ch", use_gpu=False, show_log=False
            )
            logger.info("PaddleOCR initialized successfully")
        except Exception as e:
            logger.warning("PaddleOCR init failed: %s", e)
    return _paddle_instance


def _get_tesseract():
    global _tesseract_module
    if _tesseract_module is None and TESSERACT_ENABLED:
        try:
            import pytesseract
            _tesseract_module = pytesseract
            logger.info("Tesseract initialized successfully")
        except Exception as e:
            logger.warning("Tesseract init failed: %s", e)
    return _tesseract_module


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """健康检查 — 返回引擎可用状态"""
    paddle_ok = _get_paddle() is not None
    tesseract_ok = _get_tesseract() is not None

    status = "healthy" if (paddle_ok or tesseract_ok) else "unhealthy"
    return jsonify({
        "status": status,
        "engines": {
            "paddle": {"available": paddle_ok},
            "tesseract": {"available": tesseract_ok},
        },
    }), 200 if status == "healthy" else 503


@app.route("/recognize", methods=["POST"])
def recognize():
    """OCR 识别接口

    接收图片/PDF 文件，返回识别结果。

    Request:
        - file: 上传文件 (multipart/form-data)
        - engine: auto|paddle|tesseract (query param, default=auto)

    Response:
        {
            "text": "识别出的文本",
            "engine": "paddle|tesseract",
            "regions": [{"text": "...", "box": [...], "confidence": 0.95}, ...]
        }
    """
    if "file" not in request.files:
        return jsonify({"error": "缺少文件参数 'file'"}), 400

    file = request.files["file"]
    engine = request.args.get("engine", "auto")

    # 保存到临时文件
    suffix = Path(file.filename or "image.png").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp)
        tmp_path = tmp.name

    try:
        result = _do_recognize(tmp_path, engine, file.filename or "")
        return jsonify(result), 200
    except Exception as e:
        logger.error("OCR recognition failed: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _do_recognize(image_path: str, engine: str, filename: str) -> dict:
    """执行 OCR 识别"""
    if engine == "paddle" or (engine == "auto" and PADDLE_ENABLED):
        paddle = _get_paddle()
        if paddle:
            return _paddle_recognize(paddle, image_path)

    if engine == "tesseract" or (engine == "auto" and TESSERACT_ENABLED):
        tess = _get_tesseract()
        if tess:
            return _tesseract_recognize(tess, image_path)

    # Last resort: try any available engine
    paddle = _get_paddle()
    if paddle:
        return _paddle_recognize(paddle, image_path)

    tess = _get_tesseract()
    if tess:
        return _tesseract_recognize(tess, image_path)

    raise RuntimeError("没有可用的 OCR 引擎")


def _paddle_recognize(paddle, image_path: str) -> dict:
    """PaddleOCR 识别"""
    result = paddle.ocr(image_path, cls=True)

    text_lines: list[str] = []
    regions: list[dict] = []

    if result:
        for page in result:
            if not page:
                continue
            for item in page:
                box, (text, confidence) = item
                text_lines.append(text)
                regions.append({
                    "text": text,
                    "box": box,
                    "confidence": confidence,
                })

    return {
        "text": "\n".join(text_lines),
        "engine": "paddle",
        "regions": regions,
    }


def _tesseract_recognize(tess, image_path: str) -> dict:
    """Tesseract 识别"""
    from PIL import Image
    image = Image.open(image_path)
    text = tess.image_to_string(image, lang="chi_sim+eng")

    return {
        "text": text.strip() if text else "",
        "engine": "tesseract",
        "regions": [],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting OCR service on port %d", OCR_PORT)
    app.run(host="0.0.0.0", port=OCR_PORT)
