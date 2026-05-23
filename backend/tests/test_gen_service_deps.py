"""单测：scripts/gen_service_deps.py（MT-5 后端服务依赖图）

覆盖：
1. _classify_file 节点分类
2. _module_to_node 模块名映射
3. _extract_imports AST 抽取（含函数体内 lazy import）
4. build_graph 端到端：mock 一个临时目录的几个 .py 文件，验证生成正确的图
5. render_mermaid + render_markdown 输出格式

脚本位于工作区根 `scripts/`，测试通过 importlib 显式加载，避免与
backend/scripts/ 命名空间冲突。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    """通过 importlib 显式加载 workspace-root 的 scripts/gen_service_deps.py。"""
    backend_dir = Path(__file__).resolve().parents[1]
    workspace_root = backend_dir.parent
    target = workspace_root / "scripts" / "gen_service_deps.py"
    assert target.exists(), f"脚本不存在: {target}"

    module_name = "gen_service_deps_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, target)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


gsd = _load_module()


# ─────────────────────────── 单元工具函数 ───────────────────────────


class TestModuleToNode:
    def test_service_module(self):
        assert gsd._module_to_node("app.services.foo") == ("service:foo", "service")

    def test_service_submodule(self):
        # 子模块视为顶层 leaf 节点
        assert gsd._module_to_node("app.services.foo.bar") == ("service:foo", "service")

    def test_router_module(self):
        assert gsd._module_to_node("app.routers.bar") == ("router:bar", "router")

    def test_unrelated_module(self):
        assert gsd._module_to_node("app.models.core") is None
        assert gsd._module_to_node("os") is None
        assert gsd._module_to_node("") is None


class TestClassifyFile:
    def test_service_file(self, tmp_path: Path):
        path = tmp_path / "backend" / "app" / "services" / "foo_service.py"
        path.parent.mkdir(parents=True)
        path.write_text("")
        assert gsd._classify_file(path) == ("service:foo_service", "service")

    def test_router_file(self, tmp_path: Path):
        path = tmp_path / "backend" / "app" / "routers" / "bar_router.py"
        path.parent.mkdir(parents=True)
        path.write_text("")
        assert gsd._classify_file(path) == ("router:bar_router", "router")

    def test_init_file_skipped(self, tmp_path: Path):
        path = tmp_path / "backend" / "app" / "services" / "__init__.py"
        path.parent.mkdir(parents=True)
        path.write_text("")
        assert gsd._classify_file(path) is None

    def test_unrelated_folder(self, tmp_path: Path):
        path = tmp_path / "backend" / "app" / "models" / "core.py"
        path.parent.mkdir(parents=True)
        path.write_text("")
        assert gsd._classify_file(path) is None


class TestExtractImports:
    def test_module_level_import(self):
        src = "import app.services.foo\nfrom app.services.bar import Baz\n"
        targets = gsd._extract_imports(src)
        assert "app.services.foo" in targets
        assert "app.services.bar" in targets

    def test_function_body_lazy_import(self):
        src = """
def my_func():
    from app.services.lazy_one import helper
    import app.routers.lazy_two
