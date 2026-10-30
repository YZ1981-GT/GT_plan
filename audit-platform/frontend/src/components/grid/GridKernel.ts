/**
 * 表格交互内核（spec excel-style-table-editing design §5）：选区、键盘、焦点承接框、
 * 复制 / 剪切 / 粘贴、撤销重做、编辑状态机。每张 el-table（全局 mixin）/ GtGridTable 一个实例。
 *
 * 只读写自己声明的 `data-gt-*` 属性与自己插入的承接框，不改表格的其他 DOM；
 * 单元格的值一律经编辑器句柄（editorHost）读写，宿主照常收到原有事件。
 */
import { effectScope, nextTick, watch, type ComponentInternalInstance, type EffectScope } from 'vue'
import { ElMessage } from 'element-plus'
import { useDisplayPrefsStore, type GridEditMode } from '@/stores/displayPrefs'
import { buildClipboardPayload, parseClipboardMatrix, parseLooseNumber, stripDecorations } from './cellValue'
import { cellFromTarget, rectWithin, scrollCellIntoView, type CellBox, type CellPos, type GridGeometry } from './gridDom'
import { anyEditor, CELL_EDITOR_ATTR, handleOfElement, primaryEditor, type CellEditorHandle, type OpenMode } from './editorHost'

export type GridState = 'idle' | 'selected' | 'entering' | 'editing' | 'picking'

interface Range { r1: number; c1: number; r2: number; c2: number }
interface UndoChange { r: number; c: number; before: unknown; after: unknown }
interface UndoEntry { changes: UndoChange[] }
interface OpenEditor { handle: CellEditorHandle; td: HTMLTableCellElement; mode: OpenMode; before: unknown; pos: CellPos }

export interface GridKernelSource {
  kind: 'el-table' | 'raw-table'
  geometry(): GridGeometry
  /** 表格所属组件实例（ElTable / GtGridTable）：useCellSelection 门面按父链认「本组件里的表」 */
  owner?: ComponentInternalInstance
}

/** source：值从编辑器来（模型值）/ 从 `data-gt-value` 来（原始金额，不受显示单位影响）/ 从显示文字解析。 */
export interface SelectedCellInfo { r: number; c: number; td: HTMLTableCellElement; text: string; value: unknown; source: CellValueSource }

/** 自激活编辑器的手势窗口（design §7 规则 1）。 */
export const GESTURE_WINDOW_MS = 300
const UNDO_LIMIT = 100

/** 点在这些元素上只选中、不拦截默认行为（让控件自己拿焦点 / 激活）。 */
const INTERACTIVE_SELECTOR = [
  'input', 'textarea', 'select', 'button', 'a[href]', 'label', '[contenteditable="true"]', '[contenteditable=""]',
  '.el-checkbox', '.el-switch', '.el-radio', '.el-radio-button', '.el-button', '.el-link', '.el-upload',
  '.el-input', '.el-input-number', '.el-select', '.el-date-editor', '[data-gt-grid-interactive]',
].join(',')
const TOGGLE_SELECTOR = '.el-checkbox, .el-switch, .el-radio, .el-radio-button'

/** 常驻的文字输入控件（一格多控件时它们不是单元格编辑器）；下拉的输入框只用于过滤，选中项文字已在格的文本里 */
const TEXT_CONTROL_SELECTOR = 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea'

/** 格的可见文字，常驻输入框按位置换成它的值（复制、统计、读屏用；innerText 不含输入框里的字） */
function textWithControlValues(root: HTMLElement): string {
  const parts: string[] = []
  const walk = (n: Node): void => {
    if (n.nodeType === Node.TEXT_NODE) { parts.push(n.textContent ?? ''); return }
    if (!(n instanceof HTMLElement)) return
    if (n.style.display === 'none' || n.hidden) return
    if (n.matches(TEXT_CONTROL_SELECTOR)) {
      if (!n.closest('.el-select')) parts.push(` ${(n as HTMLInputElement).value} `)
      return
    }
    for (const c of Array.from(n.childNodes)) walk(c)
  }
  walk(root)
  return parts.join('').replace(/\s+/g, ' ').trim()
}

export const liveKernels = new Set<GridKernel>()

// ── 给 useCellSelection 门面用的全局钩子（spec excel-style-table-editing 5.1） ──
const anyChangeListeners = new Set<(k: GridKernel) => void>()
let gridInstalled = false

/** 任一表格的选区 / 编辑状态变了（含拆掉：此时 root 为 null）时回调。 */
export function onAnyKernelChange(cb: (k: GridKernel) => void): () => void {
  anyChangeListeners.add(cb)
  return () => anyChangeListeners.delete(cb)
}

/** 元素所在表格的内核。 */
export function kernelForElement(el: Element | null | undefined): GridKernel | null {
  const root = el?.closest?.('[data-gt-grid-root]') ?? null
  if (!root) return null
  for (const k of liveKernels) if (k.root === root) return k
  return null
}

/** 插件已安装（应用里）。单测不装插件时，旧的选区实现照旧工作。 */
export function markGridInstalled(on = true): void { gridInstalled = on }
export function isGridInstalled(): boolean { return gridInstalled }

export type CellValueSource = 'editor' | 'data' | 'text'

function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a == null && b == null) return true
  if (a instanceof Date || b instanceof Date || Array.isArray(a) || Array.isArray(b)) {
    try { return JSON.stringify(a) === JSON.stringify(b) } catch { return false }
  }
  return false
}

function norm(r: Range): Range {
  return { r1: Math.min(r.r1, r.r2), c1: Math.min(r.c1, r.c2), r2: Math.max(r.r1, r.r2), c2: Math.max(r.c1, r.c2) }
}

export class GridKernel {
  root: HTMLElement | null = null
  state: GridState = 'idle'
  active: CellPos | null = null
  anchor: CellPos | null = null
  ranges: Range[] = []
  editor: OpenEditor | null = null
  readonly sink: HTMLTextAreaElement | null
  private live: HTMLElement | null = null
  private geo: GridGeometry | null = null
  private marked = new Set<HTMLElement>()
  private copyRange: Range | null = null
  private observer: MutationObserver | null = null
  private tabStartCol: number | null = null
  /** hadEditor：手势发生时这一格已有编辑器 —— 只有「点了才出现」的编辑器才按兼容规则自动打开。 */
  private lastGesture: { td: Element; at: number; hadEditor: boolean } | null = null
  private undoStack: UndoEntry[] = []
  private redoStack: UndoEntry[] = []
  private composing = false
  private opening = false
  private subscribers = new Set<() => void>()
  private scope: EffectScope | null = null
  private cleanups: Array<() => void> = []
  private raf = 0
  private hintAt = 0
  private optOut = false
  /** 单击编辑方式：mousedown 记下，click 时再打开（下拉在 mousedown 打开会被随后的 click 收起）。 */
  private clickOpen: { td: Element; at: number } | null = null

