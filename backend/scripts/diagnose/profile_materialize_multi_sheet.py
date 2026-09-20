# -*- coding: utf-8 -*-
"""多 sheet / 多 binding 的全簿结构观测剖析（spec workpaper-sync-materialize-large-table-performance Wave 5 Task 9）。

**为什么需要它**：Wave 0-4 的基线脚本 `profile_materialize_large_table.py` 锚在 D2 **单 binding** 大表，
量的是「行数 → 耗时」的线性度。D4 entry 长到 34 binding 后暴露的是**另一个维度**：同一份不变字节被
每个 anchor 各自重新全簿解析一遍（`collect_workbook_structure` → 每 anchor 一次 `structure_fingerprint`
+ 一次 `_read_gt_sync_pairs`）。本脚本量的是「binding 数 → 解析次数」，判据是**次数不随 binding 数增长**。

**离线可复跑**：anchors 由 `anchors_from_instrumentation_specs` 从 provider spec 投影，substrate 由
`stage_instrumented_substrate` 现造 —— 全程**不连库、不写库、不 gen++**，可任意重复跑。

用法：
    python -m scripts.diagnose.profile_materialize_multi_sheet
    python -m scripts.diagnose.profile_materialize_multi_sheet --json evidence/xxx.json

判据（Property 11/13/14）：
    `structure_fingerprint` / `_read_gt_sync_pairs` 的调用次数 SHALL 不随 anchor 数 M 增长。
    优化前：次数 ≈ 1 + M（FAIL）；优化后：次数 ≈ 常数（PASS）。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

ENTRY_ID = "xlsx/gt-d4-operating-revenue"

#: 次数不得随 M 增长的函数（判据对象）。容差：允许常数级多次（入口/校验各一次）。
_COUNT_BUDGET_CONST = 6


class _Counter:
    """进程内计数/计时 patch（不改生产代码）。"""

    def __init__(self) -> None:
        self.stats: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "seconds": 0.0})
        self._undo: list[tuple[Any, str, Any]] = []

    def wrap(self, mod: Any, name: str, label: str | None = None) -> None:
        label = label or name
        orig = getattr(mod, name, None)
        if orig is None:
            return
        stats = self.stats[label]

        def timed(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            try:
                return orig(*args, **kwargs)
            finally:
                stats["calls"] += 1
                stats["seconds"] += time.perf_counter() - t0

        timed.__name__ = getattr(orig, "__name__", name)
        setattr(mod, name, timed)
        self._undo.append((mod, name, orig))

    def restore(self) -> None:
        for mod, name, orig in reversed(self._undo):
            setattr(mod, name, orig)
        self._undo.clear()


def _build_inputs() -> tuple[Any, tuple[Any, ...], bytes]:
    """contract / anchors / substrate 字节 —— 全部离线现造。"""
    import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
    from app.services.workpaper_sync.contracts import parse_contract
    from app.services.workpaper_sync import projection_first_publication as F
    from app.services.workpaper_sync import publish_time_structure_hash as PH

    contract = parse_contract(D4.build_contract_payload())
    specs = tuple(D4.instrumentation_specs())
    fn = getattr(PH, "anchors_from_instrumentation_specs", None)
    if fn is None:
        one = PH.anchors_from_instrumentation_spec
        anchors = tuple(one(s) for s in specs)
    else:
        anchors = tuple(fn(specs))

    with tempfile.TemporaryDirectory(prefix="prof-multisheet-") as tmp:
        staged = F.stage_instrumented_substrate(
            entry_id=ENTRY_ID, staging_dir=Path(tmp), contract=contract
        )
        path = Path(str(getattr(staged, "staged_path", staged)))
        data = path.read_bytes()
    return contract, anchors, data


def run() -> dict[str, Any]:
    contract, anchors, data = _build_inputs()
    m = len(anchors)

    from app.services import excel_structure_fingerprint as FP
    from app.services.workpaper_sync import published_identity_observer as OBS
    from app.services.workpaper_sync import publish_time_structure_hash as PH

    counter = _Counter()
    counter.wrap(FP, "structure_fingerprint")
    counter.wrap(FP, "_read_gt_sync_pairs")
    counter.wrap(FP, "identity_inventory")
    # observer 模块内以 from-import 绑定了同名符号，两处都要 patch 才计得全
    counter.wrap(OBS, "structure_fingerprint", "structure_fingerprint")
    counter.wrap(OBS, "identity_inventory", "identity_inventory")
    counter.wrap(OBS, "_read_gt_sync_pairs", "_read_gt_sync_pairs")

    t0 = time.perf_counter()
    err: str | None = None
    digest: str | None = None
    try:
        digest = PH.compute_structure_hash_from_artifact(
            data=data, contract=contract, anchors=list(anchors)
        )
    except Exception as exc:  # noqa: BLE001 —— 剖析脚本要如实报告失败而非崩
        err = f"{type(exc).__name__}: {exc}"
    finally:
        elapsed = time.perf_counter() - t0
        counter.restore()

    stats = {
        k: {"calls": int(v["calls"]), "seconds": round(v["seconds"], 3)}
        for k, v in sorted(counter.stats.items(), key=lambda kv: -kv[1]["seconds"])
    }
    fp_calls = stats.get("structure_fingerprint", {}).get("calls", 0)
    sync_calls = stats.get("_read_gt_sync_pairs", {}).get("calls", 0)

    # 判据：次数不随 M 增长 ⇒ 应为常数级，而非 ~1+M
    linear_in_m = fp_calls > _COUNT_BUDGET_CONST and fp_calls >= m
    verdict = "FAIL" if linear_in_m else "PASS"

    return {
        "entry_id": ENTRY_ID,
        "anchors_m": m,
        "substrate_bytes": len(data),
        "structure_hash": digest,
        "error": err,
        "collect_seconds": round(elapsed, 3),
        "counts": stats,
        "criterion": {
            "name": "解析次数不随 binding 数增长",
            "structure_fingerprint_calls": fp_calls,
            "read_gt_sync_pairs_calls": sync_calls,
            "const_budget": _COUNT_BUDGET_CONST,
            "verdict": verdict,
            "explain": (
                f"fingerprint 调用 {fp_calls} 次 >= anchor 数 {m}，呈 O(M)，未共享"
                if linear_in_m
                else f"fingerprint 调用 {fp_calls} 次 <= 常数预算 {_COUNT_BUDGET_CONST}，与 M({m}) 无关"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", default=None, help="把报告写到该文件")
    args = parser.parse_args()

    report = run()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        # Windows 控制台可能是 GBK：退化为 ASCII 转义输出，不影响 --json 落盘的 UTF-8 原文
        sys.stdout.write(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return 0 if report["criterion"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
