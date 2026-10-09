/**
 * useKnowledge — 全局知识库调用 composable [R3.7]
 *
 * 提供统一的知识库交互能力：
 * - search(query, context?)：带权限的知识库全文搜索（文档名 / 正文 / 标签）
 * - getDocContent(docId)：读取文档正文（预览接口，不可读与不存在同构 404）
 * - pickDocuments()：打开 KnowledgePickerDialog 选择文档
 *
 * 用法：
 *   const { pickDocuments } = useKnowledge()
 *   const docs = await pickDocuments()
 *   // 把 docs.map(d => d.id) 交给后端，由后端逐篇判权后读正文注入 AI（见 useNoteAi）
 *
 * 🔴 2026-09-30 修复（spec knowledge-upload-robustness-and-consumer-wiring R6）：
 * 旧实现调 `/api/knowledge/search` 与 `/api/knowledge/{分类}/{id}` —— 后端**从未有过**这两条路由，
 * 附注 / 审计报告编辑器的「📚 知识库」恒显示「未找到匹配的文档」（404 被 catch 吞成空列表）。
 * 旧 `buildContext` 在前端拼正文交给 AI 的做法同时废弃：客户端文本不可信，
 * 且它依赖的取正文接口同样不存在（实际只把 200 字片段当成了全文）。
 *
 * @module composables/useKnowledge
 * @see R3.7
 */
import { ref, shallowRef } from 'vue'
import { api } from '@/services/apiProxy'
import { knowledgeLibrary as P_kl } from '@/services/apiPaths'

// ── 类型定义 ──

/** 知识库搜索结果（`GET /api/knowledge-library/search` 的行） */
export interface KnowledgeDoc {
  id: string
  name: string
  folder_id?: string
  folder_name?: string
  /** 所在文件夹路径（`/根/…/当前`） */
  folder_path?: string
  file_type?: string
  file_size?: number
  created_at?: string
  /** 命中片段（≤200 字） */
  snippet?: string
  score?: number
}

export interface PickDocumentsOptions {
  /** 弹窗标题 */
  title?: string
  /** 最大可选数量，默认 5（与后端 knowledge_doc_ids 上限一致） */
  maxSelect?: number
}

// ── 内部状态：KnowledgePickerDialog 的 resolve/reject ──

type PickerResolve = (docs: KnowledgeDoc[]) => void
type PickerReject = (reason?: any) => void

/**
 * 单例 Promise 回调：同一时刻只能有一个 pickDocuments() 调用处于等待状态。
 * 如果同一页面有两处同时调用 pickDocuments()，后一次会覆盖前一次的 resolve/reject，
 * 导致前一次调用永远不会 resolve。使用时应确保同一时刻只有一个弹窗实例。
 */
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
   * 搜索知识库（后端按当前用户可读过滤）
   * @param query 搜索关键词
   * @param context 上下文词（底稿编码 / 科目名），只参与排序加分，不参与召回
   */
  async function search(query: string, context?: string): Promise<KnowledgeDoc[]> {
    if (!query.trim()) return []
    searching.value = true
    try {
      const params: Record<string, string> = { q: query.trim() }
      if (context) params.context = context
      const data = await api.get<any>(P_kl.search, { params })
      const results: KnowledgeDoc[] = Array.isArray(data) ? data : []
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
   * 读取文档正文；非文本类（无抽取正文）或不可读时返回空串
   * @param docId 文档 ID
   */
  async function getDocContent(docId: string): Promise<string> {
    try {
      const data = await api.get<any>(P_kl.documentPreview(docId), { _silent: true } as any)
      return data?.preview_type === 'text' ? String(data?.content || '') : ''
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

  return {
    searching,
    searchResults,
    search,
    getDocContent,
    pickDocuments,
  }
}
