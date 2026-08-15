#!/usr/bin/env python
"""G7 列对齐守卫的**变异检验**（只读式破坏 + 字节级还原）。

## 为什么需要它

守卫「全绿」有两种可能：判据真的在保护代码，或判据根本抓不到东西（假绿）。
平台已记的三类假绿成因里，第二类正是「grep 式守卫只查字符串存在」——
把被保护的实现改成 `if False:` / 删调用 / 改名残留，守卫仍绿。

本脚本对每个锚点**故意改坏一处**，跑对应守卫，看它是否**打红且打红的正是预期那条**。

## 🔴 四态判定（只看 exit code 会把后三态误判成 RED）

======  ============================================================
RED     打红，且新增失败里含预期测试名 ⇒ 判据有效
GREEN   没打红 ⇒ **守卫缺陷**（判据抓不到这个改动）
MISS    锚点未命中或命中 >1 ⇒ **本脚本缺陷**（不是代码没问题）
WRONG   打红了但新增失败不含预期测试名 ⇒ 污染残留或锚点错行
======  ============================================================

判定按**失败测试名集合差集** ``new_fails = fails_after - fails_baseline``，
不看 exit code —— 工作树里存在并发会话引入的预存在失败（实测 K 循环 1 例），
按 exit code 判会把它算成「我的变异打红了」。

## 🔴 三条实现铁律（都是踩过的坑）

1. **备份写 `.bak` 文件**，不只放内存：脚本被 Ctrl+C 中断时内存备份随进程消失，
   工作树会留下变异残留。配 ``--restore`` 可随时清理。
2. **还原用 `write_bytes` 字节级**：``write_text`` 在 Windows 会把 LF 转成 CRLF，
   导致「还原后文件与原始不逐字相等」的假 DIRTY。
3. **锚点必须是单行**：工作树多为 CRLF，含 ``\n`` 的跨行锚点在 `str.count` 下必 MISS。

前端变异跑 vitest 一律 ``--reporter=json --outputFile=<绝对路径>``：
控制台的 ``FAIL`` 行会按终端宽度折行，靠文本解析必漏。

用法::

    python backend/scripts/diagnose/mutate_g7_column_alignment_guards.py            # 全跑
    python backend/scripts/diagnose/mutate_g7_column_alignment_guards.py --only be  # 只跑后端
    python backend/scripts/diagnose/mutate_g7_column_alignment_guards.py --list     # 只列锚点
    python backend/scripts/diagnose/mutate_g7_column_alignment_guards.py --restore  # 清理 .bak

spec: .kiro/specs/g7-column-alignment-and-extraction-closure/ (Task 18, Property 37)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
ROOT = _BACKEND.parent
FRONTEND = ROOT / "audit-platform" / "frontend"

_BAK_SUFFIX = ".mutate-g7.bak"

#: 子进程环境：中文输出必须 UTF-8（GBK 控制台会让含 emoji 的脚本抛 UnicodeEncodeError）
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


# ─────────────────────────── 数据模型 ───────────────────────────


@dataclass(frozen=True)
class Mutation:
    """一个变异锚点。

    Attributes:
        name: 人类可读的变异名（报告用）。
        target: 被改坏的**生产/数据**文件（相对仓库根）。
        anchor: 要替换掉的**单行**文本（须在目标文件里恰好出现 1 次）。
        replacement: 替换成什么（空串 = 删掉该行内容）。
        expect_test: 预期打红的测试名片段（判 RED 用；空 = 只要有新增失败即算 RED）。
        suite: 跑哪个测试套（``be`` 后端 pytest / ``fe`` 前端 vitest）。
        selector: pytest 的路径/nodeid，或 vitest 的文件名过滤词。
    """

    name: str
    target: str
    anchor: str
    replacement: str
    expect_test: str
    suite: str
    selector: str


@dataclass
class Outcome:
    mutation: Mutation
    verdict: str = ""
    detail: str = ""
    new_fails: list[str] = field(default_factory=list)


# ─────────────────────────── 锚点登记 ───────────────────────────

_MODEL_LISTED = (
    "audit-platform/frontend/src/components/workpaper/"
    "g7-long-term-equity-main/disclosure/g7ListedDisclosureModel.ts"
)
_MODEL_SOE = (
    "audit-platform/frontend/src/components/workpaper/"
    "g7-long-term-equity-main/disclosure/g7SoeDisclosureModel.ts"
)
_PROJECTOR = "backend/app/services/note_sub_table_projector.py"
_FACTS = "backend/data/g7_column_source_facts.json"
_SLOT_COLS = "audit-platform/frontend/src/components/workpaper/composables/g7SlotColumns.ts"
_TAB_SOE = (
    "audit-platform/frontend/src/components/workpaper/"
    "g7-long-term-equity-main/disclosure/G7TabDisclosureSOE.vue"
)
_DIAG = "backend/scripts/diagnose/diagnose_g7_column_alignment.py"

_FE_THREE_WAY = "g7ColumnThreeWayAlignment"
_FE_SOE_MODEL = "g7SoeDisclosureModel"
_BE_FACTS = "backend/tests/four_table/test_g7_column_source_facts.py"

MUTATIONS: tuple[Mutation, ...] = (
    # ① 删一个 group —— A 类判据（运行时 vs seed 同名同跨度 + vs 源 段数跨度）
    Mutation(
        name="删一个 group（listed 分类表）",
        target=_MODEL_LISTED,
        anchor="function groupedCols(",
        replacement="function groupedCols_MUTATED(",
        expect_test="",  # 改函数名会让整文件挂掉 ⇒ 只要有新增失败即 RED
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ② 改一个 label 的全半角 —— D 类判据（逐字取源 xlsx，禁统一括号）
    Mutation(
        name="label 全半角改动（soe 认缴持股比例（%）→ (%)）",
        target=_MODEL_SOE,
        # 🔴 `认缴持股比例（%）` 在本文件出现 2 次（L215 与 L232），单靠它锚点必 MISS；
        #    用**同一行内的相邻列**（`paidInRatio` 实缴持股比例）把锚点收窄到唯一。
        anchor="  ['paidInRatio', '实缴持股比例（%）', 'percent', 130],",
        replacement="  ['paidInRatio', '实缴持股比例(%)', 'percent', 130],",
        expect_test="D 类",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ③ 标签列 key 改回中文 '项目' —— B 类判据 + 禁中文字面量当 key
    Mutation(
        name="标签列 key 改回中文 '项目'（listed）",
        target=_MODEL_LISTED,
        anchor="        { key: 'label', label: labelText, is_label: true, ...(hasGroup ? {} : { flat: true }) },",
        replacement="        { key: '项目', label: labelText, is_label: true, ...(hasGroup ? {} : { flat: true }) },",
        expect_test="B 类",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ④ 去掉 is_label —— 投影器靠它选标签列并跳过它算 group 索引
    Mutation(
        name="去掉 is_label（soe 标签列）",
        target=_MODEL_SOE,
        anchor="        { key: 'label', label: labelText, is_label: true, ...(hasGroup ? {} : { flat: true }) },",
        replacement="        { key: 'label', label: labelText, ...(hasGroup ? {} : { flat: true }) },",
        expect_test="is_label",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ⑤ 改 hasGroup 三元表达式 —— flat/group 互斥且不留 undefined 的结构性防回退
    Mutation(
        name="hasGroup 三元表达式写死（listed）",
        target=_MODEL_LISTED,
        anchor="      const hasGroup = columns.some(c => c.group)",
        replacement="      const hasGroup = true // MUTATED",
        expect_test="hasGroup",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ⑥ 篡改事实 JSON 一格 —— stale 检测（派生投影不得漂移）
    Mutation(
        name="篡改事实 JSON 的 source_sha256",
        target=_FACTS,
        anchor='    "two_level_rule": "横向合并（跨度>=2、值非空、起始列在标签列右侧）= 父表头",',
        replacement='    "two_level_rule": "MUTATED",',
        expect_test="",
        suite="be",
        selector=_BE_FACTS,
    ),
    # ⑦ 删投影器兜底分支 —— 标签列 key 改动零数据风险的前提
    Mutation(
        name="删投影器逆投影侧标签列兜底",
        target=_PROJECTOR,
        anchor='        out[label_key] = out["label"]',
        replacement="        pass  # MUTATED",
        expect_test="兜底",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ⑧ 动态列 key 改回写死序号 —— Property 13（禁回退成 c1Current/company1）
    Mutation(
        name="动态列 key 改回写死序号",
        target=_SLOT_COLS,
        anchor="      out.push({ key: `${slot}_${seq}`, seq, entityName, editable: true })",
        replacement="      out.push({ key: `company${seq}`, seq, entityName, editable: true })",
        expect_test="",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ⑨ 把 facts 的公式读取改成取值 —— Task 17 的 stale 探针会全体失效
    Mutation(
        name="源模板缺陷探针改成读值（data_only=True）",
        target=_BE_FACTS,
        anchor="    wb = load_workbook(mod.SRC_XLSX, data_only=False)",
        replacement="    wb = load_workbook(mod.SRC_XLSX, data_only=True)  # MUTATED",
        expect_test="test_probes_read_formulas_not_values",
        suite="be",
        selector=_BE_FACTS,
    ),
    # ⑩ 抽掉边① 的归一化 —— 证明 `_norm` 真的在被使用（不是死代码）
    Mutation(
        name="抽掉边① 的表头归一化（_norm 直接返回原文）",
        target=_DIAG,
        anchor='    return re.sub(r"[\\s\\u3000]+", "", str(text))',
        replacement="    return str(text)  # MUTATED",
        expect_test="",
        suite="be",
        selector=_BE_FACTS,
    ),
    # ⑪ 第四边（渲染层两级表头）：把分组渲染的门控写死为假
    #    —— 模板字样都还在、只是形态失效，正是 grep 式守卫会放过的形态。
    Mutation(
        name="国企 Tab 分组渲染门控写死（v-if=\"blk.group\" → false）",
        target=_TAB_SOE,
        anchor='<el-table-column v-if="blk.group" :label="blk.group" align="center">',
        replacement='<el-table-column v-if="false" :label="blk.group" align="center">',
        expect_test="两个 Tab 的模板都按分组渲染",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ⑫ 第四边：把共享分块实现的引用删掉（改回本地自造/扁平的第一步）
    Mutation(
        name="国企 Tab 去掉共享分块实现的 import",
        target=_TAB_SOE,
        anchor="import { buildG7HeaderBlocks, type G7HeaderBlock } from './g7DisclosureHeaderBlocks'",
        replacement="// MUTATED: import removed",
        expect_test="分块函数与单元格组件存在",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ⑬ 第四边：让一张**本该两级**的表在模型侧失去父表头
    #    （父分组名常量清空 ⇒ `groupedCols` 拿到空 group ⇒ 该表退化为单级）。
    #
    #    🔴 两次锚点/预期修正（都由判定四态当场抓出，记录以免重犯）：
    #    ① 初版锚点取 facts 的 `"expected_source_runs": 1` → `--list` 静态自检打红：
    #       该字符串在 facts 里命中 **4 次**（正是 4 张单槽豁免表），一次 replace 改 4 处、
    #       判定失去指向性。改用模型侧唯一的常量赋值行。
    #    ② 第二版打在 **soe** 模型的 `MOVEMENT_GROUP` 上，判定为 **WRONG**：打红的是前三边
    #       （A 类 / A源 类 / flat 表态），**不含**第四边。原因是那张表在 facts 里没有对应
    #       条目（`facts` 为 null ⇒ 第四边的逐表比对按设计跳过它），而前三边比的是
    #       runtime ↔ seed、不需要 facts ⇒ 先红。改打 **listed** 的同名常量：它对应
    #       facts `五、18 / 长期股权投资`（12 列、is_two_level=true），第四边必然覆盖。
    #
    #    另记：「两级表头张数锁死」只数**源侧**应两级的张数（锁的是源侧期望），
    #    运行时退化由「逐表：运行时是否给出父表头 == 源侧是否应两级」承担 —— 分工如此，
    #    故本条 expect_test 取后者。
    Mutation(
        name="上市「长期股权投资」丢父表头（MOVEMENT_GROUP 清空）",
        target=_MODEL_LISTED,
        anchor="const MOVEMENT_GROUP = '本期增减变动'",
        replacement="const MOVEMENT_GROUP = ''  // MUTATED",
        expect_test="运行时是否给出父表头",
        suite="fe",
        selector=_FE_THREE_WAY,
    ),
    # ⑭ 同步失败提示回退成 fail-open：真同步失败分支改回吞异常的裸 catch
    #    —— 这正是「已同步 128 行」与「同步附注失败」同时弹出的成因形态。
    Mutation(
        name="国企 Tab 同步失败分支回退成裸 catch（吞异常）",
        target=_TAB_SOE,
        anchor="    } catch (err: unknown) {\n      // 🔴 绝不吞异常",
        replacement="    } catch {\n      // MUTATED 绝不吞异常",
        expect_test="不再用裸 catch",
        suite="fe",
        selector=_FE_SOE_MODEL,
    ),
    # ⑮ 收尾失败又被说成「同步失败」（附注已落地却诱使重复写库）
    Mutation(
        name="国企 Tab 收尾失败改回「同步失败」文案",
        target=_TAB_SOE,
        anchor="      ElMessage.warning(describeSyncTailFailure(okText, err))",
        replacement="      ElMessage.warning('同步附注失败，请检查国企附注章节映射后重试')  // MUTATED",
        expect_test="分成两段 try",
        suite="fe",
        selector=_FE_SOE_MODEL,
    ),
)


# ─────────────────────────── 测试执行 ───────────────────────────


def _run_pytest(selector: str) -> set[str]:
    """跑 pytest，返回**失败测试名**集合（不看 exit code）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", selector, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(ROOT),
        env=ENV,
        capture_output=True,
        timeout=900,
    )
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    # `FAILED backend/tests/x.py::Class::test_name - msg`
    return set(re.findall(r"^FAILED\s+(\S+)", text, re.MULTILINE))


