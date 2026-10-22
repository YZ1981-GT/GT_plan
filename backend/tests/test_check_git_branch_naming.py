"""repo-git-workflow-unification spec / Sprint 4 / Task 4.2

check_git_branch_naming.py 单元测试 - 5 类前缀 + 不合规 + 无 spec 目录 + 各种归档形态。

2026-10-22：脚本已搬到 ``scripts/check/``，原导入路径失效（整文件收集即报错）；spec 分支用例改为在临时目录
里造活跃 / 归档目录，不再依赖仓库当前有哪些 spec。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "check"))
import check_git_branch_naming as mod  # noqa: E402


@pytest.fixture
def specs_root(tmp_path, monkeypatch):
    specs = tmp_path / ".kiro" / "specs"
    for d in ("active-spec", "_archive/50-numbered-spec", "_archive/23-some-group/grouped-spec",
              "_archive/plain-archived-spec"):
        (specs / d).mkdir(parents=True)
    for d in ("_archive/50-numbered-spec", "_archive/23-some-group/grouped-spec"):
        (specs / d / "tasks.md").write_text("# tasks\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    return specs


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

    @pytest.mark.parametrize("name", ["active-spec", "numbered-spec", "grouped-spec", "plain-archived-spec"])
    def test_spec_active_or_archived_passes(self, specs_root, name):
        # 活跃区 / 归档为 NN-<name> / 归入分组 NN-<分组>/<name> / 早期不带序号的归档
        ok, prefix, msg = mod.validate(f"spec/{name}")
        assert (ok, prefix, msg) == (True, "spec", "")

    @pytest.mark.parametrize("name", ["totally-nonexistent-xyz-spec", "some-group", "spec", "numbered"])
    def test_spec_nonexistent_fails(self, specs_root, name):
        # 分组目录名本身、序号前缀的片段都不算 spec
        ok, prefix, msg = mod.validate(f"spec/{name}")
        assert ok is False and prefix == "spec"
        assert "不存在" in msg

    def test_real_repo_archived_spec_branch_passes(self):
        # 真实仓库：按约定归档为 _archive/50-… 的 spec 分支（原实现拒推）
        assert mod.validate("spec/disclosure-note-doc-upload-and-batch-fill")[0] is True

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
