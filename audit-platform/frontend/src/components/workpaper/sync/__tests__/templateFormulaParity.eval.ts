/**
 * 模板公式表达式求值 —— 前端 ↔ 模板公式对拍守卫用
 * （spec oo-writeback-template-parity-closure R2.4，design §3.3）。
 *
 * 表达式来自 `templateFormulaParity.generated.json` 的 `expr`：生成器把权威模板数据首行的公式
 * 换成同一行的 store 字段名，记号之间以空格分隔。字段名可带路径：`agingAudited/within1` 是嵌套对象，
 * `months/0` 是数组下标；除号 `/` 两侧一定有空格，不会与路径混淆。
 *
 * 取值口径对齐 Excel：
 * - 空（undefined / null / ''）在算术里是 0，比较时与 0 / '' / FALSE 相等；
 * - 数字字符串按数（模板格里存的是数）；`YYYY-MM-DD` 日期字符串按 Excel 序列日数；
 * - 其他文本进算术 ⇒ #VALUE!；除以 0 ⇒ #DIV/0!；错误值沿运算传播，`IFERROR` 吃掉；
 * - `SUM` / `MAX` / `MIN` 的引用参数原本是同行区间：文本与布尔不计；
 * - `=` / `<>` 按分比较（两侧四舍五入到分后相等），`<` `>` 等按原值；文本比较不分大小写；
 * - `ROUND` 四舍五入远离 0（Excel 口径）。
 */

export interface ExcelError {
  readonly error: '#DIV/0!' | '#VALUE!'
}

/** null = 空格 */
export type ExcelValue = number | string | boolean | null | ExcelError

type Node =
  | { kind: 'num'; value: number }
  | { kind: 'str'; value: string }
  | { kind: 'bool'; value: boolean }
  | { kind: 'ref'; path: string }
  | { kind: 'unary'; op: '-' | '+'; arg: Node }
  | { kind: 'binary'; op: string; left: Node; right: Node }
  | { kind: 'call'; name: string; args: Node[] }

const DIV0: ExcelError = { error: '#DIV/0!' }
const VALUE: ExcelError = { error: '#VALUE!' }
const COMPARISONS = new Set(['=', '<>', '<', '>', '<=', '>='])

const BINARY_PREC: Readonly<Record<string, number>> = {
  '=': 1, '<>': 1, '<': 1, '>': 1, '<=': 1, '>=': 1,
  '+': 3, '-': 3,
  '*': 4, '/': 4,
  '^': 5,
}
/** Excel 的负号比乘方先结合：`-2^2` = 4 */
const UNARY_PREC = 6
const FUNCTIONS = new Set(['SUM', 'IF', 'AND', 'OR', 'NOT', 'ROUND', 'ABS', 'MAX', 'MIN', 'IFERROR'])
const FIELD_PATH = /^[A-Za-z_]\w*(\/\w+)*$/

export function isError(v: unknown): v is ExcelError {
  return typeof v === 'object' && v !== null && 'error' in v
}

/** 记号切分：空格分隔；文本常量里的空格保留；粘在操作数上的逗号单独成记号 */
export function tokenize(expr: string): string[] {
  const out: string[] = []
  let i = 0
  while (i < expr.length) {
    const ch = expr[i]
    if (ch === ' ') {
      i++
      continue
    }
    if (ch === '"') {
      let j = i + 1
      while (j < expr.length) {
        if (expr[j] === '"') {
          if (expr[j + 1] === '"') {
            j += 2
            continue
          }
          break
        }
        j++
      }
      if (j >= expr.length) throw new Error(`文本常量没有闭合：${expr}`)
      out.push(expr.slice(i, j + 1))
      i = j + 1
      continue
    }
    let j = i
    while (j < expr.length && expr[j] !== ' ') j++
    const word = expr.slice(i, j)
    i = j
    if (word === ',') {
      out.push(word)
      continue
    }
    const parts = word.split(',')
    parts.forEach((p, idx) => {
      if (p) out.push(p)
      if (idx < parts.length - 1) out.push(',')
    })
  }
  return out
}

class Parser {
  private pos = 0
  constructor(private readonly tokens: string[], private readonly source: string) {}

  parse(): Node {
    const node = this.expr(0)
    if (this.pos !== this.tokens.length) this.fail(`多余的记号「${this.tokens[this.pos]}」`)
    return node
  }

  private peek(): string | undefined {
    return this.tokens[this.pos]
  }

