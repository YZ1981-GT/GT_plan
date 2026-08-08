/**
 * 结论确认门控统一出口 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 3.4, 4.3, 5.1, 5.2, 5.3, 11.1, 11.2, 11.3
 * Properties: Property 8, Property 10, Property 12, Property 14, Property 26
 *
 * 三处新门控（未检查处置 / 偏差性质 / 完整性核对）必须收敛到**同一个**
 * `conclusionBlockedReason` 计算链。平台已登记铁律：门控提示指向被弹窗遮挡的区域
 * 等于死信，故消费方只能用它做「前置 disable + tooltip」。
 *
 * 本文件不挂载组件（引擎组件 1163 行且依赖大量 provide），改为源码级接线断言 +
 * 纯函数行为断言的组合 —— 这与「守卫必须能抓住调用点传错」的判据一致。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { resolveUncheckedDisposition } from '../composables/samplingUncheckedDisposition'
import { summarizeDeviationNature } from '../composables/samplingDeviationNature'
import type { SampledVoucher } from '../composables/useSamplingAlgorithms'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'routers', 'voucher_sampling.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('未找到仓库根（双哨兵均未命中）')
}

//: 行尾统一归一为 LF —— 仓库里 .ts 是 CRLF，任何含 `\n` 的字面量断言在未归一时必失效。
const SRC = fs
  .readFileSync(
    path.join(
      repoRoot(),
      'audit-platform/frontend/src/components/workpaper/composables/useVoucherSampling.ts',
    ),
    'utf-8',
  )
  .replace(/\r\n/g, '\n')

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 该块看起来是函数体（含语句特征）而不是类型注解字面量。 */
function looksLikeBody(block: string): boolean {
  return /\b(return|const|let|await|if|for|switch)\b/.test(block)
}

/**
 * 截出某 computed/function 的体（花括号配对）。
 *
 * **不能直接取声明后第一个 `{`**：平台已登记的坑 —— 带内联返回类型注解的函数
 * （`function f(): { a: X; b: Y } {`）第一个 `{` 是类型字面量，截出来的"函数体"是那段
 * 类型，导致后续所有断言在一段无关文本上求值（表现为莫名打红或静默通过）。
 * 故逐个候选 `{` 尝试配对，取第一个**含语句特征**的块。
 */
function blockOf(src: string, decl: string): string {
  const at = src.indexOf(decl)
  if (at < 0) throw new Error(`未找到声明：${decl}`)
  let cursor = at
  for (let attempt = 0; attempt < 6; attempt++) {
    const open = src.indexOf('{', cursor)
    if (open < 0) break
    let depth = 0
    for (let j = open; j < src.length; j++) {
      if (src[j] === '{') depth++
      else if (src[j] === '}') {
        depth--
        if (depth === 0) {
          const block = src.slice(open, j + 1)
          if (looksLikeBody(block)) return block
          cursor = j + 1
          break
        }
      }
    }
    if (depth !== 0) break
  }
  throw new Error(`未截到函数体（可能全是类型注解）：${decl}`)
}

const sample = (over: Partial<SampledVoucher> = {}): SampledVoucher => ({
  voucherNo: 'V-1',
  voucherDate: '2025-06-01',
  summary: null,
  debitAmount: '1000.00',
  creditAmount: null,
  accountCode: '1122',
  accountName: null,
  counterpartAccount: null,
  voucherType: null,
  accountingPeriod: 6,
  checkResult: '',
  abnormal: false,
  remark: '',
  selected: true,
  phase: 'final',
  editTrail: [],
  ...over,
})

// ─── 门控统一出口（源码级）───────────────────────────────────────────────────

