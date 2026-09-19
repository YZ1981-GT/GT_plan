/**
 * WpAmountInput 组件行为守卫 —— 千分符 / 防 NaN / 持久化 number
 *
 * Spec: `.kiro/specs/amount-input-migration-and-column-typing/`
 * 锁定 Property 15（非法输入不写 NaN）/ 16（持久化值仍为 number，不得带逗号字符串）
 * 以及 Task 6 的组件层判据（输 `1234567.5` → 失焦显示 `1,234,567.50`）。
 *
 * 🔴 立项时该组件**无任何单测** —— 迁移把 61 处金额列指向它，其千分符/防 NaN 行为
 * 却无测试锁定，任何回归都不会被发现。本 spec 补齐组件层守卫。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WpAmountInput from '../WpAmountInput.vue'
import { amountFormatter, amountParser } from '../../composables/wpAmountInput'

describe('amountFormatter / amountParser 纯函数', () => {
  it('格式化为千分符 + 两位小数', () => {
    expect(amountFormatter(1234567.5)).toBe('1,234,567.50')
    expect(amountFormatter(50000)).toBe('50,000.00')
    expect(amountFormatter(0)).toBe('0.00')
    expect(amountFormatter(9871.4)).toBe('9,871.40')
  })

  it('parser 去掉千分符逗号', () => {
    expect(amountParser('1,234,567.50')).toBe('1234567.50')
    expect(amountParser('50,000.00')).toBe('50000.00')
  })
})

describe('WpAmountInput 组件（Property 15 / 16 + Task 6 组件层判据）', () => {
  const mountInput = (modelValue: number) =>
    mount(WpAmountInput, {
      props: { modelValue },
      global: { plugins: [ElementPlus] },
    })

  it('失焦态显示千分符（输 1234567.5 → 1,234,567.50）', () => {
    const w = mountInput(1234567.5)
    expect(w.find('input').element.value).toBe('1,234,567.50')
  })

  it('合法输入失焦：emit 的是 number，不是带逗号字符串（Property 16）', async () => {
    const w = mountInput(0)
    const input = w.find('input')
    await input.trigger('focus')
    await input.setValue('1234567.5')
    await input.trigger('blur')
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe(1234567.5)
    expect(typeof emitted![0][0]).toBe('number')
  })

  it('粘贴带逗号的金额可解析（1,234,567.50 → 1234567.5）', async () => {
    const w = mountInput(0)
    const input = w.find('input')
    await input.trigger('focus')
    await input.setValue('1,234,567.50')
    await input.trigger('blur')
    expect(w.emitted('update:modelValue')![0][0]).toBe(1234567.5)
  })

  it('非法输入失焦：不 emit、不写 NaN，回退上一次有效值（Property 15）', async () => {
    const w = mountInput(100)
    const input = w.find('input')
    await input.trigger('focus')
    await input.setValue('abc')
    await input.trigger('blur')
    expect(w.emitted('update:modelValue')).toBeFalsy()
    // 回退到失焦格式化态
    expect(input.element.value).toBe('100.00')
  })

  it('值未变化时不重复 emit', async () => {
    const w = mountInput(500)
    const input = w.find('input')
    await input.trigger('focus')
    await input.setValue('500')
    await input.trigger('blur')
    expect(w.emitted('update:modelValue')).toBeFalsy()
  })
})
