/**
 * Unit tests for composable factories
 *
 * Feature: platform-global-hardening
 * Requirements: 6.5, 6.6
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ─── createDualMode ──────────────────────────────────────────────────────────

describe('createDualMode', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Mock localStorage
    const store: Record<string, string> = {}
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => store[key] ?? null)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key, val) => { store[key] = val })
    // Mock fetch for OO health
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ healthy: true }), { status: 200 }),
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('defaults to html mode', async () => {
    const { createDualMode } = await import('../createDualMode')
    const { currentMode, isHtmlMode, isOoMode } = createDualMode()
    expect(currentMode.value).toBe('html')
    expect(isHtmlMode.value).toBe(true)
    expect(isOoMode.value).toBe(false)
  })

  it('allows custom default mode', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ healthy: true }), { status: 200 }),
    )
    const { createDualMode } = await import('../createDualMode')
    const { currentMode } = createDualMode({ defaultMode: 'onlyoffice' })
    expect(currentMode.value).toBe('onlyoffice')
  })

  it('switchMode changes mode when OO available', async () => {
    const { createDualMode } = await import('../createDualMode')
    const result = createDualMode()
    result.isOoAvailable.value = true
    await result.switchMode('onlyoffice')
    expect(result.currentMode.value).toBe('onlyoffice')
    expect(result.isOoMode.value).toBe(true)
  })

  it('switchMode refuses OO when unavailable', async () => {
    const { createDualMode } = await import('../createDualMode')
    const result = createDualMode()
    result.isOoAvailable.value = false
    await result.switchMode('onlyoffice')
    expect(result.currentMode.value).toBe('html')
  })

  it('toggleMode flips between modes', async () => {
    const { createDualMode } = await import('../createDualMode')
    const result = createDualMode()
    result.isOoAvailable.value = true
    await result.toggleMode()
    expect(result.currentMode.value).toBe('onlyoffice')
    await result.toggleMode()
    expect(result.currentMode.value).toBe('html')
  })

  it('persists mode to localStorage', async () => {
    const { createDualMode } = await import('../createDualMode')
    const result = createDualMode({ persistKey: 'test-dual-mode' })
    result.isOoAvailable.value = true
    await result.switchMode('onlyoffice')
    expect(localStorage.setItem).toHaveBeenCalledWith('test-dual-mode', 'onlyoffice')
  })

  it('calls onSwitchToHtml callback', async () => {
    const onSwitch = vi.fn()
    const { createDualMode } = await import('../createDualMode')
    const result = createDualMode({ onSwitchToHtml: onSwitch })
    result.isOoAvailable.value = true
    result.currentMode.value = 'onlyoffice'
    await result.switchMode('html')
    expect(onSwitch).toHaveBeenCalledOnce()
  })

  it('checkOOHealth sets isOoAvailable based on response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ healthy: false }), { status: 200 }),
    )
    const { createDualMode } = await import('../createDualMode')
    const result = createDualMode()
    const healthy = await result.checkOOHealth()
    expect(healthy).toBe(false)
    expect(result.isOoAvailable.value).toBe(false)
  })
})

// ─── createImportExport ──────────────────────────────────────────────────────

describe('createImportExport', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('test-token')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('exportTemplate calls correct endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['xlsx-data']), { status: 200 }),
    )
    // Mock createObjectURL/revokeObjectURL for jsdom
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:test')
    globalThis.URL.revokeObjectURL = vi.fn()

    const { createImportExport } = await import('../createImportExport')
    const wpId = ref('wp-123')
    const ie = createImportExport({ wpId, prefix: 'd2' })

    await ie.exportTemplate('D2-3')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workpapers/wp-123/d2/export-template?sheet=D2-3',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(ie.error.value).toBeNull()
  })

  it('exportData calls correct endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['xlsx-data']), { status: 200 }),
    )
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:test')
    globalThis.URL.revokeObjectURL = vi.fn()

    const { createImportExport } = await import('../createImportExport')
    const wpId = ref('wp-456')
    const ie = createImportExport({ wpId, prefix: 'f1' })

    await ie.exportData('F1-2')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workpapers/wp-456/f1/export-data?sheet=F1-2',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('importData uploads file and returns result', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ data: { imported_count: 15, fieldCount: 4 } }), { status: 200 }),
    )

    const { createImportExport } = await import('../createImportExport')
    const wpId = ref('wp-789')
    const ie = createImportExport({ wpId, prefix: 'k1' })

    const file = new File(['test'], 'data.xlsx', { type: 'application/vnd.ms-excel' })
    const result = await ie.importData('K1-3', file)

    expect(result).toEqual({ rowCount: 15, fieldCount: 4, warning: undefined })
    expect(ie.loading.value).toBe(false)
    expect(ie.error.value).toBeNull()
  })

  it('importData sets error on failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    )

    const { createImportExport } = await import('../createImportExport')
    const wpId = ref('wp-err')
    const ie = createImportExport({ wpId, prefix: 'd3' })

    const file = new File(['test'], 'data.xlsx')
    const result = await ie.importData('D3-2', file)

    expect(result).toBeNull()
    expect(ie.error.value).toBeTruthy()
  })
})

// ─── createDetailTable ───────────────────────────────────────────────────────

describe('createDetailTable', () => {
  it('starts with empty rows', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [
        { key: 'name', label: '名称' },
        { key: 'amount', label: '金额', numeric: true },
      ],
      defaultRow: () => ({ name: '', amount: 0 }),
    })

    expect(table.rows.value).toHaveLength(0)
    expect(table.rowCount.value).toBe(0)
  })

  it('addRow appends new row with defaults', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [
        { key: 'name', label: '名称' },
        { key: 'amount', label: '金额', numeric: true },
      ],
      defaultRow: () => ({ name: '新行', amount: 0 }),
    })

    table.addRow()
    expect(table.rows.value).toHaveLength(1)
    expect(table.rows.value[0]).toEqual({ name: '新行', amount: 0 })
  })

  it('addRow merges initial values', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [
        { key: 'name', label: '名称' },
        { key: 'amount', label: '金额', numeric: true },
      ],
      defaultRow: () => ({ name: '', amount: 0 }),
    })

    table.addRow({ name: '自定义', amount: 1000 })
    expect(table.rows.value[0]).toEqual({ name: '自定义', amount: 1000 })
  })

  it('removeRow removes the correct row', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [{ key: 'id', label: 'ID' }],
      defaultRow: () => ({ id: '' }),
    })

    table.addRow({ id: 'a' })
    table.addRow({ id: 'b' })
    table.addRow({ id: 'c' })
    table.removeRow(1)

    expect(table.rows.value).toHaveLength(2)
    expect(table.rows.value[0]).toEqual({ id: 'a' })
    expect(table.rows.value[1]).toEqual({ id: 'c' })
  })

  it('totals computes sum of numeric fields', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [
        { key: 'name', label: '名称' },
        { key: 'debit', label: '借方', numeric: true },
        { key: 'credit', label: '贷方', numeric: true },
      ],
      defaultRow: () => ({ name: '', debit: 0, credit: 0 }),
    })

    table.setRows([
      { name: 'A', debit: 100, credit: 50 },
      { name: 'B', debit: 200, credit: 75 },
      { name: 'C', debit: 300, credit: 125 },
    ])

    expect(table.totals.value).toEqual({ debit: 600, credit: 250 })
  })

  it('totals includes aging fields', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [
        { key: 'name', label: '名称' },
        { key: 'amount', label: '金额', numeric: true },
        { key: 'aging_0_30', label: '0-30天', aging: true },
        { key: 'aging_31_60', label: '31-60天', aging: true },
      ],
      defaultRow: () => ({ name: '', amount: 0, aging_0_30: 0, aging_31_60: 0 }),
    })

    table.setRows([
      { name: 'X', amount: 100, aging_0_30: 60, aging_31_60: 40 },
      { name: 'Y', amount: 200, aging_0_30: 120, aging_31_60: 80 },
    ])

    expect(table.totals.value.amount).toBe(300)
    expect(table.totals.value.aging_0_30).toBe(180)
    expect(table.totals.value.aging_31_60).toBe(120)
  })

  it('setRows replaces all data', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [{ key: 'val', label: 'V', numeric: true }],
      defaultRow: () => ({ val: 0 }),
    })

    table.addRow({ val: 1 })
    table.addRow({ val: 2 })
    table.setRows([{ val: 10 }, { val: 20 }, { val: 30 }])

    expect(table.rows.value).toHaveLength(3)
    expect(table.totals.value.val).toBe(60)
  })

  it('updateRow modifies specific field', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [
        { key: 'name', label: '名称' },
        { key: 'amount', label: '金额', numeric: true },
      ],
      defaultRow: () => ({ name: '', amount: 0 }),
    })

    table.setRows([{ name: 'row1', amount: 100 }])
    table.updateRow(0, 'amount', 999)

    expect(table.rows.value[0].amount).toBe(999)
    expect(table.totals.value.amount).toBe(999)
  })

  it('insertRow adds row at correct position', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [{ key: 'id', label: 'ID' }],
      defaultRow: () => ({ id: '' }),
    })

    table.addRow({ id: 'a' })
    table.addRow({ id: 'c' })
    table.insertRow(1, { id: 'b' })

    expect(table.rows.value.map((r: any) => r.id)).toEqual(['a', 'b', 'c'])
  })

  it('clearRows empties the table', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [{ key: 'x', label: 'X', numeric: true }],
      defaultRow: () => ({ x: 5 }),
    })

    table.addRow()
    table.addRow()
    table.clearRows()

    expect(table.rows.value).toHaveLength(0)
    expect(table.totals.value.x).toBe(0)
  })

  it('exposes columnDefs from config', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const cols = [
      { key: 'a', label: 'A' },
      { key: 'b', label: 'B', numeric: true },
    ]
    const table = createDetailTable({
      columns: cols,
      defaultRow: () => ({ a: '', b: 0 }),
    })
    expect(table.columnDefs).toEqual(cols)
  })

  it('handles NaN values gracefully in totals', async () => {
    const { createDetailTable } = await import('../createDetailTable')
    const table = createDetailTable({
      columns: [{ key: 'amount', label: '金额', numeric: true }],
      defaultRow: () => ({ amount: 0 as unknown }),
    })

    table.setRows([
      { amount: 100 },
      { amount: 'invalid' as unknown },
      { amount: null as unknown },
      { amount: 200 },
    ])

    expect(table.totals.value.amount).toBe(300)
  })
})

// ─── createCycleFormData ─────────────────────────────────────────────────────

describe('createCycleFormData', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('starts with empty formData and not dirty', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )
    const { createCycleFormData } = await import('../createCycleFormData')
    const wpId = ref('wp-test')
    const fd = createCycleFormData({ wpId, prefix: 'D2-' })

    expect(fd.formData.value.size).toBe(0)
    expect(fd.isDirty.value).toBe(false)
    expect(fd.loading.value).toBe(false)
  })

  it('loadData fetches and filters by prefix', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([
        { item_id: 'D2-adj-conclusion', conclusion: '无差异', remark: '已核对' },
        { item_id: 'D2-ecl-method', conclusion: 'ECL', remark: null },
        { item_id: 'F1-something', conclusion: 'x', remark: 'y' },
      ]), { status: 200 }),
    )

    const { createCycleFormData } = await import('../createCycleFormData')
    const wpId = ref('wp-load')
    const fd = createCycleFormData({ wpId, prefix: 'D2-' })

    await fd.loadData()

    expect(fd.formData.value.size).toBe(2)
    expect(fd.formData.value.has('D2-adj-conclusion')).toBe(true)
    expect(fd.formData.value.has('D2-ecl-method')).toBe(true)
    expect(fd.formData.value.has('F1-something')).toBe(false)
    expect(fd.isDirty.value).toBe(false)
  })

  it('setField marks dirty and schedules save', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )

    const { createCycleFormData } = await import('../createCycleFormData')
    const wpId = ref('wp-set')
    const fd = createCycleFormData({ wpId, prefix: 'D2-', debounceMs: 500 })

    fd.setField('D2-test', 'conclusion', '有异常')

    expect(fd.isDirty.value).toBe(true)
    expect(fd.formData.value.get('D2-test')?.conclusion).toBe('有异常')

    // 尚未触发 save
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('setFieldImmediate saves immediately', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 }),
    )

    const { createCycleFormData } = await import('../createCycleFormData')
    const wpId = ref('wp-immediate')
    const fd = createCycleFormData({ wpId, prefix: 'K8-' })
    fd.isDirty.value = true

    fd.setFieldImmediate('K8-check', 'remark', '复核通过')

    // 等异步操作
    await vi.runAllTimersAsync()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workpapers/wp-immediate/checklist-responses',
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('resetData applies defaultValues with prefix', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )

    const { createCycleFormData } = await import('../createCycleFormData')
    const wpId = ref('wp-reset')
    const fd = createCycleFormData({
      wpId,
      prefix: 'F1-',
      defaultValues: { conclusion: '正常', method: '实质性程序' },
    })

    fd.resetData()

    expect(fd.formData.value.get('F1-conclusion')?.conclusion).toBe('正常')
    expect(fd.formData.value.get('F1-method')?.conclusion).toBe('实质性程序')
    expect(fd.isDirty.value).toBe(true)
  })

  it('validates with custom validateFn', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )

    const { createCycleFormData } = await import('../createCycleFormData')
    const wpId = ref('wp-validate')
    const fd = createCycleFormData({
      wpId,
      prefix: 'D3-',
      validateFn: (data) => {
        const errors: string[] = []
        if (!data.has('D3-conclusion')) errors.push('缺少审计结论')
        return errors
      },
    })

    expect(fd.errors.value).toEqual(['缺少审计结论'])

    fd.setField('D3-conclusion', 'conclusion', '无保留')
    expect(fd.errors.value).toEqual([])
  })
})
