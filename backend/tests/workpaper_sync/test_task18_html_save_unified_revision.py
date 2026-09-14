# -*- coding: utf-8 -*-
"""Task 18 结构与行为守卫：普通 HTML save 与 orchestrator 迁入统一 revision 域。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 18
Requirements: 2.1, 2.2, 2.12, 3.1, 13.4
Properties: P4（业务版本与 representation generation 正交）/ P54（after-save 失败可
重试）/ P61（所有 writer 进入唯一 revision 域）

═══ 判据取法：三类，各自可被单点变异 falsify ═══

1. **AST 结构判据**（本文件上半）：`wp_html_save` 不再写 `parsed_data['_version']`、
   不再自己 `db.commit()`、乐观锁读的是 `content_revision`。全部落在**赋值/调用节点**
   与**下标常量**上，不是"文件里出现过某个字符串"。
2. **真实执行判据**（本文件下半）：`HtmlOnlyCommitPlan` 对 bidirectional /
   single_onlyoffice 真抛；`commit_html_projection` 的两条 lane 步骤集合互不重叠。
   这些是**否定式承诺**（「bidirectional 不可能走这条 lane」），只能用注入反例证明，
   不能靠短路。
3. **真库行为判据**：一次保存恰一次 revision、状态变化零 revision、after-save 失败
   落 outbox 可重放 —— 在 `test_task18_html_save_unified_revision_pg.py`，因为
   `_TransactionWitness` 的判据是 `pg_current_xact_id()`，mock session 上不可判定。

═══ 为什么"旧路径不可复活"需要单独的守卫 ═══

Task 18 删掉的是三样东西：`parsed_data['_version']` 的读写、`after_save` 里的
`file_version += 1`、以及 router 自己的 `db.commit()`。"代码已经删了"不是判据 ——
把任意一样写回去，如果没有守卫打红，它下一次重构就会回来（本 spec 已经在 Task 16
的收口里遇到过一次：`expected_version` 被删后调用点仍传，直到 TypeError 才暴露）。
所以每一样都有一条**注入即红**的判据，逐条列在
`backend/scripts/diagnose/mutate_task18_html_save_unified_revision_guards.py`。
"""
from __future__ import annotations

import ast
import os
import sys
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_APP = _BACKEND / "app"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_HTML_SAVE = _APP / "routers" / "wp_html_save.py"
_ORCHESTRATOR = _APP / "services" / "workpaper_save_orchestrator.py"
_CONTENT_MUTATION = _APP / "services" / "workpaper_sync" / "content_mutation.py"

#: 本 spec 判为「第二真源」的版本键。它们出现在 `parsed_data` 下标赋值里就是回归。
_FORBIDDEN_PARSED_DATA_VERSION_KEYS = frozenset({"_version", "content_revision", "file_version"})


# ─── AST 工具（与 task16 守卫同形态，刻意不跨文件 import 私有 helper）─────────


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _iter_functions(tree: ast.AST):
    stack: list[tuple[str, ast.AST]] = [("", tree)]
    while stack:
        prefix, parent = stack.pop()
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                yield qualname, child
                stack.append((f"{qualname}.", child))
            elif isinstance(child, ast.ClassDef):
                stack.append((f"{prefix}{child.name}.", child))
            else:
                stack.append((prefix, child))


def _find_function(tree: ast.AST, qualname: str) -> ast.AST:
    for name, node in _iter_functions(tree):
        if name == qualname:
            return node
    raise AssertionError(f"AST 里找不到 {qualname}（重命名了？守卫必须跟着改）")


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    if isinstance(node, ast.Subscript):
        return _dotted(node.value)
    return ""


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


# ═══════════════════════════════════════════════════════════════════════════
# 一、`_version` / `file_version` 跨域被拆掉，且不可复活
# ═══════════════════════════════════════════════════════════════════════════


