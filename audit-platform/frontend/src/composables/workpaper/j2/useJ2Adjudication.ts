/**
 * useJ2Adjudication — J2-1 审定表三区块逻辑
 *
 * J2-1审定表含三区块：
 * 1. 设定受益计划（离职后福利）— DBO净负债
 * 2. 其他长期职工福利 — 净负债
 * 3. 辞退福利
 *
 * 每区块含：期初(未审/调整/审定) + 期末(未审/调整/审定) + 变动额/率 + 原因分析
 * 合计行 = 三区块之和
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 2.2-2.6, 3.1-3.3
 */
import { ref, computed, type Ref } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  parseNum,
} from './useJ2FormulaEngine'

export interface AdjudicationRow {
  label: string
  // 期初
  beginUnadj: number
  beginAje: number
  beginAudited: number
  // 期末
  endUnadj: number
  endAje: number
  endAudited: number
  // 变动（本期未审vs上期审定）
  changeAmountUnadj: number
  changeRateUnadj: number
  // 变动（本期审定vs上期审定）
  changeAmountAudited: number
  changeRateAudited: number
  // 原因分析
  reasonAnalysis: string
}

export interface J2AdjudicationOptions {
  wpId: string
  projectId: string
}

export function useJ2Adjudication(options: J2AdjudicationOptions) {
  // 三区块行数据
  const definedBenefitRow: Ref<AdjudicationRow> = ref(createEmptyRow('设定受益计划'))
  const otherLongTermRow: Ref<AdjudicationRow> = ref(createEmptyRow('其他长期职工福利'))
  const terminationRow: Ref<AdjudicationRow> = ref(createEmptyRow('辞退福利'))

  // 减：一年内到期
  const withinOneYearRow: Ref<AdjudicationRow> = ref(createEmptyRow('减：一年内支付的长期应付职工薪酬'))

  function createEmptyRow(label: string): AdjudicationRow {
    return {
      label,
      beginUnadj: 0, beginAje: 0, beginAudited: 0,
      endUnadj: 0, endAje: 0, endAudited: 0,
      changeAmountUnadj: 0, changeRateUnadj: 0,
      changeAmountAudited: 0, changeRateAudited: 0,
      reasonAnalysis: '',
    }
  }

  // ── 公式计算 ──────────────────────────────────────────────────────────────

  function recalcRow(row: AdjudicationRow): AdjudicationRow {
    // 审定数 = 未审 + AJE
    row.beginAudited = calcAuditedAmount(row.beginUnadj, row.beginAje, 0)
    row.endAudited = calcAuditedAmount(row.endUnadj, row.endAje, 0)
    // 变动分析
    row.changeAmountUnadj = calcChangeAmount(row.endUnadj, row.beginAudited)
    row.changeRateUnadj = calcChangeRate(row.beginAudited, row.endUnadj)
    row.changeAmountAudited = calcChangeAmount(row.endAudited, row.beginAudited)
    row.changeRateAudited = calcChangeRate(row.beginAudited, row.endAudited)
    return row
  }

  function recalcAll() {
    recalcRow(definedBenefitRow.value)
    recalcRow(otherLongTermRow.value)
    recalcRow(terminationRow.value)
    recalcRow(withinOneYearRow.value)
  }

  // ── 合计行（自动计算） ────────────────────────────────────────────────────

  const totalRow = computed((): AdjudicationRow => {
    const rows = [definedBenefitRow.value, otherLongTermRow.value, terminationRow.value]
    const total: AdjudicationRow = {
      label: '合计',
      beginUnadj: calcSubtotal(rows.map(r => r.beginUnadj)),
      beginAje: calcSubtotal(rows.map(r => r.beginAje)),
      beginAudited: calcSubtotal(rows.map(r => r.beginAudited)),
      endUnadj: calcSubtotal(rows.map(r => r.endUnadj)),
      endAje: calcSubtotal(rows.map(r => r.endAje)),
      endAudited: calcSubtotal(rows.map(r => r.endAudited)),
      changeAmountUnadj: 0,
      changeRateUnadj: 0,
      changeAmountAudited: 0,
      changeRateAudited: 0,
      reasonAnalysis: '',
    }
    total.changeAmountUnadj = calcChangeAmount(total.endUnadj, total.beginAudited)
    total.changeRateUnadj = calcChangeRate(total.beginAudited, total.endUnadj)
    total.changeAmountAudited = calcChangeAmount(total.endAudited, total.beginAudited)
    total.changeRateAudited = calcChangeRate(total.beginAudited, total.endAudited)
    return total
  })

  // 列报金额 = 合计 - 一年内到期
  const reportingAmount = computed(() => {
    return totalRow.value.endAudited - withinOneYearRow.value.endAudited
  })

  // ── 从htmlData加载 ─────────────────────────────────────────────────────

  function loadFromHtmlData(data: Record<string, unknown>) {
    if (data.adjudication && typeof data.adjudication === 'object') {
      const adj = data.adjudication as Record<string, unknown>
      if (adj.definedBenefit) Object.assign(definedBenefitRow.value, adj.definedBenefit)
      if (adj.otherLongTerm) Object.assign(otherLongTermRow.value, adj.otherLongTerm)
      if (adj.termination) Object.assign(terminationRow.value, adj.termination)
      if (adj.withinOneYear) Object.assign(withinOneYearRow.value, adj.withinOneYear)
    }
    recalcAll()
  }

  return {
    definedBenefitRow,
    otherLongTermRow,
    terminationRow,
    withinOneYearRow,
    totalRow,
    reportingAmount,
    recalcRow,
    recalcAll,
    loadFromHtmlData,
  }
}
