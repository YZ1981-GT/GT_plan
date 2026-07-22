/**

 * G10-5 公允价值测试跨表联动（纯函数）

 * G10-2 明细 ↔ G10-5 公允测试 ↔ G10-3 调整

 */

import { parseNum } from './useG10FormulaEngine'

import { G10_ACCOUNT_CODE } from './g10Constants'

import { inferG10AdjudicationRowKey } from './g10AccountMatch'

import {
  aggregateG10AdjustmentAjeRjeByRow,
} from './g10AdjStorage'
import { commitG10AdjustmentWritebackFromRows } from './g10CrossHelpers'

import type { ChecklistResponse } from './useF1FormData'



export const G10_ADJ_KEY = 'G10-aje-rows'

export const G10_FV_KEY = 'G10-fv-test-rows'

export const G10_DETAIL_KEY = 'G10-detail-rows'

export const G10_ADJ_WRITEBACK_OVERLAY_ID = 'G10-adj-writeback'



export const G10_FV_DIFF_THRESHOLD = 0.01



export interface G10PushAdjItem {

  summary: string

  /** 审定 − 未审；正数=负债公允价值上升 */

  amount: number

  liabilityName?: string

  liabilityType?: string

  indexRef?: string

  remark?: string

}



export function calcG10FairValueDiff(audited: number, unadjusted: number): number {

  return Math.round((parseNum(audited) - parseNum(unadjusted)) * 100) / 100

}



export function hasG10FairValueDifference(row: { fairValueDiff?: number; closingAuditedFV?: number; closingUnadjustedFV?: number }): boolean {

  const diff = row.fairValueDiff ?? calcG10FairValueDiff(row.closingAuditedFV ?? 0, row.closingUnadjustedFV ?? 0)

  return Math.abs(diff) > G10_FV_DIFF_THRESHOLD

}



export async function fetchG10PerformanceMateriality(projectId: string): Promise<number> {

  if (!projectId) return 0

  try {

    const { fetchPerformanceMateriality } = await import('./g6CrossHelpers')

    const pm = await fetchPerformanceMateriality(projectId)

    return pm && pm > 0 ? pm : 0

  } catch {

    return 0

  }

}



export interface G10FvDiffSelectInput {

  rows: Array<{

    liabilityName: string

    fairValueDiff: number

    closingAuditedFV: number

    closingUnadjustedFV: number

  }>

  performanceMateriality: number

  onlyMaterial?: boolean

}



export function selectG10FvDiffTargets(input: G10FvDiffSelectInput): {

  targets: G10FvDiffSelectInput['rows']

  skipped: Array<{ liabilityName: string; diff: number; reason: string }>

  threshold: number

} {

  const onlyMaterial = input.onlyMaterial !== false

  const pm = parseNum(input.performanceMateriality)

  const threshold = onlyMaterial ? (pm > 0 ? pm : G10_FV_DIFF_THRESHOLD) : G10_FV_DIFF_THRESHOLD

  const targets: G10FvDiffSelectInput['rows'] = []

  const skipped: Array<{ liabilityName: string; diff: number; reason: string }> = []

  for (const r of input.rows) {

    const diff = parseNum(r.fairValueDiff)

    if (Math.abs(diff) <= G10_FV_DIFF_THRESHOLD) continue

    if (Math.abs(diff) > threshold) {

      targets.push(r)

    } else {

      skipped.push({

        liabilityName: r.liabilityName || '未命名',

        diff,

        reason: pm > 0

          ? `|差异| ${Math.abs(diff).toFixed(2)} ≤ B15 ${pm.toFixed(2)}`

          : '低于阈值',

      })

    }

  }

  return { targets, skipped, threshold }

}



/** 差异相对未审合计的预警 */