def test_html_save_never_writes_the_parsed_data_version() -> None:
    """**Validates: Requirements 2.1**

    Requirement 2.1 原文：`parsed_data._version` 「不得推进或充当跨通道同步版本」。

    判据是 ``parsed_data[<key>] = ...`` 这类**下标赋值节点**，因此：

    * 把 `parsed_data["_version"] = new` 写回去 ⇒ 红；
    * 改成 `parsed_data.setdefault("_version", n)` 或 `parsed_data.update(...)` 也红
      （下面那条 call 判据接住）；
    * 只是**读**存量脏数据（比如日志里打出来）不红 —— 存量键保持原值是刻意的，
      Requirement 2.1 禁的是"推进/充当版本"，不是"必须删除历史字段"。
    """
    tree = _parse(_HTML_SAVE)
    offenders: list[str] = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            if not isinstance(target, ast.Subscript):
                continue
            key = target.slice
            if (
                isinstance(key, ast.Constant)
                and key.value in _FORBIDDEN_PARSED_DATA_VERSION_KEYS
                and "parsed_data" in _dotted(target)
            ):
                offenders.append(f"parsed_data[{key.value!r}]@{target.lineno}")
    assert offenders == [], (
        f"wp_html_save 又开始写 parsed_data 里的版本键: {offenders} —— 那是第二个真源，"
        "与 working_paper.content_revision 必然漂移（Requirement 2.1）"
    )

    # 同一条禁令的另一种写法：setdefault / update 也不许把版本键塞回去。
    for call in _calls(tree):
        dotted = _dotted(call.func)
        if not dotted.endswith(("setdefault", "update")) or "parsed_data" not in dotted:
            continue
        literals = {
            arg.value
            for arg in call.args
            if isinstance(arg, ast.Constant)
        } | {
            keyword.arg
            for keyword in call.keywords
            if keyword.arg is not None
        }
        clash = literals & _FORBIDDEN_PARSED_DATA_VERSION_KEYS
        assert not clash, f"{dotted}(行 {call.lineno}) 把版本键塞回 parsed_data: {clash}"


def test_html_save_reads_the_business_revision_as_its_optimistic_lock() -> None:
    """**Validates: Requirements 2.1, 2.2**

    上一条只证明"不再写 `_version`"。单有它是**不够的**：把整段乐观锁删掉也满足
    （否定式承诺可以靠删代码满足）。所以这条钉住正面形态 —— `server_version` 必须
    从 ``working_paper.content_revision`` 取。

    判据是赋值右侧的取值形态，不是"文件里出现过 content_revision"：后者被本文件里
    好几处注释与 payload 键满足，等于没测。
    """
    fn = _find_function(_parse(_HTML_SAVE), "save_html_data")
    sources: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "server_version"
            for target in targets
        ):
            continue
        assert node.value is not None
        sources.append(ast.dump(node.value))

    assert len(sources) == 1, f"save_html_data 应恰有一处 server_version 赋值，实得 {len(sources)}"
    dumped = sources[0]
    assert "content_revision" in dumped, (
        "乐观锁比对目标必须是 working_paper.content_revision（唯一 business revision 域）"
    )
    for forbidden in ("_version", "file_version"):
        assert f"'{forbidden}'" not in dumped, (
            f"server_version 又从 {forbidden} 取值 —— 跨域比较必然造假冲突"
        )


def test_html_save_owns_no_direct_commit() -> None:
    """**Validates: Requirements 2.2**

    Requirement 2.2：所有业务内容 writer 经统一入口提交，「任何绕过入口的 writer
    SHALL 被清册与 CI 阻断」。落地形态就是 router 自己**一个** ``db.commit()`` 都
    没有 —— 那笔事务的唯一提交出口在 ``ContentMutationService`` 里。

    这条同时是 `test_task16_durable_outbox_wiring.py` 放宽 `_CONTENT_COMMIT_LEAVES`
    的补偿：那边允许把 content commit 认成 ``commit_html_projection``，这边保证
    router 没有偷偷留一个裸 commit。
    """
    tree = _parse(_HTML_SAVE)
    direct = [
        f"{_dotted(call.func)}@{call.lineno}"
        for call in _calls(tree)
        if _dotted(call.func) in ("db.commit", "session.commit", "self._session.commit")
    ]
    assert direct == [], (
        f"wp_html_save 自己提交了事务: {direct} —— 业务内容的唯一提交出口是 "
        "ContentMutationService.commit_html_projection()（Requirement 2.2 / Property 61）"
    )


