/**
 * formulaEngineInventory.ts — 前端 per-cycle 公式引擎清单（元数据登记）
 *
 * Spec: .kiro/specs/formula-management-library/ — Task 13.1
 * Requirements: 19.1（清单化：登记所有 useXFormulaEngine / useXCrossSheet 作为可核查真源）
 *               19.2（三类型映射：求和/比率→auto_calc、阈值→reasonability、勾稽→logic_check）
 *
 * 设计原则（无死角、无回归）：
 * - 本文件**仅登记元数据**（清单 + 三类型映射 + 接入状态），
 *   **不改变任何现有引擎的计算数值**（Property 19：接入前后产出逐一相等）。
 * - 平台存在两类客户端硬编码公式 composable：
 *     · `useXFormulaEngine`：计算原语（求和/比率/账面价值/阈值判断）
 *     · `useXCrossSheet`：跨 sheet/跨底稿勾稽与平衡校验
 *   本清单把它们统一登记，并标注其计算原语到三类型公式语义的映射，
 *   作为增量收敛（试点 useD3FormulaEngine + useS34FormulaEngine，其余标"待接入"）的可核查真源。
 *
 * 三类型公式语义（与后端 formula_type ∈ {auto_calc, logic_check, reasonability} 一致）：
 *   · auto_calc     计算并回填值（求和 createSumFormula / 比率 createRatioFormula / 账面价值 / 小计）
 *   · reasonability 提示/合理性判断，不改值（阈值 createThresholdFormula / 变动率超阈值高亮）
 *   · logic_check   勾稽/平衡校验，产出问题清单不改值（useXCrossSheet 的一致性/平衡检查）
 */

// ─── 三类型公式语义 ────────────────────────────────────────────────────────────

export type FormulaType = 'auto_calc' | 'logic_check' | 'reasonability'

/** composable 类别：计算引擎 vs 跨表勾稽 */
export type FormulaEngineKind = 'formula-engine' | 'cross-sheet'

/** 统一治理接入状态 */
export type IntegrationStatus = 'integrated' | 'pending'

/** 三类型中文标签（供 UI 展示） */
export const FORMULA_TYPE_LABEL: Record<FormulaType, string> = {
  auto_calc: '自动运算',
  logic_check: '逻辑判断',
  reasonability: '合理性提示',
}

/** 接入状态中文标签 */
export const INTEGRATION_STATUS_LABEL: Record<IntegrationStatus, string> = {
  integrated: '已接入',
  pending: '待接入',
}

// ─── 计算原语 → 三类型 的规则映射（Req 19.2） ─────────────────────────────────

/**
 * 计算原语函数名 → 公式类型 的规范映射。
 *
 * 这是三类型映射的**单一规则源**：任何前端公式引擎新增的计算原语，
 * 都应在此登记其对应的三类型语义，供接入统一治理时套用。
 * 仅作元数据标注，不改变原语的计算实现。
 */
export const PRIMITIVE_TYPE_MAP: Record<string, FormulaType> = {
  // ── auto_calc：求和 / 比率 / 账面价值 / 小计（计算并回填值） ──
  createSumFormula: 'auto_calc',
  createRatioFormula: 'auto_calc',
  sumRange: 'auto_calc',
  calcSubtotal: 'auto_calc',
  calcAuditedAmount: 'auto_calc',
  calcChangeAmount: 'auto_calc',
  calcChangeRate: 'auto_calc',
  calcPriorAudited: 'auto_calc',
  calcEndBalance: 'auto_calc',
  calcEndUnadjusted: 'auto_calc',
  calcEndAudited: 'auto_calc',
  calcRelatedPartyEndBalance: 'auto_calc',
  calcAnomalyRate: 'auto_calc',
  calcRatio: 'auto_calc',
  aggregateByNature: 'auto_calc',
  aggregateByAging: 'auto_calc',
  computeFormulas: 'auto_calc',

  // ── reasonability：阈值 / 合理性判断（提示，不改值） ──
  createThresholdFormula: 'reasonability',
  isChangeRateExceeding: 'reasonability',

  // ── logic_check：勾稽 / 平衡校验（产出问题清单，不改值） ──
  // 跨表勾稽由 useXCrossSheet 承载，其一致性/平衡检查一律映射为 logic_check。
}

/** 每种 composable 类别的默认三类型标注（可被单条 entry 覆盖） */
const DEFAULT_TYPES_BY_KIND: Record<FormulaEngineKind, FormulaType[]> = {
  // 计算引擎：求和/比率/账面价值（auto_calc）+ 阈值/合理性判断（reasonability）
  'formula-engine': ['auto_calc', 'reasonability'],
  // 跨表勾稽：一致性/平衡校验（logic_check）
  'cross-sheet': ['logic_check'],
}

// ─── 清单条目结构 ──────────────────────────────────────────────────────────────

