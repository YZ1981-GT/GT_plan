"""MT-5 后端服务依赖图生成脚本

基于 ast 模块解析 backend/app/services/*.py 与 backend/app/routers/*.py 的
import 语句，抽取它们之间的引用关系，输出一个 Mermaid `graph TD` 到
docs/architecture/service-dependency.md。

Usage::

    python scripts/gen_service_deps.py
    python scripts/gen_service_deps.py --output docs/architecture/service-dependency.md
    python scripts/gen_service_deps.py --backend backend/app --output -

仅依赖标准库（ast / pathlib / argparse / typing），不引入新依赖。

设计要点：
* 节点 = 文件 stem（含命名空间前缀 `service:` / `router:` 防同名冲突）
* 边 = "A imports B"（A → B 表示 A 依赖 B）；module 级 import 与 函数体内
  的延迟 import（`from app.services.xxx import yyy`）都计入
* "关键路径" = 入度（被多少个文件 import）最高的 top 5 服务
* 输出 Markdown 包含：概览 + 关键路径表 + Mermaid block + 孤立节点列表
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

SERVICE_PREFIX = "app.services."
ROUTER_PREFIX = "app.routers."


@dataclass
class DependencyGraph:
    """简单的有向图模型。"""

    nodes: dict[str, str] = field(default_factory=dict)
    """node_id -> kind ('service' / 'router')"""

    edges: set[tuple[str, str]] = field(default_factory=set)
    """(source, target) 去重边集合"""

    def add_node(self, node_id: str, kind: str) -> None:
        # kind 升级规则：router 优先于 service（同名情况几乎不存在，但保守处理）
        existing = self.nodes.get(node_id)
        if existing is None:
            self.nodes[node_id] = kind
        elif existing != kind and kind == "router":
            self.nodes[node_id] = kind

    def add_edge(self, source: str, target: str) -> None:
        if source == target:
            return
        self.edges.add((source, target))

    def in_degrees(self) -> dict[str, int]:
        result: dict[str, int] = defaultdict(int)
        for node in self.nodes:
            result[node] = 0
        for _src, dst in self.edges:
            result[dst] += 1
        return dict(result)

    def out_degrees(self) -> dict[str, int]:
        result: dict[str, int] = defaultdict(int)
        for node in self.nodes:
            result[node] = 0
        for src, _dst in self.edges:
            result[src] += 1
        return dict(result)


def _module_to_node(module_path: str) -> tuple[str, str] | None:
    """把 'app.services.foo' / 'app.routers.bar' 形式的 module 名映射为节点。

    返回 (node_id, kind)；若不是 service/router 类，返回 None。
    """
    if module_path.startswith(SERVICE_PREFIX):
        leaf = module_path[len(SERVICE_PREFIX):].split(".", 1)[0]
        if not leaf:
            return None
        return f"service:{leaf}", "service"
    if module_path.startswith(ROUTER_PREFIX):
        leaf = module_path[len(ROUTER_PREFIX):].split(".", 1)[0]
        if not leaf:
            return None
        return f"router:{leaf}", "router"
    return None


def _classify_file(path: Path) -> tuple[str, str] | None:
    """从文件路径推断节点 (id, kind)。"""
    parts = path.parts
    # 支持任意祖先（兼容 backend/app/services/foo.py 与
    # backend/app/services/sub_pkg/__init__.py 等场景）
    try:
        idx_app = parts.index("app")
    except ValueError:
        return None
    if idx_app + 2 > len(parts):
        return None

    # 找出 app/<services|routers>/<leaf>...
    folder = parts[idx_app + 1]
    if folder not in ("services", "routers"):
        return None

    # leaf 名 = 第一层 .py 文件 stem 或子目录名
    if idx_app + 2 >= len(parts):
        return None
    leaf_part = parts[idx_app + 2]
    if leaf_part.endswith(".py"):
        leaf = leaf_part[:-3]
        if leaf == "__init__":
            return None
    else:
        leaf = leaf_part  # 子目录视为聚合节点

    kind = "service" if folder == "services" else "router"
    return f"{kind}:{leaf}", kind


def _extract_imports(source: str) -> list[str]:
    """抽取所有 module 级与函数体内 `import` 语句的目标 module 路径。

    支持两种形式：
      - `import app.services.foo`
      - `from app.services.foo import Bar`
    `from . import foo` / `from .foo import bar` 类相对 import 一律忽略
    （services/routers 目录下基本没有相对 import）。
    """
    targets: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return targets

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # 相对 import，跳过
                continue
            if node.module:
                targets.append(node.module)
    return targets


def collect_files(backend_root: Path) -> list[Path]:
    """枚举所有应纳入分析的 Python 文件。"""
    candidates: list[Path] = []
    for sub in ("services", "routers"):
        base = backend_root / sub
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            # 忽略 __pycache__
            if "__pycache__" in py.parts:
                continue
            if py.name == "__init__.py":
                continue
            candidates.append(py)
    return candidates


def build_graph(backend_root: Path) -> DependencyGraph:
    """扫描指定后端根目录，构建依赖图。"""
    graph = DependencyGraph()
    files = collect_files(backend_root)

    for path in files:
        node_info = _classify_file(path)
        if not node_info:
            continue
        node_id, kind = node_info
        graph.add_node(node_id, kind)

        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for module_path in _extract_imports(source):
            target = _module_to_node(module_path)
            if not target:
                continue
            target_id, target_kind = target
            graph.add_node(target_id, target_kind)
            graph.add_edge(node_id, target_id)

    return graph


def _mermaid_node_id(node: str) -> str:
    """把 'service:foo_bar' 转为 mermaid 安全标识符。"""
    return node.replace(":", "__").replace("-", "_")


def _mermaid_label(node: str, critical: bool) -> str:
    kind, _, leaf = node.partition(":")
    suffix = " ⭐" if critical else ""
    if kind == "router":
        return f"🛣 {leaf}{suffix}"
    return f"⚙ {leaf}{suffix}"


def render_mermaid(graph: DependencyGraph, critical_nodes: Iterable[str]) -> str:
    """渲染 Mermaid `graph TD`。

    关键路径节点用 `:::critical` class 高亮；router 节点用 `:::router` class。
    """
    critical_set = set(critical_nodes)
    lines: list[str] = ["graph TD"]
    # 节点声明
    for node in sorted(graph.nodes):
        node_id = _mermaid_node_id(node)
        label = _mermaid_label(node, node in critical_set)
        lines.append(f'    {node_id}["{label}"]')

    # 边
    for src, dst in sorted(graph.edges):
        lines.append(f"    {_mermaid_node_id(src)} --> {_mermaid_node_id(dst)}")

    # 样式
    lines.append("")
    lines.append("    classDef critical fill:#FFE082,stroke:#F57F17,stroke-width:2px;")
    lines.append("    classDef router fill:#B3E5FC,stroke:#0277BD;")
    lines.append("    classDef service fill:#E8F5E9,stroke:#2E7D32;")

    router_nodes = [n for n, k in graph.nodes.items() if k == "router"]
    service_nodes = [n for n, k in graph.nodes.items() if k == "service"]
    if router_nodes:
        lines.append(
            "    class "
            + ",".join(_mermaid_node_id(n) for n in sorted(router_nodes))
            + " router;"
        )
    if service_nodes:
        lines.append(
            "    class "
            + ",".join(_mermaid_node_id(n) for n in sorted(service_nodes))
            + " service;"
        )
    if critical_set:
        lines.append(
            "    class "
            + ",".join(_mermaid_node_id(n) for n in sorted(critical_set))
            + " critical;"
        )

    return "\n".join(lines)


def render_markdown(graph: DependencyGraph, top_n: int = 5) -> str:
    """生成 Markdown 文档（含 mermaid block 与说明）。"""
    in_deg = graph.in_degrees()
    # 关键路径 = 入度最高的 top N（仅 service 类，router 通常入度=0）
    service_only = [(n, in_deg[n]) for n, k in graph.nodes.items() if k == "service"]
    service_only.sort(key=lambda x: (-x[1], x[0]))
    critical = [n for n, deg in service_only[:top_n] if deg > 0]

    out_deg = graph.out_degrees()

    service_count = sum(1 for k in graph.nodes.values() if k == "service")
    router_count = sum(1 for k in graph.nodes.values() if k == "router")

    lines: list[str] = []
    lines.append("# 后端服务依赖图（MT-5）")
    lines.append("")
    lines.append("> 本文档由 `scripts/gen_service_deps.py` 自动生成，请勿手工编辑。")
    lines.append(">")
    lines.append("> 重新生成命令：`python scripts/gen_service_deps.py`")
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append(f"- Service 数量：**{service_count}**")
    lines.append(f"- Router 数量：**{router_count}**")
    lines.append(f"- 依赖边数量：**{len(graph.edges)}**")
    lines.append("")
    lines.append("## 关键路径（入度最高的 Top 5 Service）")
    lines.append("")
    lines.append("> 入度 = 被多少个 service / router 引用。入度高 = 改动影响面大，")
    lines.append("> 需重点保证测试覆盖与变更评审。")
    lines.append("")
    if critical:
        lines.append("| 排名 | Service | 入度 | 出度 |")
        lines.append("|------|---------|------|------|")
        for idx, name in enumerate(critical, start=1):
            leaf = name.split(":", 1)[1]
            lines.append(f"| {idx} | `{leaf}` | {in_deg[name]} | {out_deg[name]} |")
    else:
        lines.append("（无被引用的 service）")
    lines.append("")
    lines.append("## 依赖图")
    lines.append("")
    lines.append("```mermaid")
    lines.append(render_mermaid(graph, critical))
    lines.append("```")
    lines.append("")
    lines.append("## 图例")
    lines.append("")
    lines.append("- ⚙ 绿色 = service 节点")
    lines.append("- 🛣 蓝色 = router 节点")
    lines.append("- ⭐ 黄色高亮 = 关键路径（入度 Top 5 service）")
    lines.append("")

    # 孤立节点 = 出度 + 入度均为 0
    isolated = [
        n
        for n in graph.nodes
        if in_deg.get(n, 0) == 0 and out_deg.get(n, 0) == 0
    ]
    if isolated:
        lines.append("## 孤立节点（无入边也无出边）")
        lines.append("")
        lines.append(
            "下列文件未被其他 service/router 引用，也未引用任何 service/router；"
            "可能是入口路由、纯模型工具或废弃代码，建议人工 review。"
        )
        lines.append("")
        for node in sorted(isolated):
            kind, _, leaf = node.partition(":")
            lines.append(f"- {kind}: `{leaf}`")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成后端服务依赖关系 Mermaid 图")
    parser.add_argument(
        "--backend",
        default=str(REPO_ROOT / "backend" / "app"),
        help="后端 app 根目录（默认: backend/app）",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "docs" / "SERVICE_DEPENDENCY.md"),
        help="输出 Markdown 文件路径，传入 '-' 表示打印到 stdout",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="关键路径节点数量（默认 5）",
    )
    args = parser.parse_args(argv)

    backend_root = Path(args.backend).resolve()
    if not backend_root.exists():
        print(f"ERROR: backend 路径不存在：{backend_root}", file=sys.stderr)
        return 2

    graph = build_graph(backend_root)
    markdown = render_markdown(graph, top_n=args.top)

    if args.output == "-":
        print(markdown)
    else:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        service_count = sum(1 for k in graph.nodes.values() if k == "service")
        router_count = sum(1 for k in graph.nodes.values() if k == "router")
        print(
            f"OK: 已生成 {out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path}"
            f"（services={service_count}, routers={router_count}, edges={len(graph.edges)}）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
