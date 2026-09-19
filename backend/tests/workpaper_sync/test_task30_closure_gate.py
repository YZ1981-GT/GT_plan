# -*- coding: utf-8 -*-
"""Task 30 关门判据（离线半）：`multi_resolver` 归零、阻塞前提、以及登记债的复核。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 30
Requirements: 2.9, 5.6, 9.11, 9.12, 10.1, 10.2, 13.5
Properties: **P43 / P44 / P45 / P62**

═══ `multi_resolver` 的裁决归属已再次移交：Task 20 → Task 30 → Task 71 ═══

Task 30 在活体库上实测到该 criterion 在**自己这个位置**同样不可满足（供给只能来自
Task 36 的逐 entry `finalizeCandidate`，而 Task 36 依赖 Task 30 —— 与第一跳同形的第二次
成环），故 tasks.md 已把**裁决归属**移交 Task 71（`legacy_delete` gate 成员，且本就依赖
Task 30，方向不成环）。

判据**留在本文件**，形态照抄第一跳：`test_task20_writer_gate.py` §6 至今持有归属 Task 30
的那条 criterion。放手方保留可跑的守卫，而不是留一句承诺 —— Task 71 还没开工，此刻把判据
搬进一个 `test_task71_*.py` 只会让它无人维护，且「一条准则从所有分母里消失」与「它归零」
在报告里逐字相同。文件名记的是**作者**，不是归属；归属由 tasks.md 现场解析（见
`_criterion_owner_task()`），doc 与登记一旦不一致就红。

═══ 本文件与 `_pg.py` 的分工 ═══

* 本文件：**门本身**的判据 —— 4 条 resolver 行是否已清零、清不了零时阻塞前提是否被
  机器可读地登记、归属移交是否没有把 criterion 挂到反向的 wave 上、Task 29 移交过来的
  evidence schema 债是否还成立。全部只读源码/生成物。
* `test_task30_closure_gate_pg.py`：durable protocol / application / close exactly-one /
  recovery 生命周期的**独立集成验证**，真实 PostgreSQL。

═══ 为什么「独立门」不能只复用各任务自己的守卫 ═══

Task 21~29 的守卫各自证明「我这一层对」。关门要证的是**跨层组合**对：shell 与 application
是两个任务写的，`durable_at` 判 owner 与 quarantine 拒绝是第三个任务写的，close leader 仲裁
是第四个。所以本 spec 的关门判据一律**重算**而不是引用：`multi_resolver` 这一条用本文件
自己的 AST 走查与门的报告做双向比对，集成那一半在一个 scratch schema 里把生产服务对象串起来
真跑。

═══ 判据形态的三条硬约束（本 spec 反复付过代价）═══

1. **不许自证**：任何一条「X 等于 Y」都要求 X、Y 来自两条独立推导链。本文件的
   `multi_resolver` 判据因此**不读**矩阵里的 `resolver_identities`（那是从同一份清册生成的），
   而是自己对 `backend/app` 走一遍 AST。
2. **不许把当前缺陷冻成基线**：这里**没有** `assert count == 4`。判据是双条件式
   （「计数非零 ⇔ 阻塞前提已登记」），归零那天它会强制把登记删掉，而不是变红拦人。
3. **不许 fail-open**：生成物缺失/陈旧一律抛，不降级成「无数据」。
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_APP_ROOT = _BACKEND / "app"
_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
_GATE_PATH = _BACKEND / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
_MATRIX_PATH = _BACKEND / "data" / "workpaper_resolver_migration_matrix.json"
_INVENTORY_PATH = _BACKEND / "data" / "workpaper_writer_inventory.json"
_SPEC_DIR = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
_TASKS_MD = _SPEC_DIR / "tasks.md"
_MIGRATION = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)

#: 那一条 criterion 的门内 key。**不抄名单**（4 条行名与归属任务号都从 tasks.md 解析，
#: 与 `test_task20_writer_gate.py` 同源），只固定这一个 key。
_CRITERION_KEY = "multi_resolver"

#: 承接 `wp_onlyoffice_router` 那 4 行的矩阵分组（矩阵 POLICY 的单一真源里就是这个值）。
_OO_GROUP = "oo_room"

_TASK_HEAD_RE = re.compile(r"^- \[[ x~\-]\] (\d+)\.\s")
#: 「自 Task M 移交至本门」= 该任务**接手**这条 criterion，即当前裁决归属。
_ASSUME_RE = re.compile(r"自 Task (\d+) 移交至本门")
#: bulk adapter 迁移 lane 里的一个代表任务号（Wave 5）。归属任务的 wave 必须晚于它 ——
#: 这正是「相同措辞若被原样搬到 Task 71 就会让 Wave 5 依赖 Wave 7」那条成环的算术形式。
_BULK_ADAPTER_LANE_TASK = "46"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load_module("task30_writer_inventory_generator", _GENERATOR_PATH)


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return _load_module("task30_writer_revision_gate", _GATE_PATH)


@pytest.fixture(scope="module")
def inventory(gate: ModuleType) -> dict[str, Any]:
    """清册 —— 且**必须**是当前源码派生的那一份。

    直接读 JSON 会让「源码动了但没重生成」变成一份看起来干净的旧账。门自己带
    `assert_inventory_is_current`（三重比对），这里复用它：陈旧即抛。
    """
    stored = gate.load_inventory()
    gate.assert_inventory_is_current(stored)
    return stored


@pytest.fixture(scope="module")
def matrix() -> dict[str, Any]:
    return json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))


def _task_bodies() -> dict[str, list[str]]:
    """tasks.md → {任务号: 正文行}。行首锚定，不用字符窗口。"""
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
    """归属任务正文点名的「N 条 resolver 行」→ ``(N, {函数名})``。

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
    text = _TASKS_MD.read_bytes().decode("utf-8")
    block = re.search(
        r"^## Task Dependency Graph$\n\n^```json$\n(.*?)^```$", text, re.M | re.S
    )
    assert block, "tasks.md 里找不到 `## Task Dependency Graph` 的 json 块"
    graph = json.loads(block.group(1))
    for key in ("waves", "dependencies", "gates"):
        assert graph.get(key), f"依赖图缺 `{key}`"
    return graph


