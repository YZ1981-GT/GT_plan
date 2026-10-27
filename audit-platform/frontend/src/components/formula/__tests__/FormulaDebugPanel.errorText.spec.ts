/**
 * 公式调试 / 健康度 / 变更时间线面板：请求失败时在面板里写明原因、不另弹提示（spec formula-fetch-followup-defect-closure 7.2）。
 *
 * 原状：catch 里写 `handleApiError(e, { silent: true }) || '请求失败'` —— handleApiError 的第二参是上下文文案、
 * 返回 void ⇒ 弹一条「[object Object]：无权操作」，面板里永远只显示「请求失败 / 加载失败」；请求也不带 _silent，
 * 全局拦截器再弹一次。FormulaPushVerifyPanel 早先修过同一写法，另外三个面板漏了。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get, post, msg } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg, ElNotification: vi.fn() }
})
vi.mock('@/services/apiProxy', () => ({ api: { get, post } }))

import FormulaDebugPanel from '@/components/formula/FormulaDebugPanel.vue'
import FormulaHealthPanel from '@/components/formula/FormulaHealthPanel.vue'
import FormulaTimelinePanel from '@/components/formula/FormulaTimelinePanel.vue'

const DENIED = { response: { status: 403, data: { detail: '您不是该项目成员' } } }
const state = (w: any) => w.vm.$.setupState

describe('公式调试面板的错误显示', () => {
  beforeEach(() => vi.clearAllMocks())

  it('失败：面板写明后端给的原因，不弹提示；请求带 _silent', async () => {
    post.mockRejectedValue(DENIED)
    const w = shallowMount(FormulaDebugPanel, {
      props: { formula: "NOTE('五、1','合计','期末')", projectId: 'p1', year: 2025, scope: 'report' },
      global: { plugins: [ElementPlus] },
    })
    await state(w).onRun()
    await flushPromises()
    expect(post).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ project_id: 'p1', year: 2025 }),
      expect.objectContaining({ _silent: true }))
    expect(state(w).result.errors).toEqual(['您不是该项目成员'])
    expect(msg.error).not.toHaveBeenCalled()
    expect(msg.warning).not.toHaveBeenCalled()
    w.unmount()
  })

  it('成功：结果原样显示', async () => {
    post.mockResolvedValue({ value: '9182572.99', ok: true, state: 'ok', trace: ["NOTE('五、1','合计','期末') = 9182572.99"] })
    const w = shallowMount(FormulaDebugPanel, {
      props: { formula: "NOTE('五、1','合计','期末')", projectId: 'p1', year: 2025 },
      global: { plugins: [ElementPlus] },
    })
    await state(w).onRun()
    expect(state(w).result.value).toBe('9182572.99')
    w.unmount()
  })

  // post-push-residual-defect-closure R2：项目没填审计年度 ⇒ 不请求、面板里写明原因（原先按钮点了没反应）
  it('审计年度为空：不请求，面板写明去填年度', async () => {
    const w = shallowMount(FormulaDebugPanel, {
      props: { formula: "NOTE('五、1','合计','期末')", projectId: 'p1', year: null },
      global: { plugins: [ElementPlus] },
    })
    await state(w).onRun()
    expect(post).not.toHaveBeenCalled()
    expect(state(w).result.errors).toEqual(['未设置审计年度，请先在项目基本信息中填写'])
    w.unmount()
  })
})

describe.each([
  ['公式健康度面板', FormulaHealthPanel],
  ['公式变更时间线面板', FormulaTimelinePanel],
])('%s的错误显示', (_name, Panel) => {
  beforeEach(() => vi.clearAllMocks())

  it('加载失败：面板写明原因，不弹提示；请求带 _silent', async () => {
    get.mockRejectedValue(DENIED)
    const w = shallowMount(Panel as any, { props: { projectId: 'p1', year: 2025 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(get).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ _silent: true }))
    expect(state(w).error).toBe('您不是该项目成员')
    expect(msg.error).not.toHaveBeenCalled()
    expect(msg.warning).not.toHaveBeenCalled()
    w.unmount()
  })
})

// ── 全仓守卫：handleApiError 第二参必须是文案（不是选项对象），也不能拿它的返回值（恒为 undefined） ──
const SRC = resolve(__dirname, '../../..')
const SKIP_DIRS = new Set(['__tests__', 'test', 'tests', 'node_modules'])
const MISUSE = [
  /handleApiError\(\s*[\w.?]+\s*,\s*\{/,
  /=\s*handleApiError\(/,
  /handleApiError\([^)]*\)\s*(?:\|\||\?\?)/,
]
const COMMENT_LINE = /^\s*(?:\/\/|\/\*|\*|<!--)/

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.(?:ts|vue)$/.test(name) && !/\.(?:spec|test)\.ts$/.test(name)) out.push(full)
  }
  return out
}

function misuses(text: string): number {
  return text.split('\n').filter((ln) => !COMMENT_LINE.test(ln) && MISUSE.some((re) => re.test(ln))).length
}

describe('handleApiError 用法守卫', () => {
  it('全仓没有把选项对象当第二参、或使用其返回值的写法', () => {
    const hits = walk(SRC).filter((f) => misuses(readFileSync(f, 'utf-8')))
      .map((f) => relative(SRC, f).split('\\').join('/'))
    expect(hits).toEqual([])
  })

  it('判据能抓到三种误用（防空转），注释里提到不算', () => {
    expect(misuses("    error.value = handleApiError(e, { silent: true }) || '加载失败'")).toBe(1)
    expect(misuses("    handleApiError(err, { silent: true })")).toBe(1)
    expect(misuses("    const t = handleApiError(e, '加载')")).toBe(1)
    expect(misuses("    // 原先写 handleApiError(e, { silent: true }) || '请求失败'")).toBe(0)
    expect(misuses("    handleApiError(e, '加载公式')")).toBe(0)
  })
})
