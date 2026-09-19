"""Note template diff service — SOE/Listed 模板差异管理.

Sprint A.5 Tasks: A.5.9 / A.5.10 / A.5.11

纯函数 / 无 DB（原「≤ 350 行」的约束已随 Task 1/2 的可观测化改造失效，
现按「一个职责一族函数」组织：差异比对 / 章节分类 / table_data 适配）

Functions:
    load_diff_data() — **实时计算为准**，落盘 JSON 仅作交叉校验（2026-08-06 改，
        原「落盘优先」会让生产一直读一份 is_mock=true 且已 stale 的数据）
    compare_diff_payloads(stored, live) — 落盘 vs 实时的桶级集合比对（纯函数）
    compute_diff_from_templates(soe_sections, listed_sections) — 按 section_title 匹配
    compute_section_diff(soe_section, listed_section) — 单章节 diff
    adapt_table_data(table_data, target_format, field_mapping) — 列重映射（薄壳）
    adapt_table_data_with_report(...) — 同上 + 可观测的 AdaptReport（2026-08-07 新增）
    classify_section_mapping(section_id, diff_data) — 分类工具
"""
from __future__ import annotations

import json
import logging
import pathlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "load_diff_data",
    "reset_diff_cache",
    "compare_diff_payloads",
    "compute_diff_from_templates",
    "compute_section_diff",
    "adapt_table_data",
    "adapt_table_data_with_report",
    "AdaptReport",
    "SUPPORTED_FIELD_MAPPING_KEYS",
    "DECLARED_UNIMPLEMENTED_FIELD_MAPPING_KEYS",
    "ADAPT_REASON_APPLIED",
    "ADAPT_REASON_NO_EFFECT",
    "ADAPT_REASON_NO_FIELD_MAPPING",
    "ADAPT_REASON_UNSUPPORTED_ONLY",
    "classify_section_mapping",
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "data"
_DIFF_JSON_PATH = _DATA_DIR / "note_soe_listed_diff.json"
_SOE_TEMPLATE_PATH = _DATA_DIR / "note_template_soe.json"
_LISTED_TEMPLATE_PATH = _DATA_DIR / "note_template_listed.json"

# Cache
_DIFF_CACHE: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# load_diff_data
# ---------------------------------------------------------------------------


#: 四个差异桶的键名（比对与守卫共用，避免各处硬编码）
DIFF_BUCKETS: tuple[str, ...] = (
    "common_sections",
    "soe_only_sections",
    "listed_only_sections",
    "format_diff_sections",
)


#: 各桶用作「可读头部」的键（排序后放在标识前面，便于失败信息定位到具体章节）
_IDENTITY_HEAD_KEYS: dict[str, tuple[str, ...]] = {
    "common_sections": ("soe_section_id", "listed_section_id", "section_title"),
    "format_diff_sections": ("soe_section_id", "listed_section_id", "section_title"),
    "soe_only_sections": ("section_id", "title"),
    "listed_only_sections": ("section_id", "title"),
}


def _bucket_identity(bucket: str, entry: Any) -> tuple[str, ...]:
    """把一个桶条目归一成**载荷完备**的可比对标识。

    形态 = 可读头部（sid / 标题）+ 其余全部字段的规范化序列化。

    🔴 头部之外的字段必须一起进标识（2026-08-07 补）：只比 sid + 标题时，
    ``format_diff_sections`` 的 ``soe_format`` / ``listed_format`` /
    ``field_mapping`` 载荷发生变化**检测不到** —— 而 ``adapt_table_data`` 正是
    拿 ``*_format`` 当目标格式、拿 ``field_mapping`` 当指令，载荷 stale 等于
    「按旧模板结构去适配新模板」。Requirement 1.2 要求比的是**条目集合**，
    载荷是条目的一部分。

    未登记的桶退化为「整条规范化序列化」，缺字段一律取空串（不猜）。
    """
    if not isinstance(entry, dict):
        return (str(entry),)
    head_keys = _IDENTITY_HEAD_KEYS.get(bucket, ())
    head = tuple(str(entry.get(k, "")) for k in head_keys)
    tail = tuple(
        f"{k}={json.dumps(entry[k], sort_keys=True, ensure_ascii=False, default=str)}"
        for k in sorted(entry)
        if k not in head_keys
    )
    return head + tail


