/**
 * K4 其他流动负债 — 集成联动验证测试
 *
 * Phase 7 Task 7.2:
 * - sheetName正则提取 → 正确子组件路由
 * - 负债类回写 TB(2245) + EventBus substantive:adjudicated
 * - 跨sheet: 明细合计 → 审定表交叉验证
 * - 导入导出 composable 初始化
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/
 * Requirements: 1.2, 2.5, 2.6, 3.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mockPut, mockGet, mockEmit } = vi.hoisted(() => ({
  mockPut: vi.fn().mockResolvedValue({}),
  mockGet: vi.fn().mockResolvedValue({}),
  mockEmit: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: mockGet,
    put: mockPut,
  },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: mockEmit,
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// ═══ 7.2-A: sheetName regex extraction → component routing ═══

describe('K4 Integration — sheetName分发路由', () => {
  /**
   * 复现 GtK4OtherCurrentLiabilities.vue 中 currentSheet computed 逻辑。
   * 验证正则提取编码的正确性。
   */
  function extractSheet(sheetName: string): string {
    const name = sheetName || ''
    if (/底稿目录/.test(name)) return 'K4'
    if (/附注.*上市/.test(name)) return '附注上市'
    if (/附注.*国/.test(name)) return '附注国企'
    if (/K4A/.test(name)) return 'K4A'
    const m = name.match(/(K4-\d+)/)
    if (m) return m[1]
    if (/\bK4\b/.test(name) && !/K4-/.test(name) && !/K4A/.test(name)) return 'K4'
    return ''
  }

  it('底稿目录 → K4', () => {
    expect(extractSheet('底稿目录')).toBe('K4')
    expect(extractSheet('K4 底稿目录')).toBe('K4')
  })

  it('实质性程序表 K4A → K4A', () => {
    expect(extractSheet('实质性程序表 K4A')).toBe('K4A')
    expect(extractSheet('K4A 其他流动负债实质性程序表')).toBe('K4A')
  })

  it('审定表 K4-1 → K4-1', () => {
    expect(extractSheet('审定表 K4-1')).toBe('K4-1')
    expect(extractSheet('K4-1 审定表')).toBe('K4-1')
  })

  it('明细表 K4-2 → K4-2', () => {
    expect(extractSheet('明细表 K4-2')).toBe('K4-2')
    expect(extractSheet('K4-2 其他流动负债明细')).toBe('K4-2')
  })

  it('调整分录汇总 K4-3 → K4-3', () => {
    expect(extractSheet('调整分录汇总 K4-3')).toBe('K4-3')
  })

  it('检查表 K4-4 → K4-4', () => {
    expect(extractSheet('其他流动负债检查表 K4-4')).toBe('K4-4')
  })

  it('附注披露信息（上市公司） → 附注上市', () => {
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
  })

  it('附注披露信息（国企） → 附注国企', () => {
    expect(extractSheet('附注披露信息（国企）')).toBe('附注国企')
  })

  it('未匹配 → 空字符串 (fallback OO)', () => {
    expect(extractSheet('随机无关sheet名')).toBe('')
    expect(extractSheet('')).toBe('')
  })

  it('纯 K4 (无后缀/无K4-/无K4A) → K4 目录', () => {
    expect(extractSheet('K4')).toBe('K4')
  })
})

// ═══ 7.2-B: TB writeback flow — writebackTB(2245) + EventBus emit ═══

describe('K4 Integration — TB回写(2245负债类) + EventBus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPut.mockResolvedValue({})
    mockGet.mockResolvedValue({})
  })

  it('writebackTB calls PUT with account_code=2245 + correct amount', async () => {
    const { useK4FormData } = await import('../composables/useK4FormData')
    const { ref } = await import('vue')

    const formData = useK4FormData({
      wpId: ref('wp-k4-001'),
      projectId: ref('proj-001'),
      sheetPrefix: 'K4-1',
    })

    await formData.writebackTB(800_000)

    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      { account_code: '2245', audited_amount: 800_000 },
    )
  })

  it('writebackTB emits substantive:adjudicated with 2245/K4 payload', async () => {
    const { useK4FormData } = await import('../composables/useK4FormData')
    const { ref } = await import('vue')

    const formData = useK4FormData({
      wpId: ref('wp-k4-002'),
      projectId: ref('proj-002'),
      sheetPrefix: 'K4-1',
    })

    await formData.writebackTB(1_200_000)

    expect(mockEmit).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        accountCode: '2245',
        auditedAmount: 1_200_000,
        wpCode: 'K4',
      }),
    )
  })

  it('writebackTB updates local tbData.audited2245', async () => {
    const { useK4FormData } = await import('../composables/useK4FormData')
    const { ref } = await import('vue')

    const formData = useK4FormData({
      wpId: ref('wp-k4-003'),
      projectId: ref('proj-003'),
      sheetPrefix: 'K4-1',
    })

    expect(formData.tbData.value.audited2245).toBe(0)
    await formData.writebackTB(2_500_000)
    expect(formData.tbData.value.audited2245).toBe(2_500_000)
  })

  it('writebackTB zero amount is valid (全部清偿)', async () => {
    const { useK4FormData } = await import('../composables/useK4FormData')
    const { ref } = await import('vue')

    const formData = useK4FormData({
      wpId: ref('wp-k4-004'),
      projectId: ref('proj-004'),
      sheetPrefix: 'K4-1',
    })

    await formData.writebackTB(0)

    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-004/trial-balance/writeback',
      { account_code: '2245', audited_amount: 0 },
    )
    expect(formData.tbData.value.audited2245).toBe(0)
  })

  it('writebackTB negative amount (负债转出) still calls API', async () => {
    const { useK4FormData } = await import('../composables/useK4FormData')
    const { ref } = await import('vue')

    const formData = useK4FormData({
      wpId: ref('wp-k4-005'),
      projectId: ref('proj-005'),
      sheetPrefix: 'K4-1',
    })

    await formData.writebackTB(-100_000)

    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-005/trial-balance/writeback',
      { account_code: '2245', audited_amount: -100_000 },
    )
  })
})

