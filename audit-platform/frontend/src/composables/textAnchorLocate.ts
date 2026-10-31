/**
 * textAnchorLocate — 按目录登记的锚点文字在渲染器根元素内找区块（spec wp-deeplink-locate-coverage-closure 需求 2.1）。
 *
 * 目录里的「审计结论」标签格（如 E1-14!A50）在网页视图里对应各组件的结论区标题（卡片标题 / `.section-title` /
 * 表单项标签，文字都是「审计结论」）。按文字节点找：文字去空白、去序号（「四、」「2.」等）与尾部冒号后等于锚点文字的，取其所在元素；
 * 排除表格单元格（th / td，表格列名不是结论区）与隐藏的（hidden / aria-hidden / display:none）；恰好一处时高亮它所在的
 * 卡片或表单项（不在根元素内则高亮标题本身），没有或多于一处返回 false（由调用方提示「没有对应位置」，不猜）。
 *
 * 二级（spec wp-deeplink-locate-residual-closure 需求 3）：整段相等一处都没有时，认「含锚点文字、归一后不超过锚点文字
 * + COMPOUND_EXTRA 字」的标题（「分析结论（四、审计结论）」「综合审计结论」），不在按钮 / 链接 / 表格单元格 / 浮层里，
 * 恰好一处才认；整段相等有两处及以上时照旧不认。
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

/**
 * 二级标题比锚点文字最多多出的字数：组件模板普查（2026-10-30，`heading_forms.txt`）里带别的字的结论标题最长 12 字
 * （「分析结论（四、审计结论）」），提示句最短 13 字（「完成核对清单并填写审计结论」），取 8（锚点「审计结论」4 字 + 8 = 12）。
 */
export const COMPOUND_EXTRA = 8
/** 二级不认的位置：表格单元格、按钮 / 链接（「🤖 AI 生成审计结论」）、浮层 */
const COMPOUND_EXCLUDE = 'th, td, button, a, [role="button"], [role="tooltip"], .el-popper'

/** 找唯一可见的锚点区块；没有或不唯一返回 null（先整段相等，一处都没有再按二级认） */
export function findTextAnchorElement(root: ParentNode, text: string): Element | null {
  const want = normalizeAnchorText(text)
  const doc = (root as Node).ownerDocument ?? (root as Document)
  if (!want || !doc?.createTreeWalker) return null
  const walker = doc.createTreeWalker(root as Node, NodeFilter.SHOW_TEXT)
  const hits = new Set<Element>()
  const compound = new Set<Element>()
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement
    if (!el) continue
    const got = normalizeAnchorText(n.textContent)
    if (got === want) {
      if (el.closest('th, td') || isHidden(el, root)) continue
      hits.add(el)
    } else if (got.includes(want) && got.length <= want.length + COMPOUND_EXTRA) {
      if (el.closest(COMPOUND_EXCLUDE) || isHidden(el, root)) continue
      compound.add(el)
    }
  }
  const only = hits.size === 1 ? hits : hits.size === 0 && compound.size === 1 ? compound : null
  if (!only) return null
  const [el] = only
  const block = el.closest('.el-card, .el-form-item')
  return block && (root as Node).contains(block) ? block : el
}

export function locateTextAnchor(root: ParentNode, text: string, key: string): boolean {
  const el = findTextAnchorElement(root, text)
  return el ? highlightElement(el, key) : false
}
