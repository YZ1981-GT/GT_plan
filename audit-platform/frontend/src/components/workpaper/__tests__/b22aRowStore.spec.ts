/**
 * useB22ARowStore 守卫 — 行数组存储层 + legacy 自动迁移。
 *
 * spec: b-cycle-sync-foundation-and-first-canary（BC-53）
 *
 * 🔴 核心判据三条：
 *   ① legacy 下标数据能自动迁移成行数组，且值不变
 *   ② 迁移幂等（不重复迁移、不覆盖已有行数组）
 *   ③ 删中间行后剩余行内容不串台（legacy shift 实现下必红）
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useB22ARowStore, type ChecklistLike } from '../composables/useB22ARowStore'
import { parseRows, rowsItemId, legacyRowId } from '../composables/b22aRowIdentity'

type Rec = { conclusion?: string | null; remark?: string | null; wp_ref?: string | null }

function setup(seed: Record<string, Rec> = {}) {
  const allResponses = ref(new Map<string, Rec>(Object.entries(seed)))
  const saved: ChecklistLike[][] = []
  const saveImmediate = vi.fn((items: ChecklistLike[]) => { saved.push(items) })
  const store = useB22ARowStore({ allResponses: allResponses as any, saveImmediate })
  return { store, allResponses, saveImmediate, saved }
}

describe('readRows — 空态', () => {
  it('无任何数据 → 空数组，不落库', () => {
    const { store, saveImmediate } = setup()
    expect(store.readRows(1)).toEqual([])
    expect(saveImmediate).not.toHaveBeenCalled()
  })

  it('行数组已存在 → 直接解析，不回读 legacy', () => {
    const { store, saveImmediate } = setup({
      'B22A-T1-rows': { remark: '[{"rowId":"R-1","seq":1,"point":"甲"}]' },
      // 同时放 legacy 数据：不应被使用
      'B22A-T1-count': { remark: '5' },
      'B22A-T1-item-1-point': { remark: '不该出现' },
    })
    const rows = store.readRows(1)
    expect(rows).toHaveLength(1)
    expect(rows[0].point).toBe('甲')
    expect(saveImmediate).not.toHaveBeenCalled()
  })
})

describe('🔴 legacy 自动迁移', () => {
  const legacySeed: Record<string, Rec> = {
    'B22A-T1-count': { remark: '3' },
    'B22A-T1-item-1-point': { remark: '管理层诚信' },
    'B22A-T1-item-1-conclusion': { conclusion: '有效' },
    'B22A-T1-item-2-point': { remark: '治理层独立性' },
    'B22A-T1-item-2-conclusion': { conclusion: '设计无效' },
    'B22A-T1-item-2-desc': { remark: '未设独立董事' },
    'B22A-T1-item-3-point': { remark: '组织架构' },
  }

  it('行数组缺失 + legacy count>0 → 当场迁移并落库', () => {
    const { store, saveImmediate, saved } = setup(legacySeed)
    const rows = store.readRows(1)

    expect(rows).toHaveLength(3)
    expect(saveImmediate).toHaveBeenCalledTimes(1)
    // 落库的是行数组 item
    expect(saved[0][0].item_id).toBe(rowsItemId(1))
  })

  it('迁移后值逐条不变（只改键形状）', () => {
    const { store } = setup(legacySeed)
    const rows = store.readRows(1)

    expect(rows[0].point).toBe('管理层诚信')
    expect(rows[0].conclusion).toBe('有效')
    expect(rows[1].point).toBe('治理层独立性')
    expect(rows[1].conclusion).toBe('设计无效')
    expect(rows[1].desc).toBe('未设独立董事')
    expect(rows[2].point).toBe('组织架构')
  })

  it('迁移后每行有稳定 rowId', () => {
    const { store } = setup(legacySeed)
    const rows = store.readRows(1)
    expect(rows[0].rowId).toBe(legacyRowId('T1', 1))
    expect(rows[2].rowId).toBe(legacyRowId('T1', 3))
    rows.forEach((r) => expect(String(r.rowId).length).toBeGreaterThan(0))
  })

  it('迁移幂等：二次读取不再落库', () => {
    const { store, saveImmediate } = setup(legacySeed)
    store.readRows(1)
    expect(saveImmediate).toHaveBeenCalledTimes(1)
    store.readRows(1)
    store.readRows(1)
    // 第一次迁移已把行数组写进 Map，后续直接命中
    expect(saveImmediate).toHaveBeenCalledTimes(1)
  })

  it('legacy count=0 → 不迁移不落库', () => {
    const { store, saveImmediate } = setup({ 'B22A-T1-count': { remark: '0' } })
    expect(store.readRows(1)).toEqual([])
    expect(saveImmediate).not.toHaveBeenCalled()
  })

  it('subPanel 组独立迁移（IT 命名空间）', () => {
    const { store } = setup({
      'B22A-T4-IT-itgc-count': { remark: '2' },
      'B22A-T4-IT-itgc-1-point': { remark: 'ITGC-A' },
      'B22A-T4-IT-itgc-2-point': { remark: 'ITGC-B' },
    })
    const rows = store.readRows(4, 'itgc')
    expect(rows).toHaveLength(2)
    expect(rows[0].point).toBe('ITGC-A')
    expect(rows[0].rowId).toBe(legacyRowId('T4-itgc', 1))
  })
})

describe('appendRow / appendRows', () => {
  it('追加一行：rowId 唯一、seq 连续', () => {
    const { store } = setup()
    const a = store.appendRow(1)
    const b = store.appendRow(1)
    expect(a.rowId).not.toBe(b.rowId)
    const rows = store.readRows(1)
    expect(rows.map((r) => r.seq)).toEqual([1, 2])
  })

  it('带 seed 追加（套用示例控制点）', () => {
    const { store } = setup()
    const created = store.appendRows(1, [
      { point: '示例A' }, { point: '示例B' },
    ])
    expect(created).toHaveLength(2)
    const rows = store.readRows(1)
    expect(rows.map((r) => r.point)).toEqual(['示例A', '示例B'])
    // 两行 rowId 不同
    expect(rows[0].rowId).not.toBe(rows[1].rowId)
  })

  it('空 seeds → 不写库', () => {
    const { store, saveImmediate } = setup()
    expect(store.appendRows(1, [])).toEqual([])
    expect(saveImmediate).not.toHaveBeenCalled()
  })

  it('追加不影响既有行身份', () => {
    const { store } = setup({
      'B22A-T1-rows': { remark: '[{"rowId":"KEEP","seq":1,"point":"原有"}]' },
    })
    store.appendRow(1, undefined, { point: '新增' })
    const rows = store.readRows(1)
    expect(rows[0].rowId).toBe('KEEP')
    expect(rows[0].point).toBe('原有')
    expect(rows[1].point).toBe('新增')
  })
})

describe('🔴 removeRowAt — 删中间行不串台', () => {
  function threeRowSeed() {
    return {
      'B22A-T1-rows': {
        remark: JSON.stringify([
          { rowId: 'R-A', seq: 1, point: '甲', conclusion: '有效' },
          { rowId: 'R-B', seq: 2, point: '乙', conclusion: '设计无效' },
          { rowId: 'R-C', seq: 3, point: '丙', conclusion: '未实施' },
        ]),
      },
    }
  }

  it('删第 2 行后，第 3 行内容不上移顶替', () => {
    const { store } = setup(threeRowSeed())
    expect(store.removeRowAt(1, 2)).toBe(true)

    const rows = store.readRows(1)
    expect(rows).toHaveLength(2)
    expect(rows.map((r) => r.rowId)).toEqual(['R-A', 'R-C'])
    // 🔴 legacy shift 下这里会变成 '丙' 被搬到位置 2 但身份仍是 R-B
    expect(rows[1].rowId).toBe('R-C')
    expect(rows[1].point).toBe('丙')
    expect(rows[1].conclusion).toBe('未实施')
  })

  it('删行后 seq 重排为连续，但身份不变', () => {
    const { store } = setup(threeRowSeed())
    store.removeRowAt(1, 1)
    const rows = store.readRows(1)
    expect(rows.map((r) => r.seq)).toEqual([1, 2])
    expect(rows.map((r) => r.rowId)).toEqual(['R-B', 'R-C'])
  })

  it('越界序号 → 返回 false，不改数据', () => {
    const { store } = setup(threeRowSeed())
    expect(store.removeRowAt(1, 0)).toBe(false)
    expect(store.removeRowAt(1, 4)).toBe(false)
    expect(store.readRows(1)).toHaveLength(3)
  })
})

describe('patchRowAt — 按显示序号改字段', () => {
  it('改中间行只影响该行', () => {
    const { store } = setup({
      'B22A-T1-rows': {
        remark: JSON.stringify([
          { rowId: 'R-A', seq: 1, point: '甲' },
          { rowId: 'R-B', seq: 2, point: '乙' },
        ]),
      },
    })
    store.patchRowAt(1, 2, { conclusion: '有效' })
    const rows = store.readRows(1)
    expect(rows[0].conclusion).toBeUndefined()
    expect(rows[1].conclusion).toBe('有效')
    // 身份与其它字段不动
    expect(rows[1].rowId).toBe('R-B')
    expect(rows[1].point).toBe('乙')
  })

  it('序号超出现有行数 → 补足空行到该序号（对齐 legacy 宽松行为）', () => {
    const { store } = setup()
    store.patchRowAt(1, 3, { point: '第三行' })
    const rows = store.readRows(1)
    expect(rows).toHaveLength(3)
    expect(rows[2].point).toBe('第三行')
    // 补足的中间行是空行但有稳定身份
    expect(rows[0].point).toBeUndefined()
    expect(String(rows[0].rowId).length).toBeGreaterThan(0)
    expect(rows[0].rowId).not.toBe(rows[1].rowId)
  })

  it('序号 < 1 → 返回 undefined 不改数据', () => {
    const { store, saveImmediate } = setup()
    expect(store.patchRowAt(1, 0, { point: 'x' })).toBeUndefined()
    expect(saveImmediate).not.toHaveBeenCalled()
  })
})

describe('rowAt / rowCount', () => {
  it('rowAt 按 1-based 取行', () => {
    const { store } = setup({
      'B22A-T1-rows': {
        remark: JSON.stringify([
          { rowId: 'R-A', seq: 1, point: '甲' },
          { rowId: 'R-B', seq: 2, point: '乙' },
        ]),
      },
    })
    expect(store.rowAt(1, 1)?.point).toBe('甲')
    expect(store.rowAt(1, 2)?.point).toBe('乙')
    expect(store.rowAt(1, 3)).toBeUndefined()
    expect(store.rowAt(1, 0)).toBeUndefined()
  })

  it('rowCount 反映实际行数（替代 legacy count 键）', () => {
    const { store } = setup()
    expect(store.rowCount(1)).toBe(0)
    store.appendRow(1)
    store.appendRow(1)
    expect(store.rowCount(1)).toBe(2)
    store.removeRowAt(1, 1)
    expect(store.rowCount(1)).toBe(1)
  })

  it('count 键与实际行数一致性：删行后 rowCount 立即反映（BC-54）', () => {
    const { store } = setup({
      'B22A-T1-rows': {
        remark: JSON.stringify([
          { rowId: 'R-A', seq: 1 }, { rowId: 'R-B', seq: 2 }, { rowId: 'R-C', seq: 3 },
        ]),
      },
    })
    expect(store.rowCount(1)).toBe(3)
    store.removeRowAt(1, 2)
    // 🔴 legacy 下 count 键与实际行数可能脱钩（静默丢行）；行数组形态下不可能
    expect(store.rowCount(1)).toBe(2)
    expect(store.readRows(1)).toHaveLength(2)
  })
})

describe('写入后 Map 与落库同步', () => {
  it('writeRows 同时更新本地 Map 和调 saveImmediate', () => {
    const { store, allResponses, saveImmediate } = setup()
    store.appendRow(1, undefined, { point: '甲' })

    const rec = allResponses.value.get(rowsItemId(1))
    expect(rec).toBeDefined()
    expect(parseRows(rec!.remark ?? null, 'T1')[0].point).toBe('甲')
    expect(saveImmediate).toHaveBeenCalled()
  })

  it('落库 payload 的 remark 是合法 JSON 数组', () => {
    const { store, saved } = setup()
    store.appendRow(1, undefined, { point: '甲' })
    const payload = saved[saved.length - 1][0]
    expect(() => JSON.parse(payload.remark!)).not.toThrow()
    expect(Array.isArray(JSON.parse(payload.remark!))).toBe(true)
  })
})
