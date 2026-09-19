/**
 * jAdjudicationPublishGate.spec.ts — J 循环审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 15 / M9 / Req 1,2,8)
 *
 * 背景：此前 J1TabAdjudication 的 writebackTB 直调旧端点
 * `PUT /projects/{pid}/trial-balance/writeback`（科目 2211）绕过显式发布门。改造后与
 * D2/D4-1/E1/I/K 同范式：二次确认（中文）→ `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
 * （writeback_rows，应付职工薪酬为负债余额类 → amount_kind='balance'，sheet_name 解出 J1-1）。
 *
 * J1 的回写逻辑内联在 J1TabAdjudication.vue 的 <script setup>（非独立 composable），
 * 故用 @vue/test-utils mount 组件、点击 [data-testid=j1-publish-tb] 按钮走真实点击路径断言。
 *
 * 断言：
 *  - 确认 → POST publish-to-tb（url 含 wpId / sheet_name 含 J1-1 / writeback_rows 科目 2211 / amount_kind=balance / 审定合计）
 *  - 用户取消二次确认 → 无 POST、无 emit substantive:adjudicated
 *  - readonly → 无 POST（早退）
 *  - 不再调旧端点 trial-balance/writeback（PUT 或 POST 变体）
 *  - 发布后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8），wpCode='J1' / accountCode='2211'
 *  - J2 不在本任务（死代码，归 task 17），本 spec 只覆盖 J1 活路径
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { eventBus } from '@/utils/eventBus'

/** 刷新 microtask/macrotask 队列：handler 内含 await confirm + await import() + await api.post，
 *  需多轮 flush（动态 import 在 setTimeout 边界解析）才能让 mockPost 完成。 */
async function flush(times = 6): Promise<void> {
  for (let i = 0; i < times; i++) {
    await Promise.resolve()
    await new Promise((r) => setTimeout(r, 0))
  }
}
import J1TabAdjudication from '@/components/workpaper/j1/core/J1TabAdjudication.vue'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, mockPut, mockGet } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布到试算表', published: true })),
  mockPut: vi.fn(async () => ({})),
  mockGet: vi.fn(async () => ({ data: [] })),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: mockPost, put: mockPut, get: mockGet },
}))

// ─── mock http（默认落库 defaultSave / AI / 若有其他直调都被隔离） ───
const { mockHttpPut, mockHttpPost } = vi.hoisted(() => ({
  mockHttpPut: vi.fn(async () => ({ data: {} })),
  mockHttpPost: vi.fn(async () => ({ data: {} })),
}))
vi.mock('@/utils/http', () => ({
  default: { put: mockHttpPut, post: mockHttpPost, get: vi.fn(async () => ({ data: {} })) },
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

// ─── mock 带入调整 composable（其 onMounted 会 load 集中调整；隔离网络） ───
vi.mock('@/components/workpaper/composables/useAdjudicationBringIn', () => ({
  useAdjudicationBringIn: () => ({
    adjPull: { loading: { value: false }, matches: { value: [] } },
    visible: { value: false },
    rowOptions: { value: [] },
    open: vi.fn(),
    apply: vi.fn(),
    pendingCount: { value: 0 },
  }),
  default: () => ({
    adjPull: { loading: { value: false }, matches: { value: [] } },
    visible: { value: false },
    rowOptions: { value: [] },
    open: vi.fn(),
    apply: vi.fn(),
    pendingCount: { value: 0 },
  }),
}))

// ─── mock 审计上下文（year） ───
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({ year: { value: 2025 } }),
}))

const globalStubs = {
  'el-alert': { template: '<div><slot name="title" /></div>', props: ['type', 'closable'] },
  'el-button': {
    template: '<button class="el-button" :data-testid="$attrs[\'data-testid\']" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'plain', 'disabled', 'loading'],
    emits: ['click'],
  },
  'el-icon': { template: '<i><slot /></i>' },
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  // el-table/column 的默认插槽是 scoped（{ row }），mount 时 row 为 undefined 会崩；
  // 本测试只点击 .mode-bar 里的发布按钮，与表格无关 → 不渲染其默认插槽。
  'el-table': { template: '<div class="stub-el-table" />', props: ['data'] },
  'el-table-column': { template: '<div class="stub-el-table-column" />', props: ['label'] },
  'el-input': { template: '<input />', props: ['modelValue'] },
  'el-input-number': { template: '<input />', props: ['modelValue'] },
  'el-tag': { template: '<span><slot /></span>', props: ['type', 'size'] },
  GtIndexChip: { template: '<span />', props: ['value', 'contextProjectId'] },
  AdjudicationBringInDialog: { template: '<div />' },
  WpFourTableSourcePanel: { template: '<div />' },
  WpAmountInput: { template: '<input />', props: ['modelValue', 'disabled'] },
  Download: { template: '<i />' },
}

