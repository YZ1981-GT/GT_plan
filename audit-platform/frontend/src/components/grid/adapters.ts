/**
 * 单元格编辑器适配组件（spec excel-style-table-editing ADR-1 / ADR-5 / design §6 §7）。
 *
 * vite 的组件解析器把模板里的 el-input / el-input-number / el-select / el-date-picker /
 * el-checkbox / el-switch / el-radio-group 解析到这里的同名导出；类型声明为原组件类型。
 *
 * - 表格外（含表头、展开行、弹出层里）：透传原组件，只多一层；只绑 `:model-value` 的输入框
 *   用草稿值兜住，修「打字即被改回」（R9）。
 * - 表体单元格里：平时渲染格式化文本；内核打开时才挂原组件。编辑期 `update:modelValue` / `input`
 *   照常即时转发，`change` 在提交时按最终值发一次，取消时把即时更新还原。
 * - GtGridCell 托管：一直渲染原组件，打开 / 提交 / 取消由 GtGridCell 转交。
 */
import {
  camelize, computed, defineComponent, Fragment, getCurrentInstance, h, inject, nextTick, onBeforeUnmount,
  onBeforeUpdate, onMounted, ref, shallowRef, toHandlerKey,
  type Component, type ComponentInternalInstance, type Slots, type VNode,
} from 'vue'
import {
  ElCheckbox as RawElCheckbox, ElDatePicker as RawElDatePicker, ElInput as RawElInput,
  ElInputNumber as RawElInputNumber, ElRadioGroup as RawElRadioGroup, ElSelect as RawElSelect, ElSwitch as RawElSwitch,
} from 'element-plus/es'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { componentNameOf, detectCellContext } from './cellDetect'
import {
  formatDateDisplay, formatNumberDisplay, formatSelectDisplay, formatTextDisplay, formatToggleCopy,
  parseDateText, parseNumberText, parseSelectText, parseToggleText,
  type CellEditorKind, type ParseResult, type SelectOptionLite,
} from './cellValue'
import {
  CELL_EDITOR_ATTR, nextEditorId, registerEditorHandle, unregisterEditorHandle,
  type CellEditorHandle, type OpenRequest,
} from './editorHost'
import { GRID_CELL_KEY } from './gridCellContext'
import { kernelForContext } from './gridRegistry'

type Attrs = Record<string, unknown>

// ── attrs 读取（模板里 kebab / camel 两种写法都可能出现） ─────────────────────
const hyphenate = (s: string) => s.replace(/\B([A-Z])/g, '-$1').toLowerCase()
const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k)

export function readAttr(attrs: Attrs, camel: string): unknown {
  if (own(attrs, camel)) return attrs[camel]
  const k = hyphenate(camel)
  return own(attrs, k) ? attrs[k] : undefined
}

export function readFlag(attrs: Attrs, camel: string): boolean {
  const v = readAttr(attrs, camel)
  return v === '' || v === true || v === 'true'
}

function readNumber(attrs: Attrs, camel: string): number | undefined {
  const v = readAttr(attrs, camel)
  if (v === undefined || v === null || v === '') return undefined
  const n = Number(v)
  return Number.isFinite(n) ? n : undefined
}

const handlerKey = (event: string) => toHandlerKey(camelize(event))

export function hasListener(attrs: Attrs, event: string): boolean {
  const v = attrs[handlerKey(event)]
  return typeof v === 'function' || (Array.isArray(v) && v.some((f) => typeof f === 'function'))
}

export function callListener(attrs: Attrs, event: string, ...args: unknown[]): void {
  const v = attrs[handlerKey(event)]
  if (typeof v === 'function') (v as (...a: unknown[]) => unknown)(...args)
  else if (Array.isArray(v)) for (const f of v) if (typeof f === 'function') f(...args)
}

const isBlank = (x: unknown) => x === null || x === undefined || x === ''

/** 空值（null / undefined / ''）互相视为相等：进入编辑后原样提交不应发出 change。 */
export function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (isBlank(a) && isBlank(b)) return true
  if (a instanceof Date || b instanceof Date || Array.isArray(a) || Array.isArray(b)) {
    try { return JSON.stringify(a) === JSON.stringify(b) } catch { return false }
  }
  return false
}

