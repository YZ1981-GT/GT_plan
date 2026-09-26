# -*- coding: utf-8 -*-
"""D4 整册真栈 materialize + extract + verify_unmanaged_regions 闭环验证。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 19 · Requirements 2.5 / 4.2 / 4.3

═══ 为什么这条能跑，而 D1/D3/D5/D6/D7 跑不了 ═══

`d4.revenue_detail` 是 D 循环里**唯一** `adapter_registered=True` 的 entry
（`backend/data/workpaper_sync_d_cycle_manifest_slice.json` 实测；D1/D3/D5/D6/D7 全为
`false`，manifest capability 非 `bidirectional` ⇒ `attach_adapters()` 在任何 DB 查询之前
短路返回 `()`）。因此 Task 19 的「D4 整册真 materialize + verify 全绿」是本 spec 家族里
唯一**当下就能真跑**的真栈判据。

🔴 **必须走隔离式 attach，不能走全量注册**：共享的
`registry.register_from_manifest()` 会在轮到 D4 **之前**先炸在 `d2.receivable_detail`
的 `ContractDriftError`（真实实测：`sheet='d21-managed' table='adjudication_cells'
field='adjudication_cells/aging_b' locator='B:static:10'`，根因是并发会话把 D2-1 加进
契约后 live representation 尚未重物化）。那是 D2 lane 的在途工作，与 D4 无关 ⇒ 本脚本
直接调 `phase5_d4_revenue_detail.attach_pilot_adapters()` 单独挂 D4。

🔴 **`before` 必须用真实 substrate 字节，不能用 `read_authoritative_template()`**：
D4 这条真实数据已演化 164 代，权威模板与当前 representation 之间存在大量**合法**结构差异
（历史插行 / footer 重冻结坐标 / sibling ref 位移）。拿模板当 before 会把这些合法历史
变化逐字节判成 drift，判据直接失去意义。`verify_unmanaged_regions` 的语义是
「**这一次** materialize 有没有动不该动的字节」，参照系必须是这一次的输入。

用法（仓库根，需要 `audit-postgres` 可连，**不需要**真后端进程）::

    python backend/scripts/e2e/verify_d4_full_book_real_stack.py

退出码：0 = verify equivalent（全绿）；1 = 任一步失败或 verify 判漂移。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import sqlalchemy as sa

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

#: 真库实测的 D4 宿主（与 `seed_d4_l2_empty_sheets.py` / `real-stack-probe` 同一实例）。
PROJECT_ID = uuid.UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
WP_ID = uuid.UUID("b3ab3c46-828f-4f48-950e-aee9bbdc923f")
ENTRY_ID = "xlsx/gt-d4-operating-revenue"


async def run() -> int:
    from app.core.database import async_session
    from app.services.workpaper_sync.adapters.registry import (
        WorkpaperSyncAdapterRegistry,
    )
    from app.services.workpaper_sync.entry_profile import load_entry_manifest
    from app.services.workpaper_sync.phase5_d4_revenue_detail import (
        attach_pilot_adapters as attach_d4,
    )
    from app.services.workpaper_sync.resolution import (
        CanonicalArtifactRepository,
        CanonicalResolutionService,
        ResolutionIntent,
    )
    from app.services.workpaper_sync.store_projection_response import (
        _overlay_with_published_substrate,
        resolve_store_projection_provider,
    )

    async with async_session() as session:
        # ── ① 隔离式 attach（绕开被 D2 漂移挡住的全量注册链）────────────
        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        ids = await attach_d4(registry, session=session)
        if not ids:
            print("[①] ❌ D4 attach 返回空 —— manifest capability 可能已被改动")
            return 1
        registration = registry.resolve_for_entry(ENTRY_ID)
        contract = registration.contract
        if contract is None:
            print("[①] ❌ registration 无 approved contract")
            return 1
        print(f"[①] attach={ids} adapter_id={registration.adapter_id!r}")

        # ── ② 解析当前 representation（真实字节）────────────────────────
        resolver = CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND)
        )
        resolution = await resolver.resolve(
            intent=ResolutionIntent.extract,
            project_id=PROJECT_ID,
            wp_id=WP_ID,
            entry_id=ENTRY_ID,
        )
        substrate_path = resolution.artifact_path
        if not substrate_path.is_file():
            print(f"[②] ❌ substrate 文件不存在: {substrate_path}")
            return 1
        print(
            f"[②] generation={resolution.representation_generation} "
            f"substrate={substrate_path.name} size={substrate_path.stat().st_size}"
        )

        # ── ③ 真实 store projection + published substrate overlay ───────
        provider = resolve_store_projection_provider(str(registration.adapter_id))
        all_ids_fn = getattr(provider, "all_store_item_ids", None)
        item_ids = (
            tuple(all_ids_fn())
            if callable(all_ids_fn)
            else tuple(getattr(provider, "STORE_ITEM_IDS", ()) or ())
        )
        fixed_text_ids = set(
            getattr(provider, "STORE_ITEM_IDS_D45_FIXED", ()) or ()
        ) | set(getattr(provider, "STORE_ITEM_IDS_D413_FIXED", ()) or ())
        payloads: dict[str, str] = {}
        for item in item_ids:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                    ),
                    {"wp": str(WP_ID), "item": item},
                )
            ).scalar_one_or_none()
            if item in fixed_text_ids:
                payloads[item] = str(row) if row is not None else ""
            elif row is not None and str(row).strip():
                payloads[item] = str(row)
        store_projection = provider.build_combined_store_projection(
            payloads, contract=contract
        )
        print(
            f"[③a] store item={len(item_ids)} 有载荷={len(payloads)} "
            f"store values={len(store_projection.values)}"
        )
        projection, overlay_applied = await _overlay_with_published_substrate(
            resolution=resolver,
            project_id=PROJECT_ID,
            wp_id=WP_ID,
            entry_id=ENTRY_ID,
            registration=registration,
            store_projection=store_projection,
        )
        print(
            f"[③b] overlay_applied={overlay_applied} values={len(projection.values)} "
            f"表数={len(projection.row_keys)} 行数={sum(len(v) for v in projection.row_keys.values())}"
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "d4-materialized.xlsx"

            # ── ④ 整册 materialize ──────────────────────────────────────
            t0 = time.perf_counter()
            try:
                result = registration.adapter.materialize(
                    substrate=substrate_path,
                    projection=projection,
                    output=output_path,
                    contract=contract,
                )
            except Exception as exc:  # noqa: BLE001 —— 真栈探测须如实报告任何异常
                print(f"[④] ❌ materialize 失败: {type(exc).__name__}: {exc}")
                return 1
            dt_mat = time.perf_counter() - t0
            row_shift = getattr(result, "row_shift", None)
            print(
                f"[④] materialize OK {dt_mat:.1f}s size={output_path.stat().st_size} "
                f"row_shift={row_shift!r}"
            )

            # ── ⑤ extract 反读 ─────────────────────────────────────────
            t1 = time.perf_counter()
            try:
                extracted = registration.adapter.extract(
                    artifact=output_path, contract=contract
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[⑤] ❌ extract 失败: {type(exc).__name__}: {exc}")
                return 1
            dt_ext = time.perf_counter() - t1
            print(
                f"[⑤] extract OK {dt_ext:.1f}s values={len(extracted.values)} "
                f"表数={len(extracted.row_keys)}"
            )

            # ── ⑥ verify_unmanaged_regions（before = 真实 substrate）────
            t2 = time.perf_counter()
            try:
                report = registration.adapter.verify_unmanaged_regions(
                    before=substrate_path,
                    after=output_path,
                    contract=contract,
                    row_shift=row_shift,
                    total_formula_rows=getattr(result, "total_formula_rows", ()),
                    propagation=getattr(result, "workbook_row_change", None),
                    per_table_shift=getattr(result, "per_table_shift", None),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[⑥] ❌ verify 失败: {type(exc).__name__}: {exc}")
                return 1
            dt_ver = time.perf_counter() - t2
            equivalent = bool(getattr(report, "equivalent", False))
            print(f"[⑥] verify OK {dt_ver:.1f}s equivalent={equivalent}")
            if not equivalent:
                print(f"[⑥] 🔴 判漂移，报告详情: {report}")
                return 1
            print(
                f"[总计] materialize {dt_mat:.1f}s + extract {dt_ext:.1f}s + "
                f"verify {dt_ver:.1f}s = {dt_mat + dt_ext + dt_ver:.1f}s"
            )
            print("✅ D4 整册真栈闭环全绿（materialize + extract + verify equivalent）")
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
