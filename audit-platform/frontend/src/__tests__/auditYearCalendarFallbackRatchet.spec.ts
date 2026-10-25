/**
 * 拿不到审计年度时用「今年」的写法 —— 全前端棘轮（spec audit-year-calendar-fallback-ratchet 任务 1）。
 *
 * 审计年度应取项目的审计年度（`resolveAuditYearFromProject` / store / 路由），取不到时如实提示「未设置审计年度」。
 * 直接拿 `new Date().getFullYear()`（或减 1）兜底，跨年审计（1~4 月做上年报表）、往年项目、新项目未填年度时
 * 会静默取到别的年度的数，写请求还会写进别的年度。2026-10-25 现算冻结在 auditYearCalendarFallbackBaseline.json：
 *
 * * 新的出现处（基线外的文件，或文件里比基线多）⇒ 红；
 * * 文件里比基线少（修掉了 / 文件删了）⇒ 红，请把基线下调到现算值（为 0 删掉该行）—— 基线只许变小。
 *
 * 口径：src 下非测试源码（.ts / .tsx / .vue / .js / .mjs / .cjs；跳过 __tests__ / test / tests 目录与 *.spec / *.test / *.stories）
 * 里「今天的年份」表达式：`new Date().getFullYear()`、`(new Date()).getFullYear()`、`new Date(Date.now()).getFullYear()`、
 * `dayjs().year()`、`moment().year()`。整行注释（`//`、`/*`、`*`、`<!--` 开头）与行尾 `//` 注释不计。
 * 日历本身就该取今年的地方（年度声明、年份下拉上限等）同样冻结在表里，逐处判定见 spec 任务 2。
 * 盲区：先把 `new Date()` 存进变量再取 `.getFullYear()` 不计（与格式化日期同形，分不开）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '..')
const BASELINE_PATH = join(__dirname, 'auditYearCalendarFallbackBaseline.json')
const SOURCE_EXT = /\.(?:ts|tsx|vue|js|mjs|cjs)$/
const TEST_FILE = /\.(?:spec|test|stories)\.[cm]?[jt]sx?$/
const SKIP_DIRS = new Set(['__tests__', 'test', 'tests', 'node_modules'])
const TODAY_YEAR = new RegExp(
  [
    String.raw`\(\s*new\s+Date\s*\(\s*\)\s*\)\s*\.\s*getFullYear\s*\(\s*\)`,
    String.raw`new\s+Date\s*\(\s*(?:Date\.now\s*\(\s*\)\s*)?\)\s*\.\s*getFullYear\s*\(\s*\)`,
    String.raw`\b(?:dayjs|moment)\s*\(\s*\)\s*\.\s*year\s*\(\s*\)`,
  ].join('|'),
  'g',
)
const COMMENT_LINE = /^\s*(?:\/\/|\/\*|\*|<!--)/
/** 2026-10-25 冻结时的总数。挪动代码可以把条目挪到新文件，但基线总数不得超过它（净增不行）。 */
const FROZEN_TOTAL_CAP = 340

/** 引号成对（`//` 不在字符串里）。 */
function quotesBalanced(head: string): boolean {
  return ["'", '"', '`'].every((q) => head.split(q).length % 2 === 1)
}

/** 去掉行尾 `//` 注释：`//` 前须是空白，且它前面的引号成对。 */
function stripTrailingComment(line: string): string {
  const re = /\s\/\//g
  for (let m = re.exec(line); m; m = re.exec(line)) {
    const head = line.slice(0, m.index)
    if (quotesBalanced(head)) return head
  }
  return line
}

function countTodayYear(text: string): number {
  let n = 0
  for (const raw of text.split('\n')) {
    if (COMMENT_LINE.test(raw)) continue
    n += stripTrailingComment(raw).match(TODAY_YEAR)?.length ?? 0
  }
  return n
}

function isScannedFile(name: string): boolean {
  return SOURCE_EXT.test(name) && !TEST_FILE.test(name)
}

