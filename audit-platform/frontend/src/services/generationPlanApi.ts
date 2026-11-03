/**
 * 生成计划 / 粗裁状态 / 按计划生成底稿（spec trim-generation-plan-linkage R1~R3）。
 *
 * 生成底稿弹窗（底稿列表页与程序裁剪页共用）只读后端给的生成计划：每个模板编码这次会不会生成、为什么
 * （与生成接口同一判定）。弹窗只能按循环勾选，逐个底稿的排除走程序裁剪页（有理由、有权限、留痕）。
 * 契约：docs/contracts/procedure-chain/generation-plan-view.schema.json。
 */
import { api } from '@/services/apiProxy'
import { procedures as P_proc, templates as P_tpl } from '@/services/apiPaths'
import type { TemplateSetItem } from '@/services/workpaperApi'
import type { WorkpaperGenerateResult } from '@/utils/workpaperGenerateResult'

export type TrimState = 'not_initialized' | 'unconfirmed' | 'confirmed'
export type PlanItemState = 'trimmed' | 'in_recycle' | 'existing' | 'category_excluded' | 'to_create'
export type ProgramOrigin = 'catalog' | 'supplement' | 'custom'

export interface PlanCounts {
  total: number
  to_create: number
  existing: number
  in_recycle: number
  trimmed: number
  category_excluded: number
}

export interface PlanProgram {
  code: string
  name: string
  status: string
  skip_reason: string | null
  origin: ProgramOrigin
}

export interface PlanItem {
  wp_code: string
  wp_name: string
  state: PlanItemState
  /** 决定它的程序行（没有程序行覆盖为 null） */
  decided_by: string | null
  /** 实质性循环的科目母码（D2 审定表等）跟随下级程序行 */
  follows_children: boolean
  category_applicable: boolean
  category_reason: string | null
  /** 已保存粗裁的循环里：业务分类不适用但程序行执行，照常生成 */
  category_conflict: boolean
}

export interface PlanCycle {
  cycle: string
  trim_state: TrimState
  confirmed_at: string | null
  confirmed_by: string | null
  counts: PlanCounts
  programs: PlanProgram[]
  items: PlanItem[]
}

export interface GenerationPlan {
  template_set: { id: string; set_name: string; code_count: number } | null
  business_category: { code: 'A' | 'B' | 'C'; defaulted: boolean }
  totals: PlanCounts
  cycles: PlanCycle[]
}

export interface ScopeConfirmation {
  cycle: string
  trim_state: TrimState
  program_count: number
  confirmed_at: string | null
  confirmed_by: string | null
}

/** 弹窗里只显示「标准年审」与自建模板集（与原生成弹窗同一过滤口径：去掉内置占位集） */
const HIDDEN_BUILTIN_SETS = new Set(['IPO', '上市公司', '上市附注', '国企附注', '精简版'])

export function visibleTemplateSets(sets: TemplateSetItem[]): TemplateSetItem[] {
  return (sets || []).filter((s) => s.set_name === '标准年审' || !HIDDEN_BUILTIN_SETS.has(s.set_name))
}

/**
 * 列出可选模板集（只读）。
 *
 * 内置模板集由后端启动任务 `seed_builtin_template_sets` 幂等初始化；原先每次打开弹窗先 POST seed
 * （只读账号也会发写请求、每次改写内置集）——spec trim-followup-residual-findings-closure R2。
 */
export async function listGenerationTemplateSets(): Promise<TemplateSetItem[]> {
  const sets = await api.get<TemplateSetItem[]>(P_tpl.sets.list, { _silent: true } as any)
  return visibleTemplateSets(Array.isArray(sets) ? sets : [])
}

export async function getGenerationPlan(projectId: string, templateSetId?: string | null): Promise<GenerationPlan> {
  return api.get<GenerationPlan>(P_proc.generationPlan(projectId), {
    params: templateSetId ? { template_set_id: templateSetId } : {},
    _silent: true,
  } as any)
}

export async function getScopeConfirmations(projectId: string): Promise<ScopeConfirmation[]> {
  const data = await api.get<{ cycles: ScopeConfirmation[] }>(P_proc.scopeConfirmations(projectId), {
    _silent: true,
    _dedupe: false,
  } as any)
  return Array.isArray(data?.cycles) ? data.cycles : []
}

