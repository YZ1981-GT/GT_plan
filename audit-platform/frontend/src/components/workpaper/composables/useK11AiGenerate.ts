/**
 * useK11AiGenerate — K11 资产减值损失 AI 辅助文本生成（统一端点）
 *
 * 调 POST /api/workpapers/{wpId}/ai/generate-text
 * 🔴 后端 AiGenerateTextRequest.context 是 dict[str, str]，
 *    值必须全部转字符串，否则 422（传 JSON.stringify 字符串同样 422）。
 *
 * 供 K11-1 审定表 / K11-2 明细表 / 附注上市 / 附注国企 复用。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export interface UseK11AiGenerateOptions {
  wpId: () => string
}

export interface K11AiGenerateArgs {
  section: string
  prompt: string
  /** 上下文（值会被强制转字符串以避免 422） */
  context?: Record<string, unknown>
  existingContent?: string
}

export function useK11AiGenerate(options: UseK11AiGenerateOptions) {
  const generating = ref(false)

  /** 把任意上下文对象归一为 Record<string,string>（后端契约要求） */
  function _stringifyContext(ctx?: Record<string, unknown>): Record<string, string> {
    const out: Record<string, string> = {}
    if (!ctx) return out
    for (const [k, v] of Object.entries(ctx)) {
      if (v == null) continue
      out[k] = typeof v === 'string' ? v : String(v)
    }
    return out
  }

  /**
   * 生成文本。成功返回内容字符串；失败返回 null（并已给出提示）。
   */
  async function generate(args: K11AiGenerateArgs): Promise<string | null> {
    const wpId = options.wpId()
    if (!wpId) return null
    generating.value = true
    try {
      const res = await http.post(`/api/workpapers/${wpId}/ai/generate-text`, {
        prompt: args.prompt,
        context: _stringifyContext(args.context),
        section: args.section,
        existingContent: args.existingContent ?? '',
      })
      const text = res.data?.data?.content ?? res.data?.content ?? ''
      if (text) {
        ElMessage.success('AI 文本已生成')
        return text as string
      }
      ElMessage.warning('AI 未返回内容，请稍后重试')
      return null
    } catch {
      ElMessage.error('AI 生成失败，请稍后重试')
      return null
    } finally {
      generating.value = false
    }
  }

  return { generating, generate }
}

export default useK11AiGenerate
