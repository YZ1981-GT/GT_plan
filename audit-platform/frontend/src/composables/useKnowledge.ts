/**
 * useKnowledge — 全局知识库调用 composable [R3.7]
 *
 * 提供统一的知识库交互能力：
 * - search(query, category?)：搜索知识库文档
 * - getDocContent(category, docId)：获取文档内容
 * - pickDocuments()：打开 KnowledgePickerDialog 选择文档
 * - buildContext(selectedDocs)：将选中文档构建为 AI 上下文字符串
 *
 * 用法：
 *   const { search, pickDocuments, buildContext } = useKnowledge()
 *   const docs = await pickDocuments()
 *   const context = await buildContext(docs)
 *
 * @module composables/useKnowledge
 * @see R3.7
 */
import { ref, shallowRef } from 'vue'
import { api } from '@/services/apiProxy'
import { knowledge as P_kb } from '@/services/apiPaths'

// ── 类型定义 ──

export interface KnowledgeDoc {
  id: string
  name: string
  category?: string
  folder_id?: string
  folder_name?: string
  file_type?: string
  file_size?: number
  created_at?: string
  /** 搜索结果中的摘要片段 */
  snippet?: string
  /** 文档正文内容（getDocContent 后填充） */
  content?: string
}

export interface PickDocumentsOptions {
  /** 限定分类（可选） */
  category?: string
  /** 弹窗标题 */
  title?: string
  /** 最大可选数量，默认 5 */
  maxSelect?: number
}

// ── 内部状态：KnowledgePickerDialog 的 resolve/reject ──

type PickerResolve = (docs: KnowledgeDoc[]) => void
type PickerReject = (reason?: any) => void

let _pickerResolve: PickerResolve | null = null
let _pickerReject: PickerReject | null = null

/** 弹窗可见性（由 KnowledgePickerDialog 绑定） */
export const knowledgePickerVisible = ref(false)
/** 弹窗选项（由 KnowledgePickerDialog 读取） */
export const knowledgePickerOptions = shallowRef<PickDocumentsOptions>({})

/**
 * 由 KnowledgePickerDialog 调用：用户确认选择
 */
export function _resolvePickerSelection(docs: KnowledgeDoc[]) {
  knowledgePickerVisible.value = false
  _pickerResolve?.(docs)
  _pickerResolve = null
  _pickerReject = null
}

/**
 * 由 KnowledgePickerDialog 调用：用户取消
 */
export function _rejectPickerSelection() {
  knowledgePickerVisible.value = false
  _pickerReject?.()
  _pickerResolve = null
  _pickerReject = null
}

// ── Composable ──

export function useKnowledge() {
  const searching = ref(false)
  const searchResults = ref<KnowledgeDoc[]>([])

  /**
   * 搜索知识库
   * @param query 搜索关键词
   * @param category 可选分类过滤
   */
  async function search(query: string, category?: string): Promise<KnowledgeDoc[]> {
    if (!query.trim()) return []
    searching.value = true
    try {
      const params: Record<string, string> = { q: query }
      if (category) params.category = category
      const data = await api.get<any>(P_kb.search, { params })
      const results: KnowledgeDoc[] = Array.isArray(data) ? data : data?.results || []
      searchResults.value = results
      return results
    } catch {
      searchResults.value = []
      return []
    } finally {
      searching.value = false
    }
  }

  /**
   * 获取文档内容
   * @param category 文档分类
   * @param docId 文档 ID
   */
  async function getDocContent(category: string, docId: string): Promise<string> {
    try {
      const data = await api.get<any>(P_kb.doc(category, docId))
      return data?.content || data?.text || (typeof data === 'string' ? data : '')
    } catch {
      return ''
    }
  }

  /**
   * 打开知识库文档选择弹窗，返回用户选中的文档列表
   * 如果用户取消则返回空数组
   */
  async function pickDocuments(options?: PickDocumentsOptions): Promise<KnowledgeDoc[]> {
    knowledgePickerOptions.value = options || {}
    knowledgePickerVisible.value = true
    return new Promise<KnowledgeDoc[]>((resolve, reject) => {
      _pickerResolve = resolve
      _pickerReject = reject
    }).catch(() => [])
  }

  /**
   * 将选中的文档构建为 AI 上下文字符串
   * 格式：每个文档以 --- 分隔，包含标题和内容
   */
  async function buildContext(docs: KnowledgeDoc[]): Promise<string> {
    if (!docs.length) return ''

    const parts: string[] = []
    for (const doc of docs) {
      let content = doc.content || ''
      // 如果文档没有内容，尝试获取
      if (!content && doc.category && doc.id) {
        content = await getDocContent(doc.category, doc.id)
      }
      // 如果还是没有内容但有 snippet，用 snippet
      if (!content && doc.snippet) {
        content = doc.snippet
      }
      if (content) {
        parts.push(`【${doc.name}】\n${content}`)
      }
    }

    if (!parts.length) return ''
    return `--- 知识库参考资料 ---\n${parts.join('\n\n---\n\n')}\n--- 参考资料结束 ---`
  }

  return {
    searching,
    searchResults,
    search,
    getDocContent,
    pickDocuments,
    buildContext,
  }
}
