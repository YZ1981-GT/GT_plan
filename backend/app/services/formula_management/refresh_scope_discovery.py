"""全局刷新范围动态发现（RefreshScopeDiscovery）.

公式管理库（formula-management-library）Task 17.1 / 设计 §19（Req 20）。

**目的**：从平台既有来源**动态派生**可刷新范围项（``RefreshScopeItem``），
供全局刷新勾选弹窗（Req 19，前端 ``GtRefreshScopeDialog``）与后端编排
（Req 21，``DraftRefreshOrchestrator``）**共用同一发现口径**（Req 20.6），
避免前后端范围清单漂移。

**三来源动态派生 + 按 key 去重（Req 20.1 / 20.4，禁硬编码固定清单 Req 20.2）**：

    ① 模块注册固定顶层域：报表（report）/ 调整分录（adjudication）/ 附注（note）。
       这三者是平台的固定模块域（非可增长的循环清单），作为顶层可勾选项。
    ② 循环集合（cycleDialogRegistry 等价物）：``cycleDialogRegistry`` 是**前端** TS
       注册表（``frontend/src/config/cycleDialogRegistry.ts``），后端无法直接 import。
       后端可得的等价"既有循环常量"是 ``dashboard_aggregator_service.CYCLE_NAMES``
       （D~N 循环的模块注册常量，单一真源，被 Dashboard 复用）——本服务以它作为
       后端侧的注册循环集合（②），而非在此新造一份硬编码清单。
    ③ ``wp_index`` 现存 wp_code 的循环前缀：``re.match(r'([A-N])', wp_code)``。
       随项目实际底稿动态变化——新增循环的底稿一旦落 ``wp_index`` 即自动出现（Req 20.3）。

    ②③ 并集去重 → 每个循环产出一个 ``workpaper:{cycle}`` 项（Req 20.4 循环粒度 + 去重）。

**只读**：本服务仅读 ``wp_index``，无任何写入（service 只 flush，本服务不 flush 不 commit）。
``wp_index`` 是**项目级**（无 year / 无 dataset_id 列），故不经 ``get_active_filter``
（其要求四表的 year + dataset 语义）；沿用既有 ``wp_progress_service`` 口径以
``is_deleted == False`` 过滤。``year`` 参数保留用于与 ``/draft-refresh`` 共用签名口径。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpIndex
from app.services.dashboard_aggregator_service import CYCLE_NAMES

logger = logging.getLogger(__name__)

# ── ① 模块注册固定顶层域（Req 20.1）──────────────────────────────────────────
# 平台固定模块域（非可增长的循环清单），(key, 中文标签) 顺序即弹窗顶层展示顺序。
_TOP_LEVEL_DOMAINS: list[tuple[str, str]] = [
    ("report", "报表"),
    ("adjudication", "调整分录"),
    ("note", "附注"),
]

# ③ wp_code 循环前缀提取（设计 §19 明确口径：re.match(r'([A-N])', wp_code)）。
_CYCLE_PREFIX_RE = re.compile(r"([A-N])")


@dataclass
class RefreshScopeItem:
    """一个可勾选刷新范围项（Req 20.4）。

    Attributes:
        key: 范围键（去重主键）：``report`` / ``adjudication`` / ``note`` /
            ``workpaper:{cycle}``（如 ``workpaper:D``）。
        label: 中文标签：报表 / 调整分录 / 附注 / 底稿·循环D。
        group: 顶层域：``report`` | ``adjudication`` | ``note`` | ``workpaper``。
        cycle: workpaper 域的循环字母（A..N），其余顶层域为 ``None``。
    """

    key: str
    label: str
    group: str
    cycle: str | None = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "group": self.group,
            "cycle": self.cycle,
        }


class RefreshScopeDiscovery:
    """从三来源动态发现可刷新范围项（Req 20）。

    单一实现供弹窗（Req 19）与后端编排（Req 21）共用，避免清单漂移（Req 20.6）。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def discover(self, *, project_id: UUID, year: int) -> list[RefreshScopeItem]:
        """动态派生可刷新项并按 ``key`` 去重（Req 20.1 / 20.4，禁硬编码 Req 20.2）。

        Args:
            project_id: 目标项目。
            year: 目标年度（保留用于与 ``/draft-refresh`` 共用签名口径；``wp_index``
                为项目级无 year 列，故不参与其过滤）。

        Returns:
            去重后的 ``RefreshScopeItem`` 列表：先固定顶层域，再按循环字母排序的
            ``workpaper:{cycle}`` 项。
        """
        items: list[RefreshScopeItem] = []
        seen: set[str] = set()

        def _add(item: RefreshScopeItem) -> None:
            if item.key in seen:
                return
            seen.add(item.key)
            items.append(item)

        # ── ① 模块注册固定顶层域（报表 / 调整分录 / 附注）──────────────────────
        for key, label in _TOP_LEVEL_DOMAINS:
            _add(RefreshScopeItem(key=key, label=label, group=key, cycle=None))

        # ── ② 后端注册循环常量集合（cycleDialogRegistry 后端等价物）────────────
        cycles: set[str] = {c.upper() for c in CYCLE_NAMES.keys() if c}

        # ── ③ wp_index 现存 wp_code 循环前缀（随项目动态变化）──────────────────
        rows = await self.db.execute(
            sa.select(WpIndex.wp_code)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == sa.false(),
            )
            .distinct()
        )
        for (wp_code,) in rows.all():
            if not wp_code:
                continue
            m = _CYCLE_PREFIX_RE.match(str(wp_code).upper())
            if m:
                cycles.add(m.group(1))

        # ②③ 并集 → 每循环产一个 workpaper:{cycle} 项（按字母排序，稳定输出）。
        for cycle in sorted(cycles):
            name = CYCLE_NAMES.get(cycle)
            label = f"底稿·循环{cycle}" + (f"（{name}）" if name else "")
            _add(
                RefreshScopeItem(
                    key=f"workpaper:{cycle}",
                    label=label,
                    group="workpaper",
                    cycle=cycle,
                )
            )

        return items
