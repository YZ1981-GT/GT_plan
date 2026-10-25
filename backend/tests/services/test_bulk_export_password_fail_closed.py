"""批量导出的密码保护必须 fail-closed（spec environment-hygiene-deps-and-scratch-schemas Requirement 4）。

旧实现：要求密码时 ``import pyzipper`` 失败 ⇒ ``logger.warning`` 后**返回明文 ZIP**；加密过程
任何异常同样退回明文。用户设了密码，拿到的却是未加密压缩包，界面没有任何提示。

判据分三层：
  * 服务层 —— 缺 pyzipper 在**任何导出工作之前**失败（manifest 未建）；加密成功时每个条目
    都带加密标志、条目集合与明文一致、用密码可读、无密码不可读；加密异常 / 产物复核不通过 ⇒ 抛错。
  * 端点层 —— 真发请求（ASGI）：同步导出返回 503 + 中文原因，不返回 ZIP。
  * 异步层 —— 见 ``tests/test_bulk_async_runner.py``（原因写在文件末尾）。

缺 pyzipper 用 ``sys.modules["pyzipper"] = None`` 模拟（``import`` 即抛 ImportError），不卸载真包。
"""
from __future__ import annotations

import io
import os
import sys
import uuid
import zipfile
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pyzipper  # noqa: E402 - 真包必须已装（requirements.txt 声明 pyzipper==0.3.6）

from app.services.bulk_tab import bulk_export_service  # noqa: E402
from app.services.bulk_tab.exceptions import (  # noqa: E402
    BulkExportEncryptionError,
    BulkExportEncryptionFailedError,
    BulkExportEncryptionUnavailableError,
)
from app.services.bulk_tab.manifest_builder import BulkManifest, ManifestFileEntry  # noqa: E402

#: 🔴 **2026-09-30 契约变更**：原值 `"审计-Pa55!"` 含中文，按 Req 8.3 起属**非法输入**
#: （服务端按 UTF-8 加密，按 GBK 处理密码的解压软件会算出不同字节 ⇒ 密码输对了也打不开，
#: 真栈已实测确认）。本文件覆盖的是「能加密吗」这条链路，故密码改成合法 ASCII；
#: 「中文密码被拒」的正反用例在 `test_bulk_export_usability.py`。
PASSWORD = "Audit-Pa55!"
_PATCH_BUILD_MANIFEST = "app.services.bulk_tab.bulk_export_service.build_manifest"
_PATCH_EXPORT_TAB = "app.services.bulk_tab.bulk_export_service.export_tab"


# ═══ 夹具 ═════════════════════════════════════════════════════════════════════