export function calcG10FvDiffWarning(

  absDiff: number,

  unadjTotal: number,

  opts?: { softRatio?: number; hardRatio?: number; hardAbs?: number },

): 'none' | 'soft' | 'hard' {

  const softRatio = opts?.softRatio ?? 0.05

  const hardRatio = opts?.hardRatio ?? 0.2

  const hardAbs = opts?.hardAbs ?? 0

  if (Math.abs(absDiff) <= G10_FV_DIFF_THRESHOLD) return 'none'

  const base = Math.abs(unadjTotal)

  const ratio = base > G10_FV_DIFF_THRESHOLD ? Math.abs(absDiff) / base : 1

  if (ratio >= hardRatio || (hardAbs > 0 && Math.abs(absDiff) >= hardAbs)) return 'hard'

  if (ratio >= softRatio) return 'soft'

  return 'none'

}



/**

 * 推送公允差异至 G10-3（FVTPL：负债上升 Dr 6101 / Cr 2101），并回写 G10-1。

 */

export function pushG10FvDiffToAdjustment(

  responses: Map<string, ChecklistResponse>,

  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,

  items: G10PushAdjItem[],

  source = 'G10-5',

): number {

  if (!items.length) return 0



  let existing: Record<string, unknown>[] = []

  const raw = responses.get(G10_ADJ_KEY)?.remark

  if (raw) {

    try {

      const parsed = JSON.parse(raw)

      if (Array.isArray(parsed)) existing = parsed

    } catch { /* ignore */ }

  }



  const seqBase = existing.length

  const added: Record<string, unknown>[] = []

  items.forEach((it, i) => {

    const amt = Math.abs(parseNum(it.amount))

    if (amt < G10_FV_DIFF_THRESHOLD) return

    const isIncrease = parseNum(it.amount) > 0

    const rowKey = inferG10AdjudicationRowKey({

      liabilityType: it.liabilityType,

      liabilityName: it.liabilityName,

      summary: it.summary,

    })

    const base = {

      date: new Date().toISOString().slice(0, 10),

      entryType: 'AJE',

      preparedBy: '',

      indexRef: it.indexRef || source,

      liabilityType: it.liabilityType || '',

      adjudicationRowKey: rowKey,

      remark: it.remark || `来源 ${source}`,

    }

    added.push({

      ...base,

      rowId: `g10fv-adj-${Date.now().toString(36)}-${i}a`,

      seq: seqBase + added.length + 1,

      summary: it.summary,

      accountCode: '6101',

      accountName: '公允价值变动损益',

      debitAmount: isIncrease ? amt : 0,

      creditAmount: isIncrease ? 0 : amt,

    })

    added.push({

      ...base,

      rowId: `g10fv-adj-${Date.now().toString(36)}-${i}b`,

      seq: seqBase + added.length + 1,

      summary: `${it.summary}（公允变动）`,

      accountCode: G10_ACCOUNT_CODE,

      accountName: '交易性金融负债',

      debitAmount: isIncrease ? 0 : amt,

      creditAmount: isIncrease ? amt : 0,

    })

  })



  if (!added.length) return 0



  const merged = [...existing, ...added]

  debouncedSave(G10_ADJ_KEY, { remark: JSON.stringify(merged) })

  const pushedCount = items.filter((it) => Math.abs(parseNum(it.amount)) >= G10_FV_DIFF_THRESHOLD).length
  commitG10AdjustmentWritebackFromRows(responses, debouncedSave, merged as Parameters<typeof aggregateG10AdjustmentAjeRjeByRow>[0], {
    source: 'G10-5',
    offerDisclosurePull: pushedCount > 0,
  })

  return pushedCount
}

/** G10A 程序表 sheet 名（field-overrides scope） */
export const G10A_PROCEDURE_SHEET = '交易性金融负债实质性程序表G10A'

