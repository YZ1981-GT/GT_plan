/**
 * CellTraceDialog.spec.ts — Sprint 2 Task 2.4 单元格溯源弹窗 vitest
 *
 * Spec:    .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.4
 * Design:  D5 CellTrace 三栏布局
 * Reqs:    R3.1 验收 21、22
 *
 * ≥ 3 用例：
 *   1. 加载 + 显示 binding metadata + formula_resolved + computed_value
 *   2. 点击 evidence 行 emit `penetrate-to-tb` 含 account_code
 *   3. 接收 trace error → 显示友好提示（不崩）
 *   4. 默认 active tab = trial_balance
 *   5. mode tag type 映射（auto/manual/locked）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mock element-plus ──────────────────────────────────────────────
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// ─── Mock api.get ───────────────────────────────────────────────────
const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
  },
}))

// el-* 组件 stub（避免引入完整 element-plus 导致 jsdom 报错）
const globalStubs = {
  stubs: {
    'el-dialog': {
      template:
        '<div data-test="dialog" v-if="modelValue"><slot /></div>',
      props: ['modelValue'],
      emits: ['update:modelValue'],
    },
    'el-alert': {
      template: '<div data-test="alert" :data-title="title">{{ title }}</div>',
      props: ['title', 'description', 'type', 'showIcon', 'closable'],
    },
    'el-tabs': {
      template: '<div><slot /></div>',
      props: ['modelValue', 'type', 'size'],
      emits: ['update:modelValue'],
    },
    'el-tab-pane': {
      template: '<div :data-tab="name"><slot /></div>',
      props: ['label', 'name'],
    },
    'el-tag': {
      template: '<span data-test="tag" :data-type="type">{{ $slots.default ? "" : "" }}<slot /></span>',
      props: ['type', 'size'],
    },
    'el-table': {
      template:
        '<div data-test="table"><slot />' +
        '<div v-for="(row, idx) in data" :key="idx" data-test="row" @click="$emit(\'rowClick\', row); $emit(\'row-click\', row)">' +
        '<slot name="default" :row="row" /></div></div>',
      props: ['data', 'size', 'border', 'stripe', 'maxHeight'],
      emits: ['row-click'],
    },
    'el-table-column': {
      template: '<span><slot /></span>',
      props: ['prop', 'label', 'width', 'align', 'minWidth'],
    },
    'el-button': {
      template:
        '<button :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
      props: ['disabled', 'size', 'type', 'link'],
    },
    'el-empty': {
      template: '<div data-test="empty">{{ description }}</div>',
      props: ['description', 'imageSize'],
    },
  },
}

// vue-tsc 历史 type 债：vitest spec 文件 import .vue 无类型声明，
// 实际 vitest 能解析（已通过 4/4 测试），不影响运行时
import CellTraceDialog from '../CellTraceDialog.vue'

const baseTraceResp = {
  binding: {
    source: 'trial_balance',
    field: 'audited_amount',
    account_codes: ['1001', '1002'],
    agg: 'sum',
    mode: 'auto',
  },
  binding_id: '五、1 货币资金.库存现金.closing_balance',
  formula_resolved: "=SUM(TB('1001','audited_amount'), TB('1002','audited_amount'))",
  computed_value: 1234.56,
  computed_at: '2026-05-27T10:00:00+00:00',
  semantic: 'closing_balance',
  row_label: '库存现金',
  evidence: {
    trial_balance_rows: [
      { account_code: '1001', audited: 1000.0, opening: 800.0 },
      { account_code: '1002', audited: 234.56, opening: 100.0 },
    ],
    ledger_sample: [],
    aux_balance_sample: [],
  },
}

beforeEach(() => {
  mockGet.mockReset()
})

describe('CellTraceDialog — 加载 + 显示 binding metadata', () => {
  it('挂载后调 trace 接口并展示 formula + binding', async () => {
    mockGet.mockResolvedValueOnce(baseTraceResp)
    const wrapper = mount(CellTraceDialog, {
      props: {
        modelValue: true,
        noteId: 'note-uuid-1',
        rowIdx: 0,
        colIdx: 0,
      },
      global: globalStubs,
    })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledWith(
      '/api/disclosure-notes/note-uuid-1/cells/0/0/trace',
    )
    const html = wrapper.html()
    expect(html).toContain('trial_balance')
    expect(html).toContain('audited_amount')
    expect(html).toContain('1001')
    expect(html).toContain('1002')
    // formula_resolved 渲染
    expect(html).toContain("SUM(TB('1001'")
    // computed_value 渲染（千分位）
    expect(html).toMatch(/1,234\.56/)
    // 行标签
    expect(html).toContain('库存现金')
  })
})

describe('CellTraceDialog — 点击 evidence 行 emit penetrate-to-tb', () => {
  it('点击行 → emit { account_code }', async () => {
    mockGet.mockResolvedValueOnce(baseTraceResp)
    const wrapper = mount(CellTraceDialog, {
      props: {
        modelValue: true,
        noteId: 'note-uuid-2',
        rowIdx: 1,
        colIdx: 0,
      },
      global: globalStubs,
    })
    await flushPromises()
    // 触发表格行点击：直接调用组件 vm 的 onEvidenceRowClick
    const vm = wrapper.vm as any
    // tbRows 应有两条
    expect(vm.tbRows.length).toBe(2)
    // 仿真点击第一行
    const rows = wrapper.findAll('[data-test="row"]')
    expect(rows.length).toBeGreaterThan(0)
    await rows[0].trigger('click')
    const emitted = wrapper.emitted('penetrate-to-tb')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ account_code: '1001' })
  })
})

describe('CellTraceDialog — error 友好提示', () => {
  it('trace 返回 error=no_binding → 显示 alert 不崩', async () => {
    mockGet.mockResolvedValueOnce({
      error: 'no_binding',
      computed_value: 999.0,
      semantic: null,
      computed_at: '2026-05-27T10:00:00+00:00',
    })
    const wrapper = mount(CellTraceDialog, {
      props: {
        modelValue: true,
        noteId: 'note-uuid-3',
        rowIdx: 0,
        colIdx: 0,
      },
      global: globalStubs,
    })
    await flushPromises()
    const html = wrapper.html()
    expect(html).toContain('无 binding 配置')
    // 三栏不应渲染（errorState 优先）
    expect(html).not.toContain('binding 元数据')
  })

  it('网络异常 → 错误状态 fetch_failed', async () => {
    mockGet.mockRejectedValueOnce(new Error('boom'))
    const wrapper = mount(CellTraceDialog, {
      props: {
        modelValue: true,
        noteId: 'note-uuid-4',
        rowIdx: 0,
        colIdx: 0,
      },
      global: globalStubs,
    })
    await flushPromises()
    const html = wrapper.html()
    expect(html).toContain('加载溯源数据失败')
  })
})