export interface FormulaEngineInventoryEntry {
  /** composable 函数名，如 'useD3FormulaEngine'（同名可能存在于不同目录，故 filePath 为唯一键） */
  composable: string
  /** 相对 frontend/ 根的文件路径（唯一标识） */
  filePath: string
  /** 所属审计循环/子循环，如 'D3' / 'S34' / 'J1'（由 composable 名派生） */
  cycle: string
  /** composable 类别 */
  kind: FormulaEngineKind
  /** 该引擎承载的三类型公式语义标注（元数据，不改变计算数值） */
  formulaTypes: FormulaType[]
  /** 统一治理接入状态 */
  status: IntegrationStatus
  /** 备注（如试点说明、特殊原语） */
  notes?: string
}

// ─── cycle 派生 ────────────────────────────────────────────────────────────────

/**
 * 从 composable 名派生审计循环子码。
 * 'useD3FormulaEngine' → 'D3'；'useS34FormulaEngine' → 'S34'；
 * 'useG4BonInvFormulaEngine' → 'G4'；'useF2InvMaiFormulaEngine' → 'F2'。
 */
export function deriveCycle(composable: string): string {
  const stripped = composable.replace(/^use/, '')
  const m = stripped.match(/^([A-Z]\d*)/)
  return m ? m[1] : stripped
}

// ─── 试点（已接入统一治理，Task 13.2） ─────────────────────────────────────────

/** Task 13.2 试点接入的引擎（其余保留现状标"待接入"，无回归） */
const PILOT_INTEGRATED = new Set<string>([
  'src/components/workpaper/composables/useD3FormulaEngine.ts',
  'src/components/workpaper/s34-ipo-bundle/useS34FormulaEngine.ts',
])

// ─── 原始登记表（按目录分组的 composable 基名） ─────────────────────────────────

const WP_DIR = 'src/components/workpaper/composables'
const SRC_DIR = 'src/composables'

/** components/workpaper/composables/ 下的 useXFormulaEngine 引擎基名 */
const WP_FORMULA_ENGINES: string[] = [
  'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7',
  'E1',
  'F1', 'F2InvMai', 'F2InvSpe', 'F2InvVal', 'F2Special', 'F3', 'F3NotPay', 'F4AccPay', 'F5CosOf',
  'G10', 'G10TraFin', 'G11', 'G11InvInc', 'G12', 'G12NetHed', 'G13FaiVal', 'G13', 'G14CreImp', 'G14',
  'G1TraFin', 'G2IntRec', 'G3DivRec', 'G4BonInv', 'G5LonTer', 'G6OthBon',
  'G7EquityMethod', 'G7', 'G7LonTer', 'G7Sub', 'G8', 'G9',
  'H10', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8', 'H9',
  'I1', 'I2', 'I3', 'I4', 'I5', 'I6',
  'K10', 'K11', 'K12', 'K13', 'K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K7', 'K8', 'K9',
  'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8',
  'M10', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9',
  'N1', 'N2', 'N3', 'N4', 'N5',
  'S15', 'S20', 'S21', 'S35', 'S4', 'S5',
]

/** components/workpaper/composables/ 下的 useXCrossSheet 跨表勾稽基名 */
const WP_CROSS_SHEETS: string[] = [
  'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7',
  'F1', 'F2', 'F3',
  'H10', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8', 'H9',
  'I1', 'I2', 'I3', 'I4', 'I5', 'I6',
  'K10', 'K11', 'K12', 'K13', 'K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K7', 'K8', 'K9',
  'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8',
  'M10', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9',
  'N1', 'N2', 'N3', 'N4', 'N5',
]

/** src/composables/ 下的 useXFormulaEngine（G4/G5/G6 拆分引擎 + L1/L3） */
const SRC_FORMULA_ENGINES: string[] = [
  'G4Ecl', 'G4Main', 'G4Sppi', 'G5', 'G6Ecl', 'G6Main', 'G6Sppi', 'L1', 'L3',
]

/** 独立目录（函证 / IPO bundle / J 循环）的引擎与跨表，路径不规则，显式登记 */
const EXPLICIT_ENTRIES: Array<Pick<FormulaEngineInventoryEntry, 'composable' | 'filePath' | 'kind'>> = [
  // 函证模块公式引擎（跨循环复用）
  { composable: 'useH0FormulaEngine', filePath: 'src/components/workpaper/confirmation/alternativeH05/composables/useH0FormulaEngine.ts', kind: 'formula-engine' },
  { composable: 'useK0FormulaEngine', filePath: 'src/components/workpaper/confirmation/k0-confirmation/composables/useK0FormulaEngine.ts', kind: 'formula-engine' },
  { composable: 'useL0FormulaEngine', filePath: 'src/components/workpaper/confirmation/l0-confirmation/composables/useL0FormulaEngine.ts', kind: 'formula-engine' },
  { composable: 'useG0FormulaEngine', filePath: 'src/components/workpaper/g0-confirmation/composables/useG0FormulaEngine.ts', kind: 'formula-engine' },
  // S34 IPO bundle（试点引擎所在）
  { composable: 'useS34FormulaEngine', filePath: 'src/components/workpaper/s34-ipo-bundle/useS34FormulaEngine.ts', kind: 'formula-engine' },
  // J 循环公式引擎
  { composable: 'useJ1FormulaEngine', filePath: 'src/composables/workpaper/j1/useJ1FormulaEngine.ts', kind: 'formula-engine' },
  { composable: 'useJ2FormulaEngine', filePath: 'src/composables/workpaper/j2/useJ2FormulaEngine.ts', kind: 'formula-engine' },
  { composable: 'useJ3FormulaEngine', filePath: 'src/composables/workpaper/j3/useJ3FormulaEngine.ts', kind: 'formula-engine' },
  // 跨表勾稽：src/composables 下的独立 CrossSheet
  { composable: 'useL1CrossSheet', filePath: 'src/composables/useL1CrossSheet.ts', kind: 'cross-sheet' },
  { composable: 'useJ1CrossSheet', filePath: 'src/composables/workpaper/j1/useJ1CrossSheet.ts', kind: 'cross-sheet' },
  { composable: 'useJ2CrossSheet', filePath: 'src/composables/workpaper/j2/useJ2CrossSheet.ts', kind: 'cross-sheet' },
  { composable: 'useJ3CrossSheet', filePath: 'src/composables/workpaper/j3/useJ3CrossSheet.ts', kind: 'cross-sheet' },
]

