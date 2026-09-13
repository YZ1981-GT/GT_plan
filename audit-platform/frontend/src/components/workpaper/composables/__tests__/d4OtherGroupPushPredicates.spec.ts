/**
 * d4OtherGroupPushPredicates 守卫 —— 四表 A13 可推送判据单一真源
 *
 * spec: d4-33-36-writeback-formula-and-io-closure（Requirement 3 / Property 6/8/10/15）
 * 断言判据行为：科目 6051（防照抄 6001）、方向保留（不 abs）、定性项需人工认定金额、
 * forward/backward 取数方向、空项返回空。
 */
import { describe, it, expect } from 'vitest'
import {
  D4_OTHER_ACCOUNT_CODE,
  D4_OTHER_ACCOUNT_NAME,
  d4_33Candidates,
  d4_34Candidates,
  d4_35Candidates,
  d4_36Candidates,
} from '../d4OtherGroupPushPredicates'

describe('d4OtherGroupPushPredicates', () => {
  // ─── Property 8：科目码不越界（6051，非 6001）──────────────────────────
  it('科目码常量为 6051 / 其他业务收入（不得为 6001）', () => {
    expect(D4_OTHER_ACCOUNT_CODE).toBe('6051')
    expect(D4_OTHER_ACCOUNT_NAME).toBe('其他业务收入')
    // 防照抄姊妹 spec
    expect(D4_OTHER_ACCOUNT_CODE).not.toBe('6001')
    expect(D4_OTHER_ACCOUNT_NAME).not.toBe('营业收入')
  })

  // ─── D4-33 毛利率：定性项 requiresManualAmount，无 refAmount（不推 0）──────
  describe('d4_33Candidates', () => {
    it('毛利率超阈值命中且标记需人工认定金额（不带金额）', () => {
      const cands = d4_33Candidates([
        { name: '出租固定资产', marginPct: 55, changeRatePct: 5 }, // 毛利率 55 > 20 阈值
      ])
      expect(cands).toHaveLength(1)
      expect(cands[0].wpCode).toBe('D4-33')
      expect(cands[0].requiresManualAmount).toBe(true)
      expect(cands[0].refAmount).toBeUndefined() // 定性项不带金额，不得自动推 0
      expect(cands[0].description).toContain('毛利率')
      expect(cands[0].description).toContain('超阈值')
    })
    it('同比变动率超阈值也命中', () => {
      const cands = d4_33Candidates([
        { name: '销售材料', marginPct: 10, changeRatePct: 45 }, // 毛利率 10 未超，变动 45 > 30
      ])
      expect(cands).toHaveLength(1)
      expect(cands[0].description).toContain('同比变动')
    })
    it('均未超阈值不命中', () => {
      expect(d4_33Candidates([{ name: 'X', marginPct: 10, changeRatePct: 5 }])).toHaveLength(0)
    })
    it('阈值可覆盖', () => {
      const cands = d4_33Candidates([{ name: 'X', marginPct: 10, changeRatePct: 25 }], { changeRateThresholdPct: 20 })
      expect(cands).toHaveLength(1)
    })
  })

  // ─── D4-34 差异：两区各自独立成条，保留符号（不 abs）─────────────────────
  describe('d4_34Candidates', () => {
    it('租赁+咨询各自独立成条，差异保留符号', () => {
      const cands = d4_34Candidates(
        [{ tenant: '甲', expectedRevenue: 100, actualRevenue: 80, diff: -20, indexRef: 'R1' }],
        [{ client: '乙', expectedRevenue: 50, actualRevenue: 70, diff: 20, indexRef: 'C1' }],
      )
      expect(cands).toHaveLength(2)
      const rental = cands.find(c => c.description.includes('租赁'))!
      const consult = cands.find(c => c.description.includes('咨询'))!
      expect(rental.refAmount).toBe(-20) // 负差异保留符号，不 abs
      expect(consult.refAmount).toBe(20)
      expect(rental.requiresManualAmount).toBe(false)
    })
    it('diff=0 不命中', () => {
      expect(d4_34Candidates([{ tenant: '甲', expectedRevenue: 100, actualRevenue: 100, diff: 0 }], [])).toHaveLength(0)
    })
  })

  // ─── D4-35 抽凭：isAnomalous==='是' 命中，带未通过核对项 ───────────────────
  describe('d4_35Candidates', () => {
    it('异常行命中且描述含未通过核对项', () => {
      const cands = d4_35Candidates([
        { voucherNo: 'PZ-1', content: '材料', amount: 12000, isAnomalous: '是',
          check1: '√', check2: '', check3: '√', check4: '', check5: '', check6: '', indexRef: 'IX' },
        { voucherNo: 'PZ-2', content: '正常', amount: 5000, isAnomalous: '否',
          check1: '√', check2: '√', check3: '√', check4: '√', check5: '√', check6: '√' },
      ])
      expect(cands).toHaveLength(1)
      expect(cands[0].voucherNo).toBe('PZ-1')
      expect(cands[0].refAmount).toBe(12000)
      expect(cands[0].description).toContain('未通过核对项')
      expect(cands[0].description).toContain('记账凭证与原始凭证是否相符') // check2 未通过
    })
  })

  // ─── D4-36 跨期：forward 取 docAmount，backward 取 voucherAmount，带方向 ────
  describe('d4_36Candidates', () => {
    it('forward 取单据金额、backward 取凭证金额，方向标识正确', () => {
      const cands = d4_36Candidates(
        [{ voucherNo: 'PZ-F', voucherAmount: 999, docNo: 'FH-F', docAmount: 500, isCrossing: '×', crossPeriodDays: 3 }],
        [{ voucherNo: 'PZ-B', voucherAmount: 700, docNo: 'FH-B', docAmount: 888, isCrossing: '×', crossPeriodDays: 5 }],
      )
      expect(cands).toHaveLength(2)
      const fwd = cands.find(c => c.description.includes('账到单据'))!
      const bwd = cands.find(c => c.description.includes('单据到账'))!
      expect(fwd.refAmount).toBe(500) // forward 取 docAmount
      expect(bwd.refAmount).toBe(700) // backward 取 voucherAmount
      expect(fwd.description).toContain('跨期 3 天')
      expect(bwd.description).toContain('跨期 5 天')
    })
    it('未跨期(√)不命中', () => {
      expect(d4_36Candidates([{ voucherNo: 'x', voucherAmount: 1, docNo: 'y', docAmount: 1, isCrossing: '√' }], [])).toHaveLength(0)
    })
  })

  // ─── Property 6：空项返回空数组（供 UI 转中文提示，非静默/非抛错）──────────
  it('四表空输入均返回空数组', () => {
    expect(d4_33Candidates([])).toEqual([])
    expect(d4_34Candidates([], [])).toEqual([])
    expect(d4_35Candidates([])).toEqual([])
    expect(d4_36Candidates([], [])).toEqual([])
  })
})
