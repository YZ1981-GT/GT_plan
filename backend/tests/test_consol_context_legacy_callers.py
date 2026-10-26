"""``ConsolContext.legacy`` 调用方守卫（spec consol-autotree-linkage-closure，2026-10-26 抓到）。

2026-10-10 起分录审批、数据集激活、调整审批后的试算表更新三处事件发布方都给 ``legacy()`` 传
``source_version``，而签名不收 ⇒ ``TypeError`` 被发布方的 ``except`` 吞掉 ⇒ 事件从未发出：
分录审批从不触发合并推送，调整审批后不发 ``TRIAL_BALANCE_UPDATED``。

两道判据：
1. 静态：全部生产代码里 ``ConsolContext.legacy(...)`` 的关键字参数 ⊆ 签名参数（AST，不看注释）；
2. 行为：分录审批接口审批后真的发出 ``ELIMINATION_APPROVED``（见 test_consol_push 的往返用例）。
"""

from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path

from app.schemas.consol_context import ConsolContext

APP = Path(__file__).resolve().parents[1] / "app"


def _legacy_calls() -> list[tuple[Path, int, set[str]]]:
    out: list[tuple[Path, int, set[str]]] = []
    for path in APP.rglob("*.py"):
        # utf-8-sig：个别路由文件带 BOM（如 note_offline.py），按 utf-8 读 ast 会报 U+FEFF
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == "legacy"
                    and isinstance(func.value, ast.Name) and func.value.id == "ConsolContext"):
                out.append((path, node.lineno, {kw.arg for kw in node.keywords if kw.arg}))
    return out


def test_every_legacy_call_uses_only_accepted_keywords():
    accepted = set(inspect.signature(ConsolContext.legacy).parameters)
    calls = _legacy_calls()
    assert len(calls) >= 3, "扫描器没找到调用方 —— 判据会空转"
    bad = [(str(p.relative_to(APP.parent)), line, sorted(kws - accepted)) for p, line, kws in calls if kws - accepted]
    assert bad == [], f"ConsolContext.legacy 收到签名之外的关键字参数（运行时 TypeError，常被 except 吞掉）：{bad}"


def test_the_three_publishers_can_build_their_contexts():
    """三处发布方的实参形态：project_id / year / source_version。"""
    pid = uuid.uuid4()
    for source in (str(uuid.uuid4()), "adjustment_approved"):
        ctx = ConsolContext.legacy(project_id=pid, year=2025, source_version=source)
        assert ctx.is_legacy and ctx.source_version == source


def test_legacy_without_source_version_stays_versionless():
    ctx = ConsolContext.legacy(uuid.uuid4(), 2025)
    assert ctx.source_version is None and ctx.tree_fingerprint is None
