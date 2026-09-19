/**
 * E1 金额控件与格式铁律守卫（Task 15）
 *
 * **铁律来源**（memory / 平台级）：
 * - element-plus **2.13.6 的 `el-input-number` 不存在 `formatter`/`parser` prop**
 *   （`es/components/input-number/**` 全文无 `formatter`），挂 `:formatter="amountFormatter"`
 *   是**空操作**、千分符从未生效 → 可编辑金额必须用 `WpAmountInput.vue`
 * - **反向边界**：折算率 / 汇率 / 利率 / 比例 / 面值 / 张数 / 笔数 / 年度 **不得**套 `WpAmountInput`
 * - 只读金额一律走 `displayPrefs.fmtAmount()`（**store 成员**，不是 `@/stores/displayPrefs`
 *   的模块命名导出；写成命名导入会在**运行时**抛 `does not provide an export named 'fmtAmount'`
 *   让整页崩，而 `get_diagnostics` / Vite / vitest 全绿）
 * - `useDisplayPrefsStore()` 是 setup 作用域 composable，**必须写在 setup 顶层**
 *
 * 本 spec 的落地范围 = `E1TabDisclosure` / `E1TabCashCount` / `E1TabCreditReport` 三个文件
 * （spec Task 15 明确的范围）；E1 其余文件的存量另有 `E1_LEGACY_FORMATTER_BUDGET` 预算表
 * 记录，**只允许变短**（平台级存量替换由单独 spec 收口，见 memory）。
 *
 * spec: e1-four-table-extraction-and-disclosure-alignment / Requirements 10.1~10.5
 */
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const E1_DIR = resolve(__dirname, '../../e1')

function readVue(name: string): string {
  return readFileSync(resolve(E1_DIR, name), 'utf-8')
}

function listVue(): string[] {
  return readdirSync(E1_DIR).filter((f) => f.endsWith('.vue')).sort()
}

/** 剥离注释（`//`、`/* *​/`、`<!-- -->`），避免踩坑说明里的反例被数成真实用法 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 逐个抽出 `<el-input-number …>` 开标签（支持多行、属性值内含 `>`） */
function inputNumberTags(src: string): Array<{ line: number; tag: string }> {
  const out: Array<{ line: number; tag: string }> = []
  let pos = 0
  for (;;) {
    const i = src.indexOf('<el-input-number', pos)
    if (i < 0) break
    let j = i
    let quote: string | null = null
    while (j < src.length) {
      const ch = src[j]
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'") {
        quote = ch
      } else if (ch === '>') {
        break
      }
      j += 1
    }
    out.push({ line: src.slice(0, i).split('\n').length, tag: src.slice(i, j + 1) })
    pos = j + 1
  }
  return out
}

/** 同上，抽 `<WpAmountInput …>` */
function amountInputTags(src: string): Array<{ line: number; tag: string }> {
  const out: Array<{ line: number; tag: string }> = []
  let pos = 0
  for (;;) {
    const i = src.indexOf('<WpAmountInput', pos)
    if (i < 0) break
    let j = i
    let quote: string | null = null
    while (j < src.length) {
      const ch = src[j]
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'") {
        quote = ch
      } else if (ch === '>') {
        break
      }
      j += 1
    }
    out.push({ line: src.slice(0, i).split('\n').length, tag: src.slice(i, j + 1) })
    pos = j + 1
  }
  return out
}

/** 本 spec 收口的三个文件 */
const SCOPED = ['E1TabDisclosure.vue', 'E1TabCashCount.vue', 'E1TabCreditReport.vue']

/**
 * E1 其余文件的 `el-input-number :formatter` 存量预算（**只允许变短**）。
 *
 * 这些是平台级存量（EP 无该 prop → 千分符从未生效，属既有缺陷不是本 spec 引入），
 * 由单独的平台级 spec 统一替换。此表的作用是**冻结现状**：新增即打红。
 */
const E1_LEGACY_FORMATTER_BUDGET: Record<string, number> = {
  'E1TabAccruedInterest.vue': 1,
  'E1TabAdjustment.vue': 2,
  'E1TabAnalysis.vue': 9,
  'E1TabBankDetail.vue': 11,
  'E1TabCashDetail.vue': 5,
  'E1TabCertificateCount.vue': 1,
  'E1TabDigitalCurrency.vue': 5,
  'E1TabInterestAnalysis.vue': 4,
  'E1TabIpoSpecial.vue': 1,
  'E1TabReconciliation.vue': 3,
}

/** 明确属于「非金额」的字段名（反向边界：不得套 WpAmountInput） */
const NON_AMOUNT_FIELDS = [
  'endRate',
  'openRate',
  'fxRate',
  'closingFxRate',
  'annualRate',
  'marketRate',
  'denomination',
  'quantity',
]

