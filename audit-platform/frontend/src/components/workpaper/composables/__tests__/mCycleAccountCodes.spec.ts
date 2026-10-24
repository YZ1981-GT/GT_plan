/**
 * mCycleAccountCodes.spec.ts — M 循环（股东权益）科目码单一来源守卫
 *
 * spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.4
 *
 * 背景：2026-10-24 前 M3/M7/M8/M9/M10 的组合函数与页签写死的码整体错位（M3 写 4002 资本公积、
 * M7 写 4201 库存股、M8 写 4104 利润分配、M9 写 4103 本年利润、M10 写 4003 其他综合收益）。
 * 审定数发布按 `standard_account_code` 精确写行、不校验归属 ⇒ 发布 M3 会覆盖资本公积的试算表行……
 *
 * 本守卫锁四件事：
 * 1. `M_CYCLE_ACCOUNT` 与后端 `four_table/m_cycle_specs.py` 的兜底码 / 槽名逐项一致（读后端源码，不抄第二份）；
 * 2. M1~M10 组合函数 / 页签 / 主入口里不再出现科目码字面量（码只能取自 mCycleAccountScope）；
 * 3. 全前端「科目名 ↔ 码」配对一致（文案、注释、手册、选项列表都算）；
 * 4. 运行态定位：溯源必须属于本循环才用；M8 定位不到 / 多码时不能发布。
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'

import {
  M_CYCLE_ACCOUNT,
  OCI_ACCOUNT_CODE,
  isOwnMSource,
  mAccountCodeOf,
  mAccountLabel,
  mPublishBlockReason,
  type MCycleWpCode,
} from '../mCycleAccountScope'
import type { TbSourceCodes } from '../shared/tbSourceCodes'

// ─── 路径 ────────────────────────────────────────────────────────────────────

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
const BE_SPECS = resolve(REPO_ROOT, 'backend/app/services/four_table/m_cycle_specs.py')
const WORKPAPER_DIR = resolve(__dirname, '..', '..')
const FRONTEND_SRC = resolve(WORKPAPER_DIR, '..', '..')
const WP_CODES = Object.keys(M_CYCLE_ACCOUNT) as MCycleWpCode[]

function walk(dir: string, accept: (p: string) => boolean): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...walk(full, accept))
    else if (accept(full)) out.push(full)
  }
  return out
}

/** M{n} 文件集：m{n}/ 子目录 + useM{n}*.ts 组合函数 + GtM{n}* 主入口（不含测试） */
function mFileSet(wp: MCycleWpCode): string[] {
  const n = wp.slice(1)
  const isCode = (p: string) => /\.(ts|vue)$/.test(p) && !/[\\/]__tests__[\\/]/.test(p)
  const files = new Set<string>()
  const sub = join(WORKPAPER_DIR, `m${n}`)
  if (existsSync(sub)) walk(sub, isCode).forEach((f) => files.add(f))
  for (const name of readdirSync(join(WORKPAPER_DIR, 'composables'))) {
    if (new RegExp(`^useM${n}[A-Z].*\\.ts$`).test(name)) files.add(join(WORKPAPER_DIR, 'composables', name))
  }
  for (const name of readdirSync(WORKPAPER_DIR)) {
    if (new RegExp(`^GtM${n}[A-Z].*\\.vue$`).test(name)) files.add(join(WORKPAPER_DIR, name))
  }
  return [...files].sort()
}

/** 去注释（`//`、`/* *\/`、`<!-- -->`）；字符串里的 `//`（URL）按整行注释处理会误删，这里只删行首注释 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`])\/\/[^\n]*/g, '$1')
}

const rel = (p: string) => relative(FRONTEND_SRC, p).replace(/\\/g, '/')

// ═══════════════════════════════════════════════════════════════════
// 1. 与后端 m_cycle_specs 逐项一致
// ═══════════════════════════════════════════════════════════════════

