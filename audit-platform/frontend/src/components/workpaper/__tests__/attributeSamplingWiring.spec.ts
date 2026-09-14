/**
 * 属性抽样接线 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 11.2, 11.3
 * Properties: Property 23, Property 24
 *
 * 背景（2026-08-05 实证 F12/F13）：`computeAttributeSampleSize` /
 * `evaluateDeviationRate` / `DEFAULT_TOLERABLE_DEVIATION_RATE` **零生产消费方**
 * （只被自己的两个测试文件引用），而控制测试底稿用的是 `useSampleSizeEngine` 快捷表
 * ⇒ CAS 1314 附录的属性抽样统计评价能力写好了但用户不可达。
 *
 * 本文件的核心是 **Property 23 消费方存在性**：把「有没有真实生产消费方」做成断言，
 * 杜绝将来又退回孤儿（平台已登记的「链条上游合格、整条链仍是死的」反模式）。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  CONTROL_SAMPLE_SIZE_MODES,
  CONTROL_SAMPLE_SIZE_MODE_HINTS,
  CONTROL_SAMPLE_SIZE_MODE_LABELS,
  SAMPLING_METHOD_BOUNDARY,
  defaultStatisticalInput,
  evaluateControlDeviation,
  statisticalSampleSize,
} from '@/composables/useAttributeSamplingMode'
import { DEFAULT_TOLERABLE_DEVIATION_RATE } from '../composables/useSamplingAlgorithms'

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

const SRC_ROOT = path.join(repoRoot(), 'audit-platform/frontend/src')

/** 递归收集 .ts/.vue（排除测试与自动生成的 components.d.ts）。 */
function collectSources(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue
      collectSources(full, out)
      continue
    }
    if (!/\.(ts|vue)$/.test(entry.name)) continue
    if (entry.name.endsWith('.spec.ts') || entry.name.endsWith('.test.ts')) continue
    if (entry.name === 'components.d.ts') continue
    out.push(full)
  }
  return out
}

const ALL_SOURCES = collectSources(SRC_ROOT)

/** 汇总表组件绝对路径（Property 17 数据流断言的读取目标）。 */
const SUMMARY = path.join(
  SRC_ROOT,
  'components/workpaper/cControlTest/CControlTestSummaryTable.vue',
)

/**
 * 按**花括号配对**截取函数体（禁固定字符窗口 —— 平台已登记「固定窗口会溢出到下一个
 * 函数」的踩坑）。先用圆括号配对跳过整个参数列表，再找函数体起始 `{`，
 * 否则参数里的内联类型字面量 `(row: { a: 1 })` 会被误当函数体。
 *
 * 找不到函数声明时**抛错**而不是返回空串 —— 返回空串会让全部断言静默空转。
 */
function fnBody(file: string, fnName: string): string {
  const src = fs.readFileSync(file, 'utf-8')
  const decl = new RegExp('function\\s+' + fnName + '\\s*\\(')
  const m = src.match(decl)
  if (!m || m.index == null) {
    throw new Error(`fnBody: 未找到函数声明 ${fnName}（判据失效，断言会全部空转）`)
  }
  // 1) 圆括号配对跳过参数列表
  let i = src.indexOf('(', m.index)
  let depth = 0
  for (; i < src.length; i++) {
    if (src[i] === '(') depth++
    else if (src[i] === ')') {
      depth--
      if (depth === 0) { i++; break }
    }
  }
  // 2) 找函数体起始 `{`
  const open = src.indexOf('{', i)
  if (open < 0) throw new Error(`fnBody: ${fnName} 未找到函数体起始花括号`)
  // 3) 花括号配对截取
  depth = 0
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++
    else if (src[j] === '}') {
      depth--
      if (depth === 0) return src.slice(open + 1, j)
    }
  }
  throw new Error(`fnBody: ${fnName} 花括号未闭合`)
}


