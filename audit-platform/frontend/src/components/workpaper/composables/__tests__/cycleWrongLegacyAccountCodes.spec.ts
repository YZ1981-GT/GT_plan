/**
 * cycleWrongLegacyAccountCodes.spec.ts — 各循环「已声明的历史错码」残留守卫
 *
 * spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.4（触类旁通）
 *
 * 背景：J2 / K2 / K4 / K5 / L6 / L7 的科目真源（*AccountScope.ts）早已写明「哪个码是错的」，
 * 并注明「守卫用（源码不得再出现该字面量作科目码）」—— 但仓库里**没有任何守卫真的去扫源码**
 * （`L6_WRONG_LEGACY_ACCOUNT` / `J2_WRONG_LEGACY_ACCOUNTS` 只被断言了常量值本身）。
 * 结果 2026-10-24 现扫仍有：
 *   - J2 带入调整按 `2221`（应交税费）拉分录；L6 按 `2601`（租赁负债）；L7 按 `2801`（预计负债）；
 *   - K4 发布缺省回退 `2245`、调整分录 / 附注事件都带 `2245`；
 *   - K5 发布后事件载荷写死 `2701`（长期应付款）——既有守卫 k5AccountCodeNoHardcode 只扫 k5/ 目录，漏了组合函数；
 *   - 以及大量把错码写给用户看的说明文案与手册。
 *
 * 本守卫：
 * 1. 零容忍组（真源已声明错码的循环）：去掉注释后，文件集里不得再出现错码（解释性 UI 文案逐条登记）；
 * 2. 棘轮组（已登记待决、本 spec 不改的循环 G1 / I2 / I5 / I6）：残留只许减少；
 * 3. K1 坏账准备不得用宽口径 `1231` 带入 / 发布（应收票据 / 应收账款的坏账同在该码下）；
 * 4. 全前端「带入调整」的字面量科目码必须属于该底稿在 wp_account_mapping.json 的科目，例外逐条登记理由。
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'

import { J2_GROSS_FALLBACK, J2_WRONG_LEGACY_ACCOUNTS } from '../jAccountScope'
import { K2_GROSS_FALLBACK_STANDARD, K2_WRONG_LEGACY_ACCOUNT } from '../k2AccountScope'
import { K4_FALLBACK_STANDARD, K4_WRONG_LEGACY_ACCOUNTS } from '../k4AccountScope'
import { K5_FALLBACK_STANDARD, K5_WRONG_LEGACY_ACCOUNT } from '../k5AccountScope'
import { L6_GROSS_FALLBACK_STANDARD, L6_WRONG_LEGACY_ACCOUNT } from '../l6AccountScope'
import { L7_GROSS_FALLBACK_STANDARD, L7_WRONG_LEGACY_ACCOUNTS } from '../l7AccountScope'
import { L3_GROSS_FALLBACK_STANDARD } from '../l3AccountScope'
import { G1_GROSS_FALLBACK_STANDARD } from '../g1AccountScope'
import { I2_GROSS_FALLBACK_STANDARD } from '../i2AccountScope'
import { I5_GROSS_FALLBACK_STANDARD } from '../i5AccountScope'
import { I6_GROSS_FALLBACK_STANDARD } from '../i6AccountScope'

// ─── 路径与文件集 ─────────────────────────────────────────────────────────────

function findRepoRoot(start: string): string {
  let cur = start
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(cur, 'backend')) && existsSync(join(cur, 'audit-platform'))) return cur
    const parent = dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  throw new Error('找不到仓库根（缺 backend/ + audit-platform/ 双哨兵）')
}

const REPO_ROOT = findRepoRoot(__dirname)
const WORKPAPER_DIR = resolve(__dirname, '..', '..')
const COMPOSABLES_DIR = join(WORKPAPER_DIR, 'composables')
/** `src/composables/`（部分循环的组合函数放在这里，如 useL3Adjustment） */
const ROOT_COMPOSABLES_DIR = resolve(WORKPAPER_DIR, '..', '..', 'composables')
const MAPPING_JSON = resolve(REPO_ROOT, 'backend/data/wp_account_mapping.json')

const rel = (p: string) => relative(WORKPAPER_DIR, p).replace(/\\/g, '/')