def _bucket_sets(data: dict[str, Any]) -> dict[str, set[tuple[str, ...]]]:
    """按桶取条目标识集合（Requirement 1.2 的比对基准：集合而非仅数量）。"""
    out: dict[str, set[tuple[str, ...]]] = {}
    for bucket in DIFF_BUCKETS:
        entries = data.get(bucket)
        items = entries if isinstance(entries, list) else []
        out[bucket] = {_bucket_identity(bucket, e) for e in items}
    return out


def compare_diff_payloads(
    stored: dict[str, Any],
    live: dict[str, Any],
) -> dict[str, Any]:
    """比对落盘与实时两份差异数据（纯函数，供守卫与日志共用）。

    Returns:
        ``{"consistent": bool, "buckets": {bucket: {"only_stored": [...],
        "only_live": [...], "stored_count": int, "live_count": int}}}``

    只比对**条目集合**，不比 ``version`` / ``is_mock`` 等元数据 —— 后者的
    差异由 :func:`load_diff_data` 单独记 WARNING。
    """
    s_sets = _bucket_sets(stored)
    l_sets = _bucket_sets(live)
    buckets: dict[str, Any] = {}
    consistent = True
    for bucket in DIFF_BUCKETS:
        only_stored = sorted(s_sets[bucket] - l_sets[bucket])
        only_live = sorted(l_sets[bucket] - s_sets[bucket])
        if only_stored or only_live:
            consistent = False
        buckets[bucket] = {
            "stored_count": len(s_sets[bucket]),
            "live_count": len(l_sets[bucket]),
            "only_stored": only_stored,
            "only_live": only_live,
        }
    return {"consistent": consistent, "buckets": buckets}


def load_diff_data() -> dict[str, Any]:
    """加载 SOE/Listed 差异数据 —— **实时计算为准**，落盘 JSON 仅作交叉校验。

    spec: soe-listed-note-conversion-correctness / Requirements 1.3

    ------------------------------------------------------------------
    为什么不再「落盘优先」（2026-08-06 实证）
    ------------------------------------------------------------------

    改造前：落盘 ``note_soe_listed_diff.json`` 存在即直接返回，实时计算只作
    文件缺失/损坏时的降级。而该文件实测 **自标 ``is_mock: true`` 且已 stale**
    （落盘 common 106 / listed_only 71 / format_diff 33 vs 实时 107 / 70 / 39，
    ``common`` 集合比对结果 ``False``）⇒ 生产一直在用一份过期的 mock 数据做
    「归档源侧章节 + 新建目标侧空章」的裁决，**会丢已录数据**。

    改造后语义：

    1. 以 :func:`compute_diff_from_templates` 的实时结果为返回值（模板即真源）；
    2. 落盘文件存在时读出来做**交叉校验**，不一致 → WARNING（含差异摘要），
       提示重新生成，但**不改变返回值**；
    3. ``is_mock`` 为真同样 WARNING；
    4. 实时计算失败（模板文件缺失/损坏）才退回落盘（fail-open，避免转换整体不可用）。

    Returns:
        Dict with keys: version, is_mock, common_sections,
        soe_only_sections, listed_only_sections, format_diff_sections
    """
    global _DIFF_CACHE
    if _DIFF_CACHE is not None:
        return _DIFF_CACHE

    live = _compute_from_template_files()
    live_ok = bool(
        live.get("common_sections")
        or live.get("soe_only_sections")
        or live.get("listed_only_sections")
    )

    stored: dict[str, Any] | None = None
    if _DIFF_JSON_PATH.exists():
        try:
            loaded = json.loads(_DIFF_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                stored = loaded
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "note_template_diff: 落盘 %s 读取失败(%s) —— 已改用实时计算结果",
                _DIFF_JSON_PATH.name, e,
            )

    if not live_ok:
        # 实时计算拿不到东西（模板缺失/损坏）→ fail-open 用落盘，绝不返回空
        if stored is not None:
            logger.warning(
                "note_template_diff: 实时计算无结果，降级使用落盘 %s（可能 stale）",
                _DIFF_JSON_PATH.name,
            )
            _DIFF_CACHE = stored
            return stored
        logger.error("note_template_diff: 实时计算与落盘均不可用，返回空差异数据")
        _DIFF_CACHE = live
        return live

    if stored is not None:
        if stored.get("is_mock"):
            logger.warning(
                "note_template_diff: 落盘 %s 标记 is_mock=true（占位数据）"
                " —— 已改用实时计算结果，请重跑 scripts/gen/generate_note_soe_listed_diff.py",
                _DIFF_JSON_PATH.name,
            )
        cmp_result = compare_diff_payloads(stored, live)
        if not cmp_result["consistent"]:
            summary = ", ".join(
                f"{b}: 落盘{d['stored_count']}/实时{d['live_count']}"
                f"(仅落盘{len(d['only_stored'])}/仅实时{len(d['only_live'])})"
                for b, d in cmp_result["buckets"].items()
                if d["only_stored"] or d["only_live"]
            )
            logger.warning(
                "note_template_diff: 落盘 %s 与实时计算不一致 —— 以实时为准。差异摘要: %s",
                _DIFF_JSON_PATH.name, summary,
            )

    _DIFF_CACHE = live
    return live


