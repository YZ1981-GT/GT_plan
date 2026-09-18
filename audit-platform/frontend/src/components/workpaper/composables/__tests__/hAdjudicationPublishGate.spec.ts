/**
 * hAdjudicationPublishGate.spec.ts — H 循环审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 10 / M7 H 循环 / Req 1,2,5,6,8)
 *
 * 背景：此前 H 循环各审定表直调旧端点 `PUT /projects/{pid}/trial-balance/writeback`
 * （H3 是 1.5s debounce 自动写、H10 是 mount/debounce/跨wp 自动写、H6 是只 emit 不写的假回写），
 * 绕过显式确认门。改造后与 D2/D4-1/F/K 同范式：中文二次确认 →
 * `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（writeback_rows）。
 *
 * 覆盖两类载体：
 *  - Group A（composable publishToTb，内置中文二次确认）：H1(1601/1602/1603 多科目)、H2(1604)、
 *    H4(1605)、H5(1631/1632 多科目)、H6(1606 补真回写)、H10(6115 occurrence)。
 *  - Group B（.vue 内联 handlePublish/publishToTb，用 @vue/test-utils mount 走真实点击路径）：
 *    H3(grossCode/accumDepCode 动态 + 🔴防跨循环污染)、H7 Cost(1621)、H7 Fair(1621)。
 *
 * 断言：确认→POST publish-to-tb（sheet_name 含 H{n}-1 / writeback_rows 科目 / amount_kind）；
 *       取消→无 POST 无 emit；readonly→无 POST；不再调旧 trial-balance/writeback；发布后仍
 *       emit substantive:adjudicated。H1/H5 专项：多科目单次 writeback_rows；H10 专项：occurrence；
 *       🔴 H3 专项：本项目无该科目 → writeback_rows 不含该行（防污染）。
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

// H1/H2 .vue 用 http 直调（回写已迁移，剩余 AI/取数走 http）；mock 防真实网络
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

// vue-router：H3/H7 mount 经 useAuditContext → useRoute()，隔离路由依赖
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'test' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

import { useH1Adjudication } from '../useH1Adjudication'
import { useH2Adjudication } from '../useH2Adjudication'
import { useH4Adjudication } from '../useH4Adjudication'
import { useH5Adjudication } from '../useH5Adjudication'
import { useH6Adjudication } from '../useH6Adjudication'
import { useH10Adjudication } from '../useH10Adjudication'

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockClear()
  confirmRef.resolve = true
  setActivePinia(createPinia())
  // 清空 mitt eventBus 残留监听器，防跨测试污染（组件/composable 的 eventBus.on 不随 effectScope 清理）
  ;(eventBus as any).all?.clear?.()
})

// ════════════════════════════════════════════════════════════════════════════
// Group A — composable publishToTb（内置中文二次确认）
// ════════════════════════════════════════════════════════════════════════════

interface AdjCase {
  cycle: string
  wpId: string
  sheetCodeRe: RegExp
  /** 期望 writeback_rows 至少包含的科目码 */
  expectAccountCodes: string[]
  amountKind: 'balance' | 'occurrence'
  wpCode: string
  /** 构建 composable（readonly 可控），返回带 publishToTb 的实例 */
  build: (readonly: boolean) => { publishToTb: () => Promise<void> }
}

