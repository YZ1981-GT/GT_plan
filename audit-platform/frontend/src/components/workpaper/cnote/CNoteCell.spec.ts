/**
 * CNoteCell.spec.ts — C 类附注披露嵌套表单元格渲染器单元测试
 *
 * spec gt-c-note-table-shrink Task 5
 *
 * 覆盖全部 8 渲染分支 + amount precision + readonly：
 * 1. readonly / label → 只读 span（含 _indent 缩进 class）
 * 2. amount_formula → 只读 gt-amt + formatAmount(computedValue)
 * 3. percent_formula → 只读 + formatPercent(computedValue)
 * 4. boolean → ElCheckbox
 * 5. number → ElInputNumber（amount 时 precision=2 + gt-amt class）
 * 6. enum → ElSelect 单选 clearable
 * 7. multi_enum → ElSelect multiple
 * 8. date → ElDatePicker / textarea → ElInput textarea / 默认 → ElInput text
 *
 * Validates: Requirements 2, 13
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// Mock formatAmount（与 GtCNoteTable.spec.ts 一致）
vi.mock('@/utils/formatAmount', () => ({
  formatAmount: (v: any) =>
    v == null || v === '' ? '' : Number(v).toLocaleString('zh-CN'),
}))

import CNoteCell from './CNoteCell.vue'
import type { ColumnDefWithKey, RowData } from '../GtCNoteTable.types'

// ─── Helpers ──────────────────────────────────────────────────────────────

function mountCell(opts: {
  col: Partial<ColumnDefWithKey>
  row?: RowData
  readonly?: boolean
  computedValue?: number | string | null
}) {
  const col: ColumnDefWithKey = {
    field: 'val',
    label: '数值',
    _cellKey: 'B1',
    ...opts.col,
  } as ColumnDefWithKey
  const row: RowData = opts.row ?? {}
  return mount(CNoteCell, {
    props: {
      row,
      col,
      readonly: opts.readonly ?? false,
      computedValue: opts.computedValue ?? null,
    },
  })
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('CNoteCell — 8 渲染分支', () => {
  it('分支 1a：col.readonly → 只读 span 显示文本', () => {
    const wrapper = mountCell({
      col: { field: 'note', label: '备注', readonly: true },
      row: { note: '只读内容' },
    })
    const span = wrapper.find('span.gt-cnt__cell-readonly')
    expect(span.exists()).toBe(true)
    expect(span.text()).toBe('只读内容')
    // 非输入控件
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('分支 1b：label 字段（category_label）→ 只读 span + _indent 缩进 class', () => {
    const wrapper = mountCell({
      col: { field: 'category_label', label: '类别' },
      row: { category_label: '应收账款', _indent: 2 },
    })
    const span = wrapper.find('span.gt-cnt__cell-readonly')
    expect(span.exists()).toBe(true)
    expect(span.text()).toBe('应收账款')
    expect(span.classes()).toContain('gt-cnt__indent-2')
  })

  it('分支 1c：label 字段无值时回退到 row._label', () => {
    const wrapper = mountCell({
      col: { field: 'aging_label', label: '账龄' },
      row: { _label: '1年以内' },
    })
    expect(wrapper.find('span.gt-cnt__cell-readonly').text()).toBe('1年以内')
  })

  it('分支 2：amount_formula → 只读 gt-amt span + formatAmount(computedValue)', () => {
    const wrapper = mountCell({
      col: { field: 'total', label: '合计', type: 'number', render: 'amount_formula' },
      computedValue: 12345.67,
    })
    const span = wrapper.find('span.gt-cnt__cell-readonly.gt-amt')
    expect(span.exists()).toBe(true)
    // formatAmount mock → toLocaleString
    expect(span.text()).toBe((12345.67).toLocaleString('zh-CN'))
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('分支 3：percent_formula → 只读 span + formatPercent(computedValue)', () => {
    const wrapper = mountCell({
      col: { field: 'ratio', label: '占比', type: 'number', render: 'percent_formula' },
      computedValue: 25.5,
    })
    const span = wrapper.find('span.gt-cnt__cell-readonly')
    expect(span.exists()).toBe(true)
    // formatPercent → "25.50%"
    expect(span.text()).toContain('%')
    expect(span.text()).toContain('25.50')
  })

  it('分支 4：boolean → ElCheckbox', () => {
    const wrapper = mountCell({
      col: { field: 'flag', label: '标记', type: 'boolean' },
      row: { flag: true },
    })
    expect(wrapper.find('.el-checkbox').exists()).toBe(true)
  })

  it('分支 5：number → ElInputNumber', () => {
    const wrapper = mountCell({
      col: { field: 'qty', label: '数量', type: 'number' },
      row: { qty: 10 },
    })
    expect(wrapper.find('.el-input-number').exists()).toBe(true)
  })

  it('分支 6：enum → ElSelect 单选（非 multiple）', () => {
    const wrapper = mountCell({
      col: { field: 'cat', label: '类别', type: 'enum', enum: ['A', 'B', 'C'] },
      row: { cat: 'A' },
    })
    const select = wrapper.find('.el-select')
    expect(select.exists()).toBe(true)
    // 单选不应有 multiple 标记
    expect(wrapper.find('.el-select__tags').exists()).toBe(false)
  })

  it('分支 7：multi_enum → ElSelect multiple', () => {
    const wrapper = mountCell({
      col: { field: 'tags', label: '标签', type: 'multi_enum', enum: ['X', 'Y'] },
      row: { tags: ['X'] },
    })
    expect(wrapper.find('.el-select').exists()).toBe(true)
  })

  it('分支 8a：date → ElDatePicker', () => {
    const wrapper = mountCell({
      col: { field: 'dt', label: '日期', type: 'date' },
      row: { dt: '2025-01-01' },
    })
    expect(wrapper.find('.el-date-editor').exists()).toBe(true)
  })

  it('分支 8b：textarea → ElInput textarea', () => {
    const wrapper = mountCell({
      col: { field: 'memo', label: '说明', type: 'textarea' },
      row: { memo: '多行文本' },
    })
    expect(wrapper.find('textarea').exists()).toBe(true)
  })

  it('分支 8c：默认（无 type）→ ElInput text', () => {
    const wrapper = mountCell({
      col: { field: 'name', label: '名称' },
      row: { name: '文本' },
    })
    expect(wrapper.find('.el-input').exists()).toBe(true)
    expect(wrapper.find('textarea').exists()).toBe(false)
  })
})

describe('CNoteCell — amount precision + readonly', () => {
  it('number + render=amount → 带 gt-amt class（precision=2 金额铁律）', () => {
    const wrapper = mountCell({
      col: { field: 'money', label: '金额', type: 'number', render: 'amount' },
      row: { money: 100 },
    })
    const inputNumber = wrapper.find('.el-input-number')
    expect(inputNumber.exists()).toBe(true)
    expect(inputNumber.classes()).toContain('gt-amt')
  })

  it('number 非 amount → 无 gt-amt class', () => {
    const wrapper = mountCell({
      col: { field: 'qty', label: '数量', type: 'number' },
      row: { qty: 5 },
    })
    const inputNumber = wrapper.find('.el-input-number')
    expect(inputNumber.exists()).toBe(true)
    expect(inputNumber.classes()).not.toContain('gt-amt')
  })

  it('readonly=true → number 输入控件 disabled', () => {
    const wrapper = mountCell({
      col: { field: 'qty', label: '数量', type: 'number' },
      row: { qty: 5 },
      readonly: true,
    })
    expect(wrapper.find('.el-input-number').classes()).toContain('is-disabled')
  })

  it('change 事件：number 变更时回写 row[field] + emit change', async () => {
    const row: RowData = { qty: 1 }
    const wrapper = mountCell({
      col: { field: 'qty', label: '数量', type: 'number' },
      row,
    })
    const input = wrapper.find('.el-input-number input')
    await input.setValue('42')
    await input.trigger('blur')
    // 行数据被回写
    expect(row.qty).toBe(42)
    expect(wrapper.emitted('change')).toBeTruthy()
    expect(wrapper.emitted('change')!.at(-1)).toEqual([42])
  })
})
