/**
 * E1 宿主种子化接线守卫（Task 8）
 *
 * spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/
 * Requirements 1.6, 2.4, 11.3 / Property 8
 *
 * 判据是**三段链**（缺任何一段都是 dead output，而四层验证全查不出）：
 *
 *   后端 render 键 `account_prefill`
 *     → 宿主 `GtE1MonetaryFund.vue` 消费（`normalizeAccountPrefill(props.htmlData?.account_prefill)`）
 *       → 写入 `allResponses` 的键（`E1-bank-detail-rows` / `E1-account-list-rows` / `E1-digital-rows`）
 *         → 子 Tab / composable 真的读该键
 *
 * 🔴 三条判据形态上的硬约束（每条对应一次平台踩坑）：
 * 1. **判据落在「函数体内」而非「文件内出现」** —— 用圆括号配对跳过参数列表、
 *    再取第一个含语句特征的花括号块（`function f(): Promise<{a:1}> {` 的第一个
 *    `{` 是返回类型注解，直接找 `{` 会截出类型）。
 * 2. **断言函数名存在性本身** —— `reExtractFromFourTable` 命中 1 次且
 *    `refetchFromFourTable` 命中 0 次。spec 曾写错后者，按错名写守卫会静默空转。
 * 3. **替身反向自检** —— 复现「删掉账户级优先链」的源码形态时，同一判据必须打红。
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    try {
      readFileSync(resolve(dir, 'backend/app/routers/wp_render_strategies/_e1_monetary_fund.py'))
      readFileSync(resolve(dir, 'audit-platform/frontend/package.json'))
      return dir
    } catch {
      dir = resolve(dir, '..')
    }
  }
  throw new Error('定位不到仓库根（双哨兵均未命中）')
}

const ROOT = repoRoot()
const read = (rel: string) => readFileSync(resolve(ROOT, rel), 'utf-8').replace(/\r\n/g, '\n')

const HOST_REL = 'audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue'
const HOST = read(HOST_REL)

// ─────────────────────────── 源码截取 helper ─────────────────────────────────

/** 剥 `//` 行注释与 `/* *\/` 块注释（说明文字里会写被禁形态）。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .map(l => l.replace(/(^|[^:])\/\/.*$/, '$1'))
    .join('\n')
}

/** 从 `from` 起做括号配对，返回闭合位置（含）。 */
function matchPair(src: string, from: number, open: string, close: string): number {
  let depth = 0
  for (let i = from; i < src.length; i += 1) {
    const c = src[i]
    if (c === open) depth += 1
    else if (c === close) {
      depth -= 1
      if (depth === 0) return i
    }
  }
  return -1
}

const STATEMENT_HINTS = ['return', 'const ', 'let ', 'if ', 'for ', 'await ', 'throw ']

/**
 * 截一个具名函数的**函数体**。
 *
 * 先用圆括号配对跳过参数列表，再逐个候选 `{` 做配对，取第一个含语句特征的块 ——
 * 直接找第一个 `{` 会命中返回类型注解（`): Promise<{ a: 1 }> {`）。
 */
function fnBody(src: string, name: string): string {
  const m = new RegExp(`function\\s+${name}\\s*\\(`).exec(src)
  if (!m) throw new Error(`找不到 function ${name}`)
  const parenOpen = src.indexOf('(', m.index)
  let cursor = matchPair(src, parenOpen, '(', ')')
  if (cursor < 0) throw new Error(`${name} 参数列表不闭合`)
  for (let guard = 0; guard < 8; guard += 1) {
    const brace = src.indexOf('{', cursor)
    if (brace < 0) break
    const end = matchPair(src, brace, '{', '}')
    if (end < 0) break
    const body = src.slice(brace + 1, end)
    if (STATEMENT_HINTS.some(h => body.includes(h))) return body
    cursor = end + 1
  }
  throw new Error(`截不到 ${name} 的函数体（候选块均无语句特征）`)
}

/** 截 `const NAME = computed(...)` 的实参区（表达式体也能取到）。 */
function computedArg(src: string, name: string): string {
  const m = new RegExp(`const\\s+${name}\\s*=\\s*computed\\s*(<[^>]*>)?\\s*\\(`).exec(src)
  if (!m) throw new Error(`找不到 computed ${name}`)
  const open = src.indexOf('(', m.index + m[0].length - 1)
  const end = matchPair(src, open, '(', ')')
  if (end < 0) throw new Error(`${name} 实参不闭合`)
  return src.slice(open + 1, end)
}

const CODE = stripComments(HOST)

// ═══════════════════ helper 自身的 fixture 自检 ═════════════════════════════

