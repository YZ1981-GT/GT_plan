"""报告正文网页预览：导出的 Word 经 OnlyOffice 转 PDF（``services/onlyoffice_pdf``）。

假 OnlyOffice（httpx.MockTransport）照真实 ConvertService 的做法**回来取签名地址**的文件 ⇒
签名、取文件接口、缓存、缺字体判定都走生产代码，只把 OnlyOffice 的转换本身换成「生成一份 PDF」。
「转出的 PDF 用了哪些字体」由 ``FakeOnlyOffice.font_name`` 决定（改写内嵌字体的 BaseFont，
字体程序仍是 PyMuPDF 自带的 Droid Sans Fallback）。
"""

from __future__ import annotations

import json
from io import BytesIO
from urllib.parse import unquote, urlsplit

import httpx
import pymupdf as fitz
import pytest
import pytest_asyncio
from docx import Document
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.core.config import settings
from app.routers.onlyoffice_pdf import router as source_router
from app.services import onlyoffice_pdf
from tests.test_tax_assurance_api import URL, Y, env  # noqa: F401 — 共用夹具（项目 / 成员 / 试算表）

SECRET = "oo-preview-test-secret"
ALL_FONTS = ("FangSong", "SimHei", "ArialNarrow")


def make_pdf(base_fonts: tuple[str, ...]) -> bytes:
    """每个 BaseFont 一页、各内嵌一份 PyMuPDF 自带 CJK 字体，再把 BaseFont 改成给定名字。

    🔴 同一文档里多次 insert_font 同一份字体内容会被合并成一个字体对象 ⇒ 每种字体单独成文档再合并。
    """
    out = fitz.open()
    buf = fitz.Font("cjk").buffer
    for name in base_fonts:
        one = fitz.open()
        page = one.new_page()
        page.insert_font(fontname="F0", fontbuffer=buf)
        page.insert_text((72, 72), "报告", fontname="F0")
        xref = page.get_fonts(full=True)[0][0]
        one.xref_set_key(xref, "BaseFont", "/ABCDEF+" + name.replace(" ", "#20"))
        out.insert_pdf(fitz.open(stream=one.tobytes(), filetype="pdf"))
        one.close()
    data = out.tobytes()
    out.close()
    return data


class FakeOnlyOffice:
    """记录请求、回后端取文件、返回 ``base_fonts`` 字体的 PDF。"""

    def __init__(self, app: FastAPI):
        self.app = app
        self.base_fonts: tuple[str, ...] = ALL_FONTS
        self.calls: list[dict] = []
        self.fetched: list[bytes] = []
        self.error: int | None = None

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ConvertService.ashx":
            body = json.loads(request.content)
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            assert jwt.decode(token, SECRET, algorithms=["HS256"])["payload"] == body, "JWT 载荷须与请求体一致"
            self.calls.append(body)
            if self.error is not None:
                return httpx.Response(200, json={"error": self.error})
            src = urlsplit(body["url"])
            assert src.netloc == "backend", "取文件地址须用 ONLYOFFICE_CALLBACK_BASE"
            async with AsyncClient(transport=ASGITransport(app=self.app), base_url="http://backend") as c:
                got = await c.get(f"{src.path}?{src.query}")
            assert got.status_code == 200, got.text
            self.fetched.append(got.content)
            return httpx.Response(200, json={"endConvert": True, "percent": 100,
                                             "fileUrl": "http://localhost/cache/files/out.pdf"})
        if request.url.path == "/cache/files/out.pdf":
            assert request.url.host == "oo.test", "结果地址须换成后端访问 OnlyOffice 用的 ONLYOFFICE_URL"
            return httpx.Response(200, content=make_pdf(self.base_fonts))
        return httpx.Response(404)


