# -*- coding: utf-8 -*-
"""程序裁剪智能化 — 守卫变异检验。

Feature: procedure-trimming-and-delegation-intelligence
Requirements: 14.3, 14.4, 14.7

用法::

    python backend/scripts/check/mutate_trim_decision_guards.py
    python backend/scripts/check/mutate_trim_decision_guards.py --only T10-1 T22-3
    python backend/scripts/check/mutate_trim_decision_guards.py --only-prefix T22
    python backend/scripts/check/mutate_trim_decision_guards.py --restore

两组变异共用同一台机器：

- ``T10-*``（16 条，Task 10 交付资产）—— 只跑后端 pytest。
- ``T22-*``（12 条，Task 22）—— **跨前后端**：同一条变异同时跑 pytest 与 vitest，
  失败名归一到**一个集合**后再求差集。tasks.md Task 22 未写这一点（它假定变异都落在
  后端），但 12 条里 10 条的被测实现是前端纯函数 / SFC，不跑 vitest 就等于不判。

═══ 判据（五态，缺一即误判）═══

按**失败测试名集合求差集**判定，**不看退出码** —— 本 spec 的守卫按「先打红」范式交付，
基线本身就有红（实测：后端 0 红；前端 ``procedureTrimDecision.spec.ts`` 7 红，全是 Wave 1
「改造前基线快照」在 Task 12/13 落地后的预期转红）。用 rc 判会把「守卫缺陷」误报成
「变异有效」。

- ``RED``                   : 新增失败（或基线红转绿）非空，**且其中确实包含**该变异声明的
                              预期打红项（``expect_red``）
- ``WRONG-TEST``            : 失败集合变了，但变的不是预期那条 ⇒ 污染残留或锚点错行
- ``GREEN``                 : 失败集合完全不变 ⇒ **守卫缺陷**（或该变异行为等价 = 无效变异，
                              见 ``T10-8`` 注释里的真实先例，判缺陷前必须先排除它）
- ``ANCHOR-MISS``           : 锚点命中数 != 1，或变异后文件字节未变 ⇒ **脚本缺陷**
- ``COLLECT-ERROR·NO-JSON`` : 变异体非法语法致零断言执行 / vitest JSON 未生成 ⇒ 该轮什么都
                              没证明，不得当 RED

═══ 硬约束 ═══

- 锚点**行级唯一**（``splitlines()`` + 整行 strip 比对 + ``hits == 1``）。禁跨行字面量 ——
  工作树多为 CRLF，含 ``\\n`` 的锚点必 MISS。
- 同一行文本天然多命中时（如 ``verdict: 'suggest_trim',`` 全文 2 处）用 ``scope`` +
  ``offset``：``scope`` 必须自身唯一，再按相对行偏移定位，并**核对该行内容等于 anchor**。
  禁「第 n 次出现」定位 —— 代码增删会让它错位成 WRONG-TEST 而看不出来。
- 备份落 ``.t22snap``（不用 ``.bak``：仓库里有别的会话的活体 ``*.bak``，换后缀彻底避开
  任何按扩展名扫目录的清理脚本）。``try/finally`` 无条件写回，还原后 **md5 逐字节核验**。
- 变异只改**一行**（多行变异请拆成多条），便于定位。
- 报告落盘 ``tmp_mutate_trim_report.txt``（本环境 python stdout 会被转义符污染吞掉）。
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
# 🔴 本文件在 backend/scripts/check/ ==> 仓库根是 parents[3]（parents[2] 是 backend/）。
#    写成 parents[2] 会拼出 backend/backend/... 并以 FileNotFoundError 收场。
_REPO = _HERE.parents[3]
_BACKEND = _REPO / "backend"
_FRONTEND = _REPO / "audit-platform" / "frontend"
assert (_BACKEND / "app" / "main.py").exists(), f"仓库根定位错误: {_REPO}"
assert (_FRONTEND / "package.json").exists(), f"前端根定位错误: {_FRONTEND}"

# ── 后端被变异文件 ──
PROBE = _BACKEND / "app" / "services" / "workpaper_entry_probe.py"
CTX = _BACKEND / "app" / "services" / "trim_decision_context.py"
CTX_TEST = _BACKEND / "tests" / "procedure_trim" / "test_trim_decision_context.py"
B50_READER = _BACKEND / "app" / "services" / "b50_risk_reader.py"

# ── 前端被变异文件 ──
_FE_SRC = _FRONTEND / "src"
_CMP = _FE_SRC / "components" / "workpaper" / "composables"
DECISION_TS = _CMP / "procedureTrimDecision.ts"
EXEMPTION_TS = _CMP / "completenessExemption.ts"
GATE_TS = _CMP / "trimAggregateGate.ts"
TRIM_VUE = _FE_SRC / "views" / "ProcedureTrimming.vue"

TEST_TARGET = "backend/tests/procedure_trim/"

# 前端守卫扫描面：9 个 view 级 + 7 个 composable 级。
#
# 🔴 不能只跑 view 级 —— T22 的 8 条变异落在 composable 纯函数上，它们的守卫在
#    `components/workpaper/composables/__tests__/` 下；只跑 view 级会让那 8 条恒 GREEN
#    并被误判成守卫缺陷。
VITEST_TARGETS: tuple[str, ...] = (
    "src/views/__tests__/trimDegradationConsistency.spec.ts",
    "src/views/__tests__/trimAdequacyReview.spec.ts",
    "src/views/__tests__/trimDecisionWiring.spec.ts",
    "src/views/__tests__/delegationSuggestionApply.spec.ts",
    "src/views/__tests__/completenessScopeOverride.spec.ts",
    "src/views/__tests__/noteLinkageHost.spec.ts",
    "src/views/__tests__/ProcedureTrimming.twoLayer.spec.ts",
    "src/views/__tests__/delegationLoadSingleSource.spec.ts",
    "src/views/__tests__/b50BadgeSingleSource.spec.ts",
    "src/components/workpaper/composables/__tests__/procedureTrimDecision.spec.ts",
    "src/components/workpaper/composables/__tests__/procedureTrimDecision.behavior.spec.ts",
    "src/components/workpaper/composables/__tests__/trimAggregateGate.spec.ts",
    "src/components/workpaper/composables/__tests__/completenessExemption.spec.ts",
    "src/components/workpaper/composables/__tests__/b50Completeness.spec.ts",
    "src/components/workpaper/composables/__tests__/delegationSuggestion.spec.ts",
    "src/components/workpaper/composables/__tests__/delegationSeniority.spec.ts",
)

_VITEST_JSON = _FRONTEND / "tmp_mutate_vitest.json"
_REPORT = _REPO / "tmp_mutate_trim_report.txt"
_SNAP_SUFFIX = ".t22snap"


@dataclass(frozen=True)
class Mutation:
    mid: str
    path: Path
    anchor: str                       # 整行内容（strip 后比对）
    replacement: str                  # 替换后的整行（保留原缩进）
    expect: str                       # 期望被打红的守卫（人类可读）
    sides: tuple[str, ...] = ("py",)  # 该变异要跑哪几侧测试："py" / "ts"
    #: 声明「预期打红项」的名称特征。变异后的新增失败必须**包含**其中至少一条，
    #: 否则判 WRONG-TEST —— 只看「有没有新红」会把污染残留当成有效变异。
    expect_red: tuple[str, ...] = ()
    #: 同行文本天然多命中时的消歧锚（必须自身唯一）+ 相对行偏移。
    scope: str | None = None
    offset: int = 0
    note: str = ""


MUTATIONS: tuple[Mutation, ...] = (
    # ══════════════════════════════════════════════════════════════════════
    # Task 10（既有交付资产，勿删）—— 只跑后端
    # ══════════════════════════════════════════════════════════════════════
    # ── Task 10：系统副产键剥除清单 ──────────────────────────────────────────
    Mutation(
        "T10-1",
        PROBE,
        '"audit_checks",',
        "# audit_checks 被移除（变异）",
        "剥除清单完备性 + 连库主形态剥空",
        expect_red=("test_workpaper_entry_probe",),
    ),
    Mutation(
        "T10-2",
        PROBE,
        'DELIBERATELY_KEPT_PARSED_DATA_KEYS: tuple[str, ...] = ("html_data",)',
        'DELIBERATELY_KEPT_PARSED_DATA_KEYS: tuple[str, ...] = ()',
        "html_data 有意保留的意图留痕",
        expect_red=("test_workpaper_entry_probe",),
    ),
    Mutation(
        "T10-3",
        PROBE,
        '"changed_sheets_last_save",',
        '"changed_sheets_last_save", "html_data",',
        "剥除清单不得吞真实内容键 + 连库 html_data 保留",
        expect_red=("test_workpaper_entry_probe",),
    ),
    # ── Task 10：失败兜底与降级上报 ─────────────────────────────────────────
    Mutation(
        "T10-4",
        PROBE,
        "entries={c: True for c in codes},",
        "entries={c: False for c in codes},",
        "查询失败按可能有录入保守保留",
        expect_red=("test_workpaper_entry_probe",),
    ),
    Mutation(
        "T10-5",
        PROBE,
        "degraded=True,",
        "degraded=False,",
        "失败必须如实上报降级",
        expect_red=("test_workpaper_entry_probe",),
    ),
    Mutation(
        "T10-6",
        PROBE,
        "return ProbeResult(entries={c: found.get(c, False) for c in codes}, degraded=False)",
        "return ProbeResult(entries=found, degraded=False)",
        "每个请求码都有显式布尔",
        expect_red=("test_workpaper_entry_probe",),
    ),
    # ── Task 10：批量化与 SQL 形态 ──────────────────────────────────────────
    Mutation(
        "T10-7",
        PROBE,
        "WHERE wi.project_id = CAST(:pid AS uuid)",
        "WHERE wi.project_id = :pid",
        "project_id 必须显式 CAST 为 uuid",
        expect_red=("test_workpaper_entry_probe",),
    ),
    # 🔴 曾把本条写成 `GROUP BY cr.wp_id` -> `GROUP BY cr.wp_id, cr.item_id` 并判 GREEN。
    #    那是**无效变异** —— 多出的分组键只让 `filled` 返回更多行，外层 bool_or 结果不变
    #    ==> 行为等价，守卫不红是对的。判「守卫缺陷」前必须先确认变异真的改变了行为。
    Mutation(
        "T10-8",
        PROBE,
        "    GROUP BY cr.wp_id",
        "    -- GROUP BY 被移除（变异）",
        "checklist 侧必须是独立 CTE + 分组聚合（禁相关子查询 EXISTS）",
        expect_red=("test_workpaper_entry_probe",),
    ),
    Mutation(
        "T10-9",
        PROBE,
        'PROBE_SQL_MARKER = "-- workpaper_entry_probe"',
        'PROBE_SQL_MARKER = "-- renamed_marker"',
        "SQL 标记存在性 + 替身分流",
        expect_red=("test_workpaper_entry_probe",),
    ),
    Mutation(
        "T10-10",
        PROBE,
        'stmt = sa.text(_PROBE_SQL).bindparams(sa.bindparam("codes", expanding=True))',
        "stmt = sa.text(_PROBE_SQL.replace('IN :codes', 'IN (' + ','.join(repr(c) for c in codes) + ')'))",
        "expanding bindparam 不得改成 SQL 串拼接",
        expect_red=("test_workpaper_entry_probe",),
    ),
    # ── Task 10：取数装配接线 ───────────────────────────────────────────────
    Mutation(
        "T10-11",
        CTX,
        "    result = await probe_workpaper_entries_detailed(db, project_id, codes)",
        "    result = ProbeResult(entries=await probe_workpaper_entries(db, project_id, codes))",
        "装配层必须用 detailed 版本（薄壳丢弃 degraded）",
        expect_red=("test_trim_decision_context",),
    ),
    Mutation(
        "T10-12",
        CTX,
        '            "本项目无带底稿编号的程序实例，底稿已录入探测目标为空",',
        "            None,",
        "degradation 的 reason 必须是非空字符串（结构稳定性）",
        expect_red=("test_trim_decision_context",),
    ),
    Mutation(
        "T10-13",
        CTX,
        "    if not codes:",
        "    if False:",
        "探测目标为空时仍须记 degradation",
        expect_red=("test_trim_decision_context",),
    ),
    Mutation(
        "T10-14",
        CTX,
        "    if result.degraded:",
        "    if False:",
        "探测降级为全保留时必须记 degradation",
        expect_red=("test_trim_decision_context",),
    ),
    Mutation(
        "T10-15",
        CTX,
        "            if cyc not in wanted:",
        "            if False:",
        "cycles 过滤必须生效",
        expect_red=("test_trim_decision_context",),
    ),
    # ── 守卫自身判据（防「假红被绕开」而不是「真红被忽略」）──────────────────
    # 🔴 锚点必须是**整行**（`_locate` 按整行 strip 比对）；写半行片段必 ANCHOR-MISS。
    Mutation(
        "T10-16",
        CTX_TEST,
        r'(rf"\b{_SESSION_RECEIVER}\s*\.\s*add\s*\(", "db.add("),',
        r'(r"\.add\s*\(", "db.add("),',
        "写库判据不得被 Python 集合操作 set.add 骗",
        expect_red=("test_trim_decision_context",),
    ),

    # ══════════════════════════════════════════════════════════════════════
    # Task 22（本轮新增）—— 12 条，跨前后端
    # ══════════════════════════════════════════════════════════════════════
    # ── ① 风险保护（档 1）：特别风险 / 高风险恒 keep ─────────────────────────
    Mutation(
        "T22-1",
        DECISION_TS,
        "if (risk && (risk.hasSpecial === true || risk.maxRisk === 'H')) {",
        "if (false && risk && (risk.hasSpecial === true || risk.maxRisk === 'H')) {",
        "档 1 风险保护：特别风险与高重大错报风险不因金额被裁（CAS 1231）",
        sides=("py", "ts"),
        expect_red=("档 1 风险保护", "风险保护"),
        note="用 `false &&` 而不是 `if (false)`：保留 TS 对 risk 的收窄，"
             "避免变异体因类型收窄丢失而变成 COLLECT-ERROR（那时什么都证明不了）。",
    ),
    # ── ② 认定级优先（完整性豁免）────────────────────────────────────────────
    Mutation(
        "T22-2",
        EXEMPTION_TS,
        "if (hasAssertion || isSpecial) {",
        "if (false && (hasAssertion || isSpecial)) {",
        "Property 6：完整性认定级优先且短路于循环级清单",
        sides=("py", "ts"),
        expect_red=("Property 6", "认定级", "source=assertion", "认定优先"),
    ),
    # ── ③ 汇总闸：按科目名去重 ───────────────────────────────────────────────
    Mutation(
        "T22-3",
        GATE_TS,
        "const account = normalizeAccountName(item.accountName)",
        "const account = normalizeAccountName(item.accountName) + '#' + String(byAccount.size)",
        "Property 10：同一科目多条建议只计一次（去重键 = accountName）",
        sides=("py", "ts"),
        expect_red=("只计一次", "去重", "Property 10"),
        note="🔴 不能写成删掉 `if (byAccount.has(account)) continue` —— Map 本身按 key 去重，"
             "删那句只改「同科目不同金额取首条还是末条」，合计不变 ⇒ 行为等价 = 无效变异"
             "（同 T10-8 那类先例）。真正去掉去重必须让 key 不再是科目名。",
    ),
    # ── ④ 汇总闸：只计两个重要性类理由码 ─────────────────────────────────────
    Mutation(
        "T22-4",
        GATE_TS,
        "if (!MATERIALITY_REASON_CODES.has(String(item.reasonCode ?? ''))) continue",
        "if (!String(item.reasonCode ?? '')) continue",
        "Property 10：no_data 等非重要性类理由码不得计入汇总（否则闸门恒亮被当误报关掉）",
        sides=("py", "ts"),
        expect_red=("no_data", "理由码"),
    ),
    # ── ⑤ 汇总闸：阈值方向 >= ────────────────────────────────────────────────
    Mutation(
        "T22-5",
        GATE_TS,
        "const blocked = threshold !== null && totalAmount >= threshold",
        "const blocked = threshold !== null && totalAmount > threshold",
        "Property 11：恰好等于实际执行重要性时必须阻断（>= 而非 >）",
        sides=("py", "ts"),
        expect_red=("恰好等于阈值", ">= 而非 >", "当且仅当"),
    ),
    # ── ⑥ B50 矩阵键前缀锚定闸 ──────────────────────────────────────────────
    Mutation(
        "T22-6",
        B50_READER,
        "if body == item_id:",
        "if False:",
        "前缀锚定闸承重（移除后非 matrix 前缀键会被误判成矩阵格并污染 cells）",
        sides=("py", "ts"),
        expect_red=("test_prefix_anchor_guard_is_load_bearing",
                    "test_spec_sample_is_blocked_by_suffix_whitelist_not_prefix_anchor"),
        note="tasks.md 原文举的样本（B50-T3-balance-货币资金）会被 suffix 白名单挡住，"
             "证明不了这道闸；Task 1 守卫已改用穿透样本并把该结论写成断言。本条变异打红的"
             "正是那两条反向自检。",
    ),
    # ── ⑦ 底稿已录入判据（档 2）─────────────────────────────────────────────
    Mutation(
        "T22-7",
        DECISION_TS,
        "if (procedure.hasWorkpaperEntry === true) {",
        "if (false && procedure.hasWorkpaperEntry === true) {",
        "Property 15：待执行 + 底稿已录入必须保留（裁剪会让已录入的工作在清单上消失）",
        sides=("py", "ts"),
        expect_red=("hasWorkpaperEntry", "底稿已录入", "Property 15"),
    ),
    # ── ⑧ 驳回判据（档 2）──────────────────────────────────────────────────
    Mutation(
        "T22-8",
        DECISION_TS,
        "if (procedure.suggestionRejected === true) {",
        "if (false && procedure.suggestionRejected === true) {",
        "Property 32：已驳回建议恒 keep（不再重复提示）",
        sides=("py", "ts"),
        expect_red=("suggestionRejected", "已驳回", "驳回"),
    ),
    # ── ⑨ 重要性类恒 suggest_trim，永不 auto_trim ───────────────────────────
    Mutation(
        "T22-9",
        DECISION_TS,
        "verdict: 'suggest_trim',",
        "verdict: 'auto_trim',",
        "Property 2 双向锁死：重要性类判据只产建议；auto_trim 只允许 no_data 一种成因",
        sides=("py", "ts"),
        expect_red=("below_trivial", "auto_trim", "档 7"),
        scope="reasonCode: 'below_trivial',",
        offset=-1,
        note="`verdict: 'suggest_trim',` 全文 2 处（档 7 / 档 8）⇒ 必须用 scope+offset 消歧："
             "scope 取唯一的 `reasonCode: 'below_trivial',`，offset=-1 回到 verdict 行，"
             "并核对该行内容确等于 anchor。禁用「第 2 次出现」这类位置定位。",
    ),
    # ── ⑩ 降级标注与实际执行一致（Property 12）──────────────────────────────
    Mutation(
        "T22-10",
        TRIM_VUE,
        '<div v-if="degradationNotes.length > 0" class="gt-proc-degrade-bar">',
        '<div v-if="degradationNotes.length > 0 && suggestionStats.suggested > 0" class="gt-proc-degrade-bar">',
        "降级标注的门控不得与它的内容互斥（重新嵌回「有建议」前提 = 标注在唯一该出现的场景恒不显示）",
        sides=("py", "ts"),
        expect_red=("独立宿主", "真的渲染到 DOM", "恒显也不是恒隐"),
        note="复现落地前的真缺陷：重要性维度不可用 ⇒ 该维度零建议 ⇒ suggested === 0 ⇒ "
             "宿主整块不渲染 ⇒ 「未做重要性联动」永远看不到。",
    ),
    # ── ⑪ overall_materiality 禁用约束（Requirement 4.6）────────────────────
    Mutation(
        "T22-11",
        CTX,
        'return {"performance_materiality": pm, "trivial_threshold": tt}, []',
        'return {"performance_materiality": pm, "trivial_threshold": tt, "overall_materiality": pm / 0.75}, []',
        "返回结构任何层级都不得出现 overall_materiality（下发即把「不推算」漏给前端自觉）",
        sides=("py", "ts"),
        expect_red=("test_result_never_contains_overall_materiality_key",
                    "test_materiality_query_does_not_select_overall_materiality"),
        note="选「泄漏禁用键」而不是「把 FORBIDDEN_RESULT_KEYS 清空」：后者只让集合交集恒空、"
             "行为上仍不下发该键，属半无效变异。泄漏是真实的越界行为。",
    ),
    # ── ⑫ 委派负载单一真源（Task 16 已删的前端自算）─────────────────────────
    Mutation(
        "T22-12",
        TRIM_VUE,
        "const memberLoads = ref<Record<string, number> | null>(null)",
        "const memberLoads = ref<Record<string, number> | null>(null)\n"
        "const assigneeLoadMap = computed(() => { const map: Record<string, number> = {};"
        " for (const p of procedures.value) { if (p.assigned_to)"
        " map[p.assigned_to] = (map[p.assigned_to] || 0) + 1 } return map })",
        "负载单一真源：前端不得再按底稿张数自算一份（口径与后端「非终态任务数」不同）",
        sides=("py", "ts"),
        expect_red=("前端自算负载", "按底稿聚合负载", "assigneeLoadMap"),
        note="唯一一条 replacement 含换行的变异（要塞回一整个 computed）。`_apply` 对 "
             "replacement 内的 \\n 做展开而不是当锚点用 —— 锚点侧仍严格禁跨行。",
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# 运行器
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class RunResult:
    fails: set[str] = field(default_factory=set)
    total: int = 0
    collect_errors: list[str] = field(default_factory=list)
    fatal: str = ""      # 非空 = 该侧本轮什么都没证明
    summary: str = ""


def _env() -> dict:
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _run_pytest() -> RunResult:
    """跑后端守卫。失败名 = 完整 nodeid（含参数化 id），不截成函数名。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_TARGET, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(_REPO),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=_env(),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    res = RunResult()
    res.fails = {f"py::{n}" for n in re.findall(r"^FAILED\s+(\S+)", out, re.M)}
    res.collect_errors = [f"py::{n}" for n in re.findall(r"^ERROR\s+(\S+)", out, re.M)]
    m = re.search(r"(\d+) failed", out)
    n_failed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) passed", out)
    res.total = (int(m.group(1)) if m else 0) + n_failed
    m = re.search(r"(\d+) error", out)
    if m and int(m.group(1)) > 0 and not res.collect_errors:
        res.collect_errors.append(f"py::<{m.group(1)} errors, 未解析出 nodeid>")
    # 自检：短摘要被截断时不得静默
    if n_failed != len(res.fails):
        res.fails.add(f"py::<unparsed:{n_failed}!={len(res.fails)}>")
    if res.total == 0:
        res.fatal = "pytest 零测试执行（collection error 或调用失败）"
    res.summary = f"total={res.total} failed={n_failed}"
    return res


