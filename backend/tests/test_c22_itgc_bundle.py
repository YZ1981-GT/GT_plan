"""C22 IT 一般控制测试聚合组件 — 注册契约测试.

Spec: .kiro/specs/c22-itgc-bundle/ Task 2.3
Validates: Requirements 1.2, 1.4, 2.1, 2.2

mirror 自 test_c1_entity_control.py 模式：
断言 C22 wp_code_overrides 映射 → c22-itgc-bundle，
C21 / C21-1 映射 → skip（并入本 bundle 的 IT 专业成员 / 发现汇总 Tab），
componentType c22-itgc-bundle ∈ VALID_COMPONENT_TYPES，
已注册于 RENDERER_DISPATCH（Task 4.1 起，整册专属渲染策略 render_c22_itgc），
并加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由到 bundle，前端按 sheetName 分发），
且完整线上 overrides 经 validate_overrides 校验通过。

注：C22 为单一 34-sheet 工作簿（C1 模式，非 a17/s34 兄弟加载单入口 bundle）。
跨 sheet 分发靠 _WHOLE_WP_MULTISHEET_DEDICATED + render_c22_itgc 轻量策略，
避免多 sheet dispatch 把各 sheet 重写为 onlyoffice-sheet（铁律：专属组件必须注册）。
"""

import json
from pathlib import Path

C22_COMPONENT_TYPE = "c22-itgc-bundle"


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_c22_overrides_mapping():
    """C22 在 wp_code_overrides 中映射到聚合组件 c22-itgc-bundle."""
    data = _load_overrides()
    assert data.get("C22") == C22_COMPONENT_TYPE


def test_c21_and_c21_1_mapped_to_skip():
    """C21 / C21-1 映射为 skip（并入 bundle 的 IT 专业成员 / 发现汇总 Tab，不作独立条目）."""
    data = _load_overrides()
    # C21-1 wp_code 需按编码精确匹配（源模板文件名含双空格、主 sheet 名含空格，
    # 解析 wp_id 时按 wp_code=C21-1 而非 sheet 名匹配，见 phase0-notes D10）
    assert data.get("C21") == "skip"
    assert data.get("C21-1") == "skip"


def test_c22_in_valid_component_types():
    """c22-itgc-bundle 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert C22_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_c22_registered_in_dispatch():
    """c22-itgc-bundle 已注册于 RENDERER_DISPATCH（整册专属渲染策略）.

    确保多 sheet dispatch 循环能命中 render_c22_itgc，返回轻量 html_data，
    而非把 C22 各 sheet 重写为 onlyoffice-sheet。
    """
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert C22_COMPONENT_TYPE in RENDERER_DISPATCH


def test_c22_in_whole_wp_multisheet_dedicated():
    """c22-itgc-bundle 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）.

    C22 为单一 34-sheet 工作簿，所有 sheet 统一路由到 bundle，
    由前端 GtC22ItgcBundle 按 sheetName / 分组页签内部分发。
    """
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert C22_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


def test_validate_overrides_passes_for_c22():
    """validate_overrides 对 C22/C21/C21-1 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # 本 bundle 的三条映射单独校验通过，不 raise
    validate_overrides(
        {"C22": C22_COMPONENT_TYPE, "C21": "skip", "C21-1": "skip"}
    )

    # 完整线上 overrides 整体校验通过（含 C22 新映射）
    validate_overrides(_load_overrides())
