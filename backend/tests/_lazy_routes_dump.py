"""test_lazy_api_routes 的子进程助手：导入 app.main（是否推迟由 GT_LAZY_ROUTES 决定），物化全部路由，
把逐条路由签名（轻属性 + 物化后的结构）与 OpenAPI 摘要写到 argv[1]。不连库、不跑 lifespan。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GT_BOOTSTRAP_DONE", "1")

_t = time.perf_counter()
from app.main import app  # noqa: E402

IMPORT_S = time.perf_counter() - _t
from fastapi.routing import APIRoute  # noqa: E402

from app.core import lazy_api_routes as lar  # noqa: E402

_ADDR = re.compile(r" at 0x[0-9A-Fa-f]+")


def _r(x) -> str:
    return _ADDR.sub("", repr(x))


def _field(f):
    if f is None:
        return None
    info = getattr(f, "field_info", None)
    return [getattr(f, "name", None), getattr(f, "mode", None), _r(getattr(info, "annotation", None)), getattr(f, "alias", None)]


def _dep(d, depth=0):
    if d is None or depth > 12:
        return None
    return [
        getattr(d.call, "__qualname__", _r(d.call)) if d.call is not None else None,
        d.name,
        [_field(p) for p in d.path_params],
        [_field(p) for p in d.query_params],
        [_field(p) for p in d.header_params],
        [_field(p) for p in d.cookie_params],
        [_field(p) for p in d.body_params],
        [_dep(s, depth + 1) for s in d.dependencies],
        d.use_cache,
    ]


_CHEAP = ("path", "name", "methods", "unique_id", "status_code", "tags", "summary", "description", "response_description",
          "deprecated", "operation_id", "include_in_schema", "response_model", "response_class", "openapi_extra",
          "response_model_include", "response_model_exclude", "response_model_by_alias", "response_model_exclude_unset",
          "response_model_exclude_defaults", "response_model_exclude_none", "strict_content_type", "path_format",
          "stream_item_type", "responses")

pending_before = len(lar.pending_routes(app.router.routes))
_t = time.perf_counter()
failures = lar.materialize_all(app.router.routes)
materialize_s = time.perf_counter() - _t
routes = []
for route in app.router.routes:
    if not isinstance(route, APIRoute):
        routes.append(["non-api", type(route).__name__, getattr(route, "path", None)])
        continue
    routes.append([
        sorted(k for k in vars(route) if k != "_gt_lazy_args"),
        {k: _r(getattr(route, k, None)) for k in _CHEAP},
        [_r(getattr(d, "dependency", d)) for d in route.dependencies],
        route.path_regex.pattern,
        _dep(route.dependant),
        _field(route.body_field),
        _field(route.response_field),
        _field(route.stream_item_field),
        sorted(str(k) for k in route.response_fields),
        route._embed_body_fields,
        route.is_sse_stream,
        route.is_json_stream,
        getattr(route.endpoint, "__qualname__", _r(route.endpoint)),
    ])
blob = json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True).encode("utf-8")
out = {
    "enabled": lar.is_enabled(),
    "import_s": round(IMPORT_S, 2),
    "pending_before": pending_before,
    "materialize_s": round(materialize_s, 2),
    "failures": failures,
    "lazy_classes": sum(isinstance(r, lar.LazyAPIRoute) for r in app.router.routes),
    "routes": routes,
    "openapi_sha256": hashlib.sha256(blob).hexdigest(),
}
Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
