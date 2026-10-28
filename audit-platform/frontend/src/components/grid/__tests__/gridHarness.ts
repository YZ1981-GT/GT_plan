/**
 * 表格交互测试夹具：真实 el-table（element-plus/es，与适配组件同一份）+ 适配组件 + 全局 mixin。
 * vitest 未接组件解析器，这里按名字注册适配组件，模板写法与生产一致。
 */
import { defineComponent, nextTick, type Component } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElButton, ElOption, ElPopover, ElRadio, ElTable, ElTableColumn } from 'element-plus/es'
import { liveKernels, type GridKernel } from '../GridKernel'
import * as A from '../adapters'
import GtGridCell from '../GtGridCell.vue'
import GtGridTable from '../GtGridTable.vue'
import { gridTableMixin } from '../plugin'

export const gridComponents = {
  ElTable, ElTableColumn, ElOption, ElRadio, ElPopover, ElButton,
  ElInput: A.ElInput, ElInputNumber: A.ElInputNumber, ElSelect: A.ElSelect, ElDatePicker: A.ElDatePicker,
  ElCheckbox: A.ElCheckbox, ElSwitch: A.ElSwitch, ElRadioGroup: A.ElRadioGroup,
  GtGridCell, GtGridTable,
}

const live: VueWrapper[] = []

export async function mountGrid(
  template: string,
  data: () => Record<string, unknown>,
  methods: Record<string, (...args: never[]) => unknown> = {},
  /** 页面里的业务组件（如 WpAmountInput）：其模板里的 el-input 同样解析到适配组件 */
  extra: Record<string, Component> = {},
): Promise<VueWrapper> {
  const Host = defineComponent({ template, data, methods })
  const w = mount(Host, { attachTo: document.body, global: { components: { ...gridComponents, ...extra }, mixins: [gridTableMixin] } })
  live.push(w)
  await settle()
  return w
}

export async function settle(): Promise<void> {
  for (let i = 0; i < 4; i++) {
    await flushPromises()
    await nextTick()
  }
}

/** 等内核按帧重画（表体行被替换后选区按坐标重贴）。 */
export async function settleFrames(): Promise<void> {
  await settle()
  await new Promise((r) => setTimeout(r, 40))
  await settle()
}

export function unmountAll(): void {
  while (live.length) live.pop()!.unmount()
  document.body.innerHTML = ''
}

export function bodyRows(w: VueWrapper): HTMLTableRowElement[] {
  return Array.from(w.element.querySelectorAll('table.el-table__body tbody tr.el-table__row')) as HTMLTableRowElement[]
}

export function cell(w: VueWrapper, r: number, c: number): HTMLTableCellElement {
  const row = bodyRows(w)[r]
  if (!row) throw new Error(`没有第 ${r} 行`)
  return row.cells[c] as HTMLTableCellElement
}

/** 页面里第一张表格的内核。 */
export function kernelOf(w: VueWrapper): GridKernel {
  const root = w.element.querySelector('[data-gt-grid-root]') ?? (w.element.hasAttribute?.('data-gt-grid-root') ? w.element : null)
  const k = Array.from(liveKernels).find((x) => x.root === root)
  if (!k) throw new Error('没有表格内核')
  return k
}

export function sink(w: VueWrapper): HTMLTextAreaElement {
  const s = w.element.querySelector('.gt-grid-sink') as HTMLTextAreaElement | null
  if (!s) throw new Error('没有承接框')
  return s
}

export function mousedown(el: Element, init: MouseEventInit = {}): MouseEvent {
  const ev = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0, ...init })
  el.dispatchEvent(ev)
  document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  return ev
}

export function click(el: Element): void {
  mousedown(el)
  el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
}

export function dblclick(el: Element): MouseEvent {
  const ev = new MouseEvent('dblclick', { bubbles: true, cancelable: true, button: 0 })
  el.dispatchEvent(ev)
  return ev
}

export function key(target: Element, k: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const ev = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...init })
  target.dispatchEvent(ev)
  return ev
}

/** 在承接框里「打字」：字符进承接框后发 input（与浏览器默认行为一致）。 */
export function typeInSink(s: HTMLTextAreaElement, text: string): void {
  s.value += text
  s.dispatchEvent(new Event('input', { bubbles: true }))
}

export function activeInput(w: VueWrapper): HTMLInputElement | HTMLTextAreaElement {
  const el = w.element.querySelector('td[data-gt-editing] input, td[data-gt-editing] textarea') as HTMLInputElement | null
  if (!el) throw new Error('没有正在编辑的输入框')
  return el
}

/** 构造剪贴板事件（jsdom 没有 ClipboardEvent / DataTransfer）。 */
export function clipboardEvent(type: 'copy' | 'cut' | 'paste', data: Record<string, string> = {}) {
  const store: Record<string, string> = { ...data }
  const ev = new Event(type, { bubbles: true, cancelable: true }) as Event & { clipboardData: unknown }
  Object.defineProperty(ev, 'clipboardData', {
    value: { getData: (t: string) => store[t] ?? '', setData: (t: string, v: string) => { store[t] = v } },
  })
  return { ev, store }
}
