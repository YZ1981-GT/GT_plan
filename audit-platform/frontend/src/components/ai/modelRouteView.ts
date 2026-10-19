/**
 * 「调用路由」面板的展示逻辑（纯函数，单测见 modelRouteView.spec.ts）。
 *
 * 数据来自 GET /api/ai-models/routes：每类路由按「本机 → 服务器」列出已启用候选，
 * effective 为按顺序第一个可用的候选（后端判定，这里只负责展示）。
 */
import type { AIDeployment, AIModel, AIRoute, AIRouteCandidate } from '@/services/aiModelApi'

export const DEPLOYMENT_LABELS: Record<AIDeployment, string> = { local: '本机', server: '服务器' }

/** 同一条路由（同类型；OCR 还要同能力槽）里的另一条已启用模型。 */
function otherActiveInSlot(model: AIModel, models: AIModel[]): AIModel | undefined {
  return models.find(item => item.id !== model.id && item.is_active
    && item.model_type === model.model_type
    && (model.model_type !== 'ocr' || item.ocr_capability === model.ocr_capability))
}

/** 表格「已启用」标签：本机行先用；服务器行在有本机行时是兜底，没有时就是唯一生效。 */
export function activeTagText(model: AIModel, models: AIModel[]): string {
  if (model.model_type === 'embedding') return '已启用'
  if (model.deployment === 'local') return '已启用 · 本机优先'
  const other = otherActiveInSlot(model, models)
  return other?.deployment === 'local' ? '已启用 · 服务器兜底' : '已启用 · 服务器'
}

/** 停用确认文案：停用后该类型（OCR 同能力槽）由谁承担调用。 */
export function deactivateConsequence(model: AIModel, models: AIModel[]): string {
  const other = otherActiveInSlot(model, models)
  if (other) {
    return `停用后由${DEPLOYMENT_LABELS[other.deployment]}模型「${other.model_name}」承担调用。`
  }
  if (model.model_type === 'chat') {
    return '停用后对话没有启用模型，将回落 .env 默认配置（LLM_BASE_URL / DEFAULT_CHAT_MODEL）。'
  }
  if (model.model_type === 'embedding') {
    return '停用后向量没有启用模型，将回落 .env 默认配置（LLM_EMBEDDING_BASE_URL / DEFAULT_EMBEDDING_MODEL）。'
  }
  if (model.ocr_capability === 'layout_parsing') return '停用后版面解析没有启用模型，调用会提示「未配置」。'
  return '停用后文字识别没有启用模型，将使用本机内置 OCR 引擎（本机未安装时识别会失败）。'
}

export interface ChainSlot {
  key: string
  deployment: AIDeployment
  /** null = 该部署位置没有启用模型（只在本机优先的路由里补出来） */
  candidate: AIRouteCandidate | null
}

/** JSON 里 effective 与 candidates[i] 是两个对象，按身份字段比较。 */
export function sameCandidate(a: AIRouteCandidate, b: AIRouteCandidate): boolean {
  return a.deployment === b.deployment && a.model_name === b.model_name && a.model_id === b.model_id
}

/** 本机优先的路由补齐「未启用」的一端，让管理员看清兜底链是否完整；向量只列实际那一条。 */
export function chainOf(route: AIRoute): ChainSlot[] {
  const slots: ChainSlot[] = route.candidates.map((candidate, index) => ({
    key: `${candidate.deployment}-${candidate.model_id ?? candidate.model_name}-${index}`,
    deployment: candidate.deployment,
    candidate,
  }))
  if (route.policy !== 'local_first') return slots
  if (!route.has_local) slots.unshift({ key: 'local-empty', deployment: 'local', candidate: null })
  if (!route.has_server) slots.push({ key: 'server-empty', deployment: 'server', candidate: null })
  return slots
}

/** 没有启用行时的兜底：对话 / 向量取 `.env`，文字识别用进程内引擎链（前面已有「本机」二字，不再重复）。 */
export function candidateName(candidate: AIRouteCandidate): string {
  if (candidate.implicit && candidate.source === 'environment') return `${candidate.model_name}（.env 默认）`
  if (candidate.implicit) return '内置引擎'
  return candidate.model_name
}

export function statusText(candidate: AIRouteCandidate): string {
  if (candidate.status === 'available') {
    return candidate.latency_ms != null ? `可用 · ${candidate.latency_ms} ms` : '可用'
  }
  if (candidate.status === 'unknown') return '未检测'
  return candidate.reason || '不可用'
}

export function emptyText(route: AIRoute): string {
  return route.kind === 'layout_parsing' ? '未启用版面解析模型，调用会提示「未配置」' : '未启用模型'
}

export function effectiveText(route: AIRoute): string {
  const effective = route.effective
  if (effective) {
    const first = route.candidates[0]
    const fallback = first && !sameCandidate(first, effective) ? '（兜底）' : ''
    return `${DEPLOYMENT_LABELS[effective.deployment]}「${effective.model_name}」${fallback}`
  }
  if (route.candidates.some(item => item.status === 'unknown')) return '未检测，点击「检测状态」'
  return '不可用'
}

export function effectiveClass(route: AIRoute): 'ok' | 'unknown' | 'err' {
  if (route.effective) return 'ok'
  return route.candidates.some(item => item.status === 'unknown') ? 'unknown' : 'err'
}