describe('源码截取 helper 自检（防判据空转）', () => {
  it('fnBody 跳过返回类型注解里的花括号', () => {
    const fake = [
      'function f(a: { x: number }): Promise<{ ok: boolean }> {',
      '  return a.x',
      '}',
      'function g(): void {',
      '  const y = 1',
      '}',
    ].join('\n')
    expect(fnBody(fake, 'f')).toContain('return a.x')
    expect(fnBody(fake, 'f')).not.toContain('ok: boolean')
    expect(fnBody(fake, 'g')).toContain('const y = 1')
  })

  it('fnBody 只截目标函数，不吞下一个函数', () => {
    const fake = ['function a(): void {', '  const one = 1', '}', 'function b(): void {', '  const two = 2', '}'].join('\n')
    expect(fnBody(fake, 'a')).toContain('one')
    expect(fnBody(fake, 'a')).not.toContain('two')
  })

  it('computedArg 支持块体与表达式体', () => {
    const fake = [
      "const blockOne = computed(() => { return 'x' })",
      "const exprOne = computed(() => resolveIt('y'))",
    ].join('\n')
    expect(computedArg(fake, 'blockOne')).toContain("return 'x'")
    expect(computedArg(fake, 'exprOne')).toContain("resolveIt('y')")
  })

  it('stripComments 生效且不误剥 URL 里的双斜杠', () => {
    const fake = ['const u = "http://x/y" // trailing', '/* block */ const v = 1'].join('\n')
    const out = stripComments(fake)
    expect(out).toContain('http://x/y')
    expect(out).not.toContain('trailing')
    expect(out).not.toContain('block')
  })

  it('找不到目标时抛错（不静默返空串）', () => {
    expect(() => fnBody('const x = 1', 'nope')).toThrow()
    expect(() => computedArg('const x = 1', 'nope')).toThrow()
  })
})

// ═══════════════════ 段一：宿主消费 render 键 ════════════════════════════════

describe('段一：宿主消费 account_prefill（Requirements 1.6）', () => {
  it('后端 render 确实下发 account_prefill 键', () => {
    const py = read('backend/app/routers/wp_render_strategies/_e1_monetary_fund.py')
    expect(py).toContain('"account_prefill"')
    expect(py).toContain('def _build_account_prefill')
  })

  it('宿主有 accountPrefill computed 且读 props.htmlData?.account_prefill', () => {
    const arg = computedArg(CODE, 'accountPrefill')
    expect(arg).toContain('normalizeAccountPrefill')
    expect(arg).toContain('account_prefill')
    expect(arg).toContain('props.htmlData')
  })

  it('宿主 import 了账户级归一层的四个符号', () => {
    for (const sym of [
      'normalizeAccountPrefill',
      'buildBankSeedRowsFromAccounts',
      'buildAccountListSeedRowsFromAccounts',
      'buildDigitalSeedRows',
    ]) {
      expect(CODE, `宿主未 import ${sym}`).toContain(sym)
    }
    expect(CODE).toContain("from './composables/e1BankAccountPrefill'")
  })
})

// ═══════════════════ 段二：函数名与函数体内的接线 ════════════════════════════

