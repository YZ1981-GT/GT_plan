/**
 * K4 其他流动负债 — 集成联动验证测试
 *
 * Phase 7 Task 7.2:
 * - sheetName正则提取 → 正确子组件路由
 * - 负债类回写 TB（科目由调用方传入；K4 没有统一标准码）+ EventBus substantive:adjudicated
 * - 跨sheet: 明细合计 → 审定表交叉验证
 * - 导入导出 composable 初始化
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/
 * Requirements: 1.2, 2.5, 2.6, 3.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mockPut, mockPost, mockGet, mockEmit } = vi.hoisted(() => ({
  mockPut: vi.fn().mockResolvedValue({}),
  mockPost: vi.fn().mockResolvedValue({ message: '已发布到试算表' }),
  mockGet: vi.fn().mockResolvedValue({}),
  mockEmit: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: mockGet,
    put: mockPut,
    post: mockPost,
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

// ═══ 7.2-B: TB writeback flow — writebackTB(调用方传入的科目) + EventBus emit ═══
//
// 🔴 K4 其他流动负债**没有统一标准科目码**（宁缺勿造，见 k4AccountScope.ts）。
//    原用例断言 writebackTB 缺省发布到 `2245` —— 那是缺省值写死的错码，不是其他流动负债。
//    现 writebackTB 必须由调用方传科目（K4TabAdjudication 取 k4Code）；传空串不发布。

/** 模拟本项目从 tb_source_codes 解析出的科目码（K4 没有统一标准码，各项目不同） */
const RESOLVED = '2249'

describe('K4 Integration — TB回写(负债类，科目由调用方传入) + EventBus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPut.mockResolvedValue({})
    mockPost.mockResolvedValue({ message: '已发布到试算表' })
    mockGet.mockResolvedValue({})
  })

  async function makeFormData(wpId: string) {
    const { useK4FormData } = await import('../composables/useK4FormData')
    const { ref } = await import('vue')
    return useK4FormData({ wpId: ref(wpId), projectId: ref('proj-k4'), sheetPrefix: 'K4-1' })
  }

  it('writebackTB 按调用方传入的科目发布（publish-to-tb，balance 口径）', async () => {
    const formData = await makeFormData('wp-k4-001')
    await formData.writebackTB(800_000, RESOLVED)

    expect(mockPut).not.toHaveBeenCalled()
    expect(mockPost).toHaveBeenCalledWith(
      '/api/workpapers/wp-k4-001/audit-determination/publish-to-tb',
      expect.objectContaining({
        sheet_name: expect.stringMatching(/K4-1/),
        writeback_rows: [{ account_code: RESOLVED, audited_amount: 800_000, amount_kind: 'balance' }],
      }),
    )
  })

  it('writebackTB 发布后 emit substantive:adjudicated，事件码 = 发布码', async () => {
    const formData = await makeFormData('wp-k4-002')
    await formData.writebackTB(1_200_000, RESOLVED)

    expect(mockEmit).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({ accountCode: RESOLVED, auditedAmount: 1_200_000, wpCode: 'K4' }),
    )
  })

  it('writebackTB 更新本地 tbData.audited', async () => {
    const formData = await makeFormData('wp-k4-003')
    expect(formData.tbData.value.audited).toBe(0)
    await formData.writebackTB(2_500_000, RESOLVED)
    expect(formData.tbData.value.audited).toBe(2_500_000)
  })

  it('writebackTB zero amount is valid (全部清偿)', async () => {
    const formData = await makeFormData('wp-k4-004')
    await formData.writebackTB(0, RESOLVED)

    expect(mockPut).not.toHaveBeenCalled()
    expect(mockPost).toHaveBeenCalledWith(
      '/api/workpapers/wp-k4-004/audit-determination/publish-to-tb',
      expect.objectContaining({
        writeback_rows: [{ account_code: RESOLVED, audited_amount: 0, amount_kind: 'balance' }],
      }),
    )
    expect(formData.tbData.value.audited).toBe(0)
  })

  it('writebackTB negative amount (负债转出) still calls API', async () => {
    const formData = await makeFormData('wp-k4-005')
    await formData.writebackTB(-100_000, RESOLVED)

    expect(mockPut).not.toHaveBeenCalled()
    expect(mockPost).toHaveBeenCalledWith(
      '/api/workpapers/wp-k4-005/audit-determination/publish-to-tb',
      expect.objectContaining({
        writeback_rows: [{ account_code: RESOLVED, audited_amount: -100_000, amount_kind: 'balance' }],
      }),
    )
  })

  it('🔴 科目为空串（本项目未定位到）⇒ 不发布、不发事件（宁缺勿造，不回退任何码）', async () => {
    const formData = await makeFormData('wp-k4-006')
    await formData.writebackTB(300_000, '')

    expect(mockPost).not.toHaveBeenCalled()
    expect(mockEmit).not.toHaveBeenCalledWith('substantive:adjudicated', expect.anything())
    expect(formData.tbData.value.audited).toBe(0)
  })
})

// ═══ 7.2-B2: loadTbData —— 读后端真实下发的键；解析不出科目不取数 ═══

describe('K4 Integration — loadTbData 取数口径', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  /** selfLoad 依次 GET render-config / checklist-responses / (可选) trial-balance */
  function stubGets(htmlData: Record<string, unknown>, tbRows: unknown[] = []) {
    mockGet.mockImplementation(async (url: string) => {
      if (url.includes('/render-config')) return { html_data: htmlData }
      if (url.includes('/checklist-responses')) return []
      if (url.includes('/trial-balance')) return tbRows
      return {}
    })
  }

  function tbCalls() {
    return mockGet.mock.calls.filter(([url]) => String(url).includes('/trial-balance'))
  }

  async function load(htmlData: Record<string, unknown>, tbRows: unknown[] = []) {
    stubGets(htmlData, tbRows)
    const { useK4FormData } = await import('../composables/useK4FormData')
    const { ref } = await import('vue')
    const fd = useK4FormData({ wpId: ref('wp-k4-load'), projectId: ref('proj-k4'), sheetPrefix: 'K4-1' })
    await fd.selfLoad()
    return fd
  }

  it('render 下发 tb_values.liability_* ⇒ 直接取用，不再请求试算表', async () => {
    const fd = await load({ tb_values: { liability_unadjusted: 51_000, liability_audited: 52_000 } })
    expect(fd.tbData.value).toEqual({ unadjusted: 51_000, audited: 52_000 })
    expect(tbCalls()).toHaveLength(0)
  })

  it('🔴 解析不出科目（gross 为空）⇒ 不请求试算表（原实现按写死的 2245 去取）', async () => {
    const fd = await load({ tb_source_codes: { gross: [], gross_standard: [] } })
    expect(tbCalls()).toHaveLength(0)
    expect(fd.tbData.value).toEqual({ unadjusted: 0, audited: 0 })
  })

  it('解析出科目 ⇒ 按该科目请求并只累加该科目及其子目', async () => {
    const fd = await load(
      { tb_source_codes: { gross: [RESOLVED], gross_standard: [RESOLVED] } },
      [
        { standard_account_code: RESOLVED, unadjusted_amount: 100, audited_amount: 110 },
        { standard_account_code: `${RESOLVED}.01`, unadjusted_amount: 5, audited_amount: 6 },
        { standard_account_code: '2245', unadjusted_amount: 9_999, audited_amount: 9_999 },
      ],
    )
    expect(tbCalls()).toHaveLength(1)
    expect(tbCalls()[0][1]).toMatchObject({ params: { account_prefix: RESOLVED } })
    expect(fd.tbData.value).toEqual({ unadjusted: 105, audited: 116 })
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