# ═══════════════════════════════════════════════════════════════════════════
# §1 `multi_resolver` —— 独立重算 × 门的报告，双向比对
# ═══════════════════════════════════════════════════════════════════════════


def _recompute_multi_resolver_rows(generator: ModuleType) -> dict[str, list[str]]:
    """本文件**自己**走一遍 `backend/app` 的 AST，找出「一个函数抵达 ≥2 个 resolver」的行。

    这是与清册生成器**独立的**第二条推导链：符号集合从生成器读（单一真源，不抄字面量），
    但「哪些函数命中」由本函数自己数。两条链对不上时，问题在生成器或在本函数，
    两种都必须被看见 —— 而只读生成物的判据是自证的。

    🔴 只数 `ast.Call` 的被调用名：import 行、类型注解、字符串里的同名标识符不算。
    否则「把调用删掉只留 import」会让计数不变（本 spec 已为同一形态付过一次代价）。
    """
    symbols: frozenset[str] = generator._RESOLVER_SYMBOLS
    assert len(symbols) >= 5, f"resolver 符号集退化成 {sorted(symbols)} ⇒ 重算会恒空"

    found: dict[str, list[str]] = {}
    scanned = 0
    for path in sorted(_APP_ROOT.rglob("*.py")):
        if not generator._is_production_source(path):
            continue
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        module = generator._module_path(path)
        for qualname, function in generator._iter_functions(tree):
            hits: set[str] = set()
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                leaf = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else None
                )
                if leaf in symbols:
                    hits.add(leaf)
            if len(hits) > 1:
                found[f"{module}::{qualname}"] = sorted(hits)
    assert scanned > 50, f"只扫到 {scanned} 个生产模块 ⇒ 重算分母塌了"
    return found


