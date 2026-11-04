"""Word → PDF：交给 OnlyOffice 文档服务器转换（报告正文网页预览用，版式与 Word 一致）。

流程：docx 写进缓存目录 → 生成带 HMAC 签名、2 分钟有效的取文件地址 → 调 OnlyOffice
``ConvertService.ashx``（同步模式，请求头带 JWT）→ OnlyOffice 按地址回来取文件、转好后给出结果地址 →
后端从 ``ONLYOFFICE_URL`` 取回 PDF。同一份内容（``cache_key``）转过一次就直接用缓存。

版式取决于 OnlyOffice 容器里有没有文档用到的字体（仿宋 / 黑体 / Arial Narrow 等，镜像只带开源字体）。
转出的 PDF 缺 ``required_fonts`` 里的字体时结果不缓存，``missing_fonts`` 如实返回，装好字体后会重新转换。
字体安装：``backend/scripts/ops/install_onlyoffice_fonts.py``。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from jose import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

#: OnlyOffice 回来取文件的签名地址有效期（秒）
SOURCE_TTL_SECONDS = 120
#: 缓存的 PDF / 遗留的待转换文件保留时长（秒）
CACHE_KEEP_SECONDS = 7 * 24 * 3600
CONVERT_TIMEOUT_SECONDS = 60
DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
#: 默认回调基址（与交付件在线编辑同一取法）：容器经 Docker Desktop 的宿主别名访问本机后端
DEFAULT_CALLBACK_BASE = "http://host.docker.internal:9980"

_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
#: 单进程同时向 OnlyOffice 发起的转换数
_SEMAPHORE = asyncio.Semaphore(4)
#: 测试替换 OnlyOffice 的 HTTP 层（None = 真实网络）
_transport: httpx.AsyncBaseTransport | None = None

#: ConvertService 错误码 → 原因（OnlyOffice 文档：Conversion API · Possible error codes）
_ERRORS = {
    -1: "未知错误",
    -2: "转换超时",
    -3: "转换出错",
    -4: "OnlyOffice 取不到待转换的文件（请确认 ONLYOFFICE_CALLBACK_BASE 能从 OnlyOffice 容器访问到后端）",
    -5: "文件有密码",
    -6: "OnlyOffice 数据库出错",
    -7: "请求参数有误",
    -8: "签名无效（ONLYOFFICE_JWT_SECRET 与 OnlyOffice 容器的 JWT_SECRET 不一致）",
}


class ConvertError(Exception):
    """转换不可用或失败；``str(e)`` 是给用户看的原因。"""


@dataclass
class PdfResult:
    pdf: bytes
    cached: bool
    #: 要求的字体里 PDF 没用上的（显示名）；非空时结果未缓存
    missing_fonts: list[str] = field(default_factory=list)


def cache_dir() -> Path:
    return Path(settings.STORAGE_ROOT) / "preview_cache" / "onlyoffice_pdf"


def source_path(source_id: str) -> Path:
    return cache_dir() / f"{source_id}.docx"


def _sign(source_id: str, expires: int) -> str:
    payload = f"onlyoffice-pdf-source:{source_id}:{expires}".encode()
    return hmac.new(settings.JWT_SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()


def verify_source(source_id: str, expires: int, sig: str) -> bool:
    """取文件地址的签名校验：编号格式、未过期、签名一致。"""
    if not _KEY_RE.match(source_id) or int(time.time()) > expires:
        return False
    return hmac.compare_digest(sig, _sign(source_id, expires))


def _font_key(name: str) -> str:
    """字体名归一：去子集前缀（ABCDEF+）、大小写、空格 / 连字符，便于比对。"""
    name = name.split("+", 1)[-1]
    return re.sub(r"[\s\-_]", "", name).lower()


def embedded_fonts(pdf: bytes) -> set[str]:
    """PDF 实际用到的字体（归一化名）。

    PDF 字典里的 BaseFont 不可信：OnlyOffice 把 Arial Narrow 写成「Arial」，名字只能从内嵌字体程序里读；
    读不出字体程序时退回 BaseFont。
    """
    import pymupdf as fitz  # 新包名；旧名 fitz 导入时报 FutureWarning

    found: set[str] = set()
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        seen: set[int] = set()
        for page in doc:
            for info in page.get_fonts(full=True):
                xref, basefont = info[0], info[3]
                if xref in seen:
                    continue
                seen.add(xref)
                found.add(_font_key(basefont))
                try:
                    buf = doc.extract_font(xref)[3]
                    if buf:
                        found.add(_font_key(fitz.Font(fontbuffer=buf).name))
                except Exception:  # noqa: BLE001 — 个别字体程序读不出，只少一个名字
                    continue
    return found


def missing_fonts(pdf: bytes, required: dict[str, tuple[str, ...]]) -> list[str]:
    """``required`` = {显示名: 可接受的字体名…}；返回 PDF 里一个都没用上的显示名。"""
    used = embedded_fonts(pdf)
    return [label for label, names in required.items()
            if not any(any(u.startswith(_font_key(n)) for u in used) for n in names)]


def callback_base() -> str:
    return (settings.ONLYOFFICE_CALLBACK_BASE or DEFAULT_CALLBACK_BASE).rstrip("/")


def _public_url(url: str) -> str:
    """结果地址是 OnlyOffice 自己视角的（http://localhost/cache/…）⇒ 换成后端访问它用的 ONLYOFFICE_URL。"""
    base = urlsplit(settings.ONLYOFFICE_URL or "")
    parts = urlsplit(url)
    if not base.netloc or parts.netloc == base.netloc:
        return url
    return urlunsplit((base.scheme or parts.scheme, base.netloc, parts.path, parts.query, parts.fragment))


