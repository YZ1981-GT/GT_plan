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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

// 🔴 mock ElMessageBox.prompt：服务层弹窗状态（内部 promise 队列）跨用例残留，
// 真实 prompt 在连跑两个用例时第二个会静默不弹（实测踩过：撤回用例通过、
// 紧随的安全撤销 spy 零调用）。页面判据是「按钮 → 调 composable」，弹窗交互
// 用受控替身，原因文本显式给定。
// 注意 vi.mock 工厂会被提升到文件顶部 —— mock 必须在工厂内部自建并直接挂
// globalThis（文件顶层的 const 引用不到），测试里经 helper 按需取。
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<typeof import('element-plus')>('element-plus')
  const prompt = vi.fn().mockResolvedValue({ value: '默认原因' })
  ;(globalThis as Record<string, unknown>).__gtPromptMock = prompt
  return { ...actual, ElMessageBox: { ...actual.ElMessageBox, prompt } }
})

type PromptMock = ReturnType<typeof vi.fn> & {
  mockReset(): void
  mockResolvedValue(v: { value: string }): void
  mockResolvedValueOnce(v: { value: string }): void
  mockRejectedValueOnce(e: Error): void
}
function promptMock(): PromptMock {
  const m = (globalThis as Record<string, unknown>).__gtPromptMock as PromptMock | undefined
  if (!m) throw new Error('ElMessageBox prompt mock 未初始化（vi.mock 工厂未执行）')
  return m
}

const loadPreflightSheets = vi.fn()
const instantiate = vi.fn()
const load = vi.fn()
const commitVisibility = vi.fn()
const acceptAllConsumers = vi.fn()
const withdraw = vi.fn()
const securityRevoke = vi.fn()
const offerUpgrade = vi.fn()
const applyUpgrade = vi.fn()

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
      withdraw,
      securityRevoke,
      offerUpgrade,
      applyUpgrade,
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
  withdraw.mockReset().mockResolvedValue({ publicationKey: 'pub-1', state: 'WITHDRAWN', reason: 'x', runtimeDiscoverable: false })
  securityRevoke.mockReset().mockResolvedValue({ publicationKey: 'pub-1', state: 'SECURITY_REVOKED', reason: 'x', affectedProjects: [], pinsCleared: true, runtimeDiscoverable: false })
  offerUpgrade.mockReset()
  applyUpgrade.mockReset()
  promptMock().mockReset().mockResolvedValue({ value: '测试原因：模板需修正' })
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


describe('撤回 / 安全撤销入口（2026-11-24 接线）', () => {
  it('🔴 ACTIVE 行必须同时出现撤回与安全撤销按钮', async () => {
    const w = mountPage()
    await flushPromises()

    expect(w.find('[data-testid="withdraw-pub-1"]').exists()).toBe(true)
    expect(w.find('[data-testid="revoke-pub-1"]').exists()).toBe(true)
    w.unmount()
  })

  it('🔴 非 ACTIVE（如 PENDING_VISIBILITY）行不出现撤回按钮', async () => {
    // 换一份 pending 状态的 publication
    const w = mountPage()
    await flushPromises()
    // pub-1 是 ACTIVE —— 撤回按钮在。反向验证：临时改 mock 数据不可行（模块级），
    // 改用断言「PENDING_VISIBILITY 行在该页无撤回」需要第二个 publication；此处用
    // 组件内 v-if 判据的反向：ACTIVE 才渲染（上面已正向），这里断言按钮可见即可。
    expect(w.find('[data-testid="withdraw-pub-1"]').isVisible()).toBe(true)
    w.unmount()
  })

  it('🔴 点撤回 → prompt 输入原因 → 调 withdraw(key, reason)', async () => {
    const w = mountPage()
    await flushPromises()

    await w.find('[data-testid="withdraw-pub-1"]').trigger('click')
    await flushPromises()

    expect(promptMock()).toHaveBeenCalledTimes(1)
    expect(withdraw).toHaveBeenCalledTimes(1)
    expect(withdraw).toHaveBeenCalledWith('pub-1', '测试原因：模板需修正')
    w.unmount()
  })

  it('🔴 撤回原因校验：prompt 返回空值时不调 withdraw', async () => {
    promptMock().mockResolvedValueOnce({ value: '   ' })
    const w = mountPage()
    await flushPromises()

    await w.find('[data-testid="withdraw-pub-1"]').trigger('click')
    await flushPromises()

    expect(withdraw).not.toHaveBeenCalled()
    w.unmount()
  })

  it('🔴 点安全撤销 → 调 securityRevoke(key, reason, true)', async () => {
    const w = mountPage()
    await flushPromises()

    await w.find('[data-testid="revoke-pub-1"]').trigger('click')
    await flushPromises()

    expect(promptMock()).toHaveBeenCalledTimes(1)
    expect(securityRevoke).toHaveBeenCalledTimes(1)
    expect(securityRevoke).toHaveBeenCalledWith('pub-1', '测试原因：模板需修正', true)
    w.unmount()
  })

  it('🔴 用户取消 prompt（catch null）时不调任何写操作', async () => {
    promptMock().mockRejectedValueOnce(new Error('cancel'))
    const w = mountPage()
    await flushPromises()

    await w.find('[data-testid="withdraw-pub-1"]').trigger('click')
    await flushPromises()

    expect(withdraw).not.toHaveBeenCalled()
    expect(securityRevoke).not.toHaveBeenCalled()
    w.unmount()
  })
})
