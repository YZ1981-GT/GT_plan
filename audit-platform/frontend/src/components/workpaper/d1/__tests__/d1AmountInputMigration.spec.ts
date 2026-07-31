/**
 * D1 披露表可编辑金额输入组件守卫
 *
 * 🔴 平台已定论（双证）：element-plus 2.13.6 的 `input-number` **不存在**
 * `formatter` / `parser` prop（编译产物全文无 `formatter`），挂
 * `:formatter="amountFormatter"` 是未知属性、千分符不生效；浏览器实测输
 * 1234567.5 显示 `1234567.50`（无千分符），换 `el-input` 后才是 `1,234,567.50`。
 * → 可编辑**金额**一律用共享 `WpAmountInput`。
 *
 * 同时锁住反向边界：利率 / 汇率 / 比例 / 笔数 / 年度 / 月份**绝不能**套用本组件
 * （它会强制两位小数 + 千分符）。
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const TAB = path.resolve(__dirname, '../D1TabDisclosure.vue')
const src = fs.readFileSync(TAB, 'utf-8')

/** 抽出所有自闭合组件标签（属性里的 `=>` 不含 `/>`，故非贪婪到 `/>` 安全） */
function tags(name: string): string[] {
  return [...src.matchAll(new RegExp(`<${name}\\b(.*?)/>`, 'gs'))].map(m => m[1])
}

/** 不得用 WpAmountInput 的字段（非金额） */
const NON_AMOUNT_HINTS = [
  'ratio', 'lossRate', 'Rate', 'rate',
  'precision', 'percent', 'count', 'year', 'month',
]

describe('D1 披露表金额输入组件', () => {
  it('已无 el-input-number（千分符不生效，禁止用于金额）', () => {
    expect(src).not.toContain('<el-input-number')
  })

  it('WpAmountInput 已引入且被实际使用', () => {
    expect(src).toMatch(/import WpAmountInput from '\.\.\/shared\/WpAmountInput\.vue'/)
    expect(tags('WpAmountInput').length).toBeGreaterThanOrEqual(20)
  })

  it('禁止出现 :formatter / :parser（EP input-number 无此 prop，是空操作）', () => {
    expect(src).not.toMatch(/:formatter=/)
    expect(src).not.toMatch(/:parser=/)
  })

  it('每个 WpAmountInput 都有 change 回写与 disabled 透传', () => {
    const offenders: string[] = []
    for (const attrs of tags('WpAmountInput')) {
      const flat = attrs.replace(/\s+/g, ' ').trim()
      if (!/@change=/.test(flat)) offenders.push(`缺 @change: ${flat.slice(0, 90)}`)
      if (!/:disabled=/.test(flat)) offenders.push(`缺 :disabled: ${flat.slice(0, 90)}`)
      // `v-model` 与 `:model-value` 都合法（组件 emit `update:modelValue`）
      if (!/(:model-value=|v-model=)/.test(flat)) offenders.push(`缺值绑定: ${flat.slice(0, 90)}`)
    }
    expect(offenders).toEqual([])
  })

  it('change 回调不再有 `?? 0` 兜底（组件保证 emit number）', () => {
    const offenders = tags('WpAmountInput')
      .filter(a => a.includes('?? 0'))
      .map(a => a.replace(/\s+/g, ' ').trim().slice(0, 90))
    expect(offenders).toEqual([])
  })

  it('🔴 反向边界：比例 / 损失率等非金额字段未套用 WpAmountInput', () => {
    const offenders: string[] = []
    for (const attrs of tags('WpAmountInput')) {
      const flat = attrs.replace(/\s+/g, ' ')
      for (const hint of NON_AMOUNT_HINTS) {
        if (flat.includes(hint)) offenders.push(`${hint} → ${flat.trim().slice(0, 90)}`)
      }
    }
    expect(
      offenders,
      'WpAmountInput 强制两位小数 + 千分符，利率/比例/笔数/年度绝不能套用',
    ).toEqual([])
  })

  it('比例与损失率仍是只读展示（走 fmtPct，不是输入框）', () => {
    // 分类表与组合表的比率列一律读时推导 → 只能展示，不得提供输入
    expect(src).toMatch(/fmtPct\(row\.ratio\)/)
    expect(src).toMatch(/fmtPct\(row\.lossRate/)
  })
})
