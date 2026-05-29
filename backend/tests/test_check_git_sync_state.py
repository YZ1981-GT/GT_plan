"""repo-git-workflow-unification spec / Sprint 4 / Task 4.1

check_git_sync_state.py 单元测试。

策略：mock run_git 输出，测纯函数逻辑。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_git_sync_state as mod  # noqa: E402


class TestIsAllOk:

    def test_all_ok_state(self):
        result = {
            "working_tree_clean": True,
            "local_eq_remote": True,
            "ahead": 0,
            "behind": 0,
            "untracked_count": 0,
        }
        assert mod.is_all_ok(result, strict=False) is True
        assert mod.is_all_ok(result, strict=True) is True

    def test_dirty_working_tree_fails(self):
        result = {
            "working_tree_clean": False,
            "local_eq_remote": True,
            "ahead": 0, "behind": 0, "untracked_count": 0,
        }
        assert mod.is_all_ok(result) is False

    def test_local_remote_diverge_fails(self):
        result = {
            "working_tree_clean": True,
            "local_eq_remote": False,
            "ahead": 1, "behind": 0, "untracked_count": 0,
        }
        assert mod.is_all_ok(result) is False

    def test_behind_fails(self):
        result = {
            "working_tree_clean": True,
            "local_eq_remote": False,
            "ahead": 0, "behind": 3, "untracked_count": 0,
        }
        assert mod.is_all_ok(result) is False

    def test_untracked_only_passes_loose_fails_strict(self):
        result = {
            "working_tree_clean": True,
            "local_eq_remote": True,
            "ahead": 0, "behind": 0, "untracked_count": 5,
        }
        # 非 strict：untracked 不影响
        assert mod.is_all_ok(result, strict=False) is True
        # strict：untracked 视为不达标
        assert mod.is_all_ok(result, strict=True) is False


class TestGetGitMode:

    def test_default_single(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GIT_MODE", None)
            assert mod.get_git_mode() == "single"

    def test_multi_mode(self):
        with patch.dict("os.environ", {"GIT_MODE": "multi"}):
            assert mod.get_git_mode() == "multi"

    def test_uppercase_normalized(self):
        with patch.dict("os.environ", {"GIT_MODE": "MULTI"}):
            assert mod.get_git_mode() == "multi"


class TestFormatReport:

    def test_report_contains_branch_name(self):
        result = {
            "branch": "main",
            "working_tree_clean": True,
            "working_tree_count": 0,
            "local_head": "abc12345",
            "remote_head": "abc12345",
            "local_eq_remote": True,
            "ahead": 0,
            "behind": 0,
            "untracked_count": 0,
            "last_commit": "abc1234 some commit",
            "git_mode": "single",
        }
        report = mod.format_report(result)
        assert "main" in report
        assert "single" in report
        assert "✅" in report

    def test_report_marks_failures(self):
        result = {
            "branch": "main",
            "working_tree_clean": False,
            "working_tree_count": 5,
            "local_head": "aaa", "remote_head": "bbb",
            "local_eq_remote": False,
            "ahead": 2, "behind": 3,
            "untracked_count": 1,
            "last_commit": "x",
            "git_mode": "multi",
        }
        report = mod.format_report(result)
        assert "❌" in report
        assert "5 文件" in report
