/**
 * D7 合同负债增强 — 生命周期 / 动态账龄接线测试（需组件上下文 + API mock）
 *
 * 覆盖需要 useAgingConfig（onMounted 拉取项目段）的 composable 行为：
 *  - Property 6:  D7-5 长期挂账筛选与账龄 label 填充（importFromD72）
 *  - Property 14: 段列 nested keyed 写入（updateCell agingPrior/agingAudited.{segKey}）
 *  - 单元：subject='D7' 接线 + 加载失败回退 THREE_YEAR
 *  - 单元：只读守卫（useD7Detail）
 *  - 单元：aging-config:changed 监听挂载 + 卸载移除
 *
 * Spec: .kiro/specs/d7-contract-liabilities-enhancement/
 * Task: 11
 */
import { describe, it, expect, beforeEach, beforeAll, afterAll, vi } from 'vitest'
import { defineComponent, h, ref, nextTick, type Ref } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import * as fc from 'fast-check'

// ── element-plus：仅 ElMessage 被 composable 使用，全量 mock 避免加载重型库 ──
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(vi.fn(), {
    success: vi.fn(),
    info: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  }),
}))

// ── apiProxy：控制 useAgingConfig 的 /aging/config 响应 ──
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: mockGet } }))

import { useD7Detail } from '../composables/useD7Detail'
import { useD7LongTerm } from '../composables/useD7LongTerm'
import { PRESET_SEGMENTS, clearAgingConfigCache, type AgingSegment } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '../composables/useD7FormData'

// ─── Helpers ───────────────────────────────────────────────────────────────

const THREE_YEAR_RESP = {
  preset: 'THREE_YEAR' as const,
  effective_segments: PRESET_SEGMENTS.THREE_YEAR,
  subject_overrides: {},
}

function makeMap(entries: Record<string, string> = {}): Map<string, ChecklistResponse> {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: v })
  }
  return m
}

/** 在组件上下文中调用 composable，返回其结果与 wrapper（供 unmount） */
async function mountComposable<T>(factory: () => T): Promise<{ result: T; wrapper: VueWrapper<any> }> {
  let result!: T
  const Comp = defineComponent({
    setup() {
      result = factory()
      return () => h('div')
    },
  })
  const wrapper = mount(Comp)
  await flushPromises()
  await nextTick()
  return { result, wrapper }
}

beforeEach(() => {
  clearAgingConfigCache()
  mockGet.mockReset()
  mockGet.mockResolvedValue(THREE_YEAR_RESP)
})

// ══════════════════════════════════════════════════════════════════════════════
// 单元：subject='D7' 接线 + 加载失败回退 THREE_YEAR
// ══════════════════════════════════════════════════════════════════════════════

