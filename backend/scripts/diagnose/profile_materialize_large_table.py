"""离线剖析大表 materialize 耗时（可复算基线 / 复杂度自判）。

spec: workpaper-sync-materialize-large-table-performance · Wave 0 Task 1
Requirements: 4.1, 4.2, 4.4 · Property 9

对同一份真实 D2 权威模板衍生的 substrate，在多个行规模各跑一次
``materialize_projection``（纯引擎、不连库），输出::

    rows, seconds, seconds_per_row, field_count

并**自动判定**「每行摊销成本不随规模上升」::

    seconds_per_row[max] <= seconds_per_row[ref] * tolerance

数字现场实测，不手抄。优化前预期呈超线性、判据失败；优化后判据通过。

用法（仓库根）::

    python backend/scripts/diagnose/profile_materialize_large_table.py
    python backend/scripts/diagnose/profile_materialize_large_table.py --rows 10,50,200
    python backend/scripts/diagnose/profile_materialize_large_table.py \\
        --out .kiro/specs/_archive/15-workpaper-sync-engine-hardening/workpaper-sync-materialize-large-table-performance/evidence/baseline-pre-opt.json

`--out` 无默认值（默认只打印不落盘），所以本示例路径失效不会让脚本报错；但 spec 已于
2026-09-25 归档进 `_archive/15-workpaper-sync-engine-hardening/`，照抄旧路径会 `FileNotFoundError`。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import d2_bidirectional_bridge as bridge  # noqa: E402
from app.services.workpaper_sync import excel_materialize as XM  # noqa: E402
from app.services.workpaper_sync import pilot_d2_large_json as P  # noqa: E402
from app.services.workpaper_sync.adapters.base import SubstrateRole  # noqa: E402
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState  # noqa: E402

DEFAULT_ROW_SCALES: tuple[int, ...] = (10, 50, 200, 729)
#: 729 相对 200 的每行摊销容差。超线性时必然失败；线性或更好则通过。
DEFAULT_TOLERANCE = 1.15
#: 复杂度自判的参照规模（取中档，避开小 N 的固定开销主导）。
DEFAULT_REF_ROWS = 200


def _aging_zero() -> dict[str, float]:
    return {seg: 0.0 for seg, _label in P.AGING_SEGMENTS}


def make_synthetic_rows(n: int) -> list[dict[str, Any]]:
    """构造 n 行最小合法 store 行（稳定 rowId + 标量/账龄叶子）。"""
    if n < 0:
        raise ValueError(f"row count 不得为负: {n}")
    rows: list[dict[str, Any]] = []
    for i in range(n):
        row: dict[str, Any] = {
            P.ROW_IDENTITY_STORE_KEY: f"dr-bench-{i:06d}",
            "seq": i + 1,
            "customerName": f"剖析客户{i + 1}",
            "companyCode": f"C{i + 1:04d}",
            "relationType": "非关联方",
            "priorUnadjusted": float(i),
            "priorAje": 0.0,
            "priorRje": 0.0,
            "priorAudited": float(i),
            "debitOccurrence": 1.0,
            "creditOccurrence": 0.0,
            "endBalance": float(i + 1),
            "reclassification": 0.0,
            "currentUnadjusted": float(i + 1),
            "currentAje": 0.0,
            "currentRje": 0.0,
            "currentAudited": float(i + 1),
            "creditRiskClassification": "",
            "groupName": "",
            "isConfirmation": False,
            "postPayment": 0.0,
            "remark": "",
            "agingPrior": _aging_zero(),
            "agingCurrent": _aging_zero(),
            "agingAudited": _aging_zero(),
        }
        rows.append(row)
    return rows


def prepare_substrate(*, rows: Sequence[Mapping[str, Any]], work_dir: Path) -> Path:
    """权威模板 → 插桩 → 扩行 → 播种 UUID，写出可 materialize 的 substrate。"""
    original = P.read_authoritative_template()
    carrier, _newly = bridge.ensure_instrumented(original)
    expanded = bridge._ensure_row_capacity(carrier, len(rows))  # noqa: SLF001
    seeded = bridge._seed_row_identity(expanded, list(rows))  # noqa: SLF001
    path = work_dir / f"substrate-{len(rows)}.xlsx"
    path.write_bytes(seeded)
    return path


def run_materialize_once(
    *,
    rows: Sequence[Mapping[str, Any]],
    work_dir: Path,
) -> dict[str, Any]:
    """准备 substrate 后只对 ``materialize_projection`` 计时。"""
    contract = P.load_pilot_contract()
    projection = bridge.rows_to_projection(list(rows), contract=contract)
    substrate = prepare_substrate(rows=rows, work_dir=work_dir)
    binding = bridge.identity_binding()
    definitions = bridge.build_frozen_definitions(
        contract=contract, workbook_bytes=substrate.read_bytes()
    )
    output = work_dir / f"out-{len(rows)}.xlsx"

    started = time.perf_counter()
    outcome = XM.materialize_projection(
        substrate=substrate,
        projection=projection,
        output=output,
        definitions=definitions,
        binding=binding,
        substrate_role=SubstrateRole.published_representation,
        substrate_kind=ArtifactKind.canonical,
        substrate_state=ArtifactState.published,
    )
    elapsed = time.perf_counter() - started
    field_count = len(projection.stable_keys())
    per_row = elapsed / len(rows) if rows else elapsed
    return {
        "rows": len(rows),
        "seconds": round(elapsed, 4),
        "seconds_per_row": round(per_row, 6),
        "field_count": field_count,
        "artifact_sha256": getattr(
            getattr(outcome, "result", outcome), "artifact_sha256", None
        ),
        "write_strategy": str(
            getattr(getattr(outcome, "strategy", None), "strategy", "")
            or getattr(outcome, "strategy", "")
        )[:120],
    }


def judge_linearity(
    samples: Sequence[Mapping[str, Any]],
    *,
    ref_rows: int,
    tolerance: float,
) -> dict[str, Any]:
    """每行摊销成本不随规模上升 ⇒ pass；否则 fail（优化前基线预期 fail）。"""
    by_rows = {int(s["rows"]): s for s in samples}
    if ref_rows not in by_rows:
        return {
            "passed": False,
            "reason": f"缺少参照规模 {ref_rows} 的样本",
            "ref_rows": ref_rows,
            "tolerance": tolerance,
        }
    max_rows = max(by_rows)
    if max_rows <= ref_rows:
        return {
            "passed": False,
            "reason": f"最大规模 {max_rows} 不大于参照 {ref_rows}，无法判定",
            "ref_rows": ref_rows,
            "tolerance": tolerance,
        }
    ref_spr = float(by_rows[ref_rows]["seconds_per_row"])
    max_spr = float(by_rows[max_rows]["seconds_per_row"])
    limit = ref_spr * tolerance
    passed = max_spr <= limit
    return {
        "passed": passed,
        "ref_rows": ref_rows,
        "max_rows": max_rows,
        "ref_seconds_per_row": ref_spr,
        "max_seconds_per_row": max_spr,
        "tolerance": tolerance,
        "limit": round(limit, 6),
        "ratio": round(max_spr / ref_spr, 4) if ref_spr > 0 else None,
        "reason": (
            f"seconds_per_row[{max_rows}]={max_spr:.6f} "
            f"{'<=' if passed else '>'} "
            f"seconds_per_row[{ref_rows}]×{tolerance}={limit:.6f}"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rows",
        default=",".join(str(n) for n in DEFAULT_ROW_SCALES),
        help="逗号分隔的行规模，默认 10,50,200,729",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="每行摊销成本容差（max 相对 ref）",
    )
    parser.add_argument(
        "--ref-rows",
        type=int,
        default=DEFAULT_REF_ROWS,
        help="复杂度自判的参照行规模",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="把实测 JSON 写到该路径（现场数字，非手抄）",
    )
    parser.add_argument(
        "--expect-fail",
        action="store_true",
        help="优化前基线：判据失败时 exit 0（记录超线性锚点）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    scales = tuple(int(x.strip()) for x in str(args.rows).split(",") if x.strip())
    if not scales:
        print("ERROR: --rows 为空", file=sys.stderr)
        return 2

    samples: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mat-profile-") as tmp:
        work = Path(tmp)
        for n in scales:
            print(f"[profile] preparing + materialize rows={n} …", flush=True)
            sample = run_materialize_once(rows=make_synthetic_rows(n), work_dir=work)
            samples.append(sample)
            print(
                f"[profile] rows={sample['rows']}  "
                f"seconds={sample['seconds']:.4f}  "
                f"per_row={sample['seconds_per_row']:.6f}  "
                f"fields={sample['field_count']}",
                flush=True,
            )

    verdict = judge_linearity(
        samples, ref_rows=int(args.ref_rows), tolerance=float(args.tolerance)
    )
    payload = {
        "script": "profile_materialize_large_table.py",
        "spec": "workpaper-sync-materialize-large-table-performance",
        "task": "Wave 0 Task 1",
        "engine": "materialize_projection",
        "template": P.TEMPLATE_RELATIVE_PATH,
        "template_sha256": P.TEMPLATE_SHA256,
        "samples": samples,
        "linearity": verdict,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text, flush=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"[profile] wrote {args.out}", flush=True)

    if verdict["passed"]:
        print("[profile] LINEARITY PASS", flush=True)
        return 0
    print(f"[profile] LINEARITY FAIL: {verdict['reason']}", flush=True)
    # 优化前基线允许 --expect-fail：失败即「锚点已记录」，exit 0。
    if args.expect_fail:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
