"""导出程序链接口的 OpenAPI 子集：docs/contracts/procedure-chain/openapi.procedure-chain.json
（spec procedure-chain-hardening-and-java-contracts R23）。

真源：请求体、路径 / 查询参数与鉴权方式取自真实应用的 ``app.openapi()``（pydantic 模型）；2xx 的 data 与登记的
错误详情挂到同目录的 JSON Schema 契约（每个接口的 ``x-contract`` 写明对应关系）。这些路由返回普通 dict，FastAPI
生成的响应 schema 是空的 —— 响应形状只认契约。

- 只收 ``OPERATIONS`` 登记的接口，及其请求引用到的组件（传递闭包）。组件按模型名（title）命名：别处出现同名模型时
  FastAPI 会把组件键改成带模块路径的长名，按 title 命名则本文件不受影响。
- 外层信封：成功 ``{code, message, data}``（ResponseWrapperMiddleware）；错误 ``{code, message}``，message 即错误详情；
  422 是 ``{code, message, detail}``（validation_exception_handler），不是 FastAPI 默认的 ``{detail}``。
- 输出不含时间戳、键排序 ⇒ 内容不变就不改文件；``--check`` 按解析后的 JSON 比对（行尾不影响）。

用法（cwd = backend/）::

    python scripts/gen/export_procedure_chain_openapi.py            # 内容变了才写
    python scripts/gen/export_procedure_chain_openapi.py --check    # 只比对：一致退出 0，不一致退出 2 并列出差异
    python scripts/gen/export_procedure_chain_openapi.py --out X    # 指定文件（测试用）

退出码：0 = 一致 / 已写盘；2 = 不一致，或应用里找不到登记的接口（路由改名 / 删除要同步改这里与契约）。
控制台输出只用 ASCII 标记（Windows GBK 控制台）。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Iterator


def _backend_root(start: Path) -> Path:
    for cand in (start, *start.parents):
        if (cand / "app" / "main.py").is_file() and (cand / "migrations").is_dir():
            return cand
    raise RuntimeError(f"未能从 {start} 向上定位 backend/ 根")


BACKEND = _backend_root(Path(__file__).resolve().parent)
CONTRACTS = BACKEND.parent / "docs" / "contracts" / "procedure-chain"
OUTPUT = CONTRACTS / "openapi.procedure-chain.json"
TAG = "procedure-chain"
TEXT = "string"  # 错误详情是一句中文（HTTPException.detail 为字符串）
_COMPONENT_REF = "#/components/schemas/"
_ENVELOPE = "common.schema.json#/$defs/responseEnvelope"
_VALIDATION = "common.schema.json#/$defs/validationErrorBody"
_UNAVAILABLE = "trimmed-scope.schema.json#/$defs/unavailable"
_ERROR_TEXT = {
    "400": "请求被拒（委派被拒时 message 带 reason / cycles）",
    "409": "冲突：已被他人分配、凭证已消费 / 过期 / 被篡改、目标版本已变化",
    "503": "读不到粗裁结果，停止执行（fail-closed）",
}

#: 登记的接口：request = 请求体对应的契约定义；response = 2xx 的 data；errors = 状态码 → message 的可能形状
OPERATIONS: tuple[dict[str, Any], ...] = (
    {"method": "post", "path": "/api/projects/{pid}/procedure-trim/preview",
     "request": "trimmed-scope.schema.json#/$defs/previewRequest",
     "response": "trimmed-scope.schema.json#/$defs/previewResponse"},
    {"method": "post", "path": "/api/projects/{pid}/procedure-trim/apply",
     "request": "trimmed-scope.schema.json#/$defs/applyRequest",
     "response": "trimmed-scope.schema.json#/$defs/applyResponse"},
    {"method": "post", "path": "/api/projects/{project_id}/working-papers/generate",
     "request": "generation-receipt.schema.json#/$defs/templateSetGenerateRequest",
     "response": "generation-receipt.schema.json#/$defs/templateSetGenerateResponse",
     "errors": {"503": (_UNAVAILABLE,)}},
    {"method": "post", "path": "/api/projects/{project_id}/working-papers/generate-from-codes",
     "request": "generation-receipt.schema.json#/$defs/generateFromCodesRequest",
     "response": "generation-receipt.schema.json#/$defs/generateFromCodesResponse",
     "errors": {"503": (_UNAVAILABLE,)}},
    {"method": "post", "path": "/api/projects/{pid}/procedure-delegations/preview",
     "request": "delegation-preview.schema.json#/$defs/request",
     "response": "delegation-preview.schema.json",
     "errors": {"503": (_UNAVAILABLE,)}},
    {"method": "post", "path": "/api/projects/{pid}/procedure-delegations/apply",
     "request": "delegation-apply.schema.json#/$defs/request",
     "response": "delegation-apply.schema.json",
     "errors": {"400": ("delegation-apply.schema.json#/$defs/rejection", TEXT),
                "409": ("delegation-apply.schema.json#/$defs/conflictError", TEXT),
                "503": (_UNAVAILABLE,)}},
    {"method": "get", "path": "/api/workpapers/{wp_id}/program-row-access",
     "response": "program-row-identity.schema.json#/$defs/rowAccess"},
    {"method": "post", "path": "/api/workpapers/field-overrides/batch",
     "request": "program-row-patch.schema.json#/$defs/request",
     "response": "program-row-patch.schema.json"},
)


def live_spec() -> dict:
    """真实应用的完整 OpenAPI（只导入、不启动）。"""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 别处路由的重复 operationId 等告警与本子集无关
        from app.main import app

        return app.openapi()


def _envelope(data_ref: str) -> dict:
    return {"allOf": [{"$ref": _ENVELOPE}], "required": ["data"], "properties": {"data": {"$ref": data_ref}}}


def _error(alternatives: tuple[str, ...]) -> dict:
    alts = [{"type": "string"} if a == TEXT else {"$ref": a} for a in alternatives]
    return {"allOf": [{"$ref": _ENVELOPE}], "properties": {"message": alts[0] if len(alts) == 1 else {"anyOf": alts}}}


def _json(schema: dict) -> dict:
    return {"application/json": {"schema": schema}}


def _operation(entry: dict, live: dict) -> dict:
    op = {k: copy.deepcopy(live[k]) for k in ("operationId", "summary", "parameters", "requestBody", "security")
          if k in live}
    op["tags"] = [TAG]
    responses = {
        "200": {"description": "成功：data 见 x-contract.response", "content": _json(_envelope(entry["response"]))},
        "422": {"description": "请求参数校验失败", "content": _json({"$ref": _VALIDATION})},
    }
    for status, alts in entry.get("errors", {}).items():
        responses[status] = {"description": _ERROR_TEXT[status], "content": _json(_error(alts))}
    op["responses"] = responses
    contract: dict[str, Any] = {"response": entry["response"]}
    if entry.get("request"):
        contract["request"] = entry["request"]
    if entry.get("errors"):
        contract["errors"] = {status: list(alts) for status, alts in entry["errors"].items()}
    op["x-contract"] = contract
    return op


def iter_component_refs(node: Any) -> Iterator[str]:
    """``#/components/schemas/<名>`` 形式的引用名。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(_COMPONENT_REF):
                yield value[len(_COMPONENT_REF):]
            else:
                yield from iter_component_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_component_refs(value)


