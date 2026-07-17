/**
 * ConfirmationKit.ts — 共享 UI 工具集
 *
 * 提供函证模块统一的：
 * - 金额格式化（右对齐 / 千分位 / 2 位小数 / 元）
 * - 网格美化调色板（与 GtGridSheet 网格美化对齐）
 * - 自动取数蓝色标识
 *
 * Sprint 3 Task 3.1
 * 注：原 12 态状态徽章（STATUS_BADGE_MAP/getStatusBadge）随孤儿的 useConfirmationStatus
 * 一并删除（2026-07-17 G3）——真实 UI 用 match_status 3 态 / Hub 5 态，无 12 态消费者。
 */

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

export interface AmountFormatOptions {
  /** 小数位数（默认 2） */
  decimals?: number
  /** 单位后缀（默认 '元'） */
  unit?: string
  /** 是否显示千分位分隔符（默认 true） */
  separator?: boolean
  /** 零值显示方式：'dash'=— / 'zero'=0.00 / 'empty'=空 */
  zeroDisplay?: 'dash' | 'zero' | 'empty'
}

/**
 * 格式化金额数值
 * - 右对齐（样式由消费方处理）
 * - 千分位分隔
 * - 2 位小数
 * - 单位"元"
 */
export function formatAmount(
  value: number | null | undefined,
  options: AmountFormatOptions = {}
): string {
  const { decimals = 2, unit = '', separator = true, zeroDisplay = 'zero' } = options

  if (value === null || value === undefined) {
    return zeroDisplay === 'empty' ? '' : zeroDisplay === 'dash' ? '—' : `0.${'0'.repeat(decimals)}`
  }

  if (value === 0) {
    switch (zeroDisplay) {
      case 'dash': return '—'
      case 'empty': return ''
      default: return `0.${'0'.repeat(decimals)}${unit}`
    }
  }

  const fixed = Math.abs(value).toFixed(decimals)
  const [intPart, decPart] = fixed.split('.')
  const formatted = separator
    ? intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
    : intPart
  const sign = value < 0 ? '-' : ''
  return `${sign}${formatted}.${decPart}${unit}`
}

// ─── 网格美化调色板 ──────────────────────────────────────────────────────────

/** 函证模块网格统一配色（与 GtGridSheet 网格美化对齐） */
export const GRID_PALETTE = {
  /** 表头背景（分组 5 色轮转） */
  headerColors: [
    '#E8F4FD',  // 浅蓝
    '#FFF3E0',  // 浅橙
    '#E8F5E9',  // 浅绿
    '#F3E5F5',  // 浅紫
    '#FFF9C4',  // 浅黄
  ],
  /** 斑马纹奇数行 */
  zebraOdd: '#FAFAFA',
  /** 斑马纹偶数行 */
  zebraEven: '#FFFFFF',
  /** 冻结列背景 */
  frozenCol: '#F5F7FA',
  /** 空值单元格文字色（淡化） */
  emptyCell: '#C0C4CC',
  /** 选中行高亮 */
  selectedRow: '#ECF5FF',
  /** 异常行高亮（舞弊/超限） */
  dangerRow: '#FEF0F0',
  /** 警告行高亮 */
  warningRow: '#FDF6EC',
} as const

// ─── 自动取数标识 ─────────────────────────────────────────────────────────────

/** 数据来源类型 */
export type DataSource = 'auto' | 'manual' | 'import'

export interface SourceIndicatorConfig {
  label: string
  color: string
  icon: string
}

/** 数据来源标识配置（蓝色=自动取数） */
export const SOURCE_INDICATOR_MAP: Record<DataSource, SourceIndicatorConfig> = {
  auto: { label: '自动', color: '#409EFF', icon: 'lightning' },
  manual: { label: '手工', color: '#909399', icon: 'edit' },
  import: { label: '导入', color: '#67C23A', icon: 'upload' },
}

/**
 * 获取数据来源标识配置
 */
export function getSourceIndicator(source?: string): SourceIndicatorConfig {
  return SOURCE_INDICATOR_MAP[(source as DataSource) ?? 'manual'] ?? SOURCE_INDICATOR_MAP.manual
}

// ─── 看板快捷常量 ────────────────────────────────────────────────────────────

/** 预警等级配色 */
export const WARN_LEVEL_COLORS = {
  ok: '#67C23A',
  warn: '#E6A23C',
  danger: '#F56C6C',
} as const

/** 覆盖率红线阈值 */
export const COVERAGE_THRESHOLDS = {
  /** 回函率警戒线 */
  replyRate: { warn: 80, danger: 60 },
  /** 确认覆盖率警戒线 */
  confirmRate: { warn: 70, danger: 50 },
} as const
