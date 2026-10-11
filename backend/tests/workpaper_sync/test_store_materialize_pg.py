"""P5 + P2 真库判据：服务端直取投影 + store 指纹直通（真 D2 provider / 真首版 / 真协调器）。

spec: workpaper-sync-switch-performance · 需求 3（P2 无改动直通）+ 需求 6（P5 服务端直取）

═══ 为什么要真库 ═══

零库那份（``test_store_materialize.py``）证的是编排分支。它证不了三件只在数据上成立的事：

1. **同源**：服务端构造的投影与客户端路径（GET store-projection → POST → ``build_projection``）
   逐字节相同 —— 否则 pending digest 与复用判据都和原路径分叉。
2. **直通的前提真的成立**：复用命中后，同一份 store 再来一次，协调器的 preflight 看到的 content
   version / substrate 与记录一致，直通只开 operation + room、零 revision、零 pending mutation。
3. **世界前进时直通必让路**：store 一改、或记录与当前版本对不上，必须回落正常路径真比一次；
   提交之后的下一次也必须真比一次（不把没做过的校验当成做过）。

世界搭建复用 R14 真库判据（``test_target_bound_registration_pg``）的 ``_setup_schema``：
scratch schema + 临时 artifact 根，结束 ``DROP SCHEMA CASCADE`` + ``rmtree``；存储根换到临时根
（``ORCH._BACKEND_ROOT`` 给 provider、``canonical_paths.BACKEND_ROOT`` 给生产协调器装配），
解析 / 注册 / 物化逻辑全走生产。全部阶段一次 ``asyncio.run`` 采集，采集失败落 ``errors`` 不穿透。

用法（仓库根）::

    .\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_store_materialize_pg.py -q
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.workpaper_sync.test_target_bound_registration_pg import (
    ENTRY,
    _err,
    _HarnessError,
    _setup_schema,
)

_SCHEMA_PREFIX = "tmp_swp_pg_"
_SECRET = "store-materialize-pg-secret"

ROWS: list[dict[str, Any]] = [
    {
        "rowId": f"swp-{i:03d}",
        "seq": i + 1,
        "customerName": f"直通客户{i}",
        "relationType": "非关联方",
        "priorUnadjusted": 100.0 + i,
        "currentUnadjusted": 200.0 + i,
    }
    for i in range(3)
]


async def _seed_and_publish(Session: Any, engine: Any, sa: Any, *, artifacts: Any) -> dict[str, Any]:
    """一家企业：写 D2 明细 store → provision → 生产按需首版。"""
    from app.services.workpaper_sync import pilot_d2_large_json as D2
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync.first_publication_on_demand import ensure_first_publication
    from app.services.workpaper_sync.projection_target_resolution import adjudicated_wp_codes
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    project, index, wp, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(sa.text("INSERT INTO users (id) VALUES (:u)"), {"u": actor})
        await conn.execute(
            sa.text("INSERT INTO projects (id, name) VALUES (:p, 'swp')"), {"p": project}
        )
        await conn.execute(
            sa.text("INSERT INTO wp_index (id, wp_code) VALUES (:i, :c)"),
            {"i": index, "c": adjudicated_wp_codes(ENTRY)[0]},
        )
        await conn.execute(
            sa.text("INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"),
            {"w": wp, "p": project, "i": index},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
                "VALUES (:id, :w, :item, :remark)"
            ),
            {"id": uuid.uuid4(), "w": wp, "item": D2.STORE_ITEM_ID,
             "remark": json.dumps(ROWS, ensure_ascii=False)},
        )
    async with Session() as session:
        await PP.ProjectionDefinitionProvisioner(
            session=session, repository=WorkpaperSyncRepository(session), artifacts=artifacts,
            project_id=project, wp_id=wp,
        ).ensure(entry_id=ENTRY)
        await session.commit()
    async with Session() as session:
        outcome = await ensure_first_publication(
            session=session, resolution=CanonicalResolutionService(session, artifacts),
            artifacts=artifacts, repository=WorkpaperSyncRepository(session),
            project_id=project, wp_id=wp, entry_id=ENTRY, actor_id=actor,
        )
        await session.commit()
    return {"project": project, "wp": wp, "actor": actor, "store_item": D2.STORE_ITEM_ID,
            "sheet_key": D2.SHEET_KEY, "published": str(outcome.status)}


async def _counts(Session: Any, sa: Any, wp: uuid.UUID) -> dict[str, int]:
    async with Session() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT (SELECT content_revision FROM working_paper WHERE id = :w), "
                    "(SELECT count(*) FROM working_paper_pending_mutation WHERE wp_id = :w), "
                    "(SELECT count(*) FROM working_paper_sync_operation WHERE wp_id = :w), "
                    "(SELECT count(*) FROM working_paper_content_version WHERE wp_id = :w), "
                    "(SELECT count(*) FROM working_paper_oo_room WHERE wp_id = :w)"
                ),
                {"w": wp},
            )
        ).one()
    return dict(zip(("revision", "pending", "operations", "versions", "rooms"), map(int, row)))


async def _last_stage(Session: Any, sa: Any, operation_id: uuid.UUID) -> str | None:
    async with Session() as session:
        return (
            await session.execute(
                sa.text(
                    "SELECT stage FROM working_paper_sync_operation_event "
                    "WHERE operation_id = :op ORDER BY sequence_no DESC LIMIT 1"
                ),
                {"op": operation_id},
            )
        ).scalar_one_or_none()


async def _same_source(Session: Any, *, world: dict[str, Any], artifacts: Any, registration: Any) -> dict[str, Any]:
    """服务端构造 vs 客户端路径（GET store-projection 的 projection → build_projection）逐字节对拍。"""
    from app.services.workpaper_sync import store_materialize as SM
    from app.services.workpaper_sync.content_mutation import _projection_payload
    from app.services.workpaper_sync.definitions import canonical_json_bytes
    from app.services.workpaper_sync.endpoint_payloads import build_projection
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.store_projection_response import (
        compute_store_projection_response,
        read_store_payload,
        resolve_store_projection_provider,
    )

    async with Session() as session:
        reg = await registration(session)
        resolution = CanonicalResolutionService(session, artifacts)
        response = await compute_store_projection_response(
            session=session, project_id=world["project"], wp_id=world["wp"], entry_id=ENTRY,
            registration=reg, resolution=resolution,
        )
        # 客户端拿到的是 JSON：经一次 dumps/loads 往返，与浏览器转一圈同形。
        wire = json.loads(json.dumps(response["projection"], ensure_ascii=False))
        client = build_projection(payload=wire, contract=reg.contract)
        provider = resolve_store_projection_provider(str(reg.adapter_id))
        read = await read_store_payload(session=session, wp_id=world["wp"], provider=provider)
        server = await SM._server_projection(
            session=session, resolution=resolution, registration=reg, provider=provider,
            read=read, project_id=world["project"], wp_id=world["wp"], entry_id=ENTRY,
        )
    keys = "\n".join(str(k) for k in server.values)
    return {
        "equal": canonical_json_bytes(_projection_payload(client))
        == canonical_json_bytes(_projection_payload(server)),
        "field_count": len(server.values),
        "overlay_applied": bool(response["overlay_applied"]),
        "store_rows_present": all(row["rowId"] in keys for row in ROWS),
    }


async def _exercise(Session: Any, sa: Any, *, world: dict[str, Any], artifacts: Any, snap: dict[str, Any]) -> None:
    import dataclasses

    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync import store_materialize as SM
    from app.services.workpaper_sync.adapters.registry import build_production_registry
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    wp, key = world["wp"], (str(world["wp"]), ENTRY)

    async def registration(session: Any) -> Any:
        svc = SimpleNamespace(session=session, registry=build_production_registry())
        return await SR._registration(svc, SimpleNamespace(entry_id=ENTRY, wp_id=wp))

    snap["phases"]["same_source"] = await _same_source(
        Session, world=world, artifacts=artifacts, registration=registration
    )

    builds = {"n": 0}
    original_build = SM._server_projection

    async def counting_build(**kwargs: Any) -> Any:
        builds["n"] += 1
        return await original_build(**kwargs)

    async def call(label: str) -> dict[str, Any]:
        before, builds_before = await _counts(Session, sa, wp), builds["n"]
        started = time.perf_counter()
        async with Session() as session:
            result = await SM.materialize_from_store(
                session=session, resolution=CanonicalResolutionService(session, artifacts),
                registration=await registration(session), project_id=world["project"], wp_id=wp,
                entry_id=ENTRY, user_id=world["actor"], sheet_key=world["sheet_key"], client_edit_epoch=0,
                idempotency_key=f"swp-{label}", secret=_SECRET,
            )
            await session.commit()
        seconds = round(time.perf_counter() - started, 3)
        after, outcome, record = await _counts(Session, sa, wp), result.outcome, SM.STORE_FINGERPRINTS.get(key)
        return {
            "fast_path": result.fast_path,
            "metric_result": outcome.reuse_verdict.metric_result,
            "differences": list(outcome.reuse_verdict.differences)[:3],
            "content_version_id": str(outcome.content_version_id),
            "representation_id": str(outcome.representation_id),
            "artifact_sha256": str(outcome.descriptor.artifact_sha256),
            "room_id": str(outcome.descriptor.room_id),
            "last_stage": await _last_stage(Session, sa, outcome.operation_id),
            "projection_builds": builds["n"] - builds_before,
            "recorded_version": None if record is None else str(record.content_version_id),
            "seconds": seconds,
            **{f"{name}_delta": after[name] - before[name] for name in after},
        }

    async def edit_store() -> None:
        edited = [dict(ROWS[0], currentUnadjusted=999.0), *ROWS[1:]]
        async with Session() as session:
            await session.execute(
                sa.text("UPDATE checklist_responses SET remark = :r WHERE wp_id = :w AND item_id = :i"),
                {"r": json.dumps(edited, ensure_ascii=False), "w": wp, "i": world["store_item"]},
            )
            await session.commit()

    def corrupt(**changes: Any) -> None:
        record = SM.STORE_FINGERPRINTS.get(key)
        if record is None:
            raise _HarnessError("期望此刻已有指纹记录（上一步应是复用命中）")
        SM.STORE_FINGERPRINTS.put(key, dataclasses.replace(record, **changes))

    steps: dict[str, Any] = {}
    snap["phases"]["steps"] = steps
    SM._server_projection = counting_build
    try:
        steps["first"] = await call("first")
        steps["unchanged"] = await call("unchanged")
        await edit_store()
        steps["edited"] = await call("edited")
        steps["after_commit"] = await call("after-commit")
        steps["unchanged_again"] = await call("unchanged-again")
        corrupt(content_version_id=uuid.uuid4())
        steps["stale_version"] = await call("stale-version")
        corrupt(artifact_sha256="0" * 64)
        steps["stale_artifact"] = await call("stale-artifact")
        steps["recovered"] = await call("recovered")
    finally:
        SM._server_projection = original_build


async def _collect() -> dict[str, Any]:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync import canonical_paths as CP
    from app.services.workpaper_sync import phase5_entry_orchestration as ORCH
    from app.services.workpaper_sync import store_materialize as SM
    from app.services.workpaper_sync import target_bound_registration as TB
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.parse_cache import BoundedLruCache, clear_all_parse_caches

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise _HarnessError(
            "直通的判据是「真协调器在真 content version 上真的零 revision」，必须真实 PostgreSQL。"
            "此处**不 skip** —— skip 等于把「没验证」记成「通过」"
        )
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_swp_pg_store_"))
    (base_root / "storage").mkdir(exist_ok=True)
    (base_root / "definition_store").mkdir(exist_ok=True)
    snap: dict[str, Any] = {"schema": schema, "errors": {}, "phases": {}}
    saved = (ORCH._BACKEND_ROOT, CP.BACKEND_ROOT, SR._REGISTRATION_CACHE, SR._REGISTRATION_BUILD_LOCK)
    admin = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off))
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            str(settings.DATABASE_URL), poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        Session = async_sessionmaker(engine, expire_on_commit=False)
        artifacts = CanonicalArtifactRepository(base_root)
        await _setup_schema(engine, sa)
        world = await _seed_and_publish(Session, engine, sa, artifacts=artifacts)
        snap["phases"]["published"] = world["published"]
        # 存储根换到临时根（provider 与生产协调器装配各读一处）；全部进程内缓存从空开始。
        ORCH._BACKEND_ROOT = base_root
        CP.BACKEND_ROOT = base_root
        SR._REGISTRATION_CACHE = BoundedLruCache(maxsize=8)
        SR._REGISTRATION_BUILD_LOCK = None
        TB.clear_target_registration_cache()
        clear_all_parse_caches()
        SM.STORE_FINGERPRINTS.clear()
        await _exercise(Session, sa, world=world, artifacts=artifacts, snap=snap)
    except Exception as exc:  # noqa: BLE001 - 记录不穿透，由守卫断言为空
        snap["errors"]["collect"] = _err(exc)
    finally:
        ORCH._BACKEND_ROOT, CP.BACKEND_ROOT, SR._REGISTRATION_CACHE, SR._REGISTRATION_BUILD_LOCK = saved
        TB.clear_target_registration_cache()
        clear_all_parse_caches()
        SM.STORE_FINGERPRINTS.clear()
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()
            shutil.rmtree(base_root, ignore_errors=True)
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 判据
# ═══════════════════════════════════════════════════════════════════════════

_STEPS = (
    "first", "unchanged", "edited", "after_commit", "unchanged_again",
    "stale_version", "stale_artifact", "recovered",
)


def _step(snap: dict[str, Any], name: str) -> dict[str, Any]:
    return snap["phases"]["steps"][name]


class TestHarness:
    def test_collection_did_not_crash(self, snap: dict[str, Any]) -> None:
        assert snap["errors"] == {}, snap["errors"]

    def test_the_world_was_really_published_and_every_step_measured(self, snap: dict[str, Any]) -> None:
        assert snap["phases"]["published"] == "published"
        assert tuple(snap["phases"]["steps"]) == _STEPS


class TestServerProjectionIsTheClientProjection:
    """需求 6：服务端直取不是第二套投影 —— 与客户端路径逐字节同源。"""

    def test_the_two_paths_serialise_identically(self, snap: dict[str, Any]) -> None:
        same = snap["phases"]["same_source"]
        assert same["equal"] is True, same

    def test_the_comparison_covers_the_overlay_and_the_store_rows(self, snap: dict[str, Any]) -> None:
        """反空转：比的是「基线 ⊕ store」的真投影（有叠加、带 store 行），不是两个空投影。"""
        same = snap["phases"]["same_source"]
        assert same["overlay_applied"] is True, same
        assert same["store_rows_present"] is True, same
        assert same["field_count"] > len(ROWS), same


class TestFingerprintFastPath:
    """需求 3：无改动直通 —— 何时直通、何时必须让路。"""

    def test_a_verified_reuse_records_the_fingerprint(self, snap: dict[str, Any]) -> None:
        first = _step(snap, "first")
        assert first["fast_path"] is False and first["projection_builds"] == 1, first
        assert first["metric_result"] == "hit" and first["revision_delta"] == 0, first
        assert first["recorded_version"] == first["content_version_id"], first

    def test_an_unchanged_store_skips_projection_and_pending_mutation(self, snap: dict[str, Any]) -> None:
        fast, first = _step(snap, "unchanged"), _step(snap, "first")
        assert fast["fast_path"] is True, fast
        assert fast["projection_builds"] == 0, "直通仍构造了投影 —— 省掉的正是这一步"
        assert (fast["pending_delta"], fast["revision_delta"], fast["versions_delta"]) == (0, 0, 0), fast
        assert fast["operations_delta"] == 1, "直通也必须留下 operation 终态（可追溯）"
        assert fast["last_stage"] == "store_fingerprint_reused", fast
        for field in ("content_version_id", "representation_id", "artifact_sha256", "room_id"):
            assert fast[field] == first[field], (field, fast, first)

    def test_an_edit_falls_back_and_commits(self, snap: dict[str, Any]) -> None:
        edited = _step(snap, "edited")
        assert edited["fast_path"] is False and edited["projection_builds"] == 1, edited
        assert edited["metric_result"].startswith("miss_"), edited
        assert (edited["revision_delta"], edited["versions_delta"]) == (1, 1), edited

    def test_a_commit_is_not_trusted_until_reverified(self, snap: dict[str, Any]) -> None:
        """提交之后不记指纹：下一次必须走正常路径真比一次（不把没做过的校验当成做过）。"""
        edited, after = _step(snap, "edited"), _step(snap, "after_commit")
        assert edited["recorded_version"] is None, edited
        assert after["fast_path"] is False and after["projection_builds"] == 1, after
        assert after["metric_result"] == "hit" and after["revision_delta"] == 0, after
        assert after["content_version_id"] == edited["content_version_id"], (after, edited)
        assert after["recorded_version"] == after["content_version_id"], after

    def test_the_fast_path_resumes_after_reverification(self, snap: dict[str, Any]) -> None:
        again, after = _step(snap, "unchanged_again"), _step(snap, "after_commit")
        assert again["fast_path"] is True and again["projection_builds"] == 0, again
        assert again["content_version_id"] == after["content_version_id"], (again, after)

    @pytest.mark.parametrize("name", ["stale_version", "stale_artifact"])
    def test_a_record_that_disagrees_with_the_world_is_not_trusted(
        self, snap: dict[str, Any], name: str
    ) -> None:
        """指纹相同但记录的版本 / substrate 与 preflight 不符 ⇒ 回落正常路径；直通尝试零副作用。"""
        step = _step(snap, name)
        assert step["fast_path"] is False and step["projection_builds"] == 1, step
        assert (step["operations_delta"], step["pending_delta"]) == (1, 1), (
            f"直通尝试泄漏了 operation / pending：{step}"
        )
        assert step["metric_result"] == "hit" and step["revision_delta"] == 0, step
        assert step["recorded_version"] == step["content_version_id"], "记录未被纠正"
        assert _step(snap, "recovered")["fast_path"] is True
