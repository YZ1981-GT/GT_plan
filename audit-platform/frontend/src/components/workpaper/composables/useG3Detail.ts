/**
 * useG3Detail — G3-2 应收股利明细表
 *
 * spec: `g-cycle-single-region-detail-lanes` · Task 14 / C-13（方案 A：按模板 32 列矩阵重建）
 *
 * ═══ 方案 A 整表重建 ═══
 *
 * 改造前 34 字段（id/seq + 32 业务）是「被投资方信息/持股明细/分红方案/应收核算」四区段体系，
 * 与模板 `明细表G3-2` 的 32 列（A + C..AG）**只有 2 个能对上**（`investeeName`→A / `remark`→AG）。
 *
 * 本轮按模板矩阵重建：
 * - 32 受管列严格对齐模板（列序即 Excel 列序 A→AG，跳过空的 B 列）
 * - 12 公式列 = F M N O P T AA AB AC AD AE AF（两区同形）
 * - 20 editable 列 = A C D E G H I J K L Q R S U V W X Y Z AG
 * - 两区通过 `agingCategory` 字段区分（`within_one_year` / `over_one_year`）
 *
 * 🔴 **旧 34 字段中 30 个不在模板里的字段归属**（不删，保留为非受管）：
 * - 被投资方档案 7 个（socialCreditCode/registeredCapital/industry/investType/initialCost/investDate
 *   + sharesHeld/shareholdingRatio/investeeNetProfit/investeeNetAssets/equityShare/bookValue/
 *   accountingMethod/isListed/listingCode）→ 部分归 `测算及检查表G3-4`
 * - 分红方案 8 个（resolutionDate/dividendPlan/dps/declarationDate/recordDate/exDividendDate/
 *   totalDividend/payoutRatio）→ 归 `测算及检查表G3-4`
 * - 收款 5 个（dividendReceivable/receivedAmount/netReceivable/receiptDate/receiptMethod）
 *   → 归 `长期未收回款项检查表G3-5`
 * - 逾期 2 个（isOverdue/overdueDays）→ 归 `G3-5`
 *
 * Requirements: g-cycle-single-region-detail-lanes 1.4, 2.1, 2.4, 2.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcEquityShare,
  calcDividend,
  calcPayoutRatio,
  calcNetReceivable,
  calcOverdueDays,
  calcSubtotal,
} from './useG3DivRecFormulaEngine'
import { G3_DETAIL_ROWS_KEY } from './g3Constants'
import type { ChecklistResponse } from './useF1FormData'
// 🔴 Task 7（spec g-cycle-single-region-detail-lanes）：行身份铸造收口到单点。
import {
  createMintStats,
  mintRowIdSuffix,
  resolveStableRowIds,
  type RowIdentityMintStats,
} from './g1g3RowIdentity'

// ─── Types ───────────────────────────────────────────────────────────────────

export type G3InvestType = 'long-term-equity' | 'other-equity'
export type G3AccountingMethod = 'cost' | 'equity'
/** 两区归属：账龄一年以内 / 一年以上 */
export type G3AgingCategory = 'within_one_year' | 'over_one_year'

/** G3-2 明细行 —— 按模板 32 列矩阵重建 + 旧字段保留为非受管 */
export interface DividendDetailRow {
  id: string
  seq: number

  // ═══ 受管列（32 个，顺序即模板列序 A → AG，跳过空的 B 列）═══
  // 两区归属（前端用，不映射独立模板列，但 A 列本身就是「项目」）
  agingCategory: G3AgingCategory

  // A —— 项目（被投资方名称）
  investeeName: string