def _run_vitest() -> RunResult:
    """跑前端守卫（JSON reporter 落盘后解析）。

    🔴 两个必踩的坑：
    1. ``npm exec`` 传 flag **必须**加 ``--`` 分隔符。不加则 npm 把 ``--reporter`` 当自己的
       cli config ==> **JSON 不生成而退出码仍 0** ==> 差集恒空、全判 GREEN。
    2. 跑前删旧 JSON 并断言新 JSON 存在。否则上一轮的 JSON 会被当本轮结果读走。
    """
    res = RunResult()
    if _VITEST_JSON.exists():
        _VITEST_JSON.unlink()
    # 跨平台：Windows 的 npm 实为 npm.cmd（须经 cmd /c），而 ubuntu-latest 无 cmd。
    #  写死 cmd /c 会让本脚本在 CI 上必然 NO-JSON ⇒ 基线 fatal ⇒ job 恒红（Task 24 实证）。
    _npm = ["cmd", "/c", "npm"] if os.name == "nt" else ["npm"]
    cmd = [
        *_npm, "exec", "--", "vitest", "run",
        "--reporter=json", f"--outputFile={_VITEST_JSON.name}",
        *VITEST_TARGETS,
    ]
    subprocess.run(
        cmd, cwd=str(_FRONTEND), capture_output=True,
        encoding="utf-8", errors="replace", env=_env(),
    )
    if not _VITEST_JSON.exists():
        res.fatal = "vitest JSON 未生成（NO-JSON）"
        return res
    try:
        data = json.loads(_VITEST_JSON.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        res.fatal = f"vitest JSON 不可解析: {e!r}"
        return res
    files = data.get("testResults") or []
    for tr in files:
        name = Path(str(tr.get("name") or "")).name
        ars = tr.get("assertionResults") or []
        if not ars:
            # 该 spec 文件零断言执行 ==> transform / collection 失败
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
    res.summary = f"total={res.total} failed={n_failed} files={len(files)}"
    return res


def _run(sides: tuple[str, ...]) -> RunResult:
    """跑指定侧并把失败名**归一到一个集合**再返回。"""
    merged = RunResult()
    parts: list[str] = []
    for side in sides:
        r = _run_pytest() if side == "py" else _run_vitest()
        merged.fails |= r.fails
        merged.collect_errors.extend(r.collect_errors)
        merged.total += r.total
        if r.fatal:
            merged.fatal = f"{merged.fatal}; {side}: {r.fatal}".strip("; ")
        parts.append(f"{side}[{r.summary or r.fatal}]")
    merged.summary = " ".join(parts)
    return merged


# ═══════════════════════════════════════════════════════════════════════════
# 变异施加 / 还原
# ═══════════════════════════════════════════════════════════════════════════
def _locate(lines: list[str], text: str) -> list[int]:
    t = text.strip()
    return [i for i, ln in enumerate(lines) if ln.strip() == t]


def _apply(mut: Mutation) -> str | None:
    """施加变异；返回错误原因（None = 成功）。

    CRLF 安全：按 ``\\n`` 切分后每行可能带尾随 ``\\r``；比对用 strip 故不受影响，
    写回时**逐字保留**该行原有的行尾符，避免只把变异那一行改成 LF 造成混合行尾。
    """
    if "\n" in mut.anchor or (mut.scope and "\n" in mut.scope):
        return "ANCHOR-MISS: 锚点含换行（CRLF 工作树必 MISS，禁跨行锚点）"
    before = mut.path.read_bytes()
    lines = before.decode("utf-8").split("\n")

    if mut.scope is None:
        hits = _locate(lines, mut.anchor)
        if len(hits) != 1:
            return f"ANCHOR-MISS: anchor 命中 {len(hits)} 处（要求恰好 1）"
        idx = hits[0]
    else:
        shits = _locate(lines, mut.scope)
        if len(shits) != 1:
            return f"ANCHOR-MISS: scope 命中 {len(shits)} 处（要求恰好 1）"
        idx = shits[0] + mut.offset
        if not (0 <= idx < len(lines)):
            return f"ANCHOR-MISS: scope+offset 越界（idx={idx}）"
        if lines[idx].strip() != mut.anchor.strip():
            return (
                f"ANCHOR-MISS: scope+offset 定位到的行内容与 anchor 不符 "
                f"（实得 {lines[idx].strip()[:60]!r}）"
            )

    original = lines[idx]
    eol = "\r" if original.endswith("\r") else ""
    body = original[: len(original) - len(eol)] if eol else original
    indent = body[: len(body) - len(body.lstrip())]
    new_lines = [indent + seg.strip() + eol for seg in mut.replacement.split("\n")]
    lines[idx : idx + 1] = new_lines
    mut.path.write_text("\n".join(lines), encoding="utf-8", newline="")
    if mut.path.read_bytes() == before:
        return "ANCHOR-MISS: 变异后文件字节未变（replacement 与原文等价 = 空操作）"
    return None


def _snap_path(p: Path) -> Path:
    return p.with_suffix(p.suffix + _SNAP_SUFFIX)


def _restore_all() -> None:
    """只还原 MUTATIONS 登记过的路径 —— **绝不按扩展名扫目录**。"""
    for p in sorted({m.path for m in MUTATIONS}, key=str):
        for suffix in (_SNAP_SUFFIX, ".bak"):
            snap = p.with_suffix(p.suffix + suffix)
            if snap.exists():
                p.write_bytes(snap.read_bytes())
                snap.unlink()
                print(f"[restore] {p.name} <- {suffix}")
                break


# ═══════════════════════════════════════════════════════════════════════════
# 判定
# ═══════════════════════════════════════════════════════════════════════════
def _judge(
    mut: Mutation, base: RunResult, cur: RunResult,
) -> tuple[str, str]:
    if cur.fatal:
        return "COLLECT-ERROR·NO-JSON", cur.fatal
    new_ce = [c for c in cur.collect_errors if c not in base.collect_errors]
    if new_ce:
        return "COLLECT-ERROR·NO-JSON", f"新增零断言执行/收集错误 {new_ce}"

    new = cur.fails - base.fails
    resolved = base.fails - cur.fails
    changed = sorted(new) + [f"(红转绿){x}" for x in sorted(resolved)]
    if not changed:
        return "GREEN", "失败集合完全不变（守卫缺陷，或该变异行为等价=无效变异）"
    if not mut.expect_red:
        return "RED", f"失败集合变化 {len(changed)} 项：{changed}"
    hit = [c for c in changed if any(pat in c for pat in mut.expect_red)]
    if not hit:
        return (
            "WRONG-TEST",
            f"打红了但不是预期项（期望特征 {list(mut.expect_red)}）；实得 {changed}",
        )
    miss = [c for c in changed if c not in hit]
    detail = f"命中预期 {len(hit)}/{len(changed)} 项：{hit}"
    if miss:
        detail += f"；同时连带打红（非预期特征但同源）：{miss}"
    return "RED", detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--only-prefix", default=None, help="如 T22 / T10")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    if args.restore:
        _restore_all()
        return 0

    targets = list(MUTATIONS)
    if args.only:
        targets = [m for m in targets if m.mid in args.only]
    if args.only_prefix:
        targets = [m for m in targets if m.mid.startswith(args.only_prefix)]
    if not targets:
        print("没有匹配的变异 id")
        return 2

    files = sorted({m.path for m in targets}, key=str)
    sides: tuple[str, ...] = tuple(
        s for s in ("py", "ts") if any(s in m.sides for m in targets)
    )

    md5_before = {p: _md5(p) for p in files}
    for p in files:
        _snap_path(p).write_bytes(p.read_bytes())

    lines_out: list[str] = []

    def log(s: str) -> None:
        """落盘为主、stdout 为辅。

        🔴 本环境控制台是 GBK：直接 print 含 ``⊇`` / ``⟹`` 的测试名会 UnicodeEncodeError
        并把整轮跑崩（首轮实测）。故 stdout 侧一律 errors='replace'，且每条都**立即刷盘**，
        中途崩掉也留得下已跑出的判定。
        """
        lines_out.append(s)
        _REPORT.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
        sys.stdout.write(s.encode(sys.stdout.encoding or "utf-8", "replace")
                         .decode(sys.stdout.encoding or "utf-8", "replace") + "\n")

    base = _run(sides)
    log(f"[baseline] {base.summary}")
    log(f"[baseline] failed={len(base.fails)}")
    for f in sorted(base.fails):
        log(f"  base-red  {f}")
    if base.collect_errors:
        for c in base.collect_errors:
            log(f"  base-CE   {c}")

    results: list[tuple[str, str, str]] = []
    try:
        for mut in targets:
            err = _apply(mut)
            if err:
                results.append((mut.mid, "ANCHOR-MISS", err))
                log(f"[{mut.mid}] ANCHOR-MISS  {err}")
                continue
            try:
                cur = _run(mut.sides)
                state, detail = _judge(mut, base, cur)
                detail = f"{detail}  |{cur.summary}"
            finally:
                snap = _snap_path(mut.path)
                mut.path.write_bytes(snap.read_bytes())
            results.append((mut.mid, state, detail))
            log(f"[{mut.mid}] {state:24s} {detail}")
            log(f"          期望: {mut.expect}")
    finally:
        for p in files:
            snap = _snap_path(p)
            if snap.exists():
                p.write_bytes(snap.read_bytes())
                snap.unlink()
        if _VITEST_JSON.exists():
            _VITEST_JSON.unlink()

    md5_after = {p: _md5(p) for p in files}
    drift = [p.name for p in files if md5_before[p] != md5_after[p]]
    log("")
    tally: dict[str, list[str]] = {}
    for mid, state, _ in results:
        tally.setdefault(state, []).append(mid)
    for state in ("RED", "GREEN", "WRONG-TEST", "ANCHOR-MISS", "COLLECT-ERROR·NO-JSON"):
        if state in tally:
            log(f"{state:24s} {len(tally[state]):2d}  {tally[state]}")
    log(f"RED {len(tally.get('RED', []))}/{len(results)}")
    log(f"字节级还原核验: {'OK 全部一致' if not drift else 'FAILED 漂移 ' + str(drift)}")
    _REPORT.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    print(f"[report] {_REPORT}")
    return 0 if not drift else 1


if __name__ == "__main__":
    raise SystemExit(main())