/** 测试目录整个跳过（里面的非 spec 文件是测试夹具 / 辅助，用今年造数据是正常的）。 */
function isSkippedDir(name: string): boolean {
  return SKIP_DIRS.has(name)
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (isSkippedDir(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (isScannedFile(name)) out.push(full)
  }
  return out
}

function scan(): { files: number; counts: Record<string, number> } {
  const files = walk(SRC)
  const counts: Record<string, number> = {}
  for (const file of files) {
    const n = countTodayYear(readFileSync(file, 'utf-8'))
    if (n) counts[relative(SRC, file).split('\\').join('/')] = n
  }
  return { files: files.length, counts }
}

const COUNTED = [
  'const year = props.year || new Date().getFullYear()',
  'const year = props.year ?? new Date().getFullYear() - 1',
  ':year="year || new Date().getFullYear()"',
  'const label = `${new Date().getFullYear()}年`',
  'const a = (new Date()).getFullYear()',
  'const b = new Date(Date.now()).getFullYear()',
  'const c = dayjs().year()',
  "const url = 'https://x.y/a' + String(new Date().getFullYear())",
]
const NOT_COUNTED = [
  '// 兜底 new Date().getFullYear()',
  ' * 兜底 `new Date().getFullYear()`',
  '/* new Date().getFullYear() */',
  '<!-- new Date().getFullYear() -->',
  'const y = props.year // 原先是 new Date().getFullYear()',
  "const u = 'https://x.y' // new Date().getFullYear()",
  'const d = new Date(2024, 0, 1).getFullYear()',
  'const e = new Date(row.date).getFullYear()',
]

describe('拿不到审计年度时用今年：只许减少（audit-year-calendar-fallback-ratchet）', () => {
  const { files, counts } = scan()
  const frozen = JSON.parse(readFileSync(BASELINE_PATH, 'utf-8')) as Record<string, number>

  it('扫描口径没失锚（计数规则 + 扫描范围）', () => {
    expect(COUNTED.map(countTodayYear)).toEqual(COUNTED.map(() => 1))
    expect(NOT_COUNTED.map(countTodayYear)).toEqual(NOT_COUNTED.map(() => 0))
    expect(countTodayYear(COUNTED.join('\n'))).toBe(COUNTED.length)
    const names = [
      'A.vue', 'b.ts', 'c.tsx', 'd.mjs',
      'E.spec.ts', 'f.test.ts', 'g.pbt.spec.ts', 'h.test.tsx', 'k.stories.ts', 'i.md', 'j.json',
    ]
    expect(names.filter(isScannedFile)).toEqual(['A.vue', 'b.ts', 'c.tsx', 'd.mjs'])
    const dirs = ['__tests__', 'test', 'tests', 'node_modules', 'components', 'testing', 'contest']
    expect(dirs.filter(isSkippedDir)).toEqual(['__tests__', 'test', 'tests', 'node_modules'])
    expect(files).toBeGreaterThan(3000)
  })

  it('没有新增：基线外的文件、或文件里比基线多', () => {
    const grown = Object.entries(counts)
      .filter(([rel, n]) => n > (frozen[rel] ?? 0))
      .map(([rel, n]) => `${rel}：基线 ${frozen[rel] ?? 0} → 现算 ${n}`)
    expect(
      grown,
      '审计年度请取项目年度，取不到如实提示，不要用今年兜底；只是把代码挪到别的文件时，把基线条目一起挪过去',
    ).toEqual([])
  })

  it('基线只许变小：已修掉的请把基线下调到现算值（为 0 删掉该行）', () => {
    const stale = Object.entries(frozen)
      .filter(([rel, n]) => (counts[rel] ?? 0) < n)
      .map(([rel, n]) => `${rel}：基线 ${n} → 现算 ${counts[rel] ?? 0}`)
    expect(stale).toEqual([])
  })

  it('基线文件规范（键已排序、值为正整数、总数不超过冻结值）', () => {
    const keys = Object.keys(frozen)
    expect(keys).toEqual([...keys].sort())
    expect(Object.values(frozen).filter((n) => !Number.isInteger(n) || n <= 0)).toEqual([])
    expect(Object.values(frozen).reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(FROZEN_TOTAL_CAP)
  })
})