def test_html_save_routes_the_business_content_through_the_unified_service() -> None:
    """**Validates: Requirements 2.2**

    上一条是否定式的（"没有裸 commit"），把整个提交删掉也满足。这条钉正面接线：
    stage 与 commit 各恰一次，且 stage 在 commit **之前**（staged artifact 协议 ——
    文件先耐久，数据库事务后开）。
    """
    fn = _find_function(_parse(_HTML_SAVE), "save_html_data")
    stage_lines = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "stage_html_projection"
    ]
    commit_lines = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_html_projection"
    ]
    assert len(stage_lines) == 1, f"stage_html_projection 应恰一处，实得 {stage_lines}"
    assert len(commit_lines) == 1, (
        f"commit_html_projection 应恰一处，实得 {commit_lines} —— 两次就是两个 revision"
    )
    assert stage_lines[0] < commit_lines[0], (
        f"stage(行 {stage_lines[0]}) 必须早于 commit(行 {commit_lines[0]})：Requirement 2.4 "
        "要求 artifact 先耐久校验，再开那个短数据库事务写 pointer"
    )


def test_after_save_receives_the_business_revision_read_only() -> None:
    """**Validates: Requirements 2.12**

    `after_save` 的 `content_revision` 参数是只读的。这条断言 HTML save 真的把本次
    预定 revision 传进去了 —— 不传的话审计日志与耐久 payload 里的版本会是 None，
    下游"按返回的新版本刷新"就没有依据（Requirement 4.5 的同类判据）。
    """
    fn = _find_function(_parse(_HTML_SAVE), "save_html_data")
    calls = [
        call
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "after_save"
    ]
    assert len(calls) == 1, f"wp_html_save 应恰有一处 after_save 调用，实得 {len(calls)}"
    keywords = {keyword.arg: keyword for keyword in calls[0].keywords}
    assert "content_revision" in keywords, sorted(keywords)
    assert "expected_version" not in keywords, (
        "expected_version 已删除：它比较的是内存里的 wp.file_version，不是乐观锁"
    )
    passed = ast.dump(keywords["content_revision"].value)
    assert "target_revision" in passed, (
        "content_revision 必须传本次 commit 预定的 target_revision，"
        f"实得 {ast.unparse(keywords['content_revision'].value)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 二、两条 lane 的必需步骤互不重叠（Property 4 / Requirement 3.1）
# ═══════════════════════════════════════════════════════════════════════════


def test_the_two_lanes_have_disjoint_required_step_tuples() -> None:
    """**Validates: Requirements 3.1**

    html-only lane 必须有**自己**的必需步骤元组。若它复用 bidirectional 的
    `CONTENT_COMMIT_STEPS` 再"跳过 representation"，那 bidirectional 那条
    「representation 必须同事务写」的判据就多出一个可绕过分支：只要声明成 html-only，
    representation 缺失就不再打红。
    """
    from app.services.workpaper_sync.content_mutation import (
        CONTENT_COMMIT_STEPS,
        HTML_ONLY_COMMIT_STEPS,
    )

    assert "representation" in CONTENT_COMMIT_STEPS
    assert "entry_pointer" in CONTENT_COMMIT_STEPS
    assert "representation" not in HTML_ONLY_COMMIT_STEPS, (
        "single_html entry 没有 OO representation —— 凭空造一个空白 artifact 正是 "
        "Requirement 3.9 禁止的"
    )
    assert "entry_pointer" not in HTML_ONLY_COMMIT_STEPS
    # 但两条 lane 都必须推进 revision 并入队 outbox（否则就不是一次业务内容应用）。
    for step in ("revision", "content_version", "outbox"):
        assert step in CONTENT_COMMIT_STEPS
        assert step in HTML_ONLY_COMMIT_STEPS
    assert HTML_ONLY_COMMIT_STEPS != CONTENT_COMMIT_STEPS


def test_html_only_lane_bumps_the_revision_exactly_once_in_source() -> None:
    """**Validates: Requirements 2.1**

    「恰一次」的真库行为判据在 `_pg.py`；这条是**结构**判据，防的是另一种回归：
    有人在 lane 里加第二处 `bump_content_revision(` 或第二处 `commit_once(`。
    """
    fn = _find_function(
        _parse(_CONTENT_MUTATION), "ContentMutationService.commit_html_projection"
    )
    bumps = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "bump_content_revision"
    ]
    commits = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] in ("commit_once", "commit")
    ]
    assert len(bumps) == 1, f"html-only lane 的 revision CAS 应恰一处，实得 {bumps}"
    assert len(commits) == 1, f"html-only lane 应恰一次提交，实得 {commits}"

    # 反向锚：lane 不得自己写 representation / entry pointer（那会造一个空白 OO 指针）。
    for forbidden in ("create_representation", "set_entry_pointer", "finalize_candidate"):
        assert not [
            call
            for call in _calls(fn)
            if _dotted(call.func).rsplit(".", 1)[-1] == forbidden
        ], f"html-only lane 不得调 {forbidden}（Requirement 3.9）"


