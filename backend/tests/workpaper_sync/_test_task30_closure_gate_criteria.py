"""test_task30_closure_gate —— 判据层（tasks.md / 里程碑定义的解析 helper 与常量）。

从 `backend/tests/workpaper_sync/test_task30_closure_gate.py` 拆出：2026-11-04 把 doc 派生判据
改绑 Wave 6 冻结快照、当前归属改读里程碑定义之后，原文件到 902 行，超过 pre-commit 的 800 行
门禁。**不加 file_size_whitelist** —— 白名单表头写明「仅历史大文件」，新增文件套用属滥用。

刻意与用例文件**同目录**：`Path(__file__).parents[3]` 的路径推算移到子目录会整体错一层。
搬过来的定义逐行等于原文；用例层的 import 清单由拆分脚本按实际引用算出。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))


_SPEC_NAME = "workpaper-html-onlyoffice-bidirectional-writeback-closure"


#: active（2026-11-01 重写后，两级任务号）的 tasks.md —— 只用来读**当前**归属方点名的待清行。
_ACTIVE_TASKS_MD = _REPO / ".kiro" / "specs" / _SPEC_NAME / "tasks.md"


_MILESTONE_DEFINITIONS = (
    _BACKEND / "data" / "workpaper_sync_program_milestone_definitions.json"
)


#: Wave 6 形态（整数任务号、依赖图 `gates`、20 → 30 → 71 的接手语）在冻结快照里的内容标记。
_FROZEN_TASKS_MARKERS = (
    r"^- \[[ x~\-]\] 30\.\s",
    r"^- \[[ x~\-]\] 71\.\s",
    r"自 Task \d+ 移交至本门",
    r'"gates"\s*:',
)


#: 那一条 criterion 的门内 key。**不抄名单**（4 条行名与归属任务号都从 tasks.md 解析，
#: 与 `test_task20_writer_gate.py` 同源），只固定这一个 key。
_CRITERION_KEY = "multi_resolver"


_TASK_HEAD_RE = re.compile(r"^- \[[ x~\-]\] (\d+)\.\s")


#: 「自 Task M 移交至本门」= 该任务**接手**这条 criterion，即当前裁决归属。
_ASSUME_RE = re.compile(r"自 Task (\d+) 移交至本门")


def _frozen_tasks_md() -> Path:
    """Wave 6 形态 tasks.md 的冻结快照（按内容标记定位，与 0.6 重绑旧消费方同一实现）。

    🔴 2026-11-04：本 spec 2026-11-01 被重写成两级任务号，active tasks.md 里没有 Task 30 / 71，
    依赖图也没有 `gates` ⇒ 本文件的 doc 派生判据原先全部报「一个任务都没解析出来」。这些判据
    核对的是 Wave 6 的**移交历史**（20 → 30 → 71 的成环理由、gate / wave 形状、阻塞登记指向的
    发布门任务），它们在冻结快照里、不会再变；**当前**归属与待清名单改读 active 计划（见
    `_active_owner_task` / `_active_owner_named_rows`）。
    """
    from app.core.spec_docs import resolve_spec_dir

    spec_dir = resolve_spec_dir(
        _SPEC_NAME,
        require_files=("tasks.md",),
        require_matches={"tasks.md": _FROZEN_TASKS_MARKERS},
    )
    path = spec_dir / "tasks.md"
    assert path.is_file(), "Wave 6 形态的 tasks.md 在 active 与归档快照里都找不到"
    assert "_archive" in spec_dir.parts, (
        f"Wave 6 形态竟解析到 {spec_dir} —— active 若回到整数任务号，本文件 active / 冻结的分工"
        "要重判，不能默默通过"
    )
    return path


def _tasks_md_text() -> str:
    """Wave 6 冻结快照的 tasks.md 文本，**换行符归一化**后返回。

    🔴 不能用 `read_bytes().decode("utf-8")`：`.gitattributes` 没有对 `*.md` 强制
    `eol=lf`，所以 Windows 工作树里 tasks.md 是 **CRLF**。裸 decode 会把 `\\r` 留在
    行尾，于是 `re.M` 下的 `^…$` 锚点全部失配 —— `## Task Dependency Graph` 明明在
    文件里（第 17 行），判据却报「找不到 json 块」，把一个**解析缺陷**伪装成
    「文档缺章节」。同 spec 的 `generate_workpaper_sync_program_milestones.py` 一直用
    `read_text()`（universal newlines）读同一个文件，本处与之对齐。
    """
    return (
        _frozen_tasks_md().read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    )


def _active_owner_task() -> str:
    """当前计划里持有 `multi_resolver` 的任务号。

    来源是里程碑定义：谓词 `writer_gate_issue_zero(multi_resolver)` 所在 milestone 的本 spec
    producer。重写后的 tasks.md 用两级任务号，Wave 6 那句「自 Task M 移交至本门」写不进去
    （2.8 正文已登记这一点），而 producer 映射本来就是机器可读、经审核的单一来源。
    """
    definitions = json.loads(_MILESTONE_DEFINITIONS.read_text(encoding="utf-8"))
    owners = sorted(
        {
            task
            for milestone in definitions["milestones"]
            if any(
                predicate.get("type") == "writer_gate_issue_zero"
                and predicate.get("issue") == _CRITERION_KEY
                for predicate in milestone.get("predicates") or ()
            )
            for producer in milestone.get("producers") or ()
            if producer.get("spec") == _SPEC_NAME
            for task in producer.get("tasks") or ()
        }
    )
    assert len(owners) == 1, (
        f"里程碑定义里清零 `{_CRITERION_KEY}` 的 producer 不是恰一个：{owners}（0 = 无人守，"
        ">1 = 两个任务都自称归属）"
    )
    return owners[0]


def _active_task_body(task_id: str) -> list[str]:
    """active tasks.md 里 ``task_id`` 的正文行（两级任务号，行首锚定）。"""
    head_re = re.compile(r"^- \[[ xX~\-]\]\*? (\d+(?:\.\d+)*)\s")
    text = _ACTIVE_TASKS_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
    body: list[str] | None = None
    for line in text.split("\n"):
        head = head_re.match(line)
        if head:
            if body is not None:
                break
            if head.group(1) == task_id:
                body = [line]
            continue
        if body is not None:
            if line.startswith("#"):
                break
            body.append(line)
    assert body, f"active tasks.md 里找不到任务 {task_id}"
    return body


def _active_owner_named_rows(owner: str) -> tuple[int, set[str]]:
    """当前归属任务正文点名的「N 条 resolver 行（`module::function`、…）」。

    与 `test_task20_writer_gate.py` 各自解析同一句话是**故意的**：任一侧改了措辞两处都得改。
    """
    for line in _active_task_body(owner):
        if f"gate issue key `{_CRITERION_KEY}`" not in line:
            continue
        count = re.search(r"(\d+) 条 resolver 行", line)
        listed = re.search(r"resolver 行（([^）]+)）", line)
        if not (count and listed):
            continue
        return int(count.group(1)), set(re.findall(r"`([a-z_]+::[a-z_]+)`", listed.group(1)))
    raise AssertionError(
        f"任务 {owner}（当前归属）正文里找不到 gate issue key `{_CRITERION_KEY}` 的待清行名单"
    )


def _module_leaf_and_function(writer_id: str) -> str:
    """`app.routers.wp_onlyoffice_router::f` → `wp_onlyoffice_router::f`（与 doc 的写法同形）。"""
    module, function = writer_id.split("::", 1)
    return f"{module.rsplit('.', 1)[-1]}::{function}"


def _task_bodies() -> dict[str, list[str]]:
    """tasks.md → {任务号: 正文行}。行首锚定，不用字符窗口。"""
    bodies: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in _tasks_md_text().split("\n"):
        head = _TASK_HEAD_RE.match(line)
        if head:
            current = bodies.setdefault(head.group(1), [])
            current.append(line)
            continue
        if line.startswith("#") or line.startswith("- "):
            current = None
            continue
        if current is not None:
            current.append(line)
    assert bodies, "tasks.md 一个任务都没解析出来 ⇒ 本文件的 doc 派生判据会全部空跑"
    return bodies


def _criterion_owner_task() -> str:
    """当前持有这条 criterion 的任务号 —— 从 tasks.md 的显式接手语现场解析。

    🔴 不硬写 `"71"`：归属已经移交过两次（20 → 30 → 71），下一次移交时硬写的常量会和
    文档静默分叉。判别只认 `自 Task M 移交至本门`（接手），因为「好几个任务都提到了
    `multi_resolver`」本身分不出谁在守它 —— 那正是第一跳漂移的形态。
    """
    owners = [
        task
        for task, body in _task_bodies().items()
        for line in body
        if f"gate issue key `{_CRITERION_KEY}`" in line and _ASSUME_RE.search(line)
    ]
    assert len(owners) == 1, (
        f"tasks.md 里接手 `{_CRITERION_KEY}` 的任务不是恰一个：{owners}（0 = 无人守，"
        ">1 = 两个门都自称归属，两种都让「谁负责清零」不可判）"
    )
    return owners[0]


def _owner_named_rows() -> tuple[int, set[str]]:
    """Wave 6 冻结快照里归属任务正文点名的「N 条 resolver 行」→ ``(N, {函数名})``。

    🔴 只用于核对**冻结历史**的内部一致性（见 `test_the_frozen_handoff_lists_rows_only_at_its_owner`）：
    那份名单是 Wave 6 当时的 4 行（含此后已收敛的 `get_whole_excel_grid`），不再与今天的门比。

    与 `test_task20_writer_gate.py::_task71_multi_resolver_rows_from_tasks_md` 同一锚点。
    两个文件各自解析同一句话是**故意的**：任一侧改了措辞，两处都得同时改，
    「还剩几行要清」不会只活在散文里。

    额外守一件事：**放手方不得同时留着名单**。移交若被写成「复制」，两个任务的正文会同时
    点名这 4 行，于是「归属」在文档里有两个答案，而两处都能各自解析成功、谁都不红。
    """
    owner = _criterion_owner_task()
    bodies = _task_bodies()
    for other, body in bodies.items():
        if other == owner:
            continue
        for line in body:
            if f"gate issue key `{_CRITERION_KEY}`" in line:
                assert "条 resolver 行（" not in line, (
                    f"Task {other} 已放手 `{_CRITERION_KEY}`，却仍在正文里列着待清行名单 —— "
                    f"移交被写成了复制：{line[:160]}"
                )
    for line in bodies[owner]:
        if f"gate issue key `{_CRITERION_KEY}`" not in line:
            continue
        count = re.search(r"(\d+) 条 resolver 行", line)
        listed = re.search(r"resolver 行（([^）]+)）", line)
        if not (count and listed):
            continue
        return int(count.group(1)), set(re.findall(r"`([a-z_]+)`", listed.group(1)))
    raise AssertionError(
        f"Task {owner}（当前归属）正文里找不到 gate issue key `{_CRITERION_KEY}` 的待清行名单"
    )


def _dependency_graph() -> dict[str, Any]:
    """tasks.md `## Task Dependency Graph` 里的 waves/dependencies/gates JSON。

    行首锚定 + 结构断言，不用字符窗口（本 spec 三个文档都在被并发会话改）。
    """
    text = _tasks_md_text()
    block = re.search(
        r"^## Task Dependency Graph$\n\n^```json$\n(.*?)^```$", text, re.M | re.S
    )
    assert block, "tasks.md 里找不到 `## Task Dependency Graph` 的 json 块"
    graph = json.loads(block.group(1))
    for key in ("waves", "dependencies", "gates"):
        assert graph.get(key), f"依赖图缺 `{key}`"
    return graph
