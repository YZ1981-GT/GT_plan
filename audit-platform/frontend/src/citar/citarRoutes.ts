/**
 * CITAR 版式覆盖的路由（单一来源）。
 *
 * DefaultLayout 按 citarLayoutMode 决定渲染 CitarLayout 还是原三栏布局；
 * CitarLayout 的一级栏也从这里读。增删菜单只改本文件。
 */
import type { InjectionKey, Ref } from 'vue'

/** 项目内一级栏菜单项 */
export interface CitarNavItem {
  key: string
  label: string
  /** 拼在 /projects/:projectId/ 之后的路径段 */
  segment: string
  /** Element Plus 图标组件名（CitarLayout 内按名取组件） */
  icon: string
}

/** 菜单分组（按用户 2026-11-02 给的分组图） */
export interface CitarNavGroup {
  title: string
  items: CitarNavItem[]
}

export const CITAR_NAV_GROUPS: CitarNavGroup[] = [
  {
    title: '数据导入与账务查询',
    items: [
      { key: 'import', label: '数据导入', segment: 'ledger-import', icon: 'Upload' },
      { key: 'ledger-query', label: '账务查询', segment: 'ledger-query', icon: 'Search' },
    ],
  },
  {
    title: '试算平衡与报表',
    items: [
      { key: 'trial-balance', label: '试算平衡表', segment: 'trial-balance', icon: 'Grid' },
      { key: 'adjustments', label: '调整分录', segment: 'adjustments', icon: 'EditPen' },
      { key: 'reports', label: '审定报表', segment: 'reports', icon: 'Tickets' },
      { key: 'report-analysis', label: '报表分析', segment: 'report-analysis', icon: 'DocumentChecked' },
    ],
  },
  {
    title: '税审底稿',
    items: [
      { key: 'mapping', label: '底稿映射', segment: 'mapping', icon: 'Connection' },
      { key: 'workpapers', label: '税审底稿', segment: 'workpapers', icon: 'Notebook' },
    ],
  },
  {
    // 用户 2026-11-03：鉴证报告分为报告正文、审核说明、汇算申报表、单体财务报表四个菜单（spec citar-assurance-report-menus）
    title: '鉴证报告',
    items: [
      { key: 'report-body', label: '报告正文', segment: 'report-body', icon: 'DocumentChecked' },
      { key: 'review-notes', label: '审核说明', segment: 'review-notes', icon: 'Notebook' },
      { key: 'tax-return', label: '汇算申报表', segment: 'tax-return', icon: 'Document' },
      { key: 'financial-statements', label: '单体财务报表', segment: 'financial-statements', icon: 'Tickets' },
    ],
  },
]

/** 扁平菜单（项目空页的流程提示等用） */
export const CITAR_NAV: CitarNavItem[] = CITAR_NAV_GROUPS.flatMap(g => g.items)

/** 税务底稿：点它展开 / 收起二级栏「底稿目录」 */
export const CITAR_WORKPAPER_SEGMENT = 'workpapers'

/** 项目空页（从项目列表点进来先到这里） */
export const CITAR_HOME_SEGMENT = 'home'

/** 页面自带目录栏、内容区不留内边距的菜单段（税务底稿、汇算申报表） */
export const CITAR_FLUSH_SEGMENTS: ReadonlySet<string> = new Set([CITAR_WORKPAPER_SEGMENT, 'tax-return'])

const PROJECT_SEGMENTS = new Set([CITAR_HOME_SEGMENT, ...CITAR_NAV.map(n => n.segment)])

/**
 * - list：项目列表（页面自带顶栏）
 * - create：新建 / 修改项目（只有 CITAR 顶栏）
 * - project：项目内（顶栏 + 项目信息行 + 一级栏）
 * - null：不归 CITAR 版式管，走原三栏布局
 */
export type CitarLayoutMode = 'list' | 'create' | 'project' | null

export function citarLayoutMode(path: string): CitarLayoutMode {
  const p = path.replace(/\/+$/, '') || '/'
  if (p === '/projects') return 'list'
  if (p === '/projects/new') return 'create'
  const m = /^\/projects\/[^/]+\/([^/]+)$/.exec(p)
  if (m && PROJECT_SEGMENTS.has(m[1])) return 'project'
  return null
}

/** 当前路径所在的一级菜单段（项目空页返回 home） */
export function citarSegment(path: string): string | null {
  const m = /^\/projects\/[^/]+\/([^/]+)\/?$/.exec(path)
  return m ? m[1] : null
}

/** 税务底稿二级栏是否展开（CitarLayout 提供，TaxWorkpaperView 读取） */
export const CITAR_SUBNAV_OPEN_KEY: InjectionKey<Ref<boolean>> = Symbol('citar-subnav-open')

/** 当前项目详情（CitarLayout 读一次后提供，各页取编制单位等，避免重复请求） */
export const CITAR_PROJECT_KEY: InjectionKey<Ref<Record<string, any> | null>> = Symbol('citar-project')