def test_the_database_fact_check_runs_before_the_revision_cas() -> None:
    """**Validates: Requirements 3.1**

    `plan.capability` 是调用方声明（可以写错、可以过期）；
    `_assert_entry_has_no_representation` 查的是数据库事实（该 entry 是否已有 current
    representation pointer）。两条判据来源不同，必须**都在**，而且 DB 事实检查要跑在
    revision CAS **之前** —— 跑在之后意味着「已经推进了版本才发现不该走这条 lane」，
    回滚虽然能兜住，但 artifact 已经按错的 revision 命名发布了。
    """
    fn = _find_function(
        _parse(_CONTENT_MUTATION), "ContentMutationService.commit_html_projection"
    )
    guard_lines = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "_assert_entry_has_no_representation"
    ]
    cas_lines = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "bump_content_revision"
    ]
    assert len(guard_lines) == 1, (
        f"缺少数据库事实判据（_assert_entry_has_no_representation），实得 {guard_lines} —— "
        "只留 capability 声明这一条，某个 entry 日后真被接上 OO 就会静默让 HTML/OO 分叉"
    )
    assert cas_lines, "lane 必须做 revision CAS"
    assert guard_lines[0] < min(cas_lines), (
        f"DB 事实判据(行 {guard_lines[0]}) 必须早于 revision CAS(行 {cas_lines})"
    )

    # 判据本体必须真查那张表，而不是恒返回 0（那就是 fail-open）。
    checker = _find_function(
        _parse(_CONTENT_MUTATION),
        "ContentMutationService._assert_entry_has_no_representation",
    )
    names = {_dotted(node) for node in ast.walk(checker) if isinstance(node, ast.Name)}
    assert "WorkpaperSyncEntryState" in names, (
        "判据必须查 working_paper_sync_entry_state（entry 级 current representation "
        f"pointer），实得引用 {sorted(names)}"
    )
    raises = [
        node
        for node in ast.walk(checker)
        if isinstance(node, ast.Raise)
        and node.exc is not None
        and _dotted(node.exc).endswith("HtmlOnlyEntryHasRepresentationError")
    ]
    assert raises, "查到 representation 必须抛专属异常，不得只记日志"


