"""变异检验：裁剪判据的报表行科目定位守卫是否真的承重。

spec: procedure-trim-report-line-account-resolution — Task 13
Requirements: 7.2 / Property 19

被测守卫（跨两个运行器）::

    pytest  backend/tests/procedure_trim/test_report_line_index.py
            backend/tests/procedure_trim/test_trim_report_line_amounts.py
            backend/tests/procedure_trim/test_trim_context_report_line_wiring.py
    vitest  src/views/__tests__/trimAmountSourcePriority.spec.ts
            src/components/workpaper/composables/__tests__/trimDecisionAmountSourceNeutrality.spec.ts

## 为什么必须做

守卫**红/绿两种结果都不可信**，除非证明过「把实现改坏时它真会红」。本 spec 落地过程中
已实测出 4 处守卫锚点缺陷（全是假红：扫描面漏了独立 interface、样本构造使判据恒空转、
正则误命中合法写法、锚点绑定了已迁移的旧写法），若不做变异检验，其中任何一处都可能
反向表现为假绿而无人发现。

## 判定五态（**不看退出码**）

按**失败测试名集合求差集**：

- ``RED``          new_fails 非空 ⇒ 变异有效、守卫承重
- ``RED(转绿)``    基线红转绿 ⇒ 亦为有效信号（变异改变了判据结论）
- ``GREEN``        差集为空 ⇒ **守卫缺陷**（变异生效了但没人发现）
- ``ANCHOR-MISS``  锚点未命中或命中 != 1 ⇒ **脚本缺陷**，变异根本没施加
                   （此时"测试仍绿"不能作任何结论）
- ``NO-REPORT``    报告文件未生成 / 用例总数骤降 ⇒ 整文件零断言执行（第五态）

## 锚点铁律

- **行级唯一**：``splitlines()`` + 行内 needle + ``hits == 1`` + 相对 offset
- 锚点里**禁含 ``\\n``**：本工作树 CRLF，跨行字面量必 MISS
- 变异后断言字节确实变了（未变则"测试仍绿"无意义）

## 还原

``.bak`` 备份 + ``try/finally`` 无条件写回 + md5 字节级核验 + ``.bak`` 零残留。
被测文件是跨 spec 共享热点（``ProcedureTrimming.vue`` / ``procedureTrimDecision.ts`` /
``trim_decision_context.py``），故启动前若发现 ``.bak`` 已存在**直接中止**
（可能是别的会话的活体备份，覆盖它会毁掉对方的还原能力）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
FE = os.path.join(ROOT, 'audit-platform', 'frontend')
BE = os.path.join(ROOT, 'backend')

# ── 被变异的实现文件 ─────────────────────────────────────────────────────────
IDX = os.path.join(BE, 'app', 'services', 'four_table', 'report_line_index.py')
AMT = os.path.join(BE, 'app', 'services', 'trim_report_line_amounts.py')
CTX = os.path.join(BE, 'app', 'services', 'trim_decision_context.py')
SRC = os.path.join(FE, 'src', 'components', 'workpaper', 'composables', 'trimAmountSource.ts')
DEC = os.path.join(FE, 'src', 'components', 'workpaper', 'composables', 'procedureTrimDecision.ts')
VUE = os.path.join(FE, 'src', 'views', 'ProcedureTrimming.vue')

# ── 被测守卫 ─────────────────────────────────────────────────────────────────
PY_SPECS = [
    'backend/tests/procedure_trim/test_report_line_index.py',
    'backend/tests/procedure_trim/test_trim_report_line_amounts.py',
    'backend/tests/procedure_trim/test_trim_context_report_line_wiring.py',
]
TS_SPECS = [
    'src/views/__tests__/trimAmountSourcePriority.spec.ts',
    'src/components/workpaper/composables/__tests__/trimDecisionAmountSourceNeutrality.spec.ts',
]
PY_XML = 'tmp_mutate_report_line_py.xml'
TS_JSON = 'tmp_mutate_report_line_ts.json'

#: 用例总数骤降到基线的这个比例以下 ⇒ 判 NO-REPORT（整文件零断言执行）
_COUNT_FLOOR = 0.8


@dataclass
class Mutation:
    mid: str
    runner: str
    """``py`` 或 ``ts`` —— 决定跑哪一组守卫。"""
    path: str
    desc: str
    anchor: str
    """行内唯一 needle（**禁含换行**）。"""
    offset: int = 0
    """相对锚点行的偏移（0 = 锚点行本身，负数 = 往上）。"""
    span: int = 1
    """从 offset 起替换多少行。"""
    new_lines: list[str] = field(default_factory=list)
    expect: str = ''
    """预期打红的判据（人读，用于归因）。"""
    live_only: bool = False
    """🔴 预期打红的判据**只有连库判据**。

    CI 上没有真实库 ⇒ 那些判据 ``pytest.skip`` ⇒ 变异后仍 skip ⇒ 差集为空
    ⇒ 会被误判成 ``GREEN(守卫缺陷)`` 而让 CI **假红**。故 CI 用
    ``--skip-live-only`` 跳过它们，并在 job 注释里如实写明「这几条只在本地
    连库环境验证」。用布尔标记而不是在 CI 里手写 mid 列表：新增变异时不会漏标。
    """


MUTATIONS: list[Mutation] = [
    # ══ 后端：索引 ═══════════════════════════════════════════════════════════
    Mutation(
        'M1', 'py', IDX, '索引写死一个报表行编码字面量（双真源入口）',
        anchor='    return str(getattr(spec, "row_code", None) or "").strip()',
        new_lines=['    return str(getattr(spec, "row_code", None) or "BS-999").strip()'],
        expect='test_index_module_has_zero_row_code_literals + 交叉锁死',
    ),
    Mutation(
        'M2', 'py', IDX, '索引改取另一循环的注册表（映射漂移）',
        anchor='    ("D", "d_cycle_specs", "D_CYCLE_SPECS", d_cycle_specs.D_CYCLE_SPECS),',
        new_lines=['    ("D", "d_cycle_specs", "D_CYCLE_SPECS", f_cycle_specs.F_CYCLE_SPECS),'],
        expect='test_index_cross_locked_with_percycle_declarations + 覆盖面判据',
    ),
    Mutation(
        'M3', 'py', IDX, '归一正则去掉数字段（D2-1至D2-4 → D）',
        anchor='_WP_CODE_PREFIX_RE = re.compile(r"^([A-Z]+\\d+)")',
        new_lines=['_WP_CODE_PREFIX_RE = re.compile(r"^([A-Z]+)")'],
        expect='test_normalize_wp_code_handles_range_forms + 与前端正则交叉锁死',
    ),
    Mutation(
        'M4', 'py', IDX, 'A/B/C/S 从「不适用」改成「无落点」（两态混同）',
        anchor='            status=REF_NON_BALANCE_DRIVEN,',
        new_lines=['            status=REF_NO_REPORT_LINE,'],
        expect='test_index_non_balance_driven_cycles_are_distinguishable',
    ),
    # ══ 后端：金额解析 ═══════════════════════════════════════════════════════
    Mutation(
        'M5', 'py', AMT, '非 resolved 态的 amount 默认从 None 改 0.0（编造 0）',
        anchor='    amount: float | None = None',
        new_lines=['    amount: float | None = 0.0'],
        expect='test_amounts_dataclass_defaults_never_fabricate_zero + 行为级不兜 0',
    ),
    Mutation(
        'M6', 'py', AMT, '含 ROW() 的公式不再拒解析（传空 row_cache 强行求值）',
        anchor='        if parser.extract_row_refs(formula):',
        new_lines=['        if False:'],
        expect='test_amounts_behavior_row_reference_is_unavailable',
    ),
    Mutation(
        'M7', 'py', AMT, '公式求值异常从 ERROR 降为 WARNING（接线错误被掩盖）',
        anchor='                    "裁剪判据·报表行金额：公式求值失败 project=%s year=%s wp=%s "',
        offset=-1,
        new_lines=['                logger.warning('],
        expect='test_amounts_module_logs_error_not_warning_on_failure + 行为级 ERROR 断言',
    ),
    Mutation(
        'M8', 'py', AMT, '准则未确定时默认取国企个别（违反「不默认取某变体」）',
        anchor='        return "", "本项目尚未设置适用会计准则（主体类型 / 报表范围）"',
        new_lines=['        return "soe_standalone", ""'],
        expect='test_amounts_behavior_standard_unset_project',
        live_only=True,
    ),
    Mutation(
        'M9', 'py', AMT, '两组准则分叉时随便取一个出数（宁缺勿造被破坏）',
        anchor='        return "", (',
        new_lines=['        return v2, ""'],
        span=4,
        expect='test_amounts_behavior_diverged_standard_project',
        live_only=True,
    ),
    # ══ 后端：上下文接线 ═════════════════════════════════════════════════════
    Mutation(
        'M10', 'py', CTX, '第八键装配好了但返回语句不带（additive 注入即死代码）',
        anchor='        "report_line_amounts": report_lines,',
        new_lines=['        # (mutated: key dropped)'],
        expect='test_return_dict_keys_match_result_keys + test_live_context_has_exactly_eight_keys',
    ),
    Mutation(
        'M11', 'py', CTX, '整体不可用时不记 degradation（前端漏标注）',
        anchor='    if payload and all(',
        new_lines=['    if False and all('],
        expect='test_live_empty_payload_always_accompanied_by_degradation',
        live_only=True,
    ),
    # ══ 前端：优先级与中立性 ═════════════════════════════════════════════════
    Mutation(
        'M12', 'ts', SRC, '前端优先级反转（科目名兜底反而优先于报表行）',
        anchor='  if (reportLineOk) {',
        new_lines=['  if (reportLineOk && byNameOk === null) {'],
        expect='报表行 resolved 时 source = report_line',
    ),
    Mutation(
        'M13', 'ts', SRC, '非 resolved 态的报表行金额也采用（后端违约时不设防）',
        anchor="  const reportLineAmount = (reportLine && reportLine.status === 'resolved')",
        span=3,
        new_lines=['  const reportLineAmount = reportLine ? reportLine.amount : null'],
        expect='报表行 status 非 resolved 但带了金额时**不采用**',
    ),
    Mutation(
        'M14', 'ts', DEC, 'decideTrim 的档 1 条件引用 amountSource（破中立性）',
        anchor="  if (risk && (risk.hasSpecial === true || risk.maxRisk === 'H')) {",
        new_lines=[
            "  if (input.amountSource === 'report_line'"
            " || (risk && (risk.hasSpecial === true || risk.maxRisk === 'H'))) {",
        ],
        expect='decideTrim 函数体内零出现 amountSource + 三种来源下结论相同',
    ),
    Mutation(
        'M15', 'ts', DEC, 'evidence 不再写入溯源字段（溯源链断）',
        anchor='    amountSource: input.amountSource ?? null,',
        span=2,
        new_lines=['    // (mutated: trace dropped)'],
        expect='evidence 真的带上了这两个字段 + buildEvidence 函数体内出现这两个字段',
    ),
    Mutation(
        'M16', 'ts', VUE, '复核视图另算一份金额（两处分叉）',
        anchor='    accountAmount: resolvedAmount?.amount ?? null,',
        new_lines=[
            '    accountAmount: accountName !== null'
            ' ? Number((ctx as TrimDecisionContext).accounts?.[accountName]?.amount)'
            ' : null,',
        ],
        expect='toReviewRow 的金额来自 resolveAccountAmount + 零处直接取 accounts 金额',
    ),
    Mutation(
        'M17', 'ts', VUE, '兜底标记门控改成判 evidence 有无（单向门控）',
        anchor='                v-if="row._amountSource === \'account_name\'"',
        new_lines=['                v-if="row._decisionEvidence"'],
        expect='报表行来源时不渲染兜底标记（门控是双向的）',
    ),
]


def md5(path: str) -> str:
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 运行器：pytest（junit xml）与 vitest（json reporter）
# ─────────────────────────────────────────────────────────────────────────────
def run_py() -> tuple[str, set[str], dict]:
    """跑后端守卫；返回 ``(state, 失败测试名集合, 摘要)``。

    🔴 用 junit xml 而不是解析 ``-q`` 文本：文本摘要在 collection error 时
    只有 ``ERROR`` 行、没有 ``FAILED`` 行 ⇒ 失败名集合为空 ⇒ 会被误判成 GREEN。
    xml 的 ``<error>`` 节点能把「整文件零断言执行」显式暴露出来。
    """
    out = os.path.join(ROOT, PY_XML)
    if os.path.exists(out):
        os.remove(out)
    cmd = [sys.executable, '-m', 'pytest', *PY_SPECS,
           '-p', 'no:randomly', '-q', '--tb=no', '--junitxml=%s' % PY_XML]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if not os.path.exists(out):
        return 'no-report', set(), {'exit': proc.returncode,
                                    'stderr': (proc.stderr or '')[-1200:]}
    fails: set[str] = set()
    total = failed = errored = skipped = 0
    for tc in ET.parse(out).iter('testcase'):
        total += 1
        name = '%s::%s' % (tc.get('classname') or '', tc.get('name') or '')
        if tc.find('failure') is not None:
            failed += 1
            fails.add(name)
        elif tc.find('error') is not None:
            errored += 1
            fails.add(name)
        elif tc.find('skipped') is not None:
            skipped += 1
    os.remove(out)
    return 'ok', fails, {'total': total, 'failed': failed,
                         'errored': errored, 'skipped': skipped}


def run_ts() -> tuple[str, set[str], dict]:
    """跑前端守卫；返回 ``(state, 失败测试名集合, 摘要)``。"""
    out = os.path.join(FE, TS_JSON)
    if os.path.exists(out):
        os.remove(out)
    # 🔴 `npm exec vitest` 传 flag 必须有 `--` 分隔符，否则 npm 把 --reporter 当自己的
    #    cli config，JSON 根本不生成而退出码仍 0。
    # 🔴 Windows 的 npm 实为 npm.cmd（须经 cmd /c）。
    _npm = ['cmd', '/c', 'npm'] if os.name == 'nt' else ['npm']
    cmd = [*_npm, 'exec', 'vitest', '--', 'run', *TS_SPECS,
           '--reporter=json', '--outputFile=%s' % TS_JSON]
    proc = subprocess.run(cmd, cwd=FE, capture_output=True, text=True)
    if not os.path.exists(out):
        return 'no-report', set(), {'exit': proc.returncode,
                                    'stderr': (proc.stderr or '')[-1200:]}
    with open(out, encoding='utf-8') as fh:
        data = json.load(fh)
    fails: set[str] = set()
    total = failed = 0
    for res in data.get('testResults', []):
        for a in res.get('assertionResults', []):
            total += 1
            if a.get('status') == 'failed':
                failed += 1
                fails.add(a.get('fullName') or a.get('title') or '?')
    os.remove(out)
    return 'ok', fails, {'total': total, 'failed': failed,
                         'suites': len(data.get('testResults', []))}


RUNNERS = {'py': run_py, 'ts': run_ts}


# ─────────────────────────────────────────────────────────────────────────────
# 变异施加
# ─────────────────────────────────────────────────────────────────────────────
def locate(m: Mutation) -> tuple[list[str], str, int, int]:
    """返回 ``(lines, newline, 目标起始索引, 命中数)``；锚点必须行级唯一。"""
    assert '\n' not in m.anchor, '%s: anchor 含换行（CRLF 工作树必 MISS）' % m.mid
    with open(m.path, encoding='utf-8') as fh:
        raw = fh.read()
    newline = '\r\n' if '\r\n' in raw else '\n'
    lines = raw.split(newline)
    hits = [i for i, ln in enumerate(lines) if m.anchor in ln]
    start = (hits[0] + m.offset) if len(hits) == 1 else -1
    return lines, newline, start, len(hits)


def apply_mutation(m: Mutation) -> tuple[bool, str]:
    lines, newline, start, hits = locate(m)
    if hits != 1:
        return False, 'ANCHOR-MISS(hits=%d)' % hits
    if start < 0 or start + m.span > len(lines):
        return False, 'ANCHOR-MISS(offset 越界)'
    before = md5(m.path)
    mutated = lines[:start] + list(m.new_lines) + lines[start + m.span:]
    with open(m.path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(newline.join(mutated))
    if md5(m.path) == before:
        return False, 'NO-BYTE-CHANGE（变异未真正施加）'
    return True, 'ok'


def main() -> int:
    ap = argparse.ArgumentParser(description='报表行科目定位守卫的变异检验')
    ap.add_argument('--restore', action='store_true', help='仅从 .bak 还原并退出')
    ap.add_argument('--only', default='', help='只跑指定变异（逗号分隔 mid）')
    ap.add_argument(
        '--skip-live-only', action='store_true',
        help='跳过「预期红判据只有连库判据」的变异（CI 无库时必须加，否则会假红）',
    )
    args = ap.parse_args()

    targets = sorted({m.path for m in MUTATIONS})
    baks = {p: p + '.bak' for p in targets}

    if args.restore:
        for p, b in baks.items():
            if os.path.exists(b):
                shutil.copyfile(b, p)
                os.remove(b)
        print('restored')
        return 0

    for p, b in baks.items():
        assert not os.path.exists(b), (
            '%s 已存在（可能是别的会话的活体备份，不覆盖）' % b
        )
        shutil.copyfile(p, b)
    pristine = {p: md5(p) for p in targets}

    report: list[str] = []
    verdicts: list[tuple[str, str, int]] = []
    try:
        baselines: dict[str, tuple[set[str], dict]] = {}
        for runner in ('py', 'ts'):
            state, fails, summary = RUNNERS[runner]()
            assert state == 'ok', '%s 基线报告未生成: %s' % (runner, summary)
            baselines[runner] = (fails, summary)
            report.append('BASELINE[%s] %s' % (runner, summary))
            report.append('BASELINE[%s] failing names (%d):' % (runner, len(fails)))
            report.extend('  - %s' % n for n in sorted(fails))
        report.append('')

        selected = [m for m in MUTATIONS
                    if not args.only or m.mid in args.only.split(',')]
        if args.skip_live_only:
            skipped_live = [m.mid for m in selected if m.live_only]
            selected = [m for m in selected if not m.live_only]
            report.append(
                'SKIP-LIVE-ONLY: %s（预期红判据只有连库判据，本环境无真实库故不跑；'
                '这几条须在本地连库环境验证，见 Task 14 验收报告）' % (skipped_live or '无')
            )
            report.append('')
        for m in selected:
            ok, note = apply_mutation(m)
            if not ok:
                verdicts.append((m.mid, note, 0))
                report.append('%s [%s] %s -> %s' % (m.mid, m.runner, m.desc, note))
                report.append('    expect: %s' % m.expect)
                report.append('')
                shutil.copyfile(baks[m.path], m.path)
                continue

            st, fails, summary = RUNNERS[m.runner]()
            shutil.copyfile(baks[m.path], m.path)
            assert md5(m.path) == pristine[m.path], '%s 还原后字节不一致' % m.path

            base_fails, base_sum = baselines[m.runner]
            if st == 'no-report':
                verdict = 'NO-REPORT(整文件零断言执行)'
                new: set[str] = set()
            elif summary.get('total', 0) < base_sum.get('total', 0) * _COUNT_FLOOR:
                verdict = 'NO-REPORT(用例总数骤降 %s→%s)' % (
                    base_sum.get('total'), summary.get('total'))
                new = set()
            else:
                new = fails - base_fails
                gone = base_fails - fails
                if new:
                    verdict = 'RED'
                elif gone:
                    verdict = 'RED(基线红转绿，亦为有效信号)'
                else:
                    verdict = 'GREEN(守卫缺陷)'
            verdicts.append((m.mid, verdict, len(new)))
            report.append('%s [%s] %s -> %s  new_fails=%d  %s' % (
                m.mid, m.runner, m.desc, verdict, len(new), summary))
            report.append('    expect: %s' % m.expect)
            for n in sorted(new):
                report.append('    NEW RED: %s' % n)
            report.append('')
    finally:
        for p, b in baks.items():
            if os.path.exists(b):
                shutil.copyfile(b, p)
                os.remove(b)
        residual = [b for b in baks.values() if os.path.exists(b)]
        restored = all(md5(p) == pristine[p] for p in targets)
        report.append('RESTORE: md5 一致=%s  .bak 残留=%s' % (restored, residual))
        for leftover in (os.path.join(ROOT, PY_XML), os.path.join(FE, TS_JSON)):
            if os.path.exists(leftover):
                os.remove(leftover)

    red = sum(1 for _, v, _ in verdicts if v.startswith('RED'))
    report.append('SUMMARY: %d/%d RED' % (red, len(verdicts)))
    for mid, v, n in verdicts:
        report.append('  %s = %s (new=%d)' % (mid, v, n))

    out_path = os.path.join(ROOT, 'tmp_report_line_mutate_report.txt')
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(report) + '\n')
    print('report -> %s' % out_path)
    print('SUMMARY: %d/%d RED' % (red, len(verdicts)))
    return 0 if red == len(verdicts) else 1


if __name__ == '__main__':
    sys.exit(main())
