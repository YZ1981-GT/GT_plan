/**
 * useNoteAi — AI 续写 / 改写 / 知识库选取
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  noteAiContinueWrite,
  noteAiRewrite,
  noteAiGeneratePolicy,
  noteAiGenerateAnalysis,
} from '@/services/commonApi'
import { useKnowledge } from '@/composables/useKnowledge'
import { handleApiError } from '@/utils/errorHandler'

export interface UseNoteAiOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
  templateType: Ref<string>
  currentNote: Ref<{ note_section: string } | null>
  editor: Ref<any>
}

export interface UseNoteAiReturn {
  aiLoading: Ref<boolean>
  aiRewriteDialogVisible: Ref<boolean>
  aiRewriteInstruction: Ref<string>
  aiSelectedText: Ref<string>
  /** 已选参考文档的名称摘要（仅界面回显；非空即「已加载」） */
  knowledgeContextText: Ref<string>
  knowledgeDocCount: Ref<number>
  /** 已选参考文档 ID —— 续写 / 改写时交给后端逐篇判权后读正文 */
  knowledgeDocIds: Ref<string[]>
  onAiContinueWrite: () => Promise<void>
  onAiRewriteOpen: () => void
  onAiRewriteConfirm: () => Promise<void>
  onAiGeneratePolicy: () => Promise<void>
  onAiGenerateAnalysis: () => Promise<void>
  onPickKnowledge: () => Promise<void>
  clearKnowledgeContext: () => void
  getSelectedText: () => string
}

