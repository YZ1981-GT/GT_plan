"""Note cell merge — 引擎重生成时三态合并 sidecar 字段（D1 决策）.

Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.5
Design: D1 渐进兼容现有 `_cell_modes` 行级 dict（sidecar 模式）

引擎重生成规则（auto / manual / locked 三态）：

  - ``_cell_modes[str(i)] == "auto"``  → 用 new_row.values[i] 覆盖；
    更新 ``_cell_meta[str(i)].binding_id`` 为 new 值（若 new 提供）
  - ``_cell_modes[str(i)] == "manual"`` → **保留** old.values[i]（不动）；
    若 ``_cell_meta[str(i)].manual_value`` 为 None，把 old.values[i] 备份进去
  - ``_cell_modes[str(i)] == "locked"`` → 连 values[i] 都不重算（保留 old）；
    不更新 _cell_meta
  - row 缺 ``_cell_modes[str(i)]`` 时按 "auto" 处理（默认行为）
  - new_row 没有 _cell_meta 时按全 auto 处理；旧 row 已有 _cell_meta 中的
    manual_value 字段保留

行级合并（多 row）：
  - 按 label 对齐优先，否则 index 兜底
  - new 独有 row → 直接进 merged
  - old 独有 row（new 缺） → 追加到 merged 末尾，标记 ``_legacy_row: True``
  - merged.row_type 优先用 new_row.row_type（模板权威）；缺则用 old_row.row_type

多表（``_tables`` 数组）：按 _tables[i].rows 同样规则合并；
顶层 headers/rows 同步首张表（兼容前端老代码读 ``table_data.rows``）。

铁律：
  - 纯函数 — 不打印日志、不操作 DB、不操作文件
  - deepcopy 入参后再修改（不破坏 caller 的 dict）
  - 必须保留 row 现有 sidecar 字段（row_type / _cell_meta）和现有字段
    （label / is_total / formula_type 等）
  - 入参可能 None / {} / 缺 rows / 缺 values，全都安全处理

Validates: Requirements R1.3 验收 10、11、12
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

__all__ = [
    "merge_row_preserving_cell_modes",
    "merge_table_data_preserving_cell_modes",
    "merge_columns_preserving_cell_modes",
]

# 三态合并允许值
_MODE_AUTO = "auto"
_MODE_MANUAL = "manual"
_MODE_LOCKED = "locked"
_VALID_MODES = {_MODE_AUTO, _MODE_MANUAL, _MODE_LOCKED}


# ---------------------------------------------------------------------------
# 内部小工具
# ---------------------------------------------------------------------------


def _safe_dict(x: Any) -> dict[str, Any]:
    """把 x 当成 dict 处理；非 dict 全部当空 dict."""
    return x if isinstance(x, dict) else {}


def _safe_list(x: Any) -> list[Any]:
    """把 x 当成 list 处理；非 list 全部当空 list."""
    return x if isinstance(x, list) else []


def _get_mode(cell_modes: dict[str, Any], idx: int) -> str:
    """读取 cell_modes[str(idx)]；缺失或非法 → 默认 "auto"."""
    raw = cell_modes.get(str(idx))
    if isinstance(raw, str) and raw in _VALID_MODES:
        return raw
    return _MODE_AUTO


def _make_empty_meta_slot() -> dict[str, Any]:
    """与 scripts/migrate_disclosure_notes_to_v2.py 的 _make_empty_cell_meta 单格保持一致."""
    return {"manual_value": None, "semantic": None, "binding_id": None}


def _ensure_meta_slot(meta: dict[str, Any], idx: int) -> dict[str, Any]:
    """读取 / 创建 meta[str(idx)] 槽位（确保是 dict）.

    返回 meta 中的 slot 引用（修改 slot 即修改 meta）.
    """
    key = str(idx)
    slot = meta.get(key)
    if not isinstance(slot, dict):
        slot = _make_empty_meta_slot()
        meta[key] = slot
    else:
        # 兜底补齐缺失字段（不覆盖已有值）
        for k in ("manual_value", "semantic", "binding_id"):
            if k not in slot:
                slot[k] = None
    return slot


def _row_key(row: dict[str, Any]) -> str | None:
    """提取 row 的 label（用于 row 对齐）；空 / 非 str → None."""
    label = row.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return None


# ---------------------------------------------------------------------------
# 单行三态合并
# ---------------------------------------------------------------------------


def merge_row_preserving_cell_modes(
    old_row: dict[str, Any] | None,
    new_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """对单行做三态合并；返回新 row dict（不修改入参）.

    实现：
      1. 起始结果 = deepcopy(new_row)（new 是权威结构 / 长度 / row_type）
      2. 遍历 i ∈ [0, len(new.values)) — new 是权威长度
         - mode = old._cell_modes.get(str(i), "auto")
         - auto   → merged.values[i] = new.values[i]（不变，已是 new）；
                    更新 merged._cell_meta[str(i)].binding_id 用 new 提供的
         - manual → merged.values[i] = old.values[i]；
                    若 old._cell_meta[str(i)].manual_value 为 None →
                    备份 old.values[i] 到 manual_value
         - locked → merged.values[i] = old.values[i]；不动 _cell_meta
      3. _cell_modes 整体复制 old 的（用户态权威）
      4. _cell_meta 整体复制 old 的（manual_value 备份等）后再做局部更新
      5. row_type / formula_type / is_total 等结构字段：new 优先，缺则取 old
      6. 老 row 字段（label 等）以 new 为准；如果 new 缺，退而求其次取 old

    Args:
        old_row: 旧 row dict（可 None / 空）— 用户态：含 _cell_modes / _cell_meta
        new_row: 新 row dict（可 None / 空）— 引擎重新算出的权威值

    Returns:
        合并后的 row dict（独立对象，可安全修改）
    """
    # 双 None / 双空：直接返回空 dict
    if not isinstance(new_row, dict) and not isinstance(old_row, dict):
        return {}

    # new_row 缺：直接返回 deepcopy(old_row)（行级缺失，row 保留为 _legacy_row 由 caller 标）
    if not isinstance(new_row, dict):
        return deepcopy(_safe_dict(old_row))

    merged: dict[str, Any] = deepcopy(new_row)
    old_safe = _safe_dict(old_row)

    # 不存在 old → 全 auto，直接返回 merged（new 即权威）.
    # 但仍兜底：merged._cell_modes 空时建空 dict，_cell_meta 空时建空 dict。
    new_values = _safe_list(merged.get("values"))
    if not old_safe:
        # 标准化空 sidecar
        if "_cell_modes" not in merged or not isinstance(merged.get("_cell_modes"), dict):
            merged["_cell_modes"] = {}
        if "_cell_meta" not in merged or not isinstance(merged.get("_cell_meta"), dict):
            merged["_cell_meta"] = {}
        return merged

    old_values = _safe_list(old_safe.get("values"))
    old_cell_modes = _safe_dict(old_safe.get("_cell_modes"))
    old_cell_meta = _safe_dict(old_safe.get("_cell_meta"))
    new_cell_meta = _safe_dict(merged.get("_cell_meta"))

    # _cell_modes 一律复制 old（用户态权威）；缺失即空 dict
    merged["_cell_modes"] = deepcopy(old_cell_modes)

    # _cell_meta 起始 = deepcopy(old) — 保留 manual_value 备份等历史
    out_meta: dict[str, Any] = deepcopy(old_cell_meta)

    # 逐 col 处理 — new.values 是权威长度
    n = len(new_values)
    out_values: list[Any] = list(new_values)  # 起始 = new（auto 默认行为）

    for i in range(n):
        mode = _get_mode(merged["_cell_modes"], i)
        slot = _ensure_meta_slot(out_meta, i)

        if mode == _MODE_AUTO:
            # 用新值（已在 out_values 中），同时更新 binding_id（如果 new 提供了）
            new_slot = new_cell_meta.get(str(i))
            if isinstance(new_slot, dict):
                # 仅更新 binding_id 字段（语义来自 new；manual_value 不动）
                new_binding_id = new_slot.get("binding_id")
                if new_binding_id is not None:
                    slot["binding_id"] = new_binding_id
                new_semantic = new_slot.get("semantic")
                if new_semantic is not None and slot.get("semantic") in (None, ""):
                    slot["semantic"] = new_semantic

        elif mode == _MODE_MANUAL:
            # 保留旧值
            old_val: Any = old_values[i] if i < len(old_values) else None
            out_values[i] = old_val
            # 备份原始值到 manual_value（仅当槽位空时）
            if slot.get("manual_value") is None and old_val is not None:
                slot["manual_value"] = old_val
            # binding_id 仍跟随 new（语义不变）
            new_slot = new_cell_meta.get(str(i))
            if isinstance(new_slot, dict):
                new_binding_id = new_slot.get("binding_id")
                if new_binding_id is not None:
                    slot["binding_id"] = new_binding_id

        elif mode == _MODE_LOCKED:
            # 完全保留旧值；不更新 _cell_meta
            old_val = old_values[i] if i < len(old_values) else None
            out_values[i] = old_val
            # 不动 slot — 保留 old 的所有字段
            # 但若 new 提供了 binding_id 而 slot 中无（首次升级场景），补上
            if slot.get("binding_id") is None:
                new_slot = new_cell_meta.get(str(i))
                if isinstance(new_slot, dict):
                    new_binding_id = new_slot.get("binding_id")
                    if new_binding_id is not None:
                        slot["binding_id"] = new_binding_id

    merged["values"] = out_values
    merged["_cell_meta"] = out_meta

    # row_type：new 优先（模板权威），缺则用 old
    if not merged.get("row_type") and old_safe.get("row_type"):
        merged["row_type"] = old_safe["row_type"]

    # 现有字段（formula_type / is_total / _row_id 等）：new 缺则用 old 兜底
    # 但 new 已经通过 deepcopy(new_row) 起始，这里只补 new 没有的
    for k, v in old_safe.items():
        if k in ("values", "_cell_modes", "_cell_meta"):
            continue
        if k not in merged or merged.get(k) in (None, ""):
            merged[k] = deepcopy(v)

    return merged


# ---------------------------------------------------------------------------
# 单表合并 + 多表合并入口
# ---------------------------------------------------------------------------


def _merge_rows(
    old_rows: list[Any],
    new_rows: list[Any],
) -> list[dict[str, Any]]:
    """合并两个 rows 数组：按 label 对齐优先，index 兜底；保留 old 独有 row 标 _legacy_row.

    返回 merged rows（深拷贝后的独立 list）.
    """
    old_rows = _safe_list(old_rows)
    new_rows = _safe_list(new_rows)

    # 收集 old rows 的 label → row 引用（仅含 dict + 非空 label）
    old_by_label: dict[str, dict[str, Any]] = {}
    old_dict_rows: list[dict[str, Any]] = []  # 顺序 list（用于 index 兜底）
    for r in old_rows:
        if isinstance(r, dict):
            old_dict_rows.append(r)
            key = _row_key(r)
            if key is not None and key not in old_by_label:
                old_by_label[key] = r

    used_old_ids: set[int] = set()  # 已对齐使用的 old row 内存 id
    merged: list[dict[str, Any]] = []

    for i, new_r in enumerate(new_rows):
        if not isinstance(new_r, dict):
            # 非 dict 行（极少见），原样追加 deepcopy
            merged.append(deepcopy(new_r) if isinstance(new_r, dict) else new_r)
            continue

        # ① label 对齐
        new_key = _row_key(new_r)
        old_r: dict[str, Any] | None = None
        if new_key is not None and new_key in old_by_label:
            cand = old_by_label[new_key]
            if id(cand) not in used_old_ids:
                old_r = cand
                used_old_ids.add(id(cand))

        # ② index 兜底（label 没匹到时）
        if old_r is None and i < len(old_dict_rows):
            cand = old_dict_rows[i]
            if id(cand) not in used_old_ids:
                # 不强制要求 label 一致 — 但若 cand 已有强 label 且与 new 冲突，跳过
                cand_key = _row_key(cand)
                if cand_key is None or cand_key == new_key:
                    old_r = cand
                    used_old_ids.add(id(cand))

        merged.append(merge_row_preserving_cell_modes(old_r, new_r))

    # ③ 老 row 独有的（new 没匹配到的）→ 追加 + _legacy_row 标记
    for r in old_dict_rows:
        if id(r) in used_old_ids:
            continue
        legacy = deepcopy(r)
        legacy["_legacy_row"] = True
        merged.append(legacy)

    return merged


def _merge_single_table(
    old_table: dict[str, Any],
    new_table: dict[str, Any],
) -> dict[str, Any]:
    """合并单张表（{headers, rows, name, ...}）.

    headers / name 等表级字段以 new 为权威；rows 走 _merge_rows.
    """
    out: dict[str, Any] = deepcopy(new_table)
    out["rows"] = _merge_rows(old_table.get("rows"), new_table.get("rows"))
    return out


def merge_table_data_preserving_cell_modes(
    old_table_data: dict[str, Any] | None,
    new_table_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """合并 note.table_data — 单表 + 多表 schema 自动识别.

    Args:
        old_table_data: 历史 note.table_data dict（含 _cell_modes / _cell_meta 等）
        new_table_data: 引擎重新算出的权威 table_data（按 binding 取值）

    Returns:
        合并后的 dict — 独立深拷贝；可直接赋值 note.table_data.

    Schema 检测：
      - 多表：new_table_data._tables 是 list 且非空 → 按 _tables[i] 顺序合并
              （额外把 merged._tables[0] 的 headers/rows 镜像到顶层，兼容前端老代码）
      - 单表：仅 headers / rows → 当成一张表处理
    """
    # 双 None / 双空：返回空 dict
    if not isinstance(new_table_data, dict) and not isinstance(old_table_data, dict):
        return {}

    # new 缺：返回 deepcopy(old)
    if not isinstance(new_table_data, dict):
        return deepcopy(_safe_dict(old_table_data))

    old_safe = _safe_dict(old_table_data)
    new_tables = new_table_data.get("_tables")

    # 多表分支
    if isinstance(new_tables, list) and new_tables:
        old_tables = old_safe.get("_tables")
        old_tables_list = _safe_list(old_tables)

        merged_tables: list[dict[str, Any]] = []
        for i, new_tbl in enumerate(new_tables):
            if not isinstance(new_tbl, dict):
                merged_tables.append(deepcopy(new_tbl) if isinstance(new_tbl, dict) else new_tbl)
                continue
            old_tbl = (
                old_tables_list[i]
                if i < len(old_tables_list) and isinstance(old_tables_list[i], dict)
                else {}
            )
            merged_tables.append(_merge_single_table(old_tbl, new_tbl))

        # 起始结果 = new 顶层结构 deepcopy
        out: dict[str, Any] = deepcopy(new_table_data)
        out["_tables"] = merged_tables
        # 顶层 headers / rows 镜像首张表（兼容前端老代码读 table_data.rows）
        first = merged_tables[0] if merged_tables else None
        if isinstance(first, dict):
            out["headers"] = deepcopy(first.get("headers", []))
            out["rows"] = deepcopy(first.get("rows", []))
            if "name" in first:
                out["name"] = first.get("name", "")
        return out

    # 单表分支
    return _merge_single_table(old_safe, new_table_data)


# ---------------------------------------------------------------------------
# A.2.9 — 列级三态合并（动态加列时保留旧 cells 的 cell_modes 状态）
# ---------------------------------------------------------------------------


def _columns_meta_index_by_id(meta: list[Any]) -> dict[str, int]:
    """返回 {col_id: position_index}（_columns_meta 顺序索引）."""
    out: dict[str, int] = {}
    for i, c in enumerate(meta):
        if isinstance(c, dict):
            cid = c.get("id")
            if isinstance(cid, str) and cid:
                out[cid] = i
    return out


def _row_value_at(row: dict[str, Any], idx: int) -> Any:
    vals = _safe_list(row.get("values"))
    return vals[idx] if 0 <= idx < len(vals) else None


def _row_cell_mode_at(row: dict[str, Any], idx: int) -> str:
    modes = _safe_dict(row.get("_cell_modes"))
    return _get_mode(modes, idx)


def _row_cell_meta_at(row: dict[str, Any], idx: int) -> dict[str, Any] | None:
    meta = _safe_dict(row.get("_cell_meta"))
    slot = meta.get(str(idx))
    return slot if isinstance(slot, dict) else None


def _build_remapped_row(
    old_row: dict[str, Any] | None,
    new_row: dict[str, Any],
    old_meta: list[Any],
    new_meta: list[Any],
) -> dict[str, Any]:
    """根据 new_meta 列顺序重建 row.

    - 对每个 new column：
        - 若该 col_id 也在 old → 用旧 row 同 col_id 的 (value/_cell_modes/_cell_meta)
          走行级三态合并（manual/locked 保留旧值）
        - 若该 col_id 是新列 → 用 new_row 的对应位置值，cell_modes 默认 auto
    - old 独有的 col_id：把那个 cell 的 (value, _cell_modes, _cell_meta) 暂存到
      ``_legacy_cells[col_id]``，便于回滚 / 审计追溯（不写入 values）
    """
    new_row_safe = _safe_dict(new_row)
    new_values_in = _safe_list(new_row_safe.get("values"))

    old_idx_by_id = _columns_meta_index_by_id(old_meta)
    new_idx_by_id = _columns_meta_index_by_id(new_meta)

    n_new = len(new_meta)
    out_values: list[Any] = [None] * n_new
    out_modes: dict[str, Any] = {}
    out_meta_dict: dict[str, Any] = {}

    old_row_safe = _safe_dict(old_row)

    for col in new_meta:
        if not isinstance(col, dict):
            continue
        cid = col.get("id")
        if not isinstance(cid, str) or not cid:
            continue
        new_pos = new_idx_by_id[cid]
        new_val = new_values_in[new_pos] if new_pos < len(new_values_in) else None

        if cid in old_idx_by_id and old_row_safe:
            old_pos = old_idx_by_id[cid]
            mode = _row_cell_mode_at(old_row_safe, old_pos)
            old_val = _row_value_at(old_row_safe, old_pos)
            old_slot = _row_cell_meta_at(old_row_safe, old_pos)

            # 复制 mode（用户态权威）
            out_modes[str(new_pos)] = mode

            # 起始 meta slot：deepcopy 旧 slot；缺则空
            slot = deepcopy(old_slot) if old_slot is not None else _make_empty_meta_slot()
            for k in ("manual_value", "semantic", "binding_id"):
                if k not in slot:
                    slot[k] = None

            if mode == _MODE_AUTO:
                out_values[new_pos] = new_val
                # 更新 binding_id 用 new
                # （new 通常无 _cell_meta，简化处理）
            elif mode == _MODE_MANUAL:
                out_values[new_pos] = old_val
                if slot.get("manual_value") is None and old_val is not None:
                    slot["manual_value"] = old_val
            elif mode == _MODE_LOCKED:
                out_values[new_pos] = old_val
                # locked 不动 slot
            else:
                out_values[new_pos] = new_val

            out_meta_dict[str(new_pos)] = slot
        else:
            # 新列接入 — 直接用 new 值，cell_modes 默认 auto（不显式写）
            out_values[new_pos] = new_val
            out_meta_dict[str(new_pos)] = _make_empty_meta_slot()

    # 收集 old 独有 col_id → _legacy_cells（保留以备审计回滚）
    legacy_cells: dict[str, Any] = {}
    if old_row_safe:
        for cid, old_pos in old_idx_by_id.items():
            if cid in new_idx_by_id:
                continue
            legacy_cells[cid] = {
                "value": _row_value_at(old_row_safe, old_pos),
                "mode": _row_cell_mode_at(old_row_safe, old_pos),
                "meta": deepcopy(_row_cell_meta_at(old_row_safe, old_pos))
                or _make_empty_meta_slot(),
            }

    # 起始结果 = deepcopy(new_row)；覆盖 values / _cell_modes / _cell_meta
    merged: dict[str, Any] = deepcopy(new_row_safe)
    merged["values"] = out_values
    merged["_cell_modes"] = out_modes
    merged["_cell_meta"] = out_meta_dict
    if legacy_cells:
        merged["_legacy_cells"] = legacy_cells

    # 兜底字段：old 有 / new 无的字段（label / row_type / formula_type / is_total 等）
    for k, v in old_row_safe.items():
        if k in (
            "values",
            "_cell_modes",
            "_cell_meta",
            "_legacy_cells",
        ):
            continue
        if k not in merged or merged.get(k) in (None, ""):
            merged[k] = deepcopy(v)

    return merged


def merge_columns_preserving_cell_modes(
    old_table_data: dict[str, Any] | None,
    new_table_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """列级三态合并：动态加列时保留旧 cells 的 cell_modes 状态.

    场景：用户在某列手填了值（``_cell_modes[col_id] == "manual"``），
    动态展开新增列后，旧列的 manual/locked 状态必须保留。

    规则
    ----
    - **列对齐**：按 ``_columns_meta[].id`` 对齐（不依赖位置）
    - **旧列保留**：old 中存在 + new 中也存在的列 → 走行级三态合并
      （manual 保留旧值；locked 保留旧值；auto 用新值）
    - **新列接入**：new 独有的列 → 直接插入，cell_modes 默认 auto
    - **旧列消失**：old 独有的列 → 不写入 values，但写入 row 的
      ``_legacy_cells[col_id]`` 字段保留 (value, mode, meta) 以备审计回滚
    - **行对齐**：按现有 ``_merge_rows`` 规则（label 优先 / index 兜底）

    Args:
        old_table_data: 历史 table_data（含 _columns_meta / rows）
        new_table_data: 引擎重新算出的表格（含 _columns_meta / rows）

    Returns:
        新 dict — 独立深拷贝；可直接赋值 note.table_data。

    Notes:
        - 与 ``merge_table_data_preserving_cell_modes`` 不同：本函数处理
          列结构变化（加列 / 删列 / 重排），而行级合并函数假设列结构不变。
        - 若 ``new._columns_meta`` 为空或缺失，退化到行级合并函数（保持兼容）。
    """
    if not isinstance(new_table_data, dict) and not isinstance(old_table_data, dict):
        return {}

    if not isinstance(new_table_data, dict):
        return deepcopy(_safe_dict(old_table_data))

    new_safe = _safe_dict(new_table_data)
    old_safe = _safe_dict(old_table_data)

    new_meta = _safe_list(new_safe.get("_columns_meta"))
    old_meta = _safe_list(old_safe.get("_columns_meta"))

    # 退化：new 没声明 _columns_meta → 行级合并
    if not new_meta:
        return merge_table_data_preserving_cell_modes(old_table_data, new_table_data)

    # 验 CI-3：new._columns_meta 中 id 必须全表唯一
    seen: set[str] = set()
    for c in new_meta:
        if isinstance(c, dict):
            cid = c.get("id")
            if isinstance(cid, str) and cid:
                if cid in seen:
                    raise ValueError(
                        f"merge_columns_preserving_cell_modes: duplicate column id "
                        f"'{cid}' in new _columns_meta (CI-3 violation)"
                    )
                seen.add(cid)

    # 行对齐：复用 _merge_rows 但每个 row 走列重映射
    old_rows = _safe_list(old_safe.get("rows"))
    new_rows = _safe_list(new_safe.get("rows"))

    # 收集 old rows 索引（按 label 对齐）
    old_by_label: dict[str, dict[str, Any]] = {}
    old_dict_rows: list[dict[str, Any]] = []
    for r in old_rows:
        if isinstance(r, dict):
            old_dict_rows.append(r)
            key = _row_key(r)
            if key is not None and key not in old_by_label:
                old_by_label[key] = r

    used_old_ids: set[int] = set()
    merged_rows: list[dict[str, Any]] = []

    for i, new_r in enumerate(new_rows):
        if not isinstance(new_r, dict):
            merged_rows.append(deepcopy(new_r) if isinstance(new_r, dict) else new_r)
            continue

        new_key = _row_key(new_r)
        old_r: dict[str, Any] | None = None
        if new_key is not None and new_key in old_by_label:
            cand = old_by_label[new_key]
            if id(cand) not in used_old_ids:
                old_r = cand
                used_old_ids.add(id(cand))
        if old_r is None and i < len(old_dict_rows):
            cand = old_dict_rows[i]
            if id(cand) not in used_old_ids:
                cand_key = _row_key(cand)
                if cand_key is None or cand_key == new_key:
                    old_r = cand
                    used_old_ids.add(id(cand))

        merged_rows.append(_build_remapped_row(old_r, new_r, old_meta, new_meta))

    # 老 row 独有 → 追加 + _legacy_row 标记（按 new_meta 列结构对齐）
    for r in old_dict_rows:
        if id(r) in used_old_ids:
            continue
        # 给老行也走列重映射（生成符合 new_meta 列结构的 row）
        legacy = _build_remapped_row(r, {"values": [None] * len(new_meta)}, old_meta, new_meta)
        legacy["_legacy_row"] = True
        merged_rows.append(legacy)

    out = deepcopy(new_safe)
    out["rows"] = merged_rows
    return out
