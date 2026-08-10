"""mutate_h_cycle_guards — H 循环守卫变异检验（改一字看是否变红，然后还原）

Spec: `.kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/` Task 17
（Requirements 11.1 ~ 11.4）

## 为什么需要它

本 spec 的守卫大量是**读源码型**断言（跨前后端交叉锁死 / 登记表双向锁死 /
源 docx 三向比对）。这类守卫最常见的失效方式不是「写错」而是「**空转**」——
正则不命中、解析器把真实内容截成空串、判据字面量写错，都会让守卫**全绿**
而实际什么都没测。全绿本身证明不了任何事，只有「注入缺陷 → 必须变红」能证明。

平台已多次实测到「守卫全绿但缺陷在位」（memory §踩坑铁律）：
- `toContain('<Foo')` 被 `<FooREMOVED` 骗过
- 固定字符窗口截函数体溢出到下一个函数
- `src.index('[')` 命中类型注解里的 `string[]`
- 只断言标识符存在，挡不住把条件改成 `if False:`

## 三态判定（缺一即漏判）

=============  ==========================================================
结果            含义
=============  ==========================================================
``RED``         注入后出现**新增**失败测试 ⇒ 守卫有效
``GREEN``       注入后失败集合不变 ⇒ **守卫缺陷**（或该变异无效，须自行确认）
``ANCHOR-MISS`` 锚点未命中或命中多行 ⇒ **脚本缺陷**，变异根本没施加
=============  ==========================================================

🔴 ``ANCHOR-MISS`` 既不是 RED 也不是 GREEN。把它当 GREEN 处理会漏掉守卫缺陷；
当 RED 处理会让「其实没做变异」冒充「守卫有效」。

## 判据 = 失败**测试名集合**的差集，不是退出码

本 spec 的守卫里有 skip、有连库条件跳过，`rc` 在多种情形下都是非零；
且 Wave 1 的「先打红」范式让 baseline 本身可能有红。故一律：

    new_failures = failures(mutated) - failures(baseline)

``new_failures`` 非空才算 RED。同时报告 ``resolved``（baseline 红转绿）——
它是「修好后守卫会转绿」的独立证据。

## 安全性

- 备份落**磁盘** ``<file>.bak_<id>``（只在内存会因 Ctrl+C 中断留下变异残留 ——
  平台实测踩过一次，让下一轮脚本把变异态当成原文基线）
- ``try/finally`` 无条件还原 + **md5 逐字节核验**
- ``--restore`` 单独提供：中断后可一键清残留
- **不碰共享热点数据文件**（``note_template_*.json`` / ``prefill_formula_mapping.json``
  正被并发会话高频改写）⇒ 政策章那条改的是**幂等脚本的规则常量**，
  让 ``--check`` 报欠账从而让守卫变红，一行数据都不动

用法::

    python backend/scripts/diagnose/mutate_h_cycle_guards.py
    python backend/scripts/diagnose/mutate_h_cycle_guards.py --only M3 M4
    python backend/scripts/diagnose/mutate_h_cycle_guards.py --restore
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND = REPO_ROOT / "audit-platform" / "frontend"

_LINES: list[str] = []


def log(s: str = "") -> None:
    _LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:  # pragma: no cover - GBK 控制台兜底
        print(s.encode("ascii", "replace").decode("ascii"), flush=True)


# ───────────────────────────── 测试目标组 ─────────────────────────────

BE_DUAL = "be_dual"
BE_PREFILL = "be_prefill"
BE_POLICY = "be_policy"
FE_SCOPE = "fe_scope"
FE_AMOUNT = "fe_amount"
FE_AGING = "fe_aging"
FE_H5 = "fe_h5"

#: 组 → (是否前端, 测试路径列表)
TARGET_GROUPS: dict[str, tuple[bool, tuple[str, ...]]] = {
    BE_DUAL: (False, (
        "backend/tests/four_table/test_dual_family_codes.py",
        "backend/tests/four_table/test_dual_family_mirror.py",
        "backend/tests/test_h_cycle_preset_account_coherence.py",
    )),
    BE_PREFILL: (False, (
        "backend/tests/four_table/test_h_cycle_adjudication_prefill.py",
    )),
    BE_POLICY: (False, (
        "backend/tests/test_note_h_policy_chapter_structure.py",
    )),
    FE_SCOPE: (True, (
        "src/components/workpaper/composables/__tests__/hCycleAccountScope.spec.ts",
    )),
    FE_AMOUNT: (True, (
        "src/components/workpaper/__tests__/hCycleAmountControl.spec.ts",
    )),
    FE_AGING: (True, (
        "src/components/workpaper/__tests__/hCycleNoAgingEnum.spec.ts",
    )),
    FE_H5: (True, (
        "src/components/workpaper/h5/__tests__/h5ListedNotApplicable.spec.ts",
        "src/components/workpaper/composables/__tests__/h5NoteSectionMap.spec.ts",
        "src/components/workpaper/composables/__tests__/hDisclosureAiWiring.spec.ts",
    )),
}


# ───────────────────────────── 变异定义 ─────────────────────────────


@dataclass(frozen=True)
class Mutation:
    """一个行级变异。

    :param mid: 编号（报告与 ``--only`` 用）
    :param what: 注入的缺陷是什么（用户视角）
    :param rel: 目标文件（仓库相对路径）
    :param anchor: 锚点**整行**（去尾部空白后精确相等，必须命中恰好 1 行）
    :param new_line: 替换后的整行
    :param groups: 应当变红的测试组
    """

    mid: str
    what: str
    rel: str
    anchor: str
    new_line: str
    groups: tuple[str, ...] = field(default_factory=tuple)


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        mid="M1",
        what="双族退回单族：使用权资产原值去掉 alternate 族 1651（真实库上只能取到 0.04%）",
        rel="backend/app/services/four_table/dual_family_codes.py",
        anchor='        alternate="1651",',
        new_line="        alternate=None,",
        groups=(BE_DUAL, FE_SCOPE),
    ),
    Mutation(
        mid="M2",
        what="双族槽映射串味：H9 的租赁负债槽指向使用权资产（docstring 明确警告的陷阱）",
        rel="backend/app/services/four_table/dual_family_codes.py",
        anchor='    ("H9", "gross"): "lease_liability",',
        new_line='    ("H9", "gross"): "gross",',
        groups=(BE_DUAL, FE_SCOPE),
    ),
    Mutation(
        mid="M3",
        what="后端兜底码退回字面量单族（前端三向锁死若只认字面形态就会静默放行）",
        rel="backend/app/services/four_table/h8_account_scope.py",
        anchor="            fallback_standard_codes=_GROSS_CODES,",
        new_line='            fallback_standard_codes=("1641",),',
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M4",
        what="前端注册表退回单族（render 未下发 tb_source_codes 时按单族查 ⇒ 取不到新族项目）",
        rel="audit-platform/frontend/src/components/workpaper/composables/hCycleAccountScope.ts",
        anchor="    gross: ['1641', '1651'],",
        new_line="    gross: ['1641'],",
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M5",
        what="金额控件登记表塞空理由（登记表退化成逃逸阀）",
        rel="audit-platform/frontend/src/components/workpaper/composables/hCycleAmountControlRegistry.ts",
        anchor="    '源模板列头「本期利息资本化率%」—— 利率类，不加千分符、不强制两位小数',",
        new_line="    '',",
        groups=(FE_AMOUNT,),
    ),
    Mutation(
        mid="M6",
        what="库龄分段常量改名含 AGING（诱导后来者统一到平台账龄枚举 —— 裁决 2 要防的正是这个）",
        rel="audit-platform/frontend/src/components/workpaper/h4/core/H4TabDetail.vue",
        anchor="const STOCK_AGE_OPTS = ['1年以内', '1-2年', '2-3年', '3年以上']",
        new_line="const AGING_OPTS = ['1年以内', '1-2年', '2-3年', '3年以上']",
        groups=(FE_AGING,),
    ),
    Mutation(
        mid="M7",
        what="审定表预填去掉 found 闸（科目不存在时凭空造 0 行）",
        rel="backend/app/services/four_table/h_cycle_adjudication_prefill.py",
        anchor='        if not slot or not getattr(slot, "found", False):',
        new_line="        if not slot:",
        groups=(BE_PREFILL,),
    ),
    Mutation(
        mid="M8",
        what="政策章补表规则被改名（幂等脚本 --check 应报欠账 ⇒ 守卫变红）",
        rel="backend/scripts/fix/fix_note_h_policy_chapter_structure.py",
        anchor='        "name": "生产性生物资产",',
        new_line='        "name": "生产性生物资产（改名探针）",',
        groups=(BE_POLICY,),
    ),
    Mutation(
        mid="M9",
        what="给 H5_NOTE_SECTION 加 listed 键（上市侧本无附注落点，加了就会下发虚构章节号）",
        rel="audit-platform/frontend/src/components/workpaper/composables/h5NoteSectionMap.ts",
        anchor="export const H5_NOTE_SECTION = { soe: '八、25' } as const",
        new_line="export const H5_NOTE_SECTION = { soe: '八、25', listed: '五、油气资产' } as const",
        groups=(FE_H5,),
    ),
    # ── 以下 5 条覆盖 Task 18 浏览器实测新增的守卫（防新断言空转）─────────────
    Mutation(
        mid="M10",
        what="溯源面板取数公式退回单族（真实库 5 个项目上只覆盖金额的 0.04%）",
        rel="audit-platform/frontend/src/components/workpaper/composables/hiExtractionSegments.ts",
        anchor="  return codes.map((c) => `TB('${c}','${column}')`).join('+')",
        new_line="  return `TB('${codes[0]}','${column}')`",
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M11",
        what="宿主不给审定表传 :html-data（TB 核对整块退化成本表口径 —— 实测的 P0-b）",
        rel="audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue",
        anchor='            :html-data="props.htmlData"',
        new_line="",
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M12",
        what="TB 核对形参退回含错码的键名（旧键 cost1901/dep1902/impair1903 零生产者 = dead prop）",
        rel="audit-platform/frontend/src/components/workpaper/composables/useH8Adjudication.ts",
        anchor="  tbUnadjusted?: Ref<{ cost: number; dep: number; impair?: number }>",
        new_line="  tbUnadjusted?: Ref<{ cost1901: number; dep1902: number; impair1903?: number }>",
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M13",
        what="H9 序时账退回写死 2205（合同负债 D7 域 —— 实测的 P0-d）",
        rel="audit-platform/frontend/src/components/workpaper/composables/h9LedgerPull.ts",
        anchor="export const H9_LEDGER_ACCOUNT_CODES: readonly string[] = h9Scope.def.slotFallbacks.gross",
        new_line="export const H9_LEDGER_ACCOUNT_CODES: readonly string[] = ['2205']",
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M14",
        what="审定表读 tb_values 的键名改错（render 真下发的是 rou_asset_unadjusted）",
        rel="audit-platform/frontend/src/components/workpaper/h8/core/H8TabAdjudication.vue",
        anchor="    cost: num('rou_asset_unadjusted'),",
        new_line="    cost: num('cost1901_unadjusted'),",
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M15",
        what="宿主全局 TB 告警文案退回写死 1901（待处理财产损溢 —— 浏览器上直接展示给审计师）",
        rel="audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue",
        anchor="          ≠ 试算平衡表({{ tbReconcileCodeText }}净额) {{ tbAuditedRou?.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}，",
        new_line="          ≠ 试算平衡表(1901净额) {{ tbAuditedRou?.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}，",
        groups=(FE_SCOPE,),
    ),
    Mutation(
        mid="M16",
        what="H9 TB 字段名退回内嵌错码（`unadjusted2205`，`\\b` 判据抓不到）",
        rel="audit-platform/frontend/src/components/workpaper/composables/useH9FormData.ts",
        anchor="  unadjustedLeaseLiability: number",
        new_line="  unadjusted2205: number",
        groups=(FE_SCOPE,),
    ),
)


# ───────────────────────────── 跑测试 ─────────────────────────────


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


_PYTEST_FAILED = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)
_PYTEST_ERROR = re.compile(r"^ERROR\s+(\S+)", re.MULTILINE)


def run_backend(paths: tuple[str, ...]) -> tuple[set[str], int]:
    """跑后端 pytest，返回 (失败/错误测试名集合, 收集到的用例总数)。"""
    cmd = ["python", "-m", "pytest", *paths, "-q", "--tb=no", "-rf",
           "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, env=_env(),
                          encoding="utf-8", errors="replace", timeout=1800)
    out = proc.stdout + proc.stderr
    fails = set(_PYTEST_FAILED.findall(out)) | {f"ERROR::{x}" for x in _PYTEST_ERROR.findall(out)}
    m = re.search(r"(\d+) passed", out)
    collected = int(m.group(1)) if m else 0
    return fails, collected


def run_frontend(paths: tuple[str, ...]) -> tuple[set[str], int]:
    """跑前端 vitest（JSON reporter），返回 (失败测试名集合, 通过数)。

    🔴 必须用 JSON reporter：``FAIL`` 行会按控制台宽度折行，正则抓失败名恒 0 命中，
    平台实测曾因此让 6 个变异全部误判成 GREEN。
    """
    with tempfile.TemporaryDirectory() as td:
        out_json = Path(td) / "vitest.json"
        cmd = ["npx", "vitest", "run", *paths, "--reporter=json",
               f"--outputFile={out_json}"]
        subprocess.run(" ".join(f'"{c}"' if " " in c else c for c in cmd),
                       cwd=str(FRONTEND), capture_output=True, env=_env(),
                       encoding="utf-8", errors="replace", timeout=1800, shell=True)
        if not out_json.exists():
            return {"__NO_JSON_OUTPUT__"}, 0
        data = json.loads(out_json.read_text(encoding="utf-8"))
    fails: set[str] = set()
    for tr in data.get("testResults", []):
        if tr.get("message"):
            fails.add(f"FILE::{Path(str(tr.get('name', '?'))).name}")
        for a in tr.get("assertionResults", []):
            if a.get("status") == "failed":
                fails.add(str(a.get("fullName") or a.get("title")))
    return fails, int(data.get("numPassedTests") or 0)


def run_group(group: str) -> tuple[set[str], int]:
    is_fe, paths = TARGET_GROUPS[group]
    return run_frontend(paths) if is_fe else run_backend(paths)


# ───────────────────────────── 文件读写 ─────────────────────────────


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _backup_path(p: Path, mid: str) -> Path:
    return p.with_name(p.name + f".bak_{mid}")


def apply_mutation(mu: Mutation) -> tuple[Path, str] | None:
    """行级注入。返回 (文件, 原始 md5)；锚点不唯一返回 None。"""
    p = REPO_ROOT / mu.rel
    if not p.exists():
        log(f"  [ANCHOR-MISS] 文件不存在: {mu.rel}")
        return None
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    # 行尾无关：按 splitlines 定位，写回时保留原行尾
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    target = mu.anchor.rstrip()
    hits = [i for i, l in enumerate(lines) if l.rstrip() == target]
    if len(hits) != 1:
        log(f"  [ANCHOR-MISS] 锚点命中 {len(hits)} 行（要求恰好 1）: {mu.anchor[:70]!r}")
        return None
    before = _md5(p)
    _backup_path(p, mu.mid).write_bytes(raw)
    lines[hits[0]] = mu.new_line
    p.write_bytes(newline.join(lines).encode("utf-8"))
    return p, before


def restore(p: Path, mid: str, expect_md5: str) -> bool:
    bak = _backup_path(p, mid)
    if not bak.exists():
        log(f"  [WARN] 备份不存在，无法还原: {bak.name}")
        return False
    p.write_bytes(bak.read_bytes())
    bak.unlink()
    ok = _md5(p) == expect_md5
    if not ok:
        log(f"  [ERR] 还原后 md5 不符: {p.name}")
    return ok


def restore_all_leftovers() -> int:
    """清理中断留下的 ``*.bak_M*`` 残留。"""
    n = 0
    for mu in MUTATIONS:
        p = REPO_ROOT / mu.rel
        bak = _backup_path(p, mu.mid)
        if bak.exists():
            p.write_bytes(bak.read_bytes())
            bak.unlink()
            log(f"  [RESTORED] {mu.rel} <- {bak.name}")
            n += 1
    return n


# ───────────────────────────── 主流程 ─────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="H 循环守卫变异检验")
    ap.add_argument("--only", nargs="*", default=None, help="只跑指定编号，如 M3 M4")
    ap.add_argument("--restore", action="store_true", help="只清理 .bak_M* 残留")
    ap.add_argument("--out", default=None, help="报告落盘路径")
    args = ap.parse_args()

    if args.restore:
        n = restore_all_leftovers()
        log(f"[OK] 清理 {n} 个残留备份")
        return 0

    leftovers = restore_all_leftovers()
    if leftovers:
        log(f"[INFO] 开跑前先清掉 {leftovers} 个上次中断留下的变异残留")

    todo = [m for m in MUTATIONS if not args.only or m.mid in set(args.only)]
    if not todo:
        log("[ERR] --only 未匹配任何变异")
        return 2

    needed = sorted({g for m in todo for g in m.groups})
    log("=" * 78)
    log("H 循环守卫变异检验")
    log("=" * 78)
    log("")
    log("[1/2] 采集 baseline 失败集合")
    baseline: dict[str, set[str]] = {}
    for g in needed:
        fails, passed = run_group(g)
        baseline[g] = fails
        log(f"  {g:<12} passed={passed:<5} baseline_failures={len(fails)}")
        for f in sorted(fails):
            log(f"      (baseline red) {f}")
    log("")
    log("[2/2] 逐个注入")

    results: list[tuple[str, str, str]] = []
    for mu in todo:
        log("")
        log(f"--- {mu.mid} {mu.what}")
        log(f"    file: {mu.rel}")
        applied = apply_mutation(mu)
        if applied is None:
            results.append((mu.mid, "ANCHOR-MISS", ""))
            continue
        p, before = applied
        verdict, detail = "GREEN", ""
        try:
            new_all: set[str] = set()
            resolved_all: set[str] = set()
            for g in mu.groups:
                fails, _passed = run_group(g)
                new_all |= fails - baseline[g]
                resolved_all |= baseline[g] - fails
            if new_all:
                verdict = "RED"
                detail = f"新增失败 {len(new_all)} 条"
                for f in sorted(new_all)[:6]:
                    log(f"    [RED] {f}")
            else:
                log("    [GREEN] 失败集合无变化 —— 守卫缺陷，或该变异未真正改变被测属性")
            if resolved_all:
                log(f"    [note] baseline 红转绿 {len(resolved_all)} 条（该断言不是死断言）")
        finally:
            ok = restore(p, mu.mid, before)
            log(f"    RESTORED same_as_baseline={ok}")
        results.append((mu.mid, verdict, detail))

    log("")
    log("=" * 78)
    red = sum(1 for _, v, _ in results if v == "RED")
    miss = sum(1 for _, v, _ in results if v == "ANCHOR-MISS")
    for mid, verdict, detail in results:
        log(f"  {mid:<4} {verdict:<12} {detail}")
    log(f"总计 {red}/{len(results)} RED；ANCHOR-MISS {miss}")
    log("=" * 78)

    if args.out:
        Path(args.out).write_text("\n".join(_LINES), encoding="utf-8")

    # ANCHOR-MISS 与 GREEN 都视为失败（前者脚本缺陷，后者守卫缺陷）
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