export function useNoteAi(options: UseNoteAiOptions): UseNoteAiReturn {
  const { projectId, year, templateType, currentNote, editor } = options

  const aiLoading = ref(false)
  const aiRewriteDialogVisible = ref(false)
  const aiRewriteInstruction = ref('请改写以下文本，使其更加专业规范')
  const aiSelectedText = ref('')

  // ── 知识库上下文 ──
  // 只在前端保留「选了哪几篇」：正文由后端按 ID 逐篇判权后读取并注入 LLM
  // （spec knowledge-upload-robustness-and-consumer-wiring R6.2）。旧实现把前端拼好的
  // `knowledge_context` 文本发给后端，而后端请求模型根本没有这个字段 —— 被静默丢弃。
  const { pickDocuments } = useKnowledge()
  const knowledgeContextText = ref('')
  const knowledgeDocCount = ref(0)
  const knowledgeDocIds = ref<string[]>([])

  function getSelectedText(): string {
    if (!editor.value) return ''
    const { from, to } = editor.value.state.selection
    if (from === to) return ''
    return editor.value.state.doc.textBetween(from, to, ' ')
  }

  function getFullText(): string {
    return editor.value?.getText() || ''
  }

  async function onPickKnowledge() {
    const docs = await pickDocuments({ title: '选择参考文档（AI续写/改写时使用）', maxSelect: 5 })
    if (docs.length) {
      knowledgeDocIds.value = docs.map((d) => d.id)
      knowledgeContextText.value = docs.map((d) => d.name).join('、')
      knowledgeDocCount.value = docs.length
      ElMessage.success(`已选 ${docs.length} 篇参考文档，续写 / 改写时 AI 将参考它们`)
    }
  }

  function clearKnowledgeContext() {
    knowledgeContextText.value = ''
    knowledgeDocCount.value = 0
    knowledgeDocIds.value = []
  }

  /**
   * 选了参考文档却一篇都没用上（全部不可见 / 已删除 / 无正文）时如实告知；
   * 否则用户会以为 AI 参考了资料。部分可用时说明实际篇数。
   */
  function reportKnowledgeUsage(used: number | undefined, verb: string): void {
    const selected = knowledgeDocIds.value.length
    if (!selected || used === undefined) {
      ElMessage.success(`${verb}完成`)
      return
    }
    if (used === 0) {
      ElMessage.warning(`${verb}完成，但所选 ${selected} 篇参考文档均不可用（无权访问、已删除或未提取到正文），本次未参考`)
      return
    }
    ElMessage.success(used < selected ? `${verb}完成（参考了 ${used}/${selected} 篇文档）` : `${verb}完成（参考了 ${used} 篇文档）`)
  }

  async function onAiContinueWrite() {
    const text = getFullText()
    if (!text.trim()) { ElMessage.warning('请先输入一些内容再续写'); return }
    aiLoading.value = true
    try {
      const res = await noteAiContinueWrite(projectId.value, {
        text,
        section_number: currentNote.value?.note_section || '',
        year: year.value,
        knowledge_doc_ids: knowledgeDocIds.value,
      })
      if (res.error) { ElMessage.warning(res.error); return }
      if (res.appended) {
        editor.value?.commands.insertContent(res.appended)
        reportKnowledgeUsage(res.knowledge_count, '续写')
      }
    } catch (e: any) {
      handleApiError(e, 'AI续写')
    } finally {
      aiLoading.value = false
    }
  }

  function onAiRewriteOpen() {
    const sel = getSelectedText()
    if (!sel.trim()) { ElMessage.warning('请先选中要改写的文本'); return }
    aiSelectedText.value = sel
    aiRewriteInstruction.value = '请改写以下文本，使其更加专业规范'
    aiRewriteDialogVisible.value = true
  }

  async function onAiRewriteConfirm() {
    if (!aiSelectedText.value.trim()) return
    aiLoading.value = true
    try {
      const res = await noteAiRewrite(projectId.value, {
        text: aiSelectedText.value,
        instruction: aiRewriteInstruction.value,
        section_number: currentNote.value?.note_section || '',
        year: year.value,
        knowledge_doc_ids: knowledgeDocIds.value,
      })
      if (res.error) { ElMessage.warning(res.error); return }
      if (res.rewritten && res.rewritten !== res.original) {
        // 替换选中文本
        const { from, to } = editor.value!.state.selection
        editor.value!.chain().focus().deleteRange({ from, to }).insertContent(res.rewritten).run()
        reportKnowledgeUsage(res.knowledge_count, '改写')
      }
    } catch (e: any) {
      handleApiError(e, 'AI改写')
    } finally {
      aiLoading.value = false
      aiRewriteDialogVisible.value = false
    }
  }

  async function onAiGeneratePolicy() {
    aiLoading.value = true
    try {
      const res = await noteAiGeneratePolicy(projectId.value, {
        section_number: currentNote.value?.note_section || '',
        template_type: templateType.value || 'soe',
        year: year.value,
      })
      if (res.generated_text) {
        editor.value?.commands.setContent(res.generated_text)
        ElMessage.success(`会计政策已生成（参照${res.reference_count}篇文档）`)
      }
    } catch (e: any) {
      handleApiError(e, '生成会计政策')
    } finally {
      aiLoading.value = false
    }
  }

  async function onAiGenerateAnalysis() {
    aiLoading.value = true
    try {
      const res = await noteAiGenerateAnalysis(projectId.value, {
        section_number: currentNote.value?.note_section || '',
        year: year.value,
      })
      if (res.generated_text) {
        editor.value?.commands.insertContent('\n\n' + res.generated_text)
        ElMessage.success('变动分析已生成')
      }
    } catch (e: any) {
      handleApiError(e, '生成变动分析')
    } finally {
      aiLoading.value = false
    }
  }

  return {
    aiLoading,
    aiRewriteDialogVisible,
    aiRewriteInstruction,
    aiSelectedText,
    knowledgeContextText,
    knowledgeDocCount,
    knowledgeDocIds,
    onAiContinueWrite,
    onAiRewriteOpen,
    onAiRewriteConfirm,
    onAiGeneratePolicy,
    onAiGenerateAnalysis,
    onPickKnowledge,
    clearKnowledgeContext,
    getSelectedText,
  }
}
