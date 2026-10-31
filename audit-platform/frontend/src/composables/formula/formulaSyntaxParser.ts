/**
 * 公式语法解析器（纯函数）。
 *
 * spec: formula-grammar-resolver-unification · S1 ADR-FGR-01
 *
 * 函数表、参数范围、运算符均从生成文件 ``formulaFunctionCatalog.ts`` 读取，
 * 按调用方传入的引擎（l1 / note / cell）取对应子集。
 *
 * 两个入口：
 * - `tokenize(expr, engine?)` → 着色用 token 数组
 * - `validate(expr, engine?)` → 语法校验结果（errors + 提取到的函数调用列表）
 */

import type { FormulaEngine } from '@/generated/formulaFunctionCatalog'
import {
  FUNCTION_NAMES_BY_ENGINE,
  ARITY_BY_ENGINE,
  OPERATORS_BY_ENGINE,
  FUNCTION_HINTS_BY_ENGINE,
} from '@/generated/formulaFunctionCatalog'

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

// ── 默认引擎 ────────────────────────────────────────────────────────────────

const DEFAULT_ENGINE: FormulaEngine = 'l1'

/** 所有引擎的函数名并集（tokenize 着色用，不区分引擎时使用）。 */
const ALL_FUNCTION_NAMES = new Set([
  ...FUNCTION_NAMES_BY_ENGINE.l1,
  ...FUNCTION_NAMES_BY_ENGINE.note,
  ...FUNCTION_NAMES_BY_ENGINE.cell,
])

// ── tokenize ────────────────────────────────────────────────────────────────

export function tokenize(expr: string, engine?: FormulaEngine): ParseToken[] {
  const funcNames = engine ? FUNCTION_NAMES_BY_ENGINE[engine] : ALL_FUNCTION_NAMES
  const operators = engine ? OPERATORS_BY_ENGINE[engine] : OPERATORS_BY_ENGINE.l1

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
      if (funcNames.has(name)) {
        tokens.push({ type: 'function', value: name, start, end: i })
      } else if (ALL_FUNCTION_NAMES.has(name)) {
        // 函数存在但不属于当前引擎——给出改用提示
        const hint = _crossEngineHint(name, engine)
        tokens.push({ type: 'unknown', value: name, start, end: i, error: hint })
      } else {
        tokens.push({ type: 'unknown', value: name, start, end: i, error: `未知函数 "${name}"` })
      }
      continue
    }

    // 小写字母开头的标识符（附注域的 cell 函数）
    if (/[a-z]/.test(ch) && funcNames.has('cell')) {
      const start = i
      while (i < len && /[a-z_0-9]/i.test(expr[i])) i++
      const name = expr.slice(start, i)
      if (funcNames.has(name)) {
        tokens.push({ type: 'function', value: name, start, end: i })
      } else {
        tokens.push({ type: 'unknown', value: name, start, end: i, error: `未知标识符 "${name}"` })
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

    // 冒号（附注域 SUM 函数用 start:end 语法）
    if (ch === ':') {
      tokens.push({ type: 'operator', value: ch, start: i, end: i + 1 })
      i++
      continue
    }

    // 运算符
    if (operators.has(ch)) {
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

export function validate(expr: string, engine: FormulaEngine = DEFAULT_ENGINE): ValidationResult {
  const errors: ValidationError[] = []
  const functions: FunctionCall[] = []

  if (!expr || !expr.trim()) {
    return { valid: true, errors: [], functions: [] }
  }

  const tokens = tokenize(expr, engine)
  const arity = ARITY_BY_ENGINE[engine]
  const funcNames = FUNCTION_NAMES_BY_ENGINE[engine]

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

      // 参数数量校验（从目录读取）
      const bounds = arity[t.value]
      if (bounds) {
        const [min, max] = bounds
        if (args.length < min || (max !== null && args.length > max)) {
          const expected = max === null
            ? `至少 ${min}`
            : min === max ? `${min}` : `${min}~${max}`
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
export function cursorContext(expr: string, cursor: number, engine?: FormulaEngine): { funcName: string; argIndex: number } | null {
  const funcNames = engine ? FUNCTION_NAMES_BY_ENGINE[engine] : ALL_FUNCTION_NAMES

  let depth = 0
  let argIndex = 0
  for (let i = cursor - 1; i >= 0; i--) {
    const ch = expr[i]
    if (ch === ')') depth++
    else if (ch === '(') {
      if (depth === 0) {
        let nameEnd = i
        let nameStart = i - 1
        while (nameStart >= 0 && /[A-Z_0-9]/.test(expr[nameStart])) nameStart--
        nameStart++
        const name = expr.slice(nameStart, nameEnd)
        if (funcNames.has(name)) {
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

/** 获取当前引擎的函数提示列表（供补全用，从目录生成文件读取）。 */
export function knownFunctions(engine: FormulaEngine = DEFAULT_ENGINE): Array<{ name: string; minArgs: number; maxArgs: number | null; description: string }> {
  return [...FUNCTION_HINTS_BY_ENGINE[engine]]
}

// ── 跨引擎提示 ─────────────────────────────────────────────────────────────

function _crossEngineHint(name: string, engine?: FormulaEngine): string {
  if (!engine) return `未知函数 "${name}"`

  // PRIOR 在 L1 下给出改用 PREV 的提示
  if (name === 'PRIOR' && engine === 'l1') {
    return 'PRIOR 是附注公式函数，报表/底稿公式请用 PREV'
  }
  // PREV 在附注域给出改用 PRIOR 的提示
  if (name === 'PREV' && engine === 'note') {
    return 'PREV 是报表公式函数，附注公式请用 PRIOR'
  }

  // 通用提示
  const engines: string[] = []
  for (const [eng, names] of Object.entries(FUNCTION_NAMES_BY_ENGINE)) {
    if ((names as ReadonlySet<string>).has(name)) engines.push(eng)
  }
  if (engines.length > 0) {
    return `${name} 不支持当前引擎（${engine}），仅在 ${engines.join('/')} 下可用`
  }
  return `未知函数 "${name}"`
}
