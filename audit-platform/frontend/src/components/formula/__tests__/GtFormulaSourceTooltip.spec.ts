/**
 * GtFormulaSourceTooltip.spec.ts — 统一公式来源悬停提示 示例 + 属性测试
 *
 * spec formula-management-library Task 12.5（组件由 Task 12.2 实现）
 *
 * 覆盖：
 *  - Req 10.1：虚线下划线 + cursor:help 样式标识（`.formula-cell` / `--plain`）
 *  - Req 10.2：悬停展示三要素（公式表达式 + 来源地址 + 最近计算时间）
 *  - Req 10.3：底稿 / 报表 / 附注三处统一挂载 —— 同一组件、同一渲染结构
 *  - Req 10.4：未计算过（无 last_computed_at）显示"尚未计算"占位而非空白
 *  - **Property 14: 来源提示地址保真（前端侧）**
 *      来源地址取 full_resolve 返回的 canonical semantic_label，而非前端拼接坐标串
 *
 * **Validates: Requirements 10.5**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import * as fc from 'fast-check'

// ─── ResizeObserver polyfill（Element Plus 部分组件在 jsdom 下需要） ────────────
if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// ─── Mock useAcnr（受控 resolveAddr / resolveFormula，返回带 semantic_label） ───
const mockResolveAddr = vi.fn()
const mockResolveFormula = vi.fn()

vi.mock('@/services/acnr/useAcnr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/acnr/useAcnr')>()
  return {
    ...actual, // 保留类型导出
    useAcnr: () => ({
      resolveAddr: mockResolveAddr,
      resolveFormula: mockResolveFormula,
      listSheets: vi.fn(),
      listCells: vi.fn(),
      resolveUri: vi.fn(),
      resolveIndex: vi.fn(),
      resolveInstance: vi.fn(),
      buildAddressTree: vi.fn(),
      loadCellNodes: vi.fn(),
      clearCache: vi.fn(),
    }),
  }
})

// ─── Import after mocks ───────────────────────────────────────────────────────
import ElementPlus from 'element-plus'
import GtFormulaSourceTooltip from '../GtFormulaSourceTooltip.vue'

// ─── ElTooltip stub（内联渲染 content + default 插槽，可驱动 before-show） ──────
// 真实 ElTooltip 用 teleport 渲染浮层，jsdom 下难以驱动；stub 后 content 始终内联，
// 且透传 @before-show 事件 —— 这样可断言 tooltip 三要素内容并触发懒解析（Req 10.5）。
const ElTooltipStub = defineComponent({
  name: 'ElTooltip',
  emits: ['before-show'],
  template:
    '<div class="el-tooltip-stub">' +
    '<div class="tt-content"><slot name="content" /></div>' +
    '<slot />' +
    '</div>',
})

const STUBS = { ElTooltip: ElTooltipStub } as const

function mountTooltip(props: Record<string, unknown> = {}): VueWrapper {
  return mount(GtFormulaSourceTooltip, {
    props,
    slots: { default: '<span class="cell-val">1,234.56</span>' },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

/** 触发悬停展开前的懒解析（@before-show="handleBeforeShow"） */
async function triggerBeforeShow(wrapper: VueWrapper) {
  wrapper.findComponent(ElTooltipStub).vm.$emit('before-show')
  await flushPromises()
  await nextTick()
}

