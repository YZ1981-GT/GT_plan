"""I 循环守卫的变异检验（Task 20 / Requirements 11.3）。

## 为什么需要它

「测试全绿」不等于「守卫有鉴别力」。平台已记的三类假绿里有两类靠跑测试发现不了：

1. **additive 注入即死代码** —— 新加的取值/字段无消费方
2. **grep 式守卫只查字符串存在** —— 改成 `if False:` / 删调用 / 改名残留仍绿
3. **守卫把错值当基线锁死** —— 把真源改对反而打红

变异检验是唯一能系统性排除第 2、3 类的手段：**逐个把被测对象改坏，看守卫是否打红**。
本轮开发过程中它抓出 6 个真守卫缺陷（详见 `tasks.md` Task 17/18 的记录），
其中「HTML 判据跳过整表」「I3 行标签写错」两处若无变异检验就会成为假绿交付。

## 四态判定（只看退出码会把后三态误判成 RED）

- ``RED``          变异后打红，且**正是预期那条**守卫 → 守卫有鉴别力 ✅
- ``GREEN``        变异后仍全绿 → **守卫有缺陷**（判据太宽 / 在空转）
- ``ANCHOR-MISS``  锚点未命中或命中 != 1 → **脚本缺陷**（不是守卫问题）
- ``WRONG-TEST``   打红了但不是预期项 → 污染残留或锚点落错行

## 判定方式：失败测试名**集合差集**，不看退出码

Wave 1 的守卫基线本就可能有红（并发会话在写 K/L 域）。故先跑一遍取 `baseline_failed`，
变异后再跑取 `mutated_failed`，判据 = ``expect_test ∈ (mutated_failed - baseline_failed)``。

## 安全性

- 每次变异前把原文备份成 ``<file>.mutbak``，变异后 **finally 必还原 + 字节级 md5 核验**
- ``--restore`` 可在脚本被 Ctrl+C 中断后手工还原全部 ``.mutbak``
- **不变异源 xlsx**（二进制 + 运行时权威模板，Requirement 10.7 明令不得反改）
- 只读式退出：任何异常都先还原再抛

用法::

    python backend/scripts/diagnose/mutate_i_cycle_guards.py            # 跑全部
    python backend/scripts/diagnose/mutate_i_cycle_guards.py --only P1,P6
    python backend/scripts/diagnose/mutate_i_cycle_guards.py --list     # 只列清单
    python backend/scripts/diagnose/mutate_i_cycle_guards.py --restore  # 中断后还原

spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 20
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_FT = _ROOT / "backend" / "app" / "services" / "four_table"
_FIX = _ROOT / "backend" / "scripts" / "fix"
_TESTS = _ROOT / "backend" / "tests"
_FE = _ROOT / "audit-platform" / "frontend"
_CB = _FE / "src" / "components" / "workpaper" / "composables"
_WPC = _FE / "src" / "components" / "workpaper"

_BAK_SUFFIX = ".mutbak"

# ─────────────────────────────────────────────────────────────────────────────
# 变异定义
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Mutation:
    """一个变异。

    Attributes:
        prop: design.md 的 Property 编号（`P1` / `P16` …）。
        title: 变异语义（中文，报告用）。
        target: 被变异的**生产文件**（禁写测试文件本身 —— 改判据不算变异被测对象）。
        anchor: 锚点原文。**必须在 target 里恰好命中 1 次**（行级定位）。
        replacement: 替换文本。
        expect_test: 期望打红的测试名（pytest 的 `test_xxx` 或 vitest 的用例名片段）。
        suite: `backend` 走 pytest，`frontend` 走 vitest。
        allow_first: 允许锚点多命中、只改首处（仅用于「文件里出现任意一处即该打红」类判据）。
    """

    prop: str
    title: str
    target: Path
    anchor: str
    replacement: str
    expect_test: str
    suite: str = "backend"
    allow_first: bool = False


#: 后端守卫的默认跑测范围（一次跑全部 I 循环守卫，用差集判定，不怕基线有红）
_BE_PATHS: tuple[str, ...] = (
    "backend/tests/four_table/test_i_cycle_row_code_evidence.py",
    "backend/tests/four_table/test_i_cycle_accounts.py",
    "backend/tests/four_table/test_i5_absent_account.py",
    "backend/tests/test_i_cycle_formula_presets.py",
    "backend/tests/test_note_i_cycle_structure.py",
)

#: 前端守卫范围
_FE_SPECS: tuple[str, ...] = (
    "src/components/workpaper/composables/__tests__/iCycleAccountScope.spec.ts",
    "src/components/workpaper/composables/__tests__/iCycleDynamicRows.spec.ts",
    "src/components/workpaper/composables/__tests__/iDisclosureColumns.spec.ts",
    "src/components/workpaper/composables/__tests__/iCycleAdjudicationSeed.spec.ts",
    # 跨域：本 spec 修正了该守卫的判据缺陷（旧判据要求被检行自带 `disclosure-notes`
    # 才检查 ⇒ 走错端点的调用恒被放过）。纳入变异范围以锁死修正后的判据。
    "src/components/workpaper/__tests__/disclosureSyncUrlContract.spec.ts",
)


MUTATIONS: tuple[Mutation, ...] = (
    # ── P1：row_code 与 report_config 行名一致 ─────────────────────────────
    Mutation(
        prop="P1",
        title="I1 行编码改回旧错值 BS-033（该码实为 I2 开发支出的行）",
        target=_FT / "i_cycle_accounts.py",
        anchor='"I1": {"listed": "BS-032", "soe": "BS-032"},',
        replacement='"I1": {"listed": "BS-033", "soe": "BS-033"},',
        expect_test="test_row_code_equals_expected",
    ),
    # ── P2：两准则同码 ────────────────────────────────────────────────────
    Mutation(
        prop="P2",
        title="I6 拆成两码（模拟被按 J1「按变体不同」范式误改）",
        target=_FT / "i_cycle_accounts.py",
        anchor='"I6": {"listed": "IS-006", "soe": "IS-006"},',
        replacement='"I6": {"listed": "IS-006", "soe": "IS-024"},',
        expect_test="test_listed_equals_soe",
    ),
    # ── P3：取数零回归（叶子聚合的符号与空段语义） ──────────────────────────
    Mutation(
        prop="P3",
        title="叶子行聚合去掉备抵段取绝对值（累计摊销/减值会变负数）",
        target=_FT / "i_cycle_prefill.py",
        anchor="        sign = abs if seg.absolute else (lambda v: v)\n        out.append(",
        replacement="        sign = (lambda v: v)\n        out.append(",
        # 🔴 首轮该条判 GREEN —— 实测全库**没有任何守卫测** build_leaf_project_rows /
        #    segment_amounts / build_i1_category_rows（其余循环都测了自己的
        #    build_adjudication_prefill，只有 I 循环纯函数层裸奔）。已补
        #    `TestProperty3LeafAggregationPurity` 8 条常驻判据。
        expect_test="test_provision_segment_takes_absolute_value",
    ),
    # ── P6：I5 兜底空 tuple ───────────────────────────────────────────────
    Mutation(
        prop="P6",
        title="给 I5 的空兜底塞一个码（把「本项目无此科目」伪装成有科目）",
        target=_FT / "i_cycle_accounts.py",
        # 🔴 锚点必须含 `name_keywords` 行才唯一：`fallback=()` 在本文件出现 2 次
        #    （I3.impairment 与 I5.cost），且两者之间夹着 source_ref 与注释行。
        anchor='            fallback=(),\n            name_keywords=("其他非流动资产",),',
        replacement='            fallback=("1911",),\n            name_keywords=("其他非流动资产",),',
        expect_test="test_i5_fallback_is_empty_tuple",
    ),
    # ── P8：预设 sheet 名存在于源模板 ──────────────────────────────────────
    Mutation(
        prop="P8",
        title="把审定表 tab 名改回不存在的「审定表I1-1」",
        target=_FIX / "fix_i_cycle_prefill_presets.py",
        anchor='("I1", "附注披露信息（上市公司）"): (',
        replacement='("I1", "附注披露信息（上市公司）不存在的后缀"): (',
        expect_test="test_registry_sheets_are_real_tabs",
    ),
    # ── P9：预设科目码与公式自洽 ───────────────────────────────────────────
    Mutation(
        prop="P9",
        title="删掉一条披露 sheet 的处置登记（12 条变 11 条）",
        target=_FIX / "fix_i_cycle_prefill_presets.py",
        anchor='    ("I2", "附注披露（国有企业）"): "54 格全部引用 `明细表I2-2`，结构同上市版（少「资本化依据」续表）。",',
        replacement="",
        expect_test="test_registry_count_anchor",
    ),
    # ── P15：附注列元数据齐备 + 无段落泄漏成表名 ────────────────────────────
    Mutation(
        prop="P15",
        title="把 I5 第 2 张表名改回 90 字符的段落泄漏名",
        target=_FIX / "fix_note_i_cycle_structure.py",
        anchor='_I5_TABLE2_NAME = "合同取得成本"',
        # 🔴 **不能**写成 `_I5_TABLE2_NAME = _I5_TABLE2_LEAKED_NAME`：后者定义在前者
        #    **之后**，会触发 NameError 让整个模块导入失败 ⇒ 测试全部 error 而非
        #    「打红预期那条」，差集里找不到 expect_test、被误判成 GREEN（首轮踩到）。
        #    改为直接写泄漏名字面量。
        replacement=(
            '_I5_TABLE2_NAME = ("[披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、"\n'
            '    "该资产的摊销方法、按该资产主要类别披露的期末账面价值以及本期确认的摊销及"\n'
            '    "减值损失金额等。例如：")'
        ),
        # 🔴 首轮该条判 GREEN —— 既有「表名不得以 `[` 开头 / 超长」判据读的是**模板 JSON**，
        #    改脚本常量不重跑脚本 JSON 不变；而 `--check` 比对的两侧**都由同一常量推导**，
        #    改了常量两边一起变、仍自洽（自洽性判据的固有盲区：只保证两侧一致、
        #    不保证两侧都对）。已补 3 条直接对**脚本常量**断言形态的判据。
        expect_test="test_fix_script_table_name_constants_are_not_paragraphs",
    ),
    # ── P16：列真源三向一致 ───────────────────────────────────────────────
    Mutation(
        prop="P16",
        title="I1 类别 label 改错字（源 xlsx ↔ 声明 ↔ 列头三向断链）",
        target=_FT / "i1_asset_categories.py",
        anchor='label="矿产权",',
        replacement='label="采矿权",',
        expect_test="test_i1_category_labels_match_source_template",
    ),
    # ── P17：flat 两处都加 ───────────────────────────────────────────────
    Mutation(
        prop="P17",
        title="I5 上市披露列去掉 group 分组（两级表头退化成单级）",
        target=_CB / "i5DisclosureSyncPayload.ts",
        anchor="group: '期末数'",
        replacement="flat: true",
        expect_test="两级 7 列",
        suite="frontend",
        allow_first=True,
    ),
    # ── P18：I1 上市列集与源模板一致 ───────────────────────────────────────
    Mutation(
        prop="P18",
        title="I1 类别 seq 打乱（披露主表列序与源模板行序脱钩）",
        target=_FT / "i1_asset_categories.py",
        anchor="        priority=90,\n        seq=9,",
        replacement="        priority=90,\n        seq=1,",
        expect_test="test_i1_listed_header_middle_equals_category_labels",
    ),
    # ── P21：动态可扩行数量与源模板一致 ────────────────────────────────────
    Mutation(
        prop="P21",
        title="I1 国企四层砍成三层（源模板 4 处可扩位对不上）",
        target=_CB / "i1SoeDisclosureModel.ts",
        anchor="  carrying: { title: '四、账面价值合计', movementNa: true },",
        replacement="",
        expect_test="四层",
        suite="frontend",
    ),
    Mutation(
        prop="P21",
        title="I2 按性质默认行删一条（六类变五类）",
        target=_CB / "i2DisclosureModel.ts",
        anchor="  '外购在研项目',",
        replacement="",
        expect_test="费用性质",
        suite="frontend",
        allow_first=True,
    ),
    # ── P23：动态行 key 不复用已删序号 ─────────────────────────────────────
    Mutation(
        prop="P23",
        title="国企自定义 key 去掉单调计数器（复用已删序号）",
        target=_CB / "i1SoeDisclosureModel.ts",
        anchor="Math.max(maxI1SoeCustomSeq(layers), seqFloor) + 1",
        replacement="maxI1SoeCustomSeq(layers) + 1",
        expect_test="单调",
        suite="frontend",
    ),
    Mutation(
        prop="P23",
        title="I1 上市列 key 改用中文 label（会撞键）",
        target=_CB / "i1CategoryScope.ts",
        anchor="return `${slot.key}_${slot.seq}`",
        replacement="return `${slot.label}`",
        expect_test="key",
        suite="frontend",
    ),
    # ── X1：附注同步 URL 契约（跨域附加守卫，非 design.md Property） ──────────
    # 本 spec 修正了 disclosureSyncUrlContract.spec.ts 的判据缺陷：旧判据写
    #   if (!line.includes('/api/') || !line.includes('disclosure-notes')) return
    # 要求被检行**自带 `disclosure-notes`** 才检查 ⇒ 走错端点的调用（实测存量 15 个
    # M/J 文件写成 `/api/workpapers/${props.wpId}/sync-from-workpaper`，后端无此路由
    # 必 404，且调用点包在 `catch { /* fail-open */ }` 里 ⇒ 「同步到附注」静默全失效）
    # 恰恰不含 `disclosure-notes`，被整条放过、守卫恒绿。
    # 本变异把一个已修好的 canonical URL 改回坏形态，新判据必须打红。
    Mutation(
        prop="X1",
        title="M1 国企披露同步 URL 改回坏形态 /api/workpapers/{wpId}/sync-from-workpaper（后端无此路由）",
        target=_WPC / "m1" / "core" / "M1TabDisclosureSoe.vue",
        anchor="`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`",
        replacement="`/api/workpapers/${props.wpId}/sync-from-workpaper`",
        expect_test="canonical",
        suite="frontend",
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# 执行
# ─────────────────────────────────────────────────────────────────────────────


def _env() -> dict[str, str]:
    """子进程环境：强制 UTF-8（Windows 上不设会把中文输出腌成乱码）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _run_backend() -> set[str]:
    """跑后端 I 循环守卫，返回失败测试名集合（参数用列表，不经 shell）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *_BE_PATHS, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=_env(),
    )
    return set(re.findall(r"^FAILED\s+\S+::(\S+)", proc.stdout, re.MULTILINE))


def _run_frontend() -> set[str]:
    """跑前端 I 循环守卫，返回失败用例全名集合。"""
    out = _FE / ".vitest-mutate-i-cycle.json"
    subprocess.run(
        ["npx.cmd", "vitest", "run", *_FE_SPECS, "--reporter=json", f"--outputFile={out.name}"],
        cwd=str(_FE), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=_env(),
    )
    failed: set[str] = set()
    if out.exists():
        try:
            import json

            data = json.loads(out.read_text(encoding="utf-8"))
            for res in data.get("testResults", []):
                for a in res.get("assertionResults", []):
                    if a.get("status") == "failed":
                        failed.add(a.get("fullName") or a.get("title") or "?")
        except Exception as exc:  # noqa: BLE001
            failed.add(f"<解析失败 {exc}>")
        # vitest 可能仍持句柄（WinError 32）→ 重试删除
        for _ in range(10):
            try:
                out.unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.3)
    return failed


def _run(suite: str) -> set[str]:
    return _run_backend() if suite == "backend" else _run_frontend()


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def restore_all() -> int:
    """还原全部 `.mutbak`（脚本被中断后手工调用）。"""
    baks = sorted(_ROOT.rglob(f"*{_BAK_SUFFIX}"))
    if not baks:
        print("无 .mutbak 待还原")
        return 0
    for bak in baks:
        target = bak.with_suffix("")
        # 目标名 = 去掉 .mutbak 后缀（原文件可能本就有后缀，故用字符串裁剪）
        target = Path(str(bak)[: -len(_BAK_SUFFIX)])
        target.write_bytes(bak.read_bytes())
        bak.unlink()
        print(f"已还原 {target.relative_to(_ROOT)}")
    return 0


def apply_one(m: Mutation, baseline: dict[str, set[str]]) -> tuple[str, str]:
    """施加单个变异并判定四态；无论成败都还原 + md5 核验。"""
    target = m.target
    if not target.exists():
        return "ANCHOR-MISS", f"被测文件不存在 {target}"

    original = target.read_bytes()
    n = target.read_text(encoding="utf-8").count(m.anchor)
    if n == 0 or (n != 1 and not m.allow_first):
        return "ANCHOR-MISS", f"锚点命中 {n} 次（须恰好 1；本条 allow_first={m.allow_first}）"

    bak = Path(str(target) + _BAK_SUFFIX)
    bak.write_bytes(original)
    before_md5 = _md5(target)
    try:
        text = target.read_text(encoding="utf-8")
        target.write_text(text.replace(m.anchor, m.replacement, 1), encoding="utf-8")
        mutated = _run(m.suite)
    finally:
        target.write_bytes(original)
        after_md5 = _md5(target)
        assert after_md5 == before_md5, (
            f"{m.prop} 还原失败！md5 {after_md5} != {before_md5}，备份仍在 {bak}"
        )
        bak.unlink(missing_ok=True)

    new_failed = mutated - baseline[m.suite]
    if not new_failed:
        return "GREEN", "无新增失败 ⇒ 守卫未打红，判据有缺陷"
    if any(m.expect_test in f for f in new_failed):
        extra = [f for f in new_failed if m.expect_test not in f]
        return "RED", f"另有连带打红 {len(extra)} 条" if extra else "精确命中"
    sample = sorted(new_failed)[:2]
    return "WRONG-TEST", f"新增失败但非预期项：{sample}"


def main() -> int:
    ap = argparse.ArgumentParser(description="I 循环守卫变异检验")
    ap.add_argument("--only", help="只跑指定 Property（逗号分隔，如 P1,P6）")
    ap.add_argument("--list", action="store_true", help="只列变异清单")
    ap.add_argument("--restore", action="store_true", help="还原全部 .mutbak 后退出")
    args = ap.parse_args()

    if args.restore:
        return restore_all()

    picked = MUTATIONS
    if args.only:
        want = {x.strip().upper() for x in args.only.split(",") if x.strip()}
        picked = tuple(m for m in MUTATIONS if m.prop.upper() in want)
        if not picked:
            print(f"--only {args.only} 未匹配任何变异")
            return 2

    covered = sorted({m.prop for m in MUTATIONS}, key=lambda x: int(x[1:]))
    print(f"变异总数 {len(MUTATIONS)}，覆盖 Property {covered}")
    if args.list:
        for m in MUTATIONS:
            print(f"  {m.prop:<4} [{m.suite:<8}] {m.title}")
            print(f"        target={m.target.relative_to(_ROOT)}  expect={m.expect_test!r}")
        return 0

    stale = sorted(_ROOT.rglob(f"*{_BAK_SUFFIX}"))
    if stale:
        print(f"🔴 发现残留备份 {[str(p.relative_to(_ROOT)) for p in stale]}")
        print("   先跑 --restore 还原，再重新执行")
        return 1

    suites = sorted({m.suite for m in picked})
    baseline: dict[str, set[str]] = {}
    for s in suites:
        baseline[s] = _run(s)
        print(f"基线[{s}] 失败 {len(baseline[s])} 条"
              + (f"：{sorted(baseline[s])[:3]}…" if baseline[s] else "（全绿）"))
    print("  ↑ 判定用**差集**，基线有红不影响结论\n")

    verdicts: list[tuple[Mutation, str, str]] = []
    for i, m in enumerate(picked, 1):
        print(f"[{i}/{len(picked)}] {m.prop} {m.title} …", flush=True)
        verdict, note = apply_one(m, baseline)
        verdicts.append((m, verdict, note))
        print(f"        → {verdict}  {note}")

    print("\n" + "=" * 78)
    print("变异检验结论")
    print("=" * 78)
    bad = 0
    for m, v, note in verdicts:
        if v != "RED":
            bad += 1
        print(f"{'OK ' if v == 'RED' else 'XX '}{m.prop:<4} {m.title[:40]:<42} {v:<12} {note}")

    print()
    for s in suites:
        post = _run(s)
        drift = post - baseline[s]
        print(f"恢复后[{s}]：新增失败 {len(drift)} 条 {sorted(drift)[:3] if drift else '(无残留污染)'}")
        if drift:
            bad += 1
    print(f"\n非 RED 数 = {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
