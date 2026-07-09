/**
 * K3 其他应付款 — 集成联动验证测试
 *
 * Phase 6 验证 Tasks 6.1 / 6.2 / 6.3 的 EventBus 联动 + 抽凭/OCR 接线 + 双模式
 * Phase 7 验证 Task 7.2: 负债类回写 + 长期挂账联动 + 账龄勾稽
 *
 * Spec: .kiro/specs/k3-other-payables/
 * Requirements: 2.5, 2.6, 4.4, 5.2, 5.4, 6.3, 8.1, 8.2
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ═══ Task 6.1: EventBus TB回写(2241) + substantive:adjudicated → 附注 ═══

describe('K3 Integration — Task 6.1: TB回写 + substantive:adjudicated', () => {
  let eventBus: { emit: ReturnType<typeof vi.fn>; on: ReturnType<typeof vi.fn>; off: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    eventBus = { emit: vi.fn(), on: vi.fn(), off: vi.fn() }
    vi.doMock('@/utils/eventBus', () => ({ eventBus }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('writebackTB publishes substantive:adjudicated with correct payload', async () => {
    // Mock api
    const api = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    vi.doMock('@/services/apiProxy', () => ({ api }))

    const { useK3FormData } = await import('../composables/useK3FormData')
    const { ref } = await import('vue')

    const formData = useK3FormData({
      wpId: ref('test-wp-123'),
      projectId: ref('test-proj-456'),
      sheetPrefix: 'K3-1',
    })

    await formData.writebackTB(500000)

    // Verify TB writeback API call
    expect(api.put).toHaveBeenCalledWith(
      '/api/projects/test-proj-456/trial-balance/writeback',
      expect.objectContaining({
        account_code: '2241',
        audited_amount: 500000,
      }),
    )

    // Verify EventBus emit
    expect(eventBus.emit).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        accountCode: '2241',
        auditedAmount: 500000,
        wpCode: 'K3',
      }),
    )
  })

  it('K3TabDisclosureListed subscribes to substantive:adjudicated on mount', async () => {
    // The component subscribes in onMounted. We verify by importing the source
    // and checking eventBus.on is called with the right event name.
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const disclosureSource = readFileSync(
      path.resolve(__dirname, '../k3/core/K3TabDisclosureListed.vue'),
      'utf-8',
    )

    // Static verification: file contains the subscription pattern
    expect(disclosureSource).toContain("eventBus.on('substantive:adjudicated'")
    expect(disclosureSource).toContain("eventBus.off('substantive:adjudicated'")
  })

  it('K3TabDisclosureSoe subscribes to substantive:adjudicated on mount', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const soeSource = readFileSync(
      path.resolve(__dirname, '../k3/core/K3TabDisclosureSoe.vue'),
      'utf-8',
    )

    expect(soeSource).toContain("eventBus.on('substantive:adjudicated'")
    expect(soeSource).toContain("eventBus.off('substantive:adjudicated'")
  })
})

// ═══ Task 6.2: adjustment:created → A13 + 附注subscribe刷新 + K12联动 ═══

describe('K3 Integration — Task 6.2: adjustment:created + K12联动', () => {
  it('K3TabAdjustment publishes adjustment:created event', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const adjSource = readFileSync(
      path.resolve(__dirname, '../k3/core/K3TabAdjustment.vue'),
      'utf-8',
    )

    // Static verification: event publishing exists
    expect(adjSource).toContain("eventBus.emit('adjustment:created'")
    expect(adjSource).toContain("wpCode: 'K3'")
    expect(adjSource).toContain("accountCode: K3_ACCOUNT_CODE")
    expect(adjSource).toContain('ajeTotal')
    expect(adjSource).toContain('rjeTotal')
  })

  it('YAML schema defines CW-K3-006 long-outstanding → K12 cross reference', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const yamlPath = path.resolve(
      __dirname,
      '../../../../../../backend/data/ledger_adapters/wp_render_schema/k3-other-payables.yaml',
    )
    const yamlContent = readFileSync(yamlPath, 'utf-8')

    expect(yamlContent).toContain('CW-K3-006')
    expect(yamlContent).toContain('target_wp: K12')
    expect(yamlContent).toContain('转销')
  })

  it('K3TabLongOutstanding has K12 navigation button (↗K12)', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const loSource = readFileSync(
      path.resolve(__dirname, '../k3/inspection/K3TabLongOutstanding.vue'),
      'utf-8',
    )

    expect(loSource).toContain('navigateToK12')
    expect(loSource).toContain("emit('navigate-sheet', 'K12 营业外收入')")
    expect(loSource).toContain('↗K12')
  })
})

// ═══ Task 6.3: 抽凭引擎 + 行级OCR + GtIndexChip跳转 + 双模式OO ═══

describe('K3 Integration — Task 6.3: 抽凭 + OCR + GtIndexChip + 双模式', () => {
  it('K3TabRelatedParty imports and uses GtVoucherSamplingEngine', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const rpSource = readFileSync(
      path.resolve(__dirname, '../k3/inspection/K3TabRelatedParty.vue'),
      'utf-8',
    )

    // Has GtVoucherSamplingEngine import + dialog
    expect(rpSource).toContain("import GtVoucherSamplingEngine from")
    expect(rpSource).toContain('showSamplingDialog')
    expect(rpSource).toContain('account-code="2241"')
    // Has OCR with /d4/contract-ocr endpoint
    expect(rpSource).toContain("'/api/d4/contract-ocr'")
    expect(rpSource).toContain('handleOcrUpload')
    expect(rpSource).toContain('ElMessageBox.confirm')
    // No more console.log stubs
    expect(rpSource).not.toContain("console.log('[K3-6] Voucher sampling")
    expect(rpSource).not.toContain("console.log('[K3-6] OCR")
  })

  it('K3TabLongOutstanding imports and uses GtVoucherSamplingEngine', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const loSource = readFileSync(
      path.resolve(__dirname, '../k3/inspection/K3TabLongOutstanding.vue'),
      'utf-8',
    )

    expect(loSource).toContain("import GtVoucherSamplingEngine from")
    expect(loSource).toContain('showSamplingDialog')
    expect(loSource).toContain('account-code="2241"')
    expect(loSource).toContain('onSampleFilled')
    // No console.log stub
    expect(loSource).not.toContain("console.log('[K3-5] Voucher sampling")
  })

  it('K3TabLargeAmount has counterparty-link for GtIndexChip navigation', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const laSource = readFileSync(
      path.resolve(__dirname, '../k3/inspection/K3TabLargeAmount.vue'),
      'utf-8',
    )

    expect(laSource).toContain('counterparty-link')
    expect(laSource).toContain('navigateToDetail')
    expect(laSource).toContain("emit('navigate-sheet'")
  })

  it('GtK3OtherPayables has dual mode (el-segmented HTML/OO)', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const mainSource = readFileSync(
      path.resolve(__dirname, '../GtK3OtherPayables.vue'),
      'utf-8',
    )

    expect(mainSource).toContain('el-segmented')
    expect(mainSource).toContain('dualMode.currentMode')
    expect(mainSource).toContain("'html' | 'onlyoffice'")
    expect(mainSource).toContain('GtOnlyOfficeSheet')
    expect(mainSource).toContain('/workpapers/onlyoffice/health')
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Phase 7 Task 7.2: 集成测试 — 负债类回写 + 长期挂账联动 + 账龄勾稽
// Requirements: 2.5, 2.6, 5.4
// ═══════════════════════════════════════════════════════════════════════════════

// ─── 7.2-A: TB writeback flow: writebackTB(amount) → API call + EventBus emit ───

describe('K3 Integration — Task 7.2-A: TB回写流程 (负债口径 2241)', () => {
  let eventBus: { emit: ReturnType<typeof vi.fn>; on: ReturnType<typeof vi.fn>; off: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    eventBus = { emit: vi.fn(), on: vi.fn(), off: vi.fn() }
    vi.doMock('@/utils/eventBus', () => ({ eventBus }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('writebackTB calls PUT /trial-balance/writeback with 2241 + correct amount', async () => {
    const api = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    vi.doMock('@/services/apiProxy', () => ({ api }))

    const { useK3FormData } = await import('../composables/useK3FormData')
    const { ref } = await import('vue')

    const formData = useK3FormData({
      wpId: ref('wp-k3-001'),
      projectId: ref('proj-001'),
      sheetPrefix: 'K3-1',
    })

    await formData.writebackTB(1_500_000)

    expect(api.put).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      { account_code: '2241', audited_amount: 1_500_000 },
    )
  })

  it('writebackTB emits substantive:adjudicated with 2241/K3 payload', async () => {
    const api = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    vi.doMock('@/services/apiProxy', () => ({ api }))

    const { useK3FormData } = await import('../composables/useK3FormData')
    const { ref } = await import('vue')

    const formData = useK3FormData({
      wpId: ref('wp-k3-002'),
      projectId: ref('proj-002'),
      sheetPrefix: 'K3-1',
    })

    await formData.writebackTB(2_000_000)

    expect(eventBus.emit).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        accountCode: '2241',
        auditedAmount: 2_000_000,
        wpCode: 'K3',
      }),
    )
  })

  it('writebackTB updates local tbData.audited2241', async () => {
    const api = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    vi.doMock('@/services/apiProxy', () => ({ api }))

    const { useK3FormData } = await import('../composables/useK3FormData')
    const { ref } = await import('vue')

    const formData = useK3FormData({
      wpId: ref('wp-k3-003'),
      projectId: ref('proj-003'),
      sheetPrefix: 'K3-1',
    })

    expect(formData.tbData.value.audited2241).toBe(0)
    await formData.writebackTB(3_000_000)
    expect(formData.tbData.value.audited2241).toBe(3_000_000)
  })

  it('writebackTB zero amount is valid (全部清偿)', async () => {
    const api = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    vi.doMock('@/services/apiProxy', () => ({ api }))

    const { useK3FormData } = await import('../composables/useK3FormData')
    const { ref } = await import('vue')

    const formData = useK3FormData({
      wpId: ref('wp-k3-004'),
      projectId: ref('proj-004'),
      sheetPrefix: 'K3-1',
    })

    await formData.writebackTB(0)

    expect(api.put).toHaveBeenCalledWith(
      '/api/projects/proj-004/trial-balance/writeback',
      { account_code: '2241', audited_amount: 0 },
    )
    expect(formData.tbData.value.audited2241).toBe(0)
  })
})

// ─── 7.2-B: Long-outstanding → K12 navigation ───────────────────────────────

describe('K3 Integration — Task 7.2-B: 长期挂账 → K12 联动 (Req 5.4)', () => {
  it('K3-5 LongOutstanding has needTransfer=是 triggers K12 navigation emit', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const loSource = readFileSync(
      path.resolve(__dirname, '../k3/inspection/K3TabLongOutstanding.vue'),
      'utf-8',
    )

    // 需转营业外收入字段
    expect(loSource).toContain('needTransfer')
    // 导航到K12的emit事件
    expect(loSource).toContain("emit('navigate-sheet', 'K12 营业外收入')")
    // 函数名
    expect(loSource).toContain('navigateToK12')
  })

  it('K3 CrossSheet composable provides longOutstandingVsDetail computed', async () => {
    const { ref } = await import('vue')
    const { useK3CrossSheet } = await import('../composables/useK3CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K3-2-aging-over3y-count', { remark: '5' }],
      ['K3-2-aging-over3y-total', { remark: '750000' }],
    ]))

    const crossSheet = useK3CrossSheet(allResponses)

    expect(crossSheet.longOutstandingVsDetail.value.count).toBe(5)
    expect(crossSheet.longOutstandingVsDetail.value.total).toBe(750000)
  })

  it('K3 CrossSheet: zero 3-year-old items → count=0, total=0', async () => {
    const { ref } = await import('vue')
    const { useK3CrossSheet } = await import('../composables/useK3CrossSheet')

    const allResponses = ref(new Map<string, any>())

    const crossSheet = useK3CrossSheet(allResponses)

    expect(crossSheet.longOutstandingVsDetail.value.count).toBe(0)
    expect(crossSheet.longOutstandingVsDetail.value.total).toBe(0)
  })
})

// ─── 7.2-C: 账龄勾稽 — K3-2 detail aging total vs endBalance ────────────────

describe('K3 Integration — Task 7.2-C: 账龄勾稽 (Req 2.5)', () => {
  it('K3 CrossSheet adjudicationVsDetail: matched case (diff=0)', async () => {
    const { ref } = await import('vue')
    const { useK3CrossSheet } = await import('../composables/useK3CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { remark: '1000000' }],
      ['K3-2-detail-total', { remark: '1000000' }],
    ]))

    const crossSheet = useK3CrossSheet(allResponses)

    expect(crossSheet.adjudicationVsDetail.value.diff).toBe(0)
    expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('K3 CrossSheet adjudicationVsDetail: mismatched case (diff≠0)', async () => {
    const { ref } = await import('vue')
    const { useK3CrossSheet } = await import('../composables/useK3CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { remark: '1050000' }],
      ['K3-2-detail-total', { remark: '1000000' }],
    ]))

    const crossSheet = useK3CrossSheet(allResponses)

    expect(crossSheet.adjudicationVsDetail.value.diff).toBe(50000)
    expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(false)
  })

  it('K3 CrossSheet adjudicationVsDetail: both zero → match', async () => {
    const { ref } = await import('vue')
    const { useK3CrossSheet } = await import('../composables/useK3CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { remark: '0' }],
      ['K3-2-detail-total', { remark: '0' }],
    ]))

    const crossSheet = useK3CrossSheet(allResponses)

    expect(crossSheet.adjudicationVsDetail.value.diff).toBe(0)
    expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('K3 CrossSheet adjudicationVsDetail: null/missing values → 0 (defensive)', async () => {
    const { ref } = await import('vue')
    const { useK3CrossSheet } = await import('../composables/useK3CrossSheet')

    // Only K3-1 has data, K3-2 missing → diff = value - 0
    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { remark: '500000' }],
    ]))

    const crossSheet = useK3CrossSheet(allResponses)

    expect(crossSheet.adjudicationVsDetail.value.diff).toBe(500000)
    expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(false)
  })

  it('K3 CrossSheet adjudicationVsDetail: 分以内差异视为一致 (0.005)', async () => {
    const { ref } = await import('vue')
    const { useK3CrossSheet } = await import('../composables/useK3CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { remark: '1000000.005' }],
      ['K3-2-detail-total', { remark: '1000000' }],
    ]))

    const crossSheet = useK3CrossSheet(allResponses)

    // diff=0.005 < 0.01 threshold → isMatch=true
    expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('K3 Detail aging integration: K3TabDetail has aging-total vs endBalance reconciliation', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const detailSource = readFileSync(
      path.resolve(__dirname, '../k3/core/K3TabDetail.vue'),
      'utf-8',
    )

    // 账龄合计与期末勾稽 (Req 3.2)
    expect(detailSource).toContain('agingTotal')
    expect(detailSource).toContain('aging')
    // 3年以上标记 (Req 3.5)
    expect(detailSource).toContain('3年以上')
  })
})
