"""统一 CLI 入口：``--list`` / ``--check-anchors`` / ``--run`` / ``--restore``。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.2, 6.3, 6.4, 6.7 · Property 21, 22, 23, 24

## `guard_files` 是必填关键字参数

不是「建议声明」而是**签名层面必填** —— 让「没有覆盖面分母」这件事在调用侧
不可能发生。平台 17 个变异脚本里只有 3 个有分母，正是因为它此前靠约定。

## `--list` 不得只打印

g7 spec 沉淀的教训：只打印的 `--list` 在 CI 里恒绿，等于没挂。本实现的 `--list`
同时校验四件事，任一不成立即非零退出：

1. 声明期校验全过（`spec.validate_all`：锚点不含换行、`new != anchor`、id 唯一…）
2. 每条锚点在目标文件里**恰好命中 1 行**
3. 目标文件存在
4. ``want`` 能在登记的守卫文件里定位到（否则判定永远只能是 WRONG-TEST）

## `--check-anchors` 只读

执行后目标文件 md5 全不变、无 `.mutbak` 残留、无新增文件。它是「已归档 spec 的
变异体系是否还可复现」的最便宜判据：秒级、零风险，不必重跑全量变异去改那些
可能带着并发在途改动的文件。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .anchor import AnchorMiss, block_range, find_anchor, md5_of, read_lines
from .apply import BAK_SUFFIX, RestoreFailed, mutated, restore_all, stale_backups
from .coverage import CoverageTally, guard_files_of
from .runner import RunResult, run_pytest, run_vitest
from .spec import Mutation, validate_all
from .verdict import ANCHOR_MISS, ERROR, GREEN, RED, WRONG_TEST, judge

DEFAULT_GUARD_ROOTS = ("backend/tests", "audit-platform/frontend/src")


def _reconfigure_stdio() -> None:
    """PS 控制台默认 GBK，报告含中文与箭头 ⇒ 不重配会在报告阶段 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - 老版本 Python 无 reconfigure
            pass


def _select(mutations: list[Mutation], spec: str) -> list[Mutation]:
    if not spec or spec == "all":
        return list(mutations)
    if spec in ("be", "fe"):
        return [m for m in mutations if m.side == spec]
    ids = {s.strip().upper() for s in spec.split(",") if s.strip()}
    got = [m for m in mutations if m.id.upper() in ids]
    missing = ids - {m.id.upper() for m in got}
    if missing:
        raise SystemExit(f"未知变异 id：{sorted(missing)}")
    return got


def _guard_file_paths(
    repo: Path, guard_files: dict[str, str], roots: tuple[str, ...]
) -> dict[str, list[Path]]:
    """按文件名在给定根目录下递归定位（同名多处时全部返回）。"""
    out: dict[str, list[Path]] = {name: [] for name in guard_files}
    for rel in roots:
        base = repo / rel
        if not base.is_dir():
            continue
        for name in guard_files:
            out[name].extend(sorted(base.rglob(name)))
    return out


def _locate_want(want: str, paths: dict[str, list[Path]]) -> list[str]:
    """``want`` 能在哪些守卫文件里找到（子串匹配；后端 nodeid 取末段）。"""
    needle = want.split("::")[-1]
    hits: list[str] = []
    for name, files in paths.items():
        for fp in files:
            try:
                body = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if needle and needle in body:
                hits.append(name)
                break
    return sorted(set(hits))


