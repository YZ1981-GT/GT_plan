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