def _run_vitest(selector: str) -> set[str]:
    """跑 vitest，返回**失败测试全名**集合。

    🔴 必须走 ``--reporter=json --outputFile=<绝对路径>``：控制台的 FAIL 行会按
    终端宽度折行，正则解析必漏（平台已记）。
    """
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "vitest.json"
        subprocess.run(
            [
                "cmd", "/c",
                f"npx vitest run {selector} --reporter=json --outputFile={report} > NUL 2>&1",
            ],
            cwd=str(FRONTEND),
            env=ENV,
            timeout=900,
        )
        if not report.exists():
            # 报告都没生成 = 整个套挂了（如语法错），用哨兵表示「全套失败」
            return {"<vitest-report-missing>"}
        data = json.loads(report.read_text(encoding="utf-8"))
    fails: set[str] = set()
    for file_result in data.get("testResults", []):
        for assertion in file_result.get("assertionResults", []):
            if assertion.get("status") == "failed":
                fails.add(assertion.get("fullName") or assertion.get("title") or "?")
        # 文件级失败（收集期报错）也要计入，否则「整文件挂掉」会被当成 0 失败
        if file_result.get("status") == "failed" and not file_result.get("assertionResults"):
            fails.add(f"<file-failed>{Path(file_result.get('name', '?')).name}")
    return fails


