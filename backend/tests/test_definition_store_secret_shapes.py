# -*- coding: utf-8 -*-
"""`backend/definition_store/` 的 gitleaks 路径豁免的**可伪证**背书。

═══ 为什么需要这条守卫 ═══

`.gitleaks.toml` 把 `backend/definition_store/` 整目录加进 `[allowlist].paths`，理由是
`generic-api-key` 对它是**系统性误报**：规则把契约里的业务键
（`table_key":"d4_32_groups"` / `column_key":"group_label"`）当成 `key":"<secret>"`。
实测抽样已入库 blob（HEAD 版本）同样命中 —— 286 个 contracts + 216 个 instrumentation
入库时这道门就没拦住过，不是某次提交的特例。

但「整目录豁免 + 一段理由文本」正是平台明令禁止的那种后门：加一行配置就把整个目录
从安全扫描里摘出去，之后谁往 definition payload 里塞了真凭据都不会有人知道。

所以本文件是那条豁免的**对价**：对该目录全量跑**严格锚定**的凭据形态扫描，并钉住
分母非空。真塞进凭据时这条会红，豁免也就不再成立。

═══ 为什么判据必须严格锚定（本轮实测教训）═══

首版用裸子串 `b"sk-"` 扫，报了 **9** 处"命中"。逐处读上下文才发现全部出自
`xlsx/gt-m8-general-risk-reserve` —— `ri|sk-|reserve` 的子串。裸子串口径会把
`task-` / `risk-` 这类业务词判成 OpenAI key，于是守卫要么长期假红（没人看），
要么被加一堆白名单掩盖掉。换成带边界的锚定正则后，1030 个文件 0 命中。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

#: 仓库根（本文件在 `backend/tests/` 下）。
_REPO_ROOT = Path(__file__).resolve().parents[2]
_STORE = _REPO_ROOT / "backend" / "definition_store"
_GITLEAKS_CONFIG = _REPO_ROOT / ".gitleaks.toml"

#: 真实凭据形态。每条都带前后边界 —— 见模块 docstring 的「严格锚定」一节：
#: 不带边界时 `sk-` 会命中 `risk-reserve`、`ghp_` 之类也会被业务词误触。
_CREDENTIAL_SHAPES: dict[str, re.Pattern[bytes]] = {
    "openai_or_anthropic_key": re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
    "pem_private_key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github_pat": re.compile(rb"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,}"),
    "aws_access_key_id": re.compile(rb"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![0-9A-Z])"),
    "slack_token": re.compile(rb"(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{10,}"),
    "pg_uri_with_password": re.compile(rb"postgres(?:ql)?://[^:/@\s]+:[^@\s]+@"),
}


def _store_files() -> list[Path]:
    return [path for path in _STORE.rglob("*") if path.is_file()]


def test_definition_store_exists_and_is_not_empty() -> None:
    """分母非空 —— 目录空掉时「0 命中」是假绿。"""
    assert _STORE.is_dir(), f"{_STORE} 不存在 —— 豁免的对象没了，配置该一起删"
    files = _store_files()
    assert len(files) > 100, (
        f"definition_store 只有 {len(files)} 个文件 —— 分母异常小，"
        "本守卫的「0 命中」此时不构成背书（内容寻址产物只增不减）"
    )


@pytest.mark.parametrize("shape", sorted(_CREDENTIAL_SHAPES))
def test_definition_store_carries_no_real_credential_shape(shape: str) -> None:
    """逐形态扫全目录。命中即豁免失效 —— 要么清掉凭据，要么撤掉路径豁免。"""
    pattern = _CREDENTIAL_SHAPES[shape]
    hits: list[str] = []
    for path in _store_files():
        raw = path.read_bytes()
        match = pattern.search(raw)
        if match is None:
            continue
        # 只报文件与偏移，不把命中内容打进日志（真是凭据时日志本身就成了泄漏面）。
        hits.append(f"{path.relative_to(_REPO_ROOT).as_posix()}@{match.start()}")
    assert not hits, (
        f"definition_store 出现 {shape} 形态 {len(hits)} 处：{hits[:5]} —— "
        "`.gitleaks.toml` 对该目录的路径豁免据此失效，必须先清除凭据"
    )


def test_gitleaks_config_actually_declares_the_exemption() -> None:
    """守卫与配置不得脱钩：豁免被删掉后本文件就该一起删，而不是留着空转。"""
    assert _GITLEAKS_CONFIG.is_file(), f"{_GITLEAKS_CONFIG} 不存在"
    text = _GITLEAKS_CONFIG.read_text(encoding="utf-8")
    assert "backend/definition_store/" in text, (
        ".gitleaks.toml 已不再豁免 backend/definition_store/ —— "
        "本守卫是那条豁免的对价，豁免撤销时应连同本文件一并移除，不留空转判据"
    )
