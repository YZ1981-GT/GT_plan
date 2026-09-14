/**
 * D4 IPO 表内计算公式引擎（intra_sheet）—— 纯函数，无 eval、无外链。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 3 · Task 8
 *
 * 支持的表达式形态（IPO_FORMULA_PRESETS 的全部 intra_sheet expression）：
 *   - `$col`                行内某列值（列 key，非 label）
 *   - `SUM($col)`           该列在**当前全部行**上的求和（跨行聚合）
 *   - `SUM($a, $b, ...)`    行内多列之和（行内聚合，D4-27 总计）
 *   - `+ - * /` 四则运算（左结合，无括号嵌套，够覆盖本 spec 全部预设）
 *
 * 🔴 分母为 0 / 空 → `null`（不返回 0、不显示 0%、不抛除零）。Property 21/26/33。
 * 🔴 派生列（derived）默认只读；用户手填 → 锁定为手填值不再重算（Property 15），
 *    该锁定由组件层记录 manualOverride，本引擎只负责「未手填时」的重算。
 * 🔴 不持有公式覆盖库：二次编辑走平台 F-SHELL v2 mutation（后端权威执行），
 *    本模块只做 HTML 侧预览计算。
 */

import type { ChecklistRow, IpoFormulaPreset } from './ipoChecklistSchema'
import { IPO_FORMULA_PRESETS } from './ipoChecklistSchema'

/** 行内取列值 → number（checkbox true→1/false→0；非数字→0 用于聚合，空值单独处理）。 */
function rowNum(row: Record<string, unknown>, key: string): number {
  const v = row[key]
  if (v === true) return 1
  if (v === false || v == null || v === '') return 0
  const n = typeof v === 'number' ? v : Number(String(v).replace(/,/g, '').replace(/%$/, ''))
  return Number.isFinite(n) ? n : 0
}

/** 行内取列值，区分「空」（返回 null）与 0。用于分子判空。 */
function rowNumOrNull(row: Record<string, unknown>, key: string): number | null {
  const v = row[key]
  if (v === true) return 1
  if (v === false) return 0
  if (v == null || v === '') return null
  const n = typeof v === 'number' ? v : Number(String(v).replace(/,/g, '').replace(/%$/, ''))
  return Number.isFinite(n) ? n : null
}

type Term =
  | { kind: 'col'; key: string }
  | { kind: 'sumCol'; key: string }
  | { kind: 'sumRow'; keys: string[] }
  | { kind: 'num'; value: number }

interface ParsedExpr {
  terms: Term[]
  /** 运算符序列，长度 = terms.length - 1 */
  ops: Array<'+' | '-' | '*' | '/'>
}

/** 解析一个 term（$col / SUM(...) / 数字）。 */
function parseTerm(raw: string): Term {
  const s = raw.trim()
  const sumMatch = s.match(/^SUM\((.+)\)$/i)
  if (sumMatch) {
    const inner = sumMatch[1]
    const args = inner.split(',').map((a) => a.trim())
    const keys = args.map((a) => {
      const m = a.match(/^\$(.+)$/)
      if (!m) throw new Error(`SUM 参数必须是 $col：${a}`)
      return m[1].trim()
    })
    if (keys.length === 1) return { kind: 'sumCol', key: keys[0] }
    return { kind: 'sumRow', keys }
  }
  const colMatch = s.match(/^\$(.+)$/)
  if (colMatch) return { kind: 'col', key: colMatch[1].trim() }
  const num = Number(s)
  if (Number.isFinite(num)) return { kind: 'num', value: num }
  throw new Error(`无法解析 term：${raw}`)
}

/** 解析整个表达式为 terms + ops（左结合，无括号）。 */
export function parseExpression(expression: string): ParsedExpr {
  // 按顶层运算符切分（表达式无括号嵌套，SUM(...) 内的逗号不是运算符）。
  const tokens: string[] = []
  const ops: Array<'+' | '-' | '*' | '/'> = []
  let depth = 0
  let cur = ''
  for (const ch of expression) {
    if (ch === '(') depth++
    if (ch === ')') depth--
    if (depth === 0 && (ch === '+' || ch === '-' || ch === '*' || ch === '/')) {
      tokens.push(cur)
      ops.push(ch)
      cur = ''
    } else {
      cur += ch
    }
  }
  tokens.push(cur)
  return { terms: tokens.map(parseTerm), ops }
}

/**
 * 求值一条表达式（对指定行 row，聚合跨 allRows）。
 * @returns number 或 null（分母为 0/空、或分子空时返回 null）
 */
export function evaluateExpression(
  expression: string,
  row: Record<string, unknown>,
  allRows: Array<Record<string, unknown>>,
): number | null {
  const { terms, ops } = parseExpression(expression)

  function termValue(t: Term): number | null {
    switch (t.kind) {
      case 'num':
        return t.value
      case 'col':
        return rowNumOrNull(row, t.key)
      case 'sumCol':
        return allRows.reduce((acc, r) => acc + rowNum(r, t.key), 0)
      case 'sumRow':
        return t.keys.reduce((acc, k) => acc + rowNum(row, k), 0)
    }
  }

  let acc = termValue(terms[0])
  for (let i = 0; i < ops.length; i++) {
    const rhs = termValue(terms[i + 1])
    const op = ops[i]
    if (op === '/') {
      // 分母为 0 / null → null（不显示 0%、不抛除零）
      if (rhs == null || rhs === 0) return null
      if (acc == null) return null
      acc = acc / rhs
    } else if (op === '*') {
      if (acc == null || rhs == null) return null
      acc = acc * rhs
    } else if (op === '+') {
      // 加减：null 视作 0（差异/总计允许部分为空时按 0 参与）
      acc = (acc ?? 0) + (rhs ?? 0)
    } else {
      // 差异 = 减法：任一为空 → null（Property 26：任一为空留空）
      if (acc == null || rhs == null) return null
      acc = acc - rhs
    }
  }
  return acc
}

/** 取某 sheet 某派生列的 intra_sheet 公式（预设真源）。 */
export function getIntraFormula(sheetCode: string, columnKey: string): IpoFormulaPreset | undefined {
  return IPO_FORMULA_PRESETS.find(
    (p) => p.sheetCode === sheetCode && p.columnKey === columnKey && p.category === 'intra_sheet',
  )
}

/**
 * 重算一张表全部 intra_sheet 派生列，写回 rows（不改手填锁定的列）。
 * @param manualLocks Set of `${rowId}:${columnKey}` 表示用户手填锁定、不重算。
 */
export function recalcDerivedColumns(
  sheetCode: string,
  rows: ChecklistRow[],
  manualLocks: Set<string> = new Set(),
): ChecklistRow[] {
  const intraPresets = IPO_FORMULA_PRESETS.filter(
    (p) => p.sheetCode === sheetCode && p.category === 'intra_sheet',
  )
  if (intraPresets.length === 0) return rows
  for (const row of rows) {
    for (const preset of intraPresets) {
      const lockKey = `${row.rowId}:${preset.columnKey}`
      if (manualLocks.has(lockKey)) continue // 手填锁定，不重算
      const val = evaluateExpression(preset.expression as string, row, rows as Array<Record<string, unknown>>)
      row[preset.columnKey] = val == null ? null : Number(val.toFixed(preset.precision))
    }
  }
  return rows
}
