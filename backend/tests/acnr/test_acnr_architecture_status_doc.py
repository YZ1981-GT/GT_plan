r"""T32 守卫：架构提案「现状（2026-10-26）」节一致性（design §15.1 / D12）。

校验：
  1. 架构提案文档存在且含「## 现状（2026-10-26）」节。
  2. 该节声明的 registry_version 格式与 `catalog_contract.REGISTRY_VERSION_PATTERN`
     （`^\d{14}$`）逐字一致。
  3. 该节显式把旧的 `YYYY.N.N`（示例 `2026.07.10`）标为过时/勘误，而非当前有效格式。
  4. resolver 模块注释声明「唯一解析入口」（canonical resolver 定位）。

节范围 = 从「## 现状」标题行起，到下一个顶层「## 」标题行止（按标题定位，不写死行号）。

变异（在 verify_wt 做）：删该节标题 → 红（节缺失）；把节内 `^\d{14}$` 改回 `YYYY.N.N`
→ 红（版本格式不一致）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.acnr import catalog_contract as cc

_REPO = Path(__file__).resolve().parents[3]
_DOC = _REPO / "docs" / "proposals" / "address-coordinate-name-registry-architecture.md"
_RESOLVER = _REPO / "backend" / "app" / "services" / "acnr" / "resolver.py"

_STATUS_HEADING_RE = re.compile(r"^##\s*现状（2026-10-26）\s*$")
_NEXT_H2_RE = re.compile(r"^##\s+")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _status_section(text: str) -> str:
    """提取「现状（2026-10-26）」节正文（标题行到下一个顶层 ## 之前）。"""
    lines = text.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if _STATUS_HEADING_RE.match(ln.strip()):
            start = i
            break
    assert start is not None, "架构提案缺少「## 现状（2026-10-26）」节（D12 守卫）"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _NEXT_H2_RE.match(lines[j]) and not _STATUS_HEADING_RE.match(lines[j].strip()):
            end = j
            break
    return "\n".join(lines[start:end])


def test_architecture_doc_exists():
    assert _DOC.exists(), f"架构提案文档不存在：{_DOC}"


def test_status_section_present_and_nonempty():
    section = _status_section(_read(_DOC))
    # 节正文需有实质内容（标题之外 ≥ 10 行）
    body_lines = [l for l in section.split("\n")[1:] if l.strip()]
    assert len(body_lines) >= 10, "现状节内容过短，疑似被清空"


def test_status_section_version_format_matches_contract():
    """节内声明的版本格式与 catalog_contract.REGISTRY_VERSION_PATTERN 逐字一致。"""
    section = _status_section(_read(_DOC))
    pattern = cc.REGISTRY_VERSION_PATTERN  # '^\\d{14}$'
    # 节内须出现与契约逐字相等的正则字面量（反引号包裹）
    assert pattern in section, (
        f"现状节未声明与契约一致的版本格式 {pattern!r}；"
        "版本格式须与 catalog_contract.REGISTRY_VERSION_PATTERN 保持单一来源"
    )
    assert "14 位" in section and "UTC" in section, "现状节须说明 14 位 UTC 时间戳"


def test_status_section_marks_old_format_as_deprecated():
    """旧 YYYY.N.N（示例 2026.07.10）须被标为过时/勘误，不得作为当前有效格式。"""
    section = _status_section(_read(_DOC))
    # 节内若出现 2026.07.10，必须与「过时/作废/勘误」同现（在同一节里有勘误说明）
    if "2026.07.10" in section or "YYYY.N.N" in section:
        assert any(k in section for k in ("过时", "作废", "勘误", "不再使用")), (
            "现状节提到旧版本格式但未标注为过时/勘误"
        )


def test_status_section_lists_gate_and_parallel_relation():
    """现状节须覆盖门禁清单与 V1/V2/legacy 并行关系（D12 节内容要点）。"""
    section = _status_section(_read(_DOC))
    assert "门禁" in section, "现状节须列本 spec 完成后的门禁清单"
    assert "V2" in section and ("V1" in section or "legacy" in section), (
        "现状节须说明 V1/V2/legacy 并行关系"
    )


def test_resolver_module_declares_canonical_entry():
    """resolver 模块注释声明唯一解析入口（canonical resolver + legacy 委托 定位）。"""
    head = "\n".join(_read(_RESOLVER).split("\n")[:40])
    assert "唯一解析入口" in head, (
        "resolver 模块注释须声明「四大消费库的唯一解析入口」（canonical resolver 定位）"
    )
