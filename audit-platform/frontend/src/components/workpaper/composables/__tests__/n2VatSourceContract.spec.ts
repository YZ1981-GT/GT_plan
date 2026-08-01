/**
 * n2VatSourceContract.spec.ts — N2-6 增值税测算表源模板契约守卫
 *
 * Task 5.2: 固定项 label 逐字比对 / 源码断言 _currentRaw 不含派生键 /
 *           附加分析区三键未被改写 / 解构键集 ⊆ 返回键集
 * Requirements: 8.1, 8.3, 8.5
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  N2_VAT_DECLARATION_ITEMS,
  N2_VAT_SPECIAL_ITEMS,
} from '../useN2VatSourceEngine'

// ─── 源码读取 + stripComments ────────────────────────────────────────────────

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*/g, '')
}

const SOURCE_CALC_PATH = path.resolve(__dirname, '../useN2VatSourceCalc.ts')
const SOURCE_CALC_RAW = fs.readFileSync(SOURCE_CALC_PATH, 'utf-8')
const SOURCE_CALC_CODE = stripComments(SOURCE_CALC_RAW)

const VAT_CALC_PATH = path.resolve(__dirname, '../useN2VatCalc.ts')
const VAT_CALC_RAW = fs.readFileSync(VAT_CALC_PATH, 'utf-8')
const VAT_CALC_CODE = stripComments(VAT_CALC_RAW)

const VUE_PATH = path.resolve(__dirname, '../../n2/calc/N2TabVatCalc.vue')
const VUE_RAW = fs.readFileSync(VUE_PATH, 'utf-8')
const VUE_CODE = stripComments(VUE_RAW)

// ─── 固定项 label 逐字比对（测试内写死字面量，不引用模块常量） ─────────────────

describe('固定项 label 逐字比对', () => {
  it('（一）申报表核对 10 项 label 逐字一致', () => {
    const EXPECTED_DECLARATION_LABELS = [
      '1.按适用税率征税销售额',
      '2.视同销售',
      '3.按简易征收办法征税货物',
      '4.免、抵、退办法出口销售额',
      '5.免税销售额',
      '6.销项税额',
      '7.进项税额',
      '8.进项税额转出',
      '9.免、抵、退应退税额',
      '10.其他',
    ]
    const actualLabels = N2_VAT_DECLARATION_ITEMS.map(i => i.label)
    expect(actualLabels).toEqual(EXPECTED_DECLARATION_LABELS)
  })

  it('（四）特殊情况检查 4 项 label 逐字一致', () => {
    const EXPECTED_SPECIAL_LABELS = [
      '视同销售',
      '大额进项税转出',
      '转让金融商品应交增值税额',
      '代扣代缴增值税额',
    ]
    const actualLabels = N2_VAT_SPECIAL_ITEMS.map(i => i.label)
    expect(actualLabels).toEqual(EXPECTED_SPECIAL_LABELS)
  })
})

// ─── 源码断言：_currentRaw 不含派生键 ───────────────────────────────────────

