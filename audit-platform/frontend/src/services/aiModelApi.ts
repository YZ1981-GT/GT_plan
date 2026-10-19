/** AI 模型配置 API 服务层 */
import http from '@/utils/http'
import { aiModels as P } from '@/services/apiPaths'

const silent = (extra: Record<string, unknown> = {}) => ({ ...extra, _silent: true } as any)

export type AIModelType = 'chat' | 'embedding' | 'ocr'
export type ReasoningEffort = 'low' | 'medium' | 'high' | 'xhigh'
export type OCRCapability = 'ocr' | 'layout_parsing'
export type OCRProtocol = 'local' | 'paddlex_json'
export type AIAuthScheme = 'none' | 'bearer' | 'x_api_key' | 'api_key' | 'custom_header'
/** 部署位置（V197）：由端点推导，环回地址或本机 OCR 引擎为本机；调用按「本机 → 服务器」选择已启用模型 */
export type AIDeployment = 'local' | 'server'
export type AIRouteKind = 'chat' | 'embedding' | 'ocr' | 'layout_parsing'
export type AIRouteCandidateStatus = 'available' | 'unavailable' | 'unknown'
export type AIProvider =
  | 'ollama'
  | 'openai_compatible'
  | 'paddleocr'
  | 'deepseek'
  | 'zhipu'
  | 'qwen'
  | 'azure_openai'
  | 'custom'

export interface AIModel {
  id: string
  preset_key: string | null
  model_name: string
  model_type: AIModelType
  provider: AIProvider
  endpoint_url: string | null
  reasoning_effort: ReasoningEffort | null
  /** 企业预设登记的服务端支持取值；null 表示不限制 */
  reasoning_effort_options?: ReasoningEffort[] | null
  /** 「未指定」时服务端采用的默认强度（仅展示） */
  reasoning_effort_server_default?: ReasoningEffort | null
  ocr_capability: OCRCapability | null
  ocr_protocol: OCRProtocol | null
  api_path: string | null
  auth_scheme: AIAuthScheme | null
  auth_header_name: string | null
  request_timeout_seconds: number | null
  has_api_key: boolean
  api_key_updated_at: string | null
  deployment: AIDeployment
  /** 参与路由（V197 起不再是「唯一生效」：对话 / OCR 本机、服务器各可启用一条） */
  is_active: boolean
  context_window: number | null
  performance_notes: string | null
  created_at: string | null
  updated_at: string | null
}

/** 保存已启用的本机模型时，若本机当前不可用会照常保存并返回提示 */
export interface AIModelSaveResult extends AIModel {
  warning?: string | null
}

export interface AIModelActivateResult {
  message: string
  model_name: string
  provider: AIProvider
  deployment: AIDeployment
  /** 本机模型当前不可用但已启用时的提示（含有无服务器兜底） */
  warning: string | null
}

export interface AIRouteCandidate {
  model_id: string | null
  model_name: string
  deployment: AIDeployment
  provider: string | null
  /** 公共健康接口不返回端点 */
  endpoint?: string | null
  source: 'database' | 'environment' | 'builtin'
  reasoning_effort: ReasoningEffort | null
  /** 没有启用行时的兜底（对话 / 向量 = `.env`，文字识别 = 本机进程内引擎） */
  implicit: boolean
  status: AIRouteCandidateStatus
  reason: string
  latency_ms: number | null
  checked_at: string | null
}

export interface AIRoute {
  kind: AIRouteKind
  label: string
  /** single = 向量只用一条模型，不跨模型兜底 */
  policy: 'local_first' | 'single'
  /** 按顺序第一个可用的候选；没有可用候选或尚未检测时为 null */
  effective: AIRouteCandidate | null
  candidates: AIRouteCandidate[]
  error: string | null
  has_local: boolean
  has_server: boolean
}

export interface AIRouteStatus {
  routes: AIRoute[]
  checked_at: string
}

