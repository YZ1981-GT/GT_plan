/**
 * 单元格编辑器协议与登记（spec excel-style-table-editing design §6）。
 *
 * 适配组件 / GtGridCell 在自己的根节点上标 `data-gt-cell-editor="<id>"`（显示态与编辑态都标），
 * 内核按格内元素找到句柄，不需要逐格预先登记。
 */
import type { CellEditorKind, ParseResult } from './cellValue'

export type OpenMode = 'entering' | 'editing' | 'picking'

export interface OpenRequest {
  mode: OpenMode
  /** 直接输入进入时的首批字符（含输入法组好的字）。 */
  initialText?: string
  /** 编辑器挂好、聚焦前再取一次承接框里新敲的字（快速连敲不丢字）。 */
  takePendingText?: () => string
}

export interface CellEditorHandle {
  readonly id: string
  readonly kind: CellEditorKind
  editable(): boolean
  /** 文本框（Alt+Enter 换行、Enter 不换行）。 */
  multiline(): boolean
  getText(): string
  getValue(): unknown
  isOpen(): boolean
  open(req: OpenRequest): Promise<boolean>
  /** 同步发出提交事件并返回提交后的值；之后由内核把焦点收回承接框，编辑器随即卸载。 */
  commit(): unknown
  cancel(): void
  /** 粘贴：按本格类型解析文本并写入。 */
  applyText(text: string): ParseResult | Promise<ParseResult>
  /** 撤销 / 重做：写入一个已解析的值。 */
  setValue(value: unknown): boolean | Promise<boolean>
  /** 勾选类：空格切换。 */
  toggle?(): void
}

export const CELL_EDITOR_ATTR = 'data-gt-cell-editor'

const handles = new Map<string, CellEditorHandle>()
let seq = 0

export function nextEditorId(): string {
  seq += 1
  return `e${seq}`
}

export function registerEditorHandle(handle: CellEditorHandle): void {
  handles.set(handle.id, handle)
}

export function unregisterEditorHandle(id: string): void {
  handles.delete(id)
}

export function handleOfElement(el: Element | null): CellEditorHandle | null {
  const id = el?.getAttribute(CELL_EDITOR_ATTR)
  return id ? handles.get(id) ?? null : null
}

/** 格内（不含嵌套子表）的全部编辑器，按 DOM 顺序；GtGridCell 托管的内层编辑器不重复列出。 */
export function editorsInCell(td: Element | null): CellEditorHandle[] {
  if (!td) return []
  const out: CellEditorHandle[] = []
  const seen = new Set<string>()
  for (const el of Array.from(td.querySelectorAll(`[${CELL_EDITOR_ATTR}]`))) {
    if (el.closest('td, th') !== td) continue
    if (el.parentElement?.closest(`[${CELL_EDITOR_ATTR}]`) && el.parentElement.closest('td, th') === td) continue
    const h = handleOfElement(el)
    if (h && !seen.has(h.id)) {
      seen.add(h.id)
      out.push(h)
    }
  }
  return out
}

/** 主编辑器：第一个可编辑的输入类；没有则第一个可编辑的勾选类。 */
export function primaryEditor(td: Element | null): CellEditorHandle | null {
  const all = editorsInCell(td)
  return (
    all.find((h) => h.kind !== 'toggle' && h.editable()) ??
    all.find((h) => h.editable()) ??
    null
  )
}

/** 格内是否有编辑器（不论可否编辑）——只读的编辑器格复制时取它的显示文本。 */
export function anyEditor(td: Element | null): CellEditorHandle | null {
  return editorsInCell(td)[0] ?? null
}

/** 仅供测试 */
export function _editorHandleCount(): number {
  return handles.size
}
