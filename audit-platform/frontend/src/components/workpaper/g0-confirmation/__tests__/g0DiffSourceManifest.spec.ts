/**
 * g0DiffSourceManifest 契约 + 零回归守卫
 *   Property 3  源外字段登记（security_code/security_type）
 *   Property 5  共享 diffReconcile 未被本 spec 改动（无耦合/仍单维）
 *   Property 6  非证券 15 列对 manifest 不多不少
 *   Property 10 两表每列可追溯源出处
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import {
  SECURITIES_DIFF_COLUMNS,
  NONSECURITIES_DIFF_COLUMNS,
  SECURITIES_SOURCE_EXTRA,
  NONSECURITIES_SOURCE_EXTRA,
  SECURITIES_PREVIOUSLY_MISSING,
  diffColumnKind,
  isDiffAmountColumn,
} from '../g0DiffSourceManifest'
import type { SecuritiesDiffRow } from '../diffSecurities/diffSecuritiesTypes'
import type { NonSecuritiesDiffRow } from '../diffNonSecurities/nonSecuritiesDiffTypes'

const __dir = dirname(fileURLToPath(import.meta.url))
const REPO_CONFIRMATION = resolve(__dir, '../..', 'confirmation')

describe('g0DiffSourceManifest — 列集合契约', () => {
  it('Property 6: 非证券恰好 15 列（源模板 A..O）', () => {
    expect(NONSECURITIES_DIFF_COLUMNS.length).toBe(15)
    const cells = NONSECURITIES_DIFF_COLUMNS.map((c) => c.source_cell)
    expect(cells).toEqual(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O'])
  })

  it('证券恰好 17 列（源模板 A..Q）', () => {
    expect(SECURITIES_DIFF_COLUMNS.length).toBe(17)
    const cells = SECURITIES_DIFF_COLUMNS.map((c) => c.source_cell)
    expect(cells).toEqual([
      'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q',
    ])
  })

  it('Property 10: 每列都有 field/label/source_cell/kind（可追溯）', () => {
    for (const col of [...SECURITIES_DIFF_COLUMNS, ...NONSECURITIES_DIFF_COLUMNS]) {
      expect(col.field).toBeTruthy()
      expect(col.label).toBeTruthy()
      expect(col.source_cell).toMatch(/^[A-Q]$/)
      expect(['text', 'enum', 'number', 'amount', 'ratio', 'term']).toContain(col.kind)
    }
  })

  it('三维分组齐全：非证券 booked/reply/diff 各含比例/金额/条款', () => {
    const dims = (d: string) =>
      NONSECURITIES_DIFF_COLUMNS.filter((c) => c.dim === d).map((c) => c.kind)
    expect(dims('booked')).toEqual(expect.arrayContaining(['ratio', 'amount', 'term']))
    expect(dims('reply')).toEqual(expect.arrayContaining(['ratio', 'amount', 'term']))
    // 差异维：比例(ratio 派生) + 金额(amount 派生) + 条款(enum 判断)
    const diffKinds = NONSECURITIES_DIFF_COLUMNS.filter((c) => c.dim === 'diff').map((c) => c.kind)
    expect(diffKinds).toEqual(expect.arrayContaining(['ratio', 'amount', 'enum']))
  })

  it('差异派生列标记 derived（比例/金额差异只读）', () => {
    const ratioDiff = NONSECURITIES_DIFF_COLUMNS.find((c) => c.field === 'ratio_diff')
    const amountDiff = NONSECURITIES_DIFF_COLUMNS.find((c) => c.field === 'amount_diff')
    expect(ratioDiff?.derived).toBe(true)
    expect(amountDiff?.derived).toBe(true)
  })
})

describe('g0DiffSourceManifest — Property 3 源外字段登记', () => {
  it('security_code / security_type 登记为源外增强且不为源模板列', () => {
    const extraFields = SECURITIES_SOURCE_EXTRA.map((e) => e.field)
    expect(extraFields).toEqual(expect.arrayContaining(['security_code', 'security_type']))
    const sourceFields = new Set(SECURITIES_DIFF_COLUMNS.map((c) => c.field))
    expect(sourceFields.has('security_code')).toBe(false)
    expect(sourceFields.has('security_type')).toBe(false)
    for (const e of SECURITIES_SOURCE_EXTRA) expect(e.reason).toBeTruthy()
  })

  it('非证券源外字段（term_diff_note/adj_ref_index）登记且非渲染列', () => {
    const extra = NONSECURITIES_SOURCE_EXTRA.map((e) => e.field)
    expect(extra).toEqual(expect.arrayContaining(['term_diff_note', 'adj_ref_index']))
    const sourceFields = new Set(NONSECURITIES_DIFF_COLUMNS.map((c) => c.field))
    for (const f of extra) expect(sourceFields.has(f)).toBe(false)
  })
})

describe('g0DiffSourceManifest — 补齐守卫（Requirement 1.1）', () => {
  it('证券此前缺列现全部在类型上存在（编译期 + manifest）', () => {
    const cols = new Set(SECURITIES_DIFF_COLUMNS.map((c) => c.field))
    for (const f of SECURITIES_PREVIOUSLY_MISSING) expect(cols.has(f)).toBe(true)
    // 类型层存在性（会因缺字段编译失败）
    const probe: SecuritiesDiffRow = {
      confirm_index: 'G0-001',
      fund_account: 'X',
      account_holder: 'Y',
      support_evidence: 'Z',
      need_adjust: '待定',
    }
    expect(probe.confirm_index).toBe('G0-001')
  })

  it('非证券三维字段在类型上齐全', () => {
    const probe: NonSecuritiesDiffRow = {
      confirm_index: 'G0-101',
      entity_name: 'A公司',
      booked_ratio: 30,
      reply_ratio: 30,
      booked_amount: 100,
      reply_amount: 90,
      booked_term: 'x',
      reply_term: 'y',
      term_match: '不一致',
    }
    expect(probe.term_match).toBe('不一致')
  })
})

describe('Property 5 — 共享 diffReconcile 零回归守卫', () => {
  it('DiffReconcileRow 仍为单维金额模型（sent_amount/reply_amount/difference）', () => {
    const src = readFileSync(resolve(REPO_CONFIRMATION, 'diffReconcile/diffReconcileTypes.ts'), 'utf-8')
    expect(src).toContain('sent_amount')
    expect(src).toContain('reply_amount')
    expect(src).toContain('difference')
    // 单维金额调节表不含三维比例/条款字段
    expect(src).not.toContain('booked_ratio')
    expect(src).not.toContain('term_match')
    expect(src).not.toContain('diff-nonsecurities-v1')
  })

  it('本 spec 非证券组件不耦合共享 diffReconcile（无 import/引用其类型）', () => {
    const files = [
      '../diffNonSecurities/nonSecuritiesDiffTypes.ts',
      '../diffNonSecurities/composables/useG0DiffNonSecurities.ts',
      '../diffNonSecurities/GtG0DiffNonSecurities.vue',
    ]
    for (const rel of files) {
      const src = readFileSync(resolve(__dir, rel), 'utf-8')
      // 无 import 语句引用共享 diffReconcile 路径或其类型（prose 注释说明零回归允许）
      expect(src).not.toMatch(/import[\s\S]*?from\s+['"][^'"]*diffReconcile/)
      expect(src).not.toMatch(/import[\s\S]*?DiffReconcileRow/)
    }
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Task 3 / Requirements 3.4, 3.5 —— manifest 接线（派生格按 kind 格式化）
// ─────────────────────────────────────────────────────────────────────────────

/** 去注释（守卫读源码前必做；否则说明性注释里的反例会被数成真实代码） */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
    .replace(/<!--[\s\S]*?-->/g, '')
}

