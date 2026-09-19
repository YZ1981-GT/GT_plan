"""Task 20（裁剪充分性复核视图）守卫变异检验。

spec: procedure-trimming-and-delegation-intelligence — Task 20
被测守卫:
  audit-platform/frontend/src/views/__tests__/trimAdequacyReview.spec.ts
  audit-platform/frontend/src/views/__tests__/trimDecisionWiring.spec.ts（受影响面）

## 为什么必须做变异检验

守卫**红/绿两种结果都不可信**，除非证明过「把实现改坏时它真会红」。平台已多次实证：
判据的扫描面与它声称覆盖的输入空间不一致时，缺陷既可能表现为假红（正则失配、
substring 误命中），也可能表现为假绿（未剥注释、被自己的说明文字骗过、锚点未命中）。

## 判定四态（不看退出码）

按**失败测试名集合求差集**：

- ``RED``          new_fails 非空 ⇒ 变异有效、守卫承重
- ``GREEN``        new_fails 为空 ⇒ **守卫缺陷**（变异生效了但没人发现）
- ``ANCHOR-MISS``  锚点未命中或命中 != 1 ⇒ **脚本缺陷**，变异根本没施加
                   （此时"测试仍绿"不能作任何结论）
- ``WRONG-TEST``   打红了但预期那条没红 ⇒ 判据错行 / 污染残留
- ``NO-JSON``      整文件 collection error 或 JSON 未生成（第五态：零断言执行）

## 锚点铁律

- **行级唯一**（``splitlines()`` + 行内 needle 匹配 + ``hits == 1`` + 相对 offset）
- 锚点里**禁含 ``\\n``**：本工作树 CRLF，跨行字面量必 MISS
- 变异后断言字节确实变了（未变则"测试仍绿"无意义）

## 还原

``.bak`` 备份 + ``try/finally`` 无条件写回 + md5 字节级核验 + ``.bak`` 零残留。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
FE = os.path.join(ROOT, 'audit-platform', 'frontend')

VUE = os.path.join(FE, 'src', 'views', 'ProcedureTrimming.vue')
TS = os.path.join(FE, 'src', 'components', 'workpaper', 'composables', 'trimAdequacyReview.ts')
CMP = os.path.join(FE, 'src', 'components', 'workpaper', 'trim', 'GtTrimAdequacyReview.vue')

SPECS = [
    'src/views/__tests__/trimAdequacyReview.spec.ts',
    'src/views/__tests__/trimDecisionWiring.spec.ts',
]
OUT_JSON = 'tmp_mutate_task20.json'


@dataclass
class Mutation:
    mid: str
    path: str
    desc: str
    anchor: str
    """行内唯一 needle（禁含换行）。"""
    offset: int = 0
    """相对锚点行的偏移（0 = 锚点行本身）。"""
    span: int = 1
    """从 offset 起替换多少行。"""
    new_lines: list[str] = field(default_factory=list)
    expect: str = ''
    """预期打红的判据说明（人读，用于 WRONG-TEST 归因）。"""


MUTATIONS: list[Mutation] = [
    Mutation(
        'M1', CMP, '复核组件引入并调用写入入口（破只读）',
        anchor="import { computed } from 'vue'",
        span=1,
        new_lines=[
            "import { computed } from 'vue'",
            "import { canonicalTrimApply } from '@/services/commonApi'",
            "void canonicalTrimApply",
        ],
        expect='判据 A：不 import api 模块 / 不出现写入函数名',
    ),
    Mutation(
        'M2', TS, '已确认那道闸自己求和（不走 evaluateAggregateGate）',
        anchor='  const confirmedGate = evaluateAggregateGate({',
        span=4,
        new_lines=[
            '  let _t = 0',
            '  for (const it of args.confirmedItems) _t += Math.abs(it.amount)',
            '  const confirmedGate = {',
            '    applicable: performanceMateriality !== null,',
            '    distinctAccountCount: args.confirmedItems.length,',
            '    totalAmount: _t,',
            '    threshold: performanceMateriality,',
            '    blocked: performanceMateriality !== null && _t >= performanceMateriality,',
            "    narrative: '',",
            '  }',
        ],
        expect='判据 B：两道闸都必须走 evaluateAggregateGate；且不得自己 Math.abs 求和',
    ),
    Mutation(
        'M3', VUE, '复核视图另构造一份建议项（第二真源）',
        anchor='  suggestedGateItems: suggestedGateItems.value,',
        span=1,
        new_lines=[
            "  suggestedGateItems: suggestedRows.value.map(p => ({",
            "    accountName: String(p.wp_code ?? ''),",
            '    amount: 0,',
            "    reasonCode: String(p._suggestReasonCode ?? ''),",
            '  })),',
        ],
        expect='判据 B：复核视图入参必须用同一批 suggestedGateItems',
    ),
    Mutation(
        'M4', TS, '未加载循环的待确认数补成 0',
        anchor='        suggested: null,',
        span=1,
        new_lines=['        suggested: 0,'],
        expect='判据 C：未加载循环 suggested 必须为 null',
    ),
    Mutation(
        'M5', VUE, '非当前循环的待确认数补成 0',
        anchor='    suggested: isActive && loaded ? suggestionStats.value.suggested : null,',
        span=1,
        new_lines=['    suggested: isActive && loaded ? suggestionStats.value.suggested : 0,'],
        expect='判据 C：不可派生循环 suggested 必须为 null（宿主结构 + 行为）',
    ),
    Mutation(
        'M6', TS, '重要性未确定时仍给出「合计低于重要性」结论',
        anchor='    return `本项目尚未确定实际执行重要性，无法对因金额原因裁剪的科目做汇总评估。`',
        span=4,
        new_lines=[
            "    return `已确认的金额类裁剪 ${confirmedCount} 项，`",
            "      + '合计低于该水平，汇总错报敞口在可容忍范围内。'",
            '      + (unknownNote ? ` ${unknownNote}` : \'\')',
        ],
        expect='判据 C：未确定重要性时不得宣称"合计低于"，且须含"尚未确定实际执行重要性"',
    ),
    Mutation(
        'M7', TS, '金额无法定位的按 0 计入合计（汇总额偏低）',
        anchor='          amountUnknownCount += 1',
        span=1,
        new_lines=[
            '          confirmedItems.push({',
            '            accountName: text(row.accountName) || text(row.wpCode),',
            '            amount: 0,',
            '            reasonCode: code,',
            '          })',
        ],
        expect='判据 C：amountUnknownCount 必须单独计、不得占去重槽位',
    ),
    Mutation(
        'M8', VUE, '覆盖表读取失败当成「全部平台默认」',
        anchor='const reviewPlatformDefaults = computed',
        offset=1,
        span=1,
        new_lines=['  if (completenessOverrides.value === null) return []'],
        expect='判据 C：未知态必须传 null（结构断言 return null）',
    ),
    Mutation(
        'M9', TS, '移除 riskKnown 前置（把未评估当成高风险）',
        anchor='  if (!row.riskKnown) return false',
        span=1,
        new_lines=['  if (false) return false'],
        expect='判据 D：风险维度不可用时不得产出高风险异常',
    ),
    Mutation(
        'M10', TS, '缺理由判据改看理由码（存量自由文本被误判成缺理由）',
        anchor="  return row.trimmed === true && text(row.skipReason) === ''",
        span=1,
        new_lines=['  return row.trimmed === true && row.reasonCode === null'],
        expect='判据 D / B：缺理由口径必须与裁剪页概览一致（看 skipReason）',
    ),
    Mutation(
        'M11', VUE, '定位只切 Tab 不过滤到该条',
        anchor='  searchText.value = payload.wpCode',
        span=1,
        new_lines=['  void payload.wpCode'],
        expect='判据 F + 行为级：定位必须过滤到该条并高亮',
    ),
    Mutation(
        'M12', VUE, '复核组件标签改名（模板宿主实际不存在）',
        anchor='      <GtTrimAdequacyReview',
        span=1,
        new_lines=['      <GtTrimAdequacyReviewXX'],
        expect='判据 E：组件必须真的挂在宿主模板上（定界符判据）',
    ),
    Mutation(
        'M13', VUE, '去掉循环覆盖门控（跨循环解析科目，张冠李戴）',
        anchor='  const covered = ctx !== null && trimContextCycles.value.has',
        span=1,
        new_lines=['  const covered = ctx !== null'],
        expect='判据 D：toReviewRow 必须以 trimContextCycles 门控',
    ),
    Mutation(
        'M14', TS, '平台默认异常的 detail 塌成一句结论词（丢掉审计依据）',
        anchor="        detail: `平台默认${pd.sensitiveByDefault ? '视为' : '不视为'}完整性敏感 —— 依据：`",
        span=4,
        new_lines=["        detail: '未经确认',"],
        expect='判据 D：detail 必须含审计依据原文且长度 >= 40',
    ),
]


def md5(path: str) -> str:
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()


def run_specs() -> tuple[str, set[str], dict]:
    """跑守卫，返回 (state, 失败测试名集合, 摘要)。

    state: 'ok' | 'no-json'
    """
    out_path = os.path.join(FE, OUT_JSON)
    if os.path.exists(out_path):
        os.remove(out_path)
    # 🔴 `npm exec vitest` 传 flag 必须有 `--` 分隔符，否则 npm 把 --reporter 当自己的
    #    cli config，JSON 根本不生成而退出码仍 0。
    # 跨平台：Windows 的 npm 实为 npm.cmd（须经 cmd /c），POSIX 上 shell=True + 列表参数
    #  只会执行 npm 本身、不带任何参数 ⇒ JSON 不生成 ⇒ no-json（Task 24 实证）。
    _npm = ['cmd', '/c', 'npm'] if os.name == 'nt' else ['npm']
    cmd = [*_npm, 'exec', 'vitest', '--', 'run', *SPECS,
           '--reporter=json', '--outputFile=%s' % OUT_JSON]
    proc = subprocess.run(cmd, cwd=FE, capture_output=True, text=True)
    if not os.path.exists(out_path):
        return 'no-json', set(), {'exit': proc.returncode,
                                  'stderr': (proc.stderr or '')[-1200:]}
    with open(out_path, encoding='utf-8') as fh:
        data = json.load(fh)
    fails: set[str] = set()
    total = passed = failed = 0
    for res in data.get('testResults', []):
        for a in res.get('assertionResults', []):
            total += 1
            st = a.get('status')
            if st == 'passed':
                passed += 1
            elif st == 'failed':
                failed += 1
                fails.add(a.get('fullName') or a.get('title') or '?')
    return 'ok', fails, {'total': total, 'passed': passed, 'failed': failed,
                         'suites': len(data.get('testResults', []))}


def locate(path: str, m: Mutation) -> tuple[list[str], int, int]:
    """返回 (lines, 目标起始索引, 命中数)。锚点必须行级唯一。"""
    assert '\n' not in m.anchor, 'anchor 含换行（CRLF 工作树必 MISS）'
    with open(path, encoding='utf-8') as fh:
        raw = fh.read()
    newline = '\r\n' if '\r\n' in raw else '\n'
    lines = raw.split(newline)
    hits = [i for i, l in enumerate(lines) if m.anchor in l]
    return lines, (hits[0] + m.offset if len(hits) == 1 else -1), len(hits)


def apply_mutation(m: Mutation) -> tuple[bool, str]:
    with open(m.path, encoding='utf-8') as fh:
        raw = fh.read()
    newline = '\r\n' if '\r\n' in raw else '\n'
    lines, start, hits = locate(m.path, m)
    if hits != 1:
        return False, 'ANCHOR-MISS(hits=%d)' % hits
    before = md5(m.path)
    mutated = lines[:start] + list(m.new_lines) + lines[start + m.span:]
    with open(m.path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(newline.join(mutated))
    after = md5(m.path)
    if before == after:
        return False, 'NO-BYTE-CHANGE（变异未真正施加）'
    return True, 'ok'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--restore', action='store_true', help='仅从 .bak 还原并退出')
    ap.add_argument('--only', default='', help='只跑指定变异（逗号分隔 mid）')
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
        assert not os.path.exists(b), '%s 已存在（可能是别的会话的活体备份，不覆盖）' % b
        shutil.copyfile(p, b)
    pristine = {p: md5(p) for p in targets}

    report: list[str] = []
    verdicts: list[tuple[str, str, int]] = []
    try:
        state, base_fails, base_sum = run_specs()
        assert state == 'ok', '基线 JSON 未生成: %s' % base_sum
        report.append('BASELINE %s' % base_sum)
        report.append('BASELINE failing names (%d):' % len(base_fails))
        report.extend('  - %s' % n for n in sorted(base_fails))
        report.append('')

        selected = [m for m in MUTATIONS
                    if not args.only or m.mid in args.only.split(',')]
        for m in selected:
            ok, note = apply_mutation(m)
            if not ok:
                verdicts.append((m.mid, note, 0))
                report.append('%s %s -> %s :: %s' % (m.mid, m.desc, note, m.expect))
                shutil.copyfile(baks[m.path], m.path)
                continue
            st, fails, summary = run_specs()
            shutil.copyfile(baks[m.path], m.path)
            assert md5(m.path) == pristine[m.path], '%s 还原后字节不一致' % m.path

            if st == 'no-json':
                verdict = 'NO-JSON(整文件零断言执行)'
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
            report.append('%s %s -> %s  new_fails=%d  %s' % (
                m.mid, m.desc, verdict, len(new), summary))
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
        out = os.path.join(FE, OUT_JSON)
        if os.path.exists(out):
            os.remove(out)

    red = sum(1 for _, v, _ in verdicts if v.startswith('RED'))
    report.append('SUMMARY: %d/%d RED' % (red, len(verdicts)))
    for mid, v, n in verdicts:
        report.append('  %s = %s (new=%d)' % (mid, v, n))
    path = os.path.join(ROOT, 'tmp_t20_mutate_report.txt')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(report))
    return 0 if red == len(verdicts) else 1


if __name__ == '__main__':
    sys.exit(main())