describe('E1 金额控件铁律 — 本 spec 收口范围', () => {
  it('反向自检：三个 scoped 文件都能读到且非空', () => {
    for (const name of SCOPED) {
      expect(readVue(name).length, name).toBeGreaterThan(1000)
    }
  })

  it.each(SCOPED)('%s：不得残留 el-input-number :formatter（EP 无该 prop = 空操作）', (name) => {
    const src = stripComments(readVue(name))
    const bad = inputNumberTags(src).filter((t) => t.tag.includes(':formatter='))
    expect(
      bad.map((t) => `L${t.line}`),
      `${name} 仍有 ${bad.length} 处 el-input-number :formatter，应改 WpAmountInput`,
    ).toEqual([])
  })

  it.each(SCOPED.filter((n) => n !== 'E1TabDisclosure.vue'))(
    '%s：金额控件已改 WpAmountInput 且不再传 precision/controls',
    (name) => {
      const src = stripComments(readVue(name))
      const tags = amountInputTags(src)
      expect(tags.length, `${name} 应有 WpAmountInput`).toBeGreaterThan(0)
      for (const t of tags) {
        expect(t.tag, `${name} L${t.line} 不应传 :precision`).not.toContain(':precision')
        expect(t.tag, `${name} L${t.line} 不应传 :controls`).not.toContain(':controls')
        expect(t.tag, `${name} L${t.line} 不应传 :formatter`).not.toContain(':formatter')
      }
      expect(src, `${name} 须 import WpAmountInput`).toContain('WpAmountInput.vue')
    },
  )

  it('🔴 反向边界：折算率/汇率/利率/面值/张数不得套 WpAmountInput', () => {
    for (const name of listVue()) {
      const src = stripComments(readVue(name))
      for (const t of amountInputTags(src)) {
        for (const field of NON_AMOUNT_FIELDS) {
          expect(
            t.tag.includes(`'${field}'`) || t.tag.includes(`.${field}`),
            `${name} L${t.line} 把非金额字段 ${field} 套了 WpAmountInput`,
          ).toBe(false)
        }
      }
    }
  })

  it('E1TabDisclosure 剩余的 el-input-number 只许是折算率（precision 4）', () => {
    const src = stripComments(readVue('E1TabDisclosure.vue'))
    const tags = inputNumberTags(src)
    expect(tags.length).toBeGreaterThan(0)
    for (const t of tags) {
      expect(
        /endRate|openRate/.test(t.tag),
        `E1TabDisclosure L${t.line} 是非折算率的 el-input-number`,
      ).toBe(true)
      expect(t.tag).toContain(':precision="4"')
    }
  })
})

describe('E1 金额格式铁律 — 全目录', () => {
  it('🔴 不得从 @/stores/displayPrefs 命名导入 fmtAmount（运行时崩整页）', () => {
    for (const name of listVue()) {
      const src = stripComments(readVue(name))
      expect(
        /import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*['"]@\/stores\/displayPrefs['"]/.test(src),
        `${name} 把 store 成员 fmtAmount 当模块命名导出引了`,
      ).toBe(false)
    }
  })

  it('不得自造 toLocaleString 做金额格式（Date 的本地化不算）', () => {
    for (const name of listVue()) {
      const src = stripComments(readVue(name))
      for (const m of src.matchAll(/[^\n]*toLocaleString[^\n]*/g)) {
        const line = m[0]
        // 允许：日期本地化
        if (/new Date\(|Date\(/.test(line)) continue
        expect(
          /minimumFractionDigits|maximumFractionDigits|zh-CN/.test(line),
          `${name} 自造金额格式：${line.trim().slice(0, 120)}`,
        ).toBe(false)
      }
    }
  })

  it('useDisplayPrefsStore() 必须在 setup 顶层（写进函数体静默失效）', () => {
    for (const name of listVue()) {
      const src = readVue(name)
      for (const m of src.matchAll(/useDisplayPrefsStore\(\)/g)) {
        const lineStart = src.lastIndexOf('\n', m.index!) + 1
        const prefix = src.slice(lineStart, m.index!)
        const indent = prefix.length - prefix.trimStart().length
        expect(indent, `${name} L${src.slice(0, m.index!).split('\n').length} 缩进 ${indent} > 0`).toBe(0)
      }
    }
  })

  it('存量预算：其余文件的 el-input-number :formatter 只允许变少（新增即红）', () => {
    const actual: Record<string, number> = {}
    for (const name of listVue()) {
      if (SCOPED.includes(name)) continue
      const src = stripComments(readVue(name))
      const n = inputNumberTags(src).filter((t) => t.tag.includes(':formatter=')).length
      if (n > 0) actual[name] = n
    }
    // 反向自检：预算表必须真的对上现存文件（防表失效后断言空转）
    expect(Object.keys(E1_LEGACY_FORMATTER_BUDGET).length).toBeGreaterThan(5)
    for (const [name, budget] of Object.entries(E1_LEGACY_FORMATTER_BUDGET)) {
      expect(
        (actual[name] ?? 0) <= budget,
        `${name} 存量由 ${budget} 涨到 ${actual[name]}，新增金额控件必须直接用 WpAmountInput`,
      ).toBe(true)
    }
    for (const name of Object.keys(actual)) {
      expect(
        name in E1_LEGACY_FORMATTER_BUDGET,
        `${name} 未登记存量预算：新文件的金额控件必须直接用 WpAmountInput`,
      ).toBe(true)
    }
  })
})
