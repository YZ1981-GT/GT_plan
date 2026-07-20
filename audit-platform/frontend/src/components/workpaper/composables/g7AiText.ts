/**
 * G7 AI 响应正文提取（兼容 ResponseWrapper / 旧 conclusion 字段）
 * 优先 content，与后端 G7SubAiGenerateResponse / equity-method AI 对齐。
 */
export function extractG7AiText(payload: unknown): string {
  if (payload == null) return ''
  if (typeof payload === 'string') return payload.trim()
  const root = payload as Record<string, any>
  const data = root.data && typeof root.data === 'object' ? root.data : root
  const text = data.content
    ?? data.conclusion
    ?? data.text
    ?? root.content
    ?? root.conclusion
    ?? root.text
    ?? ''
  return typeof text === 'string' ? text.trim() : ''
}

/** @deprecated 使用 extractG7AiText；保留别名兼容既有 import */
export const extractG7SubAiText = extractG7AiText
