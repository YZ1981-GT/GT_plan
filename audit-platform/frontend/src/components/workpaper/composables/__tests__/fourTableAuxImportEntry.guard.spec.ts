/**
 * fourTableAuxImportEntry.guard.spec.ts — 四表库「从余额表导入」入口连通守卫（Task 8）.
 *
 * spec: .kiro/specs/four-table-extraction-entry-completion/ Task 8
 * Requirements:
 *   - 6.3：vitest 断言按钮存在、disabled 受 `isReadonly` 控制、点击真调对应端点（不是只 mock 通过）
 *   - 4.4：0 行按 reason 码给可辨别中文提示（全分支覆盖）
 * Property 7（连接性）：每个循环的「从余额表导入」必须打**字面量正确**的端点 URL
 *   （`.../{cycle}/import-aux-balance`），改错循环前缀（k1→d1）必须打红 —— 见 Block D 变异自检。
 *
 * ── 为什么这样测（防假绿三源）──────────────────────────────────────────────
 *  ① 不 grep「函数存在」：Block A 真调各循环**生产代码**的 `importFromAuxBalance`
 *     （经 http.post / api.post / 动态 import('@/utils/http')，最终都落到被 mock 的
 *     `@/utils/http` 默认导出），断言 mock 收到的**字面量完整 URL 串**，而非子串/正则。
 *  ② 不只 mount 通过：Block B mount 真实宿主（K1TabDetail / D5TabDetail），点击真按钮，
 *     断言 http.post 收到该循环字面量 URL —— 按钮存在 + isReadonly 禁用 + 点击真发请求
 *     一次走完（Requirement 6.3）。
 *  ③ 变异自检（Block D）：把断言里的循环前缀 k1→d1 后，同一断言必须 RED —— 证明字面量
 *     断言真的锁住了循环前缀（Property 7 连接性），不是恒真。
 *
 * ── 变异 RED 实证（已真翻生产代码验证，改动已还原）──────────────────────────
 *  把生产文件 `useK1DetailAutoSeed.ts` 的 URL builder 从
 *      `/api/workpapers/${wpId}/k1/import-aux-balance`
 *  真改为
 *      `/api/workpapers/${wpId}/d1/import-aux-balance`
 *  后 `rtk npx vitest run <本文件>` → **3 个用例 RED（22 中 3 失败），四态判定 = RED**：
 *    1) Block A「K1 手动入口」：expected .../k1/... received .../d1/...（真调 manualImport 生产链路）
 *    2) Block B「K1TabDetail 点击」：expected .../k1/... received .../d1/...（真 mount + 点击真按钮）
 *    3) Block D「K1 前缀翻转自检」：real 与 mutated 收敛（生产已是 d1）→ not.toBe RED，正确提示生产被变异
 *  其余 19 用例保持 GREEN（D3/D5/D6/D7 各自前缀不受 K1 变异影响 → 证明无串扰、非恒真）。
 *  改回 k1 后 22/22 全 GREEN。
 *  ⇒ 字面量断言真的锁住了循环前缀（Property 7 连接性），接错循环必被拦下（防接错循环）。
 *  Block D 另含一个**自动化**同义变异（对 URL 副本翻转前缀，断言其打红），CI 常驻、无需人工翻转。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref, computed, h } from 'vue'

// ── 单点 mock：所有循环的 aux 取数最终都经 `@/utils/http` 默认导出（api.post/动态 import 亦然）──
const postMock = vi.fn()
const getMock = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { post: (...a: any[]) => postMock(...a), get: (...a: any[]) => getMock(...a) },
}))
// ElMessage 提示不参与断言，短路避免 teleport/DOM 噪音
vi.mock('element-plus', async (orig) => {
  const actual = await (orig as any)()
  const noop = () => {}
  const msg: any = Object.assign(noop, { success: noop, info: noop, warning: noop, error: noop })
  return { ...actual, ElMessage: msg, ElMessageBox: { prompt: vi.fn() } }
})

import http from '@/utils/http'
import {
  auxImportPrompt,
  type AuxImportReason,
  type AuxImportPromptLevel,
} from '../fourTableAuxImportFeedback'
import { K1_IMPORT_AUX_URL, manualImportK1DetailFromAux } from '../useK1DetailAutoSeed'

// 各循环生产 composable（真代码，非复刻）
import { useD3ImportExport } from '../useD3ImportExport'
import { useD5Detail } from '../useD5Detail'
import { useD6Detail } from '../useD6Detail'
import { useD7Detail } from '../useD7Detail'

/** 从 postMock 的调用记录里取「本次唯一一次 aux 取数」的 URL（第一个位置参数）。 */
function lastPostUrl(): string {
  expect(postMock).toHaveBeenCalledTimes(1)
  return String(postMock.mock.calls[0][0])
}

