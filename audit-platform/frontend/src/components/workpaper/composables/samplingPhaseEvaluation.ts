/**
 * 两阶段合并评价（spec voucher-identity-writeback-and-audit-phase 任务 16，需求 7.5 / 7.6，ADR-VK-10）。
 *
 * - `computeSampleErrorTotal`：样本实际错报合计 E = 参与推断的样本（未检查样本已按处置改写，视同偏差按账面金额）
 *   实际错报的**绝对值**之和，随批次评价保存。取绝对值：高估与低估不互相抵消 —— 年审口径 b 拿它与年审错报上限
 *   相加后同可容忍错报比较，抵消会把全年错报上限算小。
 * - `loadPhaseEvaluation`：读 `GET /sampling/phase-evaluation`。合并公式与全年结论全在后端
 *   （`services/sampling_phase_evaluation.py`），保存评价时同一结果写进年审批次评价、投影到抽样记录结论；
 *   这里只解析展示，不在前端再算一遍。
 */
import Decimal from 'decimal.js'
import http from '@/utils/http'
import type { SampledVoucher } from './useSamplingAlgorithms'
import { finalPopulationModeOf, type FinalPopulationMode } from './useFinalPopulationMode'

function absAmount(v: string | number | null | undefined): Decimal {
  try {
    const d = new Decimal(v === undefined || v === null || v === '' ? 0 : v)
    return d.isFinite() ? d.abs() : new Decimal(0)
  } catch {
    return new Decimal(0)
  }
}

/** 样本实际错报合计 E：传入的是参与推断的那批样本（调用方已按未检查处置改写、排除未选处置的未检查样本） */
export function computeSampleErrorTotal(samples: readonly SampledVoucher[]): string {
  const e = samples.reduce((acc, v) => acc.plus(absAmount(v.actualMisstatement)), new Decimal(0))
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- 发给后端的 2 位小数串，不是界面显示格式化
  return e.toFixed(2, Decimal.ROUND_HALF_EVEN)
}

export type CombinedConclusionCode = 'acceptable' | 'not_acceptable' | 'undetermined'

export interface CombinedEvaluation {
  mode: FinalPopulationMode
  /** 口径 a：预审各批推断错报之和；口径 b：预审样本实际错报合计之和 */
  interimComponent: string
  /** 口径 a：预审各批错报上限之和；口径 b 同 interimComponent */
  interimUpperComponent: string
  finalProjected: string
  finalUpperLimit: string
  projected: string
  upperLimit: string
  tolerableMisstatement: string | null
  conclusionCode: CombinedConclusionCode
  /** 后端拼好的全年结论（含「仅供参考」等注明），与抽样记录结论里的那一条逐字相同 */
  conclusionMessage: string
  scopeConsistent: boolean
}

export interface InterimBatchComponent {
  seq: number
  projected: string | null
  upperLimit: string | null
  sampleErrorTotal: string | null
}

export interface PhaseEvaluationView {
  available: boolean
  /** false = 这个批次本来就不需要合并评价（预审批次、抽凭时没有预审工作的年审批次）：界面不显示 */
  applicable: boolean
  /** 不可用的原因（写给用户看）；可用时为空串 */
  reason: string
  mode: FinalPopulationMode | null
  interim: InterimBatchComponent[]
  combined: CombinedEvaluation | null
}

function strOrNull(v: unknown): string | null {
  return v === undefined || v === null || v === '' ? null : String(v)
}

const CONCLUSION_CODES: readonly CombinedConclusionCode[] = ['acceptable', 'not_acceptable', 'undetermined']

export function parsePhaseEvaluation(raw: any): PhaseEvaluationView {
  const c = raw?.combined
  const mode = finalPopulationModeOf(raw?.mode)
  const available = raw?.available === true && c != null && typeof c === 'object' && mode != null
  const code = CONCLUSION_CODES.find(x => x === c?.conclusion_code) ?? 'undetermined'
  return {
    available,
    applicable: available || raw?.applicable === true,
    reason: available ? '' : String(raw?.reason ?? ''),
    mode,
    interim: available && Array.isArray(raw?.interim)
      ? raw.interim.map((i: any, idx: number) => ({
          seq: Number.isFinite(Number(i?.seq)) ? Number(i.seq) : idx + 1,
          projected: strOrNull(i?.projected),
          upperLimit: strOrNull(i?.upper_limit),
          sampleErrorTotal: strOrNull(i?.sample_error_total),
        }))
      : [],
    combined: available
      ? {
          mode: mode as FinalPopulationMode,
          interimComponent: String(c.interim_component ?? ''),
          interimUpperComponent: String(c.interim_upper_component ?? ''),
          finalProjected: String(c.final_projected ?? ''),
          finalUpperLimit: String(c.final_upper_limit ?? ''),
          projected: String(c.projected ?? ''),
          upperLimit: String(c.upper_limit ?? ''),
          tolerableMisstatement: strOrNull(c.tolerable_misstatement),
          conclusionCode: code,
          conclusionMessage: String(c.conclusion_message ?? ''),
          scopeConsistent: c.scope_consistent !== false,
        }
      : null,
  }
}

/** logId 为空时后端取本底稿最近一次带年审口径的批次 */
export async function loadPhaseEvaluation(
  projectId: string,
  workpaperId: string,
  logId: string | null,
): Promise<PhaseEvaluationView> {
  const params: Record<string, string> = { wp_id: workpaperId }
  if (logId) params.log_id = logId
  const res = await http.get(`/api/projects/${projectId}/sampling/phase-evaluation`, { params, _silent: true } as any)
  const body: any = res?.data
  return parsePhaseEvaluation(body?.data ?? body)
}
