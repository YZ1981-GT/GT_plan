"""Task 18 变异检验：建议分配表组件 / 资历折算 / 接线守卫。

spec: procedure-trimming-and-delegation-intelligence — Task 18

## 为什么必须有这个脚本

守卫全绿有两种可能：①被测代码是对的 ②守卫的判据压根没落在被测结构上（空转）。
两者在退出码上完全一样。变异检验就是逐条把**正确实现改坏**，看守卫是否打红 ——
没打红 = 守卫有缺陷，不是代码没问题。

本轮 Task 18 的守卫在写作过程中已暴露 4 个自身缺陷（`fnBody` 语句特征筛选把只含
表达式语句的函数体跳过、`computedArg` 不认 `computed<T>(`、断言 camelCase
`wpIndexIds` 而真源是 snake_case、`P_COMMON_API` 未声明），这些都是「判据落在
无关文本上」的形态 —— 正是变异检验要防的。

## 四态判定（只看退出码会把后三态误判成 RED）

| 态 | 含义 |
|---|---|
| RED | 打红且**正是**预期那条测试 ⇒ 守卫承重，有效 |
| GREEN | 变异施加了但测试仍全绿 ⇒ **守卫缺陷** |
| ANCHOR-MISS | 锚点零命中或多命中 ⇒ **脚本缺陷**（变异根本没施加，此时"绿"无意义） |
| WRONG-TEST | 打红了但不是预期项 ⇒ 锚点错行或有污染残留 |

## 锚点约定（踩过的坑）

- **行级唯一**：`splitlines()` + 锚点行内匹配 + `hits == 1` + 相对 offset。
- **禁含 `\\n` 的跨行字面量** —— 本工作树是 CRLF，跨行锚点必 MISS。
- 变异后断言**字节确实变了**（未变则"测试仍绿"不能作为任何结论）。
- `.bak` + `try/finally` 无条件写回 + md5 核验字节级还原。

## 判定读 JSON 不读 stdout

本环境 python 子进程 stdout 会被 `\\ode (vitest N)\\` 转义符污染吞掉，故一律落盘再读。
`npm exec` 经 `subprocess.run` 数组形式**必须加 `--` 分隔符**，否则 npm 把
`--reporter` 当自己的 cli config 并 warn `Unknown cli config`，**JSON 根本不生成而
退出码仍 0** —— 会让「解析到陈旧 JSON」以「功能未修好」的形态误导判断。故跑前删旧
JSON + 断言新 JSON 存在。

用法::

    python backend/scripts/check/mutate_task18_suggestion_guards.py
    python backend/scripts/check/mutate_task18_suggestion_guards.py --restore
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform" / "frontend"
SRC = FE / "src"

P_COMP = SRC / "components" / "workpaper" / "delegation" / "GtDelegationSuggestionTable.vue"
P_TRIM = SRC / "views" / "ProcedureTrimming.vue"
P_SENIORITY = SRC / "components" / "workpaper" / "composables" / "delegationSeniority.ts"
P_SUGGESTION = SRC / "components" / "workpaper" / "composables" / "delegationSuggestion.ts"

TARGETS = [
    "src/components/workpaper/delegation",
    "src/components/workpaper/composables/__tests__/delegationSeniority.spec.ts",
    "src/components/workpaper/composables/__tests__/delegationSuggestion.spec.ts",
]

REPORT = ROOT / "_wip_t18_mutation_report.txt"
JSONP = ROOT / "_wip_t18_mutation.json"


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
    # ── M1：wp_index_id → wp_id（最贵的一条）──────────────────────────────
    Mutation(
        ident="M1",
        path=P_TRIM,
        desc="buildSuggestionTargets 取 wp_id 代替 wp_index_id",
        anchor="const wpIndexId = String(item.wp_index_id",
        offset=0,
        old="item.wp_index_id",
        new="item.wp_id",
        expect_substr="wp_index_id",
        rationale=(
            "底稿粒度 selector 要 wp_index.id，而 wp_id 是 working_paper.id。"
            "拿 wp_id 填 wp_index_ids 后端匹配不到任何目标且不报错 —— 表现为"
            "「建议表生成了但应用后 0 变更」，最难归因的一类。"
        ),
    ),
    # ── M2：负载未知补 0 ──────────────────────────────────────────────────
    Mutation(
        ident="M2",
        path=P_COMP,
        desc="loadBoard 把负载未知的成员补成 0 基线",
        anchor="after: before === null ? null : before + increment,",
        offset=0,
        old="before === null ? null : before + increment",
        new="(before ?? 0) + increment",
        expect_substr="null",
        rationale=(
            "补 0 会产出一个「分配后负载 1.50」这样看起来像绝对值的数，UI 无从区分"
            "它和真实的 1.50；更糟的是 0 会被读成「这个人很空闲」，于是工作被堆给"
            "我们连在手任务量都不知道的那个人。"
        ),
    ),
    # ── M3：ROLE_SENIORITY 改成与 ROLE_PRIORITY 同序 ──────────────────────
    Mutation(
        ident="M3",
        path=P_SENIORITY,
        desc="未登记 role 兜底改成最高档（与 ROLE_PRIORITY 的 ?? 90 同向）",
        anchor="export const SENIORITY_UNREGISTERED = 1",
        offset=0,
        old="SENIORITY_UNREGISTERED = 1",
        new="SENIORITY_UNREGISTERED = 99",
        expect_substr="未登记",
        rationale=(
            "ROLE_PRIORITY 的兜底是 `?? 90`，在它自己的语义里（越小越靠前）表示"
            "「排最后」；但同一个数值挪到资历尺子上（越大越资深）就变成「资历最高」。"
            "这是两个字典最危险的一处方向差异：不认识的角色反而被允许承担高风险底稿。"
        ),
    ),
    # ── M4：SOD 复核人候选不排除执行人本人 ────────────────────────────────
    Mutation(
        ident="M4",
        path=P_COMP,
        desc="reviewerOptions 不再排除执行人本人（破 SOD 硬约束）",
        anchor="(m) => m.staffId !== row.assigneeStaffId && m.seniority >= floor,",
        offset=0,
        old="m.staffId !== row.assigneeStaffId && m.seniority >= floor",
        new="m.seniority >= floor",
        expect_substr="SOD",
        rationale=(
            "执行人复核自己的工作，在质控与 EQCR 眼里等于没有复核，而底稿上却显示"
            "「已复核」—— 比明摆着缺复核人更坏。"
        ),
    ),
    # ── M5：组件自己发请求（破只读+emit 边界）────────────────────────────
    Mutation(
        ident="M5",
        path=P_COMP,
        desc="emitApply 改为组件自行调用 applyProcedureDelegation",
        anchor="  emit('apply', applyGroups.value, plainRows())",
        offset=0,
        old="emit('apply', applyGroups.value, plainRows())",
        new="applyProcedureDelegation(applyGroups.value)",
        expect_substr="emit",
        rationale=(
            "组件一旦自己发请求，写入路径就从「宿主统一走既有 preview → apply 两阶段」"
            "裂成两条；且组件无法拿到 request_id 幂等凭证与 409 重试语义。"
        ),
    ),
    # ── M6：unassignedTargets 只塞 tooltip 不独立成块 ─────────────────────
    Mutation(
        ident="M6",
        path=P_COMP,
        desc="删掉 unassignedTargets 独立区块的渲染条件",
        anchor='<div v-if="suggestion.unassignedTargets.length > 0" class="gt-dst__block">',
        offset=0,
        old='v-if="suggestion.unassignedTargets.length > 0"',
        new='v-if="false"',
        # 🔴 expect_substr 必须与**守卫测试名**匹配，不是与被测标识符匹配。
        #    首轮这里写 "unassignedTargets"（被测标识符）⇒ 守卫其实正确打红了，
        #    但脚本因测试名里没有该字样而误判成 WRONG-TEST。这类「脚本判据与
        #    守卫产出不同口径」是变异检验第四态的典型成因，改为钉测试名。
        expect_substr="未分配区块的渲染条件由数据驱动",
        rationale=(
            "「H 风险无人覆盖」是必须上报项目负责人的事实（需加派资深人员或升级复核"
            "层级）。藏进 tooltip 或不渲染，等于算法默默把它咽下去。"
        ),
    ),
    # ── M7：targets 不再按 wpIndexId 去重（本轮零回归暴露的真实缺陷）────────
    Mutation(
        ident="M7",
        path=P_SUGGESTION,
        desc="suggestDelegation 去掉 targets 的 wpIndexId 去重判断",
        anchor="    if (seenTargets.has(wpIndexId)) {",
        offset=0,
        old="seenTargets.has(wpIndexId)",
        new="false",
        # ancestorTitles 命中三条确定性用例（PBT 那条 describe 名不同，不会误配）
        expect_substr="targets 按 wpIndexId 去重",
        rationale=(
            "同一张底稿出现两次若不去重，会产出两条针对同一底稿的建议 ⇒ "
            "①委派对同一 wp_index_id 重复下发（产出的 wpIndexId 直接进 selector 的 "
            "wp_index_ids）②Task 18 建议分配表以 wpIndexId 作行键（row-key），重复键"
            "会让改执行人/移除行串行到错误的行。该缺陷原本只由 PBT 偶发抽到重复 id 时"
            "显形（seed -986847725），故必须有确定性用例把它钉死。"
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

    lines: list[str] = ["# Task 18 变异检验报告", ""]

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
