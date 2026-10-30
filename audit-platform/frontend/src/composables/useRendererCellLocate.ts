/**
 * useRendererCellLocate — GtWpRenderer 的定位调度（spec wp-deeplink-cell-locate-closure 需求 1 / 2.3 / 3）
 *
 * 请求来源：深链初始属性（initialSheet / initialCell）与 `workpaper:locate-cell` 事件。
 * - 渲染配置未到：记为待办（只留最后一个），到达后执行；不再静默丢弃。
 * - 执行：先同步切页签（发事件后 nextTick 即切页的既有语义不变）；有单元格时按 waits 重试：
 *   组件钩子 `locateCell` → 本渲染器根元素内的通用策略（useCellLocate）→ 目录登记的文字锚点（textAnchor，
 *   spec wp-deeplink-locate-coverage-closure；登记了锚点的请求在 waits 后再追加 anchorWaits）。全部失败只提示一次；
 *   新请求到来时旧请求的剩余重试作废。
 */
import { nextTick, onScopeDispose, ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useCellLocate, type LocateTarget } from './useCellLocate'
import { locateTextAnchor } from './textAnchorLocate'
import { extractSheetCodeFromName } from '@/components/formula/sheetIdentityMatch'

export interface RendererLocateRequest {
  wpId: string
  sheetName?: string | null
  cellRef?: string | null
  wpCode?: string | null
  componentType?: string | null
  value?: string | null
  label?: string | null
}

export interface ResolvedLocateSheet {
  sheet_name: string
  sheet_code?: string | null
  componentType?: string | null
}

/** 组件定位钩子（defineExpose({ locateCell })）：返回是否已定位 */
export type ComponentLocateHook = (target: LocateTarget) => boolean | Promise<boolean>

export interface RendererCellLocateDeps {
  wpId: () => string
  /** 渲染配置已到（可解析页签） */
  ready: () => boolean
  resolveSheet: (locator: string) => ResolvedLocateSheet | null | undefined
  activeSheet: () => ResolvedLocateSheet | null | undefined
  selectSheet: (sheetName: string) => void
  /** 本渲染器根元素；为空时不做 DOM 查找（不退回整个 document） */
  root: () => ParentNode | null | undefined
  component: () => { locateCell?: ComponentLocateHook } | null | undefined
  wpCode: () => string
  componentType: () => string | null | undefined
  notify?: (message: string) => void
  /** 第 i 次尝试前的等待（ms）；首项一般为 0 */
  waits?: readonly number[]
  /** 目录登记的文字锚点（sheet 编码 + A1 → 标题文字，spec wp-deeplink-locate-coverage-closure）：前两级都找不到时用 */
  textAnchor?: (sheetCode: string | null, cellRef: string) => string | null
  /** 有文字锚点时在 waits 之后追加的等待（ms）；缺省 TEXT_ANCHOR_EXTRA_WAITS */
  anchorWaits?: readonly number[]
}

export const SHEET_MISSING_MESSAGE = '已打开底稿但未能定位到目标位置（可能已变更）'
export const DEFAULT_LOCATE_WAITS: readonly number[] = [0, 100, 250, 500, 1000]
/** 2026-10-30 浏览器实测：D4 取完数才渲染结论区，标题比页签晚约 2.3 秒出现；默认 1.85 秒内重试完会误报「没有对应位置」 */
export const TEXT_ANCHOR_EXTRA_WAITS: readonly number[] = [1500, 2000, 3000]

type TextAnchorPlan = { text: string; key: string } | null

export function cellMissingMessage(sheetName: string, cellRef: string): string {
  return `「${sheetName}」的网页视图里没有单元格 ${cellRef} 的对应位置`
}

/**
 * 查文字锚点用的 sheet 编码：渲染配置给了 sheet_code 就用它；模板页签（后端不下发 sheet_code、原因 template_sheet_name）
 * 按页签名末尾的结构化编码取（「银行存单盘点表E1-9」→ E1-9，与公式右栏 extractSheetCodeFromName 同一口径），取不到为 null。
 */
