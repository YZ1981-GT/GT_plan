/**
 * 前端 ↔ 模板公式对拍守卫（spec oo-writeback-template-parity-closure R2.4，design §3.3）。
 *
 * 清单 `templateFormulaParity.generated.json` 由 `backend/scripts/gen/gen_template_formula_parity.py`
 * 从生产契约 + 权威模板生成（后端测试校验 `--check` 无漂移）：每个行表的公式字段 → 换成同一行 store
 * 字段名的表达式。本守卫对每个有适配器的 store item 用固定种子造一批录入行，经前端真实的行计算后逐行核对：
 *   ① 公式：前端算出的每个公式字段 == 模板表达式在前端这一行上的求值（按分比较，半分容差）；
 *   ② 录入：前端不改写数值录入列（模板直接用录入值算）。
 * 一半样本给公式列塞旧值：前端必须重算，不能沿用存库值。
 * 暂不能对齐的逐条登记在 `templateFormulaParity.exceptions.ts`（只许减少，失效即报红）。
 */
import { describe, expect, it } from 'vitest'
import generated from './templateFormulaParity.generated.json'
import {
  closeEnough,
  compileExpr,
  describeValue,
  evaluate,
  excelRound,
  frontendNumber,
  getPath,
  matches,
  referencedFields,
  setPath,
  tokenize,
} from './templateFormulaParity.eval'
import { PARITY_ADAPTERS, type ParityRow } from './templateFormulaParity.adapters'
import {
  PARITY_EXCEPTION_BASELINE,
  PARITY_EXCEPTIONS,
  UNCOVERED_BASELINE,
  UNCOVERED_ITEMS,
  type ParityException,
} from './templateFormulaParity.exceptions'

interface ParityEntry {
  store_item: string
  contract: string
  sheet: string
  cell: string
  field: string
  header: string
  formula: string | null
  expr: string | null
  skip: string | null
}

interface ParityItem {
  contract: string
  tables: string[]
  inputs: string[]
  input_types: Record<string, string>
  date_inputs: string[]
  text_inputs: string[]
  /** auto_source / cross_sheet：系统带出、受保护，不随机录入也不按录入核对 */
  auto_fields: string[]
  literals: string[]
}

interface ParityManifest {
  summary: { formula_fields: number; ok: number; skip: number }
  items: Record<string, ParityItem>
  entries: ParityEntry[]
}

const manifest = generated as unknown as ParityManifest
const SAMPLES_PER_ITEM = 24

// ─── 样本 ────────────────────────────────────────────────────────────────────

