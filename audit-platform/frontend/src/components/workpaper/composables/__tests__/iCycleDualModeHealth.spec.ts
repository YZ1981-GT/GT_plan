/**
 * I1 / I3~I6 双模式的 OnlyOffice 健康检查走平台统一探针（spec platform-performance-residual-findings-closure）。
 *
 * 原先五个 composable 各自 `http.get('/workpapers/onlyoffice/health')`（少 /api 前缀）：请求落到前端页面、拿到首页
 * HTML ⇒ healthy 恒取不到 ⇒ 在线编辑切换入口从不出现。改为 `sync/onlyOfficeHealth.fetchOnlyOfficeHealthy`
 * （唯一端点 / 字段、TTL 缓存、并发去重）。这里挂载时用假探针分别返回可用 / 不可用，看切换入口状态跟着走。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const health = vi.hoisted(() => ({ fetchOnlyOfficeHealthy: vi.fn() }))
vi.mock('../../sync/onlyOfficeHealth', () => health)
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(() => Promise.reject(new Error('不应直调 http'))) } }))

import { useI1DualMode } from '../useI1DualMode'
import { useI3DualMode } from '../useI3DualMode'
import { useI4DualMode } from '../useI4DualMode'
import { useI5DualMode } from '../useI5DualMode'
import { useI6DualMode } from '../useI6DualMode'

const FACTORIES = { useI1DualMode, useI3DualMode, useI4DualMode, useI5DualMode, useI6DualMode } as const

function host(factory: (o: any) => any) {
  let api: any
  const Comp = defineComponent({
    setup() {
      api = factory({ wpId: ref('wp-1'), sheetName: ref(''), autoSave: vi.fn(), reloadAll: vi.fn() })
      return () => null
    },
  })
  mount(Comp)
  return () => api
}

beforeEach(() => {
  health.fetchOnlyOfficeHealthy.mockReset()
  localStorage.clear()
})

describe.each(Object.entries(FACTORIES))('%s', (_name, factory) => {
  it('探针可用 ⇒ 出现在线编辑切换', async () => {
    health.fetchOnlyOfficeHealthy.mockResolvedValue(true)
    const api = host(factory)
    await flushPromises()
    expect(health.fetchOnlyOfficeHealthy).toHaveBeenCalledTimes(1)
    expect(api().isOoAvailable.value).toBe(true)
    expect(api().checking.value).toBe(false)
  })

  it('探针不可用 ⇒ 只给结构化视图', async () => {
    health.fetchOnlyOfficeHealthy.mockResolvedValue(false)
    const api = host(factory)
    await flushPromises()
    expect(api().isOoAvailable.value).toBe(false)
    expect(api().checking.value).toBe(false)
  })
})