export function locateSheetCode(sheet: ResolvedLocateSheet | null | undefined): string | null {
  const code = String(sheet?.sheet_code ?? '').trim() || extractSheetCodeFromName(sheet?.sheet_name)
  return code ? code.toUpperCase() : null
}

export function useRendererCellLocate(deps: RendererCellLocateDeps) {
  const pending = ref<RendererLocateRequest | null>(null) as Ref<RendererLocateRequest | null>
  const notify = deps.notify ?? ((message: string) => { ElMessage.info(message) })
  const waits = deps.waits && deps.waits.length ? deps.waits : DEFAULT_LOCATE_WAITS
  const { locateCell } = useCellLocate()
  let seq = 0

  function request(req: RendererLocateRequest | null | undefined): void {
    if (!req || req.wpId !== deps.wpId()) return
    if (!deps.ready()) {
      pending.value = req
      return
    }
    pending.value = null
    run(req)
  }

  // sync：同一 tick 里就绪状态先假后真也要接住待办（pre 只比较首尾值，会漏掉）
  watch(() => deps.ready(), (isReady) => {
    if (!isReady || !pending.value) return
    const req = pending.value
    pending.value = null
    run(req)
  }, { flush: 'sync' })

  // 组件卸载后作废未完成的重试（不再提示、不再碰 DOM）
  onScopeDispose(() => {
    seq += 1
    pending.value = null
  })

  function run(req: RendererLocateRequest): void {
    const token = ++seq
    let sheet = deps.activeSheet() ?? null
    if (req.sheetName) {
      const resolved = deps.resolveSheet(req.sheetName)
      if (!resolved) {
        notify(SHEET_MISSING_MESSAGE)
        return
      }
      if (resolved.sheet_name !== sheet?.sheet_name) deps.selectSheet(resolved.sheet_name)
      sheet = resolved
    }
    const cellRef = (req.cellRef || '').trim()
    if (!cellRef) return
    const target: LocateTarget = {
      wp_code: req.wpCode || deps.wpCode() || '',
      wp_id: req.wpId,
      sheet_name: sheet?.sheet_name ?? null,
      cell_ref: cellRef,
      component_type: req.componentType || sheet?.componentType || deps.componentType() || null,
      value: req.value || null,
      label: req.label || null,
    }
    const sheetCode = locateSheetCode(sheet)
    const anchorText = deps.textAnchor?.(sheetCode, cellRef) ?? null
    const anchor = anchorText ? { text: anchorText, key: `text:${sheetCode ?? ''}:${cellRef}` } : null
    // 目录登记了文字锚点 ⇒ 该位置在网页视图里应当存在；重组件（如 D4）取完数才渲染结论区，多等一段再下结论
    const plan = anchor ? [...waits, ...(deps.anchorWaits ?? TEXT_ANCHOR_EXTRA_WAITS)] : waits
    schedule(token, target, 0, plan, anchor)
  }

  function schedule(token: number, target: LocateTarget, index: number, plan: readonly number[], anchor: TextAnchorPlan): void {
    const wait = plan[index] ?? 0
    const go = () => { void attempt(token, target, index, plan, anchor) }
    if (wait > 0) setTimeout(go, wait)
    else go()
  }

  async function attempt(token: number, target: LocateTarget, index: number, plan: readonly number[], anchor: TextAnchorPlan): Promise<void> {
    await nextTick()
    if (token !== seq) return
    let ok = false
    const hook = deps.component()?.locateCell
    if (typeof hook === 'function') {
      try {
        ok = !!(await hook(target))
      } catch {
        ok = false
      }
      if (token !== seq) return
    }
    const root = ok ? null : deps.root()
    if (root) ok = locateCell(target, { root })
    if (!ok && root && anchor) ok = locateTextAnchor(root, anchor.text, anchor.key)
    if (ok) return
    if (index + 1 < plan.length) {
      schedule(token, target, index + 1, plan, anchor)
      return
    }
    notify(cellMissingMessage(target.sheet_name || '当前页', target.cell_ref || ''))
  }

  return { request, pending }
}
