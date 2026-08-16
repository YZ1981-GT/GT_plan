/**
 * K11 披露表符号口径：明细表正数填列、披露表按负数填列（Requirement 8.7）。
 *
 * 源 xlsx 两版末行注「本科目明细表按照正数填列、披露表按照负数填列」。
 * 🔴 实测原状是「只有注释和界面文案说负数，代码里一处翻转都没有」——
 * 那种状态下附注里的资产减值损失以正数出现（与利润表口径相反），而且
 * **任何测试都不会红**。本文件就是补那个洞。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
 *       Requirements 8.7
 */
import { describe, expect, it } from 'vitest'

import {
  buildK11SyncPayload,
  k11DisclosureAmount,
} from '../k11NoteSectionMap'

describe('k11DisclosureAmount', () => {
  it('正数翻成负数（底稿正数 → 披露负数）', () => {
    expect(k11DisclosureAmount(1234.56)).toBe(-1234.56)
  })

  it('0 保持 0，不得产出 -0', () => {
    const got = k11DisclosureAmount(0)
    expect(got).toBe(0)
    // 🔴 `-0 === 0` 为真，只有 Object.is 能区分；界面上 -0 会显示成「-0.00」
    expect(Object.is(got, -0)).toBe(false)
  })

  it('负数输入照常翻成正数（口径转换，不是取负绝对值）', () => {
    // 底稿里若录了负数，说明录入口径错了，应在录入侧修；
    // 这里悄悄「吸收」成负数会把录入错误藏起来。
    expect(k11DisclosureAmount(-500)).toBe(500)
  })

  it('非有限值原样返回（不伪造成 0）', () => {
    expect(Number.isNaN(k11DisclosureAmount(Number.NaN))).toBe(true)
    expect(k11DisclosureAmount(Number.POSITIVE_INFINITY)).toBe(
      Number.POSITIVE_INFINITY,
    )
  })
})

describe('buildK11SyncPayload 翻符号接线', () => {
  const rows = [
    { project: '固定资产减值损失', currentAmount: 100, priorAmount: 50 },
    { project: '存货跌价损失', currentAmount: 0, priorAmount: 20 },
  ]

  it.each(['listed', 'soe'] as const)('%s 侧载荷金额全部翻成负数', (variant) => {
    const payload: any = buildK11SyncPayload(variant, 'wp-1', rows, '说明')
    const sub = payload?.sub_table_data ?? payload?.subTableData ?? {}
    const tables = Object.values(sub).filter(Array.isArray) as any[][]
    expect(tables.length, '载荷里没有任何表 —— 断言会空转').toBeGreaterThan(0)

    const amounts: number[] = []
    for (const table of tables) {
      for (const row of table) {
        for (const [k, v] of Object.entries(row ?? {})) {
          if (typeof v === 'number' && k !== 'seq') amounts.push(v)
        }
      }
    }
    expect(amounts.length, '载荷里没有数值列 —— 断言会空转').toBeGreaterThan(0)
    expect(amounts.some((n) => n < 0), `实际金额=${amounts}`).toBe(true)
    expect(amounts.every((n) => n <= 0), `出现正数金额：${amounts}`).toBe(true)
  })

  it('原始入参不被就地改写（组件后续还要用它渲染底稿的正数）', () => {
    const input = [{ project: 'x', currentAmount: 7, priorAmount: 8 }]
    buildK11SyncPayload('listed', 'wp-1', input, '说明')
    expect(input[0].currentAmount).toBe(7)
    expect(input[0].priorAmount).toBe(8)
  })
})