def reset_diff_cache() -> None:
    """Reset the cached diff data (for testing)."""
    global _DIFF_CACHE, _TEMPLATE_SECTION_CACHE
    _DIFF_CACHE = None
    _TEMPLATE_SECTION_CACHE = None


# ---------------------------------------------------------------------------
# 模板 sections 加载（章节映射需要 sid → section_number 的对照）
# ---------------------------------------------------------------------------

_TEMPLATE_SECTION_CACHE: dict[str, list[dict[str, Any]]] | None = None

#: 侧 → 模板文件路径。与 :func:`_compute_from_template_files` 共用同一组常量，
#: 避免在本 spec 半径内出现第二条模板路径定义。
_TEMPLATE_PATHS: dict[str, pathlib.Path] = {
    "soe": _SOE_TEMPLATE_PATH,
    "listed": _LISTED_TEMPLATE_PATH,
}


def load_template_sections(side: str) -> list[dict[str, Any]]:
    """按侧加载附注模板的 ``sections`` 列表。

    spec: soe-listed-note-conversion-correctness / Requirement 2.1

    章节映射需要「目标侧 ``section_id`` → ``section_number``」的对照（改写
    ``disclosure_notes.note_section`` 用），以及「源侧 (``section_number``,
    ``section_title``) → ``section_id``」的反查（``section_id IS NULL`` 存量行
    回填用，Requirement 2.8）。两者的真源都是模板 JSON。

    Args:
        side: ``"soe"`` 或 ``"listed"``；其余取值返回 ``[]``。

    Returns:
        sections 列表；文件缺失/损坏时返回 ``[]``（fail-open，由调用方按
        「回填不出 → skipped」处置，不让转换整体不可用）。
    """
    global _TEMPLATE_SECTION_CACHE
    if side not in _TEMPLATE_PATHS:
        return []
    if _TEMPLATE_SECTION_CACHE is None:
        _TEMPLATE_SECTION_CACHE = {}
    cached = _TEMPLATE_SECTION_CACHE.get(side)
    if cached is not None:
        return cached

    path = _TEMPLATE_PATHS[side]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sections = data.get("sections") or []
        if not isinstance(sections, list):
            sections = []
    except (OSError, json.JSONDecodeError) as e:
        logger.error("note_template_diff: 模板 %s 加载失败: %s", path.name, e)
        sections = []
    _TEMPLATE_SECTION_CACHE[side] = sections
    return sections


# ---------------------------------------------------------------------------
# compute_diff_from_templates
# ---------------------------------------------------------------------------


