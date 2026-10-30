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

// ─── 最终来源诊断（spec note-chain-followup-optimizations R2）──────────────────

const sourcesResp = {
  target: 't1:3:0',
  target_label: '货币资金 · 合计 · 期末余额',
  value: 999,
  projected: true,
  storage: { kind: 'sub_table', text: '底稿子表「货币资金」第 4 行 · end_amount' },
  final: { kind: 'workpaper_sync', label: '底稿披露表同步', detail: '底稿 E1「附注披露」' },
  steps: [
    { kind: 'formula', label: '预设公式（系统预设）', status: 'kept', detail: 'SUM(0:2, 0)；按当前各格算得 6.00' },
    { kind: 'sync', label: '底稿披露表同步', status: 'final', detail: '底稿 E1「附注披露」' },
  ],
  conflicts: [{ kind: 'workpaper_differs', message: '底稿披露表的值 999.00 与预设公式结果 6.00 不一致，保留底稿值' }],
}

function routeGet(map: Record<string, unknown>) {
  mockGet.mockImplementation(async (url: string) => {
    for (const [part, value] of Object.entries(map)) {
      if (url.includes(part)) {
        if (value instanceof Error) throw value
        return value
      }
    }
    throw new Error(`unexpected ${url}`)
  })
}

describe('CellTraceDialog — 最终来源', () => {
  it('底稿来源的格：只查最终来源（按子表 + 来源行 + 列键），不请求模板取数溯源', async () => {
    routeGet({ '/cell-sources': sourcesResp })
    const wrapper = mount(CellTraceDialog, {
      props: {
        modelValue: true, noteId: 'n1', rowIdx: 3, colIdx: 0, projectId: 'p1', year: 2025, noteSection: '五、1',
        sourceRef: { tableIndex: 0, row: 3, col: 0, subTableKey: '货币资金', valueKey: 'end_amount' },
      },
      global: globalStubs,
    })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith(
      `/api/disclosure-notes/p1/2025/${encodeURIComponent('五、1')}/cell-sources`,
      { params: { table_index: 0, row: 3, col: 0, sub_table_key: '货币资金', value_key: 'end_amount' }, _silent: true },
    )
    const html = wrapper.html()
    expect(html).toContain('最终来源')
    expect(html).toContain('底稿披露表同步')
    expect(html).toContain('保留底稿值')
    expect(html).toContain('货币资金 · 合计 · 期末余额')
    expect(html).not.toContain('binding 元数据')
  })

  it('存储表第 3 张表：模板取数溯源带表序号，无绑定时提示看最终来源', async () => {
    routeGet({
      '/cell-sources': { ...sourcesResp, final: { kind: 'preset_formula', label: '预设公式', detail: 'SUM(0:1, 0)' } },
      '/trace': { error: 'no_binding', computed_value: 5 },
    })
    const wrapper = mount(CellTraceDialog, {
      props: {
        modelValue: true, noteId: 'n2', rowIdx: 1, colIdx: 0, tableIndex: 2, projectId: 'p1', year: 2025,
        noteSection: '五、1', sourceRef: { tableIndex: 2, row: 1, col: 0 },
      },
      global: globalStubs,
    })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledWith('/api/disclosure-notes/n2/cells/1/0/trace', { params: { table_index: 2 } })
    expect(mockGet).toHaveBeenCalledWith(
      `/api/disclosure-notes/p1/2025/${encodeURIComponent('五、1')}/cell-sources`,
      { params: { table_index: 2, row: 1, col: 0 }, _silent: true },
    )
    const html = wrapper.html()
    expect(html).toContain('预设公式')
    expect(html).toContain('无 binding 配置')
  })

  it('最终来源请求被拒：就地提示，不影响模板取数溯源', async () => {
    routeGet({
      '/cell-sources': Object.assign(new Error('forbidden'), { response: { status: 403, data: {} } }),
      '/trace': baseTraceResp,
    })
    const wrapper = mount(CellTraceDialog, {
      props: {
        modelValue: true, noteId: 'n3', rowIdx: 0, colIdx: 0, projectId: 'p1', year: 2025, noteSection: '五、1',
        sourceRef: { tableIndex: 0, row: 0, col: 0 },
      },
      global: globalStubs,
    })
    await flushPromises()
    const html = wrapper.html()
    expect(html).toContain('无权查看本项目附注')
    expect(html).toContain("SUM(TB('1001'")
  })
})
