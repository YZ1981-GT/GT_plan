# -*- coding: utf-8 -*-
"""Task 16 接线与结构守卫：facade 复用、提交顺序、去 best-effort、重放零版本移动。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 16
Requirements: 2.12, 13.1, 13.2, 13.4
Properties: P52 / P53（写入侧）/ P54

═══ 判据取法 ═══

全部走 **AST 或真实执行**，不做"字符串是否出现"式检查：

* "``publish_pending`` 在 ``commit`` 之后"用同一函数体内的**语句行号次序**判定，
  把调用挪到 commit 前面就会红；只 grep 名字则挪不挪都绿。
* "``after_save`` 不再在事务内发布"判的是函数体内**有没有 publish 调用节点**，
  改成别的别名照样红。
* "facade 不复制 DLQ 逻辑"判的是 ``outbox.py`` 里**没有** ``EventOutboxDLQ`` 构造节点，
  同时 ``replay_pending`` 体内**有**对旧 service 的调用节点。
* Property 53 的写入侧用**真实调用** ``_persist_to_stream``（注入假 Redis 捕获 XADD 的
  字段字典），再把捕获到的条目喂回 ``deserialize_payload_from_stream`` 比对 —— 只测纯
  函数的话，写入侧漏字段（也就是原缺陷本身）不会被发现。
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_APP = _BACKEND / "app"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_ORCHESTRATOR = _APP / "services" / "workpaper_save_orchestrator.py"
_FACADE = _APP / "services" / "workpaper_sync" / "outbox.py"
_LEGACY_SERVICE = _APP / "services" / "import_event_outbox_service.py"

#: 提交 ``after_save`` 那笔事务、因此必须在自己 commit 之后发布事件的模块。
#: ``snapshot_writer`` 自身不 commit（见 test_snapshot_writer_does_not_own_a_commit），
#: 它的两个 router 才是提交方。
_PUBLISH_SITES = {
    "app/routers/wp_html_save.py",
    "app/routers/wp_editor_router.py",
    "app/routers/wp_onlyoffice_router.py",
    "app/routers/custom_query.py",
    "app/routers/custom_query_writeback.py",
}

#: 允许调用 ``after_save`` 的生产模块。新增第五个调用方必须同时补一处发布接线，
#: 因此这个集合固定住 —— 多出来就红。
_AFTER_SAVE_CALLERS = {
    "app/routers/wp_html_save.py",
    "app/routers/wp_editor_router.py",
    "app/routers/wp_onlyoffice_router.py",
    "app/services/custom_query/snapshot_writer.py",
}

_VERSION_ATTRS = {"file_version", "content_revision"}
_PARSED_DATA_VERSION_KEYS = {"_version", "schema_version", "content_revision", "file_version"}


# ─── AST 工具 ───────────────────────────────────────────────────────────────


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _iter_functions(tree: ast.AST):
    """产出 ``(qualname, node)``，含嵌套函数与方法。"""
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


def _own_nodes(function: ast.AST):
    """只产出属于本函数的节点，跳过嵌套函数（它们是独立单元）。"""
    stack: list[ast.AST] = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


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


def _call_lines(tree_or_fn: ast.AST, leaf: str, *, own_only: bool = False) -> list[int]:
    nodes = _own_nodes(tree_or_fn) if own_only else ast.walk(tree_or_fn)
    return sorted(
        node.lineno
        for node in nodes
        if isinstance(node, ast.Call) and _dotted(node.func).rsplit(".", 1)[-1] == leaf
    )


def _version_writes(scope: ast.AST) -> list[str]:
    """收集对 version 字段的**赋值**（属性、AugAssign、parsed_data['_version'] 下标）。"""
    hits: list[str] = []

    def _record(target: ast.AST) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                _record(element)
        elif isinstance(target, ast.Attribute) and target.attr in _VERSION_ATTRS:
            hits.append(f"{_dotted(target)}@{target.lineno}")
        elif isinstance(target, ast.Subscript):
            key = target.slice
            if (
                isinstance(key, ast.Constant)
                and key.value in _PARSED_DATA_VERSION_KEYS
                and "parsed_data" in _dotted(target)
            ):
                hits.append(f"{_dotted(target)}[{key.value}]@{target.lineno}")

    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _record(target)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            _record(node.target)
    return hits


def _relative(path: Path) -> str:
    return str(path.relative_to(_BACKEND)).replace("\\", "/")


def _production_modules() -> list[Path]:
    return [
        path
        for path in sorted(_APP.rglob("*.py"))
        if "__pycache__" not in path.parts and "migrations" not in path.parts
    ]


# ═══════════════════════════════════════════════════════════════════════════
# after_save 的形状：入队不发布、不吞异常
# ═══════════════════════════════════════════════════════════════════════════


def test_after_save_enqueues_instead_of_publishing_inside_the_transaction() -> None:
    """**Validates: Requirements 13.1**

    Property 52 的核心：事务内只入队，publish 一个都不许有。
    """
    fn = _find_function(_parse(_ORCHESTRATOR), "WorkpaperSaveOrchestrator.after_save")
    assert _call_lines(fn, "enqueue", own_only=True), (
        "after_save 必须调 DurableEventOutboxService.enqueue"
    )
    for forbidden in ("publish", "publish_immediate", "broadcast_raw"):
        assert not _call_lines(fn, forbidden, own_only=True), (
            f"after_save 事务内不许调 {forbidden}（回滚后会留下幽灵事件）"
        )
    # 入队走的是 facade，不是绕过它直接 new 一个 ORM 行。
    dotted = {
        _dotted(node.func)
        for node in _own_nodes(fn)
        if isinstance(node, ast.Call)
    }
    assert any("DurableEventOutboxService.enqueue" in name for name in dotted), dotted
    assert not any("ImportEventOutbox(" in name for name in dotted)


def test_after_save_no_longer_swallows_its_own_side_effects() -> None:
    """**Validates: Requirements 13.4**

    "不得 best-effort warning 后永久丢失"。原实现有两个 bare except 把审计日志与事件
    发布降级成 warning。
    """
    fn = _find_function(_parse(_ORCHESTRATOR), "WorkpaperSaveOrchestrator.after_save")
    handlers = [node for node in _own_nodes(fn) if isinstance(node, ast.ExceptHandler)]
    assert handlers == [], (
        "after_save 体内不该再有 except 分支，行号: "
        f"{[node.lineno for node in handlers]}"
    )


def test_html_save_no_longer_crosses_the_version_domains() -> None:
    """**Validates: Requirements 13.4**

    原实现把 `body.data_version`（parsed_data['_version'] 域）当 `expected_version` 传
    给按 `wp.file_version` 比较的 after_save，必然假冲突并被 except 吞掉，导致四项副
    作用全部静默跳过。判据：这一处调用不再带 `expected_version` 关键字。
    """
    tree = _parse(_APP / "routers" / "wp_html_save.py")
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _dotted(node.func).rsplit(".", 1)[-1] == "after_save"
    ]
    assert len(calls) == 1, f"wp_html_save 应恰有一处 after_save 调用，实得 {len(calls)}"
    keywords = {keyword.arg for keyword in calls[0].keywords}
    assert "expected_version" not in keywords, (
        "expected_version 必须去掉：真正的乐观锁校验在 Step 2b，用的是客户端真正发来的域"
    )
    assert "trigger" in keywords


# ═══════════════════════════════════════════════════════════════════════════
# 提交顺序：publish 只能在 commit 之后
# ═══════════════════════════════════════════════════════════════════════════


def test_after_save_callers_are_exactly_the_adjudicated_four() -> None:
    """**Validates: Requirements 13.1**

    新增第五个 after_save 调用方就必须同时补一处提交后发布接线，所以调用方集合固定。
    """
    found = {
        _relative(path)
        for path in _production_modules()
        if _call_lines(_parse(path), "after_save")
    }
    assert found == _AFTER_SAVE_CALLERS, (
        f"意外多出/少掉 after_save 调用方: 多={found - _AFTER_SAVE_CALLERS} "
        f"少={_AFTER_SAVE_CALLERS - found}"
    )


def test_snapshot_writer_does_not_own_a_commit() -> None:
    """**Validates: Requirements 13.1**

    snapshot_writer 自己不提交，所以它的发布接线必须落在两个 router 上。这条断言把
    "为什么 _PUBLISH_SITES 里是 router 而不是 service"钉住。
    """
    tree = _parse(_APP / "services" / "custom_query" / "snapshot_writer.py")
    assert _call_lines(tree, "commit") == []


#: `after_save` 调用允许被 swallowing `try` 包住的**唯一**模块。
#: design.md「明确拒绝的方案 §8」：文件已耐久保存后给 OnlyOffice 返回非零会让它重发
#: callback，制造重复 delivery 与重复版本。所以 callback 路径必须 ack OO，代价是保留一个
#: except（已从 warning 升到 error + rollback）。真正的失败恢复台账由 Task 22 建立。
_SWALLOW_EXEMPT = {"app/routers/wp_onlyoffice_router.py"}


def _calls_within(statements: list[ast.stmt], target_leaf: str) -> bool:
    """``statements`` 里是否出现对 ``target_leaf`` 的调用。"""
    return any(
        isinstance(inner, ast.Call)
        and _dotted(inner.func).rsplit(".", 1)[-1] == target_leaf
        for statement in statements
        for inner in ast.walk(statement)
    )


def _handlers_around(tree: ast.AST, target_leaf: str) -> list[ast.ExceptHandler]:
    """包住 ``target_leaf`` 调用的那些 ``Try`` 的 ``except`` 分支。"""
    out: list[ast.ExceptHandler] = []
    for _qualname, function in _iter_functions(tree):
        for node in _own_nodes(function):
            if isinstance(node, ast.Try) and node.handlers and _calls_within(
                node.body, target_leaf
            ):
                out.extend(node.handlers)
    return out


def _direct_handler_calls(handlers: list[ast.ExceptHandler]) -> set[str]:
    """handler **直接语句层**的调用点名（不下钻嵌套 ``Try``/``if``）。

    区分"直接"与"walk 到"很重要：豁免分支里既有顶层的 ``logger.error(...)``，也有嵌套
    ``try: await db.rollback() except: logger.error(...)``。若用 walk，把顶层那句从
    ``logger.error`` 改成 ``logger.warning`` 会被嵌套那句顶掉 ⇒ 判据无法被单点变异伪造，
    等于没测（本任务变异检验时实测到这一点）。
    """
    names: set[str] = set()
    for handler in handlers:
        for statement in handler.body:
            if not isinstance(statement, ast.Expr):
                continue
            value = statement.value
            if isinstance(value, ast.Await):
                value = value.value
            if isinstance(value, ast.Call):
                names.add(_dotted(value.func))
    return names


def _walked_handler_calls(handlers: list[ast.ExceptHandler]) -> set[str]:
    """handler 内的**全部**调用点名（含嵌套结构）。"""
    return {
        _dotted(inner.func)
        for handler in handlers
        for inner in ast.walk(handler)
        if isinstance(inner, ast.Call)
    }


@pytest.mark.parametrize("relative", sorted(_AFTER_SAVE_CALLERS))
def test_after_save_call_sites_do_not_swallow_the_durability_failure(relative: str) -> None:
    """**Validates: Requirements 13.4**

    "不得 best-effort warning 后永久丢失"不只管 orchestrator 自身，也管调用点 —— 原来
    4 个调用点全都把 after_save 包在 ``except Exception: logger.warning`` 里，等于把
    orchestrator 内部的加固整体抵消掉。

    规则：after_save 的调用要么根本不被 ``try`` 包住，要么那个 ``try`` 必须有一条会
    ``raise`` 出去的 handler（把耐久失败放出去）。唯一例外是 OO callback（见
    ``_SWALLOW_EXEMPT``），它必须 ack OnlyOffice。
    """
    tree = _parse(_BACKEND / relative)
    swallowing: list[tuple[str, int]] = []
    for qualname, node in _iter_functions(tree):
        for try_node in _own_nodes(node):
            if not isinstance(try_node, ast.Try) or not try_node.handlers:
                continue
            if not _calls_within(try_node.body, "after_save"):
                continue
            reraises = any(
                isinstance(inner, ast.Raise)
                for handler in try_node.handlers
                for inner in ast.walk(handler)
            )
            if not reraises:
                swallowing.append((qualname, try_node.lineno))

    if relative in _SWALLOW_EXEMPT:
        assert swallowing, (
            f"{relative} 必须保留 ack-OO 的 except（design 明确拒绝返回非零）；"
            "去掉它会让 OnlyOffice 重发 callback、制造重复 delivery"
        )
        # 但豁免的代价必须被限定住：那条 handler 的**顶层语句**得有 error 级诊断，
        # 并且要回滚被污染的事务。判据落在 handler 内部的调用节点，不是"文件里出现过
        # logger.error" —— 后者被同文件另外三处 error 日志满足，等于没测。
        handlers = _handlers_around(tree, "after_save")
        direct = _direct_handler_calls(handlers)
        assert "logger.error" in direct, (
            f"ack-OO 的 except 顶层必须记 ERROR（降级成 warning 就看不见了），实得 {sorted(direct)}"
        )
        walked = _walked_handler_calls(handlers)
        assert any(name.endswith("rollback") for name in walked), (
            f"ack-OO 的 except 必须回滚被污染的事务，实得 {sorted(walked)}"
        )
    else:
        assert swallowing == [], (
            f"{relative} 把 after_save 包在没有 raise 的 try 里: {swallowing}"
        )


#: 「content commit 发生在这一行」的调用叶子名。
#:
#: 🔴 Task 18 加入 ``commit_html_projection``：`wp_html_save` 迁入统一 revision 域后
#: **自己不再有 `db.commit()`** —— 那笔事务的唯一提交出口在
#: `ContentMutationService.commit_html_projection()` 里面（Requirement 2.2 的
#: 「统一入口」落地形态）。如果这里只认裸 ``commit``，守卫会因为「router 里没有
#: commit」而红，逼着把 commit 写回 router —— 恰好是本 spec 要消灭的形态。
#:
#: 「router 里一个 `db.commit()` 都没有」这条更强的承诺由
#: `test_task18_html_save_unified_revision.py::test_html_save_owns_no_direct_commit`
#: 单独断言，所以放宽这里不会丢判据。
_CONTENT_COMMIT_LEAVES: tuple[str, ...] = ("commit", "commit_html_projection")


@pytest.mark.parametrize("relative", sorted(_PUBLISH_SITES))
def test_publish_pending_runs_after_the_content_commit(relative: str) -> None:
    """**Validates: Requirements 13.1**

    Property 52：``workpaper.saved`` 只在 content commit 之后发布。判据是同一函数体内
    的语句次序，而不是"文件里出现过 publish_pending"。
    """
    tree = _parse(_BACKEND / relative)
    hosts = [
        (qualname, node)
        for qualname, node in _iter_functions(tree)
        if _call_lines(node, "publish_pending", own_only=True)
    ]
    assert hosts, f"{relative} 缺少 publish_pending 接线"
    for qualname, node in hosts:
        publish_lines = _call_lines(node, "publish_pending", own_only=True)
        commit_lines = sorted(
            line
            for leaf in _CONTENT_COMMIT_LEAVES
            for line in _call_lines(node, leaf, own_only=True)
        )
        assert commit_lines, (
            f"{relative}::{qualname} 有 publish 却没有 content commit"
            f"（认的叶子名: {_CONTENT_COMMIT_LEAVES}）"
        )
        assert min(publish_lines) > min(commit_lines), (
            f"{relative}::{qualname} 的 publish_pending(行 {publish_lines}) "
            f"跑在 content commit(行 {commit_lines}) 之前"
        )


# ═══════════════════════════════════════════════════════════════════════════
# facade 复用而非复制；重放路径零版本移动
# ═══════════════════════════════════════════════════════════════════════════


def test_facade_delegates_replay_and_dlq_to_the_legacy_service() -> None:
    """**Validates: Requirements 13.4**

    design.md §outbox："不新建第二套事件表"、"底层复用现有 ImportEventOutbox/DLQ 能力，
    保留旧 service 作为兼容门面"。判据：facade 里没有 DLQ 行构造，且重放确实委托出去。
    """
    tree = _parse(_FACADE)
    constructed = {
        _dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "EventOutboxDLQ" not in constructed, "facade 不得自己实现 DLQ 升级"
    assert not any(name.endswith("_move_to_dlq") for name in constructed)

    replay = _find_function(tree, "DurableEventOutboxService.replay_pending")
    delegated = {
        _dotted(node.func)
        for node in _own_nodes(replay)
        if isinstance(node, ast.Call)
    }
    assert "ImportEventOutboxService.replay_pending" in delegated, delegated
    # 旧 service 仍在（兼容门面），没有被删掉。
    assert _LEGACY_SERVICE.is_file()
    legacy = _parse(_LEGACY_SERVICE)
    legacy_methods = {name for name, _ in _iter_functions(legacy)}
    for method in ("ImportEventOutboxService.enqueue", "ImportEventOutboxService.replay_pending"):
        assert method in legacy_methods


def test_the_replayable_path_writes_no_version_field() -> None:
    """**Validates: Requirements 2.12**

    "handler 重试不得再次递增 content revision"。重放执行的全部代码就是 facade 与旧
    service 的发布路径，两者整模块都不许出现 version 字段赋值。
    """
    for path in (_FACADE, _LEGACY_SERVICE):
        hits = _version_writes(_parse(path))
        assert hits == [], f"{_relative(path)} 出现了 version 字段赋值: {hits}"


def test_enqueue_only_flushes_and_never_commits() -> None:
    """**Validates: Requirements 13.1**

    入队必须留在调用方事务里。``enqueue`` 体内一旦出现 commit，Property 52 的"回滚时
    无事件"就没了。``publish_pending`` 里的 commit 是合法的（它跑在调用方 commit 之后）。
    """
    tree = _parse(_FACADE)
    enqueue = _find_function(tree, "DurableEventOutboxService.enqueue")
    assert _call_lines(enqueue, "flush", own_only=True)
    assert _call_lines(enqueue, "commit", own_only=True) == []


# ═══════════════════════════════════════════════════════════════════════════
# Property 53 写入侧：真实调用 _persist_to_stream 捕获 XADD 字段
# ═══════════════════════════════════════════════════════════════════════════


class _FakeRedis:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict[str, Any]]] = []

    async def ping(self) -> bool:
        return True

    async def xadd(self, key: str, fields: dict[str, Any], **_kwargs: Any) -> str:
        self.entries.append((key, dict(fields)))
        return "0-1"


def _persist_once() -> tuple[dict[str, Any], Any, Any]:
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services import event_bus as event_bus_module
    import app.core.redis as redis_module

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=2025,
        account_codes=["1001"],
        batch_id=uuid.uuid4(),
        extra={
            "wp_id": str(uuid.uuid4()),
            "revision": 12,
            "operation_id": str(uuid.uuid4()),
            "source": "onlyoffice",
            "adapter_id": "g7.disclosure.listed",
            "artifact_sha256": "c" * 64,
            "__event_id": str(uuid.uuid4()),
        },
    )
    fake = _FakeRedis()
    bus = event_bus_module.EventBus(debounce_ms=0)
    previous = getattr(redis_module, "redis_client", None)
    redis_module.redis_client = fake
    try:
        asyncio.run(bus._persist_to_stream(payload))
    finally:
        redis_module.redis_client = previous
    assert len(fake.entries) == 1, "未写入 Redis Stream（假 Redis 没被调用）"
    return fake.entries[0][1], payload, event_bus_module


def test_persist_to_stream_writes_the_whole_payload() -> None:
    """**Validates: Requirements 13.2**

    Property 53 的修点在写入侧：旧实现只写 event_type/project_id/year/account_codes，
    ``extra`` 与 batch_id 在这一步就蒸发了。
    """
    fields, payload, module = _persist_once()
    assert module._STREAM_PAYLOAD_FIELD in fields, (
        f"XADD 字段缺 payload 载体，实得 {sorted(fields)}"
    )
    # 旧的扁平字段仍在：本次改动前已在流里的条目还要能被读出来。
    for legacy in ("event_type", "project_id", "year", "account_codes"):
        assert legacy in fields

    restored = module.deserialize_payload_from_stream(fields)
    assert restored.extra == payload.extra
    assert restored.batch_id == payload.batch_id
    assert restored.account_codes == payload.account_codes
    assert restored.year == payload.year
    assert restored.project_id == payload.project_id
    assert restored.event_type == payload.event_type


def test_stream_payload_field_is_json_and_self_describing() -> None:
    """**Validates: Requirements 13.2**

    Stream 字段值必须是标量（Redis 只接受 str/bytes/int/float），且解析出来是完整
    payload —— 写成 repr / dict 会在真 Redis 上直接报错。
    """
    fields, payload, module = _persist_once()
    raw = fields[module._STREAM_PAYLOAD_FIELD]
    assert isinstance(raw, str)
    decoded = json.loads(raw)
    assert decoded["extra"]["wp_id"] == payload.extra["wp_id"]
    assert decoded["event_type"] == payload.event_type.value
    assert set(decoded) >= {
        "event_type",
        "project_id",
        "year",
        "account_codes",
        "batch_id",
        "entry_group_id",
        "extra",
    }


class _ReplayRedis(_FakeRedis):
    """只回放一批预置条目的假 Redis（xreadgroup 第二次返回空，避免死循环）。"""

    def __init__(self, messages: list[tuple[str, dict[str, Any]]]) -> None:
        super().__init__()
        self._messages = messages
        self.acked: list[str] = []

    async def xgroup_create(self, *_args: Any, **_kwargs: Any) -> bool:
        return True

    async def xreadgroup(self, *_args: Any, **_kwargs: Any):
        batch, self._messages = self._messages, []
        return [("audit:events", batch)] if batch else []

    async def xack(self, _key: str, _group: str, msg_id: str) -> int:
        self.acked.append(msg_id)
        return 1


def _replay(messages: list[tuple[str, dict[str, Any]]]) -> tuple[dict[str, Any], list[Any], _ReplayRedis]:
    from app.models.audit_platform_schemas import EventType
    from app.services import event_bus as event_bus_module
    import app.core.redis as redis_module

    fake = _ReplayRedis(messages)
    bus = event_bus_module.EventBus(debounce_ms=0)
    seen: list[Any] = []

    async def _collector(payload) -> None:
        seen.append(payload)

    bus.subscribe(EventType.WORKPAPER_SAVED, _collector)
    previous = getattr(redis_module, "redis_client", None)
    redis_module.redis_client = fake
    try:
        asyncio.run(bus.replay_pending_events())
    finally:
        redis_module.redis_client = previous
    return bus.get_replay_report(), seen, fake


def test_replay_restores_the_whole_payload_and_counts_dropped_entries() -> None:
    """**Validates: Requirements 13.2, 13.9**

    Property 53 的 replay 侧：带 payload 载体的条目原样恢复 ``extra``；无法解析的条目
    仍然 ACK（否则 consumer group 队头永久阻塞）但必须单独计数，否则"事件被丢弃"在日志
    与 /metrics 里都不可见。
    """
    from app.services import event_bus as event_bus_module

    fields, payload, module = _persist_once()
    report, seen, fake = _replay(
        [("1-1", fields), ("1-2", {"event_type": "totally.unknown"})]
    )

    assert report["read_count"] == 2
    assert report["success_count"] == 1
    assert report["dropped_unparseable_count"] == 1
    assert report["acked_count"] == 2, "两条都要 ACK，否则队头阻塞"
    assert sorted(fake.acked) == ["1-1", "1-2"]

    assert len(seen) == 1
    assert seen[0].extra == payload.extra, "replay 出来的 extra 必须与写入时逐项相等"
    assert seen[0].batch_id == payload.batch_id

    # 初始 report（首次重放前）也必须有这个键：/metrics 会先读到它。
    assert "dropped_unparseable_count" in event_bus_module.EventBus(
        debounce_ms=0
    ).get_replay_report()


# ═══════════════════════════════════════════════════════════════════════════
# Requirement 13.3：fan-out 闸门的结构判据（行为判据在 _pg.py 的场景 J/K/L）
# ═══════════════════════════════════════════════════════════════════════════


def test_deliver_is_the_only_fanout_site() -> None:
    """**Validates: Requirements 13.3**

    闸门只有在**每一条**派发路径上都生效才有意义。旧实现里 ``publish_one`` 与
    ``replay_pending`` 各自内联了一份 ``publish_immediate``，任何加在其中一处的闸门都会
    被另一处绕过 —— 行为上表现为"重启/重试后下游被刷了两遍"，极难归因。

    判据是 AST 调用节点：两个方法各自**必须**调 ``_deliver``、且**不得**自己直接派发。
    """
    tree = _parse(_LEGACY_SERVICE)
    deliver = _find_function(tree, "ImportEventOutboxService._deliver")
    assert _call_lines(deliver, "publish_immediate", own_only=True), (
        "_deliver 必须是真正派发的那一处"
    )
    for host in (
        "ImportEventOutboxService.publish_one",
        "ImportEventOutboxService.replay_pending",
    ):
        fn = _find_function(tree, host)
        assert _call_lines(fn, "_deliver", own_only=True), f"{host} 必须经 _deliver 派发"
        assert _call_lines(fn, "publish_immediate", own_only=True) == [], (
            f"{host} 绕过 _deliver 直接派发 ⇒ fan-out 闸门在这条路径上失效"
        )


def test_fanout_gate_precedes_the_dispatch_and_is_released_on_failure() -> None:
    """**Validates: Requirements 13.3, 13.4**

    两条次序/结构约束，各自独立可 falsify：

    * 闸门必须在派发**之前**（判据是行号次序）—— 放到之后等于副作用已经做完了才判重；
    * 派发失败必须归还派发权并把异常放出去 —— 否则失败事件被自己的闸门永久挡住，
      正是 Requirement 13.4 禁止的"静默丢失"。
    """
    deliver = _find_function(
        _parse(_LEGACY_SERVICE), "ImportEventOutboxService._deliver"
    )
    gate_lines = _call_lines(deliver, "begin_fanout", own_only=True)
    dispatch_lines = _call_lines(deliver, "publish_immediate", own_only=True)
    assert gate_lines, "_deliver 缺少 begin_fanout 闸门"
    assert dispatch_lines
    assert max(gate_lines) < min(dispatch_lines), (
        f"闸门(行 {gate_lines}) 跑在派发(行 {dispatch_lines}) 之后"
    )

    handlers = [node for node in _own_nodes(deliver) if isinstance(node, ast.ExceptHandler)]
    assert handlers, "_deliver 必须有 except 分支来归还派发权"
    aborts = [
        node.lineno
        for handler in handlers
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and _dotted(node.func).rsplit(".", 1)[-1] == "abort_fanout"
    ]
    assert aborts, "派发失败不归还派发权 ⇒ 重放被闸门挡下，事件永久丢失"
    assert any(
        isinstance(node, ast.Raise)
        for handler in handlers
        for node in ast.walk(handler)
    ), "_deliver 的 except 必须把异常放出去，让调用方落 failed/DLQ"


def test_the_gate_covers_the_two_workpaper_sync_event_types_only() -> None:
    """**Validates: Requirements 13.3**

    闸门范围是**双向**判据：底稿域两个耐久事件必须被管住，导入域必须不受影响
    （``LEDGER_*`` 的重放语义归 ledger-import spec）。

    另外锁死"字符串形态也要认"：``import_event_outbox.event_type`` 是 VARCHAR 列，
    派发口拿到的是 ``str``。若判定写成 ``event_type in GATED_...``（只认枚举），闸门在
    生产里恒为 False —— 整条闸门静默失效而任何 grep 式守卫都会绿。
    """
    from app.models.audit_platform_schemas import EventType
    from app.services.workpaper_sync.outbox import (
        GATED_FANOUT_EVENT_TYPES,
        DurableEventOutboxService,
    )

    assert GATED_FANOUT_EVENT_TYPES == {
        EventType.WORKPAPER_SAVED,
        EventType.WORKPAPER_CONTENT_UPDATED,
    }
    for gated in GATED_FANOUT_EVENT_TYPES:
        assert DurableEventOutboxService.is_fanout_gated(gated)
        assert DurableEventOutboxService.is_fanout_gated(gated.value), (
            f"{gated.value} 的字符串形态（ORM 列里存的就是它）没被认出来"
        )
    for untouched in (
        EventType.LEDGER_DATASET_ACTIVATED,
        EventType.DATA_IMPORTED,
        EventType.REPORTS_UPDATED,
    ):
        assert not DurableEventOutboxService.is_fanout_gated(untouched)
        assert not DurableEventOutboxService.is_fanout_gated(untouched.value)


def test_release_consumption_actually_deletes_the_row() -> None:
    """**Validates: Requirements 13.4**

    归还派发权必须是真的 DELETE。写成 UPDATE 一个"已撤销"标记而唯一索引仍然拦着，
    行为上与不归还完全一样（重放仍被挡下）。判据落在 AST：函数体内有 ``sa.delete``
    且目标是 ``ImportEventConsumption``。
    """
    fn = _find_function(
        _parse(_FACADE), "DurableEventOutboxService.release_consumption"
    )
    deletes = [
        node
        for node in _own_nodes(fn)
        if isinstance(node, ast.Call) and _dotted(node.func).endswith("delete")
    ]
    assert deletes, "release_consumption 没有 DELETE"
    targets = {
        _dotted(arg)
        for node in deletes
        for arg in node.args
    }
    assert "ImportEventConsumption" in targets, targets


def test_the_version_write_is_confined_to_the_pre_commit_half() -> None:
    """**Validates: Requirements 2.12**

    Requirement 2.12 有两半，判据不同：

    * "``after_save()`` 等副作用 SHALL 由提交后可重放 handler 执行" —— 由耐久行 +
      提交后 ``publish_pending`` + fan-out 闸门承担；
    * "handler 重试不得再次递增 content revision" —— 判据是**重放路径零 version 写**
      （见 ``test_the_replayable_path_writes_no_version_field``：重放执行的全部代码就是
      facade 与旧 service，两个模块整模块零 version 赋值）。

    ═══ Task 16 的期望值是 1；Task 18 把它降到 0 ═══

    Task 16 只做到「被重放的那一半不碰 version」，提交前那一半仍然
    ``wp.file_version += 1``，因为当时**还没有替代所有者**：四条生产写路径都靠它。
    Task 18 给出了替代所有者，于是期望值随生产改动一起降到 0：

    * 业务内容版本 = ``working_paper.content_revision``，唯一推进者是
      ``ContentMutationService``（`wp_html_save` 已迁入，其余三条归 Task 19）；
    * 文件生命周期版本 = ``file_version``，所有者是**真正写文件的那三处**
      （`wp_editor_router` 写完 xlsx、`wp_onlyoffice_router` ``write_bytes`` 之后、
      `snapshot_writer` 换掉 xlsx 缓存之后）。

    改期望值在这里是合法的，**因为生产所有者同时搬走了**：三处新的
    ``file_version += 1`` 由 ``test_the_file_lifecycle_version_has_three_named_owners``
    逐处断言，Task 3 的 writer gate 红基线
    （``test_after_save_side_effect_handler_still_moves_a_version``）同批翻面。单独改
    这一个数字而不搬生产，会被那两条立刻打红。
    """
    fn = _find_function(_parse(_ORCHESTRATOR), "WorkpaperSaveOrchestrator.after_save")
    writes = _version_writes(fn)
    assert writes == [], (
        f"after_save 仍在写版本字段: {writes}。它是**共享且可重放**的副作用 handler，"
        "不能是任何版本域的所有者 —— 重放一次就多一个伪版本（Requirement 2.12）"
    )
    # 反向锚：handler 仍然必须入队耐久事件。上一条断言"没有 version 写"是**否定式
    # 承诺**，把整个函数体删空也能满足它 —— 所以必须同时钉住"该做的事还在做"。
    assert _call_lines(fn, "enqueue", own_only=True), "after_save 必须入队耐久事件"


#: `after_save` 的四个调用方里，**真正写文件**的那三条 —— Task 18 把
#: `file_version` 的所有权交还给它们各自。第四个（`wp_html_save`）一个字节都不写盘，
#: 因此必须**零** `file_version` 写（Requirement 2.1）。
#:
#: 判据范围刻意只覆盖这四个模块：`file_version` 在上传 / WOPI / storage / download /
#: structure 等路径上还有别的写入点，那些是 Task 19「迁移上传、WOPI、custom、F2、
#: rollback 与历史恢复 writer」的活。把它们混进来会让本条守卫变成 Task 19 的红基线，
#: 从而在 Task 18 交付时被迫挂红或被迫加豁免 —— 两者都会污染判据。
_FILE_WRITING_AFTER_SAVE_CALLERS = {
    "app/routers/wp_editor_router.py",
    "app/routers/wp_onlyoffice_router.py",
    "app/services/custom_query/snapshot_writer.py",
}


def _file_version_writes(path: Path) -> list[str]:
    return [hit for hit in _version_writes(_parse(path)) if "file_version" in hit]


def test_the_file_lifecycle_version_has_three_named_owners() -> None:
    """**Validates: Requirements 2.1**

    这条是上一条的**配对反证**。"after_save 零 version 写"若只被单向断言，把那一行
    直接删掉、让三条写文件路径的文件版本永久停在旧值，守卫照样绿 —— 那是纯粹的行为
    退化（univer 保存的版本快照名、OO doc_key、前端 ``v{n}`` 全部凝固）。

    所以判据是**双向**的，且落在 ``after_save`` 的四个调用方上：三条写文件的各自
    恰有一处 ``file_version`` 写，`wp_html_save` 与 orchestrator 各自零处。
    """
    for relative in sorted(_FILE_WRITING_AFTER_SAVE_CALLERS):
        hits = _file_version_writes(_BACKEND / relative)
        assert len(hits) == 1, (
            f"{relative} 应恰有一处 file_version 写（它是这条文件生命周期的所有者），"
            f"实得 {hits}"
        )

    for relative in sorted(_AFTER_SAVE_CALLERS - _FILE_WRITING_AFTER_SAVE_CALLERS):
        assert _file_version_writes(_BACKEND / relative) == [], (
            f"{relative} 不写文件，不该推进 file_version"
        )

    assert _file_version_writes(_ORCHESTRATOR) == [], (
        "共享的副作用 handler 不得是 file_version 的所有者"
    )