@pytest_asyncio.fixture
async def oo(env, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(settings, "ONLYOFFICE_URL", "http://oo.test")
    monkeypatch.setattr(settings, "ONLYOFFICE_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "ONLYOFFICE_CALLBACK_BASE", "http://backend")
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    source_app = FastAPI()
    source_app.include_router(source_router)
    fake = FakeOnlyOffice(source_app)
    monkeypatch.setattr(onlyoffice_pdf, "_transport", httpx.MockTransport(fake))
    return fake


def _missing(resp: httpx.Response) -> list[str]:
    return [unquote(s) for s in resp.headers["x-preview-missing-fonts"].split(",") if s]


@pytest.mark.asyncio
async def test_preview_converts_export_and_caches(env, oo):  # noqa: F811
    c = env["client"]
    r = await c.get(f"{URL}/report-body/preview.pdf", params=Y)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert r.headers["x-preview-cache"] == "miss" and _missing(r) == []
    # OnlyOffice 取到的是导出的同一份 Word（占位已替换）
    assert len(oo.fetched) == 1
    text = "\n".join(p.text for p in Document(BytesIO(oo.fetched[0])).paragraphs)
    assert "甲公司" in text and "{{" not in text
    assert oo.calls[0]["filetype"] == "docx" and oo.calls[0]["outputtype"] == "pdf"
    # 转换结束待转换文件即删除，同一签名地址再取 404
    src = urlsplit(oo.calls[0]["url"])
    async with AsyncClient(transport=ASGITransport(app=oo.app), base_url="http://backend") as raw:
        assert (await raw.get(f"{src.path}?{src.query}")).status_code == 404

    again = await c.get(f"{URL}/report-body/preview.pdf", params=Y)
    assert again.headers["x-preview-cache"] == "hit" and len(oo.calls) == 1

    # 内容变了（报告日期）⇒ 重新转换
    saved = await c.put(f"{URL}/report-body", params=Y, json={"version": 0, "report_date": "2026-04-30"})
    assert saved.status_code == 200, saved.text
    third = await c.get(f"{URL}/report-body/preview.pdf", params=Y)
    assert third.headers["x-preview-cache"] == "miss" and len(oo.calls) == 2
    assert "2026年4月30日" in "\n".join(p.text for p in Document(BytesIO(oo.fetched[1])).paragraphs)


@pytest.mark.asyncio
async def test_missing_fonts_reported_and_not_cached(env, oo):  # noqa: F811
    """OnlyOffice 没装中文字体（回退 Droid Sans Fallback）⇒ 如实回报、不缓存；装好后重新转换。"""
    c = env["client"]
    oo.base_fonts = ("Droid Sans Fallback", "Arial")
    r = await c.get(f"{URL}/report-body/preview.pdf", params=Y)
    assert r.status_code == 200, r.text
    assert _missing(r) == ["仿宋", "黑体", "Arial Narrow"]
    assert (await c.get(f"{URL}/report-body/preview.pdf", params=Y)).headers["x-preview-cache"] == "miss"
    oo.base_fonts = ALL_FONTS
    fixed = await c.get(f"{URL}/report-body/preview.pdf", params=Y)
    assert _missing(fixed) == [] and len(oo.calls) == 3


@pytest.mark.parametrize("error, reason", [(-4, "取不到待转换的文件"), (-8, "签名无效")])
@pytest.mark.asyncio
async def test_convert_error_is_503_with_reason(env, oo, error, reason):  # noqa: F811
    oo.error = error
    r = await env["client"].get(f"{URL}/report-body/preview.pdf", params=Y)
    assert r.status_code == 503
    assert reason in r.json()["detail"]


@pytest.mark.asyncio
async def test_onlyoffice_unreachable_is_503(env, oo, monkeypatch):  # noqa: F811
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(onlyoffice_pdf, "_transport", httpx.MockTransport(boom))
    r = await env["client"].get(f"{URL}/report-body/preview.pdf", params=Y)
    assert r.status_code == 503 and "不可用" in r.json()["detail"]


@pytest.mark.asyncio
async def test_preview_requires_project_access(env, oo):  # noqa: F811
    env["as"]("reader")
    assert (await env["client"].get(f"{URL}/report-body/preview.pdf", params=Y)).status_code == 200
    env["as"]("outsider")
    assert (await env["client"].get(f"{URL}/report-body/preview.pdf", params=Y)).status_code == 403
    assert len(oo.calls) == 1


@pytest.mark.asyncio
async def test_source_endpoint_rejects_bad_signature(oo):
    """取文件接口不带用户令牌，只认签名：伪造 / 过期 / 编号格式不对一律 403。"""
    sid = "a" * 64
    onlyoffice_pdf.cache_dir().mkdir(parents=True, exist_ok=True)
    onlyoffice_pdf.source_path(sid).write_bytes(b"docx")
    good_exp = 9_999_999_999
    good = onlyoffice_pdf._sign(sid, good_exp)
    async with AsyncClient(transport=ASGITransport(app=oo.app), base_url="http://backend") as c:
        base = "/api/onlyoffice-pdf/sources"
        assert (await c.get(f"{base}/{sid}", params={"expires": good_exp, "sig": good})).content == b"docx"
        assert (await c.get(f"{base}/{sid}", params={"expires": good_exp, "sig": "0" * 64})).status_code == 403
        assert (await c.get(f"{base}/{sid}", params={"expires": good_exp + 1, "sig": good})).status_code == 403
        old = 1_000
        assert (await c.get(f"{base}/{sid}", params={"expires": old, "sig": onlyoffice_pdf._sign(sid, old)})).status_code == 403
        bad_id = "..%2F" + "a" * 59
        assert (await c.get(f"{base}/{bad_id}", params={"expires": good_exp, "sig": good})).status_code in (403, 404)


def test_missing_fonts_reads_font_program_not_basefont():
    """OnlyOffice 把 Arial Narrow 写成 BaseFont「Arial」：判定看字体程序里的真名。"""
    pdf = make_pdf(("Arial",))
    assert onlyoffice_pdf.missing_fonts(pdf, {"Arial Narrow": ("ArialNarrow",)}) == ["Arial Narrow"]
    assert onlyoffice_pdf.missing_fonts(pdf, {"fallback": ("Droid Sans Fallback",)}) == []