  // ── 账面余额 (C9:P9) ──
  // 未审数 (C10:F10)
  bvUnauditedOpening: number      // C 期初数
  bvUnauditedIncrease: number     // D 本期增加
  bvUnauditedDecrease: number     // E 本期减少
  bvUnauditedClosing: number      // F 期末数（公式 = C+D-E）
  // 期初调整 (G10:H10)
  bvPriorAdjAje: number           // G 账项调整
  bvPriorAdjRje: number           // H 重分类调整
  // 账项调整 (I10:J10)
  bvAjeIncrease: number           // I 本期增加
  bvAjeDecrease: number           // J 本期减少
  // 重分类调整 (K10:L10)
  bvRjeIncrease: number           // K 本期增加
  bvRjeDecrease: number           // L 本期减少
  // 审定数 (M10:P10)
  bvAuditedOpening: number        // M 期初数（公式 = C+G+H）
  bvAuditedIncrease: number       // N 本期增加（公式 = D+I+K）
  bvAuditedDecrease: number       // O 本期减少（公式 = E+J+L）
  bvAuditedClosing: number        // P 期末数（公式 = M+N-O）

  // ── 减值准备 (Q9:AD9) ──
  // 未审数 (Q10:T10)
  impUnauditedOpening: number     // Q 期初数
  impUnauditedIncrease: number    // R 本期增加
  impUnauditedDecrease: number    // S 本期减少
  impUnauditedClosing: number     // T 期末数（公式 = Q+R-S）
  // 期初调整 (U10:V10)
  impPriorAdjAje: number          // U 账项调整
  impPriorAdjRje: number          // V 重分类调整
  // 账项调整 (W10:X10)
  impAjeIncrease: number          // W 本期增加
  impAjeDecrease: number          // X 本期减少
  // 重分类调整 (Y10:Z10)
  impRjeIncrease: number          // Y 本期增加
  impRjeDecrease: number          // Z 本期减少
  // 审定数 (AA10:AD10)
  impAuditedOpening: number       // AA 期初数（公式 = Q+U+V）
  impAuditedIncrease: number      // AB 本期增加（公式 = R+W+Y）
  impAuditedDecrease: number      // AC 本期减少（公式 = S+X+Z）
  impAuditedClosing: number       // AD 期末数（公式 = AA+AB-AC）

  // ── 账面价值 (AE9:AF9) ──
  netBookOpening: number          // AE 期初数（公式 = M-AA）
  netBookClosing: number          // AF 期末数（公式 = P-AD）

  // ── 备注 (AG) ──
  remark: string

  // ═══ 非受管字段（旧 34 字段中不在模板里的 30 个，保留兼容 G3-4/G3-5）═══
  /** @deprecated 移交 G3-4 测算及检查表 */
  socialCreditCode: string
  /** @deprecated 移交 G3-4 */
  registeredCapital: number
  /** @deprecated 移交 G3-4 */
  industry: string
  /** @deprecated 移交 G3-4 */
  investType: G3InvestType
  /** @deprecated 移交 G3-4 */
  initialCost: number
  /** @deprecated 移交 G3-4 */
  investDate: string
  /** @deprecated 移交 G3-4 */
  sharesHeld: number
  /** @deprecated 移交 G3-4 */
  shareholdingRatio: number
  /** @deprecated 移交 G3-4 */
  investeeNetProfit: number
  /** @deprecated 移交 G3-4 */
  investeeNetAssets: number
  /** @deprecated 移交 G3-4 */
  equityShare: number
  /** @deprecated 移交 G3-4 */
  bookValue: number
  /** @deprecated 移交 G3-4 */
  accountingMethod: G3AccountingMethod
  /** @deprecated 移交 G3-4 */
  isListed: string
  /** @deprecated 移交 G3-4 */
  listingCode: string
  /** @deprecated 移交 G3-4 */
  resolutionDate: string
  /** @deprecated 移交 G3-4 */
  dividendPlan: string
  /** @deprecated 移交 G3-4 */
  dps: number
  /** @deprecated 移交 G3-4 */
  declarationDate: string
  /** @deprecated 移交 G3-4 */
  recordDate: string
  /** @deprecated 移交 G3-4 */
  exDividendDate: string
  /** @deprecated 移交 G3-4 */
  totalDividend: number
  /** @deprecated 移交 G3-4 */
  payoutRatio: number
  /** @deprecated 移交 G3-5 长期未收回检查表 */
  dividendReceivable: number
  /** @deprecated 移交 G3-5 */
  receivedAmount: number
  /** @deprecated 移交 G3-5 */
  netReceivable: number
  /** @deprecated 移交 G3-5 */
  receiptDate: string
  /** @deprecated 移交 G3-5 */
  receiptMethod: string
  /** @deprecated 移交 G3-5 */
  isOverdue: string
  /** @deprecated 移交 G3-5 */
  overdueDays: number
}