  constructor(private readonly source: GridKernelSource) {
    this.sink = typeof document !== 'undefined' ? document.createElement('textarea') : null
  }

  // ── 状态 ──────────────────────────────────────────────────────────────────
  get owner(): ComponentInternalInstance | null {
    return this.source.owner ?? null
  }

  get mode(): GridEditMode {
    try { return useDisplayPrefsStore().gridEditMode } catch { return 'excel' }
  }

  get enabled(): boolean {
    return !!this.root && !this.optOut && this.mode !== 'classic'
  }

  geometry(): GridGeometry {
    if (!this.geo) this.geo = this.source.geometry()
    return this.geo
  }

  invalidate(): void {
    this.geo = null
    this.scheduleRepaint()
  }

  onChange(cb: () => void): () => void {
    this.subscribers.add(cb)
    return () => this.subscribers.delete(cb)
  }

  private emitChange(): void {
    for (const cb of Array.from(this.subscribers)) {
      try { cb() } catch { /* 订阅方自己的错误不影响表格 */ }
    }
    for (const cb of Array.from(anyChangeListeners)) {
      try { cb(this) } catch { /* 同上 */ }
    }
  }

  // ── 挂载 ──────────────────────────────────────────────────────────────────
  /**
   * sinkHost：承接框与读屏播报放在哪（缺省放根节点里）。原生表格的根是 `<table>`，
   * 直接放进去会被当成匿名行组撑出一个 border-spacing，GtGridTable 给的是零高 `<caption>`。
   */
  attach(root: HTMLElement | null, opts: { sinkHost?: HTMLElement | null } = {}): void {
    if (!root || root === this.root) return
    if (this.root) this.detach()
    this.root = root
    this.optOut = !!root.closest('[data-gt-grid="off"]')
    root.setAttribute('data-gt-grid-root', '')
    liveKernels.add(this)
    if (this.sink) {
      const host = opts.sinkHost && root.contains(opts.sinkHost) ? opts.sinkHost : root
      const s = this.sink
      s.className = 'gt-grid-sink'
      s.setAttribute('data-gt-grid-sink', '')
      s.setAttribute('aria-label', '表格')
      s.setAttribute('autocomplete', 'off')
      s.setAttribute('spellcheck', 'false')
      s.rows = 1
      s.tabIndex = this.enabled ? 0 : -1
      host.appendChild(s)
      this.live = document.createElement('div')
      this.live.className = 'gt-grid-live'
      this.live.setAttribute('aria-live', 'polite')
      host.appendChild(this.live)
      this.listen(s, 'keydown', (e) => this.onSinkKeyDown(e as KeyboardEvent))
      this.listen(s, 'input', (e) => this.onSinkInput(e as InputEvent))
      this.listen(s, 'compositionstart', () => this.onCompositionStart())
      this.listen(s, 'compositionend', () => this.onCompositionEnd())
      this.listen(s, 'copy', (e) => this.onCopy(e as ClipboardEvent))
      this.listen(s, 'cut', (e) => this.onCut(e as ClipboardEvent))
      this.listen(s, 'paste', (e) => void this.onPaste(e as ClipboardEvent))
      this.listen(s, 'focus', () => this.setFocused(true))
    }
    this.listen(root, 'mousedown', (e) => this.onMouseDown(e as MouseEvent), true)
    this.listen(root, 'click', (e) => this.onClick(e as MouseEvent), true)
    this.listen(root, 'dblclick', (e) => this.onDblClick(e as MouseEvent), true)
    this.listen(root, 'contextmenu', (e) => this.onContextMenu(e as MouseEvent), true)
    this.listen(root, 'keydown', (e) => this.onEditorKeyDown(e as KeyboardEvent), true)
    this.listen(root, 'focusout', (e) => this.onFocusOut(e as FocusEvent), true)
    this.listen(root, 'scroll', () => this.scheduleRepaint(), true)
    if (typeof MutationObserver !== 'undefined') {
      this.observer = new MutationObserver((records) => {
        for (const rec of records) {
          const nodes = [...Array.from(rec.addedNodes), ...Array.from(rec.removedNodes)]
          if (nodes.some((n) => n.nodeName === 'TR' || n.nodeName === 'TD' || n.nodeName === 'TH' || n.nodeName === 'TBODY')) {
            this.invalidate()
            return
          }
        }
      })
      this.observer.observe(root, { childList: true, subtree: true })
    }
    this.scope = effectScope(true)
    this.scope.run(() => {
      try {
        const prefs = useDisplayPrefsStore()
        watch(() => prefs.gridEditMode, () => this.onModeChanged())
      } catch { /* 无 pinia（纯单测）时按默认方式 */ }
    })
  }

  detach(): void {
    this.commitEdit({ refocus: false })
    this.clearMarks()
    for (const off of this.cleanups.splice(0)) off()
    this.observer?.disconnect()
    this.observer = null
    this.scope?.stop()
    this.scope = null
    this.sink?.remove()
    this.live?.remove()
    this.root?.removeAttribute('data-gt-grid-root')
    this.root = null
    this.geo = null
    liveKernels.delete(this)
    this.cancelScheduled()
    for (const cb of Array.from(anyChangeListeners)) {
      try { cb(this) } catch { /* 订阅方自己的错误不影响表格 */ }
    }
  }

  private listen(el: EventTarget, type: string, fn: (e: Event) => void, capture = false): void {
    el.addEventListener(type, fn, capture)
    this.cleanups.push(() => el.removeEventListener(type, fn, capture))
  }

  private onModeChanged(): void {
    if (this.sink) this.sink.tabIndex = this.enabled ? 0 : -1
    if (!this.enabled) {
      this.commitEdit({ refocus: false })
      this.clearMarks()
    } else {
      this.repaint()
    }
  }

  // ── 选区 ──────────────────────────────────────────────────────────────────
  activeTd(): HTMLTableCellElement | null {
    return this.active ? this.geometry().cellAt(this.active.r, this.active.c) : null
  }

