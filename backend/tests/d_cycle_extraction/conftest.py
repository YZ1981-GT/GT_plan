"""d_cycle_extraction 测试公共夹具。

``presets.resolve_effective`` 自 formula-grammar-resolver-unification ADR-FGR-08 起经
``wp_effective.effective_cell_formulas`` 读有效定义（本项目 > 全局），不再直查 ``wp_formula``。
本目录的假会话只预置「用户 wp_formula 行」（``_formulas`` / ``user_formulas``），不模拟
``_load`` 的三段查询与保存点 ⇒ 这里把 ``effective_cell_formulas`` 换成：有预置行的假会话
走生产纯函数 ``project_cell_formulas``（停用判定与生产同一份），其余会话照常调用真实实现。
"""
from __future__ import annotations

import pytest

import app.services.formula_settings.wp_effective as wp_effective

_REAL = wp_effective.effective_cell_formulas


def _fake_rows(db):
    for attr in ("_formulas", "user_formulas"):
        rows = getattr(db, attr, None)
        if isinstance(rows, list):
            return rows
    return None


@pytest.fixture(autouse=True)
def _effective_from_fake_session(monkeypatch):
    async def _effective(db, project_id, wp_id, *, include_disabled=False):
        rows = _fake_rows(db)
        if rows is None:
            return await _REAL(db, project_id, wp_id, include_disabled=include_disabled)
        return None, wp_effective.project_cell_formulas(rows, include_disabled=include_disabled)

    monkeypatch.setattr(wp_effective, "effective_cell_formulas", _effective)
