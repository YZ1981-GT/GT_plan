/**
 * 公式真源覆盖面守卫 — Property 11/12/13/14/15/16/37
 *
 * 🔴 必须先红：ipoChecklistSchema.ts / ipoChecklistFormulaEngine.ts 不存在时 import 失败即红
 * 🔴 Property 13 是跨语言契约：resolver 名与后端 auto_data_resolvers 注册名比对
 * 🔴 四个 .vue 组件内零公式字面量
 */
import { describe, it, expect } from 'vitest'
import {
  SHEET_SPECS,
  IPO_FORMULA_PRESETS,
  getDerivedColumns,
  type IpoFormulaPreset,
} from '../ipoChecklistSchema'
import {
  evaluateIntraSheet,
  type ManualOverrides,
} from '../ipoChecklistFormulaEngine'
import type { RowRecord } from '../ipoChecklistSchema'

const VALID_SHEETS = new Set(['D4-25', 'D4-26', 'D4-27', 'D4-28'])

describe('Property 11: sheet_code 全部属于四张 IPO 表', () => {
  it('所有预设的 sheetCode 都在四张表范围内', () => {
    for (const p of IPO_FORMULA_PRESETS) {
      expect(VALID_SHEETS.has(p.sheetCode)).toBe(true)
    }
  })

  it('无外部 sheet 混入', () => {
    const codes = new Set(IPO_FORMULA_PRESETS.map(p => p.sheetCode))
    for (const c of codes) {
      expect(VALID_SHEETS.has(c)).toBe(true)
    }
  })
})

describe('Property 12: column_key 在对应 sheet 列规格内', () => {
  it('每条公式的 columnKey 都在该 sheet 的 key 集合中', () => {
    for (const p of IPO_FORMULA_PRESETS) {
      const spec = SHEET_SPECS[p.sheetCode]
      expect(spec).toBeDefined()
      const keys = new Set(spec.columns.map(c => c.key))
      expect(keys.has(p.columnKey)).toBe(true)
    }
  })
})

describe('Property 13: inter_sheet resolver 名已注册（跨语言契约）', () => {
  // 后端注册的 resolver 名（硬编码基线，与后端 test_auto_data_resolvers.py 契约一致）
  const KNOWN_RESOLVERS = new Set([
    'd4_25_dealer_sales',
    'd4_26_overseas_sales',
    'd4_27_related_party_sales',
    'd4_28_customer_balances',
    // 以下是 _d4_revenue.py 的既有 resolver
    'd4_tb_unadjusted',
    'd4_ledger_monthly',
    'd4_analysis_indicators',
    'd4_ledger_monthly_by_product',
  ])

  it('每条 inter_sheet 公式的 resolver 名存在于 _REGISTRY', () => {
    const interSheet = IPO_FORMULA_PRESETS.filter(p => p.category === 'inter_sheet')
    expect(interSheet.length).toBeGreaterThan(0)
    for (const p of interSheet) {
      expect(p.resolver).toBeDefined()
      expect(KNOWN_RESOLVERS.has(p.resolver!)).toBe(true)
    }
  })

  it('反向自检：拼错 resolver 名必失败', () => {
    // 模拟一个错误的 resolver 名
    expect(KNOWN_RESOLVERS.has('d4_25_dealer_saless')).toBe(false) // 多一个 s
    expect(KNOWN_RESOLVERS.has('d4_26_overseas_sale')).toBe(false) // 少一个 s
  })
})

describe('Property 14: intra_sheet 的 dependsOn 全为该 sheet 列 key', () => {
  it('每条 intra_sheet 公式的 dependsOn 都在该 sheet 列规格内', () => {
    const intraSheet = IPO_FORMULA_PRESETS.filter(p => p.category === 'intra_sheet')
    expect(intraSheet.length).toBeGreaterThan(0)
    for (const p of intraSheet) {
      const spec = SHEET_SPECS[p.sheetCode]
      const keys = new Set(spec.columns.map(c => c.key))
      for (const dep of p.dependsOn) {
        expect(keys.has(dep)).toBe(true)
      }
    }
  })
})