function toText(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (Array.isArray(v)) return v.map(toText).join(',')
  return String(v)
}

/** 合成 blur：程序写入（粘贴 / 清空 / 撤销）时给读 `e.target.value` 的宿主用。 */
function syntheticBlur(text: string): FocusEvent {
  const ev = typeof FocusEvent !== 'undefined' ? new FocusEvent('blur') : (new Event('blur') as FocusEvent)
  const fake = { value: text }
  Object.defineProperty(ev, 'target', { value: fake })
  Object.defineProperty(ev, 'currentTarget', { value: fake })
  return ev
}

function nativeInputOf(comp: unknown): HTMLInputElement | HTMLTextAreaElement | null {
  const c = comp as { input?: unknown; textarea?: unknown; $el?: Element } | null
  if (!c) return null
  for (const el of [c.input, c.textarea]) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return el
  }
  const root = c.$el
  return root instanceof Element ? (root.querySelector('input, textarea') as HTMLInputElement | HTMLTextAreaElement | null) : null
}

function typeInto(el: HTMLInputElement | HTMLTextAreaElement, text: string): void {
  el.value = text
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

function caretToEnd(el: HTMLInputElement | HTMLTextAreaElement): void {
  try { el.setSelectionRange(el.value.length, el.value.length) } catch { /* type=number 不支持选区 */ }
}

function safePrefs(): ReturnType<typeof useDisplayPrefsStore> | null {
  try { return useDisplayPrefsStore() } catch { return null }
}

// ── 从插槽里取选项（el-option / el-option-group / el-radio） ──────────────────
function vnodeText(node: unknown): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(vnodeText).join('')
  const v = node as VNode
  const ch = v.children as unknown
  if (typeof ch === 'string') return ch
  if (Array.isArray(ch)) return ch.map(vnodeText).join('')
  if (ch && typeof (ch as { default?: unknown }).default === 'function') {
    try { return vnodeText((ch as { default: () => unknown }).default()) } catch { return '' }
  }
  return ''
}

function walkVNodes(nodes: unknown, visit: (v: VNode, name: string) => boolean | void): void {
  if (Array.isArray(nodes)) { nodes.forEach((n) => walkVNodes(n, visit)); return }
  if (!nodes || typeof nodes !== 'object') return
  const v = nodes as VNode
  if (v.type === Fragment) { walkVNodes(v.children, visit); return }
  const name = (v.type as { name?: string } | null)?.name ?? ''
  if (visit(v, name) === false) return
  const ch = v.children as unknown
  if (Array.isArray(ch)) walkVNodes(ch, visit)
}

function slotOptions(slots: Slots): SelectOptionLite[] {
  const out: SelectOptionLite[] = []
  let nodes: unknown
  try { nodes = slots.default?.() } catch { nodes = [] }
  const visit = (v: VNode, name: string): boolean | void => {
    const p = (v.props ?? {}) as Record<string, unknown>
    if (name === 'ElOption' || name === 'ElRadio' || name === 'ElRadioButton') {
      const value = 'value' in p ? p.value : p.label
      const text = name === 'ElOption' ? (p.label ?? vnodeText(v.children)) : (vnodeText(v.children) || p.label)
      out.push({ label: String(text ?? (typeof value === 'object' ? '' : value ?? '')), value })
      return false
    }
    if (name === 'ElOptionGroup') {
      const ch = v.children as { default?: () => unknown } | unknown
      const inner = ch && typeof (ch as { default?: unknown }).default === 'function' ? (ch as { default: () => unknown }).default() : ch
      walkVNodes(inner, visit)
      return false
    }
  }
  walkVNodes(nodes, visit)
  return out
}

function selectOptions(attrs: Attrs, slots: Slots): SelectOptionLite[] {
  const opts = readAttr(attrs, 'options')
  if (Array.isArray(opts) && opts.length) {
    const alias = (readAttr(attrs, 'props') ?? {}) as { label?: string; value?: string }
    const lk = alias.label || 'label'
    const vk = alias.value || 'value'
    return opts.map((o) => (o && typeof o === 'object'
      ? { label: String((o as Record<string, unknown>)[lk] ?? ''), value: (o as Record<string, unknown>)[vk] }
      : { label: String(o), value: o }))
  }
  return slotOptions(slots)
}

