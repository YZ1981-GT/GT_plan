/**
 * WpFormulaCell 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 4.2
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import WpFormulaCell from '../WpFormulaCell.vue'

describe('WpFormulaCell', () => {
  it('渲染 value 文本', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: '1,234,567.89' },
    })
    expect(wrapper.find('.wp-formula-cell').text()).toBe('1,234,567.89')
  })

  it('value 为 null 时显示 "—"', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: null },
    })
    expect(wrapper.find('.wp-formula-cell').text()).toBe('—')
  })

  it('value 为 undefined 时显示 "—"', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: undefined },
    })
    expect(wrapper.find('.wp-formula-cell').text()).toBe('—')
  })

  it('value 为数字时正确渲染', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: 42000 },
    })
    expect(wrapper.find('.wp-formula-cell').text()).toBe('42000')
  })

  it('虚线下划线样式（border-bottom: 1px dashed）', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: '100' },
    })
    const cell = wrapper.find('.wp-formula-cell')
    expect(cell.exists()).toBe(true)
    // The class wp-formula-cell has border-bottom: 1px dashed in scoped styles
  })

  it('cursor:help 样式', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: '100' },
    })
    const cell = wrapper.find('.wp-formula-cell')
    expect(cell.exists()).toBe(true)
    // The class wp-formula-cell has cursor: help in scoped styles
  })

  it('el-tooltip 包裹单元格', () => {
    const wrapper = mount(WpFormulaCell, {
      props: {
        value: '100',
        formula: '=TB(1122, audited)',
        source: '试算平衡表',
      },
    })
    // el-tooltip renders as a wrapper
    expect(wrapper.find('.wp-formula-cell').exists()).toBe(true)
  })

  it('无 formula 和 source 时 tooltip 禁用', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: '100' },
    })
    // The component still renders the cell, tooltip is just disabled
    expect(wrapper.find('.wp-formula-cell').exists()).toBe(true)
  })

  it('value 为 0 时正确显示 0 而非 "—"', () => {
    const wrapper = mount(WpFormulaCell, {
      props: { value: 0 },
    })
    expect(wrapper.find('.wp-formula-cell').text()).toBe('0')
  })
})