export interface G3DetailColumn {
  prop: keyof DividendDetailRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'invest-type' | 'method'
}

export interface G3DetailSegment {
  key: string
  label: string
  columns: G3DetailColumn[]
}

// ─── Column Constants ────────────────────────────────────────────────────────

export const G3_INVEST_TYPE_OPTIONS: { value: G3InvestType; label: string }[] = [
  { value: 'long-term-equity', label: '长期股权投资' },
  { value: 'other-equity', label: '其他权益工具投资' },
]

export const G3_ACCOUNTING_METHOD_OPTIONS: { value: G3AccountingMethod; label: string }[] = [
  { value: 'cost', label: '成本法' },
  { value: 'equity', label: '权益法' },
]

/** 4区段列配置 */
export const G3_DETAIL_SEGMENTS: G3DetailSegment[] = [
  {
    key: 'investee',
    label: '被投资方信息',
    columns: [
      { prop: 'seq', label: '序号', width: 60, formula: true },
      { prop: 'investeeName', label: '被投资方名称', width: 160, type: 'text' },
      { prop: 'socialCreditCode', label: '统一社会信用代码', width: 180, type: 'text' },
      { prop: 'registeredCapital', label: '注册资本', width: 130, type: 'number' },
      { prop: 'industry', label: '行业', width: 120, type: 'text' },
      { prop: 'investType', label: '投资类型', width: 140, type: 'invest-type' },
      { prop: 'initialCost', label: '初始投资成本', width: 130, type: 'number' },
      { prop: 'investDate', label: '投资日期', width: 130, type: 'date' },
    ],
  },
  {
    key: 'shareholding',
    label: '持股明细',
    columns: [
      { prop: 'sharesHeld', label: '持股数量(股)', width: 130, type: 'number' },
      { prop: 'shareholdingRatio', label: '持股比例(%)', width: 120, type: 'number' },
      { prop: 'investeeNetProfit', label: '被投资方净利润', width: 140, type: 'number' },
      { prop: 'investeeNetAssets', label: '被投资方净资产', width: 140, type: 'number' },
      { prop: 'equityShare', label: '权益份额', width: 130, type: 'number', formula: true },
      { prop: 'bookValue', label: '账面值', width: 120, type: 'number' },
      { prop: 'accountingMethod', label: '核算方法', width: 110, type: 'method' },
      { prop: 'isListed', label: '是否上市', width: 100, type: 'text' },
      { prop: 'listingCode', label: '上市代码', width: 120, type: 'text' },
    ],
  },
  {
    key: 'dividend',
    label: '分红方案',
    columns: [
      { prop: 'resolutionDate', label: '决议日期', width: 130, type: 'date' },
      { prop: 'dividendPlan', label: '分红方案描述', width: 160, type: 'text' },
      { prop: 'dps', label: '每股股利(元)', width: 120, type: 'number' },
      { prop: 'declarationDate', label: '宣告日', width: 130, type: 'date' },
      { prop: 'recordDate', label: '股权登记日', width: 130, type: 'date' },
      { prop: 'exDividendDate', label: '除权日', width: 130, type: 'date' },
      { prop: 'totalDividend', label: '分红总额', width: 130, type: 'number', formula: true },
      { prop: 'payoutRatio', label: '实际分红率(%)', width: 130, type: 'number', formula: true },
    ],
  },
  {
    key: 'receivable',
    label: '应收核算',
    columns: [
      { prop: 'dividendReceivable', label: '应收股利', width: 130, type: 'number', formula: true },
      { prop: 'receivedAmount', label: '已收金额', width: 120, type: 'number' },
      { prop: 'netReceivable', label: '期末应收', width: 120, type: 'number', formula: true },
      { prop: 'receiptDate', label: '收款日期', width: 130, type: 'date' },
      { prop: 'receiptMethod', label: '收款方式', width: 120, type: 'text' },
      { prop: 'isOverdue', label: '是否逾期', width: 100, type: 'text' },
      { prop: 'overdueDays', label: '逾期天数', width: 110, type: 'number', formula: true },
      { prop: 'remark', label: '备注', width: 140, type: 'text' },
    ],
  },
]

