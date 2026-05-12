"""``GenericAdapter`` — 通用兜底适配器。

见 design.md §5 / Sprint 1 Task 18。

职责：

- ``id = "generic"`` / ``priority = 0``（最低，真正没匹配上时才命中）。
- ``match(fd)`` 恒返回 0.1：非零保证它在空 registry 时也能当选；同时
  远低于任何 vendor 适配器（建议 60-90），不会与 vendor 误抢。
- ``get_column_aliases(table_type)`` 复用 ``identifier.default_aliases()``
  的全量通用别名（与识别层 Level 2 所用的 ``HEADER_ALIASES`` 同源），
  作为 vendor 未覆盖时的通用映射真源。
- ``preprocess_rows`` 走 ``BaseAdapter`` 默认透传。

实际的子串包含 / Levenshtein 模糊匹配算法已在 ``identifier._match_header``
中实装，此处不再重复实现——``GenericAdapter`` 只承担"提供别名数据"的
职责，匹配引擎由识别层统一驱动。
"""

from ..detection_types import FileDetection, TableType
from ..identifier import default_aliases
from .base import BaseAdapter


class GenericAdapter(BaseAdapter):
    """兜底适配器：永远返回正分，通用别名走 ``identifier.HEADER_ALIASES``。"""

    id = "generic"
    display_name = "通用兜底（Generic）"
    priority = 0

    def match(self, fd: FileDetection) -> float:  # noqa: ARG002 - 恒定分值
        # 返回一个非零小数：空 registry 场景下 ``detect_best`` 仍能挑到兜底；
        # 任何 priority > 0 的 vendor 适配器若 match > 0 都会胜出。
        return 0.1

    def get_column_aliases(self, table_type: TableType) -> dict[str, list[str]]:  # noqa: ARG002
        """返回通用默认别名映射。

        ``table_type`` 参数保留接口一致性；当前通用别名不分表类型
        （identifier 层按 ``KEY_COLUMNS`` / ``RECOMMENDED_COLUMNS`` 决定
        每个别名在具体表类型下的分层归属）。
        """

        return default_aliases()


__all__ = ["GenericAdapter"]
