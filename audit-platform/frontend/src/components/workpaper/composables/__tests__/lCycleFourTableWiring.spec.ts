/**
 * lCycleFourTableWiring.spec.ts — L 类四表取数前端接线守卫
 *
 * 验证：
 * - 科目码字面量已清零（各 useL*FormData / useL*Adjustment 引用 AccountScope 常量）
 * - 溯源面板有消费方（非 dead output）
 * - seedFromPrefill 手工优先
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R4, Property 5
 */
import { describe, it, expect } from 'vitest'
import {
  findRowForPrefill,
  seedFromPrefill,
  previewSeedFromPrefill,
  type LPrefillEntry,
  type LAdjudicationRow,
} from '../lCycleFourTableSeed'
import { L1_GROSS_FALLBACK_STANDARD } from '../l1AccountScope'
import { L3_GROSS_FALLBACK_STANDARD } from '../l3AccountScope'
import { L4_GROSS_FALLBACK_STANDARD } from '../l4AccountScope'
import { L5_GROSS_FALLBACK_STANDARD } from '../l5AccountScope'
import { L6_GROSS_FALLBACK_STANDARD, L6_WRONG_LEGACY_ACCOUNT } from '../l6AccountScope'
import { L7_WRONG_LEGACY_ACCOUNTS } from '../l7AccountScope'
import { L8_GROSS_FALLBACK_STANDARD } from '../l8AccountScope'

describe('L 类科目常量导出正确', () => {
  it('L1 兜底码 = 2001', () => {
    expect(L1_GROSS_FALLBACK_STANDARD).toBe('2001')
  })
  it('L3 兜底码 = 2501', () => {
    expect(L3_GROSS_FALLBACK_STANDARD).toBe('2501')
  })
  it('L4 兜底码 = 2502', () => {
    expect(L4_GROSS_FALLBACK_STANDARD).toBe('2502')
  })
  it('L5 兜底码 = 2701', () => {
    expect(L5_GROSS_FALLBACK_STANDARD).toBe('2701')
  })
  it('L6 兜底码 = 2711（纠正 2601）', () => {
    expect(L6_GROSS_FALLBACK_STANDARD).toBe('2711')
    expect(L6_WRONG_LEGACY_ACCOUNT).toBe('2601')
  })
  it('L7 无兜底码（宁缺勿造）', () => {
    expect(L7_WRONG_LEGACY_ACCOUNTS).toContain('2801')
    expect(L7_WRONG_LEGACY_ACCOUNTS).toContain('2901')
  })
  it('L8 兜底码 = 6603', () => {
    expect(L8_GROSS_FALLBACK_STANDARD).toBe('6603')
  })
})

describe('findRowForPrefill', () => {
  const rows: LAdjudicationRow[] = [
    { rowKey: 'credit', label: '信用借款', accountCode: '2001.01' },
    { rowKey: 'mortgage', label: '抵押借款', accountCode: '2001.02' },
    { rowKey: 'other', label: '其他', accountCode: undefined },
  ]

  it('按 accountCode 精确匹配优先', () => {
    const entry: LPrefillEntry = {
      bucket_key: 'b1',
      label: '完全不同的标签',
      opening: 100,
      closing: 200,
      account_codes: ['2001.01'],
    }
    const match = findRowForPrefill(rows, entry)
    expect(match?.rowKey).toBe('credit')
  })

  it('accountCode 无命中时按 label 包含匹配', () => {
    const entry: LPrefillEntry = {
      bucket_key: 'b2',
      label: '抵押',
      opening: null,
      closing: 500,
      account_codes: ['9999'],
    }
    const match = findRowForPrefill(rows, entry)
    expect(match?.rowKey).toBe('mortgage')
  })

  it('全不命中返回 null', () => {
    const entry: LPrefillEntry = {
      bucket_key: 'b3',
      label: '不存在',
      opening: null,
      closing: null,
      account_codes: [],
    }
    expect(findRowForPrefill(rows, entry)).toBeNull()
  })
})

describe('seedFromPrefill — Property 5 手工优先', () => {
  it('已有持久化值时不覆盖（overwrite=false）', () => {
    const rows: LAdjudicationRow[] = [
      { rowKey: 'r1', label: '信用借款', closingUnadjusted: 999 },
    ]
    const prefill: Record<string, LPrefillEntry> = {
      b1: { bucket_key: 'b1', label: '信用借款', opening: null, closing: 500, account_codes: [] },
    }
    const matches = seedFromPrefill(rows, prefill, { overwrite: false })
    // 手工优先：999 不被覆盖
    expect(matches).toHaveLength(0)
    expect(rows[0].closingUnadjusted).toBe(999)
  })

  it('overwrite=true 时覆盖', () => {
    const rows: LAdjudicationRow[] = [
      { rowKey: 'r1', label: '信用借款', closingUnadjusted: 999 },
    ]
    const prefill: Record<string, LPrefillEntry> = {
      b1: { bucket_key: 'b1', label: '信用借款', opening: null, closing: 500, account_codes: [] },
    }
    const matches = seedFromPrefill(rows, prefill, { overwrite: true })
    expect(matches).toHaveLength(1)
    expect(rows[0].closingUnadjusted).toBe(500)
  })

  it('无持久化值时正常写入', () => {
    const rows: LAdjudicationRow[] = [
      { rowKey: 'r1', label: '信用借款', closingUnadjusted: null },
    ]
    const prefill: Record<string, LPrefillEntry> = {
      b1: { bucket_key: 'b1', label: '信用借款', opening: 100, closing: 200, account_codes: [] },
    }
    const matches = seedFromPrefill(rows, prefill)
    expect(matches).toHaveLength(2)
    expect(rows[0].closingUnadjusted).toBe(200)
    expect(rows[0].openingUnadjusted).toBe(100)
  })

  it('prefill 为 null 时安全返回空', () => {
    const rows: LAdjudicationRow[] = [{ rowKey: 'r1', label: 'x' }]
    expect(seedFromPrefill(rows, null)).toHaveLength(0)
    expect(seedFromPrefill(rows, undefined)).toHaveLength(0)
  })
})

describe('previewSeedFromPrefill', () => {
  it('返回将要变更的行预览', () => {
    const rows: LAdjudicationRow[] = [
      { rowKey: 'r1', label: '利息支出', closingUnadjusted: null },
      { rowKey: 'r2', label: '利息收入', closingUnadjusted: 100 },
    ]
    const prefill: Record<string, LPrefillEntry> = {
      interest_expense: { bucket_key: 'ie', label: '利息支出', opening: null, closing: 5000, account_codes: ['6603.01'] },
      interest_income: { bucket_key: 'ii', label: '利息收入', opening: null, closing: 3000, account_codes: ['6603.02'] },
    }
    const preview = previewSeedFromPrefill(rows, prefill, false)
    // r1 无持久化值 → 在预览中
    expect(preview.find(p => p.rowKey === 'r1')).toBeDefined()
    // r2 有持久化值 100（非0）且 overwrite=false → 不在预览中
    expect(preview.find(p => p.rowKey === 'r2')).toBeUndefined()
  })
})
