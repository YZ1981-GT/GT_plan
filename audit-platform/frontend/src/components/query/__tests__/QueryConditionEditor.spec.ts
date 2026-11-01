/**
 * QueryConditionEditor.spec.ts — 业务视图条件编辑器（advanced-query-linkage-closure 任务 29；R6.1、R6.2、R6.4，AQ-13 前端）
 *
 * - 结构化条件：v-model `{conditions, logic}`，加 / 改 / 删都发新状态；为空 / 不为空不显示值框；
 * - 字段下拉显示中文列名（按数据源：合并试算的 summary 是「汇总数」）；
 * - 值框不窄于 120px、条件行可换行（原先 `flex:1; min-width:0` 被挤成 0 宽，评估 B12a）——按 SFC 样式块静态核对；
 * - 数据源不支持条件时整块禁用并显示原因；
 * - 纯函数：请求体条件、未填写完整的原因、旧模板写法（operator / contains、大写 AND / OR）兼容。
 */
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse as parseSfc } from '@vue/compiler-sfc'
import ElementPlus from 'element-plus'
import QueryConditionEditor from '../QueryConditionEditor.vue'
import {
  CONDITION_OPS, EDITOR_OPS, WEEKDAY_OPTIONS, conditionOpsForDtype, conditionsIncompleteReason,
  fromSavedConditions, needsConditionValue, normalizeConditionLogic, toRequestConditions, toSavedConditions,
  type ConditionState,
} from '../queryConditions'

const HERE = dirname(fileURLToPath(import.meta.url))

