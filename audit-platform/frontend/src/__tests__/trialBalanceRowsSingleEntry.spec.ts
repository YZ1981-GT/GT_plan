/**
 * 试算表列表端点只许经唯一入口取数（spec post-push-residual-defect-closure R1，设计 §2.4）。
 *
 * `GET /api/projects/{id}/trial-balance` 原先 84 处各自直连：37 处不带 year（端点当时必填 ⇒ 422 被吞成「待取数」），
 * 20 多种读法读的是端点不返回的字段（debit_amount / ending_balance / prior_* …）⇒ 带上年度也静默得 0；
 * 另有 6 处请求后端没有的 `/api/trial-balance` 根路径（404 被 validateStatus 放行或被 catch 吞掉 ⇒ 恒空）：
 * 3 处不带子路径；收紧口径后又抓到 G6 审定表与 E0 账面金额的 `/api/trial-balance/query`、附注公式弹窗的 `/api/trial-balance/`。
 * 现在一律经 `services/trialBalanceRows.ts`（行字段与后端逐键一致：`backend/tests/test_trial_balance_row_contract.py`）。
 *
 * 口径：src 下非测试源码（.ts / .vue；跳过 __tests__ / test / tests 目录与 *.spec / *.test / *.stories），
 * 整行注释（`//`、`/*`、`*`、`<!--` 开头）不计。命中任一写法即违规：
 * 1. 字面量 / 模板串 `/api/projects/<…>/trial-balance` 后接引号或 `?`（子路径 /recalc 等不算）；
 * 2. 拼接 `'/api/projects/' + id + '/trial-balance'`；
 * 3. 不存在的根路径 `/api/trial-balance` 后接引号或 `?`，以及它下面不以 `${…}` 开头的子路径（`/`、`/query` 等）——
 *    该前缀下后端只有 `/api/trial-balance/{project_id}/{year}/sync-from-workpaper`；
 * 4. 路径常量 `trialBalance.get(` 及其导入别名（`trialBalance as X` 之后的 `X.get(`）。
 * 允许：入口本身、路径常量定义处。页面导航（`/projects/<…>/trial-balance`，不带 /api）不受影响。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '..')
const ENTRY = 'services/trialBalanceRows.ts'
const ALLOWED = new Set([ENTRY, 'services/apiPaths/accounting.ts'])
const SOURCE_EXT = /\.(?:ts|vue)$/
const TEST_FILE = /\.(?:spec|test|stories)\.ts$/
const SKIP_DIRS = new Set(['__tests__', 'test', 'tests', 'node_modules'])
const COMMENT_LINE = /^\s*(?:\/\/|\/\*|\*|<!--)/
/** `${ … }` 插值或任意非空白、非引号字符 */
const URL_CHARS = String.raw`(?:\$\{[^}]*\}|[^\s'"\x60])*?`
const RULES: ReadonlyArray<{ name: string; re: RegExp }> = [
  { name: '直连列表端点', re: new RegExp(String.raw`/api/projects/${URL_CHARS}/trial-balance(?=[\x60'"?])`, 'g') },
  { name: '拼接列表端点', re: /\/api\/projects\/['"`]\s*\+[^;\n]*?['"`]\/trial-balance(?=[`'"?])/g },
  { name: '不存在的根路径', re: /['"`]\/api\/trial-balance(?:\/(?!\$\{)[^\s'"`?]*)?(?=[`'"?])/g },
  { name: '路径常量取列表', re: /\btrialBalance\s*\.\s*get\s*\(/g },
]

/** 返回违规写法名（每处一条）。注释行先剔除，导入别名按 `trialBalance as X` 收集。 */
function findTrialBalanceListFetches(text: string): string[] {
  const code = text
    .split('\n')
    .filter((line) => !COMMENT_LINE.test(line))
    .join('\n')
  const hits: string[] = []
  for (const { name, re } of RULES) {
    for (const _ of code.matchAll(re)) hits.push(name)
  }
  for (const m of code.matchAll(/\btrialBalance\s+as\s+(\w+)/g)) {
    const alias = new RegExp(String.raw`\b${m[1]}\s*\.\s*get\s*\(`, 'g')
    for (const _ of code.matchAll(alias)) hits.push('路径常量别名取列表')
  }
  return hits
}