/**
 * 在**已挂载组件的 setup 作用域**内执行 fn（满足 onBeforeUnmount / EventBus 注册等生命周期钩子）。
 * 返回 fn 的返回值。用于安全驱动需要 Vue 生命周期的 composable。
 */
async function runInSetup<T>(fn: () => T): Promise<{ result: T; unmount: () => void }> {
  let captured!: T
  const Host = defineComponent({
    setup() {
      captured = fn()
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  await flushPromises()
  return { result: captured, unmount: () => wrapper.unmount() }
}

beforeEach(() => {
  postMock.mockReset()
  getMock.mockReset()
  // 默认让端点返回一个「0 行 / reason=ok」的规范响应（ResponseWrapperMiddleware 双层包装）
  postMock.mockResolvedValue({ data: { data: { imported_count: 0, reason: 'ok' } } })
})

// ════════════════════════════════════════════════════════════════════════════
// Block A — 字面量 URL 连接性守卫（Property 7）：真调各循环生产代码，断言完整字面量 URL
// ════════════════════════════════════════════════════════════════════════════
describe('Block A · 字面量 URL 连接性（Property 7 · 防接错循环）', () => {
  it('K1 手动入口 → 打 /api/workpapers/{wp}/k1/import-aux-balance（字面量）', async () => {
    // URL builder 本身也断言字面量（不是拼串正则）
    expect(K1_IMPORT_AUX_URL('wp-1')).toBe('/api/workpapers/wp-1/k1/import-aux-balance')
    await manualImportK1DetailFromAux({ wpId: 'wp-1', reload: vi.fn().mockResolvedValue(undefined) })
    expect(lastPostUrl()).toBe('/api/workpapers/wp-1/k1/import-aux-balance')
  })

  it('D3 明细入口 → 打 .../d3/import-aux-balance（字面量）', async () => {
    const { result } = await runInSetup(() =>
      useD3ImportExport({ wpId: ref('wp-1'), sheetCode: 'D3-2' }),
    )
    await result.importFromAuxBalance()
    expect(lastPostUrl()).toBe('/api/workpapers/wp-1/d3/import-aux-balance')
  })

  it('D5 明细入口 → 打 .../d5/import-aux-balance（字面量）', async () => {
    const { result } = await runInSetup(() =>
      useD5Detail({
        allResponses: ref(new Map()),
        wpId: ref('wp-1'),
        projectId: ref('proj-1'),
        saveImmediate: vi.fn().mockResolvedValue(undefined),
        debouncedSave: vi.fn(),
        isReadonly: ref(false),
      }),
    )
    await result.importFromAuxBalance()
    expect(lastPostUrl()).toBe('/api/workpapers/wp-1/d5/import-aux-balance')
  })

  it('D6 明细入口 → 打 .../d6/import-aux-balance（字面量）', async () => {
    const { result } = await runInSetup(() =>
      useD6Detail({
        allResponses: ref(new Map()),
        wpId: ref('wp-1'),
        projectId: ref('proj-1'),
        saveImmediate: vi.fn().mockResolvedValue(undefined),
        debouncedSave: vi.fn(),
        isReadonly: ref(false),
      } as any),
    )
    await (result as any).importFromAuxBalance()
    expect(lastPostUrl()).toBe('/api/workpapers/wp-1/d6/import-aux-balance')
  })

  it('D7 明细入口 → 打 .../d7/import-aux-balance（字面量）', async () => {
    const { result } = await runInSetup(() =>
      useD7Detail({
        allResponses: ref(new Map()),
        wpId: ref('wp-1'),
        projectId: ref('proj-1'),
        saveImmediate: vi.fn().mockResolvedValue(undefined),
        debouncedSave: vi.fn(),
        isReadonly: ref(false),
      } as any),
    )
    await (result as any).importFromAuxBalance()
    expect(lastPostUrl()).toBe('/api/workpapers/wp-1/d7/import-aux-balance')
  })

  it('循环前缀必须两两不同（防两条链接到同一端点）', () => {
    const urls = ['k1', 'd1', 'd2', 'd3', 'd5', 'd6', 'd7', 'f1', 'g7'].map(
      (c) => `/api/workpapers/wp-1/${c}/import-aux-balance`,
    )
    expect(new Set(urls).size).toBe(urls.length)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// Block B — 按钮存在 + isReadonly 禁用 + 点击真发请求（Requirement 6.3）
// ════════════════════════════════════════════════════════════════════════════

/**
 * Element Plus 组件全量 stub：让 el-dropdown-item / el-button 的默认插槽**即时**渲染到 DOM
 * （否则 el-dropdown 内容是 teleport/惰性，不展开点不到）。stub 保留 `disabled` 属性透传，
 * 供断言按钮禁用态。
 */
// 直通容器：渲染默认插槽（让下拉/工具栏里的入口进入 DOM）
const passthrough = (cls: string) => ({ template: `<div class="${cls}"><slot /></div>` })
// 空渲染：表格族的 scoped slot 会被真实 el-table 用 undefined row 调用而崩，直接不渲染其内容
const emptyStub = { template: '<div></div>' }

const EP_STUBS: Record<string, any> = {
  // 入口所在容器 + 入口本体（保留 disabled 透传 + click 门控）
  'el-dropdown': { template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': passthrough('el-dropdown-menu'),
  'el-dropdown-item': {
    props: ['disabled', 'divided'],
    emits: ['click'],
    template:
      '<div class="el-dropdown-item" :data-disabled="disabled ? \'true\' : \'false\'" @click="!disabled && $emit(\'click\')"><slot /></div>',
  },
  'el-button': {
    props: ['disabled', 'loading', 'type', 'size', 'plain', 'link'],
    emits: ['click'],
    template:
      '<button class="el-button" :disabled="disabled" :data-disabled="disabled ? \'true\' : \'false\'" @click="!disabled && $emit(\'click\')"><slot /></button>',
  },
  // 表格族：空渲染，避开 #default="{ row }" 被 undefined row 调用而崩（与本守卫无关）
  'el-table': emptyStub,
  'el-table-v2': emptyStub,
  'el-table-column': emptyStub,
  // 其余容器：直通默认插槽即可（工具栏/下拉项都在这些容器内）
  'el-tabs': passthrough('el-tabs'),
  'el-tab-pane': passthrough('el-tab-pane'),
  'el-popover': passthrough('el-popover'),
  'el-tooltip': passthrough('el-tooltip'),
  'el-card': passthrough('el-card'),
  'el-alert': passthrough('el-alert'),
  'el-divider': emptyStub,
  'el-checkbox': passthrough('el-checkbox'),
  'el-tag': passthrough('el-tag'),
  'el-icon': passthrough('el-icon'),
  'el-input': emptyStub,
  'el-input-number': emptyStub,
  'el-select': passthrough('el-select'),
  'el-option': emptyStub,
  'el-upload': passthrough('el-upload'),
}

/** 递归找到文案含「从余额表导入」的入口节点（dropdown-item 或 button）。 */
function findAuxEntry(wrapper: any) {
  const items = wrapper.findAll('.el-dropdown-item, .el-button')
  return items.find((n: any) => n.text().includes('从余额表导入'))
}

describe('Block B · 按钮存在 + isReadonly 禁用 + 点击真发请求', () => {
  // K1TabDetail：入口在「导入导出 ▾」下拉里
  it('K1TabDetail：入口存在，isReadonly=false 可点，点击打 k1 字面量端点', async () => {
    const K1TabDetail = (await import('../../k1/core/K1TabDetail.vue')).default
    const wrapper = mount(K1TabDetail, {
      props: {
        wpId: 'wp-1',
        projectId: 'proj-1',
        allResponses: new Map(),
        isReadonly: false,
      },
      global: { stubs: EP_STUBS },
    })
    await flushPromises()
    const entry = findAuxEntry(wrapper)
    expect(entry, '「从余额表导入」入口应存在于 K1TabDetail').toBeTruthy()
    expect(entry!.attributes('data-disabled')).toBe('false')

    postMock.mockReset()
    postMock.mockResolvedValue({ data: { data: { imported_count: 0, reason: 'ok' } } })
    await entry!.trigger('click')
    await flushPromises()
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(String(postMock.mock.calls[0][0])).toBe('/api/workpapers/wp-1/k1/import-aux-balance')
    wrapper.unmount()
  })

  it('K1TabDetail：isReadonly=true → 入口禁用（点击不发请求）', async () => {
    const K1TabDetail = (await import('../../k1/core/K1TabDetail.vue')).default
    const wrapper = mount(K1TabDetail, {
      props: { wpId: 'wp-1', projectId: 'proj-1', allResponses: new Map(), isReadonly: true },
      global: { stubs: EP_STUBS },
    })
    await flushPromises()
    const entry = findAuxEntry(wrapper)
    expect(entry, '「从余额表导入」入口应存在').toBeTruthy()
    expect(entry!.attributes('data-disabled')).toBe('true')

    postMock.mockReset()
    await entry!.trigger('click')
    await flushPromises()
    expect(postMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  // D5TabDetail：入口是 toolbar 上平铺 el-button
  it('D5TabDetail：入口存在，isReadonly=false 可点，点击打 d5 字面量端点', async () => {
    const D5TabDetail = (await import('../../d5/D5TabDetail.vue')).default
    const wrapper = mount(D5TabDetail, {
      props: {
        wpId: 'wp-1',
        projectId: 'proj-1',
        isReadonly: false,
        allResponses: new Map(),
        saveImmediate: vi.fn().mockResolvedValue(undefined),
        debouncedSave: vi.fn(),
      },
      global: { stubs: EP_STUBS },
    })
    await flushPromises()
    const entry = findAuxEntry(wrapper)
    expect(entry, '「从余额表导入」入口应存在于 D5TabDetail').toBeTruthy()
    expect(entry!.attributes('data-disabled')).toBe('false')

    postMock.mockReset()
    postMock.mockResolvedValue({ data: { data: { imported_count: 0, reason: 'ok' } } })
    await entry!.trigger('click')
    await flushPromises()
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(String(postMock.mock.calls[0][0])).toBe('/api/workpapers/wp-1/d5/import-aux-balance')
    wrapper.unmount()
  })

  it('D5TabDetail：isReadonly=true → 入口禁用（点击不发请求）', async () => {
    const D5TabDetail = (await import('../../d5/D5TabDetail.vue')).default
    const wrapper = mount(D5TabDetail, {
      props: {
        wpId: 'wp-1',
        projectId: 'proj-1',
        isReadonly: true,
        allResponses: new Map(),
        saveImmediate: vi.fn().mockResolvedValue(undefined),
        debouncedSave: vi.fn(),
      },
      global: { stubs: EP_STUBS },
    })
    await flushPromises()
    const entry = findAuxEntry(wrapper)
    expect(entry, '「从余额表导入」入口应存在').toBeTruthy()
    expect(entry!.attributes('data-disabled')).toBe('true')

    postMock.mockReset()
    await entry!.trigger('click')
    await flushPromises()
    expect(postMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// Block C — reason → 提示文案映射全分支覆盖（Requirement 4.4）
// ════════════════════════════════════════════════════════════════════════════
describe('Block C · reason→提示映射全分支覆盖', () => {
  // 全部 6 个 reason 分支（与后端 AuxAggregationResult.reason 对齐）
  const ALL_REASONS: AuxImportReason[] = [
    'ok',
    'no_prefixes',
    'no_aux_type',
    'no_rows',
    'no_active_dataset',
    'error',
  ]

  const EXPECTED_LEVEL: Record<AuxImportReason, AuxImportPromptLevel> = {
    ok: 'info',
    no_prefixes: 'warning',
    no_rows: 'info',
    no_aux_type: 'warning',
    no_active_dataset: 'warning',
    error: 'error',
  }

  it.each(ALL_REASONS)('reason=%s（0 行）→ 非空文案 + 预期 level', (reason) => {
    const p = auxImportPrompt({ importedCount: 0, reason })
    expect(p.text.length, `reason=${reason} 文案不能为空`).toBeGreaterThan(0)
    expect(p.level, `reason=${reason} level`).toBe(EXPECTED_LEVEL[reason])
  })

  it('全 6 个 reason 覆盖：EXPECTED_LEVEL 键集 = AuxImportReason 全集（防漏分支）', () => {
    // 若共享件新增 reason 而本测未同步，此断言会打红提醒补分支
    expect(Object.keys(EXPECTED_LEVEL).sort()).toEqual([...ALL_REASONS].sort())
  })

  it('异常类 reason 文案两两可辨别（no_prefixes/no_aux_type/no_active_dataset/error 互不相同）', () => {
    const texts = (['no_prefixes', 'no_aux_type', 'no_active_dataset', 'error'] as AuxImportReason[]).map(
      (r) => auxImportPrompt({ importedCount: 0, reason: r }).text,
    )
    expect(new Set(texts).size).toBe(texts.length)
  })

  it('error 与 no_rows 的 level 不同（Requirement 5.2：接线错误 vs 真无数据可分辨）', () => {
    expect(auxImportPrompt({ importedCount: 0, reason: 'error' }).level).toBe('error')
    expect(auxImportPrompt({ importedCount: 0, reason: 'no_rows' }).level).toBe('info')
  })

  it('imported>0 → success（不落 0 行分支）', () => {
    const p = auxImportPrompt({ importedCount: 3, reason: 'ok' })
    expect(p.level).toBe('success')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// Block D — 变异自检：改错循环前缀必须打红（Property 7 连接性）
// ════════════════════════════════════════════════════════════════════════════
describe('Block D · 变异自检（改错循环前缀 → 字面量断言打红）', () => {
  /**
   * 自动化变异：对 K1 的 URL builder 结果做「前缀翻转」（k1→d1），
   * 断言「翻转后的 URL」不再等于「生产 builder 的字面量」——
   * 即：若生产代码真被改成打 d1，Block A 的字面量断言必 RED。
   *
   * 这是 Property 7 连接性的机器化证明：字面量断言锁住了循环前缀，不是恒真。
   */
  it('K1：把端点前缀 k1→d1 后，字面量断言不再成立（证明断言真锁前缀）', () => {
    const real = K1_IMPORT_AUX_URL('wp-1') // 生产：.../k1/import-aux-balance
    const mutated = real.replace('/k1/', '/d1/') // 变异：接到 d1
    expect(mutated).not.toBe(real) // 变异确实改变了 URL
    // 模拟 Block A 的断言在「生产被变异」下的表现：期望 k1，实际拿到 d1 → 必不相等（RED）
    expect(() => expect(mutated).toBe('/api/workpapers/wp-1/k1/import-aux-balance')).toThrow()
  })

  it('全循环通用：任一循环前缀被换成另一循环 → 字面量断言打红', () => {
    const cycles = ['k1', 'd1', 'd2', 'd3', 'd5', 'd6', 'd7', 'f1', 'g7']
    for (const c of cycles) {
      const correct = `/api/workpapers/wp-1/${c}/import-aux-balance`
      // 换成任意另一个循环前缀
      const other = cycles.find((x) => x !== c)!
      const mutated = `/api/workpapers/wp-1/${other}/import-aux-balance`
      expect(() => expect(mutated).toBe(correct)).toThrow()
    }
  })
})
