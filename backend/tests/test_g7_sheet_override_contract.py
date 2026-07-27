"""G7 三册 sheet → wp_code_overrides 覆盖契约（P2-6）。

背景：G7 三个工作簿（main / method / subsidiary）靠 `wp_code_overrides.json` 的
41 条精确映射把 wp_code 路由到各自 componentType。若新增/改名 sheet 忘记加 override，
render-config 会静默落通用兜底渲染（noRendererGridFallback / d-form-table），不报错。

本契约锁定：每册 render 策略 SHEETS 中**编码型 sheet**（G7-N）都必须在
`wp_code_overrides.json` 有映射且指向本册 componentType。附注/底稿目录等非编码 sheet
靠 sheetName override，不在本契约范围（另有 sheetName 精确 override 覆盖）。
"""

import json
import re
from pathlib import Path

import pytest

from app.routers.wp_render_strategies._g7_long_term_equity_main import G7_MAIN_SHEETS
from app.routers.wp_render_strategies._g7_long_term_equity_method import (
    G7_EQUITY_METHOD_SHEETS,
)
from app.routers.wp_render_strategies._g7_long_term_equity_subsidiary import (
    G7_SUBSIDIARY_SHEETS,
)

_CODE_RE = re.compile(r"^G7-\d+$")


def _load_overrides() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "app" / "data" / "wp_code_overrides.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping = data.get("wp_code_overrides", data)
    return {k: v for k, v in mapping.items() if isinstance(v, str)}


@pytest.mark.parametrize(
    ("sheets", "component_type"),
    [
        (G7_MAIN_SHEETS, "g7-long-term-equity-main"),
        (G7_EQUITY_METHOD_SHEETS, "g7-long-term-equity-method"),
        (G7_SUBSIDIARY_SHEETS, "g7-long-term-equity-subsidiary"),
    ],
)
def test_g7_coded_sheets_have_override(sheets, component_type):
    """每个编码型 sheet 的 code 在 overrides 中映射到本册 componentType。"""
    overrides = _load_overrides()
    coded = [s["code"] for s in sheets if _CODE_RE.match(str(s.get("code", "")))]
    assert coded, f"{component_type} 未提取到任何编码型 sheet"
    for code in coded:
        assert code in overrides, f"{code} 缺少 wp_code_overrides 映射（会静默落通用兜底）"
        assert overrides[code] == component_type, (
            f"{code} 映射到 {overrides[code]}，应为 {component_type}"
        )


def test_g7_override_component_types_are_registered():
    """overrides 中所有 g7-* 目标 componentType 均在 RENDERER_DISPATCH 注册。"""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    overrides = _load_overrides()
    g7_types = {v for v in overrides.values() if v.startswith("g7-long-term-equity")}
    assert g7_types == {
        "g7-long-term-equity-main",
        "g7-long-term-equity-method",
        "g7-long-term-equity-subsidiary",
    }
    for ct in g7_types:
        assert ct in RENDERER_DISPATCH, f"{ct} 未在 RENDERER_DISPATCH 注册"