  private next(): string {
    const t = this.tokens[this.pos++]
    if (t === undefined) this.fail('表达式意外结束')
    return t as string
  }

  private fail(msg: string): never {
    throw new Error(`${msg}：${this.source}`)
  }

  private expect(tok: string): void {
    const t = this.next()
    if (t !== tok) this.fail(`应为「${tok}」，实为「${t}」`)
  }

  private expr(minPrec: number): Node {
    let left = this.prefix()
    for (;;) {
      const op = this.peek()
      const prec = op === undefined ? undefined : BINARY_PREC[op]
      if (prec === undefined || prec < minPrec) return left
      this.next()
      const right = this.expr(prec + 1)
      left = { kind: 'binary', op: op as string, left, right }
    }
  }

  private prefix(): Node {
    const t = this.next()
    if (t === '-' || t === '+') return { kind: 'unary', op: t, arg: this.expr(UNARY_PREC) }
    if (t === '(') {
      const inner = this.expr(0)
      this.expect(')')
      return inner
    }
    if (t.endsWith('(')) {
      const name = t.slice(0, -1).toUpperCase()
      if (!FUNCTIONS.has(name)) this.fail(`不支持的函数 ${name}`)
      const args: Node[] = []
      if (this.peek() === ')') {
        this.next()
        return { kind: 'call', name, args }
      }
      for (;;) {
        args.push(this.expr(0))
        const sep = this.next()
        if (sep === ')') break
        if (sep !== ',') this.fail(`函数参数之间应为「,」，实为「${sep}」`)
      }
      return { kind: 'call', name, args }
    }
    if (t.startsWith('"')) return { kind: 'str', value: t.slice(1, -1).replace(/""/g, '"') }
    if (t === 'TRUE' || t === 'FALSE') return { kind: 'bool', value: t === 'TRUE' }
    if (/^[0-9.]/.test(t)) {
      const value = Number(t)
      if (!Number.isFinite(value)) this.fail(`认不出的数字 ${t}`)
      return { kind: 'num', value }
    }
    if (!FIELD_PATH.test(t)) this.fail(`认不出的记号「${t}」`)
    return { kind: 'ref', path: t }
  }
}

const compiled = new Map<string, Node>()

/** 编译（带缓存）；表达式写错直接抛 */
export function compileExpr(expr: string): Node {
  let node = compiled.get(expr)
  if (!node) {
    node = new Parser(tokenize(expr), expr).parse()
    compiled.set(expr, node)
  }
  return node
}

/** 表达式引用到的字段路径（去重，按出现顺序） */
export function referencedFields(expr: string): string[] {
  const out: string[] = []
  const walk = (n: Node): void => {
    if (n.kind === 'ref') {
      if (!out.includes(n.path)) out.push(n.path)
    } else if (n.kind === 'unary') walk(n.arg)
    else if (n.kind === 'binary') {
      walk(n.left)
      walk(n.right)
    } else if (n.kind === 'call') n.args.forEach(walk)
  }
  walk(compileExpr(expr))
  return out
}

/** 按路径取值：`a/b` 取嵌套，数组按下标 */
export function getPath(row: unknown, path: string): unknown {
  let cur: unknown = row
  for (const seg of path.split('/')) {
    if (cur === null || cur === undefined) return undefined
    cur = Array.isArray(cur) ? cur[Number(seg)] : (cur as Record<string, unknown>)[seg]
  }
  return cur
}