def run_suite(mutation: Mutation) -> set[str]:
    return _run_vitest(mutation.selector) if mutation.suite == "fe" else _run_pytest(mutation.selector)


# ─────────────────────────── 备份 / 还原 ───────────────────────────


def _bak_path(target: Path) -> Path:
    return target.with_name(target.name + _BAK_SUFFIX)


def backup(target: Path) -> bytes:
    """写 `.bak` 文件（不只放内存）并返回原始字节。"""
    raw = target.read_bytes()
    _bak_path(target).write_bytes(raw)
    return raw


def restore(target: Path) -> bool:
    """从 `.bak` 字节级还原并删除 `.bak`。返回是否做了还原。"""
    bak = _bak_path(target)
    if not bak.exists():
        return False
    # 🔴 `write_bytes` 而非 `write_text`：后者在 Windows 会把 LF 转 CRLF ⇒ 假 DIRTY
    target.write_bytes(bak.read_bytes())
    bak.unlink()
    return True


def restore_all() -> list[str]:
    """清理全部残留 `.bak`（`--restore`）。"""
    done: list[str] = []
    for m in MUTATIONS:
        target = ROOT / m.target
        if restore(target):
            done.append(m.target)
    return done


# ─────────────────────────── 主流程 ───────────────────────────


def apply_mutation(target: Path, mutation: Mutation) -> str | None:
    """施加变异。返回 None 表示成功，否则返回 MISS 原因。"""
    text = target.read_text(encoding="utf-8")
    hits = text.count(mutation.anchor)
    if hits != 1:
        return f"锚点命中 {hits} 次（须恰 1）"
    target.write_text(text.replace(mutation.anchor, mutation.replacement), encoding="utf-8")
    return None


