/**
 * Unit tests for useG2ECLCalc — 单项/账龄组合/自定义枚举/推送 G2-4
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useG2ECLCalc, syncAgingGroupRows } from '../useG2ECLCalc'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    onBeforeUnmount: vi.fn(),
  }
})

vi.mock('@/composables/useAgingConfig', async () => {
  const actual = await vi.importActual<any>('@/composables/useAgingConfig')
  return {
    ...actual,
    useAgingConfig: () => ({
      segments: ref(actual.PRESET_SEGMENTS.FIVE_YEAR),
      preset: ref('FIVE_YEAR'),
      bands: ref([]),
      loading: ref(false),
      refresh: vi.fn(),
    }),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), info: vi.fn(), success: vi.fn() },
}))

function setup() {
  const allResponses = ref(new Map<string, any>())
  const saves: Array<{ id: string; data: any }> = []
  const debouncedSave = (itemId: string, data: any) => {
    saves.push({ id: itemId, data })
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion: data.conclusion ?? null,
      remark: data.remark ?? null,
    })
  }
  const ecl = useG2ECLCalc({
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    debouncedSave,
    isReadonly: ref(false),
  })
  return { ecl, allResponses, saves }
}

describe('useG2ECLCalc', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('默认 5 年段 + 两个账龄组合', () => {
    const { ecl } = setup()
    expect(ecl.agingPreset.value).toBe('FIVE_YEAR')
    expect(ecl.segments.value).toHaveLength(PRESET_SEGMENTS.FIVE_YEAR.length)
    expect(ecl.agingGroups.value.length).toBeGreaterThanOrEqual(2)
    expect(ecl.agingGroups.value[0].rows).toHaveLength(6)
  })

  it('应计提 = 余额 × 损失率；差异 = 应计提 − 账面', () => {
    const { ecl } = setup()
    ecl.addSingleRow()
    const id = ecl.singleRows.value[0].rowId
    ecl.updateSingleCell(id, 'auditedBalance', 1000)
    ecl.updateSingleCell(id, 'lossRate', 0.05)
    ecl.updateSingleCell(id, 'bookBalance', 30)
    expect(ecl.singleRows.value[0].expectedProvision).toBeCloseTo(50, 5)
    expect(ecl.singleRows.value[0].difference).toBeCloseTo(20, 5)
  })

  it('切换 3 年段并 remap', async () => {
    const { ecl } = setup()
    const gid = ecl.agingGroups.value[0].groupId
    const rid = ecl.agingGroups.value[0].rows[0].rowId
    ecl.updateAgingCell(gid, rid, 'auditedBalance', 500)
    ecl.updateAgingCell(gid, rid, 'lossRate', 0.01)
    ecl.setAgingPreset('THREE_YEAR')
    await nextTick()
    expect(ecl.agingPreset.value).toBe('THREE_YEAR')
    expect(ecl.agingGroups.value[0].rows.filter((r) => !r.archived)).toHaveLength(4)
    expect(ecl.agingGroups.value[0].rows[0].auditedBalance).toBe(500)
  })

  it('自定义账龄至少 2 段', () => {
    const { ecl } = setup()
    expect(ecl.setAgingPreset('CUSTOM', ['仅一段'])).toBe(false)
    expect(ecl.setAgingPreset('CUSTOM', ['0-6月', '6-12月', '1年以上'])).toBe(true)
    expect(ecl.agingPreset.value).toBe('CUSTOM')
    expect(ecl.segments.value).toHaveLength(3)
  })

  it('推送差异至 G2-4', () => {
    const { ecl, saves } = setup()
    ecl.addSingleRow()
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'investTarget', '甲债券')
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'auditedBalance', 1000)
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'lossRate', 0.1)
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'bookBalance', 0)
    const n = ecl.pushDiffsToG24()
    expect(n).toBe(1)
    const adj = saves.find((s) => s.id === 'G2-4-rows')
    expect(adj).toBeTruthy()
    const rows = JSON.parse(String(adj!.data.remark))
    expect(rows[0].remark).toContain('G2-7')
    expect(rows[0].creditAmount).toBeCloseTo(100, 5)
  })

  it('回填 G2-3 本期计提（单项 + 账龄段）', () => {
    const { ecl, allResponses } = setup()
    ecl.addSingleRow()
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'investTarget', '甲债券')
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'auditedBalance', 1000)
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'lossRate', 0.1)
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'bookBalance', 0)
    const g = ecl.agingGroups.value[0]
    const within = g.rows.find((r) => r.segmentKey === 'within1')!
    ecl.updateAgingCell(g.groupId, within.rowId, 'auditedBalance', 500)
    ecl.updateAgingCell(g.groupId, within.rowId, 'lossRate', 0.02)
    ecl.updateAgingCell(g.groupId, within.rowId, 'bookBalance', 0)
    const r = ecl.pushProvisionToG23('expected')
    expect(r.individual).toBeGreaterThanOrEqual(1)
    expect(r.portfolio).toBeGreaterThanOrEqual(1)
    const leaves = JSON.parse(String(allResponses.value.get('G2-3-bad-debt-rows')?.remark))
    const ind = leaves.find((x: any) => x.category === 'individual' && x.item === '甲债券')
    expect(ind.provisionIncrease).toBeCloseTo(100, 5)
    const port = leaves.find((x: any) => x.category === 'portfolio' && x.agingKey === 'within1')
    expect(port.provisionIncrease).toBeCloseTo(10, 5)
  })

  it('回填 G2-3 默认用差异口径', () => {
    const { ecl, allResponses } = setup()
    ecl.addSingleRow()
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'investTarget', '乙债')
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'auditedBalance', 1000)
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'lossRate', 0.1)
    ecl.updateSingleCell(ecl.singleRows.value[0].rowId, 'bookBalance', 40)
    const r = ecl.pushProvisionToG23('difference')
    expect(r.individual).toBeGreaterThanOrEqual(1)
    const leaves = JSON.parse(String(allResponses.value.get('G2-3-bad-debt-rows')?.remark))
    const ind = leaves.find((x: any) => x.item === '乙债')
    expect(ind.provisionIncrease).toBeCloseTo(60, 5)
  })

  it('syncAgingGroupRows 保留已有段数据', () => {
    const existing = [
      {
        rowId: '1',
        segmentKey: 'within1',
        agingBand: '1年以内',
        auditedBalance: 100,
        lossRate: 0.02,
        expectedProvision: 2,
        bookBalance: 1,
        difference: 1,
        basis: '',
        indexRef: '',
      },
    ]
    const next = syncAgingGroupRows(existing, PRESET_SEGMENTS.THREE_YEAR)
    expect(next.find((r) => r.segmentKey === 'within1')?.auditedBalance).toBe(100)
    expect(next.filter((r) => !r.archived)).toHaveLength(4)
  })
})
