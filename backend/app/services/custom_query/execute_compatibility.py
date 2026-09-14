"""主 custom-query execute 到 QueryOrchestrator 的唯一兼容适配层。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.services.query_cache import CanonicalRedisQueryCache
from app.services.custom_query.query_orchestrator import (
    Agg,
    PivotConfig,
    QueryOrchestrator,
    QueryRequest,
    QueryResult,
)


def _model_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    raise TypeError(f"unsupported request model: {type(value).__name__}")


class ExecuteCompatibilityAdapter:
    """旧/新请求无损映射到一个已注入业务 fetcher 的编排器。"""

    def __init__(self, *, business_fetcher, orchestrator: QueryOrchestrator | None = None):
        if business_fetcher is None:
            raise ValueError("business_fetcher is required")
        self._orchestrator = orchestrator or QueryOrchestrator(
            business_fetcher=business_fetcher,
            cache=CanonicalRedisQueryCache(),
        )

    @staticmethod
    def to_orchestrator_request(body: Any) -> QueryRequest:
        raw_sort = getattr(body, "sort", [])
        sort = [_model_dict(item) for item in raw_sort] if isinstance(raw_sort, (list, tuple)) else []
        raw_group = getattr(body, "group", None)
        group = raw_group if isinstance(raw_group, dict) else {}
        dimensions = group.get("dimensions", group.get("group_by", []))
        raw_aggs = group.get("aggregates", group.get("aggs", []))
        aggs = [
            Agg(
                field=str(item["field"]),
                func=str(item.get("op", item.get("func", "sum"))),
                alias=item.get("alias"),
            )
            for item in raw_aggs
            if isinstance(item, dict) and item.get("field")
        ]
        raw_pivot = getattr(body, "pivot", None)
        pivot = None
        if isinstance(raw_pivot, dict):
            pivot = PivotConfig(
                row_dims=list(
                    raw_pivot.get("rowDimensions", raw_pivot.get("row_dimensions", raw_pivot.get("row_dims", [])))
                ),
                col_dims=list(
                    raw_pivot.get("columnDimensions", raw_pivot.get("column_dimensions", raw_pivot.get("col_dims", [])))
                ),
                value_field=raw_pivot.get("valueField", raw_pivot.get("value_field")),
                agg=str(raw_pivot.get("aggregate", raw_pivot.get("agg", "sum"))),
                max_cols=int(raw_pivot.get("maxCols", raw_pivot.get("max_cols", 512))),
            )

        raw_filters = getattr(body, "filters", {})
        raw_columns = getattr(body, "columns", [])
        raw_targets = getattr(body, "acnr_targets", [])
        raw_limit = getattr(body, "limit", 500)
        raw_offset = getattr(body, "offset", 0)
        return QueryRequest(
            entry="business",
            project_id=str(body.project_id),
            year=int(body.year),
            source=str(body.source),
            filters=dict(raw_filters) if isinstance(raw_filters, dict) else {},
            columns=list(raw_columns) if isinstance(raw_columns, (list, tuple)) else [],
            targets=list(raw_targets) if isinstance(raw_targets, (list, tuple)) else [],
            sort=sort,
            group_by=[str(item) for item in dimensions],
            aggs=aggs,
            pivot=pivot,
            limit=int(raw_limit) if isinstance(raw_limit, int) else 500,
            offset=int(raw_offset) if isinstance(raw_offset, int) else 0,
        )

    @staticmethod
    def to_legacy_response(result: QueryResult) -> dict[str, Any]:
        columns: list[Any] = []
        for column in result.columns:
            if column.addr_id or column.source or column.semantic_label:
                columns.append(asdict(column))
            else:
                columns.append(column.key)
        return {
            "rows": result.rows,
            "columns": columns,
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
            "warnings": result.warnings,
            "cache_hit": result.cache_hit,
        }

    async def execute(self, body: Any, *, user: Any, db: Any) -> dict[str, Any]:
        request = self.to_orchestrator_request(body)
        result = await self._orchestrator.execute(request, user=user, db=db)
        return self.to_legacy_response(result)
