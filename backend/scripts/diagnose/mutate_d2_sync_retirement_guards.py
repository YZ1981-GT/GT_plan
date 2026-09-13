"""G4-2 退役守卫的变异检验（四态判读 + 哈希还原自检）。

═══ 为什么必须做 ═══

「删干净了」这件事只能由守卫证明，而守卫本身可能是恒真重言式。本脚本对每条禁令
制造一次**真实**违反（在磁盘上），跑指定测试，确认它打红，然后逐字节还原。

═══ 四态判读（只看退出码会把后三态误判成 RED）═══

  RED          预期那条测试打红（守卫成立）
  GREEN        测试仍全绿 ⇒ 守卫缺陷
  ANCHOR-MISS  变异没落地（锚点缺失或命中 >1）⇒ 脚本缺陷
  WRONG-TEST   打红了但不是预期那条 ⇒ 锚点错行或有污染残留

用法::

    python backend/scripts/diagnose/mutate_d2_sync_retirement_guards.py
    python backend/scripts/diagnose/mutate_d2_sync_retirement_guards.py --json out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_FE = _REPO / "audit-platform" / "frontend"

GUARD_SPEC = "backend/tests/workpaper_sync/test_d2_sync_retirement.py"
STORE_SPEC = "backend/tests/workpaper_sync/test_d2_store_value_equivalence.py"

ROUTER = _BACKEND / "app" / "routers" / "d2_sync_router.py"
FE_BRIDGE = _FE / "src" / "components" / "workpaper" / "sync" / "useD2SyncBridge.ts"
REGISTRY = _BACKEND / "app" / "router_registry" / "workpaper.py"
BRIDGE = _BACKEND / "app" / "services" / "workpaper_sync" / "d2_bidirectional_bridge.py"
HOST_WIRING = _FE / "src" / "components" / "workpaper" / "__tests__" / "d2SyncHostWiring.spec.ts"
OO_SHEET = _FE / "src" / "components" / "workpaper" / "GtOnlyOfficeSheet.vue"
OO_TO_HTML = _BACKEND / "app" / "services" / "workpaper_sync" / "oo_to_html.py"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "<absent>"


@dataclass
class Mutation:
    """一次变异。`apply` 就地改盘并返回「是否真的落地」。"""

    id: str
    name: str
    targets: tuple[Path, ...]
    spec: str
    expect_test: str
    apply: Callable[[], bool]


def _replace_once(path: Path, old: str, new: str) -> bool:
    """唯一锚点替换。命中 0 次或 >1 次一律不改盘（ANCHOR-MISS）。"""
    text = path.read_bytes().decode("utf-8")
    if text.count(old) != 1:
        return False
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    return True


def _replace_all(path: Path, old: str, new: str, *, expected: int) -> bool:
    """全量替换，但命中数必须**恰等于** `expected`（少了/多了都是 ANCHOR-MISS）。

    不写 `expected` 就等于「命中几处算几处」，源码增删一处分支时脚本会静默少改一处，
    结果被读成「守卫缺陷」。
    """
    text = path.read_bytes().decode("utf-8")
    if text.count(old) != expected:
        return False
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    return True


def _create(path: Path, body: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))
    return True


def _append(path: Path, body: str) -> bool:
    if not path.is_file():
        return False
    path.write_bytes(path.read_bytes() + body.encode("utf-8"))
    return True


def _delete(path: Path) -> bool:
    if not path.is_file():
        return False
    path.unlink()
    return True


_FAKE_ROUTER = '''"""变异注入的假 router —— 变异检验结束会被删除。"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/workpapers", tags=["mutation"])


@router.get("/{wp_id}/d2-sync/status")
async def d2_sync_status(wp_id: str) -> dict:
    return {"bidirectional": True}
