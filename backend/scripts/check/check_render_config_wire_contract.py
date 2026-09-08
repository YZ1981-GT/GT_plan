"""双向校验 Pydantic render-config 模型与前端 Wire 类型。

检查字段集合、JSON 类型、可选性与 nullability；任一方向存在差集都会失败。
TypeScript 解析先剥离注释，并对不支持的 interface 形态 fail-closed。
"""

from __future__ import annotations

import argparse
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Union, get_args, get_origin

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.render_config_contract import (  # noqa: E402
    CrossRefItem,
    RenderConfigResponse,
    RenderDecisionWire,
    RenderPermissions,
    SheetRenderConfig,
)
from scripts.gen.generate_component_capability_manifest import (  # noqa: E402
    SourceExtractionError,
    _scan_balanced,
    _split_top_level,
    strip_ts_comments,
)

DEFAULT_FRONTEND_PATH = (
    ROOT / "audit-platform" / "frontend" / "src" / "types" / "renderConfig.ts"
)
MODEL_INTERFACES: tuple[tuple[type[BaseModel], str], ...] = (
    (RenderConfigResponse, "RenderConfigWire"),
    (SheetRenderConfig, "SheetRenderConfigWire"),
    (CrossRefItem, "CrossRefWire"),
    (RenderPermissions, "RenderPermissionsWire"),
    (RenderDecisionWire, "RenderDecisionWire"),
)


class WireContractError(ValueError):
    """契约源无法安全解析。"""


@dataclass(frozen=True, slots=True)
class FieldShape:
    kind: str
    optional: bool
    nullable: bool


@dataclass(frozen=True, slots=True)
class ContractDiff:
    missing_in_frontend: tuple[str, ...]
    missing_in_backend: tuple[str, ...]
    mismatched: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (
            self.missing_in_frontend
            or self.missing_in_backend
            or self.mismatched
        )

    def describe(self) -> str:
        if self.ok:
            return "render-config backend/frontend wire contract is equivalent"
        parts: list[str] = []
        if self.missing_in_frontend:
            parts.append(
                "backend-only=" + ",".join(self.missing_in_frontend)
            )
        if self.missing_in_backend:
            parts.append(
                "frontend-only=" + ",".join(self.missing_in_backend)
            )
        if self.mismatched:
            parts.append("shape-mismatch=" + ";".join(self.mismatched))
        return " | ".join(parts)


