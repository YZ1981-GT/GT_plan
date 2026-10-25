/**
 * b50RowIdentity 守卫 — BC-48 存储层身份修复的纯函数层。
 *
 * spec: b-class-shared-base-carrier-lanes（BC-48）
 */
import { describe, it, expect } from 'vitest'
import {
  b50RowItemId,
  b50PlanItemId,
  b50CellItemId,
  B50_ACCOUNTS_ITEM_ID,
  parseAccountRefs,
  serializeAccountRefs,
  readWithLegacyFallback,
  type B50AccountRef,
} from '../composables/b50RowIdentity'

describe('键构造：身份段可换（名字 or rowKey）', () => {
  it('行级键形状不变，只换身份段', () => {
    expect(b50RowItemId('cycle', '应收账款')).toBe('B50-T3-cycle-应收账款')
    expect(b50RowItemId('cycle', 'B50-acct-x1')).toBe('B50-T3-cycle-B50-acct-x1')
  })

  it('四种行级字段都能构造', () => {
    expect(b50RowItemId('balance', 'K')).toBe('B50-T3-balance-K')
    expect(b50RowItemId('category', 'K')).toBe('B50-T3-category-K')
    expect(b50RowItemId('estimate', 'K')).toBe('B50-T3-estimate-K')
  })

  it('plan 键的字段在身份段之后（与 legacy 顺序一致）', () => {
    expect(b50PlanItemId('K', 'reliance')).toBe('B50-T3-plan-K-reliance')
    expect(b50PlanItemId('K', 'approach')).toBe('B50-T3-plan-K-approach')
  })

  it('矩阵单元格键三段齐全', () => {
    expect(b50CellItemId('K', 'C', 'RMM')).toBe('B50-T3-matrix-K-C-RMM')
  })

  it('科目清单 item_id 与 legacy 一致（不改键名，只改载荷形态）', () => {
    expect(B50_ACCOUNTS_ITEM_ID).toBe('B50-T3-accounts')
  })
})

describe('parseAccountRefs — 兼容 legacy 纯名字数组', () => {
  it('legacy 形态：字符串数组 → rowKey 留空待铸', () => {
    const refs = parseAccountRefs('["应收账款","存货"]')
    expect(refs).toHaveLength(2)
    expect(refs[0]).toEqual({ rowKey: '', name: '应收账款' })
    expect(refs[1].name).toBe('存货')
  })

  it('新形态：对象数组 → rowKey 原样保留', () => {
    const refs = parseAccountRefs(
      '[{"rowKey":"B50-acct-a1","name":"应收账款"}]',
    )
    expect(refs[0].rowKey).toBe('B50-acct-a1')
    expect(refs[0].name).toBe('应收账款')
  })

  it('混合形态（半迁移状态）逐元素分流', () => {
    const refs = parseAccountRefs(
      '[{"rowKey":"K1","name":"甲"},"乙"]',
    )
    expect(refs).toHaveLength(2)
    expect(refs[0].rowKey).toBe('K1')
    expect(refs[1].rowKey).toBe('')
    expect(refs[1].name).toBe('乙')
  })

  it('空名字元素被丢弃（不造空行）', () => {
    expect(parseAccountRefs('["","  "]')).toEqual([])
    expect(parseAccountRefs('[{"rowKey":"K","name":""}]')).toEqual([])
  })

  it('非法输入 → 空数组（渲染侧 fail soft）', () => {
    expect(parseAccountRefs(null)).toEqual([])
    expect(parseAccountRefs('')).toEqual([])
    expect(parseAccountRefs('坏JSON')).toEqual([])
    expect(parseAccountRefs('{"a":1}')).toEqual([])
  })
})

describe('serializeAccountRefs — 一律写新形态', () => {
  it('往返一致', () => {
    const refs: B50AccountRef[] = [
      { rowKey: 'K1', name: '甲' },
      { rowKey: 'K2', name: '乙' },
    ]
    expect(parseAccountRefs(serializeAccountRefs(refs))).toEqual(refs)
  })

  it('legacy 读入 → 补 rowKey → 写出为新形态', () => {
    const loaded = parseAccountRefs('["甲"]')
    loaded[0].rowKey = 'K-new'
    const out = serializeAccountRefs(loaded)
    expect(JSON.parse(out)).toEqual([{ rowKey: 'K-new', name: '甲' }])
    // 写出后不再是裸字符串数组
    expect(typeof JSON.parse(out)[0]).toBe('object')
  })
})

