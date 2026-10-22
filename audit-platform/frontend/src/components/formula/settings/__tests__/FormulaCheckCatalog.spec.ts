/**
 * 全平台校对规则目录（spec formula-governance-coverage-closure R3）：
 * 来源清单 → 选中来源看规则（执行位置 / 去哪编辑）→ 跨来源搜索；表间审核面板的目录入口与「从预置选用」。
 * 真挂载（mock 只替换 formulaSettingsApi 网络层）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'

const calls: Array<Record<string, unknown>> = []
const SOURCES = [
  { key: 'report_builtin', label: '报表勾稽（内置）', category: '报表', runs_in: '公式管理中心表间审核', editable: false,
    edit_where: '', files: [], from_db: false, rule_count: 2, error: null },
  { key: 'cross_check_preset', label: '表间审核预置', category: '报表', runs_in: '新增表间审核规则时「从预置选用」',
    editable: true, edit_where: '选用后可改', files: ['cross_check_preset_rules.json'], from_db: false, rule_count: 1,
    error: null },
  { key: 'a17_consistency', label: 'A17 跨章节一致性', category: '底稿', runs_in: 'A17', editable: false, edit_where: '',
    files: ['a17_consistency_rules.json'], from_db: false, rule_count: 0, error: '加载失败：文件坏了' },
]
const RULES: Record<string, any[]> = {
  report_builtin: [
    { id: 'report-cross-check-1', label: '资产合计 = 负债合计 + 所有者权益合计', expression: "ROW('assets_total')", severity: 'logic_check',
      severity_label: '勾稽', scope: '报表' },
    { id: 'report-cross-check-7', label: '货币资金 ≥ 0', expression: "ROW('BS-001') >= 0", severity: 'logic_check',
      severity_label: '勾稽', scope: '报表' },
  ],
  cross_check_preset: [
    { id: 'preset-1', label: '资产负债表平衡', expression: "ROW('资产合计') = ROW('负债和所有者权益合计')",
      severity: 'logic_check', severity_label: '勾稽', scope: 'balance_sheet',
      fields: { label: '资产负债表平衡', left_ref: "ROW('资产合计')", operator: '=', right_ref: "ROW('负债和所有者权益合计')",
        tolerance: '0.01', description: '资产合计 = 负债合计 + 所有者权益合计' } },
  ],
  a17_consistency: [],
}

vi.mock('@/services/formulaSettingsApi', () => ({
  formulaSettingsApi: {
    checkRules: vi.fn(async (params: Record<string, string> = {}) => {
      calls.push(params)
      if (params.source) {
        const s = SOURCES.find((x) => x.key === params.source)!
        return { sources: [{ ...s, rules: RULES[s.key], matched: RULES[s.key].length }], total: 3 }
      }
      if (params.q) {
        return { sources: SOURCES.map((s) => {
          const rules = RULES[s.key].filter((r) => r.label.includes(params.q) || r.expression.includes(params.q))
          return { ...s, rules, matched: rules.length }
        }), total: 3 }
      }
      return { sources: SOURCES, total: 3 }
    }),
  },
}))

import FormulaCheckCatalog from '../FormulaCheckCatalog.vue'
import FormulaCrossCheckPanel from '../../FormulaCrossCheckPanel.vue'

beforeEach(() => {
  calls.length = 0
})

const mountCatalog = (props: Record<string, unknown> = {}) =>
  mount(FormulaCheckCatalog, { props, global: { plugins: [ElementPlus] } })

describe('校对规则目录', () => {
  it('先取来源清单，再取第一个来源的规则；展示执行位置与是否可编辑', async () => {
    const w = mountCatalog()
    await flushPromises()
    expect(calls).toEqual([{}, { source: 'report_builtin' }])
    const text = w.text()
    for (const s of ['共 3 个来源 · 3 条规则', '报表勾稽（内置）', '执行：公式管理中心表间审核', '平台内不可编辑',
      'report-cross-check-7', '货币资金 ≥ 0', '勾稽']) {
      expect(text, s).toContain(s)
    }
    expect(w.find('[data-testid="fcc-src-report_builtin"]').attributes('aria-selected')).toBe('true')
  })

  it('点另一个来源：按来源取规则；可编辑来源写明去哪编辑；加载失败的来源给出原因', async () => {
    const w = mountCatalog()
    await flushPromises()
    await w.find('[data-testid="fcc-src-cross_check_preset"]').trigger('click')
    await flushPromises()
    expect(calls.at(-1)).toEqual({ source: 'cross_check_preset' })
    expect(w.find('[data-testid="fcc-head"]').text()).toContain('编辑：选用后可改')
    expect(w.text()).toContain('规则文件：cross_check_preset_rules.json')
    await w.find('[data-testid="fcc-src-a17_consistency"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(w.text()).toContain('加载失败：文件坏了')
  })

  it('跨来源搜索：结果带来源列；清空回到所选来源', async () => {
    const w = mountCatalog({ initialSource: 'cross_check_preset' })
    await flushPromises()
    expect(calls).toEqual([{}, { source: 'cross_check_preset' }])
    // el-input 不继承属性到外层：data-testid 落在原生 input 上
    await w.find('input[data-testid="fcc-search"]').setValue('资产')
    await w.find('[data-testid="fcc-search-btn"]').trigger('click')
    await flushPromises()
    expect(calls.at(-1)).toEqual({ q: '资产' })
    const text = w.text()
    expect(text).toContain('搜索「资产」')
    expect(text).toContain('来源')
    expect(text).toContain('报表勾稽（内置）')
    expect(w.find('[data-testid="fcc-src-report_builtin"] .gt-fcc-count').text()).toBe('1')
    await w.find('input[data-testid="fcc-search"]').setValue('')
    await w.find('[data-testid="fcc-search-btn"]').trigger('click')
    await flushPromises()
    expect(calls.at(-1)).toEqual({ source: 'cross_check_preset' })
  })
})

describe('表间审核面板：目录入口与从预置选用', () => {
  const panelProps = () => ({
    selectedPath: '资产负债表', rules: [], execEmpty: false, running: false, showDialog: true, dialogTitle: '新增规则',
    form: { label: '', left_ref: '', operator: '<=', right_ref: '', description: '' }, projectId: 'p1', year: 2025,
    layerTagType: () => 'info', layerLabel: () => '',
  })

  it('选一条预置：填进编辑表单（名称 / 两侧 / 运算符 / 说明），仍可再改', async () => {
    const props = panelProps()
    const w = mount(FormulaCrossCheckPanel, { props, global: { plugins: [ElementPlus], stubs: { CrossCheckHistoryPanel: true } } })
    const vm = w.vm as any
    await vm.$.setupState.onPresetOpen(true)
    expect(calls).toEqual([{ source: 'cross_check_preset' }])
    vm.$.setupState.applyPreset('preset-1')
    expect(props.form).toEqual({
      label: '资产负债表平衡', left_ref: "ROW('资产合计')", operator: '=', right_ref: "ROW('负债和所有者权益合计')",
      description: '资产合计 = 负债合计 + 所有者权益合计',
    })
    await vm.$.setupState.onPresetOpen(true)
    expect(calls.length).toBe(1)
  })

  it('目录入口打开只读目录弹窗', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => ({}) as any)
    const w = mount(FormulaCrossCheckPanel, {
      props: { ...panelProps(), showDialog: false },
      global: { plugins: [ElementPlus], stubs: { CrossCheckHistoryPanel: true } },
    })
    expect((w.vm as any).$.setupState.catalogVisible).toBe(false)
    await w.find('[data-testid="cc-open-catalog"]').trigger('click')
    await flushPromises()
    expect((w.vm as any).$.setupState.catalogVisible).toBe(true)
    expect(calls[0]).toEqual({})
    expect(errSpy).not.toHaveBeenCalled()
  })
})