/**
 * 构造含非零审定数的 htmlData：useJ1Adjudication.init 读 adjudication_rows（snake_case 兼容），
 * 审定 = 未审 + 调整。此处期末未审 1000000 → grandTotal.endAudited = 1000000。
 */
function buildHtmlData() {
  return {
    adjudication_rows: [
      { id: 'r1', label: '工资', category: 'short_term', begin_unadj: 800000, end_unadj: 1000000 },
    ],
  }
}

function mountJ1(readonly = false) {
  return mount(J1TabAdjudication, {
    props: {
      wpId: 'wp-j1-001',
      projectId: 'proj-j1',
      htmlData: buildHtmlData(),
      isReadonly: readonly,
    },
    global: { stubs: globalStubs },
  })
}

function findPublishBtn(wrapper: ReturnType<typeof mountJ1>) {
  return wrapper.findAll('.el-button').find((b) => b.attributes('data-testid') === 'j1-publish-tb')
}

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockClear()
  mockHttpPut.mockClear()
  mockHttpPost.mockClear()
  confirmRef.resolve = true
})

describe('J1 审定表发布到试算表走显式发布门（tb-writeback-explicit-publish-gate Task 15）', () => {
  it('工具栏存在"发布到试算表"按钮（data-testid=j1-publish-tb）', () => {
    const wrapper = mountJ1()
    const btn = findPublishBtn(wrapper)
    expect(btn).toBeDefined()
    expect(btn!.text()).toContain('发布到试算表')
  })

  it('确认后调 POST publish-to-tb，body 含 sheet_name(J1-1) + writeback_rows(2211/balance/审定合计)', async () => {
    const wrapper = mountJ1()
    await findPublishBtn(wrapper)!.trigger('click')
    await flush()

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toBe('/api/workpapers/wp-j1-001/audit-determination/publish-to-tb')
    expect(body.sheet_name).toMatch(/J1-1/)
    expect(Array.isArray(body.writeback_rows)).toBe(true)
    expect(body.writeback_rows).toHaveLength(1)
    const row = body.writeback_rows[0]
    expect(row.account_code).toBe('2211')
    expect(row.amount_kind).toBe('balance')
    expect(row.audited_amount).toBe(1000000) // 期末未审 1000000 + 调整 0
  })

  it('不再调旧端点 trial-balance/writeback（api.put 或 http.put 变体）', async () => {
    const wrapper = mountJ1()
    await findPublishBtn(wrapper)!.trigger('click')
    await flush()

    // api.put 完全未被调用
    expect(mockPut).not.toHaveBeenCalled()
    // http.put / api.post 均不含 trial-balance/writeback 字面量
    for (const call of mockHttpPut.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
    for (const call of mockPost.mock.calls) {
      expect(String(call[0])).not.toContain('trial-balance/writeback')
    }
  })

  it('用户取消二次确认 → 不发请求、不 emit substantive:adjudicated（无副作用 / Req 2）', async () => {
    confirmRef.resolve = false
    const emitSpy = vi.fn()
    eventBus.on('substantive:adjudicated', emitSpy)
    const wrapper = mountJ1()
    try {
      await findPublishBtn(wrapper)!.trigger('click')
      await flush()
      expect(mockPost).not.toHaveBeenCalled()
      expect(emitSpy).not.toHaveBeenCalled()
    } finally {
      eventBus.off('substantive:adjudicated', emitSpy)
    }
  })

  it('readonly → 按钮禁用且处理函数早退，不发请求', async () => {
    const wrapper = mountJ1(true)
    const btn = findPublishBtn(wrapper)!
    expect(btn.attributes('disabled')).toBeDefined()
    // 即便直接触发点击也早退
    await btn.trigger('click')
    await flush()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('发布后仍 emit substantive:adjudicated（wpCode=J1 / accountCode=2211 / Req 8）', async () => {
    const emitSpy = vi.fn()
    eventBus.on('substantive:adjudicated', emitSpy)
    const wrapper = mountJ1()
    try {
      await findPublishBtn(wrapper)!.trigger('click')
      await flush()
      expect(mockPost).toHaveBeenCalledTimes(1)
      expect(emitSpy).toHaveBeenCalled()
      const payload = emitSpy.mock.calls[0][0] as { wpCode: string; accountCode: string; auditedAmount: number }
      expect(payload.wpCode).toBe('J1')
      expect(payload.accountCode).toBe('2211')
      expect(payload.auditedAmount).toBe(1000000)
    } finally {
      eventBus.off('substantive:adjudicated', emitSpy)
    }
  })
})
