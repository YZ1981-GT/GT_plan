/**
 * 联动全景图颜色与样式映射常量（design v0.2）
 *
 * 节点 cycle 着色 / 边 severity 着色 / 边线宽，前后端共享逻辑。
 */

// 节点颜色 — 按循环
export const CYCLE_COLOR_MAP: Record<string, string> = {
  // 业务循环
  D: '#1976D2',   // 蓝
  E: '#00ACC1',   // 青
  F: '#43A047',   // 绿
  G: '#FDD835',   // 金
  H: '#FB8C00',   // 橙
  I: '#3949AB',   // 靛
  J: '#EC407A',   // 粉
  K: '#78909C',   // 灰
  L: '#8D6E63',   // 棕
  M: '#AB47BC',   // 紫
  N: '#E53935',   // 红
  // 辅助类
  A: '#26A69A',   // 蓝绿（A 类报表/调整）
  B: '#7E57C2',   // 淡紫（B 类控制了解）
  C: '#5C6BC0',   // 紫蓝（C 类控制测试）
  S: '#FFA726',   // 浅橙（S 专项程序）
  // 报表/附注/模块/兜底
  report: '#0D47A1',   // 深蓝 (BS/IS/CFS/EQ)
  note: '#4A148C',     // 深紫 (附注)
  module: '#607D8B',   // 蓝灰 (cross_module 虚拟节点)
  other: '#BDBDBD',    // 中灰 (兜底)
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
export function cycleColor(cycle: string): string {
  return CYCLE_COLOR_MAP[cycle] ?? CYCLE_COLOR_MAP.other
}

export function severityColor(severity: string): string {
  return SEVERITY_COLOR_MAP[severity] ?? SEVERITY_COLOR_MAP.info
}

export function severityWidth(severity: string): number {
  return SEVERITY_WIDTH_MAP[severity] ?? 1
}
