/**
 * AI 模块 API 服务层
 * 封装所有 AI 相关 API 调用
 */
import http from '@/utils/http'
import { ai as P_ai, aiProject as P_aip, wpAI as P_wpai } from './apiPaths'

// ─── Types ───

export interface AIHealthResponse {
  ollama_status: string
  paddleocr_status: string
  chromadb_status: string
  active_chat_model: string | null
  active_embedding_model: string | null
  timestamp: string
}

export interface AIModelConfig {
  id: string
  model_name: string
  model_type: string
  provider: string
  endpoint_url: string | null
  is_active: boolean
  context_window: number | null
  performance_notes: string | null
  created_at: string | null
}

export interface DocumentScan {
  id: string
  project_id: string
  file_name: string
  file_path: string
  document_type: string
  recognition_status: string
  uploaded_by: string | null
  created_at: string | null
}

export interface ExtractedField {
  id: string
  field_name: string
  field_value: string
  confidence_score: number
  human_confirmed: boolean
}

export interface DocumentMatch {
  id: string
  document_scan_id: string
  matched_voucher_no: string | null
  matched_account_code: string | null
  matched_amount: number | null
  match_result: string
  difference_amount: number | null
  difference_description: string | null
}

export interface AIContent {
  id: string
  project_id: string
  workpaper_id: string | null
  content_type: string
  content_text: string
  data_sources: string[]
  generation_model: string | null
  generation_time: string | null
  confidence_level: string
  confirmation_status: string
  confirmed_by: string | null
  confirmed_at: string | null
  modification_note: string | null
  workpaper_name?: string
}

export interface Contract {
  id: string
  project_id: string
  contract_no: string
  party_a: string
  party_b: string
  contract_amount: number | null
  contract_date: string | null
  effective_date: string | null
  expiry_date: string | null
  contract_type: string
  analysis_status: string
  file_path: string | null
  file_name?: string
}

export interface ExtractedClause {
  id: string
  clause_type: string
  clause_content: string
  confidence_score: number
  human_confirmed: boolean
}

export interface ContractWPLink {
  id: string
  contract_id: string
  workpaper_id: string
  link_type: string
  link_description: string | null
  workpaper_name?: string
}

export interface EvidenceChainNode {
  icon: string
  label: string
  status: string
  missing: boolean
  statusText: string
}

export interface EvidenceAnomaly {
  riskLevel: string
  riskLevelText: string
  description: string
  documents: string[]
  suggestedProcedure: string
}

export interface EvidenceChainSummary {
  total: number
  matched: number
  unmatched: number
  missing: number
  highRisk: number
}

export interface ConfirmationAIResult {
  id: string
  check_type: string
  check_result: Record<string, any>
  risk_level: string
  human_confirmed: boolean
  confirmed_by: string | null
  confirmed_at: string | null
}

export interface NLIntent {
  intent_type: string
  params: Record<string, any>
  confidence: number
}

// ─── OCR API ───

export const ocrApi = {
  async uploadDocument(projectId: string, file: File): Promise<DocumentScan> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('project_id', projectId)
    const { data } = await http.post(P_aip.documents.upload(projectId), formData)
    return data
  },

  async batchUploadDocuments(
    projectId: string,
    files: File[],
    documentType?: string,
    onProgress?: (p: number) => void
  ): Promise<{ task_id: string }> {
    const formData = new FormData()
    files.forEach(f => formData.append('files', f))
    formData.append('project_id', projectId)
    if (documentType) formData.append('document_type', documentType)
    const { data } = await http.post(P_ai.ocr.batchUpload, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total))
        }
      },
    })
    return data
  },

  async getDocumentList(projectId: string, documentType?: string): Promise<DocumentScan[]> {
    const params: Record<string, string> = {}
    if (documentType) params.document_type = documentType
    const { data } = await http.get(P_aip.documents.list(projectId), { params })
    return data
  },

  async getExtractedFields(projectId: string, docId: string): Promise<ExtractedField[]> {
    const { data } = await http.get(P_aip.documents.extracted(projectId, docId))
    return data
  },

  async updateExtractedField(
    projectId: string,
    docId: string,
    fieldId: string,
    body: { field_value?: string; human_confirmed?: boolean }
  ): Promise<void> {
    await http.put(P_aip.documents.extractedField(projectId, docId, fieldId), body)
  },

  async matchWithLedger(projectId: string, docId: string): Promise<DocumentMatch> {
    const { data } = await http.post(P_aip.documents.match(projectId, docId))
    return data
  },

  async getTaskStatus(taskId: string): Promise<{ status: string; progress: number }> {
    const { data } = await http.get(P_ai.ocr.taskStatus(taskId))
    return data
  },
}