'''

_FAKE_FE_BRIDGE = """// 变异注入的假前端桥 —— 变异检验结束会被删除。
export function useD2SyncBridge() {
  return { path: '/api/workpapers/x/d2-sync/status' }
}
"""


def build_mutations() -> tuple[Mutation, ...]:
    return (
        Mutation(
            "M01",
            "后端 legacy router 复活（模块可导入 + 路由回来 + 相位变 partial）",
            (ROUTER,),
            GUARD_SPEC,
            "test_legacy_router_module_is_not_importable",
            lambda: _create(ROUTER, _FAKE_ROUTER),
        ),
        Mutation(
            "M02",
            "前端 legacy 桥文件复活",
            (FE_BRIDGE,),
            GUARD_SPEC,
            "test_legacy_frontend_bridge_file_is_gone",
            lambda: _create(FE_BRIDGE, _FAKE_FE_BRIDGE),
        ),
        Mutation(
            "M03",
            "后端生产模块重新把 d2-sync 当端点字面量用",
            (OO_TO_HTML,),
            GUARD_SPEC,
            "test_no_production_source_uses_the_retired_endpoint",
            lambda: _append(OO_TO_HTML, '\n_MUTATION_LEGACY_PATH = "/api/workpapers/{x}/d2-sync/status"\n'),
        ),
        Mutation(
            "M04",
            "registry 重新绑定 d2_sync",
            (REGISTRY,),
            GUARD_SPEC,
            "test_no_route_declares_a_d2_sync_path",
            lambda: _replace_once(
                REGISTRY,
                "    from app.routers.cutoff_sampling import router as cutoff_sampling",
                "    from app.routers.wp_sync_router import router as d2_sync\n"
                "    from app.routers.cutoff_sampling import router as cutoff_sampling",
            ),
        ),
        Mutation(
            "M05",
            "把仍在被统一路径消费的桥一起删掉（删过头）",
            (BRIDGE,),
            GUARD_SPEC,
            "test_reusable_bridge_is_retained_not_collateral_damage",
            lambda: _delete(BRIDGE),
        ),
        Mutation(
            "M06",
            "拆掉缺陷 A 反向锁的顺序断言",
            (HOST_WIRING,),
            GUARD_SPEC,
            "test_replacement_surface_still_covers_what_legacy_covered",
            lambda: _replace_once(
                HOST_WIRING,
                "expect(readAt).toBeGreaterThan(flushAt)",
                "expect(readAt).not.toBe(-1)",
            ),
        ),
        Mutation(
            "M07",
            "去掉 G4-0a fail-closed 的必填端点判断",
            (OO_SHEET,),
            GUARD_SPEC,
            "test_replacement_surface_still_covers_what_legacy_covered",
            lambda: _replace_once(OO_SHEET, "if (!endpoint) {", "if (false) {"),
        ),
        Mutation(
            "M08",
            "打断一处防复活负向断言（宿主不得调 legacy 桥）",
            (HOST_WIRING,),
            GUARD_SPEC,
            "test_anti_revival_negative_assertions_are_all_alive",
            lambda: _replace_once(
                HOST_WIRING,
                "expect(hostSrc).not.toMatch(/useD2SyncBridge\\s*\\(/)",
                "expect(hostSrc).toBeTruthy()",
            ),
        ),
        Mutation(
            # 🔴 预期项修正（首跑判 WRONG-TEST）：只掏空 D2 分支时，h1/b60 分支仍绑着同名
            # 函数，故「接线是否存在」那条通用判据**应该**保持绿 —— 打红的是 D2 专属那条。
            # 这不是守卫缺陷，是本脚本一开始把预期项写错了。M10 才是通用判据的变异。
            "M09",
            "只掏空 D2 分支的 store 合并绑定（错绑成别的 pilot 的同名函数）",
            (OO_TO_HTML,),
            STORE_SPEC,
            "test_d2_branch_of_the_store_mirror_binds_this_bridge",
            lambda: _replace_once(
                OO_TO_HTML,
                "            merge_rows_fn = bridge.merge_projection_into_store_rows\n"
                '        elif adapter_id == "h1.disposal_check":',
                "            merge_rows_fn = None  # MUTATION\n"
                '        elif adapter_id == "h1.disposal_check":',
            ),
        ),
        Mutation(
            "M10",
            "掏空**全部** store 合并绑定（通用接线反向锁）",
            (OO_TO_HTML,),
            STORE_SPEC,
            "test_unified_oo_to_html_really_wires_the_merge_function",
            lambda: _replace_all(
                OO_TO_HTML,
                "merge_rows_fn = bridge.merge_projection_into_store_rows",
                "merge_rows_fn = None  # MUTATION",
                expected=3,
            ),
        ),
    )


def _run_spec(spec: str) -> tuple[int, set[str]]:
    """跑一个测试文件，返回 (退出码, 失败测试名集合)。不经 shell。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", spec, "-q", "--no-header", "-p", "no:randomly", "--tb=no"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    failed: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith(("FAILED", "ERROR")):
            continue
        # 形如 `FAILED backend\tests\...py::TestX::test_y - AssertionError: ...`
        head = stripped.split(" ", 1)[1] if " " in stripped else ""
        ref = head.split(" ")[0]
        if "::" in ref:
            failed.add(ref.rsplit("::", 1)[-1])
    return proc.returncode, failed


def run_all(mutations: tuple[Mutation, ...]) -> list[dict]:
    rows: list[dict] = []
    for mut in mutations:
        before = {p: (_sha(p), p.read_bytes() if p.is_file() else None) for p in mut.targets}
        landed = mut.apply()
        if not landed:
            rows.append(
                {
                    "id": mut.id,
                    "name": mut.name,
                    "verdict": "ANCHOR-MISS",
                    "detail": "锚点缺失或命中不唯一，变异未落盘",
                    "expect_test": mut.expect_test,
                    "failed_tests": [],
                }
            )
            continue
        try:
            code, failed = _run_spec(mut.spec)
        finally:
            for path, (_digest, blob) in before.items():
                if blob is None:
                    if path.is_file():
                        path.unlink()
                else:
                    path.write_bytes(blob)
        restored = all(_sha(path) == digest for path, (digest, _blob) in before.items())
        if code == 0:
            verdict = "GREEN"
            detail = "变异已落盘但测试仍全绿 —— 守卫缺陷"
        elif mut.expect_test in failed:
            verdict = "RED"
            detail = f"预期测试打红（本轮共 {len(failed)} 条红）"
        else:
            verdict = "WRONG-TEST"
            detail = f"打红的是 {sorted(failed)}，不含预期的 {mut.expect_test}"
        rows.append(
            {
                "id": mut.id,
                "name": mut.name,
                "verdict": verdict,
                "detail": detail,
                "expect_test": mut.expect_test,
                "failed_tests": sorted(failed),
                "restored_byte_identical": restored,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G4-2 退役守卫变异检验")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    mutations = build_mutations()
    baseline = {p: _sha(p) for mut in mutations for p in mut.targets}
    rows = run_all(mutations)
    drifted = [str(p.relative_to(_REPO)) for p, digest in baseline.items() if _sha(p) != digest]
    leftovers = [str(p.relative_to(_REPO)) for p in _REPO.rglob("*.mutbak")]

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    for row in rows:
        print(f"[{row['verdict']:11s}] {row['id']} {row['name']}")
        if row["verdict"] != "RED":
            print(f"              {row['detail']}")
    print(f"\n[MUTATION] {counts} declared={len(rows)}")
    print(f"[RESTORE ] 漂移文件={drifted or '无'} .mutbak 残留={leftovers or '无'}")

    report = {
        "work_package": "G4-2",
        "declared_count": len(rows),
        "executed_count": len(rows),
        "verdicts": counts,
        "rows": rows,
        "restore_drift": drifted,
        "mutbak_leftovers": leftovers,
    }
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[MUTATION] 报告已写入 {args.json}")
    ok = counts.get("RED", 0) == len(rows) and not drifted and not leftovers
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
