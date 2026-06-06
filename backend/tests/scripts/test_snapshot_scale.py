"""Tests for snapshot_scale.py — 规模快照可复现性。

Property 1: 同一提交上重复运行输出一致。
"""
import json
import sys
from pathlib import Path

import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_collect_metrics_returns_expected_structure():
    """collect_metrics 返回包含 backend/frontend 键的 dict。"""
    from scripts.analyze.snapshot_scale import collect_metrics
    repo_root = Path(__file__).resolve().parents[3]
    metrics = collect_metrics(repo_root)

    assert "timestamp" in metrics
    assert "backend" in metrics
    assert "frontend" in metrics
    assert set(metrics["backend"].keys()) == {"routers", "services", "models", "migrations", "tests"}
    assert set(metrics["frontend"].keys()) == {"views", "components", "composables"}


def test_backend_counts_are_positive():
    """后端计数均为正整数。"""
    from scripts.analyze.snapshot_scale import collect_metrics
    repo_root = Path(__file__).resolve().parents[3]
    metrics = collect_metrics(repo_root)

    for key, value in metrics["backend"].items():
        assert isinstance(value, int), f"backend.{key} should be int"
        assert value > 0, f"backend.{key} should be > 0, got {value}"


def test_frontend_counts_are_positive():
    """前端计数均为正整数。"""
    from scripts.analyze.snapshot_scale import collect_metrics
    repo_root = Path(__file__).resolve().parents[3]
    metrics = collect_metrics(repo_root)

    for key, value in metrics["frontend"].items():
        assert isinstance(value, int), f"frontend.{key} should be int"
        assert value > 0, f"frontend.{key} should be > 0, got {value}"


def test_reproducibility():
    """Property 1: 同一提交重复运行输出一致。"""
    from scripts.analyze.snapshot_scale import collect_metrics
    repo_root = Path(__file__).resolve().parents[3]

    m1 = collect_metrics(repo_root)
    m2 = collect_metrics(repo_root)

    # timestamp 会不同，比较其他字段
    assert m1["backend"] == m2["backend"]
    assert m1["frontend"] == m2["frontend"]
