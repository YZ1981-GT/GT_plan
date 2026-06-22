/**
 * ConfirmationKit.ts — 共享 UI 工具集
 *
 * 提供函证模块统一的：
 * - 状态徽章配色（绿#完成 / 橙#关注 / 红#异常）
 * - 金额格式化（右对齐 / 千分位 / 2 位小数 / 元）
 * - 网格美化调色板（与 GtGridSheet 网格美化对齐）
 * - 自动取数蓝色标识
 *
 * Sprint 3 Task 3.1
 */
import type { ConfirmationStatus } from './useConfirmationStatus'

// ─── 状态颜色体系 ────────────────────────────────────────────────────────────

export type StatusColorLevel = 'success' | 'warning' | 'danger' | 'info' | 'primary'

export interface StatusBadgeConfig {
  label: string
  color: string
  bgColor: string
  level: StatusColorLevel
}

/** 12 态状态徽章配色映射 */
export const STATUS_BADGE_MAP: Record<ConfirmationStatus, StatusBadgeConfig> = {
  '未核实': { label: '未核实', color: '#909399', bgColor: '#f4f4f5', level: 'info' },
  '已核实': { label: '已核实', color: '#409EFF', bgColor: '#ecf5ff', level: 'primary' },
  '已发函': { label: '已发函', color: '#409EFF', bgColor: '#ecf5ff', level: 'primary' },
  '跟函中': { label: '跟函中', color: '#E6A23C', bgColor: '#fdf6ec', level: 'warning' },
  '已回函': { label: '已回函', color: '#67C23A', bgColor: '#f0f9eb', level: 'success' },
  '未回函': { label: '未回函', color: '#F56C6C', bgColor: '#fef0f0', level: 'danger' },
  '待验证': { label: '待验证', color: '#E6A23C', bgColor: '#fdf6ec', level: 'warning' },
  '相符': { label: '相符', color: '#67C23A', bgColor: '#f0f9eb', level: 'success' },
  '有差异': { label: '有差异', color: '#F56C6C', bgColor: '#fef0f0', level: 'danger' },
  '替代中': { label: '替代中', color: '#E6A23C', bgColor: '#fdf6ec', level: 'warning' },
  '完成': { label: '完成', color: '#67C23A', bgColor: '#f0f9eb', level: 'success' },
  '舞弊迹象': { label: '舞弊迹象', color: '#F56C6C', bgColor: '#fef0f0', level: 'danger' },
}

/**
 * 获取状态徽章配置
 */
export function getStatusBadge(status: ConfirmationStatus): StatusBadgeConfig {
  return STATUS_BADGE_MAP[status] ?? STATUS_BADGE_MAP['未核实']
}

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
