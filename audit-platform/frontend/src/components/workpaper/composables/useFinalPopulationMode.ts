/**
 * 年审抽样口径（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1~7.4，ADR-VK-10）。
 *
 * 年审阶段在有预审工作（未撤销的预审抽凭批次或预审手工挂凭）的底稿上抽凭前，先读
 * `GET /sampling/phase-context`；须选口径时弹 FinalPopulationModeDialog（缺省上次口径，首次 b）。
 * 后端按同一份上下文校验并执行（缺口径 422 FINAL_POPULATION_MODE_REQUIRED），这里只负责问用户。
 */
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export type FinalPopulationMode = 'remaining' | 'full_minus_interim'

export const FINAL_POPULATION_MODES: readonly FinalPopulationMode[] = ['full_minus_interim', 'remaining']

export const FINAL_POPULATION_MODE_LABELS: Record<FinalPopulationMode, string> = {
  remaining: '口径 a 只抽剩余期间',
  full_minus_interim: '口径 b 全年扣除预审已检样本',
}

/** 截止日来源：项目设置 / 项目没设时取预审批次期间上限（需求 7.2） */
export type CutoffSource = 'project' | 'interim_batches'

export interface SamplingPhaseContext {
  phase: 'preliminary' | 'final'
  /** 项目设置里的预审截止日 */
  interimCutoffDate: string | null
  /** 口径 a 实际采用的截止日（项目没设时为预审批次期间上限）；null = 口径 a 不可用 */
  effectiveCutoffDate: string | null
  cutoffSource: CutoffSource | null
  auditPeriodEnd: string | null
  interimBatchCount: number
  interimSampleCount: number
  interimLineCount: number
  interimAttachCount: number
  /** 本底稿上次年审批次的口径（未撤销的） */
  lastMode: FinalPopulationMode | null
  requiresMode: boolean
  defaultMode: FinalPopulationMode
}

/** 抽凭结果里的口径（后端 `stats.final_population`），回填时原样写进批次留痕 */
export interface FinalPopulationTrace {
  mode: FinalPopulationMode
  interim_cutoff_date: string | null
  interim_cutoff_source: CutoffSource | null
  date_start: string | null
  date_end: string | null
  interim_batch_count: number
  interim_sample_count: number
  interim_batch_line_fps: number
  interim_attach_count: number
  excluded_attach_lines: number
  unresolved_attach_count: number
}

/** 合法口径原样返回，其余（含旧记录没有口径）为 null */
export function finalPopulationModeOf(v: unknown): FinalPopulationMode | null {
  return v === 'remaining' || v === 'full_minus_interim' ? v : null
}

const asMode = finalPopulationModeOf

function asCount(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : 0
}

export function parsePhaseContext(raw: any): SamplingPhaseContext {
  const source = raw?.cutoff_source
  return {
    phase: raw?.current_audit_phase === 'preliminary' ? 'preliminary' : 'final',
    interimCutoffDate: raw?.interim_cutoff_date ?? null,
    effectiveCutoffDate: raw?.effective_cutoff_date ?? null,
    cutoffSource: source === 'project' || source === 'interim_batches' ? source : null,
    auditPeriodEnd: raw?.audit_period_end ?? null,
    interimBatchCount: asCount(raw?.interim_batch_count),
    interimSampleCount: asCount(raw?.interim_sample_count),
    interimLineCount: asCount(raw?.interim_line_count),
    interimAttachCount: asCount(raw?.interim_attach_count),
    lastMode: asMode(raw?.last_final_population_mode),
    requiresMode: raw?.requires_final_population_mode === true,
    defaultMode: asMode(raw?.default_final_population_mode) ?? 'full_minus_interim',
  }
}

/** 抽凭结果 stats.final_population → 留痕；没有（预审、或年审但无预审工作）返回 null */
export function parseFinalPopulationTrace(raw: any): FinalPopulationTrace | null {
  const mode = asMode(raw?.mode)
  if (!mode) return null
  return { ...raw, mode } as FinalPopulationTrace
}

export async function loadSamplingPhaseContext(
  projectId: string,
  workpaperId: string,
  year: number | null,
): Promise<SamplingPhaseContext> {
  const params: Record<string, unknown> = { wp_id: workpaperId }
  if (year != null) params.year = year
  const res = await http.get(`/api/projects/${projectId}/sampling/phase-context`, { params, _silent: true } as any)
  const body: any = res?.data
  return parsePhaseContext(body?.data ?? body)
}

/** FinalPopulationModeDialog 经 defineExpose 提供的接口 */
export interface FinalPopulationModePicker {
  open(ctx: SamplingPhaseContext): Promise<FinalPopulationMode | false>
}

/**
 * 抽凭前确定年审口径：不须选 → null；用户取消 → false；选定 → 口径。
 * 读上下文失败按 null 继续：口径由后端判定，须选时后端 422 并说明原因，不会静默按错口径抽。
 */
export async function chooseFinalPopulationMode(
  projectId: string,
  workpaperId: string,
  year: number | null,
  picker: FinalPopulationModePicker | null | undefined,
): Promise<FinalPopulationMode | null | false> {
  let ctx: SamplingPhaseContext
  try {
    ctx = await loadSamplingPhaseContext(projectId, workpaperId, year)
  } catch {
    ElMessage.warning('读取年审抽样口径失败，将由后端判定是否需要选择口径')
    return null
  }
  if (!ctx.requiresMode || !picker) return null
  return picker.open(ctx)
}
