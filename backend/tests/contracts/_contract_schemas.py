"""程序链契约（docs/contracts/procedure-chain）的加载与校验助手：SQLite 契约用例与 PG 契约用例共用。

schema 文件不写 ``$schema``（IDE 会去下载远程元模式），方言固定按 JSON Schema 2020-12；``$id`` 只作标识，
注册表把 ``$id`` 映射到本地文件内容，相对 ``$ref`` 按 ``$id`` 解析。
"""
from __future__ import annotations

import functools
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "procedure-chain"
CASES = CONTRACTS / "cases"
BASE_ID = "https://contracts.gt-plan.local/procedure-chain/v1/"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_path(name: str) -> Path:
    return CONTRACTS / f"{name}.schema.json"


def load_schema(name: str) -> dict:
    return load_json(schema_path(name))


def load_cases(name: str) -> dict:
    return load_json(CASES / f"{name}.cases.json")


@functools.lru_cache(maxsize=1)
def registry() -> Registry:
    resources = []
    for path in sorted(CONTRACTS.glob("*.schema.json")):
        schema = load_json(path)
        resources.append((schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def validator(name: str, pointer: str | None = None) -> Draft202012Validator:
    """``pointer`` = 片段（如 ``/$defs/decision``）：校验 schema 里的某个子定义。"""
    schema = load_schema(name)
    if pointer:
        schema = {"$ref": f"{schema['$id']}#{pointer}"}
    return Draft202012Validator(schema, registry=registry())


def errors_of(name: str, instance: Any, pointer: str | None = None) -> list[str]:
    errs = sorted(validator(name, pointer).iter_errors(instance), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errs]


def assert_valid(name: str, instance: Any, pointer: str | None = None) -> None:
    errs = errors_of(name, instance, pointer)
    assert not errs, f"{name}{'#' + pointer if pointer else ''} 不符合契约：\n" + "\n".join(errs[:12])


def jsonable(value: Any) -> Any:
    """库里的值 → JSON（Java 侧按同一规则映射）：UUID → 小写字符串，时间 → ISO 8601，其余原样。"""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):  # SQLite 丢时区；契约要求带偏移（PG timestamptz 本就带）
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    return value


def orm_row(obj: Any) -> dict:
    """ORM 对象 → 按列名的 JSON 行（与表结构一一对应，Java 读同一张表）。"""
    return {c.name: jsonable(getattr(obj, c.key)) for c in obj.__table__.columns}


def mapping_row(row: Any) -> dict:
    """原生 SQL 结果行 → JSON 行。"""
    return {k: jsonable(v) for k, v in row._mapping.items()}


def iter_refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_refs(item)