export type GenerationOperationState =
  | 'prepared' | 'materializing' | 'materialized' | 'finalizing'
  | 'succeeded' | 'partial_failed' | 'failed' | 'stale'

export interface GenerationOperationStatus {
  operation_id: string
  status: GenerationOperationState
  progress_total: number
  progress_done: number
  attempt: number
  terminal: boolean
  resumable: boolean
  resumable_after: string | null
  public_error: string | null
  receipt?: WorkpaperGenerateResult & { operation_id: string; status: GenerationOperationState }
}

export interface GenerateOperationOptions {
  templateSetId: string
  year: number
  codes: string[]
  operationId: string
}

/**
 * 按模板集生成所选编码。客户端 UUID 是响应丢失后的恢复身份；同一次业务操作重试必须复用。
 */
export async function generateWorkpapers(
  projectId: string,
  opts: GenerateOperationOptions,
): Promise<WorkpaperGenerateResult | GenerationOperationStatus> {
  return api.post<WorkpaperGenerateResult | GenerationOperationStatus>(P_tpl.generateFromSet(projectId), {
    template_set_id: opts.templateSetId,
    year: opts.year,
    selected_templates: opts.codes,
    operation_id: opts.operationId,
  }, { _silent: true } as any)
}

export async function getGenerationOperation(
  projectId: string,
  operationId: string,
): Promise<GenerationOperationStatus> {
  return api.get<GenerationOperationStatus>(P_tpl.generationOperation(projectId, operationId), {
    _silent: true,
    _dedupe: false,
  } as any)
}

export function operationReceipt(
  value: WorkpaperGenerateResult | GenerationOperationStatus,
): WorkpaperGenerateResult | null {
  if ('terminal' in value) return value.terminal && value.receipt ? value.receipt : null
  return value
}

export function isActiveOperation(value: GenerationOperationStatus): boolean {
  return !value.terminal && !value.resumable
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/**
 * 执行并恢复一次持久 operation。网络错误先查服务端状态；只有租约已可恢复时才以同一 id、同一请求重入。
 * 不改调第二写端点，也不创建新 operation id。
 */
export async function runGenerationOperation(
  projectId: string,
  opts: GenerateOperationOptions,
  config: { timeoutMs?: number; pollMs?: number; sleepFn?: (ms: number) => Promise<void> } = {},
): Promise<WorkpaperGenerateResult> {
  const timeoutMs = config.timeoutMs ?? 180_000
  const pollMs = config.pollMs ?? 1_000
  const sleepFn = config.sleepFn ?? sleep
  const started = Date.now()
  let value: WorkpaperGenerateResult | GenerationOperationStatus
  try {
    value = await generateWorkpapers(projectId, opts)
  } catch (initialError: any) {
    const httpStatus = Number(initialError?.response?.status || 0)
    if (httpStatus >= 400 && httpStatus < 500) throw initialError
    try {
      value = await getGenerationOperation(projectId, opts.operationId)
    } catch {
      throw initialError
    }
  }

  let resumed = false
  while (true) {
    const receipt = operationReceipt(value)
    if (receipt) return receipt
    const status = value as GenerationOperationStatus
    if (status.terminal) throw new Error(status.public_error || '生成操作已结束，但没有可用回执')
    if (status.resumable && !resumed) {
      resumed = true
      value = await generateWorkpapers(projectId, opts)
      continue
    }
    if (Date.now() - started >= timeoutMs) {
      throw new Error('底稿仍在后台生成，可稍后再次点击生成查看原操作结果')
    }
    await sleepFn(pollMs)
    value = await getGenerationOperation(projectId, opts.operationId)
  }
}

/** 接口错误 → 一句中文原因（后端错误体的 message 被 http 拦截器复制到 detail；503 是 {error, message}） */
export function planErrorText(e: any): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail.message === 'string' && detail.message) return detail.message
  if (!e?.response) return '网络不通，请检查连接'
  if (e.response.status === 401) return '登录状态已失效，请重新登录'
  if (e.response.status === 403) return '没有本项目的查看权限'
  if (e.response.status === 423) return '项目已归档，只能查看，不能生成底稿'
  return '请稍后重试'
}