// ── 各组件的口径 ─────────────────────────────────────────────────────────────
interface AdapterSpec {
  name: string
  /** 原组件：渲染时才取（模块求值时不碰 element-plus 的导出 —— 单测里对 element-plus 的局部 mock 只在真渲染到时才需要它们） */
  raw: () => Component
  kind: CellEditorKind
  /** 显示态就是控件本身（勾选 / 开关 / 单选） */
  direct?: boolean
  /** 需要从插槽 / options 取选项：在渲染时取并缓存（插槽只在渲染函数里调用） */
  options?: 'select' | 'radio'
  display(attrs: Attrs, options: () => SelectOptionLite[], value: unknown): string
  parse(text: string, attrs: Attrs, options: () => SelectOptionLite[]): ParseResult
  /** 提交时由原生输入框文字得出最终值（文本 / 数字） */
  finalize?(native: string, attrs: Attrs, openValue: unknown): unknown
  multiline?(attrs: Attrs): boolean
  toggle?(attrs: Attrs, options: () => SelectOptionLite[], value: unknown): unknown
  /** 不按单元格编辑器处理的情形（例如复选框组里的单个复选框） */
  passthroughWhen?(instance: ComponentInternalInstance): boolean
}

function numberOpts(attrs: Attrs) {
  return { precision: readNumber(attrs, 'precision'), min: readNumber(attrs, 'min'), max: readNumber(attrs, 'max') }
}

function toggleOpts(attrs: Attrs, on: string, off: string, legacyOn?: string, legacyOff?: string) {
  const a = readAttr(attrs, on) ?? (legacyOn ? readAttr(attrs, legacyOn) : undefined)
  const b = readAttr(attrs, off) ?? (legacyOff ? readAttr(attrs, legacyOff) : undefined)
  return { activeValue: a === undefined ? true : a, inactiveValue: b === undefined ? false : b }
}

function insideCheckboxGroup(instance: ComponentInternalInstance): boolean {
  for (let p = instance.parent; p; p = p.parent) {
    const name = componentNameOf(p)
    if (name === 'ElCheckboxGroup') return true
    if (name === 'TableTdWrapper' || name === 'ElTable' || name === 'GtGridTable') return false
  }
  return false
}

