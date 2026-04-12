/**
 * AI 功能 Composable
 * 提供 Vue 3 组合式 API，管理 AI 功能的状态和交互
 */

import { ref, computed } from 'vue'
import {
  aiAdmin,
  aiOCR,
  aiWorkpaper,
  aiContract,
  aiEvidenceChain,
  aiChat,
  aiConfirmation,
  aiKnowledge,
} from '@/api'

// ============ AI 管理 ============

export function useAIAdmin() {
  const models = ref([])
  const loading = ref(false)
  const error = ref(null)

  async function fetchModels(params = {}) {
    loading.value = true
    error.value = null
    try {
      models.value = await aiAdmin.listModels(params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function createModel(data) {
    const model = await aiAdmin.createModel(data)
    models.value.unshift(model)
    return model
  }

  async function updateModel(modelId, data) {
    const updated = await aiAdmin.updateModel(modelId, data)
    const idx = models.value.findIndex(m => m.model_id === modelId || m.id === modelId)
    if (idx >= 0) models.value[idx] = updated
    return updated
  }

  async function deleteModel(modelId) {
    await aiAdmin.deleteModel(modelId)
    models.value = models.value.filter(m => m.model_id !== modelId && m.id !== modelId)
  }

  async function testModel(modelId) {
    return aiAdmin.testModel(modelId)
  }

  return { models, loading, error, fetchModels, createModel, updateModel, deleteModel, testModel }
}

// ============ OCR ============

export function useAIOCR() {
  const scans = ref([])
  const currentScan = ref(null)
  const loading = ref(false)
  const progress = ref(0)
  const error = ref(null)

  async function uploadDocument(formData, onProgress) {
    loading.value = true
    error.value = null
    progress.value = 0

    try {
      const response = await aiOCR.upload(formData, (p) => {
        progress.value = p
        if (onProgress) onProgress(p)
      })
      const result = await response.json()
      currentScan.value = result
      scans.value.unshift(result)
      return result
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchScans(projectId, params = {}) {
    loading.value = true
    error.value = null
    try {
      scans.value = await aiOCR.listScans(projectId, params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function getScanDetails(scanId) {
    loading.value = true
    try {
      currentScan.value = await aiOCR.getScan(scanId)
      return currentScan.value
    } finally {
      loading.value = false
    }
  }

  async function updateExtractedField(scanId, fieldId, value) {
    return aiOCR.updateField(scanId, fieldId, value)
  }

  async function batchProcess(files, projectId, docType) {
    loading.value = true
    error.value = null
    try {
      const response = await aiOCR.batchProcess(files, projectId, docType)
      return await response.json()
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    scans,
    currentScan,
    loading,
    progress,
    error,
    uploadDocument,
    fetchScans,
    getScanDetails,
    updateExtractedField,
    batchProcess,
  }
}

// ============ 底稿填充 ============

export function useAIWorkpaper() {
  const tasks = ref([])
  const currentTask = ref(null)
  const loading = ref(false)
  const error = ref(null)

  async function createFillTask(data) {
    loading.value = true
    error.value = null
    try {
      const result = await aiWorkpaper.createFillTask(data)
      currentTask.value = result
      return result
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchTasks(projectId, params = {}) {
    loading.value = true
    try {
      tasks.value = await aiWorkpaper.listTasks(projectId, params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function getTaskResult(taskId) {
    return aiWorkpaper.getResult(taskId)
  }

  return { tasks, currentTask, loading, error, createFillTask, fetchTasks, getTaskResult }
}

// ============ 合同分析 ============

export function useAIContract() {
  const reports = ref([])
  const currentReport = ref(null)
  const loading = ref(false)
  const error = ref(null)

  async function analyzeContract(data) {
    loading.value = true
    error.value = null
    try {
      const result = await aiContract.analyze(data)
      currentReport.value = result
      return result
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function analyzeFile(formData) {
    loading.value = true
    error.value = null
    try {
      const response = await aiContract.analyzeFile(formData)
      return await response.json()
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchReports(projectId, params = {}) {
    loading.value = true
    try {
      reports.value = await aiContract.listReports(projectId, params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function getReport(reportId) {
    loading.value = true
    try {
      currentReport.value = await aiContract.getReport(reportId)
      return currentReport.value
    } finally {
      loading.value = false
    }
  }

  return { reports, currentReport, loading, error, analyzeContract, analyzeFile, fetchReports, getReport }
}

// ============ 证据链 ============

export function useAIEvidenceChain() {
  const chains = ref([])
  const currentChain = ref(null)
  const loading = ref(false)
  const analysisResult = ref(null)
  const error = ref(null)

  async function createChain(data) {
    const chain = await aiEvidenceChain.createChain(data)
    chains.value.unshift(chain)
    return chain
  }

  async function addEvidenceItem(data) {
    return aiEvidenceChain.addItem(data)
  }

  async function analyzeChain(chainId) {
    loading.value = true
    error.value = null
    try {
      analysisResult.value = await aiEvidenceChain.analyze(chainId)
      return analysisResult.value
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchChains(projectId, params = {}) {
    loading.value = true
    try {
      chains.value = await aiEvidenceChain.listChains(projectId, params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function getChainDetails(chainId, params = {}) {
    loading.value = true
    try {
      currentChain.value = await aiEvidenceChain.getChain(chainId, params)
      return currentChain.value
    } finally {
      loading.value = false
    }
  }

  return {
    chains,
    currentChain,
    loading,
    analysisResult,
    error,
    createChain,
    addEvidenceItem,
    analyzeChain,
    fetchChains,
    getChainDetails,
  }
}

// ============ AI 问答（对话） ============

export function useAIChat() {
  const sessions = ref([])
  const currentSession = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const streaming = ref(false)
  const error = ref(null)
  let eventSource = null

  async function createSession(projectId, sessionType = 'general') {
    const session = await aiChat.createSession({
      project_id: projectId,
      session_type: sessionType,
    })
    sessions.value.unshift(session)
    currentSession.value = session
    messages.value = []
    return session
  }

  async function fetchSessions(projectId) {
    loading.value = true
    try {
      sessions.value = await aiChat.listSessions(projectId)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function loadSession(sessionId) {
    loading.value = true
    try {
      const data = await aiChat.getSession(sessionId)
      currentSession.value = { session_id: sessionId, ...data }
      messages.value = data.messages || []
      return data
    } finally {
      loading.value = false
    }
  }

  async function sendMessage(sessionId, message, useRag = true) {
    loading.value = true
    error.value = null
    try {
      const result = await aiChat.sendMessage({
        session_id: sessionId,
        message,
        use_rag: useRag,
      })
      messages.value.push({ role: 'user', content: message })
      messages.value.push({ role: 'assistant', content: result.content })
      return result
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  function sendMessageStream(sessionId, message, useRag = true) {
    return new Promise((resolve, reject) => {
      streaming.value = true
      error.value = null
      messages.value.push({ role: 'user', content: message, pending: true })

      const assistantMsg = { role: 'assistant', content: '', pending: true }
      messages.value.push(assistantMsg)
      const assistantIdx = messages.value.length - 1

      eventSource = aiChat.sendMessageStream({
        session_id: sessionId,
        message,
        use_rag: useRag,
      })

      eventSource.addEventListener('message', (e) => {
        const delta = e.detail.delta || ''
        messages.value[assistantIdx].content += delta
      })

      eventSource.addEventListener('done', (e) => {
        messages.value[assistantIdx].pending = false
        streaming.value = false
        resolve(e.detail)
      })

      eventSource.addEventListener('error', (e) => {
        messages.value[assistantIdx].pending = false
        streaming.value = false
        error.value = e.detail?.message || 'Stream error'
        reject(e.detail)
      })

      eventSource.addEventListener('open', () => {
        messages.value[assistantIdx].pending = true
      })
    })
  }

  function stopStream() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    streaming.value = false
  }

  async function deleteSession(sessionId) {
    await aiChat.deleteSession(sessionId)
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    if (currentSession.value?.session_id === sessionId) {
      currentSession.value = null
      messages.value = []
    }
  }

  return {
    sessions,
    currentSession,
    messages,
    loading,
    streaming,
    error,
    createSession,
    fetchSessions,
    loadSession,
    sendMessage,
    sendMessageStream,
    stopStream,
    deleteSession,
  }
}

// ============ 函证审核 ============

export function useAIConfirmation() {
  const audits = ref([])
  const currentAudit = ref(null)
  const loading = ref(false)
  const error = ref(null)

  async function auditConfirmation(data) {
    loading.value = true
    error.value = null
    try {
      const result = await aiConfirmation.audit(data)
      currentAudit.value = result
      return result
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchAudits(projectId, params = {}) {
    loading.value = true
    try {
      audits.value = await aiConfirmation.listAudits(projectId, params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function getAuditDetails(auditId) {
    loading.value = true
    try {
      currentAudit.value = await aiConfirmation.getAudit(auditId)
      return currentAudit.value
    } finally {
      loading.value = false
    }
  }

  return { audits, currentAudit, loading, error, auditConfirmation, fetchAudits, getAuditDetails }
}

// ============ 知识库 ============

export function useAIKnowledge() {
  const documents = ref([])
  const searchResults = ref([])
  const loading = ref(false)
  const error = ref(null)

  async function addDocument(data) {
    loading.value = true
    try {
      const result = await aiKnowledge.addDocument(data)
      documents.value.unshift(result)
      return result
    } finally {
      loading.value = false
    }
  }

  async function search(projectId, query, topK = 5) {
    loading.value = true
    error.value = null
    try {
      searchResults.value = await aiKnowledge.search(projectId, query, topK)
      return searchResults.value
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchDocuments(projectId, params = {}) {
    loading.value = true
    try {
      documents.value = await aiKnowledge.list(projectId, params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function deleteDocument(knowledgeId) {
    await aiKnowledge.delete(knowledgeId)
    documents.value = documents.value.filter(d => d.knowledge_id !== knowledgeId)
  }

  return { documents, searchResults, loading, error, addDocument, search, fetchDocuments, deleteDocument }
}