describe('_currentRaw 不含派生键（派生列禁持久化）', () => {
  // 反向自检：源码确实含 _currentRaw 或等效 _xxxRaw 函数
  it('反向自检：useN2VatSourceCalc.ts 含 _declarationRaw/_outputRaw/_inputRaw', () => {
    expect(SOURCE_CALC_CODE).toContain('_declarationRaw')
    expect(SOURCE_CALC_CODE).toContain('_outputRaw')
    expect(SOURCE_CALC_CODE).toContain('_inputRaw')
  })

  /**
   * 在 _xxxRaw() 附近不应出现派生键名。
   * 派生列 = diff / outputTax / inputTax / taxableRevenue / isMatch
   */
  const DERIVED_KEYS = ['diff', 'outputTax', 'inputTax', 'taxableRevenue', 'isMatch']

  it.each(DERIVED_KEYS)('_declarationRaw 附近不含派生键 "%s"', (key) => {
    const rawFn = SOURCE_CALC_CODE.match(/function _declarationRaw\(\)[^}]*\}/s)?.[0] ?? ''
    expect(rawFn.length).toBeGreaterThan(10) // 确保匹配到了函数体
    expect(rawFn).not.toContain(key)
  })

  it.each(DERIVED_KEYS)('_outputRaw 附近不含派生键 "%s"', (key) => {
    const rawFn = SOURCE_CALC_CODE.match(/function _outputRaw\(\)[^}]*\}/s)?.[0] ?? ''
    expect(rawFn.length).toBeGreaterThan(10)
    expect(rawFn).not.toContain(key)
  })

  it.each(DERIVED_KEYS)('_inputRaw 附近不含派生键 "%s"', (key) => {
    const rawFn = SOURCE_CALC_CODE.match(/function _inputRaw\(\)[^}]*\}/s)?.[0] ?? ''
    expect(rawFn.length).toBeGreaterThan(10)
    expect(rawFn).not.toContain(key)
  })
})

// ─── 附加分析区三键未被改写 ─────────────────────────────────────────────────

describe('附加分析区三键未被改写', () => {
  // 反向自检：useN2VatCalc.ts 确实存在且非空
  it('反向自检：useN2VatCalc.ts 源码非空', () => {
    expect(VAT_CALC_RAW.length).toBeGreaterThan(100)
  })

  it('useN2VatCalc.ts 含 vat-rows 键', () => {
    expect(VAT_CALC_CODE).toContain('vat-rows')
  })

  it('useN2VatCalc.ts 含 period-mode 键', () => {
    expect(VAT_CALC_CODE).toContain('period-mode')
  })

  it('useN2VatCalc.ts 含 declared-payable-vat 键', () => {
    expect(VAT_CALC_CODE).toContain('declared-payable-vat')
  })
})

// ─── 解构键集 ⊆ 返回键集 ────────────────────────────────────────────────────

describe('解构键集 ⊆ 返回键集（含 stripComments 自检）', () => {
  // 反向自检：原始源码确实含 sourceCalc.
  it('反向自检：N2TabVatCalc.vue 原始源码含 "sourceCalc."', () => {
    expect(VUE_RAW).toContain('sourceCalc.')
  })

  it('反向自检：stripComments 后源码非空', () => {
    expect(VUE_CODE.length).toBeGreaterThan(100)
  })

  it('组件使用的 sourceCalc.xxx 全部在 useN2VatSourceCalc 的 return 中', () => {
    // 从 Vue 组件源码中提取 sourceCalc.xxx 的所有 xxx
    const usedKeys = new Set<string>()
    const re = /sourceCalc\.(\w+)/g
    let m: RegExpExecArray | null
    while ((m = re.exec(VUE_CODE)) !== null) {
      usedKeys.add(m[1])
    }

    expect(usedKeys.size).toBeGreaterThan(0) // 确保提取到了

    // 从 useN2VatSourceCalc.ts 提取 return {} 的键集
    const returnBlock = SOURCE_CALC_CODE.match(/return\s*\{([^}]+)\}\s*\}\s*$/ms)?.[1] ?? ''
    expect(returnBlock.length).toBeGreaterThan(10) // 确保匹配到了

    const returnedKeys = new Set<string>()
    const keyRe = /(\w+),?/g
    let km: RegExpExecArray | null
    while ((km = keyRe.exec(returnBlock)) !== null) {
      returnedKeys.add(km[1])
    }

    expect(returnedKeys.size).toBeGreaterThan(0) // 确保提取到了

    // usedKeys ⊆ returnedKeys
    for (const key of usedKeys) {
      // 跳过 .value（不是属性名而是 .value 后缀）
      if (key === 'value') continue
      expect(returnedKeys.has(key)).toBe(true)
    }
  })
})
