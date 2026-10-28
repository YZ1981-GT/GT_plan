/**
 * contentEditableCells — 把 v-html 渲染的表格里「contenteditable 的格」接入表格内核（spec excel-style-table-editing 5.5）
 *
 * 后端 excel-html 预览（表样编辑器）给每个可编辑格写 `contenteditable="true"`：一点就进编辑、方向键在格里移光标。
 * 这里把这些格改成与其他表格一致的单元格编辑器：
 * - 格里的文字包进一个 span，span 是编辑器（`data-gt-cell-editor`），平时不可编辑（只显示文字）；
 * - 双击 / F2 / 直接输入（含输入法）由内核打开：span 设为可编辑（纯文本）并聚焦；Enter / Tab / Esc / 失焦
 *   由内核按统一键位提交或取消；粘贴 / Delete 清空 / 撤销重做走 `applyText` / `setValue`；
 * - 坐标标签等不算值的子元素（`ignoreSelector`）留在 span 外，不参与取值与编辑。
 * 返回的函数拆掉接入并还原后端给的结构（切到「经典」编辑方式时用：格又回到一点就编辑）。
 */
import { CELL_EDITOR_ATTR, nextEditorId, registerEditorHandle, unregisterEditorHandle, type CellEditorHandle, type OpenRequest } from './editorHost'
import type { ParseResult } from './cellValue'

export interface ContentEditableCellsOptions {
  /** 可编辑格（在 table 内找，不含嵌套子表）；默认 `td[contenteditable="true"]` */
  cellSelector?: string
  /** 格里不算值的子元素（如坐标标签）：不包进编辑器 */
  ignoreSelector?: string
  /** 值变了（提交 / 粘贴 / 清空 / 撤销）：格、新文字、原文字 */
  onChange: (td: HTMLTableCellElement, text: string, before: string) => void
}

export const CE_VALUE_CLASS = 'gt-ce-value'

function caretToEnd(el: HTMLElement): void {
  const sel = typeof window !== 'undefined' ? window.getSelection() : null
  if (!sel || typeof document.createRange !== 'function') return
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(false)
  sel.removeAllRanges()
  sel.addRange(range)
}

interface Bound { td: HTMLTableCellElement; span: HTMLElement; id: string; attr: string | null }

export function bindContentEditableCells(table: HTMLTableElement, opts: ContentEditableCellsOptions): () => void {
  const selector = opts.cellSelector ?? 'td[contenteditable="true"]'
  const bound: Bound[] = []
  for (const td of Array.from(table.querySelectorAll<HTMLTableCellElement>(selector))) {
    if (td.closest('table') !== table || td.querySelector(`:scope > .${CE_VALUE_CLASS}`)) continue
    const attr = td.getAttribute('contenteditable')
    td.removeAttribute('contenteditable')
    const span = document.createElement('span')
    span.className = CE_VALUE_CLASS
    for (const node of Array.from(td.childNodes)) {
      if (opts.ignoreSelector && node instanceof Element && node.matches(opts.ignoreSelector)) continue
      span.appendChild(node)
    }
    td.insertBefore(span, td.firstChild)
    const id = nextEditorId()
    span.setAttribute(CELL_EDITOR_ATTR, id)

    let open = false
    let before = ''
    const text = (): string => span.textContent ?? ''
    const close = (): void => {
      open = false
      span.removeAttribute('contenteditable')
    }
    const write = (t: string): boolean => {
      const old = text()
      if (old === t) return true
      span.textContent = t
      opts.onChange(td, t, old)
      return true
    }
    const handle: CellEditorHandle = {
      id,
      kind: 'text',
      editable: () => true,
      multiline: () => false,
      getText: text,
      getValue: text,
      isOpen: () => open,
      async open(req: OpenRequest): Promise<boolean> {
        before = text()
        open = true
        // 纯文本编辑：粘贴进来的网页 / Word 内容不带格式
        span.setAttribute('contenteditable', 'plaintext-only')
        const more = req.takePendingText?.() ?? ''
        if (req.initialText !== undefined) span.textContent = req.initialText + more
        else if (more) span.textContent = text() + more
        span.focus()
        caretToEnd(span)
        return true
      },
      commit(): unknown {
        if (!open) return text()
        close()
        const t = text()
        if (t !== before) opts.onChange(td, t, before)
        return t
      },
      cancel(): void {
        if (!open) return
        span.textContent = before
        close()
      },
      applyText(t: string): ParseResult {
        write(t)
        return { ok: true, value: t }
      },
      setValue: (v: unknown) => write(v == null ? '' : String(v)),
    }
    registerEditorHandle(handle)
    bound.push({ td, span, id, attr })
  }

  return () => {
    for (const b of bound.splice(0)) {
      unregisterEditorHandle(b.id)
      if (b.span.parentNode === b.td) {
        while (b.span.firstChild) b.td.insertBefore(b.span.firstChild, b.span)
        b.span.remove()
      }
      if (b.attr != null) b.td.setAttribute('contenteditable', b.attr)
    }
  }
}
