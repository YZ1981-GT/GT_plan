/**
 * useH1Detail 公式与兼容层单测
 * 对齐源模板 H1-2：未审 roll-forward → 期初/账项调整 → 审定 → 净值
 */
import { describe, it, expect } from 'vitest'
import {
  createEmptyDetailRow,
  normalizeDetailRow,
  recalcDetailRow,
  H1_2_CONCLUSION_TEMPLATES,
} from '../useH1Detail'

describe('recalcDetailRow（源模板公式）', () => {
  it('原值：未审期末=期初+增−减；审定=未审+调整', () => {
    const row = createEmptyDetailRow('测试设备', '机器设备')
    row.costBeginUnadj = 1000
    row.costIncUnadj = 200
    row.costDecUnadj = 50
    row.costOpenAdj = 10
    row.costAjeInc = 5
    row.costAjeDec = 2
    recalcDetailRow(row)

    expect(row.costEndUnadj).toBe(1150) // 1000+200-50
    expect(row.costBeginAud).toBe(1010) // 1000+10
    expect(row.costIncAud).toBe(205) // 200+5
    expect(row.costDecAud).toBe(52) // 50+2
    expect(row.costEndAud).toBe(1163) // 1010+205-52
  })

  it('累计折旧：计提|其他增 / 处置|其他减', () => {
    const row = createEmptyDetailRow('测试')
    row.depBeginUnadj = 100
    row.depProvUnadj = 30
    row.depOtherIncUnadj = 5
    row.depDispUnadj = 10
    row.depOtherDecUnadj = 2
    row.depOpenAdj = 1
    row.depAjeProv = 3
    recalcDetailRow(row)

    expect(row.depEndUnadj).toBe(123) // 100+30+5-10-2
    expect(row.depBeginAud).toBe(101)
    expect(row.depIncAud).toBe(38) // 30+3+5+0
    expect(row.depDecAud).toBe(12) // 10+0+2+0
    expect(row.depEndAud).toBe(127) // 101+38-12
  })

  it('净值：期初/期末 × 未审|审定', () => {
    const row = createEmptyDetailRow('测试')
    row.costBeginUnadj = 1000
    row.costIncUnadj = 0
    row.costDecUnadj = 0
    row.depBeginUnadj = 200
    row.depProvUnadj = 50
    row.impairBeginUnadj = 20
    row.impairProvUnadj = 10
    recalcDetailRow(row)

    expect(row.netBeginUnadj).toBe(780) // 1000-200-20
    expect(row.netEndUnadj).toBe(720) // 1000-(250)-(30)
    expect(row.netEndAud).toBe(720)
    expect(row.netValue).toBe(720) // legacy = 审定期末净值
  })

  it('legacy 字段同步：期末原值/折旧/减值写审定口径', () => {
    const row = createEmptyDetailRow('测试')
    row.costBeginUnadj = 500
    row.costAjeInc = 20
    row.depBeginUnadj = 100
    row.depProvUnadj = 10
    row.impairBeginUnadj = 5
    recalcDetailRow(row)

    expect(row.originalCostBegin).toBe(500)
    expect(row.originalCostIncrease).toBe(0)
    expect(row.originalCostEnd).toBe(520) // 审定期末
    expect(row.accDepEnd).toBe(110)
    expect(row.impairmentEnd).toBe(5)
  })
})

describe('normalizeDetailRow 兼容旧数据', () => {
  it('旧精简字段映射为未审，调整为0时审定=未审', () => {
    const row = normalizeDetailRow({
      rowId: 'r1',
      category: '房屋及建筑物',
      name: '厂房A',
      originalCostBegin: 800,
      originalCostIncrease: 100,
      originalCostDecrease: 0,
      accDepBegin: 50,
      accDepProvision: 20,
      accDepReversal: 0,
      impairmentBegin: 0,
      impairmentProvision: 0,
      impairmentReversal: 0,
      depMethod: 'straight',
    })

    expect(row.costBeginUnadj).toBe(800)
    expect(row.costIncUnadj).toBe(100)
    expect(row.costEndUnadj).toBe(900)
    expect(row.costEndAud).toBe(900)
    expect(row.depProvUnadj).toBe(20)
    expect(row.depEndAud).toBe(70)
    expect(row.depMethod).toBe('直线法')
    expect(row.originalCostEnd).toBe(900)
  })

  it('新字段优先于 legacy', () => {
    const row = normalizeDetailRow({
      name: '设备',
      costBeginUnadj: 100,
      costIncUnadj: 10,
      costOpenAdj: 5,
      originalCostBegin: 999, // 应被忽略
      depBeginUnadj: 20,
      depProvUnadj: 4,
    })
    expect(row.costBeginUnadj).toBe(100)
    expect(row.costBeginAud).toBe(105)
    expect(row.costEndAud).toBe(115)
  })
})

describe('结论模板', () => {
  it('A/B/C 与源模板提示一致', () => {
    expect(H1_2_CONCLUSION_TEMPLATES.A).toContain('未见异常')
    expect(H1_2_CONCLUSION_TEMPLATES.B).toContain('调整事项')
    expect(H1_2_CONCLUSION_TEMPLATES.C).toContain('不可确认')
  })
})
