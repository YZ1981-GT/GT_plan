/**
 * 拿不到审计年度时用「写死的年份」兜底 —— 全前端守卫（spec post-push-residual-defect-closure R2）。
 *
 * 与 auditYearCalendarFallbackRatchet（`new Date().getFullYear()` 兜底）同一类缺陷的另一种写法：
 * `year ?? 2025`、`props.year || 2025`、参数缺省 `year = 2025`、`ref(2025)`。日历棘轮看不到它们，
 * 2026-10-26 现扫 14 处，其中真缺陷：一致性看板两处调用不传年度 ⇒ 任何项目都按 2025 校验；合并快照恒建在
 * 2025；辅助余额汇总页恒按 2025 汇总；D4（6）剩余履约义务表头恒为 2026年 / 2027年；工作流进度条、试算表 /
 * 调整分录的联动徽章与影响预览在没选年度时按 2025 取数。全部改为「取项目审计年度，取不到如实提示」后清零。
 *
 * 口径：src 下非测试源码（.ts / .tsx / .vue；跳过 __tests__ / test / tests / node_modules 与 *.spec / *.test / *.stories），
 * 整行注释（`//`、`/*`、`*`、`<!--` 开头）不计。豁免须写明理由且仍命中（失效即红）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '..')
const SOURCE_EXT = /\.(?:ts|tsx|vue)$/
const TEST_FILE = /\.(?:spec|test|stories)\.[cm]?[jt]sx?$/
const SKIP_DIRS = new Set(['__tests__', 'test', 'tests', 'node_modules'])
const COMMENT_LINE = /^\s*(?:\/\/|\/\*|\*|<!--)/

/** 三种写法：空值兜底到字面年份 / 年度参数缺省为字面年份 / ref 初值为字面年份 */
const PATTERNS: Array<[string, RegExp]> = [
  ['fallback', /(?:\?\?|\|\|)\s*20[12]\d\b(?!\s*[-/年])/],
  ['param-default', /\b(?:year|auditYear|fiscalYear|currentYear)\w*\s*(?::\s*number(?:\s*\|\s*null)?)?\s*=\s*20[12]\d\b/],
  ['ref-init', /\bref(?:<[^>]*>)?\(\s*20[12]\d\s*\)/],
]

/**
 * 豁免（键 = 相对 src 的路径，值 = 处数 + 理由）。只放「本来就不是审计年度」的用法。
 */
const EXEMPT: Record<string, { count: number; reason: string }> = {
  'components/workpaper/composables/d4DisclosureModel.ts': {
    count: 1,
    reason: 'buildD4ObligationColumns 零参调用供披露列覆盖扫描用的示例年度；生产调用都显式传审计年度（含 null）',
  },
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (SOURCE_EXT.test(name) && !TEST_FILE.test(name)) out.push(full)
  }
  return out
}

export function literalYearHits(text: string): string[] {
  const hits: string[] = []
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (COMMENT_LINE.test(line)) continue
    for (const [kind, re] of PATTERNS) {
      if (re.test(line)) {
        hits.push(`${kind}: ${line.trim()}`)
        break
      }
    }
  }
  return hits
}

describe('拿不到审计年度时用写死的年份兜底：清零守卫（post-push-residual-defect-closure R2）', () => {
  const files = walk(SRC)
  const counts: Record<string, string[]> = {}
  for (const f of files) {
    const hits = literalYearHits(readFileSync(f, 'utf-8'))
    if (hits.length) counts[relative(SRC, f).split('\\').join('/')] = hits
  }

  it('扫描范围没失锚（> 1000 个源码文件）', () => {
    expect(files.length).toBeGreaterThan(1000)
  })

  it('除豁免外没有字面年份兜底', () => {
    const offenders = Object.entries(counts)
      .filter(([rel, hits]) => hits.length !== (EXEMPT[rel]?.count ?? 0))
      .map(([rel, hits]) => `${rel}：${hits.join(' ｜ ')}`)
    expect(offenders).toEqual([])
  })

  it('豁免可证伪：每条豁免仍命中、处数一致、写明理由', () => {
    const stale = Object.entries(EXEMPT)
      .filter(([rel, e]) => (counts[rel]?.length ?? 0) !== e.count || !e.reason.trim())
      .map(([rel]) => rel)
    expect(stale).toEqual([])
  })

  it('判据能抓到三种写法（防空转），注释与非年度数字不算', () => {
    expect(literalYearHits('    const yr = props.year || 2025')).toHaveLength(1)
    expect(literalYearHits("  :year=\"selectedYear ?? year ?? 2025\"")).toHaveLength(1)
    expect(literalYearHits('export async function f(projectId: string, year = 2025) {')).toHaveLength(1)
    expect(literalYearHits('export function g(auditYear: number | null = 2025) {')).toHaveLength(1)
    expect(literalYearHits('const year = ref(2025)')).toHaveLength(1)
    expect(literalYearHits('const year = ref<number>(2024)')).toHaveLength(1)
    expect(literalYearHits('  // 原先 `props.year || 2025`：没传年度的页面一律按 2025 年度算进度')).toHaveLength(0)
    expect(literalYearHits("const label = name || '2025-12-31'")).toHaveLength(0)
    expect(literalYearHits('const n = amount || 2000')).toHaveLength(0)
    expect(literalYearHits('const max = 2030')).toHaveLength(0)
  })
})