def run_one(mutation: Mutation, baselines: dict[str, set[str]]) -> Outcome:
    out = Outcome(mutation=mutation)
    target = ROOT / mutation.target
    if not target.exists():
        out.verdict = "MISS"
        out.detail = f"目标文件不存在：{mutation.target}"
        return out

    raw = backup(target)
    try:
        miss = apply_mutation(target, mutation)
        if miss:
            out.verdict = "MISS"
            out.detail = miss
            return out

        after = run_suite(mutation)
        base = baselines[mutation.suite + "|" + mutation.selector]
        new_fails = sorted(after - base)
        out.new_fails = new_fails

        if not new_fails:
            out.verdict = "GREEN"
            out.detail = "无新增失败 ⇒ 守卫抓不到这个改动"
        elif not mutation.expect_test:
            out.verdict = "RED"
            out.detail = f"新增失败 {len(new_fails)} 条"
        elif any(mutation.expect_test in f for f in new_fails):
            out.verdict = "RED"
            out.detail = f"新增失败 {len(new_fails)} 条，含预期「{mutation.expect_test}」"
        else:
            out.verdict = "WRONG"
            out.detail = f"新增失败不含预期「{mutation.expect_test}」：{new_fails[:3]}"
        return out
    finally:
        # 字节级还原 + 删 .bak；并核验确实还原干净
        target.write_bytes(raw)
        _bak_path(target).unlink(missing_ok=True)