function mountEditor(state: ConditionState, extra: Record<string, unknown> = {}) {
  return mount(QueryConditionEditor, {
    props: {
      modelValue: state,
      fields: [
        { key: 'account_code', dtype: 'text' },
        { key: 'debit_amount', dtype: 'number' },
        { key: 'voucher_date', dtype: 'date' },
        { key: 'summary', dtype: 'text' },
        { key: 'line_amount', dtype: 'number' },
      ],
      source: 'ledger_entries',
      ...extra,
    },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
}

describe('QueryConditionEditor 组件', () => {
  it('添加条件发出新状态：默认首个字段、等于、空值；组合逻辑原样', async () => {
    const w = mountEditor({ conditions: [], logic: 'or' })
    await w.find('[data-testid="cq-condition-add"]').trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as ConditionState
    expect(emitted).toEqual({ conditions: [{ field: 'account_code', op: 'eq', value: '' }], logic: 'or' })
    w.unmount()
  })

  it('改值 / 改算子 / 删除都只改对应那一行', async () => {
    const state: ConditionState = {
      conditions: [{ field: 'debit_amount', op: 'gt', value: '1' }, { field: 'summary', op: 'like', value: '冲销' }],
      logic: 'and',
    }
    const w = mountEditor(state)
    await flushPromises()
    // el-input 把非 class / style 的属性落在内部 <input> 上
    const inputs = w.findAll('input[data-testid="cq-condition-value"]')
    expect(inputs).toHaveLength(2)
    await inputs[0].setValue('100000000')
    let emitted = w.emitted('update:modelValue')!.at(-1)![0] as ConditionState
    expect(emitted.conditions).toEqual([{ field: 'debit_amount', op: 'gt', value: '100000000' },
      { field: 'summary', op: 'like', value: '冲销' }])
    const remove = w.findAll('button').filter((b) => b.text() === '删除')
    await remove[1].trigger('click')
    emitted = w.emitted('update:modelValue')!.at(-1)![0] as ConditionState
    expect(emitted.conditions).toEqual([{ field: 'debit_amount', op: 'gt', value: '1' }])
    w.unmount()
  })

  it('为空 / 不为空不显示值框（「无需值」）', async () => {
    const w = mountEditor({ conditions: [{ field: 'summary', op: 'is_null', value: '' }], logic: 'and' })
    await flushPromises()
    expect(w.findAll('[data-testid="cq-condition-value"]')).toHaveLength(0)
    expect(w.text()).toContain('无需值')
    w.unmount()
  })

  it('字段下拉显示中文列名，并按数据源取（合并试算的 summary 是「汇总数」，R6.6）', async () => {
    const ledger = mountEditor({ conditions: [], logic: 'and' })
    expect((ledger.vm as any).fieldOptions.map((f: any) => f.label)).toEqual([
      '科目编码', '借方发生额', '凭证日期', '摘要', '发生额（借贷较大者）',
    ])
    ledger.unmount()
    const consol = mountEditor({ conditions: [], logic: 'and' }, { fields: ['summary'], source: 'ws_consol_tb' })
    expect((consol.vm as any).fieldOptions.map((f: any) => f.label)).toEqual(['汇总数'])
    consol.unmount()
  })

  it('数据源不支持条件：整块禁用并显示原因', async () => {
    const reason = '该数据源不支持条件筛选'
    const w = mountEditor({ conditions: [], logic: 'and' }, { disabled: true, disabledReason: reason })
    expect(w.find('[data-testid="cq-condition-disabled"]').text()).toBe(reason)
    expect(w.find('[data-testid="cq-condition-add"]').attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('参数说明可见，组件暴露首个中文缺值原因', () => {
    const w = mountEditor(
      { conditions: [{ field: 'line_amount', op: 'gte', value: '', params: ['materiality_performance'] }], logic: 'and' },
      { notices: ['当前阈值：本项目实际执行的重要性水平'] },
    )
    expect(w.find('[data-testid="cq-condition-notice"]').text()).toContain('当前阈值')
    expect(w.find('[data-testid="cq-condition-param"]').text()).toContain('materiality_performance')
    expect((w.vm as any).incompleteReason).toBe('条件「发生额（借贷较大者）」未填写值')
    w.unmount()
  })

  it('用户改值或算子会清除 params 标记', async () => {
    const state: ConditionState = {
      conditions: [{ field: 'debit_amount', op: 'gte', value: '100', params: ['materiality_performance'] }],
      logic: 'and',
    }
    const valueEditor = mountEditor(state)
    await valueEditor.find('input[data-testid="cq-condition-value"]').setValue('200')
    let emitted = valueEditor.emitted('update:modelValue')!.at(-1)![0] as ConditionState
    expect(emitted.conditions[0]).toEqual({ field: 'debit_amount', op: 'gte', value: '200' })
    valueEditor.unmount()

    const opEditor = mountEditor(state)
    ;(opEditor.vm as any).onOperatorChange(0, 'lte')
    emitted = opEditor.emitted('update:modelValue')!.at(-1)![0] as ConditionState
    expect(emitted.conditions[0]).toEqual({ field: 'debit_amount', op: 'lte', value: '100' })
    opEditor.unmount()
  })

  it('星期条件渲染周一至周日多选并保留 0=周日', () => {
    const w = mountEditor({ conditions: [{ field: 'voucher_date', op: 'weekday_in', value: [1, 6, 0] }], logic: 'and' })
    expect(w.find('[data-testid="cq-condition-weekday"]').exists()).toBe(true)
    expect((w.vm as any).weekdayValue([1, 6, 0])).toEqual([1, 6, 0])
    expect((w.vm as any).operatorsFor({ field: 'voucher_date', op: 'eq', value: '' })
      .map((op: any) => op.label)).toContain('星期为')
    w.unmount()
  })

  it('值框不窄于 120px、条件行可换行（静态核对 SFC 样式）', () => {
    const { descriptor } = parseSfc(readFileSync(resolve(HERE, '../QueryConditionEditor.vue'), 'utf-8'))
    const css = descriptor.styles.map((s) => s.content).join('\n').replace(/\s+/g, ' ')
    expect(css).toMatch(/\.gt-qce-row \{[^}]*flex-wrap: wrap/)
    expect(css).toMatch(/\.gt-qce-value \{[^}]*min-width: 120px/)
    expect(css).not.toMatch(/\.gt-qce-value \{[^}]*min-width: 0/)
  })
})

describe('queryConditions 纯函数', () => {
  it('按 dtype 给精确中文算子，编辑器全集与各组并集一致', () => {
    expect(conditionOpsForDtype('text').map((o) => o.value)).toEqual([
      'eq', 'like', 'starts_with', 'is_null', 'is_not_null', 'is_blank',
    ])
    expect(conditionOpsForDtype('number').map((o) => o.value)).toEqual([
      'eq', 'gt', 'gte', 'lt', 'lte', 'between', 'is_null', 'is_not_null',
    ])
    expect(conditionOpsForDtype('date').map((o) => o.value)).toEqual([
      'eq', 'gt', 'gte', 'lt', 'lte', 'between', 'is_null', 'is_not_null', 'weekday_in',
    ])
    expect(conditionOpsForDtype('bool').map((o) => o.value)).toEqual(['eq', 'is_null', 'is_not_null'])
    expect(new Set(CONDITION_OPS.map((o) => o.value))).toEqual(EDITOR_OPS)
    expect(CONDITION_OPS.every((o) => /[\u4e00-\u9fff]/.test(o.label))).toBe(true)
    expect(['is_null', 'is_not_null', 'is_blank'].map(needsConditionValue)).toEqual([false, false, false])
    expect(WEEKDAY_OPTIONS.map((day) => day.value)).toEqual([1, 2, 3, 4, 5, 6, 0])
  })

  it('请求体只发 field/op/value：星期映射、为空、介于正确，params 不泄漏', () => {
    expect(toRequestConditions([
      { field: '', op: 'eq', value: 'x' },
      { field: 'summary', op: 'is_blank', value: 'ignored', params: ['unused'] },
      { field: 'debit_amount', op: 'between', value: ' 1 ，2 ', params: ['cutoff_start', 'cutoff_end'] },
      { field: 'voucher_date', op: 'weekday_in', value: [1, 6, 0] },
      { field: 'debit_amount', op: 'gte', value: ' 100000000 ', params: ['materiality_performance'] },
    ])).toEqual([
      { field: 'summary', op: 'is_blank', value: null },
      { field: 'debit_amount', op: 'between', value: ['1', '2'] },
      { field: 'voucher_date', op: 'weekday_in', value: [1, 6, 0] },
      { field: 'debit_amount', op: 'gte', value: '100000000' },
    ])
  })

  it('toSavedConditions 把参数来源写回占位，用户字面值保持字面量', () => {
    expect(toSavedConditions([
      { field: 'line_amount', op: 'gte', value: '1000000', params: ['materiality_performance'] },
      { field: 'voucher_date', op: 'between', value: '2025-12-26,2026-01-05', params: ['cutoff_start', 'cutoff_end'] },
      { field: 'summary', op: 'starts_with', value: '冲销' },
    ])).toEqual([
      { field: 'line_amount', op: 'gte', value: { $param: 'materiality_performance' } },
      { field: 'voucher_date', op: 'between', value: [
        { $param: 'cutoff_start' }, { $param: 'cutoff_end' },
      ] },
      { field: 'summary', op: 'starts_with', value: '冲销' },
    ])
  })

  it('未填写完整的原因：首个缺值的条件（字段中文名）、介于不是两个值、星期未选、没选字段却填了值', () => {
    const label = (f: string) => ({ debit_amount: '借方发生额' } as Record<string, string>)[f] ?? f
    expect(conditionsIncompleteReason([{ field: 'debit_amount', op: 'gt', value: ' ' }], label))
      .toBe('条件「借方发生额」未填写值')
    expect(conditionsIncompleteReason([{ field: 'debit_amount', op: 'between', value: '1' }], label))
      .toBe('条件「借方发生额」请按「起,止」填写两个值')
    expect(conditionsIncompleteReason([{ field: 'voucher_date', op: 'weekday_in', value: [] }], label))
      .toBe('条件「voucher_date」未填写值')
    expect(conditionsIncompleteReason([{ field: '', op: 'eq', value: '9' }], label)).toBe('第 1 个条件未选择字段')
    expect(conditionsIncompleteReason([{ field: 'summary', op: 'is_not_null', value: '' }, { field: '', op: 'eq', value: '' }],
      label)).toBe('')
  })

  it('旧模板与参数占位兼容：operator / contains、介于数组、大写 AND / OR', () => {
    expect(fromSavedConditions([
      { field: 'summary', operator: 'contains', value: '冲销' },
      { field: 'debit_amount', op: 'between', value: [1, 2] },
      { field: 'line_amount', op: 'gte', value: '1000000', params: ['materiality_performance'] },
      { field: 'voucher_date', op: 'between', value: [
        { $param: 'cutoff_start' }, { $param: 'cutoff_end' },
      ] },
      { field: 'summary', op: 'is_null', value: null },
      'bad',
    ])).toEqual([
      { field: 'summary', op: 'like', value: '冲销' },
      { field: 'debit_amount', op: 'between', value: '1,2' },
      { field: 'line_amount', op: 'gte', value: '1000000', params: ['materiality_performance'] },
      { field: 'voucher_date', op: 'between', value: ',', params: ['cutoff_start', 'cutoff_end'] },
      { field: 'summary', op: 'is_null', value: '' },
    ])
    expect([normalizeConditionLogic('OR'), normalizeConditionLogic('AND'), normalizeConditionLogic(undefined)])
      .toEqual(['or', 'and', 'and'])
  })
})

describe('系统预置算子契约（R13.8）', () => {
  it('custom_query_presets.json 每条条件的算子都能由编辑器表达', () => {
    const path = resolve(HERE, '../../../../../../backend/data/custom_query_presets.json')
    const data = JSON.parse(readFileSync(path, 'utf-8')) as {
      presets?: Array<{ id?: string; config?: { conditions?: Array<{ op?: string }> } }>
    }
    const presets = data.presets ?? []
    expect(presets.length).toBeGreaterThan(0)
    for (const preset of presets) {
      const conditions = preset.config?.conditions ?? []
      expect(conditions.length, `${preset.id} 应至少有一个条件`).toBeGreaterThan(0)
      for (const condition of conditions) {
        expect(EDITOR_OPS.has(condition.op as any), `${preset.id} 使用了编辑器不支持的算子 ${condition.op}`).toBe(true)
      }
    }
  })
})