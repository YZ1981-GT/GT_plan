"""Task 75 的「逐 entry 真调 adapter」探针 —— 单独一个模块，避免门禁继续膨胀。

═══ 为什么需要这个探针 ═══

`_task44_request_path_probe.probe_request_path_registration()` 只证明**注册路径**兑现：
D2/G7/H1 三个 pilot 的 adapter 真的被 `register_from_manifest()` 注册进 registry。但它
从不消费这些 adapter —— 拿到 ``('d2.receivable_detail', 'g7...', 'h1...')`` 就停了。

Task 75 的第五 bullet 因此登记了另一半欠账：「对 D2/G7/H1 三个已注册 entry 逐 entry
**真调** extract / materialize 以证明 adapter 能解析 published representation 并返回
frozen identity」。注册成功只说明 matcher/bundle/contract 校验通过，adapter 在真实的
published representation 上能不能解析、返回的 Projection 是否携带**注册时冻结的那份**
identity，只有真调才知道。这正是「假绿第①源」—— additive 注入即死代码：加一个
adapter 类，注册全绿，但没有任何消费方。

═══ 三个刻意的判据选择 ═══

1. **用 registry 里冻结的 adapter，不重新构造。**
   重新 `build_excel_adapter()` 一份再调它等于自我比对：新构造的 adapter 携带的是
   本模块现算的 definitions，测不出注册链路有没有把错的那份 definitions 冻结进去。
   本探针走 `registry.resolve_for_entry(entry_id).adapter`，消费的是注册时的产物。

2. **published representation 的物理路径现读，不硬编码。**
   路径口径与四个 pilot 的 provider 完全一致：
   `resolve_visible_current_representation_id(session, entry_id=...)` 取可见 current
   pointer，再从 `working_paper_content_representation` join `working_paper_artifact`
   读 `relative_path`。manifest 里**没有** representation 路径字段 —— 它是运行时供给，
   写死等于把某个项目的 storage 目录编进代码。

3. **`unverifiable` 与 `failed` 必须分型。**
   拿不到真库、没有 published representation、artifact 文件不在磁盘 —— 这些都是
   「环境不可得」，记 ``unverifiable``；adapter 抛异常、identity 漂移、返回类型不对
   —— 这些是「实现有问题」，记 ``failed``。混为一谈会把没有数据库的 CI 跑成假红，
   也会把环境缺失误读成实现缺陷。AC 5.12 要求「失败原因可操作」，分型是它的前提。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["probe_entry_adapter_roundtrip"]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def probe_entry_adapter_roundtrip() -> dict[str, Any]:
    """逐已注册 entry 真调 ``extract`` / ``materialize`` / ``extract`` round-trip。

    :returns: 结构化结果字典，含 ``summary``（registered / verified / failed /
        unverifiable 四计数）、逐 entry 明细，以及 ``note``（环境不可得时的原因）。

    🔴 **独立 ``NullPool`` 引擎 + ``dispose()``**：门禁里多处各自 ``asyncio.run``，
    共享连接池会把上一次 event loop 里的连接留下，第二次取到它就报
    ``'NoneType' object has no attribute 'send'`` —— 那是假 ERROR 态，会被误读成
    「库不可达」（Task 44 / Task 61 gate 各自踩过同一个坑）。
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
        from app.models.workpaper_sync_models import (
            WorkpaperArtifact,
            WorkpaperContentRepresentation,
        )
        from app.services.workpaper_sync.adapters import registry as registry_mod
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.projection_target_resolution import (
            resolve_visible_current_representation_id,
        )
    except Exception as exc:  # noqa: BLE001 - 环境不可得
        return {
            "verified": 0,
            "failed": 0,
            "unverifiable": 0,
            "summary": {"registered": 0, "verified": 0, "failed": 0, "unverifiable": 0},
            "note": f"导入失败（环境不可得）：{type(exc).__name__}: {exc}"[:300],
        }

    async def _run() -> dict[str, Any]:
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        session_factory: Any = async_sessionmaker(engine, expire_on_commit=False)
        entries: list[dict[str, Any]] = []
        summary = {"registered": 0, "verified": 0, "failed": 0, "unverifiable": 0}

        async with session_factory() as session:
            reg = registry_mod.build_production_registry()
            outcome = await reg.register_from_manifest(session=session)

            for entry_id in outcome.registered_entry_ids:
                item: dict[str, Any] = {"entry_id": entry_id}
                entries.append(item)
                summary["registered"] += 1
                try:
                    registration = reg.resolve_for_entry(entry_id)
                except Exception as exc:  # noqa: BLE001
                    item.update(verdict="failed", detail=f"resolve_for_entry: {exc}"[:200])
                    summary["failed"] += 1
                    continue

                adapter = registration.adapter
                contract = registration.contract
                item["adapter_id"] = registration.adapter_id
                if contract is None:
                    item.update(
                        verdict="failed",
                        detail="注册记录 contract 为空 —— 双向 entry 必须有 approved contract",
                    )
                    summary["failed"] += 1
                    continue

                # ── published representation 物理路径（provider 同口径）──
                rep_id = await resolve_visible_current_representation_id(
                    session, entry_id=entry_id
                )
                if rep_id is None:
                    item.update(
                        verdict="unverifiable",
                        detail="无可见 current published representation —— 供给不足，非实现缺陷",
                    )
                    summary["unverifiable"] += 1
                    continue

                row = (
                    await session.execute(
                        select(WorkpaperContentRepresentation, WorkpaperArtifact)
                        .join(
                            WorkpaperArtifact,
                            WorkpaperArtifact.id
                            == WorkpaperContentRepresentation.artifact_id,
                        )
                        .where(WorkpaperContentRepresentation.id == rep_id)
                    )
                ).first()
                if row is None:
                    item.update(verdict="unverifiable", detail="representation 或 artifact 行不存在")
                    summary["unverifiable"] += 1
                    continue
                rep_row, artifact_row = row

                # artifact 的 substrate 形态直接取 `build_excel_adapter("html_to_oo")`
                # 的封闭词表：published representation = (canonical, published)。
                # 🔴 注意 artifact 表的 kind 不是 "published" —— 那是 adapter 构造时给
                # substrate_role 的词表，两者不是同一维，判错会把供给充足的 entry 误判成缺供给。
                if artifact_row.kind != "canonical" or artifact_row.state != "published":
                    item.update(
                        verdict="unverifiable",
                        detail=(
                            f"artifact kind={artifact_row.kind!r} state={artifact_row.state!r}"
                            " —— 仅 kind='canonical' 且 state='published' 才是可提取 substrate"
                        ),
                    )
                    summary["unverifiable"] += 1
                    continue

                artifact = _BACKEND_ROOT / str(artifact_row.relative_path)
                if not artifact.exists():
                    item.update(verdict="unverifiable", detail=f"artifact 不在磁盘: {artifact}")
                    summary["unverifiable"] += 1
                    continue

                # ── 真调 extract（同步方法）──
                try:
                    projection = adapter.extract(artifact=artifact, contract=contract)
                except Exception as exc:  # noqa: BLE001
                    item.update(
                        verdict="failed", detail=f"extract: {type(exc).__name__}: {exc}"[:200]
                    )
                    summary["failed"] += 1
                    continue

                if not isinstance(projection, Projection):
                    item.update(
                        verdict="failed",
                        detail=f"extract 返回 {type(projection).__name__}，期望 Projection",
                    )
                    summary["failed"] += 1
                    continue

                # ── frozen identity 必须与注册时契约逐字段一致 ──
                drift: list[str] = []
                if projection.contract_id != contract.contract_id:
                    drift.append(
                        f"contract_id {projection.contract_id!r} != {contract.contract_id!r}"
                    )
                if projection.document_type != contract.document_type:
                    drift.append(
                        f"document_type {projection.document_type!r}"
                        f" != {contract.document_type!r}"
                    )

                # ── 真调 materialize → extract round-trip ──
                with tempfile.TemporaryDirectory(prefix="task75_entry_probe_") as td:
                    out_path = Path(td) / "reprojection.xlsx"
                    try:
                        adapter.materialize(
                            substrate=artifact, projection=projection, output=out_path,
                            contract=contract,
                        )
                        re_projection = adapter.extract(artifact=out_path, contract=contract)
                        roundtrip_ok = (
                            out_path.exists()
                            and isinstance(re_projection, Projection)
                            and re_projection.contract_id == contract.contract_id
                            and len(re_projection.stable_keys()) == len(projection.stable_keys())
                        )
                    except Exception as exc:  # noqa: BLE001
                        roundtrip_ok = False
                        drift.append(f"round-trip: {type(exc).__name__}: {exc}"[:160])

                item["stable_key_count"] = len(projection.stable_keys())
                item["semantic_version"] = str(getattr(projection, "semantic_version", None))
                if drift:
                    item.update(verdict="failed", detail="; ".join(drift))
                    summary["failed"] += 1
                else:
                    item["verdict"] = "verified"
                    item["roundtrip_ok"] = roundtrip_ok
                    summary["verified"] += 1

            return {
                "summary": summary,
                "entries": entries,
                "planned_entry_count": len(outcome.planned_entry_ids),
                "blocked_reason_count": len(outcome.reasons),
                "note": "请求路径真跑 + 逐 entry 真调 extract/materialize（真库 session）",
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - 环境不可得
        return {
            "verified": 0,
            "failed": 0,
            "unverifiable": 0,
            "summary": {"registered": 0, "verified": 0, "failed": 0, "unverifiable": 0},
            "note": f"真库不可达或注册路径抛错（环境不可得）：{type(exc).__name__}: {exc}"[:300],
        }
