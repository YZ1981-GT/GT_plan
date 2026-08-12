/**
 * `no_data` 自动裁剪集合的零回归 characterization（Property 31）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 23
 * Requirements 14.2；design.md Property 31 / 32。
 *
 * ## 为什么只能用构造输入，而不能在真实库上比对
 *
 * 真实库 `procedure_instances` 456 行 / 34 个项目，`status` **全为 `execute`、0 条已裁剪**
 * （tasks.md 已登记，Task 19 / 20 / 21 各自复核过）⇒ 改造前的 `no_data` 自动裁集合在真实
 * 数据上是**空集**，"两侧都空所以相等"不构成任何证据。故 R14.2 明确要求用构造输入的
 * characterization，且报告中不得声称已在真实库比对过。
 *
 * ## 判据结构：冻结改造前谓词 → 全枚举矩阵 → 集合等价
 *
 * 1. `legacyDecide` 是**改造前**（HEAD 版 `ProcedureTrimming.vue` 的 `confirmSmartTrim`
 *    内联 `decide()`，L1170-1190）的逐字转写。它返回裁剪理由或 `null`（保留）。
 * 2. 矩阵在改造前判据真正读到的**每一个**输入轴上全枚举（循环 / 执行状态 / 手工理由 /
 *    科目底稿级有无数据 / 循环级有无数据）。
 * 3. 断言：把本 spec 新增的三个维度（风险、底稿已录入、建议已驳回）**中性化**后，
 *    `decideTrim(...).verdict === 'auto_trim'` ⟺ `legacyDecide(...) !== null`，逐条相同。
 * 4. 再断言新增维度**开启**时，`auto_trim` 集合只会**变小**（新增的都是 `keep` 档），
 *    永不出现"改造前保留、改造后自动裁"这一方向 —— 那才是真正的回归。
 *
 * ## 🔴 唯一分歧输入类：`is_mandatory === true`
 *
 * 改造前读 `p.is_mandatory`；落地后 `buildAndDecide` 如实硬传 `false`（`ProcedureInstance`
 * 压根没有该列，Task 13 实证 16 列全量）。故该输入类上两者结论不同 —— 但它**不可达**：
 * `procedure_service._to_dict` 有意不下发该键。本文件用一条专测把这个分歧**显式登记**
 * （而不是从矩阵里悄悄拿掉），不可达性由后端守卫
 * `backend/tests/procedure_trim/test_task23_zero_regression.py::TestMandatoryDivergenceUnreachable`
 * 钉死。两处一起看才是完整论证。
 *
 * ## 三条硬约束（与本 spec 其余守卫一致）
 *
 * 1. 读源码型断言必须先 `stripComments()` —— 本文件与生产代码的注释里都写着反例
 *    （「改造前只读 a.cycle」等），裸 `includes` 会把说明文字数成真实引用。
 * 2. 每条扫描判据配「扫描面非空」自检。
 * 3. 集合等价类判据必须配**内存内变异自检**：把冻结谓词改坏一处后等价必须破裂。
 *    没有它，若矩阵哪天退化成空集，等价会以「两侧都空」恒绿（假绿）。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

import { decideTrim } from '../procedureTrimDecision'
import type { TrimDecisionInput, SubjectDataState } from '../procedureTrimDecision'

// ── 双哨兵向上找仓库根（禁写死回退级数）──
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵 package.json + backend/app/main.py）')
}

const ROOT = repoRoot()
const P_TRIM_VUE = path.join(ROOT, 'audit-platform', 'frontend', 'src', 'views', 'ProcedureTrimming.vue')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/** 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不是块注释起点）。 */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') {
        out += n ?? ''
        i += 2
        continue
      }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i += 1
      continue
    }
    if (c === '/' && n === '/') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i)
      i = end < 0 ? src.length : end + 3
      continue
    }
    out += c
    i += 1
  }
  return out
}

/**
 * 截具名函数体（花括号配对）。
 *
 * 🔴 不能用「声明后第一个 `{`」—— 那可能是内联返回类型注解或参数的内联类型字面量，
 * 截出来的"函数体"是那段类型，断言会在无关文本上求值（本 spec 已踩过两次）。
 */