// ═══ 7.2-C: CrossSheet — detail total → adjudication verification ═══

describe('K4 Integration — 明细聚合→审定表交叉验证 (Req 2.5)', () => {
  it('detailTotals reads K4-2-detail-total from allResponses', async () => {
    const { ref } = await import('vue')
    const { useK4CrossSheet } = await import('../composables/useK4CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K4-2-detail-total', { remark: '500000' }],
    ]))

    const crossSheet = useK4CrossSheet(allResponses)

    expect(crossSheet.detailTotals.value.total).toBe(500000)
  })

  it('detailTotals: missing key → 0', async () => {
    const { ref } = await import('vue')
    const { useK4CrossSheet } = await import('../composables/useK4CrossSheet')

    const allResponses = ref(new Map<string, any>())
    const crossSheet = useK4CrossSheet(allResponses)

    expect(crossSheet.detailTotals.value.total).toBe(0)
  })

  it('adjudicationFromDetail: audited matches detail total', async () => {
    const { ref } = await import('vue')
    const { useK4CrossSheet } = await import('../composables/useK4CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K4-2-detail-total', { remark: '750000' }],
    ]))

    const crossSheet = useK4CrossSheet(allResponses)

    expect(crossSheet.adjudicationFromDetail.value.audited).toBe(750000)
  })

  it('adjudicationFromDetail: null/empty → 0', async () => {
    const { ref } = await import('vue')
    const { useK4CrossSheet } = await import('../composables/useK4CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K4-2-detail-total', { remark: null }],
    ]))

    const crossSheet = useK4CrossSheet(allResponses)

    expect(crossSheet.adjudicationFromDetail.value.audited).toBe(0)
  })

  it('adjudicationFromDetail: non-numeric remark → 0', async () => {
    const { ref } = await import('vue')
    const { useK4CrossSheet } = await import('../composables/useK4CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K4-2-detail-total', { remark: 'abc' }],
    ]))

    const crossSheet = useK4CrossSheet(allResponses)

    expect(crossSheet.adjudicationFromDetail.value.audited).toBe(0)
  })
})

// ═══ 7.2-D: Import/Export composable 初始化验证 ═══

describe('K4 Integration — useK4ImportExport初始化', () => {
  it('K4_API_PREFIX constant is "k4" (source verification)', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const source = readFileSync(
      path.resolve(__dirname, '../composables/useK4ImportExport.ts'),
      'utf-8',
    )

    // K4_API_PREFIX = 'k4'
    expect(source).toMatch(/K4_API_PREFIX\s*=\s*['"]k4['"]/)
  })

  it('K4ImportableSheet includes K4-2 and K4-3', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const source = readFileSync(
      path.resolve(__dirname, '../composables/useK4ImportExport.ts'),
      'utf-8',
    )

    expect(source).toContain("'K4-2'")
    expect(source).toContain("'K4-3'")
  })

  it('uses http (axios) not native fetch', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const source = readFileSync(
      path.resolve(__dirname, '../composables/useK4ImportExport.ts'),
      'utf-8',
    )

    expect(source).toContain("from '@/utils/http'")
    // Should NOT use native fetch for API calls (401 issue)
    expect(source).not.toMatch(/\bfetch\s*\(/)
  })
})

// ═══ 7.2-E: 附注 subscribe substantive:adjudicated ═══

describe('K4 Integration — 附注subscribe刷新', () => {
  it('K4TabDisclosureListed subscribes to substantive:adjudicated', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const source = readFileSync(
      path.resolve(__dirname, '../k4/core/K4TabDisclosureListed.vue'),
      'utf-8',
    )

    expect(source).toContain("eventBus.on('substantive:adjudicated'")
    expect(source).toContain("eventBus.off('substantive:adjudicated'")
  })

  it('K4TabDisclosureSoe subscribes to substantive:adjudicated', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const source = readFileSync(
      path.resolve(__dirname, '../k4/core/K4TabDisclosureSoe.vue'),
      'utf-8',
    )

    expect(source).toContain("eventBus.on('substantive:adjudicated'")
    expect(source).toContain("eventBus.off('substantive:adjudicated'")
  })
})

// ═══ 7.2-F: K4TabAdjustment publishes adjustment:created ═══

describe('K4 Integration — 调整分录 adjustment:created', () => {
  it('K4TabAdjustment publishes adjustment:created with K4/2245 payload', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const source = readFileSync(
      path.resolve(__dirname, '../k4/core/K4TabAdjustment.vue'),
      'utf-8',
    )

    expect(source).toContain("eventBus.emit('adjustment:created'")
    expect(source).toContain("wpCode: 'K4'")
    expect(source).toContain('2245')
  })
})
