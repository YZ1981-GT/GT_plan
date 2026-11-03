import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { createChecklistCasClient } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import type { ChecklistResponse } from './useF1FormData'

export function useF5CosSalFormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  /** F5-7 成本倒轧 TB 自动取数（1401/1404/1405 期初期末，来自 render 策略） */
  const rollforwardTb = ref<Record<string, number>>({})
  /** F5-7 校验区审定营业成本回退值（来自 render 策略持久化读取） */
  const adjudicatedCogs = ref<number>(0)
  /** 后端 render 提供的 project_context（含 tb_amount/bs_date/related_parties 等） */
  const projectContext = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const cas = createChecklistCasClient()
  const queue = createChecklistWriteQueue<ChecklistResponse>({
    readLatest: (itemId) => allResponses.value.get(itemId),
    persist: async (items) => {
      if (!opts.wpId.value) throw new Error('缺少底稿标识，无法保存')
      await cas.save({ wpId: opts.wpId.value, projectId: opts.projectId.value, items })
    },
  })
  const itemPrefix = 'F5-'

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      cas.remember(responses)
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith(itemPrefix)) {
          map.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('F5数据加载失败，可手动填写')
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        (async () => {
          const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
            params: { force_component_type: 'f5-cost-of-sales' }, _silent: true,
          } as any)
          const data = res?.data ?? res
          for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
            const hd = s.html_data ?? s
            sheetCache.value[s.sheet_name || s.name || 'default'] = hd
            // render 策略在各 F5 sheet 的 html_data 中携带 rollforward_tb / adjudicated_cogs
            if (hd && typeof hd === 'object') {
              if (hd.rollforward_tb && typeof hd.rollforward_tb === 'object') {
                rollforwardTb.value = hd.rollforward_tb
              }
              if (hd.adjudicated_cogs != null && hd.adjudicated_cogs !== '') {
                const n = Number(hd.adjudicated_cogs)
                if (Number.isFinite(n)) adjudicatedCogs.value = n
              }
              if (hd.project_context && typeof hd.project_context === 'object') {
                projectContext.value = hd.project_context
              }
            }
          }
        })(),
      ])
    } finally { isLoading.value = false }
  }

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>) {
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    queue.mark(itemId)
    await queue.flush()
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data }
    allResponses.value.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    queue.mark(itemId)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void queue.flush().catch(() => undefined)
    }, 2000))
  }

  /** 批量保存多个 item（一次 strict-CAS PUT 提交，用于导入/整表提交）。 */
  async function saveBatch(items: Array<{ item_id: string } & Partial<ChecklistResponse>>) {
    if (!items.length) return
    const payload = items.map((it) => {
      const timer = _debounceTimers.get(it.item_id)
      if (timer) clearTimeout(timer)
      _debounceTimers.delete(it.item_id)
      const existing = allResponses.value.get(it.item_id) || { item_id: it.item_id, conclusion: null, remark: null }
      const updated = { ...existing, ...it, item_id: it.item_id }
      allResponses.value.set(it.item_id, updated)
      return updated
    })
    queue.markMany(payload.map((item) => item.item_id))
    await queue.flush()
  }

  function getSheet(name: string) { return sheetCache.value[name] ?? { rows: [] } }

  // ─── trial_balance 回写：已移除 writebackTrialBalance（spec tb-writeback-explicit-publish-gate Task 3） ──
  // 原 writebackTrialBalance 直调旧端点 PUT /projects/{pid}/trial-balance/writeback 绕过确认门。
  // 改造后 TB 回写走显式发布门（F5TabAdjudication.publishToTb → publish-to-tb，发生额口径）。
  // 唯一消费方 GtF5CostOfSales.handleF5Writeback 已随监听器移除 ⇒ 此函数为零消费死代码。

  /**
   * flush 掉 2s debounce 未落库的编辑。
   *
   * 🔴 修复两处真缺陷（原实现 `onScopeDispose` 只 clearTimeout **不保存**）：
   *   1. 卸载/切 sheet 时，debounce 窗口内的编辑被静默丢弃；
   *   2. syncBridge 的 flushHtml 若不 flush，readStoreProjection 读到旧快照，
   *      切到 OO 侧后会用旧值覆盖 HTML 侧刚写的编辑。
   * 取值口径与 D3/F3/F4 一致：从 `allResponses` 取最新值，不用 timer 闭包的旧快照。
   */
  async function _flushPending(): Promise<void> {
    for (const t of _debounceTimers.values()) clearTimeout(t)
    _debounceTimers.clear()
    await queue.flush()
  }

  onScopeDispose(() => { void _flushPending().catch(() => undefined) })

  return {
    isLoading,
    sheetCache,
    allResponses,
    rollforwardTb,
    adjudicatedCogs,
    projectContext,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    saveBatch,
    // F5-8 canary：syncBridge 的 flushHtml 第一步须 flush 掉 2s debounce 未落库的编辑。
    flushPendingSave: _flushPending,
  }
}
