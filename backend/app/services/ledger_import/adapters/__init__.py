"""``AdapterRegistry`` — 财务软件适配器注册中心。

见 design.md §5.3 / Sprint 1 Tasks 14 / 18 / 19。

职责：

- ``AdapterRegistry.register(adapter)``：按 ``-priority`` + 插入顺序（稳定）
  排序，同 ``id`` 的后注册者覆盖前者（idempotent）。
- ``AdapterRegistry.detect_best(fd)``：按 ``match()`` 选最高分适配器；
  ``GenericAdapter`` 作为兜底始终存在，保证返回值非 None。
- ``AdapterRegistry.reload_from_json(directory)``：扫描 ``*.json``（跳过
  ``_*.json``），为每个 JSON 构造 ``JsonDrivenAdapter`` 并注册；返回加载文件数。
  格式非法时打 warning 并跳过，不抛异常。
- 模块级单例 ``registry``：import 时自动注册 ``GenericAdapter``。

vendor 适配器（用友 / 金蝶 / SAP / Oracle / 浪潮 / 新中大 / SAP B1）的
注册由各自的模块（``yonyou.py`` / ``kingdee.py`` / ...）在 Sprint 1 Tasks 15-17
完成后加入；届时它们应在各自文件末尾调用 ``registry.register(...)``。
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Union

from ..detection_types import FileDetection, TableType
from .base import BaseAdapter
from .generic import GenericAdapter

logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# JSON-driven adapter
# ---------------------------------------------------------------------------


class JsonDrivenAdapter(BaseAdapter):
    """基于 JSON 定义动态构造的适配器（见 ``backend/data/ledger_adapters/*.json``）。

    JSON schema 摘要（完整见 ``backend/data/ledger_adapters/_schema.md``）：

    .. code-block:: json

        {
          "id": "yonyou",
          "display_name": "用友 U8/NC/T+",
          "priority": 80,
          "match_patterns": {
            "filename_regex": ["(?i)(用友|UFIDA|U8|NC\\\\d|T\\\\+)"],
            "signature_columns": {
              "balance": ["科目编码", "科目名称", "方向", "年初余额"],
              "ledger":  ["凭证日期", "凭证号", "摘要", "科目"]
            }
          },
          "column_aliases": {
            "balance": { "account_code": ["科目编码", "科目代码"] },
            "ledger":  { "voucher_date": ["凭证日期", "制单日期"] }
          }
        }

    打分（``match``）：

    - filename 命中任一 ``filename_regex`` → +0.5（多个命中不累加）
    - headers 与 ``signature_columns[table_type]`` 的交集比例 × 0.5
      （每个 sheet 的 table_type 独立计算，多 sheet 取最高）
    - 上限 1.0
    """

    def __init__(self, definition: dict) -> None:
        self.id = str(definition.get("id", "")).strip()
        self.display_name = str(definition.get("display_name", "")).strip()

        prio = definition.get("priority", 0)
        try:
            self.priority = int(prio)
        except (TypeError, ValueError):
            self.priority = 0

        match_patterns = definition.get("match_patterns") or {}
        raw_filename_regex = match_patterns.get("filename_regex") or []
        self._filename_patterns: list[re.Pattern[str]] = []
        for pat in raw_filename_regex:
            try:
                self._filename_patterns.append(re.compile(str(pat)))
            except re.error as exc:
                logger.warning(
                    "JsonDrivenAdapter %s: invalid filename_regex %r: %s",
                    self.id,
                    pat,
                    exc,
                )

        sig_cols = match_patterns.get("signature_columns") or {}
        self._signature_columns: dict[str, set[str]] = {}
        for tt, cols in sig_cols.items():
            if isinstance(cols, list):
                self._signature_columns[str(tt)] = {
                    str(c).strip()
                    for c in cols
                    if c is not None and str(c).strip()
                }

        col_aliases = definition.get("column_aliases") or {}
        self._column_aliases: dict[str, dict[str, list[str]]] = {}
        for tt, field_map in col_aliases.items():
            if not isinstance(field_map, dict):
                continue
            normalized: dict[str, list[str]] = {}
            for field, aliases in field_map.items():
                if isinstance(aliases, list):
                    normalized[str(field)] = [
                        str(a) for a in aliases if a is not None and str(a)
                    ]
            self._column_aliases[str(tt)] = normalized

    def match(self, fd: FileDetection) -> float:
        score = 0.0

        # Filename
        for pat in self._filename_patterns:
            if pat.search(fd.file_name or ""):
                score += 0.5
                break

        # Signature columns (across sheets; take max intersection ratio)
        if self._signature_columns and fd.sheets:
            best_ratio = 0.0
            for sheet in fd.sheets:
                sig_for_type = self._signature_columns.get(sheet.table_type)
                if not sig_for_type:
                    continue
                headers = {
                    (m.column_header or "").strip()
                    for m in sheet.column_mappings
                    if m.column_header
                }
                if not headers:
                    continue
                intersection = headers & sig_for_type
                ratio = len(intersection) / len(sig_for_type)
                if ratio > best_ratio:
                    best_ratio = ratio
            score += 0.5 * best_ratio

        return min(score, 1.0)

    def get_column_aliases(self, table_type: TableType) -> dict[str, list[str]]:
        bucket = self._column_aliases.get(table_type, {})
        # Defensive copy of inner lists to keep caller mutations isolated.
        return {field: list(aliases) for field, aliases in bucket.items()}



# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class AdapterRegistry:
    """按 ``-priority`` + 插入顺序稳定排序的适配器注册表。"""

    def __init__(self) -> None:
        self._adapters: list[BaseAdapter] = []
        # 单调递增的插入序号，用于 priority 相同时的稳定 tie-break
        self._insert_counter: int = 0
        self._insert_order: dict[str, int] = {}

    # ---- CRUD -------------------------------------------------------------

    def register(self, adapter: BaseAdapter) -> None:
        """注册 / 替换适配器（按 ``adapter.id`` idempotent）。

        同 ``id`` 再注册等价于"替换"：保留原插入顺序，避免同一模块
        重复 import 导致列表膨胀或排序抖动。
        """

        if not adapter.id:
            raise ValueError("adapter.id must be non-empty")

        existing_index: Optional[int] = None
        for i, a in enumerate(self._adapters):
            if a.id == adapter.id:
                existing_index = i
                break

        if existing_index is not None:
            self._adapters[existing_index] = adapter
            # Keep original insertion order; no counter bump.
        else:
            self._adapters.append(adapter)
            self._insert_order[adapter.id] = self._insert_counter
            self._insert_counter += 1

        self._resort()

    def unregister(self, adapter_id: str) -> bool:
        """从注册表移除指定适配器，返回是否真实移除。"""

        for i, a in enumerate(self._adapters):
            if a.id == adapter_id:
                del self._adapters[i]
                self._insert_order.pop(adapter_id, None)
                return True
        return False

    def all(self) -> list[BaseAdapter]:
        """返回当前排序的适配器列表（副本，调用方修改不影响内部状态）。"""

        return list(self._adapters)

    def get(self, adapter_id: str) -> Optional[BaseAdapter]:
        for a in self._adapters:
            if a.id == adapter_id:
                return a
        return None

    # ---- Detection --------------------------------------------------------

    def detect_best(self, fd: FileDetection) -> tuple[BaseAdapter, float]:
        """选择最佳适配器（分数最高；``GenericAdapter`` 兜底）。

        Tie-break：分数相同时按当前排序靠前者胜出（即 priority 高者 /
        同 priority 时先注册者）。
        """

        if not self._adapters:
            # 理论上不会发生（模块加载时已注册 GenericAdapter），兜底仍给一个
            fallback = GenericAdapter()
            return fallback, fallback.match(fd)

        best_adapter = self._adapters[0]
        best_score = best_adapter.match(fd)

        for adapter in self._adapters[1:]:
            score = adapter.match(fd)
            if score > best_score:
                best_adapter = adapter
                best_score = score

        return best_adapter, best_score

    # ---- Hot reload from JSON directory -----------------------------------

    def reload_from_json(self, directory: Union[Path, str]) -> int:
        """从目录扫描 ``*.json`` 外置适配器定义，注册为 ``JsonDrivenAdapter``。

        - 跳过以 ``_`` 开头的文件（保留 ``_schema.md`` / ``_notes.json`` 作文档用）
        - 格式非法（JSON 解析错 / 缺 id）时打 warning 并跳过，不抛异常
        - 返回成功加载的文件数

        目录不存在时返回 0（打 warning），便于在 CI 环境无此目录时不挂。
        """

        path = Path(directory)
        if not path.exists() or not path.is_dir():
            logger.warning(
                "AdapterRegistry.reload_from_json: directory %s does not exist",
                path,
            )
            return 0

        count = 0
        for json_path in sorted(path.glob("*.json")):
            if json_path.name.startswith("_"):
                continue
            try:
                with json_path.open("r", encoding="utf-8") as fh:
                    definition = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "AdapterRegistry.reload_from_json: failed to parse %s: %s",
                    json_path,
                    exc,
                )
                continue

            if not isinstance(definition, dict):
                logger.warning(
                    "AdapterRegistry.reload_from_json: %s top-level is not an object",
                    json_path,
                )
                continue
            if not str(definition.get("id", "")).strip():
                logger.warning(
                    "AdapterRegistry.reload_from_json: %s missing 'id' field",
                    json_path,
                )
                continue

            try:
                adapter = JsonDrivenAdapter(definition)
                self.register(adapter)
                count += 1
            except Exception as exc:  # noqa: BLE001 - 防御式，单个文件不影响整体
                logger.warning(
                    "AdapterRegistry.reload_from_json: failed to register %s: %s",
                    json_path,
                    exc,
                )

        return count

    # ---- Internal ---------------------------------------------------------

    def _resort(self) -> None:
        """按 ``(-priority, insert_order)`` 稳定排序。"""

        self._adapters.sort(
            key=lambda a: (-a.priority, self._insert_order.get(a.id, 0))
        )


# ---------------------------------------------------------------------------
# Module-level singleton — GenericAdapter 在 import 期即可用
# ---------------------------------------------------------------------------

registry = AdapterRegistry()
registry.register(GenericAdapter())

# ---------------------------------------------------------------------------
# Vendor adapters (Sprint 1 Tasks 15-17) — 在此统一注册，避免 vendor 文件副作用
# import 带来的循环依赖与注册顺序不稳定。
# ---------------------------------------------------------------------------

from .inspur import InspurAdapter  # noqa: E402
from .kingdee import KingdeeAdapter  # noqa: E402
from .newgrand import NewgrandAdapter  # noqa: E402
from .oracle import OracleAdapter  # noqa: E402
from .sap import SapAdapter  # noqa: E402
from .yonyou import YonyouAdapter  # noqa: E402

for _adapter_cls in (
    YonyouAdapter,
    KingdeeAdapter,
    SapAdapter,
    OracleAdapter,
    InspurAdapter,
    NewgrandAdapter,
):
    registry.register(_adapter_cls())


__all__ = [
    "AdapterRegistry",
    "JsonDrivenAdapter",
    "registry",
    "YonyouAdapter",
    "KingdeeAdapter",
    "SapAdapter",
    "OracleAdapter",
    "InspurAdapter",
    "NewgrandAdapter",
]
