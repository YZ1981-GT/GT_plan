/**
 * G2/G3 披露 sync payload columns 列头元数据锁定
 * spec: disclosure-table-sync-convergence — 验证 columns 源对齐且随载荷发出（禁止假绿）
 */
import { describe, it, expect } from 'vitest'
import {
  buildG2SoeSyncPayloads,
  buildG2ListedSyncPayloads,
  type G2SoeSyncSnapshot,
} from '../g2DisclosureSyncPayload'
import {
  buildG3ListedSyncPayloads,
  buildG3SoeSyncPayloads,
} from '../g3DisclosureSyncPayload'

function g2Snap(): G2SoeSyncSnapshot {
  return {
    classRows: [{ rowKey: 'r1', label: '委托贷款利息', kind: 'data', endAmount: 100, priorAmount: 80 } as any],
    overdueRows: [{ borrower: '甲公司', endAmount: 50, overdueMonths: 6, overdueReason: '资金紧张', impairmentBasis: '已单项' } as any],
    eclRows: [{ rowKey: 'closing', label: '期末余额', kind: 'data', stage1: 1, stage2: 2, stage3: 3 } as any],
    auditNote: '测试',
  }
}

describe('G2 disclosure columns', () => {
  it('soe 三张子表均带源对齐 columns', () => {
    const p = buildG2SoeSyncPayloads('wp', ['soe_standalone'], g2Snap())[0]
    expect(p.columns).toBeDefined()
    expect(p.columns!['应收利息分类'][0]).toMatchObject({ key: 'label', label: '项目', is_label: true })
    expect(p.columns!['重要逾期利息'][0]).toMatchObject({ key: 'borrower', label: '借款单位', is_label: true })
    expect(p.columns!['坏账准备计提情况'].find(c => c.key === 'stage3')?.label).toBe('第三阶段')
    // 每个非元数据子表都有列头
    for (const k of Object.keys(p.sub_table_data)) {
      if (k.startsWith('_')) continue
      expect(p.columns![k], `缺列头: ${k}`).toBeDefined()
    }
  })

  it('listed 同结构带 columns', () => {
    const p = buildG2ListedSyncPayloads('wp', ['listed_standalone'], g2Snap())[0]
    expect(p.columns!['应收利息分类']).toBeDefined()
  })
})

describe('G3 disclosure columns', () => {
  it('listed 应收股利：上年年末/本期增加/本期减少', () => {
    const p = buildG3ListedSyncPayloads('wp', ['listed_standalone'],
      [{ investeeName: '子公司A', openingBalance: 100, currentIncrease: 50, currentDecrease: 20 }], '备注')[0]
    const cols = p.columns!['应收股利']
    expect(cols[0]).toMatchObject({ key: 'label', label: '被投资方', is_label: true })
    expect(cols.find(c => c.key === 'current_increase')?.label).toBe('本期增加')
    expect(cols.find(c => c.key === 'current_decrease')?.label).toBe('本期减少')
  })

  it('soe 应收股利：期初余额/本期变动', () => {
    const p = buildG3SoeSyncPayloads('wp', ['soe_standalone'],
      [{ investeeName: '子公司B', openingBalance: 100, currentChange: 30 }], '备注')[0]
    const cols = p.columns!['应收股利']
    expect(cols.find(c => c.key === 'prior_balance')?.label).toBe('期初余额')
    expect(cols.find(c => c.key === 'current_change')?.label).toBe('本期变动')
  })
})
