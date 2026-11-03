/**
 * G6-5 公允价值测试表载入：录了 0 照存，只有旧版数据（键缺失）才反推
 * （spec oo-writeback-template-parity-closure R3 批 B）。
 *
 * 数量 / 单价是两侧都能改的录入列。原载入逻辑按「单价为 0」拿存库的公允价值反推单价、按「数量单价都为 0」把数量改成 1，
 * 在线编辑里把单价改成 0（或整行清零）回到表单就被改回去，两侧来回变值。
 */
import { describe, expect, it } from 'vitest'
import { migrateFairValueRow } from '../composables/useG6SppiFairValue'

describe('G6-5 载入不改写录入的 0', () => {
  it('单价录了 0：不按存库的公允价值反推', () => {
    const row = migrateFairValueRow({ id: 'r1', investProject: '甲', unadjQty: 100, unadjPrice: 0, unadjFairValue: 1200 }, 1)
    expect(row.unadjPrice).toBe(0)
    expect(row.unadjFairValue).toBe(0)
  })

  it('数量、单价都清成 0：不补成 数量 1 × 单价 = 公允价值', () => {
    const row = migrateFairValueRow({
      id: 'r2', investProject: '乙', auditedQty: 0, auditedPrice: 0, auditedFairValue: 800,
    }, 1)
    expect([row.auditedQty, row.auditedPrice, row.auditedFairValue]).toEqual([0, 0, 0])
  })

  it('旧版数据没有单价键：按公允价值 / 数量反推', () => {
    const row = migrateFairValueRow({ id: 'r3', investProject: '丙', unadjQty: 4, unadjFairValue: 10 }, 1)
    expect(row.unadjPrice).toBe(2.5)
    expect(row.unadjFairValue).toBe(10)
  })

  it('旧版数据只有公允价值：数量记 1、单价 = 公允价值', () => {
    const row = migrateFairValueRow({ id: 'r4', investProject: '丁', auditedFairValue: 300 }, 1)
    expect([row.auditedQty, row.auditedPrice, row.auditedFairValue]).toEqual([1, 300, 300])
  })
})