const ADJ_CASES: AdjCase[] = [
  {
    cycle: 'H1', wpId: 'wp-h1-001', sheetCodeRe: /H1-1/, expectAccountCodes: ['1601', '1602', '1603'],
    amountKind: 'balance', wpCode: 'H1',
    build: (readonly) =>
      useH1Adjudication(ref('wp-h1-001'), ref('proj-h1'), ref(new Map()), {
        onPublishEvent: (event, payload) => eventBus.emit(event as any, payload),
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'H2', wpId: 'wp-h2-001', sheetCodeRe: /H2-1/, expectAccountCodes: ['1604'],
    amountKind: 'balance', wpCode: 'H2',
    build: (readonly) =>
      useH2Adjudication({
        wpId: ref('wp-h2-001'),
        projectId: ref('proj-h2'),
        allResponses: ref(new Map()),
        isReadonly: ref(readonly),
        onPublishEvent: (event, payload) => eventBus.emit(event as any, payload),
      }) as any,
  },
  {
    cycle: 'H4', wpId: 'wp-h4-001', sheetCodeRe: /H4-1/, expectAccountCodes: ['1605'],
    amountKind: 'balance', wpCode: 'H4',
    build: (readonly) =>
      useH4Adjudication({
        wpId: ref('wp-h4-001'),
        projectId: ref('proj-h4'),
        allResponses: ref(new Map()),
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'H5', wpId: 'wp-h5-001', sheetCodeRe: /H5-1/, expectAccountCodes: ['1631', '1632'],
    amountKind: 'balance', wpCode: 'H5',
    build: (readonly) =>
      useH5Adjudication({
        allResponses: ref(new Map()),
        wpId: ref('wp-h5-001'),
        projectId: ref('proj-h5'),
        isReadonly: ref(readonly),
        onPublishEvent: (event, payload) => eventBus.emit(event as any, payload),
      }) as any,
  },
  {
    cycle: 'H6', wpId: 'wp-h6-001', sheetCodeRe: /H6-1/, expectAccountCodes: ['1606'],
    amountKind: 'balance', wpCode: 'H6',
    build: (readonly) =>
      useH6Adjudication({
        wpId: ref('wp-h6-001'),
        projectId: ref('proj-h6'),
        allResponses: ref(new Map()),
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'H10', wpId: 'wp-h10-001', sheetCodeRe: /H10-1/, expectAccountCodes: ['6115'],
    amountKind: 'occurrence', wpCode: 'H10',
    build: (readonly) =>
      useH10Adjudication({
        wpId: ref('wp-h10-001'),
        projectId: ref('proj-h10'),
        allResponses: ref(new Map()),
        debouncedSave: vi.fn(),
        isReadonly: ref(readonly),
      }) as any,
  },
]

function runAdj(c: AdjCase, readonly = false) {
  const scope = effectScope()
  const api = scope.run(() => c.build(readonly))!
  return { api, dispose: () => scope.stop() }
}

describe.each(ADJ_CASES)(
  '$cycle 审定表 publishToTb 走显式发布门（tb-writeback-explicit-publish-gate Task 10）',
  (c) => {
    it('确认后调 POST publish-to-tb，body 含审定表 sheet_name + writeback_rows(科目/口径)', async () => {
      const { api, dispose } = runAdj(c)
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
      const { api, dispose } = runAdj(c)
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
      eventBus.on('substantive:adjudicated', emitSpy)
      const { api, dispose } = runAdj(c)
      try {
        await api.publishToTb()
        expect(mockPost).not.toHaveBeenCalled()
        expect(emitSpy).not.toHaveBeenCalled()
      } finally {
        eventBus.off('substantive:adjudicated', emitSpy)
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
      eventBus.on('substantive:adjudicated', emitSpy)
      const { api, dispose } = runAdj(c)
      try {
        await api.publishToTb()
        expect(mockPost).toHaveBeenCalledTimes(1)
        expect(emitSpy).toHaveBeenCalled()
        const payload = emitSpy.mock.calls[0][0] as { wpCode?: string; wp_code?: string }
        expect(payload.wpCode ?? payload.wp_code).toBe(c.wpCode)
      } finally {
        eventBus.off('substantive:adjudicated', emitSpy)
        dispose()
      }
    })
  },
)

describe('H1 多科目在单次 writeback_rows 原子发布（Task 10 / Req 5）', () => {
  it('1601 + 1602 + 1603 同在一次 POST', async () => {
    const scope = effectScope()
    try {
      const api = scope.run(() =>
        useH1Adjudication(ref('wp-h1-002'), ref('proj-h1'), ref(new Map()), {
          onPublishEvent: () => {},
          isReadonly: ref(false),
        }),
      )!
      await api.publishToTb()
      expect(mockPost).toHaveBeenCalledTimes(1)
      const body = mockPost.mock.calls[0]![1]
      expect(body.writeback_rows).toHaveLength(3)
      const codes = body.writeback_rows.map((r: any) => r.account_code)
      expect(codes).toEqual(['1601', '1602', '1603'])
    } finally {
      scope.stop()
    }
  })
})

describe('H5 双科目在单次 writeback_rows 原子发布（Task 10 / Req 5）', () => {
  it('1631 + 1632 同在一次 POST', async () => {
    const scope = effectScope()
    try {
      const api = scope.run(() =>
        useH5Adjudication({
          allResponses: ref(new Map()),
          wpId: ref('wp-h5-002'),
          projectId: ref('proj-h5'),
          isReadonly: ref(false),
          onPublishEvent: () => {},
        }),
      )!
      await api.publishToTb()
      expect(mockPost).toHaveBeenCalledTimes(1)
      const body = mockPost.mock.calls[0]![1]
      expect(body.writeback_rows).toHaveLength(2)
      const codes = body.writeback_rows.map((r: any) => r.account_code)
      expect(codes).toEqual(['1631', '1632'])
    } finally {
      scope.stop()
    }
  })
})

describe('H10 损益类发生额发布 amount_kind=occurrence（Task 10 / Req 6）', () => {
  it('6115 单行 occurrence', async () => {
    const scope = effectScope()
    try {
      const api = scope.run(() =>
        useH10Adjudication({
          wpId: ref('wp-h10-002'),
          projectId: ref('proj-h10'),
          allResponses: ref(new Map()),
          debouncedSave: vi.fn(),
          isReadonly: ref(false),
        }),
      )!
      await api.publishToTb()
      expect(mockPost).toHaveBeenCalledTimes(1)
      const body = mockPost.mock.calls[0]![1]
      expect(body.writeback_rows).toHaveLength(1)
      expect(body.writeback_rows[0]).toMatchObject({ account_code: '6115', amount_kind: 'occurrence' })
    } finally {
      scope.stop()
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
// Group B — .vue 内联 handlePublish（@vue/test-utils mount 走真实点击路径）
// ════════════════════════════════════════════════════════════════════════════

// 隔离子组件/依赖：H3/H7 用大量 el-* + 自定义组件，用 shallow stub
const globalStubs = {
  WpFourTableSourcePanel: true,
  WpAmountInput: true,
  GtIndexChip: true,
  AdjudicationBringInDialog: true,
  HiFourTableSourcePanel: true,
  // inheritAttrs:false 防止父组件 @click 作为原生 fallthrough 监听器二次绑定（否则触发一次点击会调 2 次）
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
    h10Amount: ref(0),
  },
}

// H3 htmlData 含 tb_source_codes.slots：h3AccountScope 用 slots[key].standard_codes + found 解析。
// 🔴 防污染语义（与源码一致）：
//   - gross(原值)：h3AccountScope.accountCode 无 isAccountAbsent 检查 + queryCodes 有 fallback '1521'
//     ⇒ gross 恒解出至少兜底码 1521（1521 是 H3 本循环科目族，非别循环码，写它不污染他循环）。
//   - accumDep(累计折旧备抵)：源码 `isAccountAbsent ? '' : accountCode` ⇒ found=false 时为空串 → 跳过该行。
//     这正是防跨循环污染硬约束的落点（缺备抵科目则不写该行，宁缺勿造）。
function buildH3HtmlData(hasAccumDep = true) {
  const slots: Record<string, any> = {
    gross: { key: 'gross', standard_codes: ['1521'], codes: ['1521'], found: true },
  }
  // accumDep 缺失 → found:false + 空 codes ⇒ isAccountAbsent=true ⇒ 该行被跳过（防污染）
  slots.accum_dep = hasAccumDep
    ? { key: 'accum_dep', standard_codes: ['1525'], codes: ['1525'], found: true }
    : { key: 'accum_dep', standard_codes: [], codes: [], found: false }
  return { tb_source_codes: { slots } }
}

describe('H3 审定表发布走显式发布门 + 🔴 防跨循环污染（Task 10 / Req 1,2,8）', () => {
  let H3TabAdjudicationCost: any
  beforeEach(async () => {
    H3TabAdjudicationCost = (await import('../../h3/core/H3TabAdjudicationCost.vue')).default
  })

  function mountH3(readonly = false, html: any = buildH3HtmlData()) {
    return mount(H3TabAdjudicationCost, {
      props: {
        wpId: 'wp-h3-001',
        projectId: 'proj-h3',
        allResponses: new Map(),
        htmlData: html,
        isReadonly: readonly,
      },
      global: globalMocks,
    })
  }

  it('点击"发布到试算表" → 确认 → POST publish-to-tb（sheet_name H3-1，两科目 balance）', async () => {
    const w = mountH3()
    await flushPromises()
    const btn = w.find('[data-testid="h3-publish-tb"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toContain('/api/workpapers/wp-h3-001/audit-determination/publish-to-tb')
    expect(body.sheet_name).toMatch(/H3-1/)
    const codes = body.writeback_rows.map((r: any) => r.account_code)
    expect(codes).toContain('1521') // gross 原值
    expect(codes).toContain('1525') // accumDep 累计折旧
    expect(body.writeback_rows.every((r: any) => r.amount_kind === 'balance')).toBe(true)
    // 不再调旧端点
    for (const call of mockPut.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
    w.unmount()
  })

  it('🔴 防污染：本项目无累计折旧科目（found=false）→ writeback_rows 不含该行（宁缺勿造）', async () => {
    const w = mountH3(false, buildH3HtmlData(false))
    await flushPromises()
    await w.find('[data-testid="h3-publish-tb"]').trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const body = mockPost.mock.calls[0]![1]
    const codes = body.writeback_rows.map((r: any) => r.account_code)
    // 只含 gross（1521 H3 本循环族），不含缺失的累计折旧 1525 —— 绝不误写其他循环科目
    expect(codes).toContain('1521')
    expect(codes).not.toContain('1525')
    expect(body.writeback_rows).toHaveLength(1)
    w.unmount()
  })

  it('取消二次确认 → 不发 POST', async () => {
    confirmRef.resolve = false
    const w = mountH3()
    await flushPromises()
    await w.find('[data-testid="h3-publish-tb"]').trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })

  it('readonly → 按钮 disabled + publishToTb 早退不发 POST', async () => {
    const w = mountH3(true)
    await flushPromises()
    const btn = w.find('[data-testid="h3-publish-tb"]')
    // H3 发布按钮在工具栏（无 v-if 包裹），readonly 下 :disabled 生效
    expect(btn.attributes('disabled')).toBeDefined()
    // 即使触发点击，publishToTb 的 props.isReadonly 早退保证不发 POST
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('H7 Cost/Fair 审定表发布走显式发布门（Task 10 / Req 1,2,8）', () => {
  interface H7Case {
    name: string
    testid: string
    load: () => Promise<any>
  }
  const H7_CASES: H7Case[] = [
    { name: 'H7 Cost', testid: 'h7-cost-publish-tb', load: async () => (await import('../../h7/core/H7TabAdjudicationCost.vue')).default },
    { name: 'H7 Fair', testid: 'h7-fair-publish-tb', load: async () => (await import('../../h7/core/H7TabAdjudicationFair.vue')).default },
  ]

  function mountH7(comp: any, readonly = false) {
    return mount(comp, {
      props: {
        wpId: 'wp-h7-001',
        projectId: 'proj-h7',
        allResponses: new Map(),
        isReadonly: readonly,
      },
      global: globalMocks,
    })
  }

  it.each(H7_CASES)('$name 点击发布 → 确认 → POST publish-to-tb（H7-1 / 1621 balance）', async (c) => {
    const comp = await c.load()
    const w = mountH7(comp)
    await flushPromises()
    const btn = w.find(`[data-testid="${c.testid}"]`)
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toContain('/api/workpapers/wp-h7-001/audit-determination/publish-to-tb')
    expect(body.sheet_name).toMatch(/H7-1/)
    expect(body.writeback_rows[0]).toMatchObject({ account_code: '1621', amount_kind: 'balance' })
    for (const call of mockPut.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
    w.unmount()
  })

  it.each(H7_CASES)('$name 取消确认 → 不发 POST', async (c) => {
    confirmRef.resolve = false
    const comp = await c.load()
    const w = mountH7(comp)
    await flushPromises()
    await w.find(`[data-testid="${c.testid}"]`).trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })

  it.each(H7_CASES)('$name readonly → 无发布按钮', async (c) => {
    const comp = await c.load()
    const w = mountH7(comp, true)
    await flushPromises()
    expect(w.find(`[data-testid="${c.testid}"]`).exists()).toBe(false)
    w.unmount()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// H9 — 双科目审定表（.vue 内联 handleWriteback，@vue/test-utils mount 走真实点击）
//   spec: tb-writeback-explicit-publish-gate Task 11 / Req 5,2,8
//   活路径：H9TabAdjudication inline handleWriteback（原双科目分两次 http.put
//   `/projects/{pid}/trial-balance/writeback`，**无 /api 前缀**）→ 改走单次
//   `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`（双科目单次原子发布 balance）。
//   科目：租赁负债 gross（h9Scope 兜底 2601）+ 未确认融资费用 unearned_finance（兜底 2602），均 balance。
// ════════════════════════════════════════════════════════════════════════════

describe('H9 双科目审定表发布走显式发布门（Task 11 / Req 5,2,8）', () => {
  let H9TabAdjudication: any
  beforeEach(async () => {
    H9TabAdjudication = (await import('../../h9/core/H9TabAdjudication.vue')).default
  })

  // 提供 render 下发的 tb_source_codes.slots，令 h9Scope 解析真实双科目（否则退兜底码，仍双科目）
  function buildH9HtmlData() {
    return {
      tb_source_codes: {
        slots: {
          gross: { key: 'gross', standard_codes: ['2601'], codes: ['2601'], found: true },
          unearned_finance: { key: 'unearned_finance', standard_codes: ['2602'], codes: ['2602'], found: true },
        },
      },
    }
  }

  function mountH9(readonly = false, html: any = buildH9HtmlData()) {
    return mount(H9TabAdjudication, {
      props: {
        wpId: 'wp-h9-001',
        projectId: 'proj-h9',
        allResponses: new Map(),
        htmlData: html,
        isReadonly: readonly,
      },
      global: globalMocks,
    })
  }

  it('点击"发布到试算表" → 确认 → POST publish-to-tb（sheet_name 含 H9-1，双科目单次 writeback_rows balance）', async () => {
    const w = mountH9()
    await flushPromises()
    const btn = w.find('[data-testid="h9-publish-tb"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toContain('/api/workpapers/wp-h9-001/audit-determination/publish-to-tb')
    expect(body.sheet_name).toMatch(/H9-1/)
    // 双科目在单次 writeback_rows 原子发布（租赁负债 2601 + 未确认融资费用 2602）
    expect(body.writeback_rows).toHaveLength(2)
    const codes = body.writeback_rows.map((r: any) => r.account_code)
    expect(codes).toContain('2601')
    expect(codes).toContain('2602')
    expect(body.writeback_rows.every((r: any) => r.amount_kind === 'balance')).toBe(true)
    for (const r of body.writeback_rows) {
      expect(typeof r.audited_amount).toBe('number')
    }
    w.unmount()
  })

  it('不再调旧端点 trial-balance/writeback（含无 /api 前缀的 http.put 变体）', async () => {
    const w = mountH9()
    await flushPromises()
    await w.find('[data-testid="h9-publish-tb"]').trigger('click')
    await flushPromises()
    for (const call of mockPut.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
    for (const call of mockPost.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
    w.unmount()
  })

  it('取消二次确认 → 不发 POST、不 emit substantive:adjudicated', async () => {
    confirmRef.resolve = false
    const emitSpy = vi.fn()
    window.addEventListener('substantive:adjudicated', emitSpy)
    const w = mountH9()
    await flushPromises()
    await w.find('[data-testid="h9-publish-tb"]').trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    expect(emitSpy).not.toHaveBeenCalled()
    window.removeEventListener('substantive:adjudicated', emitSpy)
    w.unmount()
  })

  it('readonly → 无发布按钮（v-if 包裹）+ 不发 POST', async () => {
    const w = mountH9(true)
    await flushPromises()
    expect(w.find('[data-testid="h9-publish-tb"]').exists()).toBe(false)
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })

  it('发布后仍 emit substantive:adjudicated（H8 联动 / 附注刷新回归 / Req 8）', async () => {
    const emitSpy = vi.fn()
    window.addEventListener('substantive:adjudicated', emitSpy)
    const w = mountH9()
    await flushPromises()
    await w.find('[data-testid="h9-publish-tb"]').trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(emitSpy).toHaveBeenCalled()
    const detail = (emitSpy.mock.calls[0][0] as CustomEvent).detail as { wpCode?: string }
    expect(detail.wpCode).toBe('H9')
    window.removeEventListener('substantive:adjudicated', emitSpy)
    w.unmount()
  })
})

// 未使用的 nextTick / Ref 引入用途保留（避免 TS unused）
void nextTick
export type { Ref }