function fnBody(src: string, decl: RegExp): string {
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  let from = m.index + m[0].length
  for (let guard = 0; guard < 14; guard += 1) {
    const open = src.indexOf('{', from)
    if (open < 0) return ''
    let depth = 0
    let end = -1
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1
      else if (src[i] === '}') {
        depth -= 1
        if (depth === 0) {
          end = i
          break
        }
      }
    }
    if (end < 0) return ''
    const block = src.slice(open, end + 1)
    if (/\b(return|const|let|await|if|for|throw)\b/.test(block)) return block
    from = end + 1
  }
  return ''
}

// ═══════════════════════════════════════════════════════════════════════════
// 改造前谓词的逐字转写（冻结基线）
//
// 来源：HEAD 版 `audit-platform/frontend/src/views/ProcedureTrimming.vue` 的
// `confirmSmartTrim` 内联 `decide()`（L1170-1190）。原文（去注释）：
//
//   const cc = (p.procedure_code || p.wp_code || '').charAt(0).toUpperCase()
//   const applicable = p._applicable !== undefined ? p._applicable
//     : (p.status !== 'not_applicable' && p.status !== 'skip')
//   if (!applicable) return null
//   if (p.is_mandatory) return null
//   if (protectedCycles.has(cc)) return null            // protectedCycles = {A, S}
//   if (['in_progress','completed','reviewed'].includes(p.execution_status)) return null
//   if (p.skip_reason) return null
//   if (!DATA_DRIVEN_CYCLES.has(cc)) return null        // DATA_DRIVEN_CYCLES = D..N
//   const prefix = ...match(/^([A-Z]+\d+)/)?.[1] || ''
//   if (subjectWithData.has(prefix)) return null
//   if (subjectNoData.has(prefix)) return '智能裁剪：...科目...无数据...'
//   if (cyclesWithData.has(cc)) return null
//   return '智能裁剪：...循环...无科目数据...'
//
// 🔴 转写只做一件事：把「从 p 上取字段」换成显式入参，判据顺序与取值逐条不动。
// 转写正确性由三层保证：① 下方 `LEGACY_AXES` 覆盖它读到的每一个输入轴
// ② 内存内变异自检证明这份谓词在等价判据里承重 ③ 桥接断言证明落地后的
// `buildAndDecide` 用同样的优先级把这些输入映射成 `decideTrim` 的入参。
// ═══════════════════════════════════════════════════════════════════════════
const LEGACY_PROTECTED_CYCLES = new Set(['A', 'S'])
const LEGACY_DATA_DRIVEN_CYCLES = new Set(['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'])
const LEGACY_IN_PROGRESS = ['in_progress', 'completed', 'reviewed']

interface LegacyInput {
  cycle: string
  applicable: boolean
  isMandatory: boolean
  executionStatus: string | null
  skipReason: string
  /** 该科目在试算表**有**数据（registry 覆盖的 wp_code 前缀命中） */
  subjectWithData: boolean
  /** 该科目在试算表**无**数据 */
  subjectNoData: boolean
  /** 该循环在试算表有科目数据 */
  cycleHasData: boolean
}

/** 改造前谓词：返回裁剪理由（非空字符串）或 `null`（保留）。 */
function legacyDecide(a: LegacyInput): string | null {
  if (!a.applicable) return null
  if (a.isMandatory) return null
  if (LEGACY_PROTECTED_CYCLES.has(a.cycle)) return null
  if (LEGACY_IN_PROGRESS.includes(String(a.executionStatus))) return null
  if (a.skipReason) return null
  if (!LEGACY_DATA_DRIVEN_CYCLES.has(a.cycle)) return null
  if (a.subjectWithData) return null
  if (a.subjectNoData) return `智能裁剪：${a.cycle}1 科目在试算表中无数据`
  if (a.cycleHasData) return null
  return `智能裁剪：${a.cycle} 循环在试算表中无科目数据`
}

