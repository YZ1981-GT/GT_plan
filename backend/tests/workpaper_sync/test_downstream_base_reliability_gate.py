# -*- coding: utf-8 -*-
"""跨 Wave 假绿拦截：**门未过时，下游任务不得宣称 base 可靠**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure
被兑现的散文: tasks.md Task 20 正文最后一条 —— 「本门未过，Wave 2 coordinator 与任何
adapter pilot 不得宣称 base 可靠。」在本文件出现之前，这句话**没有任何守卫兑现**：
门现算 916 条 blocking facts（`[BLOCKED]`），而 Wave 2–5 的 Tasks 25–47 / 58 / 59 全部
标着 `[x]`。这正是平台假绿第①源的治理层形态 —— 一句约束只活在散文里，等于不存在。

## 判据形态（三类「宣称」，全部落在结构与真实执行上）

===========  ==========================================================================
类别         「宣称 base 可靠」被做成了什么可判结构
===========  ==========================================================================
A 依赖序     下游任务标 `[x]`，而它所依赖的 base 欠账，其**归属任务排在它之后**
             （wave 更大，或该归属任务反过来依赖这个宣称方）。归属由 tasks.md 的
             「14 条准则的归属」行派生，欠账计数由 `evaluate_gate()` **现场执行**得出。
             同一函数还覆盖 instruction 的字面读法：归属就是本门（Task 20）自己的准则
             一旦非零，任何下游 `[x]` 同样被拦下（:data:`_KIND_GATE_OWNER_OPEN`）。
B 门禁序     依赖图 `gates` 块里由本门把守的那道闸（`bulk_adapters`）**之后**的任务
             标了 `[x]`，而门 `[BLOCKED]`。「谁在闸后」= 闸的全部把守者都落在其依赖
             闭包里的任务集合，从 JSON 现算。
C 证据结构   slice / manifest / contract 里的 entry 节点在**结构上**断言了验收：
             `evidence.<verification_state>` 取了「非不可验证」的值、`capability`
             或 `adjudication.honest_capability` 等于 bidirectional、或 SR-5/SR-6 的
             五个身份字段任一非 null。字段名与词汇**从 paradigm 的 `slice_schema`
             现读**（`required_entry_evidence` / `behavioral_rules` /
             `presence_required_value_may_be_null`），不在本文件里抄。
===========  ==========================================================================

## 🔴 为什么这不是字符串匹配（三条实测反例）

1. **正文里的 `verified` 多数是否定句。** 全文扫 tasks.md，命中「verified」的行是
   「真实 smoke 只能作为附加证据，**不能恢复** verified」「smoke 只能附加，**不能恢复**
   verified」—— 关键词命中处的语义与「宣称」正好相反。按关键词判会得到纯假阳性。
2. **evidence 目录里 `RED`/`GREEN`/`PASS` 有 2000+ 处，全是变异判定。**
   `mutation_report.json` 的 `verdict` 字段与 base 可靠性无关；只要按值扫描就必然
   淹没在噪声里。本文件因此只认**字段路径**（`entry` 节点下的 `evidence.<field>`），
   且 `entry` 节点靠 `entry_id` 键判定。
3. **同一个词在不同字段名下含义相反。** E 循环 slice 里 `bidirectional` 出现三次，
   全部是 `blocking_preconditions[].blocks == "bidirectional"`（= 「它阻断
   bidirectional」）。按值匹配会把「登记了阻断项」读成「宣称已 bidirectional」。

## 🔴 「本门未过」为什么取门的 `has_debt` 而不是只取归属 Task 20 的那几条

实测：归属 Task 20 的六条准则（`keeps_legacy_write_path_beside_unified_commit`、
`after_save_still_increments_revision`、`representation_upgrade_increments_business_revision`、
`artifact_snapshot_writer_not_verifiable`、`retired_writer_not_verifiable`、
`missing_required_domain`）**当前全为 0**；912 条归 Task 74、4 条归 Task 71。若「本门未过」
只按归属 Task 20 的准则判，本守卫会**恒绿** —— 而门自己 `exit 1 [BLOCKED]`。

Task 20 正文对此有明文裁决：移交的是**裁决归属**，`check_workpaper_writer_revision_gate.py`
「必须继续算这七条、继续把它们计入 `has_debt`，一行计算都不许删」。所以：
**归属决定谁清零，不决定门有没有过。** 本文件两者都用，且分工写死在判据里 ——
:func:`door_is_blocked` 取全部准则（:func:`test_a_relocated_criterion_still_blocks_the_door`
用合成场景锁死「只剩已移交准则非零时门仍然未过」），归属只用来回答「谁排在谁之后」。

## 存量红与解除条件

:func:`test_downstream_completed_tasks_do_not_outrun_the_owner_of_the_open_debt` 与
:func:`test_no_task_behind_the_bulk_adapter_gate_is_completed_while_the_door_is_blocked`
以 ``xfail(strict=True)`` 标注当前欠账。**不用 `pytest.skip`** —— skip 记为通过就是
fail-open，正是本文件要拦的东西。`strict=True` 保证欠账清掉后这两条变成 XPASS 报错，
逼人回来删标记而不是让守卫悄悄退化成装饰。逐条解除条件写在各自的 ``reason`` 里。

反向变异脚本：``backend/scripts/diagnose/mutate_downstream_base_reliability_gate.py``。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SPEC_DIR = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
_TASKS_MD = _SPEC_DIR / "tasks.md"
_SPEC_EVIDENCE_DIR = _SPEC_DIR / "evidence"
_DATA_DIR = _REPO / "backend" / "data"
_GATE_PATH = (
    _REPO / "backend" / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
)
_PARADIGM_PATH = _DATA_DIR / "workpaper_sync_migration_paradigm.json"
_ENTRY_MANIFEST_PATH = _DATA_DIR / "workpaper_sync_entry_manifest.json"
#: 归属解析工具的单一真源。**只 import，不修改** —— 派生逻辑分叉本身就是漂移源。
_TASK20_GUARD_PATH = Path(__file__).with_name("test_task20_writer_gate.py")

#: 本守卫守的是哪一道门。它不是「名单」而是「门的标识」：下游集合、闸后集合、准则归属
#: 全部由它现场派生，改依赖图不需要改这里，改这里等于换一道门。
_GATE_TASK = "20"

#: tasks.md 勾选态里表示「宣称完成」的标记。
#:
#: 🔴 `~`（进行中）与 `-`（阻塞/驻留）**不算宣称** —— 它们恰恰是「没宣称完成」的写法，
#: 把它们算进来会让本守卫变成「凡有欠账就打红所有下游任务」的恒红装饰。
_CLAIM_MARKERS = frozenset({"x"})

_TASK_HEAD_RE = re.compile(r"^- \[([ x~\-])\] (\d+)\.\s")
_GRAPH_RE = re.compile(r"^## Task Dependency Graph\s*\n```json\n(.*?)\n```", re.S | re.M)
#: paradigm `behavioral_rules` 里 `capability == <token> ⇒ …` 的那个 token（SR-6）。
#:
#: 尾部要求一个空格 + 非字母，专为排除 SR-4 的 `capability == adjudication.honest_capability`
#: （那条没有 `⇒`，也不是一个能力枚举值）。命中数必须唯一，否则 fail closed。
_SR_CAPABILITY_RE = re.compile(r"capability == ([a-z_]+) ⇒")
#: SR-7 的 `evidence.verification_state == 'UNVERIFIABLE' ⇒ …` —— 「不可验证」态的字面来源。
_SR_CANNOT_VERIFY_RE = re.compile(r"verification_state == '([A-Z_]+)'")

# ── 违规类别（判据的输出词汇，报告与变异脚本都按它对齐）────────────────────────
_KIND_OWNER_LATER = "owner_scheduled_after_claimant"
_KIND_GATE_OWNER_OPEN = "gate_owner_criterion_still_open"
_KIND_GATE_CROSSED = "completed_behind_a_blocked_gate"
_KIND_EV_VERIFIED = "evidence_asserts_verification_state"
_KIND_EV_BIDI = "evidence_asserts_bidirectional_capability"
_KIND_EV_IDENTITY = "evidence_carries_bidirectional_identity_field"


# ═══════════════════════════ 纯派生：tasks.md → 图与状态 ═══════════════════════
#
# 全部做成纯函数（入参是文本/字典，不碰磁盘），这样反向自检可以直接喂合成输入 ——
# 「守卫不是恒红也不是恒绿」只有在判据可注入时才证得出来。


def _normalized(path: Path) -> str:
    """按字节读 + 归一化行尾。CRLF 工作树下 `\\n` 锚定的正则否则会静默零命中。"""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def parse_dependency_graph(tasks_md_text: str) -> dict[str, Any]:
    """tasks.md 的 ``## Task Dependency Graph`` JSON 块 → dict。"""
    match = _GRAPH_RE.search(tasks_md_text)
    assert match, "tasks.md 里找不到 `## Task Dependency Graph` 的 json 块"
    graph = json.loads(match.group(1))
    for key in ("waves", "dependencies", "gates"):
        assert key in graph, f"依赖图缺 `{key}` —— 下游集合无从派生"
    return graph