def _cmd_list(
    mutations: list[Mutation], repo: Path, guard_files: dict[str, str],
    roots: tuple[str, ...],
) -> int:
    """打印 + 校验。任一校验不过即返回非零。"""
    problems: list[str] = []

    decl = validate_all(mutations)
    problems.extend(decl)

    paths = _guard_file_paths(repo, guard_files, roots)
    for name, files in paths.items():
        if not files:
            problems.append(f"<guard_files>: {name} 在 {list(roots)} 下找不到 —— 分母项失效")

    for m in mutations:
        target = m.abspath(repo)
        print(f"{m.id}  {m.side}  {m.kind:<8} {m.path}")
        print(f"      want: {m.want}")
        print(f"      why : {m.why[:150]}")
        if not target.exists():
            problems.append(f"{m.id}: 目标文件不存在 {m.path}")
            continue
        try:
            lines = read_lines(target)
            idx = find_anchor(lines, m.anchor, m.line)
            print(f"      anchor: L{idx + 1} 唯一命中")
            if m.kind in ("swap", "move"):
                j = find_anchor(lines, m.anchor2)
                a = block_range(lines, idx, m.block_open)
                b = block_range(lines, j, m.block_open)
                print(f"      blocks: A={a[0] + 1}..{a[1]}  B={b[0] + 1}..{b[1]}")
        except AnchorMiss as exc:
            problems.append(f"{m.id}: 锚点校验失败 —— {exc}")
        hit_files = _locate_want(m.want, paths)
        if hit_files:
            print(f"      want 可定位于: {hit_files}")
        else:
            problems.append(
                f"{m.id}: want={m.want!r} 在登记的守卫文件里定位不到 —— "
                "判定将永远只能是 WRONG-TEST"
            )

    print()
    if problems:
        print(f"[FAIL] --list 校验发现 {len(problems)} 个问题：")
        for p in problems:
            print(f"  !! {p}")
        return 1
    print(f"[OK] --list 校验通过：{len(mutations)} 条变异声明、"
          f"{len(guard_files)} 个分母文件全部可定位")
    return 0


def _cmd_check_anchors(mutations: list[Mutation], repo: Path) -> int:
    """只读锚点自检。跑完核验「目标文件 md5 未变 + 无 .mutbak 残留」。"""
    before = {m.path: (md5_of(m.abspath(repo)) if m.abspath(repo).exists() else None)
              for m in mutations}
    bad = 0
    for m in mutations:
        target = m.abspath(repo)
        if not target.exists():
            bad += 1
            print(f"[MISS] {m.id} {m.kind:<8} {m.path}\n        目标文件不存在")
            continue
        try:
            lines = read_lines(target)
            i = find_anchor(lines, m.anchor, m.line)
            extra = ""
            if m.kind in ("swap", "move"):
                j = find_anchor(lines, m.anchor2)
                a = block_range(lines, i, m.block_open)
                b = block_range(lines, j, m.block_open)
                extra = f"  blockA={a[0] + 1}..{a[1]} blockB={b[0] + 1}..{b[1]}"
            print(f"[OK  ] {m.id} {m.kind:<8} L{i + 1} {m.path}{extra}")
        except AnchorMiss as exc:
            bad += 1
            print(f"[MISS] {m.id} {m.kind:<8} {m.path}\n        {exc}")

    changed = [
        m.path for m in mutations
        if m.abspath(repo).exists() and md5_of(m.abspath(repo)) != before[m.path]
    ]
    leftover = stale_backups(repo)
    print(f"\n锚点自检：{len(mutations) - bad}/{len(mutations)} OK，{bad} MISS")
    if changed:
        print(f"[FATAL] --check-anchors 必须只读，但以下文件被改动：{changed}")
        return 2
    if leftover:
        print(f"[FATAL] --check-anchors 必须只读，但留下了备份：{[str(p) for p in leftover]}")
        return 2
    print("只读性核验：目标文件 md5 全部未变、无 .mutbak 残留")
    return 1 if bad else 0


