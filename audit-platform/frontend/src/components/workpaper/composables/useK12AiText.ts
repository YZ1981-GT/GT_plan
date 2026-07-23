/**
 * useK12AiText — K12 营业外收入底稿统一 AI 文本生成 helper
 *
 * 2026-07-23 修复：原 K12 各 sheet 的 AI 按钮全是 ElMessage.info 桩 /
 * 空钩子；两个附注 tab 虽调了 /ai/generate-text 但 context 传 JSON.stringify
 * 字符串 → 后端 context: dict[str,str] → 422（附注 AI 也从未真正工作）。
 * 此 helper 统一调用平台通用端点 POST /api/workpapers/{wpId}/ai/generate-text。
 *
 * 铁律：context 值全部转 str（AiGenerateTextRequest.context 为 dict[str,str]，
 * 传数字/数组/对象会 422）。
 */
import http from '@/utils/http'
import { ElMessage } from 'element-plus'

export interface K12AiTextOptions {
  prompt: string
  section: string
  context?: Record<string, unknown>
  existingContent?: string
}

/**
 * 调用通用 AI 文本生成端点，返回生成内容（失败/空返回空串，并弹提示）。
 */
export async function generateK12AiText(wpId: string, opts: K12AiTextOptions): Promise<string> {
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

export default generateK12AiText
