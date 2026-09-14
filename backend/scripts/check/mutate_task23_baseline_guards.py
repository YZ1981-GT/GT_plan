"""Task 23 变异检验：回收后的 7 条到期冻结基线 + 两处新增零回归判据是否仍承重。

spec: procedure-trimming-and-delegation-intelligence — Task 23

## 为什么必须做这一轮

Task 22 把 7 条「改造前基线」移交 Task 23 回收。改写这类断言最大的风险不是写错方向，
而是**改成恒真** —— 断言还在、名字还在、测试全绿，但对应缺陷再出现时不会打红。
故每条回收后的基线都要有一个**只有它能挡住**的变异，逐条验证「改一字必变红」。

## 判定：按失败测试名集合求差集，跨前后端归一，不看退出码

12 条变异跨前后端：改 `.py` 的可能同时打红 pytest 与 vitest（前端守卫读后端 py 源码做
交叉锁死），改 `.vue` / `.ts` 只影响 vitest。故每条变异声明 `sides`，判定时把两侧失败
测试名归一到同一集合（``py::`` / ``ts::`` 前缀）后求差集。

只跑单侧会让另一侧的变异恒显「失败集合不变」，从而把**有效变异误判成守卫缺陷**
（Task 22 已登记过这条）。

## 五态（缺一态就会把脚本缺陷当成结论）

- ``RED``           新增失败非空**且**包含预期测试名特征 ⇒ 变异有效、判据承重
- ``WRONG-TEST``    新增失败非空但不含预期特征 ⇒ 污染残留或锚点打偏（**不能算 RED**）
- ``GREEN``         新增失败为空 ⇒ **守卫缺陷**（判据没抓到这个缺陷）
- ``ANCHOR-MISS``   锚点行命中数 != 1，或变异后字节未变 ⇒ **脚本缺陷**，此时"测试仍绿"
                    不能作任何结论
- ``COLLECT-ERROR`` 整文件零断言执行 / vitest JSON 未生成 ⇒ 同样不是 RED 也不是 GREEN

## 三条工程约束（都是本 spec 历轮踩出来的）

1. **锚点行级唯一**：`splitlines()` + needle 行内匹配 + `hits == 1` + 相对 `offset`。
   禁含 ``\\n`` 的跨行字面量 —— 本工作树 CRLF，跨行锚点必 MISS。
2. **`npm exec` 传 flag 必须加 ``--`` 分隔符**，否则 npm 把 ``--reporter`` 当自己的
   cli config ⇒ **JSON 不生成而退出码仍 0** ⇒ 差集恒空、全判 GREEN。跑前删旧 JSON。
3. **`.bak` + `try/finally` 无条件写回 + md5 字节级核验**。已存在 `.bak` 的文件拒绝启动
   （那可能是**别的会话**变异脚本的活体备份，覆盖它会让它的 `--restore` 失败并把变异体
   留在工作树）。

用法::

    python backend/scripts/check/mutate_task23_baseline_guards.py            # 全部
    python backend/scripts/check/mutate_task23_baseline_guards.py --only T23-4
    python backend/scripts/check/mutate_task23_baseline_guards.py --restore  # 应急还原
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
_BACKEND = _REPO / "backend"
_FE = _REPO / "audit-platform" / "frontend"
_FE_SRC = _FE / "src"
_CMP = _FE_SRC / "components" / "workpaper" / "composables"

# ── 被变异的生产文件 ──
TRIM_ENGINE = _BACKEND / "app" / "services" / "procedure_trim_engine.py"
TRIM_SERVICE = _BACKEND / "app" / "services" / "procedure_trim_service.py"
DELEG_SERVICE = _BACKEND / "app" / "services" / "procedure_delegation_service.py"
PROC_SERVICE = _BACKEND / "app" / "services" / "procedure_service.py"
TRIM_VUE = _FE_SRC / "views" / "ProcedureTrimming.vue"
DECISION_TS = _CMP / "procedureTrimDecision.ts"
REASON_MIRROR = _CMP / "trimReasonCodes.ts"

PYTEST_TARGET = "backend/tests/procedure_trim/"
VITEST_TARGETS: tuple[str, ...] = (
    "src/components/workpaper/composables/__tests__/procedureTrimDecision.spec.ts",
    "src/components/workpaper/composables/__tests__/procedureTrimDecision.behavior.spec.ts",
    "src/components/workpaper/composables/__tests__/trimNoDataZeroRegression.spec.ts",
    "src/components/workpaper/composables/__tests__/trimReasonCodes.spec.ts",
    "src/components/workpaper/composables/__tests__/trimAggregateGate.spec.ts",
    "src/components/workpaper/composables/__tests__/completenessExemption.spec.ts",
)
_VITEST_JSON = _FE / "tmp_t23_mutate_vitest.json"
_REPORT = _REPO / "tmp_t23_mutate_report.txt"


@dataclass
class Mutation:
    mid: str
    what: str
    target: Path
    anchor: str
    """锚点行必须**行级唯一**（hits == 1）。"""
    offset: int = 0
    """相对锚点行的偏移；被替换的是 `锚点行号 + offset` 那一行。"""
    old: str = ""
    new: str = ""
    """在目标行内做 `old` → `new` 的替换（`old` 为空则整行替换为 `new`）。"""
    sides: tuple[str, ...] = ("py", "ts")
    expect: tuple[str, ...] = ()
    """期望打红的测试名特征（子串），至少命中一条才算 RED。"""
    note: str = ""


MUTATIONS: tuple[Mutation, ...] = (
    # ── 回收基线 1：TrimReasonCode 取值域快照（原「当前恰为这 4 值」）──
    Mutation(
        mid="T23-1",
        what="删掉 Task 12 新增的 BELOW_MATERIALITY 取值（新增值未登记 / 被回退）",
        target=TRIM_ENGINE,
        anchor='BELOW_MATERIALITY = "below_materiality"',
        old='BELOW_MATERIALITY = "below_materiality"',
        new='_REMOVED_BELOW_MATERIALITY = "x_removed"',
        expect=("落地后取值域", "前后端交叉锁死", "mirror_values_equal_backend_enum",
                "test_new_codes_present", "test_no_unexpected_values"),
        note="回收后的基线若写成「⊇ 既有 4 值」而不冻结全集，本变异会恒绿",
    ),
    # ── 回收基线 1 的反向半边：既有 4 值不得丢 ──
    Mutation(
        mid="T23-2",
        what="删掉既有取值 NO_RELATED_BUSINESS（additive 扩展偷偷删了既有值）",
        target=TRIM_ENGINE,
        anchor='NO_RELATED_BUSINESS = "no_related_business"',
        old='NO_RELATED_BUSINESS = "no_related_business"',
        new='_REMOVED_NO_RELATED = "x_removed"',
        expect=("现有 4 个取值在扩展后必须仍在", "M5 真实 procedure_trim_engine",
                "test_legacy_codes_preserved", "前后端交叉锁死"),
    ),
    # ── 回收基线 2：canonical scope entry 的 reason_code 为**条件**写入 ──
    Mutation(
        mid="T23-3",
        what="把 reason_code 无条件写进 normalized dict 字面量（破 R8.9 additive 零回归）",
        target=TRIM_SERVICE,
        anchor='"target_status": target_status,',
        offset=0,
        old='"target_status": target_status,',
        new='"target_status": target_status, "reason_code": reason_code or None,',
        expect=("entry 支持 reason_code，且为条件写入",
                "test_real_normalize_entry_payload_unchanged_without_reason_code",
                "criterion_b_independent_recompute"),
        note="存量 payload 多一键 ⇒ hash 全变 ⇒ 在途 preview 凭证全部 409",
    ),
    # ── 回收基线 3：智能裁剪真读科目金额 ──
    Mutation(
        mid="T23-4",
        what="buildAndDecide 退回「丢弃 amount」形态（金额恒 null，重要性维度静默失效）",
        target=TRIM_VUE,
        anchor="? Number((ctx.accounts as any)[accountName]?.amount)",
        old="? Number((ctx.accounts as any)[accountName]?.amount)",
        new="? null",
        sides=("ts",),
        expect=("金额被真读并传入决策内核", "M3 真实 buildAndDecide",
                "M4 「剥类型声明」这一步不得过宽"),
    ),
    # ── 回收基线 4：扫描面锚定在 buildAndDecide ──
    Mutation(
        mid="T23-5",
        what="改名 buildAndDecide（扫描面失锚，判据应显式报「未截到函数体」而非空转）",
        target=TRIM_VUE,
        anchor="function buildAndDecide(",
        old="function buildAndDecide(",
        new="function buildAndDecideRenamed(",
        sides=("ts",),
        expect=("扫描面非空自检：截到 buildAndDecide 函数体", "金额被真读并传入决策内核",
                "M3 真实 buildAndDecide", "buildAndDecide` 如实硬传 false"),
        note="模板/脚本其余引用会一并断掉 —— 本变异同时验证「失锚必红」而不是恒绿",
    ),
    # ── 回收基线 5：粗裁既有理由码**且**存量自由文本仍在 ──
    Mutation(
        mid="T23-6",
        what="删掉自由文本理由常量 COMMON_SKIP_REASONS（破 R8.4 存量可读）",
        target=TRIM_VUE,
        anchor="const COMMON_SKIP_REASONS = [",
        old="const COMMON_SKIP_REASONS = [",
        new="const RENAMED_SKIP_REASONS = [",
        sides=("ts",),
        expect=("裁剪页既有结构化理由码，也保留自由文本理由",),
        note="只断言「有理由码」的判据会让这种改法悄悄通过",
    ),
    # ── 回收基线 6：confirmSmartTrim 不得自带第二份判据 ──
    Mutation(
        mid="T23-7",
        what="confirmSmartTrim 内联第二份金额取数（第二判据真源，改造前正是此形态）",
        target=TRIM_VUE,
        anchor="const cycleList = Array.from(targetCycles)",
        old="const cycleList = Array.from(targetCycles)",
        new=("const cycleList = Array.from(targetCycles)\n"
             "  const _inlinedAmount = (trimContext.value as any)?.accounts?.['x']?.amount"),
        sides=("ts",),
        expect=("confirmSmartTrim 不再自带第二份判据",),
    ),
    # ── 回收基线 7（M4 的承重方向）：剥类型声明这一步不得过宽 ──
    Mutation(
        mid="T23-8",
        what="把取金额那一行伪装成类型字面量形态（复现「过滤过宽吞掉真实取值行」）",
        target=TRIM_VUE,
        anchor="? Number((ctx.accounts as any)[accountName]?.amount)",
        old="? Number((ctx.accounts as any)[accountName]?.amount)",
        new="? Number(((ctx.accounts as any) as { amount: number })[accountName]?.amount)",
        sides=("ts",),
        expect=("M4 「剥类型声明」这一步不得过宽", "金额被真读并传入决策内核",
                "M3 真实 buildAndDecide"),
        note="过滤器把该行当类型注解剥掉 ⇒ scanned 里再无 `?.amount` ⇒ M4 必红",
    ),
    # ── 新增判据 (a)：no_data 集合等价 ──
    Mutation(
        mid="T23-9",
        what="决策内核档 4 去掉循环级兜底（未覆盖科目一律不再自动裁 ⇒ 漏裁）",
        target=DECISION_TS,
        anchor="const cycleNoData = input.subjectDataState === 'unknown' && input.cycleHasData === false",
        old="input.subjectDataState === 'unknown' && input.cycleHasData === false",
        new="false",
        sides=("ts",),
        expect=("新增维度中性化时，两侧集合逐格相同",),
        note="R14.2 的正面判据：改造前的循环级兜底裁剪不得缩水",
    ),
    Mutation(
        mid="T23-10",
        what="buildAndDecide 把 subjectNoData 排在 subjectWithData 之前（矛盾输入下多裁）",
        target=TRIM_VUE,
        anchor="const subjectDataState: SubjectDataState = subjectWithData.has(prefix)",
        old="subjectWithData.has(prefix)",
        new="subjectNoData.has(prefix)",
        sides=("ts",),
        expect=("`subjectDataState` 映射优先级为 with_data > no_data > unknown",),
        note="改造前 subjectWithData 先判；掉换后「有数据的科目」会被判 no_data 并自动裁",
    ),
    # ── 新增判据 (c)：委派对外契约字段 ──
    Mutation(
        mid="T23-11",
        what="委派 preview.summary 删掉 already_assigned 字段（破 R14.1 对外契约）",
        target=DELEG_SERVICE,
        anchor='"already_assigned": already_assigned,',
        old='"already_assigned": already_assigned,',
        new="",
        sides=("py",),
        expect=("test_preview_nested_keys_frozen", "test_head_side_keys_equal_worktree"),
    ),
    # ── 新增判据 (a) 的不可达前提 ──
    Mutation(
        mid="T23-12",
        what="_to_dict 下发 is_mandatory（让 no_data 等价论证的「唯一分歧不可达」前提失效）",
        target=PROC_SERVICE,
        anchor='"wp_code": p.wp_code,',
        old='"wp_code": p.wp_code,',
        new='"wp_code": p.wp_code, "is_mandatory": False,',
        sides=("py",),
        expect=("test_to_dict_does_not_emit_is_mandatory",),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# 运行两侧测试并抽失败测试名
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class RunResult:
    fails: set[str] = field(default_factory=set)
    collect_errors: list[str] = field(default_factory=list)
    total: int = 0
    fatal: str | None = None
    summary: str = ""


def _env() -> dict:
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _run_pytest() -> RunResult:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", PYTEST_TARGET, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(_REPO), capture_output=True, encoding="utf-8",
        errors="replace", env=_env(),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    res = RunResult()
    res.fails = {f"py::{n}" for n in re.findall(r"^FAILED\s+(\S+)", out, re.M)}
    res.collect_errors = [f"py::{n}" for n in re.findall(r"^ERROR\s+(\S+)", out, re.M)]
    m = re.search(r"(\d+) failed", out)
    n_failed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) passed", out)
    res.total = (int(m.group(1)) if m else 0) + n_failed
    if n_failed != len(res.fails):
        res.fails.add(f"py::<unparsed:{n_failed}!={len(res.fails)}>")
    if res.total == 0:
        res.fatal = "pytest 零测试执行（COLLECT-ERROR）"
    res.summary = f"py total={res.total} failed={n_failed}"
    return res


def _run_vitest() -> RunResult:
    res = RunResult()
    if _VITEST_JSON.exists():
        _VITEST_JSON.unlink()
    # 跨平台：Windows 的 npm 实为 npm.cmd（须经 cmd /c），而 ubuntu-latest 无 cmd。
    #  写死 cmd /c 会让本脚本在 CI 上必然 NO-JSON ⇒ 基线 fatal ⇒ job 恒红（Task 24 实证）。
    _npm = ["cmd", "/c", "npm"] if os.name == "nt" else ["npm"]
    cmd = [*_npm, "exec", "--", "vitest", "run",
           "--reporter=json", f"--outputFile={_VITEST_JSON.name}", *VITEST_TARGETS]
    subprocess.run(cmd, cwd=str(_FE), capture_output=True,
                   encoding="utf-8", errors="replace", env=_env())
    if not _VITEST_JSON.exists():
        res.fatal = "vitest JSON 未生成（NO-JSON）"
        return res
    try:
        data = json.loads(_VITEST_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        res.fatal = f"vitest JSON 不可解析: {exc!r}"
        return res
    files = data.get("testResults") or []
    for tr in files:
        name = Path(str(tr.get("name") or "")).name
        ars = tr.get("assertionResults") or []
        if not ars:
            res.collect_errors.append(f"ts::{name}::<零断言执行>")
            continue
        for a in ars:
            if a.get("status") == "failed":
                res.fails.add(f"ts::{name}::{a.get('fullName')}")
    res.total = int(data.get("numTotalTests") or 0)
    n_failed = int(data.get("numFailedTests") or 0)
    if res.total == 0:
        res.fatal = "vitest 零测试执行"
    if n_failed != len(res.fails):
        res.fails.add(f"ts::<unparsed:{n_failed}!={len(res.fails)}>")
    res.summary = f"ts total={res.total} failed={n_failed} files={len(files)}"
    if len(files) != len(VITEST_TARGETS):
        res.summary += f" 🔴files!={len(VITEST_TARGETS)}"
    return res


def _run(sides: tuple[str, ...]) -> RunResult:
    merged = RunResult()
    parts: list[str] = []
    for side in sides:
        r = _run_pytest() if side == "py" else _run_vitest()
        merged.fails |= r.fails
        merged.collect_errors += r.collect_errors
        merged.total += r.total
        if r.fatal:
            merged.fatal = f"{merged.fatal or ''} | {side}: {r.fatal}".strip(" |")
        parts.append(r.summary)
    merged.summary = "  ".join(parts)
    return merged


# ═══════════════════════════════════════════════════════════════════════════
# 施加 / 还原变异
# ═══════════════════════════════════════════════════════════════════════════
def _snap(p: Path) -> Path:
    return p.with_suffix(p.suffix + ".t23bak")


_OWNED = tuple({m.target for m in MUTATIONS})


def _preflight() -> list[str]:
    """启动前检查：owned 文件不得已存在快照（那说明上一轮没还原干净）。"""
    bad: list[str] = []
    for p in _OWNED:
        if not p.exists():
            bad.append(f"目标文件不存在: {p}")
        if _snap(p).exists():
            bad.append(f"已存在快照 {_snap(p).name} —— 上一轮未还原干净，拒绝启动")
        if p.with_suffix(p.suffix + ".bak").exists():
            bad.append(
                f"存在他人活体备份 {p.name}.bak —— 本脚本不动它，但请确认无变异残留"
            )
    return bad


def _apply(mut: Mutation) -> str | None:
    """施加变异；返回 None = 成功，否则返回 ANCHOR-MISS 原因。"""
    p = mut.target
    raw = p.read_text(encoding="utf-8")
    _snap(p).write_bytes(p.read_bytes())
    lines = raw.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if mut.anchor in ln]
    if len(hits) != 1:
        return f"ANCHOR-MISS: 锚点行命中 {len(hits)} 次（要求恰 1）: {mut.anchor[:70]!r}"
    idx = hits[0] + mut.offset
    if not (0 <= idx < len(lines)):
        return f"ANCHOR-MISS: offset 越界 idx={idx} len={len(lines)}"
    target_line = lines[idx]
    eol = "\r\n" if target_line.endswith("\r\n") else ("\n" if target_line.endswith("\n") else "")
    body = target_line[: len(target_line) - len(eol)]
    if mut.old:
        if mut.old not in body:
            return f"ANCHOR-MISS: 目标行内未见 old 片段: {mut.old[:70]!r} / 行={body[:90]!r}"
        if body.count(mut.old) != 1:
            return f"ANCHOR-MISS: 目标行内 old 出现 {body.count(mut.old)} 次"
        new_body = body.replace(mut.old, mut.new)
    else:
        new_body = mut.new
    # 变异体可能是多行（用 \n 书写，写盘时统一成目标行的行尾）
    new_line = eol.join(new_body.split("\n")) + eol if eol else new_body
    lines[idx] = new_line
    p.write_text("".join(lines), encoding="utf-8", newline="")
    if p.read_text(encoding="utf-8") == raw:
        return "ANCHOR-MISS: 变异后字节未变（此时「测试仍绿」不能作任何结论）"
    return None


def _restore_all() -> list[str]:
    msgs: list[str] = []
    for p in _OWNED:
        s = _snap(p)
        if s.exists():
            p.write_bytes(s.read_bytes())
            s.unlink()
            msgs.append(f"restored {p.name}")
    return msgs


# ═══════════════════════════════════════════════════════════════════════════
def _judge(mut: Mutation, base: set[str], after: RunResult) -> tuple[str, list[str]]:
    if after.fatal:
        return "COLLECT-ERROR", [after.fatal]
    if after.collect_errors:
        return "COLLECT-ERROR", after.collect_errors
    new = sorted(after.fails - base)
    if not new:
        return "GREEN", []
    if mut.expect and not any(any(e in n for e in mut.expect) for n in new):
        return "WRONG-TEST", new
    return "RED", new


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    if args.restore:
        msgs = _restore_all()
        _REPORT.write_text("\n".join(msgs) or "无快照可还原", encoding="utf-8")
        return 0

    problems = _preflight()
    hard = [x for x in problems if "他人活体备份" not in x]
    if hard:
        _REPORT.write_text("启动前检查失败:\n" + "\n".join(problems), encoding="utf-8")
        return 2

    selected = [m for m in MUTATIONS if not args.only or m.mid in args.only]
    md5_before = {p: _md5(p) for p in _OWNED}

    lines: list[str] = ["Task 23 变异检验（回收基线 + 新增零回归判据）", ""]
    if problems:
        lines += ["启动前提示（非阻断）:", *[f"  {x}" for x in problems], ""]

    # 基线：两侧各跑一次
    base_both = _run(("py", "ts"))
    lines += [
        f"基线: {base_both.summary}",
        f"基线失败数 = {len(base_both.fails)}",
        *[f"    (基线红) {x}" for x in sorted(base_both.fails)],
        "",
    ]
    if base_both.fatal:
        lines.append(f"🔴 基线本身 fatal: {base_both.fatal} —— 差集判定不可靠，中止")
        _REPORT.write_text("\n".join(lines), encoding="utf-8")
        return 2

    tally: dict[str, int] = {}
    rows: list[str] = []
    try:
        for mut in selected:
            miss = _apply(mut)
            if miss:
                _restore_all()
                tally["ANCHOR-MISS"] = tally.get("ANCHOR-MISS", 0) + 1
                rows.append(f"{mut.mid:8s} ANCHOR-MISS  {mut.what}\n         {miss}")
                continue
            try:
                after = _run(mut.sides)
                verdict, new = _judge(mut, base_both.fails, after)
            finally:
                _restore_all()
            tally[verdict] = tally.get(verdict, 0) + 1
            rows.append(
                f"{mut.mid:8s} {verdict:12s} sides={','.join(mut.sides):6s} {mut.what}\n"
                f"         {after.summary}\n"
                + "\n".join(f"         + {n}" for n in new[:12])
                + (f"\n         ...共 {len(new)} 条" if len(new) > 12 else "")
                + (f"\n         note: {mut.note}" if mut.note else "")
            )
    finally:
        msgs = _restore_all()
        if msgs:
            rows.append("finally 兜底还原: " + ", ".join(msgs))

    lines += ["逐条判定:", *rows, ""]
    lines.append("汇总: " + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))

    md5_after = {p: _md5(p) for p in _OWNED}
    drift = [p.name for p in _OWNED if md5_before[p] != md5_after[p]]
    lines.append(
        "字节级还原核验: " + ("OK 全部一致" if not drift else f"🔴 未还原: {drift}")
    )
    leftover = [_snap(p).name for p in _OWNED if _snap(p).exists()]
    lines.append(f".t23bak 残留: {leftover or '无'}")
    if _VITEST_JSON.exists():
        _VITEST_JSON.unlink()

    _REPORT.write_text("\n".join(lines), encoding="utf-8")
    ok = not drift and not leftover and tally.get("RED", 0) == len(selected)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
