/**
 * formulaBarSupportGating.spec.ts — FormulaBar 函数支持矩阵 UI 门控（前端组件侧）
 * spec formula-manager-closure · Task 4.2 / 需求 8（禁静默 0）
 *
 * 验收判据（tasks.md Task 4.2）：
 *   不支持者 UI 禁用/标注「此处不支持」、禁静默 0；支持者可运行。
 *   变异反证：把某不支持函数改成静默返 0 而 UI 仍可点，应被断言打红；
 *   反向断言支持函数不误判为禁用。
 *
 * 函数按钮渲染在 el-popover 内（jsdom 下惰性/teleport 不稳定），故本文件在真实挂载的
 * FormulaBar 实例上断言其**生产门控逻辑**：
 *  - sourceButtons（模板 :disabled / :title / data-supported 的唯一数据源）按执行器正确标 supported/reason；
 *  - pickSource 对不支持函数 fail-closed（提示「此处不支持」+ 不打开数据源弹窗，禁静默 0）；
 *  - 支持函数 pickSource 打开数据源弹窗（真实选择路径，非静默 0）。
 * 模板把 sourceButtons[].supported 直接绑定到 el-button :disabled，故门控逻辑即 UI 行为的真源。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const { mockMsgInfo } = vi.hoisted(() => ({ mockMsgInfo: vi.fn() }))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { info: mockMsgInfo, error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  }
})

vi.mock('@/stores/addressRegistry', () => ({
  useAddressRegistry: () => ({ loaded: false, tbAddresses: [], reportAddresses: [], noteAddresses: [] }),
}))
vi.mock('@/services/acnr/useAcnr', () => ({ useAcnr: () => ({}) }))
// apiProxy：支持函数打开弹窗后会走 legacy 取数端点；mock 成空数组，避免 jsdom 真实网络请求噪声
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue([]), post: vi.fn().mockResolvedValue([]) } }))

import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import FormulaBar from '../FormulaBar.vue'

const CELL = {
  cell: 'B5',
  address: '审定表E1!B5',
  value: null,
  formula: null,
  formula_type: null,
  formula_desc: null,
  fetch_rule_id: null,
  merge: null,
  is_merged: false,
}

function mountBar(executor?: string) {
  return mount(FormulaBar, {
    props: { visible: true, cellInfo: CELL, projectId: 'p1', executor: executor as any },
    global: { plugins: [ElementPlus, createPinia()] },
  })
}

interface SourceButton {
  fn: string
  supported: boolean
  reason: string
}
function buttons(w: ReturnType<typeof mountBar>): SourceButton[] {
  return (w.vm as any).sourceButtons as SourceButton[]
}
function btn(w: ReturnType<typeof mountBar>, fn: string): SourceButton {
  return buttons(w).find((b) => b.fn === fn)!
}

describe('FormulaBar 函数支持矩阵 UI 门控', () => {
  beforeEach(() => {
    mockMsgInfo.mockReset()
    // 清理上一个测试 teleport 到 body 的 popover 残留，避免跨测试 DOM 污染
    document.body.innerHTML = ''
  })

  it('wp_evaluator 执行器下全部取数按钮可用（supported，无禁用原因）', () => {
    const w = mountBar('wp_evaluator')
    for (const fn of ['TB', 'ROW', 'SUM_ROW', 'NOTE', 'WP', 'REPORT']) {
      const b = btn(w, fn)
      expect(b.supported).toBe(true)
      expect(b.reason).toBe('')
    }
  })

  it('note_executor 执行器下 ROW/SUM_ROW 不支持 → supported=false + 标注原因（禁静默 0 的依据）', () => {
    const w = mountBar('note_executor')
    for (const fn of ['ROW', 'SUM_ROW']) {
      const b = btn(w, fn)
      expect(b.supported).toBe(false)
      expect(b.reason).toBeTruthy() // UI :title 据此标注「此处不支持」
    }
    // note 执行器支持 TB/REPORT/NOTE/WP
    for (const fn of ['TB', 'REPORT', 'NOTE', 'WP']) {
      expect(btn(w, fn).supported).toBe(true)
    }
  })

  it('不支持按钮点击 fail-closed：不开数据源弹窗，提示「此处不支持」（禁静默 0）', async () => {
    const w = mountBar('note_executor')
    await (w.vm as any).pickSource('ROW')
    await flushPromises()
    expect(mockMsgInfo).toHaveBeenCalledTimes(1)
    expect(mockMsgInfo.mock.calls[0][0]).toContain('此处不支持')
    expect((w.vm as any).showSourceDialog).toBe(false) // 未进入可能静默 0 的取数路径
  })

  it('支持按钮点击打开数据源弹窗（产生真实选择路径，非静默 0）', async () => {
    const w = mountBar('wp_evaluator')
    await (w.vm as any).pickSource('TB')
    await flushPromises()
    expect(mockMsgInfo).not.toHaveBeenCalled()
    expect((w.vm as any).showSourceDialog).toBe(true)
  })

  it('DOM 校验：note 执行器 ROW 按钮渲染为 disabled（打开取数 popover 后）', async () => {
    const w = mountBar('note_executor')
    // 打开 📋 选择 popover，使内部取数按钮渲染
    const trigger = w.findAll('button').find((b) => b.text().includes('选择'))
    expect(trigger).toBeTruthy()
    await trigger!.trigger('click')
    await flushPromises()
    // el-button 渲染为 <button data-testid=...>，data-testid 即落在该 button 本身
    const rowBtn = document.querySelector('[data-testid="fn-btn-ROW"]') as HTMLButtonElement | null
    expect(rowBtn).toBeTruthy()
    expect(rowBtn!.getAttribute('data-supported')).toBe('0')
    const buttonEl = rowBtn!.tagName.toLowerCase() === 'button' ? rowBtn! : rowBtn!.querySelector('button')
    expect(buttonEl?.hasAttribute('disabled') || buttonEl?.classList.contains('is-disabled')).toBe(true)
    expect(rowBtn!.getAttribute('title')).toContain('此处不支持')
  })

  // ── 变异反证 ──
  it('变异：note 执行器把 ROW 当支持可点必与门控冲突；反向断言 wp_evaluator 下不误判', () => {
    const wNote = mountBar('note_executor')
    const mutatedClickable = true // 变异态（错误）= ROW 在 note 可点 → 静默 0
    const realSupported = btn(wNote, 'ROW').supported
    expect(realSupported).toBe(false) // 真源：note 执行器禁 ROW
    expect(realSupported).not.toBe(mutatedClickable) // 生产若按变异态渲染，此红
    // 反向断言：wp_evaluator 下同一按钮不被误判为禁用
    const wWp = mountBar('wp_evaluator')
    expect(btn(wWp, 'ROW').supported).toBe(true)
  })
})