const SPECS = {
  input: {
    name: 'GtGridElInput',
    raw: () => RawElInput,
    kind: 'text',
    display: (attrs, _s, v) => formatTextDisplay(v, readAttr(attrs, 'type') as string | undefined),
    parse: (text, attrs) => {
      const mods = (readAttr(attrs, 'modelModifiers') ?? {}) as { trim?: boolean }
      return { ok: true, value: mods.trim ? text.trim() : text }
    },
    finalize: (native, attrs) => {
      const mods = (readAttr(attrs, 'modelModifiers') ?? {}) as { trim?: boolean; number?: boolean }
      let v: unknown = mods.trim ? native.trim() : native
      if (mods.number) { const n = Number.parseFloat(String(v)); if (!Number.isNaN(n)) v = n }
      return v
    },
    multiline: (attrs) => readAttr(attrs, 'type') === 'textarea',
  },
  inputNumber: {
    name: 'GtGridElInputNumber',
    raw: () => RawElInputNumber,
    kind: 'number',
    display: (attrs, _s, v) => formatNumberDisplay(v, readNumber(attrs, 'precision')),
    parse: (text, attrs) => parseNumberText(text, numberOpts(attrs)),
    finalize: (native, attrs, openValue) => {
      const r = parseNumberText(native, numberOpts(attrs))
      if (!r.ok) return openValue
      if (r.value === null) {
        const voc = readAttr(attrs, 'valueOnClear')
        if (voc === 'min') return readNumber(attrs, 'min') ?? null
        if (voc === 'max') return readNumber(attrs, 'max') ?? null
        if (typeof voc === 'number') return voc
        return null
      }
      const step = readNumber(attrs, 'step')
      if (step && readFlag(attrs, 'stepStrictly')) return Math.round(r.value / step) * step
      return r.value
    },
  },
  select: {
    name: 'GtGridElSelect',
    raw: () => RawElSelect,
    kind: 'select',
    options: 'select',
    display: (attrs, opts, v) => formatSelectDisplay(v, opts(), readFlag(attrs, 'multiple')),
    parse: (text, attrs, opts) => parseSelectText(text, opts(), {
      multiple: readFlag(attrs, 'multiple'), allowCreate: readFlag(attrs, 'allowCreate'),
    }),
  },
  datePicker: {
    name: 'GtGridElDatePicker',
    raw: () => RawElDatePicker,
    kind: 'date',
    display: (attrs, _s, v) => formatDateDisplay(v, {
      type: readAttr(attrs, 'type') as string | undefined,
      format: readAttr(attrs, 'format') as string | undefined,
      valueFormat: readAttr(attrs, 'valueFormat') as string | undefined,
      rangeSeparator: readAttr(attrs, 'rangeSeparator') as string | undefined,
    }),
    parse: (text, attrs) => parseDateText(text, {
      type: readAttr(attrs, 'type') as string | undefined,
      valueFormat: readAttr(attrs, 'valueFormat') as string | undefined,
    }),
  },
  checkbox: {
    name: 'GtGridElCheckbox',
    raw: () => RawElCheckbox,
    kind: 'toggle',
    direct: true,
    display: (attrs, _s, v) => formatToggleCopy(v, toggleOpts(attrs, 'trueValue', 'falseValue', 'trueLabel', 'falseLabel')),
    parse: (text, attrs) => parseToggleText(text, toggleOpts(attrs, 'trueValue', 'falseValue', 'trueLabel', 'falseLabel')),
    toggle: (attrs, _s, v) => {
      const o = toggleOpts(attrs, 'trueValue', 'falseValue', 'trueLabel', 'falseLabel')
      return sameValue(v, o.activeValue) ? o.inactiveValue : o.activeValue
    },
    passthroughWhen: insideCheckboxGroup,
  },
  switch: {
    name: 'GtGridElSwitch',
    raw: () => RawElSwitch,
    kind: 'toggle',
    direct: true,
    display: (attrs, _s, v) => formatToggleCopy(v, toggleOpts(attrs, 'activeValue', 'inactiveValue')),
    parse: (text, attrs) => parseToggleText(text, toggleOpts(attrs, 'activeValue', 'inactiveValue')),
    toggle: (attrs, _s, v) => {
      const o = toggleOpts(attrs, 'activeValue', 'inactiveValue')
      return sameValue(v, o.activeValue) ? o.inactiveValue : o.activeValue
    },
  },
  radioGroup: {
    name: 'GtGridElRadioGroup',
    raw: () => RawElRadioGroup,
    kind: 'toggle',
    direct: true,
    options: 'radio',
    display: (_a, opts, v) => formatSelectDisplay(v, opts()),
    parse: (text, _a, opts) => parseSelectText(text, opts()),
    toggle: (_a, opts, v) => {
      const list = opts()
      if (!list.length) return v
      const i = list.findIndex((o) => sameValue(o.value, v))
      return list[(i + 1) % list.length].value
    },
  },
} satisfies Record<string, AdapterSpec>

// ── 适配组件 ─────────────────────────────────────────────────────────────────
type Phase = 'idle' | 'open' | 'committing' | 'cancelling'

