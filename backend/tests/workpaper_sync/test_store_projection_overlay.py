"""store-projection materialize-ready overlay 守卫（G4 host 迁移前置）。

行为判据：纯 store 缺脚手架键时，叠加基线后必须带上基线键；store 非空值覆盖基线；
基线没有且值为 None 的占位被丢弃（G7 矩阵坑）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.projection_first_publication import (
    overlay_store_on_baseline_projection,
)


def _fv(key: str, value: Any, *, row_key: str | None = None) -> FieldValue:
    return FieldValue(
        stable_key=key,
        value=value,
        value_type=ValueType.text,
        mode=FieldMode.editable,
        row_key=row_key,
    )


def _proj(values: dict[str, FieldValue], *, rows: dict[str, tuple[str, ...]] | None = None) -> Projection:
    return Projection(
        contract_id="d2.receivable_detail",
        semantic_version="1.0.0",
        document_type="xlsx",
        values=values,
        row_keys=rows or {},
    )


class TestOverlayStoreOnBaselineProjection:
    def test_baseline_scaffold_keys_survive_when_absent_from_store(self) -> None:
        """当 store 声明了 row_keys，以 store 为准（权威）。

        baseline 中的脚手架行（GTROW）不随投影保留——它们由 materialize 的 identity
        carrier 机制自动处理。2026-09-28 D4-2 事故形态：旧 substrate 带入全部旧行
        identity，导致 materialize 写 33 行进 12 行模板 → 大量空行 / 旧数据残留。
        """
        baseline = _proj(
            {
                "receivable_detail_rows/GTROW-D22-0013/seq": _fv(
                    "receivable_detail_rows/GTROW-D22-0013/seq", "1", row_key="GTROW-D22-0013"
                ),
                "receivable_detail_rows/dr-1/remark": _fv(
                    "receivable_detail_rows/dr-1/remark", "old", row_key="dr-1"
                ),
            },
            rows={"receivable_detail_rows": ("GTROW-D22-0013", "dr-1")},
        )
        store = _proj(
            {
                "receivable_detail_rows/dr-1/remark": _fv(
                    "receivable_detail_rows/dr-1/remark", "new", row_key="dr-1"
                ),
            },
            rows={"receivable_detail_rows": ("dr-1",)},
        )
        merged = overlay_store_on_baseline_projection(
            baseline=baseline, store_projection=store
        )
        # store 声明了 row_keys → store 为准：只有 dr-1
        assert merged.row_keys["receivable_detail_rows"] == ("dr-1",)
        assert merged.values["receivable_detail_rows/dr-1/remark"].value == "new"
        # GTROW 脚手架行不在 store row_keys 中 → 不在合并结果中
        assert "receivable_detail_rows/GTROW-D22-0013/seq" not in merged.values

    def test_store_none_placeholder_without_baseline_key_is_dropped(self) -> None:
        baseline = _proj({})
        store = _proj(
            {
                "minority_financials/r1/amount": _fv(
                    "minority_financials/r1/amount", None, row_key="r1"
                ),
            }
        )
        merged = overlay_store_on_baseline_projection(
            baseline=baseline, store_projection=store
        )
        assert "minority_financials/r1/amount" not in merged.values

    def test_store_none_clears_existing_baseline_value(self) -> None:
        baseline = _proj(
            {
                "receivable_detail_rows/dr-1/remark": _fv(
                    "receivable_detail_rows/dr-1/remark", "keep-or-clear", row_key="dr-1"
                ),
            }
        )
        store = _proj(
            {
                "receivable_detail_rows/dr-1/remark": _fv(
                    "receivable_detail_rows/dr-1/remark", None, row_key="dr-1"
                ),
            }
        )
        merged = overlay_store_on_baseline_projection(
            baseline=baseline, store_projection=store
        )
        assert merged.values["receivable_detail_rows/dr-1/remark"].value is None
