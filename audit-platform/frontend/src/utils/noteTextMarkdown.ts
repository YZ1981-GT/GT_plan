/**
 * 附注正文（text_content）加载进编辑器时统一为 HTML。
 *
 * spec disclosure-note-doc-upload-and-batch-fill 第 22 组。
 * 🔴 与后端 `backend/app/services/note_html_sanitizer.py`（note_text_to_html：Word 导出 / 批量写入）
 *    是同一规则的两份实现，且用同一个引擎 markdown-it、同一配置；两端测试逐条跑共享夹具
 *    `backend/data/note_text_markdown_cases.json`，改规则必须两端同改并补用例。
 *    首版编辑器用 marked、后端用 markdown-it：书写的「1. 」接在文字后，编辑器拆成两段、Word 里同段换行。
 *
 * text_content 可能是 HTML（富文本框保存）或纯文字（生成链写入，含换行、markdown 表格 / 标题 / 粗体）。
 * 纯文字按 markdown 渲染，但书写的编号、项目符号与缩进是正文、必须原样：不认列表与缩进代码块
 * （按有序列表解释会把两组「1~4」排成 1~8）。纯文字里的尖括号一律按文字。
 */
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

/**
 * 判定「正文是 HTML」：出现附注编辑器 / 消毒器认识的标签之一（与后端 `_HTML_TAG` 同一条）。
 * `<` 后不允许空白，`a < b 且 c > d`、`<公司名称>` 都不命中；标签名后的词边界按 Unicode
 * （后端 Python 的 `\b` 把汉字算词字符，`<b中文>` 不是标签）。
 */
export const NOTE_HTML_TAG =
  /<\/?(?:p|br|div|span|strong|em|b|i|u|ul|ol|li|h[1-6]|table|thead|tbody|tfoot|tr|td|th|blockquote|hr)(?![\p{L}\p{N}_])[^>]*>/iu

export function isHtmlNoteText(text: string | null | undefined): boolean {
  return !!text && NOTE_HTML_TAG.test(text)
}

const md = new MarkdownIt('commonmark', { breaks: true, html: false })
  .enable(['table', 'strikethrough'])
  .disable(['list', 'code'])

/** 纯文字按 markdown 渲染的引擎原样输出（未消毒；去掉 markdown-it 补在标签边上的换行）。两端对拍比的就是它。 */
export function renderNoteMarkdown(text: string): string {
  return md.render(text).replace(/>\n/g, '>').replace(/\n</g, '<')
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/**
 * 附注正文 → 编辑器 HTML（幂等；保存后即以 HTML 落库）。
 * 已是 HTML 只消毒不转换：富文本框以 innerHTML 显示（首版靠隐藏的 TipTap 编辑器顺带清洗，代价是表格被拍平）。
 */
export function renderNoteTextToHtml(raw: string | null | undefined): string {
  if (!raw || !raw.trim()) return ''
  if (isHtmlNoteText(raw)) return DOMPurify.sanitize(raw)
  try {
    return DOMPurify.sanitize(renderNoteMarkdown(raw))
  } catch {
    // 渲染失败降级为按空行分段、单换行换行（保底不丢内容）
    const paragraphs = raw.trim().split(/\n\s*\n/).filter(Boolean)
    return DOMPurify.sanitize(paragraphs.map(p => `<p>${escapeHtml(p).replace(/\n/g, '<br>')}</p>`).join(''))
  }
}