def _run_one(
    m: Mutation, repo: Path, baseline: set[str], runner: Callable[[], RunResult]
) -> dict:
    rec: dict = {"id": m.id, "side": m.side, "want": m.want, "why": m.why}
    t0 = time.time()
    before_md5 = md5_of(m.abspath(repo))
    try:
        with mutated(m, repo) as mutated_bytes:
            if m.scope_check is not None and not m.scope_check(mutated_bytes):
                rec["verdict"] = ANCHOR_MISS
                rec["detail"] = (
                    "作用域自证失败 —— 变异落在被测判据的作用域之外"
                    "（锚点可能命中了同名的文档/注释/无关结构）"
                )
            else:
                res = runner()
                v, added, gone, hit = judge(m.want, baseline, res.failed, m.wants)
                rec.update(
                    verdict=v, summary=res.summary, added=added, gone=gone, hit=hit,
                    added_files=sorted(guard_files_of(added, res.name2file)),
                )
    except AnchorMiss as exc:
        rec["verdict"] = ANCHOR_MISS
        rec["detail"] = str(exc)
    except RestoreFailed:
        raise
    except Exception as exc:  # noqa: BLE001 - 记录并继续；还原已在 finally 完成
        rec["verdict"] = ERROR
        rec["detail"] = f"{type(exc).__name__}: {exc}"
    rec["restored"] = md5_of(m.abspath(repo)) == before_md5
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def run_cli(
    *,
    mutations: list[Mutation],
    guard_files: dict[str, str],
    repo: Path,
    description: str = "守卫变异检验",
    backend_args: list[str] | None = None,
    frontend_filters: list[str] | None = None,
    frontend_dir: Path | None = None,
    vitest_json: Path | None = None,
    baseline_backend_passed: int | None = None,
    baseline_frontend_passed: int | None = None,
    guard_roots: tuple[str, ...] = DEFAULT_GUARD_ROOTS,
    allow_dirty_baseline: bool = False,
    argv: list[str] | None = None,
) -> int:
    """变异检验统一入口。

    :param guard_files: **必填** —— 覆盖面分母（守卫文件名 → 归属说明）
    :param baseline_backend_passed: 冻结基线；不符时 WARN（改基线必须说明来源）
    :param allow_dirty_baseline: 允许基线含既存失败。默认 False（ABORT）。

        差集判定（`added = current - baseline`）在脏基线下**仍然有效**，但基线非空
        通常意味着环境漂移或依赖问题，此时变异结果的可解读性下降，故默认拦住。

        显式开启的场景只有一个：**迁移等价** —— 某些存量脚本的判据本来就允许脏基线
        （如 `mutate_note_text_hygiene_and_expandable` 的 docstring 明写「基线可能本就有红」），
        迁移不该让原本能跑的脚本变成不能跑。开启时必须在调用处写明理由。
    """
    _reconfigure_stdio()
    tally = CoverageTally(guard_files)  # 空分母在此直接抛，不给「后面再说」的机会

    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--list", action="store_true", help="列出并校验全部变异声明")
    ap.add_argument("--check-anchors", action="store_true", help="只读锚点自检，不改文件")
    ap.add_argument("--run", metavar="SPEC", help="执行：all | be | fe | M01,M02")
    ap.add_argument("--restore", action="store_true", help="还原所有 .mutbak")
    ap.add_argument("--out", metavar="PATH", help="结果 JSON 落盘路径")
    args = ap.parse_args(argv)

    # 声明期校验对所有子命令无条件生效 —— 坏声明不该有机会跑起来
    decl_problems = validate_all(mutations)
    if decl_problems and not args.list:
        print(f"[FAIL] 变异声明校验不通过（{len(decl_problems)} 项）：")
        for p in decl_problems:
            print(f"  !! {p}")
        return 6

    if args.restore:
        print(f"还原 {restore_all(repo)} 个备份文件")
        return 0
    if args.list:
        return _cmd_list(mutations, repo, guard_files, guard_roots)

    muts = _select(mutations, args.run or "all")
    if args.check_anchors:
        return _cmd_check_anchors(muts, repo)
    if not args.run:
        ap.print_help()
        return 2

    stale = stale_backups(repo)
    if stale:
        print("[ABORT] 存在残留备份，先 --restore：")
        for p in stale:
            print(f"  {p}")
        return 3

    sides = {m.side for m in muts}
    if "fe" in sides and (frontend_dir is None or vitest_json is None):
        print("[ABORT] 含 fe 侧变异但未提供 frontend_dir / vitest_json")
        return 7
    if "be" in sides and not backend_args:
        print("[ABORT] 含 be 侧变异但未提供 backend_args")
        return 7

    def be_runner() -> RunResult:
        return run_pytest(repo, list(backend_args or []))

    def fe_runner() -> RunResult:
        assert frontend_dir is not None and vitest_json is not None
        return run_vitest(frontend_dir, list(frontend_filters or []), vitest_json)

    print(f"变异 {len(muts)} 条，涉及侧：{sorted(sides)}")
    baselines: dict[str, set[str]] = {}
    for side, runner, frozen, label in (
        ("be", be_runner, baseline_backend_passed, "后端"),
        ("fe", fe_runner, baseline_frontend_passed, "前端"),
    ):
        if side not in sides:
            continue
        print(f"\n── {label}基线 ──")
        res = runner()
        baselines[side] = res.failed
        print(f"  {res.summary}")
        print(f"  失败名集合：{sorted(res.failed) or '空集'}")
        if res.failed and not allow_dirty_baseline:
            print("  [ABORT] 基线非空，变异差集判定不可信")
            print("          若该脚本的判据本就允许脏基线（差集 added = current - baseline "
                  "不受既存失败影响），传 allow_dirty_baseline=True 并在脚本里写明理由")
            return 4
        if res.failed:
            print(f"  [WARN] 基线非空但已显式允许：{len(res.failed)} 条既存失败。"
                  "差集判定仍有效，但既存失败的成因应单独查清")
        if frozen is not None and res.passed != frozen:
            print(f"  [WARN] 与冻结基线 {frozen} passed 不符（实测 {res.passed}）"
                  " —— 改基线必须同时说明来源")

    results: list[dict] = []
    for m in muts:
        runner = be_runner if m.side == "be" else fe_runner
        print(f"\n── {m.id} [{m.side}] {m.kind} {Path(m.path).name} ──")
        print(f"   {m.why[:180]}")
        try:
            rec = _run_one(m, repo, baselines[m.side], runner)
        except RestoreFailed as exc:
            print(f"   [FATAL] {exc}")
            return 5
        results.append(rec)
        v = rec["verdict"]
        print(f"   判定 {v}  ({rec.get('seconds')}s)  还原={rec.get('restored')}")
        if rec.get("summary"):
            print(f"   {rec['summary']}")
        if rec.get("detail"):
            print(f"   detail: {rec['detail']}")
        if v == RED:
            print(f"   命中 want：{rec['hit'][:4]}")
            print(f"   新增失败 {len(rec['added'])} 条")
            tally.record(rec.get("added_files") or [])
        elif v == WRONG_TEST:
            print(f"   want 未命中：{m.want}")
            print(f"   实际新增：{rec['added'][:10]}")
            tally.record(rec.get("added_files") or [])
        elif v == GREEN:
            print("   [守卫缺陷] 变异未被任何守卫捕获")
        if rec.get("gone"):
            print(f"   [WARN] 基线中消失的失败项：{rec['gone'][:5]}")
        if not rec.get("restored"):
            print("   [FATAL] 还原核验失败，停止后续变异")
            break

    print("\n" + "=" * 72)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for k in (RED, GREEN, WRONG_TEST, ANCHOR_MISS, ERROR):
        if k in counts:
            print(f"  {k:<12} {counts[k]}")
    for r in results:
        flag = "OK " if r["verdict"] == RED else "!! "
        files = ",".join(r.get("added_files") or []) or "-"
        print(f"  {flag}{r['id']}  {r['verdict']:<12} {r['want'][:40]:<40} [{files}]")

    full_run = len(muts) == len(mutations)
    print()
    for line in tally.report(full_run):
        print(line)

    if args.out:
        Path(args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n结果已落盘：{args.out}")

    left = stale_backups(repo)
    if left:
        print(f"[FATAL] 残留备份 {len(left)} 个，需手动 --restore")
        return 5
    # 🔴 覆盖面只在**全量运行**时参与退出码：子集运行（`--run M01,M02`）天然覆盖不全，
    # 把 `is_complete(full_run=False)` 算进退出码会让子集运行**恒非零** —— 于是
    # 「只跑一条变异确认它还红」这个最常用的动作在 CI 或脚本里永远失败。
    # 该缺陷是 Task 11 迁移 e-cycle 时用 `--run M01,...` 做等价性比对才暴露的：
    # 判定矩阵 6/6 逐一相同却 RC=1。
    all_red = bool(results) and counts.get(RED) == len(results)
    coverage_ok = tally.is_complete(True) if full_run else True
    return 0 if (all_red and coverage_ok) else 1