def parse_task_states(tasks_md_text: str) -> dict[str, str]:
    """tasks.md → ``{任务号: 勾选标记}``。行首锚定，不用字符窗口。"""
    states: dict[str, str] = {}
    for line in tasks_md_text.split("\n"):
        head = _TASK_HEAD_RE.match(line)
        if head:
            states[head.group(2)] = head.group(1)
    assert states, "tasks.md 一个任务勾选态都没解析出来 —— 本文件的判据会全部空跑"
    return states


def wave_index(graph: dict[str, Any]) -> dict[str, int]:
    """``{任务号: wave 序号}``。一个任务出现在两个 wave 里即抛（归属不可有两个答案）。"""
    waves: dict[str, int] = {}
    for wave in graph["waves"]:
        for task in wave["tasks"]:
            task = str(task)
            assert task not in waves, f"Task {task} 同时出现在两个 wave 里"
            waves[task] = int(wave["wave"])
    missing = sorted(set(graph["dependencies"]) - set(waves), key=str)
    assert not missing, f"依赖图里有任务不属于任何 wave：{missing}"
    return waves


def dependency_closure(deps: dict[str, list[str]], task: str) -> set[str]:
    """``task`` 的**传递**依赖闭包（不含自身）。"""
    seen: set[str] = set()
    stack = list(deps.get(task, []))
    while stack:
        node = str(stack.pop())
        if node in seen:
            continue
        seen.add(node)
        stack.extend(str(n) for n in deps.get(node, []))
    return seen


def downstream_of_gate(
    *, deps: dict[str, list[str]], waves: dict[str, int], gate_task: str
) -> list[str]:
    """「下游」= 排在门之后的 wave 里、且依赖闭包含这道门的任务。

    🔴 **不手写名单**：Wave 2 的 Tasks 21–24 就在门之后的 wave 里，但它们的依赖闭包
    里没有 Task 20（21 依赖 4/9/10/12），所以它们**不是**这道门的下游 —— 手写
    「Wave 2 = 21..30」会把四个无关任务打红，而这类误报最后总是靠放宽判据来消掉。
    """
    gate_wave = waves[gate_task]
    return sorted(
        (
            task
            for task in deps
            if waves[task] > gate_wave and gate_task in dependency_closure(deps, task)
        ),
        key=int,
    )


def gate_names_held_by(gates: dict[str, list[str]], gate_task: str) -> list[str]:
    """依赖图 ``gates`` 块里由该任务把守的闸名。"""
    return sorted(name for name, holders in gates.items() if gate_task in map(str, holders))


def tasks_behind_gate(
    *, deps: dict[str, list[str]], gates: dict[str, list[str]], gate_name: str
) -> list[str]:
    """闸后的任务 = 该闸**全部**把守者都落在其依赖闭包里的任务。"""
    holders = {str(h) for h in gates[gate_name]}
    assert holders, f"闸 `{gate_name}` 没有把守者 —— 空把守集会让闸后集合退化成全集"
    return sorted(
        (task for task in deps if holders <= dependency_closure(deps, task)), key=int
    )


# ═══════════════════════════ 纯判据：门的状态 ═════════════════════════════════


def blocking_counts(issues: dict[str, list[str]]) -> dict[str, int]:
    """``evaluate_gate()`` 的 issue map → ``{准则: 非零计数}``（零的准则不出现）。"""
    return {key: len(rows) for key, rows in issues.items() if rows}


def door_is_blocked(issues: dict[str, list[str]]) -> bool:
    """门有没有过 —— 与门自己的 ``has_debt = any(issues.values())`` 逐字同构。

    🔴 **不按归属过滤**。已移交的准则仍留在门里且仍计入 `has_debt`（Task 20 正文：
    「一行计算都不许删」），因为「一条准则从报告里消失」与「它归零」在报告里长得一样。
    """
    return any(issues.values())


