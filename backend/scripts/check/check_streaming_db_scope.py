"""流式路由 DB 作用域棘轮守卫（spec platform-heavy-jobs-and-capacity-closure A6）。

背景：返回 `StreamingResponse` / `FileResponse` 的路由若仍用**请求级**
`Depends(get_db)`，session 会一直活到响应体发完 —— 大文件下载期间占住一个
连接，6000 并发下直接打满连接池。

口径（AST，不 import 应用）：
- 路由函数（`@router.get/post/put/delete/patch`）
- 返回 `StreamingResponse` / `FileResponse`
- 签名里 `db` 用 `Depends(get_db)` 且**未**带 `scope="function"`

处置：**冻结棘轮**。现算 112 个候选，逐条迁移需要先判「响应生成器是否仍读 DB」
（读 DB 的不能简单改 scope），属独立 spec 工作量。本守卫保证：
1. 候选数**只减不增**（新增流式路由必须一开始就 function-scope）；
2. 基线文件缺失即失败（不能静默退化成「无候选」）；
3. 基线**不得虚高**（防止把数字改大来蒙过关）。

用法：
    python -m scripts.check.check_streaming_db_scope --check
    python -m scripts.check.check_streaming_db_scope --write   # 只在候选数下降时
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_APP = _REPO_ROOT / "backend" / "app"
_BASELINE = _REPO_ROOT / "backend" / "data" / "streaming_db_scope_baseline.json"

_STREAM_TYPES = {"StreamingResponse", "FileResponse"}

#: 基线虚高上限：基线数不得比现算数多出这个值以上（防「改大基线蒙过关」）。
_MAX_BASELINE_INFLATION = 5


def _is_route(node: ast.AST) -> bool:
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            if dec.func.attr in {"get", "post", "put", "delete", "patch"}:
                return True
    return False


def _returns_stream(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return) and sub.value is not None:
            dumped = ast.dump(sub.value)
            if any(t in dumped for t in _STREAM_TYPES):
                return True
    return False


def _has_request_db(node: ast.AST) -> bool:
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    all_args = positional + list(args.kwonlyargs)
    pad = [None] * (len(positional) - len(args.defaults))
    pos_defaults = pad + list(args.defaults)
    kw_defaults = list(args.kw_defaults)

    for idx, arg in enumerate(all_args):
        if arg.arg != "db":
            continue
        default = None
        if idx < len(positional):
            default = pos_defaults[idx] if idx < len(pos_defaults) else None
        else:
            kw_idx = idx - len(positional)
            if kw_idx < len(kw_defaults):
                default = kw_defaults[kw_idx]
        if default is None:
            continue
        dumped = ast.dump(default)
        if "get_db" not in dumped:
            continue
        if "function" in dumped:
            return False
        return True
    return False


def scan() -> list[dict[str, object]]:
    """返回全部候选（file / function / lineno）。"""
    found: list[dict[str, object]] = []
    for path in sorted(_BACKEND_APP.rglob("*.py")):
        rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_route(node):
                continue
            if not _returns_stream(node):
                continue
            if _has_request_db(node):
                found.append({"file": rel, "function": node.name, "lineno": node.lineno})
    return sorted(found, key=lambda x: (str(x["file"]), int(x["lineno"])))


def _load_baseline() -> dict | None:
    if not _BASELINE.exists():
        return None
    try:
        return json.loads(_BASELINE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_baseline(candidates: list[dict[str, object]]) -> None:
    _BASELINE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "_source": "scripts/check/check_streaming_db_scope.py",
        "criteria": (
            "路由返回 StreamingResponse/FileResponse 且 db 为请求级 "
            "Depends(get_db)（未带 scope='function'）"
        ),
        "count": len(candidates),
        "candidates": candidates,
    }
    _BASELINE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="流式路由 DB 作用域棘轮")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    candidates = scan()
    current = len(candidates)

    if args.write:
        old = _load_baseline()
        if old is not None and current > int(old.get("count") or 0):
            print(
                f"[FAIL] 拒绝上调基线：{old.get('count')} → {current}。"
                "新增流式路由必须一开始就 function-scope。",
                file=sys.stderr,
            )
            return 1
        _write_baseline(candidates)
        print(f"[OK] 基线已写入：{current} 个候选 → {_BASELINE}")
        return 0

    baseline = _load_baseline()
    if baseline is None:
        print(
            f"[FAIL] 缺少或无法解析基线 {_BASELINE}；先跑 --write",
            file=sys.stderr,
        )
        return 1
    base_count = int(baseline.get("count") or 0)

    # 基线不得虚高（防「改大基线蒙过关」）
    if base_count - current > _MAX_BASELINE_INFLATION:
        print(
            f"[FAIL] 基线虚高：基线 {base_count} 比现算 {current} 多出 "
            f"{base_count - current}（上限 {_MAX_BASELINE_INFLATION}）；"
            "请用 --write 重新冻结",
            file=sys.stderr,
        )
        return 1

    if current > base_count:
        base_keys = {(c["file"], c["function"]) for c in baseline.get("candidates") or []}
        new = [c for c in candidates if (c["file"], c["function"]) not in base_keys]
        print(
            f"[FAIL] 候选增加：{base_count} → {current}。新增的流式路由必须 function-scope：",
            file=sys.stderr,
        )
        for c in new:
            print(f"  {c['file']}:{c['lineno']} {c['function']}", file=sys.stderr)
        return 1

    if current < base_count:
        print(
            f"[OK] 候选下降：{base_count} → {current}（可跑 --write 收紧基线）"
        )
        return 0

    print(f"[OK] 流式路由 DB 作用域候选：{current}（等于基线，只减不增）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
