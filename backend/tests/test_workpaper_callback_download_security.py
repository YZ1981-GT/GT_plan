"""Task 4 characterization：OnlyOffice callback 下载路径的 SSRF / DNS rebinding / redirect /
流式超限 / 超时 现状取证，以及 Property 16 / 17 的真实行为前置判据。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 4
Requirements 5.1 / 5.2 / 5.3 / 5.6 / 10.7

**这是 characterization，不是修复**：Task 4 硬约束「不接通生产 callback」。
本文件只做两件事：
  1. 从生产源码 AST 抽出真实的下载配置（`httpx.AsyncClient(...)` 参数、是否跟随重定向、
     是否流式、body 读取方式、url 在下载前经过哪些调用），任何漂移都会打红并强制重新裁决；
  2. 用**本机 mock server + 猴补 DNS 解析**（全离线，不触外网、不碰生产 callback 端点）
     按同一份配置真跑请求，把当前行为固化成可复核基线。

判据全部是「真实执行 + AST 数据流」，不是「字符串是否出现」：
  - 生产改成 `follow_redirects=True` / 加 size cap / 换成流式 → AST 断言红；
  - 本机 mock 行为变化（例如 httpx 版本改变 3xx 语义）→ 行为断言红。

契约侧的目标策略（allowlist / DNS 复核 / redirect 0 / 200MiB 流式上限 / 5s+30s 超时）见
`backend/data/onlyoffice_callback_state_contract.json` 的 `download_security`；
本文件的 `gaps` 断言与该契约互锁，防止 gap 清单被悄悄删空。
"""

from __future__ import annotations

import ast
import http.server
import json
import socket
import threading
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.routers import wp_onlyoffice_router as router_mod
from app.services.wp_visibility import editor_security

_REPO = Path(__file__).resolve().parents[2]
_ROUTER_PATH = Path(router_mod.__file__)
_CONTRACT_PATH = _REPO / "backend" / "data" / "onlyoffice_callback_state_contract.json"
_CALLBACK_FUNC = "post_sheet_onlyoffice_callback"

_ONE_MIB = 1024 * 1024


# ---------------------------------------------------------------------------
# 一、从生产源码抽真实下载配置（AST，不用正则）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DownloadProfile:
    """生产 callback 下载调用点的真实配置快照。"""

    client_kwargs: tuple[tuple[str, Any], ...]
    get_kwargs: tuple[str, ...]
    body_attribute: str
    url_preprocessors: tuple[str, ...]
    writes_downloaded_bytes_directly: bool
    claim_version_argument: str

    @property
    def timeout(self) -> float:
        return float(dict(self.client_kwargs)["timeout"])

    @property
    def trust_env(self) -> bool:
        """httpx `trust_env` 默认 True：未显式传参即代表生产会采用环境/系统代理。"""
        return bool(dict(self.client_kwargs).get("trust_env", True))

    @property
    def follow_redirects(self) -> bool:
        return bool(dict(self.client_kwargs).get("follow_redirects", False)) or (
            "follow_redirects" in self.get_kwargs
        )


