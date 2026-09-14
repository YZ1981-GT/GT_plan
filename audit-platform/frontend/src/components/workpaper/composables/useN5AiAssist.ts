/**
 * useN5AiAssist — N5 AI 辅助文本生成（真回填版）
 *
 * 修复全 sheet 通病：原 handleAiAssist 只是 `http.post().catch(()=>{})`——
 * 发请求后不接收/不回填/不 loading/不报错。
 *
 * 铁律：调 /ai/generate-text 时 context 所有值必须转字符串（dict[str,str]，传数字会 422）。
 *
 * 用法：
 *   const ai = useN5AiAssist({ wpId })
 *   await ai.generate('n5-adjudication', '请给出审计分析建议', () => ({ 期末: fmt(x) }), auditNotes)
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export interface UseN5AiAssistOptions {
  wpId: Ref<string>
}

/** 把任意 context 值转成字符串，规避 /ai/generate-text 的 dict[str,str] 422 */
function stringifyContext(ctx: Record<string, any> | undefined): Record<string, string> {
  const out: Record<string, string> = {}
  if (!ctx) return out
  for (const [k, v] of Object.entries(ctx)) {
    if (v == null) continue
    out[k] = typeof v === 'string' ? v : String(v)
  }
  return out
}

export function useN5AiAssist(options: UseN5AiAssistOptions) {
  const { wpId } = options
  const loading = ref(false)

  /**
   * 生成文本。成功后：若传入 target ref 则回填（追加/替换），并返回生成文本。
   * @param section  AI section 标识
   * @param prompt   提示词
   * @param contextFn 返回 context 对象（值会被转字符串）
   * @param target   可选，生成结果回填的目标 ref（textarea 绑定）
   * @param mode     'replace'(默认) | 'append'
   */
  async function generate(
    section: string,
    prompt: string,
    contextFn?: () => Record<string, any>,
    target?: Ref<string>,
    mode: 'replace' | 'append' = 'replace',
  ): Promise<string> {
    if (loading.value) return ''
    loading.value = true
    try {
      const res = await http.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section,
        prompt,
        existingContent: target?.value ?? '',
        context: stringifyContext(contextFn?.()),
      })
      const payload = res.data?.data ?? res.data
      const text: string = payload?.content ?? payload?.text ?? payload?.result ?? ''
      if (!text) {
        ElMessage.warning('AI 未返回内容')
        return ''
      }
      if (target) {
        target.value = mode === 'append' && target.value
          ? `${target.value}\n${text}`
          : text
      }
      ElMessage.success('AI 辅助内容已生成')
      return text
    } catch (e: any) {
      const msg = e?.response?.data?.message || e?.message || 'AI 生成失败'
      ElMessage.error(`AI 生成失败：${msg}`)
      return ''
    } finally {
      loading.value = false
    }
  }

  return { loading, generate }
}

export default useN5AiAssist