def _purge_old(now: float) -> None:
    """删超过保留期的缓存 PDF 与遗留的待转换文件（转换中途进程退出时留下的）。"""
    for f in cache_dir().glob("*"):
        try:
            if now - f.stat().st_mtime > CACHE_KEEP_SECONDS:
                f.unlink()
        except OSError:
            continue


async def docx_to_pdf(
    docx: bytes,
    cache_key: str,
    title: str,
    required_fonts: dict[str, tuple[str, ...]] | None = None,
) -> PdfResult:
    """docx → PDF。``cache_key`` 须能区分内容（调用方传 docx 内容摘要即可）。"""
    if not settings.ONLYOFFICE_URL:
        raise ConvertError("未配置 OnlyOffice 服务地址（ONLYOFFICE_URL），无法生成 Word 版式预览")
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(cache_key.encode()).hexdigest()
    cached = directory / f"{key}.pdf"
    if cached.is_file():
        return PdfResult(cached.read_bytes(), cached=True)

    pdf = await _convert(docx, title)
    missing = missing_fonts(pdf, required_fonts) if required_fonts else []
    if missing:
        logger.warning("[ONLYOFFICE_PDF] OnlyOffice 缺字体 %s，本次结果不缓存", missing)
    else:
        tmp = directory / f"{key}.{uuid.uuid4().hex}.tmp"
        try:
            tmp.write_bytes(pdf)
            os.replace(tmp, cached)
        except OSError as exc:  # 写缓存失败不影响本次结果
            logger.warning("[ONLYOFFICE_PDF] 缓存写入失败：%s", exc)
            tmp.unlink(missing_ok=True)
        _purge_old(time.time())
    return PdfResult(pdf, cached=False, missing_fonts=missing)


async def _convert(docx: bytes, title: str) -> bytes:
    source_id = secrets.token_hex(32)
    src = source_path(source_id)
    src.write_bytes(docx)
    try:
        async with _SEMAPHORE:
            return await _request_convert(source_id, title)
    finally:
        src.unlink(missing_ok=True)


async def _request_convert(source_id: str, title: str) -> bytes:
    expires = int(time.time()) + SOURCE_TTL_SECONDS
    url = (f"{callback_base()}/api/onlyoffice-pdf/sources/{source_id}"
           f"?expires={expires}&sig={_sign(source_id, expires)}")
    payload = {
        "async": False, "filetype": "docx", "outputtype": "pdf",
        "key": source_id[:40], "title": title, "url": url,
    }
    headers = {"Accept": "application/json"}
    if settings.ONLYOFFICE_JWT_SECRET:
        # 请求头带 JWT（OnlyOffice 容器 JWT_ENABLED=true 时必需；私网取文件也要靠它放行）
        token = jwt.encode({"payload": payload}, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256")
        headers["Authorization"] = f"Bearer {token}"
    base = settings.ONLYOFFICE_URL.rstrip("/")
    # trust_env=False：本机 HTTP(S)_PROXY 会把访问 OnlyOffice 的请求带进代理
    async with httpx.AsyncClient(timeout=CONVERT_TIMEOUT_SECONDS, transport=_transport, trust_env=False) as client:
        try:
            resp = await client.post(f"{base}/ConvertService.ashx", json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[ONLYOFFICE_PDF] 调用 ConvertService 失败：%s", exc)
            raise ConvertError("OnlyOffice 文档服务不可用，暂时无法生成 Word 版式预览") from exc
        error = result.get("error")
        if error is not None:
            reason = _ERRORS.get(error, f"错误码 {error}")
            if error == -8 and not settings.ONLYOFFICE_JWT_SECRET:
                reason = "OnlyOffice 要求签名，后端未配置 ONLYOFFICE_JWT_SECRET"
            logger.warning("[ONLYOFFICE_PDF] 转换失败 error=%s", error)
            raise ConvertError(f"OnlyOffice 转换失败：{reason}")
        file_url = result.get("fileUrl")
        if not result.get("endConvert") or not file_url:
            raise ConvertError("OnlyOffice 未完成转换，请稍后重试")
        try:
            pdf = await client.get(_public_url(str(file_url)))
            pdf.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("[ONLYOFFICE_PDF] 取回 PDF 失败：%s", exc)
            raise ConvertError("取回 OnlyOffice 转换结果失败，请稍后重试") from exc
    if not pdf.content.startswith(b"%PDF"):
        raise ConvertError("OnlyOffice 返回的不是 PDF")
    return pdf.content
