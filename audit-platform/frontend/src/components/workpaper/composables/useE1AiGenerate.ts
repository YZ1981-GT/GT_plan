import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

interface GenerateOptions {
  section: string
  prompt: string
  context?: Record<string, unknown> | string
  existingContent?: string
  confirmTitle?: string
}

function normalizeContext(context?: Record<string, unknown> | string): Record<string, string> {
  if (typeof context === 'string') return { context }
  if (!context) return {}
  return Object.fromEntries(Object.entries(context).map(([key, value]) => {
    if (value === null) return [key, '']
    if (typeof value === 'string') return [key, value]
    return [key, JSON.stringify(value) ?? '']
  }))
}

function isConfirmationCancel(error: unknown): boolean {
  if (error === 'cancel' || error === 'close') return true
  const action = String((error as any)?.action ?? (error as any)?.message ?? '').toLowerCase()
  return action === 'cancel' || action === 'close'
}

export function useE1AiGenerate(wpId: Ref<string>) {
  const loadingSections = ref<Record<string, boolean>>({})

  async function generateText(options: GenerateOptions): Promise<string> {
    if (!wpId.value || loadingSections.value[options.section]) return ''
    loadingSections.value = { ...loadingSections.value, [options.section]: true }
    try {
      const response = await http.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        prompt: options.prompt,
        context: normalizeContext(options.context),
        existingContent: options.existingContent ?? '',
        section: options.section,
      }, { _silent: true } as any)
      const envelope = (response as any)?.data ?? response
      const payload = envelope?.data ?? envelope
      const rawText = typeof payload === 'string' ? payload : payload?.content ?? payload?.text ?? ''
      const text = String(rawText)
      if (!text) {
        ElMessage.warning('AI 未生成内容')
        return ''
      }
      if (options.confirmTitle) {
        await ElMessageBox.confirm(text.length > 800 ? `${text.slice(0, 800)}…` : text, options.confirmTitle, {
          confirmButtonText: '填入', cancelButtonText: '取消', type: 'info',
          customStyle: { maxWidth: '680px' },
        })
      }
      return text
    } catch (error: unknown) {
      if (!isConfirmationCancel(error)) ElMessage.error('AI 生成失败，请稍后重试')
      return ''
    } finally {
      loadingSections.value = { ...loadingSections.value, [options.section]: false }
    }
  }

  const isGenerating = (section: string) => !!loadingSections.value[section]
  return { generateText, isGenerating, loadingSections }
}