/**
 * 某模块是否有真实生产消费方。
 *
 * **只认 import 路径**（平台已登记铁律）：符号级匹配会被注释、同名 `export const`、
 * 通用类型名撞车骗成假阴性。TS/Vue 跨文件消费必须先 import，故路径命中是充分必要判据。
 */
function importersOf(moduleStem: string, selfPath: string): string[] {
  const re = new RegExp(`from\\s+['"][^'"]*${moduleStem}['"]`)
  return ALL_SOURCES.filter(f => f !== selfPath && re.test(fs.readFileSync(f, 'utf-8')))
}

// ─── Property 23：消费方存在性 ───────────────────────────────────────────────

describe('Property 23：属性抽样能力有真实生产消费方', () => {
  it('useAttributeSamplingMode 有非测试消费方', () => {
    const consumers = importersOf(
      'useAttributeSamplingMode',
      path.join(SRC_ROOT, 'composables/useAttributeSamplingMode.ts'),
    )
    expect(
      consumers.length,
      '接线件零消费方 = 又一个孤儿（写好了用户不可达）',
    ).toBeGreaterThan(0)
  })

  it('消费方里含控制测试组件（准则能力落到 C 类底稿）', () => {
    const consumers = importersOf(
      'useAttributeSamplingMode',
      path.join(SRC_ROOT, 'composables/useAttributeSamplingMode.ts'),
    )
    expect(consumers.some(f => f.includes('cControlTest'))).toBe(true)
  })

  it('三个属性抽样纯函数在生产代码中被真实调用', () => {
    // 接线件本身即消费方；断言它确实调用了三者（而不是只 import 不用）
    const src = fs.readFileSync(
      path.join(SRC_ROOT, 'composables/useAttributeSamplingMode.ts'),
      'utf-8',
    )
    for (const fn of [
      'computeAttributeSampleSize(',
      'evaluateDeviationRate(',
      'DEFAULT_TOLERABLE_DEVIATION_RATE',
    ]) {
      expect(src, `接线件未使用 ${fn}`).toContain(fn)
    }
  })

  it('控制测试组件同时保留快捷表调用（不是替换而是并列）', () => {
    const src = fs.readFileSync(
      path.join(SRC_ROOT, 'components/workpaper/cControlTest/CControlTestSummaryTable.vue'),
      'utf-8',
    )
    expect(src).toContain('suggestSampleSize(')
    expect(src).toContain('statisticalSampleSize(')
    expect(src).toContain('evaluateControlDeviation(')
  })
})

// ─── Property 24 / R9.4：两套方法学边界 ──────────────────────────────────────

