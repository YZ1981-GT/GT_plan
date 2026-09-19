# -*- coding: utf-8 -*-
"""D4-26「打开即定位到目标 sheet」端到端实测（真实后端 9980 + 真实 PG）。

判据落在**真实 DocServer 会下载到的那串字节**上，而不是"某个函数能跑"：

1. ``POST .../materialize`` 带 ``sheet_key='d4-26-managed'``；
2. 响应 ``onlyoffice_config.document.url`` 里的 contents token 必须含
   ``sheet='境外销售收入检查D4-26'`` claim（参数链前半段）；
3. 直接 GET 那个 URL（OO ``document.url`` 的真实消费路径，public 端点）拿到的 workbook
   里 ``xl/workbook.xml`` 的 ``activeTab`` 必须**正好**指向 D4-26 的 sheet 序号（后半段）。

🔴 负向对照同时跑 ``d4-25-managed``：两次打开同一份 artifact（D4 的 13 张受管 sheet 共用
``D/D4 收入底稿.xlsx``）必须拿到**不同**的 activeTab。缺这条，"定位"可能只是恰好等于
artifact 里写死的那个值。

前置：``start-dev.bat``（后端 9980）+ PG 在线 + 存在真实 D4 底稿。后端不在线时 skip。
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import uuid
import zipfile
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest

BASE = os.environ.get("D4_E2E_BASE", "http://127.0.0.1:9980")
PROJECT = os.environ.get("MS_E2E_PROJECT", "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
WP = os.environ.get("MS_E2E_WP", "b3ab3c46-828f-4f48-950e-aee9bbdc923f")
ENTRY = "xlsx/gt-d4-operating-revenue"
PREFIX = f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entries/{ENTRY}"

#: 契约实测冻结（`d4.revenue_detail` 的 sheets[]）。
TARGETS = {
    "d4-26-managed": "境外销售收入检查D4-26",
    "d4-25-managed": "经销商检查D4-25",
}


def _backend_up() -> bool:
    try:
        return httpx.get(f"{BASE}/api/health", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _backend_up(),
    reason="需真实后端(9980)在线 + 真实 D4 收入 entry（13 张受管 sheet 共用一本 workbook）",
)


def _login(c: httpx.Client) -> dict[str, str]:
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    body = r.json()
    token = body.get("data", {}).get("access_token") or body.get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _jwt_payload(token: str) -> dict:
    """只解 payload，不验签（验签是服务端的事；这里只看 claim 有没有被带上）。"""
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


def _active_tab(data: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("xl/workbook.xml").decode("utf-8")
    view = re.search(r"<workbookView[^>]*>", xml)
    hit = re.search(r'activeTab="(\d+)"', view.group(0)) if view else None
    return int(hit.group(1)) if hit else 0


def _sheet_order(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("xl/workbook.xml").decode("utf-8")
    return re.findall(r'<sheet[^>]*\bname="([^"]*)"', xml)


def _launch(c: httpx.Client, h: dict[str, str], sheet_key: str) -> dict:
    """flush → pending-mutation → materialize，返回 descriptor body。"""
    sp = c.get(PREFIX + "/store-projection", headers=h)
    assert sp.status_code == 200, sp.text[:500]
    data = sp.json().get("data", {})
    body = {
        "projection": data.get("projection") or {},
        "sheet_key": sheet_key,
        "expected_revision": data.get("expected_revision") or 0,
        "client_edit_epoch": 0,
    }
    idem = f"locate-e2e-{uuid.uuid4().hex[:8]}"
    pm = c.post(
        PREFIX + "/pending-mutations",
        headers={**h, "Idempotency-Key": idem},
        json=body,
    )
    assert pm.status_code == 200, f"pending-mutations 失败: {pm.text[:600]}"
    token = (pm.json().get("data") or {}).get("pending_mutation_token")
    assert token, f"未拿到 pending_mutation_token: {pm.text[:400]}"

    mr = c.post(
        PREFIX + "/materialize",
        headers={**h, "Idempotency-Key": idem},
        json={**body, "pending_mutation_token": token},
    )
    assert mr.status_code == 200, f"materialize 失败: {mr.status_code} {mr.text[:800]}"
    out = mr.json().get("data", mr.json())
    assert isinstance(out, dict) and out.get("artifact_sha256"), f"descriptor 不完整: {out}"
    return out


def _assert_locates(c: httpx.Client, descriptor: dict, sheet_key: str) -> tuple[int, str]:
    """descriptor → contents token claim → 真实下载字节的 activeTab。返回 (index, name)。"""
    expected_name = TARGETS[sheet_key]
    url = (descriptor.get("onlyoffice_config") or {}).get("document", {}).get("url") or ""
    assert "/contents?token=" in url, f"document.url 形态异常: {url[:200]}"

    # ① 参数链前半段：目标 sheet 进了**被签名的** contents claim。
    claims = _jwt_payload(url.split("token=", 1)[1])
    assert claims.get("sheet") == expected_name, (
        f"contents token 未带目标 sheet claim（参数链断在 materialize→token）: "
        f"{ {k: v for k, v in claims.items() if k != 'artifact_sha256'} }"
    )

    # ② 参数链后半段：OO document.url 的真实消费路径拿到的字节 activeTab 已指向目标。
    #
    # 🔴 host 要换成 BASE：`ONLYOFFICE_CALLBACK_BASE` 是给 **OO 容器**用的
    # （`host.docker.internal:9980`），从测试进程直连它会 502。token 不绑 host（claim 里
    # 只有 room/representation/artifact/sheet），换 host 不改变被验证的任何东西 ——
    # 这一步模拟的就是 DocServer 拿这枚 token 来下载。
    parts = urlsplit(url)
    base = urlsplit(BASE)
    local_url = urlunsplit((base.scheme, base.netloc, parts.path, parts.query, ""))
    got = c.get(local_url, headers={}, follow_redirects=True)
    assert got.status_code == 200, f"contents 下载失败: {got.status_code} {got.text[:300]}"
    payload = got.content
    assert payload[:2] == b"PK", "contents 返回的不是 xlsx（zip）字节"

    order = _sheet_order(payload)
    assert expected_name in order, (
        f"下发的 workbook 里没有 {expected_name!r}（只有 {len(order)} 张）—— 文档找错了"
    )
    tab = _active_tab(payload)
    assert tab == order.index(expected_name), (
        f"activeTab={tab} 指向 {order[tab] if tab < len(order) else '?'!r}，"
        f"期望 {order.index(expected_name)} = {expected_name!r}"
    )
    return tab, order[tab]


def test_d4_26_opens_on_its_own_sheet() -> None:
    with httpx.Client(base_url=BASE, timeout=240.0) as c:
        h = _login(c)
        descriptor = _launch(c, h, "d4-26-managed")
        tab, name = _assert_locates(c, descriptor, "d4-26-managed")
        assert name == TARGETS["d4-26-managed"]
        assert tab > 0, "D4-26 不该是 0 号 sheet（那样这条判据会恒真）"


def test_two_managed_sheets_of_one_workbook_get_different_active_tabs() -> None:
    """负向对照：同一份 artifact、两张受管 sheet ⇒ 必须各自定位，不是写死的常量。"""
    with httpx.Client(base_url=BASE, timeout=240.0) as c:
        h = _login(c)
        tab_26, name_26 = _assert_locates(
            c, _launch(c, h, "d4-26-managed"), "d4-26-managed"
        )
        tab_25, name_25 = _assert_locates(
            c, _launch(c, h, "d4-25-managed"), "d4-25-managed"
        )
    assert name_26 == TARGETS["d4-26-managed"]
    assert name_25 == TARGETS["d4-25-managed"]
    assert tab_26 != tab_25, "两张 sheet 拿到同一个 activeTab —— 定位没按本次目标算"
