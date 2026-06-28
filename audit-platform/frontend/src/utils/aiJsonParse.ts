/**
 * 尝试从 AI 返回内容中解析 JSON 数组
 * 三层容错：直接parse → 提取```json代码块 → 提取[...]片段
 */
export function tryParseJsonArray(text: string): any[] | null {
  if (!text) return null
  // 直接解析
  try { const arr = JSON.parse(text); if (Array.isArray(arr)) return arr } catch {}
  // 提取 ```json ... ``` 代码块
  const match = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (match) { try { const arr = JSON.parse(match[1]); if (Array.isArray(arr)) return arr } catch {} }
  // 提取 [ ... ] 部分
  const bracketMatch = text.match(/\[[\s\S]*\]/)
  if (bracketMatch) { try { const arr = JSON.parse(bracketMatch[0]); if (Array.isArray(arr)) return arr } catch {} }
  return null
}
