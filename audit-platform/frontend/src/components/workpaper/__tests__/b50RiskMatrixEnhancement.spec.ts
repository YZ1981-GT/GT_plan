/**
 * B50 认定矩阵增强 PBT（spec: b50-workpaper-rework）
 *
 * - Property 3：computeSuggestedApproach 纯函数
 * - Property 5：importAccounts 幂等 + balance 带入
 * - Property 9：Tab3 新增列（余额/类别/会计估计）不改变 incompleteAccounts 判定
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import {
  useB50RiskMatrix,
  computeSuggestedApproach,
  type ScopeCategory,
} from '../composables/useB50RiskMatrix'
import type { ChecklistItem, ChecklistResponse, Tab3State } from '../composables/useB50FormData'

const noopSave = async (_items: ChecklistItem[]) => {}

function createMatrix(accountNames: string[]) {
  const items = new Map<string, ChecklistResponse>()
  items.set('B50-T3-accounts', { item_id: 'B50-T3-accounts', conclusion: null, remark: JSON.stringify(accountNames), wp_ref: null })
  const tab3Data = ref<Tab3State>({ items })
  return useB50RiskMatrix(tab3Data, noopSave)
}

const arbCategory = fc.constantFrom<ScopeCategory>('', 'scot', 'amount_only', 'other')

// ─── Property 3 ───────────────────────────────────────────────────────────────

describe('Property 3: computeSuggestedApproach', () => {
  it('SCOT+ 或 有高综合风险 → 综合性方案', () => {
    fc.assert(fc.property(arbCategory, fc.boolean(), (cat, hasHigh) => {
      const out = computeSuggestedApproach(cat, hasHigh)
      if (cat === 'scot' || hasHigh) return out === 'combined'
      if (cat === 'amount_only') return out === 'substantive'
      return out === ''
    }))
  })

  it('仅金额重大 ∧ 无高风险 → 实质性方案', () => {
    expect(computeSuggestedApproach('amount_only', false)).toBe('substantive')
  })

  it('SCOT+ 恒综合性（即便无高风险）', () => {
    expect(computeSuggestedApproach('scot', false)).toBe('combined')
  })

  it('其他/空 且无高风险 → 不建议', () => {
    expect(computeSuggestedApproach('other', false)).toBe('')
    expect(computeSuggestedApproach('', false)).toBe('')
  })
})

// ─── Property 5 ───────────────────────────────────────────────────────────────

describe('Property 5: importAccounts 幂等 + balance', () => {
  it('重复导入同名科目不新增行', () => {
    const m = createMatrix([])
    const before = m.accounts.value.length
    const a1 = m.importAccounts([{ name: '货币资金', balance: 100 }])
    const a2 = m.importAccounts([{ name: '货币资金', balance: 999 }])
    expect(a1).toBe(1)
    expect(a2).toBe(0) // 已存在 → 不新增
    expect(m.accounts.value.filter(r => r.name === '货币资金').length).toBe(1)
    expect(m.accounts.value.length).toBe(before + 1)
  })

  it('导入带入 balance（数字）', () => {
    const m = createMatrix([])
    m.importAccounts([{ name: '存货', balance: 357817153.75 }])
    const row = m.accounts.value.find(r => r.name === '存货')
    expect(row?.balance).toBe(357817153.75)
  })

  it('非法 balance 不写入（保持 null）', () => {
    const m = createMatrix([])
    m.importAccounts([{ name: '应收账款', balance: Number.NaN }])
    const row = m.accounts.value.find(r => r.name === '应收账款')
    expect(row?.balance).toBeNull()
  })
})

// ─── Property 9 ───────────────────────────────────────────────────────────────

describe('Property 9: 新增列不影响 incompleteAccounts', () => {
  it('设 balance/category/estimate 后 incompleteAccounts 不变', () => {
    const m = createMatrix([])
    m.importAccounts([{ name: '固定资产' }])
    const before = [...m.incompleteAccounts.value].sort()
    m.setScopeField('固定资产', 'balance', 12345)
    m.setScopeField('固定资产', 'category', 'scot')
    m.setScopeField('固定资产', 'estimate', 'Y')
    const after = [...m.incompleteAccounts.value].sort()
    expect(after).toEqual(before)
    // 固定资产仍未评（无 combinedRisk）→ 应仍在未完成集合
    expect(after).toContain('固定资产')
  })

  it('suggestedApproach 随 category 变化（仅建议不写 approach）', () => {
    const m = createMatrix([])
    m.importAccounts([{ name: '预付款项' }])
    m.setScopeField('预付款项', 'category', 'amount_only')
    expect(m.suggestedApproach('预付款项')).toBe('substantive')
    m.setScopeField('预付款项', 'category', 'scot')
    expect(m.suggestedApproach('预付款项')).toBe('combined')
    // approach 字段本身未被自动写入
    expect(m.accounts.value.find(r => r.name === '预付款项')?.approach).toBeNull()
  })
})