def compute_diff_from_templates(
    soe_sections: list[dict[str, Any]],
    listed_sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute diff between SOE and Listed section lists by section_title matching.

    Args:
        soe_sections: List of SOE template section dicts
        listed_sections: List of Listed template section dicts

    Returns:
        Dict with common_sections, soe_only_sections, listed_only_sections,
        format_diff_sections
    """
    soe_by_title = _build_title_index(soe_sections)
    listed_by_title = _build_title_index(listed_sections)

    soe_titles = set(soe_by_title.keys())
    listed_titles = set(listed_by_title.keys())

    common_titles = sorted(soe_titles & listed_titles)
    soe_only_titles = sorted(soe_titles - listed_titles)
    listed_only_titles = sorted(listed_titles - soe_titles)

    common_sections: list[dict[str, Any]] = []
    format_diff_sections: list[dict[str, Any]] = []

    for title in common_titles:
        soe_s = soe_by_title[title]
        listed_s = listed_by_title[title]
        common_sections.append({
            "section_title": title,
            "soe_section_id": soe_s.get("section_id", ""),
            "listed_section_id": listed_s.get("section_id", ""),
        })

        diff = compute_section_diff(soe_s, listed_s)
        if diff.get("has_format_diff"):
            format_diff_sections.append({
                "section_title": title,
                "soe_section_id": soe_s.get("section_id", ""),
                "listed_section_id": listed_s.get("section_id", ""),
                "soe_format": diff["soe_format"],
                "listed_format": diff["listed_format"],
                "field_mapping": diff.get("field_mapping"),
            })

    soe_only_sections = [
        {"section_id": soe_by_title[t].get("section_id", ""), "title": t}
        for t in soe_only_titles
    ]
    listed_only_sections = [
        {"section_id": listed_by_title[t].get("section_id", ""), "title": t}
        for t in listed_only_titles
    ]

    return {
        "version": "1.0.0",
        "is_mock": False,
        "common_sections": common_sections,
        "soe_only_sections": soe_only_sections,
        "listed_only_sections": listed_only_sections,
        "format_diff_sections": format_diff_sections,
    }


# ---------------------------------------------------------------------------
# compute_section_diff
# ---------------------------------------------------------------------------


def compute_section_diff(
    soe_section: dict[str, Any],
    listed_section: dict[str, Any],
) -> dict[str, Any]:
    """Compute diff between a single SOE section and its Listed counterpart.

    Returns:
        Dict with has_format_diff, soe_format, listed_format, field_mapping
    """
    soe_ct = soe_section.get("content_type", "text")
    listed_ct = listed_section.get("content_type", "text")
    soe_tables = len(soe_section.get("tables", []))
    listed_tables = len(listed_section.get("tables", []))

    has_diff = (
        soe_ct != listed_ct
        or (soe_tables > 0 and listed_tables > 0 and soe_tables != listed_tables)
    )

    return {
        "has_format_diff": has_diff,
        "soe_format": {"content_type": soe_ct, "table_count": soe_tables},
        "listed_format": {"content_type": listed_ct, "table_count": listed_tables},
        "field_mapping": None,  # Populated by P-7 auditor annotation
    }


# ---------------------------------------------------------------------------
# adapt_table_data (A.5.11)
# ---------------------------------------------------------------------------


#: ``field_mapping`` 已实现的指令键
SUPPORTED_FIELD_MAPPING_KEYS: frozenset[str] = frozenset({"column_remap", "row_filter"})

#: 曾在 docstring 里声明过但**从未实现**的指令键。
#: 显式登记而不是静默忽略 —— 静默忽略会让调用方以为「已适配」（假成功反馈）。
DECLARED_UNIMPLEMENTED_FIELD_MAPPING_KEYS: frozenset[str] = frozenset({"value_transform"})

#: ``row_filter`` 已实现的子键
_SUPPORTED_ROW_FILTER_KEYS: frozenset[str] = frozenset({"exclude_row_types"})

#: 行内**按列 id 建键**的桶。列 id 改名时这些键必须跟着改，否则值/模式/溯源
#: 与新列 id 失联（改造前只改了 ``_columns_meta[].id``，实测值留在旧键上）。
#: 注：列索引形态的 ``_cell_modes``（键为 ``"0"``/``"1"``）不会命中 remap，天然不受影响。
_ROW_COLUMN_KEYED_BUCKETS: tuple[str, ...] = (
    "values",
    "_cell_modes",
    "_cell_meta",
    "_legacy_cells",
)

# 原因码（Requirement 4.4：零值必须可区分成因）
ADAPT_REASON_NO_FIELD_MAPPING = "no_field_mapping"
ADAPT_REASON_APPLIED = "applied"
ADAPT_REASON_NO_EFFECT = "no_effect"
ADAPT_REASON_UNSUPPORTED_ONLY = "unsupported_only"


@dataclass(frozen=True)
class AdaptReport:
    """``adapt_table_data`` 的可观测结果。

    ``changed`` 是**事实判据**（输出 != 输入），不是「我以为改了」——
    调用方据此决定要不要计入 ``format_adapted_count``，避免把空操作
    上报成「已适配」。
    """

    changed: bool
    reason: str
    applied: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def adapt_table_data(
    table_data: dict[str, Any],
    target_format: dict[str, Any],
    field_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt table_data to target format using column/field remapping（薄壳）.

    保留原签名与返回类型，供既有消费方（``consol_cross_template_service`` /
    ``note_conversion_service``）与既有测试的 patch 点不变；需要知道「到底
    改没改」的调用方走 :func:`adapt_table_data_with_report`。
    """
    adapted, _report = adapt_table_data_with_report(table_data, target_format, field_mapping)
    return adapted


def adapt_table_data_with_report(
    table_data: dict[str, Any],
    target_format: dict[str, Any],
    field_mapping: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], AdaptReport]:
    """把 table_data 适配到目标格式，并如实上报是否真的改了结构。

    spec: soe-listed-note-conversion-correctness / Requirement 1.5（Property 4）

    ------------------------------------------------------------------
    语义（2026-08-07 明确化）
    ------------------------------------------------------------------

    * ``field_mapping`` 为 null / 空 dict / 非 dict → **空操作**：返回深拷贝，
      逐字等于输入，``changed=False`` / ``reason=no_field_mapping``。
      这是现状行为且是**正确**的（实测落盘 39 条 format_diff 的
      ``field_mapping`` 全为 null ⇒ 转换阶段不该擅自改结构）。
    * ``field_mapping`` 非空 → 必须**真正改结构**；改不动时不再静默返回原样，
      而是记 WARNING 并在 ``AdaptReport`` 里给出原因与诊断（``no_effect`` /
      ``unsupported_only``），使调用方能区分「适配了」与「什么都没发生」。

    ------------------------------------------------------------------
    改造前的三处静默空转（2026-08-07 逐个实测）
    ------------------------------------------------------------------

    1. ``column_remap`` **只改 ``_columns_meta[].id``**，行内 dict 形态的
       ``values`` / ``_cell_modes`` 与表级 ``_cell_provenance``（键
       ``"{row_idx}:{col_id}"``）**一个都没跟着改** ⇒ 列改名后值/人工标记/
       溯源全部留在旧列 id 上（人工编辑事实上丢失，属平台已登记的
       「manual 单元格必须保留」红线）。
    2. ``_columns_meta`` 缺失或非 list → 直接 ``return table_data``，
       即便行内确有可改的列键也一律不改。
    3. ``field_mapping`` 只含未实现指令（``value_transform`` 在 docstring
       里写着「支持」但从未实现）→ 静默空操作，而调用方照样
       ``format_adapted_count += 1``。

    Args:
        table_data: 源 table_data（rows / headers / _columns_meta / _cell_provenance…）
        target_format: 目标格式描述（content_type / table_count…）；当前仅作诊断记录
        field_mapping: 可选指令 dict，已实现 ``column_remap`` / ``row_filter``

    Returns:
        ``(adapted_table_data, report)``；``adapted`` 恒为深拷贝，可安全 mutate。
    """
    if not isinstance(table_data, dict):
        return {}, AdaptReport(
            changed=False,
            reason=ADAPT_REASON_NO_FIELD_MAPPING,
            notes=("table_data 非 dict —— 按空表返回",),
        )

    result = deepcopy(table_data)

    if not field_mapping or not isinstance(field_mapping, dict):
        # 无映射 → 保持原结构（现状语义，合法的空操作）
        return result, AdaptReport(changed=False, reason=ADAPT_REASON_NO_FIELD_MAPPING)

    notes: list[str] = []
    applied: list[str] = []

    unsupported = tuple(
        sorted(k for k in field_mapping if k not in SUPPORTED_FIELD_MAPPING_KEYS)
    )
    for key in unsupported:
        if key in DECLARED_UNIMPLEMENTED_FIELD_MAPPING_KEYS:
            notes.append(
                f"field_mapping.{key} 已声明但未实现 —— 结构未按该指令改动"
            )
        else:
            notes.append(
                f"field_mapping.{key} 不是已识别指令"
                f"（已识别: {sorted(SUPPORTED_FIELD_MAPPING_KEYS)}）"
            )

    column_remap = field_mapping.get("column_remap")
    if isinstance(column_remap, dict) and column_remap:
        changed, remap_notes = _apply_column_remap(result, column_remap)
        notes.extend(remap_notes)
        if changed:
            applied.append("column_remap")
    elif "column_remap" in field_mapping:
        notes.append("field_mapping.column_remap 为空或非 dict —— 未生效")

    row_filter = field_mapping.get("row_filter")
    if isinstance(row_filter, dict) and row_filter:
        changed, filter_notes = _apply_row_filter(result, row_filter)
        notes.extend(filter_notes)
        if changed:
            applied.append("row_filter")
    elif "row_filter" in field_mapping:
        notes.append("field_mapping.row_filter 为空或非 dict —— 未生效")

    # `changed` 取事实判据（输出 != 输入），不取 `applied` 的自我声明
    really_changed = result != table_data
    has_recognized = any(k in SUPPORTED_FIELD_MAPPING_KEYS for k in field_mapping)

    if really_changed:
        reason = ADAPT_REASON_APPLIED
    elif unsupported and not has_recognized:
        reason = ADAPT_REASON_UNSUPPORTED_ONLY
    else:
        reason = ADAPT_REASON_NO_EFFECT

    if not really_changed:
        logger.warning(
            "note_template_diff.adapt_table_data: field_mapping 非空(%s)但结构未发生任何改变"
            "(reason=%s, target_format=%s)。诊断: %s",
            sorted(field_mapping.keys()),
            reason,
            target_format if isinstance(target_format, dict) else type(target_format).__name__,
            "; ".join(notes) or "(无)",
        )

    return result, AdaptReport(
        changed=really_changed,
        reason=reason,
        applied=tuple(applied),
        unsupported=unsupported,
        notes=tuple(notes),
    )


