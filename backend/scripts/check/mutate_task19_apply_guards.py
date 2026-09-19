"""Task 19 变异检验：建议分配「逐组应用」守卫。

spec: procedure-trimming-and-delegation-intelligence — Task 19

## 为什么必须有这个脚本

守卫全绿有两种可能：①被测代码是对的 ②守卫的判据压根没落在被测结构上（空转）。
两者在退出码上完全一样。变异检验就是逐条把**正确实现改坏**，看守卫是否打红 ——
没打红 = 守卫有缺陷，不是代码没问题。

本轮守卫在写作过程中已暴露 1 个自身缺陷（拿花括号配对法去截 python 的
`class DelegationSelector`，命中的是类体里 `to_payload` 的 `return {...}` 字典字面量，
断言在无关文本上求值并以「后端未声明 wp_index_ids」的形态假红），正是本脚本要防的形态。

## 四态判定（只看退出码会把后三态误判成 RED）

| 态 | 含义 |
|---|---|
| RED | 打红且**正是**预期那条测试 ⇒ 守卫承重，有效 |
| GREEN | 变异施加了但测试仍全绿 ⇒ **守卫缺陷** |
| ANCHOR-MISS | 锚点零命中或多命中 ⇒ **脚本缺陷**（变异根本没施加，此时"绿"无意义） |
| WRONG-TEST | 打红了但不是预期项 ⇒ 锚点错行或有污染残留 |

另有第五态 **collection-error**（变异体不是合法 TS/Vue，整文件零断言执行）：
本脚本按「新增失败中是否含预期子串」判定，若整文件挂掉会以 WRONG-TEST 暴露。

## 锚点约定（踩过的坑）

- **行级唯一**：`splitlines()` + 锚点行内匹配 + `hits == 1` + 相对 offset。
- **禁含 `\\n` 的跨行字面量** —— 本工作树是 CRLF，跨行锚点必 MISS。
- 变异后断言**字节确实变了**（未变则"测试仍绿"不能作为任何结论）。
- `.bak` + `try/finally` 无条件写回 + md5 核验字节级还原。

## 判定读 JSON 不读 stdout

本环境 python 子进程 stdout 会被 `\\ode (vitest N)\\` 转义符污染吞掉，故一律落盘再读。
`npm exec` 经 `subprocess.run` 数组形式**必须加 `--` 分隔符**，否则 npm 把 `--reporter`
当自己的 cli config 并 warn `Unknown cli config`，**JSON 根本不生成而退出码仍 0**。
故跑前删旧 JSON + 断言新 JSON 存在。

用法::

    python backend/scripts/check/mutate_task19_apply_guards.py
    python backend/scripts/check/mutate_task19_apply_guards.py --restore
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform" / "frontend"
SRC = FE / "src"

P_TRIM = SRC / "views" / "ProcedureTrimming.vue"
P_COMP = SRC / "components" / "workpaper" / "delegation" / "GtDelegationSuggestionTable.vue"

TARGETS = [
    "src/views/__tests__/delegationSuggestionApply.spec.ts",
]

REPORT = ROOT / "_wip_t19_mutation_report.txt"
JSONP = ROOT / "_wip_t19_mutation.json"


@dataclass
class Mutation:
    ident: str
    path: Path
    desc: str
    anchor: str
    offset: int
    old: str
    new: str
    expect_substr: str
    rationale: str


MUTATIONS: list[Mutation] = [
    # ── M1：selector 退回循环粒度 ─────────────────────────────────────────
    Mutation(
        ident="M1",
        path=P_TRIM,
        desc="suggestionGroupBody 的 selector 退回 cycle 粒度",
        anchor="    selector: { kind: 'workpaper' as const, wp_index_ids: state.wpIndexIds },",
        offset=0,
        old="{ kind: 'workpaper' as const, wp_index_ids: state.wpIndexIds }",
        new="{ kind: 'cycle' as const, cycle: activeCycle.value }",
        expect_substr="selector 用底稿粒度 workpaper",
        rationale=(
            "建议分配的全部价值在于底稿粒度逐张分派；用 cycle 会把整循环的任务都改成"
            "本组执行人 —— 恰好抹掉用户逐行调整的结果，而请求会 200 成功。"
        ),
    ),
    # ── M2：读组件不存在的 wpIndexIds（复现 Task 18 宿主缺陷）─────────────
    Mutation(
        ident="M2",
        path=P_TRIM,
        desc="从组件 group 上读不存在的 wpIndexIds（Task 18 宿主原缺陷）",
        anchor="    wpIndexIds: [...g.selector.wp_index_ids],",
        offset=0,
        old="[...g.selector.wp_index_ids]",
        new="[...(g as any).wpIndexIds]",
        expect_substr="不读不存在的 wpIndexIds",
        rationale=(
            "组件 emit 的是 `selector.wp_index_ids`，根本没有 `wpIndexIds` 字段。"
            "读它得 undefined，`[...undefined]` 直接抛 TypeError —— 而 Volar / vitest 源码扫 / "
            "get_diagnostics / HEAD-swap 四层全绿（本文件上 get_diagnostics 更是全盲）。"
        ),
    ),
    # ── M3：body 构造两次（防篡改 hash 会不一致）──────────────────────────
    Mutation(
        ident="M3",
        path=P_TRIM,
        desc="apply 侧另构造一份 body（preview/apply payload 可能不一致）",
        anchor="      projectId.value, previewId, state.requestId, body,",
        offset=0,
        old="state.requestId, body,",
        new="state.requestId, suggestionGroupBody(state),",
        expect_substr="复用同一个 body 对象",
        rationale=(
            "后端 apply 侧用 `canonical_request_hash(request_payload)` 重算并与 preview "
            "存储的 hash 比对（防篡改）。构造两次一旦 builder 带上任何时变量就 409"
            "「预览请求已被篡改」，且这种失败在 UI 上与"
            "「预览过期」难以区分。"
        ),
    ),
    # ── M4：零目标不再短路 ────────────────────────────────────────────────
    Mutation(
        ident="M4",
        path=P_TRIM,
        desc="targets === 0 不再短路，继续走 apply（applied:0 冒充成功）",
        anchor="    if (state.targets === 0) {",
        offset=0,
        old="if (state.targets === 0) {",
        new="if (false) {",
        expect_substr="targets === 0 在 apply 调用之前短路",
        rationale=(
            "目标数 0 时 apply 也会 200 并返回 applied:0，屏幕上就是「已应用」。"
            "真实库 procedure_row_tasks 仅 46 行 / 3 个项目 ⇒ 多数项目正是这个形态"
            "（行任务未物化），此路一开则「委派成功但一行没动」成为常态。"
        ),
    ),
    # ── M5：一组失败即中断后续组 ──────────────────────────────────────────
    Mutation(
        ident="M5",
        path=P_TRIM,
        desc="逐组循环里一组非 applied 即 break（放弃其余组）",
        anchor="      await applySuggestionGroup(state)",
        offset=0,
        old="await applySuggestionGroup(state)",
        new="await applySuggestionGroup(state)\n      if (state.status !== 'applied') break",
        expect_substr="循环体不中断后续组",
        rationale=(
            "第一组 409 就放弃其余组，会让审计师以为整批都失败而整体重做 —— "
            "对已成功组构成重复委派。任务书明确要求「不影响已成功组」。"
        ),
    ),
    # ── M6：409 三分类塌成一句「请重新预览」──────────────────────────────
    Mutation(
        ident="M6",
        path=P_TRIM,
        desc="SOD 类 409 也提示「重新预览」（三分类塌成一类）",
        anchor="      message: text + '；重新预览无效，请为本组改选操作复核人',",
        offset=0,
        old="text + '；重新预览无效，请为本组改选操作复核人'",
        new="text + '；请重新预览该组后重试'",
        expect_substr="SOD 类 409 不得建议",
        rationale=(
            "SOD 冲突（后端 assert_sod_distinct）也是 409，但重新预览一万次都不会好 —— "
            "必须换复核人。把三类 409 塌成一句「请重新预览」会让审计师做无用功，"
            "并最终把问题归因成「系统不稳定」。"
        ),
    ),
    # ── M7：重试重建 groups（抹掉已成功组）───────────────────────────────
    Mutation(
        ident="M7",
        path=P_TRIM,
        desc="retrySuggestionGroup 重建 groups 数组",
        anchor="  const state = suggestApply.value.groups[index]",
        offset=0,
        old="const state = suggestApply.value.groups[index]",
        new=(
            "suggestApply.value.groups = suggestApply.value.groups.slice(index, index + 1)\n"
            "  const state = suggestApply.value.groups[0]"
        ),
        expect_substr="单组重试只重跑该组",
        rationale=(
            "重建会把已成功组的 applied 计数抹成 0（甚至整行消失），屏幕上像"
            "「上次全白做了」⇒ 审计师会对已落库的组再委派一遍。"
        ),
    ),
    # ── M8：改走底稿主编层写入（第二套真源）─────────────────────────────
    Mutation(
        ident="M8",
        path=P_TRIM,
        desc="逐组应用改调 assignProcedures（底稿主编层的另一真源）",
        anchor="    const pv = await previewProcedureDelegation(projectId.value, body)",
        offset=0,
        old="const pv = await previewProcedureDelegation(projectId.value, body)",
        new=(
            "await assignProcedures(projectId.value, [])\n"
            "    const pv = await previewProcedureDelegation(projectId.value, body)"
        ),
        expect_substr="不借用 assignProcedures",
        rationale=(
            "assignProcedures 写的是 WorkingPaper.assigned_to（底稿主编），与行级委派"
            "不是同一真源；掺进来会让两层状态互相串线，且绕过 preview 的版本校验。"
        ),
    ),
    # ── M9：删掉模板里的单组重试入口 ─────────────────────────────────────
    Mutation(
        ident="M9",
        path=P_TRIM,
        desc="模板去掉单组「重新应用」按钮（渲染宿主缺一半）",
        anchor='                @click="retrySuggestionGroup($index)"',
        offset=0,
        old='@click="retrySuggestionGroup($index)"',
        new='@click="suggestPanel.visible = true"',
        expect_substr="单组重试入口",
        rationale=(
            "脚本侧状态机全在、模板缺入口 = Task 14 已登记的「声明而无渲染宿主」形态，"
            "四层检查全绿而功能不存在：审计师只能整体重做。"
        ),
    ),
    # ── M10：并行提交（互相顶掉 lock_version）───────────────────────────
    Mutation(
        ident="M10",
        path=P_TRIM,
        desc="逐组改并行 Promise.all 提交",
        # 🔴 `old` 必须**单行**：本工作树是 CRLF，含 `\n` 的字面量在 raw 文本里必失配
        #    （报 ANCHOR-MISS 而非施加变异）。故只改 for 行本身，把循环体留成永不执行
        #    的合法块 —— 变异体仍是合法 TS，避免退化成 collection-error 第五态。
        anchor="    for (const state of suggestApply.value.groups) {",
        offset=0,
        old="for (const state of suggestApply.value.groups) {",
        new=(
            "await Promise.all(suggestApply.value.groups.map(s => applySuggestionGroup(s)))\n"
            "    for (const state of [] as SuggestionApplyGroupState[]) {"
        ),
        expect_substr="逐组顺序执行而非并行",
        rationale=(
            "后端 apply 用 `resolve_targets(..., for_update=True)` 行锁复取并比对 "
            "`target_versions`；并行提交时先落库的那组改变 lock_version ⇒ 其余组全部 409"
            "「目标任务版本已变化」。表现为「随机有几组失败」，最难复现的一类。"
        ),
    ),
    # ── M11：组件把 selector 字段改成 camelCase（跨文件锁死）──────────────
    Mutation(
        ident="M11",
        path=P_COMP,
        desc="组件导出类型把 wp_index_ids 改成 camelCase",
        anchor="  selector: { kind: 'workpaper'; wp_index_ids: string[] }",
        offset=0,
        old="wp_index_ids: string[]",
        new="wpIndexIds: string[]",
        expect_substr="组件导出的 DelegationApplyGroup",
        rationale=(
            "后端 `DelegationSelector.wp_index_ids` 是 snake_case；组件侧一改名，"
            "宿主取值全 undefined 而 selector 里塞进 undefined —— 请求 422 或匹配 0 个目标。"
            "两侧命名必须交叉锁死。"
        ),
    ),
    # ── M12：no_target 标成成功态 ────────────────────────────────────────
    Mutation(
        ident="M12",
        path=P_TRIM,
        desc="no_target 的标签改成「已应用成功」",
        anchor="  no_target: '无可委派目标',",
        offset=0,
        old="no_target: '无可委派目标',",
        new="no_target: '已应用成功',",
        expect_substr="no_target 的标签与配色都不是",
        rationale=(
            "状态机分了独立态却在展示层又标成成功，等于白分 —— 审计师看到的仍是"
            "「委派成功」。判据必须同时钉死状态与它的呈现。"
        ),
    ),
]


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def locate(text: str, mu: Mutation) -> tuple[int, int]:
    """行级唯一定位，返回 (绝对偏移, 命中行数)。"""
    lines = text.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if mu.anchor in ln]
    if len(hits) != 1:
        return -1, len(hits)
    target = hits[0] + mu.offset
    if not (0 <= target < len(lines)):
        return -1, 0
    return sum(len(x) for x in lines[:target]), 1


def run_guards() -> tuple[dict, str]:
    if JSONP.exists():
        JSONP.unlink()
    cmd = ["npm.cmd", "exec", "--", "vitest", "run", *TARGETS,
           "--reporter=json", f"--outputFile={JSONP}"]
    proc = subprocess.run(cmd, cwd=str(FE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not JSONP.exists():
        return {}, f"JSON 未生成（exit={proc.returncode}）\n{(proc.stderr or '')[-2000:]}"
    return json.loads(JSONP.read_text(encoding="utf-8")), ""


def failed_names(data: dict) -> set[str]:
    out: set[str] = set()
    for res in data.get("testResults", []):
        fname = Path(res.get("name", "")).name
        status = res.get("status")
        msg = (res.get("message") or "").strip()
        if status == "failed" and not res.get("assertionResults"):
            # 整文件 collection error（零断言执行）—— 必须显式暴露，别当 GREEN
            out.add(f"{fname}::<COLLECTION-ERROR> {msg[:120]}")
        for a in res.get("assertionResults", []):
            if a.get("status") == "failed":
                anc = " ".join(a.get("ancestorTitles") or [])
                out.add(f"{fname}::{anc} {a.get('title')}")
    return out


def restore_all() -> list[str]:
    msgs = []
    for p in {m.path for m in MUTATIONS}:
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.exists():
            p.write_bytes(bak.read_bytes())
            bak.unlink()
            msgs.append(f"已还原 {p.name}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    if args.restore:
        lines = restore_all() or ["无 .bak 需还原"]
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        return 0

    lines: list[str] = ["# Task 19 变异检验报告", ""]

    base, err = run_guards()
    if err:
        REPORT.write_text(f"基线跑失败：{err}", encoding="utf-8")
        return 2
    base_fail = failed_names(base)
    lines += [
        f"基线 total={base.get('numTotalTests')} passed={base.get('numPassedTests')} "
        f"failed={base.get('numFailedTests')} suites={base.get('numTotalTestSuites')}",
        f"基线失败集合大小={len(base_fail)}",
        "",
    ]
    for n in sorted(base_fail):
        lines.append(f"  [基线红] {n}")
    lines.append("")

    verdicts: dict[str, str] = {}

    for mu in MUTATIONS:
        p = mu.path
        original = p.read_bytes()
        before_md5 = md5(p)
        bak = p.with_suffix(p.suffix + ".bak")
        bak.write_bytes(original)
        lines += [f"## {mu.ident} — {mu.desc}", f"文件: {p.name}", f"理由: {mu.rationale}"]

        try:
            text = original.decode("utf-8")
            off, hits = locate(text, mu)
            if off < 0:
                verdicts[mu.ident] = "ANCHOR-MISS"
                lines += [f"判定: ANCHOR-MISS（锚点命中 {hits} 次，必须恰 1）", ""]
                continue

            seg_end = off + 4000
            segment = text[off:seg_end]
            if mu.old not in segment:
                verdicts[mu.ident] = "ANCHOR-MISS"
                lines += [f"判定: ANCHOR-MISS（锚点行附近未找到 old 片段 {mu.old!r}）", ""]
                continue

            mutated = text[:off] + segment.replace(mu.old, mu.new, 1) + text[seg_end:]
            if mutated == text:
                verdicts[mu.ident] = "ANCHOR-MISS"
                lines += ["判定: ANCHOR-MISS（替换后字节未变）", ""]
                continue

            p.write_text(mutated, encoding="utf-8", newline="")
            if md5(p) == before_md5:
                verdicts[mu.ident] = "ANCHOR-MISS"
                lines += ["判定: ANCHOR-MISS（写盘后 md5 未变）", ""]
                continue

            data, err2 = run_guards()
            if err2:
                verdicts[mu.ident] = "ANCHOR-MISS"
                lines += [f"判定: 跑测失败 {err2}", ""]
                continue

            mut_fail = failed_names(data)
            new_fail = mut_fail - base_fail
            if not new_fail:
                verdicts[mu.ident] = "GREEN"
                lines += ["判定: 🔴 GREEN = 守卫缺陷（变异已施加但无新增失败）", ""]
                continue

            matched = [n for n in new_fail if mu.expect_substr in n]
            if matched:
                verdicts[mu.ident] = "RED"
                lines += [f"判定: RED（新增失败 {len(new_fail)} 条，含预期项）"]
            else:
                verdicts[mu.ident] = "WRONG-TEST"
                lines += [
                    f"判定: WRONG-TEST（新增 {len(new_fail)} 条但无一含 "
                    f"{mu.expect_substr!r}）"
                ]
            for n in sorted(new_fail):
                lines.append(f"    + {n}")
            lines.append("")
        finally:
            p.write_bytes(original)
            after_md5 = md5(p)
            ok = after_md5 == before_md5
            lines.append(f"还原核验: md5 {'一致' if ok else '不一致 ⚠️'} ({after_md5[:12]})")
            if bak.exists():
                bak.unlink()
            lines.append("")

    lines += ["## 汇总", ""]
    for mu in MUTATIONS:
        lines.append(f"  {mu.ident}: {verdicts.get(mu.ident, '未执行')} — {mu.desc}")
    reds = sum(1 for v in verdicts.values() if v == "RED")
    lines += ["", f"RED {reds}/{len(MUTATIONS)}"]
    if reds != len(MUTATIONS):
        lines.append("⚠️ 存在非 RED 项，必须逐条查明是守卫缺陷还是脚本缺陷")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return 0 if reds == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
