/**
 * 对拍适配器：契约 store item → 前端「一行录入 → 算完的一行」
 * （spec oo-writeback-template-parity-closure R2.4，design §3.3）。
 *
 * 每个适配器调前端真实的行计算函数（必要时已从 composable 导出 / 外提为纯函数），不在这里重写公式。
 * raw 是 store 里存的行形状（字段名 = 契约字段名）；返回前端算完派生列后的一行。
 * 契约字段名与前端不同的 store item 不在这里翻译（R3 任务 9 改契约），登记在例外表的未覆盖清单。
 */
import * as d1BadDebt from '../../composables/useD1BadDebt'
import * as d1Category from '../../composables/useD1DetailCategory'
import * as d1Customer from '../../composables/useD1DetailCustomer'
import * as d1Ecl from '../../composables/useD1EclCalc'
import * as d1Interest from '../../composables/useD1InterestCheck'
import * as d1Memo from '../../composables/useD1MemoReconciliation'
import * as d1RelatedParty from '../../composables/useD1RelatedPartyCheck'
import * as d2BadDebt from '../../composables/useD2BadDebt'
import * as d2Detail from '../../composables/useD2Detail'
import * as d2Ecl from '../../composables/useD2Ecl'
import * as d2RelatedParty from '../../composables/useD2RelatedParty'
import * as d3Detail from '../../composables/useD3Detail'
import * as d3RelatedParty from '../../composables/useD3RelatedParty'
import * as d4Revenue from '../../composables/useD4RevenueDetail'
import * as d5Detail from '../../composables/useD5Detail'
import * as d5FairValue from '../../composables/useD5FairValue'
import * as d6Detail from '../../composables/useD6Detail'
import * as d6Ecl from '../../composables/useD6EclCalculation'
import * as d6Impairment from '../../composables/useD6ImpairmentDetail'
import * as d6RelatedParty from '../../composables/useD6RelatedParty'
import * as d7Detail from '../../composables/useD7Detail'
import * as d7RelatedParty from '../../composables/useD7RelatedParty'
import * as e1CashDetail from '../../composables/useE1CashDetail'
import * as e1Digital from '../../e1/e1DigitalRowCalc'
import * as f1RelatedParty from '../../composables/useF1RelatedParty'
import * as f2Impairment from '../../composables/useF2ContractCostImpairmentFormulas'
import * as f2Detail from '../../composables/useF2DetailSheet'
import * as f2Obsolete from '../../composables/useF2ObsoleteInventoryFormulas'
import * as f2Stocktake from '../../f2/stocktake/f2StocktakeRowCalc'
import * as f3Interest from '../../composables/useF3InterestCalc'
import * as f4Adjudication from '../../composables/useF4Adjudication'
import * as f4RelatedParty from '../../composables/useF4RelatedParty'
import * as f5Rollforward from '../../composables/useF5CostRollforward'
import { buildG13CategorySkeleton } from '../../composables/g13CategorySkeleton'
import { G13_SKELETON_ROW_KEYS, mergeSkeletonOverrides } from '../../composables/g13SkeletonStore'
import { G14_LINE_ITEMS } from '../../composables/g14Constants'
import * as g1Detail from '../../composables/useG1Detail'
import * as g2Detail from '../../composables/useG2Detail'
import * as g3Detail from '../../composables/useG3Detail'
import * as g8Detail from '../../composables/useG8Detail'
import * as g9Detail from '../../composables/useG9Detail'
import * as g10Detail from '../../composables/useG10Detail'
import * as g11Detail from '../../composables/useG11DetailAnalysis'
import * as g14Detail from '../../composables/useG14Detail'
import * as h1Disposal from '../../composables/useH1DisposalCheck'
import * as h2Detail from '../../composables/useH2Detail'
import * as h4Detail from '../../composables/useH4Detail'
import * as h5Detail from '../../composables/useH5Detail'
import * as h6Detail from '../../composables/useH6Detail'
import * as h8Detail from '../../composables/useH8Detail'
import * as h9Detail from '../../composables/useH9Detail'
import * as l1FormData from '@/composables/useL1FormData'
import * as l4FinLiab from '../../composables/useL4FinLiabRows'
import * as l5Detail from '../../composables/useL5Detail'
import * as l6Detail from '../../composables/useL6Detail'
import * as l7Detail from '../../composables/useL7Detail'
import * as l8Detail from '../../composables/useL8Detail'

