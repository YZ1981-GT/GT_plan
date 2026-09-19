/**
 * H10 P2 — 空行隐藏 / 排除科目守卫 / DR·NM 映射
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useH10Disclosure } from '../useH10Disclosure'
import {
  detectH10ExcludedClassText,
  scanH10ExcludedClassRows,
  summarizeH10ExcludedHits,
} from '../h10ExcludedClassGuard'
import { H10_SOURCE_WP_TO_ROW_KEY } from '../useH10CrossSheet'
import { aggregateH10DetailByAdjRowKey } from '../h10FillFromDetail'
import { SOURCE_WP_OPTIONS } from '../h10Constants'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onMounted: vi.fn(), onBeforeUnmount: vi.fn() }
})

vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn().mockResolvedValue({ data: { content: 'AI' } }) },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

describe('h10ExcludedClassGuard', () => {
  it('识别投房/长投/金融工具关键词', () => {
    expect(detectH10ExcludedClassText('出售投资性房地产A')?.matched).toBe('投资性房地产')
    expect(detectH10ExcludedClassText('处置长投子公司')?.matched).toBe('长期股权投资')
    expect(detectH10ExcludedClassText('交易性金融资产')?.matched).toBe('金融工具')
    expect(detectH10ExcludedClassText('机床设备')).toBeNull()
  })

  it('汇总告警文案', () => {
    const hits = scanH10ExcludedClassRows([
      { id: '1', assetName: '大厦', assetType: '投资性房地产' },
      { id: '2', assetName: '股权', assetType: '长期股权投资' },
    ])
    expect(hits).toHaveLength(2)
    expect(summarizeH10ExcludedHits(hits)).toContain('不应计入 6115')
  })
})

describe('DR/NM source mapping', () => {
  it('SOURCE_WP_OPTIONS 含 DR/NM', () => {
    expect(SOURCE_WP_OPTIONS.some((o) => o.value === 'DR')).toBe(true)
    expect(SOURCE_WP_OPTIONS.some((o) => o.value === 'NM')).toBe(true)
  })

  it('汇总到债务重组/非货币审定行', () => {
    expect(H10_SOURCE_WP_TO_ROW_KEY.DR).toBe('debt_restructuring_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.NM).toBe('non_monetary_exchange')
    const totals = aggregateH10DetailByAdjRowKey([
      { sourceWp: 'DR', disposalGainLoss: 10 },
      { sourceWp: 'NM', disposalGainLoss: -3 },
    ])
    expect(totals.debt_restructuring_disposal).toBe(10)
    expect(totals.non_monetary_exchange).toBe(-3)
  })
})

describe('useH10Disclosure hide empty rows', () => {
  beforeEach(() => vi.clearAllMocks())

  it('有数据后默认隐藏空行，合计仍按全量', () => {
    const allResponses = ref(new Map<string, any>([
      ['H10-disclosure-listed', {
        item_id: 'H10-disclosure-listed',
        remark: JSON.stringify([
          { rowKey: 'fixed_asset_disposal', currentAmount: 100, priorAmount: 0 },
          { rowKey: 'construction_disposal', currentAmount: 0, priorAmount: 0 },
        ]),
      }],
    ]))
    const dis = useH10Disclosure({
      variant: 'listed',
      allResponses,
      debouncedSave: vi.fn(),
      wpId: ref('wp1'),
      projectId: ref('p1'),
      isReadonly: ref(false),
    })

    expect(dis.hiddenEmptyCount.value).toBeGreaterThan(0)
    expect(dis.displayRows.value.some((r) => r.rowKey === 'fixed_asset_disposal')).toBe(true)
    expect(dis.displayRows.value.some((r) => r.rowKey === 'construction_disposal')).toBe(false)
    const total = dis.displayRows.value.find((r) => r.rowKey === 'total')!
    expect(total.currentAmount).toBe(100)

    dis.setShowEmptyRows(true)
    expect(dis.hiddenEmptyCount.value).toBe(0)
    expect(dis.displayRows.value.length).toBeGreaterThan(2)
  })
})
