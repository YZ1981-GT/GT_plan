"""后端产出的底稿跳转路由形态夹具（spec acnr-foundation-defect-closure T16 / RV7.5-01）。

``fixtures/frontend_route_shapes.json`` 由前端 ``src/router/__tests__/backendRouteShapes.contract.spec.ts`` 读取：
逐个形态（占位符换成样例值）用真实路由表 ``router.resolve``，断言命中的不是 404 兜底路由。本测试用 AST 扫
``backend/app`` 守夹具不过期：凡是赋给「路由」的站内路由字符串（f-string 也算；以 ``/`` 开头、不是 ``/api/``）
且含 ``/workpapers``，都必须登记。

「赋给路由」的口径（AST，注释 / docstring 不计）：
- 关键字参数名含 ``route``（``jump_route=`` / ``route=``）；
- 赋值目标名含 ``route``（``route = … if … else f"…"``）；
- 函数名含 ``route`` 的 ``return``。
API 路径（``/api/…``，含 ``router = APIRouter(prefix=…)``）排除；``@router.get("/workpapers/{wp_id}/…")`` 装饰器、
``"/workpapers/" in p`` 这类比较不在上述位置，自然不计。

目录 ``jump_route_template`` 不在源码里，由前端测试直接读 ``backend/data/acnr/global_catalog.json``。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
FIXTURE = Path(__file__).with_name("fixtures") / "frontend_route_shapes.json"
def is_site_workpaper_route(text: str) -> bool:
    return text.startswith("/") and not text.startswith(("/api/", "//")) and "/workpapers" in text


def _render(node: ast.AST) -> str | None:
    """字符串常量或 f-string → 形态文本（插值写成 ``{…}``）；其余返回 None。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            parts.append(v.value if isinstance(v, ast.Constant) else "{…}")
        return "".join(parts)
    return None


def _route_strings(value: ast.AST) -> list[str]:
    out = []
    # f-string 内部的常量片段不单独计（只计整串）
    pieces = {id(v) for sub in ast.walk(value) if isinstance(sub, ast.JoinedStr) for v in sub.values}
    for sub in ast.walk(value):
        if id(sub) in pieces:
            continue
        text = _render(sub)
        if text is not None and is_site_workpaper_route(text):
            out.append(text)
    return out


def scan_source(rel: str, src: str) -> set[tuple[str, str]]:
    tree = ast.parse(src)
    found: set[tuple[str, str]] = set()

    def add(value: ast.AST | None) -> None:
        if value is not None:
            found.update((rel, s) for s in _route_strings(value))

    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg and "route" in node.arg:
            add(node.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and "route" in t.id for t in targets):
                add(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "route" in node.name:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return):
                    add(sub.value)
    return found


def scan_app() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for f in sorted(APP.rglob("*.py")):
        src = f.read_text(encoding="utf-8-sig", errors="replace")
        if "/workpapers" not in src:
            continue
        found |= scan_source(f.relative_to(APP).as_posix(), src)
    return found


def _fixture() -> set[tuple[str, str]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {(e["file"], e["shape"]) for e in data["source_shapes"]}


def test_fixture_matches_backend_sources():
    """夹具与现算逐条相等：新增形态未登记 → 红（前端契约看不到它）；登记了已不存在的 → 红（失效条目）。"""
    current, fixture = scan_app(), _fixture()
    assert current - fixture == set(), f"后端新增了未登记的跳转路由形态：{sorted(current - fixture)}"
    assert fixture - current == set(), f"夹具里有已不存在的形态（请删除）：{sorted(fixture - current)}"


def test_fixture_is_not_empty_and_covers_known_producers():
    """防空转：已知的五个产出方都在（resolver 缺省 / 目录模板生成 / acnr_targets / AI 提及 / 证据治理）。"""
    files = {f for f, _ in _fixture()}
    assert {"services/acnr/resolver.py", "services/acnr/loaders/from_classification.py",
            "services/custom_query/acnr_target_values.py", "services/ai_chat/mention_service.py",
            "services/evidence_governance/typed_adapters.py"} <= files


def test_scanner_ignores_api_paths_and_docstrings():
    """反向样本：装饰器 API 路径、比较字面量、docstring 不计；正向样本：route= / jump_route= / route 赋值 / route 函数 return 计入。"""
    sample = (
        '@router.get("/workpapers/{wp_id}/x")\n'
        "def api(wp_id):\n"
        '    """jump_route=/workpapers/doc"""\n'
        '    return "/workpapers/" in wp_id\n'
        "def _build_route(x):\n"
        '    return f"/workpapers/{x}?sheet=a"\n'
        "def g(x):\n"
        '    route = "a" if x else f"/workpapers/{x}"\n'
        '    return Item(jump_route=f"/workpapers/{x}", route="/workpapers/k")\n'
        'router = APIRouter(prefix="/api/workpapers")\n'
        'h = Hint(route="/api/workpapers/{x}")\n'
    )
    assert scan_source("s.py", sample) == {
        ("s.py", "/workpapers/{…}?sheet=a"), ("s.py", "/workpapers/{…}"), ("s.py", "/workpapers/k")}
