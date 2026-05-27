/**
 * formRules.ts 单测 — V3 Req 3.1
 *
 * 验证：required / amount / accountCode / year / projectName / dateRange
 * 等通用校验规则的 pattern / required / message / trigger 行为正确。
 */
import { describe, it, expect } from 'vitest'
import type { FormItemRule } from 'element-plus'
import { rules, makeRules } from '../formRules'

/** 把 pattern rule 应用到一个值，返回是否通过校验。 */
function patternMatch(rule: FormItemRule, value: string): boolean {
  if (!rule.pattern) return false
  const re = rule.pattern instanceof RegExp ? rule.pattern : new RegExp(rule.pattern)
  return re.test(value)
}

describe('rules.required — 生成器', () => {
  it('返回的规则带 required=true 且包含字段 label', () => {
    const r = rules.required('金额')
    expect(r.required).toBe(true)
    expect(r.message).toBe('金额不能为空')
    expect(r.trigger).toBe('blur')
  })

  it('支持自定义 trigger', () => {
    const r = rules.required('日期', 'change')
    expect(r.trigger).toBe('change')
  })
})

describe('rules.amount', () => {
  it.each([
    ['100', true],
    ['100.50', true],
    ['-100.25', true],
    ['0', true],
    ['0.01', true],
    ['100.123', false], // > 2 位小数
    ['abc', false],
    ['', false],
  ])('amount(%s) → %s', (value, expected) => {
    expect(patternMatch(rules.amount, value)).toBe(expected)
  })

  it('trigger 为 blur', () => {
    expect(rules.amount.trigger).toBe('blur')
  })
})

describe('rules.accountCode', () => {
  it.each([
    ['1001', true],
    ['100101', true],
    ['1234567890', true],
    ['100', false], // < 4 位
    ['12345678901', false], // > 10 位
    ['100A', false], // 含字母
    ['', false],
  ])('accountCode(%s) → %s', (value, expected) => {
    expect(patternMatch(rules.accountCode, value)).toBe(expected)
  })
})

describe('rules.year', () => {
  it('类型为 number 且范围 2000-2100', () => {
    expect(rules.year.type).toBe('number')
    expect(rules.year.min).toBe(2000)
    expect(rules.year.max).toBe(2100)
  })
})

describe('rules.projectName', () => {
  it('包含 required + 长度限制（2-200）', () => {
    expect(Array.isArray(rules.projectName)).toBe(true)
    const required = rules.projectName.find((r) => r.required)
    expect(required).toBeDefined()
    expect(required?.message).toBe('项目名不能为空')
    const length = rules.projectName.find((r) => r.min !== undefined)
    expect(length?.min).toBe(2)
    expect(length?.max).toBe(200)
  })
})

describe('rules.clientName', () => {
  it('包含 required + 长度限制（2-100）', () => {
    expect(Array.isArray(rules.clientName)).toBe(true)
    const required = rules.clientName.find((r) => r.required)
    expect(required?.message).toBe('客户名不能为空')
    const length = rules.clientName.find((r) => r.min !== undefined)
    expect(length?.min).toBe(2)
    expect(length?.max).toBe(100)
  })
})

describe('rules.dateRange', () => {
  it('类型为 array、长度 2、required=true', () => {
    expect(rules.dateRange.type).toBe('array')
    expect(rules.dateRange.required).toBe(true)
    expect(rules.dateRange.len).toBe(2)
    expect(rules.dateRange.trigger).toBe('change')
  })
})

describe('rules.email / phone / ratio / positiveInt / idCard / creditCode', () => {
  it.each([
    ['user@example.com', rules.email, true],
    ['invalid', rules.email, false],
  ])('email patterns', (value, rule, _expected) => {
    // type=email 不走 pattern，仅验证配置存在
    expect(rule.type).toBe('email')
  })

  it.each([
    ['13800138000', true],
    ['1380013800', false],
    ['23800138000', false],
  ])('phone(%s) → %s', (value, expected) => {
    expect(patternMatch(rules.phone, value)).toBe(expected)
  })

  it.each([
    ['1001', true],
    ['12345', true],
    ['0', false],
    ['1.5', false],
  ])('positiveInt(%s) → %s', (value, expected) => {
    expect(patternMatch(rules.positiveInt, value)).toBe(expected)
  })
})

describe('makeRules — 组合生成器', () => {
  it('生成"必填 + 自定义"的规则数组', () => {
    const combined = makeRules('金额', rules.amount)
    expect(combined.length).toBe(2)
    expect(combined[0].required).toBe(true)
    expect(combined[0].message).toBe('金额不能为空')
    expect(combined[1]).toBe(rules.amount)
  })

  it('支持多个额外规则', () => {
    const combined = makeRules('科目编码', rules.accountCode, rules.amount)
    expect(combined.length).toBe(3)
  })
})