  private box(pos: CellPos): CellBox {
    const td = this.geometry().cellAt(pos.r, pos.c)
    return (td && this.geometry().boxOf(td)) || { ...pos, rs: 1, cs: 1 }
  }

  private clamp(pos: CellPos): CellPos {
    const g = this.geometry()
    return { r: Math.max(0, Math.min(g.rowCount - 1, pos.r)), c: Math.max(0, Math.min(g.colCount - 1, pos.c)) }
  }

  isInSelection(pos: CellPos): boolean {
    return this.ranges.some((rg) => pos.r >= rg.r1 && pos.r <= rg.r2 && pos.c >= rg.c1 && pos.c <= rg.c2)
  }

  /** 选中一格（extend：从锚点扩展；add：Ctrl 追加一个区域）。 */
  select(pos: CellPos, opts: { extend?: boolean; add?: boolean; scroll?: boolean } = {}): void {
    const g = this.geometry()
    if (!g.rowCount || !g.colCount) return
    const p = this.clamp(pos)
    const b = this.box(p)
    if (opts.extend && this.anchor) {
      const a = this.box(this.anchor)
      const rg = norm({ r1: a.r, c1: a.c, r2: b.r + b.rs - 1, c2: b.c + b.cs - 1 })
      this.ranges = [...this.ranges.slice(0, -1), this.expandForMerges(rg)]
      this.active = { r: b.r, c: b.c }
    } else {
      const rg: Range = { r1: b.r, c1: b.c, r2: b.r + b.rs - 1, c2: b.c + b.cs - 1 }
      this.ranges = opts.add ? [...this.ranges, rg] : [rg]
      this.active = { r: b.r, c: b.c }
      this.anchor = { r: b.r, c: b.c }
    }
    if (this.state === 'idle') this.state = 'selected'
    this.repaint()
    if (opts.scroll !== false) {
      const td = this.activeTd()
      if (td) scrollCellIntoView(td)
    }
    this.announce()
    this.emitChange()
  }

  /** 区域碰到合并单元格时外扩到把它整个包进来（与 Excel 一致）。 */
  private expandForMerges(rg: Range): Range {
    const g = this.geometry()
    let out = { ...rg }
    for (let guard = 0; guard < 8; guard++) {
      let grown = false
      for (let r = out.r1; r <= out.r2; r++) {
        for (let c = out.c1; c <= out.c2; c++) {
          const td = g.cellAt(r, c)
          const b = td && g.boxOf(td)
          if (!b) continue
          const next = norm({ r1: Math.min(out.r1, b.r), c1: Math.min(out.c1, b.c), r2: Math.max(out.r2, b.r + b.rs - 1), c2: Math.max(out.c2, b.c + b.cs - 1) })
          if (next.r1 !== out.r1 || next.c1 !== out.c1 || next.r2 !== out.r2 || next.c2 !== out.c2) { out = next; grown = true }
        }
      }
      if (!grown) break
    }
    return out
  }

  selectAll(): void {
    const g = this.geometry()
    if (!g.rowCount || !g.colCount) return
    if (!this.active) this.select({ r: 0, c: 0 }, { scroll: false })
    this.ranges = [{ r1: 0, c1: 0, r2: g.rowCount - 1, c2: g.colCount - 1 }]
    this.repaint()
    this.emitChange()
  }

  clearSelection(): void {
    this.ranges = []
    this.active = null
    this.anchor = null
    this.state = 'idle'
    this.clearMarks()
    this.emitChange()
  }

  /** 选中矩形区域（行列为本表坐标；超出部分夹到表内）。 */
  selectRect(r1: number, c1: number, r2: number, c2: number): void {
    const g = this.geometry()
    if (!g.rowCount || !g.colCount) return
    const a = this.clamp({ r: r1, c: c1 })
    const b = this.clamp({ r: r2, c: c2 })
    this.select(a, { scroll: false })
    this.ranges = [this.expandForMerges(norm({ r1: a.r, c1: a.c, r2: b.r, c2: b.c }))]
    this.repaint()
    this.emitChange()
  }

  /** 把选区按显示文字复制到剪贴板（制表符文本 + HTML 表格，与 Ctrl+C 同口径）；右键菜单「复制」用。 */
  async copySelectionToClipboard(): Promise<boolean> {
    const matrix = this.selectionMatrix()
    if (!matrix.length) return false
    const { text, html } = buildClipboardPayload(matrix)
    this.copyRange = this.primaryRange()
    this.repaint()
    const nav = typeof navigator !== 'undefined' ? navigator : null
    try {
      if (nav?.clipboard && typeof ClipboardItem !== 'undefined' && typeof nav.clipboard.write === 'function') {
        await nav.clipboard.write([new ClipboardItem({
          'text/plain': new Blob([text], { type: 'text/plain' }),
          'text/html': new Blob([html], { type: 'text/html' }),
        })])
        return true
      }
    } catch { /* 浏览器不支持多格式写入：退回纯文本 */ }
    try {
      await nav?.clipboard?.writeText(text)
      return !!nav?.clipboard
    } catch {
      return false
    }
  }

  /** 选区内的格（只算源格，按行列顺序）。 */
  selectedCells(): SelectedCellInfo[] {
    const g = this.geometry()
    const seen = new Set<Element>()
    const out: SelectedCellInfo[] = []
    for (const rg of this.ranges) {
      for (let r = rg.r1; r <= rg.r2; r++) {
        for (let c = rg.c1; c <= rg.c2; c++) {
          const td = g.cellAt(r, c)
          if (!td || seen.has(td)) continue
          seen.add(td)
          const b = g.boxOf(td)
          if (!b) continue
          const { value, source } = this.cellValueWithSource(td)
          out.push({ r: b.r, c: b.c, td, text: this.cellText(td), value, source })
        }
      }
    }
    return out
  }

  cellText(td: HTMLTableCellElement): string {
    const h = anyEditor(td)
    if (h) return h.getText()
    const el = td as HTMLElement
    if (el.querySelector(TEXT_CONTROL_SELECTOR)) return stripDecorations(textWithControlValues(el))
    return stripDecorations(el.innerText ?? el.textContent ?? '')
  }

  cellValue(td: HTMLTableCellElement): unknown {
    return this.cellValueWithSource(td).value
  }