/** G10A seq9：公允价值计量 / L3 调节（G10-5/G10-6） */
export const G10A_FV_PROGRAM_NOS = [9] as const
/** G10A seq10：衍生金融工具核查（G10-8） */
export const G10A_DERIVATIVE_PROGRAM_NOS = [10] as const
/** G10A seq6/7/8：新增/处置/截止（G10-7） */
export const G10A_VOUCHER_PROGRAM_NOS = [6, 7, 8] as const
/** G10A seq5：分类适当性（G10-4） */
export const G10A_CLASSIFICATION_PROGRAM_NOS = [5] as const
/** G10A seq1：明细表 + 审定表（G10-1/G10-2） */
export const G10A_DETAIL_PROGRAM_NOS = [1] as const
/** G10A seq4：分析程序（G10-1/G10-2） */
export const G10A_ANALYSIS_PROGRAM_NOS = [4] as const
/** G10A seq1+4：审定表编制 + 变动分析（G10-1） */
export const G10A_ADJUDICATION_PROGRAM_NOS = [1, 4] as const
/** G10A seq14：列报披露（附注） */
export const G10A_DISCLOSURE_PROGRAM_NOS = [14] as const
/** G10A seq3/4：公允证据与损益勾稽（G10-3；短模板 ref G10-3/G13） */
export const G10A_ADJUSTMENT_PROGRAM_NOS = [3, 4] as const

export const G10A_FV_MARK_KEY = 'G10A-fv-complete'
export const G10A_DERIVATIVE_MARK_KEY = 'G10A-derivative-complete'
export const G10A_VOUCHER_MARK_KEY = 'G10A-voucher-complete'
export const G10A_CLASSIFICATION_MARK_KEY = 'G10A-classification-complete'
export const G10A_DETAIL_MARK_KEY = 'G10A-detail-complete'
export const G10A_ADJUDICATION_MARK_KEY = 'G10A-adjudication-complete'
export const G10A_DISCLOSURE_MARK_KEY = 'G10A-disclosure-complete'
export const G10A_ADJUSTMENT_MARK_KEY = 'G10A-adjustment-complete'

export interface G10AProcedureMark {
  key: string
  label: string
  programNos: readonly number[]
}

function isG10AProcedureMarkDone(m: Map<string, { conclusion?: string; remark?: string }>, key: string): boolean {
  const item = m.get(key)
  return item?.conclusion === 'completed' || !!item?.remark
}

/** 底稿目录展示：已回填 G10A 的程序步骤 */
export function collectG10AProcedureMarks(
  m: Map<string, { conclusion?: string; remark?: string }>,
): G10AProcedureMark[] {
  const marks: G10AProcedureMark[] = []
  if (isG10AProcedureMarkDone(m, G10A_DETAIL_MARK_KEY)) {
    marks.push({ key: 'detail', label: '明细编制 seq1', programNos: G10A_DETAIL_PROGRAM_NOS })
  }
  if (isG10AProcedureMarkDone(m, G10A_ADJUDICATION_MARK_KEY)) {
    marks.push({ key: 'adjudication', label: '审定/分析 seq1/4', programNos: G10A_ADJUDICATION_PROGRAM_NOS })
  }
  if (isG10AProcedureMarkDone(m, G10A_ADJUSTMENT_MARK_KEY)) {
    marks.push({ key: 'adjustment', label: '调整/公允损益 seq3/4', programNos: G10A_ADJUSTMENT_PROGRAM_NOS })
  }
  if (isG10AProcedureMarkDone(m, G10A_DISCLOSURE_MARK_KEY)) {
    marks.push({ key: 'disclosure', label: '列报披露 seq14', programNos: G10A_DISCLOSURE_PROGRAM_NOS })
  }
  if (isG10AProcedureMarkDone(m, G10A_FV_MARK_KEY)) {
    marks.push({ key: 'fv', label: '公允测试/L3 seq9', programNos: G10A_FV_PROGRAM_NOS })
  }
  if (isG10AProcedureMarkDone(m, G10A_CLASSIFICATION_MARK_KEY)) {
    marks.push({ key: 'classification', label: '分类适当性 seq5', programNos: G10A_CLASSIFICATION_PROGRAM_NOS })
  }
  if (isG10AProcedureMarkDone(m, G10A_DERIVATIVE_MARK_KEY)) {
    marks.push({ key: 'derivative', label: '衍生工具 seq10', programNos: G10A_DERIVATIVE_PROGRAM_NOS })
  }
  if (isG10AProcedureMarkDone(m, G10A_VOUCHER_MARK_KEY)) {
    marks.push({ key: 'voucher', label: '凭证检查 seq6/7/8', programNos: G10A_VOUCHER_PROGRAM_NOS })
  }
  return marks
}

