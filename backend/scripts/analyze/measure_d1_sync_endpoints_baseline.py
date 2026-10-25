# -*- coding: utf-8 -*-
"""D1 三端点性能基线（store-projection / pending-mutations / materialize）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 4（真栈部分，Property 13 / D1-P13）
Requirements 8.1 / 8.4

═══ 这条基线钉的是什么、不钉的是什么 ═══

需求 8.1 原文是「三端点耗时 ≤ 抽取前 110%」。但本 spec 的引擎抽取（阶段 1~3）**早已完成**，
HEAD 上没有「抽取前」那个运行时环境可供对照 —— 拿不到那个历史快照，就没有分母。
因此本脚本的实际职责**不是**与一个不存在的历史快照比，而是：

  **在同一 substrate 上建立当前三端点核心计算段的基线数**，供 Task 34 收尾复测
  （以及 Task 15/16/17 的 ≤150 行收敛后复跑）与之对照 —— 110% 门这才有了分母。

🔴 **口径必须说清，否则又是一处换口径的假数**（measure_d4 docstring 已有同族教训）：

* 本脚本量的是**服务层核心计算段**，不是 HTTP 端点的墙钟。端点真跑还要过 guard / auth /
  room / revision 推进，那些是 I/O 与锁，run-to-run 漂且与「引擎重构有没有变慢」无关。
  三端点各自的**计算热点**是：
    - store-projection → `build_combined_store_projection` + `_overlay_with_published_substrate`
      （只读，provider 现算 projection + 叠加 published substrate 脚手架）
    - pending-mutations → 与 materialize 共享的 `_materialize_request` projection 解析
      （把 body/store 解析成 `MaterializeRequest.projection`）—— 它**不写库**那一段
    - materialize   → `adapter.materialize`（整册逐 binding 写 + 位移归一化）
* 走**隔离式 attach**（`attach_pilot_adapters`），与 verify_d1 脚本同一理由：共享
  `register_from_manifest()` 可能撞别 lane 在途的 `ContractDriftError`。
* `before` 用**真实 substrate 字节**，不是权威模板（verify 的参照系语义，同 verify_d1）。
* `--repeat N` 多轮取 min/median/max —— 单样本墙钟在 materialize 这条路上 run-to-run 漂
  （verify_d1 实测见过 4.6 / 4.7 / 4.8 / 4.9 / 5.2s），单样本不算证据。

用法（仓库根，需要 `audit-postgres` 可连，**不需要**真后端进程）::

    .venv\\Scripts\\python.exe backend/scripts/analyze/measure_d1_sync_endpoints_baseline.py
    .venv\\Scripts\\python.exe backend/scripts/analyze/measure_d1_sync_endpoints_baseline.py \\
        --repeat 5 --label task4-d1-endpoints-baseline

证据落 `docs/operations/evidence/row-table-engine-d1-coverage/<label>.json`。
退出码：0 = 三端点全部测得且无异常；1 = 任一段抛异常或整册门未开（representation 阻塞）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

DEFAULT_OUT_DIR = (
    _REPO / "docs" / "operations" / "evidence" / "row-table-engine-d1-coverage"
)

#: 真库实测的 D1 宿主：`重药控股安徽有限公司_2025`（同 verify_d1 脚本，理由见那里）。
PROJECT_ID = uuid.UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
WP_ID = uuid.UUID("68c7740e-dc48-4787-a788-2e77f8560673")
ENTRY_ID = "xlsx/gt-d1-notes-receivable"


def _stats(values: list[float]) -> dict[str, Any]:
    """min / median / max（秒，保留 3 位）。单样本时三者相等，如实呈现。"""
    if not values:
        return {"samples": 0, "min_s": None, "median_s": None, "max_s": None}
    return {
        "samples": len(values),
        "min_s": round(min(values), 3),
        "median_s": round(statistics.median(values), 3),
        "max_s": round(max(values), 3),
    }


#: 需求 8.1：三端点耗时 ≤ 抽取前 110%。
_REGRESSION_FACTOR: float = 1.10

#: 比对用的端点键（store-projection 的 median 太小、CPU 抖动占比大，用 median 比会假红
#: —— 对这类亚毫秒段改比 max 不现实，统一用 median 但对 < _NOISE_FLOOR_S 的段豁免，
#: 因为那个量级的「变慢 10%」是时钟噪音不是回归）。
_COMPARED_ENDPOINTS: tuple[str, ...] = (
    "store_projection",
    "pending_mutations_projection_segment",
    "materialize",
    "extract",
    "verify_unmanaged_regions",
)

#: 低于此值（秒）的端点段，median 的绝对波动被时钟噪音主导 ⇒ 110% 比值无意义，豁免。
#: 实测 store-projection median 0.009s / pending 0.001s 都在此之下；materialize/extract/
#: verify 都远高于它，是真正要守的三段。
_NOISE_FLOOR_S: float = 0.05


def compare_against_baseline(
    baseline: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    """逐端点比当前 **min** 与基线 **min**，判是否 ≤ 基线 × 110%。

    纯函数（不连库、不读文件），便于守卫穷举验证。返回 {ok, per_endpoint, violations}。
    低于 `_NOISE_FLOOR_S` 的端点段豁免（min 绝对值被时钟噪音主导，110% 比值无意义），
    但仍如实记录其比值供人读。

    🔴 **比 min 不比 median，有实测依据不是为了凑绿**：extract 与 verify 是**双峰分布**
       —— 9 轮实测 extract 要么 ~0.40s 要么 ~0.66s（`BASELINE_EXTRACT_CACHE` 命中/未命中，
       需求 8.4），几乎无中间值。median 落在哪个峰取决于这一批里缓存命中了几次，run-to-run
       跳 20% ⇒ 用 median 比 median 会把缓存抖动误判成性能回归。min 代表「缓存命中时的
       真实计算成本」，剔除未命中的慢样本，是对「代码有没有变慢」更忠实的量。
       materialize 则很稳（min run-to-run < 1%），min/median 都可，统一用 min。
    """
    base_ep = baseline.get("endpoints", {})
    cur_ep = current.get("endpoints", {})
    per_endpoint: dict[str, Any] = {}
    violations: list[str] = []
    for key in _COMPARED_ENDPOINTS:
        b = (base_ep.get(key) or {}).get("min_s")
        c = (cur_ep.get(key) or {}).get("min_s")
        if b is None or c is None:
            per_endpoint[key] = {"baseline_s": b, "current_s": c, "ratio": None,
                                 "verdict": "missing"}
            violations.append(f"{key}: 基线或当前缺 median（b={b} c={c}）")
            continue
        ratio = (c / b) if b > 0 else None
        noise = b < _NOISE_FLOOR_S and c < _NOISE_FLOOR_S
        if noise:
            verdict = "noise_floor_exempt"
        elif ratio is not None and ratio <= _REGRESSION_FACTOR:
            verdict = "ok"
        else:
            verdict = "regressed"
            violations.append(
                f"{key}: 当前 {c}s / 基线 {b}s = {ratio:.2f}× > {_REGRESSION_FACTOR}×"
            )
        per_endpoint[key] = {
            "baseline_s": b,
            "current_s": c,
            "ratio": round(ratio, 3) if ratio is not None else None,
            "verdict": verdict,
        }
    return {
        "ok": not violations,
        "factor": _REGRESSION_FACTOR,
        "noise_floor_s": _NOISE_FLOOR_S,
        "per_endpoint": per_endpoint,
        "violations": violations,
    }


async def _load_substrate_and_projection(session: Any) -> dict[str, Any]:
    """隔离式 attach + 解析 representation + 现算 store projection（三端点共享的前置）。

    返回 registration / contract / substrate_path / store_payloads，供三段计时各自取用。
    任何前置失败（attach 空 / 无契约 / substrate 缺失）直接抛，由 run() 捕获报 1。
    """
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
        resolve_store_projection_provider,
    )

    registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
    ids = await attach_d1(registry, session=session)
    if not ids:
        raise RuntimeError("D1 attach 返回空 —— manifest/representation 可能已变")
    registration = registry.resolve_for_entry(ENTRY_ID)
    contract = registration.contract
    if contract is None:
        raise RuntimeError("registration 无 approved contract")

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
        raise RuntimeError(f"substrate 文件不存在: {substrate_path}")

    provider = resolve_store_projection_provider(str(registration.adapter_id))
    all_ids_fn = getattr(provider, "all_store_item_ids", None)
    if not callable(all_ids_fn):
        raise RuntimeError("provider 没有 all_store_item_ids —— 单一口径断了")
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

    return {
        "registration": registration,
        "contract": contract,
        "provider": provider,
        "resolver": resolver,
        "substrate_path": substrate_path,
        "generation": resolution.representation_generation,
        "store_payloads": payloads,
        "store_item_ids": item_ids,
    }


async def _measure_store_projection(ctx: dict[str, Any]) -> float:
    """store-projection 端点核心段：provider 现算 projection + overlay published substrate。

    这是 `read_store_projection` 端点在 guard 之后真正花时间的那一段
    （`compute_store_projection_response` 的 body）。只读，不写库。
    """
    from app.services.workpaper_sync.store_projection_response import (
        _overlay_with_published_substrate,
    )

    provider = ctx["provider"]
    contract = ctx["contract"]
    registration = ctx["registration"]
    payloads = ctx["store_payloads"]

    t0 = time.perf_counter()
    store_projection = provider.build_combined_store_projection(
        payloads, contract=contract
    )
    await _overlay_with_published_substrate(
        resolution=ctx["resolver"],
        project_id=PROJECT_ID,
        wp_id=WP_ID,
        entry_id=ENTRY_ID,
        registration=registration,
        store_projection=store_projection,
    )
    return time.perf_counter() - t0


async def _measure_pending_mutation(ctx: dict[str, Any]) -> float:
    """pending-mutations 端点核心段：把 store 载荷解析成 projection（不写库那一段）。

    `create_pending_mutation` 端点先过 `_materialize_request` 把 body/store 解析成
    `MaterializeRequest.projection`，再 `coordinator.create_pending_mutation` 落库。
    落库是 I/O（且需要已 authorize 的 request、会推 revision，与「引擎有没有变慢」无关）；
    真正与引擎重构相关的 CPU 段就是这步 projection 构造 —— 它与 store-projection 端点
    同源（都走 `build_combined_store_projection`），单独计时以便两端口径一致。
    """
    provider = ctx["provider"]
    contract = ctx["contract"]
    payloads = ctx["store_payloads"]

    t0 = time.perf_counter()
    provider.build_combined_store_projection(payloads, contract=contract)
    return time.perf_counter() - t0


async def _measure_materialize(ctx: dict[str, Any]) -> dict[str, float]:
    """materialize 端点核心段：整册 materialize（逐 binding 写 + 位移归一化）。

    这是三端点里最重的一段，也是 `materialize` 端点在 coordinator 之后真正干活的地方。
    连带量 extract + verify 以便与 verify_d1 脚本的「总计」口径对齐（那三段是生产切 OO 时
    用户观测到的合计，拿单段去比是换口径）。
    """
    from app.services.workpaper_sync.store_projection_response import (
        _overlay_with_published_substrate,
    )

    provider = ctx["provider"]
    contract = ctx["contract"]
    registration = ctx["registration"]
    payloads = ctx["store_payloads"]

    store_projection = provider.build_combined_store_projection(
        payloads, contract=contract
    )
    projection, _ = await _overlay_with_published_substrate(
        resolution=ctx["resolver"],
        project_id=PROJECT_ID,
        wp_id=WP_ID,
        entry_id=ENTRY_ID,
        registration=registration,
        store_projection=store_projection,
    )

    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "d1-materialized.xlsx"
        t0 = time.perf_counter()
        result = registration.adapter.materialize(
            substrate=ctx["substrate_path"],
            projection=projection,
            output=output_path,
            contract=contract,
        )
        dt_mat = time.perf_counter() - t0

        t1 = time.perf_counter()
        extracted = registration.adapter.extract(
            artifact=output_path, contract=contract
        )
        dt_ext = time.perf_counter() - t1

        t2 = time.perf_counter()
        registration.adapter.verify_unmanaged_regions(
            before=ctx["substrate_path"],
            after=output_path,
            contract=contract,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=getattr(result, "per_table_shift", None),
        )
        dt_ver = time.perf_counter() - t2

    return {
        "materialize_s": dt_mat,
        "extract_s": dt_ext,
        "verify_s": dt_ver,
        "extracted_values": len(extracted.values),
        "extracted_tables": len(extracted.row_keys),
    }


async def run(
    repeat: int,
    label: str,
    out_dir: Path,
    compare_baseline_path: Path | None = None,
) -> int:
    from app.core.database import async_session

    store_samples: list[float] = []
    pending_samples: list[float] = []
    mat_samples: list[float] = []
    ext_samples: list[float] = []
    ver_samples: list[float] = []
    last_mat_meta: dict[str, Any] = {}
    generation = None
    store_item_count = 0
    has_load_count = 0

    async with async_session() as session:
        try:
            ctx = await _load_substrate_and_projection(session)
        except Exception as exc:  # noqa: BLE001 —— 前置失败如实报
            print(f"[前置] ❌ {type(exc).__name__}: {exc}")
            return 1

        generation = ctx["generation"]
        store_item_count = len(ctx["store_item_ids"])
        has_load_count = len(ctx["store_payloads"])
        print(
            f"[前置] generation={generation} substrate={ctx['substrate_path'].name} "
            f"store item={store_item_count} 有载荷={has_load_count}"
        )

        for i in range(repeat):
            try:
                store_samples.append(await _measure_store_projection(ctx))
                pending_samples.append(await _measure_pending_mutation(ctx))
                mat_meta = await _measure_materialize(ctx)
            except Exception as exc:  # noqa: BLE001
                import traceback

                print(f"[轮 {i + 1}] ❌ {type(exc).__name__}: {exc}")
                traceback.print_exc()
                return 1
            mat_samples.append(mat_meta["materialize_s"])
            ext_samples.append(mat_meta["extract_s"])
            ver_samples.append(mat_meta["verify_s"])
            last_mat_meta = mat_meta
            print(
                f"[轮 {i + 1}/{repeat}] store-projection {store_samples[-1]:.3f}s · "
                f"pending(projection) {pending_samples[-1]:.3f}s · "
                f"materialize {mat_meta['materialize_s']:.3f}s "
                f"(+extract {mat_meta['extract_s']:.3f}s +verify {mat_meta['verify_s']:.3f}s)"
            )

    report = {
        "label": label,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "spec": "d1-sync-row-table-engine-and-d1-coverage",
        "task": "4",
        "requirements": ["8.1", "8.4"],
        "host": {
            "project_id": str(PROJECT_ID),
            "wp_id": str(WP_ID),
            "entry_id": ENTRY_ID,
            "representation_generation": generation,
        },
        "platform": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "system": platform.system(),
        },
        "store_item_count": store_item_count,
        "store_items_with_payload": has_load_count,
        "repeat": repeat,
        "endpoints": {
            "store_projection": _stats(store_samples),
            "pending_mutations_projection_segment": _stats(pending_samples),
            "materialize": _stats(mat_samples),
            "extract": _stats(ext_samples),
            "verify_unmanaged_regions": _stats(ver_samples),
        },
        "materialize_last_run": {
            "extracted_values": last_mat_meta.get("extracted_values"),
            "extracted_tables": last_mat_meta.get("extracted_tables"),
        },
        "caliber_note": (
            "量的是服务层核心计算段，不是 HTTP 端点墙钟（guard/auth/room/revision 推进为 I/O，"
            "run-to-run 漂且与引擎重构无关）。pending-mutations 只量其与 materialize 共享的 "
            "projection 解析段（不含落库）。此 JSON 为 Task 34 收尾复测的对照分母。"
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{label}.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n═══ 三端点基线（min / median / max，秒）═══")
    for name, key in (
        ("store-projection", "store_projection"),
        ("pending-mutations(projection 段)", "pending_mutations_projection_segment"),
        ("materialize", "materialize"),
        ("extract", "extract"),
        ("verify", "verify_unmanaged_regions"),
    ):
        s = report["endpoints"][key]
        print(f"  {name:34s} min={s['min_s']} median={s['median_s']} max={s['max_s']}")
    print(f"\n✅ 证据已落 {out_path}")

    if compare_baseline_path is not None:
        verdict = _run_comparison(compare_baseline_path, report)
        return 0 if verdict else 1
    return 0


def _run_comparison(baseline_path: Path, current: dict[str, Any]) -> bool:
    """读基线 JSON，与当前 report 比对，打印逐端点结论。返回 ok。"""
    if not baseline_path.is_file():
        print(f"\n❌ --compare-against 指向的基线不存在: {baseline_path}")
        return False
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    result = compare_against_baseline(baseline, current)
    print(f"\n═══ P13 不劣化复测（比 min，≤ 基线 × {result['factor']}，"
          f"< {result['noise_floor_s']}s 段豁免）═══")
    for key, info in result["per_endpoint"].items():
        print(f"  {key:36s} 基线min={info['baseline_s']}s 当前min={info['current_s']}s "
              f"比值={info['ratio']} ⇒ {info['verdict']}")
    if result["ok"]:
        print("✅ 三端点均未劣化（或在噪音地板以下豁免）")
    else:
        print("❌ 存在劣化端点：")
        for v in result["violations"]:
            print(f"   {v}")
    return bool(result["ok"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5, help="采样轮数（默认 5）")
    parser.add_argument(
        "--label", type=str, default="task4-d1-endpoints-baseline", help="证据文件名"
    )
    parser.add_argument(
        "--out-dir", type=str, default=str(DEFAULT_OUT_DIR), help="证据目录"
    )
    parser.add_argument(
        "--compare-against",
        type=str,
        default=None,
        help="基线 JSON 路径；给出则复测后比对 ≤110%，劣化返回 1（P13 不劣化门）",
    )
    args = parser.parse_args(argv)
    if args.repeat < 1:
        print("--repeat 必须 ≥ 1")
        return 2
    compare_path = Path(args.compare_against) if args.compare_against else None
    return asyncio.run(run(args.repeat, args.label, Path(args.out_dir), compare_path))


if __name__ == "__main__":
    raise SystemExit(main())
