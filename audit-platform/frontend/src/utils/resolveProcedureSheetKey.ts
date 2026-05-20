/**
 * resolveProcedureSheetKey — 按 wp_code 前缀路由程序状态数据源 sheetKey
 *
 * spec workpaper-h-fixed-assets-cycle H-F13（Task 3.6）
 * 原始实现：F-F13 Task 3.7（E1/D/F 路由）
 * G-investment-cycle G-F12 Task 3.5: 加 G 循环路由 G1→g1a / G4→g4a / G7→g7a
 * M-equity-cycle M-F5 Task 2.4: 加 M 循环路由 M2→m2a / M4→m4a / M5→m5a / M6→m6a / M9→m9a / M10→m10a
 * N-tax-cycle N-F5 Task 2.5: 加 N 循环路由 N1→n1a / N2→n2a / N3→n3a / N4→n4a / N5→n5a
 *
 * 路由映射：
 * - G 循环：G1→g1a / G4→g4a / G7→g7a (G14 优先于 G1 避免误匹配)
 * - H 循环：H1→h1a / H2→h2a / H3→h3a / H8→h8a / H9→h9a
 * - F 循环：F2→f2a / F1→f1a / F3→f3a / F4→f4a / F5→f5a
 * - D 循环：D4→d4a / D2→d2a
 * - I 循环：I1→i1a / I3→i3a / I4→i4a (后续按需扩展)
 * - J 循环：J1→j1a / J2→j2a / J3→j3a
 * - L 循环：L1→l1a / L3→l3a / L5→l5a / L8→l8a
 * - M 循环：M2→m2a / M4→m4a / M5→m5a / M6→m6a / M9→m9a / M10→m10a
 * - N 循环：N1→n1a / N2→n2a / N3→n3a / N4→n4a / N5→n5a
 * - 默认：E1→e1a
 */
export function resolveProcedureSheetKey(wpCode: string): string {
  const upper = (wpCode || '').toUpperCase()
  // G 循环路由（G10/G11/G12/G13/G14 必须在 G1 之前判断，避免 startsWith('G1') 误匹配多位编号）
  if (upper.startsWith('G14')) return 'e1a' // G14 信用减值，无专属程序表 fallback
  if (upper.startsWith('G13')) return 'e1a' // G13 公允价值变动收益，fallback
  if (upper.startsWith('G12')) return 'e1a' // G12 净敞口套期，fallback
  if (upper.startsWith('G11')) return 'g11a' // G11 投资收益汇总专属
  if (upper.startsWith('G10')) return 'e1a' // G10 交易性金融负债，fallback
  if (upper.startsWith('G1')) return 'g1a' // G1 交易性金融资产
  if (upper.startsWith('G4')) return 'g4a' // G4 债权投资
  if (upper.startsWith('G6')) return 'g6a' // G6 其他债权投资
  if (upper.startsWith('G7')) return 'g7a' // G7 长期股权投资
  if (upper.startsWith('G8')) return 'g8a' // G8 其他权益工具投资
  // H 循环路由（H10 必须在 H1 之前判断，避免 startsWith('H1') 误匹配 H10）
  if (upper.startsWith('H10')) return 'e1a' // H10 无专属程序表，fallback
  if (upper.startsWith('H1')) return 'h1a'
  if (upper.startsWith('H2')) return 'h2a'
  if (upper.startsWith('H3')) return 'h3a'
  if (upper.startsWith('H8')) return 'h8a'
  if (upper.startsWith('H9')) return 'h9a'
  // I 循环路由
  if (upper.startsWith('I1')) return 'i1a'
  if (upper.startsWith('I3')) return 'i3a'
  if (upper.startsWith('I4')) return 'i4a'
  // J 循环路由
  if (upper.startsWith('J1')) return 'j1a'
  if (upper.startsWith('J2')) return 'j2a'
  if (upper.startsWith('J3')) return 'j3a'
  // L 循环路由（L-F9: L1→l1a / L3→l3a / L5→l5a / L8→l8a）
  if (upper.startsWith('L1')) return 'l1a' // L1 短期借款
  if (upper.startsWith('L3')) return 'l3a' // L3 长期借款
  if (upper.startsWith('L5')) return 'l5a' // L5 长期应付款
  if (upper.startsWith('L8')) return 'l8a' // L8 财务费用
  // M 权益循环路由（M-F5: M2→m2a / M4→m4a / M5→m5a / M6→m6a / M9→m9a / M10→m10a）
  if (upper.startsWith('M10')) return 'm10a' // M10 其他权益工具（必须在 M1 之前判断）
  if (upper.startsWith('M2')) return 'm2a' // M2 实收资本
  if (upper.startsWith('M4')) return 'm4a' // M4 资本公积
  if (upper.startsWith('M5')) return 'm5a' // M5 盈余公积
  if (upper.startsWith('M6')) return 'm6a' // M6 未分配利润
  if (upper.startsWith('M9')) return 'm9a' // M9 其他综合收益
  // N 税金循环路由（N-F5: N1→n1a / N2→n2a / N3→n3a / N4→n4a / N5→n5a）
  if (upper.startsWith('N1')) return 'n1a' // N1 递延所得税资产
  if (upper.startsWith('N2')) return 'n2a' // N2 应交税费
  if (upper.startsWith('N3')) return 'n3a' // N3 递延所得税负债
  if (upper.startsWith('N4')) return 'n4a' // N4 税金及附加
  if (upper.startsWith('N5')) return 'n5a' // N5 所得税费用
  // K 循环路由（K10/K11/K12/K13 必须在 K1 之前判断，避免 startsWith('K1') 误匹配多位编号）
  if (upper.startsWith('K13')) return 'e1a' // K13 资产处置收益（实测 wp_code 编号），fallback
  if (upper.startsWith('K12')) return 'e1a' // K12 营业外支出，fallback
  if (upper.startsWith('K11')) return 'k11a' // K11 资产减值损失专属
  if (upper.startsWith('K10')) return 'e1a' // K10 营业外收入，fallback
  if (upper.startsWith('K1')) return 'k1a' // K1 其他应收款
  if (upper.startsWith('K3')) return 'k3a' // K3 其他应付款
  if (upper.startsWith('K5')) return 'k5a' // K5 预计负债
  if (upper.startsWith('K8')) return 'k8a' // K8 销售费用
  if (upper.startsWith('K9')) return 'k9a' // K9 管理费用
  // F 循环路由
  if (upper.startsWith('F2')) return 'f2a'
  if (upper.startsWith('F1')) return 'f1a'
  if (upper.startsWith('F3')) return 'f3a'
  if (upper.startsWith('F4')) return 'f4a'
  if (upper.startsWith('F5')) return 'f5a'
  // D 循环路由
  if (upper.startsWith('D4')) return 'd4a'
  if (upper.startsWith('D2')) return 'd2a'
  // 默认 E1
  return 'e1a'
}