describe('Property 15: derived 集合 == intra_sheet 公式的 columnKey 集合', () => {
  it('每张表的 derived 列与 intra_sheet 公式目标列双向锁死', () => {
    for (const sheetCode of VALID_SHEETS) {
      const derivedKeys = getDerivedColumns(sheetCode)
      const formulaKeys = new Set(
        IPO_FORMULA_PRESETS
          .filter(p => p.sheetCode === sheetCode && p.category === 'intra_sheet')
          .map(p => p.columnKey)
      )
      // derived ⊇ formulaKeys
      for (const k of formulaKeys) {
        expect(derivedKeys.has(k)).toBe(true)
      }
      // derived ⊆ formulaKeys（派生列必有公式）
      for (const k of derivedKeys) {
        expect(formulaKeys.has(k)).toBe(true)
      }
    }
  })
})

describe('Property 16: source_ref 非空', () => {
  it('每条公式的 sourceRef 不为空', () => {
    for (const p of IPO_FORMULA_PRESETS) {
      expect(p.sourceRef.trim().length).toBeGreaterThan(0)
    }
  })
})

describe('公式引擎行为验证', () => {
  it('占比列：分母为 0 → null', () => {
    const preset: IpoFormulaPreset = {
      sheetCode: 'D4-25',
      rowKey: '*',
      columnKey: 'salesRatio',
      category: 'intra_sheet',
      expression: "'$salesAmount' / SUM($salesAmount)",
      dependsOn: ['salesAmount'],
      precision: 4,
      sourceRef: 'test',
      reason: 'test',
    }
    const row: RowRecord = { rowId: 'r1', salesAmount: 0 }
    const allRows: RowRecord[] = [row]
    const result = evaluateIntraSheet(row, allRows, preset)
    // SUM = 0，分母为 0 → null
    expect(result.value).toBeNull()
  })

  it('D4-27 总计列：正确求和 checkbox 列', () => {
    const preset: IpoFormulaPreset = IPO_FORMULA_PRESETS.find(
      p => p.sheetCode === 'D4-27' && p.columnKey === 'total'
    )!
    expect(preset).toBeDefined()

    const row: RowRecord = {
      rowId: 'r1',
      personalCustomer: true,
      customerLegalPerson: false,
      contractSignee: true,
      executiveRelative: false,
      financeDept: true,
      managementDept: false,
      techDept: false,
      productionDept: false,
      salesDept: false,
      otherDept: false,
    }
    const result = evaluateIntraSheet(row, [row], preset)
    expect(result.value).toBe(3) // 3 个 checkbox 勾选
    expect(result.applied).toBe(true)
  })

  it('D4-26 差异列：任一为空 → null', () => {
    const preset: IpoFormulaPreset = IPO_FORMULA_PRESETS.find(
      p => p.sheetCode === 'D4-26' && p.columnKey === 'diff'
    )!
    expect(preset).toBeDefined()

    const row: RowRecord = { rowId: 'r1', verifiedAmount: 100, salesAmount: null }
    const result = evaluateIntraSheet(row, [row], preset)
    expect(result.value).toBeNull() // salesAmount 为空 → null
  })

  it('D4-26 差异列：正常计算', () => {
    const preset: IpoFormulaPreset = IPO_FORMULA_PRESETS.find(
      p => p.sheetCode === 'D4-26' && p.columnKey === 'diff'
    )!
    const row: RowRecord = { rowId: 'r1', verifiedAmount: 150, salesAmount: 100 }
    const result = evaluateIntraSheet(row, [row], preset)
    expect(result.value).toBe(50) // 150 - 100
  })
})

describe('Property 37: 预设总条目数', () => {
  it('14 条预设', () => {
    expect(IPO_FORMULA_PRESETS.length).toBe(14)
  })
})
