/**
 * textAnchorLocate — 按目录登记的锚点文字在渲染器根元素内找区块（spec wp-deeplink-locate-coverage-closure 需求 2.1）。
 *
 * 目录里的「审计结论」标签格（如 E1-14!A50）在网页视图里对应各组件的结论区标题（卡片标题 / `.section-title` /
 * 表单项标签，文字都是「审计结论」）。按文字节点找：文字去空白、去序号（「四、」「2.」等）与尾部冒号后等于锚点文字的，取其所在元素；
 * 排除表格单元格（th / td，表格列名不是结论区）与隐藏的（hidden / aria-hidden / display:none）；恰好一处时高亮它所在的
 * 卡片或表单项（不在根元素内则高亮标题本身），没有或多于一处返回 false（由调用方提示「没有对应位置」，不猜）。
 */
import { highlightElement } from './useCellLocate'

/**
 * 标题前的序号：「四、」「2、」「2.」「（三）」「(3)」「IV.」（2026-10-30 组件模板普查：标签文字含「审计结论」587 处，
 * 中文序号或无序号能认出 511 处，阿拉伯 / 括号 / 罗马序号另 52 处；放宽后同一文件里能认出的标题只会 0 → 1，不会 1 → 2）
 */
const NUMBERING = /^(?:[一二三四五六七八九十]+、|\d+[、.．]|[（(][一二三四五六七八九十\d]+[)）]|[IVX]+[.．])/

export function normalizeAnchorText(text: string | null | undefined): string {
  return String(text ?? '').replace(/\s+/g, '').replace(NUMBERING, '').replace(/[:：]$/, '')
}

function isHidden(el: Element, root: ParentNode): boolean {
  for (let node: Element | null = el; node && node !== root; node = node.parentElement) {
    const h = node as HTMLElement
    if (h.hidden || h.getAttribute('aria-hidden') === 'true' || h.style?.display === 'none') return true
    if (typeof getComputedStyle === 'function' && getComputedStyle(h).display === 'none') return true
  }
  return false
}

/** 找唯一可见的锚点区块；没有或不唯一返回 null */
export function findTextAnchorElement(root: ParentNode, text: string): Element | null {
  const want = normalizeAnchorText(text)
  const doc = (root as Node).ownerDocument ?? (root as Document)
  if (!want || !doc?.createTreeWalker) return null
  const walker = doc.createTreeWalker(root as Node, NodeFilter.SHOW_TEXT)
  const hits = new Set<Element>()
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement
    if (!el || normalizeAnchorText(n.textContent) !== want) continue
    if (el.closest('th, td') || isHidden(el, root)) continue
    hits.add(el)
  }
  if (hits.size !== 1) return null
  const [el] = hits
  const block = el.closest('.el-card, .el-form-item')
  return block && (root as Node).contains(block) ? block : el
}

export function locateTextAnchor(root: ParentNode, text: string, key: string): boolean {
  const el = findTextAnchorElement(root, text)
  return el ? highlightElement(el, key) : false
}