// ─── Workpaper AI API ───

export const workpaperAI = {
  async generateWorkpaperFill(
    projectId: string,
    workpaperId: string,
    body: { template_type?: string; year?: number }
  ): Promise<AIContent[]> {
    const { data } = await http.post(P_wpai.aiFill(projectId, workpaperId), body)
    return data
  },

  async generateAnalyticalReview(
    projectId: string,
    body: { account_code?: string; year?: number }
  ): Promise<AIContent> {
    const { data } = await http.post(P_ai.analyticalReview, { project_id: projectId, ...body })
    return data
  },

  async generateNoteDraft(
    projectId: string,
    body: { note_section: string; year?: number }
  ): Promise<AIContent> {
    const { data } = await http.post(P_ai.noteDraft, { project_id: projectId, ...body })
    return data
  },

  async workpaperReview(projectId: string, workpaperId: string): Promise<AIContent[]> {
    const { data } = await http.post(P_ai.workpaperReview, {
      project_id: projectId,
      workpaper_id: workpaperId,
    })
    return data
  },

  async getAIContentList(projectId: string, params?: {
    workpaper_id?: string
    content_type?: string
    confirmation_status?: string
  }): Promise<{ data: AIContent[] }> {
    const { data } = await http.get(P_aip.aiContent.list(projectId), { params })
    return data
  },

  async confirmAIContent(
    projectId: string,
    contentId: string,
    body: { action: 'accept' | 'modify' | 'reject' | 'regenerate'; modification_note?: string }
  ): Promise<void> {
    await http.put(P_aip.aiContent.confirm(projectId, contentId), body)
  },

  async getAIContentSummary(projectId: string): Promise<{
    total: number
    confirmed: number
    pending: number
    rejected: number
    modification_rate: number
  }> {
    const { data } = await http.get(P_aip.aiContent.summary(projectId))
    return data
  },

  async getPendingCount(projectId: string): Promise<number> {
    const { data } = await http.get(P_aip.aiContent.pendingCount(projectId))
    return data
  },
}

// ─── Contract API ───

export const contractAI = {
  async uploadContract(projectId: string, file: File): Promise<Contract> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('project_id', projectId)
    const { data } = await http.post(P_aip.contracts.upload(projectId), formData)
    return data
  },

  async batchUpload(
    formData: FormData,
    onProgress?: (p: number) => void
  ): Promise<{ task_id?: string; data?: any }> {
    const { data } = await http.post(P_aip.contracts.batchUpload, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total))
        }
      },
    })
    return data
  },

  async getContractList(projectId: string): Promise<{ data: Contract[] }> {
    const { data } = await http.get(P_aip.contracts.list(projectId))
    return data
  },

  async analyzeContract(projectId: string, contractId: string): Promise<{ data: ExtractedClause[] }> {
    const { data } = await http.post(P_aip.contracts.analyze(projectId, contractId))
    return data
  },

  async getExtractedClauses(contractId: string): Promise<{ data: ExtractedClause[] }> {
    const { data } = await http.get(P_aip.contracts.extracted(contractId))
    return data
  },

  async confirmClause(contractId: string, clauseId: string): Promise<void> {
    await http.put(P_aip.contracts.confirmClause(contractId, clauseId))
  },

  async crossReference(projectId: string, contractId: string): Promise<{ data: any[] }> {
    const { data } = await http.post(P_aip.contracts.crossReference(projectId, contractId))
    return data
  },

  async linkToWorkpaper(contractId: string, workpaperId: string, linkType: string): Promise<ContractWPLink> {
    const { data } = await http.post(P_aip.contracts.linkWorkpaper(contractId), {
      workpaper_id: workpaperId,
      link_type: linkType,
    })
    return data
  },

  async getLinkedWorkpapers(contractId: string): Promise<{ data: ContractWPLink[] }> {
    const { data } = await http.get(P_aip.contracts.links(contractId))
    return data
  },

  async unlinkWorkpaper(linkId: string): Promise<void> {
    await http.delete(P_aip.contracts.unlinkWorkpaper(linkId))
  },

  async getContractSummary(projectId: string): Promise<any> {
    const { data } = await http.get(P_aip.contracts.summary(projectId))
    return data
  },

  async getTaskStatus(taskId: string): Promise<{ status: string; summary?: any }> {
    const { data } = await http.get(P_aip.contracts.taskStatus(taskId))
    return data
  },
}

