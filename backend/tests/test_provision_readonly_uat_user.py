"""只读 UAT 账号工具的决策与参数（spec trim-generation-plan-followup-optimizations R5.1 / R5.2，纯函数，不连库）。

写库路径（单事务、只写两张表、并发、回滚、撤销后重建）见 ``test_provision_readonly_uat_user_pg.py``。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import uuid

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "e2e" / "provision_readonly_uat_user.py"


def load_tool():
    """按文件加载脚本（scripts/e2e 不是包）；dataclass 需要模块先登记进 sys.modules。"""
    name = "provision_readonly_uat_user"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()

PID = uuid.UUID(int=1)
UID = uuid.UUID(int=2)


def _project(status="created", deleted=False):
    return tool.ProjectFacts(PID, "【测试】只读 UAT", status, deleted)


def _user(role="readonly", active=True, deleted=False):
    return tool.UserFacts(UID, "uat_reader", role, active, deleted, "hash")


def _member(role="readonly", level="readonly", scope=frozenset()):
    return tool.MemberFacts(uuid.uuid4(), role, level, frozenset(scope))


def _snap(project="ok", user=None, members=(), others=()):
    return tool.Snapshot(_project() if project == "ok" else project, user, tuple(members), tuple(others))


def test_standard_cycles_match_visibility_scope_and_scope_parsing():
    from app.services.wp_visibility.effective_scope import STANDARD_CYCLES

    assert tool.STANDARD_CYCLES == STANDARD_CYCLES
    assert tool.parse_scope(None) is None
    assert tool.parse_scope(" all ") == STANDARD_CYCLES
    assert tool.parse_scope("d, e ,D") == frozenset({"D", "E"})
    assert tool.parse_scope("") == frozenset(), "空串 = 显式清空（只读成员看不到底稿）"
    for bad in ("X", "D,AA", "全部"):
        with pytest.raises(ValueError):
            tool.parse_scope(bad)
    assert tool.format_scope(frozenset({"E", "D"})) == "D,E"
    assert tool.format_scope(frozenset()) is None


@pytest.mark.parametrize(
    ("snapshot", "scope", "password_ok", "actions"),
    [
        (_snap(), frozenset({"D"}), None, ("create_user", "create_member")),
        (_snap(user=_user()), None, True, ("create_member",)),
        (_snap(user=_user(active=False)), None, True, ("reactivate_user", "create_member")),
        (_snap(user=_user(), members=[_member(scope={"D"})]), frozenset({"D"}), True, ()),
        (_snap(user=_user(), members=[_member(scope={"D"})]), None, True, ()),
        (_snap(user=_user(), members=[_member(scope={"D"})]), frozenset({"D", "E"}), True, ("update_scope",)),
        (_snap(user=_user(), members=[_member()]), None, None, ()),  # 只报告：没有密码可校验，不算拒绝
    ],
    ids=["new", "reuse_user", "reactivate", "noop_same_scope", "noop_scope_unchanged", "update_scope", "dry_run"],
)
def test_provision_actions(snapshot, scope, password_ok, actions):
    plan = tool.decide(snapshot, mode="provision", scope=scope, password_ok=password_ok)
    assert plan.allowed, plan.refusals
    assert plan.actions == actions


@pytest.mark.parametrize(
    ("snapshot", "password_ok", "needle"),
    [
        (_snap(project=None), None, "项目不存在"),
        (_snap(project=_project(deleted=True)), None, "项目已删除"),
        (_snap(project=_project(status="archived")), None, "项目已归档"),
        (_snap(user=_user(role="auditor")), True, "不是只读专用账号"),
        (_snap(user=_user(role="admin")), True, "不是只读专用账号"),
        (_snap(user=_user(deleted=True)), True, "已删除"),
        (_snap(user=_user()), False, "密码不符"),
        (_snap(user=_user(), members=[_member(role="auditor", level="edit")]), True, "高于只读"),
        (_snap(user=_user(), members=[_member(level="review")]), True, "高于只读"),
        (_snap(user=_user(), members=[_member(), _member()]), True, "数据异常"),
    ],
    ids=["no_project", "deleted_project", "archived", "auditor_user", "admin_user", "deleted_user", "bad_password",
         "auditor_member", "review_level", "two_members"],
)
def test_provision_refusals_write_nothing(snapshot, password_ok, needle):
    plan = tool.decide(snapshot, mode="provision", scope=frozenset({"D"}), password_ok=password_ok)
    assert not plan.allowed
    assert any(needle in r for r in plan.refusals), plan.refusals
    assert plan.actions == (), "拒绝时不得带任何动作（不做部分写入）"


@pytest.mark.parametrize(
    ("snapshot", "allowed", "actions"),
    [
        (_snap(user=_user(), members=[_member()]), True, ("revoke_member", "deactivate_user")),
        (_snap(user=_user(active=False), members=[_member()]), True, ("revoke_member",)),
        (_snap(user=_user(), members=[]), True, ("deactivate_user",)),
        (_snap(user=_user(active=False), members=[]), True, ()),
        (_snap(project=_project(status="archived"), user=_user(), members=[_member()]), True,
         ("revoke_member", "deactivate_user")),  # 收权对已归档项目照样放行
        (_snap(user=None), False, ()),
        (_snap(user=_user(role="manager"), members=[_member()]), False, ()),
        (_snap(user=_user(), members=[_member(role="auditor", level="edit")]), False, ()),
    ],
    ids=["revoke", "already_inactive", "no_member", "noop", "archived_project", "no_user", "manager_user",
         "foreign_member"],
)
def test_revoke_is_precise(snapshot, allowed, actions):
    plan = tool.decide(snapshot, mode="revoke", scope=None, password_ok=None)
    assert plan.allowed is allowed, plan.refusals
    assert plan.actions == actions


@pytest.mark.parametrize(
    "argv",
    [
        ["--project-id", "not-a-uuid", "--username", "u"],
        ["--project-id", str(PID), "--username", " u"],
        ["--project-id", str(PID), "--username", "a b"],
        ["--project-id", str(PID), "--username", "u", "--apply"],
        ["--project-id", str(PID), "--username", "u", "--apply", "--confirm-project-id", str(uuid.UUID(int=9))],
        ["--project-id", str(PID), "--username", "u", "--revoke", "--scope-cycles", "D"],
        ["--project-id", str(PID), "--username", "u", "--scope-cycles", "Z"],
    ],
    ids=["bad_uuid", "leading_space", "inner_space", "apply_without_confirm", "confirm_mismatch",
         "revoke_with_scope", "bad_scope"],
)
def test_usage_errors_exit_before_touching_the_database(argv, monkeypatch, capsys):
    called = []
    monkeypatch.setattr(tool, "asyncio", type("NoAsyncio", (), {"run": staticmethod(lambda *_a, **_k: called.append(1))}))
    assert tool.main(argv) == tool.EXIT_USAGE
    assert not called, "参数错误必须在连库之前返回"
    assert "参数错误" in capsys.readouterr().err


def test_short_password_is_rejected_and_never_echoed(monkeypatch, capsys):
    monkeypatch.setenv(tool.PASSWORD_ENV, "short-pw")
    monkeypatch.setattr(tool, "asyncio", type("NoAsyncio", (), {"run": staticmethod(lambda *_a, **_k: 1 / 0)}))
    assert tool.main(["--project-id", str(PID), "--username", "uat_reader"]) == tool.EXIT_USAGE
    captured = capsys.readouterr()
    assert "short-pw" not in captured.out + captured.err


def test_check_password_only_touches_readonly_accounts_and_survives_broken_hashes():
    from app.core.security import hash_password

    good = tool.UserFacts(UID, "uat_reader", "readonly", True, False, hash_password("Uat-Readonly-2026!"))
    assert tool.check_password(_snap(user=good), "Uat-Readonly-2026!") is True
    assert tool.check_password(_snap(user=good), "Wrong-Password-2026") is False
    assert tool.check_password(_snap(user=good), None) is None
    broken = tool.UserFacts(UID, "uat_reader", "readonly", True, False, "not-a-bcrypt-hash")
    assert tool.check_password(_snap(user=broken), "Uat-Readonly-2026!") is False, "哈希损坏按不符拒绝，不崩"
    other = tool.UserFacts(UID, "uat_reader", "auditor", True, False, "h")
    assert tool.check_password(_snap(user=other), "Uat-Readonly-2026!") is None, "非只读账号由角色拒绝，不校验密码"
    assert tool.check_password(_snap(), "Uat-Readonly-2026!") is None


def test_password_is_not_a_command_line_option():
    with pytest.raises(SystemExit):
        tool._parse_args(["--project-id", str(PID), "--username", "u", "--password", "x" * 20])
