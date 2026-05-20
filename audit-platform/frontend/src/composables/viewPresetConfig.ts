/**
 * viewPresetConfig.ts — 角色视图预设配置（Role-Based View Switching）
 *
 * 配置驱动的 4 种视图预设（助理/经理/合伙人/质控），
 * 定义排序/过滤/高亮/badge/汇总规则。
 *
 * Requirements: 3.1, 4.5, 5.1, 6.1
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export type ViewPresetId = 'assistant' | 'manager' | 'partner' | 'qc'

/** 底稿列表项（最小接口，兼容 WorkpaperList 已有数据结构） */
export interface WpItem {
  id: string
  wp_code: string
  status: string
  audit_cycle: string
  review_status?: string
  /** 运行时注入：open review count */
  _openReviewCount?: number
  /** 运行时注入：risk level (0=高 1=中 2=低) */
  _riskLevel?: number
  [key: string]: any
}

export interface PrereqResult {
  overall: 'ready' | 'partial' | 'blocked'
  items: { wp_code: string }[]
}

export interface VRResult {
  blocking_count: number
  warning_count: number
  info_count: number
}

export interface ReviewRecord {
  id: string
  status: string
  [key: string]: any
}

export interface HighlightContext {
  prerequisiteStatus: Map<string, PrereqResult>
  consistencyGate: Map<string, VRResult>
  reviewRecords: Map<string, ReviewRecord[]>
}

export interface RowHighlight {
  style: Record<string, string>
  tooltip?: string
}

export interface BadgeData {
  value: number
  type: 'danger' | 'warning' | 'info'
  visible: boolean
}

export interface HighlightRule {
  condition: (item: WpItem, ctx: HighlightContext) => boolean
  style: Record<string, string>
  tooltip?: (item: WpItem, ctx: HighlightContext) => string
}

export interface BadgeRule {
  position: 'right'
  value: (item: WpItem) => number
  type: (val: number) => 'danger' | 'warning' | 'info'
  visible: (val: number) => boolean
}

export interface SummaryData {
  label: string
  items: { key: string; value: number | string }[]
}

export interface GroupedData {
  key: string
  label: string
  items: WpItem[]
  progress: number
  total: number
  completed: number
  trimmedCount: number
  collapsed: boolean
}