describe('Requirement 3.4 — diffColumnKind 纯函数', () => {
  it('按 (table, field) 返回 manifest 声明的 kind', () => {
    // 证券：三个派生列语义各不相同
    expect(diffColumnKind('securities', 'qty_diff')).toBe('number')
    expect(diffColumnKind('securities', 'fv_diff')).toBe('amount')
    expect(diffColumnKind('securities', 'market_value_diff')).toBe('amount')
    // 非证券：两个派生列语义相反
    expect(diffColumnKind('nonSecurities', 'ratio_diff')).toBe('ratio')
    expect(diffColumnKind('nonSecurities', 'amount_diff')).toBe('amount')
  })

  it('两张表各自独立查表（同名 field 不串表）', () => {
    // confirm_index 两表都有，remark 两表都有 —— 必须各查各的集合
    expect(diffColumnKind('securities', 'confirm_index')).toBe('text')
    expect(diffColumnKind('nonSecurities', 'confirm_index')).toBe('text')
    // booked_amount 只在非证券表；证券表查它必须返 undefined 而不是跨表命中
    expect(diffColumnKind('nonSecurities', 'booked_amount')).toBe('amount')
    expect(diffColumnKind('securities', 'booked_amount')).toBeUndefined()
    // booked_qty 只在证券表
    expect(diffColumnKind('securities', 'booked_qty')).toBe('number')
    expect(diffColumnKind('nonSecurities', 'booked_qty')).toBeUndefined()
  })

  it('未登记字段返回 undefined（宁缺勿造，不猜成金额）', () => {
    expect(diffColumnKind('securities', 'not_a_column')).toBeUndefined()
    expect(diffColumnKind('nonSecurities', '')).toBeUndefined()
    // 源外增强字段不在渲染列集合里 → 同样 undefined
    expect(diffColumnKind('securities', 'security_code')).toBeUndefined()
    expect(diffColumnKind('nonSecurities', 'adj_ref_index')).toBeUndefined()
  })

  it('对 manifest 全部列都能查到 kind（函数与真源双向锁死）', () => {
    for (const c of SECURITIES_DIFF_COLUMNS) {
      expect(diffColumnKind('securities', c.field)).toBe(c.kind)
    }
    for (const c of NONSECURITIES_DIFF_COLUMNS) {
      expect(diffColumnKind('nonSecurities', c.field)).toBe(c.kind)
    }
  })
})

