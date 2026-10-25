# -*- coding: utf-8 -*-
"""Task 8 —— adopt-substrate 的**端点级**判据：真 PostgreSQL + 真 ASGI 发 HTTP。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 3.4 / 3.8 / 6.1 / 6.2 / 6.3 / 6.4 / 6.5 / 6.6 / 6.7 / 6.8

═══ 为什么必须真发 HTTP（平台铁律 ㉕）═══

本 spec 前面的 router 判据（Task 6.2 / 6.3）**全是源码锁**：AST 现扫 `except` 分支在不在、
状态码字面量对不对。源码锁证得了「代码里写了这一行」，证不了：

* **鉴权真的跑过** —— `Depends(_services)` → 内层 `get_current_user` 是否真是 401 产生点；
* **依赖链真的接上** —— `_guard` → `_registration` → `compute_adopt_substrate` 的顺序；
* **响应信封** —— 平台 `ResponseWrapperMiddleware` 把 2xx JSON 包成 `{code,message,data}`，
  4xx/5xx 的 `detail` 落在哪里；前端解构写的是 `data?.data ?? data`，两侧必须真对得上。

⇒ 本文件挂**真** `wp_sync_router` + **真** `ResponseWrapperMiddleware`，经 ASGI 发请求。

═══ 注入边界（诚实说明，逐项给理由）═══

替换的只有下面这些，每一项都是**设计上的注入缝**或**外部端口**，不是被测对象：

| 替换 | 为什么不是「把被测链 mock 掉」 |
| --- | --- |
| `get_db` | 指向 scratch schema 的真 session（PG 真库，不是替身） |
| `get_current_user` | 401 的产生点；置 None 即未认证（Requirement 6.1 的否定侧） |
| `_services.probe` | `ProjectVisibilityProbe` 协议实现体，`workflow_locked` 的开关（6.2） |
| `_services.guard` | **真** `SyncEndpointGuard`，只把 visibility / authorize 换成上面那个开关 |
| `_services.registry` | 只替换**查询面**：`register_from_manifest` 覆盖 186 条 entry 实测 25~30s，
  与本任务判据无关；`assert_bidirectional_ready` 返回一份现算装配的 registration |
| `_services.resolution` | `substrate` 解析端口。**真** `_resolve_published_substrate` 照旧跑
  （含 `is_file()` fail-closed 判断），只是不去发布一份真 artifact |
| `registration.adapter.extract` | artifact→Projection 的适配边界。返回的是**真** `Projection`，
  由**真**引擎 `phase5_row_table_sheet.build_store_projection` 现算 |

🔴 **被测链一个都没替**：`compute_adopt_substrate` / `compute_plan_for_adopt` /
`apply_overwrite_deletions` / `verify_plan_digest` / `mirror_projection_into_store` /
`prune_undeclared_rows` 全是生产对象，本文件 §3 用「对象同一性 + 只有它们能产生的可观测
副作用」两路证明它们真在跑（`unittest.mock` 一次都没用）。

═══ 载体为什么是 `f4.accounts_payable_detail`（现算选出，不是随手挑）═══

需要同时满足三条：① `store_merge_plan_or_skip` 有 plan 且是**单 item rows** 形态
（`mirror_projection_into_store` 走单 item 分支）② 行枚举器**可枚举**（否则 plan 三清单恒空，
8.5 的对账在空集上恒真）③ merge 门面签名与 `store_mirror` 的调用形态兼容。
探针逐 adapter 实测（51 条 store-backed）后 f4 是最小的一条满足者；🔴 常量一律从 provider
现读（`ADAPTER_ID` / `ENTRY_ID` / `STORE_ITEM_ID` / `ROW_IDENTITY_STORE_KEY`），本文件不写字面量。

═══ 隔离与采集 ═══

scratch schema `tmp_aos8_endpoint_<hex>`，结束 `DROP SCHEMA CASCADE`。全部场景由**一次**
`asyncio.run` 跑完落进快照（module fixture）—— 每个测试各自开 async 会污染共享连接池
（域内 Task 21~29 实测：第二个起 `NoneType has no attribute send`）。采集阶段异常一律
**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf` 只列 FAILED 不列 ERROR
⇒ 定向变异看不到预期失败项 ⇒ 误判 GREEN。`test_no_phase_crashed_during_collection` 是这条
决定的另一半。`DATABASE_URL` 非 PostgreSQL 时**直接失败不 skip**。

伴生件 `test_aos_adopt_endpoint_injection_and_atomicity.py` 承 §3（8.3 注入形态自我约束）/
§4（8.4 原子性）/ §5（8.5 真库对账），共用本文件的**同一次**采集（`collect_once()`）——
两份各跑一次采集就是两套 schema、两倍真库写入。
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_aos8_endpoint_"



# 🔴 世界构件住伴生模块 `aos8_endpoint_world`（harness / 判据切口，见其 docstring）。
#    **顶层模块名** import：该目录无 `__init__.py`，pytest 走 `prepend`，写成
#    `tests.workpaper_sync.…` 会拿到第二个模块实例、载体常量与替身类当场分家。
from aos8_endpoint_world import (  # noqa: E402
    CARRIER_ADAPTER_ID,
    CARRIER_ENTRY_ID,
    CARRIER_IDENTITY_KEY,
    CARRIER_ITEM_ID,
    STUB_DDL as _STUB_DDL,
    HarnessError as _HarnessError,
    InjectingSession as _InjectingSession,
    StubAdapter as _StubAdapter,
    StubRegistry as _StubRegistry,
    StubResolution as _StubResolution,
    Switchboard as _Switchboard,
    base_store_payload,
    base_substrate_payload,
    collect_multi_item_scenarios,
    collect_stale_by_store_change_scenario,
    func_ast,
    handler_except_map,
    http_statuses,
    reachable_statuses,
    router_ast,
    err as _err,
    error_code,
    error_detail,
    identities_in_store,
    unwrap,
)


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    import httpx
    from fastapi import Depends, FastAPI, HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.middleware.response import ResponseWrapperMiddleware
    from app.models.audit_log_models import AuditLogEntry
    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync.adapters.registry import RegistryError
    from app.services.workpaper_sync.contracts import load_contract
    from app.services.workpaper_sync.endpoint_guard import ScopeClaimCodec, SyncEndpointGuard
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 8 的判据是「HTTP 响应 + 库里行集」的组合（状态码分支 / digest 门 / "
            "原子性零残留 / dry_run 与落库逐元素对账），必须真实 PostgreSQL；当前 "
            f"DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "server_version": None,
        "harness_errors": {},
        "scenarios": {},
        "world": {},
    }

    def _phase_failed(name: str, exc: BaseException) -> None:
        snap["harness_errors"][name] = _err(exc)

    engine = None
    tmp_dir = Path(tempfile.mkdtemp(prefix="aos8_artifact_"))
    try:
        async with admin.connect() as conn:
            snap["server_version"] = (
                await conn.exec_driver_sql("SELECT version()")
            ).scalar_one()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            for stmt in (s.strip() for s in _STUB_DDL.split(";")):
                if stmt:
                    await conn.exec_driver_sql(stmt)
            await conn.run_sync(AuditLogEntry.__table__.create)

        project = uuid.uuid4()
        wp_index = uuid.uuid4()
        user = uuid.uuid4()
        base_revision = 7
        scenario_names = (
            "unauthenticated",
            "workflow_locked",
            "revision_conflict",
            "substrate_pointer_missing",
            "substrate_file_missing",
            "contract_required",
            "adapter_not_ready",
            "digest_flow",
            "reconcile",
            "inject_after_business_write",
            "inject_after_deletion_side",
            "inject_before_audit",
            "atomicity_positive_control",
            "digest_stale_by_store_change",
            "multi_item_positive_control",
            "multi_item_inject_mid_deletion",
        )
        wps = {name: uuid.uuid4() for name in scenario_names}
        async with Session() as s:
            await s.execute(
                sa.text("INSERT INTO projects (id, name) VALUES (:p, 'aos8')"), {"p": str(project)}
            )
            await s.execute(
                sa.text("INSERT INTO wp_index (id, project_id) VALUES (:i, :p)"),
                {"i": str(wp_index), "p": str(project)},
            )
            for name, wp in wps.items():
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper (id, project_id, wp_index_id, content_revision)"
                        " VALUES (:w, :p, :i, :rev)"
                    ),
                    {"w": str(wp), "p": str(project), "i": str(wp_index), "rev": base_revision},
                )
            await s.commit()
        snap["world"] = {
            "project": str(project),
            "user": str(user),
            "base_revision": base_revision,
            "wps": {k: str(v) for k, v in wps.items()},
            "adapter_id": CARRIER_ADAPTER_ID,
            "entry_id": CARRIER_ENTRY_ID,
            "item_id": CARRIER_ITEM_ID,
            "identity_key": CARRIER_IDENTITY_KEY,
        }

        artifact = tmp_dir / "aos8-substrate.xlsx"
        artifact.write_bytes(b"PK\x03\x04aos8")
        contract = load_contract(CARRIER_ADAPTER_ID)

        async def _seed_store(wp: uuid.UUID, payload: str | None) -> None:
            async with Session() as s:
                await s.execute(
                    sa.text("DELETE FROM checklist_responses WHERE wp_id = :w"), {"w": str(wp)}
                )
                if payload is not None:
                    await s.execute(
                        sa.text(
                            "INSERT INTO checklist_responses (project_id, wp_id, item_id, remark)"
                            " VALUES (:p, :w, :item, :val)"
                        ),
                        {
                            "p": str(project),
                            "w": str(wp),
                            "item": CARRIER_ITEM_ID,
                            "val": payload,
                        },
                    )
                await s.commit()

        async def _read_store(wp: uuid.UUID) -> list[dict[str, Any]]:
            """独立 session 读整张表快照（8.4「库一字节未变」的比对面）。"""
            async with Session() as s:
                rows = (
                    await s.execute(
                        sa.text(
                            "SELECT id, item_id, remark, content_version, "
                            "       created_at, updated_at "
                            "FROM checklist_responses WHERE wp_id = :w ORDER BY item_id"
                        ),
                        {"w": str(wp)},
                    )
                ).mappings().all()
            return [
                {
                    "id": str(r["id"]),
                    "item_id": r["item_id"],
                    "remark": r["remark"],
                    "content_version": r["content_version"],
                    "created_at": r["created_at"].isoformat(),
                    "updated_at": r["updated_at"].isoformat(),
                }
                for r in rows
            ]

        async def _audit_rows() -> list[dict[str, Any]]:
            async with Session() as s:
                rows = (
                    await s.execute(
                        sa.text(
                            "SELECT action_type, entry_hash, payload FROM audit_log_entries"
                            " ORDER BY ts, entry_hash"
                        )
                    )
                ).mappings().all()
            return [
                {"action": r["action_type"], "hash": r["entry_hash"], "payload": r["payload"]}
                for r in rows
            ]

        # ═══ ASGI app：真 router + 真中间件（信封是对外契约的一部分）
        board = _Switchboard()
        registry = _StubRegistry()
        resolution = _StubResolution(artifact)
        adapter = _StubAdapter(contract)
        registry.registration = SimpleNamespace(
            adapter_id=CARRIER_ADAPTER_ID, contract=contract, adapter=adapter
        )
        current: dict[str, Any] = {"user": SimpleNamespace(id=user)}
        injector: dict[str, Any] = {"session": None, "fail_writes": None, "fail_audit": False}

        app = FastAPI()
        app.add_middleware(ResponseWrapperMiddleware)
        app.include_router(SR.router)

        async def _override_db():
            async with Session() as inner:
                proxy = _InjectingSession(inner)
                proxy.fail_after_store_writes = injector["fail_writes"]
                proxy.fail_before_audit = bool(injector["fail_audit"])
                injector["session"] = proxy
                yield proxy

        async def _override_user():
            holder = current["user"]
            if holder is None:
                # 生产 `get_current_user` 的同一形态：未认证即 401（router docstring 明写
                # 它是**唯一** 401 产生点）。
                raise HTTPException(status_code=401, detail="未认证")
            return holder

        async def _services_override(db=Depends(get_db), user=Depends(get_current_user)):
            from dataclasses import replace

            base = SR.build_sync_services(db, user)
            repo = WorkpaperSyncRepository(db)
            return replace(
                base,
                repo=repo,
                registry=registry,  # type: ignore[arg-type]
                resolution=resolution,  # type: ignore[arg-type]
                probe=board,  # type: ignore[arg-type]
                guard=SyncEndpointGuard(
                    repository=repo,
                    visibility=board,
                    authorize=board.authorize,
                    claim_codec=ScopeClaimCodec("aos8-endpoint-secret"),
                    read_only_actions=SR._READ_ONLY_ACTIONS,
                ),
            )

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[SR._services] = _services_override
        snap["override_keys"] = sorted(
            f"{k.__module__}.{k.__name__}" for k in app.dependency_overrides
        )

        def _url(wp: uuid.UUID, entry: str = CARRIER_ENTRY_ID) -> str:
            return (
                f"/api/projects/{project}/workpapers/{wp}/sync/entries/"
                f"{entry}/adopt-substrate"
            )

        async def _seed_many(wp: uuid.UUID, payloads: dict[str, str]) -> None:
            async with Session() as s:
                await s.execute(
                    sa.text("DELETE FROM checklist_responses WHERE wp_id = :w"), {"w": str(wp)}
                )
                for item, payload in payloads.items():
                    await s.execute(
                        sa.text(
                            "INSERT INTO checklist_responses (project_id, wp_id, item_id, remark)"
                            " VALUES (:p, :w, :item, :val)"
                        ),
                        {"p": str(project), "w": str(wp), "item": item, "val": payload},
                    )
                await s.commit()

        scen = snap["scenarios"]
        adapter.payload = base_substrate_payload()
        # 🔴 两个 client 的差别只有 `raise_app_exceptions`：默认 True 会把 app 内未处理异常
        #    **原样抛给调用方**，于是 8.4 的注入场景根本拿不到响应、「HTTP 5xx」这条判据无从谈起。
        #    置 False 让 Starlette 的 `ServerErrorMiddleware` 照生产那样吐 500 响应体。
        strict = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://aos8"
        )
        lenient = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://aos8",
        )
        async with strict as client, lenient as client_5xx:

            async def _run(
                name: str,
                *,
                body: dict[str, Any],
                before_payload: str | None = None,
                fail_writes: int | None = None,
                fail_audit: bool = False,
            ) -> dict[str, Any]:
                wp = wps[name]
                await _seed_store(wp, base_store_payload() if before_payload is None else before_payload)
                before = await _read_store(wp)
                audit_before = await _audit_rows()
                injector["fail_writes"] = fail_writes
                injector["fail_audit"] = fail_audit
                injecting = fail_writes is not None or fail_audit
                try:
                    resp = await (client_5xx if injecting else client).post(_url(wp), json=body)
                    observed = {"status": resp.status_code, "body": None, "raised": None}
                    try:
                        observed["body"] = resp.json()
                    except ValueError:
                        observed["body"] = {"_text": resp.text[:200]}
                except Exception as exc:  # noqa: BLE001 - 异常穿透也要落进快照而不是崩采集
                    observed = {"status": None, "body": None, "raised": _err(exc)}
                finally:
                    injector["fail_writes"] = None
                    injector["fail_audit"] = False
                session = injector["session"]
                observed.update(
                    {
                        "wp": str(wp),
                        "store_before": before,
                        "store_after": await _read_store(wp),
                        "audit_before": audit_before,
                        "audit_after": await _audit_rows(),
                        "store_writes": getattr(session, "store_writes", None),
                        "commits": getattr(session, "commits", None),
                        "rollbacks": getattr(session, "rollbacks", None),
                    }
                )
                scen[name] = observed
                return observed

            # ── 8.1 ① 401 未认证（唯一 401 产生点：内层 get_current_user）
            try:
                current["user"] = None
                await _run("unauthenticated", body={"dry_run": True})
            except Exception as exc:  # noqa: BLE001
                _phase_failed("unauthenticated", exc)
            finally:
                current["user"] = SimpleNamespace(id=user)

            # ── 8.1 ② 403 workflow_locked（写 action 在锁定下被拒；与 404 分型）
            try:
                board.workflow_locked = True
                await _run("workflow_locked", body={"dry_run": True})
            except Exception as exc:  # noqa: BLE001
                _phase_failed("workflow_locked", exc)
            finally:
                board.workflow_locked = False

            # ── 8.1 ③ 409 expected_revision 不符
            try:
                await _run(
                    "revision_conflict",
                    body={"dry_run": False, "expected_revision": base_revision + 1},
                )
            except Exception as exc:  # noqa: BLE001
                _phase_failed("revision_conflict", exc)

            # ── 8.1 ④ 409 无已发布 substrate（两个子分支：指针缺失 / 文件缺失）
            #    🔴 必须**同时**断言「409」与「store 行数未变」—— 只看状态码排除不了空覆盖。
            for name, mode in (
                ("substrate_pointer_missing", "pointer_missing"),
                ("substrate_file_missing", "file_missing"),
            ):
                try:
                    resolution.mode = mode
                    await _run(name, body={"dry_run": False})
                except Exception as exc:  # noqa: BLE001
                    _phase_failed(name, exc)
                finally:
                    resolution.mode = "ok"

            # ── 8.1 ⑤ 422：**两个**产生点各一例（现算映射表的偏差之一，见 §1）
            try:
                registry.registration = SimpleNamespace(
                    adapter_id=CARRIER_ADAPTER_ID, contract=None, adapter=adapter
                )
                await _run("contract_required", body={"dry_run": False})
            except Exception as exc:  # noqa: BLE001
                _phase_failed("contract_required", exc)
            finally:
                registry.registration = SimpleNamespace(
                    adapter_id=CARRIER_ADAPTER_ID, contract=contract, adapter=adapter
                )
            try:
                registry.registry_error = RegistryError("harness：本 entry 无可用 adapter")
                await _run("adapter_not_ready", body={"dry_run": False})
            except Exception as exc:  # noqa: BLE001
                _phase_failed("adapter_not_ready", exc)
            finally:
                registry.registry_error = None

            # ── 8.2 plan_digest：dry_run 取 digest → 带**错误** digest ⇒ 409 且 store 未变
            #    → 带**正确** digest ⇒ 不是 409（正向对照，否则「409」可能只是恒拒）
            try:
                wp = wps["digest_flow"]
                await _seed_store(wp, base_store_payload())
                before = await _read_store(wp)
                dry = await client.post(_url(wp), json={"dry_run": True})
                dry_body = dry.json()
                plan_wire = dry_body.get("data", dry_body) if isinstance(dry_body, dict) else {}
                digest = str(plan_wire.get("plan_digest") or "")
                stale = ("f" if digest[:1] != "f" else "0") + digest[1:]
                after_dry = await _read_store(wp)
                bad = await client.post(
                    _url(wp), json={"dry_run": False, "plan_digest": stale}
                )
                after_bad = await _read_store(wp)
                good = await client.post(
                    _url(wp), json={"dry_run": False, "plan_digest": digest}
                )
                after_good = await _read_store(wp)
                scen["digest_flow"] = {
                    "wp": str(wp),
                    "dry_status": dry.status_code,
                    "dry_envelope": dry_body,
                    "plan_wire": plan_wire,
                    "digest": digest,
                    "stale_digest": stale,
                    "bad_status": bad.status_code,
                    "bad_body": bad.json(),
                    "good_status": good.status_code,
                    "good_body": good.json(),
                    "store_before": before,
                    "store_after_dry": after_dry,
                    "store_after_bad": after_bad,
                    "store_after_good": after_good,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("digest_flow", exc)

            # ── 8.5 真库对账：同一 substrate 与同一 store 版本下，dry_run 三清单 == 实际落库
            try:
                wp = wps["reconcile"]
                await _seed_store(wp, base_store_payload())
                before = await _read_store(wp)
                dry = await client.post(_url(wp), json={"dry_run": True})
                dry_body = dry.json()
                wire = dry_body.get("data", dry_body) if isinstance(dry_body, dict) else {}
                real = await client.post(_url(wp), json={"dry_run": False})
                after = await _read_store(wp)
                scen["reconcile"] = {
                    "wp": str(wp),
                    "dry_status": dry.status_code,
                    "plan_wire": wire,
                    "real_status": real.status_code,
                    "real_body": real.json(),
                    "store_before": before,
                    "store_after": after,
                    "audit_after": await _audit_rows(),
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("reconcile", exc)

            # ── 8.4 原子性：三个注入点各一例（全部在 merge 之后 / 统一 commit 之前）
            for name, kwargs in (
                ("inject_after_business_write", {"fail_writes": 1}),
                ("inject_after_deletion_side", {"fail_writes": 2}),
                ("inject_before_audit", {"fail_audit": True}),
            ):
                try:
                    await _run(name, body={"dry_run": False}, **kwargs)  # type: ignore[arg-type]
                except Exception as exc:  # noqa: BLE001
                    _phase_failed(name, exc)

            # ── 8.4 正向对照：不注入时**确实**写成功了（否则「库未变」在空操作上恒真）
            try:
                await _run("atomicity_positive_control", body={"dry_run": False})
            except Exception as exc:  # noqa: BLE001
                _phase_failed("atomicity_positive_control", exc)

            # ── 采集体住世界模块（纯行数门禁所迫），判据在伴生件 §2 / §4。
            ctx = SimpleNamespace(
                scen=scen,
                wps=wps,
                registry=registry,
                resolution=resolution,
                injector=injector,
                client=client,
                client_5xx=client_5xx,
                seed_store=_seed_store,
                seed_many=_seed_many,
                read_store=_read_store,
                audit_rows=_audit_rows,
                url=_url,
                phase_failed=_phase_failed,
                carrier_contract=contract,
                carrier_adapter=adapter,
            )
            # 8.2 的第二种过期：**改动 store** 使 digest 过期（tasks.md 逐字那一种）。
            await collect_stale_by_store_change_scenario(ctx)
            # 8.4 多 item 场景（上游实测过的「部分写入」事故形态）：载体换成 5 item 的 f3，
            # 注入点落在**删除侧中途** ⇒ 后面几个 item 的删除还没发生 = 真部分写入。
            await collect_multi_item_scenarios(ctx)

        snap["probe_calls"] = list(board.probe_calls)
        snap["authorize_calls"] = list(board.authorize_calls)
        snap["resolution_calls"] = list(resolution.calls)
        snap["adapter_extract_calls"] = adapter.calls
        snap["registry_ready_calls"] = list(registry.ready_calls)
    except BaseException as exc:  # noqa: BLE001 - 采集阶段异常记录不穿透
        _phase_failed("collect", exc)
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            _phase_failed("teardown_schema", exc)
        await admin.dispose()
        try:
            for leftover in tmp_dir.glob("*"):
                leftover.unlink()
            tmp_dir.rmdir()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("teardown_tmp", exc)
    return snap


_SNAPSHOT: dict[str, Any] | None = None


def collect_once() -> dict[str, Any]:
    """**唯一**一次采集（伴生件共用它）。两份各跑一次就是两套 schema、两倍真库写入。"""
    global _SNAPSHOT
    if _SNAPSHOT is None:
        _SNAPSHOT = asyncio.run(_collect())
    return _SNAPSHOT


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return collect_once()


# ═══════════════════════════════════════════════════════════════════════════════
# §0 采集完整性（记录不穿透的另一半）
# ═══════════════════════════════════════════════════════════════════════════════


class TestCollectionIntegrity:
    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """任一阶段崩掉 ⇒ 下面每条判据都在看一个残缺快照（假绿）。"""
        assert snap["harness_errors"] == {}, snap["harness_errors"]

    def test_it_really_ran_on_postgresql(self, snap: dict[str, Any]) -> None:
        assert "PostgreSQL" in str(snap["server_version"]), snap["server_version"]
        assert str(snap["schema"]).startswith(_SCHEMA_PREFIX)

    def test_every_scenario_was_collected(self, snap: dict[str, Any]) -> None:
        missing = [
            name
            for name in (
                "unauthenticated",
                "workflow_locked",
                "revision_conflict",
                "substrate_pointer_missing",
                "substrate_file_missing",
                "contract_required",
                "adapter_not_ready",
                "digest_flow",
                "reconcile",
                "inject_after_business_write",
                "inject_after_deletion_side",
                "inject_before_audit",
                "atomicity_positive_control",
                "digest_stale_by_store_change",
                "multi_item_positive_control",
                "multi_item_inject_mid_deletion",
            )
            if name not in snap["scenarios"]
        ]
        assert not missing, f"未采集的场景：{missing}"


# ═══════════════════════════════════════════════════════════════════════════════
# §1 Task 8.1 —— 状态码映射表**现算** + 五个分支各一例真 HTTP
#
# 🔴 任务书写「五个状态码分支」。现算的结论是：**handler 自身的 `except` 链恰 5 支**
#    （409×3 / 500 / 422），而本端点**可达**的状态码是 **7** 个 —— 偏差逐条登记在
#    `test_reachable_status_codes_exceed_the_five_named_branches` 的断言文案里，
#    不为了凑「五」而漏登记。
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatusCodeMapIsRecomputed:
    """**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**"""

    def test_the_handler_except_chain_maps_each_branch_to_exactly_one_status(self) -> None:
        rows = handler_except_map(func_ast(router_ast(), "adopt_substrate"))
        assert rows, "handler 里一个 `except` 都没找到 —— 提取器坏了（不是端点没映射）"
        bad = [(exc, codes) for exc, codes in rows if len(codes) != 1]
        assert not bad, f"每个 except 分支应恰 1 个状态码，异常项：{bad}"
        assert {codes[0] for _exc, codes in rows} == {409, 422, 500}, rows

    def test_reachable_status_codes_exceed_the_five_named_branches(self) -> None:
        """🔴 现算偏差登记：任务书说「五个」，可达码实为 **7** 个，且 422 有**两个**产生点。"""
        reachable = reachable_statuses(router_ast())
        named = {401, 403, 409, 422}  # 6.1~6.5 那五条 AC 只用到 4 个不同码（两条都是 409）
        assert named <= set(reachable), f"五条 AC 的状态码未全部可达：{sorted(reachable)}"
        extra = sorted(set(reachable) - named)
        assert extra == [404, 500, 503], (
            "可达状态码集合变了 —— 原现算值 {401,403,404,409,422,500,503}（7 个）。"
            f"当前额外可达：{extra}；全表：{ {k: v for k, v in reachable.items()} }"
        )
        assert len(reachable[422]) >= 2, (
            "422 应有**两个**产生点（handler 兜底 `AdoptSubstrateError` 与 "
            f"`_registration` 的 adapter 未就绪），实得：{reachable[422]}"
        )

    def test_the_extractor_really_reads_the_handler(self) -> None:
        """变异反证：把 500 那支 `except` 从 AST 里摘掉 ⇒ 可达集合必须少掉 500。"""
        import copy

        tree = copy.deepcopy(router_ast())
        handler = func_ast(tree, "adopt_substrate")
        removed = 0
        for node in ast.walk(handler):
            if not isinstance(node, ast.Try):
                continue
            keep = [c for c in node.handlers if 500 not in http_statuses(c)]
            removed += len(node.handlers) - len(keep)
            node.handlers = keep
        assert removed == 1, f"应恰摘掉 1 支 500 分支，实得 {removed}"
        assert 500 in reachable_statuses(router_ast())
        after = reachable_statuses(tree)
        assert 500 not in after or "handler" not in " ".join(after.get(500, ())), (
            "摘掉 500 分支后仍认为 handler 能产生 500 ⇒ 提取器没在读 handler（判据失效）"
        )


class TestFiveBranchesOverRealHttp:
    """五个状态码分支各一例，全部**真发 HTTP**。

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    """

    def test_401_when_no_identity(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["unauthenticated"]
        assert obs["status"] == 401, obs["body"]
        assert obs["store_writes"] == 0 and obs["commits"] == 0

    def test_403_when_workflow_locked(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["workflow_locked"]
        assert obs["status"] == 403, obs["body"]
        assert error_code(obs["body"]) == "sync_workflow_locked", obs["body"]

    def test_409_when_expected_revision_does_not_match(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["revision_conflict"]
        assert obs["status"] == 409, obs["body"]
        assert error_code(obs["body"]) == "adopt_revision_conflict", obs["body"]
        assert str(snap["world"]["base_revision"]) in str(error_detail(obs["body"]))

    @pytest.mark.parametrize(
        "name", ["substrate_pointer_missing", "substrate_file_missing"]
    )
    def test_409_when_no_published_substrate_and_store_is_untouched(
        self, snap: dict[str, Any], name: str
    ) -> None:
        """🔴 同时断言「409」**与**「store 未变」—— 只看状态码排除不了空覆盖（design § Error Handling）。"""
        obs = snap["scenarios"][name]
        assert obs["status"] == 409, obs["body"]
        assert error_code(obs["body"]) == "adopt_substrate_not_published", obs["body"]
        assert obs["store_before"] == obs["store_after"], "store 被动过了（含 updated_at）"
        assert identities_in_store(obs["store_before"]) == identities_in_store(obs["store_after"])
        assert len(identities_in_store(obs["store_after"])) == 2, "行数分母为 0 ⇒ 判据空跑"
        assert obs["store_writes"] == 0 and obs["audit_before"] == obs["audit_after"]

    def test_422_has_two_distinct_producers_with_distinct_error_codes(
        self, snap: dict[str, Any]
    ) -> None:
        contract = snap["scenarios"]["contract_required"]
        registry = snap["scenarios"]["adapter_not_ready"]
        assert contract["status"] == 422 and registry["status"] == 422
        assert error_code(contract["body"]) == "adopt_contract_required", contract["body"]
        assert error_code(registry["body"]) and error_code(registry["body"]) != error_code(
            contract["body"]
        ), (
            "两个 422 产生点的 error_code 必须可区分，否则前端无从判「没契约」还是"
            f"「adapter 没就绪」：{registry['body']}"
        )

    def test_the_five_branches_are_not_all_the_same_code(self, snap: dict[str, Any]) -> None:
        """反空转：五条判据若全落在同一个码上，「分支各一例」就没有区分度。"""
        codes = [
            snap["scenarios"][name]["status"]
            for name in (
                "unauthenticated",
                "workflow_locked",
                "revision_conflict",
                "substrate_pointer_missing",
                "contract_required",
            )
        ]
        assert codes == [401, 403, 409, 409, 422], codes
        assert len(set(codes)) == 4, codes
