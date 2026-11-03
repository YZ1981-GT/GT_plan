# -*- coding: utf-8 -*-
"""G9 的 store 投影/合并门面 —— 绑定到 G9 的多区门面（实现在 `phase5_section_store_facade`）。

spec: `g-cycle-single-region-detail-lanes` · Task 8 / C-5；spec oo-writeback-template-parity-closure R3 批 B3

═══ 为什么抽出来 ═══

主模块触到仓库的单文件行数门禁（`.git-hooks/pre-commit`，上限 800 行）。三区组合的四个 store 门面是**内聚**的一块，
抽成伴生模块（先例 `pilot_h1_store_merge.py`），主模块在文件末尾重导出，调用方按名取属性零改动。

═══ 批 B3 ═══

原实现的 `_provider()` 写死 G9，G3 / G4 / G5 / G6 又原样重导出了它 ⇒ 那四家投影 / 合并用的全是 G9 的 spec（出方向恒空、
回写一格合不进）。实现挪到按 provider 绑定的 `SectionStoreFacade`，四家各自绑定自己；本模块只剩 G9 的绑定，
G9 的行为逐字不变（同一套三区穿线，错误信息里的 entry 名改为 adapter_id）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_section_store_facade import SectionStoreFacade

__all__ = [
    "specs_for",
    "build_store_projection",
    "merge_projection_into_store_rows",
    "iter_store_rows",
    "split_store_payload_by_section",
]

_FACADE: Final[SectionStoreFacade] = SectionStoreFacade("phase5_g9_other_noncurrent")
specs_for = _FACADE.specs_for
build_store_projection = _FACADE.build_store_projection
merge_projection_into_store_rows = _FACADE.merge_projection_into_store_rows
iter_store_rows = _FACADE.iter_store_rows
split_store_payload_by_section = _FACADE.split_store_payload_by_section