  /**
   * 格的值：编辑器的模型值 → 格里唯一一个 `data-gt-value`（GtAmountCell 写的原始金额，不受「万元」等显示单位影响）
   * → 显示文字解析成数字 → 显示文字。
   */
  cellValueWithSource(td: HTMLTableCellElement): { value: unknown; source: CellValueSource } {
    const h = anyEditor(td)
    if (h) return { value: h.getValue(), source: 'editor' }
    const marks = td.querySelectorAll('[data-gt-value]')
    if (marks.length === 1) {
      const raw = marks[0].getAttribute('data-gt-value') ?? ''
      if (raw === '') return { value: null, source: 'data' }
      const n = Number(raw)
      return { value: Number.isFinite(n) ? n : raw, source: 'data' }
    }
    const text = this.cellText(td)
    return { value: parseLooseNumber(text) ?? text, source: 'text' }
  }

  // ── 绘制 ──────────────────────────────────────────────────────────────────
  private clearMarks(): void {
    for (const td of this.marked) {
      td.removeAttribute('data-gt-sel')
      td.removeAttribute('data-gt-active')
      td.removeAttribute('data-gt-copy')
    }
    this.marked.clear()
  }

  private paintRange(rg: Range, attr: 'data-gt-sel' | 'data-gt-copy'): void {
    const g = this.geometry()
    for (let r = rg.r1; r <= rg.r2; r++) {
      for (let c = rg.c1; c <= rg.c2; c++) {
        const td = g.cellAt(r, c)
        const b = td && g.boxOf(td)
        if (!td || !b || b.r !== r || b.c !== c) continue
        const edges = [
          b.r === rg.r1 ? 't' : '', b.r + b.rs - 1 === rg.r2 ? 'b' : '',
          b.c === rg.c1 ? 'l' : '', b.c + b.cs - 1 === rg.c2 ? 'r' : '',
        ].filter(Boolean).join(' ')
        td.setAttribute(attr, edges || 'in')
        this.marked.add(td)
      }
    }
  }

  private cancelScheduled(): void {
    if (!this.raf) return
    if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(this.raf)
    else clearTimeout(this.raf)
    this.raf = 0
  }

  repaint(): void {
    this.cancelScheduled()
    this.clearMarks()
    if (!this.enabled || !this.root) return
    if (this.editor && !this.editor.td.isConnected) {
      this.editor = null
      this.state = this.active ? 'selected' : 'idle'
    }
    for (const rg of this.ranges) this.paintRange(rg, 'data-gt-sel')
    if (this.copyRange) this.paintRange(this.copyRange, 'data-gt-copy')
    const td = this.activeTd()
    if (td) {
      td.setAttribute('data-gt-active', '')
      this.marked.add(td)
    }
    this.positionSink()
  }

  private scheduleRepaint(): void {
    if (this.raf) return
    const run = () => { this.raf = 0; this.repaint() }
    this.raf = typeof requestAnimationFrame === 'function'
      ? requestAnimationFrame(run)
      : (setTimeout(run, 16) as unknown as number)
  }

  private positionSink(): void {
    const s = this.sink
    const td = this.activeTd()
    if (!s || !this.root) return
    if (!td) { s.style.width = '0px'; s.style.height = '0px'; return }
    const rect = rectWithin(td, this.root)
    s.style.left = `${rect.left}px`
    s.style.top = `${rect.top}px`
    s.style.width = `${Math.max(0, rect.width)}px`
    s.style.height = `${Math.max(0, rect.height)}px`
  }

  private setFocused(on: boolean): void {
    this.root?.toggleAttribute('data-gt-grid-focused', on)
  }

  focusSink(): void {
    if (!this.sink || !this.enabled) return
    this.positionSink()
    try { this.sink.focus({ preventScroll: true }) } catch { this.sink.focus() }
    this.setFocused(true)
  }

  private announce(): void {
    const td = this.activeTd()
    if (!this.live || !td || !this.active) return
    const label = this.geometry().columnLabel(this.active.c)
    const h = primaryEditor(td)
    const text = this.cellText(td)
    const msg = `${label ? label + '，' : ''}第 ${this.active.r + 1} 行：${text || '空'}${h ? '（可编辑）' : ''}`
    this.live.textContent = msg
    this.sink?.setAttribute('aria-label', msg)
  }

  // ── 导航 ──────────────────────────────────────────────────────────────────
  moveBy(dr: number, dc: number, opts: { extend?: boolean; jump?: boolean } = {}): void {
    const g = this.geometry()
    if (!g.rowCount) return
    const from = opts.extend && this.ranges.length ? this.extendHead() : this.active ?? { r: 0, c: 0 }
    const b = this.box(from)
    let r = dr > 0 ? b.r + b.rs - 1 + dr : b.r + dr
    let c = dc > 0 ? b.c + b.cs - 1 + dc : b.c + dc
    if (dr === 0) r = from.r
    if (dc === 0) c = from.c
    if (opts.jump) {
      if (dr) r = dr > 0 ? g.rowCount - 1 : 0
      if (dc) c = dc > 0 ? g.colCount - 1 : 0
    }
    this.tabStartCol = null
    if (opts.extend) this.extendTo(this.clamp({ r, c }))
    else this.select({ r, c })
  }

  /** Shift 扩展时，扩展端（区域里离锚点最远的一角）。 */
  private extendHead(): CellPos {
    const rg = this.ranges[this.ranges.length - 1]
    const a = this.anchor ?? { r: rg.r1, c: rg.c1 }
    return { r: a.r === rg.r1 ? rg.r2 : rg.r1, c: a.c === rg.c1 ? rg.c2 : rg.c1 }
  }

  private extendTo(pos: CellPos): void {
    if (!this.anchor) { this.select(pos); return }
    const a = this.anchor
    const b = this.box(pos)
    const rg = this.expandForMerges(norm({ r1: a.r, c1: a.c, r2: pos.r < a.r ? b.r : b.r + b.rs - 1, c2: pos.c < a.c ? b.c : b.c + b.cs - 1 }))
    this.ranges = [...this.ranges.slice(0, -1), rg]
    this.repaint()
    const td = this.geometry().cellAt(pos.r, pos.c)
    if (td) scrollCellIntoView(td)
    this.emitChange()
  }

  moveVertical(dir: 1 | -1): void {
    if (!this.active) return
    if (this.tabStartCol != null) {
      const c = this.tabStartCol
      this.tabStartCol = null
      const b = this.box(this.active)
      this.select({ r: dir > 0 ? b.r + b.rs : b.r - 1, c })
      return
    }
    this.moveBy(dir, 0)
  }

