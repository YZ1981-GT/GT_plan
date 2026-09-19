# -*- coding: utf-8 -*-
"""Task 35 结构与真实执行守卫：commit 后 content event 接到前端刷新。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 35
Requirements: 11.9, 13.1, 13.2, 13.3, 13.4
Properties: P52（只在 commit 后发布 —— 本文件判"绝不走 debounce publish"这一半）/
            P53（typed replay 逐项保留 payload，含 `extra`）/
            P54（event/刷新失败落可恢复态；DB 侧在 `_pg.py`）

═══ 判据取向 ═══

四类，全部避开"字符串出现过"：

1. **真实执行**：三条 lane 的 payload 构造器**真调一次**，再把 payload 走完
   ``EventPayload → Redis Stream 序列化 → 反序列化 → replay 投影`` 全链，逐键比对。
   改坏任何一环都会红；改个变量名不会假绿。
2. **AST 归属**：``EventType.WORKPAPER_CONTENT_UPDATED`` 只能作为 ``enqueue(...)``
   的实参出现，**不得**出现在 ``publish/publish_immediate/broadcast_raw`` 的实参里
   （AC 11.9 的"不得依赖进程内 commit 前 debounce 事件"后端半边）。分析器带
   **反向自检**：喂一段含违规的源码必须被抓到，否则分析器本身有缺陷。
3. **函数体标识符**：``get_events_since`` 必须引用 ``EVENT_STREAM_KEY`` 与
   ``replay_entry_projection``，且整个 router 文件里不得再出现 ``"events:stream"``
   这个第二真源字面量。
4. **两向锁死**：前端 ``workpaperSyncContentRefresh.ts`` 的必填键清单与事件名，
   与后端常量/三条 lane 的真实 payload 双向比对。前端多要一个键（某条 lane 不给）
   或后端漏给一个键，都会红。
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_APP = _BACKEND / "app"
_FRONTEND_MODULE = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncContentRefresh.ts"
)
_EVENTS_ROUTER = _APP / "routers" / "events.py"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.models.audit_platform_schemas import EventPayload, EventType  # noqa: E402
from app.services import event_bus as event_bus_module  # noqa: E402
from app.services.workpaper_sync import content_events as CE  # noqa: E402
from app.services.workpaper_sync import content_mutation as CM  # noqa: E402
from app.services.workpaper_sync import representations as R  # noqa: E402

from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync.entry_profile import Capability  # noqa: E402

# Task 15 的守卫里已经有"构造一份合法 plan / bundle / representation stub"的整套夹具。
# 复用它而不是再抄一份：抄一份就会在 plan 字段变化时静默跑在旧形状上（第二真源）。
# 目录里没有 `__init__.py`（pytest prepend 模式把它自己的目录塞进 sys.path），
# 因此用绝对模块名导入。
if str(Path(__file__).parent) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(Path(__file__).parent))

from test_task15_content_mutation import (  # noqa: E402
    _RepStub,
    bundle_snapshot,
    plan as _standard_plan,
    xlsx_payload,
)


def _d(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode()).hexdigest()


def _read_py(path: Path) -> str:
    """读 Python 源码。

    🔴 用 ``utf-8-sig``：仓库里有带 BOM 的历史文件，``utf-8`` 读出来的前导 U+FEFF 会让
    ``ast.parse`` 直接 ``SyntaxError``。全仓扫描的守卫不能因为一个历史 BOM 就整条 error
    （那既不是被测代码的问题，也会把真正的违规藏在异常后面）。
    """
    return path.read_text(encoding="utf-8-sig")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """返回全部 docstring 常量节点的 ``id()``。

    结构判据必须把 docstring 排除在外：本次改动**在 events.py 的 docstring 里逐字引用了**
    被废弃的旧 stream key 以说明修点，不排除就等于把说明当成违规证据
    （本 spec 已登记的 ``stripComments`` 同类坑）。
    """
    marked: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            marked.add(id(body[0].value))
    return marked


def _code_string_literals(source: str) -> list[str]:
    """源码里**真正参与运算**的字符串字面量（排除 docstring）。"""
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 前端清单读取（两向锁死的另一侧）
# ═══════════════════════════════════════════════════════════════════════════


def _ts_string_array(source: str, const_name: str) -> list[str]:
    """从 TS 源码里取 ``export const X = [ 'a', 'b' ] as const`` 的字符串成员。

    刻意用**定位 + 括号配对**而不是固定字符窗口：窗口式切片在新增成员后会截半，
    而截半后的清单仍是"一个非空清单"，比对照样能过（假绿）。
    """
    anchor = f"export const {const_name} = ["
    index = source.find(anchor)
    assert index >= 0, f"前端模块里找不到 {const_name}"
    start = index + len(anchor) - 1
    depth = 0
    end = -1
    for position in range(start, len(source)):
        char = source[position]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = position
                break
    assert end > start, f"{const_name} 的数组字面量括号不配对"
    return re.findall(r"'([^']+)'", source[start : end + 1])


@pytest.fixture(scope="module")
def frontend_source() -> str:
    assert _FRONTEND_MODULE.exists(), f"前端接线模块不存在：{_FRONTEND_MODULE}"
    return _FRONTEND_MODULE.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 1. 三条 lane 的真实 payload 都满足前端的消费契约
# ═══════════════════════════════════════════════════════════════════════════


def _standard_payload() -> dict[str, Any]:
    """标准 commit lane 的真实 payload（真调 `_event_payload`）。"""
    contract = C.parse_contract(xlsx_payload())
    return CM.ContentMutationService._event_payload(  # noqa: SLF001
        plan=_standard_plan(bundle=bundle_snapshot(contract), contract=contract),
        revision=12,
        version_id=uuid.uuid4(),
        representation=_RepStub(generation=2),  # type: ignore[arg-type]
        artifact_sha256=_d("artifact"),
        projection_sha256=_d("projection"),
        requires_client_refresh=False,
    )


def _html_only_payload() -> dict[str, Any]:
    """html-only lane 的真实 payload（`single_html` 入口，没有 representation）。"""

    class _Artifact:
        relative_path = ".versions/wp/content/000000012-abc.projection.json.gz"
        sha256 = _d("html-projection")
        size_bytes = 2048
        document_type = "json"

    class _Staged:
        artifact = _Artifact()
        revision = 12

    html_plan = CM.HtmlOnlyCommitPlan(
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="html-only:D2",
        expected_revision=11,
        capability=Capability.single_html,
        sheet_name="审定表D2-1",
        schema_version=CM.HTML_PROJECTION_SCHEMA_VERSION,
    )
    return CM.ContentMutationService._html_only_event_payload(  # noqa: SLF001
        plan=html_plan,
        revision=12,
        version_id=uuid.uuid4(),
        staged=_Staged(),  # type: ignore[arg-type]
    )


def _definition_upgrade_payload() -> dict[str, Any]:
    """纯表示升级 lane 的真实 payload。"""
    return R.RepresentationService._event_payload(  # noqa: SLF001
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="g7.disclosure.listed",
        revision=12,
        representation=_RepStub(generation=3),  # type: ignore[arg-type]
        bundle=bundle_snapshot(C.parse_contract(xlsx_payload())),
        adapter_id="g7.disclosure.listed",
        artifact_sha256=_d("upgrade-artifact"),
    )


#: 三条 lane 的真实 payload 构造器。守卫对**每一条**断言前端契约成立。
_LANES = {
    "standard_commit": _standard_payload,
    "html_only_commit": _html_only_payload,
    "definition_upgrade": _definition_upgrade_payload,
}


class TestFrontendConsumerContract:
    def test_frontend_design_keys_equal_backend_constant(self, frontend_source: str) -> None:
        """**Validates: Requirements 13.2**

        前端声明的 design 7 键必须与后端 `EVENT_PAYLOAD_REQUIRED_KEYS` 逐字相等。
        """
        declared = _ts_string_array(frontend_source, "WP_CONTENT_EVENT_DESIGN_KEYS")
        assert set(declared) == set(CM.EVENT_PAYLOAD_REQUIRED_KEYS), (
            "前端 design 键清单与后端常量漂移："
            f"前端={sorted(declared)} vs 后端={sorted(CM.EVENT_PAYLOAD_REQUIRED_KEYS)}"
        )
        assert len(declared) == len(set(declared)) == 7

    def test_frontend_event_name_equals_backend_enum(self, frontend_source: str) -> None:
        """**Validates: Requirements 11.9**"""
        match = re.search(
            r"export const WP_CONTENT_UPDATED_EVENT_NAME = '([^']+)'", frontend_source
        )
        assert match, "前端没有声明 WP_CONTENT_UPDATED_EVENT_NAME"
        assert match.group(1) == EventType.WORKPAPER_CONTENT_UPDATED.value
        assert CE.CONTENT_UPDATED_EVENT_TYPE is EventType.WORKPAPER_CONTENT_UPDATED

    @pytest.mark.parametrize("lane", sorted(_LANES))
    def test_every_lane_supplies_every_key_the_consumer_requires(
        self, lane: str, frontend_source: str
    ) -> None:
        """**Validates: Requirements 11.9, 13.2**

        前端 11 个必填键必须被**三条 lane 全部**提供。

        🔴 这条防的是最贵的一类接线错误：前端多要一个只有某条 lane 才给的键，
        于是另一条 lane 的每一条事件都被静默拒绝 —— 前端判据只用一份夹具时全绿。
        """
        required = set(_ts_string_array(frontend_source, "WP_CONTENT_EVENT_DESIGN_KEYS")) | set(
            _ts_string_array(frontend_source, "WP_CONTENT_EVENT_CONSUMER_KEYS")
        )
        payload = _LANES[lane]()
        missing = sorted(required - set(payload))
        assert not missing, f"{lane} lane 的 payload 缺前端必填键 {missing}"
        # 消费侧靠它区分「业务改动」与「纯表示升级」；非布尔会被前端拒绝。
        assert isinstance(payload["content_revision_advanced"], bool)
        # commit 后判据：必须是一个真实的 content version id（非空、非全零）
        version_id = payload["content_version_id"]
        assert isinstance(version_id, str)
        assert uuid.UUID(version_id) != uuid.UUID(int=0)

    def test_definition_upgrade_lane_reports_revision_unchanged(self) -> None:
        """**Validates: Requirements 13.2**

        纯表示升级必须自报 `content_revision_advanced=False`，否则前端会把一次隐形
        模板升级当成业务改动去重载 HTML。
        """
        assert _definition_upgrade_payload()["content_revision_advanced"] is False
        assert _standard_payload()["content_revision_advanced"] is True
        assert _html_only_payload()["content_revision_advanced"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 53：payload → Stream → replay 投影，逐项不丢
# ═══════════════════════════════════════════════════════════════════════════


class TestTypedReplayPreservesPayload:
    @pytest.mark.parametrize("lane", sorted(_LANES))
    def test_full_round_trip_keeps_every_key(self, lane: str) -> None:
        """**Validates: Requirements 13.2**

        Property 53：``Redis typed event 中 wp_id/revision/operation/source/adapter 与
        outbox 逐项相等``。这里走的是**真实**那条链：

        ``outbox.payload → EventPayload.extra → serialize_payload_for_stream →
        deserialize_payload_from_stream → replay_entry_projection``。
        """
        payload = _LANES[lane]()
        outbox_payload = dict(payload)
        outbox_payload[CE.REPLAY_ITEM_KEYS[0]] = None  # 故意加一个无关键，验证不被吞
        outbox_payload.pop(CE.REPLAY_ITEM_KEYS[0])
        outbox_payload["__event_id"] = str(uuid.uuid4())

        event = EventPayload(
            event_type=EventType.WORKPAPER_CONTENT_UPDATED,
            project_id=uuid.UUID(payload["project_id"]),
            year=2025,
            extra=outbox_payload,
        )
        raw = event_bus_module.serialize_payload_for_stream(event)
        msg_id = "1755300000000-0"
        item = CE.replay_entry_projection(msg_id, {"payload_json": raw})
        assert item is not None
        assert sorted(item) == sorted(CE.REPLAY_ITEM_KEYS)
        assert item["event_type"] == EventType.WORKPAPER_CONTENT_UPDATED.value
        assert item["event_id"] == msg_id
        assert item["timestamp"] == 1755300000.0
        # 逐键相等（等值，不是包含）
        assert item["extra"] is not None
        assert sorted(item["extra"]) == sorted(outbox_payload)
        for key, value in outbox_payload.items():
            assert item["extra"][key] == value, f"{lane}: replay 后 {key} 漂移"
        # design 点名的 6 个业务字段逐项复核
        for key in ("wp_id", "revision", "operation_id", "source", "adapter_id", "file_sha256"):
            assert item["extra"][key] == outbox_payload[key]

    def test_extension_keys_survive(self) -> None:
        """**Validates: Requirements 13.2**

        `extra` 里的扩展键（representation/bundle/authority identity）必须原样回来 ——
        白名单裁剪等于在读取侧重新丢一次 `extra`。
        """
        payload = _standard_payload()
        event = EventPayload(
            event_type=EventType.WORKPAPER_CONTENT_UPDATED,
            project_id=uuid.UUID(payload["project_id"]),
            year=None,
            extra=payload,
        )
        item = CE.replay_entry_projection(
            "1-0", {"payload_json": event_bus_module.serialize_payload_for_stream(event)}
        )
        assert item is not None
        for extension in (
            "representation_id",
            "representation_generation",
            "definition_bundle_id",
            "definition_bundle_sha256",
            "authority_model",
            "adapter_build_digest",
            "projection_sha256",
            "requires_client_refresh",
        ):
            assert extension in item["extra"], f"扩展键 {extension} 在 replay 后丢了"

    def test_legacy_flat_entry_degrades_without_crashing(self) -> None:
        """**Validates: Requirements 13.2**

        本次改动之前躺在 Stream 里的旧条目没有 `payload_json`：必须降级重建而不是抛。
        它们本来就没有 `extra`，降级不"丢"任何已存在的东西。
        """
        item = CE.replay_entry_projection(
            "5-0",
            {
                "event_type": EventType.WORKPAPER_CONTENT_UPDATED.value,
                "project_id": str(uuid.uuid4()),
                "year": "2025",
                "account_codes": "[]",
            },
        )
        assert item is not None
        assert item["extra"] is None
        assert item["year"] == 2025

    def test_unparseable_entry_returns_none_instead_of_silently_empty(self) -> None:
        """**Validates: Requirements 13.9**

        解析不出来必须返回 `None` 让调用方显式计数。返回一个空壳 item 就是 fail-open：
        "事件被丢弃"这件事在日志和响应里都不可见。
        """
        assert CE.replay_entry_projection("6-0", {"event_type": "not.a.registered.event"}) is None
        assert CE.replay_entry_projection("7-0", {"payload_json": "{not json"}) is None

    def test_timestamp_and_project_scoping(self) -> None:
        """**Validates: Requirements 10.6, 13.2**"""
        project = uuid.uuid4()
        other = uuid.uuid4()
        item = {"project_id": str(project), "extra": {}}
        assert CE.belongs_to_project(item, project) is True
        assert CE.belongs_to_project(item, other) is False
        # 无归属事件不得下发到任何具体项目流（跨项目泄露）
        assert CE.belongs_to_project({"project_id": ""}, project) is False
        assert CE.belongs_to_project({}, project) is False

    def test_dedupe_key_matches_the_frontend_shape(self, frontend_source: str) -> None:
        """**Validates: Requirements 11.9**

        后端与前端的去重键必须同一口径：`wp_id|revision`，**不含** operation。
        """
        wp_id = str(uuid.uuid4())
        item = {"extra": {"wp_id": wp_id, "revision": 12, "operation_id": str(uuid.uuid4())}}
        key = CE.content_update_dedupe_key(item)
        assert key == f"{wp_id}|12"
        assert item["extra"]["operation_id"] not in str(key)
        # 前端的键拼法逐字相同（模板字符串）
        assert "`${wpId}|${revision}`" in frontend_source
        # 不可去重时返回 None 而不是编一个键
        assert CE.content_update_dedupe_key({"extra": {"revision": 12}}) is None
        assert CE.content_update_dedupe_key({"extra": {"wp_id": wp_id}}) is None
        assert CE.content_update_dedupe_key({"extra": None}) is None
        # bool 是 int 的子类：`True` 当 revision 会算出 "wp|True"
        assert CE.content_update_dedupe_key({"extra": {"wp_id": wp_id, "revision": True}}) is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. AC 11.9 后端半边：内容事件绝不走 debounce publish
# ═══════════════════════════════════════════════════════════════════════════

#: 会在 commit 前把事件发出去的三个发布口。``publish`` 还额外过 debounce 窗口。
_DEBOUNCE_PUBLISHERS = {"publish", "publish_immediate", "broadcast_raw"}


def _content_event_publish_violations(source: str, label: str) -> list[str]:
    """返回"把内容事件直接交给 debounce/立即发布口"的调用位置。

    判据是 **AST 实参归属**：``EventType.WORKPAPER_CONTENT_UPDATED``（或它的字面量值）
    出现在 ``publish/publish_immediate/broadcast_raw`` 的实参子树里就算违规。
    """
    violations: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in _DEBOUNCE_PUBLISHERS:
            continue
        for argument in list(node.args) + [kw.value for kw in node.keywords]:
            for inner in ast.walk(argument):
                if (
                    isinstance(inner, ast.Attribute)
                    and inner.attr == "WORKPAPER_CONTENT_UPDATED"
                ):
                    violations.append(f"{label}:{node.lineno} {name}(...)")
                if (
                    isinstance(inner, ast.Constant)
                    and inner.value == EventType.WORKPAPER_CONTENT_UPDATED.value
                ):
                    violations.append(f"{label}:{node.lineno} {name}(...)")
    return violations


class TestContentEventNeverGoesThroughDebounce:
    def test_no_app_module_publishes_the_content_event_directly(self) -> None:
        """**Validates: Requirements 11.9, 13.1**

        AC 11.9 末句"不得依赖进程内 commit 前 debounce 事件"的后端半边：内容事件只能
        经 outbox ``enqueue`` 落耐久行，由 commit 之后的 ``publish_pending`` 发出。
        """
        violations: list[str] = []
        for path in sorted(_APP.rglob("*.py")):
            violations.extend(
                _content_event_publish_violations(
                    _read_py(path), str(path.relative_to(_REPO))
                )
            )
        assert violations == [], (
            "内容事件被直接交给 debounce/立即发布口，事务回滚后事件已经出去了："
            f"{violations}"
        )

    def test_the_analyzer_actually_catches_a_violation(self) -> None:
        """**反向自检**：分析器必须能抓到违规，否则上一条恒绿（永久 GREEN）。"""
        enum_form = (
            "from app.models.audit_platform_schemas import EventPayload, EventType\n"
            "async def bad(bus):\n"
            "    await bus.publish(EventPayload(\n"
            "        event_type=EventType.WORKPAPER_CONTENT_UPDATED, project_id=None))\n"
        )
        literal_form = (
            "def bad(bus):\n"
            "    bus.broadcast_raw('workpaper.content.updated', {'wp_id': 'x'})\n"
        )
        assert _content_event_publish_violations(enum_form, "synthetic") != []
        assert _content_event_publish_violations(literal_form, "synthetic") != []
        # 合法形态不得被误报
        legal = (
            "from app.models.audit_platform_schemas import EventType\n"
            "async def good(outbox, db):\n"
            "    await outbox.enqueue(db,\n"
            "        event_type=EventType.WORKPAPER_CONTENT_UPDATED, project_id=None)\n"
        )
        assert _content_event_publish_violations(legal, "synthetic") == []

    def test_the_two_content_event_enqueue_sites_are_the_publishers(self) -> None:
        """**Validates: Requirements 13.1**

        内容事件的入队点只能在 `ContentMutationService` 与 `RepresentationService`
        （两者都在自己的单事务里 stamp `outbox` 步）。第三处入队意味着又出现了一条
        绕过单一提交边界的发布路径。
        """
        hosts: set[str] = set()
        for path in sorted(_APP.rglob("*.py")):
            tree = ast.parse(_read_py(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name != "enqueue":
                    continue
                for kw in node.keywords:
                    for inner in ast.walk(kw.value):
                        if (
                            isinstance(inner, ast.Attribute)
                            and inner.attr == "WORKPAPER_CONTENT_UPDATED"
                        ):
                            hosts.add(str(path.relative_to(_APP)).replace("\\", "/"))
        assert hosts == {
            "services/workpaper_sync/content_mutation.py",
            "services/workpaper_sync/representations.py",
        }, hosts


# ═══════════════════════════════════════════════════════════════════════════
# 4. `/events/since`：typed replay 的读取面接上了
# ═══════════════════════════════════════════════════════════════════════════


def _function_node(path: Path, name: str) -> ast.AST:
    tree = ast.parse(_read_py(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path.name} 里找不到函数 {name}")


def _body_names(node: ast.AST) -> set[str]:
    """函数体内出现的全部标识符（Name.id + Attribute.attr）。"""
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            names.add(inner.id)
        elif isinstance(inner, ast.Attribute):
            names.add(inner.attr)
    return names


class TestReplayEndpointWiring:
    def test_stream_key_has_exactly_one_source(self) -> None:
        """**Validates: Requirements 13.2**

        写入方（`event_bus`）与读取方（`/events/since`）必须共用同一个键常量。
        """
        assert event_bus_module.EVENT_STREAM_KEY == "audit:events"
        source = _read_py(_EVENTS_ROUTER)
        # 第二真源字面量必须从**代码**里消失（它读的是一条没有写入方的 stream）。
        # docstring 里逐字引用它是为了说明修点，因此判据排除 docstring。
        literals = _code_string_literals(source)
        assert "events:stream" not in literals, "router 里仍有第二个 stream key 字面量"
        # 反向自检：排除 docstring 之后仍能看到真实字面量（否则判据恒真）
        assert "audit:events" not in literals, "本条应从常量取键，不该出现写死的键"
        assert literals, "字符串字面量提取器返回空 —— 判据恒真"
        names = _body_names(_function_node(_EVENTS_ROUTER, "get_events_since"))
        assert "EVENT_STREAM_KEY" in names, "/events/since 没有引用唯一的 stream key 常量"

    def test_since_endpoint_uses_the_shared_replay_projection(self) -> None:
        """**Validates: Requirements 13.2**

        投影必须走 `replay_entry_projection`（唯一真源），而不是在端点里再拼一份 ——
        端点里那份原来就把 `extra` 整片丢了。
        """
        names = _body_names(_function_node(_EVENTS_ROUTER, "get_events_since"))
        assert "replay_entry_projection" in names
        assert "belongs_to_project" in names

    def test_authorization_before_resource_read_is_preserved(self) -> None:
        """**Validates: Requirements 10.6**

        改动不得动掉授权前置：`check_project_access` 必须仍在函数体内。
        """
        node = _function_node(_EVENTS_ROUTER, "get_events_since")
        assert "check_project_access" in _body_names(node)
        # 且必须在读取 Redis 之前（语句次序，不是"出现过"）
        lines_auth = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and getattr(inner.func, "id", getattr(inner.func, "attr", "")) == "check_project_access"
        ]
        lines_read = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and getattr(inner.func, "attr", "") == "xrange"
        ]
        assert lines_auth and lines_read
        assert min(lines_auth) < min(lines_read), "授权检查跑在资源读取之后"

    @pytest.mark.asyncio
    async def test_since_endpoint_really_returns_the_full_payload(self, monkeypatch) -> None:
        """**Validates: Requirements 13.2**

        真实执行一次 `/events/since`（直接调 endpoint 函数）：喂一条真序列化过的
        Stream 条目，断言返回项的 `extra` 与 outbox payload 逐键相等。

        🔴 这条是 Property 53 在**断线补拉**路径上的判据。改动之前它恒返回 `[]`
        （读的 stream key 没有写入方），因此这条断言在改动前必红。
        """
        from app.routers import events as events_router

        payload = _standard_payload()
        project = uuid.UUID(payload["project_id"])
        event = EventPayload(
            event_type=EventType.WORKPAPER_CONTENT_UPDATED,
            project_id=project,
            year=2025,
            extra=payload,
        )
        raw = event_bus_module.serialize_payload_for_stream(event)

        # 另一个项目的事件：必须被 scope 过滤掉
        other_event = EventPayload(
            event_type=EventType.WORKPAPER_CONTENT_UPDATED,
            project_id=uuid.uuid4(),
            year=2025,
            extra={**payload, "project_id": str(uuid.uuid4())},
        )
        other_raw = event_bus_module.serialize_payload_for_stream(other_event)

        seen_keys: list[str] = []

        class _FakeRedis:
            async def xrange(self, key, min, max, count):  # noqa: A002 - 与真实签名一致
                seen_keys.append(key)
                return [
                    ("1755300000000-0", {"payload_json": raw}),
                    ("1755300000001-0", {"payload_json": other_raw}),
                    ("1755300000002-0", {"event_type": "not.a.registered.event"}),
                ]

        import app.core.redis as core_redis

        monkeypatch.setattr(core_redis, "redis_client", _FakeRedis(), raising=False)

        async def _allow(*_args, **_kwargs):
            return None

        monkeypatch.setattr(events_router, "check_project_access", _allow)

        result = await events_router.get_events_since(
            project_id=project,
            last_event_id=None,
            since_timestamp=None,
            current_user=object(),  # type: ignore[arg-type]
            db=object(),  # type: ignore[arg-type]
        )
        assert seen_keys == [event_bus_module.EVENT_STREAM_KEY]
        assert len(result) == 1, f"scope 过滤 / 丢弃计数不对：{result}"
        item = result[0]
        assert item["event_type"] == EventType.WORKPAPER_CONTENT_UPDATED.value
        assert item["extra"] is not None
        assert sorted(item["extra"]) == sorted(payload)
        for key, value in payload.items():
            assert item["extra"][key] == value
        # 去重键在补拉结果上同样算得出来（AC 11.9 的断线恢复）
        assert CE.content_update_dedupe_key(item) == f"{payload['wp_id']}|{payload['revision']}"

    @pytest.mark.asyncio
    async def test_since_endpoint_degrades_to_empty_when_redis_is_down(self, monkeypatch) -> None:
        """**Validates: Requirements 13.4**

        Redis 不可用时降级返回 `[]` 而不是 500 —— 断线补拉失败不得把整页打挂。
        """
        from app.routers import events as events_router

        class _DeadRedis:
            async def xrange(self, *_args, **_kwargs):
                raise RuntimeError("redis down")

        import app.core.redis as core_redis

        monkeypatch.setattr(core_redis, "redis_client", _DeadRedis(), raising=False)

        async def _allow(*_args, **_kwargs):
            return None

        monkeypatch.setattr(events_router, "check_project_access", _allow)
        result = await events_router.get_events_since(
            project_id=uuid.uuid4(),
            last_event_id=None,
            since_timestamp=None,
            current_user=object(),  # type: ignore[arg-type]
            db=object(),  # type: ignore[arg-type]
        )
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. SSE `/stream` 的信封形态与前端归一逐字对齐
# ═══════════════════════════════════════════════════════════════════════════


class TestSseEnvelopeShape:
    def test_stream_endpoint_puts_business_keys_under_extra(self) -> None:
        """**Validates: Requirements 11.9, 13.2**

        前端归一层剥的就是这一层。判据取 `/events/stream` 里真实构造的 `event_data`
        字典的**键集**（AST 读字面量键），而不是"某个字符串出现过"。
        """
        tree = ast.parse(_read_py(_EVENTS_ROUTER))
        envelopes: list[set[str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                item.value
                for item in node.keys
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            if {"event_type", "extra"} <= keys:
                envelopes.append(keys)
        assert envelopes, "/events/stream 没有构造带 event_type + extra 的信封"
        for keys in envelopes:
            assert "wp_id" not in keys, (
                "业务键被提到信封顶层了 —— 前端归一层剥的是 `extra`，"
                "两侧形态必须一致"
            )

    def test_frontend_unwraps_exactly_the_two_envelope_markers(
        self, frontend_source: str
    ) -> None:
        """**Validates: Requirements 13.2**

        前端剥层的判据是"顶层有 `event_type` **且** `extra` 是对象"。两个条件都要 ——
        只看 `extra` 会误剥一个恰好带 `extra` 键的扁平 payload。
        """
        assert "outer.event_type" in frontend_source
        assert "asWire(outer.extra)" in frontend_source
        assert "eventName !== null && inner !== null" in frontend_source


# ═══════════════════════════════════════════════════════════════════════════
# 6. 前端接线层的结构判据（零 api 面 ⇒ 结构上不产生新 revision）
# ═══════════════════════════════════════════════════════════════════════════


def _strip_ts_comments(source: str) -> str:
    return re.sub(r"(^|[^:])//[^\n]*", r"\1", re.sub(r"/\*[\s\S]*?\*/", "", source))


class TestFrontendCoordinatorHasNoWritePath:
    def test_the_module_imports_no_http_surface(self, frontend_source: str) -> None:
        """**Validates: Requirements 13.4**

        Task 35 正文："event/刷新失败……不影响已提交内容，不产生新 revision"。
        结构判据：接线模块不 import 任何 HTTP / api 面，因此它**没有**写入口。
        """
        stripped = _strip_ts_comments(frontend_source)
        # 反向自检：剥注释没把 import 段一起剥掉
        assert "from '@/services/sse/projectEventStream'" in stripped
        assert "from './workpaperSyncDto'" in stripped
        for forbidden in (
            "@/utils/http",
            "@/services/apiProxy",
            "./workpaperSyncApi",
            "fetch(",
            "XMLHttpRequest",
        ):
            assert forbidden not in stripped, f"接线模块引了写入面 {forbidden}"

    def test_two_failure_classes_have_disjoint_codes(self, frontend_source: str) -> None:
        """**Validates: Requirements 13.4**

        事件形态失败与刷新失败必须是两套码：共用一个码会让先到的分支把后到的遮成
        永不可达（本 spec 已三次抓到这个形态）。
        """
        stripped = _strip_ts_comments(frontend_source)
        event_codes = set(re.findall(r"'(content_event_[a-z_]+)'", stripped))
        refresh_codes = set(re.findall(r"'(content_refresh_[a-z_]+)'", stripped))
        assert len(event_codes) >= 5, sorted(event_codes)
        assert len(refresh_codes) >= 3, sorted(refresh_codes)
        assert event_codes.isdisjoint(refresh_codes)

    def test_dirty_branch_does_not_reach_the_reload_hook(self, frontend_source: str) -> None:
        """**Validates: Requirements 11.9**

        "dirty 时不静默覆盖"的**结构**判据：`isDirty()` 分支体内不得出现 `runReload`。
        行为侧判据在 `workpaperSyncContentRefresh.spec.ts`（reload 调用次数 = 0）。
        """
        stripped = _strip_ts_comments(frontend_source)
        anchor = "if (options.isDirty()) {"
        index = stripped.find(anchor)
        assert index >= 0, "找不到 dirty 分支"
        depth = 0
        end = -1
        for position in range(index + len(anchor) - 1, len(stripped)):
            char = stripped[position]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = position
                    break
        assert end > index
        branch = stripped[index : end + 1]
        assert "runReload" not in branch, "dirty 分支里调了 reload —— 那就是静默覆盖"
        assert "rememberPending" in branch