function isScannedFile(name: string): boolean {
  return SOURCE_EXT.test(name) && !TEST_FILE.test(name)
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (isScannedFile(name)) out.push(full)
  }
  return out
}

const HITS = [
  'const r = await api.get(`/api/projects/${pid}/trial-balance`, { params: { year } })',
  'await http.get(`/api/projects/${ props.projectId }/trial-balance`)',
  'const res: any = await api.get(`/api/projects/${props.projectId}/trial-balance?year=${y}&account_prefix=1621`)',
  "const url = '/api/projects/' + pid + '/trial-balance'",
  "await api.get('/api/trial-balance', { params: { project_id: pid } })",
  "const res = await api.get('/api/trial-balance/query', { params: { project_id: pid, account_code: '1506' } })",
  'api.get(`/api/trial-balance/`, { params: { project_id: pid, year } })',
  'await api.get(P.trialBalance.get(pid), { params: { year } })',
  'const resp = await import(\'@/utils/http\').then(m => m.default.get(\n  `/api/projects/${props.projectId}/trial-balance`,\n))',
]
const MISSES = [
  'router.push(`/projects/${pid}/trial-balance`)',
  'await http.post(`/api/projects/${pid}/trial-balance/recalc`, null, { params: { year } })',
  'await http.get(P_tb.consistencyCheck(projectId), { params: { year } })',
  'await http.post(`/api/trial-balance/${pid}/${year}/sync-from-workpaper`)',
  "eventBus.on('trial-balance:updated', onTbUpdated)",
  "const p = '/api/consolidation/worksheet/drill/trial-balance'",
  '// 原先 api.get(`/api/projects/${pid}/trial-balance`)',
  ' * 端点 `GET /api/projects/{id}/trial-balance`',
  '<!-- /api/trial-balance -->',
]

describe('试算表列表端点只许经唯一入口取数（post-push-residual-defect-closure R1）', () => {
  it('识别口径没失锚：九种违规写法各命中一次，导航 / 子路径 / 事件名 / 注释不命中', () => {
    expect(HITS.map((s) => findTrialBalanceListFetches(s).length)).toEqual(HITS.map(() => 1))
    expect(MISSES.map((s) => findTrialBalanceListFetches(s))).toEqual(MISSES.map(() => []))
    // 路径常量的导入别名（auditPlatformApi 里有 `trialBalance as P_tb`）：取 .get 才违规
    const aliased = "import { trialBalance as P_tb } from '@/services/apiPaths'\n"
    expect(findTrialBalanceListFetches(`${aliased}await http.get(P_tb.get(id))`)).toEqual(['路径常量别名取列表'])
    expect(findTrialBalanceListFetches(`${aliased}await http.post(P_tb.recalc(id))`)).toEqual([])
  })

  const files = walk(SRC)

  it('扫描范围没失锚：扫到全前端源码，入口本身命中（证明口径对真实代码有效）', () => {
    expect(files.length).toBeGreaterThan(3000)
    expect(['A.vue', 'b.ts', 'c.spec.ts', 'd.test.ts', 'e.stories.ts', 'f.md'].filter(isScannedFile)).toEqual(['A.vue', 'b.ts'])
    expect(findTrialBalanceListFetches(readFileSync(join(SRC, ENTRY), 'utf-8')).length).toBeGreaterThan(0)
  })

  it('入口之外没有任何直连（新代码请用 fetchTrialBalanceRows 与 tbSumUnder / tbOccurrence 等）', () => {
    const offenders: string[] = []
    for (const file of files) {
      const rel = relative(SRC, file).split('\\').join('/')
      if (ALLOWED.has(rel)) continue
      const hits = findTrialBalanceListFetches(readFileSync(file, 'utf-8'))
      if (hits.length) offenders.push(`${rel}：${hits.join('、')}`)
    }
    expect(offenders, '试算表行请经 services/trialBalanceRows.ts 取（年度 / 前缀 / 发生额 / 上年数都有开关）').toEqual([])
  })
})