def _without_none(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin not in (Union, types.UnionType):
        return annotation, False
    args = get_args(annotation)
    nullable = type(None) in args
    remaining = tuple(item for item in args if item is not type(None))
    if len(remaining) != 1:
        raise WireContractError(f"不支持的后端 union: {annotation!r}")
    return remaining[0], nullable


def _python_kind(annotation: Any) -> tuple[str, bool]:
    base, nullable = _without_none(annotation)
    origin = get_origin(base)
    if base is str:
        return "string", nullable
    if base in (int, float):
        return "number", nullable
    if base is bool:
        return "boolean", nullable
    if origin is list:
        return "array", nullable
    if origin in (dict, Mapping) or base is dict:
        return "object", nullable
    if isinstance(base, type) and issubclass(base, BaseModel):
        return "object", nullable
    raise WireContractError(f"不支持的后端字段类型: {annotation!r}")


def backend_contract() -> dict[str, FieldShape]:
    result: dict[str, FieldShape] = {}
    for model, interface_name in MODEL_INTERFACES:
        for python_name, field in model.model_fields.items():
            wire_name = field.serialization_alias or field.alias or python_name
            kind, nullable = _python_kind(field.annotation)
            key = f"{interface_name}.{wire_name}"
            if key in result:
                raise WireContractError(f"后端字段重复: {key}")
            result[key] = FieldShape(
                kind=kind,
                optional=not field.is_required(),
                nullable=nullable,
            )
    return result


def _extract_interface(source: str, interface_name: str) -> dict[str, str]:
    marker = f"export interface {interface_name}"
    starts = [
        index
        for index in range(len(source))
        if source.startswith(marker, index)
    ]
    if len(starts) != 1:
        raise WireContractError(
            f"{interface_name} 声明数量必须为 1，实际 {len(starts)}"
        )
    brace = source.find("{", starts[0] + len(marker))
    if brace < 0:
        raise WireContractError(f"{interface_name} 缺少 '{{'")
    try:
        end = _scan_balanced(source, brace, "{", "}")
    except SourceExtractionError as exc:
        raise WireContractError(str(exc)) from exc

    fields: dict[str, str] = {}
    for line_number, raw_line in enumerate(source[brace + 1 : end].splitlines(), 1):
        line = raw_line.strip().rstrip(";")
        if not line:
            continue
        if ":" not in line:
            raise WireContractError(
                f"{interface_name} 第 {line_number} 行不是字段声明: {line!r}"
            )
        raw_name, raw_type = line.split(":", 1)
        raw_name = raw_name.strip()
        optional = raw_name.endswith("?")
        name = raw_name[:-1] if optional else raw_name
        if not name.replace("_", "a").isalnum() or name[0].isdigit():
            raise WireContractError(
                f"{interface_name} 字段名不受支持: {raw_name!r}"
            )
        if name in fields:
            raise WireContractError(f"{interface_name} 字段重复: {name}")
        fields[name] = ("optional:" if optional else "required:") + raw_type.strip()
    return fields


def _typescript_kind(type_expression: str) -> tuple[str, bool]:
    try:
        union_parts = [
            part.strip()
            for part in _split_top_level(type_expression, delimiter="|")
            if part.strip()
        ]
    except SourceExtractionError as exc:
        raise WireContractError(str(exc)) from exc
    nullable = "null" in union_parts
    parts = [part for part in union_parts if part not in {"null", "undefined"}]
    if not parts:
        raise WireContractError(f"空 TypeScript 类型: {type_expression!r}")

    kinds: set[str] = set()
    for part in parts:
        compact = "".join(part.split())
        if compact == "string" or compact in {"WpComponentType", "SheetContentType"}:
            kinds.add("string")
        elif compact == "number":
            kinds.add("number")
        elif compact == "boolean":
            kinds.add("boolean")
        elif compact.endswith("[]") or compact.startswith("Array<"):
            kinds.add("array")
        elif compact.startswith("Record<") or compact.endswith("Wire"):
            kinds.add("object")
        elif (compact.startswith("'") and compact.endswith("'")) or (
            compact.startswith('"') and compact.endswith('"')
        ):
            kinds.add("string")
        else:
            raise WireContractError(f"不支持的 TypeScript 类型: {part!r}")
    if len(kinds) != 1:
        raise WireContractError(
            f"TypeScript union 跨 JSON 类型: {type_expression!r} -> {sorted(kinds)}"
        )
    return kinds.pop(), nullable


def frontend_contract(path: Path = DEFAULT_FRONTEND_PATH) -> dict[str, FieldShape]:
    try:
        source = strip_ts_comments(path.read_text(encoding="utf-8"))
    except (OSError, SourceExtractionError) as exc:
        raise WireContractError(f"无法读取前端 wire: {exc}") from exc

    result: dict[str, FieldShape] = {}
    for _, interface_name in MODEL_INTERFACES:
        for field_name, encoded in _extract_interface(source, interface_name).items():
            optional_marker, type_expression = encoded.split(":", 1)
            kind, nullable = _typescript_kind(type_expression)
            key = f"{interface_name}.{field_name}"
            if key in result:
                raise WireContractError(f"前端字段重复: {key}")
            result[key] = FieldShape(
                kind=kind,
                optional=optional_marker == "optional",
                nullable=nullable,
            )
    return result


def check_contract(path: Path = DEFAULT_FRONTEND_PATH) -> ContractDiff:
    backend = backend_contract()
    frontend = frontend_contract(path)
    backend_keys = set(backend)
    frontend_keys = set(frontend)
    mismatched = tuple(
        f"{key}: backend={backend[key]}, frontend={frontend[key]}"
        for key in sorted(backend_keys & frontend_keys)
        if backend[key] != frontend[key]
    )
    return ContractDiff(
        missing_in_frontend=tuple(sorted(backend_keys - frontend_keys)),
        missing_in_backend=tuple(sorted(frontend_keys - backend_keys)),
        mismatched=mismatched,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", type=Path, default=DEFAULT_FRONTEND_PATH)
    args = parser.parse_args()
    try:
        diff = check_contract(args.frontend)
    except WireContractError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    print(f"[{'OK' if diff.ok else 'FAIL'}] {diff.describe()}")
    return 0 if diff.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
