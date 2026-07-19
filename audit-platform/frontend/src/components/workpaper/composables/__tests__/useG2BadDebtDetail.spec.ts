/**
 * useG2BadDebtDetail — G2-3 滚动态 + 账龄枚举
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useG2BadDebtDetail, buildBadDebtDisplayRows } from '../useG2BadDebtDetail'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as any, onBeforeUnmount: vi.fn() }
})

vi.mock('@/composables/useAgingConfig', async () => {
  const actual = await vi.importActual<any>('@/composables/useAgingConfig')
  return {
    ...actual,
    useAgingConfig: () => ({
      segments: ref(actual.PRESET_SEGMENTS.THREE_YEAR),
      preset: ref('THREE_YEAR'),
      bands: ref([]),
      loading: ref(false),
      refresh: vi.fn(),
    }),
  }
})

function setup(seed?: string) {
  const map = new Map<string, any>()
  if (seed) {
    map.set('G2-3-bad-debt-rows', { item_id: 'G2-3-bad-debt-rows', conclusion: null, remark: seed })
  }
  const allResponses = ref(map)
  const bd = useG2BadDebtDetail({
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  })
  return { bd, allResponses }
}

describe('useG2BadDebtDetail — 滚动态公式', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('期初审定 / 期末未审 / 期末审定公式', () => {
    const rows = JSON.stringify([
      {
        id: 'ind-1',
        seq: 1,
        category: 'individual',
        item: 'A公司',
        openingUnadjusted: 1000,
        openingAdjustment: 100,
        provisionIncrease: 200,
        otherIncrease: 50,
        reversal: 30,
        writeOff: 20,
        otherDecrease: 10,
        closingAdjustment: 5,
        reason: '',
      },
    ])
    const { bd } = setup(rows)
    const leaf = bd.dataRows.value.find((r) => r.id === 'ind-1')!
    // 期初审定 = 1100
    expect(leaf.openingAudited).toBe(1100)
    // 期末未审 = 1100+200+50-30-20-10 = 1290
    expect(leaf.closingUnadjusted).toBe(1290)
    // 期末审定 = 1290+5 = 1295
    expect(leaf.closingAudited).toBe(1295)
  })

  it('默认含单项区 + 组合账龄段 + 合计', () => {
    const { bd } = setup()
    const kinds = bd.dataRows.value.map((r) => r.kind)
    expect(kinds).toContain('section_header')
    expect(kinds).toContain('footer')
    const portfolio = bd.dataRows.value.filter((r) => r.category === 'portfolio' && r.kind === 'leaf')
    expect(portfolio).toHaveLength(PRESET_SEGMENTS.THREE_YEAR.length)
  })

  it('切换 5 年段扩展组合行', async () => {
    const { bd } = setup()
    bd.setAgingPreset('FIVE_YEAR')
    await nextTick()
    expect(bd.agingPreset.value).toBe('FIVE_YEAR')
    const portfolio = bd.dataRows.value.filter((r) => r.category === 'portfolio' && r.kind === 'leaf')
    expect(portfolio).toHaveLength(6)
  })

  it('切换自定义使用表级段名', async () => {
    const { bd } = setup()
    expect(bd.setAgingPreset('CUSTOM', ['短', '中', '长'])).toBe(true)
    await nextTick()
    expect(bd.agingPreset.value).toBe('CUSTOM')
    expect(bd.segments.value.map((s) => s.label)).toEqual(['短', '中', '长'])
  })

  it('合计汇总单项+组合', () => {
    const rows = JSON.stringify([
      {
        id: 'ind-1', seq: 1, category: 'individual', item: 'A',
        openingUnadjusted: 100, openingAdjustment: 0,
        provisionIncrease: 0, otherIncrease: 0, reversal: 0, writeOff: 0, otherDecrease: 0,
        closingAdjustment: 0, reason: '',
      },
      {
        id: 'port-1', seq: 1, category: 'portfolio', item: '1年以内', agingKey: 'within1',
        openingUnadjusted: 50, openingAdjustment: 0,
        provisionIncrease: 10, otherIncrease: 0, reversal: 0, writeOff: 0, otherDecrease: 0,
        closingAdjustment: 0, reason: '',
      },
    ])
    const { bd } = setup(rows)
    expect(bd.totals.value.openingAudited).toBe(150)
    expect(bd.totals.value.closingAudited).toBe(160)
  })

  it('兼容旧 ECL 数组迁移为单项行', () => {
    const legacy = JSON.stringify([
      {
        id: 'old-1',
        seq: 1,
        investTarget: '旧标的',
        previousECL: 80,
        companyProvision: 100,
        writeOff: 0,
        recovery: 0,
        transferIn: 0,
        transferOut: 0,
        eclStage: 'Stage1',
        pd12Month: 0.01,
      },
    ])
    const { bd } = setup(legacy)
    const leaf = bd.dataRows.value.find((r) => r.kind === 'leaf' && r.category === 'individual')!
    expect(leaf.item).toBe('旧标的')
    expect(leaf.openingUnadjusted).toBe(80)
  })

  it('buildBadDebtDisplayRows 纯函数', () => {
    const display = buildBadDebtDisplayRows([
      {
        id: 'x', seq: 1, category: 'individual', item: 'X',
        openingUnadjusted: 10, openingAdjustment: 0,
        provisionIncrease: 0, otherIncrease: 0, reversal: 0, writeOff: 0, otherDecrease: 0,
        closingAdjustment: 0, reason: '',
      },
    ])
    expect(display[0].kind).toBe('section_header')
    expect(display.at(-1)?.kind).toBe('footer')
    expect(display.at(-1)?.closingAudited).toBe(10)
  })
})