export interface AIModelCreate {
  model_name: string
  model_type: AIModelType
  provider: AIProvider
  endpoint_url?: string | null
  api_key?: string
  reasoning_effort?: ReasoningEffort | null
  ocr_capability?: OCRCapability | null
  ocr_protocol?: OCRProtocol | null
  api_path?: string | null
  auth_scheme?: AIAuthScheme | null
  auth_header_name?: string | null
  request_timeout_seconds?: number | null
  context_window?: number | null
  performance_notes?: string | null
}

export interface AIModelUpdate {
  model_name?: string
  provider?: AIProvider
  endpoint_url?: string | null
  api_key?: string
  clear_api_key?: boolean
  reasoning_effort?: ReasoningEffort | null
  ocr_capability?: OCRCapability | null
  ocr_protocol?: OCRProtocol | null
  api_path?: string | null
  auth_scheme?: AIAuthScheme | null
  auth_header_name?: string | null
  request_timeout_seconds?: number | null
  context_window?: number | null
  performance_notes?: string | null
}

export interface AIProviderOption {
  value: AIProvider
  label: string
  default_endpoint: string
  requires_api_key: boolean
  supported_types: AIModelType[]
  description: string
}

export interface AIConnectionTestResult {
  status: 'ok' | 'error'
  error_code: string | null
  message: string
}

export interface AIRuntimeConfig {
  model_id: string | null
  model_name: string
  model_type: AIModelType
  provider: AIProvider
  endpoint_url: string
  source: 'database' | 'environment'
  deployment?: AIDeployment
}

export interface AIHealthStatus {
  llm_status: string
  embedding_status: string
  vllm_status: string
  ollama_status: string
  paddleocr_status: string
  chromadb_status: string
  active_chat_model: string | null
  active_embedding_model: string | null
  chat_config: AIRuntimeConfig | null
  embedding_config: AIRuntimeConfig | null
  routes?: AIRoute[]
  timestamp: string
}

export async function getAIModels(modelType?: AIModelType): Promise<AIModel[]> {
  const { data } = await http.get(P.list, silent({ params: modelType ? { model_type: modelType } : {} }))
  return data ?? []
}

export async function getAIProviders(): Promise<AIProviderOption[]> {
  const { data } = await http.get(P.providers, silent())
  return data?.providers ?? []
}

export async function createAIModel(payload: AIModelCreate): Promise<AIModel> {
  const { data } = await http.post(P.list, payload, silent())
  return data
}

export async function updateAIModel(id: string, payload: AIModelUpdate): Promise<AIModelSaveResult> {
  const { data } = await http.put(P.detail(id), payload, silent())
  return data
}

export async function deleteAIModel(id: string): Promise<void> {
  await http.delete(P.detail(id), silent())
}

export async function testAIModel(id: string): Promise<AIConnectionTestResult> {
  const { data } = await http.post(P.test(id), undefined, silent())
  return data
}

/** 启用：只替换同类型（OCR 同能力槽）同部署位置的那一条 */
export async function activateAIModel(id: string): Promise<AIModelActivateResult> {
  const { data } = await http.post(P.activate(id), undefined, silent())
  return data
}

/** 停用：退出路由；该类型没有启用模型时回落 `.env` / 本机进程内 OCR */
export async function deactivateAIModel(id: string): Promise<{ message: string; model_name: string }> {
  const { data } = await http.post(P.deactivate(id), undefined, silent())
  return data
}

/** 调用路由状态；refresh=true 时重新探测（否则用 30~60 秒内的检测结果与最近调用记录） */
export async function getAIRoutes(refresh = false): Promise<AIRouteStatus> {
  const { data } = await http.get(P.routes, silent({ params: refresh ? { refresh: true } : {} }))
  return data
}

export async function getAIHealth(): Promise<AIHealthStatus> {
  const { data } = await http.get(P.health, silent())
  return data
}

export async function seedDefaultModels(): Promise<void> {
  await http.post(P.seed, undefined, silent())
}