describe('Requirement 3.5 — isDiffAmountColumn 只对 amount 为真', () => {
  it('仅 kind==="amount" 返回 true，number/ratio/term/text/enum 全为 false', () => {
    for (const [table, cols] of [
      ['securities', SECURITIES_DIFF_COLUMNS],
      ['nonSecurities', NONSECURITIES_DIFF_COLUMNS],
    ] as const) {
      for (const c of cols) {
        expect(isDiffAmountColumn(table, c.field)).toBe(c.kind === 'amount')
      }
    }
  })

  it('数量列与比例列必须为 false（否则会被套千分符+2位小数+金额单位）', () => {
    // 这是本 Requirement 的核心不变式：非金额列不做金额单位换算
    expect(isDiffAmountColumn('securities', 'qty_diff')).toBe(false)
    expect(isDiffAmountColumn('securities', 'booked_qty')).toBe(false)
    expect(isDiffAmountColumn('securities', 'confirmed_qty')).toBe(false)
    expect(isDiffAmountColumn('nonSecurities', 'ratio_diff')).toBe(false)
    expect(isDiffAmountColumn('nonSecurities', 'booked_ratio')).toBe(false)
    expect(isDiffAmountColumn('nonSecurities', 'reply_ratio')).toBe(false)
  })

  it('未登记字段为 false（未知一律按非金额处理）', () => {
    expect(isDiffAmountColumn('securities', 'not_a_column')).toBe(false)
    expect(isDiffAmountColumn('nonSecurities', 'not_a_column')).toBe(false)
  })

  it('反向自检：manifest 里确实同时存在 amount 与非 amount 的派生列', () => {
    // 若两张表的派生列 kind 全同，上面几条断言就退化成空转
    const secDerived = SECURITIES_DIFF_COLUMNS.filter((c) => c.derived).map((c) => c.kind)
    const nonSecDerived = NONSECURITIES_DIFF_COLUMNS.filter((c) => c.derived).map((c) => c.kind)
    expect(new Set(secDerived).size).toBeGreaterThan(1)
    expect(new Set(nonSecDerived).size).toBeGreaterThan(1)
    expect(secDerived).toContain('amount')
    expect(secDerived).toContain('number')
    expect(nonSecDerived).toContain('amount')
    expect(nonSecDerived).toContain('ratio')
  })
})

