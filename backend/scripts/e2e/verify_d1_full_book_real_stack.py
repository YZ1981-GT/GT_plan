# -*- coding: utf-8 -*-
"""D1 整册真栈 materialize + extract + verify_unmanaged_regions 闭环验证。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 25~29 的共同门
Requirements 5.1 / 5.2 / 5.5（整册 materialize 200 + verify 全绿 + 耗时登记）

═══ 为什么现在能跑了（D4 脚本的 docstring 在这一点上已过时）═══

`verify_d4_full_book_real_stack.py` 的 docstring 断言「D4 是 D 循环里**唯一**
`adapter_registered=True` 的 entry，D1/D3/D5/D6/D7 的 manifest capability 非
`bidirectional` ⇒ `attach_adapters()` 在任何 DB 查询之前短路返回 `()`」。
**现算实测该结论对 D1 已不成立**（2026-09-28）：

* `backend/data/workpaper_sync_entry_manifest.json` 的 `entries` 里
  `xlsx/gt-d1-notes-receivable` 现为 `capability="bidirectional"` /
  `adapter_id="d1.notes_receivable_detail"`，与 D4 同级；
* 真库 `working_paper_content_representation` 有该 entry 的 4 行（generation 恒 1，
  `reason` 为 `content_commit`×3 + `rematerialize`×1）。
  🔴 **没有任何一行 `reason='materialize'`** —— 这正是「整册门从未跑过」的证据，
  也正是本脚本要补的那一刀。

🔴 **必须走隔离式 attach**：共享的 `registry.register_from_manifest()` 会在轮到 D1 之前
先炸在 `d2.receivable_detail` 的 `ContractDriftError`（D2 lane 在途工作）⇒ 本脚本直接调
`phase5_d1_notes_receivable.attach_pilot_adapters()` 单独挂 D1。

🔴 **`before` 必须用真实 substrate 字节，不能用 `read_authoritative_template()`**：
`verify_unmanaged_regions` 的语义是「**这一次** materialize 有没有动不该动的字节」，
参照系必须是这一次的输入；拿权威模板当 before 会把历史插行 / footer 重冻结 / sibling ref
位移这些**合法**演化逐字节判成 drift。

🔴 **store item 清单只从 `all_store_item_ids()` 取，不硬编码**：D4 脚本里那两个
`STORE_ITEM_IDS_D45_FIXED`/`STORE_ITEM_IDS_D413_FIXED` 是 D4 的历史包袱。D1 的
`fixed_text` 伴生（D1-10 的 3 个 recon 标量 `D1-inventory-recon-*`）**按设计不进 Excel
契约层**（见 `phase5_d1_10_inventory` 模块 docstring），因此本脚本对「出现了非
rows/dict 形态的受管 spec」显式报错而不是静默跳过 —— 静默跳过就会把该区写空。

用法（仓库根，需要 `audit-postgres` 可连，**不需要**真后端进程）::

    python backend/scripts/e2e/verify_d1_full_book_real_stack.py

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

#: 真库实测的 D1 宿主：`重药控股安徽有限公司_2025`。
#: 选它的理由 = 它是 4 个 D1 底稿里**唯一**既有 representation、又有 `D1-bd-notetype-rows`
#: 真实载荷（2 固定行）的那一份 ⇒ 静态受管区在本次 materialize 里**真的有值要写**，
#: 不会退化成「空载荷往返恒等」的假绿。
PROJECT_ID = uuid.UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
WP_ID = uuid.UUID("68c7740e-dc48-4787-a788-2e77f8560673")
ENTRY_ID = "xlsx/gt-d1-notes-receivable"


def _describe_managed_surface() -> tuple[int, int, int, tuple[str, ...]]:
    """现算受管面：(受管区数, 去重 sheet 数, store item 数, 非 rows/dict 形态的 spec 名)。

    受管区数 = 行表型 spec 数 + 静态受管区数；tasks 25~28 的「受管区 N→M」就报这个数。
    """
    from app.services.workpaper_sync import phase5_d1_expansion as exp
    from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind

    specs = exp.managed_row_table_specs()
    odd: list[str] = []
    for s in specs:
        kind = getattr(s, "store_kind", None)
        if kind not in (StoreKind.rows, StoreKind.dict):
            odd.append(f"{getattr(s, 'store_item_id', '?')}({kind})")
    # 🔴 字段名是 `managed_sheet`，不是 `sheet_name` —— 首版按后者 getattr 全得 None，
    #    去重后恒为 1，把「12 张 sheet」报成「1 张」。凡 getattr 带默认值的计数都要先验非空。
    instr = exp.instrumentation_specs()
    sheets = {s.managed_sheet for s in instr}
    if None in sheets or not sheets:
        raise RuntimeError(f"managed_sheet 取值异常: {sheets!r}")
    items = exp.all_store_item_ids()
    # 静态受管区不在 managed_row_table_specs() 里（行表引擎拒静态 spec），单独计入
    static_n = len(items) - len(specs) - 1  # -1 = 基线 D1-3
    return len(specs) + max(static_n, 0), len(sheets), len(items), tuple(odd)


async def run() -> int:
    from app.core.database import async_session
    from app.services.workpaper_sync.adapters.registry import (
        WorkpaperSyncAdapterRegistry,
    )
    from app.services.workpaper_sync.entry_profile import load_entry_manifest
    from app.services.workpaper_sync.phase5_d1_notes_receivable import (
        attach_pilot_adapters as attach_d1,
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

    regions, sheets, n_items, odd_kinds = _describe_managed_surface()
    print(f"[0] 受管区={regions} 去重 sheet={sheets} store item={n_items}")
    if odd_kinds:
        print(f"[0] ❌ 出现非 rows/dict 形态的受管 spec，会被投影静默跳过: {odd_kinds}")
        return 1

    async with async_session() as session:
        # ── ① 隔离式 attach（绕开被 D2 漂移挡住的全量注册链）────────────
        from app.services.workpaper_sync.published_identity_observer import (
            ObservedIdentityDriftError,
        )

        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        try:
            ids = await attach_d1(registry, session=session)
        except ObservedIdentityDriftError as exc:
            # 🔴 这不是本脚本的缺陷，也不是「我这次改动打挂了 D1」——
            #    已实测：HEAD 版契约（18 table）算出的 structure_hash 同样 ≠ 冻结值
            #    ⇒ 漂移**先于**本 spec 的静态 table 改动存在。
            ctx = exc.context or {}
            print("[①] 🔴 fail-closed：published representation 的 frozen "
                  "structure_hash 与现算不一致 —— 整册门在「重新发布」之前跑不了。")
            print(f"     recomputed={ctx.get('recomputed_structure_hash', '?')}")
            print(f"     frozen    ={ctx.get('frozen_structure_hash', '?')}")
            print(f"     observed_structure_size={ctx.get('observed_structure_size')} "
                  f"declared_structure_size={ctx.get('declared_structure_size')}")
            print("     ⚠️ 上面两个 size **都是「现在」的值**，平台错误信息里没有"
                  "「冻结时的 inventory 大小」⇒ 看着像「两边一致却仍判漂移」，"
                  "别被它带偏；真正的比对量是 hash。")
            print("     解除路径 = 重新发布 D1 representation（先例 "
                  "`backend/scripts/diagnose/d2_rematerialize_sibling_sheets.py`，"
                  "属 spec `workpaper-sync-registration-isolation-and-d2-republish` "
                  "的工作面，需先 provision 新 bundle，且会写共享 dev 库）。")
            print("     影响面 = 仅 D1 一个 entry：`register_from_manifest()` 逐 entry "
                  "隔离 `SyncDomainError`，记成 typed failure 后继续 ⇒ 不会打挂整批。")
            return 1
        if not ids:
            print("[①] ❌ D1 attach 返回空 —— manifest capability 或 published "
                  "representation 可能已被改动（本脚本 docstring 的前置已失效）")
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
        if not callable(all_ids_fn):
            print("[③] ❌ provider 没有 all_store_item_ids —— 单一口径断了")
            return 1
        item_ids = tuple(all_ids_fn())
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
            if row is not None and str(row).strip():
                payloads[item] = str(row)
        store_projection = provider.build_combined_store_projection(
            payloads, contract=contract
        )
        print(
            f"[③a] store item={len(item_ids)} 有载荷={len(payloads)} "
            f"store values={len(store_projection.values)} "
            f"有载荷的 item={sorted(payloads)}"
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
            f"表数={len(projection.row_keys)} "
            f"行数={sum(len(v) for v in projection.row_keys.values())}"
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "d1-materialized.xlsx"

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
                import traceback

                print(f"[④] ❌ materialize 失败: {type(exc).__name__}: {exc}")
                traceback.print_exc()
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
                import traceback

                print(f"[⑤] ❌ extract 失败: {type(exc).__name__}: {exc}")
                traceback.print_exc()
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
                import traceback

                print(f"[⑥] ❌ verify 失败: {type(exc).__name__}: {exc}")
                traceback.print_exc()
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
            print(
                f"✅ D1 整册真栈闭环全绿（受管区 {regions} / sheet {sheets} / "
                f"store item {len(item_ids)}，materialize + extract + verify equivalent）"
            )
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
