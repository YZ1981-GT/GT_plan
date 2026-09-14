"""Tests for snapshot_scale.py — 规模快照可复现性。

Property 1: 同一提交上重复运行输出一致（P0-2.6）。
**Validates: Requirements 2.1, 2.2**
"""

import json
import sys
from pathlib import Path

import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _get_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_collect_metrics_returns_expected_structure():
    """collect_metrics 返回包含 backend/frontend 键的 dict。"""
    from scripts.analyze.snapshot_scale import collect_metrics

    metrics = collect_metrics(_get_repo_root())

    assert "timestamp" in metrics
    assert "backend" in metrics
    assert "frontend" in metrics
    assert set(metrics["backend"].keys()) == {
        "routers", "services", "models", "migrations", "tests"
    }
    assert set(metrics["frontend"].keys()) == {
        "views", "components", "composables"
    }


def test_backend_counts_are_positive():
    """后端计数均为正整数。"""
    from scripts.analyze.snapshot_scale import collect_metrics

    metrics = collect_metrics(_get_repo_root())

    for key, value in metrics["backend"].items():
        assert isinstance(value, int), f"backend.{key} should be int"
        assert value > 0, f"backend.{key} should be > 0, got {value}"


def test_frontend_counts_are_positive():
    """前端计数均为正整数。"""
    from scripts.analyze.snapshot_scale import collect_metrics

    metrics = collect_metrics(_get_repo_root())

    for key, value in metrics["frontend"].items():
        assert isinstance(value, int), f"frontend.{key} should be int"
        assert value > 0, f"frontend.{key} should be > 0, got {value}"


def test_reproducibility():
    """Property 1 (P0-2.6): 同一提交重复运行输出一致。

    除 timestamp 外，所有计数字段完全相同。
    """
    from scripts.analyze.snapshot_scale import collect_metrics

    repo_root = _get_repo_root()
    m1 = collect_metrics(repo_root)
    m2 = collect_metrics(repo_root)

    # timestamp 会不同，比较其他字段
    assert m1["backend"] == m2["backend"]
    assert m1["frontend"] == m2["frontend"]


def test_format_json_is_valid():
    """JSON 输出可被正确解析。"""
    from scripts.analyze.snapshot_scale import collect_metrics, format_json

    metrics = collect_metrics(_get_repo_root())
    json_str = format_json(metrics)

    parsed = json.loads(json_str)
    assert parsed["backend"] == metrics["backend"]
    assert parsed["frontend"] == metrics["frontend"]


def test_format_markdown_contains_table():
    """Markdown 输出包含表格和自动生成标记。"""
    from scripts.analyze.snapshot_scale import collect_metrics, format_markdown

    metrics = collect_metrics(_get_repo_root())
    md = format_markdown(metrics)

    # 自动生成标记
    assert "AUTO-GENERATED" in md
    assert "DO NOT EDIT MANUALLY" in md
    # 表头
    assert "| 模块 | 数量 |" in md
    # 后端/前端区块
    assert "## 后端" in md
    assert "## 前端" in md
    # 数据行
    assert f"| Routers | {metrics['backend']['routers']} |" in md
    assert f"| Views | {metrics['frontend']['views']} |" in md


def test_write_creates_file(tmp_path: Path):
    """--write 模式写入 docs/architecture/scale-snapshot.md。"""
    from scripts.analyze.snapshot_scale import collect_metrics, format_markdown

    # 创建仿真目录结构
    (tmp_path / "backend" / "app" / "routers").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "services").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "models").mkdir(parents=True)
    (tmp_path / "backend" / "migrations").mkdir(parents=True)
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    (tmp_path / "audit-platform" / "frontend" / "src" / "views").mkdir(parents=True)
    (tmp_path / "audit-platform" / "frontend" / "src" / "components").mkdir(parents=True)
    (tmp_path / "audit-platform" / "frontend" / "src" / "composables").mkdir(parents=True)

    # 添加一些文件
    (tmp_path / "backend" / "app" / "routers" / "auth.py").write_text("# router")
    (tmp_path / "backend" / "app" / "services" / "user.py").write_text("# service")
    (tmp_path / "backend" / "app" / "models" / "user.py").write_text("# model")
    (tmp_path / "backend" / "migrations" / "V001__init.sql").write_text("-- init")
    (tmp_path / "backend" / "tests" / "test_auth.py").write_text("# test")
    (tmp_path / "audit-platform" / "frontend" / "src" / "views" / "Home.vue").write_text("<template/>")
    (tmp_path / "audit-platform" / "frontend" / "src" / "components" / "Btn.vue").write_text("<template/>")
    (tmp_path / "audit-platform" / "frontend" / "src" / "composables" / "useAuth.ts").write_text("export {}")

    metrics = collect_metrics(tmp_path)
    output_path = tmp_path / "docs" / "architecture" / "scale-snapshot.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = format_markdown(metrics)
    output_path.write_text(content, encoding="utf-8")

    assert output_path.exists()
    written = output_path.read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in written
    assert "| Routers | 1 |" in written
    assert "| Views | 1 |" in written


def test_determinism_with_synthetic_repo(tmp_path: Path):
    """P0-2.6: 用合成仓库验证确定性——多次运行结果一致。"""
    from scripts.analyze.snapshot_scale import collect_metrics

    # 创建合成目录结构
    (tmp_path / "backend" / "app" / "routers").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "services").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "models").mkdir(parents=True)
    (tmp_path / "backend" / "migrations").mkdir(parents=True)
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    (tmp_path / "audit-platform" / "frontend" / "src" / "views").mkdir(parents=True)
    (tmp_path / "audit-platform" / "frontend" / "src" / "components").mkdir(parents=True)
    (tmp_path / "audit-platform" / "frontend" / "src" / "composables").mkdir(parents=True)

    # 添加多个文件确保排序不影响计数
    for i in range(5):
        (tmp_path / "backend" / "app" / "routers" / f"r{i}.py").write_text(f"# {i}")
        (tmp_path / "backend" / "app" / "services" / f"s{i}.py").write_text(f"# {i}")
    (tmp_path / "backend" / "app" / "models" / "__init__.py").write_text("# init")
    (tmp_path / "backend" / "app" / "models" / "user.py").write_text("# model")
    (tmp_path / "backend" / "migrations" / "V001__a.sql").write_text("-- a")
    (tmp_path / "backend" / "migrations" / "V002__b.sql").write_text("-- b")
    (tmp_path / "backend" / "migrations" / "R001__a.sql").write_text("-- rollback")
    (tmp_path / "backend" / "tests" / "test_a.py").write_text("# t")
    (tmp_path / "backend" / "tests" / "test_b.py").write_text("# t")
    (tmp_path / "audit-platform" / "frontend" / "src" / "composables" / "useA.ts").write_text("")
    (tmp_path / "audit-platform" / "frontend" / "src" / "composables" / "useB.ts").write_text("")

    # 运行 10 次，所有结果（除 timestamp）应完全一致
    results = []
    for _ in range(10):
        m = collect_metrics(tmp_path)
        results.append({"backend": m["backend"], "frontend": m["frontend"]})

    first = results[0]
    for r in results[1:]:
        assert r == first

    # 验证具体计数
    assert first["backend"]["routers"] == 5
    assert first["backend"]["services"] == 5
    assert first["backend"]["models"] == 1  # __init__.py excluded
    assert first["backend"]["migrations"] == 2  # only V*.sql
    assert first["backend"]["tests"] == 2
    assert first["frontend"]["composables"] == 2
