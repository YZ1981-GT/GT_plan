/**
 * useGroupTree — 集团架构树形渲染/搜索/筛选 composable
 *
 * 设计原则：树形结构由后端 `GET /api/projects/tree` 动态构建（不缓存死结构），
 * 前端 composable 只负责拉取、渲染、搜索、筛选与视图状态管理，**不重复 build 树**。
 *
 * 后端 `to_dict_v2` 输出 camelCase 字段，本文件 TS 接口与之严格对齐。
 *
 * 用法：
 * ```ts
 * const { trees, independents, loading, error, fetchTree,
 *         searchQuery, filterNode, viewMode } = useGroupTree()
 *
 * onMounted(() => fetchTree())
 *
 * // 模板（el-tree）：
 * // <el-tree :data="tree.children" :filter-node-method="filterNode" ref="treeRef" />
 * // <el-input v-model="searchQuery" />   // watch 自动驱动 treeRef.filter()
 * ```
 *
 * Spec: group-tree-architecture, Requirements 1.1, 5.1
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { api } from '@/services/apiProxy'

// ─── 类型定义（与后端 consol_tree_service.to_dict_v2 输出对齐，camelCase）─────────

/** 树节点（后端 to_dict_v2 输出格式） */
export interface TreeNode {
  id: string // project.id
  label: string // company_name（节点显示名）
  companyCode: string // company_code
  companyName: string // client_name
  parentCompanyCode: string | null
  ultimateCompanyCode: string | null
  consolLevel: number
  status: string | null
  reportScope: string | null
  children: TreeNode[]
  // 容错/展示标记
  isDetached: boolean // parent 指向组内不存在的企业
  isIndependent: boolean // ultimate 为空
  isCycleBreak: boolean // 循环引用被打断
  hasNoCompanyCode: boolean // company_code 为空
  // Phase 2 持股/合并方式可视化（Task 14.1）——无数据时为 null（优雅降级）
  shareholding?: number | null // 持股比例（如 100.00）
  consolMethod?: string | null // 合并方式（ConsolMethod 枚举值：full/equity/proportional）
}

/** 集团树（一棵树 = 一个 ultimate_company_code 分组） */
export interface GroupTree {
  ultimateCode: string
  ultimateName: string
  rootProjectId: string | null // consolidated 根项目 ID（可能不存在）
  children: TreeNode[]
  /** 与合并范围（consol_scope）差异（Task 12 填充，可选） */
  hasScopeDiff?: boolean
}

/** 后端 `GET /api/projects/tree` 响应 */
export interface GroupTreeResponse {
  trees: GroupTree[]
  independents: TreeNode[]
}

/**
 * 前端 Project 类型（确认含三代码字段，与后端 projects 表对齐）。
 * 项目列表 API 返回的扁平项目对象——本 spec 仅依赖以下字段。
 */
export interface ProjectLike {
  id: string
  client_name?: string | null
  name?: string | null
  company_code?: string | null
  parent_company_code?: string | null
  ultimate_company_code?: string | null
  report_scope?: string | null
  status?: string | null
  audit_period_end?: string | null
  audit_year?: number | null
}

/** 视图模式：扁平列表 / 按客户 / 树形 */
export type ViewMode = 'list' | 'client' | 'tree'
export const VIEW_MODE_KEY = 'gt-project-view-mode'

const TREE_ENDPOINT = '/api/projects/tree'

// ─── 纯函数工具（导出供测试 + filter-node-method 复用）──────────────────────────

/**
 * 判断单个节点是否自身匹配搜索串（企业名称或企业代码，大小写不敏感）。
 * query 为空时视为匹配（不过滤）。
 */
export function nodeSelfMatches(node: Pick<TreeNode, 'companyName' | 'companyCode' | 'label'>, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const name = (node.companyName || node.label || '').toLowerCase()
  const code = (node.companyCode || '').toLowerCase()
  return name.includes(q) || code.includes(q)
}

