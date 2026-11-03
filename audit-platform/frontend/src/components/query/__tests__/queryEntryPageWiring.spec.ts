/**
 * 四处页面接线（advanced-query-linkage-closure 任务 47，design §4.3；ADR-AQL-20，变异 #34）
 *
 * 静态守卫（SFC 模板 AST，不挂载这四个大页面）：
 * - 每页恰好挂一处 `QueryDetailEntry`，`kind` 正确、`:year` 绑的是**宿主取数用的年度**（不是只读路由 `?year`）；
 * - 页面显式 import 该组件（不依赖由构建工具重写的 `components.d.ts`）；
 * - 现有穿透 / 明细能力仍在（新入口与它们并列，不替换，R14.1）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'

const SRC = resolve(__dirname, '../../..')
const read = (rel: string) => readFileSync(resolve(SRC, rel), 'utf-8')

interface Wiring {
  file: string
  kind: string
  year: string
  target: string
  /** 同一文件里必须仍然存在的既有能力锚点（新入口不替换它们） */
  keeps: string[]
}

const PAGES: Wiring[] = [
  {
    file: 'views/TrialBalance.vue',
    kind: 'tb_row', year: 'year', target: 'tbCtx.contextMenu.rowData',
    keeps: ['onTbCtxDrillDown', '查看明细'],
  },
  {
    file: 'views/DisclosureEditor.vue',
    kind: 'note_section', year: 'year', target: 'currentNote',
    keeps: ['onDeCtxPenetrateToLedger', '穿透到序时账'],
  },
  {
    file: 'components/report/ReportDrilldownDialogs.vue',
    kind: 'report_row', year: 'drilldownData.year ?? null', target: 'drilldownData',
    keeps: ['line-comp-jump', '构成科目'],
  },
]

function elements(source: string, tag: string): any[] {
  const ast = parse(source).descriptor.template?.ast
  const out: any[] = []
  const walk = (node: any) => {
    if (node?.type === 1 && node.tag === tag) out.push(node)
    for (const child of node?.children ?? []) walk(child)
  }
  if (ast) walk(ast)
  return out
}

function attr(el: any, name: string): string {
  const stat = el.props.find((p: any) => p.type === 6 && p.name === name)
  if (stat) return String(stat.value?.content ?? '')
  const bind = el.props.find((p: any) => p.type === 7 && p.name === 'bind' && p.arg?.content === name)
  return String(bind?.exp?.content ?? '')
}

describe.each(PAGES)('$file', (page) => {
  const source = read(page.file)
  const mounts = elements(source, 'QueryDetailEntry')

  it('恰好挂一处入口，kind 与 target 按 ADR-AQL-20 的落点', () => {
    expect(mounts).toHaveLength(1)
    expect(attr(mounts[0], 'kind')).toBe(page.kind)
    expect(attr(mounts[0], 'target')).toBe(page.target)
  })

  it('年度绑宿主取数用的那个，不是只读路由 ?year（变异 #34）', () => {
    const year = attr(mounts[0], 'year')
    expect(year).toBe(page.year)
    expect(year).not.toMatch(/route\s*\.\s*query/)
  })

  it('显式 import，不依赖 components.d.ts', () => {
    expect(source).toContain("import QueryDetailEntry from '@/components/query/QueryDetailEntry.vue'")
  })

  it('现有穿透 / 明细能力仍在（并列不替换）', () => {
    for (const anchor of page.keeps) expect(source).toContain(anchor)
  })
})

describe('底稿编辑器两个工具栏（WorkpaperEditor.vue）', () => {
  const source = read('views/WorkpaperEditor.vue')
  const mounts = elements(source, 'QueryDetailEntry')

  it('两个工具栏各挂一处，kind=workpaper、年度取 projectYear', () => {
    expect(mounts).toHaveLength(2)
    for (const el of mounts) {
      expect(attr(el, 'kind')).toBe('workpaper')
      expect(attr(el, 'target')).toBe('wpDetail')
      expect(attr(el, 'year')).toBe('projectYear')
    }
  })

  it('两处都在 projectYear != null 的门控内（缺年度时页面显示 AuditYearMissingResult，入口随工具栏一起不出现）', () => {
    expect(source).toContain('projectYear != null')
    // 两个工具栏容器都带年度门控：HTML 渲染器的 gt-wp-io-toolbar 与 Univer 的 gt-wp-editor 分支
    expect(source).toMatch(/useHtmlRenderer && wpDetail && projectYear != null[\s\S]*gt-wp-io-toolbar/)
    expect(source).toMatch(/v-else-if="projectYear != null"[\s\S]*gt-wp-editor-toolbar/)
  })

  it('显式 import', () => {
    expect(source).toContain("import QueryDetailEntry from '@/components/query/QueryDetailEntry.vue'")
  })
})

describe('报表页自己不加行（ReportView 0 行，design §4.3）', () => {
  it('入口只在穿透弹窗组件里，ReportView.vue 不出现它', () => {
    expect(read('views/ReportView.vue')).not.toContain('QueryDetailEntry')
  })

  it('onDrilldown 把报表类型 / 年度 / 项目写进 drilldownData（入口的唯一年度来源）', () => {
    const source = read('views/composables/useReportDrilldown.ts')
    expect(source).toContain('report_type: activeTab.value, year: year.value, project_id: projectId.value')
    // 合计行与无行次的行根本进不来（§10.4 评审 #22）
    expect(source).toContain('if (!row.row_code || row.is_total_row) return')
  })
})