  /** Tab：读顺序找下一个（上一个）可编辑格；找不到返回 false（焦点按浏览器默认离开表格）。 */
  moveTab(back: boolean): boolean {
    const g = this.geometry()
    if (!this.active || !g.rowCount) return false
    const start = this.active
    if (this.tabStartCol == null) this.tabStartCol = start.c
    const total = g.rowCount * g.colCount
    let idx = start.r * g.colCount + start.c
    for (let step = 0; step < total; step++) {
      idx += back ? -1 : 1
      if (idx < 0 || idx >= total) break
      const r = Math.floor(idx / g.colCount)
      const c = idx % g.colCount
      const td = g.cellAt(r, c)
      const b = td && g.boxOf(td)
      if (!td || !b || b.r !== r || b.c !== c) continue
      const h = primaryEditor(td)
      if (h && h.editable()) {
        const keep = this.tabStartCol
        this.select({ r, c })
        this.tabStartCol = keep
        return true
      }
    }
    this.tabStartCol = null
    return false
  }

  // ── 编辑 ──────────────────────────────────────────────────────────────────
  /** 页面自己「点了才渲染」的编辑器挂载时问一句：刚在这一格有过手势吗（design §7 规则 1）。 */
  hadRecentGesture(td: Element | null): boolean {
    const g = this.lastGesture
    return !!td && !!g && g.td === td && !g.hadEditor && Date.now() - g.at < GESTURE_WINDOW_MS && !this.editor
  }

  private noteGesture(td: Element): void {
    this.lastGesture = { td, at: Date.now(), hadEditor: !!anyEditor(td) }
  }

  async openEditor(handle: CellEditorHandle, td: HTMLTableCellElement, mode: OpenMode, initialText?: string): Promise<boolean> {
    if (!this.root || this.opening) return false
    if (this.editor && this.editor.handle === handle) return true
    if (this.editor) this.commitEdit({ refocus: false })
    const b = this.geometry().boxOf(td)
    if (b && (!this.active || this.active.r !== b.r || this.active.c !== b.c)) this.select({ r: b.r, c: b.c })
    const pos = b ? { r: b.r, c: b.c } : this.active ?? { r: 0, c: 0 }
    this.opening = true
    this.editor = { handle, td, mode, before: handle.getValue(), pos }
    this.state = mode
    td.setAttribute('data-gt-editing', '')
    this.copyRange = null
    try {
      const ok = await handle.open({
        mode,
        initialText,
        takePendingText: () => {
          const t = this.sink?.value ?? ''
          if (this.sink) this.sink.value = ''
          return t
        },
      })
      if (!ok && this.editor?.handle === handle) this.finish(null, true)
      return ok
    } finally {
      this.opening = false
    }
  }

  openActive(mode: OpenMode, initialText?: string): void {
    const td = this.activeTd()
    const h = primaryEditor(td)
    if (!td || !h || !h.editable()) { this.hintReadonly(); return }
    if (h.kind === 'toggle') { h.toggle?.(); return }
    const m = h.kind === 'select' || h.kind === 'date' ? 'picking' : mode
    void this.openEditor(h, td, m, initialText)
  }

  /** 提交正在编辑的格；refocus=false 用于焦点已离开表格的情形。 */
  commitEdit(opts: { refocus?: boolean } = {}): void {
    const ed = this.editor
    if (!ed) return
    this.editor = null
    let after: unknown
    try { after = ed.handle.commit() } catch { after = ed.before }
    this.recordEdit(ed, after)
    this.finish(ed, opts.refocus !== false)
  }

  cancelEdit(): void {
    const ed = this.editor
    if (!ed) return
    this.editor = null
    try { ed.handle.cancel() } catch { /* 还原失败不影响表格状态 */ }
    this.finish(ed, true)
  }

  /** 编辑器自己结束（下拉选定、失焦提交）时调用。 */
  editorFinished(handle: CellEditorHandle, committedValue: unknown, opts: { refocus?: boolean } = {}): void {
    const ed = this.editor
    if (!ed || ed.handle !== handle) return
    this.editor = null
    this.recordEdit(ed, committedValue)
    this.finish(ed, opts.refocus !== false)
  }

  private recordEdit(ed: OpenEditor, after: unknown): void {
    if (sameValue(ed.before, after)) return
    this.pushUndo({ changes: [{ r: ed.pos.r, c: ed.pos.c, before: ed.before, after }] })
  }

  private finish(ed: OpenEditor | null, refocus: boolean): void {
    ed?.td.removeAttribute('data-gt-editing')
    this.state = this.active ? 'selected' : 'idle'
    if (refocus) this.focusSink()
    this.scheduleRepaint()
    this.emitChange()
  }

  isEditing(handle?: CellEditorHandle): boolean {
    return handle ? this.editor?.handle === handle : !!this.editor
  }

  editorMode(): OpenMode | null {
    return this.editor?.mode ?? null
  }

  private hintReadonly(): void {
    const now = Date.now()
    if (now - this.hintAt < 2000) return
    this.hintAt = now
    ElMessage({ message: '该单元格不可编辑', type: 'info', duration: 1500, grouping: true })
  }