// Convenience exports (alias by segment)
export const SEGMENT_INVESTEE_COLS = G3_DETAIL_SEGMENTS[0].columns
export const SEGMENT_SHAREHOLDING_COLS = G3_DETAIL_SEGMENTS[1].columns
export const SEGMENT_DIVIDEND_COLS = G3_DETAIL_SEGMENTS[2].columns
export const SEGMENT_RECEIVABLE_COLS = G3_DETAIL_SEGMENTS[3].columns

// ─── Storage Key ─────────────────────────────────────────────────────────────

const DATA_KEY = G3_DETAIL_ROWS_KEY

// ─── Subtotal Fields ─────────────────────────────────────────────────────────

/** 合计行（受管列 + 旧兼容列） */
const SUM_FIELDS = [
  // 受管：20 个 editable 金额列
  'bvUnauditedOpening', 'bvUnauditedIncrease', 'bvUnauditedDecrease',
  'bvPriorAdjAje', 'bvPriorAdjRje',
  'bvAjeIncrease', 'bvAjeDecrease', 'bvRjeIncrease', 'bvRjeDecrease',
  'impUnauditedOpening', 'impUnauditedIncrease', 'impUnauditedDecrease',
  'impPriorAdjAje', 'impPriorAdjRje',
  'impAjeIncrease', 'impAjeDecrease', 'impRjeIncrease', 'impRjeDecrease',
  // 受管：12 个公式列（也要汇总 —— 模板小计行逐列 SUM）
  'bvUnauditedClosing', 'bvAuditedOpening', 'bvAuditedIncrease', 'bvAuditedDecrease', 'bvAuditedClosing',
  'impUnauditedClosing', 'impAuditedOpening', 'impAuditedIncrease', 'impAuditedDecrease', 'impAuditedClosing',
  'netBookOpening', 'netBookClosing',
  // 旧兼容
  'initialCost', 'totalDividend', 'dividendReceivable', 'receivedAmount', 'netReceivable',
] as const

export type G3DetailTotals = Record<(typeof SUM_FIELDS)[number], number>

// ─── Helpers ─────────────────────────────────────────────────────────────────

function emptyRow(id: string, seq: number): DividendDetailRow {
  return {
    id,
    seq,
    // 受管列（按模板列序 A→AG）
    agingCategory: 'within_one_year',
    investeeName: '',
    // 账面余额 - 未审数
    bvUnauditedOpening: 0, bvUnauditedIncrease: 0, bvUnauditedDecrease: 0, bvUnauditedClosing: 0,
    // 账面余额 - 期初调整
    bvPriorAdjAje: 0, bvPriorAdjRje: 0,
    // 账面余额 - 账项调整
    bvAjeIncrease: 0, bvAjeDecrease: 0,
    // 账面余额 - 重分类调整
    bvRjeIncrease: 0, bvRjeDecrease: 0,
    // 账面余额 - 审定数
    bvAuditedOpening: 0, bvAuditedIncrease: 0, bvAuditedDecrease: 0, bvAuditedClosing: 0,
    // 减值准备 - 未审数
    impUnauditedOpening: 0, impUnauditedIncrease: 0, impUnauditedDecrease: 0, impUnauditedClosing: 0,
    // 减值准备 - 期初调整
    impPriorAdjAje: 0, impPriorAdjRje: 0,
    // 减值准备 - 账项调整
    impAjeIncrease: 0, impAjeDecrease: 0,
    // 减值准备 - 重分类调整
    impRjeIncrease: 0, impRjeDecrease: 0,
    // 减值准备 - 审定数
    impAuditedOpening: 0, impAuditedIncrease: 0, impAuditedDecrease: 0, impAuditedClosing: 0,
    // 账面价值
    netBookOpening: 0, netBookClosing: 0,
    // 备注
    remark: '',
    // 非受管（旧字段，保留兼容）
    socialCreditCode: '', registeredCapital: 0, industry: '', investType: 'long-term-equity',
    initialCost: 0, investDate: '',
    sharesHeld: 0, shareholdingRatio: 0, investeeNetProfit: 0, investeeNetAssets: 0,
    equityShare: 0, bookValue: 0, accountingMethod: 'cost', isListed: '', listingCode: '',
    resolutionDate: '', dividendPlan: '', dps: 0, declarationDate: '', recordDate: '',
    exDividendDate: '', totalDividend: 0, payoutRatio: 0,
    dividendReceivable: 0, receivedAmount: 0, netReceivable: 0, receiptDate: '',
    receiptMethod: '', isOverdue: '', overdueDays: 0,
  }
}