interface BeSpec { fallback: string[]; label: string }

function parseBackendSpecs(): Record<string, BeSpec> {
  const src = readFileSync(BE_SPECS, 'utf-8')
  const out: Record<string, BeSpec> = {}
  const specRe = /^(M\d+)_SPEC = SemanticAccountSpec\(([\s\S]*?)^\)/gm
  for (const m of src.matchAll(specRe)) {
    const slot = /_equity\(\s*"gross",\s*\(([^)]*)\),\s*\(([^)]*)\),\s*"([^"]+)"\s*\)/.exec(m[2])
    if (!slot) continue
    const fallback = [...slot[2].matchAll(/"([^"]+)"/g)].map((x) => x[1])
    out[m[1]] = { fallback, label: slot[3] }
  }
  return out
}

describe('M_CYCLE_ACCOUNT 与后端 m_cycle_specs 一致', () => {
  const be = parseBackendSpecs()

  it('反向自检：解析出 M1~M10 全部 10 个规格（解析不到 = 守卫在空转）', () => {
    expect(Object.keys(be).sort()).toEqual([...WP_CODES].sort())
  })

  it.each(WP_CODES)('%s 兜底码与槽名逐项一致', (wp) => {
    const spec = be[wp]
    expect(spec, `${wp} 在后端没解析到`).toBeDefined()
    expect(M_CYCLE_ACCOUNT[wp].code).toBe(spec.fallback[0] ?? '')
    expect(spec.fallback.length, `${wp} 后端兜底码不止一个，前端单码表达不了`).toBeLessThanOrEqual(1)
    // 名称一致是 isOwnMSource 认归属的前提
    expect(M_CYCLE_ACCOUNT[wp].name).toBe(spec.label)
  })

  it('十个循环的码互不相同（空码除外）—— 撞码 = 发布会覆盖别的循环', () => {
    const codes = WP_CODES.map((wp) => M_CYCLE_ACCOUNT[wp].code).filter(Boolean)
    expect(new Set(codes).size).toBe(codes.length)
  })

  it('OCI_ACCOUNT_CODE 取自 M9', () => {
    expect(OCI_ACCOUNT_CODE).toBe(M_CYCLE_ACCOUNT.M9.code)
    expect(OCI_ACCOUNT_CODE).toBe(be.M9.fallback[0])
  })
})

// ═══════════════════════════════════════════════════════════════════
// 2. M 文件集不得写科目码字面量
// ═══════════════════════════════════════════════════════════════════

