/**
 * 底稿生命周期「一键生成底稿+附注」的审计年度（spec post-push-residual-defect-closure 6.5.4）。
 *
 * 原先直接拿项目 store 的年度执行链路：store 初值去年 ⇒ 没填审计年度的项目会按去年生成。
 * 现在：store 年度为空 ⇒ 提示后不执行；有年度 ⇒ 按该年度执行并刷新列表。
 */
import { beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ElMessage } from 'element-plus'
import http from '@/utils/http'

const { executeFullChain } = vi.hoisted(() => ({ executeFullChain: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('@/composables/useChainExecution', async () => {
  const { ref } = await import('vue')
  return { useChainExecution: () => ({ executing: ref(false), executeFullChain, cleanup: vi.fn() }) }
})

import WorkpaperLifecycleView from '../WorkpaperLifecycleView.vue'
import { useProjectStore } from '@/stores/project'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

let warn: MockInstance<typeof ElMessage.warning>

beforeEach(() => {
  vi.restoreAllMocks()
  setActivePinia(createPinia())
  executeFullChain.mockReset()
  executeFullChain.mockResolvedValue(undefined)
  // 挂载时的三个统计请求：只给空数据，不发真实请求
  vi.spyOn(http, 'get').mockResolvedValue({ data: {} } as any)
  vi.spyOn(http, 'post').mockResolvedValue({ data: {} } as any)
  warn = vi.spyOn(ElMessage, 'warning').mockImplementation((() => ({ close: () => {} })) as any)
})

async function mountView() {
  const w = mount(WorkpaperLifecycleView, {
    props: { projectId: 'p1', workpapers: [{ id: 'wp1', status: 'draft' }], loading: false },
    global: { plugins: [ElementPlus], stubs: { WorkpaperModuleHandbookDialog: true } },
  })
  await flushPromises()
  return w
}

describe('一键生成底稿+附注的年度', () => {
  it('项目没填审计年度：提示后不执行、不刷新列表', async () => {
    const w = await mountView()
    expect(useProjectStore().year).toBeNull()
    await (w.vm as any).onGenerateChain()
    expect(executeFullChain).not.toHaveBeenCalled()
    expect(warn).toHaveBeenCalledWith(`${MISSING_AUDIT_YEAR_MESSAGE}（本次未生成）`)
    expect(w.emitted('refresh')).toBeUndefined()
  })

  it('有审计年度：按项目年度执行，执行后刷新列表', async () => {
    const w = await mountView()
    useProjectStore().year = 2025
    await (w.vm as any).onGenerateChain()
    expect(executeFullChain).toHaveBeenCalledTimes(1)
    expect(executeFullChain).toHaveBeenCalledWith(2025, undefined, true)
    expect(warn).not.toHaveBeenCalled()
    expect(w.emitted('refresh')).toHaveLength(1)
  })
})
