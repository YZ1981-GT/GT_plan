# -*- coding: utf-8 -*-
"""push_version 的远端视图与有限重试安全边界。"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / ".git-hooks" / "push_version.py"


def _load():
    spec = importlib.util.spec_from_file_location("_push_version_safety", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_same_atomic_push_retry_requires_unchanged_branch_and_unused_tag() -> None:
    mod = _load()
    tags = {"v1.0.1": ("tag-1", "commit-1")}
    assert mod.may_retry_same_atomic_push(
        branch_before="a" * 40,
        branch_after="a" * 40,
        tag_name="v1.0.2",
        tags_before=tags,
        tags_after=tags,
    )
    assert not mod.may_retry_same_atomic_push(
        branch_before="a" * 40,
        branch_after="b" * 40,
        tag_name="v1.0.2",
        tags_before=tags,
        tags_after=tags,
    )
    assert not mod.may_retry_same_atomic_push(
        branch_before="a" * 40,
        branch_after="a" * 40,
        tag_name="v1.0.2",
        tags_before=tags,
        tags_after={**tags, "v1.0.2": ("other", "other")},
    )
    assert not mod.may_retry_same_atomic_push(
        branch_before="a" * 40,
        branch_after="a" * 40,
        tag_name="v1.0.2",
        tags_before=tags,
        tags_after={**tags, "v2.0.0": ("tag-2", "commit-2")},
    )
    assert mod.may_retry_same_atomic_push(
        branch_before="a" * 40,
        branch_after="a" * 40,
        tag_name="v1.0.2",
        tags_before=tags,
        tags_after={**tags, "release-note": ("note", "commit")},
    )
    assert not mod.may_retry_same_atomic_push(
        branch_before="a" * 40,
        branch_after=None,
        tag_name="v1.0.2",
        tags_before=tags,
        tags_after=tags,
    )


def test_fetch_failure_stops_before_tag_or_push(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    mod = _load()
    git_calls: list[tuple[str, ...]] = []
    run_calls: list[list[str]] = []

    def fake_git(*args: str, **_kwargs) -> str:
        git_calls.append(args)
        if args[:2] == ("status", "--porcelain=v1"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return "a" * 40 + "\n"
        raise AssertionError(f"fetch 失败后不应继续 git：{args}")

    def fake_run(cmd, **_kwargs):
        run_calls.append(list(cmd))
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"network unavailable")

    monkeypatch.setattr(mod, "git", fake_git)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    args = SimpleNamespace(
        remote="origin",
        branch="spec/example",
        change=["安全测试变动"],
        notes_file=None,
        bump="patch",
        version=None,
        dry_run=False,
        no_push=False,
    )
    assert mod.cmd_push(args) == 1
    assert run_calls == [["git", "fetch", "--prune", "--no-tags", "origin"]]
    assert "无法证明远端视图是最新" in capsys.readouterr().err
    assert all("tag" not in call and "push" not in call for call in git_calls)


def test_remote_branch_sha_preserves_failure_vs_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    replies = iter([
        SimpleNamespace(returncode=1, stdout=b"", stderr=b"offline"),
        SimpleNamespace(returncode=0, stdout=b"", stderr=b""),
        SimpleNamespace(returncode=0, stdout=(b"a" * 40) + b"\trefs/heads/x\n", stderr=b""),
    ])
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: next(replies))
    assert mod.remote_branch_sha("origin", "x") is None
    assert mod.remote_branch_sha("origin", "x") == ""
    assert mod.remote_branch_sha("origin", "x") == "a" * 40


def test_push_tool_never_invokes_history_rewrite_or_force() -> None:
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    forbidden = {"rebase", "cherry-pick", "--force", "--force-with-lease"}
    invoked: set[str] = set()
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        for arg in call.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                invoked.add(arg.value)
            elif isinstance(arg, (ast.List, ast.Tuple)):
                invoked.update(
                    elt.value
                    for elt in arg.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                )
    assert forbidden.isdisjoint(invoked)


def test_check_push_rejects_when_remote_tags_are_unreadable(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "remote_tag_map", lambda _remote: None)
    update = mod.RefUpdate(
        local_ref="refs/heads/spec/example",
        local_sha="a" * 40,
        remote_ref="refs/heads/spec/example",
        remote_sha="b" * 40,
    )

    assert mod.check_push("origin", [update]) == 1
    assert "取不到远端标签清单" in capsys.readouterr().out


def test_previous_version_base_prefers_remote_peeled_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load()
    head = "f" * 40
    newest_non_ancestor = "d" * 40
    remote_ancestor = "c" * 40
    calls: list[tuple[str, ...]] = []

    def fake_git_ok(*args: str) -> bool:
        calls.append(args)
        if args[:2] == ("cat-file", "-e"):
            return True
        if args[:2] == ("merge-base", "--is-ancestor"):
            return args[2] == remote_ancestor and args[3] == head
        raise AssertionError(args)

    monkeypatch.setattr(mod, "git_ok", fake_git_ok)
    commit, label = mod.previous_version_base(
        "origin",
        head,
        local_tags={},
        remote_tags={
            "v1.0.32": ("tag-32", newest_non_ancestor),
            "v1.0.31": ("tag-31", remote_ancestor),
            "release-note": ("tag-note", remote_ancestor),
        },
    )

    assert (commit, label) == (remote_ancestor, "自 v1.0.31 起")
    assert ("merge-base", "--is-ancestor", newest_non_ancestor, head) in calls
