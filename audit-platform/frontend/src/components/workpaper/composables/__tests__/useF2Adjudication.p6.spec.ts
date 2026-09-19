/**
 * P6 — 存货净额 = 余额 − 跌价准备(1471)，跌价变动后重算正确
 *
 * Spec: f2-inventory-cross-sheet-hardening Task 6
 * Property: 净额行 == 余额合计 − 跌价准备，跌价变动后重算正确。
 */
import { describe, it, expect } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { calcNetInventory, useF2Adjudication, F2_CATEGORIES } from '../useF2Adjudication'
import type { ChecklistResponse } from '../useF2FormData'

// ─── P6.1 纯函数 calcNetInventory ─────────────────────────────────────

describe('calcNetInventory (pure function)', () => {
  it('净额 = 余额 − 跌价准备', () => {
    expect(calcNetInventory(1000000, 200000)).toBe(800000)
  })

  it('跌价准备为 0 → 净额 = 余额', () => {
    expect(calcNetInventory(500000, 0)).toBe(500000)
  })

  it('余额为 0 → 净额 = -跌价准备', () => {
    expect(calcNetInventory(0, 100000)).toBe(-100000)
  })

  it('两者均为 0 → 净额 = 0', () => {
    expect(calcNetInventory(0, 0)).toBe(0)
  })

  it('负余额场景（退货/红字）', () => {
    expect(calcNetInventory(-50000, 10000)).toBe(-60000)
  })

  it('跌价准备大于余额（全额计提场景）', () => {
    expect(calcNetInventory(300000, 300000)).toBe(0)
  })

  it('小数精度', () => {
    const result = calcNetInventory(1234567.89, 123456.78)
    expect(result).toBeCloseTo(1111111.11, 2)
  })
})

// ─── P6.2 跌价变动 → 重算（composable 集成测试）─────────────────────────

