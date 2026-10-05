import { beforeEach, describe, expect, it, vi } from 'vitest'

const { httpMock } = vi.hoisted(() => ({
  httpMock: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/utils/http', () => ({ default: httpMock }))

import {
  importG7Linkage,
  loadAllWorksheetData,
  loadPriorYearWorksheetData,
  loadWorksheetData,
  previewG7Linkage,
  saveWorksheetData,
} from '../consolWorksheetDataApi'

const projectId = 'project-7'
const year = 2025

beforeEach(() => {
  httpMock.get.mockReset()
  httpMock.put.mockReset()
  httpMock.post.mockReset()
})

describe('consolWorksheetData API 契约', () => {
  it('区分单表 loaded、empty 和响应解析失败', async () => {
    httpMock.get
      .mockResolvedValueOnce({ data: { content: { rows: [{ company_code: 'A' }] } } })
      .mockResolvedValueOnce({ data: { content: {} } })
      .mockResolvedValueOnce({ data: { content: [] } })

    await expect(loadWorksheetData(projectId, year, 'info')).resolves.toEqual({
      status: 'loaded',
      data: { rows: [{ company_code: 'A' }] },
    })
    await expect(loadWorksheetData(projectId, year, 'cost')).resolves.toEqual({
      status: 'empty',
      data: {},
    })
    await expect(loadWorksheetData(projectId, year, 'net_asset')).resolves.toEqual({
      status: 'error',
      data: {},
      errorMessage: '工作底稿响应格式无法识别',
    })
    expect(httpMock.get).toHaveBeenNthCalledWith(
      1,
      '/api/consol-worksheet-data/project-7/2025/info',
    )
  })

  it('批量响应支持数组和统一信封，空内容仍保持 empty', async () => {
    httpMock.get
      .mockResolvedValueOnce({
        data: [{ sheet_key: 'info', content: { rows: [{ company_code: 'A' }] } }],
      })
      .mockResolvedValueOnce({
        data: { content: [{ sheet_key: 'cost', content: {} }] },
      })
      .mockResolvedValueOnce({
        data: [{ sheet_key: 'broken', content: [] }],
      })

    await expect(loadAllWorksheetData(projectId, year)).resolves.toEqual({
      status: 'loaded',
      data: { info: { rows: [{ company_code: 'A' }] } },
    })
    await expect(loadAllWorksheetData(projectId, year)).resolves.toEqual({
      status: 'empty',
      data: { cost: {} },
    })
    await expect(loadAllWorksheetData(projectId, year)).resolves.toEqual({
      status: 'error',
      data: {},
      errorMessage: '工作底稿批量响应包含无法解析的表数据',
    })
  })

  it('把 HTTP/网络失败保留为 error，不伪装成空表', async () => {
    httpMock.get
      .mockRejectedValueOnce({ response: { data: { detail: '没有工作底稿权限' } } })
      .mockRejectedValueOnce(new Error('网络断开'))

    await expect(loadWorksheetData(projectId, year, 'info')).resolves.toEqual({
      status: 'error',
      data: {},
      errorMessage: '没有工作底稿权限',
    })
    await expect(loadAllWorksheetData(projectId, year)).resolves.toEqual({
      status: 'error',
      data: {},
      errorMessage: '网络断开',
    })
  })
  it('保存使用 PUT、父页年度和稳定请求体', async () => {
    httpMock.put.mockResolvedValueOnce({ status: 200, data: { ok: true } })

    await expect(saveWorksheetData(projectId, year, 'info', { rows: [{ company_code: 'A' }] })).resolves.toBe(true)

    expect(httpMock.put).toHaveBeenCalledWith(
      '/api/consol-worksheet-data/project-7/2025/info',
      { sheet_key: 'info', data: { rows: [{ company_code: 'A' }] } },
    )
  })

  it('G7 预览和导入都使用父页年度，导入载荷原样传递', async () => {
    const preview = { sources_used: [], unresolved_companies: [], available_companies: [], counts: {}, targets: {}, importable: {} }
    const importPayload = {
      company_mappings: { 甲公司: 'A' },
      sheet_keys: ['info', 'net_asset'],
      overwrite: false,
      expected_versions: { info: 'v1' },
      selected_diffs: [{ sheet_key: 'info', identity: 'A', field: 'company_name' }],
      apply_suggestion_ids: ['suggestion-1'],
    }
    httpMock.get.mockResolvedValueOnce({ data: preview })
    httpMock.post.mockResolvedValueOnce({ data: { imported: { info: 1 }, unresolved_companies: [] } })

    await expect(previewG7Linkage(projectId, year)).resolves.toEqual(preview)
    await expect(importG7Linkage(projectId, year, importPayload)).resolves.toEqual({
      imported: { info: 1 },
      unresolved_companies: [],
    })

    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/consol-worksheet-data/g7-linkage/project-7/2025/preview',
    )
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/consol-worksheet-data/g7-linkage/project-7/2025/import',
      importPayload,
    )
  })

  it('上年提取使用传入年度和表键，并保留 found/content 契约', async () => {
    httpMock.get.mockResolvedValueOnce({
      data: {
        found: true,
        source_year: 2024,
        source_key: 'info_closing',
        content: { rows: [{ company_code: 'A' }] },
      },
    })

    await expect(loadPriorYearWorksheetData(projectId, year, 'info_opening')).resolves.toEqual({
      found: true,
      source_year: 2024,
      source_key: 'info_closing',
      content: { rows: [{ company_code: 'A' }] },
    })
    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/consol-worksheet-data/project-7/2025/prior-year/info_opening',
    )
  })

  it('上年提取响应无法解析时抛出明确错误', async () => {
    httpMock.get.mockResolvedValueOnce({ data: { found: true, content: [] } })

    await expect(loadPriorYearWorksheetData(projectId, year, 'info_opening'))
      .rejects.toThrow('上年工作底稿响应格式无法识别')
  })
  it('保存遇到非 2xx 响应会抛出错误', async () => {
    httpMock.put.mockResolvedValueOnce({ status: 409, data: { detail: '版本冲突' } })

    await expect(saveWorksheetData(projectId, year, 'info', { rows: [] }))
      .rejects.toThrow('工作底稿保存失败（HTTP 409）')
  })
})
