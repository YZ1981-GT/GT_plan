/**
 * K11 资产减值损失 — 集成测试（composable联动逻辑）
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/ Task 7.2
 * Requirements: 2.5, 4.2, 5.1
 *
 * 测试：
 * 1. 损益取数: Mock render-config API → verify useK11FormData loads tb_values correctly (debit/credit/net occurrence)
 * 2. 源底稿核对联动: Test useK11CrossSheet computed results with mock allResponses data
 * 3. 审定回写: Mock TB writeback API call → verify useK11Adjudication.writeback() sends correct payload (account_code='6701', is_occurrence=true)
 * 4. K11-2 → K11-1 交叉验证: Verify adjudicationVsDetail computed detects mismatches
 * 5. 商誉不可转回: Verify useK11Detail correctly handles goodwill rows (currentReversal forced to 0)
 *
 * Mock: http调用（无后端依赖），eventBus验证
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ─── Mock http / eventBus / ElMessage before imports ─────────────────────────

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { data: [] } }),
    put: vi.fn().mockResolvedValue({ data: { code: 0 } }),
    post: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: 'test' }) },
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    put: vi.fn().mockResolvedValue({ data: { code: 0 } }),
    post: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  },
}))

import { useK11FormData } from '../composables/useK11FormData'
import { useK11CrossSheet } from '../composables/useK11CrossSheet'
import { useK11Adjudication } from '../composables/useK11Adjudication'
import { useK11Detail } from '../composables/useK11Detail'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 损益取数: useK11FormData loads tb_values correctly (Req 5.1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK11FormData — 损益取数(发生额)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('setTbValues正确设置借方/贷方/净发生额', () => {
    const formData = useK11FormData({
      wpId: ref('wp-k11'),
      projectId: ref('proj-1'),
    })

    formData.setTbValues({
      unadjustedDebit: 50000,
      unadjustedCredit: 3000,
    })

    expect(formData.tbData.value.unadjustedDebit).toBe(50000)
    expect(formData.tbData.value.unadjustedCredit).toBe(3000)
    // 净发生额 = 借方 - 贷方 = 50000 - 3000 = 47000
    expect(formData.tbData.value.unadjustedNet).toBe(47000)
  })

  it('selfLoad从render-config seed读取tb_values', async () => {
    // Mock render-config返回带tb_values的seed
    const mockApi = api as any
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('render-config')) {
        return Promise.resolve({
          data: {
            html_data: {
              tb_values: {
                unadjusted_debit: 120000,
                unadjusted_credit: 8000,
                audited_amount: 112000,
              },
            },
          },
        })
      }
      if (url.includes('checklist-responses')) {
        return Promise.resolve({ data: [] })
      }
      if (url.includes('trial-balance')) {
        return Promise.resolve({ data: [] })
      }
      return Promise.resolve({ data: [] })
    })

    const formData = useK11FormData({
      wpId: ref('wp-k11'),
      projectId: ref('proj-1'),
    })

    await formData.selfLoad()

    // 损益类从tb_values读取借方/贷方发生额
    expect(formData.tbData.value.unadjustedDebit).toBe(120000)
    expect(formData.tbData.value.unadjustedCredit).toBe(8000)
    expect(formData.tbData.value.unadjustedNet).toBe(112000) // 120000-8000
    expect(formData.tbData.value.auditedAmount).toBe(112000)
  })

  it('tbData初始值全为0', () => {
    const formData = useK11FormData({
      wpId: ref('wp-k11'),
      projectId: ref('proj-1'),
    })

    expect(formData.tbData.value.unadjustedDebit).toBe(0)
    expect(formData.tbData.value.unadjustedCredit).toBe(0)
    expect(formData.tbData.value.unadjustedNet).toBe(0)
    expect(formData.tbData.value.auditedAmount).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 源底稿核对联动: useK11CrossSheet computed results (Req 4.2)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK11CrossSheet — 源底稿核对联动', () => {
  it('各来源差异为0 → 全部isMatch=true', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K11-2-inventory-occurrence', { remark: '5000' }],
      ['K11-2-inventory-source-amount', { remark: '5000' }],
      ['K11-2-fixed-asset-occurrence', { remark: '3000' }],
      ['K11-2-fixed-asset-source-amount', { remark: '3000' }],
      ['K11-2-intangible-occurrence', { remark: '1000' }],
      ['K11-2-intangible-source-amount', { remark: '1000' }],
      ['K11-2-goodwill-occurrence', { remark: '2000' }],
      ['K11-2-goodwill-source-amount', { remark: '2000' }],
    ]))

    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    const reconcile = cross.sourceReconcile.value
    const inventoryItem = reconcile.find(r => r.category === 'inventory')!
    expect(inventoryItem.diff).toBeCloseTo(0)
    expect(inventoryItem.isMatch).toBe(true)

    const fixedItem = reconcile.find(r => r.category === 'fixed-asset')!
    expect(fixedItem.diff).toBeCloseTo(0)
    expect(fixedItem.isMatch).toBe(true)
  })

  it('来源差异非零 → isMatch=false', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K11-2-inventory-occurrence', { remark: '5000' }],
      ['K11-2-inventory-source-amount', { remark: '4500' }], // 差异500
    ]))

    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    const reconcile = cross.sourceReconcile.value
    const inventoryItem = reconcile.find(r => r.category === 'inventory')!
    expect(inventoryItem.diff).toBeCloseTo(500)
    expect(inventoryItem.isMatch).toBe(false)
  })

  it('allResponses为空 → sourceReconcile全部diff=0', async () => {
    const allResponses = ref(new Map<string, any>())
    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    const reconcile = cross.sourceReconcile.value
    reconcile.forEach((item) => {
      expect(item.diff).toBe(0)
      expect(item.isMatch).toBe(true)
    })
  })

  it('返回所有7个减值来源类别', async () => {
    const allResponses = ref(new Map<string, any>())
    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    const categories = cross.sourceReconcile.value.map(r => r.category)
    expect(categories).toContain('inventory')
    expect(categories).toContain('fixed-asset')
    expect(categories).toContain('intangible')
    expect(categories).toContain('goodwill')
    expect(categories).toContain('construction')
    expect(categories).toContain('equity')
    expect(categories).toContain('other')
    expect(categories.length).toBe(7)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 审定回写: useK11Adjudication.writeback() (Req 5.1, 2.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK11Adjudication — 审定回写(发生额)', () => {
  let allResponses: ReturnType<typeof ref<Map<string, any>>>
  let saveSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    allResponses = ref(new Map())
    saveSpy = vi.fn()
  })

  it('writeback()发送正确payload: account_code=6701, is_occurrence=true', async () => {
    const adj = useK11Adjudication({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    // 设置一行数据使合计非零
    const firstRow = adj.rows.value[0]
    adj.updateCell(firstRow.rowKey, 'currentOccurrence', 10000)
    adj.updateCell(firstRow.rowKey, 'aje', 500)
    await nextTick()

    await adj.writeback()

    // 验证http.put被调用，payload含 account_code='6701' + is_occurrence=true
    const { default: http } = await import('@/utils/http')
    const putCalls = (http.put as any).mock.calls
    expect(putCalls.length).toBeGreaterThan(0)
    const writebackCall = putCalls.find((c: any[]) => c[0]?.includes('writeback'))
    expect(writebackCall).toBeDefined()
    expect(writebackCall[1]).toMatchObject({
      account_code: '6701',
      is_occurrence: true,
    })
  })

  it('writeback()后发布substantive:adjudicated EventBus事件', async () => {
    const adj = useK11Adjudication({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    await adj.writeback()

    expect(eventBus.emit).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        wpCode: 'K11',
        accountCode: '6701',
      }),
    )
  })

  it('writeback()传递正确的审定合计数（损益类发生额）', async () => {
    const adj = useK11Adjudication({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    // 多行设置: row0=10000+500+0=10500, row1=5000+0+200=5200
    const row0 = adj.rows.value[0]
    const row1 = adj.rows.value[1]
    adj.updateCell(row0.rowKey, 'currentOccurrence', 10000)
    adj.updateCell(row0.rowKey, 'aje', 500)
    adj.updateCell(row1.rowKey, 'currentOccurrence', 5000)
    adj.updateCell(row1.rowKey, 'rje', 200)
    await nextTick()

    // 合计审定 = 10500 + 5200 = 15700
    expect(adj.totalRow.value.audited).toBe(15700)

    await adj.writeback()

    const { default: http } = await import('@/utils/http')
    const putCalls = (http.put as any).mock.calls
    const writebackCall = putCalls.find((c: any[]) => c[0]?.includes('writeback'))
    expect(writebackCall[1].audited_amount).toBe(15700)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. K11-2 → K11-1 交叉验证: adjudicationVsDetail (Req 2.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK11CrossSheet — K11-1↔K11-2 交叉验证', () => {
  it('两端一致 → isMatch=true', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K11-1-audited-total', { remark: '15000' }],
      ['K11-2-total-occurrence', { remark: '15000' }],
    ]))
    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
    expect(cross.adjudicationVsDetail.value.diff).toBeCloseTo(0)
  })

  it('两端不一致 → isMatch=false, diff有值', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K11-1-audited-total', { remark: '15000' }],
      ['K11-2-total-occurrence', { remark: '14200' }],
    ]))
    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    expect(cross.adjudicationVsDetail.value.isMatch).toBe(false)
    expect(cross.adjudicationVsDetail.value.diff).toBeCloseTo(800)
  })

  it('allResponses为空 → diff=0, isMatch=true', async () => {
    const allResponses = ref(new Map<string, any>())
    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    expect(cross.adjudicationVsDetail.value.diff).toBe(0)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('微小差异(分以内) → isMatch=true', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K11-1-audited-total', { remark: '10000.005' }],
      ['K11-2-total-occurrence', { remark: '10000' }],
    ]))
    const cross = useK11CrossSheet(allResponses)
    await nextTick()

    // |0.005| < 0.01 → match
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. 商誉不可转回: useK11Detail goodwill handling (Req 4.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK11Detail — 商誉不可转回', () => {
  let allResponses: ReturnType<typeof ref<Map<string, any>>>
  let saveSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    allResponses = ref(new Map())
    saveSpy = vi.fn()
  })

  it('添加商誉行 → isNonReversible=true, currentReversal强制为0', async () => {
    const detail = useK11Detail({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    detail.addRow('商誉减值', '商誉减值准备')
    await nextTick()

    const row = detail.rows.value[0]
    expect(row.isNonReversible).toBe(true)
    expect(row.currentReversal).toBe(0)
    expect(row.sourceWp).toBe('I3')
  })

  it('商誉行尝试设置currentReversal → 被拒绝（保持0）', async () => {
    const detail = useK11Detail({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    detail.addRow('商誉减值损失', '某商誉项')
    await nextTick()

    const rowKey = detail.rows.value[0].rowKey
    detail.updateCell(rowKey, 'currentReversal', 5000) // 尝试设转回
    await nextTick()

    // CAS8: 商誉减值不可转回，应保持0
    expect(detail.rows.value[0].currentReversal).toBe(0)
  })

  it('商誉行发生额 = 本期计提 - 0(不可转回)', async () => {
    const detail = useK11Detail({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    detail.addRow('商誉减值', '')
    const rowKey = detail.rows.value[0].rowKey
    detail.updateCell(rowKey, 'currentProvision', 8000)
    await nextTick()

    // currentOccurrence = 8000 - 0 = 8000
    expect(detail.rows.value[0].currentOccurrence).toBe(8000)
    expect(detail.rows.value[0].currentReversal).toBe(0)
  })

  it('非商誉行可正常转回', async () => {
    const detail = useK11Detail({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    detail.addRow('存货跌价', '原材料跌价')
    const rowKey = detail.rows.value[0].rowKey
    detail.updateCell(rowKey, 'currentProvision', 10000)
    detail.updateCell(rowKey, 'currentReversal', 2000)
    await nextTick()

    expect(detail.rows.value[0].isNonReversible).toBe(false)
    expect(detail.rows.value[0].currentReversal).toBe(2000)
    // currentOccurrence = 10000 - 2000 = 8000
    expect(detail.rows.value[0].currentOccurrence).toBe(8000)
  })

  it('差异非零行高亮检测(varianceRows)', async () => {
    const detail = useK11Detail({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    detail.addRow('固定资产减值', '')
    const rowKey = detail.rows.value[0].rowKey
    detail.updateCell(rowKey, 'currentProvision', 5000)
    // sourceAmount=0 → variance=5000-0=5000 → 非零
    await nextTick()

    expect(detail.varianceRows.value.length).toBe(1)
    expect(detail.varianceRows.value[0].rowKey).toBe(rowKey)
    expect(detail.varianceRows.value[0].variance).toBe(5000)
  })

  it('sourceAmount与occurrence一致时varianceRows为空', async () => {
    const detail = useK11Detail({
      allResponses,
      projectId: ref('proj-1'),
      wpId: ref('wp-k11'),
      onSave: saveSpy,
    })

    detail.addRow('无形资产减值', '')
    const rowKey = detail.rows.value[0].rowKey
    detail.updateCell(rowKey, 'currentProvision', 3000)
    detail.updateCell(rowKey, 'sourceAmount', 3000) // 与发生额一致
    await nextTick()

    expect(detail.varianceRows.value.length).toBe(0)
  })
})
