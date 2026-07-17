/**
 * useNoteAutoFill — 附注跨表取数统一 SDK（P2 · 附注联动加固）
 *
 * 背景：各循环附注 tab 的 `refreshFromAdjudication` 口径三花八门（有的读
 * `formData.allResponses.get('X-1-*')`、有的读 `crossSheetAutoFill`、有的读 render-config），
 * 且 `substantive:adjudicated` 订阅逻辑各自实现（brittle 的 wpCode+accountCode 双条件、
 * 甚至失效的 SSE）。本 SDK 把「订阅审定事件 → 从 allResponses 按 item_id 取数 → 回调应用」
 * 收敛为一处参数化实现：
 *  - 经 `eventBus`（已由 crossWpEventBridge 桥接 window/mitt 两传输通道）订阅
 *    `substantive:adjudicated` / `trial-balance:updated`；
 *  - 可按 `accountCodes` 过滤（不传则任意审定事件都刷新）；
 *  - 支持可选 `reload()`（先回后端拉最新 allResponses 再取数）；
 *  - `onRefresh(values, raw)` 回调把取到的数值交给组件应用到自己的行模型；
 *  - 去抖，onMounted 先 pull 一次，onUnmounted 自动 off。
 *
 * 只做「取数 + 分发」，不假设行结构，故可被任意附注 tab 复用。
 *
 * @see .kiro/steering/memory.md §待办（复盘发现）附注模块跨模块联动复盘
 */
import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'

export interface NoteAutoFillOptions {
  /** 数据源真值（父入口或 formData 提供的 responses Map 的 Ref）。 */
  allResponses: Ref<Map<string, any>>
  /** 逻辑键 → checklist_responses item_id 映射。 */
  sources: Record<string, string>
  /** 读取字段：默认先 remark 再回退 conclusion。 */
  field?: 'remark' | 'conclusion'
  /** 仅当 substantive:adjudicated 的 accountCode 命中时刷新；不传=任意审定事件都刷新。 */
  accountCodes?: string[]
  /** 取数后的回调：values=按 sources 键解析出的数值，raw=原始 response 对象。 */
  onRefresh?: (values: Record<string, number | null>, raw: Record<string, any>) => void
  /** 可选：刷新前先回后端拉最新数据（如 formData.loadData）。 */
  reload?: () => Promise<void> | void
  /** 去抖毫秒，默认 300。 */
  debounceMs?: number
  /** 是否同时订阅 trial-balance:updated，默认 true。 */
  subscribeTbUpdated?: boolean
}

/** 宽松数值解析：非有限数返回 null（区别于 0）。 */
export function parseNoteNumber(v: any): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export function useNoteAutoFill(opts: NoteAutoFillOptions) {
  const field = opts.field ?? 'remark'
  const debounceMs = opts.debounceMs ?? 300
  const subscribeTb = opts.subscribeTbUpdated !== false

  const values = ref<Record<string, number | null>>({})
  const rawValues = ref<Record<string, any>>({})
  const lastRefreshAt = ref<string>('')

  /** 从 allResponses 按 sources 取数并触发 onRefresh。 */
  function pull(): void {
    const nextValues: Record<string, number | null> = {}
    const nextRaw: Record<string, any> = {}
    const map = opts.allResponses.value
    for (const [key, itemId] of Object.entries(opts.sources)) {
      const resp = map?.get?.(itemId)
      nextRaw[key] = resp ?? null
      const rawVal = resp?.[field] ?? resp?.conclusion ?? resp?.remark
      nextValues[key] = parseNoteNumber(rawVal)
    }
    values.value = nextValues
    rawValues.value = nextRaw
    lastRefreshAt.value = new Date().toLocaleTimeString('zh-CN')
    opts.onRefresh?.(nextValues, nextRaw)
  }

  let timer: ReturnType<typeof setTimeout> | null = null
  function scheduleRefresh(): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      timer = null
      if (opts.reload) {
        try {
          await opts.reload()
        } catch {
          /* reload 失败仍尝试 pull 现有数据 */
        }
      }
      pull()
    }, debounceMs)
  }

  function onAdjudicated(payload: any): void {
    const codes = opts.accountCodes
    if (codes && codes.length > 0) {
      const code = payload?.accountCode
      if (!code || !codes.includes(String(code))) return
    }
    scheduleRefresh()
  }

  function onTbUpdated(): void {
    scheduleRefresh()
  }

  onMounted(() => {
    pull()
    eventBus.on('substantive:adjudicated', onAdjudicated)
    if (subscribeTb) eventBus.on('trial-balance:updated', onTbUpdated)
  })

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
    eventBus.off('substantive:adjudicated', onAdjudicated)
    if (subscribeTb) eventBus.off('trial-balance:updated', onTbUpdated)
  })

  return { values, rawValues, lastRefreshAt, refresh: scheduleRefresh, pull }
}
