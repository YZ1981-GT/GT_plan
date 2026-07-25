/**
 * cycleHandbookRegistry.ts — 底稿目录页「编制/使用手册」弹窗注册表（wp_code → 异步 dialog 组件）
 *
 * GtBIndex 渲染的目录页（E1 + D~N 各科目）按 wp_code 从此注册表取对应手册弹窗；
 * 未注册的科目目录页不显示手册按钮（优雅降级）。K 循环走专属 GtK{n} 不经此表。
 *
 * 每个 dialog 组件契约：props `modelValue:boolean` + `initialTab?:'preparation'|'usage'`，
 * emit `update:modelValue`；内部渲染 `{cycle}/handbooks/{preparation,usage}.md`。
 */
import type { Component } from 'vue'

type DialogLoader = () => Promise<{ default: Component }>

export const cycleHandbookRegistry: Record<string, DialogLoader> = {
  // E1 货币资金（E1 自带 E1TabDirectory，此处备用）
  E1: () => import('@/components/workpaper/e1/E1PreparationHandbookDialog.vue'),
  // D 销售/收入循环
  D1: () => import('@/components/workpaper/d1/D1PreparationHandbookDialog.vue'),
  D2: () => import('@/components/workpaper/d2/D2PreparationHandbookDialog.vue'),
  D3: () => import('@/components/workpaper/d3/D3PreparationHandbookDialog.vue'),
  D4: () => import('@/components/workpaper/d4/D4PreparationHandbookDialog.vue'),
  D5: () => import('@/components/workpaper/d5/D5PreparationHandbookDialog.vue'),
  D6: () => import('@/components/workpaper/d6/D6PreparationHandbookDialog.vue'),
  D7: () => import('@/components/workpaper/d7/D7PreparationHandbookDialog.vue'),
  // F 存货/成本循环（GtBIndex 路径，通用卡片自动渲染）
  F1: () => import('@/components/workpaper/f1/F1PreparationHandbookDialog.vue'),
  F2: () => import('@/components/workpaper/f2/F2PreparationHandbookDialog.vue'),
  F3: () => import('@/components/workpaper/f3-notes-payable/F3PreparationHandbookDialog.vue'),
  F4: () => import('@/components/workpaper/f4-accounts-payable/F4PreparationHandbookDialog.vue'),
  F5: () => import('@/components/workpaper/f5-cost-of-sales/F5PreparationHandbookDialog.vue'),
  // G 金融资产/投资/损益循环（GtBIndex 路径，通用卡片自动渲染）
  G1: () => import('@/components/workpaper/g1-trading-financial-assets/G1PreparationHandbookDialog.vue'),
  G2: () => import('@/components/workpaper/g2-interest-receivable/G2PreparationHandbookDialog.vue'),
  G3: () => import('@/components/workpaper/g3-dividend-receivable/G3PreparationHandbookDialog.vue'),
  G4: () => import('@/components/workpaper/g4-bond-investment-main/G4PreparationHandbookDialog.vue'),
  G5: () => import('@/components/workpaper/g5-long-term-receivable/G5PreparationHandbookDialog.vue'),
  G6: () => import('@/components/workpaper/g6-other-bond-investment-main/G6PreparationHandbookDialog.vue'),
  G7: () => import('@/components/workpaper/g7-long-term-equity-main/G7PreparationHandbookDialog.vue'),
  G8: () => import('@/components/workpaper/g8-other-equity-instruments/G8PreparationHandbookDialog.vue'),
  G9: () => import('@/components/workpaper/g9-other-noncurrent-financial/G9PreparationHandbookDialog.vue'),
  G10: () => import('@/components/workpaper/g10-trading-financial-liabilities/G10PreparationHandbookDialog.vue'),
  G11: () => import('@/components/workpaper/g11-investment-income/G11PreparationHandbookDialog.vue'),
  G12: () => import('@/components/workpaper/g12-net-hedge-gains/G12PreparationHandbookDialog.vue'),
  G13: () => import('@/components/workpaper/g13-fair-value-changes/G13PreparationHandbookDialog.vue'),
  G14: () => import('@/components/workpaper/g14-credit-impairment-loss/G14PreparationHandbookDialog.vue'),
  // H 长期资产循环（GtBIndex 路径）
  H1: () => import('@/components/workpaper/h1/H1PreparationHandbookDialog.vue'),
  H2: () => import('@/components/workpaper/h2/H2PreparationHandbookDialog.vue'),
  H3: () => import('@/components/workpaper/h3/H3PreparationHandbookDialog.vue'),
  H4: () => import('@/components/workpaper/h4/H4PreparationHandbookDialog.vue'),
  H5: () => import('@/components/workpaper/h5/H5PreparationHandbookDialog.vue'),
  H6: () => import('@/components/workpaper/h6/H6PreparationHandbookDialog.vue'),
  H7: () => import('@/components/workpaper/h7/H7PreparationHandbookDialog.vue'),
  H8: () => import('@/components/workpaper/h8/H8PreparationHandbookDialog.vue'),
  H9: () => import('@/components/workpaper/h9/H9PreparationHandbookDialog.vue'),
  H10: () => import('@/components/workpaper/h10/H10PreparationHandbookDialog.vue'),
}

/** 取指定 wp_code 的手册弹窗 loader；无则返回 null（目录页不显示手册按钮）。 */
export function getCycleHandbookLoader(wpCode: string | undefined | null): DialogLoader | null {
  if (!wpCode) return null
  return cycleHandbookRegistry[wpCode] ?? null
}
