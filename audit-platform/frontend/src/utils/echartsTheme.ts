/**
 * ECharts 全局主题统一 (UI-7)
 *
 * 基于致同品牌紫色 (#4b2d77) 色系定义 ECharts 全局主题，
 * 确保所有图表组件风格一致。
 *
 * 使用方式：
 *   import { useEchartsTheme } from '@/utils/echartsTheme'
 *   const { themeName } = useEchartsTheme()
 *   <v-chart :theme="themeName" ... />
 *
 * 在 main.ts 中调用 registerGtAuditTheme() 完成全局注册。
 */
import * as echarts from 'echarts'

// 品牌色系
const COLORS = {
  primary: '#4b2d77',
  secondary: '#7c5ba0',
  accent: '#a78bca',
  success: '#67C23A',
  warning: '#E6A23C',
  danger: '#F56C6C',
} as const

// 图表调色板（按视觉优先级排列）
const colorPalette = [
  COLORS.primary,
  COLORS.secondary,
  COLORS.accent,
  '#c4b5d9', // light purple
  COLORS.success,
  COLORS.warning,
  COLORS.danger,
  '#409EFF', // info blue
]

const GT_AUDIT_THEME_NAME = 'gt-audit'

const themeConfig = {
  color: colorPalette,
  backgroundColor: 'transparent',
  textStyle: {
    color: '#303133',
  },
  title: {
    textStyle: { color: '#303133', fontSize: 16 },
    subtextStyle: { color: '#909399' },
  },
  line: {
    itemStyle: { borderWidth: 2 },
    lineStyle: { width: 2 },
    symbolSize: 6,
    smooth: false,
  },
  bar: {
    itemStyle: { barBorderWidth: 0, barBorderRadius: [2, 2, 0, 0] },
  },
  pie: {
    itemStyle: { borderWidth: 1, borderColor: '#fff' },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#DCDFE6' } },
    axisTick: { lineStyle: { color: '#DCDFE6' } },
    axisLabel: { color: '#606266' },
    splitLine: { lineStyle: { color: '#F2F6FC' } },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#606266' },
    splitLine: { lineStyle: { color: '#F2F6FC' } },
  },
  legend: {
    textStyle: { color: '#606266' },
  },
  tooltip: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderColor: '#EBEEF5',
    textStyle: { color: '#303133' },
  },
}

/**
 * 注册 gt-audit 主题到 ECharts 全局（在 main.ts 中调用一次）
 */
export function registerGtAuditTheme(): void {
  echarts.registerTheme(GT_AUDIT_THEME_NAME, themeConfig)
}

/**
 * Composable：返回主题名称供 v-chart 使用
 */
export function useEchartsTheme() {
  return {
    themeName: GT_AUDIT_THEME_NAME,
    colors: COLORS,
  }
}

export { COLORS, GT_AUDIT_THEME_NAME }
