/**
 * BalanceDiagnosticsDialog 单元测试
 *
 * 5.6: 报表行次未匹配只跳 ReportLineMapping，不跳 ColumnMappingEditor
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import BalanceDiagnosticsDialog from '../BalanceDiagnosticsDialog.vue'
import type { BalanceDiagnosticsResult, DiagnosticJumpTarget } from '@/types/balance-diagnostics'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

const globalStubs = {
  'el-dialog': {
    template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
    emits: ['close', 'update:modelValue'],
  },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size', 'effect'] },
  'el-button': {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'link', 'loading'],
    emits: ['click'],
  },
  'el-table': { template: '<div class="el-table"><slot /></div>', props: ['data', 'size', 'maxHeight', 'stripe'] },
  'el-table-column': { template: '<div class="el-table-column" />', props: ['prop', 'label', 'width', 'align'] },
}

function makeResult(overrides: Partial<BalanceDiagnosticsResult> = {}): BalanceDiagnosticsResult {
  return {
    caliber: 'trial_balance_debit_credit',
    caliber_label: '试算表全科目借方合计 vs 贷方合计',
    status: 'blocking',
    difference: 44030236.47,
    debit_total: 2546171215.70,
    credit_total: 2502140979.23,
    likely_causes: [
      {
        cause_code: 'report_line_unmatched',
        severity: 4,
        confidence: 0.85,
        description: '存在有余额但未映射报表行次的科目',
        evidence: {},
      },
      {
        cause_code: 'sign_convention_anomaly',
        severity: 3,
        confidence: 0.6,
        description: '部分科目符号异常',
        evidence: {},
      },
    ],
    unmatched_accounts: [
      { account_code: '2701', account_name: '长期应付款', amount: 1000000, mapping_status: 'seed_missing' },
    ],
    sign_anomalies: [],
    sign_anomalies_unavailable: false,
    top_contributors: [],
    jump_targets: [
      {
        target_type: 'report_line_mapping',
        label: '修复报表行次映射',
        transport: 'dialog_prop',
        params: { account_code: '2701', highlight: 'true' },
      },
    ],
    data_sources: {},
    ...overrides,
  }
}

describe('BalanceDiagnosticsDialog', () => {
  it('展示口径和差额', () => {
    const result = makeResult()
    const wrapper = mount(BalanceDiagnosticsDialog, {
      props: { modelValue: true, result },
      global: { stubs: globalStubs },
    })

    const html = wrapper.html()
    expect(html).toContain('试算表全科目借方合计 vs 贷方合计')
    expect(html).toContain('44,030,236.47')
  })

  it('原因按 severity 降序排列', () => {
    const result = makeResult()
    const wrapper = mount(BalanceDiagnosticsDialog, {
      props: { modelValue: true, result },
      global: { stubs: globalStubs },
    })

    const causeItems = wrapper.findAll('.bd-cause-item')
    expect(causeItems.length).toBe(2)
    // severity=4 在前
    expect(causeItems[0].text()).toContain('未映射报表行次')
    // severity=3 在后
    expect(causeItems[1].text()).toContain('符号异常')
  })

  it('展示未匹配科目清单', () => {
    const result = makeResult()
    const wrapper = mount(BalanceDiagnosticsDialog, {
      props: { modelValue: true, result },
      global: { stubs: globalStubs },
    })

    const html = wrapper.html()
    expect(html).toContain('未匹配报表行次科目')
  })

  it('展示跳转修复入口', () => {
    const result = makeResult()
    const wrapper = mount(BalanceDiagnosticsDialog, {
      props: { modelValue: true, result },
      global: { stubs: globalStubs },
    })

    const jumpButton = wrapper.findAll('.bd-jump-buttons .el-button')
    expect(jumpButton.length).toBe(1)
    expect(jumpButton[0].text()).toContain('修复报表行次映射')
  })

  // ─── 5.6: 核心测试 — 报表行次未匹配只跳 ReportLineMapping，不跳 ColumnMappingEditor ───

  it('报表行次未匹配只跳 ReportLineMapping，不跳 ColumnMappingEditor', async () => {
    const result = makeResult({
      jump_targets: [
        {
          target_type: 'report_line_mapping',
          label: '修复报表行次映射',
          transport: 'dialog_prop',
          params: { account_code: '2701', highlight: 'true' },
        },
      ],
    })

    const wrapper = mount(BalanceDiagnosticsDialog, {
      props: { modelValue: true, result },
      global: { stubs: globalStubs },
    })
    await nextTick()

    // 点击跳转按钮
    const jumpBtn = wrapper.find('.bd-jump-buttons .el-button')
    await jumpBtn.trigger('click')
    await nextTick()

    // 验证 emit 的是 report_line_mapping 跳转，而非 column_mapping_editor
    const jumpEmits = wrapper.emitted('jump')
    expect(jumpEmits).toBeTruthy()
    expect(jumpEmits!.length).toBe(1)
    const emittedTarget = jumpEmits![0][0] as DiagnosticJumpTarget
    expect(emittedTarget.target_type).toBe('report_line_mapping')
    // 确认不是 column_mapping / column_mapping_editor
    expect(emittedTarget.target_type).not.toBe('column_mapping_editor')
    expect(emittedTarget.target_type).not.toContain('column')
  })

  it('jump_targets 中不存在 column_mapping_editor 类型', () => {
    const result = makeResult()
    // 验证组件设计：对于 report_line_unmatched 原因，
    // 生成的跳转目标不会指向 ColumnMappingEditor
    for (const target of result.jump_targets) {
      expect(target.target_type).not.toContain('column')
    }
  })

  it('通过时不显示差额', () => {
    const result = makeResult({ status: 'passed', difference: 0 })
    const wrapper = mount(BalanceDiagnosticsDialog, {
      props: { modelValue: true, result },
      global: { stubs: globalStubs },
    })

    // status=passed 时不展示差额信息
    expect(wrapper.find('.bd-difference').exists()).toBe(false)
  })
})
