/**
 * adjustment-collaboration-and-propagation — Part B 前端纯函数属性测试
 * P8 明细表标注科目匹配 / P10 带入三模式金额 / P11 类型→列映射一致
 */
import { describe, it, expect } from 'vitest'
import { sumBringIn } from '@/components/adjustment/AdjustmentBringInDialog.vue'
import { accountMatches } from '@/components/workpaper/composables/useAdjustmentDetailPropagation'
import { COLLAB_STATUS_LABELS, COLLAB_STATUS_TAG } from '@/components/workpaper/composables/useAdjustmentCollaboration'

function line(p: Partial<any>): any {
  return {
    entry_group_id: p.entry_group_id || 'g1',
    adjustment_no: 'AJE-001',
    adjustment_type: p.adjustment_type || 'aje',
    standard_account_code: p.standard_account_code || '6602',
    debit_amount: p.debit_amount ?? 0,
    credit_amount: p.credit_amount ?? 0,
  }
}

describe('P8 accountMatches（明细行科目匹配）', () => {
  it('精确匹配', () => {
    expect(accountMatches('1122', '1122')).toBe(true)
  })
  it('明细子科目上卷到标准科目', () => {
    expect(accountMatches('1122.01', '1122')).toBe(true)
    expect(accountMatches('1122', '1122.01')).toBe(true)
  })
  it('不同科目不匹配', () => {
    expect(accountMatches('6602', '1122')).toBe(false)
  })
  it('空值不匹配', () => {
    expect(accountMatches('', '1122')).toBe(false)
    expect(accountMatches('1122', '')).toBe(false)
  })
})

// adjustment-detail-account-code：matchByAccount 用 effectiveCode = detail_account_code || standard_account_code
// 复刻实现核心判定，锁定 P9（有明细码精确）/ P10（NULL 回退一级）。
function matches(rowStdCode: string, adj: { detail_account_code?: string | null; standard_account_code: string }): boolean {
  const effectiveCode = adj.detail_account_code || adj.standard_account_code
  return accountMatches(rowStdCode, effectiveCode)
}

describe('P9 有明细码时按明细码精确匹配（不上卷到全部同级明细）', () => {
  it('调整行带明细码 112201 → 只配 112201，不误配同一级的 112202', () => {
    const adj = { detail_account_code: '112201', standard_account_code: '1122' }
    expect(matches('112201', adj)).toBe(true)   // 精确命中审计师选定明细
    expect(matches('112202', adj)).toBe(false)  // 不误配同一级另一明细
  })
  it('明细码可上卷/下钻到其自身子科目', () => {
    const adj = { detail_account_code: '1122', standard_account_code: '1122' }
    expect(matches('112201', adj)).toBe(true)
  })
})

describe('P10 明细码为 NULL 时回退 standard_account_code（历史零回归）', () => {
  it('detail_account_code=null → 用一级 1122 前缀上卷匹配所有 1122xx', () => {
    const adj = { detail_account_code: null, standard_account_code: '1122' }
    expect(matches('112201', adj)).toBe(true)
    expect(matches('112202', adj)).toBe(true)
    expect(matches('1122', adj)).toBe(true)
  })
  it('detail_account_code 缺省(undefined) 等价回退一级', () => {
    const adj = { standard_account_code: '6602' }
    expect(matches('660201', adj)).toBe(true)
    expect(matches('1122', adj)).toBe(false)
  })
})

describe('P10 sumBringIn（三模式金额）', () => {
  it('单行带入=该行净额（借-贷）', () => {
    const r = sumBringIn([line({ debit_amount: 100 })])
    expect(r.amount).toBe(100)
    expect(r.lineCount).toBe(1)
  })

  it('多选合计=选中行净额之和', () => {
    const r = sumBringIn([line({ debit_amount: 100 }), line({ credit_amount: 40 })])
    expect(r.amount).toBe(60)
    expect(r.debitTotal).toBe(100)
    expect(r.creditTotal).toBe(40)
    expect(r.lineCount).toBe(2)
  })

  it('全部求和 == 全选多选合计（同一集合恒等，P10 不变量）', () => {
    const set = [
      line({ debit_amount: 100 }),
      line({ credit_amount: 40 }),
      line({ debit_amount: 25.5 }),
    ]
    const all = sumBringIn(set)
    const fullMulti = sumBringIn([...set])
    expect(all.amount).toBe(fullMulti.amount)
    expect(all.amount).toBe(85.5)
  })

  it('去重来源引用', () => {
    const r = sumBringIn([
      line({ entry_group_id: 'g1', debit_amount: 10 }),
      line({ entry_group_id: 'g1', credit_amount: 10 }),
      line({ entry_group_id: 'g2', debit_amount: 5 }),
    ])
    expect(r.sourceEntryRefs.sort()).toEqual(['g1', 'g2'])
  })
})

describe('P11 类型→列映射（adjustmentType）', () => {
  it('全 aje → aje', () => {
    expect(sumBringIn([line({ adjustment_type: 'aje' })]).adjustmentType).toBe('aje')
  })
  it('全 rje → rje', () => {
    expect(sumBringIn([line({ adjustment_type: 'rje' })]).adjustmentType).toBe('rje')
  })
  it('混合 → mixed', () => {
    const r = sumBringIn([line({ adjustment_type: 'aje' }), line({ adjustment_type: 'rje' })])
    expect(r.adjustmentType).toBe('mixed')
  })
})

describe('协作状态标签/tag 完整', () => {
  it('五态标签齐全', () => {
    for (const s of ['pending', 'acknowledged', 'contributed', 'confirmed', 'rejected']) {
      expect(COLLAB_STATUS_LABELS[s]).toBeTruthy()
      expect(COLLAB_STATUS_TAG[s]).toBeTruthy()
    }
  })
})