def owner_is_scheduled_after(
    *,
    owner: str,
    claimant: str,
    waves: dict[str, int],
    deps: dict[str, list[str]],
) -> bool:
    """欠账的归属方是否排在宣称方**之后**。

    两种「之后」都算：wave 更大；或归属方的依赖闭包里含宣称方（那它只可能更晚）。
    """
    if owner == claimant:
        return False
    if waves[owner] > waves[claimant]:
        return True
    return claimant in dependency_closure(deps, owner)


def cross_wave_base_claims(
    *,
    issues: dict[str, list[str]],
    homing: dict[str, str],
    states: dict[str, str],
    waves: dict[str, int],
    deps: dict[str, list[str]],
    gate_task: str,
) -> list[dict[str, Any]]:
    """类别 A：下游 `[x]` 任务与它够不着的 base 欠账。

    两种违规：

    - :data:`_KIND_GATE_OWNER_OPEN` —— 欠账归属就是本门，且未归零。这是 instruction
      「只用归属本门的准则判本门未过」的字面兑现。
    - :data:`_KIND_OWNER_LATER` —— 欠账归属方排在宣称方之后。这是当前的真实形态：
      912 条归 Task 74、4 条归 Task 71，两者都在 Wave 7，而宣称方在 Wave 2–5。
    """
    open_debt = blocking_counts(issues)
    if not open_debt:
        return []
    downstream = downstream_of_gate(deps=deps, waves=waves, gate_task=gate_task)
    violations: list[dict[str, Any]] = []
    for task in downstream:
        if states.get(task) not in _CLAIM_MARKERS:
            continue
        for criterion, count in sorted(open_debt.items()):
            owner = homing.get(criterion)
            if owner is None:
                # 归属缺失单独由 test_every_gate_criterion_has_exactly_one_home 兜。
                continue
            if owner == gate_task:
                kind = _KIND_GATE_OWNER_OPEN
            elif owner_is_scheduled_after(
                owner=owner, claimant=task, waves=waves, deps=deps
            ):
                kind = _KIND_OWNER_LATER
            else:
                continue
            violations.append(
                {
                    "kind": kind,
                    "task": task,
                    "task_wave": waves[task],
                    "criterion": criterion,
                    "open_facts": count,
                    "owner": owner,
                    "owner_wave": waves.get(owner),
                }
            )
    return violations


def gate_crossing_claims(
    *,
    issues: dict[str, list[str]],
    states: dict[str, str],
    deps: dict[str, list[str]],
    gates: dict[str, list[str]],
    gate_task: str,
) -> list[dict[str, Any]]:
    """类别 B：本门把守的闸之后，已有任务标 `[x]`，而门未过。"""
    if not door_is_blocked(issues):
        return []
    violations: list[dict[str, Any]] = []
    for gate_name in gate_names_held_by(gates, gate_task):
        for task in tasks_behind_gate(deps=deps, gates=gates, gate_name=gate_name):
            if task == gate_task or states.get(task) not in _CLAIM_MARKERS:
                continue
            violations.append(
                {
                    "kind": _KIND_GATE_CROSSED,
                    "task": task,
                    "gate": gate_name,
                    "holders": sorted(map(str, gates[gate_name]), key=int),
                    "open_facts": sum(len(rows) for rows in issues.values()),
                }
            )
    return violations


# ═══════════════════════════ 纯判据：证据结构 ════════════════════════════════


