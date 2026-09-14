/**
 * blockNumberFormat.spec.ts — 非金额数值列只读态格式化（Task 8 最小单测）
 *
 * 本文件只覆盖 Task 8 引入的纯函数与 `CheckBlock.vue` 三处分流的可用性。
 * 金额语义双向锁死守卫（Property 9/10/11/12）属 Task 12 的
 * `blockColumnAmountRender.spec.ts`，**不在此实现**。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { formatPlainNumber } from '../blockNumberFormat'

const HERE = dirname(fileURLToPath(import.meta.url))
const CHECK_BLOCK = resolve(HERE, '../CheckBlock.vue')

describe('formatPlainNumber — 非金额数值列', () => {
  it('空值返回空串（不返 —，数量为空与金额为空语义不同）', () => {
    expect(formatPlainNumber(null)).toBe('')
    expect(formatPlainNumber(undefined)).toBe('')
    expect(formatPlainNumber('')).toBe('')
  })

  it('加千分位分组但不强制小数位、不做金额单位换算', () => {
    expect(formatPlainNumber(1200)).toBe('1,200')
    expect(formatPlainNumber(1234567)).toBe('1,234,567')
    // 金额格式会显示 1,234,567.50；非金额列保留原小数位
    expect(formatPlainNumber(1234567.5)).toBe('1,234,567.5')
    expect(formatPlainNumber(0)).toBe('0')
  })

  it('非有限数值原样透传，不显示 NaN', () => {
    expect(formatPlainNumber('abc')).toBe('abc')
    expect(formatPlainNumber(Number.NaN)).toBe('NaN')
    expect(formatPlainNumber(Number.POSITIVE_INFINITY)).toBe('Infinity')
  })
})

describe('CheckBlock.vue — 三处按 render 分流', () => {
  const src = readFileSync(CHECK_BLOCK, 'utf-8')

  it('抽取到源码（防断言空转）', () => {
    expect(src.length).toBeGreaterThan(1000)
    expect(src).toContain("col.type === 'number'")
  })

  it('编辑态：金额分支用 WpAmountInput，非金额分支仍是 el-input type=number', () => {
    expect(src).toContain('<WpAmountInput')
    expect(src).toContain("col.render === 'amount'")
    // 非金额分支逐字保留（零回归支点）
    expect(src).toContain('v-model.number="row[col.field]"')
    expect(src).toContain('type="number"')
  })

  it('只读态与合计行走同一对函数，且不再无条件对全部 number 列调 prefs.fmt', () => {
    expect(src).toContain('formatCell(row[col.field], col.render)')
    expect(src).toContain('getFieldRender(field as string)')
    // 旧的无条件实现已移除
    expect(src).not.toContain('function formatNumber')
  })

  it('金额格式走 inject 优先的 store 成员（平台铁律）', () => {
    expect(src).toContain('inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()')
    expect(src).not.toContain("import { fmtAmount }")
  })
})