/**
 * 判断节点（含其后代）是否应在搜索结果中可见。
 *
 * Property 9（搜索过滤正确性）：节点可见 iff 自身或任一后代的
 * companyName/companyCode 含搜索串（大小写不敏感）。query 为空 → 全部可见。
 */
export function nodeMatchesQuery(node: TreeNode, query: string): boolean {
  const q = query.trim()
  if (!q) return true
  if (nodeSelfMatches(node, q)) return true
  return (node.children || []).some((c) => nodeMatchesQuery(c, q))
}

/** 高亮分段：一段文本中匹配/非匹配子串的有序切片 */
export interface HighlightSegment {
  text: string
  /** true = 命中搜索串需高亮 */
  match: boolean
}

/**
 * 将文本按搜索串（大小写不敏感）切分为高亮分段，供 node label 渲染高亮使用。
 *
 * Property（搜索高亮，Requirements 5.3）：
 * - query 为空或 text 为空 → 返回单个非高亮分段（原文）
 * - 无匹配 → 返回单个非高亮分段（原文）
 * - 有匹配 → 命中子串 match=true，其余 match=false，按出现顺序拼接后等于原文
 *
 * 大小写不敏感匹配，但分段文本保留原始大小写。
 */
export function highlightSegments(text: string | null | undefined, query: string): HighlightSegment[] {
  const src = text ?? ''
  const q = (query || '').trim()
  if (!q || !src) return [{ text: src, match: false }]

  const lowerSrc = src.toLowerCase()
  const lowerQ = q.toLowerCase()
  const segments: HighlightSegment[] = []
  let cursor = 0

  while (cursor < src.length) {
    const idx = lowerSrc.indexOf(lowerQ, cursor)
    if (idx === -1) {
      segments.push({ text: src.slice(cursor), match: false })
      break
    }
    if (idx > cursor) segments.push({ text: src.slice(cursor, idx), match: false })
    segments.push({ text: src.slice(idx, idx + q.length), match: true })
    cursor = idx + q.length
  }

  // q 恰好在末尾结束时 cursor === src.length，无需补尾
  return segments.length > 0 ? segments : [{ text: src, match: false }]
}

/** 统计森林 + 独立节点总数（递归） */
function countNodes(nodes: TreeNode[]): number {
  let n = 0
  for (const node of nodes) {
    n += 1 + countNodes(node.children || [])
  }
  return n
}

// ─── Phase 2 持股/合并方式展示（Task 14.1 / 14.2）──────────────────────────────

/**
 * 合并方式枚举值 → 中文标签（与后端 ConsolMethod 枚举对齐：full/equity/proportional）。
 * 未知值原样返回，空值返回空串（不渲染 tag）。
 */
export function consolMethodLabel(method: string | null | undefined): string {
  if (!method) return ''
  return (
    ({
      full: '完全合并',
      equity: '权益法',
      proportional: '比例合并',
    } as Record<string, string>)[method] || method
  )
}

/**
 * 持股比例格式化为带百分号文本（如 100 → "100%"，66.67 → "66.67%"）。
 * 整数去掉小数尾零，空值返回空串（不渲染 badge）。
 */
export function formatShareholding(pct: number | null | undefined): string {
  if (pct == null || Number.isNaN(pct)) return ''
  // 去掉无意义的小数尾零：100.00 → 100，66.70 → 66.7
  const rounded = Math.round(pct * 100) / 100
  return `${rounded}%`
}

/** 合并方式统计计数（用于根节点统计信息增强，Task 14.2） */
export interface ConsolMethodCounts {
  full: number
  equity: number
  proportional: number
  total: number // 有 consolMethod 数据的节点总数
}

/**
 * 递归统计一组节点（含后代）的合并方式分布。
 * 仅统计 consolMethod 非空的节点；无任何数据时各项为 0。
 */
