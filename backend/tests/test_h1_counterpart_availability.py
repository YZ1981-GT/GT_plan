"""H1 折旧对方科目可用性探测（Req3.4）+ 宁缺勿造契约（Req8.1）."""
from __future__ import annotations

import types
from pathlib import Path

import pytest

from app.routers.wp_render_strategies import _h1_fixed_assets as h1


class _Row:
    def __init__(self, total, filled):
        self.total = total
        self.filled = filled


class _FakeResult:
    def __init__(self, one):
        self._one = one

    def fetchone(self):
        return self._one


class _FakeDb:
    def __init__(self, one=None, raise_exc=False):
        self._one = one
        self._raise = raise_exc

    async def execute(self, *_a, **_k):
        if self._raise:
            raise RuntimeError("db down")
        return _FakeResult(self._one)


def _ctx(db):
    return types.SimpleNamespace(db=db, project_id="p1", year=2025, wp_id="wp1")


@pytest.fixture(autouse=True)
def _patch_filter(monkeypatch):
    async def _fake_filter(*_a, **_k):
        return True

    monkeypatch.setattr(h1, "get_active_filter", _fake_filter)


@pytest.mark.asyncio
async def test_zero_fill_rate_not_available():
    out = await h1._probe_counterpart_availability(_ctx(_FakeDb(_Row(1000, 0))))
    assert out["available"] is False
    assert out["fill_rate"] == 0.0
    assert "填充率" in out["reason"]


@pytest.mark.asyncio
async def test_real_world_9_percent_not_available():
    """真实账套实证：1519 行中仅 135 行有对方科目 → 不可用。"""
    out = await h1._probe_counterpart_availability(_ctx(_FakeDb(_Row(1519, 135))))
    assert out["available"] is False
    assert out["fill_rate"] == pytest.approx(0.0889, abs=1e-4)
    assert out["total_lines"] == 1519
    assert "合并记账" in out["reason"]


@pytest.mark.asyncio
async def test_high_fill_rate_available():
    out = await h1._probe_counterpart_availability(_ctx(_FakeDb(_Row(1000, 950))))
    assert out["available"] is True
    assert out["fill_rate"] == 0.95
    assert out["reason"] == ""


@pytest.mark.asyncio
async def test_no_depreciation_lines_not_available():
    out = await h1._probe_counterpart_availability(_ctx(_FakeDb(_Row(0, 0))))
    assert out["available"] is False
    assert "无累计折旧" in out["reason"]


@pytest.mark.asyncio
async def test_probe_fail_open_on_db_error():
    out = await h1._probe_counterpart_availability(_ctx(_FakeDb(raise_exc=True)))
    assert out["available"] is False
    assert out["fill_rate"] == 0.0


def _code_only(path: Path) -> str:
    """剥离注释与字符串字面量，只留可执行代码（注释里提及表名不算违规）。"""
    import io
    import tokenize

    kept: list[str] = []
    with io.open(path, "r", encoding="utf-8") as fh:
        for tok in tokenize.generate_tokens(fh.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(tok.string)
    return " ".join(kept)


def test_h1_render_does_not_read_tb_aux_balance():
    """宁缺勿造（Req8.1）：tb_aux_balance 无资产卡片维度，H1 不得以它作明细取数来源。"""
    code = _code_only(Path(h1.__file__))
    assert "TbAuxBalance" not in code
    assert "tb_aux_balance" not in code