function defineCellAdapter(spec: AdapterSpec) {
  return defineComponent({
    name: spec.name,
    inheritAttrs: false,
    setup(_props, { attrs, slots, expose }) {
      const instance = getCurrentInstance()!
      const prefs = safePrefs()
      const detected = detectCellContext(instance)
      const ctx = detected && !spec.passthroughWhen?.(instance) ? detected : null
      const hosted = ctx?.kind === 'grid-cell'
      const cellHost = hosted ? inject(GRID_CELL_KEY, null) : null
      const leftCell = ref(false)
      const inCell = computed(() => !!ctx && !hosted && prefs?.gridEditMode !== 'classic' && !leftCell.value)
      const editing = ref(false)
      const focused = ref(false)
      const typing = ref(false)
      const draft = shallowRef<unknown>(undefined)
      const inner = shallowRef<Record<string, unknown> | null>(null)
      const id = nextEditorId()
      let phase: Phase = 'idle'
      let openValue: unknown
      /** 打开那一刻的值（内核记撤销用的 before）；宿主在 focus 里改显示值后 openValue 会换基准，这个不变 */
      let originalOpen: unknown
      let lastValue: unknown
      let liveForwarded = false
      /**
       * 刚把 focus 转发给了监听 focus 的宿主：宿主可能在 focus 里把显示值换成编辑态
       * （WpAmountInput 去千分符、0 显示为空），紧接着的那次重渲染不是「这一格换了行」。
       */
      let focusRebasePending = false
      let optionsCache: SelectOptionLite[] | null = null
      let cellHostFinished: ((value: unknown, refocus: boolean) => void) | null = null
      /**
       * 打开编辑时的 attrs 快照：编辑期间事件一律发给「打开时那一行」的处理函数。
       * 没有 row-key 的 el-table 按下标复用格子 —— 编辑中上方删了一行，这一格就换成了下一行的数据，
       * 不用快照会把打的字提交到别的行上。
       */
      let snap: Attrs | null = null
      const ls = (): Attrs => (phase !== 'idle' && snap ? snap : attrs)

      const model = (): unknown => readAttr(attrs, 'modelValue')
      const twoWay = () => hasListener(ls(), 'update:modelValue')
      const isPick = spec.kind === 'select' || spec.kind === 'date'
      const editable = () => !readFlag(attrs, 'disabled') && !readFlag(attrs, 'readonly')
      const showDisplay = computed(() => inCell.value && !spec.direct && !editing.value)
      /** 单向绑定：打字中 / 编辑中用草稿，其余时候跟宿主的值 */
      const innerModel = (): unknown => (twoWay() ? model() : (typing.value || phase === 'open' ? draft.value : model()))
      /** 选项只在渲染函数里从插槽取（插槽在渲染外调用会丢依赖并告警），其余时候读缓存。 */
      const refreshOptions = () => {
        if (spec.options === 'select') optionsCache = selectOptions(attrs, slots)
        else if (spec.options === 'radio') optionsCache = slotOptions(slots)
      }
      const getOptions = (): SelectOptionLite[] => optionsCache ?? []
      const displayText = (): string => spec.display(attrs, getOptions, model())

      const notifyFinished = (value: unknown, refocus: boolean) => {
        if (hosted) cellHostFinished?.(value, refocus)
        else if (ctx) kernelForContext(ctx)?.editorFinished(handle, value, { refocus })
      }

      const blurInner = () => {
        const el = nativeInputOf(inner.value)
        if (el && typeof document !== 'undefined' && document.activeElement === el) el.blur()
      }

      function commitNow(): unknown {
        phase = 'committing'
        let final: unknown
        if (spec.kind === 'text' || spec.kind === 'number') {
          const el = nativeInputOf(inner.value)
          const text = el ? el.value : toText(twoWay() ? model() : draft.value)
          final = spec.finalize ? spec.finalize(text, attrs, openValue) : text
        } else {
          final = lastValue
        }
        if (!sameValue(final, openValue)) {
          if (!twoWay()) draft.value = final
          if (twoWay() && !sameValue(model(), final)) callListener(ls(), 'update:modelValue', final)
          if (spec.kind === 'number') callListener(ls(), 'change', final, openValue)
          else callListener(ls(), 'change', final)
        }
        return final
      }

      async function open(req: OpenRequest): Promise<boolean> {
        if (!editable()) return false
        if (phase === 'open') return true
        openValue = model()
        originalOpen = openValue
        lastValue = openValue
        draft.value = openValue
        liveForwarded = false
        focusRebasePending = false
        snap = { ...attrs }
        phase = 'open'
        if (!hosted) {
          editing.value = true
          await nextTick()
        }
        const comp = inner.value
        if (!comp) {
          phase = 'idle'
          editing.value = false
          return false
        }
        const el = nativeInputOf(comp)
        const pending = () => req.takePendingText?.() ?? ''
        if (spec.kind === 'select') {
          if (el) el.focus()
          else (comp.focus as (() => void) | undefined)?.()
          if (req.initialText !== undefined && readFlag(attrs, 'filterable') && el) typeInto(el, req.initialText + pending())
        } else if (spec.kind === 'date') {
          ;(comp.focus as (() => void) | undefined)?.()
          ;(comp.handleOpen as (() => void) | undefined)?.()
          if (req.initialText !== undefined && el) typeInto(el, req.initialText + pending())
        } else if (el) {
          el.focus()
          const more = pending()
          if (req.initialText !== undefined) typeInto(el, req.initialText + more)
          else if (more) typeInto(el, el.value + more)
          caretToEnd(el)
        }
        return true
      }

      /** 报给内核的提交值：没改（与换过基准的 openValue 相同）就报打开那一刻的值，免得多记一步空撤销 */
      const reported = (v: unknown): unknown => (sameValue(v, openValue) ? originalOpen : v)

      function commit(): unknown {
        if (phase !== 'open') return model()
        const v = commitNow()
        blurInner()
        phase = 'idle'
        if (!hosted) editing.value = false
        return reported(v)
      }

      function cancel(): void {
        if (phase !== 'open') return
        phase = 'cancelling'
        const el = nativeInputOf(inner.value)
        if (el && (spec.kind === 'text' || spec.kind === 'number')) el.value = toText(openValue)
        draft.value = openValue
        if (liveForwarded) {
          callListener(ls(), 'update:modelValue', openValue)
          if (hasListener(ls(), 'input')) callListener(ls(), 'input', openValue)
        }
        blurInner()
        phase = 'idle'
        if (!hosted) editing.value = false
      }

      function finishPick(committed: boolean): void {
        if (phase !== 'open') return
        phase = 'committing'
        const v = committed ? lastValue : model()
        if (!hosted) editing.value = false
        notifyFinished(v, true)
        phase = 'idle'
      }

      function setValue(v: unknown): boolean {
        if (!editable()) return false
        const old = model()
        if (sameValue(old, v)) return true
        if (!twoWay()) draft.value = v
        callListener(ls(), 'update:modelValue', v)
        if ((spec.kind === 'text' || spec.kind === 'number') && hasListener(attrs, 'input')) callListener(ls(), 'input', v)
        if (spec.kind === 'number') callListener(ls(), 'change', v, old)
        else callListener(ls(), 'change', v)
        if (hasListener(attrs, 'blur')) callListener(ls(), 'blur', syntheticBlur(toText(v)))
        return true
      }

      const handle: CellEditorHandle = {
        id,
        kind: spec.kind,
        editable,
        multiline: () => spec.multiline?.(attrs) ?? false,
        getText: displayText,
        getValue: model,
        isOpen: () => phase === 'open',
        open,
        commit,
        cancel,
        applyText: (text: string) => {
          const r = spec.parse(text, attrs, getOptions)
          if (r.ok && !setValue(r.value)) return { ok: false, reason: '不可编辑' }
          return r
        },
        setValue,
        toggle: spec.toggle ? () => { setValue(spec.toggle!(attrs, getOptions, model())) } : undefined,
      }

      function onInnerBlur(e: FocusEvent): void {
        focused.value = false
        if (!inCell.value && !hosted) {
          callListener(ls(), 'blur', e)
          if (!twoWay()) void nextTick(() => { typing.value = false })
          return
        }
        if (phase !== 'open') { callListener(ls(), 'blur', e); return }
        const next = e.relatedTarget as Element | null
        if (next && typeof next.closest === 'function' && next.closest('.el-popper')) return
        if (isPick) {
          finishPick(false)
          callListener(ls(), 'blur', e)
          return
        }
        // 焦点离开表格：先提交（change 在 blur 之前，与原生顺序一致），再转发 blur
        const v = commitNow()
        callListener(ls(), 'blur', e)
        phase = 'idle'
        if (!hosted) editing.value = false
        notifyFinished(reported(v), false)
      }

      const listeners = {
        'onUpdate:modelValue': (v: unknown) => {
          lastValue = v
          if (!twoWay()) draft.value = v
          if (phase === 'cancelling') return
          if (focused.value && !twoWay()) typing.value = true
          if (phase === 'open' && hasListener(ls(), 'update:modelValue')) liveForwarded = true
          callListener(ls(), 'update:modelValue', v)
        },
        onInput: (v: unknown) => {
          if (phase === 'cancelling') return
          if (phase === 'open' && hasListener(ls(), 'input')) liveForwarded = true
          callListener(ls(), 'input', v)
        },
        onChange: (...args: unknown[]) => {
          if (inCell.value || hosted) {
            if (phase === 'open') {
              if (!isPick) return // 文本 / 数字：提交时统一发
              lastValue = args[0]
              callListener(ls(), 'change', ...args)
              if (!(spec.kind === 'select' && readFlag(attrs, 'multiple'))) finishPick(true)
              return
            }
            if (phase === 'committing' || phase === 'cancelling') return
          }
          callListener(ls(), 'change', ...args)
        },
        onFocus: (e: FocusEvent) => {
          focused.value = true
          const reacts = phase === 'open' && hasListener(ls(), 'focus')
          callListener(ls(), 'focus', e)
          if (reacts) {
            // 宿主在 focus 里改的状态在下一次刷新里渲染出来；刷新完就不再认（之后的变化仍按换行判）
            focusRebasePending = true
            void nextTick(() => { focusRebasePending = false })
          }
        },
        onBlur: onInnerBlur,
        onVisibleChange: (visible: boolean) => {
          callListener(ls(), 'visible-change', visible)
          if (!visible && phase === 'open' && isPick && !(spec.kind === 'select' && readFlag(attrs, 'multiple'))) {
            void nextTick(() => finishPick(lastValue !== openValue))
          }
        },
      }

      function renderDisplay(): VNode {
        const text = displayText()
        const v = model()
        const n = typeof v === 'number' ? v : Number.NaN
        const pass: Record<string, unknown> = {}
        for (const k of Object.keys(attrs)) if (k.startsWith('data-') || k.startsWith('aria-') || k === 'id') pass[k] = attrs[k]
        return h('div', {
          ...pass,
          class: ['gt-cell-display', `gt-cell-display--${spec.kind}`, {
            'gt-cell-display--empty': text === '',
            'gt-cell-display--readonly': !editable(),
            'gt-cell-display--multiline': spec.multiline?.(attrs) ?? false,
            'gt-cell-display--negative': spec.kind === 'number' && prefs?.negativeRed !== false && n < 0,
          }, attrs.class],
          style: attrs.style,
          [CELL_EDITOR_ATTR]: id,
          'data-placeholder': (readAttr(attrs, 'placeholder') as string | undefined) || undefined,
          title: text.length > 24 ? text : undefined,
        }, text)
      }

      /**
       * 编辑中这一格被换成了别的数据（没有 row-key 的表格在上方增删行时按下标复用格子）：
       * 宿主的值既不是打开时的值、也不是本格刚发出去的值 ⇒ 按快照提交给原来那一行并收起编辑器。
       */
      onBeforeUpdate(() => {
        // 已即时转发过（v-model / @input 宿主）：打的字已经写进原来那一行，宿主还可能对值做规整，不在这里判
        if (phase !== 'open' || hosted || liveForwarded) return
        const m = model()
        if (focusRebasePending) {
          // 宿主响应 focus 换了显示值（去千分符等）：以它为新基准；用户已经打了字就保留打的字
          focusRebasePending = false
          if (!sameValue(m, openValue)) {
            const typed = !sameValue(lastValue, openValue)
            openValue = m
            if (!typed) {
              lastValue = m
              if (!twoWay()) draft.value = m
            }
          }
          return
        }
        if (sameValue(m, openValue) || sameValue(m, lastValue)) return
        const v = commitNow()
        if (hasListener(ls(), 'blur') && !sameValue(v, openValue)) callListener(ls(), 'blur', syntheticBlur(toText(v)))
        phase = 'idle'
        editing.value = false
        notifyFinished(reported(v), true)
      })

      onMounted(() => {
        registerEditorHandle(handle)
        if (hosted) {
          cellHost?.register(handle)
          cellHostFinished = (value, refocus) => cellHost?.finished?.(handle, value, refocus)
          return
        }
        if (!ctx) return
        const el = instance.subTree?.el as Element | null
        const td = el instanceof Element ? (el.closest('td, th') as HTMLTableCellElement | null) : null
        if (ctx.kind === 'raw-table' && (!td || td.tagName !== 'TD')) { leftCell.value = true; return }
        if (!inCell.value || spec.direct || !td || !editable()) return
        const k = kernelForContext(ctx)
        if (k && (readFlag(attrs, 'autofocus') || k.hadRecentGesture(td))) {
          void k.openEditor(handle, td, isPick ? 'picking' : 'editing')
        }
      })

      onBeforeUnmount(() => {
        if (phase === 'open') {
          const v = commitNow()
          if (hasListener(ls(), 'blur') && !sameValue(v, openValue)) callListener(ls(), 'blur', syntheticBlur(toText(v)))
          phase = 'idle'
          notifyFinished(reported(v), false)
        }
        unregisterEditorHandle(id)
        if (hosted) cellHost?.unregister(id)
      })

      /** 显示态下的 focus() 等同打开编辑（design §7 规则 2）。 */
      function openFromApi(): Promise<boolean> {
        const el = instance.subTree?.el as Element | null
        const td = el instanceof Element ? (el.closest('td') as HTMLTableCellElement | null) : null
        const k = ctx ? kernelForContext(ctx) : null
        if (!k || !td) return Promise.resolve(false)
        return k.openEditor(handle, td, isPick ? 'picking' : 'editing')
      }

      expose(new Proxy({} as Record<string | symbol, unknown>, {
        get(_t, key) {
          if (key === 'focus') return () => (showDisplay.value ? void openFromApi() : (inner.value?.focus as (() => void) | undefined)?.())
          if (key === 'select') {
            return () => (showDisplay.value
              ? void openFromApi().then(() => (inner.value?.select as (() => void) | undefined)?.())
              : (inner.value?.select as (() => void) | undefined)?.())
          }
          const target = inner.value
          if (!target) return undefined
          const val = target[key as string]
          return typeof val === 'function' ? (val as (...a: unknown[]) => unknown).bind(target) : val
        },
        has(_t, key) {
          if (key === 'focus' || key === 'select') return true
          const target = inner.value
          return !!target && typeof key === 'string' && key in target
        },
      }))

      return () => {
        refreshOptions()
        if (showDisplay.value) return renderDisplay()
        const props: Record<string, unknown> = { ...attrs, ...listeners, ref: inner }
        delete props['model-value']
        props.modelValue = innerModel()
        if (inCell.value) props[CELL_EDITOR_ATTR] = id
        if (inCell.value && editing.value && spec.kind === 'select') props.automaticDropdown = true
        return h(spec.raw(), props, slots)
      }
    },
  })
}

export const ElInput = defineCellAdapter(SPECS.input) as unknown as typeof RawElInput
export const ElInputNumber = defineCellAdapter(SPECS.inputNumber) as unknown as typeof RawElInputNumber
export const ElSelect = defineCellAdapter(SPECS.select) as unknown as typeof RawElSelect
export const ElDatePicker = defineCellAdapter(SPECS.datePicker) as unknown as typeof RawElDatePicker
export const ElCheckbox = defineCellAdapter(SPECS.checkbox) as unknown as typeof RawElCheckbox
export const ElSwitch = defineCellAdapter(SPECS.switch) as unknown as typeof RawElSwitch
export const ElRadioGroup = defineCellAdapter(SPECS.radioGroup) as unknown as typeof RawElRadioGroup

/** 组件解析器映射的组件名（vite.config.ts 与守卫共用）。 */
export const GRID_ADAPTED_COMPONENTS = [
  'ElInput', 'ElInputNumber', 'ElSelect', 'ElDatePicker', 'ElCheckbox', 'ElSwitch', 'ElRadioGroup',
] as const
