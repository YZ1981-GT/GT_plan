/**
 * useK13AiText — K13 营业外支出底稿统一 AI 文本生成 helper
 *
 * 2026-07-23：镜像 useK12AiText。原 K13-4 的 handleAiAssist 用
 * context: JSON.stringify(...) → 后端 AiGenerateTextRequest.context 为
 * dict[str,str] → 传字符串 422（AI 从未真正工作）。此 helper 统一调用
 * 平台通用端点 POST /api/workpapers/{wpId}/ai/generate-text。
 *
 * 铁律：context 值全部转 str（传数字/数组/对象会 422）。
 */
import http from '@/utils/http'
import { ElMessage } from 'element-plus'

export interface K13AiTextOptions {
  prompt: string
  section: string
  context?: Record<string, unknown>
  existingContent?: string
}

/** 调用通用 AI 文本生成端点，返回生成内容（失败/空返回空串并弹提示）。 */
export async function generateK13AiText(wpId: string, opts: K13AiTextOptions): Promise<string> {
  if (!wpId) {
    ElMessage.warning('缺少底稿 ID，无法生成')
    return ''
  }
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

export default generateK13AiText