def _collect_existing_column_ids(table_data: dict[str, Any]) -> set[str]:
    """收集本表已出现过的列 id（``_columns_meta`` ∪ 行内 dict 形态的列键）。

    撞车检测要用它 —— ``_columns_meta`` 的 id 必须全表唯一（ADR-011 的 CI-3），
    改名撞到既有 id 会产生重复列。
    """
    ids: set[str] = set()
    meta = table_data.get("_columns_meta")
    if isinstance(meta, list):
        for col in meta:
            if isinstance(col, dict) and col.get("id"):
                ids.add(str(col["id"]))
    rows = table_data.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            for bucket_key in _ROW_COLUMN_KEYED_BUCKETS:
                bucket = row.get(bucket_key)
                if isinstance(bucket, dict):
                    ids.update(str(k) for k in bucket)
    return ids


def _remap_dict_keys(
    bucket: dict[Any, Any],
    safe_remap: dict[str, str],
) -> tuple[dict[Any, Any], bool]:
    """按 ``safe_remap`` 改 dict 的键，保持插入顺序；目标键已存在则跳过该项。"""
    changed = False
    out: dict[Any, Any] = {}
    for key, value in bucket.items():
        skey = str(key)
        new_key = safe_remap.get(skey)
        if new_key is not None and new_key not in bucket:
            out[new_key] = value
            changed = True
        else:
            out[key] = value
    return out, changed


