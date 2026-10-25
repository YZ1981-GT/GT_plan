/**
 * useKnowledge —— 编辑器「📚 知识库」选择器的数据源
 *
 * 回归背景（spec knowledge-upload-robustness-and-consumer-wiring R6.1，2026-09-30 Playwright 实测）：
 * 旧实现调 `/api/knowledge/search`，后端从未有过这条路由 —— 404 被 catch 吞成空列表，
 * 附注 / 审计报告编辑器的选择器恒显示「未找到匹配的文档」。
 * 本文件断言**请求打到哪条 URL、带什么参数**（只断言返回值的旧测试形态抓不到这类缺陷）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

import { useKnowledge, knowledgePickerVisible, knowledgePickerOptions, _resolvePickerSelection, _rejectPickerSelection } from '../useKnowledge'
import { knowledgeLibrary } from '@/services/apiPaths'

// 🔴 hook 体必须用花括号：`beforeEach(() => mockGet.mockReset())` 会把 spy 本身返回给 vitest，
// 而 vitest 把 beforeEach 返回的函数当作「用例结束后的清理钩子」调用 ⇒ 每条用例结束时 mockGet
// 被多调一次；在 mockRejectedValue 的用例里这次调用返回被拒绝的 promise，用例因此失败，
// 报错形态恰好是注入的那个错误（本文件首跑即踩到，被测代码并无问题）。
describe('useKnowledge.search', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('调用带权限的知识库搜索端点，查询词去首尾空白，上下文只作加分参数', async () => {
    mockGet.mockResolvedValue([{ id: 'd1', name: '治理层沟通函.docx', snippet: '片段', folder_path: '/准则' }])
    const { search, searchResults } = useKnowledge()

    const rows = await search('  治理层  ', 'A10 货币资金')

    expect(mockGet).toHaveBeenCalledTimes(1)
    const [url, config] = mockGet.mock.calls[0]
    expect(url).toBe('/api/knowledge-library/search')
    expect(url).toBe(knowledgeLibrary.search)
    expect(config).toEqual({ params: { q: '治理层', context: 'A10 货币资金' } })
    expect(rows.map((r) => r.id)).toEqual(['d1'])
    expect(searchResults.value).toEqual(rows)
  })

  it('不带上下文时不发送 context 参数', async () => {
    mockGet.mockResolvedValue([])
    await useKnowledge().search('函证')
    expect(mockGet.mock.calls[0][1]).toEqual({ params: { q: '函证' } })
  })

  it('空白查询不发请求', async () => {
    const rows = await useKnowledge().search('   ')
    expect(rows).toEqual([])
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('接口失败返回空列表且复位 searching', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    const k = useKnowledge()
    const rows = await k.search('函证')
    expect(rows).toEqual([])
    expect(k.searching.value).toBe(false)
  })

  it('非数组响应按空列表处理（不把包装体当结果行）', async () => {
    mockGet.mockResolvedValue({ results: [{ id: 'x' }] })
    expect(await useKnowledge().search('函证')).toEqual([])
  })
})

describe('useKnowledge.getDocContent', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('走预览端点，只返回文本类正文', async () => {
    mockGet.mockResolvedValueOnce({ preview_type: 'text', content: '正文' })
    mockGet.mockResolvedValueOnce({ preview_type: 'download', download_url: '/x' })
    const { getDocContent } = useKnowledge()

    expect(await getDocContent('d1')).toBe('正文')
    expect(mockGet.mock.calls[0][0]).toBe(knowledgeLibrary.documentPreview('d1'))
    expect(await getDocContent('d2')).toBe('')
  })

  it('不可读 / 不存在（404）返回空串', async () => {
    mockGet.mockRejectedValue({ response: { status: 404 } })
    expect(await useKnowledge().getDocContent('nope')).toBe('')
  })
})

describe('useKnowledge.pickDocuments', () => {
  it('确认后返回所选文档，取消返回空列表', async () => {
    const { pickDocuments } = useKnowledge()

    const picked = pickDocuments({ title: 'T', maxSelect: 3 })
    expect(knowledgePickerVisible.value).toBe(true)
    expect(knowledgePickerOptions.value).toEqual({ title: 'T', maxSelect: 3 })
    _resolvePickerSelection([{ id: 'a', name: 'A' }])
    expect(await picked).toEqual([{ id: 'a', name: 'A' }])
    expect(knowledgePickerVisible.value).toBe(false)

    const cancelled = pickDocuments()
    _rejectPickerSelection()
    expect(await cancelled).toEqual([])
  })
})
