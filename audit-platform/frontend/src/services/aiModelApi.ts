/**
 * AI 模型配置 API 服务层
 */
import http from '@/utils/http'

// ─── Types ───

export type AIModelType = 'chat' | 'embedding' | 'ocr'
export type AIProvider = 'ollama' | 'openai_compatible' | 'paddleocr'

export interface AIModel {
  id: string
  model_name: string
  model_type: AIModelType
  provider: AIProvider
  endpoint_url: string | null
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
  endpoint_url?: string
  is_active?: boolean
  context_window?: number
  performance_notes?: string
}

export interface AIModelUpdate {
  model_name?: string
  endpoint_url?: string | null
  is_active?: boolean
  context_window?: number | null
  performance_notes?: string | null
}

export interface AIHealthStatus {
  ollama_status: string
  paddleocr_status: string
  chromadb_status: string
  active_chat_model: string | null
  active_embedding_model: string | null
  timestamp: string
}

// ─── API Functions ───

export async function getAIModels(modelType?: AIModelType): Promise<AIModel[]> {
  const params = modelType ? { model_type: modelType } : {}
  const { data } = await http.get('/api/ai-models', { params })
  return data.data ?? data ?? []
}

export async function createAIModel(payload: AIModelCreate): Promise<AIModel> {
  const { data } = await http.post('/api/ai-models', payload)
  return data.data ?? data
}

export async function updateAIModel(id: string, payload: AIModelUpdate): Promise<AIModel> {
  const { data } = await http.put(`/api/ai-models/${id}`, payload)
  return data.data ?? data
}

export async function deleteAIModel(id: string): Promise<void> {
  await http.delete(`/api/ai-models/${id}`)
}

export async function activateAIModel(id: string): Promise<{ message: string; model_name: string }> {
  const { data } = await http.post(`/api/ai-models/${id}/activate`)
  return data.data ?? data
}

export async function getAIHealth(): Promise<AIHealthStatus> {
  const { data } = await http.get('/api/ai-models/health')
  return data.data ?? data
}

export async function seedDefaultModels(): Promise<void> {
  await http.post('/api/ai-models/seed')
}