describe('门控收敛到单一出口', () => {
  const body = stripComments(blockOf(SRC, 'const conclusionBlockedReason = computed'))

  it('三处门控全部在 conclusionBlockedReason 内', () => {
    expect(body).toContain('uncheckedResolution')
    expect(body).toContain('deviationResolution')
    expect(body).toContain('reconcileBlockedReason')
  })

  it('可确认时返回 null（而非空串或 false，避免 falsy 混淆）', () => {
    expect(body.trimEnd().endsWith('return null\n  }')).toBe(true)
  })

  it('自检：blockOf 会跳过内联返回类型注解，截到真正的函数体', () => {
    const fake = [
      'function f(): {',
      '  a: number',
      '} {',
      '  const x = 1',
      '  return x',
      '}',
    ].join('\n')
    const got = blockOf(fake, 'function f')
    expect(got).toContain('const x = 1')
    expect(got).not.toContain('a: number')
  })

  /**
   * 判据必须断言**条件形态**而不是「字符串出现过」。
   *
   * 变异检验实证：把 `if (unchecked.pending.length > 0)` 改成 `if (false)` 时，
   * `toContain('unchecked.pending.length')` 仍然通过 —— 因为该表达式在返回消息的
   * 模板字符串里也出现（`有 ${unchecked.pending.length} 笔…`）。这类「删掉判断」的
   * 核心变异会静默逃逸，与已登记的 `toContain('<Foo')` 被 `<FooREMOVED` 骗过同源。
   */
  it.each([
    ['未检查样本未选处置', /if\s*\(\s*unchecked\.pending\.length\s*>\s*0\s*\)/],
    ['替代程序缺说明', /if\s*\(\s*unchecked\.missingNote\.length\s*>\s*0\s*\)/],
    ['偏差未标注性质', /if\s*\(\s*dev\.unannotated\.length\s*>\s*0\s*\)/],
    ['需说明性质缺说明', /if\s*\(\s*dev\.missingExplanation\.length\s*>\s*0\s*\)/],
  ])('阻断条件存在且形态正确：%s', (_label, re) => {
    expect(body).toMatch(re)
  })

  it('自检：条件形态判据对「if (false)」必打红（防 toContain 式误判）', () => {
    const mutated = body.replace(
      /if\s*\(\s*unchecked\.pending\.length\s*>\s*0\s*\)/,
      'if (false)',
    )
    expect(mutated).not.toMatch(/if\s*\(\s*unchecked\.pending\.length\s*>\s*0\s*\)/)
    // 而弱判据仍会通过 —— 这正是本自检要钉死的差别
    expect(mutated).toContain('unchecked.pending.length')
  })

  it('完整性核对：理由长度下限 10 字（R5.3）', () => {
    expect(body).toMatch(/reconcileOverrideReason\.value\.trim\(\)\.length\s*<\s*10/)
  })

  it('每条阻断原因都是可读中文（供 tooltip 直接展示）', () => {
    const messages = [...body.matchAll(/return\s*\(?\s*`?([^`\n]*[\u4e00-\u9fa5][^`\n]*)/g)]
    expect(messages.length).toBeGreaterThanOrEqual(4)
  })

  it('自检：块截取非空且确实是该 computed', () => {
    expect(body.length).toBeGreaterThan(300)
    expect(body).toContain('CAS 1314')
  })
})

// ─── 视同偏差接入推断（源码级）───────────────────────────────────────────────

describe('未检查样本处置改写必须早于未检查过滤', () => {
  const body = stripComments(blockOf(SRC, 'function inferMisstatement'))

  // 2026-08-08 Task 19：调用点由 `applyDeviationTreatment` 换为统一入口
  // `applyUncheckedDisposition`（同时处置视同偏差与已实施替代程序，见 R3.3）。
  // 判据形态不变（改写必须早于过滤），只把符号改成新入口，并禁旧符号回潮 ——
  // 只改写视同偏差会让替代程序样本既不进分子也不进分母。
  it('applyUncheckedDisposition 在 filter 之前', () => {
    const treat = body.indexOf('applyUncheckedDisposition')
    const filter = body.indexOf("filter(v => v.checkResult !== '')")
    expect(treat).toBeGreaterThan(-1)
    expect(filter).toBeGreaterThan(-1)
    expect(treat).toBeLessThan(filter)
  })

  it('调用点不得只处置视同偏差（防回退）', () => {
    expect(body).not.toContain('applyDeviationTreatment')
  })

  it('过滤的是改写后的数组（treated）而非原始 sampledVouchers', () => {
    expect(body).toMatch(/const samples = treated\.filter/)
  })

  it('分层评价受灰度开关门控且异常回退 legacy', () => {
    expect(body).toContain('strataEvaluationEnabled')
    expect(body).toContain('stratifiedFallback')
    expect(body).toContain('projectMisstatementByStrata')
  })
})

// ─── 载荷接线（源码级）──────────────────────────────────────────────────────

describe('Wave 2 三项进评价载荷', () => {
  const body = stripComments(blockOf(SRC, 'function buildEvaluationPayload'))

  it.each([
    'unchecked_disposition',
    'deviation_nature_summary',
    'stratified_evaluation',
    'reconcile_override_reason',
  ])('载荷含 %s', key => {
    expect(body).toContain(`${key}:`)
  })

  it('视同偏差计入 deviation_count', () => {
    expect(body).toContain('countTreatedAsDeviation')
  })

  it('未启用分层评价时该键为 null（不发空对象）', () => {
    expect(body).toMatch(/stratifiedDetail\.value[\s\S]{0,400}:\s*null/)
  })

  it('放行理由为空白时归一为 null', () => {
    expect(body).toMatch(/reconcileOverrideReason\.value\.trim\(\)\s*\|\|\s*null/)
  })
})

// ─── Property 26：全关闭时零阻断 ─────────────────────────────────────────────

describe('Property 26：无未检查样本 + 无偏差 + 核对通过 ⇒ 零阻断', () => {
  it('两个 resolution 均为空集合', () => {
    const samples = [
      sample({ voucherNo: 'A', checkResult: 'Y' }),
      sample({ voucherNo: 'B', checkResult: 'Y' }),
    ]
    const u = resolveUncheckedDisposition(samples, {})
    const d = summarizeDeviationNature(samples, {})
    expect(u.pending).toEqual([])
    expect(u.missingNote).toEqual([])
    expect(d.unannotated).toEqual([])
    expect(d.missingExplanation).toEqual([])
  })

  it('reconcileBlockedReason 默认为 null（未注入即不阻断，零回归）', () => {
    const decl = SRC.match(/const reconcileBlockedReason = ref<string \| null>\((.*?)\)/)
    expect(decl, '未找到 reconcileBlockedReason 声明').toBeTruthy()
    expect(decl![1].trim()).toBe('null')
  })

  it('灰度开关默认关闭（分层评价不改变已有项目数字）', () => {
    const body = stripComments(SRC)
    expect(body).toContain('VITE_SAMPLING_STRATA_EVALUATION_ENABLED')
    // 只有显式 'true' 才开启 → 未配置即关闭
    expect(body).toMatch(/toLowerCase\(\)\s*===\s*\n?\s*'true'/)
  })
})

// ─── 反向自检 ────────────────────────────────────────────────────────────────

describe('反向自检', () => {
  it('复现旧门控（只看 conclusionConfirmed）会缺三处判据', () => {
    const legacy = `{
      if (!conclusionConfirmed.value) return '请先确认抽样结论'
      return null
    }`
    expect(legacy).not.toContain('uncheckedResolution')
    expect(legacy).not.toContain('deviationResolution')
    expect(legacy).not.toContain('reconcileBlockedReason')
  })

  it('复现旧推断（不做视同偏差改写）会让顺序断言失效', () => {
    const legacy = `{
      const samples = sampledVouchers.value.filter(v => v.checkResult !== '')
    }`
    expect(legacy).not.toContain('applyDeviationTreatment')
  })

  it('自检：stripComments 生效', () => {
    expect(stripComments('a // uncheckedResolution\nb')).not.toContain('uncheckedResolution')
  })
})
