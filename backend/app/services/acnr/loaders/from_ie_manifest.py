"""Loader: {cycle}_cycle_ie_manifest.yaml → import_export 段。

读取 `backend/data/acnr/sources/{cycle}_cycle_ie_manifest.yaml`，
返回 dict[sheet_code → import_export segment]。

Requirements: 1.3, 4.1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_SOURCES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "data"
    / "acnr"
    / "sources"
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class ImportExportSegment:
    """import_export 段的 plain dict 封装（方便类型提示）。"""

    __slots__ = (
        "enabled",
        "api_prefix",
        "item_id",
        "storage_field",
        "import_order",
        "depends_on_sheets",
    )

    def __init__(
        self,
        *,
        enabled: bool = True,
        api_prefix: str = "",
        item_id: str | list[str] = "",
        storage_field: str = "remark",
        import_order: int = 0,
        depends_on_sheets: list[str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.api_prefix = api_prefix
        self.item_id = item_id
        self.storage_field = storage_field
        self.import_order = import_order
        self.depends_on_sheets = depends_on_sheets or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "api_prefix": self.api_prefix,
            "item_id": self.item_id,
            "storage_field": self.storage_field,
            "import_order": self.import_order,
            "depends_on_sheets": self.depends_on_sheets,
        }


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def load_ie_manifest(
    cycle: str,
    *,
    sources_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """加载指定循环的 IE manifest，返回 {sheet_code → import_export dict}。

    Parameters
    ----------
    cycle
        循环码（小写），如 'd'。
    sources_dir
        自定义源目录（默认 backend/data/acnr/sources/）。

    Returns
    -------
    dict[str, dict]
        键为 sheet_code（如 'D2-2'），值为 import_export 段。

    Raises
    ------
    FileNotFoundError
        manifest 文件不存在时。
    """
    base = sources_dir or _SOURCES_DIR
    manifest_path = base / f"{cycle.lower()}_cycle_ie_manifest.yaml"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"IE manifest not found: {manifest_path}"
        )

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = data.get("entries", [])
    result: dict[str, dict[str, Any]] = {}

    for entry in entries:
        sheet_code = entry.get("sheet_code", "")
        if not sheet_code:
            continue

        segment = ImportExportSegment(
            enabled=True,
            api_prefix=entry.get("api_prefix", ""),
            item_id=entry.get("item_id", ""),
            storage_field=entry.get("storage_field", "remark"),
            import_order=entry.get("import_order", 0),
            depends_on_sheets=entry.get("depends_on_sheets") or [],
        )
        result[sheet_code] = segment.to_dict()

    return result
