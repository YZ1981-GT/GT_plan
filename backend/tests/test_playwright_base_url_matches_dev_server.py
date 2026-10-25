# -*- coding: utf-8 -*-
r"""e2e 入口地址一致性 —— `use.baseURL` 必须和 `webServer.url` 同 host。

起因（2026-09-30，D4-4 的 env 门验收）：`playwright.config.ts` 同一个文件里
`use.baseURL` 写 `http://127.0.0.1:3030`、`webServer.url` 写 `http://localhost:3030`，
而本机 **Vite 只监听 IPv6**（`netstat` 只有 `TCP [::1]:3030 LISTENING`）。

后果极难归因：`webServer` 探活走 `localhost` **能过**，于是 Playwright 认为服务已就绪；
随后所有相对 `page.goto('/...')` 走 `baseURL` 的 IPv4 地址 `ECONNREFUSED` ——
表象是「服务起着但页面打不开」，**本机任何 e2e 都跑不起来**，而报错落在业务判据上。

🔴 这个结论本仓早有记录：`audit-platform/frontend/scripts/check_vite_transform.mjs`
文件头就写着「Vite 只监听 IPv6，故用 localhost 而非 127.0.0.1（实测 `127.0.0.1:3030`
会『连接被拒绝』，极易误判成服务没起）」。知识在仓库里，只是 `playwright.config.ts`
没对齐 —— 本判据就是防这种「一处已知、另一处照旧」。

判据刻意**不写死 `localhost`**：真要改 host（比如将来 Vite 配 `host: true` 双栈）时，
两处一起改应当是允许的；不允许的是**两处不一致**。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "audit-platform" / "frontend"
_CONFIG = _FRONTEND / "playwright.config.ts"

_HOST_RE = re.compile(r"https?://([^/:'\"]+)(?::(\d+))?")


@pytest.fixture(scope="module")
def config_text() -> str:
    assert _CONFIG.exists(), f"找不到 {_CONFIG}"
    return _CONFIG.read_text(encoding="utf-8", errors="replace")


def _extract(text: str, key_pattern: str, label: str) -> tuple[str, str]:
    """取某个键的 URL 的 (host, port)。只认**非注释行**上的赋值。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue  # 注释里的历史值不算（本文件注释里就引了旧的 127.0.0.1）
        if not re.search(key_pattern, stripped):
            continue
        m = _HOST_RE.search(stripped)
        if m:
            return m.group(1), m.group(2) or ""
    pytest.fail(f"在 {_CONFIG.name} 的非注释行里找不到 {label}（正则 {key_pattern}）")


def test_base_url_and_web_server_url_share_the_same_host(config_text: str) -> None:
    """🔴 核心判据：两处 host 必须一致。

    不一致时 `webServer` 探活能过、而测试全连不上 —— 绿着的那一半会掩盖红着的那一半。
    """
    base_host, base_port = _extract(config_text, r"\bbaseURL\s*:", "use.baseURL")
    ws_host, ws_port = _extract(config_text, r"\burl\s*:", "webServer.url")
    assert base_host == ws_host, (
        f"use.baseURL 的 host 是 {base_host!r}，webServer.url 是 {ws_host!r} —— "
        "两者必须一致：探活用一个地址、测试用另一个地址时，服务就绪判断会假阳，"
        "而真实失败落在业务判据上（本机 Vite 只监听 IPv6，127.0.0.1 必拒连）"
    )
    assert base_port == ws_port, f"端口不一致：baseURL {base_port!r} vs webServer.url {ws_port!r}"


def test_no_ipv4_loopback_literal_survives_under_frontend() -> None:
    """反向断言：`audit-platform/frontend` 下**可执行代码**里不得再出现 `127.0.0.1:3030`。

    只查 config 一处会 fail-open —— e2e spec 里各自写死默认值同样会踩同一个坑
    （本轮就在 `g5-1-d4-price-linkage.spec.ts` 里发现一处）。
    注释与文档刻意放行：它们正是用来解释「为什么不能用 127.0.0.1」的。
    """
    offenders: list[str] = []
    for path in list(_FRONTEND.rglob("*.ts")) + list(_FRONTEND.rglob("*.mjs")):
        rel = path.relative_to(_FRONTEND).as_posix()
        if rel.startswith("node_modules/") or "/node_modules/" in rel:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if "127.0.0.1:3030" not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                continue
            offenders.append(f"{rel}:{i}: {stripped[:100]}")
    assert offenders == [], (
        "下列可执行语句仍写死 IPv4 回环地址（Vite 只监听 IPv6，必拒连）：\n  "
        + "\n  ".join(offenders)
    )


def test_the_ipv6_only_fact_is_documented_where_it_was_first_found() -> None:
    """那条「Vite 只监听 IPv6」的记录必须还在 —— 它是本判据的依据来源。

    若它被删掉，后人会把本判据当成无来由的洁癖而改回去。
    """
    mjs = _FRONTEND / "scripts" / "check_vite_transform.mjs"
    assert mjs.exists(), f"找不到 {mjs}"
    text = mjs.read_text(encoding="utf-8", errors="replace")
    assert "IPv6" in text and "127.0.0.1" in text, (
        "check_vite_transform.mjs 里关于「Vite 只监听 IPv6，故用 localhost」的记录不见了 —— "
        "那是本判据的依据，删它之前请先把依据搬到别处"
    )
