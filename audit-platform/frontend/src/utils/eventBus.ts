/**
 * eventBus — 全局事件总线（mitt）
 *
 * 替代 CustomEvent + document/window.dispatchEvent，提供：
 * - 类型安全（Events 映射表 → IDE 自动补全）
 * - 自动清理（onUnmounted 中 off 即可，无需 removeEventListener）
 * - 零 _redispatched 补丁
 *
 * @see design.md D1
 */
import mitt from 'mitt'

// ─── 事件载荷类型 ─────────────────────────────────────────────────────────────

/** 公式保存/应用 */
export interface FormulaChangedPayload {
  action: 'saved' | 'applied'
}

/** 准则切换 */
export interface StandardChangePayload {
  standard: 'soe' | 'listed'
}

/** 四栏切换 */
export interface FourColSwitchPayload {
  tab?: string
}

/** 打开公式管理器 */
export interface OpenFormulaManagerPayload {
  nodeKey?: string
}

/** 合并树节点选择 */
export interface ConsolTreeSelectPayload {
  companyCode?: string
  label?: string
  isReport?: boolean
  reportType?: string
  isDiff?: boolean
  switchTab?: string
}

/** 四栏 catalog 选择 */
export interface ConsolCatalogSelectPayload {
  type: string
  reportType?: string
  sectionId?: string
  title?: string
  standard?: string
  label?: string
}

/** 合并主体刷新 */
export interface ConsolRefreshEntityPayload {
  companyCode: string
  companyName: string
  types: string[]
}

/** 合并树汇总 */
export interface ConsolTreeAggregatePayload {
  mode: 'direct' | 'custom'
  companyCode: string
  companyName: string
}

/** 附注全审 */
export interface ConsolNoteAuditAllPayload {
  standard: string
}

/** 模板应用（新增表样后触发地址注册表刷新） */
export interface TemplateAppliedPayload {
  configType: string
  projectId?: string
}

/** SSE 同步状态事件 */
export interface SyncEventPayload {
  event_type: string
  project_id: string
  year?: number
  account_codes?: string[]
  extra?: {
    source_event?: string
    handler?: string
    error?: string
    [key: string]: any
  }
}

// ─── 事件映射表 ───────────────────────────────────────────────────────────────

export type Events = {
  // 布局 & 公式
  'formula-changed': FormulaChangedPayload
  'standard-change': StandardChangePayload
  'four-col-switch': FourColSwitchPayload
  'open-formula-manager': OpenFormulaManagerPayload

  // 合并模块通信
  'consol-tree-select': ConsolTreeSelectPayload
  'consol-catalog-select': ConsolCatalogSelectPayload
  'consol-refresh-entity': ConsolRefreshEntityPayload
  'consol-tree-aggregate': ConsolTreeAggregatePayload
  'consol-note-audit-all': ConsolNoteAuditAllPayload

  // 模板 & 地址注册表
  'template-applied': TemplateAppliedPayload

  // SSE 同步状态
  'sse:sync-event': SyncEventPayload
  'sse:sync-failed': SyncEventPayload
  'sse:connected': void
  'sse:disconnected': void

  // 快捷键（shortcuts.ts 发出）
  'shortcut:save': void
  'shortcut:undo': void
  'shortcut:redo': void
  'shortcut:search': void
  'shortcut:goto': void
  'shortcut:export': void
  'shortcut:submit': void
  'shortcut:escape': void
  'shortcut:refresh': void
  'shortcut:help': void
  'shortcut:tab-focus': void
  'shortcut:list-up': void
  'shortcut:list-down': void
}

// ─── 导出单例 ─────────────────────────────────────────────────────────────────

export const eventBus = mitt<Events>()