function walk(dir: string, accept: (p: string) => boolean): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      if (name === '__tests__') continue
      out.push(...walk(full, accept))
    } else if (accept(full)) out.push(full)
  }
  return out
}

const isScanned = (p: string) => /\.(ts|vue|md)$/.test(p)

/**
 * 循环文件集：`{x}{n}` / `{x}{n}-*` 子目录 + `use{X}{n}*.ts` / `{x}{n}*.ts` 组合函数 + `Gt{X}{n}*.vue` 主入口。
 * 含 .md 手册（手册经 `?raw` 渲染给用户看）；不含测试；不含真源文件本身。
 */
function cycleFileSet(wp: string, scopeFile: string): string[] {
  const letter = wp[0].toLowerCase()
  const n = wp.slice(1)
  const files = new Set<string>()
  for (const name of readdirSync(WORKPAPER_DIR)) {
    const full = join(WORKPAPER_DIR, name)
    if (statSync(full).isDirectory() && new RegExp(`^${letter}${n}(?:$|[-_])`).test(name)) {
      walk(full, isScanned).forEach((f) => files.add(f))
    }
    if (new RegExp(`^Gt${wp}[A-Z].*\\.vue$`).test(name)) files.add(full)
  }
  for (const name of readdirSync(COMPOSABLES_DIR)) {
    if (name === scopeFile) continue
    if (new RegExp(`^(use${wp}|${letter}${n})[A-Z].*\\.ts$`).test(name)) files.add(join(COMPOSABLES_DIR, name))
  }
  for (const name of readdirSync(ROOT_COMPOSABLES_DIR)) {
    if (new RegExp(`^use${wp}[A-Z].*\\.ts$`).test(name)) files.add(join(ROOT_COMPOSABLES_DIR, name))
  }
  return [...files].sort()
}

/**
 * 后端「公式说明目录」`routers/wp_surfaced_{x}.py` 里该底稿的一段（向用户展示取数 / 回写口径）。
 * 只取 `"X{n}": {` 到下一个同级键之间，并去掉 `#` 注释；文件头的循环总览不在段内。
 */