def _remap_provenance_keys(
    provenance: dict[Any, Any],
    safe_remap: dict[str, str],
) -> tuple[dict[Any, Any], bool]:
    """改 ``_cell_provenance`` 的键（形态 ``"{row_idx}:{col_id}"``）。"""
    changed = False
    out: dict[Any, Any] = {}
    for key, value in provenance.items():
        skey = str(key)
        if ":" in skey:
            row_part, col_part = skey.split(":", 1)
            new_col = safe_remap.get(col_part)
            if new_col is not None:
                new_key = f"{row_part}:{new_col}"
                if new_key not in provenance:
                    out[new_key] = value
                    changed = True
                    continue
        out[key] = value
    return out, changed


def _apply_column_remap(
    table_data: dict[str, Any],
    column_remap: dict[str, str],
) -> tuple[bool, list[str]]:
    """就地把列 id 从旧改到新，并让值/人工标记/溯源跟随新 id。

    覆盖四处：``_columns_meta[].id`` / 行内 dict 形态的
    ``values``·``_cell_modes``·``_cell_meta``·``_legacy_cells`` /
    表级 ``_cell_provenance``（``"{row_idx}:{col_id}"``）。

    Returns:
        ``(changed, notes)``
    """
    notes: list[str] = []
    pairs = {
        str(old): str(new)
        for old, new in column_remap.items()
        if str(old) != str(new) and str(new)
    }
    if not pairs:
        return False, ["column_remap 的每一项 old == new（或目标为空）—— 无需改动"]

    existing = _collect_existing_column_ids(table_data)

    meta = table_data.get("_columns_meta")
    if not isinstance(meta, list):
        notes.append(
            "table_data 缺 _columns_meta（或非 list）—— 只改行内 dict 形态的列键"
        )

    # 撞车检测：目标 id 已存在（且它本身不会被改走）/ 两个源改成同一目标
    safe: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for old, new in pairs.items():
        if new in existing and new not in pairs:
            notes.append(
                f"列 id 撞车：{old} → {new}，目标 id 已存在于本表，已跳过"
                "（ADR-011 CI-3 要求列 id 全表唯一）"
            )
            continue
        if new in claimed:
            notes.append(
                f"列 id 撞车：{claimed[new]} 与 {old} 都要改名为 {new}，已跳过 {old}"
            )
            continue
        claimed[new] = old
        safe[old] = new

    if not safe:
        return False, notes

    missing = sorted(old for old in safe if old not in existing)
    if missing:
        notes.append(f"column_remap 的源列 id 在本表不存在，未改动: {missing}")

    changed = False

    if isinstance(meta, list):
        for col in meta:
            if not isinstance(col, dict):
                continue
            cid = str(col.get("id", ""))
            if cid in safe:
                col["id"] = safe[cid]
                changed = True

    rows = table_data.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            for bucket_key in _ROW_COLUMN_KEYED_BUCKETS:
                bucket = row.get(bucket_key)
                if not isinstance(bucket, dict):
                    continue
                new_bucket, bucket_changed = _remap_dict_keys(bucket, safe)
                if bucket_changed:
                    row[bucket_key] = new_bucket
                    changed = True

    provenance = table_data.get("_cell_provenance")
    if isinstance(provenance, dict):
        new_prov, prov_changed = _remap_provenance_keys(provenance, safe)
        if prov_changed:
            table_data["_cell_provenance"] = new_prov
            changed = True

    if not changed:
        notes.append("column_remap 未命中任何列 id —— 结构未改动")
    return changed, notes