// ─── 条目构建（元数据登记，不触碰计算实现） ─────────────────────────────────────

function buildEntry(
  composable: string,
  filePath: string,
  kind: FormulaEngineKind,
  overrides: Partial<FormulaEngineInventoryEntry> = {},
): FormulaEngineInventoryEntry {
  return {
    composable,
    filePath,
    cycle: deriveCycle(composable),
    kind,
    formulaTypes: DEFAULT_TYPES_BY_KIND[kind],
    status: PILOT_INTEGRATED.has(filePath) ? 'integrated' : 'pending',
    ...overrides,
  }
}

function buildFromBaseNames(
  baseNames: string[],
  dir: string,
  suffix: 'FormulaEngine' | 'CrossSheet',
  kind: FormulaEngineKind,
): FormulaEngineInventoryEntry[] {
  return baseNames.map((base) => {
    const composable = `use${base}${suffix}`
    return buildEntry(composable, `${dir}/${composable}.ts`, kind)
  })
}

/**
 * 前端 per-cycle 公式引擎完整清单（Req 19.1 可核查真源）。
 *
 * 覆盖全部 useXFormulaEngine（计算引擎）与 useXCrossSheet（跨表勾稽），
 * 每条标注三类型映射与接入状态。仅元数据，不改变任何计算数值（Req 19.2 / Property 19）。
 */
export const FORMULA_ENGINE_INVENTORY: FormulaEngineInventoryEntry[] = [
  ...buildFromBaseNames(WP_FORMULA_ENGINES, WP_DIR, 'FormulaEngine', 'formula-engine'),
  ...buildFromBaseNames(WP_CROSS_SHEETS, WP_DIR, 'CrossSheet', 'cross-sheet'),
  ...buildFromBaseNames(SRC_FORMULA_ENGINES, SRC_DIR, 'FormulaEngine', 'formula-engine'),
  ...EXPLICIT_ENTRIES.map((e) => buildEntry(e.composable, e.filePath, e.kind)),
].map((entry) => {
  // 试点引擎补充备注
  if (entry.status === 'integrated') {
    return { ...entry, notes: 'Task 13.2 试点：isFormulaCell 单元挂 GtFormulaSourceTooltip，引用经 useAcnr 解析' }
  }
  return entry
})

// ─── 查询辅助（供治理进度视图 / 契约测试使用） ──────────────────────────────────

/** 按接入状态过滤 */
export function getEnginesByStatus(status: IntegrationStatus): FormulaEngineInventoryEntry[] {
  return FORMULA_ENGINE_INVENTORY.filter((e) => e.status === status)
}

/** 按三类型语义过滤（含该类型的引擎） */
export function getEnginesByFormulaType(type: FormulaType): FormulaEngineInventoryEntry[] {
  return FORMULA_ENGINE_INVENTORY.filter((e) => e.formulaTypes.includes(type))
}

/** 按 composable 类别过滤 */
export function getEnginesByKind(kind: FormulaEngineKind): FormulaEngineInventoryEntry[] {
  return FORMULA_ENGINE_INVENTORY.filter((e) => e.kind === kind)
}

/** 清单覆盖度摘要（供治理进度可视化 / 增量收敛追踪） */
export interface InventorySummary {
  total: number
  integrated: number
  pending: number
  byKind: Record<FormulaEngineKind, number>
  byFormulaType: Record<FormulaType, number>
}

export function getInventorySummary(): InventorySummary {
  const summary: InventorySummary = {
    total: FORMULA_ENGINE_INVENTORY.length,
    integrated: 0,
    pending: 0,
    byKind: { 'formula-engine': 0, 'cross-sheet': 0 },
    byFormulaType: { auto_calc: 0, logic_check: 0, reasonability: 0 },
  }
  for (const entry of FORMULA_ENGINE_INVENTORY) {
    if (entry.status === 'integrated') summary.integrated += 1
    else summary.pending += 1
    summary.byKind[entry.kind] += 1
    for (const t of entry.formulaTypes) summary.byFormulaType[t] += 1
  }
  return summary
}
