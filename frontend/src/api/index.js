/**
 * AI 平台 API 封装
 * 封装所有 AI 相关功能的后端 API 调用
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

// ============ 通用工具 ============

async function request(path, options = {}) {
  const token = localStorage.getItem('access_token')
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// ============ AI 管理 API ============

export const aiAdmin = {
  /** 获取 AI 模型列表 */
  listModels: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/ai-admin/models${qs ? '?' + qs : ''}`)
  },

  /** 获取单个模型详情 */
  getModel: (modelId) => request(`/ai-admin/models/${modelId}`),

  /** 创建模型配置 */
  createModel: (data) => request('/ai-admin/models', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 更新模型配置 */
  updateModel: (modelId, data) => request(`/ai-admin/models/${modelId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  /** 删除模型 */
  deleteModel: (modelId) => request(`/ai-admin/models/${modelId}`, {
    method: 'DELETE',
  }),

  /** 测试模型连接 */
  testModel: (modelId) => request(`/ai-admin/models/${modelId}/test`, {
    method: 'POST',
  }),

  /** 列出已配置的提供商 */
  listProviders: () => request('/ai-admin/providers'),

  /** 获取模型使用统计 */
  getUsageStats: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/ai-admin/usage${qs ? '?' + qs : ''}`)
  },

  /** 获取对话历史 */
  getChatHistory: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/ai-admin/chat-history${qs ? '?' + qs : ''}`)
  },

  /** 清空调试日志 */
  clearLogs: () => request('/ai-admin/logs', { method: 'DELETE' }),
}

// ============ OCR API ============

export const aiOCR = {
  /** 上传文档进行 OCR 识别 */
  upload: (formData, onProgress) => {
    const token = localStorage.getItem('access_token')
    return fetch(`${BASE_URL}/ai/ocr/upload`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: formData,
    })
  },

  /** 批量处理文档 */
  batchProcess: (files, projectId, docType = 'invoice') => {
    const formData = new FormData()
    files.forEach(f => formData.append('files', f))
    formData.append('project_id', projectId)
    formData.append('document_type', docType)

    const token = localStorage.getItem('access_token')
    return fetch(`${BASE_URL}/ai/ocr/batch`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: formData,
    })
  },

  /** 获取识别记录 */
  getScan: (scanId) => request(`/ai/ocr/scans/${scanId}`),

  /** 获取提取的字段 */
  getExtractedFields: (scanId) => request(`/ai/ocr/scans/${scanId}/fields`),

  /** 更新字段值 */
  updateField: (scanId, fieldId, value) => request(
    `/ai/ocr/scans/${scanId}/fields/${fieldId}`,
    { method: 'PATCH', body: JSON.stringify({ value }) }
  ),

  /** 列出项目的扫描记录 */
  listScans: (projectId, params = {}) => {
    const qs = new URLSearchParams({ project_id: projectId, ...params }).toString()
    return request(`/ai/ocr/scans?${qs}`)
  },

  /** 删除扫描记录 */
  deleteScan: (scanId) => request(`/ai/ocr/scans/${scanId}`, { method: 'DELETE' }),
}

// ============ 底稿填充 API ============

