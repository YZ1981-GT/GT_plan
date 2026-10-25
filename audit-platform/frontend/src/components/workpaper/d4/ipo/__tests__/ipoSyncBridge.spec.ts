/**
 * D4 IPO 双模式回写投影纯函数判据 —— rows ↔ OO sheet 数据区。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 1 · Task 2
 *
 * 判据落到「行为」（真跑 rowsToSheet / sheetToRows），不是「字符串存在」：
 *   - rows → sheet：checkbox → 1，null → 空单元格（不写占位文本），amount 写数值
 *   - sheet → rows：全空行跳过（不产生幽灵空行）、checkbox 1/true/Y/是 → true、
 *     非数字（含 12.3%）解析失败 → null（禁写 NaN）、seq 列不参与投影
 *   - 数值容差 0.005
 *
 * 🔴 Wave 1 阶段必须先红：ipoChecklistSchema.ts 尚不存在。
 *
 * Property 6/7/8（requirements.md）。checkbox 映射实测依据 = D4-27 源模板 C16=1/G16=1。
 */
import { describe, it, expect } from 'vitest'

// 动态 import 让「文件不存在」表现为该 describe 全红，而非整文件 crash 到无法收集。
import * as schema from '../ipoChecklistSchema'

const D4_27 = schema.SHEET_SPECS?.['D4-27']

describe('ipoChecklistSchema 存在且导出投影纯函数', () => {
  it('导出 SHEET_SPECS / rowsToSheet / sheetToRows', () => {
    expect(schema.SHEET_SPECS).toBeTruthy()
    expect(typeof schema.rowsToSheet).toBe('function')
    expect(typeof schema.sheetToRows).toBe('function')
  })
})

describe('rows → sheet 投影（Property 6）', () => {
  it('checkbox true → 1、false/空 → 空单元格；amount 写数值不写格式化串', () => {
    const spec = schema.SHEET_SPECS['D4-27']
    const rows = [
      { rowId: 'r1', seq: 1, name: '陈XX', isPersonalCustomer: false, isCustomerLegal: true, annualSales: 942.91 },
    ]
    const grid = schema.rowsToSheet(rows, spec)
    // grid 是二维数组（数据区行 × 列），按列规格顺序
    const row0 = grid[0]
    const keyIndex = (k: string) => spec.columns.findIndex((c: any) => c.key === k)
    expect(row0[keyIndex('isCustomerLegal')]).toBe(1) // checkbox true → 1
    // 个人客户 false → 空单元格（null / '' 均可，但不得是占位文本 '否'/'0'）
    const personal = row0[keyIndex('isPersonalCustomer')]
    expect(personal === null || personal === '' || personal === undefined).toBe(true)
    // amount 是数值
    expect(row0[keyIndex('annualSales')]).toBeCloseTo(942.91, 3)
    expect(typeof row0[keyIndex('annualSales')]).toBe('number')
  })
})

describe('sheet → rows 投影（Property 7/8）', () => {
  const spec = () => schema.SHEET_SPECS['D4-27']
  const colIdx = (k: string) => spec().columns.findIndex((c: any) => c.key === k)

  function makeGridRow(vals: Record<string, unknown>): unknown[] {
    const row = new Array(spec().columns.length).fill(null)
    for (const [k, v] of Object.entries(vals)) row[colIdx(k)] = v
    return row
  }

  it('全空数据区行被跳过（不产生幽灵空行，Property 8）', () => {
    const grid = [
      makeGridRow({ name: '陈XX', isPersonalCustomer: 1 }),
      makeGridRow({}), // 全空
      new Array(spec().columns.length).fill(''),
    ]
    const rows = schema.sheetToRows(grid, spec())
    expect(rows.length).toBe(1)
    expect(rows[0]['name']).toBe('陈XX')
  })

  it('checkbox 1 / true / Y / 是 → true（D4-27 源模板 1 是勾选态）', () => {
    const grid = [
      makeGridRow({ name: 'a', isPersonalCustomer: 1 }),
      makeGridRow({ name: 'b', isPersonalCustomer: 'Y' }),
      makeGridRow({ name: 'c', isPersonalCustomer: '是' }),
      makeGridRow({ name: 'd', isPersonalCustomer: true }),
      makeGridRow({ name: 'e', isPersonalCustomer: '' }),
    ]
    const rows = schema.sheetToRows(grid, spec())
    expect(rows[0]['isPersonalCustomer']).toBe(true)
    expect(rows[1]['isPersonalCustomer']).toBe(true)
    expect(rows[2]['isPersonalCustomer']).toBe(true)
    expect(rows[3]['isPersonalCustomer']).toBe(true)
    expect(rows[4]['isPersonalCustomer']).toBe(false)
  })

  it('number/amount 非数字解析失败 → null（禁写 NaN）', () => {
    const grid = [
      makeGridRow({ name: 'a', annualSales: 'abc' }),
      makeGridRow({ name: 'b', annualSales: '12.3%' }),
    ]
    const rows = schema.sheetToRows(grid, spec())
    expect(rows[0]['annualSales']).toBeNull()
    // 12.3% 按百分比数值解析
    expect(rows[1]['annualSales']).toBeCloseTo(0.123, 3)
    expect(Number.isNaN(rows[0]['annualSales'])).toBe(false)
  })

  it('数值容差往返一致（rows → sheet → rows）', () => {
    const orig = [{ rowId: 'r1', seq: 1, name: '陈XX', isPersonalCustomer: true, annualSales: 942.91 }]
    const grid = schema.rowsToSheet(orig, spec())
    const back = schema.sheetToRows(grid, spec())
    expect(back[0]['annualSales']).toBeCloseTo(942.91, 3)
    expect(back[0]['isPersonalCustomer']).toBe(true)
    expect(back[0]['name']).toBe('陈XX')
  })
})

describe('两级表头 sheet 投影保留结构（D4-28 核查方式 5 子列）', () => {
  it('sheetToRows 能按列规格 key 读回 5 个 checkbox 子列', () => {
    const spec = schema.SHEET_SPECS['D4-28']
    const subCols = spec.columns.filter((c: any) => c.group)
    expect(subCols.length).toBe(5)
    const row = new Array(spec.columns.length).fill(null)
    const idx = (k: string) => spec.columns.findIndex((c: any) => c.key === k)
    row[idx('customerName')] = 'A公司'
    row[idx(subCols[0].key)] = 1
    const rows = schema.sheetToRows([row], spec)
    expect(rows.length).toBe(1)
    expect(rows[0][subCols[0].key]).toBe(true)
  })
})

// 稳住 D4_27 引用以免 lint 未用变量（同时校验顶层 import 真拿到了 spec）
describe('顶层 import 拿到 D4-27 spec', () => {
  it('D4-27 有 18 列', () => {
    expect(D4_27?.columns?.length).toBe(18)
  })
})
