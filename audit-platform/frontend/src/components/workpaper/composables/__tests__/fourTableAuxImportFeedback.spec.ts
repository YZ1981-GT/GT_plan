/**
 * fourTableAuxImportFeedback 单测（smoke）.
 *
 * spec: .kiro/specs/four-table-extraction-entry-completion/ Task 7
 * Requirements: 4.4（0 行按 reason 码给可辨别提示）/ 5.2（reason 分辨接线错误与真无数据）
 *
 * 注：完整入口连通守卫（按钮存在 + isReadonly 禁用 + 点击真发请求 + reason→文案全分支）
 * 由 Task 8 拥有；此处只锁 reason→文案映射与响应解析的核心行为，防口径漂移。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({ default: { post: vi.fn() } }))

import http from '@/utils/http'
import {
  parseAuxImportResponse,
  auxImportPrompt,
  AUX_IMPORT_NETWORK_ERROR_PROMPT,
  type AuxImportReason,
} from '../fourTableAuxImportFeedback'
import { manualImportK1DetailFromAux, K1_IMPORT_AUX_URL } from '../useK1DetailAutoSeed'

describe('parseAuxImportResponse — 统一读 ResponseWrapperMiddleware 包装层级', () => {
  it('从 res.data.data 读业务载荷（双层包装）', () => {
    const out = parseAuxImportResponse({
      data: { data: { imported_count: 5, reason: 'ok', selected_aux_type: '客户', total_rows: 12, message: 'm' } },
    })
    expect(out).toEqual({
      importedCount: 5,
      reason: 'ok',
      selectedAuxType: '客户',
      message: 'm',
      totalRows: 12,
    })
  })

  it('从 res.data 读业务载荷（单层包装）', () => {
    const out = parseAuxImportResponse({ data: { imported_count: 2, reason: 'no_rows' } })
    expect(out.importedCount).toBe(2)
    expect(out.reason).toBe('no_rows')
  })

  it('非法 reason 值 → reason 归 undefined（不污染分支）', () => {
    const out = parseAuxImportResponse({ data: { imported_count: 0, reason: 'weird_code' } })
    expect(out.reason).toBeUndefined()
  })

  it('缺 imported_count → 归 0', () => {
    expect(parseAuxImportResponse({ data: {} }).importedCount).toBe(0)
  })
})

describe('auxImportPrompt — reason → 可辨别中文提示（Requirement 4.4）', () => {
  it('imported>0 → success（用 message，缺省给行数）', () => {
    expect(auxImportPrompt({ importedCount: 3, message: '从辅助余额表归集 3 个' })).toEqual({
      level: 'success',
      text: '从辅助余额表归集 3 个',
    })
    expect(auxImportPrompt({ importedCount: 3 })).toEqual({
      level: 'success',
      text: '成功从余额表导入 3 行',
    })
  })

  // 0 行时四类 reason 必须**互不相同**（可辨别性是 Requirement 4.4 的核心）
  const zeroCases: Array<[AuxImportReason, string]> = [
    ['no_prefixes', 'warning'],
    ['no_rows', 'info'],
    ['no_aux_type', 'warning'],
    ['no_active_dataset', 'warning'],
    ['error', 'error'],
  ]
  it.each(zeroCases)('reason=%s → 非空可辨别提示（level=%s）', (reason, level) => {
    const p = auxImportPrompt({ importedCount: 0, reason })
    expect(p.text.length).toBeGreaterThan(0)
    expect(p.level).toBe(level)
  })

  it('四类空结果提示文案两两不同（可辨别）', () => {
    const texts = (['no_prefixes', 'no_aux_type', 'no_active_dataset', 'error'] as AuxImportReason[]).map(
      (r) => auxImportPrompt({ importedCount: 0, reason: r }).text,
    )
    expect(new Set(texts).size).toBe(texts.length)
  })

  it('error 与 no_rows level 不同（Requirement 5.2：分辨接线错误 vs 真无数据）', () => {
    expect(auxImportPrompt({ importedCount: 0, reason: 'error' }).level).toBe('error')
    expect(auxImportPrompt({ importedCount: 0, reason: 'no_rows' }).level).toBe('info')
  })

  it('旧端点无 reason + 0 行 → 用 message 兜底', () => {
    expect(auxImportPrompt({ importedCount: 0, message: '未找到科目1221的辅助余额数据' })).toEqual({
      level: 'info',
      text: '未找到科目1221的辅助余额数据',
    })
  })
})

describe('manualImportK1DetailFromAux — 手动入口语义（区别于 AutoSeed）', () => {
  beforeEach(() => vi.mocked(http.post).mockReset())

  it('打字面量正确的 K1 端点 URL', () => {
    expect(K1_IMPORT_AUX_URL('wp-9')).toBe('/api/workpapers/wp-9/k1/import-aux-balance')
  })

  it('无 wpId → 不发请求，返回网络错误提示', async () => {
    const reload = vi.fn()
    const r = await manualImportK1DetailFromAux({ wpId: '', reload })
    expect(http.post).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
    expect(r.ok).toBe(false)
    expect(r.prompt).toEqual(AUX_IMPORT_NETWORK_ERROR_PROMPT)
  })

  it('无论新增几行都 reload（区别于 AutoSeed 的 imported>0 才 reload）', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { data: { imported_count: 0, reason: 'ok' } } })
    const reload = vi.fn().mockResolvedValue(undefined)
    const r = await manualImportK1DetailFromAux({ wpId: 'wp-1', reload })
    expect(http.post).toHaveBeenCalledWith('/api/workpapers/wp-1/k1/import-aux-balance', null)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(r.ok).toBe(true)
  })

  it('新增>0 → success 提示 + reload', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { imported_count: 4, reason: 'ok', message: '新增 4 行' } },
    })
    const reload = vi.fn().mockResolvedValue(undefined)
    const r = await manualImportK1DetailFromAux({ wpId: 'wp-1', reload })
    expect(r.imported).toBe(4)
    expect(r.prompt.level).toBe('success')
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('端点抛错 → ok=false + 错误提示，不抛出、不 reload', async () => {
    // 让 http.post 在被 await 时才 reject（惰性 thenable），避免 vitest 把 mock 建立时
    // 的 rejected promise 记为 test-level 未处理错误。
    vi.mocked(http.post).mockImplementationOnce(
      () => ({ then: (_: any, onRej: any) => onRej(new Error('network down')) }) as any,
    )
    const reload = vi.fn()
    let threw = false
    let r: Awaited<ReturnType<typeof manualImportK1DetailFromAux>> | undefined
    try {
      r = await manualImportK1DetailFromAux({ wpId: 'wp-1', reload })
    } catch {
      threw = true
    }
    expect(threw).toBe(false)
    expect(r?.ok).toBe(false)
    expect(r?.prompt.level).toBe('error')
    expect(reload).not.toHaveBeenCalled()
  })
})
