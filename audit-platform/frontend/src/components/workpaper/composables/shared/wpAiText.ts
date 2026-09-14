/**
 * 底稿通用 AI 文本生成（真回填）—— 平台共用
 *
 * 唯一正解端点 = `POST /api/workpapers/{wpId}/ai/generate-text`
 * （后端 `wp_guidance_chat.AiGenerateTextRequest`）：
 *
 * | 字段 | 说明 |
 * |---|---|
 * | `section` | 区段标识（如 `n2-disclosure-listed-conclusion`），端点不做白名单拒绝 |
 * | `prompt` | 生成提示；不传时后端按 section 兜底 |
 * | `context` | 🔴 `dict[str, str]` —— **值必须全部是字符串**，传数字会 422 |
 * | `existingContent` | 🔴 **驼峰**，写成 `existing_content` 会被忽略 |
 *
 * 响应 = `{ content }`（经 `ResponseWrapperMiddleware` 包成信封 → 读
 * `data.data.content`，兼容双层）。
 *
 * 🔴 写错端点/字段的代价是**静默空转**：D1 曾把请求体写成 `{section, context}`
 * 打到 `review-dialog/ai-generate` 并读 `.text` → 必然 422，被 `catch` 吞成
 * 「AI生成失败」，7 个按钮长期无效。故各循环一律走本 helper，不要各写一份 http.post。
 *
 * 起源于 `useN1AiText.ts`（N1 递延所得税），由 `n-cycle-tax-disclosure-alignment`
 * 提升为平台共用（N2 / N4 / N5 复用）。
 */
import http from '@/utils/http'
import { ElMessage } from 'element-plus'

export interface GenerateWpTextOptions {
  wpId: string
  /** 区段标识（如 `n5-disclosure-soe-reconcile`） */
  section: string
  /** 生成提示 */
  prompt: string
  /** 上下文（🔴 值必须为字符串） */
  context?: Record<string, string>
  /** 已有内容（供 AI 在其基础上补充/润色） */
  existingContent?: string
}

/**
 * 调用 AI 生成文本并返回内容字符串。
 *
 * 服务不可用时静默降级（返回空串 + 轻提示），不阻断底稿编制。
 *
 * @returns 生成的文本；失败或无返回时为空串。
 */
export async function generateWpText(opts: GenerateWpTextOptions): Promise<string> {
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

export default generateWpText