describe('单元测试 — subject=D7 账龄接线', () => {
  it('成功加载后 useD7Detail.segments 采用项目配置段（THREE_YEAR 2-period）', async () => {
    const { result, wrapper } = await mountComposable(() =>
      useD7Detail({
        allResponses: ref(makeMap()),
        saveImmediate: async () => {},
        debouncedSave: () => {},
        wpId: ref('wp'),
        projectId: ref('p-d7-ok'),
        isReadonly: ref(false),
      }),
    )
    expect(result.segments.value.map(s => s.key)).toEqual(['within1', 'y1to2', 'y2to3', 'over3'])
    // 2-period：bands 无 currentField
    for (const b of result.bands.value) expect(b.currentField).toBe('')
    wrapper.unmount()
  })

  it('加载失败时回退 THREE_YEAR（不保留上次配置）', async () => {
    mockGet.mockReset()
    mockGet.mockRejectedValue(new Error('network fail'))
    const { result, wrapper } = await mountComposable(() =>
      useD7Detail({
        allResponses: ref(makeMap()),
        saveImmediate: async () => {},
        debouncedSave: () => {},
        wpId: ref('wp'),
        projectId: ref('p-d7-fail'),
        isReadonly: ref(false),
      }),
    )
    expect(result.segments.value.length).toBe(4)
    expect(result.segments.value.map(s => s.key)).toEqual(['within1', 'y1to2', 'y2to3', 'over3'])
    wrapper.unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 14: 段列 nested keyed 写入
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 14: 段列 nested keyed 写入', () => {
  let detail: ReturnType<typeof useD7Detail>
  let wrapper: VueWrapper<any>

  beforeAll(async () => {
    clearAgingConfigCache()
    mockGet.mockReset()
    mockGet.mockResolvedValue(THREE_YEAR_RESP)
    const mounted = await mountComposable(() =>
      useD7Detail({
        allResponses: ref(makeMap()),
        saveImmediate: async () => {},
        debouncedSave: () => {},
        wpId: ref('wp'),
        projectId: ref('p-d7-p14'),
        isReadonly: ref(false),
      }),
    )
    detail = mounted.result
    wrapper = mounted.wrapper
    // segments 就绪
    expect(detail.segments.value.length).toBe(4)
  })

  afterAll(() => {
    wrapper?.unmount()
  })

  it('updateCell(row, "agingAudited.{segKey}" / "agingPrior.{segKey}", v) 写入对应 nested 段', () => {
    // Feature: d7-contract-liabilities-enhancement, Property 14: 段列 nested keyed 写入
    const segKeys = PRESET_SEGMENTS.THREE_YEAR.map(s => s.key)
    fc.assert(
      fc.property(
        fc.constantFrom(...segKeys),
        fc.constantFrom(...segKeys),
        fc.float({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (auditedKey, priorKey, vAudited, vPrior) => {
          detail.addRow()
          const row = detail.rows.value[detail.rows.value.length - 1]
          const rowId = row.rowId

          detail.updateCell(rowId, `agingAudited.${auditedKey}`, vAudited)
          detail.updateCell(rowId, `agingPrior.${priorKey}`, vPrior)

          const updated = detail.rows.value.find(r => r.rowId === rowId)!
          expect(updated.agingAudited[auditedKey]).toBe(vAudited)
          expect(updated.agingPrior[priorKey]).toBe(vPrior)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 6: D7-5 长期挂账筛选与账龄 label 填充（importFromD72）
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 6: 长期挂账筛选 + 账龄 label（importFromD72）', () => {
  let longTerm: ReturnType<typeof useD7LongTerm>
  let allResponses: Ref<Map<string, ChecklistResponse>>
  let wrapper: VueWrapper<any>

  const SEGS = PRESET_SEGMENTS.THREE_YEAR
  const overKeys = SEGS.filter(s => s.dayFrom >= 366).map(s => s.key) // y1to2 / y2to3 / over3
  const labelByKey = new Map(SEGS.map(s => [s.key, s.label]))

  beforeAll(async () => {
    clearAgingConfigCache()
    mockGet.mockReset()
    mockGet.mockResolvedValue(THREE_YEAR_RESP)
    allResponses = ref(makeMap())
    const mounted = await mountComposable(() =>
      useD7LongTerm({
        allResponses,
        saveImmediate: async () => {},
        debouncedSave: () => {},
        wpId: ref('wp'),
        projectId: ref('p-d7-p6'),
      }),
    )
    longTerm = mounted.result
    wrapper = mounted.wrapper
    expect(longTerm.overOneYearKeys.value.sort()).toEqual([...overKeys].sort())
  })

  afterAll(() => {
    wrapper?.unmount()
  })

  const segAmt = () => fc.float({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true })

  it('选中行 ⟺ 期末审定账龄超1年段之和>0；label = 占比最大的超1年段', () => {
    // Feature: d7-contract-liabilities-enhancement, Property 6: 长期挂账筛选与账龄 label 填充
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ w: segAmt(), a: segAmt(), b: segAmt(), c: segAmt() }),
          { minLength: 0, maxLength: 8 },
        ),
        (raw) => {
          // 清空既有长期挂账行，隔离每次运行
          while (longTerm.rows.value.length > 0) {
            longTerm.removeRow(longTerm.rows.value[0].rowId)
          }

          const detailRows = raw.map((r, i) => ({
            rowId: `d${i}`,
            companyName: `客户_${i}`,
            endAudited: r.w + r.a + r.b + r.c,
            agingAudited: { within1: r.w, y1to2: r.a, y2to3: r.b, over3: r.c },
            agingPrior: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
          }))
          allResponses.value.set('D7-2-rows', {
            item_id: 'D7-2-rows', conclusion: null, remark: JSON.stringify(detailRows),
          })

          longTerm.importFromD72()

          // 期望：over1yr 段之和 > 0 的行被选中
          const expected = detailRows.filter(
            d => overKeys.reduce((s, k) => s + (d.agingAudited as any)[k], 0) > 0,
          )
          const importedNames = new Set(longTerm.rows.value.map(r => r.customerName))
          expect(importedNames.size).toBe(expected.length)

          for (const d of expected) {
            expect(importedNames.has(d.companyName)).toBe(true)
            // label = 占比最大的超1年段（顺序首个最大值优先）
            let topKey = overKeys[0]
            let topAmt = -Infinity
            for (const k of overKeys) {
              const amt = (d.agingAudited as any)[k]
              if (amt > topAmt) { topAmt = amt; topKey = k }
            }
            const expectedLabel = labelByKey.get(topKey) || topKey
            const imported = longTerm.rows.value.find(r => r.customerName === d.companyName)!
            expect(imported.aging).toBe(expectedLabel)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 单元：只读守卫（useD7Detail）
// ══════════════════════════════════════════════════════════════════════════════

describe('单元测试 — 只读守卫（useD7Detail）', () => {
  it('只读模式下 addRow / updateCell 均为 no-op', async () => {
    const seedRow = {
      rowId: 'r1', companyName: 'A', contractName: '',
      agingPrior: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
      agingAudited: { within1: 10, y1to2: 0, y2to3: 0, over3: 0 },
    }
    const allResponses = ref(makeMap({ 'D7-2-rows': JSON.stringify([seedRow]) }))
    const { result, wrapper } = await mountComposable(() =>
      useD7Detail({
        allResponses,
        saveImmediate: async () => {},
        debouncedSave: () => {},
        wpId: ref('wp'),
        projectId: ref('p-d7-ro'),
        isReadonly: ref(true),
      }),
    )

    expect(result.rows.value.length).toBe(1)
    result.addRow()
    expect(result.rows.value.length).toBe(1) // 未新增

    result.updateCell('r1', 'agingAudited.within1', 999)
    expect(result.rows.value[0].agingAudited.within1).toBe(10) // 未改变
    wrapper.unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 单元：aging-config:changed 监听挂载 + 卸载移除
// ══════════════════════════════════════════════════════════════════════════════

describe('单元测试 — aging-config:changed 监听生命周期', () => {
  it('挂载时注册 aging-config:changed 监听，卸载时全部移除', async () => {
    let added = 0
    let removed = 0
    const realAdd = window.addEventListener.bind(window)
    const realRemove = window.removeEventListener.bind(window)
    const addSpy = vi.spyOn(window, 'addEventListener').mockImplementation((type: any, ...rest: any[]) => {
      if (type === 'aging-config:changed') added++
      return (realAdd as any)(type, ...rest)
    })
    const removeSpy = vi.spyOn(window, 'removeEventListener').mockImplementation((type: any, ...rest: any[]) => {
      if (type === 'aging-config:changed') removed++
      return (realRemove as any)(type, ...rest)
    })

    const { wrapper } = await mountComposable(() =>
      useD7Detail({
        allResponses: ref(makeMap()),
        saveImmediate: async () => {},
        debouncedSave: () => {},
        wpId: ref('wp'),
        projectId: ref('p-d7-evt'),
        isReadonly: ref(false),
      }),
    )
    // useD7Detail 自身 + useAgingConfig 各注册一次
    expect(added).toBeGreaterThanOrEqual(1)

    // 派发事件不应抛错
    expect(() => window.dispatchEvent(new Event('aging-config:changed'))).not.toThrow()

    wrapper.unmount()
    await nextTick()
    // 卸载后全部移除（对称）
    expect(removed).toBe(added)

    addSpy.mockRestore()
    removeSpy.mockRestore()
  })
})
