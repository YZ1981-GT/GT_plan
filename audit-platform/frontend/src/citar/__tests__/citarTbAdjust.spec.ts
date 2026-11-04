/**
 * 试算表改审定数 → 调整分录（spec citar-table-manual-edit R2）：差额方向、两行借贷平衡、校验。
 */
import { describe, expect, it } from 'vitest'
import { adjustmentDelta, buildTbAdjustLines, signedOf } from '../citarTbAdjust'

const base = { code: '1122', name: '应收账款', counterCode: '6001', counterName: '主营业务收入', description: '' }

describe('buildTbAdjustLines', () => {
  it('借方科目调增：借本科目、贷对方', () => {
    const { lines, error } = buildTbAdjustLines({ ...base, current: 1000, target: 1200.5 })
    expect(error).toBe('')
    expect(lines).toEqual([
      { standard_account_code: '1122', account_name: '应收账款', debit_amount: 200.5, credit_amount: 0 },
      { standard_account_code: '6001', account_name: '主营业务收入', debit_amount: 0, credit_amount: 200.5 },
    ])
  })

  it('贷方科目调增贷方余额（借正贷负变小）：贷本科目、借对方', () => {
    const { lines } = buildTbAdjustLines({ ...base, code: '2202', name: '应付账款', current: -300, target: signedOf('贷', 350) })
    expect(lines[0]).toMatchObject({ standard_account_code: '2202', debit_amount: 0, credit_amount: 50 })
    expect(lines[1]).toMatchObject({ standard_account_code: '6001', debit_amount: 50, credit_amount: 0 })
  })

  it('余额由借翻贷', () => {
    const { lines } = buildTbAdjustLines({ ...base, current: 100, target: signedOf('贷', 40) })
    expect(lines[0].credit_amount).toBe(140)
  })

  it('差额为 0、缺对方科目、对方科目与本科目相同都拒绝', () => {
    expect(buildTbAdjustLines({ ...base, current: 100, target: 100.001 }).error).toContain('相同')
    expect(buildTbAdjustLines({ ...base, counterCode: ' ', current: 0, target: 1 }).error).toContain('对方科目')
    expect(buildTbAdjustLines({ ...base, counterCode: '1122', current: 0, target: 1 }).error).toContain('不能与本科目相同')
  })

  it('差额按分取整，不产生浮点尾差', () => {
    expect(adjustmentDelta(0.1, 0.3)).toBe(0.2)
  })
})