# ═══════════════════════════════════════════════════════════════════════════
# 三、真实执行：bidirectional 不可能走 html-only lane
# ═══════════════════════════════════════════════════════════════════════════


def _plan(capability) -> object:
    from app.services.workpaper_sync.content_mutation import HtmlOnlyCommitPlan

    return HtmlOnlyCommitPlan(
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="html-only:D2",
        expected_revision=3,
        capability=capability,
        sheet_name="审定表D2-1",
        schema_version="v2025-R5",
    )


#: capability → 期望的拒绝 `error_code`。**两条拒绝各自一个码**，因为它们是两个不同的
#: 判断：「bidirectional 必须走 representation lane」与「这条 lane 只服务 single_html」。
#:
#: 🔴 合成一个码会让第一条判据变成不可达分支：短路掉 `if capability is
#: Capability.bidirectional` 之后，bidirectional 会被第二个 `if` 接住并抛出**同样的**
#: 码，于是守卫照样绿。本任务变异检验 M10 首轮实测到这一点（GREEN → 归因为守卫缺陷 →
#: 生产拆成两个异常类型）。
_REFUSAL_CODES = {
    "bidirectional": "bidirectional_requires_representation_lane",
    "single_onlyoffice": "html_only_lane_capability_mismatch",
    "unreachable": "html_only_lane_capability_mismatch",
}


@pytest.mark.parametrize("capability_value", sorted(_REFUSAL_CODES))
def test_only_single_html_may_use_the_projection_only_lane(capability_value: str) -> None:
    """**Validates: Requirements 3.1**

    否定式承诺「bidirectional flush 不得先提交 projection-only revision」只能靠
    **注入反例**证明。这里就是注入：拿 bidirectional / single_onlyoffice /
    unreachable 去构造 plan，必须抛，**且抛出各自那条拒绝的码**。
    """
    from app.services.workpaper_sync.content_mutation import ContentMutationError
    from app.services.workpaper_sync.entry_profile import Capability

    with pytest.raises(ContentMutationError) as exc:
        _plan(Capability(capability_value))
    assert exc.value.error_code == _REFUSAL_CODES[capability_value], (
        f"{capability_value} 走的拒绝分支不对：实得 {exc.value.error_code}。"
        "两条拒绝理由不同，共用一个码会让其中一条变成不可达分支"
    )


def test_single_html_plan_is_accepted_and_targets_exactly_one_revision() -> None:
    """正面锚：上一条只证明"某些 capability 被拒"，把构造函数改成恒抛也满足它。"""
    from app.services.workpaper_sync.entry_profile import Capability
    from app.services.workpaper_sync.models import AuthorityModel

    plan = _plan(Capability.single_html)
    assert plan.target_revision == plan.expected_revision + 1
    assert plan.authority_model is AuthorityModel.projection_contract


def test_plan_accepts_the_capability_as_a_plain_string_too() -> None:
    """调用方从 manifest 读到的是字符串；构造点必须归一，不能静默接受一个裸 str。

    如果 `__post_init__` 不做 `Capability(...)` 归一，`capability is
    Capability.bidirectional` 对字符串 `"bidirectional"` 恒为 False ⇒ 整条禁令静默
    失效（`Capability` 是 `str` Enum，`==` 会通过但 `is` 不会）。
    """
    from app.services.workpaper_sync.content_mutation import (
        RepresentationLaneRequiredError,
    )
    from app.services.workpaper_sync.entry_profile import Capability

    assert _plan("single_html").capability is Capability.single_html
    with pytest.raises(RepresentationLaneRequiredError) as exc:
        _plan("bidirectional")
    assert exc.value.error_code == "bidirectional_requires_representation_lane"


