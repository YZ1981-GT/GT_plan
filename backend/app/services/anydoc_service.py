"""anydoc 文档转 Markdown 服务

`@firecrawl/anydoc`（Rust + Node bindings，MIT）把 Word / PowerPoint / Excel /
OpenDocument / RTF / EPUB / CSV / 文本层 PDF 转成 GitHub-Flavored Markdown。

选它作为文本抽取主路径的理由（对比 markitdown）：
- **Rust 实现**，单文档通常单位数毫秒级，远快于 markitdown 的 Python 链路。
- **覆盖旧二进制格式** `.doc` / `.xls` / `.ppt`，审计场景大量存量客户文件是这些格式。
- **错误码分明**（Unsupported / Malformed / Encrypted / ResourceLimit / MissingPart / Io），
  尤其对扫描件 PDF 明确回 `PDF has no extractable text ... OCR is required`
  —— 上层据此**精准路由**到 MinerU OCR，而不是盲目往下试一遍降级链。
- **纯本地**：无 API key、无外部服务、不联网，符合「审计数据不出内网」。

不接管：
- HTML / JSON / XML / 图片 / 音频 → anydoc 不支持，交给 markitdown（若安装）。
- 扫描件 PDF（无文本层）→ 交给 MinerU OCR。
- Excel 模板结构提取 → 仍走 openpyxl（anydoc 只出 Markdown，丢单元格坐标）。

设计对齐 `markitdown_service.py`：单例 + 懒加载可用性探测 + 失败返 None，
使两者可在同一条降级链中互换位置而不改调用方。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# anydoc 支持的扩展名（源自其 README 的格式表）。
# 注意：anydoc 实际按内容标记探测格式，错标扩展名仍能转；此白名单只用于
# 避免对明显无关的文件（图片/音频）无谓启动子进程。
SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset({
    # Word
    ".doc", ".docx", ".docm",
    # PowerPoint
    ".ppt", ".pps", ".pot", ".pptx", ".pptm", ".ppsx", ".ppsm",
    # Excel
    ".xls", ".xlsx", ".xlsm", ".xlsb",
    # OpenDocument
    ".odt", ".ods", ".odp",
    # Other
    ".rtf", ".epub", ".csv", ".pdf",
})

# 输出长度上限，与 markitdown_service / _extract_text_with_ocr 口径一致
MAX_OUTPUT_CHARS: Final[int] = 50_000

# 子进程超时（anydoc 通常毫秒级，给足余量应对超大文档）
_TIMEOUT_SECONDS: Final[int] = 120

# anydoc 的错误码字面（见其 README 的 error.code 表）
_ERROR_CODES: Final[tuple[str, ...]] = (
    "Unsupported",
    "Malformed",
    "Encrypted",
    "ResourceLimit",
    "MissingPart",
    "Io",
)

# 判定「需要 OCR」的信号：anydoc 对图片型 PDF 的原话是
#   anydoc: unsupported input: PDF has no extractable text (Scanned, N pages): OCR is required
# 用两个独立子串共同判定，避免任一措辞微调即失效
_OCR_REQUIRED_MARKERS: Final[tuple[str, ...]] = ("no extractable text", "OCR is required")


@dataclass(frozen=True)
class AnydocResult:
    """一次转换的完整结果（含失败归因，供上层精准路由）"""

    text: str | None
    """转换出的 Markdown；失败为 None。"""

    ok: bool
    """是否成功产出非空 Markdown。"""

    error_code: str | None = None
    """anydoc 错误码（Unsupported / Encrypted / ...），无法归类时为 None。"""

    message: str = ""
    """原始诊断信息，便于日志与用户可见提示。"""

    needs_ocr: bool = False
    """True 表示这是扫描件/图片型 PDF，应路由到 OCR 引擎（MinerU）。"""

    permanent: bool = False
    """True 表示重试无意义（Encrypted / 不支持的格式），应记录后放弃。"""


class AnydocService:
    """anydoc CLI 封装（单例）"""

    _instance: "AnydocService | None" = None

    def __init__(self) -> None:
        self._exe: str | None = None
        self._probed = False
        self._version: str | None = None

    @classmethod
    def get_instance(cls) -> "AnydocService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # 可用性
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """anydoc CLI 是否可调用（首次调用时探测并缓存）

        探测方式是真实执行 `anydoc --version` 并要求 rc==0 —— 不是只看文件存在，
        因为 npm 包装脚本可能指向已被删除的 venv/exe。
        """
        if self._probed:
            return self._exe is not None

        self._probed = True
        exe = shutil.which("anydoc")
        if not exe:
            logger.info("[anydoc] CLI 未在 PATH 中，跳过该抽取路径")
            return False

        try:
            proc = subprocess.run(
                [exe, "--version"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                logger.warning(
                    "[anydoc] --version 返回 rc=%s，视为不可用", proc.returncode
                )
                return False
            self._version = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
            self._exe = exe
            logger.info("[anydoc] 可用，version=%s path=%s", self._version, exe)
            return True
        except Exception as exc:
            logger.warning("[anydoc] 可用性探测失败: %s", exc)
            return False

    @property
    def version(self) -> str | None:
        return self._version

    @staticmethod
    def is_supported(filename: str) -> bool:
        if not filename:
            return False
        return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS

    # ------------------------------------------------------------------
    # 转换
    # ------------------------------------------------------------------

    def convert_bytes_detailed(
        self,
        content: bytes,
        filename: str,
        max_chars: int = MAX_OUTPUT_CHARS,
    ) -> AnydocResult:
        """把字节流转 Markdown，返回含失败归因的完整结果。

        anydoc 是 CLI 且只接受文件路径，故内容先落临时文件；临时文件在
        finally 中删除，异常路径也不残留。
        """
        if not content:
            return AnydocResult(None, False, message="空内容")
        if not self.is_supported(filename):
            return AnydocResult(
                None, False, error_code="Unsupported",
                message=f"扩展名不在 anydoc 支持列表: {Path(filename).suffix}",
                permanent=True,
            )
        if not self.is_available():
            return AnydocResult(None, False, message="anydoc CLI 不可用")

        suffix = Path(filename).suffix.lower()
        tmp_dir = Path(tempfile.mkdtemp(prefix="anydoc_"))
        src = tmp_dir / f"input{suffix}"
        out = tmp_dir / "output.md"

        try:
            src.write_bytes(content)

            cmd = [self._exe or "anydoc", str(src), "-o", str(out)]
            # CSV 无内容签名，anydoc 要求显式声明格式
            if suffix == ".csv":
                cmd += ["--format", "csv"]

            # 强制子进程 UTF-8 输出：Windows 控制台默认代码页会把 CJK 变乱码
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
                env=env,
            )
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
            diag = (stderr or stdout).strip()

            if proc.returncode != 0 or not out.exists():
                return self._classify_failure(filename, diag)

            text = out.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                # rc=0 但无内容：按失败处理并如实标注，不返回空串冒充成功
                return AnydocResult(
                    None, False, error_code="Malformed",
                    message=f"anydoc 返回成功但产出为空: {filename}",
                )

            if len(text) > max_chars:
                logger.info(
                    "[anydoc] 截断 %d→%d chars: %s", len(text), max_chars, filename
                )
                text = text[:max_chars]

            return AnydocResult(text, True, message=f"anydoc {self._version}")

        except subprocess.TimeoutExpired:
            return AnydocResult(
                None, False, error_code="ResourceLimit",
                message=f"anydoc 转换超时（>{_TIMEOUT_SECONDS}s）: {filename}",
            )
        except Exception as exc:
            logger.warning("[anydoc] 转换异常 %s: %s", filename, exc)
            return AnydocResult(None, False, message=f"{type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _classify_failure(filename: str, diag: str) -> AnydocResult:
        """把 anydoc 的诊断输出归类为结构化失败结果。

        识别两类特殊情形：
        - 扫描件 PDF → needs_ocr=True，上层应路由到 MinerU 而非继续盲目降级
        - Encrypted / Unsupported → permanent=True，重试无意义，记录后放弃
        """
        code = next((c for c in _ERROR_CODES if c in diag), None)
        needs_ocr = all(m in diag for m in _OCR_REQUIRED_MARKERS)

        if needs_ocr:
            logger.info("[anydoc] %s 是扫描件，需 OCR: %s", filename, diag[:160])
            return AnydocResult(
                None, False, error_code=code or "Unsupported",
                message=diag, needs_ocr=True,
            )

        # Encrypted 与真正的格式不支持都是永久失败；"OCR is required" 已在上面分流
        permanent = code in ("Encrypted", "Unsupported")
        if permanent:
            logger.info("[anydoc] %s 永久失败(%s): %s", filename, code, diag[:160])
        else:
            logger.warning("[anydoc] %s 转换失败(%s): %s", filename, code, diag[:200])

        return AnydocResult(
            None, False, error_code=code, message=diag, permanent=permanent
        )

    # ------------------------------------------------------------------
    # 兼容接口
    # ------------------------------------------------------------------

    def convert_bytes(
        self,
        content: bytes,
        filename: str,
        max_chars: int = MAX_OUTPUT_CHARS,
    ) -> str | None:
        """与 markitdown_service.convert_bytes 同签名，便于在降级链中互换。"""
        return self.convert_bytes_detailed(content, filename, max_chars=max_chars).text


def convert_bytes_to_markdown(
    content: bytes,
    filename: str,
    max_chars: int = MAX_OUTPUT_CHARS,
) -> str | None:
    """便捷函数：单例调用。"""
    return AnydocService.get_instance().convert_bytes(
        content, filename, max_chars=max_chars
    )


def convert_bytes_detailed(
    content: bytes,
    filename: str,
    max_chars: int = MAX_OUTPUT_CHARS,
) -> AnydocResult:
    """便捷函数：需要失败归因（尤其 needs_ocr 路由）时用这个。"""
    return AnydocService.get_instance().convert_bytes_detailed(
        content, filename, max_chars=max_chars
    )
