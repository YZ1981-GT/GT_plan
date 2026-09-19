/**
 * 联动全景图颜色与样式映射常量（design v0.2）
 *
 * 节点 cycle 着色 / 边 severity 着色 / 边线宽，前后端共享逻辑。
 * 循环色取自 constants/cyclePalette.ts 单一真源。
 */

import { CYCLE_PALETTE, cycleColor } from '@/constants/cyclePalette'

// 节点颜色 — 按循环（从 cyclePalette 展开 + 全景图专有分类键）
export const CYCLE_COLOR_MAP: Record<string, string> = {
  ...CYCLE_PALETTE,
  // 全景图专有分类
  report: '#0D47A1',   // 深蓝 (BS/IS/CFS/EQ)
  note: '#4A148C',     // 深紫 (附注)
  module: '#607D8B',   // 蓝灰 (cross_module 虚拟节点)
}

// 边颜色 — 按 severity（5 级）
export const SEVERITY_COLOR_MAP: Record<string, string> = {
  blocking: '#D32F2F',
  required: '#EF6C00',
  warning: '#F57C00',
  recommended: '#42A5F5',
  info: '#9E9E9E',
}

// 边线宽 — 按 severity
export const SEVERITY_WIDTH_MAP: Record<string, number> = {
  blocking: 2,
  required: 2,
  warning: 1.5,
  recommended: 1,
  info: 1,
}

// 循环显示名（CycleFilter / Legend 用）
export const CYCLE_DISPLAY_NAME: Record<string, string> = {
  D: 'D 销售收入',
  E: 'E 货币资金',
  F: 'F 采购存货',
  G: 'G 投资',
  H: 'H 固定资产',
  I: 'I 无形资产',
  J: 'J 薪酬股份支付',
  K: 'K 管理费用',
  L: 'L 筹资',
  M: 'M 股东权益',
  N: 'N 税费',
  A: 'A 报表/调整',
  B: 'B 控制了解',
  C: 'C 控制测试',
  S: 'S 专项程序',
  report: '报表',
  note: '附注',
  module: '跨模块',
  other: '其他/未分类',
}

// severity 显示名（Legend 用）
export const SEVERITY_DISPLAY_NAME: Record<string, string> = {
  blocking: '阻断',
  required: '必填',
  warning: '警告',
  recommended: '建议',
  info: '提示',
}

// 节点半径计算（degree 加权）
export function nodeRadius(degree: number): number {
  // 基础 6px + degree 0.4 加权，cap 在 18px
  return Math.min(6 + degree * 0.4, 18)
}

// 颜色映射安全访问（兜底为 other 灰）
// 全景图有专有键(module/note/report)，用本地 map 查再 fallback 到统一 cycleColor
export function cycleColor(cycle: string): string {
  return CYCLE_COLOR_MAP[cycle] ?? CYCLE_PALETTE.other
}

export function severityColor(severity: string): string {
  return SEVERITY_COLOR_MAP[severity] ?? SEVERITY_COLOR_MAP.info
}

export function severityWidth(severity: string): number {
  return SEVERITY_WIDTH_MAP[severity] ?? 1
}
