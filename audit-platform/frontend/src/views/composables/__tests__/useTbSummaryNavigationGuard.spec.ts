import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { settleTbSummaryNavigation } from '../useTbSummaryNavigationGuard'

const HERE = dirname(fileURLToPath(import.meta.url))
const SOURCE = readFileSync(resolve(HERE, '../useTbSummaryNavigationGuard.ts'), 'utf-8')

function state(dirty: boolean, saved: boolean) {
  return {
    dirty: ref(dirty),
    errorMessage: ref('自动保存冲突：数据已被他人修改'),
    flush: vi.fn().mockResolvedValue(saved),
    discard: vi.fn(),
  }
}

describe('settleTbSummaryNavigation', () => {
  it('同时守住路由离开、同组件路由更新和浏览器关闭', () => {
    expect(SOURCE).toContain("onBeforeRouteLeave(() => settle('离开页面'))")
    expect(SOURCE).toContain("onBeforeRouteUpdate(() => settle('切换项目或年度'))")
    expect(SOURCE).toContain("window.addEventListener('beforeunload', beforeUnload)")
    expect(SOURCE).toContain("window.removeEventListener('beforeunload', beforeUnload)")
  })

  it('没有未保存修改时直接放行', async () => {
    const current = state(false, false)
    const confirm = vi.fn()
    expect(await settleTbSummaryNavigation(current, '刷新', confirm)).toBe(true)
    expect(current.flush).not.toHaveBeenCalled()
    expect(confirm).not.toHaveBeenCalled()
  })

  it('队列保存成功后放行，不询问丢弃', async () => {
    const current = state(true, true)
    const confirm = vi.fn()
    expect(await settleTbSummaryNavigation(current, '离开页面', confirm)).toBe(true)
    expect(current.flush).toHaveBeenCalledTimes(1)
    expect(confirm).not.toHaveBeenCalled()
    expect(current.discard).not.toHaveBeenCalled()
  })

  it('保存失败且用户取消时阻止刷新或导航并保留本地修改', async () => {
    const current = state(true, false)
    const confirm = vi.fn().mockResolvedValue(false)
    expect(await settleTbSummaryNavigation(current, '刷新', confirm)).toBe(false)
    expect(confirm).toHaveBeenCalledWith(current.errorMessage.value, '刷新')
    expect(current.discard).not.toHaveBeenCalled()
  })

  it('保存失败仅在用户明确确认后丢弃并放行', async () => {
    const current = state(true, false)
    const confirm = vi.fn().mockResolvedValue(true)
    expect(await settleTbSummaryNavigation(current, '切换项目或年度', confirm)).toBe(true)
    expect(current.discard).toHaveBeenCalledTimes(1)
  })
})