def test_recomputation_and_the_gate_agree_on_the_multi_resolver_rows(
    generator: ModuleType, gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 9.11**

    门报出的行集合 == 本文件独立重算出的行集合。

    只有一侧时的失效形态各不相同：只信门 ⇒ 生成器的发现谓词漂了看不见；只信重算 ⇒
    门可能已经不把这条准则计入 `has_debt`（key 还在、计数恒零，报告与「已清零」逐字相同）。
    """
    reported = set(gate.evaluate_gate(inventory)[_CRITERION_KEY])
    recomputed = _recompute_multi_resolver_rows(generator)
    assert reported == set(recomputed), (
        "门与独立重算不一致：\n"
        f"  仅门报出 = {sorted(reported - set(recomputed))}\n"
        f"  仅重算报出 = {sorted(set(recomputed) - reported)}"
    )
    # 反向自检：判据不是恒真。构造一个只抵达 1 个 resolver 的合成函数体，重算必须不收它。
    single = ast.parse("def f():\n    return resolve_wp_file(1)\n")
    hits = {
        node.func.id
        for node in ast.walk(single)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } & generator._RESOLVER_SYMBOLS
    assert len(hits) == 1, hits


def test_the_gate_still_counts_the_criterion_its_owner_verifies_zero_with(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 9.11, 13.5**

    这条 criterion 的**裁决归属**已两跳（Task 20 → Task 30 → Task 71）；门里的**计算**
    一行都不能删。

    两段都必要：`key in issues` 只证明键还在（把判定短路成 `if False` 时键仍在、计数恒零）；
    所以第二段真喂一条多 resolver 行进去，看门点名它。
    """
    issues = gate.evaluate_gate(inventory)
    assert _CRITERION_KEY in issues, (
        f"门不再评估 `{_CRITERION_KEY}` —— 一条准则从报告里消失与它归零逐字相同，"
        f"而 Task {_criterion_owner_task()}（当前归属）正是靠这个计数验零"
    )

    synthetic = json.loads(json.dumps(inventory))  # 深拷贝，不动 fixture
    probe_id = "app.routers.__task30_probe__::probe_two_resolvers"
    row = json.loads(json.dumps(synthetic["entries"][0]))
    row["writer_id"] = probe_id
    row["kind"] = "resolver"
    row["verdicts"] = dict(row["verdicts"])
    row["verdicts"][_CRITERION_KEY] = True
    row["resolver_identities"] = ["_resolve_wp_file", "find_template_file_any"]
    row["adjudication"] = {"status": "adjudicated", "domain": "export_storage_resolver"}
    synthetic["entries"].append(row)
    assert probe_id in gate.evaluate_gate(synthetic)[_CRITERION_KEY], (
        "喂进一条真的多 resolver 行后门没点名它 ⇒ 判定被短路，计数恒零"
    )


def test_the_criterion_is_either_cleared_or_its_blocker_is_registered(
    gate: ModuleType, inventory: dict[str, Any], matrix: dict[str, Any]
) -> None:
    """**Validates: Requirements 9.11, 9.12**

    双条件式：`multi_resolver` 计数非零 ⇔ 那些行在 Task 12 矩阵里仍是 `deferred` 且写明阻塞。

    🔴 这里刻意**不写** `assert count == 4`：把当前缺陷冻成基线之后，真清零那天守卫会
    反过来打红拦人（本 spec 的「守卫把错值当基线」形态）。写成双条件式则相反 ——
    清零那天它强制要求把 deferral 登记一起删掉。
    """
    reported = sorted(gate.evaluate_gate(inventory)[_CRITERION_KEY])
    rows = {r["writer_id"]: r for r in matrix["rows"]}
    oo_deferred = sorted(
        wid
        for wid, r in rows.items()
        if r.get("group") == _OO_GROUP and r.get("status") == "deferred"
    )

    if not reported:
        assert not oo_deferred, (
            "门已报 `multi_resolver=0`，但矩阵里这些行还挂着 deferral 登记 —— "
            f"清零后必须一并撤销登记: {oo_deferred}"
        )
        return

    owner = _criterion_owner_task()
    for writer_id in reported:
        row = rows.get(writer_id)
        assert row is not None, f"门报出的行 {writer_id} 不在 Task 12 矩阵里（分母漏登记）"
        assert row["status"] == "deferred", (
            f"{writer_id} 在矩阵里是 {row['status']}，但门仍把它计入 `{_CRITERION_KEY}` —— "
            "「已迁移」与「门仍报红」不能同时成立"
        )
        assert row.get("blocking_task") and row.get("reason"), (
            f"{writer_id} 的 deferral 没写 blocking_task/reason（等于悄悄留双真源）"
        )
        # 裁决归属是与 `blocking_task` **不同**的一件事，故矩阵里分列两个字段：前者是
        # 「什么不落地就迁不了」（真实供给阻塞），后者是「哪一道门的验收卡在它上面」。
        # 这里把 doc 侧派生的归属与矩阵登记双向锁死 —— 少了这条，新字段就是无人消费的
        # additive 死代码（本 spec 的假绿第①源），而 doc 单方面改归属也不会红。
        assert row.get("adjudication_owner_task") == owner, (
            f"{writer_id} 的 adjudication_owner_task="
            f"{row.get('adjudication_owner_task')!r}，而 tasks.md 派生的归属是 Task {owner}"
        )
        assert row["adjudication_owner_task"] != row["blocking_task"], (
            f"{writer_id} 把裁决归属与真实阻塞写成了同一个值 —— 两者合并后，"
            "「登记的阻塞必须真的把守发布门」那条判据会指向一个不是发布门的任务而失效"
        )


def test_the_registered_blocker_points_at_a_task_that_really_gates_publication(
    gate: ModuleType, inventory: dict[str, Any], matrix: dict[str, Any]
) -> None:
    """**Validates: Requirements 6.2, 9.12**

    阻塞登记必须**可追**：`blocking_task` 里的任务号要真的存在，且它的正文真的承担
    「per-entry approved contract/bundle + candidate finalize 后才有 published
    representation」这件事。

    没有这一条时，`blocking_task` 可以写成任意数字、`reason` 可以写成任意散文，
    于是「为什么迁不了」在下一轮复盘里又要从头查一遍。
    """
    reported = gate.evaluate_gate(inventory)[_CRITERION_KEY]
    if not reported:
        pytest.skip("criterion 已清零，阻塞登记应当已被撤销（由上一条判据覆盖）")

    rows = {r["writer_id"]: r for r in matrix["rows"]}
    bodies = _task_bodies()
    for writer_id in reported:
        tasks = [t for t in re.findall(r"\d+", str(rows[writer_id]["blocking_task"]))]
        assert tasks, rows[writer_id]["blocking_task"]
        for task in tasks:
            assert task in bodies, (
                f"{writer_id} 的 blocking_task 指向不存在的 Task {task}"
            )
        gating = [
            t
            for t in tasks
            if any(
                "finalize" in line.lower() and "contract" in line.lower()
                for line in bodies[t]
            )
        ]
        assert gating, (
            f"{writer_id} 的 blocking_task={tasks} 里没有一个任务的正文承担 "
            "「approved per-entry contract + candidate finalize」这道发布门 —— "
            "登记的阻塞与真实阻塞脱钩了"
        )


def test_relocating_the_criterion_did_not_invert_the_wave_order(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 9.11, 9.12**

    移交本身可能**造出新环**，所以移交方向要有结构判据，而不是靠散文里那句「方向不成环」。

    这条 criterion 原文带一句「`bulk_adapters` gate 亦不得放行 bulk adapter 迁移」。归属搬到
    Wave 7 之后，把那句一起搬过去就等于让 Wave 5 的 bulk adapter 迁移依赖 Wave 7 —— 与它
    要修的那个环同形。故此处按依赖图断言三件事：

    1. 归属任务在 `legacy_delete` gate 里 —— criterion 真的把守了它声称把守的那道门
       （否则移交后它谁也不拦，等于静默豁免）；
    2. 归属任务**不在** `bulk_adapters` gate 里 —— 那句话必须被丢掉而不是被搬走；
    3. 归属任务的 wave **晚于** bulk adapter 迁移 lane —— 这是 (2) 的算术理由，把「为什么
       不能挂」变成可计算事实，而不是一句判断。

    三条都**不**依赖「criterion 今天仍非零」：真清零之后本条仍然成立（它说的是归属与
    gate/wave 的形状）。
    """
    graph = _dependency_graph()
    owner = _criterion_owner_task()
    wave_of = {task: w["wave"] for w in graph["waves"] for task in w["tasks"]}
    gates = graph["gates"]
    assert owner in wave_of, f"归属 Task {owner} 不在任何 wave 里"
    assert _BULK_ADAPTER_LANE_TASK in wave_of, _BULK_ADAPTER_LANE_TASK

    assert owner in gates["legacy_delete"], (
        f"归属 Task {owner} 不在 `legacy_delete` gate {gates['legacy_delete']} 里 —— "
        "criterion 移交后不再把守任何放行门，等于悄悄变成豁免"
    )
    assert owner not in gates["bulk_adapters"], (
        f"归属 Task {owner} 落在 `bulk_adapters` gate {gates['bulk_adapters']} 里 —— "
        f"bulk adapter 迁移在 Wave {wave_of[_BULK_ADAPTER_LANE_TASK]}，"
        f"而本 criterion 归属在 Wave {wave_of[owner]}，挂上即反向依赖"
    )
    assert wave_of[owner] > wave_of[_BULK_ADAPTER_LANE_TASK], (
        f"归属 Task {owner} 在 Wave {wave_of[owner]}，未晚于 bulk adapter lane "
        f"Task {_BULK_ADAPTER_LANE_TASK}（Wave {wave_of[_BULK_ADAPTER_LANE_TASK]}）—— "
        "那么「不能挂 bulk_adapters」这条理由本身不成立，措辞需要重新裁决"
    )

    # 反向：放手方仍必须留在 `bulk_adapters` 里（它自己的其余准则继续把守 bulk 放行）。
    # 少了这一条，「把 criterion 移走」会被误读成「bulk adapter 从此无人把守」。
    relinquisher = "30"
    assert relinquisher in gates["bulk_adapters"], (
        f"Task {relinquisher} 不再是 `bulk_adapters` gate 成员 —— criterion 移交不应改变"
        "bulk 放行的把守结构，本门其余准则仍然是 bulk adapter 的前置门"
    )
    assert owner in graph["dependencies"] and relinquisher in graph["dependencies"][owner], (
        f"Task {owner} 不依赖 Task {relinquisher} —— 归属只能往「已经依赖放手方」的任务移，"
        "否则移交本身造出一条新的反向边"
    )


def test_the_unified_resolver_really_requires_a_published_approved_substrate() -> None:
    """**Validates: Requirements 2.10, 6.2, 9.12**

    上一条登记的阻塞**前提**本身也要是机器可读事实，而不是一句话：

    * `WorkpaperSyncRepository.create_representation` 必须调 `assert_bundle_usable`
      —— 没有 approved 非空 bundle 就产不出 published representation；
    * `materialize_coordinator` 必须为「entry 还没有 published representation」保留一个
      **专门的**拒绝类型，且它真的被 `raise`。

    这两件事一旦被放宽（例如允许 candidate 或 legacy artifact 当 substrate），本条即红，
    届时 4 行的 deferral 理由必须重新评估 —— 而不是继续躺在矩阵里。
    """
    repo_src = (
        _BACKEND / "app" / "services" / "workpaper_sync" / "repository.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(repo_src)
    target = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "create_representation"
        ),
        None,
    )
    assert target is not None, "repository.create_representation 不见了"
    called = {
        node.func.attr
        for node in ast.walk(target)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "assert_bundle_usable" in called, (
        "create_representation 不再校验 approved bundle ⇒ published representation "
        f"可以在没有 approved bundle 的情况下产生；实测调用集 {sorted(called)}"
    )

    coord_src = (
        _BACKEND / "app" / "services" / "workpaper_sync" / "materialize_coordinator.py"
    ).read_text(encoding="utf-8")
    coord_tree = ast.parse(coord_src)
    classes = {
        node.name
        for node in ast.walk(coord_tree)
        if isinstance(node, ast.ClassDef)
    }
    assert "SubstrateNotPublishedError" in classes, (
        "coordinator 不再为「没有 published representation」保留专门的拒绝类型"
    )
    raised = {
        node.exc.func.id
        for node in ast.walk(coord_tree)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
    }
    assert "SubstrateNotPublishedError" in raised, (
        "`SubstrateNotPublishedError` 只被定义、从不被 raise ⇒ 无 published substrate 时"
        "不再 fail closed（additive 死代码）"
    )


def test_owner_named_rows_match_the_gate_report(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 9.11**

    归属任务正文点名的行名，必须就是门今天报出的行（doc ↔ 实测双向）。
    """
    count, names = _owner_named_rows()
    assert names and len(names) == count, (
        f"Task {_criterion_owner_task()} 自称 {count} 条，却列了 {sorted(names)}"
    )
    reported = gate.evaluate_gate(inventory)[_CRITERION_KEY]
    assert {wid.split("::")[-1] for wid in reported} == names, (
        f"门={sorted(reported)} doc={sorted(names)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §2 Task 29 移交过来的 evidence schema 债：复核而不是采信
# ═══════════════════════════════════════════════════════════════════════════


def test_the_quarantine_scenario_is_still_required_and_still_unrepresentable() -> None:
    """**Validates: Requirements 5.6, 12.11**

    Task 29 把 `quarantined_rejects_application_and_engine` 登记为**债**而不是豁免。
    Task 30 必须复核这条登记今天仍然成立，而不是引用它：

    1. 场景仍在 required set 的声明里（没被悄悄摘掉）；
    2. 它推导出的入库 kind 仍是 `standard`，因而 `expects_passable` 为假；
    3. V151 的 `ck_wpees_standard_requires_entities` 真的要求 `standard` 的 passed 行
       `application_ids >= 1` —— 从迁移 SQL 现场解析，不抄结论；
    4. 登记表里恰好只有这一条（多一条就是有人把新债也塞进来了）。

    只要 (2) 或 (3) 变了（例如真加了 `authorization_reject` kind），本条即红 ——
    届时登记必须撤销。这就是「债」与「豁免」的差别：债有到期日。
    """
    from app.services.workpaper_sync import evidence as EV

    sid = "quarantined_rejects_application_and_engine"
    declared = {s.scenario_id: s for s in EV.PROJECTION_BASE_SCENARIOS + EV.CLOSE_SCENARIOS}
    assert sid in declared, f"{sid} 已不在场景声明里 —— required set 被悄悄削了"
    scenario = declared[sid]
    assert scenario.kind is EV.ScenarioKind.standard, scenario.kind
    assert scenario.expects_application is False, (
        "场景开始期望 application 了 ⇒ 与 AC 5.6「quarantined 永不创建 application」冲突"
    )
    assert scenario.schema_representable_as_passed is False, (
        "场景已可记为 passed ⇒ Task 29 的债已解，登记必须撤销"
    )
    assert sid in EV.NON_REPLACEABLE_SCENARIOS, (
        "authorization 家族场景不得被 authority model 替换掉"
    )
    assert set(EV.SCHEMA_UNREPRESENTABLE_SCENARIOS) == {sid}, (
        f"登记表内容变了: {sorted(EV.SCHEMA_UNREPRESENTABLE_SCENARIOS)}"
    )

    sql = _MIGRATION.read_text(encoding="utf-8")
    body = re.search(
        r"CONSTRAINT ck_wpees_standard_requires_entities CHECK \((.*?)\)\),",
        sql,
        re.S,
    )
    assert body, "V151 里找不到 ck_wpees_standard_requires_entities —— 约束改名或删除了"
    text = " ".join(body.group(1).split())
    assert "jsonb_array_length(application_ids) >= 1" in text, text
    #: 约束的豁免名单必须**恰好**是那两个 kind。多一个（例如真加了
    #: `authorization_reject`）就说明债已解，本条即红、登记必须撤销。
    exempted = set(re.findall(r"'([a-z_]+)'", text))
    assert exempted == {"download_only", "recovery_reject", "passed"}, (
        f"约束的 kind 豁免名单变了: {sorted(exempted)}（原为 download_only/recovery_reject）"
    )

    kinds = re.search(r"CONSTRAINT ck_wpees_scenario_kind CHECK \((.*?)\)\),", sql, re.S)
    assert kinds, "V151 里找不到 ck_wpees_scenario_kind"
    assert set(re.findall(r"'([a-z_]+)'", kinds.group(1))) == {
        "standard",
        "download_only",
        "recovery_reject",
        "recovery_claim",
        "close_capture",
    }, kinds.group(1)


def test_the_quarantine_boundary_itself_is_verified_not_deferred() -> None:
    """**Validates: Requirements 5.6**

    evidence 记不下来 ≠ 行为没验。Task 30 owe 的是**行为**：quarantined incoming 在
    application 与 engine 两处都被拒。这里跑生产判定函数本身（纯内存那一层），
    库层与 trigger 层在 `_pg.py` 里跑。

    正向 + 反向都要有：只测「forbidden 被拒」时，把 allowed 集合改成全集也会通过。
    """
    from app.services.workpaper_sync.callback_delivery import (
        QUARANTINE_ALLOWED_OPERATIONS,
        QUARANTINE_FORBIDDEN_OPERATIONS,
        QuarantineOperationForbiddenError,
        assert_quarantine_operation_allowed,
    )

    assert not (set(QUARANTINE_ALLOWED_OPERATIONS) & set(QUARANTINE_FORBIDDEN_OPERATIONS)), (
        "allowed 与 forbidden 有交集 ⇒ 判定自相矛盾"
    )
    for op in ("application", "extract", "merge", "retry", "rematerialize", "release"):
        assert op in QUARANTINE_FORBIDDEN_OPERATIONS, op
        with pytest.raises(QuarantineOperationForbiddenError):
            assert_quarantine_operation_allowed(op)
    for op in sorted(QUARANTINE_ALLOWED_OPERATIONS):
        assert_quarantine_operation_allowed(op)  # 不抛即为通过（反向自检）


def test_delivery_ownership_is_decided_by_durable_at_not_by_terminal_state() -> None:
    """**Validates: Requirements 5.1, 5.2, 5.3**

    Task 30 正文点名的变异之一是「把 delivery gate 改回按 terminal 判 owner」。
    区分这两种实现的**唯一**办法是取同一个 `state`、只翻 `durable_at`：

    * `state=durable, durable_at=True` + application ⇒ 允许（owner 成立）；
    * `state=durable, durable_at=False` + application ⇒ **禁止**（pre-durable 不得有 owner）；
      这两行的 state 逐字相同，所以「按 terminal 判」的实现无法同时满足它们。
    * `state=durable, durable_at=True` 但**无** owner ⇒ 禁止（durable 后必须恰一个）；
    * pre-durable 终态（rejected / error, `durable_at=False`）⇒ 允许且零 owner；
    * 双 owner ⇒ 无论状态一律禁止。
    """
    import uuid as _uuid

    from app.services.workpaper_sync.callback_delivery import (
        classify_delivery_ownership,
    )
    from app.services.workpaper_sync.models import (
        CorrelationResult,
        DeliveryOwnershipError,
        DeliveryState,
    )

    app_id, case_id, req_id, art_id = (_uuid.uuid4() for _ in range(4))

    def _probe(**over: Any) -> Any:
        kwargs: dict[str, Any] = {
            "state": DeliveryState.durable,
            "durable_at_is_set": True,
            "application_id": app_id,
            "callback_recovery_case_id": None,
            "forcesave_request_id": req_id,
            "incoming_artifact_id": art_id,
            "correlation_result": CorrelationResult.existing_application,
        }
        kwargs.update(over)
        return classify_delivery_ownership(**kwargs)

    # ① durable_at 已置 + application ⇒ 允许
    assert _probe().verdict.value == "allowed"
    # ② 同一个 state，只把 durable_at 翻掉 ⇒ 必须禁止（判据就在这一行）
    with pytest.raises(DeliveryOwnershipError):
        _probe(durable_at_is_set=False)
    # ③ durable_at 已置但没有 owner ⇒ 禁止（durable 后 owner 恰一）
    with pytest.raises(DeliveryOwnershipError):
        _probe(application_id=None)
    # ④ pre-durable 终态零 owner ⇒ 允许
    for state in (DeliveryState.rejected, DeliveryState.error):
        row = classify_delivery_ownership(
            state=state,
            durable_at_is_set=False,
            application_id=None,
            callback_recovery_case_id=None,
            forcesave_request_id=req_id,
            incoming_artifact_id=None,
            correlation_result=None,
        )
        assert row.verdict.value == "allowed", (state, row)
    # ⑤ durable + unmatched ⇒ recovery case 恰一个 owner；再挂 request 即双 owner ⇒ 禁止
    assert (
        classify_delivery_ownership(
            state=DeliveryState.unmatched,
            durable_at_is_set=True,
            application_id=None,
            callback_recovery_case_id=case_id,
            forcesave_request_id=None,
            incoming_artifact_id=art_id,
            correlation_result=CorrelationResult.unmatched,
        ).verdict.value
        == "allowed"
    )
    with pytest.raises(DeliveryOwnershipError):
        classify_delivery_ownership(
            state=DeliveryState.received,
            durable_at_is_set=False,
            application_id=app_id,
            callback_recovery_case_id=case_id,
            forcesave_request_id=None,
            incoming_artifact_id=None,
            correlation_result=None,
        )
