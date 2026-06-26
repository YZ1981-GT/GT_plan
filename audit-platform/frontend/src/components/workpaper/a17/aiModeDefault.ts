/**
 * AI 模式默认值逻辑
 *
 * 章节内容为空（去除 HTML 标签后纯空白）→ "generate"
 * 章节内容有实质文字 → "polish"
 *
 * Requirements: 4.4
 */

export type AiMode = 'generate' | 'polish'

/**
 * 根据章节内容决定 AI 生成模式默认值。
 *
 * @param content - 章节 HTML/纯文本内容
 * @returns "generate" 当内容为空或仅空白；"polish" 当内容有实质字符
 */
export function getDefaultAiMode(content: string): AiMode {
  // 去除 HTML 标签后判断是否为纯空白
  const stripped = content.replace(/<[^>]*>/g, '').trim()
  return stripped.length === 0 ? 'generate' : 'polish'
}
