/**
 * 附注披露 sheetName → 变体分发 平台级契约
 *
 * 背景（实测踩中）：H1 源模板国企 sheet 名是「附注披露信息（**国有企业**）」，
 * 而多数循环组件的分发正则只写了 `/附注.*国企/`。该正则不命中后落到末尾 fallback
 * `name.includes('国企') ? soe : listed` → 同样不命中 → **误判为上市**，
 * 结果国企 TAB 渲染出上市组件（`get_diagnostics` 与 vitest 均查不出，只有浏览器实测能发现）。
 *
 * 共 24 份源模板使用「国有企业」式命名，这里逐一锁定每个组件的实际分发正则文本，
 * 确保它能把「国有企业」判成国企。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const COMPONENT_DIR = resolve(__dirname, '..')

/** 源模板中使用「国有企业」命名的循环 → 组件文件 + 该源模板的 sheet 名 */
const SOE_SHEET_BY_COMPONENT: Array<[string, string, string]> = [
  ['H1', 'GtH1FixedAssets.vue', '附注披露信息（国有企业）'],
  ['H2', 'GtH2ConstructionInProgress.vue', '附注披露信息（国有企业）'],
  ['H3', 'GtH3InvestmentProperty.vue', '附注披露信息（国有企业）'],
  ['H4', 'GtH4EngineeringMaterials.vue', '附注披露信息（国有企业）'],
  ['H5', 'GtH5OilGasAssets.vue', '附注披露信息（国有企业）'],
  ['H6', 'GtH6AssetDisposalClearing.vue', '附注披露信息（国有企业）'],
  ['H7', 'GtH7BiologicalAssets.vue', '附注披露信息（国有企业）'],
  ['I1', 'GtI1IntangibleAssets.vue', '附注披露信息（国有企业）'],
  ['I2', 'GtI2DevelopmentExpenditure.vue', '附注披露（国有企业）'],
  ['I3', 'GtI3Goodwill.vue', '附注披露（国有企业）'],
  ['I4', 'GtI4LongTermPrepaid.vue', '附注披露（国有企业）'],
  ['I5', 'GtI5OtherNoncurrentAssets.vue', '附注披露（国有企业）'],
  ['I6', 'GtI6ResearchDevelopmentExpense.vue', '附注披露（国有企业）'],
  // G6 源模板用的是「国企」，但分发已同时认「国有」——防御性锁定，避免后续
  // 模板改名或复制到「国有企业」式命名时静默误判成上市
  ['G6', 'GtG6OtherBondMain.vue', '附注披露信息（国有企业）'],
]

/** 对应的上市 sheet 名（确认修复没有把上市误判成国企） */
const LISTED_SHEETS = ['附注披露信息（上市公司）', '附注披露（上市公司）']

/**
 * 从组件源码抽取附注分发的判定行，重放到给定 sheet 名上。
 * 只取形如 `if (/…/.test(name)) return '…'` 及 `name.includes('…')` 的分发链，
 * 避免把模板里的 v-else-if 字符串误当逻辑。
 */
function resolveVariant(source: string, sheetName: string): 'listed' | 'soe' | 'other' {
  const lines = source.split('\n')
  for (const raw of lines) {
    const line = raw.trim()
    // 形式 A：if (/正则/.test(name)) return '附注上市' | '附注国企' | 'disclosureSOE' …
    const reMatch = line.match(/^if \(\/(.+?)\/\.test\(name\)\) return (.+)$/)
    if (reMatch) {
      const [, pattern, tail] = reMatch
      if (!/附注/.test(pattern)) continue
      let re: RegExp
      try {
        re = new RegExp(pattern)
      } catch {
        continue
      }
      if (!re.test(sheetName)) continue
      // 三元 fallback，两种形态：
      //  a) 按 sheet 名判定：`name.includes('国企') || name.includes('国有') ? A : B`
      //  b) 按运行时可见性开关判定：`disclosureVis.value.soe ? '附注国企' : 'I6'`
      //     —— 与 sheet 名无关，取「变体可见」的正常路径即分发结果。
      const ternary = tail.match(/^(.*?)\s*\?\s*(.+?)\s*:\s*(.+?)$/)
      if (ternary) {
        const [, cond, ifTrue, ifFalse] = ternary
        const keys = [...cond.matchAll(/includes\('(.+?)'\)/g)].map((m) => m[1])
        if (keys.length === 0) return classify(ifTrue)
        const hit = keys.some((k) => sheetName.includes(k))
        return classify(hit ? ifTrue : ifFalse)
      }
      return classify(tail)
    }
  }
  return 'other'
}

function classify(token: string): 'listed' | 'soe' | 'other' {
  const t = token.replace(/['"]/g, '').trim()
  if (t.includes('国企') || /soe/i.test(t)) return 'soe'
  if (t.includes('上市') || /listed/i.test(t)) return 'listed'
  return 'other'
}

const sources = new Map<string, string>()
function sourceOf(file: string): string {
  if (!sources.has(file)) {
    sources.set(file, readFileSync(resolve(COMPONENT_DIR, file), 'utf-8'))
  }
  return sources.get(file)!
}

describe('附注披露 sheetName 分发：「国有企业」必须判为国企', () => {
  it.each(SOE_SHEET_BY_COMPONENT)(
    '%s：「%s」→ 国企',
    (_code, file, sheetName) => {
      expect(resolveVariant(sourceOf(file), sheetName)).toBe('soe')
    },
  )
})

describe('附注披露 sheetName 分发：上市不受影响', () => {
  const cases = SOE_SHEET_BY_COMPONENT.flatMap(([code, file]) =>
    LISTED_SHEETS.map((sheet) => [code, file, sheet] as [string, string, string]),
  )

  it.each(cases)('%s：「%s」→ 上市', (_code, file, sheetName) => {
    expect(resolveVariant(sourceOf(file), sheetName)).toBe('listed')
  })
})

describe('测试替身自身可信（分发重放器）', () => {
  const buggy = `
  if (/附注.*上市|X-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|X-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  `.trim()

  const fixed = `
  if (/附注.*上市|X-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有|X-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  `.trim()

  it('能复现修复前的误判（「国有企业」→ 上市）', () => {
    expect(resolveVariant(buggy, '附注披露信息（国有企业）')).toBe('listed')
  })

  it('能确认修复后判定正确', () => {
    expect(resolveVariant(fixed, '附注披露信息（国有企业）')).toBe('soe')
    expect(resolveVariant(fixed, '附注披露信息（上市公司）')).toBe('listed')
  })
})