function surfacedSection(wp: string): string | null {
  const f = resolve(REPO_ROOT, `backend/app/routers/wp_surfaced_${wp[0].toLowerCase()}.py`)
  if (!existsSync(f)) return null
  const src = readFileSync(f, 'utf-8').replace(/\r\n/g, '\n')
  const m = new RegExp(`^ {4}"${wp}": \\{`, 'm').exec(src)
  if (!m) return null
  const rest = src.slice(m.index + m[0].length)
  const next = rest.search(/^ {4}"[A-Z]\d+": \{|^\}/m)
  return (next < 0 ? rest : rest.slice(0, next)).replace(/#[^\n]*/g, '')
}

/** 去注释并保留行号（`<!-- -->`、`/* *\/` 换成等量换行；行内 `//` 注释截掉，URL 的 `://` 不动） */
function stripComments(src: string, isMd: boolean): string {
  if (isMd) return src
  const keepNewlines = (m: string) => m.replace(/[^\n]/g, '')
  return src
    .replace(/<!--[\s\S]*?-->/g, keepNewlines)
    .replace(/\/\*[\s\S]*?\*\//g, keepNewlines)
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
}

function codeRe(codes: readonly string[]): RegExp {
  // 前后不能紧贴数字 / 字母：`unadjusted1717` 这类驼峰标识符不算；
  // `1231-03` 子目、`provisions_2701_unadjusted` 这种把错码写进契约键名的都算
  return new RegExp(`(?<![\\dA-Za-z])(${codes.join('|')})(?![\\dA-Za-z])`)
}

interface Hit { file: string; line: number; text: string }

function scanText(src: string, isMd: boolean, codes: readonly string[]): Array<{ line: number; text: string }> {
  const re = codeRe(codes)
  const out: Array<{ line: number; text: string }> = []
  stripComments(src, isMd).split('\n').forEach((l, i) => {
    if (re.test(l)) out.push({ line: i + 1, text: l.trim() })
  })
  return out
}

function scanCycle(wp: string, scopeFile: string, codes: readonly string[]): Hit[] {
  const hits: Hit[] = []
  for (const f of cycleFileSet(wp, scopeFile)) {
    const src = readFileSync(f, 'utf-8')
    for (const h of scanText(src, f.endsWith('.md'), codes)) hits.push({ file: rel(f), ...h })
  }
  return hits
}

// ═══════════════════════════════════════════════════════════════════
// 0. 扫描器自检（判据不能空转）
// ═══════════════════════════════════════════════════════════════════

describe('扫描器自检', () => {
  it('代码里的错码被抓到；注释里的说明不算；标识符后缀不算；子目算', () => {
    const src = [
      "const code = '2245'",                 // 1 抓
      '// 原写死 2245 —— 不是其他流动负债',      // 2 不抓（行注释）
      '/* 历史 2245 */ const ok = 1',         // 3 不抓（块注释）
      '<!-- 2245 说明 -->',                   // 4 不抓（HTML 注释）
      'const unadjusted2245 = 0',            // 5 不抓（驼峰标识符）
      "<li>回写 TB(2245)</li>",               // 6 抓（给用户看的文案）
      "const sub = '2245.01'",               // 7 抓（子目）
      "const url = 'http://x/2245'",         // 8 抓（字符串内容，不是注释）
      'tb_values?.liability_2245_audited',   // 9 抓（错码写进了契约键名）
    ].join('\n')
    expect(scanText(src, false, ['2245']).map((h) => h.line)).toEqual([1, 6, 7, 8, 9])
  })

  it('块注释跨行时保留行号', () => {
    const src = ['/**', ' * 2245', ' */', "const c = '2245'"].join('\n')
    expect(scanText(src, false, ['2245']).map((h) => h.line)).toEqual([4])
  })

  it('手册（.md）不剔注释，全文算', () => {
    expect(scanText('| 回写 2245 |', true, ['2245'])).toHaveLength(1)
  })

  it('文件集非空且不含测试 / 真源文件', () => {
    const files = cycleFileSet('K4', 'k4AccountScope.ts').map(rel)
    expect(files.length).toBeGreaterThan(10)
    expect(files.some((f) => f.includes('__tests__'))).toBe(false)
    expect(files).not.toContain('composables/k4AccountScope.ts')
    expect(files).toContain('composables/useK4FormData.ts')
    expect(files).toContain('k4/handbooks/preparation.md')
    // K1 的文件集不能把 K10~K13 吞进来（`k1AdjK11Writeback.ts` 是 K1 自己的文件，不算）
    const k1 = cycleFileSet('K1', 'k1AccountScope.ts').map(rel)
    expect(k1.filter((f) => /(^|\/)k1[0-3]\/|useK1[0-3]|GtK1[0-3]|(^|\/)k1[0-3][A-Z]/.test(f))).toEqual([])
    expect(k1).toContain('composables/useK1FormData.ts')
  })
})

// ═══════════════════════════════════════════════════════════════════
// 1. 零容忍组：真源已声明错码的循环
// ═══════════════════════════════════════════════════════════════════

interface ZeroCase {
  wp: string
  scopeFile: string
  wrong: readonly string[]
  /** 真源的正确码（'' / null = 宁缺勿造，无标准码） */
  fallback: string | null
}

const ZERO_CASES: ZeroCase[] = [
  { wp: 'J2', scopeFile: 'jAccountScope.ts', wrong: J2_WRONG_LEGACY_ACCOUNTS, fallback: J2_GROSS_FALLBACK },
  { wp: 'K2', scopeFile: 'k2AccountScope.ts', wrong: [K2_WRONG_LEGACY_ACCOUNT], fallback: K2_GROSS_FALLBACK_STANDARD },
  { wp: 'K4', scopeFile: 'k4AccountScope.ts', wrong: K4_WRONG_LEGACY_ACCOUNTS, fallback: K4_FALLBACK_STANDARD },
  { wp: 'K5', scopeFile: 'k5AccountScope.ts', wrong: [K5_WRONG_LEGACY_ACCOUNT], fallback: K5_FALLBACK_STANDARD },
  { wp: 'L6', scopeFile: 'l6AccountScope.ts', wrong: [L6_WRONG_LEGACY_ACCOUNT], fallback: L6_GROSS_FALLBACK_STANDARD },
  { wp: 'L7', scopeFile: 'l7AccountScope.ts', wrong: L7_WRONG_LEGACY_ACCOUNTS, fallback: L7_GROSS_FALLBACK_STANDARD },
  // L3 的一年内到期重分类贷方原写 2801 —— 2801 是预计负债（K5 的真源兜底码），不是「一年内到期的非流动负债」
  { wp: 'L3', scopeFile: 'l3AccountScope.ts', wrong: [K5_FALLBACK_STANDARD], fallback: L3_GROSS_FALLBACK_STANDARD },
]

/**
 * 解释性 UI 文案：给用户看「为什么不是这个码」，必须保留原码。
 * 每条须在现扫里恰好命中一行（多了 / 少了都报错，防登记失效或被复制扩散）。
 */
const EXPLANATION_ALLOWLIST: Array<{ wp: string; file: string; contains: string; reason: string }> = [
  {
    wp: 'K2', file: 'k2/core/K2FourTableSourcePanel.vue', contains: '历史实现误把 <code>1231</code> 当其他流动资产',
    reason: '溯源面板向用户说明 1231 是坏账准备、不是其他流动资产',
  },
  {
    wp: 'L7', file: 'l7/core/L7TabAdjudication.vue', contains: '<code>2801</code> 是预计负债（K5）',
    reason: '溯源面板向用户说明其他非流动负债没有专属科目码、2801 属预计负债',
  },
  {
    wp: 'L7', file: 'l7/core/L7TabAdjudication.vue', contains: '<code>2901</code> 是递延所得税负债（N1/N3）',
    reason: '同上：2901 属递延所得税负债',
  },
]

describe('零容忍组：真源已声明的错码不得残留（注释里的历史说明除外）', () => {
  it.each(ZERO_CASES.map((c) => [c.wp, c] as const))('%s 真源错码 ≠ 真源正确码', (_wp, c) => {
    expect(c.wrong.length).toBeGreaterThan(0)
    for (const w of c.wrong) expect(w).not.toBe(c.fallback)
  })

  it.each(ZERO_CASES.map((c) => [c.wp, c] as const))('%s 文件集去注释后无错码', (wp, c) => {
    const hits = scanCycle(wp, c.scopeFile, c.wrong)
    const allowed = EXPLANATION_ALLOWLIST.filter((a) => a.wp === wp)
    const offenders = hits.filter((h) => !allowed.some((a) => h.file === a.file && h.text.includes(a.contains)))
    expect(
      offenders.map((h) => `${h.file}:${h.line}: ${h.text}`),
      `${wp} 仍有真源已声明为错码（${c.wrong.join('/')}）的残留；改用 ${c.scopeFile} 的真源，` +
        '或（仅限向用户解释为什么不是该码的文案）登记到 EXPLANATION_ALLOWLIST',
    ).toEqual([])
  })

  it.each(ZERO_CASES.map((c) => [c.wp, c] as const))('%s 后端公式说明目录（wp_surfaced）该底稿段无错码', (wp, c) => {
    const sec = surfacedSection(wp)
    if (sec === null) return // 该循环没有说明目录段
    const re = codeRe(c.wrong)
    const bad = sec.split('\n').filter((l) => re.test(l)).map((l) => l.trim())
    expect(bad, `${wp} 说明目录仍向用户展示错码 ${c.wrong.join('/')}`).toEqual([])
  })

  it('说明目录段确实取到了（防空转）', () => {
    for (const wp of ['J2', 'K4', 'K5', 'L3', 'L6', 'L7']) {
      const sec = surfacedSection(wp)
      expect(sec, `${wp} 段没取到`).not.toBeNull()
      expect(sec!.length, `${wp} 段为空`).toBeGreaterThan(200)
    }
    // 段边界：J2 段不能吞进 J3
    expect(surfacedSection('J2')).not.toMatch(/"J3-1"/)
  })

  it.each(EXPLANATION_ALLOWLIST.map((a) => [`${a.wp} ${a.file}`, a] as const))('登记项仍有效且只命中一行：%s', (_k, a) => {
    const c = ZERO_CASES.find((z) => z.wp === a.wp)!
    const hits = scanCycle(a.wp, c.scopeFile, c.wrong).filter((h) => h.file === a.file && h.text.includes(a.contains))
    expect(hits, `登记项已失效（文案改了或删了）：${a.contains}`).toHaveLength(1)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 2. 棘轮组：已登记待决（design §10.3），残留只许减少
// ═══════════════════════════════════════════════════════════════════

interface RatchetCase {
  wp: string
  scopeFile: string
  wrong: readonly string[]
  fallback: string
  /** 现扫基线（2026-10-24）。修掉一处就把基线降下来；不许升。 */
  baseline: number
  why: string
}

const RATCHET_CASES: RatchetCase[] = [
  { wp: 'G1', scopeFile: 'g1AccountScope.ts', wrong: ['1501'], fallback: G1_GROSS_FALLBACK_STANDARD, baseline: 44, why: '1501 是持有至到期投资（G4）；交易性金融资产是 1101' },
  { wp: 'I2', scopeFile: 'i2AccountScope.ts', wrong: ['1717'], fallback: I2_GROSS_FALLBACK_STANDARD, baseline: 60, why: '1717 真实库无此码；开发支出是 1704' },
  { wp: 'I5', scopeFile: 'i5AccountScope.ts', wrong: ['1911', '1901'], fallback: I5_GROSS_FALLBACK_STANDARD, baseline: 55, why: '其他非流动资产无标准独立码；1901 是其他流动资产（K2）' },
  { wp: 'I6', scopeFile: 'i6AccountScope.ts', wrong: ['6602'], fallback: I6_GROSS_FALLBACK_STANDARD, baseline: 69, why: '6602 是管理费用（K9）；研发费用是 6604' },
]

/** 基线允许的「虚高」上限：现扫比基线少太多说明有人修了却没降基线 */
const RATCHET_SLACK = 5

describe('棘轮组：已登记待决的错码残留只许减少', () => {
  it.each(RATCHET_CASES.map((c) => [c.wp, c] as const))('%s 错码 ≠ 真源正确码（登记依据仍成立）', (_wp, c) => {
    for (const w of c.wrong) expect(w, c.why).not.toBe(c.fallback)
  })

  it.each(RATCHET_CASES.map((c) => [c.wp, c] as const))('%s 残留不超过基线、基线不虚高', (wp, c) => {
    const n = scanCycle(wp, c.scopeFile, c.wrong).length
    expect(n, `${wp} 错码残留 ${n} 超过基线 ${c.baseline}（${c.why}）`).toBeLessThanOrEqual(c.baseline)
    expect(c.baseline - n, `${wp} 现扫 ${n}，比基线 ${c.baseline} 少了 ${c.baseline - n}：请把基线降到 ${n}`).toBeLessThanOrEqual(RATCHET_SLACK)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 3. K1 坏账准备：不得用宽口径 1231 带入 / 发布
// ═══════════════════════════════════════════════════════════════════

describe('K1 坏账准备只用本循环专属备抵口径', () => {
  const ADJ = join(WORKPAPER_DIR, 'k1/core/K1TabAdjudication.vue')
  const FORM = join(COMPOSABLES_DIR, 'useK1FormData.ts')

  it('K1-1 审定表与发布组合函数里没有 `1231` 字面量（宽口径同时承载应收票据 / 应收账款的坏账）', () => {
    for (const f of [ADJ, FORM]) {
      const src = stripComments(readFileSync(f, 'utf-8'), false)
      expect(src, `${rel(f)} 仍有宽口径 '1231'`).not.toMatch(/['"`]1231['"`]/)
    }
  })

  it('带入与发布都取 k1ProvisionQueryCodes（render 溯源 provision_standard，兜底 1231-03）', () => {
    const src = stripComments(readFileSync(ADJ, 'utf-8'), false)
    expect(src).toMatch(/subjectPrefix:\s*\(\)\s*=>\s*k1ProvisionQueryCodes\(props\.tbSourceCodes\)/)
    expect(src).toMatch(/const k1BadDebtCode = computed\(\(\) => k1ProvisionQueryCodes\(props\.tbSourceCodes\)\[0\]\)/)
    expect(src).toMatch(/writebackTB\(recSec\.subtotalRow\.audited, bdSec\.subtotalRow\.audited, codes\)/)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 4. 「带入调整」的字面量科目码必须属于该底稿的映射科目
// ═══════════════════════════════════════════════════════════════════

function loadMapping(): Map<string, Set<string>> {
  const data = JSON.parse(readFileSync(MAPPING_JSON, 'utf-8'))
  const out = new Map<string, Set<string>>()
  for (const e of data.mappings ?? []) {
    const m = /^([A-Z]\d+)/.exec(String(e.wp_code ?? ''))
    if (!m) continue
    const set = out.get(m[1]) ?? new Set<string>()
    for (const c of e.account_codes ?? []) set.add(String(c))
    out.set(m[1], set)
  }
  return out
}

interface BringInCall { file: string; line: number; wp: string; prefix: string; code: string }

/** 抽取 `useAdjudicationBringIn({...})` 调用的 wpCode / subjectPrefix / subjectCode 原文 */
function extractBringInCalls(src: string, file: string): BringInCall[] {
  const out: BringInCall[] = []
  const re = /useAdjudicationBringIn\(\s*\{/g
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    const body = src.slice(m.index, m.index + 2000)
    const wp = /wpCode:\s*['"]([A-Z]\d+)['"]/.exec(body)?.[1] ?? '?'
    const prefix = /subjectPrefix:\s*([^\n]+)/.exec(body)?.[1]?.trim() ?? ''
    const code = /subjectCode:\s*([^\n]+)/.exec(body)?.[1]?.trim() ?? ''
    out.push({ file, line: src.slice(0, m.index).split('\n').length, wp, prefix, code })
  }
  return out
}

const LITERAL_CODE_RE = /['"](\d{4}(?:[-.]\d{2})?)['"]/g
const literalCodes = (expr: string) => [...expr.matchAll(LITERAL_CODE_RE)].map((x) => x[1])

/**
 * 不在映射里、但有理由的字面量（逐条写明；`registered` = design §10.3 已登记待用户决定，不在本 spec 改）。
 */
const BRING_IN_ALLOWLIST: Array<{ wp: string; code: string; reason: string; registered?: boolean }> = [
  { wp: 'H5', code: '1632', reason: '累计折耗（备抵科目）；映射表只列原值 1631' },
  { wp: 'L5', code: '2702', reason: '未确认融资费用（备抵科目）；映射表只列原值 2701' },
  { wp: 'G1', code: '1501', reason: '映射为 1101；G 循环 1501 拆分待决', registered: true },
  { wp: 'G4', code: '1501', reason: '映射为 1504；1501 / 1504 新旧准则科目待决', registered: true },
  { wp: 'G8', code: '1503', reason: '映射为 1507（2026-10-24 第三批）；G 循环旧准则码 1503 待决，与 G1 / G4 的 1501 同批定', registered: true },
  { wp: 'D5', code: '1124', reason: '应收款项融资无标准独立码、映射表为空；D 循环另有会话在改', registered: true },
]

describe('「带入调整」字面量科目码 ⊆ 该底稿的映射科目', () => {
  const mapping = loadMapping()
  const calls = walk(WORKPAPER_DIR, (p) => /\.(ts|vue)$/.test(p))
    .flatMap((f) => extractBringInCalls(stripComments(readFileSync(f, 'utf-8'), false), rel(f)))

  it('自检：抽到足够多的调用、映射表可读', () => {
    expect(calls.length).toBeGreaterThan(60)
    expect(mapping.get('D1')?.has('1121')).toBe(true)
    const synthetic = extractBringInCalls("useAdjudicationBringIn({\n  subjectPrefix: '2601',\n  subjectCode: X,\n  wpCode: 'L6',\n})", 'x.vue')
    expect(synthetic).toEqual([{ file: 'x.vue', line: 1, wp: 'L6', prefix: "'2601',", code: 'X,' }])
    expect(literalCodes("['1231-03', '2245']")).toEqual(['1231-03', '2245'])
  })

  it('每处字面量码都属于映射或已登记', () => {
    const offenders: string[] = []
    for (const c of calls) {
      const want = mapping.get(c.wp) ?? new Set<string>()
      for (const code of [...literalCodes(c.prefix), ...literalCodes(c.code)]) {
        if (want.has(code)) continue
        if (BRING_IN_ALLOWLIST.some((a) => a.wp === c.wp && a.code === code)) continue
        offenders.push(`${c.file}:${c.line} ${c.wp} 带入码 ${code}（映射 ${[...want].join('/') || '空'}）`)
      }
    }
    expect(offenders, '带入调整按别的科目拉分录：改用该循环的科目真源，或写明理由登记到 BRING_IN_ALLOWLIST').toEqual([])
  })

  it.each(BRING_IN_ALLOWLIST.map((a) => [`${a.wp} ${a.code}`, a] as const))('登记项仍在用：%s', (_k, a) => {
    const used = calls.some((c) => c.wp === a.wp && [...literalCodes(c.prefix), ...literalCodes(c.code)].includes(a.code))
    expect(used, `登记项已失效（${a.wp} 不再用 ${a.code}）：删掉这条`).toBe(true)
    expect(mapping.get(a.wp)?.has(a.code) ?? false, `${a.wp} 映射已含 ${a.code}，不必再登记`).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 5. 运行态：事件码 = 发布码；空码不去匹配别人的事件
// ═══════════════════════════════════════════════════════════════════

describe('运行态：K4 事件归属 / K5 事件码', () => {
  it('K4：按 wpCode 认；空码不匹配别人的空码事件，也不认持有错码 2245 的事件', async () => {
    const { isK4Event } = await import('../k4AccountScope')
    expect(isK4Event({ wpCode: 'K4' }, '')).toBe(true)
    expect(isK4Event({ wpCode: 'L7', accountCode: '' }, '')).toBe(false)
    expect(isK4Event({ wpCode: 'K6', accountCode: '2245' }, '')).toBe(false)
    expect(isK4Event({ wpCode: 'X', accountCode: '2249' }, '2249')).toBe(true)
    expect(isK4Event({ wpCode: 'X', accountCode: '2249' }, '2250')).toBe(false)
  })

  it('K4 两个附注页签都用共享判定（不再各写一份按码匹配）', () => {
    for (const f of ['k4/core/K4TabDisclosureListed.vue', 'k4/core/K4TabDisclosureSoe.vue']) {
      const src = stripComments(readFileSync(join(WORKPAPER_DIR, f), 'utf-8'), false)
      expect(src, f).toMatch(/matchesK4Event\(payload, k4EventCode\(\)\)/)
      expect(src, f).not.toMatch(/payload\.accountCode === K4_ACCOUNT_CODE/)
    }
  })

  it('K5：发布后事件载荷的科目码 = 调用方传入的发布码', async () => {
    const { ref } = await import('vue')
    const { eventBus } = await import('@/utils/eventBus')
    const { useK5Adjudication } = await import('../useK5Adjudication')
    const seen: any[] = []
    const handler = (p: any) => seen.push(p)
    eventBus.on('substantive:adjudicated', handler)
    try {
      const adj = useK5Adjudication({
        allResponses: ref(new Map()),
        tbData: ref({ unadjusted: 0, audited: 0 }) as any,
        saveResponse: async () => {},
      })
      adj.publishAdjudicated('2801-09')
    } finally {
      eventBus.off('substantive:adjudicated', handler)
    }
    expect(seen.map((p) => p.accountCode)).toEqual(['2801-09'])
  })

  it('K5-1 发布后用本次发布码发事件', () => {
    const src = stripComments(readFileSync(join(WORKPAPER_DIR, 'k5/core/K5TabAdjudication.vue'), 'utf-8'), false)
    expect(src).toMatch(/const accountCode = k5AccountCode\(props\.tbSourceCodes as any\)/)
    expect(src).toMatch(/publishAdjudicated\(accountCode\)/)
  })

  it('L7 带入调整按钮在无可映射科目时禁用', () => {
    const src = readFileSync(join(WORKPAPER_DIR, 'l7/core/L7TabAdjudication.vue'), 'utf-8')
    expect(src).toMatch(/:disabled="!l7BringInCodes\.length"[^>]*@click="openBringInAdjustment"/)
    expect(src).toMatch(/const l7BringInCodes = computed\(\(\) => l7GrossQueryCodes\(tbSourceCodes\.value\)\)/)
  })
})
