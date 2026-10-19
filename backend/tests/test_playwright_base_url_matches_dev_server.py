# -*- coding: utf-8 -*-
"""前端开发服务器地址族契约。

2026-10-19 实测：Windows IPv6 loopback 可出现 `[::1]:3030 LISTENING`，但任何 TCP
连接都被拒绝。Vite 必须显式监听 0.0.0.0，启动器、Playwright 与 transform probe
统一走 127.0.0.1，避免“服务看似已启动但页面打不开”。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "audit-platform" / "frontend"
_CONFIG = _FRONTEND / "playwright.config.ts"
_VITE_CONFIG = _FRONTEND / "vite.config.ts"
_TRANSFORM = _FRONTEND / "scripts" / "check_vite_transform.mjs"
_HOST_RE = re.compile(r"https?://([^/:'\"]+)(?::(\d+))?")


@pytest.fixture(scope="module")
def config_text() -> str:
    assert _CONFIG.exists(), f"找不到 {_CONFIG}"
    return _CONFIG.read_text(encoding="utf-8", errors="strict")


def _extract(text: str, key_pattern: str, label: str) -> tuple[str, str]:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        if not re.search(key_pattern, stripped):
            continue
        match = _HOST_RE.search(stripped)
        if match:
            return match.group(1), match.group(2) or ""
    pytest.fail(f"在 {_CONFIG.name} 的非注释行里找不到 {label}")


def test_base_url_and_web_server_url_share_ipv4_loopback(config_text: str) -> None:
    base_host, base_port = _extract(config_text, r"\bbaseURL\s*:", "use.baseURL")
    ws_host, ws_port = _extract(config_text, r"\burl\s*:", "webServer.url")
    assert (base_host, base_port) == (ws_host, ws_port)
    assert base_host == "127.0.0.1", (
        "Playwright 必须使用 IPv4 loopback；localhost 可能先落到失效的 ::1"
    )
    assert base_port == "3030"


def test_vite_explicitly_binds_ipv4_all_interfaces() -> None:
    text = _VITE_CONFIG.read_text(encoding="utf-8", errors="strict")
    assert re.search(r"\bhost\s*:\s*['\"]0\.0\.0\.0['\"]", text), (
        "Vite 未显式监听 0.0.0.0，Windows 可能退回 IPv6-only ::1"
    )
    assert re.search(r"\bstrictPort\s*:\s*true", text)


def test_transform_probe_uses_ipv4_loopback() -> None:
    text = _TRANSFORM.read_text(encoding="utf-8", errors="strict")
    assert "http://127.0.0.1:${port}/" in text
    executable = [
        line for line in text.splitlines()
        if not line.strip().startswith(("*", "//"))
    ]
    assert not any("http://localhost:${port}" in line for line in executable)