describe('Requirements 3.4/3.5 — 两张差异表已真实接线（manifest 有生产消费方）', () => {
  const DIFF_TABLES = [
    { rel: '../diffSecurities/GtConfirmationDiffSecurities.vue', table: 'securities' },
    { rel: '../diffNonSecurities/GtG0DiffNonSecurities.vue', table: 'nonSecurities' },
  ] as const

  it('两张表都 import isDiffAmountColumn 并按自己的 table 调用', () => {
    for (const { rel, table } of DIFF_TABLES) {
      const src = stripComments(readFileSync(resolve(__dir, rel), 'utf-8'))
      expect(src).toMatch(/import\s*\{[^}]*isDiffAmountColumn[^}]*\}\s*from\s*['"][^'"]*g0DiffSourceManifest['"]/)
      // 必须传自己那张表的标识，串表会让整表格式判定失效
      expect(src).toContain(`isDiffAmountColumn('${table}'`)
    }
  })

  it('派生格不再裸渲染：全部经 diffCellText 统一格式化', () => {
    const cases = [
      {
        rel: '../diffSecurities/GtConfirmationDiffSecurities.vue',
        fields: ['qty_diff', 'fv_diff', 'market_value_diff'],
      },
      {
        rel: '../diffNonSecurities/GtG0DiffNonSecurities.vue',
        fields: ['ratio_diff', 'amount_diff'],
      },
    ]
    for (const { rel, fields } of cases) {
      const src = stripComments(readFileSync(resolve(__dir, rel), 'utf-8'))
      for (const f of fields) {
        // 已接线形态
        expect(src).toContain(`diffCellText('${f}', row.${f})`)
        // 反向：不得再有裸插值 {{ row.xxx }}
        const bare = new RegExp(`\\{\\{\\s*row\\.${f}\\s*\\}\\}`)
        expect(src).not.toMatch(bare)
      }
    }
  })

  it('金额格式走 prefs.fmt（平台单一真源），且不得 import 不存在的模块级 fmtAmount', () => {
    for (const { rel } of DIFF_TABLES) {
      const src = stripComments(readFileSync(resolve(__dir, rel), 'utf-8'))
      expect(src).toContain('prefs.fmt(')
      // 🔴 平台铁律：fmtAmount 是 store 成员，不是 @/stores/displayPrefs 的模块级导出。
      //    写成命名 import 会让整页崩，而 diagnostics/vitest 全绿。
      expect(src).not.toMatch(/import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*['"]@\/stores\/displayPrefs['"]/)
    }
  })

  it('displayPrefs 在 setup 顶层取且走 inject-优先回退（不得写进函数体）', () => {
    for (const { rel } of DIFF_TABLES) {
      const src = stripComments(readFileSync(resolve(__dir, rel), 'utf-8'))
      expect(src).toMatch(
        /const\s+prefs\s*=\s*inject\(\s*DisplayPrefs_Key\s*,\s*null\s*\)\s*\?\?\s*useDisplayPrefsStore\(\)/,
      )
      // 反向：diffCellText 函数体内不得再调用 setup 作用域 composable
      const m = src.match(/function\s+diffCellText[\s\S]*?\n\}/)
      expect(m).not.toBeNull()
      expect(m![0]).not.toContain('useDisplayPrefsStore(')
      expect(m![0]).not.toContain('inject(')
    }
  })

  it('反向自检：stripComments 确实生效（原文注释含被禁字样、去注释后消失）', () => {
    const fixture = `
      // import { fmtAmount } from '@/stores/displayPrefs'
      /* {{ row.qty_diff }} */
      const prefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
    `
    expect(fixture).toMatch(/fmtAmount/)
    expect(fixture).toMatch(/\{\{\s*row\.qty_diff\s*\}\}/)
    const cleaned = stripComments(fixture)
    expect(cleaned).not.toMatch(/fmtAmount/)
    expect(cleaned).not.toMatch(/\{\{\s*row\.qty_diff\s*\}\}/)
    expect(cleaned).toContain('inject(DisplayPrefs_Key, null)')
  })

  it('反向自检：旧裸渲染写法会被判红', () => {
    const legacy = `<span class="formula-cell">{{ row.market_value_diff }}</span>`
    expect(legacy).toMatch(/\{\{\s*row\.market_value_diff\s*\}\}/)
    expect(legacy).not.toContain("diffCellText('market_value_diff'")
  })
})