/** mulberry32；每个 store item 用自己名字的哈希做种子 ⇒ 增删别的 item 不改本 item 的样本 */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function hashSeed(text: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

const RATIO_NAME = /(rate|ratio|probability)$/i
/** 契约把日期列标成文本的（D1-9 等）按字段名认：…Date / …date */
const DATE_NAME = /date$/i

/**
 * 金额 ±100 万两位小数（15% 为 0）；整数 0~399；
 * 比例 0~1 四位小数，第 3 / 11 / 19 个样本固定取负数、第 5 / 13 / 21 个固定取大于 1
 * （每个比例字段都确定地碰到区间外，前端截断这类改写不靠种子运气才暴露）。
 */
function randomNumber(field: string, type: string | undefined, sample: number, rand: () => number): number {
  const r = rand()
  if (type === 'integer') return r < 0.15 ? 0 : Math.floor(rand() * 400)
  const leaf = field.split('/').pop() ?? field
  if (type === 'ratio' || type === 'percent' || type === 'rate' || RATIO_NAME.test(leaf)) {
    if (sample % 8 === 3) return -Math.round((r * 0.9 + 0.05) * 10_000) / 10_000
    if (sample % 8 === 5) return Math.round((1.05 + r) * 10_000) / 10_000
    if (r < 0.12) return 0
    return Math.round(rand() * 10_000) / 10_000
  }
  if (r < 0.15) return 0
  return Math.round((rand() * 2 - 1) * 1e8) / 100
}

/** 2023-01-01 ~ 2026-12-31 */
function randomDate(rand: () => number): string {
  const day = Math.floor(rand() * 1461)
  return new Date(Date.UTC(2023, 0, 1) + day * 86_400_000).toISOString().slice(0, 10)
}

function randomText(literals: string[], rand: () => number): string {
  if (literals.length && rand() < 0.6) return literals[Math.floor(rand() * literals.length)]
  return '文本'
}

// ─── 对拍 ────────────────────────────────────────────────────────────────────

interface Check {
  field: string
  expr: string
  where: string
}

interface Mismatch {
  storeItem: string
  kind: 'formula' | 'input'
  field: string
  detail: string
  raw: ParityRow
  row: ParityRow
}

interface ItemResult {
  samples: number
  mismatches: Mismatch[]
}

function entriesOf(storeItem: string): ParityEntry[] {
  return manifest.entries.filter((e) => e.store_item === storeItem)
}

/** 同一 store item 的 (字段, 表达式) 去重（多区共用一个 store item 时公式逐区相同） */
function checksOf(storeItem: string): Check[] {
  const out = new Map<string, Check>()
  for (const e of entriesOf(storeItem)) {
    if (e.expr === null) continue
    const key = `${e.field}\u0000${e.expr}`
    const prev = out.get(key)
    if (prev) prev.where += ` / ${e.cell}`
    else out.set(key, { field: e.field, expr: e.expr, where: `${e.sheet}!${e.cell} ${e.formula}` })
  }
  return [...out.values()]
}

function makeRaw(item: ParityItem, formulaFields: string[], sample: number, rand: () => number): ParityRow {
  const raw: ParityRow = {}
  for (const f of item.inputs) setPath(raw, f, randomNumber(f, item.input_types[f], sample, rand))
  for (const f of item.date_inputs) setPath(raw, f, randomDate(rand))
  for (const f of item.text_inputs) {
    setPath(raw, f, DATE_NAME.test(f) ? randomDate(rand) : randomText(item.literals, rand))
  }
  // 一半样本给公式列塞旧值：前端必须重算，不能沿用存库值
  if (sample % 2 === 1) for (const f of formulaFields) setPath(raw, f, randomNumber(f, 'amount', sample, rand))
  return raw
}

const usedExceptions = new Set<ParityException>()

function excused(m: Omit<Mismatch, 'detail'>): boolean {
  const hit = PARITY_EXCEPTIONS.find((e) =>
    e.storeItem === m.storeItem && e.field === m.field && e.kind === m.kind && (!e.when || e.when(m.raw, m.row)))
  if (hit) usedExceptions.add(hit)
  return hit !== undefined
}

function runItem(storeItem: string): ItemResult {
  const item = manifest.items[storeItem]
  const adapter = PARITY_ADAPTERS[storeItem]
  const checks = checksOf(storeItem)
  const formulaFields = [...new Set(entriesOf(storeItem).map((e) => e.field))]
  const rand = mulberry32(hashSeed(storeItem))
  const mismatches: Mismatch[] = []
  for (let sample = 0; sample < SAMPLES_PER_ITEM; sample++) {
    const raw = makeRaw(item, formulaFields, sample, rand)
    const ctx = { sample, rand }
    adapter.prepare?.(raw, ctx)
    const given = JSON.parse(JSON.stringify(raw)) as ParityRow
    const row = adapter.compute(raw, ctx)
    for (const c of checks) {
      const expected = evaluate(c.expr, row)
      const actual = getPath(row, c.field)
      const base = { storeItem, kind: 'formula' as const, field: c.field, raw: given, row }
      if (matches(expected, actual) || excused(base)) continue
      const refs = referencedFields(c.expr).map((f) => `${f}=${describeValue(getPath(row, f))}`).join(' ')
      mismatches.push({
        ...base,
        detail: `${c.where}｜模板 ${describeValue(expected)}，前端 ${describeValue(actual)}｜${refs}`,
      })
    }
    for (const f of item.inputs) {
      const want = getPath(given, f) as number
      const kept = frontendNumber(getPath(row, f))
      const base = { storeItem, kind: 'input' as const, field: f, raw: given, row }
      if ((kept !== null && closeEnough(want, kept)) || excused(base)) continue
      mismatches.push({ ...base, detail: `录入 ${want}，前端改成 ${describeValue(getPath(row, f))}` })
    }
  }
  return { samples: SAMPLES_PER_ITEM, mismatches }
}

const adapterItems = Object.keys(PARITY_ADAPTERS).sort()
let allResults: Map<string, ItemResult> | null = null

function results(): Map<string, ItemResult> {
  if (!allResults) {
    allResults = new Map(adapterItems.filter((k) => manifest.items[k]).map((k) => [k, runItem(k)]))
  }
  return allResults
}

/** 每个 (类型, 字段) 只报第一例 + 次数 */
function summarize(ms: Mismatch[]): string[] {
  const groups = new Map<string, { first: Mismatch; n: number }>()
  for (const m of ms) {
    const key = `${m.kind}:${m.field}`
    const g = groups.get(key)
    if (g) g.n += 1
    else groups.set(key, { first: m, n: 1 })
  }
  return [...groups.values()].map(({ first, n }) =>
    `${first.storeItem}.${first.field}［${first.kind === 'formula' ? '公式' : '录入'}，${n}/${SAMPLES_PER_ITEM}］${first.detail}`)
}

const itemsWithExpr = Object.keys(manifest.items)
  .filter((k) => entriesOf(k).some((e) => e.expr !== null))
  .sort()

// ─── 求值器 ──────────────────────────────────────────────────────────────────

describe('模板公式求值器', () => {
  it('记号：粘在操作数上的逗号单独成记号，文本常量里的空格保留', () => {
    expect(tokenize('SUM( a, b ) - c')).toEqual(['SUM(', 'a', ',', 'b', ')', '-', 'c'])
    expect(tokenize('IF( s = "a b" , 1 , 0 )')).toEqual(['IF(', 's', '=', '"a b"', ',', '1', ',', '0', ')'])
  })

  it('运算优先级与 Excel 一致（负号先于乘方）', () => {
    expect(evaluate('a + b * c', { a: 1, b: 2, c: 3 })).toBe(7)
    expect(evaluate('( a + b ) * c', { a: 1, b: 2, c: 3 })).toBe(9)
    expect(evaluate('- a ^ 2', { a: 2 })).toBe(4)
    expect(evaluate('a - b - c', { a: 10, b: 3, c: 2 })).toBe(5)
  })

  it('空值在算术里是 0；文本进算术报 #VALUE!，SUM 的引用参数不计文本', () => {
    expect(evaluate('a + 1', {})).toBe(1)
    expect(evaluate('a + b', { a: 'x', b: 2 })).toEqual({ error: '#VALUE!' })
    expect(evaluate('SUM( a, b )', { a: 'x', b: 2 })).toBe(2)
    expect(evaluate('a + b', { a: '1.5', b: 2 })).toBe(3.5)
  })

  it('除以 0 报 #DIV/0! 并传播，IFERROR 吃掉，IF 只求选中的分支', () => {
    expect(evaluate('a / b', { a: 1, b: 0 })).toEqual({ error: '#DIV/0!' })
    expect(evaluate('a / b + 1', { a: 1, b: 0 })).toEqual({ error: '#DIV/0!' })
    expect(evaluate('IFERROR( a / b , 7 )', { a: 1, b: 0 })).toBe(7)
    expect(evaluate('IF( b = 0 , 0 , a / b )', { a: 1, b: 0 })).toBe(0)
  })

  it('ROUND 四舍五入远离 0', () => {
    expect(excelRound(2.5, 0)).toBe(3)
    expect(excelRound(-2.5, 0)).toBe(-3)
    expect(excelRound(1.005, 2)).toBe(1.01)
    expect(evaluate('ROUND( a * b , 2 )', { a: 0.125, b: 1 })).toBe(0.13)
  })

  it('比较：= 按分，< > 按原值，文本不分大小写，空与 0 / 空串相等', () => {
    expect(evaluate('a = b', { a: 0.1 + 0.2, b: 0.3 })).toBe(true)
    expect(evaluate('a = b', { a: 1, b: 1.01 })).toBe(false)
    expect(evaluate('a < b', { a: 1, b: 1.001 })).toBe(true)
    expect(evaluate('a = "abc"', { a: 'ABC' })).toBe(true)
    expect(evaluate('a = 0', {})).toBe(true)
    expect(evaluate('IF( a = "背书" , b , 0 )', { a: '背书', b: 5 })).toBe(5)
  })

  it('日期按 Excel 序列日数相减；路径字段取嵌套对象与数组', () => {
    expect(evaluate('a - b', { a: '2025-03-01', b: '2025-02-01' })).toBe(28)
    expect(evaluate('x/y + months/1', { x: { y: 1 }, months: [0, 2] })).toBe(3)
  })

  it('结果比对：模板出错时前端空 / 0 / 非有限数都算一致；数按半分容差；布尔比布尔', () => {
    expect(matches({ error: '#DIV/0!' }, null)).toBe(true)
    expect(matches({ error: '#DIV/0!' }, '')).toBe(true)
    expect(matches({ error: '#DIV/0!' }, 0)).toBe(true)
    expect(matches({ error: '#DIV/0!' }, Number.NaN)).toBe(true)
    expect(matches({ error: '#DIV/0!' }, 5)).toBe(false)
    expect(matches(1.234, 1.23)).toBe(true)
    expect(matches(1.24, 1.23)).toBe(false)
    expect(matches(0, undefined)).toBe(true)
    expect(matches(true, true)).toBe(true)
    expect(matches(true, false)).toBe(false)
    expect(matches(true, 1)).toBe(false)
    expect(matches('是', '是')).toBe(true)
  })
})

// ─── 清单与登记表 ────────────────────────────────────────────────────────────

describe('前端 ↔ 模板公式对拍', () => {
  it('清单自洽：表达式都能编译，引用的字段都是同一 store item 的列', () => {
    const problems: string[] = []
    for (const e of manifest.entries) {
      if (e.expr === null) {
        if (!e.skip) problems.push(`${e.store_item}.${e.field} 既无表达式也无跳过原因`)
        continue
      }
      try {
        compileExpr(e.expr)
      } catch (err) {
        problems.push(`${e.store_item}.${e.field}：${(err as Error).message}`)
        continue
      }
      const item = manifest.items[e.store_item]
      const known = new Set([
        ...item.inputs, ...item.date_inputs, ...item.text_inputs, ...item.auto_fields,
        ...entriesOf(e.store_item).map((x) => x.field),
      ])
      for (const ref of referencedFields(e.expr)) {
        if (!known.has(ref)) problems.push(`${e.store_item}.${e.field} 引用了不在本表的字段 ${ref}`)
      }
    }
    expect(problems).toEqual([])
    expect(manifest.summary.ok).toBe(manifest.entries.filter((e) => e.expr !== null).length)
  })

  it('每个有可对拍公式的 store item 都有适配器，或登记在未覆盖清单（写明理由）', () => {
    const missing = itemsWithExpr.filter((k) => !PARITY_ADAPTERS[k] && !UNCOVERED_ITEMS[k])
    expect(missing).toEqual([])
    const both = Object.keys(UNCOVERED_ITEMS).filter((k) => PARITY_ADAPTERS[k])
    expect(both).toEqual([])
  })

  it('适配器与未覆盖清单都没有失效条目（store item 仍在清单里且仍有可对拍公式）', () => {
    const stale = [...Object.keys(PARITY_ADAPTERS), ...Object.keys(UNCOVERED_ITEMS)]
      .filter((k) => !itemsWithExpr.includes(k))
    expect(stale).toEqual([])
    const noReason = Object.entries(UNCOVERED_ITEMS).filter(([, why]) => why.trim().length < 8).map(([k]) => k)
    expect(noReason).toEqual([])
  })

  it('未覆盖清单只许减少', () => {
    expect(
      Object.keys(UNCOVERED_ITEMS).length,
      '未覆盖清单条数与基线不等：接上适配器后请删掉对应条目并同步改小 UNCOVERED_BASELINE；不许新增',
    ).toBe(UNCOVERED_BASELINE)
  })

  it.each(adapterItems)('%s：前端行计算与模板公式一致、不改写录入值', (storeItem) => {
    const r = results().get(storeItem)
    expect(r, `${storeItem} 不在生成清单里`).toBeDefined()
    expect(summarize(r!.mismatches)).toEqual([])
  })

  it('例外表只许减少，且每一条都还在挡住至少一处不一致', () => {
    results()
    const stale = PARITY_EXCEPTIONS.filter((e) => !usedExceptions.has(e))
      .map((e) => `${e.storeItem}.${e.field}［${e.kind}］${e.reason}`)
    expect(stale, '这些例外已不再生效（前端已对齐），请删掉并同步改小 PARITY_EXCEPTION_BASELINE').toEqual([])
    const unknown = PARITY_EXCEPTIONS.filter((e) => !PARITY_ADAPTERS[e.storeItem])
      .map((e) => `${e.storeItem}.${e.field}`)
    expect(unknown).toEqual([])
    expect(
      PARITY_EXCEPTIONS.length,
      '例外表条数与基线不等：删了条目请同步改小 PARITY_EXCEPTION_BASELINE；不许新增',
    ).toBe(PARITY_EXCEPTION_BASELINE)
  })
})