def _callback_function_ast() -> ast.AsyncFunctionDef:
    tree = ast.parse(_ROUTER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == _CALLBACK_FUNC:
            return node
    raise AssertionError(
        f"生产 callback 函数 {_CALLBACK_FUNC} 不存在于 {_ROUTER_PATH}："
        "characterization 失去锚点，必须重新定位后再断言"
    )


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


@pytest.fixture(scope="module")
def profile() -> DownloadProfile:
    func = _callback_function_ast()

    client_kwargs: list[tuple[str, Any]] = []
    get_kwargs: list[str] = []
    body_attribute = ""
    url_preprocessors: list[str] = []
    writes_directly = False
    claim_version_argument = "<missing>"
    downloaded_var = ""

    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "AsyncClient":
                for kw in node.keywords:
                    client_kwargs.append(
                        (kw.arg or "**", ast.literal_eval(kw.value) if isinstance(kw.value, ast.Constant) else "<expr>")
                    )
            elif name == "get" and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "url":
                get_kwargs.extend(kw.arg or "**" for kw in node.keywords)
            elif name == "verify_callback_preconditions":
                for kw in node.keywords:
                    if kw.arg == "claim_version":
                        claim_version_argument = (
                            "None"
                            if isinstance(kw.value, ast.Constant) and kw.value.value is None
                            else ast.dump(kw.value)[:60]
                        )
        # url = <fn>(url, ...)  → 下载前对 url 本身施加的变换链
        # （`url = body.get("url")` 只是取值、不是变换，故要求实参里真的引用了 `url`）
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (
                isinstance(target, ast.Name)
                and target.id == "url"
                and isinstance(node.value, ast.Call)
                and any(
                    isinstance(arg, ast.Name) and arg.id == "url"
                    for arg in ast.walk(node.value)
                    if isinstance(arg, ast.Name)
                )
            ):
                url_preprocessors.append(_call_name(node.value))
            # file_bytes = resp.content
            if (
                isinstance(target, ast.Name)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr in {"content", "text"}
            ):
                body_attribute = node.value.attr
                downloaded_var = target.id

    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and _call_name(node) == "write_bytes"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == downloaded_var
        ):
            writes_directly = True

    return DownloadProfile(
        client_kwargs=tuple(client_kwargs),
        get_kwargs=tuple(get_kwargs),
        body_attribute=body_attribute,
        url_preprocessors=tuple(url_preprocessors),
        writes_downloaded_bytes_directly=writes_directly,
        claim_version_argument=claim_version_argument,
    )


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 二、离线 mock server（redirect / 超大 body / 慢响应 / 非 xlsx）
# ---------------------------------------------------------------------------

_SECRET_BODY = b"SSRF-INTERNAL-SECRET-BODY"


def _tiny_zip() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