export type ParityRow = Record<string, unknown>

export interface ParityContext {
  /** 样本序号（0 起） */
  sample: number
  /** 固定种子随机数 */
  rand: () => number
}

export interface ParityAdapter {
  /** 前端实现位置（报错时提示） */
  source: string
  /** 一行录入 → 前端算完的一行 */
  compute: (raw: ParityRow, ctx: ParityContext) => ParityRow
  /** 样本预处理（补行键、造相等 / 差一分的边界样本），在 compute 之前原地改 raw */
  prepare?: (raw: ParityRow, ctx: ParityContext) => void
}

/** 空行底板 + 录入（嵌套对象逐键合并，数组整替）；底板深拷贝，不改工厂返回值 */
function merged<T>(base: T, raw: ParityRow): T {
  const out = JSON.parse(JSON.stringify(base)) as Record<string, unknown>
  for (const [k, v] of Object.entries(raw)) {
    const cur = out[k]
    const bothObjects = v !== null && typeof v === 'object' && !Array.isArray(v)
      && cur !== null && typeof cur === 'object' && !Array.isArray(cur)
    out[k] = bothObjects ? { ...(cur as object), ...(v as object) } : v
  }
  return out as T
}

/** 全 0 底板（前端无导出工厂、行计算又不容错空值时用） */
function zeros(...keys: string[]): ParityRow {
  return Object.fromEntries(keys.map((k) => [k, 0]))
}

const asRow = (v: unknown): ParityRow => v as ParityRow

const D1_BAD_DEBT_KEYS = [
  'priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited', 'currentProvision', 'currentRecovery',
  'currentReversal', 'currentWriteOff', 'currentOther', 'currentUnadjusted', 'currentAje', 'currentRje',
  'currentAudited',
]
const D1_CATEGORY_KEYS = [
  'priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited', 'currentIncrease', 'currentDecrease',
  'currentUnadjusted', 'currentAje', 'currentRje', 'currentAudited',
]
const L7_KEYS = [
  'beginUnadjusted', 'beginAje', 'beginRje', 'beginAudited', 'ajeIncrease', 'rjeIncrease', 'endAjeIncrease',
  'endRjeDecrease', 'endAjeDecrease', 'endRjeIncrease', 'endUnadjusted', 'endAje', 'endRje', 'endAudited',
]
/** 期末日（D1-7 年初余额、D5-4 计量日默认值用） */
const PERIOD_END = '2025-12-31'

/** 金额两位小数 */
const cents = (x: number): number => Math.round(x * 100) / 100

/** 核对列边界样本：让两侧相等（差 0）或差一分；其余样本保持随机 */
function nudgeEqual(ctx: ParityContext, target: number): number | null {
  const mode = ctx.sample % 4
  if (mode === 0) return cents(target)
  if (mode === 1) return cents(target + 0.01)
  return null
}