describe('inventoryNetRow — 跌价变动自动重算', () => {
  function createMap(data: Record<string, string | null>): Map<string, ChecklistResponse> {
    const map = new Map<string, ChecklistResponse>()
    for (const [id, val] of Object.entries(data)) {
      map.set(id, { item_id: id, conclusion: val, remark: null })
    }
    // 标记有持久化数据防止 seed 覆盖
    map.set('F2-adjudication-data', { item_id: 'F2-adjudication-data', conclusion: '', remark: '{}' })
    return map
  }

  it('初始: 净额 = 原值合计审定 − 跌价准备审定', () => {
    // raw-materials gross opening=100000, impairment-provision opening=20000
    const map = createMap({
      'F2-1-gross-raw-materials-opening': '500000',
      'F2-1-gross-raw-materials-increase': '100000',
      'F2-1-gross-raw-materials-decrease': '50000',
      'F2-1-impairment-impairment-provision-opening': '80000',
      'F2-1-impairment-impairment-provision-increase': '20000',
    })

    const allResponses = ref(map)
    const { inventoryNetRow, grossSubtotal, impairmentSubtotal } = useF2Adjudication({
      wpId: ref('test-wp'),
      projectId: ref('test-project'),
      allResponses: allResponses as any,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    // gross subtotal endAudited: 500000 + 100000 - 50000 + 0(adj) = 550000
    expect(grossSubtotal.value.endAudited).toBe(550000)
    // impairment row endAudited: 80000 + 20000 - 0 + 0 = 100000
    expect(inventoryNetRow.value.totalBalance).toBe(550000)
    expect(inventoryNetRow.value.impairmentProvision).toBe(100000)
    expect(inventoryNetRow.value.netAmount).toBe(450000)
  })

  it('跌价变动后净额自动重算', async () => {
    const map = createMap({
      'F2-1-gross-raw-materials-opening': '1000000',
      'F2-1-impairment-impairment-provision-opening': '100000',
    })

    const allResponses = ref(map)
    const { inventoryNetRow } = useF2Adjudication({
      wpId: ref('test-wp'),
      projectId: ref('test-project'),
      allResponses: allResponses as any,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    // 初始: 净额 = 1000000 - 100000 = 900000
    expect(inventoryNetRow.value.netAmount).toBe(900000)

    // 模拟跌价变动：增加跌价准备 50000
    allResponses.value.set('F2-1-impairment-impairment-provision-increase', {
      item_id: 'F2-1-impairment-impairment-provision-increase',
      conclusion: '50000',
      remark: null,
    })
    // 触发 computed 重算（Map 本身不是 reactive 但 ref 触发重算）
    allResponses.value = new Map(allResponses.value)
    await nextTick()

    // 跌价准备审定 = 100000 + 50000 = 150000
    // 净额 = 1000000 - 150000 = 850000
    expect(inventoryNetRow.value.netAmount).toBe(850000)
  })

  it('给两组不同跌价值，断言净额同步变化', async () => {
    const map = createMap({
      'F2-1-gross-finished-goods-opening': '2000000',
      'F2-1-impairment-impairment-provision-opening': '200000',
    })

    const allResponses = ref(map)
    const { inventoryNetRow } = useF2Adjudication({
      wpId: ref('test-wp'),
      projectId: ref('test-project'),
      allResponses: allResponses as any,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    // 场景 A: 跌价 200000 → 净额 1800000
    expect(inventoryNetRow.value.netAmount).toBe(1800000)

    // 场景 B: 跌价变为 500000
    allResponses.value.set('F2-1-impairment-impairment-provision-opening', {
      item_id: 'F2-1-impairment-impairment-provision-opening',
      conclusion: '500000',
      remark: null,
    })
    allResponses.value = new Map(allResponses.value)
    await nextTick()

    // 跌价 = 500000 → 净额 = 2000000 - 500000 = 1500000
    expect(inventoryNetRow.value.netAmount).toBe(1500000)
  })
})

// ─── P6.3 预填 seed 逻辑 ─────────────────────────────────────────────

describe('tb_values seed logic', () => {
  it('无持久化数据 + tb_values 存在 → seed 填入', () => {
    const map = new Map<string, ChecklistResponse>()
    const allResponses = ref(map)
    const tbValues = ref<Record<string, { opening?: number; closing?: number }>>({
      'raw-materials': { opening: 100000, closing: 150000 },
      'finished-goods': { opening: 200000, closing: 180000 },
    })

    useF2Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      debouncedSave: () => {},
      isReadonly: ref(false),
      tbValues: tbValues as any,
    })

    // raw-materials opening seeded
    expect(map.get('F2-1-gross-raw-materials-opening')?.conclusion).toBe('100000')
    // raw-materials increase = 150000 - 100000 = 50000
    expect(map.get('F2-1-gross-raw-materials-increase')?.conclusion).toBe('50000')
    // finished-goods decrease = |180000 - 200000| = 20000
    expect(map.get('F2-1-gross-finished-goods-decrease')?.conclusion).toBe('20000')
  })

  it('已有持久化数据 → 不覆盖（幂等）', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-adjudication-data', { item_id: 'F2-adjudication-data', conclusion: '', remark: '{}' })
    const allResponses = ref(map)
    const tbValues = ref<Record<string, { opening?: number; closing?: number }>>({
      'raw-materials': { opening: 999999, closing: 999999 },
    })

    useF2Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      debouncedSave: () => {},
      isReadonly: ref(false),
      tbValues: tbValues as any,
    })

    // 不应 seed（有持久化标记）
    expect(map.has('F2-1-gross-raw-materials-opening')).toBe(false)
  })

  it('用户已编辑过（有 F2-1 前缀 key）→ 不覆盖', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-1-gross-raw-materials-opening', {
      item_id: 'F2-1-gross-raw-materials-opening',
      conclusion: '888888',
      remark: null,
    })
    const allResponses = ref(map)
    const tbValues = ref<Record<string, { opening?: number; closing?: number }>>({
      'raw-materials': { opening: 111111, closing: 222222 },
    })

    useF2Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      debouncedSave: () => {},
      isReadonly: ref(false),
      tbValues: tbValues as any,
    })

    // 保留用户编辑的值
    expect(map.get('F2-1-gross-raw-materials-opening')?.conclusion).toBe('888888')
  })
})
