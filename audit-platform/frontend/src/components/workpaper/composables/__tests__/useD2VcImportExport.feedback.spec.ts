/**
 * D2-7 凭证检查表导入导出：调用方错误提示
 *
 * **Validates: Requirements R4.1**
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import type { VoucherCheckRow } from '../useD2VoucherCheckEnhanced'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: { post: mocks.post },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: mocks.success,
    error: mocks.error,
    info: mocks.info,
  },
}))

import http from '@/utils/http'
import {
  COLUMN_HEADERS,
  SHEET_NAME_CURRENT,
  SHEET_NAME_POST,
  useD2VcImportExport,
} from '../useD2VcImportExport'

const mockPost = http.post as ReturnType<typeof vi.fn>

function makeHarness() {
  const currentRows = ref<VoucherCheckRow[]>([])
  const postRows = ref<VoucherCheckRow[]>([])
  const saveToResponses = vi.fn()
  return {
    ...useD2VcImportExport({
      wpId: ref('wp-1'),
      currentRows,
      postRows,
      saveToResponses,
    }),
    currentRows,
    postRows,
    saveToResponses,
  }
}

function sheetRow(voucherNo: string): (string | number | null)[] {
  const row: (string | number | null)[] = Array(17).fill(null)
  row[0] = '测试客户'
  row[1] = '2025-12-31'
  row[2] = voucherNo
  row[6] = 100
  return row
}

function importReply() {
  return {
    data: {
      sheets: {
        [SHEET_NAME_CURRENT]: [COLUMN_HEADERS, sheetRow('PZ-CURRENT')],
        [SHEET_NAME_POST]: [COLUMN_HEADERS, sheetRow('PZ-POST')],
      },
    },
  }
}

beforeEach(() => {
  mockPost.mockReset()
  mocks.success.mockReset()
  mocks.error.mockReset()
  mocks.info.mockReset()
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:d2-vc-test'),
    revokeObjectURL: vi.fn(),
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('useD2VcImportExport 的调用方错误提示', () => {
  it('导出模板成功时以静默配置发请求且保持下载成功提示', async () => {
    mockPost.mockResolvedValueOnce({ data: new Blob(['template']) })
    const harness = makeHarness()

    await harness.exportTemplate()

    expect(mockPost).toHaveBeenCalledWith(
      '/api/workpapers/wp-1/d2/vc-export-template',
      null,
      expect.objectContaining({ responseType: 'blob', _silent: true }),
    )
    expect(mocks.success).toHaveBeenCalledWith('凭证检查表模板已导出')
    expect(mocks.error).not.toHaveBeenCalled()
  })


  it('导出数据成功时以静默配置保留当前双区数据', async () => {
    mockPost.mockResolvedValueOnce({ data: new Blob(['data']) })
    const harness = makeHarness()
    harness.currentRows.value = [{
      rowId: 'row-1', seq: 1, customerName: '客户', voucherDate: '', voucherNo: 'PZ-1',
      businessContent: '', counterpartAccount: '', counterpartDetail: '', debitAmount: 1, creditAmount: 0,
      supportingDoc: '', check1: '', check2: '', check3: '', check4: '', check5: '', indexRef: '',
      isAbnormal: '', remark: '', attachments: [],
    }]

    await harness.exportData()

    const [, body, config] = mockPost.mock.calls[0]
    expect(body.currentRows).toEqual([COLUMN_HEADERS, expect.any(Array)])
    expect(body.postRows).toEqual([COLUMN_HEADERS])
    expect(config).toMatchObject({ responseType: 'blob', _silent: true })
    expect(mocks.success).toHaveBeenCalledWith('凭证检查表数据已导出')
    expect(mocks.error).not.toHaveBeenCalled()
  })

  it('导入成功时以静默配置合并双区数据并保存', async () => {
    mockPost.mockResolvedValueOnce(importReply())
    const harness = makeHarness()

    const result = await harness.importData(new File(['xlsx'], '凭证检查表.xlsx'))

    expect(result).toMatchObject({ currentImported: 1, postImported: 1, skippedSheets: [] })
    expect(harness.currentRows.value[0].voucherNo).toBe('PZ-CURRENT')
    expect(harness.postRows.value[0].voucherNo).toBe('PZ-POST')
    expect(harness.saveToResponses).toHaveBeenCalledTimes(1)
    expect(mockPost.mock.calls[0][2]).toMatchObject({
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    })
    expect(mocks.success).toHaveBeenCalledWith('成功导入 2 行数据')
    expect(mocks.error).not.toHaveBeenCalled()
  })


  it.each([
    {
      title: '模板导出读取 detail',
      reason: '当前底稿不存在',
      failure: { response: { status: 404, data: { detail: '当前底稿不存在' } } },
      invoke: (harness: ReturnType<typeof makeHarness>) => harness.exportTemplate(),
    },
    {
      title: '数据导出读取 blob message',
      reason: '导出数据超出行数限制',
      failure: {
        response: {
          status: 422,
          data: new Blob([JSON.stringify({ message: '导出数据超出行数限制' })], { type: 'application/json' }),
        },
      },
      invoke: (harness: ReturnType<typeof makeHarness>) => harness.exportData(),
    },
    {
      title: '导入读取嵌套 detail message',
      reason: '文件无法解析',
      failure: { response: { status: 400, data: { detail: { message: '文件无法解析' } } } },
      invoke: (harness: ReturnType<typeof makeHarness>) => harness.importData(new File(['bad'], '错误.xlsx')),
    },
  ])('$title 时只显示一次后端中文原因', async ({ reason, failure, invoke }) => {
    mockPost.mockRejectedValueOnce(failure)
    const harness = makeHarness()

    await invoke(harness)

    expect(mocks.error).toHaveBeenCalledTimes(1)
    expect(mocks.error).toHaveBeenCalledWith(reason)
    expect(harness.lastError.value).toBe(reason)
    expect(mockPost.mock.calls[0][2]).toMatchObject({ _silent: true })
  })


  it.each([
    {
      title: '导出模板',
      fallback: '导出模板失败，请检查网络后重试',
      invoke: (harness: ReturnType<typeof makeHarness>) => harness.exportTemplate(),
    },
    {
      title: '导出数据',
      fallback: '导出数据失败，请检查网络后重试',
      invoke: (harness: ReturnType<typeof makeHarness>) => harness.exportData(),
    },
    {
      title: '导入',
      fallback: '导入失败，请检查网络后重试',
      invoke: (harness: ReturnType<typeof makeHarness>) => harness.importData(new File(['offline'], '离线.xlsx')),
    },
  ])('$title 无服务端响应时不泄露 Axios 英文错误', async ({ fallback, invoke }) => {
    mockPost.mockRejectedValueOnce(new Error('Network Error'))
    const harness = makeHarness()

    await invoke(harness)

    expect(mocks.error).toHaveBeenCalledTimes(1)
    expect(mocks.error).toHaveBeenCalledWith(fallback)
    expect(harness.lastError.value).toBe(fallback)
    expect(mocks.error).not.toHaveBeenCalledWith('Network Error')
  })
})
