/**
 * useWorkpaperListContext — 底稿列表 Shell 共享上下文契约（types + InjectionKey + mock helper）
 *
 * 契约层：仅定义 InjectionKey / TS interfaces / createMockContext()，不实现 reactive state。
 * Shell 通过 provide(WP_LIST_CONTEXT_KEY, ctx) 注入；子 SFC 通过 inject 读取（只读约定）。
 * 写操作走子 SFC emit('mutate', payload) 由 Shell 统一调 service（详见 design §2.3）。
 *
 * @see .kiro/specs/workpaper-list-shrink/design.md §3.1
 * Requirements: 3.1, 3.2, 3.3, 3.4
 */
import { ref, computed, type InjectionKey, type Ref, type ComputedRef } from 'vue'
import type { WpIndexItem, WorkpaperDetail } from '@/services/workpaperApi'
import type { ViewPresetId } from '@/composables/viewPresetConfig'

// ─── 共用基础类型（与 Shell / 子 SFC / 测试一致） ────────────────────────────

/** 树节点：与 WorkpaperList.vue 现有内联定义保持同形 */
export interface TreeNode {
  id: string
  label: string
  status?: string
  assigned_to?: string | null
  wpId?: string
  children?: TreeNode[]
}

/** 进度计算结果（totalProgress / filteredProgress 共用） */
export interface ProgressInfo {
  total: number
  completed: number
  percent: number
}

/** WpListItem 是 WorkpaperDetail 的别名（保持 design.md 命名约定，便于子 SFC 引用） */
export type WpListItem = WorkpaperDetail

/** RolePreset 是 ViewPresetId 别名（'assistant' | 'manager' | 'partner' | 'qc'） */
export type RolePreset = ViewPresetId

// ─── 共享 reactive state（Shell provide → 子 SFC inject） ────────────────────

/**
 * Shell 通过 useWorkpaperListContext() 暴露的响应式数据
 * （注意：provide 的是 Ref/ComputedRef 本身，不是 .value，子 SFC 通过 .value 读取保持响应式）
 */
export interface WpListContextData {
  // ── 核心数据 ──
  wpIndex: Ref<WpIndexItem[]>
  wpList: Ref<WpListItem[]>
  treeData: Ref<TreeNode[]>
  loading: Ref<boolean>
  projectId: ComputedRef<string>
  currentYear: ComputedRef<number>
  projectName: Ref<string>
  viewMode: Ref<string>

  // ── 筛选 ──
  searchKeyword: Ref<string>
  filterCycle: Ref<string>
  filterStatus: Ref<string>
  filterAssignee: Ref<string>
  /** 'active' = 仅活跃 / 'all' = 含已裁剪 */
  showTrimmedFilter: ComputedRef<'active' | 'all'>

  // ── 选中 ──
  selectedWpId: Ref<string>

  // ── 进度 ──
  totalProgress: ComputedRef<ProgressInfo>

  // ── 角色视图 ──
  roleViewPreset: ComputedRef<RolePreset>
  roleViewWpList: ComputedRef<WpListItem[]>
}

/** Shell 暴露的 actions（写操作在 Shell 内部统一调 service） */
export interface WpListContextActions {
  /** 重新拉取 wpIndex / wpList / treeData，进入路由或外部刷新触发 */
  fetchWpIndex: () => Promise<void>
  /** 子 SFC emit('mutate', ...) 后 Shell 调 service 成功后的统一刷新入口 */
  refreshAfterMutate: () => Promise<void>
}

/** Shell 注入的完整 context */
export type WpListContext = WpListContextData & WpListContextActions

/** Vue InjectionKey（Symbol，避免字符串 key 冲突） */
export const WP_LIST_CONTEXT_KEY: InjectionKey<WpListContext> = Symbol('WpListContext')

// ─── 子 SFC 对外契约 ────────────────────────────────────────────────────────

/** 5 子 SFC 共用 props 接口（projectId/year 显式声明，禁止子 SFC 直调 useRoute） */
export interface WpChildProps {
  projectId: string
  year: number
}

/** 子 SFC mutate 事件 payload（统一 action + data 形式，Shell 路由到对应 service） */
export interface MutatePayload {
  action: 'updateStatus' | 'assign' | 'batchAssign' | 'delegate' | 'reorder'
  data: Record<string, unknown>
}

/** 5 子 SFC 共用 emits 接口 */
export interface WpChildEmits {
  (e: 'navigate', wpId: string): void
  (e: 'refresh'): void
  (e: 'mutate', payload: MutatePayload): void
}

// ─── 测试 helper ────────────────────────────────────────────────────────────

/**
 * createMockContext — vitest 中通过 `provide(WP_LIST_CONTEXT_KEY, createMockContext())` 独立 mount 子 SFC
 *
 * 默认返回空数据 + 无副作用 actions；overrides 用于按需替换部分字段（保持其余默认）。
 *
 * @example
 *   const ctx = createMockContext({ loading: ref(true) })
 *   wrapper = mount(WorkpaperBoardView, {
 *     global: { provide: { [WP_LIST_CONTEXT_KEY as symbol]: ctx } },
 *     props: { projectId: 'p1', year: 2024 },
 *   })
 */
export function createMockContext(overrides: Partial<WpListContext> = {}): WpListContext {
  const empty: WpListContext = {
    wpIndex: ref<WpIndexItem[]>([]),
    wpList: ref<WpListItem[]>([]),
    treeData: ref<TreeNode[]>([]),
    loading: ref(false),
    projectId: computed(() => ''),
    currentYear: computed(() => new Date().getFullYear() - 1),
    projectName: ref(''),
    viewMode: ref('workbench'),
    searchKeyword: ref(''),
    filterCycle: ref(''),
    filterStatus: ref(''),
    filterAssignee: ref(''),
    showTrimmedFilter: computed<'active' | 'all'>(() => 'active'),
    selectedWpId: ref(''),
    totalProgress: computed<ProgressInfo>(() => ({ total: 0, completed: 0, percent: 0 })),
    roleViewPreset: computed<RolePreset>(() => 'assistant'),
    roleViewWpList: computed<WpListItem[]>(() => []),
    fetchWpIndex: async () => { /* noop */ },
    refreshAfterMutate: async () => { /* noop */ },
  }
  return { ...empty, ...overrides }
}
