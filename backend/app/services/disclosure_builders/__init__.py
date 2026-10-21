"""后端披露表 payload builder 注册入口。

import 本包时自动注册所有已实现的 builder 到
``disclosure_payload_builder_service._BUILDER_REGISTRY``。

spec: backend-disclosure-payload-builder Phase 2~4
"""
# Phase 2：核心 8 科目（专用 builder）
from app.services.disclosure_builders import e1_builder as _e1  # noqa: F401
from app.services.disclosure_builders import d1_builder as _d1  # noqa: F401
from app.services.disclosure_builders import d2_builder as _d2  # noqa: F401
from app.services.disclosure_builders import f2_builder as _f2  # noqa: F401
from app.services.disclosure_builders import h1_builder as _h1  # noqa: F401
from app.services.disclosure_builders import i1_builder as _i1  # noqa: F401
from app.services.disclosure_builders import g7_builder as _g7  # noqa: F401
from app.services.disclosure_builders import k1_builder as _k1  # noqa: F401

# Phase 3~4：标准两字段 builder 批量注册（70 个科目）
from app.services.disclosure_builders import standard_builder as _std  # noqa: F401