def _apply_row_filter(
    table_data: dict[str, Any],
    row_filter: dict[str, Any],
) -> tuple[bool, list[str]]:
    """按条件剔除行（当前仅 ``exclude_row_types``），并同步重排行级溯源下标。

    Returns:
        ``(changed, notes)``
    """
    notes: list[str] = []
    unknown = sorted(k for k in row_filter if k not in _SUPPORTED_ROW_FILTER_KEYS)
    for key in unknown:
        notes.append(
            f"row_filter.{key} 不是已识别子键"
            f"（已识别: {sorted(_SUPPORTED_ROW_FILTER_KEYS)}）"
        )

    exclude_types = row_filter.get("exclude_row_types")
    if not isinstance(exclude_types, list) or not exclude_types:
        if "exclude_row_types" in row_filter:
            notes.append("row_filter.exclude_row_types 为空或非 list —— 未生效")
        return False, notes

    rows = table_data.get("rows")
    if not isinstance(rows, list):
        notes.append("table_data.rows 缺失或非 list —— row_filter 未生效")
        return False, notes

    exclude_set = {str(t) for t in exclude_types}
    keep_idx: list[int] = []
    filtered: list[Any] = []
    for idx, row in enumerate(rows):
        if isinstance(row, dict) and str(row.get("row_type", "")) in exclude_set:
            continue
        keep_idx.append(idx)
        filtered.append(row)

    if len(filtered) == len(rows):
        notes.append(f"row_filter 未命中任何行（exclude_row_types={sorted(exclude_set)}）")
        return False, notes

    table_data["rows"] = filtered

    # 行被剔除后，表级 `_cell_provenance` 的行下标必须重排，否则溯源指向错行
    provenance = table_data.get("_cell_provenance")
    if isinstance(provenance, dict) and provenance:
        remap_idx = {str(old): str(new) for new, old in enumerate(keep_idx)}
        new_prov: dict[Any, Any] = {}
        for key, value in provenance.items():
            skey = str(key)
            if ":" in skey:
                row_part, col_part = skey.split(":", 1)
                if row_part not in remap_idx:
                    continue  # 该行已被剔除 → 溯源一并丢弃
                new_prov[f"{remap_idx[row_part]}:{col_part}"] = value
            else:
                new_prov[key] = value
        table_data["_cell_provenance"] = new_prov
        notes.append("row_filter 剔除了行 —— 已同步重排 _cell_provenance 的行下标")

    return True, notes


