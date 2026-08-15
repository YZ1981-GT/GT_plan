/**
 * 决策内核对金额来源的**中立性**守卫。
 *
 * Feature: procedure-trim-report-line-account-resolution — Task 3（Wave 1 打红）
 * Requirements: 5.4, 6.1, 6.4, 7.1
 * Validates: Property 15（未命中零回归且九档语义不变）,
 *            Property 16（溯源字段齐备且不新建第二套）
 *
 * ═══ 这条守卫在防什么 ═══
 *
 * `procedure-trimming-and-delegation-intelligence` 已收口（26/26，含 12 条变异检验）。
 * 本 spec 只改「`accountAmount` 从哪来」，**不动 9 档顺序、不动短路语义、不新增档位**。
 * 新增的 `amountSource` / `reportLine` 是**纯溯源字段**：进 evidence，不参与任何判断。
 *
 * 若九档里哪一档的条件表达式引用了它们，就等于「金额从哪来」会改变裁剪结论 ——
 * 那是审计上说不通的（同一个金额，因为取数路径不同而得出不同结论），
 * 且会让改造前后的行为无法做零回归对照。
 *
 * ═══ 断言分两类 ═══
 *
 * - **类 A = 独立口径判据**：`decideTrim` 的档位标识有序序列、`if` 条件个数、
 *   `buildEvidence` 现有字段清单、`stripComments` 反向自检。**现在就应全绿**。
 * - **类 B = 被测实现**：`amountSource` / `reportLine` 的存在与中立性。
 *   **Task 11 之前应全红**。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

import { decideTrim, type TrimDecisionInput } from '../procedureTrimDecision'

const NOT_IMPLEMENTED = '尚未实现（Task 11）。本条红是预期的 Wave 1 打红结果'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 10; i += 1) {
    if (fs.existsSync(path.join(dir, '.kiro'))) return dir
    dir = path.dirname(dir)
  }
  throw new Error('未定位到仓库根（.kiro 不存在）')
}

const P_DECISION = path.join(
  repoRoot(), 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
  'composables', 'procedureTrimDecision.ts',
)

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/** 带字符串状态的注释剥离（与既有裁剪守卫同款）。 */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') { out += n ?? ''; i += 2; continue }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i += 1; continue }
    if (c === '/' && n === '/') { while (i < src.length && src[i] !== '\n') i += 1; continue }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    out += c
    i += 1
  }
  return out
}

/**
 * 截取具名函数的**函数体**（花括号配对 + 语句特征筛选）。
 *
 * 🔴 不能用「声明后第一个 `{`」—— 参数列表里的解构/内联对象类型
 * （`materialityBasis: TrimEvidence['materialityBasis'] = null`）与内联返回类型注解
 * 都会骗到它。
 */
function fnBody(src: string, decl: RegExp): string {
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  let from = m.index + m[0].length
  for (let guard = 0; guard < 12; guard += 1) {
    const open = src.indexOf('{', from)
    if (open < 0) return ''
    let depth = 0
    let end = -1
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1
      else if (src[i] === '}') {
        depth -= 1
        if (depth === 0) { end = i; break }
      }
    }
    if (end < 0) return ''
    const block = src.slice(open, end + 1)
    if (/\b(return|const|let|await|if|for|throw)\b/.test(block)) return block
    from = end + 1
  }
  return ''
}

/** 截取 `export interface NAME {...}` 的花括号块。 */
function interfaceBody(src: string, name: string): string {
  const m = src.match(new RegExp(`export interface\\s+${name}\\s*\\{`))
  if (!m || m.index === undefined) return ''
  const open = src.indexOf('{', m.index)
  let depth = 0
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  return ''
}

function countOf(hay: string, needle: string): number {
  return hay.split(needle).length - 1
}

const RAW = read(P_DECISION)
const CLEAN = stripComments(RAW)
const FN_DECIDE = fnBody(CLEAN, /export function decideTrim\b/)
const FN_BUILD_EVIDENCE = fnBody(CLEAN, /function buildEvidence\b/)
const IF_INPUT = interfaceBody(CLEAN, 'TrimDecisionInput')
const IF_EVIDENCE = interfaceBody(CLEAN, 'TrimEvidence')
/**
 * 报表行溯源的字段声明块。
 *
 * 🔴 四项（rowCode / rowName / formula / standardCodes）落在**独立 interface**
 * `TrimReportLineTrace` 里而不是内联进 Input / Evidence —— 内联要写两遍，
 * 两遍之后就会漂移（改一处忘一处，而两侧各自的类型检查都过）。
 * 故本文件的「溯源含四项」判据扫描面必须包含这个独立块，否则会以「缺 rowCode」
 * 的形态**假红**（本文件初版实测踩到）。
 */