def test_html_only_entry_id_is_namespaced_and_never_empty() -> None:
    """**Validates: Requirements 2.3**

    V151 的 `ck_wpssi_entry_non_empty` 不接受空串；`wp_index` 缺行时必须退回 wp_id。
    """
    from app.services.workpaper_sync.content_mutation import (
        HTML_ONLY_ENTRY_PREFIX,
        html_only_entry_id,
    )

    wp_id = uuid.uuid4()
    assert html_only_entry_id(wp_code="D2", wp_id=wp_id) == f"{HTML_ONLY_ENTRY_PREFIX}D2"
    for blank in (None, "", "   "):
        entry = html_only_entry_id(wp_code=blank, wp_id=wp_id)
        assert entry == f"{HTML_ONLY_ENTRY_PREFIX}{wp_id}"
        assert entry.strip() == entry and len(entry.strip()) > 0
    # V151 的列宽是 VARCHAR(200)
    assert len(html_only_entry_id(wp_code="X" * 500, wp_id=wp_id)) <= 200


# ═══════════════════════════════════════════════════════════════════════════
# 四、orchestrator 异常进 outbox retry，不被 warning 吞掉（Property 54）
# ═══════════════════════════════════════════════════════════════════════════


def test_html_save_does_not_swallow_the_after_save_failure() -> None:
    """**Validates: Requirements 13.4**

    Property 54 的**接线侧**判据：`after_save` 失败必须放出去让整笔保存回滚，
    客户端可重试；耐久行随之回滚，不会留下"内容没写但事件已入队"的半成功态。

    行为侧（注入失败后 outbox 为 failed/pending 并可重放成功）在
    `test_task16_durable_outbox_pg.py` 与 `_pg.py` 的场景里。
    """
    tree = _parse(_HTML_SAVE)
    swallowing: list[tuple[str, int]] = []
    for qualname, fn in _iter_functions(tree):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try) or not node.handlers:
                continue
            wraps_after_save = any(
                isinstance(inner, ast.Call)
                and _dotted(inner.func).rsplit(".", 1)[-1] == "after_save"
                for statement in node.body
                for inner in ast.walk(statement)
            )
            if not wraps_after_save:
                continue
            reraises = any(
                isinstance(inner, ast.Raise)
                for handler in node.handlers
                for inner in ast.walk(handler)
            )
            if not reraises:
                swallowing.append((qualname, node.lineno))
    assert swallowing == [], (
        f"wp_html_save 把 after_save 包在没有 raise 的 try 里: {swallowing} —— "
        "Requirement 13.4 禁止 best-effort warning 后永久丢失"
    )


def test_the_revision_conflict_is_translated_not_swallowed() -> None:
    """**Validates: Requirements 13.4**

    CAS 冲突必须变成 409（用户可行动），而不是被 `except Exception` 吞成"保存成功"。
    判据：包住 `commit_html_projection` 的那个 `try` 只捕获 `RevisionConflictError`，
    且 handler 里 `raise` 的是 `HTTPException`。
    """
    fn = _find_function(_parse(_HTML_SAVE), "save_html_data")
    found = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try) or not node.handlers:
            continue
        if not any(
            isinstance(inner, ast.Call)
            and _dotted(inner.func).rsplit(".", 1)[-1] == "commit_html_projection"
            for statement in node.body
            for inner in ast.walk(statement)
        ):
            continue
        found = True
        caught = {
            _dotted(handler.type) if handler.type is not None else "<bare>"
            for handler in node.handlers
        }
        assert caught == {
            "RevisionConflictError",
            "HtmlOnlyEntryHasRepresentationError",
        }, (
            f"只许捕获这两个精确异常，实得 {sorted(caught)} —— 宽泛 except 会把"
            "「artifact 发布失败」「事务分裂」一起吞成 409，用户看到的错误原因会归错类"
        )
        raised = {
            _dotted(inner.exc)
            for handler in node.handlers
            for inner in ast.walk(handler)
            if isinstance(inner, ast.Raise) and inner.exc is not None
        }
        assert raised == {"HTTPException"}, sorted(raised)
    assert found, "commit_html_projection 没有被 RevisionConflictError 的 try 包住"