describe('段二：种子化与重新取数的账户级优先链（Property 8）', () => {
  it('🔴 函数名是 reExtractFromFourTable（spec 写的 refetchFromFourTable 不存在）', () => {
    const hits = (CODE.match(/reExtractFromFourTable/g) || []).length
    expect(hits, 'reExtractFromFourTable 必须存在').toBeGreaterThanOrEqual(1)
    expect((CODE.match(/refetchFromFourTable/g) || []).length,
      'refetchFromFourTable 是 spec 的错名，不得出现').toBe(0)
  })

  it('seedFromFourTable 函数体内：E1-3 / E1-10 账户级优先 + 叶子兜底', () => {
    const body = fnBody(CODE, 'seedFromFourTable')
    expect(body).toMatch(/buildBankSeedRowsFromAccounts\([^)]*\)\s*\?\?\s*buildBankSeedRows\(/)
    expect(body).toMatch(/buildAccountListSeedRowsFromAccounts\([^)]*\)\s*\?\?\s*buildAccountListSeedRows\(/)
  })

  it('seedFromFourTable 函数体内：E1-3 传 variant（两版字段集不同）', () => {
    const body = fnBody(CODE, 'seedFromFourTable')
    expect(body).toMatch(/buildBankSeedRowsFromAccounts\(\s*\w+\s*,\s*e13Variant\.value\s*\)/)
  })

  it('seedFromFourTable 函数体内：E1-4 种子写 E1-digital-rows', () => {
    const body = fnBody(CODE, 'seedFromFourTable')
    expect(body).toContain('buildDigitalSeedRows')
    expect(body).toMatch(/seedRowsKey\(\s*'E1-digital-rows'/)
    expect(body, '不得写 spec 里的错名 E1-digital-detail-rows')
      .not.toContain('E1-digital-detail-rows')
  })

  it('reExtractFromFourTable 函数体内与种子化同口径（防两处产出两套行 id）', () => {
    const body = fnBody(CODE, 'reExtractFromFourTable')
    expect(body).toMatch(/buildBankSeedRowsFromAccounts\([^)]*\)\s*\?\?\s*buildBankSeedRows\(/)
    expect(body).toMatch(/buildAccountListSeedRowsFromAccounts\([^)]*\)\s*\?\?\s*buildAccountListSeedRows\(/)
    expect(body).toContain('buildDigitalSeedRows')
    expect(body).toContain("'E1-4'")
  })

  it('ftRowsKey 覆盖四张 sheet（E1-4 必须有映射，否则重新取数按钮不可达）', () => {
    const arg = computedArg(CODE, 'ftRowsKey')
    for (const [sheet, key] of [
      ['E1-2', 'E1-cash-detail-rows'],
      ['E1-3', 'E1-bank-detail-rows'],
      ['E1-4', 'E1-digital-rows'],
      ['E1-10', 'E1-account-list-rows'],
    ]) {
      expect(arg, `ftRowsKey 缺 ${sheet}`).toContain(`'${sheet}'`)
      expect(arg, `ftRowsKey 缺 ${key}`).toContain(`'${key}'`)
    }
  })

  it('showFtPanel 含 E1-4（面板不显示则重新取数按钮不可达）', () => {
    const arg = computedArg(CODE, 'showFtPanel')
    expect(arg).toContain("'E1-4'")
  })

  it('ftSources 为 E1-4 给出 digital 来源行', () => {
    const arg = computedArg(CODE, 'ftSources')
    expect(arg).toMatch(/'E1-4'[\s\S]{0,120}?digital/)
  })
})

// ═══════════════════ 段三：子 Tab 真的读那些键 ═══════════════════════════════

describe('段三：写入的键有真实消费方（否则是孤儿键）', () => {
  const CONSUMERS: Array<[string, string]> = [
    ['E1-bank-detail-rows', 'audit-platform/frontend/src/components/workpaper/composables/useE1BankDetail.ts'],
    ['E1-account-list-rows', 'audit-platform/frontend/src/components/workpaper/composables/useE1AccountList.ts'],
    ['E1-digital-rows', 'audit-platform/frontend/src/components/workpaper/e1/E1TabDigitalCurrency.vue'],
    ['E1-cash-detail-rows', 'audit-platform/frontend/src/components/workpaper/composables/useE1CashDetail.ts'],
  ]

  it.each(CONSUMERS)('%s 是消费方的 STORAGE_KEY', (key, rel) => {
    const src = read(rel)
    expect(src).toMatch(new RegExp(`STORAGE_KEY\\s*=\\s*'${key.replace(/-/g, '\\-')}'`))
  })

  it('E1-4 的 Tab 在宿主模板里收到 all-responses（否则种子进不去）', () => {
    const m = /<E1TabDigitalCurrency[\s\S]*?\/>/.exec(HOST)
    expect(m, '宿主模板未挂载 E1TabDigitalCurrency').toBeTruthy()
    expect(m![0]).toContain(':all-responses')
    expect(m![0]).toContain("currentSheet === 'E1-4'")
  })

  it('E1-3 的 Tab 收到 variant（两版共用持久化键，靠 variant 区分行模型）', () => {
    const m = /<E1TabBankDetail[\s\S]*?\/>/.exec(HOST)
    expect(m).toBeTruthy()
    expect(m![0]).toContain(':all-responses')
    expect(m![0]).toMatch(/:variant=/)
  })
})

// ═══════════════════ 反向自检：复现旧形态必红 ════════════════════════════════

describe('反向自检：判据对「删掉账户级优先链」必须打红', () => {
  const naiveSeed = [
    'function seedFromFourTable(): void {',
    '  const p = fourTablePrefill.value',
    '  const bankSeed = buildBankSeedRows(p)',
    '  const acctSeed = buildAccountListSeedRows(p)',
    "  seedRowsKey('E1-bank-detail-rows', bankSeed)",
    "  seedRowsKey('E1-account-list-rows', acctSeed)",
    '}',
  ].join('\n')

  it('叶子口径独占时，账户级优先判据不成立', () => {
    const body = fnBody(naiveSeed, 'seedFromFourTable')
    expect(body).not.toMatch(/buildBankSeedRowsFromAccounts\([^)]*\)\s*\?\?\s*buildBankSeedRows\(/)
    expect(body).not.toContain('buildDigitalSeedRows')
    // 而真实宿主必须成立（同一判据两侧对照）
    const real = fnBody(CODE, 'seedFromFourTable')
    expect(real).toMatch(/buildBankSeedRowsFromAccounts\([^)]*\)\s*\?\?\s*buildBankSeedRows\(/)
  })

  it('把 ?? 换成直接覆盖时判据不成立（账户级空态会清掉叶子种子）', () => {
    const overwrite = naiveSeed.replace(
      'const bankSeed = buildBankSeedRows(p)',
      'const bankSeed = buildBankSeedRowsFromAccounts(ap, e13Variant.value)',
    )
    const body = fnBody(overwrite, 'seedFromFourTable')
    expect(body).toContain('buildBankSeedRowsFromAccounts')
    expect(body).not.toMatch(/buildBankSeedRowsFromAccounts\([^)]*\)\s*\?\?\s*buildBankSeedRows\(/)
  })

  it('错名 refetchFromFourTable 的替身会被函数名判据抓住', () => {
    const wrong = 'async function refetchFromFourTable(): Promise<void> { return }'
    expect((wrong.match(/refetchFromFourTable/g) || []).length).toBeGreaterThan(0)
    expect((wrong.match(/\breExtractFromFourTable\b/g) || []).length).toBe(0)
  })
})