export interface ViewPresetConfig {
  id: ViewPresetId
  label: string
  icon: string
  sortFn: (a: WpItem, b: WpItem) => number
  filterFn?: (item: WpItem) => boolean
  groupBy?: (item: WpItem) => string
  highlightRules: HighlightRule[]
  badgeRules?: BadgeRule[]
  summaryFn?: (items: WpItem[], ctx: HighlightContext) => SummaryData
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 角色→默认视图映射 */
export const ROLE_DEFAULT_MAP: Record<string, ViewPresetId> = {
  assistant: 'assistant',
  auditor: 'assistant',
  manager: 'manager',
  partner: 'partner',
  qc: 'qc',
  admin: 'partner',
  eqcr: 'qc',
}

/** 状态优先级（助理视图排序） */
export const STATUS_PRIORITY: Record<string, number> = {
  pending: 0,
  in_progress: 1,
  completed: 2,
  reviewed: 3,
}

// ─── Sort Functions ──────────────────────────────────────────────────────────

/** 按状态优先级排序：pending → in_progress → completed → reviewed */
export function statusPrioritySort(a: WpItem, b: WpItem): number {
  return (STATUS_PRIORITY[a.status] ?? 99) - (STATUS_PRIORITY[b.status] ?? 99)
}

/** 按风险等级排序：高风险(0) → 中风险(1) → 低风险(2) */
export function riskLevelSort(a: WpItem, b: WpItem): number {
  return (a._riskLevel ?? 2) - (b._riskLevel ?? 2)
}

/** wp_code 自然排序（经理视图分组内） */
export function wpCodeNaturalSort(a: WpItem, b: WpItem): number {
  return a.wp_code.localeCompare(b.wp_code, undefined, { numeric: true })
}

// ─── Filter Functions ────────────────────────────────────────────────────────

/** 质控视图过滤：关键判断点底稿
 *
 * 包含规则：
 * - B15（重要性水平）/ A15（持续经营）/ B50-4（特别风险）
 * - 各业务循环审定表（D~N 循环 + 数字 + "-1"，如 D2-1/F2-1/H1-1）
 *
 * 不包含：B23-1（控制了解）/ C2-1（控制测试）等非业务循环底稿
 */
const QC_FILTER_PATTERN = /^(B15|A15|B50-4)$|^[D-N]\d+-1$/
export function isKeyJudgmentPoint(item: WpItem): boolean {
  return QC_FILTER_PATTERN.test(item.wp_code)
}

// ─── Summary Functions ───────────────────────────────────────────────────────

/** 合伙人视图汇总：blocking 总数 + 未解决复核意见总数 */
export function partnerSummary(items: WpItem[], ctx: HighlightContext): SummaryData {
  let blockingTotal = 0
  let openReviewTotal = 0

  for (const item of items) {
    const vr = ctx.consistencyGate.get(item.wp_code)
    if (vr && vr.blocking_count > 0) {
      blockingTotal += vr.blocking_count
    }
    const reviews = ctx.reviewRecords.get(item.wp_code)
    if (reviews) {
      openReviewTotal += reviews.filter(r => r.status === 'open').length
    }
  }

  return {
    label: '合伙人视图汇总',
    items: [
      { key: 'Blocking 未通过', value: blockingTotal },
      { key: '未解决复核意见', value: openReviewTotal },
    ],
  }
}

/** 质控视图汇总：抽查路径建议（按风险从高到低排列编码序列） */
export function qcSummary(items: WpItem[], _ctx: HighlightContext): SummaryData {
  // 按风险等级排序后取编码序列
  const sorted = [...items].sort((a, b) => (a._riskLevel ?? 2) - (b._riskLevel ?? 2))
  const path = sorted.map(item => item.wp_code).join(' → ')

  return {
    label: '抽查路径建议',
    items: [
      { key: '建议路径', value: path || '暂无关键判断点底稿' },
      { key: '底稿数', value: items.length },
    ],
  }
}

// ─── View Preset Configurations ──────────────────────────────────────────────

export const VIEW_PRESET_CONFIG: Record<ViewPresetId, ViewPresetConfig> = {
  // Task 1.4: 助理视图预设
  assistant: {
    id: 'assistant',
    label: '助理视图',
    icon: '👤',
    sortFn: statusPrioritySort,
    highlightRules: [
      {
        // 前置依赖未满足 → 橙色左边框 3px + tooltip
        condition: (item, ctx) => {
          const prereq = ctx.prerequisiteStatus.get(item.wp_code)
          return prereq?.overall === 'blocked'
        },
        style: { borderLeft: '3px solid #e6a23c' },
        tooltip: (item, ctx) => {
          const prereq = ctx.prerequisiteStatus.get(item.wp_code)
          const codes = prereq?.items?.map(i => i.wp_code).join(', ') ?? ''
          return `缺失前置: ${codes}`
        },
      },
      {
        // 已完成/已复核 → 灰色文字
        condition: (item) => ['completed', 'reviewed'].includes(item.status),
        style: { color: '#999' },
      },
    ],
  },

  // Task 1.5: 经理视图预设
  manager: {
    id: 'manager',
    label: '经理视图',
    icon: '📊',
    sortFn: wpCodeNaturalSort,
    groupBy: (item) => item.audit_cycle,
    highlightRules: [],
  },

  // Task 1.6: 合伙人视图预设
  partner: {
    id: 'partner',
    label: '合伙人视图',
    icon: '🔍',
    sortFn: riskLevelSort,
    highlightRules: [
      {
        // blocking VR 未通过 → 红色背景 + 红色左边框
        condition: (item, ctx) => {
          const vr = ctx.consistencyGate.get(item.wp_code)
          return (vr?.blocking_count ?? 0) > 0
        },
        style: { backgroundColor: 'rgba(255,0,0,0.08)', borderLeft: '3px solid #f56c6c' },
      },
    ],
    badgeRules: [
      {
        position: 'right',
        value: (item) => item._openReviewCount ?? 0,
        type: (val) => val > 0 ? 'danger' : 'info',
        visible: (val) => val > 0,
      },
    ],
    summaryFn: partnerSummary,
  },

  // Task 1.7: 质控视图预设
  qc: {
    id: 'qc',
    label: '质控视图',
    icon: '✅',
    sortFn: riskLevelSort,
    filterFn: isKeyJudgmentPoint,
    highlightRules: [
      {
        // 未复核 → 黄色背景
        condition: (item) => item.review_status !== 'reviewed',
        style: { backgroundColor: 'rgba(255,200,0,0.08)' },
      },
    ],
    summaryFn: qcSummary,
  },
}

/** 所有有效的 ViewPresetId 值 */
export const VALID_PRESET_IDS: ViewPresetId[] = ['assistant', 'manager', 'partner', 'qc']
