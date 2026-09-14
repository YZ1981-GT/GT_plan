"""PBT: 快照 GC 不删被引用版本 [P18]

**Validates: Requirements 16.1, 16.2, 16.3**

Property P18: 随机版本集 + 随机引用集 → 被引用版本永不被删除。

策略：
- 生成随机版本集合（模拟 catalog_snapshots 目录内容）
- 生成随机被引用子集（模拟 projects.registry_version）
- 调用 cleanup_stale_snapshots
- 断言：被引用版本的快照文件仍然存在

Feature: acnr-runtime-convergence, Task 19
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.catalog_snapshot_gc import (
    cleanup_stale_snapshots,
    compute_versions_to_delete,
    list_snapshot_versions,
)


# ─── Strategies ───────────────────────────────────────────────────────────────

# 版本号 = 14位纯 ASCII 数字时间戳
st_version = st.builds(
    lambda y, mo, d, h, mi, s: f"20{y:02d}{mo:02d}{d:02d}{h:02d}{mi:02d}{s:02d}",
    st.integers(min_value=24, max_value=30),   # year 2024-2030
    st.integers(min_value=1, max_value=12),    # month
    st.integers(min_value=1, max_value=28),    # day
    st.integers(min_value=0, max_value=23),    # hour
    st.integers(min_value=0, max_value=59),    # minute
    st.integers(min_value=0, max_value=59),    # second
)

# 版本集合（1~30 个唯一版本）
st_version_set = st.lists(
    st_version,
    min_size=1,
    max_size=30,
    unique=True,
)

# keep_recent 参数
st_keep_recent = st.integers(min_value=0, max_value=20)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _create_snapshot_files(tmp_dir: Path, versions: list[str]) -> None:
    """在临时目录创建快照文件。"""
    for v in versions:
        path = tmp_dir / f"{v}.json"
        path.write_text(
            json.dumps({"registry_version": v, "sheets": [], "cells": []}, ensure_ascii=False),
            encoding="utf-8",
        )


# ─── PBT Tests ────────────────────────────────────────────────────────────────


class TestSnapshotGcSafety:
    """P18: 快照 GC 不删被引用版本。"""

    @settings(max_examples=5, deadline=None)
    @given(
        all_versions=st_version_set,
        keep_recent=st_keep_recent,
        data=st.data(),
    )
    def test_referenced_versions_never_deleted(
        self,
        all_versions: list[str],
        keep_recent: int,
        data: st.DataObject,
        tmp_path: Path,
    ):
        """PBT: 被引用版本永不被 GC 删除。

        **Validates: Requirements 16.1, 16.2, 16.3**
        """
        import tempfile

        # 从全部版本中随机选取一个子集作为被引用版本
        referenced = set(
            data.draw(
                st.lists(
                    st.sampled_from(all_versions),
                    min_size=0,
                    max_size=len(all_versions),
                    unique=True,
                )
            )
        )

        # 使用独立临时目录（避免 Hypothesis 重试时 tmp_path 被复用）
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            _create_snapshot_files(test_dir, all_versions)

            # 执行 GC（实际删除文件）
            result = cleanup_stale_snapshots(
                keep_recent=keep_recent,
                snapshots_dir=test_dir,
                referenced_versions=referenced,
                dry_run=False,
            )

            # 核心断言：被引用版本文件仍存在
            for ref_version in referenced:
                snapshot_path = test_dir / f"{ref_version}.json"
                assert snapshot_path.exists(), (
                    f"Referenced version {ref_version} was deleted! "
                    f"keep_recent={keep_recent}, all_versions={sorted(all_versions)}, "
                    f"referenced={sorted(referenced)}"
                )

            # 辅助断言：被引用版本不在 deleted 列表中
            deleted_set = set(result["deleted"])
            for ref_version in referenced:
                assert ref_version not in deleted_set, (
                    f"Referenced version {ref_version} appears in deleted list!"
                )

    @settings(max_examples=5, deadline=None)
    @given(
        all_versions=st_version_set,
        keep_recent=st_keep_recent,
    )
    def test_recent_versions_never_deleted(
        self,
        all_versions: list[str],
        keep_recent: int,
        tmp_path: Path,
    ):
        """PBT: 最近 N 个版本永不被删除。

        **Validates: Requirements 16.1**
        """
        import tempfile

        # 无引用版本（测试纯 keep_recent 保留逻辑）
        referenced: set[str] = set()

        # 使用独立临时目录（避免 Hypothesis 重试时 tmp_path 被复用）
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            _create_snapshot_files(test_dir, all_versions)

            result = cleanup_stale_snapshots(
                keep_recent=keep_recent,
                snapshots_dir=test_dir,
                referenced_versions=referenced,
                dry_run=False,
            )

            # 排序后取最近 N 个
            sorted_versions = sorted(all_versions, reverse=True)
            recent_versions = set(sorted_versions[:keep_recent])

            # 最近 N 个版本文件仍存在
            for recent in recent_versions:
                snapshot_path = test_dir / f"{recent}.json"
                assert snapshot_path.exists(), (
                    f"Recent version {recent} was deleted! "
                    f"keep_recent={keep_recent}"
                )

    @settings(max_examples=5, deadline=None)
    @given(
        all_versions=st_version_set,
        keep_recent=st_keep_recent,
        data=st.data(),
    )
    def test_total_remaining_le_keep_recent_plus_referenced(
        self,
        all_versions: list[str],
        keep_recent: int,
        data: st.DataObject,
        tmp_path: Path,
    ):
        """PBT: GC 后剩余总数 <= keep_recent + referenced_count。

        **Validates: Requirements 16.4 (CI 守卫前提条件)**
        """
        import tempfile

        referenced = set(
            data.draw(
                st.lists(
                    st.sampled_from(all_versions),
                    min_size=0,
                    max_size=len(all_versions),
                    unique=True,
                )
            )
        )

        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            _create_snapshot_files(test_dir, all_versions)

            cleanup_stale_snapshots(
                keep_recent=keep_recent,
                snapshots_dir=test_dir,
                referenced_versions=referenced,
                dry_run=False,
            )

            # 统计剩余文件数
            remaining = list_snapshot_versions(test_dir)

            # 剩余应 <= keep_recent + referenced（可能有重叠）
            max_allowed = keep_recent + len(referenced)
            assert len(remaining) <= max_allowed, (
                f"Remaining={len(remaining)} exceeds "
                f"keep_recent({keep_recent}) + referenced({len(referenced)}) = {max_allowed}"
            )


class TestComputeVersionsToDelete:
    """compute_versions_to_delete 单元测试。"""

    def test_empty_versions_returns_empty(self):
        """空版本列表 → 不删除任何版本。"""
        result = compute_versions_to_delete([], set(), keep_recent=10)
        assert result == []

    def test_all_within_keep_recent_returns_empty(self):
        """全部在 keep_recent 范围内 → 不删除。"""
        versions = ["20260715120000", "20260714120000", "20260713120000"]
        result = compute_versions_to_delete(versions, set(), keep_recent=10)
        assert result == []

    def test_exceeding_keep_recent_deletes_old(self):
        """超过 keep_recent 且无引用 → 删除旧版本。"""
        versions = ["20260715", "20260714", "20260713", "20260712", "20260711"]
        result = compute_versions_to_delete(versions, set(), keep_recent=3)
        assert set(result) == {"20260712", "20260711"}

    def test_referenced_versions_preserved(self):
        """被引用版本即使超出 keep_recent 也不删除。"""
        versions = ["20260715", "20260714", "20260713", "20260712", "20260711"]
        referenced = {"20260711", "20260712"}
        result = compute_versions_to_delete(versions, referenced, keep_recent=2)
        # keep_recent=2 保留 20260715, 20260714
        # referenced 保留 20260711, 20260712
        # 可删除: 20260713
        assert set(result) == {"20260713"}

    def test_keep_recent_zero_deletes_all_unreferenced(self):
        """keep_recent=0 → 删除所有未被引用的版本。"""
        versions = ["20260715", "20260714", "20260713"]
        referenced = {"20260714"}
        result = compute_versions_to_delete(versions, referenced, keep_recent=0)
        assert set(result) == {"20260715", "20260713"}