/** 按路径写值：下一段是数字时建数组 */
export function setPath(row: Record<string, unknown>, path: string, value: unknown): void {
  const segs = path.split('/')
  let cur: Record<string, unknown> | unknown[] = row
  segs.forEach((seg, i) => {
    const last = i === segs.length - 1
    const key: string | number = Array.isArray(cur) ? Number(seg) : seg
    if (last) {
      ;(cur as Record<string | number, unknown>)[key] = value
      return
    }
    const holder = cur as Record<string | number, unknown>
    if (holder[key] === null || typeof holder[key] !== 'object') {
      holder[key] = /^\d+$/.test(segs[i + 1]) ? [] : {}
    }
    cur = holder[key] as Record<string, unknown> | unknown[]
  })
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/

/** Excel 1900 日期系统序列日数（1970-01-01 = 25569） */
export function excelSerial(iso: string): number | null {
  const m = ISO_DATE.exec(iso.trim())
  if (!m) return null
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / 86_400_000 + 25_569
}

function fromRow(raw: unknown): ExcelValue {
  if (raw === undefined || raw === null || raw === '') return null
  if (typeof raw === 'number') return Number.isNaN(raw) ? VALUE : raw
  if (typeof raw === 'string' || typeof raw === 'boolean') return raw
  return VALUE
}

function textToNumber(s: string): number | null {
  const t = s.trim()
  if (t === '') return 0
  if (/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) return Number(t)
  return excelSerial(t)
}

function toNumber(v: ExcelValue): number | ExcelError {
  if (v === null) return 0
  if (isError(v)) return v
  if (typeof v === 'number') return v
  if (typeof v === 'boolean') return v ? 1 : 0
  const n = textToNumber(v)
  return n === null ? VALUE : n
}

function toBool(v: ExcelValue): boolean | ExcelError {
  if (v === null) return false
  if (isError(v)) return v
  if (typeof v === 'boolean') return v
  if (typeof v === 'number') return v !== 0
  const t = v.trim().toUpperCase()
  if (t === 'TRUE') return true
  if (t === 'FALSE') return false
  return VALUE
}

/** 四舍五入远离 0；先截到 15 位有效数字消掉二进制表示误差（Excel 按 15 位有效数字运算） */
export function excelRound(x: number, digits: number): number {
  const d = Math.trunc(digits)
  const f = 10 ** d
  const scaled = Number((Math.abs(x) * f).toPrecision(15))
  return (Math.sign(x) * Math.round(scaled)) / f
}

function cents(x: number): number {
  return excelRound(x, 2)
}

function compare(op: string, a: ExcelValue, b: ExcelValue): ExcelValue {
  if (isError(a)) return a
  if (isError(b)) return b
  // 前端行里的数字字符串按数（模板那一格是数）
  if (typeof a === 'string' && typeof b === 'number') a = textToNumber(a) ?? a
  if (typeof b === 'string' && typeof a === 'number') b = textToNumber(b) ?? b
  if (a === null) a = b === null ? 0 : typeof b === 'string' ? '' : typeof b === 'boolean' ? false : 0
  if (b === null) b = typeof a === 'string' ? '' : typeof a === 'boolean' ? false : 0
  const rank = (v: number | string | boolean): number =>
    typeof v === 'number' ? 0 : typeof v === 'string' ? 1 : 2
  let c: number
  if (rank(a) !== rank(b)) c = rank(a) - rank(b)
  else if (typeof a === 'number') {
    const x = a
    const y = b as number
    c = op === '=' || op === '<>' ? Math.sign(cents(x) - cents(y)) : Math.sign(x - y)
  } else if (typeof a === 'string') {
    const x = a.toUpperCase()
    const y = (b as string).toUpperCase()
    c = x === y ? 0 : x < y ? -1 : 1
  } else c = Number(a) - Number(b)
  switch (op) {
    case '=': return c === 0
    case '<>': return c !== 0
    case '<': return c < 0
    case '>': return c > 0
    case '<=': return c <= 0
    case '>=': return c >= 0
    default: throw new Error(`未知比较 ${op}`)
  }
}

function arith(op: string, a: ExcelValue, b: ExcelValue): ExcelValue {
  const x = toNumber(a)
  if (isError(x)) return x
  const y = toNumber(b)
  if (isError(y)) return y
  switch (op) {
    case '+': return x + y
    case '-': return x - y
    case '*': return x * y
    case '/': return y === 0 ? DIV0 : x / y
    case '^': return x ** y
    default: throw new Error(`未知运算 ${op}`)
  }
}

/** SUM / MAX / MIN 的参数：引用按区间口径（文本、布尔不计），其余按数 */
function numericArgs(args: Node[], row: unknown): number[] | ExcelError {
  const out: number[] = []
  for (const a of args) {
    const v = evalNode(a, row)
    if (isError(v)) return v
    if (a.kind === 'ref') {
      if (typeof v === 'number') out.push(v)
      else if (typeof v === 'string') {
        const n = textToNumber(v)
        if (n !== null && v.trim() !== '') out.push(n)
      }
      continue
    }
    const n = toNumber(v)
    if (isError(n)) return n
    out.push(n)
  }
  return out
}

function evalCall(name: string, args: Node[], row: unknown): ExcelValue {
  switch (name) {
    case 'SUM': {
      const xs = numericArgs(args, row)
      return isError(xs) ? xs : xs.reduce((s, x) => s + x, 0)
    }
    case 'MAX':
    case 'MIN': {
      const xs = numericArgs(args, row)
      if (isError(xs)) return xs
      if (!xs.length) return 0
      return name === 'MAX' ? Math.max(...xs) : Math.min(...xs)
    }
    case 'ROUND': {
      if (args.length !== 2) return VALUE
      const x = toNumber(evalNode(args[0], row))
      if (isError(x)) return x
      const d = toNumber(evalNode(args[1], row))
      if (isError(d)) return d
      return excelRound(x, d)
    }
    case 'ABS': {
      const x = toNumber(evalNode(args[0], row))
      return isError(x) ? x : Math.abs(x)
    }
    case 'IF': {
      if (args.length < 1 || args.length > 3) return VALUE
      const c = toBool(evalNode(args[0], row))
      if (isError(c)) return c
      if (c) return args.length >= 2 ? evalNode(args[1], row) ?? 0 : true
      return args.length === 3 ? evalNode(args[2], row) ?? 0 : false
    }
    case 'AND':
    case 'OR': {
      let acc = name === 'AND'
      for (const a of args) {
        const b = toBool(evalNode(a, row))
        if (isError(b)) return b
        acc = name === 'AND' ? acc && b : acc || b
      }
      return acc
    }
    case 'NOT': {
      const b = toBool(evalNode(args[0], row))
      return isError(b) ? b : !b
    }
    case 'IFERROR': {
      const v = evalNode(args[0], row)
      return isError(v) ? evalNode(args[1], row) : v
    }
    default:
      throw new Error(`不支持的函数 ${name}`)
  }
}

function evalNode(n: Node, row: unknown): ExcelValue {
  switch (n.kind) {
    case 'num': return n.value
    case 'str': return n.value
    case 'bool': return n.value
    case 'ref': return fromRow(getPath(row, n.path))
    case 'unary': {
      const x = toNumber(evalNode(n.arg, row))
      if (isError(x)) return x
      return n.op === '-' ? -x : x
    }
    case 'binary': {
      const a = evalNode(n.left, row)
      const b = evalNode(n.right, row)
      return COMPARISONS.has(n.op) ? compare(n.op, a, b) : arith(n.op, a, b)
    }
    case 'call': return evalCall(n.name, n.args, row)
  }
}

/** 在一行上求表达式；结果为空（如 `=A1` 引用空格）时按 Excel 显示 0 */
export function evaluate(expr: string, row: unknown): ExcelValue {
  const v = evalNode(compileExpr(expr), row)
  return v === null ? 0 : v
}

/** 数值容差：半分（容纳前端四舍五入到分）+ 浮点相对误差 */
export function closeEnough(expected: number, actual: number): boolean {
  return Math.abs(expected - actual) <= 0.005 + Math.abs(expected) * 1e-13
}

/** 前端值转数（空 = 0；认不出返回 null） */
export function frontendNumber(actual: unknown): number | null {
  if (actual === undefined || actual === null || actual === '') return 0
  if (typeof actual === 'number') return Number.isFinite(actual) ? actual : null
  if (typeof actual === 'string') return textToNumber(actual)
  return null
}

/**
 * 模板结果 vs 前端值：
 * - 模板出错（#DIV/0! 等）⇒ 前端显示空 / 0 / N/A / 非有限数都算一致（显示选择，不比较）；
 * - 数按半分容差；布尔比布尔（前端也可写 'TRUE' / 'FALSE'）；文本逐字相等（去首尾空白）。
 */
export function matches(expected: ExcelValue, actual: unknown): boolean {
  if (isError(expected)) {
    const n = frontendNumber(actual)
    return n === null || n === 0
  }
  if (typeof expected === 'number') {
    if (typeof actual === 'boolean') return false
    const n = frontendNumber(actual)
    return n !== null && closeEnough(expected, n)
  }
  if (typeof expected === 'boolean') {
    if (typeof actual === 'boolean') return actual === expected
    return typeof actual === 'string' && actual.trim().toUpperCase() === (expected ? 'TRUE' : 'FALSE')
  }
  if (expected === null) return frontendNumber(actual) === 0
  return typeof actual === 'string' && actual.trim() === expected.trim()
}

/** 报错用的值描述 */
export function describeValue(v: unknown): string {
  if (isError(v)) return v.error
  if (v === undefined) return 'undefined'
  return JSON.stringify(v)
}
