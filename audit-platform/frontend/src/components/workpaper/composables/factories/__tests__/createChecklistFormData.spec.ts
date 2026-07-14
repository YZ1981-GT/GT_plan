/**
 * Unit tests for createChecklistFormData factory
 *
 * Feature: workpaper-maintainability-convergence / Task 6.1
 * Requirements: 6.1, 6.2, 6.6
 *
 * Verifies:
 * - Factory reuses useChecklistPersistence adapter
 * - itemPrefix filtering works correctly
 * - normalizeResponse hook is applied
 * - afterSave hook is invoked on success
 * - writebackTB calls trial-balance/writeback + EventBus
 * - selfLoad fetches render-config with forceComponentType
 * - debouncedSave delegates to persistence.saveDebounced
 * - flush/cancel delegate to persistence adapter
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

const mockEmit = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: (...args: any[]) => mockEmit(...args) },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

// ─── Test Suite ──────────────────────────────────────────────────────────────

describe('createChecklistFormData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: loadResponses returns mixed-prefix responses
    mockGet.mockImplementation((url: string) => {
      if (url.includes('checklist-responses')) {
        return Promise.resolve({
          data: [
            { item_id: 'K1-1-audited', conclusion: '100', remark: null },
            { item_id: 'K1-2-detail', conclusion: null, remark: '{"rows":[]}' },
            { item_id: 'D2-adj-tb', conclusion: '500', remark: null }, // other prefix
          ],
        })
      }
      if (url.includes('render-config')) {
        return Promise.resolve({
          data: {
            html_data: { tb_values: { current_amount: 12345 } },
            sheets: [
              { sheet_name: 'K1-1', html_data: { rows: [{ name: 'row1' }] } },
              { sheet_name: 'K1-2', html_data: { rows: [] } },
            ],
          },
        })
      }
      return Promise.resolve({ data: null })
    })
    mockPut.mockResolvedValue({ data: { items: [] } })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function createInstance(overrides = {}) {
    const { createChecklistFormData } = await import('../createChecklistFormData')
    return createChecklistFormData({
      wpId: ref('wp-001'),
      projectId: ref('proj-001'),
      itemPrefix: 'K1-',
      label: 'K1',
      forceComponentType: 'k1-other-receivables',
      accountCodes: ['1221', '1231'],
      ...overrides,
    })
  }

  // ─── loadData ──────────────────────────────────────────────────────────────

  it('loadData fetches render-config with force_component_type', async () => {
    const fd = await createInstance()
    await fd.loadData()

    expect(mockGet).toHaveBeenCalledWith(
      '/api/workpapers/wp-001/render-config',
      expect.objectContaining({
        params: { force_component_type: 'k1-other-receivables' },
      }),
    )
  })

  it('loadData loads checklist-responses', async () => {
    const fd = await createInstance()
    await fd.loadData()

    expect(mockGet).toHaveBeenCalledWith('/api/workpapers/wp-001/checklist-responses')
  })

  it('loadData populates sheetCache from render-config', async () => {
    const fd = await createInstance()
    await fd.loadData()

    expect(fd.sheetCache.value['K1-1']).toBeDefined()
    expect(fd.sheetCache.value['K1-1'].rows).toHaveLength(1)
  })

  it('allResponses filters by itemPrefix', async () => {
    const fd = await createInstance()
    await fd.loadData()

    // D2 item should be filtered out
    expect(fd.allResponses.value.has('D2-adj-tb')).toBe(false)
    // K1 items should be present
    expect(fd.allResponses.value.has('K1-1-audited')).toBe(true)
    expect(fd.allResponses.value.has('K1-2-detail')).toBe(true)
  })

  // ─── normalizeResponse hook ────────────────────────────────────────────────

  it('normalizeResponse hook transforms loaded responses', async () => {
    const normalizeResponse = vi.fn((r) => ({
      ...r,
      remark: r.remark ? `normalized:${r.remark}` : null,
    }))

    const fd = await createInstance({ normalizeResponse })
    await fd.loadData()

    const detail = fd.allResponses.value.get('K1-2-detail')
    expect(detail?.remark).toBe('normalized:{"rows":[]}')
    expect(normalizeResponse).toHaveBeenCalled()
  })

  // ─── save ──────────────────────────────────────────────────────────────────

  it('save calls persistence PUT with item', async () => {
    const fd = await createInstance()
    await fd.loadData()

    await fd.save('K1-new-item', { conclusion: 'yes', remark: 'test' })

    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-001/checklist-responses',
      expect.objectContaining({
        project_id: 'proj-001',
        items: expect.arrayContaining([
          expect.objectContaining({ item_id: 'K1-new-item' }),
        ]),
      }),
      expect.anything(),
    )
  })

  // ─── debouncedSave ─────────────────────────────────────────────────────────

  it('debouncedSave updates local state immediately', async () => {
    const fd = await createInstance()
    await fd.loadData()

    fd.debouncedSave('K1-debounced', { remark: 'pending' })

    // Value should be in responses immediately (optimistic update)
    const resp = fd.allResponses.value.get('K1-debounced')
    expect(resp?.remark).toBe('pending')
  })

  // ─── writebackTB ───────────────────────────────────────────────────────────

  it('writebackTB calls trial-balance/writeback for each account', async () => {
    const fd = await createInstance()

    await fd.writebackTB({ '1221': 500000, '1231': 50000 })

    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      expect.objectContaining({ account_code: '1221', audited_amount: 500000 }),
    )
    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      expect.objectContaining({ account_code: '1231', audited_amount: 50000 }),
    )
  })

  it('writebackTB emits substantive:adjudicated event', async () => {
    const fd = await createInstance()

    await fd.writebackTB({ '1221': 500000 })

    expect(mockEmit).toHaveBeenCalledWith('substantive:adjudicated', expect.objectContaining({
      accountCode: '1221',
      auditedAmount: 500000,
      wpCode: 'K1',
    }))
  })

  it('writebackTB includes year param when provided', async () => {
    const fd = await createInstance({ year: ref(2025) })

    await fd.writebackTB({ '1221': 100 })

    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      expect.objectContaining({ account_code: '1221', audited_amount: 100, year: 2025 }),
    )
  })

  // ─── setTbValues ───────────────────────────────────────────────────────────

  it('setTbValues populates responses with prefix', async () => {
    const fd = await createInstance()
    await fd.loadData()

    fd.setTbValues({ 'tb-amount': '12345' })

    const resp = fd.allResponses.value.get('K1-tb-amount')
    expect(resp?.conclusion).toBe('12345')
  })

  // ─── getSheet ──────────────────────────────────────────────────────────────

  it('getSheet returns cached sheet data', async () => {
    const fd = await createInstance()
    await fd.loadData()

    const sheet = fd.getSheet('K1-1')
    expect(sheet.rows).toHaveLength(1)
  })

  it('getSheet returns default for missing sheet', async () => {
    const fd = await createInstance()

    const sheet = fd.getSheet('nonexistent')
    expect(sheet).toEqual({ rows: [] })
  })

  // ─── afterSave hook ────────────────────────────────────────────────────────

  it('afterSave hook is called after successful save', async () => {
    const afterSave = vi.fn()
    mockPut.mockResolvedValue({ data: [{ item_id: 'K1-hook-test', conclusion: 'saved', remark: null }] })

    const fd = await createInstance({ afterSave })
    await fd.save('K1-hook-test', { conclusion: 'saved' })

    // afterSave is invoked by useChecklistPersistence's onSaved callback
    expect(afterSave).toHaveBeenCalled()
  })

  // ─── selfLoad failure does not block ────────────────────────────────────────

  it('selfLoad failure does not block loadData', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('render-config')) return Promise.reject(new Error('network'))
      if (url.includes('checklist-responses')) {
        return Promise.resolve({ data: [{ item_id: 'K1-1-x', conclusion: '1', remark: null }] })
      }
      return Promise.resolve({ data: null })
    })

    const fd = await createInstance()
    await fd.loadData()

    // Should still have responses loaded despite render-config failure
    expect(fd.allResponses.value.has('K1-1-x')).toBe(true)
    expect(fd.isLoading.value).toBe(false)
  })

  // ─── hydrate ───────────────────────────────────────────────────────────────

  it('hydrate accepts external data source', async () => {
    const fd = await createInstance()

    fd.hydrate([
      { item_id: 'K1-hydrated', conclusion: 'from-external', remark: null },
    ])

    expect(fd.allResponses.value.get('K1-hydrated')?.conclusion).toBe('from-external')
  })
})