# ---------------------------------------------------------------------------
# classify_section_mapping (A.5.10)
# ---------------------------------------------------------------------------


def classify_section_mapping(
    section_id: str,
    diff_data: dict[str, Any],
    source_type: str = "soe",
) -> tuple[str, dict[str, Any] | None]:
    """Classify how a section maps between SOE and Listed.

    Args:
        section_id: The section_id to classify
        diff_data: The diff data dict (from load_diff_data)
        source_type: "soe" or "listed" — which template the section_id belongs to

    Returns:
        Tuple of (classification, metadata):
        - ("common", {"target_section_id": "...", ...}) — direct copy
        - ("source_only", None) — exists only in source, archive in target
        - ("target_only", None) — exists only in target, create empty
        - ("format_diff", {"soe_format": ..., "listed_format": ..., "field_mapping": ...})
    """
    if not isinstance(diff_data, dict):
        return ("unknown", None)

    id_field = "soe_section_id" if source_type == "soe" else "listed_section_id"
    target_id_field = "listed_section_id" if source_type == "soe" else "soe_section_id"

    # Check format_diff_sections first (more specific)
    for entry in diff_data.get("format_diff_sections", []):
        if entry.get(id_field) == section_id:
            return ("format_diff", {
                "target_section_id": entry.get(target_id_field, ""),
                "section_title": entry.get("section_title", ""),
                "soe_format": entry.get("soe_format"),
                "listed_format": entry.get("listed_format"),
                "field_mapping": entry.get("field_mapping"),
            })

    # Check common_sections
    for entry in diff_data.get("common_sections", []):
        if entry.get(id_field) == section_id:
            return ("common", {
                "target_section_id": entry.get(target_id_field, ""),
                "section_title": entry.get("section_title", ""),
            })

    # Check source-only sections
    source_only_key = "soe_only_sections" if source_type == "soe" else "listed_only_sections"
    for entry in diff_data.get(source_only_key, []):
        if entry.get("section_id") == section_id:
            return ("source_only", {"title": entry.get("title", "")})

    # Check target-only sections (section exists in target but not source)
    target_only_key = "listed_only_sections" if source_type == "soe" else "soe_only_sections"
    for entry in diff_data.get(target_only_key, []):
        if entry.get("section_id") == section_id:
            return ("target_only", {"title": entry.get("title", "")})

    return ("unknown", None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_title_index(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build section_title -> first section dict."""
    index: dict[str, dict[str, Any]] = {}
    for s in sections:
        if not isinstance(s, dict):
            continue
        title = s.get("section_title", "")
        if title and title not in index:
            index[title] = s
    return index


def _compute_from_template_files() -> dict[str, Any]:
    """Load both template files and compute diff."""
    try:
        soe_data = json.loads(_SOE_TEMPLATE_PATH.read_text(encoding="utf-8"))
        listed_data = json.loads(_LISTED_TEMPLATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Cannot load template files for diff computation: %s", e)
        return {
            "version": "0.0.0",
            "is_mock": False,
            "common_sections": [],
            "soe_only_sections": [],
            "listed_only_sections": [],
            "format_diff_sections": [],
        }

    return compute_diff_from_templates(
        soe_data.get("sections", []),
        listed_data.get("sections", []),
    )