// ─── Evidence Chain API ───

export const evidenceChain = {
  async verifyChain(projectId: string, chainType: string): Promise<{
    data: {
      nodes: EvidenceChainNode[]
      anomalies: EvidenceAnomaly[]
      summary: EvidenceChainSummary
    }
  }> {
    const { data } = await http.post(P_aip.evidenceChain.verify(projectId, chainType))
    return data
  },

  async analyzeBankStatements(projectId: string): Promise<{ data: any }> {
    const { data } = await http.post(P_aip.evidenceChain.bankAnalysis(projectId))
    return data
  },

  async getChain(projectId: string, chainType: string): Promise<{
    data: {
      nodes: EvidenceChainNode[]
      anomalies: EvidenceAnomaly[]
      summary: EvidenceChainSummary
    }
  }> {
    const { data } = await http.get(P_aip.evidenceChain.get(projectId), {
      params: { type: chainType },
    })
    return data
  },

  async getChainSummary(projectId: string, chainType: string): Promise<EvidenceChainSummary> {
    const { data } = await http.get(P_aip.evidenceChain.summary(projectId, chainType))
    return data
  },
}

// ─── Chat API ───

export const chatApi = {
  async sendMessage(
    sessionId: string,
    message: string,
    useRag: boolean = true
  ): Promise<string> {
    const { data } = await http.post(P_ai.chat.message, {
      session_id: sessionId,
      message,
      use_rag: useRag,
    })
    return data?.content ?? ''
  },

  async sendMessageStream(
    sessionId: string,
    message: string,
    useRag: boolean = true,
    onChunk: (chunk: string) => void
  ): Promise<void> {
    const response = await fetch(P_ai.chat.messageStream, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, use_rag: useRag }),
    })

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      // SSE 解析
      const lines = chunk.split('\n')
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const json = JSON.parse(line.slice(6))
            if (json.delta) onChunk(json.delta)
          } catch {}
        }
      }
    }
  },

  async getChatHistory(projectId: string, sessionId?: string): Promise<any[]> {
    const params: Record<string, string> = {}
    if (sessionId) params.session_id = sessionId
    const { data } = await http.get(P_aip.chatHistory(projectId), { params })
    return data
  },

  async createSession(projectId: string, sessionType: string = 'general'): Promise<{ session_id: string }> {
    const { data } = await http.post(P_ai.chat.sessions, {
      project_id: projectId,
      session_type: sessionType,
    })
    return data
  },

  async deleteSession(sessionId: string): Promise<void> {
    await http.delete(P_ai.chat.deleteSession(sessionId))
  },

  async analyzeFile(projectId: string, file: File): Promise<{ analysis: string }> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('project_id', projectId)
    const { data } = await http.post(P_ai.chat.fileAnalysis, formData)
    return data
  },

  async analyzeFolder(projectId: string, folderPath: string): Promise<{ task_id: string }> {
    const { data } = await http.post(P_ai.chat.folderAnalysis, {
      project_id: projectId,
      folder_path: folderPath,
    })
    return data
  },
}

// ─── Confirmation AI API ───

export const confirmationAI = {
  async verifyAddresses(projectId: string, confirmationType?: string): Promise<{
    data: ConfirmationAIResult[]
  }> {
    const body: any = { project_id: projectId }
    if (confirmationType) body.confirmation_type = confirmationType
    const { data } = await http.post(P_aip.confirmationAI.addressVerify(projectId), body)
    return data
  },

  async ocrReply(
    projectId: string,
    confirmationId: string,
    file: File
  ): Promise<{ data: any }> {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await http.post(P_aip.confirmationAI.ocrReply(projectId, confirmationId), formData)
    return data
  },

  async analyzeMismatch(projectId: string, confirmationId?: string): Promise<{ data: any[] }> {
    const body: any = { project_id: projectId }
    if (confirmationId) body.confirmation_id = confirmationId
    const { data } = await http.post(P_aip.confirmationAI.mismatchAnalysis(projectId), body)
    return data
  },

  async getChecks(projectId: string): Promise<{ data: ConfirmationAIResult[] }> {
    const { data } = await http.get(P_aip.confirmationAI.checks(projectId))
    return data
  },

  async confirmCheck(projectId: string, checkId: string, action: 'accept' | 'reject'): Promise<void> {
    await http.put(P_aip.confirmationAI.confirmCheck(projectId, checkId), { action })
  },

  async runConfirmationAI(projectId: string, confirmationId: string): Promise<void> {
    await http.post(P_aip.confirmationAI.run(projectId, confirmationId))
  },

  async confirmAddress(projectId: string, addressId: string, action: 'accept' | 'reject'): Promise<void> {
    await http.put(P_aip.confirmationAI.confirmAddress(projectId, addressId), { action })
  },
}

