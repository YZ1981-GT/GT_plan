# -*- coding: utf-8 -*-
"""G9 的 store 投影/合并门面 —— 从 `phase5_g9_other_noncurrent` 抽出的伴生模块。

spec: `g-cycle-single-region-detail-lanes` · Task 8 / C-5

═══ 为什么抽出来 ═══

主模块触到仓库的单文件行数门禁（`.git-hooks/pre-commit`，上限 800 行）。门禁的处置顺序是
「优先拆分 / 抽伴生模块，确有必要才改 whitelist 基线」。这一段（三段组合的四个 store 门面）
是**内聚**的一块：它们共享 `_specs_for` 的段解析，且与契约装配、matcher、注册三段无耦合。

先例：`pilot_h1_store_merge.py`（H1 把 `merge_projection_into_store_rows` 抽成伴生模块，
主模块重导出使调用方零改动）。

═══ 调用方零改动 ═══

主模块在文件末尾 `from .phase5_g9_store_facade import (...)` 重导出，因此
`getattr(provider, "build_store_projection")` / `getattr(bridge, plan.merge_rows_fn)`
这类按名取属性的调用点（`store_projection_response` / `projection_first_publication` /
`oo_to_html` / 零回归门）看到的仍是主模块属性。

🔴 本模块对主模块的引用一律**函数体内惰性 import**（避免与主模块的末尾重导出构成循环）。
"""
from __future__ import annotations

import json
from typing import Any, Iterator, Mapping, Sequence

__all__ = [
    "specs_for",
    "build_store_projection",
    "merge_projection_into_store_rows",
    "iter_store_rows",
    "split_store_payload_by_section",
]


def _provider() -> Any:
    """惰性取主模块（见模块 docstring 的循环导入说明）。"""
    from app.services.workpaper_sync import phase5_g9_other_noncurrent as _p

    return _p


def specs_for(section: str | None, store_item_id: str | None) -> tuple[Any, ...]:
    """解析本次操作覆盖哪些段。

    * `section=None` ⇒ 全部受管段（生产缺省；只投一段会静默丢另两段的行）；
    * `section="main"` 等 ⇒ 仅该段（逐段判据用）。

    `store_item_id` 给了就先按它筛（三段同键 ⇒ 等价于不筛，留着是为了和其它十一家的
    门面签名一致，也让「传错键」变成显式错误而不是静默全投）。
    """
    p = _provider()
    specs = p.managed_row_table_specs()
    if not specs:
        raise p.EntrySelectionError("G9 当前无受管 sheet")
    if store_item_id is not None:
        specs = tuple(s for s in specs if s.store_item_id == store_item_id)
        if not specs:
            raise p.EntrySelectionError(
                f"store item {store_item_id!r} 不在 G9 受管清单里；"
                f"已受管：{sorted(p.all_store_item_ids())}"
            )
    if section is None:
        return specs
    picked = tuple(s for s in specs if s.row_section_value == section)
    if not picked:
        raise p.EntrySelectionError(
            f"section {section!r} 不在 G9 受管段里；"
            f"已受管：{[s.row_section_value for s in specs]}"
        )
    return picked


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: Any,
    limits: Any | None = None,
    store_item_id: str | None = None,
    section: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`（**缺省合并三段**）。

    🔴 **签名形态是刚性的**：`payload` 必须是第一个位置参数、其余走关键字。零回归门
    `scripts/check/check_sync_provider_golden_digest.py` 按
    `mod.build_store_projection(rows, contract=contract)` 调用 —— 写成两位置参会
    直接 `TypeError`（F1/F2 曾踩到）。

    🔴 缺省投影全部三段而不是只投区①：生产调用点
    （`store_projection_response.py` / `projection_first_publication.py`）
    只传一份 payload，没有段参数。只投区① ⇒ 区②③的行在 OO 侧永远是空的，而且
    digest 照样算得出来（假绿）。
    """
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )

    specs = specs_for(section, store_item_id)
    values: dict[str, Any] = {}
    row_keys: dict[str, Any] = {}
    first: Any = None
    for spec in specs:
        proj = _engine(spec, payload, contract=contract, limits=limits)
        if first is None:
            first = proj
        # 🔴 段与段的 stable_key 天然不同（`table_key` 逐段不同 ⇒ key 前缀不同），
        #    所以 update 不会互相覆盖；真撞了说明 sheet 层声明漂移，宁可显式炸。
        collision = values.keys() & proj.values.keys()
        if collision:
            raise _provider().StorePayloadError(
                f"G9 段 {spec.row_section_value!r} 的 projection 与前段 stable_key 相撞："
                f"{sorted(collision)[:3]} —— sheet 层 table_key 声明漂移"
            )
        values.update(proj.values)
        row_keys.update(proj.row_keys)
    assert first is not None  # specs_for 保证非空
    return Projection(
        contract_id=first.contract_id,
        semantic_version=first.semantic_version,
        document_type=first.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str | None = None,
    section: str | None = None,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """projection → HTML store 行（**三段顺序穿线**，含幽灵行防护）。

    穿线而不是三次独立 merge 后再拼：引擎的单段 merge 接收**整个** store 数组作为
    `base_rows`、按 identity 索引回写，不属本段的行原样保留。因此把上一段的 merged
    结果喂给下一段，最终结果同时含三段的改动；`applied/visited` 累加、`touched`
    取并集。若三次独立 merge 再拼，后写的会覆盖前面的改动。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    rows: list[Mapping[str, Any]] = list(base_rows)
    applied_total = 0
    visited_total = 0
    touched_all: set[str] = set()
    for spec in specs_for(section, store_item_id):
        merged, applied, visited, touched = _engine_merge(
            spec, projection=projection, base_rows=rows
        )
        rows = merged
        applied_total += applied
        visited_total += visited
        touched_all |= touched
    return [dict(r) for r in rows], applied_total, visited_total, touched_all


def iter_store_rows(
    payload: Any,
    *,
    store_item_id: str | None = None,
    section: str | None = None,
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """流式 `(row_identity, row)`；缺省**串联三段**（各段内部按 `section` 过滤）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    for spec in specs_for(section, store_item_id):
        yield from _engine_iter(spec, payload)


def split_store_payload_by_section(
    payload: str | bytes | Sequence[Any],
) -> dict[str, list[Mapping[str, Any]]]:
    """按 `section` 把一份 store 载荷拆成三段（排障/判据用，不在生产路径上）。

    未登记的 section 值单独归到 `""` 桶 —— 静默丢弃会让「前端写了第四个区」这类
    漂移看不见。
    """
    p = _provider()
    if isinstance(payload, (str, bytes)):
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        parsed = json.loads(text) if text.strip() else []
    else:
        parsed = list(payload)
    if not isinstance(parsed, list):
        raise p.StorePayloadError(
            f"{p.STORE_ITEM_ID} 载荷根形态必须是数组，实得 {type(parsed).__name__}"
        )
    known = {s.row_section_value for s in p.section_specs()}
    buckets: dict[str, list[Mapping[str, Any]]] = {k: [] for k in sorted(known)}
    buckets.setdefault("", [])
    for row in parsed:
        if not isinstance(row, Mapping):
            raise p.StorePayloadError(
                f"{p.STORE_ITEM_ID} 存在非对象行：{type(row).__name__}"
            )
        value = str(row.get("section") or "")
        buckets[value if value in known else ""].append(row)
    return buckets
