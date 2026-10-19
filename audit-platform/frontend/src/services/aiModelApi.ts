/** AI 模型配置 API 服务层 */
import http from '@/utils/http'
import { aiModels as P } from '@/services/apiPaths'

const silent = (extra: Record<string, unknown> = {}) => ({ ...extra, _silent: true } as any)

export type AIModelType = 'chat' | 'embedding' | 'ocr'
export type ReasoningEffort = 'low' | 'medium' | 'high' | 'xhigh'
export type OCRCapability = 'ocr' | 'layout_parsing'
export type OCRProtocol = 'local' | 'paddlex_json'
export type AIAuthScheme = 'none' | 'bearer' | 'x_api_key' | 'api_key' | 'custom_header'
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
  is_active: boolean
  context_window: number | null
  performance_notes: string | null
  created_at: string | null
  updated_at: string | null
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

export async function updateAIModel(id: string, payload: AIModelUpdate): Promise<AIModel> {
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

export async function activateAIModel(id: string): Promise<{ message: string; model_name: string; provider: AIProvider }> {
  const { data } = await http.post(P.activate(id), undefined, silent())
  return data
}

export async function getAIHealth(): Promise<AIHealthStatus> {
  const { data } = await http.get(P.health, silent())
  return data
}

export async function seedDefaultModels(): Promise<void> {
  await http.post(P.seed, undefined, silent())
}
