/**
 * useL1AiNote — L1 各 sheet 「审计说明 + 审计结论」文本区 + AI 辅助 composable
 *
 * 源模板每张底稿末尾均有「三/四、审计说明」「四/五、审计结论」段落，
 * 但 L1-1 审定表 / L1-2 明细表 / L1-5 利息测算 / L1-6 合同检查 曾缺失该段。
 * 本 composable 统一提供：
 * - note / conclusion 双文本 ref
 * - load(): 从 formData.getItemValue 恢复（依赖父入口已完成 selfLoad）
 * - onNoteInput / onConclusionInput: debounce 持久化到 checklist_responses
 * - generateNote / generateConclusion: 调统一 /ai/generate-text 端点
 *
 * item_id 命名：L1-{sheetKey}-note / L1-{sheetKey}-conclusion
 *
 * 🔴 /ai/generate-text 的 context 类型是 dict[str,str]，
 *    所有 context 值必须转字符串，否则 422 Unprocessable Entity。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import type { useL1FormData } from '@/composables/useL1FormData'

export interface UseL1AiNoteReturn {
  note: Ref<string>
  conclusion: Ref<string>
  aiNoteLoading: Ref<boolean>
  aiConclusionLoading: Ref<boolean>
  load: () => void
  onNoteInput: (val: string) => void
  onConclusionInput: (val: string) => void
  generateNote: (prompt: string, context?: Record<string, unknown>) => Promise<void>
  generateConclusion: (prompt: string, context?: Record<string, unknown>) => Promise<void>
}

/**
 * @param formData  由父入口 provide 的 useL1FormData 实例
 * @param wpId      工作底稿 id（AI 端点用）
 * @param sheetKey  sheet 短标识（如 adj / det / int / con），组成 item_id 前缀
 * @param isReadonly 只读态 ref（只读时不持久化/不 AI）
 */
export function useL1AiNote(
  formData: ReturnType<typeof useL1FormData>,
  wpId: Ref<string>,
  sheetKey: string,
  isReadonly: Ref<boolean>,
): UseL1AiNoteReturn {
  const note = ref('')
  const conclusion = ref('')
  const aiNoteLoading = ref(false)
  const aiConclusionLoading = ref(false)

  const noteId = `L1-${sheetKey}-note`
  const conclusionId = `L1-${sheetKey}-conclusion`

  function load(): void {
    note.value = formData.getItemValue(noteId) ?? ''
    conclusion.value = formData.getItemValue(conclusionId) ?? ''
  }

  function onNoteInput(val: string): void {
    note.value = val
    if (isReadonly.value) return
    formData.debounceSave([{ item_id: noteId, conclusion: null, remark: val || null }])
  }

  function onConclusionInput(val: string): void {
    conclusion.value = val
    if (isReadonly.value) return
    formData.debounceSave([{ item_id: conclusionId, conclusion: null, remark: val || null }])
  }

  /** context 全部转字符串（/ai/generate-text 要求 dict[str,str]） */
  function _strContext(raw?: Record<string, unknown>): Record<string, string> {
    const out: Record<string, string> = {}
    if (!raw) return out
    for (const [k, v] of Object.entries(raw)) {
      if (v == null) continue
      out[k] = typeof v === 'string' ? v : (typeof v === 'object' ? JSON.stringify(v) : String(v))
    }
    return out
  }

  async function _generate(
    section: string,
    prompt: string,
    existingContent: string,
    context: Record<string, unknown> | undefined,
    apply: (content: string) => void,
    loadingRef: Ref<boolean>,
  ): Promise<void> {
    if (isReadonly.value) return
    loadingRef.value = true
    try {
      const res = await http.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section,
        prompt,
        existingContent,
        context: _strContext(context),
      })
      const content = (res.data?.data ?? res.data)?.content
      if (content) {
        apply(content)
      } else {
        ElMessage.info('AI 未返回内容，请手动撰写')
      }
    } catch {
      ElMessage.info('AI 辅助暂不可用，请手动撰写')
    } finally {
      loadingRef.value = false
    }
  }

  function generateNote(prompt: string, context?: Record<string, unknown>): Promise<void> {
    return _generate(`L1-${sheetKey}-note`, prompt, note.value, context, onNoteInput, aiNoteLoading)
  }

  function generateConclusion(prompt: string, context?: Record<string, unknown>): Promise<void> {
    return _generate(`L1-${sheetKey}-conclusion`, prompt, conclusion.value, context, onConclusionInput, aiConclusionLoading)
  }

  return {
    note,
    conclusion,
    aiNoteLoading,
    aiConclusionLoading,
    load,
    onNoteInput,
    onConclusionInput,
    generateNote,
    generateConclusion,
  }
}

export default useL1AiNote
