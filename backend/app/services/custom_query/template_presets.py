"""高级查询系统预置的只读目录、校验与项目参数解析。"""
from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.custom_query.source_registry import resolve_source
from app.services.custom_query.table_whitelist import OPERATOR_WHITELIST
from app.services.custom_query.template_preset_params import resolve_parameter_values

logger = logging.getLogger(__name__)

PRESETS_PATH = Path(__file__).resolve().parents[3] / "data" / "custom_query_presets.json"
PARAM_NAMES = frozenset({"materiality_performance", "cutoff_start", "cutoff_end"})
_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_MAX_CONDITIONS = 20


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    category: str
    description: str
    notes: tuple[str, ...]
    config: dict[str, Any]


@dataclass(frozen=True)
class ResolvedConfig:
    config: dict[str, Any]
    params: list[dict[str, Any]]
    notes: list[str]


class PresetNotFoundError(LookupError):
    """请求的系统预置不存在或未通过加载校验。"""

def _read_document() -> dict[str, Any]:
    value = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("预置文件顶层必须是对象")
    return value


def _ordered_params(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        if "$param" in value:
            found.append(str(value["$param"]))
        for key, item in value.items():
            if key != "$param":
                found.extend(_ordered_params(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_ordered_params(item))
    return list(dict.fromkeys(found))


def validate_preset(
    preset: Any,
    *,
    keyword_sets: Mapping[str, Any] | None = None,
    seen_ids: set[str] | None = None,
) -> list[str]:
    """返回单条预置的全部错误；调用方据此隔离坏条目。"""
    errors: list[str] = []
    if not isinstance(preset, Mapping):
        return ["预置条目必须是对象"]
    preset_id = str(preset.get("id") or "")
    if not _ID_RE.fullmatch(preset_id):
        errors.append("id 必须匹配 ^[a-z0-9_]{1,40}$")
    if seen_ids is not None:
        if preset_id in seen_ids:
            errors.append(f"id 重复：{preset_id}")
        seen_ids.add(preset_id)
    for key in ("name", "category", "description"):
        if not isinstance(preset.get(key), str) or not preset[key].strip():
            errors.append(f"{key} 必须是非空字符串")

    config = preset.get("config")
    if not isinstance(config, Mapping):
        return [*errors, "config 必须是对象"]
    source = str(config.get("source") or "")
    spec = None
    try:
        spec = resolve_source(source).spec
    except Exception:  # resolve_source 以 HTTPException 表达未知源；校验器只返回原因
        errors.append(f"数据源未登记：{source}")
    if spec is None and not any("数据源未登记" in item for item in errors):
        errors.append(f"数据源不支持结构化条件：{source}")

    sets = keyword_sets
    if sets is None:
        try:
            sets = _read_document().get("keyword_sets", {})
        except Exception:
            sets = {}
    condition_keys = {column.key for column in spec.condition_columns} if spec else set()
    conditions = config.get("conditions")
    if not isinstance(conditions, list):
        errors.append("conditions 必须是数组")
        conditions = []
    expanded_count = 0
    for index, condition in enumerate(conditions, start=1):
        if not isinstance(condition, Mapping):
            errors.append(f"第 {index} 条条件必须是对象")
            continue
        field = str(condition.get("field") or "")
        op = str(condition.get("op") or "")
        if field not in condition_keys:
            errors.append(f"第 {index} 条条件字段不可用于该数据源：{field}")
        if op not in OPERATOR_WHITELIST:
            errors.append(f"第 {index} 条条件算子未登记：{op}")
        keyword_set = condition.get("$keyword_set")
        if keyword_set is not None:
            words = sets.get(str(keyword_set)) if isinstance(sets, Mapping) else None
            if not isinstance(words, list) or not words or not all(isinstance(word, str) and word for word in words):
                errors.append(f"第 {index} 条条件词集未登记：{keyword_set}")
            else:
                expanded_count += len(words)
        else:
            expanded_count += 1
        for param in _ordered_params(condition.get("value")):
            if param not in PARAM_NAMES:
                errors.append(f"第 {index} 条条件参数未登记：{param}")
    if expanded_count > _MAX_CONDITIONS:
        errors.append(f"词集展开后条件数 {expanded_count} 超过 {_MAX_CONDITIONS}")

    if config.get("condition_logic") not in ("and", "or"):
        errors.append("condition_logic 必须是 and 或 or")
    sort_field = config.get("sort_field")
    if sort_field is not None:
        sortable = {column.key for column in spec.columns if column.sortable} if spec else set()
        if sort_field not in sortable:
            errors.append(f"sort_field 不可排序：{sort_field}")
    sort_order = config.get("sort_order")
    if sort_order is not None and sort_order not in ("asc", "desc"):
        errors.append("sort_order 必须是 asc 或 desc")
    page_size = config.get("page_size")
    if page_size is not None and (
        isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 2000
    ):
        errors.append("page_size 必须是 1..2000 的整数")
    return errors


@lru_cache(maxsize=1)
def load_presets() -> tuple[Preset, ...]:
    """加载全部有效预置；一条损坏不会让目录整体不可用。"""
    try:
        document = _read_document()
    except Exception as exc:
        logger.error("高级查询预置文件读取失败：%s", exc)
        return ()
    keyword_sets = document.get("keyword_sets", {})
    raw_presets = document.get("presets")
    if not isinstance(raw_presets, list):
        logger.error("高级查询预置文件的 presets 必须是数组")
        return ()
    loaded: list[Preset] = []
    seen_ids: set[str] = set()
    for raw in raw_presets:
        errors = validate_preset(raw, keyword_sets=keyword_sets, seen_ids=seen_ids)
        preset_id = raw.get("id", "<unknown>") if isinstance(raw, Mapping) else "<invalid>"
        if errors:
            logger.error("跳过无效高级查询预置 id=%s：%s", preset_id, "；".join(errors))
            continue
        loaded.append(Preset(
            id=str(raw["id"]),
            name=str(raw["name"]),
            category=str(raw["category"]),
            description=str(raw["description"]),
            notes=tuple(str(note) for note in raw.get("notes", [])),
            config=copy.deepcopy(dict(raw["config"])),
        ))
    return tuple(loaded)


def list_presets() -> list[dict[str, Any]]:
    """返回不含完整查询配置的只读预置目录。"""
    return [{
        "id": preset.id,
        "name": preset.name,
        "category": preset.category,
        "description": preset.description,
        "data_source": preset.config["source"],
        "params": _ordered_params(preset.config),
        "read_only": True,
    } for preset in load_presets()]


def _expand_keyword_sets(config: dict[str, Any], keyword_sets: Mapping[str, Any]) -> None:
    expanded: list[Any] = []
    for condition in config.get("conditions") or []:
        marker = condition.get("$keyword_set") if isinstance(condition, dict) else None
        if marker is None:
            expanded.append(copy.deepcopy(condition))
            continue
        words = keyword_sets.get(str(marker))
        if not isinstance(words, list) or not words:
            raise ValueError(f"模板词集「{marker}」未登记")
        for word in words:
            expanded.append({
                key: copy.deepcopy(value)
                for key, value in condition.items()
                if key != "$keyword_set"
            } | {"value": word})
    config["conditions"] = expanded

def _replace_params(value: Any, resolved: Mapping[str, dict[str, Any]]) -> tuple[Any, list[str]]:
    if isinstance(value, Mapping) and "$param" in value:
        name = str(value["$param"])
        item = resolved[name]
        return item["value"] if item["value"] is not None else "", [name]
    if isinstance(value, list):
        pairs = [_replace_params(item, resolved) for item in value]
        return [item for item, _names in pairs], list(dict.fromkeys(name for _item, names in pairs for name in names))
    return copy.deepcopy(value), []


async def resolve_config(
    db: Any, config: Mapping[str, Any], *, project_id: Any, year: int
) -> ResolvedConfig:
    """深拷贝配置，展开词表，并按目标项目、年度解析全部参数。"""
    resolved_config = copy.deepcopy(dict(config))
    document = _read_document()
    _expand_keyword_sets(resolved_config, document.get("keyword_sets", {}))
    names = _ordered_params(resolved_config.get("conditions", []))
    unknown = [name for name in names if name not in PARAM_NAMES]
    if unknown:
        raise ValueError(f"模板参数「{unknown[0]}」未登记")
    values = await resolve_parameter_values(db, project_id, year, names)
    for condition in resolved_config.get("conditions") or []:
        if not isinstance(condition, dict):
            continue
        condition["value"], used = _replace_params(condition.get("value"), values)
        if used:
            condition["params"] = used
            missing = next((values[name]["missing_reason"] for name in used if values[name]["missing_reason"]), None)
            if missing:
                condition["missing_reason"] = missing
    notes = resolved_config.get("notes")
    return ResolvedConfig(
        config=resolved_config,
        params=[values[name] for name in names],
        notes=[str(note) for note in notes] if isinstance(notes, list) else [],
    )


async def resolve(db: Any, preset_id: str, *, project_id: Any, year: int) -> dict[str, Any]:
    preset = next((item for item in load_presets() if item.id == preset_id), None)
    if preset is None:
        raise PresetNotFoundError(preset_id)
    resolved = await resolve_config(db, preset.config, project_id=project_id, year=year)
    return {
        "id": preset.id, "name": preset.name, "config": resolved.config,
        "params": resolved.params, "notes": list(preset.notes),
    }
