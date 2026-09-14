"""附注子表投影器：sub_table_data + 列头元数据 → 渲染器可消费的 _tables[]

纯函数、无 IO、读时执行、不持久化 `_tables`（sub_table_data 仍是权威存储）。
供附注模块章节详情读取（``get_note_detail``）与 Word 导出（``note_word_exporter``）
复用同一实现，避免前后端两套逻辑漂移。

spec: disclosure-table-sync-convergence
- design §Projector 逻辑 + §Data Models（Projected_Tables）
- Correctness Properties P1~P8（纯函数 / 列序 / 缺字段空单元 / 额外字段忽略 /
  合计行 / 多表键序 / 来源优先级 / 降级不杜撰）
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

# 可扩位行判据的单一真源（纯函数、stdlib-only）；本模块只 re-export 以保住既有
# import 路径（``note_word_exporter`` 从本模块取这两个符号）。
from app.services.note_expandable_markers import (
    EXPANDABLE_ROW_TYPE,
    is_zero_visible_row,
)

logger = logging.getLogger(__name__)

# ``_source`` 视为"底稿同步来源"的标识（投影权威来源，Req6.1）
_WORKPAPER_SOURCES = ("workpaper", "workpaper_html")

#: 源模板留的「可扩位」行 —— 附注模板里形如 ``……`` / ``可无限量添加行`` 的行。
#: 它标记的是「此处可增行」这个**位置**，本身没有披露内容 ⇒ 投影与 Word 导出
#: 一律**不产出可见数据行**、不参与任何合计。
#:
#: 🔴 additive 新增（第 6 个 ``row_type`` 取值），既有五个取值
#: （``data``/``total``/``subtotal``/``header_label``/``unowned``）的语义与行为
#: **逐字不变**：`header_label` 的假行由模板侧删除解决（见
#: ``backend/scripts/fix/fix_note_text_hygiene.py``），不由渲染层过滤解决。
#: 零回归的结构性保证 = 落地前全库 ``expandable`` 计数为 0，故本过滤对存量数据空操作。
#:
#: spec: note-template-columns-and-legacy-snapshot-closure R11.2 / R11.4 / Property 33
#:
#: 🔴 判据本体在 ``app.services.note_expandable_markers``（单一真源，纯函数无 IO）——
#: ``row_type`` 有多个写者（本 spec 的幂等脚本、``_note_structure_kit.data_row()``、
#: 若干 per-cycle 幂等脚本会整表重写 rows），判据分散会让写者互相翻转。
#: 此处只是 re-export，为保住既有 import 路径（``note_word_exporter`` 从本模块取）。
#: 实际绑定在文件头部的 import 处。


def _is_meta_key(key: Any) -> bool:
    """``_`` 前缀键为元数据（如 ``_note_texts`` / ``_manual_override``），跳过。"""
    return str(key).startswith("_")


def _pick_label_def(defs: list[dict]) -> dict | None:
    """选标签列定义：首个 ``is_label`` 为真者；无则首个有效定义。"""
    for d in defs:
        if isinstance(d, dict) and d.get("is_label"):
            return d
    for d in defs:
        if isinstance(d, dict):
            return d
    return None


def _clean_defs(defs_raw: Any) -> list[dict]:
    """从列头元数据取出有效列定义（每项须为含 ``key`` 的 dict）。"""
    if not isinstance(defs_raw, list):
        return []
    return [d for d in defs_raw if isinstance(d, dict) and d.get("key")]


def _inverse_project_row(row: dict, defs: list[dict]) -> dict:
    """把投影态行（``label`` / ``values[]`` / ``is_total``）还原为业务键行。

    投影输出（``rows[].values`` 按列序排列）若被回写进 ``sub_table_data``，行里就
    只有位置化的 ``values`` 而没有业务键，直接投影会得到整表空值。此处按已声明列头
    逆投影：``values[i]`` → ``value_defs[i]['key']``，``label`` → 标签列键。

    - 无 ``values`` 列表或无列头声明 → 原样返回（不猜字段）
    - 已存在的业务键**不被覆盖**（原始值优先）
    """
    values = row.get("values")
    if not isinstance(values, list) or not defs:
        return row

    label_def = _pick_label_def(defs)
    value_defs = [d for d in defs if d is not label_def]

    out = {k: v for k, v in row.items() if k != "values"}
    label_key = label_def.get("key") if isinstance(label_def, dict) else None
    if label_key and label_key != "label" and label_key not in out and "label" in out:
        out[label_key] = out["label"]
    for d, val in zip(value_defs, values):
        key = d.get("key")
        if key and key not in out:
            out[key] = val
    return out


def normalize_sub_table_data(sub: Any, cols_map: Any = None) -> dict[str, Any]:
    """把 ``sub_table_data`` 归一为 ``{key: list[dict]}`` 规范形态（纯函数）。

    容错两类"投影结果被回写"造成的非规范值（历史数据 + 未类型化的保存入口）：

    1. 表对象包装 ``{"rows": [...], "_column_groups": ...}`` → 解包为行列表；
    2. 投影态行 ``{label, values[], is_total}`` → 按列头逆投影回业务键行。

    - ``_`` 前缀元数据键原样保留（不做行归一）
    - 既非列表、又取不出 ``rows`` 列表的值 → 丢弃该键并 ``warning``（真损坏）

    Returns:
        新 dict（不修改入参）。入参非 dict 时返回 ``{}``。
    """
    if not isinstance(sub, dict):
        return {}
    cols = cols_map if isinstance(cols_map, dict) else {}

    out: dict[str, Any] = {}
    for key, value in sub.items():
        if _is_meta_key(key):
            out[key] = value
            continue

        rows = value
        if isinstance(rows, dict):
            # 表对象包装：只认 rows 列表，其余同级键（headers/_column_groups）丢弃
            inner = rows.get("rows")
            if isinstance(inner, list):
                rows = inner
        if not isinstance(rows, list):
            logger.warning(
                "normalize_sub_table_data: sub-table %r 值形态无法识别 (%s)，丢弃",
                key, type(value).__name__,
            )
            continue

        defs = _clean_defs(cols.get(key))
        out[key] = [
            _inverse_project_row(r, defs) for r in rows if isinstance(r, dict)
        ]
    return out


def project_sub_tables(table_data: Any) -> list[dict] | None:
    """把 ``sub_table_data`` + ``_sub_table_columns`` 投影为可渲染 ``_tables[]``。

    Returns:
        - ``None``：非 workpaper 来源 → 调用方 SHALL 沿用既有 ``_tables``/``rows``
          （Requirement 6.2 / Property 7），不投影。
        - ``list``：投影出的表列表（可能为空 list，表示 workpaper 来源但无子表）。

    纯函数：不修改入参、无 IO、同输入同输出（Property 1）。
    """
    if not isinstance(table_data, dict):
        return None
    source = table_data.get("_source")
    if source not in _WORKPAPER_SOURCES:
        return None  # Property 7: 非 workpaper 来源不投影

    sub = table_data.get("sub_table_data")
    if not isinstance(sub, dict) or not sub:
        return []  # workpaper 来源但无子表

    cols_map = table_data.get("_sub_table_columns")
    if not isinstance(cols_map, dict):
        cols_map = {}

    # 读时归一：容错"投影结果被回写"的表对象包装 / 位置化 values 行，
    # 避免整表被静默跳过（附注与 Word 导出同时丢表）。
    sub = normalize_sub_table_data(sub, cols_map)

    tables: list[dict] = []
    for key, rows in sub.items():  # 保持 sub_table_data 键插入序（Property 6）
        if _is_meta_key(key):
            continue
        if not isinstance(rows, list):  # 归一后恒为 list，纯防御
            continue

        defs = _clean_defs(cols_map.get(key))

        if not defs:
            # Property 8 / Requirement 7.2 降级：无列头元数据 → 绝不用英文字段键当 header。
            # 仅以 label 列（行名）可读呈现；不产出任何数据值列（values 恒空）。
            has_label = any(isinstance(r, dict) and ("label" in r) for r in rows)
            projected_rows = [
                {
                    "label": r.get("label", ""),
                    "values": [],
                    "is_total": bool(r.get("is_total", False)),
                }
                for r in rows
                if isinstance(r, dict) and not is_zero_visible_row(r)
            ]
            tables.append({
                "name": key,
                "headers": ["项目"] if has_label else [],
                "columns": [],
                "rows": projected_rows,
                "_source_sub_table_key": key,
                "_needs_columns": True,  # 前端据此提示"待配置列头"
            })
            continue

        label_def = _pick_label_def(defs)
        label_key = label_def.get("key") if isinstance(label_def, dict) else None
        value_defs = [d for d in defs if d is not label_def]
        # headers 产出子列名
        headers = [str(label_def.get("label", ""))] + [
            str(d.get("label", "")) for d in value_defs
        ]

        # 分组信息三态（见 _extract_column_groups 文档）：
        #   None → 未声明，回退 headers 前缀推断（存量行为）
        #   []   → 任一列 flat=True，显式单级表头，禁止推断
        #   非空 → 显式 group 分组
        # ⚠️ 守卫必须是 `is None`：写成 `if not col_groups:` 会让 flat 的 [] 也去推断，
        #    凭空造出「本期」这类父表头（disclosure-columns-coverage-rollout R3.1）
        col_groups = _extract_column_groups(defs)
        if col_groups is None:
            col_groups = _infer_groups_from_headers(headers)

        projected_rows = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            if is_zero_visible_row(r):  # 可扩位：零可见内容（Property 33）
                continue
            label_val = r.get(label_key, "") if label_key else ""
            # 兜底：标签列键值缺失时回退通用 `label`（合计/小计行常用 label 而非业务键）
            if (label_val is None or label_val == "") and label_key != "label":
                label_val = r.get("label", label_val)
            projected_rows.append({
                "label": label_val,
                # 缺字段 → None（Property 3）；未声明字段自动忽略（Property 4）
                "values": [r.get(d.get("key")) for d in value_defs],
                "is_total": bool(r.get("is_total", False)),  # Property 5
            })

        tables.append({
            "name": key,
            "headers": headers,
            "columns": defs,
            "rows": projected_rows,
            "_source_sub_table_key": key,
            "_column_groups": col_groups,
        })

    return tables


def _extract_column_groups(defs: list[dict]) -> list[dict] | None:
    """从列定义提取分组信息供前端渲染多级表头。

    支持多级分组：group 字段用 "/" 分隔层级（如 "期末余额/账面余额"）。
    返回树形结构供前端递归嵌套 el-table-column：
    [{"group": "期末余额", "children": [
        {"group": "账面余额", "columns": [idx1, idx2, ...]},
        {"columns": [idx3]}  # 无子分组的直接列
    ]}]
    简单单级分组返回扁平格式 [{"group":"期末余额","start":1,"span":3}] 保持向后兼容。

    返回值三态（调用方仅在 ``None`` 时回退 ``_infer_groups_from_headers``）：

    - ``None``  未声明任何分组信息 → 允许前缀推断（**存量行为不变**）
    - ``[]``    任一列带 ``flat: True`` → 显式单级表头，**禁止**前缀推断
    - 非空列表  显式分组

    ``flat`` 用于源模板本就是单行表头的表：不声明时前缀推断会把
    ``本期增加``/``本期减少`` 归到凭空的「本期」父表头下。

    spec: disclosure-columns-coverage-rollout R3 / f2-inventory-...-alignment R10
    """
    if not defs:
        return None

    # 显式单级声明：标在任意一列即对整表生效
    if any(isinstance(d, dict) and d.get("flat") for d in defs):
        return []

    # 收集所有非 is_label 列的 group 信息
    has_any_group = False
    col_groups: list[tuple[int, str | None]] = []  # (headerIdx, group_path)
    header_idx = 1  # headers[0] 是标签列
    for d in defs:
        if not isinstance(d, dict):
            continue
        if d.get("is_label"):
            continue
        g = d.get("group")
        if g:
            has_any_group = True
        col_groups.append((header_idx, g if g else None))
        header_idx += 1

    if not has_any_group:
        return None

    # 检查是否有多级（含 "/"）
    has_multi_level = any(g and "/" in g for _, g in col_groups)

    if not has_multi_level:
        # 单级分组 → 返回扁平格式 [{"group","start","span"}]（向后兼容）
        groups: list[dict] = []
        current_group: str | None = None
        group_start = 0
        group_span = 0
        for idx, g in col_groups:
            if g and g == current_group:
                group_span += 1
            else:
                if current_group and group_span > 0:
                    groups.append({"group": current_group, "start": group_start, "span": group_span})
                if g:
                    current_group = g
                    group_start = idx
                    group_span = 1
                else:
                    current_group = None
                    group_span = 0
        if current_group and group_span > 0:
            groups.append({"group": current_group, "start": group_start, "span": group_span})
        return groups if groups else None

    # 多级分组 → 返回树形结构
    # 按相邻且顶层 group 相同的列合并
    tree: list[dict] = []
    i = 0
    while i < len(col_groups):
        idx, g = col_groups[i]
        if not g:
            tree.append({"headerIdx": idx})
            i += 1
            continue

        parts = g.split("/")
        top = parts[0]
        # 收集连续同顶层 group 的列
        group_cols: list[tuple[int, list[str]]] = [(idx, parts)]
        j = i + 1
        while j < len(col_groups):
            nidx, ng = col_groups[j]
            if ng and ng.split("/")[0] == top:
                group_cols.append((nidx, ng.split("/")))
            else:
                break
            j += 1

        # 构建子层级
        if len(parts) == 1:
            # 单级但在多级上下文中
            tree.append({"group": top, "start": group_cols[0][0], "span": len(group_cols)})
        else:
            # 按第二级分组
            children: list[dict] = []
            ci = 0
            while ci < len(group_cols):
                c_idx, c_parts = group_cols[ci]
                sub = c_parts[1] if len(c_parts) > 1 else None
                if sub:
                    # 收集连续同 sub 的列
                    sub_cols = [c_idx]
                    ck = ci + 1
                    while ck < len(group_cols):
                        ck_idx, ck_parts = group_cols[ck]
                        if len(ck_parts) > 1 and ck_parts[1] == sub:
                            sub_cols.append(ck_idx)
                            ck += 1
                        else:
                            break
                    children.append({"group": sub, "start": sub_cols[0], "span": len(sub_cols)})
                    ci = ck
                else:
                    children.append({"headerIdx": c_idx})
                    ci += 1
            tree.append({"group": top, "children": children})

        i = j

    return tree if tree else None


def _infer_groups_from_headers(headers: list[str]) -> list[dict] | None:
    """从 headers 文本自动推断分组（通用机制，无需手工标注）。"""
    # 委托带缓存的内部函数（list 不可 hash，转 tuple）
    return _infer_groups_from_headers_cached(tuple(headers))


@lru_cache(maxsize=256)
def _infer_groups_from_headers_cached(headers: tuple[str, ...]) -> list[dict] | None:
    """带缓存的实际推断逻辑。

    规则：跳过 headers[0]（标签列），对值列检测相邻列共享前缀的模式。
    只有当一个前缀覆盖 ≥2 列且去掉前缀后子列名有意义时才认为是分组。
    返回与 _extract_column_groups 相同格式 [{"group","start","span"}]，或 None。
    """
    if len(headers) < 4:
        return None

    value_headers = list(headers[1:])  # 跳过标签列
    if len(value_headers) < 4:
        return None

    # 尝试找公共前缀：取前一半和后一半分别找共享前缀
    # 通用策略：逐个字符扫描相邻列，找最长公共前缀 ≥2 字符
    def _find_prefix_of_run(items: list[str]) -> str:
        """找一组字符串的最长公共前缀（≥2 中文字符才有意义）。"""
        if not items or len(items) < 2:
            return ""
        prefix = items[0]
        for s in items[1:]:
            while prefix and not s.startswith(prefix):
                prefix = prefix[:-1]
            if not prefix:
                return ""
        # 前缀至少 2 字符且不等于完整字符串且去掉前缀后后缀互不相同
        if len(prefix) < 2 or all(s == prefix for s in items):
            return ""
        suffixes = [s[len(prefix):] for s in items]
        if len(set(suffixes)) != len(suffixes):
            return ""  # 后缀有重复说明不是真分组
        return prefix

    # 扫描值列，用滑动窗口找连续 ≥2 列共享前缀的 runs
    groups: list[dict] = []
    i = 0
    while i < len(value_headers):
        # 尝试从 i 开始找最大的共享前缀 run
        best_end = i
        best_prefix = ""
        for end in range(i + 2, len(value_headers) + 1):
            p = _find_prefix_of_run(value_headers[i:end])
            if p and len(p) >= 2:
                best_end = end
                best_prefix = p
            else:
                break

        if best_prefix and best_end - i >= 2:
            # 确认去掉前缀后子列名不为空
            suffixes = [h[len(best_prefix):] for h in value_headers[i:best_end]]
            if all(s.strip() for s in suffixes):
                groups.append({
                    "group": best_prefix.rstrip("：:"),  # 去掉可能的冒号尾缀
                    "start": i + 1,  # +1 因为 headers 含标签列
                    "span": best_end - i,
                })
                i = best_end
                continue

        i += 1

    return groups if groups else None
