/**
 * 信息栏切年度必须写路由 `?year=`（spec platform-performance-residual-findings-closure 验收期发现）。
 *
 * 这几个页面的取数年度是「路由 ?year → 项目审计年度」：`onYearChange` 只改 store、原地重取时，选择器显示新年度，
 * 数据仍按旧年度取（2026-10-31 浏览器实测报表页：选 2024 后仍请求 /api/reports/…/2025/…）。写路由后 `?year`
 * 变化整页重挂（routeViewKey）并按新年度取数 —— 试算表 / 调整分录 / 查账一直这么做，报表页漏了。
 * 另：报表页带 `?year=` 打开时选择器停在「请选择」（路由给了年度就提前 return、没同步选择器）；报表页整页重挂后页签
 * 按 `?tab` 恢复，切年度须带上当前页签。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const VIEWS = resolve(__dirname, '..')

function functionBody(src: string, name: string): string | null {
  const m = new RegExp(`^(?:async )?function ${name}\\([^)]*\\)[^{]*\\{`, 'm').exec(src)
  if (!m) return null
  let depth = 1
  let i = m.index + m[0].length
  while (depth > 0 && i < src.length) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') depth -= 1
    i += 1
  }
  return src.slice(m.index, i)
}

/** 取数年度以路由优先的页面（`routeYear.value ??` 或直接读 `route.query.year`） */
const ROUTE_FIRST = ['ReportView.vue', 'TrialBalance.vue', 'Adjustments.vue', 'LedgerPenetration.vue', 'DisclosureEditor.vue']

/** 只许删：仍只改 store 的页面（路由带 ?year= 时切年度不生效）。DisclosureEditor 已于 R10 修好删除，现为空、不得回填。 */
const KNOWN_GAPS: Record<string, string> = {}

// path 里常有 `${projectId.value}` 这类花括号 ⇒ 不按 `[^}]` 截，限定在调用起点后 200 字符内出现 year
const writesRouteYear = (body: string) => /router\.(push|replace)\([\s\S]{0,200}?\byear\b/.test(body)

describe('切年度写路由 ?year=', () => {
  it.each(ROUTE_FIRST.filter((f) => !(f in KNOWN_GAPS)))('%s 的 onYearChange 写路由年度', (file) => {
    const src = readFileSync(resolve(VIEWS, file), 'utf8')
    expect(/routeYear\.value\s*\?\?|route\.query\.year/.test(src), `${file} 不是路由优先的年度`).toBe(true)
    const body = functionBody(src, 'onYearChange')
    expect(body, `${file} 没有 onYearChange`).toBeTruthy()
    expect(writesRouteYear(body!)).toBe(true)
  })

  it('登记缺口已清空、不得回填', () => {
    expect(Object.keys(KNOWN_GAPS)).toEqual([])
  })

  describe('附注编辑页（R10）', () => {
    const src = readFileSync(resolve(VIEWS, 'DisclosureEditor.vue'), 'utf8')
    const body = functionBody(src, 'onYearChange') ?? ''
    const at = (needle: string) => body.indexOf(needle)

    it('先拦未保存改动（留下则选择器回到当前年度），再改 store，最后写路由', () => {
      expect(body).toMatch(/if \(!\(await guardUnsaved\(\)\)\) \{ selectedYear\.value = year\.value; return \}/)
      expect(at('guardUnsaved()')).toBeGreaterThan(-1)
      expect(at('guardUnsaved()')).toBeLessThan(at('projectStore.changeYear('))
      expect(at('projectStore.changeYear(')).toBeLessThan(at('router.push('))
    })

    it('只带年度（不展开 route.query：section 等一次性参数已用 replaceState 清掉，vue-router 里还在）', () => {
      expect(body).toMatch(/router\.push\(\{ path: route\.path, query: \{ year: String\(y\) \} \}\)/)
      expect(body).not.toMatch(/\.\.\.route\.query/)
    })

    it('切年度不再自己取树 / 生成；「没有附注就自动生成」在挂载流程里（仅可写时）', () => {
      expect(body).not.toMatch(/fetchTree\(|onGenerate\(/)
      const mounted = /onMounted\(async \(\) => \{([\s\S]*?)\n\}\)/.exec(src)?.[1] ?? ''
      expect(mounted).toMatch(/await fetchTree\(\)\s*\n\s*await noteEdit\.ready\(\)[^\n]*\n\s*if \(noteList\.value\.length === 0 && noteEdit\.canWrite\.value\) \{\s*\n\s*await onGenerate\(\)/)
    })

    it('未保存拦截同时挂在离开与更新上（换项目 / 改 query 整页重挂，离开守卫不触发）', () => {
      expect(src).toMatch(/onBeforeRouteLeave\(\(\) => guardUnsaved\(\)\)/)
      expect(src).toMatch(/onBeforeRouteUpdate\(\(\) => guardUnsaved\(\)\)/)
      const guard = functionBody(src, 'guardUnsaved') ?? ''
      expect(guard).toMatch(/editDirty\.value && !autoSave\.isDirty\.value/)
      expect(guard).toMatch(/confirmLeave\('附注'\)/)
    })
  })

  it('报表页：路由带年度时选择器同步为路由年度（原先停在「请选择」）', () => {
    const body = functionBody(readFileSync(resolve(VIEWS, 'ReportView.vue'), 'utf8'), '_ensureProjectYearWrapper')
    expect(body).toBeTruthy()
    const routeBranch = /if \(routeYear\.value !== null\) \{([\s\S]*?)return\s*\}/.exec(body!)?.[1] ?? ''
    expect(routeBranch).toMatch(/selectedYear\.value\s*=\s*routeYear\.value/)
  })

  it('报表页：切年度带上当前页签（重挂后页签按 ?tab 恢复；不带则回到资产负债表）', () => {
    const body = functionBody(readFileSync(resolve(VIEWS, 'ReportView.vue'), 'utf8'), 'onYearChange')
    expect(body).toMatch(/router\.push\(\{[\s\S]*?query:\s*\{[^}]*\btab:\s*activeTab\.value/)
    // 重挂后的初始页签读的正是 ?tab（useReportRouteFocus）
    const focus = readFileSync(resolve(VIEWS, '..', 'composables', 'useReportRouteFocus.ts'), 'utf8')
    expect(focus).toMatch(/first\(route\.query\.tab\)/)
  })

  it('反向自检：只改 store、原地重取的写法判为未写路由', () => {
    expect(writesRouteYear('function onYearChange(val) {\n  selectedYear.value = val\n  projectStore.changeYear(val)\n  fetchReport()\n}')).toBe(false)
    expect(writesRouteYear("function onYearChange(y) { router.push({ path: route.path, query: { year: String(y) } }) }")).toBe(true)
    // functionBody 认 async 函数（附注页 onYearChange 是 async）
    expect(functionBody('async function onYearChange(y: number) {\n  router.push({})\n}\nfunction other() {}', 'onYearChange'))
      .toBe('async function onYearChange(y: number) {\n  router.push({})\n}')
  })
})