def _closure(roots: list[str], schemas: dict) -> list[str]:
    seen: set[str] = set()
    todo = list(roots)
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo.extend(iter_component_refs(schemas[name]))
    return sorted(seen)


def _rename_refs(node: Any, names: dict[str, str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_COMPONENT_REF):
            node["$ref"] = _COMPONENT_REF + names[ref[len(_COMPONENT_REF):]]
        for value in node.values():
            _rename_refs(value, names)
    elif isinstance(node, list):
        for value in node:
            _rename_refs(value, names)


def build_subset(spec: dict) -> tuple[dict, list[str]]:
    """返回（子集文档, 应用里找不到的登记接口）。"""
    paths: dict[str, dict] = {}
    missing: list[str] = []
    for entry in OPERATIONS:
        live = spec.get("paths", {}).get(entry["path"], {}).get(entry["method"])
        if live is None:
            missing.append(f"{entry['method'].upper()} {entry['path']}")
            continue
        paths.setdefault(entry["path"], {})[entry["method"]] = _operation(entry, live)
    components = spec.get("components", {})
    schemas = components.get("schemas", {})
    keys = _closure(list(iter_component_refs(paths)), schemas)
    titles = {key: schemas[key].get("title") or key for key in keys}
    clashes = {t for t in titles.values() if list(titles.values()).count(t) > 1}
    names = {key: (key if titles[key] in clashes else titles[key]) for key in keys}
    picked = {names[key]: copy.deepcopy(schemas[key]) for key in keys}
    _rename_refs(paths, names)
    _rename_refs(picked, names)
    schemes = sorted({name for item in paths.values() for op in item.values()
                      for req in op.get("security", []) for name in req})
    doc = {
        "openapi": spec.get("openapi", "3.1.0"),
        "info": {
            "title": "程序链接口子集（程序裁剪 → 底稿生成 → 委派 → 可见性）",
            "version": "v1",
            "description": ("生成物，勿手改：backend/scripts/gen/export_procedure_chain_openapi.py。请求体取自真实应用；"
                            "响应 data 与错误详情见同目录的 JSON Schema 契约（各接口 x-contract），外层信封见 "
                            "common.schema.json。说明见 README.md。"),
        },
        "tags": [{"name": TAG, "description": "程序链：粗裁、生成、委派、程序行归属与覆盖值"}],
        "paths": paths,
        "components": {
            "schemas": picked,
            "securitySchemes": {n: copy.deepcopy(components.get("securitySchemes", {})[n]) for n in schemes},
        },
    }
    return doc, missing


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _fmt(loc: tuple) -> str:
    return " > ".join(str(p) for p in loc) or "<根>"


def diff(stored: Any, live: Any, loc: tuple = ()) -> list[str]:
    """逐键比对：``-`` 文件里有、应用里没有；``+`` 应用里有、文件里没有；``~`` 两边都有但不同。"""
    if isinstance(stored, dict) and isinstance(live, dict):
        out: list[str] = []
        for key in sorted(set(stored) | set(live)):
            here = (*loc, key)
            if key not in live:
                out.append(f"- {_fmt(here)}")
            elif key not in stored:
                out.append(f"+ {_fmt(here)}")
            else:
                out.extend(diff(stored[key], live[key], here))
        return out
    return [] if stored == live else [f"~ {_fmt(loc)}"]


def write_if_changed(path: Path, text: str) -> bool:
    """内容（不计行尾）不变就不写，返回是否写了。"""
    if path.is_file() and path.read_bytes().decode("utf-8").replace("\r\n", "\n") == text:
        return False
    path.write_bytes(text.encode("utf-8"))
    return True


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="导出程序链接口的 OpenAPI 子集")
    parser.add_argument("--check", action="store_true", help="只比对，不写")
    parser.add_argument("--out", type=Path, default=OUTPUT, help="输出文件（默认契约目录下的 openapi.procedure-chain.json）")
    args = parser.parse_args(argv)

    doc, missing = build_subset(live_spec())
    if missing:
        print("[ERR] 应用里找不到登记的接口（路由改名 / 删除要同步改本脚本的 OPERATIONS 与契约）：")
        for item in missing:
            print(f"  {item}")
        return 2
    count = sum(len(item) for item in doc["paths"].values())
    text = render(doc)
    if args.check:
        try:
            stored = json.loads(args.out.read_bytes().decode("utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[ERR] 读不到 {args.out}：{exc}")
            return 2
        changes = diff(stored, json.loads(text))
        if not changes:
            print(f"[OK] {args.out.name} 与应用一致：{count} 个接口、{len(doc['components']['schemas'])} 个组件")
            return 0
        print(f"[ERR] {args.out.name} 与应用不一致（{len(changes)} 处；- 文件里有、应用里没有，+ 反之，~ 不同）：")
        for line in changes[:50]:
            print(f"  {line}")
        if len(changes) > 50:
            print(f"  ... 另有 {len(changes) - 50} 处")
        print("  -> 不带 --check 重跑写盘，并核对契约（x-contract 指向的 schema）是否要随之修改")
        return 2
    if write_if_changed(args.out, text):
        print(f"[OK] 已写入 {args.out}：{count} 个接口")
    else:
        print(f"[OK] 内容未变，未改文件 {args.out.name}：{count} 个接口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
