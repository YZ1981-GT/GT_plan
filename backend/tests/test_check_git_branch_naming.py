"""repo-git-workflow-unification spec / Sprint 4 / Task 4.2

check_git_branch_naming.py 单元测试 - 5 类前缀 + 不合规 + 无 spec 目录。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_git_branch_naming as mod  # noqa: E402


class TestValidateBranchName:

    def test_main_passes(self):
        ok, prefix, msg = mod.validate("main")
        assert ok is True
        assert prefix == "main"

    def test_fix_passes(self):
        ok, prefix, msg = mod.validate("fix/some-bug")
        assert ok is True
        assert prefix == "fix"

    def test_release_passes(self):
        ok, prefix, msg = mod.validate("release/v1.0")
        assert ok is True
        assert prefix == "release"

    def test_release_with_patch(self):
        ok, prefix, _ = mod.validate("release/v2.1.5")
        assert ok is True
        assert prefix == "release"

    def test_work_with_date(self):
        ok, prefix, _ = mod.validate("work/2026-05-30-some-topic")
        assert ok is True
        assert prefix == "work"

    def test_work_without_date_fails(self):
        ok, prefix, msg = mod.validate("work/no-date")
        assert ok is False
        assert "不符合命名规约" in msg

    def test_spec_existing_passes(self):
        # disclosure-note-full-revamp 在 active 区
        ok, prefix, _ = mod.validate("spec/disclosure-note-full-revamp")
        assert ok is True
        assert prefix == "spec"

    def test_spec_archived_passes(self):
        # phase8 在 _archive 区
        ok, prefix, _ = mod.validate("spec/phase8")
        assert ok is True
        assert prefix == "spec"

    def test_spec_nonexistent_fails(self):
        ok, prefix, msg = mod.validate("spec/totally-nonexistent-xyz-spec")
        assert ok is False
        assert "不存在" in msg

    def test_bad_branch_name_fails(self):
        ok, prefix, msg = mod.validate("just-some-name")
        assert ok is False
        assert "不符合命名规约" in msg

    def test_legacy_feature_prefix_fails(self):
        # 历史 feature/ 前缀不再合规
        ok, prefix, msg = mod.validate("feature/foo-bar")
        assert ok is False

    def test_master_fails(self):
        # master 已废弃
        ok, prefix, msg = mod.validate("master")
        assert ok is False