def _xlsx(text: str) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["列1", "列2"])
    wb.active.append([text, "值"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _entry(sheet_code: str) -> ManifestFileEntry:
    return ManifestFileEntry(
        addr_id=f"D2/{sheet_code}", wp_code="D2", parent_wp_code="D2", sheet_code=sheet_code,
        sheet_name=f"明细表{sheet_code}", origin="standard", api_prefix="d2",
        item_id=f"{sheet_code}-vc-rows", storage_field="remark", wp_id=str(uuid.uuid4()),
        import_order=1, depends_on_sheets=[], zip_path=f"D/D2/{sheet_code}_明细表_数据.xlsx", sha256="",
    )


def _manifest() -> BulkManifest:
    return BulkManifest(
        project_id=str(uuid.uuid4()), audit_year=2025, exported_at="2026-09-30T10:00:00Z",
        exported_by="tester", mode="data", cycles=["D"], files=[_entry("D2-1"), _entry("D2-2")],
    )


@contextmanager
def _pyzipper_missing():
    saved = sys.modules.get("pyzipper")
    sys.modules["pyzipper"] = None  # type: ignore[assignment]  # import pyzipper → ImportError
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("pyzipper", None)
        else:
            sys.modules["pyzipper"] = saved


@contextmanager
def _export_world():
    """替换 manifest 构建与逐 Tab 导出；返回 build_manifest 替身供断言「是否开始了导出工作」。"""
    build = AsyncMock(side_effect=lambda *a, **k: _manifest())
    with patch(_PATCH_BUILD_MANIFEST, build), \
            patch(_PATCH_EXPORT_TAB, AsyncMock(side_effect=lambda **k: _xlsx(k["sheet_code"]))):
        yield build


def _quiet_db():
    """``db.get`` 返回 None：跳过「增量清单持久化」那一步（与本文件判据无关）。"""
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


async def _allow_every_sheet(wp_id, sheet_code):  # noqa: ANN001, ANN201
    return True


@contextmanager
def _visible_all():
    """端点层放行可见集过滤。

    🔴 为什么必须显式放行：``make_bulk_visible_filter`` 在 ``_bulk_app`` 的 MagicMock db
    上会抛错，而 ``export()`` 对过滤异常是 fail-closed（不导出该条目）⇒ **全部条目被剔除**。
    改造前这不影响本文件判据（零 Tab 照样产出 ZIP，只是里面没有底稿）；Req 8.1 起
    零 Tab ⇒ 422，不放行的话本文件测到的就不再是加密链路而是零 Tab 拦截。
    """
    with patch("app.routers.wp_bulk_router.make_bulk_visible_filter", lambda *a, **k: _allow_every_sheet):
        yield


async def _export(password: str | None, db=None):
    return await bulk_export_service.export(
        db=db or _quiet_db(), project_id=uuid.uuid4(), cycles=["D"], mode="data",
        password=password, exported_by="tester",
    )


# ═══ 1. 服务层 ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_password_without_pyzipper_fails_before_any_export_work():
    db = _quiet_db()
    with _pyzipper_missing(), _export_world() as build:
        with pytest.raises(BulkExportEncryptionUnavailableError) as info:
            await _export(PASSWORD, db=db)

    assert info.value.status_code == 503
    assert "pyzipper" in info.value.detail and "已中止导出" in info.value.detail
    build.assert_not_awaited()  # 连 manifest 都没建：不做无用功，也就不会先写增量清单
    db.get.assert_not_awaited()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_password_does_not_need_pyzipper():
    """未要求密码：缺 pyzipper 不影响导出，产物是普通 ZIP。"""
    with _pyzipper_missing(), _export_world():
        result = await _export(None)

    with zipfile.ZipFile(result) as zf:
        infos = zf.infolist()
        assert infos and not any(i.flag_bits & 0x1 for i in infos)
        assert "manifest.json" in zf.namelist()


@pytest.mark.asyncio
async def test_password_produces_aes_zip_with_every_entry_encrypted():
    with _export_world():
        plain = await _export(None)
        encrypted = await _export(PASSWORD)

    with zipfile.ZipFile(plain) as zf:
        plain_names = zf.namelist()
        plain_manifest_keys = set(__import__("json").loads(zf.read("manifest.json")))
    with zipfile.ZipFile(io.BytesIO(encrypted.getvalue())) as zf:
        infos = zf.infolist()
        assert [i.filename for i in infos] == plain_names
        assert all(i.flag_bits & 0x1 for i in infos), [i.filename for i in infos if not i.flag_bits & 0x1]
        with pytest.raises(RuntimeError, match="password required"):
            zf.read("manifest.json")  # 不给密码读不出
    with pyzipper.AESZipFile(io.BytesIO(encrypted.getvalue())) as zf:
        zf.setpassword(PASSWORD.encode("utf-8"))
        assert set(__import__("json").loads(zf.read("manifest.json"))) == plain_manifest_keys
        assert zf.read("D/D2/D2-1_明细表_数据.xlsx")[:2] == b"PK"  # 用密码读出的是真 xlsx
        zf.setpassword(b"wrong")
        with pytest.raises(RuntimeError, match="Bad password"):
            zf.read("manifest.json")


@pytest.mark.asyncio
async def test_encryption_exception_never_falls_back_to_plaintext():
    class _Boom(pyzipper.AESZipFile):
        def writestr(self, *a, **k):  # noqa: D401
            raise OSError("disk full")

    with _export_world(), patch.object(pyzipper, "AESZipFile", _Boom):
        with pytest.raises(BulkExportEncryptionFailedError) as info:
            await _export(PASSWORD)

    assert info.value.status_code == 500
    assert "加密失败" in info.value.detail and "不会输出未加密的压缩包" in info.value.detail
    assert isinstance(info.value.__cause__, OSError)  # 走的是「加密抛错」这条路


class _SilentPlain(zipfile.ZipFile):
    """「加密库」接受密码与加密参数却写出明文条目，且不抛任何异常。

    🔴 不能用 ``AESZipFile(encryption=None)`` 模拟：实测 pyzipper 那样会在 ``writestr`` 抛
    ``AttributeError``，于是测到的是「加密抛错」而不是「产物复核」—— 复核删掉也照样绿。
    """

    def __init__(self, file, mode="r", compression=zipfile.ZIP_DEFLATED, encryption=None, **_kw):
        super().__init__(file, mode, compression=compression)


class _DropsReadme(pyzipper.AESZipFile):
    """条目都加密了，但静默少写一个（条目集合与明文包不一致）。"""

    def writestr(self, zinfo_or_arcname, data, *a, **k):
        if zinfo_or_arcname == "README.txt":
            return None
        return super().writestr(zinfo_or_arcname, data, *a, **k)


@pytest.mark.asyncio
@pytest.mark.parametrize("impostor", [_SilentPlain, _DropsReadme], ids=["plaintext-entries", "missing-entry"])
async def test_output_verification_rejects_a_bad_archive(impostor):
    """加密库「成功返回」但产物不对 ⇒ 复核拦下（不返回），且拦下它的确实是复核本身。"""
    with _export_world(), patch.object(pyzipper, "AESZipFile", impostor):
        with pytest.raises(BulkExportEncryptionFailedError, match="加密失败") as info:
            await _export(PASSWORD)

    cause = info.value.__cause__
    assert isinstance(cause, RuntimeError) and "复核不通过" in str(cause), repr(cause)


def test_encryption_errors_carry_http_status_and_plain_message():
    """异步 runner 以 ``str(exc)`` 写任务错误：必须是中文原因本身，不能带 ``503: `` 前缀。"""
    for exc, status in (
        (BulkExportEncryptionUnavailableError("缺组件"), 503),
        (BulkExportEncryptionFailedError("加密失败"), 500),
    ):
        assert isinstance(exc, BulkExportEncryptionError)
        assert exc.status_code == status
        assert str(exc) == exc.detail


# ═══ 2. 端点层（真发请求）═══════════════════════════════════════════════════════


def _bulk_app():
    """只挂 bulk 路由的最小应用；鉴权与会话在内层依赖处替换，路由自身逻辑照常执行。"""
    from fastapi import FastAPI, HTTPException

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.middleware.error_handler import http_exception_handler
    from app.models.base import UserRole
    from app.routers import wp_bulk_router

    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)  # 与 main.py 同一处理器
    app.include_router(wp_bulk_router.router)

    user = SimpleNamespace(id=uuid.uuid4(), username="admin", role=UserRole.admin, is_active=True)
    project = SimpleNamespace(name="测试项目", short_name=None, audit_year=2025)
    db = MagicMock()
    db.get = AsyncMock(return_value=project)
    db.get_bind = MagicMock(return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["export-templates", "export-data"])
async def test_endpoint_returns_503_with_chinese_reason_instead_of_plain_zip(endpoint):
    from httpx import ASGITransport, AsyncClient

    app = _bulk_app()
    with _pyzipper_missing(), _export_world() as build:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{uuid.uuid4()}/bulk-tab/{endpoint}",
                json={"cycles": ["D"], "password": PASSWORD},
            )

    assert resp.status_code == 503, resp.text
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["code"] == 503 and "pyzipper" in body["message"] and "已中止导出" in body["message"]
    build.assert_not_awaited()


@pytest.mark.asyncio
async def test_endpoint_with_password_streams_an_encrypted_zip():
    """正向对照：同一端点在依赖齐全时返回加密 ZIP（证明上一条的 503 不是端点本身坏了）。"""
    from httpx import ASGITransport, AsyncClient

    app = _bulk_app()
    with _export_world(), _visible_all():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{uuid.uuid4()}/bulk-tab/export-templates",
                json={"cycles": ["D"], "password": PASSWORD},
            )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        infos = zf.infolist()
    assert infos and all(i.flag_bits & 0x1 for i in infos)
    # 两张底稿真的进了包（证明上面的 200 不是「零 Tab 却照样出包」那种假绿）
    assert [i.filename for i in infos if i.filename.startswith("D/")] == [
        "D/D2/D2-1_明细表_数据.xlsx",
        "D/D2/D2-2_明细表_数据.xlsx",
    ]


# 异步层（后台任务失败、错误文本无状态码前缀、不落 ZIP）写在 `tests/test_bulk_async_runner.py`：
# `_run_export` 是 writer 清册（`backend/data/workpaper_writer_inventory.json`）里的一行，清册按
# 「哪些测试文件调用了它」记 characterization 证据并参与新鲜度比对 —— 放在新文件里会让清册过期。