/**
 * 公式链求解 —— 12 个模板公式列 + 旧非受管公式（兼容）。
 *
 * 模板公式（逐行同形）：
 *   F = C+D-E       P = M+N-O       T = Q+R-S       AD = AA+AB-AC
 *   M = C+G+H       N = D+I+K       O = E+J+L
 *   AA = Q+U+V      AB = R+W+Y      AC = S+X+Z
 *   AE = M-AA       AF = P-AD
 */
function enrich(r: DividendDetailRow): DividendDetailRow {
  // ── 受管公式列 ──
  const C = parseNum(r.bvUnauditedOpening)
  const D = parseNum(r.bvUnauditedIncrease)
  const E = parseNum(r.bvUnauditedDecrease)
  const G = parseNum(r.bvPriorAdjAje)
  const H = parseNum(r.bvPriorAdjRje)
  const I = parseNum(r.bvAjeIncrease)
  const J = parseNum(r.bvAjeDecrease)
  const K = parseNum(r.bvRjeIncrease)
  const L = parseNum(r.bvRjeDecrease)

  const Q = parseNum(r.impUnauditedOpening)
  const R = parseNum(r.impUnauditedIncrease)
  const S = parseNum(r.impUnauditedDecrease)
  const U = parseNum(r.impPriorAdjAje)
  const V = parseNum(r.impPriorAdjRje)
  const W = parseNum(r.impAjeIncrease)
  const X = parseNum(r.impAjeDecrease)
  const Y = parseNum(r.impRjeIncrease)
  const Z = parseNum(r.impRjeDecrease)

  const F = C + D - E                    // 未审期末
  const M = C + G + H                    // 审定期初
  const N = D + I + K                    // 审定增加
  const O = E + J + L                    // 审定减少
  const P = M + N - O                    // 审定期末
  const T = Q + R - S                    // 减值未审期末
  const AA = Q + U + V                   // 减值审定期初
  const AB = R + W + Y                   // 减值审定增加
  const AC = S + X + Z                   // 减值审定减少
  const AD = AA + AB - AC                // 减值审定期末
  const AE = M - AA                      // 账面价值期初
  const AF = P - AD                      // 账面价值期末

  // ── 旧非受管公式（保留兼容 G3TabDetail 消费方）──
  const sharesHeld = parseNum(r.sharesHeld)
  const shareholdingRatio = parseNum(r.shareholdingRatio)
  const investeeNetAssets = parseNum(r.investeeNetAssets)
  const investeeNetProfit = parseNum(r.investeeNetProfit)
  const dps = parseNum(r.dps)
  const receivedAmount = parseNum(r.receivedAmount)
  const equityShare = calcEquityShare(investeeNetAssets, shareholdingRatio)
  const totalDividend = calcDividend(sharesHeld, dps)
  const payoutRatio = calcPayoutRatio(totalDividend, investeeNetProfit)
  const dividendReceivable = calcDividend(sharesHeld, dps)
  const netReceivable = calcNetReceivable(dividendReceivable, receivedAmount)
  const overdueDays = r.recordDate ? calcOverdueDays(new Date(), new Date(r.recordDate)) : 0
  const isOverdue = overdueDays > 0 ? '是' : '否'

  return {
    ...r,
    // 受管公式列
    bvUnauditedClosing: F,
    bvAuditedOpening: M,
    bvAuditedIncrease: N,
    bvAuditedDecrease: O,
    bvAuditedClosing: P,
    impUnauditedClosing: T,
    impAuditedOpening: AA,
    impAuditedIncrease: AB,
    impAuditedDecrease: AC,
    impAuditedClosing: AD,
    netBookOpening: AE,
    netBookClosing: AF,
    // 旧非受管公式
    equityShare, totalDividend, payoutRatio,
    dividendReceivable, netReceivable, overdueDays, isOverdue,
  }
}