  // ── 鼠标 ──────────────────────────────────────────────────────────────────
  private onMouseDown(e: MouseEvent): void {
    if (!this.enabled || e.button !== 0 || e.target === this.sink) return
    const target = e.target as Element | null
    const td = cellFromTarget(target, this.geometry())
    if (!td) {
      if (this.editor && !(target && this.editor.td.contains(target))) this.commitEdit({ refocus: false })
      return
    }
    if (this.editor && this.editor.td === td && target && td.contains(target)) return
    if (this.editor) this.commitEdit({ refocus: false })
    this.noteGesture(td)
    const b = this.geometry().boxOf(td)!
    const interactive = !!target?.closest(INTERACTIVE_SELECTOR) && td.contains(target!.closest(INTERACTIVE_SELECTOR))
    if (e.shiftKey && this.active) this.extendTo({ r: b.r, c: b.c })
    else this.select({ r: b.r, c: b.c }, { add: (e.ctrlKey || e.metaKey) && !!this.active, scroll: false })
    if (interactive) {
      if (target?.closest(TOGGLE_SELECTOR)) setTimeout(() => this.focusSink(), 0)
      return
    }
    e.preventDefault()
    this.focusSink()
    this.clickOpen = null
    if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
      this.startDrag()
      if (this.mode === 'click') this.clickOpen = { td, at: Date.now() }
    }
  }

  private onClick(e: MouseEvent): void {
    const pending = this.clickOpen
    this.clickOpen = null
    if (!pending || !this.enabled || this.editor) return
    const td = cellFromTarget(e.target, this.geometry())
    if (td !== pending.td || Date.now() - pending.at > 800) return
    const rg = this.primaryRange()
    if (rg && (rg.r1 !== rg.r2 || rg.c1 !== rg.c2)) return // 拖成了区域：不打开
    const h = primaryEditor(td)
    if (h && h.editable() && h.kind !== 'toggle') {
      void this.openEditor(h, td, h.kind === 'select' || h.kind === 'date' ? 'picking' : 'editing')
    }
  }

  private startDrag(): void {
    const move = (ev: MouseEvent) => {
      const td = cellFromTarget(ev.target, this.geometry())
      const b = td && this.geometry().boxOf(td)
      if (b) this.extendTo({ r: b.r, c: b.c })
    }
    const up = () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
      document.body.classList.remove('gt-grid-dragging')
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
    document.body.classList.add('gt-grid-dragging')
  }

  private onDblClick(e: MouseEvent): void {
    if (!this.enabled) return
    const td = cellFromTarget(e.target, this.geometry())
    if (!td || (this.editor && this.editor.td === td)) return
    this.noteGesture(td)
    const h = primaryEditor(td)
    if (!h || !h.editable() || h.kind === 'toggle') return // 只读格：放行页面原有的双击穿透
    e.stopPropagation()
    e.preventDefault()
    void this.openEditor(h, td, h.kind === 'select' || h.kind === 'date' ? 'picking' : 'editing')
  }

  private onContextMenu(e: MouseEvent): void {
    if (!this.enabled) return
    const td = cellFromTarget(e.target, this.geometry())
    const b = td && this.geometry().boxOf(td)
    if (!b) return
    if (this.editor && this.editor.td !== td) this.commitEdit({ refocus: false })
    if (!this.isInSelection({ r: b.r, c: b.c })) this.select({ r: b.r, c: b.c }, { scroll: false })
  }

  private onFocusOut(e: FocusEvent): void {
    const next = e.relatedTarget as Element | null
    if (next && this.root && (this.root.contains(next) || next.closest('.el-popper'))) return
    setTimeout(() => {
      if (!this.root) return
      const a = document.activeElement
      if (a && (this.root.contains(a) || a.closest('.el-popper'))) return
      if (this.editor) this.commitEdit({ refocus: false })
      this.setFocused(false)
    }, 0)
  }

  // ── 键盘 ──────────────────────────────────────────────────────────────────
  /** 编辑中的按键（根节点捕获阶段：先于控件自身处理，例如 el-input-number 的上下键加减）。 */
  private onEditorKeyDown(e: KeyboardEvent): void {
    const ed = this.editor
    if (!this.enabled || !ed || e.target === this.sink) return
    if (!(e.target instanceof Node) || !ed.td.contains(e.target)) return
    if (e.isComposing || e.keyCode === 229) return
    const ctrl = e.ctrlKey || e.metaKey
    switch (e.key) {
      case 'Escape':
        e.preventDefault()
        e.stopPropagation()
        this.cancelEdit()
        return
      case 'Enter':
        if (ed.mode === 'picking' || ctrl) return
        if (e.altKey) {
          if (ed.handle.multiline()) { e.preventDefault(); insertNewline(e.target) }
          return
        }
        e.preventDefault()
        e.stopPropagation()
        this.commitEdit()
        this.moveVertical(e.shiftKey ? -1 : 1)
        return
      case 'Tab':
        e.preventDefault()
        e.stopPropagation()
        this.commitEdit()
        if (!this.moveTab(e.shiftKey)) this.focusSink()
        return
      case 'F2':
        e.preventDefault()
        if (ed.mode !== 'picking') ed.mode = ed.mode === 'editing' ? 'entering' : 'editing'
        this.state = ed.mode
        return
      case 'ArrowUp': case 'ArrowDown': case 'ArrowLeft': case 'ArrowRight': {
        if (ed.mode !== 'entering' || e.altKey) return
        e.preventDefault()
        e.stopPropagation()
        this.commitEdit()
        const [dr, dc] = arrowDelta(e.key)
        this.moveBy(dr, dc, { extend: e.shiftKey, jump: ctrl })
        return
      }
      default:
        // Ctrl+S 不在这里提交：全局快捷键（utils/shortcuts.ts）先提交再保存 ——
        // 这里先提交会去掉 data-gt-editing，快捷键那边就认不出「编辑中的格」了
        break
    }
  }

  private onSinkKeyDown(e: KeyboardEvent): void {
    if (!this.enabled || e.isComposing || e.keyCode === 229) return
    const ctrl = e.ctrlKey || e.metaKey
    const stop = () => { e.preventDefault(); e.stopPropagation() }
    // 只读表：Enter / Backspace / Delete 交还页面（不移动、不提示，见 hasEditableCell）
    if ((e.key === 'Enter' || e.key === 'Backspace' || e.key === 'Delete') && !this.hasEditableCell()) return
    if (!this.active && /^(Arrow|Home|End|Page|Tab$|Enter$)/.test(e.key)) {
      if (e.key === 'Tab') return
      stop()
      this.select({ r: 0, c: 0 })
      return
    }
    switch (e.key) {
      case 'ArrowUp': case 'ArrowDown': case 'ArrowLeft': case 'ArrowRight': {
        if (e.altKey) return
        stop()
        const [dr, dc] = arrowDelta(e.key)
        this.moveBy(dr, dc, { extend: e.shiftKey, jump: ctrl })
        return
      }
      case 'Home':
        stop()
        if (ctrl) this.select({ r: 0, c: 0 })
        else if (this.active) this.select({ r: this.active.r, c: 0 })
        return
      case 'End': {
        stop()
        const g = this.geometry()
        if (ctrl) this.select({ r: g.rowCount - 1, c: g.colCount - 1 })
        else if (this.active) this.select({ r: this.active.r, c: g.colCount - 1 })
        return
      }
      case 'PageDown': case 'PageUp':
        stop()
        this.moveBy(e.key === 'PageDown' ? this.pageRows() : -this.pageRows(), 0, { extend: e.shiftKey })
        return
      case 'Enter':
        if (ctrl || e.altKey) return
        stop()
        this.moveVertical(e.shiftKey ? -1 : 1)
        return
      case 'Tab':
        if (this.moveTab(e.shiftKey)) stop()
        return
      case 'F2':
        stop()
        this.openActive('editing')
        return
      case 'Delete':
        stop()
        void this.clearCells()
        return
      case 'Backspace':
        stop()
        this.openActive('entering', '')
        return
      case 'Escape':
        if (this.copyRange) { this.copyRange = null; this.repaint() }
        return
      case ' ': {
        const h = primaryEditor(this.activeTd())
        if (h?.kind === 'toggle' && h.editable()) { stop(); this.toggleCells(); }
        return
      }
      default:
        break
    }
    if (!ctrl) return
    const k = e.key.toLowerCase()
    if (k === 'a') { stop(); this.selectAll() }
    else if (k === 'z' && !e.shiftKey && this.undoStack.length) { stop(); void this.undo() }
    else if ((k === 'y' || (k === 'z' && e.shiftKey)) && this.redoStack.length) { stop(); void this.redo() }
  }

  /**
   * 整张表有没有可编辑的格（嵌套子表不算）。没有的（只读列表、报表）把 Enter / Backspace / Delete 交还页面：
   * 页面常拿它们做「返回上级 / 返回上一页」（试算表溯源返回、查账穿透、全局返回栈），选中单元格后照常可用；
   * 有可编辑格的表照 Excel：Enter 下移、Backspace 清空开始输入、Delete 清空（只读格轻提示）。
   */
  private hasEditableCell(): boolean {
    const root = this.root
    if (!root) return false
    const geo = this.geometry()
    for (const el of Array.from(root.querySelectorAll(`[${CELL_EDITOR_ATTR}]`))) {
      const td = el.closest('td, th') as HTMLTableCellElement | null // 最近的格：嵌套子表里的编辑器归子表
      if (td && geo.boxOf(td) && handleOfElement(el)?.editable()) return true
    }
    return false
  }

  private pageRows(): number {
    const td = this.activeTd()
    const scroller = this.root?.querySelector('.el-scrollbar__wrap') as HTMLElement | null
    const h = td?.getBoundingClientRect().height || 24
    return Math.max(1, Math.floor(((scroller?.clientHeight || 480) / h) - 1))
  }

  private onSinkInput(e: InputEvent): void {
    if (this.composing || e.isComposing || !this.sink) return
    const text = this.sink.value
    if (text) this.beginTyping(text)
  }

  private onCompositionStart(): void {
    this.composing = true
    const h = primaryEditor(this.activeTd())
    if (h && h.editable() && h.kind !== 'toggle') this.sink?.classList.add('gt-grid-sink--composing')
  }

  private onCompositionEnd(): void {
    this.composing = false
    this.sink?.classList.remove('gt-grid-sink--composing')
    const text = this.sink?.value ?? ''
    if (text) this.beginTyping(text)
  }

  private beginTyping(text: string): void {
    const td = this.activeTd()
    const h = primaryEditor(td)
    if (!td || !h || !h.editable() || h.kind === 'toggle') {
      if (this.sink) this.sink.value = ''
      if (td) this.hintReadonly()
      return
    }
    if (this.opening) return // 编辑器正在挂载：字留在承接框里，挂好后一并取走
    if (this.sink) this.sink.value = ''
    void this.openEditor(h, td, h.kind === 'select' || h.kind === 'date' ? 'picking' : 'entering', text)
  }

  // ── 复制 / 剪切 / 粘贴 / 清空 ─────────────────────────────────────────────
  private primaryRange(): Range | null {
    return this.ranges.length ? this.ranges[this.ranges.length - 1] : null
  }

  selectionMatrix(): string[][] {
    const rg = this.primaryRange()
    if (!rg) return []
    const g = this.geometry()
    const out: string[][] = []
    for (let r = rg.r1; r <= rg.r2; r++) {
      const row: string[] = []
      for (let c = rg.c1; c <= rg.c2; c++) {
        const td = g.cellAt(r, c)
        const b = td && g.boxOf(td)
        row.push(td && b && b.r === r && b.c === c ? this.cellText(td) : '')
      }
      out.push(row)
    }
    return out
  }

  private onCopy(e: ClipboardEvent): void {
    if (!this.enabled || !this.active || !e.clipboardData) return
    const { text, html } = buildClipboardPayload(this.selectionMatrix())
    e.clipboardData.setData('text/plain', text)
    e.clipboardData.setData('text/html', html)
    e.preventDefault()
    this.copyRange = this.primaryRange()
    this.repaint()
  }

  private onCut(e: ClipboardEvent): void {
    this.onCopy(e)
    if (e.defaultPrevented) void this.clearCells()
  }

  private async onPaste(e: ClipboardEvent): Promise<void> {
    if (!this.enabled || !this.active || !e.clipboardData) return
    e.preventDefault() // 不让文字落进承接框；不阻止冒泡 —— 页面自己的粘贴导入照常收到
    const matrix = parseClipboardMatrix(e.clipboardData.getData('text/plain'), e.clipboardData.getData('text/html'))
    if (matrix.length) await this.applyMatrix(matrix)
  }

  /** 把矩阵写进选区（单个值粘到区域则填满）；返回写入 / 跳过 / 失败 / 超出数。 */
  async applyMatrix(matrix: string[][]): Promise<{ written: number; skipped: number; failed: number; overflow: number }> {
    const rg = this.primaryRange()
    const g = this.geometry()
    const res = { written: 0, skipped: 0, failed: 0, overflow: 0 }
    if (!rg || !matrix.length) return res
    const width = Math.max(...matrix.map((r) => r.length))
    const fill = matrix.length === 1 && width === 1 && (rg.r2 > rg.r1 || rg.c2 > rg.c1)
    const targets: Array<{ r: number; c: number; text: string }> = []
    if (fill) {
      for (let r = rg.r1; r <= rg.r2; r++) for (let c = rg.c1; c <= rg.c2; c++) targets.push({ r, c, text: matrix[0][0] })
    } else {
      matrix.forEach((row, i) => row.forEach((text, j) => {
        const r = rg.r1 + i
        const c = rg.c1 + j
        if (r >= g.rowCount || c >= g.colCount) res.overflow++
        else targets.push({ r, c, text })
      }))
    }
    // 目标里一个编辑器都没有（纯只读表）：不接管，交给页面自己的粘贴处理；有编辑器但都锁着则照常计数提示
    if (!targets.some(({ r, c }) => !!anyEditor(g.cellAt(r, c)))) return res
    const changes: UndoChange[] = []
    for (const t of targets) {
      const td = g.cellAt(t.r, t.c)
      const b = td && g.boxOf(td)
      if (!td || !b || b.r !== t.r || b.c !== t.c) continue
      const h = primaryEditor(td)
      if (!h || !h.editable()) { res.skipped++; continue }
      const before = h.getValue()
      const out = await h.applyText(t.text)
      if (out.ok) { res.written++; if (!sameValue(before, out.value)) changes.push({ r: t.r, c: t.c, before, after: out.value }) }
      else res.failed++
    }
    if (changes.length) this.pushUndo({ changes })
    if (!fill && res.written) {
      this.ranges = [this.expandForMerges({ r1: rg.r1, c1: rg.c1, r2: Math.min(g.rowCount - 1, rg.r1 + matrix.length - 1), c2: Math.min(g.colCount - 1, rg.c1 + width - 1) })]
    }
    this.copyRange = null
    this.repaint()
    this.emitChange()
    const parts = [`已粘贴 ${res.written} 格`]
    if (res.skipped) parts.push(`${res.skipped} 格不可编辑未改`)
    if (res.failed) parts.push(`${res.failed} 格格式不符未改`)
    if (res.overflow) parts.push(`${res.overflow} 格超出表格未粘贴`)
    ElMessage({ message: parts.join('，'), type: res.skipped || res.failed || res.overflow ? 'warning' : 'success', grouping: true })
    return res
  }

  /** Delete：清空选区内可编辑格。 */
  async clearCells(): Promise<number> {
    const changes: UndoChange[] = []
    for (const cell of this.selectedCells()) {
      const h = primaryEditor(cell.td)
      if (!h || !h.editable()) continue
      const before = h.getValue()
      const out = await h.applyText('')
      if (out.ok && !sameValue(before, out.value)) changes.push({ r: cell.r, c: cell.c, before, after: out.value })
    }
    if (changes.length) this.pushUndo({ changes })
    this.repaint()
    this.emitChange()
    return changes.length
  }

  private toggleCells(): void {
    const changes: UndoChange[] = []
    for (const cell of this.selectedCells()) {
      const h = primaryEditor(cell.td)
      if (!h || h.kind !== 'toggle' || !h.editable() || !h.toggle) continue
      const before = h.getValue()
      h.toggle()
      changes.push({ r: cell.r, c: cell.c, before, after: h.getValue() })
    }
    if (changes.length) this.pushUndo({ changes })
  }

  // ── 撤销 ──────────────────────────────────────────────────────────────────
  private pushUndo(entry: UndoEntry): void {
    this.undoStack.push(entry)
    if (this.undoStack.length > UNDO_LIMIT) this.undoStack.shift()
    this.redoStack = []
    void this.settleChanges(entry.changes, 'after')
  }

  /**
   * 宿主收到值后可能当场规整（WpAmountInput 失焦写回两位小数、千分位）：等这一轮渲染完，
   * 按格里实际的值记账 —— 否则撤销时「现值 ≠ 记下的值」，被当成别人改过而跳过（浏览器实测）。
   */
  private async settleChanges(changes: UndoChange[], side: 'before' | 'after'): Promise<void> {
    if (!changes.length) return
    await nextTick()
    if (!this.root) return
    this.geo = null
    const g = this.geometry()
    for (const ch of changes) {
      const h = primaryEditor(g.cellAt(ch.r, ch.c))
      if (h) ch[side] = h.getValue()
    }
  }

  canUndo(): boolean { return this.undoStack.length > 0 }
  canRedo(): boolean { return this.redoStack.length > 0 }

  async undo(): Promise<number> { return this.replay(this.undoStack, this.redoStack, 'before', 'after') }
  async redo(): Promise<number> { return this.replay(this.redoStack, this.undoStack, 'after', 'before') }

  private async replay(from: UndoEntry[], to: UndoEntry[], target: 'before' | 'after', expect: 'before' | 'after'): Promise<number> {
    const entry = from.pop()
    if (!entry) return 0
    const g = this.geometry()
    let applied = 0
    let stale = 0
    const written: UndoChange[] = []
    for (const ch of entry.changes) {
      const h = primaryEditor(g.cellAt(ch.r, ch.c))
      if (!h || !h.editable()) { stale++; continue }
      if (!sameValue(h.getValue(), ch[expect])) { stale++; continue }
      if (await h.setValue(ch[target])) { applied++; written.push(ch) }
    }
    to.push(entry)
    void this.settleChanges(written, target)
    this.repaint()
    this.emitChange()
    if (stale) ElMessage({ message: `${stale} 格已被其他操作修改，未${target === 'before' ? '撤销' : '重做'}`, type: 'warning', grouping: true })
    return applied
  }
}

