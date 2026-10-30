/**
 * queryIndicatorLoader.ts — 指标树加载（advanced-query-linkage-closure 任务 28 / 29，ADR-AQL-16；R10.4，AQ-31 前端）
 *
 * 弹窗与页面版共用：都带项目与审计年度请求（附注分支按该项目该年度的章节生成），都经 `queryIndicatorCache` 缓存，键含
 * schema（`X-Indicators-Schema-Version`）与附注版本（`X-Notes-Version`）——附注重新生成 / 对齐或切换年度后不再读旧树。
 * 先发 depth=1 骨架拿两个版本头再查缓存，命中即不拉全量。
 * - `full`（弹窗）：全量树（含逐底稿 / 逐 sheet 叶子，供底稿选区器）。
 * - `page`（页面版）：骨架 + 附注分支（`branch=disclosure`），不拉不带项目的全量树（原先页面版每次都拉约 578 KB）；
 *   底稿组只有「底稿清单」叶子（后端骨架自带），sheet 级查询仍从弹窗发起。
 * 两种树形缓存键不同（`variant`），互不命中。请求失败原样抛出，由调用方决定兜底。
 */
import http from '@/utils/http'
import { customQuery as P_cq } from '@/services/apiPaths'
import { isKnownYear } from '@/components/custom-query/queryPayloads'
import { indicatorCacheKey, readIndicatorCache, writeIndicatorCache } from './queryIndicatorCache'

export interface IndicatorNode {
  key: string
  label: string
  icon?: string
  children?: IndicatorNode[]
  columns?: string[] | null
  supports_conditions?: boolean
  disabled?: boolean
  lazy?: boolean
  [extra: string]: unknown
}

export type IndicatorTreeShape = 'full' | 'page'

export interface LoadIndicatorOptions {
  projectId?: string | null
  year?: number | null
  shape: IndicatorTreeShape
}

const SCHEMA_HEADER = 'x-indicators-schema-version'
const NOTES_HEADER = 'x-notes-version'
/** 页面版懒加载的分支（只取附注；底稿分支约 640 KB，页面版不列） */
const PAGE_BRANCH = 'disclosure'

function header(resp: { headers?: Record<string, unknown> } | undefined, name: string): string | null {
  const v = resp?.headers?.[name]
  return v === undefined || v === null || v === '' ? null : String(v)
}

/** 响应体 → 节点数组（拦截器已解包信封；兜底再解一层） */
export function treeOf(body: unknown): IndicatorNode[] {
  const tree = Array.isArray(body) ? body : (body as { data?: unknown } | null)?.data
  return Array.isArray(tree) ? (tree as IndicatorNode[]) : []
}

function baseParams(opts: LoadIndicatorOptions): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  if (opts.projectId) params.project_id = opts.projectId
  if (isKnownYear(opts.year)) params.year = opts.year
  return params
}

/** 按项目与年度加载指标树（缓存命中则不拉全量 / 分支） */
export async function loadIndicatorTree(opts: LoadIndicatorOptions): Promise<IndicatorNode[]> {
  const params = baseParams(opts)
  let probe: { data?: unknown; headers?: Record<string, unknown> } | undefined
  try {
    probe = await http.get(P_cq.indicators, { params: { ...params, depth: 1 }, _silent: true } as any)
  } catch (e) {
    if (opts.shape === 'page') throw e // 页面版的骨架就是这次请求，拿不到无从拼树
  }
  const schema = header(probe, SCHEMA_HEADER)
  const key = schema ? indicatorCacheKey({
    schema, projectId: opts.projectId, year: opts.year, notesVersion: header(probe, NOTES_HEADER),
    variant: opts.shape === 'page' ? 'page' : null,
  }) : null
  const cached = key ? readIndicatorCache<IndicatorNode[]>(key) : null
  if (cached) return cached

  let tree: IndicatorNode[]
  if (opts.shape === 'full') {
    tree = treeOf((await http.get(P_cq.indicators, { params, _silent: true } as any)).data)
  } else {
    tree = treeOf(probe?.data)
    const group = tree.find((n) => n.key === PAGE_BRANCH)
    if (group?.lazy) {
      const branch = await http.get(P_cq.indicators, { params: { ...params, branch: PAGE_BRANCH }, _silent: true } as any)
      group.children = treeOf(branch.data)
      group.lazy = false
    }
  }
  if (key) writeIndicatorCache(key, tree)
  return tree
}

/** 页面版下拉的一个选项（叶子） */
export interface IndicatorLeafOption {
  key: string
  /** 组内路径（中间层名 / 叶子名） */
  label: string
  columns: string[]
  supportsConditions: boolean
}

export interface IndicatorOptionGroup {
  key: string
  label: string
  children: IndicatorLeafOption[]
}

/** 把树拍平成「顶层组 → 叶子」两层（页面版 el-select 的分组选项）；不可选（disabled）的叶子不列 */
export function flattenIndicatorGroups(tree: readonly IndicatorNode[]): IndicatorOptionGroup[] {
  const groups: IndicatorOptionGroup[] = []
  for (const top of tree) {
    const leaves: IndicatorLeafOption[] = []
    const walk = (node: IndicatorNode, path: string[]) => {
      if (node.disabled) return
      const kids = node.children ?? []
      if (!kids.length) {
        leaves.push({
          key: node.key, label: [...path, node.label].join(' / '),
          columns: Array.isArray(node.columns) ? [...node.columns] : [],
          supportsConditions: node.supports_conditions === true,
        })
        return
      }
      for (const child of kids) walk(child, [...path, node.label])
    }
    for (const child of top.children ?? []) walk(child, [])
    if (leaves.length) groups.push({ key: top.key, label: top.label, children: leaves })
  }
  return groups
}
