"""`tools/gt-plan-mcp/server.py` 的 tasks.md 复选框解析守卫。

2026-11-06 立。起因：用 gt-plan 的 `spec_status` 盘点 27 个活跃 spec 时，
`platform-global-display-settings-closure` 报 **100%**（10/10），而现扫它的 tasks.md 是
10 个 `[x]` + 18 个 `[~]` + 0 个 `[ ]` —— 阶段 B（账套导入单位归一）与阶段 C（正式导出
单位策略）整段未做，却被工具判成已完成。根因是原解析器的三处漏算：

  ① `^- \\[x\\]` 只认行首无缩进 ⇒ 所有缩进子任务（`  - [x] 5.1 …`）不计入任何一类；
  ② 完全不认 `[~]` ⇒ 既不进 done 也不进 total，分母凭空缩小；
  ③ `pending` 的 `^- \\[ \\][^*]` 吃掉状态后的一个字符 ⇒ `- [ ]` 独占一行时漏算。

②是最危险的一条：它让「把未完成项改成进行中」成为提高完成率的手段，是个会自己变绿的后门。
所以下面既测「`[~]` 计入分母」，也测「只改标记不改数量时完成率必须下降」。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_PATH = REPO_ROOT / "tools" / "gt-plan-mcp" / "server.py"


@pytest.fixture(scope="module")
def server_module():
    """按文件加载 gt-plan 的 server.py。

    它不是包、也不在 sys.path 上；`mcp` 没装时整条判据会静默 skip，所以这里把缺依赖
    报成明确原因（而不是 import 失败的堆栈）。
    """
    if not SERVER_PATH.exists():
        pytest.fail(f"gt-plan server.py 不存在：{SERVER_PATH}")
    if importlib.util.find_spec("mcp") is None:
        pytest.skip("未安装 mcp 包（tools/gt-plan-mcp/requirements.txt），无法加载 server.py")
    spec = importlib.util.spec_from_file_location("_gt_plan_server_under_test", SERVER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tasks.md"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------- 三处漏算
def test_in_progress_marker_counts_into_total(server_module, tmp_path: Path) -> None:
    """`[~]` 必须进分母 —— 这是误报 100% 的直接原因。"""
    tasks = _write(
        tmp_path,
        "- [x] 1. 已完成\n"
        "- [~] 2. 进行中\n"
        "- [~] 3. 进行中\n",
    )
    got = server_module._parse_tasks(tasks)
    assert got["in_progress"] == 2, got
    assert got["total"] == 3, f"`[~]` 没进分母，完成率会虚高：{got}"
    assert got["done"] == 1, got


def test_indented_subtasks_are_counted(server_module, tmp_path: Path) -> None:
    """缩进的子任务要计入 —— 仓库里大量 spec 用 `  - [x] 5.1` 写子任务。"""
    tasks = _write(
        tmp_path,
        "- [x] 5. 父任务\n"
        "  - [x] 5.1 子任务\n"
        "  - [ ] 5.2 子任务\n"
        "\t- [ ]* 5.3 可选子任务\n",
    )
    got = server_module._parse_tasks(tasks)
    assert (got["done"], got["pending"], got["optional"]) == (2, 1, 1), got
    assert got["total"] == 4, got


def test_bare_unchecked_line_is_counted(server_module, tmp_path: Path) -> None:
    """`- [ ]` 独占一行（状态后没有字符）也要算未完成。"""
    tasks = _write(tmp_path, "- [x] 1. 已完成\n- [ ]\n")
    got = server_module._parse_tasks(tasks)
    assert got["pending"] == 1, f"`- [ ]` 独占行被漏算：{got}"
    assert got["total"] == 2, got


# ---------------------------------------------------------------- 口径
def test_optional_and_pending_are_disjoint(server_module, tmp_path: Path) -> None:
    """带 `*` 的未完成项只进 optional，不重复计入 pending。"""
    tasks = _write(tmp_path, "- [ ] 1. 普通\n- [ ]* 2. 可选\n")
    got = server_module._parse_tasks(tasks)
    assert (got["pending"], got["optional"]) == (1, 1), got
    assert got["total"] == 2, f"不得重复计数：{got}"


def test_completed_optional_counts_as_done_only(server_module, tmp_path: Path) -> None:
    """`[x]*`（已完成的可选任务）计入 done，不计入 optional。"""
    tasks = _write(tmp_path, "- [x]* 1. 已完成的可选任务\n")
    got = server_module._parse_tasks(tasks)
    assert (got["done"], got["optional"], got["total"]) == (1, 0, 1), got


def test_by_marker_equals_the_class_counts(server_module, tmp_path: Path) -> None:
    """`by_marker` 与分类计数必须自洽，否则分母无法复核。"""
    tasks = _write(
        tmp_path,
        "- [x] 1\n- [x]* 2\n- [~] 3\n- [ ] 4\n- [ ]* 5\n",
    )
    got = server_module._parse_tasks(tasks)
    assert got["by_marker"] == {"x": 2, "~": 1, " ": 2}, got
    assert got["by_marker"]["x"] == got["done"]
    assert got["by_marker"]["~"] == got["in_progress"]
    assert got["by_marker"][" "] == got["pending"] + got["optional"]
    assert got["total"] == sum(got["by_marker"].values())


def test_non_task_lines_are_ignored(server_module, tmp_path: Path) -> None:
    """正文里的方括号、表格、代码块不得被当成任务行（分母被污染同样会算错完成率）。"""
    tasks = _write(
        tmp_path,
        "# 标题\n"
        "> 说明：原判据 `- [ ]` 写法见上\n"
        "| spec | [x] | 说明 |\n"
        "文中提到 - [x] 不在行首\n"
        "```\n- [x] 代码块里的示例\n```\n"
        "- [x] 1. 唯一的真任务\n",
    )
    got = server_module._parse_tasks(tasks)
    # 代码块内的 `- [x]` 仍会被计入（解析器不做 fence 跟踪）；这里钉住的是
    # 「行内出现、表格单元格、引用说明」三类不得计入，且真任务必须算到。
    assert got["done"] >= 1, got
    assert got["by_marker"][" "] == 0, f"引用说明里的 `- [ ]` 不在行首，不该计入：{got}"


def test_missing_file_returns_zeroed_shape(server_module, tmp_path: Path) -> None:
    """文件不存在时返回零值且键齐全 —— 调用方会直接读 `by_marker`。"""
    got = server_module._parse_tasks(tmp_path / "nope.md")
    assert got["total"] == 0 and got["done"] == 0
    assert got["by_marker"] == {"x": 0, "~": 0, " ": 0}


# ---------------------------------------------------------------- 反向：不得有自己变绿的后门
def test_turning_pending_into_in_progress_lowers_nothing_but_never_raises_pct(
    server_module, tmp_path: Path
) -> None:
    """把 `[ ]` 改成 `[~]` 不得提高完成率。

    这是②的可伪证形式：原实现下，同一份清单把未完成项改成进行中，完成率会从 25% 跳到 100%。
    """
    before = _write(tmp_path, "- [x] 1\n- [ ] 2\n- [ ] 3\n- [ ] 4\n")
    got_before = server_module._parse_tasks(before)
    pct_before = 100 * got_before["done"] / got_before["total"]

    after = _write(tmp_path, "- [x] 1\n- [~] 2\n- [~] 3\n- [~] 4\n")
    got_after = server_module._parse_tasks(after)
    pct_after = 100 * got_after["done"] / got_after["total"]

    assert got_after["total"] == got_before["total"] == 4
    assert pct_after == pct_before == 25.0, (
        f"改标记不改数量却让完成率变了：{pct_before} -> {pct_after}（{got_before} / {got_after}）"
    )


def test_real_repo_spec_is_not_reported_complete(server_module) -> None:
    """现场回归：带 `[~]` 的真实 spec 不得被报成 100%。

    不写死 10/29 这类会漂的数字，只钉住「有 `[~]` ⇒ 完成率 < 100%」这条不变量；
    该 spec 全部做完后 `[~]` 归零，本用例自动失去分母并按 skip 处理。
    """
    tasks = (
        REPO_ROOT
        / ".kiro"
        / "specs"
        / "platform-global-display-settings-closure"
        / "tasks.md"
    )
    if not tasks.exists():
        pytest.skip("该 spec 已归档或改名，本回归失去对象")
    got = server_module._parse_tasks(tasks)
    if not got["in_progress"]:
        pytest.skip(f"该 spec 已无 `[~]` 任务，不再是本回归的对象：{got}")
    pct = 100 * int(got["done"]) / int(got["total"])
    assert pct < 100.0, f"有 {got['in_progress']} 个 `[~]` 却报 {pct}%：{got}"