// ══════════════════════════════════════════════════════════════════════════════
describe('GtFormulaSourceTooltip — 统一来源提示（Req 10.1~10.5）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockResolveAddr.mockResolvedValue({ found: true, semantic_label: '默认来源' })
    mockResolveFormula.mockResolvedValue({ found: true, semantic_label: '默认来源' })
  })

  // ── Req 10.1：虚线下划线 + cursor:help ──────────────────────────────────────
  describe('Req 10.1 — 虚线下划线 + cursor:help 样式标识', () => {
    it('默认以 .formula-cell 类标识公式单元（承载虚线下划线 + cursor:help 样式）', () => {
      const wrapper = mountTooltip({ expression: '= 期初 + 增加 - 减少' })
      const cell = wrapper.find('.formula-cell')
      expect(cell.exists()).toBe(true)
      // 未启用 plain → 带虚线下划线的默认样式类
      expect(cell.classes()).not.toContain('formula-cell--plain')
      // slot 内容被 formula-cell 包裹
      expect(cell.find('.cell-val').exists()).toBe(true)
      wrapper.unmount()
    })

    it('plain=true 时切换到 --plain 变体（无下划线，仅保留 cursor:help）', () => {
      const wrapper = mountTooltip({ expression: '=SUM(A1:A2)', plain: true })
      const cell = wrapper.find('.formula-cell')
      expect(cell.exists()).toBe(true)
      expect(cell.classes()).toContain('formula-cell--plain')
      wrapper.unmount()
    })
  })

  // ── Req 10.2：悬停三要素 ────────────────────────────────────────────────────
  describe('Req 10.2 — 悬停展示 表达式 + 来源地址 + 最近计算时间', () => {
    it('tooltip 内容包含三要素标签与对应值', async () => {
      const wrapper = mountTooltip({
        expression: '= 期初 + 增加 - 减少',
        sourceLabel: 'D2 应收账款明细表 · 期末余额',
        lastComputedAt: '2025-01-15T06:30:00',
      })
      const content = wrapper.find('.tt-content')
      const text = content.text()
      // 三要素标签
      expect(text).toContain('公式表达式')
      expect(text).toContain('来源地址')
      expect(text).toContain('最近计算')
      // 三要素值
      expect(text).toContain('= 期初 + 增加 - 减少')
      expect(text).toContain('D2 应收账款明细表 · 期末余额')
      // 最近计算时间已格式化（非"尚未计算"占位）
      expect(text).not.toContain('尚未计算')
      wrapper.unmount()
    })

    it('未定义表达式时显示占位而非空白', () => {
      const wrapper = mountTooltip({ expression: null, sourceLabel: '某来源' })
      expect(wrapper.find('.tt-content').text()).toContain('（未定义表达式）')
      wrapper.unmount()
    })
  })

  // ── Req 10.4："尚未计算"占位 ────────────────────────────────────────────────
  describe('Req 10.4 — 无最近计算时间显示"尚未计算"占位', () => {
    it('lastComputedAt 为空 → 显示"尚未计算"', () => {
      const wrapper = mountTooltip({ expression: '=A1+A2', sourceLabel: '来源', lastComputedAt: null })
      expect(wrapper.find('.tt-content').text()).toContain('尚未计算')
      expect((wrapper.vm as any).hasComputed).toBe(false)
      wrapper.unmount()
    })

    it('lastComputedAt 有值 → 不显示占位', () => {
      const wrapper = mountTooltip({
        expression: '=A1+A2',
        sourceLabel: '来源',
        lastComputedAt: '2025-06-01T10:00:00Z',
      })
      expect((wrapper.vm as any).hasComputed).toBe(true)
      expect(wrapper.find('.tt-content').text()).not.toContain('尚未计算')
      wrapper.unmount()
    })
  })

  // ── Req 10.3：三处统一挂载 ──────────────────────────────────────────────────
  describe('Req 10.3 — 底稿 / 报表 / 附注三处统一挂载（同组件同结构）', () => {
    // 三处典型用法各自的 props（差异仅在数据，不在组件/结构）
    const contexts = [
      { name: '底稿表格', props: { expression: '= 期初 + 增加 - 减少', sourceLabel: 'D2 明细表 · 期末余额', lastComputedAt: '2025-01-15T06:30:00' } },
      { name: '报表', props: { expression: '= 流动资产合计', sourceLabel: '资产负债表 · 流动资产合计', lastComputedAt: '2025-01-15T06:30:00' } },
      { name: '附注', props: { expression: '= 应收账款账面价值', sourceLabel: '附注五 · 应收账款', lastComputedAt: '2025-01-15T06:30:00' } },
    ]

    it('三处渲染结构一致：均有 .formula-cell + 三要素行', () => {
      for (const ctx of contexts) {
        const wrapper = mountTooltip(ctx.props)
        expect(wrapper.find('.formula-cell').exists()).toBe(true)
        // 三要素行数量一致（3 行）
        expect(wrapper.findAll('.gt-formula-source__row')).toHaveLength(3)
        const text = wrapper.find('.tt-content').text()
        expect(text).toContain('公式表达式')
        expect(text).toContain('来源地址')
        expect(text).toContain('最近计算')
        wrapper.unmount()
      }
    })
  })

  // ── Req 10.5：来源地址取 full_resolve semantic_label（非前端拼接） ───────────
  describe('Req 10.5 — 来源地址取 full_resolve semantic_label', () => {
    it('父级已提供 sourceLabel 时直接使用，不触发前端 resolve', async () => {
      const wrapper = mountTooltip({ addrId: 'D2/D2-2/E100', sourceLabel: '期末余额（父级已解析）' })
      await triggerBeforeShow(wrapper)
      // 有 sourceLabel → 短路，不调 resolve
      expect(mockResolveAddr).not.toHaveBeenCalled()
      expect(wrapper.find('.tt-content').text()).toContain('期末余额（父级已解析）')
      wrapper.unmount()
    })

    it('仅给 addrId 时，悬停前经 resolveAddr 取 semantic_label 作来源地址', async () => {
      mockResolveAddr.mockResolvedValue({ found: true, semantic_label: 'D2 应收账款明细表 · 期末余额' })
      const wrapper = mountTooltip({ expression: '=A1+A2', addrId: 'D2/D2-2/E100' })
      await triggerBeforeShow(wrapper)

      expect(mockResolveAddr).toHaveBeenCalledWith('D2/D2-2/E100')
      const text = wrapper.find('.tt-content').text()
      // 展示 canonical semantic_label
      expect(text).toContain('D2 应收账款明细表 · 期末余额')
      // 关键：不展示前端拼接的坐标串（addr_id 原文）
      expect(text).not.toContain('D2/D2-2/E100')
      wrapper.unmount()
    })

    it('addrId 缺失时以 formulaRef 经 resolveFormula 取 semantic_label', async () => {
      mockResolveFormula.mockResolvedValue({ found: true, semantic_label: '货币资金合计' })
      const wrapper = mountTooltip({
        expression: '=SUM(...)',
        formulaRef: "WP('E1','E1-1','B10')",
      })
      await triggerBeforeShow(wrapper)

      expect(mockResolveFormula).toHaveBeenCalledWith("WP('E1','E1-1','B10')")
      const text = wrapper.find('.tt-content').text()
      expect(text).toContain('货币资金合计')
      // 不展示公式引用原文作为来源地址
      expect(text).not.toContain("WP('E1','E1-1','B10')")
      wrapper.unmount()
    })

    it('resolve 未命中（found=false）时退回"（未知来源）"占位，不拼接坐标', async () => {
      mockResolveAddr.mockResolvedValue({ found: false, error: 'miss' })
      const wrapper = mountTooltip({ expression: '=A1', addrId: 'X/Y/Z1' })
      await triggerBeforeShow(wrapper)
      const text = wrapper.find('.tt-content').text()
      expect(text).toContain('（未知来源）')
      expect(text).not.toContain('X/Y/Z1')
      wrapper.unmount()
    })
  })

  // ══════════════════════════════════════════════════════════════════════════
  // Property 14 — 来源提示地址保真（前端侧）
  //   对任意由公式产生的单元，tooltip 显示的来源地址 == full_resolve 返回的
  //   canonical semantic_label，而非前端自行拼接的坐标字符串（addr_id 原文）。
  //   **Validates: Requirements 10.5**
  // ══════════════════════════════════════════════════════════════════════════
  describe('Property 14 — tooltip 来源地址 == full_resolve semantic_label（非坐标拼接）', () => {
    // addr_id：{wp_code}/{sheet_code}/{coordinate}，均为坐标性 token
    const addrIdArb = fc
      .tuple(
        fc.tuple(fc.constantFrom(...'ABCDEFGHIJKLMNS'.split('')), fc.integer({ min: 1, max: 99 })).map(([l, n]) => `${l}${n}`),
        fc.integer({ min: 1, max: 20 }),
        fc.tuple(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')), fc.integer({ min: 1, max: 9999 })).map(([c, r]) => `${c}${r}`),
      )
      .map(([wp, sheetN, cell]) => `${wp}/${wp}-${sheetN}/${cell}`)

    // canonical semantic_label：带中文标记前缀，确保与坐标拼接串可区分
    const semanticLabelArb = fc
      .array(fc.constantFrom(...'应收账款期末余额合计流动资产货币资金存货成本毛利'.split('')), {
        minLength: 2,
        maxLength: 8,
      })
      .map((a) => `名称·${a.join('')}`)

    it('对任意 addr_id + semantic_label：显示 semantic_label 且从不显示 addr_id 坐标串', async () => {
      await fc.assert(
        fc.asyncProperty(addrIdArb, semanticLabelArb, async (addrId, semanticLabel) => {
          mockResolveAddr.mockResolvedValue({ found: true, addr_id: addrId, semantic_label: semanticLabel })
          const wrapper = mountTooltip({ expression: '=公式', addrId })
          try {
            await triggerBeforeShow(wrapper)
            // 保真：来源地址恰为 full_resolve 返回的 semantic_label
            expect((wrapper.vm as any).displaySource).toBe(semanticLabel)
            const text = wrapper.find('.tt-content').text()
            expect(text).toContain(semanticLabel)
            // 反面：绝不出现前端拼接的 addr_id 坐标原文
            expect(text).not.toContain(addrId)
          } finally {
            wrapper.unmount()
          }
        }),
        { numRuns: 25 },
      )
    })
  })
})