/**
 * G3-2 明细行的行身份铸造点（本文件唯一）。前缀 `g3d` 内联理由同 `useG1Detail.genRowId`。
 */
function genRowId(): string {
  return `g3d-${mintRowIdSuffix()}`
}

/**
 * 载入并解析行，同时铸造稳定行身份。
 *
 * 🔴 Task 7（BP-7 + Req 1.3）：改造前两层病灶（与 `useG1Detail.loadRows` 同型）——
 * ① 原写法 `p.id ?? String(i + 1)` 用**数组下标**当身份（删中间一行后其后全部前移）；
 * ② 空表兜底 `emptyRow('1', 1)` 让不同底稿的第一行 id 都是 `'1'`；
 * ③ 新增行原写法 `` `row-${Date.now()}` `` 无随机后缀，同毫秒连加两行撞 id。
 * 现统一走 `resolveStableRowIds(list, genRowId, stats)`；`row-<ts>` 形态**不无条件重铸**。
 */
function loadRows(
  map: Map<string, ChecklistResponse>,
  stats?: RowIdentityMintStats,
): DividendDetailRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  const fallback = () => {
    if (stats) stats.minted += 1
    return [enrich(emptyRow(genRowId(), 1))]
  }
  if (!raw) return fallback()
  try {
    const parsed = JSON.parse(raw) as Partial<DividendDetailRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return fallback()
    const ids = resolveStableRowIds(parsed, genRowId, stats)
    return parsed.map((p, i) =>
      enrich({ ...emptyRow(ids[i], p.seq ?? i + 1), ...p, id: ids[i] }),
    )
  } catch {
    return fallback()
  }
}

function sumRows(list: DividendDetailRow[]): G3DetailTotals {
  const out = {} as G3DetailTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

/** 判断行是否逾期（用于橙色高亮） */
export function isRowOverdue(row: DividendDetailRow): boolean {
  return row.overdueDays > 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG3Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  // 🔴 Task 7 TDZ 坑：不能在 ref 初始化表达式里调 persistAll（见 useG1Detail 同名注释）。
  const initialMint = createMintStats()
  const rows = ref<DividendDetailRow[]>(loadRows(opts.allResponses.value, initialMint))
  /** 当前区段 */
  const segment = ref<string>(G3_DETAIL_SEGMENTS[0].key)

  /**
   * 载入并在**铸造了新身份时立即回写**（理由同 `useG1Detail.loadRowsAndPersistIfMinted`）。
   */
  function loadRowsAndPersistIfMinted(): void {
    const stats = createMintStats()
    rows.value = loadRows(opts.allResponses.value, stats)
    if (stats.minted > 0) persistAll()
  }

  function loadAll() {
    loadRowsAndPersistIfMinted()
  }

  // allResponses 异步加载完成后回填
  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) loadRowsAndPersistIfMinted()
    },
  )

  /** 总计行 */
  const totals = computed<G3DetailTotals>(() => sumRows(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  // 🔴 Task 7：首次载入若铸了身份，在此补回写（TDZ 坑同 useG1Detail 的 initialMint）。
  if (initialMint.minted > 0) persistAll()

  function updateRow(id: string, patch: Partial<DividendDetailRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '被投资方名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        // 🔴 Task 7：原 `row-${Date.now()}` 无随机后缀 ⇒ 同毫秒连加两行会撞 id。
        enrich({ ...emptyRow(genRowId(), seq), investeeName: value }),
      ]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  return {
    segments: G3_DETAIL_SEGMENTS,
    segment,
    rows,
    totals,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    isRowOverdue,
  }
}

export default useG3Detail
