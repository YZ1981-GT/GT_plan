/**
 * publication 管理页的视图层判据（sheet 候选下拉）。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16/20
 *
 * 🔴 为什么必须测 .vue 而不只测 composable：
 * 变异实测显示，只测 composable 时「页面打开时不拉 preflight」「没有 preflight
 * 仍允许提交」「隐藏页也列出」这三条变异全部存活 —— 视图层逻辑完全没被判据覆盖。
 *
 * 判据：
 * 1. 打开实例化弹窗时必须调用 loadPreflightSheets(candidateId)；
 * 2. 没有 preflight 报告时「确认实例化」按钮禁用；
 * 3. 下拉候选只含 visible（隐藏页不列出）；
 * 4. 已被其它行选中的 sheet 不再出现在该行候选里；
 * 5. 选中 sheet 后带出推荐 projectionMode。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const loadPreflightSheets = vi.fn()
const instantiate = vi.fn()
const load = vi.fn()
const commitVisibility = vi.fn()
const acceptAllConsumers = vi.fn()

vi.mock('@/composables/useTemplatePublications', async () => {
  const actual = await vi.importActual<typeof import('@/composables/useTemplatePublications')>(
    '@/composables/useTemplatePublications',
  )
  return {
    ...actual,
    useTemplatePublications: () => ({
      publications: { value: [
        {
          publicationKey: 'pub-1',
          candidateId: 'art-1',
          state: 'ACTIVE',
          artifactDigest: 'a'.repeat(64),
          authorityRef: 'auth-1',
          reason: null,
          runtimeDiscoverable: true,
          createdAt: '2026-11-16T00:00:00+00:00',
          updatedAt: '2026-11-16T00:00:00+00:00',
        },
      ] },
      pending: { value: [] },
      active: { value: [] },
      loading: { value: false },
      lastError: { value: null },
      load,
      commitVisibility,
      acceptAllConsumers,
      loadPreflightSheets,
      instantiate,
    }),
  }
})

import CustomTemplatePublications from '@/views/extension/CustomTemplatePublications.vue'

const SHEETS = [
  { sheetUid: 'sheet-0-a', sheetName: '甲', order: 0, state: 'visible', projectionRecommendation: 'read_only_html' },
  { sheetUid: 'sheet-1-b', sheetName: '乙', order: 1, state: 'visible', projectionRecommendation: 'onlyoffice_only' },
  { sheetUid: 'sheet-2-hidden', sheetName: '隐藏', order: 2, state: 'hidden' },
]

function mountPage() {
  return mount(CustomTemplatePublications, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
}

beforeEach(() => {
  load.mockReset().mockResolvedValue(undefined)
  loadPreflightSheets.mockReset().mockResolvedValue(SHEETS)
  instantiate.mockReset()
  commitVisibility.mockReset()
  acceptAllConsumers.mockReset()
})

describe('实例化弹窗的 sheet 候选', () => {
  it('🔴 打开弹窗时按 candidateId 拉 preflight 候选', async () => {
    const w = mountPage()
    await flushPromises()

    const instantiateBtn = w.find('[data-testid="instantiate-pub-1"]')
    expect(instantiateBtn.exists()).toBe(true)
    await instantiateBtn.trigger('click')
    await flushPromises()

    expect(loadPreflightSheets).toHaveBeenCalledTimes(1)
    // candidateId 就是 artifactId
    expect(loadPreflightSheets).toHaveBeenCalledWith('art-1')
    w.unmount()
  })

  it('🔴 没有 preflight 报告时「确认实例化」禁用', async () => {
    loadPreflightSheets.mockResolvedValueOnce([])
    const w = mountPage()
    await flushPromises()
    await w.find('[data-testid="instantiate-pub-1"]').trigger('click')
    await flushPromises()

    const submit = w.find('[data-testid="instantiate-submit"]')
    expect(submit.exists()).toBe(true)
    expect(submit.attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('有 preflight 报告时「确认实例化」可用', async () => {
    const w = mountPage()
    await flushPromises()
    await w.find('[data-testid="instantiate-pub-1"]').trigger('click')
    await flushPromises()

    const submit = w.find('[data-testid="instantiate-submit"]')
    expect(submit.attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  it('🔴 隐藏页不出现在候选里', async () => {
    const w = mountPage()
    await flushPromises()
    await w.find('[data-testid="instantiate-pub-1"]').trigger('click')
    await flushPromises()

    // 视图把 selectableSheets 传给 el-select 的 options；直接断言组件数据
    const vm = w.vm as unknown as { selectableSheets: { sheetUid: string }[] }
    expect(vm.selectableSheets.map((s) => s.sheetUid)).toEqual(['sheet-0-a', 'sheet-1-b'])
    expect(vm.selectableSheets.map((s) => s.sheetUid)).not.toContain('sheet-2-hidden')
    w.unmount()
  })
})