export function countConsolMethods(nodes: TreeNode[]): ConsolMethodCounts {
  const counts: ConsolMethodCounts = { full: 0, equity: 0, proportional: 0, total: 0 }
  const walk = (list: TreeNode[]) => {
    for (const node of list) {
      const m = node.consolMethod
      if (m) {
        counts.total += 1
        if (m === 'full') counts.full += 1
        else if (m === 'equity') counts.equity += 1
        else if (m === 'proportional') counts.proportional += 1
      }
      walk(node.children || [])
    }
  }
  walk(nodes)
  return counts
}

// ─── composable ────────────────────────────────────────────────────────────

export function useGroupTree(year?: Ref<number | null>) {
  const trees = ref<GroupTree[]>([])
  const independents = ref<TreeNode[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const searchQuery = ref('')

  // 视图模式（持久化到 localStorage）
  const savedMode =
    (typeof localStorage !== 'undefined'
      ? (localStorage.getItem(VIEW_MODE_KEY) as ViewMode | null)
      : null) || 'list'
  const viewMode = ref<ViewMode>(savedMode)
  watch(viewMode, (v) => {
    try {
      localStorage.setItem(VIEW_MODE_KEY, v)
    } catch {
      /* localStorage 不可用（隐私模式等）静默忽略 */
    }
  })

  /** 是否有任何可展示的集团树节点 */
  const hasTrees: ComputedRef<boolean> = computed(() => trees.value.length > 0)

  /** 森林中节点总数（不含独立节点） */
  const totalTreeNodes: ComputedRef<number> = computed(() =>
    trees.value.reduce((acc, t) => acc + countNodes(t.children || []), 0),
  )

  /** 搜索是否命中任何节点（用于"未找到匹配企业"空状态） */
  const hasSearchMatch: ComputedRef<boolean> = computed(() => {
    const q = searchQuery.value.trim()
    if (!q) return true
    const inTrees = trees.value.some((t) => (t.children || []).some((n) => nodeMatchesQuery(n, q)))
    const inIndep = independents.value.some((n) => nodeMatchesQuery(n, q))
    return inTrees || inIndep
  })

  /**
   * 从后端拉取已构建好的树形 JSON。
   *
   * @param scope report_scope 过滤（'consolidated' | 'all'），不传则默认 'all'
   */
  async function fetchTree(scope: 'consolidated' | 'all' = 'all'): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, string | number> = {}
      const y = year?.value
      if (y != null) params.year = y
      if (scope && scope !== 'all') params.scope = scope

      const data = await api.get<GroupTreeResponse>(TREE_ENDPOINT, { params })
      trees.value = Array.isArray(data?.trees) ? data.trees : []
      independents.value = Array.isArray(data?.independents) ? data.independents : []
    } catch (e: any) {
      error.value = e?.message || '加载集团架构树失败'
      trees.value = []
      independents.value = []
    } finally {
      loading.value = false
    }
  }

  /**
   * el-tree filter-node-method 适配：node 数据对象 + 当前过滤值 → 是否显示。
   * el-tree 会对每个节点调用；返回 true 显示。匹配节点的祖先由 el-tree 自动展开。
   */
  function filterNode(value: string, data: TreeNode): boolean {
    return nodeMatchesQuery(data, value || '')
  }

  /**
   * 设置搜索关键词（驱动 el-tree filter）。组件 watch searchQuery 后调用
   * treeRef.filter(searchQuery)。也可直接 v-model 绑定 searchQuery。
   */
  function filterTree(query: string): void {
    searchQuery.value = query
  }

  /** 清空搜索，恢复默认展开/折叠状态 */
  function clearFilter(): void {
    searchQuery.value = ''
  }

  return {
    // 状态
    trees,
    independents,
    loading,
    error,
    searchQuery,
    viewMode,
    // 计算属性
    hasTrees,
    totalTreeNodes,
    hasSearchMatch,
    // 方法
    fetchTree,
    filterNode,
    filterTree,
    clearFilter,
  }
}

export default useGroupTree