// ═══════════════════════════════════════════════════════════════════════════
// 全枚举矩阵
// ═══════════════════════════════════════════════════════════════════════════
/**
 * 轴的选取原则：**改造前谓词真正读到的每一个字段**都要枚举其取值域的代表值。
 *
 * - `cycle`：A / S（改造前显式保护）· B / C（非科目余额驱动）· D（余额驱动、完整性默认关）
 *   · L / N（余额驱动、完整性默认**开** —— 用来证明档 5 不影响 `auto_trim` 集合）
 * - `executionStatus`：三个「已投入工作」值 + 两个非该集合的值（`null` 与 `not_started`）
 * - `skipReason`：空串与非空（改造前是 truthy 判定）
 * - `subjectWithData` × `subjectNoData`：四种组合都要（含**同时为真**这个矛盾输入 ——
 *   改造前 `subjectWithData` 先判，故它必须胜出；这正是优先级承重之处）
 * - `cycleHasData`：循环级兜底两侧
 */
const AX_CYCLES = ['A', 'S', 'B', 'C', 'D', 'L', 'N'] as const
const AX_EXEC = [null, 'not_started', 'in_progress', 'completed', 'reviewed'] as const
const AX_SKIP = ['', '本期无该类交易'] as const
const AX_BOOL = [false, true] as const

/** 冻结矩阵规模 —— 轴增删必须显式改这个数（防"轴被悄悄拿掉后等价变平凡"）。 */
const MATRIX_SIZE = 7 * 5 * 2 * 2 * 2 * 2 // 1120

function legacyMatrix(): LegacyInput[] {
  const out: LegacyInput[] = []
  for (const cycle of AX_CYCLES) {
    for (const executionStatus of AX_EXEC) {
      for (const skipReason of AX_SKIP) {
        for (const subjectWithData of AX_BOOL) {
          for (const subjectNoData of AX_BOOL) {
            for (const cycleHasData of AX_BOOL) {
              out.push({
                cycle,
                applicable: true,
                isMandatory: false,
                executionStatus,
                skipReason,
                subjectWithData,
                subjectNoData,
                cycleHasData,
              })
            }
          }
        }
      }
    }
  }
  return out
}

/** 稳定标识（用于集合比对时定位到具体那一格）。 */
function caseKey(a: LegacyInput): string {
  return [
    a.cycle,
    String(a.executionStatus),
    a.skipReason ? 'reason' : 'noreason',
    a.subjectWithData ? 'with' : '-',
    a.subjectNoData ? 'no' : '-',
    a.cycleHasData ? 'cyc' : '-',
  ].join('|')
}

/**
 * `buildAndDecide` 的 `subjectDataState` 映射（**优先级与生产代码相同**）：
 * `with_data` > `no_data` > `unknown`。桥接断言在下方对生产源码钉死这一顺序。
 */
function subjectStateOf(a: LegacyInput): SubjectDataState {
  if (a.subjectWithData) return 'with_data'
  if (a.subjectNoData) return 'no_data'
  return 'unknown'
}

interface NewDims {
  /** 新增维度：B50 风险（`null` = 中性化） */
  risk?: TrimDecisionInput['risk']
  riskDimensionAvailable?: boolean
  hasWorkpaperEntry?: boolean
  suggestionRejected?: boolean
  isMandatory?: boolean
  /** 新增维度：重要性（`null` = 该维度不可用） */
  materiality?: TrimDecisionInput['materiality']
  accountAmount?: number | null
  completenessSensitiveCycle?: boolean
}

function toInput(a: LegacyInput, dims: NewDims = {}): TrimDecisionInput {
  return {
    procedure: {
      wpCode: `${a.cycle}1`,
      cycle: a.cycle,
      isMandatory: dims.isMandatory ?? a.isMandatory,
      executionStatus: a.executionStatus,
      hasManualReason: Boolean(a.skipReason),
      suggestionRejected: dims.suggestionRejected ?? false,
      hasWorkpaperEntry: dims.hasWorkpaperEntry ?? false,
    },
    accountAmount: dims.accountAmount ?? null,
    subjectDataState: subjectStateOf(a),
    cycleHasData: a.cycleHasData,
    materiality: dims.materiality ?? null,
    risk: dims.risk ?? null,
    riskDimensionAvailable: dims.riskDimensionAvailable ?? false,
    completenessSensitiveCycle: dims.completenessSensitiveCycle ?? false,
    completenessSource: 'cycle_default',
  }
}