export function buildG10FvProcedureSummary(input: {
  rowCount: number
  diffCount: number
  level3Count: number
  auditedTotal: number
  l3RowCount?: number
  validationErrors: number
}): string {
  const parts = [
    `G10-5 公允价值测试已编制：${input.rowCount} 项`,
    `差异 ${input.diffCount} 项`,
    `Level3 ${input.level3Count} 项`,
    `审定合计 ${input.auditedTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
  ]
  if (input.l3RowCount != null && input.l3RowCount > 0) {
    parts.push(`G10-6 L3 调节 ${input.l3RowCount} 行`)
  }
  parts.push(input.validationErrors ? `校验未通过 ${input.validationErrors} 项` : '校验通过')
  return parts.join('；')
}

export function buildG10DerivativeProcedureSummary(input: {
  questionnaireRows: number
  missingCompliance: number
  linkedDetailCount: number
  wizardSummary: string
}): string {
  return [
    `G10-8 衍生工具核查：问卷 ${input.questionnaireRows} 项`,
    `关联 G10-2 衍生行 ${input.linkedDetailCount} 个`,
    input.missingCompliance ? `待填合规 ${input.missingCompliance} 行` : '合规项已填',
    input.wizardSummary ? `识别结论：${input.wizardSummary}` : '',
  ].filter(Boolean).join('；')
}

export function buildG10VoucherProcedureSummary(input: {
  rowCount: number
  abnormal: number
  untested: number
  completionPct: number
  quantitative?: number
}): string {
  const parts = [
    `G10-7 凭证检查 ${input.rowCount} 行`,
    `完成度 ${input.completionPct}%`,
    `未测 ${input.untested}`,
    `异常 ${input.abnormal}`,
  ]
  if (input.quantitative != null) parts.push(`金额类异常 ${input.quantitative}`)
  return parts.join('；')
}

export function buildG10DetailProcedureSummary(input: {
  rowCount: number
  closingAdjustedTotal: number
  integrityErrors: number
  derivativeCount: number
  linkedG10A: boolean
}): string {
  return [
    `G10-2 明细表：${input.rowCount} 项`,
    `审定合计 ${input.closingAdjustedTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    input.derivativeCount ? `衍生 ${input.derivativeCount} 项` : '',
    input.integrityErrors ? `校验未通过 ${input.integrityErrors} 项` : '校验通过',
    input.linkedG10A ? '已与 G10-1 勾稽' : '',
  ].filter(Boolean).join('；')
}

export function buildG10AdjudicationProcedureSummary(input: {
  closingAdjustedTotal: number
  tbVariance: number | null
  detailVariance: number | null
  threePartMismatches: number
  missingReasons: number
}): string {
  return [
    `G10-1 审定表 (三)合计 ${input.closingAdjustedTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    input.tbVariance != null ? `试算表差异 ${input.tbVariance.toFixed(2)}` : '',
    input.detailVariance != null ? `与 G10-2 差异 ${input.detailVariance.toFixed(2)}` : '',
    input.threePartMismatches ? `(一)(二)(三)勾稽异常 ${input.threePartMismatches} 项` : '',
    input.missingReasons ? `缺原因分析 ${input.missingReasons} 行` : '',
  ].filter(Boolean).join('；')
}

export function buildG10DisclosureProcedureSummary(input: {
  variant: 'listed' | 'soe'
  closingSum: number
  adjudicated: number | null
  crossVariance: number | null
}): string {
  const label = input.variant === 'listed' ? '上市附注' : '国企附注'
  return [
    `${label} 期末合计 ${input.closingSum.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    input.adjudicated != null
      ? `G10-1 审定 ${input.adjudicated.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
      : '',
    input.crossVariance != null && Math.abs(input.crossVariance) > 0.01
      ? `勾稽差异 ${input.crossVariance.toFixed(2)}`
      : '与审定勾稽一致',
  ].filter(Boolean).join('；')
}

export function buildG10ClassificationProcedureSummary(input: {
  rowCount: number
  withBasis: number
  missingBasis: number
  categoryMismatch: number
  trading: number
  designated: number
  bookTotal: number
}): string {
  return [
    `G10-4 分类适当性：${input.rowCount} 项`,
    `已勾选依据 ${input.withBasis}`,
    input.missingBasis ? `缺依据 ${input.missingBasis}` : '依据完整',
    input.categoryMismatch ? `类别不一致 ${input.categoryMismatch}` : '',
    `交易性 ${input.trading} · 指定 ${input.designated}`,
    `期末账面 ${input.bookTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
  ].filter(Boolean).join('；')
}

export function buildG10AdjustmentProcedureSummary(input: {
  rowCount: number
  ajeCount: number
  rjeCount: number
  balanced: boolean
  net2101: number
  fvPlNet: number
  writebackRows: number
  fromG105: number
  fromG104: number
  pendingG104: number
}): string {
  return [
    `G10-3 调整分录：${input.rowCount} 行（AJE ${input.ajeCount} / RJE ${input.rjeCount}）`,
    input.balanced ? '借贷平衡' : '借贷未平衡',
    `2101 净额 ${input.net2101.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    `6101 净额 ${input.fvPlNet.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    input.writebackRows ? `回写 G10-1 分项 ${input.writebackRows} 行` : '',
    input.fromG105 ? `G10-5 来源 ${input.fromG105} 行` : '',
    input.fromG104 ? `G10-4 来源 ${input.fromG104} 行` : '',
    input.pendingG104 ? `待复核 G10-4 草稿 ${input.pendingG104} 行` : '',
  ].filter(Boolean).join('；')
}

/** 回填 G10A 程序步骤状态（FieldOverrideService，与 GtAProgramConsole 一致） */
export async function markG10AProcedureSteps(opts: {
  projectId: string
  year?: number
  programNos: readonly number[]
  status?: string
  linkedWorkpapers?: string
  executionSummary?: string
}): Promise<number> {
  if (!opts.projectId || !opts.programNos.length) return 0
  const { api } = await import('@/services/apiProxy')
  const year = opts.year || new Date().getFullYear()
  const scope = `procedure_table:${G10A_PROCEDURE_SHEET}`
  const status = opts.status || 'completed'
  let n = 0
  for (const programNo of opts.programNos) {
    const fields: Array<{ field: string; value: unknown }> = [
      { field: 'status', value: status },
    ]
    if (opts.linkedWorkpapers) fields.push({ field: 'linked_workpapers', value: opts.linkedWorkpapers })
    if (opts.executionSummary) fields.push({ field: 'execution_summary', value: opts.executionSummary })
    for (const f of fields) {
      try {
        await api.post('/api/workpapers/field-overrides', {
          project_id: opts.projectId,
          year,
          scope,
          item_key: String(programNo),
          field: f.field,
          value: f.value,
        }, { _silent: true } as any)
        if (f.field === 'status') n += 1
      } catch { /* silent */ }
    }
  }
  try {
    window.dispatchEvent(new CustomEvent('g10:procedure-marked', {
      detail: { programNos: [...opts.programNos], status, timestamp: Date.now() },
    }))
  } catch { /* silent */ }
  return n
}

