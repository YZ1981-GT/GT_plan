"""test_confirmation_component_backend_claimed — 平台级守卫

Property 4: 前端 htmlRendererRegistry 的所有 confirmation-* componentType
必须被后端认领（在 RENDERER_DISPATCH ∪ _CONFIRMATION_COMPONENTS 之中）。
未认领的 componentType 会被 wp_render_config.py 改写成 onlyoffice-sheet，
专属组件永不渲染。

豁免须在 _EXEMPTIONS 逐条登记理由。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_FRONTEND = _BACKEND.parent / "audit-platform" / "frontend"
_REGISTRY_PATH = _FRONTEND / "src" / "components" / "workpaper" / "htmlRendererRegistry.ts"

# 后端两个认领集合
from app.routers.wp_render_strategies import RENDERER_DISPATCH

# _CONFIRMATION_COMPONENTS 在 wp_render_config.py
_WP_RENDER_CONFIG = _BACKEND / "app" / "routers" / "wp_render_config.py"


def _load_confirmation_components_from_source() -> set[str]:
    """从 wp_render_config.py 源码中提取 _CONFIRMATION_COMPONENTS 的键。"""
    src = _WP_RENDER_CONFIG.read_text(encoding="utf-8")
    # 找 _CONFIRMATION_COMPONENTS 开始到下一个 } 结束
    start = src.find("_CONFIRMATION_COMPONENTS")
    if start == -1:
        return set()
    brace_start = src.find("{", start)
    brace_end = src.find("}", brace_start)
    if brace_start == -1 or brace_end == -1:
        return set()
    block = src[brace_start:brace_end + 1]
    return set(re.findall(r'"(confirmation-[^"]+)"', block))


def _load_frontend_confirmation_types() -> set[str]:
    """从 htmlRendererRegistry.ts 的 union type 中提取所有 confirmation-* 类型。"""
    if not _REGISTRY_PATH.exists():
        pytest.skip(f"前端 registry 缺失：{_REGISTRY_PATH}")
    src = _REGISTRY_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"'(confirmation-[^']+)'", src))


# 豁免清单（必须逐条登记理由）
_EXEMPTIONS: dict[str, str] = {
    "confirmation-hub": "workbook 级 placeholder，不注册 per-sheet 组件",
}


def test_all_frontend_confirmation_types_claimed():
    """前端 confirmation-* ⊆ (RENDERER_DISPATCH ∪ _CONFIRMATION_COMPONENTS ∪ EXEMPTIONS)。"""
    frontend_types = _load_frontend_confirmation_types()
    backend_dispatch = set(RENDERER_DISPATCH.keys())
    backend_confirmation = _load_confirmation_components_from_source()
    exempted = set(_EXEMPTIONS.keys())

    claimed = backend_dispatch | backend_confirmation | exempted
    unclaimed = frontend_types - claimed

    assert not unclaimed, (
        f"以下 confirmation-* componentType 在前端注册但后端未认领（会被改写成 onlyoffice-sheet）：\n"
        f"  {sorted(unclaimed)}\n"
        f"后端 RENDERER_DISPATCH 有 {len(backend_dispatch)} 条、"
        f"_CONFIRMATION_COMPONENTS 有 {len(backend_confirmation)} 条、"
        f"豁免 {len(exempted)} 条"
    )


def test_exemptions_have_reasons():
    """每个豁免必须有非空理由。"""
    for key, reason in _EXEMPTIONS.items():
        assert reason.strip(), f"豁免 {key} 缺理由"


def test_reverse_check_removing_from_backend_would_fail():
    """反向自检：如果从后端删掉某个 confirmation-send-list-e03，本守卫要能检测出。"""
    frontend_types = _load_frontend_confirmation_types()
    assert "confirmation-send-list-e03" in frontend_types, "前端应含 confirmation-send-list-e03"
    # 模拟后端不含它
    fake_claimed = set(RENDERER_DISPATCH.keys()) - {"confirmation-send-list-e03"}
    unclaimed = frontend_types - fake_claimed - _load_confirmation_components_from_source() - set(_EXEMPTIONS)
    assert "confirmation-send-list-e03" in unclaimed, "删掉后应被检测为未认领"
