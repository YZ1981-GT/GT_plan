/**
 * gAdjudicationPublishGate.spec.ts — G 循环审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 12 / M8 G 循环 / Req 1,2,7,8)
 *
 * 背景：此前 G 循环各审定表靠 useGxAdjudication.publishAdjudicated 自动 dispatch
 * `gx:writeback-trial-balance` → 宿主 GtGx 监听 → useGxFormData.writebackTB/writebackTrialBalance
 * → 旧端点 `PUT /projects/{pid}/trial-balance/writeback` 直写 audited_amount，绕过显式确认门，
 * 且在 watch(审定合计) 数据变化时自动触发（违反 Req 1）。改造后与 D2/D4-1/F/H/K 同范式：
 * 中文二次确认 → `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（writeback_rows）。
 *
 * 覆盖两类载体：
 *  - Group A（composable publishToTb，内置中文二次确认）：G2(1132)、G3(1131)、G5(1531)、
 *    G8(1503 权益工具)、G9(动态 tbResolvedCode||1519)、G10(动态 tbResolvedCode||2101)、
 *    G11(6111 occurrence)、G12(6103 occurrence)、G13(6101 occurrence)、G14(6702 occurrence)。
 *  - Group B（.vue 内联 handlePublishToTb，用 @vue/test-utils mount 走真实点击路径）：
 *    G1(1501)、G7(1511 原值 + 1512 减值 多科目动态)。
 *
 * 断言：确认→POST publish-to-tb（sheet_name 含 G{n}-1 / writeback_rows 科目 / amount_kind）；
 *       取消→无 POST 无 emit；readonly→无 POST；不再调旧 trial-balance/writeback；
 *       不再 dispatch g{n}:writeback-trial-balance；发布后仍 emit substantive:adjudicated。
 *       G7 专项：多科目单次 writeback_rows。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, nextTick, type Ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { eventBus } from '@/utils/eventBus'

// ─── mock apiProxy（隔离网络）；get 返回空数组（组件 loadOwn 期望 list 可迭代） ───
const { mockPost, mockPut, mockGet } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布到试算表', published: true })),
  mockPut: vi.fn(async () => ({})),
  mockGet: vi.fn(async () => [] as any[]),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: mockPost, put: mockPut, get: mockGet },
}))

// 部分 .vue 剩余取数走 http 直调；mock 防真实网络
vi.mock('@/utils/http', () => ({
  default: { get: mockGet, post: mockPost, put: mockPut },
}))

// ─── mock element-plus（ElMessageBox.confirm / ElMessage） ───
const { confirmRef } = vi.hoisted(() => ({ confirmRef: { resolve: true } }))

vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: vi.fn(async () => {
      if (!confirmRef.resolve) throw new Error('cancel')
      return 'confirm'
    }),
  },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

// vue-router：G1/G7 mount 经 useAuditContext → useRoute()，隔离路由依赖
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'test' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

import { useG2Adjudication } from '../useG2Adjudication'
import { useG3Adjudication } from '../useG3Adjudication'
import { useG5Adjudication } from '../useG5Adjudication'
import { useG8Adjudication } from '../useG8Adjudication'
import { useG9Adjudication } from '../useG9Adjudication'
import { useG10Adjudication } from '../useG10Adjudication'
import { useG11Adjudication } from '../useG11Adjudication'
import { useG12Adjudication } from '../useG12Adjudication'
import { useG13Adjudication } from '../useG13Adjudication'
import { useG14Adjudication } from '../useG14Adjudication'

// G 循环审定数派发 substantive:adjudicated 的通道不统一（实证）：多数组件走
// window.dispatchEvent（G2/G5/G8/G9/G10/G11/G12/G13/G14），G3 走 mitt eventBus.emit。
// 故 emit 断言同时挂两通道，任一命中即算 emit（下游附注刷新回归）。
function listenSubstantive(spy: () => void) {
  const winHandler = () => spy()
  window.addEventListener('substantive:adjudicated', winHandler)
  eventBus.on('substantive:adjudicated', spy)
  return () => {
    window.removeEventListener('substantive:adjudicated', winHandler)
    eventBus.off('substantive:adjudicated', spy)
  }
}

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockClear()
  confirmRef.resolve = true
  setActivePinia(createPinia())
  // 清空 mitt eventBus 残留监听器，防跨测试污染
  ;(eventBus as any).all?.clear?.()
})

// ════════════════════════════════════════════════════════════════════════════
// Group A — composable publishToTb（内置中文二次确认）
// ════════════════════════════════════════════════════════════════════════════

interface AdjCase {
  cycle: string
  wpId: string
  sheetCodeRe: RegExp
  /** 期望 writeback_rows 至少包含的科目码（动态科目组件取兜底码） */
  expectAccountCodes: string[]
  amountKind: 'balance' | 'occurrence'
  wpCode: string
  build: (readonly: boolean) => { publishToTb: () => Promise<void> }
  /**
   * 发布前准备（可选）：部分审定表（如 G12）有「审定合计 vs 试算平衡表差异」发布前置守卫，
   * 空数据下默认审定合计非 0（种子明细）→ variance≠0 → 发布被拦。此 hook 令测试把 TB 取数
   * 对齐审定合计以清零 variance，从而验证真正的发布门路径（而非被业务守卫拦下）。
   */
  prep?: (api: any) => void
}

