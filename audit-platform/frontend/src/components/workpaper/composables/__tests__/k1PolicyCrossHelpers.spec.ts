/**
 * Unit Tests — K1-6 跨表辅助（K1-8 组合勾稽 / K2 损失率）
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeComboName,
  comboNamesMatch,
  computeK16K18ComboConsistency,
  mergeCombosFromK18,
  applyK2RatesToK18Payload,
  seedK2AgingLossRates,
  extractK18GroupNames,
} from '../k1PolicyCrossHelpers'
import { parseK18Payload } from '../useK1BadDebtCalcSheet'
import { K18_STORAGE_KEY } from '../k1CrossHelpers'

function emptyPayload() {
  return parseK18Payload('')
}

describe('k1PolicyCrossHelpers', () => {
  it('normalizeComboName 去除组合前缀', () => {
    expect(normalizeComboName('组合1：押金和保证金')).toBe('押金保证金')
    expect(comboNamesMatch('押金和保证金', '组合1 押金和保证金')).toBe(true)
    expect(comboNamesMatch('组合1', '组合1')).toBe(true)
  })

  it('computeK16K18ComboConsistency 识别仅一侧存在的组合', () => {
    const result = computeK16K18ComboConsistency(
      ['押金和保证金', '员工备用金'],
      [
        { name: '押金/保证金', section: 'credit' },
        { name: '应收代垫款项', section: 'aging' },
      ],
    )
    expect(result.matched.length).toBe(1)
    expect(result.onlyInK16).toContain('员工备用金')
    expect(result.onlyInK18).toContain('应收代垫款项')
    expect(result.isConsistent).toBe(false)
  })

  it('mergeCombosFromK18 保留已有字段并新增缺失组合', () => {
    const existing = [{ id: 'c1', basis: '押金和保证金', method: '固定比例', remark: '已有' }]
    const { combos, added } = mergeCombosFromK18(existing, [
      { name: '押金和保证金', section: 'credit' },
      { name: '应收代垫款项', section: 'aging' },
    ])
    expect(combos[0].remark).toBe('已有')
    expect(added).toBe(1)
    expect(combos.find((c) => c.basis === '应收代垫款项')?.method).toBe('账龄分析法')
  })

  it('applyK2RatesToK18Payload 按账龄段写入损失率', () => {
    const payload = emptyPayload()
    payload.agingGroups[0].groupName = '组合1'
    payload.agingGroups[0].rows[0].label = '1年以内/未逾期'
    payload.agingGroups[0].rows[0].auditedBalance = 100000
    payload.agingGroups[0].rows[0].bookProvision = 0

    const k2Rates = seedK2AgingLossRates()
    k2Rates[0].adjustedRate = 0.05

    const { updatedCells, payload: next } = applyK2RatesToK18Payload(
      payload,
      k2Rates,
      [{ k16Basis: '组合1', k18GroupName: '组合1', section: 'aging' }],
    )
    expect(updatedCells).toBe(1)
    expect(next.agingGroups[0].rows[0].lossRate).toBe(0.05)
    expect(next.agingGroups[0].rows[0].expectedProvision).toBe(5000)
  })

  it('extractK18GroupNames 从存储读取分组', () => {
    const payload = emptyPayload()
    payload.creditGroups[0].groupName = '押金/保证金'
    payload.agingGroups[0].groupName = '组合A'
    const map = new Map<string, any>([
      [K18_STORAGE_KEY, { remark: JSON.stringify(payload) }],
    ])
    const groups = extractK18GroupNames(map)
    expect(groups.some((g) => g.name === '押金/保证金' && g.section === 'credit')).toBe(true)
    expect(groups.some((g) => g.name === '组合A' && g.section === 'aging')).toBe(true)
  })
})
