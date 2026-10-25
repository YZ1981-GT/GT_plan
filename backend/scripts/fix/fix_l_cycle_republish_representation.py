# -*- coding: utf-8 -*-
"""L / I 循环 entry 重新发布 representation：用当前磁盘契约 provision 新 bundle + 发新 generation。

spec: l-cycle-true-adapter-registration · Task 12

═══ 为什么需要 ═══

首版 representation 冻结了当时的模板/instrumentation/契约 digest。之后若权威模板被**合法升级**
（如 L4 的受管表共享公式展开 —— 真 OO 往返插行时 `excel_row_shift_shared_formula_orientation_unsupported`
fail-closed），已发布的 representation 仍指向旧 substrate，必须用新 bundle 发新 generation。

范式与 `fix_d1_republish_representation.py` 逐段相同（不复制其逻辑出新语义）：
① `ReusingDefinitionPublisher` provision（已存在的 approved definition 直接复用，幂等）
② `fix_projection_representation_rehash.resolve_rehash_plan` 取新 bundle 的计划
③ `stage_instrumented_substrate` + `publish_first_generation` 发新 generation
差异只有一处：provider 由 `--entry` 经交付登记表现算（不写死 D1）；store 载荷读真库
（L4 受管键现算 0 行 ⇒ 等价于空载荷，不需要 D1 那条「传空 store 绕 rowId 不匹配」的取舍）。

🔴 写共享 dev 库：新 definition / bundle / representation，推进 content revision，**不可逆**
（旧 generation 保留但不再 current）。判成败一律查数据，不看退出码。

用法::

    .venv\\Scripts\\python.exe backend/scripts/fix/fix_l_cycle_republish_representation.py --check --entry xlsx/gt-l4-bonds-payable
    .venv\\Scripts\\python.exe backend/scripts/fix/fix_l_cycle_republish_representation.py --apply --entry xlsx/gt-l4-bonds-payable
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def _provider_for(entry_id: str) -> Any:
    from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    rows = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r.get("entry_id") == entry_id]
    if len(rows) != 1:
        raise SystemExit(f"交付登记表里 entry {entry_id!r} 命中 {len(rows)} 条（须恰 1）")
    module = rows[0]["provider_module"]
    if not any(tag in module for tag in (".phase5_l", ".phase5_i")):
        raise SystemExit(
            f"{entry_id} 的 provider {module} 不是 L/I 循环 phase5 provider —— "
            "本脚本仅服务声明式 row-table projection 域"
        )
    return importlib.import_module(module)


def _load_rehash_module() -> Any:
    path = _BACKEND / "scripts" / "fix" / "fix_projection_representation_rehash.py"
    name = "fix_projection_representation_rehash"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


async def run(*, entry_id: str, apply: bool) -> dict[str, Any]:
    from app.core.config import settings
    from app.services.workpaper_sync import projection_first_publication as F
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_provisioning import ReusingDefinitionPublisher
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    P = _provider_for(entry_id)
    RH = _load_rehash_module()
    engine = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    report: dict[str, Any] = {"entry_id": entry_id, "mode": "apply" if apply else "check"}
    try:
        async with Session() as session:
            current = await RH._current_representation(session, entry_id=entry_id)
            if current is None:
                report.update(status="blocked", reason="no current published representation")
                return report
            report["current"] = {k: str(current[k]) for k in ("representation_id", "wp_id", "project_id", "generation")}
            publisher = ReusingDefinitionPublisher(
                session=session,
                artifacts=CanonicalArtifactRepository(_BACKEND),
                repository=WorkpaperSyncRepository(session),
                project_id=uuid.UUID(str(current["project_id"])),
                wp_id=uuid.UUID(str(current["wp_id"])),
                source_commit="fix_l_cycle_republish",
            )
            defs = await P.publish_definitions(publisher)
            report.update(
                bundle_id=str(defs.bundle_id), bundle_sha256=defs.bundle_sha256,
                template_sha256=defs.template_definition_sha256,
                reused_stages=list(publisher.reused_stages), created_stages=list(publisher.created_stages),
            )
            if not apply:
                await session.rollback()
                report["status"] = "would_republish"
                return report
            await session.commit()

        async with Session() as session:
            resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND))
            plan = await RH.resolve_rehash_plan(
                session=session, resolution=resolution,
                project_id=uuid.UUID(str(current["project_id"])), wp_id=uuid.UUID(str(current["wp_id"])),
                entry_id=entry_id, actor_id=None,
            )
            report.update(plan_bundle_id=str(plan.bundle.bundle_id), plan_contract_sha=plan.contract.canonical_sha256)
            store: dict[str, str] = {}
            for item_id in P.all_store_item_ids():
                raw = (await session.execute(sa.text(
                    "SELECT remark FROM checklist_responses WHERE wp_id = :wp AND item_id = :item LIMIT 1"),
                    {"wp": str(current["wp_id"]), "item": item_id})).scalar_one_or_none()
                if raw is not None and str(raw).strip():
                    store[item_id] = str(raw)
            report["store_items_with_payload"] = len(store)
            item_ids = tuple(P.all_store_item_ids())
            # 🔴 `publish_first_generation._store_projection_for_provider` 对**单 store**直接把参数喂给
            # `build_store_projection`；只有 provider 声明 `STORE_ITEM_IDS`>1 才接受映射。
            # 首版错误地无条件传 dict，使 L4 单表拿到 `{}` 而不是 `[]`，被形态门正确拒绝。
            if len(item_ids) == 1:
                store_payload: Any = store.get(item_ids[0], getattr(P, "EMPTY_STORE_PAYLOAD", "[]"))
            else:
                store_payload = store
            with tempfile.TemporaryDirectory(prefix="l-republish-") as tmp:
                staged = F.stage_instrumented_substrate(entry_id=entry_id, staging_dir=Path(tmp), contract=plan.contract)
                receipt = await F.publish_first_generation(
                    session=session, resolution=resolution, artifacts=CanonicalArtifactRepository(_BACKEND),
                    repository=WorkpaperSyncRepository(session), plan=plan, staged=staged,
                    store_payload=store_payload,
                )
                await session.commit()
            report.update(
                status="republished", new_representation_id=str(receipt.representation_id),
                new_generation=int(receipt.representation_generation), new_revision=int(receipt.revision),
            )
            return report
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--entry", required=True)
    args = parser.parse_args()
    report = asyncio.run(run(entry_id=args.entry, apply=bool(args.apply)))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"would_republish", "republished"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
