/**
 * 表格单元格悬浮来源卡片（spec citar-cell-source-hover R1）：容器上事件委托、整页一张卡片。
 * - 格子写 `data-src="键"`；停留 showDelay 毫秒弹出，移出 hideDelay 毫秒内移入卡片不关；滚动 / Esc 关闭
 * - 整表来源按需请求一次（单飞 + 缓存）；表格数据刷新后调 invalidate()，下次悬停重取
 * - resolve(键, 整表来源)：页面把后端来源与本地信息（样表预置值、操作提示）合成一张卡片；返回 null 不弹
 */
import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { CellSource } from './cellSource'

export interface CellSourceHoverOptions {
  /** 整张表的来源（键 → 来源） */
  load: () => Promise<Record<string, CellSource>>
  /** 合成卡片：sources 为 null 表示还没取到（加载中 / 失败），页面可先给本地信息；extra 为 opts.extra 按格单取的结果 */
  resolve: (key: string, sources: Record<string, CellSource> | null, extra?: CellSource | null) => CellSource | null
  /** 按格单取的补充来源（序时账一行一取；失败按 null） */
  extra?: (key: string) => Promise<CellSource | null>
  /** 不弹卡片的格子（正在编辑的格子） */
  disabled?: (key: string) => boolean
  showDelay?: number
  hideDelay?: number
}

export interface CellSourceCardState {
  visible: boolean
  key: string
  source: CellSource | null
  loading: boolean
  error: string
  anchor: { left: number; top: number; right: number; bottom: number } | null
}

const EMPTY: CellSourceCardState = { visible: false, key: '', source: null, loading: false, error: '', anchor: null }

export function useCellSourceHover(container: Ref<HTMLElement | null | undefined>, opts: CellSourceHoverOptions) {
  const card = ref<CellSourceCardState>({ ...EMPTY })
  let cache: Record<string, CellSource> | null = null
  let inflight: Promise<Record<string, CellSource>> | null = null
  let epoch = 0
  let showTimer: ReturnType<typeof setTimeout> | undefined
  let hideTimer: ReturnType<typeof setTimeout> | undefined
  let hoverKey = ''

  function clearTimers() {
    clearTimeout(showTimer)
    clearTimeout(hideTimer)
  }

  function close() {
    clearTimers()
    hoverKey = ''
    card.value = { ...EMPTY }
  }

  async function loadAll(): Promise<Record<string, CellSource>> {
    if (cache) return cache
    if (!inflight) {
      const mine = epoch
      inflight = opts.load().then(
        (res) => {
          if (mine === epoch) cache = res
          return res
        },
        (e) => {
          throw e
        },
      ).finally(() => {
        if (mine === epoch) inflight = null
      })
    }
    return inflight
  }

  /** 指针此刻所在的格子（mouseover 记、mouseout 离开格子时清）：表格刷新后据此重新计时 */
  let pointerCell: HTMLElement | null = null

  function invalidate() {
    epoch += 1
    cache = null
    inflight = null
    close()
    // 指针停在格子上不动时浏览器不会再发 mouseover —— 刷新前已悬停的格子要重新计时，否则要挪一下鼠标才弹
    // （批 5 实测：汇算申报表打开时指针已在格子上，取值回来触发 invalidate，卡片一直不出来）
    if (pointerCell) schedule(pointerCell)
  }

  async function open(key: string, el: HTMLElement) {
    const r = el.getBoundingClientRect()
    const anchor = { left: r.left, top: r.top, right: r.right, bottom: r.bottom }
    const local = opts.resolve(key, cache)
    if (cache && !opts.extra) {
      if (local) card.value = { visible: true, key, source: local, loading: false, error: '', anchor }
      else close()
      return
    }
    card.value = { visible: true, key, source: local, loading: true, error: '', anchor }
    const mine = epoch
    try {
      const all = await loadAll()
      const extra = opts.extra ? await opts.extra(key).catch(() => null) : undefined
      if (mine !== epoch || hoverKey !== key) return
      const src = opts.resolve(key, all, extra)
      if (src) card.value = { visible: true, key, source: src, loading: false, error: '', anchor }
      else close()
    } catch (e: any) {
      if (mine !== epoch || hoverKey !== key) return
      const msg = e?.response?.data?.detail || e?.message || '读取数据来源失败'
      card.value = { ...card.value, loading: false, error: typeof msg === 'string' ? msg : '读取数据来源失败' }
    }
  }

  function cellOf(target: EventTarget | null): HTMLElement | null {
    const el = target instanceof Element ? target.closest<HTMLElement>('[data-src]') : null
    return el && container.value?.contains(el) ? el : null
  }

  function onOver(e: MouseEvent) {
    const el = cellOf(e.target)
    pointerCell = el
    if (!el) return
    const key = el.dataset.src ?? ''
    if (!key || key === hoverKey) {
      clearTimeout(hideTimer)
      return
    }
    schedule(el)
  }

  /** 从此格开始计时弹卡片（编辑中的格子不弹） */
  function schedule(el: HTMLElement) {
    const key = el.dataset.src ?? ''
    clearTimers()
    hoverKey = key
    if (!key || opts.disabled?.(key)) {
      close()
      return
    }
    showTimer = setTimeout(() => {
      // 刷新期间格子可能被重新渲染：按键在容器里重新找
      const cur = el.isConnected ? el : container.value?.querySelector<HTMLElement>(`[data-src="${key.replace(/["\\]/g, '\\$&')}"]`)
      if (cur) void open(key, cur)
    }, opts.showDelay ?? 400)
  }

  function onOut(e: MouseEvent) {
    const from = cellOf(e.target)
    if (!from) return
    const to = cellOf(e.relatedTarget)
    if (to && to.dataset.src === from.dataset.src) return
    pointerCell = to
    scheduleHide()
  }

  function scheduleHide() {
    clearTimeout(showTimer)
    clearTimeout(hideTimer)
    hideTimer = setTimeout(close, opts.hideDelay ?? 200)
  }

  /** 卡片的 mouseenter / mouseleave 绑这两个 */
  const onCardEnter = () => clearTimeout(hideTimer)
  const onCardLeave = () => scheduleHide()

  function onScroll(e: Event) {
    if (!card.value.visible) return
    // 卡片自己的列表滚动不关
    if (e.target instanceof Element && e.target.closest('[data-cell-source-card]')) return
    pointerCell = null // 主动关的，刷新后不再自动弹
    close()
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape' && card.value.visible) {
      pointerCell = null
      close()
    }
  }

  // sync：模板 ref 一赋值就挂监听（默认 pre 要等下一个微任务，期间的悬停会丢）
  watch(container, (el, old) => {
    old?.removeEventListener('mouseover', onOver)
    old?.removeEventListener('mouseout', onOut)
    el?.addEventListener('mouseover', onOver)
    el?.addEventListener('mouseout', onOut)
  }, { immediate: true, flush: 'sync' })

  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('keydown', onKey)
  onBeforeUnmount(() => {
    clearTimers()
    container.value?.removeEventListener('mouseover', onOver)
    container.value?.removeEventListener('mouseout', onOut)
    window.removeEventListener('scroll', onScroll, true)
    window.removeEventListener('keydown', onKey)
  })

  return { card, close, invalidate, onCardEnter, onCardLeave }
}