def iter_entry_nodes(doc: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    """递归找出所有 entry 节点（含 ``entry_id`` 键的 dict），返回 ``(路径, 节点)``。"""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(doc, dict):
        if "entry_id" in doc:
            found.append((path or "/", doc))
        for key, value in doc.items():
            found.extend(iter_entry_nodes(value, f"{path}/{key}"))
    elif isinstance(doc, list):
        for index, value in enumerate(doc):
            found.extend(iter_entry_nodes(value, f"{path}[{index}]"))
    return found


def evidence_base_claims(
    *,
    docs: dict[str, Any],
    evidence_field: str,
    cannot_verify_state: str,
    bidirectional_token: str,
    identity_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    """类别 C：磁盘上的 entry 节点在结构上断言了「base 已可用」。

    三种断言形态，全部按**字段路径**判定：

    1. ``evidence.<evidence_field>`` 取了非空且**不等于**「不可验证」态的值。
       🔴 判据是「不等于 UNVERIFIABLE」而不是「等于 VERIFIED」—— 换个词
       （`CLOSED` / `PASSED` / `OK`）就绕过去的判据是 fail-open；未知词一律当断言。
    2. ``capability`` 或 ``adjudication.honest_capability`` 等于 SR-6 的 bidirectional。
    3. 裁决为**非** bidirectional（`single_*` / `unreachable`）的 entry 上，SR-5/SR-6 的五个
       身份字段任一非 null —— 裁 single 却挂着 adapter/contract/bundle/candidate/
       representation，就是「为凑数伪造供给」。

    🔴 **第 3 条必须以 `capability` 存在为前提**（SR-5/SR-6 都是以 capability 为条件的
    蕴含式）。初版漏了这个前提，于是四处 pilot 执行记录被误报：
    `task42/43 的 identity_and_digests.json` 与 `task40 的 run_facts.json` 带
    `entry_id` + `adapter_id` 但**没有 capability 字段** —— 它们只是登记 adapter 身份，
    正文同时写着 `capability_enabled: false`、`aggregate_result…: failed (UNVERIFIABLE…)`、
    `finalize_status: blocked_by_UPSTREAM_DEBT_…`，是**诚实的未闭环记录**。把 slice
    的裁决规则套到它们头上，与本文件开头批的「按值匹配」是同一种错：判据越出了规则
    自己声明的作用域。
    """
    claims: list[dict[str, Any]] = []
    for doc_name, doc in sorted(docs.items()):
        for path, entry in iter_entry_nodes(doc):
            entry_id = entry.get("entry_id")
            evidence = entry.get("evidence")
            if isinstance(evidence, dict) and evidence_field in evidence:
                state = evidence[evidence_field]
                if (
                    isinstance(state, str)
                    and state.strip()
                    and state != cannot_verify_state
                ):
                    claims.append(
                        {
                            "kind": _KIND_EV_VERIFIED,
                            "doc": doc_name,
                            "path": f"{path}/evidence/{evidence_field}",
                            "entry_id": entry_id,
                            "detail": state,
                        }
                    )
            capability_paths = {"capability": entry.get("capability")}
            adjudication = entry.get("adjudication")
            if isinstance(adjudication, dict):
                capability_paths["adjudication/honest_capability"] = adjudication.get(
                    "honest_capability"
                )
            declared = {
                field: value
                for field, value in capability_paths.items()
                if isinstance(value, str) and value.strip()
            }
            for field, value in sorted(declared.items()):
                if value == bidirectional_token:
                    claims.append(
                        {
                            "kind": _KIND_EV_BIDI,
                            "doc": doc_name,
                            "path": f"{path}/{field}",
                            "entry_id": entry_id,
                            "detail": value,
                        }
                    )
            if declared and bidirectional_token not in declared.values():
                # SR-5：裁 single_* / unreachable ⇒ 五个身份字段必须全为 null
                for field in identity_fields:
                    if entry.get(field) is not None:
                        claims.append(
                            {
                                "kind": _KIND_EV_IDENTITY,
                                "doc": doc_name,
                                "path": f"{path}/{field}",
                                "entry_id": entry_id,
                                "detail": (
                                    f"capability={sorted(declared.values())} 却挂着 "
                                    f"{entry.get(field)!r}"
                                ),
                            }
                        )
    return claims


# ═══════════════════════════ 实测事实（fixtures）══════════════════════════════


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法以 importlib 加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tasks_md_text() -> str:
    return _normalized(_TASKS_MD)


@pytest.fixture(scope="module")
def graph(tasks_md_text: str) -> dict[str, Any]:
    return parse_dependency_graph(tasks_md_text)


@pytest.fixture(scope="module")
def deps(graph: dict[str, Any]) -> dict[str, list[str]]:
    return {str(k): [str(v) for v in vs] for k, vs in graph["dependencies"].items()}


@pytest.fixture(scope="module")
def waves(graph: dict[str, Any]) -> dict[str, int]:
    return wave_index(graph)


@pytest.fixture(scope="module")
def states(tasks_md_text: str) -> dict[str, str]:
    return parse_task_states(tasks_md_text)


@pytest.fixture(scope="module")
def issues() -> dict[str, list[str]]:
    """门的状态**现场取**：加载门脚本、读清册、跑 `evaluate_gate()`。

    🔴 不读任何缓存报告（`evidence/task20-writer-gate/gate_blockers.json` 之类）——
    缓存报告与源码脱钩时守卫会锁死一个过期结论，那是「把错值当基线」的形态。
    """
    gate = _load_module("downstream_gate_ref", _GATE_PATH)
    return gate.evaluate_gate(gate.load_inventory())


@pytest.fixture(scope="module")
def homing() -> dict[str, str]:
    """准则归属：``{门内 issue key: 归属任务号}``，从 tasks.md 的归属行派生。

    直接 import Task 20 守卫里的解析器 —— 派生逻辑只许有一份。自己再抄一个解析器
    才是漂移源：两份解析器可以各自「解析成功」而给出不同答案，谁都不红。
    """
    ref = _load_module("downstream_task20_guard_ref", _TASK20_GUARD_PATH)
    return ref._gate_criteria_homing_from_tasks_md()


@pytest.fixture(scope="module")
def paradigm() -> dict[str, Any]:
    return json.loads(_PARADIGM_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def claim_vocabulary(paradigm: dict[str, Any]) -> dict[str, Any]:
    """类别 C 的字段名与词汇 —— 全部从 paradigm 的 `slice_schema` 现读。"""
    schema = paradigm["slice_schema"]
    required_evidence = list(schema["required_entry_evidence"])
    assert "verification_state" in required_evidence, (
        "paradigm 的 required_entry_evidence 里没有 verification_state —— "
        f"实际={required_evidence}。字段名改了必须同步本判据，不许静默空跑"
    )
    rules = " || ".join(str(rule.get("rule", "")) for rule in schema["behavioral_rules"])
    capability_tokens = set(_SR_CAPABILITY_RE.findall(rules))
    assert len(capability_tokens) == 1, (
        f"从 behavioral_rules 派生 bidirectional 能力字面量失败，命中={sorted(capability_tokens)}"
    )
    cannot_verify = set(_SR_CANNOT_VERIFY_RE.findall(rules))
    assert len(cannot_verify) == 1, (
        f"从 behavioral_rules 派生「不可验证」态失败，命中={sorted(cannot_verify)}"
    )
    identity_fields = tuple(schema["presence_required_value_may_be_null"])
    assert identity_fields, "SR-5/SR-6 的身份字段表为空 —— 类别 C 的第三条判据会恒绿"
    return {
        "evidence_field": "verification_state",
        "bidirectional_token": capability_tokens.pop(),
        "cannot_verify_state": cannot_verify.pop(),
        "identity_fields": identity_fields,
    }


@pytest.fixture(scope="module")
def evidence_docs() -> dict[str, Any]:
    """被扫的证据产物：slice、全量 manifest/overlay、contract、spec evidence 目录。"""
    paths: list[Path] = []
    paths.extend(sorted(_DATA_DIR.glob("*_cycle_manifest_slice.json")))
    paths.extend(sorted(_DATA_DIR.glob("workpaper_sync_*evidence*.json")))
    paths.extend(sorted(_DATA_DIR.glob("workpaper_sync_entry_*.json")))
    paths.extend(sorted((_DATA_DIR / "workpaper_sync_contracts").glob("*.json")))
    paths.extend(sorted(_SPEC_EVIDENCE_DIR.rglob("*.json")))
    docs: dict[str, Any] = {}
    for path in paths:
        rel = path.relative_to(_REPO).as_posix()
        try:
            docs[rel] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # noqa: PERF203
            pytest.fail(f"证据产物无法解析（不得当成「没有断言」放过）：{rel} —— {exc}")
    return docs


# ═══════════════════════════ §1 派生面自身可信 ════════════════════════════════


def test_the_dependency_graph_and_task_states_parse(
    graph: dict[str, Any], deps: dict[str, list[str]], states: dict[str, str]
) -> None:
    """派生面必须有真实产出 —— 空分母会让全部判据恒绿。"""
    assert len(graph["waves"]) >= 2, "只解析出一个 wave，跨 wave 判据无从成立"
    assert len(deps) >= 50, f"依赖图只有 {len(deps)} 个节点，疑似解析到了错的代码块"
    unknown = sorted(set(deps) - set(states), key=int)
    assert not unknown, f"依赖图里的任务在正文里没有勾选行：{unknown}"
    assert _GATE_TASK in deps, f"依赖图里没有本门 Task {_GATE_TASK}"


def test_the_downstream_set_is_derived_not_enumerated(
    deps: dict[str, list[str]], waves: dict[str, int]
) -> None:
    """「下游」= waves JSON + 依赖闭包现算，且能把「更晚但无关」的任务排除干净。"""
    downstream = downstream_of_gate(deps=deps, waves=waves, gate_task=_GATE_TASK)
    assert downstream, "派生出的下游集合为空 —— 判据会恒绿"

    gate_wave = waves[_GATE_TASK]
    same_wave = [t for t in downstream if waves[t] <= gate_wave]
    assert not same_wave, (
        f"同 wave / 更早的任务被算成「下游」：{same_wave} —— "
        "跨 wave 假绿判据的分母必须严格排在门之后"
    )

    later = [t for t in deps if waves[t] > gate_wave]
    independent = sorted(set(later) - set(downstream), key=int)
    assert independent, (
        "门之后的每一个任务都被算成下游 —— 那说明闭包判定失效（退化成「wave 更大即下游」）"
    )
    for task in independent:
        assert _GATE_TASK not in dependency_closure(deps, task), (
            f"Task {task} 的闭包里有 Task {_GATE_TASK} 却没被算进下游"
        )

    transitive = [
        t for t in downstream if _GATE_TASK not in deps[t]
    ]
    assert transitive, (
        "下游集合里没有一个是**传递**依赖到门的 —— 那说明闭包没在传递，"
        "判据退化成「只看直接依赖」"
    )


def test_every_gate_criterion_has_exactly_one_home(
    issues: dict[str, list[str]], homing: dict[str, str], deps: dict[str, list[str]]
) -> None:
    """归属表与门必须**双向**覆盖：门里多一条无人认领、归属行点了门里没有的 key，两边都红。"""
    gate_keys = set(issues)
    homed_keys = set(homing)
    assert gate_keys == homed_keys, (
        "准则归属与门的准则集不一致 —— 「谁负责清零」出现空洞或幽灵条目：\n"
        f"  门里有、归属行没有：{sorted(gate_keys - homed_keys)}\n"
        f"  归属行有、门里没有：{sorted(homed_keys - gate_keys)}"
    )
    unknown_owners = sorted({t for t in homing.values() if t not in deps}, key=str)
    assert not unknown_owners, (
        f"归属指向了依赖图里不存在的任务：{unknown_owners} —— 归属方必须是可排序的真实任务"
    )


def test_the_claim_vocabulary_is_derived_from_the_paradigm_schema(
    claim_vocabulary: dict[str, Any]
) -> None:
    """类别 C 的字段名/词汇来自 paradigm，不是本文件里的字面量。"""
    assert claim_vocabulary["bidirectional_token"] == "bidirectional", (
        f"SR-6 的能力字面量变了：{claim_vocabulary['bidirectional_token']!r} —— "
        "变了不是错，但必须有人看见（类别 C 的第二条判据以它为准）"
    )
    assert claim_vocabulary["cannot_verify_state"] == "UNVERIFIABLE", (
        f"SR-7 的「不可验证」态变了：{claim_vocabulary['cannot_verify_state']!r}"
    )
    assert len(claim_vocabulary["identity_fields"]) >= 5, (
        f"SR-5/SR-6 身份字段只派生出 {claim_vocabulary['identity_fields']}"
    )


def test_the_evidence_scan_has_a_real_denominator(
    evidence_docs: dict[str, Any], paradigm: dict[str, Any]
) -> None:
    """类别 C 的分母必须真的扫到了 entry 节点，且覆盖 paradigm 钦定的参照实例。"""
    reference = paradigm["slice_schema"]["reference_instance"]
    assert reference in evidence_docs, (
        f"paradigm 钦定的参照 slice 没被扫到：{reference}（扫到 {len(evidence_docs)} 份文档）"
    )
    assert iter_entry_nodes(evidence_docs[reference]), f"参照 slice 里一个 entry 都没找到：{reference}"

    manifest = json.loads(_ENTRY_MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_floor = len(manifest["entries"])
    inspected = sum(len(iter_entry_nodes(doc)) for doc in evidence_docs.values())
    assert inspected >= expected_floor, (
        f"只检查了 {inspected} 个 entry 节点，少于全量 manifest 的 {expected_floor} 条 —— "
        "glob 或递归失效时类别 C 会恒绿"
    )


def test_a_relocated_criterion_still_blocks_the_door(
    issues: dict[str, list[str]], homing: dict[str, str]
) -> None:
    """合成场景：只剩**已移交**的准则非零时，门必须仍然「未过」。

    这是本文件里最要紧的一条 fail-open 锁。Task 20 自有的六条准则实测全为 0，若
    「本门未过」按归属过滤，916 条欠账会被读成「门已过」，整个守卫恒绿。
    """
    relocated = sorted(k for k, owner in homing.items() if owner != _GATE_TASK)
    assert relocated, "归属表里没有任何已移交的准则 —— 本条判据的前提不成立"
    synthetic = {key: [] for key in issues}
    synthetic[relocated[0]] = ["synthetic::writer_row"]
    assert door_is_blocked(synthetic), (
        f"只有已移交准则 `{relocated[0]}` 非零时门被判成「已过」—— "
        "那等于「一条准则换了归属就从 has_debt 里消失」，与它归零逐字相同（fail-open）"
    )
    assert not door_is_blocked({key: [] for key in issues}), (
        "全零时门仍被判「未过」—— 判据恒红，无法反证"
    )


# ═══════════════════════════ §2 存量红：下游宣称 base 可靠 ═══════════════════
#
# 🔴 这两条**必然打红当前状态**，这就是本文件的全部意义。用 xfail(strict=True) 冻结，
# 不用 skip（skip 记为通过 = fail-open，正是要拦的东西）。


@pytest.mark.xfail(
    strict=True,
    reason=(
        "存量欠账：门现算 916 条 blocking facts，912 条归 Task 74（Wave 7）、4 条归 "
        "Task 71（Wave 7），而 Tasks 25–47 / 58 / 59（Wave 2–5）已全部标 [x]。"
        "解除条件 = Task 74 把七条准则清零 + Task 71 清掉 multi_resolver，"
        "或把这些下游任务的 [x] 改回未完成态。清零后本条会 XPASS(strict) 报错，"
        "届时必须删掉这个 xfail 标记（不许留着当装饰）。"
    ),
)
def test_downstream_completed_tasks_do_not_outrun_the_owner_of_the_open_debt(
    issues: dict[str, list[str]],
    homing: dict[str, str],
    states: dict[str, str],
    waves: dict[str, int],
    deps: dict[str, list[str]],
) -> None:
    """类别 A：`[x]` 的下游任务，其 base 欠账的归属方不得排在它之后。"""
    violations = cross_wave_base_claims(
        issues=issues,
        homing=homing,
        states=states,
        waves=waves,
        deps=deps,
        gate_task=_GATE_TASK,
    )
    tasks = sorted({v["task"] for v in violations}, key=int)
    sample = "\n".join(
        f"  Task {v['task']}(W{v['task_wave']}) [{v['kind']}] "
        f"{v['criterion']}={v['open_facts']} → 归属 Task {v['owner']}(W{v['owner_wave']})"
        for v in violations[:12]
    )
    assert not violations, (
        f"{len(violations)} 条跨 wave 宣称，涉及 {len(tasks)} 个任务 {tasks}：\n{sample}\n"
        f"  ... 共 {len(violations)} 条\n"
        "这些任务标着 [x]，但它们依赖的 base 欠账要等更晚的 wave 才清 —— "
        "「完成」宣称的是一个当时还不存在的 base（tasks.md Task 20：本门未过，"
        "Wave 2 coordinator 与任何 adapter pilot 不得宣称 base 可靠）"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "存量欠账：Task 20 把守 `bulk_adapters` 闸（把守者 20/30/44），闸后的 "
        "Tasks 45/46/47 已标 [x]，而门 [BLOCKED]。解除条件 = 门归零（Task 74 + Task 71），"
        "或把闸后已 [x] 的任务改回未完成态。归零后本条 XPASS(strict) 报错，须删标记。"
    ),
)
def test_no_task_behind_the_bulk_adapter_gate_is_completed_while_the_door_is_blocked(
    issues: dict[str, list[str]],
    states: dict[str, str],
    deps: dict[str, list[str]],
    graph: dict[str, Any],
) -> None:
    """类别 B：本门把守的闸之后不得有已宣称完成的任务。"""
    gates = {name: [str(t) for t in holders] for name, holders in graph["gates"].items()}
    violations = gate_crossing_claims(
        issues=issues, states=states, deps=deps, gates=gates, gate_task=_GATE_TASK
    )
    sample = "\n".join(
        f"  Task {v['task']} 在闸 `{v['gate']}`（把守者 {v['holders']}）之后却已 [x]"
        for v in violations[:12]
    )
    assert not violations, (
        f"{len(violations)} 条越门宣称（门现算 "
        f"{sum(len(r) for r in issues.values())} 条 blocking facts）：\n{sample}"
    )


def test_no_evidence_artifact_asserts_a_verified_base_while_the_door_is_blocked(
    issues: dict[str, list[str]],
    evidence_docs: dict[str, Any],
    claim_vocabulary: dict[str, Any],
) -> None:
    """类别 C：门未过时，磁盘上不得有 entry 节点在结构上断言 base 已可用。

    当前实测为**绿**：E 循环 slice 的 `verification_state` 是 `UNVERIFIABLE`（带 6 条
    `unverifiable_reasons`），全量 manifest 的 186 条 entry 里 `adapter_id` 等五个身份
    字段**全部为 null**，capability 只有 `single_onlyoffice`/`single_html`/`unreachable`。
    绿不是因为判据空跑 —— :func:`test_the_evidence_scan_has_a_real_denominator` 锁分母，
    :func:`test_reverse_selfcheck_a_blocked_door_with_a_verified_claim_is_stopped` 与
    :func:`test_reverse_selfcheck_the_evidence_predicate_is_fail_closed_on_unknown_states`
    证明它能红。
    """
    claims = evidence_base_claims(docs=evidence_docs, **claim_vocabulary)
    if not door_is_blocked(issues):
        # 门已过 ⇒ 这些断言合法，类别 C 无约束。此时 §2 的两条 xfail 会 XPASS(strict)
        # 报错，提醒清理标记，所以「门过了本条就恒绿」不会变成无人察觉的退化。
        return
    sample = "\n".join(
        f"  [{c['kind']}] {c['doc']}{c['path']} = {c['detail']}（entry={c['entry_id']}）"
        for c in claims[:12]
    )
    assert not claims, (
        f"门未过（{sum(len(r) for r in issues.values())} 条 blocking facts），"
        f"但磁盘上有 {len(claims)} 处 entry 级验收断言：\n{sample}"
    )


# ═══════════════════════════ §3 反向自检：既非恒红也非恒绿 ═══════════════════
#
# 判据全是纯函数，所以「门归零就放行」「门未过 + 下游宣称就拦截」可以直接喂合成输入
# 断言出来 —— 这是本文件不是装饰的证明，也是变异脚本的落点。

#: 合成图里各任务的角色（每一个都是某条判据的**唯一**区分点，删掉哪个就有一条判据失去反证）。
#:
#: ===== ==== ============ ==========================================================
#: 任务  wave 依赖          在自检里承担的角色
#: ===== ==== ============ ==========================================================
#: 10    1    —            门本身
#: 20    2    10           下游 + 宣称方（`[x]`）
#: 21    2    —            **更晚但无关**：wave 在门之后却不依赖门 ⇒ 不是下游
#: 22    2    20           **同 wave 的归属方**：靠「归属方反过来依赖宣称方」判「之后」
#: 30    3    20           更晚 wave **且**依赖宣称方 ⇒ 两支都成立（不具区分力）
#: 31    3    10           更晚 wave **但不**依赖宣称方 ⇒ **只有 wave 序**能判「之后」
#: ===== ==== ============ ==========================================================
#:
#: 🔴 `31` 是变异检验补出来的。初版只有 `30`，于是把 wave 序那一支改成 `if False:`
#: （M05）时自检**没有打红** —— 因为 `30` 依赖 `20`，第二支照样返回 True。
#: 「两支都成立」的样例证不出任何一支承重，这正是「守卫没打红 = 守卫有缺陷」的实例。
_SYNTH_ROLES = ("10", "20", "21", "22", "30", "31")


def _synth() -> tuple[dict[str, list[str]], dict[str, int], dict[str, Any]]:
    """见 :data:`_SYNTH_ROLES`。门 = `10`。"""
    graph = {
        "waves": [
            {"wave": 1, "tasks": ["10"]},
            {"wave": 2, "tasks": ["20", "21", "22"]},
            {"wave": 3, "tasks": ["30", "31"]},
        ],
        "dependencies": {
            "10": [],
            "20": ["10"],
            "21": [],
            "22": ["20"],
            "30": ["20"],
            "31": ["10"],
        },
        # 闸只由 `10` 把守 ⇒ 闸后 = 闭包含 10 的任务（20/22/30/31）。把守者自己不在闸后。
        "gates": {"synthetic_bulk": ["10"]},
    }
    deps = {str(k): [str(v) for v in vs] for k, vs in graph["dependencies"].items()}
    assert set(deps) == set(_SYNTH_ROLES), "合成图与角色表脱节"
    return deps, wave_index(graph), graph


#: 合成场景的勾选态：只有门与 `20`/`21` 标 `[x]`（`21` 不是下游，用来证明它不被误报）。
_SYNTH_STATES = {"10": "x", "20": "x", "21": "x", "22": " ", "30": " ", "31": " "}


def test_reverse_selfcheck_closure_is_transitive() -> None:
    """闭包必须传递：`30 → 20 → 10`，`10` 要出现在 `30` 的闭包里。"""
    deps, _, _ = _synth()
    assert dependency_closure(deps, "30") == {"20", "10"}, (
        f"闭包不传递，实际={sorted(dependency_closure(deps, '30'))} —— "
        "只看直接依赖会漏掉全部间接下游（真实图里 Task 27 就是经 26 才够到 20 的）"
    )


def test_reverse_selfcheck_an_owner_in_the_same_wave_is_not_scheduled_after() -> None:
    """「排在之后」的两支必须**各自**承重，且同 wave 互不依赖时不成立（防恒红）。"""
    deps, waves, _ = _synth()

    assert not owner_is_scheduled_after(
        owner="21", claimant="20", waves=waves, deps=deps
    ), "同 wave 无依赖关系却被判成「排在之后」⇒ 类别 A 会恒红"
    assert not owner_is_scheduled_after(
        owner="20", claimant="20", waves=waves, deps=deps
    ), "自己欠自己的账被判成「排在之后」⇒ 归属方就是宣称方时会重复报"

    # 只有 wave 序能判的样例：`31` 在更晚 wave 且**不**依赖 `20`。
    assert "20" not in dependency_closure(deps, "31"), "自检前提被破坏：31 不应依赖 20"
    assert owner_is_scheduled_after(owner="31", claimant="20", waves=waves, deps=deps), (
        "更晚 wave 但不依赖宣称方的归属方没被判成「排在之后」⇒ wave 序那一支不承重。"
        "真实图里 200 条违规全部是这一支（Task 74/71 在 Wave 7，且都不依赖 Task 25–47）"
    )

    # 只有依赖序能判的样例：`22` 与 `20` 同 wave，但 `22` 依赖 `20`。
    assert waves["22"] == waves["20"], "自检前提被破坏：22 应与 20 同 wave"
    assert owner_is_scheduled_after(owner="22", claimant="20", waves=waves, deps=deps), (
        "同 wave 但反过来依赖宣称方的归属方没被判成「排在之后」⇒ 依赖序那一支不承重"
    )


def test_reverse_selfcheck_a_green_door_lets_every_claim_through() -> None:
    """场景一：门归零 ⇒ 三类判据全部放行（即使下游全标 `[x]`、evidence 满是 VERIFIED）。"""
    deps, waves, graph = _synth()
    green = {"unadjudicated_writer": [], "multi_resolver": []}
    homing = {"unadjudicated_writer": "31", "multi_resolver": "31"}
    states = dict.fromkeys(_SYNTH_ROLES, "x")  # 全部宣称完成，门归零时仍必须放行
    assert not door_is_blocked(green), "全零 issue map 被判「未过」"
    assert not cross_wave_base_claims(
        issues=green,
        homing=homing,
        states=states,
        waves=waves,
        deps=deps,
        gate_task="10",
    ), "门归零时类别 A 仍报违规 ⇒ 恒红"
    assert not gate_crossing_claims(
        issues=green,
        states=states,
        deps=deps,
        gates={k: list(map(str, v)) for k, v in graph["gates"].items()},
        gate_task="10",
    ), "门归零时类别 B 仍报违规 ⇒ 恒红"
    docs = {
        "synthetic.json": {
            "independent_entries": [
                {
                    "entry_id": "xlsx/synthetic",
                    "capability": "bidirectional",
                    "adapter_id": "synthetic.adapter",
                    "evidence": {"verification_state": "VERIFIED"},
                }
            ]
        }
    }
    claims = evidence_base_claims(
        docs=docs,
        evidence_field="verification_state",
        cannot_verify_state="UNVERIFIABLE",
        bidirectional_token="bidirectional",
        identity_fields=("adapter_id",),
    )
    assert claims, "合成的 VERIFIED entry 没被识别成断言 ⇒ 类别 C 恒绿"
    # 类别 C 的约束条件是「门未过」，门归零时上面这些断言全部合法。
    assert not door_is_blocked(green)


def test_reverse_selfcheck_a_blocked_door_with_a_verified_claim_is_stopped() -> None:
    """场景二：门未过 + 下游 `[x]` + evidence 宣称 VERIFIED ⇒ 三类判据全部拦截。"""
    deps, waves, graph = _synth()
    blocked = {"unadjudicated_writer": ["w1", "w2"], "multi_resolver": []}
    # 归属方 `31` 在更晚 wave 且不依赖宣称方 —— 与真实形态同构（Task 74/71 在 Wave 7）
    homing = {"unadjudicated_writer": "31", "multi_resolver": "31"}
    states = dict(_SYNTH_STATES)

    assert door_is_blocked(blocked), "非空 issue map 没被判「未过」"

    a = cross_wave_base_claims(
        issues=blocked,
        homing=homing,
        states=states,
        waves=waves,
        deps=deps,
        gate_task="10",
    )
    assert a, "门未过 + 下游 [x] + 归属方在更晚 wave，类别 A 却放行 ⇒ 守卫恒绿"
    assert {v["task"] for v in a} == {"20"}, (
        f"类别 A 报出的任务集不对：{sorted({v['task'] for v in a})} —— "
        "`21` 与门无依赖关系（不是下游），`22`/`30`/`31` 未标 [x]（没宣称），都不该被报"
    )
    assert {v["kind"] for v in a} == {_KIND_OWNER_LATER}

    b = gate_crossing_claims(
        issues=blocked,
        states=states,
        deps=deps,
        gates={k: list(map(str, v)) for k, v in graph["gates"].items()},
        gate_task="10",
    )
    assert {v["task"] for v in b} == {"20"}, (
        f"类别 B 报出的任务集不对：{sorted({v['task'] for v in b})} —— "
        "闸 `synthetic_bulk` 由 10 把守，闸后是 20/22/30/31，其中只有 20 标了 [x]"
    )

    docs = {
        "synthetic.json": {
            "independent_entries": [
                {
                    "entry_id": "xlsx/synthetic",
                    "evidence": {"verification_state": "VERIFIED"},
                }
            ]
        }
    }
    c = evidence_base_claims(
        docs=docs,
        evidence_field="verification_state",
        cannot_verify_state="UNVERIFIABLE",
        bidirectional_token="bidirectional",
        identity_fields=("adapter_id",),
    )
    assert [x["kind"] for x in c] == [_KIND_EV_VERIFIED], (
        f"门未过时 evidence 的 VERIFIED 断言没被拦下：{c}"
    )


def test_reverse_selfcheck_the_gate_owner_debt_is_also_a_claim_blocker() -> None:
    """归属就是门自己的准则非零时，下游 `[x]` 同样被拦（instruction 的字面读法）。"""
    deps, waves, _ = _synth()
    blocked = {"missing_required_domain": ["row"]}
    homing = {"missing_required_domain": "10"}
    states = dict(_SYNTH_STATES)
    violations = cross_wave_base_claims(
        issues=blocked,
        homing=homing,
        states=states,
        waves=waves,
        deps=deps,
        gate_task="10",
    )
    assert [v["kind"] for v in violations] == [_KIND_GATE_OWNER_OPEN], (
        f"门自有准则未归零却没拦下游宣称：{violations} —— "
        "「已移交的不该让门背锅」不等于「门自己的也不用管」"
    )


def test_reverse_selfcheck_an_unchecked_downstream_task_is_not_a_claim() -> None:
    """未勾选的下游任务不算宣称 —— 否则判据变成「有欠账就打红所有下游」的装饰。"""
    deps, waves, _ = _synth()
    blocked = {"unadjudicated_writer": ["w1"]}
    homing = {"unadjudicated_writer": "31"}
    for marker in (" ", "~", "-"):
        states = {**_SYNTH_STATES, "20": marker}
        violations = cross_wave_base_claims(
            issues=blocked,
            homing=homing,
            states=states,
            waves=waves,
            deps=deps,
            gate_task="10",
        )
        assert not violations, (
            f"勾选态 {marker!r} 被当成「宣称完成」：{violations} —— "
            "`~`/`-`/空格恰恰是「没宣称」的写法"
        )


def test_reverse_selfcheck_the_evidence_predicate_is_fail_closed_on_unknown_states() -> None:
    """陌生的验收词一律当断言 —— 判据是「≠ 不可验证」，不是「== VERIFIED」。"""
    kwargs = {
        "evidence_field": "verification_state",
        "cannot_verify_state": "UNVERIFIABLE",
        "bidirectional_token": "bidirectional",
        "identity_fields": ("adapter_id",),
    }
    for word in ("VERIFIED", "CLOSED", "PASSED", "ok", "已闭环"):
        docs = {
            "s.json": {"entry_id": "e", "evidence": {"verification_state": word}}
        }
        claims = evidence_base_claims(docs=docs, **kwargs)
        assert [c["kind"] for c in claims] == [_KIND_EV_VERIFIED], (
            f"验收态 {word!r} 没被当成断言 ⇒ 换个词就能绕过（fail-open）"
        )
    for benign in ("UNVERIFIABLE", "", "   "):
        docs = {
            "s.json": {"entry_id": "e", "evidence": {"verification_state": benign}}
        }
        assert not evidence_base_claims(docs=docs, **kwargs), (
            f"{benign!r} 被当成验收断言 ⇒ 类别 C 恒红"
        )
    assert not evidence_base_claims(
        docs={"s.json": {"entry_id": "e", "evidence": {"review_status": "reviewed"}}},
        **kwargs,
    ), "无关字段被当成验收态 ⇒ 判据没在看字段路径"


def test_reverse_selfcheck_an_identity_field_on_an_entry_is_a_claim() -> None:
    """SR-5：裁 single 的 entry 挂着身份字段即宣称；无 capability 的节点不在规则作用域内。"""
    kwargs = {
        "evidence_field": "verification_state",
        "cannot_verify_state": "UNVERIFIABLE",
        "bidirectional_token": "bidirectional",
        "identity_fields": ("adapter_id", "definition_bundle"),
    }
    claims = evidence_base_claims(
        docs={
            "s.json": {
                "entry_id": "e",
                "capability": "single_onlyoffice",
                "adapter_id": "d2.receivable_detail",
            }
        },
        **kwargs,
    )
    assert [c["kind"] for c in claims] == [_KIND_EV_IDENTITY], (
        f"裁 single 却挂 adapter 没被识别成断言：{claims}"
    )
    assert not evidence_base_claims(
        docs={
            "s.json": {
                "entry_id": "e",
                "capability": "single_onlyoffice",
                "adapter_id": None,
                "definition_bundle": None,
            }
        },
        **kwargs,
    ), "全 null 的身份字段被当成断言 ⇒ 恒红"
    # 🔴 pilot 执行记录（`identity_and_digests.json` / `run_facts.json`）带 entry_id +
    # adapter_id 但**没有 capability** ⇒ SR-5/SR-6 的前提不成立，不得误报。初版就是漏了
    # 这个前提，把四处诚实的未闭环记录判成了「宣称 base 可靠」。
    assert not evidence_base_claims(
        docs={
            "pilot.json": {
                "entry_id": "xlsx/gt-h1-fixed-assets",
                "adapter_id": "h1.disposal_check",
                "capability_enabled": False,
                "finalize_status": "blocked_by_UPSTREAM_DEBT",
            }
        },
        **kwargs,
    ), "无 capability 裁决的 pilot 执行记录被误报 ⇒ 判据越出了 SR-5/SR-6 的作用域"
    # capability 已是 bidirectional 时，身份字段非 null 是 SR-6 的**要求**，不重复报。
    bidi = evidence_base_claims(
        docs={
            "s.json": {
                "entry_id": "e",
                "capability": "bidirectional",
                "adapter_id": "x.y",
            }
        },
        **kwargs,
    )
    assert [c["kind"] for c in bidi] == [_KIND_EV_BIDI], (
        f"capability=bidirectional 时应只报能力断言，实际={[c['kind'] for c in bidi]}"
    )
    # 真实 slice 里 `blocking_preconditions[].blocks == "bidirectional"` 是「它阻断
    # bidirectional」，与 capability 断言相反 —— 判据只认字段路径，故不得命中。
    assert not evidence_base_claims(
        docs={
            "s.json": {
                "entry_id": "e",
                "blocking_preconditions": [{"id": "BP-1", "blocks": "bidirectional"}],
            }
        },
        **kwargs,
    ), "`blocks == bidirectional`（阻断项登记）被读成能力断言 ⇒ 按值匹配的老毛病"
