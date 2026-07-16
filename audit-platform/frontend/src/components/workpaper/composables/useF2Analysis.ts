/**
 * useF2Analysis — F2-18/19/20 分析组 composable 再导出
 * Spec: .kiro/specs/f2-inventory-main/ Task 11.1
 *
 * 实现已拆分：
 * - useF2OverallAnalysis.ts (F2-18)
 * - useF2ProductionSales.ts (F2-19)
 * - useF2CostComparison.ts (F2-20)
 */

// ─── F2-18 总体分析 ───────────────────────────────────────────────────────
export {
  useF2OverallAnalysis,
  F2_INDICATOR_DEFS,
  type F2CompositionRow,
  type F2StructureRow,
  type F2OverallPack,
  type F2AnomalyItem,
} from './useF2OverallAnalysis'

// ─── F2-19 产销量变动 ───────────────────────────────────────────────────────
export {
  useF2ProductionSales,
  F2_MONTH_LABELS,
  F2_PS_QUESTION_DEFS,
  type F2PsProductRow,
  type F2PsMaterialRow,
  type F2PsPack,
  type F2ProductionSalesRow,
} from './useF2ProductionSales'

// ─── F2-20 成本比较 ───────────────────────────────────────────────────────
export {
  useF2CostComparison,
  type F2CostRow,
  type F2CostPack,
} from './useF2CostComparison'
