"""``BaseAdapter`` — 财务软件适配器抽象基类。

见 design.md §5.1 / Sprint 1 Task 14。

适配器的最小契约：

- ``id`` / ``display_name`` / ``priority``：注册期元数据。
- ``match(fd)``：返回 0.0-1.0 的匹配度；``GenericAdapter`` 恒回非零，保证兜底。
- ``get_column_aliases(table_type)``：返回 ``{standard_field: [alias1, alias2, ...]}``；
  只需覆盖关键列 + 次关键列，非关键列走通用模糊匹配。
- ``preprocess_rows(table_type, rows)``：可选的 vendor 特有行级处理（如用友日期序列号转换），
  默认透传。
"""

from abc import ABC, abstractmethod

from ..detection_types import FileDetection, TableType


class BaseAdapter(ABC):
    """适配器抽象基类，所有 vendor 适配器与 ``GenericAdapter`` / JSON 驱动适配器的共同父类。"""

    #: 适配器唯一标识，如 ``"yonyou"`` / ``"kingdee"`` / ``"generic"``。
    id: str = ""

    #: 面向用户展示的中文名，如 ``"用友 U8/NC/T+"``。
    display_name: str = ""

    #: 优先级，数字越大越优先参与匹配（详见 ``AdapterRegistry.register``）。
    #: ``GenericAdapter`` 固定为 0，其余建议 60-90。
    priority: int = 0

    @abstractmethod
    def match(self, fd: FileDetection) -> float:
        """返回 0.0-1.0 的匹配度。

        规则约定（见 design §26 tie-break）：文件名权重优先于列名权重，
        多文件 / 多 sheet 时可累加但需 ``min(..., 1.0)`` 夹紧。
        """

    @abstractmethod
    def get_column_aliases(self, table_type: TableType) -> dict[str, list[str]]:
        """返回 ``{standard_field: [alias, ...]}``。

        仅需定义关键列 + 次关键列的 vendor 别名；非关键列识别由
        ``GenericAdapter`` 通用模糊匹配兜底。
        """

    def preprocess_rows(
        self,
        table_type: TableType,
        rows: list[dict],
    ) -> list[dict]:
        """可选：vendor 特有的行级预处理，默认透传。"""

        return rows


__all__ = ["BaseAdapter"]
