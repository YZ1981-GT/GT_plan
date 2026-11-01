/**
 * 抵消后长投表（batch 3 / ADR-CRW-004）：抵消列读服务端 canonical projection，不再读 elimEquity 空骨架。
 * 核心取数逻辑在 consolPostElimView（纯函数，可靠断言）；组件侧只验未分配提示的消费。
 */
import { describe, it, expect, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'

import {
  accountOf, companyElim, companyElimMap, unallocatedOf, warningsOf,
} from '../composables/consolPostElimView'

function projection(acc1511: any = {}) {
  return {
    project_id: 'p', year: 2025, root_node_key: 'G:consol',
    accounts: {
      '1511': {
        account_prefix: '1511', label: '长期股权投资', total: '100.00', unallocated: '0.00', balanced: true,
        by_company: [
          { company_code: 'A', company_name: '甲', amount: '60.00', source_entry_ids: [] },
          { company_code: 'B', company_name: '乙', amount: '40.00', source_entry_ids: [] },
        ],
        warnings: [],
        ...acc1511,
      },
    },
    manual_overrides: {}, warnings: [],
  } as any
}

describe('consolPostElimView 取数', () => {
  it('companyElimMap 按 company_code 建逐企业合计', () => {
    const m = companyElimMap(projection(), '1511')
    expect(m.get('A')).toBe(60)
    expect(m.get('B')).toBe(40)
    expect(m.has('C')).toBe(false)
  })

  it('companyElim 命中返回金额，未命中/缺来源返回 0', () => {
    expect(companyElim(projection(), '1511', 'A')).toBe(60)
    expect(companyElim(projection(), '1511', 'C')).toBe(0)
    expect(companyElim(projection(), '1511', undefined)).toBe(0)
    expect(companyElim(null, '1511', 'A')).toBe(0)
  })

  it('unallocatedOf / warningsOf 读未分配与提示', () => {
    const p = projection({ unallocated: '40.00', warnings: ['1 笔权益抵销分录关联了多家企业，无法唯一归属，计入未分配'] })
    expect(unallocatedOf(p, '1511')).toBe(40)
    expect(warningsOf(p, '1511')).toHaveLength(1)
    expect(unallocatedOf(null, '1511')).toBe(0)
    expect(warningsOf(null, '1511')).toEqual([])
  })

  it('accountOf 无 projection / 无该科目返回 null', () => {
    expect(accountOf(null, '1511')).toBeNull()
    expect(accountOf(projection(), '6111')).toBeNull()
  })
})

// ── 组件侧：未分配提示的消费（轻量 mount，只验 el-alert 文案） ──

vi.mock('@/utils/confirm', () => ({ confirmBatch: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() } }))
vi.mock('@/composables/useExcelIO', () => ({ useExcelIO: () => ({ exportData: vi.fn() }) }))
vi.mock('@/composables/useFullscreen', () => ({
  useFullscreen: () => ({ isFullscreen: { value: false }, toggleFullscreen: vi.fn() }),
}))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmt: (v: unknown) => (v == null ? '—' : String(v)), fontConfig: { tableFont: '12px' } }),
}))
vi.mock('@/services/consolidationApi', () => ({
  POST_ELIM_ACCOUNT: { longInvest: '1511', investIncome: '6111', capitalReserve: '4002', minorityEquity: '4501' },
}))

import PostElimInvestSheet from '../worksheets/PostElimInvestSheet.vue'

const AlertStub = defineComponent({
  props: ['title', 'type'],
  setup: (p) => () => h('div', { class: 'alert', 'data-type': p.type }, p.title),
})
const stubs = {
  'el-table': true, 'el-table-column': true, 'el-input-number': true,
  'el-button': true, 'el-tooltip': true, 'el-alert': AlertStub,
}

function mountSheet(proj: any) {
  return mount(PostElimInvestSheet, {
    props: {
      companies: [{ name: '甲', code: 'A', ratio: 60 }],
      investmentCost: [], investmentEquity: [], equitySimDirect: [],
      projection: proj, initialRows: [],
    },
    global: { stubs },
  })
}

describe('PostElimInvestSheet 组件消费 projection', () => {
  it('未分配额与 warning 渲染为提示条', () => {
    const w = mountSheet(projection({
      unallocated: '40.00',
      warnings: ['1 笔权益抵销分录关联了多家企业，无法唯一归属，计入未分配'],
    }))
    const alerts = w.findAll('.alert').map((n) => n.text())
    expect(alerts.some((t) => t.includes('无法唯一归属') || t.includes('企业标注不足'))).toBe(true)
    expect(alerts.some((t) => t.includes('多家'))).toBe(true)
  })

  it('projection 为空不弹未分配提示', () => {
    const w = mountSheet(null)
    expect(w.findAll('.alert[data-type="warning"]')).toHaveLength(0)
  })
})