"""
        targets = gsd._extract_imports(src)
        assert "app.services.lazy_one" in targets
        assert "app.routers.lazy_two" in targets

    def test_relative_import_ignored(self):
        src = "from . import sibling\nfrom .foo import bar\n"
        targets = gsd._extract_imports(src)
        assert targets == []

    def test_invalid_syntax_returns_empty(self):
        src = "this is not python ::: !!!"
        assert gsd._extract_imports(src) == []


# ─────────────────────────── 端到端 build_graph ───────────────────────────


@pytest.fixture
def fake_backend(tmp_path: Path) -> Path:
    """构造一个最小化的 backend/app 目录，包含 4 个 services + 2 个 routers。

    依赖关系：
        router:alpha     → service:auth, service:cache
        router:beta      → service:cache
        service:auth     → service:cache
        service:cache    → （叶子，无下游）
        service:isolated → （孤立，无人引用，自身也不引用 service/router）
        service:reporter → service:cache
    """
    app_root = tmp_path / "backend" / "app"
    services = app_root / "services"
    routers = app_root / "routers"
    services.mkdir(parents=True)
    routers.mkdir(parents=True)

    (services / "auth.py").write_text(
        "from app.services.cache import CacheService\n"
        "class AuthService:\n    pass\n",
        encoding="utf-8",
    )
    (services / "cache.py").write_text(
        "import os\n"
        "class CacheService:\n    pass\n",
        encoding="utf-8",
    )
    (services / "isolated.py").write_text(
        "import logging\n"
        "logger = logging.getLogger(__name__)\n",
        encoding="utf-8",
    )
    (services / "reporter.py").write_text(
        "def get_report():\n"
        "    from app.services.cache import CacheService\n"
        "    return CacheService()\n",
        encoding="utf-8",
    )
    (routers / "alpha.py").write_text(
        "from app.services.auth import AuthService\n"
        "from app.services.cache import CacheService\n"
        "router = None\n",
        encoding="utf-8",
    )
    (routers / "beta.py").write_text(
        "from app.services.cache import CacheService\n",
        encoding="utf-8",
    )
    # 应被忽略的 __init__.py
    (services / "__init__.py").write_text("", encoding="utf-8")
    (routers / "__init__.py").write_text("", encoding="utf-8")

    return app_root


class TestBuildGraph:
    def test_node_kinds(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        # 4 services + 2 routers = 6 nodes
        assert graph.nodes["service:auth"] == "service"
        assert graph.nodes["service:cache"] == "service"
        assert graph.nodes["service:isolated"] == "service"
        assert graph.nodes["service:reporter"] == "service"
        assert graph.nodes["router:alpha"] == "router"
        assert graph.nodes["router:beta"] == "router"
        assert len(graph.nodes) == 6

    def test_edges(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        expected = {
            ("router:alpha", "service:auth"),
            ("router:alpha", "service:cache"),
            ("router:beta", "service:cache"),
            ("service:auth", "service:cache"),
            ("service:reporter", "service:cache"),
        }
        assert graph.edges == expected

    def test_isolated_node_has_no_edges(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        in_deg = graph.in_degrees()
        out_deg = graph.out_degrees()
        assert in_deg["service:isolated"] == 0
        assert out_deg["service:isolated"] == 0

    def test_in_degrees(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        in_deg = graph.in_degrees()
        # cache 被 router:alpha + router:beta + service:auth + service:reporter 引用
        assert in_deg["service:cache"] == 4
        # auth 仅被 router:alpha 引用
        assert in_deg["service:auth"] == 1
        # routers 入度 = 0
        assert in_deg["router:alpha"] == 0
        assert in_deg["router:beta"] == 0


# ─────────────────────────── 渲染输出 ───────────────────────────


class TestRenderMermaid:
    def test_contains_graph_td_header(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        out = gsd.render_mermaid(graph, ["service:cache"])
        assert out.startswith("graph TD")

    def test_contains_all_nodes(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        out = gsd.render_mermaid(graph, ["service:cache"])
        # 每个节点都应当出现一次（用 mermaid 安全 id 表示）
        for leaf in ["auth", "cache", "isolated", "reporter"]:
            assert f"service__{leaf}" in out
        for leaf in ["alpha", "beta"]:
            assert f"router__{leaf}" in out

    def test_contains_all_edges(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        out = gsd.render_mermaid(graph, [])
        assert "router__alpha --> service__auth" in out
        assert "router__alpha --> service__cache" in out
        assert "router__beta --> service__cache" in out
        assert "service__auth --> service__cache" in out
        assert "service__reporter --> service__cache" in out

    def test_critical_class_applied(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        out = gsd.render_mermaid(graph, ["service:cache"])
        assert "class service__cache critical" in out


class TestRenderMarkdown:
    def test_markdown_structure(self, fake_backend: Path):
        graph = gsd.build_graph(fake_backend)
        md = gsd.render_markdown(graph, top_n=3)
        # 标题
        assert "# 后端服务依赖图（MT-5）" in md
        # 概览数字
        assert "Service 数量：**4**" in md
        assert "Router 数量：**2**" in md
        assert "依赖边数量：**5**" in md
        # 关键路径表
        assert "## 关键路径（入度最高的 Top 5 Service）" in md
        assert "`cache`" in md  # cache 入度最高
        # mermaid block
        assert "```mermaid" in md
        assert "graph TD" in md
        # 孤立节点段落
        assert "## 孤立节点" in md
        assert "`isolated`" in md

    def test_no_isolated_section_when_all_connected(self, tmp_path: Path):
        app_root = tmp_path / "backend" / "app"
        services = app_root / "services"
        services.mkdir(parents=True)
        (services / "a.py").write_text(
            "from app.services.b import B\n", encoding="utf-8"
        )
        (services / "b.py").write_text("class B:\n    pass\n", encoding="utf-8")

        graph = gsd.build_graph(app_root)
        md = gsd.render_markdown(graph)
        assert "## 孤立节点" not in md


# ─────────────────────────── main 端到端 ───────────────────────────


class TestMainCli:
    def test_main_writes_file(self, fake_backend: Path, tmp_path: Path):
        out_file = tmp_path / "deps.md"
        rc = gsd.main(
            ["--backend", str(fake_backend), "--output", str(out_file)]
        )
        assert rc == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "graph TD" in content
        assert "service__cache" in content

    def test_main_stdout_mode(self, fake_backend: Path, capsys):
        rc = gsd.main(["--backend", str(fake_backend), "--output", "-"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "graph TD" in captured.out

    def test_main_invalid_backend(self, tmp_path: Path, capsys):
        rc = gsd.main(
            [
                "--backend",
                str(tmp_path / "does_not_exist"),
                "--output",
                "-",
            ]
        )
        assert rc == 2
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