// ─── NL Command API ───

export const nlCommand = {
  async parseIntent(userInput: string): Promise<NLIntent> {
    const { data } = await http.post(P_ai.nl.parse, { user_input: userInput })
    return data
  },

  async executeCommand(intent: NLIntent, projectId: string): Promise<any> {
    const { data } = await http.post(P_ai.nl.execute, {
      intent,
      project_id: projectId,
    })
    return data
  },

  async analyzeFile(projectId: string, filePath: string): Promise<any> {
    const { data } = await http.post(P_ai.nl.analyzeFile, {
      file_path: filePath,
      project_id: projectId,
    })
    return data
  },

  async analyzeFolder(projectId: string, folderPath: string): Promise<{ task_id: string }> {
    const { data } = await http.post(P_ai.nl.analyzeFolder, {
      folder_path: folderPath,
      project_id: projectId,
    })
    return data
  },

  async getFolderAnalysisStatus(taskId: string): Promise<{ status: string; result?: any }> {
    const { data } = await http.get(P_ai.nl.analyzeFolderStatus(taskId))
    return data
  },

  async comparePBCList(projectId: string): Promise<{ comparison: any }> {
    const { data } = await http.post(P_ai.nl.comparePbc, { project_id: projectId })
    return data
  },
}

// ─── AI Admin API ───

export const aiAdmin = {
  async getHealth(): Promise<AIHealthResponse> {
    const { data } = await http.get(P_ai.health)
    return data
  },

  async getModels(): Promise<AIModelConfig[]> {
    const { data } = await http.get(P_ai.models.list)
    return data
  },

  async activateModel(modelId: string): Promise<void> {
    await http.put(P_ai.models.activate(modelId))
  },

  async createModel(body: Partial<AIModelConfig>): Promise<AIModelConfig> {
    const { data } = await http.post(P_ai.models.list, body)
    return data
  },

  async evaluateLLM(questions: string[], expectedAnswers?: string[]): Promise<any> {
    const { data } = await http.post(P_ai.evaluate, {
      questions,
      expected_answers: expectedAnswers,
    })
    return data
  },
}

// ─── Knowledge Base API ───

export const knowledgeBase = {
  async search(
    projectId: string,
    query: string,
    topK: number = 10
  ): Promise<{ results: any[] }> {
    const { data } = await http.get(P_ai.chat.knowledge.search, {
      params: { project_id: projectId, query, top_k: topK },
    })
    return data
  },

  async addDocument(
    projectId: string,
    content: string,
    title: string,
    sourceType: string = 'manual'
  ): Promise<void> {
    await http.post(P_ai.chat.knowledge.list, {
      project_id: projectId,
      content,
      title,
      source_type: sourceType,
    })
  },

  async listDocuments(projectId: string): Promise<any[]> {
    const { data } = await http.get(P_ai.chat.knowledge.list, {
      params: { project_id: projectId },
    })
    return data
  },

  async deleteDocument(knowledgeId: string): Promise<void> {
    await http.delete(P_ai.chat.knowledge.delete(knowledgeId))
  },

  async buildIndex(projectId: string): Promise<{ task_id: string }> {
    const { data } = await http.post(P_aip.knowledgeIndex.build(projectId))
    return data
  },

  async getIndexStatus(projectId: string): Promise<{ status: string; document_count: number }> {
    const { data } = await http.get(P_aip.knowledgeIndex.status(projectId))
    return data
  },
}

// ─── Default export ───

const aiApi = {
  ocr: ocrApi,
  workpaper: workpaperAI,
  contract: contractAI,
  evidenceChain,
  chat: chatApi,
  confirmationAI,
  nlCommand,
  aiAdmin,
  knowledgeBase,
}

export default aiApi
export { aiApi }
