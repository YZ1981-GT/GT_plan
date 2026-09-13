/**
 * ipoChecklistFormulaEngine.ts — D4-25/26/27/28 表内计算引擎
 *
 * 负责：
 * 1. 解析 $col 引用（引用列规格 key，非 label）
 * 2. 表内计算：SUM($col)（当前全部行求和）+ 四则运算
 * 3. 派生列（derived:true）默认只读；用户手填 → 锁定不再重算
 *
 * 🔴 分母为 0 → null，不返回 0、不显示 0%、不抛除零
 * 🔴 求值失败 → fail-visible（记 ERROR 态，不吞成空值）
 * 🔴 覆盖按 project/year/scope，不回写平台预设真源
 */

import type { RowRecord } from './ipoChecklistSchema'
import { IPO_FORMULA_PRESETS, type IpoFormulaPreset } from './ipoChecklistSchema'

export interface FormulaResult {
  value: number | null
  error: string | null
  applied: boolean
}

/**
 * 对单行单列求表内计算值
 *
 * @param row 当前行数据
 * @param allRows 全部行数据（用于 SUM 跨行聚合）
 * @param preset 公式预设条目
 * @returns FormulaResult
 */
export function evaluateIntraSheet(
  row: RowRecord,
  allRows: readonly RowRecord[],
  preset: IpoFormulaPreset,
): FormulaResult {
  if (preset.category !== 'intra_sheet' || !preset.expression) {
    return { value: null, error: 'not intra_sheet', applied: false }
  }

  try {
    const result = evalExpression(preset.expression, row, allRows, preset.precision)
    return { value: result, error: null, applied: result !== null }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return { value: null, error: `求值失败: ${msg}`, applied: false }
  }
}

/**
 * 解析并求值表达式
 *
 * 支持的语法：
 * - $colKey → 当前行该列的数值
 * - SUM($colKey) → 全部行该列数值求和
 * - 四则运算 +, -, *, /
 * - 括号分组
 *
 * 🔴 分母为 0 → null
 */
function evalExpression(
  expr: string,
  row: RowRecord,
  allRows: readonly RowRecord[],
  precision: number,
): number | null {
  // 替换 SUM($xxx) → 聚合值
  // 支持两种形式：
  // 1. SUM($col) → 该列在全部行上的求和
  // 2. SUM($col1,$col2,...) → 当前行多列值求和
  let processed = expr.replace(/SUM\(([^)]+)\)/g, (_match, inner: string) => {
    const refs = inner.split(',').map(s => s.trim())
    // 判断是否为多列引用（逗号分隔的多个 $col）
    if (refs.length > 1) {
      // 多列引用：当前行内多列求和
      let sum = 0
      let hasAny = false
      for (const ref of refs) {
        const colMatch = ref.match(/^\$(\w+)$/)
        if (colMatch) {
          const v = toNum(row[colMatch[1]])
          if (v !== null) {
            sum += v
            hasAny = true
          }
        }
      }
      return hasAny ? String(sum) : 'NaN'
    } else {
      // 单列引用：全部行跨行求和
      const colMatch = refs[0].match(/^\$(\w+)$/)
      if (!colMatch) return 'NaN'
      const colKey = colMatch[1]
      let sum = 0
      let hasAny = false
      for (const r of allRows) {
        const v = toNum(r[colKey])
        if (v !== null) {
          sum += v
          hasAny = true
        }
      }
      return hasAny ? String(sum) : 'NaN'
    }
  })

  // 替换 $colKey → 当前行值
  processed = processed.replace(/\$(\w+)/g, (_match, colKey: string) => {
    const v = toNum(row[colKey])
    return v !== null ? String(v) : 'NaN'
  })

  // 清理引号（expression 里可能有 '$xxx' 形式的引用，引号在替换后残留）
  processed = processed.replace(/'/g, '')

  // 检查是否包含 NaN（任一依赖值为空 → 返回 null）
  if (processed.includes('NaN')) {
    return null
  }

  // 安全求值（只允许数字和四则运算符+括号+空白+小数点+负号）
  if (!/^[\d\s+\-*/().e]+$/i.test(processed)) {
    throw new Error(`表达式含非法字符: ${processed}`)
  }

  // eslint-disable-next-line no-eval
  const raw = Function(`"use strict"; return (${processed})`)() as number

  if (!Number.isFinite(raw)) {
    // 除零等情况 → null
    return null
  }

  return round(raw, precision)
}

function toNum(val: unknown): number | null {
  if (val === null || val === undefined || val === '' || val === false) return null
  if (val === true) return 1
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : null
}

function round(v: number, precision: number): number {
  const factor = Math.pow(10, precision)
  return Math.round(v * factor) / factor
}

// ═══════════════════════════════════════════════════════════════════════
// 批量重算
// ═══════════════════════════════════════════════════════════════════════

/** 手填覆盖标记：{ [sheetCode:columnKey:rowId]: manualValue } */
export type ManualOverrides = Map<string, number | null>

function overrideKey(sheetCode: string, columnKey: string, rowId: string): string {
  return `${sheetCode}:${columnKey}:${rowId}`
}

/**
 * 对全部行重算所有表内计算列
 *
 * @param sheetCode 表 code
 * @param rows 全部行（会被就地修改）
 * @param overrides 手填覆盖映射
 * @returns 错误列表（可用于 fail-visible 展示）
 */
export function recalcAllDerived(
  sheetCode: string,
  rows: RowRecord[],
  overrides: ManualOverrides,
): string[] {
  const presets = IPO_FORMULA_PRESETS.filter(
    p => p.sheetCode === sheetCode && p.category === 'intra_sheet'
  )
  const errors: string[] = []

  for (const preset of presets) {
    for (const row of rows) {
      const oKey = overrideKey(sheetCode, preset.columnKey, row.rowId)
      // 手填覆盖 → 不重算
      if (overrides.has(oKey)) {
        row[preset.columnKey] = overrides.get(oKey) ?? null
        continue
      }

      const result = evaluateIntraSheet(row, rows, preset)
      if (result.error) {
        errors.push(`${sheetCode} 行 ${row.rowId} 列 ${preset.columnKey}: ${result.error}`)
      }
      row[preset.columnKey] = result.value
    }
  }

  return errors
}

/**
 * 标记手填覆盖
 */
export function setManualOverride(
  overrides: ManualOverrides,
  sheetCode: string,
  columnKey: string,
  rowId: string,
  value: number | null,
): void {
  overrides.set(overrideKey(sheetCode, columnKey, rowId), value)
}

/**
 * 清除手填覆盖（恢复为公式计算）
 */
export function clearManualOverride(
  overrides: ManualOverrides,
  sheetCode: string,
  columnKey: string,
  rowId: string,
): void {
  overrides.delete(overrideKey(sheetCode, columnKey, rowId))
}
