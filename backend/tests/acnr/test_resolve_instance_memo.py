"""resolve_instance 请求级缓存集成测试 — Task 21 [Req-17, P19]

验证:
1. batch 10 个同 sheet 输入 → DB resolve_instance 仅调 1 次
2. 不同 (project_id, parent_wp_code, sheet_code) 三元组各查 1 次 DB
3. disambiguation 结果不缓存（每次重新查询）
4. 缓存生命周期限定为单次请求（不跨请求保留）
5. 非 batch 单次 resolve 不受影响（无 memo 传入时正常工作）

**Validates: Requirements 17.1, 17.2, 17.3, 17.4**

Correctness Property P19: resolve_instance 请求内去重
  集成测试：batch 10 个同 sheet 输入 → DB resolve_instance 仅调 1 次
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID, uuid4

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))


# ─── Fake types ──────────────────────────────────────────────────────────────

@dataclass
class FakeResolveResult:
    found: bool = False
    addr_id: Optional[str] = None
    entry_type: Optional[str] = None
    cell_address: Optional[str] = None
    semantic_label: Optional[str] = None
    formula_ref: Optional[str] = None
    uri: Optional[str] = None
    jump_route: Optional[str] = None
    wp_id: Optional[str] = None
    error: Optional[str] = None
    candidates: Optional[list] = None
    source_layer: Optional[str] = None


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_user():
    class FakeUser:
        id = "test-user-id"
        role = "admin"
    return FakeUser()


@pytest.fixture
def mock_auth():
    with patch("app.routers.acnr.check_project_access", new_callable=AsyncMock) as m:
        yield m


# ─── P19: batch 10 同 sheet → DB 仅调 1 次 ────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_10_same_sheet_resolve_instance_called_once(mock_auth, mock_user):
    """P19: batch 10 个同 sheet 输入 → resolve_instance 仅调 DB 1 次。

    **Validates: Requirements 1.2**

    Req-17.2: 批量 resolve（resolve-batch）处理 N 个输入，
    _attach_wp_id 对相同 (project_id, parent, sheet_code) 三元组仅查 1 次 DB。
    """
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem
    from app.services.acnr.resolver import ResolveResult, ResolveInstanceResult

    fake_project_id = str(uuid4())
    fake_wp_id = uuid4()

    # Track resolve_instance calls
    resolve_instance_call_count = 0

    async def _fake_resolve_instance(db, project_id, parent_wp_code, sheet_code, *, explicit_wp_id=None):
        nonlocal resolve_instance_call_count
        resolve_instance_call_count += 1
        return ResolveInstanceResult(
            found=True,
            wp_id=fake_wp_id,
            wp_index_id=uuid4(),
            jump_route=f"/workpapers/{fake_wp_id}?sheet={sheet_code}",
        )

    # Mock full_resolve to simulate L1 hit that triggers _attach_wp_id
    # We need to NOT mock full_resolve entirely but instead mock the deeper layers
    # to allow _attach_wp_id + memo logic to execute.
    # Strategy: mock the catalog + overlay + runtime to produce L1 hits,
    # and mock resolve_instance to count DB calls.

    # Simpler approach: patch resolve_instance directly inside resolver module
    with patch("app.services.acnr.resolver.resolve_instance", side_effect=_fake_resolve_instance) as mock_ri:
        # Also need to make full_resolve return found=True with an addr_id
        # that will trigger _attach_wp_id. We'll mock the catalog to return a hit.

        fake_cell_entry = {
            "addr_id": "D2/D2-2/E100",
            "cell_address": "E100",
            "semantic_label": "应收账款期末审定",
            "formula_ref": "WP('D2','D2-2','E100')",
            "uri": "wp://D2/D2-2#E100",
            "parent_addr_id": "D2/D2-2",
        }

        fake_catalog = MagicMock()
        fake_catalog.cells_by_addr_id = {"D2/D2-2/E100": fake_cell_entry}
        fake_catalog.sheets_by_addr_id = {
            "D2/D2-2": {
                "addr_id": "D2/D2-2",
                "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2",
            }
        }
        fake_catalog.registry_version = "1.0.0"

        fake_overlay = MagicMock()
        fake_overlay.get_project_aliases = MagicMock(return_value={})

        with patch("app.services.acnr.resolver.get_catalog", return_value=fake_catalog):
            with patch("app.services.acnr.resolver.get_project_overlay", return_value=fake_overlay):
                with patch("app.services.acnr.resolver.get_project_registry_version", return_value=None):
                    with patch("app.services.acnr.resolver._detect_non_wp_domain", return_value=None):
                        body = AcnrResolveBatchRequest(
                            items=[
                                AcnrResolveBatchItem(addr_id="D2/D2-2/E100")
                                for _ in range(10)
                            ],
                            project_id=fake_project_id,
                        )

                        results = await acnr_resolve_batch(
                            body=body, _user=mock_user, db=AsyncMock()
                        )

    # All 10 should resolve successfully
    assert len(results) == 10
    for r in results:
        assert r.get("found") is True

    # KEY ASSERTION: resolve_instance called only ONCE despite 10 items
    assert resolve_instance_call_count == 1, (
        f"Expected resolve_instance to be called exactly 1 time for 10 identical "
        f"(project_id, parent_wp_code, sheet_code) tuples, but got {resolve_instance_call_count}"
    )


@pytest.mark.asyncio
async def test_different_sheet_codes_each_call_db_once(mock_auth, mock_user):
    """不同 (project_id, parent, sheet_code) 三元组各查 1 次 DB。

    **Validates: Requirements 1.2**

    验证 memo key 按三元组区分，不同 sheet_code 各自查 1 次。
    """
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem
    from app.services.acnr.resolver import ResolveResult, ResolveInstanceResult

    fake_project_id = str(uuid4())
    fake_wp_id = uuid4()

    resolve_instance_calls: list[str] = []

    async def _fake_resolve_instance(db, project_id, parent_wp_code, sheet_code, *, explicit_wp_id=None):
        key = f"{project_id}:{parent_wp_code}:{sheet_code}"
        resolve_instance_calls.append(key)
        return ResolveInstanceResult(
            found=True,
            wp_id=fake_wp_id,
            wp_index_id=uuid4(),
            jump_route=f"/workpapers/{fake_wp_id}?sheet={sheet_code}",
        )

    with patch("app.services.acnr.resolver.resolve_instance", side_effect=_fake_resolve_instance):
        fake_catalog = MagicMock()
        # Two different cells on different sheets
        fake_catalog.cells_by_addr_id = {
            "D2/D2-2/E100": {
                "addr_id": "D2/D2-2/E100",
                "cell_address": "E100",
                "semantic_label": None,
                "formula_ref": None,
                "uri": None,
                "parent_addr_id": "D2/D2-2",
            },
            "D2/D2-3/F200": {
                "addr_id": "D2/D2-3/F200",
                "cell_address": "F200",
                "semantic_label": None,
                "formula_ref": None,
                "uri": None,
                "parent_addr_id": "D2/D2-3",
            },
        }
        fake_catalog.sheets_by_addr_id = {
            "D2/D2-2": {"addr_id": "D2/D2-2", "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2"},
            "D2/D2-3": {"addr_id": "D2/D2-3", "jump_route_template": "/workpapers/{wp_id}?sheet=D2-3"},
        }
        fake_catalog.registry_version = "1.0.0"

        fake_overlay = MagicMock()
        fake_overlay.get_project_aliases = MagicMock(return_value={})

        with patch("app.services.acnr.resolver.get_catalog", return_value=fake_catalog):
            with patch("app.services.acnr.resolver.get_project_overlay", return_value=fake_overlay):
                with patch("app.services.acnr.resolver.get_project_registry_version", return_value=None):
                    with patch("app.services.acnr.resolver._detect_non_wp_domain", return_value=None):
                        # 5 items for D2-2 + 5 items for D2-3
                        items = (
                            [AcnrResolveBatchItem(addr_id="D2/D2-2/E100") for _ in range(5)]
                            + [AcnrResolveBatchItem(addr_id="D2/D2-3/F200") for _ in range(5)]
                        )
                        body = AcnrResolveBatchRequest(items=items, project_id=fake_project_id)

                        results = await acnr_resolve_batch(
                            body=body, _user=mock_user, db=AsyncMock()
                        )

    assert len(results) == 10
    # Two distinct sheet_codes → exactly 2 DB calls
    assert len(resolve_instance_calls) == 2, (
        f"Expected 2 resolve_instance calls (one per distinct sheet_code), "
        f"got {len(resolve_instance_calls)}: {resolve_instance_calls}"
    )


@pytest.mark.asyncio
async def test_disambiguation_result_not_cached(mock_auth, mock_user):
    """Req-17.4: disambiguation 结果不缓存，每次重新查询。

    **Validates: Requirements 1.2**
    """
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem
    from app.services.acnr.resolver import ResolveResult, ResolveInstanceResult

    fake_project_id = str(uuid4())

    resolve_instance_call_count = 0

    async def _fake_resolve_instance(db, project_id, parent_wp_code, sheet_code, *, explicit_wp_id=None):
        nonlocal resolve_instance_call_count
        resolve_instance_call_count += 1
        # Always return disambiguation
        return ResolveInstanceResult(
            found=False,
            error="disambiguation",
            candidates=[
                {"wp_index_id": str(uuid4()), "wp_code": sheet_code, "wp_name": "test1"},
                {"wp_index_id": str(uuid4()), "wp_code": sheet_code, "wp_name": "test2"},
            ],
        )

    with patch("app.services.acnr.resolver.resolve_instance", side_effect=_fake_resolve_instance):
        fake_catalog = MagicMock()
        fake_catalog.cells_by_addr_id = {
            "D2/D2-2/E100": {
                "addr_id": "D2/D2-2/E100",
                "cell_address": "E100",
                "semantic_label": None,
                "formula_ref": None,
                "uri": None,
                "parent_addr_id": "D2/D2-2",
            },
        }
        fake_catalog.sheets_by_addr_id = {
            "D2/D2-2": {"addr_id": "D2/D2-2", "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2"},
        }
        fake_catalog.registry_version = "1.0.0"

        fake_overlay = MagicMock()
        fake_overlay.get_project_aliases = MagicMock(return_value={})

        with patch("app.services.acnr.resolver.get_catalog", return_value=fake_catalog):
            with patch("app.services.acnr.resolver.get_project_overlay", return_value=fake_overlay):
                with patch("app.services.acnr.resolver.get_project_registry_version", return_value=None):
                    with patch("app.services.acnr.resolver._detect_non_wp_domain", return_value=None):
                        # 3 items with same sheet → disambiguation should NOT cache
                        body = AcnrResolveBatchRequest(
                            items=[AcnrResolveBatchItem(addr_id="D2/D2-2/E100") for _ in range(3)],
                            project_id=fake_project_id,
                        )

                        results = await acnr_resolve_batch(
                            body=body, _user=mock_user, db=AsyncMock()
                        )

    # disambiguation → called 3 times (not cached)
    assert resolve_instance_call_count == 3, (
        f"Disambiguation results must NOT be cached. Expected 3 calls, "
        f"got {resolve_instance_call_count}"
    )


@pytest.mark.asyncio
async def test_memo_is_request_scoped_not_shared_across_requests(mock_auth, mock_user):
    """Req-17.3: 缓存生命周期限定为单次请求，不跨请求保留。

    **Validates: Requirements 1.2**

    两次独立调用 resolve-batch 各自创建新 memo，第二次仍然查 DB。
    """
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem
    from app.services.acnr.resolver import ResolveResult, ResolveInstanceResult

    fake_project_id = str(uuid4())
    fake_wp_id = uuid4()

    resolve_instance_call_count = 0

    async def _fake_resolve_instance(db, project_id, parent_wp_code, sheet_code, *, explicit_wp_id=None):
        nonlocal resolve_instance_call_count
        resolve_instance_call_count += 1
        return ResolveInstanceResult(
            found=True,
            wp_id=fake_wp_id,
            wp_index_id=uuid4(),
            jump_route=f"/workpapers/{fake_wp_id}?sheet={sheet_code}",
        )

    with patch("app.services.acnr.resolver.resolve_instance", side_effect=_fake_resolve_instance):
        fake_catalog = MagicMock()
        fake_catalog.cells_by_addr_id = {
            "D2/D2-2/E100": {
                "addr_id": "D2/D2-2/E100",
                "cell_address": "E100",
                "semantic_label": None,
                "formula_ref": None,
                "uri": None,
                "parent_addr_id": "D2/D2-2",
            },
        }
        fake_catalog.sheets_by_addr_id = {
            "D2/D2-2": {"addr_id": "D2/D2-2", "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2"},
        }
        fake_catalog.registry_version = "1.0.0"

        fake_overlay = MagicMock()
        fake_overlay.get_project_aliases = MagicMock(return_value={})

        with patch("app.services.acnr.resolver.get_catalog", return_value=fake_catalog):
            with patch("app.services.acnr.resolver.get_project_overlay", return_value=fake_overlay):
                with patch("app.services.acnr.resolver.get_project_registry_version", return_value=None):
                    with patch("app.services.acnr.resolver._detect_non_wp_domain", return_value=None):
                        body = AcnrResolveBatchRequest(
                            items=[AcnrResolveBatchItem(addr_id="D2/D2-2/E100") for _ in range(3)],
                            project_id=fake_project_id,
                        )

                        # First request
                        await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())
                        # Second request (new memo)
                        await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())

    # Each request creates its own memo: 1 call per request = 2 total
    assert resolve_instance_call_count == 2, (
        f"Memo must be request-scoped. Expected 2 calls (1 per request), "
        f"got {resolve_instance_call_count}"
    )


@pytest.mark.asyncio
async def test_single_resolve_without_memo_still_works():
    """非 batch 单次 resolve 不传 memo，正常工作不报错。

    **Validates: Requirements 1.2**

    确保 _instance_memo=None 时 _attach_wp_id 正常执行（向后兼容）。
    """
    from app.services.acnr.resolver import _attach_wp_id, ResolveResult, ResolveInstanceResult

    fake_project_id = str(uuid4())
    fake_wp_id = uuid4()

    async def _fake_resolve_instance(db, project_id, parent_wp_code, sheet_code, *, explicit_wp_id=None):
        return ResolveInstanceResult(
            found=True,
            wp_id=fake_wp_id,
            wp_index_id=uuid4(),
            jump_route=f"/workpapers/{fake_wp_id}?sheet={sheet_code}",
        )

    with patch("app.services.acnr.resolver.resolve_instance", side_effect=_fake_resolve_instance):
        result = ResolveResult(
            found=True,
            addr_id="D2/D2-2/E100",
            entry_type="cell",
            source_layer="L1_cell",
        )

        # Call without memo (None) — backward compat
        updated = await _attach_wp_id(result, fake_project_id, AsyncMock(), None)

    assert updated.wp_id == str(fake_wp_id)
    assert updated.found is True
