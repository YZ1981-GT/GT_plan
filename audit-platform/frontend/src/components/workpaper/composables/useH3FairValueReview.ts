/**
 * useH3FairValueReview — H3-8 公允价值复核 composable
 *
 * 四区域（评估师信息/方法假设/复核计算/假设挑战）+ 15公式
 * + 独立测算 + 范围判断 + 交叉验证H3-1
 *
 * 字段命名与 H3TabFairValueReview.vue 模板保持一致（firm/appraisalValue/rentAssumption/withinRange/reasonableness）。
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.13
 * Requirements: 9.1-9.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AppraiserInfo {
  firm: string
  qualification: string
  independence: string
}

export interface FairValueCalcRow {
  rowId: string
  assetName: string
  appraisalValue: number      // 评估值
  bookValue: number           // 账面值
  difference: number          // 差异（公式）
  differenceRate: number      // 差异率%（公式）
  marketRef: number           // 市场参考价
  discountRate: number        // 收益法折现率
  rentAssumption: number      // 收益法租金假设
  capRate: number             // 资本化率
  independentCalc: number     // 独立测算值（公式）
  indVsAssessDiff: number     // 独立vs评估差异（公式）
  acceptableRange: number     // 可接受范围(±10%)
  withinRange: boolean        // 是否在范围内
  conclusion: string
  remark: string
}

export interface AssumptionChallengeRow {
  rowId: string
  assumption: string          // 关键假设
  appraiserValue: string      // 评估师假设值
  auditorJudgment: string     // 审计师独立判断
  difference: string          // 差异
  reasonableness: string      // 合理性结论
}

const ITEM_APPRAISER = 'H3-8-appraiser'
const ITEM_METHOD = 'H3-8-method'
const ITEM_CALC_ROWS = 'H3-8-calc-rows'
const ITEM_CHALLENGE = 'H3-8-challenge-rows'

export function useH3FairValueReview(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const appraiserInfo = ref<AppraiserInfo>({ firm: '', qualification: '', independence: '' })
  const methodText = ref<string>('')
  const calcRows = ref<FairValueCalcRow[]>([])
  const challengeRows = ref<AssumptionChallengeRow[]>([])

  function loadData(): void {
    const ai = getValue(ITEM_APPRAISER)
    if (ai && typeof ai === 'object') appraiserInfo.value = { ...appraiserInfo.value, ...ai }
    const mt = getValue(ITEM_METHOD)
    methodText.value = typeof mt === 'string' ? mt : (mt?.text ?? '')
    const rawCalc = getValue(ITEM_CALC_ROWS)
    calcRows.value = Array.isArray(rawCalc) ? rawCalc.map(_normCalc) : []
    const rawChallenge = getValue(ITEM_CHALLENGE)
    challengeRows.value = Array.isArray(rawChallenge) ? rawChallenge.map(_normChallenge) : []
  }

  function _normCalc(raw: any): FairValueCalcRow {
    const appraisal = Number(raw.appraisalValue ?? raw.assessedValue) || 0
    const book = Number(raw.bookValue) || 0
    const diff = appraisal - book
    const rate = book !== 0 ? (diff / book) * 100 : 0
    const rent = Number(raw.rentAssumption ?? raw.rentalAssumption) || 0
    const cap = Number(raw.capRate) || 0.05
    const growth = 0.02 // default growth rate
    const indCalc = cap > growth ? (rent * 12) / (cap - growth) : 0
    const acceptable = appraisal * 0.1
    const indDiff = indCalc - appraisal
    return {
      rowId: raw.rowId ?? `fv-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      appraisalValue: appraisal,
      bookValue: book,
      difference: diff,
      differenceRate: rate,
      marketRef: Number(raw.marketRef) || 0,
      discountRate: Number(raw.discountRate) || 0,
      rentAssumption: rent,
      capRate: cap,
      independentCalc: indCalc,
      indVsAssessDiff: indDiff,
      acceptableRange: acceptable,
      withinRange: Math.abs(indDiff) <= acceptable,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normChallenge(raw: any): AssumptionChallengeRow {
    return {
      rowId: raw.rowId ?? `ch-${Math.random().toString(36).slice(2, 8)}`,
      assumption: raw.assumption ?? '',
      appraiserValue: raw.appraiserValue ?? '',
      auditorJudgment: raw.auditorJudgment ?? '',
      difference: raw.difference ?? raw.diff ?? '',
      reasonableness: raw.reasonableness ?? raw.reasonability ?? '',
    }
  }

  /** 差异率>20%的行 */
  const highDiffRows = computed(() => calcRows.value.filter((r) => Math.abs(r.differenceRate) > 20))
  /** 不在范围内的行 */
  const outOfRangeRows = computed(() => calcRows.value.filter((r) => !r.withinRange))
  /** 公允价值变动合计（→H3-1交叉验证） */
  const fairValueChangeTotal = computed(() => calcSubtotal(calcRows.value.map((r) => r.difference)))

  /** 评估师信息变更（组件已 v-model 就地修改 appraiserInfo，此处持久化） */
  function updateAppraiserInfo(_info?: any): void {
    setValue(ITEM_APPRAISER, appraiserInfo.value)
  }

  /** 方法文本变更 */
  function updateMethod(text: string): void {
    methodText.value = text ?? ''
    setValue(ITEM_METHOD, methodText.value)
  }

  function addCalcRow(assetName?: string): void {
    calcRows.value.push(_normCalc({ assetName: assetName ?? '', rowId: `fv-${Date.now()}` }))
    setValue(ITEM_CALC_ROWS, calcRows.value)
  }

  function removeCalcRow(index: number): void {
    calcRows.value.splice(index, 1)
    setValue(ITEM_CALC_ROWS, calcRows.value)
  }

  /** 复核计算行变更：组件已 v-model 就地修改，重算公式列并持久化（组件调用 updateCalcRow(index, row)） */
  function updateCalcRow(index: number, _row?: any): void {
    const row = calcRows.value[index]
    if (!row) return
    const recalced = _normCalc({ ...row })
    Object.assign(row, recalced)
    setValue(ITEM_CALC_ROWS, calcRows.value)
  }

  function addChallengeRow(): void {
    challengeRows.value.push(_normChallenge({}))
    setValue(ITEM_CHALLENGE, challengeRows.value)
  }

  /** 假设挑战行变更：组件已 v-model 就地修改，持久化（组件调用 updateChallengeRow(index, row)） */
  function updateChallengeRow(index: number, _row?: any): void {
    if (!challengeRows.value[index]) return
    setValue(ITEM_CHALLENGE, challengeRows.value)
  }

  watch(allResponses, () => loadData(), { immediate: true })

  return {
    appraiserInfo, methodText, calcRows, challengeRows,
    // reviewCalcRows 为组件模板使用的别名（同 calcRows 引用）
    reviewCalcRows: calcRows,
    highDiffRows, outOfRangeRows, fairValueChangeTotal,
    updateAppraiserInfo, updateMethod,
    addCalcRow, removeCalcRow, updateCalcRow,
    addChallengeRow, updateChallengeRow, loadData,
  }
}

export default useH3FairValueReview
