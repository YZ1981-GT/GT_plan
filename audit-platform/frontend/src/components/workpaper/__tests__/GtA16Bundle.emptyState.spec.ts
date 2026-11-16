/**
 * GtA16Bundle：本项目没有 A16-1 ~ A16-7 子底稿时显示空态说明（spec api-prefix-fix-recovery R3）。
 * 原先只剩空白页签区、看不出原因（residual 任务 28 浏览器实测）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const getWpIndex = vi.fn()
vi.mock('@/services/workpaperApi', () => ({
  __esModule: true,
  getWpIndex: (...a: unknown[]) => getWpIndex(...a),
}))

const push = vi.fn()
vi.mock('vue-router', () => ({
  __esModule: true,
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push }),
}))

// A16 推荐版本走 apiProxy（api.get / api.post）
const apiGet = vi.fn()
const apiPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  __esModule: true,
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
  },
}))

// ElMessage：一键创建的成功 / 警告 / 失败文案要能被断言
const msgSuccess = vi.fn()
const msgWarning = vi.fn()
const msgError = vi.fn()
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), {
      success: (...a: unknown[]) => msgSuccess(...a),
      warning: (...a: unknown[]) => msgWarning(...a),
      error: (...a: unknown[]) => msgError(...a),
      info: vi.fn(),
    }),
  }
})

// __esModule: true 让 defineAsyncComponent 正确解包 default（否则 test-utils 读取命名空间的
// __isTeleport 触发 vitest mock 未定义导出错误 —— 同 GtC1EntityControl.spec.ts 的写法）
vi.mock('../WorkpaperWordEditor.vue', () => ({
  __esModule: true,
  default: { name: 'WorkpaperWordEditor', template: '<div class="word-editor" />' },
}))

import GtA16Bundle from '../GtA16Bundle.vue'

const stubs = {
  'el-empty': {
    props: ['description'],
    template: '<div class="el-empty-stub"><span class="desc">{{ description }}</span><slot /></div>',
  },
  'el-button': { template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot /></button>' },
  'el-tabs': { template: '<div class="el-tabs-stub"><slot /></div>' },
  'el-tab-pane': { props: ['label', 'name'], template: '<div class="el-tab-pane-stub" :data-name="name"><slot /></div>' },
  'el-alert': {
    props: ['title', 'type'],
    template: '<div class="el-alert-stub"><span class="title"><slot name="title" /></span><slot /></div>',
  },
}

function mountBundle() {
  return mount(GtA16Bundle, {
    props: { wpId: 'wp-a16', projectId: 'p1' },
    global: { stubs, directives: { loading: {} } },
  })
}

beforeEach(() => {
  getWpIndex.mockReset()
  push.mockReset()
  apiGet.mockReset()
  apiPost.mockReset()
  msgSuccess.mockReset()
  msgWarning.mockReset()
  msgError.mockReset()
  // 默认：推荐版本取不到 ⇒ 不显示提示（不干扰既有空态用例）
  apiGet.mockRejectedValue(new Error('no recommendation'))
})

describe('GtA16Bundle 空态', () => {
  it('wp_index 里没有任何 A16 子底稿：显示空态说明、不渲染页签区', async () => {
    getWpIndex.mockResolvedValue([{ id: 'x', wp_code: 'A16' }, { id: 'y', wp_code: 'A18-2' }])
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(true)
    const desc = w.find('.el-empty-stub .desc').text()
    // 缺哪几张要具体列出，不能只说「一张都没有」
    for (const code of ['A16-1', 'A16-2', 'A16-3', 'A16-4', 'A16-5', 'A16-6', 'A16-7']) {
      expect(desc).toContain(code)
    }
    expect(w.find('.el-tabs-stub').exists()).toBe(false)
  })

  it('空态里的「去底稿列表生成」可点击，跳到本项目底稿列表并高亮 A16', async () => {
    getWpIndex.mockResolvedValue([{ id: 'x', wp_code: 'A16' }])
    const w = mountBundle()
    await flushPromises()
    const btn = w.findAll('.el-button-stub').find(b => b.text().includes('去底稿列表生成'))
    expect(btn, '空态里必须有去底稿列表的入口').toBeTruthy()
    await btn!.trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'p1' },
      query: { highlight: 'A16' },
    })
  })

  it('取 wp_index 失败：说明是加载失败（不是「未生成」），并给重试入口', async () => {
    let attempt = 0
    getWpIndex.mockImplementation(async () => {
      attempt += 1
      if (attempt === 1) throw new Error('网络异常')
      return [{ id: 'a1', wp_code: 'A16-1' }]
    })
    const w = mountBundle()
    await flushPromises()
    const desc = w.find('.el-empty-stub .desc').text()
    expect(desc).toContain('加载失败')
    expect(desc).toContain('网络异常')
    // 不能把加载失败说成「没有生成子底稿」
    expect(desc).not.toContain('还没有生成')

    // 重试：第二次成功则应正常渲染页签
    await w.findAll('.el-button-stub').find(b => b.text().includes('重试'))!.trigger('click')
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(false)
    expect(w.findAll('.el-tab-pane-stub').map(n => n.attributes('data-name'))).toEqual(['A16-1'])
  })

  it('有子底稿：只渲染存在的页签，不显示空态', async () => {
    getWpIndex.mockResolvedValue([{ id: 'a1', wp_code: 'A16-1' }, { id: 'a3', wp_code: 'A16-3' }])
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(false)
    const names = w.findAll('.el-tab-pane-stub').map(n => n.attributes('data-name'))
    expect(names).toEqual(['A16-1', 'A16-3'])
  })

  it('加载未结束前不闪空态', async () => {
    let resolve!: (v: unknown) => void
    getWpIndex.mockReturnValue(new Promise(r => { resolve = r }))
    const w = mountBundle()
    await Promise.resolve()
    // 首帧 visibleTabs 同样是 0 —— 只按它判就会在这里误显空态
    expect(w.find('.el-empty-stub').exists()).toBe(false)
    resolve([])
    await flushPromises()
    expect(w.find('.el-empty-stub').exists()).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// A16 推荐版本提示（缺陷修复 2026-11-16）
//
// 背景：这套信息原先只挂在 `GtAProgramConsole` 的 A16 seq2 行（要求 sheetCode === 'A16'
// 且走 `a-program-console`），而 A16 底稿的 componentType 已是 `a16-bundle`
// ⇒ 推荐标记在界面上永远不出现。这里钉住「Bundle 层能显示推荐版本」。
// ─────────────────────────────────────────────────────────────────────────────
describe('GtA16Bundle 推荐版本提示', () => {
  it('推荐版本未生成：顶部提示 + 一键创建', async () => {
    getWpIndex.mockResolvedValue([{ id: 'a1', wp_code: 'A16-1' }])
    apiGet.mockResolvedValue({
      recommended_code: 'A16-2',
      recommended_label: '整合审计',
      all_versions: [],
      always_required: ['A16-7'],
    })
    const w = mountBundle()
    await flushPromises()

    const alert = w.find('.el-alert-stub')
    expect(alert.exists(), '推荐版本缺失时必须给出提示').toBe(true)
    expect(alert.find('.title').text()).toContain('A16-2')
    expect(alert.find('.title').text()).toContain('整合审计')
    expect(w.findAll('.el-button-stub').some(b => b.text().includes('一键创建'))).toBe(true)
  })

  it('推荐版本已生成：不打扰（页签已列出全部可用版本）', async () => {
    getWpIndex.mockResolvedValue([{ id: 'a2', wp_code: 'A16-2' }, { id: 'a1', wp_code: 'A16-1' }])
    apiGet.mockResolvedValue({ recommended_code: 'A16-2', recommended_label: '整合审计' })
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-alert-stub').exists()).toBe(false)
    expect(w.findAll('.el-tab-pane-stub').map(n => n.attributes('data-name'))).toEqual(['A16-1', 'A16-2'])
  })

  it('推荐版本接口失败：静默降级，不影响页签与空态', async () => {
    getWpIndex.mockResolvedValue([{ id: 'a1', wp_code: 'A16-1' }])
    apiGet.mockRejectedValue(new Error('500'))
    const w = mountBundle()
    await flushPromises()
    expect(w.find('.el-alert-stub').exists()).toBe(false)
    expect(w.findAll('.el-tab-pane-stub').map(n => n.attributes('data-name'))).toEqual(['A16-1'])
  })

  it('一键创建：调 generate-from-codes 后刷新页签与推荐状态', async () => {
    getWpIndex
      .mockResolvedValueOnce([{ id: 'a1', wp_code: 'A16-1' }])
      .mockResolvedValue([{ id: 'a1', wp_code: 'A16-1' }, { id: 'a2', wp_code: 'A16-2' }])
    apiGet.mockResolvedValue({ recommended_code: 'A16-2', recommended_label: '整合审计' })
    apiPost.mockResolvedValue({ created: 1, created_codes: ['A16-2'] })

    const w = mountBundle()
    await flushPromises()
    await w.findAll('.el-button-stub').find(b => b.text().includes('一键创建'))!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith(
      '/api/projects/p1/working-papers/generate-from-codes',
      { wp_codes: ['A16-2'] },
    )
    // 刷新后 A16-2 已在项目里 ⇒ 提示消失、页签出现
    expect(w.find('.el-alert-stub').exists()).toBe(false)
    expect(w.findAll('.el-tab-pane-stub').map(n => n.attributes('data-name'))).toContain('A16-2')
  })

  it('一键创建遇到「在回收站」：提示去回收站恢复，不谎报已创建', async () => {
    getWpIndex.mockResolvedValue([{ id: 'a1', wp_code: 'A16-1' }])
    apiGet.mockResolvedValue({ recommended_code: 'A16-2', recommended_label: '整合审计' })
    // 平台语义：软删的 wp_index 不重建，回执放进 in_recycle_codes
    apiPost.mockResolvedValue({
      created: 0,
      created_codes: [],
      in_recycle_codes: ['A16-2'],
      existing_codes: [],
      failures: [],
    })

    const w = mountBundle()
    await flushPromises()
    await w.findAll('.el-button-stub').find(b => b.text().includes('一键创建'))!.trigger('click')
    await flushPromises()

    const texts = msgWarning.mock.calls.map(c => String(c[0]))
    expect(
      texts.some(t => t.includes('回收站')),
      `应提示在回收站，实际：${JSON.stringify(texts)}`,
    ).toBe(true)
    const successTexts = msgSuccess.mock.calls.map(c => String(c[0]))
    expect(
      successTexts.some(t => t.includes('已创建')),
      '回收站场景不得谎报「已创建」',
    ).toBe(false)
  })

  it('推荐版本请求必须带 /api 前缀（utils/http baseURL 是 /）', async () => {
    getWpIndex.mockResolvedValue([{ id: 'a1', wp_code: 'A16-1' }])
    apiGet.mockResolvedValue({ recommended_code: 'A16-1' })
    mountBundle()
    await flushPromises()
    expect(apiGet).toHaveBeenCalled()
    const url = String(apiGet.mock.calls[0][0])
    expect(url.startsWith('/api/')).toBe(true)
    expect(url).toBe('/api/projects/p1/a16/recommended-version')
  })
})