export const PARITY_ADAPTERS: Readonly<Record<string, ParityAdapter>> = {
  'D1-bd-individual-rows': {
    source: 'useD1BadDebt.recalcRow',
    compute: (raw) => asRow(d1BadDebt.recalcRow(merged(zeros(...D1_BAD_DEBT_KEYS), raw) as never)),
  },
  'D1-bd-portfolio-rows': {
    source: 'useD1BadDebt.recalcRow',
    compute: (raw) => asRow(d1BadDebt.recalcRow(merged(zeros(...D1_BAD_DEBT_KEYS), raw) as never)),
  },
  'D1-cat-rows': {
    source: 'useD1DetailCategory.recalcRow',
    compute: (raw) => asRow(d1Category.recalcRow(merged(zeros(...D1_CATEGORY_KEYS), raw) as never)),
  },
  'D1-cust-rows': {
    source: 'useD1DetailCustomer.recalcRow',
    compute: (raw) => asRow(d1Customer.recalcRow(merged(d1Customer.createEmptyRow(), raw))),
  },
  'D1-ecl-individual-rows': {
    source: 'useD1EclCalc.deserializeRows',
    compute: (raw) => asRow(d1Ecl.deserializeRows(JSON.stringify([raw]))[0]),
  },
  'D1-ecl-portfolio-rows': {
    source: 'useD1EclCalc.deserializeRows',
    compute: (raw) => asRow(d1Ecl.deserializeRows(JSON.stringify([raw]))[0]),
  },
  'D1-interest-rows': {
    source: 'useD1InterestCheck.deserializeRow',
    compute: (raw) => asRow(d1Interest.deserializeRow(raw)),
  },
  'D1-memo-rows': {
    source: 'useD1MemoReconciliation.deriveMemoRow',
    compute: (raw) => asRow(d1Memo.deriveMemoRow(merged(d1Memo.emptyMemoRow('bank', 'dynamic'), raw), PERIOD_END)),
  },
  'D1-rp-rows': {
    source: 'useD1RelatedPartyCheck.deserializeRow',
    compute: (raw) => asRow(d1RelatedParty.deserializeRow(raw)),
  },
  'D2-bd-aging-rows': {
    source: 'useD2BadDebt.recalcRow',
    compute: (raw) => asRow(d2BadDebt.recalcRow(merged(d2BadDebt.createEmptySubRow('aging'), raw))),
  },
  'D2-bd-individual-rows': {
    source: 'useD2BadDebt.recalcRow',
    compute: (raw) => asRow(d2BadDebt.recalcRow(merged(d2BadDebt.createEmptySubRow('individual'), raw))),
  },
  'D2-detail-rows': {
    source: 'useD2Detail.recalcRow',
    compute: (raw) => asRow(d2Detail.recalcRow(merged(d2Detail.createEmptyRow(1, []), raw))),
  },
  'D2-ecl-single-rows': {
    source: 'useD2Ecl.recalcSingleRow',
    compute: (raw) => asRow(d2Ecl.recalcSingleRow(merged(d2Ecl.createEmptySingleRow(), raw))),
  },
  'D2-related-party-rows': {
    source: 'useD2RelatedParty.recalcRow',
    compute: (raw) => asRow(d2RelatedParty.recalcRow(merged(d2RelatedParty.createEmptyRow(), raw))),
  },
  'D3-det-rows': {
    source: 'useD3Detail.recalcRowFormulas',
    compute: (raw) => asRow(d3Detail.recalcRowFormulas(merged(d3Detail.createEmptyRow([]), raw))),
  },
  'D3-rp-rows': {
    source: 'useD3RelatedParty.normalizeD3RelatedPartyRow',
    compute: (raw) => asRow(d3RelatedParty.normalizeD3RelatedPartyRow(raw)),
  },
  'D4-2-rows': {
    source: 'useD4RevenueDetail.computeRow',
    compute: (raw) => asRow(d4Revenue.computeRow(merged<d4Revenue.StoredRevenueRow>({
      rowId: 'parity', product: '', months: Array(12).fill(0), auditAdjustment: 0,
      priorUnadjusted: 0, priorAdjustment: 0, remark: '',
    }, raw))),
  },
  'D5-2-rows': {
    source: 'useD5Detail.recalcRow',
    compute: (raw) => asRow(d5Detail.recalcRow(merged(d5Detail.createEmptyRow(), raw))),
  },
  'D5-4-rows': {
    source: 'useD5FairValue.recalcFairValueRow',
    compute: (raw) => asRow(d5FairValue.recalcFairValueRow(
      merged(d5FairValue.createEmptyFairValueRow(PERIOD_END, 0), raw),
    )),
  },
  'D6-2-rows': {
    source: 'useD6Detail.recalcRow',
    compute: (raw) => asRow(d6Detail.recalcRow(merged(d6Detail.createEmptyRow(1), raw))),
  },
  'D6-3-rows': {
    source: 'useD6ImpairmentDetail.recalcImpairmentRow',
    compute: (raw) => asRow(d6Impairment.recalcImpairmentRow(merged(d6Impairment.createEmptyRow('single'), raw))),
  },
  'D6-5-rows': {
    source: 'useD6RelatedParty.recalcRelatedPartyRow',
    compute: (raw) => asRow(d6RelatedParty.recalcRelatedPartyRow(merged(d6RelatedParty.createEmptyRow(), raw))),
  },
  'D6-8-single-rows': {
    source: 'useD6EclCalculation.recalcSingleRow',
    compute: (raw) => asRow(d6Ecl.recalcSingleRow(merged(d6Ecl.createEmptySingleRow(), raw))),
  },
  'D7-2-rows': {
    source: 'useD7Detail.recalcRow',
    compute: (raw) => asRow(d7Detail.recalcRow(merged(d7Detail.createEmptyRow([]), raw))),
  },
  'D7-6-rows': {
    source: 'useD7RelatedParty.normalizeRow + recalcRow',
    compute: (raw) => asRow(d7RelatedParty.recalcRow(d7RelatedParty.normalizeRow(raw))),
  },
  'E1-cash-detail-rows': {
    source: 'useE1CashDetail.normalizeE1CashDetailRow',
    compute: (raw) => asRow(e1CashDetail.normalizeE1CashDetailRow(raw)),
  },
  'E1-digital-rows': {
    source: 'e1DigitalRowCalc.normalizeE1DigitalRow',
    compute: (raw) => asRow(e1Digital.normalizeE1DigitalRow(raw, 0)),
  },
  'F1-rp-rows': {
    source: 'useF1RelatedParty.normalizeRelatedPartyRow',
    compute: (raw) => asRow(f1RelatedParty.normalizeRelatedPartyRow(raw)),
  },
  'F2-6-rows': {
    source: 'useF2DetailSheet.enrichRow',
    compute: (raw) => asRow(f2Detail.enrichRow(merged(f2Detail.emptyRow('parity', []), raw), true, [])),
  },
  'F2-25-floor-rows': {
    source: 'f2StocktakeRowCalc.enrichStocktakeSampleRow',
    compute: (raw) => asRow(f2Stocktake.enrichStocktakeSampleRow(merged(f2Stocktake.emptyStocktakeSampleRow(), raw))),
  },
  'F2-25-rows': {
    source: 'f2StocktakeRowCalc.enrichStocktakeSampleRow',
    compute: (raw) => asRow(f2Stocktake.enrichStocktakeSampleRow(merged(f2Stocktake.emptyStocktakeSampleRow(), raw))),
  },
  'F2-26-after-rows': {
    source: 'f2StocktakeRowCalc.enrichStocktakeRollforwardRow（日后表）',
    compute: (raw) => asRow(f2Stocktake.enrichStocktakeRollforwardRow(
      merged(f2Stocktake.emptyStocktakeRollforwardRow(), raw), 'after',
    )),
  },
  'F2-48-rows': {
    source: 'useF2ObsoleteInventoryFormulas.enrichObsoleteItem',
    compute: (raw) => asRow(f2Obsolete.enrichObsoleteItem(merged(f2Obsolete.emptyObsoleteItem(), raw))),
  },
  'F2-57-rows': {
    source: 'useF2ContractCostImpairmentFormulas.enrichImpairmentProject',
    compute: (raw) => asRow(f2Impairment.enrichImpairmentProject(merged(f2Impairment.emptyImpairmentProject(), raw))),
  },
  'F3-4-rows': {
    source: 'useF3InterestCalc.safeParseInterestRows（载入：migrateRow + computeInterestRow）',
    compute: (raw) => asRow(f3Interest.safeParseInterestRows(JSON.stringify([raw]))[0]),
  },
  'F4-1-adj-nature-rows': {
    source: 'useF4Adjudication.migrateF4AdjRows + computeF4AdjudicationRow（性质区首行「货款」）',
    compute: (raw) => asRow(f4Adjudication.computeF4AdjudicationRow(
      f4Adjudication.migrateF4AdjRows(JSON.stringify([raw]), f4Adjudication.F4_NATURE_DEFAULTS)[0],
    )),
  },
  'F4-6-rows': {
    source: 'useF4RelatedParty.migrateF4RelatedPartyRows + computeRow',
    compute: (raw) => {
      const stored = f4RelatedParty.migrateF4RelatedPartyRows(JSON.stringify([raw]))[0]
        ?? f4RelatedParty.emptyF4RelatedPartyRow(1)
      return asRow(f4RelatedParty.computeRow(stored, 0))
    },
  },
  'F5-7-cost-rollforward': {
    source: 'useF5CostRollforward.computeF57RowViews',
    prepare: (raw, ctx) => {
      const inputRows = f5Rollforward.F57_ROW_DEFS.filter((d) => d.rowType !== 'formula')
      raw.rowKey = inputRows[ctx.sample % inputRows.length].rowKey
    },
    compute: (raw) => {
      const key = String(raw.rowKey)
      const stored = f5Rollforward.migrateStored({ rows: { [key]: raw } })
      return asRow(f5Rollforward.computeF57RowViews(stored).find((r) => r.rowKey === key))
    },
  },
  'G1-2-rows': {
    source: 'useG1Detail.enrichDetailRow',
    compute: (raw) => asRow(g1Detail.enrichDetailRow({ id: 'parity', seq: 1, ...raw } as never)),
  },
  'G2-2-detail-rows': {
    source: 'useG2Detail.safeParseRows + computeRow',
    compute: (raw) => asRow(g2Detail.computeRow(g2Detail.safeParseRows(JSON.stringify([raw]), [])[0], [])),
  },
  'G3-2-detail-rows': {
    source: 'useG3Detail.enrich',
    compute: (raw) => asRow(g3Detail.enrich(merged(g3Detail.emptyRow('parity', 1), raw))),
  },
  'G8-detail-rows': {
    source: 'useG8Detail.enrichG8DetailRow',
    compute: (raw) => asRow(g8Detail.enrichG8DetailRow({ rowId: 'parity', ...raw } as g8Detail.G8DetailRowInput, 1)),
  },
  'G9-detail-rows': {
    source: 'useG9Detail.enrichG9DetailRow',
    compute: (raw) => asRow(g9Detail.enrichG9DetailRow({ rowId: 'parity', ...raw }, 1)),
  },
  'G10-detail-rows': {
    source: 'useG10Detail.enrichG10DetailRow',
    compute: (raw) => asRow(g10Detail.enrichG10DetailRow({ rowId: 'parity', ...raw } as g10Detail.G10DetailRowInput, 1)),
  },
  'G11-detail-rows': {
    source: 'useG11DetailAnalysis.enrichRow（载入后 recomputeAll 按全表合计再算一遍）',
    compute: (raw) => {
      const loaded = g11Detail.enrichRow({ id: 'parity', ...raw }, 1)
      // 单行表：合计 = 本行（与 recomputeAll 同：占比 = 本行审定 / 合计，序号 = 位置）
      return asRow(g11Detail.enrichRow(loaded, 1, { current: loaded.currentAudited, prior: loaded.priorAudited }))
    },
  },
  'G13-detail-skeleton': {
    source: 'g13SkeletonStore.mergeSkeletonOverrides',
    prepare: (raw, ctx) => {
      raw.rowKey = G13_SKELETON_ROW_KEYS[ctx.sample % G13_SKELETON_ROW_KEYS.length]
      // 核对列 K = (J = D)：造「相等」与「差一分」样本
      const v = nudgeEqual(ctx, Number(raw.currentUnadjusted) + Number(raw.adjustment))
      if (v !== null) raw.periodFvChange = v
    },
    compute: (raw) => {
      const key = String(raw.rowKey)
      const stored = new Map([[key, { ...raw, rowKey: key, manualOverride: true }]])
      return asRow(mergeSkeletonOverrides(buildG13CategorySkeleton([]), stored).find((r) => r.rowKey === key))
    },
  },
  'G14-detail-rows': {
    source: 'useG14Detail.enrichRow',
    prepare: (raw, ctx) => {
      raw.rowKey = G14_LINE_ITEMS[ctx.sample % G14_LINE_ITEMS.length].rowKey
      // 核对列 L = (D = K)：造「相等」与「差一分」样本
      const k = Number(raw.currentProvision) - Number(raw.currentReversal)
      const v = nudgeEqual(ctx, k - Number(raw.currentAdjustment))
      if (v !== null) raw.currentUnadjusted = v
    },
    compute: (raw) => asRow(g14Detail.enrichRow({ ...raw, rowKey: String(raw.rowKey) })),
  },
  'H1-8-rows': {
    source: 'useH1DisposalCheck.normalizeH1DisposalRow',
    compute: (raw) => asRow(h1Disposal.normalizeH1DisposalRow(raw, 0)),
  },
  'H2-2-rows': {
    source: 'useH2Detail.normalizeH2DetailRows',
    compute: (raw) => asRow(h2Detail.normalizeH2DetailRows([raw])[0]),
  },
  'H4-2-rows': {
    source: 'useH4Detail.normalizeH4DetailRow',
    compute: (raw) => asRow(h4Detail.normalizeH4DetailRow(raw)),
  },
  'H5-2-rows': {
    source: 'useH5Detail.normalizeH5DetailRow',
    compute: (raw) => asRow(h5Detail.normalizeH5DetailRow(raw)),
  },
  'H6-2-rows': {
    source: 'useH6Detail.normalizeH6DetailRow',
    compute: (raw) => asRow(h6Detail.normalizeH6DetailRow(raw, 0)),
  },
  'H8-2-rows': {
    source: 'useH8Detail.normalizeH8DetailRow',
    compute: (raw) => asRow(h8Detail.normalizeH8DetailRow(raw)),
  },
  'H9-2-rows': {
    source: 'useH9Detail.normalizeH9DetailRow',
    compute: (raw) => asRow(h9Detail.normalizeH9DetailRow(raw)),
  },
  'L1-2-rows': {
    source: 'useL1FormData.recalcL1DetailRow',
    compute: (raw) => asRow(l1FormData.recalcL1DetailRow(merged(l1FormData.createEmptyDetailRow(), raw))),
  },
  'L4-3-rows': {
    source: 'useL4FinLiabRows.applyL4_3Formulas',
    compute: (raw) => asRow(l4FinLiab.applyL4_3Formulas(merged(l4FinLiab.createEmptyFinLiabRow(), raw))),
  },
  'L5-L5-2-rows': {
    source: 'useL5Detail.recalcL5DetailRow',
    compute: (raw) => asRow(l5Detail.recalcL5DetailRow(merged(l5Detail.createL5DetailRow(''), raw))),
  },
  'L6-L6-2-rows': {
    source: 'useL6Detail.readL6DetailRows',
    compute: (raw) => asRow(l6Detail.readL6DetailRows(
      new Map([[l6Detail.L6_DETAIL_ROWS_ITEM_ID, { remark: JSON.stringify([raw]) }]]),
    )[0]),
  },
  'L7-L7-2-full-data': {
    source: 'useL7Detail.computeL7DetailRow',
    compute: (raw) => asRow(l7Detail.computeL7DetailRow(merged(zeros(...L7_KEYS), raw) as never)),
  },
  'L8-2-full-data': {
    source: 'useL8Detail.computeL8DetailRows',
    compute: (raw) => asRow(l8Detail.computeL8DetailRows([merged(l8Detail.makeEmptyL8Row('l82det-parity', ''), raw)])[0]),
  },
}