export const aiWorkpaper = {
  /** 创建填充任务 */
  createFillTask: (data) => request('/ai/workpaper/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 获取任务详情 */
  getTask: (taskId) => request(`/ai/workpaper/tasks/${taskId}`),

  /** 获取填充结果 */
  getResult: (taskId) => request(`/ai/workpaper/tasks/${taskId}/result`),

  /** 列出填充任务 */
  listTasks: (projectId, params = {}) => {
    const qs = new URLSearchParams({ project_id: projectId, ...params }).toString()
    return request(`/ai/workpaper/tasks?${qs}`)
  },
}

// ============ 合同分析 API ============

export const aiContract = {
  /** 分析合同文本 */
  analyze: (data) => request('/ai/contract/analyze', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 上传合同文件并分析 */
  analyzeFile: (formData) => {
    const token = localStorage.getItem('access_token')
    return fetch(`${BASE_URL}/ai/contract/analyze/file`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: formData,
    })
  },

  /** 获取分析报告 */
  getReport: (reportId) => request(`/ai/contract/reports/${reportId}`),

  /** 列出分析报告 */
  listReports: (projectId, params = {}) => {
    const qs = new URLSearchParams({ project_id: projectId, ...params }).toString()
    return request(`/ai/contract/reports?${qs}`)
  },
}

// ============ 证据链 API ============

export const aiEvidenceChain = {
  /** 创建证据链 */
  createChain: (data) => request('/ai/evidence-chain/chains', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 添加证据项 */
  addItem: (data) => request('/ai/evidence-chain/items', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 关联证据项 */
  linkItems: (data) => request('/ai/evidence-chain/link', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** AI 分析证据链 */
  analyze: (chainId) => request(`/ai/evidence-chain/analyze/${chainId}`, {
    method: 'POST',
  }),

  /** 获取证据链详情 */
  getChain: (chainId, params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/ai/evidence-chain/chains/${chainId}${qs ? '?' + qs : ''}`)
  },

  /** 列出证据链 */
  listChains: (projectId, params = {}) => {
    const qs = new URLSearchParams({ project_id: projectId, ...params }).toString()
    return request(`/ai/evidence-chain/chains?${qs}`)
  },

  /** 更新证据项完整性 */
  updateCompleteness: (itemId, completeness) => request(
    `/ai/evidence-chain/items/${itemId}/completeness?completeness=${completeness}`,
    { method: 'PATCH' }
  ),
}

// ============ AI 问答 API ============

export const aiChat = {
  /** 创建会话 */
  createSession: (data) => request('/ai/chat/sessions', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 获取会话详情 */
  getSession: (sessionId) => request(`/ai/chat/sessions/${sessionId}`),

  /** 发送消息（非流式） */
  sendMessage: (data) => request('/ai/chat/message', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 发送消息（流式） */
  sendMessageStream(data) {
    const token = localStorage.getItem('access_token')
    const eventSource = new EventSourceWithBody(
      `${BASE_URL}/ai/chat/message/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(data),
      }
    )
    return eventSource
  },

  /** 列出会话 */
  listSessions: (projectId, params = {}) => {
    const qs = new URLSearchParams({ project_id: projectId, ...params }).toString()
    return request(`/ai/chat/sessions?${qs}`)
  },

  /** 删除会话 */
  deleteSession: (sessionId) => request(`/ai/chat/sessions/${sessionId}`, {
    method: 'DELETE',
  }),
}

// ============ 函证审核 API ============

export const aiConfirmation = {
  /** 审核函证 */
  audit: (data) => request('/ai/confirmation/audit', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 获取审核记录 */
  getAudit: (auditId) => request(`/ai/confirmation/audit/${auditId}`),

  /** 列出审核记录 */
  listAudits: (projectId, params = {}) => {
    const qs = new URLSearchParams({ project_id: projectId, ...params }).toString()
    return request(`/ai/confirmation/audits?${qs}`)
  },
}

// ============ 知识库 API ============

export const aiKnowledge = {
  /** 添加知识文档 */
  addDocument: (data) => request('/ai/chat/knowledge', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** 检索知识库 */
  search: (projectId, query, topK = 5) => {
    const qs = new URLSearchParams({ project_id: projectId, query, top_k: topK }).toString()
    return request(`/ai/chat/knowledge/search?${qs}`)
  },

  /** 列出知识文档 */
  list: (projectId, params = {}) => {
    const qs = new URLSearchParams({ project_id: projectId, ...params }).toString()
    return request(`/ai/chat/knowledge?${qs}`)
  },

  /** 删除知识文档 */
  delete: (knowledgeId) => request(`/ai/chat/knowledge/${knowledgeId}`, {
    method: 'DELETE',
  }),
}

// ============ SSE 流式请求工具 ============

class EventSourceWithBody extends EventTarget {
  constructor(url, options = {}) {
    super()
    this.url = url
    this.options = options
    this.connected = false
    this.connect()
  }

  connect() {
    // 使用 fetch + ReadableStream 实现带 body 的 SSE
    fetch(this.url, this.options)
      .then(response => {
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        const read = () => {
          reader.read().then(({ done, value }) => {
            if (done) {
              this.dispatchEvent(new CustomEvent('close'))
              return
            }

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6)
                try {
                  const parsed = JSON.parse(data)
                  if (parsed.done) {
                    this.dispatchEvent(new CustomEvent('done', { detail: parsed }))
                  } else if (parsed.error) {
                    this.dispatchEvent(new CustomEvent('error', { detail: new Error(parsed.error) }))
                  } else {
                    this.dispatchEvent(new CustomEvent('message', { detail: parsed }))
                  }
                } catch (e) {
                  // 非 JSON 数据
                  this.dispatchEvent(new CustomEvent('chunk', { detail: data }))
                }
              }
            }

            read()
          })
        }

        read()
        this.connected = true
        this.dispatchEvent(new CustomEvent('open'))
      })
      .catch(err => {
        this.dispatchEvent(new CustomEvent('error', { detail: err }))
      })
  }

  close() {
    this.connected = false
  }
}

export default {
  aiAdmin,
  aiOCR,
  aiWorkpaper,
  aiContract,
  aiEvidenceChain,
  aiChat,
  aiConfirmation,
  aiKnowledge,
}
