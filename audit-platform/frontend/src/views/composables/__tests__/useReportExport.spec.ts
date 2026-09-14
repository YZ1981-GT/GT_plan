/**
 * useReportExport.spec.ts — composable 单元测试
 *
 * 验证 useReportExport 核心动作：
 * - onExportExcel: 调用 downloadFileAsBlob，URL 通过 getReportExcelUrl 生成
 * - onExportAllExcel: 调用 downloadFileAsBlob，URL 为 export-all 路径
 * - copyReportTable: 有数据时调用 clipboard.write（HTML+text）并显示成功消息
 * - copyReportTable: 空数据时显示 warning
 * - onReportImported: 关闭弹窗 + 调 fetchReport
 *
 * Validates: Requirements 3.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import type { ReportRow } from '@/services/auditPlatformApi'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

const mockGetReportExcelUrl = vi.fn().mockReturnValue('/api/reports/proj-1/2025/balance_sheet/export')
vi.mock('@/services/auditPlatformApi', () => ({
  getReportExcelUrl: (...args: any[]) => mockGetReportExcelUrl(...args),
}))

const mockDownloadFileAsBlob = vi.fn()
vi.mock('@/services/commonApi', () => ({
  downloadFileAsBlob: (...args: any[]) => mockDownloadFileAsBlob(...args),
}))

import { ElMessage } from 'element-plus'
import { useReportExport } from '../useReportExport'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function createOptions(rowsData: ReportRow[] = []) {
  const fetchReport = vi.fn().mockResolvedValue(undefined)
  return {
    projectId: computed(() => 'proj-1'),
    year: computed(() => 2025),
    activeTab: ref('balance_sheet'),
    rows: ref<ReportRow[]>(rowsData),
    activeTabLabel: computed(() => '资产负债表'),
    fetchReport,
  }
}

function makeFakeRows(n = 2): ReportRow[] {
  return Array.from({ length: n }, (_, i) => ({
    row_code: `BS-${String(i + 1).padStart(3, '0')}`,
    row_name: `Row ${i + 1}`,
    current_period_amount: String((i + 1) * 1000),
    prior_period_amount: String((i + 1) * 800),
    formula_used: null,
    source_accounts: null,
    indent_level: 1,
    is_total_row: false,
  }))
}

async function flushPromises() {
  await new Promise(resolve => setTimeout(resolve, 0))
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useReportExport — onExportExcel', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('calls downloadFileAsBlob with correct URL from getReportExcelUrl', async () => {
    const options = createOptions()
    const { onExportExcel } = useReportExport(options)

    onExportExcel()
    await flushPromises()

    expect(mockGetReportExcelUrl).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet')
    expect(mockDownloadFileAsBlob).toHaveBeenCalledWith(
      '/api/reports/proj-1/2025/balance_sheet/export',
      '报表_balance_sheet_2025.xlsx',
    )
  })
})

describe('useReportExport — onExportAllExcel', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('calls downloadFileAsBlob with export-all URL', async () => {
    const options = createOptions()
    const { onExportAllExcel } = useReportExport(options)

    onExportAllExcel()
    await flushPromises()

    expect(mockDownloadFileAsBlob).toHaveBeenCalledWith(
      '/api/reports/proj-1/2025/export',
      '全部报表_2025.xlsx',
    )
  })
})

describe('useReportExport — copyReportTable', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('with rows, calls clipboard.write with HTML+text and shows success message', () => {
    const fakeRows = makeFakeRows(2)
    const options = createOptions(fakeRows)
    const { copyReportTable } = useReportExport(options)

    const mockWrite = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, {
      clipboard: { write: mockWrite, writeText: vi.fn() },
    })
    ;(globalThis as any).ClipboardItem = class {
      constructor(public items: Record<string, Blob>) {}
    }

    copyReportTable()

    expect(mockWrite).toHaveBeenCalledTimes(1)
    const clipboardItem = mockWrite.mock.calls[0][0][0]
    expect(clipboardItem.items).toHaveProperty('text/html')
    expect(clipboardItem.items).toHaveProperty('text/plain')
    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith(
      expect.stringContaining('2 行'),
    )
  })

  it('with empty rows, shows warning', () => {
    const options = createOptions([])
    const { copyReportTable } = useReportExport(options)

    copyReportTable()

    expect(vi.mocked(ElMessage.warning)).toHaveBeenCalledWith('无数据可复制')
  })
})

describe('useReportExport — onReportImported', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('sets showReportImport to false and calls fetchReport', () => {
    const options = createOptions()
    const { showReportImport, onReportImported } = useReportExport(options)

    showReportImport.value = true
    onReportImported()

    expect(showReportImport.value).toBe(false)
    expect(options.fetchReport).toHaveBeenCalledTimes(1)
  })
})
