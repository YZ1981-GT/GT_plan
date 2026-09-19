/**
 * useSanitize — DOMPurify 封装 composable
 *
 * 对 HTML 内容进行消毒，允许安全的格式标签（h3/h4/ul/ol/li/table/tr/td/th/strong/em/br/p），
 * 剥离所有危险标签（script/iframe/object/embed）及 on* 事件属性。
 */
import DOMPurify from 'dompurify'

// ─── 允许的安全标签 ─────────────────────────────────────────────────────────────

const ALLOWED_TAGS = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'table', 'thead', 'tbody', 'tr', 'td', 'th',
  'strong', 'em', 'br', 'p', 'span',
  'pre', 'code', 'blockquote',
  'a', 'del', 'hr', 'dl', 'dt', 'dd',
]

// ─── 允许的属性（仅结构性属性，禁止所有 on* 事件） ────────────────────────────────

const ALLOWED_ATTR = [
  'colspan', 'rowspan', 'class', 'style',
  'href', 'target', 'rel',
]

// ─── 核心函数 ────────────────────────────────────────────────────────────────────

/**
 * 对 HTML 字符串进行消毒处理
 * - 保留安全的格式标签
 * - 剥离 script/iframe/object/embed 标签
 * - 剥离所有 on* 事件属性
 */
export function sanitizeHtml(raw: string): string {
  if (!raw) return ''
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
  })
}

/**
 * composable 形式导出（与项目其他 composable 风格一致）
 */
export function useSanitize() {
  return {
    sanitizeHtml,
  }
}
