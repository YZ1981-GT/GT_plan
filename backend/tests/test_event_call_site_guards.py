"""事件调用点 AST/源码守卫：错误 import、await publish、broadcast_raw 签名。

Validates: Requirements 9.3, 9.4, 9.5, 9.7 / Property 18
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "backend" / "app"
DISPATCH_PATH = APP_ROOT / "routers" / "dispatch_records.py"
S_TXN_PATH = APP_ROOT / "routers" / "s_transaction_calculation.py"
BAD_IMPORT_NEEDLE = "from app.core.event_bus import"
LEGACY_HOTSPOTS = (
    APP_ROOT / "services" / "review_workflow_service.py",
    APP_ROOT / "services" / "independence_signing_service.py",
    APP_ROOT / "routers" / "adjustments.py",
)


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    mapping: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            mapping[child] = node
    return mapping


def _attr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _calls_named(tree: ast.AST, attr: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _attr_name(node.func) == attr
    ]


def _scan_forbidden_event_bus_imports(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "__pycache__":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if BAD_IMPORT_NEEDLE in text or "import app.core.event_bus" in text:
            hits.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return hits


def _unawaited_event_bus_publishes(src: str) -> list[ast.Call]:
    tree = ast.parse(src)
    parents = _parents(tree)
    bad: list[ast.Call] = []
    for call in _calls_named(tree, "publish"):
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "event_bus"
        ):
            continue
        if not isinstance(parents.get(call), ast.Await):
            bad.append(call)
    return bad


def _awaited_broadcast_raw_calls(src: str) -> list[ast.Call]:
    tree = ast.parse(src)
    parents = _parents(tree)
    return [
        call
        for call in _calls_named(tree, "broadcast_raw")
        if isinstance(parents.get(call), ast.Await)
    ]


def _broadcast_raw_param_violations(src: str) -> list[str]:
    tree = ast.parse(src)
    violations: list[str] = []
    for call in _calls_named(tree, "broadcast_raw"):
        if not isinstance(call.func, ast.Attribute):
            continue
        kw = {k.arg for k in call.keywords if k.arg}
        if "data" in kw:
            violations.append("uses forbidden keyword 'data'")
        if "project_id" in kw:
            violations.append("uses forbidden keyword 'project_id' (must be inside extra)")
        if call.args and len(call.args) > 2:
            violations.append("too many positional args")
    return violations


# ── production guards ────────────────────────────────────────────────────────


def test_zero_app_core_event_bus_imports_under_backend_app() -> None:
    hits = _scan_forbidden_event_bus_imports(APP_ROOT)
    assert hits == [], f"forbidden app.core.event_bus imports: {hits}"
    assert not (APP_ROOT / "core" / "event_bus.py").exists()


def test_legacy_hotspots_import_real_event_bus_module() -> None:
    for path in LEGACY_HOTSPOTS:
        src = path.read_text(encoding="utf-8")
        assert BAD_IMPORT_NEEDLE not in src
        assert "from app.services.event_bus import" in src


def test_dispatch_records_awaits_every_event_bus_publish() -> None:
    src = DISPATCH_PATH.read_text(encoding="utf-8")
    bad = _unawaited_event_bus_publishes(src)
    assert not bad, f"dispatch_records has non-awaited event_bus.publish: {len(bad)}"
    tree = ast.parse(src)
    parents = _parents(tree)
    awaited = [
        call
        for call in _calls_named(tree, "publish")
        if isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "event_bus"
        and isinstance(parents.get(call), ast.Await)
    ]
    assert len(awaited) >= 2, "create + revoke must both await publish"


@pytest.mark.asyncio
async def test_dispatch_create_awaits_publish_side_effect_once() -> None:
    from app.routers.dispatch_records import (
        BatchCreateRequest,
        DispatchEntrySchema,
        create_dispatch_records,
    )
    from app.services.dispatch_service import BatchResult

    project_id = uuid.uuid4()
    user = MagicMock()
    user.id = uuid.uuid4()
    record = MagicMock()
    record.id = uuid.uuid4()
    record.project_id = project_id
    record.confirm_index = "C-1"
    record.target = "D0-4"
    record.entity_name = None
    record.account_type = None
    record.amount = None
    record.reason = None
    record.dispatched_by = user.id
    record.dispatched_at = datetime.now(timezone.utc)

    db = AsyncMock()
    db.commit = AsyncMock()
    with patch(
        "app.routers.dispatch_records.DispatchService.batch_create",
        AsyncMock(return_value=BatchResult(dispatched=[record], skipped=[])),
    ):
        with patch("app.routers.dispatch_records.event_bus") as bus:
            bus.publish = AsyncMock()
            await create_dispatch_records(
                project_id,
                BatchCreateRequest(
                    entries=[DispatchEntrySchema(confirm_index="C-1", target="D0-4")]
                ),
                db,
                user,
            )
    bus.publish.assert_awaited_once()


def test_s_transaction_broadcast_raw_is_sync_with_correct_signature() -> None:
    src = S_TXN_PATH.read_text(encoding="utf-8")
    assert not _awaited_broadcast_raw_calls(src)
    assert not _broadcast_raw_param_violations(src)
    tree = ast.parse(src)
    calls = [
        call
        for call in _calls_named(tree, "broadcast_raw")
        if isinstance(call.func, ast.Attribute)
    ]
    assert calls, "s_transaction_calculation 应调用 broadcast_raw"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords if k.arg}
        assert "extra" in kw or (call.args and len(call.args) >= 2)


@pytest.mark.asyncio
async def test_disclosure_notify_broadcast_raw_sync_once() -> None:
    from app.routers.s_transaction_calculation import (
        DisclosureNotifyRequest,
        s_transaction_disclosure_notify,
    )
    from app.services.event_bus import EventBus

    assert inspect.iscoroutinefunction(EventBus.broadcast_raw) is False

    project_id = uuid.uuid4()
    db = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = (project_id, 2024)
    db.execute = AsyncMock(return_value=result)

    calls: list[tuple] = []

    def _raw(*args, **kwargs):
        calls.append((args, kwargs))
        return "not-a-coroutine"

    with patch("app.services.event_bus.event_bus") as bus:
        bus.broadcast_raw = _raw
        await s_transaction_disclosure_notify(
            str(uuid.uuid4()),
            DisclosureNotifyRequest(wp_code="S4", section="non-recurring", text="note"),
            db,
            MagicMock(),
        )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "disclosure:note-text-updated"
    extra = kwargs.get("extra") or (args[1] if len(args) > 1 else {})
    assert extra["project_id"] == str(project_id)
    assert extra["wp_code"] == "S4"


def test_adjustments_broadcast_raw_uses_event_type_and_extra() -> None:
    path = APP_ROOT / "routers" / "adjustments.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = _parents(tree)
    calls = [
        call
        for call in _calls_named(tree, "broadcast_raw")
        if isinstance(call.func, ast.Attribute)
    ]
    assert len(calls) >= 2
    for call in calls:
        assert not isinstance(parents.get(call), ast.Await)
        assert len(call.args) <= 2
        first = call.args[0] if call.args else None
        if isinstance(first, ast.JoinedStr):
            pytest.fail("broadcast_raw 第一参不得再是 projects:{id} 频道字符串")
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            assert not first.value.startswith("projects:")
        kw = {k.arg for k in call.keywords if k.arg}
        assert "data" not in kw


# ── reverse self-checks (must RED on injected violations) ────────────────────


def test_reverse_forbidden_import_scanner_detects_needle() -> None:
    synthetic = APP_ROOT / "_pac_guard_tmp_forbidden_import.py"
    try:
        synthetic.write_text(
            textwrap.dedent(
                """\
                from app.core.event_bus import event_bus
                """
            ),
            encoding="utf-8",
        )
        hits = _scan_forbidden_event_bus_imports(APP_ROOT)
        assert any(synthetic.name in h for h in hits), hits
    finally:
        synthetic.unlink(missing_ok=True)


def test_reverse_unawaited_publish_detector_reds() -> None:
    dirty = textwrap.dedent(
        """\
        async def create():
            event_bus.publish(payload)
        """
    )
    clean = textwrap.dedent(
        """\
        async def create():
            await event_bus.publish(payload)
        """
    )
    assert _unawaited_event_bus_publishes(dirty)
    assert not _unawaited_event_bus_publishes(clean)


def test_reverse_awaited_broadcast_raw_detector_reds() -> None:
    dirty = textwrap.dedent(
        """\
        async def notify():
            await event_bus.broadcast_raw("x", extra={})
        """
    )
    clean = textwrap.dedent(
        """\
        def notify():
            event_bus.broadcast_raw("x", extra={})
        """
    )
    assert _awaited_broadcast_raw_calls(dirty)
    assert not _awaited_broadcast_raw_calls(clean)


def test_reverse_broadcast_raw_wrong_kwargs_detector_reds() -> None:
    dirty = 'event_bus.broadcast_raw("t", data={"project_id": "1"})'
    clean = 'event_bus.broadcast_raw("t", extra={"project_id": "1"})'
    assert _broadcast_raw_param_violations(dirty)
    assert not _broadcast_raw_param_violations(clean)
