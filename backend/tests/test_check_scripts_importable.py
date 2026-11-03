# -*- coding: utf-8 -*-
"""`backend/scripts/check/*.py` 带兄弟模块顶层 import 的脚本必须能被 importlib 加载。

## 为什么需要这条判据

`backend/scripts/check/` 下有共享 helper（如 `_spec_dir.py`），同目录脚本用
`from _spec_dir import resolve_spec_dir` 直接引用。这类引用有一个**只在一条调用路径上
成立**的隐含前提：

* `python backend/scripts/check/x.py` —— Python 自动把脚本所在目录放进 `sys.path[0]`，
  import 成功；
* `importlib.util.spec_from_file_location(...)` + `exec_module(...)` —— **不动 sys.path**，
  import 期直接 `ModuleNotFoundError`。

而这些门的 pytest 守卫恰恰走第二条路径（它们要在测试里调用门函数，而不是起子进程）。
于是形成一种很难看见的失效：**门当 CLI 跑是绿的，它自己的测试模块却连采集都过不去**。

2026-11-01 实测命中 `check_task44_oo94_excel_pilot_gate.py` 与
`check_task61_oo94_word_pilot_gate.py` 两个采集错误。CI 的 backend-tests 是
`pytest backend/tests/ -x` —— 一个采集错误就把整个 job 停在这里，后面所有测试都不再跑。
也就是说，这不是「两条测试红」，而是「整条后端测试链被一行 import 掐断」。

## 判据形态

1. 发现面：扫 `scripts/check/*.py`，取**顶层**（缩进为 0、不在函数/类体内）import 了
   同目录兄弟模块的脚本。分母为空即打红 —— 否则扫描器瞎了会呈现成「全都没问题」。
2. 逐个用 importlib 真加载。只要有一个抛异常就点名它和异常末行。
3. 发现谓词可伪证：合成一个「顶层 import 兄弟模块」的样本必须被认出，
   合成一个「函数体内 import」的样本必须**不**被认出（后者没有这个问题）。
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CHECK_DIR = BACKEND / "scripts" / "check"

if str(BACKEND) not in sys.path:  # 这些门普遍 `from app...` 取生产符号
    sys.path.insert(0, str(BACKEND))


def _sibling_module_names() -> set[str]:
    """同目录下可被 import 的兄弟模块名（不含脚本自身要测的那一个）。"""
    return {p.stem for p in CHECK_DIR.glob("*.py") if p.stem != "__init__"}


def _top_level_sibling_imports(source: str, siblings: set[str]) -> set[str]:
    """顶层 import 了哪些兄弟模块。

    只认 `ast.Module.body` 的直接子节点 —— 函数体内的延迟 import 不受 sys.path 时序影响
    （调用时脚本往往已经自己补过路径），把它们算进来会造出一批假阳。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - 语法错误由别的门负责
        return set()
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module in siblings:
                found.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in siblings:
                    found.add(alias.name)
    return found


def _targets() -> list[tuple[pathlib.Path, set[str]]]:
    siblings = _sibling_module_names()
    out: list[tuple[pathlib.Path, set[str]]] = []
    for path in sorted(CHECK_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        hits = _top_level_sibling_imports(path.read_text(encoding="utf-8"), siblings)
        if hits:
            out.append((path, hits))
    return out


#: 在**干净子进程**里加载单个脚本的探针源码。
#:
#: 🔴 必须隔离，不能在本进程里顺序加载。第一版就是在本进程里 `exec_module` 的，结果
#:    磁盘变异（把某个脚本的 sys.path 补丁摘掉 = 回到缺陷版）**没有打红**：同一会话里
#:    按字母序更早加载的脚本已经把 `scripts/check` 插进了 `sys.path`，于是后面的脚本
#:    白捡这条路径。也就是说，那一版判据测的是「这一批脚本里**至少有一个**补过路径」，
#:    而真实失效场景恰恰是「单独采集某一个测试模块」—— 判据与它要防的事情错位。
_PROBE = r"""
import importlib.util, json, sys, traceback
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("_probe_target", path)
module = importlib.util.module_from_spec(spec)
# 先登记进 sys.modules：`@dataclass` 在 `_is_type` 里按 sys.modules[cls.__module__]
# 反查命名空间，没登记会抛 AttributeError —— 那是探针自己的毛病，会被误读成被测脚本坏了。
sys.modules[spec.name] = module
try:
    spec.loader.exec_module(module)
    print(json.dumps({"ok": True, "err": ""}))
except BaseException:
    lines = traceback.format_exc().strip().splitlines()
    print(json.dumps({"ok": False, "err": lines[-1] if lines else "unknown"}))
"""


def _load(path: pathlib.Path) -> tuple[bool, str]:
    """在干净子进程里加载，返回 (是否成功, 异常末行)。

    子进程 cwd = `backend/`，所以 `from app...` 能解析，而
    `backend/scripts/check` **不在** sys.path 上 —— 这正是 pytest 采集这些守卫时的真实
    路径状态。
    """
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, str(path)],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(BACKEND)},
        timeout=300,
    )
    tail = (proc.stdout or "").strip().splitlines()
    for line in reversed(tail):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return bool(payload["ok"]), str(payload["err"])
    # 子进程连 JSON 都没打出来（崩在解释器层 / 被 kill）—— 当失败，并带上 stderr 末行
    stderr_tail = (proc.stderr or "").strip().splitlines()
    return False, f"rc={proc.returncode} {stderr_tail[-1] if stderr_tail else '无输出'}"


def test_discovery_denominator_is_not_empty() -> None:
    targets = _targets()
    assert targets, (
        "没有发现任何「顶层 import 兄弟模块」的 check 脚本 —— 扫描面塌了，"
        "下面那条逐个加载的判据会在空集上恒绿"
    )


def test_discovery_predicate_is_falsifiable() -> None:
    """发现谓词必须认出顶层兄弟 import，且不把函数体内的 import 算进来。"""
    siblings = {"_spec_dir", "_helper"}
    top = "from _spec_dir import resolve_spec_dir\nX = 1\n"
    assert _top_level_sibling_imports(top, siblings) == {"_spec_dir"}
    plain = "import _helper\n"
    assert _top_level_sibling_imports(plain, siblings) == {"_helper"}
    lazy = "def f():\n    from _spec_dir import resolve_spec_dir\n    return resolve_spec_dir\n"
    assert _top_level_sibling_imports(lazy, siblings) == set(), (
        "函数体内的延迟 import 被当成顶层 ⇒ 会造出一批假阳"
    )
    unrelated = "from app.core.config import settings\nimport json\n"
    assert _top_level_sibling_imports(unrelated, siblings) == set()


@pytest.mark.parametrize(
    "path",
    [p for p, _ in _targets()],
    ids=[p.stem for p, _ in _targets()],
)
def test_check_script_is_importable_via_importlib(path: pathlib.Path) -> None:
    ok, err = _load(path)
    assert ok, (
        f"{path.name} 无法被 importlib 加载：{err}\n"
        "它当 CLI 能跑（Python 自动把脚本目录放进 sys.path[0]），但测试走 "
        "`spec_from_file_location` 这条路径不动 sys.path ⇒ 它的守卫连采集都过不去，"
        "而 CI 的 backend-tests 是 `pytest -x`，一个采集错误会停掉整个 job。"
        "修法：在该 import 之前显式把脚本自己的目录补进 sys.path。"
    )
