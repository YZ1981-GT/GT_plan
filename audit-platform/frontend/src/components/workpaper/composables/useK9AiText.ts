/**
 * useK9AiText — K9 管理费用底稿统一 AI 文本生成 helper
 *
 * 2026-07-23 修复：原 K9 各 sheet 的 AI 按钮全是 ElMessage.info 桩 /
 * emit 'K9-x-ai-trigger' 死链（主入口无监听）。此 helper 统一调用平台通用
 * 端点 POST /api/workpapers/{wpId}/ai/generate-text，返回生成文本。
 *
 * 铁律：context 值全部转 str（AiGenerateTextRequest.context 为 dict[str,str]，
 * 传数字会 422）。
 */
import http from '@/utils/http'
import { ElMessage } from 'element-plus'

export interface K9AiTextOptions {
  prompt: string
  section: string
  context?: Record<string, unknown>
  existingContent?: string
}

/**
 * 调用通用 AI 文本生成端点，返回生成内容（失败/空返回空串，并弹提示）。
 */
export async function generateK9AiText(wpId: string, opts: K9AiTextOptions): Promise<string> {
  if (!wpId) {
    ElMessage.warning('缺少底稿 ID，无法生成')
    return ''
  }
  // context 值全部转字符串（避免 422）
  const ctx: Record<string, string> = {}
  for (const [k, v] of Object.entries(opts.context ?? {})) {
    ctx[k] = v == null ? '' : String(v)
  }
  try {
    const res: any = await http.post(`/api/workpapers/${wpId}/ai/generate-text`, {
      prompt: opts.prompt,
      section: opts.section,
      context: ctx,
      existingContent: opts.existingContent ?? '',
    })
    const content = res?.data?.data?.content || res?.data?.content || ''
    if (!content) {
      ElMessage.warning('AI 未返回内容')
      return ''
    }
    ElMessage.success('AI 已生成')
    return content
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
    return ''
  }
}

export default generateK9AiText
