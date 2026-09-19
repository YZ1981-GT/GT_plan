# -*- coding: utf-8 -*-
"""Task 14（完整性敏感清单项目级覆盖）守卫变异检验。

spec: procedure-trimming-and-delegation-intelligence — Task 14 / R5.5、R5.6、R5.7

用法（仓库根）：
    python backend/scripts/check/mutate_task14_cscope_guards.py            # 全量
    python backend/scripts/check/mutate_task14_cscope_guards.py --only M3
    python backend/scripts/check/mutate_task14_cscope_guards.py --restore  # 异常中断后还原

═══ 判定按「失败测试名集合求差集」，不看退出码 ═══

基线本身可能有红（工作树并发度高），只看退出码会把 ANCHOR-MISS / WRONG-TEST 误判成 RED。
四态显式区分：

- ``RED``         : `new_fails` 非空且与预期项相交 ⇒ 守卫承重
- ``WRONG-TEST``  : `new_fails` 非空但与预期项无交集 ⇒ 打红的不是该判据（锚点错行 / 污染残留）
- ``GREEN``       : `new_fails` 为空 ⇒ **守卫缺陷**（不是「代码没问题」）
- ``ANCHOR-MISS`` : 锚点未命中或命中 >1 ⇒ 脚本缺陷，变异根本没施加，此时"仍绿"无任何意义

🔴 锚点一律**行级**（`splitlines()` + 行内 needle + `hits == 1` + 相对 `offset`）：
   本工作树是 CRLF，任何含 `\\n` 的跨行字面量必 MISS。
🔴 变异后断言字节**确实变了**；`try/finally` 无条件写回；还原后 md5 双向核验。
🔴 报告落盘再读 —— 本环境 python stdout 会被终端转义符污染吞掉。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]  # 仓库根
FE = ROOT / "audit-platform" / "frontend"

P_VUE = ROOT / "audit-platform/frontend/src/views/ProcedureTrimming.vue"
P_SVC = ROOT / "backend/app/services/procedure_trim_service.py"
P_CTX = ROOT / "backend/app/services/trim_decision_context.py"
P_READER = ROOT / "backend/app/services/b50_risk_reader.py"
P_ROUTER = ROOT / "backend/app/routers/procedure_trim.py"

BE_TESTS = [
    "backend/tests/procedure_trim/test_completeness_scope_override.py",
    "backend/tests/procedure_trim/test_b50_reader_extension.py",
]
FE_TEST = "src/views/__tests__/completenessScopeOverride.spec.ts"
FE_JSON = FE / "tmp_mutate_task14.json"
REPORT = ROOT / "tmp_mutate_task14_report.txt"


# ═══════════════════════════════════════════════════════════════════════════
# 变异定义
#
# kind:
#   replace     —— 把命中行里的 `old` 换成 `new`（行内唯一）
#   insert_after—— 在命中行之后插入 `new`（保持命中行原样）
#   drop_line   —— 删掉命中行
# ═══════════════════════════════════════════════════════════════════════════
MUTATIONS: list[dict] = [
    # ── 前端：渲染宿主（本轮实证缺陷的直接还原）────────────────────────────
    dict(
        id="M1", suite="fe", file=P_VUE,
        desc="面板 el-dialog 的 v-model 改绑别的 ref（宿主形同不存在）",
        anchor='v-model="completenessPanelVisible"', offset=0, kind="replace",
        old='v-model="completenessPanelVisible"', new='v-model="showOverviewDrawer"',
        expect=["completenessPanelVisible 被模板真实消费", "面板是真正的 el-dialog"],
    ),
    dict(
        id="M2", suite="fe", file=P_VUE,
        desc="面板表格不再遍历 completenessScopeRows（逐循环行消失）",
        anchor=':data="completenessScopeRows"', offset=0, kind="replace",
        old=':data="completenessScopeRows"', new=':data="[]"',
        expect=["completenessScopeRows 被模板真实消费", "面板渲染逐循环行"],
    ),
    dict(
        id="M3", suite="fe", file=P_VUE,
        desc="只给「设为敏感」一个方向（Y/N 双向表态退化成半个功能）",
        anchor='@click="setCompletenessScope(row, false)"', offset=0, kind="replace",
        old="setCompletenessScope(row, false)", new="setCompletenessScope(row, true)",
        expect=["两个写入动作在模板上都有触发点"],
    ),
    # ── 前端：未知态 / 单一真源 / 理由必填 / 双刷新 ───────────────────────
    dict(
        id="M4", suite="fe", file=P_VUE,
        desc="读取失败退化成空数组（把技术故障谎报成「全部平台默认」）",
        anchor="completenessOverrides.value = null", offset=0, kind="replace",
        old="completenessOverrides.value = null", new="completenessOverrides.value = []",
        expect=["catch 分支把值设回 null 且不写空数组"],
    ),
    dict(
        id="M5", suite="fe", file=P_VUE,
        desc="usingPlatformDefault 改为视图自算（第二份判据真源）",
        anchor="usingPlatformDefault: resolved.usingPlatformDefault,", offset=0, kind="replace",
        old="usingPlatformDefault: resolved.usingPlatformDefault,",
        new="usingPlatformDefault: (completenessOverrides.value ?? []).length === 0,",
        expect=["结论 / 来源 / 标注三项全取纯函数输出"],
    ),
    dict(
        id="M6", suite="fe", file=P_VUE,
        desc="写入后只刷面板不刷判据上下文（面板说已确认、判据仍按平台默认）",
        # 🔴 不能直接拿 `await loadTrimContext([activeCycle.value])` 当锚点 —— 它全文
        #    **6 处命中**（Task 13 接线留下的调用点）。改锚唯一的写入调用行 + 相对偏移。
        anchor="    await saveCompletenessScopeOverride(projectId.value, row.cycle, sensitive, reason)",
        offset=5, kind="drop_line",
        expect=["写入与撤销都同时刷新面板列表与判据上下文"],
    ),
    dict(
        id="M7", suite="fe", file=P_VUE,
        desc="去掉发请求前的独立空理由判断（只剩弹窗校验，程序化调用可绕过）",
        anchor="if (!reason) {", offset=0, kind="replace",
        old="if (!reason) {", new="if (false) {",
        expect=["发请求前有独立的空理由早退"],
    ),
    # ── 后端：前缀单一真源 / 读写交叉锁死 ──────────────────────────────────
    dict(
        id="M8", suite="be", file=P_SVC,
        desc="写入侧另写一份前缀字面量（不再 import 读取侧常量）",
        anchor="    COMPLETENESS_SCOPE_ITEM_PREFIX as _CSCOPE_ITEM_PREFIX,", offset=0,
        kind="replace",
        old="    COMPLETENESS_SCOPE_ITEM_PREFIX as _CSCOPE_ITEM_PREFIX,",
        # 变异体仍是**合法 Python**（保留一个真实 import + 自造字面量），否则会以
        # collection error 而不是断言失败的形态打红 —— 那是第五种结果，不算 RED。
        new=(
            "    DIM_COMPLETENESS_OVERRIDE as _unused_dim,\n"
            ")\n"
            '_CSCOPE_ITEM_PREFIX = "B50-T3-cscope-"\n'
            "from app.services.trim_decision_context import (  # noqa: E402\n"
            "    DIM_COMPLETENESS_OVERRIDE as _unused_dim2,"
        ),
        expect=["test_write_side_imports_prefix_and_has_no_second_literal"],
    ),
    dict(
        id="M9", suite="be", file=P_CTX,
        desc="读取侧 LIKE 模式与常量漂移（写得进读不出）",
        anchor="\"WHERE wp_id = :wp AND item_id LIKE 'B50-T3-cscope-%'\"", offset=0,
        kind="replace",
        old="LIKE 'B50-T3-cscope-%'", new="LIKE 'B50-T3-cscope%'",
        expect=["test_read_side_sql_pattern_is_cross_locked_to_constant"],
    ),
    # ── 后端：理由必填 / 撤销语义 / 键空间零污染 / 端点守卫 / 形参契约 ─────
    dict(
        id="M10", suite="be", file=P_SVC,
        desc="空理由不再拒绝（无理由的覆盖直接落库）",
        anchor="        if not text_reason:", offset=0, kind="replace",
        old="if not text_reason:", new="if False:",
        expect=["test_blank_reason_is_rejected_before_any_write"],
    ),
    dict(
        id="M11", suite="be", file=P_SVC,
        desc="撤销改成写空 conclusion 而不是删行（留一条既非表态也非缺失的脏记录）",
        anchor='                "DELETE FROM checklist_responses "', offset=0, kind="replace",
        old='"DELETE FROM checklist_responses "',
        new='"UPDATE checklist_responses SET conclusion = \'\' "',
        expect=["test_clear_deletes_row_and_never_writes_blank"],
    ),
    dict(
        id="M12", suite="be", file=P_READER,
        desc="reader 把 cscope 行也当科目建项（污染 load_b50_accounts 输出）",
        anchor='        if item_id.startswith("B50-T3-plan-"):', offset=0, kind="insert_before",
        new=(
            '        if item_id.startswith("B50-T3-cscope-"):\n'
            '            _ensure(item_id.removeprefix("B50-T3-cscope-"))\n'
            "            continue"
        ),
        expect=[
            "test_cscope_rows_do_not_change_frozen_legacy_output",
            "test_cscope_only_rows_produce_no_accounts",
        ],
    ),
    dict(
        id="M13", suite="be", file=P_ROUTER,
        desc="PUT 端点摘掉项目级 Delegator 守卫（越权写入口）",
        # 🔴 `_guard: ... Depends(require_project_delegator_pid),` 全文 9 处**完全相同**，
        #    只能锚唯一的 body 标注行 + 相对偏移；按 nth 数会随端点增删而错位。
        anchor="    body: CompletenessScopeOverrideRequest,", offset=3, kind="replace",
        old="    _guard: DelegatorContext = Depends(require_project_delegator_pid),",
        new="    # mutated: guard removed",
        expect=["test_all_three_have_delegator_guard"],
    ),
    dict(
        id="M14", suite="be", file=P_ROUTER,
        desc="router 用不存在的形参名调 service（运行时 TypeError → 500）",
        # `reason=body.reason,` 全文 4 处 ⇒ 锚唯一的调用起始行 + 相对偏移
        anchor="        result = await svc.set_completeness_scope_override(", offset=5,
        kind="replace",
        old="reason=body.reason,", new="reason_text=body.reason,",
        expect=["test_every_kwarg_exists_on_service_method"],
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# 施加 / 还原
# ═══════════════════════════════════════════════════════════════════════════
def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _apply(m: dict) -> tuple[bool, str]:
    """返回 (是否成功施加, 说明)。行级锚点，hits 必须恰为 1（`replace_nth` 例外）。"""
    p: Path = m["file"]
    raw = p.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    needle = m["anchor"].rstrip("\n")
    hits = [i for i, ln in enumerate(lines) if needle in ln]

    kind = m["kind"]
    if kind == "replace_nth":
        n = m["nth"]
        if len(hits) < n:
            return False, f"ANCHOR-MISS: 锚点命中 {len(hits)} 行，不足 nth={n}"
        idx = hits[n - 1]
    else:
        if len(hits) != 1:
            return False, f"ANCHOR-MISS: 锚点命中 {len(hits)} 行（要求恰 1）"
        idx = hits[0]

    tgt = idx + m.get("offset", 0)
    if not (0 <= tgt < len(lines)):
        return False, f"ANCHOR-MISS: offset 越界 (idx={idx}, offset={m.get('offset', 0)})"

    if kind == "drop_line":
        lines[tgt] = ""
    elif kind == "insert_before":
        lines[tgt] = m["new"].rstrip("\n") + "\n" + lines[tgt]
    elif kind in ("replace", "replace_nth"):
        old, new = m["old"], m["new"]
        if old not in lines[tgt]:
            return False, f"ANCHOR-MISS: 目标行不含 old（行内容: {lines[tgt][:120]!r}）"
        if lines[tgt].count(old) != 1:
            return False, f"ANCHOR-MISS: old 在该行出现 {lines[tgt].count(old)} 次"
        lines[tgt] = lines[tgt].replace(old, new)
    else:
        return False, f"未知 kind: {kind}"

    out = "".join(lines)
    if out == raw:
        return False, "NO-OP: 变异后字节未变（此时「测试仍绿」无任何意义）"
    p.write_text(out, encoding="utf-8", newline="")
    return True, "applied"


# ═══════════════════════════════════════════════════════════════════════════
# 跑测试 → 失败测试名集合
# ═══════════════════════════════════════════════════════════════════════════
def _run_be() -> tuple[set[str], str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *BE_TESTS, "-q", "--tb=no", "-rf", "-p", "no:cacheprovider"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    fails = set()
    for ln in (r.stdout or "").splitlines():
        s = ln.strip()
        if s.startswith("FAILED ") or s.startswith("ERROR "):
            fails.add(s.split(" ", 1)[1].split(" - ")[0].strip())
    tail = "\n".join((r.stdout or "").splitlines()[-4:])
    return fails, tail


def _run_fe() -> tuple[set[str], str]:
    if FE_JSON.exists():
        FE_JSON.unlink()
    # 跨平台：Windows 的 npx 实为 npx.cmd（须经 cmd /c），POSIX 上 shell=True + 列表参数
    #  只会执行 npx 本身、不带任何参数 ⇒ JSON 不生成 ⇒ NO-JSON（Task 24 实证）。
    _npx = ["cmd", "/c", "npx"] if os.name == "nt" else ["npx"]
    r = subprocess.run(
        [*_npx, "vitest", "run", FE_TEST, "--reporter=json", "--outputFile", FE_JSON.name],
        cwd=str(FE), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if not FE_JSON.exists():
        return {"<JSON-MISSING>"}, f"vitest 未产出 JSON (exit={r.returncode})"
    d = json.loads(FE_JSON.read_text(encoding="utf-8"))
    fails = {
        a["fullName"] for f in d["testResults"] for a in f["assertionResults"]
        if a["status"] != "passed"
    }
    tail = f"total={d['numTotalTests']} passed={d['numPassedTests']} failed={d['numFailedTests']}"
    return fails, tail


def _run(suite: str) -> tuple[set[str], str]:
    return _run_be() if suite == "be" else _run_fe()


def _restore_all() -> list[str]:
    out = []
    for p in {m["file"] for m in MUTATIONS}:
        bak = Path(str(p) + ".bak")
        if bak.exists():
            shutil.copy2(bak, p)
            bak.unlink()
            out.append(f"restored {p.name}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只跑指定变异（逗号分隔，如 M3,M9）")
    ap.add_argument("--restore", action="store_true", help="仅从 .bak 还原后退出")
    args = ap.parse_args()

    log: list[str] = []

    def say(s: str) -> None:
        log.append(s)

    if args.restore:
        for line in _restore_all():
            say(line)
        REPORT.write_text("\n".join(log) or "无 .bak 可还原", encoding="utf-8")
        return 0

    picked = MUTATIONS
    if args.only:
        want = {x.strip() for x in args.only.split(",")}
        picked = [m for m in MUTATIONS if m["id"] in want]

    files = {m["file"] for m in picked}
    md5_before = {p: _md5(p) for p in files}
    for p in files:
        shutil.copy2(p, str(p) + ".bak")

    say("═══ 基线 ═══")
    baselines: dict[str, set[str]] = {}
    for suite in sorted({m["suite"] for m in picked}):
        fails, tail = _run(suite)
        baselines[suite] = fails
        say(f"[{suite}] {tail}")
        say(f"[{suite}] baseline failed = {len(fails)}")
        for f in sorted(fails):
            say(f"    - {f}")

    results: list[tuple[str, str, str]] = []
    try:
        for m in picked:
            say("")
            say(f"═══ {m['id']} · {m['desc']} ═══")
            ok, why = _apply(m)
            if not ok:
                say(f"  {why}")
                results.append((m["id"], why.split(":")[0], m["desc"]))
                shutil.copy2(str(m["file"]) + ".bak", m["file"])
                continue
            fails, tail = _run(m["suite"])
            base = baselines[m["suite"]]
            new_fails = fails - base
            healed = base - fails
            say(f"  {tail}")
            say(f"  new_fails={len(new_fails)} healed={len(healed)}")
            for f in sorted(new_fails):
                say(f"    + {f}")
            if not new_fails:
                verdict = "GREEN(守卫缺陷)"
            elif any(any(e in f for f in new_fails) for e in m["expect"]):
                verdict = "RED"
            else:
                verdict = "WRONG-TEST"
            say(f"  → {verdict}（预期项: {m['expect']}）")
            results.append((m["id"], verdict, m["desc"]))
            shutil.copy2(str(m["file"]) + ".bak", m["file"])
    finally:
        # 🔴 无条件写回 + md5 核验（被 Ctrl+C 打断时变异体不得留在工作树）
        for p in files:
            bak = Path(str(p) + ".bak")
            if bak.exists():
                shutil.copy2(bak, p)
                bak.unlink()
        say("")
        say("═══ 还原核验（md5 before == after）═══")
        for p in files:
            after = _md5(p)
            same = after == md5_before[p]
            say(f"  {'OK ' if same else 'BAD'} {p.name} {md5_before[p]} → {after}")
        if FE_JSON.exists():
            FE_JSON.unlink()

    say("")
    say("═══ 汇总 ═══")
    for mid, verdict, desc in results:
        say(f"  {mid:4s} {verdict:16s} {desc}")
    bad = [r for r in results if r[1] != "RED"]
    say("")
    say(f"RED {len(results) - len(bad)}/{len(results)}" + ("" if not bad else "  ⚠️ 存在非 RED 项"))
    REPORT.write_text("\n".join(log), encoding="utf-8")
    return 0 if not bad else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
