"""test_task20_writer_gate —— 判据层（三件套 / 里程碑定义的定位与解析 helper、正则常量）。

从 `backend/tests/workpaper_sync/test_task20_writer_gate.py` 拆出：2026-11-04 把 doc 派生判据
改绑 Wave 6 冻结快照、当前基线与待清名单改读里程碑注册表 / active 计划之后，原文件超过行数门
（白名单基线 1569 + 5%）。打磨应让文件变小，所以拆出解析层而不是抬基线。

刻意与用例文件**同目录**：`Path(__file__).parents[3]` 的路径推算移到子目录会整体错一层。
搬过来的定义逐行等于原文；用例层的 import 清单由拆分脚本按实际引用算出。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]


#: 当前归属方正文点名的、必须清零的那几条 resolver 行从 active tasks.md 现场解析（见
#: `_active_owner_rows_from_tasks_md`），不在这里抄；解析结果与门实测报出的行逐个比对。
_SPEC_NAME = "workpaper-html-onlyoffice-bidirectional-writeback-closure"


#: Wave 6 形态三件套在冻结快照里的内容标记（与 0.6 重绑旧消费方同一实现）。
_FROZEN_MARKERS: dict[str, tuple[str, ...]] = {
    "tasks.md": (r"^- \[[ x~\-]\] 20\.\s", r"当期红基线（冻结）", r"14 条准则的归属"),
    "requirements.md": (r"所有内容 writer 使用同一 revision 协议",),
    "design.md": (r"^### Property 61: 所有 writer 进入唯一 revision 域",),
}


def _frozen_spec_dir() -> Path:
    """Wave 6 三件套所在目录。

    🔴 2026-11-04：本 spec 2026-11-01 被重写成「7 条扁平 AC + 两级任务号」，Task 20 正文、
    14 条准则的归属行、20 → 30 → 71 的接手语、universal scope 的四句原话都只在冻结快照里
    ⇒ 本文件的 doc 派生判据原先读 active，报「一个任务都没解析出来」。这些判据核对的是
    **历史记录与门的形状**，绑冻结快照；**当前**的发布基线与待清名单改读里程碑注册表 /
    active 计划（见 §5 / §6 的说明）。
    """
    backend = str(_REPO / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.core.spec_docs import resolve_spec_dir

    return resolve_spec_dir(
        _SPEC_NAME, require_files=tuple(_FROZEN_MARKERS), require_matches=_FROZEN_MARKERS
    )


_FROZEN_SPEC_DIR = _frozen_spec_dir()


_TASKS_MD = _FROZEN_SPEC_DIR / "tasks.md"


_REQUIREMENTS_MD = _FROZEN_SPEC_DIR / "requirements.md"


_DESIGN_MD = _FROZEN_SPEC_DIR / "design.md"


#: active（重写后）的 tasks.md —— 只读当前归属方点名的待清行。
_ACTIVE_TASKS_MD = _REPO / ".kiro" / "specs" / _SPEC_NAME / "tasks.md"


_MILESTONE_DEFINITIONS_PATH = (
    _REPO / "backend" / "data" / "workpaper_sync_program_milestone_definitions.json"
)


_MILESTONE_REGISTRY_PATH = _REPO / "backend" / "data" / "workpaper_sync_program_milestones.json"


_TASK_HEAD_RE = re.compile(r"^- \[[ x~\-]\] (\d+)\.\s")


#: `**`多 resolver writer=0`（gate issue key `multi_resolver`…` —— 门内 key 的文档侧字面量。
_GATE_ISSUE_KEY_RE = re.compile(r"gate issue key `([a-z_]+)`")


#: 「已移交 Task N」= 本任务**放手**；「自 Task M 移交至本门」= 本任务**接手**。
#:
#: 🔴 两条措辞都只描述**本任务自己的**交接动作。追述别人那一跳时 tasks.md 用的是
#: 「已**再**移交 Task 71」/「移交链 Task 20 → Task 30 → Task 71」，两者都不匹配这两个
#: 正则 —— 否则一句历史注解会改写归属推导。移交链因此由**放手/接手事件的文档顺序**
#: 拼出来（见 `_gate_issue_key_homing`），而不是从散文里读一条箭头串。
_RELINQUISH_RE = re.compile(r"已移交 Task (\d+)")


_ASSUME_RE = re.compile(r"自 Task (\d+) 移交至本门")


#: Task 20「当期红基线（冻结）」那行里的 `标签=计数` 串（`生产写路径未裁决=236、…=0、…`）。
#:
#: 🔴 计数从 `=0` 放宽到 `=(\d+)` 是本轮整改的另一半：旧形态只能表达「已归零」，于是 Task 20
#: 的正文与实测（236 / 261）自相矛盾，而正文第 4 条又写着「本门未过」。现在正文冻结的是**实测
#: 红基线**，`test_the_frozen_red_baseline_is_derived_from_the_live_gate` 把它和门现算的计数
#: 逐条比对 —— 数字不再是手抄常量（否则源码一变就与文档静默分叉，平台假绿第③源）。
_CRITERION_LABEL_RE = re.compile(r"([^、；;]+)=(\d+)")


#: 基线行末尾的 `合计 N 条 blocking facts` —— 与 14 条之和交叉验证，防「逐条对了总数写错」。
_BASELINE_TOTAL_RE = re.compile(r"合计 (\d+) 条 blocking facts")


#: 归属行的分段：`归属 Task 74：`a`、`b`；`。分段边界用 `；`/`。`，段内只有反引号包住的 key。
_HOMING_SEGMENT_RE = re.compile(r"归属 Task (\d+)：([^；。]+)")


#: 反引号里的门内 issue key 字面量（与 `_GATE_ISSUE_KEY_RE` 不同：本条**不要求**
#: `gate issue key` 前缀，只在归属行的分段内使用，故不会把散文里的其他反引号词收进来）。
_BACKTICKED_KEY_RE = re.compile(r"`([a-z_]+)`")


def _task_bodies() -> dict[str, list[str]]:
    """tasks.md → {任务号: 该任务正文的行列表}。行首锚定，不用字符窗口。"""
    bodies: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in _TASKS_MD.read_bytes().decode("utf-8").split("\n"):
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
    assert bodies, "tasks.md 一个任务都没解析出来 —— 本文件的 doc 派生判据会全部空跑"
    return bodies


def _frozen_red_baseline_from_tasks_md() -> tuple[dict[str, int], int]:
    """Task 20 冻结的当期红基线 → ``({准则标签: 计数}, 合计)``。

    锚在「当期红基线（冻结）」上，行首锚定 + 现场解析，不抄常量。返回的计数由
    `test_the_frozen_red_baseline_is_derived_from_the_live_gate` 与 `evaluate_gate()` 的实测
    结果逐条比对，所以这里解析出的每一个数字都必须能被门反驳。
    """
    for line in _task_bodies()["20"]:
        if "当期红基线（冻结）" not in line:
            continue
        baseline = {
            m.group(1).strip(): int(m.group(2)) for m in _CRITERION_LABEL_RE.finditer(line)
        }
        assert baseline, f"基线行解析不出任何「标签=计数」：{line[:160]}"
        total = _BASELINE_TOTAL_RE.search(line)
        assert total, f"基线行没有「合计 N 条 blocking facts」：{line[:160]}"
        return baseline, int(total.group(1))
    raise AssertionError("Task 20 正文里找不到「当期红基线（冻结）」那一行")


def _task20_criteria_labels_from_tasks_md() -> set[str]:
    """Task 20 正文点名的准则标签集 —— 现在等于冻结基线那一行点名的 14 条。"""
    return set(_frozen_red_baseline_from_tasks_md()[0])


def _gate_criteria_homing_from_tasks_md() -> dict[str, str]:
    """Task 20「14 条准则的归属」行 → ``{门内 issue key: 归属任务号}``。

    与 `_gate_issue_key_homing()` 是**两套独立派生**，故意的：后者只认两句显式交接语
    （`已移交 Task N` / `自 Task M 移交至本门`），描述的是**交接事件**；本函数读的是一张
    全量归属表，描述的是**当前状态**。两者在同一个 key 上不一致即红（见
    `test_the_criteria_homing_agrees_with_tasks_md`）—— 一份「谁负责清零」的答案有两个来源
    且都能各自解析成功、谁都不红，正是第一跳漂移的形态。
    """
    for line in _task_bodies()["20"]:
        if "14 条准则的归属" not in line:
            continue
        homing: dict[str, str] = {}
        for task, segment in _HOMING_SEGMENT_RE.findall(line):
            keys = _BACKTICKED_KEY_RE.findall(segment)
            assert keys, f"「归属 Task {task}」这一段里没有任何 issue key：{segment[:120]}"
            for key in keys:
                assert key not in homing, (
                    f"`{key}` 在归属行里出现两次（Task {homing[key]} 与 Task {task}）—— "
                    "「谁负责清零」不可有两个答案"
                )
                homing[key] = task
        assert homing, f"归属行解析不出任何 `归属 Task N：` 分段：{line[:160]}"
        return homing
    raise AssertionError("Task 20 正文里找不到「14 条准则的归属」那一行")


def _gate_issue_key_homing() -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    """从 tasks.md 派生每个门内 issue key 的**归属**与**整条移交链**。

    返回 ``(homed, relinquished, assumed)``：``homed[key]`` 是该 key 当前归属的任务号；
    ``relinquished[key]`` 是按文档顺序放手过它的任务号**列表**；``assumed[key]`` 同理是
    接手过它的任务号列表。

    判别只看两句显式交接语（`已移交 Task N` / `自 Task M 移交至本门`），因为「Task 20、
    Task 30、Task 71 都提到了 `multi_resolver`」本身分不出谁在守它 —— 这正是第一跳漂移的
    形态。

    🔴 三个返回值都是**列表而不是单值**：这条 criterion 已经移交两次（20 → 30 → 71），
    单值 dict 会被第二跳静默覆盖成 `relinquished={key: "30"}`，第一跳从判据里消失，
    于是「移交链」这件事在守卫里再也不可核对 —— 而它正是下一轮复盘最先要问的东西。
    """
    homed: dict[str, str] = {}
    relinquished: dict[str, list[str]] = {}
    assumed: dict[str, list[str]] = {}
    for task, body in _task_bodies().items():
        for line in body:
            keys = _GATE_ISSUE_KEY_RE.findall(line)
            if not keys:
                continue
            hand_off = _RELINQUISH_RE.search(line)
            take_over = _ASSUME_RE.search(line)
            for key in keys:
                if hand_off:
                    relinquished.setdefault(key, []).append(task)
                    homed[key] = hand_off.group(1)
                elif take_over:
                    assumed.setdefault(key, []).append(task)
                    homed.setdefault(key, task)
                else:
                    homed.setdefault(key, task)
    return homed, relinquished, assumed


def _criterion_owner_task() -> str:
    """当前持有 `multi_resolver` 的任务号 —— 从 tasks.md 的显式接手语现场解析。

    🔴 不硬写任务号：归属已移交两次，硬写的常量会在第三次移交时与文档静默分叉。
    """
    homed, _, assumed = _gate_issue_key_homing()
    owners = assumed.get("multi_resolver") or []
    assert len(owners) == 1, (
        f"tasks.md 里接手 `multi_resolver` 的任务不是恰一个：{owners}"
        "（0 = 无人守，>1 = 两个门都自称归属）"
    )
    assert homed.get("multi_resolver") == owners[0], (
        f"放手侧指向 Task {homed.get('multi_resolver')}，接手侧却是 Task {owners[0]}"
    )
    return owners[0]


def _active_owner_task() -> str:
    """**当前**计划里清零 `multi_resolver` 的任务：里程碑定义 `writer_gate_issue_zero` 的 producer。

    Wave 6 的归属链（20 → 30 → 71）由上面的冻结派生核对；重写后的两级任务号写不进那句
    接手语，producer 映射本来就是机器可读、经审核的单一来源。
    """
    definitions = json.loads(_MILESTONE_DEFINITIONS_PATH.read_text(encoding="utf-8"))
    owners = sorted(
        {
            task
            for milestone in definitions["milestones"]
            if any(
                predicate.get("type") == "writer_gate_issue_zero"
                and predicate.get("issue") == "multi_resolver"
                for predicate in milestone.get("predicates") or ()
            )
            for producer in milestone.get("producers") or ()
            if producer.get("spec") == _SPEC_NAME
            for task in producer.get("tasks") or ()
        }
    )
    assert len(owners) == 1, f"清零 `multi_resolver` 的 producer 不是恰一个：{owners}"
    return owners[0]


def _active_owner_rows_from_tasks_md(owner: str) -> tuple[int, set[str]]:
    """active tasks.md 里该任务点名的「N 条 resolver 行（`module::function`、…）」。

    锚在 `resolver 行（…）` 这个短语上而不是抄一份名单：名单一旦在文档里改了（迁走一行、
    换个函数名），这里解析出来的集合就跟着变，和门实测报出的行比对即可发现不一致。行身份带
    模块叶名：第 4 行在 `wp_generation_staging`，只比函数名会让「同名函数换了模块」看不见。
    """
    head_re = re.compile(r"^- \[[ xX~\-]\]\*? (\d+(?:\.\d+)*)\s")
    inside = False
    for line in _ACTIVE_TASKS_MD.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
        head = head_re.match(line)
        if head:
            if inside:
                break
            inside = head.group(1) == owner
            continue
        if not inside or "gate issue key `multi_resolver`" not in line:
            continue
        count = re.search(r"(\d+) 条 resolver 行", line)
        listed = re.search(r"resolver 行（([^）]+)）", line)
        if count and listed:
            return int(count.group(1)), set(re.findall(r"`([a-z_]+::[a-z_]+)`", listed.group(1)))
    raise AssertionError(
        f"任务 {owner}（当前归属）正文里找不到 gate issue key `multi_resolver` 的待清行名单"
    )
