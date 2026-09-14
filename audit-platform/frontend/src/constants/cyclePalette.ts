/**
 * 审计循环色板 — 唯一真源
 *
 * 全平台所有"循环字母→颜色"映射都从这里取。
 * 禁止在组件/view 中重新定义本地 CYCLE_COLORS / CYCLE_PALETTE / CYCLE_COLOR_MAP。
 * CSS 变量对应见 styles/gt-tokens.css（--gt-cycle-*）。
 *
 * 色板选型依据：panorama colorMaps.ts 的 14+4 循环色系（色相分布均匀、辨识度最高）。
 */

/** A~S 审计循环 + 辅助分类颜色映射 */
export const CYCLE_PALETTE: Record<string, string> = {
  // 业务循环 D~N
  D: '#1976D2',   // 蓝 — 销售收入
  E: '#00ACC1',   // 青 — 货币资金
  F: '#43A047',   // 绿 — 采购存货
  G: '#FDD835',   // 金 — 投资
  H: '#FB8C00',   // 橙 — 固定资产
  I: '#3949AB',   // 靛 — 无形资产
  J: '#EC407A',   // 粉 — 薪酬股份支付
  K: '#78909C',   // 灰 — 管理费用
  L: '#8D6E63',   // 棕 — 筹资
  M: '#AB47BC',   // 紫 — 股东权益
  N: '#E53935',   // 红 — 税费
  // 辅助循环 A/B/C/S
  A: '#26A69A',   // 蓝绿 — 报表/调整
  B: '#7E57C2',   // 淡紫 — 控制了解
  C: '#5C6BC0',   // 紫蓝 — 控制测试
  S: '#FFA726',   // 浅橙 — 专项程序
  // 兜底
  other: '#909399',
}

/**
 * 取循环颜色（大小写不敏感，未知→other 灰）
 *
 * @example cycleColor('D') // '#1976D2'
 * @example cycleColor('d') // '#1976D2'
 * @example cycleColor(null) // '#909399'
 */
export function cycleColor(code?: string | null): string {
  if (!code) return CYCLE_PALETTE.other
  return CYCLE_PALETTE[String(code).toUpperCase()] ?? CYCLE_PALETTE.other
}