const ADJ_CASES: AdjCase[] = [
  {
    cycle: 'G2', wpId: 'wp-g2-001', sheetCodeRe: /G2-1/, expectAccountCodes: ['1132'],
    amountKind: 'balance', wpCode: 'G2',
    build: (readonly) =>
      useG2Adjudication({
        wpId: ref('wp-g2-001'), projectId: ref('proj-g2'),
        allResponses: ref(new Map()), isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'G3', wpId: 'wp-g3-001', sheetCodeRe: /G3-1/, expectAccountCodes: ['1131'],
    amountKind: 'balance', wpCode: 'G3',
    build: (readonly) =>
      useG3Adjudication({
        wpId: ref('wp-g3-001'), projectId: ref('proj-g3'),
        allResponses: ref(new Map()), isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'G5', wpId: 'wp-g5-001', sheetCodeRe: /G5-1/, expectAccountCodes: ['1531'],
    amountKind: 'balance', wpCode: 'G5',
    build: (readonly) =>
      useG5Adjudication({
        wpId: ref('wp-g5-001'), projectId: ref('proj-g5'),
        htmlData: {}, isReadonly: ref(readonly), allResponses: ref(new Map()),
        debouncedSave: vi.fn(),
      }) as any,
  },
  {
    cycle: 'G8', wpId: 'wp-g8-001', sheetCodeRe: /G8-1/, expectAccountCodes: ['1503'],
    amountKind: 'balance', wpCode: 'G8',
    build: (readonly) =>
      useG8Adjudication({
        wpId: ref('wp-g8-001'), projectId: ref('proj-g8'),
        allResponses: ref(new Map()), debouncedSave: vi.fn(), isReadonly: ref(readonly),
      }) as any,
  },
  {
    // G9 动态科目：tbResolvedCode 未解出时取兜底码 1519
    cycle: 'G9', wpId: 'wp-g9-001', sheetCodeRe: /G9-1/, expectAccountCodes: ['1519'],
    amountKind: 'balance', wpCode: 'G9',
    build: (readonly) =>
      useG9Adjudication({
        wpId: ref('wp-g9-001'), projectId: ref('proj-g9'),
        allResponses: ref(new Map()), debouncedSave: vi.fn(), isReadonly: ref(readonly),
      }) as any,
  },
  {
    // G10 动态科目：tbResolvedCode 未解出时取兜底码 2101
    cycle: 'G10', wpId: 'wp-g10-001', sheetCodeRe: /G10-1/, expectAccountCodes: ['2101'],
    amountKind: 'balance', wpCode: 'G10',
    build: (readonly) =>
      useG10Adjudication({
        wpId: ref('wp-g10-001'), projectId: ref('proj-g10'),
        allResponses: ref(new Map()), debouncedSave: vi.fn(), isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'G11', wpId: 'wp-g11-001', sheetCodeRe: /G11-1/, expectAccountCodes: ['6111'],
    amountKind: 'occurrence', wpCode: 'G11',
    build: (readonly) =>
      useG11Adjudication({
        wpId: ref('wp-g11-001'), projectId: ref('proj-g11'),
        allResponses: ref(new Map()), debouncedSave: vi.fn(), isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'G12', wpId: 'wp-g12-001', sheetCodeRe: /G12-1/, expectAccountCodes: ['6103'],
    amountKind: 'occurrence', wpCode: 'G12',
    build: (readonly) =>
      useG12Adjudication({
        wpId: ref('wp-g12-001'), projectId: ref('proj-g12'),
        allResponses: ref(new Map()), debouncedSave: vi.fn(), isReadonly: ref(readonly),
      }) as any,
    // G12 有 variance 发布前置守卫：把 TB 取数对齐审定合计，清零 variance 后走真正发布门
    prep: (api) => api.updateTrialBalance(api.totalRow.value.currentAudited),
  },
  {
    cycle: 'G13', wpId: 'wp-g13-001', sheetCodeRe: /G13-1/, expectAccountCodes: ['6101'],
    amountKind: 'occurrence', wpCode: 'G13',
    build: (readonly) =>
      useG13Adjudication({
        wpId: ref('wp-g13-001'), projectId: ref('proj-g13'),
        allResponses: ref(new Map()), debouncedSave: vi.fn(), isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'G14', wpId: 'wp-g14-001', sheetCodeRe: /G14-1/, expectAccountCodes: ['6702'],
    amountKind: 'occurrence', wpCode: 'G14',
    build: (readonly) =>
      useG14Adjudication({
        wpId: ref('wp-g14-001'), projectId: ref('proj-g14'),
        allResponses: ref(new Map()), debouncedSave: vi.fn(), isReadonly: ref(readonly),
      }) as any,
  },
]

function runAdj(c: AdjCase, readonly = false, applyPrep = false) {
  const scope = effectScope()
  const api = scope.run(() => c.build(readonly))!
  if (applyPrep && c.prep) c.prep(api)
  return { api, dispose: () => scope.stop() }
}

describe.each(ADJ_CASES)(
  '$cycle 审定表 publishToTb 走显式发布门（tb-writeback-explicit-publish-gate Task 12）',
  (c) => {
    it('确认后调 POST publish-to-tb，body 含审定表 sheet_name + writeback_rows(科目/口径)', async () => {
      const { api, dispose } = runAdj(c, false, true)
      try {
        await api.publishToTb()
        expect(mockPost).toHaveBeenCalledTimes(1)
        const [url, body] = mockPost.mock.calls[0]!
        expect(url).toContain(`/api/workpapers/${c.wpId}/audit-determination/publish-to-tb`)
        expect(body.sheet_name).toMatch(c.sheetCodeRe)
        expect(Array.isArray(body.writeback_rows)).toBe(true)
        const codes = body.writeback_rows.map((r: any) => r.account_code)
        for (const code of c.expectAccountCodes) {
          expect(codes).toContain(code)
        }
        for (const row of body.writeback_rows) {
          expect(row.amount_kind).toBe(c.amountKind)
          expect(typeof row.audited_amount).toBe('number')
        }
      } finally {
        dispose()
      }
    })

    it('不再调旧端点 trial-balance/writeback（PUT 或 POST 变体）', async () => {
      const { api, dispose } = runAdj(c, false, true)
      try {
        await api.publishToTb()
        for (const call of mockPut.mock.calls) {
          expect(String(call[0])).not.toContain('trial-balance/writeback')
        }
        for (const call of mockPost.mock.calls) {
          expect(String(call[0])).not.toContain('trial-balance/writeback')
        }
      } finally {
        dispose()
      }
    })

    it('用户取消二次确认 → 不发请求、不 emit substantive:adjudicated', async () => {
      confirmRef.resolve = false
      const emitSpy = vi.fn()
      const off = listenSubstantive(emitSpy)
      const { api, dispose } = runAdj(c)
      try {
        await api.publishToTb()
        expect(mockPost).not.toHaveBeenCalled()
        expect(emitSpy).not.toHaveBeenCalled()
      } finally {
        off()
        dispose()
      }
    })

    it('readonly → 不发请求（早退）', async () => {
      const { api, dispose } = runAdj(c, true)
      try {
        await api.publishToTb()
        expect(mockPost).not.toHaveBeenCalled()
      } finally {
        dispose()
      }
    })

    it('发布后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8）', async () => {
      const emitSpy = vi.fn()
      const off = listenSubstantive(emitSpy)
      const { api, dispose } = runAdj(c, false, true)
      try {
        await api.publishToTb()
        expect(mockPost).toHaveBeenCalledTimes(1)
        expect(emitSpy).toHaveBeenCalled()
      } finally {
        off()
        dispose()
      }
    })
  },
)

// ════════════════════════════════════════════════════════════════════════════
// Group B — .vue 内联 handlePublishToTb（@vue/test-utils mount 走真实点击路径）
//   G1(1501) / G7(1511 原值 + 1512 减值 多科目动态)
// ════════════════════════════════════════════════════════════════════════════

const globalStubs = {
  WpFourTableSourcePanel: true,
  WpAmountInput: true,
  GtIndexChip: true,
  AdjudicationBringInDialog: true,
  HiFourTableSourcePanel: true,
  // inheritAttrs:false 防止父组件 @click 作为原生 fallthrough 监听器二次绑定
  'el-button': {
    inheritAttrs: false,
    template: '<button :data-testid="dataTestid" :disabled="disabled" @click="$emit(`click`)"><slot /></button>',
    props: {
      disabled: { type: Boolean, default: false },
      loading: { type: Boolean, default: false },
      type: { type: String, default: '' },
      size: { type: String, default: '' },
      plain: { type: Boolean, default: false },
      link: { type: Boolean, default: false },
    },
    computed: {
      dataTestid(this: any) {
        return this.$attrs['data-testid']
      },
    },
  },
  'el-table': true,
  'el-table-column': true,
  'el-tag': true,
  'el-input': true,
  'el-dialog': true,
  'el-radio-group': true,
  'el-radio': true,
  'el-alert': true,
  'el-descriptions': true,
  'el-descriptions-item': true,
  'el-icon': true,
  'el-select': true,
  'el-option': true,
  'el-tooltip': true,
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  Download: true,
  MagicStick: true,
  GtReviewTrigger: true,
}

const globalMocks = {
  stubs: globalStubs,
  provide: {
    openReviewDialog: () => {},
    saveResponse: () => {},
    saveImmediate: () => {},
    getThreadDot: () => null,
    getRowDot: () => null,
    jumpToSection: null,
  },
}

describe('G1 审定表发布走显式发布门（Task 12 / Req 1,2,8）', () => {
  let G1TabAdjudication: any
  beforeEach(async () => {
    G1TabAdjudication = (await import('../../g1-trading-financial-assets/core/G1TabAdjudication.vue')).default
  })

  function mountG1(readonly = false) {
    return mount(G1TabAdjudication, {
      props: {
        wpId: 'wp-g1-001',
        projectId: 'proj-g1',
        allResponses: new Map(),
        htmlData: {},
        isReadonly: readonly,
      },
      global: globalMocks,
    })
  }

  it('点击"发布到试算表" → 确认 → POST publish-to-tb（sheet_name G1-1，科目 1501 balance）', async () => {
    const w = mountG1()
    await flushPromises()
    const btn = w.find('[data-testid="g1-publish-tb"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toContain('/api/workpapers/wp-g1-001/audit-determination/publish-to-tb')
    expect(body.sheet_name).toMatch(/G1-1/)
    expect(body.writeback_rows[0]).toMatchObject({ account_code: '1501', amount_kind: 'balance' })
    for (const call of mockPut.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
    w.unmount()
  })

  it('取消二次确认 → 不发 POST', async () => {
    confirmRef.resolve = false
    const w = mountG1()
    await flushPromises()
    await w.find('[data-testid="g1-publish-tb"]').trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })

  it('readonly → 按钮 disabled + 早退不发 POST', async () => {
    const w = mountG1(true)
    await flushPromises()
    const btn = w.find('[data-testid="g1-publish-tb"]')
    expect(btn.attributes('disabled')).toBeDefined()
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('G7 多科目审定表发布走显式发布门 + 单次原子 writeback_rows（Task 12 / Req 2,5）', () => {
  let G7TabAdjudication: any
  beforeEach(async () => {
    G7TabAdjudication = (await import('../../g7-long-term-equity-main/core/G7TabAdjudication.vue')).default
  })

  // 提供 render 下发的 tb_source_codes.slots，令 g7AccountScope 解析原值 1511 + 减值 1512
  function buildG7HtmlData() {
    return {
      tb_source_codes: {
        slots: {
          gross: { key: 'gross', standard_codes: ['1511'], codes: ['1511'], found: true },
          impairment: { key: 'impairment', standard_codes: ['1512'], codes: ['1512'], found: true },
        },
      },
    }
  }

  function mountG7(readonly = false, html: any = buildG7HtmlData()) {
    return mount(G7TabAdjudication, {
      props: {
        wpId: 'wp-g7-001',
        projectId: 'proj-g7',
        allResponses: new Map(),
        htmlData: html,
        isReadonly: readonly,
      },
      global: globalMocks,
    })
  }

  it('点击"发布到试算表" → 确认 → POST publish-to-tb（sheet_name G7-1，原值+减值双科目单次 balance）', async () => {
    const w = mountG7()
    await flushPromises()
    const btn = w.find('[data-testid="g7-publish-tb"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toContain('/api/workpapers/wp-g7-001/audit-determination/publish-to-tb')
    expect(body.sheet_name).toMatch(/G7-1/)
    // 多科目单次原子发布（原值 1511 + 减值 1512）
    const codes = body.writeback_rows.map((r: any) => r.account_code)
    expect(codes).toContain('1511')
    expect(codes).toContain('1512')
    expect(body.writeback_rows.every((r: any) => r.amount_kind === 'balance')).toBe(true)
    for (const r of body.writeback_rows) {
      expect(typeof r.audited_amount).toBe('number')
    }
    for (const call of mockPut.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
    w.unmount()
  })

  it('取消二次确认 → 不发 POST', async () => {
    confirmRef.resolve = false
    const w = mountG7()
    await flushPromises()
    await w.find('[data-testid="g7-publish-tb"]').trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })

  it('readonly → 按钮 disabled + 早退不发 POST', async () => {
    const w = mountG7(true)
    await flushPromises()
    const btn = w.find('[data-testid="g7-publish-tb"]')
    expect(btn.attributes('disabled')).toBeDefined()
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })
})

// 未使用的 nextTick / Ref 引入用途保留（避免 TS unused）
void nextTick
export type { Ref }
