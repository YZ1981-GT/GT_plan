/**
 * plainTextCompat — 纯文本兼容渲染工具
 *
 * 检测内容无 HTML 标签时自动将 \n 转为 <br>。
 * 存量纯文本数据无需迁移，自动兼容渲染。
 *
 * Requirements: 1.5
 */

const HTML_TAG_RE = /<[a-z][\s\S]*?>/i

/**
 * 纯文本兼容渲染：如果内容不含任何 HTML 标签，将 \n 转为 <br>
 * 已含 HTML 标签的内容原样返回不做转换。
 */
export function plainTextToHtml(text: string): string {
  if (!text) return ''
  if (HTML_TAG_RE.test(text)) return text
  return text.replace(/\n/g, '<br>')
}
