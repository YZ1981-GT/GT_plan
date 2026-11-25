"""CATALOG.md 与磁盘实际 spec 目录的一致性守卫。

背景（2026-11-25）：`.kiro/specs/_archive/` 按开发时间批次归档（append-only），
功能域检索靠生成式 `CATALOG.md`（多维归属，一个 spec 可属多个域）。
生成器：`backend/scripts/analyze/build_spec_catalog.py`。

本守卫钉住三件事：
1. **无漂移**：`--check` 通过（spec 增删/改名/勾选变化后必须重新生成，否则红）；
2. **链接点得开**：CATALOG 里每条内部链接目标文件必须存在（防手改成死链）；
3. **统计自洽**：统计行的总数 = 活跃 + 归档，且未归类为 0。

沿用 `test_spec_index_consistency.py` 的同一纪律：生成类产物必须幂等，`--check` 才是门禁。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / ".kiro" / "specs" / "CATALOG.md"
GENERATOR = ROOT / "backend" / "scripts" / "analyze" / "build_spec_catalog.py"

pytestmark = pytest.mark.skipif(not CATALOG.exists(), reason="CATALOG.md 不存在")


def test_catalog_is_not_drifted() -> None:
    """生成器 --check 必须 exit 0（内容与磁盘一致）。"""
    assert GENERATOR.exists(), f"生成器缺失：{GENERATOR}"
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        capture_output=True,
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = (proc.stdout or b"").decode("utf-8", errors="replace") + (
        proc.stderr or b""
    ).decode("utf-8", errors="replace")
    assert proc.returncode == 0, (
        "CATALOG.md 与磁盘 spec 目录不一致（漂移）。\n"
        "修法：python backend/scripts/analyze/build_spec_catalog.py\n" + out
    )
    # 输出内容也要核对：只判 exit code 时，生成器崩溃成非 0 也可能被当成「漂移」误读
    assert "校验通过" in out, f"--check 没走到正常分支，输出：{out[:500]}"


def test_catalog_links_resolve() -> None:
    """CATALOG 内每条内部链接目标必须存在。"""
    text = CATALOG.read_text(encoding="utf-8")
    links = [lk for lk in re.findall(r"\]\(([^)]+)\)", text) if not lk.startswith("http")]
    missing = [lk for lk in links if not (CATALOG.parent / lk).exists()]
    assert not missing, f"{len(missing)} 条链接点不开，前 5：{missing[:5]}"


def test_catalog_stats_are_self_consistent() -> None:
    text = CATALOG.read_text(encoding="utf-8")
    m = re.search(
        r"全部 spec \*\*(\d+)\*\* = 活跃 \*\*(\d+)\*\* \+ 已归档 \*\*(\d+)\*\*", text
    )
    assert m, "统计行缺失或格式变了（生成器与守卫要同步）"
    total, active, archived = map(int, m.groups())
    assert total == active + archived, f"统计不自洽：{total} != {active} + {archived}"
    assert re.search(r"未归类 \*\*0\*\*", text), "存在未归类的 spec，需补规则后重新生成"


def test_catalog_domain_anchors_exist() -> None:
    """域概览表里登记的代码锚点必须真实存在（防锚点写错成幽灵路径）。"""
    text = CATALOG.read_text(encoding="utf-8")
    anchors = re.findall(r"^\| \*\*.+?\*\* \| \d+ \| `([^`]+)` \|", text, re.M)
    assert anchors, "域概览表没解析到任何锚点（判据自己要能抓到值，防空转）"
    missing = [a for a in anchors if not (ROOT / a).exists()]
    assert not missing, f"域锚点不存在：{missing}"
