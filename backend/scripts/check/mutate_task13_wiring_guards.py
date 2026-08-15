# -*- coding: utf-8 -*-
"""Task 13 建议态接线守卫 — 变异检验（前端 vitest 守卫）。

Feature: procedure-trimming-and-delegation-intelligence — Task 13 / Task 22 预演
Requirements: 14.3, 14.4, 14.7

被测守卫::

    audit-platform/frontend/src/views/__tests__/trimDecisionWiring.spec.ts

用法::

    python backend/scripts/check/mutate_task13_wiring_guards.py --anchors   # 只核验锚点唯一性
    python backend/scripts/check/mutate_task13_wiring_guards.py
    python backend/scripts/check/mutate_task13_wiring_guards.py --only M2 M5
    python backend/scripts/check/mutate_task13_wiring_guards.py --restore

═══ 四态判定（只看退出码会把后三态误判成 RED）═══

- ``RED(assertion)``        变异被抓到，且**正是预期那条**测试打红
- ``RED(collection-error)`` 变异让整个 suite collection 失败（也算抓到，但要与断言红区分）
- ``RED(baseline-flip)``    基线红转绿 —— 同样是有效信号
- ``WRONG-TEST``            打红了但不是预期项（污染残留或锚点错行）
- ``GREEN``                 失败集合完全不变 ==> **守卫缺陷**（该变异逃逸）
- ``ANCHOR-MISS``           锚点命中数 != 1 ==> **脚本缺陷**，不得当 GREEN 处理

═══ 硬约束 ═══

- 锚点**行级唯一**：``splitlines()`` + needle 行内匹配 + ``hits == 1`` 断言 + 相对偏移。
  禁含 ``\\n`` 的跨行字面量 —— 本工作树为 CRLF，跨行锚点必 MISS。
- 备份落 ``.bak``，``try/finally`` **无条件**写回，还原后 **md5 逐字节核验**。
- 判定读 **vitest JSON**，不读 stdout（本环境控制台被转义符污染会吞输出）。
- 跑测试前先删旧 JSON 并断言新 JSON 存在 —— 否则会解析到**陈旧结果**。
- ``npm exec`` 传 flag 必须加 ``--`` 分隔符，否则 npm 把 ``--reporter`` 当自己的 cli
  config 并 warn ``Unknown cli config``，JSON 根本不生成而退出码仍 0。
- 报告**落盘**再读（同上：stdout 不可靠）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve()
# 🔴 本文件在 backend/scripts/check/ ==> 仓库根是 parents[3]（parents[2] 是 backend/）
_REPO = _HERE.parents[3]
_FE = _REPO / "audit-platform" / "frontend"
assert (_REPO / "backend" / "app" / "main.py").exists(), f"仓库根定位错误: {_REPO}"
assert (_FE / "package.json").exists(), f"前端根定位错误: {_FE}"

TRIM_VUE = _FE / "src" / "views" / "ProcedureTrimming.vue"
DECISION_TS = _FE / "src" / "components" / "workpaper" / "composables" / "procedureTrimDecision.ts"

SPEC_REL = "src/views/__tests__/trimDecisionWiring.spec.ts"
JSON_REL = "_wip_t13_mutation.json"
REPORT = _REPO / "_wip_t13_mutation_report.txt"

FILES = (TRIM_VUE, DECISION_TS)


# ═══════════════════════════════════════════════════════════════════════════
# 变异定义
# ═══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Edit:
    """单处行级改动。

    ``needle`` 用于**行内定位**且必须行级唯一（``hits == 1``）；``offset`` 允许改动
    落在锚点行的相对位置（用于「目标行本身不唯一、但其邻行唯一」的场合）。
    """

    needle: str
    kind: str            # 'sub' | 'insert_after' | 'replace_line'
    old: str = ""        # kind='sub'：行内被替换的子串（必须存在，否则 ANCHOR-MISS）
    new: str = ""        # 'sub' 的替换串；'insert_after'/'replace_line' 的新行内容
    offset: int = 0


@dataclass(frozen=True)
class Mutation:
    mid: str
    path: Path
    edits: tuple[Edit, ...]
    expect_title: str            # 预期打红的测试标题（判 RED 的主判据）
    also: tuple[str, ...] = ()   # 预计连带打红（仅报告用，不参与判定）
    note: str = ""


MUTATIONS: tuple[Mutation, ...] = (
    # ── M1：导出表头去掉「理由码」列 ────────────────────────────────────────
    Mutation(
        "M1",
        TRIM_VUE,
        (
            Edit(
                needle="const aoa: any[][] = [['循环'",
                kind="sub",
                old="'理由码', ",
                new="",
            ),
        ),
        expect_title="表头同时含「裁剪理由」与「理由码」",
        also=("列宽 ws['!cols'] 项数与表头列数相等",),
        note="R8.6：理由码与理由文本必须并列两列，合并成一列后复核方无法按码统计",
    ),
    # ── M2：below_materiality 改走自动裁 ────────────────────────────────────
    Mutation(
        "M2",
        DECISION_TS,
        (
            # 🔴 `verdict: 'suggest_trim'` 全文 2 命中（below_trivial / below_materiality），
            #    不能直接当锚点；改用其下一行的 reasonCode（唯一）+ offset -1 定位。
            Edit(
                needle="reasonCode: 'below_materiality',",
                kind="sub",
                old="'suggest_trim'",
                new="'auto_trim'",
                offset=-1,
            ),
        ),
        expect_title="below_materiality 所在 return 块的 verdict 必为 suggest_trim",
        also=("auto_trim 恰出现 1 次，且其 reasonCode 为 no_data",),
        note="R6.7 核心红线：让「金额小就不查」绕过审计师确认自动生效",
    ),
    # ── M3：建议态分支顺手写适用性 ──────────────────────────────────────────
    Mutation(
        "M3",
        TRIM_VUE,
        (
            Edit(
                needle="p._suggest = true",
                kind="insert_after",
                new="p._applicable = false",
            ),
        ),
        expect_title="suggest_trim 分支不写 _applicable / status / skip_reason",
        note="R6.2：建议直接落成已裁剪，UI 上几乎看不出（那行照样变成「裁剪」）",
    ),
    # ── M4：概览侧去掉「已确认」统计 ────────────────────────────────────────
    Mutation(
        "M4",
        TRIM_VUE,
        (
            Edit(
                needle="const suggestConfirmed = list.filter",
                kind="replace_line",
                new="// suggestConfirmed 被移除（变异 M4）",
            ),
            Edit(
                needle="suggestConfirmed: 0, suggestRejected: 0",
                kind="sub",
                old="suggestConfirmed: 0, ",
                new="",
            ),
            Edit(
                needle="missingReason, suggestConfirmed, suggestRejected, uninitialized: false",
                kind="sub",
                old="suggestConfirmed, ",
                new="",
            ),
        ),
        expect_title="概览侧统计已确认 / 已驳回，且不伪造「待确认」",
        also=("概览未初始化循环的建议态计数为 0",),
        note="R6.6：建议态统计须在裁剪页与全项目概览双侧可见",
    ),
    # ── M5：模板调用改名（模拟「模板消费了不存在的标识符」）────────────────
    Mutation(
        "M5",
        TRIM_VUE,
        (
            # 🔴 `suggestionOf(row)` 全文 **4 命中**（模板 3 处 + 脚本注释 1 处），
            #    不能按裸子串算唯一；必须逐行钉（每行 needle 各自 hits == 1）。
            Edit(
                needle='<div v-if="suggestionOf(row)"',
                kind="sub",
                old="suggestionOf(row)",
                new="suggestionOfX(row)",
            ),
            Edit(
                needle=':content="suggestionOf(row)!.narrative"',
                kind="sub",
                old="suggestionOf(row)",
                new="suggestionOfX(row)",
            ),
            Edit(
                needle="reasonCodeLabel(suggestionOf(row)!.reasonCode)",
                kind="sub",
                old="suggestionOf(row)",
                new="suggestionOfX(row)",
            ),
        ),
        expect_title="模板里没有未声明的自由调用",
        note="本轮最贵的一类缺陷：模板消费零声明标识符，四层检查全绿、只有浏览器暴露",
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# 报告落盘（stdout 在本环境会被转义符污染吞掉）
# ═══════════════════════════════════════════════════════════════════════════
_LOG: list[str] = []


def log(*args: object) -> None:
    line = " ".join(str(a) for a in args)
    _LOG.append(line)
    _flush()


def _flush() -> None:
    REPORT.write_text("\n".join(_LOG) + "\n", encoding="utf-8")


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 施加 / 回退变异
# ═══════════════════════════════════════════════════════════════════════════
def _split(path: Path) -> tuple[list[str], str]:
    """读盘并按行切分，同时探明行尾（写回时原样恢复，不靠 open() 的换行翻译）。"""
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n").split("\n"), nl


def locate(path: Path, edits: tuple[Edit, ...]) -> list[tuple[str, int, list[int]]]:
    """逐 edit 报告命中行号（1-based）。不改文件。"""
    lines, _ = _split(path)
    out: list[tuple[str, int, list[int]]] = []
    for e in edits:
        hits = [i for i, ln in enumerate(lines) if e.needle in ln]
        out.append((e.needle, len(hits), [h + 1 for h in hits]))
    return out


def apply_mutation(mut: Mutation) -> list[str]:
    """施加变异；返回问题列表（空 = 成功）。"""
    lines, nl = _split(mut.path)
    problems: list[str] = []
    plan: list[tuple[int, Edit]] = []

    # 先一次性全部定位（先改后定位会让后续 needle 落在已变动的文本上）
    for e in mut.edits:
        hits = [i for i, ln in enumerate(lines) if e.needle in ln]
        if len(hits) != 1:
            problems.append(f"needle {e.needle!r} 命中 {len(hits)} 处（要求恰好 1）")
            continue
        idx = hits[0] + e.offset
        if not (0 <= idx < len(lines)):
            problems.append(f"needle {e.needle!r} + offset {e.offset} 越界")
            continue
        if e.kind == "sub" and e.old not in lines[idx]:
            problems.append(
                f"needle {e.needle!r} 命中行 L{idx + 1} 不含待替换串 {e.old!r}: {lines[idx].strip()!r}"
            )
            continue
        plan.append((idx, e))

    if problems:
        return problems

    # 降序施加：insert_after 会移动后续行号
    for idx, e in sorted(plan, key=lambda t: t[0], reverse=True):
        original = lines[idx]
        indent = original[: len(original) - len(original.lstrip())]
        if e.kind == "sub":
            lines[idx] = original.replace(e.old, e.new)
        elif e.kind == "replace_line":
            lines[idx] = indent + e.new.strip()
        elif e.kind == "insert_after":
            lines.insert(idx + 1, indent + e.new.strip())
        else:
            return [f"未知 edit.kind={e.kind!r}"]

    new_text = nl.join(lines)
    if new_text.encode("utf-8") == mut.path.read_bytes():
        return ["变异后文件字节未变（变异未真正施加，此时任何「测试仍绿」都无意义）"]
    mut.path.write_bytes(new_text.encode("utf-8"))
    return []


def _backup(paths: tuple[Path, ...]) -> None:
    for p in paths:
        p.with_suffix(p.suffix + ".bak").write_bytes(p.read_bytes())


def _restore(paths: tuple[Path, ...], drop_bak: bool = True) -> list[str]:
    restored: list[str] = []
    for p in paths:
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.exists():
            p.write_bytes(bak.read_bytes())
            if drop_bak:
                bak.unlink()
            restored.append(p.name)
    return restored


# ═══════════════════════════════════════════════════════════════════════════
# 跑守卫（读 JSON，不读 stdout）
# ═══════════════════════════════════════════════════════════════════════════
def run_guard() -> dict:
    out_abs = _FE / JSON_REL
    if out_abs.exists():
        out_abs.unlink()  # 🔴 不删会解析到陈旧结果
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        proc = subprocess.run(
            # 🔴 `--` 不可省，见模块 docstring
            ["npm.cmd", "exec", "--", "vitest", "run", SPEC_REL,
             "--reporter=json", f"--outputFile={JSON_REL}"],
            cwd=str(_FE),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "vitest 超时（900s）"}

    if not out_abs.exists():
        return {
            "ok": False,
            "reason": "vitest JSON 未生成",
            "rc": proc.returncode,
            "stderr": (proc.stderr or "")[-1500:],
        }
    try:
        d = json.loads(out_abs.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 解析失败本身就是要报告的事实
        return {"ok": False, "reason": f"JSON 解析失败: {exc}"}

    fails: set[str] = set()
    for res in d.get("testResults", []):
        for a in res.get("assertionResults", []):
            if a.get("status") == "failed":
                fails.add(a.get("fullName") or a.get("title") or "<unnamed>")
    suite_errors = [
        (res.get("name"), (res.get("message") or "").replace("\n", " ⏎ ")[:300])
        for res in d.get("testResults", [])
        if res.get("message")
    ]
    return {
        "ok": True,
        "rc": proc.returncode,
        "total": d.get("numTotalTests"),
        "passed": d.get("numPassedTests"),
        "failed": d.get("numFailedTests"),
        "suites": d.get("numTotalTestSuites"),
        "fails": fails,
        "suite_errors": suite_errors,
    }


def judge(base: dict, cur: dict, mut: Mutation) -> tuple[str, str, list[str]]:
    """四态判定。返回 (state, detail, 实际新增失败列表)。"""
    if not cur.get("ok"):
        return "SCRIPT-ERROR", str(cur.get("reason")) + " " + str(cur.get("stderr", "")), []

    new = sorted(cur["fails"] - base["fails"])
    resolved = sorted(base["fails"] - cur["fails"])

    if cur["suite_errors"]:
        return (
            "RED(collection-error)",
            f"suite 级失败: {cur['suite_errors']}",
            new,
        )
    if new:
        if any(mut.expect_title in f for f in new):
            return "RED(assertion)", f"新增打红 {len(new)} 条，含预期项", new
        return (
            "WRONG-TEST",
            f"新增打红 {len(new)} 条但不含预期项 {mut.expect_title!r}",
            new,
        )
    if resolved:
        return "RED(baseline-flip)", f"基线红转绿 {resolved}", new
    return "GREEN", "失败集合完全不变 ==> 守卫缺陷（该变异逃逸）", new


# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--anchors", action="store_true",
                    help="只核验锚点行级唯一性，不跑测试、不改文件")
    args = ap.parse_args()

    if args.restore:
        done = _restore(FILES)
        log(f"[restore] {done or '无 .bak 需要回退'}")
        return 0

    targets = [m for m in MUTATIONS if not args.only or m.mid in args.only]
    if not targets:
        log("没有匹配的变异 id")
        return 2

    log("=" * 78)
    log("Task 13 建议态接线守卫 — 变异检验")
    log(f"守卫: {SPEC_REL}")
    log(f"目标: {TRIM_VUE.name} / {DECISION_TS.name}")
    log("=" * 78)

    # ── 锚点唯一性核验（无论哪个模式都先做，ANCHOR-MISS 是脚本缺陷不是守卫缺陷）──
    anchor_report: dict[str, list[tuple[str, int, list[int]]]] = {}
    anchor_bad: list[str] = []
    log("")
    log("── 锚点行级唯一性 ──")
    for mut in targets:
        rows = locate(mut.path, mut.edits)
        anchor_report[mut.mid] = rows
        for needle, n, at in rows:
            flag = "OK " if n == 1 else "MISS"
            log(f"  [{flag}] {mut.mid} hits={n} at={at}  {needle!r}")
            if n != 1:
                anchor_bad.append(f"{mut.mid}:{needle!r}(hits={n})")
    if anchor_bad:
        log("")
        log(f"!! ANCHOR-MISS（脚本缺陷，不得当 GREEN）: {anchor_bad}")
    if args.anchors:
        return 1 if anchor_bad else 0

    md5_before = {p: _md5(p) for p in FILES}
    _backup(FILES)

    base = run_guard()
    log("")
    log("── 基线 ──")
    if not base.get("ok"):
        log(f"!! 基线跑不起来: {base}")
        _restore(FILES)
        return 2
    log(f"  total={base['total']} passed={base['passed']} failed={base['failed']} suites={base['suites']}")
    log(f"  基线失败集合: {sorted(base['fails']) or '空'}")
    if base["suite_errors"]:
        log(f"  !! 基线已有 suite 级错误: {base['suite_errors']}")

    results: list[dict] = []
    try:
        for mut in targets:
            log("")
            log(f"── {mut.mid} ──  {mut.note}")
            problems = apply_mutation(mut)
            if problems:
                results.append({
                    "mid": mut.mid,
                    "state": "ANCHOR-MISS",
                    "detail": "; ".join(problems),
                    "new": [],
                    "hits": [(n, c) for n, c, _ in anchor_report[mut.mid]],
                })
                log(f"  ANCHOR-MISS: {problems}")
                continue
            try:
                cur = run_guard()
                state, detail, new = judge(base, cur, mut)
            finally:
                # 🔴 无条件写回：判定过程抛异常也不能把变异留在工作树里
                bak = mut.path.with_suffix(mut.path.suffix + ".bak")
                mut.path.write_bytes(bak.read_bytes())
            results.append({
                "mid": mut.mid,
                "state": state,
                "detail": detail,
                "new": new,
                "hits": [(n, c) for n, c, _ in anchor_report[mut.mid]],
                "counts": f"total={cur.get('total')} passed={cur.get('passed')} failed={cur.get('failed')}",
            })
            log(f"  判定: {state}   {detail}")
            log(f"  计数: total={cur.get('total')} passed={cur.get('passed')} failed={cur.get('failed')}")
            for f in new:
                log(f"    FAILED: {f}")
    finally:
        _restore(FILES)

    md5_after = {p: _md5(p) for p in FILES}
    drift = [p.name for p in FILES if md5_before[p] != md5_after[p]]

    # ── 汇总表 ──────────────────────────────────────────────────────────────
    log("")
    log("=" * 78)
    log("汇总")
    log("=" * 78)
    log(f"{'编号':<5} {'锚点命中':<10} {'判定态':<22} 预期测试名")
    for mut in targets:
        r = next((x for x in results if x["mid"] == mut.mid), None)
        if r is None:
            continue
        hits = ",".join(str(c) for _, c in r["hits"])
        log(f"{mut.mid:<5} {hits:<10} {r['state']:<22} {mut.expect_title}")
        actual = r["new"] or ["(无新增失败)"]
        for a in actual:
            log(f"      实际失败: {a}")
        if mut.also:
            log(f"      预计连带: {list(mut.also)}")

    red = [r["mid"] for r in results if r["state"].startswith("RED")]
    green = [r["mid"] for r in results if r["state"] == "GREEN"]
    miss = [r["mid"] for r in results if r["state"] == "ANCHOR-MISS"]
    wrong = [r["mid"] for r in results if r["state"] == "WRONG-TEST"]
    err = [r["mid"] for r in results if r["state"] == "SCRIPT-ERROR"]

    log("")
    log(f"RED {len(red)}/{len(results)}  {red}")
    log(f"GREEN(守卫缺陷)     {green}")
    log(f"ANCHOR-MISS(脚本缺陷) {miss}")
    log(f"WRONG-TEST          {wrong}")
    log(f"SCRIPT-ERROR        {err}")
    for p in FILES:
        log(f"md5 {p.name}: before={md5_before[p]} after={md5_after[p]} "
            f"{'OK' if md5_before[p] == md5_after[p] else 'DRIFT!!'}")
    log(f"字节级还原核验: {'OK 全部一致' if not drift else 'FAILED 漂移 ' + str(drift)}")
    stray = [str(p.with_suffix(p.suffix + '.bak')) for p in FILES
             if p.with_suffix(p.suffix + ".bak").exists()]
    log(f".bak 残留: {stray or '无'}")

    ok = not drift and not green and not miss and not wrong and not err and len(red) == len(results)
    log("")
    log("结论: " + ("全部 RED，守卫承重有效" if ok else "存在未达标项，见上表"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        _flush()
    sys.exit(rc)
