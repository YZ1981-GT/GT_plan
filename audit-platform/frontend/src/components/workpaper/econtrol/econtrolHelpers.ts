// ─── econtrolHelpers.ts ──────────────────────────────────────────────────────
// Pure functions shared by GtEControlTest shell + future sub-mode SFCs

import type { StepDef, HintBlock } from '../GtEControlTest.types'

/**
 * 安全 evaluate：仅支持 schema 中 `field == 'value'` / `field in [...]` / `field > N` /
 * `field == 0` 等简单条件。无法解析时返回 true（不隐藏字段，宁可多显示）。
 */
export function safeEvaluate(expression: string, ctx: Record<string, any>): boolean {
  if (!expression || typeof expression !== 'string') return true
  const expr = expression.trim()
  if (expr === 'true') return true
  if (expr === 'false') return false

  // field == 'value' / field === "value"
  let m = expr.match(/^(\w+)\s*===?\s*['"](.+?)['"]$/)
  if (m) return ctx[m[1]] === m[2]

  // field != 'value'
  m = expr.match(/^(\w+)\s*!==?\s*['"](.+?)['"]$/)
  if (m) return ctx[m[1]] !== m[2]

  // field == number
  m = expr.match(/^(\w+)\s*===?\s*(\d+(?:\.\d+)?)$/)
  if (m) return Number(ctx[m[1]]) === Number(m[2])

  // field > N / field >= N / field < N / field <= N
  m = expr.match(/^(\w+)\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)$/)
  if (m) {
    const v = Number(ctx[m[1]])
    const target = Number(m[3])
    if (Number.isNaN(v)) return false
    switch (m[2]) {
      case '>': return v > target
      case '>=': return v >= target
      case '<': return v < target
      case '<=': return v <= target
    }
  }

  // field in ['a', 'b']
  m = expr.match(/^(\w+)\s+in\s+\[(.+)\]$/)
  if (m) {
    const list = m[2].split(',').map(s => s.trim().replace(/^['"]|['"]$/g, ''))
    return list.includes(String(ctx[m[1]] ?? ''))
  }

  // 默认：无法解析 → 不隐藏（保守）
  return true
}

const stepLabelMap: Record<number, string> = {
  1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六',
  7: '七', 8: '八', 9: '九', 10: '十',
}

export function stepLabel(no: number): string {
  return stepLabelMap[no] ?? String(no)
}

export function stepShortTitle(step: StepDef): string {
  const title = step.title || ''
  // 移除"步骤一："等前缀，保留主题
  return title.replace(/^步骤[一二三四五六七八九十\d]+[：:]\s*/, '')
}

export function hintTableRows(hint: HintBlock): Array<Record<string, string | number>> {
  if (!hint.rows) return []
  return hint.rows.map(r => {
    const obj: Record<string, string | number> = {}
    r.forEach((cell, i) => { obj[`c${i}`] = cell })
    return obj
  })
}
