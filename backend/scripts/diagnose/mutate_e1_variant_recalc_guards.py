"""E1-3 variant 抹零修复的守卫变异检验（A 组）。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/ Task 15
Requirements: 2.5, 4.4 · Property 14

## 自举——用本 spec 的共享件给本 spec 的守卫跑变异

这既是推广的第一个「非迁移」的用例（不是对旧脚本换引擎，是从零写新脚本），
也让「三形态判定 + fxRate 三态 + 跨层守卫」三组修复各自有一条变异证明它在承重。

## 覆盖面分母

= Task 1 + Task 2 + Task 7 新建/扩展的守卫文件全集。每条变异的 why 写明
「为什么这条变异不是无效变异」（e-cycle 的 M3/M15 曾各踩过一次）。

用法::

    python backend/scripts/diagnose/mutate_e1_variant_recalc_guards.py --list
    python backend/scripts/diagnose/mutate_e1_variant_recalc_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_e1_variant_recalc_guards.py --run all
    python backend/scripts/diagnose/mutate_e1_variant_recalc_guards.py --run M01
    python backend/scripts/diagnose/mutate_e1_variant_recalc_guards.py --restore
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend"

# ─── 冻结基线 ────────────────────────────────────────────────────────────────
#: 2026-08-16 亲测：e1BankDetailFxForm(19 例) + e1BankVariantIntegrity(29 例) = 48 passed。
#: 改这个数必须同时说明来源。
BASELINE_FE_PASSED = 48

# ─── 覆盖面分母 ──────────────────────────────────────────────────────────────
#: Task 1 + Task 2 + Task 7 新建的守卫文件全集。
GUARD_FILES: dict[str, str] = {
    "e1BankDetailFxForm.spec.ts": "Task 1 新建（三形态判定 + fxRate 三态 + 零回归）",
    "e1BankVariantIntegrity.spec.ts": "Task 2+7 新建（跨层端到端 + 落库形态 + 聚合键）",
}

# ─── 目标文件 ─────────────────────────────────────────────────────────────────
_USE = "audit-platform/frontend/src/components/workpaper/composables/useE1BankDetail.ts"

# ─── 变异声明 ─────────────────────────────────────────────────────────────────
MUTATIONS: list[Mutation] = [
    Mutation(
        id="M01", side="fe", path=_USE, kind="replace",
        anchor="    if (classifyFxForm(row) === 'base-identity') {",
        new="    if (false) { // MUTATED: 删掉形态 A 分支",
        want="形态 A",
        why="形态 A 分支写死 false ⇒ 退回无条件由原币派生（修复前的缺陷形态），"
            "本位币非 0 的行切到 multi 版后会被 calcFxConvert(0,1)=0 覆盖。"
            "Task 1 的形态 A 断言（opening 与输入逐字相等）+ Task 2 的跨层守卫"
            "（rmb→multi 组合金额守恒）都应打红。"
            "🔴 不能用 `if (true)` 代替（那让所有行都走形态 A），外币行的守卫也会红"
            "——判定不再精确对应「形态 A 被删」这一形态，且打红 want 会是外币相关的"
            "而非「形态 A 本位币保留」。",
    ),
    Mutation(
        id="M02", side="fe", path=_USE, kind="replace",
        anchor="            r.fxRate === null || r.fxRate === undefined || r.fxRate === ''",
        new="            !r.fxRate",
        want="显式 0 与缺失必须可区分",
        why="三态归一改回 `|| 1` 的等价形式（`!0 === true` ⇒ 显式 0 被当成缺失回落 1），"
            "Property 8「显式 0 加载后仍为 0」的断言必须打红。"
            "🔴 不能只删三态判断改 `parseNum(r.fxRate) || 1`（那与修复前逐字相同），"
            "要的是用一种「看起来正确但语义不同」的写法，证明守卫能分辨。",
    ),
    Mutation(
        id="M03", side="fe", path=_USE, kind="replace",
        anchor="  return isBaseCurrency(String(row.fxCurrency ?? '')) ? 'base-identity' : 'foreign-pending'",
        new="  return row.fxRate === 1 ? 'base-identity' : 'foreign-pending'",
        want="fxCurrency",
        why="形态判据从 fxCurrency 改成 fxRate === 1 ⇒ 外币待录入行（fxRate 为 0"
            "但经归一后变 1 的不会被此变异影响——归一在 loadFromResponses 里、判定在"
            "recalcRow 里，两者不共享行对象。但**历史数据**里无 fxRate 字段回落 1 的行"
            "会按此判据走进 base-identity 而实际上它可能是外币）。"
            "具体哪条守卫红取决于测试数据的 fxCurrency 设置，Task 1 有一组"
            "「fxCurrency=USD + fc 全 0」的形态 B 构造，改用 fxRate 判定后它会被误判"
            "成形态 A ⇒ 那组断言必红。",
    ),
    Mutation(
        id="M04", side="fe", path=_USE, kind="replace",
        anchor="      const endingFc = ending",
        new="      const endingFc = 0 // MUTATED: 不再镜像本位币",
        want="原币小计列镜像本位币",
        why="形态 A 下删掉 endingFc 镜像（改回恒 0）⇒ Property 13 断言"
            "「endingFc === calcCashBalance(opening,increase,decrease)」必须打红。"
            "🔴 这条精确验的是「不出现本位币有值而原币为 0 的自相矛盾展示」——"
            "镜像是派生列（不落库），删了不影响 opening/increase/decrease 的守恒"
            "（M01 覆盖那部分），但影响 UI 展示一致性。",
    ),
    Mutation(
        id="M05", side="fe", path=_USE, kind="replace",
        anchor="  const ending = calcCashBalance(row.opening, row.increase, row.decrease)",
        new="  const ending = row.opening + row.increase // MUTATED: rmb 少减了 decrease",
        want="rmb",
        why="rmb 分支的 ending 算法改错（少减 decrease）⇒ Property 4「rmb 分支输出与"
            "修复前逐字相同」的零回归断言必须打红。"
            "🔴 不能用 `if (variant === 'rmb')` 作锚点（不是唯一行），也不能删整个"
            "rmb 分支（会让守卫因「函数未返回」而红，命中的是别的原因 = WRONG-TEST）。"
            "改 ending 公式是最精确的：只有 rmb 的期末结果变了，其余分支不受影响。",
    ),
    Mutation(
        id="M06", side="fe", path=_USE, kind="replace",
        anchor="  if (hasFc) return 'fc-authoritative'",
        new="  if (hasFc) return 'base-identity' // MUTATED: 外币行走本位币分支",
        want="fc-authoritative",
        why="把形态 C（原币权威）误判成形态 A ⇒ 有真实原币数据的行不再由原币派生，"
            "而是保留（可能过时的）本位币值。Task 1 有形态 C 构造组（fc 列非 0 + "
            "fxRate 非 1），其 opening === calcFxConvert(openingFc, fxRate) 的断言"
            "必须打红（因为此变异下 opening 不再被派生，保留输入值 ≠ fc*rate）。",
    ),
]


# ─── CLI ─────────────────────────────────────────────────────────────────────

_FE_JSON = Path(__file__).parent / "_wip_mut_e1v_fe.json"

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="E1-3 variant 抹零修复守卫变异检验（A 组）",
            frontend_filters=["e1BankDetailFxForm", "e1BankVariantIntegrity"],
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
            baseline_frontend_passed=BASELINE_FE_PASSED,
        )
    )
