/**
 * 公式语法解析器（纯函数）。
 *
 * spec: formula-management-ux-improvements · A 批 · Task A1
 *
 * 支持 6 种平台公式函数：TB / WP / NOTE / ROW / REPORT / SUM_ROW
 * + 数学运算符（+ - * / %）+ 数字常量 + 括号。
 *
 * 两个入口：
 * - `tokenize(expr)` → 着色用 token 数组
 * - `validate(expr)` → 语法校验结果（errors + 提取到的函数调用列表）
 */

// ── 类型 ────────────────────────────────────────────────────────────────────

/** 单个 token */
export interface ParseToken {
  type: 'function' | 'string' | 'operator' | 'number' | 'paren' | 'comma' | 'whitespace' | 'unknown'
  value: string
  start: number
  end: number
  error?: string
}

export interface FunctionCall {
  name: string
  args: string[]
  start: number
  end: number
}

export interface ValidationError {
  start: number
  end: number
  message: string
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationError[]
  functions: FunctionCall[]
}

// ── 常量 ────────────────────────────────────────────────────────────────────

/** 平台已知公式函数 */
const KNOWN_FUNCTIONS = new Set(['TB', 'WP', 'NOTE', 'ROW', 'REPORT', 'SUM_ROW', 'ADJ', 'AUX', 'PRIOR'])

/** 各函数的参数数量范围 [min, max] */
const FUNCTION_ARITY: Record<string, [number, number]> = {
  TB: [2, 2],
  WP: [2, 3],
  NOTE: [2, 3],
  ROW: [1, 1],
  REPORT: [2, 2],
  SUM_ROW: [2, 2],
  ADJ: [1, 2],
  AUX: [1, 3],
  PRIOR: [1, 2],
}

const OPERATORS = new Set(['+', '-', '*', '/', '%', '=', '<', '>', '!'])

// ── tokenize ────────────────────────────────────────────────────────────────

export function tokenize(expr: string): ParseToken[] {
  const tokens: ParseToken[] = []
  let i = 0
  const len = expr.length

  while (i < len) {
    const ch = expr[i]

    // 空白
    if (/\s/.test(ch)) {
      const start = i
      while (i < len && /\s/.test(expr[i])) i++
      tokens.push({ type: 'whitespace', value: expr.slice(start, i), start, end: i })
      continue
    }

    // 字符串字面量（单引号或双引号）
    if (ch === "'" || ch === '"') {
      const start = i
      const quote = ch
      i++ // 跳过开头引号
      while (i < len && expr[i] !== quote) {
        if (expr[i] === '\\') i++ // 转义
        i++
      }
      if (i < len) {
        i++ // 跳过结尾引号
        tokens.push({ type: 'string', value: expr.slice(start, i), start, end: i })
      } else {
        // 未闭合引号
        tokens.push({ type: 'string', value: expr.slice(start, i), start, end: i, error: '未闭合的引号' })
      }
      continue
    }

    // 数字
    if (/\d/.test(ch) || (ch === '.' && i + 1 < len && /\d/.test(expr[i + 1]))) {
      const start = i
      while (i < len && /[\d.]/.test(expr[i])) i++
      tokens.push({ type: 'number', value: expr.slice(start, i), start, end: i })
      continue
    }

    // 函数名或标识符（大写字母开头）
    if (/[A-Z_]/.test(ch)) {
      const start = i
      while (i < len && /[A-Z_0-9]/.test(expr[i])) i++
      const name = expr.slice(start, i)
      if (KNOWN_FUNCTIONS.has(name)) {
        tokens.push({ type: 'function', value: name, start, end: i })
      } else {
        tokens.push({ type: 'unknown', value: name, start, end: i, error: `未知函数 "${name}"` })
      }
      continue
    }

    // 括号
    if (ch === '(' || ch === ')') {
      tokens.push({ type: 'paren', value: ch, start: i, end: i + 1 })
      i++
      continue
    }

    // 逗号
    if (ch === ',') {
      tokens.push({ type: 'comma', value: ch, start: i, end: i + 1 })
      i++
      continue
    }

    // 运算符
    if (OPERATORS.has(ch)) {
      const start = i
      // 处理 >=, <=, != 双字符运算符
      if (i + 1 < len && expr[i + 1] === '=' && (ch === '<' || ch === '>' || ch === '!')) {
        i += 2
      } else {
        i++
      }
      tokens.push({ type: 'operator', value: expr.slice(start, i), start, end: i })
      continue
    }

    // 等号（= 开头的 Excel 惯例公式前缀，跳过）
    if (ch === '=') {
      tokens.push({ type: 'operator', value: ch, start: i, end: i + 1 })
      i++
      continue
    }

    // 未识别字符
    tokens.push({ type: 'unknown', value: ch, start: i, end: i + 1, error: `无法识别的字符 "${ch}"` })
    i++
  }

  return tokens
}

// ── validate ────────────────────────────────────────────────────────────────

