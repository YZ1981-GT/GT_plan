/**
 * useD7FormData 保存走真实存在的端点（spec voucher-identity-writeback-and-audit-phase 任务 14 发现）。
 *
 * 后端 checklist-responses 只有 GET / PUT 两个路由（`backend/app/routers/checklist_responses.py`），没有按 item 的
 * `PUT /checklist-responses/{item_id}`。D7 原来的即时保存 / 防抖保存打的就是这个不存在的路由 ⇒ 恒 404、提示「保存失败」，
 * D7 各表（含凭证检查表的抽凭 / 挂凭回填行）都存不进去。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { effectScope, ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() } }))

import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useD7FormData } from '../useD7FormData'

const put = vi.mocked(http.put)

beforeEach(() => {
  vi.useRealTimers()
  put.mockReset()
  put.mockResolvedValue({ data: [] } as never)
  vi.mocked(ElMessage.error).mockReset()
})

function mk() {
  const scope = effectScope()
  const api = scope.run(() => useD7FormData({ wpId: ref('wp-7'), projectId: ref('p-7') }))!
  return { api, scope }
}

describe('useD7FormData 保存', () => {
  it('saveImmediate：PUT /checklist-responses（批量端点）带一条 items，不拼 item 路径', async () => {
    const { api, scope } = mk()
    await api.saveImmediate('D7-7-period-rows', { remark: '[{"rowId":"r1"}]' })
    expect(put).toHaveBeenCalledTimes(1)
    const [url, body] = put.mock.calls[0]
    expect(url).toBe('/api/workpapers/wp-7/checklist-responses')
    expect(body).toEqual({ project_id: 'p-7', items: [{ item_id: 'D7-7-period-rows', conclusion: null, remark: '[{"rowId":"r1"}]' }] })
    expect(ElMessage.error).not.toHaveBeenCalled()
    scope.stop()
  })

  it('debouncedSave：2 秒后同样走批量端点', async () => {
    vi.useFakeTimers()
    const { api, scope } = mk()
    api.debouncedSave('D7-7-sampling-params', { remark: '{"sampleSize":3}' })
    expect(put).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000)
    expect(put).toHaveBeenCalledTimes(1)
    expect(put.mock.calls[0][0]).toBe('/api/workpapers/wp-7/checklist-responses')
    expect((put.mock.calls[0][1] as { items: unknown[] }).items).toEqual([
      { item_id: 'D7-7-sampling-params', conclusion: null, remark: '{"sampleSize":3}' }])
    scope.stop()
  })
})

describe('全前端不调用不存在的按 item 保存路由', () => {
  const SRC = resolve(__dirname, '../../../..')
  function walk(dir: string, out: string[] = []): string[] {
    for (const name of readdirSync(dir)) {
      if (name === 'node_modules' || name === '__tests__') continue
      const p = join(dir, name)
      if (statSync(p).isDirectory()) walk(p, out)
      else if (/\.(ts|vue)$/.test(name)) out.push(p)
    }
    return out
  }
  // `checklist-responses/${...}` / `checklist-responses/' + x`：后端没有这类路由，打出去恒 404
  const PER_ITEM = /checklist-responses\/(?:\$\{|['"`]\s*\+)/

  it('判据自检', () => {
    expect(PER_ITEM.test('http.put(`/api/workpapers/${id}/checklist-responses/${itemId}`')).toBe(true)
    expect(PER_ITEM.test("http.put('/api/workpapers/' + id + '/checklist-responses/' + itemId")).toBe(true)
    expect(PER_ITEM.test('http.put(`/api/workpapers/${id}/checklist-responses`, body)')).toBe(false)
  })

  it('源码里没有按 item 拼路径的 checklist-responses 调用', () => {
    expect(SRC.replace(/\\/g, '/')).toMatch(/\/src$/)
    const hits = walk(SRC).filter(p => PER_ITEM.test(readFileSync(p, 'utf-8')))
      .map(p => p.slice(SRC.length + 1).replace(/\\/g, '/'))
    expect(hits).toEqual([])
  })
})
