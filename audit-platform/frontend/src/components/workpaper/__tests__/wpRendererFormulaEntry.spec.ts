/**
 * wpRendererFormulaEntry.spec.ts — 底稿页「公式管理」入口的当前页身份守卫
 *
 * 用户实测缺陷：在 D2 宿主里切到子页 D0-2（核实被函证单位信息）后打开公式管理，
 * 公式中心左树没定位到 D0-2，右侧列的是 D2-1 的公式 —— 因为入口把位置身份交给了
 * 外层旧入口，用的是初始页上下文。
 *
 * 本文件锁死：位置身份只能来自渲染器的 canonical 状态（当前 sheet + render-config
 * 的 wp_code），且工具栏按钮与子组件 `open-formula` 事件必须共用同一入口。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const D2_1 = '应收账款审定表D2-1'
const D0_2 = '核实被函证单位信息D0-2'

const { emit, cfg } = vi.hoisted(() => ({
  emit: vi.fn(),
  cfg: { wpCode: 'D2' as string, projectId: 'project-1' as string },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit, on: vi.fn(), off: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    projectId: 'project-1',
    auditYear: 2025,
    year: 2025,
    loadProjectContext: vi.fn(async () => undefined),
  }),
}))
vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: vi.fn(() => true) }),
}))
vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(async () => ({})), put: vi.fn(async () => ({})), post: vi.fn(async () => ({})) },
}))
vi.mock('@/composables/useWpRenderer', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  const { ref: vueRef, computed: vueComputed } = await import('vue')
  return {
    ...actual,
    useWpRenderer: () => ({
      // 两张 sheet 都用 skip：走占位渲染，绕开正在重构中的渲染器注册表依赖
      renderConfig: vueRef({
        wp_id: 'wp-d2',
        wp_code: cfg.wpCode,
        project_id: cfg.projectId,
        audit_year: 2025,
        template_version: 'test',
        sheets: [
          { sheet_name: D2_1, componentType: 'skip', schema: {}, html_data: {}, cross_refs: [] },
          { sheet_name: D0_2, componentType: 'skip', schema: {}, html_data: {}, cross_refs: [] },
        ],
      }),
      loading: vueRef(false),
      error: vueRef(null),
      reload: vi.fn(async () => undefined),
      componentType: vueComputed(() => 'skip'),
      wpCode: vueComputed(() => cfg.wpCode),
      fillResults: vueComputed(() => null),
      schemaFallbackBanner: vueComputed(() => null),
    }),
  }
})

import GtWpRenderer from '../GtWpRenderer.vue'

function mountRenderer() {
  return shallowMount(GtWpRenderer, {
    props: { wpId: 'wp-d2' },
    global: { renderStubDefaultSlot: false },
  })
}

const state = (w: ReturnType<typeof mountRenderer>) => (w.vm as any).$.setupState
const lastPayload = () => emit.mock.calls.at(-1)?.[1] as Record<string, unknown> | undefined

describe('底稿页公式管理入口：位置身份 = 当前页', () => {
  beforeEach(() => {
    emit.mockReset()
    cfg.wpCode = 'D2'
    cfg.projectId = 'project-1'
  })

  it('默认停在首个 sheet 时带首页上下文', () => {
    const w = mountRenderer()
    state(w).openPageFormulaManager()

    expect(emit).toHaveBeenCalledTimes(1)
    expect(emit.mock.calls[0][0]).toBe('open-formula-manager')
    expect(lastPayload()).toMatchObject({
      wpId: 'wp-d2', projectId: 'project-1', wpCode: 'D2', sheetName: D2_1,
    })
    w.unmount()
  })

  it('切到子页 D0-2 后必须带 D0-2，不得回退到 D2-1', () => {
    const w = mountRenderer()
    expect(state(w).selectSheet(D0_2)).toBe(D0_2)
    state(w).openPageFormulaManager()

    expect(lastPayload()).toMatchObject({ wpCode: 'D2', sheetName: D0_2 })
    expect(lastPayload()!.sheetName).not.toBe(D2_1)
    w.unmount()
  })

  it('来回切页时每次都取当次的当前页（不残留上一页）', () => {
    const w = mountRenderer()
    state(w).selectSheet(D0_2)
    state(w).openPageFormulaManager()
    state(w).selectSheet(D2_1)
    state(w).openPageFormulaManager()

    expect(emit.mock.calls.map((c) => (c[1] as any).sheetName)).toEqual([D0_2, D2_1])
    w.unmount()
  })

  it('缺 wp_code 时不打开（避免公式中心按错身份加载）', () => {
    cfg.wpCode = ''
    const w = mountRenderer()
    state(w).openPageFormulaManager()

    expect(emit).not.toHaveBeenCalled()
    w.unmount()
  })

  it('子组件 open-formula 与工具栏按钮共用同一入口，且不再向上冒泡', () => {
    // 接线形态判据：单一 canonical 入口。若改回 `emit('open-formula')` 交给外层，
    // 子页就会被外层按初始页上下文打开 —— 本条即为此回归的哨兵。
    const src = readFileSync(resolve(__dirname, '../GtWpRenderer.vue'), 'utf-8')
    expect(src).toContain('@open-formula="openPageFormulaManager"')
    expect(src).toContain('@click="openPageFormulaManager"')
    expect(src).not.toMatch(/emit\(\s*'open-formula'/)
    expect(src).not.toMatch(/'open-formula':\s*\[payload/)
  })
})
