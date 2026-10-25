# -*- coding: utf-8 -*-
"""A5-1 canary 端到端接通链守卫（componentType 路由 + 专属组件挂载）。

spec: a-cycle-sync-foundation-and-first-canary

本轮真栈排查发现：capability/契约/adapter 全就绪后，专属组件**仍未挂载** ——
根因是两处路由配置，二者缺一即 fallback 到通用渲染器（univer → onlyoffice-sheet）：

1. wp_code_overrides.json 的 A5-1 原为 "skip"（显式禁用专属组件）
2. DEDICATED_COMPONENT_TYPES 未含 5-1-cashflow-audit
   ⇒ 多 sheet 底稿走 wp_render_config L796 的整册路由判断时不命中，
     逐 sheet 按 class_code 派生成 univer，再被 L891 重写为 onlyoffice-sheet。

🔴 这两处与 capability/契约/台账是**正交**的第五、第六个要件。前四个全绿仍会
「后端说 bidirectional、前端挂通用渲染器」—— 本文件把这条链钉住。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CANARY_WP_CODE = "A5-1"
_CANARY_COMPONENT_TYPE = "a5-1-cashflow-audit"
_CANARY_HOST = "GtA51CashflowAudit.vue"


class TestCanaryComponentTypeRouting:
    """专属组件路由的六要件里的第 5、6 条。"""

    def test_wp_code_override_is_not_skip(self) -> None:
        """A5-1 的 override 必须是 componentType，不能是 skip。"""
        p = _BACKEND / "app" / "data" / "wp_code_overrides.json"
        d = json.loads(p.read_bytes())
        val = d.get(_CANARY_WP_CODE)
        assert val == _CANARY_COMPONENT_TYPE, (
            f"A5-1 override 应为 {_CANARY_COMPONENT_TYPE!r}，实际 {val!r} —— "
            f"skip 会让专属组件永不挂载（fallback 到 univer/onlyoffice-sheet）"
        )

    def test_component_type_in_whole_wp_dedicated_set(self) -> None:
        """多 sheet 整册路由集合必须含它，否则逐 sheet 按 class_code 拆散。"""
        from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES

        assert _CANARY_COMPONENT_TYPE in DEDICATED_COMPONENT_TYPES, (
            f"{_CANARY_COMPONENT_TYPE} 不在 DEDICATED_COMPONENT_TYPES ⇒ "
            f"A5-1 的 8 个 sheet 会被逐个按 class_code 派生成 univer"
        )

    def test_component_type_is_valid(self) -> None:
        """componentType 须在后端 VALID 域内。"""
        t = (_BACKEND / "app" / "services" / "wp_classification_service.py").read_text(
            encoding="utf-8", errors="replace"
        )
        i = t.find("VALID_COMPONENT_TYPES")
        assert i != -1, "找不到 VALID_COMPONENT_TYPES"
        assert _CANARY_COMPONENT_TYPE in t[i:i + 12000], (
            f"{_CANARY_COMPONENT_TYPE} 不在 VALID_COMPONENT_TYPES"
        )

    def test_frontend_registry_maps_to_host(self) -> None:
        """前端 registry 必须把 componentType 映射到改线后的宿主。"""
        entries = (
            _ROOT / "audit-platform" / "frontend" / "src" / "components"
            / "workpaper" / "registry" / "entries" / "programs.ts"
        )
        t = entries.read_text(encoding="utf-8", errors="replace")
        i = t.find(f"componentType: '{_CANARY_COMPONENT_TYPE}'")
        assert i != -1, f"programs.ts 里没有 {_CANARY_COMPONENT_TYPE} 条目"
        seg = t[i:i + 400]
        assert _CANARY_HOST in seg, (
            f"{_CANARY_COMPONENT_TYPE} 应映射到 {_CANARY_HOST}，实际段落: {seg[:200]}"
        )

    def test_host_is_rewired_to_sync_bridge(self) -> None:
        """挂载的宿主必须是改线后的版本（sync bridge 而非 legacy）。"""
        host = (
            _ROOT / "audit-platform" / "frontend" / "src" / "components"
            / "workpaper" / _CANARY_HOST
        )
        src = host.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<template\b[^>]*>(.*)</template>", src, re.S)
        tmpl = m.group(1) if m else ""
        assert "WorkpaperSyncEditorHost" in tmpl, "宿主 template 应含 sync bridge 挂点"
        assert "<GtOnlyOfficeSheet" not in tmpl, "宿主 template 不应再有 legacy 挂点"
        assert "useA51SyncMode" in src, "宿主应用 useA51SyncMode"
