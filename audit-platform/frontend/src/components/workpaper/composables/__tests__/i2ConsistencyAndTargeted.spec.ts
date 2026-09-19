/**
 * i2TargetedCheckModel / i2ConsistencyModel 单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI2TargetedRow,
  summarizeI2Targeted,
  mapSampledToI2TargetedRow,
  buildI2TargetedAdjDrafts,
  formatLayeredCoverageLabel,
} from '../i2TargetedCheckModel'
import {
  buildI2ConsistencyDashboard,
  computeI2SheetCompletion,
} from '../i2ConsistencyModel'

describe('i2TargetedCheckModel', () => {
  it('分层覆盖：特定 + 抽样', () => {
    const rows = [
      emptyI2TargetedRow({ debitAmount: 40, isSpecific: true }),
      emptyI2TargetedRow({ debitAmount: 20, isSpecific: false }),
    ]
    const s = summarizeI2Targeted(rows, 100)
    expect(s.coverageRate).toBe(60)
    expect(s.specificCoverageRate).toBe(40)
    expect(s.samplingCoverageRate).toBe(20)
    expect(formatLayeredCoverageLabel(s)).toContain('特定')
  })

  it('抽凭样本映射', () => {
    const row = mapSampledToI2TargetedRow({
      voucherNo: '记-1',
      voucherDate: '2023-03-01',
      summary: '研发领料',
      debitAmount: '1000',
      isHighValue: true,
    })
    expect(row.voucherNo).toBe('记-1')
    expect(row.debitAmount).toBe(1000)
    expect(row.isSpecific).toBe(true)
  })

  it('核对×生成调整草稿', () => {
    const drafts = buildI2TargetedAdjDrafts([
      emptyI2TargetedRow({
        voucherNo: 'V1',
        debitAmount: 500,
        check3: '×',
        check1: '√',
        check2: '√',
        check4: '√',
        check5: '√',
      }),
    ])
    expect(drafts).toHaveLength(1)
    expect(drafts[0].suggestedEntry).toContain('资本化')
  })
})

describe('i2ConsistencyModel', () => {
  it('闸门错误出现在仪表盘', () => {
    const map = new Map<string, any>([
      ['I2-6-rows', JSON.stringify([{
        projectName: 'A',
        recognizedIaAmount: 100,
        conditions: [],
      }])],
      ['I2-15-rows', JSON.stringify([])],
    ])
    const d = buildI2ConsistencyDashboard(map)
    expect(d.errorCount).toBeGreaterThan(0)
    expect(d.items.some((i) => i.id === 'cap-gate')).toBe(true)
  })

  it('关键 sheet 完成度看关键 key', () => {
    const map = new Map<string, any>([
      ['I2-6-rows', JSON.stringify([{ projectName: 'A' }])],
      ['I2-6-audit-conclusion', 'ok'],
    ])
    const c = computeI2SheetCompletion(map, ['I2-6-'])
    expect(c.status).toBe('已完成')
    expect(c.progress).toBe(100)
  })
})
