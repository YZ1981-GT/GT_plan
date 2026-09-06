# -*- coding: utf-8 -*-
"""Task 101 上游就绪门 —— 本 spec 的 Wave 1 起各任务的开工前提。

spec: excel-workbook-wide-row-change-propagation / Wave 0 Task 101
Requirements: 7.5, 7.6
Properties: **P27**（A1 改写入口唯一）

═══ 这个门在防什么 ═══

本 spec 与 `excel-structural-row-insertion-and-shift-aware-verification`（下称**上游**）
**共改三个生产文件**：

| 文件 | 上游 | 本 spec |
|---|---|---|
| `excel_row_shift.py` | N1 新建位移纯函数 | M1 给 `_rewrite_formula_refs` 加 `propagate_sheets` |
| `excel_materialize.py` | Task 16 改 `plan_managed_writes`（接位移计划） | Task 21 改它（接工作簿级计划） |
| `excel_extract.py` | Task 9 / 10 加 `row_shift` 归一化 | Task 19 改为按**声明传播量**归一化 |

三处都是「后者建立在前者之上」。并行改会互相回退 —— 这在本仓库是**已发生过的事故形态**，
不是理论风险。

═══ 判据形态：为什么不是「断言上游已完成」 ═══

上游没做完时让 CI 变红是错的 —— 那会把「顺序约束」变成「上游的债记在下游账上」。
本文件的四条判据分工：

1. **解析器本身正确** —— `test_upstream_wave4_checkboxes_are_parseable` +
   `test_whole_upstream_file_parses_to_expected_shape`（形态断言：**27** 条 = **22** 顶层
   + **5** 个 `*` 子任务、零重复 id）。与上游今天做到哪一步无关。
2. **门的行为** —— `test_gate_behaviour_on_synthetic_states`：喂 `[ ]` 必抛、喂 `[x]` 必不抛，
   `~` / `-` 与未完成的 `*` 子任务同样拦。这是唯一能证明门真的会拦的判据，且不依赖上游当前状态。
3. **fail-closed 兜底** —— 同 id 重复 / 任务编号消失时按未就绪处理并要求人工消歧。
4. 🔴 **反向判据** —— `test_wave2_artifacts_absent_while_gate_closed`：门关着的时候，
   本 spec 的**门后产物**（`excel_workbook_row_change` 模块 / `propagate_sheets` 参数）
   **必须还不存在**。有人无视门开工了，这条会红。这才是「顺序被遵守」的实证。
5. **Property 27 基线** —— `test_single_a1_rewrite_entrypoint`：`_A1_PIECE_RE`（本模块唯一的
   A1 坐标改写原语）的使用点在 AST 上只有 `_rewrite_formula_refs` 内的嵌套函数 `_piece`。
   上游收口后本条仍须绿，否则说明有人另造了第二个 A1 改写入口。

⚠ 门的边界是 **Wave 1 起**，不是 Wave 2 起（AC 7.6 于 2026-09-04 修正）：原文与 7.5 自相矛盾
—— 7.5 明列 `excel_row_shift.py` 为共改文件，而原 Wave 1 的 Task 6 正要改它的
`_rewrite_formula_refs`。唯一排在门**之前**的是零回归基线冻结（现 Task 6：只读、时间敏感，
见 AC 7.7 —— 「本 spec 前」的行为一旦被上游改动覆盖就永久无从取证）。

═══ 判据纪律 ═══

* 复选框判据落在**现读磁盘**，不是人工记忆 —— 上游 tasks.md 在并发会话中被实时编辑
  （实测本文件建立时其 mtime 距当时仅 2 分 39 秒）。
* AST 判据用 `ast` 模块，天然不看 docstring —— 规则 4 要求「判断某符号是否真被用到前
  必须先剥 docstring」，用 AST 是最省事且不可能剥漏的做法。
* 「字符存在」不算判据：第 3 条查的是 `_rewrite_formula_refs` 的**签名形参**（`ast.arguments`），
  不是源码里有没有 `propagate_sheets` 这串字。
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

#: 上游 spec 的 tasks.md —— 唯一真源，现读不缓存。
UPSTREAM_TASKS: Path = (
    _REPO
    / ".kiro"
    / "specs"
    / "excel-structural-row-insertion-and-shift-aware-verification"
    / "tasks.md"
)

#: 上游 Wave 4（计划接线）的三条任务编号。用**字符串 id** 而不是 int —— 见下方正则说明。
REQUIRED_UPSTREAM_TASKS: tuple[str, ...] = ("16", "17", "18")

#: 行首锚定的复选框正则。三处都是实测调出来的，改任一处都会让判据失真：
#:
#: 1. `^` + 调用侧 `.match` —— 行首锚定。两者**互为冗余**（`re.match` 自身锚定位置 0，
#:    `^` 在无 MULTILINE 时同样只匹配串首），所以单独去掉任一个都不改变行为；
#:    变异检验必须**同时**去掉两者才敏感。
#: 2. `\]\*?` —— 上游把可选子任务写成 `- [ ]* 2.1 …`（`]` 后紧跟 `*`）。漏掉 `\*?` 会
#:    少读 5 条（分工书 §10.3：A 在 M0 对齐时实测 P 少算 15 条、S 少算 5 条）。
#: 3. `(\d+(?:\.\d+)*)` 而不是 `(\d+)` —— 🔴 只捕前导整数会把 `- [ ]* 2.1` 读成
#:    「任务 2」，于是 2 / 5 / 6 / 8 / 10 各凭空多出一次出现，本门的「重复即 fail-closed」
#:    会误触发并永久关闭。实测：捕完整 id 得 27 条（22 顶层 + 5 子任务）、零重复；
#:    只捕前导整数得 `{2: 2, 5: 2, 6: 2, 8: 2, 10: 2}` 五组假重复。
_CHECKBOX_RE = re.compile(r"^\s*-\s\[([ x~\-])\]\*?\s+(\d+(?:\.\d+)*)\.?(?=\s|$)")

_ROW_SHIFT_SOURCE: Path = (
    _BACKEND / "app" / "services" / "workpaper_sync" / "excel_row_shift.py"
)
_WORKBOOK_ROW_CHANGE_SOURCE: Path = (
    _BACKEND / "app" / "services" / "workpaper_sync" / "excel_workbook_row_change.py"
)


class UpstreamNotReadyError(RuntimeError):
    """上游 Wave 4 未完成 —— 本 spec 的 Wave 1 起各任务不得开工。"""

    error_code = "workbook_row_change_upstream_wave4_not_ready"


def read_checkbox_occurrences(text: str) -> dict[str, list[str]]:
    """`任务 id -> 该 id 出现过的复选框字符**列表**`（按出现顺序）。

    id 是**字符串**：顶层任务是 `"16"`，可选子任务是 `"2.1"`。用 int 会把两者混为一谈。

    🔴 刻意不做「同 id 保留最后一次」：那种收敛会**掩盖判据缺陷**。变异检验实测过 ——
    把扫描从 `.match` 改成 `.search`（去掉行首锚定）时，叙述句里的 `- [x] 16.` 会被
    误当成真复选框；但只要真任务行排在叙述句之后，「保留最后一次」就让结果不变，
    变异判 GREEN。改成收集全部出现次数 + 重复即 fail-closed，变异才敏感。
    """
    found: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = _CHECKBOX_RE.match(line)
        if match is None:
            continue
        found.setdefault(match.group(2), []).append(match.group(1))
    return found


def subtask_ids(found: dict[str, list[str]], parent: str) -> list[str]:
    """`parent` 的可选子任务 id（`16.1` 之类），按数值序。"""
    prefix = f"{parent}."
    return sorted(
        (i for i in found if i.startswith(prefix)),
        key=lambda s: [int(x) for x in s.split(".")],
    )


def upstream_wave4_states() -> dict[str, str]:
    """现读上游 tasks.md，取 Wave 4 三条任务**及其子任务**的复选框状态。

    子任务一并纳入：上游把 `*` 标记的属性测试写成子任务（`- [ ]* 2.1 …`），而「optional(*)
    任务也要做完」是本平台的既定要求 —— 接线任务勾了但它的属性测试还空着，不算就绪。
    """
    if not UPSTREAM_TASKS.is_file():
        raise UpstreamNotReadyError(
            f"上游 tasks.md 不存在: {UPSTREAM_TASKS} —— 无法判定就绪状态，按未就绪处理"
        )
    text = UPSTREAM_TASKS.read_text(encoding="utf-8")
    found = read_checkbox_occurrences(text)

    missing = [n for n in REQUIRED_UPSTREAM_TASKS if n not in found]
    if missing:
        raise UpstreamNotReadyError(
            f"上游 tasks.md 里找不到任务 {missing} 的复选框 —— 上游任务编号可能已改，"
            "本门的判据基础失效，必须人工复核后更新 REQUIRED_UPSTREAM_TASKS"
        )

    wanted: list[str] = []
    for parent in REQUIRED_UPSTREAM_TASKS:
        wanted.append(parent)
        wanted.extend(subtask_ids(found, parent))

    ambiguous = {n: found[n] for n in wanted if len(found[n]) != 1}
    if ambiguous:
        raise UpstreamNotReadyError(
            f"上游 tasks.md 里任务 {sorted(ambiguous)} 的复选框出现多次 {ambiguous} —— "
            "取哪一次都是猜，按未就绪处理并要求人工消歧"
        )
    return {n: found[n][0] for n in wanted}


def assert_upstream_wave4_ready(states: dict[str, str] | None = None) -> None:
    """上游 Wave 4 三条任务（含子任务）未全 `[x]` 即抛，异常携带完整未完成清单。"""
    states = upstream_wave4_states() if states is None else states
    pending = {n: s for n, s in states.items() if s != "x"}
    if pending:
        detail = ", ".join(f"Task {n} = [{s}]" for n, s in sorted(pending.items()))
        raise UpstreamNotReadyError(
            "上游 spec `excel-structural-row-insertion-and-shift-aware-verification` "
            f"的 Wave 4 尚未完成（{detail}）—— 本 spec 的 Wave 1 起各任务共改 "
            "excel_row_shift.py / excel_materialize.py / excel_extract.py 三个生产文件，"
            "并行编辑会互相回退，因此拒绝开工（Requirements 7.5 / 7.6）"
        )


def upstream_gate_is_open() -> bool:
    """门是否已开 —— 供门后各判据做 skip 条件用。"""
    try:
        assert_upstream_wave4_ready()
    except UpstreamNotReadyError:
        return False
    return True


def _function_nodes(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _enclosing_top_level_function(
    tree: ast.Module, target: ast.AST
) -> str | None:
    """`target` 所在的**最外层**函数名（嵌套函数归属其外层）。"""
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if child is target:
                return node.name
    return None


def has_propagate_sheets_param(row_shift_text: str) -> bool:
    """`_rewrite_formula_refs` 的**签名形参**里是否已有 `propagate_sheets`（M1 的记号）。

    取 `ast.arguments` 而不是 grep 字符串 —— 注释 / docstring / 别处的同名变量都不算。
    """
    tree = ast.parse(row_shift_text)
    for node in _function_nodes(tree):
        if node.name != "_rewrite_formula_refs":
            continue
        params = [a.arg for a in (*node.args.args, *node.args.kwonlyargs)]
        if "propagate_sheets" in params:
            return True
    return False


def a1_rewrite_owners(row_shift_text: str) -> set[str]:
    """用到 `_A1_PIECE_RE` 的**顶层函数**名集合 —— 谁用它谁就在改写 A1 行号。

    `_A1_PIECE_RE` 是「A1 坐标 → 拆列/行 → 重建」的原语，因此「入口唯一」可以落成一条
    可复算的结构判据，而不是读代码的印象。
    """
    tree = ast.parse(row_shift_text)
    owners: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_A1_PIECE_RE":
            owner = _enclosing_top_level_function(tree, node)
            if owner is not None:
                owners.add(owner)
    return owners


# ═══════════════════════════════════════════════════════════════════════════
# 1. 解析器本身正确（带分母断言）
# ═══════════════════════════════════════════════════════════════════════════


def test_upstream_wave4_checkboxes_are_parseable() -> None:
    """三条顶层任务必须都取到，且取到的 id 只能是它们本身或它们的子任务。

    分母断言：`>= 3` 且三个顶层 id 全在。缺任一个说明上游改了任务编号，本门的判据基础
    失效 —— 那是必须人工复核的信号，不能静默按「未就绪」放过（静默放过会让门在上游
    重构后永久关闭）。
    """
    states = upstream_wave4_states()
    assert set(REQUIRED_UPSTREAM_TASKS) <= set(states), (
        f"上游 Wave 4 三条顶层任务未全部取到，实得 {sorted(states)}"
    )
    assert len(states) >= 3, f"应至少取到 3 条状态，实得 {len(states)}: {states}"
    for task_id, state in states.items():
        parent = task_id.split(".")[0]
        assert parent in REQUIRED_UPSTREAM_TASKS, (
            f"取到了与 Wave 4 无关的 id {task_id!r}"
        )
        assert state in {" ", "x", "~", "-"}, f"Task {task_id} 复选框字符非法: {state!r}"


def test_whole_upstream_file_parses_to_expected_shape() -> None:
    """现读上游整份 tasks.md 的形态断言 —— 防正则退化成只认一种写法。

    实测（2026-09-04）：**27** 条 = **22** 顶层 + **5** 个 `*` 子任务（`2.1` / `5.1` /
    `6.1` / `8.1` / `10.1`），零重复 id。

    这条是分工书 §10.3 那条判据缺陷的回归判据：漏 `\\*?` 会掉到 22 条；把 `2.1` 截成 `2`
    会冒出 5 组假重复。两种退化都会被本条抓住。
    """
    found = read_checkbox_occurrences(UPSTREAM_TASKS.read_text(encoding="utf-8"))
    top = sorted(i for i in found if "." not in i)
    sub = sorted(i for i in found if "." in i)
    duplicated = {i: s for i, s in found.items() if len(s) != 1}

    assert not duplicated, f"上游 tasks.md 出现重复 id {duplicated} —— 正则可能把子任务号截断了"
    assert len(sub) >= 1, (
        "一条 `*` 子任务都没解析到 —— `\\]\\*?` 可能被去掉了（分工书 §10.3）"
    )
    assert len(top) + len(sub) == len(found)
    assert len(found) >= 22, f"上游任务总条数 {len(found)} 明显偏少，正则可能退化"


def test_checkbox_scan_is_line_anchored() -> None:
    """扫描必须行首锚定 —— 否则正文里引用 `- [x] 16.` 的叙述句会被当成真复选框。

    🔴 变异检验的教训写在用例形态里：叙述句必须排在**真任务行之后**，而且判据要看
    「出现次数」而不只看「最终取值」。早先的用例把叙述句放在前面又只比最终取值，
    于是 `.match` → `.search` 这个变异判 GREEN（承重点被第二道语义掩盖）。
    """
    text = (
        "- [ ] 16. 真任务\n"
        "  - 说明：上游 - [x] 16. 完成后本 spec 才能开工\n"
    )
    occurrences = read_checkbox_occurrences(text)
    assert occurrences == {"16": [" "]}, (
        "行首锚定失效：叙述句里的 `- [x] 16.` 被当成了真复选框 —— "
        f"实得 {occurrences}"
    )


def test_star_marked_subtasks_are_read_and_not_collapsed() -> None:
    """`- [ ]* N.M` 形态必须读到，且 **不得**被截成顶层任务 N（分工书 §10.3）。"""
    text = (
        "- [x] 16. 顶层\n"
        "- [ ]* 16.1 属性测试\n"
        "- [x]* 16.2 另一条属性测试\n"
    )
    assert read_checkbox_occurrences(text) == {
        "16": ["x"],
        "16.1": [" "],
        "16.2": ["x"],
    }


def test_subtask_pending_keeps_gate_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """顶层三条全 `[x]` 但 `*` 子任务还空着时，门必须仍然关闭。

    依据本平台既定要求「optional(*) 任务也要做完」—— 接线勾了而它的属性测试空着，
    等于共用文件已被改过但没有判据护着，那是最危险的时点。
    """
    fake = tmp_path / "tasks.md"
    fake.write_text(
        "- [x] 16. a\n- [ ]* 16.1 属性测试\n- [x] 17. b\n- [x] 18. c\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "UPSTREAM_TASKS", fake, raising=True)
    assert upstream_gate_is_open() is False
    with pytest.raises(UpstreamNotReadyError) as excinfo:
        assert_upstream_wave4_ready()
    assert "Task 16.1 = [ ]" in str(excinfo.value)

    fake.write_text(
        "- [x] 16. a\n- [x]* 16.1 属性测试\n- [x] 17. b\n- [x] 18. c\n",
        encoding="utf-8",
    )
    assert upstream_gate_is_open() is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. 门的行为（不依赖上游今天做到哪一步）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "states, should_raise",
    [
        ({"16": "x", "17": "x", "18": "x"}, False),
        ({"16": " ", "17": "x", "18": "x"}, True),
        ({"16": "x", "17": "-", "18": "x"}, True),
        ({"16": "x", "17": "x", "18": "~"}, True),
        ({"16": " ", "17": " ", "18": " "}, True),
        ({"16": "x", "16.1": " ", "17": "x", "18": "x"}, True),
    ],
)
def test_gate_behaviour_on_synthetic_states(
    states: dict[str, str], should_raise: bool
) -> None:
    """`[x]` 之外的任何状态（含 `~` 进行中与 `-` 阻塞）都必须拦。"""
    if should_raise:
        with pytest.raises(UpstreamNotReadyError) as excinfo:
            assert_upstream_wave4_ready(states)
        message = str(excinfo.value)
        for number, state in states.items():
            if state != "x":
                assert f"Task {number} = [{state}]" in message, (
                    "异常必须携带完整未完成清单（Requirement 7.6），"
                    f"缺 Task {number}: {message}"
                )
    else:
        assert_upstream_wave4_ready(states)


def test_gate_error_code_is_stable() -> None:
    """error_code 是稳定标识，调用方按它分支。"""
    assert UpstreamNotReadyError.error_code == (
        "workbook_row_change_upstream_wave4_not_ready"
    )


def test_duplicate_checkbox_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """同一编号出现多次时按未就绪处理 —— 取哪一次都是猜。

    这条不只是防上游写重复，更是 `.match` 行首锚定的**第二层保护**：一旦锚定失效，
    叙述句会让编号重复出现，这里立刻 fail-closed，不会把错的状态当就绪。
    """
    fake = tmp_path / "tasks.md"
    fake.write_text(
        "- [x] 16. 一处\n- [x] 16. 又一处\n- [x] 17. a\n- [x] 18. b\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys.modules[__name__], "UPSTREAM_TASKS", fake, raising=True
    )
    with pytest.raises(UpstreamNotReadyError) as excinfo:
        upstream_wave4_states()
    assert "出现多次" in str(excinfo.value)
    assert upstream_gate_is_open() is False

    # 🔴 `16` 与 `16.1` **不是**同一个 id —— 子任务不得被算成父任务的重复出现。
    # 这正是「只捕前导整数」那种写法会造成的假重复（实测会冒出 5 组）。
    fake.write_text(
        "- [x] 16. a\n- [x]* 16.1 属性测试\n- [x] 17. b\n- [x] 18. c\n",
        encoding="utf-8",
    )
    assert upstream_gate_is_open() is True


def test_missing_task_number_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """上游改了任务编号时必须 fail-closed 并要求人工复核，不得静默按未就绪滑过。"""
    fake = tmp_path / "tasks.md"
    fake.write_text("- [x] 16. a\n- [x] 17. b\n", encoding="utf-8")
    monkeypatch.setattr(
        sys.modules[__name__], "UPSTREAM_TASKS", fake, raising=True
    )
    with pytest.raises(UpstreamNotReadyError) as excinfo:
        upstream_wave4_states()
    assert "'18'" in str(excinfo.value)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 反向判据：门关着时门后产物必须还不存在
# ═══════════════════════════════════════════════════════════════════════════


def test_wave2_artifacts_absent_while_gate_closed() -> None:
    """🔴 门关着却已出现门后产物 = 顺序约束被无视，必须红。

    两个产物各查一处**结构**而非字符：
      * `excel_workbook_row_change.py`（N1）是否已落盘；
      * `_rewrite_formula_refs` 的**签名形参**里是否已有 `propagate_sheets`（M1）——
        查 `ast.arguments` 而不是 grep 字符串，避免注释/docstring 里提到就误判。
    """
    if upstream_gate_is_open():
        pytest.skip("上游 Wave 4 已就绪，本反向判据不再适用（改由门后各任务自身判据接管）")

    violations: list[str] = []
    if _WORKBOOK_ROW_CHANGE_SOURCE.is_file():
        violations.append(
            f"{_WORKBOOK_ROW_CHANGE_SOURCE.relative_to(_REPO)} 已存在"
            "（N1 属 Wave 1 Task 5，门未开不得落盘 —— `WorkbookRowChangePlan` 以上游的"
            " `RowShiftPlan` 为其受管 sheet 分量，形态未定型就落盘要返工）"
        )
    if has_propagate_sheets_param(_ROW_SHIFT_SOURCE.read_text(encoding="utf-8")):
        violations.append(
            "`_rewrite_formula_refs` 的签名里已出现 `propagate_sheets`"
            "（M1 属 Wave 1 Task 28，门未开不得改）"
        )

    assert not violations, (
        "上游 Wave 4 未完成，但本 spec 的门后产物已出现 —— 并行改共用文件会互相回退"
        "（Requirement 7.5）：\n  " + "\n  ".join(violations)
    )


def test_propagate_sheets_detector_fires_on_synthetic_violation() -> None:
    """🔴 反向自检：喂一份**已经**加了 `propagate_sheets` 的源，检测器必须命中。

    没有这条，上面那条判据在「检测器坏了」与「产物确实不存在」之间无法区分 ——
    那正是假绿第②源（守卫只查字符串存在 / 或压根没在查）。
    """
    violating = (
        "def _rewrite_formula_refs(text, *, remap, propagate_sheets=frozenset()):\n"
        "    return text, 0\n"
    )
    assert has_propagate_sheets_param(violating) is True

    # 同名形参出现在**别的**函数上不算 —— 判据必须认函数身份
    other_function = (
        "def _shift_sqref(value, *, propagate_sheets=frozenset()):\n"
        "    return value\n"
        "def _rewrite_formula_refs(text, *, remap):\n"
        "    return text, 0\n"
    )
    assert has_propagate_sheets_param(other_function) is False

    # docstring / 注释里提到不算 —— 规则 4：字符存在不是判据
    only_mentioned = (
        "def _rewrite_formula_refs(text, *, remap):\n"
        '    """将来会加 propagate_sheets 参数。"""\n'
        "    # propagate_sheets 尚未实现\n"
        "    return text, 0\n"
    )
    assert has_propagate_sheets_param(only_mentioned) is False


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 27 基线：A1 改写入口唯一
# ═══════════════════════════════════════════════════════════════════════════


def test_single_a1_rewrite_entrypoint() -> None:
    """`_A1_PIECE_RE` 的使用点在 AST 上只归属 `_rewrite_formula_refs` 一个顶层函数。

    `_A1_PIECE_RE` 是本模块唯一的「A1 坐标 → 拆列/行 → 重建」原语；谁用它谁就在改写
    A1 行号。因此「入口唯一」这件事可以落成一条可复算的结构判据，而不是读代码的印象。

    分母断言：使用点 > 0。为 0 说明原语改名了，判据在空集上恒真。
    """
    owners = a1_rewrite_owners(_ROW_SHIFT_SOURCE.read_text(encoding="utf-8"))
    assert owners, (
        "`_A1_PIECE_RE` 在任何函数体内都没被用到 —— 原语可能已改名，"
        "本判据会在空集上恒真，必须先修判据"
    )
    assert owners == {"_rewrite_formula_refs"}, (
        "A1 行号改写入口不唯一（Property 27 / Requirements 7.2, 7.3）：`_A1_PIECE_RE` "
        f"被这些顶层函数用到 {sorted(owners)}，应只有 `_rewrite_formula_refs`"
    )


def test_a1_owner_detector_fires_on_second_entrypoint() -> None:
    """🔴 反向自检：喂一份**有第二个** A1 改写入口的源，检测器必须报出两个 owner。

    这是 Property 27 唯一能被证伪的形态 —— 真实源码里今天只有一个入口，光跑真实源码
    永远绿，分不清「入口确实唯一」与「检测器根本没在看」。
    """
    single = (
        "_A1_PIECE_RE = 1\n"
        "def _rewrite_formula_refs(t):\n"
        "    def _piece(raw):\n"
        "        return _A1_PIECE_RE.fullmatch(raw)\n"
        "    return _piece(t)\n"
    )
    assert a1_rewrite_owners(single) == {"_rewrite_formula_refs"}

    smuggled = single + (
        "def _shift_rows_quickly(t):\n"
        "    return _A1_PIECE_RE.fullmatch(t)\n"
    )
    assert a1_rewrite_owners(smuggled) == {
        "_rewrite_formula_refs",
        "_shift_rows_quickly",
    }

    # 模块级使用（不在任何函数内）不归属任何 owner，不得被算成第二个入口
    module_level = single + "_COMPILED = _A1_PIECE_RE\n"
    assert a1_rewrite_owners(module_level) == {"_rewrite_formula_refs"}
