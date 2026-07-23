/**
 * useN1AiText — N1 递延所得税资产 AI 文本生成（真回填）
 *
 * 统一封装 POST /api/workpapers/{wpId}/ai/generate-text 调用。
 * 铁律：
 * - 必须 await 并取回 response.data.data.content（信封双层兼容），返回给调用方回填 textarea；
 * - context 值必须全部为字符串（后端 AiGenerateTextRequest.context 是 dict[str,str]，传数字会 422）；
 * - 服务不可用时静默降级（返回空串 + 轻提示），不阻断底稿编制。
 */
import http from '@/utils/http'
import { ElMessage } from 'element-plus'

export interface GenerateN1TextOptions {
  wpId: string
  /** 区段标识（如 n1-adjudication-conclusion） */
  section: string
  /** 生成提示 */
  prompt: string
  /** 上下文（值必须为字符串） */
  context?: Record<string, string>
  /** 已有内容（供 AI 在其基础上补充/润色） */
  existingContent?: string
}

/**
 * 调用 AI 生成文本并返回内容字符串。
 * @returns 生成的文本；失败或无返回时为空串。
 */
export async function generateN1Text(opts: GenerateN1TextOptions): Promise<string> {
  try {
    const res = await http.post(`/api/workpapers/${opts.wpId}/ai/generate-text`, {
      section: opts.section,
      prompt: opts.prompt,
      context: opts.context ?? {},
      existingContent: opts.existingContent ?? '',
    })
    const text: string = (res as any).data?.data?.content || (res as any).data?.content || ''
    if (!text) {
      ElMessage.info('AI 暂无返回内容（服务可能不可用）')
    }
    return text
  } catch {
    ElMessage.warning('AI 服务不可用，请稍后重试')
    return ''
  }
}

export default generateN1Text