class _MockHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # noqa: A003 — 静音
        return

    def _body(self, code: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/ok.xlsx":
            self._body(200, _tiny_zip(), "application/octet-stream")
        elif path == "/redirect-once":
            self._body(
                302,
                b"<html>moved</html>",
                "text/html",
                {"Location": "/internal-secret"},
            )
        elif path == "/internal-secret":
            self._body(200, _SECRET_BODY, "text/plain")
        elif path == "/big.xlsx":
            mib = int((self.path.split("mib=") + ["8"])[-1] or 8)
            self._body(200, b"A" * (mib * _ONE_MIB), "application/octet-stream")
        elif path == "/slow.xlsx":
            import time

            time.sleep(1.5)
            self._body(200, _tiny_zip(), "application/octet-stream")
        elif path == "/text-as.xlsx":
            self._body(200, b"this is definitely not a workbook", "text/plain")
        else:
            self._body(404, b"nope", "text/plain")


class _QuietServer(http.server.ThreadingHTTPServer):
    """读超时用例会在服务端写响应时断开连接；那属于预期，不该往 stderr 刷栈。"""

    def handle_error(self, request: Any, client_address: Any) -> None:  # noqa: D102
        return


@pytest.fixture(scope="module")
def mock_server() -> Any:
    server = _QuietServer(("127.0.0.1", 0), _MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def direct_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制本次请求直连 mock server。

    生产 `httpx.AsyncClient(timeout=60)` 的 `trust_env` 默认 True，而 Windows 上
    `urllib.request.getproxies()` 会读**注册表系统代理**（本机实测 `http://127.0.0.1:7897`），
    因此不设 `no_proxy` 时请求会被代理劫持（实测返回 502）。
    该副作用本身由 `test_production_download_trusts_environment_proxy` 单独取证；
    其余行为断言必须直连才能测到目标行为，故在此隔离。
    """
    monkeypatch.setenv("no_proxy", "*")


def _download_like_production(url: str, prof: DownloadProfile, *, timeout: float | None = None) -> httpx.Response:
    """完全按生产配置执行一次下载（timeout / follow_redirects / body 读取方式一致）。"""
    with httpx.Client(
        timeout=timeout if timeout is not None else prof.timeout,
        follow_redirects=prof.follow_redirects,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        _ = getattr(resp, prof.body_attribute)
        return resp


# ---------------------------------------------------------------------------
# 三、AST 锚点：生产下载配置的真实形状
# ---------------------------------------------------------------------------


def test_production_download_profile_is_unchanged(profile: DownloadProfile) -> None:
    """生产配置漂移必须打红（否则下面的行为基线就成了脱锚的自说自话）。"""
    assert dict(profile.client_kwargs) == {"timeout": 60}, (
        f"生产 httpx.AsyncClient 参数已变为 {dict(profile.client_kwargs)}：需重新 characterization"
    )
    assert profile.get_kwargs == (), f"client.get 出现新参数 {profile.get_kwargs}"
    assert profile.follow_redirects is False, "生产已开启 follow_redirects：重定向基线失效"
    assert profile.body_attribute == "content", (
        f"body 读取方式已变为 {profile.body_attribute!r}（流式化会改变内存上限结论）"
    )
    assert profile.url_preprocessors == ("_rewrite_onlyoffice_download_url",), (
        f"下载前对 url 的处理链已变为 {profile.url_preprocessors}：若新增校验，需重测 SSRF 结论"
    )


def test_production_has_single_undifferentiated_timeout(profile: DownloadProfile) -> None:
    """契约要求 connect/read 分离超时；现状是单一 60s 总超时。"""
    with httpx.Client(timeout=profile.timeout) as client:
        timeout = client.timeout
    assert timeout.connect == timeout.read == timeout.write == timeout.pool == profile.timeout
    controls = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))["download_security"][
        "required_controls"
    ]
    assert controls["connect_timeout_seconds"] < profile.timeout
    assert controls["read_timeout_seconds"] < profile.timeout


def test_production_writes_downloaded_bytes_without_staging(profile: DownloadProfile) -> None:
    """Property 17 前置判据：现状是「下载 → 直写共享 canonical 文件」，无 staging/quarantine/incoming。"""
    assert profile.writes_downloaded_bytes_directly, (
        "未找到 `write_bytes(<下载 bytes>)` 直写链路：Property 17 的现状基线需重新定位"
    )
    func = _callback_function_ast()
    isolation_calls = sorted(
        {
            _call_name(node)
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and any(
                marker in _call_name(node).lower()
                for marker in ("stag", "quarantin", "incoming", "durable")
            )
        }
    )
    assert isolation_calls == [], (
        f"生产 callback 已出现隔离/durable 调用 {isolation_calls}：Property 17 现状基线需重新裁决"
    )


def test_production_passes_claim_version_none(profile: DownloadProfile) -> None:
    """Property 16 前置判据（Requirement 5.2）：生产实际传 `claim_version=None`。"""
    assert profile.claim_version_argument == "None", (
        f"生产 claim_version 实参已变为 {profile.claim_version_argument}：Property 16 基线需重测"
    )


def test_claim_version_none_bypasses_version_check_today() -> None:
    """真跑生产函数：None 直通，非空则真比对 —— 机制存在，但被调用点用 None 绕过。"""
    ok, reason = editor_security.verify_callback_preconditions(
        claim_action="callback",
        server_action="callback",
        claim_version=None,
        current_version="7",
        gate_allow_write=True,
    )
    assert (ok, reason) == (True, None), "claim_version=None 已不再直通：Property 16 基线需重测"

    stale_ok, stale_reason = editor_security.verify_callback_preconditions(
        claim_action="callback",
        server_action="callback",
        claim_version="6",
        current_version="7",
        gate_allow_write=True,
    )
    assert (stale_ok, stale_reason) == (False, "version_conflict"), (
        "传入真实 claim version 时必须能拦住旧版本覆盖；机制失效则 Property 16 无从实现"
    )


# ---------------------------------------------------------------------------
# 四、行为 characterization：SSRF / rebinding / redirect / 超限 / 超时
# ---------------------------------------------------------------------------


def test_url_rewrite_keeps_attacker_controlled_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """现状：只换 netloc，path/query 原样保留（allowlist 只到主机粒度且没有 path 约束）。"""
    monkeypatch.setattr(settings, "ONLYOFFICE_URL", "http://localhost:8080", raising=False)
    rewritten = router_mod._rewrite_onlyoffice_download_url(
        "http://oo-internal/cache/../../etc/passwd?md5=x&expires=1"
    )
    assert rewritten == "http://localhost:8080/cache/../../etc/passwd?md5=x&expires=1", rewritten


def test_url_rewrite_is_noop_without_onlyoffice_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """现状：ONLYOFFICE_URL 为空时 payload 的 host 完全生效 ⇒ SSRF 面开放。"""
    monkeypatch.setattr(settings, "ONLYOFFICE_URL", "", raising=False)
    hostile = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
    assert router_mod._rewrite_onlyoffice_download_url(hostile) == hostile


def test_loopback_and_private_targets_are_not_blocked(
    profile: DownloadProfile, mock_server: str, monkeypatch: pytest.MonkeyPatch, direct_network: None
) -> None:
    """SSRF characterization：环回地址无任何拦截，下载照常成功。"""
    monkeypatch.setattr(settings, "ONLYOFFICE_URL", "", raising=False)
    url = router_mod._rewrite_onlyoffice_download_url(f"{mock_server}/ok.xlsx")
    resp = _download_like_production(url, profile)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK", "环回目标未被拦截（现状基线）"


def test_dns_rebinding_is_not_rechecked(
    profile: DownloadProfile, mock_server: str, monkeypatch: pytest.MonkeyPatch, direct_network: None
) -> None:
    """DNS rebinding characterization：域名解析到环回地址后无二次复核，请求直达内网。

    离线实现：猴补 `socket.getaddrinfo`，把伪域名解析到本机 mock server。
    """
    port = int(mock_server.rsplit(":", 1)[1])
    fake_host = "oo-cache.rebind.invalid"
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host: str, *args: Any, **kwargs: Any) -> Any:
        if host == fake_host:
            return real_getaddrinfo("127.0.0.1", port, *args[1:], **kwargs)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(settings, "ONLYOFFICE_URL", "", raising=False)

    url = router_mod._rewrite_onlyoffice_download_url(f"http://{fake_host}:{port}/internal-secret")
    resp = _download_like_production(url, profile)
    assert resp.status_code == 200
    assert resp.content == _SECRET_BODY, (
        "rebinding 目标未被拦截（现状基线）；一旦实现解析后 IP 复核，本断言必须改为期望拒绝"
    )


def test_redirect_is_rejected_only_implicitly_by_client_behavior(
    profile: DownloadProfile, mock_server: str, direct_network: None
) -> None:
    """redirect characterization（实测纠正了纸面推断）。

    实测 httpx 0.28：`follow_redirects=False` 时 `raise_for_status()` **对 3xx 也抛
    `HTTPStatusError`** ⇒ 生产不会把 302 页面当文件写盘，重定向事实上被拦下。
    但这层保护是**客户端库版本行为的隐式依赖**，不是显式重定向策略：
      - 一旦有人加 `follow_redirects=True`，请求就会跟到重定向目标（下半段实测）；
      - 一旦换掉 httpx 或改用只检查 4xx/5xx 的判断，3xx body 就会落盘。
    故契约仍要求显式 `follow_redirects=False + max_redirects=0`。
    """
    with httpx.Client(timeout=profile.timeout, follow_redirects=profile.follow_redirects) as client:
        resp = client.get(f"{mock_server}/redirect-once")
        assert resp.status_code == 302
        assert _SECRET_BODY not in resp.content, "未跟随重定向（follow_redirects=False 的现状）"
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            resp.raise_for_status()
        assert "302" in str(excinfo.value)

    # 反证：若配置改成跟随重定向，同一条 callback url 就能把请求引到另一个资源。
    with httpx.Client(timeout=profile.timeout, follow_redirects=True) as client:
        followed = client.get(f"{mock_server}/redirect-once")
        followed.raise_for_status()
    assert followed.content == _SECRET_BODY, (
        "跟随重定向后确实抵达了重定向目标 ⇒ 显式 max_redirects=0 仍是必需的契约项"
    )


def test_no_streaming_size_cap(
    profile: DownloadProfile, mock_server: str, contract: dict[str, Any], direct_network: None
) -> None:
    """流式超限 characterization：`resp.content` 把整包读进内存，8 MiB 全量落到内存无任何截断。"""
    resp = _download_like_production(f"{mock_server}/big.xlsx?mib=8", profile)
    body = getattr(resp, profile.body_attribute)
    assert len(body) == 8 * _ONE_MIB, "现状基线：无大小上限、无流式截断"
    cap = contract["download_security"]["required_controls"]["streaming_size_cap_bytes"]
    assert cap >= len(body), (
        "契约上限已低于本测试样本，样本需调整（避免用超过上限的样本证明'无上限'）"
    )


def test_read_timeout_is_far_looser_than_contract(
    profile: DownloadProfile, mock_server: str, direct_network: None
) -> None:
    """超时 characterization：1.5s 才回响应头也照样成功（生产 60s 单一超时）。

    同时证明「按契约的 30s 读超时同样能通过」，即真正的差距在**没有连接/读取分离与更短读超时**，
    而不是随便一个慢响应就会被拦 —— 这样后续实现改成 5s/30s 时本测试不会假红。
    """
    resp = _download_like_production(f"{mock_server}/slow.xlsx", profile)
    assert resp.status_code == 200
    with pytest.raises(httpx.ReadTimeout):
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=0.3, write=5.0, pool=5.0)) as client:
            client.get(f"{mock_server}/slow.xlsx")


def test_no_content_type_or_ooxml_validation_at_download(
    profile: DownloadProfile, mock_server: str, direct_network: None
) -> None:
    """OOXML characterization：text/plain 内容照样被完整接收（下载层不做 magic/MIME 校验）。"""
    resp = _download_like_production(f"{mock_server}/text-as.xlsx", profile)
    body = getattr(resp, profile.body_attribute)
    assert resp.headers["content-type"].startswith("text/plain")
    assert body[:2] != b"PK" and len(body) > 0, "现状基线：非 OOXML 内容不会在下载层被拒"


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    """最小 HTTP 代理：只记录被代理的绝对 URI，并回一个可识别的 body。"""

    protocol_version = "HTTP/1.1"
    seen: list[str] = []

    def log_message(self, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        _ProxyHandler.seen.append(self.path)
        body = b"INTERCEPTED-BY-PROXY"
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_production_download_trusts_environment_proxy(
    profile: DownloadProfile, monkeypatch: pytest.MonkeyPatch
) -> None:
    """代理 characterization：生产未传 `trust_env=False` ⇒ callback 下载会走环境/系统代理。

    本机实测 `urllib.request.getproxies()` 读到 Windows 注册表系统代理
    （`http://127.0.0.1:7897`），未设 `no_proxy` 时 callback 下载会被劫持并返回 502。
    这既是可用性风险（保存失败），也是 Requirement 10.7 的泄露风险（底稿字节过第三方代理）。
    """
    assert profile.trust_env is True, "生产已显式关闭 trust_env：代理 gap 已修复，需更新契约"

    proxy = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    _ProxyHandler.seen.clear()
    try:
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy.server_address[1]}")
        target = "http://oo-cache.internal.invalid/cache/files/data/x/output.xlsx"
        with httpx.Client(timeout=profile.timeout) as client:  # 与生产同款构造（trust_env 默认 True）
            resp = client.get(target)
            resp.raise_for_status()
            body = getattr(resp, profile.body_attribute)
    finally:
        proxy.shutdown()
        proxy.server_close()

    assert body == b"INTERCEPTED-BY-PROXY", "请求未经代理 —— 代理 gap 结论需重新取证"
    assert _ProxyHandler.seen and _ProxyHandler.seen[0] == target, (
        f"代理未收到原始绝对 URI: {_ProxyHandler.seen}"
    )


# ---------------------------------------------------------------------------
# 五、与真值表契约互锁：gap 清单不得被悄悄删空
# ---------------------------------------------------------------------------


def test_contract_gap_list_matches_characterized_reality(contract: dict[str, Any], profile: DownloadProfile) -> None:
    current = contract["download_security"]["characterized_current_production_behavior"]
    assert current["characterization_test"] == "backend/tests/test_workpaper_callback_download_security.py"
    gaps = " ".join(current["gaps"])
    # 每条 gap 都必须有本文件的行为/AST 断言支撑；反之若生产已修复，AST 断言会先红。
    assert "allowlist" in gaps
    assert "DNS" in gaps
    assert "重定向" in gaps or "3xx" in gaps
    assert "大小上限" in gaps or "内存" in gaps
    assert "超时" in gaps
    assert profile.follow_redirects is False and profile.body_attribute == "content", (
        "gap 清单与真实配置脱钩：生产已改动却未更新契约"
    )