export function validate(expr: string): ValidationResult {
  const errors: ValidationError[] = []
  const functions: FunctionCall[] = []

  if (!expr || !expr.trim()) {
    return { valid: true, errors: [], functions: [] }
  }

  const tokens = tokenize(expr)

  // 1. 收集 token 级错误
  for (const t of tokens) {
    if (t.error) {
      errors.push({ start: t.start, end: t.end, message: t.error })
    }
  }

  // 2. 括号配对检查
  let parenDepth = 0
  for (const t of tokens) {
    if (t.type === 'paren' && t.value === '(') parenDepth++
    if (t.type === 'paren' && t.value === ')') parenDepth--
    if (parenDepth < 0) {
      errors.push({ start: t.start, end: t.end, message: '多余的右括号' })
      parenDepth = 0
    }
  }
  if (parenDepth > 0) {
    const lastOpen = tokens.filter(t => t.type === 'paren' && t.value === '(').pop()
    if (lastOpen) {
      errors.push({ start: lastOpen.start, end: lastOpen.end, message: '未闭合的左括号' })
    }
  }

  // 3. 提取函数调用并检查参数数量
  const nonWs = tokens.filter(t => t.type !== 'whitespace')
  for (let idx = 0; idx < nonWs.length; idx++) {
    const t = nonWs[idx]
    if (t.type === 'function') {
      const next = nonWs[idx + 1]
      if (!next || next.type !== 'paren' || next.value !== '(') {
        errors.push({ start: t.start, end: t.end, message: `函数 ${t.value} 后缺少 "("` })
        continue
      }
      // 收集括号内的参数
      const args: string[] = []
      let currentArg = ''
      let depth = 0
      let argStart = next.end
      let closeParen = -1
      for (let j = idx + 2; j < nonWs.length; j++) {
        const a = nonWs[j]
        if (a.type === 'paren' && a.value === '(') {
          depth++
          currentArg += a.value
        } else if (a.type === 'paren' && a.value === ')') {
          if (depth === 0) {
            if (currentArg.trim()) args.push(currentArg.trim())
            closeParen = a.end
            break
          }
          depth--
          currentArg += a.value
        } else if (a.type === 'comma' && depth === 0) {
          args.push(currentArg.trim())
          currentArg = ''
        } else {
          currentArg += a.value
        }
      }

      const fc: FunctionCall = { name: t.value, args, start: t.start, end: closeParen > 0 ? closeParen : t.end }
      functions.push(fc)

      // 参数数量校验
      const arity = FUNCTION_ARITY[t.value]
      if (arity) {
        const [min, max] = arity
        if (args.length < min || args.length > max) {
          const expected = min === max ? `${min}` : `${min}~${max}`
          errors.push({
            start: t.start,
            end: closeParen > 0 ? closeParen : t.end,
            message: `${t.value} 需要 ${expected} 个参数，实际 ${args.length} 个`,
          })
        }
      }
    }
  }

  return { valid: errors.length === 0, errors, functions }
}

// ── 辅助：提取函数参数候选（用于自动补全） ────────────────────────────────

/**
 * 判断光标在哪个函数的哪个参数位置。
 * 返回 null 表示不在任何函数参数中。
 */
export function cursorContext(expr: string, cursor: number): { funcName: string; argIndex: number } | null {
  // 从光标位置往前找最近的未闭合的 FUNC(
  let depth = 0
  let argIndex = 0
  for (let i = cursor - 1; i >= 0; i--) {
    const ch = expr[i]
    if (ch === ')') depth++
    else if (ch === '(') {
      if (depth === 0) {
        // 找到未闭合的左括号，往前取函数名
        let nameEnd = i
        let nameStart = i - 1
        while (nameStart >= 0 && /[A-Z_0-9]/.test(expr[nameStart])) nameStart--
        nameStart++
        const name = expr.slice(nameStart, nameEnd)
        if (KNOWN_FUNCTIONS.has(name)) {
          return { funcName: name, argIndex }
        }
        return null
      }
      depth--
    } else if (ch === ',' && depth === 0) {
      argIndex++
    }
  }
  return null
}

/** 获取已知函数列表（供补全用） */
export function knownFunctions(): Array<{ name: string; minArgs: number; maxArgs: number; description: string }> {
  return [
    { name: 'TB', minArgs: 2, maxArgs: 2, description: "试算表取数 TB('科目代码','字段')" },
    { name: 'WP', minArgs: 2, maxArgs: 3, description: "底稿取数 WP('底稿','字段') 或 WP('底稿','sheet','坐标')" },
    { name: 'NOTE', minArgs: 2, maxArgs: 3, description: "附注取数 NOTE('章节','字段')" },
    { name: 'ROW', minArgs: 1, maxArgs: 1, description: "行次引用 ROW('行次')" },
    { name: 'REPORT', minArgs: 2, maxArgs: 2, description: "报表取数 REPORT('行次','字段')" },
    { name: 'SUM_ROW', minArgs: 2, maxArgs: 2, description: "区间求和 SUM_ROW('起始行','结束行')" },
    { name: 'ADJ', minArgs: 1, maxArgs: 2, description: "调整分录取数 ADJ('科目')" },
    { name: 'AUX', minArgs: 1, maxArgs: 3, description: "辅助余额取数 AUX('科目')" },
    { name: 'PRIOR', minArgs: 1, maxArgs: 2, description: "上期数取数 PRIOR('行次')" },
  ]
}