/** 落地后被自动裁剪的 case 集合。 */
function autoTrimSet(matrix: LegacyInput[], dims: NewDims = {}): Set<string> {
  const s = new Set<string>()
  for (const a of matrix) {
    const d = decideTrim(toInput(a, dims))
    if (d.verdict === 'auto_trim') s.add(caseKey(a))
  }
  return s
}

/** 改造前被裁剪的 case 集合。 */
function legacyTrimSet(
  matrix: LegacyInput[],
  fn: (a: LegacyInput) => string | null = legacyDecide,
): Set<string> {
  const s = new Set<string>()
  for (const a of matrix) if (fn(a) !== null) s.add(caseKey(a))
  return s
}

function diff(a: Set<string>, b: Set<string>): { onlyA: string[]; onlyB: string[] } {
  return {
    onlyA: [...a].filter((x) => !b.has(x)).sort(),
    onlyB: [...b].filter((x) => !a.has(x)).sort(),
  }
}

// ═══════════════════════════════════════════════════════════════════════════
describe('矩阵与转写自检（判据基础设施必须非空且非平凡）', () => {
  const matrix = legacyMatrix()

  it('矩阵规模与冻结值相等（轴增删必须显式登记）', () => {
    expect(matrix.length, '矩阵规模与 MATRIX_SIZE 不符 —— 有轴被增删而未登记').toBe(MATRIX_SIZE)
    expect(new Set(matrix.map(caseKey)).size, 'caseKey 有碰撞 ⇒ 集合比对会丢格').toBe(MATRIX_SIZE)
  })

  it('改造前谓词在矩阵上既有裁也有留（非平凡）', () => {
    const trimmed = legacyTrimSet(matrix)
    expect(trimmed.size, '改造前谓词在整个矩阵上一格都不裁 ⇒ 等价判据平凡恒真').toBeGreaterThan(0)
    expect(
      trimmed.size,
      '改造前谓词在整个矩阵上全裁 ⇒ 等价判据同样平凡',
    ).toBeLessThan(matrix.length)
  })

  it('落地后决策在矩阵上同样既有裁也有留', () => {
    const auto = autoTrimSet(matrix)
    expect(auto.size).toBeGreaterThan(0)
    expect(auto.size).toBeLessThan(matrix.length)
  })

  it('矩阵覆盖了 `subjectWithData` 与 `subjectNoData` 同时为真的矛盾输入', () => {
    const both = matrix.filter((a) => a.subjectWithData && a.subjectNoData)
    expect(both.length, '缺矛盾输入 ⇒ 「有数据优先」这条优先级无从验证').toBeGreaterThan(0)
    for (const a of both) {
      expect(subjectStateOf(a), '同时命中时必须判 `with_data`（改造前 subjectWithData 先判）')
        .toBe('with_data')
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('Property 31: `no_data` 自动裁集合与改造前逐条一致', () => {
  const matrix = legacyMatrix()

  it('新增维度中性化时，两侧集合逐格相同', () => {
    const legacy = legacyTrimSet(matrix)
    const auto = autoTrimSet(matrix)
    const { onlyA, onlyB } = diff(auto, legacy)
    expect(
      onlyA,
      `落地后**多裁**了这些格（改造前保留）—— 这是真正的回归方向：${onlyA.join(' , ')}`,
    ).toEqual([])
    expect(
      onlyB,
      `落地后**漏裁**了这些格（改造前会裁）—— \`no_data\` 自动裁行为缩水：${onlyB.join(' , ')}`,
    ).toEqual([])
    expect(auto.size, '集合规模也应逐格相同').toBe(legacy.size)
  })

  it('每一格 `auto_trim` 的理由码恒为 `no_data`（自动裁只允许这一种成因）', () => {
    for (const a of matrix) {
      const d = decideTrim(toInput(a))
      if (d.verdict !== 'auto_trim') continue
      expect(d.reasonCode, `${caseKey(a)} 自动裁的理由码不是 no_data`).toBe('no_data')
      expect(d.evidence.decidedBy, `${caseKey(a)} 自动裁不是由数据存在性档决定`).toBe('no_data')
    }
  })

  it('`auto_trim` 集合对重要性维度取值不变（档 7/8 只产生建议）', () => {
    const base = autoTrimSet(matrix)
    const withMateriality = autoTrimSet(matrix, {
      materiality: { performanceMateriality: 500000, trivialThreshold: 20000 },
      accountAmount: 1,
    })
    expect(
      diff(base, withMateriality),
      '设置重要性后自动裁集合变了 —— 重要性类判据泄漏进了自动裁路径（破 R6.7 红线）',
    ).toEqual({ onlyA: [], onlyB: [] })
  })

  it('`auto_trim` 集合对完整性豁免取值不变（档 5 排在档 4 之后）', () => {
    const base = autoTrimSet(matrix)
    const exempt = autoTrimSet(matrix, { completenessSensitiveCycle: true })
    expect(
      diff(base, exempt),
      '完整性豁免改变了自动裁集合 —— 档序被改（档 5 必须在档 4 之后，'
      + '否则完整性敏感循环里「科目压根没数据」这类反而不再自动裁）',
    ).toEqual({ onlyA: [], onlyB: [] })
  })

  it('`applicable === false` 两侧同为「不判定」（改造前早退，落地后由调用方早退）', () => {
    const already = { ...legacyMatrix()[0], applicable: false, subjectNoData: true, cycle: 'D' }
    expect(legacyDecide(already), '改造前对已裁剪的行早退').toBeNull()
    // 落地后该早退在调用方 `decide(p)` 里（源码级断言见「桥接」一节）
    const src = stripComments(read(P_TRIM_VUE))
    // 🔴 锚点必须容忍 `(p: any)` 与 `=>` 之间的返回类型注解
    //    （`const decide = (p: any): TrimDecision | null => {`）——
    //    写成 `\)\s*=>` 会以「未截到函数体」的形态假红。
    const body = fnBody(src, /const\s+decide\s*=\s*\(p:\s*any\)[^=]*=>/)
    expect(body, '未截到裁剪页的 `decide` 包装函数体').not.toBe('')
    expect(body, '调用方丢了「已裁剪不重复判定」的早退 ⇒ 已裁行会被重复判定').toMatch(
      /if\s*\(!applicable\)\s*return\s+null/,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('Property 31 反向：新增保留档只让集合变小，永不变大', () => {
  const matrix = legacyMatrix()

  const CASES: Array<[string, NewDims]> = [
    ['底稿已录入', { hasWorkpaperEntry: true }],
    ['建议已被驳回', { suggestionRejected: true }],
    ['特别风险', { risk: {
      maxRisk: null, hasSpecial: true, completenessRmm: null,
      completenessSpecial: false, approach: null, reliance: null,
    }, riskDimensionAvailable: true }],
    ['高重大错报风险', { risk: {
      maxRisk: 'H', hasSpecial: false, completenessRmm: null,
      completenessSpecial: false, approach: null, reliance: null,
    }, riskDimensionAvailable: true }],
  ]

  it.each(CASES)('%s 开启时：自动裁集合 ⊆ 改造前集合', (_label, dims) => {
    const legacy = legacyTrimSet(matrix)
    const auto = autoTrimSet(matrix, dims)
    const extra = [...auto].filter((x) => !legacy.has(x))
    expect(
      extra,
      `新增维度开启后出现改造前不会裁的格 —— 新增判据不是「只加保留」：${extra.join(' , ')}`,
    ).toEqual([])
  })

  it.each(CASES)('%s 开启时集合确实收缩（证明上一条不是恒真）', (_label, dims) => {
    const base = autoTrimSet(matrix)
    const auto = autoTrimSet(matrix, dims)
    expect(
      auto.size,
      '新增保留档开启后自动裁集合一格没少 ⇒ 该档没在决策顺序里生效（⊆ 断言恒真）',
    ).toBeLessThan(base.size)
  })

  it('中性化时 `risk` 为 null 但风险维度可用：既不保护也不因风险裁（Property 13）', () => {
    const base = autoTrimSet(matrix)
    const unknownRisk = autoTrimSet(matrix, { risk: null, riskDimensionAvailable: true })
    expect(
      diff(base, unknownRisk),
      '风险维度可用而该科目未评估时自动裁集合变了 —— 「未填」被当成了某种风险结论',
    ).toEqual({ onlyA: [], onlyB: [] })
    const probe = decideTrim(toInput(
      { ...legacyMatrix()[0], cycle: 'D', subjectNoData: true },
      { risk: null, riskDimensionAvailable: true },
    ))
    expect(probe.evidence.risk_unknown, '风险未知未留痕').toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('内存内变异自检：等价判据必须能被改坏的冻结谓词打破', () => {
  const matrix = legacyMatrix()

  /** 变异 1：去掉「科目有数据优先」这一条（改造前 `subjectWithData` 先判）。 */
  function mutantNoWithDataPrecedence(a: LegacyInput): string | null {
    if (!a.applicable) return null
    if (a.isMandatory) return null
    if (LEGACY_PROTECTED_CYCLES.has(a.cycle)) return null
    if (LEGACY_IN_PROGRESS.includes(String(a.executionStatus))) return null
    if (a.skipReason) return null
    if (!LEGACY_DATA_DRIVEN_CYCLES.has(a.cycle)) return null
    if (a.subjectNoData) return 'trim' // ← 少了「subjectWithData 先判」这一条
    if (a.subjectWithData) return null
    if (a.cycleHasData) return null
    return 'trim'
  }

  /** 变异 2：去掉循环级兜底（未覆盖科目一律不裁）。 */
  function mutantNoCycleFallback(a: LegacyInput): string | null {
    if (!a.applicable) return null
    if (a.isMandatory) return null
    if (LEGACY_PROTECTED_CYCLES.has(a.cycle)) return null
    if (LEGACY_IN_PROGRESS.includes(String(a.executionStatus))) return null
    if (a.skipReason) return null
    if (!LEGACY_DATA_DRIVEN_CYCLES.has(a.cycle)) return null
    if (a.subjectWithData) return null
    if (a.subjectNoData) return 'trim'
    return null // ← 少了循环级兜底
  }

  /** 变异 3：A/S 循环不再保护。 */
  function mutantNoProtectedCycles(a: LegacyInput): string | null {
    if (!a.applicable) return null
    if (a.isMandatory) return null
    if (LEGACY_IN_PROGRESS.includes(String(a.executionStatus))) return null
    if (a.skipReason) return null
    if (!LEGACY_DATA_DRIVEN_CYCLES.has(a.cycle) && !LEGACY_PROTECTED_CYCLES.has(a.cycle)) return null
    if (a.subjectWithData) return null
    if (a.subjectNoData) return 'trim'
    if (a.cycleHasData) return null
    return 'trim'
  }

  const MUTANTS: Array<[string, (a: LegacyInput) => string | null]> = [
    ['去掉「科目有数据优先」', mutantNoWithDataPrecedence],
    ['去掉循环级兜底', mutantNoCycleFallback],
    ['A/S 循环不再保护', mutantNoProtectedCycles],
  ]

  it.each(MUTANTS)('%s ⟹ 等价判据必须破裂', (_label, mutant) => {
    const auto = autoTrimSet(matrix)
    const mutated = legacyTrimSet(matrix, mutant)
    const d = diff(auto, mutated)
    expect(
      d.onlyA.length + d.onlyB.length,
      '把冻结谓词改坏后集合仍逐格相同 ⇒ 等价判据空转（两侧可能都退化成同一个平凡集合）',
    ).toBeGreaterThan(0)
  })

  it('未变异的冻结谓词与落地后相等（正控制，防上一条靠"总有差异"取巧）', () => {
    expect(diff(autoTrimSet(matrix), legacyTrimSet(matrix))).toEqual({ onlyA: [], onlyB: [] })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('唯一分歧输入类：`is_mandatory === true`（显式登记，不从矩阵里悄悄拿掉）', () => {
  it('改造前保留、落地后按其余档判定 —— 分歧确实存在', () => {
    const a: LegacyInput = {
      cycle: 'D',
      applicable: true,
      isMandatory: true,
      executionStatus: null,
      skipReason: '',
      subjectWithData: false,
      subjectNoData: true,
      cycleHasData: false,
    }
    expect(legacyDecide(a), '改造前 `is_mandatory` 为真时保留').toBeNull()
    // 落地后 `buildAndDecide` 硬传 false ⇒ 该格会被自动裁
    const d = decideTrim(toInput(a, { isMandatory: false }))
    expect(d.verdict, '落地后该格按数据存在性判定').toBe('auto_trim')
  })

  it('落地后若真的传入 `isMandatory: true` 则与改造前一致（档 2 在档 4 之前）', () => {
    const a: LegacyInput = {
      cycle: 'D',
      applicable: true,
      isMandatory: true,
      executionStatus: null,
      skipReason: '',
      subjectWithData: false,
      subjectNoData: true,
      cycleHasData: false,
    }
    expect(decideTrim(toInput(a, { isMandatory: true })).verdict).toBe('keep')
  })

  it('`buildAndDecide` 如实硬传 false 并写明成因（不读一个不存在的列）', () => {
    const src = stripComments(read(P_TRIM_VUE))
    const body = fnBody(src, /function\s+buildAndDecide\b/)
    expect(body, '未截到 buildAndDecide 函数体').not.toBe('')
    expect(body.length, '函数体过短，扫描面可疑').toBeGreaterThan(500)
    expect(body, '`isMandatory` 未硬传 false').toMatch(/isMandatory\s*:\s*false/)
    expect(
      /\bp\??\.is_mandatory\b/.test(body),
      '`buildAndDecide` 读了 `p.is_mandatory` —— `procedure_instances` 无该列，'
      + '读它恒 undefined（死判据），且会让本文件登记的分歧输入类变得可达',
    ).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('桥接断言：生产路径必须按转写假定的优先级映射入参', () => {
  const raw = read(P_TRIM_VUE)
  const src = stripComments(raw)

  it('反向自检：stripComments 真的生效（本 SFC 含大量中文注释）', () => {
    expect(raw.length, '剥注释前后无差异 ⇒ 下面的判据在原文上求值').toBeGreaterThan(src.length)
  })

  it('`subjectDataState` 映射优先级为 with_data > no_data > unknown', () => {
    const body = fnBody(src, /function\s+buildAndDecide\b/)
    expect(body).not.toBe('')
    const iWith = body.indexOf('subjectWithData.has(prefix)')
    const iNo = body.indexOf('subjectNoData.has(prefix)')
    expect(iWith, '未见 subjectWithData 判定').toBeGreaterThan(-1)
    expect(iNo, '未见 subjectNoData 判定').toBeGreaterThan(-1)
    expect(
      iWith,
      '`subjectNoData` 被排在 `subjectWithData` 之前 —— 矛盾输入下会把「有数据」的科目'
      + '判成 no_data 并自动裁掉（改造前是有数据优先）',
    ).toBeLessThan(iNo)
  })

  it('循环级数据存在性由 `ctx.accounts` 派生，与改造前 `cyclesWithData` 同口径', () => {
    const body = fnBody(src, /function\s+buildAndDecide\b/)
    expect(body, '未见遍历 ctx.accounts 派生循环级数据存在性').toMatch(
      /Object\.values\(ctx\.accounts/,
    )
    expect(body, '未见 cycleHasData 入参').toMatch(/cycleHasData/)
  })

  it('裁剪页的 DATA_DRIVEN_CYCLES 与转写基线逐值相同', () => {
    const m = src.match(/const\s+DATA_DRIVEN_CYCLES\s*=\s*new\s+Set\(\[([^\]]+)\]\)/)
    expect(m, '未找到 DATA_DRIVEN_CYCLES').not.toBeNull()
    const codes = Array.from(m![1].matchAll(/'([A-Z])'/g)).map((x) => x[1]).sort()
    expect(
      codes,
      '裁剪页的科目余额驱动循环集合与转写基线不同 ⇒ 转写的 legacyDecide 不再代表改造前',
    ).toEqual([...LEGACY_DATA_DRIVEN_CYCLES].sort())
  })

  it('`auto_trim` 在裁剪页只有一处落地，且落的是 `no_data` 那一路', () => {
    const body = fnBody(src, /async\s+function\s+confirmSmartTrim\b/)
    expect(body, '未截到 confirmSmartTrim 函数体').not.toBe('')
    const hits = body.match(/verdict\s*===\s*'auto_trim'/g) || []
    expect(
      hits.length,
      `confirmSmartTrim 内 auto_trim 分支数 = ${hits.length}（期望 2：当前循环 + 跨循环各一处）`,
    ).toBe(2)
  })
})