describe('🔴 readWithLegacyFallback — 双路读取', () => {
  const store = new Map<string, string>([
    ['B50-T3-cycle-B50-acct-new', 'D'],      // 新键
    ['B50-T3-cycle-应收账款', 'E'],           // 存量键
    ['B50-T3-cycle-存货', 'F'],               // 只有存量键
  ])
  const lookup = (id: string) => store.get(id)
  const build = (identity: string) => b50RowItemId('cycle', identity)

  it('新键存在 → 优先用新键（不被存量键盖过）', () => {
    const v = readWithLegacyFallback(lookup, build, 'B50-acct-new', '应收账款')
    expect(v).toBe('D')
  })

  it('新键缺失 → 回落存量键（存量数据读得到）', () => {
    const v = readWithLegacyFallback(lookup, build, 'B50-acct-unknown', '存货')
    expect(v).toBe('F')
  })

  it('rowKey 为空（legacy 清单刚读入）→ 直接走存量键', () => {
    const v = readWithLegacyFallback(lookup, build, '', '存货')
    expect(v).toBe('F')
  })

  it('两路都无 → undefined（不抛、不造值）', () => {
    expect(
      readWithLegacyFallback(lookup, build, 'K-none', '不存在科目'),
    ).toBeUndefined()
  })

  it('科目名为空且 rowKey 无命中 → undefined', () => {
    expect(readWithLegacyFallback(lookup, build, 'K-none', '')).toBeUndefined()
  })
})


// ═══════════════════════════════════════════════════════════════════════════
// 存储层接线：存量读得到 + 新写入用 rowKey（BC-48 端到端）
// ═══════════════════════════════════════════════════════════════════════════

import { vi } from 'vitest'
import { ref, effectScope } from 'vue'

function makeTab3(items: Record<string, any> = {}) {
  return ref({ items: new Map(Object.entries(items)) }) as any
}