def _selector_sources(mutation: Mutation) -> list[str]:
    """把 `selector` 解析成**测试源文件正文**列表（供 expect_test 定位）。

    - ``be``：selector 是 pytest 路径或 nodeid（可能带 ``::``），也可能是目录；
    - ``fe``：selector 是 vitest 的文件名过滤词，去前端 src 下按文件名包含匹配。
    """
    texts: list[str] = []
    if mutation.suite == "be":
        for part in mutation.selector.split():
            rel = part.split("::", 1)[0]
            path = ROOT / rel
            files = sorted(path.rglob("test_*.py")) if path.is_dir() else [path]
            for f in files:
                if f.is_file():
                    texts.append(f.read_text(encoding="utf-8", errors="replace"))
    else:
        for f in sorted((FRONTEND / "src").rglob("*.spec.ts")):
            if mutation.selector in f.name:
                texts.append(f.read_text(encoding="utf-8", errors="replace"))
    return texts


def verify_anchors(selected: list[Mutation]) -> list[str]:
    """`--list` 的静态自检：不执行变异，只校验这份登记表本身没腐烂。

    拦三类只在手工跑全量变异时才暴露的 stale（与平台既有
    `mutate_excel_io_guards.mjs --list` 同款取舍：真执行变异要临时改生产代码，
    不适合 CI 并发环境）：

    1. **锚点漂移**：生产代码重构后 anchor 不再命中（0 次）或命中多次
       （>1 次时 `replace` 会一次改多处，判定失去指向性）⇒ 手工跑会得 ANCHOR-MISS。
    2. **变异空操作**：`replacement == anchor`（改完与原文逐字相同）⇒ 必然假 GREEN，
       且会被误读成「守卫缺陷」。
    3. **测试名漂移**：`expect_test` 片段在对应测试源里已找不到 ⇒ 手工跑会得
       WRONG-TEST，或更坏：误配到另一条测试上，于是「看起来 RED」但钉的不是原意。
    """
    problems: list[str] = []
    for mutation in selected:
        target = ROOT / mutation.target
        if not target.is_file():
            problems.append(f"{mutation.name}: target 不存在 → {mutation.target}")
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        hits = text.count(mutation.anchor)
        if hits != 1:
            problems.append(
                f"{mutation.name}: anchor 在 {mutation.target} 命中 {hits} 次"
                f"（须恰好 1 次）→ {mutation.anchor[:64]!r}"
            )
        if mutation.replacement == mutation.anchor:
            problems.append(f"{mutation.name}: replacement 与 anchor 逐字相同 ⇒ 变异是空操作")
        if mutation.expect_test:
            sources = _selector_sources(mutation)
            if not sources:
                problems.append(
                    f"{mutation.name}: selector 找不到任何测试源 → {mutation.selector}"
                )
            elif not any(mutation.expect_test in s for s in sources):
                problems.append(
                    f"{mutation.name}: expect_test「{mutation.expect_test}」"
                    f"在 {mutation.selector} 的测试源里找不到 ⇒ 测试名漂移"
                )
    leftovers = [m.target for m in selected if _bak_path(ROOT / m.target).exists()]
    if leftovers:
        problems.append(f"残留 .bak（上次变异未复原）：{leftovers} —— 请跑 --restore")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G7 列对齐守卫变异检验（四态判定）")
    parser.add_argument("--only", choices=["be", "fe"], help="只跑后端或前端锚点")
    parser.add_argument("--list", action="store_true", help="只列锚点，不执行")
    parser.add_argument("--restore", action="store_true", help="清理残留 .bak 后退出")
    args = parser.parse_args(argv)

    if args.restore:
        done = restore_all()
        print(f"[restore] 还原 {len(done)} 个文件：{done}" if done else "[restore] 无残留 .bak")
        return 0

    selected = [m for m in MUTATIONS if not args.only or m.suite == args.only]

    if args.list:
        print(f"变异锚点 {len(selected)} 条：")
        for i, m in enumerate(selected, 1):
            print(f"  [{i:>2}] ({m.suite}) {m.name}")
            print(f"        target = {m.target}")
            print(f"        anchor = {m.anchor[:78]!r}")
        problems = verify_anchors(selected)
        print()
        if problems:
            print(f"🔴 静态自检 {len(problems)} 项不通过：")
            for msg in problems:
                print(f"  x {msg}")
            return 2
        print(f"✅ 静态自检通过：{len(selected)} 条锚点均命中恰好 1 次、"
              f"replacement 非空操作、expect_test 在测试源里可定位")
        return 0

    # 先跑各套基线（预存在失败要从判定里扣掉）
    baselines: dict[str, set[str]] = {}
    for m in selected:
        key = m.suite + "|" + m.selector
        if key not in baselines:
            print(f"[baseline] {key} ...", flush=True)
            baselines[key] = run_suite(m)
            n = len(baselines[key])
            print(f"[baseline] {key} 预存在失败 {n} 条"
                  + (f"：{sorted(baselines[key])[:3]}" if n else "（干净）"), flush=True)

    results: list[Outcome] = []
    for i, m in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {m.name} ...", flush=True)
        outcome = run_one(m, baselines)
        results.append(outcome)
        print(f"        {outcome.verdict}: {outcome.detail}", flush=True)

    print()
    print("=" * 88)
    print("变异检验结果（RED=判据有效 / GREEN=守卫缺陷 / MISS=脚本缺陷 / WRONG=污染或锚点错行）")
    print("=" * 88)
    tally = {"RED": 0, "GREEN": 0, "MISS": 0, "WRONG": 0}
    for outcome in results:
        tally[outcome.verdict] += 1
        print(f"[{outcome.verdict:<5}] ({outcome.mutation.suite}) {outcome.mutation.name}")
        print(f"         {outcome.detail}")
        for f in outcome.new_fails[:4]:
            print(f"         + {f}")
    print()
    print(f"合计 {len(results)} 条：" + "  ".join(f"{k}={v}" for k, v in tally.items()))

    # 残留自检：不得留下任何 .bak
    leftovers = [m.target for m in MUTATIONS if _bak_path(ROOT / m.target).exists()]
    if leftovers:
        print(f"🔴 残留 .bak：{leftovers} —— 请跑 --restore")
        return 2

    # 只有全 RED 才算通过；GREEN/MISS/WRONG 都必须处理
    return 0 if tally["RED"] == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