describe('M1~M10 组合函数 / 页签不写科目码字面量', () => {
  /** 权益 4xxx、旧制 3xxx、应付股利 2232 的独立字面量（'4201' / "4201"） */
  const LITERAL = /['"`](?:4\d{3}|3\d{3}|2232)['"`]/g

  it.each(WP_CODES)('%s 文件集', (wp) => {
    const files = mFileSet(wp)
    expect(files.length, `${wp} 文件集为空 ⇒ 路径或命名变了，守卫在空转`).toBeGreaterThan(5)
    const bad: string[] = []
    for (const f of files) {
      const cleaned = stripComments(readFileSync(f, 'utf-8'))
      for (const m of cleaned.matchAll(LITERAL)) bad.push(`${rel(f)}: ${m[0]}`)
    }
    expect(bad, '科目码只能取自 mCycleAccountScope（M_CYCLE_ACCOUNT / mAccountCodeOf）').toEqual([])
  })

  it.each(WP_CODES)('%s 的 ajeNet/rjeNet 标识符里的码 = 本循环码', (wp) => {
    const want = M_CYCLE_ACCOUNT[wp].code
    const bad: string[] = []
    for (const f of mFileSet(wp)) {
      for (const m of readFileSync(f, 'utf-8').matchAll(/\b[ar]jeNet(\d{4})\b/g)) {
        if (m[1] !== want) bad.push(`${rel(f)}: ${m[0]}（本循环码 ${want || '无'}）`)
      }
    }
    expect(bad).toEqual([])
  })

  it('反向自检：扫描器能抓到字面量', () => {
    const sample = "const ACCOUNT_CODE = '4002' // 库存股\nsubjectPrefix: \"4201\","
    expect(stripComments(sample).match(LITERAL)).toEqual(["'4002'", '"4201"'])
    expect(stripComments('// accountCode: \'4104\'').match(LITERAL)).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════
// 3. 全前端「科目名 ↔ 码」配对一致
// ═══════════════════════════════════════════════════════════════════

/** 名 → 正确码（客户科目表实证）。'' = 没有统一码（不得与任何码配对） */
const NAME_CODE: Record<string, string> = {
  实收资本: '4001', 股本: '4001', 资本公积: '4002', 其他综合收益: '4003', 盈余公积: '4101',
  本年利润: '4103', 利润分配: '4104', 未分配利润: '4104', 库存股: '4201', 专项储备: '4301',
  其他权益工具: '4401', 一般风险准备: '', 应付股利: '2232',
  // 资产类「其他权益工具投资」（G8，1503）只为挡住「其他权益工具」的前缀误配，不校验
  其他权益工具投资: '*',
}
const NAMES = Object.keys(NAME_CODE).sort((a, b) => b.length - a.length).join('|')
const CODE = '(?<![\\d.\\-])(4\\d{3}|3\\d{3}|2232)(?!\\d)'
const Q = `['"]`
const PAIR_RES: Array<{ re: RegExp; codeFirst: boolean }> = [
  { re: new RegExp(`${CODE}[ \\t]*(?:-[ \\t]*)?(${NAMES})`, 'g'), codeFirst: true },
  { re: new RegExp(`(${NAMES})[ \\t]*[（(][ \\t]*${CODE}[ \\t]*[)）]`, 'g'), codeFirst: false },
  {
    re: new RegExp(`(?:code|accountCode|account_code)${Q}?\\s*:\\s*${Q}(\\d{4})${Q}\\s*,\\s*`
      + `(?:name|accountName|account_name)${Q}?\\s*:\\s*${Q}(?:\\d{4}\\s*)?(${NAMES})`, 'g'),
    codeFirst: true,
  },
  {
    re: new RegExp(`(?:name|accountName|account_name)${Q}?\\s*:\\s*${Q}(${NAMES})${Q}\\s*,\\s*`
      + `(?:code|accountCode|account_code)${Q}?\\s*:\\s*${Q}(\\d{4})${Q}`, 'g'),
    codeFirst: false,
  },
]

function pairMismatches(text: string): string[] {
  const out: string[] = []
  for (const { re, codeFirst } of PAIR_RES) {
    for (const m of text.matchAll(re)) {
      const code = codeFirst ? m[1] : m[2]
      const name = codeFirst ? m[2] : m[1]
      const want = NAME_CODE[name]
      if (want === '*' || code === want) continue
      out.push(`${name}<-${code}（应为 ${want || '无统一码'}）: ${m[0].replace(/\s+/g, ' ').slice(0, 80)}`)
    }
  }
  return out
}

describe('全前端「科目名 ↔ 码」配对一致（文案 / 注释 / 手册 / 选项列表）', () => {
  // 本文件的反向自检样本本身就是错配写法 ⇒ 排除自己
  const files = walk(FRONTEND_SRC, (p) => /\.(ts|vue|md)$/.test(p) && !/[\\/]node_modules[\\/]/.test(p))
    .filter((p) => resolve(p) !== resolve(__filename))

  it('反向自检：扫描器能抓到四种写法的错配', () => {
    expect(pairMismatches('科目：4002 库存股')).toHaveLength(1)
    expect(pairMismatches('其他综合收益（4103）')).toHaveLength(1)
    expect(pairMismatches("{ code: '4104', name: '其他综合收益' }")).toHaveLength(1)
    expect(pairMismatches("accountName: '盈余公积',\n  accountCode: '3101',")).toHaveLength(1)
    expect(pairMismatches('4104 一般风险准备')).toHaveLength(1)
    expect(pairMismatches('库存股(4201) / 4003 其他综合收益 / 1503 其他权益工具投资')).toEqual([])
  })

  it('反向自检：扫描了足够多的文件', () => {
    expect(files.length).toBeGreaterThan(1000)
  })

  it('没有错配', () => {
    const bad: string[] = []
    for (const f of files) {
      for (const hit of pairMismatches(readFileSync(f, 'utf-8'))) bad.push(`${rel(f)}: ${hit}`)
    }
    expect(bad).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════
// 4. 运行态定位
// ═══════════════════════════════════════════════════════════════════

function semanticSrc(label: string, standard: string[], extra: Partial<TbSourceCodes> = {}): TbSourceCodes {
  return {
    row_code: 'BS-124',
    gross_standard: standard,
    chart_available: true,
    slots: { gross: { key: 'gross', label, standard_codes: standard, found: standard.length > 0 } },
    ...extra,
  }
}

describe('mAccountCodeOf / mPublishBlockReason', () => {
  it('没有溯源 ⇒ 兜底码；M8 没有兜底码 ⇒ 空串且不能发布', () => {
    expect(mAccountCodeOf('M3', null)).toBe('4201')
    expect(mPublishBlockReason('M3', null)).toBe('')
    expect(mAccountCodeOf('M8', null)).toBe('')
    expect(mPublishBlockReason('M8', null)).toContain('未取到')
  })

  it('本循环溯源定位到码 ⇒ 用定位结果', () => {
    const src = semanticSrc('一般风险准备', ['4102'])
    expect(isOwnMSource('M8', src)).toBe(true)
    expect(mAccountCodeOf('M8', src)).toBe('4102')
    expect(mPublishBlockReason('M8', src)).toBe('')
    expect(mAccountLabel('M8', mAccountCodeOf('M8', src))).toBe('一般风险准备(4102)')
  })

  it('🔴 别的循环的溯源（嵌入场景注入到宿主的 tbSourceCodes）不用', () => {
    const g8 = semanticSrc('其他权益工具投资', ['1503'])
    expect(isOwnMSource('M8', g8)).toBe(false)
    expect(mAccountCodeOf('M8', g8)).toBe('')
    expect(mPublishBlockReason('M8', g8)).not.toBe('')
    expect(mAccountCodeOf('M9', g8)).toBe('4003')
    // 没有 slots 的旧形态溯源（M7/M9 render 的 {row_code, codes}）同样不认
    expect(mAccountCodeOf('M7', { row_code: 'BS-086', gross_standard: ['9999'] })).toBe('4301')
  })

  it('本项目没有该科目 / 科目表未导入 ⇒ 不能发布，原因分开说', () => {
    expect(mPublishBlockReason('M8', semanticSrc('一般风险准备', []))).toContain('没有「一般风险准备」科目')
    expect(mPublishBlockReason('M8', semanticSrc('一般风险准备', [], { chart_available: false }))).toContain('未导入')
    expect(mAccountLabel('M8', '')).toBe('一般风险准备（本项目无此科目）')
  })

  it('定位到多个标准码 ⇒ 不能发布（写一个码会漏掉其余码）', () => {
    const reason = mPublishBlockReason('M8', semanticSrc('一般风险准备', ['4102', '4105']))
    expect(reason).toContain('多个标准科目')
    expect(reason).toContain('4102、4105')
  })

  it('展示名：M2 / M6 用界面名', () => {
    expect(mAccountLabel('M2')).toBe('实收资本/股本(4001)')
    expect(mAccountLabel('M6')).toBe('未分配利润(4104)')
    expect(mAccountLabel('M3')).toBe('库存股(4201)')
  })
})