describe('R9.4：两套方法学边界登记且禁止合并', () => {
  it('边界登记覆盖三个符号且每条都有 serves 与 reason', () => {
    const fns = SAMPLING_METHOD_BOUNDARY.map(b => b.fn).sort()
    expect(fns).toEqual([
      'computeAttributeSampleSize',
      'evaluateDeviationRate',
      'suggestSampleSize',
    ])
    for (const entry of SAMPLING_METHOD_BOUNDARY) {
      expect(entry.serves.length, `${entry.fn} 缺 serves`).toBeGreaterThan(10)
      expect(
        entry.reason.length,
        `${entry.fn} 缺 reason —— 只写清单不写理由的登记表，下个会话仍会提议统一`,
      ).toBeGreaterThan(20)
      expect(entry.module).toMatch(/^@\//)
    }
  })

  it('两侧模块不同（快捷表与统计法各自独立）', () => {
    const modules = new Set(SAMPLING_METHOD_BOUNDARY.map(b => b.module))
    expect(modules.size).toBe(2)
  })

  it('登记表冻结，防运行时被改', () => {
    expect(Object.isFrozen(SAMPLING_METHOD_BOUNDARY)).toBe(true)
    for (const e of SAMPLING_METHOD_BOUNDARY) expect(Object.isFrozen(e)).toBe(true)
  })

  it('快捷表模块不得反向 import 统计法（保持单向依赖）', () => {
    const src = fs.readFileSync(path.join(SRC_ROOT, 'composables/useSampleSizeEngine.ts'), 'utf-8')
    expect(src).not.toContain('useSamplingAlgorithms')
    expect(src).not.toContain('computeAttributeSampleSize')
  })
})

// ─── 行为 ────────────────────────────────────────────────────────────────────

describe('统计口径样本量', () => {
  it('默认参数（95% / 5% / 0%）给出正整数样本量', () => {
    const n = statisticalSampleSize(defaultStatisticalInput())
    expect(n).not.toBeNull()
    expect(Number.isInteger(n!)).toBe(true)
    expect(n!).toBeGreaterThan(0)
  })

  it('默认可容忍偏差率取平台常量（不另写字面量）', () => {
    expect(defaultStatisticalInput().tolerableDevRate).toBe(DEFAULT_TOLERABLE_DEVIATION_RATE)
  })

  it('预期偏差率 >= 可容忍 → 返回 null 而非 0', () => {
    // 0 会被下游当「样本量为零」而不是「推不出来」
    expect(statisticalSampleSize({ confidenceLevel: 0.95, tolerableDevRate: 0.05, expectedDevRate: 0.05 })).toBeNull()
    expect(statisticalSampleSize({ confidenceLevel: 0.95, tolerableDevRate: 0.05, expectedDevRate: 0.2 })).toBeNull()
  })

  it('可容忍偏差率越小样本量越大（单调性）', () => {
    const loose = statisticalSampleSize({ confidenceLevel: 0.95, tolerableDevRate: 0.1, expectedDevRate: 0 })!
    const tight = statisticalSampleSize({ confidenceLevel: 0.95, tolerableDevRate: 0.02, expectedDevRate: 0 })!
    expect(tight).toBeGreaterThan(loose)
  })

  it('置信度越高样本量越大', () => {
    const low = statisticalSampleSize({ confidenceLevel: 0.8, tolerableDevRate: 0.05, expectedDevRate: 0 })!
    const high = statisticalSampleSize({ confidenceLevel: 0.99, tolerableDevRate: 0.05, expectedDevRate: 0 })!
    expect(high).toBeGreaterThan(low)
  })
})

describe('偏差率上限评价', () => {
  it('零偏差且样本量充分 → 可依赖', () => {
    const n = statisticalSampleSize(defaultStatisticalInput())!
    const r = evaluateControlDeviation(n, 0, defaultStatisticalInput())
    expect(r.effective).toBe(true)
    expect(r.conclusion).toContain('可予依赖')
  })

  it('偏差过多 → 不可依赖且结论给出准则处置方向', () => {
    const r = evaluateControlDeviation(25, 5, defaultStatisticalInput())
    expect(r.effective).toBe(false)
    expect(r.conclusion).toContain('不可依赖')
    expect(r.conclusion).toContain('替代程序')
  })

  it('样本量未确定 → 「无法评价」而非「控制无效」', () => {
    const r = evaluateControlDeviation(0, 0, defaultStatisticalInput())
    expect(r.conclusion).toContain('无法评价')
    expect(r.conclusion).toContain('不等于控制无效')
  })

  it('偏差数越多上限偏差率越高（单调性，支撑汇总表的保守估算说明）', () => {
    const a = evaluateControlDeviation(25, 0, defaultStatisticalInput()).upperDevRate
    const b = evaluateControlDeviation(25, 1, defaultStatisticalInput()).upperDevRate
    const c = evaluateControlDeviation(25, 3, defaultStatisticalInput()).upperDevRate
    expect(b).toBeGreaterThan(a)
    expect(c).toBeGreaterThan(b)
  })

  it('结论文本含百分数（可直接进底稿）', () => {
    expect(evaluateControlDeviation(25, 1, defaultStatisticalInput()).conclusion).toMatch(/\d+\.\d{2}%/)
  })
})

describe('模式枚举', () => {
  it('两种模式且标签全中文', () => {
    expect([...CONTROL_SAMPLE_SIZE_MODES]).toEqual(['shortcut_table', 'statistical'])
    for (const m of CONTROL_SAMPLE_SIZE_MODES) {
      expect(CONTROL_SAMPLE_SIZE_MODE_LABELS[m]).not.toBe(m)
      expect(/[\u4e00-\u9fa5]/.test(CONTROL_SAMPLE_SIZE_MODE_LABELS[m])).toBe(true)
    }
  })

  it('统计模式提示写明准则依据与公式', () => {
    const hint = CONTROL_SAMPLE_SIZE_MODE_HINTS.statistical
    expect(hint).toContain('CAS 1314')
    expect(hint).toContain('可容忍偏差率')
  })

  it('快捷表提示明示是实务经验值（不冒充准则要求）', () => {
    expect(CONTROL_SAMPLE_SIZE_MODE_HINTS.shortcut_table).toContain('经验值')
  })
})

// ─── 反向自检 ────────────────────────────────────────────────────────────────

describe('反向自检', () => {
  it('importersOf 对确实无人 import 的模块名返回空（判据有区分力）', () => {
    expect(importersOf('__definitely_not_a_module__', '')).toEqual([])
  })

  it('importersOf 对已知被广泛消费的模块返回非空（判据未失效）', () => {
    expect(
      importersOf('useSamplingAlgorithms', '').length,
      '判据失效：连 useSamplingAlgorithms 都扫不到消费方',
    ).toBeGreaterThan(3)
  })

  it('扫描面非空（防 collectSources 失效导致全部断言空转）', () => {
    expect(ALL_SOURCES.length).toBeGreaterThan(500)
  })
})

// ─── Property 17 补强：调用点必须传真实行数据（防「只 import 不真用」）───────
//
// 🔴 首版守卫只断言「汇总表引用了 evaluateControlDeviation」，变异检验发现把调用点
// 改成 `evaluateControlDeviation(0, 0, ...)`（写死常量、完全不看行数据）时守卫仍绿 ——
// 即「符号出现」不等于「真在评价这一行」。这正是平台已登记的
// 「additive 注入即死代码 + grep 式守卫是假绿源」范式。

describe('Property 17 补强：偏差评价调用点的数据流', () => {
  const body = fnBody(SUMMARY, 'getDeviationEvaluationTooltip')

  it('样本量取自 row.sampleSize（不得写死常量）', () => {
    expect(body).toMatch(/Number\(\s*row\.sampleSize\s*\)/)
  })

  it('偏差笔数取自 row.hasDeviation（不得写死常量）', () => {
    expect(body).toMatch(/row\.hasDeviation/)
  })

  it('调用 evaluateControlDeviation 时前两个实参是上面两个变量而非字面量', () => {
    const m = body.match(/evaluateControlDeviation\(\s*([^,]+),\s*([^,]+),/)
    expect(m, 'getDeviationEvaluationTooltip 里未找到 evaluateControlDeviation 调用').toBeTruthy()
    const [, arg1, arg2] = m!
    expect(arg1.trim()).not.toMatch(/^\d/)
    expect(arg2.trim()).not.toMatch(/^\d/)
    // 必须是本函数内由行数据派生出的局部变量
    expect(body).toMatch(new RegExp('const\\s+' + arg1.trim() + '\\s*='))
    expect(body).toMatch(new RegExp('const\\s+' + arg2.trim() + '\\s*='))
  })

  it('样本量非法时返回空串（不显示误导性结论）', () => {
    expect(body).toMatch(/return ''/)
  })
})

// ─── fnBody 反向自检（判据失效防护）───────────────────────────────────────

describe('fnBody 判据自检', () => {
  it('对不存在的函数名抛错（不得静默返回空串让断言空转）', () => {
    expect(() => fnBody(SUMMARY, '__definitely_not_a_function__')).toThrow()
  })

  it('截出的函数体不含下一个函数的声明（花括号配对而非固定窗口）', () => {
    const body = fnBody(SUMMARY, 'getDeviationEvaluationTooltip')
    expect(body).not.toContain('function onTextChange')
    expect(body.length).toBeGreaterThan(50)
  })
})
