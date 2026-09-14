"""D-cycle 四表库提取（Tier B 预填 + Tier A 公式）服务包.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/

- anchor_registry: 锚点登记表加载 + 合法性校验（Wave 0 / Task 1.2）。
- prefill: Tier B 审定表预填通用范式（Wave 0 / Task 1.3）。
- presets: Tier A 提取公式预设库 + 读时收敛（Wave 0 / Task 1.3）。
- tier_a_seed: Tier A render transient seed 共享助手（Wave 3/4，D6→D1-D7 复用）。
"""

from app.services.d_cycle_extraction.anchor_registry import (
    is_known_anchor,
    known_anchors,
)
from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill
from app.services.d_cycle_extraction.presets import (
    load_presets,
    resolve_effective,
)
from app.services.d_cycle_extraction.tier_a_seed import (
    seed_tier_a_reconciliation,
)

__all__ = [
    "known_anchors",
    "is_known_anchor",
    "build_d_adjudication_prefill",
    "load_presets",
    "resolve_effective",
    "seed_tier_a_reconciliation",
]