function arrowDelta(key: string): [number, number] {
  if (key === 'ArrowUp') return [-1, 0]
  if (key === 'ArrowDown') return [1, 0]
  if (key === 'ArrowLeft') return [0, -1]
  return [0, 1]
}

/** 文本框 Alt+Enter 换行：在光标处插入换行并发 input（让控件按用户输入处理）。 */
function insertNewline(target: EventTarget | null): void {
  const el = target as HTMLTextAreaElement | HTMLInputElement | null
  if (!el || typeof el.setRangeText !== 'function') return
  el.setRangeText('\n', el.selectionStart ?? el.value.length, el.selectionEnd ?? el.value.length, 'end')
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

/** 提交所有表格里正在编辑的格（Ctrl+S、切换在线编辑、切换编辑方式前调用）。 */
export function commitAllGridEdits(): void {
  for (const k of Array.from(liveKernels)) k.commitEdit({ refocus: false })
}

/** 元素是不是某张表格的承接框（全局快捷键用：承接框不算输入框）。 */
export function isGridSink(el: EventTarget | null): boolean {
  return el instanceof Element && el.hasAttribute('data-gt-grid-sink')
}

/** 元素是不是在某张表格正在编辑的格里。 */
export function isInsideGridEditor(el: EventTarget | null): boolean {
  return el instanceof Element && !!el.closest('[data-gt-editing]') && !!el.closest('[data-gt-grid-root]')
}

export type { SelectedCellInfo as GridSelectedCell }