const IF_TRACE = interfaceBody(CLEAN, 'TrimReportLineTrace')

/**
 * 🔴 档位标识的**有序**清单（`buildEvidence(seed, 'xxx')` 的第二实参序列）。
 *
 * 比抽 `if` 条件文本更稳：条件文本会因格式化变动，而档位标识是语义锚。
 * 顺序即短路顺序 —— 数量或顺序变了就说明档位被增删或重排（R5.4 禁止）。
 */
function decidedBySequence(body: string): string[] {
  return Array.from(body.matchAll(/buildEvidence\(\s*seed\s*,\s*'([a-z_]+)'/g)).map(m => m[1])
}

/** 改造前冻结的 9 档 / 14 个档位标识（2026-08-15 实测）。 */
const FROZEN_DECIDED_BY: readonly string[] = [
  'risk_protection',
  'mandatory',
  'non_data_driven_cycle_mandatory',
  'execution_progress',
  'manual_reason',
  'workpaper_entry',
  'suggestion_rejected',
  'non_balance_driven_cycle',
  'no_data',
  'completeness_exemption',
  'materiality_unavailable',
  'below_trivial',
  'below_materiality',
  'default_keep',
]

// ═══════════════════════════════════════════════════════════════════════════
// 类 A：判据基础设施 + 九档冻结基线（现在应全绿）
// ═══════════════════════════════════════════════════════════════════════════
describe('类 A：判据基础设施自检', () => {
  it('stripComments 剥注释、保留字符串字面量', () => {
    const s = `
// 注释提到 amountSource 与 reportLine
/* 块注释也提到 report_line */
const K = 'amountSource'
`
    const out = stripComments(s)
    expect(out, '行注释未剥').not.toContain('注释提到')
    expect(out, '块注释未剥').not.toContain('块注释也提到')
    expect(out, '字符串字面量被误剥').toContain("'amountSource'")
  })

  it('反向自检：raw 命中数 > clean 命中数', () => {
    // 本模块 docstring 大量提到 `accountAmount` / `materiality`（设计说明）。
    const rawHits = countOf(RAW, 'accountAmount')
    const cleanHits = countOf(CLEAN, 'accountAmount')
    expect(rawHits, 'RAW 未命中锚点').toBeGreaterThan(0)
    expect(rawHits, 'raw 与 clean 命中数相同 ⇒ 注释未剥，源码级判据空转')
      .toBeGreaterThan(cleanHits)
  })

  it('fnBody 截到 decideTrim 与 buildEvidence 的函数体', () => {
    expect(FN_DECIDE, 'decideTrim 函数体截取失败').toContain('BALANCE_DRIVEN_CYCLES')
    expect(FN_BUILD_EVIDENCE, 'buildEvidence 函数体截取失败').toContain('materialityBasis')
    // 🔴 反向自检：buildEvidence 的参数列表含 `TrimEvidence['materialityBasis']`，
    //    若 fnBody 被参数里的方括号/内联类型骗到，截出的块不会含 return 语句。
    expect(FN_BUILD_EVIDENCE, '截到的不是函数体（缺 return）').toContain('return {')
  })

  it('interfaceBody 截到两个接口块', () => {
    expect(IF_INPUT, 'TrimDecisionInput 截取失败').toContain('accountAmount')
    expect(IF_EVIDENCE, 'TrimEvidence 截取失败').toContain('decidedBy')
  })
})

describe('类 A：九档冻结基线（Task 11 之后必须完全相同）', () => {
  it('档位标识的数量与顺序与冻结基线逐字相同', () => {
    const seq = decidedBySequence(FN_DECIDE)
    expect(seq.length, `档位数从 ${FROZEN_DECIDED_BY.length} 变为 ${seq.length} —— R5.4 禁止增删档位`)
      .toBe(FROZEN_DECIDED_BY.length)
    expect(seq, '档位顺序被重排 —— 短路语义已变（R5.4 禁止）').toEqual([...FROZEN_DECIDED_BY])
  })

  it('完整性豁免（档 5）排在重要性判据（档 7/8）之前', () => {
    const seq = decidedBySequence(FN_DECIDE)
    const exempt = seq.indexOf('completeness_exemption')
    const trivial = seq.indexOf('below_trivial')
    const materiality = seq.indexOf('below_materiality')
    expect(exempt, '未找到完整性豁免档').toBeGreaterThanOrEqual(0)
    expect(exempt, '完整性豁免被排到重要性判据之后 —— 用金额豁免完整性方向就是反的')
      .toBeLessThan(trivial)
    expect(exempt).toBeLessThan(materiality)
  })

  it('风险保护（档 1）排在最前', () => {
    expect(decidedBySequence(FN_DECIDE)[0], '风险保护不再是第一档 —— 特别风险科目可能被裁')
      .toBe('risk_protection')
  })

  it('重要性两档恒为 suggest_trim（永不自动裁）', () => {
    const base = baseInput({ accountAmount: 100, materiality: { performanceMateriality: 1e6, trivialThreshold: 1e3 } })
    expect(decideTrim(base).verdict, '低于明显微小临界值竟自动裁').toBe('suggest_trim')
    const mid = decideTrim({
      ...base,
      accountAmount: 5000,
      materiality: { performanceMateriality: 1e6, trivialThreshold: 1e3 },
    })
    expect(mid.verdict, '低于实际执行重要性竟自动裁').toBe('suggest_trim')
    expect(mid.reasonCode).toBe('below_materiality')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 共享入参构造（改造前的合法最小入参 —— 不含任何新字段）
// ═══════════════════════════════════════════════════════════════════════════
function baseInput(overrides: Partial<TrimDecisionInput> = {}): TrimDecisionInput {
  return {
    procedure: {
      wpCode: 'D2-1',
      cycle: 'D',
      isMandatory: false,
      executionStatus: 'pending',
      hasManualReason: false,
      suggestionRejected: false,
      hasWorkpaperEntry: false,
    },
    accountAmount: null,
    subjectDataState: 'with_data',
    cycleHasData: true,
    materiality: null,
    risk: null,
    riskDimensionAvailable: false,
    completenessSensitiveCycle: false,
    completenessSource: 'cycle_default',
    ...overrides,
  } as TrimDecisionInput
}

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：溯源字段存在（Task 11 之前应红）
// ═══════════════════════════════════════════════════════════════════════════
describe('类 B：溯源字段 additive（Property 16 / R6.1 / R6.4）', () => {
  it('TrimDecisionInput 声明了 amountSource 与 reportLine', () => {
    expect(IF_INPUT.includes('amountSource'), `TrimDecisionInput 缺 amountSource —— ${NOT_IMPLEMENTED}`).toBe(true)
    expect(IF_INPUT.includes('reportLine'), `TrimDecisionInput 缺 reportLine —— ${NOT_IMPLEMENTED}`).toBe(true)
  })

  it('两个新字段都是可选的（additive，未消费方不受影响）', () => {
    // R5.5：新增字段必须可缺省，否则既有调用方（含所有单测）全部编译失败。
    expect(/amountSource\?\s*:/.test(IF_INPUT), 'amountSource 不是可选字段 —— 破坏 additive').toBe(true)
    expect(/reportLine\?\s*:/.test(IF_INPUT), 'reportLine 不是可选字段 —— 破坏 additive').toBe(true)
  })

  it('TrimEvidence 声明了 amountSource 与 reportLine', () => {
    expect(IF_EVIDENCE.includes('amountSource'), `TrimEvidence 缺 amountSource —— ${NOT_IMPLEMENTED}`).toBe(true)
    expect(IF_EVIDENCE.includes('reportLine'), `TrimEvidence 缺 reportLine —— ${NOT_IMPLEMENTED}`).toBe(true)
  })

  it('reportLine 溯源含四项（rowCode / rowName / formula / standardCodes）', () => {
    const seg = IF_INPUT + IF_EVIDENCE + IF_TRACE
    expect(seg, '三个声明块一个都没截到 —— 锚点已漂移').not.toBe('')
    for (const key of ['rowCode', 'rowName', 'formula', 'standardCodes']) {
      expect(seg.includes(key), `reportLine 溯源缺 ${key}（R6.1）—— ${NOT_IMPLEMENTED}`).toBe(true)
    }
  })

  it('溯源四项只声明一处（不内联两遍造成漂移）', () => {
    // Input 与 Evidence 都引用同一个 TrimReportLineTrace ⇒ 两处不可能分叉。
    expect(IF_TRACE, '未抽出独立的 TrimReportLineTrace').not.toBe('')
    expect(
      countOf(CLEAN, 'rowCode'),
      'rowCode 出现多次 —— 溯源结构被内联声明了两遍，改一处忘一处即漂移',
    ).toBeLessThanOrEqual(2)
  })

  it('不新建第二套溯源字段（信息落既有 TrimEvidence）', () => {
    // R6.4：不得另开一个 `TrimTraceability` / `evidenceV2` 之类的并行结构。
    expect(CLEAN, '出现了并行的第二套溯源接口').not.toMatch(/export interface Trim(Traceability|Provenance|EvidenceV2)/)
  })

  it('evidence 真的带上了这两个字段（行为级）', () => {
    const d = decideTrim(baseInput({
      amountSource: 'report_line',
      reportLine: {
        rowCode: 'BS-002', rowName: '货币资金',
        formula: "TB('1001','期末余额')", standardCodes: ['1001'],
      },
    } as Partial<TrimDecisionInput>))
    expect((d.evidence as any).amountSource, `evidence 未带 amountSource —— ${NOT_IMPLEMENTED}`).toBe('report_line')
    expect((d.evidence as any).reportLine?.rowCode, `evidence 未带 reportLine —— ${NOT_IMPLEMENTED}`).toBe('BS-002')
    expect((d.evidence as any).reportLine?.standardCodes).toEqual(['1001'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：中立性 —— 九档条件不得引用新字段（Property 15 / R5.4）
// ═══════════════════════════════════════════════════════════════════════════
describe('类 B：决策内核对金额来源中立（源码级）', () => {
  it('decideTrim 函数体内零出现 amountSource / reportLine', () => {
    // 🔴 这是最关键的一条：两个字段由 buildEvidence 从 seed.input 取，
    //    decideTrim 的函数体压根不该提到它们。只要出现一次，就有可能被写进某档条件。
    expect(FN_DECIDE, '尚未截到 decideTrim 函数体').not.toBe('')
    expect(
      countOf(FN_DECIDE, 'amountSource'),
      'decideTrim 函数体引用了 amountSource —— 金额来源会改变裁剪结论（R5.4 禁止）',
    ).toBe(0)
    expect(
      countOf(FN_DECIDE, 'reportLine'),
      'decideTrim 函数体引用了 reportLine —— 金额来源会改变裁剪结论（R5.4 禁止）',
    ).toBe(0)
  })

  it('buildEvidence 函数体内出现这两个字段（那才是它们唯一的去处）', () => {
    expect(
      FN_BUILD_EVIDENCE.includes('amountSource'),
      `buildEvidence 未写入 amountSource —— evidence 拿不到溯源（${NOT_IMPLEMENTED}）`,
    ).toBe(true)
    expect(
      FN_BUILD_EVIDENCE.includes('reportLine'),
      `buildEvidence 未写入 reportLine —— evidence 拿不到溯源（${NOT_IMPLEMENTED}）`,
    ).toBe(true)
  })

  it('任何 if / 三元条件里都不出现这两个字段（全模块扫）', () => {
    // 补一层：即便有人把判断挪到 buildEvidence 或工具函数里，也要打红。
    const lines = CLEAN.split('\n')
    const offenders: string[] = []
    lines.forEach((line, idx) => {
      if (!/amountSource|reportLine/.test(line)) return
      // 允许：接口声明、buildEvidence 里的赋值（`amountSource: ...`）
      if (/^\s*(\/\/|\*)/.test(line)) return
      if (/^\s*(amountSource|reportLine)\??\s*:/.test(line)) return
      if (/^\s*(amountSource|reportLine):\s*input\./.test(line)) return
      if (/\b(if|while)\s*\(/.test(line) || /\?\s*[^:]*:/.test(line)) {
        offenders.push(`L${idx + 1}: ${line.trim()}`)
      }
    })
    expect(offenders, `以下行在条件表达式里引用了溯源字段（R5.4 禁止）：\n${offenders.join('\n')}`)
      .toEqual([])
  })
})

describe('类 B：中立性 —— 结论不因来源而变（行为级 / Property 15）', () => {
  const scenarios: Array<[string, Partial<TrimDecisionInput>]> = [
    ['档1 风险保护', {
      risk: {
        maxRisk: 'H', hasSpecial: false, completenessRmm: null,
        completenessSpecial: false, approach: null, reliance: null,
      },
      riskDimensionAvailable: true,
    }],
    ['档4 无数据', { subjectDataState: 'no_data' }],
    ['档6 重要性不可用', { accountAmount: 1000, materiality: null }],
    ['档7 低于明显微小', {
      accountAmount: 100,
      materiality: { performanceMateriality: 1e6, trivialThreshold: 1e3 },
    }],
    ['档8 低于实际执行重要性', {
      accountAmount: 5000,
      materiality: { performanceMateriality: 1e6, trivialThreshold: 1e3 },
    }],
    ['档9 默认保留', {
      accountAmount: 2e6,
      materiality: { performanceMateriality: 1e6, trivialThreshold: 1e3 },
    }],
  ]

  for (const [label, override] of scenarios) {
    it(`${label}：三种 amountSource 下 verdict / reasonCode / narrative 完全相同`, () => {
      const bare = decideTrim(baseInput(override))
      const viaReportLine = decideTrim(baseInput({
        ...override,
        amountSource: 'report_line',
        reportLine: {
          rowCode: 'BS-002', rowName: '货币资金',
          formula: "TB('1001','期末余额')", standardCodes: ['1001'],
        },
      } as Partial<TrimDecisionInput>))
      const viaAccountName = decideTrim(baseInput({
        ...override, amountSource: 'account_name', reportLine: null,
      } as Partial<TrimDecisionInput>))

      for (const [name, got] of [['report_line', viaReportLine], ['account_name', viaAccountName]] as const) {
        expect(got.verdict, `${label} / ${name}：verdict 变了`).toBe(bare.verdict)
        expect(got.reasonCode, `${label} / ${name}：reasonCode 变了`).toBe(bare.reasonCode)
        expect(got.narrative, `${label} / ${name}：narrative 变了`).toBe(bare.narrative)
        expect(got.hints, `${label} / ${name}：hints 变了`).toEqual(bare.hints)
        expect(got.evidence.decidedBy, `${label} / ${name}：命中档位变了`).toBe(bare.evidence.decidedBy)
      }
    })
  }

  it('缺省时 evidence 的既有字段与改造前逐字相同（characterization）', () => {
    // R5.3：`report_line_amounts` 为空 ⇒ 前端不传新字段 ⇒ 输出必须与改造前一致。
    const d = decideTrim(baseInput({
      accountAmount: 5000,
      materiality: { performanceMateriality: 1e6, trivialThreshold: 1e3 },
    }))
    expect(d.verdict).toBe('suggest_trim')
    expect(d.reasonCode).toBe('below_materiality')
    expect(d.evidence.decidedBy).toBe('below_materiality')
    expect(d.evidence.accountAmount).toBe(5000)
    expect(d.evidence.materialityBasis).toBe('performance_materiality')
    expect(d.evidence.materialityAmount).toBe(1e6)
    expect(d.evidence.risk_unknown).toBe(true)
    expect(d.evidence.completenessSource).toBe('cycle_default')
  })

  it('缺省时新字段为 null / undefined 而非编造值', () => {
    const d = decideTrim(baseInput({ accountAmount: 1 }))
    const ev = d.evidence as any
    expect(
      ev.amountSource === null || ev.amountSource === undefined,
      `缺省时 amountSource 竟为 ${JSON.stringify(ev.amountSource)} —— 编造了来源`,
    ).toBe(true)
    expect(
      ev.reportLine === null || ev.reportLine === undefined,
      `缺省时 reportLine 竟为 ${JSON.stringify(ev.reportLine)} —— 编造了溯源`,
    ).toBe(true)
  })
})
