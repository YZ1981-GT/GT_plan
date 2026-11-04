/**
 * 报告正文网页预览：OnlyOffice 转出的 PDF + 缺字体提示 + 失败原因（taxAssuranceApi）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
vi.mock('@/utils/http', () => ({ default: { get: (...a: unknown[]) => get(...a) }, downloadFile: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), put: vi.fn() } }))

import { fetchReportBodyPreview, previewErrorReason } from '../taxAssuranceApi'

const enc = (s: string) => new TextEncoder().encode(s).buffer

describe('fetchReportBodyPreview', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('请求 preview.pdf，静默、不去重，按 arraybuffer 取', async () => {
    const pdf = enc('%PDF-1.7')
    get.mockResolvedValueOnce({ data: pdf, headers: { 'x-preview-missing-fonts': '' } })
    const res = await fetchReportBodyPreview('p1', 2025)
    expect(get).toHaveBeenCalledWith('/api/projects/p1/tax-assurance/report-body/preview.pdf', expect.objectContaining({
      params: { year: 2025 }, responseType: 'arraybuffer', _silent: true, _dedupe: false,
    }))
    expect(res.pdf).toBe(pdf)
    expect(res.missingFonts).toEqual([])
  })

  it('缺字体响应头按 URL 编码、逗号分隔解出中文名', async () => {
    const header = ['仿宋', '黑体', 'Arial Narrow'].map(encodeURIComponent).join(',')
    get.mockResolvedValueOnce({ data: enc('%PDF'), headers: { 'x-preview-missing-fonts': header } })
    expect((await fetchReportBodyPreview('p1', 2025)).missingFonts).toEqual(['仿宋', '黑体', 'Arial Narrow'])
  })

  it('没有响应头视为字体齐全', async () => {
    get.mockResolvedValueOnce({ data: enc('%PDF'), headers: {} })
    expect((await fetchReportBodyPreview('p1', 2025)).missingFonts).toEqual([])
  })
})

describe('previewErrorReason', () => {
  it('从 arraybuffer 响应体读后端 message', () => {
    const err = { response: { status: 503, data: enc(JSON.stringify({ code: 503, message: 'OnlyOffice 文档服务不可用' })) } }
    expect(previewErrorReason(err)).toBe('OnlyOffice 文档服务不可用')
  })

  it('响应体不是 JSON / 没有响应时返回空串', () => {
    expect(previewErrorReason({ response: { data: enc('<html>') } })).toBe('')
    expect(previewErrorReason(new Error('Network Error'))).toBe('')
    expect(previewErrorReason(undefined)).toBe('')
  })
})