describe('🔴 B50 存储层身份改造：存量兼容 + 新写入用 rowKey', () => {
  it('存量数据（键以科目名为身份）仍能读出', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = makeTab3({
        // legacy 清单：纯名字数组
        'B50-T3-accounts': { item_id: 'B50-T3-accounts', remark: '["应收账款"]' },
        // legacy 行级键：身份即科目名
        'B50-T3-cycle-应收账款': { item_id: 'B50-T3-cycle-应收账款', conclusion: 'D' },
        'B50-T3-balance-应收账款': { item_id: 'B50-T3-balance-应收账款', remark: '12345' },
        'B50-T3-category-应收账款': { item_id: 'B50-T3-category-应收账款', conclusion: 'scot' },
      })
      const m = useB50RiskMatrix(tab3, vi.fn())

      const row = m.accounts.value.find((r: any) => r.name === '应收账款')
      expect(row).toBeDefined()
      // 🔴 关键：改造后仍读得到存量值（回落科目名键）
      expect(row!.cycle).toBe('D')
      expect(row!.balance).toBe(12345)
      expect(row!.category).toBe('scot')
      // 同时已获得稳定身份
      expect(row!.rowKey).toBeTruthy()
    })
    scope.stop()
  })

  it('存量单元格风险等级仍能读出（matrix 键回落）', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = makeTab3({
        'B50-T3-accounts': { item_id: 'B50-T3-accounts', remark: '["存货"]' },
        'B50-T3-matrix-存货-existence-RMM': {
          item_id: 'B50-T3-matrix-存货-existence-RMM',
          conclusion: 'H',
          remark: '重大风险',
        },
        'B50-T3-matrix-存货-existence-SR': {
          item_id: 'B50-T3-matrix-存货-existence-SR', conclusion: 'Y',
        },
      })
      const m = useB50RiskMatrix(tab3, vi.fn())

      const row = m.accounts.value.find((r: any) => r.name === '存货')!
      expect(row.cells.existence.combinedRisk).toBe('H')
      expect(row.cells.existence.remark).toBe('重大风险')
      expect(row.cells.existence.isSpecialRisk).toBe(true)
    })
    scope.stop()
  })

  it('新形态清单（带 rowKey）读入后身份沿用、不重铸', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = makeTab3({
        'B50-T3-accounts': {
          item_id: 'B50-T3-accounts',
          remark: JSON.stringify([{ rowKey: 'KEEP-ME', name: '预付款项' }]),
        },
        'B50-T3-cycle-KEEP-ME': { item_id: 'B50-T3-cycle-KEEP-ME', conclusion: 'F' },
      })
      const m = useB50RiskMatrix(tab3, vi.fn())

      const row = m.accounts.value.find((r: any) => r.name === '预付款项')!
      // 身份沿用（跨会话稳定）
      expect(row.rowKey).toBe('KEEP-ME')
      // 按新键读到值
      expect(row.cycle).toBe('F')
    })
    scope.stop()
  })

  it('新键优先于同名存量键（迁移期两套并存时不读错）', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = makeTab3({
        'B50-T3-accounts': {
          item_id: 'B50-T3-accounts',
          remark: JSON.stringify([{ rowKey: 'RK-1', name: '存货' }]),
        },
        'B50-T3-cycle-RK-1': { item_id: 'B50-T3-cycle-RK-1', conclusion: 'NEW' },
        'B50-T3-cycle-存货': { item_id: 'B50-T3-cycle-存货', conclusion: 'OLD' },
      })
      const m = useB50RiskMatrix(tab3, vi.fn())

      const row = m.accounts.value.find((r: any) => r.name === '存货')!
      // 🔴 新键优先：不能被存量键盖过
      expect(row.cycle).toBe('NEW')
    })
    scope.stop()
  })

  it('新写入用 rowKey 作身份（不再用科目名）', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = makeTab3()
      const save = vi.fn()
      const m = useB50RiskMatrix(tab3, save)

      const row = m.accounts.value[0]
      const rk = row.rowKey
      m.setCycle(row.name, 'D')

      const written = save.mock.calls.flatMap((c: any) => c[0])
      const cycleItem = written.find((i: any) =>
        String(i.item_id).startsWith('B50-T3-cycle-'),
      )
      expect(cycleItem).toBeDefined()
      // 🔴 身份段是 rowKey，不是科目名
      expect(cycleItem.item_id).toBe(`B50-T3-cycle-${rk}`)
      expect(cycleItem.item_id).not.toContain(row.name)
    })
    scope.stop()
  })

  it('科目清单落库为 {rowKey,name} 配对形态', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = makeTab3()
      const save = vi.fn()
      const m = useB50RiskMatrix(tab3, save)
      m.addAccount('新增科目')

      const written = save.mock.calls.flatMap((c: any) => c[0])
      const listItem = written.find((i: any) => i.item_id === 'B50-T3-accounts')
      expect(listItem).toBeDefined()
      const parsed = JSON.parse(listItem.remark)
      expect(Array.isArray(parsed)).toBe(true)
      // 🔴 不再是裸字符串数组
      expect(typeof parsed[0]).toBe('object')
      expect(parsed[0]).toHaveProperty('rowKey')
      expect(parsed[0]).toHaveProperty('name')
      expect(parsed.every((r: any) => r.rowKey)).toBe(true)
    })
    scope.stop()
  })

  it('🔴 同名科目各自独立身份（存量形态下会互相覆盖）', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = makeTab3()
      const m = useB50RiskMatrix(tab3, vi.fn())
      m.addAccount('其他应收款')
      m.addAccount('其他应收款')

      const same = m.accounts.value.filter((r: any) => r.name === '其他应收款')
      if (same.length >= 2) {
        // 身份不同 ⇒ 落库键不同 ⇒ 不再后写覆盖先写
        expect(same[0].rowKey).not.toBe(same[1].rowKey)
      }
      // 全表身份唯一
      const keys = m.accounts.value.map((r: any) => r.rowKey)
      expect(new Set(keys).size).toBe(keys.length)
    })
    scope.stop()
  })
})
