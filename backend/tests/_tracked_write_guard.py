"""守卫：用例不得把 git 已跟踪的文件改掉不还原（formula-fetch-followup-defect-closure 6.6）。

背景：两组用例每跑一次就改写仓库里的已跟踪文件 ——
  · ``test_workpaper_route_task1_baseline`` 无条件重写 ``tests/_snapshots/…json``（还带 generated_at_epoch）；
  · ``procedure_delegation_visibility`` 的 task14 / 15 / 17 把本次计时、样例数写回归档 evidence
    （manifest 钉了 sha256）。
单跑一个文件看不出来，跑完一批 ``git status`` 才冒出一串改动，还容易被顺手提交进去。

做法：``sys.addaudithook`` 监听本进程的写方式 ``open``、``os.rename`` / ``os.replace`` 两端、
``os.remove``、``os.truncate``、``_winapi.CopyFile2`` 的目标（Windows 上 ``shutil.copy2`` 走它）。
目标是已跟踪文件时，在第一次写之前记下原字节摘要；每个用例跑完（含 teardown）后重算：
已还原（变异测试写完即恢复）就放过，没还原的留到会话结束再核一次（模块级 fixture 可能晚些还原），
仍不一致即判失败 —— 列出文件与第一次写它的用例，退出码置 1。

不覆盖：子进程里的写入（审计钩子只在本进程生效）；整目录改名。
放行：``GT_UPDATE_SNAPSHOTS=1``（显式要求重写已提交的快照 / 基线时）。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

PLUGIN_NAME = "gt-tracked-write-guard"
ALLOW_ENV = "GT_UPDATE_SNAPSHOTS"

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_EVENTS = frozenset({"open", "os.rename", "os.remove", "os.truncate", "_winapi.CopyFile2"})
_MISSING = "<不存在>"
_UNREADABLE = "<读不出>"


@dataclass
class _Entry:
    digest: str
    writer: str


@dataclass
class _State:
    armed: bool = False
    #: 武装守卫的那个 config（进程内嵌套 pytest.main 的会话不接管、不收尾）
    owner: object | None = None
    #: 归一化绝对路径 → git 里的相对路径
    tracked: dict[str, str] = field(default_factory=dict)
    current: str = "<收集阶段>"
    window: dict[str, _Entry] = field(default_factory=dict)
    leftovers: dict[str, _Entry] = field(default_factory=dict)
    local: threading.local = field(default_factory=threading.local)


STATE = _State()
_HOOK_INSTALLED = False


def is_write_open(mode: object, flags: object) -> bool:
    """``open`` 审计事件是否以写方式打开（``open()`` 给 mode 串，``os.open`` 给 None + flags）。"""
    if isinstance(mode, str):
        return any(ch in mode for ch in "wax+")
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def write_targets(event: str, args: tuple) -> tuple:
    """审计事件里会被改动的路径参数（原样返回，未归一化）。"""
    if event == "open":
        return (args[0],) if len(args) >= 3 and is_write_open(args[1], args[2]) else ()
    if event == "os.rename":  # os.rename / os.replace：源没了、目标被盖
        return tuple(args[:2])
    if event in ("os.remove", "os.truncate"):
        return tuple(args[:1])
    if event == "_winapi.CopyFile2":
        return tuple(args[1:2])
    return ()


def normalize(path: object) -> str | None:
    if isinstance(path, int):
        return None
    try:
        text = os.fsdecode(os.fspath(path))
    except TypeError:
        return None
    return os.path.normcase(os.path.abspath(text))


def _tracked_key(raw: object, tracked: dict[str, str]) -> str | None:
    """路径是已跟踪文件时返回登记用的键；Windows 8.3 短名（``ADMINI~1``）再按真实路径查一次。"""
    key = normalize(raw)
    if key is None:
        return None
    if key in tracked:
        return key
    if "~" in key:
        real = os.path.normcase(os.path.realpath(key))
        if real in tracked:
            return real
    return None


def _digest(key: str) -> str:
    sha = hashlib.sha256()
    try:
        with open(key, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                sha.update(chunk)
    except FileNotFoundError:
        return _MISSING
    except OSError:
        return _UNREADABLE
    return sha.hexdigest()


def _hook(event: str, args: tuple) -> None:
    if event not in _EVENTS:
        return
    st = STATE
    if not st.armed or getattr(st.local, "busy", False):
        return
    st.local.busy = True  # 下面读原文件也会触发 open 事件
    try:
        for raw in write_targets(event, args):
            key = _tracked_key(raw, st.tracked)
            if key is None or key in st.window or key in st.leftovers:
                continue
            st.window[key] = _Entry(_digest(key), st.current)
    except Exception:  # noqa: BLE001 —— 审计钩子抛错会让被审计的调用本身失败，宁可漏记
        pass
    finally:
        st.local.busy = False


def _changed(entries: dict[str, _Entry]) -> dict[str, _Entry]:
    # list()：后台线程可能正往里登记
    return {key: entry for key, entry in list(entries.items()) if _digest(key) != entry.digest}


def tracked_files(start: Path) -> dict[str, str] | None:
    """``start`` 所在 git 工作树的已跟踪文件（归一化绝对路径 → 相对路径）；不在工作树里时返回 None。"""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                             capture_output=True, timeout=60)
        if top.returncode != 0:
            return None
        root = Path(top.stdout.decode("utf-8", "replace").strip())
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=120)
        if listed.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    names = listed.stdout.decode("utf-8", "surrogateescape").split("\0")
    root = Path(os.path.realpath(root))
    return {normalize(root / name): name for name in names if name}


def pytest_configure(config: pytest.Config) -> None:
    global _HOOK_INSTALLED
    if os.environ.get(ALLOW_ENV) == "1" or STATE.armed:
        return
    found = tracked_files(Path(str(config.rootpath)))
    if not found:
        return
    STATE.tracked = found
    if not _HOOK_INSTALLED:
        sys.addaudithook(_hook)
        _HOOK_INSTALLED = True
    STATE.owner = config
    STATE.armed = True


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    STATE.current = item.nodeid
    try:
        return (yield)
    finally:
        for key, entry in _changed(STATE.window).items():
            STATE.leftovers.setdefault(key, entry)
        STATE.window.clear()
        STATE.current = "<用例之间>"


@pytest.hookimpl(tryfirst=True, specname="pytest_sessionfinish")
def pytest_sessionfinish__enter(session: pytest.Session, exitstatus: int) -> None:
    """其他插件 / conftest 的 pytest_sessionfinish 里写的文件记在「会话收尾」名下。

    函数名必须以 ``pytest_`` 开头：pytest 只把这类名字当钩子实现，其余名字连 specname 都不看。
    """
    STATE.current = "<会话收尾（pytest_sessionfinish）>"


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not STATE.armed or session.config is not STATE.owner:
        return
    bad = {**_changed(STATE.leftovers), **_changed(STATE.window)}
    STATE.armed = False  # 之后的写（报告插件等）不再记
    STATE.owner = None
    STATE.window.clear()
    STATE.leftovers.clear()
    if not bad:
        return
    lines = ["以下已跟踪文件在本次测试运行后与运行前不一致（只统计本进程写过的文件）："]
    for key, entry in sorted(bad.items(), key=lambda kv: STATE.tracked.get(kv[0], kv[0])):
        lines.append(f"  {STATE.tracked.get(key, key)}  ← 首次写入：{entry.writer}")
    lines.append("处置：改写到 tmp_path 或 tests/_test_artifacts.artifact_dir()；"
                 f"确需重写已提交的快照 / 基线时设 {ALLOW_ENV}=1。")
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "用例改写了已跟踪文件", red=True)
        for line in lines:
            reporter.write_line(line)
    else:
        sys.stderr.write("\n".join(lines) + "\n")
    if session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
